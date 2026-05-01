"""
adapters/parts/vendor_synthesizer.py — Skill-level vendor STEP synthesizer.

This module is the canonical home for the parametric stand-ins the skill ships
for well-known vendor parts (Maxon motors/gearheads, LEMO connectors, ATI force
sensors, …). It exposes a registry of factory functions keyed by a short ID
(`maxon_gp22c`, `lemo_fgg_0b_307`, …) and a `synthesize_to_cache(...)` helper
that writes the STEP into the shared cache at `~/.cad-spec-gen/step_cache/`.

The motivation (addressed in v2.8.2-dev): prior to this module, the three
factories lived in `tools/synthesize_demo_step_files.py` with a hard-coded
GISBOT output path, and every project had to hand-write a `parts_library.yaml`
+ populate its own `std_parts/` directory. That meant new users with only a
design document could not exercise the parts_library code path at all.

With this module:
  1. `parts_library.default.yaml` ships vendor mappings that point at shared
     cache paths (e.g. `maxon/gp22c.step` resolved against
     `~/.cad-spec-gen/step_cache/`).
  2. `step_pool_adapter.resolve()` sees the `synthesizer:` field in the spec,
     finds the matching factory here, and writes the STEP to the cache on
     first use. Subsequent runs hit the cached file.
  3. Projects remain untouched: no intermediate products are created inside
     the project directory.

Real vendor STEP files should always be preferred over these parametric
stand-ins. Users can drop a real file at the same cache path (or into a
project-local `std_parts/` directory) and the adapter will use it instead —
the cache write is skipped whenever the file already exists.

Factory vocabulary:
  maxon_ecx_22l      Maxon ECX SPEED 22L brushless motor (Φ22×68 mm)
  maxon_gp22c        Maxon GP22C 53:1 planetary gearhead (Φ22×35 mm + Φ6 shaft)
  lemo_fgg_0b_307    LEMO FGG.0B.307 7-pin push-pull plug (Φ8.6×37 mm)
  ati_nano17         ATI Nano17 6-axis force/torque sensor (Φ17×14.5 mm)
  belleville_din2093_a6
                      DIN 2093 A6 conical spring washer
  spring_pin_4x20     Spring pin assembly, 4 mm × 20 mm with conical head
  molex_15168_ffc_20p Molex 15168-style 20-pin FFC ribbon display segment
  molex_zif_5052xx    Molex 5052xx-style ZIF connector
  reservoir_38x280    Stainless cylindrical fluid reservoir
  tungsten_slug_12x7  Tungsten counterweight slug, 12 mm × 7 mm
  tungsten_slug_14x13 Tungsten counterweight slug, 14 mm × 13 mm
  gear_pump_30x25x40  Compact gear pump visual stand-in
  scraper_head_20x10x8
                      Silicone scraper head with clamp and blade
  damping_pad_20x20   Viscoelastic damping puck, Φ20 × 20 mm
  pressure_array_4x4_20mm
                      Thin-film 4×4 pressure sensing array
  cleaning_tape_cassette_42x28x12
                      Twin-reel cleaning tape cassette
  dc_motor_16x30      Micro DC motor, Φ16 × 30 mm
  gear_train_reducer_25x25x35
                      Plastic gear train reducer visual stand-in
  cushion_pad_20x15x5 Elastomer cushion pad
  constant_force_spring_10mm
                      Flat constant-force spring visual stand-in
  photoelectric_encoder_15x15x12
                      Reflective photoelectric encoder
  solvent_cartridge_25x110
                      Piston solvent cartridge with M8 port
  micro_dosing_pump_20x15x30
                      Solenoid micro dosing pump
  i300_uhf_gt         I300-UHF-GT cylindrical UHF sensor
  signal_conditioning_pcb_45x35
                      4-layer signal-conditioning PCB assembly
  sma_bulkhead_50ohm  SMA bulkhead connector
  m12_4pin_bulkhead   M12 4-pin waterproof bulkhead connector
  kfl001_flange_bearing
                      KFL001 12 mm two-bolt flange bearing unit
  gt2_20t_timing_pulley
                      GT2 20-tooth timing pulley, 16 mm OD x 8 mm wide
  gt2_310_6mm_timing_belt
                      GT2 310 mm closed timing belt visual loop, 6 mm wide
  l070_clamping_coupling
                      L070 split clamping coupling, Φ25 × 30 mm

Adding a new vendor part:
  1. Write a `make_xxx()` factory that returns a cq.Workplane with the right
     envelope (datasheet dimensions). Small artistic touches (chamfers, cable
     tabs) help renders read correctly but are not required.
  2. Register it in the `SYNTHESIZERS` and `DEFAULT_STEP_FILES` dicts below.
  3. Add the matching rule to `parts_library.default.yaml` with:
         adapter: step_pool
         spec: {file: "<vendor>/<model>.step", synthesizer: "<factory_id>"}
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Callable, Optional

__all__ = [
    "SYNTHESIZERS",
    "DEFAULT_STEP_FILES",
    "CACHE_ROOT_ENV",
    "default_cache_root",
    "resolve_cache_path",
    "synthesize_to_cache",
    "list_factory_ids",
]


# ─── Shared cache root ────────────────────────────────────────────────────

CACHE_ROOT_ENV = "CAD_SPEC_GEN_STEP_CACHE"
_DEFAULT_CACHE_REL = ".cad-spec-gen/step_cache"


def default_cache_root() -> Path:
    """Return the shared cache root, honoring the override env var."""
    override = os.environ.get(CACHE_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / _DEFAULT_CACHE_REL).resolve()


def resolve_cache_path(relative: str) -> Path:
    """Join a vendor-relative path (e.g. `maxon/gp22c.step`) to the cache root."""
    return default_cache_root() / relative


# ─── Factory functions ────────────────────────────────────────────────────
#
# Each factory returns a cadquery.Workplane the synthesizer can export via
# cq.exporters.export(obj, path). The factories use `cadquery` lazily so
# importing this module (e.g. from step_pool_adapter's code path) does not
# pay the cadquery startup cost unless synthesis actually runs.


def _make_maxon_ecx_22l():
    """Maxon ECX SPEED 22L brushless DC motor, 60 W class.

    Datasheet (Maxon part 473797):
      - Body diameter: 22 mm
      - Body length: 68 mm (without shaft)
      - Output shaft: Φ4 × 12 mm
      - Mounting flange on the output end: Φ24 × 2 mm disc with 4×M3 holes
        (we skip the holes; the envelope matches)
    """
    import cadquery as cq

    body_d, body_l = 22.0, 68.0
    shaft_d, shaft_l = 4.0, 12.0
    flange_d, flange_t = 24.0, 2.0

    flange = cq.Workplane("XY").circle(flange_d / 2).extrude(flange_t)
    body = (cq.Workplane("XY")
            .workplane(offset=flange_t)
            .circle(body_d / 2)
            .extrude(body_l))
    shaft = (cq.Workplane("XY")
             .workplane(offset=flange_t + body_l)
             .circle(shaft_d / 2)
             .extrude(shaft_l))

    assembly = flange.union(body).union(shaft)
    try:
        assembly = assembly.faces(">Z").edges(">Z").chamfer(0.5)
    except Exception:
        pass
    return assembly


def _make_maxon_gp22c():
    """Maxon GP22C planetary gearhead, 53:1 ratio.

    Datasheet (Maxon part 110364):
      - Body diameter: 22 mm
      - Body length: 35 mm (excluding output shaft)
      - Output shaft: Φ6 × 12 mm
      - Input flange: Φ24 × 1 mm thin disc (mates with motor)
    """
    import cadquery as cq

    body_d, body_l = 22.0, 35.0
    shaft_d, shaft_l = 6.0, 12.0
    flange_d, flange_t = 24.0, 1.0

    flange = cq.Workplane("XY").circle(flange_d / 2).extrude(flange_t)
    body = (cq.Workplane("XY")
            .workplane(offset=flange_t)
            .circle(body_d / 2)
            .extrude(body_l))
    shaft = (cq.Workplane("XY")
             .workplane(offset=flange_t + body_l)
             .circle(shaft_d / 2)
             .extrude(shaft_l))

    assembly = flange.union(body).union(shaft)
    try:
        assembly = assembly.faces(">Z").edges(">Z").chamfer(0.5)
    except Exception:
        pass
    return assembly


def _make_lemo_fgg_0b_307():
    """LEMO FGG.0B.307.CLAD52 push-pull plug, 7-pin.

    Datasheet:
      - Knurled grip body: Φ8.6 × 18 mm
      - Hex collet section: 6 mm flats × 8 mm long
      - Cable strain relief tail: Φ5 × 9 mm
      - Total length ≈ 37 mm
    """
    import cadquery as cq

    grip_d, grip_l = 8.6, 18.0
    hex_flats, hex_l = 6.0, 8.0
    tail_d, tail_l = 5.0, 9.0

    hex_r = hex_flats / math.cos(math.radians(30))
    hex_collet = cq.Workplane("XY").polygon(6, hex_r).extrude(hex_l)

    grip = (cq.Workplane("XY")
            .workplane(offset=hex_l)
            .circle(grip_d / 2)
            .extrude(grip_l))

    tail = (cq.Workplane("XY")
            .workplane(offset=hex_l + grip_l)
            .circle(tail_d / 2)
            .extrude(tail_l))

    # Connector pin face — small Φ4 protrusion under the hex collet
    pin_face = (cq.Workplane("XY")
                .workplane(offset=-2.0)
                .circle(2.0)
                .extrude(2.0))

    body = pin_face.union(hex_collet).union(grip).union(tail)
    try:
        body = body.faces(">Z").edges(">Z").chamfer(0.3)
    except Exception:
        pass
    return body


def _make_ati_nano17():
    """ATI Industrial Automation Nano17 6-axis force/torque sensor.

    Datasheet:
      - Sensing body: Φ17 × 14.5 mm
      - Top relief pocket: Φ12 × 0.5 mm (cable connector recess)
      - Cable exit tab: 3 × 6 × 4 mm rectangular boss on one side
    """
    import cadquery as cq

    body_d, body_h = 17.0, 14.5
    relief_d, relief_t = 12.0, 0.5

    body = cq.Workplane("XY").circle(body_d / 2).extrude(body_h)
    body = (body.faces(">Z").workplane()
            .circle(relief_d / 2).cutBlind(-relief_t))

    tab_w, tab_d, tab_h = 3.0, 6.0, 4.0
    tab = (cq.Workplane("XY")
           .center(body_d / 2 + tab_d / 2 - 1, 0)
           .workplane(offset=body_h / 2 - tab_h / 2)
           .box(tab_d, tab_w, tab_h, centered=(True, True, False)))
    body = body.union(tab)

    try:
        body = body.faces("<Z").edges("<Z").chamfer(0.5)
    except Exception:
        pass
    return body


def _make_belleville_din2093_a6():
    """DIN 2093 A6 Belleville spring washer visual stand-in."""
    import cadquery as cq

    outer_bottom_r, outer_top_r = 6.25, 5.65
    inner_bottom_r, inner_top_r = 3.15, 3.75
    height = 0.85

    outer = (
        cq.Workplane("XY")
        .circle(outer_bottom_r)
        .workplane(offset=height)
        .circle(outer_top_r)
        .loft(combine=True)
    )
    inner = (
        cq.Workplane("XY")
        .circle(inner_bottom_r)
        .workplane(offset=height)
        .circle(inner_top_r)
        .loft(combine=True)
    )
    washer = outer.cut(inner)
    try:
        washer = washer.edges().chamfer(0.08)
    except Exception:
        pass
    return washer


def _make_spring_pin_4x20():
    """Spring pin assembly, 4 mm body by 20 mm overall length."""
    import cadquery as cq

    shaft = cq.Workplane("XY").circle(2.0).extrude(16.0)
    head = (
        cq.Workplane("XY")
        .workplane(offset=16.0)
        .circle(2.0)
        .workplane(offset=4.0)
        .circle(1.25)
        .loft(combine=True)
    )
    slot = (
        cq.Workplane("XY")
        .center(0, 0)
        .workplane(offset=2.0)
        .box(0.55, 4.8, 12.0, centered=(True, True, False))
    )
    pin = shaft.union(head).cut(slot)

    # Small external spring cue: three narrow collars on the pin body.
    for z in (4.0, 7.0, 10.0):
        collar = cq.Workplane("XY").workplane(offset=z).circle(2.25).extrude(0.35)
        bore = cq.Workplane("XY").workplane(offset=z - 0.05).circle(1.98).extrude(0.45)
        pin = pin.union(collar.cut(bore))
    try:
        pin = pin.faces(">Z").edges(">Z").chamfer(0.18)
    except Exception:
        pass
    return pin


def _make_molex_15168_ffc_20p():
    """Molex 15168-style 20-pin FFC ribbon display segment."""
    import cadquery as cq

    length, width, thick = 50.0, 12.0, 0.45
    ribbon = cq.Workplane("XY").box(length, width, thick, centered=(True, True, False))

    # Reinforcement tabs at both visible ends.
    for x in (-length / 2 + 4.0, length / 2 - 4.0):
        tab = (
            cq.Workplane("XY")
            .center(x, 0)
            .box(7.0, width + 1.0, 0.35, centered=(True, True, False))
        )
        ribbon = ribbon.union(tab)

    # Twenty contact traces near one end.
    pitch = width / 21.0
    for i in range(20):
        y = -width / 2 + pitch * (i + 1)
        trace = (
            cq.Workplane("XY")
            .center(length / 2 - 5.5, y)
            .box(7.5, 0.18, 0.18, centered=(True, True, False))
        )
        ribbon = ribbon.union(trace)
    return ribbon


def _make_molex_zif_5052xx():
    """Molex 5052xx-style low-profile ZIF connector."""
    import cadquery as cq

    base = cq.Workplane("XY").box(18.0, 5.2, 2.0, centered=(True, True, False))
    latch = (
        cq.Workplane("XY")
        .center(0, 2.4)
        .box(18.5, 1.0, 1.0, centered=(True, True, False))
        .translate((0, 0, 1.6))
    )
    connector = base.union(latch)

    pitch = 16.0 / 19.0
    for i in range(20):
        x = -8.0 + pitch * i
        pad = (
            cq.Workplane("XY")
            .center(x, -2.9)
            .box(0.28, 1.4, 0.18, centered=(True, True, False))
            .translate((0, 0, 0.1))
        )
        connector = connector.union(pad)
    try:
        connector = connector.edges("|Z").chamfer(0.12)
    except Exception:
        pass
    return connector


def _make_reservoir_38x280():
    """Stainless steel fluid reservoir, 38 mm diameter by 280 mm length."""
    import cadquery as cq

    body = cq.Workplane("XY").circle(19.0).extrude(280.0)
    for z in (0.0, 280.0):
        cap = cq.Workplane("XY").workplane(offset=z).circle(20.0).extrude(1.6)
        body = body.union(cap)

    neck = (
        cq.Workplane("YZ")
        .center(0, 235.0)
        .circle(4.0)
        .extrude(16.0)
        .translate((19.0, 0, 0))
    )
    port = (
        cq.Workplane("YZ")
        .center(0, 235.0)
        .circle(2.5)
        .extrude(18.0)
        .translate((18.2, 0, 0))
    )
    body = body.union(neck.cut(port))
    try:
        body = body.faces(">Z").edges(">Z").chamfer(0.6)
    except Exception:
        pass
    return body


def _make_tungsten_slug(diameter: float, height: float):
    """Dense cylindrical tungsten counterweight with chamfer and center mark."""
    import cadquery as cq

    slug = cq.Workplane("XY").circle(diameter / 2).extrude(height)
    slug = slug.faces(">Z").workplane().circle(diameter * 0.18).cutBlind(-0.35)
    try:
        slug = slug.edges("|Z").chamfer(0.35)
    except Exception:
        pass
    return slug


def _make_tungsten_slug_12x7():
    """Tungsten counterweight slug, 12 mm diameter by 7 mm high."""
    return _make_tungsten_slug(12.0, 7.0)


def _make_tungsten_slug_14x13():
    """Tungsten counterweight slug, 14 mm diameter by 13 mm high."""
    return _make_tungsten_slug(14.0, 13.0)


def _make_gear_pump_30x25x40():
    """Compact gear pump envelope, 30 × 25 × 40 mm."""
    import cadquery as cq

    body = cq.Workplane("XY").box(30.0, 25.0, 36.8, centered=(True, True, False))
    cover = (
        cq.Workplane("XY")
        .box(26.4, 19.5, 3.2, centered=(True, True, False))
        .translate((0, 0, 36.8))
    )
    pump = body.union(cover)

    for x in (-5.2, 5.2):
        gear_face = (
            cq.Workplane("XY")
            .center(x, 0)
            .circle(4.5)
            .circle(1.5)
            .extrude(2.1)
            .translate((0, 0, 37.9))
        )
        pump = pump.union(gear_face)

    for y in (-7.5, 7.5):
        port = (
            cq.Workplane("YZ")
            .center(y, 20.8)
            .circle(2.5)
            .extrude(6.6)
            .translate((8.4, 0, 0))
        )
        pump = pump.union(port)
    return pump


def _make_scraper_head_20x10x8():
    """Silicone scraper head with clamp bar and compliant blade."""
    import cadquery as cq

    clamp = cq.Workplane("XY").box(20.0, 10.0, 3.0, centered=(True, True, False))
    blade = (
        cq.Workplane("XY")
        .center(0, -2.0)
        .box(18.0, 4.2, 5.0, centered=(True, True, False))
        .translate((0, 0, 3.0))
    )
    head = clamp.union(blade)
    for x in (-6.0, 6.0):
        head = head.faces(">Z").workplane().center(x, 0).hole(1.7)
    try:
        head = head.edges("|Z").chamfer(0.25)
    except Exception:
        pass
    return head


def _make_damping_pad_20x20():
    """Viscoelastic rubber damping puck, Φ20 × 20 mm."""
    import cadquery as cq

    pad = cq.Workplane("XY").circle(10.0).extrude(20.0)
    for r in (4.0, 6.6, 8.4):
        rib = (
            cq.Workplane("XY")
            .circle(r)
            .circle(max(r - 0.8, 0.1))
            .extrude(0.75)
            .translate((0, 0, 19.25))
        )
        pad = pad.union(rib)
    try:
        pad = pad.edges("|Z").chamfer(0.25)
    except Exception:
        pass
    return pad


def _make_pressure_array_4x4_20mm():
    """Thin-film 4×4 pressure sensing array, 20 × 20 mm."""
    import cadquery as cq

    array = cq.Workplane("XY").box(20.0, 20.0, 0.6, centered=(True, True, False))
    for row in range(4):
        for col in range(4):
            x = (col - 1.5) * 4.0
            y = (row - 1.5) * 4.0
            pad = (
                cq.Workplane("XY")
                .center(x, y)
                .box(2.8, 2.8, 0.22, centered=(True, True, False))
                .translate((0, 0, 0.6))
            )
            array = array.union(pad)
    tail = (
        cq.Workplane("XY")
        .center(0, -14.4)
        .box(6.4, 8.4, 0.6, centered=(True, True, False))
    )
    return array.union(tail)


def _make_cleaning_tape_cassette_42x28x12():
    """Twin-reel cleaning tape cassette, 42 × 28 × 12 mm."""
    import cadquery as cq

    cassette = cq.Workplane("XY").box(42.0, 28.0, 5.0, centered=(True, True, False))
    for x in (-9.7, 9.7):
        reel = (
            cq.Workplane("XY")
            .center(x, 0)
            .circle(5.0)
            .circle(1.9)
            .extrude(7.0)
            .translate((0, 0, 5.0))
        )
        hub = (
            cq.Workplane("XY")
            .center(x, 0)
            .circle(1.0)
            .extrude(12.0)
        )
        cassette = cassette.union(reel).union(hub)

    tape_span = (
        cq.Workplane("XY")
        .box(26.0, 2.0, 1.0, centered=(True, True, False))
        .translate((0, 0, 8.4))
    )
    window = (
        cq.Workplane("XY")
        .center(0, -9.2)
        .box(17.6, 4.5, 2.4, centered=(True, True, False))
        .translate((0, 0, 5.0))
    )
    return cassette.union(tape_span).union(window)


def _make_dc_motor_16x30():
    """Micro DC motor, Φ16 × 30 mm including front shaft cue."""
    import cadquery as cq

    can = cq.Workplane("XY").circle(8.0).extrude(24.9).translate((0, 0, 2.4))
    rear = cq.Workplane("XY").circle(7.35).extrude(2.4)
    front = cq.Workplane("XY").circle(7.5).extrude(2.7).translate((0, 0, 27.3))
    shaft = cq.Workplane("XY").circle(1.0).extrude(5.4).translate((0, 0, 24.6))
    motor = can.union(rear).union(front).union(shaft)
    for y in (-2.9, 2.9):
        tab = (
            cq.Workplane("XY")
            .center(4.8, y)
            .box(1.6, 2.9, 0.85, centered=(True, True, False))
            .translate((0, 0, 0.5))
        )
        motor = motor.union(tab)
    return motor


def _make_gear_train_reducer_25x25x35():
    """Plastic gear train reducer, 25 × 25 × 35 mm."""
    import cadquery as cq

    reducer = cq.Workplane("XY").box(21.5, 18.0, 24.5, centered=(True, True, False))
    cover = (
        cq.Workplane("XY")
        .box(19.5, 16.0, 3.5, centered=(True, True, False))
        .translate((0, 0, 24.5))
    )
    reducer = reducer.union(cover)
    for x in (-4.5, 4.5):
        gear = (
            cq.Workplane("XY")
            .center(x, 0)
            .circle(4.0)
            .circle(1.4)
            .extrude(2.3)
            .translate((0, 0, 25.7))
        )
        reducer = reducer.union(gear)
    boss = cq.Workplane("XY").circle(4.5).extrude(2.8).translate((0, 0, 28.0))
    shaft = cq.Workplane("XY").circle(3.0).extrude(4.2).translate((0, 0, 30.8))
    return reducer.union(boss).union(shaft)


def _make_cushion_pad_20x15x5():
    """Elastomer cushion pad with raised compliance ribs."""
    import cadquery as cq

    pad = cq.Workplane("XY").box(20.0, 15.0, 3.1, centered=(True, True, False))
    for x in (-4.8, 0.0, 4.8):
        rib = (
            cq.Workplane("XY")
            .center(x, 0)
            .box(3.2, 12.3, 1.9, centered=(True, True, False))
            .translate((0, 0, 3.1))
        )
        pad = pad.union(rib)
    try:
        pad = pad.edges("|Z").chamfer(0.2)
    except Exception:
        pass
    return pad


def _make_constant_force_spring_10mm():
    """Flat constant-force spring visual stand-in, Φ10 mm."""
    import cadquery as cq

    coil = cq.Workplane("XY").circle(5.0).circle(2.5).extrude(0.85)
    hub = cq.Workplane("XY").circle(1.1).extrude(0.85)
    tail = (
        cq.Workplane("XY")
        .center(1.2, -2.2)
        .box(5.4, 1.6, 0.85, centered=(True, True, False))
    )
    return coil.union(hub).union(tail)


def _make_photoelectric_encoder_15x15x12():
    """Reflective photoelectric encoder with lens pair and mounting ears."""
    import cadquery as cq

    encoder = cq.Workplane("XY").box(10.8, 9.3, 6.2, centered=(True, True, False))
    face = (
        cq.Workplane("XY")
        .center(0, 2.1)
        .box(6.3, 2.7, 1.7, centered=(True, True, False))
        .translate((0, 0, 6.2))
    )
    encoder = encoder.union(face)
    for x in (-1.65, 1.65):
        lens = (
            cq.Workplane("XY")
            .center(x, 2.1)
            .circle(0.82)
            .extrude(0.95)
            .translate((0, 0, 7.9))
        )
        encoder = encoder.union(lens)
    for x in (-6.3, 6.3):
        ear = cq.Workplane("XY").center(x, 0).box(2.1, 6.9, 2.25, centered=(True, True, False))
        encoder = encoder.union(ear)
    cable = cq.Workplane("XY").center(0, -5.7).box(5.1, 2.4, 3.4, centered=(True, True, False))
    return encoder.union(cable)


def _make_solvent_cartridge_25x110():
    """Piston solvent cartridge, Φ25 × 110 mm with M8 quick port."""
    import cadquery as cq

    cartridge = cq.Workplane("XY").circle(12.5).extrude(110.0)
    seal_cap = cq.Workplane("XY").circle(12.0).extrude(6.6)
    cartridge = cartridge.union(seal_cap).union(seal_cap.translate((0, 0, 103.4)))
    plunger = cq.Workplane("XY").circle(2.75).extrude(17.6).translate((0, 0, 92.4))
    m8_port = cq.Workplane("XY").circle(3.25).extrude(8.75)
    return cartridge.union(plunger).union(m8_port)


def _make_micro_dosing_pump_20x15x30():
    """Solenoid micro dosing pump, 20 × 15 × 30 mm."""
    import cadquery as cq

    pump = cq.Workplane("XY").box(20.0, 15.0, 30.0, centered=(True, True, False))
    coil = cq.Workplane("XZ").center(0, 17.4).circle(4.1).extrude(5.85, both=True)
    pump = pump.union(coil)
    for x in (-4.8, 4.8):
        nozzle = (
            cq.Workplane("YZ")
            .center(-6.3, 5.4)
            .circle(1.2)
            .extrude(3.2, both=True)
            .translate((x, 0, 0))
        )
        pump = pump.union(nozzle)
    return pump


def _make_i300_uhf_gt():
    """I300-UHF-GT cylindrical UHF sensor, Φ45 × 60 mm."""
    import cadquery as cq

    sensor = cq.Workplane("XY").circle(22.5).extrude(60.0)
    face = cq.Workplane("XY").circle(19.35).extrude(1.8).translate((0, 0, 60.0))
    antenna = (
        cq.Workplane("XY")
        .box(26.1, 7.2, 1.8, centered=(True, True, False))
        .translate((0, 0, 61.8))
    )
    cable = cq.Workplane("YZ").circle(2.0).extrude(18.9).translate((22.5, 0, 34.8))
    return sensor.union(face).union(antenna).union(cable)


def _make_signal_conditioning_pcb_45x35():
    """4-layer mixed-signal PCB assembly, 45 × 35 mm."""
    import cadquery as cq

    pcb = cq.Workplane("XY").box(45.0, 35.0, 1.6, centered=(True, True, False))
    for x in (-18.9, 18.9):
        for y in (-13.3, 13.3):
            pcb = pcb.faces(">Z").workplane().center(x, y).hole(2.8)
    main_ic = (
        cq.Workplane("XY")
        .center(-7.2, 0)
        .box(11.7, 7.7, 1.05, centered=(True, True, False))
        .translate((0, 0, 1.6))
    )
    aux_ic = (
        cq.Workplane("XY")
        .center(9.9, 4.2)
        .box(8.1, 5.6, 0.72, centered=(True, True, False))
        .translate((0, 0, 1.6))
    )
    pcb = pcb.union(main_ic).union(aux_ic)
    for i in range(8):
        x = (i - 3.5) * 3.15
        pad = (
            cq.Workplane("XY")
            .center(x, -14.7)
            .box(1.6, 2.8, 0.2, centered=(True, True, False))
            .translate((0, 0, 1.62))
        )
        pcb = pcb.union(pad)
    return pcb


def _make_sma_bulkhead_50ohm():
    """SMA 50 Ω bulkhead connector visual stand-in."""
    import cadquery as cq

    barrel = cq.Workplane("XY").circle(3.25).extrude(15.0)
    hex_nut = cq.Workplane("XY").polygon(6, 10.7).extrude(2.5).translate((0, 0, 6.3))
    rear_thread = cq.Workplane("XY").circle(2.5).extrude(4.2).translate((0, 0, 15.0))
    center_pin = cq.Workplane("XY").circle(0.52).extrude(2.7).translate((0, 0, -2.7))
    return barrel.union(hex_nut).union(rear_thread).union(center_pin)


def _make_m12_4pin_bulkhead():
    """M12 4-pin waterproof diagnostic connector."""
    import cadquery as cq

    shell = cq.Workplane("XY").circle(6.0).extrude(18.0)
    flange = cq.Workplane("XY").polygon(6, 16.2).extrude(2.6).translate((0, 0, 6.1))
    gland = cq.Workplane("XY").circle(4.55).extrude(6.8).translate((0, 0, 18.0))
    connector = shell.union(flange).union(gland)
    for i in range(4):
        angle = 2 * math.pi * i / 4
        x = 3.36 * math.cos(angle)
        y = 3.36 * math.sin(angle)
        pin = (
            cq.Workplane("XY")
            .center(x, y)
            .circle(0.42)
            .extrude(0.95)
            .translate((0, 0, 24.8))
        )
        connector = connector.union(pin)
    key = (
        cq.Workplane("XY")
        .center(0, -3.36)
        .box(1.9, 4.3, 0.95, centered=(True, True, False))
        .translate((0, 0, 24.8))
    )
    return connector.union(key)


def _make_kfl001_flange_bearing():
    """KFL001 12 mm two-bolt flange bearing unit.

    Common catalog dimensions:
      - Overall flange envelope: 63 x 38 x 16 mm
      - Bore: 12 mm
      - Mounting hole center distance: 48 mm
      - Mounting holes: approx. 7 mm clearance
    """
    import cadquery as cq

    length, width, total_h = 63.0, 38.0, 16.0
    bore_d = 12.0
    hole_spacing = 48.0
    mount_hole_d = 7.0
    base_t = 5.4

    # Flattened diamond flange with enough real envelope signal for render and
    # assembly checks. The STEP cache path promotes this out of codegen fallback.
    flange_outline = [
        (-length / 2, 0.0),
        (-hole_spacing / 2, -width / 2),
        (hole_spacing / 2, -width / 2),
        (length / 2, 0.0),
        (hole_spacing / 2, width / 2),
        (-hole_spacing / 2, width / 2),
    ]
    body = cq.Workplane("XY").polyline(flange_outline).close().extrude(base_t)
    try:
        body = body.edges("|Z").fillet(1.2)
    except Exception:
        pass

    lower_boss = (
        cq.Workplane("XY")
        .circle(17.0)
        .extrude(5.8)
        .translate((0, 0, base_t))
    )
    bearing_insert = (
        cq.Workplane("XY")
        .circle(13.0)
        .extrude(total_h - base_t)
        .translate((0, 0, base_t))
    )
    top_lip = (
        cq.Workplane("XY")
        .circle(14.2)
        .circle(8.0)
        .extrude(1.5)
        .translate((0, 0, total_h - 1.5))
    )
    body = body.union(lower_boss).union(bearing_insert).union(top_lip)

    bore = (
        cq.Workplane("XY")
        .circle(bore_d / 2)
        .extrude(total_h + 1.0)
        .translate((0, 0, -0.5))
    )
    body = body.cut(bore)

    for x in (-hole_spacing / 2, hole_spacing / 2):
        recess = (
            cq.Workplane("XY")
            .center(x, 0)
            .circle(5.4)
            .extrude(2.0)
            .translate((0, 0, base_t - 1.9))
        )
        hole = (
            cq.Workplane("XY")
            .center(x, 0)
            .circle(mount_hole_d / 2)
            .extrude(base_t + 1.0)
            .translate((0, 0, -0.5))
        )
        body = body.cut(recess).cut(hole)

    # Small locking screw cue on the bearing insert, visible in close renders.
    screw = (
        cq.Workplane("YZ")
        .center(0, base_t + 6.0)
        .circle(1.15)
        .extrude(5.0)
        .translate((11.0, 0, 0))
    )
    body = body.cut(screw)

    try:
        body = body.edges("|Z").chamfer(0.25)
    except Exception:
        pass
    return body


def _make_gt2_20t_timing_pulley():
    """GT2 20-tooth timing pulley for the lifting platform drivetrain.

    Project display dimensions follow the existing parametric template:
      - Overall visual envelope: 16 x 16 x 8 mm
      - Tooth count: 20
      - GT2 20T pitch diameter is about 12.7 mm
      - Bore display diameter: 6.35 mm
    """
    import cadquery as cq

    od, width = 16.0, 8.0
    bore_d = 6.35
    base_r = 7.18
    tooth_depth = 0.82
    tooth_w = 1.15
    tooth_h = 5.4
    tooth_z = (width - tooth_h) / 2.0

    body = cq.Workplane("XY").circle(base_r).circle(bore_d / 2.0).extrude(width)

    # Thin flanges at both sides keep the rendered silhouette recognizable as a
    # timing pulley while preserving the 16 mm maximum envelope.
    bottom_flange = cq.Workplane("XY").circle(od / 2.0).circle(bore_d / 2.0).extrude(0.7)
    top_flange = (
        cq.Workplane("XY")
        .circle(od / 2.0)
        .circle(bore_d / 2.0)
        .extrude(0.7)
        .translate((0, 0, width - 0.7))
    )
    hub = (
        cq.Workplane("XY")
        .circle(5.4)
        .circle(bore_d / 2.0)
        .extrude(width)
    )
    body = body.union(bottom_flange).union(top_flange).union(hub)

    tooth_center_r = base_r + tooth_depth / 2.0 - 0.05
    for i in range(20):
        angle = i * 18.0
        tooth = (
            cq.Workplane("XY")
            .box(tooth_depth, tooth_w, tooth_h, centered=(True, True, False))
            .translate((tooth_center_r, 0, tooth_z))
            .rotate((0, 0, 0), (0, 0, 1), angle)
        )
        body = body.union(tooth)

    # Side grub screw cue; this is intentionally shallow visual geometry, not a
    # manufacturing-ready thread model.
    screw = (
        cq.Workplane("YZ")
        .center(0, width / 2.0)
        .circle(1.25)
        .extrude(od + 1.0, both=True)
        .translate((0, 0, 0))
    )
    body = body.cut(screw)

    try:
        body = body.faces(">Z").edges(">Z").chamfer(0.18)
        body = body.faces("<Z").edges("<Z").chamfer(0.18)
    except Exception:
        pass
    return body


def _make_gt2_310_6mm_timing_belt():
    """GT2-310-6 mm closed belt loop for drivetrain visualization.

    The CAD_SPEC-derived visual envelope is 170 x 80 x 6 mm. The actual belt
    pitch length is 310 mm; this stand-in represents the installed loop around
    the two pulley centers rather than a free circular belt.
    """
    import cadquery as cq

    outer_w, outer_d, height = 170.0, 80.0, 6.0
    belt_t = 4.0
    inner_w = outer_w - 2.0 * belt_t
    inner_d = outer_d - 2.0 * belt_t

    body = (
        cq.Workplane("XY")
        .ellipse(outer_w / 2.0, outer_d / 2.0)
        .ellipse(inner_w / 2.0, inner_d / 2.0)
        .extrude(height)
    )

    # Small inner tooth cues along the straight runs. They sit inside the belt
    # envelope so the reported bbox stays aligned with the project spec.
    for y in (inner_d / 2.0 + 0.55, -(inner_d / 2.0 + 0.55)):
        for i in range(25):
            x = -72.0 + i * 6.0
            tooth = (
                cq.Workplane("XY")
                .center(x, y)
                .box(2.1, 1.15, 0.75, centered=(True, True, False))
                .translate((0, 0, height - 0.75))
            )
            body = body.union(tooth)

    seam = (
        cq.Workplane("XY")
        .center(0, outer_d / 2.0 - 1.6)
        .box(9.0, 1.2, 0.35, centered=(True, True, False))
        .translate((0, 0, height - 0.35))
    )
    body = body.union(seam)

    try:
        body = body.edges("|Z").chamfer(0.12)
    except Exception:
        pass
    return body


def _make_l070_clamping_coupling():
    """L070 split clamping coupling, 25 mm diameter by 30 mm long.

    Project CAD_SPEC dimensions:
      - Outside diameter: 25 mm
      - Overall length: 30 mm
      - Bore display diameter: 6.35 mm
      - Two 15 mm clamp sections with split slots and radial clamp screws
    """
    import cadquery as cq

    d, length = 25.0, 30.0
    bore_d = 6.35
    r = d / 2.0
    screw_d = 3.5

    body = cq.Workplane("XY").circle(r).circle(bore_d / 2.0).extrude(length)

    # Two clamp relief grooves give the plain cylinder a recognizable
    # two-ended coupling silhouette without changing the reported envelope.
    for z in (8.4, 20.4):
        groove = (
            cq.Workplane("XY")
            .circle(r + 0.05)
            .circle(r - 0.8)
            .extrude(1.8)
            .translate((0, 0, z))
        )
        body = body.cut(groove)

    # Axial split slots on opposite sides, one per clamp section.
    for zc in (7.5, 22.5):
        slot = (
            cq.Workplane("YZ")
            .center(0, zc)
            .box(3.0, d + 1.0, 11.0, centered=(True, True, True))
            .translate((r - 1.2, 0, 0))
        )
        body = body.cut(slot)

    # Radial clamp screw holes crossing each split section.
    for zc in (7.5, 22.5):
        screw = (
            cq.Workplane("YZ")
            .center(0, zc)
            .circle(screw_d / 2.0)
            .extrude(d + 2.0, both=True)
        )
        body = body.cut(screw)

    try:
        body = body.faces(">Z").edges(">Z").chamfer(0.35)
        body = body.faces("<Z").edges("<Z").chamfer(0.35)
    except Exception:
        pass
    return body


# ─── Registry ─────────────────────────────────────────────────────────────

SYNTHESIZERS: dict[str, Callable[[], object]] = {
    "maxon_ecx_22l": _make_maxon_ecx_22l,
    "maxon_gp22c": _make_maxon_gp22c,
    "lemo_fgg_0b_307": _make_lemo_fgg_0b_307,
    "ati_nano17": _make_ati_nano17,
    "belleville_din2093_a6": _make_belleville_din2093_a6,
    "spring_pin_4x20": _make_spring_pin_4x20,
    "molex_15168_ffc_20p": _make_molex_15168_ffc_20p,
    "molex_zif_5052xx": _make_molex_zif_5052xx,
    "reservoir_38x280": _make_reservoir_38x280,
    "tungsten_slug_12x7": _make_tungsten_slug_12x7,
    "tungsten_slug_14x13": _make_tungsten_slug_14x13,
    "gear_pump_30x25x40": _make_gear_pump_30x25x40,
    "scraper_head_20x10x8": _make_scraper_head_20x10x8,
    "damping_pad_20x20": _make_damping_pad_20x20,
    "pressure_array_4x4_20mm": _make_pressure_array_4x4_20mm,
    "cleaning_tape_cassette_42x28x12": _make_cleaning_tape_cassette_42x28x12,
    "dc_motor_16x30": _make_dc_motor_16x30,
    "gear_train_reducer_25x25x35": _make_gear_train_reducer_25x25x35,
    "cushion_pad_20x15x5": _make_cushion_pad_20x15x5,
    "constant_force_spring_10mm": _make_constant_force_spring_10mm,
    "photoelectric_encoder_15x15x12": _make_photoelectric_encoder_15x15x12,
    "solvent_cartridge_25x110": _make_solvent_cartridge_25x110,
    "micro_dosing_pump_20x15x30": _make_micro_dosing_pump_20x15x30,
    "i300_uhf_gt": _make_i300_uhf_gt,
    "signal_conditioning_pcb_45x35": _make_signal_conditioning_pcb_45x35,
    "sma_bulkhead_50ohm": _make_sma_bulkhead_50ohm,
    "m12_4pin_bulkhead": _make_m12_4pin_bulkhead,
    "kfl001_flange_bearing": _make_kfl001_flange_bearing,
    "gt2_20t_timing_pulley": _make_gt2_20t_timing_pulley,
    "gt2_310_6mm_timing_belt": _make_gt2_310_6mm_timing_belt,
    "l070_clamping_coupling": _make_l070_clamping_coupling,
}

# Default cache layout — mirrors parts_library.default.yaml so tests and
# batch warmup can assert the two files stay in lockstep.
DEFAULT_STEP_FILES: dict[str, str] = {
    "maxon_ecx_22l": "maxon/ecx_22l.step",
    "maxon_gp22c": "maxon/gp22c.step",
    "lemo_fgg_0b_307": "lemo/fgg_0b_307.step",
    "ati_nano17": "ati/nano17.step",
    "belleville_din2093_a6": "mechanical/belleville_din2093_a6.step",
    "spring_pin_4x20": "mechanical/spring_pin_4x20.step",
    "molex_15168_ffc_20p": "molex/15168_ffc_20p.step",
    "molex_zif_5052xx": "molex/zif_5052xx.step",
    "reservoir_38x280": "process/reservoir_38x280.step",
    "tungsten_slug_12x7": "weights/tungsten_slug_12x7.step",
    "tungsten_slug_14x13": "weights/tungsten_slug_14x13.step",
    "gear_pump_30x25x40": "process/gear_pump_30x25x40.step",
    "scraper_head_20x10x8": "process/scraper_head_20x10x8.step",
    "damping_pad_20x20": "elastomer/damping_pad_20x20.step",
    "pressure_array_4x4_20mm": "sensors/pressure_array_4x4_20mm.step",
    "cleaning_tape_cassette_42x28x12": (
        "process/cleaning_tape_cassette_42x28x12.step"
    ),
    "dc_motor_16x30": "motors/dc_motor_16x30.step",
    "gear_train_reducer_25x25x35": (
        "transmission/gear_train_reducer_25x25x35.step"
    ),
    "cushion_pad_20x15x5": "elastomer/cushion_pad_20x15x5.step",
    "constant_force_spring_10mm": "mechanical/constant_force_spring_10mm.step",
    "photoelectric_encoder_15x15x12": (
        "sensors/photoelectric_encoder_15x15x12.step"
    ),
    "solvent_cartridge_25x110": "process/solvent_cartridge_25x110.step",
    "micro_dosing_pump_20x15x30": "process/micro_dosing_pump_20x15x30.step",
    "i300_uhf_gt": "sensors/i300_uhf_gt.step",
    "signal_conditioning_pcb_45x35": (
        "electronics/signal_conditioning_pcb_45x35.step"
    ),
    "sma_bulkhead_50ohm": "connectors/sma_bulkhead_50ohm.step",
    "m12_4pin_bulkhead": "connectors/m12_4pin_bulkhead.step",
    "kfl001_flange_bearing": "mechanical/kfl001_flange_bearing.step",
    "gt2_20t_timing_pulley": "transmission/gt2_20t_timing_pulley.step",
    "gt2_310_6mm_timing_belt": "transmission/gt2_310_6mm_timing_belt.step",
    "l070_clamping_coupling": "transmission/l070_clamping_coupling.step",
}


def list_factory_ids() -> list[str]:
    """Return the sorted list of registered factory IDs."""
    return sorted(SYNTHESIZERS.keys())


# ─── Public synthesis helper ──────────────────────────────────────────────


def synthesize_to_cache(
    factory_id: str,
    relative_path: str,
    overwrite: bool = False,
) -> Optional[Path]:
    """Synthesize a vendor STEP file into the shared cache.

    Parameters
    ----------
    factory_id : str
        Registered factory ID in `SYNTHESIZERS` (e.g. `"maxon_gp22c"`).
    relative_path : str
        Cache-relative path where the STEP should be written, e.g.
        `"maxon/gp22c.step"`. Subdirectories are created as needed.
    overwrite : bool
        If False (default), skip synthesis when the file already exists.

    Returns
    -------
    Path | None
        The absolute path to the written STEP on success, or None if the
        factory is not registered or synthesis failed. Errors are logged
        to stderr but never raised — callers fall through to jinja_primitive.
    """
    factory = SYNTHESIZERS.get(factory_id)
    if factory is None:
        return None

    target = resolve_cache_path(relative_path)
    if target.exists() and not overwrite:
        return target

    try:
        import cadquery as cq
    except ImportError:
        # cadquery is a hard dependency for codegen; if it's missing the
        # caller already has bigger problems. Fail quietly.
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        obj = factory()
        cq.exporters.export(obj, str(target))
    except Exception as exc:
        # Clean up a half-written file so a retry starts fresh.
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
        import sys
        print(
            f"[vendor_synthesizer] failed to synthesize {factory_id} → "
            f"{target}: {exc}",
            file=sys.stderr,
        )
        return None

    return target


def synthesize_all_to_cache(overwrite: bool = False) -> dict[str, Path]:
    """Synthesize every registered vendor part into the shared cache.

    Intended as a bootstrap / warmup helper for CLI use. Returns a dict
    mapping factory_id → cached path for every successful synthesis.
    """
    results: dict[str, Path] = {}
    for fid, rel in DEFAULT_STEP_FILES.items():
        path = synthesize_to_cache(fid, rel, overwrite=overwrite)
        if path is not None:
            results[fid] = path
    return results
