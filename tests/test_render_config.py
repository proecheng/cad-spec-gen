#!/usr/bin/env python3
"""
Tests for render_config.py — config loading, material resolution, camera helpers.

Run: python -m pytest tests/ -v
  or: python tests/test_render_config.py
"""

import json
import math
import os
import sys
import tempfile
import unittest

# Add the end_effector directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cad", "end_effector"))
import render_config as rcfg


class TestMaterialPresets(unittest.TestCase):
    """Test MATERIAL_PRESETS definitions."""

    def test_presets_not_empty(self):
        self.assertGreater(len(rcfg.MATERIAL_PRESETS), 0)

    def test_all_presets_have_required_fields(self):
        for name, params in rcfg.MATERIAL_PRESETS.items():
            self.assertIn("color", params, f"{name} missing color")
            self.assertIn("metallic", params, f"{name} missing metallic")
            self.assertIn("roughness", params, f"{name} missing roughness")

    def test_color_is_4_tuple(self):
        for name, params in rcfg.MATERIAL_PRESETS.items():
            c = params["color"]
            self.assertEqual(len(c), 4, f"{name} color should be 4-tuple")
            for v in c:
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)

    def test_metallic_range(self):
        for name, params in rcfg.MATERIAL_PRESETS.items():
            self.assertGreaterEqual(params["metallic"], 0.0)
            self.assertLessEqual(params["metallic"], 1.0)

    def test_roughness_range(self):
        for name, params in rcfg.MATERIAL_PRESETS.items():
            self.assertGreaterEqual(params["roughness"], 0.0)
            self.assertLessEqual(params["roughness"], 1.0)


class TestResolveMaterial(unittest.TestCase):
    """Test resolve_material()."""

    def test_preset_lookup(self):
        result = rcfg.resolve_material({"preset": "brushed_aluminum"})
        self.assertEqual(result["metallic"], 1.0)
        self.assertIn("color", result)

    def test_preset_with_overrides(self):
        result = rcfg.resolve_material({
            "preset": "brushed_aluminum",
            "overrides": {"roughness": 0.5},
        })
        self.assertEqual(result["roughness"], 0.5)
        # Original metallic preserved
        self.assertEqual(result["metallic"], 1.0)

    def test_unknown_preset_raises(self):
        with self.assertRaises(ValueError):
            rcfg.resolve_material({"preset": "nonexistent"})

    def test_direct_spec(self):
        result = rcfg.resolve_material({
            "color": [0.5, 0.5, 0.5, 1.0],
            "metallic": 0.8,
            "roughness": 0.3,
        })
        self.assertEqual(result["color"], (0.5, 0.5, 0.5, 1.0))

    def test_label_preserved(self):
        result = rcfg.resolve_material({
            "preset": "brushed_aluminum",
            "label": "My Label",
        })
        self.assertEqual(result["label"], "My Label")


class TestCameraToBlender(unittest.TestCase):
    """Test camera_to_blender()."""

    def test_cartesian_passthrough(self):
        preset = {"location": [100, 200, 300], "target": [0, 0, 0]}
        result = rcfg.camera_to_blender(preset)
        self.assertEqual(result["location"], (100, 200, 300))
        self.assertEqual(result["target"], (0, 0, 0))

    def test_spherical_conversion(self):
        preset = {
            "azimuth_deg": 0,
            "elevation_deg": 0,
            "distance_factor": 1.0,
        }
        result = rcfg.camera_to_blender(preset, bounding_r=100)
        loc = result["location"]
        # At az=0, el=0: x = 100, y = 0, z = target_z
        self.assertAlmostEqual(loc[0], 100.0, places=1)
        self.assertAlmostEqual(loc[1], 0.0 + result["target"][1], places=1)

    def test_spherical_90_deg(self):
        preset = {
            "azimuth_deg": 90,
            "elevation_deg": 0,
            "distance_factor": 1.0,
            "target": [0, 0, 0],
        }
        result = rcfg.camera_to_blender(preset, bounding_r=100)
        loc = result["location"]
        self.assertAlmostEqual(loc[0], 0.0, places=1)
        self.assertAlmostEqual(loc[1], 100.0, places=1)


class TestLightingScale(unittest.TestCase):
    """Test lighting_scale() and scaled_energies()."""

    def test_reference_scale_is_one(self):
        self.assertAlmostEqual(rcfg.lighting_scale(300.0), 1.0)

    def test_double_radius_quadruple_energy(self):
        self.assertAlmostEqual(rcfg.lighting_scale(600.0), 4.0)

    def test_scaled_energies_keys(self):
        e = rcfg.scaled_energies(300.0)
        self.assertIn("key", e)
        self.assertIn("fill", e)
        self.assertIn("rim", e)
        self.assertIn("bounce", e)


class TestLoadConfig(unittest.TestCase):
    """Test load_config() validation."""

    def _write_config(self, data):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, f)
        f.close()
        return f.name

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            rcfg.load_config("/nonexistent/path.json")

    def test_invalid_json_raises(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write("{ invalid json")
        f.close()
        try:
            with self.assertRaises(ValueError):
                rcfg.load_config(f.name)
        finally:
            os.unlink(f.name)

    def test_missing_required_key_raises(self):
        path = self._write_config({"version": 1, "subsystem": {"name": "x", "glb_file": "x.glb"}})
        try:
            with self.assertRaises(ValueError) as ctx:
                rcfg.load_config(path)
            self.assertIn("materials", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_empty_materials_raises(self):
        path = self._write_config({
            "version": 1,
            "subsystem": {"name": "x", "glb_file": "x.glb"},
            "materials": {},
            "camera": {"V1": {"name": "V1"}},
        })
        try:
            with self.assertRaises(ValueError):
                rcfg.load_config(path)
        finally:
            os.unlink(path)

    def test_unknown_preset_raises(self):
        path = self._write_config({
            "version": 1,
            "subsystem": {"name": "x", "glb_file": "x.glb"},
            "materials": {"part": {"preset": "nonexistent"}},
            "camera": {"V1": {"name": "V1"}},
        })
        try:
            with self.assertRaises(ValueError) as ctx:
                rcfg.load_config(path)
            self.assertIn("nonexistent", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_valid_config_loads(self):
        path = self._write_config({
            "version": 1,
            "subsystem": {"name": "test", "glb_file": "test.glb"},
            "materials": {"part": {"preset": "brushed_aluminum"}},
            "camera": {"V1": {"name": "V1_test"}},
        })
        try:
            config = rcfg.load_config(path)
            self.assertEqual(config["subsystem"]["name"], "test")
            self.assertIn("_resolved", config)
        finally:
            os.unlink(path)

    def test_wrong_version_raises(self):
        path = self._write_config({
            "version": 99,
            "subsystem": {"name": "x", "glb_file": "x.glb"},
            "materials": {"p": {"preset": "brushed_aluminum"}},
            "camera": {"V1": {"name": "V1"}},
        })
        try:
            with self.assertRaises(ValueError):
                rcfg.load_config(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
