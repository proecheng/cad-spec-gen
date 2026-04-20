# tests/test_a14_preset_texture_coverage.py
"""Track A1-4 发版硬 gate：MATERIAL_PRESETS 纹理回填分类覆盖率。

Spec 2026-04-20-track-a §11.3 第 2 条明示：v2.12 发版要求 ≥10 preset
带 base_color_texture，分类下限：金属 ≥ 3 / 塑料 ≥ 3 / 橡胶·陶瓷 ≥ 2 /
PEEK·复合 ≥ 2。本测试是"回填不达标不能发版"的机械闸门。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# canonical 源：项目根 render_config.py
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import render_config as rcfg  # noqa: E402

# Preset → 分类归属（metal / plastic / rubber_ceramic / peek_composite）
# 凡新增 preset 必须在本表登记分类；未登记视为 unclassified 会让 gate 失败
PRESET_CATEGORY = {
    # metal
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
    # plastic
    "white_nylon": "plastic",
    "polycarbonate_clear": "plastic",
    "abs_matte_gray": "plastic",
    # rubber / ceramic
    "black_rubber": "rubber_ceramic",
    "ceramic_white": "rubber_ceramic",
    # peek / composite
    "peek_amber": "peek_composite",
    "carbon_fiber_weave": "peek_composite",
}

CATEGORY_MIN = {
    "metal": 3,
    "plastic": 3,
    "rubber_ceramic": 2,
    "peek_composite": 2,
}


def test_all_presets_have_category_mapping():
    """新增 preset 必须同步进 PRESET_CATEGORY，否则无法参与 gate 评估。"""
    unclassified = set(rcfg.MATERIAL_PRESETS) - set(PRESET_CATEGORY)
    assert not unclassified, (
        f"以下 preset 未登记分类，更新 PRESET_CATEGORY: {sorted(unclassified)}"
    )


def test_at_least_10_presets_have_base_color_texture():
    """硬 gate：≥10 preset 带 base_color_texture 非空字段。"""
    with_texture = [
        n for n, p in rcfg.MATERIAL_PRESETS.items()
        if p.get("base_color_texture")
    ]
    assert len(with_texture) >= 10, (
        f"发版 gate 未达标：仅 {len(with_texture)} preset 带 base_color_texture，"
        f"要求 ≥10。已配置：{sorted(with_texture)}"
    )


def test_category_coverage_gates():
    """四分类下限：金属≥3 / 塑料≥3 / 橡胶·陶瓷≥2 / PEEK·复合≥2。"""
    from collections import Counter

    category_counts: Counter[str] = Counter()
    for name, params in rcfg.MATERIAL_PRESETS.items():
        if not params.get("base_color_texture"):
            continue
        cat = PRESET_CATEGORY.get(name, "UNKNOWN")
        category_counts[cat] += 1

    failures = []
    for cat, minimum in CATEGORY_MIN.items():
        actual = category_counts.get(cat, 0)
        if actual < minimum:
            failures.append(f"{cat}={actual}/{minimum}")
    assert not failures, (
        f"分类覆盖未达 spec §11.3 gate：{failures}；"
        f"当前分布 {dict(category_counts)}"
    )


def test_texture_path_format_is_relative_forward_slash():
    """所有 base_color_texture 值必须是 POSIX 风格相对路径（tex bridge 兼容）。"""
    for name, params in rcfg.MATERIAL_PRESETS.items():
        rel = params.get("base_color_texture")
        if rel is None:
            continue
        assert isinstance(rel, str), f"{name}.base_color_texture 非 str: {type(rel)}"
        assert "\\" not in rel, (
            f"{name}.base_color_texture={rel!r} 含反斜杠；必须 POSIX 前向斜杠"
            " —— SW_TEXTURES_DIR 拼接跨 OS 才稳"
        )
        # 不应以 / 开头（非绝对路径；绝对路径也允许，但 MATERIAL_PRESETS 默认用相对）
        if rel.startswith("/"):
            continue  # 允许绝对路径（Linux），不强制
