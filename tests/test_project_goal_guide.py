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


def test_needs_kpi_when_subsystem_clear_but_kpis_missing(tmp_path):
    from tools.project_guide import write_project_goal_guide

    # 仅 product_goal，缺 KPI
    report = write_project_goal_guide(tmp_path, product_goal="做一个升降平台")

    assert report["status"] == "needs_kpi_confirmation"
    assert "load_kg" in report["product_goal"]["kpi_missing"]
    assert "stroke_mm" in report["product_goal"]["kpi_missing"]
    assert "platform_size_mm" in report["product_goal"]["kpi_missing"]
    assert report["next_action"]["kind"] == "supply_missing_kpis"


def test_needs_design_doc_when_kpis_complete_but_no_design_doc(tmp_path):
    """rev 4 DR-1：KPI 齐 + 无 design_doc → needs_design_doc（非 ready）。"""
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(
        tmp_path,
        product_goal="升降平台 升 50kg 行程 200mm 平台 350x230",
    )

    assert report["status"] == "needs_design_doc"
    assert report["next_action"]["kind"] == "supply_design_doc"
    assert report["product_goal"]["kpi_missing"] == []


def test_ready_for_cad_spec_when_kpis_and_design_doc_both_present(tmp_path):
    from tools.project_guide import write_project_goal_guide

    design_doc = tmp_path / "docs" / "design" / "XX-lifting_platform.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# 设计文档", encoding="utf-8")

    report = write_project_goal_guide(
        tmp_path,
        product_goal="升降平台 升 50kg 行程 200mm 平台 350x230",
        design_doc=design_doc,
    )

    assert report["status"] == "ready_for_cad_spec"
    assert report["next_action"]["kind"] == "run_cad_spec"
    assert "lifting_platform" in report["next_action"]["preview_cli"]


def test_confirmed_kpis_can_complete_missing_kpis(tmp_path):
    from tools.project_guide import write_project_goal_guide

    design_doc = tmp_path / "docs" / "design" / "XX-lifting_platform.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# 设计文档", encoding="utf-8")

    report = write_project_goal_guide(
        tmp_path,
        product_goal="做一个升降平台",
        confirmed_kpis={
            "load_kg": 50.0,
            "stroke_mm": 200.0,
            "platform_size_mm": (350.0, 230.0),
        },
        design_doc=design_doc,
    )

    assert report["status"] == "ready_for_cad_spec"
