"""中文人话提示模板覆盖测试 — 每 exit code × status 都填 placeholder 实际值。"""

from __future__ import annotations

from tools.jury.stderr_messages import format_stderr_message


def test_accepted_template() -> None:
    msg = format_stderr_message(
        exit_code=0,
        status="accepted",
        context={
            "actual_cost_usd": 0.030,
            "jury_review_input_abs_path": "/p/jri.json",
        },
    )
    assert "0.030" in msg or "0.03" in msg
    assert "/p/jri.json" in msg
    assert "{" not in msg  # 无未填 placeholder


def test_preview_template() -> None:
    msg = format_stderr_message(
        exit_code=0,
        status="preview",
        context={
            "n_failed": 2,
            "total": 6,
            "photo3d_jury_report_abs_path": "/p/r.json",
        },
    )
    assert "2/6" in msg or "2 / 6" in msg
    assert "/p/r.json" in msg
    assert "{" not in msg


def test_needs_review_includes_fallback_id() -> None:
    msg = format_stderr_message(
        exit_code=0,
        status="needs_review",
        context={
            "n_failed": 1,
            "total": 6,
            "error_kinds": "auth_failed",
            "actual_cost_usd": 0.025,
            "subsystem": "lifting_platform",
            "fallback_id": "gpt-4o-native",
        },
    )
    assert "fallback_id" not in msg  # placeholder 名不应出现
    assert "gpt-4o-native" in msg
    assert "lifting_platform" in msg


def test_blocked_first_blocking_code() -> None:
    msg = format_stderr_message(
        exit_code=1,
        status="blocked",
        context={"first_blocking_code": "subsystem_mismatch", "subsystem": "X"},
    )
    assert "subsystem_mismatch" in msg
    assert "{" not in msg


def test_blocked_freeze_drift_emphasizes_cost() -> None:
    msg = format_stderr_message(
        exit_code=1,
        status="blocked",
        context={"first_blocking_code": "freeze_drift", "actual_cost_usd": 0.030},
    )
    assert "0.030" in msg or "0.03" in msg
    assert "已花费" in msg or "cost" in msg.lower()


def test_config_schema_error() -> None:
    msg = format_stderr_message(
        exit_code=2,
        error_kind="schema_version_invalid",
        context={"actual": 5},
    )
    assert "5" in msg
    assert "schema_version" in msg.lower() or "1" in msg


def test_config_profile_id_invalid() -> None:
    msg = format_stderr_message(
        exit_code=2,
        error_kind="profile_id_invalid",
        context={
            "bad_id": "-foo",
            "first_bad_char": "-",
            "sanitized_candidate": "_foo",
        },
    )
    assert "-foo" in msg
    assert "_foo" in msg


def test_config_path_external_no_allow() -> None:
    msg = format_stderr_message(
        exit_code=2,
        error_kind="config_path_external",
        context={"abs": "/external/path.json"},
    )
    assert "/external/path.json" in msg
    assert "--allow-external-config" in msg


def test_cost_over_budget() -> None:
    msg = format_stderr_message(
        exit_code=3,
        error_kind="budget_exceeded",
        context={
            "estimated_cost_usd": 0.6,
            "budget_per_run_usd": 0.1,
            "n_views": 6,
            "cost_per_call_usd": 0.1,
        },
    )
    assert "0.6" in msg
    assert "0.1" in msg
    assert "--confirm-cost" in msg


def test_lock_busy() -> None:
    msg = format_stderr_message(
        exit_code=4,
        error_kind="lock_busy",
        context={"held_pid": 12345, "age_seconds": 30},
    )
    assert "12345" in msg
    assert "30" in msg


def test_internal_error() -> None:
    msg = format_stderr_message(
        exit_code=99,
        error_kind="internal",
        context={"exception_type": "RuntimeError"},
    )
    assert "RuntimeError" in msg
    assert "issue" in msg.lower() or "提" in msg
