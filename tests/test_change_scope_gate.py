from tools.contract_io import stable_json_hash


def _instance(
    instance_id: str,
    part_no: str,
    bbox: tuple[float, float, float, float, float, float],
    *,
    rotation_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict:
    center = [
        (bbox[0] + bbox[3]) / 2,
        (bbox[1] + bbox[4]) / 2,
        (bbox[2] + bbox[5]) / 2,
    ]
    size = [
        bbox[3] - bbox[0],
        bbox[4] - bbox[1],
        bbox[5] - bbox[2],
    ]
    return {
        "instance_id": instance_id,
        "part_no": part_no,
        "bbox_mm": list(bbox),
        "center_mm": center,
        "size_mm": size,
        "transform": {
            "translation_mm": center,
            "rotation_deg": list(rotation_deg),
            "matrix": None,
        },
    }


def _signature(instances: list[dict], *, run_id: str = "RUN001") -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "subsystem": "demo",
        "path_context_hash": "sha256:pathctx",
        "product_graph_hash": "sha256:product",
        "source_mode": "runtime",
        "coverage": {
            "required_total": len(instances),
            "matched_total": len(instances),
            "unmatched_object_total": 0,
            "missing_instance_total": 0,
        },
        "instances": instances,
        "blocking_reasons": [],
    }


def _scope(**overrides) -> dict:
    scope = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "path_context_hash": "sha256:pathctx",
        "baseline_run_id": "BASE001",
        "allowed_part_nos": [],
        "allowed_instance_ids": [],
        "allowed_change_types": ["material_refinement"],
        "tolerances": {
            "bbox_size_abs_mm": 1.0,
            "bbox_size_rel": 0.03,
            "center_abs_mm": 1.0,
            "center_rel_of_assembly_diag": 0.01,
            "rotation_deg": 1.0,
        },
    }
    scope.update(overrides)
    return scope


def test_unapproved_instance_move_over_threshold_blocks():
    from tools.change_scope import evaluate_change_scope

    baseline = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ], run_id="BASE001")
    current = _signature([
        _instance("P-100-01#01", "P-100-01", (5, 0, 0, 15, 10, 10)),
    ])

    report = evaluate_change_scope(
        _scope(),
        current_signature=current,
        baseline_signature=baseline,
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "unexpected_center_drift"
    drift = report["drift_items"][0]
    assert drift["instance_id"] == "P-100-01#01"
    assert drift["actual_delta"] == [5.0, 0.0, 0.0]
    assert drift["threshold"] == [1.0, 1.0, 1.0]
    assert drift["allowed"] is False


def test_authorized_geometry_refinement_does_not_allow_count_change():
    from tools.change_scope import evaluate_change_scope

    baseline = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
        _instance("P-100-02#01", "P-100-02", (20, 0, 0, 30, 10, 10)),
    ], run_id="BASE001")
    current = _signature([
        _instance("P-100-01#01", "P-100-01", (-1, 0, 0, 11, 10, 10)),
        _instance("P-100-02#01", "P-100-02", (20, 0, 0, 30, 10, 10)),
        _instance("P-100-02#02", "P-100-02", (40, 0, 0, 50, 10, 10)),
    ])

    report = evaluate_change_scope(
        _scope(
            allowed_instance_ids=["P-100-01#01"],
            allowed_change_types=["geometry_refinement", "material_refinement"],
        ),
        current_signature=current,
        baseline_signature=baseline,
    )

    assert report["status"] == "blocked"
    bbox_drift = next(item for item in report["drift_items"] if item["code"] == "unexpected_bbox_size_drift")
    assert bbox_drift["instance_id"] == "P-100-01#01"
    assert bbox_drift["allowed"] is True
    count_drift = next(item for item in report["drift_items"] if item["code"] == "unexpected_count_change")
    assert count_drift["part_no"] == "P-100-02"
    assert count_drift["allowed"] is False
    assert {reason["code"] for reason in report["blocking_reasons"]} == {"unexpected_count_change"}


def test_first_run_without_baseline_warns_but_does_not_fake_drift_pass():
    from tools.change_scope import evaluate_change_scope

    current = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ])

    report = evaluate_change_scope(
        _scope(baseline_run_id=""),
        current_signature=current,
        baseline_signature=None,
    )

    assert report["status"] == "warning"
    assert report["baseline_status"] == "candidate_only"
    assert report["drift_items"] == []
    assert report["blocking_reasons"] == []
    assert report["warnings"] == [{
        "code": "no_accepted_baseline",
        "message": "首轮运行没有已接受基准，只能建立候选基准，不能证明漂移稳定。",
    }]


def test_baseline_binding_mismatch_blocks_before_drift_comparison():
    from tools.change_scope import evaluate_change_scope

    baseline = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ], run_id="BASE001")
    current = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ])
    baseline_model_contract = {
        "schema_version": 1,
        "path_context_hash": "sha256:pathctx",
        "product_graph_hash": "sha256:product",
    }

    report = evaluate_change_scope(
        _scope(
            baseline_path_context_hash="sha256:other-project",
            baseline_product_graph_hash="sha256:other-product",
            baseline_model_contract_hash="sha256:other-model",
            baseline_assembly_signature_hash="sha256:other-signature",
        ),
        current_signature=current,
        baseline_signature=baseline,
        baseline_model_contract=baseline_model_contract,
    )

    assert report["status"] == "blocked"
    assert report["drift_items"] == []
    assert {reason["code"] for reason in report["blocking_reasons"]} == {
        "baseline_path_context_mismatch",
        "baseline_product_graph_hash_mismatch",
        "baseline_model_contract_hash_mismatch",
        "baseline_assembly_signature_hash_mismatch",
    }
    assert report["observed_hashes"]["baseline_model_contract_hash"] == stable_json_hash(
        baseline_model_contract
    )


def test_scope_must_match_current_signature_path_context():
    from tools.change_scope import evaluate_change_scope

    baseline = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ], run_id="BASE001")
    current = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ])
    current["path_context_hash"] = "sha256:other-current"

    report = evaluate_change_scope(
        _scope(),
        current_signature=current,
        baseline_signature=baseline,
    )

    assert report["status"] == "blocked"
    assert report["drift_items"] == []
    assert report["blocking_reasons"] == [{
        "code": "current_path_context_mismatch",
        "expected": "sha256:pathctx",
        "actual": "sha256:other-current",
        "message": "当前契约与 CHANGE_SCOPE.json 不属于同一路径上下文。",
    }]


def test_baseline_run_id_mismatch_blocks_even_without_hash_fields():
    from tools.change_scope import evaluate_change_scope

    baseline = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ], run_id="OTHER_BASE")
    current = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ])

    report = evaluate_change_scope(
        _scope(baseline_run_id="BASE001"),
        current_signature=current,
        baseline_signature=baseline,
    )

    assert report["status"] == "blocked"
    assert report["drift_items"] == []
    assert report["blocking_reasons"] == [{
        "code": "baseline_run_id_mismatch",
        "expected": "BASE001",
        "actual": "OTHER_BASE",
        "message": "基准契约绑定不匹配，不能用于本轮漂移比较。",
    }]


def test_current_model_contract_mismatch_blocks_before_drift_comparison():
    from tools.change_scope import evaluate_change_scope

    baseline = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ], run_id="BASE001")
    current = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10)),
    ])
    current_model_contract = {
        "schema_version": 1,
        "path_context_hash": "sha256:pathctx",
        "product_graph_hash": "sha256:other-product",
    }

    report = evaluate_change_scope(
        _scope(),
        current_signature=current,
        baseline_signature=baseline,
        current_model_contract=current_model_contract,
    )

    assert report["status"] == "blocked"
    assert report["drift_items"] == []
    assert report["blocking_reasons"] == [{
        "code": "current_model_product_graph_mismatch",
        "expected": "sha256:product",
        "actual": "sha256:other-product",
        "message": "当前模型契约与当前装配签名不属于同一产品图。",
    }]


def test_rotation_delta_uses_shortest_angle_across_wrap_boundary():
    from tools.change_scope import evaluate_change_scope

    baseline = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10), rotation_deg=(359, 0, 0)),
    ], run_id="BASE001")
    current = _signature([
        _instance("P-100-01#01", "P-100-01", (0, 0, 0, 10, 10, 10), rotation_deg=(0, 0, 0)),
    ])

    report = evaluate_change_scope(
        _scope(),
        current_signature=current,
        baseline_signature=baseline,
    )

    assert report["status"] == "pass"
    assert [
        item for item in report["drift_items"]
        if item["code"] == "unexpected_transform_drift"
    ] == []
