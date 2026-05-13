"""
上限位传感器支架 (SLP-404)

CP-1 Task 5f hand-completed 2026-05-13（从 codegen scaffold 升级到带特征几何）

几何与 SLP-403 完全相同（30×30×8 + M8 + 2×M3）；
两件区别仅在装配位置：
- SLP-404 装上板底面 (-80, ±5)（CAD_SPEC.md §6.2 step 17）

设计依据：tmp/_custom_parts_spec.md §6
"""

import cadquery as cq
from params import *


# 几何常量（与 SLP-403 一致；不同件保持各自副本，便于后续若需差异化时分别调整）
SENSOR_BRACKET_W = 30.0
SENSOR_BRACKET_H = 30.0
SENSOR_BRACKET_T = PLATE_THICK
SENSOR_HOLE_DIA = 8.4
M3_CLEARANCE = 3.4
M3_PITCH_Y = 10.0


def make_p404() -> cq.Workplane:
    """SLP-404: 上限位传感器支架 — 6061-T6 铝板

    Envelope: 30 × 30 × 8 mm（Task 0 spec §6 真值）
    Weight: ~20g

    Axis: +Z 板法线；装上板底面时 assembly_layout 会做 Z 翻转（旋转 180°X）
          以让 M8 孔朝下指向运动方向，但本件局部几何对称无方向问题。
    Doc:  CAD_SPEC.md §6.2 step 17 + tmp/_custom_parts_spec.md §6
    """
    body = cq.Workplane("XY").box(
        SENSOR_BRACKET_W, SENSOR_BRACKET_H, SENSOR_BRACKET_T,
        centered=(True, True, False),
    )
    # 中心 Φ8.4 M8 接近开关孔（通孔）
    body = body.cut(
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, 0))
        .circle(SENSOR_HOLE_DIA / 2.0)
        .extrude(SENSOR_BRACKET_T)
    )
    # 2× Φ3.4 M3 安装孔，沿 ±Y 方向距中心 10 mm
    for _y in (-M3_PITCH_Y, +M3_PITCH_Y):
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(0, _y, 0))
            .circle(M3_CLEARANCE / 2.0)
            .extrude(SENSOR_BRACKET_T)
        )

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """扁平板件，与 p403/p100/p300/p400 一致。"""
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §6.2 step 17 / Task 0 spec §6",
    }


def draw_p404_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-404."""
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p404()
    sheet = ThreeViewSheet(
        part_no="SLP-404",
        name="上限位传感器支架",
        material="6061-T6 铝",
        scale="1:1",
        weight_g=20,
        date=date.today().isoformat(),
        project_name="SLP",
        subsystem_name="丝杠式升降平台",
    )
    auto_three_view(solid, sheet)

    # GB/T 标注 — 数据来自 CAD_SPEC.md §2，不硬编码
    auto_annotate(solid, sheet, annotation_meta={
        "dim_tolerances": [{"fit_code": "", "label": "±0.1 mm", "lower": "-0.1", "name": "POS_ACC", "nominal": "0.1", "upper": "+0.1"}, {"fit_code": "", "label": "±0.05 mm", "lower": "-0.05", "name": "PARAM_L1204", "nominal": "0.05", "upper": "+0.05"}],
        "gdt": [],
        "surfaces": [],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_p404()
    p = os.path.join(out, "SLP-404.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
