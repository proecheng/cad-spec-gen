"""L4 cmd_enhance_check 透传 matches_spec_status — ENHANCEMENT_REPORT.quality_summary 来自 PHOTO3D_JURY_REPORT。

Task 11 (v2.37 jury matches_spec)：
- enhance_consistency.build_enhancement_report 读 `cad/<sub>/.cad-spec-gen/ARTIFACT_INDEX.json`
  拿 `active_run_id` → 读 `runs/<id>/PHOTO3D_JURY_REPORT.json` 拿 `matches_spec_status`。
- 写进 ENHANCEMENT_REPORT.json::quality_summary.matches_spec_status。
- Fail-safe：缺/烂/不是 dict → matches_spec_status = None（透传 None 而非 silently drop key）。

Plan 字面路径 `cad/output/renders/jury_report.json` 错的——真实路径走 ARTIFACT_INDEX.json
(同 Task 10 `_apply_matches_spec_fail_gate` 模式)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


def _source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 64, 192, 192), fill=(20, 90, 150))
    image.save(path)


def _manifest(project_root: Path, render_dir: Path, files: list[tuple[str, Path]], *, subsystem: str = "demo", run_id: str = "RUN001") -> dict[str, Any]:
    return {
        "schema_version": 2,
        "status": "pass",
        "run_id": run_id,
        "subsystem": subsystem,
        "render_dir_rel_project": render_dir.relative_to(project_root).as_posix(),
        "render_dir_abs_resolved": str(render_dir),
        "files": [
            {
                "view": view,
                "path_rel_project": source.relative_to(project_root).as_posix(),
                "path_abs_resolved": str(source),
                "sha256": f"sha256:{view}",
                "qa": {"passed": True},
            }
            for view, source in files
        ],
    }


def _write_jury_report(project_root: Path, *, subsystem: str, run_id: str, payload: dict[str, Any]) -> Path:
    """写 ARTIFACT_INDEX.json + PHOTO3D_JURY_REPORT.json，模仿真实 jury 落盘。"""
    cs_dir = project_root / "cad" / subsystem / ".cad-spec-gen"
    cs_dir.mkdir(parents=True, exist_ok=True)
    (cs_dir / "ARTIFACT_INDEX.json").write_text(
        json.dumps({"active_run_id": run_id}, ensure_ascii=False),
        encoding="utf-8",
    )
    run_dir = cs_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    jury_path = run_dir / "PHOTO3D_JURY_REPORT.json"
    jury_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return jury_path


def test_enhance_check_transits_matches_spec_status_pass(tmp_path: Path) -> None:
    """matches_spec_status='pass' 透传到 ENHANCEMENT_REPORT.quality_summary。"""
    from tools.enhance_consistency import build_enhancement_report

    subsystem = "demo"
    run_id = "RUN001"
    render_dir = tmp_path / "cad" / "output" / "renders" / subsystem / run_id
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260514_1200_enhanced.jpg"
    _source(src_v1)
    _source(enhanced_v1)

    _write_jury_report(
        tmp_path,
        subsystem=subsystem,
        run_id=run_id,
        payload={
            "schema_version": 1,
            "subsystem": subsystem,
            "run_id": run_id,
            "matches_spec_status": "pass",
        },
    )

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1)], subsystem=subsystem, run_id=run_id),
        enhanced_images=[enhanced_v1],
    )

    assert report["quality_summary"]["matches_spec_status"] == "pass", (
        f"应透传 matches_spec_status=pass，实际 quality_summary={report['quality_summary']}"
    )


def test_enhance_check_transits_matches_spec_status_fail(tmp_path: Path) -> None:
    """matches_spec_status='fail' 也透传（Task 10 blocked 在 deliver 阶段决定，此处仅透传）。"""
    from tools.enhance_consistency import build_enhancement_report

    subsystem = "demo"
    run_id = "RUN001"
    render_dir = tmp_path / "cad" / "output" / "renders" / subsystem / run_id
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260514_1200_enhanced.jpg"
    _source(src_v1)
    _source(enhanced_v1)

    _write_jury_report(
        tmp_path,
        subsystem=subsystem,
        run_id=run_id,
        payload={
            "schema_version": 1,
            "subsystem": subsystem,
            "run_id": run_id,
            "matches_spec_status": "fail",
        },
    )

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1)], subsystem=subsystem, run_id=run_id),
        enhanced_images=[enhanced_v1],
    )

    assert report["quality_summary"]["matches_spec_status"] == "fail"


def test_enhance_check_no_jury_report_matches_spec_none(tmp_path: Path) -> None:
    """jury_report 不存在 → quality_summary.matches_spec_status = None（fail-safe + key 仍存在）。"""
    from tools.enhance_consistency import build_enhancement_report

    subsystem = "demo"
    run_id = "RUN001"
    render_dir = tmp_path / "cad" / "output" / "renders" / subsystem / run_id
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260514_1200_enhanced.jpg"
    _source(src_v1)
    _source(enhanced_v1)
    # 故意不写 ARTIFACT_INDEX.json 也不写 PHOTO3D_JURY_REPORT.json

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1)], subsystem=subsystem, run_id=run_id),
        enhanced_images=[enhanced_v1],
    )

    assert "matches_spec_status" in report["quality_summary"], (
        "key 应始终存在（透传 None 而非 silently drop）"
    )
    assert report["quality_summary"]["matches_spec_status"] is None


def test_enhance_check_corrupted_jury_report_matches_spec_none(tmp_path: Path) -> None:
    """PHOTO3D_JURY_REPORT.json 是坏 JSON → fail-safe 不抛，matches_spec_status=None。"""
    from tools.enhance_consistency import build_enhancement_report

    subsystem = "demo"
    run_id = "RUN001"
    render_dir = tmp_path / "cad" / "output" / "renders" / subsystem / run_id
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260514_1200_enhanced.jpg"
    _source(src_v1)
    _source(enhanced_v1)

    cs_dir = tmp_path / "cad" / subsystem / ".cad-spec-gen"
    cs_dir.mkdir(parents=True, exist_ok=True)
    (cs_dir / "ARTIFACT_INDEX.json").write_text(
        json.dumps({"active_run_id": run_id}, ensure_ascii=False),
        encoding="utf-8",
    )
    run_dir = cs_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
        "{ not valid json", encoding="utf-8"
    )

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1)], subsystem=subsystem, run_id=run_id),
        enhanced_images=[enhanced_v1],
    )

    assert report["quality_summary"]["matches_spec_status"] is None


def test_enhance_check_no_active_run_id_matches_spec_none(tmp_path: Path) -> None:
    """ARTIFACT_INDEX.json 存在但缺 active_run_id → matches_spec_status=None。"""
    from tools.enhance_consistency import build_enhancement_report

    subsystem = "demo"
    run_id = "RUN001"
    render_dir = tmp_path / "cad" / "output" / "renders" / subsystem / run_id
    src_v1 = render_dir / "V1_front.png"
    enhanced_v1 = render_dir / "V1_front_20260514_1200_enhanced.jpg"
    _source(src_v1)
    _source(enhanced_v1)

    cs_dir = tmp_path / "cad" / subsystem / ".cad-spec-gen"
    cs_dir.mkdir(parents=True, exist_ok=True)
    (cs_dir / "ARTIFACT_INDEX.json").write_text(
        json.dumps({}, ensure_ascii=False), encoding="utf-8"
    )

    report = build_enhancement_report(
        tmp_path,
        _manifest(tmp_path, render_dir, [("V1", src_v1)], subsystem=subsystem, run_id=run_id),
        enhanced_images=[enhanced_v1],
    )

    assert report["quality_summary"]["matches_spec_status"] is None
