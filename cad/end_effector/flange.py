"""
Flange Body — GIS-EE-001

Per §4.4.1 (lines 334–390):
- Al 7075-T6 disc Φ90×25mm + PEEK Φ86/Φ40×5mm
- 4 arms 12×8×40mm at 0/90/180/270°
- PEEK台阶止口 3mm deep, O-ring groove Φ80×2.4 on Al face
- 4×M3 + Φ3 pin per arm end (PCD28 square)
- ISO 9409 back: 4×M6 on PCD50
- Spring pins: R=42, 4×Φ4×12mm deep (offset 45° from arms)
- PEEK固定: 6×M3 on PCD70 with Belleville washers
- Reducer mount: 4×M3 on back face
- ZIF防护盖座 15×10mm on edge
- LEMO mounting holes Φ9.4mm on each arm side
"""

import cadquery as cq
import math
from params import (
    FLANGE_OD, FLANGE_R, FLANGE_CENTER_HOLE, FLANGE_AL_THICK,
    FLANGE_PEEK_THICK, FLANGE_TOTAL_THICK,
    ARM_WIDTH, ARM_THICK, ARM_LENGTH, MOUNT_CENTER_R, MOUNT_FACE,
    MOUNT_BOLT_PCD, MOUNT_BOLT_DIA, MOUNT_BOLT_TAP_DIA, MOUNT_PIN_DIA, MOUNT_PIN_DEPTH,
    MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y, MOUNT_BOLT_NUM,
    ISO9409_PCD, ISO9409_BOLT_DIA, ISO9409_BOLT_NUM,
    SPRING_PIN_R, SPRING_PIN_DIA, SPRING_PIN_DEPTH,
    PEEK_OD, PEEK_ID, PEEK_THICK, PEEK_STEP_HEIGHT,
    PEEK_BOLT_NUM, PEEK_BOLT_DIA, PEEK_BOLT_PCD,
    ORING_CENTER_DIA, ORING_CS, ORING_GROOVE_WIDTH, ORING_GROOVE_DEPTH,
    REDUCER_MOUNT_PCD, REDUCER_MOUNT_BOLT_DIA, REDUCER_MOUNT_BOLT_NUM,
    ZIF_COVER_L, ZIF_COVER_W, ZIF_COVER_H, ZIF_BOLT_DIA,
    LEMO_BORE_DIA,
    NUM_STATIONS, STATION_ANGLES,
)


def make_flange_al() -> cq.Workplane:
    """
    Aluminium 7075-T6 flange disc with 4 arms and all features.
    Origin at disc center, Z=0 is back face (RM65-B side), Z+ is workstation side.
    """

    # ── Main disc ──
    result = (
        cq.Workplane("XY")
        .circle(FLANGE_R)
        .circle(FLANGE_CENTER_HOLE / 2.0)
        .extrude(FLANGE_AL_THICK)
    )

    # ── 4 Arms (rectangular extrusions from disc edge) ──
    for angle in STATION_ANGLES:
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        # Arm extends from R=45 to R=45+40=85, centered at R=65
        arm_mid_r = FLANGE_R + ARM_LENGTH / 2.0
        cx = arm_mid_r * cos_a
        cy = arm_mid_r * sin_a

        # Arm box: tangential=ARM_WIDTH, radial=ARM_LENGTH, axial=ARM_THICK
        # Arm is flush with front face, from Z=(AL_THICK - ARM_THICK) to Z=AL_THICK
        arm = (
            cq.Workplane("XY")
            .transformed(
                offset=(cx, cy, FLANGE_AL_THICK - ARM_THICK / 2.0),
                rotate=(0, 0, angle),
            )
            .box(ARM_WIDTH, ARM_LENGTH, ARM_THICK, centered=True)
        )
        result = result.union(arm)

    # ── PEEK step pocket (annular recess on +Z face) ──
    step_pocket = (
        cq.Workplane("XY")
        .workplane(offset=FLANGE_AL_THICK)
        .circle(PEEK_OD / 2.0)
        .circle(PEEK_ID / 2.0)
        .extrude(-PEEK_STEP_HEIGHT)
    )
    result = result.cut(step_pocket)

    # ── O-ring groove (annular channel on +Z face of Al, inside PEEK area) ──
    oring_r_center = ORING_CENTER_DIA / 2.0
    oring_r_inner = oring_r_center - ORING_GROOVE_WIDTH / 2.0
    oring_r_outer = oring_r_center + ORING_GROOVE_WIDTH / 2.0
    groove = (
        cq.Workplane("XY")
        .workplane(offset=FLANGE_AL_THICK)
        .circle(oring_r_outer)
        .circle(oring_r_inner)
        .extrude(-ORING_GROOVE_DEPTH)
    )
    result = result.cut(groove)

    # ── PEEK fixing: 6×M3 TAPPED BLIND holes in Al on PCD70 (§4 line 434) ──
    # M3×10 bolts pass through PEEK (clearance Φ3.2) and thread into Al (tap drill Φ2.5)
    # Blind depth: 8mm (10mm bolt - 5mm PEEK thickness = 5mm + 3mm safety)
    peek_tap_depth = 8.0
    for i in range(PEEK_BOLT_NUM):
        angle_rad = math.radians(i * 360.0 / PEEK_BOLT_NUM + 30)  # offset 30° from arms
        bx = (PEEK_BOLT_PCD / 2.0) * math.cos(angle_rad)
        by = (PEEK_BOLT_PCD / 2.0) * math.sin(angle_rad)
        hole = (
            cq.Workplane("XY")
            .workplane(offset=FLANGE_AL_THICK)  # drill from +Z face
            .center(bx, by)
            .circle(MOUNT_BOLT_TAP_DIA / 2.0)  # M3 tap drill Φ2.5
            .extrude(-peek_tap_depth)  # blind into Al
        )
        result = result.cut(hole)

    # ── Arm-end features: 4×M3 bolts + 1×Φ3 pin per arm ──
    for angle in STATION_ANGLES:
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        mcx = MOUNT_CENTER_R * cos_a
        mcy = MOUNT_CENTER_R * sin_a

        # 4×M3 TAPPED BLIND holes at PCD28 square (§4 line 348)
        # Bolts from station module thread INTO the arm — use tap drill Φ2.5, blind depth 6mm
        half_s = MOUNT_BOLT_PCD / 2.0  # half side of square
        bolt_offsets_local = [
            (+half_s / 2.0, +half_s / 2.0),
            (+half_s / 2.0, -half_s / 2.0),
            (-half_s / 2.0, +half_s / 2.0),
            (-half_s / 2.0, -half_s / 2.0),
        ]
        tap_depth = 6.0  # M3×8 bolt, 6mm thread engagement in 8mm arm
        for dx, dy in bolt_offsets_local:
            rx = dx * cos_a - dy * sin_a
            ry = dx * sin_a + dy * cos_a
            hole = (
                cq.Workplane("XY")
                .workplane(offset=FLANGE_AL_THICK)  # drill from +Z (workstation) face
                .center(mcx + rx, mcy + ry)
                .circle(MOUNT_BOLT_TAP_DIA / 2.0)
                .extrude(-tap_depth)  # blind hole into arm
            )
            result = result.cut(hole)

        # 1×Φ3 locating pin at +14, +14 offset (rotated to arm angle)
        pin_dx, pin_dy = MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y
        prx = pin_dx * cos_a - pin_dy * sin_a
        pry = pin_dx * sin_a + pin_dy * cos_a
        pin_hole = (
            cq.Workplane("XY")
            .workplane(offset=FLANGE_AL_THICK - ARM_THICK)
            .center(mcx + prx, mcy + pry)
            .circle(MOUNT_PIN_DIA / 2.0)
            .extrude(ARM_THICK)
        )
        result = result.cut(pin_hole)

        # LEMO Φ9.4mm bore on arm side face (radial, through arm width)
        lemo_z = FLANGE_AL_THICK - ARM_THICK / 2.0
        # Bore axis is tangential (perpendicular to radial direction)
        lemo_r = MOUNT_CENTER_R - 5.0  # slightly inward from mount center
        lemo_cx = lemo_r * cos_a
        lemo_cy = lemo_r * sin_a
        # Tangent direction
        tang_angle = angle + 90.0
        tang_rad = math.radians(tang_angle)
        lemo = (
            cq.Workplane("XY")
            .transformed(
                offset=(lemo_cx, lemo_cy, lemo_z),
                rotate=(0, 0, tang_angle),
            )
            .circle(LEMO_BORE_DIA / 2.0)
            .extrude(ARM_WIDTH)
        )
        result = result.cut(lemo)

    # ── ISO 9409 bolt holes on back face (Z=0, 4×M6 on PCD50 square) ──
    iso_half = ISO9409_PCD / 2.0 / math.sqrt(2)
    for dx, dy in [(iso_half, iso_half), (iso_half, -iso_half),
                   (-iso_half, iso_half), (-iso_half, -iso_half)]:
        hole = (
            cq.Workplane("XY")
            .center(dx, dy)
            .circle(ISO9409_BOLT_DIA / 2.0)
            .extrude(FLANGE_AL_THICK)
        )
        result = result.cut(hole)

    # ── Reducer mounting holes on back face (4×M3 on PCD22) ──
    for i in range(REDUCER_MOUNT_BOLT_NUM):
        angle_rad = math.radians(i * 90.0 + 45)  # 45° offset
        rx = (REDUCER_MOUNT_PCD / 2.0) * math.cos(angle_rad)
        ry = (REDUCER_MOUNT_PCD / 2.0) * math.sin(angle_rad)
        hole = (
            cq.Workplane("XY")
            .center(rx, ry)
            .circle(REDUCER_MOUNT_BOLT_DIA / 2.0)
            .extrude(10.0)  # blind tapped hole
        )
        result = result.cut(hole)

    # ── Spring pin holes at R=42, offset 45° from arms, 4×Φ4 H7 ×12mm deep ──
    # §4.4.2 line 403: pin on reducer output (fixed side, Z=0), engages flange (rotating)
    # Holes drilled from BACK face (Z=0) into flange body
    for angle in STATION_ANGLES:
        rad = math.radians(angle + 45)
        spx = SPRING_PIN_R * math.cos(rad)
        spy = SPRING_PIN_R * math.sin(rad)
        pin = (
            cq.Workplane("XY")
            .center(spx, spy)
            .circle(SPRING_PIN_DIA / 2.0)
            .extrude(SPRING_PIN_DEPTH)  # from Z=0 into +Z direction
        )
        result = result.cut(pin)

    # ── ZIF防护盖座 (boss on disc edge at 0° position) ──
    zif_r = FLANGE_R + ZIF_COVER_L / 2.0 - 3.0  # slightly overlapping disc edge
    zif_boss = (
        cq.Workplane("XY")
        .transformed(
            offset=(zif_r, 0, FLANGE_AL_THICK - ARM_THICK / 2.0),
            rotate=(0, 0, 0),
        )
        .box(ZIF_COVER_L, ZIF_COVER_W, ARM_THICK, centered=True)
    )
    result = result.union(zif_boss)

    # ZIF cover screw holes (2×M3)
    for dy in [-3.0, 3.0]:
        hole = (
            cq.Workplane("XY")
            .workplane(offset=FLANGE_AL_THICK - ARM_THICK)
            .center(zif_r, dy)
            .circle(ZIF_BOLT_DIA / 2.0)
            .extrude(ARM_THICK)
        )
        result = result.cut(hole)

    return result


def make_peek_ring() -> cq.Workplane:
    """
    PEEK insulation ring (GIS-EE-001-02).
    Sits in the step pocket, total protrusion = PEEK_THICK + PEEK_STEP_HEIGHT above Al.
    Actually: ring bottom is at Z = AL_THICK - STEP_HEIGHT, top at Z = AL_THICK + (PEEK_THICK - STEP_HEIGHT).
    Total ring thickness = PEEK_THICK = 5mm. Step insert = 3mm into Al, 2mm proud.
    Wait — let me re-read: total thickness = 30mm = 25mm Al + 5mm PEEK.
    So PEEK sits from Z=25 to Z=30, with 3mm step going INTO the Al (Z=22 to Z=25).
    """
    # PEEK ring: main body Φ86/Φ40 × 5mm from Z=25 to Z=30
    ring = (
        cq.Workplane("XY")
        .workplane(offset=FLANGE_AL_THICK)
        .circle(PEEK_OD / 2.0)
        .circle(PEEK_ID / 2.0)
        .extrude(PEEK_THICK)
    )

    # Step insert portion: Φ86/Φ40 × 3mm going into Al pocket from Z=22 to Z=25
    # But the pocket is already cut, so the PEEK extends down
    step_insert = (
        cq.Workplane("XY")
        .workplane(offset=FLANGE_AL_THICK - PEEK_STEP_HEIGHT)
        .circle(PEEK_OD / 2.0)
        .circle(PEEK_ID / 2.0)
        .extrude(PEEK_STEP_HEIGHT)
    )
    ring = ring.union(step_insert)

    # 6×M3 through holes matching flange pattern
    for i in range(6):
        angle_rad = math.radians(i * 60.0 + 30)
        bx = (PEEK_BOLT_PCD / 2.0) * math.cos(angle_rad)
        by = (PEEK_BOLT_PCD / 2.0) * math.sin(angle_rad)
        hole = (
            cq.Workplane("XY")
            .workplane(offset=FLANGE_AL_THICK - PEEK_STEP_HEIGHT)
            .center(bx, by)
            .circle(PEEK_BOLT_DIA / 2.0)
            .extrude(PEEK_THICK + PEEK_STEP_HEIGHT)
        )
        ring = ring.cut(hole)

    return ring


def make_oring() -> cq.Workplane:
    """O-ring FKM Φ80×2.4mm (GIS-EE-001-03).

    Approximated as annular ring (rectangular cross-section) for CadQuery compatibility.
    Origin at bottom center of ring, matching flange groove position.
    """
    oring_r = ORING_CENTER_DIA / 2.0
    cs_r = ORING_CS / 2.0  # cross-section radius 1.2mm
    z_base = FLANGE_AL_THICK - ORING_GROOVE_DEPTH
    ring = (
        cq.Workplane("XY")
        .workplane(offset=z_base)
        .circle(oring_r + cs_r)
        .circle(oring_r - cs_r)
        .extrude(ORING_CS)
    )
    return ring


def make_flange_assembly() -> tuple:
    """Return (al_body, peek_ring) as separate solids."""
    return make_flange_al(), make_peek_ring()


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)

    al, peek = make_flange_assembly()

    for name, solid in [("EE-001_flange_al", al), ("EE-001_flange_peek", peek)]:
        p = os.path.join(out, f"{name}.step")
        cq.exporters.export(solid, p)
        print(f"Exported: {p}")
