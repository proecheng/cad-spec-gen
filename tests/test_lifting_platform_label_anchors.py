from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LIFTING_RENDER_CONFIG = ROOT / "cad" / "lifting_platform" / "render_config.json"


VISIBLE_MODEL_BOXES = {
    "V1": {"x_min": 760, "x_max": 1120, "y_min": 220, "y_max": 850},
    "V2": {"x_min": 700, "x_max": 1050, "y_min": 150, "y_max": 720},
    "V3": {"x_min": 820, "x_max": 1040, "y_min": 180, "y_max": 780},
    "V4": {"x_min": 720, "x_max": 1280, "y_min": 0, "y_max": 1020},
    "V5": {"x_min": 700, "x_max": 1100, "y_min": 170, "y_max": 820},
    "V6": {"x_min": 820, "x_max": 1040, "y_min": 180, "y_max": 840},
}


def test_lifting_platform_label_anchors_stay_on_visible_model_body():
    """Callout anchors should point at the model, not the surrounding label gutters."""
    config = json.loads(LIFTING_RENDER_CONFIG.read_text(encoding="utf-8"))

    assert {label["component"] for label in config["labels"]["V1"]} == {
        "SLP-100_top_plate",
        "SLP-300_moving_plate",
        "SLP-P01_LS1",
        "NEMA23_motor",
    }

    for view_id, labels in config["labels"].items():
        model_box = VISIBLE_MODEL_BOXES[view_id]
        for label in labels:
            x, y = label["anchor"]
            assert model_box["x_min"] <= x <= model_box["x_max"], (view_id, label)
            assert model_box["y_min"] <= y <= model_box["y_max"], (view_id, label)


def test_lifting_platform_labels_cover_every_rendered_view():
    """Each lifting-platform render view should have callouts ready for annotation."""
    config = json.loads(LIFTING_RENDER_CONFIG.read_text(encoding="utf-8"))
    camera_views = set(config["camera"])

    assert set(config["labels"]) == camera_views
    for view_id, labels in config["labels"].items():
        assert len(labels) >= 4, view_id
        for label in labels:
            assert label["component"] in config["components"], label
            assert len(label["anchor"]) == 2, label
            assert len(label["label"]) == 2, label


def test_lifting_platform_label_coordinates_stay_inside_reference_frame():
    """Callout anchors and text starts are authored in the configured 1920x1080 frame."""
    config = json.loads(LIFTING_RENDER_CONFIG.read_text(encoding="utf-8"))
    width = config["resolution"]["width"]
    height = config["resolution"]["height"]

    for view_id, labels in config["labels"].items():
        for label in labels:
            for key in ("anchor", "label"):
                x, y = label[key]
                assert 0 <= x <= width, (view_id, label)
                assert 0 <= y <= height, (view_id, label)
