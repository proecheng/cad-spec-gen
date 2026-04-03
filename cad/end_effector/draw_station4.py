"""
Station 4 UHF Bracket Engineering Drawing — EE-005-02

GB/T 三视图 A3：
  - 主视图：正面 L形 50×25（含传感器孔）
  - 俯视图：顶面 50×40 矩形（含安装孔位）
  - 左视图：侧面 L形截面 40×25

All geometry from params.py.
"""

import math
import os

from params import (
    S4_SENSOR_DIA, S4_SENSOR_H,
    S4_BRACKET_W, S4_BRACKET_D, S4_BRACKET_H, S4_BRACKET_THICK,
    S4_ENVELOPE_DIA, S4_ENVELOPE_H,
    MOUNT_FACE, MOUNT_BOLT_PCD, MOUNT_BOLT_DIA,
    LEMO_BORE_DIA,
)
from drawing import (
    add_linear_dim, add_diameter_dim,
    add_section_hatch,
    add_centerline_h, add_centerline_v, add_centerline_cross,
)
from draw_three_view import ThreeViewSheet


def uhf_bracket_front_view(msp, ox, oy, scale):
    """Front view: L-bracket front face (top plate visible, sensor bore hidden)."""
    s = scale
    # centre → bottom-left origin
    oy = oy - (S4_BRACKET_H + 25) / 2 * s
    bw = S4_BRACKET_W
    bh = S4_BRACKET_H
    bd = S4_BRACKET_D
    bt = S4_BRACKET_THICK
    hw = bw / 2

    cx = ox + (hw + 10) * s
    cy_top = oy + (bh + 10) * s

    # Top plate (full width × thickness)
    msp.add_lwpolyline([
        (cx - hw * s, cy_top), (cx + hw * s, cy_top),
        (cx + hw * s, cy_top - bt * s), (cx - hw * s, cy_top - bt * s),
        (cx - hw * s, cy_top),
    ], dxfattribs={"layer": "OUTLINE"})
    add_section_hatch(msp, [
        (cx - hw * s, cy_top), (cx + hw * s, cy_top),
        (cx + hw * s, cy_top - bt * s), (cx - hw * s, cy_top - bt * s),
    ], pattern="ANSI31", scale=1.5)

    # Vertical leg (right side, width=bd, extends down)
    leg_left = cx + hw * s - bd * s
    leg_right = cx + hw * s
    leg_bottom = cy_top - bh * s
    msp.add_lwpolyline([
        (leg_left, cy_top - bt * s), (leg_right, cy_top - bt * s),
        (leg_right, leg_bottom), (leg_left, leg_bottom),
        (leg_left, cy_top - bt * s),
    ], dxfattribs={"layer": "OUTLINE"})

    # Sensor bore (hidden circle on vertical leg)
    sensor_r = S4_SENSOR_DIA / 2
    sensor_cx = (leg_left + leg_right) / 2
    sensor_cy = cy_top - bh * s + (bh - bt) / 2 * s
    msp.add_circle((sensor_cx, sensor_cy), sensor_r * s,
                   dxfattribs={"layer": "HIDDEN"})

    # Mount bolt holes in top plate
    bolt_half = MOUNT_BOLT_PCD / 4
    for bx_off in [-bolt_half, bolt_half]:
        for by_off in [-bolt_half, bolt_half]:
            msp.add_circle((cx + bx_off * s, cy_top - bt / 2 * s + by_off * s),
                           (MOUNT_BOLT_DIA / 2) * s,
                           dxfattribs={"layer": "OUTLINE"})

    # LEMO bore on vertical leg
    msp.add_circle((sensor_cx + (bd / 3) * s, sensor_cy + 5 * s),
                   (LEMO_BORE_DIA / 2) * s,
                   dxfattribs={"layer": "OUTLINE"})

    # Centerlines
    add_centerline_v(msp, sensor_cx, cy_top + 3 * s, leg_bottom - 3 * s)

    # Dimensions
    add_linear_dim(msp, (cx - hw * s, cy_top + 5 * s),
                   (cx + hw * s, cy_top + 5 * s),
                   offset=8 * s, text=f"{bw}", angle=0)
    add_linear_dim(msp, (leg_right + 5 * s, cy_top),
                   (leg_right + 5 * s, leg_bottom),
                   offset=8 * s, text=f"{bh}", angle=90)
    add_linear_dim(msp, (leg_left, leg_bottom - 5 * s),
                   (leg_right, leg_bottom - 5 * s),
                   offset=-5 * s, text=f"{bd}", angle=0)
    add_linear_dim(msp, (cx - hw * s - 5 * s, cy_top),
                   (cx - hw * s - 5 * s, cy_top - bt * s),
                   offset=-5 * s, text=f"{bt}", angle=90)

    # Sensor bore dim
    add_diameter_dim(msp, (sensor_cx, sensor_cy), sensor_r * s,
                     angle_deg=0, text=f"Φ{S4_SENSOR_DIA}")


def uhf_bracket_top_view(msp, ox, oy, scale):
    """Top view: 50×40 rectangle with bolt holes."""
    s = scale
    bw = S4_BRACKET_W
    bd = S4_BRACKET_D
    hw = bw / 2
    hd = bd / 2

    cx = ox + (hw + 10) * s
    cy = oy + (hd + 5) * s

    msp.add_lwpolyline([
        (cx - hw * s, cy - hd * s), (cx + hw * s, cy - hd * s),
        (cx + hw * s, cy + hd * s), (cx - hw * s, cy + hd * s),
        (cx - hw * s, cy - hd * s),
    ], dxfattribs={"layer": "OUTLINE"})

    # Mount bolt holes (4×M3)
    bolt_half = MOUNT_BOLT_PCD / 4
    for bx_off in [-bolt_half, bolt_half]:
        for by_off in [-bolt_half, bolt_half]:
            msp.add_circle((cx + bx_off * s, cy + by_off * s),
                           (MOUNT_BOLT_DIA / 2) * s,
                           dxfattribs={"layer": "OUTLINE"})

    add_centerline_v(msp, cx, cy - (hd + 5) * s, cy + (hd + 5) * s)
    add_centerline_h(msp, cy, cx - (hw + 5) * s, cx + (hw + 5) * s)

    # Dimensions
    add_linear_dim(msp, (cx - hw * s, cy - hd * s - 5 * s),
                   (cx + hw * s, cy - hd * s - 5 * s),
                   offset=-5 * s, text=f"{bw}", angle=0)
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy - hd * s),
                   (cx + hw * s + 5 * s, cy + hd * s),
                   offset=5 * s, text=f"{bd}", angle=90)



def uhf_bracket_left_view(msp, ox, oy, scale):
    """Left view: L-shaped cross section 40×25."""
    s = scale
    # centre → bottom-left origin
    oy = oy - (S4_BRACKET_H + 25) / 2 * s
    bd = S4_BRACKET_D
    bh = S4_BRACKET_H
    bt = S4_BRACKET_THICK
    hd = bd / 2

    cx = ox + (hd + 5) * s
    cy_top = oy + (bh + 10) * s

    # L-shape profile
    pts = [
        (cx - hd * s, cy_top),                    # top-left
        (cx + hd * s, cy_top),                    # top-right
        (cx + hd * s, cy_top - bt * s),           # step right
        (cx - hd * s + bt * s, cy_top - bt * s),  # step inner
        (cx - hd * s + bt * s, cy_top - bh * s),  # bottom inner
        (cx + hd * s, cy_top - bh * s),           # bottom-right
        (cx + hd * s, cy_top - bh * s + bt * s),  # Hmm, need L profile
    ]
    # Actually L: top plate full width + vertical leg on right
    msp.add_lwpolyline([
        (cx - hd * s, cy_top),
        (cx + hd * s, cy_top),
        (cx + hd * s, cy_top - bh * s),
        (cx + hd * s - bt * s, cy_top - bh * s),
        (cx + hd * s - bt * s, cy_top - bt * s),
        (cx - hd * s, cy_top - bt * s),
        (cx - hd * s, cy_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Hatch
    # Top plate
    add_section_hatch(msp, [
        (cx - hd * s, cy_top), (cx + hd * s, cy_top),
        (cx + hd * s, cy_top - bt * s), (cx - hd * s, cy_top - bt * s),
    ], pattern="ANSI31", scale=1.5)
    # Vertical leg
    add_section_hatch(msp, [
        (cx + hd * s - bt * s, cy_top - bt * s),
        (cx + hd * s, cy_top - bt * s),
        (cx + hd * s, cy_top - bh * s),
        (cx + hd * s - bt * s, cy_top - bh * s),
    ], pattern="ANSI31", scale=1.5)

    # Dimensions
    add_linear_dim(msp, (cx - hd * s, cy_top + 5 * s),
                   (cx + hd * s, cy_top + 5 * s),
                   offset=5 * s, text=f"{bd}", angle=0)
    add_linear_dim(msp, (cx + hd * s + 5 * s, cy_top),
                   (cx + hd * s + 5 * s, cy_top - bh * s),
                   offset=5 * s, text=f"{bh}", angle=90)


def uhf_bracket_auxiliary_c(msp, ox, oy, scale):
    """Auxiliary view C: inner face of vertical leg (looking from inside).

    Shows sensor bore (visible) and LEMO bore from the fold-inner perspective.
    """
    s = scale
    # centre → bottom-left origin
    oy = oy - (S4_BRACKET_H - S4_BRACKET_THICK + 20) / 2 * s
    bd = S4_BRACKET_D
    bh = S4_BRACKET_H
    bt = S4_BRACKET_THICK
    hd = bd / 2

    cx = ox + (hd + 5) * s
    cy_top = oy + ((bh - bt) + 10) * s
    leg_h = bh - bt

    # Vertical leg inner face (rectangle bd × (bh-bt))
    msp.add_lwpolyline([
        (cx - hd * s, cy_top), (cx + hd * s, cy_top),
        (cx + hd * s, cy_top - leg_h * s), (cx - hd * s, cy_top - leg_h * s),
        (cx - hd * s, cy_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Sensor bore (visible through-hole)
    sensor_r = S4_SENSOR_DIA / 2
    sensor_cy = cy_top - leg_h / 2 * s
    msp.add_circle((cx, sensor_cy), sensor_r * s,
                   dxfattribs={"layer": "OUTLINE"})

    # LEMO bore
    lemo_cy = sensor_cy + 5 * s
    lemo_cx = cx + (bd / 3) * s
    msp.add_circle((lemo_cx, lemo_cy), (LEMO_BORE_DIA / 2) * s,
                   dxfattribs={"layer": "OUTLINE"})

    # Centerlines
    add_centerline_cross(msp, (cx, sensor_cy), size=(hd + 5) * s)

    # Dimensions
    add_diameter_dim(msp, (cx, sensor_cy), sensor_r * s,
                     angle_deg=45, text=f"Φ{S4_SENSOR_DIA}")
    add_diameter_dim(msp, (lemo_cx, lemo_cy), (LEMO_BORE_DIA / 2) * s,
                     angle_deg=315, text=f"Φ{LEMO_BORE_DIA}")
    add_linear_dim(msp, (cx - hd * s, cy_top + 3 * s),
                   (cx + hd * s, cy_top + 3 * s),
                   offset=5 * s, text=f"{bd}", angle=0)
    add_linear_dim(msp, (cx + hd * s + 5 * s, cy_top),
                   (cx + hd * s + 5 * s, cy_top - leg_h * s),
                   offset=5 * s, text=f"{leg_h}", angle=90)


def draw_uhf_bracket_sheet(output_dir: str) -> str:
    """Generate EE-005-02 UHF bracket three-view A3 sheet."""
    front_wh = (S4_BRACKET_W + 30, S4_BRACKET_H + 25)
    top_wh = (S4_BRACKET_W + 30, S4_BRACKET_D + 20)
    left_wh = (S4_BRACKET_D + 15, front_wh[1])
    aux_wh = (S4_BRACKET_D + 15, S4_BRACKET_H - S4_BRACKET_THICK + 20)

    sheet = ThreeViewSheet(
        part_no="GIS-EE-005-02",
        name="UHF安装支架",
        material="6061 铝合金",
        scale="1:1",
        weight_g=85,
        date="2026-03-16",
    )
    sheet.draw_front(uhf_bracket_front_view, bbox=front_wh)
    sheet.draw_top(uhf_bracket_top_view, bbox=top_wh)
    sheet.draw_left(uhf_bracket_left_view, bbox=left_wh)
    sheet.draw_auxiliary(uhf_bracket_auxiliary_c, "C", bbox=aux_wh,
                         position="right")
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    draw_uhf_bracket_sheet(out)
    print("Done.")
