"""sw_toolbox_catalog 单元测试（v4 决策 #14/#18/#19/#20/#21/#12）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path
from unittest.mock import MagicMock

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

        result = extract_size_from_name(
            "M6×20 内六角螺钉", default_patterns["fastener"]
        )
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

        result = extract_size_from_name(
            "1/4-20 UNC hex bolt", default_patterns["fastener"]
        )
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

        result = extract_size_from_name(
            "深沟球轴承 6205-2RS", default_patterns["bearing"]
        )
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
        from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns

        # Classic ReDoS: nested quantifier on alternation
        patterns = {
            "fastener": {
                "size": r"(a+)+$",  # catastrophic backtracking
            },
        }
        with pytest.raises((RuntimeError, ValueError)) as exc_info:
            validate_size_patterns(patterns)
        assert (
            "ReDoS" in str(exc_info.value) or "timeout" in str(exc_info.value).lower()
        )

    def test_malformed_regex_rejected(self):
        import re
        from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns

        patterns = {"fastener": {"size": r"[unclosed"}}
        with pytest.raises((re.error, ValueError)):
            validate_size_patterns(patterns)

    def test_subprocess_launch_failure_raises_runtime_error_not_redos(
        self, monkeypatch
    ):
        """I2: subprocess 启动失败（FileNotFoundError）应抛 RuntimeError 含 '启动失败'。
        关键点：不应是 validate_size_patterns 发出的 "ReDoS suspected" 消息，
        而是 _test_pattern_safe 本身抛出的环境错误（消息含 '启动失败'）。"""
        from adapters.solidworks.sw_toolbox_catalog import _test_pattern_safe
        import adapters.solidworks.sw_toolbox_catalog as catalog_mod

        monkeypatch.setattr(
            catalog_mod.subprocess,
            "run",
            MagicMock(side_effect=FileNotFoundError("python not found")),
        )
        with pytest.raises(RuntimeError) as exc_info:
            _test_pattern_safe(r"\d+")
        msg = str(exc_info.value)
        # 必须含 '启动失败' 说明是环境错误，不是 ReDoS suspected
        assert "启动失败" in msg, f"消息应含 '启动失败'，实际: {msg!r}"
        # 不应含 'suspected'（validate_size_patterns 的 ReDoS 误报关键词）
        assert "suspected" not in msg.lower(), (
            f"不应含 'suspected'（ReDoS 误报），实际: {msg!r}"
        )

    def test_subprocess_nonzero_exit_raises_runtime_error_not_redos(self, monkeypatch):
        """I2: 子进程以非零返回码退出（segfault / AV kill 等）应抛 RuntimeError 含
        '异常退出'，不能被误报为 "ReDoS suspected"。"""
        from adapters.solidworks.sw_toolbox_catalog import _test_pattern_safe
        import adapters.solidworks.sw_toolbox_catalog as catalog_mod

        fake_result = MagicMock()
        fake_result.returncode = 1
        fake_result.stdout = ""
        fake_result.stderr = "Segmentation fault"
        monkeypatch.setattr(
            catalog_mod.subprocess,
            "run",
            MagicMock(return_value=fake_result),
        )
        with pytest.raises(RuntimeError) as exc_info:
            _test_pattern_safe(r"\d+")
        msg = str(exc_info.value)
        # 必须含 '异常退出' 说明是环境错误，不是 ReDoS suspected
        assert "异常退出" in msg, f"消息应含 '异常退出'，实际: {msg!r}"
        # 不应含 'suspected'（validate_size_patterns 的 ReDoS 误报关键词）
        assert "suspected" not in msg.lower(), (
            f"不应含 'suspected'（ReDoS 误报），实际: {msg!r}"
        )


class TestExtractSizeDefensive:
    """M5: 类型守卫 — yaml 有非 str 键时不崩溃。"""

    def test_extra_non_str_key_does_not_crash(self):
        """patterns 里有 list 类型的额外键（如改名后的 exclude 或元数据键），
        extract_size_from_name 应静默跳过而非抛 TypeError。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        patterns = {
            "size": r"[Mm](\d+(?:\.\d+)?)",
            "length": r"[×xX*\-\s](\d+(?:\.\d+)?)",
            "exclude_patterns": [r"UNC", r"\bTr\d"],  # 标准的 list 键
            "other_meta": [1, 2, 3],  # 假设 yaml 多余键
            "version": {"nested": "dict"},  # 嵌套 dict 也跳过
        }
        # 不应抛 TypeError
        result = extract_size_from_name("M6×20 螺钉", patterns)
        assert result == {"size": "M6", "length": "20"}


class TestToolboxFingerprint:
    """v4 决策 #21: 索引完整性校验 + 决策 #17 Path.home 兼容。"""

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    def test_fingerprint_stable_on_repeat(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import _compute_toolbox_fingerprint

        fp1 = _compute_toolbox_fingerprint(fake_toolbox)
        fp2 = _compute_toolbox_fingerprint(fake_toolbox)
        assert fp1 == fp2
        assert len(fp1) == 40  # SHA1 hex

    def test_fingerprint_changes_when_file_added(self, fake_toolbox, tmp_path):
        import shutil
        from adapters.solidworks.sw_toolbox_catalog import _compute_toolbox_fingerprint

        # 将 fixture 复制到 tmp_path 再添加文件
        target = tmp_path / "fake_toolbox"
        shutil.copytree(fake_toolbox, target)
        fp_before = _compute_toolbox_fingerprint(target)

        (target / "GB" / "new_part.sldprt").write_bytes(b"")
        fp_after = _compute_toolbox_fingerprint(target)
        assert fp_before != fp_after

    def test_fingerprint_missing_dir_returns_unavailable(self, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import _compute_toolbox_fingerprint

        fp = _compute_toolbox_fingerprint(tmp_path / "does-not-exist")
        assert fp == "unavailable"


class TestBuildToolboxIndex:
    """v4 §5.1: 仅接受 .sldprt，过滤 .xls/.slddrw/.sldlfp/.xml。"""

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    def test_index_has_schema_version(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import (
            build_toolbox_index,
            SCHEMA_VERSION,
        )

        idx = build_toolbox_index(fake_toolbox)
        assert idx["schema_version"] == SCHEMA_VERSION

    def test_index_has_fingerprint(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index

        idx = build_toolbox_index(fake_toolbox)
        assert "toolbox_fingerprint" in idx
        assert len(idx["toolbox_fingerprint"]) == 40

    def test_index_filters_non_sldprt(self, fake_toolbox):
        """决策 §5.1: sizes.xls / sample.slddrw / catalog.xml 必须被过滤。"""
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index

        idx = build_toolbox_index(fake_toolbox)
        flat_paths = []
        for std in idx["standards"].values():
            for sub in std.values():
                for p in sub:
                    flat_paths.append(p.filename)
        assert not any(f.endswith(".xls") for f in flat_paths)
        assert not any(f.endswith(".slddrw") for f in flat_paths)
        assert not any(f.endswith(".xml") for f in flat_paths)
        # 所有入库的都是 sldprt
        assert all(f.endswith(".sldprt") for f in flat_paths)

    def test_index_populates_gb_bolts(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index

        idx = build_toolbox_index(fake_toolbox)
        assert "GB" in idx["standards"]
        assert "bolts and studs" in idx["standards"]["GB"]
        bolts = idx["standards"]["GB"]["bolts and studs"]
        filenames = {p.filename for p in bolts}
        assert "hex bolt.sldprt" in filenames
        assert "stud.sldprt" in filenames

    def test_index_populates_iso_and_din(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index

        idx = build_toolbox_index(fake_toolbox)
        assert "ISO" in idx["standards"]
        assert "DIN" in idx["standards"]
