"""tools/project_guide.py:write_project_goal_guide 渐进路径集成测试

spec: docs/superpowers/specs/2026-05-09-product-goal-progressive-design.md v1.0
plan Task 4.1
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_write_project_goal_guide_writes_state_when_missing_kpis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §6.4 — parse 缺 KPI → state file 落盘到 cwd"""
    monkeypatch.chdir(tmp_path)
    from tools.project_guide import write_project_goal_guide

    write_project_goal_guide(
        tmp_path,
        "做升降平台",
    )
    state_path = tmp_path / "PROJECT_GOAL_STATE.json"
    assert state_path.is_file()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["subsystem_class"] == "lifting_platform"
    assert "load_kg" in state["missing_kpis"]


def test_write_project_goal_guide_deletes_state_when_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §6.4 — parse 全齐 → state file 删（如果存在）"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "PROJECT_GOAL_STATE.json").write_text(
        json.dumps({
            "schema_version": 1,
            "raw_text": "做升降平台",
            "subsystem_class": "lifting_platform",
            "subsystem_status": "implemented",
            "confirmed_subsystem": None,
            "confirmed_kpis": {"load_kg": 50, "stroke_mm": 800},
            "missing_kpis": ["platform_size_mm"],
            "design_doc": "docs/d.md",
            "round": 3,
            "created_at": "2026-05-09T18:00:00+00:00",
            "updated_at": "2026-05-09T18:00:00+00:00",
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    from tools.project_guide import write_project_goal_guide
    write_project_goal_guide(
        tmp_path,
        "做升降平台",
        confirmed_kpis={
            "load_kg": 50,
            "stroke_mm": 800,
            "platform_size_mm": (600.0, 600.0),
        },
        design_doc="docs/d.md",
        _state_round=4,
    )
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_write_project_goal_guide_no_state_when_one_shot_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §6.4 — 一次说全 + 全齐 → 不写 state"""
    monkeypatch.chdir(tmp_path)
    from tools.project_guide import write_project_goal_guide
    write_project_goal_guide(
        tmp_path,
        "做升 50kg 行程 800mm 平台 600x600 升降平台",
        design_doc="docs/d.md",
    )
    assert not (tmp_path / "PROJECT_GOAL_STATE.json").exists()


def test_command_return_code_needs_kpi_confirmation_returns_0() -> None:
    """spec §3.3 break-change — needs_kpi_confirmation 返 0（v2.25.0 是 1）"""
    from tools.project_guide import command_return_code_for_project_guide
    assert command_return_code_for_project_guide({"status": "needs_kpi_confirmation"}) == 0


def test_ordinary_user_message_contains_resume_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec §5.2 — needs_kpi_confirmation 文案含 --resume + --answer"""
    monkeypatch.chdir(tmp_path)
    from tools.project_guide import write_project_goal_guide
    report = write_project_goal_guide(
        tmp_path,
        "做升降平台",
    )
    msg = report.get("ordinary_user_message", "")
    assert "--resume" in msg
    assert "--answer" in msg
    assert "load_kg" in msg or "stroke_mm" in msg or "platform_size_mm" in msg
