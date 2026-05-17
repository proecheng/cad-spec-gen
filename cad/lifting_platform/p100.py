"""上固定板 (SLP-100) — hand-completed 2026-05-13 (CP-1 Task 5a)

Material: 6061-T6 阳极氧化铝 (PLATE_THICK = 8 mm 统一)
Source-of-truth:
  - 板尺寸 200×100：draw_top_plate.py:42 注释
  - 孔位 LS / GS / 机器人 M5 (diagonal pattern): draw_top_plate.py:60-71

坐标系：Local +Z = 板法线 (板厚方向)；assembly_layout 把局部 +Z 翻成全局 +Y (升降方向)
"""

import cadquery as cq
from params import *


def make_p100() -> cq.Workplane:
    """SLP-100: 上固定板 — 未指定

    Envelope: 200.0 x 100.0 x 8.0 mm  (CP-1 Task 5a hand-completed 2026-05-13)
    Weight: ~430g (200×100×8 × 2.7 g/cm³ × ~0.99 net)

    Axis: +Z 板法线（板厚方向）；assembly_layout 翻 90° 让 Y 轴成为竖直升降方向
    Doc:  CAD_SPEC.md §6.2 step 7-8 + draw_top_plate.py 注释
    """
    # CP-1 Task 5a (hand-completed 2026-05-13)
    # 200×100×8 板 + 4 类孔（参数自 params.py）：
    #   - 2×Φ24 丝杠通孔 at (-LS_X, +LS_Y), (+LS_X, -LS_Y) 对角
    #   - 2×Φ10 H7 导向轴孔 at (+GS_X, +GS_Y), (-GS_X, -GS_Y) 反对角
    #   - 4×Φ5.5 机器人接口孔 at (±80, ±35)
    body = cq.Workplane("XY").box(
        TOP_PLATE_W, TOP_PLATE_H, PLATE_THICK,
        centered=(True, True, False))
    # 丝杠通孔（对角）
    for _dx, _dy in [(-LS_X, LS_Y), (LS_X, -LS_Y)]:
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(_dx, _dy, 0))
            .circle(12.0).extrude(PLATE_THICK)
        )
    # 导向轴孔 Φ10H7（异对角）
    for _dx, _dy in [(GS_X, GS_Y), (-GS_X, -GS_Y)]:
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(_dx, _dy, 0))
            .circle(5.0).extrude(PLATE_THICK)
        )
    # 4×M5 机器人接口孔 (Φ5.5)
    for _dx in (-80.0, 80.0):
        for _dy in (-35.0, 35.0):
            body = body.cut(
                cq.Workplane("XY")
                .transformed(offset=cq.Vector(_dx, _dy, 0))
                .circle(2.75).extrude(PLATE_THICK)
            )

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p100().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # Generated scaffold default; tighten when design-doc axis data is available.
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §5/§6.4 scaffold envelope",
    }


def draw_p100_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-100.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p100()
    sheet = ThreeViewSheet(
        part_no="SLP-100",
        name="上固定板",
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
        "surfaces": [{"material_type": "", "part": "\u4e0a\u56fa\u5b9a\u677f SLP-100", "process": "6061-T6 \u94dd", "ra": "Ra3.2"}],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_p100()
    p = os.path.join(out, "SLP-100.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
