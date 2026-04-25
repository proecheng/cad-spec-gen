"""sw_toolbox_catalog 单元测试（v4 决策 #14/#18/#19/#20/#21/#12）。"""

from __future__ import annotations

import json
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
                "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
            },
            "bearing": {
                "model": r"\b(\d{3,5})(?:[A-Za-z]{1,3})?\b",
            },
        }

    def test_fastener_m6x20_multiplication_sign(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        result = extract_size_from_name(
            "M6×20 内六角螺钉", default_patterns["fastener"]
        )
        assert result == {"size": "M6"}

    def test_fastener_m6x20_ascii_x(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        result = extract_size_from_name("M6x20 hex bolt", default_patterns["fastener"])
        assert result == {"size": "M6"}

    def test_fastener_m6_hyphen_20(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        result = extract_size_from_name("M6-20 螺钉", default_patterns["fastener"])
        assert result == {"size": "M6"}

    def test_fastener_decimal_thread(self, default_patterns):
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        result = extract_size_from_name("M6.5×20", default_patterns["fastener"])
        assert result == {"size": "M6.5"}

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
        """6205-2RS 只抽数字核心 6205，字母后缀被消费但不计入结果。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        result = extract_size_from_name(
            "深沟球轴承 6205-2RS", default_patterns["bearing"]
        )
        assert result == {"model": "6205"}

    def test_fastener_gbt_spec_no_prefix_no_length(self, default_patterns):
        """回归（方案 B 验证）：删除 length 字段后，GB/T 规范号前缀 '70.1'
        不污染结果，×20 也不被抽出，size_dict 仅含 size 键（P1 defer bug）。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        result = extract_size_from_name(
            "GB/T 70.1 M6×20 内六角圆柱头螺钉", default_patterns["fastener"]
        )
        assert result == {"size": "M6"}  # 无 length 键

    def test_bearing_mr105zz_from_material_text(self, default_patterns):
        """MR-series 微型轴承型号在 material 字段中，需用 model_mr 模式提取。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        patterns_with_mr = {
            **default_patterns["bearing"],
            "model_mr": r"\b(MR\d{2,3}[A-Za-z0-9]*)\b",
        }
        result = extract_size_from_name(
            "MR105ZZ（Φ10×Φ5×4mm）", patterns_with_mr
        )
        assert result == {"model_mr": "MR105ZZ"}

    def test_bearing_mr84zz_variant(self, default_patterns):
        """MR84ZZ 等不同尺寸变体均可匹配。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        patterns_with_mr = {
            **default_patterns["bearing"],
            "model_mr": r"\b(MR\d{2,3}[A-Za-z0-9]*)\b",
        }
        result = extract_size_from_name("MR84ZZ bearing", patterns_with_mr)
        assert result == {"model_mr": "MR84ZZ"}

    def test_bearing_608zz_three_digit(self, default_patterns):
        """3 位型号 608ZZ：ZZ 后缀被非捕获组消费，只返回数字核心。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        result = extract_size_from_name("608ZZ 深沟球轴承", default_patterns["bearing"])
        assert result == {"model": "608"}

    def test_bearing_693zz_three_digit(self, default_patterns):
        """3 位薄壁型号 693ZZ：同样只抽数字核心。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        result = extract_size_from_name("693ZZ 薄壁深沟球轴承", default_patterns["bearing"])
        assert result == {"model": "693"}


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
        extract_size_from_name 应静默跳过而非抛 TypeError。
        此 patterns 非生产配置副本，"length" 键保留用于覆盖防御路径。"""
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


class TestPathResolution:
    """v4 决策 #16: yaml > env > 默认；决策 #17: 必须用 Path.home。"""

    def test_cache_root_from_yaml_config(self, tmp_path, monkeypatch):
        """yaml config.cache 优先级最高。"""
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_cache_root

        monkeypatch.setenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", str(tmp_path / "env_cache"))
        result = get_toolbox_cache_root({"cache": str(tmp_path / "yaml_cache")})
        assert result == Path(tmp_path / "yaml_cache")

    def test_cache_root_from_env_when_no_yaml(self, tmp_path, monkeypatch):
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_cache_root

        monkeypatch.setenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", str(tmp_path / "env_cache"))
        result = get_toolbox_cache_root({})
        assert result == Path(tmp_path / "env_cache")

    def test_cache_root_default_uses_path_home(self, monkeypatch, tmp_path):
        """v4 决策 #17: 默认路径必须通过 Path.home()。"""
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_cache_root

        monkeypatch.delenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = get_toolbox_cache_root({})
        assert result == tmp_path / ".cad-spec-gen" / "step_cache" / "sw_toolbox"

    def test_index_path_default_uses_path_home(self, monkeypatch, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_index_path

        monkeypatch.delenv("CAD_SPEC_GEN_SW_TOOLBOX_INDEX", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = get_toolbox_index_path({})
        assert result == tmp_path / ".cad-spec-gen" / "sw_toolbox_index.json"

    def test_does_not_use_expanduser(self, monkeypatch, tmp_path):
        """反例: 使用 os.path.expanduser 会在 conftest monkey 下失效。"""
        from adapters.solidworks.sw_toolbox_catalog import get_toolbox_cache_root

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("CAD_SPEC_GEN_SW_TOOLBOX_CACHE", raising=False)
        monkeypatch.setenv("HOME", "/should/not/be/used")
        result = get_toolbox_cache_root({})
        assert str(result).startswith(str(tmp_path))


class TestLoadToolboxIndex:
    """v4 决策 #21: schema_version 或 fingerprint 不匹配自动重建。"""

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    def test_load_rebuilds_when_cache_missing(self, fake_toolbox, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import (
            load_toolbox_index,
            SCHEMA_VERSION,
        )

        cache = tmp_path / "idx.json"
        assert not cache.exists()
        idx = load_toolbox_index(cache, fake_toolbox)
        assert cache.exists()
        assert idx["schema_version"] == SCHEMA_VERSION

    def test_load_uses_cache_when_fresh(self, fake_toolbox, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import load_toolbox_index

        cache = tmp_path / "idx.json"
        # 第一次调用：构建
        load_toolbox_index(cache, fake_toolbox)
        # 篡改 scan_time 以检测缓存是否被复用
        data = json.loads(cache.read_text(encoding="utf-8"))
        data["scan_time"] = "sentinel-cached"
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        idx2 = load_toolbox_index(cache, fake_toolbox)
        assert idx2["scan_time"] == "sentinel-cached"  # 来自缓存

    def test_load_rebuilds_on_schema_bump(self, fake_toolbox, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import (
            load_toolbox_index,
            SCHEMA_VERSION,
        )

        cache = tmp_path / "idx.json"
        cache.write_text(
            json.dumps(
                {
                    "schema_version": 0,  # 旧版本
                    "scan_time": "old",
                    "toolbox_fingerprint": "unavailable",
                    "standards": {},
                }
            )
        )
        idx = load_toolbox_index(cache, fake_toolbox)
        assert idx["schema_version"] == SCHEMA_VERSION
        assert idx["scan_time"] != "old"

    def test_load_rebuilds_on_fingerprint_mismatch(self, fake_toolbox, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import load_toolbox_index

        cache = tmp_path / "idx.json"
        # 先构建一次
        load_toolbox_index(cache, fake_toolbox)
        # 破坏缓存中的 fingerprint
        data = json.loads(cache.read_text(encoding="utf-8"))
        data["toolbox_fingerprint"] = "0" * 40
        data["scan_time"] = "stale"
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        idx = load_toolbox_index(cache, fake_toolbox)
        assert idx["scan_time"] != "stale"  # 已重建

    def test_load_filters_tampered_paths_on_cache_hit(self, fake_toolbox, tmp_path):
        """I-1 回归: 缓存命中路径（指纹一致）时，篡改的 sldprt_path 必须被过滤。

        场景：攻击者改写 cache JSON 把某 part 的 sldprt_path 指向 toolbox 之外
        （如 C:\\Windows\\System32\\calc.exe），但保持 fingerprint 一致。
        load_toolbox_index 必须在返回前剔除该 part，让下游不必重复校验。
        """
        from adapters.solidworks.sw_toolbox_catalog import load_toolbox_index

        cache = tmp_path / "idx.json"
        # 先合法构建一次
        idx_before = load_toolbox_index(cache, fake_toolbox)
        parts_before = sum(
            len(p) for sub in idx_before["standards"].values() for p in sub.values()
        )
        assert parts_before > 0  # 前置条件

        data = json.loads(cache.read_text(encoding="utf-8"))
        # 找到第一个 part，把 sldprt_path 改成 toolbox_dir 之外的路径
        tampered = False
        outside_path = str(tmp_path / "evil.sldprt")
        for _, sub_dict in data["standards"].items():
            for _, part_list in sub_dict.items():
                if part_list:
                    part_list[0]["sldprt_path"] = outside_path
                    tampered = True
                    break
            if tampered:
                break
        assert tampered
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        # reload — fingerprint 仍一致，走 cache hit 分支
        idx_after = load_toolbox_index(cache, fake_toolbox)
        parts_after = sum(
            len(p) for sub in idx_after["standards"].values() for p in sub.values()
        )
        # 被篡改的那个 part 必须被过滤掉
        assert parts_after == parts_before - 1

        # 任何 part 的 sldprt_path 都不应再指向 outside
        all_paths = [
            p.sldprt_path
            for sub in idx_after["standards"].values()
            for parts in sub.values()
            for p in parts
        ]
        assert outside_path not in all_paths


class TestValidateSldprtPath:
    """v4 决策 #20: sldprt_path 必须是 toolbox_dir 的真子路径。"""

    def test_valid_child_path_returns_true(self, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import _validate_sldprt_path

        toolbox = tmp_path / "toolbox"
        toolbox.mkdir()
        sldprt = toolbox / "GB" / "bolts" / "hex.sldprt"
        sldprt.parent.mkdir(parents=True)
        sldprt.write_bytes(b"")
        assert _validate_sldprt_path(str(sldprt), toolbox) is True

    def test_path_outside_toolbox_returns_false(self, tmp_path):
        from adapters.solidworks.sw_toolbox_catalog import _validate_sldprt_path

        toolbox = tmp_path / "toolbox"
        toolbox.mkdir()
        outside = tmp_path / "evil.sldprt"
        outside.write_bytes(b"")
        assert _validate_sldprt_path(str(outside), toolbox) is False

    def test_path_traversal_rejected(self, tmp_path):
        """恶意索引含 ../../etc/passwd 应被拒绝。"""
        from adapters.solidworks.sw_toolbox_catalog import _validate_sldprt_path

        toolbox = tmp_path / "toolbox"
        toolbox.mkdir()
        traversal = str(toolbox / ".." / "outside.sldprt")
        assert _validate_sldprt_path(traversal, toolbox) is False


class TestMatchToolboxPart:
    """match_toolbox_part 行为测试。

    注：生产配置 part_no=0.0（SW-C 修复，见 YAML 第 65 行），
    本类测试直接传入 query_tokens，不经过 build_query_tokens_weighted，
    可独立验证匹配机制本身（与 part_no 权重配置无关）。
    """

    @pytest.fixture
    def fake_toolbox(self):
        return Path(__file__).parent / "fixtures" / "fake_toolbox"

    @pytest.fixture
    def idx(self, fake_toolbox):
        from adapters.solidworks.sw_toolbox_catalog import build_toolbox_index

        return build_toolbox_index(fake_toolbox)

    def test_match_exact_hex_bolt(self, idx):
        from adapters.solidworks.sw_toolbox_catalog import match_toolbox_part

        query_tokens = [("hex", 1.0), ("bolt", 1.0)]
        result = match_toolbox_part(
            idx,
            query_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        assert result is not None
        part, score = result
        assert part.filename == "hex bolt.sldprt"
        assert score > 0.30

    def test_match_part_no_weight_dominates(self, idx):
        """加权机制验证：单 token 高权重（2.0）能超过阈值。

        注：生产配置 part_no=0.0；此处直接传入权重 2.0 测试 match_toolbox_part 机制本身。
        """
        from adapters.solidworks.sw_toolbox_catalog import match_toolbox_part

        # 仅 part_no token 命中（"bolt"），name_cn 无命中
        query_tokens = [("bolt", 2.0)]
        result = match_toolbox_part(
            idx,
            query_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        assert result is not None

    def test_match_below_min_score_returns_none(self, idx):
        """决策 #3: 低于 min_score 返回 None → miss。"""
        from adapters.solidworks.sw_toolbox_catalog import match_toolbox_part

        query_tokens = [("completely", 1.0), ("unrelated", 1.0)]
        result = match_toolbox_part(
            idx,
            query_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        assert result is None

    def test_match_respects_subcategory_whitelist(self, idx):
        """只在 spec 指定的 subcategories 里搜。"""
        from adapters.solidworks.sw_toolbox_catalog import match_toolbox_part

        query_tokens = [("hex", 1.0), ("nut", 1.0)]
        # 限定只搜 bolts and studs, 应不会返回 nuts 下的东西
        result = match_toolbox_part(
            idx,
            query_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        if result:
            part, _ = result
            assert part.subcategory == "bolts and studs"


class TestBuildQueryTokensWeighted:
    """build_query_tokens_weighted 的单元测试。"""

    def test_build_query_tokens_weighted(self):
        from adapters.solidworks.sw_toolbox_catalog import build_query_tokens_weighted

        class Q:
            part_no = "GB/T 70.1"
            name_cn = "M6×20 内六角螺钉"
            material = "钢"

        weights = {"part_no": 2.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}
        size_dict = {"size": "M6", "length": "20"}

        tokens_weighted = build_query_tokens_weighted(Q(), size_dict, weights)
        # 每个 token 是 (str, float) tuple
        assert all(isinstance(t, tuple) and len(t) == 2 for t in tokens_weighted)
        # part_no 里的 token 权重应为 2.0
        part_no_tokens = {t for t, w in tokens_weighted if w == 2.0}
        # "gb" 或 "70" 应属 part_no
        assert any(k in part_no_tokens for k in ["gb", "70", "1"])

    def test_internal_part_no_excluded_at_zero_weight(self):
        """part_no weight=0.0 时，内部编号 token 不应出现在结果里；其他字段 token 仍正常注入。"""
        from adapters.solidworks.sw_toolbox_catalog import build_query_tokens_weighted

        class Q:
            part_no = "GIS-DEMO-001"
            name_cn = "GB/T 70.1 M6×20 内六角圆柱头螺钉"
            material = "钢"

        weights = {"part_no": 0.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}
        size_dict = {"size": "M6", "length": "20"}
        tokens_weighted = build_query_tokens_weighted(Q(), size_dict, weights)
        token_names = {t for t, _ in tokens_weighted}
        # 零权重字段的 token 不应注入
        assert "gis" not in token_names
        assert "demo" not in token_names
        assert "001" not in token_names
        # 其他字段 token 仍应存在（name_cn / size 字段）
        assert len(tokens_weighted) > 0
        assert any(t in token_names for t in ["gb", "m6", "70"])

    def test_plural_pairs_expand_ascii_screw(self):
        """'screw' 应该自动注入 'screws'（相同权重）。"""
        from adapters.solidworks.sw_toolbox_catalog import build_query_tokens_weighted

        class Q:
            part_no = ""
            name_cn = "ISO 4762 M5×16 hex socket cap screw"
            material = ""

        weights = {"part_no": 0.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}
        tokens_weighted = build_query_tokens_weighted(Q(), {"size": "M5"}, weights)
        token_map = dict(tokens_weighted)
        assert "screw" in token_map
        assert "screws" in token_map
        assert token_map["screws"] == token_map["screw"]  # 相同权重

    def test_plural_pairs_expand_ascii_nut(self):
        """'nut' 应该自动注入 'nuts'。"""
        from adapters.solidworks.sw_toolbox_catalog import build_query_tokens_weighted

        class Q:
            part_no = ""
            name_cn = "ISO 4032 M5 hex nut"
            material = ""

        weights = {"part_no": 0.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}
        tokens_weighted = build_query_tokens_weighted(Q(), {"size": "M5"}, weights)
        token_map = dict(tokens_weighted)
        assert "nut" in token_map
        assert "nuts" in token_map

    def test_plural_pairs_expand_plural_to_singular(self):
        """复数形式（'screws'）应自动注入单数（'screw'），双向对称。"""
        from adapters.solidworks.sw_toolbox_catalog import build_query_tokens_weighted

        class Q:
            part_no = ""
            name_cn = "ISO 1207 M3 slotted cheese head screws"
            material = ""

        weights = {"part_no": 0.0, "name_cn": 1.0, "material": 0.0, "size": 1.5}
        tokens_weighted = build_query_tokens_weighted(Q(), {"size": "M3"}, weights)
        token_map = dict(tokens_weighted)
        assert "screws" in token_map
        assert "screw" in token_map
        assert token_map["screw"] == token_map["screws"]  # 权重对称

    def test_plural_pairs_expand_cn_synonym_injected_token(self):
        """中文同义词扩展注入的英文 token 也应触发单/复数扩展。

        pipeline: 螺钉（CJK）→ expand_cn_synonyms → screw（英文）→ PLURAL_PAIRS → screws
        """
        from adapters.solidworks.sw_toolbox_catalog import build_query_tokens_weighted

        class Q:
            part_no = ""
            name_cn = "GB/T 70.1 M6×20 内六角圆柱头螺钉"
            material = ""

        weights = {"part_no": 0.0, "name_cn": 1.0, "material": 0.0, "size": 1.5}
        tokens_weighted = build_query_tokens_weighted(Q(), {"size": "M6"}, weights)
        token_map = dict(tokens_weighted)
        # 螺钉 → screw（同义词），screw → screws（PLURAL_PAIRS）
        assert "screw" in token_map
        assert "screws" in token_map


class TestMakeIndexEnvelope:
    """Minor #5: _make_index_envelope 去重 _empty_index 与 build_toolbox_index 返回结构。"""

    def test_envelope_has_required_keys(self):
        """_make_index_envelope 返回结构包含所有必需键。"""
        from adapters.solidworks.sw_toolbox_catalog import (
            _make_index_envelope,
            SCHEMA_VERSION,
        )

        env = _make_index_envelope({}, "abc123")
        assert env["schema_version"] == SCHEMA_VERSION
        assert "scan_time" in env
        assert env["toolbox_fingerprint"] == "abc123"
        assert env["standards"] == {}

    def test_empty_index_consistent_with_envelope(self):
        """Minor #4: _empty_index 使用 _make_index_envelope 后结构一致。"""
        from adapters.solidworks.sw_toolbox_catalog import _empty_index, SCHEMA_VERSION

        idx = _empty_index()
        assert idx["schema_version"] == SCHEMA_VERSION
        assert idx["toolbox_fingerprint"] == "unavailable"
        assert idx["standards"] == {}

    def test_build_index_uses_envelope_structure(self, tmp_path):
        """build_toolbox_index 返回 dict 结构与 _make_index_envelope 一致。"""
        from adapters.solidworks.sw_toolbox_catalog import (
            build_toolbox_index,
            SCHEMA_VERSION,
        )

        # 使用不存在的目录触发空索引路径
        idx = build_toolbox_index(tmp_path / "nonexistent")
        assert idx["schema_version"] == SCHEMA_VERSION
        assert "scan_time" in idx
        assert "toolbox_fingerprint" in idx
        assert "standards" in idx
