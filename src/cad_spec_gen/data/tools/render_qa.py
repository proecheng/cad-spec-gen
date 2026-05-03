from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, UnidentifiedImageError

from tools.contract_io import file_sha256, load_json_required, stable_json_hash, write_json_atomic
from tools.path_policy import assert_within_project, project_relative


MIN_WIDTH = 128
MIN_HEIGHT = 128
MIN_OBJECT_OCCUPANCY = 0.01
MAX_OBJECT_OCCUPANCY = 0.98


def qa_image(path: str | Path) -> dict[str, Any]:
    image_path = Path(path)
    if not image_path.exists():
        return _invalid_image_result(image_path, "missing_image", "image file does not exist")
    try:
        with Image.open(image_path) as image:
            width, height = image.size
            rgba = image.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        return _invalid_image_result(image_path, "invalid_image", str(exc))

    alpha = rgba.getchannel("A")
    alpha_histogram = alpha.histogram()
    opaque_pixels = sum(alpha_histogram[9:])
    transparent = opaque_pixels == 0

    bbox = None
    occupancy = 0.0
    cropped = False
    if not transparent:
        background = Image.new("RGBA", rgba.size, _corner_background_color(rgba))
        diff = ImageChops.difference(rgba, background).convert("L")
        mask = diff.point(lambda value: 255 if value > 18 else 0)
        bbox = mask.getbbox()
        if bbox:
            subject_pixels = mask.histogram()[255]
            occupancy = subject_pixels / float(width * height)
            cropped = bbox[0] <= 0 or bbox[1] <= 0 or bbox[2] >= width or bbox[3] >= height

    nonblank = bool(bbox) and occupancy > 0.0
    reasons = []
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        reasons.append("low_resolution")
    if transparent:
        reasons.append("transparent_image")
    if not nonblank:
        reasons.append("blank_image")
    if nonblank and occupancy < MIN_OBJECT_OCCUPANCY:
        reasons.append("low_object_occupancy")
    if occupancy > MAX_OBJECT_OCCUPANCY:
        reasons.append("background_not_detectable")
    if cropped:
        reasons.append("cropped_subject")

    return {
        "path": str(image_path),
        "sha256": file_sha256(image_path),
        "width": width,
        "height": height,
        "nonblank": nonblank,
        "transparent": transparent,
        "object_occupancy": round(occupancy, 6),
        "cropped": cropped,
        "bbox_px": list(bbox) if bbox else None,
        "passed": not reasons,
        "reasons": reasons,
    }


def build_render_manifest(
    project_root: str | Path,
    render_dir: str | Path,
    files: list[str | Path],
    *,
    subsystem: str,
    run_id: str,
    path_context_hash: str | None,
    product_graph: dict[str, Any] | str | Path | None = None,
    model_contract: dict[str, Any] | str | Path | None = None,
    assembly_signature: dict[str, Any] | str | Path | None = None,
    render_config_path: str | Path | None = None,
    glb_path: str | Path | None = None,
    render_script_path: str | Path | None = None,
    partial: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_render_dir = Path(render_dir).resolve()
    assert_within_project(resolved_render_dir, root, "render_dir")

    product_graph_payload, product_graph_path = _load_optional_json(product_graph, root, "product graph")
    model_contract_payload, model_contract_path = _load_optional_json(model_contract, root, "model contract")
    assembly_signature_payload, assembly_signature_path = _load_optional_json(
        assembly_signature,
        root,
        "assembly signature",
    )
    render_config = _load_optional_path_json(render_config_path, root, "render config")
    camera_config = render_config.get("camera") if isinstance(render_config, dict) else None
    material_config = _material_config(render_config)

    manifest_files = []
    legacy_files = []
    blocking_reasons = []
    for image_file in sorted((Path(path).resolve() for path in files), key=lambda p: str(p).lower()):
        assert_within_project(image_file, root, "render output file")
        image_qa = qa_image(image_file)
        if not image_qa["passed"]:
            blocking_reasons.append({
                "code": "render_qa_failed",
                "path_rel_project": project_relative(image_file, root),
                "reasons": list(image_qa.get("reasons", [])),
                "message": "Render image failed QA checks.",
            })
        legacy_files.append(str(image_file))
        manifest_files.append({
            "view": _view_key(image_file),
            "path_rel_project": project_relative(image_file, root),
            "path_abs_resolved": str(image_file),
            "sha256": image_qa["sha256"],
            "width": image_qa["width"],
            "height": image_qa["height"],
            "qa": {
                key: value
                for key, value in image_qa.items()
                if key not in {"path", "sha256", "width", "height"}
            },
        })

    status = "blocked" if blocking_reasons else "pass"
    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "status": status,
        "run_id": run_id,
        "subsystem": subsystem,
        "path_context_hash": path_context_hash,
        "render_dir_rel_project": project_relative(resolved_render_dir, root),
        "render_dir_abs_resolved": str(resolved_render_dir),
        "render_dir": str(resolved_render_dir),
        "product_graph_hash": stable_json_hash(product_graph_payload) if product_graph_payload is not None else None,
        "product_graph_path": _rel_or_none(product_graph_path, root),
        "model_contract_hash": stable_json_hash(model_contract_payload) if model_contract_payload is not None else None,
        "model_contract_path": _rel_or_none(model_contract_path, root),
        "assembly_signature_hash": (
            stable_json_hash(assembly_signature_payload)
            if assembly_signature_payload is not None
            else None
        ),
        "assembly_signature_path": _rel_or_none(assembly_signature_path, root),
        "render_config_hash": _file_hash_or_none(render_config_path, root),
        "render_config_path": _path_rel_or_none(render_config_path, root),
        "camera_hash": stable_json_hash(camera_config) if camera_config is not None else None,
        "material_config_hash": stable_json_hash(material_config) if material_config is not None else None,
        "glb_hash": _file_hash_or_none(glb_path, root),
        "glb_path": _path_rel_or_none(glb_path, root),
        "render_script_hash": _file_hash_or_none(render_script_path, root),
        "render_script_path": _path_rel_or_none(render_script_path, root),
        "partial": bool(partial),
        "blocking_reasons": blocking_reasons,
        "files": manifest_files,
        "legacy_files": legacy_files,
    }


def write_render_manifest(
    project_root: str | Path,
    render_dir: str | Path,
    files: list[str | Path],
    *,
    subsystem: str,
    run_id: str,
    path_context_hash: str | None,
    product_graph: dict[str, Any] | str | Path | None = None,
    model_contract: dict[str, Any] | str | Path | None = None,
    assembly_signature: dict[str, Any] | str | Path | None = None,
    render_config_path: str | Path | None = None,
    glb_path: str | Path | None = None,
    render_script_path: str | Path | None = None,
    partial: bool = False,
) -> Path:
    manifest = build_render_manifest(
        project_root,
        render_dir,
        files,
        subsystem=subsystem,
        run_id=run_id,
        path_context_hash=path_context_hash,
        product_graph=product_graph,
        model_contract=model_contract,
        assembly_signature=assembly_signature,
        render_config_path=render_config_path,
        glb_path=glb_path,
        render_script_path=render_script_path,
        partial=partial,
    )
    return write_json_atomic(Path(render_dir) / "render_manifest.json", manifest)


def require_render_manifest(render_dir: str | Path, *, explicit: bool = True) -> Path:
    manifest_path = Path(render_dir) / "render_manifest.json"
    if manifest_path.is_file():
        return manifest_path
    if explicit:
        raise FileNotFoundError(f"render_manifest.json not found in explicit render dir: {render_dir}")
    raise FileNotFoundError(f"render_manifest.json not found: {manifest_path}")


def manifest_image_paths(
    manifest: dict[str, Any],
    *,
    project_root: str | Path | None = None,
    require_qa_passed: bool = False,
) -> list[str]:
    root = Path(project_root).resolve() if project_root is not None else _infer_project_root(manifest)
    render_dir = _manifest_render_dir(manifest, root)
    paths = []
    for entry in manifest.get("files", []):
        if isinstance(entry, dict) and require_qa_passed and not (entry.get("qa") or {}).get("passed", True):
            raise ValueError(f"render QA failed for manifest entry: {_entry_label(entry)}")
        if isinstance(entry, str):
            paths.append(str(_resolve_manifest_path(entry, root, render_dir)))
        elif isinstance(entry, dict):
            path = entry.get("path_abs_resolved") or entry.get("path") or entry.get("path_rel_project")
            if path:
                paths.append(str(_resolve_manifest_path(path, root, render_dir)))
    if not paths:
        for path in manifest.get("legacy_files", []):
            paths.append(str(_resolve_manifest_path(path, root, render_dir)))
    return paths


def manifest_blocks_enhance(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = list(manifest.get("blocking_reasons") or [])
    if manifest.get("status") == "blocked" and not reasons:
        reasons.append({
            "code": "render_manifest_blocked",
            "message": "Render manifest is blocked.",
        })
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        qa = entry.get("qa") or {}
        if qa.get("passed") is False:
            reasons.append({
                "code": "render_qa_failed",
                "path": _entry_label(entry),
                "reasons": list(qa.get("reasons", [])),
                "message": "Render image failed QA checks.",
            })
    return reasons


def _invalid_image_result(image_path: Path, reason: str, error: str) -> dict[str, Any]:
    sha256 = file_sha256(image_path) if image_path.exists() and image_path.is_file() else None
    return {
        "path": str(image_path),
        "sha256": sha256,
        "width": 0,
        "height": 0,
        "nonblank": False,
        "transparent": False,
        "object_occupancy": 0.0,
        "cropped": False,
        "bbox_px": None,
        "passed": False,
        "reasons": [reason],
        "error": error,
    }


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


def _infer_project_root(manifest: dict[str, Any]) -> Path:
    render_dir = manifest.get("render_dir_abs_resolved") or manifest.get("render_dir")
    if render_dir:
        path = Path(render_dir).resolve()
        parts = path.parts
        for index in range(len(parts) - 2):
            if parts[index].lower() == "cad" and parts[index + 1].lower() == "output":
                return Path(*parts[:index]).resolve()
    return Path.cwd().resolve()


def _manifest_render_dir(manifest: dict[str, Any], project_root: Path) -> Path:
    raw = (
        manifest.get("render_dir_abs_resolved")
        or manifest.get("render_dir")
        or manifest.get("render_dir_rel_project")
        or "."
    )
    path = Path(raw)
    resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
    assert_within_project(resolved, project_root, "manifest render_dir")
    return resolved


def _resolve_manifest_path(path_value: str | Path, project_root: Path, render_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        project_candidate = (project_root / path).resolve()
        render_candidate = (render_dir / path).resolve()
        resolved = project_candidate if _is_within(project_candidate, project_root) else render_candidate
    if not _is_within(resolved, project_root):
        raise ValueError(f"Manifest image path is outside project: {resolved}")
    if not _is_within(resolved, render_dir):
        raise ValueError(f"Manifest image path is outside render_dir: {resolved}")
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _entry_label(entry: dict[str, Any]) -> str:
    return str(entry.get("path_rel_project") or entry.get("path_abs_resolved") or entry.get("path") or "(unknown)")


def _load_optional_json(
    value: dict[str, Any] | str | Path | None,
    project_root: Path,
    label: str,
) -> tuple[dict[str, Any] | None, Path | None]:
    if value is None:
        return None, None
    if isinstance(value, dict):
        return dict(value), None
    path = _project_path(value, project_root, label)
    if not path.is_file():
        return None, None
    return load_json_required(path, label), path


def _load_optional_path_json(
    value: str | Path | None,
    project_root: Path,
    label: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    path = _project_path(value, project_root, label)
    if not path.is_file():
        return None
    try:
        return load_json_required(path, label)
    except ValueError:
        return None


def _project_path(value: str | Path, project_root: Path, label: str) -> Path:
    requested = Path(value)
    path = requested if requested.is_absolute() else project_root / requested
    path = path.resolve()
    assert_within_project(path, project_root, label)
    return path


def _material_config(render_config: dict[str, Any] | None) -> Any:
    if not isinstance(render_config, dict):
        return None
    present = {
        key: render_config[key]
        for key in ("materials", "material_presets", "components")
        if key in render_config
    }
    if set(present) == {"materials"}:
        return present["materials"]
    return present or None


def _view_key(path: Path) -> str:
    match = re.match(r"^(V\d+)", path.name, re.IGNORECASE)
    return match.group(1).upper() if match else path.stem


def _file_hash_or_none(value: str | Path | None, project_root: Path) -> str | None:
    if value is None:
        return None
    path = _project_path(value, project_root, "hash input")
    return file_sha256(path) if path.is_file() else None


def _path_rel_or_none(value: str | Path | None, project_root: Path) -> str | None:
    if value is None:
        return None
    path = _project_path(value, project_root, "path input")
    return project_relative(path, project_root) if path.exists() else None


def _rel_or_none(path: Path | None, project_root: Path) -> str | None:
    return project_relative(path, project_root) if path is not None else None
