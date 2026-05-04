from __future__ import annotations

import pytest

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from cad_spec_defaults import lookup_std_part_dims
from parts_resolver import PartQuery, default_resolver


def _q(category: str, name: str, material: str = "") -> PartQuery:
    return PartQuery(
        part_no="B2-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("MGN12H 直线导轨滑块", "", "bearing"),
        ("HGW15 直线导轨滑块", "", "bearing"),
        ("L050 夹紧联轴器", "Φ6.35×25mm", "transmission"),
        ("GT2 30T 同步带轮", "孔径8mm 6mm带宽", "transmission"),
        ("1模20齿直齿轮", "m=1 z=20 孔径6mm", "transmission"),
        ("KF301 接线端子", "3P 5.08mm", "connector"),
        ("M12 5芯航空插头", "", "connector"),
        ("二位五通电磁阀", "DC24V", "pneumatic"),
        ("快插气管接头", "PC6-01", "pneumatic"),
    ],
)
def test_batch_2_common_names_classify_to_reusable_categories(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("M12 电感接近开关", "PNP NO", "sensor"),
        ("608ZZ 深沟球轴承", "", "bearing"),
        ("普通滑块", "POM 20×10×6mm", "other"),
        ("PC6 控制板", "PCB 20×30mm", "other"),
        ("M12 六角螺母", "GB/T 6170", "fastener"),
        ("微量泵（溶剂喷射）", "电磁阀式", "pump"),
    ],
)
def test_batch_2_classifier_does_not_steal_ambiguous_rows(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("category", "name", "material", "template", "dims"),
    [
        (
            "bearing",
            "MGN12H 直线导轨滑块",
            "",
            "linear_guide_carriage",
            (45, 27, 15),
        ),
        (
            "transmission",
            "L050 夹紧联轴器",
            "Φ6.35×25mm",
            "clamping_coupling_lxx",
            (20, 20, 25),
        ),
        (
            "transmission",
            "GT2 30T 同步带轮",
            "孔径8mm 6mm带宽",
            "gt2_timing_pulley",
            (19.1, 19.1, 10),
        ),
        (
            "transmission",
            "1模20齿直齿轮",
            "m=1 z=20 孔径6mm",
            "spur_gear",
            (22, 22, 8),
        ),
        (
            "connector",
            "KF301 接线端子",
            "3P 5.08mm",
            "terminal_block",
            (15.24, 8, 10),
        ),
        (
            "connector",
            "M12 5芯航空插头",
            "",
            "m12_connector",
            (16.2, 16.2, 26.6),
        ),
        (
            "pneumatic",
            "二位五通电磁阀",
            "DC24V",
            "pneumatic_solenoid_valve",
            (45, 22, 28),
        ),
        (
            "pneumatic",
            "快插气管接头",
            "PC6-01",
            "pneumatic_push_fitting",
            (12, 12, 22),
        ),
    ],
)
def test_batch_2_jinja_templates_are_b_grade_reusable_families(
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
    assert result.metadata["template_scope"] == "reusable_part_family"
    assert result.real_dims == dims


@pytest.mark.parametrize(
    ("category", "name", "material", "forbidden_template"),
    [
        ("bearing", "608ZZ 深沟球轴承", "", "linear_guide_carriage"),
        ("bearing", "普通滑块", "POM 20×10×6mm", "linear_guide_carriage"),
        ("connector", "M12 电感接近开关", "PNP NO", "m12_connector"),
        ("pneumatic", "PC6 控制板", "PCB 20×30mm", "pneumatic_push_fitting"),
        ("transmission", "同步带 400mm", "GT2 闭环", "gt2_timing_pulley"),
    ],
)
def test_batch_2_templates_require_specific_family_intent(
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
        ("bearing", "MGN12H 直线导轨滑块", ""),
        ("transmission", "L050 夹紧联轴器", "Φ6.35×25mm"),
        ("transmission", "GT2 30T 同步带轮", "孔径8mm 6mm带宽"),
        ("transmission", "1模20齿直齿轮", "m=1 z=20 孔径6mm"),
        ("connector", "KF301 接线端子", "3P 5.08mm"),
        ("connector", "M12 5芯航空插头", ""),
        ("pneumatic", "二位五通电磁阀", "DC24V"),
        ("pneumatic", "快插气管接头", "PC6-01"),
    ],
)
def test_batch_2_template_geometry_stays_within_reported_real_dims(
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
        (_q("bearing", "MGN12H 直线导轨滑块"), "bearing", "jinja_primitive"),
        (
            _q("transmission", "GT2 30T 同步带轮", "孔径8mm 6mm带宽"),
            "transmission",
            "jinja_primitive",
        ),
        (_q("connector", "KF301 接线端子", "3P 5.08mm"), "connector", "jinja_primitive"),
        (_q("pneumatic", "二位五通电磁阀", "DC24V"), "pneumatic", "jinja_primitive"),
    ],
)
def test_default_library_has_explicit_batch_2_rules_before_terminal_fallback(
    query: PartQuery,
    expected_category: str,
    expected_adapter: str,
) -> None:
    resolver = default_resolver(project_root="__missing_project__")

    rules = resolver.matching_rules(query, adapter_name=expected_adapter)

    assert rules
    assert rules[0]["match"].get("category") == expected_category


def test_linear_guide_rule_precedes_generic_bearing_routes_but_not_vendor_steps() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("bearing", "MGN12H 直线导轨滑块")

    matching = resolver.matching_rules(query)

    assert matching[0]["adapter"] == "jinja_primitive"
    assert matching[0]["match"].get("name_contains") == [
        "直线导轨",
        "linear guide",
        "MGN",
        "HGW",
        "HGH",
        "导轨滑块",
    ]


def test_normal_ball_bearing_still_prefers_standard_bearing_routes() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("bearing", "608ZZ 深沟球轴承")

    matching = resolver.matching_rules(query)

    assert matching[0]["adapter"] in {"sw_toolbox", "bd_warehouse"}
    assert matching[0]["adapter"] != "jinja_primitive"


def test_m12_proximity_sensor_keeps_sensor_rule_before_connector_rule() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("sensor", "M12 电感接近开关", "PNP NO")

    matching = resolver.matching_rules(query, adapter_name="jinja_primitive")

    assert matching
    assert matching[0]["match"].get("category") == "sensor"


def test_generic_solenoid_valve_dims_match_specific_solenoid_family() -> None:
    """同一气动阀模板不能因别名不同产生 w/d/h 坐标语义漂移。"""
    generic = JinjaPrimitiveAdapter().resolve(_q("pneumatic", "电磁阀", "DC24V"), {})
    specific = JinjaPrimitiveAdapter().resolve(
        _q("pneumatic", "二位五通电磁阀", "DC24V"),
        {},
    )

    assert generic.metadata["template"] == "pneumatic_solenoid_valve"
    assert generic.real_dims == specific.real_dims == (45, 22, 28)


@pytest.mark.parametrize(
    ("name", "material", "template", "dims"),
    [
        ("pneumatic solenoid valve", "DC24V", "pneumatic_solenoid_valve", (45, 22, 28)),
        ("pneumatic push fitting", "PC8-01", "pneumatic_push_fitting", (14, 14, 25)),
    ],
)
def test_pneumatic_accessory_templates_precede_generic_pneumatic_body(
    name: str,
    material: str,
    template: str,
    dims: tuple[float, float, float],
) -> None:
    result = JinjaPrimitiveAdapter().resolve(_q("pneumatic", name, material), {})

    assert result.metadata["template"] == template
    assert result.real_dims == dims


def test_dimension_lookup_is_category_scoped_for_cross_family_descriptors() -> None:
    """material 中的别族关键词不能覆盖 name 中更具体的同类型号。"""
    assert lookup_std_part_dims(
        "微量泵（溶剂喷射）",
        "电磁阀式",
        category="pump",
    ) == {"w": 20, "h": 15, "l": 30}
    assert lookup_std_part_dims("电磁阀", "DC24V", category="pneumatic") == {
        "w": 45,
        "d": 22,
        "h": 28,
    }
