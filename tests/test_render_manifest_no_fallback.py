import json
from types import SimpleNamespace
from unittest import mock

import cad_pipeline


def test_require_render_manifest_rejects_explicit_dir_without_fallback(tmp_path):
    from tools.render_qa import require_render_manifest

    explicit_dir = tmp_path / "custom_renders"
    explicit_dir.mkdir()

    try:
        require_render_manifest(explicit_dir, explicit=True)
    except FileNotFoundError as exc:
        assert "render_manifest.json" in str(exc)
    else:
        raise AssertionError("explicit render dir without manifest must fail")


def test_cmd_enhance_explicit_dir_missing_manifest_does_not_use_default(tmp_path, monkeypatch):
    explicit_dir = tmp_path / "explicit"
    default_dir = tmp_path / "cad" / "output" / "renders"
    explicit_dir.mkdir(parents=True)
    default_dir.mkdir(parents=True)
    (explicit_dir / "V1_explicit.png").write_bytes(b"not a real png")
    (default_dir / "render_manifest.json").write_text(
        json.dumps({"subsystem": "demo", "files": [str(default_dir / "V1_old.png")]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cad_pipeline, "DEFAULT_OUTPUT", str(tmp_path / "cad" / "output"))
    monkeypatch.setattr(cad_pipeline, "_load_pipeline_config", lambda: {"enhance": {"backend": "engineering"}})

    with mock.patch("cad_pipeline.get_subsystem_dir", return_value=None), mock.patch(
        "engineering_enhancer.enhance_image",
        side_effect=AssertionError("enhance must not run when explicit manifest is missing"),
    ):
        rc = cad_pipeline.cmd_enhance(
            SimpleNamespace(
                subsystem=None,
                dir=str(explicit_dir),
                backend="engineering",
                labeled=False,
                model=None,
                dry_run=False,
            )
        )

    assert rc == 1


def test_cmd_enhance_blocks_manifest_with_failed_render_qa(tmp_path, monkeypatch):
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    png = explicit_dir / "V1_blank.png"
    png.write_bytes(b"not a real png")
    (explicit_dir / "render_manifest.json").write_text(
        json.dumps({
            "schema_version": 2,
            "subsystem": "demo",
            "status": "blocked",
            "files": [{
                "path_abs_resolved": str(png),
                "qa": {"passed": False, "reasons": ["blank_image"]},
            }],
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(cad_pipeline, "_load_pipeline_config", lambda: {"enhance": {"backend": "engineering"}})

    with mock.patch("cad_pipeline.get_subsystem_dir", return_value=None), mock.patch(
        "engineering_enhancer.enhance_image",
        side_effect=AssertionError("enhance must not run when manifest QA failed"),
    ):
        rc = cad_pipeline.cmd_enhance(
            SimpleNamespace(
                subsystem=None,
                dir=str(explicit_dir),
                backend="engineering",
                labeled=False,
                model=None,
                dry_run=False,
            )
        )

    assert rc == 1


def test_cmd_annotate_explicit_dir_missing_manifest_does_not_use_default(tmp_path, monkeypatch):
    explicit_dir = tmp_path / "explicit"
    default_dir = tmp_path / "cad" / "output" / "renders"
    sub_dir = tmp_path / "cad" / "demo"
    explicit_dir.mkdir(parents=True)
    default_dir.mkdir(parents=True)
    sub_dir.mkdir(parents=True)
    config = sub_dir / "render_config.json"
    config.write_text("{}", encoding="utf-8")
    (default_dir / "render_manifest.json").write_text(
        json.dumps({"subsystem": "demo", "files": [str(default_dir / "V1_old.png")]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cad_pipeline, "DEFAULT_OUTPUT", str(tmp_path / "cad" / "output"))
    monkeypatch.setattr(cad_pipeline, "SKILL_ROOT", str(tmp_path))
    (tmp_path / "annotate_render.py").write_text("# fake\n", encoding="utf-8")

    with mock.patch("cad_pipeline.get_subsystem_dir", return_value=str(sub_dir)), mock.patch(
        "cad_pipeline._run_subprocess",
        side_effect=AssertionError("annotate must not run when explicit manifest is missing"),
    ):
        rc = cad_pipeline.cmd_annotate(
            SimpleNamespace(
                subsystem="demo",
                config=str(config),
                dir=str(explicit_dir),
                lang="cn",
                dry_run=False,
            )
        )

    assert rc == 1
