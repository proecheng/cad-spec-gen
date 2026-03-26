"""
清洁窗口翻盖 (GIS-EE-004-12)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 硅橡胶一体成型

BOM: GIS-EE-004-12 清洁窗口翻盖
"""

import cadquery as cq
from params import *


def make_ee_004_12() -> cq.Workplane:
    """GIS-EE-004-12: 清洁窗口翻盖 — 硅橡胶一体成型

    Envelope: 25.0 x 20.0 x 3.0 mm
    Weight: ?g
    """
    # TODO: Replace placeholder box with actual geometry
    body = cq.Workplane("XY").box(
        25.0, 20.0, 3.0,
        centered=(True, True, False))

    return body


def draw_ee_004_12_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-004-12."""
    from drawing import ThreeViewSheet
    solid = make_ee_004_12()
    sheet = ThreeViewSheet(
        solid,
        title="清洁窗口翻盖",
        part_no="GIS-EE-004-12",
        material="硅橡胶一体成型",
    )
    return sheet.save(output_dir)


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_004_12()
    p = os.path.join(out, "GIS-EE-004-12.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
