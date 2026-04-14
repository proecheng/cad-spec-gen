"""真 subprocess.run 集成测试：验证 timeout 触发时子进程被杀、父进程返回 False。

不依赖真实 SolidWorks——用 tests/fixtures/sw_convert_worker_stub_sleep.py
当替代 worker（sleep 120s）。测试把 SINGLE_CONVERT_TIMEOUT_SEC 调成 2s，
期望父进程在 ~2s 内返回 False 且不产出 STEP 文件。
"""

from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


pytestmark = pytest.mark.real_subprocess


def test_subprocess_timeout_actually_kills_child(tmp_path, monkeypatch):
    from adapters.solidworks import sw_com_session
    from adapters.solidworks.sw_com_session import SwComSession, reset_session

    reset_session()

    # 改 worker 指向 sleep stub；改 timeout 到 2s 加速测试
    monkeypatch.setattr(
        sw_com_session,
        "_WORKER_MODULE",
        "tests.fixtures.sw_convert_worker_stub_sleep",
    )
    monkeypatch.setattr(sw_com_session, "SINGLE_CONVERT_TIMEOUT_SEC", 2)

    s = SwComSession()
    step_out = tmp_path / "out.step"
    sldprt = tmp_path / "fake.sldprt"
    sldprt.write_bytes(b"")

    t0 = time.time()
    ok = s.convert_sldprt_to_step(str(sldprt), str(step_out))
    elapsed = time.time() - t0

    assert ok is False
    assert elapsed < 10, f"subprocess 没被及时 kill：耗时 {elapsed:.1f}s"
    assert not step_out.exists()
    # tmp 若被创建也应被 _cleanup_tmp 清
    assert not (tmp_path / "out.tmp.step").exists()
    assert s._consecutive_failures == 1
