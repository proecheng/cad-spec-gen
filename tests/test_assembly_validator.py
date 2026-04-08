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
