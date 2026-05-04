import json
import sys
from types import SimpleNamespace

from tests.test_photo3d_gate_contract import _contracts, _write_json


def _write_action_inputs(
    tmp_path,
    *,
    action=None,
    actions=None,
    plan_run_id="RUN001",
    autopilot_run_id="RUN001",
):
    fixture = _contracts(tmp_path)
    run_dir = fixture["run_dir"]
    action_items = actions if actions is not None else [action]
    action_plan_rel = "cad/demo/.cad-spec-gen/runs/RUN001/ACTION_PLAN.json"
    autopilot_rel = "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_AUTOPILOT.json"
    llm_pack_rel = "cad/demo/.cad-spec-gen/runs/RUN001/LLM_CONTEXT_PACK.json"
    action_plan = {
        "schema_version": 1,
        "run_id": plan_run_id,
        "subsystem": "demo",
        "status": "blocked",
        "actions": action_items,
    }
    autopilot = {
        "schema_version": 1,
        "run_id": autopilot_run_id,
        "subsystem": "demo",
        "gate_status": "blocked",
        "status": "blocked",
        "next_action": {
            "kind": "follow_action_plan",
            "requires_user_confirmation": False,
            "action_plan": action_plan_rel,
            "llm_context_pack": llm_pack_rel,
        },
        "artifacts": {
            "action_plan": action_plan_rel,
            "llm_context_pack": llm_pack_rel,
            "photo3d_autopilot": autopilot_rel,
        },
    }
    _write_json(run_dir / "ACTION_PLAN.json", action_plan)
    _write_json(run_dir / "LLM_CONTEXT_PACK.json", {"schema_version": 1})
    _write_json(run_dir / "PHOTO3D_AUTOPILOT.json", autopilot)
    return fixture


def _rerun_render_action():
    return {
        "action_id": "rerun_render",
        "kind": "cli",
        "label_cn": "重新构建并渲染当前装配",
        "command": "python cad_pipeline.py render --subsystem demo",
        "argv": ["python", "cad_pipeline.py", "render", "--subsystem", "demo"],
        "requires_user_input": False,
        "risk": "low",
        "run_id": "RUN001",
    }


def _rerun_build_action():
    return {
        "action_id": "rerun_build",
        "kind": "cli",
        "label_cn": "重新构建当前装配并生成运行时签名",
        "command": "python cad_pipeline.py build --subsystem demo",
        "argv": ["python", "cad_pipeline.py", "build", "--subsystem", "demo"],
        "requires_user_input": False,
        "risk": "low",
        "run_id": "RUN001",
    }


def _user_request_action():
    return {
        "action_id": "ask_for_model",
        "kind": "user_request",
        "label_cn": "请用户提供或选择更高质量的零件模型",
        "part_no": "P-100-01",
        "requires_user_input": True,
        "risk": "medium",
        "run_id": "RUN001",
    }


def _cmd_args(fixture, *, confirm=False):
    return SimpleNamespace(
        subsystem="demo",
        artifact_index=str(fixture["index_path"]),
        autopilot_report=None,
        action_plan=None,
        action_id=None,
        confirm=confirm,
        output=None,
    )


def test_photo3d_action_preview_does_not_execute_cli(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_action_runner as runner

    fixture = _write_action_inputs(tmp_path, action=_rerun_render_action())
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    calls = []
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    rc = cad_pipeline.cmd_photo3d_action(_cmd_args(fixture, confirm=False))

    assert rc == 0
    assert calls == []
    report = json.loads((fixture["run_dir"] / "PHOTO3D_ACTION_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "awaiting_confirmation"
    assert report["confirmed"] is False
    assert report["executable_actions"][0]["action_id"] == "rerun_render"
    assert report["ordinary_user_message"] == "已找到可安全执行的动作；加 --confirm 后才会执行。"


def test_photo3d_action_confirm_executes_low_risk_cli_with_current_interpreter(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline
    import tools.photo3d_action_runner as runner

    fixture = _write_action_inputs(tmp_path, action=_rerun_render_action())
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="render ok", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    rc = cad_pipeline.cmd_photo3d_action(_cmd_args(fixture, confirm=True))

    assert rc == 0
    assert calls == [
        (
            [sys.executable, "cad_pipeline.py", "render", "--subsystem", "demo"],
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
    report = json.loads((fixture["run_dir"] / "PHOTO3D_ACTION_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "executed"
    assert report["executed_actions"][0]["returncode"] == 0
    assert report["executed_actions"][0]["argv"] == [
        sys.executable,
        "cad_pipeline.py",
        "render",
        "--subsystem",
        "demo",
    ]


def test_photo3d_action_confirm_keeps_user_request_for_human(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_action_runner as runner

    fixture = _write_action_inputs(tmp_path, action=_user_request_action())
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    rc = cad_pipeline.cmd_photo3d_action(_cmd_args(fixture, confirm=True))

    assert rc == 1
    report = json.loads((fixture["run_dir"] / "PHOTO3D_ACTION_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "needs_user_input"
    assert report["user_input_actions"][0]["action_id"] == "ask_for_model"
    assert report["ordinary_user_message"] == "当前动作需要用户输入；请按报告里的 user_input_actions 提供资料。"


def test_photo3d_action_rejects_action_plan_run_id_drift(tmp_path):
    from tools.photo3d_action_runner import run_photo3d_action

    fixture = _write_action_inputs(
        tmp_path,
        action=_rerun_render_action(),
        plan_run_id="RUN999",
    )

    try:
        run_photo3d_action(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
            confirm=True,
        )
    except ValueError as exc:
        assert "active_run_id" in str(exc)
    else:
        raise AssertionError("expected action plan run_id drift to be rejected")


def test_photo3d_action_rejects_autopilot_run_id_drift(tmp_path):
    from tools.photo3d_action_runner import run_photo3d_action

    fixture = _write_action_inputs(
        tmp_path,
        action=_rerun_render_action(),
        autopilot_run_id="RUN999",
    )

    try:
        run_photo3d_action(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
            confirm=True,
        )
    except ValueError as exc:
        assert "active_run_id" in str(exc)
    else:
        raise AssertionError("expected autopilot report run_id drift to be rejected")


def test_photo3d_action_rejects_action_plan_outside_active_run_dir(tmp_path):
    from tools.photo3d_action_runner import run_photo3d_action

    fixture = _write_action_inputs(tmp_path, action=_rerun_render_action())
    outside_plan = tmp_path / "cad" / "demo" / "ACTION_PLAN.json"
    _write_json(
        outside_plan,
        {
            "schema_version": 1,
            "run_id": "RUN001",
            "subsystem": "demo",
            "actions": [_rerun_render_action()],
        },
    )

    try:
        run_photo3d_action(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
            action_plan_path=outside_plan,
            confirm=True,
        )
    except ValueError as exc:
        assert "active run directory" in str(exc)
    else:
        raise AssertionError("expected action plan outside run dir to be rejected")


def test_photo3d_action_rejects_output_outside_active_run_dir(tmp_path):
    from tools.photo3d_action_runner import run_photo3d_action

    fixture = _write_action_inputs(tmp_path, action=_rerun_render_action())

    try:
        run_photo3d_action(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
            output_path=tmp_path / "cad" / "demo" / "PHOTO3D_ACTION_RUN.json",
        )
    except ValueError as exc:
        assert "active run directory" in str(exc)
    else:
        raise AssertionError("expected output outside run dir to be rejected")


def test_photo3d_action_confirm_returns_failure_when_cli_fails(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_action_runner as runner

    fixture = _write_action_inputs(tmp_path, action=_rerun_render_action())
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    def fake_run(argv, **kwargs):
        return SimpleNamespace(returncode=7, stdout="", stderr="render failed")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    rc = cad_pipeline.cmd_photo3d_action(_cmd_args(fixture, confirm=True))

    assert rc == 1
    report = json.loads((fixture["run_dir"] / "PHOTO3D_ACTION_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "execution_failed"
    assert report["executed_actions"][0]["returncode"] == 7
    assert report["executed_actions"][0]["stderr"] == "render failed"


def test_photo3d_action_confirm_stops_after_first_cli_failure(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_action_runner as runner

    fixture = _write_action_inputs(
        tmp_path,
        actions=[_rerun_build_action(), _rerun_render_action()],
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=7, stdout="", stderr="build failed")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    rc = cad_pipeline.cmd_photo3d_action(_cmd_args(fixture, confirm=True))

    assert rc == 1
    assert calls == [[sys.executable, "cad_pipeline.py", "build", "--subsystem", "demo"]]
    report = json.loads((fixture["run_dir"] / "PHOTO3D_ACTION_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "execution_failed"
    assert report["executed_actions"][0]["action_id"] == "rerun_build"
    assert report["skipped_actions"] == [
        {
            "action_id": "rerun_render",
            "reason": "skipped_due_to_previous_failure",
        }
    ]


def test_photo3d_action_executed_with_followup_returns_success(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_action_runner as runner

    fixture = _write_action_inputs(
        tmp_path,
        actions=[_rerun_render_action(), _user_request_action()],
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    def fake_run(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout="render ok", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    rc = cad_pipeline.cmd_photo3d_action(_cmd_args(fixture, confirm=True))

    assert rc == 0
    report = json.loads((fixture["run_dir"] / "PHOTO3D_ACTION_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "executed_with_followup"
    assert report["executed_actions"][0]["action_id"] == "rerun_render"
    assert report["user_input_actions"][0]["action_id"] == "ask_for_model"


def test_photo3d_action_rejects_duplicate_selected_action_id(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_action_runner as runner

    duplicate = _rerun_render_action()
    duplicate["command"] = "python cad_pipeline.py build --subsystem demo"
    duplicate["argv"] = ["python", "cad_pipeline.py", "build", "--subsystem", "demo"]
    fixture = _write_action_inputs(
        tmp_path,
        actions=[_rerun_render_action(), duplicate],
    )
    args = _cmd_args(fixture, confirm=True)
    args.action_id = "rerun_render"
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    rc = cad_pipeline.cmd_photo3d_action(args)

    assert rc == 1
    report = json.loads((fixture["run_dir"] / "PHOTO3D_ACTION_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "needs_manual_review"
    assert report["rejected_actions"] == [
        {
            "action_id": "rerun_render",
            "reason": "duplicate action_id in ACTION_PLAN.json",
        }
    ]


def test_photo3d_action_rejects_action_plan_override_that_differs_from_autopilot(
    tmp_path,
):
    from tools.photo3d_action_runner import run_photo3d_action

    fixture = _write_action_inputs(tmp_path, action=_rerun_render_action())
    alternate_plan = fixture["run_dir"] / "ALT_ACTION_PLAN.json"
    _write_json(
        alternate_plan,
        {
            "schema_version": 1,
            "run_id": "RUN001",
            "subsystem": "demo",
            "actions": [_rerun_build_action()],
        },
    )

    try:
        run_photo3d_action(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
            action_plan_path=alternate_plan,
            confirm=True,
        )
    except ValueError as exc:
        assert "PHOTO3D_AUTOPILOT.json action_plan" in str(exc)
    else:
        raise AssertionError("expected alternate action plan to be rejected")


def test_photo3d_action_rejects_nonstandard_output_filename(tmp_path):
    from tools.photo3d_action_runner import run_photo3d_action

    fixture = _write_action_inputs(tmp_path, action=_rerun_render_action())

    try:
        run_photo3d_action(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
            output_path=fixture["run_dir"] / "ACTION_PLAN.json",
        )
    except ValueError as exc:
        assert "PHOTO3D_ACTION_RUN.json" in str(exc)
    else:
        raise AssertionError("expected nonstandard output filename to be rejected")


def test_photo3d_action_rejects_non_allowlisted_cli_action(tmp_path, monkeypatch):
    import cad_pipeline
    import tools.photo3d_action_runner as runner

    enhance = {
        "action_id": "malicious_enhance",
        "kind": "cli",
        "label_cn": "不应执行的增强",
        "argv": ["python", "cad_pipeline.py", "enhance", "--subsystem", "demo"],
        "requires_user_input": False,
        "risk": "low",
        "run_id": "RUN001",
    }
    fixture = _write_action_inputs(tmp_path, action=enhance)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    rc = cad_pipeline.cmd_photo3d_action(_cmd_args(fixture, confirm=True))

    assert rc == 1
    report = json.loads((fixture["run_dir"] / "PHOTO3D_ACTION_RUN.json").read_text(encoding="utf-8"))
    assert report["status"] == "needs_manual_review"
    assert report["rejected_actions"][0]["action_id"] == "malicious_enhance"
    assert "not an allowed Photo3D recovery command" in report["rejected_actions"][0]["reason"]
