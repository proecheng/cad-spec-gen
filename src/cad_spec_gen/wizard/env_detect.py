"""Environment detection: Python version, packages, Blender, Gemini.

Consolidated from tools/hybrid_render/check_env.py and cad_pipeline.py cmd_env_check().
"""

import importlib
import subprocess
import sys
from pathlib import Path


def check_python():
    """Check Python version. Returns (version_str, ok)."""
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 10)
    return ver, ok


def check_package(name):
    """Check if a Python package is importable. Returns (version_str|None, ok)."""
    try:
        mod = importlib.import_module(name)
        ver = getattr(mod, "__version__", getattr(mod, "VERSION", "installed"))
        return str(ver), True
    except ImportError:
        return None, False


def check_packages():
    """Check all relevant packages. Returns dict of {name: (version|None, ok)}."""
    packages = {
        "jinja2": "jinja2",
        "cadquery": "cadquery",
        "ezdxf": "ezdxf",
        "matplotlib": "matplotlib",
        "Pillow": "PIL",
    }
    results = {}
    for display_name, import_name in packages.items():
        ver, ok = check_package(import_name)
        results[display_name] = (ver, ok)
    return results


def find_blender():
    """Find Blender executable. Returns (path|None, version|None).

    Search order: BLENDER_PATH env → common locations → system PATH.
    """
    import os

    candidates = []

    # 1. Environment variable
    env_path = os.environ.get("BLENDER_PATH")
    if env_path:
        candidates.append(Path(env_path))

    # 2. Common locations (avoid recursive globs — NTFS junctions cause loops)
    if sys.platform == "win32":
        # Blender Foundation standard install paths
        for pf in [Path("C:/Program Files"), Path("C:/Program Files (x86)")]:
            bf = pf / "Blender Foundation"
            if bf.is_dir():
                try:
                    for d in sorted(bf.glob("Blender */blender.exe"), reverse=True):
                        candidates.append(d)
                except OSError:
                    pass
        # Steam install
        steam = Path("C:/Program Files (x86)/Steam/steamapps/common")
        if steam.is_dir():
            for d in sorted(steam.glob("Blender/blender.exe")):
                candidates.append(d)
        # Project-local tools/blender/
        local = Path.cwd() / "tools" / "blender" / "blender.exe"
        if local.exists():
            candidates.append(local)
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    else:
        candidates.append(Path("/usr/bin/blender"))
        candidates.append(Path("/snap/bin/blender"))
        try:
            for d in sorted(Path.home().glob("blender-*/blender"), reverse=True):
                candidates.append(d)
        except OSError:
            pass

    # 3. System PATH
    candidates.append(Path("blender"))

    for path in candidates:
        ver = _get_blender_version(path)
        if ver:
            return str(path), ver

    return None, None


def _get_blender_version(path):
    """Run blender --version and extract version string."""
    try:
        result = subprocess.run(
            [str(path), "--version"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.strip().startswith("Blender"):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        return parts[1]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def find_gemini():
    """Find Gemini gen script. Returns (path|None, configured)."""
    import os
    candidates = []

    env_path = os.environ.get("GEMINI_GEN_PATH")
    if env_path:
        candidates.append(Path(env_path))

    # Common location
    candidates.append(Path("D:/imageProduce/gemini_gen.py"))
    candidates.append(Path.home() / "gemini_gen.py")

    for path in candidates:
        if path.is_file():
            return str(path), True

    # Check config file
    config_path = Path.home() / ".config" / "gemini_image_config.json"
    if config_path.exists():
        return str(config_path), True

    return None, False


def compute_capability_level(pkg_results, blender_path, gemini_path):
    """Compute capability level 1-5 based on detected environment."""
    has_cq = pkg_results.get("cadquery", (None, False))[1]
    has_ezdxf = pkg_results.get("ezdxf", (None, False))[1]
    has_mpl = pkg_results.get("matplotlib", (None, False))[1]
    has_blender = blender_path is not None
    has_gemini = gemini_path is not None

    if has_cq and has_ezdxf and has_mpl and has_blender and has_gemini:
        return 5
    if has_cq and has_blender:
        return 4
    if has_cq and has_ezdxf:
        return 3
    if has_blender:
        return 2
    return 1


def run_full_check():
    """Run all checks and return structured results."""
    python_ver, python_ok = check_python()
    pkg_results = check_packages()
    blender_path, blender_ver = find_blender()
    gemini_path, gemini_ok = find_gemini()
    level = compute_capability_level(pkg_results, blender_path, gemini_path)

    return {
        "python": {"version": python_ver, "ok": python_ok},
        "packages": pkg_results,
        "blender": {"path": blender_path, "version": blender_ver},
        "gemini": {"path": gemini_path, "ok": gemini_ok},
        "level": level,
    }
