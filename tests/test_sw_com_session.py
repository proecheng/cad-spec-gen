"""sw_com_session 单元测试（Part 2c 精简版）。

subprocess 守卫行为的覆盖已转移到 tests/test_sw_com_session_subprocess.py。
本文件只保留与 subprocess 模型无关的基础 invariant：健康初态、
singleton 语义、reset_session 清空状态。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.solidworks.sw_com_session import (
    SwComSession,
    get_session,
    reset_session,
)


class TestSwComSessionBasics:
    def test_new_session_is_healthy(self):
        reset_session()
        s = SwComSession()
        assert s.is_healthy() is True
        assert s._consecutive_failures == 0

    def test_session_has_threading_lock(self):
        s = SwComSession()
        assert hasattr(s, "_lock")
        assert hasattr(s._lock, "acquire")
        assert hasattr(s._lock, "release")

    def test_reset_session_clears_state(self):
        reset_session()
        s = get_session()
        s._consecutive_failures = 2
        s._unhealthy = True
        reset_session()
        s2 = get_session()
        assert s2._consecutive_failures == 0
        assert s2._unhealthy is False


class TestSessionSingleton:
    def test_get_session_returns_singleton(self):
        reset_session()
        s1 = get_session()
        s2 = get_session()
        assert s1 is s2

    def test_reset_session_creates_new_instance(self):
        reset_session()
        s1 = get_session()
        reset_session()
        s2 = get_session()
        assert s1 is not s2
