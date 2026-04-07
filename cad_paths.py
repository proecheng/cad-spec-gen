"""
cad_paths.py — Centralized path resolution for the CAD pipeline.

All scripts should import from here instead of duplicating path logic.

Path concepts:
  SKILL_ROOT   — where the skill is installed (templates, scripts, tools)
  PROJECT_ROOT — the user's working project directory (output, design docs)
                 Set via CAD_PROJECT_ROOT env var, defaults to cwd.
"""

import os

# Root of the cad-skill installation (immutable — always __file__'s directory)
SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))

# Root of the user's project (output and docs go here)
PROJECT_ROOT = os.path.normpath(
    os.environ.get("CAD_PROJECT_ROOT", os.getcwd())
)


def get_output_dir(override=None):
    """Resolve output directory: override > env var > PROJECT_ROOT default."""
    if override:
        return os.path.normpath(override)
    return os.path.normpath(
        os.environ.get("CAD_OUTPUT_DIR",
                       os.path.join(PROJECT_ROOT, "cad", "output"))
    )


def get_render_dir(override=None, output_dir=None):
    """Resolve render output directory."""
    if override:
        return os.path.normpath(override)
    return os.path.join(get_output_dir(output_dir), "renders")


def get_blender_path():
    """Locate Blender executable. Returns path or None."""
    # Try pipeline_config.json first
    config_blender = ""
    config_path = os.path.join(SKILL_ROOT, "pipeline_config.json")
    if os.path.isfile(config_path):
        try:
            import json
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            config_blender = cfg.get("blender_path", "")
        except Exception:
            pass
    candidates = [
        os.environ.get("BLENDER_PATH", ""),
        config_blender,
        os.path.join(SKILL_ROOT, "tools", "blender", "blender.exe"),
    ]
    for c in candidates:
        c = os.path.normpath(c) if c else ""
        if c and os.path.isfile(c):
            return c
    return None


def get_subsystem_dir(name):
    """Resolve subsystem name to its directory. Returns path or None."""
    if not name:
        return None
    cad_dir = os.path.join(PROJECT_ROOT, "cad")
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
    env = os.environ.get("GEMINI_GEN_PATH", "")
    if env and os.path.isfile(env):
        return env
    # Search in SKILL_ROOT itself
    local = os.path.join(SKILL_ROOT, "gemini_gen.py")
    if os.path.isfile(local):
        return local
    # Search relative to SKILL_ROOT (sibling directories)
    sibling = os.path.join(os.path.dirname(SKILL_ROOT), "imageProduce", "gemini_gen.py")
    if os.path.isfile(sibling):
        return sibling
    return None
