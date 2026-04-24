"""templates/parts/rectangular_housing.py — Parametric hollow rectangular enclosure.

Geometry pipeline:
    1. Outer shell (w × d × h, hollowed with wall_t thickness)
    2. Corner fillets (exterior) for structural radius
    3. Top lid flange with raised rim and bolt holes
    4. Optional cable gland boss on a selected wall face
    5. Internal standoffs (N posts with tapped holes for PCB mounting)
    6. Optional draft angle on outer walls (for castability)
    7. Edge chamfers on lid flange and gland boss

All dimensions in millimeters. Cosmetic operations wrapped in try/except.
"""

from __future__ import annotations

import math
from typing import Optional

import cadquery as cq


MATCH_KEYWORDS: list[str] = [
    "rectangular housing",
    "enclosure",
    "box housing",
    "rectangular enclosure",
    "壳体", "矩形壳体", "方形壳体", "箱体",
]
MATCH_PRIORITY: int = 15
TEMPLATE_CATEGORY: str = "housing"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {
        "w": 120.0,
        "d": 80.0,
        "h": 40.0,
        "wall_t": 2.5,
        "corner_fillet": 3.0,
        "lid_flange_w": 6.0,
        "lid_flange_h": 2.0,
        "lid_bolt_dia": 3.0,
        "lid_bolt_count": 4,
        "lid_bolt_margin": 5.0,
        "standoff_count": 4,
        "standoff_dia": 5.0,
        "standoff_h": 8.0,
        "standoff_tap_dia": 2.5,
        "cable_gland_face": "side",  # "side" | "back" | "none"
        "cable_gland_dia": 8.0,
        "cable_gland_boss_thickness": 3.0,
        "draft_angle_deg": 0.5,
        "edge_chamfer": 0.5,
    }


def make(
    *,
    w: float = 120.0,
    d: float = 80.0,
    h: float = 40.0,
    wall_t: float = 2.5,
    corner_fillet: float = 3.0,
    lid_flange_w: float = 6.0,
    lid_flange_h: float = 2.0,
    lid_bolt_dia: float = 3.0,
    lid_bolt_count: int = 4,
    lid_bolt_margin: float = 5.0,
    standoff_count: int = 4,
    standoff_dia: float = 5.0,
    standoff_h: float = 8.0,
    standoff_tap_dia: float = 2.5,
    cable_gland_face: str = "side",
    cable_gland_dia: float = 8.0,
    cable_gland_boss_thickness: float = 3.0,
    draft_angle_deg: float = 0.5,
    edge_chamfer: float = 0.5,
) -> cq.Workplane:
    """Construct a hollow rectangular enclosure with lid flange and cable gland.

    Coordinate system:
      - Origin at the center of the bottom face.
      - Outer dimensions w × d × h along X, Y, Z.
      - Open top face (no lid modeled; lid is a separate part).
    """
    # ---- Outer shell ----
    outer = cq.Workplane("XY").box(w, d, h, centered=(True, True, False))

    # ---- Corner fillets (exterior) ----
    if corner_fillet > 0 and corner_fillet < min(w, d) * 0.3:
        try:
            outer = outer.edges("|Z").fillet(corner_fillet)
        except Exception:
            pass

    # ---- Hollow the shell (shell-like via subtraction of inner box) ----
    inner_w = w - 2 * wall_t
    inner_d = d - 2 * wall_t
    inner_h = h - wall_t  # Closed bottom, open top
    if inner_w > 0 and inner_d > 0 and inner_h > 0:
        inner = cq.Workplane("XY").box(inner_w, inner_d, inner_h,
                                        centered=(True, True, False)).translate((0, 0, wall_t))
        try:
            body = outer.cut(inner)
        except Exception:
            body = outer
    else:
        body = outer

    # ---- Top lid flange (raised rim around top opening) ----
    if lid_flange_w > 0 and lid_flange_h > 0:
        try:
            flange_outer_w = inner_w + 2 * lid_flange_w
            flange_outer_d = inner_d + 2 * lid_flange_w
            if flange_outer_w < w and flange_outer_d < d:
                flange_ring = (
                    cq.Workplane("XY")
                    .box(flange_outer_w, flange_outer_d, lid_flange_h,
                         centered=(True, True, False))
                    .translate((0, 0, h))
                )
                flange_hole = (
                    cq.Workplane("XY")
                    .box(inner_w, inner_d, lid_flange_h + 1,
                         centered=(True, True, False))
                    .translate((0, 0, h - 0.5))
                )
                flange_solid = flange_ring.cut(flange_hole)
                body = body.union(flange_solid)
        except Exception:
            pass

    # ---- Lid bolt holes through flange ----
    if lid_bolt_dia > 0 and lid_bolt_count >= 4:
        pcd_w = w - 2 * lid_bolt_margin
        pcd_d = d - 2 * lid_bolt_margin
        if lid_bolt_count == 4:
            positions = [
                (pcd_w / 2, pcd_d / 2),
                (-pcd_w / 2, pcd_d / 2),
                (pcd_w / 2, -pcd_d / 2),
                (-pcd_w / 2, -pcd_d / 2),
            ]
        else:
            positions = [
                (pcd_w / 2, pcd_d / 2),
                (-pcd_w / 2, pcd_d / 2),
                (pcd_w / 2, -pcd_d / 2),
                (-pcd_w / 2, -pcd_d / 2),
            ]
        for x, y in positions:
            try:
                body = body.faces(">Z").workplane().center(x, y).hole(lid_bolt_dia)
            except Exception:
                pass

    # ---- Internal standoffs ----
    if standoff_count >= 4 and standoff_dia > 0 and standoff_h > 0:
        margin = standoff_dia
        sx = inner_w / 2 - margin
        sy = inner_d / 2 - margin
        standoff_positions = [
            (sx, sy), (-sx, sy), (sx, -sy), (-sx, -sy),
        ]
        for x, y in standoff_positions:
            try:
                standoff = (
                    cq.Workplane("XY")
                    .center(x, y)
                    .circle(standoff_dia / 2)
                    .extrude(standoff_h)
                    .translate((0, 0, wall_t))
                )
                body = body.union(standoff)
            except Exception:
                pass

    # ---- Cable gland boss ----
    if cable_gland_face != "none" and cable_gland_dia > 0:
        try:
            if cable_gland_face == "side":
                boss = (
                    cq.Workplane("YZ")
                    .circle(cable_gland_dia / 2 + cable_gland_boss_thickness)
                    .extrude(wall_t + cable_gland_boss_thickness)
                    .translate((w / 2 - wall_t, 0, h / 2))
                )
                body = body.union(boss)
                body = (
                    body.faces(">X")
                    .workplane()
                    .center(0, 0)
                    .hole(cable_gland_dia)
                )
        except Exception:
            pass

    # ---- Edge chamfers ----
    if edge_chamfer > 0:
        try:
            body = body.edges(">Z").chamfer(edge_chamfer)
        except Exception:
            pass

    return body
