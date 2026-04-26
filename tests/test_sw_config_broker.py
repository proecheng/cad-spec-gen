import json
import sys

import pytest


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

    def test_move_decision_to_history(self):
        from adapters.solidworks.sw_config_broker import _move_decision_to_history

        env = {
            "decisions_by_subsystem": {
                "end_effector": {
                    "GIS-EE-001-03": {
                        "bom_dim_signature": "X|Y",
                        "decision": "use_config",
                        "config_name": "80×2.4",
                        "decided_at": "2026-04-20T10:00:00+00:00",
                    }
                }
            },
            "decisions_history": [],
        }
        _move_decision_to_history(
            env, "end_effector", "GIS-EE-001-03", "config_name_not_in_available_configs"
        )

        # 原位删除
        assert "GIS-EE-001-03" not in env["decisions_by_subsystem"]["end_effector"]
        # history 增加
        assert len(env["decisions_history"]) == 1
        h = env["decisions_history"][0]
        assert h["subsystem"] == "end_effector"
        assert h["part_no"] == "GIS-EE-001-03"
        assert h["invalidation_reason"] == "config_name_not_in_available_configs"
        assert h["previous_decision"]["config_name"] == "80×2.4"
        assert "invalidated_at" in h

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
        """worker 失败 → 返回 [] + cache 标记（避免重试）。"""
        import subprocess

        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd, returncode=4, stdout="", stderr="COM crash"
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
        """subprocess.TimeoutExpired → 返回 []。"""
        import subprocess

        from adapters.solidworks import sw_config_broker

        sw_config_broker._CONFIG_LIST_CACHE.clear()

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=15)

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = sw_config_broker._list_configs_via_com("Z.sldprt")
        assert result == []


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
                    {"path": str(p1), "configs": ["A1", "A2"]},
                    {"path": str(p2), "configs": ["B1"]},
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
                    [{"path": str(p2), "configs": ["P2A"]}],
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
        """worker exit != 0 → cache 不写；prewarm 静默 return 不抛."""
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
        # cache 未写
        assert not patch_paths.exists()

    def test_prewarm_worker_timeout_does_not_write_cache(
        self, patch_paths, fake_sw, monkeypatch, tmp_path,
    ):
        """subprocess.TimeoutExpired → cache 不写；prewarm 静默 return."""
        import subprocess

        from adapters.solidworks import sw_config_broker as broker

        monkeypatch.delenv("CAD_SW_BROKER_DISABLE", raising=False)

        p1 = tmp_path / "p1.sldprt"
        p1.write_bytes(b"x" * 100)

        def fake_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="x", timeout=180)

        monkeypatch.setattr("subprocess.run", fake_run)

        broker.prewarm_config_lists([str(p1)])  # 不抛
        assert not patch_paths.exists()

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
                    [{"path": str(p1), "configs": ["NEW"]}],
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
