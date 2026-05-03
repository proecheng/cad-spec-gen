import json

from tests.test_photo3d_gate_contract import _contracts, _write_json


def test_hero_model_quality_below_threshold_blocks_photo3d(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path, hero_quality="D")
    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "model_quality_below_threshold"
    assert report["blocking_reasons"][0]["part_no"] == "P-100-01"


def test_missing_required_instance_blocks_photo3d(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    signature = fixture["payloads"]["assembly_signature"]
    signature["instances"] = signature["instances"][:1]
    signature["coverage"]["matched_total"] = 1
    signature["coverage"]["missing_instance_total"] = 1
    signature["blocking_reasons"] = [{
        "code": "missing_required_instance",
        "instance_id": "P-100-02#01",
        "part_no": "P-100-02",
    }]
    _write_json(fixture["paths"]["assembly_signature"], signature)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert {reason["code"] for reason in report["blocking_reasons"]} >= {
        "missing_required_instance",
        "render_manifest_assembly_signature_hash_mismatch",
    }


def test_render_manifest_blocked_status_blocks_photo3d(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    manifest = fixture["payloads"]["render_manifest"]
    manifest["status"] = "blocked"
    manifest["blocking_reasons"] = [{"code": "render_qa_failed", "message": "空图"}]
    _write_json(fixture["paths"]["render_manifest"], manifest)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert {reason["code"] for reason in report["blocking_reasons"]} == {"render_qa_failed"}


def test_photo3d_report_counts_are_product_assembly_and_render_counts(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["counts"] == {
        "product_instances": 2,
        "assembly_instances": 2,
        "render_files": 1,
    }
    assert json.loads((fixture["run_dir"] / "PHOTO3D_REPORT.json").read_text(encoding="utf-8"))[
        "counts"
    ] == report["counts"]


def test_missing_required_contract_hash_blocks_photo3d(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    signature = fixture["payloads"]["assembly_signature"]
    del signature["model_contract_hash"]
    _write_json(fixture["paths"]["assembly_signature"], signature)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert "assembly_signature_model_contract_hash_missing" in {
        reason["code"] for reason in report["blocking_reasons"]
    }


def test_missing_path_context_hash_blocks_photo3d(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    for key, payload in fixture["payloads"].items():
        payload.pop("path_context_hash", None)
        _write_json(fixture["paths"][key], payload)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert "path_context_hash_missing" in {
        reason["code"] for reason in report["blocking_reasons"]
    }


def test_render_manifest_file_without_sha256_blocks_photo3d(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    manifest = fixture["payloads"]["render_manifest"]
    del manifest["files"][0]["sha256"]
    _write_json(fixture["paths"]["render_manifest"], manifest)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert "render_file_hash_missing" in {
        reason["code"] for reason in report["blocking_reasons"]
    }
