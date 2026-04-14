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


class TestExpandCnSynonyms:
    def test_cjk_token_substring_match_injects_en_tokens(self):
        """含 '内六角' 的 CJK token 应注入 [hex, socket]。"""
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        synonyms = {"内六角": ["hex", "socket"], "螺钉": ["screw"]}
        input_tokens = [("内六角圆柱头螺钉", 1.0)]  # 单个长 CJK token
        result = expand_cn_synonyms(input_tokens, synonyms)

        result_map = dict(result)
        assert "内六角圆柱头螺钉" in result_map  # 原 token 保留
        assert result_map["hex"] == 1.0          # 注入同权重
        assert result_map["socket"] == 1.0
        assert result_map["screw"] == 1.0

    def test_ascii_tokens_passthrough(self):
        """非 CJK token 不受影响。"""
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        input_tokens = [("m6", 1.0), ("hex", 1.5)]
        result = expand_cn_synonyms(input_tokens, {"螺钉": ["screw"]})
        assert dict(result) == {"m6": 1.0, "hex": 1.5}

    def test_duplicate_en_keeps_max_weight(self):
        """多源注入同一 en token 时取最大权重。"""
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        # '螺钉' -> [screw], '螺栓' -> [bolt, screw], 两个 CJK token 都含 '螺'
        synonyms = {"螺钉": ["screw"], "螺栓": ["bolt", "screw"]}
        input_tokens = [("螺钉", 1.0), ("螺栓", 2.0)]
        result = dict(expand_cn_synonyms(input_tokens, synonyms))

        assert result["screw"] == 2.0  # 取 max
        assert result["bolt"] == 2.0

    def test_empty_synonyms_noop(self):
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        input_tokens = [("螺钉", 1.0)]
        assert list(expand_cn_synonyms(input_tokens, {})) == input_tokens

    def test_empty_input_returns_empty(self):
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        assert expand_cn_synonyms([], {"螺钉": ["screw"]}) == []
