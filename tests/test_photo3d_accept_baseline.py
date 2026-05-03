import json
from types import SimpleNamespace

from tests.test_change_scope_gate import _scope
from tests.test_photo3d_gate_contract import _contracts, _write_json


def test_photo3d_gate_uses_accepted_baseline_from_artifact_index(tmp_path):
    from tools.artifact_index import accept_run_baseline, build_artifact_index, register_run_artifacts
    from tools.contract_io import stable_json_hash
    from tools.photo3d_gate import run_photo3d_gate

    baseline = _contracts(tmp_path, run_id="BASE001")
    current = _contracts(tmp_path, run_id="RUN001")

    current_signature = current["payloads"]["assembly_signature"]
    current_signature["model_contract_hash"] = current["payloads"]["render_manifest"]["model_contract_hash"]
    _write_json(current["paths"]["assembly_signature"], current_signature)

    index = build_artifact_index("demo")
    register_run_artifacts(
        index,
        "BASE001",
        {
            key: value.relative_to(tmp_path).as_posix()
            for key, value in baseline["paths"].items()
        },
        active=False,
    )
    register_run_artifacts(
        index,
        "RUN001",
        {
            key: value.relative_to(tmp_path).as_posix()
            for key, value in current["paths"].items()
        },
        active=True,
    )
    accept_run_baseline(index, "BASE001")
    _write_json(current["index_path"], index)

    scope_path = current["run_dir"] / "CHANGE_SCOPE.json"
    _write_json(
        scope_path,
        _scope(
            run_id="RUN001",
            baseline_run_id="BASE001",
            baseline_assembly_signature_hash=stable_json_hash(
                baseline["payloads"]["assembly_signature"]
            ),
        ),
    )

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=current["index_path"],
        change_scope_path=scope_path,
    )

    assert report["status"] == "pass"
    assert report["warnings"] == []
    assert report["artifacts"]["baseline_assembly_signature"].endswith(
        "BASE001/ASSEMBLY_SIGNATURE.json"
    )


def test_cmd_accept_baseline_records_current_passing_report(tmp_path, monkeypatch):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    assert cad_pipeline.cmd_photo3d(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
            dry_run=False,
        )
    ) == 0

    rc = cad_pipeline.cmd_accept_baseline(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            run_id=None,
            report=None,
        )
    )

    assert rc == 0
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["accepted_baseline_run_id"] == "RUN001"
    assert index["runs"]["RUN001"]["accepted_baseline"] is True
    assert index["runs"]["RUN001"]["artifacts"]["photo3d_report"].endswith(
        "RUN001/PHOTO3D_REPORT.json"
    )
    report = json.loads((fixture["run_dir"] / "PHOTO3D_REPORT.json").read_text(encoding="utf-8"))
    assert report["artifact_hashes"]["assembly_signature"].startswith("sha256:")


def test_cmd_accept_baseline_rejects_report_outside_run_artifact_binding(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    assert cad_pipeline.cmd_photo3d(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
            dry_run=False,
        )
    ) == 0

    real_report = json.loads((fixture["run_dir"] / "PHOTO3D_REPORT.json").read_text(encoding="utf-8"))
    forged_report = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "forged_REPORT.json"
    _write_json(forged_report, real_report | {"status": "pass"})

    rc = cad_pipeline.cmd_accept_baseline(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            run_id=None,
            report=str(forged_report),
        )
    )

    assert rc == 1
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["accepted_baseline_run_id"] is None


def test_cmd_accept_baseline_rejects_stale_report_after_contract_mutation(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    assert cad_pipeline.cmd_photo3d(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
            dry_run=False,
        )
    ) == 0

    signature = dict(fixture["payloads"]["assembly_signature"])
    signature["instances"] = []
    _write_json(fixture["paths"]["assembly_signature"], signature)

    rc = cad_pipeline.cmd_accept_baseline(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            run_id=None,
            report=None,
        )
    )

    assert rc == 1
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["accepted_baseline_run_id"] is None


def test_cmd_accept_baseline_rejects_blocked_report(tmp_path, monkeypatch):
    import cad_pipeline

    fixture = _contracts(tmp_path, hero_quality="D")
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    assert cad_pipeline.cmd_photo3d(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
            dry_run=False,
        )
    ) == 1

    rc = cad_pipeline.cmd_accept_baseline(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            run_id=None,
            report=None,
        )
    )

    assert rc == 1
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["accepted_baseline_run_id"] is None
    assert index["runs"]["RUN001"].get("accepted_baseline") is not True
