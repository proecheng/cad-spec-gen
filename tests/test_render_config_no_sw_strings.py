"""Track A1 重构验收：MATERIAL_PRESETS 分发物不含 SW 纹理路径字符串。

用户北极星"SW 装即用 / SW 未装零感知"要求：render_config.py 的 preset 定义
只含纯 PBR 标量（color/metallic/roughness/appearance/ior/specular/sss/sss_color/
anisotropic）。SW 纹理路径在 adapters/solidworks/sw_texture_backfill.py 里
作为运行时回填实现细节，不污染 preset 层。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import render_config as rcfg  # noqa: E402


# 允许的 preset 字段白名单（v2.11 原有 + 3 新 preset 可能用的）
ALLOWED_PRESET_FIELDS = {
    "color", "metallic", "roughness", "anisotropic",
    "ior", "specular", "sss", "sss_color",
    "appearance",
    # label 由 resolve_material 动态注入，非 preset 静态字段但允许
    "label",
}

FORBIDDEN_SW_TEXTURE_FIELDS = {
    "base_color_texture", "normal_texture",
    "roughness_texture", "metallic_texture",
    "texture_scale",
}


def test_no_preset_has_sw_texture_fields():
    """分发物约束：MATERIAL_PRESETS 不应含任何 SW 纹理路径字段。"""
    violations = []
    for name, params in rcfg.MATERIAL_PRESETS.items():
        forbidden = FORBIDDEN_SW_TEXTURE_FIELDS & set(params)
        if forbidden:
            violations.append(f"{name}: {sorted(forbidden)}")
    assert not violations, (
        f"preset 含 SW 纹理字段（应移到 sw_texture_backfill.py）：{violations}"
    )


def test_preset_fields_are_all_pbr_scalars():
    """preset 字段必须全在 PBR 标量白名单内（除字符串 appearance）。"""
    violations = []
    for name, params in rcfg.MATERIAL_PRESETS.items():
        unknown = set(params) - ALLOWED_PRESET_FIELDS
        if unknown:
            violations.append(f"{name}: {sorted(unknown)}")
    assert not violations, (
        f"preset 含未知字段（白名单外）：{violations}"
    )


def test_no_sw_path_string_in_preset_values():
    """更严：preset 字符串值里不应出现 SW 纹理目录结构常见字符串。"""
    sw_markers = ("metal/", "plastic/", "painted/", "rubber/", "fibers/", "_bump.jpg")
    violations = []
    for name, params in rcfg.MATERIAL_PRESETS.items():
        for field, value in params.items():
            if isinstance(value, str):
                for marker in sw_markers:
                    if marker in value:
                        violations.append(f"{name}.{field}={value!r} 含 SW 标记 {marker!r}")
    assert not violations, f"preset 字符串值含 SW 标记：{violations}"
