"""
法兰本体（含十字悬臂） (GIS-EE-001-01)

Auto-generated scaffold by codegen/gen_parts.py
Source: CAD_SPEC.md §5 BOM
Material: 7075-T6铝合金

BOM: GIS-EE-001-01 法兰本体（含十字悬臂）
"""

import cadquery as cq
from params import *


def make_ee_001_01() -> cq.Workplane:
    """GIS-EE-001-01: 法兰本体（含十字悬臂） — 7075-T6铝合金

    Envelope: 90.0 x 90.0 x 25.0 mm
    Weight: ?g
    """
    # TODO: Replace placeholder box with actual geometry
    body = cq.Workplane("XY").box(
        90.0, 90.0, 25.0,
        centered=(True, True, False))

    return body


def draw_ee_001_01_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for GIS-EE-001-01."""
    from drawing import ThreeViewSheet
    solid = make_ee_001_01()
    sheet = ThreeViewSheet(
        solid,
        title="法兰本体（含十字悬臂）",
        part_no="GIS-EE-001-01",
        material="7075-T6铝合金",
    )
    return sheet.save(output_dir)


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ee_001_01()
    p = os.path.join(out, "GIS-EE-001-01.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
