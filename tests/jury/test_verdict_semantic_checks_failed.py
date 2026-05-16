"""tests/jury/test_verdict_semantic_checks_failed.py — §11-N6 改动 1e TDD (rev 4 真 vendor 实测 fix)。

真 vendor 实测发现 elif 链顺序漏洞：
- vision LLM 对低分图一致给 photorealistic=False（5 bool 之一）
- elif line 158 'not all(checks)' 先吃 → verdict=preview
- 改动 1 line 161 'score<min' 永远 unreachable → 改动 1 NO-OP

本测试集 verify line 158 'not all(checks)' 也升 needs_review + 加 semantic_checks_failed anomaly。
"""

from __future__ import annotations

import json

from tools.jury.verdict import parse_view_verdict


def _make_payload(*, photoreal: int = 80, photorealistic_check: bool = True) -> str:
    """构造 LLM raw response。score 默认 80（避免 photoreal<60 干扰），仅切换 photorealistic check。"""
    return json.dumps(
        {
            "photoreal_score": photoreal,
            "semantic_checks": {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": photorealistic_check,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "reason": "test reason",
            "finish_reason": "stop",
        }
    )


def test_photorealistic_false_high_score_becomes_needs_review() -> None:
    """T-checks-fail-high-score — photoreal=80 + photorealistic=False → verdict=needs_review + anomaly=semantic_checks_failed。"""
    v = parse_view_verdict(_make_payload(photoreal=80, photorealistic_check=False))
    assert v.verdict == "needs_review"
    assert "semantic_checks_failed" in v.parse_anomalies


def test_all_checks_true_high_score_remains_accepted() -> None:
    """T-checks-all-true-anchor — 5 bool 全 True + score=80 → accepted (回归 anchor)。"""
    v = parse_view_verdict(_make_payload(photoreal=80, photorealistic_check=True))
    assert v.verdict == "accepted"
    assert "semantic_checks_failed" not in v.parse_anomalies


def test_photorealistic_false_low_score_anomaly_priority() -> None:
    """T-checks-fail-low-score — photoreal=35 + photorealistic=False → 哪个 anomaly 优先？

    elif 链 line 158 'not all(checks)' 比 line 161 'score<min' 优先 →
    应得 semantic_checks_failed（先匹配的 anomaly）。
    photoreal_below_threshold 不被加（line 161 unreachable when not all(checks)）。
    """
    v = parse_view_verdict(_make_payload(photoreal=35, photorealistic_check=False))
    assert v.verdict == "needs_review"
    assert "semantic_checks_failed" in v.parse_anomalies
    # photoreal_below_threshold 因 elif 顺序不被加
    assert "photoreal_below_threshold" not in v.parse_anomalies
