"""sw_toolbox_catalog 单元测试（v4 决策 #14/#18/#19/#20/#21/#12）。"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from adapters.solidworks.sw_toolbox_catalog import (
    SwToolboxPart,
    SCHEMA_VERSION,
)


class TestSwToolboxPartDataclass:
    """v4 决策 #14: Sw 前缀命名一致。"""

    def test_dataclass_has_required_fields(self):
        p = SwToolboxPart(
            standard="GB",
            subcategory="bolts and studs",
            sldprt_path="/some/path/hex bolt.sldprt",
            filename="hex bolt.sldprt",
            tokens=["hex", "bolt"],
        )
        assert p.standard == "GB"
        assert p.subcategory == "bolts and studs"
        assert p.sldprt_path.endswith("hex bolt.sldprt")
        assert p.filename == "hex bolt.sldprt"
        assert p.tokens == ["hex", "bolt"]

    def test_schema_version_exported(self):
        """v4 决策 #21: SCHEMA_VERSION 必须存在且为正整数。"""
        assert isinstance(SCHEMA_VERSION, int)
        assert SCHEMA_VERSION >= 1


class TestTokenize:
    """v4 决策 #18: 拆分 + 小写 + stop_words 过滤，避免 'and/for' 污染打分。"""

    def test_tokenize_ascii_lowercase(self):
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        assert tokenize("Hex Bolt") == ["hex", "bolt"]

    def test_tokenize_drops_stop_words(self):
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        result = tokenize("bolts and studs")
        assert "and" not in result
        assert "bolts" in result and "studs" in result

    def test_tokenize_splits_underscore_and_hyphen(self):
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        assert tokenize("socket_head-cap screw") == ["socket", "head", "cap", "screw"]

    def test_tokenize_handles_cjk(self):
        """中英文混合："""
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        result = tokenize("六角 hex bolt")
        assert "hex" in result
        assert "bolt" in result
        # CJK 整体保留
        assert "六角" in result

    def test_tokenize_empty_returns_empty(self):
        from adapters.solidworks.sw_toolbox_catalog import tokenize
        assert tokenize("") == []
        assert tokenize("   ") == []


class TestExtractSize:
    """v4 §1.3 范围外螺纹 → None；v4 决策 #9 抽不到 → None → miss。"""

    @pytest.fixture
    def default_patterns(self):
        return {
            "fastener": {
                "size": r"[Mm](\d+(?:\.\d+)?)",
                "length": r"[×xX*\-\s](\d+(?:\.\d+)?)",
                "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
            },
            "bearing": {
                "model": r"\b(\d{4,5})\b",
            },
        }

    def test_fastener_m6x20_multiplication_sign(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("M6×20 内六角螺钉", default_patterns["fastener"])
        assert result == {"size": "M6", "length": "20"}

    def test_fastener_m6x20_ascii_x(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("M6x20 hex bolt", default_patterns["fastener"])
        assert result == {"size": "M6", "length": "20"}

    def test_fastener_m6_hyphen_20(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("M6-20 螺钉", default_patterns["fastener"])
        assert result == {"size": "M6", "length": "20"}

    def test_fastener_decimal_thread(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("M6.5×20", default_patterns["fastener"])
        assert result == {"size": "M6.5", "length": "20"}

    def test_fastener_unc_returns_none(self, default_patterns):
        """v4 §1.3: UNC 范围外 → None。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("1/4-20 UNC hex bolt", default_patterns["fastener"])
        assert result is None

    def test_fastener_trapezoidal_returns_none(self, default_patterns):
        """v4 §1.3: 梯形螺纹范围外 → None。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("Tr16×2 丝杠", default_patterns["fastener"])
        assert result is None

    def test_fastener_pipe_thread_returns_none(self, default_patterns):
        """v4 §1.3: 管螺纹范围外 → None。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("G1/2 接头", default_patterns["fastener"])
        assert result is None

    def test_fastener_no_size_returns_none(self, default_patterns):
        """v4 决策 #9: 抽不到尺寸 → None → 调用方 miss。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("非标件定制", default_patterns["fastener"])
        assert result is None

    def test_bearing_6205(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("深沟球轴承 6205", default_patterns["bearing"])
        assert result == {"model": "6205"}

    def test_bearing_suffix_preserved_only_base(self, default_patterns):
        """v4 §1.3 已知限制: 6205-2RS 只抽 6205。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name
        result = extract_size_from_name("深沟球轴承 6205-2RS", default_patterns["bearing"])
        assert result == {"model": "6205"}


class TestValidateSizePatterns:
    """v4 决策 #19: ReDoS 防御 — 加载时 timeout 预验证。"""

    def test_valid_patterns_pass(self):
        from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns
        patterns = {
            "fastener": {
                "size": r"[Mm](\d+(?:\.\d+)?)",
                "length": r"[×xX](\d+)",
            },
        }
        # Should not raise
        validate_size_patterns(patterns)

    def test_redos_pattern_rejected(self):
        import re
        from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns
        # Classic ReDoS: nested quantifier on alternation
        patterns = {
            "fastener": {
                "size": r"(a+)+$",  # catastrophic backtracking
            },
        }
        with pytest.raises((RuntimeError, ValueError)) as exc_info:
            validate_size_patterns(patterns)
        assert "ReDoS" in str(exc_info.value) or "timeout" in str(exc_info.value).lower()

    def test_malformed_regex_rejected(self):
        import re
        from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns
        patterns = {"fastener": {"size": r"[unclosed"}}
        with pytest.raises((re.error, ValueError)):
            validate_size_patterns(patterns)
