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
