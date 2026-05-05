from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any

from tools.contract_io import file_sha256, load_json_required, write_json_atomic
from tools.model_audit import build_model_quality_summary
from tools.path_policy import assert_within_project, project_relative


ACTIVE_RUN_ARTIFACTS = {
    "product_graph": "PRODUCT_GRAPH.json",
    "model_contract": "MODEL_CONTRACT.json",
    "assembly_signature": "ASSEMBLY_SIGNATURE.json",
}

RUN_REPORTS = {
    "photo3d_report": "PHOTO3D_REPORT.json",
    "photo3d_run": "PHOTO3D_RUN.json",
    "photo3d_handoff": "PHOTO3D_HANDOFF.json",
    "enhancement_review": "ENHANCEMENT_REVIEW_REPORT.json",
}


def run_photo3d_delivery_pack(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    output_path: str | Path | None = None,
    include_preview: bool = False,
    require_semantic_review: bool = False,
) -> dict[str, Any]:
    """Build an auditable Photo3D delivery package for the active run."""
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
        raise ValueError("Photo3D delivery pack requires active_run_id")
    run = (index.get("runs") or {}).get(active_run_id)
    if not run or not run.get("active"):
        raise ValueError("Photo3D delivery pack requires an active run entry")

    run_dir = (
        root / "cad" / subsystem / ".cad-spec-gen" / "runs" / active_run_id
    ).resolve()
    target = _resolve_run_file(
        root,
        run_dir,
        output_path or run_dir / "delivery" / "DELIVERY_PACKAGE.json",
        "delivery package output",
    )
    if target.name != "DELIVERY_PACKAGE.json":
        raise ValueError("delivery package output must be DELIVERY_PACKAGE.json")
    delivery_dir = target.parent.resolve()
    _reset_managed_delivery_dirs(delivery_dir)

    render_manifest_rel = _required_active_artifact(
        run,
        "render_manifest",
        f"cad/output/renders/{subsystem}/{active_run_id}/render_manifest.json",
    )
    manifest_path = _resolve_project_path(root, render_manifest_rel, "render manifest")
    manifest = load_json_required(manifest_path, "render manifest")
    _assert_current_run_payload(manifest, subsystem, active_run_id, "render_manifest.json")
    render_dir = _manifest_render_dir(manifest, root)
    expected_render_dir = (root / "cad" / "output" / "renders" / subsystem / active_run_id).resolve()
    if render_dir != expected_render_dir:
        raise ValueError(
            "render_manifest render_dir does not match active run: "
            f"{project_relative(render_dir, root)} != {project_relative(expected_render_dir, root)}"
        )

    enhancement_path = render_dir / "ENHANCEMENT_REPORT.json"
    enhancement_report = load_json_required(enhancement_path, "enhancement report")
    _assert_enhancement_report_binding(
        enhancement_report,
        subsystem,
        active_run_id,
        project_relative(manifest_path, root),
        project_relative(enhancement_path, root),
    )

    source_reports = _source_reports(
        root,
        run,
        run_dir,
        index_path,
        manifest_path,
        enhancement_path,
        subsystem,
        active_run_id,
    )
    model_quality_summary = _model_quality_summary_from_source_reports(
        root,
        source_reports,
    )
    evidence_files = _copy_evidence_files(root, delivery_dir, source_reports)

    enhancement_status = str(
        enhancement_report.get("delivery_status") or enhancement_report.get("status") or ""
    )
    blocking_reasons = list(enhancement_report.get("blocking_reasons") or [])
    quality_summary = _quality_summary(enhancement_report)
    warnings: list[dict[str, Any]] = []
    final_deliverable = enhancement_status == "accepted"
    copy_preview = enhancement_status == "preview" and include_preview
    if final_deliverable and quality_summary.get("status") != "accepted":
        final_deliverable = False
        blocking_reasons.append({
            "code": "photo_quality_not_accepted",
            "quality_status": quality_summary.get("status"),
            "warnings": list(quality_summary.get("warnings") or []),
            "message": "最终交付要求增强图质量验收为 accepted。",
        })

    semantic_material_review = _semantic_material_review_summary(
        root,
        run_dir,
        subsystem,
        active_run_id,
        manifest_path,
        enhancement_path,
    )
    semantic_material_review["required"] = bool(require_semantic_review)
    if semantic_material_review["status"] == "not_run":
        if require_semantic_review:
            final_deliverable = False
            blocking_reasons.append({
                "code": "semantic_review_required",
                "message": "最终交付要求 ENHANCEMENT_REVIEW_REPORT.json 语义/材质复核为 accepted。",
            })
    elif semantic_material_review["status"] != "accepted":
        final_deliverable = False
        blocking_reasons.append({
            "code": "semantic_review_not_accepted",
            "review_status": semantic_material_review["status"],
            "review_report": semantic_material_review.get("review_report"),
            "message": "已有同一 run 的语义/材质复核未 accepted，不能作为最终照片级交付。",
        })

    deliverables = {
        "source_images": [],
        "enhanced_images": [],
        "labeled_images": [],
    }
    if final_deliverable or copy_preview:
        image_deliverables, image_warnings, image_blockers = _copy_view_images(
            root,
            delivery_dir,
            render_dir,
            manifest,
            enhancement_report,
            final=final_deliverable,
        )
        warnings.extend(image_warnings)
        if image_blockers:
            blocking_reasons.extend(image_blockers)
            final_deliverable = False
            copy_preview = False
        else:
            deliverables = image_deliverables

    status = _package_status(enhancement_status, final_deliverable, copy_preview)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": active_run_id,
        "subsystem": subsystem,
        "status": status,
        "final_deliverable": final_deliverable,
        "ordinary_user_message": _ordinary_user_message(status),
        "enhancement_status": enhancement_status,
        "quality_summary": quality_summary,
        "model_quality_summary": model_quality_summary,
        "semantic_material_review": semantic_material_review,
        "delivery_dir": project_relative(delivery_dir, root),
        "source_reports": source_reports,
        "deliverables": deliverables,
        "evidence_files": evidence_files,
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "artifacts": {
            "delivery_package": project_relative(target, root),
            "delivery_readme": project_relative(delivery_dir / "README.md", root),
        },
    }
    write_json_atomic(target, report)
    _write_readme(delivery_dir / "README.md", report)
    return report


def command_return_code_for_delivery_pack(report: dict[str, Any]) -> int:
    return 0 if report.get("final_deliverable") is True else 1


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


def _source_reports(
    root: Path,
    run: dict[str, Any],
    run_dir: Path,
    index_path: Path,
    manifest_path: Path,
    enhancement_path: Path,
    subsystem: str,
    active_run_id: str,
) -> dict[str, str]:
    reports = {
        "artifact_index": project_relative(index_path, root),
        "render_manifest": project_relative(manifest_path, root),
        "enhancement_report": project_relative(enhancement_path, root),
    }
    artifacts = run.get("artifacts") or {}
    for key in sorted(ACTIVE_RUN_ARTIFACTS):
        raw = artifacts.get(key)
        if not raw:
            continue
        path = _resolve_project_path(root, raw, f"active artifact {key}")
        expected = run_dir / ACTIVE_RUN_ARTIFACTS[key]
        if path != expected.resolve():
            raise ValueError(f"active artifact {key} path drifted: {raw}")
        if path.is_file():
            payload = load_json_required(path, key)
            _assert_current_run_payload(payload, subsystem, active_run_id, path.name)
            reports[key] = project_relative(path, root)
    for key, filename in RUN_REPORTS.items():
        path = run_dir / filename
        if not path.is_file():
            continue
        payload = load_json_required(path, key)
        _assert_current_run_payload(payload, subsystem, active_run_id, filename)
        if key == "enhancement_review":
            _assert_enhancement_review_binding(
                payload,
                subsystem,
                active_run_id,
                project_relative(manifest_path, root),
                project_relative(enhancement_path, root),
                manifest_path=manifest_path,
                enhancement_path=enhancement_path,
            )
        reports[key] = project_relative(path, root)
    return reports


def _copy_evidence_files(
    root: Path,
    delivery_dir: Path,
    source_reports: dict[str, str],
) -> list[dict[str, Any]]:
    evidence = []
    for kind, rel_path in sorted(source_reports.items()):
        source = _resolve_project_path(root, rel_path, f"evidence {kind}")
        if not source.is_file():
            continue
        copied = _copy_file(root, source, delivery_dir / "evidence")
        evidence.append(
            {
                "kind": kind,
                "source_path": project_relative(source, root),
                "package_path": project_relative(copied, root),
                "sha256": file_sha256(copied),
            }
        )
    return evidence


def _model_quality_summary_from_source_reports(
    root: Path,
    source_reports: dict[str, str],
) -> dict[str, Any] | None:
    rel_path = source_reports.get("model_contract")
    if not rel_path:
        return None
    model_contract_path = _resolve_project_path(root, rel_path, "model contract")
    model_contract = load_json_required(model_contract_path, "model contract")
    return build_model_quality_summary(
        model_contract,
        report_path=model_contract_path,
        source="model_contract",
        binding_status="active_run_model_contract",
        project_root=root,
    )


def _quality_summary(enhancement_report: dict[str, Any]) -> dict[str, Any]:
    summary = enhancement_report.get("quality_summary")
    if isinstance(summary, dict):
        return summary
    return {
        "schema_version": 1,
        "status": "accepted" if enhancement_report.get("delivery_status") == "accepted" else "unknown",
        "view_count": enhancement_report.get("enhanced_view_count") or 0,
        "warnings": [],
    }


def _semantic_material_review_summary(
    root: Path,
    run_dir: Path,
    subsystem: str,
    active_run_id: str,
    manifest_path: Path,
    enhancement_path: Path,
) -> dict[str, Any]:
    review_path = run_dir / "ENHANCEMENT_REVIEW_REPORT.json"
    if not review_path.is_file():
        return {
            "schema_version": 1,
            "status": "not_run",
            "review_report": None,
            "required": False,
        }
    review = load_json_required(review_path, "enhancement review report")
    _assert_current_run_payload(review, subsystem, active_run_id, review_path.name)
    _assert_enhancement_review_binding(
        review,
        subsystem,
        active_run_id,
        project_relative(manifest_path, root),
        project_relative(enhancement_path, root),
        manifest_path=manifest_path,
        enhancement_path=enhancement_path,
    )
    summary = review.get("semantic_material_review")
    if not isinstance(summary, dict):
        status = str(review.get("status") or "blocked")
        return {
            "schema_version": 1,
            "status": status,
            "review_report": project_relative(review_path, root),
            "required": False,
            "warnings": [],
            "blocking_reasons": [{
                "code": "semantic_material_review_missing",
                "message": "ENHANCEMENT_REVIEW_REPORT.json 缺少 semantic_material_review。",
            }],
        }
    return {
        "schema_version": int(summary.get("schema_version") or 1),
        "status": str(summary.get("status") or review.get("status") or "blocked"),
        "review_report": project_relative(review_path, root),
        "required": False,
        "view_count": int(summary.get("view_count") or review.get("view_count") or 0),
        "required_checks": list(summary.get("required_checks") or []),
        "warnings": list(review.get("warnings") or []),
        "blocking_reasons": list(review.get("blocking_reasons") or []),
    }


def _copy_view_images(
    root: Path,
    delivery_dir: Path,
    render_dir: Path,
    manifest: dict[str, Any],
    enhancement_report: dict[str, Any],
    *,
    final: bool,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_sources = _manifest_sources_by_view(manifest, root, render_dir)
    deliverables = {
        "source_images": [],
        "enhanced_images": [],
        "labeled_images": [],
    }
    warnings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    views = list(enhancement_report.get("views") or [])
    if not views:
        return (
            deliverables,
            warnings,
            [{
                "code": "enhancement_report_no_views",
                "message": "ENHANCEMENT_REPORT.json has no per-view image records.",
            }],
        )

    for view_record in views:
        if not isinstance(view_record, dict):
            continue
        view = str(view_record.get("view") or "")
        if final and view_record.get("status") != "accepted":
            blockers.append(
                {
                    "code": "enhancement_view_not_accepted",
                    "view": view,
                    "message": "Final delivery requires every view to be accepted.",
                }
            )
            continue
        source = _resolve_render_path(
            root,
            render_dir,
            view_record.get("source_image") or "",
            f"source image {view}",
        )
        expected_source = manifest_sources.get(view)
        if expected_source is None:
            blockers.append(
                {
                    "code": "source_view_missing_from_manifest",
                    "view": view,
                    "source_image": project_relative(source, root),
                }
            )
            continue
        if source != expected_source:
            blockers.append(
                {
                    "code": "source_image_manifest_mismatch",
                    "view": view,
                    "source_image": project_relative(source, root),
                    "manifest_source_image": project_relative(expected_source, root),
                }
            )
            continue
        _assert_report_hash(source, view_record.get("source_sha256"), f"source image {view}")

        enhanced_raw = view_record.get("enhanced_image")
        if not enhanced_raw:
            blockers.append(
                {
                    "code": "enhanced_image_missing",
                    "view": view,
                    "message": "Accepted delivery requires an enhanced image for each view.",
                }
            )
            continue
        enhanced = _resolve_render_path(root, render_dir, enhanced_raw, f"enhanced image {view}")
        _assert_report_hash(enhanced, view_record.get("enhanced_sha256"), f"enhanced image {view}")

        source_copy = _copy_file(root, source, delivery_dir / "source")
        enhanced_copy = _copy_file(root, enhanced, delivery_dir / ("enhanced" if final else "preview"))
        deliverables["source_images"].append(_image_item(root, view, source, source_copy))
        deliverables["enhanced_images"].append(_image_item(root, view, enhanced, enhanced_copy))

        labeled, warning = _labeled_image_for_view(render_dir, source, enhanced, view)
        if warning:
            warnings.append(warning)
        if labeled is not None:
            labeled_copy = _copy_file(root, labeled, delivery_dir / "labeled")
            deliverables["labeled_images"].append(_image_item(root, view, labeled, labeled_copy))
    return deliverables, warnings, blockers


def _manifest_sources_by_view(
    manifest: dict[str, Any],
    root: Path,
    render_dir: Path,
) -> dict[str, Path]:
    sources = {}
    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            continue
        view = str(entry.get("view") or "")
        raw = entry.get("path_abs_resolved") or entry.get("path_rel_project") or entry.get("path")
        if view and raw:
            sources[view] = _resolve_render_path(root, render_dir, raw, f"manifest source {view}")
    return sources


def _labeled_image_for_view(
    render_dir: Path,
    source: Path,
    enhanced: Path,
    view: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    candidates = set()
    for pattern in (
        f"{enhanced.stem}_labeled*.*",
        f"{source.stem}*_labeled*.*",
    ):
        candidates.update(path for path in render_dir.glob(pattern) if path.is_file())
    candidates.discard(source)
    candidates.discard(enhanced)
    ordered = sorted(candidates, key=lambda path: path.name.lower())
    if not ordered:
        return None, None
    if len(ordered) > 1:
        return (
            None,
            {
                "code": "labeled_image_ambiguous",
                "view": view,
                "candidates": [path.name for path in ordered],
                "message": "Multiple labeled image candidates found; none were copied.",
            },
        )
    return ordered[0].resolve(), None


def _image_item(root: Path, view: str, source: Path, copied: Path) -> dict[str, Any]:
    return {
        "view": view,
        "source_path": project_relative(source, root),
        "package_path": project_relative(copied, root),
        "sha256": file_sha256(copied),
    }


def _copy_file(root: Path, source: Path, directory: Path) -> Path:
    assert_within_project(source, root, "delivery source")
    assert_within_project(directory, root, "delivery directory")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / source.name
    shutil.copy2(source, target)
    return target.resolve()


def _reset_managed_delivery_dirs(delivery_dir: Path) -> None:
    for name in ("source", "enhanced", "labeled", "preview", "evidence"):
        target = delivery_dir / name
        if target.exists():
            shutil.rmtree(target)


def _assert_enhancement_report_binding(
    report: dict[str, Any],
    subsystem: str,
    active_run_id: str,
    render_manifest_rel: str,
    enhancement_report_rel: str,
) -> None:
    _assert_current_run_payload(report, subsystem, active_run_id, "ENHANCEMENT_REPORT.json")
    if str(report.get("render_manifest") or "").replace("\\", "/") != render_manifest_rel:
        raise ValueError(
            "ENHANCEMENT_REPORT.json render_manifest does not match active run: "
            f"{report.get('render_manifest')} != {render_manifest_rel}"
        )
    raw_report_path = str(report.get("enhancement_report") or "")
    if raw_report_path and raw_report_path.replace("\\", "/") != enhancement_report_rel:
        raise ValueError(
            "ENHANCEMENT_REPORT.json self path does not match active run: "
            f"{raw_report_path} != {enhancement_report_rel}"
        )
    expected_render_dir = str(Path(enhancement_report_rel).parent).replace("\\", "/")
    raw_render_dir = str(report.get("render_dir") or "")
    if raw_render_dir and raw_render_dir.replace("\\", "/") != expected_render_dir:
        raise ValueError(
            "ENHANCEMENT_REPORT.json render_dir does not match active run: "
            f"{raw_render_dir} != {expected_render_dir}"
        )


def _assert_enhancement_review_binding(
    report: dict[str, Any],
    subsystem: str,
    active_run_id: str,
    render_manifest_rel: str,
    enhancement_report_rel: str,
    *,
    manifest_path: Path | None = None,
    enhancement_path: Path | None = None,
) -> None:
    _assert_current_run_payload(report, subsystem, active_run_id, "ENHANCEMENT_REVIEW_REPORT.json")
    source_reports = report.get("source_reports")
    if not isinstance(source_reports, dict):
        raise ValueError("ENHANCEMENT_REVIEW_REPORT.json missing source_reports")
    if str(source_reports.get("render_manifest") or "").replace("\\", "/") != render_manifest_rel:
        raise ValueError(
            "ENHANCEMENT_REVIEW_REPORT.json render_manifest does not match active run: "
            f"{source_reports.get('render_manifest')} != {render_manifest_rel}"
        )
    if str(source_reports.get("enhancement_report") or "").replace("\\", "/") != enhancement_report_rel:
        raise ValueError(
            "ENHANCEMENT_REVIEW_REPORT.json enhancement_report does not match active run: "
            f"{source_reports.get('enhancement_report')} != {enhancement_report_rel}"
        )
    if manifest_path is not None:
        _assert_report_hash(
            manifest_path,
            source_reports.get("render_manifest_sha256"),
            "ENHANCEMENT_REVIEW_REPORT.json render_manifest",
        )
    if enhancement_path is not None:
        _assert_report_hash(
            enhancement_path,
            source_reports.get("enhancement_report_sha256"),
            "ENHANCEMENT_REVIEW_REPORT.json enhancement_report",
        )
    raw_report_path = str(report.get("enhancement_review_report") or "")
    if raw_report_path and not raw_report_path.endswith("/ENHANCEMENT_REVIEW_REPORT.json"):
        raise ValueError(
            "ENHANCEMENT_REVIEW_REPORT.json self path must end with ENHANCEMENT_REVIEW_REPORT.json"
        )
    if raw_report_path:
        expected_prefix = f"cad/{subsystem}/.cad-spec-gen/runs/{active_run_id}/"
        if not raw_report_path.replace("\\", "/").startswith(expected_prefix):
            raise ValueError(
                "ENHANCEMENT_REVIEW_REPORT.json self path does not match active run: "
                f"{raw_report_path}"
            )


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


def _assert_report_hash(path: Path, expected_hash: Any, label: str) -> None:
    if not expected_hash:
        return
    actual = file_sha256(path)
    if str(expected_hash) != actual:
        raise ValueError(f"{label} hash mismatch: {expected_hash} != {actual}")


def _manifest_render_dir(manifest: dict[str, Any], project_root: Path) -> Path:
    raw = (
        manifest.get("render_dir_abs_resolved")
        or manifest.get("render_dir")
        or manifest.get("render_dir_rel_project")
    )
    if not raw:
        raise ValueError("render manifest is missing render_dir")
    return _resolve_project_path(project_root, raw, "render_dir")


def _resolve_render_path(
    project_root: Path,
    render_dir: Path,
    path: str | Path,
    label: str,
) -> Path:
    if not path:
        raise ValueError(f"{label} is missing")
    resolved = _resolve_project_path(project_root, path, label)
    try:
        resolved.relative_to(render_dir)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside render_dir: {resolved}") from exc
    return resolved


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


def _package_status(
    enhancement_status: str,
    final_deliverable: bool,
    copy_preview: bool,
) -> str:
    if final_deliverable:
        return "delivered"
    if copy_preview:
        return "preview_package"
    if enhancement_status == "accepted":
        return "not_deliverable"
    return "not_deliverable"


def _ordinary_user_message(status: str) -> str:
    messages = {
        "delivered": "最终交付包已生成，可交付照片级 3D 图和证据包。",
        "preview_package": "预览包已生成，但不能作为最终照片级交付。",
        "not_deliverable": "增强验收未通过或证据不完整，未生成最终交付图片。",
    }
    return messages.get(status, "Photo3D delivery package report generated.")


def _write_readme(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Photo3D Delivery Package",
        "",
        f"- subsystem: {report.get('subsystem')}",
        f"- run_id: {report.get('run_id')}",
        f"- status: {report.get('status')}",
        f"- final_deliverable: {report.get('final_deliverable')}",
        f"- enhancement_status: {report.get('enhancement_status')}",
        "",
        "## Reports",
    ]
    for kind, rel_path in sorted((report.get("source_reports") or {}).items()):
        lines.append(f"- {kind}: `{rel_path}`")
    lines.extend(["", "## Deliverables"])
    for category, items in (report.get("deliverables") or {}).items():
        lines.append(f"- {category}: {len(items)}")
    if report.get("blocking_reasons"):
        lines.extend(["", "## Blocking Reasons"])
        for reason in report["blocking_reasons"]:
            code = reason.get("code", "unknown")
            message = reason.get("message", "")
            lines.append(f"- {code}: {message}")
    model_quality = report.get("model_quality_summary")
    if model_quality:
        lines.extend([
            "",
            "## Model Quality",
            f"- model_quality_summary: {model_quality.get('readiness_status')}",
            f"- photoreal_risk: {model_quality.get('photoreal_risk')}",
            f"- review_recommended_count: {model_quality.get('review_recommended_count')}",
            f"- blocking_count: {model_quality.get('blocking_count')}",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
