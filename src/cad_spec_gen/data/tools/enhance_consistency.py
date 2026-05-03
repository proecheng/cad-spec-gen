from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, UnidentifiedImageError


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
