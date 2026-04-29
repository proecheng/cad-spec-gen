# tests/test_jinja_generators_new.py
"""jinja_primitive 新增 locating/elastic/transmission 生成器端到端测试。

PartQuery 是 parts_resolver.py 里的 @dataclass，字段：
  part_no, name_cn, material, category, make_buy,
  spec_envelope=None, spec_envelope_granularity="part_envelope", project_root=""
"""
from __future__ import annotations

import pytest
from parts_resolver import PartQuery
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter


def _q(category: str, name: str = "test", material: str = "") -> PartQuery:
    """快捷构造一个最小化 PartQuery。"""
    return PartQuery(
        part_no="TEST-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.fixture(scope="module")
def adapter() -> JinjaPrimitiveAdapter:
    return JinjaPrimitiveAdapter()


# ── can_resolve ──────────────────────────────────────────────────────────────

def test_can_resolve_locating(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("locating")) is True


def test_can_resolve_elastic(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("elastic")) is True


def test_can_resolve_transmission(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("transmission")) is True


# ── resolve → hit ────────────────────────────────────────────────────────────

def test_resolve_locating_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("locating"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


def test_resolve_elastic_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("elastic"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


def test_resolve_transmission_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("transmission"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


# ── probe_dims 返回有效 (w, d, h) tuple ──────────────────────────────────────

def test_probe_dims_locating(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("locating"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


def test_probe_dims_elastic(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("elastic"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


def test_probe_dims_transmission(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("transmission"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


# ── transmission envelope 正确反映齿轮厚度 w ─────────────────────────────────

def test_transmission_envelope_uses_w(adapter: JinjaPrimitiveAdapter) -> None:
    """默认 dims {"od":30,"w":8,"id":6} → probe_dims 应返回 (30, 30, 8)。

    修复前 _dims_to_envelope 不检查 "w"，返回 (30, 30, 5)。
    """
    dims = adapter.probe_dims(_q("transmission"), {})
    assert dims == (30, 30, 8)


# ── locating: dims 从 material text 提取 ─────────────────────────────────────

def test_locating_dims_from_material_text(adapter: JinjaPrimitiveAdapter) -> None:
    """material='Φ5×16mm' 经 _parse_dims_from_text 提取为 d=5, l=16。

    _gen_locating 接收 d=5 → circle(2.5)，验证字符串包含正确半径。
    """
    result = adapter.resolve(_q("locating", name="定位销", material="Φ5×16mm"), {})
    assert result.status == "hit"
    assert "circle(2.5)" in result.body_code


# ── P1 electrical / connector semi-parametric templates ─────────────────────

@pytest.mark.parametrize(
    ("category", "name", "material", "template_id", "body_marker"),
    [
        ("connector", "ZIF连接器", "Molex 5052xx", "zif_connector", "ZIF connector"),
        ("connector", "FFC线束总成", "Molex 15168, 20芯×500mm", "ffc_ribbon", "FFC ribbon"),
        ("other", "信号调理PCB", "定制4层混合信号", "pcb_board", "PCB assembly"),
        ("connector", "SMA穿壁连接器", "50Ω", "sma_bulkhead", "SMA bulkhead"),
        ("other", "M12防水诊断接口", "4芯", "m12_connector", "M12 connector"),
        ("sensor", "I300-UHF-GT传感器", "波译科技", "uhf_sensor", "UHF sensor"),
        ("other", "压力阵列", "4×4薄膜 20×20mm", "pressure_array", "pressure array"),
    ],
)
def test_p1_electrical_parts_use_specialized_templates(
    adapter: JinjaPrimitiveAdapter,
    category: str,
    name: str,
    material: str,
    template_id: str,
    body_marker: str,
) -> None:
    result = adapter.resolve(_q(category, name=name, material=material), {})

    assert result.status == "hit"
    assert result.kind == "codegen"
    assert result.geometry_source == "JINJA_TEMPLATE"
    assert result.geometry_quality == "C"
    assert result.requires_model_review is True
    assert result.metadata["template"] == template_id
    assert body_marker in result.body_code


def test_ffc_template_keeps_actual_length_metadata(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("connector", name="FFC线束总成", material="Molex 15168, 20芯×500mm"),
        {},
    )

    assert result.metadata["actual_length_mm"] == 500
    assert result.metadata["pins"] == 20
    assert result.real_dims[0] == 12
    assert result.real_dims[1] == 50
    assert result.real_dims[2] == 1


def test_non_sma_50_ohm_connector_does_not_use_sma_template(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("connector", name="BNC穿壁连接器", material="50Ω"),
        {},
    )

    assert result.metadata.get("template") != "sma_bulkhead"
    assert result.source_tag == "jinja_primitive:connector"


def test_generic_thin_film_part_does_not_use_pressure_array_template(
    adapter: JinjaPrimitiveAdapter,
) -> None:
    result = adapter.resolve(
        _q("other", name="绝缘薄膜垫片", material="20×20mm"),
        {},
    )

    assert result.metadata.get("template") != "pressure_array"
    assert result.source_tag == "jinja_primitive:other"
