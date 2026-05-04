from __future__ import annotations

import re
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any, Callable

from tools.contract_io import load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative


RECOVERY_ACTIONS = {"product-graph", "build", "render"}


def run_photo3d_recover(
    project_root: str | Path,
    subsystem: str,
    run_id: str,
    *,
    artifact_index_path: str | Path,
    action: str,
    product_graph_writer: Callable[..., Path] | None = None,
    build_runner: Callable[[Any], int] | None = None,
    render_runner: Callable[[Any], int] | None = None,
) -> dict[str, Any]:
    """Run a low-risk recovery action in the active Photo3D run scope."""
    root = Path(project_root).resolve()
    if action not in RECOVERY_ACTIONS:
        raise ValueError(f"unsupported Photo3D recovery action: {action}")
    _assert_safe_token(subsystem, "subsystem")
    _assert_safe_token(run_id, "run_id")

    index_path = _resolve_project_path(root, artifact_index_path, "artifact index")
    index = load_json_required(index_path, "artifact index")
    run = _validate_current_run(index, subsystem, run_id)
    run_dir = (root / "cad" / subsystem / ".cad-spec-gen" / "runs" / run_id).resolve()
    assert_within_project(run_dir, root, "photo3d run directory")
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts = dict(run.get("artifacts") or {})
    if action == "product-graph":
        output = run_dir / "PRODUCT_GRAPH.json"
        writer = product_graph_writer or _write_product_graph
        writer(root, subsystem, output=output, run_id=run_id)
        artifacts["product_graph"] = project_relative(output, root)
    elif action == "build":
        _stage_legacy_inputs(root, subsystem, run_id, artifacts, include_signature=False)
        build_rc = _run_build_for_current_run(
            root,
            subsystem,
            run_id,
            build_runner=build_runner,
        )
        if build_rc != 0:
            return _report(index_path, subsystem, run_id, action, build_rc, artifacts)
        copied = _copy_run_output_artifact(
            root,
            source=root / "cad" / "output" / "runs" / run_id / "ASSEMBLY_SIGNATURE.json",
            target=run_dir / "ASSEMBLY_SIGNATURE.json",
            artifact_key="assembly_signature",
            artifacts=artifacts,
        )
        if not copied:
            return _report(index_path, subsystem, run_id, action, 1, artifacts)
    else:
        _stage_legacy_inputs(root, subsystem, run_id, artifacts, include_signature=True)
        render_rc = _run_render_for_current_run(
            root,
            subsystem,
            run_id,
            artifacts=artifacts,
            render_runner=render_runner,
        )
        if render_rc != 0:
            return _report(index_path, subsystem, run_id, action, render_rc, artifacts)
        manifest = root / "cad" / "output" / "renders" / subsystem / run_id / "render_manifest.json"
        if manifest.is_file():
            artifacts["render_manifest"] = project_relative(manifest, root)

    _validate_current_run(index, subsystem, run_id)
    run["artifacts"] = artifacts
    write_json_atomic(index_path, index)
    return _report(index_path, subsystem, run_id, action, 0, artifacts)


def _write_product_graph(root: Path, subsystem: str, *, output: Path, run_id: str) -> Path:
    from tools.product_graph import write_product_graph

    return write_product_graph(root, subsystem, output=output, run_id=run_id)


def _run_build_for_current_run(
    root: Path,
    subsystem: str,
    run_id: str,
    *,
    build_runner: Callable[[Any], int] | None,
) -> int:
    runner = build_runner or _cad_pipeline_build_runner()
    return int(
        runner(
            SimpleNamespace(
                subsystem=subsystem,
                render=False,
                dry_run=False,
                verbose=False,
                skip_orientation=False,
                run_id=run_id,
            )
        )
    )


def _run_render_for_current_run(
    root: Path,
    subsystem: str,
    run_id: str,
    *,
    artifacts: dict[str, str],
    render_runner: Callable[[Any], int] | None,
) -> int:
    runner = render_runner or _cad_pipeline_render_runner()
    product_graph = _load_optional_artifact(root, artifacts.get("product_graph"), "product graph")
    output_dir = root / "cad" / "output" / "renders" / subsystem / run_id
    return int(
        runner(
            SimpleNamespace(
                subsystem=subsystem,
                view=None,
                timestamp=False,
                output_dir=str(output_dir),
                dry_run=False,
                run_id=run_id,
                path_context_hash=(product_graph or {}).get("path_context_hash"),
            )
        )
    )


def _cad_pipeline_build_runner() -> Callable[[Any], int]:
    import cad_pipeline

    return cad_pipeline.cmd_build


def _cad_pipeline_render_runner() -> Callable[[Any], int]:
    import cad_pipeline

    return cad_pipeline.cmd_render


def _copy_run_output_artifact(
    root: Path,
    *,
    source: Path,
    target: Path,
    artifact_key: str,
    artifacts: dict[str, str],
) -> bool:
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    artifacts[artifact_key] = project_relative(target, root)
    return True


def _stage_legacy_inputs(
    root: Path,
    subsystem: str,
    run_id: str,
    artifacts: dict[str, str],
    *,
    include_signature: bool,
) -> None:
    bindings = [
        ("product_graph", root / "cad" / subsystem / "PRODUCT_GRAPH.json"),
        ("model_contract", root / "cad" / subsystem / ".cad-spec-gen" / "MODEL_CONTRACT.json"),
    ]
    if include_signature:
        bindings.append(
            (
                "assembly_signature",
                root / "cad" / "output" / "runs" / run_id / "ASSEMBLY_SIGNATURE.json",
            )
        )
    for key, legacy_path in bindings:
        source_value = artifacts.get(key)
        if not source_value:
            continue
        source_path = _resolve_project_path(root, source_value, f"artifact {key}")
        if not source_path.is_file():
            continue
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, legacy_path)


def _validate_current_run(index: dict[str, Any], subsystem: str, run_id: str) -> dict[str, Any]:
    if index.get("subsystem") != subsystem:
        raise ValueError(f"artifact index subsystem mismatch: {index.get('subsystem')} != {subsystem}")
    active_run_id = str(index.get("active_run_id") or "")
    if active_run_id != run_id:
        raise ValueError(f"run_id must match active_run_id: {run_id} != {active_run_id}")
    run = (index.get("runs") or {}).get(run_id)
    if not isinstance(run, dict) or not run.get("active"):
        raise ValueError("Photo3D recovery requires an active run entry")
    return run


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved


def _load_optional_artifact(root: Path, path_value: str | None, label: str) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = _resolve_project_path(root, path_value, label)
    if not path.is_file():
        return None
    return load_json_required(path, label)


def _assert_safe_token(value: str, label: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value or ""):
        raise ValueError(f"{label} must be a safe token")


def _report(
    index_path: Path,
    subsystem: str,
    run_id: str,
    action: str,
    returncode: int,
    artifacts: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "subsystem": subsystem,
        "run_id": run_id,
        "action": action,
        "returncode": returncode,
        "artifact_index": str(index_path),
        "artifacts": dict(artifacts),
    }
