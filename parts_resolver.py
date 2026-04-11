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
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

__all__ = [
    "PartQuery",
    "ResolveResult",
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


@dataclass
class ResolveResult:
    """Output of PartsResolver.resolve().

    gen_std_parts.py inspects `kind` to decide what function body to emit:

        kind="codegen"        → body_code is a string (current behavior)
        kind="step_import"    → step_path, emit cq.importers.importStep(...)
        kind="python_import"  → import_module + import_symbol, emit lazy import
        kind="miss"           → nothing matched, caller should skip or fallback
    """

    status: Literal["hit", "miss", "fallback"]
    kind: ResolveKind
    adapter: str                            # which adapter produced this
    body_code: Optional[str] = None
    step_path: Optional[str] = None
    import_module: Optional[str] = None
    import_symbol: Optional[str] = None
    import_args: str = ""                   # literal args for the call
    real_dims: Optional[tuple] = None       # (w, d, h) mm from the library
    source_tag: str = ""                    # human-readable origin
    warnings: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # adapter-specific extras

    @classmethod
    def miss(cls) -> "ResolveResult":
        return cls(status="miss", kind="miss", adapter="")


# ─── Adapter protocol ─────────────────────────────────────────────────────
#
# The adapter base class lives in adapters/parts/base.py to keep this file
# small. We define the resolver loop here and import adapters lazily.


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
        self._decision_log: list = []  # (part_no, adapter, source_tag)

    # ---- adapter registration --------------------------------------------

    def register_adapter(self, adapter) -> None:
        """Register an adapter. Order matters: adapters are tried in order."""
        self.adapters.append(adapter)

    def available_adapter_names(self) -> list:
        return [a.name for a in self.adapters if a.is_available()]

    # ---- core resolve loop ------------------------------------------------

    def resolve(self, query: PartQuery) -> ResolveResult:
        """Match query against registry mappings, dispatch to the winning adapter.

        Algorithm:
          1. Walk `registry["mappings"]` top-to-bottom
          2. For each rule, check if its `match:` block satisfies the query
          3. If yes, find the adapter named in `rule["adapter"]` and call resolve()
          4. On hit, log the decision and return
          5. If no rule matches, fall through to the last-resort adapter
             (JinjaPrimitiveAdapter, which always answers with codegen kind)
        """
        for rule in self.registry.get("mappings", []):
            if not _match_rule(rule.get("match", {}), query):
                continue
            adapter_name = rule.get("adapter", "")
            adapter = self._find_adapter(adapter_name)
            if adapter is None:
                self.log(f"  [resolver] rule matches {query.part_no} but "
                         f"adapter '{adapter_name}' not available")
                continue
            spec = rule.get("spec", {})
            try:
                result = adapter.resolve(query, spec)
            except Exception as e:
                self.log(f"  [resolver] adapter '{adapter_name}' raised "
                         f"on {query.part_no}: {e} — falling through")
                continue
            if result.status == "hit":
                self._decision_log.append(
                    (query.part_no, adapter_name, result.source_tag))
                return result

        # Terminal fallback: jinja_primitive (guaranteed available)
        fallback = self._find_adapter("jinja_primitive")
        if fallback is not None:
            result = fallback.resolve(query, spec={})
            if result.status == "hit":
                result.status = "fallback"
                self._decision_log.append(
                    (query.part_no, "jinja_primitive", result.source_tag))
                return result

        return ResolveResult.miss()

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
            try:
                dims = adapter.probe_dims(query, rule.get("spec", {}))
            except Exception:
                dims = None
            if dims is not None:
                self._probe_cache[cache_key] = dims
                return dims

        self._probe_cache[cache_key] = None
        return None

    # ---- introspection ----------------------------------------------------

    def summary(self) -> dict:
        """Return a dict of adapter → count of decisions made this session."""
        counts: dict = {}
        for _, adapter, _ in self._decision_log:
            counts[adapter] = counts.get(adapter, 0) + 1
        return counts

    def decisions_by_adapter(self) -> dict:
        """Return adapter → list of (part_no, source_tag) tuples.

        Used by the coverage report to print which specific parts each
        adapter handled. Iteration order matches resolve() order.
        """
        result: dict = {}
        for part_no, adapter, source_tag in self._decision_log:
            result.setdefault(adapter, []).append((part_no, source_tag))
        return result

    def coverage_report(self, max_examples_per_adapter: int = 5) -> str:
        """Render a multi-line coverage report for end-of-build display.

        Format::

            resolver coverage:
              step_pool        2  GIS-EE-001-05, GIS-EE-001-06
              bd_warehouse     1  GIS-EE-002-11
              jinja_primitive 31  GIS-EE-001-03, GIS-EE-001-04 ... (and 27 more)
              ─────────────────────────────────────
              Total: 34 parts | Library hits: 3 (8.8%) | Fallback: 31 (91.2%)

              31 parts use simplified geometry. To upgrade them: add a STEP
              file under std_parts/, write a parts_library.yaml rule, or set
              `extends: default` to inherit category-driven routing.
              See docs/PARTS_LIBRARY.md for the mapping vocabulary.

        The report is intentionally plain ASCII (no Unicode tables) so it
        renders correctly on every CI runner including Windows GBK consoles.
        Returns an empty string if no decisions have been recorded yet.
        """
        decisions = self.decisions_by_adapter()
        if not decisions:
            return ""

        total = sum(len(v) for v in decisions.values())
        fallback_count = len(decisions.get("jinja_primitive", []))
        library_count = total - fallback_count

        # Order adapters: library backends first, jinja_primitive last
        ordered = sorted(
            decisions.keys(),
            key=lambda a: (a == "jinja_primitive", a),
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
            lib_pct = 100.0 * library_count / total
            fb_pct = 100.0 * fallback_count / total
        else:
            lib_pct = fb_pct = 0.0
        lines.append(
            f"  Total: {total} parts | Library hits: {library_count} "
            f"({lib_pct:.1f}%) | Fallback: {fallback_count} ({fb_pct:.1f}%)"
        )

        # Hint footer (only when fallback is non-trivial)
        if fallback_count > 0:
            lines.append("")
            lines.append(
                f"  {fallback_count} parts use simplified geometry. To upgrade "
                f"them: add a STEP file"
            )
            lines.append(
                "  under std_parts/, write a parts_library.yaml rule, or set"
            )
            lines.append(
                "  `extends: default` to inherit category-driven routing."
            )
            lines.append(
                "  See docs/PARTS_LIBRARY.md for the mapping vocabulary."
            )

        return "\n".join(lines)

    def _find_adapter(self, name: str):
        for a in self.adapters:
            if a.name == name:
                return a
        return None


# ─── Match semantics ──────────────────────────────────────────────────────


def _match_rule(match: dict, query: PartQuery) -> bool:
    """Evaluate a mapping rule's `match:` dict against the query.

    Conditions are AND'd within a rule. Supported keys:
      - any: true              (unconditional)
      - part_no: "EXACT"       (case-sensitive equality)
      - part_no_glob: "PAT*"   (fnmatch-style)
      - category: "bearing"    (classify_part output)
      - name_contains: [...]   (any substring match, case-insensitive)
      - material_contains: [...]
      - make_buy: "外购"       (substring)
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

    if "make_buy" in match:
        if match["make_buy"] not in query.make_buy:
            return False

    return True


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
            log(f"  [resolver] failed to load default registry; using project only")
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
