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
