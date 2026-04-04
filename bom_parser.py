#!/usr/bin/env python3
"""
BOM Markdown 解析器 — 从设计文档提取结构化零件树

从 docs/design/NN-*.md 中解析 §X.8 BOM 表，输出 JSON 或树形文本。
解析规则与 §4.8 已有格式一致：
  - 表头含 `料号` 和 `名称` 列
  - 总成行：料号 3 段 (GIS-XX-NNN)，加粗，自制/外购列写 `总成`
  - 零件行：料号 4 段 (GIS-XX-NNN-NN)，归属最近的上方总成
  - 单价：支持 `500元`、`100元×2`、`—`

Usage:
    python tools/bom_parser.py docs/design/04-末端执行机构设计.md
    python tools/bom_parser.py docs/design/04-*.md --json
    python tools/bom_parser.py docs/design/04-*.md --summary
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ─── Part classification ──────────────────────────────────────────────────

# Keyword-based classification for purchased/standard parts
_PART_CATEGORY_RULES = [
    ("reducer",   ["减速器", "减速机", "减速组", "gearbox", "GP22", "GP32", "GP42", "行星"]),
    ("motor",     ["电机", "motor", "ECX", "DC马达", "伺服", "servo", "步进", "NEMA", "stepper"]),
    ("spring",    ["弹簧", "spring", "DIN 2093", "碟簧", "弹性垫圈"]),
    ("bearing",   ["轴承", "bearing", "MR1", "ZZ", "688", "608", "滚珠", "LM10", "LM12",
                   "LM16", "LM20", "LMU", "KFL", "KP0", "KP1", "UCP", "UCF", "法兰座"]),
    ("sensor",    ["传感器", "sensor", "AE", "UHF", "Nano17", "力矩", "检测", "接近开关",
                   "光电", "限位", "编码器", "encoder"]),
    ("pump",      ["泵", "pump", "齿轮泵"]),
    ("connector", ["连接器", "connector", "LEMO", "SMA", "Molex", "ZIF", "插座", "插头",
                   "联轴器", "coupler", "coupling", "L070", "L050"]),
    ("seal",      ["O型圈", "O-ring", "FKM", "NBR", "缓冲垫", "PU垫"]),
    ("tank",      ["储液罐", "储罐", "tank", "容器"]),
    ("cable",     ["线缆", "cable", "FFC", "线束", "拖链", "drag chain", "coax", "同轴",
                   "同步带", "GT2", "皮带", "belt"]),
    ("fastener",  ["螺栓", "螺钉", "螺母", "销", "pin", "screw", "bolt", "定位销",
                   "DIN912", "DIN7991", "DIN933", "挡圈", "钢丝螺套", "护罩"]),
]


def classify_part(name: str, material: str = "") -> str:
    """Classify a BOM part by name/material keywords → category string.

    Returns one of: motor, reducer, spring, bearing, sensor, pump,
    connector, seal, tank, cable, fastener, other.
    """
    text = (name + " " + material).upper()
    for category, keywords in _PART_CATEGORY_RULES:
        if any(kw.upper() in text for kw in keywords):
            return category
    return "other"


# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ─── Price parser ──────────────────────────────────────────────────────────

def parse_price(text: str) -> float:
    """Parse price string like '3,000元', '50元×4', '—' → float."""
    text = text.strip()
    if not text or text in ("—", "—", "-", "N/A"):
        return 0.0
    text = text.replace(",", "").replace("，", "")
    # Match: 数字 元 [×数字]
    m = re.match(r"([\d.]+)\s*元(?:\s*[×xX*]\s*(\d+))?", text)
    if m:
        unit = float(m.group(1))
        mult = int(m.group(2)) if m.group(2) else 1
        return unit * mult
    # Bare number
    m = re.match(r"[\d.]+", text)
    if m:
        return float(m.group(0))
    return 0.0


def parse_unit_price(text: str) -> float:
    """Extract unit price (before ×N multiplier)."""
    text = text.strip().replace(",", "").replace("，", "")
    m = re.match(r"([\d.]+)\s*元", text)
    return float(m.group(1)) if m else 0.0


# ─── Table parser ─────────────────────────────────────────────────────────

def _strip_bold(s: str) -> str:
    return s.replace("**", "").strip()


def _detect_columns(header_cells: list) -> dict:
    """Map column names to indices."""
    mapping = {}
    for i, cell in enumerate(header_cells):
        cell_clean = cell.strip().lower()
        if "料号" in cell_clean or "图号" in cell_clean or "编号" in cell_clean:
            mapping["part_no"] = i
        elif "名称" in cell_clean:
            mapping["name"] = i
        elif "材质" in cell_clean or "型号" in cell_clean:
            mapping["material"] = i
        elif "数量" in cell_clean:
            mapping["qty"] = i
        elif "自制" in cell_clean or "外购" in cell_clean or "类型" in cell_clean:
            mapping["make_buy"] = i
        elif "单价" in cell_clean or "价" in cell_clean:
            mapping["price"] = i
        elif "备注" in cell_clean:
            mapping["note"] = i
    return mapping


def parse_bom_from_markdown(filepath: str) -> dict:
    """Parse BOM table from a Markdown design document.

    Returns dict with keys: subsystem, encoding_rule, assemblies, summary.
    Returns None if no BOM table found.
    """
    path = Path(filepath)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Extract subsystem name from filename: NN-名称设计.md → NN-名称
    fname = path.stem
    m = re.match(r"(\d{2})-(.+?)(?:设计)?$", fname)
    subsystem = f"{m.group(1)}-{m.group(2)}" if m else fname

    # Find BOM table: look for a Markdown table whose header contains 料号 and 名称
    assemblies = []
    current_assy = None
    encoding_rule = ""
    table_found = False

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect encoding rule line (e.g. **编号规则**：GIS-EE-NNN-NN)
        if "编号规则" in line or "编号系统" in line:
            enc_m = re.search(r"GIS-\w+-\w+(?:-\w+)?", line)
            if enc_m:
                encoding_rule = enc_m.group(0)

        # Detect table header
        if "|" in line and ("料号" in line or "图号" in line or "编号" in line) and "名称" in line:
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]  # remove empty from leading/trailing |
            col_map = _detect_columns(cells)

            if "part_no" not in col_map or "name" not in col_map:
                i += 1
                continue

            table_found = True
            # Skip separator line (|---|---|...)
            i += 1
            if i < len(lines) and re.match(r"\s*\|[\s\-:|]+\|", lines[i]):
                i += 1

            # Parse data rows — handle gaps (blockquotes, blank lines) within BOM
            while i < len(lines):
                row = lines[i].strip()
                # Stop at next section heading
                if row.startswith("#"):
                    break
                # Skip non-table rows (blank lines, blockquotes, notes)
                if not row.startswith("|"):
                    i += 1
                    continue
                # Skip separator rows
                if re.match(r"\|[\s\-:|]+\|", row):
                    i += 1
                    continue
                # Only parse rows containing part numbers (GIS-*, SLP-*, or any XX-NNN pattern)
                if not re.search(r"[A-Z]{2,}-[A-Z]?\d", row):
                    i += 1
                    continue
                cells = [c.strip() for c in row.split("|")]
                cells = [c for c in cells if c != ""]

                if len(cells) < 2:
                    i += 1
                    continue

                part_no_raw = cells[col_map["part_no"]] if "part_no" in col_map else ""
                part_no = _strip_bold(part_no_raw)
                name = _strip_bold(cells[col_map["name"]] if "name" in col_map else "")
                material = _strip_bold(cells[col_map.get("material", -1)]) if "material" in col_map and col_map["material"] < len(cells) else ""
                qty_str = cells[col_map.get("qty", -1)] if "qty" in col_map and col_map["qty"] < len(cells) else "1"
                make_buy = _strip_bold(cells[col_map.get("make_buy", -1)]) if "make_buy" in col_map and col_map["make_buy"] < len(cells) else ""
                price_str = cells[col_map.get("price", -1)] if "price" in col_map and col_map["price"] < len(cells) else ""

                qty = int(re.search(r"\d+", qty_str).group(0)) if re.search(r"\d+", qty_str) else 1

                # Determine level by segment count
                segments = [s for s in part_no.split("-") if s]
                is_assembly = (len(segments) <= 3 and ("总成" in make_buy or "装配" in make_buy)) or "**" in part_no_raw

                if is_assembly:
                    current_assy = {
                        "part_no": part_no,
                        "name": name,
                        "parts": []
                    }
                    assemblies.append(current_assy)
                else:
                    part = {
                        "part_no": part_no,
                        "name": name,
                        "material": material,
                        "qty": qty,
                        "make_buy": make_buy,
                        "part_category": classify_part(name, material) if ("外购" in make_buy or "标准" in make_buy) else "custom",
                        "unit_price": parse_unit_price(price_str),
                        "total_price": parse_price(price_str),
                    }
                    if current_assy is not None:
                        current_assy["parts"].append(part)
                    else:
                        # Orphan part — create implicit assembly
                        current_assy = {"part_no": "UNKNOWN", "name": "未分组", "parts": [part]}
                        assemblies.append(current_assy)

                i += 1
            break  # Only parse first BOM table
        i += 1

    if not table_found:
        return None

    # Build summary
    total_parts = sum(len(a["parts"]) for a in assemblies)
    custom = sum(1 for a in assemblies for p in a["parts"] if p["make_buy"] == "自制")
    purchased = sum(1 for a in assemblies for p in a["parts"] if p["make_buy"] == "外购")
    total_cost = sum(p["total_price"] for a in assemblies for p in a["parts"])

    return {
        "subsystem": subsystem,
        "encoding_rule": encoding_rule,
        "assemblies": assemblies,
        "summary": {
            "total_parts": total_parts,
            "assemblies": len(assemblies),
            "custom_parts": custom,
            "purchased_parts": purchased,
            "total_cost": round(total_cost, 2),
        }
    }


# ─── Output formatters ────────────────────────────────────────────────────

def print_tree(data: dict):
    """Print BOM as a tree with summary."""
    print(f"[BOM] {data['subsystem']}  ({data['encoding_rule']})")
    print()
    s = data["summary"]
    for assy in data["assemblies"]:
        print(f"  ├─ {assy['part_no']}  {assy['name']}")
        for j, part in enumerate(assy["parts"]):
            prefix = "  │  └─" if j == len(assy["parts"]) - 1 else "  │  ├─"
            tag = "[自制]" if part["make_buy"] == "自制" else "[外购]"
            price = f"¥{part['total_price']:.0f}" if part["total_price"] > 0 else ""
            print(f"{prefix} {part['part_no']}  {part['name']}  ×{part['qty']}  {tag}  {price}")
    print()
    print(f"  合计: {s['total_parts']}零件 / {s['assemblies']}总成 / "
          f"{s['custom_parts']}自制 / {s['purchased_parts']}外购 / ¥{s['total_cost']:,.0f}")


def print_summary(data: dict):
    """Print summary only."""
    s = data["summary"]
    print(f"{data['subsystem']}: {s['total_parts']}零件, {s['assemblies']}总成, "
          f"{s['custom_parts']}自制, {s['purchased_parts']}外购, ¥{s['total_cost']:,.0f}")


# ─── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="从设计文档 Markdown 提取 BOM 零件树")
    parser.add_argument("file", help="设计文档路径 (docs/design/NN-*.md)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--summary", action="store_true", help="仅输出统计")
    args = parser.parse_args()

    data = parse_bom_from_markdown(args.file)

    if data is None:
        print(f"未找到 BOM 表: {args.file}", file=sys.stderr)
        print("提示: 请在设计文档中添加 §X.8 BOM 章节。", file=sys.stderr)
        print("模板: docs/templates/bom_section_template.md", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.summary:
        print_summary(data)
    else:
        print_tree(data)


if __name__ == "__main__":
    main()
