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


from cad_spec_section_walker import _build_envelope_regexes


class TestEnvelopeRegex:
    def _box_re(self, terms=("模块包络尺寸",)):
        box, _ = _build_envelope_regexes(terms)
        return box

    def _cyl_re(self, terms=("模块包络尺寸",)):
        _, cyl = _build_envelope_regexes(terms)
        return cyl

    def test_box_plain(self):
        m = self._box_re().search("模块包络尺寸：60×40×290mm")
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("60", "40", "290")

    def test_box_bold_before_colon(self):
        m = self._box_re().search("- **模块包络尺寸**：60×40×290mm")
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("60", "40", "290")

    def test_box_bold_around_value(self):
        m = self._box_re().search("模块包络尺寸：**60×40×290mm**")
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("60", "40", "290")

    def test_box_with_axis_label_captured(self):
        m = self._box_re().search("模块包络尺寸：60×40×290mm (宽×深×高)")
        assert m is not None
        assert m.group(4) == "宽×深×高"

    def test_box_floats(self):
        m = self._box_re().search("模块包络尺寸：60.5×40.0×290.25mm")
        assert m is not None
        assert m.group(1) == "60.5"
        assert m.group(3) == "290.25"

    def test_cylinder_phi(self):
        m = self._cyl_re().search("模块包络尺寸：Φ45×120mm")
        assert m is not None
        assert (m.group(1), m.group(2)) == ("45", "120")

    def test_cylinder_alternate_symbols(self):
        for sym in ("φ", "Ø", "∅"):
            m = self._cyl_re().search(f"模块包络尺寸：{sym}30×45mm")
            assert m is not None, f"failed on symbol {sym}"

    def test_custom_trigger_term(self):
        """Non-GISBOT subsystems pass their own term via constructor kwarg."""
        box, _ = _build_envelope_regexes(("外形尺寸",))
        m = box.search("外形尺寸：1200×600×300mm")
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("1200", "600", "300")

    def test_multiple_trigger_terms(self):
        """Terms are joined with alternation."""
        box, _ = _build_envelope_regexes(("外形尺寸", "总体尺寸"))
        assert box.search("外形尺寸：60×40×290mm") is not None
        assert box.search("总体尺寸：60×40×290mm") is not None

    def test_wrong_trigger_term_does_not_match(self):
        box, _ = _build_envelope_regexes(("外形尺寸",))
        assert box.search("模块包络尺寸：60×40×290mm") is None


from cad_spec_section_walker import _normalize_header, _parse_section_header


class TestSectionHeader:
    def test_normalize_strips_bold(self):
        assert _normalize_header("**工位1**") == "工位1"

    def test_normalize_strips_markdown_hash(self):
        assert _normalize_header("### 4.1.2 各工位机械结构") == "4.1.2 各工位机械结构"

    def test_normalize_collapses_whitespace(self):
        assert _normalize_header("  工位1   涂抹  模块  ") == "工位1 涂抹 模块"

    def test_markdown_h1(self):
        assert _parse_section_header("# Top") == (1, "Top")

    def test_markdown_h3(self):
        assert _parse_section_header("### 4.1 Stations") == (3, "4.1 Stations")

    def test_markdown_h6(self):
        assert _parse_section_header("###### Deep") == (6, "Deep")

    def test_markdown_h7_not_a_header(self):
        """Seven hashes is not a valid Markdown header."""
        assert _parse_section_header("####### Too deep") is None

    def test_standalone_bold_is_level_100(self):
        result = _parse_section_header("**工位1(0°)：耦合剂涂抹模块**")
        assert result == (100, "工位1(0°)：耦合剂涂抹模块")

    def test_bullet_bold_is_not_a_header(self):
        """Property labels like `- **模块包络尺寸**：60×40×290mm` must NOT
        reset section state — if they did, the walker would lose the
        parent station on every envelope line."""
        assert _parse_section_header("- **模块包络尺寸**：60×40×290mm") is None

    def test_regular_line_is_not_a_header(self):
        assert _parse_section_header("This is a paragraph.") is None

    def test_empty_line_is_not_a_header(self):
        assert _parse_section_header("") is None

    def test_bold_with_trailing_content_is_not_a_header(self):
        """Only standalone-bold-on-own-line counts."""
        assert _parse_section_header("**工位1**: some text after") is None


from cad_spec_section_walker import _match_by_pattern, _DEFAULT_STATION_PATTERNS


def _bom(assemblies):
    return {"assemblies": assemblies}


class TestTier1Pattern:
    def test_unique_station_match(self):
        bom = _bom([
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
            {"part_no": "GIS-EE-003", "name": "工位2 AE检测模块"},
        ])
        result = _match_by_pattern("工位1(0°)：耦合剂涂抹模块", bom,
                                   _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.pno == "GIS-EE-002"
        assert result.tier == 1
        assert result.confidence == 1.0
        assert result.reason == "tier1_unique_match"

    def test_ambiguous_station_returns_none(self):
        """Two BOM rows share 工位1 → abstain entirely (return None),
        do NOT fall through to the next pattern. Regression test for
        round-2 programmer review finding: earlier draft used `continue`
        which silently matched a later pattern on the same header."""
        bom = _bom([
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
            {"part_no": "GIS-EE-004", "name": "工位1驱动模块"},
        ])
        result = _match_by_pattern("工位1 耦合剂涂抹", bom,
                                   _DEFAULT_STATION_PATTERNS)
        assert result is None

    def test_pattern_fires_but_no_bom_match_tries_next_pattern(self):
        """工位1 regex fires but BOM has no 工位 row → fall through to
        the next pattern (模块). This is the one legitimate `continue`
        case — distinct from ambiguity."""
        bom = _bom([
            {"part_no": "GIS-EE-010", "name": "模块3输电线"},
        ])
        result = _match_by_pattern("工位1 模块3", bom, _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.pno == "GIS-EE-010"

    def test_no_pattern_matches_header(self):
        bom = _bom([{"part_no": "X", "name": "something"}])
        assert _match_by_pattern("Plain English Title", bom,
                                 _DEFAULT_STATION_PATTERNS) is None

    def test_custom_station_patterns(self):
        """Chassis subsystem passes its own patterns via kwargs."""
        chassis = [(r"驱动轮\s*(\d+)", "驱动轮")]
        bom = _bom([{"part_no": "CHASSIS-DRV-003", "name": "驱动轮3 减速器总成"}])
        result = _match_by_pattern("驱动轮3 减速器", bom, chassis)
        assert result is not None
        assert result.pno == "CHASSIS-DRV-003"

    def test_level_pattern(self):
        bom = _bom([{"part_no": "L2", "name": "第2级支撑"}])
        assert _match_by_pattern("第2级主体", bom,
                                 _DEFAULT_STATION_PATTERNS).pno == "L2"
