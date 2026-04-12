"""SW 路由集成测试 — get_material_type_keywords / get_material_preset_keywords。

验证：
  - 无 SW 环境时（mock ImportError）返回值与基础字典一致
  - classify_material_type() 行为不变
  - get_material_preset_keywords() 无 SW 时等于 _MAT_PRESET
  - detect_environment() 含 enhancements 字段、level 不受 SW 影响
  - reset_all_sw_caches() 联动清除 cad_pipeline 缓存
"""

import sys
from unittest.mock import patch

import pytest


# ── Task 4: cad_spec_defaults 测试 ──────────────────────────────────────


class TestGetMaterialTypeKeywords:
    """get_material_type_keywords() 基础行为。"""

    def test_get_material_type_keywords_without_sw_equals_base(self):
        """无 SW 时返回值 == MATERIAL_TYPE_KEYWORDS（深拷贝，内容一致）。"""
        from cad_spec_defaults import (
            MATERIAL_TYPE_KEYWORDS,
            _reset_material_cache,
            get_material_type_keywords,
        )

        _reset_material_cache()
        # 模拟非 Windows 平台，跳过 SW 分支
        with patch("cad_spec_defaults.sys") as mock_sys:
            mock_sys.platform = "linux"
            result = get_material_type_keywords()
        assert result == MATERIAL_TYPE_KEYWORDS
        # 确保是深拷贝，修改返回值不影响原始数据
        assert result is not MATERIAL_TYPE_KEYWORDS

    def test_classify_material_type_unchanged(self):
        """classify_material_type 行为不变。"""
        from cad_spec_defaults import _reset_material_cache, classify_material_type

        _reset_material_cache()
        # 模拟非 Windows 平台，确保纯基础路由表
        with patch("cad_spec_defaults.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert classify_material_type("7075-T6铝合金") == "al"
            assert classify_material_type("SUS304不锈钢") == "steel"
            assert classify_material_type("PEEK") == "peek"
            assert classify_material_type("FKM橡胶") == "rubber"
            assert classify_material_type("PA66") == "nylon"
            assert classify_material_type("unknown") is None


# ── Task 5: cad_pipeline 测试 ───────────────────────────────────────────


class TestGetMaterialPresetKeywords:
    """get_material_preset_keywords() 基础行为。"""

    def test_get_material_preset_keywords_without_sw_equals_base(self):
        """无 SW 时返回值 == _MAT_PRESET（浅拷贝，内容一致）。"""
        from cad_pipeline import (
            _MAT_PRESET,
            _reset_preset_keywords_cache,
            get_material_preset_keywords,
        )

        _reset_preset_keywords_cache()
        # 模拟非 Windows 平台，跳过 SW 分支
        with patch("cad_pipeline.sys") as mock_sys:
            mock_sys.platform = "linux"
            result = get_material_preset_keywords()
        assert result == _MAT_PRESET
        # 确保是拷贝
        assert result is not _MAT_PRESET


# ── Task 6: env-check 增强源检测测试 ──────────────────────────────────────


class TestEnvCheckEnhancements:
    """detect_environment() 增强源检测。"""

    @staticmethod
    def _import_check_env():
        """将 tools/hybrid_render/ 临时加入 sys.path 并导入 check_env。"""
        import importlib
        import os

        check_env_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "tools", "hybrid_render")
        )
        if check_env_dir not in sys.path:
            sys.path.insert(0, check_env_dir)
        # 强制重新导入，避免缓存
        if "check_env" in sys.modules:
            return importlib.reload(sys.modules["check_env"])
        return importlib.import_module("check_env")

    def test_env_check_has_enhancements_key(self):
        """detect_environment() 返回值包含 enhancements.solidworks.ok 字段。"""
        check_env = self._import_check_env()
        result = check_env.detect_environment()
        assert "enhancements" in result
        assert "solidworks" in result["enhancements"]
        assert "ok" in result["enhancements"]["solidworks"]

    def test_env_check_level_unchanged_by_sw(self):
        """level 值在 1-5 范围内（SW 有无不影响）。"""
        check_env = self._import_check_env()
        result = check_env.detect_environment()
        assert 1 <= result["level"] <= 5


# ── Task 7: reset_all_sw_caches 联动清除测试 ──────────────────────────────


class TestResetAllSwCaches:
    """reset_all_sw_caches() 联动清除所有下游缓存。"""

    def test_reset_all_sw_caches_clears_everything(self):
        """调用 reset 后，cad_spec_defaults._merged_keywords 和
        cad_pipeline._preset_keywords_merged 都为 None。"""
        import cad_pipeline
        import cad_spec_defaults
        from adapters.solidworks.sw_material_bridge import reset_all_sw_caches

        # 先触发 cad_spec_defaults 缓存填充（用 mock 跳过 SW 分支）
        cad_spec_defaults._reset_material_cache()
        with patch("cad_spec_defaults.sys") as mock_sys:
            mock_sys.platform = "linux"
            cad_spec_defaults.get_material_type_keywords()
        assert cad_spec_defaults._merged_keywords is not None

        # 先触发 cad_pipeline preset 缓存填充
        cad_pipeline._reset_preset_keywords_cache()
        with patch("cad_pipeline.sys") as mock_sys:
            mock_sys.platform = "linux"
            cad_pipeline.get_material_preset_keywords()
        assert cad_pipeline._preset_keywords_merged is not None

        # 调用统一重置
        reset_all_sw_caches()

        # 验证 cad_spec_defaults 缓存已被清除
        assert cad_spec_defaults._merged_keywords is None
        # 验证 cad_pipeline preset 缓存也已被清除
        assert cad_pipeline._preset_keywords_merged is None
