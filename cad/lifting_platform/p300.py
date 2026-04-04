"""
动板 (SLP-300)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-300 动板

┌─ COORDINATE SYSTEM ───────────────────────────────────────────────────────┐
│ Local origin : Center of plate XY, bottom face at Z=0                    │
│ Principal axis: Flat plate on XY, thickness extruded along +Z (8mm)      │
│ Assembly orient: Translate to Z=board_bottom (variable, +43~+235)        │
│ Design doc ref : §4 动板 — 160×120×8 mm, travels Z=+43 to Z=+235        │
└──────────────────────────────────────────────────────────────────────────┘
"""

import cadquery as cq
from params import *


def make_p300() -> cq.Workplane:
    """SLP-300: 动板 — Moving plate (elevator platform)

    Envelope: 160 x 120 x 8 mm (§10.3 visual table)
    Weight: ~415g (6061-T6, 2.70 g/cm³)

    Axis: Flat plate on XY, thickness along +Z
    Doc:  §4 动板, §10.3 视觉标识表 — 160×120×8 mm
          §4: 150×100×8 in spec text, §10.3 revised to 160×120×8
    """
    # ── Geometry: 160(X) × 120(Y) × 8(Z) flat plate ──────────────────────────
    # §4: Slides vertically on screws/guide shafts
    # §4: Board bottom travels Z=+43 ~ +235 (effective stroke 192mm)
    # Local origin at plate center XY, bottom face at Z=0
    body = cq.Workplane("XY").box(
        160.0, 120.0, 8.0,
        centered=(True, True, False))

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p300().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "§4 动板 160×120×8",
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
