import json

from PIL import Image, ImageDraw

from tools.contract_io import file_sha256, stable_json_hash


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _render_png(path):
    image = Image.new("RGB", (320, 240), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 55, 240, 185), fill=(20, 90, 150))
    image.save(path)


def test_build_render_manifest_binds_contract_hashes_and_keeps_legacy_fields(tmp_path):
    from tools.render_qa import build_render_manifest

    project_root = tmp_path / "project"
    render_dir = project_root / "cad" / "output" / "renders" / "demo" / "RUN001"
    render_dir.mkdir(parents=True)
    png = render_dir / "V1_front.png"
    _render_png(png)

    product_graph = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "path_context_hash": "sha256:path",
        "parts": [],
        "instances": [],
    }
    model_contract = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "path_context_hash": "sha256:path",
        "product_graph_hash": stable_json_hash(product_graph),
    }
    assembly_signature = {
        "schema_version": 1,
        "run_id": "RUN001",
        "subsystem": "demo",
        "path_context_hash": "sha256:path",
        "product_graph_hash": stable_json_hash(product_graph),
        "instances": [],
    }
    render_config = {
        "camera": {"V1": {"type": "standard", "azimuth_deg": 35}},
        "materials": {"body": {"preset": "brushed_metal"}},
    }
    product_graph_path = project_root / "cad" / "demo" / "PRODUCT_GRAPH.json"
    model_contract_path = project_root / "cad" / "demo" / "MODEL_CONTRACT.json"
    assembly_signature_path = project_root / "cad" / "demo" / "ASSEMBLY_SIGNATURE.json"
    render_config_path = project_root / "cad" / "demo" / "render_config.json"
    glb_path = project_root / "cad" / "output" / "demo_assembly.glb"
    render_script_path = project_root / "cad" / "demo" / "render_3d.py"
    _write_json(product_graph_path, product_graph)
    _write_json(model_contract_path, model_contract)
    _write_json(assembly_signature_path, assembly_signature)
    _write_json(render_config_path, render_config)
    glb_path.write_bytes(b"glb")
    render_script_path.write_text("# render\n", encoding="utf-8")

    manifest = build_render_manifest(
        project_root,
        render_dir,
        [png],
        subsystem="demo",
        run_id="RUN001",
        path_context_hash="sha256:path",
        product_graph=product_graph_path,
        model_contract=model_contract_path,
        assembly_signature=assembly_signature_path,
        render_config_path=render_config_path,
        glb_path=glb_path,
        render_script_path=render_script_path,
    )

    assert manifest["schema_version"] == 2
    assert manifest["run_id"] == "RUN001"
    assert manifest["subsystem"] == "demo"
    assert manifest["path_context_hash"] == "sha256:path"
    assert manifest["render_dir_rel_project"] == "cad/output/renders/demo/RUN001"
    assert manifest["render_dir"] == str(render_dir.resolve())
    assert manifest["product_graph_hash"] == stable_json_hash(product_graph)
    assert manifest["model_contract_hash"] == stable_json_hash(model_contract)
    assert manifest["assembly_signature_hash"] == stable_json_hash(assembly_signature)
    assert manifest["assembly_signature_path"] == "cad/demo/ASSEMBLY_SIGNATURE.json"
    assert manifest["render_config_hash"] == file_sha256(render_config_path)
    assert manifest["camera_hash"] == stable_json_hash(render_config["camera"])
    assert manifest["material_config_hash"] == stable_json_hash(render_config["materials"])
    assert manifest["glb_hash"] == file_sha256(glb_path)
    assert manifest["render_script_hash"] == file_sha256(render_script_path)

    assert len(manifest["files"]) == 1
    file_entry = manifest["files"][0]
    assert file_entry["view"] == "V1"
    assert file_entry["path_rel_project"] == "cad/output/renders/demo/RUN001/V1_front.png"
    assert file_entry["path_abs_resolved"] == str(png.resolve())
    assert file_entry["sha256"] == file_sha256(png)
    assert file_entry["width"] == 320
    assert file_entry["height"] == 240
    assert file_entry["qa"]["passed"] is True
    assert file_entry["qa"]["nonblank"] is True


def test_write_render_manifest_writes_manifest_json_atomically(tmp_path):
    from tools.render_qa import write_render_manifest

    project_root = tmp_path / "project"
    render_dir = project_root / "cad" / "output" / "renders"
    render_dir.mkdir(parents=True)
    png = render_dir / "V2_side.png"
    _render_png(png)

    manifest_path = write_render_manifest(
        project_root,
        render_dir,
        [png],
        subsystem="demo",
        run_id="RUN002",
        path_context_hash="sha256:path2",
    )

    assert manifest_path == render_dir / "render_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["files"][0]["path_abs_resolved"] == str(png.resolve())


def test_build_render_manifest_marks_manifest_blocked_when_image_qa_fails(tmp_path):
    from tools.render_qa import build_render_manifest

    project_root = tmp_path / "project"
    render_dir = project_root / "cad" / "output" / "renders"
    render_dir.mkdir(parents=True)
    png = render_dir / "V1_blank.png"
    Image.new("RGB", (256, 256), (255, 255, 255)).save(png)

    manifest = build_render_manifest(
        project_root,
        render_dir,
        [png],
        subsystem="demo",
        run_id="RUN003",
        path_context_hash="sha256:path3",
    )

    assert manifest["status"] == "blocked"
    assert manifest["files"][0]["qa"]["passed"] is False
    assert manifest["blocking_reasons"][0]["code"] == "render_qa_failed"


def test_manifest_image_paths_rejects_project_external_absolute_paths(tmp_path):
    from tools.render_qa import manifest_image_paths

    project_root = tmp_path / "project"
    render_dir = project_root / "cad" / "output" / "renders"
    outside = tmp_path / "old_project" / "V1_old.png"
    render_dir.mkdir(parents=True)
    outside.parent.mkdir()
    outside.write_bytes(b"old")

    manifest = {
        "render_dir": str(render_dir),
        "files": [{"path_abs_resolved": str(outside), "path_rel_project": "cad/output/renders/V1_old.png"}],
    }

    try:
        manifest_image_paths(manifest, project_root=project_root)
    except ValueError as exc:
        assert "outside project" in str(exc)
    else:
        raise AssertionError("manifest absolute paths outside project must be rejected")


def test_manifest_image_paths_resolves_relative_project_paths_from_project_root(tmp_path):
    from tools.render_qa import manifest_image_paths

    project_root = tmp_path / "project"
    png = project_root / "cad" / "output" / "renders" / "V1.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"png")
    manifest = {
        "render_dir": str(png.parent),
        "files": [{"path_rel_project": "cad/output/renders/V1.png"}],
    }

    assert manifest_image_paths(manifest, project_root=project_root) == [str(png.resolve())]
