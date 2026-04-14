"""tools/cad_spec_bom_extractor 单元测试。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


SAMPLE_MD = """# CAD_SPEC

## 3. 紧固件清单

| 连接位置 | 螺栓规格 | 数量 | 力矩(Nm) | 材料等级 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 法兰→RM65 | M6×12 内六角 12.9级 | 4 | 9.0±0.5 |  | 标准 |
| PEEK段→法兰 | M3×10 内六角 A2-70不锈钢 | 6 | 0.7±0.1 |  | 标准 |

## 5. BOM树

| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |
| --- | --- | --- | --- | --- | --- |
| **GIS-EE-001** | **法兰总成** | — | 1 | 总成 | — |
| GIS-EE-001-01 | 法兰本体 | 7075-T6铝合金 | 1 | 自制 | 3000元 |
| GIS-EE-001-04 | 碟形弹簧垫圈 | DIN 2093 A6 | 6 | 外购 | 30元 |
| GIS-EE-001-05 | 伺服电机 | Maxon ECX | 1 | 外购 | 2500元 |
"""


class TestExtractFastenersSection:
    def test_parses_section_3_rows(self, tmp_path):
        from tools.cad_spec_bom_extractor import extract_fasteners

        md = tmp_path / "spec.md"
        md.write_text(SAMPLE_MD, encoding="utf-8")

        rows = extract_fasteners(md)
        assert len(rows) == 2
        assert rows[0]["spec"] == "M6×12 内六角 12.9级"
        assert rows[0]["qty"] == 4
        assert rows[1]["spec"] == "M3×10 内六角 A2-70不锈钢"

    def test_missing_section_returns_empty(self, tmp_path):
        from tools.cad_spec_bom_extractor import extract_fasteners

        md = tmp_path / "no_s3.md"
        md.write_text("# no section 3 here\n## 1. foo\n", encoding="utf-8")
        assert extract_fasteners(md) == []


class TestExtractBomTree:
    def test_parses_section_5_skips_assembly_rows(self, tmp_path):
        """加粗总成行（**GIS-EE-001**）被跳过，只保留 leaf 零件。"""
        from tools.cad_spec_bom_extractor import extract_bom_tree

        md = tmp_path / "spec.md"
        md.write_text(SAMPLE_MD, encoding="utf-8")

        rows = extract_bom_tree(md)
        # SAMPLE_MD §5 有 1 加粗总成 + 3 零件 = 应返回 3 零件
        part_nos = [r["part_no"] for r in rows]
        assert "GIS-EE-001" not in part_nos  # 总成跳过
        assert "GIS-EE-001-01" in part_nos
        assert "GIS-EE-001-04" in part_nos
        assert "GIS-EE-001-05" in part_nos

    def test_extracts_make_buy(self, tmp_path):
        from tools.cad_spec_bom_extractor import extract_bom_tree

        md = tmp_path / "spec.md"
        md.write_text(SAMPLE_MD, encoding="utf-8")

        rows = extract_bom_tree(md)
        row_by_pn = {r["part_no"]: r for r in rows}
        assert row_by_pn["GIS-EE-001-01"]["make_buy"] == "自制"
        assert row_by_pn["GIS-EE-001-04"]["make_buy"] == "外购"
