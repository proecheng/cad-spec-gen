import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tests.test_photo3d_gate_contract import _contracts, _write_json
from tools.contract_io import file_sha256


def _rel(path: Path, project_root: Path) -> str:
    return path.relative_to(project_root).as_posix()


def _save_jpg_from_png(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.convert("RGB").save(target, "JPEG")


def _write_photo3d_run(fixture, status="enhancement_accepted"):
    _write_json(
        fixture["run_dir"] / "PHOTO3D_RUN.json",
        {
            "schema_version": 1,
            "run_id": fixture["run_id"],
            "subsystem": "demo",
            "status": status,
            "ordinary_user_message": "enhancement accepted",
            "enhancement_summary": {
                "status": "accepted",
                "delivery_status": "accepted",
                "enhancement_report": "cad/output/renders/demo/RUN001/ENHANCEMENT_REPORT.json",
            },
            "next_action": {"kind": "delivery_complete"},
            "artifacts": {
                "artifact_index": "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
                "photo3d_run": "cad/demo/.cad-spec-gen/runs/RUN001/PHOTO3D_RUN.json",
            },
        },
    )


def _write_enhancement_report(fixture, *, status="accepted"):
    project_root = fixture["run_dir"].parents[4]
    source = fixture["render_dir"] / "V1_front.png"
    enhanced = fixture["render_dir"] / "V1_front_20260505_1200_enhanced.jpg"
    labeled = fixture["render_dir"] / "V1_front_20260505_1200_enhanced_labeled_en.jpg"
    if status != "blocked":
        _save_jpg_from_png(source, enhanced)
        _save_jpg_from_png(source, labeled)

    report_path = fixture["render_dir"] / "ENHANCEMENT_REPORT.json"
    _write_json(
        report_path,
        {
            "schema_version": 1,
            "run_id": fixture["run_id"],
            "subsystem": "demo",
            "status": status,
            "delivery_status": status,
            "ordinary_user_message": f"enhancement {status}",
            "render_manifest": "cad/output/renders/demo/RUN001/render_manifest.json",
            "render_dir": "cad/output/renders/demo/RUN001",
            "enhancement_report": "cad/output/renders/demo/RUN001/ENHANCEMENT_REPORT.json",
            "view_count": 1,
            "enhanced_view_count": 1 if status != "blocked" else 0,
            "quality_summary": {
                "schema_version": 1,
                "status": "accepted" if status == "accepted" else "preview",
                "view_count": 1,
                "warnings": [],
            },
            "views": [
                {
                    "view": "V1",
                    "status": "accepted" if status == "accepted" else status,
                    "source_image": _rel(source, project_root),
                    "enhanced_image": _rel(enhanced, project_root)
                    if status != "blocked"
                    else None,
                    "source_sha256": file_sha256(source),
                    "enhanced_sha256": file_sha256(enhanced)
                    if status != "blocked"
                    else None,
                    "blocking_reasons": []
                    if status == "accepted"
                    else [{"code": f"{status}_reason"}],
                }
            ],
            "blocking_reasons": [] if status == "accepted" else [{"code": f"{status}_reason"}],
        },
    )
    return report_path


def _write_review_input(
    fixture,
    enhancement_path,
    *,
    views=None,
    checks=None,
    render_manifest_sha256=None,
):
    manifest_path = fixture["paths"]["render_manifest"]
    project_root = fixture["run_dir"].parents[4]
    semantic_checks = checks or {
        "geometry_preserved": True,
        "material_consistent": True,
        "photorealistic": True,
        "no_extra_parts": True,
        "no_missing_parts": True,
    }
    payload = {
        "schema_version": 1,
        "run_id": fixture["run_id"],
        "subsystem": "demo",
        "review_type": "human",
        "source_reports": {
            "render_manifest": _rel(manifest_path, project_root),
            "render_manifest_sha256": render_manifest_sha256 or file_sha256(manifest_path),
            "enhancement_report": _rel(enhancement_path, project_root),
            "enhancement_report_sha256": file_sha256(enhancement_path),
        },
        "views": views
        if views is not None
        else [
            {
                "view": "V1",
                "semantic_checks": semantic_checks,
                "reviewer_notes": "Looks consistent.",
            }
        ],
    }
    path = fixture["run_dir"] / "ENHANCEMENT_REVIEW_INPUT.json"
    _write_json(path, payload)
    return path


def test_enhance_review_accepts_bound_semantic_evidence(tmp_path):
    from tools.enhancement_semantic_review import write_enhancement_review_report

    fixture = _contracts(tmp_path)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(fixture, enhancement_path)

    report = write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "accepted"
    assert report["semantic_material_review"]["status"] == "accepted"
    assert report["source_reports"]["render_manifest"].endswith("render_manifest.json")
    assert report["source_reports"]["enhancement_report"].endswith(
        "ENHANCEMENT_REPORT.json"
    )
    assert report["source_reports"]["review_input"].endswith(
        "ENHANCEMENT_REVIEW_INPUT.json"
    )
    assert report["view_count"] == 1
    assert report["blocking_reasons"] == []
    assert (fixture["run_dir"] / "ENHANCEMENT_REVIEW_REPORT.json").is_file()


def test_enhance_review_blocks_source_report_hash_drift(tmp_path):
    from tools.enhancement_semantic_review import write_enhancement_review_report

    fixture = _contracts(tmp_path)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(
        fixture,
        enhancement_path,
        render_manifest_sha256="sha256:not-the-current-manifest",
    )

    report = write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["semantic_material_review"]["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "review_source_report_hash_mismatch"


def test_enhance_review_blocks_missing_view(tmp_path):
    from tools.enhancement_semantic_review import write_enhancement_review_report

    fixture = _contracts(tmp_path)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(fixture, enhancement_path, views=[])

    report = write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "review_view_missing"


def test_enhance_review_marks_failed_material_check_as_preview(tmp_path):
    from tools.enhancement_semantic_review import write_enhancement_review_report

    fixture = _contracts(tmp_path)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(
        fixture,
        enhancement_path,
        checks={
            "geometry_preserved": True,
            "material_consistent": False,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
    )

    report = write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "preview"
    assert report["semantic_material_review"]["status"] == "preview"
    assert report["views"][0]["status"] == "preview"
    assert report["warnings"][0]["code"] == "semantic_check_failed"


def test_enhance_review_marks_missing_check_as_needs_review(tmp_path):
    from tools.enhancement_semantic_review import write_enhancement_review_report

    fixture = _contracts(tmp_path)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(
        fixture,
        enhancement_path,
        checks={
            "geometry_preserved": True,
            "material_consistent": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
    )

    report = write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "needs_review"
    assert report["semantic_material_review"]["status"] == "needs_review"
    assert report["views"][0]["status"] == "needs_review"
    assert report["warnings"][0]["code"] == "semantic_check_missing"


def test_cmd_enhance_review_writes_report(tmp_path, monkeypatch):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(fixture, enhancement_path)
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_enhance_review(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            review_input=str(review_input),
            output=None,
        )
    )

    assert rc == 0
    report = json.loads(
        (fixture["run_dir"] / "ENHANCEMENT_REVIEW_REPORT.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "accepted"


def test_photo3d_delivery_pack_includes_accepted_semantic_review_evidence(tmp_path):
    from tools.enhancement_semantic_review import write_enhancement_review_report
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(fixture, enhancement_path)
    write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["final_deliverable"] is True
    assert report["semantic_material_review"]["status"] == "accepted"
    assert report["source_reports"]["enhancement_review"].endswith(
        "ENHANCEMENT_REVIEW_REPORT.json"
    )
    evidence_names = {Path(item["package_path"]).name for item in report["evidence_files"]}
    assert "ENHANCEMENT_REVIEW_REPORT.json" in evidence_names


def test_photo3d_delivery_pack_blocks_existing_preview_semantic_review(tmp_path):
    from tools.enhancement_semantic_review import write_enhancement_review_report
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(
        fixture,
        enhancement_path,
        checks={
            "geometry_preserved": True,
            "material_consistent": False,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
    )
    write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["final_deliverable"] is False
    assert report["semantic_material_review"]["status"] == "preview"
    assert report["blocking_reasons"][0]["code"] == "semantic_review_not_accepted"
    assert report["deliverables"]["enhanced_images"] == []


def test_photo3d_delivery_pack_requires_semantic_review_when_requested(tmp_path):
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture)

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        require_semantic_review=True,
    )

    assert report["final_deliverable"] is False
    assert report["semantic_material_review"]["status"] == "not_run"
    assert report["blocking_reasons"][0]["code"] == "semantic_review_required"
    assert report["deliverables"]["enhanced_images"] == []


def test_cmd_photo3d_deliver_accepts_require_semantic_review_flag(tmp_path, monkeypatch):
    import cad_pipeline
    from tools.enhancement_semantic_review import write_enhancement_review_report

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(fixture, enhancement_path)
    write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_deliver(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            output=None,
            include_preview=False,
            require_semantic_review=True,
        )
    )

    assert rc == 0
