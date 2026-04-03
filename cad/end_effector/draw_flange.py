"""
Flange Engineering Drawing — EE-001-01 法兰本体

GB/T 4458.1 三视图 A3 图纸：
  - 主视图：端面（圆盘 + 4悬臂 + 孔位模式）
  - 俯视图：侧面剖视（Al + PEEK + O-ring 台阶细节）
  - 左视图：侧面（悬臂截面）

All geometry from params.py; tolerances from tolerances.py.
"""

import math
import os

from params import (
    FLANGE_OD, FLANGE_R, FLANGE_CENTER_HOLE, FLANGE_AL_THICK,
    FLANGE_TOTAL_THICK, FLANGE_PEEK_THICK,
    ARM_WIDTH, ARM_THICK, ARM_LENGTH, MOUNT_CENTER_R, MOUNT_FACE,
    MOUNT_BOLT_PCD, MOUNT_BOLT_DIA, MOUNT_PIN_DIA,
    MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y,
    ISO9409_PCD, ISO9409_BOLT_DIA,
    SPRING_PIN_R, SPRING_PIN_DIA,
    PEEK_OD, PEEK_ID, PEEK_THICK, PEEK_STEP_HEIGHT,
    PEEK_BOLT_NUM, PEEK_BOLT_DIA, PEEK_BOLT_PCD,
    ORING_CENTER_DIA, ORING_GROOVE_WIDTH, ORING_GROOVE_DEPTH, ORING_CS,
    NUM_STATIONS, STATION_ANGLES,
)
from tolerances import (
    FLANGE_OD_TOL, CENTER_HOLE_TOL, AL_THICK_TOL, TOTAL_THICK_TOL,
    ARM_WIDTH_TOL, ARM_LENGTH_TOL, MOUNT_FACE_TOL,
    SPRING_PIN_HOLE_TOL, PEEK_OD_TOL, PEEK_BOLT_PCD_TOL,
    ORING_GROOVE_W_TOL, ORING_GROOVE_D_TOL, ORING_CENTER_TOL,
    GDT_COAXIALITY, GDT_PARALLELISM, GDT_EQUAL_HEIGHT, GDT_ANGULAR,
    SURF_CRITICAL, SURF_ISO, SURF_GENERAL,
)
from drawing import (
    add_linear_dim, add_diameter_dim, add_radius_dim,
    add_gdt_frame, add_surface_symbol,
    add_section_hatch, add_section_hatch_with_holes,
    add_centerline_cross,
    add_centerline_h, add_centerline_v,
    add_datum_symbol, add_section_symbol,
    add_detail_circle,
)
from draw_three_view import ThreeViewSheet


# ═══════════════════════════════════════════════════════════════════════════════
# 主视图：端面（圆盘 + 4悬臂 + 孔位）
# ═══════════════════════════════════════════════════════════════════════════════

def flange_front_view(msp, ox, oy, scale):
    """Front view: disc end face with arms and hole patterns."""
    s = scale
    # Center of disc in drawing coordinates
    cx = ox + FLANGE_R * s + 10 * s
    cy = oy + FLANGE_R * s + 10 * s

    # Main disc
    msp.add_circle((cx, cy), FLANGE_R * s, dxfattribs={"layer": "OUTLINE"})
    # Center hole
    msp.add_circle((cx, cy), (FLANGE_CENTER_HOLE / 2) * s,
                   dxfattribs={"layer": "OUTLINE"})
    # PEEK outer ring (hidden)
    msp.add_circle((cx, cy), (PEEK_OD / 2) * s, dxfattribs={"layer": "HIDDEN"})
    # Center marks
    add_centerline_cross(msp, (cx, cy), size=(FLANGE_R + 15) * s)

    # 4 arms + mount faces
    for angle in STATION_ANGLES:
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        arm_mid_r = FLANGE_R + ARM_LENGTH / 2
        amx = cx + arm_mid_r * cos_a * s
        amy = cy + arm_mid_r * sin_a * s

        hw, hl = ARM_WIDTH / 2, ARM_LENGTH / 2
        corners_local = [(-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl)]
        corners = []
        for lx, ly in corners_local:
            gx = amx + (lx * (-sin_a) + ly * cos_a) * s
            gy = amy + (lx * cos_a + ly * sin_a) * s
            corners.append((gx, gy))
        corners.append(corners[0])
        msp.add_lwpolyline(corners, dxfattribs={"layer": "OUTLINE"})

        # Mount face (40×40 thin)
        mcx = cx + MOUNT_CENTER_R * cos_a * s
        mcy = cy + MOUNT_CENTER_R * sin_a * s
        mf = MOUNT_FACE / 2
        mf_corners = []
        for lx, ly in [(-mf, -mf), (mf, -mf), (mf, mf), (-mf, mf)]:
            gx = mcx + (lx * (-sin_a) + ly * cos_a) * s
            gy = mcy + (lx * cos_a + ly * sin_a) * s
            mf_corners.append((gx, gy))
        mf_corners.append(mf_corners[0])
        msp.add_lwpolyline(mf_corners, dxfattribs={"layer": "THIN"})

        # 4×M3 bolt holes at PCD28 square
        half_s = MOUNT_BOLT_PCD / 2
        for dx, dy in [(half_s/2, half_s/2), (half_s/2, -half_s/2),
                       (-half_s/2, half_s/2), (-half_s/2, -half_s/2)]:
            bx = mcx + (dx * (-sin_a) + dy * cos_a) * s
            by = mcy + (dx * cos_a + dy * sin_a) * s
            msp.add_circle((bx, by), (MOUNT_BOLT_DIA / 2) * s,
                           dxfattribs={"layer": "OUTLINE"})

        # Pin hole
        pin_dx, pin_dy = MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y
        px = mcx + (pin_dx * (-sin_a) + pin_dy * cos_a) * s
        py = mcy + (pin_dx * cos_a + pin_dy * sin_a) * s
        msp.add_circle((px, py), (MOUNT_PIN_DIA / 2) * s,
                       dxfattribs={"layer": "OUTLINE"})

    # ISO 9409 bolt holes
    iso_pcd_r = ISO9409_PCD / 2
    msp.add_circle((cx, cy), iso_pcd_r * s, dxfattribs={"layer": "CENTER"})
    iso_half = iso_pcd_r / math.sqrt(2)
    for dx, dy in [(iso_half, iso_half), (iso_half, -iso_half),
                   (-iso_half, iso_half), (-iso_half, -iso_half)]:
        msp.add_circle((cx + dx * s, cy + dy * s),
                       (ISO9409_BOLT_DIA / 2) * s,
                       dxfattribs={"layer": "OUTLINE"})

    # Spring pin holes
    for angle in STATION_ANGLES:
        a = math.radians(angle + 45)
        sx = cx + SPRING_PIN_R * math.cos(a) * s
        sy = cy + SPRING_PIN_R * math.sin(a) * s
        msp.add_circle((sx, sy), (SPRING_PIN_DIA / 2) * s,
                       dxfattribs={"layer": "OUTLINE"})

    # PEEK bolt holes
    msp.add_circle((cx, cy), (PEEK_BOLT_PCD / 2) * s,
                   dxfattribs={"layer": "CENTER"})
    for i in range(PEEK_BOLT_NUM):
        a = math.radians(i * 60 + 30)
        bx = cx + (PEEK_BOLT_PCD / 2) * math.cos(a) * s
        by = cy + (PEEK_BOLT_PCD / 2) * math.sin(a) * s
        msp.add_circle((bx, by), (PEEK_BOLT_DIA / 2) * s,
                       dxfattribs={"layer": "OUTLINE"})

    # ── Dimensions ──
    add_diameter_dim(msp, (cx, cy), FLANGE_R * s, angle_deg=30,
                     text=FLANGE_OD_TOL.dia_text)
    add_diameter_dim(msp, (cx, cy), (FLANGE_CENTER_HOLE / 2) * s,
                     angle_deg=210, text=CENTER_HOLE_TOL.dia_text)
    add_diameter_dim(msp, (cx, cy), (PEEK_OD / 2) * s, angle_deg=150,
                     text=PEEK_OD_TOL.dia_text)
    add_diameter_dim(msp, (cx, cy), (ISO9409_PCD / 2) * s, angle_deg=315,
                     text=f"PCD {ISO9409_PCD:.0f} (ISO 9409)")
    add_diameter_dim(msp, (cx, cy), (PEEK_BOLT_PCD / 2) * s, angle_deg=120,
                     text=PEEK_BOLT_PCD_TOL.text + " PCD")
    add_diameter_dim(msp, (cx, cy), SPRING_PIN_R * s, angle_deg=70,
                     text=f"R{SPRING_PIN_R:.0f} (4×{SPRING_PIN_HOLE_TOL.dia_text})")

    # Arm dimensions (on 0° arm)
    arm_tip_r = FLANGE_R + ARM_LENGTH
    add_linear_dim(msp,
                   (cx + arm_tip_r * s, cy - (ARM_WIDTH / 2) * s),
                   (cx + arm_tip_r * s, cy + (ARM_WIDTH / 2) * s),
                   offset=10 * s, text=ARM_WIDTH_TOL.text, angle=90)
    add_linear_dim(msp,
                   (cx + FLANGE_R * s, cy),
                   (cx + (FLANGE_R + ARM_LENGTH) * s, cy),
                   offset=(ARM_WIDTH / 2 + 8) * s, text=ARM_LENGTH_TOL.text,
                   angle=0)

    # Mount face dim
    mcx_0 = cx + MOUNT_CENTER_R * s
    add_linear_dim(msp,
                   (mcx_0 - (MOUNT_FACE / 2) * s, cy + (MOUNT_FACE / 2 + 3) * s),
                   (mcx_0 + (MOUNT_FACE / 2) * s, cy + (MOUNT_FACE / 2 + 3) * s),
                   offset=5 * s, text=MOUNT_FACE_TOL.text, angle=0)

    # GD&T
    add_gdt_frame(msp, (cx - FLANGE_R * s - 10 * s,
                        cy - FLANGE_R * s - 15 * s), [
        ("⌭", "Φ0.02", "A"),
        ("∠", "0.05°", "A"),
    ])

    # ── 基准标注 (GB/T 1182) ──
    # A = 主轴线（附着在中心孔边缘）
    add_datum_symbol(msp, (cx + (FLANGE_CENTER_HOLE / 2) * s, cy), "A",
                     direction="right")

    # ── 剖切线 A-A（标注俯视图剖面位置）──
    # 水平穿过圆盘中心，箭头朝下（指向俯视图投影方向）
    add_section_symbol(msp,
                       start=(cx - (FLANGE_R + 20) * s, cy),
                       end=(cx + (FLANGE_R + 20) * s, cy),
                       label="A", arrow_dir="down")


# ═══════════════════════════════════════════════════════════════════════════════
# 俯视图：侧面剖视（显示厚度 + Al/PEEK 台阶 + O-ring 槽）
# ═══════════════════════════════════════════════════════════════════════════════

def flange_top_view(msp, ox, oy, scale):
    """Top view (剖面): side profile showing Al+PEEK layers."""
    s = scale
    al_t = FLANGE_AL_THICK
    total_t = FLANGE_TOTAL_THICK
    step_h = PEEK_STEP_HEIGHT
    r_outer = FLANGE_R
    r_center = FLANGE_CENTER_HOLE / 2
    r_peek_o = PEEK_OD / 2
    r_peek_i = PEEK_ID / 2

    # In top view: X = radial (width of front view), Y = axial (thickness)
    # We need the radial extent to match the front view width
    # Origin ox,oy is bottom-left; section is drawn with X=radial, Y=axial upward

    # Centerline (horizontal, at axial center)
    add_centerline_h(msp, oy + (total_t / 2) * s,
                     ox - 10 * s, ox + (2 * r_outer + 20) * s)

    # Map: radial position -> X coord; axial position -> Y coord
    def rx(r):
        return ox + (r_outer + r) * s + 10 * s  # r_outer+r so center is at mid

    def ay(a):
        return oy + a * s

    # Draw both halves (above and below center)
    for sign in [1, -1]:
        # Al body
        al_pts = [
            (rx(sign * r_center), ay(0)),
            (rx(sign * r_center), ay(al_t)),
            (rx(sign * r_peek_i), ay(al_t)),
            (rx(sign * r_peek_i), ay(al_t - step_h)),
            (rx(sign * r_peek_o), ay(al_t - step_h)),
            (rx(sign * r_peek_o), ay(al_t)),
            (rx(sign * r_outer), ay(al_t)),
            (rx(sign * r_outer), ay(0)),
            (rx(sign * r_center), ay(0)),
        ]
        msp.add_lwpolyline(al_pts, dxfattribs={"layer": "OUTLINE"})
        add_section_hatch(msp, al_pts[:-1], pattern="ANSI31", scale=2.0)

        # PEEK
        peek_pts = [
            (rx(sign * r_peek_i), ay(al_t - step_h)),
            (rx(sign * r_peek_i), ay(total_t)),
            (rx(sign * r_peek_o), ay(total_t)),
            (rx(sign * r_peek_o), ay(al_t - step_h)),
            (rx(sign * r_peek_i), ay(al_t - step_h)),
        ]
        msp.add_lwpolyline(peek_pts, dxfattribs={"layer": "OUTLINE"})
        add_section_hatch(msp, peek_pts[:-1], pattern="ANSI32", scale=2.0)

        # O-ring groove
        oring_r_c = ORING_CENTER_DIA / 2
        oring_ri = oring_r_c - ORING_GROOVE_WIDTH / 2
        oring_ro = oring_r_c + ORING_GROOVE_WIDTH / 2
        groove_pts = [
            (rx(sign * oring_ri), ay(al_t - ORING_GROOVE_DEPTH)),
            (rx(sign * oring_ri), ay(al_t)),
            (rx(sign * oring_ro), ay(al_t)),
            (rx(sign * oring_ro), ay(al_t - ORING_GROOVE_DEPTH)),
            (rx(sign * oring_ri), ay(al_t - ORING_GROOVE_DEPTH)),
        ]
        msp.add_lwpolyline(groove_pts, dxfattribs={"layer": "OUTLINE"})

    # Dimensions
    add_linear_dim(msp, (rx(r_outer) + 5 * s, ay(0)),
                   (rx(r_outer) + 5 * s, ay(al_t)),
                   offset=8 * s, text=AL_THICK_TOL.text, angle=90)
    add_linear_dim(msp, (rx(r_outer) + 15 * s, ay(0)),
                   (rx(r_outer) + 15 * s, ay(total_t)),
                   offset=8 * s, text=TOTAL_THICK_TOL.text, angle=90)


    # Surface symbols
    add_surface_symbol(msp, (rx(r_center) - 10 * s, ay(al_t) + 2 * s),
                       SURF_CRITICAL.ra)

    # GD&T
    add_gdt_frame(msp, (rx(r_outer) + 20 * s, ay(0)), [
        ("⌭", "Φ0.02", "A"),
        ("∥", "0.02", "A"),
        ("=", "0.05", "B"),
    ])

    # ── 基准标注 (GB/T 1182) ──
    # B = 安装面（附着在底面）
    add_datum_symbol(msp, (rx(0), ay(0)), "B", direction="down")

    # ── Detail circle I: O-ring groove area ──
    # Mark the groove region on the top view for enlargement
    oring_r_c = ORING_CENTER_DIA / 2
    detail_cx = rx(oring_r_c)
    detail_cy = ay(FLANGE_AL_THICK - ORING_GROOVE_DEPTH / 2)
    add_detail_circle(msp, (detail_cx, detail_cy),
                      radius=8 * s, label="I")


# ═══════════════════════════════════════════════════════════════════════════════
# 左视图：侧面（显示悬臂截面）
# ═══════════════════════════════════════════════════════════════════════════════

def flange_left_view(msp, ox, oy, scale):
    """Left view: side profile showing arm cross-section."""
    s = scale
    # centre → bottom-left origin
    ox = ox - (FLANGE_TOTAL_THICK + 15) / 2 * s
    al_t = FLANGE_AL_THICK
    total_t = FLANGE_TOTAL_THICK
    r_outer = FLANGE_R
    r_center = FLANGE_CENTER_HOLE / 2

    # In left view: X = axial (thickness), Y = radial (height)
    # Same axial convention as top view; Y now shows the vertical extent

    def ax(a):
        return ox + a * s

    def ry(r):
        return oy + (r_outer + r) * s + 10 * s

    # Centerline
    add_centerline_h(msp, ry(0), ax(-5), ax(total_t + 10))

    # Disc outline (rectangle in side view)
    for sign in [1, -1]:
        msp.add_lwpolyline([
            (ax(0), ry(sign * r_center)),
            (ax(total_t), ry(sign * r_center)),
            (ax(total_t), ry(sign * r_outer)),
            (ax(0), ry(sign * r_outer)),
            (ax(0), ry(sign * r_center)),
        ], dxfattribs={"layer": "OUTLINE"})

    # Arm extension (at 90° and 270° visible as rectangles above/below disc)
    for sign in [1, -1]:
        arm_start = r_outer
        arm_end = r_outer + ARM_LENGTH
        arm_hw = ARM_THICK / 2
        msp.add_lwpolyline([
            (ax(al_t / 2 - arm_hw), ry(sign * arm_start)),
            (ax(al_t / 2 + arm_hw), ry(sign * arm_start)),
            (ax(al_t / 2 + arm_hw), ry(sign * arm_end)),
            (ax(al_t / 2 - arm_hw), ry(sign * arm_end)),
            (ax(al_t / 2 - arm_hw), ry(sign * arm_start)),
        ], dxfattribs={"layer": "OUTLINE"})

    # Al/PEEK boundary (hidden line at al_t)
    msp.add_line((ax(al_t), ry(-r_outer)), (ax(al_t), ry(r_outer)),
                 dxfattribs={"layer": "HIDDEN"})

    # Dimensions
    add_linear_dim(msp, (ax(0), ry(-r_outer) - 5 * s),
                   (ax(total_t), ry(-r_outer) - 5 * s),
                   offset=-8 * s, text=TOTAL_THICK_TOL.text, angle=0)

    # Arm thickness callout
    add_linear_dim(msp,
                   (ax(al_t / 2 - ARM_THICK / 2), ry(r_outer + ARM_LENGTH) + 3 * s),
                   (ax(al_t / 2 + ARM_THICK / 2), ry(r_outer + ARM_LENGTH) + 3 * s),
                   offset=5 * s, text=f"{ARM_THICK}", angle=0)

    # OD dim
    add_linear_dim(msp, (ax(-3), ry(-r_outer)),
                   (ax(-3), ry(r_outer)),
                   offset=-8 * s, text=FLANGE_OD_TOL.dia_text, angle=90)


# ═══════════════════════════════════════════════════════════════════════════════
# Detail I: O-ring groove enlargement (5:1)
# ═══════════════════════════════════════════════════════════════════════════════

def flange_detail_oring(msp, ox, oy, scale):
    """Detail I: enlarged cross-section of O-ring groove (5:1).

    Shows groove width, groove depth, and groove bottom radius in the
    Al flange body at the PEEK mating face.
    """
    s = scale
    # centre → bottom-left origin
    oy = oy - (ORING_GROOVE_DEPTH * 5 + 20) / 2 * s
    groove_w = ORING_GROOVE_WIDTH
    groove_d = ORING_GROOVE_DEPTH
    al_t = FLANGE_AL_THICK

    # Context: a slice of the Al body around the groove
    ctx_w = groove_w + 6.0   # context width (radial)
    ctx_h = groove_d + 4.0   # context height (axial)

    cx = ox + (ctx_w / 2 + 3) * s
    # Al top surface (mating face)
    al_top = oy + (ctx_h - 1) * s

    # Al body block
    body_left = cx - (ctx_w / 2) * s
    body_right = cx + (ctx_w / 2) * s
    body_bot = oy + 1 * s
    msp.add_lwpolyline([
        (body_left, body_bot), (body_right, body_bot),
        (body_right, al_top), (body_left, al_top),
        (body_left, body_bot),
    ], dxfattribs={"layer": "OUTLINE"})

    # O-ring groove (rectangular pocket from top)
    ghw = groove_w / 2
    groove_left = cx - ghw * s
    groove_right = cx + ghw * s
    groove_bot = al_top - groove_d * s
    msp.add_lwpolyline([
        (groove_left, al_top), (groove_left, groove_bot),
        (groove_right, groove_bot), (groove_right, al_top),
    ], dxfattribs={"layer": "OUTLINE"})

    # Hatch body (with groove subtracted)
    add_section_hatch_with_holes(msp,
        outer_boundary=[
            (body_left, body_bot), (body_right, body_bot),
            (body_right, al_top), (body_left, al_top),
        ],
        inner_boundaries=[
            [(groove_left, groove_bot), (groove_right, groove_bot),
             (groove_right, al_top), (groove_left, al_top)],
        ],
        pattern="ANSI31", scale=0.8)

    # O-ring cross-section indication (dashed circle in groove)
    oring_r = ORING_CS / 2
    oring_cy = groove_bot + oring_r * s
    msp.add_circle((cx, oring_cy), oring_r * s,
                   dxfattribs={"layer": "HIDDEN"})

    # Centerline through groove
    add_centerline_v(msp, cx, al_top + 3 * s, groove_bot - 3 * s)

    # Dimensions
    # Groove width
    add_linear_dim(msp, (groove_left, al_top + 2 * s),
                   (groove_right, al_top + 2 * s),
                   offset=3 * s,
                   text=ORING_GROOVE_W_TOL.text, angle=0)
    # Groove depth
    add_linear_dim(msp, (groove_right + 2 * s, al_top),
                   (groove_right + 2 * s, groove_bot),
                   offset=3 * s,
                   text=ORING_GROOVE_D_TOL.text, angle=90)
    # O-ring CS diameter
    add_diameter_dim(msp, (cx, oring_cy), oring_r * s,
                     angle_deg=315, text=f"Φ{ORING_CS}")

    # Surface symbol on groove bottom
    add_surface_symbol(msp, (cx + 5 * s, groove_bot - 1 * s),
                       SURF_CRITICAL.ra)


# ═══════════════════════════════════════════════════════════════════════════════
# Sheet assembly
# ═══════════════════════════════════════════════════════════════════════════════

def draw_flange_sheet(output_dir: str) -> str:
    """Generate EE-001-01 flange three-view A3 sheet."""
    # bbox: (width, height) at 1:1
    front_w = (FLANGE_R + ARM_LENGTH) * 2 + 30  # full disc + arms + margin
    front_h = front_w  # circular, symmetric

    top_w = front_w  # same radial extent
    top_h = FLANGE_TOTAL_THICK + 15  # thickness + dim space

    left_w = FLANGE_TOTAL_THICK + 15
    left_h = front_h

    detail_wh = (ORING_GROOVE_WIDTH * 5 + 20, ORING_GROOVE_DEPTH * 5 + 20)

    sheet = ThreeViewSheet(
        part_no="GIS-EE-001-01",
        name="法兰本体（含十字悬臂）",
        material="7075-T6 铝合金",
        scale="1:2",
        weight_g=280,
        date="2026-03-16",
    )
    sheet.draw_front(flange_front_view, bbox=(front_w, front_h))
    sheet.draw_top(flange_top_view, bbox=(top_w, top_h))
    sheet.draw_left(flange_left_view, bbox=(left_w, left_h))
    sheet.draw_detail(flange_detail_oring, "I", bbox=detail_wh,
                      scale_factor=5.0, position="bottom_right")
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    draw_flange_sheet(out)
    print("Done.")
