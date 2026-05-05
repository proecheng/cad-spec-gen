import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_project_guide_recommends_init_when_subsystem_is_missing(tmp_path):
    from tools.project_guide import write_project_guide

    report = write_project_guide(tmp_path, "demo")

    assert report["status"] == "needs_init"
    assert report["next_action"]["kind"] == "run_init"
    assert report["next_action"]["argv"] == [
        "python",
        "cad_pipeline.py",
        "init",
        "--subsystem",
        "demo",
    ]
    assert report["mutates_pipeline_state"] is False
    assert report["does_not_scan_directories"] is True
    assert report["artifacts"]["project_guide"] == "cad/demo/.cad-spec-gen/PROJECT_GUIDE.json"


def test_project_guide_uses_explicit_design_doc_for_spec(tmp_path):
    from tools.project_guide import write_project_guide

    subsystem_dir = tmp_path / "cad" / "demo"
    subsystem_dir.mkdir(parents=True)
    design_doc = tmp_path / "docs" / "design" / "demo.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# demo", encoding="utf-8")

    report = write_project_guide(tmp_path, "demo", design_doc=design_doc)

    assert report["status"] == "needs_spec"
    assert report["next_action"]["kind"] == "run_spec"
    assert report["next_action"]["argv"] == [
        "python",
        "cad_pipeline.py",
        "spec",
        "--subsystem",
        "demo",
        "--design-doc",
        "docs/design/demo.md",
    ]


def test_project_guide_does_not_guess_design_doc_when_missing(tmp_path):
    from tools.project_guide import write_project_guide

    (tmp_path / "cad" / "demo").mkdir(parents=True)

    report = write_project_guide(tmp_path, "demo")

    assert report["status"] == "needs_design_doc"
    assert report["next_action"]["kind"] == "provide_design_doc"
    assert "argv" not in report["next_action"]


def test_project_guide_routes_active_run_to_photo3d_run_without_switching_run(tmp_path):
    from tools.project_guide import write_project_guide

    run_dir = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "runs" / "RUN001"
    run_dir.mkdir(parents=True)
    index_path = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
    _write_json(
        index_path,
        {
            "schema_version": 1,
            "subsystem": "demo",
            "active_run_id": "RUN001",
            "accepted_baseline_run_id": None,
            "runs": {"RUN001": {"run_id": "RUN001", "active": True, "artifacts": {}}},
        },
    )
    for name in ("CAD_SPEC.md", "params.py", "build_all.py", "assembly.py"):
        (tmp_path / "cad" / "demo" / name).write_text("ok", encoding="utf-8")

    report = write_project_guide(tmp_path, "demo")

    assert report["status"] == "ready_for_photo3d_run"
    assert report["run_id"] == "RUN001"
    assert report["next_action"]["kind"] == "run_photo3d_guide"
    assert report["next_action"]["argv"] == [
        "python",
        "cad_pipeline.py",
        "photo3d-run",
        "--subsystem",
        "demo",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
    ]
    written_index = json.loads(index_path.read_text(encoding="utf-8"))
    assert written_index["active_run_id"] == "RUN001"
    assert (run_dir / "PROJECT_GUIDE.json").is_file()


def test_project_guide_exposes_provider_choices_when_ready_for_enhancement(tmp_path):
    from tools.project_guide import write_project_guide

    run_dir = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "runs" / "RUN001"
    run_dir.mkdir(parents=True)
    index_path = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
    _write_json(
        index_path,
        {
            "schema_version": 1,
            "subsystem": "demo",
            "active_run_id": "RUN001",
            "accepted_baseline_run_id": "RUN001",
            "runs": {"RUN001": {"run_id": "RUN001", "active": True, "artifacts": {}}},
        },
    )
    _write_json(
        run_dir / "PHOTO3D_RUN.json",
        {
            "schema_version": 1,
            "run_id": "RUN001",
            "subsystem": "demo",
            "status": "ready_for_enhancement",
            "next_action": {
                "kind": "run_enhancement",
                "requires_user_confirmation": False,
            },
        },
    )
    for name in ("CAD_SPEC.md", "params.py", "build_all.py", "assembly.py"):
        (tmp_path / "cad" / "demo" / name).write_text("ok", encoding="utf-8")

    report = write_project_guide(tmp_path, "demo")

    assert report["status"] == "ready_for_photo3d_run"
    assert report["next_action"]["kind"] == "run_photo3d_guide"
    choice = report["provider_choice"]
    assert choice["kind"] == "select_enhancement_provider"
    assert choice["source_report"] == "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_RUN.json"
    assert choice["default_provider_preset"] == "default"
    assert [preset["id"] for preset in choice["provider_presets"]] == [
        "default",
        "engineering",
        "gemini",
        "fal",
        "fal_comfy",
        "comfyui",
    ]
    options = choice["ordinary_user_options"]
    assert [option["provider_preset"] for option in options] == [
        "default",
        "engineering",
        "gemini",
        "fal",
        "fal_comfy",
        "comfyui",
    ]
    engineering = next(
        action for action in choice["handoff_actions"]
        if action["provider_preset"] == "engineering"
    )
    engineering_option = next(
        option for option in options
        if option["provider_preset"] == "engineering"
    )
    assert "工程" in engineering_option["ordinary_user_title"]
    assert "离线" in engineering_option["ordinary_user_summary"]
    assert "工程" in engineering_option["recommended_when"]
    assert engineering_option["requires_setup"] is False
    assert engineering_option["argv"] == engineering["argv"]
    assert "--confirm" not in engineering_option["argv"]
    cloud_option = next(
        option for option in options
        if option["provider_preset"] == "gemini"
    )
    assert cloud_option["requires_setup"] is True
    assert engineering["argv"] == [
        "python",
        "cad_pipeline.py",
        "photo3d-handoff",
        "--subsystem",
        "demo",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
        "--provider-preset",
        "engineering",
    ]
    assert "--confirm" not in engineering["argv"]


def test_project_guide_ignores_stale_provider_choice_report(tmp_path):
    from tools.project_guide import write_project_guide

    run_dir = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "runs" / "RUN001"
    run_dir.mkdir(parents=True)
    index_path = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
    _write_json(
        index_path,
        {
            "schema_version": 1,
            "subsystem": "demo",
            "active_run_id": "RUN001",
            "accepted_baseline_run_id": "RUN001",
            "runs": {"RUN001": {"run_id": "RUN001", "active": True, "artifacts": {}}},
        },
    )
    _write_json(
        run_dir / "PHOTO3D_RUN.json",
        {
            "schema_version": 1,
            "run_id": "OLD001",
            "subsystem": "demo",
            "status": "ready_for_enhancement",
            "next_action": {"kind": "run_enhancement"},
        },
    )
    for name in ("CAD_SPEC.md", "params.py", "build_all.py", "assembly.py"):
        (tmp_path / "cad" / "demo" / name).write_text("ok", encoding="utf-8")

    report = write_project_guide(tmp_path, "demo")

    assert report["status"] == "ready_for_photo3d_run"
    assert "provider_choice" not in report


def test_project_guide_cli_writes_report(tmp_path, monkeypatch):
    import cad_pipeline

    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_project_guide(
        SimpleNamespace(
            subsystem="demo",
            design_doc=None,
            artifact_index=None,
            output=None,
        )
    )

    assert rc == 0
    report = json.loads(
        (tmp_path / "cad" / "demo" / ".cad-spec-gen" / "PROJECT_GUIDE.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "needs_init"


def test_project_guide_rejects_artifact_index_for_another_subsystem(tmp_path):
    from tools.project_guide import write_project_guide

    subsystem_dir = tmp_path / "cad" / "demo"
    subsystem_dir.mkdir(parents=True)
    index_path = tmp_path / "cad" / "other" / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
    _write_json(
        index_path,
        {
            "schema_version": 1,
            "subsystem": "other",
            "active_run_id": None,
            "runs": {},
        },
    )

    with pytest.raises(ValueError, match="artifact index subsystem mismatch"):
        write_project_guide(tmp_path, "demo", artifact_index_path=index_path)


def test_project_guide_rejects_output_outside_selected_guide_directory(tmp_path):
    from tools.project_guide import write_project_guide

    (tmp_path / "cad" / "demo").mkdir(parents=True)

    with pytest.raises(ValueError, match="output must stay"):
        write_project_guide(
            tmp_path,
            "demo",
            output_path=tmp_path / "cad" / "other" / ".cad-spec-gen" / "PROJECT_GUIDE.json",
        )


def test_project_guide_rejects_non_project_guide_output_name(tmp_path):
    from tools.project_guide import write_project_guide

    (tmp_path / "cad" / "demo").mkdir(parents=True)

    with pytest.raises(ValueError, match="must be PROJECT_GUIDE.json"):
        write_project_guide(
            tmp_path,
            "demo",
            output_path=tmp_path / "cad" / "demo" / ".cad-spec-gen" / "OTHER.json",
        )
