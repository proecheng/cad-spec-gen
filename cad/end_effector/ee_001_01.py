"""
法兰本体（含十字悬臂） (GIS-EE-001-01)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 7075-T6铝合金

BOM: GIS-EE-001-01 法兰本体（含十字悬臂）

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


def make_ee_001_01() -> cq.Workplane:
    """GIS-EE-001-01: 法兰本体（含十字悬臂） — 7075-T6铝合金

    Envelope: 160.0 x 160.0 x 20.0 mm
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
    # 法兰 L2: OD=90.0mm ID=22.0mm T=30.0mm PCD=70.0mm×6孔
    body = (
        cq.Workplane('XY').circle(45.0).extrude(30.0)
        .cut(cq.Workplane('XY').circle(11.0).extrude(30.0))
    )
    # 顶面定位密封台阶
    _seat = (
        cq.Workplane('XY').transformed(offset=(0, 0, 30.0))
        .circle(41.2).extrude(2.0)
        .cut(cq.Workplane('XY').transformed(offset=(0, 0, 30.0))
             .circle(38.8).extrude(2.0))
    )
    body = body.union(_seat)
    # 通孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(35.0, 0.0, 0))
        .circle(2.8).extrude(32.0)
    )
    # 沉孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(35.0, 0.0, 25.5))
        .circle(5.04).extrude(6.5)
    )
    # 通孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(17.5, 30.3109, 0))
        .circle(2.8).extrude(32.0)
    )
    # 沉孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(17.5, 30.3109, 25.5))
        .circle(5.04).extrude(6.5)
    )
    # 通孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(-17.5, 30.3109, 0))
        .circle(2.8).extrude(32.0)
    )
    # 沉孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(-17.5, 30.3109, 25.5))
        .circle(5.04).extrude(6.5)
    )
    # 通孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(-35.0, 0.0, 0))
        .circle(2.8).extrude(32.0)
    )
    # 沉孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(-35.0, 0.0, 25.5))
        .circle(5.04).extrude(6.5)
    )
    # 通孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(-17.5, -30.3109, 0))
        .circle(2.8).extrude(32.0)
    )
    # 沉孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(-17.5, -30.3109, 25.5))
        .circle(5.04).extrude(6.5)
    )
    # 通孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(17.5, -30.3109, 0))
        .circle(2.8).extrude(32.0)
    )
    # 沉孔
    body = body.cut(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(17.5, -30.3109, 25.5))
        .circle(5.04).extrude(6.5)
    )

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_ee_001_01().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # Generated scaffold default; tighten when design-doc axis data is available
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §5/§6.4 scaffold envelope",
    }


def draw_ee_001_01_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-001-01.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_ee_001_01()
    sheet = ThreeViewSheet(
        part_no="GIS-EE-001-01",
        name="法兰本体（含十字悬臂）",
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
        "dim_tolerances": [{"fit_code": "", "label": "\u00b1135\u00b0", "lower": "-135", "name": "ROT_RANGE", "nominal": "135", "upper": "+135"}, {"fit_code": "", "label": "\u00b10.1mm", "lower": "-0.1", "name": "FLANGE_DIA", "nominal": "90", "upper": "+0.1"}, {"fit_code": "", "label": "\u00b10.5mm", "lower": "-0.5", "name": "FLANGE_THICK", "nominal": "30", "upper": "+0.5"}, {"fit_code": "", "label": "\u00b10.1mm", "lower": "-0.1", "name": "FLANGE_BODY_OD", "nominal": "90", "upper": "+0.1"}, {"fit_code": "", "label": "+0.021/0mm", "lower": "0", "name": "FLANGE_BODY_ID", "nominal": "22", "upper": "+0.021"}, {"fit_code": "", "label": "\u00b10.5mm", "lower": "-0.5", "name": "FLANGE_AL_THICK", "nominal": "25", "upper": "+0.5"}, {"fit_code": "", "label": "\u00b10.5mm", "lower": "-0.5", "name": "FLANGE_TOTAL_THICK", "nominal": "30", "upper": "+0.5"}, {"fit_code": "", "label": "\u00b10.2mm", "lower": "-0.2", "name": "ARM_SEC_W", "nominal": "12", "upper": "+0.2"}, {"fit_code": "", "label": "\u00b10.2mm", "lower": "-0.2", "name": "ARM_SEC_THICK", "nominal": "8", "upper": "+0.2"}, {"fit_code": "", "label": "\u00b10.3mm", "lower": "-0.3", "name": "ARM_L_2", "nominal": "40", "upper": "+0.3"}, {"fit_code": "", "label": "\u00b10.2mm", "lower": "-0.2", "name": "FLANGE_BOLT_PCD", "nominal": "70", "upper": "+0.2"}],
        "gdt": [],
        "surfaces": [],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_001_01()
    p = os.path.join(out, "GIS-EE-001-01.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
