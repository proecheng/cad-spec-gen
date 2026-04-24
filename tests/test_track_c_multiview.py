"""Track C Task 10: fal_enhancer hero_image 注入 + seed 支持的单元测试。"""

import importlib.util
import os
import sys

from unittest.mock import patch


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
