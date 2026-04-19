"""sw_preflight/io.py — SolidWorks 装配体检测 + 等关闭轮询（Task 9）。

职责（Task 9 范围）：
- `_count_open_assemblies()`：数当前 SW 里打开的装配体数量；任何异常返 0。
- `wait_for_assembly_close(timeout_sec, poll_interval)`：轮询等装配体全关，
  超时返 False。

设计决策：
1. **独立 COM Dispatch**，不经 `adapters.solidworks.sw_com_session`。
   sw_com_session 是 subprocess-based 的 sldprt→STEP 转换会话，包含熔断状态，
   用例与"查当前 SW 里开了哪些文档"不同；耦合过去会把查询失败算进转换熔断。
2. **import 在函数体内**：pythoncom / win32com.client 仅在 Windows 有，
   模块级 import 会让非 Windows 平台一 import sw_preflight.io 就炸，
   破坏 collection。函数体内 try 包裹后非 Windows 或无 pywin32 返 0。
3. **异常一律返 0**：SW 不在跑 / COM 调用失败 / Dispatch 抛都视为"当前
   0 个装配体打开"，不阻塞 preflight 流程；真问题在调用方（orchestrator）
   用 SwInfo.installed 这类上游 detect 结果识别，不由这里判断。

tkinter dialog / STEP 校验等属 Task 10/11，不归这里。
"""

from __future__ import annotations

import time


def _count_open_assemblies() -> int:
    """数当前 SW 里打开的装配体数量。

    走独立 pythoncom + win32com.client Dispatch，与 sw_com_session 转换器解耦。
    任何失败（非 Windows / 无 pywin32 / SW 不在跑 / COM 异常）一律返回 0，
    视为"当前 0 个装配体打开"；不抛异常、不污染调用方。

    实现细节：
    - `SldWorks.Application` Dispatch 获取活动 SW 实例；SW 未跑时 Dispatch 抛。
    - `GetDocuments()` 返回 COM tuple[IModelDoc2]，空时可能返 None / ()。
    - 每个 doc 的 `GetType()` 返回 swDocumentTypes_e 枚举：
      swDocPART=1 / swDocASSEMBLY=2 / swDocDRAWING=3。
    - `getattr(d, "GetType", lambda: 0)` 兜底：万一 doc 不是 IModelDoc2
      （理论上不会），按非装配处理。
    """
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            sw_app = win32com.client.Dispatch("SldWorks.Application")
            docs = sw_app.GetDocuments()  # 返回 COM tuple of IModelDoc2 或 None
            # swDocASSEMBLY = 2（SolidWorks API 常量）
            return sum(
                1 for d in (docs or ()) if getattr(d, "GetType", lambda: 0)() == 2
            )
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        return 0


def wait_for_assembly_close(
    timeout_sec: float = 300.0, poll_interval: float = 1.0
) -> bool:
    """轮询等 SW 里所有装配体关闭。

    Args:
        timeout_sec: 最长等待秒数。超时返 False。
        poll_interval: 两次探测之间的 sleep 秒数。

    Returns:
        True — 在 timeout 内观察到装配体全关。
        False — timeout 到了仍有装配体打开。

    语义：进入时先做一次探测；若已 0 则立即返回 True，不 sleep。否则进循环
    sleep + 探测直到 0 或超时。
    """
    start = time.time()
    while time.time() - start < timeout_sec:
        if _count_open_assemblies() == 0:
            return True
        time.sleep(poll_interval)
    return False
