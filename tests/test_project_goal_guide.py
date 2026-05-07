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


def test_preview_cli_unsafe_when_text_contains_special_chars(tmp_path):
    """rev 4 DR-4：含中文/特殊字符触发降级。"""
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(
        tmp_path,
        product_goal='升降平台 升 50kg "高精度" 平台 350x230 行程 200mm',
    )

    # 因含中文 + " → _safe_cli_token 必返 false
    assert report["next_action"].get("preview_cli_unsafe") is True
    # 降级文案不含原 user text 的特殊字符部分
    cli = report["next_action"].get("preview_cli", "")
    assert '"高精度"' not in cli
    # 降级文案应提示用户用 confirm flag
    assert "--confirm" in cli or "confirm" in cli


def test_output_path_outside_project_guide_dir_rejected(tmp_path):
    from tools.project_guide import write_project_goal_guide

    bad_output = tmp_path / "elsewhere" / "PROJECT_GUIDE.json"
    bad_output.parent.mkdir(parents=True)

    with pytest.raises(ValueError, match="PROJECT_GUIDE.json"):
        write_project_goal_guide(
            tmp_path,
            product_goal="做一个升降平台",
            output_path=bad_output,
        )


def test_cli_no_flag_writes_needs_product_goal_guide(tmp_path, capsys, monkeypatch):
    """rev 4 DR-3：dispatch 默认分支不 error，写 informative guide。"""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from cad_pipeline import cmd_project_guide

    # cmd_project_guide 用 PROJECT_ROOT，需 monkeypatch 到 tmp_path
    import cad_pipeline
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    args = type("Args", (), {
        "product_goal": None,
        "from_design_doc": False,
        "subsystem": None,
        "design_doc": None,
        "output": None,
        "artifact_index": None,
        "confirm_subsystem": None,
        "confirm_load": None, "confirm_stroke": None, "confirm_platform_size": None,
        "confirm_rot_range": None, "confirm_switch_time": None, "confirm_flange_dia": None,
    })()

    rc = cmd_project_guide(args)
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert rc == 0  # 不 error
    assert report["status"] == "needs_product_goal"
    assert report["entry_mode"] == "product_goal"


def test_cli_collect_confirmed_kpis_handles_unit_suffixes():
    """--confirm-load 50kg / 50 / 0.05t 都应解析。"""
    from cad_pipeline import _collect_confirmed_kpis

    args = type("Args", (), {
        "confirm_load": "50kg",
        "confirm_stroke": "200",
        "confirm_platform_size": "350x230",
        "confirm_rot_range": None,
        "confirm_switch_time": None,
        "confirm_flange_dia": None,
    })()

    kpis = _collect_confirmed_kpis(args)
    assert kpis["load_kg"] == 50.0
    assert kpis["stroke_mm"] == 200.0
    assert kpis["platform_size_mm"] == (350.0, 230.0)


def test_no_forbidden_secrets_in_report(tmp_path):
    """复用既有 forbidden 字段守护 — 报告永不含 api_key/url 等敏感字段。"""
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(
        tmp_path,
        product_goal="升降平台 升 50kg 行程 200mm 平台 350x230",
    )

    forbidden = {"api_key", "key", "secret", "url", "base_url", "endpoint"}

    def _walk(value):
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value), f"forbidden: {value}"
            for v in value.values():
                _walk(v)
        elif isinstance(value, list):
            for v in value:
                _walk(v)

    _walk(report)
