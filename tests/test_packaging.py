"""Packaging tests for Spec 1 — verify entry points and hatch config."""
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).parent.parent


def test_pyproject_has_cad_lib_entry_point():
    content = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "cad-lib = " in content, "pyproject.toml missing cad-lib entry point"
    assert "cad_spec_gen.cad_lib:main" in content, \
        "Entry point not pointing at cad_spec_gen.cad_lib:main"


def test_pyproject_has_pytest_env_pinned():
    content = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PYTHONHASHSEED=0" in content, "PYTHONHASHSEED not pinned"
