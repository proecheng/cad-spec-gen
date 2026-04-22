"""Track A1 R3：_build_blender_env 扩展 — SW 装了要落盘 runtime_materials.json。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_build_env_sw_installed_writes_runtime_materials_json(tmp_path, monkeypatch):
    """SW 装了 + textures_dir 真存在 → 落盘 runtime_materials.json + env 指路径。"""
    # 构造 fake SW textures 目录
    fake_sw_tex = tmp_path / "sw_textures"
    fake_sw_tex.mkdir()
    fake_sw = SimpleNamespace(installed=True, textures_dir=str(fake_sw_tex))

    # monkeypatch run_id artifact dir 到 tmp_path
    run_artifacts = tmp_path / "artifacts" / "run_123"
    run_artifacts.mkdir(parents=True)
    monkeypatch.setenv("CAD_RUN_ARTIFACTS_DIR", str(run_artifacts))

    import cad_pipeline
    with patch.object(cad_pipeline, "detect_solidworks", return_value=fake_sw):
        env = cad_pipeline._build_blender_env()

    # env 注入检查
    assert env.get("SW_TEXTURES_DIR") == str(fake_sw_tex)
    json_path = env.get("CAD_RUNTIME_MATERIAL_PRESETS_JSON")
    assert json_path, "CAD_RUNTIME_MATERIAL_PRESETS_JSON env 未注入"

    # 落盘的 JSON 可读 + 含纹理字段
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert "brushed_aluminum" in data
    assert data["brushed_aluminum"]["base_color_texture"] == "metal/brushed/brush.jpg"


def test_build_env_sw_not_installed_no_runtime_json(tmp_path, monkeypatch):
    """SW 未装 → 不落盘 runtime_materials.json + env 不含 CAD_RUNTIME 变量。"""
    fake_sw = SimpleNamespace(installed=False, textures_dir="")
    monkeypatch.setenv("CAD_RUN_ARTIFACTS_DIR", str(tmp_path))

    import cad_pipeline
    with patch.object(cad_pipeline, "detect_solidworks", return_value=fake_sw):
        env = cad_pipeline._build_blender_env()

    assert "SW_TEXTURES_DIR" not in env
    assert "CAD_RUNTIME_MATERIAL_PRESETS_JSON" not in env


def test_build_env_sw_installed_but_textures_dir_missing(tmp_path, monkeypatch):
    """SW 装了但 textures_dir 不是有效目录 → 不注入（防死路径）。"""
    fake_sw = SimpleNamespace(installed=True, textures_dir="/nonexistent/xyz123")
    monkeypatch.setenv("CAD_RUN_ARTIFACTS_DIR", str(tmp_path))

    import cad_pipeline
    with patch.object(cad_pipeline, "detect_solidworks", return_value=fake_sw):
        env = cad_pipeline._build_blender_env()

    assert "SW_TEXTURES_DIR" not in env
    assert "CAD_RUNTIME_MATERIAL_PRESETS_JSON" not in env
