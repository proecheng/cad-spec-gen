#!/usr/bin/env python3
"""
comfyui_env_check.py — Check and guide ComfyUI environment setup.

Usage:
    python comfyui_env_check.py          # full check + guidance
    python comfyui_env_check.py --quiet  # return exit code only (0=ok, 1=issues)

Returns:
    0  all requirements met
    1  one or more requirements missing (printed to stdout unless --quiet)
"""

import argparse
import importlib
import json
import os
import socket
import sys

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_comfyui_config():
    cfg_path = os.path.join(SKILL_ROOT, "pipeline_config.json")
    if not os.path.isfile(cfg_path):
        return {}
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("enhance", {}).get("comfyui", {})


def check_python_deps():
    """Return list of missing Python packages."""
    required = ["requests", "PIL", "cv2", "numpy"]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


def check_gpu():
    """Return (has_gpu, detail_str)."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory // (1024 ** 3)
            return True, f"CUDA: {name} ({vram}GB VRAM)"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return True, "Apple MPS (Metal)"
        return False, "No CUDA/MPS GPU detected — CPU-only mode (very slow)"
    except ImportError:
        return False, "torch not installed — cannot detect GPU"


def check_comfyui_server(host, port, timeout=3):
    """Return (reachable, msg)."""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True, f"ComfyUI server reachable at {host}:{port}"
    except OSError:
        return False, f"ComfyUI server NOT reachable at {host}:{port}"


def check_models(cfg):
    """
    Look for required model files under common ComfyUI install paths.
    Returns list of (model_name, found_bool, search_hint).
    """
    checkpoint = cfg.get("checkpoint", "")
    depth_model = cfg.get("controlnet_depth_model", "")
    canny_model = cfg.get("controlnet_canny_model", "")

    comfyui_roots = [
        os.environ.get("COMFYUI_ROOT", ""),
        os.path.expanduser("~/ComfyUI"),
        "C:/ComfyUI",
        "D:/ComfyUI",
    ]

    results = []
    for model_name, subdir in [
        (checkpoint, "models/checkpoints"),
        (depth_model, "models/controlnet"),
        (canny_model, "models/controlnet"),
    ]:
        if not model_name:
            continue
        found = False
        for root in comfyui_roots:
            if not root:
                continue
            candidate = os.path.join(root, subdir, model_name)
            if os.path.isfile(candidate):
                found = True
                break
        results.append((model_name, found, f"Expected under {{ComfyUI_root}}/{subdir}/"))
    return results


def run_check(quiet=False):
    cfg = _load_comfyui_config()
    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", 8188)

    issues = []
    info = []

    # 1. Python deps
    missing_pkgs = check_python_deps()
    pkg_map = {"PIL": "Pillow", "cv2": "opencv-python", "numpy": "numpy", "requests": "requests"}
    if missing_pkgs:
        pip_names = [pkg_map.get(p, p) for p in missing_pkgs]
        issues.append(
            f"Missing Python packages: {', '.join(missing_pkgs)}\n"
            f"  Fix: pip install {' '.join(pip_names)}"
        )
    else:
        info.append("Python packages: OK (requests, Pillow, opencv, numpy)")

    # 2. GPU
    has_gpu, gpu_msg = check_gpu()
    if not has_gpu:
        issues.append(
            f"GPU: {gpu_msg}\n"
            "  ComfyUI can run on CPU but will be very slow (5-30 min/image).\n"
            "  Recommended: NVIDIA GPU with 8GB+ VRAM."
        )
    else:
        info.append(f"GPU: {gpu_msg}")

    # 3. ComfyUI server
    server_ok, server_msg = check_comfyui_server(host, port)
    if not server_ok:
        issues.append(
            f"{server_msg}\n"
            "  Fix: Start ComfyUI first:\n"
            "    cd <ComfyUI_root> && python main.py --listen 127.0.0.1 --port 8188\n"
            "  Or set COMFYUI_ROOT env var and run: python comfyui_env_check.py"
        )
    else:
        info.append(f"Server: {server_msg}")

    # 4. Models
    model_results = check_models(cfg)
    for model_name, found, hint in model_results:
        if not found:
            issues.append(
                f"Model not found: {model_name}\n"
                f"  {hint}\n"
                f"  Download from Hugging Face / CivitAI and place in ComfyUI models folder."
            )
        else:
            info.append(f"Model found: {model_name}")

    if quiet:
        return 0 if not issues else 1

    print("=== ComfyUI Environment Check ===")
    for line in info:
        print(f"  [OK]  {line}")
    if issues:
        print()
        print(f"  {len(issues)} issue(s) found:")
        for i, issue in enumerate(issues, 1):
            print(f"\n  [{i}] {issue}")
        print()
        print("Run 'python cad_pipeline.py enhance --backend comfyui' after fixing issues.")
        return 1
    else:
        print("\n  All checks passed. ComfyUI backend is ready.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check ComfyUI environment for cad-skill")
    parser.add_argument("--quiet", action="store_true", help="Exit code only, no output")
    args = parser.parse_args()
    sys.exit(run_check(quiet=args.quiet))
