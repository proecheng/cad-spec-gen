"""
adapters/parts/jinja_primitive_adapter.py — Fallback adapter wrapping the
current `_gen_*` dispatch from codegen/gen_std_parts.py.

This adapter is ALWAYS available and ALWAYS the last-resort fallback. It
preserves the existing simplified-primitive behavior byte-for-byte: the
`_gen_*` functions below are copied verbatim from gen_std_parts.py before the
refactor. Any behavioral change here is a bug.

Behavior:
- `is_available()` always returns True
- `resolve()` returns kind="codegen" with body_code exactly as before
- `probe_dims()` returns the dims that would be passed to _gen_*, so the
  Phase 1 backfill can pre-populate §6.4 with "what the fallback would draw"

This file plus the spec → dims resolution logic (lifted from gen_std_parts.py)
is the *only* piece that must produce byte-identical output for the
regression test in A9.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional

# Ensure project root on sys.path so we can import the existing helpers
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from adapters.parts.base import PartsAdapter


# ─── Category geometry generators (lifted verbatim from gen_std_parts.py) ──
# Do NOT modify these functions without running the byte-identical regression
# test (A9). Any edit that changes the output of _gen_bearing, _gen_motor,
# etc. will break existing projects that rely on the generated code.


def _gen_motor(dims: dict) -> str:
    d = dims.get("d", 22)
    l = dims.get("l", 50)
    sd = dims.get("shaft_d", 4)
    sl = dims.get("shaft_l", 12)
    return f"""    # Simplified motor: cylinder + shaft
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    # Output shaft
    body = body.faces(">Z").workplane().circle({sd/2}).extrude({sl})
    return body"""


def _gen_reducer(dims: dict) -> str:
    d = dims.get("d", 25)
    l = dims.get("l", 35)
    sd = dims.get("shaft_d", 6)
    sl = dims.get("shaft_l", 10)
    return f"""    # Simplified reducer/gearbox: cylinder + output shaft
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    body = body.faces(">Z").workplane().circle({sd/2}).extrude({sl})
    return body"""


def _gen_spring(dims: dict) -> str:
    # Cylindrical mode (e.g. spring pin Φ4×20mm) — when only d/l given,
    # generate a solid pin instead of an annular disc spring.
    if "d" in dims and "l" in dims and "od" not in dims:
        d = dims["d"]
        l = dims["l"]
        return f"""    # Simplified spring pin: solid cylinder
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""
    od = dims.get("od", dims.get("d", 10))
    t = dims.get("t", 0.7)
    h = dims.get("h", dims.get("l", 0.85))
    id_ = dims.get("id", od * 0.5)
    return f"""    # Simplified disc spring: annular ring (stack approximation)
    body = (cq.Workplane("XY")
            .circle({od/2}).circle({id_/2}).extrude({max(t, h)})
            )
    return body"""


def _gen_bearing(dims: dict) -> str:
    od = dims.get("od", 12)
    id_ = dims.get("id", 6)
    w = dims.get("w", 4)
    return f"""    # Simplified bearing: outer ring + inner ring + gap
    outer = cq.Workplane("XY").circle({od/2}).circle({od/2 - 1}).extrude({w})
    inner = cq.Workplane("XY").circle({id_/2 + 1}).circle({id_/2}).extrude({w})
    body = outer.union(inner)
    return body"""


def _gen_sensor(dims: dict) -> str:
    if "d" in dims:
        d = dims["d"]
        l = dims.get("l", 12)
        return f"""    # Simplified sensor: cylinder
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""
    w = dims.get("w", 20)
    h = dims.get("h", 15)
    l = dims.get("l", 12)
    return f"""    # Simplified sensor: box
    body = cq.Workplane("XY").box({w}, {h}, {l}, centered=(True, True, False))
    return body"""


def _gen_pump(dims: dict) -> str:
    w = dims.get("w", 30)
    h = dims.get("h", 25)
    l = dims.get("l", 40)
    return f"""    # Simplified pump: box with port stubs
    body = cq.Workplane("XY").box({w}, {h}, {l}, centered=(True, True, False))
    # Input/output port stubs
    body = body.faces(">X").workplane().center(0, {l/2}).circle(3).extrude(5)
    body = body.faces("<X").workplane().center(0, {l/2}).circle(3).extrude(5)
    return body"""


def _gen_connector(dims: dict) -> str:
    d = dims.get("d", 10)
    l = min(dims.get("l", 25), 50)  # cap for assembly visualization
    if "w" in dims:
        w = dims["w"]
        h = dims.get("h", 3)
        l = min(dims.get("l", 8), 50)
        return f"""    # Simplified flat connector
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    return body"""
    return f"""    # Simplified round connector
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""


def _query_text(query) -> str:
    return f"{getattr(query, 'name_cn', '')} {getattr(query, 'material', '')}"


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


def _parse_pin_count(text: str, default: int = 4) -> int:
    m = re.search(r"(\d+)\s*(?:芯|pin|pins|pos)", text, re.IGNORECASE)
    if not m:
        return default
    return max(1, min(int(float(m.group(1))), 80))


def _parse_trailing_length_mm(text: str, default: float) -> float:
    m = re.search(r"[×xX]\s*(\d+(?:\.\d+)?)\s*mm", text)
    if not m:
        return default
    return float(m.group(1))


def _parse_size_pair_mm(text: str, default: tuple[float, float]) -> tuple[float, float]:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm", text)
    if not matches:
        return default
    w, l = matches[-1]
    return float(w), float(l)


def _parse_array_grid(text: str, default: tuple[int, int] = (4, 4)) -> tuple[int, int]:
    m = re.search(r"(\d+)\s*[×xX]\s*(\d+)\s*薄膜", text)
    if not m:
        return default
    rows = max(1, min(int(m.group(1)), 12))
    cols = max(1, min(int(m.group(2)), 12))
    return rows, cols


def _gen_zif_connector(dims: dict, pins: int) -> str:
    w = dims.get("w", 12)
    l = dims.get("l", 8)
    h = dims.get("h", 3)
    pitch = w / (pins + 1)
    pad_w = max(pitch * 0.45, 0.18)
    pad_l = max(l * 0.18, 0.8)
    actuator_l = max(l * 0.22, 1.0)
    actuator_h = max(h * 0.22, 0.4)
    return f"""    # Semi-parametric ZIF connector: base, flip-lock actuator, contact row
    base = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    actuator = (cq.Workplane("XY")
                .center(0, {l * 0.24})
                .box({w * 0.92}, {actuator_l}, {actuator_h}, centered=(True, True, False))
                .translate((0, 0, {h})))
    body = base.union(actuator)
    for i in range({pins}):
        x = (i - ({pins} - 1) / 2.0) * {pitch}
        pad = (cq.Workplane("XY")
               .center(x, {-l * 0.36})
               .box({pad_w}, {pad_l}, {max(h * 0.08, 0.12)}, centered=(True, True, False))
               .translate((0, 0, {h + 0.03})))
        body = body.union(pad)
    return body"""


def _gen_ffc_ribbon(dims: dict, pins: int, actual_length: float) -> tuple[str, dict]:
    w = dims.get("w", max(8.0, pins * 0.5))
    h = dims.get("h", 1.0)
    visual_l = min(max(actual_length, dims.get("l", 30)), 50)
    end_l = max(4.0, min(8.0, visual_l * 0.08))
    pitch = w / (pins + 1)
    pad_w = max(pitch * 0.45, 0.18)
    code = f"""    # Semi-parametric FFC ribbon: thin cable, end stiffeners, exposed contacts
    ribbon = cq.Workplane("XY").box({w}, {visual_l}, {h}, centered=(True, True, False))
    body = ribbon
    for y in ({-visual_l / 2 + end_l / 2}, {visual_l / 2 - end_l / 2}):
        stiffener = (cq.Workplane("XY")
                     .center(0, y)
                     .box({w + 1.6}, {end_l}, {h + 0.6}, centered=(True, True, False)))
        body = body.union(stiffener)
        for i in range({pins}):
            x = (i - ({pins} - 1) / 2.0) * {pitch}
            pad = (cq.Workplane("XY")
                   .center(x, y)
                   .box({pad_w}, {max(end_l * 0.72, 2.0)}, {max(h * 0.22, 0.15)}, centered=(True, True, False))
                   .translate((0, 0, {h + 0.62})))
            body = body.union(pad)
    return body"""
    return code, {"w": w, "l": visual_l, "h": h}


def _gen_pcb_board(dims: dict) -> str:
    w = dims.get("w", 45)
    l = dims.get("l", 35)
    h = dims.get("h", 1.6)
    return f"""    # Semi-parametric PCB assembly: board, corner holes, ICs, connector pads
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    for x in ({-w * 0.42}, {w * 0.42}):
        for y in ({-l * 0.38}, {l * 0.38}):
            body = body.faces(">Z").workplane().center(x, y).hole({min(w, l) * 0.08})
    main_ic = (cq.Workplane("XY")
               .center({-w * 0.16}, 0)
               .box({w * 0.26}, {l * 0.22}, {max(h * 0.65, 0.8)}, centered=(True, True, False))
               .translate((0, 0, {h})))
    aux_ic = (cq.Workplane("XY")
              .center({w * 0.22}, {l * 0.12})
              .box({w * 0.18}, {l * 0.16}, {max(h * 0.45, 0.6)}, centered=(True, True, False))
              .translate((0, 0, {h})))
    body = body.union(main_ic).union(aux_ic)
    for i in range(8):
        x = (i - 3.5) * {w * 0.07}
        pad = (cq.Workplane("XY")
               .center(x, {-l * 0.42})
               .box({w * 0.035}, {l * 0.08}, {max(h * 0.12, 0.15)}, centered=(True, True, False))
               .translate((0, 0, {h + 0.02})))
        body = body.union(pad)
    return body"""


def _gen_sma_bulkhead(dims: dict) -> str:
    d = dims.get("d", 6.5)
    l = dims.get("l", 15)
    nut_d = max(d * 1.65, 8.0)
    return f"""    # Semi-parametric SMA bulkhead connector: coax barrel, hex nut, center pin
    barrel = cq.Workplane("XY").circle({d / 2}).extrude({l})
    hex_nut = cq.Workplane("XY").polygon(6, {nut_d}).extrude({max(d * 0.38, 2.0)}).translate((0, 0, {l * 0.42}))
    rear_thread = cq.Workplane("XY").circle({d * 0.38}).extrude({l * 0.28}).translate((0, 0, {l}))
    center_pin = cq.Workplane("XY").circle({max(d * 0.08, 0.35)}).extrude({l * 0.18}).translate((0, 0, {-l * 0.18}))
    body = barrel.union(hex_nut).union(rear_thread).union(center_pin)
    return body"""


def _gen_m12_connector(dims: dict, pins: int) -> str:
    d = dims.get("d", 12)
    l = dims.get("l", 18)
    flange_d = max(d * 1.35, 16)
    pin_circle = d * 0.28
    return f"""    # Semi-parametric M12 connector: threaded shell, flange, coded pin face
    shell = cq.Workplane("XY").circle({d / 2}).extrude({l})
    flange = cq.Workplane("XY").polygon(6, {flange_d}).extrude({max(d * 0.22, 2.6)}).translate((0, 0, {l * 0.34}))
    cable_gland = cq.Workplane("XY").circle({d * 0.38}).extrude({l * 0.38}).translate((0, 0, {l}))
    body = shell.union(flange).union(cable_gland)
    for i in range({pins}):
        angle = 6.283185307179586 * i / {pins}
        x = {pin_circle} * __import__("math").cos(angle)
        y = {pin_circle} * __import__("math").sin(angle)
        pin = (cq.Workplane("XY")
               .center(x, y)
               .circle({max(d * 0.035, 0.35)})
               .extrude({max(d * 0.08, 0.8)})
               .translate((0, 0, {l + l * 0.38})))
        body = body.union(pin)
    key = (cq.Workplane("XY")
           .center(0, {-d * 0.28})
           .box({d * 0.16}, {d * 0.36}, {max(d * 0.08, 0.8)}, centered=(True, True, False))
           .translate((0, 0, {l + l * 0.38})))
    body = body.union(key)
    return body"""


def _gen_uhf_sensor(dims: dict) -> str:
    d = dims.get("d", 45)
    l = dims.get("l", 60)
    return f"""    # Semi-parametric UHF sensor: cylindrical body, antenna face, cable exit
    body = cq.Workplane("XY").circle({d / 2}).extrude({l})
    face = cq.Workplane("XY").circle({d * 0.43}).extrude({max(d * 0.04, 1.2)}).translate((0, 0, {l}))
    antenna = (cq.Workplane("XY")
               .box({d * 0.58}, {d * 0.16}, {max(d * 0.04, 1.0)}, centered=(True, True, False))
               .translate((0, 0, {l + max(d * 0.04, 1.2)})))
    cable = (cq.Workplane("YZ")
             .circle({max(d * 0.045, 1.2)})
             .extrude({d * 0.42})
             .translate(({d / 2}, 0, {l * 0.58})))
    body = body.union(face).union(antenna).union(cable)
    return body"""


def _gen_pressure_array(dims: dict, rows: int, cols: int) -> str:
    w = dims.get("w", 20)
    l = dims.get("l", 20)
    h = dims.get("h", 0.6)
    pad = min(w / (cols * 1.8), l / (rows * 1.8))
    pitch_x = w / (cols + 1)
    pitch_y = l / (rows + 1)
    return f"""    # Semi-parametric pressure array: thin film carrier, {rows}x{cols} sensing pads, flex tail
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    for r in range({rows}):
        for c in range({cols}):
            x = (c - ({cols} - 1) / 2.0) * {pitch_x}
            y = (r - ({rows} - 1) / 2.0) * {pitch_y}
            pad = (cq.Workplane("XY")
                   .center(x, y)
                   .box({pad}, {pad}, {max(h * 0.35, 0.18)}, centered=(True, True, False))
                   .translate((0, 0, {h + 0.02})))
            body = body.union(pad)
    tail = (cq.Workplane("XY")
            .center(0, {-l * 0.72})
            .box({w * 0.32}, {l * 0.42}, {h}, centered=(True, True, False)))
    body = body.union(tail)
    return body"""


def _gen_fluid_reservoir(dims: dict) -> str:
    d = dims.get("d", 38)
    l = dims.get("l", 280)
    cap_l = max(min(l * 0.035, 8.0), 3.0)
    band_w = max(min(l * 0.02, 6.0), 2.0)
    boss_d = max(d * 0.24, 5.0)
    return f"""    # Semi-parametric fluid reservoir: cylinder, end caps, clamp bands, fill boss
    body = cq.Workplane("XY").circle({d / 2}).extrude({l})
    for z in ({cap_l}, {l - cap_l - band_w}):
        band = (cq.Workplane("XY")
                .circle({d / 2})
                .circle({max(d / 2 - 1.1, d * 0.42)})
                .extrude({band_w})
                .translate((0, 0, z)))
        body = body.union(band)
    front = cq.Workplane("XY").circle({d * 0.43}).extrude({cap_l})
    rear = cq.Workplane("XY").circle({d * 0.43}).extrude({cap_l}).translate((0, 0, {l - cap_l}))
    fill_boss = (cq.Workplane("XY")
                 .center(0, {d * 0.22})
                 .circle({boss_d / 2})
                 .extrude({max(d * 0.12, 3.0)})
                 .translate((0, 0, {l * 0.55})))
    body = body.union(front).union(rear).union(fill_boss)
    return body"""


def _gen_solvent_cartridge(dims: dict) -> str:
    d = dims.get("d", 25)
    l = dims.get("l", 110)
    cap_l = max(min(l * 0.06, 7.0), 3.0)
    plunger_d = max(d * 0.22, 4.0)
    port_d = max(d * 0.26, 5.0)
    return f"""    # Semi-parametric solvent cartridge: piston tank, seal caps, M8 quick connector
    body = cq.Workplane("XY").circle({d / 2}).extrude({l})
    seal_cap = cq.Workplane("XY").circle({d * 0.48}).extrude({cap_l})
    body = body.union(seal_cap).union(seal_cap.translate((0, 0, {l - cap_l})))
    plunger = (cq.Workplane("XY")
               .circle({plunger_d / 2})
               .extrude({max(l * 0.16, 12.0)})
               .translate((0, 0, {l - max(l * 0.16, 12.0)})))
    m8_port = (cq.Workplane("XY")
               .circle({port_d / 2})
               .extrude({max(d * 0.35, 8.0)})
               .translate((0, 0, 0)))
    body = body.union(plunger).union(m8_port)
    return body"""


def _gen_gear_pump(dims: dict) -> str:
    w = dims.get("w", 30)
    d = dims.get("d", 25)
    h = dims.get("h", 40)
    cover_h = max(h * 0.08, 2.5)
    body_h = max(h - cover_h, h * 0.7)
    gear_r = min(w, d) * 0.18
    port_r = max(min(w, d) * 0.10, 2.2)
    return f"""    # Semi-parametric gear pump: rectangular housing, twin gear cover, port stubs
    body = cq.Workplane("XY").box({w}, {d}, {body_h}, centered=(True, True, False))
    cover = (cq.Workplane("XY")
             .box({w * 0.88}, {d * 0.78}, {cover_h}, centered=(True, True, False))
             .translate((0, 0, {body_h})))
    body = body.union(cover)
    for x in ({-gear_r * 1.15}, {gear_r * 1.15}):
        gear_face = (cq.Workplane("XY")
                     .center(x, 0)
                     .circle({gear_r})
                     .circle({gear_r * 0.34})
                     .extrude({cover_h * 0.65})
                     .translate((0, 0, {h - cover_h * 0.65})))
        body = body.union(gear_face)
    for y in ({-d * 0.30}, {d * 0.30}):
        port = (cq.Workplane("YZ")
                .center(y, {h * 0.52})
                .circle({port_r})
                .extrude({w * 0.22})
                .translate(({w / 2 - w * 0.22}, 0, 0)))
        body = body.union(port)
    return body"""


def _gen_micro_dosing_pump(dims: dict) -> str:
    w = dims.get("w", 20)
    d = dims.get("d", 15)
    h = dims.get("h", 30)
    coil_d = min(w, d) * 0.55
    nozzle_d = max(min(w, d) * 0.16, 2.0)
    return f"""    # Semi-parametric micro dosing pump: solenoid block, valve coil, nozzle pair
    body = cq.Workplane("XY").box({w}, {d}, {h}, centered=(True, True, False))
    coil = (cq.Workplane("XZ")
            .center(0, {h * 0.58})
            .circle({coil_d / 2})
            .extrude({d * 0.39}, both=True))
    body = body.union(coil)
    for x in ({-w * 0.24}, {w * 0.24}):
        nozzle = (cq.Workplane("YZ")
                  .center({-d / 2 + nozzle_d / 2}, {h * 0.18})
                  .circle({nozzle_d / 2})
                  .extrude({w * 0.16}, both=True)
                  .translate((x, 0, 0)))
        body = body.union(nozzle)
    return body"""


def _gen_scraper_head(dims: dict) -> str:
    w = dims.get("w", 15)
    d = dims.get("d", 8)
    h = dims.get("h", 6)
    blade_h = h * 0.55
    return f"""    # Semi-parametric scraper head: clamp bar, compliant blade, mounting holes
    clamp = cq.Workplane("XY").box({w}, {d}, {h * 0.45}, centered=(True, True, False))
    blade = (cq.Workplane("XY")
             .center(0, {-d * 0.20})
             .box({w * 0.92}, {d * 0.42}, {blade_h}, centered=(True, True, False))
             .translate((0, 0, {h * 0.35})))
    body = clamp.union(blade)
    for x in ({-w * 0.30}, {w * 0.30}):
        body = body.faces(">Z").workplane().center(x, 0).hole({max(w * 0.10, 1.2)})
    return body"""


def _gen_cleaning_tape_cassette(dims: dict) -> str:
    w = dims.get("w", 42)
    d = dims.get("d", 28)
    h = dims.get("h", 12)
    base_h = h * 0.42
    reel_h = h - base_h
    reel_r = min(w, d) * 0.18
    return f"""    # Semi-parametric cleaning tape cassette: cassette body, supply/take-up reels, tape path
    body = cq.Workplane("XY").box({w}, {d}, {base_h}, centered=(True, True, False))
    for x in ({-w * 0.23}, {w * 0.23}):
        reel = (cq.Workplane("XY")
                .center(x, 0)
                .circle({reel_r})
                .circle({reel_r * 0.38})
                .extrude({reel_h})
                .translate((0, 0, {base_h})))
        hub = (cq.Workplane("XY")
               .center(x, 0)
               .circle({reel_r * 0.20})
               .extrude({h})
               .translate((0, 0, 0)))
        body = body.union(reel).union(hub)
    tape_span = (cq.Workplane("XY")
                 .box({w * 0.62}, {max(d * 0.07, 1.8)}, {max(h * 0.08, 0.8)}, centered=(True, True, False))
                 .translate((0, 0, {base_h + reel_h * 0.48})))
    window = (cq.Workplane("XY")
              .center(0, {-d * 0.33})
              .box({w * 0.42}, {d * 0.16}, {h * 0.20}, centered=(True, True, False))
              .translate((0, 0, {base_h})))
    body = body.union(tape_span).union(window)
    return body"""


def _gen_spring_pin_assembly(dims: dict) -> str:
    d = dims.get("d", 4)
    l = dims.get("l", 20)
    tip_l = min(max(d * 0.8, 2.0), l * 0.28)
    overlap = min(0.05, tip_l * 0.04)
    stem_l = l - tip_l + overlap
    stem_r = d * 0.44
    tip_r = max(d * 0.10, 0.25)
    collar_l = max(d * 0.28, 0.8)
    return f"""    # Semi-parametric spring pin assembly: pin barrel, tapered nose, retaining collars
    body = cq.Workplane("XY").circle({stem_r}).extrude({stem_l})
    tip = (cq.Workplane("XY")
           .circle({d / 2})
           .workplane(offset={tip_l})
           .circle({tip_r})
           .loft(combine=True)
           .translate((0, 0, {stem_l - overlap})))
    body = body.union(tip)
    for z in (0, {l * 0.30}, {l * 0.62}):
        collar = (cq.Workplane("XY")
                  .circle({d / 2})
                  .extrude({collar_l})
                  .translate((0, 0, z)))
        body = body.union(collar)
    return body"""


def _gen_mini_dc_motor(dims: dict) -> str:
    d = dims.get("d", 16)
    l = dims.get("l", 30)
    shaft_d = dims.get("shaft_d", 2)
    shaft_l = min(dims.get("shaft_l", 8), max(l * 0.18, 3.0))
    rear_l = max(l * 0.08, 1.8)
    front_l = max(l * 0.09, 2.0)
    can_l = l - rear_l - front_l
    terminal_w = max(d * 0.10, 1.2)
    terminal_l = max(d * 0.18, 2.0)
    terminal_h = max(rear_l * 0.35, 0.6)
    return f"""    # Semi-parametric mini DC motor: can, end caps, recessed shaft, rear terminals
    can = cq.Workplane("XY").circle({d / 2}).extrude({can_l}).translate((0, 0, {rear_l}))
    rear = cq.Workplane("XY").circle({d * 0.46}).extrude({rear_l})
    front = cq.Workplane("XY").circle({d * 0.47}).extrude({front_l}).translate((0, 0, {rear_l + can_l}))
    shaft = cq.Workplane("XY").circle({shaft_d / 2}).extrude({shaft_l}).translate((0, 0, {l - shaft_l}))
    body = can.union(rear).union(front).union(shaft)
    for y in ({-d * 0.18}, {d * 0.18}):
        tab = (cq.Workplane("XY")
               .center({d * 0.30}, y)
               .box({terminal_w}, {terminal_l}, {terminal_h}, centered=(True, True, False))
               .translate((0, 0, {rear_l * 0.20})))
        body = body.union(tab)
    return body"""


def _gen_gear_train_reducer(dims: dict) -> str:
    w = dims.get("w", dims.get("d", 25))
    d = dims.get("d", 25)
    h = dims.get("h", dims.get("l", 35))
    shaft_d = dims.get("shaft_d", 6)
    housing_h = h * 0.70
    cover_h = max(h * 0.10, 3.0)
    gear_r = min(w, d) * 0.16
    boss_h = max(h * 0.08, 2.4)
    shaft_h = max(h - housing_h - cover_h - boss_h, h * 0.08)
    shaft_h = min(shaft_h, h * 0.14)
    return f"""    # Semi-parametric gear train reducer: gearbox case, visible gear pair, output boss
    body = cq.Workplane("XY").box({w * 0.86}, {d * 0.72}, {housing_h}, centered=(True, True, False))
    cover = (cq.Workplane("XY")
             .box({w * 0.78}, {d * 0.64}, {cover_h}, centered=(True, True, False))
             .translate((0, 0, {housing_h})))
    body = body.union(cover)
    for x in ({-gear_r * 1.12}, {gear_r * 1.12}):
        gear = (cq.Workplane("XY")
                .center(x, 0)
                .circle({gear_r})
                .circle({gear_r * 0.34})
                .extrude({cover_h * 0.65})
                .translate((0, 0, {housing_h + cover_h * 0.35})))
        body = body.union(gear)
    boss_z = {h} - {shaft_h} - {boss_h}
    boss = cq.Workplane("XY").circle({shaft_d * 0.75}).extrude({boss_h}).translate((0, 0, boss_z))
    shaft = cq.Workplane("XY").circle({shaft_d / 2}).extrude({shaft_h}).translate((0, 0, {h - shaft_h}))
    body = body.union(boss).union(shaft)
    return body"""


def _gen_constant_force_spring(dims: dict) -> str:
    od = dims.get("od", dims.get("d", 10))
    h = dims.get("h", dims.get("t", 0.85))
    inner_d = min(max(dims.get("id", od * 0.5), od * 0.28), od * 0.72)
    strip_w = max(od * 0.16, 1.0)
    return f"""    # Semi-parametric constant force spring: flat coil, hub, restrained strip tail
    coil = (cq.Workplane("XY")
            .circle({od / 2})
            .circle({inner_d / 2})
            .extrude({h}))
    hub = cq.Workplane("XY").circle({inner_d * 0.22}).extrude({h})
    tail = (cq.Workplane("XY")
            .center({od * 0.12}, {-od * 0.22})
            .box({od * 0.54}, {strip_w}, {h}, centered=(True, True, False)))
    body = coil.union(hub).union(tail)
    return body"""


def _gen_photoelectric_encoder(dims: dict) -> str:
    w = dims.get("w", dims.get("d", 15))
    d = dims.get("d", 15)
    h = dims.get("h", dims.get("l", 12))
    base_h = h * 0.52
    face_h = h * 0.14
    lens_h = h * 0.08
    return f"""    # Semi-parametric photoelectric encoder: sensor body, optical window, mounting ears
    body = cq.Workplane("XY").box({w * 0.72}, {d * 0.62}, {base_h}, centered=(True, True, False))
    face = (cq.Workplane("XY")
            .center(0, {d * 0.14})
            .box({w * 0.42}, {d * 0.18}, {face_h}, centered=(True, True, False))
            .translate((0, 0, {base_h})))
    body = body.union(face)
    for x in ({-w * 0.11}, {w * 0.11}):
        lens = (cq.Workplane("XY")
                .center(x, {d * 0.14})
                .circle({w * 0.055})
                .extrude({lens_h})
                .translate((0, 0, {base_h + face_h})))
        body = body.union(lens)
    for x in ({-w * 0.42}, {w * 0.42}):
        ear = (cq.Workplane("XY")
               .center(x, 0)
               .box({w * 0.14}, {d * 0.46}, {base_h * 0.36}, centered=(True, True, False)))
        body = body.union(ear)
    cable = (cq.Workplane("XY")
             .center(0, {-d * 0.38})
             .box({w * 0.34}, {d * 0.16}, {h * 0.28}, centered=(True, True, False)))
    body = body.union(cable)
    return body"""


def _specialized_template(query, dims: dict) -> Optional[dict]:
    """Return a semi-parametric model for high-value fallback rows."""
    text = _query_text(query)
    category = getattr(query, "category", "")

    if category == "connector" and _contains_any(text, ["ZIF", "5052"]):
        pins = _parse_pin_count(text, default=20)
        tpl_dims = dict(dims)
        tpl_dims.setdefault("w", 12)
        tpl_dims.setdefault("l", 8)
        tpl_dims.setdefault("h", 3)
        return {
            "template": "zif_connector",
            "body_code": _gen_zif_connector(tpl_dims, pins),
            "dims": tpl_dims,
            "metadata": {"pins": pins},
        }

    if category == "connector" and _contains_any(text, ["FFC", "15168", "柔性扁平"]):
        pins = _parse_pin_count(text, default=20)
        actual_length = _parse_trailing_length_mm(text, default=dims.get("l", 30))
        body_code, tpl_dims = _gen_ffc_ribbon(dims, pins, actual_length)
        return {
            "template": "ffc_ribbon",
            "body_code": body_code,
            "dims": tpl_dims,
            "metadata": {"pins": pins, "actual_length_mm": actual_length},
        }

    if category == "other" and _contains_any(text, ["PCB", "电路板", "信号调理"]):
        tpl_dims = {"w": 45, "l": 35, "h": 1.6}
        return {
            "template": "pcb_board",
            "body_code": _gen_pcb_board(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "connector" and _contains_any(text, ["SMA"]):
        tpl_dims = dict(dims)
        tpl_dims.setdefault("d", 6.5)
        tpl_dims.setdefault("l", 15)
        return {
            "template": "sma_bulkhead",
            "body_code": _gen_sma_bulkhead(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if (
        category == "other"
        and _contains_any(text, ["M12"])
        and _contains_any(text, ["防水", "接口", "connector"])
    ):
        pins = _parse_pin_count(text, default=4)
        tpl_dims = {"d": 12, "l": 18}
        return {
            "template": "m12_connector",
            "body_code": _gen_m12_connector(tpl_dims, pins),
            "dims": tpl_dims,
            "metadata": {"pins": pins},
        }

    if category == "sensor" and _contains_any(text, ["I300-UHF", "UHF-GT", "UHF"]):
        tpl_dims = dict(dims)
        tpl_dims.setdefault("d", 45)
        tpl_dims.setdefault("l", 60)
        return {
            "template": "uhf_sensor",
            "body_code": _gen_uhf_sensor(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "other" and _contains_any(text, ["压力", "阵列"]):
        rows, cols = _parse_array_grid(text)
        w, l = _parse_size_pair_mm(text, default=(20, 20))
        tpl_dims = {"w": w, "l": l, "h": 0.6}
        return {
            "template": "pressure_array",
            "body_code": _gen_pressure_array(tpl_dims, rows, cols),
            "dims": tpl_dims,
            "metadata": {"rows": rows, "cols": cols},
        }

    if category == "tank" and _contains_any(text, ["溶剂", "活塞", "M8"]):
        tpl_dims = dict(dims)
        tpl_dims.setdefault("d", 25)
        tpl_dims.setdefault("l", 110)
        return {
            "template": "solvent_cartridge",
            "body_code": _gen_solvent_cartridge(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "tank" and _contains_any(text, ["储液罐", "储罐"]):
        tpl_dims = dict(dims)
        tpl_dims.setdefault("d", 38)
        tpl_dims.setdefault("l", 280)
        return {
            "template": "fluid_reservoir",
            "body_code": _gen_fluid_reservoir(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "pump" and _contains_any(text, ["微量泵", "电磁阀"]):
        tpl_dims = {
            "w": dims.get("w", 20),
            "d": dims.get("d", dims.get("h", 15)),
            "h": dims.get("h") if "d" in dims else dims.get("l", 30),
        }
        return {
            "template": "micro_dosing_pump",
            "body_code": _gen_micro_dosing_pump(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "pump" and _contains_any(text, ["齿轮泵"]):
        tpl_dims = {
            "w": dims.get("w", 30),
            "d": dims.get("d", dims.get("h", 25)),
            "h": dims.get("h") if "d" in dims else dims.get("l", 40),
        }
        return {
            "template": "gear_pump",
            "body_code": _gen_gear_pump(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "other" and _contains_any(text, ["刮涂头", "刮胶头", "涂布头"]):
        tpl_dims = {"w": 15, "d": 8, "h": 6}
        return {
            "template": "scraper_head",
            "body_code": _gen_scraper_head(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if (
        category == "other"
        and _contains_any(text, ["清洁带盒"])
        and _contains_any(text, ["供带", "收带", "无纺布"])
    ):
        tpl_dims = {"w": 42, "d": 28, "h": 12}
        return {
            "template": "cleaning_tape_cassette",
            "body_code": _gen_cleaning_tape_cassette(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "spring" and _contains_any(text, ["弹簧销", "锥形头"]):
        tpl_dims = dict(dims)
        tpl_dims.setdefault("d", 4)
        tpl_dims.setdefault("l", 20)
        return {
            "template": "spring_pin_assembly",
            "body_code": _gen_spring_pin_assembly(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "motor" and _contains_any(text, ["微型电机", "DC 3V", "Φ16"]):
        tpl_dims = dict(dims)
        tpl_dims.setdefault("d", 16)
        tpl_dims.setdefault("l", 30)
        return {
            "template": "mini_dc_motor",
            "body_code": _gen_mini_dc_motor(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "reducer" and _contains_any(text, ["齿轮减速", "塑料齿轮", "收带卷轴"]):
        tpl_dims = {
            "w": dims.get("w", dims.get("d", 25)),
            "d": dims.get("d", dims.get("w", 25)),
            "h": dims.get("h", dims.get("l", 35)),
            "shaft_d": dims.get("shaft_d", 6),
        }
        return {
            "template": "gear_train_reducer",
            "body_code": _gen_gear_train_reducer(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "spring" and _contains_any(text, ["恒力弹簧", "供带侧张力", "SUS301"]):
        tpl_dims = dict(dims)
        tpl_dims.setdefault("od", tpl_dims.get("d", 10))
        tpl_dims.setdefault("id", tpl_dims["od"] * 0.5)
        tpl_dims.setdefault("h", tpl_dims.get("t", 0.85))
        return {
            "template": "constant_force_spring",
            "body_code": _gen_constant_force_spring(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    if category == "sensor" and _contains_any(text, ["光电编码器", "反射式"]):
        tpl_dims = {
            "w": dims.get("w", dims.get("d", 15)),
            "d": dims.get("d", dims.get("w", 15)),
            "h": dims.get("h", dims.get("l", 12)),
        }
        return {
            "template": "photoelectric_encoder",
            "body_code": _gen_photoelectric_encoder(tpl_dims),
            "dims": tpl_dims,
            "metadata": {},
        }

    return None


def _gen_seal(dims: dict) -> str:
    od = dims.get("od", 80)
    section_d = dims.get("section_d", 2.4)
    id_ = dims.get("id", od - 2 * section_d)
    r_center = (od + id_) / 4
    return f"""    # Simplified O-ring: torus
    path = cq.Workplane("XY").circle({r_center})
    body = (cq.Workplane("XZ")
            .center({r_center}, 0)
            .circle({section_d/2})
            .sweep(path))
    return body"""


def _gen_tank(dims: dict) -> str:
    d = dims.get("d", 38)
    l = dims.get("l", 280)
    return f"""    # Simplified tank: cylinder with domed ends
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""


def _gen_locating(dims: dict) -> str:
    d = dims.get("d", 3)
    l = dims.get("l", 10)
    chamfer = max(d * 0.1, 0.3)
    return f"""    # Simplified locating pin: cylinder with chamfered tip
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    body = body.faces(">Z").edges().chamfer({chamfer:.3f})
    return body"""


def _gen_elastic(dims: dict) -> str:
    if "d" in dims and "l" in dims:
        d = dims["d"]
        l = dims["l"]
        return f"""    # Simplified elastic part: solid cylinder (rubber spring/damper)
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""
    w = dims.get("w", 20)
    h = dims.get("h", 5)
    l = dims.get("l", 120)
    return f"""    # Simplified elastic part: rectangular block (leaf spring)
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    return body"""


def _gen_transmission(dims: dict) -> str:
    od = dims.get("od", 30)
    w = dims.get("w", 8)
    # 保证内孔半径 < 外圆半径，防止 CadQuery 崩溃（内孔直径上限 = 外径 90%）
    id_ = min(dims.get("id", 6), od * 0.9)
    return f"""    # Simplified gear: solid disc with shaft hole
    body = (cq.Workplane("XY")
            .circle({od/2}).circle({id_/2}).extrude({w}))
    return body"""


def _gen_generic(dims: dict) -> str:
    """Generic block for parts that don't match a specialized category.

    Used for things like 阻尼垫 (damping pad), 配重块 (counterweight), 压力阵列
    (pressure array) which are real physical parts that show up in BOM and
    chains but have no obvious geometric category. Without a generic
    fallback, the assembly validator reports gaps where these should be.
    """
    if "d" in dims and "l" in dims:
        return f"""    # Generic cylindrical block
    body = cq.Workplane("XY").circle({dims['d']/2}).extrude({dims['l']})
    return body"""
    w = dims.get("w", 20)
    h = dims.get("h", 5)
    l = dims.get("l", dims.get("d", 20))
    return f"""    # Generic rectangular block
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    return body"""


_GENERATORS = {
    "motor":        _gen_motor,
    "reducer":      _gen_reducer,
    "spring":       _gen_spring,
    "bearing":      _gen_bearing,
    "sensor":       _gen_sensor,
    "pump":         _gen_pump,
    "connector":    _gen_connector,
    "seal":         _gen_seal,
    "tank":         _gen_tank,
    "locating":     _gen_locating,
    "elastic":      _gen_elastic,
    "transmission": _gen_transmission,
    "other":        _gen_generic,
}

# Categories to skip (too small or too complex for simplified geometry).
_SKIP_CATEGORIES = {"fastener", "cable"}


def _resolve_dims_from_spec_envelope_or_lookup(query) -> Optional[dict]:
    """Reproduce the original dims-resolution logic from gen_std_parts.py.

    Order:
      0. If query.spec_envelope is set BUT granularity is NOT "part_envelope"
         (i.e. it's a station_constraint or component-level envelope),
         REJECT and fall through to lookup — station constraints describe
         an outer bounding box that multiple parts must fit inside, NOT
         the size of an individual part. This enforcement is the last
         step of the six-step granularity chain from the walker spec.
      1. If query.spec_envelope is set AND granularity is "part_envelope",
         convert (w,d,h) → dims dict
      2. Else call lookup_std_part_dims(name, material, category)
      3. Else for category="other", use a small default block
      4. Else return None (caller should skip)
    """
    from cad_spec_defaults import lookup_std_part_dims

    if query.spec_envelope is not None:
        granularity = getattr(query, "spec_envelope_granularity", "part_envelope")
        if granularity == "part_envelope":
            w, d, h = query.spec_envelope
            if abs(w - d) < 0.1:  # cylindrical
                return {"d": w, "l": h}
            else:
                return {"w": w, "d": d, "h": h}
        else:
            # station_constraint / component — do NOT size an individual part.
            import logging
            logging.getLogger("jinja_primitive_adapter").debug(
                "spec_envelope for %s has granularity=%s; deferring to lookup",
                query.part_no, granularity,
            )

    dims = lookup_std_part_dims(query.name_cn, query.material, query.category)
    if dims:
        return dims

    # "other" parts always need a file because gen_assembly.py imports them
    if query.category == "other":
        return {"d": 15, "l": 10}

    return None


# ─── The adapter class itself ──────────────────────────────────────────────


class JinjaPrimitiveAdapter(PartsAdapter):
    """Always-available fallback that reproduces pre-refactor behavior.

    This adapter exists so that the refactor of gen_std_parts.py into the
    resolver architecture is behaviorally identical when no parts_library.yaml
    is present.
    """

    name = "jinja_primitive"

    def is_available(self) -> tuple[bool, Optional[str]]:
        return True, None

    def can_resolve(self, query) -> bool:
        if query.category in _SKIP_CATEGORIES:
            return False
        return query.category in _GENERATORS

    def resolve(self, query, spec: dict, mode: str = "codegen"):
        # Import ResolveResult lazily to avoid circular import during package
        # init (parts_resolver.py → default_resolver → adapters.parts → here)
        from parts_resolver import ResolveResult

        if query.category in _SKIP_CATEGORIES:
            return ResolveResult.skip(
                reason=f"{query.category} category: no geometry generated"
            )

        gen_func = _GENERATORS.get(query.category)
        if gen_func is None:
            return ResolveResult.miss()

        dims = _resolve_dims_from_spec_envelope_or_lookup(query)
        if dims is None:
            return ResolveResult.miss()

        template = _specialized_template(query, dims)
        if template is not None:
            tpl_dims = template["dims"]
            metadata = {
                "dims": tpl_dims,
                "template": template["template"],
            }
            metadata.update(template.get("metadata", {}))
            return ResolveResult(
                status="hit",
                kind="codegen",
                adapter=self.name,
                body_code=template["body_code"],
                real_dims=self._dims_to_envelope(tpl_dims),
                source_tag=f"jinja_template:{template['template']}",
                geometry_source="JINJA_TEMPLATE",
                geometry_quality="C",
                requires_model_review=True,
                metadata=metadata,
            )

        body_code = gen_func(dims)
        return ResolveResult(
            status="hit",
            kind="codegen",
            adapter=self.name,
            body_code=body_code,
            real_dims=self._dims_to_envelope(dims),
            source_tag=f"jinja_primitive:{query.category}",
            metadata={"dims": dims},  # preserved for legacy header format
        )

    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        """Return (w, d, h) as the jinja adapter would draw it.

        Used by Phase 1 backfill to pre-populate §6.4 for parts where the
        only information source is classify_part + lookup_std_part_dims.
        Same dims the _gen_* function would consume.
        """
        if query.category in _SKIP_CATEGORIES:
            return None
        dims = _resolve_dims_from_spec_envelope_or_lookup(query)
        if dims is None:
            return None
        template = _specialized_template(query, dims)
        if template is not None:
            return self._dims_to_envelope(template["dims"])
        return self._dims_to_envelope(dims)

    @staticmethod
    def _dims_to_envelope(dims: dict) -> Optional[tuple]:
        """Best-effort conversion of a _gen_* dims dict to a (w, d, h) tuple."""
        if "d" in dims and "l" in dims and "od" not in dims:
            return (dims["d"], dims["d"], dims["l"])
        if "od" in dims:
            h = dims.get("h", dims.get("l", dims.get("w", dims.get("t", 5))))
            return (dims["od"], dims["od"], h)
        if "w" in dims and "d" in dims and "h" in dims and "l" not in dims:
            return (dims["w"], dims["d"], dims["h"])
        if "w" in dims and "h" in dims and "l" in dims:
            return (dims["w"], dims["d"] if "d" in dims else dims["l"],
                    dims["h"])
        if "w" in dims and "l" in dims:
            return (dims["w"],
                    dims.get("d", dims["w"]),
                    dims.get("h", 20))
        return None
