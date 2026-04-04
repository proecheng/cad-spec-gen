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


# ── Task 3: Dimension parser tests ──

def test_parse_dims_text_cylinder():
    from gen_assembly import _parse_dims_text
    w, d, h = _parse_dims_text("SUS316L不锈钢 Φ38×280mm")
    assert (w, d, h) == (38.0, 38.0, 280.0)

def test_parse_dims_text_box():
    from gen_assembly import _parse_dims_text
    w, d, h = _parse_dims_text("6063铝合金 140×100×55mm")
    assert (w, d, h) == (140.0, 100.0, 55.0)

def test_parse_dims_text_diameter_only():
    from gen_assembly import _parse_dims_text
    w, d, h = _parse_dims_text("PEEK Φ86mm")
    assert w == 86.0
    assert h > 0

def test_parse_dims_text_no_dims():
    from gen_assembly import _parse_dims_text
    assert _parse_dims_text("7075-T6铝合金") is None
    assert _parse_dims_text("") is None

# ── Task 4: Offset resolution tests ──

@pytest.fixture
def sample_bom():
    return [
        {"part_no": "GIS-XX-002", "name_cn": "工位A", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-002-01", "name_cn": "壳体", "is_assembly": False,
         "material": "铝合金 60×40×55mm", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-002-02", "name_cn": "储罐", "is_assembly": False,
         "material": "不锈钢 Φ38×280mm", "make_buy": "外购", "quantity": "1"},
        {"part_no": "GIS-XX-002-03", "name_cn": "泵", "is_assembly": False,
         "material": "—", "make_buy": "外购", "quantity": "1"},
    ]

def test_offsets_explicit_z(sample_bom):
    from gen_assembly import _resolve_child_offsets
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0, "axis_dir": "轴沿-Z", "is_origin": False},
        "GIS-XX-002-01": {"z": -10.0, "r": None, "theta": None, "axis_dir": "", "is_origin": False},
    }
    offsets = _resolve_child_offsets(sample_bom, layer_poses)
    assert offsets["GIS-XX-002-01"] == (0, 0, -10.0)

def test_offsets_auto_stack_no_overlap(sample_bom):
    from gen_assembly import _resolve_child_offsets
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0, "axis_dir": "轴沿-Z", "is_origin": False},
    }
    offsets = _resolve_child_offsets(sample_bom, layer_poses)
    zs = [offsets[p["part_no"]][2] for p in sample_bom if not p["is_assembly"]]
    assert len(set(zs)) == len(zs), f"Duplicate Z offsets: {zs}"
    assert all(z <= 0 for z in zs), f"Expected all Z ≤ 0 for -Z stacking: {zs}"

def test_offsets_auto_stack_order(sample_bom):
    from gen_assembly import _resolve_child_offsets
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0, "axis_dir": "轴沿-Z", "is_origin": False},
    }
    offsets = _resolve_child_offsets(sample_bom, layer_poses)
    z_body = offsets["GIS-XX-002-01"][2]
    z_tank = offsets["GIS-XX-002-02"][2]
    z_pump = offsets["GIS-XX-002-03"][2]
    assert z_body >= z_tank, f"Body {z_body} should be above tank {z_tank}"
    assert z_body >= z_pump, f"Body {z_body} should be above pump {z_pump}"

def test_offsets_per_part_axis_dir():
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-002", "name_cn": "涂抹工位", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-002-01", "name_cn": "壳体", "is_assembly": False,
         "material": "铝合金 60×40×55mm", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-002-02", "name_cn": "储罐", "is_assembly": False,
         "material": "不锈钢 Φ38×280mm", "make_buy": "外购", "quantity": "1"},
    ]
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0,
                        "axis_dir": "壳体轴沿-Z（垂直向下），储罐轴∥XY（水平径向外伸）",
                        "is_origin": False},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    assert offsets["GIS-XX-002-01"][0] == 0
    assert offsets["GIS-XX-002-01"][2] <= 0
    assert offsets["GIS-XX-002-02"][0] != 0
    assert offsets["GIS-XX-002-02"][2] == 0

def test_offsets_no_layer_data(sample_bom):
    from gen_assembly import _resolve_child_offsets
    offsets = _resolve_child_offsets(sample_bom, {})
    zs = [offsets[p["part_no"]][2] for p in sample_bom if not p["is_assembly"]]
    assert len(set(zs)) == len(zs), f"Duplicate Z offsets: {zs}"

def test_offsets_non_radial():
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-001", "name_cn": "法兰总成", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-001-01", "name_cn": "法兰", "is_assembly": False,
         "material": "铝合金", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-001-02", "name_cn": "PEEK环", "is_assembly": False,
         "material": "PEEK", "make_buy": "自制", "quantity": "1"},
    ]
    layer_poses = {
        "GIS-XX-001-01": {"z": 0.0, "r": None, "theta": None, "axis_dir": "盘面∥XY", "is_origin": False},
        "GIS-XX-001-02": {"z": -27.0, "r": None, "theta": None, "axis_dir": "盘面∥XY", "is_origin": False},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    assert offsets["GIS-XX-001-01"] == (0, 0, 0.0)
    assert offsets["GIS-XX-001-02"] == (0, 0, -27.0)


def test_integration_end_effector():
    """Generate assembly.py for end_effector and verify positioning correctness."""
    spec_path = os.path.join(
        os.path.dirname(__file__), "..", "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.exists(spec_path):
        pytest.skip("end_effector CAD_SPEC.md not found")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from codegen.gen_build import parse_bom_tree
    from gen_assembly import generate_assembly, _extract_all_layer_poses
    from gen_assembly import parse_assembly_pose, _resolve_child_offsets

    content = generate_assembly(spec_path)
    parts = parse_bom_tree(spec_path)
    pose = parse_assembly_pose(spec_path)
    layer_poses = _extract_all_layer_poses(pose, parts)
    offsets = _resolve_child_offsets(parts, layer_poses)

    # 1. Zero offset should never emit a translate call
    assert ".translate((0, 0, 0))" not in content
    assert ".translate((0.0, 0.0, 0.0))" not in content

    # 2. PEEK ring Z=-27 must be present
    assert "-27" in content, "PEEK ring Z=-27 offset not found"

    # 3. Motor Z=+73 must be present (from name-fallback)
    assert "73" in content, "Motor Z=+73 offset not found"

    # 4. Each station should have at least one translate before _station_transform
    lines = content.splitlines()
    stations_with_translate = 0
    for i, line in enumerate(lines):
        if "_station_transform" in line and "def " not in line:
            var = line.strip().split("=")[0].strip()
            window = "\n".join(lines[max(0, i - 8):i])
            if ".translate(" in window and var in window:
                stations_with_translate += 1
    assert stations_with_translate >= 4, \
        f"Expected ≥4 station parts with translate, got {stations_with_translate}"

    # 5. Offsets dict should cover all non-assembly parts
    non_assy = [p for p in parts if not p["is_assembly"]]
    assert len(offsets) >= len(non_assy), \
        f"Expected offsets for all {len(non_assy)} parts, got {len(offsets)}"
