"""电机支架 (SLP-400) — hand-completed 2026-05-13 (CP-1 Task 5d)

Material: 6061-T6 阳极氧化铝 (PLATE_THICK = 8 mm 统一)
Source-of-truth:
  - 板尺寸 70×90：draw_motor_bracket.py:33 注释
  - 中心 Φ28 + NEMA23 4×Φ5.5 PCD 47.14 (45°/135°/225°/315°)：draw_motor_bracket.py:21,48,53-58

坐标系：Local +Z = 板法线（NEMA23 贴这面）；assembly 平移到右支撑条底部
"""

import math

import cadquery as cq
from params import *


def make_p400() -> cq.Workplane:
    """SLP-400: 电机支架 — 未指定

    Envelope: 70.0 x 90.0 x 8.0 mm  (CP-1 Task 5d hand-completed 2026-05-13)
    Weight: ~135g (70×90×8 × 2.7 g/cm³ × ~0.89 net，减电机轴孔 Φ28 + 4 NEMA23 孔)

    Axis: +Z 板法线；NEMA23 电机贴这面安装
    Doc:  CAD_SPEC.md §6.2 step 10 + draw_motor_bracket.py 注释 (_NEMA_PCD=47.14)
    """
    # CP-1 Task 5d (hand-completed 2026-05-13)
    # 70×90×8 电机支架板 + NEMA23 标准孔阵：
    #   - 中心 Φ28 电机轴定位孔
    #   - 4×Φ5.5 M5 安装孔 PCD 47.14 mm，角度 45°/135°/225°/315°
    body = cq.Workplane("XY").box(
        BRACKET_W, BRACKET_H, PLATE_THICK,
        centered=(True, True, False))
    # 中心 Φ28 电机轴孔
    body = body.cut(
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, 0))
        .circle(BRACKET_CENTER_HOLE / 2.0).extrude(PLATE_THICK)
    )
    # 4×Φ5.5 NEMA23 安装孔 PCD 47.14
    _NEMA_PCD = 47.14
    _PCD_R = _NEMA_PCD / 2.0
    for _ang_deg in (45.0, 135.0, 225.0, 315.0):
        _rad = math.radians(_ang_deg)
        _hx = _PCD_R * math.cos(_rad)
        _hy = _PCD_R * math.sin(_rad)
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(_hx, _hy, 0))
            .circle(2.75).extrude(PLATE_THICK)
        )

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p400().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # Generated scaffold default; tighten when design-doc axis data is available.
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §5/§6.4 scaffold envelope",
    }


def draw_p400_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-400.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p400()
    sheet = ThreeViewSheet(
        part_no="SLP-400",
        name="电机支架",
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
        "surfaces": [{"material_type": "", "part": "\u7535\u673a\u652f\u67b6 SLP-400", "process": "6061-T6 \u94dd", "ra": "Ra3.2"}],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_p400()
    p = os.path.join(out, "SLP-400.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
