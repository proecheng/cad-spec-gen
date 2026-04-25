import subprocess
import sys


def test_usage_error_returns_64():
    """无参数 → exit 64"""
    proc = subprocess.run(
        [sys.executable, "-m", "adapters.solidworks.sw_list_configs_worker"],
        capture_output=True,
        text=True,
        cwd="D:/Work/cad-spec-gen",
    )
    assert proc.returncode == 64
    assert "usage" in proc.stderr.lower()


def test_pywin32_unavailable_returns_4(monkeypatch):
    """pywin32 import 失败 → exit 4"""
    import importlib
    import sys as _sys

    # 把 pythoncom 强制设成 None 模拟 import 失败
    monkeypatch.setitem(_sys.modules, "pythoncom", None)
    from adapters.solidworks import sw_list_configs_worker
    importlib.reload(sw_list_configs_worker)

    rc = sw_list_configs_worker._list_configs("dummy.sldprt")
    assert rc == 4
