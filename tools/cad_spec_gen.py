#!/usr/bin/env python3
"""
CAD Spec 生成器 — 从设计文档自动生成规范化 CAD 数据文档

Usage:
    python tools/cad_spec_gen.py docs/design/04-末端执行机构设计.md
    python tools/cad_spec_gen.py docs/design/05-*.md --force
    python tools/cad_spec_gen.py --all
"""

import argparse
import glob
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure tools/ on sys.path for sibling imports
_TOOLS_DIR = str(Path(__file__).parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from cad_spec_extractors import (
    extract_params, extract_tolerances, extract_fasteners, extract_bom,
    extract_connection_matrix, extract_assembly_pose, extract_visual_ids,
    extract_render_plan,
)
from cad_spec_defaults import (
    fill_fastener_defaults, fill_surface_defaults,
    compute_derived, check_completeness,
)

# ─── 子系统映射 ──────────────────────────────────────────────────────────

SUBSYSTEM_MAP = {
    "01": {"name": "项目背景与需求分析", "prefix": "GIS-SYS", "cad_dir": "sys_req",
           "aliases": ["需求", "背景", "sys_req"]},
    "02": {"name": "系统总体方案", "prefix": "GIS-SYS", "cad_dir": "sys_arch",
           "aliases": ["总体", "架构", "sys_arch"]},
    "03": {"name": "机器人平台", "prefix": "GIS-RP", "cad_dir": "robot_platform",
           "aliases": ["平台", "底盘", "husky", "rp", "robot_platform"]},
    "04": {"name": "末端执行机构", "prefix": "GIS-EE", "cad_dir": "end_effector",
           "aliases": ["末端", "执行器", "ee", "end_effector"]},
    "05": {"name": "电气系统与信号调理", "prefix": "GIS-EL", "cad_dir": "electrical",
           "aliases": ["电气", "信号调理", "el", "electrical"]},
    "06": {"name": "导航定位与避障", "prefix": "GIS-NAV", "cad_dir": "navigation",
           "aliases": ["导航", "定位", "避障", "nav", "navigation"]},
    "07": {"name": "运动控制", "prefix": "GIS-MC", "cad_dir": "motion_ctrl",
           "aliases": ["运动", "控制", "mc", "motion"]},
    "08": {"name": "检测方法与信号处理", "prefix": "GIS-DET", "cad_dir": "detection",
           "aliases": ["检测", "信号处理", "det", "detection"]},
    "09": {"name": "电源与能量管理", "prefix": "GIS-PWR", "cad_dir": "power",
           "aliases": ["电源", "电池", "能量", "pwr", "power"]},
    "10": {"name": "智能充电站与边缘计算", "prefix": "GIS-CHG", "cad_dir": "charging",
           "aliases": ["充电", "边缘", "chg", "charging"]},
    "11": {"name": "耦合剂全流程管理", "prefix": "GIS-CPL", "cad_dir": "couplant",
           "aliases": ["耦合剂", "cpl", "couplant"]},
    "12": {"name": "通信架构", "prefix": "GIS-COM", "cad_dir": "communication",
           "aliases": ["通信", "com", "communication"]},
    "13": {"name": "软件系统", "prefix": "GIS-SW", "cad_dir": "software",
           "aliases": ["软件", "sw", "software"]},
    "14": {"name": "安全系统", "prefix": "GIS-SAF", "cad_dir": "safety",
           "aliases": ["安全", "saf", "safety"]},
    "15": {"name": "系统集成与验证", "prefix": "GIS-INT", "cad_dir": "integration",
           "aliases": ["集成", "验证", "int", "integration"]},
    "16": {"name": "采购与预算", "prefix": "GIS-BUD", "cad_dir": "budget",
           "aliases": ["采购", "预算", "bud", "budget"]},
    "17": {"name": "研发实施计划", "prefix": "GIS-PLN", "cad_dir": "plan",
           "aliases": ["计划", "实施", "pln", "plan"]},
    "18": {"name": "专利对照与附录", "prefix": "GIS-PAT", "cad_dir": "patent",
           "aliases": ["专利", "附录", "pat", "patent"]},
}


def detect_chapter(filepath: str) -> str:
    """从文件名或内容检测章节号。"""
    fname = Path(filepath).stem
    m = re.match(r"(\d{2})-", fname)
    if m:
        return m.group(1)
    return ""


# ─── Markdown 输出 ────────────────────────────────────────────────────────

def _md_table(columns: list, rows: list) -> str:
    """生成 Markdown 表格字符串。"""
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
    """将提取数据渲染为 CAD_SPEC.md 完整 Markdown。"""
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


# ─── 主流程 ──────────────────────────────────────────────────────────────

def process_doc(filepath: str, force: bool = False) -> dict:
    """处理单个设计文档，返回 {output_path, summary}。"""
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"设计文档不存在: {filepath}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    md5 = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

    # Detect chapter
    chapter = detect_chapter(str(path))
    if chapter not in SUBSYSTEM_MAP:
        raise ValueError(f"无法识别章节号: {path.name} (期望 NN-*.md 格式)")

    info = SUBSYSTEM_MAP[chapter]
    cad_dir = Path(__file__).resolve().parent.parent / "cad" / info["cad_dir"]

    # Check idempotency: if CAD_SPEC.md exists with same hash, skip
    output_path = cad_dir / "CAD_SPEC.md"
    if not force and output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        if f"Hash: {md5}" in existing:
            return {
                "output_path": str(output_path),
                "skipped": True,
                "reason": "源文档未变更 (MD5相同)",
            }

    # ── Extract all data ──
    print(f"[CAD Spec] 提取: {info['name']} ({chapter})")

    params = extract_params(lines)
    print(f"  §1 参数: {len(params)} 项")

    tolerances = extract_tolerances(lines)
    dim_count = len(tolerances["dim_tols"])
    surf_count = len(tolerances["surfaces"])
    print(f"  §2 公差: {dim_count}尺寸 + {len(tolerances['gdt'])}形位 + {surf_count}表面")

    fasteners = extract_fasteners(lines)
    fasteners = fill_fastener_defaults(fasteners)
    print(f"  §3 紧固件: {len(fasteners)} 项")

    bom = extract_bom(str(path))
    if bom:
        print(f"  §5 BOM: {bom['summary']['total_parts']}零件 / ¥{bom['summary']['total_cost']:,.0f}")
    else:
        print(f"  §5 BOM: 未找到")

    assembly = extract_assembly_pose(lines)
    print(f"  §6 装配: {len(assembly['coord_sys'])}坐标 + {len(assembly['layers'])}层")

    visual_ids = extract_visual_ids(lines, bom)
    print(f"  §7 视觉: {len(visual_ids)} 零件")

    render_plan = extract_render_plan(lines)
    g_count = len(render_plan["groups"])
    v_count = len(render_plan["views"])
    c_count = len(render_plan["constraints"])
    print(f"  §8 渲染: {g_count}组 + {v_count}视角 + {c_count}约束")

    # Connections (synthesized from fasteners + layers)
    connections = extract_connection_matrix(lines, fasteners, assembly.get("layers", []))
    print(f"  §4 连接: {len(connections)} 条")

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
    print(f"  派生量: {len(derived)} 项")

    # Completeness check
    issues = check_completeness(data)
    data["issues"] = issues
    critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
    warning = sum(1 for i in issues if i["severity"] == "WARNING")
    info_count = sum(1 for i in issues if i["severity"] == "INFO")
    print(f"  §9 缺失: {critical} CRITICAL / {warning} WARNING / {info_count} INFO")

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
        description="从设计文档自动生成 CAD_SPEC.md 规范化数据文档")
    parser.add_argument("files", nargs="*",
                        help="设计文档路径 (docs/design/NN-*.md)")
    parser.add_argument("--all", action="store_true",
                        help="处理全部18个子系统")
    parser.add_argument("--force", action="store_true",
                        help="强制重新生成（忽略MD5幂等检查）")
    args = parser.parse_args()

    if args.all:
        # Find all design docs
        design_dir = Path(__file__).parent.parent / "docs" / "design"
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
        print("未找到设计文档。", file=sys.stderr)
        sys.exit(1)

    results = []
    for f in files:
        try:
            result = process_doc(str(f), force=args.force)
            results.append(result)
        except Exception as e:
            print(f"[ERROR] {f.name}: {e}", file=sys.stderr)
            results.append({"output_path": str(f), "skipped": True, "reason": str(e)})

    # Summary
    print()
    print("=" * 60)
    processed = [r for r in results if not r.get("skipped")]
    skipped = [r for r in results if r.get("skipped")]
    print(f"处理: {len(processed)} | 跳过: {len(skipped)} | 共: {len(results)}")
    for r in processed:
        c = r.get("issues_critical", 0)
        w = r.get("issues_warning", 0)
        tag = " ⚠ CRITICAL" if c > 0 else ""
        print(f"  {Path(r['output_path']).name}: "
              f"{r.get('params', 0)}参数 {r.get('bom_parts', 0)}零件 "
              f"{r.get('fasteners', 0)}紧固件 {c}C/{w}W{tag}")
    for r in skipped:
        print(f"  [跳过] {Path(r['output_path']).name}: {r.get('reason', '')}")


if __name__ == "__main__":
    main()
