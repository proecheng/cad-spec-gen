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
from cad_spec_defaults import strip_part_prefix


def _safe_module_name(part_no: str, name_cn: str) -> str:
    """Generate a clean Python module/function name from part number."""
    # 通用前缀剥离: GIS-EE-001-01 → EE-001-01 → ee_001_01
    suffix = strip_part_prefix(part_no).lower().replace("-", "_")
    # Python identifiers cannot start with a digit; prefix with 'p' if needed
    if suffix and suffix[0].isdigit():
        suffix = "p" + suffix
    return suffix


def _derive_coord_system(part_no: str, name_cn: str, geom: dict,
                         pose_data: dict) -> dict:
    """Derive coordinate system descriptions from §6.2 assembly pose data.

    Returns dict with keys: local_origin_desc, principal_axis_desc,
    assembly_orient_desc, axis_source_ref.
    If §6.2 data is unavailable, returns empty strings (template falls back to TODO).
    """
    pose = pose_data.get(part_no, {})

    # If exact part_no not found, try parent assembly prefix match
    # e.g. GIS-EE-002-01 inherits from GIS-EE-002 (assembly-level pose)
    if not pose:
        for prefix_len in range(len(part_no) - 1, 5, -1):
            prefix = part_no[:prefix_len].rstrip("-")
            if prefix in pose_data:
                pose = pose_data[prefix]
                break

    axis_dir = pose.get("axis_dir", "")
    z = pose.get("z")
    r = pose.get("r")
    theta = pose.get("theta")

    if not axis_dir and z is None and r is None:
        return {}  # No data → template will use TODO defaults

    # Local origin — always center + bottom Z=0
    gtype = geom.get("type", "box")
    shape_word = {"cylinder": "cylinder", "ring": "ring", "disc_arms": "disc",
                  "l_bracket": "L-bracket base"}.get(gtype, "body")
    local_origin = f"Center of {shape_word} XY, bottom face at Z=0"

    # Principal axis — from geometry type
    h = geom.get("envelope_h", geom.get("h", "?"))
    principal = f"{gtype.replace('_', ' ').capitalize()} on XY, height along +Z ({h}mm)"

    # Assembly orientation — from §6.2 offsets
    orient_parts = []
    if r is not None and theta is not None:
        orient_parts.append(f"Polar R={r}mm θ={theta}°")
    if z is not None:
        orient_parts.append(f"Z={z}mm")
    if axis_dir:
        orient_parts.append(f"axis: {axis_dir}")
    assembly_orient = ", ".join(orient_parts) + " — per §6.2" if orient_parts else ""

    # Source ref
    source_ref = f"§6.2 {name_cn} ({part_no})"
    if axis_dir:
        source_ref += f" — {axis_dir}"

    return {
        "local_origin_desc": local_origin,
        "principal_axis_desc": principal,
        "assembly_orient_desc": assembly_orient,
        "axis_source_ref": source_ref,
    }


def _guess_geometry(name_cn: str, material: str) -> dict:
    """Infer approximate geometry type and dimensions for a custom part.

    Priority 1: Parse explicit dimensions from BOM material column
                (e.g. "6063铝合金 140×100×55mm" → box, "Φ38×280mm" → cylinder).
    Priority 2: Keyword-based heuristics from part name (generic types only).

    Returns dict with "type" key and type-specific dimension keys.
    Also always includes "envelope_w/d/h" for docstring use.
    """
    # ── Priority 1: Parse explicit dimensions from material text ──
    # Cylinder: Φ38×280mm or φ38x280mm
    m_cyl = re.search(r"[Φφ](\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm", material)
    if m_cyl:
        d, h = float(m_cyl.group(1)), float(m_cyl.group(2))
        return {"type": "cylinder", "d": d, "h": h,
                "envelope_w": d, "envelope_d": d, "envelope_h": h}

    # Box: 140×100×55mm (three dimensions with ×)
    m_box = re.search(
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm",
        material)
    if m_box:
        w, d, h = float(m_box.group(1)), float(m_box.group(2)), float(m_box.group(3))
        return {"type": "box", "w": w, "d": d, "h": h,
                "envelope_w": w, "envelope_d": d, "envelope_h": h}

    # Diameter only: Φ90mm (no height) → flat disc
    m_dia = re.search(r"[Φφ](\d+(?:\.\d+)?)\s*mm", material)
    if m_dia:
        d = float(m_dia.group(1))
        h = max(5.0, round(d * 0.25, 1))
        return {"type": "cylinder", "d": d, "h": h,
                "envelope_w": d, "envelope_d": d, "envelope_h": h}

    # ── Priority 2: Keyword heuristics (generic types) ──
    if ("壳体" in name_cn or "筒" in name_cn or "缸" in name_cn):
        return {"type": "cylinder", "d": 50.0, "h": 60.0,
                "envelope_w": 50.0, "envelope_d": 50.0, "envelope_h": 60.0}

    if "法兰" in name_cn and "悬臂" in name_cn:
        return {"type": "disc_arms", "d": 80.0, "arm_l": 40.0, "arm_w": 12.0,
                "t": 20.0, "arm_count": 4,
                "envelope_w": 160.0, "envelope_d": 160.0, "envelope_h": 20.0}

    if "法兰" in name_cn or "盘" in name_cn:
        return {"type": "cylinder", "d": 80.0, "h": 20.0,
                "envelope_w": 80.0, "envelope_d": 80.0, "envelope_h": 20.0}

    if "环" in name_cn or "绝缘段" in name_cn:
        d = 80.0
        return {"type": "ring", "od": d, "id": round(d * 0.75, 1), "h": 5.0,
                "envelope_w": d, "envelope_d": d, "envelope_h": 5.0}

    if "支架" in name_cn and ("L" in name_cn or "抱箍" in name_cn):
        return {"type": "l_bracket", "w": 50.0, "d": 40.0, "h": 25.0, "t": 3.0,
                "envelope_w": 50.0, "envelope_d": 40.0, "envelope_h": 25.0}

    if "支架" in name_cn:
        return {"type": "box", "w": 50.0, "d": 40.0, "h": 25.0,
                "envelope_w": 50.0, "envelope_d": 40.0, "envelope_h": 25.0}

    if "适配" in name_cn:
        return {"type": "cylinder", "d": 60.0, "h": 10.0,
                "envelope_w": 60.0, "envelope_d": 60.0, "envelope_h": 10.0}

    if "板" in name_cn:
        return {"type": "box", "w": 60.0, "d": 40.0, "h": 10.0,
                "envelope_w": 60.0, "envelope_d": 40.0, "envelope_h": 10.0}

    # Default fallback
    return {"type": "box", "w": 40.0, "d": 40.0, "h": 20.0,
            "envelope_w": 40.0, "envelope_d": 40.0, "envelope_h": 20.0}


def _parse_spec_title(spec_path: str) -> tuple:
    """Extract project_name and subsystem_name from CAD_SPEC.md title line.

    Returns (project_name, subsystem_name).
    """
    text = Path(spec_path).read_text(encoding="utf-8")
    m = re.search(r"# CAD Spec\s*[—\-]\s*(.+?)(?:\s*\((.+?)\)|$)", text.split("\n")[0])
    if m:
        subsystem_name = m.group(1).strip()
        project_prefix = m.group(2).strip() if m.group(2) else ""
        return project_prefix, subsystem_name
    return "", ""


def _parse_annotation_meta(spec_path: str, part_name: str) -> dict:
    """Extract §2 annotation metadata for a specific part.

    Returns dict with dim_tolerances, gdt, surfaces filtered for this part.
    """
    from cad_spec_extractors import extract_tolerances
    text = Path(spec_path).read_text(encoding="utf-8")
    tol_data = extract_tolerances(text.splitlines())

    # Filter tolerances — keep all (they may apply to any part)
    dim_tols = tol_data.get("dim_tols", [])
    # Filter GD&T — keep entries matching this part name
    gdt = [g for g in tol_data.get("gdt", [])
           if not g.get("parts") or part_name in g["parts"]]
    # Filter surfaces — keep entries matching this part name
    surfaces = [s for s in tol_data.get("surfaces", [])
                if not s.get("part") or part_name in s["part"]]

    return {
        "dim_tolerances": dim_tols,
        "gdt": gdt,
        "surfaces": surfaces,
    }


def generate_part_files(spec_path: str, output_dir: str, mode: str = "scaffold") -> list:
    """Generate part module scaffolds for all custom-made leaf parts.

    Args:
        mode: "scaffold" (skip existing), "force" (overwrite existing)

    Returns list of generated file paths.
    """
    parts = parse_bom_tree(spec_path)
    generated = []
    skipped = []

    # Parse project/subsystem name from spec title
    project_name, subsystem_name = _parse_spec_title(spec_path)

    # Parse §2 annotation metadata (once for all parts)
    try:
        full_meta = _parse_annotation_meta(spec_path, "")
    except Exception:
        full_meta = {"dim_tolerances": [], "gdt": [], "surfaces": []}

    # Parse part features from §2/§3/§4/§8 (once for all parts)
    try:
        from cad_spec_extractors import extract_part_features
        spec_text = Path(spec_path).read_text(encoding="utf-8")
        all_features = extract_part_features(spec_text.splitlines(), parts)
    except Exception:
        all_features = {}

    # Parse §6 assembly pose for coordinate system auto-fill
    # Reuse gen_assembly.py's existing parsing — single data source (design doc)
    all_poses = {}  # {part_no: {axis_dir, z, r, theta, ...}}
    try:
        from gen_assembly import parse_assembly_pose, _extract_all_layer_poses
        pose = parse_assembly_pose(spec_path)
        all_poses = _extract_all_layer_poses(pose, parts)
    except Exception:
        pass

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

        geom = _guess_geometry(p["name_cn"], p["material"])

        # Derive material_type
        from cad_spec_defaults import classify_material_type, SURFACE_RA
        mat_type = classify_material_type(p["material"])
        if mat_type is None:
            print(f"  WARNING: Cannot classify material '{p['material']}' for {p['part_no']}, "
                  f"defaulting to 'al'")
            mat_type = "al"

        # Per-part annotation meta
        part_meta = _parse_annotation_meta(spec_path, p["name_cn"])

        # Default Ra from material type
        default_ra = SURFACE_RA.get(mat_type, SURFACE_RA.get("default", 3.2))

        # Flatten geometry dict for template: geom_type, geom_d, geom_h, etc.
        geom_vars = {f"geom_{k}": v for k, v in geom.items() if k != "type"}
        geom_vars["geom_type"] = geom["type"]

        # Part features from cross-referencing §2/§3/§4/§8
        part_features = all_features.get(p["part_no"], [])
        # Determine if section view is needed (part has internal features)
        needs_section = bool(part_features) and any(
            f["type"] in ("through_hole", "counterbore", "pocket")
            for f in part_features
        )

        # Coordinate system — auto-fill from §6.2 if available
        coord = _derive_coord_system(p["part_no"], p["name_cn"], geom, all_poses)

        content = template.render(
            part_name_cn=p["name_cn"],
            part_no=p["part_no"],
            source_ref=f"CAD_SPEC.md §5 BOM",
            material=p["material"],
            func_name=func_name,
            param_imports=[],  # Empty — user adds specific params
            envelope_w=geom["envelope_w"],
            envelope_d=geom["envelope_d"],
            envelope_h=geom["envelope_h"],
            weight="?",
            has_mounting_holes=False,
            has_dxf=True,
            # Coordinate system — from §6.2 (auto-filled if data exists)
            local_origin_desc=coord.get("local_origin_desc"),
            principal_axis_desc=coord.get("principal_axis_desc"),
            assembly_orient_desc=coord.get("assembly_orient_desc"),
            axis_source_ref=coord.get("axis_source_ref"),
            # Geometry type dispatch
            **geom_vars,
            # Part features — from cross-referencing §2/§3/§4/§8
            features=part_features,
            needs_section_view=needs_section,
            # Annotation metadata — from CAD_SPEC.md §2 + BOM material
            material_type=mat_type,
            project_name=project_name,
            subsystem_name=subsystem_name,
            dim_tolerances=part_meta["dim_tolerances"],
            gdt_entries=part_meta["gdt"],
            surface_ra=part_meta["surfaces"],
            default_ra=default_ra,
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
