"""Photo3D 普通用户流程和安装版帮助契约。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]

USER_FLOW_TERMS = {
    "photo3d",
    "photo3d-autopilot",
    "photo3d-action",
    "run_id",
    "PHOTO3D_REPORT.json",
    "PHOTO3D_AUTOPILOT.json",
    "PHOTO3D_ACTION_RUN.json",
    "ACTION_PLAN.json",
    "LLM_CONTEXT_PACK.json",
    "ARTIFACT_INDEX.json",
    "pass",
    "warning",
    "blocked",
    "enhancement_status",
    "baseline",
    "baseline-signature",
    "accept-baseline",
    "accepted_baseline_run_id",
    "CHANGE_SCOPE.json",
}

DOC_FLOW_TERMS = {
    "路径隔离",
    "旧产物",
    "接受基准",
    "候选基准",
    "authorized",
}

DELIVERY_STATUS_TERMS = {
    "accepted",
    "preview",
    "blocked",
}


def test_photo3d_help_explains_user_flow_and_reports():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "photo3d", "--help"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    help_text = result.stdout
    for term in USER_FLOW_TERMS:
        assert term in help_text
    for term in DELIVERY_STATUS_TERMS:
        assert term in help_text
    assert "Gate status" in help_text
    assert "Enhancement delivery status" in help_text
    assert "Status semantics: accepted" not in help_text
    assert "python cad_pipeline.py photo3d --subsystem <name>" in help_text


def test_accept_baseline_help_explains_explicit_acceptance_flow():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "accept-baseline", "--help"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    help_text = result.stdout
    for term in (
        "accept-baseline",
        "PHOTO3D_REPORT.json",
        "ARTIFACT_INDEX.json",
        "accepted baseline",
        "pass",
        "warning",
        "active_run_id",
        "baseline-signature",
    ):
        assert term in help_text


def test_photo3d_autopilot_help_explains_foolproof_next_action_flow():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "photo3d-autopilot", "--help"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    help_text = result.stdout
    for term in USER_FLOW_TERMS:
        assert term in help_text
    for term in DELIVERY_STATUS_TERMS:
        assert term in help_text
    assert "autopilot" in help_text
    assert "普通用户" in help_text
    assert "does not scan directories" in help_text or "扫描目录猜最新文件" in help_text
    assert "python cad_pipeline.py photo3d-autopilot --subsystem <name>" in help_text
    assert "python cad_pipeline.py accept-baseline --subsystem <name>" in help_text


def test_photo3d_action_help_explains_confirmed_execution_flow():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "photo3d-action", "--help"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    help_text = result.stdout
    for term in (
        "photo3d-action",
        "PHOTO3D_AUTOPILOT.json",
        "ACTION_PLAN.json",
        "PHOTO3D_ACTION_RUN.json",
        "ARTIFACT_INDEX.json",
        "active_run_id",
        "--confirm",
        "low-risk",
        "用户输入",
    ):
        assert term in help_text
    assert "python cad_pipeline.py photo3d-action --subsystem <name>" in help_text
    assert "does not scan directories" in help_text or "扫描目录" in help_text
    assert "does not run enhancement" in help_text or "不" in help_text


def test_cad_help_docs_describe_photo3d_foolproof_user_flow():
    for rel in (
        "docs/cad-help-guide-zh.md",
        "skill_cad_help.md",
        ".claude/commands/cad-help.md",
    ):
        text = (_ROOT / rel).read_text(encoding="utf-8")
        for term in USER_FLOW_TERMS:
            assert term in text, f"{rel} missing {term}"
        for term in DELIVERY_STATUS_TERMS:
            assert term in text, f"{rel} missing {term}"
        for term in DOC_FLOW_TERMS:
            assert term in text, f"{rel} missing {term}"
        assert ("Gate status" in text or "门禁状态" in text), rel
        assert ("Enhancement delivery status" in text or "增强交付状态" in text), rel
        assert "大模型" in text, f"{rel} missing LLM-facing guidance"
        assert "不能扫描目录猜最新文件" in text, f"{rel} missing no-fallback rule"
        assert "photo3d-action" in text, f"{rel} missing confirmed action runner"
        assert "PHOTO3D_ACTION_RUN.json" in text, f"{rel} missing action run report"


def test_skill_metadata_advertises_photo3d_and_llm_action_reports():
    for rel in ("skill.json", "src/cad_spec_gen/data/skill.json"):
        data = json.loads((_ROOT / rel).read_text(encoding="utf-8"))

        cad_help = next(skill for skill in data["skills"] if skill["id"] == "cad-help")
        assert "photo3d" in cad_help["description"], rel
        assert "ACTION_PLAN.json" in cad_help["description"], rel
        assert "pass/warning/blocked" in cad_help["description"], rel

        tools_by_name = {tool["name"]: tool for tool in data["tools"]}
        assert "photo3d" in tools_by_name, rel
        assert "photo3d_autopilot" in tools_by_name, rel
        assert "photo3d_action" in tools_by_name, rel
        assert "accept_baseline" in tools_by_name, rel
        assert (
            tools_by_name["photo3d"]["cli"]
            == "python cad_pipeline.py photo3d --subsystem <name>"
        )
        assert (
            tools_by_name["photo3d_autopilot"]["cli"]
            == "python cad_pipeline.py photo3d-autopilot --subsystem <name>"
        )
        assert (
            tools_by_name["photo3d_action"]["cli"]
            == "python cad_pipeline.py photo3d-action --subsystem <name> --confirm"
        )
        assert (
            tools_by_name["accept_baseline"]["cli"]
            == "python cad_pipeline.py accept-baseline --subsystem <name>"
        )
        assert "LLM_CONTEXT_PACK.json" in tools_by_name["photo3d"]["description"]
        assert "PHOTO3D_AUTOPILOT.json" in tools_by_name["photo3d_autopilot"]["description"]
        assert "PHOTO3D_ACTION_RUN.json" in tools_by_name["photo3d_action"]["description"]
        assert "--confirm" in tools_by_name["photo3d_action"]["description"]
        assert "普通用户" in tools_by_name["photo3d_autopilot"]["description"]
        assert "pass/warning/blocked" in tools_by_name["photo3d"]["description"]
        assert "accepted/preview/blocked" in tools_by_name["photo3d"]["description"]
        assert "accepted_baseline_run_id" in tools_by_name["accept_baseline"]["description"]
