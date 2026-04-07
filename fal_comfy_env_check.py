#!/usr/bin/env python3
"""
fal_comfy_env_check.py — Pre-flight check for fal Cloud ComfyUI backend.

Usage:
    python fal_comfy_env_check.py          # full check + guidance
    python fal_comfy_env_check.py --quiet  # return exit code only (0=ok, 1=issues)

Checks:
    1. FAL_KEY environment variable
    2. fal-client Python package
    3. Depth-map processing dependencies (numpy, Pillow)
    4. fal.ai API network reachability
    5. HuggingFace model URL accessibility
    6. First-run model download advisory (~5 GB)
"""

import argparse
import importlib
import json
import os
import sys

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_fal_comfy_config():
    cfg_path = os.path.join(SKILL_ROOT, "pipeline_config.json")
    if not os.path.isfile(cfg_path):
        return {}
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("enhance", {}).get("fal_comfy", {})


# ── Individual checks ────────────────────────────────────────────────────────


def check_fal_key():
    """Return (ok, message)."""
    key = os.environ.get("FAL_KEY", "")
    if not key:
        return False, (
            "FAL_KEY environment variable not set.\n"
            "  Fix: Get your key from https://fal.ai/dashboard/keys\n"
            "       then set: export FAL_KEY=\"your-key-here\"  (Linux/Mac)\n"
            "                 set FAL_KEY=your-key-here         (Windows CMD)\n"
            "                 $env:FAL_KEY=\"your-key-here\"     (PowerShell)"
        )
    # Mask key for display: show first 4 + last 4 chars
    masked = key[:4] + "..." + key[-4:] if len(key) > 12 else "***"
    return True, f"FAL_KEY set ({masked})"


def check_fal_client():
    """Return (ok, message)."""
    try:
        import fal_client  # noqa
        ver = getattr(fal_client, "__version__", "unknown")
        return True, f"fal-client installed (version {ver})"
    except ImportError:
        return False, (
            "fal-client package not installed.\n"
            "  Fix: pip install fal-client"
        )


def check_depth_deps():
    """Return (ok, message).  numpy + Pillow needed for EXR→PNG depth conversion."""
    missing = []
    for mod, pip_name in [("numpy", "numpy"), ("PIL", "Pillow")]:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        return False, (
            f"Missing depth-processing packages: {', '.join(missing)}\n"
            f"  Fix: pip install {' '.join(missing)}\n"
            "  (These are needed for EXR → PNG depth map conversion.)"
        )
    return True, "Depth processing deps: OK (numpy, Pillow)"


def check_fal_api_reachable(timeout=8):
    """Return (ok, message). Quick HTTPS HEAD to fal.ai gateway."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(
            "https://fal.run/fal-ai/comfy",
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=timeout):
            pass
        return True, "fal.ai API reachable (https://fal.run)"
    except urllib.error.HTTPError as e:
        # 401/405 still means reachable
        if e.code in (401, 403, 405, 422):
            return True, f"fal.ai API reachable (HTTP {e.code} — auth needed, OK)"
        return False, (
            f"fal.ai API returned HTTP {e.code}.\n"
            "  Check: https://status.fal.ai for service status."
        )
    except Exception as e:
        return False, (
            f"Cannot reach fal.ai API: {e}\n"
            "  Check your network / proxy settings.\n"
            "  fal.ai status: https://status.fal.ai"
        )


def check_hf_model_urls(cfg, timeout=10):
    """Return list of (url_label, ok, message) for each HuggingFace model URL."""
    import urllib.request
    import urllib.error

    urls = [
        ("Checkpoint", cfg.get("checkpoint_url", "")),
        ("ControlNet Depth", cfg.get("controlnet_depth_url", "")),
        ("ControlNet Canny", cfg.get("controlnet_canny_url", "")),
    ]
    results = []
    for label, url in urls:
        if not url:
            results.append((label, False, f"{label}: URL not configured in pipeline_config.json"))
            continue
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                size = resp.headers.get("Content-Length", "?")
                if size != "?":
                    size_mb = int(size) / (1024 * 1024)
                    results.append((label, True, f"{label}: OK ({size_mb:.0f} MB)"))
                else:
                    results.append((label, True, f"{label}: OK (size unknown)"))
        except urllib.error.HTTPError as e:
            if e.code == 302:
                # HuggingFace often redirects — treat as reachable
                results.append((label, True, f"{label}: OK (redirect, normal for HF)"))
            else:
                short_url = url[:60] + "..." if len(url) > 60 else url
                results.append((label, False,
                    f"{label}: HTTP {e.code} — model may not exist at:\n"
                    f"    {short_url}\n"
                    "    Check the URL in pipeline_config.json [enhance][fal_comfy]."
                ))
        except Exception as e:
            results.append((label, False,
                f"{label}: Cannot reach HuggingFace — {e}\n"
                "    Check network / proxy.  Models are downloaded on first run."
            ))
    return results


# ── Main runner ──────────────────────────────────────────────────────────────


def run_check(quiet=False):
    cfg = _load_fal_comfy_config()
    issues = []    # hard failures (FAL_KEY, packages) — block execution
    warnings = []  # soft failures (network, HF URLs) — warn but allow
    info = []

    # 1. FAL_KEY
    ok, msg = check_fal_key()
    (info if ok else issues).append(msg)

    # 2. fal-client
    ok, msg = check_fal_client()
    (info if ok else issues).append(msg)

    # 3. Depth deps
    ok, msg = check_depth_deps()
    (info if ok else issues).append(msg)

    # 4. fal.ai API (warning only — transient SSL errors should not block)
    ok, msg = check_fal_api_reachable()
    if ok:
        info.append(msg)
    else:
        warnings.append(msg)

    # 5. HuggingFace model URLs (warning only — models download at runtime)
    hf_results = check_hf_model_urls(cfg)
    for label, ok, msg in hf_results:
        if ok:
            info.append(msg)
        else:
            warnings.append(msg)

    # 6. First-run advisory (always shown, not an issue)
    first_run_note = (
        "First-run advisory: fal downloads models from HuggingFace on first call.\n"
        "    Checkpoint (~2 GB) + 2 ControlNets (~1.5 GB each) ≈ 5 GB total.\n"
        "    First image may take 3-5 minutes; subsequent runs use cached models."
    )

    if quiet:
        return 0 if not issues else 1

    print("=== fal Cloud ComfyUI Environment Check ===")
    print()
    for line in info:
        print(f"  [OK]  {line}")

    if warnings:
        print()
        for w in warnings:
            print(f"  [WARN] {w}")

    if issues:
        print()
        print(f"  {len(issues)} issue(s) found:")
        for i, issue in enumerate(issues, 1):
            print(f"\n  [{i}] {issue}")
        print()
        print("Fix the issues above, then run:")
        print("  python cad_pipeline.py enhance --backend fal_comfy")
        return 1
    else:
        print()
        print(f"  [NOTE] {first_run_note}")
        if warnings:
            print("  [NOTE] Network warnings above may be transient — proceeding is OK.")
        print()
        print("  All checks passed. fal_comfy backend is ready.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check fal Cloud ComfyUI environment")
    parser.add_argument("--quiet", action="store_true", help="Exit code only, no output")
    args = parser.parse_args()
    sys.exit(run_check(quiet=args.quiet))
