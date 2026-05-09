"""verdict.py 纯函数解析 — LLM 文本 → ViewVerdict + parse_anomalies (11 case)。"""

from __future__ import annotations

import json

from tools.jury.verdict import ViewVerdict, parse_view_verdict


_OK_RESPONSE = json.dumps(
    {
        "semantic_checks": {
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        "photoreal_score": 78,
        "reason": "金属铸件高光一致，背景虚化自然。",
    }
)


def test_standard_response_parses_clean() -> None:
    v = parse_view_verdict(_OK_RESPONSE, finish_reason="stop")
    assert v.parse_status == "ok"
    assert v.parse_anomalies == []
    assert v.semantic_checks["photorealistic"] is True
    assert v.photoreal_score == 78
    assert v.reason == "金属铸件高光一致，背景虚化自然。"
    assert v.verdict == "accepted"


def test_unicode_reason_preserved() -> None:
    body = json.dumps(
        {
            "semantic_checks": {
                k: True
                for k in [
                    "geometry_preserved",
                    "material_consistent",
                    "photorealistic",
                    "no_extra_parts",
                    "no_missing_parts",
                ]
            },
            "photoreal_score": 70,
            "reason": "中文 + 🎨 emoji 测试",
        }
    )
    v = parse_view_verdict(body, finish_reason="stop")
    assert "🎨" in v.reason


def test_boolean_field_non_bool_marks_anomaly() -> None:
    body = json.dumps(
        {
            "semantic_checks": {
                "geometry_preserved": "yes",
                "material_consistent": True,
                "photorealistic": True,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            "photoreal_score": 70,
            "reason": "x",
        }
    )
    v = parse_view_verdict(body, finish_reason="stop")
    assert "content_keys_mismatch" in v.parse_anomalies
    assert v.verdict == "needs_review"


def test_photoreal_score_below_zero_clamped() -> None:
    body = json.dumps(
        {
            "semantic_checks": {
                k: True
                for k in [
                    "geometry_preserved",
                    "material_consistent",
                    "photorealistic",
                    "no_extra_parts",
                    "no_missing_parts",
                ]
            },
            "photoreal_score": -5,
            "reason": "x",
        }
    )
    v = parse_view_verdict(body, finish_reason="stop")
    assert v.photoreal_score == 0
    assert "clamped" in v.parse_anomalies
    assert v.verdict == "preview"  # 0 < min 60


def test_photoreal_score_above_100_clamped() -> None:
    body = json.dumps(
        {
            "semantic_checks": {
                k: True
                for k in [
                    "geometry_preserved",
                    "material_consistent",
                    "photorealistic",
                    "no_extra_parts",
                    "no_missing_parts",
                ]
            },
            "photoreal_score": 150,
            "reason": "x",
        }
    )
    v = parse_view_verdict(body, finish_reason="stop")
    assert v.photoreal_score == 100
    assert "clamped" in v.parse_anomalies
    assert v.verdict == "accepted"  # 100 >= min 60


def test_photoreal_score_at_min_boundary_accepted() -> None:
    body = json.dumps(
        {
            "semantic_checks": {
                k: True
                for k in [
                    "geometry_preserved",
                    "material_consistent",
                    "photorealistic",
                    "no_extra_parts",
                    "no_missing_parts",
                ]
            },
            "photoreal_score": 60,
            "reason": "x",
        }
    )
    v = parse_view_verdict(body, finish_reason="stop")
    assert v.verdict == "accepted"  # = 边界 accepted


def test_reason_control_chars_stripped() -> None:
    body = json.dumps(
        {
            "semantic_checks": {
                k: True
                for k in [
                    "geometry_preserved",
                    "material_consistent",
                    "photorealistic",
                    "no_extra_parts",
                    "no_missing_parts",
                ]
            },
            "photoreal_score": 70,
            "reason": "abc\x00\x07def\x1bbad",
        }
    )
    v = parse_view_verdict(body, finish_reason="stop")
    assert "\x00" not in v.reason
    assert "\x1b" not in v.reason
    assert "reason_sanitized" in v.parse_anomalies


def test_reason_truncated_to_80() -> None:
    body = json.dumps(
        {
            "semantic_checks": {
                k: True
                for k in [
                    "geometry_preserved",
                    "material_consistent",
                    "photorealistic",
                    "no_extra_parts",
                    "no_missing_parts",
                ]
            },
            "photoreal_score": 70,
            "reason": "x" * 150,
        }
    )
    v = parse_view_verdict(body, finish_reason="stop")
    assert len(v.reason) <= 80
    assert "reason_sanitized" in v.parse_anomalies


def test_invalid_json_marks_content_not_json() -> None:
    v = parse_view_verdict("not a json", finish_reason="stop")
    assert "content_not_json" in v.parse_anomalies
    assert v.verdict == "needs_review"


def test_finish_reason_length_marks_invalid() -> None:
    body = json.dumps(
        {
            "semantic_checks": {
                k: True
                for k in [
                    "geometry_preserved",
                    "material_consistent",
                    "photorealistic",
                    "no_extra_parts",
                    "no_missing_parts",
                ]
            },
            "photoreal_score": 70,
            "reason": "x",
        }
    )
    v = parse_view_verdict(body, finish_reason="length")
    assert "finish_reason_invalid" in v.parse_anomalies
    assert v.verdict == "needs_review"


def test_multiple_anomalies_coexist() -> None:
    """reason_sanitized + clamped 共存仍 accepted（白名单内）。"""
    body = json.dumps(
        {
            "semantic_checks": {
                k: True
                for k in [
                    "geometry_preserved",
                    "material_consistent",
                    "photorealistic",
                    "no_extra_parts",
                    "no_missing_parts",
                ]
            },
            "photoreal_score": 150,
            "reason": "abc\x00def",
        }
    )
    v = parse_view_verdict(body, finish_reason="stop")
    assert "clamped" in v.parse_anomalies
    assert "reason_sanitized" in v.parse_anomalies
    assert v.verdict == "accepted"  # 二者都在白名单 + 5 bool 全 true + 100 >= 60


def test_view_verdict_dataclass_exposed() -> None:
    """ViewVerdict 必须从模块导出（symbol 检查）。"""
    assert ViewVerdict is not None
