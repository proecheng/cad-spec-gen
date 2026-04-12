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
