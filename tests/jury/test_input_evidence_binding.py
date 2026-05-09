"""Layer 0 — 输入证据绑定 + 资源/竞态防护 (Tasks 13+14, 11 case)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jury.config import JuryCaps
from tools.jury.input_evidence_binding import (
    JuryLockBusy,
    Layer0Verdict,
    run_layer0,
)

# 重导出冒烟（保证 import 路径稳定，对应 spec rev 5 §6.4）；不计入 11 case 主体。
assert issubclass(JuryLockBusy, Exception)
assert Layer0Verdict is not None


_DEFAULT_CAPS = JuryCaps(
    max_image_bytes=8 * 1024 * 1024, max_n_views=32, min_photoreal_score=60
)


@pytest.fixture
def project_root_with_run(tmp_path: Path) -> Path:
    """构造完整 cad/<sub>/.cad-spec-gen/runs/<run>/ + ARTIFACT_INDEX.json + 假图。"""
    sub = "lifting_platform"
    run_id = "20260508-123456"
    fixtures = Path("tests/jury/fixtures")

    run_dir = tmp_path / "cad" / sub / ".cad-spec-gen" / "runs" / run_id
    run_dir.mkdir(parents=True)
    render_dir = tmp_path / "cad" / "output" / "renders" / sub / run_id
    render_dir.mkdir(parents=True)
    (render_dir / "iso_enhanced.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)
    (render_dir / "front_enhanced.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000
    )

    rm = json.loads(
        (fixtures / "sample_render_manifest.json").read_text(encoding="utf-8")
    )
    er = json.loads(
        (fixtures / "sample_enhancement_report.json").read_text(encoding="utf-8")
    )
    for v in er["views"]:
        v["enhanced_image"] = (
            f"cad/output/renders/{sub}/{run_id}/{v['view']}_enhanced.png"
        )
    (render_dir / "render_manifest.json").write_text(json.dumps(rm), encoding="utf-8")
    (render_dir / "ENHANCEMENT_REPORT.json").write_text(
        json.dumps(er), encoding="utf-8"
    )

    ai = json.loads(
        (fixtures / "sample_artifact_index.json").read_text(encoding="utf-8")
    )
    (run_dir.parent.parent / "ARTIFACT_INDEX.json").write_text(
        json.dumps(ai), encoding="utf-8"
    )
    return tmp_path


def test_happy_path_freezes_all(project_root_with_run: Path) -> None:
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is True
    assert v.frozen_run_id == "20260508-123456"
    assert v.frozen_sha256.get("enhancement_report", "").startswith("sha256:")
    assert v.frozen_sha256.get("render_manifest", "").startswith("sha256:")


def test_subsystem_mismatch_blocked(project_root_with_run: Path) -> None:
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="other_subsystem",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is False
    # 整个 subsystem 错可能在更早阶段 fail（artifact_index 不存在），允许多种 blocking_reasons
    assert any(
        r["code"] in {"subsystem_mismatch", "artifact_index_missing"}
        for r in v.blocking_reasons
    )


def test_enhancement_report_missing_blocked(project_root_with_run: Path) -> None:
    er_path = (
        project_root_with_run
        / "cad"
        / "output"
        / "renders"
        / "lifting_platform"
        / "20260508-123456"
        / "ENHANCEMENT_REPORT.json"
    )
    er_path.unlink()
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is False
    assert any(
        r["code"] in {"enhancement_report_missing", "enhancement_report_unreadable"}
        for r in v.blocking_reasons
    )


def test_quality_summary_status_not_accepted_blocked(
    project_root_with_run: Path,
) -> None:
    er_path = (
        project_root_with_run
        / "cad"
        / "output"
        / "renders"
        / "lifting_platform"
        / "20260508-123456"
        / "ENHANCEMENT_REPORT.json"
    )
    er = json.loads(er_path.read_text(encoding="utf-8"))
    er["quality_summary"]["status"] = "preview"
    er_path.write_text(json.dumps(er), encoding="utf-8")
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is False
    assert any(r["code"] == "quality_summary_not_accepted" for r in v.blocking_reasons)


def test_views_empty_blocked(project_root_with_run: Path) -> None:
    er_path = (
        project_root_with_run
        / "cad"
        / "output"
        / "renders"
        / "lifting_platform"
        / "20260508-123456"
        / "ENHANCEMENT_REPORT.json"
    )
    er = json.loads(er_path.read_text(encoding="utf-8"))
    er["views"] = []
    er_path.write_text(json.dumps(er), encoding="utf-8")
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is False
    assert any(r["code"] == "views_empty" for r in v.blocking_reasons)


def test_duplicate_view_name_blocked(project_root_with_run: Path) -> None:
    er_path = (
        project_root_with_run
        / "cad"
        / "output"
        / "renders"
        / "lifting_platform"
        / "20260508-123456"
        / "ENHANCEMENT_REPORT.json"
    )
    er = json.loads(er_path.read_text(encoding="utf-8"))
    er["views"].append(dict(er["views"][0]))  # 复制第一个视角（同 view 名 "iso"）
    er_path.write_text(json.dumps(er), encoding="utf-8")
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is False
    assert any(r["code"] == "duplicate_view" for r in v.blocking_reasons)


def test_max_n_views_exceeded_blocked(project_root_with_run: Path) -> None:
    er_path = (
        project_root_with_run
        / "cad"
        / "output"
        / "renders"
        / "lifting_platform"
        / "20260508-123456"
        / "ENHANCEMENT_REPORT.json"
    )
    er = json.loads(er_path.read_text(encoding="utf-8"))
    # 拷贝出 40 个独立视角（避免 view 名重复触发 duplicate_view）
    er["views"] = [{**er["views"][0], "view": f"v{i}"} for i in range(40)]
    er_path.write_text(json.dumps(er), encoding="utf-8")
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is False
    assert any(r["code"] == "max_n_views_exceeded" for r in v.blocking_reasons)


def test_image_too_large_blocked(project_root_with_run: Path) -> None:
    img = (
        project_root_with_run
        / "cad"
        / "output"
        / "renders"
        / "lifting_platform"
        / "20260508-123456"
        / "iso_enhanced.png"
    )
    img.write_bytes(b"\x00" * (10 * 1024 * 1024))  # 10 MiB > 8 MiB cap
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is False
    assert any(r["code"] == "image_too_large" for r in v.blocking_reasons)


def test_active_run_not_active_blocked(project_root_with_run: Path) -> None:
    ai_path = (
        project_root_with_run
        / "cad"
        / "lifting_platform"
        / ".cad-spec-gen"
        / "ARTIFACT_INDEX.json"
    )
    ai = json.loads(ai_path.read_text(encoding="utf-8"))
    ai["runs"]["20260508-123456"]["active"] = False
    ai_path.write_text(json.dumps(ai), encoding="utf-8")
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.passed is False


def test_artifact_index_missing_blocked(tmp_path: Path) -> None:
    """完全空 project_root，无 ARTIFACT_INDEX → blocked。"""
    v = run_layer0(project_root=tmp_path, subsystem="x", caps=_DEFAULT_CAPS)
    assert v.passed is False
    assert any(r["code"] == "artifact_index_missing" for r in v.blocking_reasons)


def test_sha256_freeze_returns_with_prefix(project_root_with_run: Path) -> None:
    v = run_layer0(
        project_root=project_root_with_run,
        subsystem="lifting_platform",
        caps=_DEFAULT_CAPS,
    )
    assert v.frozen_sha256["enhancement_report"].startswith("sha256:")
    assert v.frozen_sha256["render_manifest"].startswith("sha256:")
