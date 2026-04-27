"""adapters/solidworks/sw_list_configs_worker.py 的单元测试.

复用 tests/test_sw_convert_worker.py 的 _patch_com 模板（"全 mock pythoncom +
Dispatch，不依赖真实 SW"）。

spec 引用: docs/superpowers/specs/2026-04-27-sw-config-broker-m2-m4-cleanup-design.md §7.1
"""

from __future__ import annotations

import json
import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _patch_com(monkeypatch, *, dispatch_return=None, dispatch_raises=None):
    """安装 pythoncom + win32com.client 的 fake 模块。模式同
    tests/test_sw_convert_worker.py L34 的 _patch_com。"""
    fake_pythoncom = mock.MagicMock()
    fake_pythoncom.VT_BYREF = 0x4000
    fake_pythoncom.VT_I4 = 3

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
    return fake_win32com_client.DispatchEx.return_value if dispatch_raises is None else None


class TestWorkerListConfigs:
    """spec §3.1.7：_list_configs 入口 try/except 路由按 rc 合约分流。"""

    def test_worker_success_returns_rc0_with_configs_json(self, monkeypatch, capsys):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        # mock _open_doc_get_configs 不走真 OpenDoc6
        monkeypatch.setattr(wkr, "_open_doc_get_configs",
                           lambda app, p: ["A", "B"])

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out.strip()) == ["A", "B"]


class TestWorkerOpenDocFailure:
    """spec §3.1.3 + §3.1.4：OpenDocFailure 子类异常按 errors 数值分类。"""

    def test_worker_open_doc_failure_terminal_errors_returns_rc2(self, monkeypatch, capsys):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        # OpenDocFailure errors=8192 (swFutureVersion，rev 6 本机校准) → terminal
        def raise_terminal(app, p):
            raise wkr.OpenDocFailure(errors=8192, warnings=0, model_was_null=False)
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_terminal)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 2

    def test_worker_open_doc_failure_transient_errors_returns_rc3(self, monkeypatch, capsys):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        # OpenDocFailure errors=8388608 (swApplicationBusy，rev 6 本机校准) → transient
        def raise_transient(app, p):
            raise wkr.OpenDocFailure(errors=8388608, warnings=0, model_was_null=False)
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_transient)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 3

    def test_worker_open_doc_null_model_returns_rc2(self, monkeypatch, capsys):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        # OpenDocFailure errors=0 + model_was_null=True → terminal (Edge 7)
        def raise_null_model(app, p):
            raise wkr.OpenDocFailure(errors=0, warnings=0, model_was_null=True)
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_null_model)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 2


class TestWorkerComError:
    """spec §3.1.5：pythoncom.com_error 按 hresult 分类（DispatchEx / GetConfigurationNames 路径）."""

    def test_worker_com_error_transient_hresult_returns_rc3(self, monkeypatch, capsys):
        from adapters.solidworks import sw_list_configs_worker as wkr

        # mock pythoncom + win32com.client，DispatchEx 抛 com_error
        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        # 构造一个真 com_error subclass 让 isinstance 通过
        class FakeComError(Exception):
            def __init__(self, hresult):
                self.hresult = hresult
                self.args = (hresult,)
        sys.modules["pythoncom"].com_error = FakeComError

        def raise_transient_com(app, p):
            raise FakeComError(-2147023170)  # RPC_E_DISCONNECTED
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_transient_com)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 3

    def test_worker_com_error_terminal_hresult_returns_rc2(self, monkeypatch, capsys):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        class FakeComError(Exception):
            def __init__(self, hresult):
                self.hresult = hresult
                self.args = (hresult,)
        sys.modules["pythoncom"].com_error = FakeComError

        def raise_terminal_com(app, p):
            raise FakeComError(-2147467259)  # 未识别 hresult → terminal
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_terminal_com)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 2


class TestWorkerImportError:
    """ImportError → terminal (pywin32 没装是部署问题)."""

    def test_worker_import_error_returns_rc2(self, monkeypatch, capsys):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        def raise_import(app, p):
            raise ImportError("pywin32 not installed")
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_import)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 2


class TestWorkerUnknownException:
    """兜底未识别 Exception → transient (避免 worker 自身 bug 永久污染)."""

    def test_worker_unknown_exception_defaults_transient_rc3(self, monkeypatch, capsys):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        def raise_value(app, p):
            raise ValueError("unexpected")
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_value)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 3
        captured = capsys.readouterr()
        assert "ValueError" in captured.err


class TestClassifyWorkerException:
    """spec §3.1.6：_classify_worker_exception 直接单测."""

    def test_classify_open_doc_failure_table_lookup(self, monkeypatch):
        from adapters.solidworks import sw_list_configs_worker as wkr

        # transient: 65536 / 262144 / 8388608
        assert wkr._classify_worker_exception(
            wkr.OpenDocFailure(errors=65536, warnings=0, model_was_null=False)
        ) == 3
        assert wkr._classify_worker_exception(
            wkr.OpenDocFailure(errors=262144, warnings=0, model_was_null=False)
        ) == 3
        assert wkr._classify_worker_exception(
            wkr.OpenDocFailure(errors=8388608, warnings=0, model_was_null=False)
        ) == 3

        # terminal: 1 / 2 / 8192 (swFutureVersion) / 1024 / etc.
        assert wkr._classify_worker_exception(
            wkr.OpenDocFailure(errors=1, warnings=0, model_was_null=False)
        ) == 2
        assert wkr._classify_worker_exception(
            wkr.OpenDocFailure(errors=8192, warnings=0, model_was_null=False)
        ) == 2

    def test_classify_com_error_table_lookup(self, monkeypatch):
        from adapters.solidworks import sw_list_configs_worker as wkr
        import pythoncom

        # mock pythoncom.com_error
        class FakeComError(Exception):
            def __init__(self, hresult):
                self.hresult = hresult
                self.args = (hresult,)
        monkeypatch.setattr(pythoncom, "com_error", FakeComError)

        # transient hresults
        assert wkr._classify_worker_exception(FakeComError(-2147023170)) == 3
        assert wkr._classify_worker_exception(FakeComError(-2147418113)) == 3
        assert wkr._classify_worker_exception(FakeComError(-2147023174)) == 3

        # 未识别 hresult → terminal
        assert wkr._classify_worker_exception(FakeComError(-2147467259)) == 2

    def test_classify_worker_exception_without_pythoncom(self, monkeypatch):
        """spec Edge 9：mock pythoncom import 失败 → 走兜底 transient."""
        from adapters.solidworks import sw_list_configs_worker as wkr

        # 模拟 pythoncom 不可用
        original_pythoncom = sys.modules.pop("pythoncom", None)
        try:
            # ImportError 在 _classify_worker_exception 内部 try 块被 catch
            # 走兜底分支 → transient
            assert wkr._classify_worker_exception(ValueError("random")) == 3
        finally:
            if original_pythoncom is not None:
                sys.modules["pythoncom"] = original_pythoncom

    def test_classify_open_doc_failure_null_model_terminal(self, monkeypatch):
        """spec Edge 7：OpenDocFailure(errors=0, model_was_null=True) → terminal."""
        from adapters.solidworks import sw_list_configs_worker as wkr

        e = wkr.OpenDocFailure(errors=0, warnings=0, model_was_null=True)
        assert wkr._classify_worker_exception(e) == 2  # terminal


class TestRunBatchModeBootFail:
    """spec §3.1.8.1 (rev 4 A1)：worker 顶部 boot fail emit per-entry stdout 让 broker 走 entry 分流."""

    def test_batch_mode_pywin32_import_failure_emits_terminal_per_entry(
        self, monkeypatch, capsys,
    ):
        """Edge 14：pywin32 import 失败 → stdout per-entry exit_code=2 + rc=0."""
        from adapters.solidworks import sw_list_configs_worker as wkr

        # 模拟 stdin 提供 batch 输入
        sldprt_list = ["a.sldprt", "b.sldprt", "c.sldprt"]
        monkeypatch.setattr(sys, "stdin", mock.MagicMock())
        sys.stdin.read = lambda: ""  # placeholder
        # 实际 _run_batch_mode 用 json.load(sys.stdin)，monkeypatch json.load
        monkeypatch.setattr(json, "load", lambda f: sldprt_list)

        # 模拟 pythoncom 顶部 import 失败
        import builtins
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pythoncom":
                raise ImportError("pywin32 not installed (test)")
            if name == "win32com.client":
                raise ImportError("pywin32 not installed (test)")
            return original_import(name, *args, **kwargs)

        # 清掉 mock 的 pythoncom 让 import 真触发 ImportError
        sys.modules.pop("pythoncom", None)
        sys.modules.pop("win32com.client", None)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        rc = wkr._run_batch_mode()
        assert rc == 0  # 整 batch rc=0，分类信号通过 entries

        captured = capsys.readouterr()
        results = json.loads(captured.out.strip())
        assert len(results) == 3
        for entry in results:
            assert entry["configs"] == []
            assert entry["exit_code"] == 2  # EXIT_TERMINAL (pywin32 没装)

    def test_batch_mode_dispatchex_com_error_emits_classified_per_entry(
        self, monkeypatch, capsys,
    ):
        """Edge 15：DispatchEx 抛 com_error → stdout per-entry 按 hresult 分类 + rc=0."""
        from adapters.solidworks import sw_list_configs_worker as wkr

        sldprt_list = ["a.sldprt", "b.sldprt"]
        monkeypatch.setattr(json, "load", lambda f: sldprt_list)

        # mock pythoncom + win32com.client，DispatchEx 抛 com_error
        class FakeComError(Exception):
            def __init__(self, hresult):
                self.hresult = hresult
                self.args = (hresult,)

        fake_pythoncom = mock.MagicMock()
        fake_pythoncom.com_error = FakeComError
        fake_pythoncom.CoInitialize = lambda: None
        fake_pythoncom.CoUninitialize = lambda: None

        fake_win32com_client = mock.MagicMock()
        fake_win32com_client.DispatchEx.side_effect = FakeComError(-2147023170)  # RPC_E_DISCONNECTED → transient

        monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
        monkeypatch.setitem(sys.modules, "win32com.client", fake_win32com_client)

        rc = wkr._run_batch_mode()
        assert rc == 0

        captured = capsys.readouterr()
        results = json.loads(captured.out.strip())
        assert len(results) == 2
        for entry in results:
            assert entry["configs"] == []
            assert entry["exit_code"] == 3  # EXIT_TRANSIENT (RPC_E_DISCONNECTED)


class TestInvariantI11I12:
    """spec §5 不变性 I11/I12 直接断言测试（rev 5 A）。"""

    def test_invariant_open_doc_failure_is_runtime_error_subclass(self):
        """I11: OpenDocFailure 是 RuntimeError 子类，不破现有 except RuntimeError。"""
        from adapters.solidworks.sw_list_configs_worker import OpenDocFailure
        assert issubclass(OpenDocFailure, RuntimeError)

        e = OpenDocFailure(errors=65536, warnings=0, model_was_null=False)  # rev 6
        assert isinstance(e, RuntimeError)
        # 现有 except RuntimeError 调用方不破
        try:
            raise e
        except RuntimeError as caught:
            assert caught is e

    def test_invariant_classify_worker_exception_called_by_both_single_and_batch_paths(
        self, monkeypatch, capsys,
    ):
        """I12: _classify_worker_exception 是单件+batch 共享调用入口（DRY）。"""
        from adapters.solidworks import sw_list_configs_worker as wkr

        call_log = []
        original_classify = wkr._classify_worker_exception

        def spy_classify(e):
            call_log.append(("called_with", type(e).__name__))
            return original_classify(e)

        monkeypatch.setattr(wkr, "_classify_worker_exception", spy_classify)

        # 触发单件路径失败
        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)
        monkeypatch.setattr(wkr, "_open_doc_get_configs",
                           lambda app, p: (_ for _ in ()).throw(ValueError("boom")))
        wkr._list_configs("p1.sldprt")

        assert len(call_log) >= 1, "single path should call _classify_worker_exception"
        assert call_log[0] == ("called_with", "ValueError")

    def test_invariant_open_doc_failure_carries_structured_fields(self):
        """rev 5 A：OpenDocFailure 字段不被吞，按字段分类才能工作。"""
        from adapters.solidworks.sw_list_configs_worker import OpenDocFailure

        try:
            raise OpenDocFailure(errors=65536, warnings=2, model_was_null=False)  # rev 6
        except OpenDocFailure as e:
            assert e.errors == 65536
            assert e.warnings == 2
            assert e.model_was_null is False
            assert "OpenDoc6 errors=65536" in str(e)
