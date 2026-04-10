"""templates/parts/fixture_plate.py — Parametric flat plate with hole grid.

Common in fixtures, jigs, tooling, and locating plates. The single most
common part in a wide swath of mechanical work.

Geometry pipeline:
    1. Base plate (w × d × t) with optional corner fillets
    2. Regular hole grid (N×M pattern) with optional counterbores
    3. Optional dowel pin holes (precision fits, separate list)
    4. Optional slots (elongated holes, oriented X)
    5. Edge chamfers on all rims

All dimensions in millimeters. Cosmetic operations wrapped in try/except.

Coordinate conventions for position lists:
    - Plate origin at geometric center of w×d rectangle
    - (x, y) tuples in plate-local coordinates
    - dowel_pin_positions: list[tuple[float, float]] — empty disables
    - slot_positions: list[tuple[float, float]] — each entry is a slot
      CENTER; slot_w = width across, slot_l = length along X axis
"""

from __future__ import annotations

import math
from typing import List, Tuple

import cadquery as cq


MATCH_KEYWORDS: list[str] = [
    "fixture plate",
    "mounting plate",
    "base plate",
    "hole grid plate",
    "locating plate",
    "tooling plate",
]
MATCH_PRIORITY: int = 15
TEMPLATE_CATEGORY: str = "plate"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {
        "w": 200.0,
        "d": 150.0,
        "t": 10.0,
        "corner_fillet": 4.0,
        "hole_grid_nx": 4,
        "hole_grid_ny": 3,
        "hole_spacing_x": 40.0,
        "hole_spacing_y": 40.0,
        "hole_margin": 20.0,
        "hole_dia": 6.0,
        "counterbore_dia": 10.0,
        "counterbore_depth": 5.0,
        "dowel_pin_positions": [],  # list[(x, y)] — empty disables
        "dowel_pin_dia": 5.0,
        "slot_positions": [],  # list[(x, y)] — empty disables
        "slot_w": 0.0,
        "slot_l": 0.0,
        "edge_chamfer": 0.5,
    }


def make(
    *,
    w: float = 200.0,
    d: float = 150.0,
    t: float = 10.0,
    corner_fillet: float = 4.0,
    hole_grid_nx: int = 4,
    hole_grid_ny: int = 3,
    hole_spacing_x: float = 40.0,
    hole_spacing_y: float = 40.0,
    hole_margin: float = 20.0,
    hole_dia: float = 6.0,
    counterbore_dia: float = 0.0,
    counterbore_depth: float = 0.0,
    dowel_pin_positions: List[Tuple[float, float]] = None,
    dowel_pin_dia: float = 0.0,
    slot_positions: List[Tuple[float, float]] = None,
    slot_w: float = 0.0,
    slot_l: float = 0.0,
    edge_chamfer: float = 0.5,
) -> cq.Workplane:
    """Construct the fixture plate.

    Coordinate system:
      - Origin at geometric center of the plate (bottom face at Z=0, top at Z=t).
      - Plate extends ±w/2 in X and ±d/2 in Y.
    """
    if dowel_pin_positions is None:
        dowel_pin_positions = []
    if slot_positions is None:
        slot_positions = []

    # ---- Base plate ----
    body = cq.Workplane("XY").box(w, d, t, centered=(True, True, False))

    # ---- Corner fillets ----
    if corner_fillet > 0 and corner_fillet < min(w, d) * 0.3:
        try:
            body = body.edges("|Z").fillet(corner_fillet)
        except Exception:
            pass

    # ---- Regular hole grid ----
    if hole_grid_nx > 0 and hole_grid_ny > 0 and hole_dia > 0:
        # Compute grid origin
        total_span_x = (hole_grid_nx - 1) * hole_spacing_x if hole_grid_nx > 1 else 0
        total_span_y = (hole_grid_ny - 1) * hole_spacing_y if hole_grid_ny > 1 else 0
        start_x = -total_span_x / 2
        start_y = -total_span_y / 2
        for ix in range(hole_grid_nx):
            for iy in range(hole_grid_ny):
                x = start_x + ix * hole_spacing_x
                y = start_y + iy * hole_spacing_y
                try:
                    if counterbore_dia > hole_dia and counterbore_depth > 0:
                        body = (
                            body.faces(">Z")
                            .workplane()
                            .center(x, y)
                            .cboreHole(hole_dia, counterbore_dia, counterbore_depth)
                        )
                    else:
                        body = (
                            body.faces(">Z")
                            .workplane()
                            .center(x, y)
                            .hole(hole_dia)
                        )
                except Exception:
                    pass

    # ---- Dowel pin holes (precision fits) ----
    if dowel_pin_positions and dowel_pin_dia > 0:
        for x, y in dowel_pin_positions:
            try:
                body = (
                    body.faces(">Z")
                    .workplane()
                    .center(x, y)
                    .hole(dowel_pin_dia)
                )
            except Exception:
                pass

    # ---- Slots (elongated along X axis) ----
    if slot_positions and slot_w > 0 and slot_l > 0:
        for x, y in slot_positions:
            try:
                slot = (
                    cq.Workplane("XY")
                    .center(x, y)
                    .slot2D(slot_l, slot_w, 0)
                    .extrude(t + 1)
                    .translate((0, 0, -0.5))
                )
                body = body.cut(slot)
            except Exception:
                pass

    # ---- Edge chamfers ----
    if edge_chamfer > 0:
        try:
            body = body.edges(">Z or <Z").chamfer(edge_chamfer)
        except Exception:
            pass

    return body
