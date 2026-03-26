"""
Signal Conditioning Module (GIS-EE-006) — Mounted on J3-J4 arm link.

Per §4.6 (lines 527–533) / design doc §4.1.3:
- Enclosure 140×100×55mm (Al 7075-T6) with heat sink fins on top
- 4-layer PCB 134×94×2mm (signal conditioning + power regulation)
- L-shaped mounting bracket with Φ50mm clamp
- 4× LEMO 0B panel-mount sockets (rear panel)
- 2× SMA 50Ω bulkhead connectors (side panel)
- 1× M12 A-coded diagnostic port (bottom panel)

NOTE: This module is NOT part of the rotating end effector assembly.
      It mounts on the robot arm link ~250mm from the flange.
      Exported as separate STEP via build_all.py.

BOM: GIS-EE-006-01~06
"""

import cadquery as cq
import math
from params import (
    SIG_COND_W, SIG_COND_D, SIG_COND_H,
    LEMO_BORE_DIA,
)


def make_sig_cond_shell() -> cq.Workplane:
    """GIS-EE-006-01: Enclosure with heat sink fins (140×100×55mm).

    Origin at bottom-center, Z+ up.
    """
    wall = 3.0
    # Main box
    shell = cq.Workplane("XY").box(SIG_COND_W, SIG_COND_D, SIG_COND_H,
                                    centered=(True, True, False))
    # Hollow interior
    cavity = (
        cq.Workplane("XY")
        .workplane(offset=wall)
        .box(SIG_COND_W - 2*wall, SIG_COND_D - 2*wall, SIG_COND_H - 2*wall,
             centered=(True, True, False))
    )
    shell = shell.cut(cavity)

    # Heat sink fins on top (13 fins, 2mm tall, 1.5mm thick, spaced ~10mm)
    n_fins = 13
    fin_h = 2.0
    fin_thick = 1.5
    fin_len = SIG_COND_D - 10  # slightly shorter than enclosure depth
    fin_spacing = (SIG_COND_W - 10) / (n_fins - 1)
    start_x = -(SIG_COND_W - 10) / 2.0
    for i in range(n_fins):
        x = start_x + i * fin_spacing
        fin = (
            cq.Workplane("XY")
            .workplane(offset=SIG_COND_H)
            .center(x, 0)
            .box(fin_thick, fin_len, fin_h, centered=(True, True, False))
        )
        shell = shell.union(fin)

    # 4× LEMO bores on rear panel (+Y face)
    lemo_spacing = 25.0
    for i in range(4):
        x = -1.5 * lemo_spacing + i * lemo_spacing
        bore = (
            cq.Workplane("XZ")
            .workplane(offset=SIG_COND_D / 2.0)
            .center(x, SIG_COND_H * 0.5)
            .circle(LEMO_BORE_DIA / 2.0)
            .extrude(-wall - 1)
        )
        shell = shell.cut(bore)

    # 2× SMA bores on side panel (+X face)
    for z_off in [SIG_COND_H * 0.35, SIG_COND_H * 0.65]:
        bore = (
            cq.Workplane("YZ")
            .workplane(offset=SIG_COND_W / 2.0)
            .center(0, z_off)
            .circle(3.25)  # SMA bore ~6.5mm dia
            .extrude(-wall - 1)
        )
        shell = shell.cut(bore)

    # 1× M12 bore on bottom panel
    m12_bore = (
        cq.Workplane("XY")
        .center(SIG_COND_W / 4.0, 0)
        .circle(6.0)
        .extrude(wall + 1)
    )
    shell = shell.cut(m12_bore)

    # Lid screw holes (4× M3 at corners, top face)
    for dx in [-SIG_COND_W / 2.0 + 8, SIG_COND_W / 2.0 - 8]:
        for dy in [-SIG_COND_D / 2.0 + 8, SIG_COND_D / 2.0 - 8]:
            h = (
                cq.Workplane("XY")
                .workplane(offset=SIG_COND_H - wall)
                .center(dx, dy)
                .circle(1.6)
                .extrude(wall + 1)
            )
            shell = shell.cut(h)

    return shell


def make_sig_cond_pcb() -> cq.Workplane:
    """GIS-EE-006-02: 4-layer PCB 134×94×2mm."""
    pcb = cq.Workplane("XY").box(134.0, 94.0, 2.0, centered=(True, True, False))

    # Mounting holes (4× M3 at corners)
    for dx in [-60, 60]:
        for dy in [-40, 40]:
            h = cq.Workplane("XY").center(dx, dy).circle(1.6).extrude(2.0)
            pcb = pcb.cut(h)

    # Component zone representation (a few raised blocks)
    # Main processor area
    proc = (
        cq.Workplane("XY")
        .workplane(offset=2.0)
        .center(-20, 0)
        .box(15, 15, 2.5, centered=(True, True, False))
    )
    pcb = pcb.union(proc)

    # ADC cluster
    adc = (
        cq.Workplane("XY")
        .workplane(offset=2.0)
        .center(25, 15)
        .box(10, 10, 1.5, centered=(True, True, False))
    )
    pcb = pcb.union(adc)

    # Power regulator
    pwr = (
        cq.Workplane("XY")
        .workplane(offset=2.0)
        .center(40, -20)
        .box(12, 8, 3.0, centered=(True, True, False))
    )
    pcb = pcb.union(pwr)

    return pcb


def make_sig_cond_bracket() -> cq.Workplane:
    """GIS-EE-006-03: L-shaped mounting bracket with Φ50mm clamp.

    Bracket attaches enclosure to J3-J4 arm link.
    Origin at clamp center.
    """
    clamp_id = 50.0
    clamp_od = 56.0
    clamp_w = 20.0

    # Half-circle clamp (270° wrap for clamping)
    clamp = (
        cq.Workplane("XY")
        .circle(clamp_od / 2.0)
        .circle(clamp_id / 2.0)
        .extrude(clamp_w)
    )
    # Cut opening (60° gap at bottom for clamp bolt)
    cut_block = (
        cq.Workplane("XY")
        .center(0, -clamp_od / 2.0 - 5)
        .box(12, clamp_od / 2.0, clamp_w + 2, centered=(True, True, False))
    )
    clamp = clamp.cut(cut_block)

    # Clamp bolt ears
    for dx in [-8, 8]:
        ear = (
            cq.Workplane("XY")
            .center(dx, -clamp_od / 2.0 + 3)
            .box(10, 5, clamp_w, centered=(True, True, False))
        )
        clamp = clamp.union(ear)
        bolt_h = (
            cq.Workplane("XY")
            .center(dx, -clamp_od / 2.0 + 3)
            .circle(2.5)
            .extrude(clamp_w)
        )
        clamp = clamp.cut(bolt_h)

    # L-shaped plate extending from clamp to enclosure
    plate_h = 30.0
    plate_w = SIG_COND_W - 20
    plate_thick = 4.0
    plate = (
        cq.Workplane("XY")
        .center(0, clamp_od / 2.0)
        .box(plate_w, plate_thick, clamp_w, centered=(True, False, False))
    )
    clamp = clamp.union(plate)

    # Vertical riser
    riser = (
        cq.Workplane("XZ")
        .workplane(offset=clamp_od / 2.0 + plate_thick)
        .center(0, clamp_w / 2.0)
        .box(plate_w, plate_h, plate_thick, centered=(True, True, False))
    )
    clamp = clamp.union(riser)

    # Enclosure mounting holes on riser (4× M4)
    for dx in [-plate_w / 2.0 + 15, plate_w / 2.0 - 15]:
        for dz in [clamp_w / 2.0 - 8, clamp_w / 2.0 + plate_h - 8]:
            h = (
                cq.Workplane("XZ")
                .workplane(offset=clamp_od / 2.0 + plate_thick)
                .center(dx, dz)
                .circle(2.0)
                .extrude(-plate_thick - 1)
            )
            clamp = clamp.cut(h)

    return clamp


def make_sig_cond_assembly() -> cq.Workplane:
    """Full signal conditioning module (GIS-EE-006).

    Combines shell + PCB + bracket + connectors.
    Origin at clamp center.
    """
    from fasteners import make_lemo_0b, make_sma_connector, make_m12_connector

    bracket = make_sig_cond_bracket()

    # Position shell on top of bracket riser
    clamp_od = 56.0
    plate_thick = 4.0
    riser_y = clamp_od / 2.0 + plate_thick * 2
    shell_offset_z = 0  # bottom of shell at Z=0 relative to bracket top

    shell = (
        make_sig_cond_shell()
        .translate((0, riser_y + SIG_COND_D / 2.0, shell_offset_z))
    )
    bracket = bracket.union(shell)

    # PCB inside shell (3mm above bottom wall)
    pcb = (
        make_sig_cond_pcb()
        .translate((0, riser_y + SIG_COND_D / 2.0, shell_offset_z + 5.0))
    )
    bracket = bracket.union(pcb)

    # 4× LEMO connectors on rear panel
    lemo_spacing = 25.0
    lemo_y = riser_y + SIG_COND_D
    for i in range(4):
        x = -1.5 * lemo_spacing + i * lemo_spacing
        lemo = (
            make_lemo_0b()
            .rotate((0, 0, 0), (1, 0, 0), 90)
            .translate((x, lemo_y, shell_offset_z + SIG_COND_H * 0.5))
        )
        bracket = bracket.union(lemo)

    # 2× SMA on side panel
    sma_x = SIG_COND_W / 2.0
    for z_off in [SIG_COND_H * 0.35, SIG_COND_H * 0.65]:
        sma = (
            make_sma_connector()
            .rotate((0, 0, 0), (0, 1, 0), -90)
            .translate((sma_x, riser_y + SIG_COND_D / 2.0, shell_offset_z + z_off))
        )
        bracket = bracket.union(sma)

    # M12 on bottom panel
    m12 = (
        make_m12_connector()
        .rotate((0, 0, 0), (1, 0, 0), 180)
        .translate((SIG_COND_W / 4.0, riser_y + SIG_COND_D / 2.0, shell_offset_z))
    )
    bracket = bracket.union(m12)

    return bracket


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    assy = make_sig_cond_assembly()
    p = os.path.join(out, "EE-006_signal_conditioning.step")
    cq.exporters.export(assy, p)
    print(f"Exported: {p}")
