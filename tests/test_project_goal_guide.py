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


# ===== §11.I-4: 7 个 per-status builder =====
def _make_parse_result_for_builder_test():
    """共用 fixture：构造一个 minimal ParseResult-like 对象供 builder 测试。"""
    from tools.product_goal_parser import parse_product_goal
    return parse_product_goal(text="做升降平台")


def test_action_for_needs_product_goal():
    """RED → GREEN: I-4 builder #1。"""
    from tools.project_guide import _action_for_needs_product_goal

    parse_result = _make_parse_result_for_builder_test()
    action = _action_for_needs_product_goal(parse_result)
    assert action["kind"] == "supply_product_goal"
    assert "preview_cli" in action
    assert "--product-goal" in action["preview_cli"]


def test_action_for_needs_subsystem_confirmation():
    """RED → GREEN: I-4 builder #2。"""
    from tools.project_guide import _action_for_needs_subsystem_confirmation

    parse_result = _make_parse_result_for_builder_test()
    action = _action_for_needs_subsystem_confirmation(parse_result)
    assert action["kind"] == "confirm_subsystem"
    assert "preview_cli" in action
    assert "--confirm-subsystem" in action["preview_cli"]


def test_action_for_unknown_subsystem():
    """RED → GREEN: I-4 builder #3 — 不带 preview_cli，必带 supported。"""
    from tools.project_guide import _action_for_unknown_subsystem

    parse_result = _make_parse_result_for_builder_test()
    action = _action_for_unknown_subsystem(parse_result)
    assert action["kind"] == "list_supported_subsystems"
    assert action["supported"] == ["lifting_platform", "end_effector"]
    # 此 builder 不带 preview_cli（spec rev 4 builder 契约表）
    assert "preview_cli" not in action


def test_action_for_not_yet_implemented():
    """RED → GREEN: I-4 builder #4 — 不带 preview_cli，必带 alternatives。"""
    from tools.project_guide import _action_for_not_yet_implemented

    parse_result = _make_parse_result_for_builder_test()
    action = _action_for_not_yet_implemented(parse_result)
    assert action["kind"] == "wait_for_implementation"
    alts = action["alternatives"]
    assert "lifting_platform" in alts["implemented_subsystems"]
    assert "end_effector" in alts["implemented_subsystems"]
    assert "switch_example" in alts
    assert "feedback_url" in alts
    assert "preview_cli" not in action


def test_action_for_needs_kpi_confirmation():
    """RED → GREEN: I-4 builder #5。"""
    from tools.project_guide import _action_for_needs_kpi_confirmation

    parse_result = _make_parse_result_for_builder_test()
    action = _action_for_needs_kpi_confirmation(parse_result, missing=["load_kg", "stroke_mm"])
    assert action["kind"] == "supply_missing_kpis"
    assert action["missing_kpis"] == ["load_kg", "stroke_mm"]
    assert "preview_cli" in action


def test_action_for_needs_design_doc():
    """RED → GREEN: I-4 builder #6。"""
    from tools.project_guide import _action_for_needs_design_doc

    parse_result = _make_parse_result_for_builder_test()
    action = _action_for_needs_design_doc(parse_result)
    assert action["kind"] == "supply_design_doc"
    assert "preview_cli" in action
    assert "--design-doc" in action["preview_cli"]


def test_action_for_ready_for_cad_spec():
    """RED → GREEN: I-4 builder #7。"""
    from tools.project_guide import _action_for_ready_for_cad_spec

    parse_result = _make_parse_result_for_builder_test()
    action = _action_for_ready_for_cad_spec(parse_result, design_doc=Path("docs/design/x.md"))
    assert action["kind"] == "run_cad_spec"
    assert "preview_cli" in action
    assert "cad_pipeline.py spec" in action["preview_cli"]


def test_derive_goal_status_e2e_all_7_paths():
    """guard: I-4 e2e 集成 pin — 7 状态全路径走真实 parse_product_goal 入口。"""
    from tools.product_goal_parser import parse_product_goal
    from tools.project_guide import _derive_goal_status_and_next_action

    cases = [
        # (input, design_doc, expected_status)
        ("",                                   None, "needs_product_goal"),
        ("升降",                                None, "needs_subsystem_confirmation"),
        ("xyzzy 不存在的产品",                   None, "unknown_subsystem"),
        ("做导航 SLAM",                         None, "not_yet_implemented"),
        ("做升降平台",                                    None, "needs_kpi_confirmation"),
        ("做升降平台 50kg 行程200mm 350x230mm",           None, "needs_design_doc"),
        ("做升降平台 50kg 行程200mm 350x230mm",           Path("docs/x.md"), "ready_for_cad_spec"),
    ]
    for text, design_doc, expected_status in cases:
        parse_result = parse_product_goal(text=text)
        status, action = _derive_goal_status_and_next_action(
            parse_result, design_doc, root=Path(".")
        )
        assert status == expected_status, f"text={text!r} 实际 status={status}"
        assert isinstance(action, dict) and "kind" in action


# ===== §11.M-3: _classify_unsafe_reason =====
def test_classify_unsafe_windows_path():
    """RED → GREEN: M-3 windows_path 路径。"""
    from tools.project_guide import _classify_unsafe_reason

    assert _classify_unsafe_reason("D:\\Work\\design.md") == "windows_path"
    assert _classify_unsafe_reason("C:/User/x") == "windows_path"


def test_classify_unsafe_chinese_text():
    """RED → GREEN: M-3 chinese_text 路径。"""
    from tools.project_guide import _classify_unsafe_reason

    assert _classify_unsafe_reason("做升降平台") == "chinese_text"


def test_classify_unsafe_chinese_with_backslash():
    """RED → GREEN: M-3 优先级 — 中文里随手反斜杠必须归 chinese_text 不归 windows_path。"""
    from tools.project_guide import _classify_unsafe_reason

    assert _classify_unsafe_reason("做\\升降") == "chinese_text"
    # 中文+引号 也走 chinese_text（CJK 优先于 special_chars）
    assert _classify_unsafe_reason('高"精度"') == "chinese_text"


def test_classify_unsafe_special_chars():
    """RED → GREEN: M-3 special_chars 路径（含纯 ASCII 引号 / 换行 / 单反斜杠）。"""
    from tools.project_guide import _classify_unsafe_reason

    assert _classify_unsafe_reason('"abc"') == "special_chars"
    assert _classify_unsafe_reason("\\") == "special_chars"
    assert _classify_unsafe_reason("\n") == "special_chars"


def test_classify_unsafe_safe_passthrough():
    """guard: M-3 safe 路径不变。"""
    from tools.project_guide import _classify_unsafe_reason

    assert _classify_unsafe_reason("lifting_platform") == "safe"
    assert _classify_unsafe_reason("foo-bar_v1.2") == "safe"


def test_sanitize_preview_cli_unsafe_reason_invariant(tmp_path):
    """RED → GREEN: M-4 不变量 — preview_cli_unsafe=True ⇔ unsafe_reason 存在；safe 时两字段都不写。"""
    from tools.project_guide import write_project_goal_guide

    # chinese_text 触发降级
    report = write_project_goal_guide(tmp_path, product_goal="做升降平台")
    action = report["next_action"]
    if action.get("preview_cli_unsafe") is True:
        assert "unsafe_reason" in action, "preview_cli_unsafe=True 必须有 unsafe_reason"
        assert action["unsafe_reason"] in {"windows_path", "chinese_text", "special_chars"}

    # safe 路径下两字段都不写
    report_safe = write_project_goal_guide(tmp_path, product_goal="lifting_platform")
    action_safe = report_safe["next_action"]
    if not action_safe.get("preview_cli_unsafe"):
        assert "unsafe_reason" not in action_safe, "safe 路径不得有 unsafe_reason"
