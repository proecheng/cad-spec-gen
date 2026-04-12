# SolidWorks 集成 Phase SW-A 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 SolidWorks 材质库作为可选增强层接入管道——检测 SW 安装、解析 sldmat 材质、扩展关键词路由、增强 env-check 报告。

**Architecture:** `sw_detect.py` 从注册表动态获取 SW 安装信息；`sw_material_bridge.py` 解析 sldmat XML 生成关键词路由扩展；`cad_spec_defaults.py` 和 `cad_pipeline.py` 的路由表通过延迟加载函数合并 SW 数据。非 Windows 或无 SW 时全部短路，零退化。

**Tech Stack:** Python 3.11+, stdlib only (winreg, xml.etree, os, pathlib), pytest

**Spec:** `docs/superpowers/specs/2026-04-12-solidworks-integration-design.md` (rev3)

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `adapters/solidworks/__init__.py` | 创建 | 包声明 |
| `adapters/solidworks/sw_detect.py` | 创建 | SW 安装检测 + SwInfo 数据类 |
| `adapters/solidworks/sw_material_bridge.py` | 创建 | sldmat 解析 + SwMaterialBundle + 路由生成 |
| `cad_spec_defaults.py` | 修改 L452-466 | `get_material_type_keywords()` + `classify_material_type()` 改造 |
| `cad_pipeline.py` | 修改 L461-468, L502, L529, L586 | `_MAT_PRESET` 提为模块级 + `get_material_preset_keywords()` |
| `tools/hybrid_render/check_env.py` | 修改 L156 后 + L215 后 | `enhancements` 字段 + 报告输出 |
| `tests/test_sw_detect.py` | 创建 | sw_detect 单元测试 |
| `tests/test_sw_material_bridge.py` | 创建 | 材质桥接单元测试 |
| `tests/test_sw_routing_integration.py` | 创建 | 路由函数化 + 无 SW 等同 集成测试 |
| `tests/fixtures/generate_sldmat_fixture.py` | 创建 | 测试用 sldmat 生成脚本 |

---

### Task 1: `sw_detect.py` — SwInfo 数据类与检测函数

**Files:**
- Create: `adapters/solidworks/__init__.py`
- Create: `adapters/solidworks/sw_detect.py`
- Create: `tests/test_sw_detect.py`

- [ ] **Step 1: 创建包目录和空 `__init__.py`**

```python
# adapters/solidworks/__init__.py
"""SolidWorks 可选集成模块。仅在 Windows + SW 已安装时生效。"""
```

- [ ] **Step 2: 写 `SwInfo` 数据类的测试**

```python
# tests/test_sw_detect.py
"""sw_detect 单元测试。用 mock 模拟各种 SW 安装场景。"""

import sys
import pytest


def test_non_windows_returns_not_installed(monkeypatch):
    """非 Windows 平台直接返回 installed=False。"""
    monkeypatch.setattr(sys, "platform", "linux")
    # 强制重新导入以触发平台分支
    import importlib
    from adapters.solidworks import sw_detect
    importlib.reload(sw_detect)
    info = sw_detect.detect_solidworks()
    assert info.installed is False
    assert info.version is None
    assert info.sldmat_paths == []
    assert info.toolbox_dir is None
    assert info.com_available is False
    assert info.pywin32_available is False
    # 恢复平台
    monkeypatch.setattr(sys, "platform", "win32")
    importlib.reload(sw_detect)


def test_sw_info_dataclass_defaults():
    """SwInfo 数据类默认值正确。"""
    from adapters.solidworks.sw_detect import SwInfo
    info = SwInfo(installed=False)
    assert info.version is None
    assert info.version_year is None
    assert info.install_dir is None
    assert info.sldmat_paths == []
    assert info.com_available is False
    assert info.pywin32_available is False
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/test_sw_detect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.solidworks'`

- [ ] **Step 4: 实现 `SwInfo` 数据类和 `detect_solidworks()` 基础框架**

```python
# adapters/solidworks/sw_detect.py
"""SolidWorks 安装检测。

从注册表动态获取所有路径，不硬编码任何文件系统路径。
非 Windows 平台直接短路返回。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__all__ = ["SwInfo", "detect_solidworks"]


@dataclass
class SwInfo:
    """SolidWorks 安装信息快照。"""

    installed: bool = False
    version: Optional[str] = None
    version_year: Optional[int] = None
    install_dir: Optional[Path] = None
    sldmat_paths: list[Path] = field(default_factory=list)
    textures_dir: Optional[Path] = None
    p2m_dir: Optional[Path] = None
    toolbox_dir: Optional[Path] = None
    com_available: bool = False
    pywin32_available: bool = False


# ─── 进程级缓存 ──────────────────────────────────────────────────────────

_cached_info: Optional[SwInfo] = None


def detect_solidworks() -> SwInfo:
    """检测 SolidWorks 安装。结果缓存，进程内只执行一次。"""
    global _cached_info
    if _cached_info is not None:
        return _cached_info
    _cached_info = _detect_impl()
    return _cached_info


def _reset_cache() -> None:
    """测试用：清除缓存，下次调用 detect_solidworks() 重新检测。"""
    global _cached_info
    _cached_info = None


# ─── 内部检测实现 ─────────────────────────────────────────────────────────

_MIN_YEAR = 2020
_MAX_YEAR = 2030


def _detect_impl() -> SwInfo:
    """实际检测逻辑。"""
    if sys.platform != "win32":
        return SwInfo(installed=False)

    # 1. 注册表查 SW 安装目录
    install_dir, version_year = _find_install_from_registry()
    if install_dir is None:
        return SwInfo(installed=False)

    version_str = str(version_year) if version_year else None

    # 2. 注册表查 Toolbox 路径
    toolbox_dir = _find_toolbox_from_registry(version_year)

    # 3. 从 install_dir 派生资产路径
    sldmat_paths = _find_sldmat_files(install_dir)
    textures_dir = _check_subdir(install_dir, "data", "Images", "textures")
    p2m_dir = _check_subdir(install_dir, "data", "graphics", "Materials")

    # 4. COM 检测
    com_available = _check_com_registered()

    # 5. pywin32 检测
    pywin32_available = _check_pywin32()

    return SwInfo(
        installed=True,
        version=version_str,
        version_year=version_year,
        install_dir=install_dir,
        sldmat_paths=sldmat_paths,
        textures_dir=textures_dir,
        p2m_dir=p2m_dir,
        toolbox_dir=toolbox_dir,
        com_available=com_available,
        pywin32_available=pywin32_available,
    )


def _find_install_from_registry() -> tuple[Optional[Path], Optional[int]]:
    """从注册表双路查询 SW 安装目录。返回 (install_dir, year)。"""
    try:
        import winreg
    except ImportError:
        return None, None

    # 两种注册表 key 格式（大小写不同，都需要查）
    key_patterns = [
        r"SOFTWARE\SolidWorks\SolidWorks {year}\Setup",
        r"SOFTWARE\SolidWorks\SOLIDWORKS {year}\Setup",
    ]

    for year in range(_MAX_YEAR, _MIN_YEAR - 1, -1):
        for pattern in key_patterns:
            key_path = pattern.format(year=year)
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    folder, _ = winreg.QueryValueEx(key, "SolidWorks Folder")
                    p = Path(folder)
                    if p.is_dir():
                        return p, year
            except OSError:
                continue
    return None, None


def _find_toolbox_from_registry(version_year: Optional[int]) -> Optional[Path]:
    """从注册表读取 Toolbox Data Location。"""
    if version_year is None:
        return None
    try:
        import winreg
    except ImportError:
        return None

    key_patterns = [
        r"SOFTWARE\SolidWorks\SolidWorks {year}\General",
        r"SOFTWARE\SolidWorks\SOLIDWORKS {year}\General",
    ]
    for pattern in key_patterns:
        key_path = pattern.format(year=version_year)
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                location, _ = winreg.QueryValueEx(key, "Toolbox Data Location")
                browser_dir = Path(location) / "browser"
                if browser_dir.is_dir():
                    return browser_dir
        except OSError:
            continue
    return None


def _find_sldmat_files(install_dir: Path) -> list[Path]:
    """搜索 install_dir/lang/*/sldmaterials/*.sldmat（所有语言目录）。"""
    lang_dir = install_dir / "lang"
    if not lang_dir.is_dir():
        return []
    results = []
    for lang_sub in lang_dir.iterdir():
        mat_dir = lang_sub / "sldmaterials"
        if mat_dir.is_dir():
            results.extend(sorted(mat_dir.glob("*.sldmat")))
    return results


def _check_subdir(base: Path, *parts: str) -> Optional[Path]:
    """检查 base/parts... 是否存在。存在返回 Path，否则 None。"""
    p = base.joinpath(*parts)
    return p if p.is_dir() else None


def _check_com_registered() -> bool:
    """检查 SldWorks.Application COM CLSID 是否已注册。"""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application\CLSID"
        ):
            return True
    except (ImportError, OSError):
        return False


def _check_pywin32() -> bool:
    """检查 pywin32 是否可导入。"""
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_sw_detect.py -v`
Expected: 2 PASSED

- [ ] **Step 6: 补充 mock 注册表测试场景**

在 `tests/test_sw_detect.py` 末尾追加：

```python
def test_detect_caches_result():
    """detect_solidworks() 第二次调用返回缓存。"""
    from adapters.solidworks import sw_detect
    sw_detect._reset_cache()
    info1 = sw_detect.detect_solidworks()
    info2 = sw_detect.detect_solidworks()
    assert info1 is info2  # 同一对象
    sw_detect._reset_cache()


def test_reset_cache_clears():
    """_reset_cache() 后下次调用重新检测。"""
    from adapters.solidworks import sw_detect
    sw_detect._reset_cache()
    info1 = sw_detect.detect_solidworks()
    sw_detect._reset_cache()
    info2 = sw_detect.detect_solidworks()
    # 不要求同一对象，但字段值应相同
    assert info1.installed == info2.installed
    sw_detect._reset_cache()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_detect_on_current_machine():
    """在当前机器上跑真实检测（仅 Windows CI/开发机）。"""
    from adapters.solidworks import sw_detect
    sw_detect._reset_cache()
    info = sw_detect.detect_solidworks()
    # 不断言是否安装——只检查结构正确
    assert isinstance(info.installed, bool)
    assert isinstance(info.sldmat_paths, list)
    assert isinstance(info.com_available, bool)
    assert isinstance(info.pywin32_available, bool)
    if info.installed:
        assert info.install_dir is not None
        assert info.install_dir.is_dir()
        assert info.version_year is not None
        assert info.version_year >= 2020
    sw_detect._reset_cache()
```

- [ ] **Step 7: 运行全部 sw_detect 测试**

Run: `uv run pytest tests/test_sw_detect.py -v`
Expected: 4 PASSED (或 3 PASSED + 1 SKIPPED on non-Windows)

- [ ] **Step 8: 提交**

```bash
git add adapters/solidworks/__init__.py adapters/solidworks/sw_detect.py tests/test_sw_detect.py
git commit -m "feat(sw): sw_detect.py — SwInfo 数据类 + 注册表动态检测"
```

---

### Task 2: sldmat fixture 生成器 + `parse_sldmat()`

**Files:**
- Create: `tests/fixtures/generate_sldmat_fixture.py`
- Create: `adapters/solidworks/sw_material_bridge.py` (部分)
- Create: `tests/test_sw_material_bridge.py`

- [ ] **Step 1: 创建 sldmat fixture 生成器**

```python
# tests/fixtures/generate_sldmat_fixture.py
"""生成测试用最小化 sldmat 文件。不含任何 SolidWorks 原始数据。"""

import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://www.solidworks.com/sldmaterials"


def generate_minimal_sldmat(out_path: Path) -> None:
    """构造一个含 2 种材质的最小 sldmat（UTF-16 LE + BOM）。"""
    root = ET.Element(f"{{{NS}}}materials", attrib={
        "version": "2008.03",
    })

    # classification: Steel
    steel = ET.SubElement(root, "classification", name="Steel")
    mat1 = ET.SubElement(steel, "material", name="Test Carbon Steel 1000", matid="1")
    props1 = ET.SubElement(mat1, "physicalproperties")
    ET.SubElement(props1, "DENS", displayname="Mass density", value="7850.0")
    ET.SubElement(props1, "KX", displayname="Thermal conductivity", value="50.0")
    ET.SubElement(props1, "SIGXT", displayname="Tensile strength", value="420000000")
    shaders1 = ET.SubElement(mat1, "shaders")
    ET.SubElement(shaders1, "pwshader2",
                  path=r"\metal\steel\matte steel.p2m", name="matte steel")

    # classification: Aluminum Alloys
    al = ET.SubElement(root, "classification", name="Aluminum Alloys")
    mat2 = ET.SubElement(al, "material", name="Test 6061 Alloy", matid="2")
    props2 = ET.SubElement(mat2, "physicalproperties")
    ET.SubElement(props2, "DENS", displayname="Mass density", value="2700.0")
    ET.SubElement(props2, "KX", displayname="Thermal conductivity", value="167.0")
    shaders2 = ET.SubElement(mat2, "shaders")
    ET.SubElement(shaders2, "pwshader2",
                  path=r"\metal\aluminum\polished aluminum.p2m",
                  name="polished aluminum")

    tree = ET.ElementTree(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(b"\xff\xfe")  # UTF-16 LE BOM
        tree.write(f, encoding="utf-16-le", xml_declaration=False)


if __name__ == "__main__":
    out = Path(__file__).parent / "test_materials.sldmat"
    generate_minimal_sldmat(out)
    print(f"Generated: {out}")
```

- [ ] **Step 2: 写 `parse_sldmat` 的测试**

```python
# tests/test_sw_material_bridge.py
"""sw_material_bridge 单元测试。使用生成的 fixture。"""

import pytest
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_SLDMAT = FIXTURE_DIR / "test_materials.sldmat"


@pytest.fixture(autouse=True, scope="module")
def _generate_fixture():
    """测试前生成 fixture 文件。"""
    from tests.fixtures.generate_sldmat_fixture import generate_minimal_sldmat
    generate_minimal_sldmat(FIXTURE_SLDMAT)
    yield
    # 不删除——便于调试


def test_parse_sldmat_returns_list():
    """parse_sldmat 返回 SwMaterial 列表。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat
    materials = parse_sldmat(FIXTURE_SLDMAT)
    assert isinstance(materials, list)
    assert len(materials) == 2


def test_parse_sldmat_steel_fields():
    """Steel 材质字段正确解析。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat
    materials = parse_sldmat(FIXTURE_SLDMAT)
    steel = [m for m in materials if "Carbon Steel" in m.name][0]
    assert steel.classification == "Steel"
    assert abs(steel.density_kg_m3 - 7850.0) < 0.1
    assert steel.shader_path == r"\metal\steel\matte steel.p2m"


def test_parse_sldmat_aluminum_fields():
    """Aluminum 材质字段正确解析。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat
    materials = parse_sldmat(FIXTURE_SLDMAT)
    al = [m for m in materials if "6061" in m.name][0]
    assert al.classification == "Aluminum Alloys"
    assert abs(al.density_kg_m3 - 2700.0) < 0.1


def test_parse_nonexistent_file_returns_empty():
    """不存在的文件返回空列表。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat
    result = parse_sldmat(Path("/nonexistent/fake.sldmat"))
    assert result == []
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/test_sw_material_bridge.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 4: 实现 `SwMaterial` 和 `parse_sldmat()`**

```python
# adapters/solidworks/sw_material_bridge.py
"""SolidWorks 材质桥接 — 解析 sldmat XML，生成关键词路由扩展。

sldmat 文件是 UTF-16 LE XML，带 BOM。每个文件包含多个 classification，
每个 classification 下有多个 material，每个 material 有物理属性和 shader 引用。
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
    "load_sw_material_bundle",
    "reset_all_sw_caches",
]


# ─── 数据类 ───────────────────────────────────────────────────────────────

@dataclass
class SwMaterial:
    """从 sldmat XML 解析出的单个材质条目。"""

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
    preset_keywords: 合并进 _MAT_PRESET（preset 关键词路由）
    """

    type_keywords: dict[str, list[str]] = field(default_factory=dict)
    preset_keywords: dict[str, str] = field(default_factory=dict)


# ─── sldmat XML 解析 ─────────────────────────────────────────────────────

# sldmat 使用 namespace，但版本间 namespace URI 可能不同。
# 用 iterparse 时 tag 带 namespace 前缀；简单起见用 local name 匹配。

def _local_tag(elem: ET.Element) -> str:
    """去掉 namespace，返回 local tag name。"""
    tag = elem.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_sldmat(path: Path) -> list[SwMaterial]:
    """解析单个 sldmat 文件，返回 SwMaterial 列表。

    文件不存在或解析失败返回空列表（warning log，不 raise）。
    """
    if not path.is_file():
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

            # 解析物理属性
            for child in mat_elem:
                if _local_tag(child) == "physicalproperties":
                    _parse_physical_props(child, mat)
                elif _local_tag(child) == "shaders":
                    _parse_shaders(child, mat)

            results.append(mat)

    return results


def _parse_physical_props(props_elem: ET.Element, mat: SwMaterial) -> None:
    """从 <physicalproperties> 提取物理属性到 SwMaterial。"""
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
    """从 <shaders> 提取 p2m 路径。"""
    for shader in shaders_elem:
        if _local_tag(shader) == "pwshader2":
            mat.shader_path = shader.get("path")
            break
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_sw_material_bridge.py -v`
Expected: 4 PASSED

- [ ] **Step 6: 提交**

```bash
git add tests/fixtures/generate_sldmat_fixture.py adapters/solidworks/sw_material_bridge.py tests/test_sw_material_bridge.py
git commit -m "feat(sw): parse_sldmat — sldmat UTF-16 XML 解析 + fixture 生成器"
```

---

### Task 3: `SwMaterialBundle` 构建 + `load_sw_material_bundle()`

**Files:**
- Modify: `adapters/solidworks/sw_material_bridge.py`
- Modify: `tests/test_sw_material_bridge.py`

- [ ] **Step 1: 写 bundle 构建的测试**

在 `tests/test_sw_material_bridge.py` 末尾追加：

```python
def test_build_bundle_type_keywords():
    """bundle.type_keywords 包含 SW classification 到 material_type 的关键词。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat, build_bundle
    materials = parse_sldmat(FIXTURE_SLDMAT)
    bundle = build_bundle(materials)
    # "Steel" classification → "steel" type 的关键词应包含 "Carbon Steel"
    assert "steel" in bundle.type_keywords
    assert any("Carbon Steel" in kw for kw in bundle.type_keywords["steel"])
    # "Aluminum Alloys" → "al"
    assert "al" in bundle.type_keywords
    assert any("6061" in kw for kw in bundle.type_keywords["al"])


def test_build_bundle_preset_keywords():
    """bundle.preset_keywords 将材质名映射到已有 preset key。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat, build_bundle
    materials = parse_sldmat(FIXTURE_SLDMAT)
    bundle = build_bundle(materials)
    # Steel 材质 → "dark_steel" preset
    steel_presets = [v for k, v in bundle.preset_keywords.items()
                     if "Carbon Steel" in k]
    assert steel_presets and steel_presets[0] == "dark_steel"
    # Aluminum 材质 → "brushed_aluminum" preset
    al_presets = [v for k, v in bundle.preset_keywords.items()
                  if "6061" in k]
    assert al_presets and al_presets[0] == "brushed_aluminum"


def test_build_bundle_preset_values_in_allowed_set():
    """bundle.preset_keywords 的所有值必须属于已有 MATERIAL_PRESETS key 集合。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat, build_bundle
    from render_config import MATERIAL_PRESETS
    materials = parse_sldmat(FIXTURE_SLDMAT)
    bundle = build_bundle(materials)
    for preset_key in bundle.preset_keywords.values():
        assert preset_key in MATERIAL_PRESETS, (
            f"preset_keywords 值 '{preset_key}' 不在 MATERIAL_PRESETS 中"
        )


def test_load_sw_material_bundle_non_windows(monkeypatch):
    """非 Windows 平台返回 None。"""
    monkeypatch.setattr(sys, "platform", "linux")
    from adapters.solidworks import sw_material_bridge
    sw_material_bridge._cached_bundle = None  # 清缓存
    result = sw_material_bridge.load_sw_material_bundle()
    assert result is None
    monkeypatch.setattr(sys, "platform", "win32")
    sw_material_bridge._cached_bundle = None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_sw_material_bridge.py::test_build_bundle_type_keywords -v`
Expected: FAIL — `ImportError: cannot import name 'build_bundle'`

- [ ] **Step 3: 在 `sw_material_bridge.py` 中实现 `build_bundle()` 和 `load_sw_material_bundle()`**

在文件末尾追加：

```python
# ─── classification → material_type / preset 映射 ────────────────────────

# SW classification 名 → 管道 material_type 码
_SW_CLASSIFICATION_TO_TYPE = {
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
SW_CLASSIFICATION_TO_PRESET = {
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

# SW 材质名 → 现有 MATERIAL_PROPS key（已有等价物的不重复注入）
EQUIVALENCE_MAP = {
    "AISI 304":                "SUS304",
    "304 Stainless Steel":     "SUS304",
    "201 Annealed Stainless Steel": "SUS304",
    "316L Stainless Steel":    "SUS316L",
    "7075 Alloy":              "7075-T6",
    "6061 Alloy":              "6061-T6",
    "6063 Alloy":              "6063",
}


def build_bundle(materials: list[SwMaterial]) -> SwMaterialBundle:
    """从 SwMaterial 列表构建路由扩展 bundle。"""
    type_kw: dict[str, list[str]] = {}
    preset_kw: dict[str, str] = {}

    for mat in materials:
        # 跳过等价映射中的材质（已有 MATERIAL_PROPS key 覆盖）
        # 但仍贡献 type_keywords 路由
        cls = mat.classification
        mtype = _SW_CLASSIFICATION_TO_TYPE.get(cls)
        preset = SW_CLASSIFICATION_TO_PRESET.get(cls)

        if mtype:
            type_kw.setdefault(mtype, []).append(mat.name)

        if preset and mat.name not in EQUIVALENCE_MAP:
            preset_kw[mat.name] = preset

    return SwMaterialBundle(type_keywords=type_kw, preset_keywords=preset_kw)


# ─── 一键加载入口 ─────────────────────────────────────────────────────────

_cached_bundle: Optional[SwMaterialBundle] = None
_BUNDLE_LOADED = False  # 区分 None（未加载）和 None（加载后 SW 不可用）


def load_sw_material_bundle() -> Optional[SwMaterialBundle]:
    """一键加载 SW 材质路由扩展。

    内部使用 _cached_bundle 缓存结果，多次调用只解析一次 sldmat。
    get_material_type_keywords() 和 get_material_preset_keywords()
    都调用此函数，但不会触发重复 I/O。

    SW 未安装或版本不足时返回 None。
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
        parsed = parse_sldmat(sldmat_path)
        all_materials.extend(parsed)
        if parsed:
            log.info("解析 %s: %d 种材质", sldmat_path.name, len(parsed))

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
    """测试用统一入口：重置 bundle 缓存 + 所有下游合并缓存。"""
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_sw_material_bridge.py -v`
Expected: 8 PASSED

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_material_bridge.py tests/test_sw_material_bridge.py
git commit -m "feat(sw): SwMaterialBundle 构建 + load_sw_material_bundle 一键加载"
```

---

### Task 4: `cad_spec_defaults.py` — `get_material_type_keywords()` 函数化

**Files:**
- Modify: `cad_spec_defaults.py` (L452-466)
- Create: `tests/test_sw_routing_integration.py`

- [ ] **Step 1: 写路由函数化的测试**

```python
# tests/test_sw_routing_integration.py
"""SW 路由函数化集成测试。验证无 SW 时字节等同。"""

import sys
import pytest


def test_get_material_type_keywords_without_sw_equals_base():
    """无 SW 时 get_material_type_keywords() 返回值 == MATERIAL_TYPE_KEYWORDS。"""
    from cad_spec_defaults import (
        MATERIAL_TYPE_KEYWORDS,
        get_material_type_keywords,
        _reset_material_cache,
    )
    _reset_material_cache()
    result = get_material_type_keywords()
    # 值内容相同
    assert result.keys() == MATERIAL_TYPE_KEYWORDS.keys()
    for key in MATERIAL_TYPE_KEYWORDS:
        assert sorted(result[key]) == sorted(MATERIAL_TYPE_KEYWORDS[key])
    _reset_material_cache()


def test_classify_material_type_unchanged():
    """classify_material_type 行为不受函数化影响。"""
    from cad_spec_defaults import classify_material_type, _reset_material_cache
    _reset_material_cache()
    assert classify_material_type("7075-T6铝合金") == "al"
    assert classify_material_type("SUS304不锈钢") == "steel"
    assert classify_material_type("PEEK") == "peek"
    assert classify_material_type("FKM橡胶") == "rubber"
    assert classify_material_type("PA66") == "nylon"
    assert classify_material_type("unknown stuff") is None
    _reset_material_cache()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_sw_routing_integration.py::test_get_material_type_keywords_without_sw_equals_base -v`
Expected: FAIL — `ImportError: cannot import name 'get_material_type_keywords'`

- [ ] **Step 3: 修改 `cad_spec_defaults.py`**

在 `MATERIAL_TYPE_KEYWORDS` 定义之后、`classify_material_type()` 定义之前，插入 `get_material_type_keywords()` 函数。然后修改 `classify_material_type()` 改为调用该函数。

在 `cad_spec_defaults.py` 的 `MATERIAL_TYPE_KEYWORDS` 定义 (L449) 后追加：

```python
# ─── SW 可选扩展的延迟加载 ────────────────────────────────────────────────

_merged_keywords = None


def get_material_type_keywords():
    """返回基础 + SW 扩展的关键词路由表。

    首次调用时尝试合并 SW sldmat 提取的关键词。结果缓存。
    无 SW 时返回值与 MATERIAL_TYPE_KEYWORDS 内容一致。
    """
    global _merged_keywords
    if _merged_keywords is not None:
        return _merged_keywords
    # 深拷贝基础层
    _merged_keywords = {k: list(v) for k, v in MATERIAL_TYPE_KEYWORDS.items()}
    if sys.platform == "win32":
        try:
            from adapters.solidworks.sw_material_bridge import (
                load_sw_material_bundle,
            )
            bundle = load_sw_material_bundle()
            if bundle:
                for mtype, kws in bundle.type_keywords.items():
                    if mtype in _merged_keywords:
                        existing = {kw.lower() for kw in _merged_keywords[mtype]}
                        for kw in kws:
                            if kw.lower() not in existing:
                                _merged_keywords[mtype].append(kw)
                    else:
                        _merged_keywords[mtype] = list(kws)
        except ImportError:
            pass
    return _merged_keywords


def _reset_material_cache():
    """测试用：重置缓存。"""
    global _merged_keywords
    _merged_keywords = None
```

然后将 `classify_material_type()` 从引用 `MATERIAL_TYPE_KEYWORDS` 改为引用 `get_material_type_keywords()`：

```python
def classify_material_type(material: str):
    """从 BOM material 字段推断 material_type。

    遍历 get_material_type_keywords() 查找关键词匹配。
    无匹配时返回 None。
    """
    if not material:
        return None
    for mtype, keywords in get_material_type_keywords().items():
        if any(kw.lower() in material.lower() for kw in keywords):
            return mtype
    return None
```

需要在文件顶部确保 `import sys` 存在（如果尚未导入）。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_sw_routing_integration.py -v`
Expected: 2 PASSED

- [ ] **Step 5: 运行现有测试确认无退化**

Run: `uv run pytest tests/ -v --timeout=60 -x`
Expected: 全部 PASSED（`classify_material_type` 行为不变）

- [ ] **Step 6: 提交**

```bash
git add cad_spec_defaults.py tests/test_sw_routing_integration.py
git commit -m "refactor(defaults): classify_material_type 改用 get_material_type_keywords() 延迟加载"
```

---

### Task 5: `cad_pipeline.py` — `get_material_preset_keywords()` 函数化

**Files:**
- Modify: `cad_pipeline.py` (L461-468, L502, L529, L586)
- Modify: `tests/test_sw_routing_integration.py`

- [ ] **Step 1: 写 preset 路由函数化的测试**

在 `tests/test_sw_routing_integration.py` 末尾追加：

```python
def test_get_material_preset_keywords_without_sw_equals_base():
    """无 SW 时 get_material_preset_keywords() 返回值 == _MAT_PRESET 原值。"""
    from cad_pipeline import (
        _MAT_PRESET,
        get_material_preset_keywords,
        _reset_preset_keywords_cache,
    )
    _reset_preset_keywords_cache()
    result = get_material_preset_keywords()
    assert result == _MAT_PRESET
    _reset_preset_keywords_cache()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_sw_routing_integration.py::test_get_material_preset_keywords_without_sw_equals_base -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 修改 `cad_pipeline.py`**

1. 将 `_MAT_PRESET` 从 `_sync_bom_to_render_config()` 函数体内（L461-468）**提到模块级**（在函数定义之前）。

2. 在 `_MAT_PRESET` 之后定义 `get_material_preset_keywords()` 和 `_reset_preset_keywords_cache()`：

```python
# ─── 材质 preset 关键词路由 ──────────────────────────────────────────────

_MAT_PRESET = {
    "铝": "brushed_aluminum", "Al": "brushed_aluminum",
    "钢": "stainless_304", "SUS": "stainless_304",
    "PEEK": "peek_amber",
    "橡胶": "black_rubber", "硅橡胶": "black_rubber",
    "塑料": "white_nylon", "尼龙": "white_nylon",
    "铜": "copper",
}

_preset_keywords_merged = None


def get_material_preset_keywords():
    """返回基础 + SW 扩展的 preset 关键词路由。

    首次调用时尝试合并 SW sldmat 提取的 preset 关键词。结果缓存。
    无 SW 时返回值与 _MAT_PRESET 内容一致。
    """
    global _preset_keywords_merged
    if _preset_keywords_merged is not None:
        return _preset_keywords_merged
    _preset_keywords_merged = dict(_MAT_PRESET)
    if sys.platform == "win32":
        try:
            from adapters.solidworks.sw_material_bridge import (
                load_sw_material_bundle,
            )
            bundle = load_sw_material_bundle()
            if bundle:
                for k, v in bundle.preset_keywords.items():
                    if k not in _preset_keywords_merged:
                        _preset_keywords_merged[k] = v
        except ImportError:
            pass
    return _preset_keywords_merged


def _reset_preset_keywords_cache():
    """测试用：重置缓存。"""
    global _preset_keywords_merged
    _preset_keywords_merged = None
```

3. 在 `_sync_bom_to_render_config()` 函数体内，删除原来的 `_MAT_PRESET = {...}` 块，将 3 处 `_MAT_PRESET.items()` 改为 `get_material_preset_keywords().items()`：

   - L502: `for keyword, p_name in get_material_preset_keywords().items():`
   - L529: `for keyword, p_name in get_material_preset_keywords().items():`
   - L586: `for keyword, p_name in get_material_preset_keywords().items():`

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_sw_routing_integration.py -v`
Expected: 3 PASSED

- [ ] **Step 5: 运行现有测试确认无退化**

Run: `uv run pytest tests/ -v --timeout=60 -x`
Expected: 全部 PASSED

- [ ] **Step 6: 提交**

```bash
git add cad_pipeline.py tests/test_sw_routing_integration.py
git commit -m "refactor(pipeline): _MAT_PRESET 提为模块级 + get_material_preset_keywords() 延迟加载"
```

---

### Task 6: env-check `enhancements` 增强

**Files:**
- Modify: `tools/hybrid_render/check_env.py` (L156 后, L215 后)
- Modify: `tests/test_sw_routing_integration.py`

- [ ] **Step 1: 写 env-check 增强的测试**

在 `tests/test_sw_routing_integration.py` 末尾追加：

```python
def test_env_check_has_enhancements_key():
    """detect_environment() 返回值包含 enhancements 字段。"""
    sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "hybrid_render"))
    try:
        import check_env
        import importlib
        importlib.reload(check_env)
        result = check_env.detect_environment()
        assert "enhancements" in result
        assert "solidworks" in result["enhancements"]
        sw = result["enhancements"]["solidworks"]
        assert "ok" in sw
        assert isinstance(sw["ok"], bool)
    finally:
        sys.path.pop(0)


def test_env_check_level_unchanged_by_sw():
    """SW 有无不影响 level 计算。"""
    sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "hybrid_render"))
    try:
        import check_env
        import importlib
        importlib.reload(check_env)
        result = check_env.detect_environment()
        # level 应该只取决于 cq/ez/bl/gm/mp，不取决于 SW
        assert 1 <= result["level"] <= 5
    finally:
        sys.path.pop(0)
```

文件头追加 `from pathlib import Path`。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_sw_routing_integration.py::test_env_check_has_enhancements_key -v`
Expected: FAIL — `KeyError: 'enhancements'`

- [ ] **Step 3: 修改 `check_env.py`**

在 `detect_environment()` 函数中，`result["level"] = level` 之前（L156），插入：

```python
    # ─── 增强源检测（不影响 level） ───
    enhancements = {}
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        sw = detect_solidworks()
        enhancements["solidworks"] = {
            "ok": sw.installed and (sw.version_year or 0) >= 2020,
            "version": sw.version,
            "path_a": (sw.version_year or 0) >= 2020,
            "path_b": (sw.version_year or 0) >= 2024 and sw.com_available,
            "pywin32": sw.pywin32_available,
            "materials": len(sw.sldmat_paths),
        }
    except ImportError:
        enhancements["solidworks"] = {"ok": False}
    result["enhancements"] = enhancements
```

在 `print_report()` 函数中，`# Next steps` 之前（L241），插入增强源报告段：

```python
    # Enhancement sources
    enhancements = result.get("enhancements", {})
    sw_enh = enhancements.get("solidworks", {})
    print()
    print("  增强源（可选，不影响能力等级）")
    print("  " + "-" * 56)
    if sw_enh.get("ok"):
        sw_ver = sw_enh.get("version", "?")
        path_a = "✓" if sw_enh.get("path_a") else "✗"
        path_b_parts = []
        if sw_enh.get("path_b"):
            path_b_parts.append("✓")
        else:
            path_b_parts.append("✗")
        if not sw_enh.get("pywin32") and sw_enh.get("path_b") is False:
            path_b_parts.append("(pywin32 未安装)")
        path_b = " ".join(path_b_parts)
        print(f"  SolidWorks    [OK]    {sw_ver}"
              f" — 材质 {path_a} / Toolbox {path_b}")
    else:
        print("  SolidWorks    [  ]    未检测到安装")
        print("                        已有 SolidWorks 许可？"
              "安装后可自动集成材质库和标准件。")
    print("  " + "-" * 56)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_sw_routing_integration.py -v`
Expected: 5 PASSED

- [ ] **Step 5: 提交**

```bash
git add tools/hybrid_render/check_env.py tests/test_sw_routing_integration.py
git commit -m "feat(env-check): enhancements 增强源报告 — SolidWorks 检测状态"
```

---

### Task 7: 统一缓存重置 + `reset_all_sw_caches()` 完善

**Files:**
- Modify: `adapters/solidworks/sw_material_bridge.py` (reset_all_sw_caches)
- Modify: `tests/test_sw_routing_integration.py`

- [ ] **Step 1: 写统一重置的测试**

在 `tests/test_sw_routing_integration.py` 末尾追加：

```python
def test_reset_all_sw_caches_clears_everything():
    """reset_all_sw_caches() 重置所有缓存。"""
    from adapters.solidworks.sw_material_bridge import reset_all_sw_caches
    from cad_spec_defaults import get_material_type_keywords, _reset_material_cache

    # 先触发缓存
    get_material_type_keywords()

    # 重置
    reset_all_sw_caches()

    # 验证 cad_spec_defaults 缓存已清
    from cad_spec_defaults import _merged_keywords
    assert _merged_keywords is None
```

- [ ] **Step 2: 运行测试确认通过**

`reset_all_sw_caches()` 已在 Task 3 中实现，这里只是验证它能正确清除下游缓存。

Run: `uv run pytest tests/test_sw_routing_integration.py::test_reset_all_sw_caches_clears_everything -v`
Expected: PASS

- [ ] **Step 3: 补充 `cad_pipeline` 缓存到 `reset_all_sw_caches()`**

在 `adapters/solidworks/sw_material_bridge.py` 的 `reset_all_sw_caches()` 末尾追加：

```python
    try:
        from cad_pipeline import _reset_preset_keywords_cache
        _reset_preset_keywords_cache()
    except ImportError:
        pass
```

- [ ] **Step 4: 运行全部测试**

Run: `uv run pytest tests/test_sw_detect.py tests/test_sw_material_bridge.py tests/test_sw_routing_integration.py -v`
Expected: 全部 PASSED

- [ ] **Step 5: 运行完整测试套件确认无退化**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: 全部 PASSED，无新增失败

- [ ] **Step 6: 提交**

```bash
git add adapters/solidworks/sw_material_bridge.py tests/test_sw_routing_integration.py
git commit -m "feat(sw): reset_all_sw_caches 统一缓存重置 + 集成测试"
```

---

## 自审检查

### Spec 覆盖

| Spec 章节 | 对应 Task |
|-----------|----------|
| §4.1 sw_detect | Task 1 |
| §4.2 sw_material_bridge | Task 2 + 3 |
| §4.3 函数化改造 | Task 4 + 5 |
| §4.4 env-check 增强 | Task 6 |
| §5.4 无 SW 字节等同 | Task 4 Step 5, Task 5 Step 5 |
| §6 降级策略 | Task 1 (非 Windows 短路), Task 2 (文件不存在返回空), Task 3 (版本不足返回 None) |
| §7 测试策略 | Task 1-7 全覆盖 |
| reset_all_sw_caches | Task 7 |

### 不在 SW-A 范围内（留给 SW-B/SW-C）

- `sw_toolbox_catalog.py` — SW-B
- `sw_toolbox_adapter.py` — SW-B
- `SwComSession` — SW-B
- `parts_resolver.py` 注册 — SW-B
- `parts_library.default.yaml` 规则 — SW-B
- `sw-warmup` 命令 — SW-B
- p2m 解析 — SW-C
- `keywords_cn` 中文对照映射 — SW-C
