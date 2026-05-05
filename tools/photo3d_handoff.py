from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Any

from tools.contract_io import load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.photo3d_baseline import accept_photo3d_baseline
from tools.photo3d_loop import run_photo3d_loop
from tools.photo3d_provider_presets import (
    DEFAULT_PROVIDER_PRESET,
    public_provider_preset,
    trusted_provider_argv_suffix,
)


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
