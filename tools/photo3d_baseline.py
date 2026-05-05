from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.artifact_index import accept_run_baseline
from tools.contract_io import file_sha256, load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative


def accept_photo3d_baseline(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    run_id: str | None = None,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Accept a pass/warning Photo3D run after verifying report/artifact bindings."""
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

    selected_run_id = run_id or index.get("active_run_id")
    if not selected_run_id:
        raise ValueError("No active run_id; pass --run-id explicitly")
    run = (index.get("runs") or {}).get(selected_run_id)
    if not run:
        raise ValueError(f"run_id not found in ARTIFACT_INDEX.json: {selected_run_id}")

    artifacts = run.setdefault("artifacts", {})
    selected_report_path = report_path or artifacts.get("photo3d_report")
    if not selected_report_path:
        selected_report_path = (
            Path("cad")
            / subsystem
            / ".cad-spec-gen"
            / "runs"
            / selected_run_id
            / "PHOTO3D_REPORT.json"
        )
    report_resolved = _resolve_project_path(root, selected_report_path, "photo3d report")
    report = load_json_required(report_resolved, "photo3d report")

    if report.get("subsystem") != subsystem or report.get("run_id") != selected_run_id:
        raise ValueError("PHOTO3D_REPORT.json does not match subsystem/run_id")
    if report.get("status") not in {"pass", "warning"}:
        raise ValueError("Only pass/warning photo3d reports can become accepted baseline")

    expected_report_rel = artifacts.get("photo3d_report") or (
        Path("cad")
        / subsystem
        / ".cad-spec-gen"
        / "runs"
        / selected_run_id
        / "PHOTO3D_REPORT.json"
    )
    expected_report_path = _resolve_project_path(
        root,
        expected_report_rel,
        "indexed photo3d report",
    )
    if expected_report_path != report_resolved:
        raise ValueError("PHOTO3D_REPORT.json is not the indexed report for this run_id")

    report_artifacts = report.get("artifacts") or {}
    report_hashes = report.get("artifact_hashes") or {}
    for key in ("product_graph", "model_contract", "assembly_signature", "render_manifest"):
        indexed_value = artifacts.get(key)
        report_value = report_artifacts.get(key)
        if not indexed_value or not report_value:
            raise ValueError(f"PHOTO3D_REPORT.json missing indexed artifact binding: {key}")
        indexed_path = _resolve_project_path(root, indexed_value, f"indexed artifact {key}")
        report_bound_path = _resolve_project_path(root, report_value, f"report artifact {key}")
        if indexed_path != report_bound_path:
            raise ValueError(f"PHOTO3D_REPORT.json artifact path mismatch: {key}")
        expected_hash = report_hashes.get(key)
        if not expected_hash or file_sha256(indexed_path) != expected_hash:
            raise ValueError(f"PHOTO3D_REPORT.json artifact hash mismatch: {key}")

    artifacts["photo3d_report"] = project_relative(report_resolved, root)
    accept_run_baseline(index, selected_run_id)
    write_json_atomic(index_path, index)
    return {
        "run_id": selected_run_id,
        "subsystem": subsystem,
        "artifact_index": project_relative(index_path, root),
        "photo3d_report": project_relative(report_resolved, root),
        "baseline_signature": run["artifacts"]["assembly_signature"],
    }


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved
