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
        assert synonyms["螺钉"] == ["screw", "screws"]
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

    def test_bearing_miniature_synonym_exists(self):
        """微型 → miniature 同义词须存在，确保微型轴承 token 扩展正确。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms, _load_cn_synonyms_cached

        _load_cn_synonyms_cached.cache_clear()
        synonyms = load_cn_synonyms()
        assert "微型" in synonyms, "缺少 '微型' 同义词条目"
        assert "miniature" in synonyms["微型"]


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


class TestEndToEndMatchWithSynonyms:
    """端到端：BOM name_cn 中文 → Toolbox 英文零件命中。"""

    def test_gb_70_1_m6_20_hits_socket_head_cap_screw(self):
        """GB/T 70.1 M6×20 内六角圆柱头螺钉 匹配 'hexagon socket head cap screws' sldprt。

        fake_index 文件名为真实 toolbox 的 hexagon 前缀形式（SW-C 同义词表补充后）。
        权重使用生产配置（part_no: 0.0），内部 ID token 不注入。
        """
        from adapters.solidworks.sw_toolbox_catalog import (
            SwToolboxPart,
            build_query_tokens_weighted,
            match_toolbox_part,
        )

        # 伪造含一条 GB 内六角圆柱头螺钉 M6 的索引（文件名贴近真实 toolbox）
        fake_index = {
            "standards": {
                "GB": {
                    "bolts and studs": [
                        SwToolboxPart(
                            standard="GB",
                            subcategory="bolts and studs",
                            sldprt_path="/fake/GB/hexagon socket head cap screws gb.sldprt",
                            filename="hexagon socket head cap screws gb.sldprt",
                            tokens=["hexagon", "socket", "head", "cap", "screws", "gb"],
                        ),
                    ]
                }
            }
        }

        class Query:
            part_no = "GIS-DEMO-001"
            name_cn = "GB/T 70.1 M6×20 内六角圆柱头螺钉"
            material = "钢"

        weights = {"part_no": 0.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}
        q_tokens = build_query_tokens_weighted(Query(), {"size": "M6"}, weights)

        # 内部 ID token 不应注入（part_no=0.0 生产配置）
        q_map = dict(q_tokens)
        assert "gis" not in q_map
        assert "demo" not in q_map
        # 同义词扩展已注入关键匹配 token
        assert "socket" in q_map
        assert "screw" in q_map
        assert "hex" in q_map
        assert "hexagon" in q_map

        # 端到端匹配（生产阈值 0.30）
        result = match_toolbox_part(
            fake_index,
            q_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        assert result is not None
        part, score = result
        assert part.filename == "hexagon socket head cap screws gb.sldprt"
        assert score >= 0.30


class TestNewSynonyms:
    """SW-C: 验证 hexagon + 六角头 + 复数形式。"""

    def _expand(self, name_cn, synonyms):
        from adapters.solidworks.sw_toolbox_catalog import tokenize, expand_cn_synonyms
        base = [(t, 1.0) for t in tokenize(name_cn)]
        expanded = expand_cn_synonyms(base, synonyms)
        return {t for t, _ in expanded}

    def test_neiliujiao_expands_to_hexagon(self):
        """内六角 → hexagon（toolbox 文件用 hexagon，不只是 hex）。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms
        syns = load_cn_synonyms()
        tokens = self._expand("内六角圆柱头螺钉", syns)
        assert "hexagon" in tokens

    def test_liujiaotou_expands_to_head(self):
        """六角头 → hexagon + head（匹配 hexagon head bolts）。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms
        syns = load_cn_synonyms()
        tokens = self._expand("六角头螺栓", syns)
        assert "hexagon" in tokens
        assert "head" in tokens

    def test_luomu_expands_to_nuts(self):
        """螺母 → nut + nuts（toolbox 有 'nuts' token）。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms
        syns = load_cn_synonyms()
        tokens = self._expand("六角螺母", syns)
        assert "nut" in tokens
        assert "nuts" in tokens

    def test_dianjuan_expands_to_washers(self):
        """垫圈 → washer + washers。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms
        syns = load_cn_synonyms()
        tokens = self._expand("平垫圈", syns)
        assert "washers" in tokens

    def test_zhoucheng_expands_to_bearings(self):
        """轴承 → bearing + bearings。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms
        syns = load_cn_synonyms()
        tokens = self._expand("深沟球轴承", syns)
        assert "bearings" in tokens
