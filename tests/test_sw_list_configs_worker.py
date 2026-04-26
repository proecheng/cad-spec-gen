"""sw_list_configs_worker 测试：单件 CLI 契约 + --batch IPC 协议（spec §6.1 D 矩阵）。

worker 内部 _list_configs_returning 真调 SW COM；测试用 monkeypatch 替换该函数避免 SW 触发，
仅验证 CLI 入口 / IPC 协议 / exit code 契约。
"""

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 仅 Windows 平台运行（worker 依赖 pywin32 + COM）
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="仅在 Windows 运行")

# 项目根 — 用 __file__ 动态取，避免硬编码开发机路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
    """pythoncom import 失败 → exit 4（通过 sys.modules None 条目触发 ImportError）"""
    # 把 pythoncom 强制设成 None 模拟 import 失败
    monkeypatch.setitem(sys.modules, "pythoncom", None)
    from adapters.solidworks import sw_list_configs_worker

    # 函数内 import，无需 reload；直接调用即可
    rc = sw_list_configs_worker._list_configs("dummy.sldprt")
    assert rc == 4


def test_single_file_cli_mode_preserved():
    """单件 CLI 模式（main([sldprt_path])）保留兼容：调 _list_configs 一次。"""
    from adapters.solidworks import sw_list_configs_worker as w

    with patch.object(w, "_list_configs", return_value=0) as mock_list:
        rc = w.main(["C:/path1.sldprt"])
        assert rc == 0
        mock_list.assert_called_once_with("C:/path1.sldprt")


def test_no_args_returns_64():
    """空参数返 exit 64（CLI usage error）— 函数级契约（与 subprocess 版互补）。"""
    from adapters.solidworks import sw_list_configs_worker as w

    rc = w.main([])
    assert rc == 64


def test_batch_mode_reads_stdin_and_writes_stdout(monkeypatch, capsys):
    """--batch flag → stdin JSON list → stdout JSON list of {path, configs}."""
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
    assert parsed == [
        {"path": "C:/p1.sldprt", "configs": ["M3", "M4"]},
        {"path": "C:/p2.sldprt", "configs": []},
    ]


def test_batch_mode_invalid_stdin_returns_64(monkeypatch):
    """--batch + stdin 不是 JSON list → exit 64。"""
    from adapters.solidworks import sw_list_configs_worker as w

    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    rc = w.main(["--batch"])
    assert rc == 64


def test_batch_mode_per_file_failure_continues(monkeypatch, capsys):
    """单 sldprt 失败（_open_doc_get_configs 抛异常）不阻其他 sldprt；
    输出仍是 JSON list，失败者 configs=[]，整 batch exit 0。"""
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
    assert parsed == [
        {"path": "C:/good.sldprt", "configs": ["A"]},
        {"path": "C:/bad.sldprt", "configs": []},
    ]


def _make_fake_com_modules(open_doc_fail_paths: set | None = None):
    """构造 fake pythoncom + win32com.client 模块，注入 sys.modules，
    返 (counters dict, fake_pythoncom, fake_win32com, fake_win32com_client) 供测试断言。

    open_doc_fail_paths：模拟 OpenDoc6 失败的 sldprt 路径集合（err_var.value=1）。
    """
    from pathlib import Path as _Path

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
            self.ConfigurationManager = FakeConfigMgr([f"cfg-{_Path(path).stem}"])

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
