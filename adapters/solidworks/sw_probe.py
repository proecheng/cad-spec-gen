"""SolidWorks 诊断内核 — 纯函数 probe + ProbeResult dataclass。

所有 probe_* 函数：
- 不抛异常（除 KeyboardInterrupt/SystemExit）
- 不 print / 不 sys.exit
- 返回结构化 ProbeResult

被 tools/sw_inspect.py（CLI 格式化）和 scripts/sw_spike_diagnose.py（薄壳）共同调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class ProbeResult:
    """单层探测结果。

    字段：
        layer: 层名（"environment" / "pywin32" / "detect" / ...）
        ok: 本层是否健康（ok 或 warn 视为可用）
        severity: "ok" | "warn" | "fail"
        summary: 一行人读摘要
        data: 结构化字段（JSON schema 定义见 spec §4.4）
        error: 失败时的错误文案（str(exc)[:200]）
        hint: 用户可采取的下一步行动（中文，文本模式缩进打印）
    """

    layer: str
    ok: bool
    severity: Literal["ok", "warn", "fail"]
    summary: str
    data: dict
    error: Optional[str] = None
    hint: Optional[str] = None
