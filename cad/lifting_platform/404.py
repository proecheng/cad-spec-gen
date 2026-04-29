"""
上限位传感器支架 (SLP-404)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-404 上限位传感器支架

┌─ COORDINATE SYSTEM (generated scaffold defaults) ──────────────────┐
│ Local origin : CAD_SPEC envelope center on XY; bottom face at Z=0
│ Principal axis: +Z scaffold extrusion axis; body height from envelope
│ Assembly orient: assembly.py applies §6.2/§6.3 placement transforms
│ Design doc ref : CAD_SPEC.md §5 BOM + §6.4 envelope
└──────────────────────────────────────────────────────────────────────────┘

DO NOT extrude / rotate based on assumption. Every axis choice must cite
a design-doc line above. If the doc is ambiguous, raise a DESIGN QUESTION
before writing geometry.
"""

import cadquery as cq
from params import *


def make_404() -> cq.Workplane:
    """SLP-404: 上限位传感器支架 — 

    Envelope: 50.0 x 40.0 x 25.0 mm
    Weight: ?g

    Axis: +Z scaffold default; verify against §6.3 before production use
    Doc:  CAD_SPEC.md §5 BOM / §6.4 envelope
    """
    # ── Geometry source: CAD_SPEC.md §5 BOM ─────────────────────────────────────
    # Principal axis: +Z scaffold default
    # If this part needs a non-Z extrusion direction, document WHY here.
    #
    # NOTE: Approximate geometry from BOM dimensions / part-name heuristics.
    #       Refine with actual geometry citing design-doc lines.
    body = cq.Workplane("XY").box(
        50.0, 40.0, 25.0,
        centered=(True, True, False))  # § refine with real geometry

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_404().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # Generated scaffold default; tighten when design-doc axis data is available
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §5/§6.4 scaffold envelope",
    }


def draw_404_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-404.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_404()
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
    r = make_404()
    p = os.path.join(out, "SLP-404.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
