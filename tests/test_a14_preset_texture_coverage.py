"""Track A1-4 发版 hard gate（重构版集成测试）。

**约束对齐（v2.12 发版 checklist 第 2 条）**：

1. **分发物干净**：MATERIAL_PRESETS 无 SW 纹理字段（细节测试在
   test_render_config_no_sw_strings.py）
2. **回填表完整**：PRESET_TO_SW_TEXTURE_MAP ≥10 preset + 分类 3+3+2+2（细节
   测试在 test_sw_texture_backfill.py）
3. **端到端可用**：SW 装了时 backfill_presets_for_sw 返回的 dict 至少 10 条
   含 base_color_texture

本文件只保留高层集成断言；细粒度单元测试在上述两个姐妹文件。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import render_config as rcfg  # noqa: E402
from adapters.solidworks.sw_texture_backfill import (  # noqa: E402
    PRESET_TO_SW_TEXTURE_MAP,
    backfill_presets_for_sw,
)


def test_release_gate_sw_installed_end_to_end_coverage(tmp_path):
    """端到端：假设 SW 已装 + textures_dir 有效，backfill 后 ≥10 preset 带纹理。"""
    # mock SW 装机（用 tmp_path 造一个有效 textures_dir）
    fake_tex_dir = tmp_path / "textures"
    fake_tex_dir.mkdir()
    sw = SimpleNamespace(installed=True, textures_dir=str(fake_tex_dir))

    backfilled = backfill_presets_for_sw(rcfg.MATERIAL_PRESETS, sw)
    with_tex = [n for n, p in backfilled.items() if p.get("base_color_texture")]

    assert len(with_tex) >= 10, (
        f"发版 gate：SW 装后 backfilled preset 仅 {len(with_tex)} 带 texture，"
        f"要求 ≥10。命中：{sorted(with_tex)}"
    )


def test_release_gate_sw_absent_presets_unchanged():
    """无 SW → backfill 返回的 dict 各 preset 字段数与 MATERIAL_PRESETS 完全一致。"""
    sw = SimpleNamespace(installed=False, textures_dir="")
    backfilled = backfill_presets_for_sw(rcfg.MATERIAL_PRESETS, sw)
    for name, original in rcfg.MATERIAL_PRESETS.items():
        # 不新增字段
        assert set(backfilled[name]) == set(original), (
            f"{name} 字段集被动（SW 未装应无回填）："
            f"{set(backfilled[name]) - set(original)}"
        )


def test_release_gate_map_entries_subset_of_preset_names():
    """PRESET_TO_SW_TEXTURE_MAP 不应预留 MATERIAL_PRESETS 没定义的 preset 名。"""
    unknown = set(PRESET_TO_SW_TEXTURE_MAP) - set(rcfg.MATERIAL_PRESETS)
    assert not unknown, f"映射表含未定义的 preset：{sorted(unknown)}"
