"""
SLP-300 动板 Engineering Drawing
GB/T 4458.1 三视图 A3 图纸
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from params import (
    MOV_PLATE_W, MOV_PLATE_H, PLATE_THICK,
    LS_X, LS_Y, GS_X, GS_Y,
    LM10UU_OD,
)
from drawing import (
    add_line, add_circle, add_arc,
    dim_linear, dim_diameter,
    add_centerline, add_centerline_circle,
    LAYER_HIDDEN, LAYER_CENTER,
)
from draw_three_view import ThreeViewSheet
from ezdxf.layouts import Modelspace


def front_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """主视图：俯视（XY 平面，150×100）"""
    s = scale
    w = MOV_PLATE_W * s
    h = MOV_PLATE_H * s
    cx = ox + w / 2
    cy = oy + h / 2

    # 外框
    add_line(msp, (ox, oy), (ox + w, oy))
    add_line(msp, (ox + w, oy), (ox + w, oy + h))
    add_line(msp, (ox + w, oy + h), (ox, oy + h))
    add_line(msp, (ox, oy + h), (ox, oy))

    # 中心线
    add_centerline(msp, (ox - 5, cy), (ox + w + 5, cy))
    add_centerline(msp, (cx, oy - 5), (cx, oy + h + 5))

    # 丝杠螺母孔 φ22 ×2
    for dx, dy in [(-LS_X * s, LS_Y * s), (LS_X * s, -LS_Y * s)]:
        add_circle(msp, (cx + dx, cy + dy), 11 * s)
        add_centerline_circle(msp, (cx + dx, cy + dy), 11 * s)

    # LM10UU 轴承孔 φ19 ×2
    for dx, dy in [(GS_X * s, GS_Y * s), (-GS_X * s, -GS_Y * s)]:
        add_circle(msp, (cx + dx, cy + dy), 9.5 * s)
        add_centerline_circle(msp, (cx + dx, cy + dy), 9.5 * s)

    # 中心油管孔 φ16
    add_circle(msp, (cx, cy), 8 * s)
    add_centerline_circle(msp, (cx, cy), 8 * s)

    # 电缆孔 φ10 (X=+30)
    add_circle(msp, (cx + 30 * s, cy), 5 * s)
    add_centerline_circle(msp, (cx + 30 * s, cy), 5 * s)

    # M6 液压钳安装孔 ×4
    for dx, dy in [(-35 * s, 25 * s), (35 * s, 25 * s),
                   (-35 * s, -25 * s), (35 * s, -25 * s)]:
        add_circle(msp, (cx + dx, cy + dy), 3.35 * s)
        add_centerline_circle(msp, (cx + dx, cy + dy), 3.35 * s)

    # 尺寸标注
    dim_linear(msp, (ox, oy - 12), (ox + w, oy - 12),
               (ox, oy), (ox + w, oy), f"{MOV_PLATE_W}")
    dim_linear(msp, (ox - 12, oy), (ox - 12, oy + h),
               (ox, oy), (ox, oy + h), f"{MOV_PLATE_H}", angle=90)
    dim_diameter(msp, (cx - LS_X * s, cy + LS_Y * s), 11 * s, "φ22")
    dim_diameter(msp, (cx + GS_X * s, cy + GS_Y * s), 9.5 * s, "φ19")
    dim_diameter(msp, (cx, cy), 8 * s, "φ16")
    dim_diameter(msp, (cx + 30 * s, cy), 5 * s, "φ10")
    dim_diameter(msp, (cx - 35 * s, cy + 25 * s), 3.35 * s, "φ6.7")

    # 孔位距离
    dim_linear(msp, (cx - LS_X * s, oy - 20), (cx + LS_X * s, oy - 20),
               (cx - LS_X * s, oy), (cx + LS_X * s, oy), f"{2*LS_X}")


def side_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """侧视图：板厚方向"""
    s = scale
    w = MOV_PLATE_H * s
    h = PLATE_THICK * s

    add_line(msp, (ox, oy), (ox + w, oy))
    add_line(msp, (ox + w, oy), (ox + w, oy + h))
    add_line(msp, (ox + w, oy + h), (ox, oy + h))
    add_line(msp, (ox, oy + h), (ox, oy))

    dim_linear(msp, (ox - 8, oy), (ox - 8, oy + h),
               (ox, oy), (ox, oy + h), f"{PLATE_THICK}", angle=90)


def draw_moving_plate_sheet(output_dir: str) -> str:
    sheet = ThreeViewSheet(
        part_no="SLP-300",
        name="动板",
        material="Al 6061-T6  硬质阳极氧化≥25μm",
        scale="1:1",
        weight_g=290.0,
        date="2026-03-29",
        designer="proecheng",
    )
    sheet.draw_front(front_view, bbox=(MOV_PLATE_W, MOV_PLATE_H))
    sheet.draw_left(side_view, bbox=(MOV_PLATE_H, PLATE_THICK))
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.environ.get("CAD_OUTPUT_DIR",
                        os.path.join(os.path.dirname(__file__), "../../output"))
    os.makedirs(out, exist_ok=True)
    draw_moving_plate_sheet(out)
    print("Done.")
