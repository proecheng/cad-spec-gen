"""Track A1 SW 纹理运行时回填层。

**职责**：探测 SolidWorks 装机后，把 `PRESET_TO_SW_TEXTURE_MAP` 里的纹理路径
注入到 MATERIAL_PRESETS 的 copy，供 `render_3d.create_pbr_material` 挂 PBR 贴图。

**分发物约束**（CLAUDE.md 用户北极星"SW 装即用 / SW 未装零感知"）：
- `render_config.py` MATERIAL_PRESETS 保持纯 PBR（无 SW 路径字符串）
- SW 纹理映射表存在本模块里（实现细节，不污染 preset 定义层）
- SW 未装 → `backfill_presets_for_sw` 返回原输入，字段不出现

**映射表来源**：18 个 preset 对应的 SW 纹理库相对路径（基于 SOLIDWORKS 2024
`data/Images/textures/` 结构实地探查，见 Track A spec §3.1 + §11.3 发版 gate 分类）。
文件名含空格合法（`rubber/texture/tire tread.jpg`），pathlib 透传。
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Optional


# preset 名 → SW 纹理路径（相对 SwInfo.textures_dir）
# 值是 4 字段 dict：base_color_texture (必填 str) / normal_texture (str | None)
# / roughness_texture (str | None) / metallic_texture (str | None)
PRESET_TO_SW_TEXTURE_MAP: dict[str, dict[str, Optional[str]]] = {
    # ── 金属 (11) ──
    "brushed_aluminum": {
        "base_color_texture": "metal/brushed/brush.jpg",
        "normal_texture": "metal/wire_bump.jpg",
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "anodized_blue": {
        "base_color_texture": "painted/powdercoat_light.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "anodized_green": {
        "base_color_texture": "painted/powdercoat_light.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "anodized_purple": {
        "base_color_texture": "painted/powdercoat_light.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "anodized_red": {
        "base_color_texture": "painted/powdercoat_light.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "black_anodized": {
        "base_color_texture": "painted/powdercoat_dark.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "bronze": {
        "base_color_texture": "metal/cast/cast_iron.jpg",
        "normal_texture": "metal/cast/cast_bump.jpg",
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "copper": {
        "base_color_texture": "metal/polished/chrome1.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "gunmetal": {
        "base_color_texture": "metal/rough/rmetal3.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "dark_steel": {
        "base_color_texture": "metal/steelplaincarbon_diffusemap.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "stainless_304": {
        "base_color_texture": "metal/polished/polishedsteel_diffusemap.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    # ── 塑料 (3) ──
    "white_nylon": {
        "base_color_texture": "plastic/smooth/sgray.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "polycarbonate_clear": {
        "base_color_texture": "plastic/polished/pplastic.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "abs_matte_gray": {
        "base_color_texture": "plastic/smooth/sgray.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    # ── 橡胶/陶瓷 (2) ──
    "black_rubber": {
        "base_color_texture": "rubber/texture/tire tread.jpg",
        "normal_texture": "rubber/texture/tire tread bump.jpg",
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "ceramic_white": {
        "base_color_texture": "plastic/polished/pplastic.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    # ── PEEK/复合 (2) ──
    "peek_amber": {
        "base_color_texture": "plastic/bumpy/plasticmt11030_bump.jpg",
        "normal_texture": None,
        "roughness_texture": None,
        "metallic_texture": None,
    },
    "carbon_fiber_weave": {
        "base_color_texture": "fibers/glassfibre_bump.jpg",
        "normal_texture": "fibers/glassfibre_bump.jpg",
        "roughness_texture": None,
        "metallic_texture": None,
    },
}


def backfill_presets_for_sw(
    presets: Mapping[str, Mapping[str, Any]],
    sw_info: Any | None,
) -> dict[str, dict[str, Any]]:
    """把 PRESET_TO_SW_TEXTURE_MAP 的纹理路径注入 preset 副本。

    行为表：
    | sw_info          | textures_dir       | 行为                     |
    |------------------|--------------------|--------------------------|
    | None             | —                  | 返 deep copy（no-op）    |
    | installed=False  | —                  | 返 deep copy（no-op）    |
    | installed=True   | "" (空串)          | 返 deep copy（no-op）    |
    | installed=True   | 不存在磁盘路径     | 返 deep copy（no-op；防死路径） |
    | installed=True   | 有效目录           | 返 copy + 合并映射表字段 |

    Parameters
    ----------
    presets : Mapping[str, Mapping[str, Any]]
        原 MATERIAL_PRESETS（或任意形状一致的映射）。不会被改动。
    sw_info : Any | None
        `SwInfo` 或等效 dataclass（需有 installed / textures_dir 属性）。
        None 视为 SW 未装。

    Returns
    -------
    dict
        deep copy 后的 preset dict。SW 回填成功时各命中 preset 增加 4 字段。
    """
    result: dict[str, dict[str, Any]] = {k: dict(v) for k, v in presets.items()}

    if sw_info is None:
        return result
    if not getattr(sw_info, "installed", False):
        return result
    tex_dir = getattr(sw_info, "textures_dir", "") or ""
    if not tex_dir:
        return result
    if not os.path.isdir(tex_dir):
        return result

    for name, texture_fields in PRESET_TO_SW_TEXTURE_MAP.items():
        if name not in result:
            # 映射表预留但 preset 未定义（v2.13+ 自定义场景）——跳过
            continue
        result[name].update(texture_fields)
    return result
