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


def test_t4_mixed_archive(tmp_path: Path) -> None:
    """T4 — 混合 archive (A + B + 无 subsystem + bool + dict 无 name)。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {
            "a.json": {"subsystem": "old"},  # pattern A → 改
            "b.json": {"subsystem": {"name": "old"}},  # pattern B → 改
            "c.json": {"other": "x"},  # 无 subsystem → skip
            "d.json": {"subsystem": True},  # bool → WARN skip
            "e.json": {"subsystem": {"part_prefix": "x"}},  # dict 无 name → WARN
        },
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    assert json.loads((arch / "a.json").read_text(encoding="utf-8"))["subsystem"] == "new"
    assert json.loads((arch / "b.json").read_text(encoding="utf-8"))["subsystem"]["name"] == "new"
    assert json.loads((arch / "c.json").read_text(encoding="utf-8")) == {"other": "x"}
    assert json.loads((arch / "d.json").read_text(encoding="utf-8")) == {"subsystem": True}
    assert "[APPLY]" in cp.stderr  # a + b
    assert "[WARN]" in cp.stderr  # d + e


def test_t5_idempotent_rerun(tmp_path: Path) -> None:
    """T5 — 二次 apply 零写盘。"""
    arch = _make_archive_tempdir(
        tmp_path,
        {"a.json": {"subsystem": "old"}},
    )
    _run(str(arch), "--from", "old", "--to", "new", "--apply")  # 第一次

    sha_before = _sha256(arch / "a.json")
    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")  # 第二次

    assert cp.returncode == 0
    assert _sha256(arch / "a.json") == sha_before  # 零写盘
    assert "no candidates found" in cp.stderr


def test_t6_malformed_json_skip(tmp_path: Path) -> None:
    """T6 — malformed JSON skip + WARN。"""
    arch = _make_archive_tempdir(tmp_path)
    (arch / "bad.json").write_text("{ not json", encoding="utf-8")
    (arch / "good.json").write_text(
        json.dumps({"subsystem": "old"}), encoding="utf-8"
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    assert "[WARN]" in cp.stderr
    assert "invalid JSON" in cp.stderr
    assert json.loads((arch / "good.json").read_text(encoding="utf-8"))["subsystem"] == "new"


def test_t7_archive_dir_pattern_skipped(tmp_path: Path) -> None:
    """T7 — _archive_* 子目录跳过（含 case-sensitive：_archive_ skip / _Archive_ 不 skip — Linux/macOS）。"""
    arch = _make_archive_tempdir(tmp_path)
    # _archive_xxx 子目录
    (arch / "_archive_20260513").mkdir()
    (arch / "_archive_20260513" / "old.json").write_text(
        json.dumps({"subsystem": "old"}), encoding="utf-8"
    )
    # 正常子目录
    (arch / "normal").mkdir()
    (arch / "normal" / "ok.json").write_text(
        json.dumps({"subsystem": "old"}), encoding="utf-8"
    )

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0, cp.stderr
    # _archive_ 子目录未扫
    assert (
        json.loads((arch / "_archive_20260513" / "old.json").read_text(encoding="utf-8"))[
            "subsystem"
        ]
        == "old"
    )
    # 正常子目录改写
    assert (
        json.loads((arch / "normal" / "ok.json").read_text(encoding="utf-8"))["subsystem"]
        == "new"
    )


def test_t8_deny_list_skipped(tmp_path: Path) -> None:
    """T8 — .git/ __pycache__/ 等普适目录跳过。"""
    arch = _make_archive_tempdir(tmp_path)
    for skip_dir in [".git", "__pycache__", "node_modules", ".pytest_cache"]:
        d = arch / skip_dir
        d.mkdir()
        (d / "old.json").write_text(json.dumps({"subsystem": "old"}), encoding="utf-8")

    cp = _run(str(arch), "--from", "old", "--to", "new", "--apply")

    assert cp.returncode == 0
    for skip_dir in [".git", "__pycache__", "node_modules", ".pytest_cache"]:
        data = json.loads((arch / skip_dir / "old.json").read_text(encoding="utf-8"))
        assert data["subsystem"] == "old", f"{skip_dir} 子目录被扫了"


def test_t9_from_equals_to_exit_2(tmp_path: Path) -> None:
    """T9 — --from == --to exit=2。"""
    arch = _make_archive_tempdir(tmp_path)

    cp = _run(str(arch), "--from", "x", "--to", "x", "--apply")

    assert cp.returncode == 2
    assert "must differ" in cp.stderr


def test_t10_archive_dir_not_exist_exit_2(tmp_path: Path) -> None:
    """T10 — archive_dir 不存在 exit=2。"""
    fake = tmp_path / "does_not_exist"

    cp = _run(str(fake), "--from", "a", "--to", "b", "--apply")

    assert cp.returncode == 2
    assert "not a directory" in cp.stderr


def test_t11_control_char_exit_2(tmp_path: Path) -> None:
    """T11 — --from 含控制字符 exit=2。"""
    arch = _make_archive_tempdir(tmp_path)

    cp = _run(str(arch), "--from", "a\x01b", "--to", "new", "--apply")

    assert cp.returncode == 2
    assert "control chars" in cp.stderr
