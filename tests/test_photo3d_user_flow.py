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
    "photo3d-handoff",
    "photo3d-deliver",
    "photo3d-run",
    "photo3d-recover",
    "render-visual-check",
    "project-guide",
    "enhance-check",
    "enhance-review",
    "run_id",
    "RENDER_VISUAL_REGRESSION.json",
    "PHOTO3D_REPORT.json",
    "PHOTO3D_AUTOPILOT.json",
    "PHOTO3D_ACTION_RUN.json",
    "PHOTO3D_HANDOFF.json",
    "PHOTO3D_RUN.json",
    "DELIVERY_PACKAGE.json",
    "PROJECT_GUIDE.json",
    "ENHANCEMENT_REPORT.json",
    "ENHANCEMENT_REVIEW_REPORT.json",
    "quality_summary",
    "semantic_material_review",
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


def test_photo3d_handoff_help_explains_confirmed_handoff_flow():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "photo3d-handoff", "--help"],
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
        "photo3d-handoff",
        "PHOTO3D_RUN.json",
        "PHOTO3D_AUTOPILOT.json",
        "PHOTO3D_HANDOFF.json",
        "ARTIFACT_INDEX.json",
        "active_run_id",
        "--confirm",
        "--source",
        "--provider-preset",
        "provider preset",
        "engineering",
        "accept-baseline",
        "enhance-check",
        "photo3d-run --confirm-actions",
        "does not scan directories",
        "never trusts arbitrary argv",
        "followup_action",
        "post_handoff_photo3d_run",
        "executed_with_followup",
        "runs enhance-check",
        "accepted/preview/blocked",
    ):
        assert term in help_text
    assert "python cad_pipeline.py photo3d-handoff --subsystem <name>" in help_text


def test_photo3d_deliver_help_explains_final_delivery_package():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "photo3d-deliver", "--help"],
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
        "photo3d-deliver",
        "DELIVERY_PACKAGE.json",
        "README.md",
        "ENHANCEMENT_REPORT.json",
        "PHOTO3D_RUN.json",
        "ARTIFACT_INDEX.json",
        "active_run_id",
        "accepted",
        "preview",
        "blocked",
        "final_deliverable",
        "--include-preview",
        "--require-semantic-review",
        "ENHANCEMENT_REVIEW_REPORT.json",
        "semantic_material_review",
        "does not scan directories",
        "run_id",
        "subsystem",
    ):
        assert term in help_text
    assert "python cad_pipeline.py photo3d-deliver --subsystem <name>" in help_text


def test_render_visual_check_help_explains_phase4_consistency_gate():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "render-visual-check", "--help"],
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
        "render-visual-check",
        "RENDER_VISUAL_REGRESSION.json",
        "ARTIFACT_INDEX.json",
        "active_run_id",
        "accepted baseline",
        "baseline-manifest",
        "baseline-signature",
        "render_manifest.json",
        "does not scan",
        "per-view instance evidence",
    ):
        assert term in help_text
    assert "python cad_pipeline.py render-visual-check --subsystem <name>" in help_text


def test_render_quality_check_help_explains_blender_and_pixel_quality_gate():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "render-quality-check", "--help"],
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
        "render-quality-check",
        "RENDER_QUALITY_REPORT.json",
        "Blender preflight",
        "pixel quality",
        "ARTIFACT_INDEX.json",
        "active_run_id",
        "render_manifest.json",
        "blender_preflight",
        "pixel_metrics",
        "--blender",
        "does not scan",
    ):
        assert term in help_text
    assert "python cad_pipeline.py render-quality-check --subsystem <name>" in help_text


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


def test_project_guide_help_explains_read_only_user_flow():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "project-guide", "--help"],
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
        "project-guide",
        "PROJECT_GUIDE.json",
        "普通用户",
        "大模型",
        "read-only",
        "does not scan directories",
        "does not mutate pipeline state",
        "photo3d-run",
        "enhance-check",
        "accept-baseline",
        "provider_wizard",
        "provider_health",
    ):
        assert term in help_text


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
        "quality_summary",
        "multi-view quality",
        "accepted",
        "preview",
        "blocked",
        "does not scan directories",
    ):
        assert term in help_text
    assert "python cad_pipeline.py enhance-check --subsystem <name> --dir <render_dir>" in help_text


def test_enhance_review_help_explains_semantic_material_contract():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "enhance-review", "--help"],
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
        "enhance-review",
        "ENHANCEMENT_REVIEW_REPORT.json",
        "ENHANCEMENT_REPORT.json",
        "ARTIFACT_INDEX.json",
        "active_run_id",
        "--review-input",
        "--artifact-index",
        "--output",
        "human",
        "LLM",
        "does not call AI",
        "does not scan directories",
        "accepted",
        "preview",
        "needs_review",
        "blocked",
    ):
        assert term in help_text
    assert (
        "python cad_pipeline.py enhance-review --subsystem <name> --review-input <json>"
        in help_text
    )


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
        assert "photo3d-handoff" in text, f"{rel} missing confirmed handoff runner"
        assert "photo3d-deliver" in text, f"{rel} missing final delivery package"
        assert "render-visual-check" in text, f"{rel} missing render visual check"
        assert "RENDER_VISUAL_REGRESSION.json" in text, (
            f"{rel} missing render visual regression report"
        )
        assert "render-quality-check" in text, f"{rel} missing render quality check"
        assert "RENDER_QUALITY_REPORT.json" in text, (
            f"{rel} missing render quality report"
        )
        assert "blender_preflight" in text, f"{rel} missing blender preflight evidence"
        assert "pixel_metrics" in text, f"{rel} missing pixel metrics evidence"
        assert "quality_summary" in text, f"{rel} missing enhancement quality summary"
        assert "photo_quality_not_accepted" in text, (
            f"{rel} missing final delivery quality blocker"
        )
        assert "ENHANCEMENT_REVIEW_REPORT.json" in text, (
            f"{rel} missing semantic material review report"
        )
        assert "semantic_material_review" in text, (
            f"{rel} missing semantic material review summary"
        )
        assert "enhance-review" in text, f"{rel} missing enhance-review command"
        assert "--require-semantic-review" in text, (
            f"{rel} missing semantic review delivery gate"
        )
        assert "followup_action" in text, f"{rel} missing handoff follow-up report"
        assert "post_handoff_photo3d_run" in text, (
            f"{rel} missing post-handoff loop summary"
        )
        assert "executed_with_followup" in text, (
            f"{rel} missing executed-with-followup status"
        )
        assert "--provider-preset" in text, f"{rel} missing provider preset option"
        assert "engineering" in text, f"{rel} missing engineering provider preset"
        assert "白名单" in text or "allowlisted" in text, (
            f"{rel} missing provider allowlist rule"
        )
        assert "PHOTO3D_ACTION_RUN.json" in text, f"{rel} missing action run report"
        assert "PHOTO3D_HANDOFF.json" in text, f"{rel} missing handoff report"
        assert "DELIVERY_PACKAGE.json" in text, f"{rel} missing delivery package"
        assert "post_action_autopilot" in text, f"{rel} missing autopilot loop summary"
        assert "自动重跑" in text, f"{rel} missing rerun autopilot guidance"
        assert "project-guide" in text, f"{rel} missing project guide"
        assert "PROJECT_GUIDE.json" in text, f"{rel} missing project guide report"
        assert "provider preset" in text or "provider 选择" in text, (
            f"{rel} missing project-guide provider preset guidance"
        )
        assert "photo3d-handoff --provider-preset" in text, (
            f"{rel} missing provider handoff guidance"
        )
        assert "ordinary_user_options" in text or "普通用户可读选项" in text, (
            f"{rel} missing ordinary-user provider option guidance"
        )
        assert "provider_wizard" in text, f"{rel} missing provider wizard guidance"
        assert "provider_health" in text, f"{rel} missing provider health guidance"
        assert "photo3d-run" in text, f"{rel} missing multi-round guide"
        assert "PHOTO3D_RUN.json" in text, f"{rel} missing loop report"
        assert "--confirm-actions" in text, f"{rel} missing confirmed loop guidance"
        assert "photo3d-recover" in text, f"{rel} missing run-aware recovery wrapper"
        assert "enhance-check" in text, f"{rel} missing enhancement acceptance"
        assert (
            "自动运行" in text or "automatically runs" in text
        ), f"{rel} missing automatic enhance-check follow-up"
        assert "ENHANCEMENT_REPORT.json" in text, f"{rel} missing enhancement report"
        assert "final_deliverable" in text, f"{rel} missing final delivery semantics"
        assert "quality_summary" in text, f"{rel} missing quality summary semantics"
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
        assert "photo3d_handoff" in tools_by_name, rel
        assert "photo3d_deliver" in tools_by_name, rel
        assert "photo3d_run" in tools_by_name, rel
        assert "photo3d_recover" in tools_by_name, rel
        assert "render_visual_check" in tools_by_name, rel
        assert "render_quality_check" in tools_by_name, rel
        assert "project_guide" in tools_by_name, rel
        assert "enhance_check" in tools_by_name, rel
        assert "enhancement_review" in tools_by_name, rel
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
            tools_by_name["photo3d_handoff"]["cli"]
            == "python cad_pipeline.py photo3d-handoff --subsystem <name> --confirm"
        )
        assert (
            tools_by_name["photo3d_deliver"]["cli"]
            == "python cad_pipeline.py photo3d-deliver --subsystem <name>"
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
            tools_by_name["render_visual_check"]["cli"]
            == "python cad_pipeline.py render-visual-check --subsystem <name>"
        )
        assert (
            tools_by_name["render_quality_check"]["cli"]
            == "python cad_pipeline.py render-quality-check --subsystem <name>"
        )
        assert (
            tools_by_name["project_guide"]["cli"]
            == "python cad_pipeline.py project-guide --subsystem <name> --design-doc <path>"
        )
        assert (
            tools_by_name["enhance_check"]["cli"]
            == "python cad_pipeline.py enhance-check --subsystem <name> --dir <render_dir>"
        )
        assert (
            tools_by_name["enhancement_review"]["cli"]
            == "python cad_pipeline.py enhance-review --subsystem <name> --review-input <json>"
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
        assert "PHOTO3D_HANDOFF.json" in tools_by_name["photo3d_handoff"]["description"]
        assert "followup_action" in tools_by_name["photo3d_handoff"]["description"]
        assert (
            "post_handoff_photo3d_run"
            in tools_by_name["photo3d_handoff"]["description"]
        )
        assert "executed_with_followup" in tools_by_name["photo3d_handoff"]["description"]
        assert "accepted/preview/blocked" in tools_by_name["photo3d_handoff"]["description"]
        assert "--confirm" in tools_by_name["photo3d_handoff"]["description"]
        assert "--provider-preset" in tools_by_name["photo3d_handoff"]["description"]
        assert "engineering" in tools_by_name["photo3d_handoff"]["description"]
        assert "allowlisted provider preset" in tools_by_name["photo3d_handoff"]["description"]
        assert "does not scan directories" in tools_by_name["photo3d_handoff"]["description"]
        assert "never trusts arbitrary argv" in tools_by_name["photo3d_handoff"]["description"]
        assert "DELIVERY_PACKAGE.json" in tools_by_name["photo3d_deliver"]["description"]
        assert "final_deliverable" in tools_by_name["photo3d_deliver"]["description"]
        assert "photo_quality_not_accepted" in tools_by_name["photo3d_deliver"]["description"]
        assert "accepted" in tools_by_name["photo3d_deliver"]["description"]
        assert "does not scan directories" in tools_by_name["photo3d_deliver"]["description"]
        assert "active_run_id" in tools_by_name["photo3d_deliver"]["description"]
        assert "quality_summary" in tools_by_name["enhance_check"]["description"]
        assert "ENHANCEMENT_REVIEW_REPORT.json" in tools_by_name["enhancement_review"][
            "description"
        ]
        assert "semantic_material_review" in tools_by_name["enhancement_review"][
            "description"
        ]
        assert "does not scan directories" in tools_by_name["enhancement_review"][
            "description"
        ]
        assert "does not call AI" in tools_by_name["enhancement_review"]["description"]
        assert "active_run_id" in tools_by_name["enhancement_review"]["description"]
        assert "--review-input" in tools_by_name["enhancement_review"]["description"]
        assert "--require-semantic-review" in tools_by_name["photo3d_deliver"][
            "description"
        ]
        assert "semantic_material_review" in tools_by_name["photo3d_deliver"][
            "description"
        ]
        assert "RENDER_VISUAL_REGRESSION.json" in tools_by_name["render_visual_check"][
            "description"
        ]
        assert "does not scan directories" in tools_by_name["render_visual_check"][
            "description"
        ]
        assert "accepted baseline" in tools_by_name["render_visual_check"][
            "description"
        ]
        assert "RENDER_QUALITY_REPORT.json" in tools_by_name["render_quality_check"][
            "description"
        ]
        assert "Blender preflight" in tools_by_name["render_quality_check"][
            "description"
        ]
        assert "pixel_metrics" in tools_by_name["render_quality_check"]["description"]
        assert "does not scan directories" in tools_by_name["render_quality_check"][
            "description"
        ]
        assert "PHOTO3D_RUN.json" in tools_by_name["photo3d_run"]["description"]
        assert "--confirm-actions" in tools_by_name["photo3d_run"]["description"]
        assert "does not accept baseline" in tools_by_name["photo3d_run"]["description"]
        assert "does not run enhancement" in tools_by_name["photo3d_run"]["description"]
        assert "PROJECT_GUIDE.json" in tools_by_name["project_guide"]["description"]
        assert "provider preset" in tools_by_name["project_guide"]["description"]
        assert "photo3d-handoff --provider-preset" in tools_by_name["project_guide"]["description"]
        assert "ordinary_user_options" in tools_by_name["project_guide"]["description"]
        assert "provider_wizard" in tools_by_name["project_guide"]["description"]
        assert "provider_health" in tools_by_name["project_guide"]["description"]
        assert "does not scan directories" in tools_by_name["project_guide"]["description"]
        assert "does not mutate pipeline state" in tools_by_name["project_guide"]["description"]
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
