"""sw-warmup 核心实现（v4 §7 + 决策 #26）。

模块只暴露 run_sw_warmup(args) → int 主入口，
acquire_warmup_lock(lock_path) context manager 给单元测试单独覆盖。
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

# 全局状态：追踪当前进程已持有的锁（同进程内防止重复 acquire）
_held_locks: set[str] = set()


@contextlib.contextmanager
def acquire_warmup_lock(lock_path: Path) -> Iterator[None]:
    """独占进程锁（决策 #26）。Windows 用 msvcrt，其他平台 fcntl。

    Args:
        lock_path: 锁文件绝对路径，父目录会被自动创建

    Yields:
        None — with 块内代表已持锁

    Raises:
        RuntimeError: 已被另一进程占用（带 PID 提示）
    """
    lock_path = Path(lock_path)
    lock_path_str = str(lock_path.resolve())

    # 同进程内重复 acquire 检查
    if lock_path_str in _held_locks:
        pid = os.getpid()
        raise RuntimeError(f"另一个 sw-warmup 进程运行中 (PID {pid})")

    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # 确保文件存在，以便 lock 操作
    if not lock_path.exists():
        lock_path.write_text(str(os.getpid()))

    fh = open(lock_path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise RuntimeError(f"另一个 sw-warmup 进程运行中 (PID {pid})") from e
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise RuntimeError(f"另一个 sw-warmup 进程运行中 (PID {pid})") from e

        # 记录为已持有
        _held_locks.add(lock_path_str)

        # 持锁后写入当前 PID 供下个尝试者诊断（spec 要求）
        # 用 seek(0)+truncate 保证清掉 bootstrap 写入的旧值
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(str(os.getpid()))
            fh.flush()
        except OSError as e:
            log.debug("写入 PID 异常（忽略）: %s", e)

        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as e:
                    log.debug("释放 msvcrt 锁异常（忽略）: %s", e)
            else:
                import fcntl

                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError as e:
                    log.debug("释放 fcntl 锁异常（忽略）: %s", e)

            # 移除持有标记
            _held_locks.discard(lock_path_str)
    finally:
        fh.close()
