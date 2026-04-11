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


# ─── Registry ─────────────────────────────────────────────────────────────

SYNTHESIZERS: dict[str, Callable[[], object]] = {
    "maxon_ecx_22l": _make_maxon_ecx_22l,
    "maxon_gp22c": _make_maxon_gp22c,
    "lemo_fgg_0b_307": _make_lemo_fgg_0b_307,
    "ati_nano17": _make_ati_nano17,
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
