#!/usr/bin/env python3
"""
Code Generator: CAD_SPEC.md → params.py

Reads §1 (全局参数表) from a CAD_SPEC.md and generates a parametric
dimensions file (params.py) using Jinja2 templates.

Modes:
  - scaffold: Generate new params.py from scratch (will NOT overwrite existing)
  - update:   Diff-merge changed values into an existing params.py
  - force:    Overwrite existing params.py entirely

Usage:
    python codegen/gen_params.py cad/end_effector/CAD_SPEC.md
    python codegen/gen_params.py cad/end_effector/CAD_SPEC.md --mode update
    python codegen/gen_params.py cad/end_effector/CAD_SPEC.md --mode force
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root on path
_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ── CAD_SPEC.md Parser ────────────────────────────────────────────────────────

def parse_spec_params(spec_path: str) -> list:
    """Parse §1 全局参数表 from CAD_SPEC.md.

    Returns list of dicts: {name, value, unit, tolerance, source, remark}
    """
    text = Path(spec_path).read_text(encoding="utf-8")
    lines = text.splitlines()

    params = []
    in_section = False
    header_found = False

    for line in lines:
        # Detect §1 start
        if re.match(r"##\s*1\.\s*全局参数表", line):
            in_section = True
            continue

        # Detect next section (§2, §3, etc.)
        if in_section and re.match(r"##\s*[2-9]", line):
            break

        if not in_section:
            continue

        # Skip table header and separator
        if "参数名" in line and "值" in line:
            header_found = True
            continue
        if re.match(r"\|\s*---", line):
            continue

        # Parse table rows
        if header_found and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            # Remove empty first/last from split
            cells = [c for c in cells if c or cells.index(c) not in (0, len(cells)-1)]
            if len(cells) < 2:
                continue

            # Pad to 6 columns
            while len(cells) < 6:
                cells.append("")

            name, value, unit, tol, source, remark = cells[:6]

            # Skip empty rows or computed summary rows
            if not name or name.startswith("（"):
                continue

            params.append({
                "name": name,
                "value": value,
                "unit": unit,
                "tolerance": tol,
                "source": source,
                "remark": remark,
            })

    return params


def parse_assembly_params(spec_path: str) -> list:
    """Parse §6.2 装配层叠 from CAD_SPEC.md for assembly-level derived params.

    Extracts:
    - MOUNT_CENTER_R from R=XXmm in offset column
    - STATION_ANGLES list from θ=XXX° in offset column
    - PEEK/motor/adapter geometry from layer descriptions
    """
    text = Path(spec_path).read_text(encoding="utf-8")
    lines = text.splitlines()

    derived = []
    in_section = False
    header_found = False
    station_angles = []
    mount_r = None

    for line in lines:
        if re.match(r"###?\s*6\.2\s", line) or "装配层叠" in line:
            in_section = True
            continue
        if in_section and re.match(r"##\s*[78]", line):
            break
        if not in_section:
            continue

        if "层级" in line and "零件" in line:
            header_found = True
            continue
        if re.match(r"\|\s*---", line):
            continue

        if header_found and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c != ""]
            if len(cells) < 5:
                continue

            offset_col = cells[4] if len(cells) > 4 else ""

            # Extract R=XXmm (mount center radius)
            m_r = re.search(r"R\s*=\s*(\d+(?:\.\d+)?)\s*mm", offset_col)
            if m_r and mount_r is None:
                mount_r = float(m_r.group(1))

            # Extract θ=XXX° (station angles)
            m_theta = re.search(r"θ\s*=\s*(\d+(?:\.\d+)?)\s*°", offset_col)
            if m_theta:
                station_angles.append(float(m_theta.group(1)))

            # Extract Z offsets for key layers
            m_z = re.search(r"Z\s*=\s*([+\-]?\d+(?:\.\d+)?)\s*mm", offset_col)
            if m_z:
                z_val = float(m_z.group(1))
                layer_name = cells[1] if len(cells) > 1 else ""
                if "电机" in layer_name or "减速器" in layer_name:
                    derived.append({
                        "name": "MOTOR_L",
                        "expr": str(abs(z_val)),
                        "remark": f"mm — 电机+减速器总长 (§6.2 {offset_col.strip()})",
                    })

    if mount_r is None:
        # Fallback 1: broader R= scan across all of §6.2 (not just offset column)
        in_sec2 = False
        for line in lines:
            if re.match(r"###?\s*6\.2\s", line) or "装配层叠" in line:
                in_sec2 = True
                continue
            if in_sec2 and re.match(r"##\s*[78]", line):
                break
            if not in_sec2:
                continue
            m_r2 = re.search(r"\bR\s*=\s*(\d+(?:\.\d+)?)\s*mm", line)
            if m_r2:
                mount_r = float(m_r2.group(1))
                break

    if mount_r is None:
        # Fallback 2: derive from §6.4 envelope — use half of largest cylindrical diameter
        try:
            from codegen.gen_assembly import parse_envelopes
            envs_raw = parse_envelopes(spec_path)
            envs = {pno: (e["dims"] if isinstance(e, dict) else e)
                    for pno, e in envs_raw.items()}
            if envs:
                max_dia = max((w for w, d, h in envs.values() if abs(w - d) < 0.1), default=None)
                if max_dia:
                    mount_r = round(max_dia / 2.0, 1)
                    print(f"  [gen_params] MOUNT_CENTER_R: no R= found in §6.2, "
                          f"derived {mount_r}mm from §6.4 envelope (half of Φ{max_dia}mm)")
        except Exception:
            pass

    if mount_r is not None:
        derived.insert(0, {
            "name": "MOUNT_CENTER_R",
            "expr": str(int(mount_r) if mount_r == int(mount_r) else mount_r),
            "remark": "mm — 工位安装面中心到旋转轴距离 (§6.2)",
        })

    if station_angles:
        angles_str = "[" + ", ".join(str(int(a) if a == int(a) else a) for a in station_angles) + "]"
        derived.append({
            "name": "STATION_ANGLES",
            "expr": angles_str,
            "remark": f"° — {len(station_angles)}工位角度 (§6.2)",
        })

        # M5: Validate station_angles count against BOM assembly count
        try:
            from codegen.gen_build import parse_bom_tree
            bom_parts = parse_bom_tree(spec_path)
            num_assemblies = sum(1 for p in bom_parts
                                 if p.get("is_assembly") and p.get("level", 0) == 1
                                 and not p.get("exclude"))
            if num_assemblies > 0 and len(station_angles) != num_assemblies:
                print(f"  WARNING: {len(station_angles)} station angles vs "
                      f"{num_assemblies} top-level assemblies in BOM — "
                      f"check §6.2 θ= entries")
        except Exception:
            pass

    return derived


def _normalize_param_name(raw_name: str) -> str:
    """Convert raw parameter name to Python constant name.

    Rules:
    - Already UPPER_SNAKE → keep as-is
    - Has Chinese → prefix with PARAM_ + source line
    - Contains spaces/hyphens → replace with _
    """
    name = raw_name.strip()

    # Already valid Python constant
    if re.match(r"^[A-Z][A-Z0-9_]*$", name):
        return name

    # Clean up
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^A-Za-z0-9_]", "", name)

    if name:
        return name.upper()
    return None


def _parse_value(raw_value: str):
    """Parse a raw value string into Python literal.

    Returns (python_repr, is_numeric).
    """
    v = raw_value.strip()
    if not v:
        return "None", False

    # Try numeric
    try:
        if "." in v:
            return str(float(v)), True
        else:
            return str(int(v)), True
    except ValueError:
        pass

    # String — quote it
    return f'"{v}"', False


def _group_params(params: list) -> list:
    """Group parameters by source section.

    Groups by source line prefix (e.g., L25-L38 → one group).
    """
    groups = []
    current_group = {"title": "Parameters", "params": []}

    prev_source_num = 0
    for p in params:
        # Extract source line number
        m = re.search(r"L(\d+)", p.get("source", ""))
        source_num = int(m.group(1)) if m else 0

        # New group if gap > 20 lines
        if source_num > 0 and prev_source_num > 0 and (source_num - prev_source_num) > 20:
            if current_group["params"]:
                groups.append(current_group)
            current_group = {"title": f"Section (lines {source_num}+)", "params": []}

        py_name = _normalize_param_name(p["name"])
        if not py_name:
            continue

        py_value, is_numeric = _parse_value(p["value"])

        current_group["params"].append({
            "name": py_name,
            "value": py_value,
            "unit": p.get("unit", ""),
            "remark": p.get("remark", ""),
            "source": p.get("source", ""),
            "tolerance": p.get("tolerance", ""),
            "is_numeric": is_numeric,
        })

        prev_source_num = source_num

    if current_group["params"]:
        groups.append(current_group)

    return groups


# ── Render with Jinja2 ────────────────────────────────────────────────────────

def render_params_py(params: list, spec_path: str, design_doc: str = "",
                     derived_params: list = None) -> str:
    """Render params.py content from parsed parameters."""
    import jinja2

    template_dir = os.path.join(_PROJECT_ROOT, "templates")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    template = env.get_template("params.py.j2")
    groups = _group_params(params)

    return template.render(
        subsystem_name=Path(spec_path).parent.name,
        source_file=spec_path,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        design_doc=design_doc or "design document",
        total_lines="?",
        param_groups=groups,
        derived_params=derived_params or [],
    )


# ── Diff-merge for update mode ────────────────────────────────────────────────

def update_params_py(existing_path: str, new_params: list) -> tuple:
    """Update values in existing params.py without destroying structure.

    Returns (updated_content, changelog).
    """
    content = Path(existing_path).read_text(encoding="utf-8")
    lines = content.splitlines()
    changelog = []

    # Build lookup from new params
    new_lookup = {}
    for p in new_params:
        py_name = _normalize_param_name(p["name"])
        if py_name:
            new_lookup[py_name] = p

    updated_lines = []
    for line in lines:
        # Match: PARAM_NAME = value  # comment
        m = re.match(r"^(\s*)([A-Z][A-Z0-9_]*)\s*=\s*(.+?)(\s*#.*)?$", line)
        if m:
            indent, name, old_val, comment = m.groups()
            comment = comment or ""

            if name in new_lookup:
                new_val_raw = new_lookup[name]["value"]
                new_py, _ = _parse_value(new_val_raw)

                # Strip trailing whitespace from old value for comparison
                old_val_clean = old_val.strip()

                if old_val_clean != new_py:
                    # Value changed — update
                    padding = max(1, 30 - len(name) - len(new_py))
                    updated_lines.append(
                        f"{indent}{name} = {new_py}{' ' * padding}{comment}")
                    changelog.append(f"  {name}: {old_val_clean} → {new_py}")
                else:
                    updated_lines.append(line)

                del new_lookup[name]  # Mark as processed
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    # Report unmatched new params
    if new_lookup:
        changelog.append(f"\n  New params not in existing file ({len(new_lookup)}):")
        for name in sorted(new_lookup.keys()):
            changelog.append(f"    + {name} = {new_lookup[name]['value']}")

    return "\n".join(updated_lines) + "\n", changelog


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate params.py from CAD_SPEC.md §1")
    parser.add_argument("spec", help="Path to CAD_SPEC.md")
    parser.add_argument("--output", "-o", default=None,
                        help="Output path (default: same dir as spec)")
    parser.add_argument("--mode", choices=["scaffold", "update", "force"],
                        default="force",
                        help="force=overwrite (default), scaffold=new only, update=diff-merge (deprecated)")
    parser.add_argument("--design-doc", default=None,
                        help="Original design document path (for header comment)")
    args = parser.parse_args()

    spec_path = os.path.abspath(args.spec)
    if not os.path.exists(spec_path):
        print(f"ERROR: {spec_path} not found")
        sys.exit(1)

    output_path = args.output or os.path.join(os.path.dirname(spec_path), "params.py")

    # Parse spec
    params = parse_spec_params(spec_path)
    derived = parse_assembly_params(spec_path)
    print(f"[gen_params] Parsed {len(params)} parameters + {len(derived)} assembly-derived from {os.path.basename(spec_path)}")

    if args.mode == "update" and os.path.exists(output_path):
        # Diff-merge mode
        content, changelog = update_params_py(output_path, params)
        if changelog:
            print(f"[gen_params] Updated {len(changelog)} parameter(s):")
            for c in changelog:
                print(c)
            Path(output_path).write_text(content, encoding="utf-8")
            print(f"[gen_params] Written: {output_path}")
        else:
            print("[gen_params] No changes detected — params.py is up to date")

    elif args.mode == "scaffold" and os.path.exists(output_path):
        print(f"[gen_params] SKIP: {output_path} already exists (use --mode update or --mode force)")

    else:
        # Generate from scratch
        content = render_params_py(params, spec_path, args.design_doc,
                                   derived_params=derived)
        Path(output_path).write_text(content, encoding="utf-8")
        print(f"[gen_params] Generated: {output_path}")

    return params


if __name__ == "__main__":
    main()
