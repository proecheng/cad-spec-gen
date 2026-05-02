from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LIFTING_RENDER_CONFIG = ROOT / "cad" / "lifting_platform" / "render_config.json"


def test_lifting_platform_v1_label_anchors_stay_on_visible_model_body():
    """V1 callout anchors should point at the model, not the surrounding label gutters."""
    config = json.loads(LIFTING_RENDER_CONFIG.read_text(encoding="utf-8"))
    labels = config["labels"]["V1"]

    expected_components = {
        "SLP-100_top_plate",
        "SLP-300_moving_plate",
        "SLP-P01_LS1",
        "NEMA23_motor",
    }
    assert {label["component"] for label in labels} == expected_components

    model_box = {
        "x_min": 760,
        "x_max": 1120,
        "y_min": 220,
        "y_max": 850,
    }
    for label in labels:
        x, y = label["anchor"]
        assert model_box["x_min"] <= x <= model_box["x_max"], label
        assert model_box["y_min"] <= y <= model_box["y_max"], label
