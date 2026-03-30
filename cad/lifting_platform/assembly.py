"""
Top-Level Assembly — SLP-01 丝杠式升降平台
Based on: 19-液压钳升降平台设计.md V12.0
"""
import cadquery as cq
import math
import os
from params import *

def make_top_plate():
    """SLP-100 上固定板 200x100x8"""
    p = (cq.Workplane("XY")
         .box(TOP_PLATE_W, TOP_PLATE_H, PLATE_THICK, centered=(True, True, False))
         )
    # 丝杠穿过孔 φ24 ×2
    for x, y in [(-LS_X, LS_Y), (LS_X, -LS_Y)]:
        p = p.faces(">Z").workplane().pushPoints([(x, y)]).hole(24)
    # 导向轴孔 φ10H7 ×2
    for x, y in [(GS_X, GS_Y), (-GS_X, -GS_Y)]:
        p = p.faces(">Z").workplane().pushPoints([(x, y)]).hole(10)
    # M5 机器人接口 ×4
    for x, y in [(-80, 35), (80, 35), (-80, -35), (80, -35)]:
        p = p.faces(">Z").workplane().pushPoints([(x, y)]).hole(5.5)
    return p

def make_support_bar():
    """SLP-200/201 支撑条 50x100x8"""
    p = (cq.Workplane("XY")
         .box(SUP_BAR_W, SUP_BAR_H, PLATE_THICK, centered=(True, True, False))
         )
    # 丝杠穿过孔 φ24
    p = p.faces(">Z").workplane().pushPoints([(0, 30)]).hole(24)
    # 导向轴孔 φ10H7
    p = p.faces(">Z").workplane().pushPoints([(0, -30)]).hole(10)
    return p

def make_moving_plate():
    """SLP-300 动板 150x100x8"""
    p = (cq.Workplane("XY")
         .box(MOV_PLATE_W, MOV_PLATE_H, PLATE_THICK, centered=(True, True, False))
         )
    # 丝杠螺母穿过孔 φ22 ×2
    for x, y in [(-LS_X, LS_Y), (LS_X, -LS_Y)]:
        p = p.faces(">Z").workplane().pushPoints([(x, y)]).hole(22)
    # LM10UU 轴承孔 φ19 ×2
    for x, y in [(GS_X, GS_Y), (-GS_X, -GS_Y)]:
        p = p.faces(">Z").workplane().pushPoints([(x, y)]).hole(19)
    # 中心油管孔 φ16
    p = p.faces(">Z").workplane().pushPoints([(0, 0)]).hole(16)
    # 电缆孔 φ10
    p = p.faces(">Z").workplane().pushPoints([(30, 0)]).hole(10)
    # M6 液压钳安装孔 ×4
    for x, y in [(-35, 25), (35, 25), (-35, -25), (35, -25)]:
        p = p.faces(">Z").workplane().pushPoints([(x, y)]).hole(6.7)
    return p

def make_motor_bracket():
    """SLP-400 电机支架 70x90x8"""
    p = (cq.Workplane("XY")
         .box(BRACKET_W, BRACKET_H, PLATE_THICK, centered=(True, True, False))
         )
    # 中心通孔 φ28
    p = p.faces(">Z").workplane().hole(BRACKET_CENTER_HOLE)
    # NEMA23 安装孔 ×4 (PCD 47.1)
    r = 47.1 / 2
    for ang in [45, 135, 225, 315]:
        rad = math.radians(ang)
        hx = r * math.cos(rad)
        hy = r * math.sin(rad)
        p = p.faces(">Z").workplane().pushPoints([(hx, hy)]).hole(5.5)
    return p

def make_lead_screw():
    """SLP-P01 丝杠 Tr16x4 L350"""
    # 上端轴头 φ12×40
    upper = cq.Workplane("XY").circle(SCREW_SHAFT_D/2).extrude(SCREW_UPPER_SHAFT_L)
    # 螺纹段 φ16×230
    thread = cq.Workplane("XY").circle(SCREW_THREAD_D/2).extrude(SCREW_THREAD_L)
    thread = thread.translate((0, 0, SCREW_UPPER_SHAFT_L + 5))  # +5 过渡
    # 下端轴头 φ12×70
    lower = cq.Workplane("XY").circle(SCREW_SHAFT_D/2).extrude(SCREW_LOWER_SHAFT_L)
    lower = lower.translate((0, 0, SCREW_UPPER_SHAFT_L + 5 + SCREW_THREAD_L + 5))
    result = upper.union(thread).union(lower)
    return result

def make_guide_shaft():
    """SLP-P02 导向轴 φ10 L296"""
    return cq.Workplane("XY").circle(GUIDE_D/2).extrude(GUIDE_L)

def make_kfl001():
    """KFL001 轴承座（简化几何）"""
    # 简化为一个矩形块 55x13x30 含 φ12 中心孔
    p = (cq.Workplane("XY")
         .box(13, 55, KFL_HEIGHT, centered=(True, True, False))
         )
    p = p.faces(">Z").workplane().hole(KFL_BORE)
    return p

def make_t16_nut():
    """T16 法兰铜螺母（简化）"""
    flange = cq.Workplane("XY").circle(NUT_FLANGE_D/2).extrude(NUT_FLANGE_THICK)
    body = cq.Workplane("XY").circle(NUT_BODY_D/2).extrude(NUT_BODY_L)
    body = body.translate((0, 0, NUT_FLANGE_THICK))
    result = flange.union(body)
    # 中心孔
    result = result.faces(">Z").workplane().hole(SCREW_THREAD_D)
    return result

def make_motor():
    """NEMA23 电机（简化）"""
    body = cq.Workplane("XY").box(MOTOR_BODY_SIZE, MOTOR_BODY_SIZE, MOTOR_BODY_L, centered=(True, True, False))
    shaft = cq.Workplane("XY").circle(6.35/2).extrude(21)
    shaft = shaft.translate((0, 0, MOTOR_BODY_L))
    return body.union(shaft)

def make_coupler():
    """L070 联轴器（简化）"""
    return cq.Workplane("XY").circle(COUPLER_OD/2).extrude(COUPLER_L)

def make_lm10uu():
    """LM10UU 直线轴承（简化）"""
    outer = cq.Workplane("XY").circle(LM10UU_OD/2).extrude(LM10UU_L)
    outer = outer.faces(">Z").workplane().hole(GUIDE_D)
    return outer

def make_pulley():
    """GT2 20T 带轮（简化）"""
    return cq.Workplane("XY").circle(PULLEY_OD/2).extrude(9)


def make_assembly() -> cq.Assembly:
    """Build complete assembly."""
    assy = cq.Assembly()

    # Colors
    C_AL = cq.Color(0.15, 0.15, 0.18)       # 黑色阳极氧化铝
    C_STEEL = cq.Color(0.5, 0.5, 0.52)      # 钢
    C_BRONZE = cq.Color(0.7, 0.42, 0.2)     # 铜螺母
    C_MOTOR = cq.Color(0.2, 0.2, 0.22)      # 电机
    C_SILVER = cq.Color(0.75, 0.75, 0.78)   # 导向轴/轴承
    C_BLUE = cq.Color(0.35, 0.55, 0.75)     # 动板（区分色）

    # ── 上固定板 ──
    top_plate = make_top_plate()
    assy.add(top_plate, name="SLP-100_top_plate", color=C_AL,
             loc=cq.Location((0, 0, TOP_PLATE_Z_BOT)))

    # ── 左支撑条 ──
    left_bar = make_support_bar()
    assy.add(left_bar, name="SLP-200_left_bar", color=C_AL,
             loc=cq.Location((LEFT_BAR_X_CENTER, 0, SUP_BAR_Z_BOT)))

    # ── 右支撑条 (丝杠/导向轴孔 Y 对称翻转) ──
    right_bar = make_support_bar()  # 简化：用相同形状
    assy.add(right_bar, name="SLP-201_right_bar", color=C_AL,
             loc=cq.Location((RIGHT_BAR_X_CENTER, 0, SUP_BAR_Z_BOT)))

    # ── 动板 (放在行程中位 Z=140) ──
    mid_z = (STROKE_Z_MIN + STROKE_Z_MAX) / 2  # ≈139
    mov_plate = make_moving_plate()
    assy.add(mov_plate, name="SLP-300_moving_plate", color=C_BLUE,
             loc=cq.Location((0, 0, mid_z)))

    # ── 丝杠 ×2 ──
    for name, x, y in [("LS1", -LS_X, LS_Y), ("LS2", LS_X, -LS_Y)]:
        screw = make_lead_screw()
        assy.add(screw, name=f"SLP-P01_{name}", color=C_STEEL,
                 loc=cq.Location((x, y, SCREW_Z_BOT)))

    # ── 导向轴 ×2 ──
    for name, x, y in [("GS1", GS_X, GS_Y), ("GS2", -GS_X, -GS_Y)]:
        shaft = make_guide_shaft()
        assy.add(shaft, name=f"SLP-P02_{name}", color=C_SILVER,
                 loc=cq.Location((x, y, GUIDE_Z_BOT)))

    # ── KFL001 ×4 ──
    for label, x, y, z in [
        ("upper_LS1", -LS_X, LS_Y, TOP_PLATE_Z_TOP),
        ("upper_LS2", LS_X, -LS_Y, TOP_PLATE_Z_TOP),
        ("lower_LS1", -LS_X, LS_Y, SUP_BAR_Z_TOP),
        ("lower_LS2", LS_X, -LS_Y, SUP_BAR_Z_TOP),
    ]:
        kfl = make_kfl001()
        assy.add(kfl, name=f"KFL001_{label}", color=C_SILVER,
                 loc=cq.Location((x, y, z)))

    # ── T16 螺母 ×2 (在动板上) ──
    for label, x, y in [("LS1", -LS_X, LS_Y), ("LS2", LS_X, -LS_Y)]:
        nut = make_t16_nut()
        nut_z = mid_z - (NUT_FLANGE_THICK - NUT_RECESS_DEPTH)  # 法兰嵌入沉台
        assy.add(nut, name=f"T16_nut_{label}", color=C_BRONZE,
                 loc=cq.Location((x, y, nut_z)))

    # ── LM10UU ×2 ──
    for label, x, y in [("GS1", GS_X, GS_Y), ("GS2", -GS_X, -GS_Y)]:
        lm = make_lm10uu()
        lm_z = mid_z + (PLATE_THICK - LM10UU_L) / 2  # 居中于板厚
        assy.add(lm, name=f"LM10UU_{label}", color=C_SILVER,
                 loc=cq.Location((x, y, lm_z)))

    # ── 电机支架 ──
    bracket = make_motor_bracket()
    assy.add(bracket, name="SLP-400_bracket", color=C_AL,
             loc=cq.Location((RIGHT_BAR_X_CENTER, -LS_Y, BRACKET_Z_BOT)))

    # ── 电机 ──
    motor = make_motor()
    assy.add(motor, name="NEMA23_motor", color=C_MOTOR,
             loc=cq.Location((LS_X, -LS_Y, MOTOR_Z_BOT)))

    # ── 联轴器 ──
    coupler = make_coupler()
    assy.add(coupler, name="L070_coupler", color=C_SILVER,
             loc=cq.Location((LS_X, -LS_Y, -48)))  # Z=-48 to -18

    # ── GT2 带轮 ×2 ──
    for label, x, y in [("LS1", -LS_X, LS_Y), ("LS2", LS_X, -LS_Y)]:
        pulley = make_pulley()
        assy.add(pulley, name=f"GT2_pulley_{label}", color=C_STEEL,
                 loc=cq.Location((x, y, PULLEY_Z_BOT)))

    return assy


def export_assembly(output_dir: str, glb: bool = True) -> str:
    """Build and export the full assembly STEP (and optionally GLB)."""
    assy = make_assembly()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "SLP-000_assembly.step")
    assy.save(path, "STEP")
    print(f"Exported: {path}")
    if glb:
        glb_path = os.path.join(output_dir, "SLP-000_assembly.glb")
        assy.save(glb_path, "GLTF")
        print(f"Exported: {glb_path}")
    return path


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "..", "output", "lifting_platform")
    os.makedirs(out, exist_ok=True)
    export_assembly(out)
