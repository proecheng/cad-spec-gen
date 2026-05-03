import json

from PIL import Image, ImageDraw

from tools.artifact_index import build_artifact_index, register_run_artifacts
from tools.contract_io import stable_json_hash
from tools.render_qa import build_render_manifest


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (320, 240), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 55, 240, 185), fill=(20, 90, 150))
    image.save(path)


def _contracts(project_root, *, run_id="RUN001", subsystem="demo", hero_quality="B"):
    run_dir = project_root / "cad" / subsystem / ".cad-spec-gen" / "runs" / run_id
    render_dir = project_root / "cad" / "output" / "renders" / subsystem / run_id
    png = render_dir / "V1_front.png"
    _render_png(png)

    product_graph = {
        "schema_version": 1,
        "run_id": run_id,
        "subsystem": subsystem,
        "path_context_hash": "sha256:pathctx",
        "parts": [
            {
                "part_no": "P-100-01",
                "name_cn": "主体件",
                "required": True,
                "render_policy": "required",
                "visual_priority": "hero",
                "quantity": 1,
            },
            {
                "part_no": "P-100-02",
                "name_cn": "附件",
                "required": True,
                "render_policy": "required",
                "visual_priority": "high",
                "quantity": 1,
            },
        ],
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
                "visual_priority": "high",
            },
        ],
        "counts_by_part_no": {"P-100-01": 1, "P-100-02": 1},
    }
    model_contract = {
        "schema_version": 1,
        "run_id": run_id,
        "subsystem": subsystem,
        "path_context_hash": "sha256:pathctx",
        "product_graph_hash": stable_json_hash(product_graph),
        "coverage": {"required_total": 2, "decided_total": 2, "missing_total": 0},
        "decisions": [
            {
                "part_no": "P-100-01",
                "visual_priority": "hero",
                "render_policy": "required",
                "geometry_quality": hero_quality,
                "geometry_source": "PARAMETRIC_TEMPLATE",
                "validated": True,
            },
            {
                "part_no": "P-100-02",
                "visual_priority": "high",
                "render_policy": "required",
                "geometry_quality": "C",
                "geometry_source": "PARAMETRIC_TEMPLATE",
                "validated": True,
            },
        ],
    }
    assembly_signature = {
        "schema_version": 1,
        "run_id": run_id,
        "subsystem": subsystem,
        "path_context_hash": "sha256:pathctx",
        "source_mode": "runtime",
        "product_graph_hash": stable_json_hash(product_graph),
        "model_contract_hash": stable_json_hash(model_contract),
        "coverage": {
            "required_total": 2,
            "matched_total": 2,
            "unmatched_object_total": 0,
            "missing_instance_total": 0,
        },
        "instances": [
            {
                "instance_id": "P-100-01#01",
                "part_no": "P-100-01",
                "bbox_mm": [0, 0, 0, 100, 80, 20],
                "center_mm": [50, 40, 10],
                "size_mm": [100, 80, 20],
                "transform": {"translation_mm": [50, 40, 10], "rotation_deg": [0, 0, 0]},
            },
            {
                "instance_id": "P-100-02#01",
                "part_no": "P-100-02",
                "bbox_mm": [10, 0, 20, 20, 10, 120],
                "center_mm": [15, 5, 70],
                "size_mm": [10, 10, 100],
                "transform": {"translation_mm": [15, 5, 70], "rotation_deg": [0, 0, 0]},
            },
        ],
        "blocking_reasons": [],
    }
    render_manifest = build_render_manifest(
        project_root,
        render_dir,
        [png],
        subsystem=subsystem,
        run_id=run_id,
        path_context_hash="sha256:pathctx",
        product_graph=product_graph,
        model_contract=model_contract,
        assembly_signature=assembly_signature,
    )

    paths = {
        "product_graph": run_dir / "PRODUCT_GRAPH.json",
        "model_contract": run_dir / "MODEL_CONTRACT.json",
        "assembly_signature": run_dir / "ASSEMBLY_SIGNATURE.json",
        "render_manifest": render_dir / "render_manifest.json",
    }
    _write_json(paths["product_graph"], product_graph)
    _write_json(paths["model_contract"], model_contract)
    _write_json(paths["assembly_signature"], assembly_signature)
    _write_json(paths["render_manifest"], render_manifest)

    index = build_artifact_index(subsystem)
    register_run_artifacts(
        index,
        run_id,
        {
            key: value.relative_to(project_root).as_posix()
            for key, value in paths.items()
        },
    )
    index_path = project_root / "cad" / subsystem / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
    _write_json(index_path, index)
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "render_dir": render_dir,
        "index_path": index_path,
        "paths": paths,
        "payloads": {
            "product_graph": product_graph,
            "model_contract": model_contract,
            "assembly_signature": assembly_signature,
            "render_manifest": render_manifest,
        },
    }


def test_photo3d_gate_passes_current_run_contracts_and_writes_user_report(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "pass"
    assert report["enhancement_status"] == "not_run"
    assert report["blocking_reasons"] == []
    assert report["ordinary_user_message"] == "照片级 CAD 门禁通过，可以进入增强阶段。"
    written = json.loads((fixture["run_dir"] / "PHOTO3D_REPORT.json").read_text(encoding="utf-8"))
    assert written["status"] == "pass"
    assert written["artifacts"]["render_manifest"].endswith("render_manifest.json")


def test_photo3d_gate_blocks_static_preflight_signature(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    signature = fixture["payloads"]["assembly_signature"]
    signature["source_mode"] = "static_preflight"
    _write_json(fixture["paths"]["assembly_signature"], signature)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert {reason["code"] for reason in report["blocking_reasons"]} >= {
        "assembly_signature_not_runtime",
        "render_manifest_assembly_signature_hash_mismatch",
    }


def test_cmd_photo3d_runs_gate_without_render_or_enhance_side_effects(tmp_path, monkeypatch):
    import cad_pipeline
    from types import SimpleNamespace

    fixture = _contracts(tmp_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
            dry_run=False,
        )
    )

    assert rc == 0
    report = json.loads((fixture["run_dir"] / "PHOTO3D_REPORT.json").read_text(encoding="utf-8"))
    assert report["status"] == "pass"
