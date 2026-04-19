"""sw_preflight/cache.py — 跨进程 IPC + TTL 的 sw_preflight_cache.json（Task 19）。

doctor / codegen / main 入口共享同一份 preflight 结果：
  * 同一次运行内避免重复 COM Dispatch 探测；
  * 超过 ttl_seconds 或 schema_version 不匹配时视为失效，回退到重新探测。

schema_version 变更即破坏兼容，调用方读到 None 就应该当作无缓存。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 序列化格式版本；字段增删/语义变更时 +1。
SCHEMA_VERSION = 1


def write_cache(
    path: Path,
    payload: dict,
    ttl_sec: int = 300,
    ran_by_entry: str = "unknown",
) -> None:
    """把 payload + 元数据一次写入到 path（JSON 文本）。

    Args:
        path: 目标文件；父目录不存在会被创建。
        payload: 业务字段（如 sw_year / diagnosis_code）；会与元数据合并。
        ttl_sec: 缓存有效期秒数，read_cache 超过则返回 None。
        ran_by_entry: 首次生成该缓存的入口（用于排查多入口互相覆盖）。
    """
    data = {
        "schema_version": SCHEMA_VERSION,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ran_by_entry": ran_by_entry,
        "ttl_seconds": ttl_sec,
        **payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # default=str 兜底处理 dataclass / Path 等非原生类型序列化
    path.write_text(json.dumps(data, default=str), encoding="utf-8")


def read_cache(path: Path) -> Optional[dict]:
    """读取并校验缓存；不可用时返回 None（调用方需要重新探测）。

    失效判定顺序：
      1. 文件不存在
      2. JSON / IO 异常
      3. schema_version 不匹配
      4. ran_at 距今 > ttl_seconds
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        return None
    ran_at = datetime.fromisoformat(data["ran_at"])
    age_sec = (datetime.now(timezone.utc) - ran_at).total_seconds()
    if age_sec > data.get("ttl_seconds", 300):
        return None
    return data
