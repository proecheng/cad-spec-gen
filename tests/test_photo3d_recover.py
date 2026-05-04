import json
from types import SimpleNamespace

from tests.test_photo3d_gate_contract import _contracts, _write_json


def _recover_args(fixture, *, action="product-graph", run_id="RUN001"):
    return SimpleNamespace(
        subsystem="demo",
        run_id=run_id,
        artifact_index=str(fixture["index_path"]),
        action=action,
    )


def test_photo3d_recover_product_graph_writes_current_run_artifact_and_updates_index(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    _write_json(fixture["paths"]["product_graph"], {"stale": True})
    (tmp_path / "cad" / "demo" / "CAD_SPEC.md").write_text(
        "\n".join(
            [
                "# demo",
                "",
                "## 5. BOM",
                "",
                "| 料号 | 名称 | 材质 | 数量 | 自制/外购 |",
                "| --- | --- | --- | --- | --- |",
                "| P-100-01 | 主体件 | Al6061 | 1 | 自制 |",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_recover(_recover_args(fixture))

    assert rc == 0
    product_graph = json.loads(fixture["paths"]["product_graph"].read_text(encoding="utf-8"))
    assert product_graph["run_id"] == "RUN001"
    assert product_graph["subsystem"] == "demo"
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["active_run_id"] == "RUN001"
    assert index["runs"]["RUN001"]["active"] is True
    assert (
        index["runs"]["RUN001"]["artifacts"]["product_graph"]
        == "cad/demo/.cad-spec-gen/runs/RUN001/PRODUCT_GRAPH.json"
    )


def test_photo3d_recover_rejects_non_active_run_id(tmp_path, monkeypatch):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_recover(_recover_args(fixture, run_id="RUN002"))

    assert rc == 1
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert index["active_run_id"] == "RUN001"


def test_photo3d_recover_render_stages_current_run_contracts_for_legacy_render_inputs(
    tmp_path,
):
    from tools.photo3d_recover import run_photo3d_recover

    fixture = _contracts(tmp_path)
    stale = {
        "schema_version": 1,
        "run_id": "OLD",
        "subsystem": "demo",
        "path_context_hash": "sha256:old",
    }
    _write_json(tmp_path / "cad" / "demo" / "PRODUCT_GRAPH.json", stale)
    _write_json(tmp_path / "cad" / "demo" / ".cad-spec-gen" / "MODEL_CONTRACT.json", stale)
    _write_json(tmp_path / "cad" / "output" / "runs" / "RUN001" / "ASSEMBLY_SIGNATURE.json", stale)
    calls = []

    def fake_render(args):
        calls.append(args)
        staged_graph = json.loads((tmp_path / "cad" / "demo" / "PRODUCT_GRAPH.json").read_text(encoding="utf-8"))
        staged_model = json.loads(
            (tmp_path / "cad" / "demo" / ".cad-spec-gen" / "MODEL_CONTRACT.json").read_text(encoding="utf-8")
        )
        staged_signature = json.loads(
            (tmp_path / "cad" / "output" / "runs" / "RUN001" / "ASSEMBLY_SIGNATURE.json").read_text(encoding="utf-8")
        )
        assert staged_graph == fixture["payloads"]["product_graph"]
        assert staged_model == fixture["payloads"]["model_contract"]
        assert staged_signature == fixture["payloads"]["assembly_signature"]
        manifest = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001" / "render_manifest.json"
        _write_json(manifest, {"schema_version": 2, "run_id": "RUN001", "subsystem": "demo"})
        return 0

    report = run_photo3d_recover(
        tmp_path,
        "demo",
        "RUN001",
        artifact_index_path=fixture["index_path"],
        action="render",
        render_runner=fake_render,
    )

    assert report["returncode"] == 0
    assert len(calls) == 1
    assert calls[0].run_id == "RUN001"
    assert calls[0].output_dir == str(tmp_path / "cad" / "output" / "renders" / "demo" / "RUN001")
    assert calls[0].path_context_hash == "sha256:pathctx"
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    assert (
        index["runs"]["RUN001"]["artifacts"]["render_manifest"]
        == "cad/output/renders/demo/RUN001/render_manifest.json"
    )


def test_photo3d_recover_build_fails_when_runtime_signature_is_not_produced(tmp_path):
    from tools.photo3d_recover import run_photo3d_recover

    fixture = _contracts(tmp_path)
    (tmp_path / "cad" / "output" / "runs" / "RUN001" / "ASSEMBLY_SIGNATURE.json").unlink(missing_ok=True)

    report = run_photo3d_recover(
        tmp_path,
        "demo",
        "RUN001",
        artifact_index_path=fixture["index_path"],
        action="build",
        build_runner=lambda args: 0,
    )

    assert report["returncode"] == 1


def test_photo3d_recover_build_backfills_current_run_build_artifacts(tmp_path):
    from tools.photo3d_recover import run_photo3d_recover

    fixture = _contracts(tmp_path)
    output_dir = tmp_path / "cad" / "output"
    run_output_dir = output_dir / "runs" / "RUN001"
    _write_json(run_output_dir / "ASSEMBLY_SIGNATURE.json", {"schema_version": 1, "source_mode": "runtime"})
    _write_json(run_output_dir / "ASSEMBLY_REPORT.json", {"summary": "0 WARNING"})
    _write_json(
        tmp_path / "cad" / "demo" / ".cad-spec-gen" / "MODEL_CONTRACT.json",
        {"schema_version": 1, "refreshed": True},
    )
    (tmp_path / "cad" / "demo" / "render_config.json").write_text(
        json.dumps({"subsystem": {"glb_file": "DEMO-000_assembly.glb"}}),
        encoding="utf-8",
    )
    (output_dir / "DEMO-000_assembly.glb").write_bytes(b"glb")
    (output_dir / "DEMO-000_assembly.step").write_text("STEP", encoding="utf-8")

    report = run_photo3d_recover(
        tmp_path,
        "demo",
        "RUN001",
        artifact_index_path=fixture["index_path"],
        action="build",
        build_runner=lambda args: 0,
    )

    assert report["returncode"] == 0
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    artifacts = index["runs"]["RUN001"]["artifacts"]
    assert artifacts["assembly_signature"] == "cad/demo/.cad-spec-gen/runs/RUN001/ASSEMBLY_SIGNATURE.json"
    assert artifacts["assembly_report"] == "cad/demo/.cad-spec-gen/runs/RUN001/ASSEMBLY_REPORT.json"
    assert artifacts["model_contract"] == "cad/demo/.cad-spec-gen/runs/RUN001/MODEL_CONTRACT.json"
    assert artifacts["assembly_glb"] == "cad/demo/.cad-spec-gen/runs/RUN001/DEMO-000_assembly.glb"
    assert artifacts["assembly_step"] == "cad/demo/.cad-spec-gen/runs/RUN001/DEMO-000_assembly.step"
    assert (fixture["run_dir"] / "ASSEMBLY_REPORT.json").is_file()
    assert (fixture["run_dir"] / "MODEL_CONTRACT.json").is_file()
    assert (fixture["run_dir"] / "DEMO-000_assembly.glb").read_bytes() == b"glb"
    assert (fixture["run_dir"] / "DEMO-000_assembly.step").read_text(encoding="utf-8") == "STEP"


def test_photo3d_recover_build_does_not_guess_ambiguous_assembly_deliverables(tmp_path):
    from tools.photo3d_recover import run_photo3d_recover

    fixture = _contracts(tmp_path)
    output_dir = tmp_path / "cad" / "output"
    run_output_dir = output_dir / "runs" / "RUN001"
    _write_json(run_output_dir / "ASSEMBLY_SIGNATURE.json", {"schema_version": 1, "source_mode": "runtime"})
    (output_dir / "A-000_assembly.glb").write_bytes(b"a")
    (output_dir / "B-000_assembly.glb").write_bytes(b"b")
    (output_dir / "A-000_assembly.step").write_text("A", encoding="utf-8")
    (output_dir / "B-000_assembly.step").write_text("B", encoding="utf-8")

    report = run_photo3d_recover(
        tmp_path,
        "demo",
        "RUN001",
        artifact_index_path=fixture["index_path"],
        action="build",
        build_runner=lambda args: 0,
    )

    assert report["returncode"] == 0
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    artifacts = index["runs"]["RUN001"]["artifacts"]
    assert "assembly_glb" not in artifacts
    assert "assembly_step" not in artifacts


def test_photo3d_recover_build_accepts_configured_output_relative_glb_path(tmp_path):
    from tools.photo3d_recover import run_photo3d_recover

    fixture = _contracts(tmp_path)
    output_dir = tmp_path / "cad" / "output"
    run_output_dir = output_dir / "runs" / "RUN001"
    _write_json(run_output_dir / "ASSEMBLY_SIGNATURE.json", {"schema_version": 1, "source_mode": "runtime"})
    (tmp_path / "cad" / "demo" / "render_config.json").write_text(
        json.dumps({"subsystem": {"glb_file": "assemblies/DEMO-000_assembly.glb"}}),
        encoding="utf-8",
    )
    (output_dir / "assemblies").mkdir()
    (output_dir / "assemblies" / "DEMO-000_assembly.glb").write_bytes(b"nested glb")
    (output_dir / "assemblies" / "DEMO-000_assembly.step").write_text("nested STEP", encoding="utf-8")
    (output_dir / "OTHER-000_assembly.glb").write_bytes(b"other")

    report = run_photo3d_recover(
        tmp_path,
        "demo",
        "RUN001",
        artifact_index_path=fixture["index_path"],
        action="build",
        build_runner=lambda args: 0,
    )

    assert report["returncode"] == 0
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    artifacts = index["runs"]["RUN001"]["artifacts"]
    assert artifacts["assembly_glb"] == "cad/demo/.cad-spec-gen/runs/RUN001/DEMO-000_assembly.glb"
    assert artifacts["assembly_step"] == "cad/demo/.cad-spec-gen/runs/RUN001/DEMO-000_assembly.step"
    assert (fixture["run_dir"] / "DEMO-000_assembly.glb").read_bytes() == b"nested glb"

