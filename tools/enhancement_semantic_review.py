from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.contract_io import file_sha256, load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative


REPORT_FILENAME = "ENHANCEMENT_REVIEW_REPORT.json"
REQUIRED_SEMANTIC_CHECKS = (
    "geometry_preserved",
    "material_consistent",
    "photorealistic",
    "no_extra_parts",
    "no_missing_parts",
)


def build_enhancement_review_report(
    project_root: str | Path,
    subsystem: str,
    *,
    review_input_path: str | Path,
    artifact_index_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a same-run semantic/material review report from explicit evidence."""
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
        raise ValueError("enhancement review requires active_run_id")
    run = (index.get("runs") or {}).get(active_run_id)
    if not run or not run.get("active"):
        raise ValueError("enhancement review requires an active run entry")

    run_dir = (
        root / "cad" / subsystem / ".cad-spec-gen" / "runs" / active_run_id
    ).resolve()
    target = _resolve_run_file(
        root,
        run_dir,
        output_path or run_dir / REPORT_FILENAME,
        "enhancement review output",
    )
    if target.name != REPORT_FILENAME:
        raise ValueError(f"enhancement review output must be {REPORT_FILENAME}")

    review_input = _resolve_project_path(root, review_input_path, "review input")
    review_payload = load_json_required(review_input, "enhancement review input")

    manifest_rel = _required_active_artifact(
        run,
        "render_manifest",
        f"cad/output/renders/{subsystem}/{active_run_id}/render_manifest.json",
    )
    manifest_path = _resolve_project_path(root, manifest_rel, "render manifest")
    manifest = load_json_required(manifest_path, "render manifest")
    _assert_current_run_payload(manifest, subsystem, active_run_id, "render_manifest.json")
    render_dir = _manifest_render_dir(manifest, root)
    expected_render_dir = (
        root / "cad" / "output" / "renders" / subsystem / active_run_id
    ).resolve()
    if render_dir != expected_render_dir:
        raise ValueError(
            "render_manifest render_dir does not match active run: "
            f"{project_relative(render_dir, root)} != "
            f"{project_relative(expected_render_dir, root)}"
        )

    enhancement_path = render_dir / "ENHANCEMENT_REPORT.json"
    enhancement_report = load_json_required(enhancement_path, "enhancement report")
    manifest_rel_project = project_relative(manifest_path, root)
    enhancement_rel_project = project_relative(enhancement_path, root)

    blocking_reasons: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    blocking_reasons.extend(
        _enhancement_binding_blockers(
            enhancement_report,
            subsystem,
            active_run_id,
            manifest_rel_project,
            enhancement_rel_project,
        )
    )
    blocking_reasons.extend(
        _review_input_binding_blockers(
            review_payload,
            subsystem,
            active_run_id,
            root,
            manifest_path,
            enhancement_path,
            manifest_rel_project,
            enhancement_rel_project,
        )
    )

    expected_views = _expected_views(enhancement_report)
    view_records, view_blockers, view_warnings = _review_views(
        review_payload.get("views"),
        expected_views,
        enhancement_report,
    )
    blocking_reasons.extend(view_blockers)
    warnings.extend(view_warnings)

    status = _status(blocking_reasons, view_records)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": active_run_id,
        "subsystem": subsystem,
        "status": status,
        "ordinary_user_message": _ordinary_user_message(status),
        "review_type": str(review_payload.get("review_type") or "unknown"),
        "enhancement_review_report": project_relative(target, root),
        "source_reports": {
            "artifact_index": project_relative(index_path, root),
            "render_manifest": manifest_rel_project,
            "render_manifest_sha256": file_sha256(manifest_path),
            "enhancement_report": enhancement_rel_project,
            "enhancement_report_sha256": file_sha256(enhancement_path),
            "review_input": project_relative(review_input, root),
            "review_input_sha256": file_sha256(review_input),
        },
        "semantic_material_review": {
            "schema_version": 1,
            "status": status,
            "required_checks": list(REQUIRED_SEMANTIC_CHECKS),
            "view_count": len(view_records),
            "review_report": project_relative(target, root),
        },
        "view_count": len(view_records),
        "views": view_records,
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
    }
    return report


def write_enhancement_review_report(
    project_root: str | Path,
    subsystem: str,
    *,
    review_input_path: str | Path,
    artifact_index_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    report = build_enhancement_review_report(
        project_root,
        subsystem,
        review_input_path=review_input_path,
        artifact_index_path=artifact_index_path,
        output_path=output_path,
    )
    root = Path(project_root).resolve()
    target = _resolve_project_path(
        root,
        report["enhancement_review_report"],
        "enhancement review output",
    )
    write_json_atomic(target, report)
    return report


def command_return_code_for_enhancement_review(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {"accepted", "preview", "needs_review"} else 1


def _enhancement_binding_blockers(
    report: dict[str, Any],
    subsystem: str,
    active_run_id: str,
    render_manifest_rel: str,
    enhancement_report_rel: str,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    payload_subsystem = str(report.get("subsystem") or "")
    payload_run_id = str(report.get("run_id") or "")
    if payload_subsystem != subsystem:
        blockers.append({
            "code": "enhancement_report_subsystem_mismatch",
            "actual": payload_subsystem,
            "expected": subsystem,
        })
    if payload_run_id != active_run_id:
        blockers.append({
            "code": "enhancement_report_run_id_mismatch",
            "actual": payload_run_id,
            "expected": active_run_id,
        })
    if _norm(report.get("render_manifest")) != render_manifest_rel:
        blockers.append({
            "code": "enhancement_report_render_manifest_mismatch",
            "actual": report.get("render_manifest"),
            "expected": render_manifest_rel,
        })
    if _norm(report.get("enhancement_report")) != enhancement_report_rel:
        blockers.append({
            "code": "enhancement_report_self_path_mismatch",
            "actual": report.get("enhancement_report"),
            "expected": enhancement_report_rel,
        })
    if _norm(report.get("render_dir")) != str(Path(enhancement_report_rel).parent).replace("\\", "/"):
        blockers.append({
            "code": "enhancement_report_render_dir_mismatch",
            "actual": report.get("render_dir"),
            "expected": str(Path(enhancement_report_rel).parent).replace("\\", "/"),
        })

    status = str(report.get("delivery_status") or report.get("status") or "")
    if status != "accepted":
        blockers.append({
            "code": "enhancement_report_not_accepted",
            "status": status,
            "message": "语义/材质复核只能建立在已 accepted 的增强验收报告之上。",
        })
    quality_summary = report.get("quality_summary")
    quality_status = (
        quality_summary.get("status") if isinstance(quality_summary, dict) else None
    )
    if quality_status != "accepted":
        blockers.append({
            "code": "enhancement_quality_not_accepted",
            "quality_status": quality_status,
            "message": "语义/材质复核要求 deterministic quality_summary 已 accepted。",
        })
    return blockers


def _review_input_binding_blockers(
    payload: dict[str, Any],
    subsystem: str,
    active_run_id: str,
    project_root: Path,
    manifest_path: Path,
    enhancement_path: Path,
    manifest_rel: str,
    enhancement_rel: str,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    payload_run_id = str(payload.get("run_id") or "")
    payload_subsystem = str(payload.get("subsystem") or "")
    if payload_run_id != active_run_id:
        blockers.append({
            "code": "review_run_id_mismatch",
            "actual": payload_run_id,
            "expected": active_run_id,
        })
    if payload_subsystem != subsystem:
        blockers.append({
            "code": "review_subsystem_mismatch",
            "actual": payload_subsystem,
            "expected": subsystem,
        })

    source_reports = payload.get("source_reports")
    if not isinstance(source_reports, dict):
        return blockers + [{
            "code": "review_source_reports_missing",
            "message": "复核输入缺少 source_reports，不能绑定当前 run 证据。",
        }]

    expected_sources = {
        "render_manifest": (manifest_rel, manifest_path),
        "enhancement_report": (enhancement_rel, enhancement_path),
    }
    for key, (expected_rel, expected_path) in expected_sources.items():
        actual_rel = _norm(source_reports.get(key))
        if actual_rel != expected_rel:
            blockers.append({
                "code": "review_source_report_path_mismatch",
                "source_report": key,
                "actual": source_reports.get(key),
                "expected": expected_rel,
            })
        hash_key = f"{key}_sha256"
        actual_hash = str(source_reports.get(hash_key) or "")
        expected_hash = file_sha256(expected_path)
        if actual_hash != expected_hash:
            blockers.append({
                "code": "review_source_report_hash_mismatch",
                "source_report": key,
                "actual": actual_hash,
                "expected": expected_hash,
            })
        if actual_rel:
            actual_path = _resolve_project_path(
                project_root,
                actual_rel,
                f"review source report {key}",
            )
            if actual_path != expected_path.resolve():
                blockers.append({
                    "code": "review_source_report_resolved_path_mismatch",
                    "source_report": key,
                    "actual": project_relative(actual_path, project_root),
                    "expected": expected_rel,
                })
    return blockers


def _expected_views(enhancement_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in enhancement_report.get("views") or []:
        if not isinstance(record, dict):
            continue
        view = str(record.get("view") or "")
        if view:
            result[view] = record
    return result


def _review_views(
    raw_views: Any,
    expected_views: dict[str, dict[str, Any]],
    enhancement_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not expected_views:
        blockers.append({
            "code": "enhancement_report_no_views",
            "message": "ENHANCEMENT_REPORT.json 没有可复核的逐视角记录。",
        })
        return [], blockers, warnings
    if not isinstance(raw_views, list):
        blockers.append({
            "code": "review_views_invalid",
            "message": "复核输入 views 必须是列表。",
        })
        return [], blockers, warnings

    by_view: dict[str, dict[str, Any]] = {}
    duplicate_views: set[str] = set()
    extra_views: set[str] = set()
    for raw in raw_views:
        if not isinstance(raw, dict):
            continue
        view = str(raw.get("view") or "")
        if not view:
            continue
        if view in by_view:
            duplicate_views.add(view)
            continue
        if view not in expected_views:
            extra_views.add(view)
            continue
        by_view[view] = raw

    for view in sorted(set(expected_views) - set(by_view)):
        blockers.append({
            "code": "review_view_missing",
            "view": view,
            "message": "复核输入缺少增强报告中的视角。",
        })
    for view in sorted(duplicate_views):
        blockers.append({
            "code": "review_view_duplicate",
            "view": view,
            "message": "复核输入同一视角出现多次，不能猜测哪条有效。",
        })
    for view in sorted(extra_views):
        blockers.append({
            "code": "review_view_extra",
            "view": view,
            "message": "复核输入包含不属于当前增强报告的视角。",
        })

    view_records: list[dict[str, Any]] = []
    for view in sorted(expected_views):
        raw = by_view.get(view, {})
        semantic_checks = raw.get("semantic_checks")
        if not isinstance(semantic_checks, dict):
            semantic_checks = {}
        view_warnings, view_status = _semantic_check_warnings(view, semantic_checks)
        warnings.extend(view_warnings)
        source_view = expected_views[view]
        view_records.append({
            "view": view,
            "status": view_status,
            "source_image": source_view.get("source_image"),
            "enhanced_image": source_view.get("enhanced_image"),
            "semantic_checks": {
                key: semantic_checks.get(key)
                for key in REQUIRED_SEMANTIC_CHECKS
                if key in semantic_checks
            },
            "reviewer_notes": str(raw.get("reviewer_notes") or ""),
            "warnings": view_warnings,
            "blocking_reasons": [],
        })
    return view_records, blockers, warnings


def _semantic_check_warnings(
    view: str,
    semantic_checks: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    warnings: list[dict[str, Any]] = []
    has_preview = False
    has_needs_review = False
    for key in REQUIRED_SEMANTIC_CHECKS:
        if key not in semantic_checks:
            has_needs_review = True
            warnings.append({
                "code": "semantic_check_missing",
                "view": view,
                "check": key,
                "message": "复核输入缺少必需语义/材质检查项。",
            })
            continue
        value = semantic_checks.get(key)
        if not isinstance(value, bool):
            has_needs_review = True
            warnings.append({
                "code": "semantic_check_invalid",
                "view": view,
                "check": key,
                "actual": value,
                "message": "语义/材质检查项必须是布尔值。",
            })
            continue
        if value is False:
            has_preview = True
            warnings.append({
                "code": "semantic_check_failed",
                "view": view,
                "check": key,
                "message": "语义/材质复核发现该视角只能作为预览。",
            })
    if has_needs_review:
        return warnings, "needs_review"
    if has_preview:
        return warnings, "preview"
    return warnings, "accepted"


def _status(
    blocking_reasons: list[dict[str, Any]],
    view_records: list[dict[str, Any]],
) -> str:
    if blocking_reasons:
        return "blocked"
    if any(view.get("status") == "needs_review" for view in view_records):
        return "needs_review"
    if any(view.get("status") == "preview" for view in view_records):
        return "preview"
    return "accepted"


def _ordinary_user_message(status: str) -> str:
    messages = {
        "accepted": "语义/材质复核通过，可作为照片级交付证据。",
        "preview": "语义/材质复核发现材质、结构或照片级表现风险，只能作为预览。",
        "needs_review": "语义/材质复核证据不完整，需要补充人工或大模型复核。",
        "blocked": "语义/材质复核证据与当前 active run 不一致，不能作为交付证据。",
    }
    return messages.get(status, "语义/材质复核报告已生成。")


def _required_active_artifact(run: dict[str, Any], key: str, expected: str) -> str:
    raw = str((run.get("artifacts") or {}).get(key) or "")
    if not raw:
        raise ValueError(f"active run is missing required artifact: {key}")
    normalized = raw.replace("\\", "/")
    if normalized != expected:
        raise ValueError(
            f"active run artifact {key} does not match active run: {raw} != {expected}"
        )
    return normalized


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
            f"{label} run_id does not match active_run_id: "
            f"{payload_run_id} != {active_run_id}"
        )


def _manifest_render_dir(manifest: dict[str, Any], project_root: Path) -> Path:
    raw = (
        manifest.get("render_dir_abs_resolved")
        or manifest.get("render_dir")
        or manifest.get("render_dir_rel_project")
    )
    if not raw:
        raise ValueError("render manifest is missing render_dir")
    return _resolve_project_path(project_root, raw, "render_dir")


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


def _norm(value: Any) -> str:
    return str(value or "").replace("\\", "/")
