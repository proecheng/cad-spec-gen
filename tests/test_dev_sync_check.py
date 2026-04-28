"""dev_sync --check 契约。"""

from __future__ import annotations

from pathlib import Path


def test_dev_sync_check_mode_reports_drift_without_writing(tmp_path):
    from scripts import dev_sync

    root = tmp_path
    (root / "src" / "cad_spec_gen" / "data").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / ".claude" / "commands").mkdir(parents=True)

    (root / "hatch_build.py").write_text(
        "_PIPELINE_TOOLS = ['tool.py']\nCOPY_DIRS = {}\nTOP_LEVEL_FILES = {}\n",
        encoding="utf-8",
    )
    (root / "tool.py").write_text("new\n", encoding="utf-8")
    mirror = root / "src" / "cad_spec_gen" / "data" / "python_tools" / "tool.py"
    mirror.parent.mkdir(parents=True)
    mirror.write_text("old\n", encoding="utf-8")

    (root / "src" / "cad_spec_gen" / "data" / "skill.json").write_text(
        '{"homepage":"x","version":"1.0.0","requires":{"python":">=3.10"},"skills":[]}',
        encoding="utf-8",
    )

    changed = dev_sync.check(root)

    assert mirror.read_text(encoding="utf-8") == "old\n"
    assert Path(mirror) in changed


def test_dev_sync_check_main_returns_one_on_drift(tmp_path, capsys):
    from scripts import dev_sync

    root = tmp_path
    (root / "src" / "cad_spec_gen" / "data").mkdir(parents=True)
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "hatch_build.py").write_text(
        "_PIPELINE_TOOLS = ['tool.py']\nCOPY_DIRS = {}\nTOP_LEVEL_FILES = {}\n",
        encoding="utf-8",
    )
    (root / "tool.py").write_text("new\n", encoding="utf-8")
    (root / "src" / "cad_spec_gen" / "data" / "skill.json").write_text(
        '{"homepage":"x","version":"1.0.0","requires":{"python":">=3.10"},"skills":[]}',
        encoding="utf-8",
    )

    rc = dev_sync.main(["--check"], root=root)

    assert rc == 1
    assert "out of date" in capsys.readouterr().out
