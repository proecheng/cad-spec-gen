from __future__ import annotations

import pytest

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from cad_spec_defaults import lookup_std_part_dims
from parts_resolver import PartQuery, default_resolver


def _q(category: str, name: str, material: str = "") -> PartQuery:
    return PartQuery(
        part_no="B4-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("IP65 控制箱", "160×120×80mm", "other"),
        ("22mm 急停按钮", "红色", "other"),
        ("M12 传感器安装支架", "不锈钢", "other"),
        ("真空发生器", "CV-10HS", "pneumatic"),
        ("真空吸盘", "Φ30 硅胶", "pneumatic"),
        ("2020铝型材", "L=200mm", "other"),
        ("2020角码", "铝合金", "other"),
    ],
)
def test_batch_4_common_names_classify_to_reusable_categories(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("普通支架", "铝合金 50×30×5mm", "other"),
        ("按钮标签", "PVC", "other"),
        ("真空包装袋", "PE", "other"),
        ("铝型材手册", "A4", "other"),
        ("M12 电感接近开关", "PNP NO", "sensor"),
        ("KF301 接线端子", "3P 5.08mm", "connector"),
    ],
)
def test_batch_4_classifier_does_not_steal_ambiguous_rows(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("category", "name", "material", "template", "dims"),
    [
        ("other", "IP65 控制箱", "160×120×80mm", "electrical_enclosure_box", (160, 120, 80)),
        ("other", "22mm 急停按钮", "红色", "panel_pushbutton_22mm", (30, 30, 45)),
        (
            "other",
            "M12 传感器安装支架",
            "不锈钢",
            "sensor_mounting_bracket",
            (50, 32, 28),
        ),
        ("pneumatic", "真空发生器", "CV-10HS", "vacuum_ejector", (60, 18, 28)),
        ("pneumatic", "真空吸盘", "Φ30 硅胶", "vacuum_suction_cup", (30, 30, 25)),
        ("other", "2020铝型材", "L=200mm", "aluminum_tslot_extrusion", (200, 20, 20)),
        ("other", "2020角码", "铝合金", "aluminum_corner_bracket", (40, 40, 20)),
    ],
)
def test_batch_4_jinja_templates_are_b_grade_reusable_families(
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
        ("other", "普通支架", "铝合金 50×30×5mm", "sensor_mounting_bracket"),
        ("other", "按钮标签", "PVC", "panel_pushbutton_22mm"),
        ("other", "真空包装袋", "PE", "vacuum_ejector"),
        ("other", "铝型材手册", "A4", "aluminum_tslot_extrusion"),
        ("sensor", "M12 电感接近开关", "PNP NO", "sensor_mounting_bracket"),
        ("connector", "KF301 接线端子", "3P 5.08mm", "panel_pushbutton_22mm"),
    ],
)
def test_batch_4_templates_require_specific_family_intent(
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
        ("other", "IP65 控制箱", "160×120×80mm"),
        ("other", "22mm 急停按钮", "红色"),
        ("other", "M12 传感器安装支架", "不锈钢"),
        ("pneumatic", "真空发生器", "CV-10HS"),
        ("pneumatic", "真空吸盘", "Φ30 硅胶"),
        ("other", "2020铝型材", "L=200mm"),
        ("other", "2020角码", "铝合金"),
    ],
)
def test_batch_4_template_geometry_stays_within_reported_real_dims(
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
    ("query", "expected_category", "expected_adapter"),
    [
        (_q("other", "IP65 控制箱", "160×120×80mm"), "other", "jinja_primitive"),
        (_q("other", "22mm 急停按钮", "红色"), "other", "jinja_primitive"),
        (_q("other", "M12 传感器安装支架", "不锈钢"), "other", "jinja_primitive"),
        (_q("pneumatic", "真空发生器", "CV-10HS"), "pneumatic", "jinja_primitive"),
        (_q("other", "2020铝型材", "L=200mm"), "other", "jinja_primitive"),
    ],
)
def test_default_library_has_explicit_batch_4_rules_before_terminal_fallback(
    query: PartQuery,
    expected_category: str,
    expected_adapter: str,
) -> None:
    resolver = default_resolver(project_root="__missing_project__")

    rules = resolver.matching_rules(query, adapter_name=expected_adapter)

    assert rules
    assert rules[0]["match"].get("category") == expected_category
    assert rules[0]["match"] != {"any": True}


def test_batch_4_existing_sensor_and_connector_templates_still_win() -> None:
    sensor = JinjaPrimitiveAdapter().resolve(_q("sensor", "M12 电感接近开关", "PNP NO"), {})
    connector = JinjaPrimitiveAdapter().resolve(
        _q("connector", "KF301 接线端子", "3P 5.08mm"),
        {},
    )

    assert sensor.source_tag == "parametric_template:cylindrical_proximity_sensor"
    assert connector.source_tag == "parametric_template:terminal_block"


def test_batch_4_dimension_lookup_is_category_scoped_for_vacuum_and_profile_text() -> None:
    assert lookup_std_part_dims("真空包装袋", "PE", category="other") == {}
    assert lookup_std_part_dims("2020铝型材", "L=200mm", category="other") == {
        "w": 200,
        "d": 20,
        "h": 20,
        "slot_w": 6,
    }
    assert lookup_std_part_dims("真空吸盘", "Φ30 硅胶", category="pneumatic") == {
        "w": 30,
        "d": 30,
        "h": 25,
    }
