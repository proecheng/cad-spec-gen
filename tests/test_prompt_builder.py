#!/usr/bin/env python3
"""Tests for enhance_prompt.py — the current prompt-building API.

Note: This file was originally test_prompt_builder.py targeting a standalone
`prompt_builder` module with `build_prompt()` / `build_material_lines()`.
That module was refactored into `enhance_prompt.py` with a unified template
(`build_enhance_prompt()` + `fill_prompt_template()`). Tests updated to match.
"""

import os
import sys
import unittest

# Import enhance_prompt via explicit path to bypass sys.path pollution from
# test_render_config.py which inserts cad/end_effector/ at sys.path[0] and
# shadows the canonical enhance_prompt.py with a stale copy.
import importlib.util
_EP_PATH = os.path.join(
    os.path.dirname(__file__), "..", "enhance_prompt.py")
_spec = importlib.util.spec_from_file_location("_ep_canonical", _EP_PATH)
enhance_prompt = importlib.util.module_from_spec(_spec)
# The module imports prompt_data_builder lazily inside _try_auto_enrich,
# so we need the project root on sys.path at import time for top-level imports.
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_spec.loader.exec_module(enhance_prompt)


class TestFillPromptTemplate(unittest.TestCase):
    """Test fill_prompt_template directly with inline template strings.

    Using inline templates keeps these tests independent of on-disk
    prompt_enhance.txt content drift.
    """

    TEMPLATE = (
        "Product: {product_name}\n"
        "View: {view_description}\n"
        "{view_type_note}\n"
        "Materials:\n{material_descriptions}\n"
        "Standards:\n{standard_parts_description}\n"
        "Negative:\n{negative_constraints}\n"
        "{consistency_rules}\n"
        "Env: {environment}\n"
    )

    def test_product_name_substituted(self):
        rc = {"prompt_vars": {"product_name": "test device"}}
        result = enhance_prompt.fill_prompt_template(
            self.TEMPLATE, "V1", rc)
        self.assertIn("test device", result)

    def test_material_descriptions_rendered(self):
        rc = {
            "prompt_vars": {
                "product_name": "robot arm",
                "material_descriptions": [
                    {"visual_cue": "body", "material_desc": "aluminum"},
                    {"visual_cue": "ring", "material_desc": "PEEK amber"},
                ],
            }
        }
        result = enhance_prompt.fill_prompt_template(
            self.TEMPLATE, "V1", rc)
        self.assertIn("body: aluminum", result)
        self.assertIn("ring: PEEK amber", result)

    def test_standard_parts_rendered(self):
        rc = {
            "prompt_vars": {"product_name": "arm"},
            "standard_parts": [
                {"visual_cue": "motor_cyl", "real_part": "Maxon ECX 22L"},
            ],
        }
        result = enhance_prompt.fill_prompt_template(
            self.TEMPLATE, "V1", rc)
        self.assertIn("Maxon ECX 22L", result)

    def test_missing_prompt_vars_uses_defaults(self):
        result = enhance_prompt.fill_prompt_template(
            self.TEMPLATE, "V1", {})
        self.assertIn("precision mechanical assembly", result)

    def test_exploded_view_type_note(self):
        rc = {
            "prompt_vars": {"product_name": "sensor"},
            "camera": {"V4": {"type": "exploded"}},
        }
        result = enhance_prompt.fill_prompt_template(
            self.TEMPLATE, "V4", rc)
        self.assertIn("sensor", result)
        # _VIEW_TYPE_NOTES["exploded"] should appear
        self.assertTrue(
            "exploded" in result.lower() or "explode" in result.lower(),
            f"Expected exploded view note in: {result}")

    def test_section_view_cut_plane_filled(self):
        rc = {
            "prompt_vars": {"product_name": "housing"},
            "camera": {"V6": {"type": "section"}},
            "section": {"cut_plane": "XZ"},
        }
        result = enhance_prompt.fill_prompt_template(
            self.TEMPLATE, "V6", rc)
        # {cut_plane} placeholder in view_type_note should be replaced
        self.assertNotIn("{cut_plane}", result)

    def test_negative_constraints_rendered(self):
        rc = {
            "prompt_vars": {"product_name": "arm"},
            "negative_constraints": ["no glossy plastic", "no chrome"],
        }
        result = enhance_prompt.fill_prompt_template(
            self.TEMPLATE, "V1", rc)
        self.assertIn("no glossy plastic", result)
        self.assertIn("no chrome", result)

    def test_no_triple_blank_lines(self):
        rc = {"prompt_vars": {"product_name": "arm"}}
        result = enhance_prompt.fill_prompt_template(
            self.TEMPLATE, "V1", rc)
        self.assertNotIn("\n\n\n", result)


class TestLoadTemplate(unittest.TestCase):
    """Test load_template resolves the on-disk unified template."""

    def test_load_template_returns_string(self):
        tmpl = enhance_prompt.load_template()
        self.assertIsInstance(tmpl, str)
        self.assertTrue(len(tmpl) > 0)
        # Unified template must contain at least one placeholder
        self.assertIn("{product_name}", tmpl)


class TestBuildEnhancePrompt(unittest.TestCase):
    """Test build_enhance_prompt — the high-level entry point."""

    def test_build_enhance_prompt_basic(self):
        rc = {
            "prompt_vars": {
                "product_name": "end effector",
                "material_descriptions": [
                    {"visual_cue": "flange", "material_desc": "brushed aluminum"},
                ],
            }
        }
        # auto_enrich=False so the test doesn't depend on params.py
        result = enhance_prompt.build_enhance_prompt(
            "V1", rc, auto_enrich=False)
        self.assertIn("end effector", result)
        self.assertIn("flange: brushed aluminum", result)


if __name__ == "__main__":
    unittest.main()
