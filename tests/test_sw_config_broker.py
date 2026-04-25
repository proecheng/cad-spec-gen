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
        BOM 'M6' + available 'long-name-M6-extra' → L2 命中但 confidence < 0.95"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X|M6",
            available=["long-name-M6-extra"],
        )
        if result:
            # M6 归一化后 'm6'，len 2 → confidence = min(0.95, 0.7 + 2/100) = 0.72
            assert result[1] < 0.95

    def test_below_threshold_returns_none(self):
        """confidence < 0.7 → 返回 None，让 caller 走含糊路径。
        BOM token '2.4' 孤立小数，Task 4 正则修复后不被提取 → 自动返回 None"""
        from adapters.solidworks.sw_config_broker import _match_config_by_rule

        result = _match_config_by_rule(
            bom_dim_signature="X|2.4",  # '2.4' 孤立小数不被正则提取
            available=["abc"],
        )
        assert result is None

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
