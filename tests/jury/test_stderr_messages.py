"""中文人话提示模板覆盖测试 — 每 exit code × status 都填 placeholder 实际值。"""

from __future__ import annotations

import pytest

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


# spec §5.2.1 钉死的 14 个 (exit_code, error_kind, context) 三元组（含 awaiting_confirmation_with_jury）
HANDOFF_ERROR_KINDS = [
    (10, "handoff_jury_preview", {"failed_n": 2, "score": 60, "min_score": 75, "report_path": "/r/p", "mode": "strict"}),
    (0, "handoff_jury_preview", {"failed_n": 2, "score": 60, "min_score": 75, "report_path": "/r/p", "mode": "warning"}),
    (11, "handoff_jury_needs_review", {"failed_views": ["v1"], "vendor_request_id": None, "report_path": "/r/p", "mode": "strict"}),
    (12, "handoff_jury_blocked", {"report_path": "/r/p"}),
    (4, "handoff_jury_lock_busy", {"lock_mtime_minutes_ago": 5, "lock_path": "/r/.jury.lock"}),
    (99, "handoff_jury_internal_error", {"redacted_traceback": "Traceback..."}),
    (2, "handoff_jury_config_error", {"config_path": "~/.claude/cad_jury_config.json"}),
    (3, "handoff_jury_cost_over_budget", {"estimated_usd": 0.04, "budget_usd": 0.02, "n_views": 4}),
    (20, "handoff_review_failed", {"review_raw_exit": 1, "report_path": "/r/p"}),
    (13, "handoff_review_input_missing", {"review_input_path": "/r/p", "reason": "not_found"}),
    (23, "handoff_review_input_corrupt", {"review_input_path": "/r/p", "parse_error": "Expecting value"}),
    (25, "handoff_unexpected_jury_exit", {"raw_exit": 137}),
    (24, "handoff_handoff_lock_busy", {"lock_mtime_minutes_ago": 3, "lock_path": "/r/.handoff.lock"}),
    (2, "handoff_jury_preflight_config_missing", {"config_path": "~/.claude/cad_jury_config.json"}),
    (0, "handoff_awaiting_confirmation_with_jury", {"argv_with_confirm": "python cad_pipeline.py photo3d-handoff --subsystem X --with-jury --confirm"}),
]


@pytest.mark.parametrize("exit_code,error_kind,context", HANDOFF_ERROR_KINDS)
def test_handoff_error_kinds_no_unfilled_placeholders(exit_code, error_kind, context):
    """spec §6.2 — 13 个 handoff_* error_kind 模板渲染无 {xxx} 残留"""
    out = format_stderr_message(exit_code=exit_code, error_kind=error_kind, context=context)
    import re
    assert re.search(r"\{[a-zA-Z_]+\}", out) is None, f"unfilled placeholder in {error_kind}: {out!r}"
    assert out.strip()


@pytest.mark.parametrize("exit_code,error_kind,context", HANDOFF_ERROR_KINDS)
def test_handoff_error_kinds_dispatch_complete(exit_code, error_kind, context):
    """spec §6.2 — 用每个 error_kind 调 format_stderr_message，输出非 fallback 兜底"""
    out = format_stderr_message(exit_code=exit_code, error_kind=error_kind, context=context)
    assert f"（{error_kind}）" not in out, f"fell through to fallback for {error_kind}: {out!r}"


def test_handoff_templates_no_secret_leakage():
    """spec §5.3 — handoff_* 模板源码中无 api_key / base_url / model 字面量作为 placeholder"""
    import inspect
    from tools.jury import stderr_messages
    src = inspect.getsource(stderr_messages.format_stderr_message)
    for forbidden in ("{api_key}", "{base_url}", "{model}"):
        assert forbidden not in src, f"forbidden placeholder {forbidden!r} found in format_stderr_message"
