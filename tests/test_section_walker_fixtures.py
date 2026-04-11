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


def test_11_non_gisbot_chassis_via_constructor_kwargs():
    """G12 validation: chassis subsystem uses DIFFERENT trigger term and
    station pattern, customized via constructor kwargs — NO code edit."""
    chassis_bom = _bom([
        {"part_no": "CHASSIS-DRV-001", "name": "驱动轮1 减速器总成"},
        {"part_no": "CHASSIS-DRV-002", "name": "驱动轮2 减速器总成"},
        {"part_no": "CHASSIS-DRV-003", "name": "驱动轮3 减速器总成"},
    ])
    walker = SectionWalker(
        _load("11_non_gisbot_chassis.md"),
        chassis_bom,
        trigger_terms=("外形尺寸",),
        station_patterns=[(r"驱动轮\s*(\d+)", "驱动轮")],
        axis_label_default="长×宽×高",
    )
    outputs, stats = walker.extract_envelopes()
    assert stats.matched_count == 3
    assert {o.matched_pno for o in outputs} == {
        "CHASSIS-DRV-001", "CHASSIS-DRV-002", "CHASSIS-DRV-003",
    }
    assert all(o.tier == 1 for o in outputs)


def test_12_english_bom_ascii_word_subsequence():
    """G12 + Tier 2 ASCII path: English BOM + English header → match via
    word subsequence (not CJK path)."""
    english_bom = _bom([
        {"part_no": "LIFT-001", "name": "Main Arm"},
        {"part_no": "LIFT-002", "name": "Cross Beam"},
    ])
    outputs, stats = SectionWalker(
        _load("12_english_bom.md"), english_bom,
    ).extract_envelopes()
    assert stats.matched_count == 1
    assert outputs[0].matched_pno == "LIFT-001"
    assert outputs[0].tier == 2


def test_13_axis_label_canonicalization():
    """Box with 長×宽×高 label → dims stored as canonical (X, Y, Z)
    where position 0 = length, 1 = width, 2 = height. The raw label
    is preserved in axis_label for audit."""
    bom = _bom([{"part_no": "GIS-EE-002", "name": "工位1长方形臂"}])
    outputs, _ = SectionWalker(_load("13_axis_label_rotation.md"), bom).extract_envelopes()
    assert len(outputs) == 1
    o = outputs[0]
    assert o.matched_pno == "GIS-EE-002"
    # dims[0] is X and carries the length value (1200)
    assert o.dims[0] == ("x", 1200.0)
    assert o.dims[1] == ("y", 60.0)
    assert o.dims[2] == ("z", 290.0)
    # Raw source label preserved
    assert o.axis_label == "长×宽×高"
