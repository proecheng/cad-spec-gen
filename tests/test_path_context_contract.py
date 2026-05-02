import os
from pathlib import Path

import pytest

from tools.contract_io import stable_json_hash
from tools.path_policy import (
    assert_within_project,
    build_path_context,
    canonical_compare_path,
    project_relative,
    strict_subsystem_dir,
)


def test_strict_subsystem_dir_accepts_only_exact_directory(tmp_path):
    project_root = tmp_path / "project"
    subsystem_dir = project_root / "cad" / "lift"
    subsystem_dir.mkdir(parents=True)

    assert strict_subsystem_dir(project_root, "lift") == subsystem_dir


def test_strict_subsystem_dir_does_not_match_similar_directory(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "cad" / "lift_v2").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="lift"):
        strict_subsystem_dir(project_root, "lift")


@pytest.mark.parametrize(
    "subsystem",
    [
        "..",
        ".",
        "foo/..",
        "foo\\bar",
        "",
    ],
)
def test_strict_subsystem_dir_rejects_path_like_subsystem_names(tmp_path, subsystem):
    project_root = tmp_path / "project"
    (project_root / "cad" / "foo").mkdir(parents=True)
    (project_root / "cad" / "foo" / "bar").mkdir()

    with pytest.raises(ValueError, match="subsystem"):
        strict_subsystem_dir(project_root, subsystem)


def test_strict_subsystem_dir_rejects_absolute_subsystem_path(tmp_path):
    project_root = tmp_path / "project"
    escaped = tmp_path / "escaped"
    (project_root / "cad").mkdir(parents=True)
    escaped.mkdir()

    with pytest.raises(ValueError, match="subsystem"):
        strict_subsystem_dir(project_root, str(escaped))


def test_strict_subsystem_dir_rejects_case_drift_on_case_insensitive_filesystems(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "cad" / "lift").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="Lift"):
        strict_subsystem_dir(project_root, "Lift")


def test_project_relative_returns_posix_style_path(tmp_path):
    project_root = tmp_path / "project"
    target = project_root / "cad" / "lift" / "model.step"
    target.parent.mkdir(parents=True)
    target.write_text("data", encoding="utf-8")

    assert project_relative(target, project_root) == "cad/lift/model.step"


def test_project_relative_rejects_paths_outside_project(tmp_path):
    project_root = tmp_path / "project"
    outside = tmp_path / "outside.txt"

    with pytest.raises(ValueError):
        project_relative(outside, project_root)


def test_assert_within_project_error_includes_label(tmp_path):
    with pytest.raises(ValueError, match="render_dir"):
        assert_within_project(tmp_path / "outside", tmp_path / "project", "render_dir")


def test_canonical_compare_path_normalizes_case_on_windows():
    path = Path("A") / "B" / ".." / "C"
    expected = os.path.normcase(os.path.normpath(str(path))).replace("\\", "/")

    assert canonical_compare_path(path) == expected


def test_build_path_context_uses_defaults_and_stable_hash_excludes_itself(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "cad" / "lift").mkdir(parents=True)

    context = build_path_context(
        project_root,
        "lift",
        run_id="run-001",
        env={"backend": "blender"},
        skill_root=project_root / "skills",
    )
    without_hash = {key: value for key, value in context.items() if key != "path_context_hash"}

    assert context["schema_version"] == 1
    assert context["subsystem"] == "lift"
    assert context["requested_subsystem"] == "lift"
    assert context["resolved_subsystem"] == "lift"
    assert context["project_root"] == str(project_root.resolve())
    assert context["cad_dir"] == str((project_root / "cad").resolve())
    assert context["subsystem_dir"] == str((project_root / "cad" / "lift").resolve())
    assert context["output_dir"] == str((project_root / "cad" / "output").resolve())
    assert context["render_dir"] == str(
        (project_root / "cad" / "output" / "renders" / "lift" / "run-001").resolve()
    )
    assert context["skill_root"] == str((project_root / "skills").resolve())
    assert context["env"] == {"backend": "blender"}
    assert context["run_id"] == "run-001"
    assert context["path_context_hash"] == stable_json_hash(without_hash)

    changed_hash_field = dict(context)
    changed_hash_field["path_context_hash"] = "sha256:changed"
    without_changed_hash = {
        key: value for key, value in changed_hash_field.items() if key != "path_context_hash"
    }
    assert stable_json_hash(without_changed_hash) == context["path_context_hash"]


def test_build_path_context_rejects_output_dir_outside_project(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "cad" / "lift").mkdir(parents=True)

    with pytest.raises(ValueError, match="output_dir"):
        build_path_context(project_root, "lift", output_dir=tmp_path / "outside", run_id="run-001")
