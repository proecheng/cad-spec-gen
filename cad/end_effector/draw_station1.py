"""
Station 1 Applicator Body Engineering Drawing — EE-002-01  (V5)

视图配置 (§4.8.1):
  - 主视图：正面 60×55 + 隐藏线内部特征
  - 全剖 A-A：沿宽度中心纵切，显示壁厚/泵腔/内腔/NTC孔
  - 俯视图：顶面 60×40 + 储罐孔

标注规则：纯数字+标准符号，不附加零件名称/功能描述。
线型规则：不可见内部结构用 HIDDEN，剖面实体填充 ANSI31。
"""

import os

from params import (
    S1_BODY_W, S1_BODY_D, S1_BODY_H, S1_WALL_THICK,
    S1_TANK_OD, S1_PUMP_CAVITY_DIA, S1_PUMP_CAVITY_DEPTH,
    S1_SCRAPER_W, S1_SCRAPER_H, S1_SCRAPER_D,
    S1_NTC_BORE_DIA, S1_NTC_BORE_DEPTH,
    MOUNT_FACE, LEMO_BORE_DIA,
)
from drawing import (
    add_linear_dim, add_diameter_dim,
    add_section_hatch_with_holes, add_section_symbol,
    add_centerline_h, add_centerline_v,
    add_detail_circle,
)
from draw_three_view import ThreeViewSheet


# ─── Front view ───────────────────────────────────────────────────────────────

def applicator_front_view(msp, ox, oy, scale):
    """Front view: body 60×55 outline, hidden internal features, scraper."""
    s = scale
    w, h, wall = S1_BODY_W, S1_BODY_H, S1_WALL_THICK
    hw = w / 2

    cx = ox + (hw + 10) * s
    cy_top = oy + (h + 10) * s

    # Outer shell outline
    msp.add_lwpolyline([
        (cx - hw * s, cy_top), (cx + hw * s, cy_top),
        (cx + hw * s, cy_top - h * s), (cx - hw * s, cy_top - h * s),
        (cx - hw * s, cy_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Inner cavity — hidden (not visible from outside)
    ihw = hw - wall
    msp.add_lwpolyline([
        (cx - ihw * s, cy_top - wall * s),
        (cx + ihw * s, cy_top - wall * s),
        (cx + ihw * s, cy_top - (h - wall) * s),
        (cx - ihw * s, cy_top - (h - wall) * s),
        (cx - ihw * s, cy_top - wall * s),
    ], dxfattribs={"layer": "HIDDEN"})

    # Tank bore (hidden circle at top center)
    tank_r = S1_TANK_OD / 2
    msp.add_circle((cx, cy_top), tank_r * s, dxfattribs={"layer": "HIDDEN"})

    # Pump cavity (hidden circle)
    pump_r = S1_PUMP_CAVITY_DIA / 2
    pump_cy = cy_top - (h - wall - S1_PUMP_CAVITY_DEPTH / 2) * s
    msp.add_circle((cx, pump_cy), pump_r * s, dxfattribs={"layer": "HIDDEN"})

    # LEMO bore (visible through-hole on side wall)
    lemo_cx = cx + (hw - 8) * s
    lemo_cy = cy_top - h / 2 * s
    msp.add_circle((lemo_cx, lemo_cy),
                   (LEMO_BORE_DIA / 2) * s, dxfattribs={"layer": "OUTLINE"})

    # Scraper below body
    scr_hw = S1_SCRAPER_W / 2
    scr_top = cy_top - h * s
    scr_bot = scr_top - S1_SCRAPER_H * s
    msp.add_lwpolyline([
        (cx - scr_hw * s, scr_top), (cx + scr_hw * s, scr_top),
        (cx + scr_hw * s, scr_bot), (cx - scr_hw * s, scr_bot),
        (cx - scr_hw * s, scr_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Centerlines
    add_centerline_v(msp, cx, cy_top + 5 * s, scr_bot - 5 * s)
    add_centerline_h(msp, cy_top - h / 2 * s,
                     cx - (hw + 10) * s, cx + (hw + 10) * s)

    # Section cut line A-A (vertical, through center)
    add_section_symbol(msp,
                       start=(cx, cy_top + 8 * s),
                       end=(cx, scr_bot - 8 * s),
                       label="A", arrow_dir="right")

    # ── Dimensions (numbers only, no descriptive text) ──
    # Width 60
    add_linear_dim(msp, (cx - hw * s, cy_top + 5 * s),
                   (cx + hw * s, cy_top + 5 * s),
                   offset=8 * s, text=f"{w:.0f}", angle=0)
    # Height 55
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy_top),
                   (cx + hw * s + 5 * s, cy_top - h * s),
                   offset=8 * s, text=f"{h:.0f}", angle=90)
    # Scraper height 10
    add_linear_dim(msp, (cx - hw * s - 5 * s, scr_top),
                   (cx - hw * s - 5 * s, scr_bot),
                   offset=-5 * s, text=f"{S1_SCRAPER_H:.0f}", angle=90)
    # Pump cavity Φ
    add_diameter_dim(msp, (cx, pump_cy), pump_r * s, angle_deg=45,
                     text=f"Φ{S1_PUMP_CAVITY_DIA:.0f}")
    # LEMO bore Φ
    add_diameter_dim(msp, (lemo_cx, lemo_cy), (LEMO_BORE_DIA / 2) * s,
                     angle_deg=30, text=f"Φ{LEMO_BORE_DIA}")
    # Tank bore Φ
    add_diameter_dim(msp, (cx, cy_top), tank_r * s, angle_deg=60,
                     text=f"Φ{S1_TANK_OD:.0f}")


# ─── Section A-A (full section through center of width) ───────────────────────

def applicator_section_aa(msp, ox, oy, scale):
    """Section A-A: longitudinal cut through center of width, looking right.

    Shows 40(depth) × 55(height) cross-section with wall thickness,
    pump cavity depth, NTC bore, and hatched solid material.
    """
    s = scale
    d, h, wall = S1_BODY_D, S1_BODY_H, S1_WALL_THICK
    hd = d / 2

    cx = ox + (hd + 5) * s
    cy_top = oy + (h + 10) * s

    # ── Outline of cut face ──
    # Outer profile
    ol = cx - hd * s
    or_ = cx + hd * s
    ot = cy_top
    ob = cy_top - h * s

    msp.add_lwpolyline([
        (ol, ob), (or_, ob), (or_, ot), (ol, ot), (ol, ob),
    ], dxfattribs={"layer": "OUTLINE"})

    # Inner cavity (visible because cut is through it)
    il = cx - (hd - wall) * s
    ir = cx + (hd - wall) * s
    it = cy_top - wall * s
    ib = cy_top - (h - wall) * s

    msp.add_lwpolyline([
        (il, ib), (ir, ib), (ir, it), (il, it), (il, ib),
    ], dxfattribs={"layer": "OUTLINE"})

    # Pump cavity in section (rectangular pocket in bottom wall)
    # The pump cavity extends upward from the inner floor
    pc_r = (S1_PUMP_CAVITY_DIA / 2) * s
    pc_top = ib + S1_PUMP_CAVITY_DEPTH * s
    # In this section, pump cavity appears as a rectangle
    # (because the circular bore is cut through its center)
    msp.add_lwpolyline([
        (cx - pc_r, ib), (cx + pc_r, ib),
        (cx + pc_r, pc_top), (cx - pc_r, pc_top),
        (cx - pc_r, ib),
    ], dxfattribs={"layer": "OUTLINE"})

    # Tank bore at top (circle cut through center = rectangle in section)
    tank_r = (S1_TANK_OD / 2) * s
    msp.add_lwpolyline([
        (cx - tank_r, it), (cx + tank_r, it),
        (cx + tank_r, ot), (cx - tank_r, ot),
        (cx - tank_r, it),
    ], dxfattribs={"layer": "OUTLINE"})

    # NTC bore (hidden, behind the cut plane — side wall blind hole)
    ntc_cy = ib + S1_SCRAPER_H / 2 * s
    ntc_r = (S1_NTC_BORE_DIA / 2) * s
    msp.add_circle((or_ - wall * s / 2, ntc_cy + 5 * s),
                   ntc_r, dxfattribs={"layer": "HIDDEN"})

    # Scraper below
    scr_hd = S1_SCRAPER_D / 2
    scr_top = ob
    scr_bot = scr_top - S1_SCRAPER_H * s
    msp.add_lwpolyline([
        (cx - scr_hd * s, scr_top), (cx + scr_hd * s, scr_top),
        (cx + scr_hd * s, scr_bot), (cx - scr_hd * s, scr_bot),
        (cx - scr_hd * s, scr_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # ── Hatch solid material ──
    # Left wall section
    add_section_hatch_with_holes(msp,
        outer_boundary=[(ol, ob), (il, ob), (il, ot), (ol, ot)],
        inner_boundaries=[
            # Tank bore cuts into left wall at top
            [(ol, it), (cx - tank_r, it), (cx - tank_r, ot), (ol, ot)],
        ] if (cx - tank_r) > ol else [],
        pattern="ANSI31", scale=1.5)

    # Right wall section
    add_section_hatch_with_holes(msp,
        outer_boundary=[(ir, ob), (or_, ob), (or_, ot), (ir, ot)],
        inner_boundaries=[
            [(cx + tank_r, it), (or_, it), (or_, ot), (cx + tank_r, ot)],
        ] if (cx + tank_r) < or_ else [],
        pattern="ANSI31", scale=1.5)

    # Top wall section (between tank bore edges)
    # Only hatch left-of-tank and right-of-tank portions
    if (cx - tank_r) > il:
        add_section_hatch_with_holes(msp,
            outer_boundary=[(il, it), (cx - tank_r, it),
                            (cx - tank_r, ot), (il, ot)])
    if (cx + tank_r) < ir:
        add_section_hatch_with_holes(msp,
            outer_boundary=[(cx + tank_r, it), (ir, it),
                            (ir, ot), (cx + tank_r, ot)])

    # Bottom wall section (between pump cavity edges)
    if (cx - pc_r) > il:
        add_section_hatch_with_holes(msp,
            outer_boundary=[(il, ob), (cx - pc_r, ob),
                            (cx - pc_r, ib), (il, ib)])
    if (cx + pc_r) < ir:
        add_section_hatch_with_holes(msp,
            outer_boundary=[(cx + pc_r, ob), (ir, ob),
                            (ir, ib), (cx + pc_r, ib)])

    # Centerlines
    add_centerline_v(msp, cx, ot + 5 * s, scr_bot - 5 * s)

    # ── Dimensions ──
    # Depth 40
    add_linear_dim(msp, (ol, ot + 5 * s), (or_, ot + 5 * s),
                   offset=5 * s, text=f"{d:.0f}", angle=0)
    # Height 55
    add_linear_dim(msp, (or_ + 5 * s, ot), (or_ + 5 * s, ob),
                   offset=5 * s, text=f"{h:.0f}", angle=90)
    # Wall thickness 3 (top)
    add_linear_dim(msp, (ol - 3 * s, ot), (ol - 3 * s, it),
                   offset=-5 * s, text=f"{wall:.0f}", angle=90)
    # Wall thickness 3 (bottom)
    add_linear_dim(msp, (ol - 3 * s, ib), (ol - 3 * s, ob),
                   offset=-5 * s, text=f"{wall:.0f}", angle=90)
    # Wall thickness 3 (side)
    add_linear_dim(msp, (ol, ob - 3 * s), (il, ob - 3 * s),
                   offset=-3 * s, text=f"{wall:.0f}", angle=0)
    # Pump cavity depth 25
    add_linear_dim(msp, (cx + pc_r + 3 * s, ib),
                   (cx + pc_r + 3 * s, pc_top),
                   offset=5 * s, text=f"{S1_PUMP_CAVITY_DEPTH:.0f}", angle=90)
    # Pump cavity width Φ20 (in section = 20mm linear)
    add_linear_dim(msp, (cx - pc_r, ib - 3 * s),
                   (cx + pc_r, ib - 3 * s),
                   offset=-3 * s, text=f"Φ{S1_PUMP_CAVITY_DIA:.0f}", angle=0)
    # NTC bore callout
    msp.add_text(f"Φ{S1_NTC_BORE_DIA}×{S1_NTC_BORE_DEPTH:.0f}", height=2.5,
                 dxfattribs={"layer": "DIM", "color": 3}
                 ).set_placement((or_ + 3 * s, ntc_cy + 5 * s))


# ─── Detail I: NTC bore enlargement (2:1) ────────────────────────────────────

def applicator_detail_ntc(msp, ox, oy, scale):
    """Detail I: enlarged view of NTC bore Φ3.5×15 in side wall (2:1)."""
    s = scale
    wall = S1_WALL_THICK
    bore_d = S1_NTC_BORE_DIA
    bore_depth = S1_NTC_BORE_DEPTH
    bore_r = bore_d / 2

    # Side wall section with NTC blind hole
    # Wall shown as rectangle (wall thick × ~20mm height context)
    ctx_h = 20.0  # context height
    cx = ox + (wall + 5) * s
    cy_mid = oy + (ctx_h / 2 + 5) * s

    # Wall section rectangle
    wl = cx - wall / 2 * s
    wr = cx + wall / 2 * s
    wt = cy_mid + ctx_h / 2 * s
    wb = cy_mid - ctx_h / 2 * s
    msp.add_lwpolyline([
        (wl, wb), (wr, wb), (wr, wt), (wl, wt), (wl, wb),
    ], dxfattribs={"layer": "OUTLINE"})

    # NTC bore (blind hole from right side, depth into wall)
    bore_cy = cy_mid
    bore_left = wr - bore_depth * s
    msp.add_lwpolyline([
        (wr, bore_cy - bore_r * s),
        (bore_left, bore_cy - bore_r * s),
        (bore_left, bore_cy + bore_r * s),
        (wr, bore_cy + bore_r * s),
    ], dxfattribs={"layer": "OUTLINE"})

    # Hatch wall material (with bore hole subtracted)
    from drawing import add_section_hatch_with_holes
    add_section_hatch_with_holes(msp,
        outer_boundary=[(wl, wb), (wr, wb), (wr, wt), (wl, wt)],
        inner_boundaries=[
            [(bore_left, bore_cy - bore_r * s),
             (wr, bore_cy - bore_r * s),
             (wr, bore_cy + bore_r * s),
             (bore_left, bore_cy + bore_r * s)],
        ],
        pattern="ANSI31", scale=0.8)

    # Centerline through bore
    add_centerline_h(msp, bore_cy, wl - 3 * s, wr + 5 * s)

    # Dimensions
    add_diameter_dim(msp, ((bore_left + wr) / 2, bore_cy), bore_r * s,
                     angle_deg=90, text=f"Φ{bore_d}")
    add_linear_dim(msp, (bore_left, bore_cy + bore_r * s + 3 * s),
                   (wr, bore_cy + bore_r * s + 3 * s),
                   offset=3 * s, text=f"{bore_depth:.0f}", angle=0)


# ─── Top view ─────────────────────────────────────────────────────────────────

def applicator_top_view(msp, ox, oy, scale):
    """Top view: 60×40 rectangle with tank bore circle."""
    s = scale
    w, d, wall = S1_BODY_W, S1_BODY_D, S1_WALL_THICK
    hw, hd = w / 2, d / 2

    cx = ox + (hw + 10) * s
    cy = oy + (hd + 5) * s

    # Outer
    msp.add_lwpolyline([
        (cx - hw * s, cy - hd * s), (cx + hw * s, cy - hd * s),
        (cx + hw * s, cy + hd * s), (cx - hw * s, cy + hd * s),
        (cx - hw * s, cy - hd * s),
    ], dxfattribs={"layer": "OUTLINE"})

    # Inner cavity (hidden — covered by top wall)
    ihw, ihd = hw - wall, hd - wall
    msp.add_lwpolyline([
        (cx - ihw * s, cy - ihd * s), (cx + ihw * s, cy - ihd * s),
        (cx + ihw * s, cy + ihd * s), (cx - ihw * s, cy + ihd * s),
        (cx - ihw * s, cy - ihd * s),
    ], dxfattribs={"layer": "HIDDEN"})

    # Tank bore (visible through-hole at top)
    tank_r = S1_TANK_OD / 2
    msp.add_circle((cx, cy), tank_r * s, dxfattribs={"layer": "OUTLINE"})

    # Centerlines
    add_centerline_v(msp, cx, cy - (hd + 5) * s, cy + (hd + 5) * s)
    add_centerline_h(msp, cy, cx - (hw + 5) * s, cx + (hw + 5) * s)

    # ── Dimensions (numbers only) ──
    # Width 60
    add_linear_dim(msp, (cx - hw * s, cy - hd * s - 5 * s),
                   (cx + hw * s, cy - hd * s - 5 * s),
                   offset=-5 * s, text=f"{w:.0f}", angle=0)
    # Depth 40
    add_linear_dim(msp, (cx + hw * s + 5 * s, cy - hd * s),
                   (cx + hw * s + 5 * s, cy + hd * s),
                   offset=5 * s, text=f"{d:.0f}", angle=90)
    # Tank bore Φ
    add_diameter_dim(msp, (cx, cy), tank_r * s, angle_deg=45,
                     text=f"Φ{S1_TANK_OD:.0f}")


# ─── Sheet assembly ───────────────────────────────────────────────────────────

def draw_applicator_sheet(output_dir: str) -> str:
    """Generate EE-002-01 applicator body A3 sheet.

    Views: front + section A-A (right) + top (below).
    """
    front_wh = (S1_BODY_W + 30, S1_BODY_H + S1_SCRAPER_H + 25)
    top_wh = (S1_BODY_W + 30, S1_BODY_D + 20)
    section_wh = (S1_BODY_D + 25, front_wh[1])
    detail_wh = (S1_WALL_THICK * 2 + 15, 30)

    sheet = ThreeViewSheet(
        part_no="GIS-EE-002-01",
        name="涂抹模块壳体",
        material="PA66 (尼龙)",
        scale="1:1",
        weight_g=80,
        date="2026-03-20",
    )
    sheet.draw_front(applicator_front_view, bbox=front_wh)
    sheet.draw_top(applicator_top_view, bbox=top_wh)
    sheet.draw_section(applicator_section_aa, "A", bbox=section_wh,
                       position="right")
    sheet.draw_detail(applicator_detail_ntc, "I", bbox=detail_wh,
                      scale_factor=2.0, position="bottom_right")
    return sheet.save(output_dir, material_type="nylon")


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    draw_applicator_sheet(out)
    print("Done.")
