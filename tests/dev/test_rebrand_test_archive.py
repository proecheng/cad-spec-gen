"""tests/dev/test_rebrand_test_archive.py — §11-N1 rebrand 工具 TDD 套件。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.dev.conftest import _make_archive_tempdir

_TOOL = "tools/dev/rebrand_test_archive.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """执行工具，cwd 默认 repo root。"""
    return subprocess.run(
        [sys.executable, _TOOL, *args],
        capture_output=True,
        text=True,
        cwd=cwd or Path(__file__).resolve().parents[2],
    )


def test_t1_dry_run_does_not_write(tmp_path: Path) -> None:
    """T1 (rev 5 layer 2 角色 3.1 — SHA-256 跨平台精度防御)"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old"}},
    )
    sha_before = _sha256(arch / "a.json")

    cp = _run(str(arch), "--from", "old", "--to", "new")

    assert cp.returncode == 0, cp.stderr
    assert _sha256(arch / "a.json") == sha_before
    assert "[DRY]" in cp.stderr


def test_t2_apply_pattern_a_string(tmp_path: Path) -> None:
    """T2 — pattern A: 顶层 subsystem string 改写。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old", "other": "keep"}},
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "a.json").read_text(encoding="utf-8"))
    assert data["subsystem"] == "new"
    assert data["other"] == "keep"
    assert "[APPLY]" in cp.stderr


def test_t3_apply_pattern_b_dict_nested(tmp_path: Path) -> None:
    """T3 — pattern B: subsystem.name dict-nested 改写（name_cn 保留）。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {
            "b.json": {
                "subsystem": {
                    "name": "old",
                    "name_cn": "保留中文",
                    "part_prefix": "GIS-EE",
                }
            }
        },
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    data = json.loads((arch / "b.json").read_text(encoding="utf-8"))
    assert data["subsystem"]["name"] == "new"
    assert data["subsystem"]["name_cn"] == "保留中文"  # name_cn 不改
    assert data["subsystem"]["part_prefix"] == "GIS-EE"  # 其他字段不改
    assert "[APPLY]" in cp.stderr
