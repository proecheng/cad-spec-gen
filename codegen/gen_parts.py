#!/usr/bin/env python3
"""
Code Generator: CAD_SPEC.md §5 BOM → Part Module Scaffolds

Generates a CadQuery .py file for each custom-made leaf part in the BOM.
Only creates NEW files — never overwrites existing ones.

Usage:
    python codegen/gen_parts.py cad/end_effector/CAD_SPEC.md
    python codegen/gen_parts.py cad/end_effector/CAD_SPEC.md --output-dir cad/end_effector
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import jinja2

_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from codegen.gen_build import parse_bom_tree


def _safe_module_name(part_no: str, name_cn: str) -> str:
    """Generate a clean Python module/function name from part number."""
    # Use part_no suffix: GIS-EE-001-01 → ee_001_01
    suffix = re.sub(r"^GIS-", "", part_no).lower().replace("-", "_")
    return suffix


def _guess_envelope(name_cn: str, material: str) -> dict:
    """Guess reasonable envelope dimensions from part name (generic defaults)."""
    defaults = {"w": 40.0, "d": 40.0, "h": 20.0}

    # Generic patterns by part type keywords
    if "壳体" in name_cn or "模块" in name_cn or "housing" in name_cn.lower():
        defaults = {"w": 50.0, "d": 40.0, "h": 60.0}
    elif "支架" in name_cn or "bracket" in name_cn.lower():
        defaults = {"w": 50.0, "d": 40.0, "h": 25.0}
    elif "法兰" in name_cn or "flange" in name_cn.lower():
        defaults = {"w": 80.0, "d": 80.0, "h": 20.0}
    elif "适配" in name_cn or "adapter" in name_cn.lower():
        defaults = {"w": 60.0, "d": 60.0, "h": 10.0}
    elif "垫" in name_cn or "ring" in name_cn.lower():
        defaults = {"w": 30.0, "d": 30.0, "h": 5.0}
    elif "盖" in name_cn or "cover" in name_cn.lower():
        defaults = {"w": 25.0, "d": 20.0, "h": 3.0}
    elif "板" in name_cn or "plate" in name_cn.lower():
        defaults = {"w": 60.0, "d": 40.0, "h": 10.0}
    elif "柱" in name_cn or "column" in name_cn.lower():
        defaults = {"w": 30.0, "d": 30.0, "h": 80.0}

    return defaults


def generate_part_files(spec_path: str, output_dir: str, mode: str = "scaffold") -> list:
    """Generate part module scaffolds for all custom-made leaf parts.

    Args:
        mode: "scaffold" (skip existing), "force" (overwrite existing)

    Returns list of generated file paths.
    """
    parts = parse_bom_tree(spec_path)
    generated = []
    skipped = []

    template_dir = os.path.join(_PROJECT_ROOT, "templates")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("part_module.py.j2")

    for p in parts:
        # Only generate for custom-made leaf parts
        if p["is_assembly"]:
            continue
        if "自制" not in p.get("make_buy", ""):
            continue

        mod_name = _safe_module_name(p["part_no"], p["name_cn"])
        func_name = mod_name
        out_file = os.path.join(output_dir, f"{mod_name}.py")

        # Skip existing unless force mode
        if os.path.exists(out_file) and mode != "force":
            skipped.append(out_file)
            continue

        envelope = _guess_envelope(p["name_cn"], p["material"])

        content = template.render(
            part_name_cn=p["name_cn"],
            part_no=p["part_no"],
            source_ref=f"CAD_SPEC.md §5 BOM",
            material=p["material"],
            func_name=func_name,
            param_imports=[],  # Empty — user adds specific params
            envelope_w=envelope["w"],
            envelope_d=envelope["d"],
            envelope_h=envelope["h"],
            weight="?",
            has_mounting_holes=False,
            mount_bolt_pcd=28.0,
            mount_bolt_num=4,
            has_dxf=True,
        )

        Path(out_file).write_text(content, encoding="utf-8")
        generated.append(out_file)

    return generated, skipped


def scan_todos(files: list) -> dict:
    """Scan generated files for unfilled TODO markers.

    Returns dict of {filepath: [line_numbers]} for files with TODOs.
    """
    result = {}
    for f in files:
        todos = []
        try:
            lines = Path(f).read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, 1):
                if "TODO:" in line:
                    todos.append((i, line.strip()))
        except OSError:
            pass
        if todos:
            result[f] = todos
    return result



def main():
    parser = argparse.ArgumentParser(
        description="Generate part module scaffolds from CAD_SPEC.md §5 BOM")
    parser.add_argument("spec", help="Path to CAD_SPEC.md")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory (default: same dir as spec)")
    parser.add_argument("--mode", choices=["scaffold", "force"], default="scaffold",
                        help="scaffold=skip existing, force=overwrite")
    args = parser.parse_args()

    spec_path = os.path.abspath(args.spec)
    output_dir = args.output_dir or os.path.dirname(spec_path)
    os.makedirs(output_dir, exist_ok=True)

    generated, skipped = generate_part_files(spec_path, output_dir, mode=args.mode)
    print(f"[gen_parts] Generated {len(generated)} part scaffold(s), "
          f"skipped {len(skipped)} existing")
    for f in generated:
        print(f"  + {os.path.basename(f)}")
    if skipped:
        print(f"  (skipped: {', '.join(os.path.basename(f) for f in skipped)})")

    # ── TODO scan: warn on unfilled coordinate system blocks ─────────────────
    todos = scan_todos(generated)
    if todos:
        print(f"\n[gen_parts] WARNING: {len(todos)} file(s) have unfilled TODO markers")
        print("  Fill these before running 'cad_pipeline.py build' or orientation_check will fail:")
        for fpath, items in todos.items():
            print(f"  {os.path.basename(fpath)}:")
            for lineno, text in items:
                print(f"    L{lineno}: {text}")
        sys.exit(2)  # exit code 2 = scaffold generated but TODOs remain
    else:
        print("[gen_parts] All coordinate system blocks filled. Ready for build.")


if __name__ == "__main__":
    main()
