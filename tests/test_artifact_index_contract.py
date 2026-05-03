import pytest

from tools.artifact_index import (
    accept_run_baseline,
    build_artifact_index,
    get_accepted_baseline,
    get_active_artifacts,
    register_run_artifacts,
)


def test_register_run_artifacts_records_only_explicit_artifacts_without_scanning(tmp_path):
    index = build_artifact_index("lift")
    render_dir = tmp_path / "renders"
    render_dir.mkdir()
    (render_dir / "unregistered.png").write_text("data", encoding="utf-8")

    result = register_run_artifacts(
        index,
        "run-001",
        {"front": render_dir / "front.png"},
    )

    assert result["runs"]["run-001"]["artifacts"] == {"front": str(render_dir / "front.png")}
    assert "unregistered" not in str(result)


def test_register_run_artifacts_switches_active_run():
    index = build_artifact_index("lift")

    register_run_artifacts(index, "run-001", {"front": "old.png"}, active=True)
    register_run_artifacts(index, "run-002", {"front": "new.png"}, active=True)

    assert index["active_run_id"] == "run-002"
    assert index["runs"]["run-001"]["active"] is False
    assert index["runs"]["run-002"]["active"] is True
    assert get_active_artifacts(index) == {"front": "new.png"}


def test_register_run_artifacts_can_record_inactive_run_without_switching_active():
    index = build_artifact_index("lift")

    register_run_artifacts(index, "run-001", {"front": "active.png"}, active=True)
    register_run_artifacts(index, "run-002", {"front": "inactive.png"}, active=False)

    assert index["active_run_id"] == "run-001"
    assert index["runs"]["run-002"]["active"] is False
    assert get_active_artifacts(index) == {"front": "active.png"}


def test_get_active_artifacts_raises_when_no_active_run():
    index = build_artifact_index("lift")

    with pytest.raises(ValueError, match="active"):
        get_active_artifacts(index)


def test_accept_run_baseline_records_accepted_run_without_switching_active():
    index = build_artifact_index("lift")
    register_run_artifacts(
        index,
        "run-001",
        {
            "assembly_signature": "cad/lift/.cad-spec-gen/runs/run-001/ASSEMBLY_SIGNATURE.json",
            "photo3d_report": "cad/lift/.cad-spec-gen/runs/run-001/PHOTO3D_REPORT.json",
        },
        active=True,
    )
    register_run_artifacts(
        index,
        "run-002",
        {"assembly_signature": "cad/lift/.cad-spec-gen/runs/run-002/ASSEMBLY_SIGNATURE.json"},
        active=True,
    )

    result = accept_run_baseline(index, "run-001")

    assert result["active_run_id"] == "run-002"
    assert result["accepted_baseline_run_id"] == "run-001"
    assert result["runs"]["run-001"]["accepted_baseline"] is True
    assert result["runs"]["run-002"].get("accepted_baseline") is not True
    assert get_accepted_baseline(result) == {
        "run_id": "run-001",
        "assembly_signature": "cad/lift/.cad-spec-gen/runs/run-001/ASSEMBLY_SIGNATURE.json",
        "photo3d_report": "cad/lift/.cad-spec-gen/runs/run-001/PHOTO3D_REPORT.json",
    }


def test_accept_run_baseline_rejects_run_without_assembly_signature():
    index = build_artifact_index("lift")
    register_run_artifacts(index, "run-001", {"photo3d_report": "report.json"})

    with pytest.raises(ValueError, match="assembly_signature"):
        accept_run_baseline(index, "run-001")
