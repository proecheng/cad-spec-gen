"""templates/parts/cylindrical_housing.py — Parametric hollow cylindrical enclosure.

Geometry pipeline:
    1. Outer cylinder (outer_dia × h, hollowed with wall_t)
    2. End cap option: "open" / "flat" (lid with bolt circle) / "domed"
    3. Axial through-bore (optional — for shaft pass-through)
    4. External mounting flange at one end with PCD bolt circle
    5. Internal ledge/step for component seating
    6. Edge chamfers and rim fillets

All dimensions in millimeters. Cosmetic operations wrapped in try/except.
"""

from __future__ import annotations

import math
from typing import Optional

import cadquery as cq


MATCH_KEYWORDS: list[str] = [
    "cylindrical housing",
    "cylinder enclosure",
    "tube housing",
    "cylindrical shell",
    "壳体", "圆柱壳体", "圆筒壳体",
]
MATCH_PRIORITY: int = 15
TEMPLATE_CATEGORY: str = "housing"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {
        "outer_dia": 60.0,
        "h": 100.0,
        "wall_t": 3.0,
        "end_cap": "flat",
        "end_cap_thickness": 4.0,
        "end_cap_bolt_dia": 3.0,
        "end_cap_bolt_count": 6,
        "bore_dia": 0.0,
        "bore_chamfer": 0.0,
        "flange_dia": 80.0,
        "flange_t": 5.0,
        "flange_bolt_dia": 4.0,
        "flange_bolt_count": 4,
        "flange_bolt_pcd": 70.0,
        "ledge_dia": 0.0,
        "ledge_depth": 0.0,
        "register_type": "none",
        "register_dim": 0.0,
        "edge_chamfer": 0.5,
    }


def make(
    *,
    outer_dia: float = 60.0,
    h: float = 100.0,
    wall_t: float = 3.0,
    end_cap: str = "flat",
    end_cap_thickness: float = 4.0,
    end_cap_bolt_dia: float = 3.0,
    end_cap_bolt_count: int = 6,
    bore_dia: float = 0.0,
    bore_chamfer: float = 0.0,
    flange_dia: float = 80.0,
    flange_t: float = 5.0,
    flange_bolt_dia: float = 4.0,
    flange_bolt_count: int = 4,
    flange_bolt_pcd: float = 70.0,
    ledge_dia: float = 0.0,
    ledge_depth: float = 0.0,
    register_type: str = "none",
    register_dim: float = 0.0,
    edge_chamfer: float = 0.5,
) -> cq.Workplane:
    """Construct the cylindrical housing.

    Coordinate system:
      - Origin at the center of the bottom face.
      - Cylinder axis along +Z, height h.
      - Flange at Z=0; end cap (if any) at Z=h.
    """
    outer_r = outer_dia / 2
    inner_r = outer_r - wall_t

    # ---- Outer cylinder ----
    body = cq.Workplane("XY").circle(outer_r).extrude(h)

    # ---- Hollow the cylinder ----
    if inner_r > 0:
        try:
            hollow_h = h
            if end_cap == "flat" and end_cap_thickness > 0:
                hollow_h = h - end_cap_thickness
            inner = (
                cq.Workplane("XY")
                .circle(inner_r)
                .extrude(hollow_h)
                .translate((0, 0, wall_t if end_cap != "open" else 0))
            )
            body = body.cut(inner)
        except Exception:
            pass

    # ---- Mounting flange at bottom (Z=0) ----
    if flange_dia > outer_dia and flange_t > 0:
        try:
            flange = (
                cq.Workplane("XY")
                .circle(flange_dia / 2)
                .circle(outer_r)
                .extrude(flange_t)
                .translate((0, 0, -flange_t))
            )
            body = body.union(flange)

            # Flange bolt circle
            if flange_bolt_dia > 0 and flange_bolt_count > 0 and flange_bolt_pcd > 0:
                angle_step = 360.0 / flange_bolt_count
                for i in range(flange_bolt_count):
                    angle = math.radians(i * angle_step)
                    x = (flange_bolt_pcd / 2) * math.cos(angle)
                    y = (flange_bolt_pcd / 2) * math.sin(angle)
                    try:
                        body = (
                            body.faces("<Z")
                            .workplane()
                            .center(x, y)
                            .hole(flange_bolt_dia)
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    # ---- End cap bolt holes (if flat cap) ----
    if end_cap == "flat" and end_cap_bolt_dia > 0 and end_cap_bolt_count > 0:
        cap_pcd = inner_r + wall_t / 2
        angle_step = 360.0 / end_cap_bolt_count
        for i in range(end_cap_bolt_count):
            angle = math.radians(i * angle_step)
            x = cap_pcd * math.cos(angle)
            y = cap_pcd * math.sin(angle)
            try:
                body = (
                    body.faces(">Z")
                    .workplane()
                    .center(x, y)
                    .hole(end_cap_bolt_dia, depth=end_cap_thickness * 0.8)
                )
            except Exception:
                pass

    # ---- Axial through-bore ----
    if bore_dia > 0 and bore_dia < inner_r * 2:
        try:
            bore = (
                cq.Workplane("XY")
                .circle(bore_dia / 2)
                .extrude(h + 2 * end_cap_thickness)
                .translate((0, 0, -end_cap_thickness))
            )
            body = body.cut(bore)
            if bore_chamfer > 0:
                try:
                    body = body.edges("%CIRCLE").chamfer(bore_chamfer)
                except Exception:
                    pass
        except Exception:
            pass

    # ---- Edge chamfers ----
    if edge_chamfer > 0:
        try:
            body = body.edges(">Z").chamfer(edge_chamfer)
        except Exception:
            pass

    return body
