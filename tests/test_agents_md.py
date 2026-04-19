"""AGENTS.md 生成测试（spec: docs/superpowers/specs/2026-04-19-skills-refactor-design.md v4）。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _REPO_ROOT / "src" / "cad_spec_gen" / "data"


def test_agents_md_contains_all_5_skills():
    """生成的 AGENTS.md 含 5 skill 的 trigger + 项目概述 + 自动生成头。"""
    from scripts.dev_sync import _render_agents_md

    content = _render_agents_md(_DATA_DIR)

    # 5 skill trigger 必须全在
    for trigger in ("/cad-help", "/cad-spec", "/cad-codegen", "/cad-enhance", "/mechdesign"):
        assert trigger in content, f"missing trigger {trigger}"

    # 项目概述
    assert "cad-spec-gen 代理指南" in content
    assert "6 阶段" in content

    # 自动生成头部警示（防手改）
    assert "AUTO-GENERATED" in content


def test_agents_md_deterministic():
    """连跑 2 次 _render_agents_md 字节相等（无 timestamp/git rev）。"""
    from scripts.dev_sync import _render_agents_md

    c1 = _render_agents_md(_DATA_DIR)
    c2 = _render_agents_md(_DATA_DIR)

    assert c1 == c2, "生成函数必须确定性；发现 run-to-run 差异"


def test_agents_md_no_volatile_fields():
    """AGENTS.md 不含 ISO timestamp / git full SHA。"""
    from scripts.dev_sync import _render_agents_md

    content = _render_agents_md(_DATA_DIR)

    # ISO 时间戳（如 2026-04-19T14:32:00）
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", content), \
        "AGENTS.md 不应含 ISO timestamp"

    # Git full SHA（40 字符 hex）
    assert not re.search(r"\b[0-9a-f]{40}\b", content), \
        "AGENTS.md 不应含 40 字符 git sha"
