"""
上限位传感器支架 (SLP-404)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-404 上限位传感器支架

┌─ COORDINATE SYSTEM ───────────────────────────────────────────────────────┐
│ Local origin : Center of horizontal foot XY, top face at Z=0             │
│ Principal axis: Inverted L — foot on XY (top), arm hangs along −Z        │
│ Assembly orient: Foot top at Z=+272 (top plate bottom), arm down to +240 │
│                  Center at (−80, 0) in global coords                     │
│ Design doc ref : §9.2 上限位支架 — 倒L型, 壁厚5mm, foot 25×20, arm 32mm │
└──────────────────────────────────────────────────────────────────────────┘
"""

import cadquery as cq
from params import *


def make_p404() -> cq.Workplane:
    """SLP-404: 上限位传感器支架 — Upper limit sensor bracket

    Inverted L-shaped, 5mm wall thickness, 6061-T6 aluminum
    Horizontal top foot: 25(X) × 20(Y) mm, mounted on top plate bottom face
    Vertical arm: 5(X) × 20(Y) × 32(Z) mm, hanging from −X edge

    Doc:  §9.2 传感器支架 — SLP-404
          Mounts at top plate bottom face (Z=+272), sensor at Z=+240
    """
    # ── Geometry: Inverted L-shaped bracket ───────────────────────────────────
    # §9.2: 倒L型, 壁厚 5mm
    #   Horizontal top foot: 25(X) × 20(Y) × 5(Z) — bolted to top plate bottom
    #   Vertical arm:        5(X) × 20(Y) × 32(Z) — hangs down from −X edge
    # Local origin at foot top-center, Z=0 at mounting face (top of foot)
    # Foot extends downward from Z=0 to Z=−5
    # Arm extends downward from Z=0 to Z=−32
    t = 5.0   # wall thickness

    # Horizontal foot: 25 × 20 × 5, centered in XY, top at Z=0
    foot = (cq.Workplane("XY")
            .transformed(offset=(0, 0, -t))
            .box(25.0, 20.0, t,
                 centered=(True, True, False)))

    # Vertical arm: 5 × 20 × 32, at −X edge, extends down from Z=0
    # Foot X range = [-12.5, +12.5]; arm at X = [-12.5, -7.5]
    arm = (cq.Workplane("XY")
           .transformed(offset=(-10.0, 0, -32.0))
           .box(t, 20.0, 32.0,
                centered=(True, True, False)))

    body = foot.union(arm)
    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p404().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "§9.2 上限位支架 倒L型 25×20 foot + 32mm arm",
    }


def draw_p404_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-404.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p404()
    sheet = ThreeViewSheet(
        part_no="SLP-404",
        name="上限位传感器支架",
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
    r = make_p404()
    p = os.path.join(out, "SLP-404.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
