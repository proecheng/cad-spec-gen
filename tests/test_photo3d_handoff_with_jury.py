"""photo3d-handoff --with-jury / --no-strict-jury 集成测试

spec: docs/superpowers/specs/2026-05-09-photo3d-jury-v2-handoff-integration-design.md v1.4
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# v1.4 §6.0.5 — 新文件顶部 module-scope autouse 复制 jury kill switch
@pytest.fixture(autouse=True)
def _disable_llm_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")


# === H1 / H1b / H1c 回归 + golden snapshot ===

@pytest.mark.regression
def test_h1_no_with_jury_golden_snapshot() -> None:
    """H1 — 不带 --with-jury 路径：v2.27.0 基线 fixture 不应有 jury_* 字段"""
    golden = json.loads(
        Path("tests/fixtures/photo3d_handoff_v2_27_0.json").read_text(encoding="utf-8")
    )
    assert "jury_handoff_status" not in golden, (
        "v2.27.0 基线不应有 jury_* 字段（@regression）"
    )
    assert "jury_status" not in golden
    assert "review_status" not in golden
    assert "enhance_review_path" not in golden
    assert "jury_estimated_usd" not in golden
    assert "jury_actual_usd" not in golden
    assert "jury_raw_exit" not in golden
    assert "review_raw_exit" not in golden
    # 同时守门 v2.27.0 字段集存在
    expected_keys = {
        "artifacts",
        "confirmed",
        "executed_action",
        "followup_action",
        "generated_at",
        "manual_action",
        "ordinary_user_message",
        "post_handoff_photo3d_run",
        "run_id",
        "schema_version",
        "selected_action",
        "source",
        "source_report",
        "status",
        "subsystem",
    }
    assert set(golden.keys()) == expected_keys, (
        f"golden snapshot keyset 漂移: {set(golden.keys()) ^ expected_keys}"
    )


def test_run_photo3d_handoff_accepts_with_jury_kwarg() -> None:
    """spec §3.2 — run_photo3d_handoff 签名 add-only 加 with_jury / no_strict_jury 参数"""
    import inspect

    from tools.photo3d_handoff import run_photo3d_handoff

    sig = inspect.signature(run_photo3d_handoff)
    assert "with_jury" in sig.parameters
    assert "no_strict_jury" in sig.parameters
    # 都是 keyword-only with default False
    assert sig.parameters["with_jury"].default is False
    assert sig.parameters["no_strict_jury"].default is False
    assert sig.parameters["with_jury"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["no_strict_jury"].kind == inspect.Parameter.KEYWORD_ONLY


def test_clamp_review_exit_mapping() -> None:
    """spec §3.3.1 + §6.2 — clamp_review_exit 映射钉死"""
    from tools.photo3d_handoff import clamp_review_exit
    assert clamp_review_exit(0) == 0
    assert clamp_review_exit(1) == 20
    assert clamp_review_exit(2) == 21
    assert clamp_review_exit(3) == 22
    assert clamp_review_exit(4) == 23
    assert clamp_review_exit(137) == 23
    assert clamp_review_exit(-1) == 23


def test_validate_run_id_format_rejects_traversal() -> None:
    """spec §3.4 inv 10 + §6.2 — run_id 格式正则守门"""
    from tools.photo3d_handoff import validate_run_id_format
    assert validate_run_id_format("20260509-123456") is True
    assert validate_run_id_format("run_001") is True
    assert validate_run_id_format("a") is True
    assert validate_run_id_format("../etc/passwd") is False
    assert validate_run_id_format("..\\windows\\system32") is False
    assert validate_run_id_format("") is False
    assert validate_run_id_format("a" * 65) is False
    assert validate_run_id_format("run id") is False
    assert validate_run_id_format("run/id") is False
