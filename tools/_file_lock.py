"""跨平台文件锁 + PID stale 自动清理。

抽自 tools/sw_warmup.py acquire_warmup_lock；jury 与 sw_warmup 共用。
锁路径由调用方决定（jury 用 active_run_dir/.jury.lock，sw_warmup 用 GB cache root）。

设计要点：
- 用 JSON sidecar（pid + started_at）而非 OS-level msvcrt/fcntl 锁；
  优点：跨平台一致、可读、可手动清理；
- stale 自动清理 = mtime > 30 分钟 或 PID 不存活；
- 同进程内重入也会抛 LockBusy（与旧 sw_warmup 行为一致）；
- v1 stdlib only：不引入 portalocker / filelock 等第三方依赖。
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class LockBusy(Exception):
    """已有 live lock；调用方需自行映射到 exit code。

    pid 作为结构化属性暴露，方便上层无需正则解析字符串即可拿到持锁者。
    """

    _MSG_FMT = "已有进程持有 {name}（PID={pid}）"

    def __init__(self, lock_name: str, pid: str | int):
        super().__init__(self._MSG_FMT.format(name=lock_name, pid=pid))
        self.pid: str = str(pid)


_STALE_SECONDS = 30 * 60  # 30 分钟


def _pid_alive(pid: int) -> bool:
    """跨平台判断 PID 是否在系统中存活。

    pid <= 0 一律视为不存活（包括 0、负数）。
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            # ctypes.windll 仅在 Windows 提供；attr-defined 忽略仅 Linux mypy 需要，
            # Windows mypy 策略下视为冗余（CLAUDE.md 禁裸 type: ignore），改用动态属性访问。
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = getattr(ctypes, "windll").kernel32  # noqa: B009
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # PermissionError 表示 PID 存在但属于他人
            return True
        except Exception:
            return False


@contextmanager
def acquire_lock(lock_path: Path) -> Iterator[None]:
    """获取 lock；live 则抛 LockBusy；stale（mtime>30min 或 PID 不存活）自动清理。

    Args:
        lock_path: 锁文件绝对路径，父目录会被自动创建

    Yields:
        None — with 块内代表已持锁

    Raises:
        LockBusy: 已被另一进程占用；exc.pid 暴露持锁者 PID 字符串
    """
    lock_path = Path(lock_path)

    if lock_path.exists():
        held_pid = -1
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            held_pid = int(data.get("pid", -1))
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            held_pid = -1  # 损坏 lock 视为 stale

        try:
            held_mtime = lock_path.stat().st_mtime
        except OSError:
            held_mtime = 0.0
        now = time.time()
        stale_by_age = (now - held_mtime) > _STALE_SECONDS
        stale_by_pid = held_pid > 0 and not _pid_alive(held_pid)

        if held_pid <= 0 or stale_by_age or stale_by_pid:
            sys.stderr.write(
                f"警告：检测到 stale lock {lock_path.name}（PID={held_pid}, "
                f"age={int(now - held_mtime)}s），自动清理后继续。\n"
            )
            try:
                lock_path.unlink()
            except OSError:
                pass
        else:
            raise LockBusy(lock_path.name, held_pid)

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "started_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    try:
        yield
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
