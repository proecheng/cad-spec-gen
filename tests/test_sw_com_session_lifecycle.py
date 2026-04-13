"""SwComSession Part 2 生命周期测试（v4 决策 #10/#11）。"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestStartLocked:
    """`_start_locked` 是 `convert` 内部 _app 未初始化时的懒加载入口。"""

    def test_start_locked_sets_app_on_success(self):
        """成功冷启动：Dispatch → Visible/UserControl=False → LoadAddIn 成功。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        fake_app = mock.MagicMock()
        fake_app.LoadAddIn.return_value = 1  # SW LoadAddIn 成功返回 1
        fake_dispatch = mock.MagicMock(return_value=fake_app)

        with mock.patch.object(sw_com_session, "_com_dispatch", fake_dispatch):
            with sess._lock:
                sess._start_locked()

        assert sess._app is fake_app
        assert sess._unhealthy is False
        fake_app.LoadAddIn.assert_called_once_with("SOLIDWORKS Toolbox")
        assert fake_app.Visible is False
        assert fake_app.UserControl is False

    def test_start_locked_marks_unhealthy_on_dispatch_failure(self):
        """Dispatch 失败（SW 未安装/启动失败） → _unhealthy=True。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        def fake_dispatch(_prog_id):
            raise RuntimeError("COM Dispatch failed")

        with mock.patch.object(sw_com_session, "_com_dispatch", fake_dispatch):
            with sess._lock:
                with pytest.raises(RuntimeError, match="COM Dispatch failed"):
                    sess._start_locked()

        assert sess._unhealthy is True
        assert sess._app is None

    def test_start_locked_marks_unhealthy_on_loadaddin_failure(self):
        """LoadAddIn 返回 0 → _unhealthy=True + 提示 Tools→Add-Ins 勾选。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        fake_app = mock.MagicMock()
        fake_app.LoadAddIn.return_value = 0  # 失败

        with mock.patch.object(
            sw_com_session, "_com_dispatch", mock.MagicMock(return_value=fake_app)
        ):
            with sess._lock:
                with pytest.raises(RuntimeError, match="Tools → Add-Ins"):
                    sess._start_locked()

        assert sess._unhealthy is True
        assert sess._app is None
