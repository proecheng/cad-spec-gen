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


# ---- route() tests ----


def _get_route_symbols():
    """Load GeomInfo, TemplateDescriptor, RouteDecision, route via the safe importer."""
    m = _import_parts_routing_module()
    return m.GeomInfo, m.TemplateDescriptor, m.RouteDecision, m.route


def _make_td(name, kws, priority, category, tier="builtin"):
    _, TemplateDescriptor, _, _ = _get_route_symbols()
    return TemplateDescriptor(
        name=name,
        keywords=tuple(sorted(kws)),
        priority=priority,
        category=category,
        tier=tier,
        source_path=Path(f"/tmp/{name}.py"),
    )


def test_route_empty_templates_returns_fallback():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("box", 100, 50, 20)
    decision = route("some part", geom, [])
    assert decision.outcome == "FALLBACK"
    assert decision.template is None
    assert "no templates available" in decision.reason


def test_route_empty_name_returns_fallback():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("box", 100, 50, 20)
    t = [_make_td("l_bracket", ["bracket"], 10, "bracket")]
    decision = route("", geom, t)
    assert decision.outcome == "FALLBACK"
    assert "empty part name" in decision.reason


def test_route_unknown_geom_type_returns_fallback():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("weird_shape", 100, 50, 20)
    t = [_make_td("l_bracket", ["bracket"], 10, "bracket")]
    decision = route("bracket 01", geom, t)
    assert decision.outcome == "FALLBACK"
    assert "unknown geom type" in decision.reason


def test_route_disc_arms_with_mechanical_interface_template_hits():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("disc_arms", 90, 90, 25,
                    extras={"arm_count": 4, "arm_l": 40})
    t = [_make_td("iso_9409_flange", ["flange", "robot flange"],
                  20, "mechanical_interface")]
    decision = route("十字法兰 01", geom, t)
    assert decision.outcome == "HIT_BUILTIN"
    assert decision.template.name == "iso_9409_flange"


def test_route_disc_arms_without_mechanical_interface_fallback():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("disc_arms", 90, 90, 25, extras={"arm_count": 4})
    t = [_make_td("l_bracket", ["bracket"], 15, "bracket")]
    decision = route("flange", geom, t)
    assert decision.outcome == "FALLBACK"
    assert "mechanical_interface" in decision.reason


def test_route_single_keyword_match_hits_builtin():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("box", 100, 50, 20)
    t = [_make_td("l_bracket", ["l_bracket", "angle bracket"], 15, "bracket")]
    decision = route("l_bracket mount", geom, t)
    assert decision.outcome == "HIT_BUILTIN"
    assert decision.template.name == "l_bracket"


def test_route_higher_priority_wins_on_keyword_collision():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("box", 100, 100, 100)
    t = [
        _make_td("housing_a", ["housing"], 10, "housing"),
        _make_td("housing_b", ["housing"], 20, "housing"),  # higher priority
    ]
    decision = route("enclosure housing", geom, t)
    assert decision.outcome == "HIT_BUILTIN"
    assert decision.template.name == "housing_b"


def test_route_equal_priority_collision_returns_ambiguous():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("box", 100, 100, 100)
    t = [
        _make_td("a", ["shared_kw"], 15, "bracket"),
        _make_td("b", ["shared_kw"], 15, "bracket"),
    ]
    decision = route("shared_kw mount", geom, t)
    assert decision.outcome == "AMBIGUOUS"
    assert decision.template is None
    assert len(decision.ambiguous_candidates) == 2


def test_route_project_tier_shadows_builtin():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("box", 100, 50, 20)
    t = [
        _make_td("l_bracket", ["l_bracket"], 15, "bracket", tier="builtin"),
        _make_td("l_bracket", ["l_bracket"], 15, "bracket", tier="project"),
    ]
    decision = route("l_bracket", geom, t)
    assert decision.outcome == "HIT_PROJECT"


def test_route_degenerate_envelope_fallback():
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("box", 0, 50, 20)  # zero width
    t = [_make_td("l_bracket", ["bracket"], 15, "bracket")]
    decision = route("l_bracket", geom, t)
    assert decision.outcome == "FALLBACK"
    assert "degenerate" in decision.reason


def test_route_is_deterministic():
    """Same inputs must produce identical RouteDecision 100 times."""
    GeomInfo, _, _, route = _get_route_symbols()
    geom = GeomInfo("box", 100, 50, 20)
    t = [_make_td("l_bracket", ["bracket", "angle"], 15, "bracket")]
    first = route("bracket mount", geom, t)
    for _ in range(100):
        assert route("bracket mount", geom, t) == first
