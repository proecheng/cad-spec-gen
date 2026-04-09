#!/usr/bin/env python3
"""
synthesize_demo_step_files.py — Generate demo vendor STEP files for the
GISBOT end_effector parts library.

These are NOT real vendor STEP files. They are dimensionally accurate
parametric stand-ins built from publicly known datasheet dimensions, used
to demonstrate the StepPoolAdapter routing path on the GISBOT project
without shipping copyrighted vendor files in the test fixtures.

Real STEP files from the vendor websites should always replace these:
  - Maxon GP22C reducer:    https://www.maxongroup.com/maxon/view/product/353273
  - LEMO FGG.0B.307 plug:   https://www.lemo.com/en/products/series/fgg-0b
  - ATI Nano17 force sensor: https://www.ati-ia.com/products/ft/ft_models.aspx?id=Nano17

Usage:
    python tools/synthesize_demo_step_files.py [--out PROJECT_ROOT/std_parts]

Each part is built as a recognizable shape with the right overall envelope:
the build pipeline cares about bbox, the 3D viewer cares about silhouette.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cadquery as cq


def make_maxon_gp22c() -> cq.Workplane:
    """Maxon GP22C planetary gearhead, 53:1 ratio.

    Datasheet (Maxon part 110364):
      - Body diameter: 22 mm
      - Body length: 35 mm (excluding output shaft)
      - Output shaft: Φ6 × 12 mm
      - Mounting flange: Φ24 × 1 mm thin disc on the input side (to motor)
    """
    body_d, body_l = 22.0, 35.0
    shaft_d, shaft_l = 6.0, 12.0
    flange_d, flange_t = 24.0, 1.0

    # Input flange (mates with motor)
    flange = cq.Workplane("XY").circle(flange_d / 2).extrude(flange_t)

    # Main body cylinder
    body = (cq.Workplane("XY")
            .workplane(offset=flange_t)
            .circle(body_d / 2)
            .extrude(body_l))

    # Output shaft
    shaft = (cq.Workplane("XY")
             .workplane(offset=flange_t + body_l)
             .circle(shaft_d / 2)
             .extrude(shaft_l))

    # Slight chamfer on the output end for visual realism
    body_with_shaft = flange.union(body).union(shaft)
    try:
        body_with_shaft = (body_with_shaft.faces(">Z")
                           .edges(">Z")
                           .chamfer(0.5))
    except Exception:
        pass

    return body_with_shaft


def make_lemo_fgg_0b() -> cq.Workplane:
    """LEMO FGG.0B.307.CLAD52 push-pull plug, 7-pin.

    Datasheet:
      - Body diameter: 8.6 mm (knurled grip section)
      - Total length: 35 mm
      - Hex collet section: 6 mm flats × 8 mm long
      - Cable strain relief: Φ5 × 10 mm tail
    """
    grip_d, grip_l = 8.6, 18.0
    hex_flats, hex_l = 6.0, 8.0
    tail_d, tail_l = 5.0, 9.0

    # Hex collet at the connector end
    import math
    hex_r = hex_flats / math.cos(math.radians(30))  # circumradius
    hex_collet = (cq.Workplane("XY")
                  .polygon(6, hex_r)
                  .extrude(hex_l))

    # Knurled grip cylinder above the hex
    grip = (cq.Workplane("XY")
            .workplane(offset=hex_l)
            .circle(grip_d / 2)
            .extrude(grip_l))

    # Cable strain-relief tail
    tail = (cq.Workplane("XY")
            .workplane(offset=hex_l + grip_l)
            .circle(tail_d / 2)
            .extrude(tail_l))

    # Connector face on the bottom — small Φ4 protrusion (insulator + pins)
    pin_face = (cq.Workplane("XY")
                .workplane(offset=-2.0)
                .circle(4.0 / 2)
                .extrude(2.0))

    body = pin_face.union(hex_collet).union(grip).union(tail)
    try:
        body = body.faces(">Z").edges(">Z").chamfer(0.3)
    except Exception:
        pass
    return body


def make_ati_nano17() -> cq.Workplane:
    """ATI Industrial Automation Nano17 6-axis force/torque sensor.

    Datasheet:
      - Sensing body diameter: 17 mm
      - Sensing body height: 14.5 mm
      - Mounting flange: Φ17 × 2 mm at the base, with a Φ12 × 0.5 mm
        relieved center
      - Cable exit: small Φ3 × 5 mm tab on one side
    """
    body_d, body_h = 17.0, 14.5
    relief_d, relief_t = 12.0, 0.5

    # Main sensing cylinder
    body = cq.Workplane("XY").circle(body_d / 2).extrude(body_h)

    # Top relief pocket (cable connector recess)
    body = (body.faces(">Z").workplane()
            .circle(relief_d / 2).cutBlind(-relief_t))

    # Side cable exit tab — small rectangular boss
    tab_w, tab_d, tab_h = 3.0, 6.0, 4.0
    tab = (cq.Workplane("XY")
           .center(body_d / 2 + tab_d / 2 - 1, 0)
           .workplane(offset=body_h / 2 - tab_h / 2)
           .box(tab_d, tab_w, tab_h, centered=(True, True, False)))
    body = body.union(tab)

    # Slight bottom chamfer
    try:
        body = body.faces("<Z").edges("<Z").chamfer(0.5)
    except Exception:
        pass

    return body


PARTS = [
    ("maxon/gp22c.step", make_maxon_gp22c, "Maxon GP22C 53:1 reducer"),
    ("lemo/fgg_0b_307.step", make_lemo_fgg_0b, "LEMO FGG.0B.307 plug"),
    ("ati/nano17.step", make_ati_nano17, "ATI Nano17 6-axis F/T sensor"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="D:/Work/cad-tests/GISBOT/std_parts",
        help="Output root for STEP files (default: GISBOT std_parts/)",
    )
    args = parser.parse_args()
    out_root = Path(args.out)

    print(f"Synthesizing demo vendor STEP files into: {out_root}")
    print()

    for rel, factory, desc in PARTS:
        target = out_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        body = factory()
        cq.exporters.export(body, str(target))
        bb = body.val().BoundingBox()
        span = (bb.xmax - bb.xmin, bb.ymax - bb.ymin, bb.zmax - bb.zmin)
        print(f"  + {rel}")
        print(f"      {desc}")
        print(f"      bbox span: {span[0]:.1f} x {span[1]:.1f} x {span[2]:.1f} mm")
        print()

    print(f"Done. {len(PARTS)} STEP files generated.")
    print()
    print("Next: add these to the project parts_library.yaml:")
    for rel, _, desc in PARTS:
        print(f"  - {desc:40s} → {rel}")


if __name__ == "__main__":
    sys.exit(main())
