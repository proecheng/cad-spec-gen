"""Regression tests for screw-lift drivetrain visibility.

The hydraulic-clamp lift platform uses a screw drive with GT2 belt, pulley,
coupling, and screw nut leaves. These are mechanical drivetrain parts, not
electrical cables/connectors or tiny fasteners, so they must flow through spec
constraints, codegen build tables, std part generation, assembly, and F5.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def _load_top_level_cad_spec_gen():
    spec = importlib.util.spec_from_file_location(
        "_cad_spec_gen_drivetrain_visibility",
        _ROOT / "cad_spec_gen.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_spec_constraints_do_not_exclude_mechanical_drivetrain() -> None:
    """Auto §9.2 exclude_stack is only for real cable/connector leaves."""
    cad_spec_gen = _load_top_level_cad_spec_gen()
    bom = {
        "assemblies": [
            {
                "part_no": "SLP-000",
                "name": "丝杠式升降平台",
                "make_buy": "总成",
                "parts": [
                    {"part_no": "SLP-500", "name": "同步带护罩",
                     "material": "PLA", "make_buy": "自制"},
                    {"part_no": "SLP-C01", "name": "T16 螺母 C7",
                     "material": "", "make_buy": "外购"},
                    {"part_no": "SLP-C04", "name": "GT2 20T 开式带轮 φ12",
                     "material": "", "make_buy": "外购"},
                    {"part_no": "SLP-C05", "name": "GT2-310-6mm 带",
                     "material": "", "make_buy": "外购"},
                    {"part_no": "SLP-C06", "name": "L070 联轴器",
                     "material": "", "make_buy": "外购"},
                    {"part_no": "SLP-E01", "name": "FFC 线束",
                     "material": "20芯×500mm", "make_buy": "外购"},
                ],
            }
        ]
    }

    constraints = cad_spec_gen.extract_assembly_constraints(
        fasteners=[],
        assembly={"layers": []},
        bom=bom,
        visual_ids=[],
        part_envelopes={},
    )

    excluded = {
        c["part_a"]
        for c in constraints
        if c["type"] == "exclude_stack"
    }
    assert "SLP-E01" in excluded
    assert excluded.isdisjoint(
        {"SLP-500", "SLP-C01", "SLP-C04", "SLP-C05", "SLP-C06"}
    )


def test_build_tables_include_transmission_std_parts() -> None:
    """build_all.py must export generated STEP files for drivetrain leaves."""
    from codegen.gen_build import generate_build_tables

    tables = generate_build_tables([
        {"part_no": "SLP-C04", "name_cn": "GT2 20T 开式带轮 φ12",
         "is_assembly": False, "material": "", "make_buy": "外购"},
        {"part_no": "SLP-C05", "name_cn": "GT2-310-6mm 带",
         "is_assembly": False, "material": "", "make_buy": "外购"},
        {"part_no": "SLP-C06", "name_cn": "L070 联轴器",
         "is_assembly": False, "material": "", "make_buy": "外购"},
    ])

    modules = {row["module"] for row in tables["std_step_builds"]}
    assert {"std_c04", "std_c05", "std_c06"}.issubset(modules)


def test_std_part_generation_includes_transmission_parts(tmp_path) -> None:
    """gen_std_parts must produce modules for GT2 and L070 drivetrain leaves."""
    from codegen import gen_std_parts

    spec = tmp_path / "CAD_SPEC.md"
    spec.write_text("# placeholder\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    original_parse_bom_tree = gen_std_parts.parse_bom_tree
    original_parse_envelopes = gen_std_parts.parse_envelopes
    try:
        gen_std_parts.parse_bom_tree = lambda _path: [
            {"part_no": "SLP-C04", "name_cn": "GT2 20T 开式带轮 φ12",
             "is_assembly": False, "material": "", "make_buy": "外购"},
            {"part_no": "SLP-C05", "name_cn": "GT2-310-6mm 带",
             "is_assembly": False, "material": "", "make_buy": "外购"},
            {"part_no": "SLP-C06", "name_cn": "L070 联轴器",
             "is_assembly": False, "material": "", "make_buy": "外购"},
        ]
        gen_std_parts.parse_envelopes = lambda _path: {}

        generated, _skipped, _resolver, _pending = (
            gen_std_parts.generate_std_part_files(
                spec_path=str(spec),
                output_dir=str(out_dir),
                mode="force",
            )
        )
    finally:
        gen_std_parts.parse_bom_tree = original_parse_bom_tree
        gen_std_parts.parse_envelopes = original_parse_envelopes

    produced = {Path(p).name for p in generated}
    assert {"std_c04.py", "std_c05.py", "std_c06.py"}.issubset(produced)
