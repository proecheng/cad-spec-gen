"""
Station 2 AE Module Engineering Drawings — EE-003-03 / EE-003-04

Two self-made parts, each gets a GB/T 三视图 A3 sheet:
  1. EE-003-03 弹簧限力机构 — 主视图（轴向剖视）+ 俯视图（端面 Φ12）
  2. EE-003-04 柔性万向节 — 主视图（外形 Φ30）+ 俯视图（剖面）

All geometry from params.py.
"""

import math
import os

from params import (
    S2_ENDPLATE_DIA, S2_ENDPLATE_THICK,
    S2_SLEEVE_OD, S2_SLEEVE_ID, S2_SLEEVE_H,
    S2_SPRING_OD, S2_SPRING_FREE_L,
    S2_GUIDE_DIA, S2_GUIDE_LENGTH,
    S2_SHIM_DIA, S2_SHIM_THICK,
    S2_GIMBAL_OD, S2_GIMBAL_ID, S2_GIMBAL_H,
    S2_GIMBAL_FLANGE_DIA, S2_GIMBAL_FLANGE_THICK,
)
from drawing import (
    add_linear_dim, add_diameter_dim,
    add_section_hatch,
    add_centerline_h, add_centerline_v, add_centerline_cross,
)
from draw_three_view import ThreeViewSheet


# ═══════════════════════════════════════════════════════════════════════════════
# EE-003-03 弹簧限力机构
# ═══════════════════════════════════════════════════════════════════════════════

def spring_limiter_front_view(msp, ox, oy, scale):
    """Front view (axial section): stacked endplate-sleeve-endplate."""
    s = scale
    # centre → bottom-left origin
    total_h = S2_ENDPLATE_THICK * 2 + S2_SHIM_THICK + S2_SLEEVE_H
    oy = oy - (total_h + 15) / 2 * s
    ep_r = S2_ENDPLATE_DIA / 2
    slv_or = S2_SLEEVE_OD / 2
    slv_ir = S2_SLEEVE_ID / 2
    spr_r = S2_SPRING_OD / 2
    guide_r = S2_GUIDE_DIA / 2
    shim_r = S2_SHIM_DIA / 2
    ep_t = S2_ENDPLATE_THICK
    slv_h = S2_SLEEVE_H
    shim_t = S2_SHIM_THICK

    # Total height
    total_h = ep_t + shim_t + slv_h + ep_t

    cx = ox + (ep_r + 10) * s
    cy_top = oy + (total_h + 5) * s

    # Centerline
    add_centerline_v(msp, cx, cy_top + 3 * s, oy - 3 * s)

    y = cy_top  # current Y (top-down stacking)

    # Upper endplate
    for sign in [-1, 1]:
        pts = [(cx + sign * ep_r * s, y),
               (cx + sign * ep_r * s, y - ep_t * s)]
        msp.add_line(pts[0], pts[1], dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx - ep_r * s, y), (cx + ep_r * s, y),
                 dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx - ep_r * s, y - ep_t * s),
                 (cx + ep_r * s, y - ep_t * s),
                 dxfattribs={"layer": "OUTLINE"})
    add_section_hatch(msp, [
        (cx - ep_r * s, y), (cx + ep_r * s, y),
        (cx + ep_r * s, y - ep_t * s), (cx - ep_r * s, y - ep_t * s),
    ], pattern="ANSI31", scale=1.5)
    y -= ep_t * s

    # Shim
    msp.add_line((cx - shim_r * s, y), (cx + shim_r * s, y),
                 dxfattribs={"layer": "THIN"})
    y -= shim_t * s
    msp.add_line((cx - shim_r * s, y), (cx + shim_r * s, y),
                 dxfattribs={"layer": "THIN"})

    # Sleeve + spring region
    for sign in [-1, 1]:
        # Sleeve outer
        msp.add_line((cx + sign * slv_or * s, y),
                     (cx + sign * slv_or * s, y - slv_h * s),
                     dxfattribs={"layer": "OUTLINE"})
        # Sleeve inner
        msp.add_line((cx + sign * slv_ir * s, y),
                     (cx + sign * slv_ir * s, y - slv_h * s),
                     dxfattribs={"layer": "THIN"})
        # Spring OD
        msp.add_line((cx + sign * spr_r * s, y),
                     (cx + sign * spr_r * s, y - slv_h * s),
                     dxfattribs={"layer": "THIN"})
        # Guide shaft
        msp.add_line((cx + sign * guide_r * s, y),
                     (cx + sign * guide_r * s, y - slv_h * s),
                     dxfattribs={"layer": "THIN"})

    msp.add_line((cx - slv_or * s, y), (cx + slv_or * s, y),
                 dxfattribs={"layer": "OUTLINE"})
    y -= slv_h * s
    msp.add_line((cx - slv_or * s, y), (cx + slv_or * s, y),
                 dxfattribs={"layer": "OUTLINE"})

    # Sleeve wall hatch
    for sign in [-1, 1]:
        add_section_hatch(msp, [
            (cx + sign * slv_ir * s, y + slv_h * s),
            (cx + sign * slv_or * s, y + slv_h * s),
            (cx + sign * slv_or * s, y),
            (cx + sign * slv_ir * s, y),
        ], pattern="ANSI31", scale=1.0)

    # Lower endplate
    msp.add_line((cx - ep_r * s, y), (cx + ep_r * s, y),
                 dxfattribs={"layer": "OUTLINE"})
    y -= ep_t * s
    msp.add_line((cx - ep_r * s, y), (cx + ep_r * s, y),
                 dxfattribs={"layer": "OUTLINE"})
    for sign in [-1, 1]:
        msp.add_line((cx + sign * ep_r * s, y),
                     (cx + sign * ep_r * s, y + ep_t * s),
                     dxfattribs={"layer": "OUTLINE"})
    add_section_hatch(msp, [
        (cx - ep_r * s, y + ep_t * s), (cx + ep_r * s, y + ep_t * s),
        (cx + ep_r * s, y), (cx - ep_r * s, y),
    ], pattern="ANSI31", scale=1.5)

    # Dimensions
    dim_x = cx + (ep_r + 5) * s
    add_linear_dim(msp, (dim_x, cy_top), (dim_x, cy_top - total_h * s),
                   offset=8 * s, text=f"{total_h:.1f}", angle=90)
    add_diameter_dim(msp, (cx, cy_top - ep_t * s / 2), ep_r * s,
                     angle_deg=0, text=f"Φ{S2_ENDPLATE_DIA}")
    add_diameter_dim(msp, (cx, cy_top - (ep_t + shim_t + slv_h / 2) * s),
                     slv_or * s, angle_deg=0, text=f"Φ{S2_SLEEVE_OD}")



def spring_limiter_top_view(msp, ox, oy, scale):
    """Top view: circular end face Φ12 with guide bore."""
    s = scale
    ep_r = S2_ENDPLATE_DIA / 2
    guide_r = S2_GUIDE_DIA / 2

    cx = ox + (ep_r + 10) * s
    cy = oy + (ep_r + 5) * s

    msp.add_circle((cx, cy), ep_r * s, dxfattribs={"layer": "OUTLINE"})
    msp.add_circle((cx, cy), guide_r * s, dxfattribs={"layer": "OUTLINE"})
    add_centerline_cross(msp, (cx, cy), size=(ep_r + 5) * s)

    add_diameter_dim(msp, (cx, cy), ep_r * s, angle_deg=45,
                     text=f"Φ{S2_ENDPLATE_DIA}")
    add_diameter_dim(msp, (cx, cy), guide_r * s, angle_deg=225,
                     text=f"Φ{S2_GUIDE_DIA}")


def draw_spring_limiter_sheet(output_dir: str) -> str:
    """Generate EE-003-03 spring limiter three-view A3 sheet."""
    total_h = S2_ENDPLATE_THICK * 2 + S2_SHIM_THICK + S2_SLEEVE_H
    r = S2_ENDPLATE_DIA / 2
    front_wh = (2 * r + 40, total_h + 15)
    top_wh = (2 * r + 25, 2 * r + 15)

    sheet = ThreeViewSheet(
        part_no="GIS-EE-003-03",
        name="弹簧限力机构",
        material="SUS303 + SUS304 弹簧钢",
        scale="2:1",
        weight_g=16,
        date="2026-03-16",
    )
    sheet.draw_front(spring_limiter_front_view, bbox=front_wh)
    sheet.draw_top(spring_limiter_top_view, bbox=top_wh)
    return sheet.save(output_dir, material_type="steel")


# ═══════════════════════════════════════════════════════════════════════════════
# EE-003-04 柔性万向节
# ═══════════════════════════════════════════════════════════════════════════════

def gimbal_front_view(msp, ox, oy, scale):
    """Front view: outer profile Φ30 with flange."""
    s = scale
    # centre → bottom-left origin
    total_h = S2_GIMBAL_H + S2_GIMBAL_FLANGE_THICK
    oy = oy - (total_h + 15) / 2 * s
    od_r = S2_GIMBAL_OD / 2
    id_r = S2_GIMBAL_ID / 2
    fl_r = S2_GIMBAL_FLANGE_DIA / 2
    h = S2_GIMBAL_H
    fl_t = S2_GIMBAL_FLANGE_THICK
    total_h = h + fl_t

    cx = ox + (od_r + 10) * s
    cy_top = oy + (total_h + 5) * s

    add_centerline_v(msp, cx, cy_top + 3 * s, oy - 3 * s)

    # Rubber body (section)
    for sign in [-1, 1]:
        msp.add_line((cx + sign * od_r * s, cy_top),
                     (cx + sign * od_r * s, cy_top - h * s),
                     dxfattribs={"layer": "OUTLINE"})
        msp.add_line((cx + sign * id_r * s, cy_top),
                     (cx + sign * id_r * s, cy_top - h * s),
                     dxfattribs={"layer": "HIDDEN"})

    msp.add_line((cx - od_r * s, cy_top), (cx + od_r * s, cy_top),
                 dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx - od_r * s, cy_top - h * s),
                 (cx + od_r * s, cy_top - h * s),
                 dxfattribs={"layer": "OUTLINE"})

    # Hatch rubber
    for sign in [-1, 1]:
        add_section_hatch(msp, [
            (cx + sign * id_r * s, cy_top),
            (cx + sign * od_r * s, cy_top),
            (cx + sign * od_r * s, cy_top - h * s),
            (cx + sign * id_r * s, cy_top - h * s),
        ], pattern="ANSI37", scale=1.5)

    # Flange below
    y_fl = cy_top - h * s
    for sign in [-1, 1]:
        msp.add_line((cx + sign * fl_r * s, y_fl),
                     (cx + sign * fl_r * s, y_fl - fl_t * s),
                     dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx - fl_r * s, y_fl - fl_t * s),
                 (cx + fl_r * s, y_fl - fl_t * s),
                 dxfattribs={"layer": "OUTLINE"})
    add_section_hatch(msp, [
        (cx - fl_r * s, y_fl), (cx + fl_r * s, y_fl),
        (cx + fl_r * s, y_fl - fl_t * s), (cx - fl_r * s, y_fl - fl_t * s),
    ], pattern="ANSI31", scale=1.5)

    # Dimensions
    add_diameter_dim(msp, (cx, cy_top - h / 2 * s), od_r * s,
                     angle_deg=0, text=f"Φ{S2_GIMBAL_OD}")
    add_diameter_dim(msp, (cx, cy_top - h / 2 * s), id_r * s,
                     angle_deg=180, text=f"Φ{S2_GIMBAL_ID}")
    dim_x = cx + (od_r + 5) * s
    add_linear_dim(msp, (dim_x, cy_top), (dim_x, cy_top - h * s),
                   offset=8 * s, text=f"{h}", angle=90)
    add_linear_dim(msp, (dim_x, y_fl), (dim_x, y_fl - fl_t * s),
                   offset=8 * s, text=f"{fl_t}", angle=90)



def gimbal_top_view(msp, ox, oy, scale):
    """Top view: circular face Φ30 with inner bore."""
    s = scale
    od_r = S2_GIMBAL_OD / 2
    id_r = S2_GIMBAL_ID / 2

    cx = ox + (od_r + 10) * s
    cy = oy + (od_r + 5) * s

    msp.add_circle((cx, cy), od_r * s, dxfattribs={"layer": "OUTLINE"})
    msp.add_circle((cx, cy), id_r * s, dxfattribs={"layer": "OUTLINE"})
    add_centerline_cross(msp, (cx, cy), size=(od_r + 5) * s)

    add_diameter_dim(msp, (cx, cy), od_r * s, angle_deg=45,
                     text=f"Φ{S2_GIMBAL_OD}")
    add_diameter_dim(msp, (cx, cy), id_r * s, angle_deg=225,
                     text=f"Φ{S2_GIMBAL_ID}")


def draw_gimbal_sheet(output_dir: str) -> str:
    """Generate EE-003-04 gimbal three-view A3 sheet."""
    total_h = S2_GIMBAL_H + S2_GIMBAL_FLANGE_THICK
    r = S2_GIMBAL_OD / 2
    front_wh = (2 * r + 40, total_h + 15)
    top_wh = (2 * r + 25, 2 * r + 15)

    sheet = ThreeViewSheet(
        part_no="GIS-EE-003-04",
        name="柔性万向节",
        material="硅橡胶 + 6061 铝合金",
        scale="2:1",
        weight_g=35,
        date="2026-03-16",
    )
    sheet.draw_front(gimbal_front_view, bbox=front_wh)
    sheet.draw_top(gimbal_top_view, bbox=top_wh)
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    draw_spring_limiter_sheet(out)
    draw_gimbal_sheet(out)
    print("Done.")
