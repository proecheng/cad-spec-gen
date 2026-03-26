"""
弹簧限力机构总成 (GIS-EE-003-03)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 见§4.1.2零件表

BOM: GIS-EE-003-03 弹簧限力机构总成
"""

import cadquery as cq
from params import *


def make_ee_003_03() -> cq.Workplane:
    """GIS-EE-003-03: 弹簧限力机构总成 — 见§4.1.2零件表

    Envelope: 40.0 x 40.0 x 20.0 mm
    Weight: ?g
    """
    # TODO: Replace placeholder box with actual geometry
    body = cq.Workplane("XY").box(
        40.0, 40.0, 20.0,
        centered=(True, True, False))

    return body


def draw_ee_003_03_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-003-03."""
    from drawing import ThreeViewSheet
    solid = make_ee_003_03()
    sheet = ThreeViewSheet(
        solid,
        title="弹簧限力机构总成",
        part_no="GIS-EE-003-03",
        material="见§4.1.2零件表",
    )
    return sheet.save(output_dir)


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_003_03()
    p = os.path.join(out, "GIS-EE-003-03.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
