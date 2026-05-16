"""tests/jury/test_verdict_below_threshold.py — §11-N6 photoreal<60 升 needs_review TDD。"""

from __future__ import annotations

import json


from tools.jury.verdict import parse_view_verdict


def _make_payload(photoreal: int, *, finish_reason: str = "stop") -> str:
    """构造 LLM raw response JSON payload（用 _REQUIRED_BOOL_KEYS 真实 key）。"""
    return json.dumps({
        "photoreal_score": photoreal,
        "semantic_checks": {
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        "reason": "test reason",
        "finish_reason": finish_reason,
    })


def test_photoreal_59_below_threshold_becomes_needs_review() -> None:
    """T1 — photoreal=59 (边界 - 1) → verdict=needs_review + anomaly=photoreal_below_threshold。"""
    v = parse_view_verdict(_make_payload(59))
    assert v.verdict == "needs_review"
    assert "photoreal_below_threshold" in v.parse_anomalies


def test_photoreal_60_at_threshold_remains_accepted() -> None:
    """T2 — photoreal=60 (边界) → verdict=accepted（不变）。"""
    v = parse_view_verdict(_make_payload(60))
    assert v.verdict == "accepted"
    assert "photoreal_below_threshold" not in v.parse_anomalies


def test_photoreal_35_gisbot_baseline_becomes_needs_review() -> None:
    """T3 — photoreal=35 (GISBOT 实测最低值) → verdict=needs_review。"""
    v = parse_view_verdict(_make_payload(35))
    assert v.verdict == "needs_review"
    assert "photoreal_below_threshold" in v.parse_anomalies
    assert v.photoreal_score == 35


def test_photoreal_45_gisbot_high_becomes_needs_review() -> None:
    """T4 — photoreal=45 (GISBOT 实测最高值) → verdict=needs_review。"""
    v = parse_view_verdict(_make_payload(45))
    assert v.verdict == "needs_review"
    assert "photoreal_below_threshold" in v.parse_anomalies
