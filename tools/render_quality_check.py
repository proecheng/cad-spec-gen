from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageFilter, ImageStat

from cad_paths import get_blender_path
from tools.artifact_index import get_active_artifacts
from tools.contract_io import file_sha256, load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.render_qa import qa_image


MIN_RENDER_CONTRAST_STDDEV = 12.0
MIN_EDGE_DENSITY = 0.005


def run_render_quality_check(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    output_path: str | Path | None = None,
    blender_path: str | Path | None = None,
    version_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Check active-run Blender availability and screenshot pixel quality."""
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
    active_run_dir = _default_run_dir(root, subsystem, active_run_id or "unknown")
    blocking_reasons: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    artifact_paths: dict[str, Path] = {}
    active_artifacts = get_active_artifacts(index)
    render_manifest_raw = active_artifacts.get("render_manifest")
    if not render_manifest_raw:
        blocking_reasons.append({
            "code": "artifact_index_missing_required_artifact",
            "artifact": "render_manifest",
            "message": "渲染质量检查缺少当前 active run 的 render_manifest.json。",
        })
        render_manifest = {}
    else:
        artifact_paths["render_manifest"] = _resolve_project_path(
            root,
            render_manifest_raw,
            "active render manifest",
        )
        render_manifest = load_json_required(
            artifact_paths["render_manifest"],
            "active render manifest",
        )

    run_id = active_run_id
    active_run_dir = _default_run_dir(root, subsystem, run_id or "unknown")
    if render_manifest:
        blocking_reasons.extend(_check_manifest_identity(subsystem, run_id, render_manifest))
        blocking_reasons.extend(_check_active_render_dir(root, subsystem, run_id, render_manifest))

    blender_preflight = _blender_preflight(
        root,
        blender_path=blender_path,
        version_runner=version_runner,
    )
    if blender_preflight["status"] == "blocked":
        blocking_reasons.extend(blender_preflight["blocking_reasons"])

    views: list[dict[str, Any]] = []
    quality_records: list[dict[str, Any]] = []
    if render_manifest:
        file_reasons, views, quality_records = _check_render_files(root, render_manifest)
        blocking_reasons.extend(file_reasons)

    render_quality_summary = _build_render_quality_summary(quality_records)
    warnings.extend(render_quality_summary["warnings"])

    status = "blocked" if blocking_reasons else ("warning" if warnings else "pass")
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "subsystem": subsystem,
        "status": status,
        "ordinary_user_message": _ordinary_user_message(status, blocking_reasons, warnings),
        "blender_preflight": blender_preflight,
        "render_quality_summary": render_quality_summary,
        "views": views,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "artifacts": {
            "artifact_index": project_relative(index_path, root),
            **{
                key: project_relative(path, root)
                for key, path in artifact_paths.items()
            },
        },
    }
    target = _resolve_project_path(
        root,
        output_path or active_run_dir / "RENDER_QUALITY_REPORT.json",
        "render quality report output",
    )
    try:
        target.relative_to(active_run_dir.resolve())
    except ValueError as exc:
        raise ValueError("render quality report output must stay in the active run directory") from exc
    report["artifacts"]["render_quality_report"] = project_relative(target, root)
    write_json_atomic(target, report)
    return report


def command_return_code_for_render_quality_check(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {"pass", "warning"} else 1


def _blender_preflight(
    project_root: Path,
    *,
    blender_path: str | Path | None,
    version_runner: Callable[..., Any] | None,
) -> dict[str, Any]:
    raw_path = blender_path or get_blender_path()
    if not raw_path:
        return {
            "status": "blocked",
            "path": None,
            "version": None,
            "blocking_reasons": [{
                "code": "blender_not_found",
                "message": "未找到 Blender 可执行文件，不能证明 Phase 4 渲染环境可用。",
            }],
            "warnings": [],
        }
    blender = Path(raw_path)
    if not blender.is_absolute():
        blender = (project_root / blender).resolve()
    else:
        blender = blender.resolve()
    if not blender.is_file():
        return {
            "status": "blocked",
            "path": project_relative(blender, project_root) if _is_within(blender, project_root) else str(blender),
            "version": None,
            "blocking_reasons": [{
                "code": "blender_not_found",
                "path": str(blender),
                "message": "Blender 可执行文件路径不存在。",
            }],
            "warnings": [],
        }
    runner = version_runner or subprocess.run
    try:
        completed = runner(
            [str(blender), "--background", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive around external executable
        return {
            "status": "blocked",
            "path": str(blender),
            "version": None,
            "blocking_reasons": [{
                "code": "blender_version_check_failed",
                "error": str(exc),
                "message": "Blender 版本预检执行失败。",
            }],
            "warnings": [],
        }
    output = f"{getattr(completed, 'stdout', '')}\n{getattr(completed, 'stderr', '')}"
    version = _parse_blender_version(output)
    if int(getattr(completed, "returncode", 1) or 0) != 0:
        return {
            "status": "blocked",
            "path": str(blender),
            "version": version,
            "blocking_reasons": [{
                "code": "blender_version_check_failed",
                "returncode": int(getattr(completed, "returncode", 1) or 1),
                "message": "Blender 版本预检返回非零退出码。",
            }],
            "warnings": [],
        }
    return {
        "status": "pass",
        "path": str(blender),
        "version": version,
        "blocking_reasons": [],
        "warnings": [],
    }


def _check_manifest_identity(
    subsystem: str,
    run_id: str,
    render_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    reasons = []
    if render_manifest.get("subsystem") != subsystem:
        reasons.append({
            "code": "subsystem_mismatch",
            "expected": subsystem,
            "actual": render_manifest.get("subsystem"),
            "message": "render_manifest.json 不属于当前子系统。",
        })
    if render_manifest.get("run_id") != run_id:
        reasons.append({
            "code": "run_id_mismatch",
            "expected": run_id,
            "actual": render_manifest.get("run_id"),
            "message": "render_manifest.json 不属于当前 active run。",
        })
    return reasons


def _check_active_render_dir(
    project_root: Path,
    subsystem: str,
    run_id: str,
    render_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    render_dir, reason = _manifest_render_dir_or_reason(project_root, render_manifest)
    if reason:
        return [reason]
    expected = (project_root / "cad" / "output" / "renders" / subsystem / run_id).resolve()
    if render_dir != expected:
        return [{
            "code": "render_dir_not_active_run",
            "expected": project_relative(expected, project_root),
            "actual": project_relative(render_dir, project_root),
            "message": "渲染清单的 render_dir 不属于当前 active run。",
        }]
    return []


def _check_render_files(
    project_root: Path,
    render_manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []
    quality_records: list[dict[str, Any]] = []
    render_dir, reason = _manifest_render_dir_or_reason(project_root, render_manifest)
    if reason:
        return [reason], views, quality_records
    files = render_manifest.get("files", [])
    if not files:
        reasons.append({
            "code": "render_manifest_empty",
            "message": "render_manifest.json 没有登记任何渲染图片。",
        })
        return reasons, views, quality_records
    for entry in files:
        if not isinstance(entry, dict):
            continue
        view = str(entry.get("view") or "")
        image_path = _entry_image_path(project_root, render_dir, entry)
        view_record: dict[str, Any] = {
            "view": view,
            "path": project_relative(image_path, project_root) if image_path else None,
            "status": "pass",
        }
        if not image_path:
            reasons.append({
                "code": "render_file_path_missing",
                "view": view,
                "message": "渲染清单中的视角缺少图片路径。",
            })
            view_record["status"] = "blocked"
            views.append(view_record)
            continue
        try:
            image_path.relative_to(render_dir)
        except ValueError:
            reasons.append({
                "code": "render_file_outside_render_dir",
                "view": view,
                "path": project_relative(image_path, project_root),
                "message": "渲染图片不在当前 active run 的 render_dir 内。",
            })
            view_record["status"] = "blocked"
            views.append(view_record)
            continue
        if not image_path.is_file():
            reasons.append({
                "code": "render_file_missing",
                "view": view,
                "path": project_relative(image_path, project_root),
                "message": "渲染图片文件不存在。",
            })
            view_record["status"] = "blocked"
            views.append(view_record)
            continue
        expected_hash = entry.get("sha256")
        actual_hash = file_sha256(image_path)
        if expected_hash != actual_hash:
            reasons.append({
                "code": "render_file_hash_mismatch",
                "view": view,
                "path": project_relative(image_path, project_root),
                "expected": expected_hash,
                "actual": actual_hash,
                "message": "渲染图片内容已不同于 render_manifest.json 登记的文件。",
            })
            view_record["status"] = "blocked"
            views.append(view_record)
            continue
        qa = qa_image(image_path)
        if not qa.get("passed"):
            reasons.append({
                "code": "render_qa_failed",
                "view": view,
                "path": project_relative(image_path, project_root),
                "reasons": list(qa.get("reasons", [])),
                "message": "渲染图片基础 QA 未通过。",
            })
            view_record["status"] = "blocked"
        metrics = _pixel_metrics(image_path, qa)
        quality_records.append({"view": view, **metrics})
        view_record["pixel_metrics"] = metrics
        view_record["qa"] = {
            key: value
            for key, value in qa.items()
            if key not in {"path", "sha256"}
        }
        views.append(view_record)
    return reasons, views, quality_records


def _pixel_metrics(path: Path, image_qa: dict[str, Any]) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        hsv = rgb.convert("HSV")
        gray = rgb.convert("L")
        luminance = ImageStat.Stat(gray)
        saturation = ImageStat.Stat(hsv.getchannel("S"))
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
    edge_density = float(edge_stat.mean[0]) / 255.0
    return {
        "width": int(image_qa.get("width") or rgb.width),
        "height": int(image_qa.get("height") or rgb.height),
        "object_occupancy": float(image_qa.get("object_occupancy") or 0.0),
        "luminance_mean": round(float(luminance.mean[0]), 6),
        "contrast_stddev": round(float(luminance.stddev[0]), 6),
        "saturation_mean": round(float(saturation.mean[0]), 6),
        "edge_density": round(edge_density, 6),
    }


def _build_render_quality_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    canvas_sizes = sorted({(int(item["width"]), int(item["height"])) for item in records})
    if not records:
        return {
            "schema_version": 1,
            "status": "blocked",
            "view_count": 0,
            "canvas_sizes": [],
            "min_contrast_stddev": MIN_RENDER_CONTRAST_STDDEV,
            "min_edge_density": MIN_EDGE_DENSITY,
            "warnings": [],
        }
    if len(canvas_sizes) > 1:
        warnings.append({
            "code": "render_quality_inconsistent_canvas",
            "canvas_sizes": [list(size) for size in canvas_sizes],
            "message": "多视角渲染画布尺寸不一致。",
        })
    for item in records:
        if float(item.get("contrast_stddev") or 0.0) < MIN_RENDER_CONTRAST_STDDEV:
            warnings.append({
                "code": "render_quality_low_contrast",
                "view": item["view"],
                "contrast_stddev": item.get("contrast_stddev"),
                "min_contrast_stddev": MIN_RENDER_CONTRAST_STDDEV,
                "message": "渲染截图对比度过低，需要复查灯光、材质或相机。",
            })
        if float(item.get("edge_density") or 0.0) < MIN_EDGE_DENSITY:
            warnings.append({
                "code": "render_quality_low_edge_density",
                "view": item["view"],
                "edge_density": item.get("edge_density"),
                "min_edge_density": MIN_EDGE_DENSITY,
                "message": "渲染截图边缘信息过少，可能缺少可辨识结构。",
            })
    return {
        "schema_version": 1,
        "status": "warning" if warnings else "pass",
        "view_count": len(records),
        "canvas_sizes": [list(size) for size in canvas_sizes],
        "min_contrast_stddev": MIN_RENDER_CONTRAST_STDDEV,
        "min_edge_density": MIN_EDGE_DENSITY,
        "warnings": warnings,
    }


def _entry_image_path(
    project_root: Path,
    render_dir: Path,
    entry: dict[str, Any],
) -> Path | None:
    raw = entry.get("path_abs_resolved") or entry.get("path") or entry.get("path_rel_project")
    if not raw:
        return None
    requested = Path(raw)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, "render image")
    return resolved


def _manifest_render_dir(project_root: Path, render_manifest: dict[str, Any]) -> Path:
    render_dir, reason = _manifest_render_dir_or_reason(project_root, render_manifest)
    if reason:
        raise ValueError(reason["message"])
    assert render_dir is not None
    return render_dir


def _manifest_render_dir_or_reason(
    project_root: Path,
    render_manifest: dict[str, Any],
) -> tuple[Path | None, dict[str, Any] | None]:
    raw = (
        render_manifest.get("render_dir_abs_resolved")
        or render_manifest.get("render_dir")
        or render_manifest.get("render_dir_rel_project")
    )
    if not raw:
        return None, {
            "code": "render_dir_missing",
            "message": "render_manifest.json 缺少 render_dir，不能证明图片属于当前 active run。",
        }
    return _resolve_project_path(project_root, raw, "render manifest render_dir"), None


def _parse_blender_version(output: str) -> str | None:
    match = re.search(r"Blender\s+(\d+(?:\.\d+){1,2})", output)
    return match.group(1) if match else None


def _ordinary_user_message(
    status: str,
    blocking_reasons: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    if status == "pass":
        return "Blender 预检和渲染截图质量检查通过，可以继续 Phase 4 视觉回归或照片级增强。"
    if status == "warning":
        first = warnings[0].get("message") if warnings else "存在非阻断警告。"
        return f"渲染截图质量有警告：{first}"
    first = blocking_reasons[0].get("message") if blocking_reasons else "存在阻断问题。"
    return f"渲染质量检查已停止：{first}"


def _default_run_dir(project_root: Path, subsystem: str, run_id: str) -> Path:
    return project_root / "cad" / subsystem / ".cad-spec-gen" / "runs" / run_id


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
