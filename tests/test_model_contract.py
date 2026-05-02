import json

import pytest


def _graph(parts: list[dict], *, run_id: str = "RUN001") -> dict:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "subsystem": "demo_device",
        "path_context_hash": "sha256:pathctx",
        "parts": parts,
    }


def _part(part_no: str, *, visual_priority: str = "normal", render_policy: str = "required") -> dict:
    return {
        "part_no": part_no,
        "name_cn": part_no,
        "render_policy": render_policy,
        "visual_priority": visual_priority,
        "bbox_expected_mm": [1.0, 2.0, 3.0],
    }


def test_contract_has_one_decision_for_each_renderable_part(tmp_path):
    from tools.model_contract import build_model_contract

    project_root = tmp_path / "project"
    project_root.mkdir()
    step_file = project_root / "std_parts" / "bearing.step"
    step_file.parent.mkdir()
    step_file.write_text("ISO-10303-21;\n", encoding="utf-8")
    product_graph = _graph([
        _part("P-001", visual_priority="hero"),
        _part("P-002"),
        _part("P-003"),
        _part("P-999", render_policy="excluded"),
    ])
    decisions = [
        {
            "part_no": "P-001",
            "adapter": "step_pool",
            "geometry_source": "USER_STEP",
            "geometry_quality": "A",
            "validated": True,
            "requires_model_review": False,
            "step_path": "std_parts/bearing.step",
            "real_dims": [9, 8, 7],
            "hash": "sha256:abc",
        },
        {
            "part_no": "P-002",
            "adapter": "jinja_primitive",
            "geometry_source": "JINJA_PRIMITIVE",
            "geometry_quality": "D",
            "validated": False,
            "requires_model_review": True,
        },
        {
            "part_no": "P-003",
            "adapter": "partcad",
            "geometry_source": "PARTCAD",
            "geometry_quality": "B",
            "validated": True,
            "requires_model_review": False,
        },
    ]

    contract = build_model_contract(project_root, product_graph, resolver_decisions=decisions)

    assert [row["part_no"] for row in contract["decisions"]] == ["P-001", "P-002", "P-003"]
    assert contract["coverage"] == {
        "required_total": 3,
        "decided_total": 3,
        "missing_total": 0,
    }
    assert contract["quality_counts"] == {"A": 1, "B": 1, "C": 0, "D": 1, "E": 0}
    step_decision = contract["decisions"][0]
    assert step_decision["source_path_rel_project"] == "std_parts/bearing.step"
    assert step_decision["source_path_abs_resolved"] == str(step_file.resolve())
    assert step_decision["dimensional_confidence"] == "high"
    assert step_decision["visual_confidence"] == "high"
    fallback_decision = contract["decisions"][1]
    assert fallback_decision["dimensional_confidence"] == "low"
    assert fallback_decision["visual_confidence"] == "low"
    assert contract["run_id"] == "RUN001"
    assert contract["subsystem"] == "demo_device"
    assert contract["path_context_hash"] == "sha256:pathctx"
    assert contract["product_graph_hash"].startswith("sha256:")


def test_missing_model_is_e_quality_decision_not_silent_skip(tmp_path):
    from tools.model_contract import build_model_contract

    contract = build_model_contract(
        tmp_path,
        _graph([_part("P-001"), _part("P-002")]),
        resolver_decisions=[
            {
                "part_no": "P-001",
                "adapter": "step_pool",
                "geometry_source": "USER_STEP",
                "geometry_quality": "A",
                "validated": True,
                "requires_model_review": False,
            }
        ],
    )

    missing = next(row for row in contract["decisions"] if row["part_no"] == "P-002")
    assert missing["adapter"] == "(none)"
    assert missing["geometry_source"] == "MISSING"
    assert missing["geometry_quality"] == "E"
    assert missing["validated"] is False
    assert missing["requires_model_review"] is True
    assert missing["dimensional_confidence"] == "none"
    assert missing["visual_confidence"] == "none"
    assert "missing_geometry_decision" in missing["review_reasons"]
    assert contract["coverage"]["missing_total"] == 1


def test_d_or_e_quality_blocks_photo_gate_for_hero_and_high_parts(tmp_path):
    from tools.model_contract import blocked_required_decisions
    from tools.model_contract import build_model_contract

    contract = build_model_contract(
        tmp_path,
        _graph([
            _part("H-001", visual_priority="hero"),
            _part("N-001", visual_priority="normal"),
            _part("HIGH-001", visual_priority="high"),
        ]),
        resolver_decisions=[
            {"part_no": "H-001", "geometry_quality": "D", "adapter": "jinja_primitive"},
            {"part_no": "N-001", "geometry_quality": "D", "adapter": "jinja_primitive"},
        ],
    )

    blocked = blocked_required_decisions(contract)

    assert [row["part_no"] for row in blocked] == ["H-001", "HIGH-001"]


def test_outside_project_step_path_is_downgraded_without_leaking_absolute_path(tmp_path):
    from tools.model_contract import build_model_contract

    project_root = tmp_path / "project"
    project_root.mkdir()
    outside_step = tmp_path / "outside" / "bad.step"
    outside_step.parent.mkdir()
    outside_step.write_text("ISO-10303-21;\n", encoding="utf-8")

    contract = build_model_contract(
        project_root,
        _graph([_part("P-001", visual_priority="hero")]),
        resolver_decisions=[
            {
                "part_no": "P-001",
                "adapter": "step_pool",
                "geometry_source": "USER_STEP",
                "geometry_quality": "A",
                "validated": True,
                "requires_model_review": False,
                "step_path": str(outside_step),
            }
        ],
    )

    decision = contract["decisions"][0]
    assert decision["geometry_quality"] == "E"
    assert decision["validated"] is False
    assert decision["requires_model_review"] is True
    assert "outside_project_step" in decision["review_reasons"]
    assert decision["source_path_rel_project"] is None
    assert decision["source_path_abs_resolved"] is None
    assert str(outside_step) not in json.dumps(contract, ensure_ascii=False)


def test_cache_uri_step_is_downgraded_until_imported_into_project(tmp_path):
    from tools.model_contract import build_model_contract

    contract = build_model_contract(
        tmp_path,
        _graph([_part("P-001", visual_priority="hero")]),
        resolver_decisions=[
            {
                "part_no": "P-001",
                "adapter": "step_pool",
                "geometry_source": "USER_STEP",
                "geometry_quality": "A",
                "validated": True,
                "requires_model_review": False,
                "step_path": "cache://vendor/foo.step",
            }
        ],
    )

    decision = contract["decisions"][0]
    assert decision["geometry_quality"] == "E"
    assert decision["validated"] is False
    assert decision["requires_model_review"] is True
    assert "cache_uri_requires_project_import" in decision["review_reasons"]
    assert decision["source_path_rel_project"] is None
    assert decision["source_path_abs_resolved"] is None
    assert "cache://" not in json.dumps(contract, ensure_ascii=False)


def test_duplicate_geometry_decisions_raise_value_error(tmp_path):
    from tools.model_contract import build_model_contract

    with pytest.raises(ValueError, match="P-001"):
        build_model_contract(
            tmp_path,
            _graph([_part("P-001")]),
            resolver_decisions=[
                {"part_no": "P-001", "geometry_quality": "A"},
                {"part_no": "P-001", "geometry_quality": "B"},
            ],
        )


def test_write_model_contract_defaults_to_meta_dir(tmp_path):
    from tools.model_contract import write_model_contract

    product_graph_path = tmp_path / "cad" / "demo" / "PRODUCT_GRAPH.json"
    product_graph_path.parent.mkdir(parents=True)
    product_graph_path.write_text(
        json.dumps(_graph([_part("P-001")]), ensure_ascii=False),
        encoding="utf-8",
    )

    output = write_model_contract(tmp_path, product_graph_path)

    assert output == tmp_path / ".cad-spec-gen" / "MODEL_CONTRACT.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["subsystem"] == "demo_device"
    assert payload["source_paths"] == {
        "PRODUCT_GRAPH.json": "cad/demo/PRODUCT_GRAPH.json",
    }
    assert payload["source_hashes"]["PRODUCT_GRAPH.json"].startswith("sha256:")
    assert payload["decisions"][0]["geometry_quality"] == "E"


def test_codegen_model_contract_existing_invalid_product_graph_raises(tmp_path):
    from codegen.gen_std_parts import _write_model_contract

    class Resolver:
        def geometry_decisions(self):
            return []

    output_dir = tmp_path / "cad" / "demo"
    output_dir.mkdir(parents=True)
    (output_dir / "PRODUCT_GRAPH.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError):
        _write_model_contract(Resolver(), str(output_dir), str(tmp_path))


def test_product_graph_path_outside_project_is_rejected_before_reading(tmp_path):
    from tools.model_contract import write_model_contract

    project_root = tmp_path / "project"
    project_root.mkdir()
    outside_graph = tmp_path / "outside" / "PRODUCT_GRAPH.json"

    try:
        write_model_contract(project_root, outside_graph)
    except ValueError as exc:
        assert "product graph must be within project" in str(exc)
    else:
        raise AssertionError("outside product graph path should be rejected")
