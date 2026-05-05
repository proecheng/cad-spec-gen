import json
from types import SimpleNamespace
import sys

from tests.test_photo3d_gate_contract import _contracts, _write_json


def _accept_baseline(fixture):
    from tools.artifact_index import accept_run_baseline

    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    accept_run_baseline(index, fixture["run_id"])
    fixture["index_path"].write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_photo3d_run(fixture, next_action, *, status="needs_baseline_acceptance"):
    _write_json(
        fixture["run_dir"] / "PHOTO3D_RUN.json",
        {
            "schema_version": 1,
            "run_id": fixture["run_id"],
            "subsystem": "demo",
            "status": status,
            "ordinary_user_message": "next action ready",
            "next_action": next_action,
            "artifacts": {
                "artifact_index": "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
                "photo3d_run": "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_RUN.json",
            },
        },
    )


def _cmd_args(fixture, *, confirm=False, source=None, output=None):
    return SimpleNamespace(
        subsystem="demo",
        artifact_index=str(fixture["index_path"]),
        source=source,
        confirm=confirm,
        output=output,
    )


def test_photo3d_handoff_preview_accept_baseline_does_not_mutate_index(tmp_path):
    from tools.photo3d_handoff import run_photo3d_handoff

    fixture = _contracts(tmp_path)
    _write_photo3d_run(
        fixture,
        {
            "kind": "accept_baseline",
            "requires_user_confirmation": True,
            "argv": ["python", "cad_pipeline.py", "accept-baseline", "--subsystem", "demo"],
        },
    )

    report = run_photo3d_handoff(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        source="run",
    )

    assert report["status"] == "awaiting_confirmation"
    assert report["confirmed"] is False
    assert report["source"] == "run"
    assert report["selected_action"]["kind"] == "accept_baseline"
    assert report["selected_action"]["argv"] == [
        sys.executable,
        "cad_pipeline.py",
        "accept-baseline",
        "--subsystem",
        "demo",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
        "--run-id",
        "RUN001",
    ]
    assert report["artifacts"]["photo3d_handoff"].endswith("RUN001/PHOTO3D_HANDOFF.json")

    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["accepted_baseline_run_id"] is None


def test_photo3d_handoff_confirm_accept_baseline_updates_index_and_reruns_loop(
    tmp_path,
    monkeypatch,
):
    import tools.photo3d_handoff as handoff
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    run_photo3d_gate(tmp_path, "demo", artifact_index_path=fixture["index_path"])
    _write_photo3d_run(
        fixture,
        {"kind": "accept_baseline", "requires_user_confirmation": True},
    )

    def fake_loop(project_root, subsystem, **kwargs):
        assert project_root == tmp_path
        assert subsystem == "demo"
        assert kwargs["artifact_index_path"] == fixture["index_path"]
        assert kwargs["max_rounds"] == 1
        assert kwargs["confirm_actions"] is False
        return {
            "run_id": "RUN001",
            "subsystem": "demo",
            "status": "ready_for_enhancement",
            "ordinary_user_message": "ready",
            "next_action": {"kind": "run_enhancement"},
            "artifacts": {"photo3d_run": "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_RUN.json"},
        }

    monkeypatch.setattr(handoff, "run_photo3d_loop", fake_loop)

    report = handoff.run_photo3d_handoff(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        source="run",
        confirm=True,
    )

    assert report["status"] == "executed"
    assert report["executed_action"]["returncode"] == 0
    assert report["post_handoff_photo3d_run"]["status"] == "ready_for_enhancement"
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["accepted_baseline_run_id"] == "RUN001"
    assert index["runs"]["RUN001"]["accepted_baseline"] is True


def test_photo3d_handoff_preview_enhancement_binds_active_render_dir(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_handoff as handoff

    fixture = _contracts(tmp_path)
    _accept_baseline(fixture)
    _write_photo3d_run(
        fixture,
        {
            "kind": "run_enhancement",
            "requires_user_confirmation": False,
            "argv": ["python", "cad_pipeline.py", "enhance", "--dir", "wrong"],
        },
        status="ready_for_enhancement",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        handoff.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    rc = cad_pipeline.cmd_photo3d_handoff(_cmd_args(fixture, source="run"))

    assert rc == 0
    report = json.loads((fixture["run_dir"] / "PHOTO3D_HANDOFF.json").read_text(encoding="utf-8"))
    assert report["status"] == "awaiting_confirmation"
    assert report["selected_action"]["kind"] == "run_enhancement"
    assert report["selected_action"]["argv"] == [
        sys.executable,
        "cad_pipeline.py",
        "enhance",
        "--subsystem",
        "demo",
        "--dir",
        "cad/output/renders/demo/RUN001",
    ]


def test_photo3d_handoff_confirm_enhancement_executes_current_run_command(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline
    import tools.photo3d_handoff as handoff

    fixture = _contracts(tmp_path)
    _accept_baseline(fixture)
    _write_photo3d_run(
        fixture,
        {"kind": "run_enhancement", "requires_user_confirmation": False},
        status="ready_for_enhancement",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="enhance ok", stderr="")

    monkeypatch.setattr(handoff.subprocess, "run", fake_run)

    rc = cad_pipeline.cmd_photo3d_handoff(_cmd_args(fixture, confirm=True, source="run"))

    assert rc == 0
    assert calls == [
        (
            [
                sys.executable,
                "cad_pipeline.py",
                "enhance",
                "--subsystem",
                "demo",
                "--dir",
                "cad/output/renders/demo/RUN001",
            ],
            {
                "cwd": str(tmp_path),
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "check": False,
                "shell": False,
            },
        )
    ]
    report = json.loads((fixture["run_dir"] / "PHOTO3D_HANDOFF.json").read_text(encoding="utf-8"))
    assert report["status"] == "executed"
    assert report["executed_action"]["stdout"] == "enhance ok"


def test_photo3d_handoff_confirm_enhance_check_uses_active_render_dir(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline
    import tools.photo3d_handoff as handoff

    fixture = _contracts(tmp_path)
    _write_photo3d_run(
        fixture,
        {
            "kind": "run_enhance_check",
            "requires_user_confirmation": False,
            "render_manifest": "cad/output/renders/demo/RUN001/render_manifest.json",
        },
        status="ready_for_enhance_check",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="check ok", stderr="")

    monkeypatch.setattr(handoff.subprocess, "run", fake_run)

    rc = cad_pipeline.cmd_photo3d_handoff(_cmd_args(fixture, confirm=True, source="run"))

    assert rc == 0
    assert calls == [[
        sys.executable,
        "cad_pipeline.py",
        "enhance-check",
        "--subsystem",
        "demo",
        "--dir",
        "cad/output/renders/demo/RUN001",
    ]]


def test_photo3d_handoff_rejects_mismatched_enhance_check_manifest(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_handoff as handoff

    fixture = _contracts(tmp_path)
    _write_photo3d_run(
        fixture,
        {
            "kind": "run_enhance_check",
            "requires_user_confirmation": False,
            "render_manifest": "cad/output/renders/demo/OLD/render_manifest.json",
        },
        status="ready_for_enhance_check",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        handoff.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    rc = cad_pipeline.cmd_photo3d_handoff(_cmd_args(fixture, confirm=True, source="run"))

    assert rc == 1
    report = json.loads((fixture["run_dir"] / "PHOTO3D_HANDOFF.json").read_text(encoding="utf-8"))
    assert report["status"] == "needs_manual_review"
    assert report["selected_action"]["kind"] == "run_enhance_check"
    assert "render_manifest" in report["selected_action"]["reason"]


def test_photo3d_handoff_confirm_action_plan_delegates_to_photo3d_run_confirm_actions(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline
    import tools.photo3d_handoff as handoff

    fixture = _contracts(tmp_path)
    _write_photo3d_run(
        fixture,
        {"kind": "confirm_action_plan", "requires_user_confirmation": True},
        status="awaiting_action_confirmation",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="loop ok", stderr="")

    monkeypatch.setattr(handoff.subprocess, "run", fake_run)

    rc = cad_pipeline.cmd_photo3d_handoff(_cmd_args(fixture, confirm=True, source="run"))

    assert rc == 0
    assert calls == [[
        sys.executable,
        "cad_pipeline.py",
        "photo3d-run",
        "--subsystem",
        "demo",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
        "--confirm-actions",
    ]]


def test_photo3d_handoff_rejects_terminal_delivery_action(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_handoff as handoff

    fixture = _contracts(tmp_path)
    _write_photo3d_run(
        fixture,
        {"kind": "delivery_complete", "requires_user_confirmation": False},
        status="enhancement_accepted",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        handoff.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    rc = cad_pipeline.cmd_photo3d_handoff(_cmd_args(fixture, confirm=True, source="run"))

    assert rc == 0
    report = json.loads((fixture["run_dir"] / "PHOTO3D_HANDOFF.json").read_text(encoding="utf-8"))
    assert report["status"] == "needs_manual_review"
    assert report["manual_action"]["kind"] == "delivery_complete"


def test_photo3d_handoff_confirm_unknown_action_is_blocked(tmp_path):
    from tools.photo3d_handoff import command_return_code, run_photo3d_handoff

    fixture = _contracts(tmp_path)
    _write_photo3d_run(
        fixture,
        {"kind": "future_unknown_action", "requires_user_confirmation": True},
        status="needs_manual_review",
    )

    report = run_photo3d_handoff(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        source="run",
        confirm=True,
    )

    assert report["status"] == "needs_manual_review"
    assert report["selected_action"]["classification"] == "manual"
    assert report["selected_action"]["kind"] == "future_unknown_action"
    assert command_return_code(report) == 1


def test_photo3d_handoff_rejects_output_outside_active_run_dir(tmp_path):
    from tools.photo3d_handoff import run_photo3d_handoff

    fixture = _contracts(tmp_path)
    _write_photo3d_run(
        fixture,
        {"kind": "accept_baseline", "requires_user_confirmation": True},
    )

    try:
        run_photo3d_handoff(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
            output_path=tmp_path / "cad" / "demo" / "PHOTO3D_HANDOFF.json",
        )
    except ValueError as exc:
        assert "active run directory" in str(exc)
    else:
        raise AssertionError("expected output outside active run directory to fail")
