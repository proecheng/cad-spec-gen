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
