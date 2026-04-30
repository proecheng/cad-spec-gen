"""STEP geometry validation for user-provided model imports."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.model_import import import_user_step_model, validate_step_file


def _write_box_step(path: Path, x: float = 10, y: float = 20, z: float = 30) -> None:
    cq = pytest.importorskip("cadquery")
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(cq.Workplane("XY").box(x, y, z), str(path))


def test_validate_step_file_returns_bbox_and_hash_for_box_step(tmp_path):
    source_step = tmp_path / "box.step"
    _write_box_step(source_step, 10, 20, 30)

    result = validate_step_file(source_step)

    assert result.ok is True
    assert result.reason == ""
    assert result.source_hash.startswith("sha256:")
    assert result.bbox_mm == pytest.approx((10, 20, 30))
    assert result.to_dict()["bbox_mm"] == pytest.approx([10, 20, 30])


def test_import_user_step_model_rejects_corrupt_step_before_writing(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_step = project_root / "models" / "corrupt.step"
    source_step.parent.mkdir()
    source_step.write_text(
        "ISO-10303-21;\nthis is not valid STEP geometry\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )

    result = import_user_step_model(
        part_no="BAD-001",
        name_cn="坏模型",
        step="models/corrupt.step",
        project_root=project_root,
    )

    assert result["applied"] is False
    assert result["reason"].startswith("invalid STEP:")
    assert result["part_no"] == "BAD-001"
    assert result["validation"]["ok"] is False
    assert "invalid STEP" in result["reason"]
    assert not (project_root / "parts_library.yaml").exists()
    assert not (project_root / "std_parts" / "user_provided").exists()


def test_import_user_step_model_writes_validation_bbox_to_payload_and_yaml(tmp_path):
    yaml = pytest.importorskip("yaml")
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_step = project_root / "models" / "valid.step"
    _write_box_step(source_step, 10, 20, 30)

    result = import_user_step_model(
        part_no="BOX-001",
        name_cn="盒子",
        step="models/valid.step",
        project_root=project_root,
    )

    assert result["applied"] is True
    assert result["source_hash"] == result["validation"]["source_hash"]
    assert result["validation"]["ok"] is True
    assert result["validation"]["bbox_mm"] == pytest.approx([10, 20, 30])

    cfg = yaml.safe_load((project_root / "parts_library.yaml").read_text("utf-8"))
    provenance = cfg["mappings"][0]["provenance"]
    assert provenance["source_hash"] == result["validation"]["source_hash"]
    assert provenance["validated"] is True
    assert provenance["validation_status"] == "geometry_validated"
    assert isinstance(provenance["bbox_mm"], list)
    assert provenance["bbox_mm"] == pytest.approx([10, 20, 30])
