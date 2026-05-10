"""Task 3.2：score_select Strategy Protocol + 两实现单元测试（RED → GREEN）。

按 spec §4.5.2 实现可插拔 Strategy；本测试覆盖 plan line 1146-1152 全 7 例。
SP3 兼容性约束：candidates 是 list（不是 2-tuple），SP1 始终传 2 张。
"""
from __future__ import annotations

from typing import Callable
from unittest.mock import MagicMock

import pytest

from tools.jury.verdict import ViewVerdict
from tools.jury_loop.score_select import (
    STRATEGY_REGISTRY,
    CandidateImage,
    ForceRetryStrategy,
    PickMaxJuryStrategy,
    ScoreSelectStrategy,
    SelectionResult,
)


def _v(score: int) -> ViewVerdict:
    """造最小有效 ViewVerdict 仅设 photoreal_score。"""
    return ViewVerdict(
        semantic_checks={},
        photoreal_score=score,
        reason="x",
        parse_status="ok",
    )


@pytest.fixture
def baseline() -> CandidateImage:
    """baseline 张已被 orchestrator 评过分（verdict 非 None）。"""
    return CandidateImage(image_path="/fake/baseline.jpg", verdict=_v(60))


@pytest.fixture
def retry() -> CandidateImage:
    """retry 张尚未评分（PickMaxJuryStrategy 内部调 jury_callable 评）。"""
    return CandidateImage(image_path="/fake/retry.jpg", verdict=None)


@pytest.fixture
def fake_budget() -> object:
    """LoopBudget 占位（Task 4.1 才创建）；SP1 两策略均不读 budget，给 sentinel。"""
    return object()


# ============ PickMaxJuryStrategy（plan line 1146-1149，4 case） ============


def test_pick_max_jury_retry_higher_than_baseline_picks_retry(
    baseline: CandidateImage, retry: CandidateImage, fake_budget: object
) -> None:
    """retry score > baseline → 选 retry，extra_jury_calls=1。"""
    jury_callable: Callable[[str], ViewVerdict] = MagicMock(return_value=_v(80))
    strat = PickMaxJuryStrategy()
    result = strat.select([baseline, retry], jury_callable, fake_budget)  # type: ignore[arg-type]
    assert result.pick.image_path == "/fake/retry.jpg"
    assert result.pick.verdict is not None
    assert result.pick.verdict.photoreal_score == 80
    assert result.extra_jury_calls == 1


def test_pick_max_jury_retry_lower_than_baseline_picks_baseline(
    baseline: CandidateImage, retry: CandidateImage, fake_budget: object
) -> None:
    """retry score < baseline → 选 baseline（保守），extra_jury_calls=1。"""
    jury_callable: Callable[[str], ViewVerdict] = MagicMock(return_value=_v(50))
    strat = PickMaxJuryStrategy()
    result = strat.select([baseline, retry], jury_callable, fake_budget)  # type: ignore[arg-type]
    assert result.pick.image_path == "/fake/baseline.jpg"
    assert result.extra_jury_calls == 1


def test_pick_max_jury_retry_equal_to_baseline_picks_baseline(
    baseline: CandidateImage, retry: CandidateImage, fake_budget: object
) -> None:
    """retry score == baseline → 选 baseline（保守），extra_jury_calls=1。"""
    jury_callable: Callable[[str], ViewVerdict] = MagicMock(return_value=_v(60))
    strat = PickMaxJuryStrategy()
    result = strat.select([baseline, retry], jury_callable, fake_budget)  # type: ignore[arg-type]
    assert result.pick.image_path == "/fake/baseline.jpg"
    assert result.extra_jury_calls == 1


def test_pick_max_jury_callable_raises_picks_baseline_zero_extra_calls(
    baseline: CandidateImage, retry: CandidateImage, fake_budget: object
) -> None:
    """jury_callable 抛异常 → 选 baseline，extra_jury_calls=0（spec §4.6 jury_unavailable 路径之一）。"""
    jury_callable = MagicMock(side_effect=RuntimeError("jury offline"))
    strat = PickMaxJuryStrategy()
    result = strat.select([baseline, retry], jury_callable, fake_budget)  # type: ignore[arg-type]
    assert result.pick.image_path == "/fake/baseline.jpg"
    assert result.extra_jury_calls == 0


# ============ ForceRetryStrategy（plan line 1150-1151，2 case） ============


def test_force_retry_picks_retry_zero_extra_jury_calls(
    baseline: CandidateImage, retry: CandidateImage, fake_budget: object
) -> None:
    """force_retry 不调 jury 强选 retry，extra_jury_calls=0。"""
    jury_callable = MagicMock()  # 不应被调
    strat = ForceRetryStrategy()
    result = strat.select([baseline, retry], jury_callable, fake_budget)  # type: ignore[arg-type]
    assert result.pick.image_path == "/fake/retry.jpg"
    assert result.extra_jury_calls == 0
    jury_callable.assert_not_called()


def test_force_retry_candidates_length_not_two_raises_value_error(
    fake_budget: object,
) -> None:
    """SP1 收紧：force_retry 候选 list 长度 ≠ 2 抛 ValueError（spec line 577）。"""
    strat = ForceRetryStrategy()
    one = [CandidateImage(image_path="/x.jpg", verdict=None)]
    with pytest.raises(ValueError):
        strat.select(one, MagicMock(), fake_budget)  # type: ignore[arg-type]
    three = [CandidateImage(image_path=f"/{i}.jpg", verdict=None) for i in range(3)]
    with pytest.raises(ValueError):
        strat.select(three, MagicMock(), fake_budget)  # type: ignore[arg-type]


# ============ STRATEGY_REGISTRY（plan line 1152，1 case） ============


def test_registry_maps_strings_to_strategy_classes() -> None:
    """STRATEGY_REGISTRY: 字符串 → Strategy 类映射（不是实例）。"""
    assert STRATEGY_REGISTRY["pick_max_jury"] is PickMaxJuryStrategy
    assert STRATEGY_REGISTRY["force_retry"] is ForceRetryStrategy
    # 实例化无副作用
    inst1 = STRATEGY_REGISTRY["pick_max_jury"]()
    inst2 = STRATEGY_REGISTRY["force_retry"]()
    assert isinstance(inst1, ScoreSelectStrategy)
    assert isinstance(inst2, ScoreSelectStrategy)


# ============ 边角扩展：SelectionResult / Protocol runtime check ============


def test_selection_result_namedtuple_fields() -> None:
    """SelectionResult 字段顺序锁死（pick / extra_jury_calls / rationale）。"""
    pick = CandidateImage(image_path="/x.jpg", verdict=None)
    r = SelectionResult(pick=pick, extra_jury_calls=0, rationale="test")
    assert r.pick is pick
    assert r.extra_jury_calls == 0
    assert r.rationale == "test"


def test_pick_max_jury_candidates_length_not_two_raises_value_error(
    fake_budget: object,
) -> None:
    """PickMaxJuryStrategy 同样收紧 SP1 = 2 张候选。"""
    strat = PickMaxJuryStrategy()
    one = [CandidateImage(image_path="/x.jpg", verdict=_v(60))]
    with pytest.raises(ValueError):
        strat.select(one, MagicMock(), fake_budget)  # type: ignore[arg-type]
