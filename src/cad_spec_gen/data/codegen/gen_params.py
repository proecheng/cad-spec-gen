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

def render_params_py(params: list, spec_path: str, design_doc: str = "") -> str:
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
        derived_params=[],
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
    print(f"[gen_params] Parsed {len(params)} parameters from {os.path.basename(spec_path)}")

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
        content = render_params_py(params, spec_path, args.design_doc)
        Path(output_path).write_text(content, encoding="utf-8")
        print(f"[gen_params] Generated: {output_path}")

    return params


if __name__ == "__main__":
    main()
