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
    MATERIAL_DENSITY, COMMON_CONNECTION_PATTERNS, WEAK_LOAD_CONNECTIONS,
    PARAM_UNIT_PATTERNS, SURFACE_RA,
    check_completeness,
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
        if not isinstance(p, dict):
            continue
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
    params = [p for p in (data.get("params", []) + data.get("derived", [])) if isinstance(p, dict)]
    idx = 0

    # --- A1: 悬臂弯矩 ---
    arm_w = _find_param(params, "ARM", "W") or _find_param(params, "悬臂", "宽")
    arm_t = _find_param(params, "ARM", "THICK") or _find_param(params, "悬臂", "厚")
    arm_l = _find_param(params, "ARM", "L") or _find_param(params, "悬臂", "长")
    # Find heaviest station weight — 动态检测工位数，不硬编码 S1_~S4_
    station_weights = []
    station_prefixes = set()
    for p in params:
        pname = p.get("name", "")
        m = re.match(r"(S\d+_)", pname)
        if m:
            station_prefixes.add(m.group(1))
    for prefix in sorted(station_prefixes):
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
        # 尝试从 BOM 获取实际材质，不硬编码 7075-T6
        _arm_mat = None
        bom = data.get("bom")
        if bom:
            for assy in bom.get("assemblies", []):
                for part in assy.get("parts", []):
                    if "悬臂" in part.get("name", "") or "arm" in part.get("name", "").lower():
                        _arm_mat = part.get("material", "")
                        break
        _yield = MATERIAL_YIELD_STRENGTH.get(_arm_mat, 0) if _arm_mat else 0
        if _yield == 0:
            # 从所有材质中找最可能的
            for mk in MATERIAL_YIELD_STRENGTH:
                if _arm_mat and mk.lower() in _arm_mat.lower():
                    _yield = MATERIAL_YIELD_STRENGTH[mk]
                    break
        if _yield == 0:
            _yield = 250  # 保守通用值
        allowable = _yield / SAFETY_FACTOR_STATIC
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
    params = [p for p in (data.get("params", []) + data.get("derived", [])) if isinstance(p, dict)]
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

    # --- B2: 同心件外径干涉检查 (通用) ---
    # 检测是否存在外径配对关系（如绝缘环 vs 法兰、盖板 vs 壳体）
    od_params = [(p.get("name", ""), float(p["value"]))
                 for p in params
                 if "OD" in p.get("name", "") and p.get("value")]
    if len(od_params) >= 2:
        # 按外径从大到小排序，检查相邻对
        od_params.sort(key=lambda x: x[1], reverse=True)
        for k in range(len(od_params) - 1):
            outer_name, outer_val = od_params[k]
            inner_name, inner_val = od_params[k + 1]
            if inner_val > outer_val:
                idx += 1
                items.append({
                    "id": f"B{idx}", "item": f"{inner_name} vs {outer_name} 外径关系",
                    "detail": f"{inner_name} Φ{inner_val}mm > {outer_name} Φ{outer_val}mm — 内件突出外件",
                    "verdict": "WARNING",
                    "suggestion": "确认尺寸关系正确，内件不应超出外件轮廓",
                })

    # --- B3: 工位包络干涉 (通用：动态检测工位数) ---
    mount_r = _find_param(params, "MOUNT", "CENTER", "R") or _find_param(params, "安装面", "中心")
    station_envs = []
    for prefix in sorted(station_prefixes) if 'station_prefixes' in dir() else []:
        env_dia = _find_param(params, prefix + "ENVELOPE_DIA") or _find_param(params, prefix + "BODY_W")
        if env_dia:
            station_envs.append((prefix.rstrip("_"), env_dia))
    # Also try generic detection if no S\d_ prefixes found
    if not station_envs:
        for p in params:
            pname = p.get("name", "")
            m = re.match(r"(S\d+)_(?:ENVELOPE_DIA|BODY_W)", pname)
            if m and p.get("value"):
                try:
                    station_envs.append((m.group(1), float(p["value"])))
                except (ValueError, TypeError):
                    pass

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
    # Mount face SIZE (not flatness/roughness) — filter for reasonable dimension (>5mm)
    mount_face_candidates = [
        v for name, v in ((p.get("name", ""), p.get("value")) for p in params)
        if v and "安装面" in str(name) and isinstance(v, (int, float)) and 5 < v < 200
    ]
    mount_face = min(mount_face_candidates) if mount_face_candidates else _find_param(params, "安装面", "尺寸")
    # Prefer flange_od/2 — _find_param("FLANGE","R") may match spring pin R=42mm
    flange_od = _find_param(params, "FLANGE", "OD") or _find_param(params, "法兰", "外径") or _find_param(params, "FLANGE_OD")
    flange_r = (flange_od / 2.0 if flange_od else None) or _find_param(params, "FLANGE", "R", prefer="max")
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

    # --- B5: 悬空零件检查 — BOM零件不在连接矩阵中 ---
    connections = data.get("connections", [])
    bom = data.get("bom")
    if connections and bom:
        # Build set of part names AND part numbers from connections
        connected_names = set()
        connected_pnums = set()
        for conn in connections:
            for key in ("partA", "partB"):
                raw = str(conn.get(key, ""))
                # Extract part number from parenthetical like "(GIS-EE-001-01)" or "(GIS-EE-002)"
                pnum_match = re.search(r"\(?(GIS-[A-Z]+-\d+(?:-\d+)?)\)?", raw)
                if pnum_match:
                    connected_pnums.add(pnum_match.group(1))
                # Strip parenthetical for name matching
                name = re.sub(r"\s*\(GIS-[A-Z]+-\d+(?:-\d+)?\)", "", raw).strip()
                if name and name not in ("全部", "—", ""):
                    connected_names.add(name)

        # Build assembly part_no → member part_no map
        assy_pnum_members = {}  # "GIS-EE-001" → {"GIS-EE-001-01", ...}
        for assy in bom.get("assemblies", []):
            apnum = assy.get("part_no", "")
            if apnum:
                assy_pnum_members[apnum] = {p.get("part_no", "") for p in assy.get("parts", [])}

        # Mark parts as connected if their assembly appears in connections
        connected_via_assy = set()
        for cpnum in connected_pnums:
            # Direct assembly match: GIS-EE-002 → all parts under GIS-EE-002
            if cpnum in assy_pnum_members:
                connected_via_assy.update(assy_pnum_members[cpnum])
            # Sub-part match: GIS-EE-001-01 → parent GIS-EE-001's members
            parent = re.sub(r"-\d{2}$", "", cpnum)
            if parent in assy_pnum_members:
                connected_via_assy.update(assy_pnum_members[parent])

        # Check leaf parts
        orphan_parts = []
        for assy in bom.get("assemblies", []):
            for part in assy.get("parts", []):
                pname = part.get("name", "")
                pnum = part.get("part_no", "")
                # Skip assembly-level entries and 总成
                if "总成" in pname or (pnum and re.match(r"^GIS-[A-Z]+-\d{3}$", pnum)):
                    continue
                # Connected via assembly part_number
                if pnum in connected_via_assy:
                    continue
                # Connected via direct part_number match
                if pnum in connected_pnums:
                    continue
                # Connected via name substring match (fuzzy)
                found = False
                pname_short = pname.split("（")[0].split("(")[0].strip()
                for cn in connected_names:
                    cn_short = cn.split("（")[0].split("(")[0].strip()
                    if (len(pname_short) >= 2 and pname_short in cn) or \
                       (len(cn_short) >= 2 and cn_short in pname):
                        found = True
                        break
                if not found:
                    orphan_parts.append(pname)

        if orphan_parts:
            idx += 1
            items.append({
                "id": f"B{idx}", "item": f"悬空零件 ({len(orphan_parts)}项)",
                "detail": f"BOM中以下零件未出现在连接矩阵: {', '.join(orphan_parts[:5])}{'...' if len(orphan_parts) > 5 else ''}",
                "verdict": "WARNING",
                "suggestion": "补充这些零件的连接关系，或确认为独立附件",
            })
        else:
            idx += 1
            items.append({
                "id": f"B{idx}", "item": "悬空零件检查",
                "detail": f"所有BOM零件均出现在连接矩阵中",
                "verdict": "OK", "suggestion": "",
            })

    # --- B6: 连接描述缺失 ---
    if connections:
        empty_conns = []
        for conn in connections:
            ctype = str(conn.get("type", "")).strip()
            if not ctype or ctype in ("—", "-", "") or len(ctype) < 3:
                pa = conn.get("partA", "?")
                pb = conn.get("partB", "?")
                empty_conns.append(f"{pa}↔{pb}")
        idx += 1
        if empty_conns:
            items.append({
                "id": f"B{idx}", "item": f"连接描述缺失 ({len(empty_conns)}条)",
                "detail": f"缺少连接方式: {', '.join(empty_conns[:3])}{'...' if len(empty_conns) > 3 else ''}",
                "verdict": "WARNING",
                "suggestion": "补充连接类型（螺栓规格、配合方式等）",
            })
        else:
            items.append({
                "id": f"B{idx}", "item": "连接描述完整性",
                "detail": f"所有{len(connections)}条连接均有连接方式描述",
                "verdict": "OK", "suggestion": "",
            })

    # --- B7: 连接方式合理性 ---
    if connections:
        unusual_conns = []
        weak_conns = []
        for conn in connections:
            ctype = str(conn.get("type", "")).strip()
            if not ctype or len(ctype) < 3:
                continue  # Already flagged in B6
            # Check if matches any common pattern
            matched = any(re.search(pat, ctype, re.IGNORECASE) for pat in COMMON_CONNECTION_PATTERNS)
            if not matched:
                unusual_conns.append(f"{conn.get('partA', '?')}↔{conn.get('partB', '?')}: {ctype}")
            # Check if weak connection used
            for wpat in WEAK_LOAD_CONNECTIONS:
                if re.search(wpat, ctype, re.IGNORECASE):
                    weak_conns.append(f"{conn.get('partA', '?')}↔{conn.get('partB', '?')}: {ctype}")
                    break

        if unusual_conns:
            idx += 1
            items.append({
                "id": f"B{idx}", "item": f"非常规连接方式 ({len(unusual_conns)}条)",
                "detail": "; ".join(unusual_conns[:3]) + ("..." if len(unusual_conns) > 3 else ""),
                "verdict": "INFO",
                "suggestion": "确认连接方式符合设计意图",
            })
        if weak_conns:
            idx += 1
            items.append({
                "id": f"B{idx}", "item": f"低强度连接方式 ({len(weak_conns)}条)",
                "detail": "; ".join(weak_conns[:3]) + ("..." if len(weak_conns) > 3 else ""),
                "verdict": "WARNING",
                "suggestion": "粘接/卡扣连接承载能力有限，确认该处不承受显著力学载荷",
            })

    # --- B8: 对向工位空间重叠估算 ---
    # Stations at 180° apart share the same diameter line → higher overlap risk
    if mount_r and len(station_envs) >= 2:
        diametral_distance = 2 * mount_r  # 180° apart
        for i in range(len(station_envs)):
            for j in range(i + 1, len(station_envs)):
                name_i, env_i = station_envs[i]
                name_j, env_j = station_envs[j]
                # Determine if 180° apart (S1↔S3, S2↔S4)
                si = int(name_i.replace("S", "")) if name_i.startswith("S") else 0
                sj = int(name_j.replace("S", "")) if name_j.startswith("S") else 0
                if abs(si - sj) == 2:  # 180° apart
                    overlap = (env_i + env_j) / 2.0 - diametral_distance
                    if overlap > 0:
                        idx += 1
                        items.append({
                            "id": f"B{idx}", "item": f"对向工位空间重叠 {name_i}↔{name_j}",
                            "detail": f"对向距离={diametral_distance:.1f}mm, 包络半径和={(env_i + env_j) / 2.0:.1f}mm, 重叠={overlap:.1f}mm",
                            "verdict": "WARNING",
                            "suggestion": "对向工位包络可能交叉，建议3D校验",
                        })

    # --- B10: 孤儿总成 (BOM assembly not in layers and not excluded) ---
    layers = data.get("assembly", {}).get("layers", [])
    layer_pnos = set()
    excluded_pnos = set()
    for l in layers:
        m_pno = re.search(r"([A-Z]+-[A-Z]+-\d+)", l.get("part", ""))
        if m_pno:
            if l.get("exclude"):
                excluded_pnos.add(m_pno.group(1))
            else:
                layer_pnos.add(m_pno.group(1))

    bom = data.get("bom")
    if bom:
        orphans = []
        for assy in bom.get("assemblies", []):
            apno = assy.get("part_no", "")
            if apno and apno not in layer_pnos and apno not in excluded_pnos:
                orphans.append(apno)
        if orphans:
            idx += 1
            items.append({
                "id": f"B{idx}", "item": f"孤儿总成 ({len(orphans)}项)",
                "detail": f"BOM总成在§6.2中无定位且未标记排除: {', '.join(orphans)}",
                "verdict": "CRITICAL",
                "suggestion": "在源文档装配层叠表中添加定位，或在否定约束表中标记排除",
            })

    # --- B11: 零件缺少包络尺寸 ---
    envelopes = data.get("part_envelopes", {})
    if bom:
        missing_env = []
        for assy in bom.get("assemblies", []):
            for part in assy.get("parts", []):
                if "自制" in part.get("make_buy", "") and part["part_no"] not in envelopes:
                    missing_env.append(part["part_no"])
        if missing_env:
            idx += 1
            items.append({
                "id": f"B{idx}", "item": f"自制件缺少包络尺寸 ({len(missing_env)}项)",
                "detail": f"缺少包络: {', '.join(missing_env[:5])}{'...' if len(missing_env) > 5 else ''}",
                "verdict": "WARNING",
                "suggestion": "在源文档中补充零件尺寸表或BOM材质列中的尺寸",
            })

    # --- B12: 总成缺少零件级定位 ---
    part_offsets = data.get("assembly", {}).get("part_offsets", {})
    if bom:
        for assy in bom.get("assemblies", []):
            apno = assy.get("part_no", "")
            if apno in excluded_pnos:
                continue
            children = assy.get("parts", [])
            if not children:
                continue
            positioned = sum(1 for p in children if p["part_no"] in part_offsets)
            total = len(children)
            if total > 0 and positioned / total < 0.5:
                idx += 1
                items.append({
                    "id": f"B{idx}", "item": f"总成 {apno} 零件级定位不足",
                    "detail": f"{positioned}/{total} 零件有定位 ({positioned/total*100:.0f}%)",
                    "verdict": "WARNING",
                    "suggestion": "在源文档中添加串联堆叠链（→语法）描述装配顺序",
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
    params = [p for p in (data.get("params", []) + data.get("derived", [])) if isinstance(p, dict)]
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
    params = [p for p in (data.get("params", []) + data.get("derived", [])) if isinstance(p, dict)]
    idx = len(items)

    # D+1: Check if any param has empty unit — attempt to infer units
    empty_unit_params = [p for p in data.get("params", []) if not p.get("unit")]
    inferred_units = []
    for p in empty_unit_params:
        pname = str(p.get("name", ""))
        for pat, unit in PARAM_UNIT_PATTERNS.items():
            if re.search(pat, pname, re.IGNORECASE):
                inferred_units.append((pname, unit))
                break
    if len(empty_unit_params) > 3:
        idx += 1
        can_infer = len(inferred_units)
        items.append({
            "id": f"D{idx}", "item": f"参数缺少单位 ({len(empty_unit_params)}项)",
            "severity": "WARNING",
            "auto_fill": "是" if can_infer > 0 else "否",
            "default_value": f"可推断{can_infer}项" if can_infer > 0 else "—",
            "note": "多个参数缺少单位，可能导致下游计算错误",
            "_auto_fill_detail": inferred_units if inferred_units else None,
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

    # D+3: Fasteners missing torque — can auto-fill from BOLT_TORQUE
    fasteners = data.get("fasteners", [])
    missing_torque = []
    for f in fasteners:
        torque = str(f.get("torque", "")).strip()
        if not torque or torque in ("—", ""):
            spec = str(f.get("spec", ""))
            bolt_match = re.search(r"(M\d+(?:\.\d+)?)", spec)
            if bolt_match:
                bsize = bolt_match.group(1)
                default_t = BOLT_TORQUE.get(bsize)
                if default_t:
                    missing_torque.append((f.get("location", "?"), bsize, default_t))
    if missing_torque:
        idx += 1
        items.append({
            "id": f"D{idx}", "item": f"螺栓缺少力矩 ({len(missing_torque)}项)",
            "severity": "INFO",
            "auto_fill": "是",
            "default_value": f"按8.8级标准力矩补全{len(missing_torque)}项",
            "note": "; ".join(f"{loc} {sz}→{t}Nm" for loc, sz, t in missing_torque[:5]),
            "_auto_fill_detail": missing_torque,
        })

    # D+4: Parts missing surface roughness — can auto-fill from SURFACE_RA
    tolerances = data.get("tolerances", {})
    surfaces = tolerances.get("surfaces", [])
    vis_ids = data.get("visual_ids", [])
    parts_with_ra = {s.get("part", "") for s in surfaces}
    fillable_ra = []
    for vis in vis_ids:
        pname = vis.get("part", "")
        mat = vis.get("material", "")
        if pname and pname not in parts_with_ra and mat:
            for mk, rv in SURFACE_RA.items():
                if mk.lower() in mat.lower() or mk in mat:
                    fillable_ra.append((pname, mat, rv))
                    break
    if fillable_ra:
        idx += 1
        items.append({
            "id": f"D{idx}", "item": f"零件缺少表面粗糙度 ({len(fillable_ra)}项)",
            "severity": "INFO",
            "auto_fill": "是",
            "default_value": f"按材质默认Ra补全{len(fillable_ra)}项",
            "note": "; ".join(f"{p} ({m})→Ra{r}" for p, m, r in fillable_ra[:5]),
            "_auto_fill_detail": fillable_ra,
        })

    # ── 标注数据充分性审查（新增） ─────────────────────────────────────────

    # D+N: 尺寸公差不足
    tolerances = data.get("tolerances", {})
    dim_tols = tolerances.get("dim_tols", [])
    custom_parts = [p for assy in ((data.get("bom") or {}).get("assemblies", []))
                    for p in assy.get("parts", []) if "自制" in p.get("make_buy", "")]
    if custom_parts and len(dim_tols) < len(custom_parts) * 2:
        idx += 1
        items.append({
            "id": f"D{idx}",
            "item": f"§2.1 尺寸公差不足 ({len(dim_tols)}条 vs {len(custom_parts)}个自制件)",
            "severity": "WARNING",
            "auto_fill": "否",
            "default_value": "—",
            "note": "自制零件的关键尺寸应有明确公差，否则自动标注无法标注公差文本",
        })

    # D+N: 公差参数名无法匹配 params
    param_names = {p.get("name", "") for p in params}
    if dim_tols:
        unmatched = [t for t in dim_tols if t.get("name", "") not in param_names]
        if len(unmatched) > len(dim_tols) * 0.5:
            idx += 1
            items.append({
                "id": f"D{idx}",
                "item": f"尺寸公差参数名无法匹配 ({len(unmatched)}/{len(dim_tols)}项)",
                "severity": "WARNING",
                "auto_fill": "否",
                "default_value": "—",
                "note": f"不匹配: {', '.join(t['name'] for t in unmatched[:5])}",
            })

    # D+N: 材质无法推断 material_type
    from cad_spec_defaults import classify_material_type as _cmt
    if custom_parts:
        unclassified = [p for p in custom_parts
                        if _cmt(p.get("material", "")) is None and p.get("material")]
        if unclassified:
            idx += 1
            items.append({
                "id": f"D{idx}",
                "item": f"零件材质无法推断 material_type ({len(unclassified)}项)",
                "severity": "WARNING",
                "auto_fill": "否",
                "default_value": "—",
                "note": f"无法分类: {', '.join(p['name'] + '(' + p.get('material', '') + ')' for p in unclassified[:3])}",
            })

    return items


# ─── 自动补全 ──────────────────────────────────────────────────────────

def apply_auto_fill(review_data, data):
    """Apply auto-computable values to data dict.

    Reads completeness items with auto_fill=="是" and updates the
    corresponding entries in data. Returns changelog for user display.

    Args:
        review_data: run_review() output
        data: the original extracted data dict (modified in place)

    Returns:
        list of dicts: [{field, old, new, source}]
    """
    changelog = []
    comp = review_data.get("completeness", [])

    for item in comp:
        if item.get("auto_fill") != "是":
            continue
        detail = item.get("_auto_fill_detail")
        if not detail:
            continue

        item_text = item.get("item", "")

        # --- Unit inference ---
        if "缺少单位" in item_text and isinstance(detail, list):
            for pname, unit in detail:
                for p in data.get("params", []):
                    if p.get("name") == pname and not p.get("unit"):
                        old = p.get("unit", "")
                        p["unit"] = unit
                        changelog.append({
                            "field": f"params.{pname}.unit",
                            "old": old, "new": unit,
                            "source": "PARAM_UNIT_PATTERNS推断",
                        })

        # --- Bolt torque ---
        elif "缺少力矩" in item_text and isinstance(detail, list):
            for loc, bsize, torque_val in detail:
                for f in data.get("fasteners", []):
                    floc = str(f.get("location", ""))
                    fspec = str(f.get("spec", ""))
                    ftorque = str(f.get("torque", "")).strip()
                    if (not ftorque or ftorque in ("—", "")) and bsize in fspec and loc in floc:
                        old = f.get("torque", "")
                        f["torque"] = f"{torque_val} [默认]"
                        changelog.append({
                            "field": f"fasteners.{loc}.torque",
                            "old": old, "new": f"{torque_val}Nm",
                            "source": f"BOLT_TORQUE[{bsize}] 8.8级标准",
                        })

        # --- Surface roughness ---
        elif "缺少表面粗糙度" in item_text and isinstance(detail, list):
            surfaces = data.get("tolerances", {}).setdefault("surfaces", [])
            for pname, mat, ra_val in detail:
                surfaces.append({
                    "part": pname,
                    "ra": f"Ra{ra_val}",
                    "process": "",
                    "material_type": mat,
                })
                changelog.append({
                    "field": f"tolerances.surfaces.{pname}",
                    "old": "—", "new": f"Ra{ra_val}",
                    "source": f"SURFACE_RA[{mat}] 默认值",
                })

    return changelog


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
        "auto_fill": sum(1 for c in comp if c.get("auto_fill") == "是"),
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


def render_review(review_data, info, filepath, md5, data=None):
    """将审查结果渲染为 DESIGN_REVIEW.md Markdown 文档。

    Args:
        review_data: run_review() 的返回值
        info: {"name": "子系统名", "prefix": "GIS-XX"}
        filepath: 源设计文档路径
        md5: 源文档 MD5 (12位)
        data: 原始提取数据字典（用于 §E 装配定位统计）

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

    # Section E: 装配定位审查
    if data:
        sections.append("")
        sections.append("## E. 装配定位审查")
        sections.append("")
        part_offsets = data.get("assembly", {}).get("part_offsets", {})
        envelopes = data.get("part_envelopes", {})
        bom_e = data.get("bom")
        total_parts = 0
        if bom_e:
            total_parts = sum(len(a.get("parts", [])) for a in bom_e.get("assemblies", []))
        positioned = len(part_offsets)
        envelope_count = len(envelopes)
        sections.append(f"- 零件总数: {total_parts}")
        sections.append(f"- 有定位数据: {positioned} ({positioned*100//max(total_parts,1)}%)")
        sections.append(f"- 有包络尺寸: {envelope_count} ({envelope_count*100//max(total_parts,1)}%)")
        sections.append("")

    # Summary
    sections.append("## 审查结论")
    sections.append("")
    sections.append(f"- **CRITICAL**: {s['critical']}项 / **WARNING**: {s['warning']}项 / **INFO**: {s['info']}项 / **OK**: {s['ok']}项")

    auto_fill_count = s.get("auto_fill", 0)
    if auto_fill_count > 0:
        sections.append(f"- 可自动补全: **{auto_fill_count}项**（螺栓力矩、单位、粗糙度等）")

    if s["critical"] > 0:
        sections.append("- 建议: **需修正后继续** — 存在阻塞性问题")
    elif s["warning"] > 0:
        sections.append("- 建议: **可继续，但建议先处理 WARNING 项**")
    else:
        sections.append("- 建议: **可继续** — 无阻塞性问题")

    sections.append("")
    if auto_fill_count > 0:
        sections.append("> 用户可选择:")
        sections.append("> 1. 「继续审查」讨论具体问题")
        sections.append("> 2. 「自动补全」计算缺失数据并写入 CAD_SPEC.md")
        sections.append("> 3. 「下一步」按现有数据生成 CAD_SPEC.md")
    else:
        sections.append("> 用户可选择「继续审查」讨论具体问题，或「下一步」生成 CAD_SPEC.md")
    sections.append("")

    return "\n".join(sections)
