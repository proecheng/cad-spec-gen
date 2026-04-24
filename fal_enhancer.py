"""
fal_enhancer.py — fal.ai Flux ControlNet backend for CAD enhance pipeline.

Uses Flux ControlNet Union (depth + canny) to hard-lock geometry while
enhancing surface materials to photorealistic quality.

Function signature matches comfyui_enhancer.enhance_image() for drop-in use.

Requires: pip install fal-client
          Environment variable: FAL_KEY
"""

import logging
import os
import tempfile
import time

log = logging.getLogger("fal_enhancer")


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

    # Try OpenEXR first, fall back to imageio
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

    # Separate foreground from background (Blender uses 1e10 for sky)
    finite_mask = np.isfinite(depth) & (depth < 1e9)
    if finite_mask.any():
        fg_values = depth[finite_mask]
        min_depth = np.percentile(fg_values, 1)   # robust min (ignore outliers)
        max_depth = np.percentile(fg_values, 99)   # robust max
    else:
        min_depth = 0.0
        max_depth = 1.0

    # Clip to foreground range, then normalize to 0-255 (near=white, far=black)
    clipped = np.clip(depth, min_depth, max_depth)
    if max_depth > min_depth:
        normalized = 1.0 - (clipped - min_depth) / (max_depth - min_depth)
    else:
        normalized = np.zeros_like(depth)
    # Background pixels (sky) → black (far)
    normalized[~finite_mask] = 0.0
    depth_u8 = (normalized * 255).clip(0, 255).astype(np.uint8)

    img = Image.fromarray(depth_u8, mode="L")

    # Force same resolution as RGB PNG
    if rgb_png_path and os.path.isfile(rgb_png_path):
        rgb_size = Image.open(rgb_png_path).size  # (w, h)
        if img.size != rgb_size:
            img = img.resize(rgb_size, Image.LANCZOS)

    if output_path is None:
        output_path = exr_path.replace(".exr", "_depth.png")
    img.save(output_path)
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# Flux prompt distillation
# ═══════════════════════════════════════════════════════════════════════════════


def _distill_prompt_for_flux(full_prompt, rc, view_key):
    """Distill unified enhance prompt to Flux-optimal short form (~200 chars).

    Flux prefers positive descriptive prompts, NOT negative instructions.
    Extracts: product name + top 3 material descriptions + lighting.
    """
    pv = rc.get("prompt_vars", {})
    product = pv.get("product_name", "precision mechanical assembly")

    # Extract material descriptions
    mat_descs = pv.get("material_descriptions", [])
    mat_parts = []
    for d in mat_descs[:3]:
        desc = d.get("material_desc", "")
        if desc:
            # Take first 50 chars of each material description
            mat_parts.append(desc[:50].rstrip(",. "))

    mat_text = ", ".join(mat_parts) if mat_parts else "brushed aluminum and dark anodized metal"

    return (
        f"photorealistic product render, {product}, "
        f"{mat_text}, "
        f"studio lighting, sharp focus, 4k professional product photography, "
        f"engineering precision, clean background"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Upload with retry
# ═══════════════════════════════════════════════════════════════════════════════


def _upload_with_retry(file_path, max_retries=3):
    """Upload file to fal.ai storage with exponential backoff retry."""
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
# Find depth map for a given render PNG
# ═══════════════════════════════════════════════════════════════════════════════


def _find_depth_for_png(png_path):
    """Locate the depth EXR/PNG corresponding to a render PNG.

    Search order:
    1. {stem}_depth_.exr (Blender render pass output)
    2. {stem}_depth.png (pre-converted)
    3. {dir}/V{N}_depth_*.exr (glob pattern)

    Returns (depth_png_path, is_temp) or (None, False).
    """
    import glob as _glob

    stem = os.path.splitext(png_path)[0]
    render_dir = os.path.dirname(png_path)

    # 1. Exact match: {stem}_depth_.exr
    exr_exact = stem.replace(os.path.basename(stem),
                              os.path.basename(stem).split("_")[0] + "_depth_")
    for exr_candidate in _glob.glob(os.path.join(render_dir, "*depth*.exr")):
        # Match by view key (V1, V2, etc.)
        view_key = os.path.basename(png_path).split("_")[0]  # "V1"
        if view_key.lower() in os.path.basename(exr_candidate).lower():
            # Convert EXR → PNG
            tmp = tempfile.NamedTemporaryFile(suffix="_depth.png", delete=False)
            tmp.close()
            convert_depth_exr_to_png(exr_candidate, tmp.name, rgb_png_path=png_path)
            return tmp.name, True

    # 2. Pre-converted PNG
    for png_candidate in _glob.glob(os.path.join(render_dir, "*depth*.png")):
        view_key = os.path.basename(png_path).split("_")[0]
        if view_key.lower() in os.path.basename(png_candidate).lower():
            return png_candidate, False

    return None, False


# ═══════════════════════════════════════════════════════════════════════════════
# Main enhance function
# ═══════════════════════════════════════════════════════════════════════════════


def enhance_image(png_path, prompt, fal_cfg, view_key, rc):
    """Enhance a Blender render using fal.ai Flux ControlNet.

    Function signature matches comfyui_enhancer.enhance_image() for drop-in use.

    Args:
        png_path:  str, absolute path to source Blender PNG
        prompt:    str, unified enhance prompt (will be distilled for Flux)
        fal_cfg:   dict, pipeline_config.json["enhance"]["fal"]
        view_key:  str, e.g. "V1", "V2"
        rc:        dict, render_config.json

    Returns:
        str: path to generated enhanced image (caller renames)

    Raises:
        RuntimeError on API failure after retries
        ImportError if fal-client not installed
    """
    import fal_client

    # Distill prompt for Flux (short, positive, no negations)
    flux_prompt = _distill_prompt_for_flux(prompt, rc, view_key)
    log.info("  Flux prompt (%d chars): %s", len(flux_prompt), flux_prompt[:80])

    # Upload source image
    render_url = _upload_with_retry(png_path)

    # Find and upload depth map (optional but strongly recommended)
    depth_url = None
    depth_tmp = None
    depth_path, is_temp = _find_depth_for_png(png_path)
    if depth_path:
        depth_url = _upload_with_retry(depth_path)
        if is_temp:
            depth_tmp = depth_path
        log.info("  Depth map: %s", os.path.basename(depth_path))
    else:
        log.warning("  No depth map found for %s — canny-only mode (weaker geometry lock)",
                    os.path.basename(png_path))

    # Build ControlNet configuration
    canny_model = fal_cfg.get("controlnet_canny", "InstantX/FLUX.1-dev-Controlnet-Canny")
    depth_model = fal_cfg.get("controlnet_depth", "Shakker-Labs/FLUX.1-dev-ControlNet-Depth")
    canny_strength = fal_cfg.get("canny_strength", 0.75)
    depth_strength = fal_cfg.get("depth_strength", 0.7)
    canny_end = fal_cfg.get("canny_end_pct", 0.8)
    depth_end = fal_cfg.get("depth_end_pct", 0.8)
    steps = fal_cfg.get("steps", 28)
    guidance = fal_cfg.get("guidance_scale", 3.5)
    img2img_strength = fal_cfg.get("img2img_strength", 0.45)

    controlnets = [
        {
            "path": canny_model,
            "control_image_url": render_url,
            "conditioning_scale": canny_strength,
            "start_percentage": 0.0,
            "end_percentage": canny_end,
        },
    ]
    if depth_url and depth_strength > 0:
        controlnets.append({
            "path": depth_model,
            "control_image_url": depth_url,
            "conditioning_scale": depth_strength,
            "start_percentage": 0.0,
            "end_percentage": depth_end,
        })

    # Track C: v1_anchor — 将 V1 增强结果替换 canny 参考图
    hero = fal_cfg.get("hero_image")
    if hero and os.path.isfile(hero):
        hero_url = _upload_with_retry(hero)
        controlnets[0]["control_image_url"] = hero_url
        log.info("  v1_anchor: canny 参考替换为 hero_image %s", os.path.basename(hero))

    # Determine endpoint: img2img (preserves geometry) vs txt2img
    endpoint = fal_cfg.get("model", "fal-ai/flux-general")
    use_img2img = fal_cfg.get("img2img", True)  # default: img2img for geometry preservation
    if use_img2img:
        endpoint = endpoint.rstrip("/") + "/image-to-image"

    api_args = {
        "prompt": flux_prompt,
        "num_inference_steps": steps,
        "guidance_scale": guidance,
        "num_images": 1,
        "output_format": "jpeg",
        "enable_safety_checker": False,
        "controlnets": controlnets,
    }
    if use_img2img:
        api_args["image_url"] = render_url
        api_args["strength"] = img2img_strength
    else:
        api_args["image_size"] = "landscape_16_9"

    # Track C: 固定 seed（None 时不传，保持随机）
    _seed = fal_cfg.get("seed")
    if _seed is not None:
        api_args["seed"] = int(_seed)

    log.info("  Endpoint: %s (img2img=%s, strength=%.2f)",
             endpoint, use_img2img, img2img_strength if use_img2img else 0)

    # Call fal.ai API
    try:
        result = fal_client.subscribe(
            endpoint,
            arguments=api_args,
            with_logs=False,
        )
    finally:
        # Clean up temp depth PNG
        if depth_tmp and os.path.isfile(depth_tmp):
            try:
                os.remove(depth_tmp)
            except OSError:
                pass

    # Download result image
    if not result or "images" not in result or not result["images"]:
        raise RuntimeError("fal.ai returned no images")

    output_url = result["images"][0]["url"]

    # Download to temp file
    import urllib.request
    tmp_out = tempfile.NamedTemporaryFile(suffix="_enhanced.jpg", delete=False)
    tmp_out.close()
    urllib.request.urlretrieve(output_url, tmp_out.name)

    log.info("  fal.ai output: %s (%.0fKB)",
             os.path.basename(tmp_out.name),
             os.path.getsize(tmp_out.name) / 1024)
    return tmp_out.name
