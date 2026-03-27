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
    "外径": "OD", "内径": "ID", "厚度": "THICK", "宽度": "W",
    "高度": "H", "长度": "L", "直径": "DIA", "半径": "R",
    "壁厚": "WALL", "安装半径": "MOUNT_R", "重量": "WEIGHT",
    "电压": "VOLTAGE", "频率": "FREQ", "功耗": "POWER",
    "分度": "INDEX", "定位精度": "POS_ACC", "角度": "ANGLE",
    "行程": "STROKE", "负载": "LOAD", "力矩": "TORQUE",
    "速度": "SPEED", "加速度": "ACCEL", "温度": "TEMP",
    "转速": "RPM", "齿数": "TEETH", "模数": "MODULE",
    "传动比": "RATIO", "间距": "PITCH", "节距": "PCD",
    "深度": "DEPTH", "槽宽": "SLOT_W", "槽深": "SLOT_D",
    "孔径": "BORE", "孔深": "BORE_D", "倒角": "CHAMFER",
    "圆角": "FILLET", "螺距": "THREAD_P", "容量": "CAPACITY",
    "压力": "PRESSURE", "流量": "FLOW", "阻抗": "IMPEDANCE",
    "增益": "GAIN", "灵敏度": "SENSITIVITY",
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
    combined = context + cn_name
    for pat, fn in ctx_patterns:
        m_ctx = re.search(pat, combined)
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

            value, unit = _parse_value_unit(val_text)
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

    # From assembly layers: consecutive layers form connections
    for i in range(len(assembly_layers) - 1):
        a = assembly_layers[i]
        b = assembly_layers[i + 1]
        order += 1
        connections.append({
            "partA": a.get("part", ""),
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
    for tbl in conn_tables:
        cols = [c.lower() for c in tbl["columns"]]
        a_i = next((i for i, c in enumerate(cols) if "零件a" in c or "部件a" in c), 0)
        b_i = next((i for i, c in enumerate(cols) if "零件b" in c or "部件b" in c), 1)
        type_i = next((i for i, c in enumerate(cols) if "类型" in c or "连接" in c), -1)
        for row in tbl["rows"]:
            order += 1
            connections.append({
                "partA": row[a_i].strip() if a_i < len(row) else "",
                "partB": row[b_i].strip() if b_i < len(row) else "",
                "type": row[type_i].strip() if type_i >= 0 and type_i < len(row) else "",
                "fit": "", "torque": "", "order": order,
            })

    return connections


# ─── 6. 装配姿态与定位 ───────────────────────────────────────────────────

def extract_assembly_pose(lines: list) -> dict:
    """提取 §X.10.0 坐标系 + §X.10.1 装配层叠。

    Returns:
        {"coord_sys": [{term, definition, equivalent}],
         "layers": [{level, part, fixed_moving, connection, offset, axis_dir}]}
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
            result["layers"].append({
                "level": row[level_i].strip() if level_i < len(row) else "",
                "part": row[part_i].strip() if part_i < len(row) else "",
                "fixed_moving": row[fm_i].strip() if fm_i >= 0 and fm_i < len(row) else "",
                "connection": row[conn_i].strip() if conn_i >= 0 and conn_i < len(row) else "",
                "offset": row[offset_i].strip() if offset_i >= 0 and offset_i < len(row) else "",
                "axis_dir": row[axis_i].strip() if axis_i >= 0 and axis_i < len(row) else "",
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
        id_i = next((i for i, c in enumerate(cols) if "视角" in c and "id" in c), 0)
        name_i = next((i for i, c in enumerate(cols) if "名称" in c), -1)
        angle_i = next((i for i, c in enumerate(cols) if "仰角" in c or "方位" in c), -1)
        visible_i = next((i for i, c in enumerate(cols) if "可见" in c), -1)
        hidden_i = next((i for i, c in enumerate(cols) if "遮挡" in c or "不可见" in c), -1)
        focus_i = next((i for i, c in enumerate(cols) if "重点" in c or "焦点" in c), -1)

        for row in tbl["rows"]:
            result["views"].append({
                "id": row[id_i].strip() if id_i < len(row) else "",
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
        desc_i = next((i for i, c in enumerate(cols) if "描述" in c or "约束" in c), 1)
        reason_i = next((i for i, c in enumerate(cols) if "原因" in c or "说明" in c), -1)

        for row in tbl["rows"]:
            result["constraints"].append({
                "id": row[id_i].strip() if id_i < len(row) else "",
                "description": row[desc_i].strip() if desc_i < len(row) else "",
                "reason": row[reason_i].strip() if reason_i >= 0 and reason_i < len(row) else "",
            })

    return result
