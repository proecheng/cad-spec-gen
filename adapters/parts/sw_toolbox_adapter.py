"""
adapters/parts/sw_toolbox_adapter.py — SolidWorks Toolbox COM adapter。

实现 PartsAdapter 接口。is_available() 做 6 项检查（v4 §5.3）；
resolve() 编排 catalog 匹配 + com_session 转换（Task 9 实现）。

熔断状态委托给 SwComSession（v4 决策 #22）。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from adapters.parts.base import PartsAdapter

log = logging.getLogger(__name__)


class SwToolboxAdapter(PartsAdapter):
    """v4 决策 #14: 从 SolidWorksToolboxAdapter 改名为 SwToolboxAdapter。"""

    name = "sw_toolbox"

    def __init__(self, project_root: str = "", config: Optional[dict] = None) -> None:
        self.project_root = project_root
        self.config = config or {}

    def is_available(self) -> bool:
        """v4 §5.3: 6 项检查全通过。

        检查顺序（短路优先）：
        1. 非 Windows 平台 → False
        2. SolidWorks 未安装 → False
        3. 版本低于 2024 → False
        4. pywin32 不可用 → False
        5. Toolbox 目录为空 → False
        6. Toolbox Add-In 未启用 → False（v4 决策 #13）
        7. SwComSession 熔断 → False（v4 决策 #22）
        """
        if sys.platform != "win32":
            return False

        try:
            from adapters.solidworks.sw_detect import detect_solidworks
            from adapters.solidworks.sw_com_session import get_session
        except ImportError:
            return False

        info = detect_solidworks()
        if not info.installed:
            return False
        if info.version_year < 2024:
            return False
        if not info.pywin32_available:
            return False
        if not info.toolbox_dir:
            return False
        if not info.toolbox_addin_enabled:
            return False

        # v4 决策 #22: 熔断委托给 SwComSession
        session = get_session()
        if not session.is_healthy():
            return False

        return True

    def can_resolve(self, query) -> bool:
        """总是 True（具体匹配由 resolve 决定）。"""
        return True

    def resolve(self, query, spec: dict):
        """resolve 实现留给 Task 9（主编排流程）。"""
        raise NotImplementedError("implemented in Task 9")

    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        """probe_dims 实现留给 Task 9。"""
        raise NotImplementedError("implemented in Task 9")
