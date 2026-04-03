"""
壳体（含散热鳍片） (GIS-EE-006-01)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 6063铝合金 140×100×55mm

BOM: GIS-EE-006-01 壳体（含散热鳍片）

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


def make_ee_006_01() -> cq.Workplane:
    """GIS-EE-006-01: 壳体（含散热鳍片） — 6063铝合金 140×100×55mm

    Envelope: 140.0 x 100.0 x 55.0 mm
    Weight: ?g

    Axis: TODO — must match COORDINATE SYSTEM block above
    Doc:  TODO — cite design doc section + line
    """
    # ── Geometry source: CAD_SPEC.md §5 BOM ─────────────────────────────────────
    # Principal axis: TODO
    # If this part needs a non-Z extrusion direction, document WHY here.
    #
    # NOTE: Approximate geometry from BOM dimensions / part-name heuristics.
    #       Refine with actual geometry citing design-doc lines.
    body = cq.Workplane("XY").box(
        140.0, 100.0, 55.0,
        centered=(True, True, False))  # § refine with real geometry

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_ee_006_01().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # TODO: fill after geometry is implemented
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "TODO",
    }


def draw_ee_006_01_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-006-01.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_ee_006_01()
    sheet = ThreeViewSheet(
        part_no="GIS-EE-006-01",
        name="壳体（含散热鳍片）",
        material="6063铝合金 140×100×55mm",
        scale="1:1",
        weight_g=0,
        date=date.today().isoformat(),
        project_name="GIS-EE",
        subsystem_name="末端执行机构",
    )
    auto_three_view(solid, sheet)

    # GB/T 标注 — 数据来自 CAD_SPEC.md §2，不硬编码
    auto_annotate(solid, sheet, annotation_meta={
        "dim_tolerances": [{"fit_code": "", "label": "\u00b1135\u00b0", "lower": "-135", "name": "ROT_RANGE", "nominal": "135", "upper": "+135"}, {"fit_code": "", "label": "\u00b10.1mm", "lower": "-0.1", "name": "FLANGE_DIA", "nominal": "90", "upper": "+0.1"}, {"fit_code": "", "label": "\u00b10.5mm", "lower": "-0.5", "name": "FLANGE_THICK", "nominal": "30", "upper": "+0.5"}, {"fit_code": "", "label": "\u00b10.1mm", "lower": "-0.1", "name": "FLANGE_BODY_OD", "nominal": "90", "upper": "+0.1"}, {"fit_code": "", "label": "+0.021/0mm", "lower": "0", "name": "FLANGE_BODY_ID", "nominal": "22", "upper": "+0.021"}, {"fit_code": "", "label": "\u00b10.5mm", "lower": "-0.5", "name": "FLANGE_AL_THICK", "nominal": "25", "upper": "+0.5"}, {"fit_code": "", "label": "\u00b10.5mm", "lower": "-0.5", "name": "FLANGE_TOTAL_THICK", "nominal": "30", "upper": "+0.5"}, {"fit_code": "", "label": "\u00b10.2mm", "lower": "-0.2", "name": "ARM_SEC_W", "nominal": "12", "upper": "+0.2"}, {"fit_code": "", "label": "\u00b10.2mm", "lower": "-0.2", "name": "ARM_SEC_THICK", "nominal": "8", "upper": "+0.2"}, {"fit_code": "", "label": "\u00b10.3mm", "lower": "-0.3", "name": "ARM_L_2", "nominal": "40", "upper": "+0.3"}, {"fit_code": "", "label": "+0.012/0mm", "lower": "0", "name": "SPRING_PIN_BORE", "nominal": "4", "upper": "+0.012"}, {"fit_code": "", "label": "\u00b10.2mm", "lower": "-0.2", "name": "FLANGE_BOLT_PCD", "nominal": "70", "upper": "+0.2"}],
        "gdt": [],
        "surfaces": [],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_006_01()
    p = os.path.join(out, "GIS-EE-006-01.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
