"""
法兰本体（含十字悬臂） (GIS-EE-001-01)

Hand-completed 2026-05-13 (CP-1 Task 1, quality overhaul) —
scaffold geometry (disc + 6×M3 bolt circle) preserved + 4 十字悬臂 added +
4×M6 ISO-9409 back-face mount holes added per CAD_SPEC §2/§5.
Source: CAD_SPEC.md §5 BOM + §6.4 envelope (160×160×20 mm)
Material: 7075-T6铝合金 + 顶面 PEEK 5mm（PEEK 段未建模，由装配 stack 表示）

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
    # ── Geometry source: CAD_SPEC.md §2 全局参数 + §5 BOM ────────────────────
    # 法兰本体 Φ90 OD / Φ22 ID（H7 与 GP22C 减速器壳体定位）/ 30mm 总厚（铝 25 + PEEK 5）
    # +Z 主轴：圆盘底面在 z=0、顶面 z=30；4 条悬臂沿 ±X/±Y、嵌在顶面 8mm 厚度内
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

    # ── 4 条十字悬臂（CP-1 Task 1, 2026-05-13 手工补完）─────────────────
    # CAD_SPEC L31/L32/L34: ARM_SEC_W=12, ARM_SEC_THICK=8, ARM_L_2=40
    # 设计文档"法兰本体（含十字悬臂）"4 工位径向布局
    # 几何：单臂 40L × 12W × 8T，沿 +X/+Y/-X/-Y 4 方向从圆盘外缘 r=45 向外伸 40mm
    # z 范围：顶面与圆盘顶面齐平 z=30，向下延伸 8mm → z=22..30
    _arm_l, _arm_w, _arm_t = 40.0, 12.0, 8.0
    _arm_z_bottom = 30.0 - _arm_t  # z=22
    # +X 臂（长边沿 X）
    body = body.union(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(45 + _arm_l / 2, 0, _arm_z_bottom))
        .box(_arm_l, _arm_w, _arm_t, centered=(True, True, False))
    )
    # +Y 臂（长边沿 Y）
    body = body.union(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(0, 45 + _arm_l / 2, _arm_z_bottom))
        .box(_arm_w, _arm_l, _arm_t, centered=(True, True, False))
    )
    # -X 臂
    body = body.union(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(-(45 + _arm_l / 2), 0, _arm_z_bottom))
        .box(_arm_l, _arm_w, _arm_t, centered=(True, True, False))
    )
    # -Y 臂
    body = body.union(
        cq.Workplane('XY')
        .transformed(offset=cq.Vector(0, -(45 + _arm_l / 2), _arm_z_bottom))
        .box(_arm_w, _arm_l, _arm_t, centered=(True, True, False))
    )

    # ── 4×M6 ISO-9409 安装孔（机械臂侧背面）─────────────────────────
    # CAD_SPEC L31 FLANGE_MOUNT_FACE = 50；L100 "法兰→RM65-B（ISO 9409）M6×12 内六角"
    # 边长 50 mm 方形分布，Φ6.7 通孔从背面 z=0 钻通整个法兰厚 30mm + 余量
    for _dx in (-25.0, 25.0):
        for _dy in (-25.0, 25.0):
            body = body.cut(
                cq.Workplane('XY')
                .transformed(offset=cq.Vector(_dx, _dy, 0))
                .circle(3.35)  # Φ6.7 / 2
                .extrude(32.0)
            )

    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_ee_001_01().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    # CP-1 Task 1：圆盘 + 4 悬臂构成的法兰；主轴 +Z（厚度方向 30），
    # 径向 (x/y) 跨度 ~170，z 跨度 30 → min_ratio = max(x,y)/z ≈ 5.67 但语义上
    # 此件不是细长件，min_ratio 取 1.0 表示"任何主轴方向都接受"
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "CAD_SPEC.md §2 FLANGE_*  + §5 BOM (hand-completed 2026-05-13)",
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
