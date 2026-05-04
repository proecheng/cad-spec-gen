import json
from pathlib import Path
from types import SimpleNamespace

from tests.test_photo3d_action_runner import _rerun_render_action, _user_request_action
from tests.test_photo3d_action_runner import _write_action_inputs
from tests.test_photo3d_gate_contract import _contracts, _write_json


def _render_stale_fixture(tmp_path):
    fixture = _contracts(tmp_path)
    render_manifest = fixture["payloads"]["render_manifest"]
    render_manifest["assembly_signature_hash"] = "sha256:stale"
    _write_json(fixture["paths"]["render_manifest"], render_manifest)
    return fixture


def test_photo3d_run_stops_at_baseline_acceptance_without_accepting(tmp_path):
    from tools.photo3d_loop import run_photo3d_loop

    fixture = _contracts(tmp_path)

    report = run_photo3d_loop(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "needs_baseline_acceptance"
    assert report["run_id"] == "RUN001"
    assert report["subsystem"] == "demo"
    assert report["round_count"] == 1
    assert report["rounds"][0]["autopilot_status"] == "needs_baseline_acceptance"
    assert report["next_action"]["kind"] == "accept_baseline"
    assert report["next_action"]["requires_user_confirmation"] is True
    assert report["artifacts"]["photo3d_run"].endswith("RUN001/PHOTO3D_RUN.json")

    written = json.loads((fixture["run_dir"] / "PHOTO3D_RUN.json").read_text(encoding="utf-8"))
    assert written["status"] == "needs_baseline_acceptance"

    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["accepted_baseline_run_id"] is None


def test_photo3d_run_preview_stops_before_blocked_recovery_without_confirm(tmp_path):
    from tools.photo3d_loop import run_photo3d_loop

    fixture = _render_stale_fixture(tmp_path)

    report = run_photo3d_loop(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        confirm_actions=False,
    )

    assert report["status"] == "awaiting_action_confirmation"
    assert report["round_count"] == 1
    assert report["rounds"][0]["gate_status"] == "blocked"
    assert report["rounds"][0]["autopilot_status"] == "blocked"
    assert report["rounds"][0]["action_run_status"] == "awaiting_confirmation"
    assert report["next_action"]["kind"] == "confirm_action_plan"
    assert report["next_action"]["requires_user_confirmation"] is True
    assert report["next_action"]["argv"] == [
        "python",
        "cad_pipeline.py",
        "photo3d-run",
        "--subsystem",
        "demo",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
        "--confirm-actions",
    ]


def test_photo3d_run_confirm_executes_low_risk_actions_and_stops_on_post_action_baseline(
    tmp_path,
    monkeypatch,
):
    from tools.photo3d_loop import run_photo3d_loop
    import tools.photo3d_action_runner as action_runner

    fixture = _render_stale_fixture(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="render ok", stderr="")

    def fake_gate(project_root, subsystem, **kwargs):
        assert project_root == tmp_path
        assert subsystem == "demo"
        assert Path(kwargs["artifact_index_path"]) == fixture["index_path"]
        return {
            "schema_version": 1,
            "run_id": "RUN001",
            "subsystem": "demo",
            "status": "pass",
            "enhancement_status": "not_run",
            "artifacts": {
                "photo3d_report": "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_REPORT.json",
                "product_graph": "cad/demo/.cad-spec-gen/runs/RUN001/PRODUCT_GRAPH.json",
                "model_contract": "cad/demo/.cad-spec-gen/runs/RUN001/MODEL_CONTRACT.json",
                "assembly_signature": "cad/demo/.cad-spec-gen/runs/RUN001/ASSEMBLY_SIGNATURE.json",
                "render_manifest": "cad/output/renders/demo/RUN001/render_manifest.json",
            },
        }

    monkeypatch.setattr(action_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(action_runner, "run_photo3d_gate", fake_gate)

    report = run_photo3d_loop(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        confirm_actions=True,
    )

    assert calls, "expected low-risk recovery to execute"
    assert report["status"] == "needs_baseline_acceptance"
    assert report["round_count"] == 1
    assert report["rounds"][0]["action_run_status"] == "executed"
    assert report["rounds"][0]["post_action_autopilot"]["rerun"] is True
    assert report["rounds"][0]["post_action_autopilot"]["status"] == "needs_baseline_acceptance"
    assert report["next_action"]["kind"] == "accept_baseline"


def test_photo3d_run_does_not_continue_when_action_plan_needs_user_input(tmp_path):
    from tools.photo3d_loop import run_photo3d_loop

    fixture = _contracts(tmp_path, hero_quality="D")

    report = run_photo3d_loop(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        confirm_actions=True,
    )

    assert report["status"] == "needs_user_input"
    assert report["round_count"] == 1
    assert report["rounds"][0]["action_run_status"] == "needs_user_input"
    assert report["next_action"]["kind"] == "provide_user_input"
    assert report["next_action"]["requires_user_confirmation"] is False


def test_cmd_photo3d_run_writes_loop_report(tmp_path, monkeypatch):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_run(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            max_rounds=2,
            confirm_actions=False,
            output=None,
        )
    )

    assert rc == 0
    report = json.loads((fixture["run_dir"] / "PHOTO3D_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "needs_baseline_acceptance"
