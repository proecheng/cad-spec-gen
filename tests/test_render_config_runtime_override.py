"""A1 重构 R4：render_config 能从 env JSON 载入 runtime preset 覆盖。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import render_config as rcfg  # noqa: E402


def test_load_runtime_override_env_missing_returns_none(monkeypatch):
    monkeypatch.delenv("CAD_RUNTIME_MATERIAL_PRESETS_JSON", raising=False)
    assert rcfg.load_runtime_materials_override() is None


def test_load_runtime_override_env_points_to_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("CAD_RUNTIME_MATERIAL_PRESETS_JSON", str(tmp_path / "nope.json"))
    assert rcfg.load_runtime_materials_override() is None


def test_load_runtime_override_env_valid_returns_dict(monkeypatch, tmp_path):
    payload = {
        "brushed_aluminum": {
            "color": [0.82, 0.82, 0.84, 1.0],
            "metallic": 1.0,
            "roughness": 0.18,
            "base_color_texture": "metal/brushed/brush.jpg",
        }
    }
    json_path = tmp_path / "runtime_materials.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("CAD_RUNTIME_MATERIAL_PRESETS_JSON", str(json_path))
    result = rcfg.load_runtime_materials_override()
    assert result is not None
    assert "brushed_aluminum" in result
    assert result["brushed_aluminum"]["base_color_texture"] == "metal/brushed/brush.jpg"


def test_load_runtime_override_invalid_json_returns_none(monkeypatch, tmp_path):
    json_path = tmp_path / "bad.json"
    json_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("CAD_RUNTIME_MATERIAL_PRESETS_JSON", str(json_path))
    assert rcfg.load_runtime_materials_override() is None
