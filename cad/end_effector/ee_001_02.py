"""
PEEK绝缘段 (GIS-EE-001-02)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: PEEK

BOM: GIS-EE-001-02 PEEK绝缘段

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


def make_ee_001_02() -> cq.Workplane:
    """GIS-EE-001-02: PEEK绝缘段 — PEEK

    Envelope: 80.0 x 80.0 x 5.0 mm
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
    body = (cq.Workplane("XY")
            .circle(80.0 / 2).extrude(5.0)
            .faces(">Z").workplane()
            .circle(60.0 / 2).cutThruAll())

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_ee_001_02().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # Generated scaffold default; tighten when design-doc axis data is available
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §5/§6.4 scaffold envelope",
    }


def draw_ee_001_02_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-001-02.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_ee_001_02()
    sheet = ThreeViewSheet(
        part_no="GIS-EE-001-02",
        name="PEEK绝缘段",
        material="PEEK",
        scale="1:1",
        weight_g=0,
        date=date.today().isoformat(),
        project_name="GIS-EE",
        subsystem_name="末端执行机构",
    )
    auto_three_view(solid, sheet)

    # GB/T 标注 — 数据来自 CAD_SPEC.md §2，不硬编码
    auto_annotate(solid, sheet, annotation_meta={
        "dim_tolerances": [{"fit_code": "", "label": "\u00b1135\u00b0", "lower": "-135", "name": "ROT_RANGE", "nominal": "135", "upper": "+135"}],
        "gdt": [],
        "surfaces": [],
    })

    return sheet.save(output_dir, material_type="peek")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_001_02()
    p = os.path.join(out, "GIS-EE-001-02.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
