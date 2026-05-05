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


def _write_enhancement_report(fixture, status="accepted", *, run_id=None, with_views=True):
    project_root = fixture["run_dir"].parents[4]
    source = fixture["render_dir"] / "V1_front.png"
    enhanced = fixture["render_dir"] / "V1_front_20260505_1200_enhanced.jpg"
    labeled = fixture["render_dir"] / "V1_front_20260505_1200_enhanced_labeled_en.jpg"
    if status != "blocked":
        _save_jpg_from_png(source, enhanced)
        _save_jpg_from_png(source, labeled)

    views = []
    if with_views:
        views.append(
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
        )

    _write_json(
        fixture["render_dir"] / "ENHANCEMENT_REPORT.json",
        {
            "schema_version": 1,
            "run_id": run_id or fixture["run_id"],
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
                "status": "accepted",
                "view_count": 1,
                "warnings": [],
            },
            "views": views,
            "blocking_reasons": [] if status == "accepted" else [{"code": f"{status}_reason"}],
        },
    )


def test_photo3d_delivery_pack_packages_accepted_run_evidence(tmp_path):
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "delivered"
    assert report["final_deliverable"] is True
    assert report["run_id"] == "RUN001"
    assert report["delivery_dir"] == "cad/demo/.cad-spec-gen/runs/RUN001/delivery"
    assert report["artifacts"]["delivery_package"].endswith(
        "RUN001/delivery/DELIVERY_PACKAGE.json"
    )

    package_path = tmp_path / report["artifacts"]["delivery_package"]
    package = json.loads(package_path.read_text(encoding="utf-8"))
    assert package["status"] == "delivered"
    assert package["quality_summary"]["status"] == "accepted"
    assert package["source_reports"]["enhancement_report"] == (
        "cad/output/renders/demo/RUN001/ENHANCEMENT_REPORT.json"
    )
    assert package["source_reports"]["render_manifest"] == (
        "cad/output/renders/demo/RUN001/render_manifest.json"
    )

    enhanced_paths = [
        tmp_path / image["package_path"]
        for image in package["deliverables"]["enhanced_images"]
    ]
    source_paths = [
        tmp_path / image["package_path"]
        for image in package["deliverables"]["source_images"]
    ]
    labeled_paths = [
        tmp_path / image["package_path"]
        for image in package["deliverables"]["labeled_images"]
    ]
    evidence_names = {
        Path(item["package_path"]).name for item in package["evidence_files"]
    }

    assert [path.name for path in enhanced_paths] == [
        "V1_front_20260505_1200_enhanced.jpg"
    ]
    assert [path.name for path in source_paths] == ["V1_front.png"]
    assert [path.name for path in labeled_paths] == [
        "V1_front_20260505_1200_enhanced_labeled_en.jpg"
    ]
    for path in enhanced_paths + source_paths + labeled_paths:
        assert path.is_file()
    assert {
        "ENHANCEMENT_REPORT.json",
        "render_manifest.json",
        "PHOTO3D_RUN.json",
    } <= evidence_names
    assert (tmp_path / report["artifacts"]["delivery_readme"]).is_file()


def test_photo3d_delivery_pack_includes_active_run_model_quality_summary(tmp_path):
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    summary = report["model_quality_summary"]
    assert summary["source"] == "model_contract"
    assert summary["binding_status"] == "active_run_model_contract"
    assert summary["source_report"] == "cad/demo/.cad-spec-gen/runs/RUN001/MODEL_CONTRACT.json"
    assert summary["readiness_status"] == "needs_review"
    assert summary["photoreal_risk"] == "high"
    assert summary["quality_counts"] == {"B": 1, "C": 1}
    assert summary["source_counts"] == {"parametric_template": 2}
    assert summary["recommended_next_action"]["kind"] == "review_models"
    assert report["source_reports"]["model_contract"] == (
        "cad/demo/.cad-spec-gen/runs/RUN001/MODEL_CONTRACT.json"
    )
    evidence_names = {
        Path(item["package_path"]).name for item in report["evidence_files"]
    }
    assert "MODEL_CONTRACT.json" in evidence_names

    readme = (tmp_path / report["artifacts"]["delivery_readme"]).read_text(
        encoding="utf-8"
    )
    assert "model_quality_summary" in readme
    assert "needs_review" in readme


def test_photo3d_delivery_pack_rejects_report_from_non_active_run(tmp_path):
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_enhancement_report(fixture, "accepted", run_id="RUN000")

    with pytest.raises(ValueError, match="run_id"):
        run_photo3d_delivery_pack(
            tmp_path,
            "demo",
            artifact_index_path=fixture["index_path"],
        )


def test_photo3d_delivery_pack_blocked_report_is_not_final_delivery(tmp_path):
    from tools.photo3d_delivery_pack import (
        command_return_code_for_delivery_pack,
        run_photo3d_delivery_pack,
    )

    fixture = _contracts(tmp_path)
    _write_enhancement_report(fixture, "blocked")

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "not_deliverable"
    assert report["final_deliverable"] is False
    assert report["deliverables"]["enhanced_images"] == []
    assert report["blocking_reasons"] == [{"code": "blocked_reason"}]
    assert command_return_code_for_delivery_pack(report) == 1

    package = json.loads(
        (fixture["run_dir"] / "delivery" / "DELIVERY_PACKAGE.json").read_text(
            encoding="utf-8"
        )
    )
    assert package["status"] == "not_deliverable"
    assert package["deliverables"]["enhanced_images"] == []
    assert not (fixture["run_dir"] / "delivery" / "enhanced").exists()


def test_photo3d_delivery_pack_blocked_rerun_removes_stale_final_images(tmp_path):
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")

    accepted = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )
    accepted_image = (
        tmp_path / accepted["deliverables"]["enhanced_images"][0]["package_path"]
    )
    assert accepted_image.is_file()

    _write_enhancement_report(fixture, "blocked")
    blocked = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert blocked["status"] == "not_deliverable"
    assert blocked["deliverables"]["enhanced_images"] == []
    assert not accepted_image.exists()
    assert not (fixture["run_dir"] / "delivery" / "enhanced").exists()


def test_photo3d_delivery_pack_rejects_unaccepted_quality_summary(tmp_path):
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")
    report_path = fixture["render_dir"] / "ENHANCEMENT_REPORT.json"
    enhancement_report = json.loads(report_path.read_text(encoding="utf-8"))
    enhancement_report["quality_summary"] = {
        "schema_version": 1,
        "status": "preview",
        "view_count": 1,
        "warnings": [{"code": "photo_quality_low_contrast", "view": "V1"}],
    }
    report_path.write_text(json.dumps(enhancement_report), encoding="utf-8")

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "not_deliverable"
    assert report["final_deliverable"] is False
    assert report["quality_summary"]["status"] == "preview"
    assert report["blocking_reasons"][0]["code"] == "photo_quality_not_accepted"
    assert report["deliverables"]["enhanced_images"] == []
    assert not (fixture["run_dir"] / "delivery" / "enhanced").exists()


def test_cmd_photo3d_deliver_writes_delivery_package(tmp_path, monkeypatch):
    import cad_pipeline

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_deliver(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            output=None,
            include_preview=False,
        )
    )

    assert rc == 0
    assert (fixture["run_dir"] / "delivery" / "DELIVERY_PACKAGE.json").is_file()
