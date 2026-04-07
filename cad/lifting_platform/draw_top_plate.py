"""
[DEPRECATED] SLP-100 上固定板 Engineering Drawing — 手写旧版

此文件为手写的 2D 工程图，孔位与 3D 模型不一致（手动 8 孔 vs 3D 5 孔），
已被自动管线取代。正式 2D 图由 p100.py:draw_p100_sheet() 通过
auto_three_view() + auto_annotate() 自动生成。

请勿使用此文件。如需修改 SLP-100 的 2D 图，应修改：
- 管线工具层: drawing.py / cq_to_dxf.py
- 模板层: templates/part_module.py.j2
- 3D 几何源: p100.py:make_p100()

GB/T 4458.1 三视图 A3 图纸
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from params import (
    TOP_PLATE_W, TOP_PLATE_H, PLATE_THICK,
    LS_X, LS_Y, GS_X, GS_Y,
)
from drawing import (
    add_line, add_circle, add_arc,
    dim_linear, dim_diameter, dim_radius,
    add_centerline, add_centerline_circle,
    add_hatch, add_thread_symbol,
    DIM_TEXT_H, LAYER_VISIBLE, LAYER_HIDDEN, LAYER_CENTER,
)
from draw_three_view import ThreeViewSheet
from ezdxf.layouts import Modelspace


def front_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """主视图：俯视（XY 平面，200×100）"""
    s = scale
    # Convert centre origin to bottom-left for legacy geometry code
    ox = ox - TOP_PLATE_W / 2 * s
    oy = oy - TOP_PLATE_H / 2 * s
    w = TOP_PLATE_W * s
    h = TOP_PLATE_H * s

    # 外框
    add_line(msp, (ox, oy), (ox + w, oy))
    add_line(msp, (ox + w, oy), (ox + w, oy + h))
    add_line(msp, (ox + w, oy + h), (ox, oy + h))
    add_line(msp, (ox, oy + h), (ox, oy))

    cx = ox + w / 2
    cy = oy + h / 2

    # 中心线
    add_centerline(msp, (ox - 5, cy), (ox + w + 5, cy))
    add_centerline(msp, (cx, oy - 5), (cx, oy + h + 5))

    # 丝杠孔 φ24 ×2  (对角布置)
    for dx, dy in [(-LS_X * s, LS_Y * s), (LS_X * s, -LS_Y * s)]:
        add_circle(msp, (cx + dx, cy + dy), 12 * s)  # r=12
        add_centerline_circle(msp, (cx + dx, cy + dy), 12 * s)

    # 导向轴孔 φ10H7 ×2
    for dx, dy in [(GS_X * s, GS_Y * s), (-GS_X * s, -GS_Y * s)]:
        add_circle(msp, (cx + dx, cy + dy), 5 * s)  # r=5
        add_centerline_circle(msp, (cx + dx, cy + dy), 5 * s)

    # M5 机器人接口孔 ×4（φ5.5）
    for dx, dy in [(-80 * s, 35 * s), (80 * s, 35 * s),
                   (-80 * s, -35 * s), (80 * s, -35 * s)]:
        add_circle(msp, (cx + dx, cy + dy), 2.75 * s)
        add_centerline_circle(msp, (cx + dx, cy + dy), 2.75 * s)

    # 尺寸标注
    dim_linear(msp, (ox, oy - 12), (ox + w, oy - 12),
               (ox, oy), (ox + w, oy), f"{TOP_PLATE_W}")
    dim_linear(msp, (ox - 12, oy), (ox - 12, oy + h),
               (ox, oy), (ox, oy + h), f"{TOP_PLATE_H}", angle=90)
    # 孔位尺寸
    dim_linear(msp, (ox, oy - 20), (cx - LS_X * s, oy - 20),
               (ox, oy), (cx - LS_X * s, oy), f"{TOP_PLATE_W//2 - LS_X}")
    dim_diameter(msp, (cx - LS_X * s, cy + LS_Y * s), 12 * s, "φ24")
    dim_diameter(msp, (cx + GS_X * s, cy + GS_Y * s), 5 * s, "φ10H7")
    dim_diameter(msp, (cx - 80 * s, cy + 35 * s), 2.75 * s, "φ5.5")


def side_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """侧视图：右视（厚度方向 8mm）"""
    s = scale
    # Convert centre origin to bottom-left for legacy geometry code
    ox = ox - TOP_PLATE_H / 2 * s
    oy = oy - PLATE_THICK / 2 * s
    w = TOP_PLATE_H * s   # 深度
    h = PLATE_THICK * s   # 厚度

    add_line(msp, (ox, oy), (ox + w, oy))
    add_line(msp, (ox + w, oy), (ox + w, oy + h))
    add_line(msp, (ox + w, oy + h), (ox, oy + h))
    add_line(msp, (ox, oy + h), (ox, oy))

    # 孔（隐线）
    for dy in [LS_Y * s, -LS_Y * s]:
        cy = oy + h / 2
        cx_h = ox + w / 2 + dy
        add_line(msp, (cx_h - 12 * s, oy), (cx_h - 12 * s, oy + h),
                 layer=LAYER_HIDDEN)
        add_line(msp, (cx_h + 12 * s, oy), (cx_h + 12 * s, oy + h),
                 layer=LAYER_HIDDEN)

    dim_linear(msp, (ox, oy - 8), (ox + w, oy - 8),
               (ox, oy), (ox + w, oy), f"{TOP_PLATE_H}")
    dim_linear(msp, (ox - 8, oy), (ox - 8, oy + h),
               (ox, oy), (ox, oy + h), f"{PLATE_THICK}", angle=90)


def draw_top_plate_sheet(output_dir: str) -> str:
    sheet = ThreeViewSheet(
        part_no="SLP-100",
        name="上固定板",
        material="Al 6061-T6  硬质阳极氧化≥25μm",
        scale="1:1",
        weight_g=430.0,
        date="2026-03-29",
        designer="proecheng",
    )
    sheet.draw_front(front_view, bbox=(TOP_PLATE_W, TOP_PLATE_H))
    sheet.draw_left(side_view, bbox=(TOP_PLATE_H, PLATE_THICK))
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.environ.get("CAD_OUTPUT_DIR",
                        os.path.join(os.path.dirname(__file__), "../../output"))
    os.makedirs(out, exist_ok=True)
    draw_top_plate_sheet(out)
    print("Done.")
