"""adapters/solidworks/sw_convert_worker.py 的单元测试。

全部 mock win32com/pythoncom，不依赖真实 SW。
"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock

import pytest  # noqa: F401  # pytest fixtures 由 pytest 框架注入，ruff 误报 unused

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestWorkerUsage:
    def test_main_missing_args_returns_64(self, capsys):
        from adapters.solidworks import sw_convert_worker

        rc = sw_convert_worker.main([])
        assert rc == 64
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower()

    def test_main_one_arg_returns_64(self, capsys):
        from adapters.solidworks import sw_convert_worker

        rc = sw_convert_worker.main(["only_one"])
        assert rc == 64


class TestWorkerConvert:
    """_convert 的退出码契约；全部 mock pythoncom + Dispatch。"""

    def _patch_com(self, monkeypatch, *, dispatch_return=None, dispatch_raises=None):
        """安装 pythoncom + win32com.client 的 fake 模块。返回 fake_app 给测试控制 side effects。"""
        fake_pythoncom = mock.MagicMock()
        fake_pythoncom.VT_BYREF = 0x4000
        fake_pythoncom.VT_I4 = 3
        fake_pythoncom.VT_DISPATCH = 9

        fake_win32com_client = mock.MagicMock()

        if dispatch_raises is not None:
            fake_win32com_client.Dispatch.side_effect = dispatch_raises
        else:
            fake_app = dispatch_return or mock.MagicMock()
            fake_win32com_client.Dispatch.return_value = fake_app

        # VARIANT 的 mock：每次构造返回一个有 .value 属性的对象，初值为传入的 initial
        def fake_variant(vartype, initial):
            v = mock.MagicMock()
            v.value = initial
            return v

        fake_win32com_client.VARIANT.side_effect = fake_variant

        monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
        monkeypatch.setitem(sys.modules, "win32com.client", fake_win32com_client)
        return (
            fake_win32com_client.Dispatch.return_value
            if dispatch_raises is None
            else None
        )

    def test_opendoc6_errors_returns_2(self, monkeypatch, capsys):
        """OpenDoc6 调用后 err_var.value 非 0 → exit 2。"""
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        def opendoc_sets_error(sldprt, doctype, opts, cfg, err_v, warn_v):
            err_v.value = 256  # swFileLoadError
            return mock.MagicMock()  # non-None model

        fake_app.OpenDoc6.side_effect = opendoc_sets_error

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 2
        assert "OpenDoc6 errors=256" in capsys.readouterr().err

    def test_saveas3_saved_false_returns_3(self, monkeypatch, capsys):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model  # err_v.value 保持 0 → OpenDoc6 通过
        model.Extension.SaveAs3.return_value = False  # saved=False

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 3
        assert "SaveAs3 saved=False" in capsys.readouterr().err

    def test_saveas3_success_returns_0(self, monkeypatch):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model
        model.Extension.SaveAs3.return_value = True  # saved=True，err2 默认 0

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 0
        fake_app.ExitApp.assert_called_once()

    def test_dispatch_exception_returns_4(self, monkeypatch, capsys):
        from adapters.solidworks import sw_convert_worker

        self._patch_com(monkeypatch, dispatch_raises=RuntimeError("COM unavailable"))

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 4
        assert "Dispatch failed" in capsys.readouterr().err
