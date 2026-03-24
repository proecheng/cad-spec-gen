"""Blender detection and setup guidance."""

import sys
from . import env_detect
from .i18n import t
from . import ui


def run_blender_step(lang, env_results):
    """Step 4: Blender configuration. Returns blender_path or None."""
    blender_path = env_results["blender"]["path"]
    blender_ver = env_results["blender"]["version"]

    if blender_path and blender_ver:
        ui.success(t("blender_found", lang, version=blender_ver))
        ui.info(f"  {blender_path}")
        return blender_path

    # Not found — show download guidance
    ui.warn(t("blender_not_found", lang))
    print()
    ui.info(t("blender_download", lang))
    if sys.platform == "win32":
        ui.info(t("blender_win", lang))
    elif sys.platform == "darwin":
        ui.info(t("blender_mac", lang))
    else:
        ui.info(t("blender_linux", lang))
    print()

    # Ask for path
    path = ui.prompt(t("blender_path_prompt", lang))
    if not path:
        return None

    # Verify
    ver = env_detect._get_blender_version(path)
    if ver:
        ui.success(t("blender_verified", lang, version=ver))
        return path
    else:
        ui.warn(t("blender_invalid", lang, path=path))
        return None
