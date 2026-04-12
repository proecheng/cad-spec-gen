"""sw_material_bridge 单元测试。使用生成的 fixture。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


# ─── Task 2: parse_sldmat 测试 ─────────────────────────────────────────────


def test_parse_sldmat_returns_list():
    """parse_sldmat 返回 SwMaterial 列表，长度 2。"""
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
    assert steel.thermal_conductivity == pytest.approx(50.0)
    assert steel.shader_path == r"\metal\steel\matte steel.p2m"


def test_parse_sldmat_aluminum_fields():
    """Aluminum 材质字段正确解析。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat
    materials = parse_sldmat(FIXTURE_SLDMAT)
    al = [m for m in materials if "6061" in m.name][0]
    assert al.classification == "Aluminum Alloys"
    assert abs(al.density_kg_m3 - 2700.0) < 0.1
    assert al.thermal_conductivity == pytest.approx(167.0)
    assert al.shader_path == r"\metal\aluminum\polished aluminum.p2m"


def test_parse_nonexistent_file_returns_empty():
    """不存在的文件返回空列表。"""
    from adapters.solidworks.sw_material_bridge import parse_sldmat
    result = parse_sldmat(Path("/nonexistent/fake.sldmat"))
    assert result == []


# ─── Task 3: build_bundle + load_sw_material_bundle 测试 ───────────────────


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
    from adapters.solidworks import sw_material_bridge
    # 清缓存
    sw_material_bridge._cached_bundle = None
    sw_material_bridge._BUNDLE_LOADED = False
    monkeypatch.setattr(sys, "platform", "linux")
    result = sw_material_bridge.load_sw_material_bundle()
    assert result is None
    # 还原
    sw_material_bridge._cached_bundle = None
    sw_material_bridge._BUNDLE_LOADED = False
