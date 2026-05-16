"""tests/dev/conftest.py — rebrand_test_archive 测试共用 fixture。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _make_archive_tempdir(
    tmp_path: Path,
    json_files: dict[str, dict[str, Any]] | None = None,
    *,
    include_marker: bool = True,
) -> Path:
    """tempdir 内 touch .test-archive-marker + 写 JSON 文件。

    rev 5 B1 fix：所有 T1-T14 测试 fixture 必含空 .test-archive-marker；
    T15 例外不 touch marker（专测 sentinel 缺失 exit=2）。

    Args:
        tmp_path: pytest 标准 tmp_path fixture
        json_files: {relpath: dict_content} 映射；None 表示不写 JSON
        include_marker: True touch .test-archive-marker / False 不 touch（T15 用）

    Returns:
        tmp_path（同传入）
    """
    if include_marker:
        (tmp_path / ".test-archive-marker").touch()
    for relpath, content in (json_files or {}).items():
        p = tmp_path / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(content, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return tmp_path


__all__ = ["_make_archive_tempdir"]


_GISBOT_MARKER = Path("D:/Work/cad-tests/GISBOT/.test-archive-marker")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """rev 5 B2+B3 fix — 集成测 conftest skip 检 .test-archive-marker 真值契约。"""
    if _GISBOT_MARKER.is_file():
        return
    skip_reason = pytest.mark.skip(
        reason=(
            f"archive marker missing: run `touch {_GISBOT_MARKER}` to enable"
        )
    )
    for item in items:
        if "requires_test_archive" in item.keywords:
            item.add_marker(skip_reason)
