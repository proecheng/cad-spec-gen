"""验证抽出后的通用文件锁 API。"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tools._file_lock import LockBusy, acquire_lock, _pid_alive


def test_acquire_release_basic(tmp_path: Path) -> None:
    """正常获取 + 自动释放。"""
    lock_path = tmp_path / "test.lock"
    with acquire_lock(lock_path):
        assert lock_path.exists()
        data = lock_path.read_text(encoding="utf-8")
        assert str(os.getpid()) in data
    assert not lock_path.exists()


def test_acquire_busy_raises(tmp_path: Path) -> None:
    """已有 live lock 抛 LockBusy。"""
    lock_path = tmp_path / "test.lock"
    with acquire_lock(lock_path):
        with pytest.raises(LockBusy):
            with acquire_lock(lock_path):
                pass


def test_stale_by_pid_auto_clean(tmp_path: Path) -> None:
    """PID 不存在的 stale lock 自动清理。"""
    import json

    lock_path = tmp_path / "test.lock"
    # 写一个不存在的 PID
    lock_path.write_text(
        json.dumps({"pid": 99999999, "started_at": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    with acquire_lock(lock_path):
        # 自动清理后 PID 应是当前进程
        data = lock_path.read_text(encoding="utf-8")
        assert str(os.getpid()) in data


def test_stale_by_mtime_auto_clean(tmp_path: Path) -> None:
    """mtime > 30 min 的 stale lock 自动清理。"""
    import json

    lock_path = tmp_path / "test.lock"
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "started_at": "..."}),
        encoding="utf-8",
    )
    # 改 mtime 到 31 分钟前
    old_time = time.time() - 31 * 60
    os.utime(lock_path, (old_time, old_time))
    with acquire_lock(lock_path):
        # 已清理重写
        assert lock_path.stat().st_mtime > old_time + 30 * 60


def test_pid_alive_current_process() -> None:
    assert _pid_alive(os.getpid()) is True


def test_pid_alive_nonexistent() -> None:
    assert _pid_alive(99999999) is False
