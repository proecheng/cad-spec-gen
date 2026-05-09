"""tools/jury/cost.py — 预估 + budget 守门 + cost=0 警告。"""
from __future__ import annotations

import pytest

from tools.jury.cost import CostDecision, compute_cost_decision


def test_estimate_under_budget_no_confirm() -> None:
    decision = compute_cost_decision(
        cost_per_call_usd=0.005, n_views=6, budget_per_run_usd=0.1, confirm_cost=False
    )
    assert decision.allowed is True
    assert decision.estimated_usd == pytest.approx(0.030)


def test_estimate_equal_budget_no_confirm() -> None:
    decision = compute_cost_decision(
        cost_per_call_usd=0.01, n_views=10, budget_per_run_usd=0.1, confirm_cost=False
    )
    assert decision.allowed is True


def test_estimate_over_budget_no_confirm_rejected() -> None:
    decision = compute_cost_decision(
        cost_per_call_usd=0.05, n_views=6, budget_per_run_usd=0.1, confirm_cost=False
    )
    assert decision.allowed is False
    assert "超" in decision.reason or "exceed" in decision.reason.lower()


def test_estimate_over_budget_with_confirm_allowed() -> None:
    decision = compute_cost_decision(
        cost_per_call_usd=0.05, n_views=6, budget_per_run_usd=0.1, confirm_cost=True
    )
    assert decision.allowed is True


def test_cost_zero_normal_no_warn() -> None:
    """免费 profile 默认放行（不强制 confirm-cost）当 budget > 0。"""
    decision = compute_cost_decision(
        cost_per_call_usd=0.0, n_views=100, budget_per_run_usd=0.1, confirm_cost=False
    )
    assert decision.allowed is True


def test_cost_zero_with_budget_zero_double_zero_no_confirm() -> None:
    """双 0：cost=0 + budget=0 是最严守门 → 不需 confirm-cost。"""
    decision = compute_cost_decision(
        cost_per_call_usd=0.0, n_views=10, budget_per_run_usd=0.0, confirm_cost=False
    )
    assert decision.allowed is True


def test_n_views_zero_edge() -> None:
    """N=0 视角 cost=0 通过（虽然 Layer 0 已拒 views=[]，cost.py 兜底）。"""
    decision = compute_cost_decision(
        cost_per_call_usd=0.005, n_views=0, budget_per_run_usd=0.1, confirm_cost=False
    )
    assert decision.allowed is True
    assert decision.estimated_usd == 0.0


def test_budget_zero_with_cost_positive_rejected() -> None:
    """budget=0 + cost>0 必然拒（即使 confirm-cost，因为 == 不超）。"""
    decision = compute_cost_decision(
        cost_per_call_usd=0.005, n_views=1, budget_per_run_usd=0.0, confirm_cost=False
    )
    assert decision.allowed is False  # 0.005 > 0.0
