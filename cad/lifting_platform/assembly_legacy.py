"""
Top-Level Assembly — 丝杠式升降平台 (SLP-000)

Auto-generated scaffold by codegen/gen_assembly.py
Source: D:\Work\cad-spec-gen\cad\lifting_platform\CAD_SPEC.md
Generated: 2026-04-04 13:51

Coordinate system:
- Origin at 下板顶面中心（几何基准点）
- Z-up, X-right

Assembly hierarchy:
  ├── UNKNOWN 未分组
    ├── SLP-100 上固定板
    ├── SLP-200 左支撑条
    ├── SLP-201 右支撑条
    ├── SLP-300 动板
    ├── SLP-400 电机支架
    ├── SLP-403 下限位传感器支架
    ├── SLP-404 上限位传感器支架
    ├── SLP-500 同步带护罩
    ├── SLP-P01 丝杠 L350
    ├── SLP-P02 导向轴 L296
    ├── SLP-C01 T16 螺母 C7
    ├── SLP-C02 LM10UU
    ├── SLP-C03 KFL001
    ├── SLP-C04 GT2 20T 开式带轮 φ12
"""

import cadquery as cq
import math
import os
import params  # noqa: F401


def _station_transform(part, angle: float, tx: float, ty: float, tz: float):
    """Apply station rotation + translation."""
    part = part.rotate((0, 0, 0), (0, 0, 1), angle)
    part = part.translate((tx, ty, tz))
    return part


def make_assembly() -> cq.Assembly:
    """Build CadQuery Assembly with split sub-components."""
    from p100 import make_p100
    from p200 import make_p200
    from p201 import make_p201
    from p300 import make_p300
    from p400 import make_p400
    from p403 import make_p403
    from p404 import make_p404
    from p500 import make_p500
    from p01 import make_p01
    from p02 import make_p02
    from std_c02 import make_std_c02
    from std_c03 import make_std_c03
    from std_c06 import make_std_c06
    from std_c07 import make_std_c07
    from std_f11 import make_std_f11
    from std_f12 import make_std_f12

    assy = cq.Assembly()

    # ── Colors (custom parts) ──
    C_DARK = cq.Color(0.15, 0.15, 0.15)
    C_SILVER = cq.Color(0.8, 0.8, 0.82)
    C_AMBER = cq.Color(0.85, 0.65, 0.13)
    C_BLUE = cq.Color(0.35, 0.55, 0.75)
    C_GREEN = cq.Color(0.15, 0.5, 0.25)
    C_BRONZE = cq.Color(0.7, 0.42, 0.2)
    C_PURPLE = cq.Color(0.5, 0.18, 0.65)
    C_RUBBER = cq.Color(0.1, 0.1, 0.1)

    # ── Colors (standard/purchased parts) ──
    C_STD_BEARING = cq.Color(0.6, 0.6, 0.65)
    C_STD_CONN = cq.Color(0.25, 0.25, 0.25)
    C_STD_MOTOR = cq.Color(0.75, 0.75, 0.78)
    C_STD_SEAL = cq.Color(0.08, 0.08, 0.08)
    C_STD_SENSOR = cq.Color(0.2, 0.2, 0.2)

    # ═══════ Spatial layout — §4 diagonal pattern ═══════
    # Origin: bottom plate top surface center (Z=0)
    # Shaft XY positions:
    #   LS1 (lead screw 1): (-60, +30)
    #   LS2 (lead screw 2): (+60, -30) — motor-connected
    #   GS1 (guide shaft 1): (+60, +30)
    #   GS2 (guide shaft 2): (-60, -30)

    # ── SLP-100 上固定板 ─────────────────────────────────────────────────────
    # §2: 200×160×8 mm, board bottom Z=+272, centered at (0,0)
    # Local: flat on XY, bottom at Z=0 → translate Z=+272
    p_p100 = make_p100()
    p_p100 = p_p100.translate((0.0, 0.0, 272.0))
    assy.add(p_p100, name="SLP-100", color=C_DARK)

    # ── SLP-200 左支撑条 ─────────────────────────────────────────────────────
    # §3.1: 40(X)×260(Y)×15(Z) — but 260mm is the HEIGHT (vertical).
    # Local: 40(X)×260(Y)×15(Z), bottom at Z=0.
    # Need to rotate -90° around X so Y→Z (260mm becomes vertical height).
    # After rotation: 40(X)×15(Y)×260(Z), bottom at Y=0→Z=0.
    # Position: X=-80 (left side), Y=0, base at Z=0 (support bar bottom),
    #   top at Z=260. §3.1 says Z=[-8, 0] for the 8mm plate, but the
    #   visual table says 260mm tall. Using user spec: X=-80, Y=0, Z=[0,260].
    p_p200 = make_p200()
    p_p200 = p_p200.rotate((0, 0, 0), (1, 0, 0), -90)
    p_p200 = p_p200.translate((-80.0, 0.0, 0.0))
    assy.add(p_p200, name="SLP-200", color=C_DARK)

    # ── SLP-201 右支撑条 ─────────────────────────────────────────────────────
    # Mirror of SLP-200 at X=+80
    p_p201 = make_p201()
    p_p201 = p_p201.rotate((0, 0, 0), (1, 0, 0), -90)
    p_p201 = p_p201.translate((80.0, 0.0, 0.0))
    assy.add(p_p201, name="SLP-201", color=C_DARK)

    # ── SLP-300 动板 ─────────────────────────────────────────────────────────
    # §4: 160×120×8 mm, slides Z=+43 to +235. Mid-stroke ~Z=100.
    # Local: flat on XY, bottom at Z=0 → translate Z=+100 (mid-stroke)
    p_p300 = make_p300()
    p_p300 = p_p300.translate((0.0, 0.0, 100.0))
    assy.add(p_p300, name="SLP-300", color=C_AMBER)

    # ── SLP-400 电机支架 ─────────────────────────────────────────────────────
    # §8.2: 70×90×8 mm, hangs below right support bar bottom face.
    # Local: flat on XY, bottom at Z=0, top at Z=+8.
    # Assembly: top face at Z=-8 (flush with support bar bottom).
    # Translate Z=-16 (top at -16+8=-8). Center at (+80, 0) per user spec.
    p_p400 = make_p400()
    p_p400 = p_p400.translate((80.0, 0.0, -16.0))
    assy.add(p_p400, name="SLP-400", color=C_BLUE)

    # ── SLP-403 下限位传感器支架 ─────────────────────────────────────────────
    # §9.2: L-shaped, foot at Z=0, arm rises to Z=+43.
    # Mounts on left support bar. User says: left support bar, Z≈43.
    # Position: (-80, 0), foot on support bar top face.
    # The bracket's foot sits at Z=0 (support bar top surface), arm up.
    # Translate to (-80, 0, 0).
    p_p403 = make_p403()
    p_p403 = p_p403.translate((-80.0, 0.0, 0.0))
    assy.add(p_p403, name="SLP-403", color=C_GREEN)

    # ── SLP-404 上限位传感器支架 ─────────────────────────────────────────────
    # §9.2: Inverted L, top face at Z=0 (mounting face), hangs down 32mm.
    # Mounts at top plate bottom face Z=+272. Center at (-80, 0).
    # Local: top at Z=0. Translate Z=+272.
    p_p404 = make_p404()
    p_p404 = p_p404.translate((-80.0, 0.0, 272.0))
    assy.add(p_p404, name="SLP-404", color=C_GREEN)

    # ── SLP-500 同步带护罩 ───────────────────────────────────────────────────
    # §10.2: 170×80×40 U-shaped, top at Z=0 local, extends down 40mm.
    # Assembly: top at Z=-8 (bottom plate underside), centered at (0,0).
    # Translate Z=-8.
    p_p500 = make_p500()
    p_p500 = p_p500.translate((0.0, 0.0, -8.0))
    assy.add(p_p500, name="SLP-500", color=C_PURPLE)

    # ── SLP-P01 丝杠 ×2 ─────────────────────────────────────────────────────
    # §5.1: 350mm total, bottom at Z=0 local.
    # Assembly: bottom tip at Z=-48 per doc. Two instances at LS1 and LS2.
    # LS1 at (-60, +30), LS2 at (+60, -30)
    p_p01_ls1 = make_p01()
    p_p01_ls1 = p_p01_ls1.translate((-60.0, 30.0, -48.0))
    assy.add(p_p01_ls1, name="SLP-P01-LS1", color=C_SILVER)

    p_p01_ls2 = make_p01()
    p_p01_ls2 = p_p01_ls2.translate((60.0, -30.0, -48.0))
    assy.add(p_p01_ls2, name="SLP-P01-LS2", color=C_SILVER)

    # ── SLP-P02 导向轴 ×2 ───────────────────────────────────────────────────
    # §5.2: 296mm total, bottom at Z=0 local.
    # Assembly: bottom tip at Z=-12 per doc. Two instances at GS1 and GS2.
    # GS1 at (+60, +30), GS2 at (-60, -30)
    p_p02_gs1 = make_p02()
    p_p02_gs1 = p_p02_gs1.translate((60.0, 30.0, -12.0))
    assy.add(p_p02_gs1, name="SLP-P02-GS1", color=C_SILVER)

    p_p02_gs2 = make_p02()
    p_p02_gs2 = p_p02_gs2.translate((-60.0, -30.0, -12.0))
    assy.add(p_p02_gs2, name="SLP-P02-GS2", color=C_SILVER)

    # ── SLP-C02 LM10UU 直线轴承 ×2 ──────────────────────────────────────────
    # On guide shafts at moving plate height. GS1(+60,+30), GS2(-60,-30).
    # Moving plate bottom at Z=100, plate 8mm thick → center ~Z=104.
    p_std_c02_gs1 = make_std_c02()
    p_std_c02_gs1 = p_std_c02_gs1.translate((60.0, 30.0, 100.0))
    assy.add(p_std_c02_gs1, name="STD-SLP-C02-GS1", color=C_STD_BEARING)

    p_std_c02_gs2 = make_std_c02()
    p_std_c02_gs2 = p_std_c02_gs2.translate((-60.0, -30.0, 100.0))
    assy.add(p_std_c02_gs2, name="STD-SLP-C02-GS2", color=C_STD_BEARING)

    # ── SLP-C03 KFL001 轴承座 ×4 ────────────────────────────────────────────
    # 4 units: bottom of each shaft (Z=0) and top of each shaft (Z=272).
    # Bottom pair at LS1(-60,+30) and LS2(+60,-30), top face at Z=0.
    # Top pair at LS1(-60,+30) and LS2(+60,-30), bottom face at Z=272.
    p_std_c03_ls1_bot = make_std_c03()
    p_std_c03_ls1_bot = p_std_c03_ls1_bot.translate((-60.0, 30.0, 0.0))
    assy.add(p_std_c03_ls1_bot, name="STD-SLP-C03-LS1-BOT", color=C_STD_BEARING)

    p_std_c03_ls2_bot = make_std_c03()
    p_std_c03_ls2_bot = p_std_c03_ls2_bot.translate((60.0, -30.0, 0.0))
    assy.add(p_std_c03_ls2_bot, name="STD-SLP-C03-LS2-BOT", color=C_STD_BEARING)

    p_std_c03_ls1_top = make_std_c03()
    p_std_c03_ls1_top = p_std_c03_ls1_top.translate((-60.0, 30.0, 280.0))
    assy.add(p_std_c03_ls1_top, name="STD-SLP-C03-LS1-TOP", color=C_STD_BEARING)

    p_std_c03_ls2_top = make_std_c03()
    p_std_c03_ls2_top = p_std_c03_ls2_top.translate((60.0, -30.0, 280.0))
    assy.add(p_std_c03_ls2_top, name="STD-SLP-C03-LS2-TOP", color=C_STD_BEARING)

    # ── SLP-C06 L070 联轴器 ─────────────────────────────────────────────────
    # Below motor at LS2 position. §1.2: top at Z=-30, bottom at Z=-48.
    # Local: bottom at Z=0, 25mm tall. Translate to Z=-48 (bottom).
    # Actually coupler top=Z=-30, L=18mm per doc spacing. Simplified model
    # is 25mm. Place bottom at Z=-48: translate Z=-48.
    p_std_c06 = make_std_c06()
    p_std_c06 = p_std_c06.translate((60.0, -30.0, -48.0))
    assy.add(p_std_c06, name="STD-SLP-C06", color=C_STD_CONN)

    # ── SLP-C07 NEMA23 电机 ─────────────────────────────────────────────────
    # Below platform at LS2 position. Motor hangs below, shaft pointing up.
    # Local: body Z=[0,50], shaft Z=[50,62]. Shaft tip connects coupler
    # bottom at Z=-48. Translate: tz = -48 - 62 = -110.
    # Result: motor body Z=[-110,-60], shaft tip at Z=-48.
    p_std_c07 = make_std_c07()
    p_std_c07 = p_std_c07.translate((60.0, -30.0, -110.0))
    assy.add(p_std_c07, name="STD-SLP-C07", color=C_STD_MOTOR)

    # ── SLP-F11 PU 缓冲垫 ───────────────────────────────────────────────────
    # PU bumper pads at lower stroke limit. On support bar top face.
    # Place near the lower travel limit area, centered.
    p_std_f11 = make_std_f11()
    p_std_f11 = p_std_f11.translate((0.0, 0.0, 36.0))
    assy.add(p_std_f11, name="STD-SLP-F11", color=C_STD_SEAL)

    # ── SLP-F12 M8 接近开关 ×2 ──────────────────────────────────────────────
    # Proximity sensors on left support bar, detecting moving plate side face.
    # Lower sensor at Z≈43, upper at Z≈240.
    # Sensor is cylinder along +Z, 12mm tall. Mount horizontally (along +X)
    # to detect moving plate −X face. Rotate 90° around Y.
    # Lower sensor near SLP-403 bracket.
    p_std_f12_low = make_std_f12()
    p_std_f12_low = p_std_f12_low.rotate((0, 0, 0), (0, 1, 0), -90)
    p_std_f12_low = p_std_f12_low.translate((-80.0, 0.0, 43.0))
    assy.add(p_std_f12_low, name="STD-SLP-F12-LOW", color=C_STD_SENSOR)

    p_std_f12_high = make_std_f12()
    p_std_f12_high = p_std_f12_high.rotate((0, 0, 0), (0, 1, 0), -90)
    p_std_f12_high = p_std_f12_high.translate((-80.0, 0.0, 240.0))
    assy.add(p_std_f12_high, name="STD-SLP-F12-HIGH", color=C_STD_SENSOR)

    return assy


def export_assembly(output_dir: str, glb: bool = True) -> str:
    """Build and export the full assembly STEP (and optionally GLB)."""
    assy = make_assembly()
    path = os.path.join(output_dir, "SLP-000_assembly.step")
    assy.save(path, "STEP")
    print(f"Exported: {path}")
    if glb:
        glb_path = os.path.join(output_dir, "SLP-000_assembly.glb")
        assy.save(glb_path, "GLTF")
        print(f"Exported: {glb_path}")
    return path


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out, exist_ok=True)
    export_assembly(out)
