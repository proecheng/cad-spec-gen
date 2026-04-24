# tests/test_track_c_llm.py
import json
import pytest
from unittest.mock import patch

from cad_spec_gen.data.codegen.llm_codegen import _llm_extract_params


def test_llm_extract_params_returns_populated_list():
    """mock LLM 返回合法 JSON → 返回 dim_tolerances 列表"""
    mock_json = json.dumps([
        {"name": "FLANGE_BODY_OD", "nominal": "90"},
        {"name": "FLANGE_BODY_ID", "nominal": "45"},
        {"name": "FLANGE_TOTAL_THICK", "nominal": "20"},
        {"name": "FLANGE_BOLT_PCD", "nominal": "65"},
    ])
    with patch("cad_spec_gen.data.codegen.llm_codegen._call_gemini_text", return_value=mock_json):
        result = _llm_extract_params(
            part_name="法兰盘",
            spec_text="法兰外径 90mm，中心孔 45mm，厚度 20mm，螺栓孔中心距 65mm",
            template_name="flange",
            required_tol_keys=["FLANGE_BODY_OD", "FLANGE_BODY_ID", "FLANGE_TOTAL_THICK", "FLANGE_BOLT_PCD"],
            existing_dim_tols=[],
        )
    assert result is not None
    by_name = {d["name"]: float(d["nominal"]) for d in result}
    assert abs(by_name["FLANGE_BODY_OD"] - 90) < 1
    assert abs(by_name["FLANGE_BODY_ID"] - 45) < 1


def test_llm_extract_params_json_fail_returns_none():
    """LLM 返回非法 JSON → 返回 None，不抛异常"""
    with patch("cad_spec_gen.data.codegen.llm_codegen._call_gemini_text", return_value="not valid json"):
        result = _llm_extract_params("法兰盘", "spec", "flange", ["FLANGE_BODY_OD"], [])
    assert result is None


def test_llm_extract_params_skips_existing_keys():
    """existing_dim_tols 中已有的键不被覆盖"""
    existing = [{"name": "FLANGE_BODY_OD", "nominal": "90"}]
    mock_json = json.dumps([
        {"name": "FLANGE_BODY_ID", "nominal": "45"},
        {"name": "FLANGE_TOTAL_THICK", "nominal": "20"},
        {"name": "FLANGE_BOLT_PCD", "nominal": "65"},
    ])
    with patch("cad_spec_gen.data.codegen.llm_codegen._call_gemini_text", return_value=mock_json):
        result = _llm_extract_params("法兰盘", "spec", "flange",
                                     ["FLANGE_BODY_OD", "FLANGE_BODY_ID", "FLANGE_TOTAL_THICK", "FLANGE_BOLT_PCD"],
                                     existing)
    assert result is not None
    by_name = {d["name"]: d["nominal"] for d in result}
    assert by_name["FLANGE_BODY_OD"] == "90"


def test_call_gemini_text_empty_candidates_returns_none():
    """Gemini 返回空 candidates 列表时不抛异常，返回 None"""
    from cad_spec_gen.data.codegen.llm_codegen import _call_gemini_text
    mock_resp_data = json.dumps({"candidates": []}).encode()

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return mock_resp_data

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
            result = _call_gemini_text("test prompt")
    assert result is None


def test_apply_template_decision_calls_l1_when_code_none():
    """_apply_template_decision: factory 返回 None 时调用 _llm_extract_params"""
    import pytest
    pytest.importorskip("cadquery")
    geom = {"type": "cylinder", "envelope_w": 90.0, "envelope_d": 90.0, "envelope_h": 20.0}
    part_meta = {"dim_tolerances": [{"name": "FLANGE_BODY_OD", "nominal": "90"}]}
    filled = [
        {"name": "FLANGE_BODY_OD", "nominal": "90"},
        {"name": "FLANGE_BODY_ID", "nominal": "45"},
        {"name": "FLANGE_TOTAL_THICK", "nominal": "20"},
        {"name": "FLANGE_BOLT_PCD", "nominal": "65"},
    ]
    with patch("cad_spec_gen.data.codegen.llm_codegen._llm_extract_params", return_value=filled) as mock_l1:
        from cad_spec_gen.data.codegen.gen_parts import _apply_template_decision
        result = _apply_template_decision(geom, "flange", part_meta, (90.0, 90.0, 20.0))
    mock_l1.assert_called_once()
    assert result.get("template_code") is not None, "L1 应补参后生成代码"


def test_enriched_envelope_flange_has_more_faces_than_cylinder():
    """法兰富化 envelope 面数 >= 9（远多于裸圆柱的 3 面，含中心孔+螺栓孔）"""
    pytest.importorskip("cadquery")
    from cad_spec_gen.data.codegen.enriched_envelope import _make_enriched_envelope
    wp = _make_enriched_envelope("flange", 90.0, 90.0, 20.0)
    assert wp is not None
    assert len(wp.val().Faces()) >= 9


def test_enriched_envelope_unknown_type_returns_box():
    """未知 tpl_type → 返回带圆角的 box，不返回 None"""
    pytest.importorskip("cadquery")
    from cad_spec_gen.data.codegen.enriched_envelope import _make_enriched_envelope
    wp = _make_enriched_envelope("unknown_xyz", 50.0, 40.0, 30.0)
    assert wp is not None


def test_enriched_envelope_exports_valid_step(tmp_path):
    """富化 envelope 可导出为合法 STEP 文件（文件大小 > 1KB）"""
    pytest.importorskip("cadquery")
    import cadquery as cq
    from cad_spec_gen.data.codegen.enriched_envelope import _make_enriched_envelope
    wp = _make_enriched_envelope("bracket", 60.0, 40.0, 50.0)
    out = tmp_path / "test.step"
    cq.exporters.export(wp, str(out))
    assert out.stat().st_size > 1000


def test_write_enriched_placeholder_creates_files(tmp_path):
    """_write_enriched_placeholder 生成 .py 含 ENRICHED_PLACEHOLDER + .step 文件"""
    pytest.importorskip("cadquery")
    from cad_spec_gen.data.codegen.gen_parts import _write_enriched_placeholder
    out_py = tmp_path / "test_part.py"
    _write_enriched_placeholder(out_py, "test_fn", "flange", 90.0, 90.0, 20.0)
    content = out_py.read_text(encoding="utf-8")
    assert "ENRICHED_PLACEHOLDER" in content
    step_out = tmp_path / "test_part.step"
    assert step_out.exists()
