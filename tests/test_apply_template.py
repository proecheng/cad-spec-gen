import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "codegen"))

from gen_parts import _apply_template_decision


class TestApplyTemplateDecision:
    _BASE_GEOM = {
        "type": "cylinder",
        "envelope_w": 160.0,
        "envelope_d": 160.0,
        "envelope_h": 20.0,
    }
    _FLANGE_META = {
        "dim_tolerances": [
            {"name": "FLANGE_BODY_OD", "nominal": "90"},
            {"name": "FLANGE_BODY_ID", "nominal": "22"},
            {"name": "FLANGE_TOTAL_THICK", "nominal": "30"},
            {"name": "FLANGE_BOLT_PCD", "nominal": "70"},
        ]
    }
    _ENVELOPE = (160.0, 160.0, 20.0)

    def test_flange_sets_type_and_template_code(self, monkeypatch, tmp_path):
        # Force non-Win32 to skip SW path (isolate CadQuery logic)
        monkeypatch.setattr("sys.platform", "linux")
        result = _apply_template_decision(
            dict(self._BASE_GEOM), "flange", self._FLANGE_META, self._ENVELOPE,
            part_no="TEST-001", output_dir=str(tmp_path),
        )
        assert result["type"] == "flange"
        assert "template_code" in result
        assert result["template_code"] is not None
        assert "body" in result["template_code"]

    def test_none_tpl_type_returns_original_geom(self, tmp_path):
        geom = dict(self._BASE_GEOM)
        result = _apply_template_decision(
            geom, None, self._FLANGE_META, self._ENVELOPE,
            part_no="", output_dir=str(tmp_path),
        )
        assert result is geom

    def test_missing_required_param_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        result = _apply_template_decision(
            dict(self._BASE_GEOM), "housing",
            {"dim_tolerances": []}, None,  # envelope=None → env_w/d/h=0
            part_no="TEST-002", output_dir=str(tmp_path),
        )
        # All required params are 0/None → housing returns None → fallback
        assert result["type"] == "cylinder"
        assert "template_code" not in result
