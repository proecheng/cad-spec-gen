"""
丝杠 L350 (SLP-P01)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-P01 丝杠 L350

┌─ COORDINATE SYSTEM ───────────────────────────────────────────────────────┐
│ Local origin : Shaft centerline at XY origin, bottom tip at Z=0          │
│ Principal axis: Cylinder along +Z, total height 350mm                    │
│ Assembly orient: Bottom tip at Z=−48, top at Z=+302                      │
│                  LS1 at (−60, +30), LS2 at (+60, −30)                    │
│ Design doc ref : §5.1 丝杠 — Tr16×4, 350mm total                        │
└──────────────────────────────────────────────────────────────────────────┘
"""

import cadquery as cq
from params import *


def make_p01() -> cq.Workplane:
    """SLP-P01: 丝杠 L350 — Lead screw Tr16x4 (x2)

    Simplified as stepped cylinder (no thread detail):
      Upper shaft: phi12 x 40mm
      Upper transition: 5mm
      Thread body: phi16 x 230mm
      Lower transition: 5mm
      Lower shaft: phi12 x 70mm
    Total: 350mm

    Doc:  §5.1 丝杠 — Tr16×4, 45# steel, total length 350mm
    """
    # ── Geometry: Stepped cylinder along Z ────────────────────────────────────
    # §5.1 Z segments (from bottom up, local coords):
    #   Lower shaft:      phi12 × 70mm   (Z=0 to Z=70)
    #   Lower transition: phi16 × 5mm    (Z=70 to Z=75)  — simplified as phi16
    #   Thread body:      phi16 × 230mm  (Z=75 to Z=305)
    #   Upper transition: phi16 × 5mm    (Z=305 to Z=310) — simplified as phi16
    #   Upper shaft:      phi12 × 40mm   (Z=310 to Z=350)

    # Lower shaft phi12
    lower_shaft = cq.Workplane("XY").circle(6.0).extrude(70.0)

    # Thread body + transitions phi16 (combined 5+230+5 = 240mm)
    thread_body = (cq.Workplane("XY")
                   .transformed(offset=(0, 0, 70.0))
                   .circle(8.0).extrude(240.0))

    # Upper shaft phi12
    upper_shaft = (cq.Workplane("XY")
                   .transformed(offset=(0, 0, 310.0))
                   .circle(6.0).extrude(40.0))

    body = lower_shaft.union(thread_body).union(upper_shaft)
    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p01().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    return {
        "principal_axis": "z",
        "min_ratio": 10.0,
        "doc_ref": "§5.1 丝杠 Tr16×4 L350",
    }


def draw_p01_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-P01.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p01()
    sheet = ThreeViewSheet(
        part_no="SLP-P01",
        name="丝杠 L350",
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
    r = make_p01()
    p = os.path.join(out, "SLP-P01.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
