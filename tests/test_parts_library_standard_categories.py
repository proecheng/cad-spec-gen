"""Task 8: parts_library.default.yaml 的 4 类 STANDARD_* mapping 命中测试。

Task 7 已在 _infer_category 里支持 match.category in
{seal, locating, elastic, transmission} → STANDARD_* 路由。
Task 8 只是在 yaml 里补齐这 4 条 mapping 规则。

测试策略（与 Task 7 的 VENDOR_PURCHASED 测试相同模式）：
加载 default registry → 按 match.category 抽出新增的 4 条规则 →
直接调 _infer_category(rule, fake_adapter) 验证推断结果。

为何不 end-to-end 走 resolve()：elastic/locating/transmission 的 category
既不在 jinja_primitive 的 _GENERATORS，也不在 sw_toolbox catalog 覆盖范围，
end-to-end 必 miss 与本 Task 验收目标（yaml 规则存在 + 推断正确）正交。
"""
from __future__ import annotations

import pytest

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from parts_resolver import PartQuery, _infer_category, default_resolver, load_registry
from sw_preflight.types import PartCategory


def _find_rule_by_match_category(cat: str) -> dict:
    """从默认 registry 按 match.category 抽第一条规则，找不到报错便于定位 yaml 缺漏。"""
    registry = load_registry(project_root=".")
    for rule in registry.get("mappings", []):
        if rule.get("match", {}).get("category") == cat:
            return rule
    raise AssertionError(
        f"parts_library.default.yaml 缺 match.category={cat!r} 的 mapping（Task 8）"
    )


class _FakeSwToolbox:
    """伪造 adapter，只需 name 属性供 _infer_category 走路由。"""
    name = "sw_toolbox"


def test_o_ring_rule_exists_and_routes_to_standard_seal() -> None:
    """yaml 应有 match.category=seal 规则 → _infer_category → STANDARD_SEAL。"""
    rule = _find_rule_by_match_category("seal")
    assert _infer_category(rule, _FakeSwToolbox()) == PartCategory.STANDARD_SEAL


def test_dowel_pin_rule_exists_and_routes_to_standard_locating() -> None:
    """yaml 应有 match.category=locating 规则 → _infer_category → STANDARD_LOCATING。"""
    rule = _find_rule_by_match_category("locating")
    assert _infer_category(rule, _FakeSwToolbox()) == PartCategory.STANDARD_LOCATING


def test_compression_spring_rule_exists_and_routes_to_standard_elastic() -> None:
    """yaml 应有 match.category=elastic 规则 → _infer_category → STANDARD_ELASTIC。"""
    rule = _find_rule_by_match_category("elastic")
    assert _infer_category(rule, JinjaPrimitiveAdapter()) == PartCategory.STANDARD_ELASTIC


def test_gear_rule_exists_and_routes_to_standard_transmission() -> None:
    """yaml 应有 match.category=transmission 规则 → _infer_category → STANDARD_TRANSMISSION。"""
    rule = _find_rule_by_match_category("transmission")
    assert (
        _infer_category(rule, JinjaPrimitiveAdapter())
        == PartCategory.STANDARD_TRANSMISSION
    )


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("motor", "NEMA17 步进电机", ""),
        ("sensor", "M12 电感接近开关", ""),
        ("cable", "拖链线束", "4芯×1200mm"),
        ("pneumatic", "薄型气缸", "MGPM20-50"),
    ],
)
def test_common_electromechanical_rule_exists_before_terminal_fallback(
    category: str,
    name: str,
    material: str,
) -> None:
    """常用机电件应有显式默认规则，不能只靠终端 fallback 或项目特判。"""
    query = PartQuery(
        part_no="GEN-DEFAULT-RULE",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )
    rules = default_resolver(project_root="__missing_project__").matching_rules(
        query,
        adapter_name="jinja_primitive",
    )

    assert rules
    assert rules[0]["match"].get("category") == category


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("bearing", "MGN12H 直线导轨滑块", ""),
        ("transmission", "GT2 30T 同步带轮", "孔径8mm 6mm带宽"),
        ("connector", "KF301 接线端子", "3P 5.08mm"),
        ("pneumatic", "二位五通电磁阀", "DC24V"),
    ],
)
def test_common_model_batch_2_rule_exists_before_terminal_fallback(
    category: str,
    name: str,
    material: str,
) -> None:
    """第二批常用模型库应有显式规则，不能只靠终端 fallback。"""
    query = PartQuery(
        part_no="B2-DEFAULT-RULE",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )
    rules = default_resolver(project_root="__missing_project__").matching_rules(
        query,
        adapter_name="jinja_primitive",
    )

    assert rules
    assert rules[0]["match"].get("category") == category


def test_batch_2_linear_guide_route_precedes_generic_bearing_routes() -> None:
    """线性导轨滑块应先走 B 级模板，不被通用轴承 catalog 抢走。"""
    query = PartQuery(
        part_no="B2-LINEAR-GUIDE",
        name_cn="MGN12H 直线导轨滑块",
        material="",
        category="bearing",
        make_buy="外购",
    )

    rules = default_resolver(project_root="__missing_project__").matching_rules(query)

    assert rules[0]["adapter"] == "jinja_primitive"
    assert rules[0]["match"].get("name_contains") == [
        "直线导轨",
        "linear guide",
        "MGN",
        "HGW",
        "HGH",
        "导轨滑块",
    ]


def test_batch_2_normal_bearing_route_is_not_stolen_by_linear_guide() -> None:
    """普通滚动轴承仍应优先使用标准件库。"""
    query = PartQuery(
        part_no="B2-BEARING",
        name_cn="608ZZ 深沟球轴承",
        material="",
        category="bearing",
        make_buy="外购",
    )

    rules = default_resolver(project_root="__missing_project__").matching_rules(query)

    assert rules[0]["adapter"] in {"sw_toolbox", "bd_warehouse"}


def test_batch_2_m12_sensor_route_is_not_stolen_by_connector_rule() -> None:
    """裸 M12 不能把接近开关误导到连接器模板。"""
    query = PartQuery(
        part_no="B2-SENSOR",
        name_cn="M12 电感接近开关",
        material="PNP NO",
        category="sensor",
        make_buy="外购",
    )

    rules = default_resolver(project_root="__missing_project__").matching_rules(
        query,
        adapter_name="jinja_primitive",
    )

    assert rules[0]["match"].get("category") == "sensor"


@pytest.mark.parametrize(
    ("category", "name", "material", "match_key", "match_value"),
    [
        (
            "bearing",
            "UCP204 轴承座",
            "",
            "name_contains",
            ["轴承座", "pillow block", "flange bearing", "UCP", "UCF", "KP08", "KFL"],
        ),
        (
            "transmission",
            "BK12 丝杠支撑座",
            "",
            "keyword_contains",
            ["BK12", "BF12", "丝杠支撑座", "丝杆支撑座", "lead screw support", "support block"],
        ),
        (
            "transmission",
            "KK60 直线模组",
            "行程300mm",
            "keyword_contains",
            ["直线模组", "线性模组", "滑台模组", "linear module", "linear actuator module", "KK60", "KK86"],
        ),
        (
            "connector",
            "DIN导轨端子",
            "2.5mm2",
            "name_contains",
            ["DIN导轨端子", "DIN rail terminal"],
        ),
        (
            "other",
            "DIN导轨电源",
            "24V 60W",
            "keyword_contains",
            ["DIN导轨", "DIN rail", "35mm导轨", "导轨电源", "导轨继电器"],
        ),
    ],
)
def test_batch_3_default_routes_precede_generic_fallbacks(
    category: str,
    name: str,
    material: str,
    match_key: str,
    match_value: list[str],
) -> None:
    """第三批常用模型必须先命中显式族规则，不能靠 any:true 终端兜底。"""
    query = PartQuery(
        part_no="B3-DEFAULT-RULE",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )

    rules = default_resolver(project_root="__missing_project__").matching_rules(
        query,
        adapter_name="jinja_primitive",
    )

    assert rules
    assert rules[0]["match"].get("category") == category
    assert rules[0]["match"].get(match_key) == match_value


def test_batch_3_pneumatic_accessory_route_covers_manifold_and_frl() -> None:
    """气动附件路线应覆盖阀岛和 FRL，且早于普通气缸路线。"""
    resolver = default_resolver(project_root="__missing_project__")

    for name, material in [
        ("4联阀岛", "DC24V"),
        ("过滤减压阀", "G1/4 FRL"),
    ]:
        query = PartQuery(
            part_no="B3-PNEUMATIC",
            name_cn=name,
            material=material,
            category="pneumatic",
            make_buy="外购",
        )
        rules = resolver.matching_rules(query, adapter_name="jinja_primitive")

        assert rules
        assert rules[0]["match"].get("keyword_contains") == [
            "电磁阀",
            "solenoid valve",
            "快插",
            "push fitting",
            "气管接头",
            "调压阀",
            "过滤减压阀",
            "阀岛",
            "valve manifold",
            "FRL",
            "filter regulator",
            "air regulator",
            "调压过滤器",
        ]


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("fastener", "DIN912 内六角螺钉", "M5×16"),
        ("other", "阀体安装板", "6061 80×40×6mm"),
        ("other", "普通支撑座", "铝合金 60×40×20mm"),
    ],
)
def test_batch_3_broad_tokens_do_not_activate_new_default_routes(
    category: str,
    name: str,
    material: str,
) -> None:
    """裸 DIN/阀/支撑座 等宽泛词不能触发第三批 B 级模板族。"""
    query = PartQuery(
        part_no="B3-NEGATIVE",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )

    rules = default_resolver(project_root="__missing_project__").matching_rules(
        query,
        adapter_name="jinja_primitive",
    )

    assert rules[0]["match"] == {"any": True}
