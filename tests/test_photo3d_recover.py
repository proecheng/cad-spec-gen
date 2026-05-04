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

