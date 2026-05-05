from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from tools.artifact_index import get_accepted_baseline
from tools.contract_io import load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.photo3d_provider_presets import DEFAULT_PROVIDER_PRESET, public_provider_presets


def write_photo3d_autopilot_report(
    project_root: str | Path,
    subsystem: str,
    photo3d_report: dict[str, Any],
    *,
    artifact_index_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    index_path = _resolve_project_path(
        root,
        artifact_index_path
        or Path("cad") / subsystem / ".cad-spec-gen" / "ARTIFACT_INDEX.json",
        "artifact index",
    )
    index = load_json_required(index_path, "artifact index")
    if index.get("subsystem") != subsystem:
        raise ValueError(
            f"artifact index subsystem mismatch: {index.get('subsystem')} != {subsystem}"
        )

    active_run_id = str(index.get("active_run_id") or "")
    report_run_id = str(photo3d_report.get("run_id") or "")
    if not active_run_id:
        raise ValueError("Photo3D autopilot requires active_run_id")
    if report_run_id != active_run_id:
        raise ValueError(
            f"PHOTO3D_REPORT.json run_id does not match active_run_id: "
            f"{report_run_id} != {active_run_id}"
        )

    target = _resolve_project_path(
        root,
        output_path
        or Path("cad")
        / subsystem
        / ".cad-spec-gen"
        / "runs"
        / active_run_id
        / "PHOTO3D_AUTOPILOT.json",
        "photo3d autopilot output",
    )
    expected_run_dir = (
        root / "cad" / subsystem / ".cad-spec-gen" / "runs" / active_run_id
    ).resolve()
    try:
        target.relative_to(expected_run_dir)
    except ValueError as exc:
        raise ValueError(
            "PHOTO3D_AUTOPILOT.json output must stay in the active run directory"
        ) from exc
    report = build_photo3d_autopilot_report(
        root,
        subsystem,
        photo3d_report,
        index=index,
        output_path=target,
    )
    write_json_atomic(target, report)
    return report


def build_photo3d_autopilot_report(
    project_root: str | Path,
    subsystem: str,
    photo3d_report: dict[str, Any],
    *,
    index: dict[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    run_id = str(photo3d_report.get("run_id") or "")
    gate_status = str(photo3d_report.get("status") or "blocked")
    try:
        accepted_baseline = get_accepted_baseline(index)
        accepted_baseline_run_id = accepted_baseline["run_id"]
    except ValueError:
        accepted_baseline_run_id = None

    artifacts = _safe_artifacts(root, photo3d_report, subsystem, run_id)
    artifacts["photo3d_autopilot"] = project_relative(
        _resolve_project_path(root, output_path, "photo3d autopilot output"),
        root,
    )
    enhancement_summary, enhancement_report = _enhancement_summary_for_run(
        root,
        subsystem,
        run_id,
        artifacts,
    )
    if enhancement_report:
        artifacts["enhancement_report"] = enhancement_report

    status, next_action = _next_action(
        subsystem,
        gate_status=gate_status,
        accepted_baseline_run_id=accepted_baseline_run_id,
        artifacts=artifacts,
        enhancement_summary=enhancement_summary,
    )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "subsystem": subsystem,
        "gate_status": gate_status,
        "enhancement_status": photo3d_report.get("enhancement_status"),
        "enhancement_summary": enhancement_summary,
        "status": status,
        "ordinary_user_message": _ordinary_user_message(
            status,
            gate_status,
            enhancement_summary=enhancement_summary,
        ),
        "accepted_baseline_run_id": accepted_baseline_run_id,
        "next_action": next_action,
        "artifacts": artifacts,
    }


def _next_action(
    subsystem: str,
    *,
    gate_status: str,
    accepted_baseline_run_id: str | None,
    artifacts: dict[str, str],
    enhancement_summary: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    if gate_status == "blocked":
        return (
            "blocked",
            {
                "kind": "follow_action_plan",
                "requires_user_confirmation": False,
                "action_plan": artifacts.get("action_plan"),
                "llm_context_pack": artifacts.get("llm_context_pack"),
            },
        )
    if accepted_baseline_run_id is None:
        argv = ["python", "cad_pipeline.py", "accept-baseline", "--subsystem", subsystem]
        action = {
            "kind": "accept_baseline",
            "requires_user_confirmation": True,
            "argv": argv,
        }
        if _safe_cli_token(subsystem):
            action["cli"] = " ".join(argv)
        return (
            "needs_baseline_acceptance",
            action,
        )
    if enhancement_summary:
        delivery_status = str(
            enhancement_summary.get("delivery_status")
            or enhancement_summary.get("status")
            or ""
        )
        if delivery_status == "accepted":
            return (
                "enhancement_accepted",
                {
                    "kind": "delivery_complete",
                    "requires_user_confirmation": False,
                    "enhancement_report": enhancement_summary.get("enhancement_report"),
                },
            )
        if delivery_status == "preview":
            return (
                "enhancement_preview",
                {
                    "kind": "review_enhancement_preview",
                    "requires_user_confirmation": True,
                    "enhancement_report": enhancement_summary.get("enhancement_report"),
                    "blocking_reasons": enhancement_summary.get("blocking_reasons") or [],
                },
            )
        if delivery_status == "blocked":
            return (
                "enhancement_blocked",
                {
                    "kind": "fix_enhancement_blockers",
                    "requires_user_confirmation": False,
                    "enhancement_report": enhancement_summary.get("enhancement_report"),
                    "blocking_reasons": enhancement_summary.get("blocking_reasons") or [],
                },
            )
    render_dir = _render_dir_from_manifest_path(artifacts.get("render_manifest"))
    if not render_dir:
        raise ValueError("Photo3D autopilot cannot recommend enhancement without render_manifest")
    argv = ["python", "cad_pipeline.py", "enhance", "--subsystem", subsystem]
    argv.extend(["--dir", render_dir])
    action = {
        "kind": "run_enhancement",
        "requires_user_confirmation": False,
        "argv": argv,
        "default_provider_preset": DEFAULT_PROVIDER_PRESET,
        "provider_presets": public_provider_presets(),
    }
    if _safe_cli_token(subsystem) and render_dir:
        action["cli"] = " ".join(argv)
    return (
        "ready_for_enhancement",
        action,
    )


def _ordinary_user_message(
    status: str,
    gate_status: str,
    *,
    enhancement_summary: dict[str, Any] | None = None,
) -> str:
    if status in {"enhancement_accepted", "enhancement_preview", "enhancement_blocked"}:
        message = (enhancement_summary or {}).get("ordinary_user_message")
        if message:
            return str(message)
    if status == "enhancement_accepted":
        return "增强一致性验收通过，可作为照片级交付。"
    if status == "enhancement_preview":
        return "增强图已生成但仍有交付风险，只能作为预览。"
    if status == "enhancement_blocked":
        return "增强验收阻断；请按 ENHANCEMENT_REPORT.json 修复后复查。"
    if status == "needs_baseline_acceptance":
        return "Photo3D 门禁通过；请确认本轮报告后显式接受为 baseline。"
    if status == "ready_for_enhancement":
        return "Photo3D 门禁通过且已有 accepted baseline，可以进入增强阶段。"
    if gate_status == "blocked":
        return "Photo3D 门禁阻断；请按 ACTION_PLAN.json 继续。"
    return "Photo3D autopilot 已生成下一步建议。"


def _safe_artifacts(
    project_root: Path,
    photo3d_report: dict[str, Any],
    subsystem: str,
    run_id: str,
) -> dict[str, str]:
    result = {}
    for key, raw_path in (photo3d_report.get("artifacts") or {}).items():
        if key not in {
            "photo3d_report",
            "action_plan",
            "llm_context_pack",
            "product_graph",
            "model_contract",
            "assembly_signature",
            "render_manifest",
        }:
            continue
        if not raw_path:
            continue
        resolved = _resolve_project_path(project_root, raw_path, f"artifact {key}")
        rel_path = project_relative(resolved, project_root)
        if _artifact_belongs_to_run(rel_path, subsystem, run_id, key):
            result[key] = rel_path
    return result


def _enhancement_summary_for_run(
    root: Path,
    subsystem: str,
    run_id: str,
    artifacts: dict[str, str],
) -> tuple[dict[str, Any] | None, str | None]:
    render_manifest = artifacts.get("render_manifest")
    render_dir = _render_dir_from_manifest_path(render_manifest)
    if not render_dir:
        return None, None
    report_rel = f"{render_dir}/ENHANCEMENT_REPORT.json"
    report_path = _resolve_project_path(root, report_rel, "enhancement report")
    if not report_path.is_file():
        return None, None
    report = load_json_required(report_path, "enhancement report")
    if str(report.get("run_id") or "") != run_id:
        return None, None
    if str(report.get("subsystem") or "") != subsystem:
        return None, None
    if str(report.get("render_manifest") or "") != render_manifest:
        return None, None
    summary = _compact_enhancement_summary(report, report_rel)
    return summary, report_rel


def _compact_enhancement_summary(report: dict[str, Any], report_rel: str) -> dict[str, Any]:
    status = str(report.get("delivery_status") or report.get("status") or "")
    return {
        "status": str(report.get("status") or status),
        "delivery_status": status,
        "ordinary_user_message": str(report.get("ordinary_user_message") or ""),
        "enhancement_report": report_rel,
        "render_manifest": str(report.get("render_manifest") or ""),
        "view_count": int(report.get("view_count") or 0),
        "enhanced_view_count": int(report.get("enhanced_view_count") or 0),
        "blocking_reasons": list(report.get("blocking_reasons") or []),
    }


def _artifact_belongs_to_run(path_rel_project: str, subsystem: str, run_id: str, key: str) -> bool:
    if key == "render_manifest":
        return path_rel_project == f"cad/output/renders/{subsystem}/{run_id}/render_manifest.json"
    if key in {"photo3d_report", "action_plan", "llm_context_pack"}:
        filename = {
            "photo3d_report": "PHOTO3D_REPORT.json",
            "action_plan": "ACTION_PLAN.json",
            "llm_context_pack": "LLM_CONTEXT_PACK.json",
        }[key]
        return path_rel_project == f"cad/{subsystem}/.cad-spec-gen/runs/{run_id}/{filename}"
    if key in {"product_graph", "model_contract", "assembly_signature"}:
        filename = {
            "product_graph": "PRODUCT_GRAPH.json",
            "model_contract": "MODEL_CONTRACT.json",
            "assembly_signature": "ASSEMBLY_SIGNATURE.json",
        }[key]
        return path_rel_project == f"cad/{subsystem}/.cad-spec-gen/runs/{run_id}/{filename}"
    return False


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved


def _safe_cli_token(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", value or ""))


def _render_dir_from_manifest_path(path_rel_project: str | None) -> str | None:
    if not path_rel_project or not path_rel_project.endswith("/render_manifest.json"):
        return None
    return path_rel_project.removesuffix("/render_manifest.json")
