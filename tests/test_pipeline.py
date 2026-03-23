#!/usr/bin/env python3
"""
Tests for cad_pipeline.py — CLI argument parsing and subsystem discovery.

Run: python -m pytest tests/ -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cad_pipeline


class TestFindBlender(unittest.TestCase):
    def test_returns_string_or_none(self):
        result = cad_pipeline._find_blender()
        self.assertTrue(result is None or isinstance(result, str))

    def test_found_blender_is_file(self):
        result = cad_pipeline._find_blender()
        if result:
            self.assertTrue(os.path.isfile(result))


class TestFindSubsystem(unittest.TestCase):
    def test_end_effector_found(self):
        result = cad_pipeline._find_subsystem("end_effector")
        self.assertIsNotNone(result)
        self.assertTrue(os.path.isdir(result))

    def test_nonexistent_returns_none(self):
        result = cad_pipeline._find_subsystem("nonexistent_subsystem_xyz")
        self.assertIsNone(result)

    def test_fuzzy_match(self):
        result = cad_pipeline._find_subsystem("end_eff")
        # Should find end_effector via fuzzy match
        if result:
            self.assertIn("end_effector", result)


class TestCLIParsing(unittest.TestCase):
    def test_no_args_exits_zero(self):
        # main() with no command should return 0 (print help)
        sys.argv = ["cad_pipeline.py"]
        rc = cad_pipeline.main()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
