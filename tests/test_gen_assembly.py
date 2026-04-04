# tests/test_gen_assembly.py
"""Tests for codegen/gen_assembly.py positioning logic."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "codegen"))


@pytest.fixture
def sample_layers():
    return {"layers": [
        {"level": "L1", "part": "适配板 (GIS-XX-001-08)", "fix_move": "固定",
         "connection": "4×M6", "offset": "基准原点", "axis_dir": "盘面∥XY"},
        {"level": "L2", "part": "ECX 22L电机+GP22C减速器", "fix_move": "固定",
         "connection": "4×M3", "offset": "Z=+73mm(向上)", "axis_dir": "轴沿Z"},
        {"level": "L3", "part": "法兰 Φ90mm (GIS-XX-001-01)", "fix_move": "旋转",
         "connection": "过盈配合", "offset": "Z=0(参考面)", "axis_dir": "盘面∥XY"},
        {"level": "L4", "part": "PEEK环 (GIS-XX-001-02)", "fix_move": "随旋转",
         "connection": "6×M3", "offset": "Z=-27mm(向下)", "axis_dir": "盘面∥XY"},
        {"level": "L5a", "part": "工位A (GIS-XX-002)", "fix_move": "随旋转",
         "connection": "4×M3", "offset": "R=65mm, θ=0°", "axis_dir": "轴沿-Z"},
        {"level": "L5b", "part": "工位B (GIS-XX-003)", "fix_move": "随旋转",
         "connection": "4×M3", "offset": "R=65mm, θ=90°", "axis_dir": "轴沿-Z"},
    ]}


@pytest.fixture
def sample_bom_for_layers():
    return [
        {"part_no": "GIS-XX-001-05", "name_cn": "伺服电机", "is_assembly": False,
         "material": "Maxon ECX SPEED 22L", "make_buy": "外购", "quantity": "1"},
        {"part_no": "GIS-XX-001-06", "name_cn": "行星减速器", "is_assembly": False,
         "material": "Maxon GP22C", "make_buy": "外购", "quantity": "1"},
    ]


def test_extract_z_only(sample_layers, sample_bom_for_layers):
    from gen_assembly import _extract_all_layer_poses
    poses = _extract_all_layer_poses(sample_layers, sample_bom_for_layers)
    assert poses["GIS-XX-001-08"]["z"] == 0.0
    assert poses["GIS-XX-001-08"]["is_origin"] is True
    assert poses["GIS-XX-001-01"]["z"] == 0.0
    assert poses["GIS-XX-001-02"]["z"] == -27.0


def test_extract_radial(sample_layers, sample_bom_for_layers):
    from gen_assembly import _extract_all_layer_poses
    poses = _extract_all_layer_poses(sample_layers, sample_bom_for_layers)
    assert poses["GIS-XX-002"]["r"] == 65.0
    assert poses["GIS-XX-002"]["theta"] == 0.0
    assert poses["GIS-XX-003"]["theta"] == 90.0


def test_extract_axis_dir(sample_layers, sample_bom_for_layers):
    from gen_assembly import _extract_all_layer_poses
    poses = _extract_all_layer_poses(sample_layers, sample_bom_for_layers)
    assert poses["GIS-XX-001-01"]["axis_dir"] == "盘面∥XY"
    assert poses["GIS-XX-002"]["axis_dir"] == "轴沿-Z"


def test_extract_name_fallback(sample_layers, sample_bom_for_layers):
    from gen_assembly import _extract_all_layer_poses
    poses = _extract_all_layer_poses(sample_layers, sample_bom_for_layers)
    assert "GIS-XX-001-05" in poses
    assert poses["GIS-XX-001-05"]["z"] == 73.0


def test_extract_empty():
    from gen_assembly import _extract_all_layer_poses
    assert _extract_all_layer_poses({"layers": []}, []) == {}
    assert _extract_all_layer_poses({}, []) == {}
