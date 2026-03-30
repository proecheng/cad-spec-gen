"""
SLP-P01 丝杠 Tr16x4 Engineering Drawing
GB/T 4458.1 + GB/T 4459.1(螺纹画法) A3 图纸
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from params import (
    SCREW_TOTAL_L, SCREW_THREAD_D, SCREW_SHAFT_D,
    SCREW_UPPER_SHAFT_L, SCREW_THREAD_L, SCREW_LOWER_SHAFT_L,
)
from drawing import (
    add_line, add_circle,
    dim_linear, dim_diameter,
    add_centerline, add_thread_symbol,
    LAYER_HIDDEN, LAYER_CENTER,
)
from draw_three_view import ThreeViewSheet
from ezdxf.layouts import Modelspace


def front_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """主视图：正视（轴向截面）"""
    s = scale
    total = SCREW_TOTAL_L * s
    td = SCREW_THREAD_D * s   # 螺纹大径 16
    sd = SCREW_SHAFT_D * s    # 轴径 12
    r_t = td / 2
    r_s = sd / 2

    # 上轴头 (40mm)
    usl = SCREW_UPPER_SHAFT_L * s
    # 螺纹段 (230mm)
    thl = SCREW_THREAD_L * s
    # 下轴头 (70mm 含联轴器区)
    lsl = SCREW_LOWER_SHAFT_L * s

    cy = oy + r_t  # center Y

    # 上轴头矩形
    add_line(msp, (ox, cy - r_s), (ox + usl, cy - r_s))
    add_line(msp, (ox, cy + r_s), (ox + usl, cy + r_s))
    add_line(msp, (ox, cy - r_s), (ox, cy + r_s))
    # 过渡台阶
    add_line(msp, (ox + usl, cy - r_s), (ox + usl, cy - r_t))
    add_line(msp, (ox + usl, cy + r_s), (ox + usl, cy + r_t))

    # 螺纹段外径
    x1 = ox + usl
    add_line(msp, (x1, cy - r_t), (x1 + thl, cy - r_t))
    add_line(msp, (x1, cy + r_t), (x1 + thl, cy + r_t))
    # 螺纹小径（虚线 GB/T 4459.1）
    r_minor = 6.5 * s  # Tr16x4 小径约 13mm -> r=6.5
    add_line(msp, (x1, cy - r_minor), (x1 + thl, cy - r_minor), layer=LAYER_HIDDEN)
    add_line(msp, (x1, cy + r_minor), (x1 + thl, cy + r_minor), layer=LAYER_HIDDEN)

    # 过渡台阶
    x2 = x1 + thl
    add_line(msp, (x2, cy - r_t), (x2, cy - r_s))
    add_line(msp, (x2, cy + r_t), (x2, cy + r_s))

    # 下轴头
    add_line(msp, (x2, cy - r_s), (x2 + lsl, cy - r_s))
    add_line(msp, (x2, cy + r_s), (x2 + lsl, cy + r_s))
    add_line(msp, (x2 + lsl, cy - r_s), (x2 + lsl, cy + r_s))

    # 中心线
    add_centerline(msp, (ox - 5, cy), (ox + total + 5, cy))

    # 尺寸标注
    dim_linear(msp, (ox, oy - 12), (ox + total, oy - 12),
               (ox, oy), (ox + total, oy), f"{SCREW_TOTAL_L}")
    dim_linear(msp, (ox, oy - 20), (ox + usl, oy - 20),
               (ox, oy), (ox + usl, oy), f"{SCREW_UPPER_SHAFT_L}")
    dim_linear(msp, (x1, oy - 20), (x2, oy - 20),
               (x1, oy), (x2, oy), f"{SCREW_THREAD_L}")
    dim_linear(msp, (x2, oy - 20), (x2 + lsl, oy - 20),
               (x2, oy), (x2 + lsl, oy), f"{SCREW_LOWER_SHAFT_L}")
    # 直径标注
    dim_diameter(msp, (ox + usl / 2, cy), r_s, f"phi{SCREW_SHAFT_D}")
    dim_diameter(msp, (x1 + thl / 2, cy), r_t, f"Tr{SCREW_THREAD_D}x4")


def end_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """端视图：轴端面"""
    s = scale
    r = SCREW_SHAFT_D / 2 * s
    cx = ox + r + 5
    cy = oy + r + 5
    add_circle(msp, (cx, cy), r)
    add_centerline(msp, (cx - r - 3, cy), (cx + r + 3, cy))
    add_centerline(msp, (cx, cy - r - 3), (cx, cy + r + 3))
    dim_diameter(msp, (cx, cy), r, f"phi{SCREW_SHAFT_D}")


def draw_screw_sheet(output_dir: str) -> str:
    scale = 0.5  # 丝杠较长，缩小
    sheet = ThreeViewSheet(
        part_no="SLP-P01",
        name="丝杠Tr16x4",
        material="45# 钢  调质 HRC28-32",
        scale="1:2",
        weight_g=520.0,
        date="2026-03-29",
        designer="proecheng",
    )
    sheet.draw_front(front_view, bbox=(SCREW_TOTAL_L, SCREW_THREAD_D))
    sheet.draw_left(end_view, bbox=(SCREW_SHAFT_D + 10, SCREW_SHAFT_D + 10))
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.environ.get("CAD_OUTPUT_DIR",
                        os.path.join(os.path.dirname(__file__), "../../output"))
    os.makedirs(out, exist_ok=True)
    draw_screw_sheet(out)
    print("Done.")
