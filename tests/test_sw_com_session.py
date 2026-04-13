"""sw_com_session 单元测试（v4 决策 #6/#10/#11/#22/#23/#25）。

全部 mock win32com，不依赖真实 SW。
真实 COM 测试在 tests/test_sw_toolbox_integration.py 用 @requires_solidworks。
"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.solidworks.sw_com_session import (
    SwComSession,
    get_session,
    reset_session,
)


class TestSwComSessionBasics:
    """锁、计数器、健康状态。"""

    def test_new_session_is_healthy(self):
        reset_session()
        s = SwComSession()
        assert s.is_healthy() is True
        assert s._convert_count == 0
        assert s._consecutive_failures == 0

    def test_session_has_threading_lock(self):
        """v4 决策 #22: COM 非线程安全，全方法要有 _lock 保护。"""
        s = SwComSession()
        assert hasattr(s, "_lock")
        # threading.Lock() 返回的是 _thread.lock，type() 名不太好测，用 acquire/release 探测
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
    """get_session 返回同一实例；reset_session 清空 singleton。"""

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


class TestConvertSldprtToStep:
    """v4 决策 #6/#23: 熔断器 + atomic write 校验。"""

    @pytest.fixture
    def mock_app(self):
        """Mock win32com Dispatch 对象 + OpenDoc6/SaveAs3/CloseDoc。"""
        app = mock.MagicMock()
        app.OpenDoc6 = mock.MagicMock(return_value=(mock.MagicMock(), 0, 0))
        app.CloseDoc = mock.MagicMock()
        return app

    def test_atomic_write_success(self, tmp_path, mock_app, monkeypatch):
        """成功路径：生成的 STEP 大小 > MIN 且以 ISO-10303 开头。"""
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        s._app = mock_app

        step_out = tmp_path / "out.step"

        def fake_saveas(path, *args, **kwargs):
            Path(path).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return True

        model = mock_app.OpenDoc6.return_value[0]
        model.Extension.SaveAs3.side_effect = lambda path, *a, **kw: (
            fake_saveas(path, *a, **kw),
            0,
            0,
        )[0]
        model.GetTitle.return_value = "hex bolt"

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(step_out),
        )
        assert ok is True
        assert step_out.exists()
        assert step_out.read_bytes().startswith(b"ISO-10303")

    def test_atomic_write_rejects_small_file(self, tmp_path, mock_app):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        s._app = mock_app

        step_out = tmp_path / "out.step"
        model = mock_app.OpenDoc6.return_value[0]
        model.Extension.SaveAs3.side_effect = lambda path, *a, **kw: (
            Path(path).write_bytes(b"tiny"),
            0,
            0,
        )[0]
        model.GetTitle.return_value = "hex bolt"

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(step_out),
        )
        assert ok is False
        assert not step_out.exists()

    def test_atomic_write_rejects_wrong_magic(self, tmp_path, mock_app):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        s._app = mock_app
        step_out = tmp_path / "out.step"
        model = mock_app.OpenDoc6.return_value[0]
        model.Extension.SaveAs3.side_effect = lambda path, *a, **kw: (
            Path(path).write_bytes(b"BINARY_GARBAGE" + b"X" * 2000),
            0,
            0,
        )[0]
        model.GetTitle.return_value = "hex bolt"

        ok = s.convert_sldprt_to_step(
            str(tmp_path / "hex bolt.sldprt"),
            str(step_out),
        )
        assert ok is False
        assert not step_out.exists()

    def test_circuit_breaker_trips_at_threshold(self, tmp_path, mock_app):
        """v4 决策 #6: 连续 3 次失败 → _unhealthy=True。"""
        from adapters.solidworks.sw_com_session import (
            SwComSession,
            CIRCUIT_BREAKER_THRESHOLD,
            reset_session,
        )

        reset_session()
        s = SwComSession()
        s._app = mock_app
        mock_app.OpenDoc6.side_effect = RuntimeError("COM crashed")

        for _ in range(CIRCUIT_BREAKER_THRESHOLD):
            s.convert_sldprt_to_step(
                str(tmp_path / "x.sldprt"),
                str(tmp_path / "x.step"),
            )

        assert s._unhealthy is True
        assert s.is_healthy() is False

    def test_success_resets_failure_counter(self, tmp_path, mock_app):
        from adapters.solidworks.sw_com_session import SwComSession, reset_session

        reset_session()
        s = SwComSession()
        s._app = mock_app
        s._consecutive_failures = 2

        # Success case
        model = mock_app.OpenDoc6.return_value[0]

        def fake_saveas(path, *a, **kw):
            Path(path).write_bytes(b"ISO-10303-214\n" + b"X" * 2000)
            return True

        model.Extension.SaveAs3.side_effect = lambda path, *a, **kw: (
            fake_saveas(path, *a, **kw),
            0,
            0,
        )[0]
        model.GetTitle.return_value = "x"

        s.convert_sldprt_to_step(
            str(tmp_path / "x.sldprt"),
            str(tmp_path / "x.step"),
        )
        assert s._consecutive_failures == 0
