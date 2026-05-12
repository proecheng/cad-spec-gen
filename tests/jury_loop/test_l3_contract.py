"""SP1 CP-8 Task 8.1：L3 契约测试 — schema 字段集锁 + ENHANCEMENT_REPORT additive-only 兼容性。

锁定下游消费方依赖的字段集（spec §4.4 sidecar / §7 loop_summary），防 SP2-5 演进破契约：
- sidecar `<view>_enhance_meta.json` 字段集 + 顺序（spec §4.4，additive-only）
- ENHANCEMENT_REPORT.loop_summary 字段集 + 顺序（spec §7，headline 三数字置顶）
- photo3d_autopilot 旧解析器读含 loop_summary 的 v1 报告不破（"透明扩展"，spec §N-7）
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.enhance_consistency import _aggregate_loop_summary
from tools.jury_loop import metadata


# ════════════════════════════════════════════════════════════════════════════
# sidecar `<view>_enhance_meta.json` 字段集 + 顺序契约（spec §4.4）
# ════════════════════════════════════════════════════════════════════════════

#: spec §4.4 锁定的 sidecar 顶层字段集（与 metadata._FIELD_ORDER 一致；additive-only）。
_EXPECTED_SIDECAR_FIELDS = (
    "$schema_version", "view", "backend", "loop_eligible", "loop_status",
    "loop_skipped_reason", "delivered_kind", "baseline", "retry", "tags_parsed",
    "rules_hit", "rules_missed_tags", "llm_fallback_used", "prompt_addons_applied",
    "param_overrides_applied", "user_friendly_summary", "loop_status_zh",
    "retry_score_delta", "delivered_score_delta", "extra_cost_usd", "warnings", "errors",
)


def test_sidecar_field_order_constant_matches_spec() -> None:
    """metadata._FIELD_ORDER 必须与 spec §4.4 锁定的字段集 + 顺序一字不差。"""
    assert metadata._FIELD_ORDER == _EXPECTED_SIDECAR_FIELDS


def test_sidecar_written_field_set_and_order(tmp_path: Path) -> None:
    """write_sidecar 产出的 JSON 顶层 key 集 + 顺序锁死。"""
    path = metadata.write_sidecar(
        view="V1",
        render_dir=tmp_path,
        backend="gemini",
        loop_status="above_threshold",
    )
    written = json.loads(path.read_text(encoding="utf-8"))
    assert tuple(written.keys()) == _EXPECTED_SIDECAR_FIELDS
    assert written["$schema_version"] == 1


def test_sidecar_delivered_retry_field_set_unchanged(tmp_path: Path) -> None:
    """delivered_retry 形态（含 retry 子段）字段集与 above_threshold 形态一致（additive-only）。"""
    path = metadata.write_sidecar(
        view="V2",
        render_dir=tmp_path,
        backend="gemini",
        loop_status="delivered_retry",
        delivered_kind="retry",
        baseline={"image_path": "V2_enhanced_baseline.jpg", "photoreal_score": 58},
        retry={"image_path": "V2_enhanced_retry.jpg", "photoreal_score": 78},
        retry_score_delta=20,
        delivered_score_delta=20,
        extra_cost_usd=0.18,
    )
    written = json.loads(path.read_text(encoding="utf-8"))
    assert tuple(written.keys()) == _EXPECTED_SIDECAR_FIELDS


# ════════════════════════════════════════════════════════════════════════════
# ENHANCEMENT_REPORT.loop_summary 字段集 + 顺序契约（spec §7）
# ════════════════════════════════════════════════════════════════════════════

#: spec §7 锁定的 loop_summary 顶层字段集 + 顺序（headline + user_friendly_summary 紧随
#: $schema_version / loop_type；详细统计后置）。
_EXPECTED_LOOP_SUMMARY_FIELDS = (
    "$schema_version", "loop_type", "headline", "user_friendly_summary",
    "n_views", "loop_eligible_views", "delivered_baseline_count",
    "delivered_retry_count", "skipped_count", "skipped_reasons",
    "total_retries", "extra_cost_usd", "score_gain_avg", "score_gain_total",
)
_EXPECTED_HEADLINE_FIELDS = ("improved_views", "score_gain_total", "extra_cost_cny")


def _build_loop_summary(tmp_path: Path) -> dict[str, Any]:
    """跑 _aggregate_loop_summary 得到一个真实 loop_summary dict。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    (project_root / "pipeline_config.json").write_text(
        json.dumps({"enhance": {"jury_loop": {"enabled": True}}}), encoding="utf-8",
    )
    for view, status, kind, delta, cost in [
        ("V1", "delivered_retry", "retry", 20, 0.18),
        ("V2", "above_threshold", "baseline", 0, 0.0),
        ("V3", "jury_unavailable", "baseline", 0, 0.0),
    ]:
        (render_dir / f"{view}_enhance_meta.json").write_text(
            json.dumps({
                "$schema_version": 1, "view": view, "loop_status": status,
                "delivered_kind": kind, "loop_eligible": True,
                "delivered_score_delta": delta, "extra_cost_usd": cost,
            }),
            encoding="utf-8",
        )
    summary = _aggregate_loop_summary(project_root, render_dir)
    assert summary is not None
    return summary


def test_loop_summary_field_set_and_order(tmp_path: Path) -> None:
    """loop_summary 顶层 key 集 + 顺序锁死（spec §7）。"""
    summary = _build_loop_summary(tmp_path)
    assert tuple(summary.keys()) == _EXPECTED_LOOP_SUMMARY_FIELDS


def test_loop_summary_headline_field_set_and_order(tmp_path: Path) -> None:
    """headline 子段 = improved_views / score_gain_total / extra_cost_cny（M-7 三数字置顶）。"""
    summary = _build_loop_summary(tmp_path)
    assert tuple(summary["headline"].keys()) == _EXPECTED_HEADLINE_FIELDS


def test_loop_summary_schema_version_and_loop_type(tmp_path: Path) -> None:
    """$schema_version=1 / loop_type='single_retry'（SP1 锁定；SP3 多 sample 才出 multi_sample）。"""
    summary = _build_loop_summary(tmp_path)
    assert summary["$schema_version"] == 1
    assert summary["loop_type"] == "single_retry"


def test_loop_summary_value_types(tmp_path: Path) -> None:
    """字段值类型契约：计数 int / cost float / reasons dict / summary str。"""
    summary = _build_loop_summary(tmp_path)
    for key in ("n_views", "loop_eligible_views", "delivered_baseline_count",
                "delivered_retry_count", "skipped_count", "total_retries",
                "score_gain_total"):
        assert isinstance(summary[key], int), f"{key} 应为 int"
    assert isinstance(summary["extra_cost_usd"], float)
    assert isinstance(summary["score_gain_avg"], float)
    assert isinstance(summary["skipped_reasons"], dict)
    assert isinstance(summary["user_friendly_summary"], str)
    assert isinstance(summary["headline"]["extra_cost_cny"], float)


# ════════════════════════════════════════════════════════════════════════════
# ENHANCEMENT_REPORT additive-only 兼容性回归（spec §N-7：autopilot 透明扩展）
# ════════════════════════════════════════════════════════════════════════════


def test_autopilot_compact_summary_tolerates_loop_summary() -> None:
    """photo3d_autopilot._compact_enhancement_summary 读含 loop_summary 的报告不破，
    且不把 loop_summary 透出（autopilot 状态机保持透明，spec §N-7）。"""
    from tools.photo3d_autopilot import _compact_enhancement_summary

    base_report = {
        "schema_version": 1, "status": "accepted", "delivery_status": "accepted",
        "ordinary_user_message": "ok", "render_manifest": "renders/render_manifest.json",
        "view_count": 3, "enhanced_view_count": 3, "blocking_reasons": [],
    }
    report_with_loop = {
        **base_report,
        "loop_summary": {
            "$schema_version": 1, "loop_type": "single_retry",
            "headline": {"improved_views": 1, "score_gain_total": 20, "extra_cost_cny": 1.3},
            "user_friendly_summary": "...", "n_views": 3,
        },
    }
    out_without = _compact_enhancement_summary(base_report, "renders/ENHANCEMENT_REPORT.json")
    out_with = _compact_enhancement_summary(report_with_loop, "renders/ENHANCEMENT_REPORT.json")
    # 透明扩展：含/不含 loop_summary 时 autopilot 摘要输出完全一致
    assert out_with == out_without
    assert "loop_summary" not in out_with


def test_build_enhancement_report_loop_summary_is_additive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENHANCEMENT_REPORT 加 loop_summary 后，既有顶层字段集不变（additive-only，§4.4 约束）。"""
    from tools import enhance_consistency

    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    manifest = {
        "schema_version": 1, "run_id": "r1", "subsystem": "demo",
        "render_dir_abs_resolved": str(render_dir), "sources": [],
    }
    # 无 loop_summary 版（aggregate 返 None）
    monkeypatch.setattr(enhance_consistency, "_aggregate_loop_summary", lambda *_a, **_k: None)
    report_without = enhance_consistency.build_enhancement_report(tmp_path, manifest)
    # 有 loop_summary 版
    monkeypatch.setattr(
        enhance_consistency, "_aggregate_loop_summary",
        lambda *_a, **_k: {"$schema_version": 1, "loop_type": "single_retry"},
    )
    report_with = enhance_consistency.build_enhancement_report(tmp_path, manifest)
    # 加段只新增 loop_summary key，其余字段集一字不变
    assert set(report_with.keys()) - set(report_without.keys()) == {"loop_summary"}
    assert set(report_without.keys()) - set(report_with.keys()) == set()
