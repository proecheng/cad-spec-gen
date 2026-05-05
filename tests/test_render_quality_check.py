import json
from types import SimpleNamespace

from PIL import Image, ImageDraw

from tests.test_photo3d_gate_contract import _contracts, _write_json


def _fake_version_runner(cmd, **kwargs):
    return SimpleNamespace(
        returncode=0,
        stdout="Blender 4.2.1 LTS\nbuild date: 2026-01-01\n",
        stderr="",
    )


def _low_contrast_render(path):
    image = Image.new("RGB", (320, 240), (132, 132, 132))
    draw = ImageDraw.Draw(image)
    draw.rectangle((96, 72, 224, 168), fill=(152, 152, 152))
    image.save(path)


def test_render_quality_check_writes_active_run_report_with_blender_preflight(tmp_path):
    from tools.render_quality_check import run_render_quality_check

    fixture = _contracts(tmp_path, run_id="RUN001")
    blender = tmp_path / "Blender Foundation" / "Blender" / "blender.exe"
    blender.parent.mkdir(parents=True)
    blender.write_text("fake blender", encoding="utf-8")

    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=blender,
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "pass"
    assert report["run_id"] == "RUN001"
    assert report["blender_preflight"]["status"] == "pass"
    assert report["blender_preflight"]["version"] == "4.2.1"
    assert report["render_quality_summary"]["status"] == "pass"
    assert report["views"][0]["view"] == "V1"
    assert report["views"][0]["pixel_metrics"]["contrast_stddev"] > 12.0
    written = json.loads(
        (fixture["run_dir"] / "RENDER_QUALITY_REPORT.json").read_text(encoding="utf-8")
    )
    assert written["artifacts"]["render_quality_report"].endswith(
        "cad/demo/.cad-spec-gen/runs/RUN001/RENDER_QUALITY_REPORT.json"
    )


def test_render_quality_check_blocks_missing_blender(tmp_path):
    from tools.render_quality_check import run_render_quality_check

    fixture = _contracts(tmp_path, run_id="RUN001")

    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=tmp_path / "missing_blender.exe",
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "blocked"
    assert report["blender_preflight"]["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "blender_not_found"


def test_render_quality_check_warns_for_low_contrast_active_run_render(tmp_path):
    from tools.render_quality_check import run_render_quality_check

    fixture = _contracts(tmp_path, run_id="RUN001")
    render_file = fixture["render_dir"] / "V1_front.png"
    _low_contrast_render(render_file)
    manifest = fixture["payloads"]["render_manifest"]
    manifest["files"][0]["sha256"] = "sha256:" + "0" * 64
    _write_json(fixture["paths"]["render_manifest"], manifest)
    blender = tmp_path / "blender.exe"
    blender.write_text("fake blender", encoding="utf-8")

    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=blender,
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "render_file_hash_mismatch"

    manifest["files"][0]["sha256"] = report["blocking_reasons"][0]["actual"]
    _write_json(fixture["paths"]["render_manifest"], manifest)
    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=blender,
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "warning"
    assert report["render_quality_summary"]["status"] == "warning"
    assert report["warnings"][0]["code"] == "render_quality_low_contrast"
    assert report["views"][0]["pixel_metrics"]["contrast_stddev"] < 12.0


def test_render_quality_check_blocks_manifest_run_drift_and_writes_active_run_report(
    tmp_path,
):
    from tools.render_quality_check import run_render_quality_check

    fixture = _contracts(tmp_path, run_id="RUN001")
    manifest = fixture["payloads"]["render_manifest"]
    manifest["run_id"] = "RUN999"
    _write_json(fixture["paths"]["render_manifest"], manifest)
    blender = tmp_path / "blender.exe"
    blender.write_text("fake blender", encoding="utf-8")

    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=blender,
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "blocked"
    assert report["run_id"] == "RUN001"
    assert {reason["code"] for reason in report["blocking_reasons"]} >= {"run_id_mismatch"}
    written = json.loads(
        (fixture["run_dir"] / "RENDER_QUALITY_REPORT.json").read_text(encoding="utf-8")
    )
    assert written["run_id"] == "RUN001"
    assert written["artifacts"]["render_quality_report"].endswith(
        "cad/demo/.cad-spec-gen/runs/RUN001/RENDER_QUALITY_REPORT.json"
    )
    assert not (
        tmp_path
        / "cad"
        / "demo"
        / ".cad-spec-gen"
        / "runs"
        / "RUN999"
        / "RENDER_QUALITY_REPORT.json"
    ).exists()


def test_render_quality_check_blocks_render_dir_drift(tmp_path):
    from tools.render_quality_check import run_render_quality_check

    fixture = _contracts(tmp_path, run_id="RUN001")
    manifest = fixture["payloads"]["render_manifest"]
    old_render_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN000"
    old_render_dir.mkdir(parents=True)
    manifest["render_dir_rel_project"] = old_render_dir.relative_to(tmp_path).as_posix()
    manifest["render_dir_abs_resolved"] = str(old_render_dir.resolve())
    manifest["render_dir"] = str(old_render_dir.resolve())
    _write_json(fixture["paths"]["render_manifest"], manifest)
    blender = tmp_path / "blender.exe"
    blender.write_text("fake blender", encoding="utf-8")

    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=blender,
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "blocked"
    assert report["run_id"] == "RUN001"
    assert {reason["code"] for reason in report["blocking_reasons"]} >= {
        "render_dir_not_active_run",
    }


def test_render_quality_check_blocks_missing_manifest_render_dir(tmp_path):
    from tools.render_quality_check import run_render_quality_check

    fixture = _contracts(tmp_path, run_id="RUN001")
    manifest = fixture["payloads"]["render_manifest"]
    manifest.pop("render_dir_rel_project", None)
    manifest.pop("render_dir_abs_resolved", None)
    manifest.pop("render_dir", None)
    _write_json(fixture["paths"]["render_manifest"], manifest)
    blender = tmp_path / "blender.exe"
    blender.write_text("fake blender", encoding="utf-8")

    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=blender,
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "render_dir_missing"
    written = json.loads(
        (fixture["run_dir"] / "RENDER_QUALITY_REPORT.json").read_text(encoding="utf-8")
    )
    assert written["status"] == "blocked"


def test_render_quality_check_blocks_render_file_outside_active_render_dir(tmp_path):
    from tools.render_quality_check import run_render_quality_check

    fixture = _contracts(tmp_path, run_id="RUN001")
    other_dir = tmp_path / "cad" / "output" / "renders" / "demo" / "RUN000"
    other_dir.mkdir(parents=True)
    other_file = other_dir / "V1_front.png"
    other_file.write_bytes((fixture["render_dir"] / "V1_front.png").read_bytes())
    manifest = fixture["payloads"]["render_manifest"]
    manifest["files"][0]["path_rel_project"] = other_file.relative_to(tmp_path).as_posix()
    manifest["files"][0]["path_abs_resolved"] = str(other_file.resolve())
    _write_json(fixture["paths"]["render_manifest"], manifest)
    blender = tmp_path / "blender.exe"
    blender.write_text("fake blender", encoding="utf-8")

    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=blender,
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "render_file_outside_render_dir"


def test_render_quality_check_blocks_empty_render_manifest_files(tmp_path):
    from tools.render_quality_check import run_render_quality_check

    fixture = _contracts(tmp_path, run_id="RUN001")
    manifest = fixture["payloads"]["render_manifest"]
    manifest["files"] = []
    _write_json(fixture["paths"]["render_manifest"], manifest)
    blender = tmp_path / "blender.exe"
    blender.write_text("fake blender", encoding="utf-8")

    report = run_render_quality_check(
        tmp_path,
        "demo",
        artifact_index_path=fixture["index_path"],
        blender_path=blender,
        version_runner=_fake_version_runner,
    )

    assert report["status"] == "blocked"
    assert report["render_quality_summary"]["status"] == "blocked"
    assert report["blocking_reasons"][0]["code"] == "render_manifest_empty"


def test_cmd_render_quality_check_writes_report_and_returns_nonzero_when_blocked(
    tmp_path,
    monkeypatch,
):
    import cad_pipeline

    fixture = _contracts(tmp_path, run_id="RUN001")
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_render_quality_check(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            blender=str(tmp_path / "missing.exe"),
            output=None,
        )
    )

    assert rc == 1
    written = json.loads(
        (fixture["run_dir"] / "RENDER_QUALITY_REPORT.json").read_text(encoding="utf-8")
    )
    assert written["status"] == "blocked"
    assert written["blocking_reasons"][0]["code"] == "blender_not_found"
