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

Adding a new vendor part:
  1. Write a `make_xxx()` factory that returns a cq.Workplane with the right
     envelope (datasheet dimensions). Small artistic touches (chamfers, cable
     tabs) help renders read correctly but are not required.
  2. Register it in the `SYNTHESIZERS` dict below.
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
    # Default cache layout — mirrors the mappings shipped in
    # parts_library.default.yaml so the two files stay in lockstep.
    default_paths = {
        "maxon_ecx_22l": "maxon/ecx_22l.step",
        "maxon_gp22c": "maxon/gp22c.step",
        "lemo_fgg_0b_307": "lemo/fgg_0b_307.step",
        "ati_nano17": "ati/nano17.step",
    }
    results: dict[str, Path] = {}
    for fid, rel in default_paths.items():
        path = synthesize_to_cache(fid, rel, overwrite=overwrite)
        if path is not None:
            results[fid] = path
    return results
