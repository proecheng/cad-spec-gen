"""
SLP-P03 T16法兰铜螺母 Engineering Drawing
GB/T 4458.1 + GB/T 4459.1(螺纹画法) A3 图纸
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from params import (
    NUT_FLANGE_D, NUT_FLANGE_THICK,
    NUT_BODY_D, NUT_BODY_L,
)
from drawing import (
    add_line, add_circle,
    dim_linear, dim_diameter,
    add_centerline, add_centerline_circle,
    add_thread_symbol,
    LAYER_HIDDEN,
)
from draw_three_view import ThreeViewSheet
from ezdxf.layouts import Modelspace

_NUT_TOTAL_L = NUT_FLANGE_THICK + NUT_BODY_L   # 25mm


def front_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """主视图：轴向截面"""
    s = scale
    r_f = NUT_FLANGE_D / 2 * s    # 法兰大径 r=16
    r_b = NUT_BODY_D / 2 * s     # 体径 r=11
    r_minor = 6.5 * s             # 内螺纹大径 Tr16 → r=8, 用大径虚线
    r_inner = 8.0 * s             # 底孔 r=8 (Tr16 底孔约 phi16 → 螺母内径)
    fl = NUT_FLANGE_THICK * s     # 法兰厚 5
    bl = NUT_BODY_L * s           # 体长 20
    total = (NUT_FLANGE_THICK + NUT_BODY_L) * s
    cy = oy + r_f

    # 法兰轮廓
    add_line(msp, (ox, cy - r_f), (ox + fl, cy - r_f))
    add_line(msp, (ox, cy + r_f), (ox + fl, cy + r_f))
    add_line(msp, (ox, cy - r_f), (ox, cy + r_f))   # 左端面
    # 法兰→体过渡台阶
    add_line(msp, (ox + fl, cy - r_f), (ox + fl, cy - r_b))
    add_line(msp, (ox + fl, cy + r_f), (ox + fl, cy + r_b))

    # 螺母体轮廓
    add_line(msp, (ox + fl, cy - r_b), (ox + total, cy - r_b))
    add_line(msp, (ox + fl, cy + r_b), (ox + total, cy + r_b))
    add_line(msp, (ox + total, cy - r_b), (ox + total, cy + r_b))  # 右端面

    # 内螺纹大径（虚线 GB/T 4459.1）
    add_line(msp, (ox, cy - r_inner), (ox + total, cy - r_inner), layer=LAYER_HIDDEN)
    add_line(msp, (ox, cy + r_inner), (ox + total, cy + r_inner), layer=LAYER_HIDDEN)

    # 中心线
    add_centerline(msp, (ox - 5, cy), (ox + total + 5, cy))

    # 尺寸标注
    dim_linear(msp, (ox, oy - 12), (ox + total, oy - 12),
               (ox, oy), (ox + total, oy), f"{_NUT_TOTAL_L}")
    dim_linear(msp, (ox, oy - 20), (ox + fl, oy - 20),
               (ox, oy), (ox + fl, oy), f"{NUT_FLANGE_THICK}")
    dim_linear(msp, (ox + fl, oy - 20), (ox + total, oy - 20),
               (ox + fl, oy), (ox + total, oy), f"{NUT_BODY_L}")
    dim_diameter(msp, (ox + fl / 2, cy), r_f, f"phi{NUT_FLANGE_D}")
    dim_diameter(msp, (ox + fl + bl / 2, cy), r_b, f"phi{NUT_BODY_D}")
    dim_diameter(msp, (ox + total / 2, cy), r_inner, "Tr16x4")


def end_view(msp: Modelspace, ox: float, oy: float, scale: float) -> None:
    """端视图：法兰端面"""
    s = scale
    r_f = NUT_FLANGE_D / 2 * s
    r_b = NUT_BODY_D / 2 * s
    cx = ox + r_f + 5
    cy = oy + r_f + 5

    # 法兰圆
    add_circle(msp, (cx, cy), r_f)
    add_centerline_circle(msp, (cx, cy), r_f)
    # 体径圆（内部可见）
    add_circle(msp, (cx, cy), r_b)
    # 中心内螺纹孔（虚线）
    add_circle(msp, (cx, cy), 8 * s, layer=LAYER_HIDDEN)
    add_centerline(msp, (cx - r_f - 3, cy), (cx + r_f + 3, cy))
    add_centerline(msp, (cx, cy - r_f - 3), (cx, cy + r_f + 3))

    dim_diameter(msp, (cx, cy), r_f, f"phi{NUT_FLANGE_D}")


def draw_nut_sheet(output_dir: str) -> str:
    sheet = ThreeViewSheet(
        part_no="SLP-P03",
        name="T16法兰铜螺母",
        material="锡青铜 ZCuSn10Pb1  精车",
        scale="2:1",
        weight_g=45.0,
        date="2026-03-29",
        designer="proecheng",
    )
    sheet.draw_front(front_view, bbox=(_NUT_TOTAL_L, NUT_FLANGE_D))
    sheet.draw_left(end_view, bbox=(NUT_FLANGE_D + 10, NUT_FLANGE_D + 10))
    return sheet.save(output_dir)


if __name__ == "__main__":
    out = os.environ.get("CAD_OUTPUT_DIR",
                        os.path.join(os.path.dirname(__file__), "../../output"))
    os.makedirs(out, exist_ok=True)
    draw_nut_sheet(out)
    print("Done.")
