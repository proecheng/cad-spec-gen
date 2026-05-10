"""Task 3.2：score_select 可插拔 Strategy Protocol（spec §4.5.2 / M-2 SP3 兼容）。

SP1 内置两策略：
- PickMaxJuryStrategy（默认）：retry 跑完调 jury 一次，retry > baseline 才选 retry
- ForceRetryStrategy：不调 jury 强选 retry，length≠2 抛 ValueError

SP3 多 sample 时新增 PickBestOfNStrategy 注册到 STRATEGY_REGISTRY，
orchestrator 调用代码不改（Strategy Protocol 锁死契约）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, NamedTuple, Protocol, runtime_checkable

from tools.jury.verdict import ViewVerdict

if TYPE_CHECKING:
    # Task 4.1 已落地 enhance_budget.LoopBudget；保留 TYPE_CHECKING 是为了避免
    # 循环导入风险（enhance_budget 后续可能 import jury_loop 工具），
    # 而非 Task 4.1 之前那样作为运行时占位（review Minor #7）。
    from enhance_budget import LoopBudget


class CandidateImage(NamedTuple):
    """候选张：image_path + 可选 verdict（None=未评分）。"""

    image_path: str
    verdict: ViewVerdict | None


class SelectionResult(NamedTuple):
    """选张结果：picked 张 + 实际 jury 调用次数 + 中文 rationale + retry verdict 出口。

    retry_verdict 出口（rev 3 决议 #12）：orchestrator 写 sidecar.retry 字段需要
    retry candidate 的二轮 verdict；即使最终 pick=baseline（retry 降分被拒），
    retry verdict 仍要原样保留以便观测（默认 None 兼容既有 3 字段调用点）。

    - PickMaxJuryStrategy：jury_callable 成功 → retry_verdict 为二轮 verdict
      （无论 pick 是 retry 还是 baseline）；jury_callable 抛异常 → None
    - ForceRetryStrategy：不二轮评分 → 始终 None
    """

    pick: CandidateImage
    extra_jury_calls: int
    rationale: str
    retry_verdict: ViewVerdict | None = None


@runtime_checkable
class ScoreSelectStrategy(Protocol):
    """选张策略契约（candidates 是 list 不是 2-tuple，SP3 兼容）。"""

    def select(
        self,
        candidates: list[CandidateImage],
        jury_callable: Callable[[str], ViewVerdict],
        budget: "LoopBudget",
    ) -> SelectionResult: ...


class PickMaxJuryStrategy:
    """retry 跑完后再调 jury 一次，比较 photoreal_score 选高分张。

    回退规则：
    - retry score 平/降 → 选 baseline（保守：付一次 jury 调用换"不会降分"安全网）
    - jury_callable 抛异常 → 选 baseline + extra_jury_calls=0
    """

    def select(
        self,
        candidates: list[CandidateImage],
        jury_callable: Callable[[str], ViewVerdict],
        budget: "LoopBudget",
    ) -> SelectionResult:
        if len(candidates) != 2:
            raise ValueError(
                f"PickMaxJuryStrategy 期望 2 张候选（baseline + retry），实际 {len(candidates)}"
            )
        baseline, retry = candidates
        if baseline.verdict is None:
            raise ValueError(
                "baseline candidate 必须已有 verdict（orchestrator 评过 baseline）"
            )

        try:
            retry_verdict = jury_callable(retry.image_path)
        except Exception:
            # 二轮 jury 失败 fallback：无 retry verdict 可填，retry_verdict=None
            return SelectionResult(
                pick=baseline,
                extra_jury_calls=0,
                rationale="二轮 jury 失败，保守退 baseline",
                retry_verdict=None,
            )

        retry_with_verdict = retry._replace(verdict=retry_verdict)
        if retry_verdict.photoreal_score > baseline.verdict.photoreal_score:
            # 选 retry 路径：retry_verdict 出口同二轮 verdict（rev 3 决议 #12）
            return SelectionResult(
                pick=retry_with_verdict,
                extra_jury_calls=1,
                rationale=(
                    f"retry 提分 {baseline.verdict.photoreal_score} → "
                    f"{retry_verdict.photoreal_score}，选 retry"
                ),
                retry_verdict=retry_verdict,
            )
        # 保守退 baseline 路径：retry verdict 仍出口（写 sidecar.retry 用，rev 3 决议 #12 关键点）
        return SelectionResult(
            pick=baseline,
            extra_jury_calls=1,
            rationale=(
                f"retry 平/降分 {retry_verdict.photoreal_score} ≤ "
                f"{baseline.verdict.photoreal_score}，保守退 baseline"
            ),
            retry_verdict=retry_verdict,
        )


class ForceRetryStrategy:
    """强选 retry 张，不调 jury（cost 极敏感场景）。

    SP1 严格 2 张候选；length≠2 抛 ValueError（spec line 577）。
    """

    def select(
        self,
        candidates: list[CandidateImage],
        jury_callable: Callable[[str], ViewVerdict],
        budget: "LoopBudget",
    ) -> SelectionResult:
        if len(candidates) != 2:
            raise ValueError(
                f"ForceRetryStrategy 期望 2 张候选（baseline + retry），实际 {len(candidates)}"
            )
        # force_retry 不二轮评分（spec §4.4 line 530）→ retry_verdict 必为 None
        return SelectionResult(
            pick=candidates[1],
            extra_jury_calls=0,
            rationale="force_retry: 强选 retry 不二轮评分",
            retry_verdict=None,
        )


STRATEGY_REGISTRY: dict[str, type[ScoreSelectStrategy]] = {
    "pick_max_jury": PickMaxJuryStrategy,
    "force_retry": ForceRetryStrategy,
}
