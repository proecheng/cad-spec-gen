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
