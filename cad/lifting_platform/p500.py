"""
同步带护罩 (SLP-500) — CP-1 Task 5g hand-completed 2026-05-13

从 L3 ENRICHED_PLACEHOLDER (importStep stub, envelope=(40,40,20)) 升级到真实 box 几何。

设计依据：
- CAD_SPEC.md §6.4 line 248: envelope **170×80×40 mm**，"开口朝 −Z"（v1 不开口，纯单 box）
- tmp/_custom_parts_spec.md §7：v1 极度简化为单 box，装饰件不影响装配
- 装配位置（assembly_layout.py:30）：(0,0,-8) 在 GT2-310 同步带上方做装饰罩
"""

import cadquery as cq


# 几何常量（CAD_SPEC §6.4 envelope）
COVER_W = 170.0   # mm — 沿带方向（X）
COVER_D = 80.0    # mm — 宽（Y）
COVER_H = 40.0    # mm — 高（Z）
COVER_T = 1.5     # mm — 板厚（v1 不做空心，记录意图）


def make_p500() -> cq.Workplane:
    """SLP-500: 同步带护罩 — 铝板/PLA 装饰件

    Envelope: 170×80×40 mm（CAD_SPEC §6.4 line 248 真值）
    v1 简化：单 box 实心；"开口朝 −Z" 工程意图不实现（不影响 GLB 视觉）。

    Axis: +Z 板法线（box 短边）；assembly 平移到带轮组上方。
    Doc:  CAD_SPEC.md §6.4 + tmp/_custom_parts_spec.md §7
    """
    body = cq.Workplane("XY").box(
        COVER_W, COVER_D, COVER_H,
        centered=(True, True, False),
    )
    return body


# Backward-compatible alias for older direct callers
p500 = make_p500


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """护罩件：principal_axis 用 'x' 因为 170 是最长跨度。"""
    return {
        "principal_axis": "x",
        "min_ratio": 1.5,
        "doc_ref": "CAD_SPEC.md §6.4 / Task 0 spec §7",
    }


def draw_p500_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-500.

    与其他自制件保持一致的 GB/T 三视图接口；
    build_all._DXF_BUILDS 调用此函数。
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p500()
    sheet = ThreeViewSheet(
        part_no="SLP-500",
        name="同步带护罩",
        material="铝板/PLA",
        scale="1:2",
        weight_g=0,
        date=date.today().isoformat(),
        project_name="SLP",
        subsystem_name="丝杠式升降平台",
    )
    auto_three_view(solid, sheet)

    auto_annotate(solid, sheet, annotation_meta={
        "dim_tolerances": [],
        "gdt": [],
        "surfaces": [{"material_type": "", "part": "同步带护罩 SLP-500", "process": "铝板/PLA", "ra": "Ra3.2"}],
    })

    return sheet.save(output_dir, material_type="al")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_p500()
    p = os.path.join(out, "SLP-500.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
