"""sw_toolbox_adapter ↔ sw_config_broker 测试辅助函数（Task 14 Step 5）。

conftest.py 的 autouse `disable_sw_config_broker_by_default` 把 env
`CAD_SW_BROKER_DISABLE=1` 当默认值，所有 broker 真路径短路成 policy_fallback。
任何想真跑 broker（或 mock broker 返指定结果）的测试，需要：
  1. delenv CAD_SW_BROKER_DISABLE  → 解除安全阀
  2. monkeypatch broker.resolve_config_for_part → 注入想要的 ConfigResolution
  3. （可选）monkeypatch broker._list_configs_via_com → 防御真 SW spawn

`patch_broker_to_return` 把 1+2 收成一行调用；3 默认不挂（patch
resolve_config_for_part 本身就吃掉了 _list_configs 的所有路径）。
"""

from __future__ import annotations

from typing import Optional


def patch_broker_to_return(
    monkeypatch,
    *,
    config_name: Optional[str],
    source: str = "auto",
    confidence: float = 1.0,
    available_configs: Optional[list[str]] = None,
    notes: str = "",
) -> None:
    """让 sw_toolbox_adapter.resolve() 内部 broker 调用返指定 ConfigResolution。

    Args:
      monkeypatch: pytest monkeypatch fixture
      config_name: broker 解析出的 SW config 名；None 触发 adapter miss 分支
      source: ConfigResolution.source（"auto" / "cached_decision" / "policy_fallback"）
      confidence: 0.0 ~ 1.0
      available_configs: 默认 [config_name]（None 时 fallback []）
      notes: 自由文本，进入 metadata.warnings 供调试

    用法：
        def test_xxx(monkeypatch, ...):
            patch_broker_to_return(monkeypatch, config_name="M6×20", source="auto")
            result = adapter.resolve(query, spec)
    """
    from adapters.solidworks import sw_config_broker as broker

    monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
    monkeypatch.setattr(
        broker,
        "resolve_config_for_part",
        lambda **kw: broker.ConfigResolution(
            config_name=config_name,
            source=source,
            confidence=confidence,
            available_configs=available_configs
            if available_configs is not None
            else ([config_name] if config_name else []),
            notes=notes,
        ),
    )
