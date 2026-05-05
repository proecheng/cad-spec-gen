from __future__ import annotations

import pytest

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from cad_spec_defaults import lookup_std_part_dims
from parts_resolver import PartQuery, default_resolver


def _q(category: str, name: str, material: str = "") -> PartQuery:
    return PartQuery(
        part_no="B5-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("60法兰伺服电机", "400W 3000rpm", "motor"),
        ("PLE60 行星减速机", "速比10:1", "reducer"),
        ("Igus 拖链段", "内宽18mm", "cable"),
        ("DIN导轨继电器模块", "24V 1CO", "other"),
        ("按钮盒", "2孔 22mm", "other"),
    ],
)
def test_batch_5_common_names_classify_to_reusable_categories(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("伺服标签", "不干胶", "other"),
        ("行星轮图纸", "A4", "other"),
        ("拖链润滑说明", "PDF", "other"),
        ("继电器标签", "PVC", "other"),
        ("按钮标签", "PVC", "other"),
        ("DIN912 内六角螺钉", "M5×16", "fastener"),
    ],
)
def test_batch_5_classifier_does_not_steal_ambiguous_rows(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("category", "name", "material", "template", "dims"),
    [
        (
            "motor",
            "60法兰伺服电机",
            "400W 3000rpm",
            "square_flange_servo_motor",
            (60, 60, 115),
        ),
        (
            "reducer",
            "PLE60 行星减速机",
            "速比10:1",
            "planetary_gearbox",
            (60, 60, 70),
        ),
        (
            "cable",
            "Igus 拖链段",
            "内宽18mm",
            "drag_chain_segment",
            (120, 30, 18),
        ),
        (
            "other",
            "DIN导轨继电器模块",
            "24V 1CO",
            "din_rail_relay_module",
            (6.2, 78, 90),
        ),
        ("other", "按钮盒", "2孔 22mm", "operator_control_box", (80, 70, 65)),
    ],
)
def test_batch_5_jinja_templates_are_b_grade_reusable_families(
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
    assert result.source_tag == f"parametric_template:{template}"
    assert result.metadata["template"] == template
    assert result.metadata["template_scope"] == "reusable_part_family"
    assert result.real_dims == dims


@pytest.mark.parametrize(
    ("category", "name", "material", "forbidden_template"),
    [
        ("other", "伺服标签", "不干胶", "square_flange_servo_motor"),
        ("other", "行星轮图纸", "A4", "planetary_gearbox"),
        ("other", "拖链润滑说明", "PDF", "drag_chain_segment"),
        ("other", "继电器标签", "PVC", "din_rail_relay_module"),
        ("other", "按钮标签", "PVC", "operator_control_box"),
        ("fastener", "DIN912 内六角螺钉", "M5×16", "din_rail_relay_module"),
    ],
)
def test_batch_5_templates_require_specific_family_intent(
    category: str,
    name: str,
    material: str,
    forbidden_template: str,
) -> None:
    result = JinjaPrimitiveAdapter().resolve(_q(category, name, material), {})

    assert result.metadata.get("template") != forbidden_template


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("motor", "60法兰伺服电机", "400W 3000rpm"),
        ("reducer", "PLE60 行星减速机", "速比10:1"),
        ("cable", "Igus 拖链段", "内宽18mm"),
        ("other", "DIN导轨继电器模块", "24V 1CO"),
        ("other", "按钮盒", "2孔 22mm"),
    ],
)
def test_batch_5_template_geometry_stays_within_reported_real_dims(
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
    for measured, expected in zip((bbox.xlen, bbox.ylen, bbox.zlen), result.real_dims):
        assert measured <= expected + 1e-6


@pytest.mark.parametrize(
    ("query", "expected_category", "expected_adapter"),
    [
        (_q("motor", "60法兰伺服电机", "400W 3000rpm"), "motor", "jinja_primitive"),
        (_q("reducer", "PLE60 行星减速机", "速比10:1"), "reducer", "jinja_primitive"),
        (_q("cable", "Igus 拖链段", "内宽18mm"), "cable", "jinja_primitive"),
        (_q("other", "DIN导轨继电器模块", "24V 1CO"), "other", "jinja_primitive"),
        (_q("other", "按钮盒", "2孔 22mm"), "other", "jinja_primitive"),
    ],
)
def test_default_library_has_explicit_batch_5_rules_before_terminal_fallback(
    query: PartQuery,
    expected_category: str,
    expected_adapter: str,
) -> None:
    resolver = default_resolver(project_root="__missing_project__")

    rules = resolver.matching_rules(query, adapter_name=expected_adapter)

    assert rules
    assert rules[0]["match"].get("category") == expected_category
    assert rules[0]["match"] != {"any": True}


@pytest.mark.parametrize(
    ("category", "name", "template", "dims"),
    [
        ("motor", "AC servo motor", "square_flange_servo_motor", (60, 60, 115)),
        ("motor", "servo motor 60mm", "square_flange_servo_motor", (60, 60, 115)),
        ("reducer", "行星减速机", "planetary_gearbox", (60, 60, 70)),
        ("reducer", "planetary gearbox", "planetary_gearbox", (60, 60, 70)),
        ("reducer", "planetary reducer", "planetary_gearbox", (60, 60, 70)),
        ("cable", "塑料拖链段", "drag_chain_segment", (120, 30, 18)),
        ("cable", "drag chain segment", "drag_chain_segment", (120, 30, 18)),
        ("cable", "cable carrier", "drag_chain_segment", (120, 30, 18)),
        ("other", "DIN rail relay module", "din_rail_relay_module", (6.2, 78, 90)),
        ("other", "interface relay", "din_rail_relay_module", (6.2, 78, 90)),
        ("other", "操作盒", "operator_control_box", (80, 70, 65)),
        ("other", "control station", "operator_control_box", (80, 70, 65)),
        ("other", "operator box", "operator_control_box", (80, 70, 65)),
    ],
)
def test_batch_5_route_aliases_resolve_to_same_template_and_dims(
    category: str,
    name: str,
    template: str,
    dims: tuple[float, float, float],
) -> None:
    result = JinjaPrimitiveAdapter().resolve(_q(category, name, ""), {})

    assert result.source_tag == f"parametric_template:{template}"
    assert result.real_dims == dims


def test_batch_5_existing_stepper_and_din_power_templates_still_win() -> None:
    stepper = JinjaPrimitiveAdapter().resolve(_q("motor", "NEMA17 步进电机", ""), {})
    din_power = JinjaPrimitiveAdapter().resolve(
        _q("other", "DIN导轨电源", "24V 60W"),
        {},
    )

    assert stepper.source_tag == "parametric_template:nema_stepper_motor"
    assert din_power.source_tag == "parametric_template:din_rail_device"


def test_batch_5_dimension_lookup_is_category_scoped_for_cross_family_text() -> None:
    assert lookup_std_part_dims("伺服标签", "不干胶", category="other") == {}
    assert lookup_std_part_dims("行星轮图纸", "A4", category="other") == {}
    assert lookup_std_part_dims("继电器标签", "PVC", category="other") == {}
    assert lookup_std_part_dims(
        "60法兰伺服电机",
        "400W 3000rpm",
        category="motor",
    ) == {"w": 60, "d": 60, "h": 115, "body_h": 85, "shaft_d": 14}
    assert lookup_std_part_dims("AC servo motor", "", category="motor") == {
        "w": 60,
        "d": 60,
        "h": 115,
        "body_h": 85,
        "shaft_d": 14,
    }
    assert lookup_std_part_dims("PLE60 行星减速机", "速比10:1", category="reducer") == {
        "w": 60,
        "d": 60,
        "h": 70,
        "shaft_d": 14,
    }
    assert lookup_std_part_dims("planetary gearbox", "", category="reducer") == {
        "w": 60,
        "d": 60,
        "h": 70,
        "shaft_d": 14,
    }
    assert lookup_std_part_dims("drag chain segment", "", category="cable") == {
        "w": 120,
        "d": 30,
        "h": 18,
        "link_count": 8,
    }
    assert lookup_std_part_dims("control station", "", category="other") == {
        "w": 80,
        "d": 70,
        "h": 65,
        "button_count": 2,
    }
