"""跨 SP 通用预算原语 — Task 4.1（M-1 + M-13）。

按 spec §3 实现注记：
- `JURY_LLM_CALL_COST_USD = 0.005`：jury 一次 LLM 调用的固定单价。
- `USD_TO_CNY_RATE = 7.2`：sidecar 显示用固定汇率（spec §4.4）。
- `LoopBudget(cap_usd, n_views)`：threading.Lock 保护下的累计预算簿。
- `estimate_retry_cost(adapter, request, with_jury)`：复合"backend 自报 + 可选 jury"成本。

不再保留 `BACKEND_RETRY_COST_USD` 静态常量 — 每个 BackendAdapter 自己实现
`estimate_cost_usd(request)`（M-2 SP3 多态代价模型）。

设计要点：
- spec §4.4 sidecar 字段需要 `extra_cost_cny`，故汇率与 LLM 单价都在本模块作为
  顶层常量导出，避免在 metadata / orchestrator 层重复定义。
- `LoopBudget` 不夹带"jury 已花几次"等业务字段；那些归属于 sidecar/orchestrator。
- `try_spend` 与 `record_actual` 在同一 `_lock` 区段内读写 `_spent`，确保 100
  线程并发不丢账（test_enhance_budget 100 线程边界用例锁死该不变量）。
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅类型用
    from tools.jury_loop.backends.protocol import BackendAdapter, BackendRequest


# ---------------------------------------------------------------------------
# 跨 SP 通用常量
# ---------------------------------------------------------------------------

#: jury 一次 LLM 调用的固定单价（spec §3）。pick_max_jury 策略会触发一次额外调用。
JURY_LLM_CALL_COST_USD: float = 0.005

#: sidecar 显示用固定汇率（spec §4.4）；非实时，故意写死避免外部依赖。
USD_TO_CNY_RATE: float = 7.2

#: spec §4.1 默认 cap：≈ 5 视角 × 0.25 USD/视角 + 安全余量 = 1.5 USD。
_DEFAULT_CAP_USD: float = 1.5

#: cap 比较容忍：vendor 报价（如 0.0123）长序列累加 IEEE-754 误差可达 ~1e-15，
#: 不应让浮点抖动错拒合法预扣。1e-9 远小于任何真实成本档位（最小 LLM 单次 0.005）。
_CAP_EPSILON: float = 1e-9


# ---------------------------------------------------------------------------
# LoopBudget
# ---------------------------------------------------------------------------


class LoopBudget:
    """单次 enhance 任务的累计预算簿。

    - 多视角并发调用时，由 `_lock` 保证 try_spend / record_actual 的原子性。
    - `try_spend(amount)` 只允许扣减不超 cap 的额度；超过即返 False 不写。
    - `record_actual(amount)` 把上一次 try_spend 的"估算"替换为 vendor 真实
      回报值（diff 可正可负）；不会回滚到 try_spend 之前。

    构造参数：
    - `cap_usd`：本次任务允许的总预算（USD）；省略则取 `_DEFAULT_CAP_USD = 1.5`。
    - `n_views`：本次任务的视角数（仅做记录，不参与扣减计算）；orchestrator
      用于 sidecar `n_views_total` 字段。
    """

    def __init__(self, cap_usd: float | None = None, *, n_views: int) -> None:
        self.cap_usd: float = _DEFAULT_CAP_USD if cap_usd is None else float(cap_usd)
        self.n_views: int = int(n_views)
        self._spent: float = 0.0
        self._last_spent: float = 0.0
        self._lock: threading.Lock = threading.Lock()

    @property
    def spent(self) -> float:
        """已花金额（USD）。读时也加锁，避免多线程读到中间状态。"""
        with self._lock:
            return self._spent

    @property
    def extra_cost_cny(self) -> float:
        """sidecar 显示用：已花金额折人民币（USD_TO_CNY_RATE 固定汇率）。"""
        return self.spent * USD_TO_CNY_RATE

    def try_spend(self, amount: float) -> bool:
        """尝试预扣 `amount` USD。成功返 True 并累计；超 cap 返 False 不写。

        与 `record_actual` 配对使用：先 try_spend(estimate) 占额度，real call
        完成后 record_actual(real) 修正。failure path（vendor 报错）时不需要
        record_actual，预扣的估算保留作为"已花成本"。
        """
        amt = float(amount)
        with self._lock:
            if self._spent + amt > self.cap_usd + _CAP_EPSILON:
                return False
            self._spent += amt
            self._last_spent = amt
            return True

    def record_actual(self, amount: float) -> None:
        """把上一次 try_spend 的估算替换为 vendor 实际回报值。

        - real > estimate：spent 上修，可能超 cap（已花的钱无法回收，后续
          try_spend 自然会失败）。
        - real < estimate：spent 下修，释放预扣额度给后续 retry。

        实现：撤销 `_last_spent` 后写入 `amount`；调用前必先有一次成功的
        try_spend（否则等价于直接 += amount 也无害，但语义不当）。
        """
        amt = float(amount)
        with self._lock:
            self._spent = self._spent - self._last_spent + amt
            self._last_spent = amt


# ---------------------------------------------------------------------------
# estimate_retry_cost — 复合 adapter 自报 + 可选 jury
# ---------------------------------------------------------------------------


def estimate_retry_cost(
    adapter: "BackendAdapter",
    request: "BackendRequest",
    *,
    with_jury: bool,
) -> float:
    """估算一次 retry 的总成本（USD）。

    - `adapter.estimate_cost_usd(request)`：backend 自报（M-2 SP3 多态代价模型）。
    - `with_jury=True` 时再加一次 jury LLM 调用成本（pick_max_jury 策略）；
      `with_jury=False` 用于 force_retry 策略或 cost-gate 检查"光 retry 划不划算"。

    本函数不读 LoopBudget；仅返回数值供 orchestrator 决策与 try_spend 输入。
    """
    base = float(adapter.estimate_cost_usd(request))
    return base + (JURY_LLM_CALL_COST_USD if with_jury else 0.0)
