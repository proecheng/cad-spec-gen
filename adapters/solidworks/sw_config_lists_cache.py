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
