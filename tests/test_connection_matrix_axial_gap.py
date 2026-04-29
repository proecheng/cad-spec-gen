"""Regression tests for axial_gap extraction and serial offset consumption."""

import os
import sys
import importlib.util
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cad_spec_defaults import compute_serial_offsets
from cad_spec_extractors import extract_connection_matrix


def _load_cad_spec_gen_module():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "_cad_spec_gen_axial_gap_test",
        root / "cad_spec_gen.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_connection_matrix_axial_gap_feeds_serial_offsets():
    lines = [
        "## 连接矩阵",
        "| 零件A | 零件B | 类型 | 轴向间隙(mm) |",
        "| --- | --- | --- | --- |",
        "| TEST-01 | TEST-02 | 垫片隔开 | 0.5 |",
    ]
    connections = extract_connection_matrix(lines, fasteners=[], assembly_layers=[])
    assert connections[0]["axial_gap"] == 0.5

    placements = [{
        "mode": "axial_stack",
        "direction": (0, 0, -1),
        "chain": [
            {"part_name": "A", "part_no": "TEST-01",
             "dims": {"type": "box", "w": 10, "d": 10, "h": 10},
             "connection": None, "sub_assembly": None},
            {"part_name": "B", "part_no": "TEST-02",
             "dims": {"type": "box", "w": 10, "d": 10, "h": 15},
             "connection": None, "sub_assembly": None},
        ],
    }]
    result = compute_serial_offsets(placements, {}, connections)
    assert result["TEST-01"]["z"] == -10.0
    assert result["TEST-02"]["z"] == -25.5


def test_serial_offsets_match_numeric_part_numbers_without_substring_leak():
    connections = [{
        "partA": "100",
        "partB": "200",
        "type": "轴向间隙0.5mm",
        "fit": "",
        "torque": "",
        "axial_gap": 0.5,
        "order": 1,
    }]
    placements = [{
        "mode": "axial_stack",
        "direction": (0, 0, -1),
        "chain": [
            {"part_name": "A", "part_no": "100",
             "dims": {"type": "box", "w": 10, "d": 10, "h": 10}},
            {"part_name": "B", "part_no": "200",
             "dims": {"type": "box", "w": 10, "d": 10, "h": 15}},
        ],
    }]
    result = compute_serial_offsets(placements, {}, connections)
    assert result["200"]["z"] == -25.5

    leaked = dict(connections[0])
    leaked["partA"] = "1000"
    result = compute_serial_offsets(placements, {}, [leaked])
    assert result["200"]["z"] == -25.0


def test_serial_offsets_clamp_negative_or_invalid_axial_gap():
    placements = [{
        "mode": "axial_stack",
        "direction": (0, 0, -1),
        "chain": [
            {"part_name": "A", "part_no": "TEST-01",
             "dims": {"type": "box", "w": 10, "d": 10, "h": 10}},
            {"part_name": "B", "part_no": "TEST-02",
             "dims": {"type": "box", "w": 10, "d": 10, "h": 15}},
        ],
    }]
    base = {
        "partA": "TEST-01",
        "partB": "TEST-02",
        "type": "过盈配合",
        "fit": "",
        "torque": "",
        "order": 1,
    }
    for raw_gap in (-0.5, "bad"):
        conn = dict(base, axial_gap=raw_gap)
        result = compute_serial_offsets(placements, {}, [conn])
        assert result["TEST-02"]["z"] == -25.0


def test_connection_matrix_plain_z_offset_is_not_axial_gap():
    layers = [
        {
            "level": "L2",
            "part": "ASSY-001",
            "connection": "基准",
            "offset": "Z=0",
            "exclude": False,
        },
        {
            "level": "L3",
            "part": "ASSY-001-01",
            "connection": "螺栓连接",
            "offset": "Z=+73mm",
            "exclude": False,
        },
    ]
    connections = extract_connection_matrix([], fasteners=[], assembly_layers=layers)
    assert connections[0]["axial_gap"] == 0.0


def test_connection_matrix_radial_clearance_is_not_axial_gap():
    lines = [
        "## 连接矩阵",
        "| 零件A | 零件B | 类型 |",
        "| --- | --- | --- |",
        "| TEST-01 | TEST-02 | H7/h7 径向间隙0.02mm |",
    ]
    connections = extract_connection_matrix(lines, fasteners=[], assembly_layers=[])
    assert connections[0]["axial_gap"] == 0.0


def test_markdown_renders_axial_gap_column():
    cad_spec_gen = _load_cad_spec_gen_module()
    md = cad_spec_gen.render_spec("00", "design.md", "md5", {
        "connections": [{
            "partA": "TEST-01",
            "partB": "TEST-02",
            "type": "垫片隔开",
            "fit": "",
            "torque": "",
            "axial_gap": 0.5,
            "order": 1,
        }],
    })
    assert "| 零件A | 零件B | 连接类型 | 配合代号 | 预紧力矩 | 轴向间隙(mm) | 装配顺序 |" in md
    assert "| TEST-01 | TEST-02 | 垫片隔开 |  |  | 0.5 | 1 |" in md
