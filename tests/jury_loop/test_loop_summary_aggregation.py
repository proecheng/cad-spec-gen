"""CP-7 Task 7.1.3：ENHANCEMENT_REPORT.loop_summary 聚合单元测试。

测试 `_aggregate_loop_summary` 直接行为 + `build_enhancement_report` 集成。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.enhance_consistency import _aggregate_loop_summary


def _write_sidecar(render_dir: Path, view: str, **fields: Any) -> Path:
    """写一份 `<view>_enhance_meta.json` sidecar。"""
    payload = {"$schema_version": 1, "view": view, **fields}
    p = render_dir / f"{view}_enhance_meta.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _write_pipeline_config(project_root: Path, enabled: bool = True) -> None:
    """写最小 pipeline_config.json 含 enhance.jury_loop.enabled。"""
    pcfg = {"enhance": {"jury_loop": {"enabled": enabled}}}
    (project_root / "pipeline_config.json").write_text(
        json.dumps(pcfg), encoding="utf-8",
    )


# ── 门控：enabled=false / 无 sidecar → None ─────────────────────────────────


def test_returns_none_when_jury_loop_disabled(tmp_path: Path) -> None:
    """OPS-MAJOR-2：enabled=false → 返 None（整段不写入）。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    _write_pipeline_config(project_root, enabled=False)
    _write_sidecar(render_dir, "V1", loop_status="delivered_retry", delivered_kind="retry")
    assert _aggregate_loop_summary(project_root, render_dir) is None


def test_returns_none_when_no_sidecars(tmp_path: Path) -> None:
    """enabled=true 但 render_dir 无 sidecar → 返 None（该次跑没经过 hook）。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    _write_pipeline_config(project_root, enabled=True)
    assert _aggregate_loop_summary(project_root, render_dir) is None


def test_returns_none_when_pipeline_config_missing_uses_default_enabled(
    tmp_path: Path,
) -> None:
    """无 pipeline_config.json → fall back DEFAULT_JURY_LOOP_DICT (enabled=True)；
    但 render_dir 无 sidecar → 仍返 None。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    # 不写 pipeline_config.json
    assert _aggregate_loop_summary(project_root, render_dir) is None


# ── 聚合：混合状态 ──────────────────────────────────────────────────────────


def test_aggregates_mixed_view_states(tmp_path: Path) -> None:
    """3 视角混合：1 delivered_retry / 1 above_threshold / 1 jury_unavailable。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    _write_pipeline_config(project_root, enabled=True)
    _write_sidecar(
        render_dir, "V1",
        loop_status="delivered_retry", delivered_kind="retry",
        loop_eligible=True, delivered_score_delta=20, extra_cost_usd=0.18,
    )
    _write_sidecar(
        render_dir, "V2",
        loop_status="above_threshold", delivered_kind="baseline",
        loop_eligible=True, delivered_score_delta=0, extra_cost_usd=0.0,
        loop_skipped_reason=None,
    )
    _write_sidecar(
        render_dir, "V3",
        loop_status="jury_unavailable", delivered_kind="baseline",
        loop_eligible=True, delivered_score_delta=0, extra_cost_usd=0.0,
        loop_skipped_reason="jury subprocess returned non-zero",
    )

    summary = _aggregate_loop_summary(project_root, render_dir)
    assert summary is not None
    assert summary["n_views"] == 3
    assert summary["loop_eligible_views"] == 3
    assert summary["delivered_retry_count"] == 1
    assert summary["delivered_baseline_count"] == 1  # only V2 (above_threshold)
    assert summary["skipped_count"] == 1  # V3 (jury_unavailable)
    assert summary["skipped_reasons"] == {"jury_unavailable": 1}
    assert summary["total_retries"] == 1
    assert summary["extra_cost_usd"] == 0.18
    assert summary["score_gain_total"] == 20
    assert summary["score_gain_avg"] == 20.0  # 20 / 1 retry view
    assert summary["headline"]["improved_views"] == 1
    assert summary["headline"]["score_gain_total"] == 20
    assert summary["headline"]["extra_cost_cny"] == pytest.approx(0.18 * 7.2, abs=0.01)
    assert "3 视角中" in summary["user_friendly_summary"]
    assert "20 分" in summary["user_friendly_summary"]


def test_field_order_matches_spec_section_7(tmp_path: Path) -> None:
    """spec §7 字段顺序：$schema_version / loop_type / headline / user_friendly_summary 置顶。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    _write_pipeline_config(project_root, enabled=True)
    _write_sidecar(
        render_dir, "V1",
        loop_status="delivered_retry", delivered_kind="retry",
        loop_eligible=True, delivered_score_delta=10, extra_cost_usd=0.05,
    )
    summary = _aggregate_loop_summary(project_root, render_dir)
    assert summary is not None
    keys = list(summary.keys())
    assert keys[:4] == ["$schema_version", "loop_type", "headline", "user_friendly_summary"]
    assert summary["loop_type"] == "single_retry"
    assert summary["$schema_version"] == 1


def test_handles_corrupt_sidecar(tmp_path: Path) -> None:
    """损坏 sidecar 不抛，按剩余好的聚合。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    _write_pipeline_config(project_root, enabled=True)
    _write_sidecar(
        render_dir, "V1",
        loop_status="delivered_retry", delivered_kind="retry",
        delivered_score_delta=15, extra_cost_usd=0.1,
    )
    (render_dir / "V2_enhance_meta.json").write_text("{not json", encoding="utf-8")

    summary = _aggregate_loop_summary(project_root, render_dir)
    assert summary is not None
    assert summary["n_views"] == 1  # 只 V1 被算入
    assert summary["delivered_retry_count"] == 1


def test_extra_cost_cny_rounded_two_decimals(tmp_path: Path) -> None:
    """extra_cost_cny = round(extra_cost_usd * 7.2, 2)（spec §7 M-8）。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    _write_pipeline_config(project_root, enabled=True)
    _write_sidecar(
        render_dir, "V1",
        loop_status="delivered_retry", delivered_kind="retry",
        delivered_score_delta=5, extra_cost_usd=0.25,
    )
    summary = _aggregate_loop_summary(project_root, render_dir)
    assert summary is not None
    assert summary["headline"]["extra_cost_cny"] == round(0.25 * 7.2, 2)


def test_all_baseline_no_retry_score_gain_avg_is_zero(tmp_path: Path) -> None:
    """所有视角都接受 baseline，无 retry → score_gain_avg=0（防 ZeroDivisionError）。"""
    project_root = tmp_path
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    _write_pipeline_config(project_root, enabled=True)
    _write_sidecar(
        render_dir, "V1",
        loop_status="above_threshold", delivered_kind="baseline",
        loop_eligible=True, delivered_score_delta=0, extra_cost_usd=0,
    )
    summary = _aggregate_loop_summary(project_root, render_dir)
    assert summary is not None
    assert summary["delivered_retry_count"] == 0
    assert summary["score_gain_avg"] == 0.0
    assert summary["score_gain_total"] == 0


# ── 集成：build_enhancement_report 条件追加 loop_summary ─────────────────────


def test_build_enhancement_report_includes_loop_summary_when_aggregate_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_enhancement_report 端到端：mock _aggregate_loop_summary 返 dict → 报告含 loop_summary。"""
    from tools import enhance_consistency

    fake_summary = {"$schema_version": 1, "loop_type": "single_retry", "n_views": 1}
    monkeypatch.setattr(
        enhance_consistency, "_aggregate_loop_summary",
        lambda *_args, **_kw: fake_summary,
    )

    # 构造最小 manifest + render_dir 满足 build_enhancement_report 前提
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    manifest = {
        "schema_version": 1,
        "run_id": "test",
        "subsystem": "demo",
        "render_dir_abs_resolved": str(render_dir),
        "sources": [],  # 空 sources → build 会标 blocked，不影响 loop_summary 判定
    }

    report = enhance_consistency.build_enhancement_report(tmp_path, manifest)
    assert report.get("loop_summary") == fake_summary


def test_build_enhancement_report_omits_loop_summary_when_aggregate_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OPS-MAJOR-2：_aggregate 返 None → 报告 **不含** loop_summary key。"""
    from tools import enhance_consistency

    monkeypatch.setattr(
        enhance_consistency, "_aggregate_loop_summary",
        lambda *_args, **_kw: None,
    )

    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    manifest = {
        "schema_version": 1,
        "run_id": "test",
        "subsystem": "demo",
        "render_dir_abs_resolved": str(render_dir),
        "sources": [],
    }
    report = enhance_consistency.build_enhancement_report(tmp_path, manifest)
    assert "loop_summary" not in report
