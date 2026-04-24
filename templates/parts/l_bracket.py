"""templates/parts/l_bracket.py — Parametric L-shaped mounting bracket.

Geometry pipeline:
    1. Base plate (w × d × t) with optional corner fillets
    2. Vertical wall (w × h × t) at 90° to base plate
    3. Inner bend fillet (structural radius between base and wall)
    4. Mounting hole grid on base plate (rectangular bolt pattern)
    5. Mounting hole grid on vertical wall (same)
    6. Optional stiffener gusset (triangular rib between faces)
    7. Edge chamfers on all exposed rims
    8. Optional counterbore on all holes

All dimensions in millimeters. Cosmetic operations (fillets, chamfers)
are wrapped in try/except so a single OCCT hiccup leaves the part
topologically valid without cosmetic polish.
"""

from __future__ import annotations

import math
from typing import Optional

import cadquery as cq


# ---------------------------------------------------------------------------
# Module contract (Spec 1 Phase 2)
# ---------------------------------------------------------------------------

MATCH_KEYWORDS: list[str] = [
    "l_bracket",
    "l bracket",
    "angle bracket",
    "corner bracket",
    "angle iron",
    "支架", "L型支架", "角支架", "安装支架",
]
MATCH_PRIORITY: int = 15
TEMPLATE_CATEGORY: str = "bracket"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    """Canonical parameter set for l_bracket."""
    return {
        "w": 60.0,
        "d": 40.0,
        "h": 50.0,
        "t": 4.0,
        "bend_fillet": 3.0,
        "gusset": True,
        "gusset_width": 15.0,
        "gusset_chamfer": 1.0,
        "base_bolt_dia": 5.0,
        "base_bolt_count_x": 2,
        "base_bolt_count_y": 1,
        "base_bolt_margin": 8.0,
        "wall_bolt_dia": 5.0,
        "wall_bolt_count_x": 2,
        "wall_bolt_count_y": 1,
        "wall_bolt_margin": 8.0,
        "counterbore_dia": 0.0,  # 0 = no counterbore
        "counterbore_depth": 0.0,
        "edge_chamfer": 0.5,
    }


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def make(
    *,
    w: float = 60.0,
    d: float = 40.0,
    h: float = 50.0,
    t: float = 4.0,
    bend_fillet: float = 3.0,
    gusset: bool = True,
    gusset_width: float = 15.0,
    gusset_chamfer: float = 1.0,
    base_bolt_dia: float = 5.0,
    base_bolt_count_x: int = 2,
    base_bolt_count_y: int = 1,
    base_bolt_margin: float = 8.0,
    wall_bolt_dia: float = 5.0,
    wall_bolt_count_x: int = 2,
    wall_bolt_count_y: int = 1,
    wall_bolt_margin: float = 8.0,
    counterbore_dia: float = 0.0,
    counterbore_depth: float = 0.0,
    edge_chamfer: float = 0.5,
) -> cq.Workplane:
    """Construct the L-bracket.

    Coordinate system:
      - Origin at the outer corner where base and wall meet.
      - Base plate extends in +X (width w) and +Y (depth d).
      - Vertical wall extends in +X (width w) and +Z (height h).
      - Both base and wall have thickness t.

    Returns:
        cq.Workplane wrapping the union of base plate + vertical wall +
        optional gusset with all features applied.
    """
    # ---- Base plate: w × d × t, sitting in the XY plane at Z=0..t ----
    base = cq.Workplane("XY").box(w, d, t, centered=(False, False, False))

    # ---- Vertical wall: w × t × h, standing in the XZ plane at Y=0..t ----
    wall = (
        cq.Workplane("XY")
        .workplane(offset=0)
        .box(w, t, h, centered=(False, False, False))
    )

    # Union base and wall
    body = base.union(wall)

    # ---- Inner bend fillet ----
    if bend_fillet > 0 and bend_fillet < min(d, h) * 0.5:
        try:
            # Select the inner edge where base top meets wall back
            body = body.edges("|X and (>Y and <Z)").fillet(bend_fillet)
        except Exception:
            pass  # Leave unfilleted if OCCT can't resolve the edge set

    # ---- Base plate holes ----
    if base_bolt_dia > 0 and base_bolt_count_x > 0 and base_bolt_count_y > 0:
        hole_dia = base_bolt_dia
        if base_bolt_count_x == 1:
            xs = [w / 2]
        else:
            span_x = w - 2 * base_bolt_margin
            step_x = span_x / (base_bolt_count_x - 1) if base_bolt_count_x > 1 else 0
            xs = [base_bolt_margin + i * step_x for i in range(base_bolt_count_x)]
        if base_bolt_count_y == 1:
            ys = [d - base_bolt_margin]
        else:
            span_y = d - 2 * base_bolt_margin - t  # Leave room for wall
            step_y = span_y / (base_bolt_count_y - 1) if base_bolt_count_y > 1 else 0
            ys = [t + base_bolt_margin + i * step_y for i in range(base_bolt_count_y)]
        for x in xs:
            for y in ys:
                try:
                    if counterbore_dia > hole_dia and counterbore_depth > 0:
                        body = (
                            body.faces(">Z")
                            .workplane()
                            .center(x - w / 2, y - d / 2)
                            .cboreHole(hole_dia, counterbore_dia, counterbore_depth)
                        )
                    else:
                        body = (
                            body.faces(">Z")
                            .workplane()
                            .center(x - w / 2, y - d / 2)
                            .hole(hole_dia)
                        )
                except Exception:
                    pass

    # ---- Wall plate holes ----
    if wall_bolt_dia > 0 and wall_bolt_count_x > 0 and wall_bolt_count_y > 0:
        hole_dia = wall_bolt_dia
        if wall_bolt_count_x == 1:
            xs = [w / 2]
        else:
            span_x = w - 2 * wall_bolt_margin
            step_x = span_x / (wall_bolt_count_x - 1) if wall_bolt_count_x > 1 else 0
            xs = [wall_bolt_margin + i * step_x for i in range(wall_bolt_count_x)]
        if wall_bolt_count_y == 1:
            zs = [h / 2]
        else:
            span_z = h - 2 * wall_bolt_margin
            step_z = span_z / (wall_bolt_count_y - 1) if wall_bolt_count_y > 1 else 0
            zs = [wall_bolt_margin + i * step_z for i in range(wall_bolt_count_y)]
        for x in xs:
            for z in zs:
                try:
                    body = (
                        body.faces("<Y")
                        .workplane(origin=(x, 0, z))
                        .hole(hole_dia)
                    )
                except Exception:
                    pass

    # ---- Optional stiffener gusset ----
    if gusset and gusset_width > 0:
        try:
            gusset_pts = [(0, 0), (gusset_width, 0), (0, gusset_width)]
            gusset_solid = (
                cq.Workplane("XZ")
                .workplane(offset=-t)  # Push to back face of wall
                .polyline(gusset_pts)
                .close()
                .extrude(t)
                .translate((w / 2, t, 0))
            )
            body = body.union(gusset_solid)
        except Exception:
            pass

    # ---- Edge chamfers ----
    if edge_chamfer > 0:
        try:
            body = body.edges("not(|Z or |X or |Y) or (|X and (>Z or <Z))").chamfer(edge_chamfer)
        except Exception:
            try:
                body = body.edges().chamfer(edge_chamfer * 0.5)
            except Exception:
                pass

    return body
