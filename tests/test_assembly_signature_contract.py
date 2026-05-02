import json


def _product_graph() -> dict:
    return {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "path_context_hash": "sha256:pathctx",
        "instances": [
            {
                "instance_id": "P-100-01#01",
                "part_no": "P-100-01",
                "required": True,
                "render_policy": "required",
                "visual_priority": "hero",
            },
            {
                "instance_id": "P-100-02#01",
                "part_no": "P-100-02",
                "required": True,
                "render_policy": "required",
                "visual_priority": "normal",
            },
        ],
    }


def test_runtime_signature_maps_objects_to_product_graph_instances(tmp_path):
    from tools.assembly_signature import build_assembly_signature

    product_graph_path = tmp_path / "cad" / "demo" / "PRODUCT_GRAPH.json"
    product_graph_path.parent.mkdir(parents=True)
    product_graph_path.write_text(
        json.dumps(_product_graph(), ensure_ascii=False),
        encoding="utf-8",
    )
    bboxes = {
        "P-100-01#01": (0.0, 0.0, 0.0, 100.0, 80.0, 20.0),
        "P-100-02#01": (10.0, 0.0, 20.0, 20.0, 10.0, 120.0),
    }

    signature = build_assembly_signature(tmp_path, product_graph_path, bboxes)

    assert signature["schema_version"] == 1
    assert signature["source_mode"] == "runtime"
    assert signature["run_id"] == "RUN001"
    assert signature["path_context_hash"] == "sha256:pathctx"
    assert signature["product_graph_hash"].startswith("sha256:")
    assert signature["coverage"] == {
        "required_total": 2,
        "matched_total": 2,
        "unmatched_object_total": 0,
        "missing_instance_total": 0,
        "assembly_instance_total": 0,
        "duplicate_instance_total": 0,
    }
    first = signature["instances"][0]
    assert first["instance_id"] == "P-100-01#01"
    assert first["part_no"] == "P-100-01"
    assert first["object_name"] == "P-100-01#01"
    assert first["bbox_mm"] == [0.0, 0.0, 0.0, 100.0, 80.0, 20.0]
    assert first["center_mm"] == [50.0, 40.0, 10.0]
    assert first["size_mm"] == [100.0, 80.0, 20.0]
    assert first["transform"]["translation_mm"] == [0.0, 0.0, 0.0]
    assert signature["blocking_reasons"] == []


def test_signature_blocks_unmapped_object_names(tmp_path):
    from tools.assembly_signature import build_assembly_signature

    graph = _product_graph()
    signature = build_assembly_signature(
        tmp_path,
        graph,
        {"legacy-name": (0, 0, 0, 10, 10, 10)},
    )

    assert signature["coverage"]["matched_total"] == 0
    assert signature["coverage"]["unmatched_object_total"] == 1
    assert signature["coverage"]["missing_instance_total"] == 2
    reason_codes = {reason["code"] for reason in signature["blocking_reasons"]}
    assert reason_codes == {"unmapped_assembly_object", "missing_required_instance"}


def test_signature_blocks_duplicate_instance_ids(tmp_path):
    from tools.assembly_signature import build_assembly_signature

    graph = _product_graph()
    graph["instances"].append({
        "instance_id": "P-100-02#01",
        "part_no": "P-100-03",
        "required": True,
        "render_policy": "required",
    })

    signature = build_assembly_signature(
        tmp_path,
        graph,
        {
            "P-100-01#01": (0, 0, 0, 10, 10, 10),
            "P-100-02#01": (10, 0, 0, 20, 10, 10),
        },
    )

    assert signature["coverage"]["required_total"] == 3
    assert signature["coverage"]["duplicate_instance_total"] == 1
    reason_codes = {reason["code"] for reason in signature["blocking_reasons"]}
    assert "duplicate_instance_id" in reason_codes
    assert signature["blocking_reasons"][0]["instance_id"] == "P-100-02#01"


def test_signature_does_not_require_assembly_level_instances_in_runtime_objects(tmp_path):
    from tools.assembly_signature import build_assembly_signature

    graph = _product_graph()
    graph["instances"].append({
        "instance_id": "P-100#01",
        "part_no": "P-100",
        "required": True,
        "render_policy": "required",
        "node_type": "assembly",
    })

    signature = build_assembly_signature(
        tmp_path,
        graph,
        {
            "P-100-01#01": (0, 0, 0, 10, 10, 10),
            "P-100-02#01": (10, 0, 0, 20, 10, 10),
        },
    )

    assert signature["coverage"]["required_total"] == 2
    assert signature["coverage"]["assembly_instance_total"] == 1
    assert signature["coverage"]["missing_instance_total"] == 0
    assert signature["blocking_reasons"] == []


def test_signature_infers_assembly_instances_from_parent_relationships(tmp_path):
    from tools.assembly_signature import build_assembly_signature

    graph = _product_graph()
    graph["parts"] = [
        {"part_no": "P-100", "make_buy": "总成"},
        {"part_no": "P-100-01", "parent_part_no": "P-100"},
        {"part_no": "P-100-02", "parent_part_no": "P-100"},
    ]
    graph["instances"].append({
        "instance_id": "P-100#01",
        "part_no": "P-100",
        "required": True,
        "render_policy": "required",
    })

    signature = build_assembly_signature(
        tmp_path,
        graph,
        {
            "P-100-01#01": (0, 0, 0, 10, 10, 10),
            "P-100-02#01": (10, 0, 0, 20, 10, 10),
        },
    )

    assert signature["coverage"]["required_total"] == 2
    assert signature["coverage"]["assembly_instance_total"] == 1
    assert signature["blocking_reasons"] == []


def test_static_preflight_signature_never_passes_photo_gate(tmp_path):
    from tools.assembly_signature import build_static_preflight_signature
    from tools.assembly_signature import signature_blocks_photo_gate

    signature = build_static_preflight_signature(
        tmp_path,
        _product_graph(),
        reason="runtime_not_executed",
    )

    assert signature["source_mode"] == "static_preflight"
    assert signature_blocks_photo_gate(signature)
    assert signature["blocking_reasons"] == [
        {
            "code": "static_preflight_only",
            "message": "Runtime assembly signature is required for photo3d gate.",
            "reason": "runtime_not_executed",
        }
    ]
