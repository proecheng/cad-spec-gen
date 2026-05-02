from tools.run_manifest import build_run_manifest, record_artifact, record_stage


def test_two_run_manifests_keep_artifact_paths_isolated():
    first = build_run_manifest(
        "run-001",
        "lift",
        "sha256:pathcontext",
        "render",
        args=["--quality", "draft"],
    )
    second = build_run_manifest("run-002", "lift", "sha256:pathcontext", "render")

    record_artifact(first, "front", "cad/output/renders/lift/run-001/front.png")
    record_artifact(second, "front", "cad/output/renders/lift/run-002/front.png")

    assert first["run_id"] == "run-001"
    assert second["run_id"] == "run-002"
    assert first["artifacts"]["front"] != second["artifacts"]["front"]
    assert first["args"] == ["--quality", "draft"]
    assert second["args"] == []


def test_record_stage_updates_stage_with_same_name_instead_of_duplicating():
    manifest = build_run_manifest("run-001", "lift", "sha256:pathcontext", "render")

    record_stage(manifest, "render", "started", progress=0)
    record_stage(manifest, "render", "passed", progress=100)

    assert manifest["stages"] == [{"name": "render", "status": "passed", "progress": 100}]
