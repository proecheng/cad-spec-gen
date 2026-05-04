from __future__ import annotations

import pytest

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from cad_spec_defaults import lookup_std_part_dims
from parts_resolver import PartQuery, default_resolver


def _q(category: str, name: str, material: str = "") -> PartQuery:
    return PartQuery(
        part_no="B3-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("UCP204 轴承座", "", "bearing"),
        ("KP08 立式轴承座", "", "bearing"),
        ("BK12 丝杠支撑座", "", "transmission"),
        ("KK60 直线模组", "行程300mm", "transmission"),
        ("4联阀岛", "DC24V", "pneumatic"),
        ("过滤减压阀", "G1/4 FRL", "pneumatic"),
        ("DIN导轨端子", "2.5mm2", "connector"),
        ("DIN导轨电源", "24V 60W", "other"),
    ],
)
def test_batch_3_common_names_classify_to_reusable_categories(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("普通支撑座", "铝合金 60×40×20mm", "other"),
        ("DIN912 内六角螺钉", "M5×16", "fastener"),
        ("阀体安装板", "6061 80×40×6mm", "other"),
        ("608ZZ 深沟球轴承", "", "bearing"),
        ("DIN A4 标签纸", "不干胶", "other"),
    ],
)
def test_batch_3_classifier_does_not_steal_ambiguous_rows(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("category", "name", "material", "template", "dims"),
    [
        ("bearing", "UCP204 轴承座", "", "mounted_bearing_support", (127, 38, 65)),
        (
            "transmission",
            "BK12 丝杠支撑座",
            "",
            "lead_screw_support_block",
            (60, 25, 43),
        ),
        (
            "transmission",
            "KK60 直线模组",
            "行程300mm",
            "linear_motion_module",
            (300, 60, 45),
        ),
        ("pneumatic", "4联阀岛", "DC24V", "pneumatic_valve_manifold", (90, 32, 36)),
        (
            "pneumatic",
            "过滤减压阀",
            "G1/4 FRL",
            "pneumatic_filter_regulator",
            (42, 42, 90),
        ),
        (
            "connector",
            "DIN导轨端子",
            "2.5mm2",
            "din_rail_terminal_block",
            (5.2, 45, 35),
        ),
        ("other", "DIN导轨电源", "24V 60W", "din_rail_device", (90, 60, 55)),
    ],
)
def test_batch_3_jinja_templates_are_b_grade_reusable_families(
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
        ("other", "普通支撑座", "铝合金 60×40×20mm", "lead_screw_support_block"),
        ("other", "阀体安装板", "6061 80×40×6mm", "pneumatic_valve_manifold"),
        ("fastener", "DIN912 内六角螺钉", "M5×16", "din_rail_device"),
        ("bearing", "608ZZ 深沟球轴承", "", "mounted_bearing_support"),
        ("connector", "KF301 接线端子", "3P 5.08mm", "din_rail_terminal_block"),
    ],
)
def test_batch_3_templates_require_specific_family_intent(
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
        ("bearing", "UCP204 轴承座", ""),
        ("bearing", "KP08 立式轴承座", ""),
        ("transmission", "BK12 丝杠支撑座", ""),
        ("transmission", "KK60 直线模组", "行程300mm"),
        ("pneumatic", "4联阀岛", "DC24V"),
        ("pneumatic", "过滤减压阀", "G1/4 FRL"),
        ("connector", "DIN导轨端子", "2.5mm2"),
        ("other", "DIN导轨电源", "24V 60W"),
    ],
)
def test_batch_3_template_geometry_stays_within_reported_real_dims(
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
        (_q("bearing", "UCP204 轴承座"), "bearing", "jinja_primitive"),
        (_q("transmission", "BK12 丝杠支撑座"), "transmission", "jinja_primitive"),
        (_q("transmission", "KK60 直线模组", "行程300mm"), "transmission", "jinja_primitive"),
        (_q("pneumatic", "4联阀岛", "DC24V"), "pneumatic", "jinja_primitive"),
        (_q("connector", "DIN导轨端子", "2.5mm2"), "connector", "jinja_primitive"),
        (_q("other", "DIN导轨电源", "24V 60W"), "other", "jinja_primitive"),
    ],
)
def test_default_library_has_explicit_batch_3_rules_before_terminal_fallback(
    query: PartQuery,
    expected_category: str,
    expected_adapter: str,
) -> None:
    resolver = default_resolver(project_root="__missing_project__")

    rules = resolver.matching_rules(query, adapter_name=expected_adapter)

    assert rules
    assert rules[0]["match"].get("category") == expected_category


def test_batch_3_bearing_support_route_precedes_generic_bearing_catalogs() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("bearing", "UCP204 轴承座")

    matching = resolver.matching_rules(query)

    assert matching[0]["adapter"] == "jinja_primitive"
    assert matching[0]["match"].get("name_contains") == [
        "轴承座",
        "pillow block",
        "flange bearing",
        "UCP",
        "UCF",
        "KP08",
        "KFL",
    ]


def test_batch_3_lead_screw_support_route_precedes_lead_screw_route() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("transmission", "BK12 丝杠支撑座")

    matching = resolver.matching_rules(query)

    assert matching[0]["adapter"] == "jinja_primitive"
    assert matching[0]["match"].get("keyword_contains") == [
        "BK12",
        "BF12",
        "丝杠支撑座",
        "丝杆支撑座",
        "lead screw support",
        "support block",
    ]


def test_batch_3_normal_bearing_still_prefers_standard_bearing_routes() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("bearing", "608ZZ 深沟球轴承")

    matching = resolver.matching_rules(query)

    assert matching[0]["adapter"] in {"sw_toolbox", "bd_warehouse"}
    assert matching[0]["adapter"] != "jinja_primitive"


def test_batch_3_din_terminal_route_precedes_generic_terminal_block() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("connector", "DIN导轨端子", "2.5mm2")

    matching = resolver.matching_rules(query, adapter_name="jinja_primitive")

    assert matching[0]["match"].get("name_contains") == [
        "DIN导轨端子",
        "DIN rail terminal",
    ]


def test_batch_3_dimension_lookup_is_category_scoped_for_din_and_support_text() -> None:
    assert lookup_std_part_dims("DIN912 内六角螺钉", "M5×16", category="fastener") == {}
    assert lookup_std_part_dims("BK12 丝杠支撑座", "", category="transmission") == {
        "w": 60,
        "d": 25,
        "h": 43,
        "bore_d": 12,
        "mount_d": 5,
    }
    assert lookup_std_part_dims("DIN导轨电源", "24V 60W", category="other") == {
        "w": 90,
        "d": 60,
        "h": 55,
    }
