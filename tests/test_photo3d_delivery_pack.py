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


# === Task 22: DELIVERY_PACKAGE.json jury 字段 ===


def test_build_jury_section_present(tmp_path):
    """PHOTO3D_JURY_REPORT.json 存在 → 抽 status / actual_cost / vendor_ids / schema_version。"""
    from tools.photo3d_delivery_pack import _build_jury_section

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "accepted",
                "jury_meta": {"actual_cost_usd": 0.030},
                "views": [
                    {"llm_meta": {"vendor_request_id": "trace-1"}},
                    {"llm_meta": {"vendor_request_id": "trace-2"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    section = _build_jury_section(run_dir, tmp_path)
    assert section is not None
    assert section["status"] == "accepted"
    assert section["actual_cost_usd"] == 0.030
    assert section["vendor_request_ids"] == ["trace-1", "trace-2"]
    assert section["jury_report_schema_version"] == 1
    assert section["report"].endswith("PHOTO3D_JURY_REPORT.json")
    # review_input 缺失则为 None
    assert section["review_input"] is None


def test_build_jury_section_with_review_input(tmp_path):
    """jury_review_input.json 存在时 review_input 字段为相对路径。"""
    from tools.photo3d_delivery_pack import _build_jury_section

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "accepted",
                "jury_meta": {"actual_cost_usd": 0.010},
                "views": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "jury_review_input.json").write_text("{}", encoding="utf-8")
    section = _build_jury_section(run_dir, tmp_path)
    assert section is not None
    assert section["review_input"] is not None
    assert section["review_input"].endswith("jury_review_input.json")


def test_build_jury_section_absent_when_no_report(tmp_path):
    """PHOTO3D_JURY_REPORT.json 不存在 → 返 None。"""
    from tools.photo3d_delivery_pack import _build_jury_section

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert _build_jury_section(run_dir, tmp_path) is None


def test_build_jury_section_corrupt_json_returns_none(tmp_path):
    """PHOTO3D_JURY_REPORT.json 解析失败 → 返 None（不抛）。"""
    from tools.photo3d_delivery_pack import _build_jury_section

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
        "{not valid json",
        encoding="utf-8",
    )
    assert _build_jury_section(run_dir, tmp_path) is None


def test_delivery_package_includes_jury_field_when_jury_ran(tmp_path):
    """jury 跑过后 deliver 把 jury 报告并入 DELIVERY_PACKAGE.json 顶层 jury 字段。"""
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")
    # 写入 jury 报告 + review_input
    run_dir = fixture["run_dir"]
    (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "subsystem": "demo",
                "run_id": fixture["run_id"],
                "status": "accepted",
                "jury_meta": {"actual_cost_usd": 0.020},
                "views": [
                    {"llm_meta": {"vendor_request_id": "trace-V1"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "jury_review_input.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "subsystem": "demo",
                "run_id": fixture["run_id"],
            }
        ),
        encoding="utf-8",
    )

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    pkg = json.loads(
        (tmp_path / report["artifacts"]["delivery_package"]).read_text(
            encoding="utf-8"
        )
    )
    assert "jury" in pkg
    assert pkg["jury"] is not None
    assert pkg["jury"]["status"] == "accepted"
    assert pkg["jury"]["actual_cost_usd"] == 0.020
    assert pkg["jury"]["vendor_request_ids"] == ["trace-V1"]
    assert isinstance(pkg["jury"]["vendor_request_ids"], list)
    assert pkg["jury"]["jury_report_schema_version"] == 1
    assert pkg["jury"]["review_input"].endswith("jury_review_input.json")


def test_delivery_package_jury_field_null_when_jury_not_run(tmp_path):
    """jury 未跑 → DELIVERY_PACKAGE.json 顶层 jury 字段为 None。"""
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")

    report = run_photo3d_delivery_pack(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
    )

    pkg = json.loads(
        (tmp_path / report["artifacts"]["delivery_package"]).read_text(
            encoding="utf-8"
        )
    )
    assert "jury" in pkg
    assert pkg["jury"] is None


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


# === 队列 D Task 1: view_evidence 字段 ===


def test_delivery_package_includes_view_evidence_when_manifest_has_visible_instance_ids(tmp_path):
    """render_manifest 带 evidence_method / visible_instance_ids（队列 C）时，
    DELIVERY_PACKAGE.json 与 report 都带 view_evidence（evidence_method + per_view）。"""
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")

    report = run_photo3d_delivery_pack(
        tmp_path, "demo", artifact_index_path=fixture["index_path"]
    )

    assert report["view_evidence"] == {
        "evidence_method": "instance_bbox_presence",
        "per_view": {"V1": ["P-100-01#01", "P-100-02#01"]},
    }
    pkg = json.loads(
        (tmp_path / report["artifacts"]["delivery_package"]).read_text(encoding="utf-8")
    )
    assert pkg["view_evidence"] == report["view_evidence"]


def test_delivery_package_view_evidence_is_none_when_manifest_lacks_evidence(tmp_path):
    """老 run / 缺 assembly_signature → render_manifest 无 evidence_method / visible_instance_ids
    → view_evidence 为 None（向后兼容）。"""
    from tools.photo3d_delivery_pack import run_photo3d_delivery_pack

    fixture = _contracts(tmp_path)
    _write_photo3d_run(fixture)
    _write_enhancement_report(fixture, "accepted")
    manifest_path = fixture["paths"]["render_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("evidence_method", None)
    for entry in manifest.get("files", []):
        entry.pop("visible_instance_ids", None)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = run_photo3d_delivery_pack(
        tmp_path, "demo", artifact_index_path=fixture["index_path"]
    )

    assert report["view_evidence"] is None
    pkg = json.loads(
        (tmp_path / report["artifacts"]["delivery_package"]).read_text(encoding="utf-8")
    )
    assert pkg["view_evidence"] is None


# === 队列 D Task 2: _status_badge ===


def test_status_badge_positive_warn_block():
    from tools.photo3d_delivery_pack import _status_badge

    assert _status_badge("delivered") == "✓ 已交付"
    assert _status_badge("accepted") == "✓ 已验收"
    assert _status_badge("preview") == "⚠ 预览"
    assert _status_badge("not_run") == "⚠ 未做"
    assert _status_badge("needs_review") == "⚠ 建议复核"
    assert _status_badge("blocked") == "✗ 阻断"
    assert _status_badge("not_deliverable") == "✗ 未交付"


def test_status_badge_unknown_is_neutral_never_block():
    from tools.photo3d_delivery_pack import _status_badge

    assert _status_badge("weird_state") == "· weird_state"
    assert _status_badge("") == "· 未知"
    assert _status_badge(None) == "· 未知"


# === 队列 D Task 3: _pkg_path_relative_to_delivery ===


def test_pkg_path_relative_to_delivery_strips_delivery_prefix():
    from tools.photo3d_delivery_pack import _pkg_path_relative_to_delivery

    delivery_dir = "cad/demo/.cad-spec-gen/runs/RUN001/delivery"
    assert (
        _pkg_path_relative_to_delivery(
            "cad/demo/.cad-spec-gen/runs/RUN001/delivery/enhanced/V1_enhanced.jpg",
            delivery_dir,
        )
        == "enhanced/V1_enhanced.jpg"
    )
    assert (
        _pkg_path_relative_to_delivery(
            "cad/demo/.cad-spec-gen/runs/RUN001/delivery/labeled/V1_labeled.jpg",
            delivery_dir,
        )
        == "labeled/V1_labeled.jpg"
    )


def test_pkg_path_relative_to_delivery_falls_back_to_basename_on_bad_path():
    from tools.photo3d_delivery_pack import _pkg_path_relative_to_delivery

    # package_path 不在 delivery_dir 内 → 不抛，退化为 basename
    assert (
        _pkg_path_relative_to_delivery(
            "some/other/place/img.jpg", "cad/demo/.cad-spec-gen/runs/RUN001/delivery"
        )
        == "img.jpg"
    )


# === 队列 D Task 4: README section builders（headline / images / view_evidence）===


def test_readme_headline_basic():
    from tools.photo3d_delivery_pack import _readme_headline

    lines = _readme_headline(
        {
            "subsystem": "demo",
            "run_id": "RUN001",
            "status": "delivered",
            "enhancement_status": "accepted",
            "final_deliverable": True,
            "ordinary_user_message": "最终交付包已生成。",
        }
    )
    text = "\n".join(lines)
    assert text.startswith("# 交付包验收 — demo / RUN001")
    assert "**状态**：✓ 已交付  ·  增强：✓ 已验收  ·  最终交付物：是" in text
    assert "> 最终交付包已生成。" in text


def test_readme_images_section_embeds_relative_path_and_part_count_and_labeled():
    from tools.photo3d_delivery_pack import _readme_images_section

    report = {
        "delivery_dir": "cad/demo/.cad-spec-gen/runs/RUN001/delivery",
        "deliverables": {
            "enhanced_images": [
                {
                    "view": "V1",
                    "package_path": "cad/demo/.cad-spec-gen/runs/RUN001/delivery/enhanced/V1_e.jpg",
                }
            ],
            "labeled_images": [
                {
                    "view": "V1",
                    "package_path": "cad/demo/.cad-spec-gen/runs/RUN001/delivery/labeled/V1_l.jpg",
                }
            ],
        },
        "view_evidence": {"evidence_method": "instance_bbox_presence", "per_view": {"V1": ["A", "B", "C"]}},
    }
    text = "\n".join(_readme_images_section(report))
    assert "## 渲染图（增强后）" in text
    assert "### V1" in text
    assert "![V1 增强图](enhanced/V1_e.jpg)" in text
    assert "- 本图标着含 3 个零件" in text
    assert "[带标注版](labeled/V1_l.jpg)" in text


def test_readme_images_section_empty_when_no_enhanced_images():
    from tools.photo3d_delivery_pack import _readme_images_section

    assert _readme_images_section({"deliverables": {"enhanced_images": []}}) == []
    assert _readme_images_section({}) == []


def test_readme_images_section_omits_part_count_when_no_view_evidence():
    from tools.photo3d_delivery_pack import _readme_images_section

    report = {
        "delivery_dir": "cad/demo/.cad-spec-gen/runs/RUN001/delivery",
        "deliverables": {
            "enhanced_images": [
                {"view": "V1", "package_path": "cad/demo/.cad-spec-gen/runs/RUN001/delivery/enhanced/V1_e.jpg"}
            ]
        },
        "view_evidence": None,
    }
    text = "\n".join(_readme_images_section(report))
    assert "![V1 增强图](enhanced/V1_e.jpg)" in text
    assert "本图标着含" not in text


def test_readme_view_evidence_section_counts_and_none():
    from tools.photo3d_delivery_pack import _readme_view_evidence_section

    text = "\n".join(
        _readme_view_evidence_section(
            {
                "view_evidence": {
                    "evidence_method": "instance_bbox_presence",
                    "per_view": {"V2": ["A"], "V1": ["A", "B"]},
                }
            }
        )
    )
    assert "## 完整性证据" in text
    assert "证据方式：instance_bbox_presence" in text
    assert "各视角实例计数：V1=2、V2=1" in text  # 按 view 名排序
    assert "RENDER_VISUAL_REGRESSION.json" in text
    assert _readme_view_evidence_section({"view_evidence": None}) == []
    assert _readme_view_evidence_section({}) == []


# === 队列 D Task 5: README section builders（model_quality / review_status / next_step / blocking / appendix）===


def test_readme_model_quality_section():
    from tools.photo3d_delivery_pack import _readme_model_quality_section

    text = "\n".join(
        _readme_model_quality_section(
            {
                "model_quality_summary": {
                    "ordinary_user_message": "模型质量摘要发现 2 个零件建议复核。",
                    "readiness_status": "needs_review",
                    "photoreal_risk": "high",
                    "review_recommended_count": 2,
                    "blocking_count": 0,
                }
            }
        )
    )
    assert "## 模型质量" in text
    assert "> 模型质量摘要发现 2 个零件建议复核。" in text
    assert "就绪状态：needs_review  ·  照片级风险：high" in text
    assert "建议复核 2 个零件  ·  阻断 0 个" in text
    assert _readme_model_quality_section({"model_quality_summary": None}) == []
    assert _readme_model_quality_section({}) == []


def test_readme_review_status_section_semantic_required_and_jury_none():
    from tools.photo3d_delivery_pack import _readme_review_status_section

    text = "\n".join(
        _readme_review_status_section(
            {
                "quality_summary": {"status": "accepted"},
                "enhancement_status": "accepted",
                "semantic_material_review": {"status": "not_run", "required": True},
                "jury": None,
            }
        )
    )
    assert "## 复核状态" in text
    assert "| 增强图质量（quality_summary）| ✓ 已验收 |" in text
    assert "| AI 增强（enhancement）| ✓ 已验收 |" in text
    assert "| 语义/材质复核（semantic_material_review）| ⚠ 必需但未做 |" in text
    assert "| AI 视觉评分（jury）| ⚠ 未运行 |" in text


def test_readme_review_status_section_semantic_not_required_and_jury_accepted():
    from tools.photo3d_delivery_pack import _readme_review_status_section

    text = "\n".join(
        _readme_review_status_section(
            {
                "quality_summary": {"status": "unknown"},
                "enhancement_status": "preview",
                "semantic_material_review": {"status": "not_run", "required": False},
                "jury": {"status": "accepted", "actual_cost_usd": 0.02},
            }
        )
    )
    assert "| 增强图质量（quality_summary）| ⚠ 未知 |" in text
    assert "| AI 增强（enhancement）| ⚠ 预览 |" in text
    assert "| 语义/材质复核（semantic_material_review）| ⚠ 未做（非强制） |" in text
    assert "| AI 视觉评分（jury）| ✓ 已验收（成本 $0.02） |" in text


def test_readme_review_status_section_semantic_blocked_shows_report_path():
    from tools.photo3d_delivery_pack import _readme_review_status_section

    text = "\n".join(
        _readme_review_status_section(
            {
                "quality_summary": {"status": "accepted"},
                "enhancement_status": "accepted",
                "semantic_material_review": {
                    "status": "blocked",
                    "required": False,
                    "review_report": "cad/x/ENHANCEMENT_REVIEW_REPORT.json",
                },
                "jury": None,
            }
        )
    )
    assert "✗ 阻断（见 `cad/x/ENHANCEMENT_REVIEW_REPORT.json`）" in text


def test_readme_next_step_section_three_branches():
    from tools.photo3d_delivery_pack import _readme_next_step_section

    # 1. 有阻断项
    text = "\n".join(_readme_next_step_section({"blocking_reasons": [{"code": "x"}]}))
    assert "## 下一步" in text
    assert "✗ 当前有阻断项" in text
    # 2. recommended_next_action.kind == review_models
    text = "\n".join(
        _readme_next_step_section(
            {
                "blocking_reasons": [],
                "model_quality_summary": {"recommended_next_action": {"kind": "review_models"}},
                "status": "preview_package",
            }
        )
    )
    assert "⚠ 建议先复核标黄的零件，再交付。" in text
    # 3. delivered 且无阻断、无建议动作
    text = "\n".join(
        _readme_next_step_section(
            {
                "blocking_reasons": [],
                "model_quality_summary": {"recommended_next_action": {"kind": "continue_photo3d"}},
                "status": "delivered",
            }
        )
    )
    assert "✓ 交付完成，无需进一步动作。" in text


def test_readme_blocking_section():
    from tools.photo3d_delivery_pack import _readme_blocking_section

    text = "\n".join(
        _readme_blocking_section({"blocking_reasons": [{"code": "photo_quality_not_accepted", "message": "质量未验收"}]})
    )
    assert "## 阻断项" in text
    assert "- photo_quality_not_accepted: 质量未验收" in text
    assert _readme_blocking_section({"blocking_reasons": []}) == []
    assert _readme_blocking_section({}) == []


def test_readme_evidence_appendix():
    from tools.photo3d_delivery_pack import _readme_evidence_appendix

    text = "\n".join(
        _readme_evidence_appendix(
            {
                "source_reports": {
                    "render_manifest": "cad/.../render_manifest.json",
                    "artifact_index": "cad/.../ARTIFACT_INDEX.json",
                },
                "deliverables": {
                    "source_images": [{"view": "V1"}],
                    "enhanced_images": [{"view": "V1"}],
                    "labeled_images": [],
                },
                "evidence_files": [{"package_path": "cad/.../delivery/evidence/x.json"}],
                "delivery_dir": "cad/.../delivery",
            }
        )
    )
    assert "## 证据清单（供审计）" in text
    assert "- artifact_index: `cad/.../ARTIFACT_INDEX.json`" in text
    assert "- render_manifest: `cad/.../render_manifest.json`" in text
    assert "- 源渲染：1 张" in text
    assert "- 增强图：1 张" in text
    assert "- 标注图：0 张" in text
    assert "- `cad/.../delivery/evidence/x.json`" in text
    assert "cad/.../delivery" in text  # 末尾说明里有 delivery_dir
