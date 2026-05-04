import json
from types import SimpleNamespace

from tests.test_photo3d_gate_contract import _contracts


def test_cmd_photo3d_autopilot_pass_writes_baseline_next_action(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_autopilot(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
        )
    )

    assert rc == 0
    autopilot_path = fixture["run_dir"] / "PHOTO3D_AUTOPILOT.json"
    report = json.loads(autopilot_path.read_text(encoding="utf-8"))

    assert report["gate_status"] == "pass"
    assert report["status"] == "needs_baseline_acceptance"
    assert report["run_id"] == "RUN001"
    assert report["subsystem"] == "demo"
    assert report["accepted_baseline_run_id"] is None
    assert report["next_action"]["kind"] == "accept_baseline"
    assert report["next_action"]["requires_user_confirmation"] is True
    assert (
        report["next_action"]["cli"]
        == "python cad_pipeline.py accept-baseline --subsystem demo"
    )
    assert report["artifacts"]["photo3d_report"].endswith("RUN001/PHOTO3D_REPORT.json")
    assert report["artifacts"]["photo3d_autopilot"].endswith(
        "RUN001/PHOTO3D_AUTOPILOT.json"
    )

    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["accepted_baseline_run_id"] is None


def test_cmd_photo3d_autopilot_blocked_points_to_action_plan(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline

    fixture = _contracts(tmp_path, hero_quality="D")
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_autopilot(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
        )
    )

    assert rc == 1
    report = json.loads(
        (fixture["run_dir"] / "PHOTO3D_AUTOPILOT.json").read_text(encoding="utf-8")
    )

    assert report["gate_status"] == "blocked"
    assert report["status"] == "blocked"
    assert report["next_action"]["kind"] == "follow_action_plan"
    assert report["next_action"]["action_plan"].endswith("RUN001/ACTION_PLAN.json")
    assert report["next_action"]["llm_context_pack"].endswith(
        "RUN001/LLM_CONTEXT_PACK.json"
    )
    assert report["artifacts"]["photo3d_report"].endswith("RUN001/PHOTO3D_REPORT.json")
    assert report["artifacts"]["action_plan"].endswith("RUN001/ACTION_PLAN.json")
    assert report["artifacts"]["llm_context_pack"].endswith(
        "RUN001/LLM_CONTEXT_PACK.json"
    )


def test_cmd_photo3d_autopilot_with_accepted_baseline_recommends_enhancement(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline
    from tools.artifact_index import accept_run_baseline

    fixture = _contracts(tmp_path)
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    accept_run_baseline(index, "RUN001")
    fixture["index_path"].write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_autopilot(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
        )
    )

    assert rc == 0
    report = json.loads(
        (fixture["run_dir"] / "PHOTO3D_AUTOPILOT.json").read_text(encoding="utf-8")
    )

    assert report["gate_status"] == "pass"
    assert report["status"] == "ready_for_enhancement"
    assert report["accepted_baseline_run_id"] == "RUN001"
    assert report["next_action"]["kind"] == "run_enhancement"
    assert (
        report["next_action"]["cli"]
        == "python cad_pipeline.py enhance --subsystem demo --dir cad/output/renders/demo/RUN001"
    )


def test_cmd_photo3d_autopilot_keeps_unsafe_subsystem_out_of_shell_cli(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline

    fixture = _contracts(tmp_path, subsystem="demo bad")
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_autopilot(
        SimpleNamespace(
            subsystem="demo bad",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
        )
    )

    assert rc == 0
    report = json.loads(
        (fixture["run_dir"] / "PHOTO3D_AUTOPILOT.json").read_text(encoding="utf-8")
    )

    action = report["next_action"]
    assert action["kind"] == "accept_baseline"
    assert "cli" not in action
    assert action["argv"] == [
        "python",
        "cad_pipeline.py",
        "accept-baseline",
        "--subsystem",
        "demo bad",
    ]


def test_write_photo3d_autopilot_rejects_report_run_id_drift(tmp_path):
    from tools.photo3d_autopilot import write_photo3d_autopilot_report
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )
    report["run_id"] = "STALE001"

    try:
        write_photo3d_autopilot_report(
            tmp_path,
            "demo",
            report,
            artifact_index_path=fixture["index_path"],
        )
    except ValueError as exc:
        assert "active_run_id" in str(exc)
    else:
        raise AssertionError("expected report run_id drift to be rejected")


def test_cmd_photo3d_autopilot_rejects_output_outside_active_run_dir(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    try:
        cad_pipeline.cmd_photo3d_autopilot(
            SimpleNamespace(
                subsystem="demo",
                artifact_index=str(fixture["index_path"]),
                change_scope=None,
                baseline_signature=None,
                output=str(tmp_path / "cad" / "demo" / "PHOTO3D_AUTOPILOT.json"),
            )
        )
    except ValueError as exc:
        assert "active run directory" in str(exc)
    else:
        raise AssertionError("expected output outside active run directory to fail")


def test_cmd_photo3d_autopilot_enhance_action_binds_active_render_dir(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline
    from tools.artifact_index import accept_run_baseline

    fixture = _contracts(tmp_path)
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    accept_run_baseline(index, "RUN001")
    fixture["index_path"].write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_autopilot(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
        )
    )

    assert rc == 0
    report = json.loads(
        (fixture["run_dir"] / "PHOTO3D_AUTOPILOT.json").read_text(encoding="utf-8")
    )

    action = report["next_action"]
    assert action["kind"] == "run_enhancement"
    assert action["argv"] == [
        "python",
        "cad_pipeline.py",
        "enhance",
        "--subsystem",
        "demo",
        "--dir",
        "cad/output/renders/demo/RUN001",
    ]
    assert (
        action["cli"]
        == "python cad_pipeline.py enhance --subsystem demo --dir cad/output/renders/demo/RUN001"
    )


def test_write_photo3d_autopilot_rejects_enhance_without_render_manifest(tmp_path):
    from tools.artifact_index import accept_run_baseline
    from tools.photo3d_autopilot import write_photo3d_autopilot_report
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    accept_run_baseline(index, "RUN001")
    fixture["index_path"].write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )
    report["artifacts"].pop("render_manifest")

    try:
        write_photo3d_autopilot_report(
            tmp_path,
            "demo",
            report,
            artifact_index_path=fixture["index_path"],
        )
    except ValueError as exc:
        assert "render_manifest" in str(exc)
    else:
        raise AssertionError("expected missing render_manifest to block enhance action")
