"""User model choices must update the resolver-facing parts library."""

import json
from pathlib import Path

import pytest


def test_save_supplements_applies_step_model_choice(tmp_path, monkeypatch):
    yaml = pytest.importorskip("yaml")
    import cad_pipeline

    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(project_root))

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_step = source_dir / "motor.step"
    source_step.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    review_dir = project_root / "output" / "demo"
    review_dir.mkdir(parents=True)
    review_json = review_dir / "DESIGN_REVIEW.json"
    review_json.write_text("{}", encoding="utf-8")

    cad_pipeline._save_supplements(
        {
            "model_choices": [
                {
                    "part_no": "P-001",
                    "name_cn": "测试电机",
                    "step_file": str(source_step),
                }
            ],
            "M1": "普通文本补充",
        },
        str(review_json),
    )

    model_choices = json.loads(
        (review_dir / "model_choices.json").read_text(encoding="utf-8")
    )
    assert model_choices["applied"][0]["applied"] is True

    copied = project_root / "std_parts" / model_choices["applied"][0]["step_file"]
    assert copied.is_file()

    cfg = yaml.safe_load(
        (project_root / "parts_library.yaml").read_text(encoding="utf-8")
    )
    mapping = cfg["mappings"][0]
    assert mapping["match"] == {"part_no": "P-001"}
    assert mapping["adapter"] == "step_pool"
    assert mapping["spec"]["file"].startswith("user_provided/")
    assert not mapping["spec"]["file"].startswith("std_parts/")
    assert mapping["provenance"]["provided_by_user"] is True
