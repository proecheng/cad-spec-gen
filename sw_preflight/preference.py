"""sw_preflight/preference.py — 跨 run 的用户版本偏好持久化（Task 5）。

多版本 SolidWorks 共存时，用户可通过 $HOME/.cad-spec-gen/sw_version_preference.json
指定常用年份版本。优先级由 sw_detect._select_version 统一裁决：
env (CAD_SPEC_GEN_SW_PREFERRED_YEAR) > 本模块 preference.json > 最新已安装版。

模块内只负责 I/O，不做校验（版本是否实际安装由 sw_detect 验证）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 偏好文件路径；测试通过 monkeypatch 覆盖此常量到 tmp_path。
PREFERENCE_PATH = Path.home() / ".cad-spec-gen" / "sw_version_preference.json"


def read_preference() -> Optional[int]:
    """读取 preferred_year 字段。

    Returns:
        已设置的年份 int；文件不存在 / JSON 解析失败 / 字段缺失 → None。
    """
    if not PREFERENCE_PATH.exists():
        return None
    try:
        data = json.loads(PREFERENCE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    value = data.get("preferred_year") if isinstance(data, dict) else None
    if isinstance(value, int):
        return value
    return None


def write_preference(year: int) -> None:
    """将 preferred_year 写入偏好文件（含 UTC 时间戳）。

    父目录不存在时自动创建。任何 I/O 异常由调用方捕获。
    """
    PREFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "preferred_year": year,
        "set_at": datetime.now(timezone.utc).isoformat(),
    }
    PREFERENCE_PATH.write_text(json.dumps(data), encoding="utf-8")
