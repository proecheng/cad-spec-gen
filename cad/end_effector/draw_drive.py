"""
ISO 9409 Adapter Plate Engineering Drawing — EE-001-08

GB/T 三视图 A3：
  - 主视图：正面（双圆孔圈 — ISO 9409 + 减速器孔位）
  - 俯视图：剖面（止口 + 厚度）
  - 左视图：与俯视图相同（对称件）

Note: 电机(ECX 22L)和减速器(GP22C)为外购件，不生成自制件图纸。

All geometry from params.py.
"""

import math
import os

from params import (
    MOTOR_OD, MOTOR_BODY_LENGTH, MOTOR_TOTAL_LENGTH,
    REDUCER_OD, REDUCER_LENGTH,
    REDUCER_OUTPUT_DIA, REDUCER_OUTPUT_LENGTH,
    REDUCER_FLANGE_DIA,
    MOTOR_FLANGE_DIA, MOTOR_FLANGE_THICK,
    REDUCER_MOUNT_PCD, REDUCER_MOUNT_BOLT_DIA, REDUCER_MOUNT_BOLT_NUM,
    ADAPTER_OD, ADAPTER_THICK, ADAPTER_CENTER_HOLE,
    ADAPTER_PILOT_DIA, ADAPTER_PILOT_DEPTH,
    ISO9409_PCD, ISO9409_BOLT_DIA, ISO9409_BOLT_NUM,
)
from drawing import (
    add_linear_dim, add_diameter_dim,
    add_section_hatch,
    add_centerline_h, add_centerline_v, add_centerline_cross,
)
from draw_three_view import ThreeViewSheet


# ═══════════════════════════════════════════════════════════════════════════════
# EE-001-08 适配板
# ═══════════════════════════════════════════════════════════════════════════════

def adapter_front_view(msp, ox, oy, scale):
    """Front view: circular plate with dual bolt patterns."""
    s = scale
    r_outer = ADAPTER_OD / 2
    r_center = ADAPTER_CENTER_HOLE / 2
    r_pilot = ADAPTER_PILOT_DIA / 2

    cx = ox + (r_outer + 10) * s
    cy = oy + (r_outer + 10) * s

    msp.add_circle((cx, cy), r_outer * s, dxfattribs={"layer": "OUTLINE"})
    msp.add_circle((cx, cy), r_center * s, dxfattribs={"layer": "OUTLINE"})
    msp.add_circle((cx, cy), r_pilot * s, dxfattribs={"layer": "HIDDEN"})
    add_centerline_cross(msp, (cx, cy), size=(r_outer + 10) * s)

    # ISO 9409 bolt holes (4×M6 on PCD50 at 45°)
    iso_r = ISO9409_PCD / 2
    msp.add_circle((cx, cy), iso_r * s, dxfattribs={"layer": "CENTER"})
    iso_half = iso_r / math.sqrt(2)
    for dx, dy in [(iso_half, iso_half), (iso_half, -iso_half),
                   (-iso_half, iso_half), (-iso_half, -iso_half)]:
        msp.add_circle((cx + dx * s, cy + dy * s),
                       (ISO9409_BOLT_DIA / 2) * s,
                       dxfattribs={"layer": "OUTLINE"})

    # Reducer mount holes (4×M3 on PCD22 at 45°)
    red_r = REDUCER_MOUNT_PCD / 2
    for i in range(REDUCER_MOUNT_BOLT_NUM):
        a = math.radians(i * 90 + 45)
        bx = cx + red_r * math.cos(a) * s
        by = cy + red_r * math.sin(a) * s
        msp.add_circle((bx, by), (REDUCER_MOUNT_BOLT_DIA / 2) * s,
                       dxfattribs={"layer": "OUTLINE"})

    # Dimensions
    add_diameter_dim(msp, (cx, cy), r_outer * s, angle_deg=30,
                     text=f"Φ{ADAPTER_OD}")
    add_diameter_dim(msp, (cx, cy), r_center * s, angle_deg=210,
                     text=f"Φ{ADAPTER_CENTER_HOLE}")
    add_diameter_dim(msp, (cx, cy), iso_r * s, angle_deg=330,
                     text=f"PCD {ISO9409_PCD} (4×M6)")
    add_diameter_dim(msp, (cx, cy), red_r * s, angle_deg=160,
                     text=f"PCD {REDUCER_MOUNT_PCD} (4×M3)")


def adapter_top_view(msp, ox, oy, scale):
    """Top view (section): plate thickness + pilot step."""
    s = scale
    # centre → bottom-left origin
    ox = ox - (ADAPTER_THICK + ADAPTER_PILOT_DEPTH + 20) / 2 * s
    r_outer = ADAPTER_OD / 2
    r_center = ADAPTER_CENTER_HOLE / 2
    r_pilot = ADAPTER_PILOT_DIA / 2
    thick = ADAPTER_THICK
    pilot_d = ADAPTER_PILOT_DEPTH

    add_centerline_h(msp, oy + (r_outer + 10) * s,
                     ox - 5 * s, ox + (thick + pilot_d + 15) * s)

    def ax(a):
        return ox + a * s

    def ry(r):
        return oy + (r_outer + r) * s + 10 * s

    for sign in [1, -1]:
        # Main body section
        pts = [
            (ax(0), ry(sign * r_center)),
            (ax(thick), ry(sign * r_center)),
            (ax(thick), ry(sign * r_outer)),
            (ax(0), ry(sign * r_outer)),
            (ax(0), ry(sign * r_center)),
        ]
        msp.add_lwpolyline(pts, dxfattribs={"layer": "OUTLINE"})
        add_section_hatch(msp, pts[:-1], pattern="ANSI31", scale=2.0)

        # Pilot step
        msp.add_line((ax(thick), ry(sign * r_pilot)),
                     (ax(thick + pilot_d), ry(sign * r_pilot)),
                     dxfattribs={"layer": "OUTLINE"})
        msp.add_line((ax(thick + pilot_d), ry(sign * r_pilot)),
                     (ax(thick + pilot_d), ry(sign * r_outer)),
                     dxfattribs={"layer": "OUTLINE"})

    # Dimensions
    add_linear_dim(msp, (ax(0), ry(r_outer) + 5 * s),
                   (ax(thick), ry(r_outer) + 5 * s),
                   offset=8 * s, text=f"{thick}", angle=0)
    add_linear_dim(msp, (ax(thick), ry(r_outer) + 3 * s),
                   (ax(thick + pilot_d), ry(r_outer) + 3 * s),
                   offset=3 * s, text=f"{pilot_d}", angle=0)
    add_linear_dim(msp, (ax(-3), ry(-r_outer)),
                   (ax(-3), ry(r_outer)),
                   offset=-8 * s, text=f"Φ{ADAPTER_OD}", angle=90)
    add_linear_dim(msp, (ax(thick + pilot_d + 3 * s), ry(-r_pilot)),
                   (ax(thick + pilot_d + 3 * s), ry(r_pilot)),
                   offset=8 * s, text=f"Φ{ADAPTER_PILOT_DIA}", angle=90)


def draw_adapter_sheet(output_dir: str) -> str:
    """Generate EE-001-08 adapter plate three-view A3 sheet."""
    r = ADAPTER_OD / 2
    front_wh = (2 * r + 25, 2 * r + 25)
    top_wh = (ADAPTER_THICK + ADAPTER_PILOT_DEPTH + 20, front_wh[1])
    left_wh = (1, 1)  # symmetric, omitted

    sheet = ThreeViewSheet(
        part_no="GIS-EE-001-08",
        name="ISO 9409适配板",
        material="7075-T6 铝合金",
        scale="1:1",
        weight_g=120,
        date="2026-03-16",
    )
    sheet.draw_front(adapter_front_view, bbox=front_wh)
    sheet.draw_top(adapter_top_view, bbox=top_wh)
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    draw_adapter_sheet(out)
    print("Done.")
