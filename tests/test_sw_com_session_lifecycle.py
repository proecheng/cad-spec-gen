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


class TestConvertAutoStart:
    """convert 入口发现 _app is None 时自动触发 _start_locked。"""

    def test_convert_triggers_start_when_app_none(self, tmp_path):
        """首次 convert 应自动冷启动。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        fake_app = mock.MagicMock()
        fake_app.LoadAddIn.return_value = 1
        # 让 _do_convert 走完但直接返回 False（不关心几何）
        # 触发路径关键：start 被调用 → _app 被赋值
        dispatch_mock = mock.MagicMock(return_value=fake_app)

        with mock.patch.object(sw_com_session, "_com_dispatch", dispatch_mock):
            # _do_convert 在 OpenDoc6 上会进一步操作 fake_app，我们只关心 start 被触发
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"

            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        dispatch_mock.assert_called_once_with("SldWorks.Application")
        assert sess._app is fake_app

    def test_convert_does_not_restart_when_already_running(self, tmp_path):
        """_app 已初始化时不应重新调用 Dispatch。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        fake_app = mock.MagicMock()
        fake_app.LoadAddIn.return_value = 1
        sess._app = fake_app  # 模拟已启动

        dispatch_mock = mock.MagicMock()
        with mock.patch.object(sw_com_session, "_com_dispatch", dispatch_mock):
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"
            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        dispatch_mock.assert_not_called()


class TestMaybeRestart:
    """_convert_count 达 RESTART_EVERY_N_CONVERTS 时 shutdown + restart。"""

    def test_restart_fires_at_threshold(self, tmp_path, monkeypatch):
        """convert_count=50 时下次 convert 入口应先 shutdown 再 start。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        old_app = mock.MagicMock()
        new_app = mock.MagicMock()
        new_app.LoadAddIn.return_value = 1
        sess._app = old_app
        sess._convert_count = sw_com_session.RESTART_EVERY_N_CONVERTS  # 触发阈值

        dispatch_mock = mock.MagicMock(return_value=new_app)
        with mock.patch.object(sw_com_session, "_com_dispatch", dispatch_mock):
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"
            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        # old_app 被 ExitApp 过
        old_app.ExitApp.assert_called_once()
        # 重新 Dispatch 产出了 new_app
        dispatch_mock.assert_called_once_with("SldWorks.Application")
        assert sess._app is new_app
        # _convert_count 重置
        assert sess._convert_count <= 1  # 可能 +1（看 _do_convert 是否成功）

    def test_no_restart_below_threshold(self, tmp_path):
        """count 未达阈值时不触发 restart。"""
        from adapters.solidworks import sw_com_session

        sw_com_session.reset_session()
        sess = sw_com_session.get_session()

        app = mock.MagicMock()
        app.LoadAddIn.return_value = 1
        sess._app = app
        sess._convert_count = sw_com_session.RESTART_EVERY_N_CONVERTS - 1

        with mock.patch.object(sw_com_session, "_com_dispatch", mock.MagicMock()):
            sldprt = tmp_path / "fake.sldprt"
            sldprt.write_bytes(b"")
            step_out = tmp_path / "out.step"
            sess.convert_sldprt_to_step(str(sldprt), str(step_out))

        app.ExitApp.assert_not_called()
