"""Generate pipeline_config.json for the target project."""

import json
from pathlib import Path
from .i18n import t
from . import ui


DEFAULT_CONFIG = {
    "blender_path": "",
    "cadquery_python": "python",
    "output_base": "cad/output",
    "render": {
        "engine": "CYCLES",
        "samples": 512,
        "resolution": [1920, 1080],
        "denoiser": "OPENIMAGEDENOISE",
    },
    "timestamp": {
        "enabled": True,
        "format": "%Y%m%d_%H%M",
        "keep_latest_symlink": True,
    },
    "archive": {
        "enabled": True,
        "max_versions": 10,
    },
}


def generate_config(target_dir, blender_path=None, lang="zh"):
    """Generate pipeline_config.json at target_dir.

    Returns the config path if written, None if skipped.
    """
    config_path = Path(target_dir) / "pipeline_config.json"

    if config_path.exists():
        ui.info(t("config_exists", lang))
        return str(config_path)

    config = dict(DEFAULT_CONFIG)
    if blender_path:
        config["blender_path"] = str(blender_path).replace("\\", "/")

    ui.info(t("config_target", lang, target=target_dir))

    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    ui.success(t("config_generated", lang))
    return str(config_path)
