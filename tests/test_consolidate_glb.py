"""Tests for codegen/consolidate_glb.py — the post-export GLB merger
that collapses CadQuery's per-face mesh split back into one mesh per
part_no.

These tests cover:

1. **Pure-Python tests** that exercise the prefix-grouping logic without
   requiring trimesh. They run in every CI environment.

2. **Round-trip tests** that exercise the full load/merge/save cycle.
   They are skipped when trimesh is not installed.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from codegen.consolidate_glb import (
    TRIMESH_AVAILABLE,
    consolidate_glb_file,
    group_meshes_by_prefix,
    _FACE_SUFFIX_RE,
)


# ─── Prefix grouping (pure Python, no trimesh) ──────────────────────────


class TestGroupingLogic:
    def test_face_suffix_regex_matches_only_at_end(self):
        # Stripped: trailing _NN
        assert _FACE_SUFFIX_RE.sub("", "EE-001-01_42") == "EE-001-01"
        assert _FACE_SUFFIX_RE.sub("", "EE-001-01_1") == "EE-001-01"
        # Unchanged: no suffix
        assert _FACE_SUFFIX_RE.sub("", "EE-001-01") == "EE-001-01"
        # Unchanged: number is in the middle, not the end
        assert _FACE_SUFFIX_RE.sub("", "EE-001-01_part") == "EE-001-01_part"
        # Unchanged: trailing letters
        assert _FACE_SUFFIX_RE.sub("", "EE-001-01_v2") == "EE-001-01_v2"

    def test_groups_by_prefix(self):
        """Sibling face nodes get gathered under their canonical name."""
        # Use a fake mesh stand-in (any object) — we never call mesh methods here
        fake = lambda: object()
        geometry = {
            "EE-001-01": fake(),
            "EE-001-01_1": fake(),
            "EE-001-01_2": fake(),
            "EE-001-01_99": fake(),
            "EE-002-01": fake(),
            "EE-002-01_1": fake(),
        }
        groups = group_meshes_by_prefix(geometry)
        assert set(groups.keys()) == {"EE-001-01", "EE-002-01"}
        assert len(groups["EE-001-01"]) == 4
        assert len(groups["EE-002-01"]) == 2

    def test_grouping_is_deterministic(self):
        """Sub-mesh order inside each group is sorted by name so the
        merge produces byte-identical output across runs."""
        fake = lambda: object()
        geometry = {
            "P_3": fake(),
            "P_1": fake(),
            "P_2": fake(),
            "P": fake(),
        }
        groups = group_meshes_by_prefix(geometry)
        names_in_order = [name for name, _ in groups["P"]]
        assert names_in_order == ["P", "P_1", "P_2", "P_3"]

    def test_singleton_components_pass_through(self):
        """A part with no per-face split (single mesh node) is its own
        group of one — no merge needed but the API stays uniform."""
        fake = lambda: object()
        geometry = {"single_part": fake()}
        groups = group_meshes_by_prefix(geometry)
        assert groups == {"single_part": [("single_part", geometry["single_part"])]}


# ─── Trimesh availability + graceful fallback ───────────────────────────


class TestTrimeshGating:
    def test_no_op_when_trimesh_missing(self, monkeypatch, tmp_path, capsys):
        """When trimesh isn't installed, consolidate_glb_file() must
        return False with a helpful warning instead of crashing."""
        from codegen import consolidate_glb
        monkeypatch.setattr(consolidate_glb, "TRIMESH_AVAILABLE", False)
        msgs = []
        result = consolidate_glb.consolidate_glb_file(
            str(tmp_path / "fake.glb"), logger=msgs.append
        )
        assert result is False
        assert any("trimesh not installed" in m for m in msgs)

    def test_missing_input_returns_false(self, tmp_path):
        msgs = []
        result = consolidate_glb_file(
            str(tmp_path / "nonexistent.glb"), logger=msgs.append
        )
        assert result is False
        # Either "trimesh not installed" or "input not found" — both are
        # graceful no-ops, never raises
        assert any("not installed" in m or "not found" in m for m in msgs)


# ─── Round-trip with real trimesh + CadQuery ────────────────────────────


@pytest.mark.skipif(not TRIMESH_AVAILABLE, reason="trimesh not installed")
class TestRoundTrip:
    """Build a tiny CadQuery assembly, export it to GLB, run the
    consolidator, and verify the result has one mesh per part."""

    @pytest.fixture
    def two_part_glb(self, tmp_path):
        import cadquery as cq

        # Two distinct parts. The first is a multi-face box (8 faces),
        # so without consolidation it produces ~8 GLB sibling components.
        # The second is a sphere (1 face) — it should pass through
        # unchanged as a single-component group.
        box = cq.Workplane("XY").box(20, 30, 40, centered=(True, True, False))
        sphere = cq.Workplane("XY").sphere(15)
        sphere = sphere.translate((50, 0, 0))

        assy = cq.Assembly()
        assy.add(box, name="part_box")
        assy.add(sphere, name="part_sphere")

        path = tmp_path / "two_parts.glb"
        assy.save(str(path), "GLTF")
        return path

    def test_round_trip_collapses_per_face_to_per_part(self, two_part_glb):
        import trimesh
        scene_before = trimesh.load(str(two_part_glb), force="scene")
        before_count = len(scene_before.geometry)
        # CadQuery emits one node per face → box has 6 face nodes
        # plus the parent (often duplicated) → at least 6 nodes
        assert before_count >= 6, (
            f"expected per-face split, got only {before_count} nodes"
        )

        msgs = []
        result = consolidate_glb_file(str(two_part_glb), logger=msgs.append)
        assert result is True

        scene_after = trimesh.load(str(two_part_glb), force="scene")
        after_count = len(scene_after.geometry)
        # After consolidation: exactly one node per part_no prefix
        assert after_count == 2, (
            f"expected 2 parts (box + sphere) after consolidation, "
            f"got {after_count}: {list(scene_after.geometry.keys())}"
        )
        assert "part_box" in scene_after.geometry
        assert "part_sphere" in scene_after.geometry

    def test_consolidated_part_bbox_is_correct(self, two_part_glb):
        """The whole point of consolidation: scene.geometry[name].bounds
        should equal the actual part bbox, not a single face's bbox."""
        consolidate_glb_file(str(two_part_glb))
        import trimesh
        scene = trimesh.load(str(two_part_glb), force="scene")

        # The box was 20×30×40 with bottom at z=0
        box_bounds = scene.geometry["part_box"].bounds
        box_span = box_bounds[1] - box_bounds[0]
        assert abs(box_span[0] - 20) < 0.5
        assert abs(box_span[1] - 30) < 0.5
        assert abs(box_span[2] - 40) < 0.5

        # The sphere has Φ30 (radius 15)
        sphere_bounds = scene.geometry["part_sphere"].bounds
        sphere_span = sphere_bounds[1] - sphere_bounds[0]
        assert abs(sphere_span[0] - 30) < 0.5
        assert abs(sphere_span[1] - 30) < 0.5
        assert abs(sphere_span[2] - 30) < 0.5

    def test_idempotent_second_run(self, two_part_glb):
        """Running the consolidator twice produces the same output as
        running it once — the second pass is a no-op."""
        msgs1 = []
        msgs2 = []
        consolidate_glb_file(str(two_part_glb), logger=msgs1.append)
        result2 = consolidate_glb_file(str(two_part_glb), logger=msgs2.append)
        # Second run should detect no per-face split and report no-op
        assert result2 is False
        assert any("already consolidated" in m for m in msgs2)
