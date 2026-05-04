from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.contract_io import load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.photo3d_action_runner import command_return_code, run_photo3d_action
from tools.photo3d_autopilot import write_photo3d_autopilot_report
from tools.photo3d_gate import run_photo3d_gate


TERMINAL_AUTOPILOT_STATUSES = {
    "needs_baseline_acceptance",
    "ready_for_enhancement",
}


def run_photo3d_loop(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    max_rounds: int = 3,
    confirm_actions: bool = False,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")
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
    if not active_run_id:
        raise ValueError("Photo3D run loop requires active_run_id")
    run = (index.get("runs") or {}).get(active_run_id)
    if not run or not run.get("active"):
        raise ValueError("Photo3D run loop requires an active run entry")

    run_dir = (
        root / "cad" / subsystem / ".cad-spec-gen" / "runs" / active_run_id
    ).resolve()
    target = _resolve_run_file(
        root,
        run_dir,
        output_path or run_dir / "PHOTO3D_RUN.json",
        "photo3d run output",
    )
    if target.name != "PHOTO3D_RUN.json":
        raise ValueError("photo3d run output must be PHOTO3D_RUN.json")

    rounds: list[dict[str, Any]] = []
    status = "loop_limit_reached"
    next_action: dict[str, Any] = {
        "kind": "rerun_photo3d_run",
        "requires_user_confirmation": False,
        "argv": _loop_argv(subsystem, index_path, root, confirm_actions),
    }

    for round_index in range(1, max_rounds + 1):
        _assert_active_run_id(index_path, active_run_id)
        photo3d_report = run_photo3d_gate(
            root,
            subsystem,
            artifact_index_path=index_path,
        )
        _assert_current_run_payload(photo3d_report, subsystem, active_run_id, "PHOTO3D_REPORT.json")
        autopilot = write_photo3d_autopilot_report(
            root,
            subsystem,
            photo3d_report,
            artifact_index_path=index_path,
        )
        _assert_current_run_payload(autopilot, subsystem, active_run_id, "PHOTO3D_AUTOPILOT.json")
        round_report: dict[str, Any] = {
            "round": round_index,
            "gate_status": photo3d_report.get("status"),
            "autopilot_status": autopilot.get("status"),
            "action_run_status": None,
            "post_action_autopilot": {"rerun": False},
            "artifacts": _round_artifacts(autopilot),
        }

        autopilot_status = str(autopilot.get("status") or "")
        if autopilot_status in TERMINAL_AUTOPILOT_STATUSES:
            status = autopilot_status
            next_action = dict(autopilot.get("next_action") or {})
            rounds.append(round_report)
            break

        if autopilot_status != "blocked":
            status = autopilot_status or "stopped"
            next_action = dict(autopilot.get("next_action") or {})
            rounds.append(round_report)
            break

        action_run = run_photo3d_action(
            root,
            subsystem,
            artifact_index_path=index_path,
            confirm=confirm_actions,
        )
        action_status = str(action_run.get("status") or "")
        round_report["action_run_status"] = action_status
        round_report["post_action_autopilot"] = action_run.get("post_action_autopilot") or {"rerun": False}
        round_report["artifacts"]["photo3d_action_run"] = str(action_run.get("photo3d_action_run") or "")
        rounds.append(round_report)

        if not confirm_actions and action_status == "awaiting_confirmation":
            status = "awaiting_action_confirmation"
            next_action = {
                "kind": "confirm_action_plan",
                "requires_user_confirmation": True,
                "argv": _loop_argv(subsystem, index_path, root, True),
            }
            break
        if action_status == "needs_user_input":
            status = "needs_user_input"
            next_action = {
                "kind": "provide_user_input",
                "requires_user_confirmation": False,
                "user_input_actions": action_run.get("user_input_actions") or [],
            }
            break
        if action_status in {"needs_manual_review", "no_matching_action"}:
            status = "needs_manual_review"
            next_action = {
                "kind": "manual_review",
                "requires_user_confirmation": False,
                "rejected_actions": action_run.get("rejected_actions") or [],
            }
            break
        if action_status == "execution_failed":
            status = "execution_failed"
            next_action = {
                "kind": "inspect_action_run",
                "requires_user_confirmation": False,
                "photo3d_action_run": action_run.get("photo3d_action_run"),
            }
            break

        post_action_autopilot = action_run.get("post_action_autopilot") or {}
        if post_action_autopilot.get("rerun") is True:
            post_status = str(post_action_autopilot.get("status") or "")
            if post_status in TERMINAL_AUTOPILOT_STATUSES:
                status = post_status
                next_action = dict(post_action_autopilot.get("next_action") or {})
                break
            if post_status == "blocked":
                if round_index == max_rounds:
                    status = "loop_limit_reached"
                    next_action = {
                        "kind": "increase_max_rounds_or_review",
                        "requires_user_confirmation": False,
                        "max_rounds": max_rounds,
                    }
                    break
                continue
            status = post_status or "stopped"
            next_action = dict(post_action_autopilot.get("next_action") or {})
            break

        if action_status == "executed_with_followup":
            status = "needs_manual_review"
            next_action = {
                "kind": "manual_review",
                "requires_user_confirmation": False,
                "user_input_actions": action_run.get("user_input_actions") or [],
                "rejected_actions": action_run.get("rejected_actions") or [],
            }
            break

        status = action_status or "stopped"
        next_action = {
            "kind": "rerun_photo3d_run",
            "requires_user_confirmation": False,
            "argv": _loop_argv(subsystem, index_path, root, confirm_actions),
        }
        break

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": active_run_id,
        "subsystem": subsystem,
        "status": status,
        "ordinary_user_message": _ordinary_user_message(status),
        "confirmed_actions": confirm_actions,
        "max_rounds": max_rounds,
        "round_count": len(rounds),
        "rounds": rounds,
        "next_action": next_action,
        "artifacts": {
            "artifact_index": project_relative(index_path, root),
            "photo3d_run": project_relative(target, root),
        },
    }
    write_json_atomic(target, report)
    return report


def command_return_code_for_loop(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {
        "needs_baseline_acceptance",
        "ready_for_enhancement",
        "awaiting_action_confirmation",
        "needs_user_input",
        "needs_manual_review",
    } else 1


def _ordinary_user_message(status: str) -> str:
    messages = {
        "needs_baseline_acceptance": "Photo3D 多轮向导已到达 baseline 确认点；请人工确认后运行 accept-baseline。",
        "ready_for_enhancement": "Photo3D 多轮向导已到达增强入口；请按当前 run 的增强命令继续。",
        "awaiting_action_confirmation": "Photo3D 多轮向导发现低风险恢复动作；加 --confirm-actions 后才会执行。",
        "needs_user_input": "Photo3D 多轮向导需要用户提供资料或选择模型。",
        "needs_manual_review": "Photo3D 多轮向导遇到不能自动处理的动作；请人工复查报告。",
        "execution_failed": "Photo3D 多轮向导执行恢复动作失败；请查看 PHOTO3D_ACTION_RUN.json。",
        "loop_limit_reached": "Photo3D 多轮向导达到最大轮数；请检查当前报告后再继续。",
    }
    return messages.get(status, "Photo3D 多轮向导已停止。")


def _loop_argv(
    subsystem: str,
    artifact_index_path: Path,
    project_root: Path,
    confirm_actions: bool,
) -> list[str]:
    argv = ["python", "cad_pipeline.py", "photo3d-run", "--subsystem", subsystem]
    argv.extend(["--artifact-index", project_relative(artifact_index_path, project_root)])
    if confirm_actions:
        argv.append("--confirm-actions")
    return argv


def _round_artifacts(autopilot: dict[str, Any]) -> dict[str, str]:
    artifacts = autopilot.get("artifacts") or {}
    return {
        key: value
        for key, value in artifacts.items()
        if key in {"photo3d_report", "photo3d_autopilot", "action_plan", "llm_context_pack"}
    }


def _assert_current_run_payload(
    payload: dict[str, Any],
    subsystem: str,
    active_run_id: str,
    label: str,
) -> None:
    payload_subsystem = str(payload.get("subsystem") or "")
    payload_run_id = str(payload.get("run_id") or "")
    if payload_subsystem != subsystem:
        raise ValueError(f"{label} subsystem mismatch: {payload_subsystem} != {subsystem}")
    if payload_run_id != active_run_id:
        raise ValueError(
            f"{label} run_id does not match active_run_id: {payload_run_id} != {active_run_id}"
        )


def _assert_active_run_id(artifact_index_path: Path, expected_active_run_id: str) -> None:
    index = load_json_required(artifact_index_path, "artifact index")
    actual = str(index.get("active_run_id") or "")
    if actual != expected_active_run_id:
        raise ValueError(
            "active_run_id changed during Photo3D run loop: "
            f"{actual} != {expected_active_run_id}"
        )


def _resolve_run_file(
    project_root: Path,
    run_dir: Path,
    path: str | Path,
    label: str,
) -> Path:
    resolved = _resolve_project_path(project_root, path, label)
    try:
        resolved.relative_to(run_dir)
    except ValueError as exc:
        raise ValueError(f"{label} must stay in the active run directory") from exc
    return resolved


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved
