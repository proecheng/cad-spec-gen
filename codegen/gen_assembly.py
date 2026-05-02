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
from codegen.library_routing import (
    build_library_part_query,
    is_library_routed_row,
    library_make_function,
    library_module_name,
)
from parts_resolver import default_resolver

# Categories that get simplified CadQuery geometry. Must stay in sync with
# _GENERATORS in codegen/gen_std_parts.py.
_STD_PART_CATEGORIES = {"motor", "reducer", "spring", "bearing", "sensor",
                        "pump", "connector", "seal", "tank", "transmission",
                        "other"}


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
        # Terminate §6.2 layer parsing when any new (sub)section starts.
        # Without this, §6.3 零件级定位 and §6.4 包络尺寸 tables are
        # incorrectly parsed as layer rows, which corrupts layer_poses.
        if line.startswith("### ") and "装配层叠" not in line and "坐标系定义" not in line:
            in_layers = False
            in_coord = False
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
                                   part_name: str = "",
                                   axis_dir_parsed: list = None) -> tuple:
    """Convert §6.2 axis_dir to CadQuery rotation code.

    Prefers axis_dir_parsed (structured data from cad_spec_extractors) when
    available; falls back to string matching on axis_dir text.

    Returns (transform_code, doc_ref) or (None, None) if no rotation needed.
    """
    # ── Priority 1: Use pre-parsed structured data if available ──
    if axis_dir_parsed:
        matched = None
        if part_name:
            for entry in axis_dir_parsed:
                kw = entry.get("keyword", "")
                if kw and kw in part_name:
                    matched = entry
                    break
        if not matched:
            matched = axis_dir_parsed[0] if axis_dir_parsed else None
        if matched and matched.get("rotation"):
            rot = matched["rotation"]
            axis = rot["axis"]
            angle = rot["angle"]
            code = f"{var_name}.rotate((0,0,0), ({axis[0]},{axis[1]},{axis[2]}), {angle})"
            return code, f"axis horizontal per §6.2: {axis_dir[:60]}"
        return None, None

    # ── Priority 2: Fall back to string matching ──
    if not axis_dir:
        return None, None

    text = axis_dir.strip()

    # Multi-clause matching by part name keywords
    if part_name and ("，" in text or "," in text):
        clauses = re.split(r"[，,]", text)
        for clause in clauses:
            keywords = [part_name[:n] for n in (3, 2) if len(part_name) >= n]
            if len(part_name) >= 4:
                keywords.append(part_name[-2:])
            if any(kw in clause for kw in keywords if kw):
                text = clause.strip()
                break

    if any(k in text for k in ["盘面∥XY", "环∥XY", "弧形∥XY"]):
        return None, None
    if any(k in text for k in ["沿-Z", "沿Z", "垂直", "⊥法兰"]):
        return None, None
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
            # Extract the key identifier (e.g. "GIS-EE-002" or "SLP-100")
            m = re.search(r"[A-Z]+-(?:[A-Z]+-)?[A-Z0-9]+(?:-\d+)?", part)
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
    "transmission": ("C_STD_TRANS", 0.70, 0.42, 0.20),  # bronze/steel
    "other":     ("C_STD_OTHER",   0.45, 0.45, 0.50),  # neutral grey
}




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


def _match_bom_by_keywords(part_text: str, bom_parts: list,
                           scope_prefix: str = "") -> list:
    """Match §6.2 part_text against BOM entries by name keywords.

    Splits part_text into Chinese character runs and tries to match
    each BOM entry's name_cn. Returns list of matched part_no strings.

    scope_prefix: if set (e.g. "GIS-EE-001"), only match parts whose
    part_no starts with this prefix. Prevents cross-assembly leaking
    (e.g. "减速器" in L2 matching both GIS-EE-001-06 and GIS-EE-004-04).
    """
    keywords = re.findall(r"[\u4e00-\u9fff]{2,}", part_text)
    if not keywords:
        return []
    matched = []
    for part in bom_parts:
        if part.get("is_assembly"):
            continue
        if scope_prefix and not part["part_no"].startswith(scope_prefix + "-"):
            continue
        name = part.get("name_cn", "")
        for kw in keywords:
            if kw in name:
                matched.append(part["part_no"])
                break
    return matched


def _extract_all_layer_poses(pose: dict, bom_parts: list = None) -> dict:
    """Extract per-part positioning from §6.2 layer stacking table.

    Captures ALL positioning data including Z-only offsets.
    For rows without a GIS-XX-NNN part number, falls back to
    name-keyword matching against bom_parts.

    Returns {part_no: {"z": float|None, "r": float|None, "theta": float|None,
                        "axis_dir": str, "is_origin": bool}}.
    """
    if bom_parts is None:
        bom_parts = []
    result = {}

    # Track current assembly context for scoped keyword matching.
    # §6.2 rows are ordered by layer level; assembly-level rows (L5a, L5b...)
    # establish context, and sub-part rows inherit it.
    current_assy_prefix = ""

    for layer in pose.get("layers", []):
        part_text = layer.get("part", "")
        offset_text = layer.get("offset", "")
        axis_dir = layer.get("axis_dir", "")

        # Detect assembly-level rows to set scoping context.
        # Accept both 3-segment and 4-segment part_nos:
        # "(GIS-EE-001-08)" → use parent prefix "GIS-EE-001"
        # "(GIS-EE-002)" → use as-is
        m_assy = re.search(r"\(([A-Z]+-[A-Z]+-\d+(?:-\d+)?)\)", part_text)
        if m_assy:
            full_pno = m_assy.group(1)
            # Strip the leaf segment (e.g. -08) to get the assembly prefix
            parent_match = re.match(r"([A-Z]+-[A-Z]+-\d+)", full_pno)
            current_assy_prefix = parent_match.group(1) if parent_match else full_pno

        # Skip rows with no useful offset
        if not offset_text or offset_text.strip() in ("—", "-", ""):
            m_pno = re.search(r"([A-Z]+-(?:[A-Z]+-)?[A-Z0-9]+(?:-\d+)?)", part_text)
            if m_pno:
                result.setdefault(m_pno.group(1), {
                    "z": None, "r": None, "theta": None,
                    "axis_dir": axis_dir, "is_origin": False})
            continue

        entry = {"z": None, "r": None, "theta": None,
                 "axis_dir": axis_dir, "is_origin": False}

        if "基准" in offset_text or "原点" in offset_text:
            entry["z"] = 0.0
            entry["is_origin"] = True

        m_z = re.search(r"Z\s*=\s*([+-]?\d+(?:\.\d+)?)\s*mm", offset_text)
        if m_z:
            entry["z"] = float(m_z.group(1))
            # R5: "Z=+73mm(向上)" means top-of-part, not bottom
            if "向上" in offset_text:
                entry["z_is_top"] = True

        if entry["z"] is None:
            m_z0 = re.search(r"Z\s*=\s*0(?:\s*\(|$)", offset_text)
            if m_z0:
                entry["z"] = 0.0

        m_r = re.search(r"R\s*[=≈]\s*(\d+(?:\.\d+)?)\s*mm", offset_text)
        if m_r:
            entry["r"] = float(m_r.group(1))

        m_theta = re.search(r"θ\s*=\s*(\d+(?:\.\d+)?)\s*°?", offset_text)
        if m_theta:
            entry["theta"] = float(m_theta.group(1))

        m_pno = re.search(r"([A-Z]+-(?:[A-Z]+-)?[A-Z0-9]+(?:-\d+)?)", part_text)
        if m_pno:
            result[m_pno.group(1)] = entry
        else:
            # R2: Scope keyword matching to current assembly to prevent
            # cross-assembly leaking (e.g. "减速器" matching parts in
            # both GIS-EE-001 and GIS-EE-004)
            matched_pnos = _match_bom_by_keywords(
                part_text, bom_parts, scope_prefix=current_assy_prefix)
            for pno in matched_pnos:
                result[pno] = dict(entry)

    return result


def _parse_dims_text(text: str):
    """Extract (w, d, h) envelope from text with dimension specs.
    Returns (w, d, h) tuple or None.
    """
    if not text:
        return None
    m = re.search(r"[Φφ](\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm", text)
    if m:
        d, h = float(m.group(1)), float(m.group(2))
        return (d, d, h)
    m = re.search(r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm", text)
    if m:
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    m = re.search(r"[Φφ](\d+(?:\.\d+)?)\s*mm", text)
    if m:
        d = float(m.group(1))
        return (d, d, max(5.0, round(d * 0.25, 1)))
    return None


def parse_envelopes(spec_path: str) -> dict:
    """Parse §6.4 envelope dimensions table from CAD_SPEC.md.

    Returns:
        {part_no: {"dims": (w, d, h), "granularity": str}}

    The `dims` tuple is read from positional `cells[3]` to preserve the
    historical column layout. `granularity` is read by header name so new
    audit columns can be appended without breaking this parser. Missing
    粒度 column defaults to 'part_envelope' for backward compat with
    legacy §6.4 tables that predate the walker.
    """
    try:
        text = Path(spec_path).read_text(encoding="utf-8")
    except Exception:
        return {}

    envelopes: dict = {}
    in_section = False
    header_cells: list[str] | None = None

    for line in text.splitlines():
        if "### 6.4" in line and "包络" in line:
            in_section = True
            header_cells = None
            continue
        if in_section and (line.startswith("## ") or
                          (line.startswith("### ") and "6.4" not in line)):
            break
        if not in_section or not line.startswith("|") or "---" in line:
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = cells[1:-1] if len(cells) >= 2 else cells

        # Header row: capture for named-column lookup below.
        if cells and cells[0] == "料号":
            header_cells = cells
            continue
        if len(cells) < 4:
            continue

        pno = cells[0]
        if not re.match(r"[A-Z]+-", pno):
            continue

        # dims: positional cells[3] (unchanged) — keep walker output
        # backward-compatible with this parser.
        dims_text = cells[3] if len(cells) > 3 else ""
        parsed = _parse_dims_text(dims_text + " mm")
        if not parsed:
            continue

        # granularity: header-name lookup, default part_envelope.
        granularity = "part_envelope"
        if header_cells and "粒度" in header_cells:
            gran_idx = header_cells.index("粒度")
            if gran_idx < len(cells):
                granularity = cells[gran_idx] or "part_envelope"

        envelopes[pno] = {"dims": parsed, "granularity": granularity}

    return envelopes


def parse_constraints(spec_path: str) -> list:
    """Parse §9.2 assembly constraint declarations from CAD_SPEC.md.

    Returns list of dicts:
        {"id": "C01", "type": "contact", "part_a": "...", "part_b": "...",
         "params": "gap=0", "source": "...", "confidence": "high"}
    """
    try:
        text = Path(spec_path).read_text(encoding="utf-8")
    except Exception:
        return []

    constraints = []
    in_section = False

    for line in text.splitlines():
        if "### 9.2" in line and "约束" in line:
            in_section = True
            continue
        if in_section and (line.startswith("## ") or
                          (line.startswith("### ") and "9.2" not in line)):
            break
        if not in_section or not line.startswith("|") or "---" in line:
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = cells[1:-1] if len(cells) >= 2 else cells
        if len(cells) < 5 or cells[0] == "约束ID":
            continue

        constraints.append({
            "id": cells[0],
            "type": cells[1],
            "part_a": cells[2] if len(cells) > 2 else "",
            "part_b": cells[3] if len(cells) > 3 else "",
            "params": cells[4] if len(cells) > 4 else "",
            "source": cells[5] if len(cells) > 5 else "",
            "confidence": cells[6] if len(cells) > 6 else "",
        })

    return constraints




def _infer_stack_direction(axis_dir: str) -> tuple:
    """Convert axis_dir text to unit stacking vector. Default: (0,0,-1)."""
    if not axis_dir:
        return (0, 0, -1)
    if any(k in axis_dir for k in ["沿+Z", "+Z", "向上"]):
        return (0, 0, 1)
    if any(k in axis_dir for k in ["沿-Z", "-Z", "向下", "垂直"]):
        return (0, 0, -1)
    if any(k in axis_dir for k in ["∥XY", "水平", "径向"]):
        return (1, 0, 0)
    return (0, 0, -1)


def _match_axis_clause(axis_dir: str, part_name: str) -> str:
    """Find axis_dir sub-clause for a specific part.
    E.g. "壳体轴沿-Z，储罐轴∥XY" + "储罐" → "储罐轴∥XY".
    Returns matched clause or empty string.
    """
    if not axis_dir or not part_name:
        return ""
    clauses = re.split(r"[，,]", axis_dir)
    if len(clauses) <= 1:
        return ""
    for clause in clauses:
        for n in (3, 2):
            if len(part_name) >= n and part_name[:n] in clause:
                return clause.strip()
    return ""


def _part_height_along(dims, direction: tuple) -> float:
    """Part extent along stacking direction. Fallback 20mm."""
    if dims is None:
        return 20.0
    w, d, h = dims
    ax, ay, az = abs(direction[0]), abs(direction[1]), abs(direction[2])
    if az >= ax and az >= ay:
        return h
    if ax >= ay:
        return w
    return d


def _stack_sort_key(child: dict, dims_map: dict, direction: tuple) -> tuple:
    """Sort: custom bodies first, then by extent descending."""
    is_custom = "自制" in child.get("make_buy", "")
    is_body = any(k in child["name_cn"] for k in ("壳体", "本体", "支架", "框架", "基座"))
    extent = _part_height_along(dims_map.get(child["part_no"]), direction)
    return (-int(is_custom), -int(is_body), -extent)


def _is_render_excluded(part_no: str, excluded_part_nos: set,
                        excluded_assembly_nos: set = None) -> bool:
    """Return True when a BOM part is excluded from generated assembly."""
    excluded_assembly_nos = excluded_assembly_nos or set()
    return (
        part_no in excluded_part_nos
        or any(part_no == p or part_no.startswith(p + "-")
               for p in excluded_assembly_nos)
    )


def _resolve_child_offsets(parts: list, layer_poses: dict,
                           spec_path: str = "") -> dict:
    """Compute per-part local offsets. §6.3 data wins over auto-stacking.

    Per-part axis_dir sub-clause matching: if axis_dir has comma-separated
    clauses, each child matches its own clause for stacking direction.

    cursor is always a positive scalar distance along direction vector.
    offset_vector = direction * cursor.

    Returns {part_no: (dx, dy, dz)}.
    """
    result = {}

    # --- NEW: Try §6.3 part-level positions first ---
    part_positions = _parse_part_positions(spec_path) if spec_path else {}

    # Hoist file-based lookups before the assembly loop (parse once, reuse).
    # parse_envelopes() now returns {pno: {"dims": (w,d,h), "granularity": str}};
    # unwrap to bare tuples so all positional indexing below is unchanged.
    _envelopes_raw = parse_envelopes(spec_path) if spec_path else {}
    _envelopes_cache = {pno: (e["dims"] if isinstance(e, dict) else e)
                        for pno, e in _envelopes_raw.items()}
    constraints = parse_constraints(spec_path) if spec_path else []
    render_exclusions = (parse_render_exclusions(spec_path) if spec_path
                         else {"parts": set(), "assemblies": set()})
    excluded_part_nos = render_exclusions["parts"]

    assemblies = [p for p in parts if p["is_assembly"]]
    children_of = {}

    # Detect flat BOM: assembly with part_no like "UNKNOWN" or no dash-hierarchy
    # In flat BOM, all non-assembly parts belong to each assembly
    non_assy_parts = [p for p in parts if not p["is_assembly"]]
    for assy in assemblies:
        assy_pno = assy["part_no"]
        # Try hierarchical match first (GIS-EE-001 → children GIS-EE-001-xx)
        hier_children = [
            p for p in non_assy_parts
            if p["part_no"].startswith(assy_pno + "-")
        ]
        if hier_children:
            children_of[assy_pno] = hier_children
        else:
            # Flat BOM: all non-assembly parts are children of this assembly
            children_of[assy_pno] = non_assy_parts

    for assy in assemblies:
        prefix = assy["part_no"]
        children = children_of.get(prefix, [])
        if not children:
            continue

        assy_pose = layer_poses.get(prefix, {})
        assy_axis_dir = assy_pose.get("axis_dir", "")
        default_direction = _infer_stack_direction(assy_axis_dir)

        # Detect orphan assembly (no §6.2 positioning at all).
        # An assembly whose *children* have explicit §6.2 positions is NOT
        # orphan, even if the assembly-level row is missing from §6.2.
        has_positioned_children = any(
            layer_poses.get(c["part_no"], {}).get("z") is not None
            or layer_poses.get(c["part_no"], {}).get("is_origin")
            for c in children
        )
        is_orphan = (not has_positioned_children and
                     assy_pose.get("r") is None and
                     assy_pose.get("theta") is None and
                     assy_pose.get("z") is None and
                     not assy_pose.get("is_origin", False))

        if is_orphan:
            default_direction = (0, 0, 1)  # orphans go upward to avoid overlap

        # R1: Compute reasonable Z-range for outlier detection.
        # Include 20mm default for parts without §6.4 envelopes so the
        # threshold scales with assembly size, not with envelope coverage.
        _child_pnos = {c["part_no"] for c in children}
        _total_h = sum(
            _envelopes_cache[pno][2] if pno in _envelopes_cache else 20.0
            for pno in _child_pnos
        )
        _max_span = max(_total_h * 1.5, 150.0)  # at least 150mm

        # Build name→part_no resolver for constraint matching
        _name_to_pno = {}
        for p in parts:
            _name_to_pno[p["name_cn"]] = p["part_no"]
            # Also index by short name prefixes (2-4 chars)
            for n in (4, 3, 2):
                if len(p["name_cn"]) >= n:
                    _name_to_pno.setdefault(p["name_cn"][:n], p["part_no"])

        def _resolve_constraint_ref(name_text: str) -> str:
            """Resolve constraint part_a/part_b text to a part_no."""
            # Direct part_no match
            if re.match(r"[A-Z]+-", name_text):
                return name_text
            # Exact name match
            if name_text in _name_to_pno:
                return _name_to_pno[name_text]
            # Substring match (e.g. "PEEK段" matches "PEEK绝缘段")
            for pname, ppno in _name_to_pno.items():
                if name_text in pname or pname in name_text:
                    return ppno
            return ""

        auto_queue = []
        _z_top_deferred = []  # (cpno, child, z_top) for z_is_top group stacking
        for child in children:
            cpno = child["part_no"]

            # P0a: §9.2 exclude_stack means "not rendered in local stack".
            # Do not turn it into a zero-offset real part; that creates
            # floating connector/cable geometry downstream.
            if _is_render_excluded(cpno, excluded_part_nos):
                continue

            # §6.3 lookup (highest priority, with outlier guard).
            # Explicit positions from design doc serial chains win over
            # auto-generated constraints (C2 contact, stack_on, etc).
            if cpno in part_positions:
                pos = part_positions[cpno]
                if pos.get("z") is not None:
                    # R1: Guard against outlier §6.3 values, but trust
                    # high-confidence serial_chain entries even if they
                    # exceed _max_span (sparse envelope coverage can make
                    # the threshold artificially tight).
                    if (pos.get("confidence") == "high"
                            or abs(pos["z"]) <= _max_span):
                        result[cpno] = (0, 0, pos["z"])
                        continue
                    # else: outlier — fall through to auto-stack
            # Existing: explicit §6.2 layer pose (overrides §9.2 constraints
            # because §6.2 contains designer-specified absolute offsets)
            if cpno in layer_poses and layer_poses[cpno].get("z") is not None:
                z = layer_poses[cpno]["z"]
                if layer_poses[cpno].get("z_is_top"):
                    # Defer z_is_top parts — resolve as group after main loop
                    _z_top_deferred.append((cpno, child, z))
                else:
                    result[cpno] = (0, 0, z)
            else:
                # §9.2 contact/stack_on — place relative to an already-
                # positioned reference part. Only consulted when neither
                # §6.3 nor §6.2 provided an explicit Z for this child.
                contact_placed = False
                for c in constraints:
                    if c["type"] not in ("contact", "stack_on"):
                        continue
                    ref_a = _resolve_constraint_ref(c["part_a"])
                    ref_b = _resolve_constraint_ref(c["part_b"])
                    if ref_a != cpno and ref_b != cpno:
                        continue
                    other_pno = ref_b if ref_a == cpno else ref_a
                    if other_pno not in result:
                        continue
                    other_z = result[other_pno][2]
                    other_h = _envelopes_cache.get(
                        other_pno, (0, 0, 15))[2]
                    my_h = _envelopes_cache.get(cpno, (0, 0, 15))[2]
                    if c["type"] == "stack_on":
                        z = other_z + other_h
                    else:
                        _dz = (default_direction[2]
                               if default_direction[2] != 0 else -1)
                        if _dz < 0:
                            z = other_z - my_h
                        else:
                            z = other_z + other_h
                    result[cpno] = (0, 0, round(z, 1))
                    contact_placed = True
                    break
                if contact_placed:
                    continue

                # R4: Skip cable/connector — place at assembly origin
                cat = classify_part(child["name_cn"], child.get("material", ""))
                if cat in ("cable", "connector"):
                    result[cpno] = (0, 0, 0)
                    continue

                # R5: Fastener accessories (washers, lock rings) are tiny
                # parts paired with bolts. Without explicit positioning they
                # auto-stack into nonsense locations. Snap them to the same Z
                # as the part they accessorize (matched by name) or to the
                # assembly's reference origin.
                _name = child["name_cn"]
                _is_accessory = (
                    cat == "spring"
                    and any(kw in _name for kw in
                            ("垫圈", "垫片", "锁圈", "卡圈", "washer"))
                )
                if _is_accessory:
                    # Find the part this accessorizes: nearest already-placed
                    # custom part in the same assembly (e.g. PEEK ring for
                    # the disc spring washer that pairs with PEEK→flange M3
                    # bolts).
                    snap_z = 0.0
                    for other_pno, other_off in result.items():
                        if not other_pno.startswith(prefix + "-"):
                            continue
                        if other_pno == cpno:
                            continue
                        # Prefer parts with non-trivial Z (not at origin)
                        if abs(other_off[2]) > 0.5:
                            snap_z = other_off[2]
                            break
                    result[cpno] = (0, 0, round(snap_z, 1))
                    continue

                auto_queue.append(child)

        # ── Resolve deferred z_is_top groups ──
        # Parts sharing the same z_is_top value come from a combined §6.2 row
        # (e.g. "电机+减速器 Z=+73mm(向上)").  They must stack sequentially
        # from z_top downward so their combined top = z_top and the bottom
        # part sits on the reference surface.
        if _z_top_deferred:
            _z_top_groups = {}
            for cpno, child, z_top in _z_top_deferred:
                _z_top_groups.setdefault(z_top, []).append((cpno, child))

            for z_top, group in _z_top_groups.items():
                # Compute per-part height: envelope → BOM text → even split
                heights = {}
                for cpno, child in group:
                    env = _envelopes_cache.get(cpno)
                    if env:
                        heights[cpno] = env[2]
                    else:
                        dims = _parse_dims_text(
                            child.get("material", "") + " "
                            + child.get("name_cn", ""))
                        if dims:
                            heights[cpno] = dims[2]
                        elif len(group) > 1:
                            heights[cpno] = abs(z_top) / len(group)
                        else:
                            heights[cpno] = abs(z_top) if z_top != 0 else 15.0

                # Stack from z_top downward; sort larger parts to bottom
                cursor = z_top
                for cpno, child in sorted(
                        group, key=lambda g: -heights.get(g[0], 15.0)):
                    h = heights[cpno]
                    cursor -= h
                    result[cpno] = (0, 0, round(cursor, 1))

        if not auto_queue:
            continue

        dims_map = {}
        for child in auto_queue:
            text = child.get("material", "") + " " + child.get("name_cn", "")
            dims_map[child["part_no"]] = _parse_dims_text(text)

        # ── Envelope-aware anchor-relative stacking ──

        def _get_height(child):
            """Get part height from §6.4 envelope, BOM dims, or default."""
            env = _envelopes_cache.get(child["part_no"])
            if env:
                return env[2]  # h component
            text = child.get("material", "") + " " + child.get("name_cn", "")
            dims = _parse_dims_text(text)
            if dims:
                return dims[2]
            return 15.0  # conservative default

        # Stacking direction from axis_dir
        dz_sign = default_direction[2]
        if dz_sign == 0:
            dz_sign = -1

        # Seed auto-stacking from the occupied-extent boundary of already-
        # positioned parts so that auto-stacked parts touch (not overlap)
        # the explicit cluster.
        #   - Stacking downward → seed at min(bottom face)
        #   - Stacking upward  → seed at max(top face)
        # Top face = bottom_z + envelope_height.
        placed_in_assy = [(cpno, result[cpno][2]) for cpno in result
                          if cpno.startswith(prefix + "-")]
        if is_orphan or not placed_in_assy:
            seed_z = 0.0
        else:
            if dz_sign < 0:
                seed_z = min(z for _, z in placed_in_assy)
            else:
                def _top_z(cpno, z_bottom):
                    env = _envelopes_cache.get(cpno)
                    return z_bottom + (env[2] if env else 15.0)
                seed_z = max(_top_z(cpno, z) for cpno, z in placed_in_assy)

        # Container constraint: find the largest envelope among ALL parts
        # in this assembly (including auto_queue). Auto-stacked parts will
        # be clamped to stay within this part's Z extent. This prevents
        # cumulative stacking from overflowing the housing.
        # Sort auto_queue so the LARGEST part stacks first, establishing
        # the container Z range; subsequent parts are clamped inside it.
        def _ph(child):
            env = _envelopes_cache.get(child["part_no"])
            return env[2] if env else 15.0

        # Find the dominant container: maximum envelope height across all
        # children of this assembly (already-placed + auto_queue).
        max_h = 0.0
        for cpno, _ in placed_in_assy:
            env = _envelopes_cache.get(cpno)
            if env and env[2] > max_h:
                max_h = env[2]
        for child in auto_queue:
            env = _envelopes_cache.get(child["part_no"])
            if env and env[2] > max_h:
                max_h = env[2]

        # Stack the largest part first so it establishes the container.
        auto_queue = sorted(auto_queue, key=_ph, reverse=True)

        container_top = None
        container_bot = None
        # Initialize container from already-placed parts (e.g. constraints)
        for cpno, z_bot in placed_in_assy:
            env = _envelopes_cache.get(cpno)
            if not env or env[2] < max_h * 0.9:
                continue
            container_bot = z_bot
            container_top = z_bot + env[2]
            break

        cursor_z = seed_z
        for child in auto_queue:
            cpno = child["part_no"]
            h = _get_height(child)

            # Check for per-part horizontal direction override
            clause = _match_axis_clause(assy_axis_dir, child["name_cn"])
            if clause and any(k in clause for k in ["∥XY", "水平", "径向"]):
                # R3: Horizontal part — offset from host body edge, not h/2.
                # Use part diameter (not length) as clearance from center.
                env = _envelopes_cache.get(cpno)
                part_d = env[0] if env else 20.0  # diameter or width
                center_x = round(part_d, 1)  # just outside host body
                result[cpno] = (center_x, 0, 0)
                continue

            # Parts have bottom at Z=0 (centered=(True,True,False)).
            # offset_z positions the bottom face, not the center.
            if dz_sign < 0:
                cursor_z -= h
                offset_z = cursor_z
            else:
                offset_z = cursor_z
                cursor_z += h

            # Container clamp: keep auto-stacked parts within the container
            # bbox if any. If the cursor would push a part beyond the
            # container bottom (downward) or top (upward), wrap the cursor
            # back to the opposite face and continue stacking from there.
            # This prevents pathological cases like 13 parts auto-stacked
            # 200mm below a 60mm housing.
            if container_top is not None and container_bot is not None:
                if dz_sign < 0:
                    # offset_z is the bottom face; check if it's below container
                    if offset_z < container_bot - 1.0:
                        # wrap: restart cursor at container top, stack down
                        cursor_z = container_top - h
                        offset_z = cursor_z
                else:
                    # offset_z is the bottom face; top = offset_z + h
                    if offset_z + h > container_top + 1.0:
                        cursor_z = container_bot
                        offset_z = cursor_z
                        cursor_z += h

            # If this part is the largest envelope (the container itself)
            # and no container is set yet, register its bbox now so smaller
            # parts that follow can be clamped to it.
            if container_top is None:
                env = _envelopes_cache.get(cpno)
                if env and abs(env[2] - max_h) < 0.1:
                    container_bot = offset_z
                    container_top = offset_z + env[2]

            result[cpno] = (0, 0, round(offset_z, 1))

    return result


def _parse_excluded_assemblies(spec_path: str) -> set:
    """Parse excluded assembly part_nos from CAD_SPEC.md §6.2 only.

    Scoped to §6.2 section to avoid false matches from §9.2 exclude_stack
    constraints (which exclude individual parts, not whole assemblies).
    """
    try:
        text = Path(spec_path).read_text(encoding="utf-8")
    except Exception:
        return set()
    excluded = set()
    in_s62 = False
    for line in text.splitlines():
        if "### 6.2" in line or "装配层叠" in line:
            in_s62 = True
            continue
        if in_s62 and line.startswith("### "):
            break
        if in_s62 and line.startswith("## "):
            break
        if not in_s62 or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if any("exclude" in c.lower() for c in cells):
            for cell in cells:
                for m in re.findall(r"[A-Z]+-[A-Z]+-\d+", cell):
                    excluded.add(m)
    return excluded


def parse_render_exclusions(spec_path: str) -> dict:
    """Parse render exclusions from CAD_SPEC.md.

    Returns:
        {"assemblies": set[str], "parts": set[str]}

    §6.2 marks whole assemblies/modules that are outside the rendered
    subsystem. §9.2 exclude_stack marks leaf connector/cable parts that should
    not be emitted as real zero-offset geometry.
    """
    assemblies = _parse_excluded_assemblies(spec_path)
    parts = set()
    for constraint in parse_constraints(spec_path):
        if constraint.get("type") != "exclude_stack":
            continue
        part_no = constraint.get("part_a", "").strip()
        if part_no:
            parts.add(part_no)
    return {"assemblies": assemblies, "parts": parts}


def _split_md_row(line: str) -> list:
    raw_cells = [c.strip() for c in line.split("|")]
    return raw_cells[1:-1] if len(raw_cells) >= 2 else raw_cells


def _header_index(header: list, aliases: tuple) -> int:
    for idx, col in enumerate(header):
        compact = re.sub(r"\s+", "", col).lower()
        for alias in aliases:
            if alias.lower() in compact:
                return idx
    return -1


def _cell_float(cells: list, idx: int):
    if idx < 0 or idx >= len(cells):
        return None
    value = cells[idx].strip()
    if value in ("", "—", "-"):
        return None
    value = value.translate(str.maketrans({
        "−": "-", "－": "-", "﹣": "-", "–": "-", "—": "-",
        "＋": "+",
    }))
    m = re.search(r"[+-]?\d+(?:\.\d+)?", value)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _parse_part_positions(spec_path: str) -> dict:
    """Parse §6.3 part-level positioning table from CAD_SPEC.md.

    Returns {part_no: {"z": float, "h": float, "mode": str,
                       "confidence": str, "instances": [...]}}.
    """
    try:
        text = Path(spec_path).read_text(encoding="utf-8")
    except Exception:
        return {}

    positions = {}
    in_section = False
    header = []

    for line in text.splitlines():
        if "### 6.3" in line and "零件级定位" in line:
            in_section = True
            header = []
            continue
        if in_section and line.startswith("### ") and "6.3" not in line:
            break
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        if not line.startswith("|") or "---" in line:
            continue

        cells = _split_md_row(line)
        if len(cells) < 5:
            continue
        if "料号" in cells:
            header = cells
            continue
        if not header:
            continue

        pno_idx = _header_index(header, ("料号", "part_no"))
        inst_idx = _header_index(header, ("实例", "instance"))
        mode_idx = _header_index(header, ("模式", "mode"))
        h_idx = _header_index(header, ("高度", "h(mm)", "height"))
        z_idx = _header_index(header, ("底面z", "z(mm)", "z"))
        x_idx = _header_index(header, ("x(mm)", "x"))
        y_idx = _header_index(header, ("y(mm)", "y"))
        src_idx = _header_index(header, ("来源", "source"))
        conf_idx = _header_index(header, ("置信度", "confidence"))

        if pno_idx < 0 or pno_idx >= len(cells):
            continue
        pno = cells[pno_idx]
        if not re.match(r"[A-Z]+-", pno):
            continue

        mode = cells[mode_idx] if 0 <= mode_idx < len(cells) else "axial_stack"
        h = _cell_float(cells, h_idx)
        z = _cell_float(cells, z_idx)
        x = _cell_float(cells, x_idx)
        y = _cell_float(cells, y_idx)
        source = cells[src_idx] if 0 <= src_idx < len(cells) else ""
        confidence = cells[conf_idx] if 0 <= conf_idx < len(cells) else ""
        instance_id = cells[inst_idx] if 0 <= inst_idx < len(cells) else ""

        pos = positions.setdefault(pno, {
            "z": z, "h": h, "mode": mode, "confidence": confidence,
            "source": source, "instances": [],
        })
        if not pos.get("instances"):
            pos.update({
                "z": z, "h": h, "mode": mode,
                "confidence": confidence, "source": source,
            })
        if instance_id or x is not None or y is not None:
            pos["instances"].append({
                "instance_id": instance_id or pno,
                "part_no": pno,
                "x": x if x is not None else 0.0,
                "y": y if y is not None else 0.0,
                "z": z if z is not None else 0.0,
                "h": h,
                "mode": mode,
                "source": source,
                "confidence": confidence,
            })

    return positions


def _safe_instance_id(instance_id: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", instance_id or "")
    return safe.strip("_").lower()


def _offset_from_instance(instance: dict, fallback):
    if instance:
        return (
            float(instance.get("x") or 0.0),
            float(instance.get("y") or 0.0),
            float(instance.get("z") or 0.0),
        )
    return fallback


def _offset_to_literal(offset) -> str:
    if not offset or offset == (0, 0, 0):
        return ""
    return f"({offset[0]}, {offset[1]}, {offset[2]})"


def generate_assembly(spec_path: str) -> str:
    """Generate assembly.py scaffold content.

    Reads §5 BOM, §4 connections, §6 assembly pose from CAD_SPEC.md.
    Computes per-part positioning:
      - Explicit: Z/R/θ from §6.2 layer stacking table (part_no or name-fallback)
      - Per-part axis: multi-clause axis_dir matched by part name keywords
      - Auto-stacked: parts without explicit positions stacked along their
        matched axis_dir with envelope-based spacing
      - Orphan assemblies: no §6.2 pose → safe default offset to avoid overlap
    Part origin convention: bottom face at Z=0, extrude upward.
    """
    parts = parse_bom_tree(spec_path)
    pose = parse_assembly_pose(spec_path)
    connections = parse_connections(spec_path)

    # Separate assemblies and their children
    assemblies = [p for p in parts if p["is_assembly"]]

    # Detect subsystem prefix from spec — supports both "GIS-EE" and "SLP" forms
    text = Path(spec_path).read_text(encoding="utf-8")
    m = re.search(r"\(([A-Z]+-[A-Z]+)\)", text[:200])
    if not m:
        # Try single-word prefix like (SLP)
        m = re.search(r"\(([A-Z]{2,})\)", text[:200])
    prefix = m.group(1) if m else "GIS-XX"
    # For GIS-EE → "EE"; for SLP → "SLP" (no dash → use whole string)
    prefix_short = prefix.split("-")[-1] if "-" in prefix else prefix
    # Detect if this is a flat BOM (no sub-assembly hierarchy)
    is_flat_bom = "-" not in prefix  # SLP = flat, GIS-EE = hierarchical

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

    # C1: Extract per-assembly pose from §6.2 (keyed by part number)
    layer_poses = _extract_all_layer_poses(pose, parts)
    part_offsets = _resolve_child_offsets(parts, layer_poses, spec_path)
    part_positions = _parse_part_positions(spec_path)

    # C6: Build orientation map from §6.2 axis_dir column
    axis_map = _build_layer_axis_map(pose)

    # Parse render exclusions once (not per-iteration)
    render_exclusions = parse_render_exclusions(spec_path)
    excluded_assemblies = render_exclusions["assemblies"]
    excluded_part_nos = render_exclusions["parts"]
    envelopes = parse_envelopes(spec_path)
    project_root = str(Path(spec_path).resolve().parent.parent.parent)
    resolver = default_resolver(project_root=project_root)

    for i, assy in enumerate(assemblies):
        pno = assy["part_no"]
        name = assy["name_cn"]

        # Skip assemblies marked as excluded in §6.2
        if pno in excluded_assemblies:
            continue

        if is_flat_bom:
            # Flat BOM: suffix is the prefix itself (e.g. "SLP")
            suffix = "000"
            # All non-assembly parts belong to the single root assembly
            children = [p for p in parts if not p["is_assembly"]]
        else:
            # Hierarchical BOM (GIS-EE-001): suffix is the station number
            from cad_spec_defaults import strip_part_prefix
            suffix = strip_part_prefix(pno).split("-")[-1] if "-" in strip_part_prefix(pno) else strip_part_prefix(pno)
            # Children match by prefix: GIS-EE-001-xx
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
            if _is_render_excluded(
                    child["part_no"], excluded_part_nos,
                    excluded_assemblies):
                continue

            # Compute child suffix for display: GIS-EE-001-01 → "01", SLP-100 → "100"
            from cad_spec_defaults import strip_part_prefix
            c_stripped = strip_part_prefix(child["part_no"])
            c_suffix = c_stripped.split("-")[-1] if "-" in c_stripped else c_stripped
            make_buy = child.get("make_buy", "")
            child_instances = part_positions.get(
                child["part_no"], {}).get("instances", [])
            placement_rows = child_instances or [None]
            category = classify_part(child["name_cn"], child.get("material", ""))
            query = build_library_part_query(
                child,
                category=category,
                envelope=envelopes.get(child["part_no"]),
                project_root=project_root,
            )
            library_routed = is_library_routed_row(
                child,
                category=category,
                resolver=resolver,
                query=query,
            )

            if "外购" in make_buy or "标准" in make_buy or library_routed:
                # Standard/purchased or resolver-routed custom part — use std_ module
                if category not in _STD_PART_CATEGORIES:
                    continue
                std_mod = library_module_name(child["part_no"])
                std_func = library_make_function(child["part_no"])
                color_info = _STD_COLOR_MAP.get(category, ("C_STD_SENSOR", 0.2, 0.2, 0.2))
                std_colors_used[color_info[0]] = color_info

                for inst in placement_rows:
                    inst_id = inst.get("instance_id", "") if inst else ""
                    inst_safe = _safe_instance_id(inst_id)
                    inst_suffix = f"_{inst_safe}" if inst_safe else ""
                    name_suffix = f"-{inst_id}" if inst_id else ""

                    # C6: Apply station-level orientation from §6.2 axis_dir
                    var_name = f"p_{std_mod}{inst_suffix}"
                    local_xform, orient_ref = _axis_dir_to_local_transform(
                        station_axis_dir, var_name, child["name_cn"])

                    offset = _offset_from_instance(
                        inst, part_offsets.get(child["part_no"]))
                    offset_str = _offset_to_literal(offset)
                    station_parts.append({
                        "var": var_name,
                        "make_call": f"{std_func}()",
                        "local_transform": local_xform,
                        "orient_doc_ref": orient_ref or "",
                        "orient_rule": "",
                        "local_offset": offset_str,
                        "assy_name": f"STD-{child['part_no']}{name_suffix}",
                        "color_var": color_info[0],
                    })
                std_func_imports.append({
                    "module": std_mod,
                    "func": std_func,
                })
            else:
                # Custom-made part — import from individual module
                # gen_parts.py names via strip_part_prefix:
                #   GIS-EE-001-01 → ee_001_01.py / make_ee_001_01()
                #   SLP-100       → p100.py      / make_p100()
                #   SLP-P01       → p01.py        / make_p01()
                ee_mod = strip_part_prefix(child["part_no"]).lower().replace("-", "_")
                if ee_mod and ee_mod[0].isdigit():
                    ee_mod = "p" + ee_mod
                ee_func = f"make_{ee_mod}"
                c_color = _COLOR_PALETTE[color_idx % len(_COLOR_PALETTE)][0]

                for inst in placement_rows:
                    inst_id = inst.get("instance_id", "") if inst else ""
                    inst_safe = _safe_instance_id(inst_id)
                    inst_suffix = f"_{inst_safe}" if inst_safe else ""
                    name_suffix = f"-{inst_id}" if inst_id else ""

                    # C6: Apply station-level orientation from §6.2 axis_dir
                    var_name = f"p_{ee_mod}{inst_suffix}"
                    local_xform, orient_ref = _axis_dir_to_local_transform(
                        station_axis_dir, var_name, child["name_cn"])

                    offset = _offset_from_instance(
                        inst, part_offsets.get(child["part_no"]))
                    offset_str = _offset_to_literal(offset)
                    station_parts.append({
                        "var": var_name,
                        "make_call": f"{ee_func}()",
                        "local_transform": local_xform,
                        "orient_doc_ref": orient_ref or "",
                        "orient_rule": "",
                        "local_offset": offset_str,
                        "assy_name": f"{c_stripped}{name_suffix}",
                        "color_var": c_color,
                    })
                # Each custom part gets its own import line
                part_imports.append({
                    "module": ee_mod,
                    "functions": [ee_func],
                })

        for si in std_func_imports:
            std_part_imports.append(si)

        # C2: Look up this assembly's pose by part number from §6.2
        sp = layer_poses.get(pno, {})
        is_radial = sp.get("r") is not None and sp.get("theta") is not None

        station_entry = {
            "name_cn": name,
            "angle": sp.get("theta", 0.0),
            "is_radial": is_radial,
            "parts": station_parts,
        }
        if is_radial:
            station_entry["mount_radius"] = sp["r"]
            station_entry["base_z"] = sp.get("z") or 0.0

        stations.append(station_entry)

        color_idx += 1

    # Build BOM tree for docstring
    bom_tree = []
    for p in parts:
        if p["is_assembly"]:
            depth = 0
        elif is_flat_bom:
            depth = 1  # flat BOM: all parts at depth 1
        else:
            # Hierarchical: depth from segment count relative to assembly level
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

    # C4: Collect assembly_params — now mount_radius/base_z are numeric
    # literals in the template, no longer params.py references.
    assembly_params = []

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
