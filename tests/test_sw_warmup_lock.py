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
