#!/usr/bin/env python3
"""
CAD Spec Generator — Auto-generate structured CAD spec documents from design docs.

Usage:
    python cad_spec_gen.py design_doc.md --config config/gisbot.json
    python cad_spec_gen.py design_doc.md --config config/gisbot.json --force
    python cad_spec_gen.py --all --config config/gisbot.json --doc-dir docs/design
"""

import argparse
import glob
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure script dir on sys.path for sibling imports
_SCRIPT_DIR = str(Path(__file__).parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from cad_spec_extractors import (
    extract_params, extract_tolerances, extract_fasteners, extract_bom,
    extract_connection_matrix, extract_assembly_pose, extract_visual_ids,
    extract_render_plan,
)
from cad_spec_defaults import (
    fill_fastener_defaults, fill_surface_defaults,
    compute_derived, check_completeness,
)

# ─── Configuration loading ───────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """Load subsystem map and paths from a JSON config file.

    Expected JSON structure:
    {
        "subsystems": { "04": {"name": "...", "prefix": "...", "cad_dir": "...", "aliases": [...]}, ... },
        "doc_dir": "docs/design",
        "output_dir": "./output"
    }
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ─── Default in-memory config (empty — requires --config) ────────────────

SUBSYSTEM_MAP = {}


def detect_chapter(filepath: str) -> str:
    """Detect chapter number from filename (NN-*.md)."""
    fname = Path(filepath).stem
    m = re.match(r"(\d{2})-", fname)
    if m:
        return m.group(1)
    return ""


# ─── Markdown output ─────────────────────────────────────────────────────

def _md_table(columns: list, rows: list) -> str:
    """Generate a Markdown table string."""
    if not rows:
        return f"| {' | '.join(columns)} |\n| {' | '.join(['---'] * len(columns))} |\n| {'（暂无数据） |' + ' |' * (len(columns) - 1)}\n"
    lines = []
    lines.append(f"| {' | '.join(columns)} |")
    lines.append(f"| {' | '.join(['---'] * len(columns))} |")
    for row in rows:
        # Pad row to column count
        padded = list(row) + [""] * (len(columns) - len(row))
        lines.append(f"| {' | '.join(str(c) for c in padded[:len(columns)])} |")
    return "\n".join(lines) + "\n"


def render_spec(chapter: str, filepath: str, md5: str, data: dict) -> str:
    """Render extracted data as a full CAD_SPEC.md Markdown document."""
    info = SUBSYSTEM_MAP.get(chapter, {"name": "未知", "prefix": "GIS-XX"})
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rel_path = Path(filepath).as_posix()

    sections = []

    # Header
    sections.append(f"# CAD Spec — {info['name']} ({info['prefix']})")
    sections.append(f"<!-- Generated: {now} | Source: {rel_path} | Hash: {md5} -->")
    sections.append("")

    # §1 全局参数表
    sections.append("## 1. 全局参数表")
    sections.append("")
    params = data.get("params", []) + data.get("derived", [])
    sections.append(_md_table(
        ["参数名", "值", "单位", "公差", "来源", "备注"],
        [[p["name"], p["value"], p["unit"], p["tol"], p["source"], p["remark"]]
         for p in params]
    ))

    # §2 公差与表面处理
    tols = data.get("tolerances", {})
    sections.append("## 2. 公差与表面处理")
    sections.append("")

    sections.append("### 2.1 尺寸公差")
    sections.append("")
    sections.append(_md_table(
        ["参数名", "标称值", "上偏差", "下偏差", "配合代号", "标注文本"],
        [[t["name"], t["nominal"], t["upper"], t["lower"], t["fit_code"], t["label"]]
         for t in tols.get("dim_tols", [])]
    ))

    sections.append("### 2.2 形位公差")
    sections.append("")
    sections.append(_md_table(
        ["符号", "值", "基准", "适用零件"],
        [[g["symbol"], g["value"], g["datum"], g["parts"]]
         for g in tols.get("gdt", [])]
    ))

    sections.append("### 2.3 表面处理")
    sections.append("")
    sections.append(_md_table(
        ["零件", "Ra(µm)", "处理方式", "material_type"],
        [[s["part"], s["ra"], s["process"], s["material_type"]]
         for s in tols.get("surfaces", [])]
    ))

    # §3 紧固件清单
    sections.append("## 3. 紧固件清单")
    sections.append("")
    fasteners = data.get("fasteners", [])
    sections.append(_md_table(
        ["连接位置", "螺栓规格", "数量", "力矩(Nm)", "材料等级", "备注"],
        [[f["location"], f["spec"], str(f["qty"]), f["torque"], f["grade"], f["remark"]]
         for f in fasteners]
    ))

    # §4 连接矩阵
    sections.append("## 4. 连接矩阵")
    sections.append("")
    connections = data.get("connections", [])
    sections.append(_md_table(
        ["零件A", "零件B", "连接类型", "配合代号", "预紧力矩", "装配顺序"],
        [[c["partA"], c["partB"], c["type"], c["fit"], c["torque"], str(c["order"])]
         for c in connections]
    ))

    # §5 BOM树
    sections.append("## 5. BOM树")
    sections.append("")
    bom = data.get("bom")
    if bom:
        sections.append(f"**编号规则**: {bom.get('encoding_rule', '—')}")
        sections.append("")
        bom_rows = []
        for assy in bom.get("assemblies", []):
            bom_rows.append([
                f"**{assy['part_no']}**", f"**{assy['name']}**",
                "—", "1", "总成", "—",
            ])
            for p in assy.get("parts", []):
                bom_rows.append([
                    p["part_no"], p["name"], p.get("material", ""),
                    str(p.get("qty", 1)), p.get("make_buy", ""),
                    f"{p.get('total_price', 0):.0f}元" if p.get("total_price") else "—",
                ])
        sections.append(_md_table(
            ["料号", "名称", "材质/型号", "数量", "自制/外购", "单价"],
            bom_rows,
        ))
        s = bom.get("summary", {})
        sections.append(
            f"> 合计: {s.get('total_parts', 0)}零件 / {s.get('assemblies', 0)}总成 / "
            f"{s.get('custom_parts', 0)}自制 / {s.get('purchased_parts', 0)}外购 / "
            f"¥{s.get('total_cost', 0):,.0f}"
        )
        sections.append("")
    else:
        sections.append("（未找到BOM表）\n")

    # §6 装配姿态与定位
    assembly = data.get("assembly", {})
    sections.append("## 6. 装配姿态与定位")
    sections.append("")

    sections.append("### 6.1 坐标系定义")
    sections.append("")
    sections.append(_md_table(
        ["术语", "定义", "等价表述"],
        [[c["term"], c["definition"], c["equivalent"]]
         for c in assembly.get("coord_sys", [])]
    ))

    sections.append("### 6.2 装配层叠")
    sections.append("")
    sections.append(_md_table(
        ["层级", "零件/模块", "固定/运动", "连接方式", "偏移(Z/R/θ)", "轴线方向"],
        [[l["level"], l["part"], l["fixed_moving"], l["connection"],
          l["offset"], l["axis_dir"]]
         for l in assembly.get("layers", [])]
    ))

    # §7 视觉标识
    sections.append("## 7. 视觉标识")
    sections.append("")
    visuals = data.get("visual_ids", [])
    sections.append(_md_table(
        ["零件", "材质", "表面颜色", "唯一标签", "外形尺寸", "方向约束"],
        [[v["part"], v["material"], v["color"], v["label"], v["size"], v["direction"]]
         for v in visuals]
    ))

    # §8 渲染规划
    render = data.get("render_plan", {})
    sections.append("## 8. 渲染规划")
    sections.append("")

    sections.append("### 8.1 迭代分组")
    sections.append("")
    sections.append(_md_table(
        ["步骤", "添加内容", "画面位置", "prompt要点", "依赖步骤"],
        [[g["step"], g["content"], g["position"], g["prompt_key"], g["depends"]]
         for g in render.get("groups", [])]
    ))

    sections.append("### 8.2 视角")
    sections.append("")
    sections.append(_md_table(
        ["视角ID", "名称", "仰角/方位", "可见模块", "被遮挡模块", "重点"],
        [[v["id"], v["name"], v["angle"], v["visible"], v["hidden"], v["focus"]]
         for v in render.get("views", [])]
    ))

    sections.append("### 8.3 否定约束")
    sections.append("")
    sections.append(_md_table(
        ["约束ID", "约束描述", "原因"],
        [[c["id"], c["description"], c["reason"]]
         for c in render.get("constraints", [])]
    ))

    # §9 缺失数据报告
    sections.append("## 9. 缺失数据报告")
    sections.append("")
    issues = data.get("issues", [])
    if issues:
        sections.append(_md_table(
            ["编号", "章节", "缺失项", "严重度", "建议默认值", "说明"],
            [[i["id"], i["section"], i["missing"], i["severity"],
              i.get("default", "—"), i["suggestion"]]
             for i in issues]
        ))
    else:
        sections.append("全部数据完整，无缺失项。\n")

    return "\n".join(sections)


# ─── Main processing ─────────────────────────────────────────────────────

def process_doc(filepath: str, output_dir: str, force: bool = False) -> dict:
    """Process a single design document and generate CAD_SPEC.md."""
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Design document not found: {filepath}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    md5 = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

    # Detect chapter
    chapter = detect_chapter(str(path))
    if chapter not in SUBSYSTEM_MAP:
        raise ValueError(f"Unknown chapter: {path.name} (expected NN-*.md with chapter in config)")

    info = SUBSYSTEM_MAP[chapter]
    cad_dir = Path(output_dir) / info["cad_dir"]

    # Check idempotency: if CAD_SPEC.md exists with same hash, skip
    output_path = cad_dir / "CAD_SPEC.md"
    if not force and output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        if f"Hash: {md5}" in existing:
            return {
                "output_path": str(output_path),
                "skipped": True,
                "reason": "Source unchanged (same MD5)",
            }

    # ── Extract all data ──
    print(f"[CAD Spec] Extracting: {info['name']} ({chapter})")

    params = extract_params(lines)
    print(f"  §1 Params: {len(params)} items")

    tolerances = extract_tolerances(lines)
    dim_count = len(tolerances["dim_tols"])
    surf_count = len(tolerances["surfaces"])
    print(f"  §2 Tolerances: {dim_count} dim + {len(tolerances['gdt'])} GD&T + {surf_count} surface")

    fasteners = extract_fasteners(lines)
    fasteners = fill_fastener_defaults(fasteners)
    print(f"  §3 Fasteners: {len(fasteners)} items")

    bom = extract_bom(str(path))
    if bom:
        print(f"  §5 BOM: {bom['summary']['total_parts']} parts / ¥{bom['summary']['total_cost']:,.0f}")
    else:
        print(f"  §5 BOM: not found")

    assembly = extract_assembly_pose(lines)
    print(f"  §6 Assembly: {len(assembly['coord_sys'])} coord + {len(assembly['layers'])} layers")

    visual_ids = extract_visual_ids(lines, bom)
    print(f"  §7 Visual: {len(visual_ids)} parts")

    render_plan = extract_render_plan(lines)
    g_count = len(render_plan["groups"])
    v_count = len(render_plan["views"])
    c_count = len(render_plan["constraints"])
    print(f"  §8 Render: {g_count} groups + {v_count} views + {c_count} constraints")

    # Connections (synthesized from fasteners + layers)
    connections = extract_connection_matrix(lines, fasteners, assembly.get("layers", []))
    print(f"  §4 Connections: {len(connections)} items")

    # Fill surface defaults
    tolerances["surfaces"] = fill_surface_defaults(tolerances["surfaces"])

    # Aggregate all data
    data = {
        "params": params,
        "tolerances": tolerances,
        "fasteners": fasteners,
        "bom": bom,
        "connections": connections,
        "assembly": assembly,
        "visual_ids": visual_ids,
        "render_plan": render_plan,
    }

    # Derived calculations
    derived = compute_derived(data)
    data["derived"] = derived
    print(f"  Derived: {len(derived)} items")

    # Completeness check
    issues = check_completeness(data)
    data["issues"] = issues
    critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
    warning = sum(1 for i in issues if i["severity"] == "WARNING")
    info_count = sum(1 for i in issues if i["severity"] == "INFO")
    print(f"  §9 Missing: {critical} CRITICAL / {warning} WARNING / {info_count} INFO")

    # Render markdown
    md_content = render_spec(chapter, str(path), md5, data)

    # Write output
    cad_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_content, encoding="utf-8")
    print(f"  → {output_path}")

    return {
        "output_path": str(output_path),
        "skipped": False,
        "params": len(params),
        "fasteners": len(fasteners),
        "bom_parts": bom["summary"]["total_parts"] if bom else 0,
        "connections": len(connections),
        "visual_ids": len(visual_ids),
        "issues_critical": critical,
        "issues_warning": warning,
        "issues_info": info_count,
    }


# ─── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate CAD_SPEC.md from design documents")
    parser.add_argument("files", nargs="*",
                        help="Design document paths (NN-*.md)")
    parser.add_argument("--config", required=True,
                        help="JSON config file with subsystem mapping (e.g. config/gisbot.json)")
    parser.add_argument("--output-dir", default="./output",
                        help="Output directory (default: ./output)")
    parser.add_argument("--doc-dir", default=None,
                        help="Design docs directory for --all (default: from config)")
    parser.add_argument("--all", action="store_true",
                        help="Process all subsystems found in doc-dir")
    parser.add_argument("--force", action="store_true",
                        help="Force regeneration (ignore MD5 idempotency check)")
    args = parser.parse_args()

    # Load config
    global SUBSYSTEM_MAP
    config = load_config(args.config)
    SUBSYSTEM_MAP = config.get("subsystems", {})

    if not SUBSYSTEM_MAP:
        print("Error: config has no 'subsystems' key or it is empty.", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or config.get("output_dir", "./output")
    doc_dir = args.doc_dir or config.get("doc_dir", "docs/design")

    if args.all:
        # Find all design docs
        design_dir = Path(doc_dir)
        files = sorted(design_dir.glob("??-*.md"))
    elif args.files:
        # Expand globs (Windows doesn't auto-expand)
        files = []
        for pattern in args.files:
            expanded = glob.glob(pattern)
            if expanded:
                files.extend(Path(f) for f in expanded)
            else:
                files.append(Path(pattern))
    else:
        parser.print_help()
        sys.exit(1)

    if not files:
        print("No design documents found.", file=sys.stderr)
        sys.exit(1)

    results = []
    for f in files:
        try:
            result = process_doc(str(f), output_dir, force=args.force)
            results.append(result)
        except Exception as e:
            print(f"[ERROR] {f.name}: {e}", file=sys.stderr)
            results.append({"output_path": str(f), "skipped": True, "reason": str(e)})

    # Summary
    print()
    print("=" * 60)
    processed = [r for r in results if not r.get("skipped")]
    skipped = [r for r in results if r.get("skipped")]
    print(f"Processed: {len(processed)} | Skipped: {len(skipped)} | Total: {len(results)}")
    for r in processed:
        c = r.get("issues_critical", 0)
        w = r.get("issues_warning", 0)
        tag = " ⚠ CRITICAL" if c > 0 else ""
        print(f"  {Path(r['output_path']).name}: "
              f"{r.get('params', 0)} params {r.get('bom_parts', 0)} parts "
              f"{r.get('fasteners', 0)} fasteners {c}C/{w}W{tag}")
    for r in skipped:
        print(f"  [Skipped] {Path(r['output_path']).name}: {r.get('reason', '')}")


if __name__ == "__main__":
    main()
