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
        """已持锁时另一次 acquire 应 raise WarmupLockContentionError（Part 2c P1 T4）。"""
        from tools.sw_warmup import acquire_warmup_lock, WarmupLockContentionError

        lock_path = tmp_path / "sw_warmup.lock"
        with acquire_warmup_lock(lock_path):
            # 同进程模拟另一个尝试者：直接再 acquire
            # （Windows msvcrt + Linux fcntl 同进程内多次 acquire 会冲突）
            with pytest.raises(WarmupLockContentionError) as ei:
                with acquire_warmup_lock(lock_path):
                    pass
            assert ei.value.pid == str(os.getpid())
            assert "另一个 sw-warmup 进程" in str(ei.value)

    def test_acquire_forwards_to_file_lock(self, tmp_path):
        """Task 1 重构后：acquire_warmup_lock 转发到 tools/_file_lock.acquire_lock。

        旧测试 test_acquire_seeks_to_zero_before_locking 直接 patch msvcrt.locking
        校验 OS-level 锁字节范围（_LOCK_OFFSET / _LOCK_NBYTES）；重构后底层实现
        改为 JSON sidecar + PID liveness 检测，不再调 msvcrt.locking。本测试改
        为校验"转发关系"和"锁文件 JSON 内容"两个新契约。
        """
        import json
        import os as _os

        from tools.sw_warmup import acquire_warmup_lock

        lock_path = tmp_path / "sw_warmup.lock"
        with acquire_warmup_lock(lock_path):
            # 持锁期间锁文件应是合法 JSON，含当前进程 PID
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            assert data["pid"] == _os.getpid()
            assert "started_at" in data
        # with 退出后锁文件应被自动清理（与 _file_lock.acquire_lock 契约一致）
        assert not lock_path.exists()

    @pytest.mark.skipif(os.name == "nt", reason="POSIX fcntl 分支测试")
    def test_concurrent_acquire_raises_on_posix(self, tmp_path):
        """POSIX fcntl 分支：同进程两次 acquire → WarmupLockContentionError。"""
        from tools.sw_warmup import (
            acquire_warmup_lock,
            WarmupLockContentionError,
        )

        lock_path = tmp_path / "sw_warmup.lock"
        with acquire_warmup_lock(lock_path):
            with pytest.raises(WarmupLockContentionError) as ei:
                with acquire_warmup_lock(lock_path):
                    pass  # unreachable
            assert ei.value.pid == str(os.getpid())
