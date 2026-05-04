import json

from tests.test_photo3d_gate_contract import _contracts, _write_json


def test_render_stale_reason_generates_rerun_render_action(tmp_path):
    from tools.photo3d_actions import build_action_plan

    report = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "status": "blocked",
        "blocking_reasons": [
            {"code": "render_file_hash_mismatch", "path": "cad/output/renders/demo/RUN001/V1.png"},
        ],
        "artifacts": {
            "photo3d_report": "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_REPORT.json",
            "render_manifest": "cad/output/renders/demo/RUN001/render_manifest.json",
        },
    }

    plan = build_action_plan(tmp_path, report)

    assert plan["status"] == "blocked"
    assert plan["actions"][0]["action_id"] == "rerun_render"
    assert plan["actions"][0]["kind"] == "cli"
    assert "cad_pipeline.py photo3d-recover --subsystem demo --run-id RUN001" in plan["actions"][0]["command"]
    assert plan["actions"][0]["argv"] == [
        "python",
        "cad_pipeline.py",
        "photo3d-recover",
        "--subsystem",
        "demo",
        "--run-id",
        "RUN001",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
        "--action",
        "render",
    ]
    assert plan["actions"][0]["run_id"] == "RUN001"
    assert plan["actions"][0]["recovery_action"] == "render"


def test_missing_model_reason_generates_user_request_action(tmp_path):
    from tools.photo3d_actions import build_action_plan

    report = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "status": "blocked",
        "blocking_reasons": [
            {"code": "model_quality_below_threshold", "part_no": "P-100-01"},
        ],
        "artifacts": {},
    }

    plan = build_action_plan(tmp_path, report)

    assert plan["actions"][0]["action_id"] == "ask_for_model"
    assert plan["actions"][0]["kind"] == "user_request"
    assert plan["actions"][0]["part_no"] == "P-100-01"


def test_photo3d_gate_writes_action_plan_and_llm_context_for_blocked_report(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path, hero_quality="D")

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    action_plan_path = fixture["run_dir"] / "ACTION_PLAN.json"
    llm_pack_path = fixture["run_dir"] / "LLM_CONTEXT_PACK.json"
    assert report["status"] == "blocked"
    assert report["artifacts"]["action_plan"] == "cad/demo/.cad-spec-gen/runs/RUN001/ACTION_PLAN.json"
    assert report["artifacts"]["llm_context_pack"] == "cad/demo/.cad-spec-gen/runs/RUN001/LLM_CONTEXT_PACK.json"
    assert action_plan_path.is_file()
    assert llm_pack_path.is_file()

    action_plan = json.loads(action_plan_path.read_text(encoding="utf-8"))
    llm_pack = json.loads(llm_pack_path.read_text(encoding="utf-8"))
    assert {action["kind"] for action in action_plan["actions"]} <= {"cli", "user_request", "manual_review"}
    assert "ask_for_model" in {action["action_id"] for action in action_plan["actions"]}
    assert llm_pack["allowed_actions"] == [action["action_id"] for action in action_plan["actions"]]
    assert set(llm_pack["artifact_paths"]) <= {
        "product_graph",
        "model_contract",
        "assembly_signature",
        "render_manifest",
        "photo3d_report",
        "action_plan",
        "llm_context_pack",
    }


def test_photo3d_gate_writes_actions_when_artifact_index_is_missing_required_contract(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    del index["runs"]["RUN001"]["artifacts"]["model_contract"]
    _write_json(fixture["index_path"], index)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert (fixture["run_dir"] / "ACTION_PLAN.json").is_file()
    assert (fixture["run_dir"] / "LLM_CONTEXT_PACK.json").is_file()
    assert report["artifacts"]["action_plan"] == "cad/demo/.cad-spec-gen/runs/RUN001/ACTION_PLAN.json"
    action_plan = json.loads((fixture["run_dir"] / "ACTION_PLAN.json").read_text(encoding="utf-8"))
    assert "ask_for_model" in {action["action_id"] for action in action_plan["actions"]}


def test_missing_render_manifest_artifact_generates_rerun_render_action(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    del index["runs"]["RUN001"]["artifacts"]["render_manifest"]
    _write_json(fixture["index_path"], index)

    run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    action_plan = json.loads((fixture["run_dir"] / "ACTION_PLAN.json").read_text(encoding="utf-8"))
    assert "rerun_render" in {action["action_id"] for action in action_plan["actions"]}
    render_action = next(action for action in action_plan["actions"] if action["action_id"] == "rerun_render")
    assert render_action["argv"] == [
        "python",
        "cad_pipeline.py",
        "photo3d-recover",
        "--subsystem",
        "demo",
        "--run-id",
        "RUN001",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
        "--action",
        "render",
    ]


def test_action_plan_uses_report_artifact_index_for_run_aware_recovery(tmp_path):
    from tools.photo3d_actions import build_action_plan

    report = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "artifact_index": "artifacts/custom/ARTIFACT_INDEX.json",
        "status": "blocked",
        "blocking_reasons": [{"code": "render_file_hash_mismatch"}],
        "artifacts": {},
    }

    plan = build_action_plan(tmp_path, report)

    assert plan["actions"][0]["argv"] == [
        "python",
        "cad_pipeline.py",
        "photo3d-recover",
        "--subsystem",
        "demo",
        "--run-id",
        "RUN001",
        "--artifact-index",
        "artifacts/custom/ARTIFACT_INDEX.json",
        "--action",
        "render",
    ]


def test_llm_context_pack_rejects_unregistered_absolute_artifact_paths(tmp_path):
    from tools.photo3d_actions import build_llm_context_pack

    report = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "status": "blocked",
        "ordinary_user_message": "照片级出图已停止。",
        "blocking_reasons": [{"code": "render_file_hash_mismatch"}],
        "artifacts": {
            "photo3d_report": "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_REPORT.json",
            "old_png": str(tmp_path.parent / "old_project" / "V1.png"),
        },
    }
    action_plan = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "status": "blocked",
        "actions": [{"action_id": "rerun_render", "kind": "cli"}],
    }

    pack = build_llm_context_pack(tmp_path, report, action_plan)

    assert "old_png" not in pack["artifact_paths"]
    assert pack["artifact_paths"] == {
        "photo3d_report": "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_REPORT.json"
    }


def test_llm_context_pack_rejects_same_run_id_from_other_subsystem(tmp_path):
    from tools.photo3d_actions import build_llm_context_pack

    report = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "status": "blocked",
        "ordinary_user_message": "照片级出图已停止。",
        "blocking_reasons": [{"code": "render_file_hash_mismatch"}],
        "artifacts": {
            "photo3d_report": "cad/other_demo/.cad-spec-gen/runs/RUN001/PHOTO3D_REPORT.json",
            "render_manifest": "cad/output/renders/other_demo/RUN001/render_manifest.json",
        },
    }
    action_plan = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "status": "blocked",
        "actions": [{"action_id": "rerun_render", "kind": "cli"}],
    }

    pack = build_llm_context_pack(tmp_path, report, action_plan)

    assert pack["artifact_paths"] == {}


def test_action_plan_does_not_emit_cli_for_invalid_subsystem_token(tmp_path):
    from tools.photo3d_actions import build_action_plan

    report = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo;Remove-Item",
        "status": "blocked",
        "blocking_reasons": [{"code": "render_file_hash_mismatch"}],
        "artifacts": {},
    }

    plan = build_action_plan(tmp_path, report)

    assert plan["actions"] == [{
        "action_id": "review_run_context",
        "kind": "manual_review",
        "label_cn": "复查当前 run_id、子系统和路径上下文",
        "requires_user_input": True,
        "risk": "medium",
        "run_id": "RUN001",
    }]


def test_gate_writes_action_outputs_to_active_run_when_index_points_to_old_run(tmp_path):
    from tools.artifact_index import build_artifact_index, register_run_artifacts
    from tools.photo3d_gate import run_photo3d_gate

    old = _contracts(tmp_path, run_id="RUN001")
    current = _contracts(tmp_path, run_id="RUN002")
    index = build_artifact_index("demo")
    register_run_artifacts(
        index,
        "RUN002",
        {
            key: value.relative_to(tmp_path).as_posix()
            for key, value in old["paths"].items()
        },
        active=True,
    )
    _write_json(current["index_path"], index)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=current["index_path"],
    )

    assert report["status"] == "blocked"
    assert (current["run_dir"] / "ACTION_PLAN.json").is_file()
    assert (current["run_dir"] / "LLM_CONTEXT_PACK.json").is_file()
    assert not (old["run_dir"] / "ACTION_PLAN.json").exists()
    assert report["artifacts"]["action_plan"] == "cad/demo/.cad-spec-gen/runs/RUN002/ACTION_PLAN.json"
