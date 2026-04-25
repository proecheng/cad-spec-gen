import subprocess
import sys
from pathlib import Path

import pytest

# 仅 Windows 平台运行（worker 依赖 pywin32 + COM）
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="仅在 Windows 运行")

# 项目根 — 用 __file__ 动态取，避免硬编码开发机路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_usage_error_returns_64():
    """无参数 → exit 64"""
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
