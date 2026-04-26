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
