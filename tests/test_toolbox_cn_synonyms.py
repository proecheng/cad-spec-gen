"""sw_toolbox_catalog 中英文同义词扩展测试（spec §13 / 决策 #34）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestLoadCnSynonyms:
    def test_load_returns_flattened_dict(self):
        """load_cn_synonyms 把分组 YAML 打平为 {cn_key: [en_tokens]}。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms

        synonyms = load_cn_synonyms()
        assert isinstance(synonyms, dict)
        assert "螺钉" in synonyms
        assert synonyms["螺钉"] == ["screw"]
        assert "深沟球" in synonyms
        assert synonyms["深沟球"] == ["deep", "groove", "ball"]

    def test_load_is_cached(self):
        """连续调用返回同一 dict 实例（lru_cache 验证）。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms

        a = load_cn_synonyms()
        b = load_cn_synonyms()
        assert a is b

    def test_load_respects_custom_path(self, tmp_path):
        """支持从参数指定 yaml 路径（测试隔离用）。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms

        custom = tmp_path / "custom.yaml"
        custom.write_text("group1:\n  测试: [test]\n", encoding="utf-8")
        # 注意: 带参数版本不过 lru_cache
        result = load_cn_synonyms(path=custom)
        assert result == {"测试": ["test"]}
