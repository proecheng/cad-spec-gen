"""
涂抹模块壳体 (GIS-EE-002-01)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 7075-T6铝合金

BOM: GIS-EE-002-01 涂抹模块壳体
"""

import cadquery as cq
from params import *


def make_ee_002_01() -> cq.Workplane:
    """GIS-EE-002-01: 涂抹模块壳体 — 7075-T6铝合金

    Envelope: 50.0 x 40.0 x 60.0 mm
    Weight: ?g
    """
    # TODO: Replace placeholder box with actual geometry
    body = cq.Workplane("XY").box(
        50.0, 40.0, 60.0,
        centered=(True, True, False))

    return body


def draw_ee_002_01_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-002-01."""
    from drawing import ThreeViewSheet
    solid = make_ee_002_01()
    sheet = ThreeViewSheet(
        solid,
        title="涂抹模块壳体",
        part_no="GIS-EE-002-01",
        material="7075-T6铝合金",
    )
    return sheet.save(output_dir)


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_002_01()
    p = os.path.join(out, "GIS-EE-002-01.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
