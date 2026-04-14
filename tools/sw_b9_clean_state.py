"""SW 进程与临时状态清理（SW-B9 Stage D before/after 隔离用）。

见 docs/superpowers/specs/2026-04-14-sw-b9-real-run-acceptance-design.md §5.7 step 3。
"""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


class SwStateNotClean(RuntimeError):
    """SW 进程未能在超时内退出。"""


def _wait_sldworks_gone(timeout_s: float = 10.0, poll_s: float = 0.5) -> bool:
    """轮询至 sldworks.exe 进程不存在或超时。"""
    try:
        import psutil
    except ImportError:
        log.warning("psutil 未安装，跳过 sldworks.exe 进程轮询")
        return True

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        alive = [p for p in psutil.process_iter(["name"]) if
                 (p.info.get("name") or "").lower().startswith("sldworks")]
        if not alive:
            return True
        time.sleep(poll_s)
    return False


def clean_sw_state(
    session: Optional[Any],
    step_cache_dir: Optional[Path],
    raise_on_lingering: bool = False,
) -> None:
    """清理 SW 状态：Quit session + 等进程退出 + 清临时 STEP 缓存。"""
    if session is not None:
        try:
            session.quit()
        except Exception as e:
            log.warning("session.quit() 异常: %s", e)

    gone = _wait_sldworks_gone()
    if not gone:
        msg = "sldworks.exe 未能在 10s 内退出"
        log.error(msg)
        if raise_on_lingering:
            raise SwStateNotClean(msg)

    if step_cache_dir is not None and step_cache_dir.exists():
        for child in step_cache_dir.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
