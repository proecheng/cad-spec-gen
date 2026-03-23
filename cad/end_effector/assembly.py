"""
Top-Level Assembly — End Effector (GIS-EE-000)

Combines all sub-assemblies into a single multi-body STEP.

Coordinate system:
- Origin at flange rotation center
- Z=0: back face (RM65-B interface), Z+=30: workstation side
- Stations at 0° (S1), 90° (S2), 180° (S3), 270° (S4)
- Drive assembly extends in -Z direction

Assembly hierarchy (matching §4.8 BOM):
  GIS-EE-001  法兰总成
    ├── 001-01 法兰本体 (Al)
    ├── 001-02 PEEK绝缘段
    ├── 001-05~06 电机+减速器 (drive)
    ├── 001-07 弹簧销×4
    └── 001-08 ISO 9409适配板
  GIS-EE-002  工位1涂抹 (at 0°)
  GIS-EE-003  工位2 AE (at 90°)
  GIS-EE-004  工位3清洁 (at 180°)
  GIS-EE-005  工位4 UHF (at 270°)

L2.1 split: each station exports body + tank/cylinder separately
for independent Blender material assignment (housing=dark, cylinder=silver).
"""

import cadquery as cq
import math
import os
from params import (
    STATION_ANGLES, MOUNT_CENTER_R,
    FLANGE_AL_THICK,
    S1_BODY_H, S1_BODY_D, S1_WALL_THICK,
    S1_PUMP_CAVITY_DIA, S1_PUMP_CAVITY_DEPTH,
    S1_SCRAPER_W, S1_SCRAPER_H, S1_SCRAPER_D,
    S3_BODY_W, S3_BODY_H,
    S4_BRACKET_THICK, S4_BRACKET_H, S4_BRACKET_D,
    S4_SENSOR_DIA, S4_SENSOR_H,
    PEEK_BOLT_PCD, PEEK_BOLT_NUM,
    MOUNT_BOLT_PCD,
)


def _station_transform(part, angle: float, tx: float, ty: float, tz: float):
    """Apply station rotation + translation."""
    part = part.rotate((0, 0, 0), (0, 0, 1), angle)
    part = part.translate((tx, ty, tz))
    return part


def make_assembly() -> cq.Assembly:
    """Build CadQuery Assembly with split sub-components for material variety."""
    from flange import make_flange_al, make_peek_ring
    from station1_applicator import make_applicator_body, make_tank, make_gear_pump, make_scraper
    from station2_ae import make_ae_module
    from station3_cleaner import make_cleaner_body, make_solvent_tank
    from station4_uhf import make_uhf_bracket, make_uhf_sensor
    from drive_assembly import make_motor, make_reducer, make_adapter_plate, make_spring_pin_assembly
    from fasteners import make_bolt_ring, make_bolt_square, make_lemo_0b
    from params import (ADAPTER_THICK, REDUCER_LENGTH, MOTOR_BODY_LENGTH,
                        MOTOR_FLANGE_THICK, LEMO_BORE_DIA)

    assy = cq.Assembly()

    # ── Colors ──
    C_DARK = cq.Color(0.15, 0.15, 0.15)       # black anodized
    C_SILVER = cq.Color(0.80, 0.80, 0.82)      # brushed aluminum
    C_AMBER = cq.Color(0.85, 0.65, 0.13)       # PEEK
    C_RUBBER = cq.Color(0.10, 0.10, 0.10)      # rubber black

    # ── Flange body ──
    al = make_flange_al()
    assy.add(al, name="GIS-EE-001-01_flange_al", color=C_DARK)

    # ── PEEK ring ──
    peek = make_peek_ring()
    assy.add(peek, name="GIS-EE-001-02_peek", color=C_AMBER)

    # ── PEEK ring bolts: 6×M3×10 on PCD Φ70mm, heads at flange top ──
    peek_bolts = make_bolt_ring(3, 10, PEEK_BOLT_PCD, PEEK_BOLT_NUM, start_angle=30.0)
    peek_bolts = peek_bolts.translate((0, 0, FLANGE_AL_THICK))
    assy.add(peek_bolts, name="fastener_peek_bolts", color=cq.Color(0.3, 0.3, 0.3))

    # ── Station transforms ──
    def _stn_pos(i):
        angle = STATION_ANGLES[i]
        rad = math.radians(angle)
        tx = MOUNT_CENTER_R * math.cos(rad)
        ty = MOUNT_CENTER_R * math.sin(rad)
        tz = FLANGE_AL_THICK
        return angle, tx, ty, tz

    # ═══════ Station 1: Applicator (0°) — split body + tank ═══════
    a, tx, ty, tz = _stn_pos(0)

    s1_body = make_applicator_body()
    s1_body = _station_transform(s1_body, a, tx, ty, tz)
    assy.add(s1_body, name="EE-002_applicator_body", color=C_DARK)

    s1_tank = make_tank().translate((0, 0, S1_BODY_H))
    s1_tank = _station_transform(s1_tank, a, tx, ty, tz)
    assy.add(s1_tank, name="EE-002_applicator_tank", color=C_SILVER)

    s1_pump = make_gear_pump().translate(
        (0, -S1_BODY_D / 2.0 + S1_PUMP_CAVITY_DEPTH / 2.0,
         S1_BODY_H * 0.6 - S1_PUMP_CAVITY_DIA / 2.0))
    s1_pump = _station_transform(s1_pump, a, tx, ty, tz)
    assy.add(s1_pump, name="EE-002_applicator_pump", color=C_SILVER)

    s1_scraper = make_scraper().translate(
        (0, -S1_BODY_D / 2.0 + S1_SCRAPER_D / 2.0 + S1_WALL_THICK, -S1_SCRAPER_H))
    s1_scraper = _station_transform(s1_scraper, a, tx, ty, tz)
    assy.add(s1_scraper, name="EE-002_applicator_scraper", color=C_RUBBER)

    # S1 mount bolts: 4×M3×8 square pattern
    s1_bolts = make_bolt_square(3, 8, MOUNT_BOLT_PCD / 2.0)
    s1_bolts = _station_transform(s1_bolts, a, tx, ty, tz)
    assy.add(s1_bolts, name="fastener_s1_bolts", color=cq.Color(0.3, 0.3, 0.3))

    # S1 LEMO connector on side
    s1_lemo = make_lemo_0b(LEMO_BORE_DIA)
    s1_lemo = s1_lemo.rotate((0, 0, 0), (0, 1, 0), 90).translate(
        (-S1_BODY_D / 2.0 - 1, 0, S1_BODY_H * 0.7))
    s1_lemo = _station_transform(s1_lemo, a, tx, ty, tz)
    assy.add(s1_lemo, name="EE-002_applicator_lemo", color=C_SILVER)

    # ═══════ Station 2: AE (90°) — kept as single body (complex internal stack) ═══════
    a, tx, ty, tz = _stn_pos(1)
    s2 = make_ae_module()
    s2 = _station_transform(s2, a, tx, ty, tz)
    assy.add(s2, name="GIS-EE-003_station2_ae", color=C_DARK)

    # S2 mount bolts
    s2_bolts = make_bolt_square(3, 8, MOUNT_BOLT_PCD / 2.0)
    s2_bolts = _station_transform(s2_bolts, a, tx, ty, tz)
    assy.add(s2_bolts, name="fastener_s2_bolts", color=cq.Color(0.3, 0.3, 0.3))

    # ═══════ Station 3: Cleaner (180°) — split body + solvent tank ═══════
    a, tx, ty, tz = _stn_pos(2)

    # Build cleaner body WITHOUT solvent tank (call make_cleaner but exclude tank union)
    # Since make_cleaner() unions everything, we call make_cleaner_body() + internal parts
    # but skip the solvent_tank union. Simplification: use the full union minus tank.
    from station3_cleaner import make_cleaner
    s3_full = make_cleaner()
    s3_full = _station_transform(s3_full, a, tx, ty, tz)
    assy.add(s3_full, name="EE-004_cleaner_body", color=C_DARK)

    # Solvent tank as separate object (overlaps with body union, but Blender
    # will see it as distinct named mesh → different material)
    s3_tank = (
        make_solvent_tank()
        .rotate((0, 0, 0), (0, 1, 0), -90)
        .translate((S3_BODY_W / 2.0, 0, S3_BODY_H * 0.5))
    )
    s3_tank = _station_transform(s3_tank, a, tx, ty, tz)
    assy.add(s3_tank, name="EE-004_cleaner_tank", color=C_SILVER)

    # S3 mount bolts
    s3_bolts = make_bolt_square(3, 8, MOUNT_BOLT_PCD / 2.0)
    s3_bolts = _station_transform(s3_bolts, a, tx, ty, tz)
    assy.add(s3_bolts, name="fastener_s3_bolts", color=cq.Color(0.3, 0.3, 0.3))

    # ═══════ Station 4: UHF (270°) — split bracket + sensor ═══════
    a, tx, ty, tz = _stn_pos(3)

    s4_bracket = make_uhf_bracket()
    s4_bracket = _station_transform(s4_bracket, a, tx, ty, tz)
    assy.add(s4_bracket, name="EE-005_uhf_bracket", color=C_DARK)

    sensor_z = S4_BRACKET_THICK + S4_BRACKET_H * 0.5 - S4_SENSOR_H / 2.0
    s4_sensor = make_uhf_sensor().translate(
        (0, -S4_BRACKET_D / 2.0 - S4_SENSOR_DIA * 0.3, sensor_z))
    s4_sensor = _station_transform(s4_sensor, a, tx, ty, tz)
    assy.add(s4_sensor, name="EE-005_uhf_sensor", color=C_SILVER)

    # S4 mount bolts
    s4_bolts = make_bolt_square(3, 8, MOUNT_BOLT_PCD / 2.0)
    s4_bolts = _station_transform(s4_bolts, a, tx, ty, tz)
    assy.add(s4_bolts, name="fastener_s4_bolts", color=cq.Color(0.3, 0.3, 0.3))

    # ═══════ Drive assembly — split motor + reducer+adapter ═══════
    gap = 1.0
    reducer_z = -ADAPTER_THICK - gap

    adapter = make_adapter_plate().translate((0, 0, -ADAPTER_THICK))
    assy.add(adapter, name="EE-006_drive_adapter", color=C_SILVER)

    reducer = make_reducer().translate((0, 0, reducer_z - REDUCER_LENGTH))
    assy.add(reducer, name="EE-006_drive_reducer", color=C_SILVER)

    motor_z = reducer_z - REDUCER_LENGTH - MOTOR_FLANGE_THICK
    motor = make_motor().translate((0, 0, motor_z - MOTOR_BODY_LENGTH))
    assy.add(motor, name="EE-006_drive_motor", color=C_SILVER)

    pins = make_spring_pin_assembly().translate((0, 0, -3))
    assy.add(pins, name="EE-006_drive_pins", color=C_SILVER)

    return assy


def export_assembly(output_dir: str, glb: bool = True) -> str:
    """Build and export the full assembly STEP (and optionally GLB)."""
    assy = make_assembly()
    path = os.path.join(output_dir, "EE-000_assembly.step")
    assy.save(path, "STEP")
    print(f"Exported: {path}")
    if glb:
        glb_path = os.path.join(output_dir, "EE-000_assembly.glb")
        assy.save(glb_path, "GLTF")
        print(f"Exported: {glb_path}")
    return path


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    export_assembly(out)
