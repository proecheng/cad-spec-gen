#!/usr/bin/env python3
"""
Code Generator: CAD_SPEC.md §5 BOM → build_all.py

Reads BOM tree from CAD_SPEC.md and generates the _STEP_BUILDS and
_DXF_BUILDS tables for build_all.py.

Usage:
    python codegen/gen_build.py cad/end_effector/CAD_SPEC.md
    python codegen/gen_build.py cad/end_effector/CAD_SPEC.md --mode force
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

from bom_parser import classify_part

# Categories that get simplified CadQuery geometry (skip fastener/cable/other)
_STD_PART_CATEGORIES = {"motor", "reducer", "spring", "bearing", "sensor",
                        "pump", "connector", "seal", "tank", "transmission"}


def parse_bom_tree(spec_path: str) -> list:
    """Parse §5 BOM tree from CAD_SPEC.md.

    Returns list of dicts: {part_no, name_cn, level, is_assembly, material, ...}
    """
    text = Path(spec_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    in_section = False
    header_found = False

    # Pass 1: collect all raw rows
    raw_rows = []
    for line in lines:
        if re.match(r"##\s*5\.\s*BOM", line):
            in_section = True
            continue
        if in_section and re.match(r"##\s*[6-9]", line):
            break
        if not in_section:
            continue

        if ("零件号" in line or "料号" in line) and "名称" in line:
            header_found = True
            continue
        if re.match(r"\|\s*---", line):
            continue

        if header_found and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c is not None]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            if len(cells) < 3:
                continue
            raw_rows.append(cells)

    # Pass 2: classify assembly vs leaf using structural analysis
    all_part_nos = {r[0].replace("**", "").strip() for r in raw_rows}
    parts = []
    for cells in raw_rows:
        part_no = cells[0].replace("**", "").strip()
        name_cn = cells[1].replace("**", "").strip() if len(cells) > 1 else ""
        material = cells[2] if len(cells) > 2 else ""
        quantity = cells[3] if len(cells) > 3 else "1"
        make_buy = cells[4] if len(cells) > 4 else ""

        # Assembly detection (prefix-independent):
        # 1. Explicit "总成" in make_buy → always assembly
        # 2. Has children: other part_nos start with this + "-" → assembly
        if "总成" in make_buy:
            is_assembly = True
        else:
            is_assembly = any(
                pno.startswith(part_no + "-")
                for pno in all_part_nos if pno != part_no
            )

        parts.append({
            "part_no": part_no,
            "name_cn": name_cn,
            "is_assembly": is_assembly,
            "material": material,
            "quantity": quantity,
            "make_buy": make_buy,
        })

    return parts


def _part_no_to_module_name(part_no: str, name_cn: str) -> str:
    """Convert part number to Python module name.

    GIS-EE-001 → flange (from name_cn)
    ACME-PLT-002 → station1_applicator
    """
    from cad_spec_defaults import strip_part_prefix
    # 通用前缀剥离后取最后一段
    stripped = strip_part_prefix(part_no)
    suffix = stripped.split("-")[-1] if "-" in stripped else stripped
    # Use name as base
    name = re.sub(r"[（(].*$", "", name_cn).strip()
    name = name.lower().replace(" ", "_").replace("-", "_")
    # Remove Chinese characters for module name
    ascii_name = re.sub(r"[^\x00-\x7f]", "", name).strip("_")
    if ascii_name:
        return ascii_name
    return f"part_{suffix.replace('-', '_')}"


def _part_no_to_func_name(part_no: str, name_cn: str) -> str:
    """Convert to CadQuery function name: make_<module_name>"""
    mod = _part_no_to_module_name(part_no, name_cn)
    return f"make_{mod}"


def _part_no_to_step_filename(part_no: str) -> str:
    """Convert part number to STEP filename: EE-001_flange_al.step"""
    from cad_spec_defaults import strip_part_prefix
    suffix = strip_part_prefix(part_no)
    return f"{suffix}.step"


def generate_build_tables(parts: list) -> dict:
    """Generate _STEP_BUILDS and _DXF_BUILDS from BOM.

    - Assembly-level parts (GIS-EE-001) → STEP builds
    - Custom-made leaf parts (GIS-EE-001-01, 自制) → DXF drawings
    - Purchased standard parts with geometry (外购, motor/bearing/...) → STD STEP builds
    """
    step_builds = []
    dxf_builds = []
    std_step_builds = []

    for p in parts:
        pno = p["part_no"]
        name = p["name_cn"]

        if p["is_assembly"]:
            # Assembly-level entries (GIS-EE-001, 002...) are exported by
            # assembly.py as EE-000_assembly.step — skip individual STEP builds
            # since there are no standalone sub-assembly Python modules.
            continue
        elif "自制" in p.get("make_buy", ""):
            # Custom-made leaf part → DXF drawing
            # Module name must match gen_parts.py: GIS-EE-001-01 → ee_001_01
            from cad_spec_defaults import strip_part_prefix
            ee_mod = strip_part_prefix(pno).lower().replace("-", "_")
            if ee_mod and ee_mod[0].isdigit():
                ee_mod = "p" + ee_mod
            mod = ee_mod
            func = f"draw_{ee_mod}_sheet"
            label = re.sub(r"[（(].*$", "", name).strip()

            dxf_builds.append({
                "label": label,
                "module": mod,
                "func": func,
            })
        elif "外购" in p.get("make_buy", "") or "标准" in p.get("make_buy", ""):
            # Purchased standard part → simplified STEP
            category = classify_part(name, p.get("material", ""))
            if category in _STD_PART_CATEGORIES:
                from cad_spec_defaults import strip_part_prefix
                suffix = strip_part_prefix(pno).lower().replace("-", "_")
                if suffix and suffix[0].isdigit():
                    suffix = "p" + suffix
                mod = f"std_{suffix}"
                func = f"make_std_{suffix}"
                filename = f"{pno}_std.step"
                label = f"[标准件] {re.sub(r'[（(].*$', '', name).strip()}"

                std_step_builds.append({
                    "label": label,
                    "module": mod,
                    "func": func,
                    "filename": filename,
                })

    return {
        "step_builds": step_builds,
        "dxf_builds": dxf_builds,
        "std_step_builds": std_step_builds,
    }


def render_build_all(tables: dict, spec_path: str, cad_dir: str,
                     subsystem_name_cn: str) -> str:
    """Render build_all.py from template."""
    template_dir = os.path.join(_PROJECT_ROOT, "templates")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    template = env.get_template("build_all.py.j2")
    return template.render(
        subsystem_name_cn=subsystem_name_cn,
        source_file=spec_path,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        cad_dir=cad_dir,
        step_builds=tables["step_builds"],
        dxf_builds=tables["dxf_builds"],
        std_step_builds=tables.get("std_step_builds", []),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate build_all.py from CAD_SPEC.md §5 BOM")
    parser.add_argument("spec", help="Path to CAD_SPEC.md")
    parser.add_argument("--output", "-o", default=None,
                        help="Output path (default: same dir as spec)")
    parser.add_argument("--mode", choices=["scaffold", "force"],
                        default="scaffold")
    parser.add_argument("--subsystem-name", default=None,
                        help="Subsystem Chinese name (auto-detected if omitted)")
    args = parser.parse_args()

    spec_path = os.path.abspath(args.spec)
    output_path = args.output or os.path.join(os.path.dirname(spec_path), "build_all.py")

    if args.mode == "scaffold" and os.path.exists(output_path):
        print(f"[gen_build] SKIP: {output_path} already exists (use --mode force)")
        return

    parts = parse_bom_tree(spec_path)
    print(f"[gen_build] Parsed {len(parts)} BOM entries")

    tables = generate_build_tables(parts)
    print(f"[gen_build] Generated {len(tables['step_builds'])} STEP + "
          f"{len(tables['dxf_builds'])} DXF + "
          f"{len(tables.get('std_step_builds', []))} STD build targets")

    # Auto-detect subsystem name from spec header
    name_cn = args.subsystem_name
    if not name_cn:
        text = Path(spec_path).read_text(encoding="utf-8")
        m = re.search(r"# CAD Spec — (.+?)(?:\s*\(|$)", text)
        name_cn = m.group(1) if m else "Unknown"

    cad_dir = os.path.basename(os.path.dirname(spec_path))
    content = render_build_all(tables, spec_path, cad_dir, name_cn)
    Path(output_path).write_text(content, encoding="utf-8")
    print(f"[gen_build] Generated: {output_path}")


if __name__ == "__main__":
    main()
