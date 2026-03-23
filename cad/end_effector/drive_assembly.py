"""
Drive Assembly — Motor + Reducer + Spring Pin Assembly + ISO 9409 Adapter

Per §4.1.1 (lines 25–38), §4.4.1 (line 348–351), §4.4.2 (lines 396–405):
- ECX SPEED 22L motor: Φ22×48mm body + connector
- GP22C reducer: Φ22×25mm, output shaft Φ8mm
- Reducer flange: Φ25mm, 4×M3 bolt pattern
- Spring pin assembly: 4× pins at R=42mm on reducer output end
- ISO 9409-1-50-4-M6 adapter plate: Φ63×8mm

BOM: GIS-EE-001-05 电机, 001-06 减速器, 001-07 弹簧销组件×4, 001-08 适配板
"""

import cadquery as cq
import math
from params import (
    MOTOR_OD, MOTOR_BODY_LENGTH, REDUCER_OD, REDUCER_LENGTH,
    MOTOR_TOTAL_LENGTH, REDUCER_OUTPUT_DIA, REDUCER_OUTPUT_LENGTH,
    REDUCER_FLANGE_DIA, REDUCER_MOUNT_PCD, REDUCER_MOUNT_BOLT_DIA,
    MOTOR_FLANGE_DIA, MOTOR_FLANGE_THICK,
    ADAPTER_OD, ADAPTER_THICK, ADAPTER_CENTER_HOLE,
    ADAPTER_PILOT_DIA, ADAPTER_PILOT_DEPTH,
    ISO9409_PCD, ISO9409_BOLT_DIA,
    SPRING_PIN_R, SPRING_PIN_DIA, SPRING_PIN_LENGTH, SPRING_PIN_CONE_LENGTH, SPRING_PIN_CONE_RATIO,
    FLANGE_CENTER_HOLE,
    STATION_ANGLES,
)


def make_motor() -> cq.Workplane:
    """GIS-EE-001-05: ECX SPEED 22L motor body."""
    # Main cylinder
    body = cq.Workplane("XY").circle(MOTOR_OD / 2.0).extrude(MOTOR_BODY_LENGTH)

    # Encoder end cap (slightly larger)
    cap = (
        cq.Workplane("XY")
        .workplane(offset=MOTOR_BODY_LENGTH)
        .circle(MOTOR_OD / 2.0 + 1)
        .extrude(5.0)
    )
    body = body.union(cap)

    # Connector pins
    for dx in [-3, 0, 3]:
        pin = (
            cq.Workplane("XY")
            .workplane(offset=MOTOR_BODY_LENGTH + 5)
            .center(dx, 0)
            .circle(0.5)
            .extrude(3.0)
        )
        body = body.union(pin)

    # Front shaft
    shaft = cq.Workplane("XY").circle(2.0).extrude(-5.0)
    body = body.union(shaft)

    # D-flat on shaft
    flat = (
        cq.Workplane("XY")
        .center(2.5, 0)
        .box(2, 4, 5, centered=(True, True, False))
        .translate((0, 0, -5))
    )
    body = body.cut(flat)

    return body


def make_reducer() -> cq.Workplane:
    """GIS-EE-001-06: GP22C planetary reducer."""
    # Main body
    body = cq.Workplane("XY").circle(REDUCER_OD / 2.0).extrude(REDUCER_LENGTH)

    # Input side flange
    in_flange = (
        cq.Workplane("XY")
        .workplane(offset=REDUCER_LENGTH)
        .circle(REDUCER_FLANGE_DIA / 2.0)
        .extrude(MOTOR_FLANGE_THICK)
    )
    body = body.union(in_flange)

    # Output shaft
    shaft = cq.Workplane("XY").circle(REDUCER_OUTPUT_DIA / 2.0).extrude(-REDUCER_OUTPUT_LENGTH)
    body = body.union(shaft)

    # Output flange (front face with bolt holes)
    out_flange = (
        cq.Workplane("XY")
        .circle(REDUCER_FLANGE_DIA / 2.0)
        .circle(REDUCER_OUTPUT_DIA / 2.0 + 1)
        .extrude(-3.0)
    )
    body = body.union(out_flange)

    # 4×M3 mounting holes on input flange
    for i in range(4):
        a = math.radians(i * 90 + 45)
        bx = (REDUCER_MOUNT_PCD / 2.0) * math.cos(a)
        by = (REDUCER_MOUNT_PCD / 2.0) * math.sin(a)
        h = (
            cq.Workplane("XY")
            .workplane(offset=REDUCER_LENGTH)
            .center(bx, by)
            .circle(REDUCER_MOUNT_BOLT_DIA / 2.0)
            .extrude(MOTOR_FLANGE_THICK)
        )
        body = body.cut(h)

    return body


def make_spring_pin() -> cq.Workplane:
    """GIS-EE-001-07: Single spring pin Φ4×20mm with 1:10 cone."""
    # Cylindrical body
    pin = cq.Workplane("XY").circle(SPRING_PIN_DIA / 2.0).extrude(SPRING_PIN_LENGTH - SPRING_PIN_CONE_LENGTH)

    # Cone tip
    cone = (
        cq.Workplane("XY")
        .workplane(offset=SPRING_PIN_LENGTH - SPRING_PIN_CONE_LENGTH)
        .circle(SPRING_PIN_DIA / 2.0)
        .workplane(offset=SPRING_PIN_CONE_LENGTH)
        .circle(SPRING_PIN_DIA / 2.0 - SPRING_PIN_CONE_LENGTH * SPRING_PIN_CONE_RATIO)
        .loft()
    )
    pin = pin.union(cone)

    # Spring housing (internal bore in body end)
    spring_bore = (
        cq.Workplane("XY")
        .circle(SPRING_PIN_DIA / 2.0 - 0.8)
        .extrude(SPRING_PIN_LENGTH * 0.5)
    )
    pin = pin.cut(spring_bore)

    return pin


def make_spring_pin_assembly() -> cq.Workplane:
    """4× spring pins at R=42mm, offset 45° from station arms."""
    result = None
    for angle in STATION_ANGLES:
        rad = math.radians(angle + 45)
        px = SPRING_PIN_R * math.cos(rad)
        py = SPRING_PIN_R * math.sin(rad)
        pin = make_spring_pin().translate((px, py, 0))
        if result is None:
            result = pin
        else:
            result = result.union(pin)
    return result


def make_adapter_plate() -> cq.Workplane:
    """GIS-EE-001-08: ISO 9409-1-50-4-M6 adapter plate Φ63×8mm."""
    plate = cq.Workplane("XY").circle(ADAPTER_OD / 2.0).extrude(ADAPTER_THICK)

    # Center bore
    center = cq.Workplane("XY").circle(ADAPTER_CENTER_HOLE / 2.0).extrude(ADAPTER_THICK)
    plate = plate.cut(center)

    # Pilot bore (locating step on one face)
    pilot = (
        cq.Workplane("XY")
        .workplane(offset=ADAPTER_THICK)
        .circle(ADAPTER_PILOT_DIA / 2.0)
        .circle(ADAPTER_CENTER_HOLE / 2.0)
        .extrude(-ADAPTER_PILOT_DEPTH)
    )
    plate = plate.cut(pilot)

    # ISO 9409 bolt holes (4×M6 on PCD50)
    iso_half = ISO9409_PCD / 2.0 / math.sqrt(2)
    for dx, dy in [(iso_half, iso_half), (iso_half, -iso_half),
                   (-iso_half, iso_half), (-iso_half, -iso_half)]:
        h = cq.Workplane("XY").center(dx, dy).circle(ISO9409_BOLT_DIA / 2.0).extrude(ADAPTER_THICK)
        plate = plate.cut(h)

    # Counterbore for bolt heads (on RM65-B side = Z=0)
    for dx, dy in [(iso_half, iso_half), (iso_half, -iso_half),
                   (-iso_half, iso_half), (-iso_half, -iso_half)]:
        cb = (
            cq.Workplane("XY")
            .center(dx, dy)
            .circle(ISO9409_BOLT_DIA / 2.0 + 2.5)
            .extrude(4.0)
        )
        plate = plate.cut(cb)

    return plate


def make_drive_assembly() -> cq.Workplane:
    """
    Full drive assembly.
    Coordinate system: Z=0 is flange interface (where adapter meets Al disc).
    Motor+reducer extend in -Z (toward RM65-B).
    Spring pins extend in +Z (into flange pin holes).
    """
    # Adapter plate: Z = -ADAPTER_THICK to Z = 0
    adapter = make_adapter_plate().translate((0, 0, -ADAPTER_THICK))

    # Reducer: output shaft at Z=0 going into flange, body in -Z
    # Reducer body starts at Z = -(ADAPTER_THICK + gap)
    gap = 1.0
    reducer = make_reducer().translate((0, 0, -ADAPTER_THICK - gap - REDUCER_LENGTH))
    # But output shaft extends from reducer toward +Z
    # Let's position more carefully:
    # Reducer body: from Z_r to Z_r + REDUCER_LENGTH
    # Output shaft: from Z_r down by REDUCER_OUTPUT_LENGTH
    # We want output shaft tip near Z=0 (through adapter center hole)
    reducer_z = -ADAPTER_THICK - gap
    reducer = make_reducer().translate((0, 0, reducer_z - REDUCER_LENGTH))

    result = adapter.union(reducer)

    # Motor connects to reducer input
    motor_z = reducer_z - REDUCER_LENGTH - MOTOR_FLANGE_THICK
    motor = make_motor().translate((0, 0, motor_z - MOTOR_BODY_LENGTH))
    result = result.union(motor)

    # Spring pin assembly (mounted on reducer output, extending +Z into flange holes)
    pins = make_spring_pin_assembly().translate((0, 0, -3))  # slightly recessed
    result = result.union(pins)

    return result


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_drive_assembly()
    p = os.path.join(out, "EE-006_drive.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
