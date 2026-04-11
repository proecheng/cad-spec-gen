"""Tests for `MATERIAL_PRESETS` dict in `render_config.py`（v2.9.2 Tier 1）。

`MATERIAL_PRESETS` 是 PBR 材质参数（color / metallic / roughness / appearance）
的单一真相源。v2.3 合并点：appearance 字段被嵌入进每个 preset dict，
之前的 `_PRESET_APPEARANCE` 独立字典被移除。本测试锁在结构契约上。

覆盖点：
- 条目数量 ≥ 15（docstring 承诺）
- 每个 preset 必含 color / metallic / roughness / appearance 四个字段
- color 是 RGBA 4-tuple 且所有值在 [0, 1]
- metallic / roughness 都在 PBR 约定的 [0, 1] 范围
- v2.3 dedup：模块级不应再有 `_PRESET_APPEARANCE` 等副本
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_material_presets_has_at_least_15_entries():
    """render_config.py 顶部 docstring：15 common engineering materials。"""
    from render_config import MATERIAL_PRESETS

    assert len(MATERIAL_PRESETS) >= 15, (
        f"MATERIAL_PRESETS 仅有 {len(MATERIAL_PRESETS)} 条，docstring 承诺 ≥15"
    )


def test_every_preset_has_required_pbr_fields():
    """每个 preset 必含 color / metallic / roughness / appearance 四个字段。"""
    from render_config import MATERIAL_PRESETS

    required = {"color", "metallic", "roughness", "appearance"}
    missing_by_key: dict[str, list[str]] = {}

    for key, preset in MATERIAL_PRESETS.items():
        assert isinstance(preset, dict), (
            f"{key} 不是 dict: {type(preset).__name__}"
        )
        missing = required - set(preset.keys())
        if missing:
            missing_by_key[key] = sorted(missing)

    assert not missing_by_key, (
        "以下 preset 缺字段：\n"
        + "\n".join(f"  {k}: {v}" for k, v in missing_by_key.items())
    )


def test_color_is_rgba_4_tuple_in_unit_range():
    """`color` 必须是 (R, G, B, A) 4-tuple，每个分量在 [0, 1]。"""
    from render_config import MATERIAL_PRESETS

    for key, preset in MATERIAL_PRESETS.items():
        color = preset["color"]
        assert isinstance(color, tuple) and len(color) == 4, (
            f"{key}.color 不是 4-tuple: {color}"
        )
        for i, c in enumerate(color):
            assert 0.0 <= c <= 1.0, (
                f"{key}.color[{i}] = {c}，超出 [0, 1]"
            )


def test_metallic_and_roughness_in_unit_range():
    """PBR 约定：metallic 和 roughness 都在 [0, 1]。"""
    from render_config import MATERIAL_PRESETS

    for key, preset in MATERIAL_PRESETS.items():
        m = preset["metallic"]
        r = preset["roughness"]
        assert isinstance(m, (int, float)) and 0.0 <= m <= 1.0, (
            f"{key}.metallic = {m}"
        )
        assert isinstance(r, (int, float)) and 0.0 <= r <= 1.0, (
            f"{key}.roughness = {r}"
        )


def test_appearance_is_nonempty_string():
    """`appearance` 字段用于 AI enhance prompt，必须是非空字符串。"""
    from render_config import MATERIAL_PRESETS

    for key, preset in MATERIAL_PRESETS.items():
        appearance = preset["appearance"]
        assert isinstance(appearance, str), (
            f"{key}.appearance 不是 str: {type(appearance).__name__}"
        )
        assert len(appearance.strip()) > 0, f"{key}.appearance 为空字符串"


def test_no_duplicate_preset_appearance_dict_exists():
    """v2.3 dedup 回归：模块级不应再存在 `_PRESET_APPEARANCE` 等独立副本。

    单一真相源原则：appearance 只存在于 `MATERIAL_PRESETS[*]["appearance"]`。
    若未来有人加了外部 appearance 字典，本测试会把它抓出来。
    """
    import render_config

    banned = ("_PRESET_APPEARANCE", "PRESET_APPEARANCE", "_APPEARANCE_MAP")
    for name in banned:
        assert not hasattr(render_config, name), (
            f"render_config.{name} 存在 —— v2.3 dedup 规则要求 appearance "
            f"只作为 MATERIAL_PRESETS[*]['appearance'] 的字段存在"
        )
