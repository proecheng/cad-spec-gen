"""adapters/solidworks/sw_list_configs_worker.py 的单元测试.

复用 tests/test_sw_convert_worker.py 的 _patch_com 模板（"全 mock pythoncom +
Dispatch，不依赖真实 SW"）。

spec 引用: docs/superpowers/specs/2026-04-27-sw-config-broker-m2-m4-cleanup-design.md §7.1
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 仅 Windows 平台运行（worker 依赖 pywin32 + COM）
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="仅在 Windows 运行")

# 项目根 — 用 __file__ 动态取，避免硬编码开发机路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _FakeComError(Exception):
    """Fake pythoncom.com_error 供各测试复用 — args[0] = hresult，.hresult attr 也可读。"""

    def __init__(self, hresult):
        self.hresult = hresult
        super().__init__(hresult)
        self.args = (hresult,)


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

    def test_worker_open_doc_failure_terminal_errors_returns_rc2(self, monkeypatch):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        # OpenDocFailure errors=8192 (swFutureVersion，rev 6 本机校准) → terminal
        def raise_terminal(app, p):
            raise wkr.OpenDocFailure(errors=8192, warnings=0, model_was_null=False)
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_terminal)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 2

    def test_worker_open_doc_failure_transient_errors_returns_rc3(self, monkeypatch):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        # OpenDocFailure errors=8388608 (swApplicationBusy，rev 6 本机校准) → transient
        def raise_transient(app, p):
            raise wkr.OpenDocFailure(errors=8388608, warnings=0, model_was_null=False)
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_transient)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 3

    def test_worker_open_doc_null_model_returns_rc2(self, monkeypatch):
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

    def test_worker_com_error_transient_hresult_returns_rc3(self, monkeypatch):
        from adapters.solidworks import sw_list_configs_worker as wkr

        # mock pythoncom + win32com.client，DispatchEx 抛 com_error
        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        # 构造一个真 com_error subclass 让 isinstance 通过
        monkeypatch.setattr(sys.modules["pythoncom"], "com_error", _FakeComError)

        def raise_transient_com(app, p):
            raise _FakeComError(-2147023170)  # RPC_E_DISCONNECTED
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_transient_com)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 3

    def test_worker_com_error_terminal_hresult_returns_rc2(self, monkeypatch):
        from adapters.solidworks import sw_list_configs_worker as wkr

        fake_app = mock.MagicMock()
        _patch_com(monkeypatch, dispatch_return=fake_app)

        monkeypatch.setattr(sys.modules["pythoncom"], "com_error", _FakeComError)

        def raise_terminal_com(app, p):
            raise _FakeComError(-2147467259)  # 未识别 hresult → terminal
        monkeypatch.setattr(wkr, "_open_doc_get_configs", raise_terminal_com)

        rc = wkr._list_configs("dummy.sldprt")
        assert rc == 2


class TestWorkerImportError:
    """ImportError → terminal (pywin32 没装是部署问题)."""

    def test_worker_import_error_returns_rc2(self, monkeypatch):
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
        monkeypatch.setattr(pythoncom, "com_error", _FakeComError)

        # transient hresults
        assert wkr._classify_worker_exception(_FakeComError(-2147023170)) == 3
        assert wkr._classify_worker_exception(_FakeComError(-2147418113)) == 3
        assert wkr._classify_worker_exception(_FakeComError(-2147023174)) == 3

        # 未识别 hresult → terminal
        assert wkr._classify_worker_exception(_FakeComError(-2147467259)) == 2

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
        monkeypatch.delitem(sys.modules, "pythoncom", raising=False)
        monkeypatch.delitem(sys.modules, "win32com.client", raising=False)
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
        fake_pythoncom = mock.MagicMock()
        fake_pythoncom.com_error = _FakeComError
        fake_pythoncom.CoInitialize = lambda: None
        fake_pythoncom.CoUninitialize = lambda: None

        fake_win32com_client = mock.MagicMock()
        fake_win32com_client.DispatchEx.side_effect = _FakeComError(-2147023170)  # RPC_E_DISCONNECTED → transient

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


# ---------------------------------------------------------------------------
# 恢复的原 10 测试（commit 223eb1e 版本，按 spec rev 6 调整 assert 标注）
# 覆盖：CLI 用法错误 / 单件 CLI / batch 协议基础 / C-1 真单 boot 回归
# ---------------------------------------------------------------------------


def _make_fake_com_modules(open_doc_fail_paths: set | None = None):
    """构造 fake pythoncom + win32com.client 模块，注入 sys.modules，
    返 (counters dict, fake_pythoncom, fake_win32com, fake_win32com_client) 供测试断言。

    open_doc_fail_paths：模拟 OpenDoc6 失败的 sldprt 路径集合（err_var.value=1）。
    """
    open_doc_fail_paths = open_doc_fail_paths or set()
    counters = {
        "co_init": 0, "co_uninit": 0, "dispatch": 0,
        "exit_app": 0, "open_doc": 0, "close_doc": 0,
    }

    class FakeVariant:
        def __init__(self, *args, **kwargs):
            self.value = 0

    class FakeConfigMgr:
        def __init__(self, configs):
            self._configs = configs

        def GetConfigurationNames(self):
            return self._configs

    class FakeModel:
        def __init__(self, path):
            self._path = path
            self.ConfigurationManager = FakeConfigMgr([f"cfg-{Path(path).stem}"])

        def GetPathName(self):
            return self._path

    class FakeApp:
        Visible = True
        UserControl = True
        FrameState = -1

        def OpenDoc6(self, path, *args):
            counters["open_doc"] += 1
            err_var = args[3] if len(args) >= 4 else None
            if path in open_doc_fail_paths and err_var is not None:
                err_var.value = 1
                return None
            return FakeModel(path)

        def CloseDoc(self, path):
            counters["close_doc"] += 1

        def ExitApp(self):
            counters["exit_app"] += 1

    app_singleton = FakeApp()

    class FakePythoncom:
        VT_BYREF = 0
        VT_I4 = 0

        @staticmethod
        def CoInitialize():
            counters["co_init"] += 1

        @staticmethod
        def CoUninitialize():
            counters["co_uninit"] += 1

    fake_pythoncom_mod = type(sys)("pythoncom")
    fake_pythoncom_mod.VT_BYREF = FakePythoncom.VT_BYREF
    fake_pythoncom_mod.VT_I4 = FakePythoncom.VT_I4
    fake_pythoncom_mod.CoInitialize = FakePythoncom.CoInitialize
    fake_pythoncom_mod.CoUninitialize = FakePythoncom.CoUninitialize

    fake_win32com_mod = type(sys)("win32com")
    fake_win32com_client_mod = type(sys)("win32com.client")
    fake_win32com_client_mod.VARIANT = FakeVariant
    fake_win32com_client_mod.DispatchEx = lambda name: (
        counters.__setitem__("dispatch", counters["dispatch"] + 1),
        app_singleton,
    )[1]
    fake_win32com_mod.client = fake_win32com_client_mod

    return counters, fake_pythoncom_mod, fake_win32com_mod, fake_win32com_client_mod


def test_usage_error_returns_64():
    """无参数 → exit 64（subprocess 真路径，验证 CLI 入口）"""
    proc = subprocess.run(
        [sys.executable, "-m", "adapters.solidworks.sw_list_configs_worker"],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
    )
    assert proc.returncode == 64
    assert "usage" in proc.stderr.lower()


def test_pywin32_unavailable_returns_4(monkeypatch):
    """pythoncom import 失败 → exit 2（spec rev 6 把 rc=4 deprecate 改为 rc=2 EXIT_TERMINAL）"""
    # 把 pythoncom 强制设成 None 模拟 import 失败
    monkeypatch.setitem(sys.modules, "pythoncom", None)
    from adapters.solidworks import sw_list_configs_worker

    # 函数内 import，无需 reload；直接调用即可
    rc = sw_list_configs_worker._list_configs("dummy.sldprt")
    assert rc == 2  # spec rev 6：rc=4 已 deprecate，改为 rc=2 (EXIT_TERMINAL)


def test_single_file_cli_mode_preserved():
    """单件 CLI 模式（main([sldprt_path])）保留兼容：调 _list_configs 一次。"""
    from adapters.solidworks import sw_list_configs_worker as w

    with mock.patch.object(w, "_list_configs", return_value=0) as mock_list:
        rc = w.main(["C:/path1.sldprt"])
        assert rc == 0
        mock_list.assert_called_once_with("C:/path1.sldprt")


def test_no_args_returns_64():
    """空参数返 exit 64（CLI usage error）— 函数级契约（与 subprocess 版互补）。"""
    from adapters.solidworks import sw_list_configs_worker as w

    rc = w.main([])
    assert rc == 64


def test_batch_mode_reads_stdin_and_writes_stdout(monkeypatch, capsys):
    """--batch flag → stdin JSON list → stdout JSON list of {path, configs, exit_code}。
    spec rev 6：每 entry 含 exit_code=0（成功）。"""
    from adapters.solidworks import sw_list_configs_worker as w

    fake_results = {
        "C:/p1.sldprt": ["M3", "M4"],
        "C:/p2.sldprt": [],
    }

    def fake_open_doc_get_configs(app, sldprt_path):
        return fake_results.get(sldprt_path, [])

    monkeypatch.setattr(w, "_open_doc_get_configs", fake_open_doc_get_configs)
    # 同时 mock COM 模块（_run_batch_mode 仍要 import + DispatchEx）
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules()
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps(["C:/p1.sldprt", "C:/p2.sldprt"])),
    )

    rc = w.main(["--batch"])
    assert rc == 0

    out = capsys.readouterr().out
    parsed = json.loads(out)
    # spec rev 6：每 entry 含 exit_code=0
    assert len(parsed) == 2
    assert parsed[0]["path"] == "C:/p1.sldprt"
    assert parsed[0]["configs"] == ["M3", "M4"]
    assert parsed[0]["exit_code"] == 0
    assert parsed[1]["path"] == "C:/p2.sldprt"
    assert parsed[1]["configs"] == []
    assert parsed[1]["exit_code"] == 0


def test_batch_mode_invalid_stdin_returns_64(monkeypatch):
    """--batch + stdin 不是 JSON list → exit 64。"""
    from adapters.solidworks import sw_list_configs_worker as w

    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    rc = w.main(["--batch"])
    assert rc == 64


def test_batch_mode_per_file_failure_continues(monkeypatch, capsys):
    """单 sldprt 失败（_open_doc_get_configs 抛异常）不阻其他 sldprt；
    输出仍是 JSON list，失败者 configs=[]，entry 含 exit_code 分类，整 batch exit 0。
    spec rev 6：失败 entry 含 exit_code=3（transient）或 2（terminal）按异常分类。"""
    from adapters.solidworks import sw_list_configs_worker as w

    def flaky(app, sldprt_path):
        if "bad" in sldprt_path:
            raise RuntimeError("simulated COM failure")
        return ["A"]

    monkeypatch.setattr(w, "_open_doc_get_configs", flaky)
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules()
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps(["C:/good.sldprt", "C:/bad.sldprt"])),
    )
    rc = w.main(["--batch"])
    assert rc == 0  # 整 batch exit 0：单件失败不算整 batch 失败
    out = capsys.readouterr().out
    parsed = json.loads(out)
    # good 件成功
    assert parsed[0]["path"] == "C:/good.sldprt"
    assert parsed[0]["configs"] == ["A"]
    assert parsed[0]["exit_code"] == 0
    # bad 件失败，configs=[] + exit_code 为分类值（RuntimeError → transient rc=3）
    assert parsed[1]["path"] == "C:/bad.sldprt"
    assert parsed[1]["configs"] == []
    assert parsed[1]["exit_code"] in (2, 3)  # 取决于 RuntimeError 的分类规则


def test_batch_mode_initializes_com_only_once(monkeypatch, capsys):
    """C-1 regression：batch 3 件 → CoInit/Dispatch/ExitApp/CoUninitialize
    各调 1 次；OpenDoc6 / CloseDoc 各调 3 次。"""
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules()
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)

    from adapters.solidworks import sw_list_configs_worker as w
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps([
            "C:/p1.sldprt", "C:/p2.sldprt", "C:/p3.sldprt",
        ])),
    )

    rc = w.main(["--batch"])
    assert rc == 0

    assert counters["co_init"] == 1, f"CoInitialize 应 1 次，实 {counters['co_init']}"
    assert counters["dispatch"] == 1, f"DispatchEx 应 1 次，实 {counters['dispatch']}"
    assert counters["exit_app"] == 1, f"ExitApp 应 1 次，实 {counters['exit_app']}"
    assert counters["co_uninit"] == 1, f"CoUninitialize 应 1 次，实 {counters['co_uninit']}"
    assert counters["open_doc"] == 3, f"OpenDoc6 应 3 次，实 {counters['open_doc']}"
    assert counters["close_doc"] == 3, f"CloseDoc 应 3 次，实 {counters['close_doc']}"

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert len(parsed) == 3
    assert all("configs" in entry for entry in parsed)


def test_batch_mode_per_file_open_failure_keeps_single_lifecycle(
    monkeypatch, capsys,
):
    """C-1 regression 配套：batch 中某件 OpenDoc6 失败 → 记 configs=[] 跳过 →
    其他件继续；CoInit/ExitApp 仍各 1 次（单 lifecycle 不被 reset）。"""
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules(
        open_doc_fail_paths={"C:/bad.sldprt"},
    )
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)

    from adapters.solidworks import sw_list_configs_worker as w
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps([
            "C:/good1.sldprt", "C:/bad.sldprt", "C:/good2.sldprt",
        ])),
    )

    rc = w.main(["--batch"])
    assert rc == 0
    assert counters["co_init"] == 1
    assert counters["exit_app"] == 1

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed[0]["configs"] == ["cfg-good1"]
    assert parsed[1]["configs"] == []  # bad 失败
    assert parsed[2]["configs"] == ["cfg-good2"]


def test_batch_mode_empty_list_skips_com_boot(monkeypatch, capsys):
    """边界：空 batch list → 不 CoInitialize / Dispatch（避免无谓 SW 启动）。"""
    counters, fake_py, fake_w32, fake_w32_client = _make_fake_com_modules()
    monkeypatch.setitem(sys.modules, "pythoncom", fake_py)
    monkeypatch.setitem(sys.modules, "win32com", fake_w32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_w32_client)

    from adapters.solidworks import sw_list_configs_worker as w
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([])))

    rc = w.main(["--batch"])
    assert rc == 0
    assert counters["co_init"] == 0
    assert counters["dispatch"] == 0
    out = capsys.readouterr().out
    assert json.loads(out) == []
