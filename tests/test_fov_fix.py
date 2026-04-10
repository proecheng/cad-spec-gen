# tests/test_fov_fix.py
"""Tests for the auto-frame FOV fix (Spec 1 Phase 1).

Verifies that the required_dist calculation uses min(fov_v, fov_h)
instead of vertical FOV only, producing correct framing for wide models.
"""
import math
import pathlib

import pytest


def compute_required_dist(sensor_w, lens, aspect, bs_radius, frame_fill=0.75):
    """Standalone implementation of the expected formula for test comparison.

    Args:
        sensor_w: Camera sensor width in mm (Blender default 36)
        lens: Camera focal length in mm
        aspect: render resolution_x / resolution_y
        bs_radius: Bounding sphere radius in scene units
        frame_fill: Fill fraction (default 0.75, unchanged by Spec 1)

    Returns:
        Required camera distance from bounding sphere center.
    """
    sensor_h = sensor_w / aspect
    fov_v = math.atan(sensor_h / (2.0 * lens))
    fov_h = math.atan(sensor_w / (2.0 * lens))
    fov_half = min(fov_v, fov_h)
    return bs_radius / math.sin(fov_half) / frame_fill


def test_wide_aspect_uses_vertical_fov():
    """For 16:9 landscape, vertical FOV is tighter → governs distance."""
    dist = compute_required_dist(sensor_w=36, lens=65, aspect=1920/1080,
                                 bs_radius=150)
    # sensor_h = 36 / 1.778 = 20.25
    # fov_v = atan(20.25 / 130) ≈ 0.1543 rad
    # fov_h = atan(36 / 130) ≈ 0.2706 rad
    # min is fov_v, so: 150 / sin(0.1543) / 0.75 ≈ 1302.8
    assert 1250 < dist < 1350, f"Expected ~1302, got {dist}"


def test_tall_aspect_uses_horizontal_fov():
    """For 9:16 portrait, horizontal FOV is tighter → governs distance."""
    dist = compute_required_dist(sensor_w=36, lens=65, aspect=1080/1920,
                                 bs_radius=150)
    # sensor_h = 36 / 0.5625 = 64
    # fov_v = atan(64 / 130) ≈ 0.4584 rad
    # fov_h = atan(36 / 130) ≈ 0.2706 rad
    # min is fov_h, so: 150 / sin(0.2706) / 0.75 ≈ 748.1
    assert 700 < dist < 800, f"Expected ~748, got {dist}"


def test_square_aspect_both_fovs_equal():
    """For 1:1, vertical == horizontal FOV, so both give the same distance."""
    dist = compute_required_dist(sensor_w=36, lens=65, aspect=1.0,
                                 bs_radius=150)
    # sensor_h = 36, fov_v == fov_h
    assert 700 < dist < 800, f"Expected ~748, got {dist}"


def test_render_3d_module_has_new_formula():
    """The promoted render_3d.py must contain the min() formula (Spec 1 fix)."""
    src = pathlib.Path(__file__).parent.parent / "src" / "cad_spec_gen" / "render_3d.py"
    assert src.exists(), f"Expected {src} to exist after Task 3"
    content = src.read_text(encoding="utf-8")
    assert "fov_v = math.atan(sensor_h" in content, \
        "render_3d.py is missing the new fov_v line"
    assert "fov_h = math.atan(sensor_w" in content, \
        "render_3d.py is missing the new fov_h line"
    assert "min(fov_v, fov_h)" in content, \
        "render_3d.py is missing the min(fov_v, fov_h) formula"


def test_render_3d_frame_fill_default_unchanged():
    """frame_fill default must remain 0.75 (3D designer review decision)."""
    src = pathlib.Path(__file__).parent.parent / "src" / "cad_spec_gen" / "render_3d.py"
    content = src.read_text(encoding="utf-8")
    # frame_fill default should still be 0.75, not 0.82
    assert "0.75" in content, "frame_fill literal 0.75 not found"
    # Explicitly verify 0.82 has NOT been introduced as frame_fill value
    assert 'frame_fill", 0.82' not in content and "frame_fill = 0.82" not in content, \
        "frame_fill was changed to 0.82 — Spec 1 keeps it at 0.75"
