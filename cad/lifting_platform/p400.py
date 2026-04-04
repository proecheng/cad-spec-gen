"""
电机支架 (SLP-400)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-400 电机支架

┌─ COORDINATE SYSTEM ───────────────────────────────────────────────────────┐
│ Local origin : Center of plate XY, bottom face at Z=0                    │
│ Principal axis: Flat plate on XY, thickness extruded along +Z (8mm)      │
│ Assembly orient: Top face at Z=−8 (right support bar bottom), center     │
│                  at (+60, −30) in global coords                          │
│ Design doc ref : §8.2 电机支架 — 70(X) × 90(Y) × 8mm                    │
└──────────────────────────────────────────────────────────────────────────┘
"""

import cadquery as cq
from params import *


def make_p400() -> cq.Workplane:
    """SLP-400: 电机支架 — Motor bracket

    Envelope: 70(X) x 90(Y) x 8(Z) mm (§8.2)
    Weight: ~136g (6061-T6, 2.70 g/cm³)

    Axis: Flat plate on XY, thickness along +Z (hangs below support bar)
    Doc:  §8.2 电机支架 — 90(Y) × 70(X) × 8mm, center (+60, −30)
          Cantilevered from right support bar bottom face
    """
    # ── Geometry: 70(X) × 90(Y) × 8(Z) flat bracket plate ────────────────────
    # §8.2: "90(Y) × 70(X) × 8mm 6061-T6"
    # In assembly: top face at Z=−8 (support bar bottom), extends to Z=−16
    # Local origin at plate center XY, bottom face at Z=0
    body = cq.Workplane("XY").box(
        70.0, 90.0, 8.0,
        centered=(True, True, False))

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p400().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "§8.2 电机支架 70×90×8",
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
