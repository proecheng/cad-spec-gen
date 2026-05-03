import json

import pytest

from tools.artifact_index import build_artifact_index, register_run_artifacts

from tests.test_photo3d_gate_contract import _contracts, _write_json


def test_photo3d_gate_reads_only_active_run_from_artifact_index(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    old = _contracts(tmp_path, run_id="OLD_RUN")
    current = _contracts(tmp_path, run_id="RUN001")
    index = build_artifact_index("demo")
    register_run_artifacts(
        index,
        "OLD_RUN",
        {
            key: value.relative_to(tmp_path).as_posix()
            for key, value in old["paths"].items()
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
    _write_json(current["index_path"], index)
    old_signature = old["payloads"]["assembly_signature"]
    old_signature["source_mode"] = "static_preflight"
    _write_json(old["paths"]["assembly_signature"], old_signature)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=current["index_path"],
    )

    assert report["status"] == "pass"
    assert report["run_id"] == "RUN001"


def test_photo3d_gate_rejects_artifact_path_outside_project(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    outside = tmp_path.parent / "other_project" / "PRODUCT_GRAPH.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("{}", encoding="utf-8")
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    index["runs"]["RUN001"]["artifacts"]["product_graph"] = str(outside)
    _write_json(fixture["index_path"], index)

    with pytest.raises(ValueError, match="within project"):
        run_photo3d_gate(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
        )


def test_photo3d_gate_blocks_wrong_subsystem_contract(tmp_path):
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    graph = fixture["payloads"]["product_graph"]
    graph["subsystem"] = "other_demo"
    _write_json(fixture["paths"]["product_graph"], graph)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "subsystem_mismatch"


def test_photo3d_gate_blocks_render_file_hash_drift_after_manifest(tmp_path):
    from PIL import Image
    from tools.photo3d_gate import run_photo3d_gate

    fixture = _contracts(tmp_path)
    render_file = fixture["render_dir"] / "V1_front.png"
    Image.new("RGB", (320, 240), (10, 10, 10)).save(render_file)

    report = run_photo3d_gate(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "render_file_hash_mismatch"
