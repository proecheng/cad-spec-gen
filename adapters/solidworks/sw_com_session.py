"""
adapters/solidworks/sw_com_session.py — SolidWorks COM 会话管理。

====== Part 1 / Part 2 交付边界 ======
Part 1 交付（本文件）：
- `SwComSession` 骨架 + `_lock` 保护 + 熔断器（连续 3 次失败）
- `convert_sldprt_to_step` 假设 `self._app` 已设置；atomic write + 大小/magic 校验
- `get_session` / `reset_session` singleton 管理
- 生命周期常量定义（COLD_START_TIMEOUT_SEC 等）

Part 2 将实现（SW-B9 真实 COM 验收时）：
- `start()` 方法 — 实际启动 SW + LoadAddIn Toolbox + 赋值 self._app
  （受 COLD_START_TIMEOUT_SEC 保护）
- `_maybe_restart()` — `_convert_count >= RESTART_EVERY_N_CONVERTS` 时 shutdown+start
- 空闲自动 shutdown — `time.time() - _last_used_ts >= IDLE_SHUTDOWN_SEC`
- `SINGLE_CONVERT_TIMEOUT_SEC` 与 `convert_sldprt_to_step` 的挂靠（可能用 threading 超时中断或 subprocess 超时）

Part 1 单元测试通过直接赋值 `session._app = mock_app` 绕过 `start()`，
生产环境用 Part 1 的 session **不会**真正启动 SW —— resolve 的 cache miss 分支
会在 `_do_convert` 看到 `self._app is None` 后返回 False。

实施 v4 决策 #6/#22/#23/#25（Part 1）+ #10/#11（Part 2）。

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

# v4 决策 #10/#11 行为契约常量 — Part 2 SW-B9 真实 COM 实现时引用
# Part 1 仅定义，不执行对应生命周期逻辑
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

            # Part 2a Task 4: idle shutdown（threading model 规则 6）
            # 先于 restart 检查 —— idle 已 shutdown 时 restart 判断无意义。
            self._maybe_idle_shutdown_locked()

            # Part 2a Task 3: 周期强制重启（决策 #11）
            try:
                self._maybe_restart_locked()
            except Exception as e:
                log.warning("COM 周期重启失败: %s", e)
                return False

            # Part 2a Task 2: _app 未初始化 → 自动触发冷启动（决策 #10）
            # 持锁调用 _start_locked（threading model 规则 5），不重新 acquire。
            if self._app is None:
                try:
                    self._start_locked()
                except Exception as e:
                    log.warning("COM 冷启动失败: %s", e)
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
        """实际 COM 调用 + atomic write（v4 决策 #23）。

        OpenDoc6 / SaveAs3 的 OUT 参数必须以 VARIANT BYREF I4 传递，否则
        pywin32 late-bind 会抛 DISP_E_TYPEMISMATCH / DISP_E_PARAMNOTOPTIONAL
        （SW-B0 spike 实证；见 scripts/sw_spike_h1_convert.py）。
        """
        if self._app is None:
            log.warning(
                "SwComSession._app 未初始化；Part 2 需要实现 start() 方法来启动真实 SW。"
                "Part 1 仅单元测试通过 mock 赋值 _app 使用。"
            )
            return False

        tmp_path = step_out + ".tmp"
        Path(step_out).parent.mkdir(parents=True, exist_ok=True)

        import pythoncom
        from win32com.client import VARIANT

        # OpenDoc6: IN (name, type, options, config) + OUT (errors, warnings)
        err_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warn_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        model = self._app.OpenDoc6(
            sldprt_path,
            1,  # swDocPART
            1,  # swOpenDocOptions_Silent
            "",
            err_var,
            warn_var,
        )
        if err_var.value:
            log.warning(
                "OpenDoc6 errors: %s (warnings: %s)",
                err_var.value,
                warn_var.value,
            )
            return False
        if model is None:
            log.warning("OpenDoc6 returned None model for %s", sldprt_path)
            return False

        try:
            # SaveAs3: IN (name, version, options) + 两个可选 IDispatch* +
            # OUT (errors, warnings)。IDispatch* 可选空位必须用 VT_DISPATCH/None。
            export_var = VARIANT(pythoncom.VT_DISPATCH, None)
            advanced_var = VARIANT(pythoncom.VT_DISPATCH, None)
            err2_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn2_var = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            saved = model.Extension.SaveAs3(
                tmp_path,
                0,
                1,
                export_var,
                advanced_var,
                err2_var,
                warn2_var,
            )
            if not saved:
                if err2_var.value:
                    log.warning("SaveAs3 errors: %s", err2_var.value)
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
