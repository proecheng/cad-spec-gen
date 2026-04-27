import json
import sys
import types

import pytest

from adapters.solidworks import sw_config_broker as broker
from adapters.solidworks import sw_config_lists_cache as cache_mod


def test_config_resolution_dataclass_fields():
    from adapters.solidworks.sw_config_broker import ConfigResolution

    r = ConfigResolution(
        config_name="80×2.4",
        source="auto",
        confidence=1.0,
        available_configs=["28×1.9", "80×2.4"],
        notes="字面完全匹配",
    )
    assert r.config_name == "80×2.4"
    assert r.source == "auto"
    assert r.confidence == 1.0
    assert r.available_configs == ["28×1.9", "80×2.4"]
    assert r.notes == "字面完全匹配"


def test_config_resolution_notes_default_empty():
    from adapters.solidworks.sw_config_broker import ConfigResolution

    r = ConfigResolution(
        config_name=None,
        source="policy_fallback",
        confidence=0.0,
        available_configs=[],
    )
    assert r.notes == ""


def test_needs_user_decision_carries_record():
    from adapters.solidworks.sw_config_broker import NeedsUserDecision

    rec = {"part_no": "X", "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence"}
    exc = NeedsUserDecision(part_no="X", subsystem="end_effector", pending_record=rec)
    assert exc.part_no == "X"
    assert exc.subsystem == "end_effector"
    assert exc.pending_record is rec
    assert "X" in str(exc)
    assert "end_effector" in str(exc)


class TestBuildBomDimSignature:
    """spec §5.1: bom_dim_signature = f'{name_cn}|{material}'"""

    def test_fastener_dim_in_material(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X", "name_cn": "内六角螺栓", "material": "GB/T 70.1 M8×20"}
        assert _build_bom_dim_signature(bom) == "内六角螺栓|GB/T 70.1 M8×20"

    def test_bearing_dim_in_name_cn(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X", "name_cn": "深沟球轴承 6205", "material": "GCr15"}
        assert _build_bom_dim_signature(bom) == "深沟球轴承 6205|GCr15"

    def test_seal(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X", "name_cn": "O型圈", "material": "FKM Φ80×2.4"}
        assert _build_bom_dim_signature(bom) == "O型圈|FKM Φ80×2.4"

    def test_missing_fields_default_empty(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X"}
        assert _build_bom_dim_signature(bom) == "|"

    def test_none_fields_treated_as_empty(self):
        from adapters.solidworks.sw_config_broker import _build_bom_dim_signature

        bom = {"part_no": "X", "name_cn": None, "material": None}
        assert _build_bom_dim_signature(bom) == "|"


class TestMatchConfigByRule:
    """spec §4.4 #2: L1 精确归一化 confidence=1.0"""

    def test_l1_exact_unicode_x(self):
        """BOM 'Φ80×2.4' + available '80×2.4' → 完全匹配 confidence=1.0"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["28×1.9", "80×2.4", "100×3.0"],
        )
        assert result == ("80×2.4", 1.0)

    def test_l1_exact_ascii_x(self):
        """BOM 'Φ80×2.4' + available '80x2.4' → 归一化后匹配 confidence=1.0"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["28×1.9", "80x2.4", "100×3.0"],
        )
        assert result == ("80x2.4", 1.0)

    def test_l1_exact_with_space_dash(self):
        """BOM 'M8×20' + available 'M8 X 20' → 归一化匹配 confidence=1.0"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="内六角螺栓|GB/T 70.1 M8×20",
            available=["M6 X 20", "M8 X 20", "M10 X 20"],
        )
        assert result == ("M8 X 20", 1.0)

    def test_no_match_returns_none(self):
        """available 完全不匹配 → None"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["AAA", "BBB"],
        )
        assert result is None

    def test_empty_available_returns_none(self):
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X",
            available=[],
        )
        assert result is None

    def test_l1_no_false_positive_from_standard_number(self):
        """防御性回归：BOM 'GB/T 70.1 M8×20' 不应让 available '70.1' 误匹配
        （'70.1' 是标准编号，不是尺寸 token）"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="内六角螺栓|GB/T 70.1 M8×20",
            available=["70.1", "M8x20"],
        )
        # 应命中 M8x20，不命中 70.1
        assert result is not None
        assert result[0] == "M8x20"


class TestMatchConfigByRuleL2:
    """spec §4.4 #2: L2 包含子串 + spec §10.2 假阳性防御"""

    def test_l2_substring_match(self):
        """available 'GB1235-80x2.4' 包含归一化 token '80x2.4' → confidence=0.7~0.95"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["GB1235-28x1.9", "GB1235-80x2.4", "GB1235-100x3.0"],
        )
        assert result is not None
        config, conf = result
        assert config == "GB1235-80x2.4"
        assert 0.7 <= conf <= 0.95

    def test_l2_false_positive_m6_vs_m16(self):
        """关键防御：BOM M16 + available [M6×20, M16×20] → 必须命中 M16×20 不是 M6×20

        L1 匹配 'm16x20' 与 available 归一化后比对：
        - 'M6×20' → 'm6x20' ≠ 'm16x20'
        - 'M16×20' → 'm16x20' == 'm16x20' ✓
        """
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="内六角螺栓|GB/T 70.1 M16×20",
            available=["M6×20", "M16×20"],
        )
        assert result is not None
        assert result[0] == "M16×20"

    def test_l2_short_token_low_confidence(self):
        """短 token (如 'M6') confidence 较低（短 token 长度→低分）。
        BOM 'M6' + available 'long-name-M6-extra' → L2 命中 confidence ≈ 0.72"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X|M6",
            available=["long-name-M6-extra"],
        )
        assert result is not None
        assert result[0] == "long-name-M6-extra"
        # M6 归一 'm6' (len=2) → conf = 0.7 + 2/100 = 0.72
        assert result[1] == pytest.approx(0.72)

    def test_below_threshold_returns_none(self):
        """confidence < 0.7 → 返回 None，让 caller 走含糊路径。
        BOM token '2.4' 孤立小数，Task 4 正则修复后不被提取 → 自动返回 None"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X|2.4",  # '2.4' 孤立小数不被正则提取
            available=["abc"],
        )
        assert result is None

    def test_l2_word_boundary_m1_not_matches_m10(self):
        """关键回归：BOM 'M1' + available ['M10x20', 'M11x20'] → 不应命中 M10x20。
        L2 子串包含必须有右边界守卫（M1 命中位置后不能紧跟数字）。
        当 available 全部带数字后缀时，L2 没有合理候选 → 返回 None。"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X|M1",
            available=["M10x20", "M11x20"],
        )
        assert result is None

    def test_l2_word_boundary_m1_matches_m1_suffix(self):
        """词边界正确性：BOM 'M1' + available 'GB1234-M1-extra' → L2 命中（M1 后是非数字 '-'）"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X|M1",
            available=["GB1234-M1-extra", "GB1234-M10-extra"],
        )
        assert result is not None
        assert result[0] == "GB1234-M1-extra"

    def test_l2_multi_match_shortest_wins(self):
        """L2 多命中 → 取字符串最短"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="O型圈|FKM Φ80×2.4",
            available=["VERY_LONG_PREFIX-80x2.4", "80x2.4-suffix", "abc-80x2.4"],
        )
        assert result is not None
        # L1 等值不命中（都有前后缀），L2 子串多命中 → 取最短
        # 长度: "VERY_LONG_PREFIX-80x2.4"=23, "80x2.4-suffix"=13, "abc-80x2.4"=10
        assert result[0] == "abc-80x2.4"


class TestValidateCachedDecision:
    """spec §5.2: 三项失效条件"""

    def _make_decision(self, **overrides):
        base = {
            "bom_dim_signature": "O型圈|FKM Φ80×2.4",
            "sldprt_filename": "o-rings series a gb.sldprt",
            "decision": "use_config",
            "config_name": "80×2.4",
            "user_note": "",
            "decided_at": "2026-04-25T22:25:11+00:00",
        }
        base.update(overrides)
        return base

    def test_valid_decision_passes(self):
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision()
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings series a gb.sldprt",
            current_available_configs=["28×1.9", "80×2.4", "100×3.0"],
        )
        assert valid is True
        assert reason is None

    def test_bom_dim_signature_changed(self):
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision()
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ100×3.0",  # 改了
            current_sldprt_filename="o-rings series a gb.sldprt",
            current_available_configs=["28×1.9", "80×2.4"],
        )
        assert valid is False
        assert reason == "bom_dim_signature_changed"

    def test_sldprt_filename_changed(self):
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision()
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings series b gb.sldprt",  # 改了
            current_available_configs=["28×1.9", "80×2.4"],
        )
        assert valid is False
        assert reason == "sldprt_filename_changed"

    def test_config_name_not_in_available(self):
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision()
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings series a gb.sldprt",
            current_available_configs=["28×1.9"],  # 没了 80×2.4
        )
        assert valid is False
        assert reason == "config_name_not_in_available_configs"

    def test_fallback_cadquery_skips_config_check(self):
        """spec §5.2: decision=fallback_cadquery 时跳过第三项检查（无 config_name 可校）"""
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = self._make_decision(decision="fallback_cadquery", config_name=None)
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings series a gb.sldprt",
            current_available_configs=[],  # 即使空也 OK
        )
        assert valid is True
        assert reason is None

    @pytest.mark.parametrize(
        "decision_state,expected_valid,expected_reason",
        [
            ("match", True, None),
            ("bom_changed", False, "bom_dim_signature_changed"),
            ("filename_changed", False, "sldprt_filename_changed"),
            ("config_renamed", False, "config_name_not_in_available_configs"),
        ],
        ids=["valid_match", "bom_changed", "filename_changed", "config_renamed"],
    )
    def test_validate_returns_typed_literal_or_none(
        self, decision_state, expected_valid, expected_reason
    ):
        """T5 (spec §4.4 / §7.2 invariant 1): _validate_cached_decision 返回 tuple
        第二位运行时是 3 字面量字符串之一（valid=False）或 None（valid=True）。
        """
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = {
            "decision": "use_config",
            "config_name": "ConfigA",
            "bom_dim_signature": "match_sig" if decision_state != "bom_changed" else "old",
            "sldprt_filename": "match.sldprt" if decision_state != "filename_changed" else "old.sldprt",
        }
        current_bom_signature = "match_sig"
        current_sldprt_filename = "match.sldprt"
        current_available_configs = (
            ["ConfigA"] if decision_state != "config_renamed" else ["ConfigB"]
        )

        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature,
            current_sldprt_filename,
            current_available_configs,
        )
        assert valid is expected_valid
        assert reason == expected_reason
        # 类型守护
        if reason is not None:
            assert isinstance(reason, str)
            assert reason in {
                "bom_dim_signature_changed",
                "sldprt_filename_changed",
                "config_name_not_in_available_configs",
            }

    def test_invalidation_reasons_frozenset_immutable_and_complete(self):
        """T6 (spec §4.4 / §7.2 invariant 5): INVALIDATION_REASONS 是不可变 frozenset
        且包含且仅包含 3 个 Literal 字面量。防御未来误删/误改常量。
        """
        from adapters.solidworks.sw_config_broker import INVALIDATION_REASONS

        assert isinstance(INVALIDATION_REASONS, frozenset)
        # 完整性：3 个 Literal 字面量都在
        assert INVALIDATION_REASONS == {
            "bom_dim_signature_changed",
            "sldprt_filename_changed",
            "config_name_not_in_available_configs",
        }
        # 不可变性
        with pytest.raises(AttributeError):
            INVALIDATION_REASONS.add("new_reason")  # type: ignore[attr-defined]


class TestBuildPendingRecord:
    """spec §5.3: pending record schema 按 match_failure_reason 分支"""

    BOM_ORING = {
        "part_no": "GIS-EE-001-03",
        "name_cn": "O型圈",
        "material": "FKM Φ80×2.4",
    }
    SLDPRT = "C:/SOLIDWORKS Data/browser/GB/o-rings/all o-rings/o-rings series a gb.sldprt"

    def test_no_exact_or_fuzzy_match(self):
        from adapters.solidworks.sw_config_broker import _build_pending_record

        rec = _build_pending_record(
            bom_row=self.BOM_ORING,
            sldprt_path=self.SLDPRT,
            available=["28×1.9", "100×3.0"],
            match_failure_reason="no_exact_or_fuzzy_match_with_high_confidence",
            attempted_match=None,
        )
        assert rec["part_no"] == "GIS-EE-001-03"
        assert rec["name_cn"] == "O型圈"
        assert rec["material"] == "FKM Φ80×2.4"
        assert rec["bom_dim_signature"] == "O型圈|FKM Φ80×2.4"
        assert rec["sldprt_path"] == self.SLDPRT
        assert rec["sldprt_filename"] == "o-rings series a gb.sldprt"
        assert rec["available_configs"] == ["28×1.9", "100×3.0"]
        assert rec["attempted_match"] is None
        assert rec["match_failure_reason"] == "no_exact_or_fuzzy_match_with_high_confidence"
        # suggested_options 至少含 fallback_cadquery
        assert any(opt["action"] == "fallback_cadquery" for opt in rec["suggested_options"])

    def test_com_open_failed(self):
        """COM 失败 → available_configs=[]，suggested 仅 fallback_cadquery"""
        from adapters.solidworks.sw_config_broker import _build_pending_record

        rec = _build_pending_record(
            bom_row=self.BOM_ORING,
            sldprt_path=self.SLDPRT,
            available=[],
            match_failure_reason="com_open_failed",
            attempted_match=None,
        )
        assert rec["available_configs"] == []
        assert len(rec["suggested_options"]) == 1
        assert rec["suggested_options"][0]["action"] == "fallback_cadquery"

    def test_empty_config_list_default_only(self):
        """SLDPRT 仅有 'Default' → suggested 含 use_config + fallback"""
        from adapters.solidworks.sw_config_broker import _build_pending_record

        rec = _build_pending_record(
            bom_row=self.BOM_ORING,
            sldprt_path=self.SLDPRT,
            available=["Default"],
            match_failure_reason="empty_config_list",
            attempted_match=None,
        )
        actions = [o["action"] for o in rec["suggested_options"]]
        assert "use_config" in actions
        assert "fallback_cadquery" in actions
        # 找到 use_config 选项 config_name=Default
        use_default = [o for o in rec["suggested_options"] if o["action"] == "use_config"][0]
        assert use_default["config_name"] == "Default"

    def test_multiple_high_confidence(self):
        """多候选 ≥ 0.7 同分 → suggested 列出全部"""
        from adapters.solidworks.sw_config_broker import _build_pending_record

        rec = _build_pending_record(
            bom_row=self.BOM_ORING,
            sldprt_path=self.SLDPRT,
            available=["80×2.4", "Φ80×2.4mm"],
            match_failure_reason="multiple_high_confidence_matches",
            attempted_match=None,
        )
        use_options = [o for o in rec["suggested_options"] if o["action"] == "use_config"]
        assert len(use_options) >= 2


class TestFixtures:
    """Task 8：tmp_project_dir fixture 验证"""

    def test_tmp_project_dir_creates_cad_dir(self, tmp_project_dir):
        assert (tmp_project_dir / ".cad-spec-gen").is_dir()

    def test_tmp_project_dir_sets_env(self, tmp_project_dir):
        import os

        assert os.environ["CAD_PROJECT_ROOT"] == str(tmp_project_dir)

    def test_tmp_project_dir_cad_paths_synced(self, tmp_project_dir):
        import os

        from cad_paths import PROJECT_ROOT

        # PROJECT_ROOT 经过 normpath 处理，所以两边都 normpath 比对
        assert os.path.normpath(PROJECT_ROOT) == os.path.normpath(str(tmp_project_dir))


class TestDecisionsEnvelopeIO:
    """spec §4.3: _load/_save_decisions_envelope"""

    def test_load_missing_file_returns_empty_envelope(self, tmp_project_dir):
        from adapters.solidworks.sw_config_broker import _load_decisions_envelope

        env = _load_decisions_envelope()
        assert env["schema_version"] == 2
        assert env["decisions_by_subsystem"] == {}
        assert env["decisions_history"] == []

    def test_save_then_load_roundtrip(self, tmp_project_dir):
        """review I-1: 改硬版 — 显式断言 _save 不 mutate 入参，
        且磁盘上有 last_updated 而入参 envelope 没有。"""
        import json

        from adapters.solidworks.sw_config_broker import (
            _load_decisions_envelope,
            _save_decisions_envelope,
        )

        envelope = {
            "schema_version": 2,
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
                        "sldprt_filename": "o-rings series a gb.sldprt",
                        "decision": "use_config",
                        "config_name": "80×2.4",
                        "user_note": "ok",
                        "decided_at": "2026-04-25T22:25:11+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        _save_decisions_envelope(envelope)

        # I-1 契约：入参不被 mutate
        assert "last_updated" not in envelope

        # 磁盘文件：含 _save 注入的 last_updated
        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        assert path.is_file()
        loaded_raw = json.loads(path.read_text(encoding="utf-8"))
        assert "last_updated" in loaded_raw
        assert loaded_raw["last_updated"] != ""

        # 除 last_updated 外其他字段与入参完全一致（真正的 round-trip 校验）
        loaded_minus_ts = {k: v for k, v in loaded_raw.items() if k != "last_updated"}
        assert loaded_minus_ts == envelope

        # _load 接口同步回读
        loaded = _load_decisions_envelope()
        loaded_minus_ts = {k: v for k, v in loaded.items() if k != "last_updated"}
        assert loaded_minus_ts == envelope

    def test_load_corrupt_json_fails_loud(self, tmp_project_dir):
        """spec §6: decisions.json 损坏 → fail loud 含行号

        review M-1: 断言 __cause__ 是 JSONDecodeError 比 match 文案稳定
        （未来错误消息 i18n 不会破测试）。
        """
        import json as _json

        from adapters.solidworks.sw_config_broker import _load_decisions_envelope

        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text('{ "broken JSON syntax', encoding="utf-8")

        with pytest.raises(ValueError) as exc_info:
            _load_decisions_envelope()
        assert isinstance(exc_info.value.__cause__, _json.JSONDecodeError)

    def test_load_schema_version_mismatch_fails(self, tmp_project_dir):
        """spec §6: schema_version 不一致 → 阻塞"""
        import json

        from adapters.solidworks.sw_config_broker import _load_decisions_envelope

        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text(
            json.dumps({"schema_version": 99, "decisions_by_subsystem": {}}),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="schema_version"):
            _load_decisions_envelope()

    def test_load_top_level_not_dict_fails(self, tmp_project_dir):
        """review I-3: 合法 JSON 但顶层非 object → fail loud 而非 AttributeError"""
        from adapters.solidworks.sw_config_broker import _load_decisions_envelope

        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError, match="顶层必须是 JSON object"):
            _load_decisions_envelope()

    def test_save_atomic_write_via_tmp(self, tmp_project_dir):
        """save 必须先写 .tmp 再 os.replace（防中途崩溃残缺）"""
        from adapters.solidworks.sw_config_broker import _save_decisions_envelope

        envelope = {"schema_version": 2, "decisions_by_subsystem": {}, "decisions_history": []}
        _save_decisions_envelope(envelope)

        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        tmp_path = path.with_suffix(".json.tmp")
        # 写完后 .tmp 应已被 rename
        assert path.is_file()
        assert not tmp_path.exists()

    @pytest.fixture
    def _make_envelope_with_history(self, tmp_project_dir):
        """构造 minimal envelope dict + 写盘，返回该 path 给 _load 测试用。"""

        def _build(history_entries: list[dict]) -> "Path":
            envelope = {
                "schema_version": 2,
                "decisions_by_subsystem": {},
                "decisions_history": history_entries,
            }
            path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(envelope), encoding="utf-8")
            return path

        return _build

    def test_load_rejects_unknown_string_in_history(
        self, _make_envelope_with_history
    ):
        """T8 (spec §4.5 IO 边界): decisions_history 含 PR #19 之前的旧字符串
        'bom_change'，_load_decisions_envelope 必抛 ValueError 守护跨 IO 边界。
        """
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": "TEST-001",
                "previous_decision": {"decision": "use_config", "config_name": "A"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": "bom_change",  # ← 旧 schema 字符串
            }
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()

    def test_load_rejects_none_invalidation_reason(
        self, _make_envelope_with_history
    ):
        """T9 (spec §4.5): invalidation_reason == None 必抛。"""
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": "TEST-001",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": None,
            }
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()

    def test_load_rejects_empty_string_invalidation_reason(
        self, _make_envelope_with_history
    ):
        """T10 (spec §4.5): invalidation_reason == '' 必抛。"""
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": "TEST-001",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": "",
            }
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()

    def test_load_rejects_int_invalidation_reason(
        self, _make_envelope_with_history
    ):
        """T11 (spec §4.5): invalidation_reason == 0（用户手编混入数字）必抛。"""
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": "TEST-001",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": 0,
            }
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()

    def test_load_rejects_partial_corrupted_history(
        self, _make_envelope_with_history
    ):
        """T12 (spec §4.5): 5 条 history，1 条含未知 reason，整体 raise（不 silent skip）。"""
        from adapters.solidworks import sw_config_broker

        _make_envelope_with_history([
            {
                "subsystem": "es",
                "part_no": f"TEST-{i:03d}",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": (
                    "bom_change_legacy" if i == 2 else "bom_dim_signature_changed"
                ),
            }
            for i in range(5)
        ])

        with pytest.raises(ValueError, match="schema 损坏或老版本数据"):
            sw_config_broker._load_decisions_envelope()

    def test_load_with_valid_history_passes(
        self, _make_envelope_with_history
    ):
        """守护 happy path（spec §4.5 补强）：含 3 条 valid invalidation_reason
        的 history 加载成功，envelope 内容正确。
        """
        from adapters.solidworks import sw_config_broker

        valid_entries = [
            {
                "subsystem": "es",
                "part_no": f"TEST-{i:03d}",
                "previous_decision": {"decision": "use_config"},
                "invalidated_at": "2026-01-01T00:00:00Z",
                "invalidation_reason": reason,
            }
            for i, reason in enumerate([
                "bom_dim_signature_changed",
                "sldprt_filename_changed",
                "config_name_not_in_available_configs",
            ])
        ]
        _make_envelope_with_history(valid_entries)

        envelope = sw_config_broker._load_decisions_envelope()
        assert len(envelope["decisions_history"]) == 3
        assert envelope["decisions_history"][0]["invalidation_reason"] == "bom_dim_signature_changed"
        assert envelope["decisions_history"][1]["invalidation_reason"] == "sldprt_filename_changed"
        assert envelope["decisions_history"][2]["invalidation_reason"] == "config_name_not_in_available_configs"


class TestDecisionAccessors:
    """Task 10：envelope 内按 subsystem/part_no 索引 + 失效归档"""

    def test_get_decision_present(self):
        from adapters.solidworks.sw_config_broker import _get_decision_for_part

        env = {
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {"decision": "use_config", "config_name": "80×2.4"}
                }
            }
        }
        d = _get_decision_for_part(env, "end_effector", "GIS-EE-001-03")
        assert d is not None
        assert d["config_name"] == "80×2.4"

    def test_get_decision_missing_subsystem(self):
        from adapters.solidworks.sw_config_broker import _get_decision_for_part

        env = {"decisions_by_subsystem": {}}
        assert _get_decision_for_part(env, "end_effector", "X") is None

    def test_get_decision_missing_part(self):
        from adapters.solidworks.sw_config_broker import _get_decision_for_part

        env = {"decisions_by_subsystem": {"end_effector": {}}}
        assert _get_decision_for_part(env, "end_effector", "X") is None

    @pytest.mark.parametrize(
        "invalidation_reason",
        [
            "bom_dim_signature_changed",
            "sldprt_filename_changed",
            "config_name_not_in_available_configs",
        ],
    )
    def test_move_decision_to_history(self, invalidation_reason):
        """T7 (spec §4.4 / §7.2 invariant 2): _move_decision_to_history 对 3 reason
        各自正确 append history + pop 原 entry。
        """
        from adapters.solidworks.sw_config_broker import (
            _empty_envelope,
            _move_decision_to_history,
        )

        envelope = _empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }

        _move_decision_to_history(
            envelope, "test_sub", "TEST-001", invalidation_reason
        )

        # 1. 原 entry 已 pop
        assert "TEST-001" not in envelope["decisions_by_subsystem"]["test_sub"]
        # 2. history append 1 条，reason 等于参数
        assert len(envelope["decisions_history"]) == 1
        history_entry = envelope["decisions_history"][0]
        assert history_entry["invalidation_reason"] == invalidation_reason
        assert history_entry["subsystem"] == "test_sub"
        assert history_entry["part_no"] == "TEST-001"
        assert "previous_decision" in history_entry
        assert "invalidated_at" in history_entry

    def test_move_decision_rejects_unknown_reason(self):
        """review I-2: invalidation_reason 不在 INVALIDATION_REASONS 内 → ValueError"""
        from adapters.solidworks.sw_config_broker import _move_decision_to_history

        env = {
            "decisions_by_subsystem": {
                "end_effector": {"GIS-EE-001-03": {"decision": "use_config", "config_name": "X"}}
            },
            "decisions_history": [],
        }
        with pytest.raises(ValueError, match="未知 invalidation_reason"):
            _move_decision_to_history(env, "end_effector", "GIS-EE-001-03", "bom_change")
        # 校验失败时不应 mutate envelope
        assert "GIS-EE-001-03" in env["decisions_by_subsystem"]["end_effector"]
        assert env["decisions_history"] == []


class TestListConfigsViaCom:
    """spec §4.3 + §4.4 #1: 调 sw_list_configs_worker 子进程 + 内部 _CONFIG_LIST_CACHE。"""

    def test_list_returns_parsed_json(self, monkeypatch):
        """worker rc=0 + stdout JSON list → 解析返回。"""
        import subprocess

        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout='["28×1.9", "80×2.4", "100×3.0"]\n',
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = sw_config_broker._list_configs_via_com("dummy.sldprt")
        assert result == ["28×1.9", "80×2.4", "100×3.0"]

    def test_list_caches_per_path(self, monkeypatch):
        """同 sldprt 第二次调 → 从 cache 拿，不再调 subprocess。"""
        import subprocess

        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        call_count = [0]

        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout='["A"]\n', stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        sw_config_broker._list_configs_via_com("X.sldprt")
        sw_config_broker._list_configs_via_com("X.sldprt")
        assert call_count[0] == 1  # 只调一次

    def test_list_failure_returns_empty_and_caches(self, monkeypatch):
        """worker terminal 失败 (rc=2) → 返回 [] + cache 标记（避免重试）。

        spec rev 5 §3.2.2：rc=2 是唯一永久 cache 失败路径。原测试用 rc=4 旧合约
        现按 spec rev 5 是 LEGACY 不 cache —— 此处改 rc=2 保持"cache 命中"测试语义。
        """
        import subprocess

        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd, returncode=2, stdout="", stderr="terminal failure"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = sw_config_broker._list_configs_via_com("Y.sldprt")
        assert result == []

        # 第二次调换成 success worker，验证 cache 命中（call_count 不再增长）
        call_count = [0]

        def counting_run(cmd, **kwargs):
            call_count[0] += 1
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="[]", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", counting_run)
        sw_config_broker._list_configs_via_com("Y.sldprt")
        assert call_count[0] == 0

    def test_list_timeout_returns_empty(self, monkeypatch):
        """subprocess.TimeoutExpired → 返回 [] + 不 cache（spec rev 5 §3.2.2）。"""
        import subprocess
        from pathlib import Path

        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=15)

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = sw_config_broker._list_configs_via_com("Z.sldprt")
        assert result == []
        # M-4 新契约：TimeoutExpired 视为 transient 不 cache，区别于旧合约 cache=[]
        assert str(Path("Z.sldprt").resolve()) not in sw_config_broker._CONFIG_LIST_CACHE


class TestResolveConfigForPart:
    """spec §3.2 数据流：5 路径全覆盖（cached / auto / cached_invalidate / policy / halt）。"""

    @pytest.fixture(autouse=True)
    def _enable_broker(self, monkeypatch):
        """Task 14.5 opt-out：本 class 测试需要 broker 真路径，覆盖 conftest 全局禁用。"""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

    BOM = {"part_no": "GIS-EE-001-03", "name_cn": "O型圈", "material": "FKM Φ80×2.4"}
    SLDPRT = "/abs/path/o-rings series a gb.sldprt"

    def _patch_com(self, monkeypatch, configs):
        """注入 _list_configs_via_com 的返回，跳过实际 subprocess 调用。"""
        from adapters.solidworks import sw_config_broker
        sw_config_broker._CONFIG_LIST_CACHE.clear()
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda p: configs
        )

    def test_path_1_auto_match_l1_exact(self, tmp_project_dir, monkeypatch):
        """路径 [3] 规则匹配 L1 命中 → source=auto, confidence=1.0"""
        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        self._patch_com(monkeypatch, ["28×1.9", "80×2.4"])
        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")

        assert r.source == "auto"
        assert r.config_name == "80×2.4"
        assert r.confidence == 1.0
        assert r.available_configs == ["28×1.9", "80×2.4"]

    def test_path_2_cached_decision_use_config_valid(
        self, tmp_project_dir, monkeypatch
    ):
        """路径 [2] cache 命中 + 三项校验通过 → source=cached_decision"""
        import json

        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        decisions = {
            "schema_version": 2,
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
                        "sldprt_filename": "o-rings series a gb.sldprt",
                        "decision": "use_config",
                        "config_name": "80×2.4",
                        "user_note": "ok",
                        "decided_at": "2026-04-25T22:25:11+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text(json.dumps(decisions), encoding="utf-8")

        # cached config 仍在 available → 校验通过
        self._patch_com(monkeypatch, ["80×2.4", "100×3.0"])
        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")

        assert r.source == "cached_decision"
        assert r.config_name == "80×2.4"
        assert r.confidence == 1.0

    def test_path_2b_cached_decision_invalidate(self, tmp_project_dir, monkeypatch):
        """cache 命中但 config 已不在 available → 自动挪 history + 走规则匹配"""
        import json

        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        decisions = {
            "schema_version": 2,
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
                        "sldprt_filename": "o-rings series a gb.sldprt",
                        "decision": "use_config",
                        "config_name": "80×2.4",  # 旧名
                        "user_note": "",
                        "decided_at": "2026-04-20T10:00:00+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text(json.dumps(decisions), encoding="utf-8")

        # SW 升级后 config 改名，旧名不在 available 中
        self._patch_com(monkeypatch, ["80x2.4 (FKM)"])

        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")
        # L2 子串匹配命中新名字
        assert r.source == "auto"
        assert r.config_name == "80x2.4 (FKM)"

        # 旧决策已挪到 history，且持久化到磁盘
        env = json.loads(path.read_text(encoding="utf-8"))
        assert "GIS-EE-001-03" not in env["decisions_by_subsystem"]["end_effector"]
        assert len(env["decisions_history"]) == 1
        assert (
            env["decisions_history"][0]["invalidation_reason"]
            == "config_name_not_in_available_configs"
        )

    def test_path_4_policy_fallback_silent(self, tmp_project_dir, monkeypatch):
        """env CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery → 含糊不抛，返回 policy_fallback"""
        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        monkeypatch.setenv("CAD_AMBIGUOUS_CONFIG_POLICY", "fallback_cadquery")
        self._patch_com(monkeypatch, ["AAA", "BBB"])  # 完全不匹配

        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")
        assert r.source == "policy_fallback"
        assert r.config_name is None
        assert r.confidence == 0.0

    def test_path_4_policy_fallback_carries_pending_record(
        self, tmp_project_dir, monkeypatch
    ):
        """C-1: spec line 89 + 278 — fallback 分支必须携带 pending_record（事后审阅）。"""
        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        monkeypatch.setenv("CAD_AMBIGUOUS_CONFIG_POLICY", "fallback_cadquery")
        self._patch_com(monkeypatch, ["AAA", "BBB"])

        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")

        # 关键契约：caller (gen_std_parts) 能从 ConfigResolution 取出 pending_record
        # 与 NeedsUserDecision.pending_record 走同样累积逻辑
        assert r.pending_record is not None
        assert r.pending_record["part_no"] == "GIS-EE-001-03"
        assert (
            r.pending_record["match_failure_reason"]
            == "no_exact_or_fuzzy_match_with_high_confidence"
        )

    def test_path_1_auto_match_pending_record_is_none(
        self, tmp_project_dir, monkeypatch
    ):
        """C-1 反例：auto/cached_decision 路径不应有 pending_record（None 表示无需审阅）。"""
        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        self._patch_com(monkeypatch, ["28×1.9", "80×2.4"])
        r = resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")

        assert r.source == "auto"
        assert r.pending_record is None

    def test_path_5_halt_raises_needs_user_decision(
        self, tmp_project_dir, monkeypatch
    ):
        """默认 policy=halt + 含糊匹配 → 抛 NeedsUserDecision"""
        from adapters.solidworks.sw_config_broker import (
            NeedsUserDecision,
            resolve_config_for_part,
        )

        monkeypatch.delenv("CAD_AMBIGUOUS_CONFIG_POLICY", raising=False)
        self._patch_com(monkeypatch, ["AAA", "BBB"])

        with pytest.raises(NeedsUserDecision) as exc_info:
            resolve_config_for_part(self.BOM, self.SLDPRT, subsystem="end_effector")

        exc = exc_info.value
        assert exc.part_no == "GIS-EE-001-03"
        assert exc.subsystem == "end_effector"
        assert (
            exc.pending_record["match_failure_reason"]
            == "no_exact_or_fuzzy_match_with_high_confidence"
        )


class TestValidateCachedDecisionRobustness:
    """C-2 + I-3 修复：cache 校验和 decision 字段值的边界处理。"""

    @pytest.fixture(autouse=True)
    def _enable_broker(self, monkeypatch):
        """Task 14.5 opt-out：含 test_resolve_unknown_decision_value_raises 调真 resolve_config_for_part。"""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

    def test_validate_skips_third_check_when_available_empty(self):
        """C-2: COM transient 失败（available=[]）时第三项校验应 short-circuit 返回 valid。

        Why: available=[] 意味着 COM 列配置失败而非 SW 升级删除了 config，
        摧毁缓存会让用户花时间确认的决策被一次 COM 抖动洗掉。
        """
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = {
            "bom_dim_signature": "O型圈|FKM Φ80×2.4",
            "sldprt_filename": "o-rings.sldprt",
            "decision": "use_config",
            "config_name": "80×2.4",
        }
        # available 为空模拟 COM 失败
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="O型圈|FKM Φ80×2.4",
            current_sldprt_filename="o-rings.sldprt",
            current_available_configs=[],
        )

        assert valid is True
        assert reason is None

    def test_validate_still_checks_third_when_available_non_empty_but_missing(self):
        """C-2 反例：available 非空但 config_name 缺失 → 仍应判失效（真删除场景）。"""
        from adapters.solidworks.sw_config_broker import _validate_cached_decision

        decision = {
            "bom_dim_signature": "X|Y",
            "sldprt_filename": "f.sldprt",
            "decision": "use_config",
            "config_name": "old_name",
        }
        valid, reason = _validate_cached_decision(
            decision,
            current_bom_signature="X|Y",
            current_sldprt_filename="f.sldprt",
            current_available_configs=["new_name"],  # 旧 config 真不在
        )

        assert valid is False
        assert reason == "config_name_not_in_available_configs"

    def test_resolve_unknown_decision_value_raises(
        self, tmp_project_dir, monkeypatch
    ):
        """I-3: cached decision 字段值非 use_config/fallback_cadquery → ValueError 而非静默 fall-through。

        Why: 静默 fall-through 到规则匹配会破坏"用户决策优先"承诺；
        坏 schema（手编 spec_decisions.json 引入未知值）应阻塞错误而非默默被规则覆盖。
        """
        import json

        from adapters.solidworks.sw_config_broker import resolve_config_for_part

        decisions = {
            "schema_version": 2,
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
                        "sldprt_filename": "o-rings series a gb.sldprt",
                        "decision": "spec_amended",  # 未知值
                        "config_name": "80×2.4",
                        "decided_at": "2026-04-25T00:00:00+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        path = tmp_project_dir / ".cad-spec-gen" / "spec_decisions.json"
        path.write_text(json.dumps(decisions), encoding="utf-8")

        from adapters.solidworks import sw_config_broker
        sw_config_broker._CONFIG_LIST_CACHE.clear()
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda p: ["80×2.4"]
        )

        bom = {
            "part_no": "GIS-EE-001-03",
            "name_cn": "O型圈",
            "material": "FKM Φ80×2.4",
        }
        with pytest.raises(ValueError, match="未知 decision"):
            resolve_config_for_part(
                bom, "/abs/path/o-rings series a gb.sldprt", subsystem="end_effector"
            )


@pytest.mark.skipif(sys.platform != "win32", reason="msvcrt only on Windows")
class TestFileLock:
    """spec §6 并发跑 codegen：msvcrt.locking 防并发 resolve。

    单元层只验证 contract（加 lock 后串行调用仍能成功 + lock 自释放）；
    真正的双进程并发阻塞测试在集成层 Task 18。
    """

    @pytest.fixture(autouse=True)
    def _enable_broker(self, monkeypatch):
        """Task 14.5 opt-out：本 class 验证文件锁行为，需要 broker 真路径。"""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

    def test_lock_does_not_block_serial_calls(self, tmp_project_dir, monkeypatch):
        """同进程内串行两次调 resolve_config_for_part 应都成功（lock 自释放）。"""
        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda p: ["80×2.4"]
        )

        bom = {"part_no": "X", "name_cn": "O型圈", "material": "FKM Φ80×2.4"}

        r1 = sw_config_broker.resolve_config_for_part(
            bom, "/p.sldprt", subsystem="ee"
        )
        r2 = sw_config_broker.resolve_config_for_part(
            bom, "/p.sldprt", subsystem="ee"
        )

        assert r1.source == "auto"
        assert r2.source == "auto"

    def test_lock_file_created_under_project_root(self, tmp_project_dir, monkeypatch):
        """lock 文件应落在 <project>/.cad-spec-gen/lock，证明走了 PROJECT_ROOT 而非真实仓库。"""
        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda p: ["80×2.4"]
        )

        bom = {"part_no": "X", "name_cn": "O型圈", "material": "FKM Φ80×2.4"}
        sw_config_broker.resolve_config_for_part(bom, "/p.sldprt", subsystem="ee")

        lock_path = tmp_project_dir / ".cad-spec-gen" / "lock"
        assert lock_path.exists(), "lock 文件未在 tmp_project_dir 创建"


class TestBrokerSafetyValve:
    """Task 14.5 (P0)：CAD_SW_BROKER_DISABLE=1 → 立即 policy_fallback，绝不进 SW。

    防护目的（spec rev 2 + Task 14.5 补丁）：
    - SW Premium silent automation 在 license check / Toolbox add-in 等场景仍可能弹
      modal 对话框，卡住 worker subprocess
    - 安全阀允许用户/CI/测试在 broker 入口立刻短路退到 CadQuery 兜底
    - tests/conftest.py 的 autouse fixture 默认设此 env，pytest 永不意外触发 SW
    - 仅 TestResolveConfigForPart / TestValidateCachedDecisionRobustness / TestFileLock
      三个 class 显式 opt-out（class-level autouse delenv）
    """

    BOM = {"part_no": "X", "name_cn": "O型圈", "material": "FKM Φ80×2.4"}
    SLDPRT = "/abs/path/seal.sldprt"

    def test_env_disable_returns_policy_fallback_without_com(
        self, tmp_project_dir, monkeypatch
    ):
        """env=1 时 resolve_config_for_part 立即返 policy_fallback，不调 _list_configs_via_com。"""
        from adapters.solidworks import sw_config_broker

        monkeypatch.setenv("CAD_SW_BROKER_DISABLE", "1")

        # 哨兵：若 _list_configs_via_com 被调，标记 + 返伪数据；测试断言它没被调
        com_called = {"flag": False}

        def _sentinel(_path: str) -> list[str]:
            com_called["flag"] = True
            return ["80×2.4"]

        sw_config_broker._CONFIG_LIST_CACHE.clear()
        monkeypatch.setattr(sw_config_broker, "_list_configs_via_com", _sentinel)

        r = sw_config_broker.resolve_config_for_part(
            self.BOM, self.SLDPRT, subsystem="end_effector",
        )

        assert com_called["flag"] is False, "安全阀启用时不应调 _list_configs_via_com"
        assert r.source == "policy_fallback"
        assert r.config_name is None
        assert r.confidence == 0.0
        assert r.available_configs == []
        assert "CAD_SW_BROKER_DISABLE" in r.notes

    def test_env_disable_does_not_acquire_file_lock(
        self, tmp_project_dir, monkeypatch
    ):
        """env=1 时不应进入 _project_file_lock（lock 文件不应被创建）。

        spec rev 2 + Task 14.5：安全阀越早短路越好；连项目锁都不取，
        最大限度避免任何文件 IO 副作用。
        """
        from adapters.solidworks import sw_config_broker

        monkeypatch.setenv("CAD_SW_BROKER_DISABLE", "1")
        sw_config_broker._CONFIG_LIST_CACHE.clear()

        sw_config_broker.resolve_config_for_part(
            self.BOM, self.SLDPRT, subsystem="end_effector",
        )

        lock_path = tmp_project_dir / ".cad-spec-gen" / "lock"
        assert not lock_path.exists(), (
            "安全阀启用时不应创建 lock 文件（应在拿锁前短路）"
        )

    def test_env_unset_lets_broker_proceed_normally(
        self, tmp_project_dir, monkeypatch
    ):
        """env 未设 → broker 走正常路径（验证安全阀只在显式 =1 时生效）。"""
        from adapters.solidworks import sw_config_broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)
        sw_config_broker._CONFIG_LIST_CACHE.clear()
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda p: ["80×2.4"]
        )

        r = sw_config_broker.resolve_config_for_part(
            self.BOM, self.SLDPRT, subsystem="end_effector",
        )

        assert r.source == "auto"
        assert r.config_name == "80×2.4"

    def test_env_zero_or_empty_does_not_trigger_safety_valve(
        self, tmp_project_dir, monkeypatch
    ):
        """仅严格 ==1 触发；其他取值（空字符串 / "0" / "false"）不短路。

        防御 truthy/falsy 误判：即便用户写 CAD_SW_BROKER_DISABLE=0 也不该误触发。
        """
        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda p: ["80×2.4"]
        )

        for v in ("", "0", "false", "no"):
            monkeypatch.setenv("CAD_SW_BROKER_DISABLE", v)
            r = sw_config_broker.resolve_config_for_part(
                self.BOM, self.SLDPRT, subsystem="end_effector",
            )
            assert r.source == "auto", f"env={v!r} 不应触发安全阀"


class TestConftestAutouseDefaultsBrokerDisable:
    """Task 14.5 (P0)：conftest autouse fixture 应让所有 pytest 默认 CAD_SW_BROKER_DISABLE=1。

    没有此防护时，任何漏 mock 的测试都可能误启 SW；有了此防护，所有测试默认安全，
    需要真跑 broker 的测试显式 opt-out（class-level autouse delenv）。
    """

    def test_default_env_is_set_to_1(self):
        """无任何 monkeypatch 时，os.environ["CAD_SW_BROKER_DISABLE"] 应为 '1'。"""
        import os

        assert os.environ.get("CAD_SW_BROKER_DISABLE") == "1", (
            "conftest autouse fixture 应默认设 CAD_SW_BROKER_DISABLE=1，"
            "实测 env={!r}".format(os.environ.get("CAD_SW_BROKER_DISABLE"))
        )


def _stub_completed_process():
    class FakeProc:
        returncode = 0
        stdout = b"[]"
        stderr = b""
    return FakeProc()


class TestPrewarmConfigLists:
    """Task 14.6：sw_config_broker.prewarm_config_lists 集成测试（spec §6.1 C 矩阵）。"""

    @pytest.fixture
    def patch_paths(self, monkeypatch, tmp_path):
        """所有 cache module 的 path 函数都指向 tmp_path 隔离目录。"""
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: target)
        return target

    @pytest.fixture
    def fake_sw(self, monkeypatch):
        """detect_solidworks 返 stable info（version_year=24, toolbox_dir='C:/SW'）。"""
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )

    def test_prewarm_disabled_by_safety_valve(self, patch_paths, fake_sw, monkeypatch):
        """CAD_SW_BROKER_DISABLE=1 → prewarm 立刻返不 spawn worker / 不写 cache."""
        from adapters.solidworks import sw_config_broker as broker

        # autouse 已设 disable=1；显式 spawn 守卫 mock subprocess 验证未调
        called = []
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: called.append((a, kw)) or _stub_completed_process(),
        )
        broker.prewarm_config_lists(["C:/p1.sldprt"])
        assert called == []
        assert not patch_paths.exists()

    def test_prewarm_all_miss_spawns_batch_once(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """全 cache miss → 1 次 batch spawn worker → 写回 cache."""
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        # 建 2 个真 sldprt 文件让 _stat_mtime/_stat_size 工作
        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)
        p2 = tmp_path / "p2.sldprt"
        p2.write_bytes(b"y" * 200)

        spawn_calls = []

        def fake_run(cmd, **kwargs):
            spawn_calls.append((cmd, kwargs))

            class FakeProc:
                returncode = 0
                stderr = b""
                stdout = json.dumps([
                    {"path": str(p1), "configs": ["A1", "A2"], "exit_code": 0},
                    {"path": str(p2), "configs": ["B1"], "exit_code": 0},
                ]).encode()

            return FakeProc()

        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1), str(p2)])

        assert len(spawn_calls) == 1  # batch 只 spawn 一次
        assert "--batch" in spawn_calls[0][0]
        assert patch_paths.exists()
        cache = json.loads(patch_paths.read_text(encoding="utf-8"))
        assert str(p1) in cache["entries"]
        assert cache["entries"][str(p1)]["configs"] == ["A1", "A2"]
        assert cache["entries"][str(p2)]["configs"] == ["B1"]
        assert cache["sw_version"] == 24
        assert cache["toolbox_path"] == "C:/SW"

    def test_prewarm_all_hit_no_spawn(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """全 cache 命中 → 0 spawn."""
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)
        st = p1.stat()
        cache = {
            "schema_version": 1,
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "generated_at": "2026-04-26T00:00:00+00:00",
            "entries": {
                str(p1): {
                    "mtime": int(st.st_mtime),
                    "size": st.st_size,
                    "configs": ["X"],
                },
            },
        }
        cache_mod._save_config_lists_cache(cache)

        spawn_calls = []
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: spawn_calls.append(a) or _stub_completed_process(),
        )
        broker.prewarm_config_lists([str(p1)])
        assert spawn_calls == []  # 0 spawn

    def test_prewarm_partial_miss_only_misses_batched(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """部分 miss → batch spawn 只含 miss 的 sldprt（命中件不重列）."""
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)
        p2 = tmp_path / "p2.sldprt"
        p2.write_bytes(b"y" * 200)
        st1 = p1.stat()
        cache = {
            "schema_version": 1,
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "generated_at": "2026-04-26T00:00:00+00:00",
            "entries": {
                str(p1): {
                    "mtime": int(st1.st_mtime),
                    "size": st1.st_size,
                    "configs": ["P1A"],
                },
            },
        }
        cache_mod._save_config_lists_cache(cache)

        captured_stdin = []

        def fake_run(cmd, input=None, **kwargs):
            captured_stdin.append(input)

            class FakeProc:
                returncode = 0
                stderr = b""
                stdout = json.dumps(
                    [{"path": str(p2), "configs": ["P2A"], "exit_code": 0}],
                ).encode()

            return FakeProc()

        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1), str(p2)])

        # batch 只含 p2（p1 已命中跳过）
        assert len(captured_stdin) == 1
        sent = json.loads(captured_stdin[0])
        assert sent == [str(p2)]

    def test_prewarm_worker_failure_does_not_write_cache(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """worker exit != 0 → prewarm 静默 return 不抛。
        I-2 修复后：envelope（sw_version/toolbox_path）已在 invalidate 时落盘，
        但 entries 仍为空（worker 未成功写入任何条目）。"""
        import json
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)

        def fake_run(cmd, **kwargs):
            class FakeProc:
                returncode = 4
                stderr = b"worker: pywin32 import failed"
                stdout = b""

            return FakeProc()

        monkeypatch.setattr("subprocess.run", fake_run)

        # 不抛异常
        broker.prewarm_config_lists([str(p1)])
        # I-2 修复：envelope 已立即落盘（sw_version/toolbox_path 已写），但 entries 为空
        assert patch_paths.exists(), "envelope 应已在 invalidate 时落盘"
        saved = json.loads(patch_paths.read_text())
        assert saved["entries"] == {}, "worker 失败后 entries 应为空"
        assert saved["sw_version"] == 24, "sw_version 应已写入 envelope"

    def test_prewarm_worker_timeout_does_not_write_cache(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """subprocess.TimeoutExpired → prewarm 静默 return 不抛。
        I-2 修复后：envelope（sw_version/toolbox_path）已在 invalidate 时落盘，
        但 entries 仍为空（worker 超时未成功写入任何条目）。"""
        import json
        import subprocess

        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)

        def fake_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="x", timeout=180)

        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])  # 不抛
        # I-2 修复：envelope 已立即落盘（sw_version/toolbox_path 已写），但 entries 为空
        assert patch_paths.exists(), "envelope 应已在 invalidate 时落盘"
        saved = json.loads(patch_paths.read_text())
        assert saved["entries"] == {}, "worker 超时后 entries 应为空"
        assert saved["sw_version"] == 24, "sw_version 应已写入 envelope"

    def test_prewarm_envelope_invalidated_clears_entries(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """SW 升级（cache.sw_version=23, current=24）→ entries 清空 → 全 batch 重列."""
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)
        st = p1.stat()
        cache_old = {
            "schema_version": 1,
            "sw_version": 23,  # 旧 SW
            "toolbox_path": "C:/SW",
            "generated_at": "2025-01-01T00:00:00+00:00",
            "entries": {
                str(p1): {
                    "mtime": int(st.st_mtime),
                    "size": st.st_size,
                    "configs": ["OLD"],
                },
            },
        }
        cache_mod._save_config_lists_cache(cache_old)

        captured_stdin = []

        def fake_run(cmd, input=None, **kwargs):
            captured_stdin.append(input)

            class FakeProc:
                returncode = 0
                stderr = b""
                stdout = json.dumps(
                    [{"path": str(p1), "configs": ["NEW"], "exit_code": 0}],
                ).encode()

            return FakeProc()

        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])

        # batch 含 p1（envelope 失效后视为全 miss）
        assert len(captured_stdin) == 1
        sent = json.loads(captured_stdin[0])
        assert sent == [str(p1)]
        # 新 cache：sw_version 升级 + entries 全新
        cache_new = json.loads(patch_paths.read_text(encoding="utf-8"))
        assert cache_new["sw_version"] == 24
        assert cache_new["entries"][str(p1)]["configs"] == ["NEW"]


class TestListConfigsViaComThreeLayer:
    """Task 14.6：_list_configs_via_com 三层 cache (L2 → L1 → fallback)."""

    @pytest.fixture
    def patch_paths(self, monkeypatch, tmp_path):
        from adapters.solidworks import sw_config_lists_cache as cache_mod
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(cache_mod, "get_config_lists_cache_path", lambda: target)
        return target

    @pytest.fixture
    def fake_sw(self, monkeypatch):
        from adapters.solidworks import sw_detect
        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, version_year=24,
                                     toolbox_dir="C:/SW"),
        )

    def test_l1_persistent_cache_hit_fills_l2_no_spawn(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """L2 miss + L1 命中 → 填 L2 + 返结果 + 0 spawn."""
        from adapters.solidworks import sw_config_broker as broker
        from adapters.solidworks import sw_config_lists_cache as cache_mod

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        # 清 L2
        broker._CONFIG_LIST_CACHE.clear()

        # 预填 L1（key 必须用 abs_path——_list_configs_via_com 内部用 resolve()）
        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)
        st = p1.stat()
        cache_mod._save_config_lists_cache({
            "schema_version": 1,
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "generated_at": "2026-04-26T00:00:00+00:00",
            "entries": {
                str(p1.resolve()): {
                    "mtime": int(st.st_mtime),
                    "size": st.st_size,
                    "configs": ["FROM_L1"],
                },
            },
        })

        spawn_calls = []
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: spawn_calls.append(a) or _stub_completed_process(),
        )

        result = broker._list_configs_via_com(str(p1))
        assert result == ["FROM_L1"]
        assert spawn_calls == []  # 0 spawn — L1 命中
        # L2 已填
        assert broker._CONFIG_LIST_CACHE[str(p1.resolve())] == ["FROM_L1"]

    def test_l2_in_process_cache_hit_no_spawn_no_l1_read(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """L2 命中 → 不读 L1 文件 + 0 spawn."""
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        # 预填 L2
        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)
        broker._CONFIG_LIST_CACHE[str(p1.resolve())] = ["FROM_L2"]

        spawn_calls = []
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: spawn_calls.append(a) or _stub_completed_process(),
        )

        # L1 文件不存在；L2 命中即 return
        result = broker._list_configs_via_com(str(p1))
        assert result == ["FROM_L2"]
        assert spawn_calls == []

    def test_fallback_spawns_single_only_fills_l2_not_l1(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """L1+L2 全 miss → fallback 单件 spawn → 只填 L2 不写 L1."""
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        broker._CONFIG_LIST_CACHE.clear()

        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)

        # mock 单件 worker 返一个 config（旧契约：text=True，stdout 是 str）
        def fake_run(cmd, **kwargs):
            class FakeProc:
                returncode = 0
                stderr = ""
                stdout = json.dumps(["FROM_FALLBACK"]) + "\n"

            return FakeProc()

        monkeypatch.setattr("subprocess.run", fake_run)

        result = broker._list_configs_via_com(str(p1))
        assert result == ["FROM_FALLBACK"]
        # L2 已填
        assert broker._CONFIG_LIST_CACHE[str(p1.resolve())] == ["FROM_FALLBACK"]
        # L1 持久化文件 未 写（spec §3.1 issue 4 决策）
        assert not patch_paths.exists()

    def test_prewarm_writes_normalized_key_so_reader_hits(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """I-1 regression：prewarm 用 mixed-slash 路径 → cache key 必须归一化 →
        `_list_configs_via_com` 用同物理文件的不同字面值（forward-slash / 反向）也命中 cache，
        不再 spawn fallback subprocess。
        """
        import json as _json
        import subprocess as _sp
        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        # 建真 sldprt 文件
        sldprt = tmp_path / "p1.SLDPRT"
        sldprt.write_text("dummy")
        # 故意用 forward-slash 字面值（Windows 上与 resolve() 后的反斜杠不同）
        forward_slash_path = sldprt.as_posix()

        # mock subprocess.run：batch 模式返一条假 result
        def _fake_run(cmd, **kwargs):
            if "--batch" in cmd:
                results = [{"path": forward_slash_path, "configs": ["6201"], "exit_code": 0}]
                return _sp.CompletedProcess(
                    cmd, 0, stdout=_json.dumps(results).encode(), stderr=b"",
                )
            # 单件 fallback 不应被调（该断言在 reader 阶段验证）
            raise AssertionError(f"unexpected single-file spawn: {cmd}")

        monkeypatch.setattr("subprocess.run", _fake_run)

        broker._CONFIG_LIST_CACHE.clear()
        broker.prewarm_config_lists([forward_slash_path])

        # reader 用 raw forward-slash → 必须命中 cache（不抛 AssertionError）
        configs = broker._list_configs_via_com(forward_slash_path)
        assert configs == ["6201"]

        # 第二次：reader 用反斜杠版同一文件 → 也必须命中（key 归一化）
        backslash_path = str(sldprt)
        broker._CONFIG_LIST_CACHE.clear()  # 清 L2 强制走 L1
        configs2 = broker._list_configs_via_com(backslash_path)
        assert configs2 == ["6201"]


# ============================================================
# PR #19 review followup — I-2 + I-3 修复测试
# spec: docs/superpowers/specs/2026-04-26-sw-config-broker-i2-i3-fix-design.md
# ============================================================
# broker / cache_mod / pytest 已在文件顶部 import；I-3 测试用的 mock helpers
# (make_fake_msvcrt / make_tracking_save / make_synced_time_mock) 在 I-3 task
# (Phase B.3+) 引入，按 task-by-task TDD 严格只加当前 task 需要的代码。


def make_failing_save(exception_to_raise):
    """构造抛指定异常的 fake _save_config_lists_cache（spec §6.4）。"""
    def failing_save(cache):
        raise exception_to_raise
    return failing_save


def make_fake_msvcrt(locking_calls: list, contention_count: int = 0):
    """构造 fake msvcrt 模块（spec §6.4）— 跨平台 universal。

    使用 setitem(sys.modules, "msvcrt", ...) 注入，函数体内 `import msvcrt` 命中 fake。
    Linux 上 real msvcrt 不存在，setattr 会炸；setitem 模式才能跨平台跑。
    """
    fake = types.ModuleType("msvcrt")
    fake.LK_NBLCK = 1
    fake.LK_UNLCK = 2
    fake.LK_LOCK = 3
    fake.LK_NBRLCK = 4

    def locking(fd, mode, nbytes):
        mode_name = "LK_NBLCK" if mode == fake.LK_NBLCK else "LK_UNLCK"
        locking_calls.append((mode_name, fd, nbytes))
        if mode == fake.LK_NBLCK and len(locking_calls) <= contention_count:
            raise OSError("contended")
        return None

    fake.locking = locking
    return fake


def make_synced_time_mock(monkeypatch):
    """time.monotonic 由 time.sleep 推进（spec §6.4）— 防 busy loop bug 漏测。"""
    fake_now = [0.0]

    def fake_sleep(seconds):
        fake_now[0] += seconds

    def fake_monotonic():
        return fake_now[0]

    monkeypatch.setattr(broker.time, "sleep", fake_sleep)
    monkeypatch.setattr(broker.time, "monotonic", fake_monotonic)
    return fake_now


# ─── I-2 修复测试（14 测试 / 7 维度 / spec §6.2）───

class TestI2EnvelopePersistence:
    """spec §6.2 I-2 测试矩阵（14 测试 / 7 维度）。"""

    @pytest.fixture(autouse=True)
    def _enable_broker(self, monkeypatch):
        """conftest.py:212 默认 CAD_SW_BROKER_DISABLE=1 锁死 broker；
        I-2 测试需要进 prewarm 真路径触发 envelope 持久化逻辑。
        T27 内显式 setenv 覆盖此默认（验证 disable 安全阀仍 work）。"""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

    # ─── E1. 核心顺序 invariant（2 测试）───

    def test_invalidate_save_called_before_worker_spawn(
        self, monkeypatch, tmp_project_dir,
    ):
        """T19：spec §6.2 — call_order 列表断言：save(2025, entries={}) 出现在
        subprocess.run(worker) 之前。防 envelope 升级 save 漏写盘 bug。"""
        # 旧 cache (sw=2024) — 触发 invalidate
        old_cache = {
            "schema_version": 1,
            "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024,
            "toolbox_path": "C:/old",
            "entries": {},
        }

        call_order = []

        # mock load 返旧 cache
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        # mock detect 返新版本
        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        # tracking_save：记录调用
        def tracking_save(cache):
            call_order.append(("save", cache.get("sw_version"), len(cache.get("entries", {}))))
        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", tracking_save)

        # mock subprocess.run：worker fail
        def tracking_run(cmd, **kwargs):
            call_order.append(("spawn", "worker"))
            import subprocess
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"boom")
        monkeypatch.setattr(broker.subprocess, "run", tracking_run)

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        # 断言顺序：save 必须在 spawn 之前
        assert call_order[0] == ("save", 2025, 0), f"call_order={call_order}"
        assert call_order[1] == ("spawn", "worker"), f"call_order={call_order}"

    def test_invalidate_save_content_correct(
        self, monkeypatch, tmp_project_dir,
    ):
        """T20：spec §6.2 — 测试前提：mock 旧 sw=2024 / 新 sw=2025（值显式不同），
        防 mutation `cache.get("sw_version", info.version_year)` 偷换旧值仍 pass。"""
        import json

        # 写真旧 cache 文件触发 invalidate（不 mock _load）
        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1,
            "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024,
            "toolbox_path": "C:/old",
            "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        captured = {}

        def capturing_save(cache):
            # 深拷贝避免 caller mutate 影响断言
            captured["cache"] = {k: v for k, v in cache.items()}
        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", capturing_save)

        # mock subprocess.run：worker fail（让 prewarm 不进 line 612 第二次 save）
        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        cache = captured["cache"]
        assert cache["schema_version"] == 1
        assert cache["sw_version"] == 2025  # 防 cache.get() 偷换旧 2024
        assert cache["toolbox_path"] == "C:/new"
        assert cache["entries"] == {}
        # generated_at 仅验存在 + ISO 8601 格式
        assert "generated_at" in cache
        from datetime import datetime
        datetime.fromisoformat(cache["generated_at"])  # 抛 ValueError 即 fail

    # ─── E2. save 失败路径（3 测试）───

    def test_invalidate_save_oserror_warns_and_continues_to_worker(
        self, monkeypatch, tmp_project_dir, caplog,
    ):
        """T21：spec §6.2 — mock save 抛 OSError → log.warning（含"envelope save 失败"）+
        worker spawn 仍调用 + prewarm 不抛。"""
        import logging

        old_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        monkeypatch.setattr(
            cache_mod, "_save_config_lists_cache",
            make_failing_save(OSError("disk full")),
        )

        spawn_called = []
        import subprocess
        def tracking_run(cmd, **kwargs):
            spawn_called.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, b"", b"")
        monkeypatch.setattr(broker.subprocess, "run", tracking_run)

        with caplog.at_level(logging.WARNING):
            broker.prewarm_config_lists(["C:/p1.sldprt"])  # 不应抛

        assert any("envelope save 失败" in rec.message for rec in caplog.records), \
            f"warn missing: {[r.message for r in caplog.records]}"
        assert len(spawn_called) == 1, "worker spawn 未被调用（fire-and-forget 契约破）"

    @pytest.mark.parametrize("exc_type", [
        RuntimeError, KeyError, TypeError, ValueError, AttributeError,
    ])
    def test_invalidate_save_any_exception_warns_and_continues(
        self, exc_type, monkeypatch, tmp_project_dir, caplog,
    ):
        """T22：spec §6.2 — 5 种 Exception 子类 parametrize；防 mutation
        `except (OSError, RuntimeError)` 漏 KeyError 等。"""
        import logging

        old_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        monkeypatch.setattr(
            cache_mod, "_save_config_lists_cache",
            make_failing_save(exc_type("test")),
        )

        spawn_called = []
        import subprocess
        def tracking_run(cmd, **kwargs):
            spawn_called.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, b"", b"")
        monkeypatch.setattr(broker.subprocess, "run", tracking_run)

        with caplog.at_level(logging.WARNING):
            broker.prewarm_config_lists(["C:/p1.sldprt"])  # 不应抛

        assert any("envelope save 失败" in rec.message for rec in caplog.records), \
            f"warn missing for {exc_type.__name__}"
        assert len(spawn_called) == 1, \
            f"worker spawn 未被调用 for {exc_type.__name__}（fire-and-forget 契约破）"

    def test_invalidate_save_baseexception_propagates(
        self, monkeypatch, tmp_project_dir,
    ):
        """T22b：spec §6.2 — KeyboardInterrupt 是 BaseException 子类，
        except Exception 天然不 catch → 上抛 + worker spawn 不调用。"""
        old_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        monkeypatch.setattr(
            cache_mod, "_save_config_lists_cache",
            make_failing_save(KeyboardInterrupt()),
        )

        spawn_called = []
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: spawn_called.append(cmd) or None,
        )

        with pytest.raises(KeyboardInterrupt):
            broker.prewarm_config_lists(["C:/p1.sldprt"])

        assert len(spawn_called) == 0, "worker spawn 不应被调用（KeyboardInterrupt 应立即上抛）"

    # ─── E3. 第二次 prewarm 验证（2 测试）───

    def test_two_prewarm_calls_after_worker_fail_no_redundant_invalidate(
        self, monkeypatch, tmp_project_dir,
    ):
        """T23：spec §6.2 — 第 1 次 prewarm worker fail → 第 2 次 prewarm 进入时
        envelope_invalidated == False（这是 I-2 修复的核心 user value）。"""
        import json

        # 旧 cache (sw=2024) 写盘
        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        # mock worker fail
        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        # 第 2 次进入：load 应读到新 envelope（sw=2025）→ invalidated False
        cache_after = cache_mod._load_config_lists_cache()
        assert cache_after["sw_version"] == 2025, \
            f"第 1 次 prewarm 后磁盘 sw_version 仍={cache_after.get('sw_version')}（envelope 未持久化）"
        assert cache_mod._envelope_invalidated(cache_after) is False, \
            "第 2 次 prewarm envelope_invalidated 应为 False（修复后不再死循环）"

    def test_two_prewarm_calls_after_worker_fail_retries_failed_sldprt(
        self, monkeypatch, tmp_project_dir,
    ):
        """T24：spec §6.2 — 第 2 次 prewarm 走 miss diff → spawn worker 重试上次失败的 sldprt。"""
        import json

        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        spawn_count = [0]
        import subprocess
        def tracking_run(cmd, **kwargs):
            spawn_count[0] += 1
            return subprocess.CompletedProcess(cmd, 1, b"", b"")
        monkeypatch.setattr(broker.subprocess, "run", tracking_run)

        broker.prewarm_config_lists(["C:/p1.sldprt"])
        broker.prewarm_config_lists(["C:/p1.sldprt"])

        assert spawn_count[0] == 2, \
            f"第 2 次 prewarm 未重试 worker；spawn_count={spawn_count[0]}"

    # ─── E4. detect 边角（2 测试）───

    def test_invalidate_save_when_sw_not_installed(
        self, monkeypatch, tmp_project_dir,
    ):
        """T25：spec §6.2 — detect 返 SwInfo(installed=False, version_year=0,
        toolbox_dir="") → 仍 save sw_version=0 / toolbox_path="" 到磁盘。"""
        import json

        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            installed = False
            version_year = 0
            toolbox_dir = ""
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        cache_after = cache_mod._load_config_lists_cache()
        assert cache_after["sw_version"] == 0
        assert cache_after["toolbox_path"] == ""

    def test_invalidate_save_propagates_detect_unexpected_exception(
        self, monkeypatch, tmp_project_dir,
    ):
        """T26：spec §6.2 — detect 抛 RuntimeError → 上抛（detect 调用不在新 try/except 包围范围内；
        防实施者把 except 范围误扩到包整个 invalidate 分支）。"""
        old_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: old_cache.copy())

        def raising_detect():
            raise RuntimeError("detect 内部 bug")
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", raising_detect,
        )

        with pytest.raises(RuntimeError, match="detect 内部 bug"):
            broker.prewarm_config_lists(["C:/p1.sldprt"])


    # ─── E5. 安全阀 regression（1 测试）───

    def test_prewarm_disable_env_skips_all_cache_ops(
        self, monkeypatch, tmp_project_dir,
    ):
        """T27：spec §6.2 — CAD_SW_BROKER_DISABLE=1 → 整函数早返；
        磁盘 cache 文件不被读 / 不被写。"""
        monkeypatch.setenv("CAD_SW_BROKER_DISABLE", "1")

        save_calls = []
        load_calls = []
        monkeypatch.setattr(
            cache_mod, "_save_config_lists_cache",
            lambda c: save_calls.append(c),
        )
        monkeypatch.setattr(
            cache_mod, "_load_config_lists_cache",
            lambda: load_calls.append(1) or {},
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        assert save_calls == [], "DISABLE=1 时不应调 save"
        assert load_calls == [], "DISABLE=1 时不应调 load"

    # ─── E6. 磁盘内容精确性（3 测试）───

    def test_invalidate_save_disk_json_schema_full_match(
        self, monkeypatch, tmp_project_dir,
    ):
        """T28：spec §6.2 — save 后磁盘 JSON 5 字段全员；schema_version=1 / sw=新 /
        toolbox=新 / entries={}；generated_at 仅验存在 + ISO 8601 格式。"""
        import json
        from datetime import datetime

        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        disk = json.loads(cache_path.read_text())
        # 5 字段全员
        for k in ("schema_version", "generated_at", "sw_version", "toolbox_path", "entries"):
            assert k in disk, f"字段 {k} 缺失"
        assert disk["schema_version"] == 1
        assert disk["sw_version"] == 2025
        assert disk["toolbox_path"] == "C:/new"
        assert disk["entries"] == {}
        # generated_at ISO 8601 格式校验
        datetime.fromisoformat(disk["generated_at"])

    def test_invalidate_save_then_worker_success_disk_has_entries(
        self, monkeypatch, tmp_project_dir, tmp_path,
    ):
        """T29：spec §6.2 — invalidate save → worker success → 第 2 次 save → 磁盘 JSON 含 entries{p1, p2}。"""
        import json

        cache_path = cache_mod.get_config_lists_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        # 真建 sldprt 文件让 _stat_mtime/_stat_size 返合理值
        p1 = tmp_path / "p1.sldprt"
        p1.write_text("dummy1")
        p2 = tmp_path / "p2.sldprt"
        p2.write_text("dummy2")

        import subprocess
        def success_run(cmd, **kwargs):
            results = [
                {"path": str(p1), "configs": ["A"], "exit_code": 0},
                {"path": str(p2), "configs": ["B"], "exit_code": 0},
            ]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(results).encode(), b"")
        monkeypatch.setattr(broker.subprocess, "run", success_run)

        broker.prewarm_config_lists([str(p1), str(p2)])

        disk = json.loads(cache_path.read_text())
        assert disk["sw_version"] == 2025
        assert len(disk["entries"]) == 2
        # 既有 _normalize_sldprt_key 决定 key 格式（resolve()），用同样 normalize 验证
        from adapters.solidworks.sw_config_broker import _normalize_sldprt_key
        assert _normalize_sldprt_key(str(p1)) in disk["entries"]
        assert _normalize_sldprt_key(str(p2)) in disk["entries"]

    def test_invalidate_save_does_not_overwrite_unrelated_user_files(
        self, monkeypatch, tmp_project_dir,
    ):
        """T30：spec §6.2 — save 只写 sw_config_lists.json；同目录 sw_toolbox_index.json 等不被 touched。"""
        import json

        cache_path = cache_mod.get_config_lists_cache_path()
        user_dir = cache_path.parent
        user_dir.mkdir(parents=True, exist_ok=True)

        # 旧 cache + 同目录其他文件
        cache_path.write_text(json.dumps({
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2024, "toolbox_path": "C:/old", "entries": {},
        }))
        unrelated_index = user_dir / "sw_toolbox_index.json"
        unrelated_index.write_text('{"unrelated": true}')
        unrelated_decisions = user_dir / "decisions.json"
        unrelated_decisions.write_text('{"some": "data"}')

        index_mtime_before = unrelated_index.stat().st_mtime
        decisions_mtime_before = unrelated_decisions.stat().st_mtime

        class FakeInfo:
            version_year = 2025
            toolbox_dir = "C:/new"
        monkeypatch.setattr(
            "adapters.solidworks.sw_detect.detect_solidworks", lambda: FakeInfo(),
        )

        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        # 不相关文件 mtime 不变
        assert unrelated_index.stat().st_mtime == index_mtime_before
        assert unrelated_decisions.stat().st_mtime == decisions_mtime_before
        assert unrelated_index.read_text() == '{"unrelated": true}'
        assert unrelated_decisions.read_text() == '{"some": "data"}'

    # ─── E7. 路径 gating（1 测试）───

    def test_no_invalidate_no_extra_envelope_save(
        self, monkeypatch, tmp_project_dir,
    ):
        """T31：spec §6.2 — envelope 已新（_envelope_invalidated 返 False）→
        call_order 中不出现 invalidate 分支 save；只有既有 line 612 save。
        防实施者把新 save 写成无条件调用、漏在 if 分支外。"""
        # cache 已是新 envelope（不 invalidate）
        new_cache = {
            "schema_version": 1, "generated_at": "2026-04-01T00:00:00+00:00",
            "sw_version": 2025, "toolbox_path": "C:/new", "entries": {},
        }
        monkeypatch.setattr(cache_mod, "_load_config_lists_cache", lambda: new_cache.copy())

        # 强制 _envelope_invalidated 返 False
        monkeypatch.setattr(cache_mod, "_envelope_invalidated", lambda c: False)

        # 不需 detect mock，因为不进 invalidate 分支

        call_order = []

        def tracking_save(cache):
            call_order.append(("save", cache.get("sw_version"), len(cache.get("entries", {}))))
        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", tracking_save)

        # mock subprocess.run worker fail 让既有 line 612 save 也不触发
        import subprocess
        monkeypatch.setattr(
            broker.subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )

        broker.prewarm_config_lists(["C:/p1.sldprt"])

        # 关键断言：cache 已新 + worker fail → call_order 应为空（无 save）
        assert call_order == [], \
            f"envelope 已新且 worker fail 时不应有 save；实际 call_order={call_order}"


# ─── I-3 修复测试（18 测试 / 8 维度 / spec §6.1）───

class TestI3LockBehavior:
    """spec §6.1 I-3 测试矩阵（18 测试 / 8 维度）。"""

    # ─── D1. happy path（2 测试）───

    def test_lock_yields_immediately_when_uncontended(
        self, monkeypatch, tmp_project_dir,
    ):
        """T1：spec §6.1 — LK_NBLCK 第 1 次成功 → 0 banner / 0 进度 / yield 正常 / unlock 调用 1 次。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

        entered = []
        with broker._project_file_lock():
            entered.append(True)

        assert entered == [True], "yield body 未执行"
        assert len(locking_calls) == 2, f"应有 1 LK_NBLCK + 1 LK_UNLCK；实际 {locking_calls}"
        assert locking_calls[0][0] == "LK_NBLCK"
        assert locking_calls[1][0] == "LK_UNLCK"

    def test_lock_yield_body_exception_still_releases_lock(
        self, monkeypatch, tmp_project_dir,
    ):
        """T2：spec §6.1 — yield body 抛 ValueError → 异常上抛 + unlock 仍调用 + fp.close() 仍执行。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

        with pytest.raises(ValueError, match="boom"):
            with broker._project_file_lock():
                raise ValueError("boom")

        # unlock 仍被调
        assert any(c[0] == "LK_UNLCK" for c in locking_calls), \
            f"unlock 未调用；locking_calls={locking_calls}"

    # ─── D2. 进度提示节奏（4 测试）───

    def test_lock_banner_printed_immediately_on_first_contention(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T3：spec §6.1 — 第 1 次 LK_NBLCK 抛 OSError → banner 立即印（不等 5s）。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=2)  # 2 次失败
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        # banner 应在 t=0 立即印（等待 0s 即印）
        assert "检测到另一个 codegen" in err or "codegen" in err, f"banner 缺失；stderr={err}"
        assert "占用" in err

    def test_lock_no_progress_when_acquired_within_5s(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T4：spec §6.1 — 撞锁 3s 后拿到 → banner 印 1 次 + 进度行 0 行。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        # contention_count=6 → 6 次失败 × 0.5s = 3s 后第 7 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=6)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        assert err.count("仍在等待锁释放") == 0, \
            f"撞锁 3s 不应印进度；stderr={err}"

    def test_lock_one_progress_at_5s_threshold(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T5：spec §6.1 — 撞锁 6s 后拿到 → banner 1 + 进度行 1 行（含 "已等 5s"）。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        # contention_count=12 → 12 × 0.5s = 6s 后第 13 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=12)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        assert err.count("仍在等待锁释放") == 1, \
            f"撞锁 6s 应印 1 行进度；stderr={err}"
        assert "已等 5s" in err, f"进度行 elapsed 数不对；stderr={err}"

    def test_lock_progress_intervals_strictly_5s(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T6：spec §6.1 — 撞锁 16s 后拿到 → 进度行 3 行（5s/10s/15s 时刻）；
        4s/9s/14s 时刻不印。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        # contention_count=32 → 32 × 0.5s = 16s 后第 33 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=32)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        progress_count = err.count("仍在等待锁释放")
        assert progress_count == 3, \
            f"撞锁 16s 应印 3 行进度（5/10/15s）；实际 {progress_count}；stderr={err}"
        for n in [5, 10, 15]:
            assert f"已等 {n}s" in err, f"缺 已等 {n}s；stderr={err}"

    # ─── D3. 永不超时（2 测试）───

    def test_lock_never_raises_timeout_at_60s_and_sleeps_between_polls(
        self, monkeypatch, tmp_project_dir,
    ):
        """T7：spec §6.1 — 撞锁 60s+ → 不抛 OSError + sleep 调用次数 ≥ 100
        + 每次 sleep == LOCK_POLL_INTERVAL_SEC（防 CPU busy loop / 间隔被改）。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        # contention_count=120 → 120 × 0.5s = 60s 后第 121 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=120)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

        # 自定义 mock 跟踪 sleep 调用
        sleep_calls = []
        fake_now = [0.0]

        def tracking_sleep(seconds):
            sleep_calls.append(seconds)
            fake_now[0] += seconds

        monkeypatch.setattr(broker.time, "sleep", tracking_sleep)
        monkeypatch.setattr(broker.time, "monotonic", lambda: fake_now[0])

        with broker._project_file_lock():
            pass

        assert len(sleep_calls) >= 100, \
            f"sleep 调用次数 {len(sleep_calls)} < 100（防 CPU busy loop）"
        assert all(s == broker.LOCK_POLL_INTERVAL_SEC for s in sleep_calls), \
            f"sleep 间隔不严格 {broker.LOCK_POLL_INTERVAL_SEC}s；首 5 个: {sleep_calls[:5]}"

    def test_lock_progress_count_matches_floor_elapsed_div_5(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T8：spec §6.1 — 撞锁 27s 后拿到 → 进度行恰 5 行（5/10/15/20/25 时刻）。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        # contention_count=54 → 54 × 0.5s = 27s 后第 55 次成功
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=54)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        progress_count = err.count("仍在等待锁释放")
        assert progress_count == 5, \
            f"撞锁 27s 应印 5 行进度（5/10/15/20/25s）；实际 {progress_count}；stderr={err}"

    # ─── D4. Ctrl+C 中止（2 测试）───

    def test_lock_keyboard_interrupt_during_sleep_propagates(
        self, monkeypatch, tmp_project_dir,
    ):
        """T9：spec §6.1 — sleep 期间 raise KeyboardInterrupt → 立即上抛 +
        fp.close() 仍执行 + 不调 unlock（锁未拿到）。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=999)  # 永不成功
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

        def kbd_sleep(seconds):
            raise KeyboardInterrupt()
        monkeypatch.setattr(broker.time, "sleep", kbd_sleep)
        monkeypatch.setattr(broker.time, "monotonic", lambda: 0.0)

        with pytest.raises(KeyboardInterrupt):
            with broker._project_file_lock():
                pass

        # unlock 不应被调（锁从未拿到）
        unlock_count = sum(1 for c in locking_calls if c[0] == "LK_UNLCK")
        assert unlock_count == 0, f"锁未拿到不应 unlock；locking_calls={locking_calls}"

    def test_lock_keyboard_interrupt_after_lk_nblck_fails_propagates(
        self, monkeypatch, tmp_project_dir,
    ):
        """T10：spec §6.1 — LK_NBLCK 抛 OSError 后、进 sleep 前 raise KeyboardInterrupt
        → 立即上抛 + fp.close() 仍执行。"""
        monkeypatch.setattr(sys, "platform", "win32")

        # locking 抛 OSError，print 抛 KeyboardInterrupt（在 sleep 之前）
        locking_calls = []
        def lk_nblck_fail(fd, mode, nbytes):
            locking_calls.append((mode, fd, nbytes))
            raise OSError("contended")

        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)
        fake_msvcrt.locking = lk_nblck_fail
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

        # print 抛 KeyboardInterrupt（在 banner 那一行）
        def kbd_print(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr("builtins.print", kbd_print)
        monkeypatch.setattr(broker.time, "monotonic", lambda: 0.0)

        with pytest.raises(KeyboardInterrupt):
            with broker._project_file_lock():
                pass

    # ─── D5. 清理路径（3 测试）───

    def test_lock_unlock_oserror_silently_warned(
        self, monkeypatch, tmp_project_dir, caplog,
    ):
        """T11：spec §6.1 — unlock 抛 OSError → log.warning 触发 + 不冒到 caller。"""
        import logging

        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)

        def fail_on_unlock(fd, mode, nbytes):
            locking_calls.append((mode, fd, nbytes))
            if mode == fake_msvcrt.LK_UNLCK:
                raise OSError("unlock failed")
            return None

        fake_msvcrt.locking = fail_on_unlock
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

        with caplog.at_level(logging.WARNING):
            with broker._project_file_lock():
                pass  # 不应抛

        assert any("unlock 异常" in rec.message for rec in caplog.records), \
            f"warn 缺；records={[r.message for r in caplog.records]}"

    def test_lock_unlock_non_oserror_propagates(
        self, monkeypatch, tmp_project_dir,
    ):
        """T12：spec §6.1 — unlock 抛 RuntimeError → 上抛（异常类型严格性，防"宽 except"）。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)

        def fail_on_unlock(fd, mode, nbytes):
            locking_calls.append((mode, fd, nbytes))
            if mode == fake_msvcrt.LK_UNLCK:
                raise RuntimeError("unexpected")
            return None

        fake_msvcrt.locking = fail_on_unlock
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

        with pytest.raises(RuntimeError, match="unexpected"):
            with broker._project_file_lock():
                pass

    def test_lock_path_with_chinese_chars_works(
        self, monkeypatch, tmp_path,
    ):
        """T13：spec §6.1 — lock_path 父目录路径含中文字符 → open + locking + unlock
        全程无 UnicodeError；Windows msvcrt 对 unicode 路径的支持回归。"""
        chinese_dir = tmp_path / "工作" / "项目"
        chinese_dir.mkdir(parents=True, exist_ok=True)

        # mock cad_paths.PROJECT_ROOT 指向中文目录
        import cad_paths
        monkeypatch.setattr(cad_paths, "PROJECT_ROOT", str(chinese_dir))

        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=0)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

        with broker._project_file_lock():
            pass  # 不应抛 UnicodeError

        # 验证 lock 文件创建在中文目录
        lock_path = chinese_dir / ".cad-spec-gen" / broker.LOCK_FILE_NAME
        assert lock_path.exists(), f"lock 文件未创建于中文路径 {lock_path}"

    # ─── D6. 跨平台（2 测试）───

    def test_lock_noop_on_linux(self, monkeypatch, tmp_project_dir):
        """T14：spec §6.1 — sys.platform = "linux" → 静默 yield + 无 msvcrt 调用 + 无 banner / 进度。"""
        monkeypatch.setattr(sys, "platform", "linux")

        # 设 msvcrt 为禁用 sentinel 让任何调用炸
        class FailMsvcrt:
            def __getattr__(self, name):
                raise AssertionError(f"msvcrt.{name} should NOT be accessed on Linux")

        monkeypatch.setitem(sys.modules, "msvcrt", FailMsvcrt())

        entered = []
        with broker._project_file_lock():
            entered.append(True)

        assert entered == [True]

    def test_lock_noop_on_darwin(self, monkeypatch, tmp_project_dir):
        """T15：spec §6.1 — sys.platform = "darwin" → 同 T14。"""
        monkeypatch.setattr(sys, "platform", "darwin")

        class FailMsvcrt:
            def __getattr__(self, name):
                raise AssertionError(f"msvcrt.{name} should NOT be accessed on macOS")

        monkeypatch.setitem(sys.modules, "msvcrt", FailMsvcrt())

        entered = []
        with broker._project_file_lock():
            entered.append(True)

        assert entered == [True]

    # ─── D7. 文案完整性（2 测试）───

    def test_lock_banner_contains_all_required_keywords(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T16：spec §6.1 — banner stderr 包含全部 6 实体关键词组：
        codegen / 占用 / Ctrl+C / 删除 / 配置 / BOM。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=2)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        for kw in ["codegen", "占用", "Ctrl+C", "删除", "配置", "BOM"]:
            assert kw in err, f"banner 缺关键词 '{kw}'；stderr={err}"

    def test_lock_banner_contains_lock_file_path_literal(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T17：spec §6.1 — banner 含 lock_path 字面字符串。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=2)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        err = capsys.readouterr().err
        # tmp_project_dir 路径片段应在 banner 中
        assert str(tmp_project_dir) in err or ".cad-spec-gen" in err, \
            f"banner 缺 lock_path；stderr={err}"

    # ─── D8. 输出 channel（1 测试）───

    def test_lock_banner_and_progress_only_on_stderr(
        self, monkeypatch, tmp_project_dir, capsys,
    ):
        """T18：spec §6.1 — capsys: stdout 为空 / stderr 含 banner + 进度。"""
        monkeypatch.setattr(sys, "platform", "win32")
        locking_calls = []
        fake_msvcrt = make_fake_msvcrt(locking_calls, contention_count=12)  # 6s 撞锁
        monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
        make_synced_time_mock(monkeypatch)

        with broker._project_file_lock():
            pass

        captured = capsys.readouterr()
        assert captured.out == "", f"stdout 应为空；实际 {captured.out!r}"
        assert "codegen" in captured.err
        assert "仍在等待" in captured.err


# ============================================================
# Phase 2 Task 8 — sw_config_broker M-2/M-4 cleanup（spec rev 6）
# spec: docs/superpowers/specs/2026-04-27-sw-config-broker-m2-m4-cleanup-design.md
#       §3.2 (rc 分流) + §3.3 (batch entry-level rc) + §7.2 + §7.5 + §7.7
# 22 RED 测试 — 待 plan Task 9-11 实现 broker rc 分流后转 GREEN。
# ============================================================


class TestRev5BrokerRcDispatch:
    """spec rev 6 §7.2 + §7.7 + §7.5：broker rc 分流 + invariant + negative 矩阵。

    13 主分流测试 + 3 invariant 直测（I4/I5/I10）+ 6 negative 组合。

    全部测试默认 RED — 当前 broker (line 517-523) `if proc.returncode != 0:
    cache=[]; return []` 不区分 rc=2 vs rc=3 vs rc=4 vs 未知 rc；batch loop
    (line 615-628) 也未读 entry["exit_code"]。Plan Task 9-11 实施后转 GREEN。
    """

    # ─── class-internal autouse 隔离 ────────────────────────────────
    @pytest.fixture(autouse=True)
    def _opt_out_safety_valve(self, monkeypatch):
        """全局 conftest 默认 CAD_SW_BROKER_DISABLE=1 — 本 class 测试需 broker 真路径。"""
        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

    @pytest.fixture(autouse=True)
    def _reset_caches(self):
        """spec §7.2 末 conftest fixture 的 class-local 替代：清 L2 + _save_failure_warned。

        放 class-local 而非 conftest.py 是为避免扩 scope（仅本 class 22 测试需要）。
        Task 9 落 cache.py `_save_failure_warned` 后 setattr 才能生效；本 RED 阶段
        cache_mod 还没此 attr，setattr 仍 well-defined（直接挂模块 namespace）。
        """
        broker._CONFIG_LIST_CACHE.clear()
        # spec rev 4：cache.py 引入 _save_failure_warned 后此 reset 才有意义
        if hasattr(cache_mod, "_save_failure_warned"):
            cache_mod._save_failure_warned = False
        yield
        broker._CONFIG_LIST_CACHE.clear()
        if hasattr(cache_mod, "_save_failure_warned"):
            cache_mod._save_failure_warned = False

    @pytest.fixture
    def patch_cache_path(self, monkeypatch, tmp_path):
        """L1 cache 文件锚定 tmp_path 隔离每测；返 Path 对象供断言读 cache 内容。"""
        target = tmp_path / "sw_config_lists.json"
        monkeypatch.setattr(
            cache_mod, "get_config_lists_cache_path", lambda: target,
        )
        return target

    @pytest.fixture
    def fake_sw(self, monkeypatch):
        """detect_solidworks 返 stable info（version_year=24 / toolbox_dir='C:/SW'）。"""
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(
                installed=True, version_year=24, toolbox_dir="C:/SW",
            ),
        )

    # ─── helpers ────────────────────────────────────────────────────
    @staticmethod
    def _make_run_factory(rc, stdout="", stderr=""):
        """构造 fake subprocess.run：返计数 list + CompletedProcess（text=True）。"""
        import subprocess as _sp

        calls = []

        def _fake(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return _sp.CompletedProcess(
                args=cmd, returncode=rc, stdout=stdout, stderr=stderr,
            )

        return _fake, calls

    @staticmethod
    def _make_batch_run_factory(rc, batch_results, stderr=b""):
        """构造 fake subprocess.run for batch：bytes stdout per worker --batch 协议。"""
        calls = []

        def _fake(cmd, input=None, **kwargs):
            calls.append((cmd, input, kwargs))

            class FakeProc:
                returncode = rc
                stdout = json.dumps(batch_results).encode()
                stderr = b""

            return FakeProc()

        return _fake, calls

    # ─── A. 13 主分流测试（spec §7.2 L685-697） ────────────────────

    def test_list_configs_rc2_caches_empty_list_to_prevent_retry(self, monkeypatch):
        """rc=2 (TERMINAL) → 第 1 次返 [] + 写 L2；第 2 次同 sldprt L2 hit call_count==1。

        spec §3.2.2 Layer 3 rc=2 分支 + §7.7 invariant I2。
        """
        import subprocess as _sp
        fake_run, calls = self._make_run_factory(rc=2, stdout="", stderr="terminal")
        monkeypatch.setattr(_sp, "run", fake_run)

        r1 = broker._list_configs_via_com("X.sldprt")
        r2 = broker._list_configs_via_com("X.sldprt")

        assert r1 == []
        assert r2 == []
        assert len(calls) == 1, (
            f"rc=2 terminal 第 2 次必须 L2 hit 不重 spawn；实际 spawn {len(calls)} 次"
        )

    def test_list_configs_rc3_does_not_cache_for_retry(self, monkeypatch):
        """rc=3 (TRANSIENT) → 第 1 次返 [] 不 cache；第 2 次重 spawn call_count==2。

        spec §3.2.2 Layer 3 rc=3 分支 + §7.7 invariant I3。
        当前 broker 不分流，rc≠0 全 cache；本测试预期 RED 直到 plan Task 10。
        """
        import subprocess as _sp
        fake_run, calls = self._make_run_factory(rc=3, stdout="", stderr="transient")
        monkeypatch.setattr(_sp, "run", fake_run)

        r1 = broker._list_configs_via_com("Y.sldprt")
        r2 = broker._list_configs_via_com("Y.sldprt")

        assert r1 == []
        assert r2 == []
        assert len(calls) == 2, (
            f"rc=3 transient 必须不 cache 让第 2 次重 spawn；实际 spawn {len(calls)} 次"
        )

    def test_list_configs_legacy_rc4_treated_as_transient(self, monkeypatch):
        """rc=4 (LEGACY 旧 worker) → 当 transient 不 cache（升级期混跑兜底）。

        spec §3.2.2 Layer 3 + §3.1 Drift 1 修复（broker WORKER_EXIT_LEGACY=4）。
        """
        import subprocess as _sp
        fake_run, calls = self._make_run_factory(rc=4, stdout="", stderr="legacy")
        monkeypatch.setattr(_sp, "run", fake_run)

        r1 = broker._list_configs_via_com("L4.sldprt")
        r2 = broker._list_configs_via_com("L4.sldprt")

        assert r1 == []
        assert r2 == []
        assert len(calls) == 2, (
            f"rc=4 legacy 必须当 transient 不 cache；实际 spawn {len(calls)} 次"
        )

    def test_list_configs_timeout_treated_as_transient_no_cache(self, monkeypatch):
        """TimeoutExpired → 不 cache；第 2 次同 sldprt 重 spawn。

        spec §3.2.2 Layer 3 TimeoutExpired 分支 — rev 6 砍 transient cache 后改不 cache。
        当前 broker line 514 `_CONFIG_LIST_CACHE[abs_path] = []` cache，故 RED。
        """
        import subprocess as _sp

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            raise _sp.TimeoutExpired(cmd=cmd, timeout=30)

        monkeypatch.setattr(_sp, "run", fake_run)

        r1 = broker._list_configs_via_com("T.sldprt")
        r2 = broker._list_configs_via_com("T.sldprt")

        assert r1 == []
        assert r2 == []
        assert len(calls) == 2, (
            f"TimeoutExpired 必须不 cache 让重试；实际 spawn {len(calls)} 次"
        )

    def test_list_configs_oserror_treated_as_transient_no_cache(self, monkeypatch):
        """OSError → 不 cache + 不抛 + 第 2 次重 spawn。

        spec §3.2.2 Layer 3 OSError 分支（fork 失败 / FileNotFoundError on python.exe 等）。
        当前 broker 未 catch OSError 会上抛，故 RED：第 1 次直接 raise。
        """
        import subprocess as _sp

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            raise OSError("[Errno 8] Exec format error")

        monkeypatch.setattr(_sp, "run", fake_run)

        r1 = broker._list_configs_via_com("O.sldprt")
        r2 = broker._list_configs_via_com("O.sldprt")

        assert r1 == [], "OSError 必须被 catch 返 []，不抛"
        assert r2 == []
        assert len(calls) == 2, (
            f"OSError 必须不 cache 让重试；实际 spawn {len(calls)} 次"
        )

    def test_list_configs_rc0_with_invalid_json_stdout_treated_as_transient(self, monkeypatch):
        """rc=0 + stdout 非合法 JSON → 不 cache（rev 6：JSON 错也归 transient）。

        spec §3.2.2 Layer 3 rc=0 JSON parse 失败分支。
        当前 broker line 531 cache []，故 RED：第 2 次 L2 hit call_count==1。
        """
        import subprocess as _sp
        fake_run, calls = self._make_run_factory(rc=0, stdout="<<not_json>>", stderr="")
        monkeypatch.setattr(_sp, "run", fake_run)

        r1 = broker._list_configs_via_com("J.sldprt")
        r2 = broker._list_configs_via_com("J.sldprt")

        assert r1 == []
        assert r2 == []
        assert len(calls) == 2, (
            f"rc=0 + JSON 错必须不 cache；实际 spawn {len(calls)} 次"
        )

    def test_list_configs_unknown_rc_defaults_transient(self, monkeypatch):
        """rc=99（未知）→ 当 transient 不 cache；第 2 次重 spawn。

        spec §3.2.2 Layer 3 "其他 rc" 分支 — 保守归 transient。
        """
        import subprocess as _sp
        fake_run, calls = self._make_run_factory(rc=99, stdout="", stderr="weird")
        monkeypatch.setattr(_sp, "run", fake_run)

        r1 = broker._list_configs_via_com("U.sldprt")
        r2 = broker._list_configs_via_com("U.sldprt")

        assert r1 == []
        assert r2 == []
        assert len(calls) == 2, (
            f"rc=99 未知必须当 transient 不 cache；实际 spawn {len(calls)} 次"
        )

    def test_prewarm_batch_mixed_rc_writes_terminal_skips_transient(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """batch stdout 三 entry 混合 exit_code → 写 rc=0 + rc=2 项跳 rc=3 项。

        spec §3.3 batch 分流 + §7.2 表格。
        当前 broker 写所有 entries（无 rc 过滤），故 RED：rc=3 entry 也被写入。
        """
        p_ok = tmp_path / "ok.sldprt"; p_ok.write_bytes(b"a" * 100)
        p_term = tmp_path / "term.sldprt"; p_term.write_bytes(b"b" * 200)
        p_trans = tmp_path / "trans.sldprt"; p_trans.write_bytes(b"c" * 300)

        results = [
            {"path": str(p_ok), "configs": ["A1", "A2"], "exit_code": 0},
            {"path": str(p_term), "configs": [], "exit_code": 2},
            {"path": str(p_trans), "configs": [], "exit_code": 3},
        ]
        fake_run, _calls = self._make_batch_run_factory(rc=0, batch_results=results)
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p_ok), str(p_term), str(p_trans)])

        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        entries = cache["entries"]

        key_ok = str(p_ok.resolve())
        key_term = str(p_term.resolve())
        key_trans = str(p_trans.resolve())

        assert key_ok in entries, "rc=0 entry 必须写入"
        assert entries[key_ok]["configs"] == ["A1", "A2"]
        assert key_term in entries, "rc=2 terminal 必须写入（[] 标记防重试）"
        assert entries[key_term]["configs"] == []
        assert key_trans not in entries, (
            "rc=3 transient 必须跳过不写 entries（防 L1 污染）"
        )

    def test_prewarm_batch_legacy_no_exit_code_field_skipped_not_polluting_cache(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path, caplog,
    ):
        """batch entry 缺 exit_code → 当 invalidate signal 跳过 + caplog warning。

        spec §3.3 rev 3 C2 修复 — 旧 worker stdout 缺 exit_code 不可信。
        """
        import logging
        p1 = tmp_path / "legacy.sldprt"; p1.write_bytes(b"x" * 100)
        results = [{"path": str(p1), "configs": []}]  # 缺 exit_code
        fake_run, _calls = self._make_batch_run_factory(rc=0, batch_results=results)
        monkeypatch.setattr("subprocess.run", fake_run)

        with caplog.at_level(logging.WARNING):
            broker.prewarm_config_lists([str(p1)])

        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        assert str(p1.resolve()) not in cache["entries"], (
            "缺 exit_code 字段（旧 worker）必须跳过不写 entries"
        )
        assert any(
            "缺 exit_code 字段（旧 worker schema）" in r.message
            for r in caplog.records
        ), "必须 log warning 含 '缺 exit_code 字段（旧 worker schema）' 标记"

    def test_prewarm_batch_rc4_legacy_skipped_like_transient(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """batch entry exit_code=4 → 当 transient 跳过不写 entries（与单件一致）。

        spec §3.3 向后兼容三层 + §3.2 rc=4 单件路径对齐。
        """
        p1 = tmp_path / "legacy4.sldprt"; p1.write_bytes(b"x" * 100)
        results = [{"path": str(p1), "configs": [], "exit_code": 4}]
        fake_run, _calls = self._make_batch_run_factory(rc=0, batch_results=results)
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])

        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        assert str(p1.resolve()) not in cache["entries"], (
            "rc=4 legacy 必须跳过不写 entries（与单件 transient 路径一致）"
        )

    def test_prewarm_batch_unknown_rc_skipped_like_transient(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """batch entry exit_code=99 (未识别) → 跳过不写 entries (I10 一致性)。

        spec §3.3 + §7.7 invariant I10：未识别 rc 单件 vs batch 行为对齐。
        """
        p1 = tmp_path / "unknown.sldprt"; p1.write_bytes(b"x" * 100)
        results = [{"path": str(p1), "configs": [], "exit_code": 99}]
        fake_run, _calls = self._make_batch_run_factory(rc=0, batch_results=results)
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])

        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        assert str(p1.resolve()) not in cache["entries"], (
            "未识别 rc=99 必须跳过不写 entries"
        )

    def test_prewarm_batch_rc64_full_fallback(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """subprocess rc=64 (worker stdin JSON 错) → broker 整 batch 不写 entries。

        spec §3.3 + Edge 10：worker EXIT_USAGE 是外部错（broker 端 BUG）— prewarm 完整 fallback。
        I-2 修复：envelope 已落盘但 entries 为空。
        """
        p1 = tmp_path / "rc64.sldprt"; p1.write_bytes(b"x" * 100)

        def fake_run(cmd, **kwargs):
            class FakeProc:
                returncode = 64
                stdout = b""
                stderr = b"worker: stdin not JSON"

            return FakeProc()

        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])  # 不抛

        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        assert str(p1.resolve()) not in cache["entries"], (
            "rc=64 worker usage 错 → entries 不写"
        )

    def test_prewarm_save_failure_does_not_propagate_to_caller(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """mock cache_mod._save_config_lists_cache 抛 OSError → prewarm 不抛（M-2 自愈）。

        spec §7.7 invariant I1 + §7.2 rev 4 补 I1 测试。
        I1：prewarm 永远不抛（fire-and-forget 契约）。
        当前 broker prewarm except 只 catch (TimeoutExpired, OSError, JSONDecodeError)，
        但 _save 抛 OSError 在 try block 内末尾——会被 catch；envelope 升级时的 _save
        失败也已处理（line 572 except Exception）。本测试确保整体不抛。
        """
        p1 = tmp_path / "save_fail.sldprt"; p1.write_bytes(b"x" * 100)
        results = [{"path": str(p1), "configs": ["A"], "exit_code": 0}]
        fake_run, _calls = self._make_batch_run_factory(rc=0, batch_results=results)
        monkeypatch.setattr("subprocess.run", fake_run)

        save_call_count = {"n": 0}

        def failing_save(cache):
            save_call_count["n"] += 1
            raise OSError("[Errno 13] Permission denied")

        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", failing_save)

        # 不抛任何异常（fire-and-forget 契约）
        broker.prewarm_config_lists([str(p1)])

        # 必须真调过 _save（否则失败注入根本无意义）
        assert save_call_count["n"] >= 1, (
            f"_save_config_lists_cache 必须被调过；实际 {save_call_count['n']} 次"
        )

    # ─── B. 3 invariant 直测（spec §7.2 L698-700 + §7.7） ──────────

    def test_invariant_l1_cache_not_polluted_by_transient_after_save(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """I4 直测：mock prewarm batch 含 rc=3 entry → 跑完读 L1 文件断 key NOT in entries。

        spec §7.7 invariant I4：transient sldprt 永不污染持久化 L1 cache。
        """
        p_trans = tmp_path / "i4_trans.sldprt"; p_trans.write_bytes(b"z" * 100)
        results = [{"path": str(p_trans), "configs": [], "exit_code": 3}]
        fake_run, _calls = self._make_batch_run_factory(rc=0, batch_results=results)
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p_trans)])

        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        abs_path = str(p_trans.resolve())
        assert abs_path not in cache["entries"], (
            f"I4 invariant 违反：transient (rc=3) 不应写入 L1 entries；"
            f"实际 entries={list(cache['entries'].keys())}"
        )

    def test_invariant_l1_cache_terminal_marked_with_empty_configs(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """I5 直测：mock prewarm batch 含 rc=2 entry (worker 返 ['JUNK']) → broker 强制写 [].

        spec §7.7 invariant I5：terminal 用 [] 显式标记防重试。
        强化断言：worker 故意返 configs=['JUNK'] (不该信任的非空 list) →
        broker 必须按 §3.3 rc=2 分支 OVERRIDE 为 []。当前 broker 不区分 rc，
        会写 ['JUNK']，故 RED。
        """
        p_term = tmp_path / "i5_term.sldprt"; p_term.write_bytes(b"y" * 100)
        # ★ 故意：rc=2 但 configs 非空（worker 不该这样返但要防御）
        results = [{"path": str(p_term), "configs": ["JUNK"], "exit_code": 2}]
        fake_run, _calls = self._make_batch_run_factory(rc=0, batch_results=results)
        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p_term)])

        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        abs_path = str(p_term.resolve())
        assert abs_path in cache["entries"], "I5：terminal 必须写入（[] 标记）"
        assert cache["entries"][abs_path]["configs"] == [], (
            f"I5 invariant 违反：terminal (rc=2) 必须显式写 []；"
            f"实际 configs={cache['entries'][abs_path]['configs']}"
        )

    def test_invariant_unknown_rc_consistent_single_vs_batch(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """I10 直测：未识别 rc=99 在单件 + batch 两路径都不写 cache（行为一致）。

        spec §7.7 invariant I10：单件 vs batch 路径未知 rc 处理对齐。
        """
        # === Phase A：batch 路径（rc=99 entry）===
        p_b = tmp_path / "i10_batch.sldprt"; p_b.write_bytes(b"a" * 100)
        results = [{"path": str(p_b), "configs": [], "exit_code": 99}]
        fake_run_batch, _ = self._make_batch_run_factory(rc=0, batch_results=results)
        monkeypatch.setattr("subprocess.run", fake_run_batch)

        broker.prewarm_config_lists([str(p_b)])

        cache_after_batch = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        assert str(p_b.resolve()) not in cache_after_batch["entries"], (
            "I10：batch 路径 rc=99 必须不写 entries"
        )

        # === Phase B：单件路径（rc=99 spawn）===
        broker._CONFIG_LIST_CACHE.clear()
        fake_run_single, calls_single = self._make_run_factory(
            rc=99, stdout="", stderr="single_unknown",
        )
        monkeypatch.setattr("subprocess.run", fake_run_single)

        r1 = broker._list_configs_via_com("i10_single.sldprt")
        r2 = broker._list_configs_via_com("i10_single.sldprt")

        assert r1 == [] and r2 == []
        assert len(calls_single) == 2, (
            f"I10：单件路径 rc=99 必须不 cache 让重 spawn；"
            f"实际 spawn {len(calls_single)} 次"
        )

    # ─── C. 6 negative 组合（spec §7.2 L701-706 + §7.5 矩阵） ──────

    def test_negative_worker_rc2_with_existing_l1_success_entry_overrides_with_terminal(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """negative：预填 L1 success + mtime 不变 → _list_configs_via_com L1 hit return success。

        spec §7.5 矩阵：rc=2 worker 失败 × L1 has success entry → L1 hit 早 return（rc=2 不触发）。
        当前 broker 三层 cache L1 hit 路径已正确（§3.2.2 Layer 1）— 测试预期 GREEN
        作为 regression sentinel；若未来 L1 hit 短路被破，本测试抓到。
        """
        import subprocess as _sp
        p1 = tmp_path / "neg1.sldprt"; p1.write_bytes(b"x" * 100)
        st = p1.stat()
        cache_mod._save_config_lists_cache({
            "schema_version": 1,
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "generated_at": "2026-04-26T00:00:00+00:00",
            "entries": {
                str(p1.resolve()): {
                    "mtime": int(st.st_mtime),
                    "size": st.st_size,
                    "configs": ["L1_SUCCESS"],
                },
            },
        })

        # 守卫：subprocess 不该被调（L1 hit 早 return）
        spawn_calls = []

        def _guard_run(cmd, **kwargs):
            spawn_calls.append(cmd)
            # 即使被错调也返 rc=2 — 测断言会抓到差异
            return _sp.CompletedProcess(args=cmd, returncode=2, stdout="", stderr="")

        monkeypatch.setattr(_sp, "run", _guard_run)

        result = broker._list_configs_via_com(str(p1))

        assert result == ["L1_SUCCESS"], (
            f"L1 hit 必须早 return success（不触发 rc=2 路径）；实际 {result}"
        )
        assert spawn_calls == [], (
            f"L1 hit 必须 0 spawn；实际 {len(spawn_calls)} 次"
        )

    def test_negative_worker_rc0_with_save_failure_returns_configs_anyway(self, monkeypatch):
        """negative：rc=0 + _save 抛 OSError → 函数仍返 configs（save 不影响读）。

        spec §7.5 矩阵 + §7.7 invariant I1 派生：fallback 单件路径不写 L1
        （spec §3.1 issue 4），所以 mock _save 不该被调；但即使被调失败也不影响 return。
        """
        import subprocess as _sp
        fake_run, calls = self._make_run_factory(
            rc=0, stdout=json.dumps(["CFG_A", "CFG_B"]) + "\n", stderr="",
        )
        monkeypatch.setattr(_sp, "run", fake_run)

        save_calls = {"n": 0}

        def failing_save(_cache):
            save_calls["n"] += 1
            raise OSError("[Errno 13] Permission denied")

        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", failing_save)

        result = broker._list_configs_via_com("neg2.sldprt")

        assert result == ["CFG_A", "CFG_B"], (
            f"rc=0 必须返 worker 解析的 configs（save 失败不影响）；实际 {result}"
        )
        # spec §3.1 issue 4：fallback 路径**不写** L1，所以 _save 不应被调
        assert save_calls["n"] == 0, (
            f"spec §3.1 issue 4：fallback 单件不写 L1；_save 不该被调，实际 {save_calls['n']} 次"
        )

    def test_negative_worker_timeout_with_l1_envelope_invalidated(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """negative：L1 envelope sw_version 过期 + worker TimeoutExpired → 升级 envelope 但 entries 不写。

        spec §7.5 矩阵：TimeoutExpired × envelope invalidated → I-2 修复保证 envelope 落盘 +
        entries 不写（worker 失败）。
        """
        import subprocess as _sp
        p1 = tmp_path / "neg3.sldprt"; p1.write_bytes(b"x" * 100)
        st = p1.stat()
        # 预填 envelope=旧 sw_version
        cache_mod._save_config_lists_cache({
            "schema_version": 1,
            "sw_version": 23,  # 旧
            "toolbox_path": "C:/SW",
            "generated_at": "2025-01-01T00:00:00+00:00",
            "entries": {
                str(p1.resolve()): {
                    "mtime": int(st.st_mtime),
                    "size": st.st_size,
                    "configs": ["OLD_ENTRY"],
                },
            },
        })

        def fake_run(cmd, **kwargs):
            raise _sp.TimeoutExpired(cmd=cmd, timeout=180)

        monkeypatch.setattr(_sp, "run", fake_run)

        broker.prewarm_config_lists([str(p1)])  # 不抛

        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        # I-2 修复：envelope 升级立即落盘
        assert cache["sw_version"] == 24, (
            f"I-2：envelope sw_version 必须立即升至 24；实际 {cache['sw_version']}"
        )
        # entries 不写（worker 超时）
        assert str(p1.resolve()) not in cache["entries"], (
            "TimeoutExpired 必须不写 entries"
        )

    def test_negative_unknown_rc_with_existing_l2_terminal_does_not_respawn(
        self, monkeypatch,
    ):
        """negative：预填 L2=[] (rc=2 终态) → _list_configs_via_com L2 hit 不 spawn。

        spec §7.5 矩阵 + §3.2.2 Layer 2：L2 hit 早 return 不触发 rc 分流。
        """
        import subprocess as _sp
        # 预填 L2=[]（模拟之前 rc=2 终态写入）
        fake_path = "Z_l2_terminal.sldprt"
        from pathlib import Path as _P
        broker._CONFIG_LIST_CACHE[str(_P(fake_path).resolve())] = []

        spawn_calls = []

        def _guard_run(cmd, **kwargs):
            spawn_calls.append(cmd)
            return _sp.CompletedProcess(args=cmd, returncode=99, stdout="", stderr="")

        monkeypatch.setattr(_sp, "run", _guard_run)

        result = broker._list_configs_via_com(fake_path)

        assert result == [], f"L2 hit 必须返 []；实际 {result}"
        assert len(spawn_calls) == 0, (
            f"L2 hit 必须 0 spawn；实际 spawn {len(spawn_calls)} 次"
        )

    def test_negative_invalid_json_stdout_with_l1_partial_load(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """negative：rc=0 + 非 JSON stdout + L1 partial（其他 sldprt 已 cache）→
        broker 不 cache 当前 sldprt + 返 [] + L1 不破其他 entry。

        spec §7.5 矩阵：JSON 错 × L1 部分填充。
        """
        import subprocess as _sp
        p_other = tmp_path / "other.sldprt"; p_other.write_bytes(b"o" * 100)
        st_other = p_other.stat()
        cache_mod._save_config_lists_cache({
            "schema_version": 1,
            "sw_version": 24,
            "toolbox_path": "C:/SW",
            "generated_at": "2026-04-26T00:00:00+00:00",
            "entries": {
                str(p_other.resolve()): {
                    "mtime": int(st_other.st_mtime),
                    "size": st_other.st_size,
                    "configs": ["OTHER_CFG"],
                },
            },
        })

        # 当前 sldprt：worker 返 rc=0 + 非 JSON
        fake_run, calls = self._make_run_factory(
            rc=0, stdout="<<malformed>>", stderr="",
        )
        monkeypatch.setattr(_sp, "run", fake_run)

        result = broker._list_configs_via_com("J_partial.sldprt")
        assert result == [], "JSON 错必须返 []"

        # L1 文件未被破（other 仍可读）
        cache = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        assert str(p_other.resolve()) in cache["entries"], "L1 其他 entry 不应丢"
        assert cache["entries"][str(p_other.resolve())]["configs"] == ["OTHER_CFG"]

        # 第 2 次：必须重 spawn（rev 6 transient 不 cache JSON 错）
        result2 = broker._list_configs_via_com("J_partial.sldprt")
        assert result2 == []
        assert len(calls) == 2, (
            f"JSON 错必须不 cache 让重 spawn；实际 {len(calls)} 次"
        )

    def test_negative_concurrent_l1_load_save_atomicity(
        self, patch_cache_path, fake_sw, monkeypatch, tmp_path,
    ):
        """negative：先成功 prewarm 写 L1 → 后续 _save 抛 PermissionError →
        _load 仍读到 partial 写之前的合法内容（os.replace 原子性）。

        spec §7.5 矩阵 + §11 known limitation：last-writer-wins 但 partial write 不允许。
        """
        import subprocess as _sp
        p1 = tmp_path / "atom1.sldprt"; p1.write_bytes(b"x" * 100)
        p2 = tmp_path / "atom2.sldprt"; p2.write_bytes(b"y" * 200)

        # === Phase A：成功 prewarm 写 L1 含 p1 ===
        results_a = [{"path": str(p1), "configs": ["A_CFG"], "exit_code": 0}]
        fake_run_a, _ = self._make_batch_run_factory(rc=0, batch_results=results_a)
        monkeypatch.setattr(_sp, "run", fake_run_a)

        broker.prewarm_config_lists([str(p1)])
        cache_phase_a = json.loads(patch_cache_path.read_text(encoding="utf-8"))
        assert str(p1.resolve()) in cache_phase_a["entries"], "Phase A 写 p1 必须成功"

        # === Phase B：mock _save 抛 PermissionError → 后续写 p2 失败 ===
        # 但 phase A 写的 p1 不应被破坏（os.replace 原子性 + .tmp 写失败前不 replace）
        results_b = [{"path": str(p2), "configs": ["B_CFG"], "exit_code": 0}]
        fake_run_b, _ = self._make_batch_run_factory(rc=0, batch_results=results_b)
        monkeypatch.setattr(_sp, "run", fake_run_b)

        original_save = cache_mod._save_config_lists_cache

        def failing_save(_cache):
            raise PermissionError("[Errno 13] Permission denied")

        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", failing_save)

        broker.prewarm_config_lists([str(p2)])  # 不抛（M-2 自愈）

        # 恢复原 _save
        monkeypatch.setattr(cache_mod, "_save_config_lists_cache", original_save)

        # === Phase C：_load 仍读到 phase A 写的内容 ===
        cache_phase_c = cache_mod._load_config_lists_cache()
        assert str(p1.resolve()) in cache_phase_c["entries"], (
            "os.replace 原子性：phase B 写失败不应破坏 phase A 已写 p1 entry"
        )
        assert cache_phase_c["entries"][str(p1.resolve())]["configs"] == ["A_CFG"]


class TestM8ContractGuard:
    """M-8 caller assert 契约守护（spec §4.6 / §7.2 invariant 1 + 3）。

    _validate_cached_decision 契约：valid=False ⇒ invalid_reason 非 None。
    caller `_resolve_config_for_part_unlocked` 失效路径用 `assert invalid_reason is not None`
    锁定不变量。本测试套守护 4 个角度（T13-T16）。
    """

    def test_assertion_holds_under_broken_validate_contract(
        self, monkeypatch, tmp_project_dir
    ):
        """T13 (spec §4.6): mock _validate_cached_decision 返回 (False, None)
        契约破裂时 _resolve_config_for_part_unlocked 必抛 AssertionError，
        而非 silent 调 _move_decision_to_history(reason=None) 写脏 history。

        RED 信号路径（缺 assert 时）：mock _move_decision_to_history 后 fall-through
        到规则匹配 → 无匹配 → 抛 NeedsUserDecision；pytest.raises(AssertionError) 因
        wrong exception type fail。GREEN（Task 2 加 assert）：assert 在
        _move_decision_to_history 调用前抢先抛 AssertionError，pytest 捕获 PASS。
        """
        from adapters.solidworks import sw_config_broker

        # 构造最小 envelope 含 cached decision（让 _resolve 走到 cached 分支）
        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "bom_dim_signature": "old_sig",
                    "sldprt_filename": "old.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }

        # mock _validate 契约破裂
        def _broken_validate(*args, **kwargs):
            return (False, None)  # ← 违反契约：valid=False 但 reason=None

        monkeypatch.setattr(
            sw_config_broker, "_validate_cached_decision", _broken_validate
        )
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda _: ["ConfigA", "ConfigB"]
        )
        # 额外 mock _move_decision_to_history 隔离 assert path：
        # main 上 _move 头部仍有 INVALIDATION_REASONS 校验，传 None 会先抛 ValueError
        # 干扰 RED 信号；mock 让 assert 成为唯一可能的早期抛点。
        monkeypatch.setattr(
            sw_config_broker, "_move_decision_to_history", lambda *a, **kw: None
        )

        with pytest.raises(AssertionError):
            sw_config_broker._resolve_config_for_part_unlocked(
                bom_row={"part_no": "TEST-001"},
                sldprt_path="C:/fake/test.sldprt",
                subsystem="test_sub",
            )

    def test_assertion_error_message_includes_contract_reference(
        self, monkeypatch, tmp_project_dir
    ):
        """T14 (spec §4.6): AssertionError message 包含 '_validate_cached_decision'
        引用，让 reviewer 失败时直接定位 spec §2.3 注释。

        RED 信号同 T13。
        """
        from adapters.solidworks import sw_config_broker

        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "bom_dim_signature": "old_sig",
                    "sldprt_filename": "old.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }
        monkeypatch.setattr(
            sw_config_broker,
            "_validate_cached_decision",
            lambda *a, **kw: (False, None),
        )
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda _: ["ConfigA"]
        )
        # 额外 mock _move_decision_to_history 隔离 assert path：
        # main 上 _move 头部仍有 INVALIDATION_REASONS 校验，传 None 会先抛 ValueError
        # 干扰 RED 信号；mock 让 assert 成为唯一可能的早期抛点。
        monkeypatch.setattr(
            sw_config_broker, "_move_decision_to_history", lambda *a, **kw: None
        )

        with pytest.raises(AssertionError) as exc_info:
            sw_config_broker._resolve_config_for_part_unlocked(
                bom_row={"part_no": "TEST-001"},
                sldprt_path="C:/fake/test.sldprt",
                subsystem="test_sub",
            )
        # message 应引用契约（spec §2.3 注释 "_validate_cached_decision 契约"）
        assert "_validate_cached_decision" in str(exc_info.value)

    @pytest.mark.parametrize(
        "invalid_reason,bom_sig_changes,sldprt_filename_changes,available_configs",
        [
            ("bom_dim_signature_changed", True, False, ["ConfigA"]),
            ("sldprt_filename_changed", False, True, ["ConfigA"]),
            ("config_name_not_in_available_configs", False, False, ["ConfigB"]),
        ],
        ids=["bom_changed", "filename_changed", "config_renamed"],
    )
    def test_cached_invalid_with_each_reason_triggers_history(
        self,
        monkeypatch,
        tmp_project_dir,
        invalid_reason,
        bom_sig_changes,
        sldprt_filename_changes,
        available_configs,
    ):
        """T15 (spec §4.6): cached decision 在 3 种失效场景下都正确 append history。
        端到端测试，不 mock _validate_cached_decision —— 用真实失效条件触发。
        """
        from adapters.solidworks import sw_config_broker

        # 构造 envelope cached
        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "bom_dim_signature": "current_sig" if not bom_sig_changes else "old_sig",
                    "sldprt_filename": "current.sldprt" if not sldprt_filename_changes else "old.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda _: available_configs
        )
        # _save_decisions_envelope mock 防真 IO（envelope 改动 in-place 后端到端 verify）
        monkeypatch.setattr(
            sw_config_broker, "_save_decisions_envelope", lambda env: None
        )

        # _build_bom_dim_signature mocked → 始终返回 "current_sig"；
        # bom_dim_signature 失效场景通过 envelope cached.bom_dim_signature == "old_sig"
        # 触发，与 bom_row 字段无关
        bom_row = {"part_no": "TEST-001"}
        monkeypatch.setattr(
            sw_config_broker, "_build_bom_dim_signature", lambda _: "current_sig"
        )

        try:
            sw_config_broker._resolve_config_for_part_unlocked(
                bom_row=bom_row,
                sldprt_path="C:/fake/current.sldprt",
                subsystem="test_sub",
            )
        except sw_config_broker.NeedsUserDecision:
            pass  # 失效 fall through 到规则匹配，可能 raise NeedsUserDecision

        # 验证 history 含失效条目，reason 等于参数化值
        assert "decisions_history" in envelope
        assert len(envelope["decisions_history"]) == 1
        assert envelope["decisions_history"][0]["invalidation_reason"] == invalid_reason
        # 验证原 entry 已被 pop
        assert "TEST-001" not in envelope["decisions_by_subsystem"].get("test_sub", {})

    def test_cached_valid_does_not_trigger_assert(
        self, monkeypatch, tmp_project_dir
    ):
        """T16 (spec §4.6): 防御性——valid=True 路径不触发 M-8 assert，
        正常返回 ConfigResolution(source='cached_decision')。
        """
        from adapters.solidworks import sw_config_broker

        envelope = sw_config_broker._empty_envelope()
        envelope["decisions_by_subsystem"] = {
            "test_sub": {
                "TEST-001": {
                    "decision": "use_config",
                    "config_name": "ConfigA",
                    "bom_dim_signature": "match_sig",
                    "sldprt_filename": "match.sldprt",
                    "decided_at": "2026-04-27T00:00:00Z",
                }
            }
        }
        monkeypatch.setattr(
            sw_config_broker, "_load_decisions_envelope", lambda: envelope
        )
        monkeypatch.setattr(
            sw_config_broker, "_list_configs_via_com", lambda _: ["ConfigA"]
        )
        monkeypatch.setattr(
            sw_config_broker, "_build_bom_dim_signature", lambda _: "match_sig"
        )

        result = sw_config_broker._resolve_config_for_part_unlocked(
            bom_row={"part_no": "TEST-001"},
            sldprt_path="C:/fake/match.sldprt",
            subsystem="test_sub",
        )

        assert result.source == "cached_decision"
        assert result.config_name == "ConfigA"
