"""
右支撑条 (SLP-201)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-201 右支撑条

┌─ COORDINATE SYSTEM ───────────────────────────────────────────────────────┐
│ Local origin : Center of bar XY, bottom face at Z=0                      │
│ Principal axis: Bar on XY, height extruded along +Z (15mm)               │
│ Assembly orient: Translate to center X=+60, Z=−8 in assembly.py          │
│ Design doc ref : §3.2 右支撑条 — 40×260×15 mm (mirror of SLP-200)        │
└──────────────────────────────────────────────────────────────────────────┘
"""

import cadquery as cq
from params import *


def make_p201() -> cq.Workplane:
    """SLP-201: 右支撑条 — Right support bar (mirror of SLP-200)

    Envelope: 40 x 260 x 15 mm (§10.3 visual table)
    Weight: ~421g (6061-T6, 2.70 g/cm³)

    Axis: Bar standing upright — 40(X) × 260(Y) × 15(Z)
    Doc:  §3.2 右支撑条, §10.3 视觉标识表 — 40×260×15 mm
          Mirror of SLP-200 about YZ plane
    """
    # ── Geometry: 40(X) × 260(Y) × 15(Z) rectangular bar ─────────────────────
    # In assembly: centered at X=+60, Z range [−8, 0] per §3.2
    # Same shape as SLP-200 (mirror), identical local geometry
    # Local origin at bar center XY, bottom face at Z=0
    body = cq.Workplane("XY").box(
        40.0, 260.0, 15.0,
        centered=(True, True, False))

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p201().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "§3.2 右支撑条 40×260×15",
    }


def draw_p201_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-201.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p201()
    sheet = ThreeViewSheet(
        part_no="SLP-201",
        name="右支撑条",
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
        "surfaces": [{"material_type": "", "part": "\u53f3\u652f\u6491\u6761 SLP-201", "process": "6061-T6 \u94dd", "ra": "Ra3.2"}],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_p201()
    p = os.path.join(out, "SLP-201.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
