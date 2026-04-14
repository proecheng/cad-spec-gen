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
