from tests.test_change_scope_gate import _instance, _scope, _signature
from tests.test_photo3d_gate_contract import _contracts, _write_json


def test_photo3d_gate_blocks_wrong_baseline_binding(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    baseline_signature = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 100, 80, 20)),
        _instance("P-100-02#01", "P-100-02", (10, 0, 20, 20, 10, 120)),
    ], run_id="BASE001")
    current_signature = fixture["payloads"]["assembly_signature"]
    current_signature["model_contract_hash"] = fixture["payloads"]["render_manifest"]["model_contract_hash"]
    _write_json(fixture["paths"]["assembly_signature"], current_signature)
    baseline_path = fixture["run_dir"] / "BASELINE_SIGNATURE.json"
    scope_path = fixture["run_dir"] / "CHANGE_SCOPE.json"
    _write_json(baseline_path, baseline_signature)
    _write_json(
        scope_path,
        _scope(
            baseline_path_context_hash="sha256:other-project",
            baseline_product_graph_hash="sha256:other-product",
            baseline_run_id="BASE001",
        ),
    )

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        change_scope_path=scope_path,
        baseline_signature_path=baseline_path,
    )

    assert report["status"] == "blocked"
    assert {reason["code"] for reason in report["blocking_reasons"]} >= {
        "baseline_path_context_mismatch",
        "baseline_product_graph_hash_mismatch",
    }


def test_photo3d_gate_allows_first_run_without_baseline_as_warning(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    scope_path = fixture["run_dir"] / "CHANGE_SCOPE.json"
    _write_json(
        scope_path,
        _scope(baseline_run_id=""),
    )

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        change_scope_path=scope_path,
    )

    assert report["status"] == "warning"
    assert report["warnings"][0]["code"] == "no_accepted_baseline"
