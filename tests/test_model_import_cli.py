"""Model import CLI contract tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_model_import(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "CAD_PROJECT_ROOT": str(project_root),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "cad_pipeline.py", "model-import", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )


def _write_step(path: Path, marker: str = "STEP") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"ISO-10303-21;\n/* {marker} */\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )


def test_model_import_copies_project_relative_step_updates_yaml_and_verifies(
    tmp_path,
):
    yaml = pytest.importorskip("yaml")
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_step = project_root / "models" / "lm10uu.step"
    _write_step(source_step)

    result = _run_model_import(
        project_root,
        "--subsystem",
        "demo",
        "--part-no",
        "SLP-C02",
        "--name-cn",
        "LM10UU",
        "--step",
        "models/lm10uu.step",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["applied"] is True
    assert payload["part_no"] == "SLP-C02"
    assert payload["step_file"].startswith("user_provided/")
    assert payload["verification"]["matched"] is True
    assert payload["verification"]["adapter"] == "step_pool"
    assert payload["verification"]["kind"] == "step_import"

    copied = project_root / "std_parts" / payload["step_file"]
    assert copied.is_file()
    assert copied.read_text(encoding="utf-8") == source_step.read_text(encoding="utf-8")

    cfg = yaml.safe_load((project_root / "parts_library.yaml").read_text("utf-8"))
    mapping = cfg["mappings"][0]
    assert mapping["match"] == {"part_no": "SLP-C02"}
    assert mapping["adapter"] == "step_pool"
    assert mapping["spec"] == {"file": payload["step_file"]}
    assert mapping["provenance"]["provided_by_user"] is True
    assert mapping["provenance"]["source_path"] == "models/lm10uu.step"
    assert mapping["provenance"]["source_hash"].startswith("sha256:")
    assert payload["source_path"] == "models/lm10uu.step"

    imports = json.loads(
        (
            project_root
            / "cad"
            / "demo"
            / ".cad-spec-gen"
            / "model_imports.json"
        ).read_text(encoding="utf-8")
    )
    assert imports["imports"][0]["part_no"] == "SLP-C02"
    assert imports["imports"][0]["step_file"] == payload["step_file"]
    assert imports["imports"][0]["source_path"] == "models/lm10uu.step"


def test_model_import_replaces_existing_user_mapping_for_same_part(tmp_path):
    yaml = pytest.importorskip("yaml")
    project_root = tmp_path / "project"
    project_root.mkdir()
    first = project_root / "models" / "first.step"
    second = project_root / "models" / "second.step"
    _write_step(first, "first")
    _write_step(second, "second")

    first_result = _run_model_import(
        project_root,
        "--part-no",
        "SLP-C03",
        "--name-cn",
        "KFL001",
        "--step",
        "models/first.step",
        "--json",
    )
    assert first_result.returncode == 0, first_result.stderr

    second_result = _run_model_import(
        project_root,
        "--part-no",
        "SLP-C03",
        "--name-cn",
        "KFL001",
        "--step",
        "models/second.step",
        "--json",
    )
    assert second_result.returncode == 0, second_result.stderr
    payload = json.loads(second_result.stdout)

    cfg = yaml.safe_load((project_root / "parts_library.yaml").read_text("utf-8"))
    user_mappings = [
        m
        for m in cfg["mappings"]
        if m.get("match") == {"part_no": "SLP-C03"}
        and (m.get("provenance") or {}).get("provided_by_user")
    ]
    assert len(user_mappings) == 1
    assert user_mappings[0]["spec"]["file"] == payload["step_file"]
    copied = project_root / "std_parts" / payload["step_file"]
    assert "second" in copied.read_text(encoding="utf-8")


def test_model_import_missing_step_is_clear_and_does_not_create_yaml(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = _run_model_import(
        project_root,
        "--part-no",
        "SLP-C99",
        "--step",
        "models/missing.step",
    )

    assert result.returncode == 2
    assert "STEP file not found" in result.stderr
    assert not (project_root / "parts_library.yaml").exists()
