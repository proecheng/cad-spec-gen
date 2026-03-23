#!/usr/bin/env python3
"""Tests for prompt_builder.py."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "hybrid_render"))
import prompt_builder


class TestBuildPrompt(unittest.TestCase):

    def test_enhance_template(self):
        config = {
            "prompt_vars": {
                "product_name": "test device",
                "material_descriptions": [
                    {"visual_cue": "body", "material_desc": "aluminum"}
                ]
            }
        }
        result = prompt_builder.build_prompt(config, "enhance")
        self.assertIn("test device", result)
        self.assertIn("body: aluminum", result)
        self.assertIn("Keep ALL geometry", result)

    def test_exploded_template(self):
        config = {"prompt_vars": {"product_name": "robot arm"}}
        result = prompt_builder.build_prompt(config, "exploded")
        self.assertIn("robot arm", result)
        self.assertIn("exploded", result.lower())

    def test_ortho_template(self):
        config = {"prompt_vars": {"product_name": "sensor"}}
        result = prompt_builder.build_prompt(config, "ortho")
        self.assertIn("sensor", result)
        self.assertIn("orthographic", result.lower())

    def test_unknown_template_raises(self):
        with self.assertRaises(ValueError):
            prompt_builder.build_prompt({}, "nonexistent")

    def test_missing_prompt_vars_uses_defaults(self):
        result = prompt_builder.build_prompt({}, "enhance")
        self.assertIn("mechanical assembly", result)
        self.assertIn("No material descriptions", result)

    def test_material_lines_empty(self):
        result = prompt_builder.build_material_lines({})
        self.assertIn("No material descriptions", result)

    def test_material_lines_with_data(self):
        config = {
            "prompt_vars": {
                "material_descriptions": [
                    {"visual_cue": "flange", "material_desc": "brushed aluminum"},
                    {"visual_cue": "ring", "material_desc": "PEEK amber"},
                ]
            }
        }
        result = prompt_builder.build_material_lines(config)
        self.assertIn("flange: brushed aluminum", result)
        self.assertIn("ring: PEEK amber", result)


if __name__ == "__main__":
    unittest.main()
