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

    def fake_list_configs_returning(sldprt_path):
        return fake_results.get(sldprt_path, [])

    monkeypatch.setattr(w, "_list_configs_returning", fake_list_configs_returning)
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
    """单 sldprt 失败（_list_configs_returning 抛异常）不阻其他 sldprt；
    输出仍是 JSON list，失败者 configs=[]，整 batch exit 0。"""
    from adapters.solidworks import sw_list_configs_worker as w

    def flaky(sldprt_path):
        if "bad" in sldprt_path:
            raise RuntimeError("simulated COM failure")
        return ["A"]

    monkeypatch.setattr(w, "_list_configs_returning", flaky)
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
