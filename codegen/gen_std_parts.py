#!/usr/bin/env python3
"""
Code Generator: Standard/Purchased Parts → Simplified CadQuery Geometry

Generates simplified CadQuery models for purchased (外购) BOM parts so they
appear in 3D renders. Motors → cylinders, springs → helical shapes, etc.
Only creates NEW files — never overwrites existing ones.

Usage:
    python codegen/gen_std_parts.py cad/end_effector/CAD_SPEC.md
    python codegen/gen_std_parts.py cad/end_effector/CAD_SPEC.md --output-dir cad/end_effector
"""

import argparse
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from bom_parser import classify_part
from cad_spec_defaults import lookup_std_part_dims
from codegen.gen_build import parse_bom_tree


# ─── Geometry generators per category ─────────────────────────────────────
# Each returns a string of CadQuery code (body of the make_ function)

def _gen_motor(dims: dict) -> str:
    d = dims.get("d", 22)
    l = dims.get("l", 50)
    sd = dims.get("shaft_d", 4)
    sl = dims.get("shaft_l", 12)
    return f"""    # Simplified motor: cylinder + shaft
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    # Output shaft
    body = body.faces(">Z").workplane().circle({sd/2}).extrude({sl})
    return body"""


def _gen_reducer(dims: dict) -> str:
    d = dims.get("d", 25)
    l = dims.get("l", 35)
    sd = dims.get("shaft_d", 6)
    sl = dims.get("shaft_l", 10)
    return f"""    # Simplified reducer/gearbox: cylinder + output shaft
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    body = body.faces(">Z").workplane().circle({sd/2}).extrude({sl})
    return body"""


def _gen_spring(dims: dict) -> str:
    od = dims.get("od", 10)
    t = dims.get("t", 0.7)
    h = dims.get("h", 0.85)
    id_ = dims.get("id", od * 0.5)
    return f"""    # Simplified disc spring: annular ring (stack approximation)
    body = (cq.Workplane("XY")
            .circle({od/2}).circle({id_/2}).extrude({max(t, h)})
            )
    return body"""


def _gen_bearing(dims: dict) -> str:
    od = dims.get("od", 12)
    id_ = dims.get("id", 6)
    w = dims.get("w", 4)
    return f"""    # Simplified bearing: outer ring + inner ring + gap
    outer = cq.Workplane("XY").circle({od/2}).circle({od/2 - 1}).extrude({w})
    inner = cq.Workplane("XY").circle({id_/2 + 1}).circle({id_/2}).extrude({w})
    body = outer.union(inner)
    return body"""


def _gen_sensor(dims: dict) -> str:
    if "d" in dims:
        d = dims["d"]
        l = dims.get("l", 12)
        return f"""    # Simplified sensor: cylinder
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""
    w = dims.get("w", 20)
    h = dims.get("h", 15)
    l = dims.get("l", 12)
    return f"""    # Simplified sensor: box
    body = cq.Workplane("XY").box({w}, {h}, {l}, centered=(True, True, False))
    return body"""


def _gen_pump(dims: dict) -> str:
    w = dims.get("w", 30)
    h = dims.get("h", 25)
    l = dims.get("l", 40)
    return f"""    # Simplified pump: box with port stubs
    body = cq.Workplane("XY").box({w}, {h}, {l}, centered=(True, True, False))
    # Input/output port stubs
    body = body.faces(">X").workplane().center(0, {l/2}).circle(3).extrude(5)
    body = body.faces("<X").workplane().center(0, {l/2}).circle(3).extrude(5)
    return body"""


def _gen_connector(dims: dict) -> str:
    d = dims.get("d", 10)
    l = min(dims.get("l", 25), 50)  # cap for assembly visualization
    if "w" in dims:
        w = dims["w"]
        h = dims.get("h", 3)
        l = min(dims.get("l", 8), 50)
        return f"""    # Simplified flat connector
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    return body"""
    return f"""    # Simplified round connector
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""


def _gen_seal(dims: dict) -> str:
    od = dims.get("od", 80)
    section_d = dims.get("section_d", 2.4)
    id_ = dims.get("id", od - 2 * section_d)
    r_center = (od + id_) / 4
    return f"""    # Simplified O-ring: torus
    path = cq.Workplane("XY").circle({r_center})
    body = (cq.Workplane("XZ")
            .center({r_center}, 0)
            .circle({section_d/2})
            .sweep(path))
    return body"""


def _gen_tank(dims: dict) -> str:
    d = dims.get("d", 38)
    l = dims.get("l", 280)
    return f"""    # Simplified tank: cylinder with domed ends
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""


_GENERATORS = {
    "motor":     _gen_motor,
    "reducer":   _gen_reducer,
    "spring":    _gen_spring,
    "bearing":   _gen_bearing,
    "sensor":    _gen_sensor,
    "pump":      _gen_pump,
    "connector": _gen_connector,
    "seal":      _gen_seal,
    "tank":      _gen_tank,
}

# Categories to skip (too small or too complex for simplified geometry)
_SKIP_CATEGORIES = {"fastener", "cable", "other"}


def _safe_module_name(part_no: str) -> str:
    """Part number → std module name.

    GIS-EE-001-05 → std_ee_001_05
    SLP-C01       → std_c01
    """
    from cad_spec_defaults import strip_part_prefix
    suffix = strip_part_prefix(part_no).lower().replace("-", "_")
    if suffix and suffix[0].isdigit():
        suffix = "p" + suffix
    return f"std_{suffix}"


def generate_std_part_files(spec_path: str, output_dir: str, mode: str = "scaffold") -> tuple:
    """Generate simplified CadQuery files for purchased standard parts.

    Args:
        mode: "scaffold" (skip existing), "force" (overwrite existing)

    Returns (generated_files, skipped_files).
    """
    parts = parse_bom_tree(spec_path)
    generated = []
    skipped = []

    for p in parts:
        if p["is_assembly"]:
            continue
        if "外购" not in p.get("make_buy", "") and "标准" not in p.get("make_buy", ""):
            continue

        category = classify_part(p["name_cn"], p["material"])
        if category in _SKIP_CATEGORIES:
            continue

        gen_func = _GENERATORS.get(category)
        if not gen_func:
            continue

        dims = lookup_std_part_dims(p["name_cn"], p["material"], category)
        if not dims:
            continue

        mod_name = _safe_module_name(p["part_no"])
        out_file = os.path.join(output_dir, f"{mod_name}.py")

        # Skip existing unless force mode
        if os.path.exists(out_file) and mode != "force":
            skipped.append(out_file)
            continue

        body_code = gen_func(dims)

        content = f'''"""
{p["name_cn"]} ({p["part_no"]}) — 简化标准件几何

Auto-generated by codegen/gen_std_parts.py
Category: {category} | Make/Buy: 外购
Material: {p["material"]}
Dimensions: {dims}

NOTE: This is a simplified representation for visualization only.
      Not for manufacturing — actual part is purchased.
"""

import cadquery as cq


def make_{mod_name}() -> cq.Workplane:
    """{p["part_no"]}: {p["name_cn"]} — simplified {category} geometry."""
{body_code}


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_{mod_name}()
    p = os.path.join(out, "{p["part_no"]}_std.step")
    cq.exporters.export(r, p)
    print(f"Exported: {{p}}")
'''
        Path(out_file).write_text(content, encoding="utf-8")
        generated.append(out_file)

    return generated, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Generate simplified CadQuery for purchased standard parts")
    parser.add_argument("spec", help="Path to CAD_SPEC.md")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory (default: same dir as spec)")
    parser.add_argument("--mode", choices=["scaffold", "force"], default="scaffold",
                        help="scaffold=skip existing, force=overwrite")
    args = parser.parse_args()

    spec_path = os.path.abspath(args.spec)
    output_dir = args.output_dir or os.path.dirname(spec_path)
    os.makedirs(output_dir, exist_ok=True)

    generated, skipped = generate_std_part_files(spec_path, output_dir, mode=args.mode)
    print(f"[gen_std_parts] Generated {len(generated)} standard part scaffold(s), "
          f"skipped {len(skipped)} existing")
    for f in generated:
        print(f"  + {os.path.basename(f)}")
    if skipped:
        print(f"  (skipped: {', '.join(os.path.basename(f) for f in skipped)})")


if __name__ == "__main__":
    main()
