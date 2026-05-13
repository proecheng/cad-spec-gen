"""
下限位传感器支架 (SLP-403)

CP-1 Task 5e hand-completed 2026-05-13（从 codegen scaffold 升级到带特征几何）

设计依据：
- `tmp/_custom_parts_spec.md` §6 — v1 取保守方块设计，envelope 30×30×8 mm
- CAD_SPEC.md §6.2 step 16-18 — M8 接近开关 (SLP-F12，Φ8×45) 装配
- 板厚统一 PLATE_THICK = 8 mm（params.py 沉淀）

几何要点：
- 30×30×8 mm 铝板
- 中心 1× Φ8.4 通孔（M8 接近开关压入，传感器自带螺纹）
- 2× Φ3.4 通孔（M3 安装孔），沿 +Y/-Y 方向对称分布在传感器孔两侧
  间距 ±10 mm（Task 0 spec 推断："间距 10 mm"）

装配位置（assembly_layout.py 处理，不在本文件）：
- SLP-403 装左支撑条顶面 (-80, ±5)（局部坐标，§6.2 step 16）
"""

import cadquery as cq
from params import *


# 几何常量（与本件高度耦合，集中放在此处而非 params.py）
SENSOR_BRACKET_W = 30.0    # mm — 板宽 (X)
SENSOR_BRACKET_H = 30.0    # mm — 板深 (Y)
SENSOR_BRACKET_T = PLATE_THICK  # mm — 板厚 8 mm
SENSOR_HOLE_DIA = 8.4      # mm — M8 接近开关压入 Φ8 + 0.4 间隙
M3_CLEARANCE = 3.4         # mm — M3 通孔 Φ3.4
M3_PITCH_Y = 10.0          # mm — 2 个 M3 孔在 ±Y 方向的间距 (中心到中心)


def make_p403() -> cq.Workplane:
    """SLP-403: 下限位传感器支架 — 6061-T6 铝板

    Envelope: 30 × 30 × 8 mm（Task 0 spec §6 真值，从 scaffold 50×40×25 修正）
    Weight: ~20g（铝板 30×30×8 × 2.7 g/cm³ ≈ 19.4 g）

    Axis: +Z 板法线方向（板厚方向）；安装时此面贴支撑条顶面，
          所以 assembly_layout 会做 +Z 平移 (不旋转)。
    Doc:  CAD_SPEC.md §6.2 step 16-18 + tmp/_custom_parts_spec.md §6
    """
    # ── 主板：30×30×8 mm，底面在 Z=0（centered=False on Z 与其他自制件一致）
    body = cq.Workplane("XY").box(
        SENSOR_BRACKET_W, SENSOR_BRACKET_H, SENSOR_BRACKET_T,
        centered=(True, True, False),
    )
    # ── 中心 Φ8.4 M8 接近开关孔（通孔）
    body = body.cut(
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, 0))
        .circle(SENSOR_HOLE_DIA / 2.0)
        .extrude(SENSOR_BRACKET_T)
    )
    # ── 2× Φ3.4 M3 安装孔，沿 ±Y 方向距中心 10 mm
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
    """Return expected bounding-box axis for orientation_check.py.

    扁平板件：principal_axis="z" + min_ratio=1.0 与 p100/p300/p400 完成件一致；
    orientation_check 对板类件 (XY 远大于 Z) 是宽容的。
    """
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §6.2 step 16 / Task 0 spec §6",
    }


def draw_p403_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-403."""
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p403()
    sheet = ThreeViewSheet(
        part_no="SLP-403",
        name="下限位传感器支架",
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
    r = make_p403()
    p = os.path.join(out, "SLP-403.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
