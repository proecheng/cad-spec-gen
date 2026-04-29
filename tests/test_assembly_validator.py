"""Tests for assembly_validator.py."""
import os
import sys
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_aabb_distance_overlapping():
    """Overlapping AABBs should have distance 0."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)
    b = (5, 5, 5, 15, 15, 15)
    assert aabb_distance(a, b) == 0.0


def test_aabb_distance_separated():
    """Separated AABBs: d = sqrt(dx^2 + dy^2 + dz^2)."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)
    b = (20, 0, 0, 30, 10, 10)
    assert aabb_distance(a, b) == 10.0


def test_aabb_distance_diagonal():
    """Diagonal separation: d = sqrt(10^2 + 10^2 + 10^2)."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)
    b = (20, 20, 20, 30, 30, 30)
    expected = math.sqrt(10**2 + 10**2 + 10**2)
    assert abs(aabb_distance(a, b) - expected) < 0.01


def test_derive_disconnect_threshold_from_tolerances():
    """Threshold = 3 * RSS(tolerances) + 0.3mm ISO 2768-m margin."""
    from assembly_validator import derive_disconnect_threshold
    tolerances = [0.1, 0.1, 0.1, 0.1]
    threshold = derive_disconnect_threshold(tolerances, min_part_size=50.0)
    expected = 3.0 * math.sqrt(sum(t**2 for t in tolerances)) + 0.3
    assert abs(threshold - expected) < 0.01


def test_derive_disconnect_threshold_no_tolerances():
    """Without tolerance data: fallback to 5% of smallest part size."""
    from assembly_validator import derive_disconnect_threshold
    threshold = derive_disconnect_threshold([], min_part_size=40.0)
    assert abs(threshold - 2.0) < 0.01


def test_derive_compactness_threshold():
    """Compactness = sum(heights) * packing_factor."""
    from assembly_validator import derive_compactness_threshold
    heights = [25.0, 5.0, 68.0, 8.0]
    threshold = derive_compactness_threshold(heights)
    assert abs(threshold - 106.0 * 2.0) < 0.01


def test_f1_floating_ignores_declared_excluded_names():
    """Excluded visual leaves should not surface as floating warnings."""
    from assembly_validator import check_f1_floating

    bboxes = {
        "EE-002-01": (0, 0, 0, 10, 10, 10),
        "EE-002-02": (10, 0, 0, 20, 10, 10),
        "STD-EE-002-05": (100, 0, 0, 110, 10, 10),
    }

    issues = check_f1_floating(
        bboxes,
        threshold=0.1,
        ignored_names={"STD-EE-002-05"},
    )
    assert issues == []


def test_f3_compactness_uses_actual_height_when_envelope_missing():
    """F3 should not become over-strict when §6.4 lacks purchased-part envelopes."""
    from assembly_validator import check_f3_compactness

    bboxes = {
        "EE-001-01": (-45, -45, 0, 45, 45, 25),
        "STD-EE-001-05": (-11, -11, 73, 11, 11, 155),
    }
    envelopes = {
        "GIS-EE-001-01": {"dims": (90.0, 90.0, 25.0)},
    }

    issues = check_f3_compactness(bboxes, envelopes, ["GIS-EE-001"])
    assert issues == []


def test_f5_completeness_excludes_connectors_cables_and_excluded_assemblies():
    """Expected and actual counts should use the same render exclusion contract."""
    from assembly_validator import check_f5_completeness

    bom_parts = [
        {"part_no": "GIS-EE-001", "name_cn": "法兰总成",
         "is_assembly": True, "material": "", "make_buy": "总成"},
        {"part_no": "GIS-EE-001-01", "name_cn": "法兰本体",
         "is_assembly": False, "material": "铝合金", "make_buy": "自制"},
        {"part_no": "GIS-EE-001-02", "name_cn": "LEMO插头",
         "is_assembly": False, "material": "FGG.0B.307", "make_buy": "外购"},
        {"part_no": "GIS-EE-001-03", "name_cn": "Gore柔性同轴",
         "is_assembly": False, "material": "MicroTCA", "make_buy": "外购"},
        {"part_no": "GIS-EE-001-04", "name_cn": "定位销",
         "is_assembly": False, "material": "Φ3×6mm H7/g6", "make_buy": "外购"},
        {"part_no": "GIS-EE-006", "name_cn": "信号调理模块",
         "is_assembly": True, "material": "", "make_buy": "总成"},
        {"part_no": "GIS-EE-006-01", "name_cn": "壳体",
         "is_assembly": False, "material": "6063铝合金", "make_buy": "自制"},
    ]
    bboxes = {
        "EE-001-01": (0, 0, 0, 90, 90, 25),
        "STD-EE-001-02": (100, 0, 0, 110, 10, 10),
    }

    report = check_f5_completeness(
        bboxes,
        bom_parts,
        excluded_part_nos={"GIS-EE-001-02"},
        excluded_assembly_nos={"GIS-EE-006"},
    )
    assert report["expected"] == 1
    assert report["actual"] == 1
    assert report["missing"] == []
    assert report["ok"] is True
