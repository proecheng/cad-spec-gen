"""Task 7: ResolveResult.category 按 mapping + adapter 类型推断。

三档验证（Task 7 范围）：
1. STANDARD_FASTENER — match.category=fastener 规则命中
2. VENDOR_PURCHASED — step_pool adapter + spec.synthesizer
3. CUSTOM — jinja_primitive 兜底 adapter

其余 4 个 STANDARD_*（seal/locating/elastic/transmission）留给 Task 8 —
Task 8 才在 parts_library.default.yaml 补齐这 4 种 match.category 规则。
"""
from __future__ import annotations

from parts_resolver import PartQuery, default_resolver, _infer_category
from sw_preflight.types import PartCategory


def _query(**kwargs) -> PartQuery:
    """构造 PartQuery，必填字段给默认值以避免 TypeError。"""
    defaults = {
        "part_no": kwargs.pop("part_no", "TEST-001"),
        "name_cn": "",
        "material": "",
        "category": "",
        "make_buy": "",
    }
    defaults.update(kwargs)
    return PartQuery(**defaults)


def test_resolver_returns_fastener_category_for_gb_bolt() -> None:
    """GB/T 70.1 内六角螺栓 → STANDARD_FASTENER

    用 _infer_category 直接验证推断规则（仿下方 maxon 测试模式），
    避开 sw_toolbox / sw_config_broker / SW 缓存等与本 Task 正交的端到端依赖。
    规则原样取自 parts_library.default.yaml:108-116（sw_toolbox GB 头 fastener）。

    Task 14 重构原因：原端到端实现依赖项目根 `.cad-spec-gen/` SW 缓存才能 PASS；
    sw_config_broker 接入后默认安全阀 CAD_SW_BROKER_DISABLE=1 让 sw_toolbox 全 miss，
    fall-through 到 jinja_primitive (CUSTOM)，掩盖了真正想测的"category 推断"逻辑。
    """

    class _FakeSwToolbox:
        name = "sw_toolbox"

    rule = {
        "match": {"category": "fastener", "keyword_contains": ["GB/T", "国标", "GB "]},
        "adapter": "sw_toolbox",
        "spec": {
            "standard": "GB",
            "subcategories": ["bolts and studs"],
            "part_category": "fastener",
        },
    }
    assert _infer_category(rule, _FakeSwToolbox()) == PartCategory.STANDARD_FASTENER


def test_resolver_returns_vendor_category_for_maxon() -> None:
    """Maxon ECX SPEED 22L → VENDOR_PURCHASED

    用 _infer_category 直接验证推断规则——不 end-to-end 走 step_pool adapter
    以避开合成 STEP 文件 / cadquery bbox probe 这些与本 Task 正交的外部依赖。
    规则原样取自 parts_library.default.yaml:125-130。
    """

    class _FakeStepPool:
        name = "step_pool"

    rule = {
        "match": {"keyword_contains": ["ECX SPEED 22L"]},
        "adapter": "step_pool",
        "spec": {"file": "maxon/ecx_22l.step", "synthesizer": "maxon_ecx_22l"},
    }
    assert _infer_category(rule, _FakeStepPool()) == PartCategory.VENDOR_PURCHASED


def test_resolver_returns_custom_category_for_unknown() -> None:
    """未知件 PXY-2024-A → CUSTOM

    无匹配规则 → 走 `any: true` 终结规则 adapter=jinja_primitive → CUSTOM。
    """
    r = default_resolver(project_root=".")
    q = _query(name_cn="私有件 PXY-2024-A", category="", material="")
    res = r.resolve(q)
    assert res.category == PartCategory.CUSTOM
