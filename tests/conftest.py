# tests/conftest.py
"""Pytest configuration for cad-spec-gen tests.

This conftest installs an autouse fixture that redirects ~/.cad-spec-gen/
to a per-test tmp_path, with a hash-based tripwire that fails loudly if
any test bypasses the redirect and modifies the real user home.

Why a hash instead of mtime: NTFS/FAT have ~1-second mtime resolution,
so two tests finishing in the same second can race an mtime check.
A hash over (rel_path, size, mtime) tuples for every file catches any
content mutation regardless of timestamp resolution.
"""
import hashlib
import os
import sys
from pathlib import Path

import pytest

# Ensure src/ is on sys.path BEFORE pytest collects tests, to avoid
# shadowing from top-level cad_spec_gen.py script.
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _dir_state_hash(path: Path) -> str | None:
    """Return a stable hash of a directory's contents, or None if missing."""
    if not path.exists():
        return None
    parts = []
    for p in sorted(path.rglob("*")):
        if p.is_file():
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(path).as_posix()
            parts.append(f"{rel}|{st.st_size}|{st.st_mtime_ns}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# Captured ONCE at conftest import time (before any test runs).
_REAL_HOME_CAD_DIR = Path.home() / ".cad-spec-gen"
_REAL_HOME_HASH_AT_START = _dir_state_hash(_REAL_HOME_CAD_DIR)


@pytest.fixture(autouse=True, scope="function")
def isolate_cad_spec_gen_home(monkeypatch, tmp_path):
    """Redirect ~/.cad-spec-gen to tmp_path for every test.

    Tripwire (teardown): fail loudly if real user home's .cad-spec-gen
    directory state changed during the test.
    """
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True)
    (fake_home / ".cad-spec-gen").mkdir()
    monkeypatch.setenv("CAD_SPEC_GEN_HOME", str(fake_home / ".cad-spec-gen"))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    yield

    current_hash = _dir_state_hash(_REAL_HOME_CAD_DIR)
    assert current_hash == _REAL_HOME_HASH_AT_START, (
        f"Real {_REAL_HOME_CAD_DIR} was modified during test.\n"
        f"  Before: {_REAL_HOME_HASH_AT_START}\n"
        f"  After:  {current_hash}\n"
        f"A code path bypassed the HOME monkeypatch — fixture breach!"
    )
