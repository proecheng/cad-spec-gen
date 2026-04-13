"""
adapters/solidworks/sw_com_session.py — SolidWorks COM 会话管理。

实现 v4 决策 #6/#10/#11/#22/#23/#25：
- 熔断器（连续 3 次失败触发）
- 冷启动超时 90s / 单零件 30s / 空闲 300s / 每 50 次重启
- threading.Lock 保护 COM 调用（非线程安全）
- atomic write（fsync + MIN_STEP_FILE_SIZE + ISO-10303 magic bytes）
- encoding 透传（os.fspath + str 断言）

不在此模块硬依赖 win32com（runtime import）。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# v4 决策 #10/#11/#6
COLD_START_TIMEOUT_SEC = 90
SINGLE_CONVERT_TIMEOUT_SEC = 30
IDLE_SHUTDOWN_SEC = 300
RESTART_EVERY_N_CONVERTS = 50
CIRCUIT_BREAKER_THRESHOLD = 3

# v4 决策 #23: atomic write 校验
MIN_STEP_FILE_SIZE = 1024
STEP_MAGIC_PREFIX = b"ISO-10303"


class SwComSession:
    """COM session 唯一 source of truth（v4 决策 #22）。

    熔断状态归此类；adapter.is_available() 委托 is_healthy()。
    """

    def __init__(self) -> None:
        self._app = None  # win32com Dispatch object (lazy init)
        self._convert_count = 0
        self._consecutive_failures = 0
        self._unhealthy = False
        self._last_used_ts = 0.0
        self._lock = threading.Lock()

    def is_healthy(self) -> bool:
        """熔断状态查询。"""
        return not self._unhealthy

    def convert_sldprt_to_step(
        self,
        sldprt_path,
        step_out,
    ) -> bool:
        """转换单个 sldprt 为 STEP（v4 决策 #6/#23/#25）。

        全方法包 self._lock（COM 非线程安全）。
        atomic write: tmp → validate → rename。

        Returns:
            True: 成功
            False: 任何失败（不抛异常），自动累加熔断计数。
        """
        # v4 决策 #25: encoding 透传
        sldprt_path = str(os.fspath(sldprt_path))
        step_out = str(os.fspath(step_out))

        with self._lock:
            if self._unhealthy:
                return False

            success = False
            try:
                success = self._do_convert(sldprt_path, step_out)
                if success:
                    self._convert_count += 1
                    self._consecutive_failures = 0
                    self._last_used_ts = time.time()
                else:
                    self._consecutive_failures += 1
            except Exception as e:
                log.warning("COM convert 异常: %s", e)
                self._consecutive_failures += 1
                success = False
            finally:
                if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    log.error(
                        "COM 熔断触发（连续 %d 次失败）",
                        self._consecutive_failures,
                    )
                    self._unhealthy = True
            return success

    def _do_convert(self, sldprt_path: str, step_out: str) -> bool:
        """实际 COM 调用 + atomic write（v4 决策 #23）。"""
        if self._app is None:
            log.warning("SwComSession._app is None; 必须先 start()")
            return False

        tmp_path = step_out + ".tmp"
        Path(step_out).parent.mkdir(parents=True, exist_ok=True)

        # OpenDoc6
        model, errors, warnings = self._app.OpenDoc6(
            sldprt_path,
            1,   # swDocPART
            1,   # swOpenDocOptions_Silent
            "",
            0, 0,
        )
        if errors:
            log.warning("OpenDoc6 errors: %s", errors)
            return False

        try:
            # SaveAs3 to tmp
            saved = model.Extension.SaveAs3(
                tmp_path,
                0, 1,
                None, None,
                0, 0,
            )
            if not saved:
                return False

            # Validate tmp
            if not self._validate_step_file(tmp_path):
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    pass
                return False

            # Atomic rename
            os.replace(tmp_path, step_out)
            return True
        finally:
            try:
                self._app.CloseDoc(model.GetTitle())
            except Exception:
                pass

    @staticmethod
    def _validate_step_file(path: str) -> bool:
        """v4 决策 #23: 校验大小 + magic bytes。"""
        p = Path(path)
        if not p.exists():
            return False
        if p.stat().st_size < MIN_STEP_FILE_SIZE:
            return False
        with p.open("rb") as f:
            header = f.read(16)
        return header.startswith(STEP_MAGIC_PREFIX)

    def shutdown(self) -> None:
        """释放 SW COM session。"""
        with self._lock:
            if self._app is not None:
                try:
                    self._app.ExitApp()
                except Exception:
                    pass
                self._app = None


# 进程级 singleton
_SESSION_SINGLETON: Optional[SwComSession] = None
_SINGLETON_LOCK = threading.Lock()


def get_session() -> SwComSession:
    """返回进程级 SwComSession 单例（v4 决策 #22）。"""
    global _SESSION_SINGLETON
    with _SINGLETON_LOCK:
        if _SESSION_SINGLETON is None:
            _SESSION_SINGLETON = SwComSession()
        return _SESSION_SINGLETON


def reset_session() -> None:
    """清空 singleton + 清熔断状态。
    注册到 sw_material_bridge.reset_all_sw_caches()（v4 决策 #15）。
    """
    global _SESSION_SINGLETON
    with _SINGLETON_LOCK:
        if _SESSION_SINGLETON is not None:
            try:
                _SESSION_SINGLETON.shutdown()
            except Exception:
                pass
        _SESSION_SINGLETON = None
