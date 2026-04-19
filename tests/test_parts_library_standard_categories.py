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

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from parts_resolver import _infer_category, load_registry
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
