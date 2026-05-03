import json
from types import SimpleNamespace
from unittest import mock

from PIL import Image, ImageDraw

import cad_pipeline


def _render_png(path, color=(40, 90, 150)):
    image = Image.new("RGB", (256, 256), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 64, 192, 192), fill=color)
    image.save(path)


def test_cmd_render_rejects_successful_blender_run_with_only_old_pngs(tmp_path, monkeypatch):
    render_dir = tmp_path / "cad" / "output" / "renders"
    sub_dir = tmp_path / "cad" / "demo"
    render_dir.mkdir(parents=True)
    sub_dir.mkdir(parents=True)
    (render_dir / "V1_old.png").write_bytes(b"old png")
    stale_manifest = render_dir / "render_manifest.json"
    stale_manifest.write_text(
        json.dumps({"schema_version": 1, "subsystem": "demo", "files": [str(render_dir / "V1_old.png")]}),
        encoding="utf-8",
    )
    stale_content = stale_manifest.read_text(encoding="utf-8")
    (sub_dir / "render_3d.py").write_text("# fake render\n", encoding="utf-8")
    (sub_dir / "render_config.json").write_text(
        json.dumps({"camera": {"V1": {"type": "standard"}}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cad_pipeline, "DEFAULT_OUTPUT", str(tmp_path / "cad" / "output"))

    with mock.patch("cad_pipeline.get_blender_path", return_value=str(tmp_path / "blender.exe")), mock.patch(
        "cad_pipeline.get_subsystem_dir",
        return_value=str(sub_dir),
    ), mock.patch("cad_pipeline._build_blender_env", return_value={}), mock.patch(
        "cad_pipeline._run_subprocess",
        return_value=(True, 0.1),
    ):
        rc = cad_pipeline.cmd_render(
            SimpleNamespace(
                subsystem="demo",
                view="V1",
                timestamp=False,
                output_dir=None,
                dry_run=False,
            )
        )

    assert rc == 1
    assert stale_manifest.read_text(encoding="utf-8") == stale_content


def test_cmd_render_treats_overwritten_png_as_current_run_output(tmp_path, monkeypatch):
    render_dir = tmp_path / "cad" / "output" / "renders"
    sub_dir = tmp_path / "cad" / "demo"
    render_dir.mkdir(parents=True)
    sub_dir.mkdir(parents=True)
    png = render_dir / "V1_front.png"
    _render_png(png, color=(20, 70, 120))
    (sub_dir / "render_3d.py").write_text("# fake render\n", encoding="utf-8")
    (sub_dir / "render_config.json").write_text(
        json.dumps({"camera": {"V1": {"type": "standard"}}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(cad_pipeline, "DEFAULT_OUTPUT", str(tmp_path / "cad" / "output"))

    def fake_run(*_args, **_kwargs):
        _render_png(png, color=(160, 70, 20))
        return True, 0.1

    with mock.patch("cad_pipeline.get_blender_path", return_value=str(tmp_path / "blender.exe")), mock.patch(
        "cad_pipeline.get_subsystem_dir",
        return_value=str(sub_dir),
    ), mock.patch("cad_pipeline._build_blender_env", return_value={}), mock.patch(
        "cad_pipeline._run_subprocess",
        side_effect=fake_run,
    ):
        rc = cad_pipeline.cmd_render(
            SimpleNamespace(
                subsystem="demo",
                view="V1",
                timestamp=False,
                output_dir=None,
                dry_run=False,
            )
        )

    assert rc == 0
    manifest = json.loads((render_dir / "render_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["files"][0]["path_abs_resolved"] == str(png.resolve())
    assert manifest["files"][0]["qa"]["passed"] is True


def test_cmd_render_returns_failure_when_new_render_fails_qa(tmp_path, monkeypatch):
    render_dir = tmp_path / "cad" / "output" / "renders"
    sub_dir = tmp_path / "cad" / "demo"
    render_dir.mkdir(parents=True)
    sub_dir.mkdir(parents=True)
    blank_png = render_dir / "V1_blank.png"
    (sub_dir / "render_3d.py").write_text("# fake render\n", encoding="utf-8")
    (sub_dir / "render_config.json").write_text(
        json.dumps({"camera": {"V1": {"type": "standard"}}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(cad_pipeline, "DEFAULT_OUTPUT", str(tmp_path / "cad" / "output"))

    def fake_run(*_args, **_kwargs):
        Image.new("RGB", (256, 256), (255, 255, 255)).save(blank_png)
        return True, 0.1

    with mock.patch("cad_pipeline.get_blender_path", return_value=str(tmp_path / "blender.exe")), mock.patch(
        "cad_pipeline.get_subsystem_dir",
        return_value=str(sub_dir),
    ), mock.patch("cad_pipeline._build_blender_env", return_value={}), mock.patch(
        "cad_pipeline._run_subprocess",
        side_effect=fake_run,
    ):
        rc = cad_pipeline.cmd_render(
            SimpleNamespace(
                subsystem="demo",
                view="V1",
                timestamp=False,
                output_dir=None,
                dry_run=False,
            )
        )

    assert rc == 1
    manifest = json.loads((render_dir / "render_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "blocked"
    assert manifest["blocking_reasons"][0]["code"] == "render_qa_failed"
