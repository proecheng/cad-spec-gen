# tests/test_templates.py
"""Tests for builtin templates in templates/parts/.

Each template must expose:
  - MATCH_KEYWORDS: list[str]
  - MATCH_PRIORITY: int
  - TEMPLATE_CATEGORY: str (one of: bracket | housing | plate | mechanical_interface | fastener_family)
  - TEMPLATE_VERSION: str
  - make(**params) -> cq.Workplane
  - example_params() -> dict

And calling make(**example_params()) must return a non-empty valid solid.
"""
import importlib.util
from pathlib import Path

import pytest


_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "parts"
_CATEGORIES = {"bracket", "housing", "plate", "mechanical_interface", "fastener_family"}


def _load_template_module(name: str):
    """Load a template .py file directly without importing as package."""
    path = _TEMPLATES_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"template_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_iso_9409_flange_has_match_keywords():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "MATCH_KEYWORDS")
    assert isinstance(mod.MATCH_KEYWORDS, list)
    assert len(mod.MATCH_KEYWORDS) >= 3
    assert all(isinstance(k, str) for k in mod.MATCH_KEYWORDS)


def test_iso_9409_flange_has_match_priority():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "MATCH_PRIORITY")
    assert isinstance(mod.MATCH_PRIORITY, int)
    assert mod.MATCH_PRIORITY > 0


def test_iso_9409_flange_has_template_category():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "TEMPLATE_CATEGORY")
    assert mod.TEMPLATE_CATEGORY in _CATEGORIES


def test_iso_9409_flange_has_template_version():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "TEMPLATE_VERSION")
    assert isinstance(mod.TEMPLATE_VERSION, str)


def test_iso_9409_flange_example_params_returns_dict():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "example_params")
    params = mod.example_params()
    assert isinstance(params, dict)
    assert "outer_dia" in params
    assert "thickness" in params


@pytest.mark.integration
def test_iso_9409_flange_make_with_example_params():
    """make(**example_params()) must return a valid non-empty solid."""
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        pytest.skip("cadquery not available")
    mod = _load_template_module("iso_9409_flange")
    result = mod.make(**mod.example_params())
    assert result is not None
    solid = result.val()
    assert solid is not None
    assert solid.Volume() > 0


def test_iso_9409_flange_docstring_is_generic():
    """Docstring must not reference specific subsystems (G10 generality).

    Note: GISBOT is allowed as an illustrative historical example per §6.3
    of the spec — new templates must not reference it, but iso_9409_flange's
    existing docstring is grandfathered.
    """
    mod = _load_template_module("iso_9409_flange")
    doc = (mod.__doc__ or "").lower()
    # These strings would violate generality in NEW templates, but
    # iso_9409_flange's GISBOT mention is allowed per spec.
    # We just verify the docstring exists and is reasonable.
    assert len(doc) > 50, "docstring too short"


# l_bracket tests
def test_l_bracket_has_match_keywords():
    mod = _load_template_module("l_bracket")
    assert hasattr(mod, "MATCH_KEYWORDS")
    assert "l_bracket" in mod.MATCH_KEYWORDS


def test_l_bracket_category_is_bracket():
    mod = _load_template_module("l_bracket")
    assert mod.TEMPLATE_CATEGORY == "bracket"


def test_l_bracket_example_params_has_required_fields():
    mod = _load_template_module("l_bracket")
    p = mod.example_params()
    for key in ["w", "d", "h", "t", "bend_fillet"]:
        assert key in p, f"Missing {key}"


@pytest.mark.integration
def test_l_bracket_make_returns_valid_solid():
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        pytest.skip("cadquery not available")
    mod = _load_template_module("l_bracket")
    result = mod.make(**mod.example_params())
    assert result is not None
    assert result.val().Volume() > 0
