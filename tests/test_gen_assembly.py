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

def test_serial_chain_skips_connection_nodes():
    """Connection-only nodes (e.g. '[4×M3螺栓]') must not advance cursor.

    Regression for Bug A: Each bracket item in a serial chain was adding
    20mm of phantom height, inflating §6.3 Z values by ~3x for chains
    with many fastener annotations.
    """
    # Import via explicit file path to bypass sys.path pollution from
    # other test files (e.g. test_render_config.py inserts cad/end_effector/
    # which contains a stale cad_spec_defaults.py without this function).
    import importlib.util
    _csd_path = os.path.join(
        os.path.dirname(__file__), "..", "cad_spec_defaults.py")
    _spec = importlib.util.spec_from_file_location(
        "_csd_canonical", _csd_path)
    _csd = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_csd)
    compute_serial_offsets = _csd.compute_serial_offsets
    placements = [{
        "mode": "axial_stack",
        "direction": (0, 0, -1),
        "chain": [
            {"part_name": "传感器A", "part_no": "TEST-01",
             "dims": {"type": "cylinder", "d": 20, "h": 10},
             "connection": None, "sub_assembly": None},
            # Connection-only node — no name, no dims, no part_no
            {"part_name": "", "part_no": None, "dims": None,
             "connection": "4×M3螺栓", "sub_assembly": None},
            {"part_name": "传感器B", "part_no": "TEST-02",
             "dims": {"type": "cylinder", "d": 20, "h": 15},
             "connection": None, "sub_assembly": None},
        ],
    }]
    result = compute_serial_offsets(placements, {})
    # Sensor A: cursor 0 → bottom -10
    assert result["TEST-01"]["z"] == -10.0
    # Connection node skipped; cursor stays at -10
    # Sensor B: cursor -10 → bottom -25 (not -45 as before the fix)
    assert result["TEST-02"]["z"] == -25.0


def test_high_confidence_bypasses_outlier_guard():
    """High-confidence §6.3 entries should bypass _max_span guard.

    Regression for Bug B: When §6.4 envelope coverage is sparse, _max_span
    is artificially tight and may reject legitimate serial-chain Z values.
    """
    import tempfile
    import textwrap
    from gen_assembly import _resolve_child_offsets

    spec_md = textwrap.dedent("""\
        # Test Spec

        ### 6.3 零件级定位

        #### GIS-XX-002 测试总成

        | 料号 | 零件名 | 模式 | 高度(mm) | 底面Z(mm) | 来源 | 置信度 |
        | --- | --- | --- | --- | --- | --- | --- |
        | GIS-XX-002-01 | 远端零件 | axial_stack | 20.0 | -250.0 | serial_chain | high |

        ### 6.4 零件包络尺寸

        | 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |
        | --- | --- | --- | --- | --- |
        | GIS-XX-002-01 | 远端零件 | cylinder | Φ20×20 | chain |
    """)
    with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(spec_md)
        spec_path = f.name
    try:
        bom = [
            {"part_no": "GIS-XX-002", "name_cn": "测试总成",
             "is_assembly": True, "material": "—",
             "make_buy": "总成", "quantity": "1"},
            {"part_no": "GIS-XX-002-01", "name_cn": "远端零件",
             "is_assembly": False, "material": "铝合金",
             "make_buy": "自制", "quantity": "1"},
        ]
        layer_poses = {
            "GIS-XX-002": {"z": None, "r": 65, "theta": 0,
                           "axis_dir": "轴沿-Z", "is_origin": False},
        }
        offsets = _resolve_child_offsets(bom, layer_poses, spec_path=spec_path)
        # Z=-250 would normally be rejected (abs=250 > _max_span ~150),
        # but confidence="high" must bypass the guard.
        assert offsets["GIS-XX-002-01"] == (0, 0, -250.0), (
            f"High-confidence §6.3 value should be trusted: {offsets}")
    finally:
        os.unlink(spec_path)


def test_parse_part_positions_supports_xy_instance_table():
    """§6.3 new contract must preserve repeated XY instances per part."""
    import tempfile
    import textwrap
    from gen_assembly import _parse_part_positions

    spec_md = textwrap.dedent("""\
        # CAD Spec — 升降平台 (SLP)

        ### 6.3 零件级定位

        #### UNKNOWN 未分组

        | 实例 | 料号 | 零件名 | 模式 | X(mm) | Y(mm) | 底面Z(mm) | 高度(mm) | 来源 | 置信度 |
        | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
        | LS1 | SLP-P01 | 丝杠 L350 | layout_xy | -60 | 30 | 0 | 350 | column_xy | high |
        | LS2 | SLP-P01 | 丝杠 L350 | layout_xy | 60 | -30 | 0 | 350 | column_xy | high |
        | GS1 | SLP-P02 | 导向轴 L296 | layout_xy | 60 | 30 | 0 | 296 | column_xy | high |
    """)
    with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(spec_md)
        spec_path = f.name
    try:
        positions = _parse_part_positions(spec_path)
        p01 = positions["SLP-P01"]
        assert len(p01["instances"]) == 2
        assert p01["instances"][0]["instance_id"] == "LS1"
        assert p01["instances"][0]["x"] == -60.0
        assert p01["instances"][0]["y"] == 30.0
        assert p01["instances"][1]["instance_id"] == "LS2"
        assert p01["instances"][1]["x"] == 60.0
        assert p01["instances"][1]["y"] == -30.0
        assert positions["SLP-P02"]["instances"][0]["instance_id"] == "GS1"
    finally:
        os.unlink(spec_path)


def test_generate_assembly_emits_xy_multi_instances():
    """Repeated BOM rows with §6.3 instances should emit repeated parts."""
    import tempfile
    import textwrap
    from gen_assembly import generate_assembly

    spec_md = textwrap.dedent("""\
        # CAD Spec — 升降平台 (SLP)

        ## 5. BOM树

        | 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |
        | --- | --- | --- | --- | --- | --- |
        | **UNKNOWN** | **未分组** | — | 1 | 总成 | — |
        | SLP-P01 | 丝杠 L350 | 45#钢 Φ16×350mm | 2 | 自制 | — |
        | SLP-P02 | 导向轴 L296 | GCr15 Φ10×296mm | 2 | 自制 | — |

        ## 6. 装配姿态与定位

        ### 6.2 装配层叠

        | 层级 | 零件/模块 | 固定/运动 | 连接方式 | 偏移(Z/R/θ) | 轴线方向 | 排除 |
        | --- | --- | --- | --- | --- | --- | --- |
        | 1 | 丝杠与导向轴 | 固定 | — | 基准原点 | 轴沿Z |  |

        ### 6.3 零件级定位

        #### UNKNOWN 未分组

        | 实例 | 料号 | 零件名 | 模式 | X(mm) | Y(mm) | 底面Z(mm) | 高度(mm) | 来源 | 置信度 |
        | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
        | LS1 | SLP-P01 | 丝杠 L350 | layout_xy | -60 | 30 | 0 | 350 | column_xy | high |
        | LS2 | SLP-P01 | 丝杠 L350 | layout_xy | 60 | -30 | 0 | 350 | column_xy | high |
        | GS1 | SLP-P02 | 导向轴 L296 | layout_xy | 60 | 30 | 0 | 296 | column_xy | high |
        | GS2 | SLP-P02 | 导向轴 L296 | layout_xy | -60 | -30 | 0 | 296 | column_xy | high |

        ### 6.4 零件包络尺寸

        | 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |
        | --- | --- | --- | --- | --- |
        | SLP-P01 | 丝杠 L350 | cylinder | Φ16×350 | design |
        | SLP-P02 | 导向轴 L296 | cylinder | Φ10×296 | design |
    """)
    with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(spec_md)
        spec_path = f.name
    try:
        content = generate_assembly(spec_path)
        assert content.count("make_p01()") == 2
        assert content.count("make_p02()") == 2
        assert 'name="P01-LS1"' in content
        assert 'name="P01-LS2"' in content
        assert 'name="P02-GS1"' in content
        assert 'name="P02-GS2"' in content
        assert ".translate((-60.0, 30.0, 0.0))" in content
        assert ".translate((60.0, -30.0, 0.0))" in content
    finally:
        os.unlink(spec_path)


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

    # 3. Motor+reducer z_is_top=73: should be split into two non-overlapping
    #    offsets that stack sequentially with combined top at Z=73.
    motor_pnos = [p["part_no"] for p in parts
                  if "电机" in p.get("name_cn", "") and "GIS-EE-001" in p["part_no"]]
    reducer_pnos = [p["part_no"] for p in parts
                    if "减速器" in p.get("name_cn", "") and "GIS-EE-001" in p["part_no"]]
    if motor_pnos and reducer_pnos:
        mz = offsets[motor_pnos[0]][2]
        rz = offsets[reducer_pnos[0]][2]
        assert mz != rz, f"Motor and reducer overlap at Z={mz}"

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


# ── Fix A: is_orphan detection with positioned children ──

def test_orphan_false_when_children_positioned():
    """Assembly with positioned children should NOT be orphan."""
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-001", "name_cn": "法兰总成", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-001-01", "name_cn": "法兰本体", "is_assembly": False,
         "material": "铝合金", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-001-02", "name_cn": "PEEK环", "is_assembly": False,
         "material": "PEEK", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-001-03", "name_cn": "碟簧", "is_assembly": False,
         "material": "钢", "make_buy": "外购", "quantity": "4"},
    ]
    # GIS-XX-001 has no direct entry; children 01/02 have explicit Z.
    layer_poses = {
        "GIS-XX-001-01": {"z": 0.0, "r": None, "theta": None,
                          "axis_dir": "盘面∥XY", "is_origin": True},
        "GIS-XX-001-02": {"z": -27.0, "r": None, "theta": None,
                          "axis_dir": "盘面∥XY", "is_origin": False},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    # 碟簧 auto-stacked: should be BELOW the lowest anchor (Z=-27) since
    # default_direction for empty axis_dir is (0,0,-1) and NOT orphan.
    assert offsets["GIS-XX-001-03"][2] < -27.0, \
        f"Disc spring should be below PEEK(-27), got Z={offsets['GIS-XX-001-03'][2]}"


# ── Fix B: z_is_top group sequential stacking ──

def test_z_is_top_group_no_overlap():
    """Two parts sharing z_is_top should stack sequentially, not overlap."""
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-001", "name_cn": "法兰总成", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-001-08", "name_cn": "适配板", "is_assembly": False,
         "material": "铝合金", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-001-05", "name_cn": "伺服电机", "is_assembly": False,
         "material": "Maxon ECX", "make_buy": "外购", "quantity": "1"},
        {"part_no": "GIS-XX-001-06", "name_cn": "行星减速器", "is_assembly": False,
         "material": "Maxon GP22C", "make_buy": "外购", "quantity": "1"},
    ]
    layer_poses = {
        "GIS-XX-001-08": {"z": 0.0, "r": None, "theta": None,
                          "axis_dir": "盘面∥XY", "is_origin": True},
        "GIS-XX-001-05": {"z": 73.0, "r": None, "theta": None,
                          "axis_dir": "轴沿Z", "is_origin": False,
                          "z_is_top": True},
        "GIS-XX-001-06": {"z": 73.0, "r": None, "theta": None,
                          "axis_dir": "轴沿Z", "is_origin": False,
                          "z_is_top": True},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    mz = offsets["GIS-XX-001-05"][2]
    rz = offsets["GIS-XX-001-06"][2]
    # Must not overlap
    assert mz != rz, f"Motor and reducer at same Z={mz}"
    # Combined stack top must equal z_is_top value (73)
    h_each = 73.0 / 2  # no envelopes → even split
    top = max(mz, rz) + h_each
    assert abs(top - 73.0) < 0.1, f"Combined top should be 73, got {top}"
    # Bottom of stack should be at 0 (touching adapter plate)
    assert abs(min(mz, rz)) < 0.1, f"Stack bottom should be ~0, got {min(mz, rz)}"


def test_z_is_top_single_part():
    """Single z_is_top part: bottom = z_top - height."""
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-002", "name_cn": "工位", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-002-01", "name_cn": "电机", "is_assembly": False,
         "material": "Maxon Φ22×40mm", "make_buy": "外购", "quantity": "1"},
    ]
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0,
                       "axis_dir": "轴沿-Z", "is_origin": False},
        "GIS-XX-002-01": {"z": 50.0, "r": None, "theta": None,
                          "axis_dir": "轴沿Z", "is_origin": False,
                          "z_is_top": True},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    # BOM text "Maxon Φ22×40mm" → height 40; bottom = 50 - 40 = 10
    assert offsets["GIS-XX-002-01"][2] == 10.0, \
        f"Expected Z=10.0, got {offsets['GIS-XX-002-01'][2]}"


def test_z_is_top_negative():
    """Negative z_top (e.g. hanging downward) must still produce positive heights."""
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-003", "name_cn": "工位", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-003-01", "name_cn": "传感器A", "is_assembly": False,
         "material": "—", "make_buy": "外购", "quantity": "1"},
        {"part_no": "GIS-XX-003-02", "name_cn": "传感器B", "is_assembly": False,
         "material": "—", "make_buy": "外购", "quantity": "1"},
    ]
    layer_poses = {
        "GIS-XX-003": {"z": None, "r": 65, "theta": 90,
                       "axis_dir": "轴沿-Z", "is_origin": False},
        "GIS-XX-003-01": {"z": -60.0, "r": None, "theta": None,
                          "axis_dir": "", "is_origin": False, "z_is_top": True},
        "GIS-XX-003-02": {"z": -60.0, "r": None, "theta": None,
                          "axis_dir": "", "is_origin": False, "z_is_top": True},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    za = offsets["GIS-XX-003-01"][2]
    zb = offsets["GIS-XX-003-02"][2]
    # Both must be at or below z_top (-60), stacking downward from -60
    assert za <= -60.0, f"Sensor A Z={za} should be <= -60"
    assert zb <= -60.0, f"Sensor B Z={zb} should be <= -60"
    assert za != zb, f"Sensors overlap at Z={za}"


# ── Fix C: auto-stacking formula bottom-at-Z=0 ──

def test_auto_stack_adjacent_contact():
    """Auto-stacked parts of different heights must be adjacent (no gap)."""
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-002", "name_cn": "工位", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-002-01", "name_cn": "壳体", "is_assembly": False,
         "material": "铝合金 60×40×55mm", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-002-02", "name_cn": "泵", "is_assembly": False,
         "material": "不锈钢 Φ20×30mm", "make_buy": "外购", "quantity": "1"},
        {"part_no": "GIS-XX-002-03", "name_cn": "阀", "is_assembly": False,
         "material": "铜 Φ10×10mm", "make_buy": "外购", "quantity": "1"},
    ]
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0,
                       "axis_dir": "轴沿-Z", "is_origin": False},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    # Get all Z offsets + heights for adjacency check
    items = []
    for p in bom:
        if p["is_assembly"]:
            continue
        z = offsets[p["part_no"]][2]
        # Parse height from material text
        from gen_assembly import _parse_dims_text
        dims = _parse_dims_text(p["material"])
        h = dims[2] if dims else 15.0
        items.append((p["part_no"], z, h))

    # Sort by Z descending (stacking downward from 0)
    items.sort(key=lambda x: -x[1])
    for i in range(len(items) - 1):
        _, z_above, h_above = items[i]
        _, z_below, _ = items[i + 1]
        bottom_of_above = z_above  # part bottom face is at z offset
        top_of_below = z_below + items[i + 1][2]
        gap = bottom_of_above - top_of_below
        assert abs(gap) < 0.1, \
            f"Gap={gap:.1f}mm between {items[i][0]}(bottom={z_above}) " \
            f"and {items[i+1][0]}(top={top_of_below})"


# ── Fix D: seed from occupied extent boundary ──

def test_seed_does_not_overlap_explicit_parts():
    """Auto-stacked parts should not overlap explicitly-placed parts."""
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-001", "name_cn": "法兰总成", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-001-01", "name_cn": "法兰本体", "is_assembly": False,
         "material": "铝合金 Φ90×25mm", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-001-02", "name_cn": "PEEK环", "is_assembly": False,
         "material": "PEEK Φ86×5mm", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-001-03", "name_cn": "碟簧", "is_assembly": False,
         "material": "钢 Φ10×3mm", "make_buy": "外购", "quantity": "4"},
    ]
    layer_poses = {
        "GIS-XX-001-01": {"z": 0.0, "r": None, "theta": None,
                          "axis_dir": "", "is_origin": True},
        "GIS-XX-001-02": {"z": -27.0, "r": None, "theta": None,
                          "axis_dir": "", "is_origin": False},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    z_spring = offsets["GIS-XX-001-03"][2]
    # Must be below PEEK bottom (-27) to avoid overlap
    assert z_spring <= -27.0, \
        f"Disc spring Z={z_spring} overlaps with PEEK at Z=-27"


def test_parse_envelopes_returns_granularity_from_column(tmp_path):
    """When the §6.4 table includes a '粒度' column, parse_envelopes
    reads it by header name and returns {pno: {"dims": ..., "granularity": ...}}.

    Positional cells[3] dims lookup is unchanged."""
    spec = tmp_path / "CAD_SPEC.md"
    spec.write_text(
        "### 6.4 零件包络尺寸\n"
        "\n"
        "| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 | 粒度 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| GIS-EE-002 | 工位1涂抹模块 | box | 60×40×290 | P2:walker:tier1 | station_constraint |\n"
        "| GIS-EE-001-05 | 螺钉 | box | 10×10×30 | P1:param_table | part_envelope |\n",
        encoding="utf-8",
    )
    from codegen.gen_assembly import parse_envelopes
    envs = parse_envelopes(str(spec))
    assert "GIS-EE-002" in envs
    assert envs["GIS-EE-002"]["dims"] == (60.0, 40.0, 290.0)
    assert envs["GIS-EE-002"]["granularity"] == "station_constraint"
    assert envs["GIS-EE-001-05"]["granularity"] == "part_envelope"


def test_parse_envelopes_defaults_granularity_when_column_absent(tmp_path):
    """Backward compat: old §6.4 tables without 粒度 column default to
    part_envelope (preserves legacy behavior)."""
    spec = tmp_path / "CAD_SPEC.md"
    spec.write_text(
        "### 6.4 零件包络尺寸\n"
        "\n"
        "| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| GIS-EE-001 | 法兰 | box | 90×90×25 | P1:param_table |\n",
        encoding="utf-8",
    )
    from codegen.gen_assembly import parse_envelopes
    envs = parse_envelopes(str(spec))
    assert envs["GIS-EE-001"]["dims"] == (90.0, 90.0, 25.0)
    assert envs["GIS-EE-001"]["granularity"] == "part_envelope"


def test_parse_render_exclusions_combines_section_62_and_exclude_stack():
    """Render exclusions include whole assemblies and exclude_stack leaves."""
    spec = os.path.join(os.path.dirname(__file__), "..",
                        "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.isfile(spec):
        pytest.skip("end_effector CAD_SPEC.md not found")

    from gen_assembly import parse_render_exclusions

    exclusions = parse_render_exclusions(spec)
    assert "GIS-EE-006" in exclusions["assemblies"]
    assert "GIS-EE-002-05" in exclusions["parts"]
    assert "GIS-EE-003-08" in exclusions["parts"]
    assert "GIS-EE-004-13" in exclusions["parts"]


def test_generate_assembly_omits_exclude_stack_leaf_parts():
    """exclude_stack is a render exclusion, not a zero-offset placement."""
    spec = os.path.join(os.path.dirname(__file__), "..",
                        "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.isfile(spec):
        pytest.skip("end_effector CAD_SPEC.md not found")

    from gen_assembly import generate_assembly

    content = generate_assembly(spec)
    assert 'name="STD-GIS-EE-002-05"' not in content
    assert 'name="STD-GIS-EE-003-08"' not in content
    assert 'name="STD-GIS-EE-004-13"' not in content


def test_generate_assembly_includes_mechanical_transmission_std_parts(tmp_path):
    """GT2 drivetrain parts and couplings must reach assembly.py."""
    spec = tmp_path / "CAD_SPEC.md"
    spec.write_text(
        "# 丝杠式升降平台 (SLP)\n"
        "\n"
        "## 5. BOM树\n"
        "| 料号 | 名称 | 规格 | 数量 | 自制/外购 | 材料 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| SLP-000 | 丝杠式升降平台 |  | 1 | 总成 | — |\n"
        "| SLP-100 | 上固定板 |  | 1 | 自制 | 6061 |\n"
        "| SLP-C04 | GT2 20T 开式带轮 φ12 |  | 2 | 外购 | — |\n"
        "| SLP-C05 | GT2-310-6mm 带 |  | 1 | 外购 | — |\n"
        "| SLP-C06 | L070 联轴器 |  | 1 | 外购 | — |\n"
        "\n"
        "## 6. 装配姿态\n"
        "### 6.1 坐标系定义\n"
        "| 术语 | 定义 |\n"
        "| --- | --- |\n"
        "| 原点 | 下板顶面中心 |\n",
        encoding="utf-8",
    )
    from gen_assembly import generate_assembly

    content = generate_assembly(str(spec))

    assert "from std_c04 import make_std_c04" in content
    assert "from std_c05 import make_std_c05" in content
    assert "from std_c06 import make_std_c06" in content
    assert 'name="STD-SLP-C04"' in content
    assert 'name="STD-SLP-C05"' in content
    assert 'name="STD-SLP-C06"' in content


def test_generate_assembly_uses_product_graph_instance_ids_when_available(tmp_path):
    spec = tmp_path / "cad" / "demo" / "CAD_SPEC.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "# CAD Spec — Demo (P)\n"
        "\n"
        "## 5. BOM\n"
        "| 料号 | 名称 | 材质 | 数量 | 自制/外购 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| P-100 | Demo总成 | 组合件 | 1 | 总成 |\n"
        "| P-100-01 | 基座 | Q235 | 1 | 自制 |\n"
        "| P-100-02 | 导柱 | 45钢 | 2 | 自制 |\n"
        "\n"
        "### 6.2 装配层叠\n"
        "| 层级 | 零件 | 固定/运动 | 连接 | 偏移 | 轴向 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| L1 | Demo总成 (P-100) | 固定 | 基准 | 0 | Z |\n",
        encoding="utf-8",
        newline="\n",
    )
    product_graph_path = spec.parent / "PRODUCT_GRAPH.json"
    product_graph_path.write_text(
        "{\n"
        '  "schema_version": 1,\n'
        '  "instances": [\n'
        '    {"instance_id": "P-100-01#01", "part_no": "P-100-01"},\n'
        '    {"instance_id": "P-100-02#01", "part_no": "P-100-02"},\n'
        '    {"instance_id": "P-100-02#02", "part_no": "P-100-02"}\n'
        "  ]\n"
        "}\n",
        encoding="utf-8",
        newline="\n",
    )

    from gen_assembly import generate_assembly

    content = generate_assembly(str(spec))

    assert 'name="P-100-01#01"' in content
    assert 'name="P-100-02#01"' in content
    assert 'name="P-100-02#02"' in content


def test_generate_assembly_rejects_invalid_product_graph_when_present(tmp_path):
    spec = tmp_path / "cad" / "demo" / "CAD_SPEC.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "# CAD Spec — Demo (P)\n"
        "\n"
        "## 5. BOM\n"
        "| 料号 | 名称 | 材质 | 数量 | 自制/外购 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| P-100 | Demo总成 | 组合件 | 1 | 总成 |\n"
        "| P-100-01 | 基座 | Q235 | 1 | 自制 |\n",
        encoding="utf-8",
        newline="\n",
    )
    (spec.parent / "PRODUCT_GRAPH.json").write_text(
        "{bad json",
        encoding="utf-8",
        newline="\n",
    )

    from gen_assembly import generate_assembly

    with pytest.raises(ValueError, match="PRODUCT_GRAPH.json"):
        generate_assembly(str(spec))
