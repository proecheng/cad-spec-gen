"""
parts_resolver.py — Unified parts library resolver (Phase A).

This module is the single entry point that `codegen/gen_std_parts.py` calls to
decide how to generate geometry for each purchased BOM part:

    result = resolver.resolve(query)

The resolver consults an ordered list of adapters, returning the first hit:

    StepPoolAdapter (project-local STEP files)    — Phase B
    BdWarehouseAdapter (parametric hardware)      — Phase A (this file)
    PartCADAdapter (package manager)              — Phase C
    JinjaPrimitiveAdapter (current _gen_* dispatch) — fallback, always wins last

Adapters are registered via the YAML registry `parts_library.yaml`. See the
plan at C:\\Users\\procheng\\.claude\\plans\\curious-meandering-hearth.md for
design rationale.

Key contracts (DO NOT BREAK):
- Generated `std_*.py` still exposes `make_std_*() -> cq.Workplane` with no args
- The ResolveResult.kind discriminates how gen_std_parts.py emits the function
  body but the module-level interface stays identical
- When no `parts_library.yaml` is present, resolver is a no-op (empty registry +
  JinjaPrimitiveAdapter fallback) and output is byte-identical to pre-refactor
- bd_warehouse / partcad remain optional imports — adapters lazy-load them
"""

from __future__ import annotations

import fnmatch
import hashlib
import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

# Task 7：ResolveResult.category 用 9 类 PartCategory 做权威路由
# sw_preflight.types 只依赖 diagnosis，没有反向 import parts_resolver，
# 故直接 import 无循环风险（若将来出现循环再改 TYPE_CHECKING + 字符串注解）
from sw_preflight.types import PartCategory

__all__ = [
    "PartQuery",
    "ResolveResult",
    "ResolveMode",
    "GeometryDecision",
    "AdapterHit",
    "ResolveReportRow",
    "ResolveReport",
    "PartsResolver",
    "load_registry",
    "default_resolver",
]


# ─── Data types ───────────────────────────────────────────────────────────


@dataclass
class PartQuery:
    """Inputs used by adapters to match + resolve a BOM row to geometry."""

    part_no: str                    # "GIS-EE-001-05"
    name_cn: str                    # "Maxon ECX SPEED 22L 减速电机"
    material: str                   # BOM material column
    category: str                   # classify_part() output
    make_buy: str                   # "外购" / "标准" / "自制"
    spec_envelope: Optional[tuple] = None  # (w, d, h) from §6.4 if known
    spec_envelope_granularity: str = "part_envelope"  # "station_constraint" must NOT size individual parts
    project_root: str = ""          # base path for relative STEP paths


ResolveKind = Literal["codegen", "step_import", "python_import", "miss"]
ResolveMode = Literal["inspect", "probe", "export", "codegen"]


@dataclass
class GeometryDecision:
    """Stable, side-effect-free record of how one BOM row was resolved."""

    part_no: str
    name_cn: str
    status: str
    kind: ResolveKind
    adapter: str
    source_tag: str = ""
    geometry_source: str = ""
    geometry_quality: str = ""
    validated: bool = False
    hash: Optional[str] = None
    path_kind: str = ""
    requires_model_review: bool = False
    step_path: Optional[str] = None
    real_dims: Optional[tuple] = None
    attempted_adapters: list[str] = field(default_factory=list)
    config_match: str = "n/a"
    category: str = ""
    warnings: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "part_no": self.part_no,
            "name_cn": self.name_cn,
            "status": self.status,
            "kind": self.kind,
            "adapter": self.adapter,
            "source_tag": self.source_tag,
            "geometry_source": self.geometry_source,
            "geometry_quality": self.geometry_quality,
            "validated": self.validated,
            "hash": self.hash,
            "path_kind": self.path_kind,
            "requires_model_review": self.requires_model_review,
            "step_path": self.step_path,
            "real_dims": self.real_dims,
            "attempted_adapters": self.attempted_adapters,
            "config_match": self.config_match,
            "category": self.category,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class ResolveResult:
    """Output of PartsResolver.resolve().

    gen_std_parts.py inspects `kind` to decide what function body to emit:

        kind="codegen"        → body_code is a string (current behavior)
        kind="step_import"    → step_path, emit cq.importers.importStep(...)
        kind="python_import"  → import_module + import_symbol, emit lazy import
        kind="miss"           → nothing matched, caller should skip or fallback
    """

    status: Literal["hit", "miss", "fallback", "skip"]
    kind: ResolveKind
    adapter: str                            # which adapter produced this
    body_code: Optional[str] = None
    step_path: Optional[str] = None
    import_module: Optional[str] = None
    import_symbol: Optional[str] = None
    import_args: str = ""                   # literal args for the call
    real_dims: Optional[tuple] = None       # (w, d, h) mm from the library
    source_tag: str = ""                    # human-readable origin
    geometry_source: str = ""               # REAL_STEP / SW_TOOLBOX_STEP / ...
    geometry_quality: str = ""              # A-E quality grade for reporting
    validated: bool = False                 # True when source can be verified now
    hash: Optional[str] = None              # sha256:<prefix> for validated files
    path_kind: str = ""                     # project_relative / absolute / ...
    requires_model_review: bool = False     # True for simplified or missing geometry
    warnings: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # adapter-specific extras
    # Task 7：9 类零件分类。默认 CUSTOM（兜底），resolve() 命中后由
    # _infer_category(rule, adapter) 覆写成更具体的 PartCategory。
    category: PartCategory = PartCategory.CUSTOM

    @classmethod
    def miss(cls) -> "ResolveResult":
        return cls(
            status="miss",
            kind="miss",
            adapter="",
            category=PartCategory.CUSTOM,
        )

    @classmethod
    def skip(cls, *, reason: str = "") -> "ResolveResult":
        return cls(
            status="skip",
            kind="miss",
            adapter="",
            category=PartCategory.CUSTOM,
            source_tag=reason,
        )

    def to_geometry_decision(
        self,
        query: PartQuery,
        attempted_adapters: Optional[list[str]] = None,
    ) -> GeometryDecision:
        """Convert this result into the durable geometry decision schema."""
        return GeometryDecision(
            part_no=query.part_no,
            name_cn=query.name_cn,
            status=self.status,
            kind=self.kind,
            adapter=self.adapter,
            source_tag=self.source_tag,
            geometry_source=self.geometry_source,
            geometry_quality=self.geometry_quality,
            validated=self.validated,
            hash=self.hash,
            path_kind=self.path_kind,
            requires_model_review=self.requires_model_review,
            step_path=self.step_path,
            real_dims=self.real_dims,
            attempted_adapters=list(attempted_adapters or []),
            config_match=(self.metadata or {}).get("config_match", "n/a"),
            category=getattr(self.category, "value", str(self.category)),
            warnings=list(self.warnings or []),
            metadata=dict(self.metadata or {}),
        )


# ─── Adapter protocol ─────────────────────────────────────────────────────
#
# The adapter base class lives in adapters/parts/base.py to keep this file
# small. We define the resolver loop here and import adapters lazily.


@dataclass
class AdapterHit:
    count: int
    unavailable_reason: Optional[str]


@dataclass
class ResolveReportRow:
    bom_id: str
    name_cn: str
    matched_adapter: str
    attempted_adapters: list[str]
    status: str  # "hit" | "fallback" | "miss" | "skip"
    config_match: str = "n/a"  # B-16: "matched" | "fallback" | "n/a"


@dataclass
class ResolveReport:
    schema_version: int = 1
    run_id: str = ""
    total_rows: int = 0
    adapter_hits: dict[str, AdapterHit] = field(default_factory=dict)
    rows: list[ResolveReportRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "total_rows": self.total_rows,
            "adapter_hits": {
                name: {"count": h.count, "unavailable_reason": h.unavailable_reason}
                for name, h in self.adapter_hits.items()
            },
            "rows": [
                {
                    "bom_id": r.bom_id,
                    "name_cn": r.name_cn,
                    "matched_adapter": r.matched_adapter,
                    "attempted_adapters": r.attempted_adapters,
                    "status": r.status,
                    "config_match": r.config_match,
                }
                for r in self.rows
            ],
        }


class PartsResolver:
    """Ordered dispatch over parts adapters.

    Usage::

        resolver = default_resolver(project_root=".")
        result = resolver.resolve(query)
        if result.kind == "codegen":
            body = result.body_code
        elif result.kind == "step_import":
            body = f'return cq.importers.importStep("{result.step_path}").val()'
        ...
    """

    def __init__(
        self,
        project_root: str = "",
        registry: Optional[dict] = None,
        adapters: Optional[list] = None,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.project_root = project_root or os.getcwd()
        self.registry = registry or {}
        self.adapters = list(adapters or [])
        self.log = logger or (lambda msg: None)
        self._probe_cache: dict = {}
        self._decision_log: list = []  # GeometryDecision; legacy tuple accepted in tests

    # ---- adapter registration --------------------------------------------

    def register_adapter(self, adapter) -> None:
        """Register an adapter. Order matters: adapters are tried in order."""
        self.adapters.append(adapter)

    def available_adapter_names(self) -> list[str]:
        return [a.name for a in self.adapters if a.is_available()[0]]

    def matching_rules(
        self,
        query: PartQuery,
        *,
        adapter_name: str | None = None,
    ) -> list[dict]:
        """Return registry rules matching a query without touching adapters."""
        rules = []
        for rule in self.registry.get("mappings", []) or []:
            if not isinstance(rule, dict):
                continue
            if adapter_name is not None and rule.get("adapter", "") != adapter_name:
                continue
            if _match_rule(rule.get("match", {}), query):
                rules.append(rule)
        return rules

    # ---- core resolve loop ------------------------------------------------

    def resolve(
        self,
        query: PartQuery,
        _trace: list[str] | None = None,
        mode: ResolveMode = "codegen",
    ) -> ResolveResult:
        """Match query against registry mappings, dispatch to the winning adapter.

        Algorithm:
          1. Walk `registry["mappings"]` top-to-bottom
          2. For each rule, check if its `match:` block satisfies the query
          3. If yes, find the adapter named in `rule["adapter"]` and call resolve()
          4. On hit, log the decision and return
          5. If no rule matches, fall through to the last-resort adapter
             (JinjaPrimitiveAdapter, which always answers with codegen kind)
        """
        trace = _trace if _trace is not None else []
        for rule in self.registry.get("mappings", []):
            if not _match_rule(rule.get("match", {}), query):
                continue
            adapter_name = rule.get("adapter", "")
            adapter = self._find_adapter(adapter_name)
            if adapter is None:
                self.log(f"  [resolver] rule matches {query.part_no} but "
                         f"adapter '{adapter_name}' not available")
                trace.append(f"{adapter_name}(not_registered)")
                continue
            _ok, _reason = adapter.is_available()
            if not _ok:
                self.log(f"  [resolver] adapter '{adapter_name}' unavailable"
                         + (f": {_reason}" if _reason else ""))
                trace.append(f"{adapter_name}(unavailable)")
                continue
            spec = rule.get("spec", {})
            try:
                result = self._call_adapter_resolve(adapter, query, spec, mode)
            except Exception as e:
                from adapters.solidworks.sw_config_broker import NeedsUserDecision

                if isinstance(e, NeedsUserDecision):
                    raise
                self.log(f"  [resolver] adapter '{adapter_name}' raised "
                         f"on {query.part_no}: {e} — falling through")
                trace.append(f"{adapter_name}(error)")
                continue
            if result.status == "hit":
                result.adapter = result.adapter or adapter_name
                # Task 7：按 mapping + adapter 类型推断分类
                result.category = _infer_category(rule, adapter)
                trace.append(f"{adapter_name}(hit)")
                self._enrich_result_geometry(result, query)
                self._record_decision(query, result, trace)
                return result
            if result.status == "skip":
                result.adapter = result.adapter or adapter_name
                trace.append(f"{adapter_name}(skip)")
                self._enrich_result_geometry(result, query)
                self._record_decision(query, result, trace)
                return result
            trace.append(f"{adapter_name}(miss)")

        # Terminal fallback: jinja_primitive (guaranteed available)
        fallback = self._find_adapter("jinja_primitive")
        if fallback is not None:
            result = self._call_adapter_resolve(fallback, query, {}, mode)
            if result.status == "hit":
                result.adapter = result.adapter or "jinja_primitive"
                # Task 7：兜底 fallback 统一 CUSTOM（规则视角无 match/spec 线索）
                result.category = PartCategory.CUSTOM
                self._enrich_result_geometry(result, query)
                if _result_requires_fallback_review(result):
                    result.status = "fallback"
                    trace.append("jinja_primitive(fallback)")
                else:
                    trace.append("jinja_primitive(hit)")
                self._record_decision(query, result, trace)
                return result
            if result.status == "skip":
                result.adapter = result.adapter or "jinja_primitive"
                trace.append("jinja_primitive(skip)")
                self._enrich_result_geometry(result, query)
                self._record_decision(query, result, trace)
                return result

        result = ResolveResult.miss()
        self._enrich_result_geometry(result, query)
        self._record_decision(query, result, trace)
        return result

    def prewarm(self, queries: list["PartQuery"]) -> None:
        """Pre-warm hook：派发 candidates 给所有 adapter（Task 14.6 / spec §3.1）。

        rule matching 在 resolver 层做（不在 adapter 层）：adapter 不知道 rule.spec，
        必须由 resolver 按 first-hit-wins 算出 (query, rule.spec) tuple 派发给目标 adapter。

        Per-adapter try/except：单 adapter 失败不阻其他 adapter / 不阻 codegen
        （prewarm 是加速优化不是必要前置）。

        Returns None — fire-and-forget。
        """
        for adapter in self.adapters:
            candidates = []  # list[tuple[PartQuery, dict]]
            for q in queries:
                for rule in self.registry.get("mappings", []):
                    if not _match_rule(rule.get("match", {}), q):
                        continue
                    if rule.get("adapter", "") != adapter.name:
                        break  # first-hit 不归此 adapter，跳过此 query
                    candidates.append((q, rule.get("spec", {})))
                    break  # first-hit-wins 与 PartsResolver.resolve 一致
            if not candidates:
                continue
            try:
                adapter.prewarm(candidates)
            except Exception as e:
                self.log(f"  [resolver] prewarm '{adapter.name}' failed: {e}")
        return None

    def probe_dims(self, query: PartQuery) -> Optional[tuple]:
        """Fast (w, d, h) lookup for Phase 1 envelope backfill.

        Does not build geometry. Uses a per-resolver cache so the same part
        queried twice (once for backfill, once for codegen) only incurs cost
        once.
        """
        cache_key = (query.part_no, query.name_cn, query.category)
        if cache_key in self._probe_cache:
            return self._probe_cache[cache_key]

        for rule in self.registry.get("mappings", []):
            if not _match_rule(rule.get("match", {}), query):
                continue
            adapter_name = rule.get("adapter", "")
            adapter = self._find_adapter(adapter_name)
            if adapter is None:
                continue
            _ok, _ = adapter.is_available()
            if not _ok:
                continue
            try:
                dims = adapter.probe_dims(query, rule.get("spec", {}))
            except Exception:
                dims = None
            if dims is not None:
                self._probe_cache[cache_key] = dims
                return dims

        self._probe_cache[cache_key] = None
        return None

    def _call_adapter_resolve(
        self,
        adapter,
        query: PartQuery,
        spec: dict,
        mode: ResolveMode,
    ) -> ResolveResult:
        """Call adapter.resolve with mode when the adapter supports it."""
        try:
            sig = inspect.signature(adapter.resolve)
        except (TypeError, ValueError):
            return adapter.resolve(query, spec)

        params = sig.parameters
        accepts_mode = "mode" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in params.values()
        )
        if accepts_mode:
            return adapter.resolve(query, spec, mode=mode)
        return adapter.resolve(query, spec)

    def _enrich_result_geometry(
        self,
        result: ResolveResult,
        query: PartQuery,
    ) -> ResolveResult:
        """Fill geometry quality/source defaults without changing adapter APIs."""
        if result.geometry_source and result.geometry_quality:
            return result

        adapter = result.adapter or ""
        if result.status in {"miss", "skip"} or result.kind == "miss":
            result.geometry_source = result.geometry_source or "MISSING"
            result.geometry_quality = result.geometry_quality or "E"
            result.requires_model_review = True
            return result

        if adapter == "sw_toolbox" and result.kind == "step_import":
            result.geometry_source = result.geometry_source or "SW_TOOLBOX_STEP"
            result.geometry_quality = result.geometry_quality or "A"
        elif adapter == "step_pool" and result.kind == "step_import":
            result.geometry_source = result.geometry_source or "REAL_STEP"
            result.geometry_quality = result.geometry_quality or "A"
        elif adapter == "bd_warehouse":
            result.geometry_source = result.geometry_source or "BD_WAREHOUSE"
            result.geometry_quality = result.geometry_quality or "B"
            result.validated = True
        elif adapter == "partcad":
            result.geometry_source = result.geometry_source or "PARTCAD"
            result.geometry_quality = result.geometry_quality or "B"
            result.validated = True
        elif adapter == "jinja_primitive":
            result.geometry_source = result.geometry_source or "JINJA_PRIMITIVE"
            result.geometry_quality = result.geometry_quality or "D"
            result.requires_model_review = True
        else:
            result.geometry_source = result.geometry_source or adapter.upper()
            result.geometry_quality = result.geometry_quality or "C"

        if result.step_path:
            step_abs = self._resolve_result_path(result.step_path, query)
            result.path_kind = result.path_kind or self._path_kind(
                result.step_path, step_abs
            )
            if step_abs and os.path.isfile(step_abs):
                result.validated = True
                result.hash = result.hash or _file_sha256(step_abs)
            else:
                result.validated = False
                if result.geometry_quality == "A":
                    result.geometry_quality = "C"
                result.requires_model_review = True

        return result

    def _resolve_result_path(self, path: str, query: PartQuery) -> Optional[str]:
        if not path:
            return None
        if path.startswith("cache://"):
            try:
                from adapters.parts.vendor_synthesizer import resolve_cache_path
                return str(resolve_cache_path(path[len("cache://"):]))
            except Exception:
                return None
        if os.path.isabs(path):
            return os.path.normpath(path)
        root = query.project_root or self.project_root
        return os.path.normpath(os.path.join(root, path))

    def _path_kind(self, original: str, absolute: Optional[str]) -> str:
        if not original:
            return ""
        if original.startswith("cache://"):
            return "shared_cache"
        if not os.path.isabs(original):
            return "project_relative"
        if absolute:
            try:
                Path(absolute).relative_to(Path(self.project_root).resolve())
                return "project_absolute"
            except ValueError:
                pass
        return "absolute"

    def _record_decision(
        self,
        query: PartQuery,
        result: ResolveResult,
        attempted_adapters: list[str],
    ) -> None:
        decision = result.to_geometry_decision(query, attempted_adapters)
        if not decision.adapter:
            decision.adapter = "(none)"
        self._decision_log.append(decision)

    # ---- introspection ----------------------------------------------------

    def summary(self) -> dict:
        """Return a dict of adapter → count of decisions made this session."""
        counts: dict = {}
        for decision in self._decision_log:
            adapter = _decision_adapter(decision)
            counts[adapter] = counts.get(adapter, 0) + 1
        return counts

    def decisions_by_adapter(self) -> dict:
        """Return adapter → list of (part_no, source_tag) tuples.

        This is the low-level execution view: it keeps the adapter that
        actually produced each result. The coverage report may group rows by a
        higher-level geometry source such as parametric_template.
        """
        result: dict = {}
        for decision in self._decision_log:
            part_no = _decision_part_no(decision)
            adapter = _decision_adapter(decision)
            source_tag = _decision_source_tag(decision)
            result.setdefault(adapter, []).append((part_no, source_tag))
        return result

    def geometry_decisions(self) -> list[dict]:
        """Return durable geometry routing decisions as JSON-ready dicts."""
        rows: list[dict] = []
        for decision in self._decision_log:
            if isinstance(decision, GeometryDecision):
                rows.append(decision.to_dict())
                continue
            part_no, adapter, source_tag = decision
            rows.append({
                "part_no": part_no,
                "name_cn": "",
                "status": "hit" if adapter != "(none)" else "miss",
                "kind": "codegen",
                "adapter": adapter,
                "source_tag": source_tag,
                "geometry_source": "",
                "geometry_quality": "",
                "validated": False,
                "hash": None,
                "path_kind": "",
                "requires_model_review": adapter == "jinja_primitive",
                "step_path": None,
                "real_dims": None,
                "attempted_adapters": [],
                "config_match": "n/a",
                "category": "",
                "warnings": [],
                "metadata": {},
            })
        return rows

    def coverage_report(self, max_examples_per_adapter: int = 5) -> str:
        """Render a multi-line coverage report for end-of-build display.

        Format::

            resolver coverage:
              step_pool        2  GIS-EE-001-05, GIS-EE-001-06
              bd_warehouse     1  GIS-EE-002-11
              parametric_template 5 GIS-EE-001-03, GIS-EE-001-04
              jinja_primitive 26  GIS-EE-001-08, GIS-EE-001-09 ... (and 22 more)
              ─────────────────────────────────────
              Total: 34 parts | Ready geometry: 8 (23.5%) | Fallback: 26 (76.5%)

              26 parts need model review or geometry upgrade. To upgrade them:
              add a STEP file under std_parts/, write a parts_library.yaml rule, or set
              `extends: default` to inherit category-driven routing.
              See docs/PARTS_LIBRARY.md for the mapping vocabulary.

        The report is intentionally plain ASCII (no Unicode tables) so it
        renders correctly on every CI runner including Windows GBK consoles.
        Returns an empty string if no decisions have been recorded yet.
        """
        rows = self.geometry_decisions()
        if not rows:
            return ""

        total = len(rows)
        fallback_count = sum(1 for row in rows if _row_requires_fallback_review(row))
        ready_count = total - fallback_count

        decisions: dict[str, list[tuple[str, str]]] = {}
        for row in rows:
            adapter = _coverage_bucket(row)
            decisions.setdefault(adapter, []).append((
                row.get("part_no", ""),
                row.get("source_tag", ""),
            ))

        # Order coverage buckets: library backends first, raw jinja last.
        ordered = sorted(
            decisions.keys(),
            key=_coverage_sort_key,
        )

        lines = ["resolver coverage:"]
        name_width = max(len(a) for a in ordered)
        for adapter in ordered:
            parts = decisions[adapter]
            count = len(parts)
            shown = [p for p, _ in parts[:max_examples_per_adapter]]
            extra = count - len(shown)
            examples = ", ".join(shown)
            if extra > 0:
                examples += f" ... (and {extra} more)"
            lines.append(
                f"  {adapter:<{name_width}}  {count:>3}  {examples}"
            )

        # Aggregate row
        lines.append("  " + "─" * (name_width + 50))
        if total > 0:
            ready_pct = 100.0 * ready_count / total
            fb_pct = 100.0 * fallback_count / total
        else:
            ready_pct = fb_pct = 0.0
        lines.append(
            f"  Total: {total} parts | Ready geometry: {ready_count} "
            f"({ready_pct:.1f}%) | Fallback: {fallback_count} ({fb_pct:.1f}%)"
        )

        # Hint footer (only when fallback is non-trivial)
        if fallback_count > 0:
            lines.append("")
            lines.append(
                f"  {fallback_count} parts need model review or geometry "
                f"upgrade. To upgrade"
            )
            lines.append(
                "  them: add a STEP file under std_parts/, write a"
            )
            lines.append(
                "  parts_library.yaml rule, or set"
            )
            lines.append(
                "  `extends: default` to inherit category-driven routing."
            )
            lines.append(
                "  See docs/PARTS_LIBRARY.md for the mapping vocabulary."
            )

        return "\n".join(lines)

    def resolve_report(
        self,
        bom_rows: list[dict],
        run_id: str = "",
        allow_inspect_fallback: bool = True,
    ) -> "ResolveReport":
        """Output per-row routing from recorded decisions.

        Report generation should not trigger codegen/export side effects. When
        called before any resolve() decisions exist, `allow_inspect_fallback`
        preserves the standalone API by resolving in read-only inspect mode.
        Codegen callers pass False so reports mirror the decisions already made
        during generation.
        """
        adapter_availability: dict[str, tuple[bool, str | None]] = {
            a.name: a.is_available() for a in self.adapters
        }

        report = ResolveReport(run_id=run_id, total_rows=len(bom_rows))

        for name, (ok, reason) in adapter_availability.items():
            report.adapter_hits[name] = AdapterHit(
                count=0,
                unavailable_reason=None if ok else reason,
            )

        decisions_by_part: dict[str, list] = {}
        for decision in self._decision_log:
            decisions_by_part.setdefault(_decision_part_no(decision), []).append(decision)

        for row in bom_rows:
            part_no = row.get("part_no", "")
            name_cn = row.get("name_cn", "")
            decision = None
            if decisions_by_part.get(part_no):
                decision = decisions_by_part[part_no].pop(0)
            elif allow_inspect_fallback:
                query = PartQuery(
                    part_no=part_no,
                    name_cn=name_cn,
                    material=row.get("material", ""),
                    category=row.get("category", ""),
                    make_buy=row.get("make_buy", ""),
                    project_root=self.project_root,
                )
                before_len = len(self._decision_log)
                result = self.resolve(query, mode="inspect")
                if len(self._decision_log) > before_len:
                    decision = self._decision_log[-1]
                else:
                    decision = result.to_geometry_decision(query, [])
            else:
                decision = _synthetic_report_decision(row)

            report_row = _report_row_from_decision(decision, part_no, name_cn)
            matched = report_row.matched_adapter
            if matched in report.adapter_hits:
                report.adapter_hits[matched].count += 1
            else:
                report.adapter_hits[matched] = AdapterHit(
                    count=1,
                    unavailable_reason=None,
                )
            report.rows.append(report_row)

        return report

    def _find_adapter(self, name: str):
        for a in self.adapters:
            if a.name == name:
                return a
        return None


# ─── Match semantics ──────────────────────────────────────────────────────


def _match_rule(match: dict, query: PartQuery) -> bool:
    """Evaluate a mapping rule's `match:` dict against the query.

    Conditions are AND'd within a rule. Supported keys:
      - any: true                   (unconditional)
      - part_no: "EXACT"            (case-sensitive equality)
      - part_no_glob: "PAT*"        (fnmatch-style)
      - category: "bearing"         (classify_part output)
      - name_contains: [...]        (substring match on name_cn, case-insensitive)
      - material_contains: [...]    (substring match on material)
      - keyword_contains: [...]     (substring match on EITHER name_cn OR material;
                                     useful for vendor part lookups where the
                                     model name may appear in either column)
      - make_buy: "外购"            (substring)
    """
    if not match:
        return False

    if match.get("any") is True:
        return True

    if "part_no" in match:
        if match["part_no"] != query.part_no:
            return False

    if "part_no_glob" in match:
        if not fnmatch.fnmatchcase(query.part_no, match["part_no_glob"]):
            return False

    if "category" in match:
        if match["category"] != query.category:
            return False

    if "name_contains" in match:
        name_lower = query.name_cn.lower()
        keywords = match["name_contains"]
        if isinstance(keywords, str):
            keywords = [keywords]
        if not any(kw.lower() in name_lower for kw in keywords):
            return False

    if "material_contains" in match:
        mat_lower = query.material.lower()
        keywords = match["material_contains"]
        if isinstance(keywords, str):
            keywords = [keywords]
        if not any(kw.lower() in mat_lower for kw in keywords):
            return False

    if "keyword_contains" in match:
        name_lower = query.name_cn.lower()
        mat_lower = query.material.lower()
        keywords = match["keyword_contains"]
        if isinstance(keywords, str):
            keywords = [keywords]
        if not any(
            kw.lower() in name_lower or kw.lower() in mat_lower
            for kw in keywords
        ):
            return False

    if "make_buy" in match:
        if match["make_buy"] not in query.make_buy:
            return False

    return True


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _quality_grade(value: Any) -> str:
    return str(value or "").strip().upper()


def _result_requires_fallback_review(result: ResolveResult) -> bool:
    return bool(result.requires_model_review) or (
        _quality_grade(result.geometry_quality) in {"C", "D", "E"}
    )


def _row_requires_fallback_review(row: dict) -> bool:
    return bool(row.get("requires_model_review")) or (
        _quality_grade(row.get("geometry_quality")) in {"C", "D", "E"}
    )


def _coverage_bucket(row: dict) -> str:
    geometry_source = str(row.get("geometry_source") or "").strip().upper()
    if geometry_source == "PARAMETRIC_TEMPLATE":
        return "parametric_template"
    return row.get("adapter") or "(none)"


def _coverage_sort_key(bucket: str) -> tuple[int, str]:
    order = {
        "sw_toolbox": 0,
        "step_pool": 1,
        "bd_warehouse": 2,
        "partcad": 3,
        "parametric_template": 4,
        "jinja_primitive": 9,
        "(skip)": 10,
        "(none)": 11,
    }
    return (order.get(bucket, 5), bucket)


def _decision_part_no(decision) -> str:
    if isinstance(decision, GeometryDecision):
        return decision.part_no
    return decision[0]


def _decision_adapter(decision) -> str:
    if isinstance(decision, GeometryDecision):
        return decision.adapter or "(none)"
    return decision[1] or "(none)"


def _decision_source_tag(decision) -> str:
    if isinstance(decision, GeometryDecision):
        return decision.source_tag
    return decision[2]


def _report_row_from_decision(
    decision,
    part_no: str,
    name_cn: str,
) -> ResolveReportRow:
    if isinstance(decision, GeometryDecision):
        status = decision.status
        if status == "miss":
            matched = "(none)"
        elif status == "skip":
            matched = "(skip)"
        elif status == "fallback":
            matched = "jinja_primitive"
        else:
            matched = decision.adapter or "(none)"
        return ResolveReportRow(
            bom_id=part_no or decision.part_no,
            name_cn=name_cn or decision.name_cn,
            matched_adapter=matched,
            attempted_adapters=list(decision.attempted_adapters or []),
            status=status if status in {"hit", "fallback", "miss", "skip"} else "miss",
            config_match=decision.config_match or "n/a",
        )

    legacy_part_no, adapter, _source_tag = decision
    matched = adapter or "(none)"
    status = "fallback" if matched == "jinja_primitive" else "hit"
    return ResolveReportRow(
        bom_id=part_no or legacy_part_no,
        name_cn=name_cn,
        matched_adapter=matched,
        attempted_adapters=[],
        status=status,
        config_match="n/a",
    )


def _synthetic_report_decision(row: dict) -> GeometryDecision:
    category = row.get("category", "")
    if category in {"fastener", "cable"}:
        return GeometryDecision(
            part_no=row.get("part_no", ""),
            name_cn=row.get("name_cn", ""),
            status="skip",
            kind="miss",
            adapter="(skip)",
            source_tag=f"{category} category: no geometry generated",
            geometry_source="MISSING",
            geometry_quality="E",
            requires_model_review=True,
            category=category,
        )
    return GeometryDecision(
        part_no=row.get("part_no", ""),
        name_cn=row.get("name_cn", ""),
        status="miss",
        kind="miss",
        adapter="(none)",
        geometry_source="MISSING",
        geometry_quality="E",
        requires_model_review=True,
        category=category,
    )


# ─── Category inference (Task 7) ──────────────────────────────────────────


# 优先级 1：rule["match"]["category"] 显式分类关键字 → 标准件 6 细分
# Task 7 只覆盖现有 yaml 已用的 fastener / bearing；其余 4 档（seal/locating/
# elastic/transmission）等 Task 8 在 yaml 里补规则后自然生效（dict 里已登记）。
_MATCH_CATEGORY_TO_PART: dict[str, PartCategory] = {
    "fastener": PartCategory.STANDARD_FASTENER,
    "bearing": PartCategory.STANDARD_BEARING,
    "seal": PartCategory.STANDARD_SEAL,
    "locating": PartCategory.STANDARD_LOCATING,
    "elastic": PartCategory.STANDARD_ELASTIC,
    "transmission": PartCategory.STANDARD_TRANSMISSION,
}

# 优先级 2：仅由 adapter 名字直接决定（不需看 spec）
# jinja_primitive 永远是 CUSTOM（参数化原语兜底）
_ADAPTER_NAME_TO_PART: dict[str, PartCategory] = {
    "jinja_primitive": PartCategory.CUSTOM,
}


def _infer_category(rule: dict, adapter) -> PartCategory:
    """推断命中规则的 PartCategory（Task 7）。

    优先级（从高到低）：
      1. rule["match"]["category"] 直接关键字映射 → 6 个 STANDARD_* 之一
      2. adapter.name == "step_pool" 且 rule["spec"] 含 "synthesizer"
         → VENDOR_PURCHASED（skill-shipped vendor STEP 合成件）
      3. adapter.name 直接映射（当前仅 jinja_primitive → CUSTOM）
      4. 兜底：CUSTOM
    """
    match = rule.get("match", {}) or {}
    match_category = match.get("category")
    if isinstance(match_category, str):
        mapped = _MATCH_CATEGORY_TO_PART.get(match_category)
        if mapped is not None:
            return mapped

    adapter_name = getattr(adapter, "name", "") or ""
    if adapter_name == "step_pool":
        spec = rule.get("spec", {}) or {}
        if "synthesizer" in spec:
            return PartCategory.VENDOR_PURCHASED

    direct = _ADAPTER_NAME_TO_PART.get(adapter_name)
    if direct is not None:
        return direct

    return PartCategory.CUSTOM


# ─── Registry loading ─────────────────────────────────────────────────────


def load_registry(
    project_root: str = "",
    explicit_path: Optional[str] = None,
    logger: Optional[Callable[[str], None]] = None,
) -> dict:
    """Load parts_library.yaml from the standard search path.

    Search order for the **project** registry (first hit wins):
      1. `explicit_path` argument (from --parts-library CLI flag)
      2. $CAD_PARTS_LIBRARY environment variable
      3. <project_root>/parts_library.yaml
      4. <skill_root>/parts_library.default.yaml (no project file → use default directly)
      5. empty dict (resolver becomes no-op)

    **Inheritance via `extends: default`** (since v2.8.1):
    A project registry that sets `extends: default` at the top level inherits
    the skill-shipped `parts_library.default.yaml`. The merge semantics are:

      - Project `mappings:` is **prepended** to default `mappings:` so project
        rules win first-hit-wins, with default rules acting as a fallback for
        anything the project doesn't explicitly cover.
      - Project top-level keys (`step_pool`, `bd_warehouse`, `partcad`,
        `version`) **override** default top-level keys shallowly.

    This is the recommended pattern: project YAML stays sparse, listing only
    the project-specific overrides, and inherits the default category-driven
    routing for everything else.

    Returns the parsed YAML dict, or {} if no file is found or YAML cannot
    be imported. Never raises on missing file.

    The kill switch `CAD_PARTS_LIBRARY_DISABLE=1` forces an empty registry.
    """
    log = logger or (lambda msg: None)

    if os.environ.get("CAD_PARTS_LIBRARY_DISABLE") == "1":
        log("  [resolver] CAD_PARTS_LIBRARY_DISABLE=1 → empty registry")
        return {}

    try:
        import yaml  # type: ignore
    except ImportError:
        log("  [resolver] PyYAML not installed → empty registry")
        return {}

    skill_root = str(Path(__file__).parent)
    default_path = os.path.join(skill_root, "parts_library.default.yaml")

    # Find the project registry (steps 1–3 above). Default is loaded
    # separately as the inheritance base.
    project_path = None
    if explicit_path and os.path.isfile(explicit_path):
        project_path = explicit_path
    elif os.environ.get("CAD_PARTS_LIBRARY"):
        env_path = os.environ["CAD_PARTS_LIBRARY"]
        if os.path.isfile(env_path):
            project_path = env_path
    elif project_root:
        candidate = os.path.join(project_root, "parts_library.yaml")
        if os.path.isfile(candidate):
            project_path = candidate

    def _load_yaml(path: str) -> Optional[dict]:
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            log(f"  [resolver] failed to parse {path}: {e}")
            return None

    # No project registry → fall back to default registry directly
    if project_path is None:
        if os.path.isfile(default_path):
            data = _load_yaml(default_path)
            if data is not None:
                log(f"  [resolver] loaded default registry from {default_path}")
                return data
        log("  [resolver] no parts_library.yaml found → empty registry")
        return {}

    project_data = _load_yaml(project_path)
    if project_data is None:
        return {}

    # Resolve `extends: default` inheritance
    extends = project_data.get("extends")
    if extends == "default":
        if not os.path.isfile(default_path):
            log(f"  [resolver] {project_path} extends default, but "
                f"{default_path} is missing — using project only")
            log(f"  [resolver] loaded registry from {project_path}")
            return project_data

        default_data = _load_yaml(default_path)
        if default_data is None:
            log("  [resolver] failed to load default registry; using project only")
            log(f"  [resolver] loaded registry from {project_path}")
            return project_data

        merged = _merge_registry(default_data, project_data)
        log(f"  [resolver] loaded registry from {project_path} (extends default)")
        return merged

    if extends is not None:
        log(f"  [resolver] unknown extends value {extends!r} in {project_path} "
            f"— ignoring (valid values: 'default')")

    log(f"  [resolver] loaded registry from {project_path}")
    return project_data


def _merge_registry(base: dict, overlay: dict) -> dict:
    """Merge an `extends: default` overlay onto its base registry.

    Semantics:
      - Top-level keys in `overlay` override `base` shallowly (e.g.
        `step_pool`, `bd_warehouse`, `partcad`, `version` are replaced).
      - `mappings` is special: overlay's mappings are **prepended** to base's
        mappings so overlay rules win first-hit-wins, with base rules acting
        as a fallback for anything overlay doesn't cover.
      - The synthetic `extends` key itself is dropped from the result so the
        merged registry is a normal flat dict.

    Note: this is intentionally NOT a deep merge. Deep-merging YAML configs
    is a footgun (silent surprises with list-vs-dict semantics); shallow
    override + mapping prepend is the model that maps cleanly to user intent.
    """
    merged = dict(base)  # shallow copy of base

    # Top-level keys: overlay wins
    for key, value in overlay.items():
        if key in ("extends", "mappings"):
            continue
        merged[key] = value

    # mappings: overlay first, then base
    overlay_mappings = list(overlay.get("mappings", []) or [])
    base_mappings = list(base.get("mappings", []) or [])
    merged["mappings"] = overlay_mappings + base_mappings

    return merged


# ─── Default factory ──────────────────────────────────────────────────────


def default_resolver(
    project_root: str = "",
    registry_path: Optional[str] = None,
    logger: Optional[Callable[[str], None]] = None,
) -> PartsResolver:
    """Build a PartsResolver with the standard adapter set.

    Adapters are instantiated unconditionally (they self-report availability
    via `is_available()`; unavailable adapters are simply never matched).

    Order of registration matters for adapter lookup by name but NOT for
    dispatch — dispatch order is driven by the YAML `mappings:` list.
    """
    registry = load_registry(project_root, registry_path, logger)
    resolver = PartsResolver(
        project_root=project_root,
        registry=registry,
        logger=logger,
    )

    # Lazy import to avoid circular deps during package initialization
    try:
        from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
        resolver.register_adapter(JinjaPrimitiveAdapter())
    except ImportError as e:
        if logger:
            logger(f"  [resolver] JinjaPrimitiveAdapter unavailable: {e}")

    try:
        from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter
        resolver.register_adapter(BdWarehouseAdapter(project_root=project_root))
    except ImportError as e:
        if logger:
            logger(f"  [resolver] BdWarehouseAdapter unavailable: {e}")

    # Phase SW-B Part 2a — SwToolboxAdapter (opt-in via yaml config +
    # runtime is_available() self-report)
    try:
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        resolver.register_adapter(SwToolboxAdapter(
            project_root=project_root,
            config=registry.get("solidworks_toolbox", {}),
        ))
    except ImportError as e:
        if logger:
            logger(f"  [resolver] SwToolboxAdapter unavailable: {e}")
    except RuntimeError as e:
        # validate_size_patterns 拒绝恶意 yaml → 不注册但管道继续
        if logger:
            logger(f"  [resolver] SwToolboxAdapter config rejected: {e}")

    # Phase B — StepPoolAdapter (not yet implemented)
    try:
        from adapters.parts.step_pool_adapter import StepPoolAdapter
        resolver.register_adapter(StepPoolAdapter(
            project_root=project_root,
            config=registry.get("step_pool", {}),
        ))
    except ImportError:
        pass

    # Phase C — PartCADAdapter (opt-in)
    if registry.get("partcad", {}).get("enabled"):
        try:
            from adapters.parts.partcad_adapter import PartCADAdapter
            resolver.register_adapter(PartCADAdapter(
                config=registry.get("partcad", {}),
            ))
        except ImportError:
            pass

    return resolver


# ─── CadQuery ↔ build123d conversion helper ───────────────────────────────


def bd_to_cq(bd_part: Any):
    """Convert a build123d Part object to a CadQuery Workplane.

    bd_warehouse returns build123d Part objects. build123d stores the OCCT
    solid in the `.wrapped` attribute (a TopoDS_Compound or TopoDS_Solid).
    CadQuery can wrap it via cq.Workplane("XY").newObject([cq.Solid(...)]).

    Centralized here so adapter updates stay in one place.
    """
    import cadquery as cq

    wrapped = getattr(bd_part, "wrapped", None)
    if wrapped is None:
        raise ValueError(
            f"bd_to_cq: input has no .wrapped attribute (got {type(bd_part)})"
        )

    # build123d exposes .part.wrapped on compound-like objects; unwrap once
    # more if needed
    inner = getattr(wrapped, "wrapped", wrapped)

    try:
        solid = cq.Solid(inner)
        return cq.Workplane("XY").newObject([solid])
    except Exception:
        # Fallback: treat as compound
        shape = cq.Shape(inner)
        return cq.Workplane("XY").newObject([shape])
