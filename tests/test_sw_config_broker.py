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
