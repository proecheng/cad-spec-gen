"""STEP geometry validation for user-provided model imports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.model_import import (
    _record_model_import,
    import_user_step_model,
    validate_step_file,
)


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


@pytest.mark.parametrize(
    "bad_yaml",
    [
        "mappings:\n  bad: value\n",
        "- not\n- a\n- mapping\n",
    ],
)
def test_import_user_step_model_rejects_invalid_parts_library_before_copying(
    tmp_path,
    bad_yaml,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_step = project_root / "models" / "valid.step"
    _write_box_step(source_step)
    library_path = project_root / "parts_library.yaml"
    library_path.write_text(bad_yaml, encoding="utf-8")

    result = import_user_step_model(
        part_no="BAD-YAML",
        name_cn="坏配置",
        step="models/valid.step",
        project_root=project_root,
    )

    assert result["applied"] is False
    assert "parts_library.yaml" in result["reason"]
    assert library_path.read_text(encoding="utf-8") == bad_yaml
    assert not (project_root / "std_parts" / "user_provided").exists()


def test_import_user_step_model_restores_existing_target_when_writer_fails(
    tmp_path,
    monkeypatch,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_step = project_root / "models" / "valid.step"
    _write_box_step(source_step, 12, 22, 32)
    target = project_root / "std_parts" / "user_provided" / "ROLL-001_滚轮.step"
    target.parent.mkdir(parents=True)
    target.write_text("old target content", encoding="utf-8")

    import tools.model_import as model_import

    def fail_writer(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(model_import, "prepend_user_step_mapping", fail_writer)

    result = import_user_step_model(
        part_no="ROLL-001",
        name_cn="滚轮",
        step="models/valid.step",
        project_root=project_root,
    )

    assert result["applied"] is False
    assert "boom" in result["reason"]
    assert target.read_text(encoding="utf-8") == "old target content"


def test_record_model_import_includes_validation(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    result = {
        "part_no": "BOX-REC",
        "name_cn": "记录盒",
        "step_file": "user_provided/box.step",
        "target_path": str(project_root / "std_parts" / "user_provided" / "box.step"),
        "source_path": "models/box.step",
        "source_hash": "sha256:abc",
        "parts_library": str(project_root / "parts_library.yaml"),
        "verification": {"matched": True},
        "validation": {
            "ok": True,
            "reason": "",
            "source_hash": "sha256:abc",
            "bbox_mm": [10.0, 20.0, 30.0],
            "warnings": [],
        },
    }

    record_path = _record_model_import(result, project_root=project_root, subsystem=None)

    imports = json.loads(record_path.read_text(encoding="utf-8"))
    assert imports["imports"][0]["validation"] == result["validation"]


def test_import_user_step_model_cleans_record_tmp_when_record_replace_fails(
    tmp_path,
    monkeypatch,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_step = project_root / "models" / "valid.step"
    _write_box_step(source_step, 18, 28, 38)
    library_path = project_root / "parts_library.yaml"
    original_yaml = (
        b"extends: default\n"
        b"mappings:\n"
        b"- match:\n"
        b"    part_no: OLD-RECORD\n"
        b"  adapter: step_pool\n"
        b"  spec:\n"
        b"    file: old.step\n"
    )
    library_path.write_bytes(original_yaml)
    target = project_root / "std_parts" / "user_provided" / "TMP-FAIL_临时失败.step"
    target.parent.mkdir(parents=True)
    old_target = b"old target content"
    target.write_bytes(old_target)
    record_path = project_root / ".cad-spec-gen" / "model_imports.json"
    record_path.parent.mkdir(parents=True)
    old_record = {"schema_version": 1, "imports": [{"part_no": "OLD-RECORD"}]}
    record_path.write_text(json.dumps(old_record), encoding="utf-8")

    import tools.model_import as model_import

    original_replace = model_import.os.replace

    def fail_record_replace(src, dst):
        if Path(dst).name == "model_imports.json":
            raise OSError("replace boom")
        return original_replace(src, dst)

    monkeypatch.setattr(model_import.os, "replace", fail_record_replace)

    result = import_user_step_model(
        part_no="TMP-FAIL",
        name_cn="临时失败",
        step="models/valid.step",
        project_root=project_root,
    )

    assert result["applied"] is False
    assert "replace boom" in result["reason"]
    assert target.read_bytes() == old_target
    assert library_path.read_bytes() == original_yaml
    assert json.loads(record_path.read_text(encoding="utf-8")) == old_record
    assert not (project_root / ".cad-spec-gen" / "model_imports.json.tmp").exists()


@pytest.mark.parametrize("library_exists", [True, False])
def test_import_user_step_model_rolls_back_yaml_when_record_write_fails(
    tmp_path,
    monkeypatch,
    library_exists,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_step = project_root / "models" / "valid.step"
    _write_box_step(source_step, 14, 24, 34)
    library_path = project_root / "parts_library.yaml"
    original_yaml = (
        b"extends: default\n"
        b"mappings:\n"
        b"- match:\n"
        b"    part_no: OLD-001\n"
        b"  adapter: step_pool\n"
        b"  spec:\n"
        b"    file: old.step\n"
    )
    if library_exists:
        library_path.write_bytes(original_yaml)

    import tools.model_import as model_import

    def fail_record(*_args, **_kwargs):
        raise OSError("record boom")

    monkeypatch.setattr(model_import, "_record_model_import", fail_record)

    result = import_user_step_model(
        part_no="REC-FAIL",
        name_cn="记录失败",
        step="models/valid.step",
        project_root=project_root,
    )

    assert result["applied"] is False
    assert "record boom" in result["reason"]
    assert not (
        project_root / "std_parts" / "user_provided" / "REC-FAIL_记录失败.step"
    ).exists()
    if library_exists:
        assert library_path.read_bytes() == original_yaml
    else:
        assert not library_path.exists()
    assert not (project_root / "parts_library.yaml.tmp").exists()


@pytest.mark.parametrize("library_exists", [True, False])
@pytest.mark.parametrize("target_exists", [True, False])
def test_import_user_step_model_rolls_back_when_resolver_verification_fails(
    tmp_path,
    monkeypatch,
    library_exists,
    target_exists,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_step = project_root / "models" / "valid.step"
    _write_box_step(source_step, 16, 26, 36)
    library_path = project_root / "parts_library.yaml"
    original_yaml = (
        b"extends: default\n"
        b"mappings:\n"
        b"- match:\n"
        b"    part_no: OLD-VERIFY\n"
        b"  adapter: step_pool\n"
        b"  spec:\n"
        b"    file: old.step\n"
    )
    if library_exists:
        library_path.write_bytes(original_yaml)

    target = project_root / "std_parts" / "user_provided" / "VER-FAIL_验证失败.step"
    old_target = b"old target content"
    if target_exists:
        target.parent.mkdir(parents=True)
        target.write_bytes(old_target)

    import tools.model_import as model_import

    def fail_verify(*_args, **_kwargs):
        return {
            "matched": False,
            "warnings": ["no matching parts_library.yaml rule"],
        }

    monkeypatch.setattr(model_import, "verify_model_import_consumed", fail_verify)

    result = import_user_step_model(
        part_no="VER-FAIL",
        name_cn="验证失败",
        step="models/valid.step",
        project_root=project_root,
        verify=True,
    )

    assert result["applied"] is False
    assert result["reason"] == (
        "resolver verification failed: no matching parts_library.yaml rule"
    )
    if target_exists:
        assert target.read_bytes() == old_target
    else:
        assert not target.exists()
    if library_exists:
        assert library_path.read_bytes() == original_yaml
    else:
        assert not library_path.exists()
    assert not (project_root / "parts_library.yaml.tmp").exists()
    assert not (project_root / ".cad-spec-gen" / "model_imports.json").exists()
