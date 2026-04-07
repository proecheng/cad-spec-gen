"""
fal_comfy_enhancer.py — fal.ai Cloud ComfyUI backend for CAD enhance pipeline.

Submits ComfyUI workflows to fal-ai/comfy serverless endpoint.
Combines ComfyUI's fine-grained ControlNet control with fal's cloud GPU
infrastructure — no local GPU required.

Uses the same dual ControlNet (depth + canny) geometry lock as the local
ComfyUI backend, but runs remotely on fal's serverless GPUs.

Function signature matches comfyui_enhancer.enhance_image() for drop-in use.

Requires: pip install fal-client
          Environment variable: FAL_KEY
"""

import copy
import json
import logging
import os

from enhance_utils import (
    upload_fal_with_retry,
    find_depth_for_png,
    extract_comfy_positive_prompt,
    build_comfy_negative_prompt,
    download_to_temp,
)

log = logging.getLogger("fal_comfy_enhancer")

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))

_WORKFLOW_TEMPLATE_DEFAULT = os.path.join(
    SKILL_ROOT, "templates", "fal_comfy_workflow_template.json"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Workflow template loading
# ═══════════════════════════════════════════════════════════════════════════════


def _load_workflow(cfg):
    tpl_path = cfg.get("workflow_template", _WORKFLOW_TEMPLATE_DEFAULT)
    if not os.path.isabs(tpl_path):
        tpl_path = os.path.join(SKILL_ROOT, tpl_path)
    if not os.path.isfile(tpl_path):
        raise FileNotFoundError(
            f"fal ComfyUI workflow template not found: {tpl_path}"
        )
    with open(tpl_path, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# Workflow node lookup helper
# ═══════════════════════════════════════════════════════════════════════════════


def _find_node_id(workflow, title):
    """Find a node ID by its _title tag. Returns str node ID or None."""
    for nid, node in workflow.items():
        if node.get("_title") == title:
            return nid
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Workflow patching for fal-ai/comfy
# ═══════════════════════════════════════════════════════════════════════════════


def _patch_workflow(workflow, input_url, depth_url, positive, negative, cfg):
    """Patch workflow template with runtime values for fal-ai/comfy.

    Key difference from local ComfyUI: model names are replaced with
    HuggingFace download URLs so fal can fetch them on-the-fly.

    Does NOT strip _title tags — caller does that after patching is complete.
    """
    checkpoint_url = cfg.get(
        "checkpoint_url",
        "https://huggingface.co/SG161222/Realistic_Vision_V6.0_B1_noVAE/resolve/main/Realistic_Vision_V6.0_B1_fp16-no-ema.safetensors"
    )
    depth_model_url = cfg.get(
        "controlnet_depth_url",
        "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11f1p_sd15_depth.pth"
    )
    canny_model_url = cfg.get(
        "controlnet_canny_url",
        "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_canny.pth"
    )
    denoise = cfg.get("denoise_strength", 0.45)
    cfg_scale = cfg.get("cfg_scale", 7.0)
    steps = cfg.get("steps", 25)
    canny_strength = cfg.get("canny_strength", 0.8)
    depth_strength = cfg.get("depth_strength", 0.95)
    seed = cfg.get("seed", -1)  # -1 = random

    has_depth = depth_url is not None

    for node_id, node in list(workflow.items()):
        title = node.get("_title", "")
        inputs = node.get("inputs", {})

        if title == "checkpoint":
            inputs["ckpt_name"] = checkpoint_url
        elif title == "positive_prompt":
            inputs["text"] = positive
        elif title == "negative_prompt":
            inputs["text"] = negative
        elif title == "input_image":
            inputs["image"] = input_url
        elif title == "depth_image":
            if has_depth:
                inputs["image"] = depth_url
        elif title == "controlnet_depth":
            inputs["control_net_name"] = depth_model_url
        elif title == "controlnet_canny":
            inputs["control_net_name"] = canny_model_url
        elif title == "apply_canny_controlnet":
            inputs["strength"] = canny_strength
        elif title == "apply_depth_controlnet":
            inputs["strength"] = depth_strength
        elif title == "ksampler":
            inputs["denoise"] = denoise
            inputs["cfg"] = cfg_scale
            inputs["steps"] = steps
            if seed >= 0:
                inputs["seed"] = seed

    # If no depth map, remove depth nodes and rewire KSampler to canny output
    if not has_depth:
        # Find canny apply node ID dynamically (never hardcode node IDs)
        canny_apply_id = _find_node_id(workflow, "apply_canny_controlnet")

        for nid in list(workflow.keys()):
            t = workflow[nid].get("_title", "")
            if t in ("controlnet_depth", "depth_image", "apply_depth_controlnet"):
                del workflow[nid]

        if canny_apply_id:
            for node in workflow.values():
                if node.get("_title") == "ksampler":
                    node["inputs"]["positive"] = [canny_apply_id, 0]

    return workflow


def _strip_titles(workflow):
    """Remove _title metadata tags — fal-ai/comfy expects clean ComfyUI API format."""
    for node in workflow.values():
        node.pop("_title", None)


# ═══════════════════════════════════════════════════════════════════════════════
# Main enhance function
# ═══════════════════════════════════════════════════════════════════════════════


def enhance_image(png_path, prompt, fal_comfy_cfg, view_key, rc):
    """Enhance a Blender render using fal-ai/comfy (cloud ComfyUI).

    Function signature matches comfyui_enhancer.enhance_image() for drop-in use.

    Args:
        png_path:       str, absolute path to source Blender PNG
        prompt:         str, unified enhance prompt
        fal_comfy_cfg:  dict, pipeline_config.json["enhance"]["fal_comfy"]
        view_key:       str, e.g. "V1", "V2"
        rc:             dict, render_config.json

    Returns:
        str: path to generated enhanced image (caller renames)

    Raises:
        RuntimeError on API failure
        ImportError if fal-client not installed
    """
    import fal_client

    # Build prompts
    positive = extract_comfy_positive_prompt(prompt, rc, view_key)
    negative = build_comfy_negative_prompt()
    log.info("  [fal_comfy] Positive prompt (%d chars): %s", len(positive), positive[:100])

    # Upload input PNG to fal CDN
    input_url = upload_fal_with_retry(png_path)
    log.info("  [fal_comfy] Uploaded input: %s", os.path.basename(png_path))

    # Find and upload depth map
    depth_url = None
    depth_tmp = None
    depth_path, is_temp = find_depth_for_png(png_path)
    if depth_path:
        depth_url = upload_fal_with_retry(depth_path)
        if is_temp:
            depth_tmp = depth_path
        log.info("  [fal_comfy] Depth map: %s", os.path.basename(depth_path))
    else:
        log.warning("  [fal_comfy] No depth map for %s — canny-only mode",
                    os.path.basename(png_path))

    # Load workflow template and deepcopy so template dict stays clean for reuse
    workflow = copy.deepcopy(_load_workflow(fal_comfy_cfg))
    workflow = _patch_workflow(
        workflow, input_url, depth_url, positive, negative, fal_comfy_cfg
    )
    # Strip _title tags as final step (after all _title-based lookups are done)
    _strip_titles(workflow)

    # Submit to fal-ai/comfy
    endpoint = fal_comfy_cfg.get("endpoint", "fal-ai/comfy")
    log.info("  [fal_comfy] Submitting workflow to %s for %s",
             endpoint, os.path.basename(png_path))

    try:
        # fal_client.subscribe does not accept timeout kwarg
        result = fal_client.subscribe(
            endpoint,
            arguments={"comfy_json": workflow},
            with_logs=True,
        )
    finally:
        if depth_tmp and os.path.isfile(depth_tmp):
            try:
                os.remove(depth_tmp)
            except OSError:
                pass

    # Extract output image URL
    if not result or "images" not in result or not result["images"]:
        raise RuntimeError(
            f"fal-ai/comfy returned no images. Response: {json.dumps(result, default=str)[:500]}"
        )

    output_url = result["images"][0]["url"]
    log.info("  [fal_comfy] Got output: %s", output_url[:80])

    # Download with correct extension derived from URL (SaveImage defaults to PNG)
    tmp_path = download_to_temp(output_url, fallback_ext=".png")

    log.info("  [fal_comfy] Downloaded: %s (%.0fKB)",
             os.path.basename(tmp_path),
             os.path.getsize(tmp_path) / 1024)
    return tmp_path
