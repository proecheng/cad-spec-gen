"""Fixture-driven tests for the section walker.

Each fixture under tests/fixtures/section_walker/ pairs a small Markdown
document with an expected walker output, expressed inline in the test.
"""
from __future__ import annotations

from pathlib import Path

from cad_spec_section_walker import SectionWalker

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "section_walker"


def _load(name: str) -> list[str]:
    return FIXTURE_DIR.joinpath(name).read_text(encoding="utf-8").splitlines()


def _bom(assemblies):
    return {"assemblies": assemblies}


# Shared BOM for most fixtures (includes ALT entry for ambiguity fixture 06).
_GISBOT_BOM = _bom([
    {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
    {"part_no": "GIS-EE-003", "name": "工位2 AE检测模块"},
    {"part_no": "GIS-EE-002-ALT", "name": "工位1驱动模块"},  # for ambiguity fixture 06
])

# Unambiguous 2-entry BOM used by fixture 01 to guarantee Tier 1 for both stations.
_CLEAN_BOM = _bom([
    {"part_no": "GIS-EE-002", "name": "工位1涂抹模块"},
    {"part_no": "GIS-EE-003", "name": "工位2 AE检测模块"},
])


def test_01_clean_station():
    """Standard GISBOT station format: 2 stations, 2 envelopes → Tier 1 each."""
    outputs, stats = SectionWalker(_load("01_clean_station.md"), _CLEAN_BOM).extract_envelopes()
    assert stats.matched_count == 2
    assert [o.matched_pno for o in outputs] == ["GIS-EE-002", "GIS-EE-003"]
    assert all(o.tier == 1 for o in outputs)


def test_02_no_parenthetical():
    """Stations without (angle°) suffix still match correctly."""
    outputs, stats = SectionWalker(_load("02_no_parenthetical.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 2
    assert [o.matched_pno for o in outputs] == ["GIS-EE-002", "GIS-EE-003"]


def test_03_markdown_hashes():
    """### header instead of **bold** is recognised as a section."""
    outputs, stats = SectionWalker(_load("03_markdown_hashes.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 1
    assert outputs[0].matched_pno == "GIS-EE-002"


def test_04_nested_subsections():
    """Envelope under an unmatched H3 child walks up to the bold station header."""
    outputs, _ = SectionWalker(_load("04_nested_subsections.md"), _GISBOT_BOM).extract_envelopes()
    assert len(outputs) == 1
    assert outputs[0].matched_pno == "GIS-EE-002"  # walked up past unmatched 4.1.2


def test_05_no_bom_match():
    """Section header matches no BOM row → UNMATCHED, all_tiers_abstained."""
    outputs, stats = SectionWalker(_load("05_no_bom_match.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 0
    assert stats.unmatched_count == 1
    assert outputs[0].reason == "all_tiers_abstained"


def test_06_ambiguous_tokens():
    """Two BOM rows share 工位1; Tier 1 abstains. All tiers abstain → UNMATCHED."""
    outputs, stats = SectionWalker(_load("06_ambiguous_tokens.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.matched_count == 0
    assert stats.unmatched_count == 1
    assert outputs[0].reason in ("tier2_density_tie", "all_tiers_abstained")


def test_07_multiple_envelopes_one_section():
    """Section has 2 envelope lines; both attribute to the same assembly."""
    outputs, stats = SectionWalker(
        _load("07_multiple_envelopes_one_section.md"), _GISBOT_BOM
    ).extract_envelopes()
    assert stats.matched_count == 2
    assert all(o.matched_pno == "GIS-EE-002" for o in outputs)


def test_08_envelope_before_any_section():
    """Envelope appears before any header → UNMATCHED with no_parent_section."""
    outputs, stats = SectionWalker(
        _load("08_envelope_before_any_section.md"), _GISBOT_BOM
    ).extract_envelopes()
    assert stats.unmatched_count == 1
    assert outputs[0].reason == "no_parent_section"


def test_09_cylinder_form():
    """Φd×h format → cylinder type, matched to GIS-EE-003."""
    outputs, _ = SectionWalker(_load("09_cylinder_form.md"), _GISBOT_BOM).extract_envelopes()
    assert len(outputs) == 1
    assert outputs[0].envelope_type == "cylinder"
    assert outputs[0].matched_pno == "GIS-EE-003"


def test_10_english_header():
    """English ## Station header doesn't match any Chinese BOM entry → UNMATCHED."""
    outputs, stats = SectionWalker(_load("10_english_header.md"), _GISBOT_BOM).extract_envelopes()
    assert stats.unmatched_count == 1
    # All tiers abstain: no CJK in header, no ASCII overlap with BOM names
    assert outputs[0].matched_pno is None
    assert outputs[0].reason == "all_tiers_abstained"
