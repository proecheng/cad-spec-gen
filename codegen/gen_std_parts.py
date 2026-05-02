#!/usr/bin/env python3
"""
Code Generator: Standard/Purchased Parts → geometry source per parts_resolver.

Phase A+ refactor: this module no longer contains the `_gen_*` dispatch table.
Instead it delegates to `parts_resolver.PartsResolver`, which picks the right
adapter (bd_warehouse, STEP pool, PartCAD, or jinja_primitive fallback) based
on a project-local YAML registry (`parts_library.yaml`).

Public contract:
- `generate_std_part_files(spec_path, output_dir, mode)` returns 4-tuple
  `(generated, skipped, resolver, pending_records)`. The `pending_records` dict
  (subsystem → list of pending records) is populated by Task 15 when
  `sw_config_broker` raises `NeedsUserDecision` for ambiguous Toolbox configs;
  Task 16 atomically writes it to `<project>/.cad-spec-gen/sw_config_pending.json`.
- Generated `std_*.py` modules expose `make_std_*() -> cq.Workplane` with no args
- Without a `parts_library.yaml`, behavior is byte-identical to pre-refactor
  (JinjaPrimitiveAdapter is the terminal fallback and reproduces `_gen_*` verbatim)

Usage:
    python codegen/gen_std_parts.py cad/end_effector/CAD_SPEC.md
    python codegen/gen_std_parts.py cad/end_effector/CAD_SPEC.md --output-dir cad/end_effector
    CAD_PARTS_LIBRARY=my.yaml python codegen/gen_std_parts.py ...
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from adapters.solidworks.sw_config_broker import NeedsUserDecision
from bom_parser import classify_part
from codegen.gen_assembly import parse_envelopes
from codegen.gen_build import parse_bom_tree
from codegen.library_routing import build_library_part_query, is_library_routed_row
from parts_resolver import PartQuery, default_resolver

# Categories the pipeline never tries to generate geometry for.
# Kept here (not in the adapter) because this is the enter-point filter.
_SKIP_CATEGORIES = {"fastener", "cable"}


def _build_part_query(p: dict, category: str, env, project_root: str) -> PartQuery:
    """Build the resolver query shared by prewarm and generation loops."""
    return build_library_part_query(
        p,
        category=category,
        envelope=env,
        project_root=project_root,
    )


def _has_exact_step_pool_mapping(resolver, query: PartQuery) -> bool:
    """True when parts_library.yaml has an exact part_no STEP rule.

    User-provided STEP imports are written this way. They must be allowed
    through even for categories normally skipped by coarse codegen filters.
    """
    matching_rules = getattr(resolver, "matching_rules", None)
    if matching_rules is None:
        return False
    for rule in matching_rules(query, adapter_name="step_pool"):
        match = rule.get("match") or {}
        if isinstance(match, dict) and match.get("part_no") == query.part_no:
            return True
    return False


def _should_skip_category(category: str, resolver, query: PartQuery) -> bool:
    if category not in _SKIP_CATEGORIES:
        return False
    return not _has_exact_step_pool_mapping(resolver, query)


def _should_generate_std_row(part: dict, category: str, resolver, query: PartQuery) -> bool:
    if "外购" in part.get("make_buy", "") or "标准" in part.get("make_buy", ""):
        return True
    return is_library_routed_row(
        part,
        category=category,
        resolver=resolver,
        query=query,
    )


def _safe_module_name(part_no: str) -> str:
    """Part number → std module name.

    GIS-EE-001-05 → std_ee_001_05
    SLP-C01       → std_c01
    """
    from cad_spec_defaults import strip_part_prefix
    suffix = strip_part_prefix(part_no).lower().replace("-", "_")
    if suffix and suffix[0].isdigit():
        suffix = "p" + suffix
    return f"std_{suffix}"


def _envelope_to_spec_envelope(env):
    """Convert parse_envelopes() output entry to the PartQuery spec_envelope
    tuple.

    Input shape: {"dims": (w, d, h), "granularity": str}  (new dict form)
                 OR (w, d, h)                              (legacy bare tuple)
    Output: (w, d, h) or None
    """
    if env is None:
        return None
    dims = env.get("dims") if isinstance(env, dict) else env
    if dims is None:
        return None
    return dims


def _envelope_to_granularity(env) -> str:
    """Extract granularity from a parse_envelopes() entry.
    Backward-compat: bare tuples (legacy format) default to part_envelope.
    """
    if isinstance(env, dict):
        return env.get("granularity") or "part_envelope"
    return "part_envelope"


def _is_parametric_template_result(result) -> bool:
    return (
        result.kind == "codegen"
        and result.geometry_source == "PARAMETRIC_TEMPLATE"
        and result.geometry_quality in {"A", "B"}
    )


def _geometry_doc_lines(result) -> str:
    """Return module-docstring lines for resolver geometry metadata."""
    validated = "true" if result.validated else "false"
    requires_model_review = "true" if result.requires_model_review else "false"
    return "\n".join([
        f"Geometry source: {result.geometry_source or 'unknown'}",
        f"Geometry quality: {result.geometry_quality or 'unknown'}",
        f"Validated: {validated}",
        f"Hash: {result.hash or 'n/a'}",
        f"Path kind: {result.path_kind or 'n/a'}",
        f"Requires model review: {requires_model_review}",
    ])


def _project_root_import_block() -> str:
    return '''import os
import sys
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_here, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

'''


def _emit_module_source(part, mod_name: str, category: str, result) -> str:
    """Build the full Python module text for a std_*.py file.

    The contract is: whatever the `make_*()` function returns must be
    compatible with cq.Workplane (chainable .translate / .rotate / used in
    cq.Assembly.add()).

    Byte-identical regression guarantee: when result.adapter is
    "jinja_primitive" (the fallback case), emit the exact pre-refactor
    header format. This preserves byte equality with the legacy
    gen_std_parts.py output for projects without a parts_library.yaml.
    """
    parametric_template = _is_parametric_template_result(result)
    material = part.get("material") or "—"
    if result.adapter == "jinja_primitive" and not parametric_template:
        # Legacy header format — DO NOT CHANGE (byte-identical gate)
        dims = result.metadata.get("dims", {})
        header = f'''"""
{part["name_cn"]} ({part["part_no"]}) — 简化标准件几何

Auto-generated by codegen/gen_std_parts.py
Category: {category} | Make/Buy: 外购
Material: {material}
Dimensions: {dims}

NOTE: This is a simplified representation for visualization only.
      Not for manufacturing — actual part is purchased.
"""

import cadquery as cq
'''
    else:
        if result.kind == "step_import":
            title = "真实 STEP 导入件"
            note = (
                "NOTE: Imported from a STEP model selected by parts_resolver.\n"
                "      Verify upstream license and dimensional fit before manufacturing."
            )
        elif result.kind == "python_import":
            title = f"{result.adapter} 参数化库几何"
            note = (
                "NOTE: Generated from an external parts library via parts_resolver.\n"
                "      Verify dimensional fit before manufacturing."
            )
        elif parametric_template:
            title = "参数化模板几何"
            note = (
                "NOTE: Generated from a curated parametric template selected by parts_resolver.\n"
                "      This is not a vendor STEP model; verify dimensional fit before manufacturing."
            )
        else:
            title = "parts_resolver 几何"
            note = (
                "NOTE: Generated via parts_resolver.\n"
                "      Verify dimensional fit before manufacturing."
            )
        geometry_doc = _geometry_doc_lines(result)
        header = f'''"""
{part["name_cn"]} ({part["part_no"]}) — {title}

Auto-generated by codegen/gen_std_parts.py via parts_resolver
Category: {category} | Make/Buy: {part["make_buy"]}
Material: {material}
Source: {result.source_tag}
{geometry_doc}

{note}
"""

{_project_root_import_block()}import cadquery as cq
'''

    func_name = f"make_{mod_name}"

    if result.kind == "codegen":
        body = (result.body_code or "").replace("\r\n", "\n").replace("\r", "\n")
        geom_desc = (
            "parametric template geometry"
            if parametric_template
            else f"simplified {category} geometry"
        )
        func_block = f'''

def {func_name}() -> cq.Workplane:
    """{part["part_no"]}: {part["name_cn"]} — {geom_desc}."""
{body}
'''

    elif result.kind == "step_import":
        # Resolve the step path at IMPORT time. Project-relative paths
        # anchor on the generated module's location so the project stays
        # relocatable. Shared-cache paths use cache://vendor/model.step so
        # committed generated modules do not bake in a developer home path.
        _step_path = result.step_path or ""
        if _step_path.startswith("cache://"):
            cache_rel = _step_path[len("cache://"):]
            path_resolver_line = (
                f'    _cache_rel = {cache_rel!r}\n'
                '    _cache_root = os.environ.get("CAD_SPEC_GEN_STEP_CACHE")\n'
                '    if _cache_root:\n'
                '        _step_path = os.path.join(os.path.expanduser(_cache_root), _cache_rel)\n'
                '    else:\n'
                '        from pathlib import Path\n'
                '        _step_path = os.path.join(str(Path.home()), ".cad-spec-gen", "step_cache", _cache_rel)'
            )
        elif os.path.isabs(_step_path):
            path_resolver_line = f'    _step_path = {_step_path!r}'
        else:
            path_resolver_line = (
                f'    _step_path = os.path.join(_here, "..", "..", {_step_path!r})'
            )
        normalize_origin = (result.metadata or {}).get("normalize_origin")
        if normalize_origin == "center_xy_bottom_z":
            import_return = '''    _model = cq.importers.importStep(_step_path)
    _bbox = _model.val().BoundingBox()
    _origin_shift = (
        -(_bbox.xmin + _bbox.xmax) / 2.0,
        -(_bbox.ymin + _bbox.ymax) / 2.0,
        -_bbox.zmin,
    )
    return _model.translate(_origin_shift)'''
        else:
            import_return = "    return cq.importers.importStep(_step_path)"
        func_block = f'''

def {func_name}() -> cq.Workplane:
    """{part["part_no"]}: {part["name_cn"]} — imported from STEP file.

    Source: {result.source_tag}
    """
    import os
    _here = os.path.dirname(os.path.abspath(__file__))
{path_resolver_line}
    _step_path = os.path.normpath(_step_path)
    if not os.path.isfile(_step_path):
        raise FileNotFoundError(
            f"STEP file missing for {part["part_no"]}: {{_step_path}}")
{import_return}
'''

    elif result.kind == "python_import":
        # External library import goes inside the function, not at module
        # top, so the spec-gen machine doesn't need the optional dep
        # installed to IMPORT the generated file — only to EXECUTE it.
        #
        # Two sub-cases based on what the external call returns:
        #   1. bd_warehouse returns a build123d Part (has .wrapped) →
        #      need _bd_to_cq() conversion.
        #   2. PartCAD's get_part_cadquery() already returns a cq.Solid →
        #      just wrap it in a Workplane.
        #
        # The _bd_to_cq() helper is INLINED here (not imported from
        # parts_resolver) because the build subprocess runs from
        # cad/<subsystem>/ which is not on the skill's sys.path. Inlining
        # keeps generated files self-contained and relocatable.
        args_str = result.import_args

        if result.adapter == "partcad":
            func_block = f'''

def {func_name}() -> cq.Workplane:
    """{part["part_no"]}: {part["name_cn"]} — partcad package part.

    Source: {result.source_tag}
    """
    import partcad as pc
    _solid = pc.{result.import_symbol}({args_str})
    return cq.Workplane("XY").newObject([_solid])
'''
        else:
            # bd_warehouse (default) — returns build123d Part, convert
            func_block = f'''

def _bd_to_cq(bd_part):
    """Convert a build123d Part to a CadQuery Workplane (self-contained)."""
    wrapped = getattr(bd_part, "wrapped", None)
    if wrapped is None:
        raise ValueError(
            f"_bd_to_cq: input has no .wrapped attribute (got {{type(bd_part)}})")
    inner = getattr(wrapped, "wrapped", wrapped)
    try:
        return cq.Workplane("XY").newObject([cq.Solid(inner)])
    except Exception:
        return cq.Workplane("XY").newObject([cq.Shape(inner)])


def {func_name}() -> cq.Workplane:
    """{part["part_no"]}: {part["name_cn"]} — {result.adapter} part.

    Source: {result.source_tag}
    """
    from {result.import_module} import {result.import_symbol}
    _bd_part = {result.import_symbol}({args_str})
    return _bd_to_cq(_bd_part)
'''

    else:
        # Should never reach here; treat as error
        raise ValueError(
            f"Unknown ResolveResult.kind: {result.kind!r} for {part['part_no']}")

    footer = f'''

if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = {func_name}()
    p = os.path.join(out, "{part["part_no"]}_std.step")
    cq.exporters.export(r, p)
    print(f"Exported: {{p}}")
'''

    return header + func_block + footer


def generate_std_part_files(
    spec_path: str,
    output_dir: str,
    mode: str = "scaffold",
) -> tuple[list, list, "PartsResolver", dict[str, list[dict]]]:
    """Generate simplified CadQuery files for purchased standard parts.

    Args:
        spec_path: Path to CAD_SPEC.md
        output_dir: Where to write std_*.py files
        mode: "scaffold" (skip existing), "force" (overwrite existing)

    Returns (generated_files, skipped_files, resolver, pending_records).

    pending_records maps subsystem → list of records for parts where
    sw_config_broker raised NeedsUserDecision (ambiguous Toolbox config).
    Task 16 turns this into sw_config_pending.json + exit 7.
    """
    parts = parse_bom_tree(spec_path)
    envelopes = parse_envelopes(spec_path)

    # Build a resolver rooted at the project (spec's grandparent dir is
    # typically the project root, one level above cad/<subsystem>/)
    project_root = str(Path(spec_path).resolve().parent.parent.parent)
    resolver = default_resolver(project_root=project_root,
                                 logger=lambda m: print(m))

    generated = []
    skipped = []
    pending_records: dict[str, list[dict]] = {}

    # ─── Task 14.6：build 全 BOM PartQuery list + prewarm 触发 broker batch worker ───
    # 把现有 loop 内的 PartQuery build 提到 loop 之前，让 prewarm 拿到完整 query 列表
    # （adapter.prewarm 用 find_sldprt 收集 sldprt → broker.prewarm 1 次 batch spawn）
    queries_for_prewarm: list[PartQuery] = []
    for p in parts:
        if p["is_assembly"]:
            continue
        category = classify_part(p["name_cn"], p["material"])
        env = envelopes.get(p["part_no"])
        query = _build_part_query(p, category, env, project_root)
        if not _should_generate_std_row(p, category, resolver, query):
            continue
        if _should_skip_category(category, resolver, query):
            continue
        queries_for_prewarm.append(query)
    if queries_for_prewarm:
        try:
            resolver.prewarm(queries_for_prewarm)
        except Exception as e:
            print(f"[gen_std_parts] prewarm 跳过（{type(e).__name__}: {e}）")
    # ─── /Task 14.6 ───

    for p in parts:
        if p["is_assembly"]:
            continue

        category = classify_part(p["name_cn"], p["material"])

        # Build the query, priming spec_envelope from §6.4 when available
        env = envelopes.get(p["part_no"])
        query = _build_part_query(p, category, env, project_root)
        if not _should_generate_std_row(p, category, resolver, query):
            continue
        if _should_skip_category(category, resolver, query):
            continue

        try:
            result = resolver.resolve(query)
        except NeedsUserDecision as exc:
            # broker 在含糊匹配时抛此异常，携带 part_no / subsystem / pending_record。
            # 累积到 pending_records 等待 main 一次性原子写 sw_config_pending.json
            # （Task 16）。跳过该零件 std_*.py 生成，继续处理后续零件。
            pending_records.setdefault(exc.subsystem, []).append(exc.pending_record)
            print(
                f"[pending] {exc.subsystem}/{exc.part_no} 等待用户决策 "
                f"({exc.pending_record.get('match_failure_reason', 'unknown')})"
            )
            continue

        if result.status in {"miss", "skip"} or result.kind == "miss":
            # Nothing matched, not even the jinja fallback → skip silently.
            # This happens for parts the fallback doesn't know how to draw
            # (e.g. missing dims AND unknown category).
            # "skip" is an intentional no-geometry signal (e.g. cable/fastener
            # categories that reached the resolver without being pre-filtered).
            continue

        mod_name = _safe_module_name(p["part_no"])
        out_file = os.path.join(output_dir, f"{mod_name}.py")

        # Scaffold mode: don't overwrite existing files
        if os.path.exists(out_file) and mode != "force":
            skipped.append(out_file)
            continue

        content = _emit_module_source(p, mod_name, category, result)
        Path(out_file).write_text(content, encoding="utf-8", newline="\n")
        generated.append(out_file)

    # Print the resolver coverage report. The report tells the user, per
    # adapter, which specific parts were handled and gives an explicit
    # hint when many parts fell through to the simplified jinja fallback.
    # See PartsResolver.coverage_report() for the format.
    report = resolver.coverage_report()
    if report:
        for line in report.splitlines():
            print(f"[gen_std_parts] {line}")

    geometry_report_path = _write_geometry_report(resolver, output_dir)
    if geometry_report_path is not None:
        print(f"[gen_std_parts] 几何质量报告 → {geometry_report_path}")

    model_contract_path = _write_model_contract(resolver, output_dir, project_root)
    if model_contract_path is not None:
        print(f"[gen_std_parts] 模型契约 → {model_contract_path}")

    return generated, skipped, resolver, pending_records


def _write_geometry_report(resolver, output_dir: str) -> Path | None:
    """Write geometry_report.json from decisions already made by resolver."""
    if not hasattr(resolver, "geometry_decisions"):
        return None
    decisions = resolver.geometry_decisions()
    if not decisions:
        return None

    quality_counts: dict[str, int] = {}
    for decision in decisions:
        quality = decision.get("geometry_quality") or "unknown"
        quality_counts[quality] = quality_counts.get(quality, 0) + 1

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(decisions),
        "quality_counts": quality_counts,
        "decisions": decisions,
    }
    out_path = Path(output_dir) / ".cad-spec-gen" / "geometry_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, out_path)
    return out_path


def _write_model_contract(resolver, output_dir: str, project_root: str) -> Path | None:
    """Write MODEL_CONTRACT.json when PRODUCT_GRAPH.json is available."""
    if not hasattr(resolver, "geometry_decisions"):
        return None
    product_graph_path = Path(output_dir) / "PRODUCT_GRAPH.json"
    if not product_graph_path.exists():
        print(
            f"[gen_std_parts] MODEL_CONTRACT 跳过：未找到 {product_graph_path}"
        )
        return None
    from tools.model_contract import write_model_contract

    return write_model_contract(
        project_root,
        product_graph_path,
        resolver_decisions=resolver.geometry_decisions(),
        output=Path(output_dir) / ".cad-spec-gen" / "MODEL_CONTRACT.json",
    )


def _write_pending_file(
    pending_records: dict[str, list[dict]], path: Path
) -> None:
    """一次性原子写 sw_config_pending.json schema v2（spec §5.3 + §5.4）。

    封装 envelope 加 schema_version / generated_at / pending_count 字段，
    items_by_subsystem 嵌套原始 records；先写 .tmp 再 os.replace 保证
    并发读到的要么是旧文件要么是完整新文件，不出现部分写入。
    """
    total = sum(len(items) for items in pending_records.values())
    envelope = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pending_count": total,
        "items_by_subsystem": pending_records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(
        description="Generate CadQuery files for purchased standard parts "
                    "via unified parts_resolver")
    parser.add_argument("spec", help="Path to CAD_SPEC.md")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory (default: same dir as spec)")
    parser.add_argument("--mode", choices=["scaffold", "force"], default="scaffold",
                        help="scaffold=skip existing, force=overwrite")
    parser.add_argument("--parts-library", default=None,
                        help="Path to parts_library.yaml (overrides default search)")
    args = parser.parse_args()

    # ─── Task 30: sw_preflight 接入（strict=True — codegen 阶段 SW 异常必须卡） ───
    # 延迟 import：只在 main 调用时触发，保持模块顶部 import 面干净。
    from datetime import datetime
    from pathlib import Path as _Path
    from sw_preflight.preflight import run_preflight
    from sw_preflight.cache import read_cache
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    cache_path = _Path(f'./artifacts/{run_id}/sw_preflight_cache.json')
    preflight_result = None
    cached = read_cache(cache_path)
    if cached and cached.get('preflight_result', {}).get('passed'):
        print(f"[preflight] 复用 cache（TTL 内）: {cache_path}")
        # 简化：cache 命中直接跳过 — PreflightResult 反序列化留给 Task 34 按需补；
        # 走到 dry_run / emit_report 时 preflight_result=None 会进入 fallback 分支。
    else:
        # strict=False：当 SW Add-in 未就绪 / 一键修不可行时，打 [INFO] 预告
        # 后继续走降级路径（std parts 脚手架仍产出；STEP 缓存由 sw-warmup 独立阶段
        # 兜底）。硬门会让整个 codegen 阶段退出 2，连自制件也产不出来，与
        # 北极星"装即用 + 傻瓜式"相左。
        preflight_result = run_preflight(strict=False, run_id=run_id, entry='cad-codegen')
    # ─── /Task 30 ───

    if args.parts_library:
        os.environ["CAD_PARTS_LIBRARY"] = args.parts_library

    spec_path = os.path.abspath(args.spec)
    output_dir = args.output_dir or os.path.dirname(spec_path)
    os.makedirs(output_dir, exist_ok=True)

    generated, skipped, resolver, pending_records = generate_std_part_files(spec_path, output_dir, mode=args.mode)

    # ─── A3: resolve_report.json（必须在 emit_report 前完成，供 HTML routing 区块使用）───
    _rr = None
    try:
        import json as _json
        _bom_for_rr = parse_bom_tree(spec_path)
        # resolve_report 的 category 规则需要 category 字段：补充分类（镜像 generation loop）
        for _row in _bom_for_rr:
            if not _row.get("category"):
                _row["category"] = classify_part(_row["name_cn"], _row.get("material", ""))
        _rr = resolver.resolve_report(
            _bom_for_rr,
            run_id=run_id,
            allow_inspect_fallback=False,
        )
        _rr_path = Path(f"./artifacts/{run_id}/resolve_report.json")
        _rr_path.parent.mkdir(parents=True, exist_ok=True)
        _rr_path.write_text(
            _json.dumps(_rr.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        print(f"[gen_std_parts] 路由报告 → {_rr_path}")
    except Exception as _rr_exc:
        print(f"[gen_std_parts] resolve_report 生成跳过（{type(_rr_exc).__name__}: {_rr_exc}）")
    # ─── /A3 ───

    # ─── Task 30: dry_run BOM + emit_report（只读分析，不反向驱动 codegen） ───
    # 失败不阻 codegen 产物；三选一 prompt + user_choice 覆盖 router 留 Task 34 重评。
    try:
        from sw_preflight.dry_run import dry_run_bom
        from sw_preflight.report import emit_report
        _bom = parse_bom_tree(spec_path)  # 已在模块顶部 import（line 37）
        _dry = dry_run_bom(_bom)
        # 若 preflight_result 为 None（走了 cache 命中分支），构造最小 fallback 供 emit_report 使用
        if preflight_result is None:
            from sw_preflight.types import PreflightResult
            preflight_result = PreflightResult(
                passed=True, sw_info=None,
                fixes_applied=[], diagnosis=None, per_step_ms={},
            )
        _report_path = emit_report(_bom, _dry, preflight_result, _Path(f'./artifacts/{run_id}'),
                                   resolve_report=_rr)
        print(f"📋 SW 资产报告 → {_report_path}")
    except Exception as _e:
        # 任何 dry_run / emit_report 异常不阻 codegen 成功出产物
        print(f"[report] 生成跳过（{type(_e).__name__}: {_e}）")
    # ─── /Task 30 ───

    print(f"[gen_std_parts] Generated {len(generated)} standard part scaffold(s), "
          f"skipped {len(skipped)} existing")
    for f in generated:
        print(f"  + {os.path.basename(f)}")
    if skipped:
        print(f"  (skipped: {', '.join(os.path.basename(f) for f in skipped)})")

    # ─── Task 16：sw_config_pending.json 一次性原子写（含糊匹配 broker 累积） ───
    if pending_records:
        pending_path = (
            Path(os.environ.get("CAD_PROJECT_ROOT", os.getcwd()))
            / ".cad-spec-gen" / "sw_config_pending.json"
        )
        _write_pending_file(pending_records, pending_path)
        print(
            f"[pending] 已写 {sum(len(v) for v in pending_records.values())} "
            f"项到 {pending_path}（待用户决策；exit 7 在 Task 17 加）"
        )
    # ─── /Task 16 ───


if __name__ == "__main__":
    main()
