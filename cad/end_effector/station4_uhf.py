"""
Station 4 (270°) — UHF Detection Module, Plan A (GIS-EE-005)

Per §4.1.2 (lines 213–221):
- I300-UHF-GT sensor: ~Φ45×60mm cylindrical body (300–1500MHz, RS485)
- Mounting bracket: L-shaped, Al 7075-T6
- Envelope: Φ50×85mm (line 219)
- LEMO 0B 7-pin, 4 pins used (RS485 2 + power 2)
- Weight: ~650g (line 221)

BOM: GIS-EE-005-01 传感器, 005-02 安装支架, 005-03 LEMO
"""

import cadquery as cq
import math
from params import (
    S4_SENSOR_DIA, S4_SENSOR_H,
    S4_BRACKET_W, S4_BRACKET_D, S4_BRACKET_H, S4_BRACKET_THICK,
    S4_ENVELOPE_DIA, S4_ENVELOPE_H,
    MOUNT_FACE, MOUNT_BOLT_PCD, MOUNT_BOLT_DIA,
    MOUNT_PIN_DIA, MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y,
    LEMO_BORE_DIA,
)


def make_uhf_sensor() -> cq.Workplane:
    """GIS-EE-005-01: I300-UHF-GT sensor body (cylindrical)."""
    body = cq.Workplane("XY").circle(S4_SENSOR_DIA / 2.0).extrude(S4_SENSOR_H)

    # Sensing face detail (slight recess on bottom)
    recess = (
        cq.Workplane("XY")
        .circle(S4_SENSOR_DIA / 2.0 - 3)
        .extrude(-1.5)
    )
    body = body.cut(recess)

    # Cable exit port on top
    cable = (
        cq.Workplane("XY")
        .workplane(offset=S4_SENSOR_H)
        .center(S4_SENSOR_DIA / 4.0, 0)
        .circle(3.0)
        .extrude(8.0)
    )
    body = body.union(cable)

    # Mounting flange ring near top
    flange = (
        cq.Workplane("XY")
        .workplane(offset=S4_SENSOR_H - 10)
        .circle(S4_SENSOR_DIA / 2.0 + 2)
        .circle(S4_SENSOR_DIA / 2.0)
        .extrude(5.0)
    )
    body = body.union(flange)

    # 4× M3 mounting holes in flange
    for i in range(4):
        a = math.radians(i * 90 + 45)
        bx = (S4_SENSOR_DIA / 2.0 + 1) * math.cos(a)
        by = (S4_SENSOR_DIA / 2.0 + 1) * math.sin(a)
        h = (
            cq.Workplane("XY")
            .workplane(offset=S4_SENSOR_H - 10)
            .center(bx, by)
            .circle(1.6)
            .extrude(5.0)
        )
        body = body.cut(h)

    return body


def make_uhf_bracket() -> cq.Workplane:
    """GIS-EE-005-02: L-shaped mounting bracket."""
    # Base plate (mounts to arm)
    base = cq.Workplane("XY").box(S4_BRACKET_W, S4_BRACKET_D, S4_BRACKET_THICK,
                                   centered=(True, True, False))

    # Vertical plate (holds sensor)
    vert_h = S4_BRACKET_H
    vert = (
        cq.Workplane("XY")
        .workplane(offset=S4_BRACKET_THICK)
        .center(0, -S4_BRACKET_D / 2.0 + S4_BRACKET_THICK / 2.0)
        .box(S4_BRACKET_W, S4_BRACKET_THICK, vert_h,
             centered=(True, True, False))
    )
    base = base.union(vert)

    # Reinforcement gussets (two triangular ribs)
    for gx in [-S4_BRACKET_W / 4.0, S4_BRACKET_W / 4.0]:
        gusset = (
            cq.Workplane("YZ")
            .workplane(offset=gx)
            .center(-S4_BRACKET_D / 2.0 + S4_BRACKET_THICK, S4_BRACKET_THICK)
            .lineTo(0, vert_h * 0.6)
            .lineTo(S4_BRACKET_THICK * 2, 0)
            .close()
            .extrude(2.0)
        )
        base = base.union(gusset)

    # Sensor clamp bore (through vertical plate)
    sensor_center_z = S4_BRACKET_THICK + vert_h * 0.5
    sensor_bore = (
        cq.Workplane("XZ")
        .workplane(offset=-S4_BRACKET_D / 2.0)
        .center(0, sensor_center_z)
        .circle(S4_SENSOR_DIA / 2.0 + 0.5)
        .extrude(S4_BRACKET_THICK + 1)
    )
    base = base.cut(sensor_bore)

    # Clamp slit (for sensor clamping adjustment)
    slit = (
        cq.Workplane("XZ")
        .workplane(offset=-S4_BRACKET_D / 2.0)
        .center(0, sensor_center_z + S4_SENSOR_DIA / 2.0)
        .box(2, 8, S4_BRACKET_THICK + 1, centered=(True, True, False))
    )
    base = base.cut(slit)

    # Mounting face holes (bottom)
    half_s = MOUNT_BOLT_PCD / 2.0
    for dx, dy in [(half_s/2, half_s/2), (half_s/2, -half_s/2),
                   (-half_s/2, half_s/2), (-half_s/2, -half_s/2)]:
        h = cq.Workplane("XY").center(dx, dy).circle(MOUNT_BOLT_DIA / 2.0).extrude(S4_BRACKET_THICK)
        base = base.cut(h)
    pin = cq.Workplane("XY").center(MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y).circle(MOUNT_PIN_DIA / 2.0).extrude(S4_BRACKET_THICK)
    base = base.cut(pin)

    # LEMO bore (side of base plate)
    lemo = (
        cq.Workplane("YZ")
        .workplane(offset=S4_BRACKET_W / 2.0)
        .center(0, S4_BRACKET_THICK / 2.0)
        .circle(LEMO_BORE_DIA / 2.0)
        .extrude(-S4_BRACKET_THICK - 1)
    )
    base = base.cut(lemo)

    return base


def make_uhf_module() -> cq.Workplane:
    """Full UHF module assembly."""
    # Bracket at Z=0
    bracket = make_uhf_bracket()

    # Sensor positioned through bracket bore (vertical plate clamp hole)
    # Sensor center Z must align with bracket bore center
    sensor_center_z = S4_BRACKET_THICK + S4_BRACKET_H * 0.5
    sensor_z = sensor_center_z - S4_SENSOR_H / 2.0
    # Y: sensor passes through bracket vertical plate, protruding forward
    # Bracket vertical plate is at Y = -S4_BRACKET_D/2 + S4_BRACKET_THICK/2
    # Sensor should be centered in the bore, protruding outward (-Y)
    sensor_y = -S4_BRACKET_D / 2.0
    sensor = make_uhf_sensor().translate((0, sensor_y, sensor_z))

    result = bracket.union(sensor)
    return result


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_uhf_module()
    p = os.path.join(out, "EE-005_station4_uhf.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
