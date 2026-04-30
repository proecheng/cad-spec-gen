"""Tests for geometry metadata emitted in generated std_*.py docstrings."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from codegen.gen_std_parts import _emit_module_source
from parts_resolver import ResolveResult


def _sample_part():
    return {
        "part_no": "GIS-EE-001-05",
        "name_cn": "测试标准件",
        "material": "铝合金",
        "make_buy": "外购",
    }


def test_step_import_docstring_includes_geometry_quality_metadata():
    result = ResolveResult(
        status="hit",
        kind="step_import",
        adapter="step_pool",
        step_path="std_parts/vendor/test.step",
        source_tag="STEP:std_parts/vendor/test.step",
        geometry_source="REAL_STEP",
        geometry_quality="A",
        validated=True,
        hash="sha256:abc123",
        path_kind="project_relative",
        requires_model_review=False,
    )

    source = _emit_module_source(
        _sample_part(),
        "std_ee_001_05",
        "motor",
        result,
    )

    assert "Source: STEP:std_parts/vendor/test.step\n" in source
    assert "Geometry source: REAL_STEP\n" in source
    assert "Geometry quality: A\n" in source
    assert "Validated: true\n" in source
    assert "Hash: sha256:abc123\n" in source
    assert "Path kind: project_relative\n" in source
    assert "Requires model review: false\n" in source


def test_legacy_jinja_primitive_header_keeps_note_without_geometry_metadata():
    result = ResolveResult(
        status="fallback",
        kind="codegen",
        adapter="jinja_primitive",
        body_code="    return cq.Workplane('XY').box(1, 1, 1)",
        source_tag="jinja_primitive:test",
        geometry_source="JINJA_PRIMITIVE",
        geometry_quality="D",
        requires_model_review=True,
        metadata={"dims": {"width": 1, "depth": 1, "height": 1}},
    )

    source = _emit_module_source(
        _sample_part(),
        "std_ee_001_05",
        "motor",
        result,
    )

    assert "Geometry source:" not in source
    assert "NOTE: This is a simplified representation for visualization only." in source
