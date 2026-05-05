import json
from types import SimpleNamespace

from tools.artifact_index import build_artifact_index, register_run_artifacts
from tools.contract_io import stable_json_hash
from tools.render_qa import build_render_manifest

from tests.test_photo3d_gate_contract import _contracts, _render_png, _write_json


def _register_baseline_and_current(project_root, baseline, current):
    index = build_artifact_index("demo")
    register_run_artifacts(
        index,
        baseline["run_id"],
        {
            key: value.relative_to(project_root).as_posix()
            for key, value in baseline["paths"].items()
        },
        active=False,
    )
    index["runs"][baseline["run_id"]]["accepted_baseline"] = True
    index["accepted_baseline_run_id"] = baseline["run_id"]
    register_run_artifacts(
        index,
        current["run_id"],
        {
            key: value.relative_to(project_root).as_posix()
            for key, value in current["paths"].items()
        },
        active=True,
    )
    _write_json(current["index_path"], index)
    return index


def _add_current_view(project_root, fixture, filename):
    png = fixture["render_dir"] / filename
    _render_png(png)
    manifest = build_render_manifest(
        project_root,
        fixture["render_dir"],
        sorted(fixture["render_dir"].glob("*.png")),
        subsystem="demo",
        run_id=fixture["run_id"],
        path_context_hash="sha256:pathctx",
        product_graph=fixture["payloads"]["product_graph"],
        model_contract=fixture["payloads"]["model_contract"],
        assembly_signature=fixture["payloads"]["assembly_signature"],
    )
    fixture["payloads"]["render_manifest"] = manifest
    _write_json(fixture["paths"]["render_manifest"], manifest)
    return png


def test_render_visual_regression_blocks_when_active_run_loses_baseline_view_and_instance(tmp_path):
    from tools.render_visual_regression import run_render_visual_regression

    baseline = _contracts(tmp_path, run_id="BASELINE")
    _add_current_view(tmp_path, baseline, "V2_side.png")
    current = _contracts(tmp_path, run_id="RUN001")
    _register_baseline_and_current(tmp_path, baseline, current)

    signature = current["payloads"]["assembly_signature"]
    signature["instances"] = signature["instances"][:1]
    signature["coverage"]["matched_total"] = 1
    signature["coverage"]["missing_instance_total"] = 1
    _write_json(current["paths"]["assembly_signature"], signature)
    manifest = build_render_manifest(
        tmp_path,
        current["render_dir"],
        [current["render_dir"] / "V1_front.png"],
        subsystem="demo",
        run_id="RUN001",
        path_context_hash="sha256:pathctx",
        product_graph=current["payloads"]["product_graph"],
        model_contract=current["payloads"]["model_contract"],
        assembly_signature=signature,
    )
    _write_json(current["paths"]["render_manifest"], manifest)

    report = run_render_visual_regression(
        tmp_path,
        "demo",
        artifact_index_path=current["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["baseline"]["run_id"] == "BASELINE"
    assert report["current"]["run_id"] == "RUN001"
    assert report["counts"]["baseline_views"] == 2
    assert report["counts"]["current_views"] == 1
    assert report["counts"]["baseline_instances"] == 2
    assert report["counts"]["current_instances"] == 1
    assert {reason["code"] for reason in report["blocking_reasons"]} >= {
        "render_view_missing_from_baseline",
        "assembly_instance_missing_from_baseline",
        "assembly_instance_missing_from_product_graph",
    }
    written = json.loads(
        (current["run_dir"] / "RENDER_VISUAL_REGRESSION.json").read_text(
            encoding="utf-8"
        )
    )
    assert written["status"] == "blocked"


def test_render_visual_regression_rejects_active_render_manifest_bound_to_wrong_run_dir(tmp_path):
    from tools.render_visual_regression import run_render_visual_regression

    fixture = _contracts(tmp_path, run_id="RUN001")
    index = build_artifact_index("demo")
    register_run_artifacts(
        index,
        "RUN001",
        {
            key: value.relative_to(tmp_path).as_posix()
            for key, value in fixture["paths"].items()
        },
        active=True,
    )
    _write_json(fixture["index_path"], index)
    manifest = fixture["payloads"]["render_manifest"]
    old_render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "OLD_RUN"
    old_render_dir.mkdir(parents=True)
    manifest["render_dir_rel_project"] = old_render_dir.relative_to(tmp_path).as_posix()
    manifest["render_dir_abs_resolved"] = str(old_render_dir.resolve())
    manifest["render_dir"] = str(old_render_dir.resolve())
    _write_json(fixture["paths"]["render_manifest"], manifest)

    report = run_render_visual_regression(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["baseline"]["status"] == "not_configured"
    assert report["blocking_reasons"][0]["code"] == "render_dir_not_active_run"


def test_render_visual_regression_warns_when_view_has_no_instance_evidence(tmp_path):
    from tools.render_visual_regression import run_render_visual_regression

    fixture = _contracts(tmp_path, run_id="RUN001")

    report = run_render_visual_regression(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "warning"
    assert report["baseline"]["status"] == "not_configured"
    assert report["blocking_reasons"] == []
    assert report["warnings"][0]["code"] == "render_view_instance_evidence_missing"
    assert report["ordinary_user_message"].startswith("渲染视觉一致性基本通过")


def test_render_visual_regression_uses_view_instance_evidence_union_when_available(tmp_path):
    from tools.render_visual_regression import run_render_visual_regression

    fixture = _contracts(tmp_path, run_id="RUN001")
    manifest = fixture["payloads"]["render_manifest"]
    manifest["files"][0]["visible_instance_ids"] = ["P-100-01#01"]
    _write_json(fixture["paths"]["render_manifest"], manifest)

    report = run_render_visual_regression(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "render_evidence_missing_required_instance"
    assert report["blocking_reasons"][0]["missing_instance_ids"] == ["P-100-02#01"]


def test_cmd_render_visual_check_writes_report_and_returns_nonzero_when_blocked(tmp_path, monkeypatch):
    import cad_pipeline

    fixture = _contracts(tmp_path, run_id="RUN001")
    manifest = fixture["payloads"]["render_manifest"]
    manifest["subsystem"] = "wrong_demo"
    _write_json(fixture["paths"]["render_manifest"], manifest)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_render_visual_check(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            baseline_manifest=None,
            baseline_signature=None,
            output=None,
        )
    )

    assert rc == 1
    report = json.loads(
        (fixture["run_dir"] / "RENDER_VISUAL_REGRESSION.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "subsystem_mismatch"


def test_render_visual_regression_blocks_current_manifest_hash_drift(tmp_path):
    from tools.render_visual_regression import run_render_visual_regression

    fixture = _contracts(tmp_path, run_id="RUN001")
    graph = fixture["payloads"]["product_graph"]
    graph["instances"].append(
        {
            "instance_id": "P-100-03#01",
            "part_no": "P-100-03",
            "required": True,
            "render_policy": "required",
            "visual_priority": "normal",
        }
    )
    _write_json(fixture["paths"]["product_graph"], graph)
    model_contract = fixture["payloads"]["model_contract"]
    model_contract["product_graph_hash"] = stable_json_hash(graph)
    _write_json(fixture["paths"]["model_contract"], model_contract)

    report = run_render_visual_regression(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert "render_manifest_product_graph_hash_mismatch" in {
        reason["code"] for reason in report["blocking_reasons"]
    }


def test_render_visual_regression_blocks_duplicate_manifest_views(tmp_path):
    from tools.render_visual_regression import run_render_visual_regression

    fixture = _contracts(tmp_path, run_id="RUN001")
    duplicate = dict(fixture["payloads"]["render_manifest"]["files"][0])
    duplicate["path_rel_project"] = fixture["payloads"]["render_manifest"]["files"][0][
        "path_rel_project"
    ]
    fixture["payloads"]["render_manifest"]["files"].append(duplicate)
    _write_json(fixture["paths"]["render_manifest"], fixture["payloads"]["render_manifest"])

    report = run_render_visual_regression(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "render_view_duplicate"
    assert report["blocking_reasons"][0]["view"] == "V1"


def test_render_visual_regression_blocks_lost_per_view_evidence_from_baseline(tmp_path):
    from tools.render_visual_regression import run_render_visual_regression

    baseline = _contracts(tmp_path, run_id="BASELINE")
    manifest = baseline["payloads"]["render_manifest"]
    manifest["files"][0]["visible_instance_ids"] = ["P-100-01#01", "P-100-02#01"]
    _write_json(baseline["paths"]["render_manifest"], manifest)
    current = _contracts(tmp_path, run_id="RUN001")
    _register_baseline_and_current(tmp_path, baseline, current)

    report = run_render_visual_regression(
        tmp_path,
        "demo",
        artifact_index_path=current["index_path"],
    )

    assert report["status"] == "blocked"
    assert "render_view_instance_evidence_missing_from_current" in {
        reason["code"] for reason in report["blocking_reasons"]
    }
