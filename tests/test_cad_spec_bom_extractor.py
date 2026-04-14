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


class TestClassifyAndFilter:
    def test_classify_category_by_keywords(self):
        """按 name_cn 关键词判定 category。"""
        from tools.cad_spec_bom_extractor import classify_category

        assert classify_category("M6×20 内六角螺钉") == "fastener"
        assert classify_category("深沟球轴承 6205") == "bearing"
        assert classify_category("碟形弹簧垫圈") == "washer"
        assert classify_category("M6 六角螺母") == "nut"
        assert classify_category("Maxon ECX 电机") == "other"
        assert classify_category("法兰本体") == "other"

    def test_filter_standard_only(self):
        """过滤到 category∈{fastener, bearing, washer, nut, screw, pin, key} 且 make_buy∈{外购, 标准}。"""
        from tools.cad_spec_bom_extractor import filter_standard_rows

        rows = [
            {"part_no": "A", "name_cn": "M6 内六角螺钉", "make_buy": "外购", "category": "fastener"},
            {"part_no": "B", "name_cn": "法兰本体", "make_buy": "自制", "category": "other"},
            {"part_no": "C", "name_cn": "轴承 6205", "make_buy": "外购", "category": "bearing"},
            {"part_no": "D", "name_cn": "非标电机", "make_buy": "外购", "category": "other"},
        ]
        kept, excluded = filter_standard_rows(rows)
        assert [r["part_no"] for r in kept] == ["A", "C"]
        assert [r["part_no"] for r in excluded] == ["B", "D"]


class TestWriteCsv:
    def test_writes_expected_columns(self, tmp_path):
        from tools.cad_spec_bom_extractor import write_bom_csv

        rows = [{"part_no": "P1", "name_cn": "M6 螺钉", "material": "钢",
                 "make_buy": "外购", "category": "fastener"}]
        csv_path = tmp_path / "out.csv"
        write_bom_csv(rows, csv_path)

        content = csv_path.read_text(encoding="utf-8")
        assert "part_no,name_cn,material,make_buy,category" in content
        assert "P1,M6 螺钉,钢,外购,fastener" in content
