"""adapters/solidworks/sw_config_lists_cache.py — SW Toolbox config_list 持久化 cache.

设计参见 docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md (rev 1)。

职责：
- envelope load/save/empty
- 失效信号 _envelope_invalidated (sw_version / toolbox_path) + _config_list_entry_valid (mtime / size)
- 文件锚定：~/.cad-spec-gen/sw_config_lists.json （用户级，跨项目共享）
- 与 broker 解耦：broker 只 import + 调用，envelope 细节全在此 module
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CONFIG_LISTS_SCHEMA_VERSION = 1


def get_config_lists_cache_path() -> Path:
    """用户级 cache 文件路径；与 sw_toolbox_index.json 同目录（catalog.py:70 同模式）。"""
    return Path.home() / ".cad-spec-gen" / "sw_config_lists.json"


def _empty_config_lists_cache() -> dict[str, Any]:
    """返新空 envelope，5 字段全员就位避免 KeyError。

    sw_version=None / toolbox_path=None 是有意：第一次调用 _envelope_invalidated
    会比较 None != detect_solidworks().version_year → True → 整 entries 清重列。
    """
    return {
        "schema_version": CONFIG_LISTS_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sw_version": None,
        "toolbox_path": None,
        "entries": {},
    }


def _save_config_lists_cache(cache: dict[str, Any]) -> None:
    """一次性原子写 cache：先 .tmp 再 os.replace，保证并发读到要么旧文件要么完整新文件。

    parent.mkdir(parents=True, exist_ok=True) 自动建目录。
    """
    path = get_config_lists_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _load_config_lists_cache() -> dict[str, Any]:
    """读 cache；4 类自愈情形返 _empty_config_lists_cache：
    1. 文件不存在
    2. JSON 损坏
    3. OSError (权限/磁盘)
    4. schema_version 不符
    """
    path = get_config_lists_cache_path()
    if not path.exists():
        return _empty_config_lists_cache()
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("config_lists cache 损坏，重建: %s", e)
        return _empty_config_lists_cache()
    if cache.get("schema_version") != CONFIG_LISTS_SCHEMA_VERSION:
        log.info(
            "config_lists schema bump %s → %s，重建",
            cache.get("schema_version"), CONFIG_LISTS_SCHEMA_VERSION,
        )
        return _empty_config_lists_cache()
    return cache


def _stat_mtime(path: str) -> int | None:
    """返 sldprt 文件 mtime epoch int；文件不存在/不可读返 None。"""
    try:
        return int(Path(path).stat().st_mtime)
    except (OSError, FileNotFoundError):
        return None


def _stat_size(path: str) -> int | None:
    """返 sldprt 文件 size bytes；文件不存在/不可读返 None。"""
    try:
        return Path(path).stat().st_size
    except (OSError, FileNotFoundError):
        return None


def _envelope_invalidated(cache: dict[str, Any]) -> bool:
    """Envelope-level 失效判定（spec §4 场景 D）。

    sw_version 或 toolbox_path 任一与当前 detect_solidworks() 结果不符 → True。
    True 时调用方应清空 cache['entries'] 视为全 batch 重列。

    detect_solidworks() 在非 Windows / SW 未装时返 SwInfo(installed=False, version_year=0,
    toolbox_dir="")，此处比较仍 well-defined。
    """
    from adapters.solidworks.sw_detect import detect_solidworks
    info = detect_solidworks()
    if cache.get("sw_version") != info.version_year:
        return True
    if cache.get("toolbox_path") != info.toolbox_dir:
        return True
    return False


def _config_list_entry_valid(cache: dict[str, Any], sldprt_path: str) -> bool:
    """Per-entry 失效判定（spec §4 场景 C）。

    True 当且仅当：
    1. cache['entries'] 含该 sldprt_path
    2. 当前 sldprt 文件 mtime == cache 记录
    3. 当前 sldprt 文件 size == cache 记录

    sldprt 文件已删 → mtime/size = None → 必不等 → False。

    caller 必须传归一化 key（spec §3.1 issue I-1）：通常是
    `sw_config_broker._normalize_sldprt_key(p)` 的输出。
    """
    entry = cache.get("entries", {}).get(sldprt_path)
    if entry is None:
        return False
    current_mtime = _stat_mtime(sldprt_path)
    current_size = _stat_size(sldprt_path)
    if current_mtime is None or current_size is None:
        return False
    if entry.get("mtime") != current_mtime:
        return False
    if entry.get("size") != current_size:
        return False
    return True
