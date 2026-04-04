"""
同步带护罩 (SLP-500)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 

BOM: SLP-500 同步带护罩

┌─ COORDINATE SYSTEM ───────────────────────────────────────────────────────┐
│ Local origin : Center of cover XY, top face at Z=0                       │
│ Principal axis: U-shape open at bottom, extends along −Z (40mm)          │
│ Assembly orient: Top face at Z=−8 (bottom plate underside), extends −48  │
│                  Center at (0, 0) in global coords                       │
│ Design doc ref : §10.2 同步带护罩 — 170×80×40 mm U-shaped                │
└──────────────────────────────────────────────────────────────────────────┘
"""

import cadquery as cq
from params import *


def make_p500() -> cq.Workplane:
    """SLP-500: 同步带护罩 — Timing belt guard cover

    Envelope: 170(X) x 80(Y) x 40(Z) mm, U-shaped (open bottom)
    Wall thickness: ~1mm (aluminum sheet) or 2mm (3D print)

    Doc:  §10.2 同步带护罩 — 170×80×40 mm U-shaped
          Covers belt pulleys + timing belt area below bottom plate
          Fixed by 2×M3 to left/right support bar bottom faces
    """
    # ── Geometry: 170(X) × 80(Y) × 40(Z) U-shaped cover ─────────────────────
    # §10.2: U型, from Z=−8 (bottom plate) down 40mm to Z=−48
    # Simplified as a solid box (shell would need wall thickness parameter)
    # Local origin at cover center XY, top face at Z=0 (mounts against bottom plate)
    # For simple representation, model as solid box — open-bottom detail
    # would require shell operation which adds complexity
    W = 170.0  # X
    D = 80.0   # Y
    H = 40.0   # Z
    wall = 2.0  # wall thickness (approximation for 3D-print variant)

    # Outer box, top at Z=0, extends downward
    outer = (cq.Workplane("XY")
             .transformed(offset=(0, 0, -H))
             .box(W, D, H, centered=(True, True, False)))

    # Inner cavity (open at bottom), leaving walls on top and 3 sides
    inner = (cq.Workplane("XY")
             .transformed(offset=(0, 0, -H - 1.0))
             .box(W - 2 * wall, D - 2 * wall, H - wall + 1.0,
                  centered=(True, True, False)))

    body = outer.cut(inner)
    return body


# ── Orientation self-check (called by orientation_check.py) ───────────────
def _orientation_spec():
    """Return expected bounding-box axis for orientation_check.py.

    Fill this in when implementing make_p500().
    Return dict with keys: principal_axis ('x'|'y'|'z'), min_ratio (length/width ratio).
    Example: {'principal_axis': 'z', 'min_ratio': 2.0}
    """
    return {
        "principal_axis": "z",
        "min_ratio": 1.0,
        "doc_ref": "§10.2 同步带护罩 170×80×40 U-shaped",
    }


def draw_p500_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for SLP-500.

    Auto-projects the 3D solid into GB/T first-angle front/top/left views
    using OCC HLR (Hidden Line Removal) via cq_to_dxf module,
    then adds GB/T compliant annotations (dimensions, center lines,
    tolerances, GD&T, surface symbols) via auto_annotate.
    """
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_p500()
    sheet = ThreeViewSheet(
        part_no="SLP-500",
        name="同步带护罩",
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
        "surfaces": [{"material_type": "", "part": "\u540c\u6b65\u5e26\u62a4\u7f69 SLP-500", "process": "\u94dd\u677f/PLA", "ra": "Ra3.2"}],
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
