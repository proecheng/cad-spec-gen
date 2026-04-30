"""Compatibility guards for the declared Python >=3.10 support window."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def test_no_python312_only_backslash_fstring_expressions():
    """Backslashes inside f-string expressions require Python 3.12+."""
    repo_root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    pattern = re.compile(r"""(?<![A-Za-z0-9_])f(?P<quote>['"]).*?\{[^}\n]*\\[^}\n]*\}""")
    tracked = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()

    for rel_path in tracked:
        path = repo_root / rel_path
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{rel_path}:{line_no}")

    assert offenders == []
