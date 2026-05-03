from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from tools.path_policy import assert_within_project, project_relative


ACTION_KINDS = {"cli", "user_request", "manual_review"}
RUN_ARTIFACTS = {
    "product_graph",
    "model_contract",
    "assembly_signature",
    "render_manifest",
    "photo3d_report",
    "action_plan",
    "llm_context_pack",
}

RENDER_STALE_CODES = {
    "render_stale",
    "render_file_hash_mismatch",
    "render_file_hash_missing",
    "render_file_missing",
    "render_manifest_assembly_signature_hash_mismatch",
    "render_manifest_model_contract_hash_mismatch",
    "render_manifest_product_graph_hash_mismatch",
    "render_qa_failed",
}

MODEL_CODES = {
    "missing_model",
    "model_quality_below_threshold",
    "model_contract_product_graph_hash_mismatch",
    "model_contract_product_graph_hash_missing",
}

ASSEMBLY_CODES = {
    "missing_required_instance",
    "unmapped_assembly_object",
    "assembly_signature_not_runtime",
    "assembly_signature_product_graph_hash_mismatch",
    "assembly_signature_model_contract_hash_mismatch",
    "assembly_signature_product_graph_hash_missing",
    "assembly_signature_model_contract_hash_missing",
}


def build_action_plan(project_root: str | Path, report: dict[str, Any]) -> dict[str, Any]:
    actions = []
    seen: set[str] = set()
    for reason in report.get("blocking_reasons", []):
        if not isinstance(reason, dict):
            continue
        for action in _actions_for_reason(report, reason):
            action_id = action["action_id"]
            if action_id in seen:
                continue
            seen.add(action_id)
            action["run_id"] = str(report.get("run_id") or "")
            actions.append(action)

    if not actions and report.get("status") == "blocked":
        action = _manual_review_action("manual_review", "人工复查照片级门禁报告")
        action["run_id"] = str(report.get("run_id") or "")
        actions.append(action)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": report.get("run_id", ""),
        "subsystem": report.get("subsystem", ""),
        "status": report.get("status", "blocked"),
        "blocking_reason_codes": [
            reason.get("code")
            for reason in report.get("blocking_reasons", [])
            if isinstance(reason, dict) and reason.get("code")
        ],
        "actions": actions,
    }


def build_llm_context_pack(
    project_root: str | Path,
    report: dict[str, Any],
    action_plan: dict[str, Any],
) -> dict[str, Any]:
    artifacts = _safe_artifacts(project_root, report)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": report.get("run_id", ""),
        "subsystem": report.get("subsystem", ""),
        "status": report.get("status", "blocked"),
        "summary_cn": report.get("ordinary_user_message") or "照片级出图被阻断。",
        "blocking_reasons": [
            reason.get("code", "")
            for reason in report.get("blocking_reasons", [])
            if isinstance(reason, dict)
        ],
        "allowed_actions": [
            action.get("action_id", "")
            for action in action_plan.get("actions", [])
            if isinstance(action, dict) and action.get("action_id")
        ],
        "artifact_paths": artifacts,
    }


def _actions_for_reason(report: dict[str, Any], reason: dict[str, Any]) -> list[dict[str, Any]]:
    code = str(reason.get("code") or "")
    subsystem = str(report.get("subsystem") or "")
    if not _safe_cli_token(subsystem):
        return [_manual_review_action("review_run_context", "复查当前 run_id、子系统和路径上下文")]
    if code in RENDER_STALE_CODES:
        return [_rerun_render_action(subsystem)]
    if code in MODEL_CODES:
        return [_ask_for_model_action(reason)]
    if code in ASSEMBLY_CODES:
        return [_rerun_build_action(subsystem)]
    if code == "artifact_index_missing_required_artifact":
        return [_action_for_missing_artifact(subsystem, reason)]
    if code.startswith("baseline_") or code.startswith("unexpected_") or code.startswith("current_"):
        return [_manual_review_action("review_change_scope", "复查变更范围和基准绑定")]
    if code in {"subsystem_mismatch", "run_id_mismatch", "path_context_hash_missing", "path_context_hash_mismatch"}:
        return [_manual_review_action("review_run_context", "复查当前 run_id、子系统和路径上下文")]
    return [_manual_review_action("manual_review", "人工复查照片级门禁报告")]


def _rerun_render_action(subsystem: str) -> dict[str, Any]:
    argv = ["python", "cad_pipeline.py", "render", "--subsystem", subsystem]
    return {
        "action_id": "rerun_render",
        "kind": "cli",
        "label_cn": "重新构建并渲染当前装配",
        "command": " ".join(argv),
        "argv": argv,
        "requires_user_input": False,
        "risk": "low",
    }


def _rerun_build_action(subsystem: str) -> dict[str, Any]:
    argv = ["python", "cad_pipeline.py", "build", "--subsystem", subsystem]
    return {
        "action_id": "rerun_build",
        "kind": "cli",
        "label_cn": "重新构建当前装配并生成运行时签名",
        "command": " ".join(argv),
        "argv": argv,
        "requires_user_input": False,
        "risk": "low",
    }


def _ask_for_model_action(reason: dict[str, Any]) -> dict[str, Any]:
    part_no = str(reason.get("part_no") or "")
    return {
        "action_id": "ask_for_model",
        "kind": "user_request",
        "label_cn": "请用户提供或选择更高质量的零件模型",
        "part_no": part_no,
        "requires_user_input": True,
        "risk": "medium",
    }


def _action_for_missing_artifact(subsystem: str, reason: dict[str, Any]) -> dict[str, Any]:
    artifact = str(reason.get("artifact") or "")
    if artifact == "product_graph":
        argv = ["python", "cad_pipeline.py", "product-graph", "--subsystem", subsystem]
        return {
            "action_id": "regenerate_product_graph",
            "kind": "cli",
            "label_cn": "重新生成产品图契约",
            "command": " ".join(argv),
            "argv": argv,
            "requires_user_input": False,
            "risk": "low",
        }
    if artifact == "model_contract":
        return _ask_for_model_action(reason)
    if artifact == "assembly_signature":
        return _rerun_build_action(subsystem)
    if artifact == "render_manifest":
        return _rerun_render_action(subsystem)
    return _manual_review_action("manual_review", "人工复查照片级门禁报告")


def _manual_review_action(action_id: str, label_cn: str) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "kind": "manual_review",
        "label_cn": label_cn,
        "requires_user_input": True,
        "risk": "medium",
    }


def _safe_artifacts(project_root: str | Path, report: dict[str, Any]) -> dict[str, str]:
    root = Path(project_root).resolve()
    result = {}
    for key, raw_path in (report.get("artifacts") or {}).items():
        if key not in RUN_ARTIFACTS:
            continue
        if not raw_path:
            continue
        path = Path(str(raw_path))
        resolved = path if path.is_absolute() else root / path
        try:
            resolved = resolved.resolve()
            assert_within_project(resolved, root, f"artifact {key}")
            rel_path = project_relative(resolved, root)
        except ValueError:
            continue
        if _artifact_belongs_to_run(
            rel_path,
            str(report.get("run_id") or ""),
            key,
            str(report.get("subsystem") or ""),
        ):
            result[key] = rel_path
    return result


def _artifact_belongs_to_run(path_rel_project: str, run_id: str, key: str, subsystem: str | None = None) -> bool:
    subsystem = subsystem or ""
    if key == "render_manifest":
        return path_rel_project == f"cad/output/renders/{subsystem}/{run_id}/render_manifest.json"
    if key in {"action_plan", "llm_context_pack", "photo3d_report"}:
        filename = {
            "action_plan": "ACTION_PLAN.json",
            "llm_context_pack": "LLM_CONTEXT_PACK.json",
            "photo3d_report": "PHOTO3D_REPORT.json",
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


def _safe_cli_token(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", value or ""))
