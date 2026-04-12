"""SW 路由集成测试 — get_material_type_keywords / get_material_preset_keywords。

验证：
  - 无 SW 环境时（mock ImportError）返回值与基础字典一致
  - classify_material_type() 行为不变
  - get_material_preset_keywords() 无 SW 时等于 _MAT_PRESET
"""

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
