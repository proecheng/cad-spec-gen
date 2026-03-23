#!/usr/bin/env python3
"""
CAD Spec 设计审查引擎 — 在生成 CAD_SPEC.md 之前对提取数据做工程校验

审查维度：
  A. 力学审查 — 弯矩、螺栓剪切、弹簧力
  B. 装配审查 — 配合尺寸链、包络干涉、装配顺序
  C. 材质审查 — 电偶腐蚀、温度、强度裕度
  D. 数据完整性 — 复用 check_completeness + 新规则
"""

import math
import re
from datetime import datetime
from pathlib import Path

from cad_spec_defaults import (
    MATERIAL_YIELD_STRENGTH, MATERIAL_MAX_TEMP, GALVANIC_PAIRS,
    SAFETY_FACTOR_STATIC, SAFETY_FACTOR_FATIGUE,
    BOLT_SHEAR_STRENGTH, BOLT_STRESS_AREA, BOLT_TORQUE,
    MATERIAL_DENSITY, check_completeness,
)


# ─── Helpers ──────────────────────────────────────────────────────────────

def _find_param(params, *keywords, prefer="max"):
    """Find a parameter by keyword match in name or cn_name.

    When multiple params match:
      prefer="max" → returns largest value (main dimension > sub-feature)
      prefer="min" → returns smallest value
      prefer="first" → returns first match
    """
    matches = []
    for p in params:
        name = (p.get("name", "") + " " + p.get("cn_name", "")).upper()
        if all(kw.upper() in name for kw in keywords):
            try:
                matches.append(float(p["value"]))
            except (ValueError, TypeError):
                continue
    if not matches:
        return None
    if prefer == "min":
        return min(matches)
    elif prefer == "first":
        return matches[0]
    return max(matches)


def _lookup_strength(material_text):
    """Lookup yield strength for a material description."""
    if not material_text:
        return None
    for key, val in MATERIAL_YIELD_STRENGTH.items():
        if key in material_text:
            return val
    return None


def _lookup_max_temp(material_text):
    """Lookup max service temperature for a material description."""
    if not material_text:
        return None
    for key, val in MATERIAL_MAX_TEMP.items():
        if key in material_text:
            return val
    return None


def _normalize_material(mat_text):
    """Normalize material text to canonical keys for galvanic lookup."""
    if not mat_text:
        return None
    mat = mat_text.strip()
    if any(k in mat for k in ("7075", "6061", "6063", "铝", "Al")):
        return "Al"
    if any(k in mat for k in ("SUS", "不锈钢")):
        return "不锈钢"
    if any(k in mat for k in ("钢", "Steel", "Q235", "45钢")):
        return "Steel"
    if any(k in mat for k in ("铜", "Cu", "黄铜")):
        return "Cu"
    if "PEEK" in mat:
        return "PEEK"
    if any(k in mat for k in ("碳纤维", "CFRP")):
        return "碳纤维"
    return None


def _extract_bolt_size(spec_text):
    """Extract bolt size like 'M3' from a spec string."""
    m = re.search(r"(M\d+(?:\.\d+)?)", spec_text or "")
    return m.group(1) if m else None


def _extract_bolt_grade(grade_text):
    """Extract bolt grade like '8.8' or 'A2-70' from grade/remark text."""
    if not grade_text:
        return None
    for g in ("12.9", "10.9", "8.8", "4.8", "A2-80", "A4-70", "A2-70"):
        if g in grade_text:
            return g
    return None


# ─── A. 力学审查 ─────────────────────────────────────────────────────────

def review_mechanical(data):
    """力学校核：悬臂弯矩、螺栓剪切、弹簧定位力。

    Returns list of review items:
        [{id, item, calc_value, allowable, margin_pct, verdict, suggestion}]
    """
    items = []
    params = data.get("params", []) + data.get("derived", [])
    idx = 0

    # --- A1: 悬臂弯矩 ---
    arm_w = _find_param(params, "ARM", "W") or _find_param(params, "悬臂", "宽")
    arm_t = _find_param(params, "ARM", "THICK") or _find_param(params, "悬臂", "厚")
    arm_l = _find_param(params, "ARM", "L") or _find_param(params, "悬臂", "长")
    # Find heaviest station weight
    station_weights = []
    for prefix in ("S1_", "S2_", "S3_", "S4_"):
        w = _find_param(params, prefix + "WEIGHT") or _find_param(params, prefix.replace("_", ""), "WEIGHT")
        if w:
            station_weights.append(w)
    # Also try generic patterns
    if not station_weights:
        for p in params:
            if "WEIGHT" in p.get("name", "") and p.get("name", "") not in ("TOTAL_WEIGHT", "CABLES_WEIGHT"):
                try:
                    station_weights.append(float(p["value"]))
                except (ValueError, TypeError):
                    pass

    if arm_w and arm_t and arm_l and station_weights:
        max_weight_g = max(station_weights)
        F = max_weight_g / 1000.0 * 9.81  # N
        M = F * arm_l  # N·mm (force at arm tip)
        I = arm_w * arm_t**3 / 12.0  # mm⁴
        y = arm_t / 2.0
        sigma = M * y / I if I > 0 else float('inf')  # MPa
        allowable = MATERIAL_YIELD_STRENGTH.get("7075-T6", 503) / SAFETY_FACTOR_STATIC
        margin = (allowable - sigma) / allowable * 100 if allowable > 0 else 0

        idx += 1
        verdict = "OK" if margin > 20 else ("WARNING" if margin > 0 else "CRITICAL")
        items.append({
            "id": f"A{idx}", "item": f"悬臂弯曲应力 ({arm_w}×{arm_t}mm, 载荷{max_weight_g:.0f}g)",
            "calc_value": f"σ={sigma:.1f} MPa",
            "allowable": f"σ_allow={allowable:.0f} MPa (7075-T6/SF={SAFETY_FACTOR_STATIC})",
            "margin_pct": f"{margin:.0f}%",
            "verdict": verdict,
            "suggestion": "" if verdict == "OK" else
                f"裕度偏低({margin:.0f}%)，建议增大截面厚度或减轻工位重量" if verdict == "WARNING" else
                "应力超限，必须增大悬臂截面或更换材料",
        })

    # --- A2: 螺栓剪切 ---
    fasteners = data.get("fasteners", [])
    for f in fasteners:
        bolt = _extract_bolt_size(f.get("spec", ""))
        if not bolt or bolt not in BOLT_STRESS_AREA:
            continue
        qty = f.get("qty", 1)
        grade = _extract_bolt_grade(f.get("grade", "") + " " + f.get("remark", ""))
        if not grade:
            grade = "A2-70"  # common default for stainless
        shear_strength = BOLT_SHEAR_STRENGTH.get(grade, 280)
        area = BOLT_STRESS_AREA[bolt]
        total_capacity = shear_strength * area * qty  # N

        # Estimate load from station weight if this is a mount bolt
        loc = f.get("location", "")
        if any(k in loc for k in ("工位", "模块", "station")):
            # Use max station weight as conservative estimate
            if station_weights:
                load_N = max(station_weights) / 1000.0 * 9.81 * 3  # ×3 for dynamic
                margin = (total_capacity - load_N) / total_capacity * 100
                idx += 1
                verdict = "OK" if margin > 50 else ("WARNING" if margin > 0 else "CRITICAL")
                items.append({
                    "id": f"A{idx}", "item": f"螺栓剪切 {loc} ({qty}×{bolt} {grade})",
                    "calc_value": f"F_load≈{load_N:.0f}N (动载×3)",
                    "allowable": f"F_cap={total_capacity:.0f}N ({qty}×{bolt}×{shear_strength}MPa)",
                    "margin_pct": f"{margin:.0f}%",
                    "verdict": verdict,
                    "suggestion": "" if verdict == "OK" else
                        f"剪切裕度不足，建议增加螺栓数量或提升等级",
                })

    # --- A3: 弹簧定位力 ---
    spring_force = _find_param(params, "SPRING", "FORCE") or _find_param(params, "弹簧", "力")
    spring_r = _find_param(params, "SPRING", "R") or _find_param(params, "弹簧", "半径")
    if spring_force and spring_r:
        # Positioning moment: M = F × R
        moment = spring_force * spring_r  # N·mm
        # Inertia moment from total rotating mass
        total_w = _find_param(params, "TOTAL_WEIGHT") or sum(station_weights) if station_weights else None
        if total_w:
            # Rough check: spring moment should exceed friction + inertia at stop
            idx += 1
            items.append({
                "id": f"A{idx}", "item": f"弹簧销定位力矩",
                "calc_value": f"M_spring={moment:.0f} N·mm ({spring_force}N×R{spring_r}mm)",
                "allowable": f"需 > 旋转部件惯性制动力矩",
                "margin_pct": "—",
                "verdict": "INFO",
                "suggestion": "弹簧力数值来自设计文档，建议实测验证定位可靠性",
            })

    return items


# ─── B. 装配审查 ─────────────────────────────────────────────────────────

def review_assembly(data):
    """装配校核：配合尺寸链、包络干涉。

    Returns list of review items:
        [{id, item, detail, verdict, suggestion}]
    """
    items = []
    params = data.get("params", []) + data.get("derived", [])
    tolerances = data.get("tolerances", {})
    idx = 0

    # --- B1: 配合尺寸链 — 中心孔 vs 输出轴 ---
    center_hole = _find_param(params, "CENTER", "HOLE") or _find_param(params, "中心孔")
    output_dia = _find_param(params, "OUTPUT", "DIA") or _find_param(params, "输出轴")
    if center_hole and output_dia:
        idx += 1
        if center_hole < output_dia:
            items.append({
                "id": f"B{idx}", "item": "中心孔/输出轴配合",
                "detail": f"中心孔Φ{center_hole}mm < 输出轴Φ{output_dia}mm — 无法装配",
                "verdict": "CRITICAL",
                "suggestion": "修正中心孔直径或输出轴直径",
            })
        else:
            clearance = center_hole - output_dia
            items.append({
                "id": f"B{idx}", "item": "中心孔/输出轴配合",
                "detail": f"间隙={clearance:.2f}mm (孔Φ{center_hole} - 轴Φ{output_dia})",
                "verdict": "OK" if clearance < 1.0 else "WARNING",
                "suggestion": "" if clearance < 1.0 else "间隙过大，可能影响同心度",
            })

    # --- B2: PEEK绝缘环 vs 法兰 ---
    peek_od = _find_param(params, "PEEK", "OD")
    flange_od = _find_param(params, "FLANGE", "OD")
    if peek_od and flange_od:
        idx += 1
        if peek_od > flange_od:
            items.append({
                "id": f"B{idx}", "item": "PEEK环外径 vs 法兰外径",
                "detail": f"PEEK Φ{peek_od}mm > 法兰 Φ{flange_od}mm — PEEK突出法兰",
                "verdict": "WARNING",
                "suggestion": "确认PEEK环不会与旋转部件干涉",
            })
        else:
            items.append({
                "id": f"B{idx}", "item": "PEEK环外径 vs 法兰外径",
                "detail": f"PEEK Φ{peek_od}mm < 法兰 Φ{flange_od}mm — 内缩{flange_od - peek_od:.1f}mm",
                "verdict": "OK", "suggestion": "",
            })

    # --- B3: 工位包络干涉 ---
    mount_r = _find_param(params, "MOUNT", "CENTER", "R") or _find_param(params, "安装面", "中心")
    station_envs = []
    for prefix in ("S1_", "S2_", "S3_", "S4_"):
        env_dia = _find_param(params, prefix + "ENVELOPE_DIA") or _find_param(params, prefix + "BODY_W")
        if env_dia:
            station_envs.append((prefix.rstrip("_"), env_dia))

    if mount_r and len(station_envs) >= 2:
        # Adjacent stations are 90° apart. Distance = mount_r * sqrt(2)
        adj_distance = mount_r * math.sqrt(2)
        for i in range(len(station_envs)):
            for j in range(i + 1, len(station_envs)):
                name_i, env_i = station_envs[i]
                name_j, env_j = station_envs[j]
                min_distance = (env_i + env_j) / 2.0
                gap = adj_distance - min_distance
                idx += 1
                verdict = "OK" if gap > 5 else ("WARNING" if gap > 0 else "CRITICAL")
                items.append({
                    "id": f"B{idx}", "item": f"工位包络间隙 {name_i}↔{name_j}",
                    "detail": f"中心距={adj_distance:.1f}mm, 最小间距={min_distance:.1f}mm, 间隙={gap:.1f}mm",
                    "verdict": verdict,
                    "suggestion": "" if verdict == "OK" else
                        "工位间隙不足，可能装配干涉" if verdict == "WARNING" else
                        "工位包络重叠，无法装配",
                })

    # --- B4: 悬臂长度 vs 安装面 ---
    arm_length = _find_param(params, "FLANGE_L", prefer="first") or _find_param(params, "ARM", "L", prefer="min") or _find_param(params, "悬臂", "长", prefer="min")
    mount_face = _find_param(params, "安装面", prefer="min")
    flange_r = _find_param(params, "FLANGE", "R", prefer="first") or (flange_od / 2.0 if flange_od else None)
    if arm_length and mount_face and flange_r and mount_r and arm_length < 200 and mount_face < 200:
        calc_r = flange_r + arm_length
        half_face = mount_face / 2.0
        actual_r = calc_r - half_face
        diff = abs(actual_r - mount_r)
        idx += 1
        if diff > 2.0:
            items.append({
                "id": f"B{idx}", "item": "安装面中心距校核",
                "detail": f"计算值={actual_r:.1f}mm vs 文档值={mount_r:.1f}mm (差{diff:.1f}mm)",
                "verdict": "WARNING",
                "suggestion": "悬臂长度、法兰半径与安装面中心距不自洽，请核实",
            })
        else:
            items.append({
                "id": f"B{idx}", "item": "安装面中心距校核",
                "detail": f"计算值={actual_r:.1f}mm ≈ 文档值={mount_r:.1f}mm (差{diff:.1f}mm)",
                "verdict": "OK", "suggestion": "",
            })

    return items


# ─── C. 材质审查 ─────────────────────────────────────────────────────────

def review_material(data):
    """材质校核：电偶腐蚀、温度、强度。

    Returns list of review items:
        [{id, item, detail, verdict, suggestion}]
    """
    items = []
    idx = 0

    # Collect material pairs from connections and BOM
    bom = data.get("bom")
    connections = data.get("connections", [])

    material_map = {}  # part_name → material_text
    if bom:
        for assy in bom.get("assemblies", []):
            for part in assy.get("parts", []):
                material_map[part["name"]] = part.get("material", "")

    # --- C1: 电偶腐蚀 ---
    for conn in connections:
        partA = conn.get("partA", "")
        partB = conn.get("partB", "")
        matA = material_map.get(partA, "")
        matB = material_map.get(partB, "")
        normA = _normalize_material(matA)
        normB = _normalize_material(matB)
        if normA and normB and normA != normB:
            risk = GALVANIC_PAIRS.get((normA, normB)) or GALVANIC_PAIRS.get((normB, normA))
            if risk:
                idx += 1
                items.append({
                    "id": f"C{idx}",
                    "item": f"电偶腐蚀 {partA}↔{partB}",
                    "detail": f"{matA} ({normA}) + {matB} ({normB}) — 风险={risk}",
                    "verdict": "WARNING" if risk in ("HIGH", "MEDIUM") else "INFO",
                    "suggestion": f"建议使用绝缘垫圈或涂层隔离" if risk in ("HIGH", "MEDIUM") else "",
                })

    # --- C2: 温度评估 (if working temp specified) ---
    params = data.get("params", []) + data.get("derived", [])
    work_temp = _find_param(params, "TEMP") or _find_param(params, "温度")
    if work_temp and material_map:
        for part_name, mat in material_map.items():
            max_t = _lookup_max_temp(mat)
            if max_t and work_temp > max_t * 0.8:
                idx += 1
                items.append({
                    "id": f"C{idx}", "item": f"温度裕度 {part_name}",
                    "detail": f"工作温度{work_temp}°C vs {mat}最高{max_t}°C (裕度{(max_t - work_temp) / max_t * 100:.0f}%)",
                    "verdict": "WARNING" if work_temp <= max_t else "CRITICAL",
                    "suggestion": "工作温度接近或超过材料极限" if work_temp > max_t * 0.8 else "",
                })

    # --- C3: 材料强度裕度 (generic check for known stressed parts) ---
    visual_ids = data.get("visual_ids", [])
    for vis in visual_ids:
        mat = vis.get("material", "")
        strength = _lookup_strength(mat)
        if strength and strength < 150:  # low-strength material in structural role
            part = vis.get("part", "")
            size = vis.get("size", "")
            if any(k in part for k in ("壳体", "支架", "bracket", "housing")):
                idx += 1
                items.append({
                    "id": f"C{idx}", "item": f"低强度结构件 {part}",
                    "detail": f"{mat} σ_y={strength}MPa 用于结构件 ({size})",
                    "verdict": "INFO",
                    "suggestion": "确认该零件不承受显著力学载荷",
                })

    return items


# ─── D. 数据完整性 ───────────────────────────────────────────────────────

def review_completeness(data):
    """数据完整性审查，复用 check_completeness + 新规则。

    Returns list:
        [{id, item, severity, auto_fill, default_value, note}]
    """
    items = []

    # Reuse existing completeness check
    base_issues = check_completeness(data)
    for issue in base_issues:
        items.append({
            "id": issue["id"],
            "item": f"{issue['section']}: {issue['missing']}",
            "severity": issue["severity"],
            "auto_fill": "是" if issue.get("default", "—") != "—" else "否",
            "default_value": issue.get("default", "—"),
            "note": issue["suggestion"],
        })

    # Additional rules
    params = data.get("params", []) + data.get("derived", [])
    idx = len(items)

    # D+1: Check if any param has empty unit
    empty_unit_count = sum(1 for p in data.get("params", []) if not p.get("unit"))
    if empty_unit_count > 3:
        idx += 1
        items.append({
            "id": f"D{idx}", "item": f"参数缺少单位 ({empty_unit_count}项)",
            "severity": "WARNING", "auto_fill": "否", "default_value": "—",
            "note": "多个参数缺少单位，可能导致下游计算错误",
        })

    # D+2: BOM material coverage
    bom = data.get("bom")
    if bom:
        missing_mat = []
        for assy in bom.get("assemblies", []):
            for part in assy.get("parts", []):
                if not part.get("material") or part["material"] in ("—", ""):
                    missing_mat.append(part["name"])
        if missing_mat:
            idx += 1
            items.append({
                "id": f"D{idx}", "item": f"BOM缺少材质 ({len(missing_mat)}项)",
                "severity": "WARNING", "auto_fill": "否", "default_value": "—",
                "note": f"缺失: {', '.join(missing_mat[:5])}{'...' if len(missing_mat) > 5 else ''}",
            })

    return items


# ─── 主入口 ──────────────────────────────────────────────────────────────

def run_review(data):
    """运行全部 4 类审查，返回汇总字典。

    Args:
        data: cad_spec_gen.py 提取的完整数据字典

    Returns:
        {
            "mechanical": [...],
            "assembly": [...],
            "material": [...],
            "completeness": [...],
            "summary": {"critical": N, "warning": N, "info": N, "ok": N},
        }
    """
    mech = review_mechanical(data)
    assy = review_assembly(data)
    mat = review_material(data)
    comp = review_completeness(data)

    # Count verdicts
    all_items = mech + assy + mat
    verdicts = [it.get("verdict", "") for it in all_items]
    severities = [it.get("severity", "") for it in comp]

    summary = {
        "critical": verdicts.count("CRITICAL") + severities.count("CRITICAL"),
        "warning": verdicts.count("WARNING") + severities.count("WARNING"),
        "info": verdicts.count("INFO") + severities.count("INFO"),
        "ok": verdicts.count("OK"),
    }

    return {
        "mechanical": mech,
        "assembly": assy,
        "material": mat,
        "completeness": comp,
        "summary": summary,
    }


# ─── Markdown 渲染 ───────────────────────────────────────────────────────

def _md_table(columns, rows):
    """Render a Markdown table."""
    if not rows:
        return f"| {' | '.join(columns)} |\n| {' | '.join(['---'] * len(columns))} |\n| 无 |{'|' * (len(columns) - 1)}\n"
    lines = [
        f"| {' | '.join(columns)} |",
        f"| {' | '.join(['---'] * len(columns))} |",
    ]
    for row in rows:
        padded = list(row) + [""] * (len(columns) - len(row))
        lines.append(f"| {' | '.join(str(c) for c in padded[:len(columns)])} |")
    return "\n".join(lines) + "\n"


def render_review(review_data, info, filepath, md5):
    """将审查结果渲染为 DESIGN_REVIEW.md Markdown 文档。

    Args:
        review_data: run_review() 的返回值
        info: {"name": "子系统名", "prefix": "GIS-XX"}
        filepath: 源设计文档路径
        md5: 源文档 MD5 (12位)

    Returns:
        str: Markdown 文本
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    s = review_data["summary"]

    sections = []
    sections.append(f"# 设计审查报告 — {info['name']} ({info['prefix']})")
    sections.append(f"<!-- Source: {filepath} | Hash: {md5} | Date: {now} -->")
    sections.append("")

    # A. 力学审查
    sections.append("## A. 力学审查")
    sections.append("")
    mech = review_data["mechanical"]
    sections.append(_md_table(
        ["#", "审查项", "计算值", "许用值", "裕度%", "结论", "建议"],
        [[m["id"], m["item"], m["calc_value"], m["allowable"],
          m["margin_pct"], m["verdict"], m["suggestion"]] for m in mech]
    ))

    # B. 装配审查
    sections.append("## B. 装配审查")
    sections.append("")
    assy = review_data["assembly"]
    sections.append(_md_table(
        ["#", "审查项", "详情", "结论", "建议"],
        [[a["id"], a["item"], a["detail"], a["verdict"], a["suggestion"]] for a in assy]
    ))

    # C. 材质审查
    sections.append("## C. 材质审查")
    sections.append("")
    mat = review_data["material"]
    sections.append(_md_table(
        ["#", "审查项", "详情", "结论", "建议"],
        [[m["id"], m["item"], m["detail"], m["verdict"], m["suggestion"]] for m in mat]
    ))

    # D. 缺失数据
    sections.append("## D. 缺失数据")
    sections.append("")
    comp = review_data["completeness"]
    sections.append(_md_table(
        ["#", "缺失项", "严重度", "可自动填充", "建议默认值", "说明"],
        [[c["id"], c["item"], c["severity"], c["auto_fill"],
          c["default_value"], c["note"]] for c in comp]
    ))

    # Summary
    sections.append("## 审查结论")
    sections.append("")
    sections.append(f"- **CRITICAL**: {s['critical']}项 / **WARNING**: {s['warning']}项 / **INFO**: {s['info']}项 / **OK**: {s['ok']}项")

    if s["critical"] > 0:
        sections.append("- 建议: **需修正后继续** — 存在阻塞性问题")
    elif s["warning"] > 0:
        sections.append("- 建议: **可继续，但建议先处理 WARNING 项**")
    else:
        sections.append("- 建议: **可继续** — 无阻塞性问题")

    sections.append("")
    sections.append("> 用户可选择「继续审查」讨论具体问题，或「下一步」生成 CAD_SPEC.md")
    sections.append("")

    return "\n".join(sections)
