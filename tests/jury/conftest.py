# tests/jury/conftest.py
"""tests/jury/ 子树 autouse 配置：默认禁用真实 LLM 调用 + 提供 dummy fixture key。"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_llm_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有 jury 测试默认 CAD_JURY_DISABLE_LLM=1，防真发 LLM 烧费。

    需要真发请求的测试通过 enable_llm_for_test fixture opt-in。
    """
    monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")


@pytest.fixture
def enable_llm_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in fixture：测试需要真调 mock urlopen 时清掉 kill switch。"""
    monkeypatch.delenv("CAD_JURY_DISABLE_LLM", raising=False)


@pytest.fixture
def dummy_api_key() -> str:
    """统一 fixture key 形态；禁止 sk-/pk-/gsk_ 前缀避免 GitHub secret scanner 误报。"""
    return "dummy-not-a-real-key"
