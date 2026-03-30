"""
SLP-200/201 支撑条（底部左右各一） Engineering Drawing
GB/T 4458.1 A3 图纸
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from params import SUP_BAR_W, SUP_BAR_H, PLATE_THICK
from drawing import (
    add_line, add_circle,
    dim_linear, dim_diameter,
    add_centerline, add_centerline_circle,
    LAYER_HIDDEN,
)
from draw_three_view import ThreeViewSheet
from ezdxf.layouts import Modelspace


def front_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """主视图：俯视（XY平面 50x100）"""
    s = scale
    w = SUP_BAR_W * s
    h = SUP_BAR_H * s
    cx = ox + w / 2
    cy = oy + h / 2

    add_line(msp, (ox, oy), (ox + w, oy))
    add_line(msp, (ox + w, oy), (ox + w, oy + h))
    add_line(msp, (ox + w, oy + h), (ox, oy + h))
    add_line(msp, (ox, oy + h), (ox, oy))

    add_centerline(msp, (ox - 5, cy), (ox + w + 5, cy))
    add_centerline(msp, (cx, oy - 5), (cx, oy + h + 5))

    # 丝杠穿过孔 phi24 (Y=+30)
    add_circle(msp, (cx, cy + 30 * s), 12 * s)
    add_centerline_circle(msp, (cx, cy + 30 * s), 12 * s)
    dim_diameter(msp, (cx, cy + 30 * s), 12 * s, "phi24")

    # 导向轴孔 phi10H7 (Y=-30)
    add_circle(msp, (cx, cy - 30 * s), 5 * s)
    add_centerline_circle(msp, (cx, cy - 30 * s), 5 * s)
    dim_diameter(msp, (cx, cy - 30 * s), 5 * s, "phi10H7")

    dim_linear(msp, (ox, oy - 12), (ox + w, oy - 12),
               (ox, oy), (ox + w, oy), f"{SUP_BAR_W}")
    dim_linear(msp, (ox - 12, oy), (ox - 12, oy + h),
               (ox, oy), (ox, oy + h), f"{SUP_BAR_H}", angle=90)
    dim_linear(msp, (ox + w + 10, cy + 30 * s), (ox + w + 10, cy - 30 * s),
               (cx, cy + 30 * s), (cx, cy - 30 * s), "60", angle=90)


def side_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """侧视图：厚度方向"""
    s = scale
    w = SUP_BAR_H * s
    h = PLATE_THICK * s

    add_line(msp, (ox, oy), (ox + w, oy))
    add_line(msp, (ox + w, oy), (ox + w, oy + h))
    add_line(msp, (ox + w, oy + h), (ox, oy + h))
    add_line(msp, (ox, oy + h), (ox, oy))

    dim_linear(msp, (ox - 8, oy), (ox - 8, oy + h),
               (ox, oy), (ox, oy + h), f"{PLATE_THICK}", angle=90)


def draw_support_bar_sheet(output_dir: str) -> str:
    sheet = ThreeViewSheet(
        part_no="SLP-200",
        name="支撑条",
        material="Al 6061-T6  硬质阳极氧化>=25um",
        scale="1:1",
        weight_g=95.0,
        date="2026-03-29",
        designer="proecheng",
    )
    sheet.draw_front(front_view, bbox=(SUP_BAR_W, SUP_BAR_H))
    sheet.draw_left(side_view, bbox=(SUP_BAR_H, PLATE_THICK))
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.environ.get("CAD_OUTPUT_DIR",
                        os.path.join(os.path.dirname(__file__), "../../output"))
    os.makedirs(out, exist_ok=True)
    draw_support_bar_sheet(out)
    print("Done.")
