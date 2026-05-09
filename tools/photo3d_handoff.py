from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from tools._file_lock import LockBusy, acquire_lock
from tools.contract_io import load_json_required, write_json_atomic
from tools.jury.stderr_messages import format_stderr_message
from tools.path_policy import assert_within_project, project_relative
from tools.photo3d_baseline import accept_photo3d_baseline
from tools.photo3d_loop import run_photo3d_loop
from tools.photo3d_provider_presets import (
    DEFAULT_PROVIDER_PRESET,
    public_provider_preset,
    trusted_provider_argv_suffix,
)


# === v2.28.0 jury 集成常量（spec §3.3.1） ===
HANDOFF_LOCK_STALE_SECONDS: int = 1800       # .handoff.lock 30 分钟自动清理
SUBPROCESS_TIMEOUT_ENHANCE: int = 1800       # enhance 子进程 30 分钟超时
SUBPROCESS_TIMEOUT_JURY: int = 600           # jury 子进程 10 分钟超时（含 LLM hang 兜底）
SUBPROCESS_TIMEOUT_REVIEW: int = 300         # enhance-review 5 分钟超时（本地处理）
RUN_ID_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def validate_run_id_format(run_id: str) -> bool:
    """returns True iff run_id matches RUN_ID_PATTERN; never raises (spec §3.4 inv 10)."""
    return bool(RUN_ID_PATTERN.fullmatch(run_id))


def clamp_review_exit(review_raw_exit: int) -> int:
    """clamp enhance-review 子进程 exit code 到 handoff exit 段，防与 handoff 自身段撞码。

    映射：0→0 / 1→20 / 2→21 / 3→22 / 其他→23（spec §3.3.1）
    """
    if review_raw_exit == 0:
        return 0
    if review_raw_exit == 1:
        return 20
    if review_raw_exit == 2:
        return 21
    if review_raw_exit == 3:
        return 22
    return 23


EXECUTABLE_HANDOFFS = {
    "accept_baseline",
    "run_enhancement",
    "run_enhance_check",
    "confirm_action_plan",
}

MANUAL_HANDOFFS = {
    "delivery_complete",
    "review_enhancement_preview",
    "fix_enhancement_blockers",
    "provide_user_input",
    "manual_review",
}


def run_photo3d_handoff(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    source: str | None = None,
    confirm: bool = False,
    provider_preset: str | None = None,
    output_path: str | Path | None = None,
    with_jury: bool = False,  # v2.28.0 — jury hook 主体后续 task 实现
    no_strict_jury: bool = False,  # v2.28.0 — jury hook 主体后续 task 实现
) -> dict[str, Any]:
    """Preview or execute the current Photo3D next-action handoff."""
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
        raise ValueError("Photo3D handoff requires active_run_id")
    run = (index.get("runs") or {}).get(active_run_id)
    if not run or not run.get("active"):
        raise ValueError("Photo3D handoff requires an active run entry")

    run_dir = (
        root / "cad" / subsystem / ".cad-spec-gen" / "runs" / active_run_id
    ).resolve()
    payload, source_name, source_path = _load_source_payload(root, run_dir, source)
    _assert_current_run_payload(payload, subsystem, active_run_id, source_path.name)
    target = _resolve_run_file(
        root,
        run_dir,
        output_path or run_dir / "PHOTO3D_HANDOFF.json",
        "photo3d handoff output",
    )
    if target.name != "PHOTO3D_HANDOFF.json":
        raise ValueError("photo3d handoff output must be PHOTO3D_HANDOFF.json")

    next_action = dict(payload.get("next_action") or {})
    selected_action = _classify_next_action(
        root,
        subsystem,
        active_run_id,
        index_path,
        next_action,
        provider_preset,
    )
    manual_action: dict[str, Any] | None = None
    executed_action: dict[str, Any] | None = None
    followup_action: dict[str, Any] | None = None
    post_handoff_photo3d_run: dict[str, Any] | None = None

    if selected_action["classification"] != "executable":
        manual_action = dict(next_action)
        manual_action["reason"] = selected_action["reason"]
        status = "needs_manual_review"
        ordinary_user_message = "当前下一步不能自动交接；请人工复查 PHOTO3D_HANDOFF.json。"
    elif not confirm:
        status = "awaiting_confirmation"
        ordinary_user_message = "已找到可交接的下一步；加 --confirm 后才会执行。"
    else:
        executed_action = _execute_selected_action(
            root,
            subsystem,
            active_run_id,
            index_path,
            selected_action,
        )
        if executed_action.get("returncode") == 0:
            status = "executed"
            ordinary_user_message = "已执行确认的 Photo3D 下一步交接。"
            if selected_action["kind"] in {"accept_baseline", "confirm_action_plan"}:
                post_handoff_photo3d_run = _post_handoff_loop(
                    root,
                    subsystem,
                    index_path,
                    active_run_id,
                )
            elif selected_action["kind"] == "run_enhancement":
                followup_action, post_handoff_photo3d_run = _run_enhancement_followup(
                    root, subsystem, active_run_id, index_path
                )
                if (
                    post_handoff_photo3d_run is not None
                    and post_handoff_photo3d_run.get("enhancement_summary")
                ):
                    status = "executed_with_followup"
                    ordinary_user_message = (
                        "已执行增强，并完成同一 run 的增强验收复查。"
                    )
                else:
                    status = "execution_failed"
                    ordinary_user_message = (
                        "增强已执行，但增强验收复查失败；请查看 followup_action。"
                    )
        else:
            status = "execution_failed"
            ordinary_user_message = "Photo3D 下一步交接执行失败；请查看 executed_action。"

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": active_run_id,
        "subsystem": subsystem,
        "source": source_name,
        "source_report": project_relative(source_path, root),
        "confirmed": confirm,
        "status": status,
        "ordinary_user_message": ordinary_user_message,
        "selected_action": _public_selected_action(selected_action),
        "manual_action": manual_action,
        "executed_action": executed_action,
        "followup_action": followup_action,
        "post_handoff_photo3d_run": post_handoff_photo3d_run,
        "artifacts": {
            "artifact_index": project_relative(index_path, root),
            "photo3d_handoff": project_relative(target, root),
        },
    }
    write_json_atomic(target, report)
    return report


def command_return_code(report: dict[str, Any]) -> int:
    if report.get("status") in {"awaiting_confirmation", "executed", "executed_with_followup"}:
        return 0
    if report.get("status") == "needs_manual_review":
        selected = report.get("selected_action") or {}
        return 0 if selected.get("kind") in MANUAL_HANDOFFS else 1
    return 1


def _load_source_payload(
    project_root: Path,
    run_dir: Path,
    source: str | None,
) -> tuple[dict[str, Any], str, Path]:
    if source not in {None, "run", "autopilot"}:
        raise ValueError("source must be run or autopilot")
    candidates: list[tuple[str, Path]]
    if source == "run":
        candidates = [("run", run_dir / "PHOTO3D_RUN.json")]
    elif source == "autopilot":
        candidates = [("autopilot", run_dir / "PHOTO3D_AUTOPILOT.json")]
    else:
        candidates = [
            ("run", run_dir / "PHOTO3D_RUN.json"),
            ("autopilot", run_dir / "PHOTO3D_AUTOPILOT.json"),
        ]
    for source_name, path in candidates:
        resolved = _resolve_run_file(project_root, run_dir, path, f"{source_name} report")
        if resolved.is_file():
            return load_json_required(resolved, f"photo3d {source_name} report"), source_name, resolved
    expected = " or ".join(path.name for _, path in candidates)
    raise FileNotFoundError(f"Required Photo3D handoff source not found: {expected}")


def _classify_next_action(
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    artifact_index_path: Path,
    next_action: dict[str, Any],
    provider_preset: str | None,
) -> dict[str, Any]:
    kind = str(next_action.get("kind") or "")
    if kind not in EXECUTABLE_HANDOFFS:
        if kind in MANUAL_HANDOFFS:
            return {
                "classification": "manual",
                "kind": kind,
                "reason": f"next_action kind requires manual handling: {kind}",
            }
        return {
            "classification": "manual",
            "kind": kind,
            "reason": f"next_action kind is not executable by photo3d-handoff: {kind}",
        }
    validation_error = _validate_next_action_binding(subsystem, active_run_id, kind, next_action)
    if validation_error:
        return {
            "classification": "manual",
            "kind": kind,
            "reason": validation_error,
        }
    selected_provider_preset = _selected_provider_preset(kind, next_action, provider_preset)
    if selected_provider_preset:
        public_preset = public_provider_preset(selected_provider_preset)
        if public_preset is None:
            return {
                "classification": "manual",
                "kind": kind,
                "reason": f"unknown provider preset: {selected_provider_preset}",
            }
    else:
        public_preset = None
    argv = _trusted_argv(
        project_root,
        subsystem,
        active_run_id,
        artifact_index_path,
        kind,
        selected_provider_preset,
    )
    selected = {
        "classification": "executable",
        "kind": kind,
        "argv": argv,
    }
    if public_preset is not None:
        selected["provider_preset"] = public_preset
    return selected


def _trusted_argv(
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    artifact_index_path: Path,
    kind: str,
    provider_preset: str | None,
) -> list[str]:
    index_rel = project_relative(artifact_index_path, project_root)
    render_dir_rel = _active_render_dir_rel(subsystem, active_run_id)
    if kind == "accept_baseline":
        return [
            sys.executable,
            "cad_pipeline.py",
            "accept-baseline",
            "--subsystem",
            subsystem,
            "--artifact-index",
            index_rel,
            "--run-id",
            active_run_id,
        ]
    if kind == "run_enhancement":
        argv = [
            sys.executable,
            "cad_pipeline.py",
            "enhance",
            "--subsystem",
            subsystem,
            "--dir",
            render_dir_rel,
        ]
        argv.extend(trusted_provider_argv_suffix(provider_preset))
        return argv
    if kind == "run_enhance_check":
        return [
            sys.executable,
            "cad_pipeline.py",
            "enhance-check",
            "--subsystem",
            subsystem,
            "--dir",
            render_dir_rel,
        ]
    if kind == "confirm_action_plan":
        return [
            sys.executable,
            "cad_pipeline.py",
            "photo3d-run",
            "--subsystem",
            subsystem,
            "--artifact-index",
            index_rel,
            "--confirm-actions",
        ]
    raise ValueError(f"Unsupported Photo3D handoff kind: {kind}")


def _selected_provider_preset(
    kind: str,
    next_action: dict[str, Any],
    provider_preset: str | None,
) -> str | None:
    if kind != "run_enhancement":
        return None
    selected = provider_preset or next_action.get("provider_preset") or DEFAULT_PROVIDER_PRESET
    return str(selected)


def _validate_next_action_binding(
    subsystem: str,
    active_run_id: str,
    kind: str,
    next_action: dict[str, Any],
) -> str | None:
    if kind != "run_enhance_check":
        return None
    render_manifest = str(next_action.get("render_manifest") or "")
    if not render_manifest:
        return None
    expected = f"cad/output/renders/{subsystem}/{active_run_id}/render_manifest.json"
    normalized = render_manifest.replace("\\", "/")
    if normalized != expected:
        return f"run_enhance_check render_manifest does not match active run: {render_manifest}"
    return None


def _execute_selected_action(
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    artifact_index_path: Path,
    selected_action: dict[str, Any],
) -> dict[str, Any]:
    kind = selected_action["kind"]
    argv = list(selected_action["argv"])
    if kind == "accept_baseline":
        try:
            accepted = accept_photo3d_baseline(
                project_root,
                subsystem,
                artifact_index_path=artifact_index_path,
                run_id=active_run_id,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            return {
                "kind": kind,
                "argv": argv,
                "returncode": 1,
                "stderr": str(exc),
                "stdout": "",
            }
        return {
            "kind": kind,
            "argv": argv,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "accepted_baseline": accepted,
        }
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
        "kind": kind,
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _run_enhancement_followup(
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    artifact_index_path: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        followup_action = _execute_enhance_check_followup(
            project_root,
            subsystem,
            active_run_id,
            artifact_index_path,
        )
        post_handoff_photo3d_run = _post_handoff_loop(
            project_root,
            subsystem,
            artifact_index_path,
            active_run_id,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        return (
            _failed_followup_action(
                project_root,
                subsystem,
                active_run_id,
                artifact_index_path,
                exc,
            ),
            None,
        )
    return followup_action, post_handoff_photo3d_run


def _failed_followup_action(
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    artifact_index_path: Path,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "kind": "run_enhance_check",
        "argv": _trusted_argv(
            project_root,
            subsystem,
            active_run_id,
            artifact_index_path,
            "run_enhance_check",
            None,
        ),
        "returncode": 1,
        "stdout": "",
        "stderr": str(exc),
    }


def _execute_enhance_check_followup(
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    artifact_index_path: Path,
) -> dict[str, Any]:
    _assert_active_run_id(artifact_index_path, active_run_id)
    argv = _trusted_argv(
        project_root,
        subsystem,
        active_run_id,
        artifact_index_path,
        "run_enhance_check",
        None,
    )
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
        "kind": "run_enhance_check",
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _post_handoff_loop(
    project_root: Path,
    subsystem: str,
    artifact_index_path: Path,
    expected_active_run_id: str,
) -> dict[str, Any]:
    _assert_active_run_id(artifact_index_path, expected_active_run_id)
    report = run_photo3d_loop(
        project_root,
        subsystem,
        artifact_index_path=artifact_index_path,
        max_rounds=1,
        confirm_actions=False,
    )
    _assert_current_run_payload(report, subsystem, expected_active_run_id, "PHOTO3D_RUN.json")
    return {
        "run_id": report.get("run_id"),
        "subsystem": report.get("subsystem"),
        "status": report.get("status"),
        "ordinary_user_message": report.get("ordinary_user_message"),
        "enhancement_summary": report.get("enhancement_summary"),
        "next_action": report.get("next_action"),
        "artifacts": report.get("artifacts"),
    }


def _public_selected_action(selected_action: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in selected_action.items()
        if key in {"classification", "kind", "argv", "reason", "provider_preset"}
    }


def _active_render_dir_rel(subsystem: str, active_run_id: str) -> str:
    return f"cad/output/renders/{subsystem}/{active_run_id}"


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
            "active_run_id changed during Photo3D handoff: "
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


# === v2.28.0 jury hook 主流程（spec §3.3.1） ===


def _run_jury_followup(
    *,
    project_root: Path,
    subsystem: str,
    active_run_id: str,
    cad_pipeline_py: Path,
    no_strict_jury: bool,
) -> dict[str, Any]:
    """jury hook 主流程（spec §3.3.1）；嵌入 _run_enhancement_followup 内（Task 13 集成）。

    本 task（Task 5）实现 step 0 acquire .handoff.lock + step 0.5 fail-fast preflight；
    step 4 jury 实跑 + step 5 enhance-review 在后续 task 加。
    """
    run_dir = (
        project_root / "cad" / subsystem / ".cad-spec-gen" / "runs" / active_run_id
    )
    lock_path = run_dir / ".handoff.lock"
    result: dict[str, Any] = {
        "jury_handoff_status": "crashed_mid_orchestration",
        "jury_status": "crashed",
        "jury_estimated_usd": 0.0,
        "jury_actual_usd": None,
        "review_status": None,
        "enhance_review_path": None,
        "jury_raw_exit": None,
        "review_raw_exit": None,
        "exit_code": 0,
    }

    # === step 0 acquire .handoff.lock ===
    try:
        lock_ctx = acquire_lock(lock_path)
    except LockBusy:
        result["jury_handoff_status"] = "handoff_lock_busy"
        result["exit_code"] = 24
        return result

    with lock_ctx:
        # === step 0.5 fail-fast jury config preflight ===
        preflight_argv = [
            sys.executable,
            str(cad_pipeline_py),
            "jury",
            "--subsystem",
            subsystem,
            "--dry-run",
        ]
        try:
            preflight = subprocess.run(
                preflight_argv,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=SUBPROCESS_TIMEOUT_JURY,
                env=os.environ.copy(),
                creationflags=0,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(format_stderr_message(
                exit_code=25, error_kind="handoff_unexpected_jury_exit",
                context={"raw_exit": "timeout"},
            ) + "\n")
            result["jury_handoff_status"] = "unexpected_jury_exit"
            result["jury_raw_exit"] = -1  # timeout sentinel
            result["exit_code"] = 25
            return result

        if preflight.returncode == 2:
            result["jury_handoff_status"] = "preflight_config_missing"
            result["jury_status"] = "config_error"
            result["exit_code"] = 2
            return result
        if preflight.returncode == 3:
            result["jury_handoff_status"] = "cost_over_budget"
            result["jury_status"] = "cost_over_budget"
            _parse_estimated_usd(preflight.stdout, result)
            # spec §5.2 + §6.3 H14: handoff 自打中文 stderr（jury 自身已打英文 [dry-run] estimated=...）
            msg = format_stderr_message(
                exit_code=3,
                error_kind="handoff_jury_cost_over_budget",
                context={
                    "estimated_usd": result["jury_estimated_usd"],
                    "budget_usd": 0.0,  # spec §3.4 inv 8 单源打印：handoff 不读 jury config，仅打印 jury 自报估价
                    "n_views": 0,
                },
            )
            sys.stderr.write(msg + "\n")
            result["exit_code"] = 3
            return result
        if preflight.returncode == 1:
            # jury Layer 0 fail（grep 实证：jury 不写 PHOTO3D_JURY_REPORT.json，return 1）
            result["jury_handoff_status"] = "jury_blocked"
            result["jury_status"] = "blocked"
            result["exit_code"] = 12
            return result
        if preflight.returncode != 0:
            result["jury_handoff_status"] = "unexpected_jury_exit"
            result["jury_raw_exit"] = preflight.returncode
            result["exit_code"] = 25
            return result

        # preflight ok（return 0）；解析估价后继续
        _parse_estimated_usd(preflight.stdout, result)

        # === step 4 jury 实跑（spec §4.1 + invariant 7）===
        real_argv = [
            sys.executable, str(cad_pipeline_py),
            "jury", "--subsystem", subsystem, "--confirm-cost",
        ]
        try:
            real = subprocess.run(
                real_argv, shell=False, capture_output=True, text=True,
                encoding="utf-8", timeout=SUBPROCESS_TIMEOUT_JURY,
                env=os.environ.copy(), creationflags=0,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(format_stderr_message(
                exit_code=25, error_kind="handoff_unexpected_jury_exit",
                context={"raw_exit": "timeout"},
            ) + "\n")
            result["jury_handoff_status"] = "unexpected_jury_exit"
            result["jury_raw_exit"] = -1
            result["exit_code"] = 25
            return result

        # invariant 7 优先级判定:
        # (a) jury exit ∈ {2, 4, 99}：jury 自己已 fail-fast 写 stderr → 直接透传不读 report
        if real.returncode in (2, 4, 99):
            _map_jury_systemerr_exit(real.returncode, result)
            return result
        # (c) 其他 unexpected exit (130/137/...) → 归 unexpected_jury_exit
        if real.returncode not in (0, 1, 3):
            sys.stderr.write(format_stderr_message(
                exit_code=25, error_kind="handoff_unexpected_jury_exit",
                context={"raw_exit": real.returncode},
            ) + "\n")
            result["jury_handoff_status"] = "unexpected_jury_exit"
            result["jury_raw_exit"] = real.returncode
            result["exit_code"] = 25
            return result
        # jury exit=1 (Layer 0 fail) → 不写 report；直接归 jury_blocked
        if real.returncode == 1:
            result["jury_handoff_status"] = "jury_blocked"
            result["jury_status"] = "blocked"
            result["exit_code"] = 12
            return result
        # jury 实跑 exit=3：理论不应到这——preflight 已用 --dry-run 守门 cost gate；
        # 实跑传了 --confirm-cost 应跳过 cost gate。但若 jury 子模块 cost 检查重复执行
        # （如 Layer 2 内部再次校验），仍 fallback 归 cost_over_budget（防御编程；spec inv 7
        # (b) 字面要求读 report，但 jury exit=3 路径不写 PHOTO3D_JURY_REPORT.json，故不读）。
        if real.returncode == 3:
            result["jury_handoff_status"] = "cost_over_budget"
            result["jury_status"] = "cost_over_budget"
            result["exit_code"] = 3
            return result

        # (b) jury exit=0 → 读 PHOTO3D_JURY_REPORT.json status 字段
        jury_report_path = run_dir / "PHOTO3D_JURY_REPORT.json"
        try:
            jury_report = json.loads(jury_report_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            # jury exit=0 但报告缺失/损坏 → unexpected
            sys.stderr.write(format_stderr_message(
                exit_code=25, error_kind="handoff_unexpected_jury_exit",
                context={"raw_exit": real.returncode},
            ) + "\n")
            result["jury_handoff_status"] = "unexpected_jury_exit"
            result["jury_raw_exit"] = real.returncode
            result["exit_code"] = 25
            return result

        jury_status = str(jury_report.get("status", ""))
        result["jury_status"] = jury_status
        actual_usd = jury_report.get("jury_meta", {}).get("actual_cost_usd")
        if isinstance(actual_usd, (int, float)):
            result["jury_actual_usd"] = float(actual_usd)

        # 业务质量类降级 / 工具故障类阻断（spec invariant 5）
        if jury_status == "accepted":
            pass  # 走 step 5
        elif jury_status == "preview":
            jury_meta_obj = jury_report.get("jury_meta", {})
            jury_meta = jury_meta_obj if isinstance(jury_meta_obj, dict) else {}
            preview_context: dict[str, Any] = {
                "failed_n": 0,  # spec 后续可填具体失败项数；本 PR 暂用 0 兜底
                "score": 0,
                "min_score": jury_meta.get("min_photoreal_score", 0),
                "report_path": str(jury_report_path),
                "mode": "warning" if no_strict_jury else "strict",
            }
            preview_exit_for_msg = 0 if no_strict_jury else 10
            sys.stderr.write(format_stderr_message(
                exit_code=preview_exit_for_msg,
                error_kind="handoff_jury_preview",
                context=preview_context,
            ) + "\n")
            if no_strict_jury:
                result["jury_handoff_status"] = "preview_warning"
                result["exit_code"] = 0
            else:
                result["jury_handoff_status"] = "preview_blocked_by_strict"
                result["exit_code"] = 10
            return result
        elif jury_status == "needs_review":
            needs_review_context: dict[str, Any] = {
                "failed_views": [],
                "vendor_request_id": None,
                "report_path": str(jury_report_path),
                "mode": "warning" if no_strict_jury else "strict",
            }
            needs_review_exit_for_msg = 0 if no_strict_jury else 11
            sys.stderr.write(format_stderr_message(
                exit_code=needs_review_exit_for_msg,
                error_kind="handoff_jury_needs_review",
                context=needs_review_context,
            ) + "\n")
            if no_strict_jury:
                result["jury_handoff_status"] = "needs_review_warning"
                result["exit_code"] = 0
            else:
                result["jury_handoff_status"] = "needs_review_blocked_by_strict"
                result["exit_code"] = 11
            return result
        elif jury_status == "blocked":
            sys.stderr.write(format_stderr_message(
                exit_code=12, error_kind="handoff_jury_blocked",
                context={"report_path": str(jury_report_path)},
            ) + "\n")
            result["jury_handoff_status"] = "jury_blocked"
            result["exit_code"] = 12
            return result
        else:
            sys.stderr.write(format_stderr_message(
                exit_code=25, error_kind="handoff_unexpected_jury_exit",
                context={"raw_exit": real.returncode},
            ) + "\n")
            result["jury_handoff_status"] = "unexpected_jury_exit"
            result["jury_raw_exit"] = real.returncode
            result["exit_code"] = 25
            return result

        # === step 5 enhance-review (仅 jury accepted 走到这) ===
        jury_run_id = str(jury_report.get("run_id", ""))
        if not validate_run_id_format(jury_run_id):
            sys.stderr.write(format_stderr_message(
                exit_code=13, error_kind="handoff_review_input_missing",
                context={
                    "review_input_path": "",
                    "reason": "run_id_format",
                },
            ) + "\n")
            result["jury_handoff_status"] = "review_input_missing"
            result["review_status"] = "input_missing"
            result["exit_code"] = 13
            return result

        review_input_path = (
            project_root / "cad" / subsystem / ".cad-spec-gen" / "runs" / jury_run_id / "jury_review_input.json"
        )
        try:
            assert_within_project(review_input_path, project_root, "jury_review_input")
        except ValueError:
            # spec invariant 10 path traversal 防御：assert_within_project 仅抛 ValueError
            # （path_policy.py:48-49 实证）
            sys.stderr.write(format_stderr_message(
                exit_code=13, error_kind="handoff_review_input_missing",
                context={
                    "review_input_path": str(review_input_path),
                    "reason": "path_traversal",
                },
            ) + "\n")
            result["jury_handoff_status"] = "review_input_missing"
            result["review_status"] = "input_missing"
            result["exit_code"] = 13
            return result

        if not review_input_path.is_file():
            sys.stderr.write(format_stderr_message(
                exit_code=13, error_kind="handoff_review_input_missing",
                context={
                    "review_input_path": str(review_input_path),
                    "reason": "not_found",
                },
            ) + "\n")
            result["jury_handoff_status"] = "review_input_missing"
            result["review_status"] = "input_missing"
            result["exit_code"] = 13
            return result

        try:
            json.loads(review_input_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as parse_exc:
            sys.stderr.write(format_stderr_message(
                exit_code=23, error_kind="handoff_review_input_corrupt",
                context={
                    "review_input_path": str(review_input_path),
                    "parse_error": str(parse_exc),
                },
            ) + "\n")
            result["jury_handoff_status"] = "review_input_corrupt"
            result["review_status"] = "input_corrupt"
            result["exit_code"] = 23
            return result

        review_argv = [
            sys.executable, str(cad_pipeline_py),
            "enhance-review", "--subsystem", subsystem,
            "--review-input", str(review_input_path),
        ]
        try:
            review = subprocess.run(
                review_argv, shell=False, capture_output=True, text=True,
                encoding="utf-8", timeout=SUBPROCESS_TIMEOUT_REVIEW,
                env=os.environ.copy(), creationflags=0,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(format_stderr_message(
                exit_code=23, error_kind="handoff_review_failed",
                context={
                    "review_raw_exit": "timeout",
                    "report_path": str(jury_report_path),
                },
            ) + "\n")
            result["jury_handoff_status"] = "review_failed"
            result["review_status"] = "failed"
            result["review_raw_exit"] = -1
            result["exit_code"] = 23
            return result

        if review.returncode == 0:
            result["jury_handoff_status"] = "accepted"
            result["review_status"] = "ok"
            result["enhance_review_path"] = str(review_input_path.parent / "ENHANCEMENT_REVIEW_REPORT.json")
            result["exit_code"] = 0
            return result
        sys.stderr.write(format_stderr_message(
            exit_code=clamp_review_exit(review.returncode),
            error_kind="handoff_review_failed",
            context={
                "review_raw_exit": review.returncode,
                "report_path": str(jury_report_path),
            },
        ) + "\n")
        result["jury_handoff_status"] = "review_failed"
        result["review_status"] = "failed"
        result["review_raw_exit"] = review.returncode
        result["exit_code"] = clamp_review_exit(review.returncode)
        return result


def _map_jury_systemerr_exit(returncode: int, result: dict[str, Any]) -> None:
    """jury 自身 fail-fast exit code 映射（spec §4.2 决策表）"""
    if returncode == 2:
        result["jury_handoff_status"] = "config_error"
        result["jury_status"] = "config_error"
        result["exit_code"] = 2
    elif returncode == 4:
        result["jury_handoff_status"] = "lock_busy"
        result["jury_status"] = "lock_busy"
        result["exit_code"] = 4
    elif returncode == 99:
        result["jury_handoff_status"] = "internal_error"
        result["jury_status"] = "internal_error"
        result["exit_code"] = 99


def _parse_estimated_usd(stdout: str, result: dict[str, Any]) -> None:
    """从 jury --dry-run stdout `[dry-run] estimated=X.XX USD, allowed=Y` 提取估价。"""
    m = re.search(r"estimated=([\d.]+)\s*USD", stdout or "")
    if m:
        try:
            result["jury_estimated_usd"] = float(m.group(1))
        except ValueError:
            pass
