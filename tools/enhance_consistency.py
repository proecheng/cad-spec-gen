from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, UnidentifiedImageError

from tools.contract_io import file_sha256, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.render_qa import qa_image


def compare_enhanced_image(
    source_image: str | Path,
    enhanced_image: str | Path,
    *,
    min_similarity: float = 0.85,
) -> dict[str, Any]:
    source_path = Path(source_image)
    enhanced_path = Path(enhanced_image)
    try:
        source_mask = _subject_mask(source_path)
        enhanced_mask = _subject_mask(enhanced_path, size=source_mask.size)
    except (OSError, UnidentifiedImageError) as exc:
        return {
            "schema_version": 1,
            "source_image": str(source_path),
            "enhanced_image": str(enhanced_path),
            "status": "preview",
            "edge_similarity": 0.0,
            "min_similarity": float(min_similarity),
            "blocking_reasons": [{
                "code": "enhancement_consistency_unavailable",
                "message": "无法读取增强一致性检查所需图片。",
                "error": str(exc),
            }],
        }

    similarity = _mask_iou(source_mask, enhanced_mask)
    blocking_reasons = []
    status = "accepted"
    if similarity < min_similarity:
        status = "preview"
        blocking_reasons.append({
            "code": "enhancement_shape_drift",
            "message": "增强图轮廓与 CAD 渲染参考不一致，只能作为预览。",
            "edge_similarity": round(similarity, 6),
            "min_similarity": float(min_similarity),
        })
    return {
        "schema_version": 1,
        "source_image": str(source_path),
        "enhanced_image": str(enhanced_path),
        "status": status,
        "edge_similarity": round(similarity, 6),
        "min_similarity": float(min_similarity),
        "blocking_reasons": blocking_reasons,
    }


def build_enhancement_report(
    project_root: str | Path,
    render_manifest: dict[str, Any],
    *,
    enhanced_images: list[str | Path] | None = None,
    min_similarity: float = 0.85,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    render_dir = _manifest_render_dir(render_manifest, root)
    sources = _manifest_sources(render_manifest, root, render_dir)
    enhanced_by_view = _enhanced_candidates_by_view(
        root,
        render_dir,
        enhanced_images if enhanced_images is not None else _discover_enhanced_images(render_dir),
    )
    report_path = (
        _resolve_project_path(root, output_path, "enhancement report output")
        if output_path is not None
        else render_dir / "ENHANCEMENT_REPORT.json"
    )
    _assert_within(report_path, render_dir, "enhancement report output", "render_dir")

    views: list[dict[str, Any]] = []
    blocking_reasons: list[dict[str, Any]] = []
    has_preview = False
    if not sources:
        blocking_reasons.append({
            "code": "render_manifest_no_sources",
            "message": "渲染清单没有可验收的源视角，不能生成照片级交付状态。",
        })
    for source in sources:
        view = source["view"]
        enhanced_candidates = enhanced_by_view.get(view, [])
        if not enhanced_candidates:
            reason = {
                "code": "enhanced_view_missing",
                "view": view,
                "message": "增强验收缺少与渲染清单视角对应的增强图。",
            }
            blocking_reasons.append(reason)
            views.append({
                "view": view,
                "status": "blocked",
                "source_image": source["path_rel_project"],
                "enhanced_image": None,
                "blocking_reasons": [reason],
            })
            continue
        if len(enhanced_candidates) > 1:
            reason = {
                "code": "enhanced_view_ambiguous",
                "view": view,
                "candidates": [
                    project_relative(path, root) for path in enhanced_candidates
                ],
                "message": "增强验收发现同一视角有多个候选增强图，不能猜测哪一个可交付。",
            }
            blocking_reasons.append(reason)
            views.append({
                "view": view,
                "status": "blocked",
                "source_image": source["path_rel_project"],
                "enhanced_image": None,
                "blocking_reasons": [reason],
            })
            continue

        enhanced_path = enhanced_candidates[0]

        comparison = compare_enhanced_image(
            source["path_abs_resolved"],
            enhanced_path,
            min_similarity=min_similarity,
        )
        source_qa = qa_image(source["path_abs_resolved"])
        enhanced_qa = qa_image(enhanced_path)
        view_reasons = list(comparison.get("blocking_reasons") or [])
        if not enhanced_qa.get("passed"):
            view_reasons.append({
                "code": "enhanced_image_qa_failed",
                "view": view,
                "reasons": list(enhanced_qa.get("reasons") or []),
                "message": "增强图未通过基础图片 QA。",
            })
        if view_reasons:
            has_preview = True
            blocking_reasons.extend(
                {**reason, "view": reason.get("view", view)}
                for reason in view_reasons
            )
        view_status = "preview" if view_reasons else "accepted"
        views.append({
            "view": view,
            "status": view_status,
            "source_image": source["path_rel_project"],
            "enhanced_image": project_relative(enhanced_path, root),
            "source_sha256": source.get("sha256") or file_sha256(source["path_abs_resolved"]),
            "enhanced_sha256": file_sha256(enhanced_path),
            "edge_similarity": comparison.get("edge_similarity"),
            "min_similarity": float(min_similarity),
            "source_qa": _compact_qa(source_qa),
            "enhanced_qa": _compact_qa(enhanced_qa),
            "blocking_reasons": view_reasons,
        })

    status = "blocked" if blocking_reasons and not views else (
        "blocked" if any(view["status"] == "blocked" for view in views) else (
        "preview" if has_preview else "accepted"
        )
    )
    return {
        "schema_version": 1,
        "run_id": str(render_manifest.get("run_id") or ""),
        "subsystem": str(render_manifest.get("subsystem") or ""),
        "status": status,
        "delivery_status": status,
        "ordinary_user_message": _ordinary_user_message(status),
        "render_manifest": project_relative(
            _manifest_path(render_manifest, root, render_dir),
            root,
        ),
        "render_dir": project_relative(render_dir, root),
        "enhancement_report": project_relative(report_path, root),
        "view_count": len(sources),
        "enhanced_view_count": len([view for view in views if view.get("enhanced_image")]),
        "min_similarity": float(min_similarity),
        "views": views,
        "blocking_reasons": blocking_reasons,
    }


def write_enhancement_report(
    project_root: str | Path,
    render_manifest: dict[str, Any],
    *,
    enhanced_images: list[str | Path] | None = None,
    min_similarity: float = 0.85,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    report = build_enhancement_report(
        project_root,
        render_manifest,
        enhanced_images=enhanced_images,
        min_similarity=min_similarity,
        output_path=output_path,
    )
    target = _resolve_project_path(
        Path(project_root).resolve(),
        report["enhancement_report"],
        "enhancement report output",
    )
    write_json_atomic(target, report)
    return report


def _subject_mask(path: Path, *, size: tuple[int, int] | None = None) -> Image.Image:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
    if size is not None and rgba.size != size:
        rgba = rgba.resize(size)
    background = Image.new("RGBA", rgba.size, _corner_background_color(rgba))
    diff = ImageChops.difference(rgba, background).convert("L")
    return diff.point(lambda value: 255 if value > 18 else 0)


def _mask_iou(a: Image.Image, b: Image.Image) -> float:
    a_pixels = a.point(lambda value: 1 if value else 0)
    b_pixels = b.point(lambda value: 1 if value else 0)
    intersection = 0
    union = 0
    for av, bv in zip(a_pixels.tobytes(), b_pixels.tobytes()):
        if av or bv:
            union += 1
            if av and bv:
                intersection += 1
    if union == 0:
        return 1.0
    return intersection / union


def _corner_background_color(image: Image.Image) -> tuple[int, int, int, int]:
    width, height = image.size
    pixels = image.load()
    corners = [
        pixels[0, 0],
        pixels[width - 1, 0],
        pixels[0, height - 1],
        pixels[width - 1, height - 1],
    ]
    return tuple(int(sum(pixel[i] for pixel in corners) / len(corners)) for i in range(4))


def _ordinary_user_message(status: str) -> str:
    messages = {
        "accepted": "增强一致性验收通过，可作为照片级交付。",
        "preview": "增强图已生成但存在结构、轮廓或遮挡风险，只能作为预览。",
        "blocked": "增强验收缺少必需视角或输入不完整，不能交付。",
    }
    return messages.get(status, "增强一致性验收已生成报告。")


def _manifest_sources(
    manifest: dict[str, Any],
    project_root: Path,
    render_dir: Path,
) -> list[dict[str, Any]]:
    sources = []
    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            continue
        view = str(entry.get("view") or _view_key(entry.get("path_rel_project") or entry.get("path_abs_resolved") or ""))
        raw_path = entry.get("path_abs_resolved") or entry.get("path_rel_project") or entry.get("path")
        if not raw_path:
            continue
        path = _resolve_render_path(project_root, render_dir, raw_path, "manifest source image")
        sources.append({
            "view": view,
            "path_abs_resolved": path,
            "path_rel_project": project_relative(path, project_root),
            "sha256": entry.get("sha256"),
        })
    return sources


def _enhanced_candidates_by_view(
    project_root: Path,
    render_dir: Path,
    enhanced_images: list[str | Path],
) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    seen: set[Path] = set()
    for image in enhanced_images:
        path = _resolve_render_path(project_root, render_dir, image, "enhanced image")
        if path in seen:
            continue
        seen.add(path)
        view = _view_key(path.name)
        if view:
            result.setdefault(view, []).append(path)
    return result


def _discover_enhanced_images(render_dir: Path) -> list[Path]:
    return sorted(
        set(render_dir.glob("V*_enhanced.*")) | set(render_dir.glob("V*_*_enhanced.*")),
        key=lambda path: path.name.lower(),
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


def _manifest_path(manifest: dict[str, Any], project_root: Path, render_dir: Path) -> Path:
    raw = manifest.get("manifest_path") or render_dir / "render_manifest.json"
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    if len(path.parts) == 1:
        return (render_dir / path).resolve()
    return (project_root / path).resolve()


def _resolve_render_path(
    project_root: Path,
    render_dir: Path,
    path: str | Path,
    label: str,
) -> Path:
    resolved = _resolve_project_path(project_root, path, label)
    _assert_within(resolved, render_dir, label, "render_dir")
    return resolved


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved


def _assert_within(path: Path, parent: Path, label: str, parent_label: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside {parent_label}: {path}") from exc


def _view_key(path_value: str | Path) -> str:
    name = Path(path_value).name
    return name.split("_", 1)[0]


def _compact_qa(qa: dict[str, Any]) -> dict[str, Any]:
    return {
        key: qa.get(key)
        for key in (
            "width",
            "height",
            "nonblank",
            "object_occupancy",
            "cropped",
            "bbox_px",
            "passed",
            "reasons",
        )
    }
