"""enhance_budget.py 单元测试 — Task 4.1。

按 spec §3 / plan line 1158-1176：
- try_spend 累计扣减；超 cap 返 False 不扣减
- record_actual 修正预估
- 100 线程并发 try_spend 总和正确（threading.Lock 不丢账）
- 默认 cap 固定 1.5 USD（≈ 5 视角 × 0.25 + 安全余量，spec §4.1）
- extra_cost_cny 用 USD_TO_CNY_RATE = 7.2 换算
- estimate_retry_cost(adapter, request, with_jury) 复合 backend 估算 + 可选 jury 成本
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from enhance_budget import (
    JURY_LLM_CALL_COST_USD,
    USD_TO_CNY_RATE,
    LoopBudget,
    estimate_retry_cost,
)
from tools.jury_loop.backends.protocol import BackendRequest


# ---------------------------------------------------------------------------
# LoopBudget — 基本扣减语义
# ---------------------------------------------------------------------------


def test_try_spend_accumulates_within_cap() -> None:
    """连续 try_spend 在 cap 内成功累计。"""
    budget = LoopBudget(cap_usd=1.0, n_views=5)
    assert budget.try_spend(0.3) is True
    assert budget.try_spend(0.4) is True
    assert budget.spent == pytest.approx(0.7)


def test_try_spend_over_cap_returns_false_and_does_not_deduct() -> None:
    """超 cap 必须返 False 且不改 spent。"""
    budget = LoopBudget(cap_usd=1.0, n_views=5)
    assert budget.try_spend(0.6) is True
    assert budget.try_spend(0.6) is False  # 0.6 + 0.6 > 1.0
    assert budget.spent == pytest.approx(0.6)


def test_record_actual_corrects_estimate() -> None:
    """record_actual 替换之前 try_spend 的估算（diff 可正可负）。"""
    budget = LoopBudget(cap_usd=1.0, n_views=5)
    assert budget.try_spend(0.3) is True  # 估算
    budget.record_actual(0.25)  # 实际 0.25
    assert budget.spent == pytest.approx(0.25)


def test_record_actual_with_higher_actual_can_push_over_cap() -> None:
    """real cost > estimate 时允许 spent 超 cap（已花的钱无法回收）。"""
    budget = LoopBudget(cap_usd=1.0, n_views=5)
    assert budget.try_spend(0.9) is True
    budget.record_actual(1.2)  # vendor 实际收 1.2
    assert budget.spent == pytest.approx(1.2)
    # 后续 try_spend 应当返 False
    assert budget.try_spend(0.01) is False


# ---------------------------------------------------------------------------
# 默认 cap + extra_cost_cny
# ---------------------------------------------------------------------------


def test_default_cap_usd_is_1_5() -> None:
    """spec §4.1：默认 cap 1.5 USD（≈ 5 视角 × 0.25 + 安全余量）。"""
    budget = LoopBudget(n_views=5)
    assert budget.cap_usd == pytest.approx(1.5)


def test_extra_cost_cny_converts_with_fixed_rate() -> None:
    """extra_cost_cny = spent × USD_TO_CNY_RATE (7.2)。"""
    budget = LoopBudget(cap_usd=2.0, n_views=5)
    assert budget.try_spend(0.5) is True
    assert budget.extra_cost_cny == pytest.approx(0.5 * USD_TO_CNY_RATE)
    assert USD_TO_CNY_RATE == pytest.approx(7.2)


# ---------------------------------------------------------------------------
# 并发安全（100 线程 × 0.01 各 try_spend 一次）
# ---------------------------------------------------------------------------


def test_try_spend_thread_safe_under_100_concurrent_callers() -> None:
    """100 线程各 try_spend(0.01) → 总和必须等于 1.00（无丢账 / 无重复扣减）。"""
    budget = LoopBudget(cap_usd=10.0, n_views=5)
    success_count = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal success_count
        if budget.try_spend(0.01):
            with lock:
                success_count += 1

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert success_count == 100
    assert budget.spent == pytest.approx(1.0)


def test_try_spend_thread_safe_at_cap_boundary() -> None:
    """cap=1.0；100 线程各 try_spend(0.01) → 全部成功且 spent==1.0；第 101 个失败。"""
    budget = LoopBudget(cap_usd=1.0, n_views=5)
    success_count = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal success_count
        if budget.try_spend(0.01):
            with lock:
                success_count += 1

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert success_count == 100
    assert budget.spent == pytest.approx(1.0)
    # 越界一笔必须被拒
    assert budget.try_spend(0.001) is False


# ---------------------------------------------------------------------------
# estimate_retry_cost — 复合 backend 自报 + jury 可选
# ---------------------------------------------------------------------------


class _StubAdapter:
    """最小 BackendAdapter 实现，仅供 estimate_retry_cost 测试。"""

    kind = "stub"
    known_params: dict[str, tuple[float | None, float | None]] = {}

    def supports_controlnet(self) -> bool:
        return False

    def estimate_cost_usd(self, request: BackendRequest) -> float:
        return 0.123

    def call(self, request: BackendRequest, timeout: float) -> Any:  # pragma: no cover
        raise NotImplementedError


def _make_request() -> BackendRequest:
    return BackendRequest(
        input_image_path=Path("/tmp/x.png"),
        prompt="p",
        params={},
        base_url="https://example.com",
        api_key="k",
        model_name="m",
    )


def test_estimate_retry_cost_without_jury_equals_adapter_estimate() -> None:
    """with_jury=False → 仅 adapter.estimate_cost_usd。"""
    cost = estimate_retry_cost(_StubAdapter(), _make_request(), with_jury=False)
    assert cost == pytest.approx(0.123)


def test_estimate_retry_cost_with_jury_adds_llm_call_cost() -> None:
    """with_jury=True → adapter 估算 + JURY_LLM_CALL_COST_USD。"""
    cost = estimate_retry_cost(_StubAdapter(), _make_request(), with_jury=True)
    assert cost == pytest.approx(0.123 + JURY_LLM_CALL_COST_USD)
    assert JURY_LLM_CALL_COST_USD == pytest.approx(0.005)
