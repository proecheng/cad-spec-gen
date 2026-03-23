"""
Station 2 (90°) — AE Ultrasonic Detection Module (GIS-EE-003)

Serial stack per §4.1.2 (lines 121–165):
  Mount face → Force sensor(Φ42×12) → Spring limiter(upper plate→spring→
  guide→sleeve→lower plate) → Gimbal(upper flange→rubber→lower flange) →
  Damper pad → AE probe(Φ28×26)
Side: Counterweight Φ12×7mm (tungsten, 50g)
Also: Pressure sensor array 20×20mm, LEMO bore

BOM items modeled individually:
  GIS-EE-003-01 AE传感器 TWAE-03
  GIS-EE-003-02 六轴力传感器 KWR42
  GIS-EE-003-03 弹簧限力机构总成 (6 sub-parts)
  GIS-EE-003-04 柔性关节（万向节）
  GIS-EE-003-05 阻尼垫
  GIS-EE-003-06 压力阵列
  GIS-EE-003-07 配重块
"""

import cadquery as cq
import math
from params import (
    S2_AE_DIA, S2_AE_H,
    S2_FORCE_DIA, S2_FORCE_H, S2_FORCE_BOLT_PCD, S2_FORCE_BOLT_DIA,
    S2_FORCE_BOLT_NUM, S2_FORCE_CENTER_HOLE,
    S2_SPRING_OD, S2_SPRING_FREE_L,
    S2_GUIDE_DIA, S2_GUIDE_LENGTH, S2_GUIDE_BORE,
    S2_ENDPLATE_DIA, S2_ENDPLATE_THICK,
    S2_SLEEVE_OD, S2_SLEEVE_ID, S2_SLEEVE_H,
    S2_SHIM_DIA, S2_SHIM_THICK,
    S2_GIMBAL_OD, S2_GIMBAL_ID, S2_GIMBAL_H,
    S2_GIMBAL_FLANGE_DIA, S2_GIMBAL_FLANGE_THICK,
    S2_GIMBAL_FLANGE_PCD, S2_GIMBAL_BOLT_DIA, S2_GIMBAL_BOLT_NUM,
    S2_DAMPER_DIA, S2_DAMPER_THICK,
    S2_PRESSURE_W, S2_PRESSURE_H, S2_PRESSURE_THICK,
    S2_CW_DIA, S2_CW_H, S2_CW_BOLT_DIA, S2_CW_BOLT_SPACING,
    S2_RETURN_SPRING_DIA, S2_RETURN_SPRING_NUM,
    MOUNT_FACE, MOUNT_BOLT_PCD, MOUNT_BOLT_DIA,
    MOUNT_PIN_DIA, MOUNT_PIN_OFFSET_X, MOUNT_PIN_OFFSET_Y,
    LEMO_BORE_DIA,
)


# ─── Individual BOM parts ────────────────────────────────────────────────

def make_force_sensor() -> cq.Workplane:
    """GIS-EE-003-02: Six-axis force sensor KWR42 (Φ42×12mm)."""
    fs = cq.Workplane("XY").circle(S2_FORCE_DIA / 2.0).extrude(S2_FORCE_H)
    # Center through hole
    ch = cq.Workplane("XY").circle(S2_FORCE_CENTER_HOLE / 2.0).extrude(S2_FORCE_H)
    fs = fs.cut(ch)
    # Mounting bolt holes (4×M3 on PCD36, top and bottom pattern)
    for i in range(S2_FORCE_BOLT_NUM):
        angle = math.radians(i * 90 + 45)
        bx = (S2_FORCE_BOLT_PCD / 2.0) * math.cos(angle)
        by = (S2_FORCE_BOLT_PCD / 2.0) * math.sin(angle)
        h = cq.Workplane("XY").center(bx, by).circle(S2_FORCE_BOLT_DIA / 2.0).extrude(S2_FORCE_H)
        fs = fs.cut(h)
    # Cable exit notch
    notch = (
        cq.Workplane("XY")
        .workplane(offset=S2_FORCE_H * 0.3)
        .center(S2_FORCE_DIA / 2.0, 0)
        .box(6, 8, S2_FORCE_H * 0.4, centered=(True, True, False))
    )
    fs = fs.cut(notch)
    return fs


def make_upper_endplate() -> cq.Workplane:
    """弹簧限力 上端板 Φ12×2mm with Φ4.1 center guide bore."""
    plate = cq.Workplane("XY").circle(S2_ENDPLATE_DIA / 2.0).extrude(S2_ENDPLATE_THICK)
    bore = cq.Workplane("XY").circle(S2_GUIDE_BORE / 2.0).extrude(S2_ENDPLATE_THICK)
    plate = plate.cut(bore)
    # 2×M3 mounting holes to connect to force sensor
    for dx in [-4, 4]:
        h = cq.Workplane("XY").center(dx, 0).circle(1.6).extrude(S2_ENDPLATE_THICK)
        plate = plate.cut(h)
    return plate


def make_lower_endplate() -> cq.Workplane:
    """弹簧限力 下端板 Φ12×2mm with Φ4.1 center guide bore."""
    plate = cq.Workplane("XY").circle(S2_ENDPLATE_DIA / 2.0).extrude(S2_ENDPLATE_THICK)
    bore = cq.Workplane("XY").circle(S2_GUIDE_BORE / 2.0).extrude(S2_ENDPLATE_THICK)
    plate = plate.cut(bore)
    for dx in [-4, 4]:
        h = cq.Workplane("XY").center(dx, 0).circle(1.1).extrude(S2_ENDPLATE_THICK)
        plate = plate.cut(h)
    return plate


def make_guide_shaft() -> cq.Workplane:
    """导向轴 Φ4×15mm (SUS303, hard chrome plated)."""
    return cq.Workplane("XY").circle(S2_GUIDE_DIA / 2.0).extrude(S2_GUIDE_LENGTH)


def make_spring() -> cq.Workplane:
    """压缩弹簧 Φ8mm OD × 12mm free length (approximated as hollow cylinder)."""
    outer = cq.Workplane("XY").circle(S2_SPRING_OD / 2.0).extrude(S2_SPRING_FREE_L)
    inner = cq.Workplane("XY").circle(S2_SPRING_OD / 2.0 - S2_SPRING_OD * 0.15).extrude(S2_SPRING_FREE_L)
    return outer.cut(inner)


def make_sleeve() -> cq.Workplane:
    """套筒 Φ12 OD × Φ8.2 ID × 14mm (7075-T6)."""
    outer = cq.Workplane("XY").circle(S2_SLEEVE_OD / 2.0).extrude(S2_SLEEVE_H)
    inner = cq.Workplane("XY").circle(S2_SLEEVE_ID / 2.0).extrude(S2_SLEEVE_H)
    return outer.cut(inner)


def make_shim() -> cq.Workplane:
    """预紧垫片 Φ8×0.5mm."""
    return cq.Workplane("XY").circle(S2_SHIM_DIA / 2.0).extrude(S2_SHIM_THICK)


def make_spring_limiter_assy() -> cq.Workplane:
    """
    弹簧限力机构总成 (GIS-EE-003-03).
    Stack: upper plate → spring+guide+sleeve → shim → lower plate.
    Total height ≈ 2 + 14 + 0.5 + 2 = 18.5mm.
    """
    z = 0.0
    # Upper endplate
    upper = make_upper_endplate()
    result = upper
    z += S2_ENDPLATE_THICK  # 2mm

    # Sleeve (outer containment)
    sleeve = make_sleeve().translate((0, 0, z))
    result = result.union(sleeve)

    # Guide shaft (inside sleeve, centered)
    shaft_offset = z + (S2_SLEEVE_H - S2_GUIDE_LENGTH) / 2.0
    guide = make_guide_shaft().translate((0, 0, shaft_offset))
    result = result.union(guide)

    # Spring (inside sleeve, around guide)
    spring_offset = z + (S2_SLEEVE_H - S2_SPRING_FREE_L) / 2.0
    spring = make_spring().translate((0, 0, spring_offset))
    result = result.union(spring)

    z += S2_SLEEVE_H  # +14mm

    # Shim
    shim = make_shim().translate((0, 0, z))
    result = result.union(shim)
    z += S2_SHIM_THICK  # +0.5mm

    # Lower endplate
    lower = make_lower_endplate().translate((0, 0, z))
    result = result.union(lower)

    return result


def make_gimbal_upper_flange() -> cq.Workplane:
    """万向节上法兰 Φ30×3mm with 4×M2 holes."""
    fl = cq.Workplane("XY").circle(S2_GIMBAL_FLANGE_DIA / 2.0).extrude(S2_GIMBAL_FLANGE_THICK)
    # Center hole
    ch = cq.Workplane("XY").circle(S2_GIMBAL_ID / 2.0).extrude(S2_GIMBAL_FLANGE_THICK)
    fl = fl.cut(ch)
    # 4×M2 holes
    for i in range(S2_GIMBAL_BOLT_NUM):
        a = math.radians(i * 90 + 45)
        bx = (S2_GIMBAL_FLANGE_PCD / 2.0) * math.cos(a)
        by = (S2_GIMBAL_FLANGE_PCD / 2.0) * math.sin(a)
        h = cq.Workplane("XY").center(bx, by).circle(S2_GIMBAL_BOLT_DIA / 2.0).extrude(S2_GIMBAL_FLANGE_THICK)
        fl = fl.cut(h)
    return fl


def make_gimbal_rubber() -> cq.Workplane:
    """硅橡胶万向节本体 Φ30/Φ12×15mm (Shore A 40)."""
    outer = cq.Workplane("XY").circle(S2_GIMBAL_OD / 2.0).extrude(S2_GIMBAL_H)
    inner = cq.Workplane("XY").circle(S2_GIMBAL_ID / 2.0).extrude(S2_GIMBAL_H)
    body = outer.cut(inner)
    # Waist (concave profile for flexibility)
    waist = (
        cq.Workplane("XY")
        .workplane(offset=S2_GIMBAL_H * 0.3)
        .circle(S2_GIMBAL_OD / 2.0 + 1)
        .circle(S2_GIMBAL_OD / 2.0 - 3.0)
        .extrude(S2_GIMBAL_H * 0.4)
    )
    body = body.cut(waist)
    return body


def make_gimbal_assy() -> cq.Workplane:
    """
    GIS-EE-003-04: 柔性关节总成.
    Stack: upper flange → rubber → lower flange.
    + 4× return springs (Φ1.5mm rods as proxy)
    """
    z = 0.0
    upper_fl = make_gimbal_upper_flange()
    result = upper_fl
    z += S2_GIMBAL_FLANGE_THICK

    rubber = make_gimbal_rubber().translate((0, 0, z))
    result = result.union(rubber)
    z += S2_GIMBAL_H

    lower_fl = make_gimbal_upper_flange().translate((0, 0, z))  # same geometry
    result = result.union(lower_fl)

    # 4× return springs (simplified as small cylinders at 90° intervals)
    spring_r = S2_GIMBAL_OD / 2.0 + 2.0
    total_h = S2_GIMBAL_FLANGE_THICK * 2 + S2_GIMBAL_H
    for i in range(S2_RETURN_SPRING_NUM):
        a = math.radians(i * 90)
        sx = spring_r * math.cos(a)
        sy = spring_r * math.sin(a)
        rs = cq.Workplane("XY").center(sx, sy).circle(S2_RETURN_SPRING_DIA / 2.0).extrude(total_h)
        result = result.union(rs)

    return result


def make_damper_pad() -> cq.Workplane:
    """GIS-EE-003-05: 黏弹性阻尼垫 Φ28×2mm."""
    return cq.Workplane("XY").circle(S2_DAMPER_DIA / 2.0).extrude(S2_DAMPER_THICK)


def make_ae_probe() -> cq.Workplane:
    """GIS-EE-003-01: AE传感器 TWAE-03 Φ28×26mm."""
    probe = cq.Workplane("XY").circle(S2_AE_DIA / 2.0).extrude(S2_AE_H)
    # Cable exit on side (small cylinder)
    cable = (
        cq.Workplane("XZ")
        .workplane(offset=0)
        .center(S2_AE_DIA / 2.0, S2_AE_H * 0.7)
        .circle(1.5)
        .extrude(10.0)
    )
    probe = probe.union(cable)
    return probe


def make_pressure_array() -> cq.Workplane:
    """GIS-EE-003-06: 压力阵列 4×4 薄膜 20×20×0.5mm."""
    arr = cq.Workplane("XY").box(S2_PRESSURE_W, S2_PRESSURE_H, S2_PRESSURE_THICK,
                                 centered=(True, True, False))
    return arr


def make_counterweight() -> cq.Workplane:
    """GIS-EE-003-07: 钨合金配重块 Φ12×7mm, 50g."""
    cw = cq.Workplane("XY").circle(S2_CW_DIA / 2.0).extrude(S2_CW_H)
    # 2×M2 mounting holes
    for dx in [-S2_CW_BOLT_SPACING / 2.0, S2_CW_BOLT_SPACING / 2.0]:
        h = cq.Workplane("XY").center(dx, 0).circle(S2_CW_BOLT_DIA / 2.0).extrude(S2_CW_H)
        cw = cw.cut(h)
    return cw


# ─── Full module assembly ────────────────────────────────────────────────

def make_ae_module() -> cq.Workplane:
    """
    Full AE module assembly (GIS-EE-003).
    Origin at mounting face center, Z+ = away from flange (downward into workspace).

    §4 line 163: envelope Φ45×120mm.
    §4 lines 154-157 serial stack (with M3 bolt interfaces between components):

      Z=0:        Mounting plate (interface to arm, 4×M3 bolts)
      Z=0→3:      Mounting adapter plate (3mm, bolt-through + spacer)
      Z=3→23:     Force sensor KWR42 (20mm, ⚠️estimated)
      Z=23→26:    Interface plate force→limiter (3mm, 4×M3)
      Z=26→44.5:  Spring limiter (2+14+0.5+2 = 18.5mm)
      Z=44.5→47.5: Interface plate limiter→gimbal (3mm, 4×M3)
      Z=47.5→68.5: Gimbal assy (3+15+3 = 21mm)
      Z=68.5→70.5: Damper pad (2mm)
      Z=70.5→71:   Pressure array (0.5mm)
      Z=71→97:     AE probe (26mm)
    Side:
      Counterweight near mount face end (Z≈5, §4 line 162 "far from AE probe end")

    Total stack ≈ 97mm. With mounting hardware tolerances → ~100mm active stack.
    120mm envelope includes safety margin for bolt heads, cable exits, etc.
    """
    z = 0.0

    # Mounting adapter plate (connects arm bolts to force sensor)
    adapter_h = 3.0
    adapter = (
        cq.Workplane("XY")
        .circle(S2_FORCE_DIA / 2.0)
        .extrude(adapter_h)
    )
    # M3 bolt pass-through holes
    for i in range(S2_FORCE_BOLT_NUM):
        a = math.radians(i * 90 + 45)
        bx = (S2_FORCE_BOLT_PCD / 2.0) * math.cos(a)
        by = (S2_FORCE_BOLT_PCD / 2.0) * math.sin(a)
        h = cq.Workplane("XY").center(bx, by).circle(S2_FORCE_BOLT_DIA / 2.0).extrude(adapter_h)
        adapter = adapter.cut(h)
    result = adapter
    z += adapter_h  # 3

    # Force sensor
    fs = make_force_sensor().translate((0, 0, z))
    result = result.union(fs)
    z += S2_FORCE_H  # 23

    # Interface plate (force sensor → spring limiter, 3mm)
    iface1_h = 3.0
    iface1 = cq.Workplane("XY").workplane(offset=z).circle(S2_ENDPLATE_DIA / 2.0 + 2).extrude(iface1_h)
    result = result.union(iface1)
    z += iface1_h  # 26

    # Spring limiter assembly
    limiter = make_spring_limiter_assy().translate((0, 0, z))
    result = result.union(limiter)
    limiter_h = S2_ENDPLATE_THICK + S2_SLEEVE_H + S2_SHIM_THICK + S2_ENDPLATE_THICK  # 18.5
    z += limiter_h  # 44.5

    # Interface plate (spring limiter → gimbal, 3mm)
    iface2_h = 3.0
    iface2 = cq.Workplane("XY").workplane(offset=z).circle(S2_GIMBAL_FLANGE_DIA / 2.0 + 1).extrude(iface2_h)
    result = result.union(iface2)
    z += iface2_h  # 47.5

    # Gimbal assembly
    gimbal = make_gimbal_assy().translate((0, 0, z))
    result = result.union(gimbal)
    gimbal_h = S2_GIMBAL_FLANGE_THICK * 2 + S2_GIMBAL_H  # 21
    z += gimbal_h  # 68.5

    # Damper pad
    damper = make_damper_pad().translate((0, 0, z))
    result = result.union(damper)
    z += S2_DAMPER_THICK  # 70.5

    # Pressure sensor array
    parr = make_pressure_array().translate((0, 0, z))
    result = result.union(parr)
    z += S2_PRESSURE_THICK  # 71

    # AE probe
    probe = make_ae_probe().translate((0, 0, z))
    result = result.union(probe)
    z += S2_AE_H  # 97

    # Counterweight — §4 line 162: "安装于模块底部（远离AE探头端）"
    # "Far from AE probe" = near mount face = near Z=0
    cw = make_counterweight().translate((S2_FORCE_DIA / 2.0 + S2_CW_DIA / 2.0 + 2.0,
                                          0, adapter_h))  # at Z=3, near mount face
    result = result.union(cw)

    return result


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    r = make_ae_module()
    p = os.path.join(out, "EE-003_station2_ae.step")
    cq.exporters.export(r, p)
    print(f"Exported: {p}")
