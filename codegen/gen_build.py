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


def parse_bom_tree(spec_path: str) -> list:
    """Parse §5 BOM tree from CAD_SPEC.md.

    Returns list of dicts: {part_no, name_cn, level, is_assembly, material, ...}
    """
    text = Path(spec_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    parts = []
    in_section = False
    header_found = False

    for line in lines:
        if re.match(r"##\s*5\.\s*BOM", line):
            in_section = True
            continue
        if in_section and re.match(r"##\s*[6-9]", line):
            break
        if not in_section:
            continue

        # Detect table header
        if ("零件号" in line or "料号" in line) and "名称" in line:
            header_found = True
            continue
        if re.match(r"\|\s*---", line):
            continue

        if header_found and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c is not None]
            # Remove empty bookend cells
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            if len(cells) < 3:
                continue

            part_no = cells[0].replace("**", "").strip()
            name_cn = cells[1].replace("**", "").strip() if len(cells) > 1 else ""
            # Determine nesting level from part number segments
            # GIS-EE-001 = assembly (3 segments), GIS-EE-001-01 = leaf part (4 segments)
            segments = part_no.split("-")
            is_assembly = len(segments) == 3  # e.g., GIS-EE-001

            material = cells[2] if len(cells) > 2 else ""
            quantity = cells[3] if len(cells) > 3 else "1"
            make_buy = cells[4] if len(cells) > 4 else ""

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
    GIS-EE-002 → station1_applicator
    """
    # Strip prefix
    suffix = re.sub(r"^GIS-\w+-", "", part_no)
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
    # Strip GIS- prefix
    suffix = re.sub(r"^GIS-", "", part_no)
    return f"{suffix}.step"


def generate_build_tables(parts: list) -> dict:
    """Generate _STEP_BUILDS and _DXF_BUILDS from BOM.

    - Assembly-level parts (GIS-EE-001) → STEP builds
    - Custom-made leaf parts (GIS-EE-001-01, 自制) → DXF drawings
    """
    step_builds = []
    dxf_builds = []

    for p in parts:
        pno = p["part_no"]
        name = p["name_cn"]

        if p["is_assembly"]:
            # Assembly module → STEP build
            mod = _part_no_to_module_name(pno, name)
            func = _part_no_to_func_name(pno, name)
            filename = _part_no_to_step_filename(pno)
            label = re.sub(r"[（(].*$", "", name).strip()

            step_builds.append({
                "label": label,
                "module": mod,
                "func": func,
                "filename": filename,
            })
        elif "自制" in p.get("make_buy", ""):
            # Custom-made leaf part → DXF drawing
            mod = f"draw_{_part_no_to_module_name(pno, name)}"
            func = f"draw_{_part_no_to_module_name(pno, name)}_sheet"
            label = re.sub(r"[（(].*$", "", name).strip()

            dxf_builds.append({
                "label": label,
                "module": mod,
                "func": func,
            })

    return {
        "step_builds": step_builds,
        "dxf_builds": dxf_builds,
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
          f"{len(tables['dxf_builds'])} DXF build targets")

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
