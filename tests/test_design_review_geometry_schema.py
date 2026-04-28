"""DESIGN_REVIEW.json must preserve structured geometry choices."""

import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location(
    "cad_spec_gen_script",
    Path(__file__).resolve().parents[1] / "cad_spec_gen.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MODULE)
_flatten_review_items = _MODULE._flatten_review_items


def test_flatten_review_items_preserves_geometry_model_choice_fields():
    review_data = {
        "geometry": [
            {
                "id": "G1",
                "item": "模型库候选",
                "detail": "电机模型可升级",
                "verdict": "WARNING",
                "suggestion": "选择供应商 STEP",
                "group_action": "choose_one",
                "parts": ["P-001", "P-002"],
                "candidates": [
                    {
                        "source": "step_pool",
                        "path": "std_parts/vendor/motor.step",
                        "geometry_quality": "A",
                    }
                ],
                "geometry_quality": "D",
                "recommended_quality": "A",
                "user_choice": {"part_no": "P-001", "step_file": "motor.step"},
            }
        ]
    }

    items = _flatten_review_items(review_data)

    assert len(items) == 1
    item = items[0]
    assert item["category"] == "geometry"
    assert item["group_action"] == "choose_one"
    assert item["parts"] == ["P-001", "P-002"]
    assert item["candidates"][0]["geometry_quality"] == "A"
    assert item["user_choice"]["part_no"] == "P-001"
