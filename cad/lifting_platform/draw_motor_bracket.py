"""
SLP-400 电机支架 Engineering Drawing
GB/T 4458.1 A3 图纸
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from params import BRACKET_W, BRACKET_H, PLATE_THICK, BRACKET_CENTER_HOLE
from drawing import (
    add_line, add_circle,
    dim_linear, dim_diameter,
    add_centerline, add_centerline_circle,
    LAYER_HIDDEN,
)
from draw_three_view import ThreeViewSheet
from ezdxf.layouts import Modelspace

# NEMA23 bolt pattern: 4xM5 on 47.14mm PCD
_NEMA_PCD = 47.14
_NEMA_BOLT_R = _NEMA_PCD / 2
import math
_NEMA_ANGLES = [45, 135, 225, 315]


def front_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """主视图：正视（XY 平面，70x90）"""
    s = scale
    w = BRACKET_W * s
    h = BRACKET_H * s
    cx = ox + w / 2
    cy = oy + h / 2

    add_line(msp, (ox, oy), (ox + w, oy))
    add_line(msp, (ox + w, oy), (ox + w, oy + h))
    add_line(msp, (ox + w, oy + h), (ox, oy + h))
    add_line(msp, (ox, oy + h), (ox, oy))

    add_centerline(msp, (ox - 5, cy), (ox + w + 5, cy))
    add_centerline(msp, (cx, oy - 5), (cx, oy + h + 5))

    # 电机轴孔 phi28
    add_circle(msp, (cx, cy), BRACKET_CENTER_HOLE / 2 * s)
    add_centerline_circle(msp, (cx, cy), BRACKET_CENTER_HOLE / 2 * s)
    dim_diameter(msp, (cx, cy), BRACKET_CENTER_HOLE / 2 * s, "phi28")

    # NEMA23 4xM5 安装孔
    for ang in _NEMA_ANGLES:
        rad = math.radians(ang)
        hx = cx + _NEMA_BOLT_R * math.cos(rad) * s
        hy = cy + _NEMA_BOLT_R * math.sin(rad) * s
        add_circle(msp, (hx, hy), 2.5 * s)
        add_centerline_circle(msp, (hx, hy), 2.5 * s)

    dim_linear(msp, (ox, oy - 12), (ox + w, oy - 12),
               (ox, oy), (ox + w, oy), f"{BRACKET_W}")
    dim_linear(msp, (ox - 12, oy), (ox - 12, oy + h),
               (ox, oy), (ox, oy + h), f"{BRACKET_H}", angle=90)
    # PCD 标注
    dim_diameter(msp, (cx, cy), _NEMA_BOLT_R * s, f"PCD {_NEMA_PCD}")


def side_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """侧视图：厚度方向"""
    s = scale
    w = BRACKET_H * s
    h = PLATE_THICK * s

    add_line(msp, (ox, oy), (ox + w, oy))
    add_line(msp, (ox + w, oy), (ox + w, oy + h))
    add_line(msp, (ox + w, oy + h), (ox, oy + h))
    add_line(msp, (ox, oy + h), (ox, oy))

    dim_linear(msp, (ox - 8, oy), (ox - 8, oy + h),
               (ox, oy), (ox, oy + h), f"{PLATE_THICK}", angle=90)


def draw_motor_bracket_sheet(output_dir: str) -> str:
    sheet = ThreeViewSheet(
        part_no="SLP-400",
        name="电机支架",
        material="Al 6061-T6  硬质阳极氧化>=25um",
        scale="1:1",
        weight_g=120.0,
        date="2026-03-29",
        designer="proecheng",
    )
    sheet.draw_front(front_view, bbox=(BRACKET_W, BRACKET_H))
    sheet.draw_left(side_view, bbox=(BRACKET_H, PLATE_THICK))
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.environ.get("CAD_OUTPUT_DIR",
                        os.path.join(os.path.dirname(__file__), "../../output"))
    os.makedirs(out, exist_ok=True)
    draw_motor_bracket_sheet(out)
    print("Done.")
