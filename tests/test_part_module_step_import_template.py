"""Regression tests for STEP import code emitted by part_module.py.j2."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import jinja2


_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_step_import_branch_normalizes_with_os_path_normpath(monkeypatch, tmp_path):
    """Rendered STEP import code must call the valid os.path.normpath API."""

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_REPO_ROOT / "templates")),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    source = env.get_template("part_module.py.j2").render(
        part_name_cn="测试 STEP 零件",
        part_no="TST-100",
        source_ref="test",
        material="test",
        func_name="p100",
        param_imports=[],
        envelope_w=10,
        envelope_d=10,
        envelope_h=10,
        weight="?",
        has_mounting_holes=False,
        has_dxf=False,
        geom_type="unknown",
        step_path="sw_parts/SLP-100.step",
        template_code=None,
    )

    fake_cadquery = types.ModuleType("cadquery")
    fake_cadquery.Workplane = object
    fake_cadquery.importers = types.SimpleNamespace(importStep=lambda path: path)
    monkeypatch.setitem(sys.modules, "cadquery", fake_cadquery)
    monkeypatch.setitem(sys.modules, "params", types.ModuleType("params"))

    module_path = tmp_path / "p100.py"
    namespace = {"__file__": str(module_path)}
    exec(compile(source, str(module_path), "exec"), namespace)

    expected = os.path.normpath(
        os.path.join(str(tmp_path), "sw_parts/SLP-100.step")
    )
    assert namespace["make_p100"]() == expected
