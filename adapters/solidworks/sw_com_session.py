"""
adapters/solidworks/sw_com_session.py — SolidWorks COM 会话管理（Part 2c P0 重写）。

设计：每次 convert 启动独立 subprocess 跑 `sw_convert_worker`，父进程用
`subprocess.run(timeout=SINGLE_CONVERT_TIMEOUT_SEC)` 守护；timeout 触发
时 subprocess.run 内部会先 kill 再 raise，父进程把失败计入熔断器。

为什么 subprocess：pywin32 COM 调用阻塞后 threading 无法中断（SW-B0 spike
第 3 轮真跑实证）；只有杀子进程是可靠手段。

Session 公共 API 不变：`convert_sldprt_to_step(sldprt, step_out) -> bool` +
`is_healthy()` + `shutdown()` + `get_session()/reset_session()`。

父进程职责：subprocess 编排 + timeout 守护 + STEP validate + atomic rename +
熔断器。Worker 职责（另一个模块）：Dispatch + OpenDoc6 + SaveAs3 + 写 tmp。

Task 3 会删除老 in-process 生命周期死代码（_start_locked / _maybe_restart_locked /
_maybe_idle_shutdown_locked / _shutdown_locked / _com_dispatch / _app）。
本任务不删，保证 git diff 聚焦。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WORKER_MODULE = "adapters.solidworks.sw_convert_worker"

# v4 决策 #10/#11 行为契约常量 — 老 in-process 生命周期相关
# Task 3 会把不再相关的删掉；本任务保留以避免老测试红透
COLD_START_TIMEOUT_SEC = 90
SINGLE_CONVERT_TIMEOUT_SEC = 30
IDLE_SHUTDOWN_SEC = 300
RESTART_EVERY_N_CONVERTS = 50
CIRCUIT_BREAKER_THRESHOLD = 3

# v4 决策 #23: atomic write 校验
MIN_STEP_FILE_SIZE = 1024
STEP_MAGIC_PREFIX = b"ISO-10303"


def _com_dispatch(prog_id: str) -> object:
    """lazy import win32com.client.Dispatch（单元测试可 monkeypatch 此函数）。

    Args:
        prog_id: 例如 "SldWorks.Application"

    Returns:
        win32com Dispatch 对象

    Raises:
        ImportError: pywin32 未安装
        pywin32 com_error: SW 未安装或启动失败
    """
    from win32com.client import Dispatch  # type: ignore[import-not-found]

    return Dispatch(prog_id)


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

    def _start_locked(self) -> None:
        """冷启动（v4 决策 #10）。必须在持 self._lock 的上下文内调用。

        流程（SW-B0 spike 简化后）：
        1. Dispatch("SldWorks.Application")
        2. app.Visible = False, UserControl = False（避免弹窗）

        **不再调用 LoadAddIn("SOLIDWORKS Toolbox")**：spike 证实
        sldprt→STEP 转换仅需 OpenDoc6 + Extension.SaveAs3，与 Toolbox
        Library UI add-in 无关。该 add-in 在无 DLL 机器上 LoadAddIn 返回
        非 1，之前会阻塞整个 warmup；现在直接略过，减少启动 I/O。

        时间上限由调用方保证（Part 2c SW-B0 spike 补课后决定实现手段）。
        """
        if not self._lock.locked():
            raise RuntimeError("_start_locked 必须在持 self._lock 的上下文内调用")

        try:
            app = _com_dispatch("SldWorks.Application")
            app.Visible = False
            app.UserControl = False
            self._app = app
            # 注意：_last_used_ts 只在 convert_sldprt_to_step 成功时更新
            # （threading model doc 规则 6 I-2 语义）。start 不赋值，保持
            # 初值 0.0 直到第一次成功产出 STEP。
        except Exception:
            self._unhealthy = True
            self._app = None
            raise

    def _maybe_restart_locked(self) -> None:
        """若已达 RESTART_EVERY_N_CONVERTS 次，先 shutdown 再 start。

        必须在持 self._lock 的上下文内调用。
        shutdown 失败被吞掉（视为进程已死），_start_locked 负责重建。
        start 失败会让 _unhealthy=True 冒泡。

        注意：`_convert_count` 跨 idle shutdown 持久化——idle 释放
        SW 进程不重置计数。所以"49 次 convert → idle 释放 → 下次 convert
        重新 start → count 涨到 50 → 再下次 convert 触发 restart"是预期
        路径，会比未 idle 场景多一次 restart 开销，可接受。
        """
        if not self._lock.locked():
            raise RuntimeError(
                "_maybe_restart_locked 必须在持 self._lock 的上下文内调用"
            )

        if self._convert_count < RESTART_EVERY_N_CONVERTS:
            return

        log.info(
            "触发 COM session 周期重启 (count=%d，阈值 %d)",
            self._convert_count,
            RESTART_EVERY_N_CONVERTS,
        )
        self._shutdown_locked()
        self._start_locked()
        self._convert_count = 0

    def _maybe_idle_shutdown_locked(self) -> None:
        """若距上次 convert 已超 IDLE_SHUTDOWN_SEC，shutdown 释放 SW。
        必须在持 self._lock 的上下文内调用。下次 convert 会重新 start。

        _app is None 或 _last_used_ts==0 时 no-op（还没用过或已释放）。
        """
        if not self._lock.locked():
            raise RuntimeError(
                "_maybe_idle_shutdown_locked 必须在持 self._lock 的上下文内调用"
            )

        if self._app is None:
            return
        if self._last_used_ts == 0.0:
            return
        if time.time() - self._last_used_ts < IDLE_SHUTDOWN_SEC:
            return

        log.info(
            "idle shutdown（距上次 convert %.0f 秒）",
            time.time() - self._last_used_ts,
        )
        self._shutdown_locked()

    def convert_sldprt_to_step(self, sldprt_path, step_out) -> bool:
        """转换单个 sldprt 为 STEP（Part 2c P0 subprocess 守护版）。

        全方法包 self._lock（保证 singleton 串行）。subprocess 执行转换，
        成功时 validate + atomic rename；失败累加熔断计数。

        Returns:
            True: 成功
            False: 任何失败（不抛异常），自动累加熔断计数。
        """
        sldprt_path = str(os.fspath(sldprt_path))
        step_out = str(os.fspath(step_out))

        with self._lock:
            if self._unhealthy:
                log.info(
                    "熔断器已开：跳过 convert（系统性故障，call reset_session() 清除）"
                )
                return False

            success = False
            try:
                success = self._do_convert(sldprt_path, step_out)
            except Exception as e:
                log.warning("convert 未预期异常: %s", e)
                success = False

            if success:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    log.error(
                        "COM 熔断触发（连续 %d 次失败）",
                        self._consecutive_failures,
                    )
                    self._unhealthy = True
            return success

    def _do_convert(self, sldprt_path: str, step_out: str) -> bool:
        """启动 worker subprocess，成功则 validate + atomic rename。"""
        # tmp 必须以 .step 结尾（SaveAs3 按扩展名推断格式；.step.tmp 会被 SW
        # 拒为 swFileSaveAsNotSupported=256，SW-B0 spike H3 实证）
        tmp_path = str(Path(step_out).with_suffix(".tmp.step"))
        Path(step_out).parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            _WORKER_MODULE,
            sldprt_path,
            tmp_path,
        ]

        try:
            proc = subprocess.run(
                cmd,
                timeout=SINGLE_CONVERT_TIMEOUT_SEC,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(_PROJECT_ROOT),
            )
        except subprocess.TimeoutExpired:
            log.warning(
                "convert subprocess 超时 %ds，已被 subprocess.run kill；sldprt=%s",
                SINGLE_CONVERT_TIMEOUT_SEC,
                sldprt_path,
            )
            self._cleanup_tmp(tmp_path)
            return False

        if proc.returncode != 0:
            log.warning(
                "convert subprocess rc=%d sldprt=%s stderr=%s",
                proc.returncode,
                sldprt_path,
                (proc.stderr or "")[:300],
            )
            self._cleanup_tmp(tmp_path)
            return False

        if not self._validate_step_file(tmp_path):
            log.warning("convert tmp STEP 校验失败: %s", tmp_path)
            self._cleanup_tmp(tmp_path)
            return False

        os.replace(tmp_path, step_out)
        return True

    @staticmethod
    def _cleanup_tmp(tmp_path: str) -> None:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
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

    def _shutdown_locked(self) -> None:
        """实际 shutdown 逻辑，假设已持 self._lock。"""
        if self._app is not None:
            try:
                self._app.ExitApp()
            except Exception as e:
                # reviewer Minor M-3: shutdown COM 异常记 debug 供 Part 2 排查
                log.debug("COM ExitApp 异常（忽略）: %s", e)
            self._app = None

    def shutdown(self) -> None:
        """外部入口：acquire self._lock 后 shutdown。"""
        with self._lock:
            self._shutdown_locked()


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
