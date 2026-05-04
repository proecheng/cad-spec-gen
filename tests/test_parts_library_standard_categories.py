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
