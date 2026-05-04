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
    "photo3d-run",
    "photo3d-recover",
    "enhance-check",
    "run_id",
    "PHOTO3D_REPORT.json",
    "PHOTO3D_AUTOPILOT.json",
    "PHOTO3D_ACTION_RUN.json",
    "PHOTO3D_RUN.json",
    "ENHANCEMENT_REPORT.json",
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
        "自动重跑",
        "post_action_autopilot",
        "photo3d-recover",
        "--run-id",
        "--artifact-index",
    ):
        assert term in help_text
    assert "python cad_pipeline.py photo3d-action --subsystem <name>" in help_text
    assert "does not scan directories" in help_text or "扫描目录" in help_text
    assert "does not run enhancement" in help_text or "不" in help_text


def test_photo3d_run_help_explains_multi_round_user_flow():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "photo3d-run", "--help"],
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
        "photo3d-run",
        "PHOTO3D_RUN.json",
        "ARTIFACT_INDEX.json",
        "active_run_id",
        "--max-rounds",
        "--confirm-actions",
        "photo3d-autopilot",
        "accept-baseline",
        "enhance",
        "needs_baseline_acceptance",
        "ready_for_enhancement",
        "needs_user_input",
        "needs_manual_review",
        "loop_limit_reached",
    ):
        assert term in help_text
    assert "python cad_pipeline.py photo3d-run --subsystem <name>" in help_text
    assert "does not scan directories" in help_text or "扫描目录" in help_text
    assert "不会静默 accept-baseline" in help_text
    assert "不会运行 enhance" in help_text


def test_enhance_check_help_explains_delivery_acceptance_contract():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "enhance-check", "--help"],
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
        "enhance-check",
        "ENHANCEMENT_REPORT.json",
        "render_manifest.json",
        "--dir",
        "--manifest",
        "--output",
        "--min-similarity",
        "accepted",
        "preview",
        "blocked",
        "does not scan directories",
    ):
        assert term in help_text
    assert "python cad_pipeline.py enhance-check --subsystem <name> --dir <render_dir>" in help_text


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
        assert "post_action_autopilot" in text, f"{rel} missing autopilot loop summary"
        assert "自动重跑" in text, f"{rel} missing rerun autopilot guidance"
        assert "photo3d-run" in text, f"{rel} missing multi-round guide"
        assert "PHOTO3D_RUN.json" in text, f"{rel} missing loop report"
        assert "--confirm-actions" in text, f"{rel} missing confirmed loop guidance"
        assert "photo3d-recover" in text, f"{rel} missing run-aware recovery wrapper"
        assert "enhance-check" in text, f"{rel} missing enhancement acceptance"
        assert "ENHANCEMENT_REPORT.json" in text, f"{rel} missing enhancement report"
        assert "--run-id" in text, f"{rel} missing run-aware run_id binding"
        assert "--artifact-index" in text, f"{rel} missing artifact-index binding"
        assert "禁止" in text or "must" in text, f"{rel} missing hard recovery rule"


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
        assert "photo3d_run" in tools_by_name, rel
        assert "photo3d_recover" in tools_by_name, rel
        assert "enhance_check" in tools_by_name, rel
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
            tools_by_name["photo3d_run"]["cli"]
            == "python cad_pipeline.py photo3d-run --subsystem <name> --confirm-actions"
        )
        assert (
            tools_by_name["photo3d_recover"]["cli"]
            == "python cad_pipeline.py photo3d-recover --subsystem <name> --run-id <run_id> --artifact-index <path> --action render"
        )
        assert (
            tools_by_name["enhance_check"]["cli"]
            == "python cad_pipeline.py enhance-check --subsystem <name> --dir <render_dir>"
        )
        assert (
            tools_by_name["accept_baseline"]["cli"]
            == "python cad_pipeline.py accept-baseline --subsystem <name>"
        )
        assert "LLM_CONTEXT_PACK.json" in tools_by_name["photo3d"]["description"]
        assert "PHOTO3D_AUTOPILOT.json" in tools_by_name["photo3d_autopilot"]["description"]
        assert "PHOTO3D_ACTION_RUN.json" in tools_by_name["photo3d_action"]["description"]
        assert "--confirm" in tools_by_name["photo3d_action"]["description"]
        assert "post_action_autopilot" in tools_by_name["photo3d_action"]["description"]
        assert "reruns photo3d-autopilot" in tools_by_name["photo3d_action"]["description"]
        assert "PHOTO3D_RUN.json" in tools_by_name["photo3d_run"]["description"]
        assert "--confirm-actions" in tools_by_name["photo3d_run"]["description"]
        assert "does not accept baseline" in tools_by_name["photo3d_run"]["description"]
        assert "does not run enhancement" in tools_by_name["photo3d_run"]["description"]
        assert "run-aware" in tools_by_name["photo3d_recover"]["description"]
        assert "active_run_id" in tools_by_name["photo3d_recover"]["description"]
        assert "does not scan directories" in tools_by_name["photo3d_recover"]["description"]
        assert "普通用户" in tools_by_name["photo3d_autopilot"]["description"]
        assert "pass/warning/blocked" in tools_by_name["photo3d"]["description"]
        assert "accepted/preview/blocked" in tools_by_name["photo3d"]["description"]
        assert "ENHANCEMENT_REPORT.json" in tools_by_name["enhance_check"]["description"]
        assert "accepted/preview/blocked" in tools_by_name["enhance_check"]["description"]
        assert "does not scan directories" in tools_by_name["enhance_check"]["description"]
        assert "accepted_baseline_run_id" in tools_by_name["accept_baseline"]["description"]
