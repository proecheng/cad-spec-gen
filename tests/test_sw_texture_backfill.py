"""Track A1 SW 纹理运行时回填层 —— 单元测试 + 分类覆盖 gate。

spec §11.3 发版 gate（重构版）：PRESET_TO_SW_TEXTURE_MAP ≥10 preset 映射，
分类覆盖 金属≥3 / 塑料≥3 / 橡胶·陶瓷≥2 / PEEK·复合≥2。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from adapters.solidworks.sw_texture_backfill import (  # noqa: E402
    PRESET_TO_SW_TEXTURE_MAP,
    backfill_presets_for_sw,
)


# —————— 映射表覆盖率 gate ——————

PRESET_CATEGORY = {
    "brushed_aluminum": "metal",
    "anodized_blue": "metal",
    "anodized_green": "metal",
    "anodized_purple": "metal",
    "anodized_red": "metal",
    "black_anodized": "metal",
    "bronze": "metal",
    "copper": "metal",
    "gunmetal": "metal",
    "dark_steel": "metal",
    "stainless_304": "metal",
    "white_nylon": "plastic",
    "polycarbonate_clear": "plastic",
    "abs_matte_gray": "plastic",
    "black_rubber": "rubber_ceramic",
    "ceramic_white": "rubber_ceramic",
    "peek_amber": "peek_composite",
    "carbon_fiber_weave": "peek_composite",
}
CATEGORY_MIN = {"metal": 3, "plastic": 3, "rubber_ceramic": 2, "peek_composite": 2}


def test_map_has_at_least_10_entries():
    assert len(PRESET_TO_SW_TEXTURE_MAP) >= 10


def test_map_category_coverage():
    from collections import Counter
    counts: Counter[str] = Counter()
    for name in PRESET_TO_SW_TEXTURE_MAP:
        counts[PRESET_CATEGORY.get(name, "UNKNOWN")] += 1
    failures = [
        f"{cat}={counts.get(cat, 0)}/{m}"
        for cat, m in CATEGORY_MIN.items() if counts.get(cat, 0) < m
    ]
    assert not failures, f"分类覆盖未达 gate：{failures}"


def test_map_entries_contain_base_color_texture():
    for name, entry in PRESET_TO_SW_TEXTURE_MAP.items():
        assert "base_color_texture" in entry, f"{name} 缺 base_color_texture"
        assert isinstance(entry["base_color_texture"], str), f"{name} 非 str"
        assert "\\" not in entry["base_color_texture"], f"{name} 含反斜杠"


# —————— backfill_presets_for_sw 函数行为测试 ——————

def test_backfill_no_sw_returns_input_unchanged():
    presets = {"foo": {"color": (1, 1, 1, 1)}}
    result = backfill_presets_for_sw(presets, sw_info=None)
    assert result == presets
    # 不可改动原输入
    assert result is not presets or presets["foo"] == {"color": (1, 1, 1, 1)}


def test_backfill_sw_not_installed_returns_input_unchanged():
    sw_info = SimpleNamespace(installed=False, textures_dir="")
    presets = {"brushed_aluminum": {"color": (0.8, 0.8, 0.8, 1.0)}}
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    assert result == presets


def test_backfill_sw_installed_injects_texture_fields(tmp_path):
    real_dir = tmp_path / "sw_textures"
    real_dir.mkdir()
    sw_info = SimpleNamespace(installed=True, textures_dir=str(real_dir))
    presets = {
        "brushed_aluminum": {
            "color": (0.82, 0.82, 0.84, 1.0),
            "metallic": 1.0,
            "roughness": 0.18,
        }
    }
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    assert "base_color_texture" not in presets["brushed_aluminum"]
    r = result["brushed_aluminum"]
    assert r["color"] == (0.82, 0.82, 0.84, 1.0)
    assert r["base_color_texture"] == "metal/brushed/brush.jpg"
    assert r["normal_texture"] == "metal/wire_bump.jpg"
    assert r["roughness_texture"] is None
    assert r["metallic_texture"] is None


def test_backfill_unknown_preset_not_in_map_passthrough(tmp_path):
    """映射表没登记的 preset 保持原样。"""
    real_dir = tmp_path / "sw_textures"
    real_dir.mkdir()
    sw_info = SimpleNamespace(installed=True, textures_dir=str(real_dir))
    presets = {"custom_preset": {"color": (0.5, 0.5, 0.5, 1.0)}}
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    assert "base_color_texture" not in result["custom_preset"]


def test_backfill_empty_textures_dir_skips_even_when_installed():
    sw_info = SimpleNamespace(installed=True, textures_dir="")
    presets = {"brushed_aluminum": {"color": (0.8, 0.8, 0.8, 1.0)}}
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    assert "base_color_texture" not in result["brushed_aluminum"]


def test_backfill_nonexistent_textures_dir_skips():
    sw_info = SimpleNamespace(installed=True, textures_dir="/nonexistent/xyz123_abc_never_exists")
    presets = {"brushed_aluminum": {"color": (0.8, 0.8, 0.8, 1.0)}}
    result = backfill_presets_for_sw(presets, sw_info=sw_info)
    assert "base_color_texture" not in result["brushed_aluminum"]
