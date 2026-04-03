"""
SLP-P02 导向轴 φ10h6×296mm Engineering Drawing
GB/T 4458.1 A3 图纸
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from params import GUIDE_D, GUIDE_L
from drawing import (
    add_line, add_circle,
    dim_linear, dim_diameter,
    add_centerline,
    LAYER_HIDDEN,
)
from draw_three_view import ThreeViewSheet
from ezdxf.layouts import Modelspace


def front_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """主视图：轴向正视"""
    s = scale
    # Convert centre origin to bottom-left for legacy geometry code
    ox = ox - GUIDE_L / 2 * s
    total = GUIDE_L * s
    r = GUIDE_D / 2 * s
    cy = oy + r
    chamfer = 1.5 * s  # C1.5

    # 上轮廓线
    add_line(msp, (ox + chamfer, cy + r), (ox + total - chamfer, cy + r))
    # 下轮廓线
    add_line(msp, (ox + chamfer, cy - r), (ox + total - chamfer, cy - r))
    # 左端倒角
    add_line(msp, (ox, cy), (ox + chamfer, cy + r))
    add_line(msp, (ox, cy), (ox + chamfer, cy - r))
    # 右端倒角
    add_line(msp, (ox + total, cy), (ox + total - chamfer, cy + r))
    add_line(msp, (ox + total, cy), (ox + total - chamfer, cy - r))

    # 中心线
    add_centerline(msp, (ox - 5, cy), (ox + total + 5, cy))

    # 尺寸标注
    dim_linear(msp, (ox, oy - 12), (ox + total, oy - 12),
               (ox, oy), (ox + total, oy), f"{GUIDE_L}")
    dim_diameter(msp, (ox + total / 2, cy), r, f"phi{GUIDE_D}h6")


def end_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """端视图：轴端面"""
    s = scale
    r = GUIDE_D / 2 * s
    cx = ox + r + 5
    cy = oy + r + 5
    add_circle(msp, (cx, cy), r)
    add_centerline(msp, (cx - r - 3, cy), (cx + r + 3, cy))
    add_centerline(msp, (cx, cy - r - 3), (cx, cy + r + 3))
    dim_diameter(msp, (cx, cy), r, f"phi{GUIDE_D}h6")


def draw_guide_shaft_sheet(output_dir: str) -> str:
    scale = 1.0
    sheet = ThreeViewSheet(
        part_no="SLP-P02",
        name="导向轴",
        material="45# 钢  镀硬铬 HV800+  Ra0.4",
        scale="1:1",
        weight_g=183.0,
        date="2026-03-29",
        designer="proecheng",
    )
    sheet.draw_front(front_view, bbox=(GUIDE_L, GUIDE_D))
    sheet.draw_left(end_view, bbox=(GUIDE_D + 10, GUIDE_D + 10))
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.environ.get("CAD_OUTPUT_DIR",
                        os.path.join(os.path.dirname(__file__), "../../output"))
    os.makedirs(out, exist_ok=True)
    draw_guide_shaft_sheet(out)
    print("Done.")
