from __future__ import annotations

import json
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

_BADGE_POSITIVE = {"delivered", "accepted", "ready", "continue_photo3d"}
_BADGE_WARN = {"preview", "preview_package", "needs_review", "unknown", "not_run"}
_BADGE_BLOCK = {"not_deliverable", "blocked", "not_available"}
_BADGE_LABELS = {
    "delivered": "已交付",
    "accepted": "已验收",
    "ready": "就绪",
    "continue_photo3d": "可继续",
    "preview": "预览",
    "preview_package": "预览包",
    "needs_review": "建议复核",
    "unknown": "未知",
    "not_run": "未做",
    "not_deliverable": "未交付",
    "blocked": "阻断",
    "not_available": "无数据",
}

_NEXT_ACTION_LABELS = {
    "import_missing_models": "先导入缺失的 3D 模型",
    "review_models": "先复核标黄的零件",
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
    jury_section = _build_jury_section(run_dir, root)
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
        "jury": jury_section,
        "delivery_dir": project_relative(delivery_dir, root),
        "source_reports": source_reports,
        "deliverables": deliverables,
        "view_evidence": _view_evidence_summary(manifest),
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


def _view_evidence_summary(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """从 render_manifest 提取逐视角可见实例证据（队列 C 的 evidence_method / visible_instance_ids）。

    manifest 既没 evidence_method 也没任何 per-view visible_instance_ids → 返 None（向后兼容）。
    """
    method = manifest.get("evidence_method")
    per_view = {
        str(f.get("view")): list(f.get("visible_instance_ids"))
        for f in (manifest.get("files") or [])
        if isinstance(f, dict)
        and f.get("view")
        and isinstance(f.get("visible_instance_ids"), list)
    }
    if not method and not per_view:
        return None
    return {"evidence_method": method, "per_view": per_view}


def _build_jury_section(
    run_dir: Path,
    project_root: Path,
) -> dict[str, Any] | None:
    """jury 跑过则返 jury 字段；否则返 None。

    PHOTO3D_JURY_REPORT.json 不存在 / 解析失败 / I/O 失败均返 None；
    存在则抽 status / actual_cost_usd / vendor_request_ids / schema_version
    + jury_review_input.json 路径（accepted 时存在）。
    """
    jury_report_path = run_dir / "PHOTO3D_JURY_REPORT.json"
    if not jury_report_path.is_file():
        return None
    try:
        rep = json.loads(jury_report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(rep, dict):
        return None
    review_input_path = run_dir / "jury_review_input.json"
    review_input_rel: str | None = (
        project_relative(review_input_path, project_root)
        if review_input_path.is_file()
        else None
    )
    vendor_ids: list[str] = []
    for v in rep.get("views", []) or []:
        if not isinstance(v, dict):
            continue
        meta = v.get("llm_meta")
        if not isinstance(meta, dict):
            continue
        vid = meta.get("vendor_request_id")
        if vid:
            vendor_ids.append(str(vid))
    raw_meta = rep.get("jury_meta")
    jury_meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    return {
        "report": project_relative(jury_report_path, project_root),
        "review_input": review_input_rel,
        "status": rep.get("status"),
        "actual_cost_usd": jury_meta.get("actual_cost_usd"),
        "vendor_request_ids": vendor_ids,
        "jury_report_schema_version": rep.get("schema_version"),
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


def _pkg_path_relative_to_delivery(package_path: str, delivery_dir: str) -> str:
    """把 project-relative 的 package_path 转成相对 delivery_dir 的 posix 路径。

    README 写在 delivery/ 下，所以图链接要相对 delivery_dir。两个入参都是 project-relative；
    正常情况 package_path 在 delivery_dir 内（cad/.../runs/RUN001/delivery/enhanced/V1.jpg →
    enhanced/V1.jpg）。路径异常（不在 delivery_dir 内）时退化为 basename，绝不抛异常。
    """
    try:
        return Path(package_path).relative_to(Path(delivery_dir)).as_posix()
    except ValueError:
        return Path(package_path).name


def _status_badge(status: object) -> str:
    """状态枚举值 → 「图标 中文」徽章。未知值用中性「·」+原值，绝不误判成 ✗。"""
    key = str(status or "").strip()
    label = _BADGE_LABELS.get(key, key or "未知")
    if key in _BADGE_POSITIVE:
        return f"✓ {label}"
    if key in _BADGE_WARN:
        return f"⚠ {label}"
    if key in _BADGE_BLOCK:
        return f"✗ {label}"
    return f"· {key}" if key else "· 未知"


def _readme_headline(report: dict[str, Any]) -> list[str]:
    """生成 README 头条区块：标题行 + 状态徽章行 + 通用人话句引用块。"""
    subsystem = report.get("subsystem") or "?"
    run_id = report.get("run_id") or "?"
    final = "是" if report.get("final_deliverable") is True else "否"
    lines = [
        f"# 交付包验收 — {subsystem} / {run_id}",
        "",
        f"**状态**：{_status_badge(report.get('status'))}  ·  "
        f"增强：{_status_badge(report.get('enhancement_status'))}  ·  "
        f"最终交付物：{final}",
    ]
    message = report.get("ordinary_user_message") or ""
    if message:
        lines += ["", f"> {message}"]
    return lines


def _readme_images_section(report: dict[str, Any]) -> list[str]:
    """生成渲染图区块：每个视角一个子标题 + 内嵌图 + 零件数 + 带标注版链接。

    若无 enhanced_images 则返回空列表（整段省略）。
    """
    deliverables = report.get("deliverables") or {}
    enhanced = deliverables.get("enhanced_images") or []
    if not enhanced:
        return []
    delivery_dir = str(report.get("delivery_dir") or "")
    labeled_by_view = {
        str(item.get("view")): item
        for item in (deliverables.get("labeled_images") or [])
        if isinstance(item, dict) and item.get("view")
    }
    per_view = (report.get("view_evidence") or {}).get("per_view") or {}
    lines: list[str] = ["", "## 渲染图（增强后）"]
    for item in enhanced:
        if not isinstance(item, dict):
            continue
        view = str(item.get("view") or "")
        rel = _pkg_path_relative_to_delivery(str(item.get("package_path") or ""), delivery_dir)
        lines += ["", f"### {view}", f"![{view} 增强图]({rel})"]
        ids = per_view.get(view)
        if isinstance(ids, list):
            lines.append(f"- 本图标着含 {len(ids)} 个零件")
        labeled = labeled_by_view.get(view)
        if isinstance(labeled, dict):
            lab_rel = _pkg_path_relative_to_delivery(
                str(labeled.get("package_path") or ""), delivery_dir
            )
            lines.append(f"- [带标注版]({lab_rel})")
    return lines


def _readme_view_evidence_section(report: dict[str, Any]) -> list[str]:
    """生成完整性证据区块：证据方式 + 各视角实例计数 + 详细说明。

    若 view_evidence 为 None 或缺失则返回空列表（整段省略）。
    """
    view_evidence = report.get("view_evidence")
    if not view_evidence:
        return []
    method = view_evidence.get("evidence_method") or "?"
    per_view = view_evidence.get("per_view") or {}
    counts = "、".join(
        f"{view}={len(ids)}"
        for view, ids in sorted(per_view.items())
        if isinstance(ids, list)
    )
    lines: list[str] = ["", "## 完整性证据", f"- 证据方式：{method}"]
    if counts:
        lines.append(f"- 各视角实例计数：{counts}")
    lines.append(
        "- 详细逐视角实例清单见 `DELIVERY_PACKAGE.json` 的 `view_evidence` 字段 / "
        "`render_manifest.json`；完整性 PASS/BLOCKED 判定见 `RENDER_VISUAL_REGRESSION.json`"
        "（若已跑过 `photo3d-render-check`）"
    )
    return lines


def _readme_model_quality_section(report: dict[str, Any]) -> list[str]:
    """生成模型质量区块：用户可读摘要 + 就绪状态 + 照片级风险 + 复核/阻断计数。

    若 model_quality_summary 为 None 或缺失则返回空列表（整段省略）。
    """
    summary = report.get("model_quality_summary")
    if not summary:
        return []
    lines = ["", "## 模型质量"]
    message = summary.get("ordinary_user_message") or ""
    if message:
        lines.append(f"> {message}")
    lines += [
        f"- 就绪状态：{summary.get('readiness_status') or '?'}  ·  "
        f"照片级风险：{summary.get('photoreal_risk') or '?'}",
        f"- 建议复核 {summary.get('review_recommended_count') or 0} 个零件  ·  "
        f"阻断 {summary.get('blocking_count') or 0} 个",
        "（来源：`MODEL_CONTRACT.json`，与本 run 绑定）",
    ]
    return lines


def _readme_review_status_section(report: dict[str, Any]) -> list[str]:
    """生成复核状态四行表：质量 / AI 增强 / 语义复核 / jury 评分。"""
    quality_status = (report.get("quality_summary") or {}).get("status")
    semantic = report.get("semantic_material_review") or {}
    semantic_status = semantic.get("status")
    if semantic_status == "accepted":
        semantic_cell = _status_badge("accepted")
    elif semantic_status == "not_run":
        semantic_cell = "⚠ 必需但未做" if semantic.get("required") else "⚠ 未做（非强制）"
    else:
        semantic_cell = _status_badge(semantic_status)
        review_report = semantic.get("review_report")
        if review_report:
            semantic_cell += f"（见 `{review_report}`）"
    jury = report.get("jury")
    if not jury:
        jury_cell = "⚠ 未运行"
    else:
        jury_status = jury.get("status")
        jury_cell = _status_badge(jury_status)
        if jury_status == "accepted":
            cost = jury.get("actual_cost_usd")
            if cost is not None:
                jury_cell += f"（成本 ${cost}）"
    return [
        "",
        "## 复核状态",
        "| 项 | 状态 |",
        "|---|---|",
        f"| 增强图质量（quality_summary）| {_status_badge(quality_status)} |",
        f"| AI 增强（enhancement）| {_status_badge(report.get('enhancement_status'))} |",
        f"| 语义/材质复核（semantic_material_review）| {semantic_cell} |",
        f"| AI 视觉评分（jury）| {jury_cell} |",
    ]


def _readme_next_step_section(report: dict[str, Any]) -> list[str]:
    """生成下一步指引：阻断 → 建议动作 → 已交付 → 兜底，三层决策树。"""
    lines = ["", "## 下一步"]
    if report.get("blocking_reasons"):
        lines.append("✗ 当前有阻断项（见下方「阻断项」），处理后重新运行 `photo3d-deliver`。")
        return lines
    summary = report.get("model_quality_summary") or {}
    kind = str((summary.get("recommended_next_action") or {}).get("kind") or "").strip()
    if kind in _NEXT_ACTION_LABELS:
        lines.append(f"⚠ 建议{_NEXT_ACTION_LABELS[kind]}，再交付。")
        return lines
    if report.get("status") == "delivered":
        lines.append("✓ 交付完成，无需进一步动作。")
        return lines
    lines.append("⚠ 见上方各项状态。")
    return lines


def _readme_blocking_section(report: dict[str, Any]) -> list[str]:
    """生成阻断项清单。阻断列表为空或缺失时返回空列表（整段省略）。"""
    reasons = report.get("blocking_reasons") or []
    if not reasons:
        return []
    lines = ["", "## 阻断项"]
    for reason in reasons:
        if not isinstance(reason, dict):
            lines.append(f"- {reason}")
            continue
        code = reason.get("code") or "unknown"
        message = reason.get("message") or ""
        lines.append(f"- {code}: {message}" if message else f"- {code}")
    return lines


def _readme_evidence_appendix(report: dict[str, Any]) -> list[str]:
    """生成证据清单附录：报告文件 + 交付物计数 + 证据文件列表 + delivery_dir 说明。"""
    lines = ["", "---", "## 证据清单（供审计）", "", "**报告**"]
    for kind, rel_path in sorted((report.get("source_reports") or {}).items()):
        lines.append(f"- {kind}: `{rel_path}`")
    deliverables = report.get("deliverables") or {}
    lines += [
        "",
        "**交付物**",
        f"- 源渲染：{len(deliverables.get('source_images') or [])} 张",
        f"- 增强图：{len(deliverables.get('enhanced_images') or [])} 张",
        f"- 标注图：{len(deliverables.get('labeled_images') or [])} 张",
        "",
        "**证据文件**",
    ]
    for item in report.get("evidence_files") or []:
        package_path = item.get("package_path") if isinstance(item, dict) else None
        if package_path:
            lines.append(f"- `{package_path}`")
    lines += [
        "",
        f"*本文件由 `photo3d-deliver` 自动生成于交付包目录"
        f"（`{report.get('delivery_dir') or ''}`）。"
        "`DELIVERY_PACKAGE.json` 是机器可读的完整证据清单。*",
    ]
    return lines


def _write_readme(path: Path, report: dict[str, Any]) -> None:
    """把交付包 report 渲染成外行用户可读的验收页 README.md。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines += _readme_headline(report)
    lines += _readme_images_section(report)
    lines += _readme_view_evidence_section(report)
    lines += _readme_model_quality_section(report)
    lines += _readme_review_status_section(report)
    lines += _readme_next_step_section(report)
    lines += _readme_blocking_section(report)
    lines += _readme_evidence_appendix(report)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
