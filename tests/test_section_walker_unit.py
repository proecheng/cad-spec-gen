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
from cad_spec_section_walker import _canonicalize_box_axes


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


class TestAxisCanonicalization:
    def test_default_gisbot_label_passes_through(self):
        raw = (60.0, 40.0, 290.0)
        result = _canonicalize_box_axes(raw, "宽×深×高")
        assert result == (("x", 60.0), ("y", 40.0), ("z", 290.0))

    def test_length_first_label_keeps_position_semantics(self):
        """长×宽×高: first dim is length (X), second is width (Y), third is height (Z)."""
        raw = (1200.0, 60.0, 290.0)
        result = _canonicalize_box_axes(raw, "长×宽×高")
        assert result == (("x", 1200.0), ("y", 60.0), ("z", 290.0))

    def test_english_wdh_equals_chinese_default(self):
        raw = (60.0, 40.0, 290.0)
        assert _canonicalize_box_axes(raw, "W×D×H") == \
               _canonicalize_box_axes(raw, "宽×深×高")

    def test_unrecognized_label_returns_none(self):
        """No silent defaulting on unknown labels — caller must handle None."""
        assert _canonicalize_box_axes((1, 2, 3), "X×Y×Z (random order)") is None

    def test_label_whitespace_insensitive(self):
        result = _canonicalize_box_axes((60.0, 40.0, 290.0), " 宽 × 深 × 高 ")
        assert result == (("x", 60.0), ("y", 40.0), ("z", 290.0))

    def test_axis_swap_reorders_correctly(self):
        """深×宽×高: first raw dim is depth→Y, second is width→X, third is height→Z."""
        raw = (40.0, 60.0, 290.0)  # depth=40, width=60, height=290
        result = _canonicalize_box_axes(raw, "深×宽×高")
        # Canonical order should have X=60 (width), Y=40 (depth), Z=290 (height)
        assert result == (("x", 60.0), ("y", 40.0), ("z", 290.0))
