"""
壳体（含散热鳍片） (GIS-EE-006-01)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 6063铝合金 140×100×55mm

BOM: GIS-EE-006-01 壳体（含散热鳍片）
"""

import cadquery as cq
from params import *


def make_ee_006_01() -> cq.Workplane:
    """GIS-EE-006-01: 壳体（含散热鳍片） — 6063铝合金 140×100×55mm

    Envelope: 50.0 x 40.0 x 60.0 mm
    Weight: ?g
    """
    # TODO: Replace placeholder box with actual geometry
    body = cq.Workplane("XY").box(
        50.0, 40.0, 60.0,
        centered=(True, True, False))

    return body


def draw_ee_006_01_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-006-01."""
    from drawing import ThreeViewSheet
    solid = make_ee_006_01()
    sheet = ThreeViewSheet(
        solid,
        title="壳体（含散热鳍片）",
        part_no="GIS-EE-006-01",
        material="6063铝合金 140×100×55mm",
    )
    return sheet.save(output_dir)


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_006_01()
    p = os.path.join(out, "GIS-EE-006-01.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
