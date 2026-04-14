"""从 CAD_SPEC.md 抽 §3 紧固件清单 + §5 BOM 树，输出 CSV。

用于 SW-B9 Stage B：把真实项目 CAD_SPEC 转为可被 sw_warmup 匹配的 BOM。
见 docs/superpowers/specs/2026-04-14-sw-b9-real-run-acceptance-design.md §5.4。
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any


SECTION_3_HEADER = re.compile(r"^##\s+3\.\s*紧固件", re.MULTILINE)
SECTION_5_HEADER = re.compile(r"^##\s+5\.\s*BOM", re.MULTILINE)
NEXT_SECTION = re.compile(r"^##\s+\d+\.", re.MULTILINE)


def _slice_section(text: str, header_re: re.Pattern) -> str:
    """截取从 header 开始到下一个 ## 章节之间的片段。"""
    m = header_re.search(text)
    if not m:
        return ""
    start = m.end()
    rest = text[start:]
    next_m = NEXT_SECTION.search(rest)
    end = next_m.start() if next_m else len(rest)
    return rest[:end]


def _parse_markdown_table(block: str) -> list[list[str]]:
    """解析 markdown 表格，跳过表头与分隔行，返回数据行的 cell 列表。"""
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or all(set(c) <= {"-", " "} for c in cells):
            continue  # 分隔行
        rows.append(cells)
    return rows[1:] if len(rows) > 1 else []  # 跳过表头


def extract_fasteners(md_path: Path) -> list[dict[str, Any]]:
    """解析 §3 紧固件清单。"""
    text = Path(md_path).read_text(encoding="utf-8")
    block = _slice_section(text, SECTION_3_HEADER)
    if not block:
        return []
    rows = _parse_markdown_table(block)
    out = []
    for r in rows:
        if len(r) < 3:
            continue
        try:
            qty = int(r[2])
        except ValueError:
            qty = 1
        out.append({"location": r[0], "spec": r[1], "qty": qty})
    return out


def _is_assembly_row(cells: list[str]) -> bool:
    """总成行以 '**' 包裹料号。"""
    return cells[0].startswith("**") and cells[0].endswith("**")


def extract_bom_tree(md_path: Path) -> list[dict[str, Any]]:
    """解析 §5 BOM 树（跳过加粗总成行，只返回 leaf 零件）。"""
    text = Path(md_path).read_text(encoding="utf-8")
    block = _slice_section(text, SECTION_5_HEADER)
    if not block:
        return []

    rows = _parse_markdown_table(block)
    out = []
    for r in rows:
        if len(r) < 5:
            continue
        if _is_assembly_row(r):
            continue
        out.append({
            "part_no": r[0],
            "name_cn": r[1],
            "material": r[2],
            "qty_raw": r[3],
            "make_buy": r[4],
        })
    return out


# dict 顺序 = 匹配优先级；具体类别（nut/washer/bearing/pin/key）必须先于泛用 fastener
# 避免 "内六角螺母" 因先命中 fastener 的 "内六角" 而被误分类。
CATEGORY_KEYWORDS = {
    "nut": ["螺母", "nut"],
    "washer": ["垫圈", "washer", "碟形弹簧"],
    "bearing": ["轴承", "bearing"],
    "pin": ["销", "pin"],
    "key": ["键 ", "key"],
    "fastener": ["螺钉", "螺栓", "紧定", "内六角", "socket head"],
    "screw": [],  # screw 同 fastener，保留占位
}

STANDARD_CATEGORIES = {"fastener", "bearing", "washer", "nut", "screw", "pin", "key"}
STANDARD_MAKE_BUY = {"外购", "标准", "外购标准件"}


def classify_category(name_cn: str) -> str:
    """按关键词识别 category；任何都不命中返回 'other'。"""
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in name_cn:
                return cat
    return "other"


def filter_standard_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 category + make_buy 过滤。返回 (kept, excluded)。"""
    kept, excluded = [], []
    for r in rows:
        cat = r.get("category") or classify_category(r.get("name_cn", ""))
        mb = r.get("make_buy", "")
        if cat in STANDARD_CATEGORIES and mb in STANDARD_MAKE_BUY:
            r["category"] = cat
            kept.append(r)
        else:
            r["category"] = cat
            excluded.append(r)
    return kept, excluded


def write_bom_csv(rows: list[dict[str, Any]], csv_path: Path) -> None:
    """写 CSV，字段对齐 tests/fixtures/sw_warmup_demo_bom.csv schema。"""
    fieldnames = ["part_no", "name_cn", "material", "make_buy", "category"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="CAD_SPEC.md → BOM CSV 抽取器")
    parser.add_argument("--input", required=True, help="CAD_SPEC.md 路径")
    parser.add_argument("--output", required=True, help="输出 CSV 路径")
    parser.add_argument("--output-excluded", help="被排除行的 CSV（可选）")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    fasteners = extract_fasteners(in_path)
    # §3 紧固件清单没有 part_no，用 location 占位
    fastener_rows = [
        {
            "part_no": f"FAST-{i:03d}",
            "name_cn": f["spec"],
            "material": "",
            "make_buy": "外购",
            "category": classify_category(f["spec"]),
        }
        for i, f in enumerate(fasteners, 1)
    ]

    bom_rows = extract_bom_tree(in_path)
    for r in bom_rows:
        r["category"] = classify_category(r.get("name_cn", ""))

    all_rows = fastener_rows + bom_rows
    kept, excluded = filter_standard_rows(all_rows)

    write_bom_csv(kept, out_path)
    if args.output_excluded:
        write_bom_csv(excluded, Path(args.output_excluded))

    print(f"total={len(all_rows)} kept={len(kept)} excluded={len(excluded)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
