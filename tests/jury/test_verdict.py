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


# v2.37.2 §11 #1 — _make_needs_review_verdict 6-key shape 一致性
# parametrize 覆盖 parse_view_verdict 3 个早返回 path 全部调用 _make_needs_review_verdict
import pytest


@pytest.mark.parametrize(
    "bad_input,expected_anomaly",
    [
        ("not json at all", "content_not_json"),
        ('"a plain string not dict"', "content_not_json"),
        ('{"no_semantic_checks_key": true}', "missing_content"),
    ],
)
def test_make_needs_review_verdict_returns_6_key_with_matches_spec_true(
    bad_input: str, expected_anomaly: str
) -> None:
    """v2.37.2 §11 #1：_make_needs_review_verdict 返回 6-key dict 含 matches_spec=True，
    与 normal path 形态一致；与 aggregate_run_verdict 的 .get('matches_spec', True) 默认等价。

    Parametrize 3 个 anomalies path 覆盖 parse_view_verdict line 67 / 73 / 79 三处早返回。
    """
    v = parse_view_verdict(bad_input, finish_reason="stop")
    assert v.parse_status == "ok"
    assert expected_anomaly in v.parse_anomalies
    assert v.verdict == "needs_review"
    # 6-key shape 锁
    assert set(v.semantic_checks.keys()) == {
        "geometry_preserved",
        "material_consistent",
        "photorealistic",
        "no_extra_parts",
        "no_missing_parts",
        "matches_spec",
    }
    # matches_spec=True 兜底语义（与 aggregate .get(default=True) 等价）
    assert v.semantic_checks["matches_spec"] is True
    # 其它 5 key 全 False（_make_needs_review_verdict 既有契约）
    assert v.semantic_checks["geometry_preserved"] is False
    assert v.semantic_checks["material_consistent"] is False
    assert v.semantic_checks["photorealistic"] is False
    assert v.semantic_checks["no_extra_parts"] is False
    assert v.semantic_checks["no_missing_parts"] is False
