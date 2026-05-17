"""§11-N5 latent bug triage — characterization regression tests for v2.37.13a.

These tests verify behavior is preserved across dead-code deletion. Each test
captures current behavior of the affected function so the deletion doesn't
silently regress.
"""
from pathlib import Path


def test_bd_warehouse_metric_screw_drops_length_by_design():
    """§11-N5 Bug 1 characterization: M{d}×{length} → 'M{d}-{pitch}' (length intentionally dropped).

    Per catalog yaml line 211: 'Size format: M{d}-{pitch}' — csv_key for screws is
    (diameter, pitch) only. Length is parsed by regex as a format validator
    (rejecting bare 'M6' without ×length) but the numeric length value is not
    used in csv_key construction. This test pins that behavior.

    Note: `patterns` is read from `self._catalog['size_patterns']` (top-level),
    not from `class_info`; this test mocks `adapter._catalog` directly.
    """
    from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter

    adapter = BdWarehouseAdapter()
    # Mock catalog with metric_screw pattern (M{d}×{length} or M{d}x{length})
    adapter._catalog = {
        "size_patterns": {
            "metric_screw": r"M(\d+(?:\.\d+)?)\s*[×x*]\s*(\d+(?:\.\d+)?)",
        }
    }
    # Empty class_info — no bearing path, just fastener
    class_info: dict = {}

    # M6×20 — pitch_map[6] = 1.0 → csv_key "M6-1.0" (length 20 dropped)
    assert adapter._auto_extract_size_from_text("M6×20 内六角螺丝", class_info) == "M6-1.0"
    # M3×10 — pitch_map[3] = 0.5 → csv_key "M3-0.5"
    assert adapter._auto_extract_size_from_text("M3×10", class_info) == "M3-0.5"
    # M8×30 — pitch_map[8] = 1.25 → csv_key "M8-1.25"
    assert adapter._auto_extract_size_from_text("M8×30", class_info) == "M8-1.25"

    # Different length suffix (×50 vs ×20) → SAME csv_key (length dropped by design)
    assert adapter._auto_extract_size_from_text("M6×20", class_info) == \
           adapter._auto_extract_size_from_text("M6×50", class_info), \
           "csv_key must be length-invariant (by-design per catalog yaml line 211)"
