"""
PEEK Insulation Ring Engineering Drawing — EE-001-02

GB/T 三视图 A3：
  - 主视图：端面（环 + 6×M3 孔位）
  - 俯视图：剖面（L形截面 — 台阶止口细节）
  - 左视图：同俯视（对称件，省略或简化）

All geometry from params.py; tolerances from tolerances.py.
"""

import math
import os

from params import (
    PEEK_OD, PEEK_ID, PEEK_THICK, PEEK_STEP_HEIGHT,
    PEEK_BOLT_NUM, PEEK_BOLT_DIA, PEEK_BOLT_PCD,
    FLANGE_AL_THICK,
)
from tolerances import (
    PEEK_OD_TOL, PEEK_ID_TOL, PEEK_THICK_TOL, PEEK_BOLT_PCD_TOL,
    SURF_CRITICAL,
)
from drawing import (
    add_linear_dim, add_diameter_dim,
    add_section_hatch, add_surface_symbol,
    add_centerline_cross, add_centerline_h,
)
from draw_three_view import ThreeViewSheet


def peek_front_view(msp, ox, oy, scale):
    """Front view: annular ring + 6×M3 holes."""
    s = scale
    r_outer = PEEK_OD / 2
    r_inner = PEEK_ID / 2

    cx = ox + (r_outer + 10) * s
    cy = oy + (r_outer + 10) * s

    msp.add_circle((cx, cy), r_outer * s, dxfattribs={"layer": "OUTLINE"})
    msp.add_circle((cx, cy), r_inner * s, dxfattribs={"layer": "OUTLINE"})
    add_centerline_cross(msp, (cx, cy), size=(r_outer + 10) * s)

    # Bolt holes
    bolt_r = PEEK_BOLT_PCD / 2
    msp.add_circle((cx, cy), bolt_r * s, dxfattribs={"layer": "CENTER"})
    for i in range(PEEK_BOLT_NUM):
        a = math.radians(i * 60 + 30)
        bx = cx + bolt_r * math.cos(a) * s
        by = cy + bolt_r * math.sin(a) * s
        msp.add_circle((bx, by), (PEEK_BOLT_DIA / 2) * s,
                       dxfattribs={"layer": "OUTLINE"})

    # Dimensions
    add_diameter_dim(msp, (cx, cy), r_outer * s, angle_deg=30,
                     text=PEEK_OD_TOL.dia_text)
    add_diameter_dim(msp, (cx, cy), r_inner * s, angle_deg=210,
                     text=PEEK_ID_TOL.dia_text)
    add_diameter_dim(msp, (cx, cy), bolt_r * s, angle_deg=330,
                     text=f"PCD {PEEK_BOLT_PCD_TOL.text}")

    # Bolt callout
    a0 = math.radians(30)
    bx0 = cx + bolt_r * math.cos(a0) * s
    by0 = cy + bolt_r * math.sin(a0) * s
    msp.add_text(f"6×M3 通孔 Φ{PEEK_BOLT_DIA}", height=2.5,
                 dxfattribs={"layer": "DIM", "color": 3}
                 ).set_placement((bx0 + 8 * s, by0 + 3 * s))
    msp.add_line((bx0 + 2 * s, by0 + 1 * s), (bx0 + 7 * s, by0 + 3 * s),
                 dxfattribs={"layer": "DIM", "color": 3})


def peek_top_view(msp, ox, oy, scale):
    """Top view (section): L-shaped cross-section showing step insert."""
    s = scale
    # centre → bottom-left origin
    oy = oy - (PEEK_THICK * 2 + PEEK_STEP_HEIGHT * 2 + 30) / 2 * s
    r_outer = PEEK_OD / 2
    r_inner = PEEK_ID / 2
    step_h = PEEK_STEP_HEIGHT
    thick = PEEK_THICK

    # Centerline
    add_centerline_h(msp, oy + (r_outer + 10) * s,
                     ox - 5 * s, ox + (thick + step_h + 10) * 2 * s)

    # Draw at 2:1 scale for clarity (within the allocated bbox)
    ds = s * 2.0  # detail scale

    def rx(r):
        return ox + (r_outer + r) * ds + 10 * s

    def ax(a):
        return oy + a * ds

    for sign in [1, -1]:
        pts = [
            (rx(sign * r_inner), ax(0)),
            (rx(sign * r_outer), ax(0)),
            (rx(sign * r_outer), ax(thick + step_h)),
            (rx(sign * r_inner), ax(thick + step_h)),
            (rx(sign * r_inner), ax(thick)),
            (rx(sign * r_inner), ax(0)),
        ]
        msp.add_lwpolyline(pts, dxfattribs={"layer": "OUTLINE"})
        add_section_hatch(msp, pts[:-1], pattern="ANSI32", scale=2.0)

    # Dimensions
    add_linear_dim(msp, (rx(r_outer) + 5 * s, ax(0)),
                   (rx(r_outer) + 5 * s, ax(thick)),
                   offset=5 * s, text=PEEK_THICK_TOL.text, angle=90)
    add_linear_dim(msp, (rx(r_outer) + 12 * s, ax(0)),
                   (rx(r_outer) + 12 * s, ax(thick + step_h)),
                   offset=5 * s, text=f"{thick + step_h}", angle=90)

    add_linear_dim(msp, (rx(-r_outer) - 3 * s, ax(0)),
                   (rx(-r_outer) - 3 * s, ax(step_h)),
                   offset=-5 * s, text=f"{step_h}", angle=90)

    # OD dim
    add_linear_dim(msp, (rx(-r_outer), ax(-3 * s)),
                   (rx(r_outer), ax(-3 * s)),
                   offset=-5 * s, text=PEEK_OD_TOL.dia_text, angle=0)

    # Surface symbol
    add_surface_symbol(msp, (rx(r_outer) + 2 * s, ax(thick + step_h) + 2 * s),
                       SURF_CRITICAL.ra)



def draw_peek_ring_sheet(output_dir: str) -> str:
    """Generate EE-001-02 PEEK ring three-view A3 sheet."""
    r = PEEK_OD / 2
    front_wh = (2 * r + 30, 2 * r + 30)
    top_wh = (front_wh[0], PEEK_THICK * 2 + PEEK_STEP_HEIGHT * 2 + 30)
    left_wh = (1, 1)  # omitted for symmetric part

    sheet = ThreeViewSheet(
        part_no="GIS-EE-001-02",
        name="PEEK绝缘环",
        material="PEEK (聚醚醚酮)",
        scale="2:1",
        weight_g=25,
        date="2026-03-16",
    )
    sheet.draw_front(peek_front_view, bbox=front_wh)
    sheet.draw_top(peek_top_view, bbox=top_wh)
    # Left view omitted (symmetric part)
    return sheet.save(output_dir, material_type="peek")


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    draw_peek_ring_sheet(out)
    print("Done.")
