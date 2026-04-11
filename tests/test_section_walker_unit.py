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


from cad_spec_section_walker import _match_by_subsequence


class TestTier2Subsequence:
    def test_cjk_subsequence_matches(self):
        """工位涂抹模块 is a character subsequence of 工位耦合剂涂抹模块."""
        bom = _bom([
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
            {"part_no": "GIS-EE-003", "name": "工位2 AE检测"},
        ])
        result = _match_by_subsequence("工位1(0°)：耦合剂涂抹模块", bom)
        assert result is not None
        assert result.pno == "GIS-EE-002"
        assert result.tier == 2
        assert result.confidence == 0.85
        assert result.reason == "tier2_unique_subsequence"

    def test_ascii_word_subsequence_matches(self):
        """'Main Arm' is a word subsequence of 'Main Arm Assembly'."""
        bom = _bom([
            {"part_no": "LIFT-001", "name": "Main Arm"},
            {"part_no": "LIFT-002", "name": "Cross Beam"},
        ])
        result = _match_by_subsequence("## Main Arm Assembly", bom)
        assert result is not None
        assert result.pno == "LIFT-001"

    def test_density_tie_abstains(self):
        """Two BOM rows with near-identical density → abstain."""
        bom = _bom([
            {"part_no": "A", "name": "工位1驱动"},
            {"part_no": "B", "name": "工位1涂抹"},
        ])
        # Header contains both subsequences with similar density.
        result = _match_by_subsequence("工位1 驱动 涂抹 共用", bom)
        assert result is None

    def test_no_cjk_no_ascii_returns_none(self):
        bom = _bom([{"part_no": "A", "name": "工位1模块"}])
        assert _match_by_subsequence("12345", bom) is None

    def test_empty_bom_returns_none(self):
        assert _match_by_subsequence("工位1", _bom([])) is None

    def test_out_of_order_chars_no_match(self):
        """Characters must appear IN ORDER as a subsequence."""
        bom = _bom([{"part_no": "A", "name": "涂抹工位"}])
        assert _match_by_subsequence("工位1涂抹", bom) is None

    def test_deterministic_tie_break_by_pno(self):
        """Equal density, different pnos → sort by pno alphabetically.
        Current behavior under tie: near-tie (gap < 0.1) abstains, so this
        test validates the sort key, not a match result."""
        bom = _bom([
            {"part_no": "B-BBB", "name": "工位模"},  # density 3/3
            {"part_no": "A-AAA", "name": "工位模"},  # density 3/3
        ])
        # Exact tie → abstain
        assert _match_by_subsequence("工位模", bom) is None


from cad_spec_section_walker import _match_by_jaccard, _tokenize


class TestTier3Jaccard:
    def test_tokenize_cjk_bigrams(self):
        tokens = _tokenize("工位耦合剂")
        assert "工位" in tokens
        assert "位耦" in tokens
        assert "耦合" in tokens

    def test_tokenize_ascii_words_lowercased(self):
        tokens = _tokenize("Main Arm Module")
        assert "main" in tokens
        assert "arm" in tokens
        assert "module" in tokens

    def test_tokenize_short_ascii_words_excluded(self):
        """Single-char ASCII words are too noisy for Jaccard."""
        tokens = _tokenize("a bc")
        assert "a" not in tokens
        assert "bc" in tokens

    def test_match_above_threshold(self):
        bom = _bom([{"part_no": "X", "name": "传感器模块组件"}])
        result = _match_by_jaccard("传感器模块组件设计", bom)
        assert result is not None
        assert result.pno == "X"
        assert result.tier == 3
        assert result.reason == "tier3_jaccard_match"

    def test_below_threshold_returns_none(self):
        bom = _bom([{"part_no": "X", "name": "unrelated stuff"}])
        assert _match_by_jaccard("完全不同的章节", bom) is None

    def test_exact_tie_abstains(self):
        bom = _bom([
            {"part_no": "A", "name": "工位模块"},
            {"part_no": "B", "name": "工位模块"},
        ])
        assert _match_by_jaccard("工位模块 附加", bom) is None

    def test_near_tie_abstains(self):
        """Two scores within AMBIGUITY_GAP → abstain."""
        bom = _bom([
            {"part_no": "A", "name": "大功率电机驱动"},
            {"part_no": "B", "name": "大功率电机控制"},
        ])
        assert _match_by_jaccard("大功率电机 通用", bom) is None

    def test_deterministic_tie_break_in_sort(self):
        """Non-tied candidates sorted by (-score, pno). Use pnos that would
        sort differently by dict iteration order vs alphabetical."""
        bom = _bom([
            {"part_no": "Z-highscore", "name": "aa bb cc dd ee ff"},
            {"part_no": "A-lower",    "name": "aa bb"},
        ])
        # Z has higher Jaccard, should win regardless of iteration order
        result = _match_by_jaccard("aa bb cc dd ee ff gg", bom)
        assert result is not None
        assert result.pno == "Z-highscore"

    def test_empty_tokens_returns_none(self):
        """Header with only single-char ASCII and single-char CJK runs."""
        bom = _bom([{"part_no": "X", "name": "工位1"}])
        assert _match_by_jaccard("a b c", bom) is None


from cad_spec_section_walker import _match_header, _match_context


class TestDispatchers:
    def test_match_header_tries_tiers_in_order(self):
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        # Unique station → Tier 1 fires
        result = _match_header("工位1涂抹", bom, _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.tier == 1

    def test_match_header_falls_through_to_tier2(self):
        """Tier 1 abstains (no 工位 in header); Tier 2 matches on CJK subsequence."""
        bom = _bom([{"part_no": "X", "name": "传感器组件"}])
        result = _match_header("传感器模块组件测试", bom,
                               _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.tier == 2

    def test_match_header_falls_through_to_tier3(self):
        """Tier 1+2 abstain; Tier 3 Jaccard matches.

        BOM name has words in reversed order so they cannot be a word
        subsequence of the header (Tier 2 abstains), but Jaccard overlap
        is high enough for Tier 3 to fire.
        """
        bom = _bom([{"part_no": "X", "name": "ee dd cc bb aa"}])
        result = _match_header("aa bb cc dd ee ff", bom,
                               _DEFAULT_STATION_PATTERNS)
        assert result is not None
        assert result.tier == 3

    def test_match_header_all_abstain_returns_none(self):
        bom = _bom([{"part_no": "X", "name": "completely unrelated"}])
        assert _match_header("完全不同", bom, _DEFAULT_STATION_PATTERNS) is None

    def test_match_context_fires_tier0_on_explicit_pno(self):
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        context = "earlier paragraphs... see GIS-EE-002 spec table above."
        result = _match_context(context, ("GIS-EE",), bom)
        assert result is not None
        assert result.tier == 0
        assert result.pno == "GIS-EE-002"
        assert result.reason == "tier0_context_window_match"

    def test_match_context_no_pno_returns_none(self):
        bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}])
        result = _match_context("unrelated context", ("GIS-EE",), bom)
        # May fall back to name-substring match (4-char 工位1涂 not in context)
        assert result is None
