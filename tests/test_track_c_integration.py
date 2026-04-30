"""Track C 集成测试：routing + L1 + L3 端对端验证（不需要真实 LLM API Key）"""
import pytest
from unittest.mock import patch


def test_route_finds_flange_in_end_effector_bom():
    """routing 层：法兰件能被 route() 命中（不需要 LLM）"""
    from cad_spec_gen.parts_routing import GeomInfo, route, discover_templates, locate_builtin_templates_dir
    geom = GeomInfo(type="cylinder", envelope_w=90.0, envelope_d=90.0, envelope_h=20.0, extras={})
    tier1 = locate_builtin_templates_dir()
    templates = discover_templates([tier1] if tier1 else [])
    decision = route("法兰盘", geom, templates)
    assert decision.outcome in ("HIT_BUILTIN", "HIT_PROJECT")
    assert decision.template is not None


def test_l1_param_extraction_flange_mock():
    """L1 层：mock LLM 返回法兰参数，_apply_template_decision 生成含螺栓孔几何"""
    pytest.importorskip("cadquery")
    from cad_spec_gen.data.codegen.gen_parts import _apply_template_decision

    filled = [
        {"name": "FLANGE_BODY_OD", "nominal": "90"},
        {"name": "FLANGE_BODY_ID", "nominal": "45"},
        {"name": "FLANGE_TOTAL_THICK", "nominal": "20"},
        {"name": "FLANGE_BOLT_PCD", "nominal": "65"},
    ]
    geom = {"type": "cylinder", "envelope_w": 90.0, "envelope_d": 90.0, "envelope_h": 20.0}
    part_meta = {"name_cn": "法兰盘", "dim_tolerances": [{"name": "FLANGE_BODY_OD", "nominal": "90"}]}

    with patch("cad_spec_gen.data.codegen.llm_codegen._llm_extract_params", return_value=filled) as mock_l1:
        result = _apply_template_decision(geom, "flange", part_meta, (90.0, 90.0, 20.0))
    mock_l1.assert_called_once()

    assert result.get("template_code") is not None, "L1 应使 factory 返回代码"
    code = result["template_code"].lower()
    assert "bolt" in code or "circle" in code


def test_l3_enriched_placeholder_written_for_unknown_part(tmp_path):
    """L3 层：无模板件生成带 ENRICHED_PLACEHOLDER 注释的 .py 文件"""
    pytest.importorskip("cadquery")
    from cad_spec_gen.data.codegen.gen_parts import _write_enriched_placeholder
    out_py = tmp_path / "ee_unknown.py"
    _write_enriched_placeholder(out_py, "ee_unknown", None, 50.0, 40.0, 30.0)
    content = out_py.read_text(encoding="utf-8")
    assert "ENRICHED_PLACEHOLDER" in content
    assert "def make_ee_unknown" in content
    assert "ee_unknown = make_ee_unknown" in content
    step_file = tmp_path / "ee_unknown.step"
    assert step_file.exists()
    assert step_file.stat().st_size > 500
