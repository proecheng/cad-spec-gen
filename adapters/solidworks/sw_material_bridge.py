"""SolidWorks 材质桥接 — 解析 sldmat XML，生成关键词路由扩展。

sldmat 文件是 UTF-16 LE XML，带 BOM。每个文件包含多个 classification，
每个 classification 下有多个 material，每个 material 有物理属性和 shader 引用。

用法::

    from adapters.solidworks.sw_material_bridge import parse_sldmat

    # 解析单个 sldmat 文件
    materials = parse_sldmat(Path("materials.sldmat"))
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

__all__ = [
    "SwMaterial",
    "parse_sldmat",
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
