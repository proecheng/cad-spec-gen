"""budget 计算 + 阈值比较 + cost=0 警告。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostDecision:
    """cost gate 决策结果：是否放行 + 预估金额 + 中文 reason。"""

    allowed: bool
    estimated_usd: float
    reason: str


def compute_cost_decision(
    *,
    cost_per_call_usd: float,
    n_views: int,
    budget_per_run_usd: float,
    confirm_cost: bool,
) -> CostDecision:
    """估算成本 + 比较 budget。

    前置条件：cost_per_call_usd 由 load_jury_config 校验通过
    （finite + 0 ≤ x < 1000）。直接调用方需自行保证此条件。

    规则：
    - estimated = cost_per_call_usd * n_views（保留 6 位小数防浮点漂移）
    - estimated <= budget → 放行
    - estimated > budget + confirm_cost=True → 放行（用户已显式 --confirm-cost）
    - estimated > budget + confirm_cost=False → 拒（exit=2）
    """
    estimated = round(float(cost_per_call_usd) * int(n_views), 6)

    if estimated <= budget_per_run_usd:
        return CostDecision(
            allowed=True,
            estimated_usd=estimated,
            reason=f"预估 {estimated} USD <= budget {budget_per_run_usd} USD",
        )

    if confirm_cost:
        return CostDecision(
            allowed=True,
            estimated_usd=estimated,
            reason=(
                f"预估 {estimated} USD 超 budget {budget_per_run_usd} USD"
                "（已 --confirm-cost 通过）"
            ),
        )

    return CostDecision(
        allowed=False,
        estimated_usd=estimated,
        reason=(
            f"预估 {estimated} USD 超 budget {budget_per_run_usd} USD；"
            "加 --confirm-cost 或调高 --budget"
        ),
    )
