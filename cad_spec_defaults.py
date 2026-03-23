#!/usr/bin/env python3
"""
CAD Spec 默认值与完整性检查

提供：
  - 标准默认值（螺栓力矩、公差、粗糙度、密度）
  - 工程常量（屈服强度、最高工作温度、电偶腐蚀、安全系数）
  - 必填项规则（CRITICAL / WARNING / INFO）
  - 派生计算（总重、总成本、BOM完整度）
"""

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
