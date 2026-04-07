"""
enhance_utils.py — Shared utilities for CAD enhance backends.

Canonical implementations of functions shared across fal_comfy_enhancer,
fal_enhancer, and comfyui_enhancer.  Existing backends keep their own
copies for backward-compatibility; new backends import from here.
"""

import logging
import os
import tempfile
import time

log = logging.getLogger("enhance_utils")


# ═══════════════════════════════════════════════════════════════════════════════
# Depth EXR → PNG conversion
# ═══════════════════════════════════════════════════════════════════════════════


def convert_depth_exr_to_png(exr_path, output_path=None, rgb_png_path=None):
    """Convert Blender 32-bit float depth EXR to normalized 0-255 grayscale PNG.

    Near = white (255), far = black (0). Infinity pixels → black.
    If rgb_png_path is given, forces output to match its resolution.

    Returns output PNG path.
    """
    import numpy as np
    from PIL import Image

    try:
        import OpenEXR
        import Imath
        exr_file = OpenEXR.InputFile(exr_path)
        header = exr_file.header()
        dw = header["dataWindow"]
        w = dw.max.x - dw.min.x + 1
        h = dw.max.y - dw.min.y + 1
        pt = Imath.PixelType(Imath.PixelType.FLOAT)
        depth_str = exr_file.channel("R", pt) or exr_file.channel("Z", pt)
        depth = np.frombuffer(depth_str, dtype=np.float32).reshape(h, w)
    except (ImportError, Exception):
        try:
            import imageio
            depth = imageio.imread(exr_path)
            if depth.ndim == 3:
                depth = depth[:, :, 0]
            depth = depth.astype(np.float32)
        except ImportError:
            raise RuntimeError(
                "Cannot read EXR. Install: pip install OpenEXR or pip install imageio"
            )

    finite_mask = np.isfinite(depth) & (depth < 1e9)
    if finite_mask.any():
        fg_values = depth[finite_mask]
        min_depth = np.percentile(fg_values, 1)
        max_depth = np.percentile(fg_values, 99)
    else:
        min_depth = 0.0
        max_depth = 1.0

    clipped = np.clip(depth, min_depth, max_depth)
    if max_depth > min_depth:
        normalized = 1.0 - (clipped - min_depth) / (max_depth - min_depth)
    else:
        normalized = np.zeros_like(depth)
    normalized[~finite_mask] = 0.0
    depth_u8 = (normalized * 255).clip(0, 255).astype(np.uint8)

    img = Image.fromarray(depth_u8, mode="L")

    if rgb_png_path and os.path.isfile(rgb_png_path):
        rgb_size = Image.open(rgb_png_path).size
        if img.size != rgb_size:
            img = img.resize(rgb_size, Image.LANCZOS)

    if output_path is None:
        output_path = exr_path.replace(".exr", "_depth.png")
    img.save(output_path)
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# Depth map locator
# ═══════════════════════════════════════════════════════════════════════════════


def find_depth_for_png(png_path):
    """Locate depth EXR/PNG for a render PNG.

    Returns (depth_png_path, is_temp) or (None, False).
    If an EXR is found, converts to PNG in a temp file (is_temp=True).
    """
    import glob as _glob

    render_dir = os.path.dirname(png_path)
    view_key = os.path.basename(png_path).split("_")[0]  # "V1"

    for exr_candidate in _glob.glob(os.path.join(render_dir, "*depth*.exr")):
        if view_key.lower() in os.path.basename(exr_candidate).lower():
            tmp = tempfile.NamedTemporaryFile(suffix="_depth.png", delete=False)
            tmp.close()
            convert_depth_exr_to_png(exr_candidate, tmp.name, rgb_png_path=png_path)
            return tmp.name, True

    for png_candidate in _glob.glob(os.path.join(render_dir, "*depth*.png")):
        if view_key.lower() in os.path.basename(png_candidate).lower():
            return png_candidate, False

    return None, False


# ═══════════════════════════════════════════════════════════════════════════════
# fal.ai upload with retry
# ═══════════════════════════════════════════════════════════════════════════════


def upload_fal_with_retry(file_path, max_retries=3):
    """Upload file to fal.ai storage with exponential backoff. Returns CDN URL."""
    import fal_client

    for attempt in range(max_retries):
        try:
            return fal_client.upload_file(file_path)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log.warning("  Upload retry %d/%d in %ds: %s",
                            attempt + 1, max_retries - 1, wait, e)
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"fal.ai upload failed after {max_retries} attempts: {e}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# ComfyUI-style prompt helpers
# ═══════════════════════════════════════════════════════════════════════════════


def extract_comfy_positive_prompt(full_prompt, rc, view_key):
    """Distill a short ComfyUI-style positive prompt from unified enhance prompt.

    Extracts MATERIAL ENHANCEMENT section and prepends product/view phrase.
    """
    product = rc.get("product_name", "industrial assembly")
    view_desc = rc.get("camera", {}).get(view_key, {}).get("description", view_key)

    mat_section = ""
    in_mat = False
    for line in full_prompt.splitlines():
        if "MATERIAL ENHANCEMENT" in line:
            in_mat = True
            continue
        if in_mat:
            if line.startswith(("CRITICAL", "MULTI-VIEW", "GEOMETRY", "COORDINATE",
                                 "VIEW:", "ASSEMBLY", "STANDARD")):
                break
            if line.strip():
                mat_section += line.strip() + ", "

    positive = (
        f"photorealistic product render, {product}, {view_desc}, "
        f"studio lighting, sharp focus, 4k, {mat_section.rstrip(', ')}"
    )
    return positive[:500]


def build_comfy_negative_prompt():
    """Standard negative prompt for ComfyUI-based backends."""
    return (
        "cartoon, anime, painting, sketch, illustration, blurry, "
        "low quality, deformed, text, watermark, signature, "
        "extra limbs, missing parts, distorted geometry"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Output download
# ═══════════════════════════════════════════════════════════════════════════════


def download_to_temp(url, fallback_ext=".png", timeout_seconds=120):
    """Download URL to a temp file. Derives extension from URL, falls back to fallback_ext.

    Returns path to the downloaded temp file.
    """
    import urllib.request
    from urllib.parse import urlparse

    # Derive extension from URL path (strip query params)
    url_path = urlparse(url).path
    _, ext = os.path.splitext(url_path)
    if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = fallback_ext

    tmp_out = tempfile.NamedTemporaryFile(suffix=f"_enhanced{ext}", delete=False)
    tmp_out.close()

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            with open(tmp_out.name, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as e:
        # Clean up partial download
        if os.path.isfile(tmp_out.name):
            try:
                os.remove(tmp_out.name)
            except OSError:
                pass
        raise RuntimeError(f"Failed to download {url[:80]}: {e}")

    return tmp_out.name
