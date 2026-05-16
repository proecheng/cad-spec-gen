"""tests/jury_loop/test_orchestrator_photoreal_retry.py — §11-N6 改动 1b BLOCKER fix TDD。

测试 orchestrator.py:199 photoreal_below_threshold 进 retry 白名单。
"""

from __future__ import annotations

import json

from tools.jury_loop.orchestrator import _parse_verdict_with_anomaly_path


def _make_view_verdict_payload(photoreal: int, anomaly: str | None = None) -> str:
    """构造 LLM single-view JSON。

    注意：semantic_checks 用真值 _REQUIRED_BOOL_KEYS — Task 1 plan-drift 教训
    geometry_preserved / material_consistent / photorealistic / no_extra_parts / no_missing_parts
    """
    payload: dict[str, object] = {
        "photoreal_score": photoreal,
        "semantic_checks": {
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        "reason": "test reason",
        "finish_reason": "stop",
    }
    if anomaly == "matches_spec_failed":
        payload["features_status"] = [{"feature_id": "f1", "visible": False}]
    return json.dumps(payload)


def test_photoreal_below_threshold_returns_verdict_for_retry() -> None:
    """T-orch-photoreal-retry — photoreal<60 走 retry path（rev 3 BLOCKER fix）。"""
    raw_json = _make_view_verdict_payload(35)

    result = _parse_verdict_with_anomaly_path(raw_json)

    assert result is not None
    verdict, anomaly_path = result
    assert verdict is not None, "photoreal_below_threshold 应保留 verdict 走 retry"
    assert anomaly_path == "photoreal_below_threshold"
    assert verdict.photoreal_score == 35


def test_matches_spec_failed_still_returns_retry_verdict() -> None:
    """T-orch-matches-spec — matches_spec_failed 路径不动（回归 anchor）。"""
    raw_json = _make_view_verdict_payload(80, anomaly="matches_spec_failed")

    result = _parse_verdict_with_anomaly_path(raw_json)

    assert result is not None
    verdict, anomaly_path = result
    assert verdict is not None
    assert anomaly_path == "matches_spec_failed"


def test_parse_failed_still_returns_jury_unavailable() -> None:
    """T-orch-parse-fail — 解析失败仍走 jury_unavailable（回归 anchor）。"""
    raw_json = "not a JSON"

    result = _parse_verdict_with_anomaly_path(raw_json)

    assert result is not None
    verdict, anomaly_path = result
    assert verdict is None  # 不可信不走 retry
    assert anomaly_path == "needs_review"


def test_semantic_checks_failed_returns_verdict_for_retry() -> None:
    """T-orch-semantic-checks-retry (rev 4 真 vendor 实测 fix) — semantic_checks_failed 走 retry path。"""
    # photoreal=80 但 photorealistic=False → semantic_checks_failed anomaly
    payload = {
        "photoreal_score": 80,
        "semantic_checks": {
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": False,  # ← 触发 not all(checks)
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        "reason": "test reason",
        "finish_reason": "stop",
    }
    raw_json = json.dumps(payload)

    result = _parse_verdict_with_anomaly_path(raw_json)

    assert result is not None
    verdict, anomaly_path = result
    assert verdict is not None, "semantic_checks_failed 应保留 verdict 走 retry"
    assert anomaly_path == "semantic_checks_failed"
