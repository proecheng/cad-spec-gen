from pathlib import Path

from tools.model_context import ModelProjectContext


def test_review_json_under_output_maps_to_canonical_cad_meta_dir(tmp_path):
    project_root = tmp_path / "project"
    review_json = project_root / "output" / "end_effector" / "DESIGN_REVIEW.json"

    ctx = ModelProjectContext.from_review_json(
        review_json,
        project_root=project_root,
    )

    assert ctx.subsystem == "end_effector"
    assert ctx.meta_dir == project_root / "cad" / "end_effector" / ".cad-spec-gen"
    assert (
        ctx.model_choices_path
        == project_root
        / "cad"
        / "end_effector"
        / ".cad-spec-gen"
        / "model_choices.json"
    )
    assert (
        ctx.geometry_report_path
        == project_root
        / "cad"
        / "end_effector"
        / ".cad-spec-gen"
        / "geometry_report.json"
    )
    assert (
        ctx.sw_export_plan_path
        == project_root
        / "cad"
        / "end_effector"
        / ".cad-spec-gen"
        / "sw_export_plan.json"
    )
    assert ctx.parts_library_path == project_root / "parts_library.yaml"
    assert ctx.user_provided_dir == project_root / "std_parts" / "user_provided"


def test_review_json_under_cad_derives_same_subsystem(tmp_path):
    project_root = tmp_path / "project"
    review_json = project_root / "cad" / "end_effector" / "DESIGN_REVIEW.json"

    ctx = ModelProjectContext.from_review_json(
        review_json,
        project_root=project_root,
    )

    assert ctx.subsystem == "end_effector"


def test_no_subsystem_uses_project_level_meta_dir(tmp_path):
    project_root = tmp_path / "project"

    ctx = ModelProjectContext.for_subsystem(None, project_root=project_root)

    assert ctx.subsystem is None
    assert ctx.meta_dir == project_root / ".cad-spec-gen"
    assert ctx.model_imports_path == project_root / ".cad-spec-gen" / "model_imports.json"
