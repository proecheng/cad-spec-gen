"""
cad_paths.py — Centralized path resolution for the CAD pipeline.

All scripts should import from here instead of duplicating path logic.
"""

import os

# Root of the cad-skill installation
SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))


def get_output_dir(override=None):
    """Resolve output directory: override > env var > default."""
    if override:
        return os.path.normpath(override)
    return os.path.normpath(
        os.environ.get("CAD_OUTPUT_DIR",
                       os.path.join(SKILL_ROOT, "cad", "output"))
    )


def get_render_dir(override=None, output_dir=None):
    """Resolve render output directory."""
    if override:
        return os.path.normpath(override)
    return os.path.join(get_output_dir(output_dir), "renders")


def get_blender_path():
    """Locate Blender executable. Returns path or None."""
    candidates = [
        os.environ.get("BLENDER_PATH", ""),
        os.path.join(SKILL_ROOT, "tools", "blender", "blender.exe"),
        "D:/cad-skill/tools/blender/blender.exe",
    ]
    for c in candidates:
        c = os.path.normpath(c) if c else ""
        if c and os.path.isfile(c):
            return c
    return None


def get_subsystem_dir(name):
    """Resolve subsystem name to its directory. Returns path or None."""
    cad_dir = os.path.join(SKILL_ROOT, "cad")
    d = os.path.join(cad_dir, name)
    if os.path.isdir(d):
        return d
    # Fuzzy match
    if os.path.isdir(cad_dir):
        for entry in os.listdir(cad_dir):
            if name.lower() in entry.lower() and os.path.isdir(os.path.join(cad_dir, entry)):
                return os.path.join(cad_dir, entry)
    return None


def get_gemini_script():
    """Locate gemini_gen.py. Returns path or None."""
    candidates = [
        os.environ.get("GEMINI_GEN_PATH", ""),
        "D:/imageProduce/gemini_gen.py",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None
