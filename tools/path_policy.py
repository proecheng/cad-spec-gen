import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.contract_io import stable_json_hash


def _validate_subsystem_name(subsystem: str) -> None:
    if not isinstance(subsystem, str) or not subsystem:
        raise ValueError("subsystem must be a non-empty directory name")
    if "/" in subsystem or "\\" in subsystem:
        raise ValueError(f"subsystem must not contain path separators: {subsystem}")
    subsystem_path = Path(subsystem)
    if subsystem_path.is_absolute() or subsystem in {".", ".."}:
        raise ValueError(f"subsystem must be a single directory name: {subsystem}")
    if subsystem_path.name != subsystem:
        raise ValueError(f"subsystem must be a single directory name: {subsystem}")


def strict_subsystem_dir(project_root: str | Path, subsystem: str) -> Path:
    _validate_subsystem_name(subsystem)
    root = Path(project_root)
    subsystem_dir = root / "cad" / subsystem
    if not subsystem_dir.is_dir() or subsystem_dir.resolve().name != subsystem:
        raise FileNotFoundError(f"Subsystem directory not found: {subsystem_dir}")
    return subsystem_dir


def canonical_compare_path(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path))).replace("\\", "/")


def project_relative(path: str | Path, project_root: str | Path) -> str:
    target = Path(path).resolve()
    root = Path(project_root).resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Path is outside project: {target}") from exc


def assert_within_project(path: str | Path, project_root: str | Path, label: str) -> None:
    target = Path(path).resolve()
    root = Path(project_root).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must be within project: {target}") from exc


def build_path_context(
    project_root: str | Path,
    subsystem: str,
    output_dir: str | Path | None = None,
    render_dir: str | Path | None = None,
    run_id: str | None = None,
    env: dict[str, Any] | None = None,
    skill_root: str | Path | None = None,
) -> dict:
    root = Path(project_root).resolve()
    requested_subsystem = subsystem
    subsystem_dir = strict_subsystem_dir(root, subsystem).resolve()
    cad_dir = (root / "cad").resolve()
    resolved_subsystem = subsystem_dir.name
    actual_run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    actual_output_dir = Path(output_dir).resolve() if output_dir is not None else (cad_dir / "output").resolve()
    actual_render_dir = (
        Path(render_dir).resolve()
        if render_dir is not None
        else (actual_output_dir / "renders" / resolved_subsystem / actual_run_id).resolve()
    )

    assert_within_project(actual_output_dir, root, "output_dir")
    assert_within_project(actual_render_dir, root, "render_dir")

    context = {
        "schema_version": 1,
        "subsystem": resolved_subsystem,
        "requested_subsystem": requested_subsystem,
        "resolved_subsystem": resolved_subsystem,
        "project_root": str(root),
        "cad_dir": str(cad_dir),
        "subsystem_dir": str(subsystem_dir),
        "output_dir": str(actual_output_dir),
        "render_dir": str(actual_render_dir),
        "skill_root": str(Path(skill_root).resolve()) if skill_root is not None else None,
        "env": dict(env or {}),
        "run_id": actual_run_id,
    }
    context["path_context_hash"] = stable_json_hash(context)
    return context
