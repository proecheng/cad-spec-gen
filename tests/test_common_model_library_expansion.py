from __future__ import annotations

import pytest

from adapters.parts import vendor_synthesizer
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from codegen.gen_std_parts import generate_std_part_files
from parts_resolver import PartQuery, default_resolver


def _q(category: str, name: str, material: str = "") -> PartQuery:
    return PartQuery(
        part_no="GEN-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("LM12UU 直线轴承", "", "bearing"),
        ("NEMA17 步进电机", "", "motor"),
        ("M12 电感接近开关", "PNP NO", "sensor"),
        ("薄型气缸", "MGPM20-50", "pneumatic"),
        ("拖链线束", "4芯×1200mm", "cable"),
    ],
)
def test_common_purchased_part_names_classify_to_reusable_categories(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("category", "name", "material", "template", "dims"),
    [
        ("bearing", "LM12UU 直线轴承", "", "linear_bearing_lmxxuu", (21, 21, 30)),
        ("motor", "NEMA17 步进电机", "", "nema_stepper_motor", (42.3, 42.3, 72)),
        (
            "sensor",
            "M12 电感接近开关",
            "",
            "cylindrical_proximity_sensor",
            (12, 12, 55),
        ),
        (
            "pneumatic",
            "薄型气缸",
            "MGPM20-50",
            "compact_pneumatic_cylinder",
            (42, 34, 70),
        ),
        ("cable", "拖链线束", "4芯×1200mm", "cable_harness_stub", (10, 50, 6)),
    ],
)
def test_jinja_adapter_has_reusable_templates_for_common_categories(
    category: str,
    name: str,
    material: str,
    template: str,
    dims: tuple[float, float, float],
) -> None:
    result = JinjaPrimitiveAdapter().resolve(_q(category, name, material), {})

    assert result.status == "hit"
    assert result.geometry_source == "PARAMETRIC_TEMPLATE"
    assert result.geometry_quality == "B"
    assert result.requires_model_review is False
    assert result.metadata["template"] == template
    assert result.real_dims == dims


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("bearing", "LM12UU 直线轴承", ""),
        ("motor", "NEMA17 步进电机", ""),
        ("sensor", "M12 电感接近开关", ""),
        ("pneumatic", "薄型气缸", "MGPM20-50"),
        ("cable", "拖链线束", "4芯×1200mm"),
    ],
)
def test_common_reusable_template_geometry_stays_within_reported_real_dims(
    category: str,
    name: str,
    material: str,
) -> None:
    import cadquery as cq

    result = JinjaPrimitiveAdapter().resolve(_q(category, name, material), {})
    namespace = {"cq": cq}
    exec(f"def _make():\n{result.body_code}\n", namespace)
    shape = namespace["_make"]()
    bbox = shape.val().BoundingBox()

    assert result.real_dims is not None
    actual = (bbox.xlen, bbox.ylen, bbox.zlen)
    for measured, expected in zip(actual, result.real_dims):
        assert measured <= expected + 1e-6


@pytest.mark.parametrize(
    ("query", "expected_adapter"),
    [
        (_q("bearing", "LM12UU 直线轴承"), "jinja_primitive"),
        (_q("motor", "NEMA17 步进电机"), "jinja_primitive"),
        (_q("sensor", "M12 电感接近开关"), "jinja_primitive"),
        (_q("pneumatic", "薄型气缸", "MGPM20-50"), "jinja_primitive"),
        (_q("cable", "拖链线束", "4芯×1200mm"), "jinja_primitive"),
    ],
)
def test_default_library_routes_common_categories_without_project_part_numbers(
    query: PartQuery,
    expected_adapter: str,
) -> None:
    result = default_resolver(project_root="__missing_project__").resolve(query)

    assert result.status in {"hit", "fallback"}
    assert result.adapter == expected_adapter
    assert result.kind == "codegen"
    assert not result.requires_model_review


def test_default_library_synthesizer_registry_remains_in_lockstep() -> None:
    assert set(vendor_synthesizer.DEFAULT_STEP_FILES) == set(
        vendor_synthesizer.SYNTHESIZERS
    )


@pytest.mark.parametrize(
    ("query", "expected_match_category"),
    [
        (_q("motor", "NEMA17 步进电机"), "motor"),
        (_q("sensor", "M12 电感接近开关"), "sensor"),
        (_q("pneumatic", "薄型气缸", "MGPM20-50"), "pneumatic"),
        (_q("cable", "拖链线束", "4芯×1200mm"), "cable"),
    ],
)
def test_default_library_has_explicit_common_category_rules(
    query: PartQuery,
    expected_match_category: str,
) -> None:
    resolver = default_resolver(project_root="__missing_project__")

    rules = resolver.matching_rules(query, adapter_name="jinja_primitive")

    assert rules
    assert rules[0]["match"].get("category") == expected_match_category


def test_codegen_generates_common_cable_harness_instead_of_prefiltering(
    tmp_path,
) -> None:
    spec_path = tmp_path / "cad" / "demo" / "CAD_SPEC.md"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(
        """# CAD Spec - demo

## 5. BOM

| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |
| --- | --- | --- | --- | --- | --- |
| GEN-000 | 测试总成 | — | 1 | 总成 | — |
| GEN-C01 | 拖链线束 | 4芯×1200mm | 1 | 外购 | — |
""",
        encoding="utf-8",
    )

    generated, _skipped, _resolver, _pending = generate_std_part_files(
        str(spec_path),
        str(spec_path.parent),
        mode="force",
    )

    generated_names = {p.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in generated}
    assert "std_c01.py" in generated_names
    content = (spec_path.parent / "std_c01.py").read_text(encoding="utf-8")
    assert "cable_harness_stub" in content
    assert "Geometry source: PARAMETRIC_TEMPLATE" in content
