#!/usr/bin/env python3
"""
CAD Spec 默认值与完整性检查

提供：
  - 标准默认值（螺栓力矩、公差、粗糙度、密度）
  - 工程常量（屈服强度、最高工作温度、电偶腐蚀、安全系数）
  - 必填项规则（CRITICAL / WARNING / INFO）
  - 派生计算（总重、总成本、BOM完整度）
  - 装配定位偏移推算（串联链Z偏移、子总成合并）
"""

import re
import sys

# ─── 标准默认值 ──────────────────────────────────────────────────────────

# 螺栓标准力矩 (Nm)，8.8级，干摩擦
BOLT_TORQUE = {
    "M2": 0.2, "M2.5": 0.4, "M3": 0.7, "M4": 1.5,
    "M5": 3.5, "M6": 9.0, "M8": 22.0, "M10": 44.0, "M12": 77.0,
}

# 通用公差等级
DEFAULT_TOLERANCE = "GB/T 1804-m"

# 表面粗糙度默认值 (Ra, µm)
SURFACE_RA = {
    "铝": 3.2, "7075": 3.2, "6061": 3.2, "Al": 3.2,
    "钢": 3.2, "不锈钢": 1.6, "SUS": 1.6, "Steel": 3.2,
    "PEEK": 1.6, "尼龙": 1.6, "PA": 1.6, "POM": 1.6,
    "黄铜": 1.6, "铜": 1.6, "Cu": 1.6,
    "default": 3.2,
}

# 材料密度 (g/cm³)
MATERIAL_DENSITY = {
    "7075-T6": 2.81, "7075": 2.81, "6061-T6": 2.70, "6061": 2.70,
    "Al": 2.70, "铝": 2.70, "铝合金": 2.80,
    "Steel": 7.85, "钢": 7.85, "不锈钢": 7.93, "SUS316L": 7.98, "SUS304": 7.93,
    "PEEK": 1.31, "尼龙": 1.14, "PA66": 1.14, "POM": 1.41,
    "黄铜": 8.50, "铜": 8.96, "碳纤维": 1.60,
}

# ─── 工程常量（供 cad_spec_reviewer.py 使用） ────────────────────────────

# 材料屈服强度 (MPa)
MATERIAL_YIELD_STRENGTH = {
    "7075-T6": 503, "7075": 503, "6061-T6": 276, "6061": 276,
    "Al": 270, "铝": 270, "铝合金": 280,
    "Steel": 250, "钢": 250, "Q235": 235, "45钢": 355,
    "不锈钢": 215, "SUS316L": 170, "SUS304": 215,
    "PEEK": 100, "PA66": 85, "POM": 70,
    "黄铜": 100, "钨合金": 600, "碳纤维": 600,
}

# 材料最高工作温度 (°C)
MATERIAL_MAX_TEMP = {
    "7075-T6": 150, "7075": 150, "6061-T6": 170, "6061": 170,
    "Al": 150, "铝": 150,
    "Steel": 400, "钢": 400, "不锈钢": 500, "SUS316L": 500, "SUS304": 500,
    "PEEK": 250, "PA66": 80, "POM": 90, "尼龙": 80,
    "硅橡胶": 200, "FKM": 200, "NBR": 100,
    "碳纤维": 150,
}

# 电偶腐蚀风险配对 (材料A, 材料B) → 风险等级 "HIGH"/"MEDIUM"/"LOW"
# 基于 MIL-STD-889 阳极指数差
GALVANIC_PAIRS = {
    ("Al", "Cu"): "HIGH", ("铝", "铜"): "HIGH",
    ("Al", "不锈钢"): "MEDIUM", ("铝", "不锈钢"): "MEDIUM",
    ("Al", "Steel"): "MEDIUM", ("铝", "钢"): "MEDIUM",
    ("Al", "碳纤维"): "HIGH", ("铝", "碳纤维"): "HIGH",
    ("PEEK", "Al"): "LOW", ("PEEK", "Steel"): "LOW",
}

# 安全系数
SAFETY_FACTOR_STATIC = 2.0   # 静载荷
SAFETY_FACTOR_FATIGUE = 3.0  # 疲劳/交变载荷
SAFETY_FACTOR_BRITTLE = 3.5  # 脆性材料

# 螺栓抗剪强度 (MPa) — 按等级
BOLT_SHEAR_STRENGTH = {
    "4.8": 190, "8.8": 380, "10.9": 520, "12.9": 620,
    "A2-70": 280, "A4-70": 280, "A2-80": 380,
}

# 螺栓有效截面积 (mm²) — 应力截面积
BOLT_STRESS_AREA = {
    "M2": 2.07, "M2.5": 3.39, "M3": 5.03, "M4": 8.78,
    "M5": 14.2, "M6": 20.1, "M8": 36.6, "M10": 58.0, "M12": 84.3,
}

# 常见连接方式 regex（供 reviewer B7 校验）
COMMON_CONNECTION_PATTERNS = [
    r"\d+\s*[×xX]\s*M\d+",     # 螺栓组: 4×M3
    r"M\d+",                     # 单螺栓: M3
    r"过盈配合|压入",            # Press fit
    r"H\d+/\w+",                # 配合代号: H7/k6
    r"焊接|点焊|钎焊|laser",    # Welding
    r"粘接|胶粘|Loctite|厌氧",  # Adhesive
    r"卡扣|弹扣|锁扣|ZIF",      # Snap fit
    r"轴承|bearing",             # Bearing
    r"O.*圈|密封|seal",         # O-ring/seal
    r"弹簧销|定位销|销|pin",    # Pin
    r"嵌入|压紧|锁紧|夹紧",    # Insert/clamp
    r"螺纹|旋入|拧入",          # Thread
    r"键|花键|spline",          # Key/spline
    r"铆|rivet",                 # Rivet
    r"Φ\d+",                    # Diameter spec (pin/shaft)
    r"碟簧|弹簧垫圈",           # Spring washer
]

# 承载结构件中较弱的连接方式
WEAK_LOAD_CONNECTIONS = [r"粘接|胶粘|Loctite", r"卡扣|弹扣"]

# 参数名→单位推断 (用于自动补全)
PARAM_UNIT_PATTERNS = {
    r"_OD$|_ID$|_DIA$|_W$|_H$|_L$|_THICK$|_R$|_GAP$": "mm",
    r"WEIGHT|MASS": "g",
    r"ANGLE|θ|DEG": "°",
    r"FORCE|_F$": "N",
    r"TORQUE|_T$": "Nm",
    r"TEMP|温度": "°C",
    r"SPEED|RPM": "rpm",
    r"VOLTAGE|_V$": "V",
    r"CURRENT|_A$|_I$": "A",
}

# ─── 标准件外形尺寸（供简化 CadQuery 几何生成使用）──────────────────────
# 格式: "型号关键词" → {"d": 直径mm, "l": 长度mm, ...}
# 对于方形件: {"w": 宽, "h": 高, "l": 长}

STD_PART_DIMENSIONS = {
    # --- Motors ---
    "ECX SPEED 22": {"d": 22, "l": 68, "shaft_d": 4, "shaft_l": 14},
    "ECX 22":       {"d": 22, "l": 55, "shaft_d": 4, "shaft_l": 14},
    "ECX 16":       {"d": 16, "l": 44, "shaft_d": 3, "shaft_l": 10},
    "DC 3V":        {"d": 16, "l": 30, "shaft_d": 2, "shaft_l": 8},
    "DC Φ16":       {"d": 16, "l": 30, "shaft_d": 2, "shaft_l": 8},
    # --- Reducers / Gearboxes ---
    "GP22C":        {"d": 22, "l": 35, "shaft_d": 6, "shaft_l": 10},
    "GP22":         {"d": 22, "l": 30, "shaft_d": 4, "shaft_l": 10},
    "GP32":         {"d": 32, "l": 45, "shaft_d": 6, "shaft_l": 12},
    "GP42":         {"d": 42, "l": 55, "shaft_d": 8, "shaft_l": 15},
    # --- Disc Springs (DIN 2093) ---
    "DIN 2093 A6":  {"od": 12.5, "id": 6.2, "t": 0.7, "h": 0.85},
    "DIN 2093 A8":  {"od": 16, "id": 8.2, "t": 0.8, "h": 1.0},
    "DIN 2093 A10": {"od": 20, "id": 10.2, "t": 1.0, "h": 1.15},
    # --- Bearings ---
    "MR105ZZ":      {"od": 10, "id": 5, "w": 4},
    "MR115ZZ":      {"od": 11, "id": 5, "w": 4},
    "MR128ZZ":      {"od": 12, "id": 8, "w": 3.5},
    "688ZZ":        {"od": 16, "id": 8, "w": 5},
    "608ZZ":        {"od": 22, "id": 8, "w": 7},
    # --- Sensors ---
    "ATI Nano17":   {"d": 17, "l": 14.5},
    "KWR42":        {"d": 42, "l": 20},
    "TWAE-03":      {"d": 28, "l": 26},
    "I300-UHF":     {"d": 45, "l": 60},
    # --- Connectors ---
    "LEMO FGG.0B":  {"d": 10, "l": 30},
    "LEMO EGG.0B":  {"d": 12, "l": 20},
    "SMA":          {"d": 6.5, "l": 15},
    "Molex ZIF":    {"w": 12, "h": 3, "l": 8},
    "Molex 5052":   {"w": 12, "h": 3, "l": 8},
    "Molex 15168":  {"w": 12, "h": 1, "l": 30},  # stub (connector portion only)
    # --- Pumps ---
    "齿轮泵":       {"w": 30, "h": 25, "l": 40},
    "微量泵":       {"w": 20, "h": 15, "l": 30},
    "电磁阀":       {"w": 20, "h": 15, "l": 30},
    # --- Linear Bearings ---
    "LM6UU":   {"od": 12, "id": 6, "w": 19},
    "LM8UU":   {"od": 15, "id": 8, "w": 24},
    "LM10UU":  {"od": 19, "id": 10, "w": 29},
    "LM12UU":  {"od": 21, "id": 12, "w": 30},
    # --- More Deep Groove Bearings (ISO 15) ---
    "6000ZZ":  {"od": 26, "id": 10, "w": 8},
    "6001ZZ":  {"od": 28, "id": 12, "w": 8},
    "6200ZZ":  {"od": 30, "id": 10, "w": 9},
    "6201ZZ":  {"od": 32, "id": 12, "w": 10},
    # --- NEMA Stepper Motors ---
    "NEMA 17": {"w": 42.3, "h": 42.3, "l": 48, "shaft_d": 5, "shaft_l": 24},
    "NEMA 23": {"w": 57, "h": 57, "l": 56, "shaft_d": 6.35, "shaft_l": 24},
    # --- Additional Tanks ---
    "_tank_small": {"d": 25, "l": 110},
    "_tank_large": {"d": 38, "l": 280},
    # --- Generic fallbacks by category ---
    "_motor":       {"d": 22, "l": 50, "shaft_d": 4, "shaft_l": 12},
    "_reducer":     {"d": 25, "l": 35, "shaft_d": 6, "shaft_l": 10},
    "_spring":      {"od": 10, "id": 5, "t": 0.7, "h": 0.85},
    "_bearing":     {"od": 12, "id": 6, "w": 4},
    "_sensor":      {"d": 15, "l": 12},
    "_pump":        {"w": 30, "h": 25, "l": 40},
    "_connector":   {"d": 10, "l": 25},
    "_seal":        {"od": 80, "id": 75, "section_d": 2.4},
    "_tank":        {"d": 38, "l": 280},
    "_locating":     {"d": 3,  "l": 10},
    "_elastic":      {"d": 20, "l": 30},
    "_transmission": {"od": 30, "w": 8, "id": 6},
}

MATERIAL_PROPS = {
    "7075-T6":  {"density": 2.81, "color": (0.15, 0.15, 0.15), "ra_default": 3.2, "material_type": "al"},
    "6063":     {"density": 2.69, "color": (0.20, 0.20, 0.20), "ra_default": 3.2, "material_type": "al"},
    "6061-T6":  {"density": 2.70, "color": (0.18, 0.18, 0.18), "ra_default": 3.2, "material_type": "al"},
    "PEEK":     {"density": 1.31, "color": (0.85, 0.65, 0.13), "ra_default": 3.2, "material_type": "peek"},
    "SUS316L":  {"density": 7.98, "color": (0.82, 0.82, 0.85), "ra_default": 1.6, "material_type": "steel"},
    "SUS304":   {"density": 7.93, "color": (0.80, 0.80, 0.83), "ra_default": 1.6, "material_type": "steel"},
    "SUS303":   {"density": 7.90, "color": (0.78, 0.78, 0.80), "ra_default": 1.6, "material_type": "steel"},
    "FKM":      {"density": 1.80, "color": (0.08, 0.08, 0.08), "ra_default": 6.3, "material_type": "rubber"},
    "PA66":     {"density": 1.14, "color": (0.10, 0.10, 0.10), "ra_default": 3.2, "material_type": "plastic"},
    "POM":      {"density": 1.41, "color": (0.90, 0.88, 0.85), "ra_default": 1.6, "material_type": "plastic"},
    "硅橡胶":   {"density": 1.10, "color": (0.75, 0.60, 0.45), "ra_default": 6.3, "material_type": "rubber"},
}


def _parse_dims_from_text(text: str) -> dict:
    """Extract dimensions from free-text material/model fields.

    Recognizes patterns commonly found in BOM material columns:
      Φ38×280mm  → {"d": 38, "l": 280}
      Φ80×2.4    → {"d": 80, "l": 2.4}   (O-ring: od × section)
      120×100×55mm → {"w": 120, "h": 100, "l": 55}
      Φ25mm      → {"d": 25}
      20芯×500mm → {"l": 500}  (cable length)
    """
    import re
    # Pattern 0: Φ_OD_×Φ_ID_×W (bearing: OD × ID × width, e.g. Φ10×Φ5×4mm)
    m = re.search(r'[Φφ]\s*(\d+(?:\.\d+)?)\s*[×x×]\s*[Φφ]\s*(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)', text)
    if m:
        return {"od": float(m.group(1)), "id": float(m.group(2)), "w": float(m.group(3))}

    # Pattern 1: Φd×l (cylinder: diameter × length)
    m = re.search(r'[Φφ]\s*(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)', text)
    if m:
        return {"d": float(m.group(1)), "l": float(m.group(2))}

    # Pattern 2: w×h×l (box: three dimensions)
    m = re.search(r'(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)\s*mm', text)
    if m:
        return {"w": float(m.group(1)), "h": float(m.group(2)), "l": float(m.group(3))}

    # Pattern 3: Φd alone (just diameter)
    m = re.search(r'[Φφ]\s*(\d+(?:\.\d+)?)\s*mm', text)
    if m:
        return {"d": float(m.group(1))}

    # Pattern 4: N芯×Lmm (cable: count × length)
    m = re.search(r'\d+芯\s*[×x×]\s*(\d+)\s*mm', text)
    if m:
        return {"d": 10, "l": min(float(m.group(1)), 50)}  # cap cable to stub

    return {}


def lookup_std_part_dims(name: str, material: str = "", category: str = "") -> dict:
    """Look up standard part dimensions from name/material/model text.

    Resolution order:
      1. Specific model match in STD_PART_DIMENSIONS (e.g. "GP22C", "MR105ZZ")
      2. Regex extraction from material/model text (e.g. Φ25×110mm → d=25, l=110)
      3. Category fallback (e.g. _tank → d=38, l=280)

    Returns dict with dimensional keys (d, l, w, h, od, id, etc.) or empty dict.
    """
    text = name + " " + material
    # Pass 1: Try specific model matches
    for key, dims in STD_PART_DIMENSIONS.items():
        if key.startswith("_"):
            continue  # Skip generic fallbacks in first pass
        if key.upper() in text.upper():
            return dict(dims)  # Return copy

    # Pass 2: Try regex extraction from material/model text
    parsed = _parse_dims_from_text(text)
    if parsed:
        return parsed

    # Pass 3: Category fallback
    if category:
        fallback_key = f"_{category}"
        if fallback_key in STD_PART_DIMENSIONS:
            return dict(STD_PART_DIMENSIONS[fallback_key])
    return {}


def compute_serial_offsets(placements: list, envelopes: dict,
                           connections: list = None) -> dict:
    """从串联堆叠链计算零件底面偏移（工位局部坐标）。

    Direction-aware: supports (0,0,-1), (0,0,+1), (1,0,0), etc.
    Bottom-face convention: returned Z = translate parameter = part bottom face position.

    Returns: {part_no: {"z": float, "h": float, "mode": str, "source": str, "confidence": str}}
    """
    result = {}

    for placement in placements:
        if placement.get("mode") != "axial_stack":
            continue
        chain = placement.get("chain", [])
        if not chain:
            continue

        # Defense-in-depth: even if BOM matching produced a cross-assembly
        # part_no (e.g. chain in GIS-EE-003 matched GIS-EE-001-04), we only
        # accept result writes for parts whose part_no is prefixed by the
        # chain's own assembly_pno. This guarantees chain-local Z values
        # never pollute another assembly's positioning table.
        chain_assy = placement.get("assembly", "")

        d = placement.get("direction", (0, 0, -1))
        # Determine primary axis sign
        if abs(d[2]) >= abs(d[0]) and abs(d[2]) >= abs(d[1]):
            sign = -1 if d[2] < 0 else 1
        elif abs(d[0]) >= abs(d[1]):
            sign = -1 if d[0] < 0 else 1
        else:
            sign = -1 if d[1] < 0 else 1

        # Merge consecutive sub_assembly nodes
        merged = _merge_sub_assemblies(chain, envelopes)

        # Track per-part top/bottom across this chain. A single BOM part
        # may correspond to multiple chain nodes (e.g. 弹簧限力机构 has
        # 上端板 + 弹簧 + 下端板 sub-nodes that all match the same BOM
        # entry). The visible envelope is the union of all sub-spans:
        #   top    = max(node_top)     (least negative for downward stack)
        #   bottom = min(node_bottom)  (most negative)
        # We accumulate top/bottom and emit a single span at the end.
        chain_spans = {}  # pno → {"top": float, "bottom": float}

        cursor = 0.0
        for i, node in enumerate(merged):
            pno = node.get("part_no")

            # Skip connection-only nodes — they describe fastener specs
            # between physical parts, not stack layers (e.g. "[4×M3螺栓]").
            # Also skip reference surfaces that failed BOM matching.
            if not pno and not node.get("dims"):
                continue

            h = _get_node_height(node, envelopes)

            # axial_gap from connections
            # TODO(P3): axial_gap is not yet populated by extract_connection_matrix;
            # this logic is ready but currently always gets gap=0.0
            gap = 0.0
            if connections and i > 0:
                prev_pno = merged[i - 1].get("part_no")
                if prev_pno and pno:
                    for conn in connections:
                        pa, pb = conn.get("partA", ""), conn.get("partB", "")
                        # Use regex extraction to avoid substring false positives
                        # (e.g. "GIS-EE-001" matching "GIS-EE-001-01")
                        pa_pnos = set(re.findall(r"[A-Z]+-[A-Z]+-\d+(?:-\d+)?", pa))
                        pb_pnos = set(re.findall(r"[A-Z]+-[A-Z]+-\d+(?:-\d+)?", pb))
                        if ((prev_pno in pa_pnos and pno in pb_pnos) or
                            (pno in pa_pnos and prev_pno in pb_pnos)):
                            gap = conn.get("axial_gap", 0.0)
                            break

            if sign < 0:
                cursor -= abs(gap)
                top = cursor
                bottom = cursor - h
            else:
                cursor += abs(gap)
                bottom = cursor
                top = cursor + h

            # Accumulate sub-chain span for this part (only within this
            # chain's assembly to prevent cross-assembly pollution).
            if pno and (not chain_assy or pno.startswith(chain_assy)):
                span = chain_spans.setdefault(
                    pno, {"top": top, "bottom": bottom})
                span["top"] = max(span["top"], top)
                span["bottom"] = min(span["bottom"], bottom)

            # Advance cursor
            if sign < 0:
                cursor = bottom
            else:
                cursor += h

        # Emit one result entry per part with span-based height
        for pno, span in chain_spans.items():
            result[pno] = {
                "z": round(span["bottom"], 1),
                "h": round(span["top"] - span["bottom"], 1),
                "mode": "axial_stack",
                "source": "serial_chain",
                "confidence": "high",
            }

    return result


def _merge_sub_assemblies(chain: list, envelopes: dict) -> list:
    """Merge consecutive nodes with same sub_assembly into single unit."""
    merged = []
    i = 0
    while i < len(chain):
        node = chain[i]
        sa = node.get("sub_assembly")
        if sa:
            group = [node]
            j = i + 1
            while j < len(chain) and chain[j].get("sub_assembly") == sa:
                group.append(chain[j])
                j += 1
            total_h = sum(_get_node_height(n, envelopes) for n in group)
            merged.append({
                "part_name": f"{sa}(merged)",
                "part_no": sa,
                "dims": {"type": "cylinder", "h": total_h, "source": "chain(merged)"},
                "connection": group[0].get("connection"),
                "sub_assembly": None,
            })
            i = j
        else:
            merged.append(node)
            i += 1
    return merged


def _get_node_height(node: dict, envelopes: dict) -> float:
    """Get height from node dims, then envelopes, then default 20mm."""
    dims = node.get("dims")
    if dims:
        h = dims.get("h", dims.get("l", 0.0))
        if h > 0:
            return h
    pno = node.get("part_no")
    if pno and pno in envelopes:
        return envelopes[pno].get("h", 20.0)
    return 20.0


# ─── 材质分类 ────────────────────────────────────────────────────────────

MATERIAL_TYPE_KEYWORDS = {
    "al":     ["铝", "Al", "7075", "6061", "6063", "2024", "5052",
               "铝合金", "aluminum", "aluminium"],
    "steel":  ["钢", "Steel", "SUS", "不锈钢", "Q235", "45钢",
               "碳钢", "合金钢", "弹簧钢", "stainless"],
    "peek":   ["PEEK"],
    "nylon":  ["尼龙", "PA66", "PA6", "POM", "塑料", "ABS",
               "PC", "Nylon", "nylon"],
    "rubber": ["硅橡胶", "FKM", "NBR", "EPDM", "橡胶",
               "Shore", "rubber", "silicone"],
}

_merged_keywords = None


def get_material_type_keywords():
    """返回基础 + SW 扩展的关键词路由表。首次调用时合并，缓存结果。

    无 SW 时返回值与 MATERIAL_TYPE_KEYWORDS 内容一致。
    """
    global _merged_keywords
    if _merged_keywords is not None:
        return _merged_keywords
    _merged_keywords = {k: list(v) for k, v in MATERIAL_TYPE_KEYWORDS.items()}
    if sys.platform == "win32":
        try:
            from adapters.solidworks.sw_material_bridge import load_sw_material_bundle
            bundle = load_sw_material_bundle()
            if bundle:
                for mtype, kws in bundle.type_keywords.items():
                    if mtype in _merged_keywords:
                        existing = {kw.lower() for kw in _merged_keywords[mtype]}
                        for kw in kws:
                            if kw.lower() not in existing:
                                _merged_keywords[mtype].append(kw)
                    else:
                        _merged_keywords[mtype] = list(kws)
        except ImportError:
            pass
    return _merged_keywords


def _reset_material_cache():
    """测试用：重置缓存。"""
    global _merged_keywords
    _merged_keywords = None


def classify_material_type(material: str):
    """从 BOM material 字段推断 material_type。

    遍历 get_material_type_keywords() 查找关键词匹配。
    无匹配时返回 None（不静默 fallback）。

    Returns:
        "al" | "steel" | "peek" | "nylon" | "rubber" | None
    """
    if not material:
        return None
    for mtype, keywords in get_material_type_keywords().items():
        if any(kw.lower() in material.lower() for kw in keywords):
            return mtype
    return None


# ─── material_type → render preset 映射 ──────────────────────────────────

MATERIAL_TYPE_TO_DEFAULT_PRESET = {
    "al":     "brushed_aluminum",
    "steel":  "dark_steel",
    "peek":   "peek_amber",
    "nylon":  "white_nylon",
    "rubber": "black_rubber",
}


def default_preset_for_material_type(material_type: str) -> str:
    """material_type → 默认 render preset 名称。

    用于 prompt_data_builder.py 运行时 fallback：当 render_config.json
    缺少 materials 配置时，从 params.py 的 material_type 自动推导 preset。

    Returns:
        MATERIAL_PRESETS 中的 key（如 "brushed_aluminum"）
    """
    return MATERIAL_TYPE_TO_DEFAULT_PRESET.get(material_type, "brushed_aluminum")


# ─── 零件编号通用前缀剥离 ────────────────────────────────────────────────

def strip_part_prefix(part_no: str) -> str:
    """通用前缀剥离：去掉第一段（首个 '-' 之前）。

    GIS-EE-001-01   → EE-001-01
    ACME-PLT-002-03 → PLT-002-03
    NOPREFIX         → NOPREFIX (无 '-' 则原样返回)
    """
    idx = part_no.find("-")
    return part_no[idx + 1:] if idx >= 0 else part_no


# ─── 必填项规则 ──────────────────────────────────────────────────────────

# 每节的完整性规则：(条件函数, 严重度, 缺失描述, 建议)
REQUIRED_RULES = [
    # §1 参数
    {
        "section": "§1 全局参数表",
        "check": lambda data: len(data.get("params", [])) >= 5,
        "severity": "CRITICAL",
        "missing": "尺寸参数不足5个",
        "suggestion": "请在设计文档中补充完整的参数表（至少含5个关键尺寸）",
    },
    {
        "section": "§1 全局参数表",
        "check": lambda data: any(
            p["name"] in ("WEIGHT", "TOTAL_WEIGHT") or "WEIGHT" in p["name"]
            for p in data.get("params", [])),
        "severity": "WARNING",
        "missing": "缺少重量预算参数",
        "suggestion": "在参数表中添加 '总重量' 行",
        "default": "由BOM计算派生",
    },
    {
        "section": "§1 全局参数表",
        "check": lambda data: any(
            any(k in p["name"] for k in ("OD", "W", "H", "L", "DIA", "ENVELOPE"))
            for p in data.get("params", [])),
        "severity": "WARNING",
        "missing": "缺少包络尺寸参数",
        "suggestion": "添加外径/宽/高/长等包络尺寸",
    },
    # §5 BOM
    {
        "section": "§5 BOM树",
        "check": lambda data: data.get("bom") is not None,
        "severity": "CRITICAL",
        "missing": "未找到BOM表",
        "suggestion": "请在 §X.8 添加BOM章节，模板: docs/templates/bom_section_template.md",
    },
    # §6 装配
    {
        "section": "§6 装配姿态与定位",
        "check": lambda data: len(data.get("assembly", {}).get("coord_sys", [])) > 0,
        "severity": "WARNING",
        "missing": "缺少坐标系定义",
        "suggestion": "在 §X.10.0 添加装配姿态定义表（术语|定义|等价表述）",
        "default": "使用标准坐标系：Z=垂直向上, X=水平向右, Y=水平向前",
    },
    {
        "section": "§6 装配姿态与定位",
        "check": lambda data: len(data.get("assembly", {}).get("layers", [])) > 0,
        "severity": "WARNING",
        "missing": "缺少装配层叠表",
        "suggestion": "在 §X.10.1 添加装配层叠表（层级|零件|固定/运动|连接方式|偏移）",
    },
    # §2 公差
    {
        "section": "§2 公差与表面处理",
        "check": lambda data: len(data.get("tolerances", {}).get("dim_tols", [])) > 0,
        "severity": "INFO",
        "missing": "未提取到尺寸公差",
        "suggestion": "在参数表中补充公差列，或添加独立公差表",
        "default": DEFAULT_TOLERANCE,
    },
    # §3 紧固件
    {
        "section": "§3 紧固件清单",
        "check": lambda data: len(data.get("fasteners", [])) > 0,
        "severity": "INFO",
        "missing": "未提取到紧固件信息",
        "suggestion": "在设计文档中明确螺栓规格和力矩要求",
    },
    # §7 视觉标识
    {
        "section": "§7 视觉标识",
        "check": lambda data: len(data.get("visual_ids", [])) > 0,
        "severity": "INFO",
        "missing": "缺少视觉标识表",
        "suggestion": "在 §X.10.2 添加视觉标识表（零件|材质|颜色|唯一标签|尺寸|方向约束）",
        "default": "从BOM生成骨架",
    },
    # §8 渲染规划
    {
        "section": "§8 渲染规划",
        "check": lambda data: (len(data.get("render_plan", {}).get("groups", [])) > 0 or
                               len(data.get("render_plan", {}).get("views", [])) > 0),
        "severity": "INFO",
        "missing": "缺少渲染规划数据",
        "suggestion": "在 §X.10.3~5 添加迭代分组/视角/否定约束表",
        "default": "使用标准5视角方案",
    },
]


# ─── 默认值填充 ──────────────────────────────────────────────────────────

def fill_fastener_defaults(fasteners: list) -> list:
    """为缺少力矩的紧固件填入标准力矩默认值。"""
    import re
    for f in fasteners:
        if not f.get("torque"):
            m = re.match(r"(M\d+(?:\.\d+)?)", f.get("spec", ""))
            if m:
                bolt_size = m.group(1)
                if bolt_size in BOLT_TORQUE:
                    f["torque"] = f"{BOLT_TORQUE[bolt_size]} [默认]"
    return fasteners


def fill_surface_defaults(surfaces: list) -> list:
    """为缺少 Ra 的零件根据材料填默认粗糙度。"""
    for s in surfaces:
        if not s.get("ra") or s["ra"] == "[待定]":
            mat = s.get("material_type", "")
            for key, val in SURFACE_RA.items():
                if key in mat:
                    s["ra"] = f"Ra{val} [默认]"
                    break
            else:
                s["ra"] = f"Ra{SURFACE_RA['default']} [默认]"
    return surfaces


# ─── 派生计算 ─────────────────────────────────────────────────────────────

def compute_derived(data: dict) -> list:
    """从已提取数据计算派生量。

    Returns:
        [{name, value, unit, tol, source, remark, cn_name}]
    """
    derived = []

    bom = data.get("bom")
    if bom:
        summary = bom.get("summary", {})
        total_cost = summary.get("total_cost", 0)
        if total_cost > 0:
            derived.append({
                "name": "TOTAL_COST", "value": str(total_cost),
                "unit": "元", "tol": "", "source": "[计算]",
                "remark": f"BOM合计 ({summary.get('total_parts', 0)}零件)",
                "cn_name": "BOM总成本",
            })

        total_parts = summary.get("total_parts", 0)
        assemblies = summary.get("assemblies", 0)
        derived.append({
            "name": "BOM_PARTS_COUNT", "value": str(total_parts),
            "unit": "", "tol": "", "source": "[计算]",
            "remark": f"{assemblies}总成",
            "cn_name": "BOM零件总数",
        })

        # BOM completeness
        total_cells = filled_cells = 0
        for assy in bom.get("assemblies", []):
            for part in assy.get("parts", []):
                for key in ("material", "make_buy", "unit_price"):
                    total_cells += 1
                    if part.get(key) and str(part[key]) not in ("", "0", "0.0"):
                        filled_cells += 1
        if total_cells > 0:
            completeness = round(filled_cells / total_cells * 100, 1)
            derived.append({
                "name": "BOM_COMPLETENESS", "value": str(completeness),
                "unit": "%", "tol": "", "source": "[计算]",
                "remark": f"{filled_cells}/{total_cells} cells filled",
                "cn_name": "BOM完整度",
            })

    return derived


# ─── 完整性检查 ──────────────────────────────────────────────────────────

def check_completeness(data: dict) -> list:
    """运行全部完整性规则，返回缺失项列表。

    Returns:
        [{id, section, missing, severity, default, suggestion}]
    """
    issues = []
    idx = 1
    for rule in REQUIRED_RULES:
        try:
            passed = rule["check"](data)
        except Exception:
            passed = False
        if not passed:
            issues.append({
                "id": f"M{idx:02d}",
                "section": rule["section"],
                "missing": rule["missing"],
                "severity": rule["severity"],
                "default": rule.get("default", "—"),
                "suggestion": rule["suggestion"],
            })
            idx += 1

    return issues
