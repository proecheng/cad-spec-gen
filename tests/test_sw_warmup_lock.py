"""sw_warmup 进程锁单元测试（决策 #26）。"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAcquireWarmupLock:
    """进程锁 context manager 行为。"""

    def test_acquire_releases_on_exit(self, tmp_path):
        """正常 with 块退出后锁应被释放。"""
        from tools.sw_warmup import acquire_warmup_lock

        lock_path = tmp_path / "sw_warmup.lock"
        with acquire_warmup_lock(lock_path):
            assert lock_path.exists()  # 锁文件存在
        # 退出后下一次 acquire 应立即成功（释放 OK）
        with acquire_warmup_lock(lock_path):
            pass

    def test_concurrent_acquire_raises(self, tmp_path):
        """已持锁时另一次 acquire 应 raise RuntimeError。"""
        from tools.sw_warmup import acquire_warmup_lock

        lock_path = tmp_path / "sw_warmup.lock"
        with acquire_warmup_lock(lock_path):
            # 同进程模拟另一个尝试者：直接再 acquire
            # （Windows msvcrt + Linux fcntl 同进程内多次 acquire 会冲突）
            with pytest.raises(RuntimeError, match="另一个 sw-warmup 进程"):
                with acquire_warmup_lock(lock_path):
                    pass

    def test_acquire_seeks_to_zero_before_locking(self, tmp_path, monkeypatch):
        """Part 2b I-3: msvcrt.locking 前必须 fh.seek(0)；字节数 == _LOCK_NBYTES。

        验证 acquire 路径调用 msvcrt.locking 时：
          - 文件位置在 _LOCK_OFFSET（由常量驱动）
          - 第 3 位置参数（nbytes）等于 _LOCK_NBYTES 模块常量
        """
        import os

        if os.name != "nt":
            pytest.skip("msvcrt 仅 Windows")

        import msvcrt
        from tools import sw_warmup as mod

        observed = {}

        def _fake_locking(fd, op, nbytes):
            observed["nbytes"] = nbytes
            observed["pos_at_call"] = os.lseek(fd, 0, 1)  # SEEK_CUR

        monkeypatch.setattr(msvcrt, "locking", _fake_locking)

        lock_path = tmp_path / "sw_warmup.lock"
        with mod.acquire_warmup_lock(lock_path):
            pass

        assert observed["pos_at_call"] == mod._LOCK_OFFSET, (
            f"acquire 未在 locking 前 seek 到 _LOCK_OFFSET={mod._LOCK_OFFSET}"
        )
        assert observed["nbytes"] == mod._LOCK_NBYTES, (
            f"acquire 的 locking 字节数 != _LOCK_NBYTES={mod._LOCK_NBYTES}"
        )
