#!/usr/bin/env python3
"""
comfyui_enhancer.py — ComfyUI backend for cad-skill enhance pipeline.

Replaces gemini_gen.py subprocess for users with a local GPU.
Uses ControlNet depth + canny to hard-lock geometry; only surface
materials are changed by the diffusion model.

Interface (called from cad_pipeline.cmd_enhance):
    result = enhance_image(png_path, prompt, cfg, view_key, rc)
    # Returns output_path (str) on success, raises RuntimeError on failure.
"""

import json
import logging
import os
import time
import uuid

log = logging.getLogger(__name__)

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))

# ── Workflow template (node IDs are stable references) ───────────────────────
_WORKFLOW_TEMPLATE_DEFAULT = os.path.join(
    SKILL_ROOT, "templates", "comfyui_workflow_template.json"
)


def _load_workflow(cfg):
    tpl_path = cfg.get("workflow_template", _WORKFLOW_TEMPLATE_DEFAULT)
    if not os.path.isabs(tpl_path):
        tpl_path = os.path.join(SKILL_ROOT, tpl_path)
    if not os.path.isfile(tpl_path):
        raise FileNotFoundError(
            f"ComfyUI workflow template not found: {tpl_path}\n"
            "  Run: python comfyui_env_check.py  for setup guidance."
        )
    with open(tpl_path, encoding="utf-8") as f:
        return json.load(f)


# ── Prompt extraction from unified enhance prompt ─────────────────────────────

def _extract_positive_prompt(full_prompt, rc, view_key):
    """
    Distill a short ComfyUI-style positive prompt from the unified enhance
    prompt.  We pull the MATERIAL ENHANCEMENT section (most relevant) and
    prepend a product/view phrase.
    """
    product = rc.get("product_name", "industrial assembly")
    view_desc = rc.get("camera", {}).get(view_key, {}).get("description", view_key)

    # Extract material section from full prompt
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
    return positive[:500]  # ComfyUI clips very long prompts


def _build_negative_prompt():
    return (
        "cartoon, anime, painting, sketch, illustration, blurry, "
        "low quality, deformed, text, watermark, signature, "
        "extra limbs, missing parts, distorted geometry"
    )


# ── Workflow patching ─────────────────────────────────────────────────────────

def _patch_workflow(workflow, png_path, positive, negative, cfg):
    """
    Fill the workflow template with runtime values.
    Node IDs are defined in the template; we look them up by title tag.
    """
    checkpoint = cfg.get("checkpoint", "realisticVisionV60B1_v51VAE.safetensors")
    depth_model = cfg.get("controlnet_depth_model", "control_v11f1p_sd15_depth.pth")
    canny_model = cfg.get("controlnet_canny_model", "control_v11p_sd15_canny.pth")
    denoise = cfg.get("denoise_strength", 0.45)
    cfg_scale = cfg.get("cfg_scale", 7.0)
    steps = cfg.get("steps", 25)

    for node_id, node in workflow.items():
        title = node.get("_title", "")
        inputs = node.get("inputs", {})

        if title == "checkpoint":
            inputs["ckpt_name"] = checkpoint
        elif title == "positive_prompt":
            inputs["text"] = positive
        elif title == "negative_prompt":
            inputs["text"] = negative
        elif title == "input_image":
            inputs["image"] = png_path
        elif title == "controlnet_depth":
            inputs["control_net_name"] = depth_model
        elif title == "controlnet_canny":
            inputs["control_net_name"] = canny_model
        elif title == "ksampler":
            inputs["denoise"] = denoise
            inputs["cfg"] = cfg_scale
            inputs["steps"] = steps

    return workflow


# ── ComfyUI REST API helpers ──────────────────────────────────────────────────

def _api_url(cfg, path):
    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", 8188)
    return f"http://{host}:{port}{path}"


def _submit_workflow(workflow, cfg):
    """POST workflow to ComfyUI, return prompt_id."""
    import requests
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    resp = requests.post(_api_url(cfg, "/prompt"), json=payload, timeout=30)
    if not resp.ok:
        import logging as _log
        _log.getLogger(__name__).error("ComfyUI /prompt error: %s", resp.text[:2000])
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ComfyUI rejected workflow: {data['error']}")
    return data["prompt_id"], client_id


def _poll_until_done(prompt_id, cfg, timeout):
    """Poll /history until prompt_id appears. Returns output images list."""
    import requests
    deadline = time.time() + timeout
    poll_interval = 3
    while time.time() < deadline:
        time.sleep(poll_interval)
        resp = requests.get(_api_url(cfg, f"/history/{prompt_id}"), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if prompt_id in data:
                outputs = data[prompt_id].get("outputs", {})
                # Find first node with images
                for node_output in outputs.values():
                    imgs = node_output.get("images", [])
                    if imgs:
                        return imgs
        poll_interval = min(poll_interval * 1.3, 15)
    raise TimeoutError(f"ComfyUI did not finish within {timeout}s")


def _download_image(image_info, cfg, dest_path):
    """Download generated image from ComfyUI /view endpoint."""
    import requests
    params = {
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    }
    resp = requests.get(_api_url(cfg, "/view"), params=params, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(resp.content)


# ── Public entry point ────────────────────────────────────────────────────────

def enhance_image(png_path, prompt, comfyui_cfg, view_key, rc):
    """
    Run ComfyUI enhancement on a single PNG.

    Args:
        png_path     : absolute path to source PNG
        prompt       : filled unified enhance prompt (used to extract material desc)
        comfyui_cfg  : pipeline_config.json["enhance"]["comfyui"] dict
        view_key     : e.g. "V1"
        rc           : render_config dict (for product_name, camera info)

    Returns:
        output_path  : path to the generated image (in ComfyUI output dir,
                       before cad_pipeline renames it to *_enhanced.jpg)

    Raises:
        RuntimeError / TimeoutError on failure
    """
    try:
        import requests  # noqa — validate import early
    except ImportError:
        raise RuntimeError(
            "'requests' package not found. Run: pip install requests"
        )

    timeout = comfyui_cfg.get("timeout", 300)

    # Build prompts
    positive = _extract_positive_prompt(prompt, rc, view_key)
    negative = _build_negative_prompt()
    log.debug("  ComfyUI positive prompt: %s", positive[:120])

    # Upload input image to ComfyUI
    import requests as _req
    _host = comfyui_cfg.get("host", "127.0.0.1")
    _port = comfyui_cfg.get("port", 8188)
    with open(png_path, "rb") as _f:
        _up = _req.post(
            f"http://{_host}:{_port}/upload/image",
            files={"image": (os.path.basename(png_path), _f, "image/png")},
            data={"overwrite": "true"},
            timeout=30,
        )
    _up.raise_for_status()
    _uploaded_name = _up.json()["name"]
    log.info("  [comfyui] Uploaded input image as %s", _uploaded_name)

    # Track C: v1_anchor — 上传 hero_image 供 workflow 使用
    _hero_uploaded = None
    _hero = comfyui_cfg.get("hero_image")
    if _hero and os.path.isfile(_hero):
        with open(_hero, "rb") as _hf:
            _hr = _req.post(
                f"http://{_host}:{_port}/upload/image",
                files={"image": (os.path.basename(_hero), _hf, "image/jpeg")},
                data={"overwrite": "true"},
                timeout=30,
            )
        _hr.raise_for_status()
        _hero_uploaded = _hr.json()["name"]
        log.info("  [comfyui] v1_anchor hero_image uploaded as %s", _hero_uploaded)

    # Load and patch workflow
    workflow = _load_workflow(comfyui_cfg)
    workflow = _patch_workflow(workflow, _uploaded_name, positive, negative, comfyui_cfg)

    # Track C: v1_anchor — hero_image が指定された場合、_patch_workflow が設定した
    # レンダリング PNG を V1 hero で上書き（V2-V4 が V1 スタイルを参照するため）
    if _hero_uploaded:
        for node in workflow.values():
            if node.get("_title") == "input_image":
                node["inputs"]["image"] = _hero_uploaded
                break
    _comfyui_seed = comfyui_cfg.get("seed")
    if _comfyui_seed is not None:
        for node in workflow.values():
            if node.get("_title") == "ksampler":
                node["inputs"]["seed"] = int(_comfyui_seed)
                break

    # Submit
    log.info("  [comfyui] Submitting workflow for %s", os.path.basename(png_path))
    prompt_id, _ = _submit_workflow(workflow, comfyui_cfg)
    log.info("  [comfyui] prompt_id=%s, polling...", prompt_id)

    # Poll
    images = _poll_until_done(prompt_id, comfyui_cfg, timeout)
    if not images:
        raise RuntimeError("ComfyUI returned no output images")

    # Download first output image to a temp path alongside the source PNG
    img_info = images[0]
    ext = os.path.splitext(img_info["filename"])[1] or ".png"
    tmp_out = os.path.join(
        os.path.dirname(png_path),
        f"_comfyui_tmp_{uuid.uuid4().hex[:8]}{ext}"
    )
    _download_image(img_info, comfyui_cfg, tmp_out)
    log.info("  [comfyui] Downloaded output: %s", os.path.basename(tmp_out))
    return tmp_out
