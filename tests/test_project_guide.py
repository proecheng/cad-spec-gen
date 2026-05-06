import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _assert_no_forbidden_fields(value):
    forbidden = {"api_key", "key", "secret", "url", "base_url", "endpoint"}
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value), value
        for child in value.values():
            _assert_no_forbidden_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_fields(child)


def test_project_entry_guide_suggests_confirmed_subsystem_from_design_doc(tmp_path):
    from tools.project_guide import write_project_entry_guide

    design_doc = tmp_path / "docs" / "design" / "04-升降平台设计.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# 升降平台设计\n\n测试设计文档。", encoding="utf-8")

    report = write_project_entry_guide(tmp_path, design_doc)

    assert report["entry_mode"] == "design_doc"
    assert report["status"] == "needs_subsystem_confirmation"
    assert report["mutates_pipeline_state"] is False
    assert report["does_not_scan_directories"] is True
    assert report["design_doc"] == {
        "path": "docs/design/04-升降平台设计.md",
        "exists": True,
    }
    assert report["ordinary_user_message"] == (
        "项目向导已读取设计文档；请先确认要创建或继续的子系统名称。"
    )
    assert report["subsystem_candidates"][0] == {
        "subsystem": "sheng_jiang_ping_tai_she_ji",
        "source": "design_doc_filename",
        "confidence": "medium",
        "reason": "由显式设计文档文件名派生；需要用户确认后才进入子系统流程。",
    }
    assert report["next_action"]["kind"] == "confirm_subsystem"
    assert report["next_action"]["requires_user_confirmation"] is True
    assert report["next_action"]["options"][0]["argv"] == [
        "python",
        "cad_pipeline.py",
        "project-guide",
        "--subsystem",
        "sheng_jiang_ping_tai_she_ji",
        "--design-doc",
        "docs/design/04-升降平台设计.md",
    ]
    assert report["artifacts"]["project_guide"] == (
        ".cad-spec-gen/project-guide/PROJECT_GUIDE.json"
    )
    written = json.loads(
        (tmp_path / ".cad-spec-gen" / "project-guide" / "PROJECT_GUIDE.json").read_text(
            encoding="utf-8"
        )
    )
    assert written["next_action"] == report["next_action"]


def test_project_entry_guide_uses_ascii_design_doc_stem_as_candidate(tmp_path):
    from tools.project_guide import write_project_entry_guide

    design_doc = tmp_path / "docs" / "design" / "04-lifting-platform.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# Lifting Platform", encoding="utf-8")

    report = write_project_entry_guide(tmp_path, design_doc)

    assert report["subsystem_candidates"][0]["subsystem"] == "lifting_platform"
    assert report["next_action"]["options"][0]["argv"] == [
        "python",
        "cad_pipeline.py",
        "project-guide",
        "--subsystem",
        "lifting_platform",
        "--design-doc",
        "docs/design/04-lifting-platform.md",
    ]


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


def test_project_guide_embeds_model_quality_summary_when_geometry_report_exists(tmp_path):
    from tools.project_guide import write_project_guide

    subsystem_dir = tmp_path / "cad" / "demo"
    subsystem_dir.mkdir(parents=True)
    for name in ("CAD_SPEC.md", "params.py", "build_all.py", "assembly.py"):
        (subsystem_dir / name).write_text("ok", encoding="utf-8")
    _write_json(
        subsystem_dir / ".cad-spec-gen" / "geometry_report.json",
        {
            "schema_version": 1,
            "total": 2,
            "quality_counts": {"A": 1, "C": 1},
            "decisions": [
                {
                    "part_no": "A-001",
                    "name_cn": "可信电机",
                    "geometry_quality": "A",
                    "geometry_source": "REAL_STEP",
                    "adapter": "step_pool",
                    "requires_model_review": False,
                    "step_path": None,
                    "validated": True,
                },
                {
                    "part_no": "C-001",
                    "name_cn": "简化接头",
                    "geometry_quality": "C",
                    "geometry_source": "JINJA_TEMPLATE",
                    "adapter": "jinja_primitive",
                    "requires_model_review": True,
                    "step_path": None,
                    "validated": False,
                },
            ],
        },
    )

    report = write_project_guide(tmp_path, "demo")

    summary = report["model_quality_summary"]
    assert summary["source"] == "geometry_report"
    assert summary["source_report"] == "cad/demo/.cad-spec-gen/geometry_report.json"
    assert summary["binding_status"] == "project_report"
    assert summary["readiness_status"] == "needs_review"
    assert summary["photoreal_risk"] == "high"
    assert summary["source_counts"] == {
        "real_step": 1,
        "simplified_template": 1,
    }
    assert summary["recommended_next_action"]["kind"] == "review_models"
    assert report["stage_status"]["model_quality"] == {
        "exists": True,
        "path": "cad/demo/.cad-spec-gen/geometry_report.json",
        "readiness_status": "needs_review",
        "photoreal_risk": "high",
    }
    written = json.loads(
        (subsystem_dir / ".cad-spec-gen" / "PROJECT_GUIDE.json").read_text(
            encoding="utf-8"
        )
    )
    assert written["model_quality_summary"] == summary


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

    wizard = report["provider_wizard"]
    assert wizard["kind"] == "provider_preset_selection_wizard"
    assert wizard["source"] == "provider_choice.ordinary_user_options"
    assert wizard["mutates_pipeline_state"] is False
    assert wizard["executes_enhancement"] is False
    assert wizard["does_not_scan_directories"] is True
    assert wizard["default_provider_preset"] == "default"
    assert [step["id"] for step in wizard["steps"]] == [
        "choose_provider",
        "preview_handoff",
        "confirm_handoff",
    ]
    assert [option["provider_preset"] for option in wizard["options"]] == [
        "default",
        "engineering",
        "gemini",
        "fal",
        "fal_comfy",
        "comfyui",
    ]
    default_wizard_option = next(
        option for option in wizard["options"]
        if option["provider_preset"] == "default"
    )
    assert default_wizard_option["is_default"] is True
    engineering_wizard_option = next(
        option for option in wizard["options"]
        if option["provider_preset"] == "engineering"
    )
    assert engineering_wizard_option["is_default"] is False
    assert engineering_wizard_option["title"] == engineering_option["ordinary_user_title"]
    assert engineering_wizard_option["summary"] == engineering_option["ordinary_user_summary"]
    assert engineering_wizard_option["recommended_when"] == engineering_option["recommended_when"]
    assert engineering_wizard_option["requires_setup"] is False
    assert engineering_wizard_option["preview_action"]["argv"] == engineering_option["argv"]
    assert "--confirm" not in engineering_wizard_option["preview_action"]["argv"]
    forbidden = {"api_key", "key", "secret", "url", "base_url", "endpoint"}
    for option in wizard["options"]:
        assert forbidden.isdisjoint(option), option["provider_preset"]
        assert forbidden.isdisjoint(option["preview_action"]), option["provider_preset"]


def test_project_guide_provider_wizard_embeds_safe_provider_health(tmp_path, monkeypatch):
    from tools.project_guide import write_project_guide

    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("COMFYUI_ROOT", raising=False)

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
            "next_action": {"kind": "run_enhancement"},
        },
    )
    for name in ("CAD_SPEC.md", "params.py", "build_all.py", "assembly.py"):
        (tmp_path / "cad" / "demo" / name).write_text("ok", encoding="utf-8")

    report = write_project_guide(tmp_path, "demo")

    wizard = report["provider_wizard"]
    assert wizard["health_summary"]["source"] == "provider_health"
    assert wizard["health_summary"]["mutates_pipeline_state"] is False
    assert wizard["health_summary"]["executes_enhancement"] is False
    assert wizard["health_summary"]["does_not_scan_directories"] is True
    by_id = {option["provider_preset"]: option for option in wizard["options"]}
    assert by_id["engineering"]["health"]["status"] == "available"
    assert by_id["gemini"]["health"]["status"] == "needs_setup"
    assert by_id["fal"]["health"]["status"] == "needs_setup"
    assert by_id["fal_comfy"]["health"]["status"] == "needs_setup"
    assert by_id["comfyui"]["health"]["status"] == "needs_setup"
    for option in wizard["options"]:
        assert option["health"]["provider_preset"] == option["provider_preset"]
        _assert_no_forbidden_fields(option["health"])


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
    assert "provider_wizard" not in report


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


def test_project_guide_cli_from_design_doc_writes_entry_report(tmp_path, monkeypatch):
    import cad_pipeline

    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    design_doc = tmp_path / "docs" / "design" / "04-升降平台设计.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# 升降平台设计", encoding="utf-8")

    rc = cad_pipeline.cmd_project_guide(
        SimpleNamespace(
            subsystem=None,
            design_doc=design_doc,
            from_design_doc=True,
            artifact_index=None,
            output=None,
        )
    )

    assert rc == 0
    report = json.loads(
        (tmp_path / ".cad-spec-gen" / "project-guide" / "PROJECT_GUIDE.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["entry_mode"] == "design_doc"
    assert report["status"] == "needs_subsystem_confirmation"
    assert report["next_action"]["kind"] == "confirm_subsystem"


def test_project_entry_guide_rejects_output_outside_entry_guide_directory(tmp_path):
    from tools.project_guide import write_project_entry_guide

    design_doc = tmp_path / "docs" / "design" / "04-lifting-platform.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# Lifting Platform", encoding="utf-8")

    with pytest.raises(ValueError, match="must stay in .cad-spec-gen/project-guide"):
        write_project_entry_guide(
            tmp_path,
            design_doc,
            output_path=tmp_path / "cad" / "demo" / ".cad-spec-gen" / "PROJECT_GUIDE.json",
        )


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
