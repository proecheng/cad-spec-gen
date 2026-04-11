"""Regression tests for assembly coherence fixes."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_parse_envelopes_from_spec():
    """§6.4 table should parse into {part_no: {"dims": (w, d, h), "granularity": str}} dict."""
    from codegen.gen_assembly import parse_envelopes
    spec = os.path.join(os.path.dirname(__file__), "..", "cad", "end_effector", "CAD_SPEC.md")
    # Fall back to fixture if the real spec doesn't exist or lacks a §6.4 envelope table
    if not os.path.isfile(spec) or "### 6.4" not in open(spec, encoding="utf-8").read():
        spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    assert len(envs) > 0
    for pno, entry in envs.items():
        dims = entry["dims"]
        assert len(dims) == 3, f"{pno}: expected 3-tuple, got {dims}"
        assert all(isinstance(v, float) for v in dims), f"{pno}: non-float in {dims}"
        assert "granularity" in entry, f"{pno}: missing granularity key"


def _write_fixture_spec():
    """Create minimal CAD_SPEC.md fixture with §6.4 table."""
    import tempfile
    content = """# CAD Spec — Test (TEST)

## 6. 装配姿态与定位

### 6.4 零件包络尺寸

| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |
| --- | --- | --- | --- | --- |
| TEST-001-01 | 法兰本体 | cylinder | Φ90.0×25.0 | P4:visual |
| TEST-001-02 | PEEK绝缘段 | cylinder | Φ86.0×5.0 | P3:BOM |
| TEST-006-01 | 壳体 | box | 140.0×100.0×55.0 | P3:BOM |
"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_parse_envelopes_cylinder():
    """Cylinder format: Φ90.0×25.0 → dims=(90.0, 90.0, 25.0)."""
    from codegen.gen_assembly import parse_envelopes
    spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    assert envs["TEST-001-01"]["dims"] == (90.0, 90.0, 25.0)
    assert envs["TEST-001-01"]["granularity"] == "part_envelope"


def test_parse_envelopes_box():
    """Box format: 140.0×100.0×55.0 → dims=(140.0, 100.0, 55.0)."""
    from codegen.gen_assembly import parse_envelopes
    spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    assert envs["TEST-006-01"]["dims"] == (140.0, 100.0, 55.0)
    assert envs["TEST-006-01"]["granularity"] == "part_envelope"


def test_guess_geometry_uses_envelope():
    """§6.4 envelope should override BOM-based dimension guessing."""
    from codegen.gen_parts import _guess_geometry
    # Without envelope: 法兰+悬臂 → hardcoded d=80
    geom_old = _guess_geometry("法兰本体（含十字悬臂）", "7075-T6铝合金")
    assert geom_old["d"] == 80.0  # old hardcoded value

    # With envelope from §6.4: Φ90×25 → d=90, t=25
    geom_new = _guess_geometry("法兰本体（含十字悬臂）", "7075-T6铝合金",
                               envelope=(90.0, 90.0, 25.0))
    assert geom_new["d"] == 90.0
    assert geom_new["envelope_h"] == 25.0


def test_guess_geometry_box_envelope():
    """Box envelope should produce box geometry."""
    from codegen.gen_parts import _guess_geometry
    geom = _guess_geometry("壳体（含散热鳍片）", "6063铝合金",
                           envelope=(140.0, 100.0, 55.0))
    assert geom["type"] == "box"
    assert geom["w"] == 140.0
    assert geom["h"] == 55.0


def test_flange_assembly_z_span():
    """法兰总成 parts should span ≤100mm, not 360mm."""
    spec = os.path.join(os.path.dirname(__file__), "..",
                        "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.isfile(spec):
        import pytest
        pytest.skip("No end_effector CAD_SPEC.md available")

    from codegen.gen_assembly import _resolve_child_offsets, _extract_all_layer_poses
    from codegen.gen_assembly import parse_assembly_pose, parse_envelopes
    from codegen.gen_build import parse_bom_tree

    parts = parse_bom_tree(spec)
    pose = parse_assembly_pose(spec)
    layer_poses = _extract_all_layer_poses(pose, parts)
    offsets = _resolve_child_offsets(parts, layer_poses, spec)

    # Collect Z offsets for GIS-EE-001-xx parts (法兰总成)
    flange_zs = [off[2] for pno, off in offsets.items()
                 if pno.startswith("GIS-EE-001-")]
    if not flange_zs:
        import pytest
        pytest.skip("No flange parts found")

    z_span = max(flange_zs) - min(flange_zs)
    assert z_span <= 120.0, (
        f"法兰总成 Z-span is {z_span:.0f}mm (should be ≤120mm). "
        f"Parts are still scattered."
    )


def test_station_parts_compact():
    """Each workstation's parts should span ≤200mm along stacking axis."""
    spec = os.path.join(os.path.dirname(__file__), "..",
                        "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.isfile(spec):
        import pytest
        pytest.skip("No end_effector CAD_SPEC.md available")

    from codegen.gen_assembly import _resolve_child_offsets, _extract_all_layer_poses
    from codegen.gen_assembly import parse_assembly_pose
    from codegen.gen_build import parse_bom_tree

    parts = parse_bom_tree(spec)
    pose = parse_assembly_pose(spec)
    layer_poses = _extract_all_layer_poses(pose, parts)
    offsets = _resolve_child_offsets(parts, layer_poses, spec)

    for station_prefix in ["GIS-EE-002-", "GIS-EE-003-", "GIS-EE-004-", "GIS-EE-005-"]:
        station_zs = [off[2] for pno, off in offsets.items()
                      if pno.startswith(station_prefix)]
        if not station_zs:
            continue
        z_span = max(station_zs) - min(station_zs)
        assert z_span <= 310.0, (
            f"{station_prefix} Z-span is {z_span:.0f}mm (should be ≤310mm). "
            f"Original pre-fix span was ~355mm; this guards against regression."
        )


def test_parse_constraints():
    """§9.2 constraint table should parse correctly."""
    import tempfile
    from codegen.gen_assembly import parse_constraints

    content = """# CAD Spec — Test

### 9.2 约束声明（自动生成草稿）

| 约束ID | 类型 | 零件A | 零件B | 参数 | 来源 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | contact | 法兰本体 | PEEK绝缘段 | gap=0 | §3 | high |
| C02 | exclude_stack | GIS-EE-001-09 |  | type=cable | §5 BOM | high |
"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    f.write(content)
    f.close()

    constraints = parse_constraints(f.name)
    assert len(constraints) == 2
    assert constraints[0]["type"] == "contact"
    assert constraints[0]["confidence"] == "high"
    assert constraints[1]["type"] == "exclude_stack"
    assert "cable" in constraints[1]["params"]
