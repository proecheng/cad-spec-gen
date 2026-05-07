"""产品目标入口端到端测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_empty_product_goal_writes_needs_product_goal_guide(tmp_path):
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(tmp_path, product_goal="")

    assert report["entry_mode"] == "product_goal"
    assert report["status"] == "needs_product_goal"
    assert report["mutates_pipeline_state"] is False
    assert report["does_not_scan_directories"] is True
    assert report["next_action"]["kind"] == "supply_product_goal"
    assert "schema_version" in report
    assert "generated_at" in report
    assert "ordinary_user_message" in report

    target = tmp_path / ".cad-spec-gen" / "project-guide" / "PROJECT_GUIDE.json"
    assert target.is_file()


def test_unknown_subsystem_returns_terminal_status(tmp_path):
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(tmp_path, product_goal="完全未知的 xyzzy 设备")

    assert report["status"] == "unknown_subsystem"
    assert report["next_action"]["kind"] == "list_supported_subsystems"


def test_not_yet_implemented_includes_alternatives(tmp_path):
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(tmp_path, product_goal="做导航 SLAM")

    assert report["status"] == "not_yet_implemented"
    assert report["next_action"]["kind"] == "wait_for_implementation"
    alts = report["next_action"]["alternatives"]
    assert "lifting_platform" in alts["implemented_subsystems"]
    assert "end_effector" in alts["implemented_subsystems"]
    assert "switch_example" in alts


def test_ambiguous_subsystem_writes_needs_subsystem_confirmation(tmp_path):
    from tools.project_guide import write_project_goal_guide

    # "升降"是 supporting_terms，无 primary → ambiguous
    report = write_project_goal_guide(tmp_path, product_goal="升降 50kg 设备")

    assert report["status"] == "needs_subsystem_confirmation"
    assert report["next_action"]["kind"] == "confirm_subsystem"
