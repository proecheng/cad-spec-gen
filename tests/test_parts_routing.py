# tests/test_parts_routing.py
"""Tests for src/cad_spec_gen/parts_routing.py — pure routing module."""
import sys
import importlib.util
from pathlib import Path

import pytest


def _import_parts_routing_module():
    """Import parts_routing.py directly via spec to avoid sys.path shadowing.

    The top-level cad_spec_gen.py script can shadow the package when running
    all tests together (because test_assembly_coherence.py adds repo root to
    sys.path). Use importlib.util.spec_from_file_location to load directly.
    """
    spec_file = Path(__file__).parent.parent / "src/cad_spec_gen/parts_routing.py"
    spec = importlib.util.spec_from_file_location("cad_spec_gen.parts_routing", spec_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules["cad_spec_gen.parts_routing"] = module
    spec.loader.exec_module(module)
    return module


def test_geom_info_is_frozen_dataclass():
    parts_routing = _import_parts_routing_module()
    GeomInfo = parts_routing.GeomInfo
    g = GeomInfo(type="box", envelope_w=100, envelope_d=50, envelope_h=20, extras={})
    assert g.type == "box"
    assert g.envelope_w == 100
    # Frozen: should raise on mutation
    with pytest.raises((AttributeError, Exception)):
        g.type = "cylinder"


def test_template_descriptor_is_frozen():
    parts_routing = _import_parts_routing_module()
    TemplateDescriptor = parts_routing.TemplateDescriptor
    td = TemplateDescriptor(
        name="l_bracket",
        keywords=("l_bracket", "angle bracket"),
        priority=15,
        category="bracket",
        tier="builtin",
        source_path=Path("/tmp/l_bracket.py"),
    )
    assert td.name == "l_bracket"
    assert "angle bracket" in td.keywords
    with pytest.raises((AttributeError, Exception)):
        td.name = "changed"


def test_route_decision_structure():
    parts_routing = _import_parts_routing_module()
    RouteDecision = parts_routing.RouteDecision
    rd = RouteDecision(outcome="FALLBACK", template=None, reason="no match")
    assert rd.outcome == "FALLBACK"
    assert rd.template is None
    assert rd.reason == "no match"


def test_allowed_categories_constant():
    parts_routing = _import_parts_routing_module()
    ALLOWED_CATEGORIES = parts_routing.ALLOWED_CATEGORIES
    assert "bracket" in ALLOWED_CATEGORIES
    assert "housing" in ALLOWED_CATEGORIES
    assert "plate" in ALLOWED_CATEGORIES
    assert "mechanical_interface" in ALLOWED_CATEGORIES
    assert "fastener_family" in ALLOWED_CATEGORIES


def test_locate_builtin_templates_dir_finds_repo_root():
    """Running from repo checkout must find templates/parts/ at repo root."""
    from cad_spec_gen.parts_routing import locate_builtin_templates_dir
    result = locate_builtin_templates_dir()
    assert result is not None
    assert result.is_dir()
    assert result.name == "parts"
    assert (result / "iso_9409_flange.py").exists()
    # Must also find the 4 new templates from Phase 2
    assert (result / "l_bracket.py").exists()
    assert (result / "rectangular_housing.py").exists()
    assert (result / "cylindrical_housing.py").exists()
    assert (result / "fixture_plate.py").exists()


def test_discover_templates_finds_all_builtin():
    """discover_templates on the real templates dir must find all 5 templates."""
    from cad_spec_gen.parts_routing import discover_templates, locate_builtin_templates_dir
    dir_path = locate_builtin_templates_dir()
    assert dir_path is not None
    descriptors = discover_templates([dir_path])
    names = {d.name for d in descriptors}
    expected = {"iso_9409_flange", "l_bracket", "rectangular_housing",
                "cylindrical_housing", "fixture_plate"}
    assert expected.issubset(names), f"Missing: {expected - names}"


def test_discover_templates_handles_empty_list():
    from cad_spec_gen.parts_routing import discover_templates
    descriptors = discover_templates([])
    assert descriptors == []


def test_discover_templates_skips_underscore_files(tmp_path):
    """Files starting with _ should be skipped."""
    from cad_spec_gen.parts_routing import discover_templates
    (tmp_path / "_private.py").write_text("# private helper")
    (tmp_path / "valid_tpl.py").write_text(
        'MATCH_KEYWORDS = ["valid"]\n'
        'MATCH_PRIORITY = 10\n'
        'TEMPLATE_CATEGORY = "bracket"\n'
        'TEMPLATE_VERSION = "1.0"\n'
        'def make(**p): pass\n'
        'def example_params(): return {}\n'
    )
    descriptors = discover_templates([tmp_path])
    names = {d.name for d in descriptors}
    assert "valid_tpl" in names
    assert "_private" not in names


def test_discover_templates_extracts_correct_metadata():
    from cad_spec_gen.parts_routing import discover_templates, locate_builtin_templates_dir
    descriptors = discover_templates([locate_builtin_templates_dir()])
    iso = next(d for d in descriptors if d.name == "iso_9409_flange")
    assert iso.category == "mechanical_interface"
    assert iso.priority == 20
    assert iso.tier == "builtin"
    assert len(iso.keywords) >= 3
