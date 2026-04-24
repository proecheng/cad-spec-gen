"""Track C Task 10/11: fal_enhancer / comfyui_enhancer hero_image 注入 + seed 支持的单元测试。"""

import importlib.util
import os
import sys

import pytest
from unittest.mock import MagicMock, patch


def _load_fal_enhancer():
    """通过 importlib 加载 fal_enhancer.py（非包模块），并注册到 sys.modules。"""
    fal_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "src", "cad_spec_gen", "data", "python_tools", "fal_enhancer.py",
    )
    spec = importlib.util.spec_from_file_location("fal_enhancer", fal_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fal_enhancer"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_fal_canny_replaced_with_hero_image(tmp_path):
    """fal_cfg 含 hero_image 时，controlnets[0].control_image_url 被替换为 V1 参考 URL"""
    pytest.importorskip("fal_client")
    hero = tmp_path / "v1_hero.jpg"
    hero.write_bytes(b"fake_image_bytes")

    captured = {}

    def mock_subscribe(endpoint, arguments, with_logs=False):
        captured["args"] = arguments
        return {"images": [{"url": "https://mock/out.jpg"}]}

    def mock_upload(path, **kw):
        return f"https://mock/uploaded/{os.path.basename(path)}"

    png = tmp_path / "V2_render.png"
    png.write_bytes(b"fake_png")

    fal_enhancer = _load_fal_enhancer()

    fal_cfg = {
        "model": "fal-ai/flux-general",
        "hero_image": str(hero),
    }
    with patch("fal_enhancer._upload_with_retry", side_effect=mock_upload), \
         patch("fal_client.subscribe", side_effect=mock_subscribe), \
         patch("fal_enhancer._find_depth_for_png", return_value=(None, False)), \
         patch("urllib.request.urlretrieve"):
        fal_enhancer.enhance_image(str(png), "test prompt", fal_cfg, "V2", {})

    controlnets = captured["args"]["controlnets"]
    assert controlnets[0]["control_image_url"] == "https://mock/uploaded/v1_hero.jpg"


def test_fal_seed_injected_when_set(tmp_path):
    """fal_cfg 含 seed 整数时，api_args 包含 seed 键"""
    pytest.importorskip("fal_client")
    png = tmp_path / "V2.png"
    png.write_bytes(b"x")
    captured = {}

    def mock_subscribe(endpoint, arguments, with_logs=False):
        captured["args"] = arguments
        return {"images": [{"url": "https://mock/out.jpg"}]}

    fal_enhancer = _load_fal_enhancer()

    with patch("fal_enhancer._upload_with_retry", return_value="https://mock/img.jpg"), \
         patch("fal_client.subscribe", side_effect=mock_subscribe), \
         patch("fal_enhancer._find_depth_for_png", return_value=(None, False)), \
         patch("urllib.request.urlretrieve"):
        fal_enhancer.enhance_image(str(png), "prompt", {"seed": 42}, "V2", {})

    assert captured["args"].get("seed") == 42


def test_comfyui_hero_image_replaces_input_node(tmp_path):
    """comfyui_cfg 含 hero_image 时，workflow input_image 节点被替換为 hero 上传名"""
    pytest.importorskip("requests")
    hero = tmp_path / "v1_hero.jpg"
    hero.write_bytes(b"hero_bytes")
    png = tmp_path / "V2.png"
    png.write_bytes(b"render_bytes")

    uploaded_names = []

    def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        if "upload" in url:
            fname = list(kwargs.get("files", {}).values())[0][0]
            uploaded_names.append(fname)
            resp.json.return_value = {"name": fname}
        elif "/prompt" in url:
            resp.ok = True
            resp.json.return_value = {"prompt_id": "pid1"}
        return resp

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "pid1": {"outputs": {"12": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}
        }
        return resp

    comfyui_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "src", "cad_spec_gen", "data", "python_tools", "comfyui_enhancer.py"
    )
    spec = importlib.util.spec_from_file_location("comfyui_enhancer", comfyui_path)
    comfyui_enhancer = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_enhancer"] = comfyui_enhancer
    spec.loader.exec_module(comfyui_enhancer)

    cfg = {"hero_image": str(hero), "host": "127.0.0.1", "port": 8188}
    with patch("requests.post", side_effect=mock_post), \
         patch("requests.get", side_effect=mock_get), \
         patch("comfyui_enhancer._download_image", return_value=None):
        try:
            comfyui_enhancer.enhance_image(str(png), "prompt", cfg, "V2", {})
        except Exception:
            pass  # 下载失败不影响断言

    # hero ファイル名がアップロードキューに含まれること
    assert "v1_hero.jpg" in uploaded_names


def test_cad_pipeline_build_enhance_cfg_with_hero():
    """_build_enhance_cfg_with_hero: hero_image を注入した浅拷贝を返し、原 cfg を変更しない"""
    import importlib.util
    import os
    import sys
    import types
    from unittest.mock import MagicMock

    # cad_pipeline.py はトップレベルで cad_paths / sw_detect を import するため
    # exec_module 前にスタブを sys.modules に注入する
    _stub_cad_paths = types.ModuleType("cad_paths")
    _stub_cad_paths.SKILL_ROOT = "/fake/skill"
    _stub_cad_paths.PROJECT_ROOT = "/fake/project"
    _stub_cad_paths.get_blender_path = lambda: "/fake/blender"
    _stub_cad_paths.get_subsystem_dir = lambda *a, **kw: "/fake/sub"
    _stub_cad_paths.get_output_dir = lambda: "/fake/output"
    _stub_cad_paths.get_gemini_script = lambda: "/fake/gemini"
    sys.modules.setdefault("cad_paths", _stub_cad_paths)

    _stub_sw_detect = types.ModuleType("adapters.solidworks.sw_detect")
    _stub_sw_detect.detect_solidworks = MagicMock(return_value=MagicMock(installed=False))
    sys.modules.setdefault("adapters", types.ModuleType("adapters"))
    sys.modules.setdefault("adapters.solidworks", types.ModuleType("adapters.solidworks"))
    sys.modules.setdefault("adapters.solidworks.sw_detect", _stub_sw_detect)

    pipeline_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "src", "cad_spec_gen", "data", "python_tools", "cad_pipeline.py"
    )
    spec = importlib.util.spec_from_file_location("cad_pipeline_hero_test", pipeline_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cfg = {"model": "fal-ai/flux-general"}
    hero = "/tmp/v1_hero.jpg"
    result = mod._build_enhance_cfg_with_hero(cfg, hero)
    assert result["hero_image"] == hero
    assert "hero_image" not in cfg  # 原始 cfg 不変
