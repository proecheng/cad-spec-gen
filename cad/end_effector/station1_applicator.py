"""
Station 1 (0°) — Coupling Agent Applicator Module (GIS-EE-002)

Per §4.1.2 (lines 110–119):
- Body shell 60×40×55mm (Al 7075-T6) with internal pump cavity
- Silicone grease tank Φ38×280mm (stainless steel), M14 threaded cap
- Gear pump cavity Φ20×25mm
- Scraper head slot 15×10×5mm (silicone rubber, replaceable)
- NTC sensor bore Φ3.5×15mm
- LEMO 0B bore Φ9.4mm on side
- Mounting base 40×40mm with 4×M3 + Φ3 pin
- Total ~400g

BOM: GIS-EE-002-01 壳体, 002-02 储罐, 002-03 齿轮泵, 002-04 刮涂头, 002-05 LEMO
"""

import cadquery as cq
import math
from params import (
    S1_BODY_W, S1_BODY_D, S1_BODY_H, S1_WALL_THICK,
    S1_TANK_OD, S1_TANK_ID, S1_TANK_LENGTH, S1_TANK_CAP_THREAD,
    S1_PUMP_CAVITY_DIA, S1_PUMP_CAVITY_DEPTH,
    S1_SCRAPER_W, S1_SCRAPER_H, S1_SCRAPER_D,
    S1_NTC_BORE_DIA, S1_NTC_BORE_DEPTH,
    MOUNT_FACE, MOUNT_BOLT_PCD, MOUNT_BOLT_DIA,
    MOUNT_PIN_DIA, MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y,
    LEMO_BORE_DIA,
)


def _mounting_holes(wp: cq.Workplane, thickness: float) -> cq.Workplane:
    """Cut standard 40×40 mounting holes into workplane at Z=0."""
    half_s = MOUNT_BOLT_PCD / 2.0
    for dx, dy in [(half_s/2, half_s/2), (half_s/2, -half_s/2),
                   (-half_s/2, half_s/2), (-half_s/2, -half_s/2)]:
        h = cq.Workplane("XY").center(dx, dy).circle(MOUNT_BOLT_DIA / 2.0).extrude(thickness)
        wp = wp.cut(h)
    pin = cq.Workplane("XY").center(MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y).circle(MOUNT_PIN_DIA / 2.0).extrude(thickness)
    wp = wp.cut(pin)
    return wp


def make_applicator_body() -> cq.Workplane:
    """GIS-EE-002-01: Shell body 60×40×55mm with internal cavities."""
    # Outer shell
    body = cq.Workplane("XY").box(S1_BODY_W, S1_BODY_D, S1_BODY_H, centered=(True, True, False))

    # Hollow interior
    cavity = (
        cq.Workplane("XY")
        .workplane(offset=S1_WALL_THICK)
        .box(S1_BODY_W - 2*S1_WALL_THICK, S1_BODY_D - 2*S1_WALL_THICK,
             S1_BODY_H - 2*S1_WALL_THICK, centered=(True, True, False))
    )
    body = body.cut(cavity)

    # Pump cavity (cylindrical bore in front wall)
    pump = (
        cq.Workplane("XZ")
        .workplane(offset=-S1_BODY_D / 2.0)
        .center(0, S1_BODY_H * 0.6)
        .circle(S1_PUMP_CAVITY_DIA / 2.0)
        .extrude(S1_PUMP_CAVITY_DEPTH)
    )
    body = body.cut(pump)

    # Scraper slot at bottom (opening in bottom face)
    scraper_slot = (
        cq.Workplane("XY")
        .center(0, -S1_BODY_D / 2.0 + S1_SCRAPER_D / 2.0 + S1_WALL_THICK)
        .box(S1_SCRAPER_W + 1, S1_SCRAPER_D + 1, S1_WALL_THICK + 0.1,
             centered=(True, True, False))
    )
    body = body.cut(scraper_slot)

    # Tank bore (through +Y side wall for radial tank insertion)
    # Per §4.1.2 L176: tank axis is radial (∥XY plane, along +Y悬臂方向)
    tank_bore = (
        cq.Workplane("XZ")
        .workplane(offset=S1_BODY_D / 2.0 - S1_WALL_THICK - 0.1)
        .center(0, S1_BODY_H * 0.5)
        .circle(S1_TANK_OD / 2.0 + 0.5)
        .extrude(S1_WALL_THICK + 0.2)
    )
    body = body.cut(tank_bore)

    # NTC sensor bore
    ntc = (
        cq.Workplane("YZ")
        .workplane(offset=S1_BODY_W / 2.0)
        .center(0, S1_BODY_H * 0.4)
        .circle(S1_NTC_BORE_DIA / 2.0)
        .extrude(-S1_NTC_BORE_DEPTH)
    )
    body = body.cut(ntc)

    # LEMO connector bore Φ9.4mm
    lemo = (
        cq.Workplane("YZ")
        .workplane(offset=-S1_BODY_W / 2.0)
        .center(0, S1_BODY_H * 0.7)
        .circle(LEMO_BORE_DIA / 2.0)
        .extrude(S1_WALL_THICK + 1)
    )
    body = body.cut(lemo)

    # Mounting face bolt holes (through bottom plate)
    body = _mounting_holes(body, S1_WALL_THICK)

    return body


def make_tank() -> cq.Workplane:
    """GIS-EE-002-02: Silicone grease tank Φ38×280mm stainless steel."""
    tank = cq.Workplane("XY").circle(S1_TANK_OD / 2.0).extrude(S1_TANK_LENGTH)
    inner = (
        cq.Workplane("XY")
        .workplane(offset=2.0)
        .circle(S1_TANK_ID / 2.0)
        .extrude(S1_TANK_LENGTH - 4.0)
    )
    tank = tank.cut(inner)

    # M14 cap boss
    cap = (
        cq.Workplane("XY")
        .workplane(offset=S1_TANK_LENGTH)
        .circle(S1_TANK_CAP_THREAD / 2.0 + 3.0)
        .circle(S1_TANK_CAP_THREAD / 2.0)
        .extrude(8.0)
    )
    tank = tank.union(cap)

    # Outlet port at bottom
    outlet = (
        cq.Workplane("XY")
        .circle(3.0)
        .extrude(-5.0)
    )
    tank = tank.union(outlet)

    return tank


def make_gear_pump() -> cq.Workplane:
    """GIS-EE-002-03: Gear pump (simplified as cylinder with ports)."""
    pump = cq.Workplane("XY").circle(S1_PUMP_CAVITY_DIA / 2.0 - 0.5).extrude(S1_PUMP_CAVITY_DEPTH - 2)

    # Inlet port on top
    inlet = cq.Workplane("XY").workplane(offset=S1_PUMP_CAVITY_DEPTH - 2).circle(2.0).extrude(5.0)
    pump = pump.union(inlet)

    # Outlet port on bottom
    outlet = cq.Workplane("XY").circle(2.0).extrude(-5.0)
    pump = pump.union(outlet)

    return pump


def make_scraper() -> cq.Workplane:
    """GIS-EE-002-04: Silicone rubber scraper head."""
    scraper = cq.Workplane("XY").box(S1_SCRAPER_W, S1_SCRAPER_D, S1_SCRAPER_H,
                                     centered=(True, True, False))
    # Round the working edge
    scraper = scraper.edges("|Z and >Y").fillet(1.5)
    return scraper


def make_lemo_plug() -> cq.Workplane:
    """GIS-EE-002-05: LEMO 0B connector (simplified)."""
    body = cq.Workplane("XY").circle(LEMO_BORE_DIA / 2.0 - 0.3).extrude(20.0)
    # Flange
    flange = cq.Workplane("XY").circle(LEMO_BORE_DIA / 2.0 + 1.5).extrude(3.0)
    body = body.union(flange)
    return body


def make_applicator() -> cq.Workplane:
    """
    Full applicator assembly.
    Origin at mounting face center, Z+ = away from flange (into workspace).
    """
    # Body at Z=0
    body = make_applicator_body()

    # Tank extending upward from body top (along +Z, radially outward in assembly)
    tank = make_tank().translate((0, 0, S1_BODY_H))

    # Gear pump inside body
    pump = make_gear_pump().translate((0, -S1_BODY_D / 2.0 + S1_PUMP_CAVITY_DEPTH / 2.0,
                                       S1_BODY_H * 0.6 - S1_PUMP_CAVITY_DIA / 2.0))

    # Scraper at bottom
    scraper = make_scraper().translate((0, -S1_BODY_D / 2.0 + S1_SCRAPER_D / 2.0 + S1_WALL_THICK,
                                        -S1_SCRAPER_H))

    result = body.union(tank).union(pump).union(scraper)
    return result


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_applicator()
    p = os.path.join(out, "EE-002_station1_applicator.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
