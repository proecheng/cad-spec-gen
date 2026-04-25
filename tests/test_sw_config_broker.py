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
