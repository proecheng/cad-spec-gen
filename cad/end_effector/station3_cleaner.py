"""
Station 3 (180°) — Tape-Wipe Cleaning Module (GIS-EE-004)

Per §4.1.2 (lines 167–198):
- Body shell 50×40×120mm (Al 7075-T6) with spool cavities + cleaning window
- Dual spools: supply Φ8→Φ28 + take-up Φ10→Φ28, center spacing 30mm
- 4× MR105ZZ bearings (Φ10×Φ5×4mm), stainless shafts Φ5mm
- Elastic pad 20×15×5mm (silicone Shore A 30) in cleaning window recess
- Solvent tank Φ25×110mm (Novec 7300), M8 cap, radially outward
- DC motor Φ16×30mm for take-up drive
- Protective silicone flap on cleaning window
- Counterweight Φ14×13mm tungsten (120g) at top
- Snap-fit tape cassette with anti-reverse notch
- LEMO 0B bore Φ9.4mm

BOM: GIS-EE-004-01~13 (壳体, 带盒, 电机, 齿轮组, 衬垫, 恒力弹簧,
     编码器, 储罐, 微量泵, 配重块, 轴承×4, 翻盖, LEMO)
"""

import cadquery as cq
import math
from params import (
    S3_BODY_W, S3_BODY_D, S3_BODY_H, S3_WALL_THICK,
    S3_TAPE_WIDTH,
    S3_SUPPLY_CORE_ID, S3_SUPPLY_FULL_OD,
    S3_TAKEUP_CORE_ID, S3_TAKEUP_FULL_OD,
    S3_SPOOL_WIDTH, S3_SPOOL_SPACING,
    S3_BEARING_OD, S3_BEARING_ID, S3_BEARING_THICK,
    S3_SHAFT_DIA,
    S3_PAD_W, S3_PAD_D, S3_PAD_H,
    S3_WINDOW_W, S3_WINDOW_D,
    S3_TANK_OD, S3_TANK_ID, S3_TANK_LENGTH, S3_TANK_CAP_THREAD,
    S3_MOTOR_DIA, S3_MOTOR_LENGTH,
    S3_FLAP_THICK, S3_FLAP_W,
    S3_CW_DIA, S3_CW_H, S3_CW_BOLT_DIA,
    S3_CASSETTE_W, S3_CASSETTE_D, S3_CASSETTE_H, S3_CASSETTE_GUIDE_W, S3_CASSETTE_NOTCH,
    MOUNT_FACE, MOUNT_BOLT_PCD, MOUNT_BOLT_DIA,
    MOUNT_PIN_DIA, MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y,
    LEMO_BORE_DIA,
)


def make_cleaner_body() -> cq.Workplane:
    """GIS-EE-004-01: Cleaner shell with spool cavities and cleaning window."""
    # Outer shell
    body = cq.Workplane("XY").box(S3_BODY_W, S3_BODY_D, S3_BODY_H,
                                   centered=(True, True, False))

    # Hollow interior (spool cavity)
    cavity = (
        cq.Workplane("XY")
        .workplane(offset=S3_WALL_THICK)
        .box(S3_BODY_W - 2*S3_WALL_THICK, S3_BODY_D - 2*S3_WALL_THICK,
             S3_BODY_H - 2*S3_WALL_THICK, centered=(True, True, False))
    )
    body = body.cut(cavity)

    # Cleaning window opening at bottom (front face, -Y side)
    window_z = S3_WALL_THICK  # just above bottom plate
    window = (
        cq.Workplane("XZ")
        .workplane(offset=-S3_BODY_D / 2.0)
        .center(0, window_z + S3_WINDOW_W / 2.0 + 5)
        .box(S3_WINDOW_W, S3_WINDOW_D, S3_WALL_THICK + 1,
             centered=(True, True, False))
    )
    body = body.cut(window)

    # Elastic pad recess behind cleaning window (inside wall)
    pad_recess = (
        cq.Workplane("XZ")
        .workplane(offset=-S3_BODY_D / 2.0 + S3_WALL_THICK)
        .center(0, window_z + 5)
        .box(S3_PAD_W, S3_PAD_H, S3_PAD_D, centered=(True, False, False))
    )
    body = body.cut(pad_recess)

    # Bearing seat bores (2 per spool, 4 total)
    # Spools are arranged along X (tangential), spacing = 30mm
    spool_x_left = -S3_SPOOL_SPACING / 2.0   # supply spool
    spool_x_right = S3_SPOOL_SPACING / 2.0    # take-up spool
    spool_z = S3_BODY_H * 0.55                 # spool center height

    for sx in [spool_x_left, spool_x_right]:
        for wall_y in [-S3_BODY_D / 2.0, S3_BODY_D / 2.0 - S3_WALL_THICK]:
            bearing_seat = (
                cq.Workplane("XZ")
                .workplane(offset=wall_y)
                .center(sx, spool_z)
                .circle(S3_BEARING_OD / 2.0)
                .extrude(S3_WALL_THICK)
            )
            body = body.cut(bearing_seat)

    # Motor cavity (in top-right area, for take-up drive)
    motor_z = S3_BODY_H - S3_WALL_THICK - S3_MOTOR_DIA / 2.0 - 3
    motor_bore = (
        cq.Workplane("XZ")
        .workplane(offset=S3_BODY_D / 2.0)
        .center(spool_x_right, motor_z)
        .circle(S3_MOTOR_DIA / 2.0 + 0.5)
        .extrude(-S3_WALL_THICK - 1)
    )
    body = body.cut(motor_bore)

    # Tank mounting bore (through side wall, radially outward)
    tank_z = S3_BODY_H * 0.5
    tank_bore = (
        cq.Workplane("YZ")
        .workplane(offset=S3_BODY_W / 2.0)
        .center(0, tank_z)
        .circle(S3_TANK_OD / 2.0 + 0.5)
        .extrude(-S3_WALL_THICK - 1)
    )
    body = body.cut(tank_bore)

    # LEMO bore on opposite side
    lemo = (
        cq.Workplane("YZ")
        .workplane(offset=-S3_BODY_W / 2.0)
        .center(0, S3_BODY_H * 0.7)
        .circle(LEMO_BORE_DIA / 2.0)
        .extrude(S3_WALL_THICK + 1)
    )
    body = body.cut(lemo)

    # Cassette guide rails (two L-shaped rails inside, front and back walls)
    for side_y in [-S3_BODY_D / 2.0 + S3_WALL_THICK,
                    S3_BODY_D / 2.0 - S3_WALL_THICK - S3_CASSETTE_GUIDE_W]:
        rail = (
            cq.Workplane("XY")
            .workplane(offset=S3_WALL_THICK)
            .center(0, side_y + S3_CASSETTE_GUIDE_W / 2.0)
            .box(S3_BODY_W - 2*S3_WALL_THICK - 2,
                 S3_CASSETTE_GUIDE_W, S3_CASSETTE_H,
                 centered=(True, True, False))
        )
        body = body.union(rail)

    # Top opening for cassette insertion
    cassette_opening = (
        cq.Workplane("XY")
        .workplane(offset=S3_BODY_H - S3_WALL_THICK - 0.1)
        .box(S3_CASSETTE_W + 1, S3_CASSETTE_D + 1, S3_WALL_THICK + 0.2,
             centered=(True, True, False))
    )
    body = body.cut(cassette_opening)

    # Mounting face bolt holes (through bottom plate)
    half_s = MOUNT_BOLT_PCD / 2.0
    for dx, dy in [(half_s/2, half_s/2), (half_s/2, -half_s/2),
                   (-half_s/2, half_s/2), (-half_s/2, -half_s/2)]:
        h = cq.Workplane("XY").center(dx, dy).circle(MOUNT_BOLT_DIA / 2.0).extrude(S3_WALL_THICK)
        body = body.cut(h)
    pin = cq.Workplane("XY").center(MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y).circle(MOUNT_PIN_DIA / 2.0).extrude(S3_WALL_THICK)
    body = body.cut(pin)

    # Flap hinge recess at bottom front
    hinge = (
        cq.Workplane("XZ")
        .workplane(offset=-S3_BODY_D / 2.0 - 0.1)
        .center(0, S3_WALL_THICK + 2)
        .box(S3_FLAP_W, 3, 2, centered=(True, True, False))
    )
    body = body.cut(hinge)

    return body


def make_supply_spool() -> cq.Workplane:
    """Supply spool: core Φ8mm → full Φ28mm, width 17mm."""
    # Hub
    hub = cq.Workplane("XY").circle(S3_SUPPLY_CORE_ID / 2.0 + 1).extrude(S3_SPOOL_WIDTH)
    bore = cq.Workplane("XY").circle(S3_SHAFT_DIA / 2.0).extrude(S3_SPOOL_WIDTH)
    hub = hub.cut(bore)
    # Side flanges
    for z_off in [0, S3_SPOOL_WIDTH - 1.0]:
        flange = (
            cq.Workplane("XY")
            .workplane(offset=z_off)
            .circle(S3_SUPPLY_FULL_OD / 2.0)
            .circle(S3_SUPPLY_CORE_ID / 2.0)
            .extrude(1.0)
        )
        hub = hub.union(flange)
    # Tape winding (partial fill)
    tape = (
        cq.Workplane("XY")
        .workplane(offset=1.0)
        .circle(S3_SUPPLY_FULL_OD / 2.0 - 1)
        .circle(S3_SUPPLY_CORE_ID / 2.0 + 1)
        .extrude(S3_SPOOL_WIDTH - 2.0)
    )
    hub = hub.union(tape)
    return hub


def make_takeup_spool() -> cq.Workplane:
    """Take-up spool: core Φ10mm, initially empty, width 17mm."""
    hub = cq.Workplane("XY").circle(S3_TAKEUP_CORE_ID / 2.0 + 1).extrude(S3_SPOOL_WIDTH)
    bore = cq.Workplane("XY").circle(S3_SHAFT_DIA / 2.0).extrude(S3_SPOOL_WIDTH)
    hub = hub.cut(bore)
    for z_off in [0, S3_SPOOL_WIDTH - 1.0]:
        flange = (
            cq.Workplane("XY")
            .workplane(offset=z_off)
            .circle(S3_TAKEUP_FULL_OD / 2.0)
            .circle(S3_TAKEUP_CORE_ID / 2.0)
            .extrude(1.0)
        )
        hub = hub.union(flange)
    return hub


def make_bearing() -> cq.Workplane:
    """MR105ZZ bearing Φ10×Φ5×4mm."""
    outer = cq.Workplane("XY").circle(S3_BEARING_OD / 2.0).extrude(S3_BEARING_THICK)
    inner = cq.Workplane("XY").circle(S3_BEARING_ID / 2.0).extrude(S3_BEARING_THICK)
    return outer.cut(inner)


def make_shaft(length: float) -> cq.Workplane:
    """Stainless steel shaft Φ5mm."""
    return cq.Workplane("XY").circle(S3_SHAFT_DIA / 2.0).extrude(length)


def make_elastic_pad() -> cq.Workplane:
    """GIS-EE-004-05: Silicone pad 20×15×5mm, Shore A 30."""
    return cq.Workplane("XY").box(S3_PAD_W, S3_PAD_D, S3_PAD_H,
                                   centered=(True, True, False))


def make_motor() -> cq.Workplane:
    """GIS-EE-004-03: DC motor Φ16×30mm."""
    motor = cq.Workplane("XY").circle(S3_MOTOR_DIA / 2.0).extrude(S3_MOTOR_LENGTH)
    # Output shaft
    shaft = cq.Workplane("XY").circle(1.5).extrude(S3_MOTOR_LENGTH + 8)
    motor = motor.union(shaft)
    return motor


def make_solvent_tank() -> cq.Workplane:
    """GIS-EE-004-08: Solvent tank Φ25×110mm with M8 cap."""
    tank = cq.Workplane("XY").circle(S3_TANK_OD / 2.0).extrude(S3_TANK_LENGTH)
    inner = (
        cq.Workplane("XY")
        .workplane(offset=2.0)
        .circle(S3_TANK_ID / 2.0)
        .extrude(S3_TANK_LENGTH - 4.0)
    )
    tank = tank.cut(inner)
    # M8 cap at end
    cap = (
        cq.Workplane("XY")
        .workplane(offset=S3_TANK_LENGTH)
        .circle(S3_TANK_CAP_THREAD / 2.0 + 2.5)
        .circle(S3_TANK_CAP_THREAD / 2.0)
        .extrude(6.0)
    )
    tank = tank.union(cap)
    # Outlet port
    outlet = cq.Workplane("XY").circle(2.0).extrude(-4.0)
    tank = tank.union(outlet)
    return tank


def make_counterweight() -> cq.Workplane:
    """GIS-EE-004-10: Tungsten counterweight Φ14×13mm, 120g."""
    cw = cq.Workplane("XY").circle(S3_CW_DIA / 2.0).extrude(S3_CW_H)
    for dx in [-4, 4]:
        h = cq.Workplane("XY").center(dx, 0).circle(S3_CW_BOLT_DIA / 2.0).extrude(S3_CW_H)
        cw = cw.cut(h)
    return cw


def make_protective_flap() -> cq.Workplane:
    """GIS-EE-004-12: Silicone rubber protective flap."""
    flap = cq.Workplane("XY").box(S3_FLAP_W, S3_PAD_D + 4, S3_FLAP_THICK,
                                   centered=(True, True, False))
    return flap


def make_tape_cassette() -> cq.Workplane:
    """GIS-EE-004-02: Snap-fit tape cassette housing both spools."""
    # Outer frame
    frame = cq.Workplane("XY").box(S3_CASSETTE_W, S3_CASSETTE_D, S3_CASSETTE_H,
                                    centered=(True, True, False))
    # Hollow
    inner = (
        cq.Workplane("XY")
        .workplane(offset=1.5)
        .box(S3_CASSETTE_W - 3, S3_CASSETTE_D - 3, S3_CASSETTE_H - 3,
             centered=(True, True, False))
    )
    frame = frame.cut(inner)

    # Anti-reverse notch (left side corner cut)
    notch = (
        cq.Workplane("XY")
        .center(-S3_CASSETTE_W / 2.0, -S3_CASSETTE_D / 2.0)
        .box(S3_CASSETTE_NOTCH, S3_CASSETTE_NOTCH, S3_CASSETTE_H,
             centered=(False, False, False))
    )
    frame = frame.cut(notch)

    # Spool windows (allow tape to enter/exit)
    for z_off in [5, S3_CASSETTE_H - 15]:
        win = (
            cq.Workplane("XZ")
            .workplane(offset=-S3_CASSETTE_D / 2.0 - 0.1)
            .center(0, z_off + 5)
            .box(S3_TAPE_WIDTH + 2, 10, 1.6, centered=(True, True, False))
        )
        frame = frame.cut(win)

    # Snap-fit tab on top
    tab = (
        cq.Workplane("XY")
        .workplane(offset=S3_CASSETTE_H)
        .center(S3_CASSETTE_W / 4.0, 0)
        .box(8, 4, 3, centered=(True, True, False))
    )
    frame = frame.union(tab)

    return frame


def make_gear_set() -> cq.Workplane:
    """GIS-EE-004-04: Gear reduction set (3 spur gears, simplified).

    Motor pinion → idler → take-up gear. Origin at motor pinion center.
    """
    # Pinion (motor output): Φ5 × 4mm
    pinion = cq.Workplane("XY").circle(2.5).extrude(4.0)
    pinion_bore = cq.Workplane("XY").circle(1.5).extrude(4.0)
    pinion = pinion.cut(pinion_bore)

    # Idler: Φ10 × 4mm, center offset 7.5mm from pinion
    idler = cq.Workplane("XY").circle(5.0).extrude(4.0).translate((7.5, 0, 0))
    idler_bore = cq.Workplane("XY").center(7.5, 0).circle(2.0).extrude(4.0)
    idler = idler.cut(idler_bore)
    pinion = pinion.union(idler)

    # Output gear: Φ14 × 4mm, center offset 12mm from idler
    output = cq.Workplane("XY").circle(7.0).extrude(4.0).translate((19.5, 0, 0))
    output_bore = cq.Workplane("XY").center(19.5, 0).circle(S3_SHAFT_DIA / 2.0).extrude(4.0)
    output = output.cut(output_bore)
    pinion = pinion.union(output)

    return pinion


def make_constant_force_spring() -> cq.Workplane:
    """GIS-EE-004-06: Constant-force spring for tape tension (0.3N).

    Simplified as a coiled thin strip. Origin at mounting point.
    """
    # Coiled drum (resting state): Φ10 × 6mm
    coil = (
        cq.Workplane("XY")
        .circle(5.0)
        .circle(3.0)
        .extrude(6.0)
    )
    # Extended strip (simplified as flat bar)
    strip = (
        cq.Workplane("XY")
        .workplane(offset=2.5)
        .center(5.0, 0)
        .rect(15.0, 3.0)
        .extrude(0.3)
    )
    return coil.union(strip)


def make_optical_encoder() -> cq.Workplane:
    """GIS-EE-004-07: Optical encoder for tape-out detection (5×5×3mm)."""
    body = cq.Workplane("XY").box(5.0, 5.0, 3.0, centered=(True, True, False))
    # Sensor slot
    slot = (
        cq.Workplane("XY")
        .workplane(offset=1.0)
        .box(1.5, 6.0, 1.0, centered=(True, True, False))
    )
    body = body.cut(slot)
    return body


def make_micro_pump() -> cq.Workplane:
    """GIS-EE-004-09: Micro diaphragm pump for solvent (Φ8×15mm)."""
    body = cq.Workplane("XY").circle(4.0).extrude(15.0)
    # Inlet port (-Z end)
    inlet = cq.Workplane("XY").circle(1.5).extrude(-3.0)
    body = body.union(inlet)
    # Outlet port (+Z end)
    outlet = (
        cq.Workplane("XY")
        .workplane(offset=15.0)
        .circle(1.5)
        .extrude(3.0)
    )
    body = body.union(outlet)
    return body


def make_cleaner() -> cq.Workplane:
    """
    Full cleaner assembly (GIS-EE-004).
    Origin at mounting face center, Z+ = away from flange.
    """
    # Body shell
    body = make_cleaner_body()

    # Spool positions
    spool_z = S3_BODY_H * 0.55
    spool_x_supply = -S3_SPOOL_SPACING / 2.0
    spool_x_takeup = S3_SPOOL_SPACING / 2.0

    # Supply spool (rotated to lay axis along Y)
    supply = (
        make_supply_spool()
        .rotate((0, 0, 0), (1, 0, 0), 90)
        .translate((spool_x_supply, -S3_SPOOL_WIDTH / 2.0, spool_z))
    )
    body = body.union(supply)

    # Take-up spool
    takeup = (
        make_takeup_spool()
        .rotate((0, 0, 0), (1, 0, 0), 90)
        .translate((spool_x_takeup, -S3_SPOOL_WIDTH / 2.0, spool_z))
    )
    body = body.union(takeup)

    # 4× bearings (one pair per spool, on each side wall)
    for sx in [spool_x_supply, spool_x_takeup]:
        for side_y, rot in [(-S3_BODY_D / 2.0 + S3_WALL_THICK, 0),
                             (S3_BODY_D / 2.0 - S3_WALL_THICK, 0)]:
            brg = (
                make_bearing()
                .rotate((0, 0, 0), (1, 0, 0), 90)
                .translate((sx, side_y, spool_z))
            )
            body = body.union(brg)

    # Shafts
    shaft_len = S3_BODY_D - 2 * S3_WALL_THICK
    for sx in [spool_x_supply, spool_x_takeup]:
        sh = (
            make_shaft(shaft_len)
            .rotate((0, 0, 0), (1, 0, 0), 90)
            .translate((sx, -shaft_len / 2.0, spool_z))
        )
        body = body.union(sh)

    # Elastic pad in cleaning window
    pad = make_elastic_pad().translate((0, -S3_BODY_D / 2.0 + S3_WALL_THICK, S3_WALL_THICK + 5))
    body = body.union(pad)

    # Motor (top right, axis along Y)
    motor_z = S3_BODY_H - S3_WALL_THICK - S3_MOTOR_DIA / 2.0 - 3
    motor = (
        make_motor()
        .rotate((0, 0, 0), (1, 0, 0), 90)
        .translate((spool_x_takeup, S3_BODY_D / 2.0, motor_z))
    )
    body = body.union(motor)

    # Solvent tank (radially outward, along +X)
    tank = (
        make_solvent_tank()
        .rotate((0, 0, 0), (0, 1, 0), -90)
        .translate((S3_BODY_W / 2.0, 0, S3_BODY_H * 0.5))
    )
    body = body.union(tank)

    # Gear set (between motor output and take-up spool)
    gear_z = motor_z - S3_MOTOR_DIA / 2.0 - 3
    gears = (
        make_gear_set()
        .rotate((0, 0, 0), (1, 0, 0), 90)
        .translate((spool_x_takeup - 5, S3_BODY_D / 2.0 - S3_WALL_THICK - 2, gear_z))
    )
    body = body.union(gears)

    # Constant-force spring (near supply spool floating guide)
    cf_spring = (
        make_constant_force_spring()
        .translate((spool_x_supply, 0, spool_z - S3_SUPPLY_FULL_OD / 2.0 - 8))
    )
    body = body.union(cf_spring)

    # Optical encoder (near take-up spool)
    encoder = (
        make_optical_encoder()
        .translate((spool_x_takeup + S3_TAKEUP_FULL_OD / 2.0 + 3, 0, spool_z))
    )
    body = body.union(encoder)

    # Micro pump (in solvent path, inside shell near tank bore)
    pump = (
        make_micro_pump()
        .rotate((0, 0, 0), (0, 1, 0), -90)
        .translate((S3_BODY_W / 2.0 - S3_WALL_THICK - 5, 0, S3_BODY_H * 0.35))
    )
    body = body.union(pump)

    # Counterweight at top
    cw = make_counterweight().translate((0, 0, S3_BODY_H))
    body = body.union(cw)

    # Protective flap at bottom front
    flap = make_protective_flap().translate((0, -S3_BODY_D / 2.0 - S3_FLAP_THICK,
                                              S3_WALL_THICK + 3))
    body = body.union(flap)

    return body


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_cleaner()
    p = os.path.join(out, "EE-004_station3_cleaner.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
