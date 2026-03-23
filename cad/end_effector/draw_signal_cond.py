"""
Signal Conditioning Module Engineering Drawings — EE-006-01 / EE-006-03

Two self-made parts:
  1. EE-006-01 信号调理壳体（含散热鳍片）— 三视图 140×100×55mm
  2. EE-006-03 信号调理安装支架（L形+抱箍）— 三视图

All geometry from params.py.
"""

import math
import os

from params import SIG_COND_W, SIG_COND_D, SIG_COND_H, LEMO_BORE_DIA

from drawing import (
    add_linear_dim, add_diameter_dim,
    add_section_hatch, add_section_hatch_with_holes,
    add_section_symbol,
    add_centerline_h, add_centerline_v,
)
from draw_three_view import ThreeViewSheet


# ═══════════════════════════════════════════════════════════════════════════════
# Shell parameters (derived from params.py + BOM notes)
# ═══════════════════════════════════════════════════════════════════════════════
SHELL_W = SIG_COND_W   # 140
SHELL_D = SIG_COND_D   # 100
SHELL_H = SIG_COND_H   # 55
SHELL_WALL = 3.0        # wall thickness
FIN_H = 8.0             # heat sink fin height
FIN_SPACING = 10.0      # fin pitch
FIN_COUNT = int(SHELL_W / FIN_SPACING) - 1  # ~13 fins

# Bracket parameters
BRKT_BASE_W = 140.0     # matches shell width
BRKT_BASE_D = 30.0      # base plate depth
BRKT_VERT_H = 40.0      # vertical plate height
BRKT_THICK = 3.0        # plate thickness
CLAMP_OD = 50.0         # pipe clamp OD (for J3-J4 link ~Φ40)
CLAMP_ID = 40.0         # clamp bore
CLAMP_SLIT = 2.0        # slit width


# ═══════════════════════════════════════════════════════════════════════════════
# EE-006-01 信号调理壳体
# ═══════════════════════════════════════════════════════════════════════════════

def sig_shell_front_view(msp, ox, oy, scale):
    """Front view: 140×55 rectangle with heat sink fins on top."""
    s = scale
    w = SHELL_W
    h = SHELL_H
    hw = w / 2
    wall = SHELL_WALL
    fin_h = FIN_H

    cx = ox + (hw + 10) * s
    cy_bot = oy + 5 * s
    cy_top = cy_bot + h * s

    # Shell outline
    msp.add_lwpolyline([
        (cx - hw * s, cy_bot), (cx + hw * s, cy_bot),
        (cx + hw * s, cy_top), (cx - hw * s, cy_top),
        (cx - hw * s, cy_bot),
    ], dxfattribs={"layer": "OUTLINE"})

    # Inner cavity
    ihw = hw - wall
    ih = h - 2 * wall
    msp.add_lwpolyline([
        (cx - ihw * s, cy_bot + wall * s),
        (cx + ihw * s, cy_bot + wall * s),
        (cx + ihw * s, cy_top - wall * s),
        (cx - ihw * s, cy_top - wall * s),
        (cx - ihw * s, cy_bot + wall * s),
    ], dxfattribs={"layer": "HIDDEN"})

    # Heat sink fins on top
    for i in range(FIN_COUNT):
        fx = cx - hw * s + (i + 1) * FIN_SPACING * s
        msp.add_line((fx, cy_top), (fx, cy_top + fin_h * s),
                     dxfattribs={"layer": "OUTLINE"})
    # Fin top caps (left and right boundary)
    msp.add_line((cx - hw * s, cy_top + fin_h * s),
                 (cx + hw * s, cy_top + fin_h * s),
                 dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx - hw * s, cy_top),
                 (cx - hw * s, cy_top + fin_h * s),
                 dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx + hw * s, cy_top),
                 (cx + hw * s, cy_top + fin_h * s),
                 dxfattribs={"layer": "OUTLINE"})

    # LEMO sockets (4× on left side)
    for i in range(4):
        ly = cy_bot + (10 + i * 10) * s
        msp.add_circle((cx - hw * s, ly), (LEMO_BORE_DIA / 2) * s,
                       dxfattribs={"layer": "OUTLINE"})

    # SMA connectors (2× on right side)
    for i in range(2):
        ry = cy_bot + (15 + i * 15) * s
        msp.add_circle((cx + hw * s, ry), 3.0 * s,
                       dxfattribs={"layer": "OUTLINE"})

    # M12 diagnostic (bottom center)
    msp.add_circle((cx, cy_bot), 6.0 * s, dxfattribs={"layer": "OUTLINE"})

    # Centerlines
    add_centerline_v(msp, cx, cy_bot - 5 * s, cy_top + fin_h * s + 5 * s)

    # Section cut line A-A (vertical, through center)
    add_section_symbol(msp,
                       start=(cx, cy_top + fin_h * s + 8 * s),
                       end=(cx, cy_bot - 8 * s),
                       label="A", arrow_dir="right")

    # Dimensions
    add_linear_dim(msp, (cx - hw * s, cy_bot - 5 * s),
                   (cx + hw * s, cy_bot - 5 * s),
                   offset=-8 * s, text=f"{w}", angle=0)
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy_bot),
                   (cx + hw * s + 5 * s, cy_top),
                   offset=8 * s, text=f"{h}", angle=90)
    add_linear_dim(msp, (cx + hw * s + 15 * s, cy_top),
                   (cx + hw * s + 15 * s, cy_top + fin_h * s),
                   offset=5 * s, text=f"{fin_h}", angle=90)



def sig_shell_section_aa(msp, ox, oy, scale):
    """Section A-A: longitudinal cut through shell center, showing
    inner cavity, wall thickness, fin roots, and connector bores."""
    s = scale
    d, h, wall = SHELL_D, SHELL_H, SHELL_WALL
    hd = d / 2
    fin_h = FIN_H

    cx = ox + (hd + 5) * s
    cy_bot = oy + 5 * s
    cy_top = cy_bot + h * s

    ol = cx - hd * s
    or_ = cx + hd * s
    ot = cy_top
    ob = cy_bot

    # Outer profile
    msp.add_lwpolyline([
        (ol, ob), (or_, ob), (or_, ot), (ol, ot), (ol, ob),
    ], dxfattribs={"layer": "OUTLINE"})

    # Inner cavity (visible in section)
    il = cx - (hd - wall) * s
    ir = cx + (hd - wall) * s
    it = cy_top - wall * s
    ib = cy_bot + wall * s
    msp.add_lwpolyline([
        (il, ib), (ir, ib), (ir, it), (il, it), (il, ib),
    ], dxfattribs={"layer": "OUTLINE"})

    # Fin roots at top (rectangles cut through)
    fin_w = 2.0
    for i in range(3):
        fx = cx - hd * s + (20 + i * 30) * s
        msp.add_lwpolyline([
            (fx, ot), (fx + fin_w * s, ot),
            (fx + fin_w * s, ot + fin_h * s),
            (fx, ot + fin_h * s), (fx, ot),
        ], dxfattribs={"layer": "OUTLINE"})
        add_section_hatch(msp, [
            (fx, ot), (fx + fin_w * s, ot),
            (fx + fin_w * s, ot + fin_h * s),
            (fx, ot + fin_h * s),
        ], pattern="ANSI31", scale=1.0)

    # LEMO bores through left wall (4×, visible in section as rectangles)
    for i in range(4):
        ly = ob + (10 + i * 10) * s
        lr = (LEMO_BORE_DIA / 2) * s
        msp.add_lwpolyline([
            (ol, ly - lr), (il, ly - lr),
            (il, ly + lr), (ol, ly + lr),
            (ol, ly - lr),
        ], dxfattribs={"layer": "OUTLINE"})

    # Hatch walls
    # Left wall (with LEMO holes as inner boundaries)
    lemo_holes = []
    for i in range(4):
        ly = ob + (10 + i * 10) * s
        lr = (LEMO_BORE_DIA / 2) * s
        lemo_holes.append([
            (ol, ly - lr), (il, ly - lr),
            (il, ly + lr), (ol, ly + lr),
        ])
    add_section_hatch_with_holes(msp,
        outer_boundary=[(ol, ob), (il, ob), (il, ot), (ol, ot)],
        inner_boundaries=lemo_holes,
        pattern="ANSI31", scale=1.5)
    # Right wall
    add_section_hatch_with_holes(msp,
        outer_boundary=[(ir, ob), (or_, ob), (or_, ot), (ir, ot)],
        pattern="ANSI31", scale=1.5)
    # Top wall
    add_section_hatch_with_holes(msp,
        outer_boundary=[(il, it), (ir, it), (ir, ot), (il, ot)],
        pattern="ANSI31", scale=1.5)
    # Bottom wall
    add_section_hatch_with_holes(msp,
        outer_boundary=[(il, ob), (ir, ob), (ir, ib), (il, ib)],
        pattern="ANSI31", scale=1.5)

    # Centerline
    add_centerline_v(msp, cx, ot + fin_h * s + 3 * s, ob - 3 * s)

    # Dimensions
    add_linear_dim(msp, (ol, ot + fin_h * s + 5 * s),
                   (or_, ot + fin_h * s + 5 * s),
                   offset=5 * s, text=f"{d}", angle=0)
    add_linear_dim(msp, (or_ + 5 * s, ob), (or_ + 5 * s, ot),
                   offset=5 * s, text=f"{h}", angle=90)
    add_linear_dim(msp, (ol - 3 * s, ot), (ol - 3 * s, it),
                   offset=-3 * s, text=f"{wall}", angle=90)


def sig_shell_top_view(msp, ox, oy, scale):
    """Top view: 140×100 rectangle with fin pattern."""
    s = scale
    w = SHELL_W
    d = SHELL_D
    hw = w / 2
    hd = d / 2

    cx = ox + (hw + 10) * s
    cy = oy + (hd + 5) * s

    msp.add_lwpolyline([
        (cx - hw * s, cy - hd * s), (cx + hw * s, cy - hd * s),
        (cx + hw * s, cy + hd * s), (cx - hw * s, cy + hd * s),
        (cx - hw * s, cy - hd * s),
    ], dxfattribs={"layer": "OUTLINE"})

    # Fin lines (parallel to depth, on top surface)
    for i in range(FIN_COUNT):
        fx = cx - hw * s + (i + 1) * FIN_SPACING * s
        msp.add_line((fx, cy - hd * s), (fx, cy + hd * s),
                     dxfattribs={"layer": "THIN"})

    add_centerline_v(msp, cx, cy - (hd + 5) * s, cy + (hd + 5) * s)
    add_centerline_h(msp, cy, cx - (hw + 5) * s, cx + (hw + 5) * s)

    add_linear_dim(msp, (cx - hw * s, cy - hd * s - 5 * s),
                   (cx + hw * s, cy - hd * s - 5 * s),
                   offset=-5 * s, text=f"{w}", angle=0)
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy - hd * s),
                   (cx + hw * s + 5 * s, cy + hd * s),
                   offset=5 * s, text=f"{d}", angle=90)


def sig_shell_left_view(msp, ox, oy, scale):
    """Left view: 100×55 side with fin cross-section."""
    s = scale
    d = SHELL_D
    h = SHELL_H
    hd = d / 2
    fin_h = FIN_H

    cx = ox + (hd + 5) * s
    cy_bot = oy + 5 * s
    cy_top = cy_bot + h * s

    msp.add_lwpolyline([
        (cx - hd * s, cy_bot), (cx + hd * s, cy_bot),
        (cx + hd * s, cy_top), (cx - hd * s, cy_top),
        (cx - hd * s, cy_bot),
    ], dxfattribs={"layer": "OUTLINE"})

    # Fins on top (cross-section: small rectangles)
    fin_w = 2.0  # fin wall thickness
    for i in range(3):  # show a few representative fins
        fx = cx - hd * s + (20 + i * 30) * s
        msp.add_lwpolyline([
            (fx, cy_top), (fx + fin_w * s, cy_top),
            (fx + fin_w * s, cy_top + fin_h * s),
            (fx, cy_top + fin_h * s),
            (fx, cy_top),
        ], dxfattribs={"layer": "OUTLINE"})
        add_section_hatch(msp, [
            (fx, cy_top), (fx + fin_w * s, cy_top),
            (fx + fin_w * s, cy_top + fin_h * s),
            (fx, cy_top + fin_h * s),
        ], pattern="ANSI31", scale=1.0)

    add_centerline_v(msp, cx, cy_bot - 3 * s, cy_top + fin_h * s + 5 * s)

    add_linear_dim(msp, (cx - hd * s, cy_bot - 5 * s),
                   (cx + hd * s, cy_bot - 5 * s),
                   offset=-5 * s, text=f"{d}", angle=0)
    add_linear_dim(msp, (cx + hd * s + 5 * s, cy_bot),
                   (cx + hd * s + 5 * s, cy_top),
                   offset=5 * s, text=f"{h}", angle=90)


def draw_sig_shell_sheet(output_dir: str) -> str:
    """Generate EE-006-01 signal conditioning shell three-view A3 sheet."""
    front_wh = (SHELL_W + 30, SHELL_H + FIN_H + 20)
    top_wh = (SHELL_W + 30, SHELL_D + 20)
    left_wh = (SHELL_D + 15, front_wh[1])
    section_wh = (SHELL_D + 25, front_wh[1])

    sheet = ThreeViewSheet(
        part_no="GIS-EE-006-01",
        name="信号调理壳体",
        material="6063 铝合金（含散热鳍片）",
        scale="1:1",
        weight_g=350,
        date="2026-03-16",
    )
    sheet.draw_front(sig_shell_front_view, bbox=front_wh)
    sheet.draw_top(sig_shell_top_view, bbox=top_wh)
    sheet.draw_left(sig_shell_left_view, bbox=left_wh)
    sheet.draw_section(sig_shell_section_aa, "A", bbox=section_wh,
                       position="right")
    return sheet.save(output_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# EE-006-03 信号调理安装支架（L形 + 抱箍）
# ═══════════════════════════════════════════════════════════════════════════════

def sig_bracket_front_view(msp, ox, oy, scale):
    """Front view: L-bracket + pipe clamp outline."""
    s = scale
    bw = BRKT_BASE_W
    vh = BRKT_VERT_H
    bt = BRKT_THICK
    hw = bw / 2

    cx = ox + (hw + 10) * s
    cy_top = oy + (vh + 10) * s

    # L-bracket: top plate + vertical
    # Vertical plate (full width × vert height)
    msp.add_lwpolyline([
        (cx - hw * s, cy_top), (cx + hw * s, cy_top),
        (cx + hw * s, cy_top - vh * s), (cx - hw * s, cy_top - vh * s),
        (cx - hw * s, cy_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Base plate extending forward (shown as dashed/hidden from this view)
    msp.add_lwpolyline([
        (cx - hw * s, cy_top - vh * s),
        (cx + hw * s, cy_top - vh * s),
        (cx + hw * s, cy_top - vh * s - bt * s),
        (cx - hw * s, cy_top - vh * s - bt * s),
        (cx - hw * s, cy_top - vh * s),
    ], dxfattribs={"layer": "OUTLINE"})

    # Clamp (semicircle at bottom center)
    clamp_r = CLAMP_OD / 2
    clamp_cy = cy_top - vh * s - bt * s - clamp_r * s
    msp.add_circle((cx, clamp_cy), clamp_r * s,
                   dxfattribs={"layer": "OUTLINE"})
    msp.add_circle((cx, clamp_cy), (CLAMP_ID / 2) * s,
                   dxfattribs={"layer": "HIDDEN"})

    # Slit
    slit_hw = CLAMP_SLIT / 2
    msp.add_line((cx - slit_hw * s, clamp_cy + clamp_r * s),
                 (cx - slit_hw * s, clamp_cy - clamp_r * s),
                 dxfattribs={"layer": "OUTLINE"})
    msp.add_line((cx + slit_hw * s, clamp_cy + clamp_r * s),
                 (cx + slit_hw * s, clamp_cy - clamp_r * s),
                 dxfattribs={"layer": "OUTLINE"})

    add_centerline_v(msp, cx, cy_top + 3 * s, clamp_cy - clamp_r * s - 5 * s)

    # Dimensions
    add_linear_dim(msp, (cx - hw * s, cy_top + 5 * s),
                   (cx + hw * s, cy_top + 5 * s),
                   offset=8 * s, text=f"{bw}", angle=0)
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy_top),
                   (cx + hw * s + 5 * s, cy_top - vh * s),
                   offset=8 * s, text=f"{vh}", angle=90)
    add_diameter_dim(msp, (cx, clamp_cy), clamp_r * s,
                     angle_deg=45, text=f"Φ{CLAMP_OD}")
    add_diameter_dim(msp, (cx, clamp_cy), (CLAMP_ID / 2) * s,
                     angle_deg=225, text=f"Φ{CLAMP_ID}")



def sig_bracket_top_view(msp, ox, oy, scale):
    """Top view: base plate 140×30."""
    s = scale
    bw = BRKT_BASE_W
    bd = BRKT_BASE_D
    hw = bw / 2
    hd = bd / 2

    cx = ox + (hw + 10) * s
    cy = oy + (hd + 5) * s

    msp.add_lwpolyline([
        (cx - hw * s, cy - hd * s), (cx + hw * s, cy - hd * s),
        (cx + hw * s, cy + hd * s), (cx - hw * s, cy + hd * s),
        (cx - hw * s, cy - hd * s),
    ], dxfattribs={"layer": "OUTLINE"})

    # Bolt holes for shell mounting (4×M4 at corners)
    for sx in [-1, 1]:
        for sy in [-1, 1]:
            bx = cx + sx * (hw - 10) * s
            by = cy + sy * (hd - 8) * s
            msp.add_circle((bx, by), 2.0 * s,
                           dxfattribs={"layer": "OUTLINE"})

    add_centerline_v(msp, cx, cy - (hd + 5) * s, cy + (hd + 5) * s)
    add_centerline_h(msp, cy, cx - (hw + 5) * s, cx + (hw + 5) * s)

    add_linear_dim(msp, (cx - hw * s, cy - hd * s - 5 * s),
                   (cx + hw * s, cy - hd * s - 5 * s),
                   offset=-5 * s, text=f"{bw}", angle=0)
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy - hd * s),
                   (cx + hw * s + 5 * s, cy + hd * s),
                   offset=5 * s, text=f"{bd}", angle=90)

    msp.add_text("4×M4", height=2.0,
                 dxfattribs={"layer": "DIM", "color": 3}
                 ).set_placement((cx + (hw - 10) * s + 5 * s,
                                 cy + (hd - 8) * s))


def sig_bracket_left_view(msp, ox, oy, scale):
    """Left view: L-profile + clamp cross-section."""
    s = scale
    bd = BRKT_BASE_D
    vh = BRKT_VERT_H
    bt = BRKT_THICK
    hd = bd / 2

    cx = ox + (hd + 5) * s
    cy_top = oy + (vh + 10) * s

    # L-profile
    msp.add_lwpolyline([
        (cx - hd * s, cy_top),
        (cx + hd * s, cy_top),
        (cx + hd * s, cy_top - vh * s - bt * s),
        (cx - hd * s, cy_top - vh * s - bt * s),
        (cx - hd * s, cy_top - vh * s),
        (cx - hd * s + bt * s, cy_top - vh * s),
        (cx - hd * s + bt * s, cy_top - bt * s),
        (cx - hd * s, cy_top - bt * s),
        (cx - hd * s, cy_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Hatch vertical plate
    add_section_hatch(msp, [
        (cx - hd * s, cy_top), (cx - hd * s + bt * s, cy_top),
        (cx - hd * s + bt * s, cy_top - bt * s), (cx - hd * s, cy_top - bt * s),
    ], pattern="ANSI31", scale=1.5)
    # Hatch base plate
    add_section_hatch(msp, [
        (cx - hd * s, cy_top - vh * s),
        (cx + hd * s, cy_top - vh * s),
        (cx + hd * s, cy_top - vh * s - bt * s),
        (cx - hd * s, cy_top - vh * s - bt * s),
    ], pattern="ANSI31", scale=1.5)

    add_linear_dim(msp, (cx - hd * s, cy_top + 5 * s),
                   (cx + hd * s, cy_top + 5 * s),
                   offset=5 * s, text=f"{bd}", angle=0)
    add_linear_dim(msp, (cx + hd * s + 5 * s, cy_top),
                   (cx + hd * s + 5 * s, cy_top - vh * s - bt * s),
                   offset=5 * s, text=f"{vh + bt}", angle=90)
    add_linear_dim(msp, (cx - hd * s - 5 * s, cy_top),
                   (cx - hd * s - 5 * s, cy_top - bt * s),
                   offset=-5 * s, text=f"{bt}", angle=90)


def draw_sig_bracket_sheet(output_dir: str) -> str:
    """Generate EE-006-03 signal conditioning bracket three-view A3 sheet."""
    total_h = BRKT_VERT_H + BRKT_THICK + CLAMP_OD + 10
    front_wh = (BRKT_BASE_W + 30, total_h + 20)
    top_wh = (BRKT_BASE_W + 30, BRKT_BASE_D + 20)
    left_wh = (BRKT_BASE_D + 15,
               BRKT_VERT_H + BRKT_THICK + 20)

    sheet = ThreeViewSheet(
        part_no="GIS-EE-006-03",
        name="信号调理安装支架",
        material="SUS304 不锈钢",
        scale="1:1",
        weight_g=200,
        date="2026-03-16",
    )
    sheet.draw_front(sig_bracket_front_view, bbox=front_wh)
    sheet.draw_top(sig_bracket_top_view, bbox=top_wh)
    sheet.draw_left(sig_bracket_left_view, bbox=left_wh)
    return sheet.save(output_dir, material_type="steel")


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    draw_sig_shell_sheet(out)
    draw_sig_bracket_sheet(out)
    print("Done.")
