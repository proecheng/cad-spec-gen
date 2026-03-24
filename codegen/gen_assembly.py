#!/usr/bin/env python3
"""
Code Generator: CAD_SPEC.md → assembly.py scaffold

Reads BOM tree (§5), connection matrix (§4), and assembly pose (§6) from
CAD_SPEC.md to generate an assembly.py scaffold with proper part imports,
station transforms, and color assignments.

Usage:
    python codegen/gen_assembly.py cad/end_effector/CAD_SPEC.md
    python codegen/gen_assembly.py cad/end_effector/CAD_SPEC.md --mode force
"""

import argparse
import math
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
from bom_parser import classify_part

# Categories that get simplified CadQuery geometry
_STD_PART_CATEGORIES = {"motor", "reducer", "spring", "bearing", "sensor",
                        "pump", "connector", "seal", "tank"}


def parse_assembly_pose(spec_path: str) -> dict:
    """Parse §6 assembly pose (coordinate system + layer stacking)."""
    text = Path(spec_path).read_text(encoding="utf-8")
    lines = text.splitlines()

    coord_sys = []
    layers = []
    in_coord = False
    in_layers = False

    for line in lines:
        if "坐标系定义" in line:
            in_coord = True
            in_layers = False
            continue
        if "装配层叠" in line:
            in_layers = True
            in_coord = False
            continue
        if re.match(r"##\s*7", line):
            break

        if in_coord and line.startswith("|") and "---" not in line and "术语" not in line:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 2:
                coord_sys.append({"term": cells[0], "definition": cells[1]})

        if in_layers and line.startswith("|") and "---" not in line and "层级" not in line:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 4:
                layers.append({
                    "level": cells[0],
                    "part": cells[1],
                    "fix_move": cells[2],
                    "connection": cells[3],
                    "offset": cells[4] if len(cells) > 4 else "",
                })

    return {"coord_sys": coord_sys, "layers": layers}


def parse_connections(spec_path: str) -> list:
    """Parse §4 connection matrix."""
    text = Path(spec_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    connections = []
    in_section = False
    header_found = False

    for line in lines:
        if re.match(r"##\s*4\.\s*连接", line):
            in_section = True
            continue
        if in_section and re.match(r"##\s*5", line):
            break
        if not in_section:
            continue

        if "零件A" in line and "零件B" in line:
            header_found = True
            continue
        if re.match(r"\|\s*---", line):
            continue

        if header_found and line.startswith("|"):
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 3:
                connections.append({
                    "part_a": cells[0],
                    "part_b": cells[1],
                    "type": cells[2],
                    "fit_code": cells[3] if len(cells) > 3 else "",
                    "torque": cells[4] if len(cells) > 4 else "",
                })

    return connections


# ── Default color palette for assemblies ──
_COLOR_PALETTE = [
    ("C_DARK",    0.15, 0.15, 0.15),
    ("C_SILVER",  0.80, 0.80, 0.82),
    ("C_AMBER",   0.85, 0.65, 0.13),
    ("C_BLUE",    0.35, 0.55, 0.75),
    ("C_GREEN",   0.15, 0.50, 0.25),
    ("C_BRONZE",  0.70, 0.42, 0.20),
    ("C_PURPLE",  0.50, 0.18, 0.65),
    ("C_RUBBER",  0.10, 0.10, 0.10),
]

# ── Distinct colors for standard/purchased parts ──
_STD_COLOR_MAP = {
    "motor":     ("C_STD_MOTOR",   0.75, 0.75, 0.78),  # silver metallic
    "reducer":   ("C_STD_REDUCER", 0.70, 0.70, 0.72),  # darker silver
    "spring":    ("C_STD_SPRING",  0.78, 0.68, 0.20),  # golden steel
    "bearing":   ("C_STD_BEARING", 0.60, 0.60, 0.65),  # steel grey
    "sensor":    ("C_STD_SENSOR",  0.20, 0.20, 0.20),  # dark (electronics)
    "pump":      ("C_STD_PUMP",    0.55, 0.55, 0.60),  # medium grey
    "connector": ("C_STD_CONN",    0.25, 0.25, 0.25),  # dark grey
    "seal":      ("C_STD_SEAL",    0.08, 0.08, 0.08),  # black rubber
    "tank":      ("C_STD_TANK",    0.82, 0.82, 0.85),  # bright steel
}


def generate_assembly(spec_path: str) -> str:
    """Generate assembly.py scaffold content."""
    parts = parse_bom_tree(spec_path)
    pose = parse_assembly_pose(spec_path)
    connections = parse_connections(spec_path)

    # Separate assemblies and their children
    assemblies = [p for p in parts if p["is_assembly"]]

    # Detect subsystem prefix from spec
    text = Path(spec_path).read_text(encoding="utf-8")
    m = re.search(r"\(([A-Z]+-[A-Z]+)\)", text[:200])
    prefix = m.group(1) if m else "GIS-XX"
    prefix_short = prefix.split("-")[-1]  # EE

    template_dir = os.path.join(_PROJECT_ROOT, "templates")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("assembly.py.j2")

    # Build station definitions
    stations = []
    part_imports = []
    std_part_imports = []
    color_idx = 0
    std_colors_used = {}  # track which std colors we need

    # Detect station angle pattern from pose layers
    station_angles = [0.0, 90.0, 180.0, 270.0]  # default 4-station
    has_radial = any("旋转" in l.get("fix_move", "") for l in pose.get("layers", []))

    for i, assy in enumerate(assemblies):
        pno = assy["part_no"]
        name = assy["name_cn"]
        suffix = re.sub(r"^GIS-\w+-", "", pno)

        # Gather children
        children = [p for p in parts
                     if p["part_no"].startswith(pno + "-") and not p["is_assembly"]]

        station_parts = []
        mod_name = f"module_{suffix.lower()}"
        func_names = []
        std_func_imports = []  # std parts for this station

        for child in children:
            c_suffix = re.sub(r"^GIS-\w+-\d+-", "", child["part_no"])
            make_buy = child.get("make_buy", "")

            if "外购" in make_buy:
                # Standard/purchased part — use std_ module
                category = classify_part(child["name_cn"], child.get("material", ""))
                if category not in _STD_PART_CATEGORIES:
                    continue
                std_mod = f"std_{re.sub(r'^GIS-', '', child['part_no']).lower().replace('-', '_')}"
                std_func = f"make_{std_mod}"
                color_info = _STD_COLOR_MAP.get(category, ("C_STD_SENSOR", 0.2, 0.2, 0.2))
                std_colors_used[color_info[0]] = color_info

                station_parts.append({
                    "var": f"p_{std_mod}",
                    "make_call": f"{std_func}()",
                    "local_transform": None,
                    "assy_name": f"STD-{child['part_no']}",
                    "color_var": color_info[0],
                })
                std_func_imports.append({
                    "module": std_mod,
                    "func": std_func,
                })
            else:
                # Custom-made part
                c_func = f"make_{suffix.lower()}_{c_suffix}"
                func_names.append(c_func)
                c_color = _COLOR_PALETTE[color_idx % len(_COLOR_PALETTE)][0]

                station_parts.append({
                    "var": f"p_{suffix.lower()}_{c_suffix}",
                    "make_call": f"{c_func}()",
                    "local_transform": None,
                    "assy_name": f"{prefix_short}-{suffix}-{c_suffix}",
                    "color_var": c_color,
                })

        if func_names:
            part_imports.append({
                "module": mod_name,
                "functions": func_names,
            })

        for si in std_func_imports:
            std_part_imports.append(si)

        # Determine if this is a radial station
        is_radial = i > 0 and i < len(assemblies) - 1 and len(station_angles) >= i
        angle = station_angles[i - 1] if is_radial and i > 0 else 0

        stations.append({
            "name_cn": name,
            "angle": angle,
            "is_radial": is_radial,
            "mount_radius": "MOUNT_CENTER_R",
            "base_z": "FLANGE_AL_THICK",
            "parts": station_parts,
        })

        color_idx += 1

    # Build BOM tree for docstring
    bom_tree = []
    for p in parts:
        segments = p["part_no"].split("-")
        depth = max(0, len(segments) - 3)
        bom_tree.append({
            "depth": depth,
            "part_no": p["part_no"],
            "name_cn": p["name_cn"],
            "is_last": False,
        })

    content = template.render(
        subsystem_name_cn=re.search(r"# CAD Spec — (.+?)(?:\s*\(|$)", text).group(1)
            if re.search(r"# CAD Spec — (.+?)(?:\s*\(|$)", text) else "Unknown",
        assembly_part_no=f"{prefix_short}-000",
        source_file=spec_path,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        origin_desc="flange rotation center",
        axis_desc="Z=0: back face, Z+: workspace side",
        bom_tree=bom_tree[:15],  # Limit docstring length
        assembly_params=[
            "STATION_ANGLES", "MOUNT_CENTER_R", "FLANGE_AL_THICK",
        ],
        part_imports=part_imports,
        std_part_imports=std_part_imports,
        colors=[{"name": c[0], "r": c[1], "g": c[2], "b": c[3]}
                for c in _COLOR_PALETTE],
        std_colors=[{"name": v[0], "r": v[1], "g": v[2], "b": v[3]}
                    for v in std_colors_used.values()],
        stations=stations,
    )

    return content


def main():
    parser = argparse.ArgumentParser(
        description="Generate assembly.py scaffold from CAD_SPEC.md")
    parser.add_argument("spec", help="Path to CAD_SPEC.md")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--mode", choices=["scaffold", "force"], default="scaffold")
    args = parser.parse_args()

    spec_path = os.path.abspath(args.spec)
    output_path = args.output or os.path.join(os.path.dirname(spec_path), "assembly.py")

    if args.mode == "scaffold" and os.path.exists(output_path):
        print(f"[gen_assembly] SKIP: {output_path} already exists (use --mode force)")
        return

    content = generate_assembly(spec_path)
    Path(output_path).write_text(content, encoding="utf-8")
    print(f"[gen_assembly] Generated: {output_path}")


if __name__ == "__main__":
    main()
