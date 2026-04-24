# tests/test_track_c_routing.py
import pytest
from cad_spec_gen.parts_routing import GeomInfo, route, discover_templates, locate_builtin_templates_dir


def _make_geom(gtype="cylinder", w=90.0, d=90.0, h=20.0):
    return GeomInfo(type=gtype, envelope_w=w, envelope_d=d, envelope_h=h, extras={})


def test_route_chinese_flange():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("法兰盘", _make_geom("cylinder"), templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT"), decision.reason
    assert decision.template is not None
    assert "flange" in decision.template.name


def test_route_chinese_bracket():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("安装支架", _make_geom("l_bracket"), templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT"), decision.reason
    assert decision.template is not None
    assert "bracket" in decision.template.name


def test_route_chinese_arm():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("悬臂件", _make_geom("box", 120, 30, 15), templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT"), decision.reason
    assert "arm" in decision.template.name


def test_route_chinese_cover():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("端盖", _make_geom("cylinder", 60, 60, 8), templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT"), decision.reason
    assert "cover" in decision.template.name


def test_route_unknown_falls_back():
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("完全未知零件XYZ", _make_geom("box"), templates)
    assert decision.outcome == "FALLBACK"


def test_gen_parts_route_to_factory_type():
    """route() 命中 iso_9409_flange → _ROUTE_TO_FACTORY_TYPE 映射到 'flange'"""
    from cad_spec_gen.data.codegen.gen_parts import _ROUTE_TO_FACTORY_TYPE
    assert _ROUTE_TO_FACTORY_TYPE["iso_9409_flange"] == "flange"
    assert _ROUTE_TO_FACTORY_TYPE["l_bracket"] == "bracket"
    assert _ROUTE_TO_FACTORY_TYPE["cantilever_arm"] == "arm"
    assert _ROUTE_TO_FACTORY_TYPE["spring_unit"] == "spring_mechanism"


def test_gen_parts_imports_pick_best():
    """gen_parts 可导入 _pick_best（routing activation 需要）"""
    from cad_spec_gen.parts_routing import _pick_best
    from cad_spec_gen.parts_routing import TemplateDescriptor
    from pathlib import Path
    a = TemplateDescriptor("a", ("kw",), priority=10, category="bracket", tier="builtin", source_path=Path("."))
    b = TemplateDescriptor("b", ("kw",), priority=20, category="bracket", tier="builtin", source_path=Path("."))
    assert _pick_best([a, b]).name == "b"
