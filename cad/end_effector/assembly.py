"""
Top-Level Assembly — 末端执行机构 (EE-000)

Auto-generated scaffold by codegen/gen_assembly.py
Source: D:\Work\cad-spec-gen\cad\end_effector\CAD_SPEC.md
Generated: 2026-04-03 16:18

Coordinate system:
- Origin at assembly geometric center
- Z-up, X-right

Assembly hierarchy:
  ├── GIS-EE-001 法兰总成
    ├── GIS-EE-001-01 法兰本体（含十字悬臂）
    ├── GIS-EE-001-02 PEEK绝缘段
    ├── GIS-EE-001-03 O型圈
    ├── GIS-EE-001-04 碟形弹簧垫圈
    ├── GIS-EE-001-05 伺服电机
    ├── GIS-EE-001-06 行星减速器
    ├── GIS-EE-001-07 弹簧销组件（含弹簧）
    ├── GIS-EE-001-08 ISO 9409适配板
  ├── GIS-EE-002 工位1涂抹模块
    ├── GIS-EE-002-01 涂抹模块壳体
    ├── GIS-EE-002-02 储罐
    ├── GIS-EE-002-03 齿轮泵
    ├── GIS-EE-002-04 刮涂头
    ├── GIS-EE-002-05 LEMO插头
"""

import cadquery as cq
import math
import os
import params  # noqa: F401 — params loaded for downstream use


def _station_transform(part, angle: float, tx: float, ty: float, tz: float):
    """Apply station rotation + translation."""
    part = part.rotate((0, 0, 0), (0, 0, 1), angle)
    part = part.translate((tx, ty, tz))
    return part


def make_assembly() -> cq.Assembly:
    """Build CadQuery Assembly with split sub-components."""
    from ee_001_01 import make_ee_001_01
    from ee_001_02 import make_ee_001_02
    from ee_001_08 import make_ee_001_08
    from ee_002_01 import make_ee_002_01
    from ee_003_03 import make_ee_003_03
    from ee_003_04 import make_ee_003_04
    from ee_004_01 import make_ee_004_01
    from ee_005_02 import make_ee_005_02
    from ee_006_01 import make_ee_006_01
    from ee_006_03 import make_ee_006_03
    from std_ee_001_03 import make_std_ee_001_03
    from std_ee_001_04 import make_std_ee_001_04
    from std_ee_001_05 import make_std_ee_001_05
    from std_ee_001_06 import make_std_ee_001_06
    from std_ee_001_07 import make_std_ee_001_07
    from std_ee_002_02 import make_std_ee_002_02
    from std_ee_002_03 import make_std_ee_002_03
    from std_ee_002_05 import make_std_ee_002_05
    from std_ee_003_01 import make_std_ee_003_01
    from std_ee_003_02 import make_std_ee_003_02
    from std_ee_004_03 import make_std_ee_004_03
    from std_ee_004_04 import make_std_ee_004_04
    from std_ee_004_06 import make_std_ee_004_06
    from std_ee_004_08 import make_std_ee_004_08
    from std_ee_004_09 import make_std_ee_004_09
    from std_ee_005_01 import make_std_ee_005_01

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
    C_STD_SEAL = cq.Color(0.08, 0.08, 0.08)
    C_STD_SPRING = cq.Color(0.78, 0.68, 0.2)
    C_STD_MOTOR = cq.Color(0.75, 0.75, 0.78)
    C_STD_REDUCER = cq.Color(0.7, 0.7, 0.72)
    C_STD_TANK = cq.Color(0.82, 0.82, 0.85)
    C_STD_PUMP = cq.Color(0.55, 0.55, 0.6)
    C_STD_CONN = cq.Color(0.25, 0.25, 0.25)
    C_STD_SENSOR = cq.Color(0.2, 0.2, 0.2)

    # ═══════ 法兰总成 (0.0°) ═══════

    p_ee_001_01 = make_ee_001_01()
    assy.add(p_ee_001_01, name="EE-001-01", color=C_DARK)

    p_ee_001_02 = make_ee_001_02()
    assy.add(p_ee_001_02, name="EE-001-02", color=C_DARK)

    p_std_ee_001_03 = make_std_ee_001_03()
    assy.add(p_std_ee_001_03, name="STD-GIS-EE-001-03", color=C_STD_SEAL)

    p_std_ee_001_04 = make_std_ee_001_04()
    assy.add(p_std_ee_001_04, name="STD-GIS-EE-001-04", color=C_STD_SPRING)

    p_std_ee_001_05 = make_std_ee_001_05()
    assy.add(p_std_ee_001_05, name="STD-GIS-EE-001-05", color=C_STD_MOTOR)

    p_std_ee_001_06 = make_std_ee_001_06()
    assy.add(p_std_ee_001_06, name="STD-GIS-EE-001-06", color=C_STD_REDUCER)

    p_std_ee_001_07 = make_std_ee_001_07()
    assy.add(p_std_ee_001_07, name="STD-GIS-EE-001-07", color=C_STD_SPRING)

    p_ee_001_08 = make_ee_001_08()
    assy.add(p_ee_001_08, name="EE-001-08", color=C_DARK)

    # ═══════ 工位1涂抹模块 (0.0°) ═══════

    p_ee_002_01 = make_ee_002_01()
    assy.add(p_ee_002_01, name="EE-002-01", color=C_SILVER)

    p_std_ee_002_02 = make_std_ee_002_02()
    assy.add(p_std_ee_002_02, name="STD-GIS-EE-002-02", color=C_STD_TANK)

    p_std_ee_002_03 = make_std_ee_002_03()
    assy.add(p_std_ee_002_03, name="STD-GIS-EE-002-03", color=C_STD_PUMP)

    p_std_ee_002_05 = make_std_ee_002_05()
    assy.add(p_std_ee_002_05, name="STD-GIS-EE-002-05", color=C_STD_CONN)

    # ═══════ 工位2 AE检测模块 (0.0°) ═══════

    p_std_ee_003_01 = make_std_ee_003_01()
    assy.add(p_std_ee_003_01, name="STD-GIS-EE-003-01", color=C_STD_SENSOR)

    p_std_ee_003_02 = make_std_ee_003_02()
    assy.add(p_std_ee_003_02, name="STD-GIS-EE-003-02", color=C_STD_SENSOR)

    p_ee_003_03 = make_ee_003_03()
    assy.add(p_ee_003_03, name="EE-003-03", color=C_AMBER)

    p_ee_003_04 = make_ee_003_04()
    assy.add(p_ee_003_04, name="EE-003-04", color=C_AMBER)

    # ═══════ 工位3卷带清洁模块 (0.0°) ═══════

    p_ee_004_01 = make_ee_004_01()
    assy.add(p_ee_004_01, name="EE-004-01", color=C_BLUE)

    p_std_ee_004_03 = make_std_ee_004_03()
    assy.add(p_std_ee_004_03, name="STD-GIS-EE-004-03", color=C_STD_MOTOR)

    p_std_ee_004_04 = make_std_ee_004_04()
    assy.add(p_std_ee_004_04, name="STD-GIS-EE-004-04", color=C_STD_REDUCER)

    p_std_ee_004_06 = make_std_ee_004_06()
    assy.add(p_std_ee_004_06, name="STD-GIS-EE-004-06", color=C_STD_SPRING)

    p_std_ee_004_08 = make_std_ee_004_08()
    assy.add(p_std_ee_004_08, name="STD-GIS-EE-004-08", color=C_STD_TANK)

    p_std_ee_004_09 = make_std_ee_004_09()
    assy.add(p_std_ee_004_09, name="STD-GIS-EE-004-09", color=C_STD_PUMP)

    # ═══════ 工位4 UHF模块 (0.0°) ═══════

    p_std_ee_005_01 = make_std_ee_005_01()
    assy.add(p_std_ee_005_01, name="STD-GIS-EE-005-01", color=C_STD_SENSOR)

    p_ee_005_02 = make_ee_005_02()
    assy.add(p_ee_005_02, name="EE-005-02", color=C_GREEN)

    # ═══════ 信号调理模块 (0.0°) ═══════

    p_ee_006_01 = make_ee_006_01()
    assy.add(p_ee_006_01, name="EE-006-01", color=C_BRONZE)

    p_ee_006_03 = make_ee_006_03()
    assy.add(p_ee_006_03, name="EE-006-03", color=C_BRONZE)

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
