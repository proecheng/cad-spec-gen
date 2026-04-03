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
                    "axis_dir": cells[5] if len(cells) > 5 else "",
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


def _axis_dir_to_local_transform(axis_dir: str, var_name: str,
                                   part_name: str = "") -> tuple:
    """Convert §6.2 axis_dir text to CadQuery rotation code.

    All std parts are generated with principal axis along +Z.
    This function returns (transform_code, doc_ref) to reorient parts
    based on their assembly axis description.

    The axis_dir field may contain multiple sub-descriptions separated by
    commas, e.g. "壳体轴沿-Z（垂直向下），储罐轴∥XY（水平径向外伸）".
    When part_name is given, match the relevant sub-clause first.

    Returns (None, None) if no rotation needed (default +Z or -Z is OK).
    """
    if not axis_dir:
        return None, None

    text = axis_dir.strip()

    # If axis_dir has multiple sub-clauses (e.g. "壳体轴沿-Z，储罐轴∥XY"),
    # find the clause relevant to this part by matching part_name keywords.
    if part_name and ("，" in text or "," in text):
        clauses = re.split(r"[，,]", text)
        matched_clause = None
        for clause in clauses:
            keywords = []
            if len(part_name) >= 2:
                keywords.append(part_name[:2])
            if len(part_name) >= 3:
                keywords.append(part_name[:3])
            if len(part_name) >= 4:
                keywords.append(part_name[-2:])
            if any(kw in clause for kw in keywords if kw):
                matched_clause = clause.strip()
                break
        if matched_clause:
            text = matched_clause

    # PRIORITY 1: "盘面∥XY" / "环∥XY" / "弧形∥XY" → face parallel to XY → axis already Z → NO rotation
    if any(k in text for k in ["盘面∥XY", "环∥XY", "弧形∥XY"]):
        return None, None

    # PRIORITY 2: "沿-Z" / "沿Z" / "垂直" / "⊥法兰" → already along Z → NO rotation
    if any(k in text for k in ["沿-Z", "沿Z", "垂直", "⊥法兰"]):
        return None, None

    # PRIORITY 3: "轴∥XY" / "水平" / "径向外伸" → needs horizontal → rotate 90° around X
    if any(k in text for k in ["∥XY", "水平", "径向外伸"]):
        code = f"{var_name}.rotate((0,0,0), (1,0,0), 90)"
        return code, f"axis horizontal per §6.2: {text[:60]}"

    return None, None


def _build_layer_axis_map(pose: dict) -> dict:
    """Build a map from part-name substring to axis_dir for orientation lookup.

    Uses §6.2 layer data. Returns {part_substring: axis_dir_text}.
    """
    axis_map = {}
    for layer in pose.get("layers", []):
        part = layer.get("part", "")
        axis = layer.get("axis_dir", "")
        if part and axis:
            # Extract the key identifier (e.g. "GIS-EE-002" from layer part name)
            m = re.search(r"GIS-\w+-\d+", part)
            if m:
                axis_map[m.group(0)] = axis
            # Also store by part description keywords for fuzzy matching
            axis_map[part[:20]] = axis
    return axis_map


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


def _extract_station_angles(pose: dict) -> list:
    """Extract station angles from §6 pose layers.

    Looks for layers with angle information (e.g. "0°", "90°", "旋转90").
    Returns list of floats, or empty list if no radial pattern found.
    """
    angles = []
    for layer in pose.get("layers", []):
        offset = layer.get("offset", "")
        fix_move = layer.get("fix_move", "")
        # Look for angle patterns in offset or fix_move
        for text in (offset, fix_move):
            m = re.search(r"(\d+(?:\.\d+)?)\s*[°度]", text)
            if m:
                angles.append(float(m.group(1)))
                break
    return angles


def _extract_origin_axis(pose: dict) -> tuple:
    """Extract origin and axis descriptions from §6 coordinate system table.

    Returns (origin_desc, axis_desc) with sensible defaults.
    """
    origin_desc = "assembly geometric center"
    axis_desc = "Z-up, X-right"
    for entry in pose.get("coord_sys", []):
        term = entry.get("term", "").lower()
        defn = entry.get("definition", "")
        if "原点" in term or "origin" in term:
            origin_desc = defn or origin_desc
        elif "轴" in term or "axis" in term.lower():
            axis_desc = defn or axis_desc
    return origin_desc, axis_desc


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

    # C1: Extract station angles from §6 pose layers instead of hardcoding
    station_angles = _extract_station_angles(pose)
    has_radial = any("旋转" in l.get("fix_move", "") for l in pose.get("layers", []))

    # C6: Build orientation map from §6.2 axis_dir column
    axis_map = _build_layer_axis_map(pose)

    for i, assy in enumerate(assemblies):
        pno = assy["part_no"]
        name = assy["name_cn"]
        suffix = re.sub(r"^GIS-\w+-", "", pno)

        # Gather children
        children = [p for p in parts
                     if p["part_no"].startswith(pno + "-") and not p["is_assembly"]]

        station_parts = []
        std_func_imports = []  # std parts for this station

        # C6: Find axis_dir for this station from §6.2 (match by assembly part_no)
        station_axis_dir = ""
        for akey, adir in axis_map.items():
            if pno in akey or name[:6] in akey:
                station_axis_dir = adir
                break

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

                # C6: Apply station-level orientation from §6.2 axis_dir
                var_name = f"p_{std_mod}"
                local_xform, orient_ref = _axis_dir_to_local_transform(
                    station_axis_dir, var_name, child["name_cn"])

                station_parts.append({
                    "var": var_name,
                    "make_call": f"{std_func}()",
                    "local_transform": local_xform,
                    "orient_doc_ref": orient_ref or "",
                    "orient_rule": "",
                    "assy_name": f"STD-{child['part_no']}",
                    "color_var": color_info[0],
                })
                std_func_imports.append({
                    "module": std_mod,
                    "func": std_func,
                })
            else:
                # Custom-made part — import from individual ee_NNN_NN module
                # gen_parts.py names: GIS-EE-001-01 → ee_001_01.py / make_ee_001_01()
                ee_mod = re.sub(r"^GIS-", "", child["part_no"]).lower().replace("-", "_")
                ee_func = f"make_{ee_mod}"
                c_color = _COLOR_PALETTE[color_idx % len(_COLOR_PALETTE)][0]

                # C6: Apply station-level orientation from §6.2 axis_dir
                var_name = f"p_{ee_mod}"
                local_xform, orient_ref = _axis_dir_to_local_transform(
                    station_axis_dir, var_name, child["name_cn"])

                station_parts.append({
                    "var": var_name,
                    "make_call": f"{ee_func}()",
                    "local_transform": local_xform,
                    "orient_doc_ref": orient_ref or "",
                    "orient_rule": "",
                    "assy_name": f"{prefix_short}-{suffix}-{c_suffix}",
                    "color_var": c_color,
                })
                # Each custom part gets its own import line
                part_imports.append({
                    "module": ee_mod,
                    "functions": [ee_func],
                })

        for si in std_func_imports:
            std_part_imports.append(si)

        # C2: Use has_radial flag and actual station_angles from spec
        is_radial = has_radial and i < len(station_angles)
        angle = station_angles[i] if is_radial else 0.0

        # C3: Only reference mount_radius/base_z params if radial layout detected
        station_entry = {
            "name_cn": name,
            "angle": angle,
            "is_radial": is_radial,
            "parts": station_parts,
        }
        if is_radial:
            station_entry["mount_radius"] = "MOUNT_CENTER_R"
            station_entry["base_z"] = "FLANGE_AL_THICK"
        stations.append(station_entry)

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

    # C5: Extract origin/axis from spec §6 instead of hardcoding
    origin_desc, axis_desc = _extract_origin_axis(pose)

    # C4: Collect assembly_params from what stations actually use
    assembly_params_set = set()
    for stn in stations:
        if stn.get("mount_radius"):
            assembly_params_set.add(stn["mount_radius"])
        if stn.get("base_z"):
            assembly_params_set.add(stn["base_z"])
    if station_angles:
        assembly_params_set.add("STATION_ANGLES")
    assembly_params = sorted(assembly_params_set)

    content = template.render(
        subsystem_name_cn=re.search(r"# CAD Spec — (.+?)(?:\s*\(|$)", text).group(1)
            if re.search(r"# CAD Spec — (.+?)(?:\s*\(|$)", text) else "Unknown",
        assembly_part_no=f"{prefix_short}-000",
        source_file=spec_path,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        origin_desc=origin_desc,
        axis_desc=axis_desc,
        bom_tree=bom_tree[:15],  # Limit docstring length
        assembly_params=assembly_params,
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
