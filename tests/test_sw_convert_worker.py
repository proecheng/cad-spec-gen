"""adapters/solidworks/sw_convert_worker.py 的单元测试。

全部 mock win32com/pythoncom，不依赖真实 SW。
"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock

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
            fake_win32com_client.DispatchEx.side_effect = dispatch_raises
        else:
            fake_app = dispatch_return or mock.MagicMock()
            fake_win32com_client.DispatchEx.return_value = fake_app

        def fake_variant(vartype, initial):
            v = mock.MagicMock()
            v.value = initial
            return v

        fake_win32com_client.VARIANT.side_effect = fake_variant

        monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
        monkeypatch.setitem(sys.modules, "win32com.client", fake_win32com_client)
        return (
            fake_win32com_client.DispatchEx.return_value
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

    def test_opendoc6_null_model_returns_2(self, monkeypatch, capsys):
        """OpenDoc6 errors==0 但返回 null model → 仍 exit 2（分支独立于 errors!=0）。"""
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        # err_var.value 保持 0；但 OpenDoc6 返回 None 表示加载失败
        fake_app.OpenDoc6.return_value = None

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 2
        assert "model=NULL" in capsys.readouterr().err

    def test_saveas3_saved_true_but_errors_returns_3(self, monkeypatch, capsys):
        """SaveAs3 返回 True 但 err2.value!=0（SW 部分保存带错误码）→ exit 3。"""
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model

        def saveas_sets_error(tmp_path, version, options, d1, d2, err_v, warn_v):
            # SaveAs3 签名里 err_v 是第 6 个位置参数（index 5），写 errors
            err_v.value = 4  # 随意非零值
            return True  # saved=True

        model.Extension.SaveAs3.side_effect = saveas_sets_error

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 3
        assert "errors=4" in capsys.readouterr().err

    def test_closedoc_uses_getpathname(self, monkeypatch):
        """CloseDoc 应调用 model.GetPathName()，不调 model.GetTitle()。"""
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        model = mock.MagicMock()
        model.GetPathName.return_value = "C:/SOLIDWORKS Data/part.sldprt"
        fake_app.OpenDoc6.return_value = model
        model.Extension.SaveAs3.return_value = True
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 0
        fake_app.CloseDoc.assert_called_once_with("C:/SOLIDWORKS Data/part.sldprt")

    def test_framestate_set_to_zero(self, monkeypatch):
        """FrameState=0（swWindowMinimized）必须在 OpenDoc6 前设置。"""
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model
        model.Extension.SaveAs3.return_value = True
        self._patch_com(monkeypatch, dispatch_return=fake_app)

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 0
        assert fake_app.FrameState == 0


class TestResolveConfig:
    """_resolve_config 两步匹配：精确 → 模糊。"""

    def test_exact_match_case_insensitive(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        available = ["GB_T70.1-M6x10", "GB_T70.1-M6x20"]
        assert _resolve_config("GB_T70.1-M6x20", available) == "GB_T70.1-M6x20"

    def test_exact_match_case_insensitive_lower(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        available = ["GB_T70.1-M6x20"]
        assert _resolve_config("gb_t70.1-m6x20", available) == "GB_T70.1-M6x20"

    def test_fuzzy_match_strips_dashes(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        available = ["GB_T70.1-M6x20"]
        assert _resolve_config("GB-T70.1-M6x20", available) == "GB_T70.1-M6x20"

    def test_no_match_returns_none(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        available = ["GB_T70.1-M6x10", "GB_T70.1-M6x20"]
        assert _resolve_config("GB_T70.1-M99x99", available) is None

    def test_empty_available_returns_none(self):
        from adapters.solidworks.sw_convert_worker import _resolve_config
        assert _resolve_config("GB_T70.1-M6x20", []) is None


class TestWorkerConfigSwitch:
    """_convert 带 target_config 参数时的 ShowConfiguration2 行为。"""

    def _patch_com(self, monkeypatch, *, dispatch_return=None, dispatch_raises=None):
        """复用 TestWorkerConvert._patch_com 的完全相同实现。"""
        fake_pythoncom = mock.MagicMock()
        fake_pythoncom.VT_BYREF = 0x4000
        fake_pythoncom.VT_I4 = 3
        fake_pythoncom.VT_DISPATCH = 9

        fake_win32com_client = mock.MagicMock()

        if dispatch_raises is not None:
            fake_win32com_client.DispatchEx.side_effect = dispatch_raises
        else:
            fake_app = dispatch_return or mock.MagicMock()
            fake_win32com_client.DispatchEx.return_value = fake_app

        def fake_variant(vartype, initial):
            v = mock.MagicMock()
            v.value = initial
            return v

        fake_win32com_client.VARIANT.side_effect = fake_variant

        monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
        monkeypatch.setitem(sys.modules, "win32com.client", fake_win32com_client)
        return (
            fake_win32com_client.DispatchEx.return_value
            if dispatch_raises is None
            else None
        )

    def _make_model(self, fake_app, config_names):
        """构造带 ConfigurationManager 的 fake model。"""
        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model
        model.Extension.SaveAs3.return_value = True

        fake_cfg_mgr = mock.MagicMock()
        fake_cfg_mgr.GetConfigurationNames.return_value = config_names
        model.ConfigurationManager = fake_cfg_mgr
        return model

    def test_exact_config_match_calls_showconfiguration(self, monkeypatch):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)
        model = self._make_model(fake_app, ["GB_T70.1-M6x10", "GB_T70.1-M6x20"])

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step", "GB_T70.1-M6x20")
        assert rc == 0
        model.ShowConfiguration2.assert_called_once_with("GB_T70.1-M6x20")

    def test_fuzzy_config_match_calls_showconfiguration(self, monkeypatch):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)
        model = self._make_model(fake_app, ["GB_T70.1-M6x20"])

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step", "GB-T70.1-M6x20")
        assert rc == 0
        model.ShowConfiguration2.assert_called_once()

    def test_no_config_match_returns_5(self, monkeypatch, capsys):
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)
        self._make_model(fake_app, ["GB_T70.1-M6x10", "GB_T70.1-M6x20"])

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step", "GB_T70.1-M99x99")
        assert rc == 5
        err = capsys.readouterr().err
        assert "config 未匹配" in err
        assert "GB_T70.1-M99x99" in err

    def test_no_target_config_skips_config_switch(self, monkeypatch):
        """target_config=None 时不调用 GetConfigurationNames 也不调用 ShowConfiguration2。"""
        from adapters.solidworks import sw_convert_worker

        fake_app = mock.MagicMock()
        self._patch_com(monkeypatch, dispatch_return=fake_app)
        model = mock.MagicMock()
        fake_app.OpenDoc6.return_value = model
        model.Extension.SaveAs3.return_value = True

        rc = sw_convert_worker._convert("in.sldprt", "out.tmp.step")
        assert rc == 0
        model.ShowConfiguration2.assert_not_called()

    def test_main_with_three_args(self, monkeypatch, capsys):
        """main([sldprt, tmp, config_name]) 正确解析 argv[2] 并传给 _convert。"""
        from adapters.solidworks import sw_convert_worker

        calls = []

        def fake_convert(sldprt, tmp, cfg=None):
            calls.append(cfg)
            return 0

        monkeypatch.setattr(sw_convert_worker, "_convert", fake_convert)
        rc = sw_convert_worker.main(["a.sldprt", "b.tmp.step", "GB_T70.1-M6x20"])
        assert rc == 0
        assert calls == ["GB_T70.1-M6x20"]

    def test_main_with_four_args_returns_64(self, capsys):
        from adapters.solidworks import sw_convert_worker

        rc = sw_convert_worker.main(["a", "b", "c", "d"])
        assert rc == 64
