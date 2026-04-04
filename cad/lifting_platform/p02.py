"""
导向轴 L296 (SLP-P02)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-P02 导向轴 L296

┌─ COORDINATE SYSTEM ───────────────────────────────────────────────────────┐
│ Local origin : Shaft centerline at XY origin, bottom tip at Z=0          │
│ Principal axis: Cylinder along +Z, total height 296mm                    │
│ Assembly orient: Bottom tip at Z=−12, top at Z=+284                      │
│                  GS1 at (+60, +30), GS2 at (−60, −30)                    │
│ Design doc ref : §5.2 导向轴 — φ10h6 × 296mm                            │
└──────────────────────────────────────────────────────────────────────────┘
"""

import cadquery as cq
from params import *


def make_p02() -> cq.Workplane:
    """SLP-P02: 导向轴 L296 — Guide shaft (x2)

    Simple cylinder: phi10 x 296mm, GCr15 bearing steel

    Doc:  §5.2 导向轴 — φ10h6 × 296mm
          Z range in assembly: −12 to +284 (total 296mm)
    """
    # ── Geometry: phi10 × 296mm cylinder along Z ──────────────────────────────
    # §5.2: φ10h6 光轴 GCr15, length 296mm
    # Local origin at shaft center, bottom at Z=0
    body = cq.Workplane("XY").circle(5.0).extrude(296.0)

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p02().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    return {
        "principal_axis": "z",
        "min_ratio": 20.0,
        "doc_ref": "§5.2 导向轴 φ10 L296",
    }


def draw_p02_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-P02.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p02()
    sheet = ThreeViewSheet(
        part_no="SLP-P02",
        name="导向轴 L296",
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
    r = make_p02()
    p = os.path.join(out, "SLP-P02.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
