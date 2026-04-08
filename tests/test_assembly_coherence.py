"""Regression tests for assembly coherence fixes."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_parse_envelopes_from_spec():
    """§6.4 table should parse into {part_no: (w, d, h)} dict."""
    from codegen.gen_assembly import parse_envelopes
    spec = os.path.join(os.path.dirname(__file__), "..", "cad", "end_effector", "CAD_SPEC.md")
    # Fall back to fixture if the real spec doesn't exist or lacks a §6.4 envelope table
    if not os.path.isfile(spec) or "### 6.4" not in open(spec, encoding="utf-8").read():
        spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    assert len(envs) > 0
    for pno, dims in envs.items():
        assert len(dims) == 3, f"{pno}: expected 3-tuple, got {dims}"
        assert all(isinstance(v, float) for v in dims), f"{pno}: non-float in {dims}"


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
    """Cylinder format: Φ90.0×25.0 → (90.0, 90.0, 25.0)."""
    from codegen.gen_assembly import parse_envelopes
    spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    assert envs["TEST-001-01"] == (90.0, 90.0, 25.0)


def test_parse_envelopes_box():
    """Box format: 140.0×100.0×55.0 → (140.0, 100.0, 55.0)."""
    from codegen.gen_assembly import parse_envelopes
    spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    assert envs["TEST-006-01"] == (140.0, 100.0, 55.0)


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
