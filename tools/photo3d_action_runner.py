from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Any

from tools.contract_io import load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.photo3d_autopilot import write_photo3d_autopilot_report
from tools.photo3d_gate import run_photo3d_gate


LOW_RISK_CLI_COMMANDS = {
    "product-graph",
    "build",
    "render",
}


def run_photo3d_action(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    autopilot_report_path: str | Path | None = None,
    action_plan_path: str | Path | None = None,
    action_id: str | None = None,
    confirm: bool = False,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Preview or execute current-run Photo3D recovery actions."""
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
    if not active_run_id:
        raise ValueError("Photo3D action runner requires active_run_id")
    run = (index.get("runs") or {}).get(active_run_id)
    if not run or not run.get("active"):
        raise ValueError("Photo3D action runner requires an active run entry")

    run_dir = (
        root / "cad" / subsystem / ".cad-spec-gen" / "runs" / active_run_id
    ).resolve()
    autopilot_path = _resolve_run_file(
        root,
        run_dir,
        autopilot_report_path
        or run_dir / "PHOTO3D_AUTOPILOT.json",
        "photo3d autopilot report",
    )
    autopilot = load_json_required(autopilot_path, "photo3d autopilot report")
    _assert_current_run_payload(autopilot, subsystem, active_run_id, "PHOTO3D_AUTOPILOT.json")

    autopilot_plan_value = _action_plan_from_autopilot(autopilot)
    if action_plan_path is not None:
        requested_plan = _resolve_run_file(
            root,
            run_dir,
            action_plan_path,
            "photo3d action plan",
        )
        autopilot_plan = _resolve_run_file(
            root,
            run_dir,
            autopilot_plan_value,
            "photo3d autopilot action plan",
        )
        if requested_plan != autopilot_plan:
            raise ValueError("ACTION_PLAN.json must match PHOTO3D_AUTOPILOT.json action_plan")
        plan_value = requested_plan
    else:
        plan_value = autopilot_plan_value
    action_plan_resolved = _resolve_run_file(
        root,
        run_dir,
        plan_value,
        "photo3d action plan",
    )
    action_plan = load_json_required(action_plan_resolved, "photo3d action plan")
    _assert_current_run_payload(action_plan, subsystem, active_run_id, "ACTION_PLAN.json")

    target = _resolve_run_file(
        root,
        run_dir,
        output_path or run_dir / "PHOTO3D_ACTION_RUN.json",
        "photo3d action run output",
    )
    if target.name != "PHOTO3D_ACTION_RUN.json":
        raise ValueError("photo3d action run output must be PHOTO3D_ACTION_RUN.json")

    all_executable_actions: list[dict[str, Any]] = []
    all_user_input_actions: list[dict[str, Any]] = []
    all_rejected_actions: list[dict[str, Any]] = []
    for raw_action in action_plan.get("actions") or []:
        if not isinstance(raw_action, dict):
            continue
        classified = _classify_action(raw_action, subsystem, active_run_id)
        kind = classified.pop("_classification")
        if kind == "executable":
            all_executable_actions.append(classified)
        elif kind == "user_input":
            all_user_input_actions.append(classified)
        else:
            all_rejected_actions.append(classified)

    executable_actions: list[dict[str, Any]] = []
    user_input_actions: list[dict[str, Any]] = []
    rejected_actions: list[dict[str, Any]] = []
    matching_actions = [
        action
        for action in all_executable_actions + all_user_input_actions + all_rejected_actions
        if not action_id or action.get("action_id") == action_id
    ]
    if action_id and len(matching_actions) > 1:
        rejected_actions.append(
            {
                "action_id": action_id,
                "reason": "duplicate action_id in ACTION_PLAN.json",
            }
        )
        matching_actions = []
    for action in matching_actions:
        if action in all_executable_actions:
            executable_actions.append(action)
        elif action in all_user_input_actions:
            user_input_actions.append(action)
        else:
            rejected_actions.append(action)

    executed_actions: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []
    if confirm and executable_actions:
        for index, action in enumerate(executable_actions):
            executed = _execute_action(root, action)
            executed_actions.append(executed)
            _assert_active_run_id(index_path, active_run_id)
            if executed.get("returncode") != 0:
                skipped_actions.extend(
                    {
                        "action_id": skipped.get("action_id"),
                        "reason": "skipped_due_to_previous_failure",
                    }
                    for skipped in executable_actions[index + 1 :]
                )
                break

    post_action_autopilot = _post_action_autopilot_summary(
        root,
        subsystem,
        artifact_index_path=index_path,
        expected_active_run_id=active_run_id,
        enabled=confirm
        and bool(executed_actions)
        and len(executed_actions) == len(all_executable_actions)
        and not all_user_input_actions
        and not all_rejected_actions
        and not skipped_actions
        and all(action.get("returncode") == 0 for action in executed_actions),
    )

    status = _status(
        confirm=confirm,
        executable_actions=executable_actions,
        user_input_actions=user_input_actions,
        rejected_actions=rejected_actions,
        executed_actions=executed_actions,
    )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": active_run_id,
        "subsystem": subsystem,
        "confirmed": confirm,
        "status": status,
        "ordinary_user_message": _ordinary_user_message(status, post_action_autopilot),
        "selected_action_id": action_id,
        "autopilot_report": project_relative(autopilot_path, root),
        "action_plan": project_relative(action_plan_resolved, root),
        "executable_actions": executable_actions,
        "user_input_actions": user_input_actions,
        "rejected_actions": rejected_actions,
        "executed_actions": executed_actions,
        "skipped_actions": skipped_actions,
        "post_action_autopilot": post_action_autopilot,
        "photo3d_action_run": project_relative(target, root),
    }
    write_json_atomic(target, report)
    return report


def _post_action_autopilot_summary(
    project_root: Path,
    subsystem: str,
    *,
    artifact_index_path: Path,
    expected_active_run_id: str,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {"rerun": False}
    _assert_active_run_id(artifact_index_path, expected_active_run_id)
    photo3d_report = run_photo3d_gate(
        project_root,
        subsystem,
        artifact_index_path=artifact_index_path,
    )
    if str(photo3d_report.get("run_id") or "") != expected_active_run_id:
        raise ValueError(
            "PHOTO3D_REPORT.json run_id does not match initial active_run_id: "
            f"{photo3d_report.get('run_id')} != {expected_active_run_id}"
        )
    _assert_active_run_id(artifact_index_path, expected_active_run_id)
    autopilot = write_photo3d_autopilot_report(
        project_root,
        subsystem,
        photo3d_report,
        artifact_index_path=artifact_index_path,
    )
    if str(autopilot.get("run_id") or "") != expected_active_run_id:
        raise ValueError(
            "PHOTO3D_AUTOPILOT.json run_id does not match initial active_run_id: "
            f"{autopilot.get('run_id')} != {expected_active_run_id}"
        )
    _assert_active_run_id(artifact_index_path, expected_active_run_id)
    return {
        "rerun": True,
        "gate_status": autopilot.get("gate_status"),
        "status": autopilot.get("status"),
        "ordinary_user_message": autopilot.get("ordinary_user_message"),
        "next_action": autopilot.get("next_action"),
        "artifacts": {
            key: value
            for key, value in (autopilot.get("artifacts") or {}).items()
            if key in {"photo3d_report", "photo3d_autopilot", "action_plan", "llm_context_pack"}
        },
    }


def command_return_code(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {"awaiting_confirmation", "executed", "executed_with_followup"} else 1


def _classify_action(
    action: dict[str, Any],
    subsystem: str,
    active_run_id: str,
) -> dict[str, Any]:
    result = dict(action)
    action_run_id = str(action.get("run_id") or "")
    if action_run_id != active_run_id:
        result["_classification"] = "rejected"
        result["reason"] = f"action run_id does not match active_run_id: {action_run_id} != {active_run_id}"
        return result

    if action.get("kind") != "cli":
        result["_classification"] = "user_input"
        return result

    if action.get("risk") != "low" or action.get("requires_user_input"):
        result["_classification"] = "rejected"
        result["reason"] = "cli action is not low-risk and input-free"
        return result

    argv = action.get("argv")
    if not _is_allowed_cli_argv(argv, subsystem):
        result["_classification"] = "rejected"
        result["reason"] = "not an allowed Photo3D recovery command"
        return result

    result["argv"] = _runtime_argv(argv)
    result["_classification"] = "executable"
    return result


def _execute_action(project_root: Path, action: dict[str, Any]) -> dict[str, Any]:
    argv = [str(item) for item in action["argv"]]
    completed = subprocess.run(
        argv,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
    )
    return {
        "action_id": action.get("action_id"),
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _assert_active_run_id(artifact_index_path: Path, expected_active_run_id: str) -> None:
    index = load_json_required(artifact_index_path, "artifact index")
    actual = str(index.get("active_run_id") or "")
    if actual != expected_active_run_id:
        raise ValueError(
            "active_run_id changed during Photo3D action execution: "
            f"{actual} != {expected_active_run_id}"
        )


def _status(
    *,
    confirm: bool,
    executable_actions: list[dict[str, Any]],
    user_input_actions: list[dict[str, Any]],
    rejected_actions: list[dict[str, Any]],
    executed_actions: list[dict[str, Any]],
) -> str:
    if rejected_actions and not executable_actions:
        return "needs_manual_review"
    if user_input_actions and not executable_actions:
        return "needs_user_input"
    if executable_actions and not confirm:
        return "awaiting_confirmation"
    if executed_actions and any(action.get("returncode") != 0 for action in executed_actions):
        return "execution_failed"
    if executed_actions and (user_input_actions or rejected_actions):
        return "executed_with_followup"
    if executed_actions:
        return "executed"
    if not executable_actions and not user_input_actions and not rejected_actions:
        return "no_matching_action"
    return "needs_manual_review"


def _ordinary_user_message(status: str, post_action_autopilot: dict[str, Any] | None = None) -> str:
    if status == "executed" and (post_action_autopilot or {}).get("rerun") is True:
        return "已执行低风险恢复动作，并自动重跑 photo3d-autopilot；请查看 post_action_autopilot。"
    messages = {
        "awaiting_confirmation": "已找到可安全执行的动作；加 --confirm 后才会执行。",
        "executed": "已执行低风险恢复动作；请重新运行 photo3d-autopilot 查看下一步。",
        "execution_failed": "低风险恢复动作执行失败；请查看 PHOTO3D_ACTION_RUN.json。",
        "executed_with_followup": "已执行低风险恢复动作，但仍有需要用户处理的动作。",
        "needs_user_input": "当前动作需要用户输入；请按报告里的 user_input_actions 提供资料。",
        "needs_manual_review": "当前动作不能自动执行；请人工复查 rejected_actions。",
        "no_matching_action": "没有找到匹配的可执行动作。",
    }
    return messages.get(status, "Photo3D action runner 已生成报告。")


def _is_allowed_cli_argv(argv: Any, subsystem: str) -> bool:
    if not isinstance(argv, list) or len(argv) != 5:
        return False
    if not all(isinstance(item, str) for item in argv):
        return False
    python_token, script, command, flag, value = argv
    if Path(python_token).name.lower() not in {"python", "python.exe"}:
        return False
    if script != "cad_pipeline.py":
        return False
    if command not in LOW_RISK_CLI_COMMANDS:
        return False
    return flag == "--subsystem" and value == subsystem


def _runtime_argv(argv: list[str]) -> list[str]:
    return [sys.executable, *argv[1:]]


def _action_plan_from_autopilot(autopilot: dict[str, Any]) -> str:
    next_action = autopilot.get("next_action") or {}
    artifacts = autopilot.get("artifacts") or {}
    plan = next_action.get("action_plan") or artifacts.get("action_plan")
    if not plan:
        raise ValueError("PHOTO3D_AUTOPILOT.json does not reference ACTION_PLAN.json")
    return str(plan)


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
