"""Tests for XY layout instance extraction from design documents."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_extract_part_placements_reads_column_xy_layout():
    from cad_spec_extractors import extract_part_placements

    lines = """
采用 2 丝杠 + 2 导向轴 对角线布局：

| 立柱 | 类型 | XY 坐标 | 功能 |
|------|------|---------|------|
| LS1 | Tr16×4 丝杠 | (−60, +30) | 驱动 + 承载 |
| LS2 | Tr16×4 丝杠 | (+60, −30) | 驱动 + 承载（电机直连） |
| GS1 | φ10 导向轴 | (+60, +30) | 导向 + 防转 |
| GS2 | φ10 导向轴 | (−60, −30) | 导向 + 防转 |
""".splitlines()
    bom = {
        "assemblies": [{
            "part_no": "UNKNOWN",
            "parts": [
                {"part_no": "SLP-P01", "name": "丝杠 L350"},
                {"part_no": "SLP-P02", "name": "导向轴 L296"},
            ],
        }],
    }

    placements = extract_part_placements(lines, bom, [])
    layout = [p for p in placements if p.get("mode") == "layout_xy"]

    assert layout, "Expected a layout_xy placement from the column table"
    instances = {
        item["instance_id"]: item
        for placement in layout
        for item in placement.get("instances", [])
    }
    assert instances["LS1"]["part_no"] == "SLP-P01"
    assert instances["LS1"]["x"] == -60.0
    assert instances["LS1"]["y"] == 30.0
    assert instances["LS2"]["part_no"] == "SLP-P01"
    assert instances["LS2"]["x"] == 60.0
    assert instances["LS2"]["y"] == -30.0
    assert instances["GS1"]["part_no"] == "SLP-P02"
    assert instances["GS1"]["x"] == 60.0
    assert instances["GS1"]["y"] == 30.0
    assert instances["GS2"]["part_no"] == "SLP-P02"
    assert instances["GS2"]["x"] == -60.0
    assert instances["GS2"]["y"] == -30.0


def test_xy_layout_derived_parts_prefer_functional_parts_over_covers_and_brackets():
    from cad_spec_extractors import extract_part_placements

    lines = """
| 立柱 | 类型 | XY 坐标 | 功能 |
|------|------|---------|------|
| LS1 | Tr16×4 丝杠 | (−60, +30) | 驱动 |
| LS2 | Tr16×4 丝杠 | (+60, −30) | 驱动（电机直连） |
| GS1 | φ10 导向轴 | (+60, +30) | 导向 |
| GS2 | φ10 导向轴 | (−60, −30) | 导向 |
""".splitlines()
    bom = {
        "assemblies": [{
            "part_no": "UNKNOWN",
            "parts": [
                {"part_no": "SLP-P01", "name": "丝杠 L350"},
                {"part_no": "SLP-P02", "name": "导向轴 L296"},
                {"part_no": "SLP-400", "name": "电机支架"},
                {"part_no": "SLP-500", "name": "同步带护罩"},
                {"part_no": "SLP-C05", "name": "GT2-310-6mm 带"},
                {"part_no": "SLP-C07", "name": "NEMA23 闭环步进 ≥1.0Nm"},
                {"part_no": "SLP-F11", "name": "PU 缓冲垫 20×20×3"},
                {"part_no": "SLP-F13", "name": "导向轴保护帽 φ10"},
            ],
        }],
    }

    placements = extract_part_placements(lines, bom, [])
    instances = {
        item["instance_id"]: item
        for placement in placements if placement.get("mode") == "layout_xy"
        for item in placement.get("instances", [])
    }

    assert instances["BELT"]["part_no"] == "SLP-C05"
    assert instances["BELT-COVER"]["part_no"] == "SLP-500"
    assert instances["LS2-MOTOR"]["part_no"] == "SLP-C07"
    assert instances["LS2-MOTOR-BRACKET"]["part_no"] == "SLP-400"
    assert instances["LS1-BUFFER-BOT"]["part_no"] == "SLP-F11"
    assert instances["LS2-BUFFER-TOP"]["part_no"] == "SLP-F11"
    assert instances["GS1-CAP-BOT"]["part_no"] == "SLP-F13"
    assert instances["GS2-CAP-TOP"]["part_no"] == "SLP-F13"
