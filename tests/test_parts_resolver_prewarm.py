"""PartsResolver.prewarm() 测试（Task 14.6 / Task 10）。

关键不变量：rule matching 在 resolver 层做（不在 adapter 层）；
adapter.prewarm 收到的是 (query, rule.spec) tuple list。
"""

from __future__ import annotations

from adapters.parts.base import PartsAdapter
from parts_resolver import PartQuery, PartsResolver, ResolveResult


class _RecordingAdapter(PartsAdapter):
    """Record prewarm() calls for assertion."""

    name = "test_adapter"

    def __init__(self):
        self.prewarm_calls = []

    def is_available(self):
        return True, None

    def can_resolve(self, q):
        return True

    def resolve(self, q, spec):
        return ResolveResult(status="miss", kind="miss", adapter=self.name)

    def probe_dims(self, q, spec):
        return None

    def prewarm(self, candidates):
        self.prewarm_calls.append(list(candidates))


def _make_query(part_no: str, name_cn: str = "", category: str = "") -> PartQuery:
    return PartQuery(
        part_no=part_no,
        name_cn=name_cn,
        material="",
        category=category,
        make_buy="",
    )


class TestPartsResolverPrewarm:
    def test_prewarm_returns_none(self):
        """fire-and-forget 契约：返 None."""
        adapter = _RecordingAdapter()
        resolver = PartsResolver(registry={"mappings": []}, adapters=[adapter])
        result = resolver.prewarm([])
        assert result is None

    def test_prewarm_dispatches_only_matching_adapter(self):
        """rule matching 在 resolver 层：query 命中 test_adapter rule → adapter 收到 candidate."""
        adapter = _RecordingAdapter()
        resolver = PartsResolver(
            registry={
                "mappings": [
                    {
                        "match": {"category": "fastener"},
                        "adapter": "test_adapter",
                        "spec": {"rule_specific": "value"},
                    },
                ],
            },
            adapters=[adapter],
        )
        q1 = _make_query("P1", category="fastener")
        q2 = _make_query("P2", category="bearing")  # 不命中 fastener rule

        resolver.prewarm([q1, q2])

        # adapter.prewarm 调用一次；candidates 只含 q1（命中）+ rule.spec
        assert len(adapter.prewarm_calls) == 1
        candidates = adapter.prewarm_calls[0]
        assert len(candidates) == 1
        candidate_q, candidate_spec = candidates[0]
        assert candidate_q.part_no == "P1"
        assert candidate_spec == {"rule_specific": "value"}

    def test_prewarm_first_hit_wins_per_query(self):
        """per query first-hit 原则：同 query 不会被多个 rule 重复派发."""
        adapter = _RecordingAdapter()
        resolver = PartsResolver(
            registry={
                "mappings": [
                    # 第一条命中 → 后面 rule 不再考虑
                    {"match": {"category": "fastener"},
                     "adapter": "test_adapter", "spec": {"first": True}},
                    {"match": {"category": "fastener"},
                     "adapter": "test_adapter", "spec": {"second": True}},
                ],
            },
            adapters=[adapter],
        )
        resolver.prewarm([_make_query("P1", category="fastener")])

        candidates = adapter.prewarm_calls[0]
        assert len(candidates) == 1
        _, spec = candidates[0]
        assert spec == {"first": True}  # first-hit-wins

    def test_prewarm_skips_adapter_with_no_candidates(self):
        """无 query 命中此 adapter 的 rule → adapter.prewarm 不调."""
        adapter = _RecordingAdapter()
        resolver = PartsResolver(
            registry={
                "mappings": [
                    {"match": {"category": "fastener"},
                     "adapter": "test_adapter", "spec": {}},
                ],
            },
            adapters=[adapter],
        )
        resolver.prewarm([_make_query("P1", category="bearing")])  # 不命中
        assert adapter.prewarm_calls == []

    def test_prewarm_adapter_exception_does_not_abort(self):
        """单 adapter.prewarm 抛异常 → resolver.prewarm 不抛 / 不阻 codegen."""

        class _ExplodingAdapter(_RecordingAdapter):
            name = "exploding"

            def prewarm(self, candidates):
                raise RuntimeError("simulated crash")

        boom = _ExplodingAdapter()
        resolver = PartsResolver(
            registry={
                "mappings": [
                    {"match": {"category": "fastener"},
                     "adapter": "exploding", "spec": {}},
                ],
            },
            adapters=[boom],
        )
        # 关键断言：不抛异常即可（好-adapter 在 first-hit-wins 后 query 已绑定 exploding，
        # 故不会再调 good — 这是 first-hit 副作用，本测试不验证）
        resolver.prewarm([_make_query("P1", category="fastener")])
