"""
Station 3 Cleaner Engineering Drawings — EE-004-01 / EE-004-12

Two self-made parts:
  1. EE-004-01 清洁模块壳体 — 三视图（50×40×120mm 箱体件）
  2. EE-004-12 清洁窗口翻盖 — 两视图（薄片硅橡胶件）

All geometry from params.py.
"""

import os

from params import (
    S3_BODY_W, S3_BODY_D, S3_BODY_H, S3_WALL_THICK,
    S3_SUPPLY_FULL_OD, S3_TAKEUP_FULL_OD,
    S3_SPOOL_SPACING,
    S3_PAD_W, S3_PAD_D, S3_PAD_H,
    S3_WINDOW_W, S3_WINDOW_D,
    S3_MOTOR_DIA,
    S3_FLAP_THICK, S3_FLAP_W,
    S3_CASSETTE_W, S3_CASSETTE_D, S3_CASSETTE_H,
    MOUNT_FACE, LEMO_BORE_DIA,
)
from drawing import (
    add_linear_dim, add_diameter_dim,
    add_section_hatch, add_section_hatch_with_holes,
    add_section_symbol,
    add_centerline_h, add_centerline_v,
)
from draw_three_view import ThreeViewSheet


# ═══════════════════════════════════════════════════════════════════════════════
# EE-004-01 清洁模块壳体
# ═══════════════════════════════════════════════════════════════════════════════

def cleaner_front_view(msp, ox, oy, scale):
    """Front view: 50×120 face with dual spool cavities (hidden circles)."""
    s = scale
    w = S3_BODY_W
    h = S3_BODY_H
    wall = S3_WALL_THICK
    hw = w / 2

    cx = ox + (hw + 10) * s
    cy_top = oy + (h + 10) * s

    # Shell
    msp.add_lwpolyline([
        (cx - hw * s, cy_top), (cx + hw * s, cy_top),
        (cx + hw * s, cy_top - h * s), (cx - hw * s, cy_top - h * s),
        (cx - hw * s, cy_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Inner
    ihw = hw - wall
    msp.add_lwpolyline([
        (cx - ihw * s, cy_top - wall * s),
        (cx + ihw * s, cy_top - wall * s),
        (cx + ihw * s, cy_top - (h - wall) * s),
        (cx - ihw * s, cy_top - (h - wall) * s),
        (cx - ihw * s, cy_top - wall * s),
    ], dxfattribs={"layer": "HIDDEN"})

    # Spool positions (hidden circles)
    spool_y1 = cy_top - (wall + 5 + S3_SUPPLY_FULL_OD / 2) * s
    spool_y2 = spool_y1 - S3_SPOOL_SPACING * s
    for sy, od in [(spool_y1, S3_SUPPLY_FULL_OD), (spool_y2, S3_TAKEUP_FULL_OD)]:
        msp.add_circle((cx, sy), (od / 2) * s, dxfattribs={"layer": "HIDDEN"})

    # Cleaning window at bottom
    win_hw = S3_WINDOW_W / 2
    win_y = cy_top - h * s
    msp.add_line((cx - win_hw * s, win_y), (cx - win_hw * s, win_y + wall * s),
                 dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx + win_hw * s, win_y), (cx + win_hw * s, win_y + wall * s),
                 dxfattribs={"layer": "OUTLINE"})

    # Motor bore (hidden, top-right)
    motor_r = S3_MOTOR_DIA / 2
    msp.add_circle((cx + (hw - 10) * s, cy_top - 15 * s),
                   motor_r * s, dxfattribs={"layer": "HIDDEN"})

    # Centerlines
    add_centerline_v(msp, cx, cy_top + 5 * s, cy_top - (h + 5) * s)

    # Section cut line A-A (vertical, through center)
    add_section_symbol(msp,
                       start=(cx, cy_top + 8 * s),
                       end=(cx, cy_top - (h + 8) * s),
                       label="A", arrow_dir="right")

    # Dimensions
    add_linear_dim(msp, (cx - hw * s, cy_top + 5 * s),
                   (cx + hw * s, cy_top + 5 * s),
                   offset=8 * s, text=f"{w}", angle=0)
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy_top),
                   (cx + hw * s + 5 * s, cy_top - h * s),
                   offset=8 * s, text=f"{h}", angle=90)

    # Spool spacing dim
    add_linear_dim(msp, (cx - hw * s - 5 * s, spool_y1),
                   (cx - hw * s - 5 * s, spool_y2),
                   offset=-8 * s, text=f"{S3_SPOOL_SPACING}", angle=90)



def cleaner_section_aa(msp, ox, oy, scale):
    """Section A-A: longitudinal cut through center of width, showing
    dual spool cavities, inner walls, and window opening."""
    s = scale
    d, h, wall = S3_BODY_D, S3_BODY_H, S3_WALL_THICK
    hd = d / 2

    cx = ox + (hd + 5) * s
    cy_top = oy + (h + 10) * s

    ol = cx - hd * s
    or_ = cx + hd * s
    ot = cy_top
    ob = cy_top - h * s

    # Outer profile
    msp.add_lwpolyline([
        (ol, ob), (or_, ob), (or_, ot), (ol, ot), (ol, ob),
    ], dxfattribs={"layer": "OUTLINE"})

    # Inner cavity (visible in section)
    il = cx - (hd - wall) * s
    ir = cx + (hd - wall) * s
    it = cy_top - wall * s
    ib = cy_top - (h - wall) * s
    msp.add_lwpolyline([
        (il, ib), (ir, ib), (ir, it), (il, it), (il, ib),
    ], dxfattribs={"layer": "OUTLINE"})

    # Spool cavities (circles cut through center → rectangles in section)
    sup_r = (S3_SUPPLY_FULL_OD / 2) * s
    sup_cy = cy_top - (wall + 5 + S3_SUPPLY_FULL_OD / 2) * s
    take_cy = sup_cy - S3_SPOOL_SPACING * s
    take_r = (S3_TAKEUP_FULL_OD / 2) * s

    for spy, spr in [(sup_cy, sup_r), (take_cy, take_r)]:
        msp.add_lwpolyline([
            (cx - spr, spy - spr), (cx + spr, spy - spr),
            (cx + spr, spy + spr), (cx - spr, spy + spr),
            (cx - spr, spy - spr),
        ], dxfattribs={"layer": "OUTLINE"})

    # Window opening at bottom
    win_hd = S3_WINDOW_D / 2
    msp.add_lwpolyline([
        (cx - win_hd * s, ob), (cx + win_hd * s, ob),
        (cx + win_hd * s, ob + wall * s), (cx - win_hd * s, ob + wall * s),
        (cx - win_hd * s, ob),
    ], dxfattribs={"layer": "OUTLINE"})

    # Hatch walls (left and right)
    add_section_hatch_with_holes(msp,
        outer_boundary=[(ol, ob), (il, ob), (il, ot), (ol, ot)],
        pattern="ANSI31", scale=1.5)
    add_section_hatch_with_holes(msp,
        outer_boundary=[(ir, ob), (or_, ob), (or_, ot), (ir, ot)],
        pattern="ANSI31", scale=1.5)
    # Top wall
    add_section_hatch_with_holes(msp,
        outer_boundary=[(il, it), (ir, it), (ir, ot), (il, ot)],
        pattern="ANSI31", scale=1.5)
    # Bottom wall (with window hole)
    if (cx - win_hd * s) > il:
        add_section_hatch_with_holes(msp,
            outer_boundary=[(il, ob), (cx - win_hd * s, ob),
                            (cx - win_hd * s, ib), (il, ib)])
    if (cx + win_hd * s) < ir:
        add_section_hatch_with_holes(msp,
            outer_boundary=[(cx + win_hd * s, ob), (ir, ob),
                            (ir, ib), (cx + win_hd * s, ib)])

    # Centerline
    add_centerline_v(msp, cx, ot + 5 * s, ob - 5 * s)

    # Dimensions
    add_linear_dim(msp, (ol, ot + 5 * s), (or_, ot + 5 * s),
                   offset=5 * s, text=f"{d}", angle=0)
    add_linear_dim(msp, (or_ + 5 * s, ot), (or_ + 5 * s, ob),
                   offset=5 * s, text=f"{h}", angle=90)
    add_linear_dim(msp, (ol - 3 * s, ot), (ol - 3 * s, it),
                   offset=-3 * s, text=f"{wall}", angle=90)


def cleaner_top_view(msp, ox, oy, scale):
    """Top view: 50×40 rectangle with cassette opening."""
    s = scale
    w = S3_BODY_W
    d = S3_BODY_D
    hw = w / 2
    hd = d / 2

    cx = ox + (hw + 10) * s
    cy = oy + (hd + 5) * s

    msp.add_lwpolyline([
        (cx - hw * s, cy - hd * s), (cx + hw * s, cy - hd * s),
        (cx + hw * s, cy + hd * s), (cx - hw * s, cy + hd * s),
        (cx - hw * s, cy - hd * s),
    ], dxfattribs={"layer": "OUTLINE"})

    # Inner
    wall = S3_WALL_THICK
    ihw = hw - wall
    ihd = hd - wall
    msp.add_lwpolyline([
        (cx - ihw * s, cy - ihd * s), (cx + ihw * s, cy - ihd * s),
        (cx + ihw * s, cy + ihd * s), (cx - ihw * s, cy + ihd * s),
        (cx - ihw * s, cy - ihd * s),
    ], dxfattribs={"layer": "HIDDEN"})

    # Cassette opening (dashed)
    cass_hw = S3_CASSETTE_W / 2
    cass_hd = S3_CASSETTE_D / 2
    msp.add_lwpolyline([
        (cx - cass_hw * s, cy - cass_hd * s),
        (cx + cass_hw * s, cy - cass_hd * s),
        (cx + cass_hw * s, cy + cass_hd * s),
        (cx - cass_hw * s, cy + cass_hd * s),
        (cx - cass_hw * s, cy - cass_hd * s),
    ], dxfattribs={"layer": "HIDDEN"})

    add_centerline_v(msp, cx, cy - (hd + 5) * s, cy + (hd + 5) * s)
    add_centerline_h(msp, cy, cx - (hw + 5) * s, cx + (hw + 5) * s)

    # Dimensions
    add_linear_dim(msp, (cx - hw * s, cy - hd * s - 5 * s),
                   (cx + hw * s, cy - hd * s - 5 * s),
                   offset=-5 * s, text=f"{w}", angle=0)
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy - hd * s),
                   (cx + hw * s + 5 * s, cy + hd * s),
                   offset=5 * s, text=f"{d}", angle=90)



def cleaner_left_view(msp, ox, oy, scale):
    """Left view: 40×120 side with cleaning window opening."""
    s = scale
    d = S3_BODY_D
    h = S3_BODY_H
    wall = S3_WALL_THICK
    hd = d / 2

    cx = ox + (hd + 5) * s
    cy_top = oy + (h + 10) * s

    msp.add_lwpolyline([
        (cx - hd * s, cy_top), (cx + hd * s, cy_top),
        (cx + hd * s, cy_top - h * s), (cx - hd * s, cy_top - h * s),
        (cx - hd * s, cy_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Window at bottom
    win_hd = S3_WINDOW_D / 2
    win_y = cy_top - h * s
    msp.add_line((cx - win_hd * s, win_y),
                 (cx - win_hd * s, win_y + wall * s),
                 dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx + win_hd * s, win_y),
                 (cx + win_hd * s, win_y + wall * s),
                 dxfattribs={"layer": "OUTLINE"})

    # Flap indication
    flap_hd = S3_FLAP_W / 2
    msp.add_lwpolyline([
        (cx - flap_hd * s, win_y),
        (cx + flap_hd * s, win_y),
        (cx + flap_hd * s, win_y - S3_FLAP_THICK * s),
        (cx - flap_hd * s, win_y - S3_FLAP_THICK * s),
        (cx - flap_hd * s, win_y),
    ], dxfattribs={"layer": "THIN"})

    add_centerline_v(msp, cx, cy_top + 3 * s, win_y - 5 * s)

    # Dimensions
    add_linear_dim(msp, (cx - hd * s, cy_top + 5 * s),
                   (cx + hd * s, cy_top + 5 * s),
                   offset=5 * s, text=f"{d}", angle=0)
    add_linear_dim(msp, (cx + hd * s + 5 * s, cy_top),
                   (cx + hd * s + 5 * s, cy_top - h * s),
                   offset=5 * s, text=f"{h}", angle=90)


def draw_cleaner_body_sheet(output_dir: str) -> str:
    """Generate EE-004-01 cleaner body three-view A3 sheet."""
    front_wh = (S3_BODY_W + 30, S3_BODY_H + 25)
    top_wh = (S3_BODY_W + 30, S3_BODY_D + 20)
    left_wh = (S3_BODY_D + 15, front_wh[1])
    section_wh = (S3_BODY_D + 25, front_wh[1])

    sheet = ThreeViewSheet(
        part_no="GIS-EE-004-01",
        name="清洁模块壳体",
        material="PA66 (尼龙)",
        scale="1:1",
        weight_g=90,
        date="2026-03-16",
    )
    sheet.draw_front(cleaner_front_view, bbox=front_wh)
    sheet.draw_top(cleaner_top_view, bbox=top_wh)
    sheet.draw_left(cleaner_left_view, bbox=left_wh)
    sheet.draw_section(cleaner_section_aa, "A", bbox=section_wh,
                       position="right")
    return sheet.save(output_dir, material_type="nylon")


# ═══════════════════════════════════════════════════════════════════════════════
# EE-004-12 清洁窗口翻盖
# ═══════════════════════════════════════════════════════════════════════════════

def flap_front_view(msp, ox, oy, scale):
    """Front view: flat rectangle 22mm wide × 2mm thick (side elevation)."""
    s = scale
    w = S3_FLAP_W
    t = S3_FLAP_THICK
    hw = w / 2

    cx = ox + (hw + 10) * s
    cy = oy + (t * 5 + 5) * s  # scale up for visibility

    # Draw at 5:1 for visibility
    ds = s * 5.0
    msp.add_lwpolyline([
        (cx - hw * ds, cy), (cx + hw * ds, cy),
        (cx + hw * ds, cy + t * ds), (cx - hw * ds, cy + t * ds),
        (cx - hw * ds, cy),
    ], dxfattribs={"layer": "OUTLINE"})

    add_centerline_h(msp, cy + t * ds / 2,
                     cx - (hw + 5) * ds, cx + (hw + 5) * ds)

    add_linear_dim(msp, (cx - hw * ds, cy - 3 * s),
                   (cx + hw * ds, cy - 3 * s),
                   offset=-5 * s, text=f"{w}", angle=0)
    add_linear_dim(msp, (cx + hw * ds + 3 * s, cy),
                   (cx + hw * ds + 3 * s, cy + t * ds),
                   offset=5 * s, text=f"{t}", angle=90)



def flap_top_view(msp, ox, oy, scale):
    """Top view: arc profile cross-section."""
    s = scale
    w = S3_FLAP_W
    # Simplified: show a thin arc (the flap has a slight curve)
    ds = s * 5.0
    cx = ox + 15 * s
    cy = oy + 10 * s

    # Simplified rectangular cross-section at 5:1
    msp.add_lwpolyline([
        (cx, cy), (cx + S3_WINDOW_D * ds, cy),
        (cx + S3_WINDOW_D * ds, cy + S3_FLAP_THICK * ds),
        (cx, cy + S3_FLAP_THICK * ds),
        (cx, cy),
    ], dxfattribs={"layer": "OUTLINE"})

    add_linear_dim(msp, (cx, cy - 3 * s),
                   (cx + S3_WINDOW_D * ds, cy - 3 * s),
                   offset=-5 * s, text=f"{S3_WINDOW_D}", angle=0)


def draw_flap_sheet(output_dir: str) -> str:
    """Generate EE-004-12 flap two-view A3 sheet."""
    front_wh = (S3_FLAP_W * 5 + 30, S3_FLAP_THICK * 5 + 30)
    top_wh = (S3_WINDOW_D * 5 + 20, S3_FLAP_THICK * 5 + 20)

    sheet = ThreeViewSheet(
        part_no="GIS-EE-004-12",
        name="清洁窗口翻盖",
        material="硅橡胶 Shore A 40",
        scale="5:1",
        weight_g=5,
        date="2026-03-16",
    )
    sheet.draw_front(flap_front_view, bbox=front_wh)
    sheet.draw_top(flap_top_view, bbox=top_wh)
    return sheet.save(output_dir, material_type="rubber")


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    draw_cleaner_body_sheet(out)
    draw_flap_sheet(out)
    print("Done.")
