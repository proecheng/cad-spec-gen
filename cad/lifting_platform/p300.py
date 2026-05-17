"""动板 (SLP-300) — hand-completed 2026-05-13 (CP-1 Task 5b)

Material: 6061-T6 阳极氧化铝 (PLATE_THICK = 8 mm 统一)
Source-of-truth:
  - 板尺寸 150×100：draw_moving_plate.py:33 注释
  - 7 类孔（丝杠/LM10UU/T16 沉台/油管/电缆/M6 安装）：draw_moving_plate.py:50-69

坐标系：Local +Z = 板法线；assembly_layout 把局部 +Z 翻成全局 +Y (升降方向)
"""

import cadquery as cq
from params import *


def make_p300() -> cq.Workplane:
    """SLP-300: 动板 — 未指定

    Envelope: 150.0 x 100.0 x 8.0 mm  (CP-1 Task 5b hand-completed 2026-05-13)
    Weight: ~320g (150×100×8 × 2.7 g/cm³ × ~0.98 net)

    Axis: +Z 板法线（板厚方向）；assembly_layout 翻 90° 让 Y 轴成为竖直升降方向
    Doc:  CAD_SPEC.md §6.2 step 5-6 + draw_moving_plate.py 注释
    """
    # CP-1 Task 5b (hand-completed 2026-05-13)
    # 150×100×8 动板 + 7 类孔（参数自 params.py）：
    #   - 2×Φ22 丝杠螺母通孔 + 2×Φ32 沉台（嵌 T16 螺母法兰）at LS 对角
    #   - 2×Φ19H7 LM10UU 直线轴承孔 at GS 反对角
    #   - 1×Φ16 中心油管孔
    #   - 1×Φ10 电缆孔 at (+30, 0)
    #   - 4×Φ6.7 液压钳安装孔 at (±35, ±25)
    body = cq.Workplane("XY").box(
        MOV_PLATE_W, MOV_PLATE_H, PLATE_THICK,
        centered=(True, True, False))
    # 丝杠螺母通孔 + Φ32 沉台
    for _dx, _dy in [(-LS_X, LS_Y), (LS_X, -LS_Y)]:
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(_dx, _dy, 0))
            .circle(11.0).extrude(PLATE_THICK)
        )
        # Φ32 沉台从顶面 z=PLATE_THICK 向下 4mm
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(_dx, _dy, PLATE_THICK - 4.0))
            .circle(16.0).extrude(4.0)
        )
    # LM10UU 孔 Φ19H7
    for _dx, _dy in [(GS_X, GS_Y), (-GS_X, -GS_Y)]:
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(_dx, _dy, 0))
            .circle(9.5).extrude(PLATE_THICK)
        )
    # Φ16 中心油管孔
    body = body.cut(
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, 0))
        .circle(8.0).extrude(PLATE_THICK)
    )
    # Φ10 电缆孔
    body = body.cut(
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(30, 0, 0))
        .circle(5.0).extrude(PLATE_THICK)
    )
    # 4×Φ6.7 液压钳安装孔
    for _dx in (-35.0, 35.0):
        for _dy in (-25.0, 25.0):
            body = body.cut(
                cq.Workplane("XY")
                .transformed(offset=cq.Vector(_dx, _dy, 0))
                .circle(3.35).extrude(PLATE_THICK)
            )

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p300().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # Generated scaffold default; tighten when design-doc axis data is available.
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §5/§6.4 scaffold envelope",
    }


def draw_p300_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-300.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p300()
    sheet = ThreeViewSheet(
        part_no="SLP-300",
        name="动板",
        material="未指定",
        scale="1:1",
        weight_g=0,
        date=date.today().isoformat(),
        project_name="SLP",
        subsystem_name="丝杠式升降平台",
    )
    auto_three_view(solid, sheet)

    # GB/T 标注 — 数据来自 CAD_SPEC.md §2，不硬编码
    auto_annotate(solid, sheet, annotation_meta={
        "dim_tolerances": [{"fit_code": "", "label": "\u00b10.1 mm", "lower": "-0.1", "name": "POS_ACC", "nominal": "0.1", "upper": "+0.1"}, {"fit_code": "", "label": "\u00b10.05 mm", "lower": "-0.05", "name": "PARAM_L1204", "nominal": "0.05", "upper": "+0.05"}],
        "gdt": [],
        "surfaces": [{"material_type": "", "part": "\u52a8\u677f SLP-300", "process": "6061-T6 \u94dd", "ra": "Ra3.2"}],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_p300()
    p = os.path.join(out, "SLP-300.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
