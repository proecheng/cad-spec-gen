"""
清洁模块壳体 (GIS-EE-004-01)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 7075-T6铝合金

BOM: GIS-EE-004-01 清洁模块壳体

┌─ COORDINATE SYSTEM (MUST fill before coding geometry) ──────────────────┐
│ Local origin : TODO: e.g. bottom-left corner of mounting face
│ Principal axis: TODO: e.g. extrude along +Z (axial), body height = PARAM_H
│ Assembly orient: TODO: e.g. rotate X+90deg in assembly.py so axis becomes +Y (radial)
│ Design doc ref : TODO: e.g. §4.1.2 L176 — "储罐轴线与悬臂共线（径向）"
└──────────────────────────────────────────────────────────────────────────┘

DO NOT extrude / rotate based on assumption. Every axis choice must cite
a design-doc line above. If the doc is ambiguous, raise a DESIGN QUESTION
before writing geometry.
"""

import cadquery as cq
from params import *


def make_ee_004_01() -> cq.Workplane:
    """GIS-EE-004-01: 清洁模块壳体 — 7075-T6铝合金

    Envelope: 50.0 x 40.0 x 60.0 mm
    Weight: ?g

    Axis: TODO — must match COORDINATE SYSTEM block above
    Doc:  TODO — cite design doc section + line
    """
    # ── Geometry source: CAD_SPEC.md §5 BOM ─────────────────────────────────────
    # Principal axis: TODO
    # If this part needs a non-Z extrusion direction, document WHY here.
    #
    # TODO: Replace placeholder box with actual geometry.
    #       Each .extrude() / .circle() / .box() call must reference the
    #       param name whose value comes from the design doc (see params.py).
    body = cq.Workplane("XY").box(
        50.0, 40.0, 60.0,
        centered=(True, True, False))  # § replace with real geometry

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_ee_004_01().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # TODO: fill after geometry is implemented
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "TODO",
    }


def draw_ee_004_01_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-004-01.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_ee_004_01()
    sheet = ThreeViewSheet(
        part_no="GIS-EE-004-01",
        name="清洁模块壳体",
        material="7075-T6铝合金",
        scale="1:1",
        weight_g=0,
        date=date.today().isoformat(),
        project_name="GIS-EE",
        subsystem_name="末端执行机构",
    )
    auto_three_view(solid, sheet)

    # GB/T 标注 — 数据来自 CAD_SPEC.md §2，不硬编码
    auto_annotate(solid, sheet, annotation_meta={
        "dim_tolerances": [],
        "gdt": [],
        "surfaces": [{"material_type": "", "part": "\u6e05\u6d01\u6a21\u5757\u58f3\u4f53", "process": "7075-T6\u94dd\u5408\u91d1", "ra": "Ra3.2"}],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_004_01()
    p = os.path.join(out, "GIS-EE-004-01.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
