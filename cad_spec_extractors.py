#!/usr/bin/env python3
"""
CAD Spec 提取器 — 从设计文档 Markdown 提取 7 类结构化数据

8 个提取函数 + 通用表格解析器，供 cad_spec_gen.py 调用。
"""

import re
import sys
from pathlib import Path
from typing import Optional

# ─── 中文→UPPER_CASE 参数名映射 ──────────────────────────────────────────

CN_PARAM = {
    # Geometry — specific compound forms first (longest match wins)
    "总厚度": "TOTAL_THICK", "铝合金段厚度": "AL_THICK", "铝合金段": "AL_THICK",
    "外接圆直径": "ENVELOPE_DIA", "本体外径": "BODY_OD", "本体内径": "BODY_ID",
    "本体厚度": "BODY_THICK", "法兰外径": "FLANGE_OD", "法兰内径": "FLANGE_ID",
    "法兰总厚度": "FLANGE_TOTAL_THICK", "法兰厚度": "FLANGE_THICK",
    "悬臂截面厚度": "ARM_SEC_THICK", "悬臂截面宽度": "ARM_SEC_W",
    "悬臂长度": "ARM_L", "截面厚度": "SEC_THICK", "截面宽度": "SEC_W",
    "台阶高度": "STEP_H", "安装半径": "MOUNT_R", "爬电距离": "CREEP_D",
    "销孔径": "PIN_BORE", "销直径": "PIN_DIA", "孔数": "HOLE_N",
    "外形尺寸": "ENVELOPE", "包络尺寸": "ENVELOPE",
    "安装面尺寸": "MOUNT_FACE", "安装面": "MOUNT_FACE",
    "安装孔": "MOUNT_BORE", "安装尺寸": "MOUNT_DIM", "腔体尺寸": "CAVITY",
    "定位销配合": "PIN_FIT", "弹簧销孔": "SPRING_PIN_BORE",
    "螺栓PCD": "BOLT_PCD", "固定螺栓PCD": "BOLT_PCD",
    "安装面粗糙度": "MOUNT_RA", "安装面平面度": "MOUNT_FLAT",
    # Geometry — primitives
    "外径": "OD", "内径": "ID", "厚度": "THICK", "宽度": "W",
    "高度": "H", "长度": "L", "直径": "DIA", "半径": "R",
    "壁厚": "WALL", "重量": "WEIGHT",
    "深度": "DEPTH", "槽宽": "SLOT_W", "槽深": "SLOT_D",
    "孔径": "BORE", "孔深": "BORE_D", "倒角": "CHAMFER",
    "圆角": "FILLET", "螺距": "THREAD_P", "间距": "PITCH", "节距": "PCD",
    # Motion / mechanical
    "旋转范围": "ROT_RANGE", "旋转分度": "INDEX", "分度": "INDEX",
    "切换时间": "SWITCH_T", "定位精度": "POS_ACC", "角度": "ANGLE",
    "行程": "STROKE", "负载": "LOAD", "传动比": "RATIO",
    "额定扭矩": "RATED_TORQUE", "堵转扭矩": "STALL_TORQUE", "力矩": "TORQUE",
    "速度": "SPEED", "加速度": "ACCEL", "转速": "RPM",
    "弹簧力": "SPRING_F", "齿数": "TEETH", "模数": "MODULE",
    # Electrical / environment
    "绝缘电阻": "INSUL_R", "耐压": "WITHSTAND_V", "粗糙度": "RA",
    "工作温度": "WORK_TEMP", "温度": "TEMP",
    "电压": "VOLTAGE", "频率": "FREQ", "功耗": "POWER",
    "容量": "CAPACITY", "压力": "PRESSURE", "流量": "FLOW",
    "阻抗": "IMPEDANCE", "增益": "GAIN", "灵敏度": "SENSITIVITY",
}


def _cn_to_upper(cn_name: str, context: str = "", line_no: int = 0) -> str:
    """将中文参数名映射为 UPPER_CASE 英文名。

    策略：
    1. 在 CN_PARAM 中查找最长匹配的中文关键词
    2. 上下文前缀（如 "工位2"→S2_，"法兰"→FLANGE_）
    3. 回退：PARAM_L{行号}
    """
    # 上下文前缀
    prefix = ""
    ctx_patterns = [
        (r"工位\s*(\d)", lambda m: f"S{m.group(1)}_"),
        (r"悬臂", lambda m: "ARM_"),
        (r"法兰", lambda m: "FLANGE_"),
        (r"适配", lambda m: "ADAPTER_"),
        (r"电机", lambda m: "MOTOR_"),
        (r"弹簧", lambda m: "SPRING_"),
        (r"传感器", lambda m: "SENSOR_"),
        (r"支架", lambda m: "BRACKET_"),
        (r"壳体", lambda m: "HOUSING_"),
        (r"清洁", lambda m: "CLEANER_"),
        (r"涂抹", lambda m: "APPLICATOR_"),
        (r"储液", lambda m: "TANK_"),
        (r"信号调理", lambda m: "SIGCOND_"),
    ]
    # Search cn_name first for prefix (prevents remark context from overriding part type)
    for pat, fn in ctx_patterns:
        m_ctx = re.search(pat, cn_name)
        if m_ctx:
            prefix = fn(m_ctx)
            break
    if not prefix:
        for pat, fn in ctx_patterns:
            m_ctx = re.search(pat, context)
            if m_ctx:
                prefix = fn(m_ctx)
                break

    # 查找最长匹配
    best_key = ""
    for cn_key in sorted(CN_PARAM.keys(), key=len, reverse=True):
        if cn_key in cn_name:
            best_key = cn_key
            break

    if best_key:
        suffix = CN_PARAM[best_key]
        # Avoid double-prefix: if suffix already starts with the prefix, drop the prefix
        if prefix and suffix.startswith(prefix.rstrip("_")):
            result = suffix
        else:
            result = prefix + suffix
    elif line_no > 0:
        result = f"{prefix}PARAM_L{line_no}" if prefix else f"PARAM_L{line_no}"
    else:
        # Transliterate: keep alphanumeric, replace rest with _
        clean = re.sub(r"[^\w]", "_", cn_name).strip("_").upper()
        result = prefix + clean if clean else f"{prefix}UNNAMED"

    return result


# ─── 通用表格解析器 ──────────────────────────────────────────────────────

def extract_tables(lines: list, heading_pattern: str = None,
                   column_keywords: list = None,
                   stop_at_heading: bool = True) -> list:
    """从 Markdown 行列表中提取表格。

    Args:
        lines: 文档行列表（str）
        heading_pattern: 可选，正则——只提取此标题下的表格
        column_keywords: 可选，表头须含全部关键词才匹配
        stop_at_heading: 遇到下一个 # 标题时停止

    Returns:
        [{"heading": str, "columns": [str], "rows": [[str]], "start_line": int}]
    """
    results = []
    in_section = heading_pattern is None  # 无标题过滤 → 全文搜索
    current_heading = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Track section headings
        if line.startswith("#"):
            current_heading = line.lstrip("#").strip()
            if heading_pattern is not None:
                in_section = bool(re.search(heading_pattern, line))
            elif results and stop_at_heading:
                # already found a table, new heading → might still find more
                pass

        # Detect table header row
        if in_section and "|" in line and not re.match(r"\s*\|[\s\-:|]+\|$", line):
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]

            if len(cells) < 2:
                i += 1
                continue

            # Check column keyword filter
            if column_keywords:
                header_text = "|".join(cells).lower()
                if not all(kw.lower() in header_text for kw in column_keywords):
                    i += 1
                    continue

            # Found a matching table header
            columns = cells
            start_line = i + 1  # 1-based

            # Skip separator
            i += 1
            if i < len(lines) and re.match(r"\s*\|[\s\-:|]+\|", lines[i]):
                i += 1

            # Parse data rows
            rows = []
            while i < len(lines):
                row = lines[i].strip()
                if row.startswith("#") and stop_at_heading:
                    break
                if not row.startswith("|"):
                    if row == "" or row.startswith(">"):
                        i += 1
                        continue
                    # Non-table, non-blank → end of table
                    break
                if re.match(r"\s*\|[\s\-:|]+\|$", row):
                    i += 1
                    continue
                rcells = [c.strip() for c in row.split("|")]
                rcells = [c for c in rcells if c != ""]
                if rcells:
                    rows.append(rcells)
                i += 1

            results.append({
                "heading": current_heading,
                "columns": columns,
                "rows": rows,
                "start_line": start_line,
            })
            continue

        i += 1

    return results


# ─── 值解析工具 ──────────────────────────────────────────────────────────

_NUM_UNIT_RE = re.compile(
    r"[Φφ]?\s*([\d.]+)\s*"
    r"(mm|cm|m|°|deg|g|kg|N|Nm|V|A|W|kHz|MHz|GHz|Hz|pC|dB|μm|Ω|mΩ|kΩ|MΩ|pF|nF|μF|mA|mV|s|ms|μs|min|h|℃|°C|MPa|GPa|kPa|rpm|r/min|L|mL|%)?"
)

_TOL_RE = re.compile(
    r"([±]\s*[\d.]+\s*(?:mm|°|μm)?)|"           # ±0.1mm
    r"(\+[\d.]+\s*/\s*[0\-][\d.]*\s*(?:mm)?)|"   # +0.021/0mm (H7)
    r"([Hh]\d+[/\\][a-z]\d+)|"                    # H7/g6
    r"(GB/T\s*\d+[-‐]\w+)"                        # GB/T 1804-m
)


def _parse_value_unit(text: str) -> tuple:
    """Extract (value_str, unit) from a cell like 'Φ90mm', '24V', '75kg'."""
    text = text.replace("，", ",").strip()
    m = _NUM_UNIT_RE.search(text)
    if m:
        return m.group(1), m.group(2) or ""
    return text, ""


def _parse_tolerance(text: str) -> str:
    """Extract tolerance string from a cell."""
    m = _TOL_RE.search(text)
    return m.group(0).strip() if m else ""


# ─── 1. 参数提取 ─────────────────────────────────────────────────────────

def extract_params(lines: list) -> list:
    """提取所有含 '参数|设计值' 或 '尺寸|值' 列的表格中的数值参数。

    Returns:
        [{name, value, unit, tol, source, remark}]
    """
    # Find tables with parameter-like columns
    kw_sets = [
        ["参数", "设计值"],
        ["参数", "值"],
        ["尺寸", "设计值"],
        ["尺寸", "值"],
        ["尺寸参数"],
    ]
    tables = []
    for kws in kw_sets:
        tables.extend(extract_tables(lines, column_keywords=kws))

    # Deduplicate by start_line
    seen = set()
    unique_tables = []
    for t in tables:
        if t["start_line"] not in seen:
            seen.add(t["start_line"])
            unique_tables.append(t)

    params = []
    for tbl in unique_tables:
        tbl_heading = tbl.get("heading", "")
        cols_lower = [c.lower() for c in tbl["columns"]]
        # Find key column indices
        param_idx = next((i for i, c in enumerate(cols_lower)
                          if "参数" in c or "尺寸" in c), 0)
        val_idx = next((i for i, c in enumerate(cols_lower)
                        if "设计值" in c or "值" in c or "设计" in c), 1)
        tol_idx = next((i for i, c in enumerate(cols_lower)
                        if "公差" in c or "偏差" in c), -1)
        remark_idx = next((i for i, c in enumerate(cols_lower)
                           if "说明" in c or "备注" in c), -1)

        for row_i, row in enumerate(tbl["rows"]):
            if len(row) <= max(param_idx, val_idx):
                continue
            cn_name = row[param_idx].replace("**", "").strip()
            val_text = row[val_idx].replace("**", "").strip() if val_idx < len(row) else ""
            if not cn_name or not val_text:
                continue

            # Skip descriptive/non-parametric rows: param name contains these keywords
            _SKIP_CN = (
                "方式", "目的", "材质", "标准", "处理", "评估", "术语",
                "定义", "朝向", "关系", "配合方式", "连接方式", "说明",
                "原则", "措施", "建议", "要求（",
            )
            if any(kw in cn_name for kw in _SKIP_CN):
                continue

            # Skip rows where value is clearly a text description, not a measurement:
            # value must start with a digit, Φ, ±, <, ≥, ≤, or a known numeric prefix
            _val_stripped = val_text.lstrip("*（(").strip()
            if _val_stripped and not re.match(
                r"[Φφ<>≥≤±＜＞]?\s*[\d\.]", _val_stripped
            ):
                continue
            # Skip count/spec rows: values like "4×M3×8mm", "法兰外缘R=42mm处"
            # Also skip multi-dimension values like "Φ20×25mm", "15×10×5mm",
            # ratio values like "1:10", and location descriptions.
            if (re.match(r"\d+[×x]", _val_stripped)
                    or re.match(r"[Φφ]?[\d.]+[×x]", _val_stripped)
                    or re.match(r"\d+:\d+", _val_stripped)
                    or "处" in val_text or "标准" in val_text):
                continue

            value, unit = _parse_value_unit(val_text)
            # Skip rows with no extractable numeric value — these are text descriptions
            # (e.g. 驱动方式, 法兰材质, 接口标准) that don't belong in §1 params table.
            if not value:
                continue

            tol = ""
            if tol_idx >= 0 and tol_idx < len(row):
                tol = _parse_tolerance(row[tol_idx])
            if not tol:
                tol = _parse_tolerance(val_text)

            remark = ""
            if remark_idx >= 0 and remark_idx < len(row):
                remark = row[remark_idx].replace("**", "").strip()

            line_no = tbl["start_line"] + row_i + 1
            name = _cn_to_upper(cn_name, context=tbl_heading + " " + remark, line_no=line_no)

            params.append({
                "name": name,
                "value": value,
                "unit": unit,
                "tol": tol,
                "source": f"L{line_no}",
                "remark": remark,
                "cn_name": cn_name,
            })

    # Deduplicate param names: if same name appears >1 time, append _2, _3 ...
    name_count: dict = {}
    for p in params:
        name_count[p["name"]] = name_count.get(p["name"], 0) + 1
    name_seen: dict = {}
    for p in params:
        n = p["name"]
        if name_count[n] > 1:
            name_seen[n] = name_seen.get(n, 0) + 1
            if name_seen[n] > 1:
                p["name"] = f"{n}_{name_seen[n]}"

    return params


# ─── 2. 公差提取 ─────────────────────────────────────────────────────────

def extract_tolerances(lines: list) -> dict:
    """提取尺寸公差、形位公差、表面处理。

    Returns:
        {"dim_tols": [...], "gdt": [...], "surfaces": [...]}
    """
    result = {"dim_tols": [], "gdt": [], "surfaces": []}

    # §2.1 尺寸公差 — tables with 公差/偏差 columns
    dim_tables = extract_tables(lines, column_keywords=["公差"])
    for tbl in dim_tables:
        cols = [c.lower() for c in tbl["columns"]]
        param_i = next((i for i, c in enumerate(cols) if "参数" in c or "尺寸" in c), 0)
        val_i = next((i for i, c in enumerate(cols) if "值" in c or "设计" in c), 1)
        tol_i = next((i for i, c in enumerate(cols) if "公差" in c or "偏差" in c), -1)
        remark_i = next((i for i, c in enumerate(cols) if "说明" in c or "备注" in c), -1)

        for row in tbl["rows"]:
            if len(row) <= param_i:
                continue
            cn = row[param_i].replace("**", "").strip()
            val = row[val_i].replace("**", "").strip() if val_i < len(row) else ""
            value, unit = _parse_value_unit(val)

            tol_text = row[tol_i].strip() if tol_i >= 0 and tol_i < len(row) else ""
            # Parse +upper/lower or ±
            upper = lower = fit_code = label = ""
            m_pm = re.search(r"±\s*([\d.]+)", tol_text)
            m_asym = re.search(r"\+([\d.]+)\s*/\s*([0\-][\d.]*)", tol_text)
            m_fit = re.search(r"([Hh]\d+)\s*[/\\]\s*([a-z]\d+)", tol_text)

            if m_asym:
                upper = f"+{m_asym.group(1)}"
                lower = f"-{m_asym.group(2)}" if m_asym.group(2) != "0" else "0"
                label = tol_text
            elif m_pm:
                upper = f"+{m_pm.group(1)}"
                lower = f"-{m_pm.group(1)}"
                label = tol_text
            if m_fit:
                fit_code = f"{m_fit.group(1)}/{m_fit.group(2)}"

            if upper or lower or fit_code:
                name = _cn_to_upper(cn)
                result["dim_tols"].append({
                    "name": name, "nominal": f"{value}{unit}",
                    "upper": upper, "lower": lower,
                    "fit_code": fit_code, "label": label or tol_text,
                })

    # §2.2 形位公差 — look for GD&T symbols or 形位 heading
    gdt_tables = extract_tables(lines, heading_pattern=r"形位公差|GD&?T")
    for tbl in gdt_tables:
        for row in tbl["rows"]:
            if len(row) >= 3:
                result["gdt"].append({
                    "symbol": row[0].strip(),
                    "value": row[1].strip(),
                    "datum": row[2].strip() if len(row) > 2 else "",
                    "parts": row[3].strip() if len(row) > 3 else "",
                })

    # §2.3 表面处理 — look for Ra or 粗糙度 or 表面处理
    surf_tables = extract_tables(lines, column_keywords=["Ra"])
    if not surf_tables:
        surf_tables = extract_tables(lines, heading_pattern=r"表面处理|粗糙度")
    for tbl in surf_tables:
        cols = [c.lower() for c in tbl["columns"]]
        part_i = next((i for i, c in enumerate(cols) if "零件" in c or "名称" in c), 0)
        ra_i = next((i for i, c in enumerate(cols) if "ra" in c or "粗糙" in c), -1)
        proc_i = next((i for i, c in enumerate(cols) if "处理" in c or "工艺" in c), -1)
        mat_i = next((i for i, c in enumerate(cols) if "材" in c), -1)

        for row in tbl["rows"]:
            part = row[part_i].replace("**", "").strip() if part_i < len(row) else ""
            ra = row[ra_i].strip() if ra_i >= 0 and ra_i < len(row) else ""
            proc = row[proc_i].strip() if proc_i >= 0 and proc_i < len(row) else ""
            mat = row[mat_i].strip() if mat_i >= 0 and mat_i < len(row) else ""
            if part:
                result["surfaces"].append({
                    "part": part, "ra": ra, "process": proc, "material_type": mat,
                })

    return result


# ─── 3. 紧固件提取 ───────────────────────────────────────────────────────

def extract_fasteners(lines: list) -> list:
    """提取含 '螺栓|螺钉|螺母' + '规格|力矩' 的表。

    Returns:
        [{location, spec, qty, torque, grade, remark}]
    """
    tables = extract_tables(lines, column_keywords=["螺"])
    # Only keep tables that also have a spec/torque column (avoid catching §2 or §6 tables)
    tables = [t for t in tables if any(
        "规格" in c or "力矩" in c or "扭矩" in c or "型号" in c
        for c in t["columns"]
    )]
    if not tables:
        # Also try inline patterns like "4×M3×8mm"
        tables = extract_tables(lines, column_keywords=["M"])

    fasteners = []

    # Table-based extraction
    for tbl in tables:
        cols = [c.lower() for c in tbl["columns"]]
        loc_i = next((i for i, c in enumerate(cols) if "位置" in c or "连接" in c), 0)
        spec_i = next((i for i, c in enumerate(cols) if "规格" in c or "型号" in c), 1)
        qty_i = next((i for i, c in enumerate(cols) if "数量" in c), -1)
        torque_i = next((i for i, c in enumerate(cols) if "力矩" in c or "扭矩" in c), -1)
        grade_i = next((i for i, c in enumerate(cols) if "等级" in c or "材料" in c), -1)
        remark_i = next((i for i, c in enumerate(cols) if "备注" in c or "说明" in c), -1)

        for row in tbl["rows"]:
            location = row[loc_i].strip() if loc_i < len(row) else ""
            # Skip empty location rows
            if not location:
                continue
            # BUG-03: skip rows where location looks like a section heading (e.g. "4.5 标准...")
            if re.match(r"^\d+\.\d+\s", location):
                continue
            spec = row[spec_i].strip() if spec_i < len(row) else ""
            qty_str = row[qty_i].strip() if qty_i >= 0 and qty_i < len(row) else ""
            torque = row[torque_i].strip() if torque_i >= 0 and torque_i < len(row) else ""
            grade = row[grade_i].strip() if grade_i >= 0 and grade_i < len(row) else ""
            remark = row[remark_i].strip() if remark_i >= 0 and remark_i < len(row) else ""

            qty_m = re.search(r"\d+", qty_str)
            qty = int(qty_m.group(0)) if qty_m else 1

            if spec or location:
                fasteners.append({
                    "location": location, "spec": spec, "qty": qty,
                    "torque": torque, "grade": grade, "remark": remark,
                })

    # Inline extraction from full text: "4×M3×8mm" patterns
    inline_re = re.compile(r"(\d+)\s*[×xX]\s*(M\d+)\s*[×xX]\s*(\d+)\s*mm")
    for i, line in enumerate(lines):
        for m in inline_re.finditer(line):
            qty, bolt, length = int(m.group(1)), m.group(2), m.group(3)
            spec_str = f"{bolt}×{length}mm"
            # Avoid duplicates from tables
            if not any(f["spec"] == spec_str for f in fasteners):
                # Try to find context from nearby heading
                context = ""
                for j in range(i, max(i - 10, -1), -1):
                    if lines[j].strip().startswith("#"):
                        context = lines[j].strip().lstrip("#").strip()
                        break
                # BUG-03: skip inline fasteners whose context is a section heading
                if re.match(r"^\d+\.\d+\s", context) or not context:
                    continue
                fasteners.append({
                    "location": context, "spec": spec_str, "qty": qty,
                    "torque": "", "grade": "", "remark": f"L{i + 1}",
                })

    return fasteners


# ─── 4. BOM 提取（委托 bom_parser） ───────────────────────────────────────

def extract_bom(filepath: str) -> Optional[dict]:
    """委托 bom_parser.py 解析 BOM。

    Returns bom_parser 输出 dict，或 None。
    """
    # Add tools/ to path so we can import bom_parser
    tools_dir = str(Path(__file__).parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)

    try:
        from bom_parser import parse_bom_from_markdown
        return parse_bom_from_markdown(filepath)
    except ImportError:
        return None
    except Exception:
        return None


# ─── 5. 连接矩阵（交叉合成） ─────────────────────────────────────────────

def extract_connection_matrix(lines: list, fasteners: list,
                              assembly_layers: list) -> list:
    """从紧固件 + 装配层叠交叉合成连接矩阵。

    Returns:
        [{partA, partB, type, fit, torque, order}]
    """
    connections = []
    order = 0

    # From assembly layers: each layer connects to its parent (layer with lower level number)
    # This produces parallel topology (all L3 items connect to L2 parent, not each other)
    active_layers = [l for l in assembly_layers if not l.get("exclude", False)]
    for i in range(1, len(active_layers)):
        b = active_layers[i]
        # Find nearest preceding layer with a strictly lower level
        b_level = b.get("level", "")
        parent = None
        for j in range(i - 1, -1, -1):
            a = active_layers[j]
            if a.get("level", "") < b_level:
                parent = a
                break
        if parent is None:
            parent = active_layers[i - 1]
        order += 1
        connections.append({
            "partA": parent.get("part", ""),
            "partB": b.get("part", ""),
            "type": b.get("connection", ""),
            "fit": "",
            "torque": "",
            "order": order,
        })

    # Enrich with fastener torque data
    for conn in connections:
        for f in fasteners:
            if (f["location"] and
                (f["location"] in conn["partA"] or
                 f["location"] in conn["partB"] or
                 conn["partA"] in f["location"] or
                 conn["partB"] in f["location"])):
                conn["torque"] = f["torque"]
                conn["type"] = conn["type"] or f["spec"]
                break

    # Also look for explicit connection tables
    conn_tables = extract_tables(lines, column_keywords=["零件A", "零件B"])
    if not conn_tables:
        conn_tables = extract_tables(lines, heading_pattern=r"连接矩阵|连接关系")
    existing_pairs = {(c["partA"], c["partB"]) for c in connections}
    for tbl in conn_tables:
        cols = [c.lower() for c in tbl["columns"]]
        a_i = next((i for i, c in enumerate(cols) if "零件a" in c or "部件a" in c), 0)
        b_i = next((i for i, c in enumerate(cols) if "零件b" in c or "部件b" in c), 1)
        type_i = next((i for i, c in enumerate(cols) if "类型" in c or "连接" in c), -1)
        for row in tbl["rows"]:
            pa = row[a_i].strip() if a_i < len(row) else ""
            pb = row[b_i].strip() if b_i < len(row) else ""
            if (pa, pb) in existing_pairs or (pb, pa) in existing_pairs:
                continue
            existing_pairs.add((pa, pb))
            order += 1
            connections.append({
                "partA": pa,
                "partB": pb,
                "type": row[type_i].strip() if type_i >= 0 and type_i < len(row) else "",
                "fit": "", "torque": "", "order": order,
            })

    return connections


# ─── 6. 装配姿态与定位 ───────────────────────────────────────────────────

def _parse_offset(text: str) -> dict:
    """Parse offset text like 'Z=+73mm(向上)' into structured values."""
    result = {"z": None, "r": None, "theta": None, "is_origin": False}
    if not text:
        return result
    if "基准" in text or "原点" in text:
        result["z"] = 0.0
        result["is_origin"] = True
    m = re.search(r"Z\s*=\s*([+-]?\d+(?:\.\d+)?)", text)
    if m:
        result["z"] = float(m.group(1))
    if result["z"] is None:
        m = re.search(r"Z\s*=\s*0(?:\s*[\(（]|$)", text)
        if m:
            result["z"] = 0.0
    m = re.search(r"R\s*[=≈]\s*(\d+(?:\.\d+)?)", text)
    if m:
        result["r"] = float(m.group(1))
    m = re.search(r"θ\s*=\s*(\d+(?:\.\d+)?)", text)
    if m:
        result["theta"] = float(m.group(1))
    return result


def _parse_axis_dir(text: str) -> list:
    """Parse axis_dir multi-clause text into structured list.

    E.g. '壳体轴沿-Z（垂直向下），储罐轴∥XY（水平径向外伸）'
    → [{"keyword": "壳体", "direction": (0,0,-1), "rotation": None},
       {"keyword": "储罐", "direction": (1,0,0), "rotation": {"axis":(1,0,0),"angle":90}}]
    """
    if not text:
        return []
    clauses = re.split(r"[，,]", text)
    parsed = []
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        entry = {"keyword": "", "direction": (0, 0, -1), "rotation": None}
        kw_m = re.match(r"([\u4e00-\u9fff]{1,4})[轴面]", clause)
        if kw_m:
            entry["keyword"] = kw_m.group(1)
        if any(k in clause for k in ["盘面∥XY", "环∥XY", "弧形∥XY"]):
            entry["direction"] = (0, 0, 1)
        elif any(k in clause for k in ["沿-Z", "-Z", "向下"]):
            entry["direction"] = (0, 0, -1)
        elif any(k in clause for k in ["沿+Z", "+Z", "向上"]):
            entry["direction"] = (0, 0, 1)
        elif any(k in clause for k in ["沿Z", "垂直", "⊥法兰"]):
            entry["direction"] = (0, 0, -1)
        elif any(k in clause for k in ["∥XY", "水平", "径向外伸", "径向"]):
            entry["direction"] = (1, 0, 0)
            entry["rotation"] = {"axis": (1, 0, 0), "angle": 90}
        parsed.append(entry)
    return parsed


def extract_assembly_pose(lines: list) -> dict:
    """提取 §X.10.0 坐标系 + §X.10.1 装配层叠。

    Returns:
        {"coord_sys": [{term, definition, equivalent}],
         "layers": [{level, part, fixed_moving, connection, offset, offset_parsed,
                     axis_dir, axis_dir_parsed, exclude, exclude_reason}]}
    """
    result = {"coord_sys": [], "layers": []}

    # Coordinate system: tables with 术语|定义
    coord_tables = extract_tables(lines, column_keywords=["术语", "定义"])
    for tbl in coord_tables:
        for row in tbl["rows"]:
            result["coord_sys"].append({
                "term": row[0].strip() if len(row) > 0 else "",
                "definition": row[1].strip() if len(row) > 1 else "",
                "equivalent": row[2].strip() if len(row) > 2 else "",
            })

    # Assembly layers: tables with 层级|零件
    layer_tables = extract_tables(lines, column_keywords=["层级"])
    if not layer_tables:
        layer_tables = extract_tables(lines, heading_pattern=r"装配层叠|装配顺序|层叠")
    for tbl in layer_tables:
        cols = [c.lower() for c in tbl["columns"]]
        level_i = next((i for i, c in enumerate(cols) if "层级" in c or "层" in c), 0)
        part_i = next((i for i, c in enumerate(cols) if "零件" in c or "模块" in c), 1)
        fm_i = next((i for i, c in enumerate(cols) if "固定" in c or "运动" in c), -1)
        conn_i = next((i for i, c in enumerate(cols) if "连接" in c), -1)
        offset_i = next((i for i, c in enumerate(cols) if "偏移" in c or "相对" in c), -1)
        axis_i = next((i for i, c in enumerate(cols) if "轴线" in c or "方向" in c), -1)

        for row in tbl["rows"]:
            part_name = row[part_i].strip() if part_i < len(row) else ""
            # Instead of hardcoded continue, keep all parts. Exclusion is determined
            # later by cross-referencing negative constraints from §X.10.5.
            offset_text = row[offset_i].strip() if offset_i >= 0 and offset_i < len(row) else ""
            axis_text = row[axis_i].strip() if axis_i >= 0 and axis_i < len(row) else ""
            result["layers"].append({
                "level": row[level_i].strip() if level_i < len(row) else "",
                "part": part_name,
                "fixed_moving": row[fm_i].strip() if fm_i >= 0 and fm_i < len(row) else "",
                "connection": row[conn_i].strip() if conn_i >= 0 and conn_i < len(row) else "",
                "offset": offset_text,
                "offset_parsed": _parse_offset(offset_text),
                "axis_dir": axis_text,
                "axis_dir_parsed": _parse_axis_dir(axis_text),
                "exclude": False,
                "exclude_reason": "",
            })

    return result


# ─── 7. 视觉标识 ─────────────────────────────────────────────────────────

def extract_visual_ids(lines: list, bom_data: Optional[dict] = None) -> list:
    """提取 §X.10.2 视觉标识表。无该节时从 BOM 生成骨架。

    Returns:
        [{part, material, color, label, size, direction}]
    """
    tables = extract_tables(lines, column_keywords=["唯一标签"])
    if not tables:
        tables = extract_tables(lines, column_keywords=["视觉标识"])
    if not tables:
        tables = extract_tables(lines, heading_pattern=r"视觉标识|Visual ID")

    visuals = []
    for tbl in tables:
        cols = [c.lower() for c in tbl["columns"]]
        part_i = next((i for i, c in enumerate(cols) if "零件" in c), 0)
        mat_i = next((i for i, c in enumerate(cols) if "材质" in c or "材料" in c), -1)
        color_i = next((i for i, c in enumerate(cols) if "颜色" in c or "表面" in c), -1)
        label_i = next((i for i, c in enumerate(cols) if "标签" in c or "label" in c.lower()), -1)
        size_i = next((i for i, c in enumerate(cols) if "尺寸" in c or "外形" in c), -1)
        dir_i = next((i for i, c in enumerate(cols) if "方向" in c or "约束" in c), -1)

        for row in tbl["rows"]:
            visuals.append({
                "part": row[part_i].strip() if part_i < len(row) else "",
                "material": row[mat_i].strip() if mat_i >= 0 and mat_i < len(row) else "",
                "color": row[color_i].strip() if color_i >= 0 and color_i < len(row) else "",
                "label": row[label_i].strip() if label_i >= 0 and label_i < len(row) else "",
                "size": row[size_i].strip() if size_i >= 0 and size_i < len(row) else "",
                "direction": row[dir_i].strip() if dir_i >= 0 and dir_i < len(row) else "",
            })

    # Fallback: generate skeleton from BOM
    if not visuals and bom_data:
        for assy in bom_data.get("assemblies", []):
            for part in assy.get("parts", []):
                visuals.append({
                    "part": part["name"],
                    "material": part.get("material", ""),
                    "color": "[待定]",
                    "label": "[待定]",
                    "size": "[待定]",
                    "direction": "[待定]",
                })

    return visuals


# ─── 8. 渲染规划 ─────────────────────────────────────────────────────────

def extract_render_plan(lines: list) -> dict:
    """提取 §X.10.3 迭代分组 + §X.10.4 视角 + §X.10.5 否定约束。

    Returns:
        {"groups": [...], "views": [...], "constraints": [...]}
    """
    result = {"groups": [], "views": [], "constraints": []}

    # Groups: tables with 步骤|添加内容
    group_tables = extract_tables(lines, column_keywords=["步骤"])
    if not group_tables:
        group_tables = extract_tables(lines, heading_pattern=r"迭代分组|渲染分组")
    for tbl in group_tables:
        cols = [c.lower() for c in tbl["columns"]]
        step_i = next((i for i, c in enumerate(cols) if "步骤" in c or "step" in c), 0)
        content_i = next((i for i, c in enumerate(cols) if "添加" in c or "内容" in c), 1)
        pos_i = next((i for i, c in enumerate(cols) if "位置" in c or "画面" in c), -1)
        prompt_i = next((i for i, c in enumerate(cols) if "prompt" in c or "要点" in c), -1)
        dep_i = next((i for i, c in enumerate(cols) if "依赖" in c), -1)

        for row in tbl["rows"]:
            result["groups"].append({
                "step": row[step_i].strip() if step_i < len(row) else "",
                "content": row[content_i].strip() if content_i < len(row) else "",
                "position": row[pos_i].strip() if pos_i >= 0 and pos_i < len(row) else "",
                "prompt_key": row[prompt_i].strip() if prompt_i >= 0 and prompt_i < len(row) else "",
                "depends": row[dep_i].strip() if dep_i >= 0 and dep_i < len(row) else "",
            })

    # Views: tables with 视角|仰角 or 视角ID
    view_tables = extract_tables(lines, column_keywords=["视角"])
    for tbl in view_tables:
        cols = [c.lower() for c in tbl["columns"]]
        id_i = next((i for i, c in enumerate(cols) if "视角" in c and "id" in c), -1)
        name_i = next((i for i, c in enumerate(cols) if "名称" in c), -1)
        angle_i = next((i for i, c in enumerate(cols) if "仰角" in c or "方位" in c), -1)
        visible_i = next((i for i, c in enumerate(cols) if "可见" in c), -1)
        hidden_i = next((i for i, c in enumerate(cols) if "遮挡" in c or "不可见" in c), -1)
        focus_i = next((i for i, c in enumerate(cols) if "重点" in c or "焦点" in c), -1)

        for row in tbl["rows"]:
            result["views"].append({
                "id": row[id_i].strip() if id_i >= 0 and id_i < len(row) else "",
                "name": row[name_i].strip() if name_i >= 0 and name_i < len(row) else "",
                "angle": row[angle_i].strip() if angle_i >= 0 and angle_i < len(row) else "",
                "visible": row[visible_i].strip() if visible_i >= 0 and visible_i < len(row) else "",
                "hidden": row[hidden_i].strip() if hidden_i >= 0 and hidden_i < len(row) else "",
                "focus": row[focus_i].strip() if focus_i >= 0 and focus_i < len(row) else "",
            })

    # Constraints: tables with 约束ID|约束描述
    constraint_tables = extract_tables(lines, column_keywords=["约束"])
    if not constraint_tables:
        constraint_tables = extract_tables(lines, heading_pattern=r"否定约束|NEVER")
    for tbl in constraint_tables:
        cols = [c.lower() for c in tbl["columns"]]
        id_i = next((i for i, c in enumerate(cols) if "id" in c or "编号" in c), 0)
        # "描述" first; avoid matching "约束id" column when looking for "约束描述"
        desc_i = next((i for i, c in enumerate(cols)
                       if "描述" in c or ("约束" in c and "id" not in c and i != id_i)), 1)
        reason_i = next((i for i, c in enumerate(cols) if "原因" in c or "说明" in c), -1)

        for row in tbl["rows"]:
            result["constraints"].append({
                "id": row[id_i].strip() if id_i < len(row) else "",
                "description": row[desc_i].strip() if desc_i < len(row) else "",
                "reason": row[reason_i].strip() if reason_i >= 0 and reason_i < len(row) else "",
            })

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 零件特征提取 — 交叉引用 §2/§3/§4/§8 合并每个零件的孔/槽/沉台特征
# ═══════════════════════════════════════════════════════════════════════════════


def extract_part_features(lines: list, bom_parts: list) -> dict:
    """从设计文档中提取每个零件的几何特征清单。

    交叉引用多个数据源：
    - §2.1 尺寸公差表：提取 Φ 值 (孔径)
    - §3 紧固件清单：提取螺纹孔规格和安装位置
    - §4 连接矩阵：提取连接类型和配合关系
    - §8 装配序列：提取装配步骤中提到的孔位信息

    Args:
        lines: 设计文档全文按行分割
        bom_parts: BOM 零件列表 [{"part_no": "SLP-100", "name_cn": "上固定板", ...}]

    Returns:
        dict mapping part_no → list of feature dicts:
        {
            "SLP-100": [
                {"type": "through_hole", "diameter": 24.0, "count": 2,
                 "positions": [(-60, 30), (60, -30)],
                 "tolerance": "+0.1/0", "source": "§2.1 Φ24, §4 LS1/LS2"},
                ...
            ]
        }
    """
    text = "\n".join(lines)
    features_by_part = {}

    # Build part name lookup for fuzzy matching
    part_lookup = {}
    for p in bom_parts:
        pno = p.get("part_no", "")
        name = p.get("name_cn", "")
        part_lookup[pno] = name
        if name:
            part_lookup[name] = pno

    # ── Source 1: §2.1 尺寸公差 → 提取 Φ 值列表 ──────────────────────────────
    hole_diameters = {}  # {Φ值: {tolerance, label}}
    tol_data = extract_tolerances(lines)
    for t in tol_data.get("dim_tols", []):
        name = t.get("name", "")
        m = re.match(r"[Φφ](\d+(?:\.\d+)?)", name)
        if m:
            d = float(m.group(1))
            hole_diameters[d] = {
                "tolerance": t.get("label", ""),
                "fit_code": t.get("fit_code", ""),
            }

    # ── Source 2: §3 紧固件清单 → 螺纹孔规格 per 位置 ───────────────────────
    fastener_tables = extract_tables(lines, column_keywords=["螺栓", "力矩"])
    if not fastener_tables:
        fastener_tables = extract_tables(lines, heading_pattern=r"紧固件|螺栓|Fastener")
    fastener_features = []
    for tbl in fastener_tables:
        cols = [c.lower() for c in tbl["columns"]]
        pos_i = next((i for i, c in enumerate(cols) if "位置" in c or "连接" in c), 0)
        spec_i = next((i for i, c in enumerate(cols) if "规格" in c or "螺栓" in c), 1)
        qty_i = next((i for i, c in enumerate(cols) if "数量" in c), 2)

        for row in tbl["rows"]:
            if len(row) <= spec_i:
                continue
            pos_text = row[pos_i].strip() if pos_i < len(row) else ""
            spec_text = row[spec_i].strip() if spec_i < len(row) else ""
            qty_text = row[qty_i].strip() if qty_i < len(row) else "1"

            m_bolt = re.search(r"M(\d+)", spec_text)
            if m_bolt:
                bolt_d = float(m_bolt.group(1))
                qty_m = re.search(r"(\d+)", qty_text)
                qty = int(qty_m.group(1)) if qty_m else 1
                fastener_features.append({
                    "bolt_d": bolt_d,
                    "count": qty,
                    "position_text": pos_text,
                    "source": f"§3 {spec_text}",
                })

    # ── Source 3: §4/§8 装配文本 → 孔位关联到零件 ────────────────────────────
    hole_pattern = re.compile(
        r"(?:穿入|装[至到]|旋入|压入|嵌入)"
        r"[^，,。\n]{0,20}?"
        r"([\u4e00-\u9fff]{2,6})"
        r"[^，,。\n]{0,10}?"
        r"[Φφ](\d+(?:\.\d+)?)"
        r"([Hh]\d+)?",
    )

    assembly_hints = []
    for i, line in enumerate(lines):
        for m in hole_pattern.finditer(line):
            part_frag = m.group(1)
            diameter = float(m.group(2))
            fit = m.group(3) or ""
            assembly_hints.append((part_frag, diameter, fit, f"L{i+1}"))

    # ── Source 4: 从全文提取坐标 (X, Y) 并关联到附近的孔/零件名 ───────────
    # 数据唯一来源：设计文档中的 "(±X, ±Y)" 坐标文本
    coord_pattern = re.compile(
        r"([\u4e00-\u9fff]{2,8})"        # part name fragment (Chinese, 2-8 chars)
        r"[^(（\n]{0,30}?"                # gap (up to 30 chars, not crossing lines)
        r"[\(（]"                          # opening bracket
        r"([+\-−]?\d+(?:\.\d+)?)"         # X coordinate
        r"\s*[,，]\s*"                     # separator
        r"([+\-−±]?\d+(?:\.\d+)?)"        # Y coordinate
        r"[\)）]"                          # closing bracket
    )
    # Map: part_name_fragment → list of (x, y) tuples
    coord_hints = {}  # {part_frag: [(x, y), ...]}
    for i, line in enumerate(lines):
        for m in coord_pattern.finditer(line):
            frag = m.group(1)
            try:
                x = float(m.group(2).replace("−", "-"))
                y_str = m.group(3).replace("−", "-")
                # Handle ±N: expand to two symmetric points
                if "±" in y_str:
                    y_abs = float(y_str.replace("±", ""))
                    coords = [(x, y_abs), (x, -y_abs)]
                else:
                    y = float(y_str)
                    coords = [(x, y)]
                coord_hints.setdefault(frag, []).extend(coords)
            except (ValueError, IndexError):
                pass

    # ── Merge: associate features with BOM parts ─────────────────────────────
    def _fuzzy_match(frag: str, name: str) -> bool:
        """模糊匹配零件名。

        支持：
        - 精确包含："动板" in "动板" → True
        - 缩写："上板" → "上固定板"（首尾字序）
        - 带后缀："上板底面" → "上固定板"（去掉方位后缀再匹配）
        """
        if frag in name or name in frag:
            return True
        # 缩写匹配：首尾字符都在名称中且顺序正确
        if len(frag) >= 2 and frag[0] in name and frag[-1] in name:
            i0 = name.index(frag[0])
            i1 = name.rindex(frag[-1])
            if i0 < i1:
                return True
        # 带方位后缀匹配："上板底面" → 去掉 "底面"/"顶面" → "上板" → 重试
        for suffix in ("底面", "顶面", "侧面", "端面", "内孔", "外壁"):
            if frag.endswith(suffix) and len(frag) > len(suffix):
                stripped = frag[:-len(suffix)]
                if _fuzzy_match(stripped, name):
                    return True
        return False

    for p in bom_parts:
        pno = p.get("part_no", "")
        name = p.get("name_cn", "")
        if not pno:
            continue

        part_features = []
        matched_diameters = set()

        # Collect coordinates that match this part name from coord_hints
        part_coords = []
        for cfrag, clist in coord_hints.items():
            if _fuzzy_match(cfrag, name):
                part_coords.extend(clist)
        # Deduplicate coordinates
        part_coords = list(set(part_coords))

        for frag, dia, fit, src in assembly_hints:
            if _fuzzy_match(frag, name):
                if dia not in matched_diameters:
                    tol_info = hole_diameters.get(dia, {})
                    tol_text = tol_info.get("tolerance", "")
                    if fit and not tol_text:
                        tol_text = fit

                    # Try to associate positions from coord_hints
                    positions = list(part_coords) if part_coords else []
                    count = len(positions) if positions else 2

                    part_features.append({
                        "type": "through_hole",
                        "diameter": dia,
                        "count": count,
                        "positions": positions,
                        "tolerance": tol_text,
                        "source": f"§2.1 Φ{dia}{fit}, {src}",
                    })
                    matched_diameters.add(dia)

        for ff in fastener_features:
            if name and name in ff["position_text"]:
                tap_d = ff["bolt_d"]
                if tap_d not in matched_diameters:
                    # Try to find positions from coord_hints for the fastener location text
                    ff_coords = []
                    for cfrag, clist in coord_hints.items():
                        if cfrag in ff["position_text"] or ff["position_text"] in cfrag:
                            ff_coords.extend(clist)
                    ff_coords = list(set(ff_coords)) if ff_coords else []

                    part_features.append({
                        "type": "threaded_hole",
                        "diameter": tap_d,
                        "tap_drill_d": round(tap_d * 0.85, 1),
                        "count": len(ff_coords) if ff_coords else ff["count"],
                        "positions": ff_coords,
                        "tolerance": "",
                        "source": ff["source"],
                    })
                    matched_diameters.add(tap_d)

        if part_features:
            features_by_part[pno] = part_features

    return features_by_part


# ═══════════════════════════════════════════════════════════════════════════════
# 零件包络提取 — 多来源优先级合并
# ═══════════════════════════════════════════════════════════════════════════════


def extract_part_envelopes(lines: list, bom_data=None,
                           visual_ids: list = None, params: list = None) -> dict:
    """从多来源提取零件包络尺寸，按优先级合并。

    Priority: P1(零件级参数表) > P2(叙述包络) > P3(BOM材质列) > P4(视觉标识) > P5(全局参数)

    Returns: {part_no: {"type": str, "d"|"w": float, "h": float, "source": str}}
    """
    from cad_spec_defaults import _parse_dims_from_text
    result = {}

    # --- P3: BOM 材质列 ---
    if bom_data:
        for assy in bom_data.get("assemblies", []):
            for part in assy.get("parts", []):
                pno = part.get("part_no", "")
                material = part.get("material", "")
                if not pno or not material:
                    continue
                dims = _parse_dims_from_text(material)
                if dims:
                    result[pno] = _dims_to_envelope(dims, "P3:BOM")

    # --- P4: 视觉标识表 size 列 ---
    if visual_ids and bom_data:
        for v in visual_ids:
            part_name = v.get("part", "")
            size_text = v.get("size", "")
            if not size_text or size_text == "[待定]":
                continue
            dims = _parse_dims_from_text(size_text)
            if dims:
                pno = _match_name_to_bom(part_name, bom_data)
                if pno:
                    result[pno] = _dims_to_envelope(dims, "P4:visual")

    # --- P2: 叙述文字中"模块包络尺寸：W×D×H" ---
    text = "\n".join(lines)
    for m in re.finditer(
        r"模块包络尺寸[：:]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm",
        text
    ):
        w, d, h = float(m.group(1)), float(m.group(2)), float(m.group(3))
        pos = m.start()
        context = text[max(0, pos - 500):pos]
        pno = _find_nearest_assembly(context, bom_data)
        if pno:
            result[pno] = {"type": "box", "w": w, "d": d, "h": h, "source": "P2:narrative"}

    # --- P1: 零件级参数表（含"外形"/"尺寸"列的子表格）---
    part_tables = extract_tables(lines, column_keywords=["外形", "尺寸参数"])
    if not part_tables:
        part_tables = extract_tables(lines, column_keywords=["设计值"])
    for tbl in part_tables:
        cols = [c.lower() for c in tbl["columns"]]
        name_i = next((i for i, c in enumerate(cols) if "零件" in c), 0)
        dim_cols = [i for i, c in enumerate(cols) if "设计值" in c or "尺寸" in c or "外形" in c]
        if not dim_cols:
            continue
        dim_i = dim_cols[0]
        for row in tbl["rows"]:
            part_name = row[name_i].strip() if name_i < len(row) else ""
            dim_text = row[dim_i].strip() if dim_i < len(row) else ""
            if not dim_text:
                continue
            dims = _parse_dims_from_text(dim_text)
            if dims and bom_data:
                pno = _match_name_to_bom(part_name, bom_data)
                if pno:
                    result[pno] = _dims_to_envelope(dims, "P1:part_table")

    # --- Post-pass: fix disc-typed motors/reducers by searching body text ---
    # When BOM only has "Φ16mm" (no length), _dims_to_envelope produces type="disc"
    # with h = d*0.25. For motors/reducers, search body text for "Φd×Lmm" full dims.
    text = "\n".join(lines)
    motor_keywords = ("电机", "减速", "motor", "reducer")
    for pno, env in list(result.items()):
        if env.get("type") != "disc":
            continue
        # Check if this part is a motor/reducer
        part_name = ""
        if bom_data:
            for assy in bom_data.get("assemblies", []):
                for part in assy.get("parts", []):
                    if part.get("part_no") == pno:
                        part_name = part.get("name", "") + part.get("material", "")
                        break
        if not any(kw in part_name for kw in motor_keywords):
            continue
        # Search body text for full Φd×Lmm near the part name
        d = env["d"]
        pattern = rf'[Φφ]\s*{int(d)}(?:\.\d+)?\s*[×x×]\s*(\d+(?:\.\d+)?)\s*mm'
        m = re.search(pattern, text)
        if m:
            full_length = float(m.group(1))
            if full_length > env["h"]:  # only if body text gives a larger dimension
                result[pno] = {"type": "cylinder", "d": d, "h": full_length,
                               "source": env["source"] + "+body_text"}

    return result


def _dims_to_envelope(dims: dict, source: str) -> dict:
    """Convert raw dims dict to envelope format."""
    if "d" in dims and "l" in dims:
        return {"type": "cylinder", "d": dims["d"], "h": dims["l"], "source": source}
    elif "w" in dims and "h" in dims and "l" in dims:
        return {"type": "box", "w": dims["w"], "d": dims["h"], "h": dims["l"], "source": source}
    elif "w" in dims and "h" in dims:
        return {"type": "box", "w": dims["w"], "d": dims["w"], "h": dims["h"], "source": source}
    elif "od" in dims:
        return {"type": "ring", "d": dims["od"], "h": dims.get("w", dims.get("h", 5)), "source": source}
    elif "d" in dims:
        return {"type": "disc", "d": dims["d"], "h": max(5, round(dims["d"] * 0.25, 1)), "source": source}
    return {"type": "box", "w": 20, "d": 20, "h": 20, "source": source + "(fallback)"}


def _match_name_to_bom(name: str, bom_data) -> Optional[str]:
    """Match a Chinese part name to BOM part_no by keyword prefix matching."""
    if not bom_data or not name:
        return None
    keywords = [name[:n] for n in (4, 3, 2) if len(name) >= n]
    for assy in bom_data.get("assemblies", []):
        for part in assy.get("parts", []):
            pname = part.get("name", "")
            for kw in keywords:
                if kw in pname:
                    return part.get("part_no")
    return None


def _find_nearest_assembly(context: str, bom_data) -> Optional[str]:
    """Find nearest assembly part_no from preceding text context."""
    if not bom_data:
        return None
    pnos = re.findall(r"([A-Z]+-[A-Z]+-\d{3})", context)
    if pnos:
        return pnos[-1]
    for assy in bom_data.get("assemblies", []):
        name = assy.get("name", "")
        if name and len(name) >= 4 and name[:4] in context:
            return assy.get("part_no")
    return None


def extract_part_placements(lines: list, bom_data=None,
                             assembly_layers: list = None) -> list:
    """提取零件级定位信息：串联堆叠链 + 非轴向定位描述。

    Returns list of placement dicts.
    """
    from cad_spec_defaults import _parse_dims_from_text
    placements = []
    text = "\n".join(lines)

    # --- Part 1: Extract axial_stack chains from → syntax ---
    # Find fenced code blocks containing → chains
    code_blocks = re.finditer(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    for block_match in code_blocks:
        block = block_match.group(1)
        if "→" not in block:
            continue
        chain_lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if len(chain_lines) < 2:
            continue

        # Detect assembly context from text before the code block
        ctx_start = max(0, block_match.start() - 500)
        context = text[ctx_start:block_match.start()]
        assembly_pno = _detect_assembly_context(context, bom_data)

        # Parse anchor (text before first →)
        anchor = ""
        full_text = " ".join(chain_lines)
        parts = full_text.split("→")
        if parts:
            anchor = parts[0].strip()

        # Parse nodes (everything after first →)
        nodes = []
        for item_text in parts[1:]:
            item_text = item_text.strip()
            if not item_text:
                continue
            node = _parse_chain_node(item_text, bom_data)
            nodes.append(node)

        if not nodes:
            continue

        # Determine stacking direction from assembly layers
        direction = (0, 0, -1)  # default: downward
        if assembly_layers and assembly_pno:
            for layer in assembly_layers:
                if assembly_pno in layer.get("part", ""):
                    parsed_dirs = layer.get("axis_dir_parsed", [])
                    if parsed_dirs:
                        direction = parsed_dirs[0].get("direction", (0, 0, -1))
                    break

        placements.append({
            "assembly": assembly_pno or "",
            "anchor": anchor,
            "direction": direction,
            "mode": "axial_stack",
            "chain": nodes,
        })

    # --- Part 2: Extract non-axial placements from narrative ---
    _extract_non_axial_placements(text, bom_data, placements)

    return placements


def _parse_chain_node(text: str, bom_data) -> dict:
    """Parse a single chain node like '[4×M3螺栓] → 力传感器KWR42(Φ42×20mm, 70g)'."""
    from cad_spec_defaults import _parse_dims_from_text
    node = {"part_name": "", "part_no": None, "dims": None,
            "connection": None, "sub_assembly": None}

    # Extract connection prefix: [4×M3螺栓]
    conn_m = re.match(r"\[([^\]]+)\]\s*", text)
    if conn_m:
        node["connection"] = conn_m.group(1).strip()
        text = text[conn_m.end():]

    # Extract dimensions from parentheses
    dim_m = re.search(r"\(([^)]+)\)", text)
    if dim_m:
        dim_text = dim_m.group(1)
        dims = _parse_dims_from_text(dim_text)
        if dims:
            node["dims"] = _dims_to_envelope(dims, "chain")
        name = text[:dim_m.start()].strip()
    else:
        name = text.strip()

    node["part_name"] = name

    # Match to BOM
    if bom_data and name:
        node["part_no"] = _match_name_to_bom(name, bom_data)

    return node


def _detect_assembly_context(context: str, bom_data) -> Optional[str]:
    """Detect which assembly a chain belongs to from surrounding text."""
    if not bom_data:
        return None
    # Look for assembly-level part numbers (3-segment: GIS-EE-003)
    pnos = re.findall(r"([A-Z]+-[A-Z]+-\d{3})", context)
    if pnos:
        return pnos[-1]
    # Fallback: match assembly name keywords
    for assy in bom_data.get("assemblies", []):
        name = assy.get("name", "")
        if name and len(name) >= 4 and name[:4] in context:
            return assy.get("part_no")
    return None


def _extract_non_axial_placements(text: str, bom_data, placements: list):
    """Extract radial_extend, side_mount, coaxial, lateral_array from narrative text."""
    patterns = [
        (r"(沿.{0,4}径向|轴线与悬臂共线).{0,6}(向外|外伸|延伸)", "radial_extend"),
        (r"(安装于|位于).{0,4}(侧壁|侧面|外侧).{0,10}(竖直|并排)", "side_mount"),
        (r"(压入|嵌入|过盈配合)", "coaxial"),
        (r"(并列|并排).{0,6}间距\s*(\d+)\s*mm", "lateral_array"),
        (r"(安装于|位于).{0,4}(顶部|底部|末端|端部)", "extremity"),
    ]
    for pattern, mode in patterns:
        for m in re.finditer(pattern, text):
            ctx_start = max(0, m.start() - 300)
            ctx_end = min(len(text), m.end() + 100)
            context = text[ctx_start:ctx_end]

            # Find part number in context
            pno = None
            pno_m = re.search(r"([A-Z]+-[A-Z]+-\d+-\d+)", context)
            if pno_m:
                pno = pno_m.group(1)
            elif bom_data:
                pno_m2 = re.search(r"([A-Z]+-[A-Z]+-\d{3})", context)
                if pno_m2:
                    pno = pno_m2.group(1)

            params = {}
            if mode == "radial_extend":
                params["rotation"] = {"axis": (1, 0, 0), "angle": 90}
            elif mode == "lateral_array":
                pitch_m = re.search(r"间距\s*(\d+)", context)
                if pitch_m:
                    params["pitch"] = float(pitch_m.group(1))

            placements.append({
                "assembly": "",
                "part_no": pno,
                "mode": mode,
                "params": params,
                "source": f"text:{mode}",
                "confidence": "medium",
            })
