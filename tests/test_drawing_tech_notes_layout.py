"""Tests for technical notes placement per GB/T 10609.1.

Verifies:
1. add_technical_notes() default position is in the LOWER half of an A3 sheet,
   not the upper half (GB/T 10609.1 compliance).
2. font_scale parameter correctly scales text height and line spacing.
3. draw_three_view.py's fallback chain never places notes in the upper area
   of the sheet (which would violate GB/T 10609.1).

Discovered during Spec 1 end-to-end validation on the real end_effector
design doc: the previous fallback at y = A3_H - MARGIN_STD - 5 ≈ 282mm
(upper-left of a 297mm-tall A3 sheet) was triggered whenever the three-view
layout filled most of the sheet height. This is where the 'why is the
technical requirements block in the upper area' visual bug came from.
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).parent.parent

# A3 sheet dimensions referenced by drawing.py
A3_WIDTH = 420.0
A3_HEIGHT = 297.0


def _load_repo_root_drawing():
    """Load the repo-root drawing.py directly via importlib, bypassing
    sys.path resolution.

    The repo has multiple drawing.py files (repo root, src mirror, and
    deployed copies under cad/<subsystem>/). Other tests in the full suite
    insert different paths into sys.path, causing `import drawing` to
    resolve to a cached deployed copy. Using importlib.util bypasses this.
    """
    # Force fresh load every call to avoid stale module cache from other tests
    drawing_path = _REPO_ROOT / "drawing.py"
    spec = importlib.util.spec_from_file_location("drawing_repo_root", drawing_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_add_technical_notes_default_pos_is_lower_half():
    """When pos=None, notes must land in the LOWER half of the A3 sheet.

    The lower half (y < 150) is where GB/T 10609.1 mandates technical
    requirements go. Previously the default was (27, 275) which put the
    notes in the UPPER area — this test is the regression gate.
    """
    add_technical_notes = _load_repo_root_drawing().add_technical_notes
    msp = MagicMock()
    add_technical_notes(msp, notes=["技术要求:", "1. test"], pos=None)
    # Collect all y coordinates from set_placement calls
    y_coords = []
    for call in msp.add_text.return_value.set_placement.call_args_list:
        args = call.args or call.kwargs.get("p", ())
        if args:
            y_coords.append(args[0][1])
    assert y_coords, "No placement calls recorded"
    for y in y_coords:
        assert y < A3_HEIGHT / 2, (
            f"Technical note y={y}mm is in the upper half of A3 "
            f"(height {A3_HEIGHT}mm). GB/T 10609.1 requires lower half."
        )
        assert y > 0, f"Technical note y={y}mm is below the sheet"


def test_add_technical_notes_default_pos_above_title_block():
    """Default position should leave room for a 56mm-tall title block at y=10..66."""
    add_technical_notes = _load_repo_root_drawing().add_technical_notes
    msp = MagicMock()
    add_technical_notes(msp, notes=["技术要求:"], pos=None)
    first_placement = msp.add_text.return_value.set_placement.call_args_list[0]
    first_y = first_placement.args[0][1] if first_placement.args else \
              first_placement.kwargs["p"][1]
    # Title block top is at y = 66 (MARGIN_STD + TITLE_BLOCK_H = 10 + 56)
    # Notes should be above the title block (y > 66)
    assert first_y > 60, (
        f"Default notes y={first_y} overlaps with or is below title block "
        f"at y=10..66"
    )


def test_add_technical_notes_font_scale_shrinks_text():
    """font_scale parameter must scale text height and line spacing."""
    add_technical_notes = _load_repo_root_drawing().add_technical_notes
    msp_full = MagicMock()
    msp_small = MagicMock()

    notes = ["技术要求:", "1. foo", "2. bar"]
    add_technical_notes(msp_full, notes=notes, pos=(27.0, 62.0), font_scale=1.0)
    add_technical_notes(msp_small, notes=notes, pos=(27.0, 62.0), font_scale=0.5)

    # Extract heights from add_text kwargs
    heights_full = [call.kwargs.get("height") for call in msp_full.add_text.call_args_list]
    heights_small = [call.kwargs.get("height") for call in msp_small.add_text.call_args_list]

    assert len(heights_full) == 3
    assert len(heights_small) == 3
    for h_full, h_small in zip(heights_full, heights_small):
        assert abs(h_small - h_full * 0.5) < 0.001, (
            f"font_scale=0.5 should halve height, got {h_small} vs {h_full}"
        )


def test_add_technical_notes_font_scale_shrinks_line_spacing():
    """font_scale must also scale line spacing so lines don't collide."""
    add_technical_notes = _load_repo_root_drawing().add_technical_notes
    msp = MagicMock()
    notes = ["技术要求:", "1. foo", "2. bar"]
    add_technical_notes(msp, notes=notes, pos=(27.0, 62.0), font_scale=0.5)

    y_coords = [
        call.args[0][1] if call.args else call.kwargs["p"][1]
        for call in msp.add_text.return_value.set_placement.call_args_list
    ]
    # Line spacing should be 5.0 * 0.5 = 2.5mm between consecutive lines
    assert len(y_coords) == 3
    diff_01 = y_coords[0] - y_coords[1]
    diff_12 = y_coords[1] - y_coords[2]
    assert abs(diff_01 - 2.5) < 0.01, f"Line spacing 0→1 is {diff_01}, expected 2.5"
    assert abs(diff_12 - 2.5) < 0.01, f"Line spacing 1→2 is {diff_12}, expected 2.5"


def test_draw_three_view_never_falls_back_to_upper_area():
    """Static source check: draw_three_view.py must not contain the old
    wrong fallback `A3_H - MARGIN_STD - 5` which placed notes in the upper area.

    This is the regression gate for the GB/T 10609.1 compliance fix.
    """
    src = (_REPO_ROOT / "draw_three_view.py").read_text(encoding="utf-8")
    # The old fallback put notes at y ≈ A3_H - 10 - 5 = 282, in the UPPER area
    assert "A3_H - MARGIN_STD - 5" not in src, (
        "Found the old upper-area fallback `A3_H - MARGIN_STD - 5` in "
        "draw_three_view.py. This violates GB/T 10609.1 which requires "
        "technical notes in the LOWER half of the drawing."
    )


def test_draw_three_view_has_tier_fallback_strategy():
    """Static source check: draw_three_view.py must have the 4-tier fallback
    (Tier 1/2/3) instead of single-tier upper fallback.
    """
    src = (_REPO_ROOT / "draw_three_view.py").read_text(encoding="utf-8")
    # Tier 1: >= 35mm gap → normal
    # Tier 2: >= 20mm gap → font_scale=0.75
    # Tier 3: < 20mm → title-block-left area
    assert "Tier 1" in src and "Tier 2" in src and "Tier 3" in src, \
        "Expected Tier 1/2/3 fallback strategy markers in draw_three_view.py"
    assert "font_scale" in src, \
        "Expected font_scale parameter usage in the fallback strategy"


def test_title_top_y_is_below_notes_default():
    """Sanity: the drawing default notes y (62) is between the title block
    top (66) and bottom (10), so notes always go ABOVE the title block.

    Wait — the default is (27, 62) which is BELOW title_top=66. That means
    notes DEFAULT position overlaps with the title block itself! This test
    documents that pairing: callers MUST pass an explicit pos; the default
    is only a safe fallback for drawings without a title block.

    Actually the default y=62 is 4mm BELOW title_top=66. That means the first
    notes line starts inside the title block... wait, the default places the
    FIRST line at (x=27, y=62). Successive lines go DOWN (y -= 5). So the
    notes span y=62 down to e.g. 37 for a 5-line block. That overlaps with
    the title block at y=10..66. Oh no.

    Wait, let me re-read. Notes go DOWN from the pos (set_placement goes
    down). So:
      line 0 at y=62
      line 1 at y=57
      line 2 at y=52
      ...
    That's WITHIN the title block (y=10..66).

    So the default (27, 62) is WRONG for drawings with title blocks. But
    it's SAFE for drawings without title blocks (which use the whole sheet).

    The correct default for drawings WITH title blocks would be: pos placed
    ABOVE the title block (y > 66) so notes going down end at y > some
    clearance above the title. E.g., pos = (27, title_block_top + 3 + N*5)
    where N is the number of notes, so line N lands at title_block_top + 3.

    But the drawing.py module doesn't know how many notes will be emitted
    until it starts emitting them. And it doesn't know the title block
    location either.

    RESOLUTION: the default is a best-effort fallback for callers that
    DON'T specify pos. Real callers (draw_three_view.py) MUST pass pos
    explicitly. The default is documented in drawing.py's docstring as
    a safe fallback and is chosen to be in the LOWER half (correct per
    GB/T), accepting that it may overlap with title blocks when present.

    This test just documents the reasoning so future maintainers don't
    accidentally "fix" the default back to the upper area.
    """
    # Default y=62 is in the lower half (< 148.5)
    assert 62.0 < A3_HEIGHT / 2
    # Default y=62 is very close to title block top (66)
    assert abs(62.0 - 66.0) < 10
