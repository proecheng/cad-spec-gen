"""
下限位传感器支架 (SLP-403)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-403 下限位传感器支架

┌─ COORDINATE SYSTEM ───────────────────────────────────────────────────────┐
│ Local origin : Center of horizontal foot XY, bottom face at Z=0          │
│ Principal axis: L-shape — foot on XY, vertical arm rises along +Z        │
│ Assembly orient: Foot at Z=0 (left support bar top), arm rises to Z=+43  │
│                  Center at (−80, 0) in global coords                     │
│ Design doc ref : §9.2 下限位支架 — L型, 壁厚5mm, foot 25×20, arm 43mm   │
└──────────────────────────────────────────────────────────────────────────┘
"""

import cadquery as cq
from params import *


def make_p403() -> cq.Workplane:
    """SLP-403: 下限位传感器支架 — Lower limit sensor bracket

    L-shaped, 5mm wall thickness, 6061-T6 aluminum
    Horizontal foot: 25(X) × 20(Y) mm, mounted on left support bar top face
    Vertical arm: 5(X) × 20(Y) × 43(Z) mm, rising from −X edge

    Doc:  §9.2 传感器支架 — SLP-403
          Mounts at left support bar top face (Z=0), sensor at Z=+43
    """
    # ── Geometry: L-shaped bracket ────────────────────────────────────────────
    # §9.2: L型折弯, 壁厚 5mm
    #   Horizontal foot: 25(X) × 20(Y) × 5(Z) — lies flat on support bar
    #   Vertical arm:    5(X) × 20(Y) × 43(Z) — rises from −X edge
    # Local origin at foot bottom-center, Z=0 at mounting face
    t = 5.0   # wall thickness

    # Horizontal foot: 25 × 20 × 5, centered in XY, bottom at Z=0
    foot = cq.Workplane("XY").box(
        25.0, 20.0, t,
        centered=(True, True, False))

    # Vertical arm: 5 × 20 × 43, at −X edge of foot, bottom at Z=0
    # Foot X range = [-12.5, +12.5]; arm at X = [-12.5, -7.5]
    arm = (cq.Workplane("XY")
           .transformed(offset=(-10.0, 0, 0))
           .box(t, 20.0, 43.0,
                centered=(True, True, False)))

    body = foot.union(arm)
    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p403().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "§9.2 下限位支架 L型 25×20 foot + 43mm arm",
    }


def draw_p403_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-403.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p403()
    sheet = ThreeViewSheet(
        part_no="SLP-403",
        name="下限位传感器支架",
        material="",
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
