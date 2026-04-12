"""SolidWorks 材质桥接 — 解析 sldmat XML，生成关键词路由扩展。

sldmat 文件是 UTF-16 LE XML，带 BOM。每个文件包含多个 classification，
每个 classification 下有多个 material，每个 material 有物理属性和 shader 引用。

用法::

    from adapters.solidworks.sw_material_bridge import (
        parse_sldmat, build_bundle, load_sw_material_bundle,
    )

    # 解析单个 sldmat 文件
    materials = parse_sldmat(Path("materials.sldmat"))

    # 一键加载所有 SW 材质路由扩展
    bundle = load_sw_material_bundle()
"""

from __future__ import annotations

import logging
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

__all__ = [
    "SwMaterial",
    "SwMaterialBundle",
    "parse_sldmat",
    "build_bundle",
    "load_sw_material_bundle",
    "reset_all_sw_caches",
    "SW_CLASSIFICATION_TO_PRESET",
    "EQUIVALENCE_MAP",
]


# ─── 数据类 ───────────────────────────────────────────────────────────────


@dataclass
class SwMaterial:
    """从 sldmat XML 解析出的单个材质条目。

    Attributes:
        name: 材质名称，如 "1023 Carbon Steel Sheet (SS)"
        classification: 分类名称，如 "Steel"
        density_kg_m3: 密度（kg/m³）
        elastic_modulus: 弹性模量（Pa），可选
        yield_strength: 屈服强度（Pa），可选
        thermal_conductivity: 热导率（W/(m·K)），可选
        shader_path: P2M 着色器相对路径，可选
    """

    name: str
    classification: str
    density_kg_m3: float = 0.0
    elastic_modulus: Optional[float] = None
    yield_strength: Optional[float] = None
    thermal_conductivity: Optional[float] = None
    shader_path: Optional[str] = None


@dataclass
class SwMaterialBundle:
    """SW 材质解析结果的两组路由数据。

    type_keywords: 合并进 MATERIAL_TYPE_KEYWORDS（分类关键词路由）
        例 {"steel": ["Carbon Steel", ...], "al": ["6061 Alloy", ...]}
    preset_keywords: 合并进 _MAT_PRESET（preset 关键词路由）
        例 {"Carbon Steel": "dark_steel", "6061 Alloy": "brushed_aluminum"}
        值域 ⊂ MATERIAL_PRESETS.keys()
    """

    type_keywords: dict[str, list[str]] = field(default_factory=dict)
    preset_keywords: dict[str, str] = field(default_factory=dict)


# ─── sldmat XML 解析 ─────────────────────────────────────────────────────


def _local_tag(elem: ET.Element) -> str:
    """去掉 namespace，返回 local tag name。

    sldmat 使用 namespace（如 http://www.solidworks.com/sldmaterials），
    但不同 SW 版本的 namespace URI 可能不同。用 local name 做宽松匹配。
    """
    tag = elem.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_sldmat(path: Path) -> list[SwMaterial]:
    """解析单个 sldmat 文件，返回 SwMaterial 列表。

    文件不存在或解析失败返回空列表（warning log，不 raise）。

    Args:
        path: sldmat 文件路径。

    Returns:
        SwMaterial 列表，每个对象对应一个 <material> 条目。
    """
    if not path.is_file():
        log.warning("sldmat 文件不存在: %s", path)
        return []
    try:
        tree = ET.parse(str(path))
    except ET.ParseError as e:
        log.warning("sldmat 解析失败 %s: %s", path, e)
        return []

    root = tree.getroot()
    results: list[SwMaterial] = []

    for cls_elem in root:
        if _local_tag(cls_elem) != "classification":
            continue
        cls_name = cls_elem.get("name", "")

        for mat_elem in cls_elem:
            if _local_tag(mat_elem) != "material":
                continue
            mat_name = mat_elem.get("name", "")
            if not mat_name:
                continue

            mat = SwMaterial(name=mat_name, classification=cls_name)

            # 解析物理属性和着色器
            for child in mat_elem:
                if _local_tag(child) == "physicalproperties":
                    _parse_physical_props(child, mat)
                elif _local_tag(child) == "shaders":
                    _parse_shaders(child, mat)

            results.append(mat)

    return results


def _parse_physical_props(props_elem: ET.Element, mat: SwMaterial) -> None:
    """从 <physicalproperties> 提取物理属性到 SwMaterial。

    支持的属性标签：
    - DENS: 密度 (kg/m³)
    - EX: 弹性模量 (Pa)
    - SIGYLD: 屈服强度 (Pa)
    - KX: 热导率 (W/(m·K))
    """
    for prop in props_elem:
        tag = _local_tag(prop)
        val_str = prop.get("value", "")
        try:
            val = float(val_str)
        except (ValueError, TypeError):
            continue

        if tag == "DENS":
            mat.density_kg_m3 = val
        elif tag == "EX":
            mat.elastic_modulus = val
        elif tag == "SIGYLD":
            mat.yield_strength = val
        elif tag == "KX":
            mat.thermal_conductivity = val


def _parse_shaders(shaders_elem: ET.Element, mat: SwMaterial) -> None:
    """从 <shaders> 提取 pwshader2 的 p2m 路径。

    只取第一个 pwshader2 条目的 path 属性。
    """
    for shader in shaders_elem:
        if _local_tag(shader) == "pwshader2":
            mat.shader_path = shader.get("path")
            break


# ─── classification → material_type / preset 映射 ────────────────────────

# SW classification 名 → 管道 material_type 码
_SW_CLASSIFICATION_TO_TYPE: dict[str, str] = {
    "Steel":             "steel",
    "Iron":              "steel",
    "Aluminum Alloys":   "al",
    "Copper Alloys":     "steel",   # 管道中 copper 归入 steel 类
    "Titanium Alloys":   "steel",
    "Zinc Alloys":       "steel",
    "Nickel Alloys":     "steel",
    "Plastics":          "nylon",
    "Rubber":            "rubber",
    "Other Non-metals":  "nylon",
}

# SW classification 名 → 管道 MATERIAL_PRESETS key
SW_CLASSIFICATION_TO_PRESET: dict[str, str] = {
    "Steel":             "dark_steel",
    "Iron":              "dark_steel",
    "Aluminum Alloys":   "brushed_aluminum",
    "Copper Alloys":     "copper",
    "Titanium Alloys":   "stainless_304",
    "Zinc Alloys":       "dark_steel",
    "Nickel Alloys":     "stainless_304",
    "Plastics":          "white_nylon",
    "Rubber":            "black_rubber",
    "Other Non-metals":  "white_nylon",
}

# SW 材质名 → 现有 MATERIAL_PROPS key（已有等价物的不重复注入 preset_keywords）
EQUIVALENCE_MAP: dict[str, str] = {
    "AISI 304":                     "SUS304",
    "304 Stainless Steel":          "SUS304",
    "201 Annealed Stainless Steel": "SUS304",
    "316L Stainless Steel":         "SUS316L",
    "7075 Alloy":                   "7075-T6",
    "6061 Alloy":                   "6061-T6",
    "6063 Alloy":                   "6063",
}


def build_bundle(materials: list[SwMaterial]) -> SwMaterialBundle:
    """从 SwMaterial 列表构建路由扩展 bundle。

    遍历材质列表，根据 classification 映射到 material_type 和 preset：
    - type_keywords: 所有材质都贡献（包括 EQUIVALENCE_MAP 中的）
    - preset_keywords: EQUIVALENCE_MAP 中的材质不进入（已有等价物覆盖）

    Args:
        materials: parse_sldmat() 的返回值。

    Returns:
        SwMaterialBundle，含 type_keywords 和 preset_keywords。
    """
    type_kw: dict[str, list[str]] = {}
    preset_kw: dict[str, str] = {}

    for mat in materials:
        cls = mat.classification
        mtype = _SW_CLASSIFICATION_TO_TYPE.get(cls)
        preset = SW_CLASSIFICATION_TO_PRESET.get(cls)

        # 所有材质都贡献 type_keywords（包括等价映射中的）
        if mtype:
            type_kw.setdefault(mtype, []).append(mat.name)

        # EQUIVALENCE_MAP 中的材质不进入 preset_keywords
        if preset and mat.name not in EQUIVALENCE_MAP:
            preset_kw[mat.name] = preset

    return SwMaterialBundle(type_keywords=type_kw, preset_keywords=preset_kw)


# ─── 一键加载入口 ─────────────────────────────────────────────────────────

_cached_bundle: Optional[SwMaterialBundle] = None
_BUNDLE_LOADED: bool = False  # 区分 None（未加载）和 None（加载后 SW 不可用）


def load_sw_material_bundle() -> Optional[SwMaterialBundle]:
    """一键加载 SW 材质路由扩展。

    内部使用 _cached_bundle 缓存结果，多次调用只解析一次 sldmat。
    get_material_type_keywords() 和 get_material_preset_keywords()
    都调用此函数，但不会触发重复 I/O。

    返回条件：
    - 非 Windows → None
    - SW 未安装或 version_year < 2020 → None
    - 无 sldmat 文件 → None
    - 解析后无材质 → None
    """
    global _cached_bundle, _BUNDLE_LOADED
    if _BUNDLE_LOADED:
        return _cached_bundle

    _BUNDLE_LOADED = True

    if sys.platform != "win32":
        return None

    try:
        from adapters.solidworks.sw_detect import detect_solidworks
    except ImportError:
        return None

    info = detect_solidworks()
    if not info.installed or (info.version_year or 0) < 2020:
        return None

    if not info.sldmat_paths:
        log.info("SW 已安装但未找到 sldmat 文件")
        return None

    all_materials: list[SwMaterial] = []
    for sldmat_path in info.sldmat_paths:
        parsed = parse_sldmat(Path(sldmat_path))
        all_materials.extend(parsed)
        if parsed:
            log.info("解析 %s: %d 种材质", Path(sldmat_path).name, len(parsed))

    if not all_materials:
        return None

    _cached_bundle = build_bundle(all_materials)
    log.info(
        "SW 材质桥接: type_keywords %d 类, preset_keywords %d 条",
        len(_cached_bundle.type_keywords),
        len(_cached_bundle.preset_keywords),
    )
    return _cached_bundle


def reset_all_sw_caches() -> None:
    """测试用统一入口：重置 bundle 缓存 + 所有下游合并缓存。

    逐个 try/except ImportError 包裹，避免下游模块未安装时报错。
    """
    global _cached_bundle, _BUNDLE_LOADED
    _cached_bundle = None
    _BUNDLE_LOADED = False

    try:
        from adapters.solidworks.sw_detect import _reset_cache
        _reset_cache()
    except ImportError:
        pass

    try:
        from cad_spec_defaults import _reset_material_cache
        _reset_material_cache()
    except ImportError:
        pass

    try:
        from cad_pipeline import _reset_preset_keywords_cache
        _reset_preset_keywords_cache()
    except ImportError:
        pass
