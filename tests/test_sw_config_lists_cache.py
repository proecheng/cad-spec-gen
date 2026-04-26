"""Task 14.6：sw_config_lists_cache module 单元测试（spec §6.1 A+B 矩阵）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestModuleConstants:
    def test_module_imports_and_has_schema_version(self):
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        assert cache_mod.CONFIG_LISTS_SCHEMA_VERSION == 1

    def test_cache_path_is_user_level(self):
        from adapters.solidworks.sw_config_lists_cache import get_config_lists_cache_path
        p = get_config_lists_cache_path()
        assert p == Path.home() / ".cad-spec-gen" / "sw_config_lists.json"


class TestEmptyCache:
    def test_empty_cache_has_5_fields(self):
        from adapters.solidworks.sw_config_lists_cache import (
            _empty_config_lists_cache,
            CONFIG_LISTS_SCHEMA_VERSION,
        )
        cache = _empty_config_lists_cache()
        assert cache["schema_version"] == CONFIG_LISTS_SCHEMA_VERSION
        assert "generated_at" in cache  # ISO timestamp
        assert cache["sw_version"] is None  # 故意 None → 触发 envelope_invalidated
        assert cache["toolbox_path"] is None
        assert cache["entries"] == {}
