"""Codex skill registration contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"


def _prefer_src_package():
    """Ensure imports resolve to src/cad_spec_gen, not root cad_spec_gen.py."""
    if str(_SRC) in sys.path:
        sys.path.remove(str(_SRC))
    sys.path.insert(0, str(_SRC))
    if (
        "cad_spec_gen" in sys.modules
        and not hasattr(sys.modules["cad_spec_gen"], "__path__")
    ):
        del sys.modules["cad_spec_gen"]


_prefer_src_package()


@pytest.fixture(autouse=True)
def _src_package_imports():
    _prefer_src_package()


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    return text[: end + 5]


def test_register_skill_codex_mode_writes_global_skill_without_claude_commands(tmp_path):
    from cad_spec_gen.wizard import skill_register

    target = tmp_path / "project"
    codex_dir = tmp_path / "codex-skills"

    count = skill_register.register_skill(
        target,
        lang="zh",
        version="0.test",
        agent="codex",
        codex_dir=codex_dir,
    )

    skill_md = codex_dir / "cad-codegen" / "SKILL.md"
    assert skill_md.exists()
    assert not (target / ".claude" / "commands").exists()
    assert (target / "cad_pipeline.py").exists()
    assert (target / "tools" / "sw_toolbox_e2e.py").exists()
    assert count > 0

    text = skill_md.read_text(encoding="utf-8")
    frontmatter = _frontmatter(text)
    assert "name: cad-codegen" in frontmatter
    assert "description: Use when " in frontmatter
    assert len(frontmatter) < 1024
    assert "Codex usage" in text
    assert "python cad_pipeline.py codegen" in text
    assert "$ARGUMENTS" not in text

    help_text = (codex_dir / "cad-help" / "SKILL.md").read_text(encoding="utf-8")
    assert "sw-export-plan" in help_text
    assert "sw_export_plan.json" in help_text


def test_register_skill_both_mode_writes_claude_commands_and_codex_skills(tmp_path):
    from cad_spec_gen.wizard import skill_register

    target = tmp_path / "project"
    codex_dir = tmp_path / "codex-skills"

    skill_register.register_skill(
        target,
        lang="en",
        version="0.test",
        agent="both",
        codex_dir=codex_dir,
    )

    assert (target / ".claude" / "commands" / "cad-codegen.md").exists()
    assert (codex_dir / "cad-codegen" / "SKILL.md").exists()


def test_cad_skill_setup_passes_agent_and_codex_dir_to_wizard(monkeypatch, tmp_path):
    from cad_spec_gen import cli
    from cad_spec_gen.wizard import wizard

    captured = {}

    def fake_run_wizard(**kwargs):
        captured.update(kwargs)
        return 7

    monkeypatch.setattr(wizard, "run_wizard", fake_run_wizard)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cad-skill-setup",
            "--lang",
            "zh",
            "--target",
            ".",
            "--skip-deps",
            "--agent",
            "codex",
            "--codex-dir",
            str(tmp_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main_setup()

    assert exc.value.code == 7
    assert captured["agent"] == "codex"
    assert captured["codex_dir"] == str(tmp_path)
