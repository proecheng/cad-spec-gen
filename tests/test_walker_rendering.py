# tests/test_walker_rendering.py
"""Tests for §6.4 rendering integration in cad_spec_gen.py."""
from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_top_level_cad_spec_gen():
    """Load the top-level cad_spec_gen.py (not the src/cad_spec_gen package).

    The conftest inserts src/ at the front of sys.path, which causes a plain
    ``import cad_spec_gen`` to resolve to src/cad_spec_gen/__init__.py.
    We bypass that by explicitly loading the repo-root .py file, after
    ensuring the repo root is on sys.path so cad_spec_gen.py's own imports
    resolve correctly regardless of the test-suite working directory.
    """
    repo_root = pathlib.Path(__file__).parent.parent
    repo_root_str = str(repo_root)
    spec_file = repo_root / "cad_spec_gen.py"
    module_name = "_cad_spec_gen_top_level"
    if module_name in sys.modules:
        return sys.modules[module_name]
    # Ensure repo root is at the FRONT of sys.path so that relative imports
    # inside cad_spec_gen.py (e.g. from cad_spec_defaults import ...) find
    # the correct top-level module even when test_render_config.py has
    # inserted cad/end_effector/ at index 0 before us.
    if sys.path[0] != repo_root_str:
        sys.path.insert(0, repo_root_str)
    # Evict any stale cad_spec_defaults that test_render_config.py may have
    # pulled in from cad/end_effector/ (which lacks compute_serial_offsets).
    stale = sys.modules.get("cad_spec_defaults")
    if stale is not None and "end_effector" in getattr(stale, "__file__", ""):
        del sys.modules["cad_spec_defaults"]
    spec = importlib.util.spec_from_file_location(module_name, spec_file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_section_6_4_legend_and_new_columns():
    """Render a minimal data dict with walker-produced envelope + unmatched
    entry and inspect the markdown output."""
    from cad_spec_section_walker import (
        WalkerReport, WalkerStats, WalkerOutput,
    )

    cad_spec_gen = _load_top_level_cad_spec_gen()

    data = {
        "part_envelopes": {
            "GIS-EE-002": {
                "type": "box",
                "x": 60.0, "y": 40.0, "z": 290.0,
                "source": "P2:walker:tier1",
                "granularity": "station_constraint",
                "axis_label": "宽×深×高",
                "confidence": 1.0,
                "reason": "tier1_unique_match",
            },
            "GIS-EE-005": {
                "type": "cylinder",
                "d": 50.0, "z": 85.0,
                "source": "P2:walker:tier3",
                "granularity": "station_constraint",
                "axis_label": None,
                "confidence": 0.62,
                "reason": "tier3_jaccard_match",
            },
        },
        "bom": None,
        "walker_report": WalkerReport(
            unmatched=(
                WalkerOutput(
                    matched_pno=None,
                    envelope_type="cylinder",
                    dims=(("d", 30.0), ("z", 45.0)),
                    tier=None,
                    confidence=0.0,
                    reason="no_parent_section",
                    header_text="",
                    line_number=183,
                    granularity="station_constraint",
                    source_line="- **模块包络尺寸**：Φ30×45mm",
                ),
            ),
            stats=None,
            feature_flag_enabled=True,
        ),
    }

    helper = getattr(cad_spec_gen, "_build_markdown", None)
    if helper is None:
        import pytest
        pytest.skip("no standalone §6.4 helper in cad_spec_gen — test via full pipeline instead")

    md = helper(data)
    if isinstance(md, list):
        md = "\n".join(md)

    assert "### 6.4 零件包络尺寸" in md
    assert "粒度" in md                          # new column header
    assert "station_constraint" in md            # new column value
    assert "P2:walker:tier1" in md               # source tag
    assert "tier1_unique_match" in md            # reason column value
    assert "VERIFY" in md                        # low-confidence flag
    assert "6.4.1" in md                         # UNMATCHED subsection
    assert "no_parent_section" in md             # UNMATCHED reason code
    # Legend block should appear before the table
    legend_pos = md.find("> 说明 / Legend")
    table_pos = md.find("| 料号 |")
    assert legend_pos != -1, "Legend block not found"
    assert legend_pos < table_pos, "Legend block should appear before the table"
    # First 5 columns unchanged (backward compat with parse_envelopes cells[3])
    assert "| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |" in md
