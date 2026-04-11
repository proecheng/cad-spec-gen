"""Unit tests for cad_spec_section_walker."""
from __future__ import annotations

import pytest

from cad_spec_section_walker import (
    EnvelopeData,
    MatchResult,
    SectionFrame,
    WalkerOutput,
    WalkerReport,
    WalkerStats,
)


class TestDataclasses:
    def test_envelope_data_is_hashable(self):
        """Frozen + tuple dims means EnvelopeData can live in a set."""
        e1 = EnvelopeData(
            type="box",
            dims=(("x", 60.0), ("y", 40.0), ("z", 290.0)),
            axis_label="宽×深×高",
        )
        e2 = EnvelopeData(
            type="box",
            dims=(("x", 60.0), ("y", 40.0), ("z", 290.0)),
            axis_label="宽×深×高",
        )
        # Hashable + equal → same set member
        assert {e1, e2} == {e1}

    def test_envelope_data_dims_dict_returns_canonical_xyz(self):
        e = EnvelopeData(
            type="box",
            dims=(("x", 60.0), ("y", 40.0), ("z", 290.0)),
        )
        assert e.dims_dict() == {"x": 60.0, "y": 40.0, "z": 290.0}

    def test_match_result_carries_reason_code(self):
        m = MatchResult(pno="GIS-EE-002", tier=1, confidence=1.0,
                        reason="tier1_unique_match")
        assert m.reason == "tier1_unique_match"

    def test_walker_output_has_all_required_fields(self):
        o = WalkerOutput(
            matched_pno="GIS-EE-002",
            envelope_type="box",
            dims=(("x", 60.0), ("y", 40.0), ("z", 290.0)),
            tier=1,
            confidence=1.0,
            reason="tier1_unique_match",
            header_text="工位1涂抹模块",
            line_number=42,
            granularity="station_constraint",
            axis_label="宽×深×高",
            source_line="- **模块包络尺寸**：60×40×290mm (宽×深×高)",
        )
        assert o.matched_pno == "GIS-EE-002"
        assert o.granularity == "station_constraint"
        assert o.candidates == ()  # default empty tuple
