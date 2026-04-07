"""
Top-Level Assembly — 末端执行机构 (EE-000)

Auto-generated scaffold by codegen/gen_assembly.py
Source: D:\Work\cad-spec-gen\cad\end_effector\CAD_SPEC.md
Generated: 2026-04-07 19:42

Coordinate system:
- Origin at assembly geometric center
- 垂直方向（平行于重力）

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
    ├── GIS-EE-001-09 FFC线束总成
    ├── GIS-EE-001-10 ZIF连接器
    ├── GIS-EE-001-11 Igus拖链段
    ├── GIS-EE-001-12 定位销
  ├── GIS-EE-002 工位1涂抹模块
    ├── GIS-EE-002-01 涂抹模块壳体
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
    from ee_001_01 import make_ee_001_01
    from ee_001_02 import make_ee_001_02
    from ee_001_08 import make_ee_001_08
    from ee_002_01 import make_ee_002_01
    from ee_003_03 import make_ee_003_03
    from ee_003_04 import make_ee_003_04
    from ee_004_01 import make_ee_004_01
    from ee_004_12 import make_ee_004_12
    from ee_005_02 import make_ee_005_02
    from ee_006_01 import make_ee_006_01
    from ee_006_03 import make_ee_006_03
    from std_ee_001_03 import make_std_ee_001_03
    from std_ee_001_04 import make_std_ee_001_04
    from std_ee_001_05 import make_std_ee_001_05
    from std_ee_001_06 import make_std_ee_001_06
    from std_ee_001_07 import make_std_ee_001_07
    from std_ee_001_09 import make_std_ee_001_09
    from std_ee_001_10 import make_std_ee_001_10
    from std_ee_002_02 import make_std_ee_002_02
    from std_ee_002_03 import make_std_ee_002_03
    from std_ee_002_05 import make_std_ee_002_05
    from std_ee_003_01 import make_std_ee_003_01
    from std_ee_003_02 import make_std_ee_003_02
    from std_ee_003_08 import make_std_ee_003_08
    from std_ee_004_03 import make_std_ee_004_03
    from std_ee_004_04 import make_std_ee_004_04
    from std_ee_004_06 import make_std_ee_004_06
    from std_ee_004_07 import make_std_ee_004_07
    from std_ee_004_08 import make_std_ee_004_08
    from std_ee_004_09 import make_std_ee_004_09
    from std_ee_004_11 import make_std_ee_004_11
    from std_ee_004_13 import make_std_ee_004_13
    from std_ee_005_01 import make_std_ee_005_01
    from std_ee_005_03 import make_std_ee_005_03
    from std_ee_006_04 import make_std_ee_006_04
    from std_ee_006_05 import make_std_ee_006_05

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
    C_STD_CONN = cq.Color(0.25, 0.25, 0.25)
    C_STD_TANK = cq.Color(0.82, 0.82, 0.85)
    C_STD_PUMP = cq.Color(0.55, 0.55, 0.6)
    C_STD_SENSOR = cq.Color(0.2, 0.2, 0.2)
    C_STD_BEARING = cq.Color(0.6, 0.6, 0.65)

    # ═══════ 法兰总成 (0.0°) ═══════

    p_ee_001_01 = make_ee_001_01()
    assy.add(p_ee_001_01, name="EE-001-01", color=C_DARK)

    p_ee_001_02 = make_ee_001_02()
    p_ee_001_02 = p_ee_001_02.translate((0, 0, -27.0))
    assy.add(p_ee_001_02, name="EE-001-02", color=C_DARK)

    p_std_ee_001_03 = make_std_ee_001_03()
    p_std_ee_001_03 = p_std_ee_001_03.translate((0, 0, -25.0))
    assy.add(p_std_ee_001_03, name="STD-EE-001-03", color=C_STD_SEAL)

    p_std_ee_001_04 = make_std_ee_001_04()
    p_std_ee_001_04 = p_std_ee_001_04.translate((0.0, 0.0, 130.0))
    assy.add(p_std_ee_001_04, name="STD-EE-001-04", color=C_STD_SPRING)

    p_std_ee_001_05 = make_std_ee_001_05()
    p_std_ee_001_05 = p_std_ee_001_05.translate((0, 0, 73.0))
    assy.add(p_std_ee_001_05, name="STD-EE-001-05", color=C_STD_MOTOR)

    p_std_ee_001_06 = make_std_ee_001_06()
    p_std_ee_001_06 = p_std_ee_001_06.translate((0, 0, 73.0))
    assy.add(p_std_ee_001_06, name="STD-EE-001-06", color=C_STD_REDUCER)

    p_std_ee_001_07 = make_std_ee_001_07()
    p_std_ee_001_07 = p_std_ee_001_07.translate((0.0, 0.0, 152.0))
    assy.add(p_std_ee_001_07, name="STD-EE-001-07", color=C_STD_SPRING)

    p_ee_001_08 = make_ee_001_08()
    assy.add(p_ee_001_08, name="EE-001-08", color=C_DARK)

    p_std_ee_001_09 = make_std_ee_001_09()
    p_std_ee_001_09 = p_std_ee_001_09.translate((0.0, 0.0, 174.0))
    assy.add(p_std_ee_001_09, name="STD-EE-001-09", color=C_STD_CONN)

    p_std_ee_001_10 = make_std_ee_001_10()
    p_std_ee_001_10 = p_std_ee_001_10.translate((0.0, 0.0, 196.0))
    assy.add(p_std_ee_001_10, name="STD-EE-001-10", color=C_STD_CONN)

    # ═══════ 工位1涂抹模块 (0.0°) ═══════
    _a = 0.0
    _rad = math.radians(_a)
    _tx = 65.0 * math.cos(_rad)
    _ty = 65.0 * math.sin(_rad)
    _tz = 0.0

    p_ee_002_01 = make_ee_002_01()
    p_ee_002_01 = p_ee_002_01.translate((0.0, 0.0, -10.0))
    p_ee_002_01 = _station_transform(p_ee_002_01, _a, _tx, _ty, _tz)
    assy.add(p_ee_002_01, name="EE-002-01", color=C_SILVER)

    p_std_ee_002_02 = make_std_ee_002_02()
    # Orient: axis horizontal per §6.2: 储罐轴∥XY（水平径向外伸）**
    # Rule:   
    p_std_ee_002_02 = p_std_ee_002_02.rotate((0,0,0), (1,0,0), 90)
    p_std_ee_002_02 = p_std_ee_002_02.translate((19.0, 0.0, 0.0))
    p_std_ee_002_02 = _station_transform(p_std_ee_002_02, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_002_02, name="STD-EE-002-02", color=C_STD_TANK)

    p_std_ee_002_03 = make_std_ee_002_03()
    p_std_ee_002_03 = p_std_ee_002_03.translate((0.0, 0.0, -32.0))
    p_std_ee_002_03 = _station_transform(p_std_ee_002_03, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_002_03, name="STD-EE-002-03", color=C_STD_PUMP)

    p_std_ee_002_05 = make_std_ee_002_05()
    p_std_ee_002_05 = p_std_ee_002_05.translate((0.0, 0.0, -76.0))
    p_std_ee_002_05 = _station_transform(p_std_ee_002_05, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_002_05, name="STD-EE-002-05", color=C_STD_CONN)

    # ═══════ 工位2 AE检测模块 (90.0°) ═══════
    _a = 90.0
    _rad = math.radians(_a)
    _tx = 65.0 * math.cos(_rad)
    _ty = 65.0 * math.sin(_rad)
    _tz = 0.0

    p_std_ee_003_01 = make_std_ee_003_01()
    p_std_ee_003_01 = p_std_ee_003_01.translate((0.0, 0.0, -54.0))
    p_std_ee_003_01 = _station_transform(p_std_ee_003_01, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_003_01, name="STD-EE-003-01", color=C_STD_SENSOR)

    p_std_ee_003_02 = make_std_ee_003_02()
    p_std_ee_003_02 = p_std_ee_003_02.translate((0.0, 0.0, -76.0))
    p_std_ee_003_02 = _station_transform(p_std_ee_003_02, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_003_02, name="STD-EE-003-02", color=C_STD_SENSOR)

    p_ee_003_03 = make_ee_003_03()
    p_ee_003_03 = p_ee_003_03.translate((0.0, 0.0, -10.0))
    p_ee_003_03 = _station_transform(p_ee_003_03, _a, _tx, _ty, _tz)
    assy.add(p_ee_003_03, name="EE-003-03", color=C_AMBER)

    p_ee_003_04 = make_ee_003_04()
    p_ee_003_04 = p_ee_003_04.translate((0.0, 0.0, -32.0))
    p_ee_003_04 = _station_transform(p_ee_003_04, _a, _tx, _ty, _tz)
    assy.add(p_ee_003_04, name="EE-003-04", color=C_AMBER)

    p_std_ee_003_08 = make_std_ee_003_08()
    p_std_ee_003_08 = p_std_ee_003_08.translate((0.0, 0.0, -142.0))
    p_std_ee_003_08 = _station_transform(p_std_ee_003_08, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_003_08, name="STD-EE-003-08", color=C_STD_CONN)

    # ═══════ 工位3卷带清洁模块 (180.0°) ═══════
    _a = 180.0
    _rad = math.radians(_a)
    _tx = 65.0 * math.cos(_rad)
    _ty = 65.0 * math.sin(_rad)
    _tz = 0.0

    p_ee_004_01 = make_ee_004_01()
    p_ee_004_01 = p_ee_004_01.translate((0.0, 0.0, -10.0))
    p_ee_004_01 = _station_transform(p_ee_004_01, _a, _tx, _ty, _tz)
    assy.add(p_ee_004_01, name="EE-004-01", color=C_BLUE)

    p_std_ee_004_03 = make_std_ee_004_03()
    p_std_ee_004_03 = p_std_ee_004_03.translate((0, 0, 73.0))
    p_std_ee_004_03 = _station_transform(p_std_ee_004_03, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_004_03, name="STD-EE-004-03", color=C_STD_MOTOR)

    p_std_ee_004_04 = make_std_ee_004_04()
    p_std_ee_004_04 = p_std_ee_004_04.translate((0, 0, 73.0))
    p_std_ee_004_04 = _station_transform(p_std_ee_004_04, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_004_04, name="STD-EE-004-04", color=C_STD_REDUCER)

    p_std_ee_004_06 = make_std_ee_004_06()
    p_std_ee_004_06 = p_std_ee_004_06.translate((0.0, 0.0, -188.0))
    p_std_ee_004_06 = _station_transform(p_std_ee_004_06, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_004_06, name="STD-EE-004-06", color=C_STD_SPRING)

    p_std_ee_004_07 = make_std_ee_004_07()
    p_std_ee_004_07 = p_std_ee_004_07.translate((0.0, 0.0, -210.0))
    p_std_ee_004_07 = _station_transform(p_std_ee_004_07, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_004_07, name="STD-EE-004-07", color=C_STD_SENSOR)

    p_std_ee_004_08 = make_std_ee_004_08()
    p_std_ee_004_08 = p_std_ee_004_08.translate((0.0, 0.0, -99.0))
    p_std_ee_004_08 = _station_transform(p_std_ee_004_08, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_004_08, name="STD-EE-004-08", color=C_STD_TANK)

    p_std_ee_004_09 = make_std_ee_004_09()
    p_std_ee_004_09 = p_std_ee_004_09.translate((0.0, 0.0, -232.0))
    p_std_ee_004_09 = _station_transform(p_std_ee_004_09, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_004_09, name="STD-EE-004-09", color=C_STD_PUMP)

    p_std_ee_004_11 = make_std_ee_004_11()
    p_std_ee_004_11 = p_std_ee_004_11.translate((0.0, 0.0, -282.0))
    p_std_ee_004_11 = _station_transform(p_std_ee_004_11, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_004_11, name="STD-EE-004-11", color=C_STD_BEARING)

    p_ee_004_12 = make_ee_004_12()
    p_ee_004_12 = p_ee_004_12.translate((0.0, 0.0, -32.0))
    p_ee_004_12 = _station_transform(p_ee_004_12, _a, _tx, _ty, _tz)
    assy.add(p_ee_004_12, name="EE-004-12", color=C_BLUE)

    p_std_ee_004_13 = make_std_ee_004_13()
    p_std_ee_004_13 = p_std_ee_004_13.translate((0.0, 0.0, -252.0))
    p_std_ee_004_13 = _station_transform(p_std_ee_004_13, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_004_13, name="STD-EE-004-13", color=C_STD_CONN)

    # ═══════ 工位4 UHF模块（方案A） (270.0°) ═══════
    _a = 270.0
    _rad = math.radians(_a)
    _tx = 65.0 * math.cos(_rad)
    _ty = 65.0 * math.sin(_rad)
    _tz = 0.0

    p_std_ee_005_01 = make_std_ee_005_01()
    p_std_ee_005_01 = p_std_ee_005_01.translate((0.0, 0.0, -32.0))
    p_std_ee_005_01 = _station_transform(p_std_ee_005_01, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_005_01, name="STD-EE-005-01", color=C_STD_SENSOR)

    p_ee_005_02 = make_ee_005_02()
    p_ee_005_02 = p_ee_005_02.translate((0.0, 0.0, -10.0))
    p_ee_005_02 = _station_transform(p_ee_005_02, _a, _tx, _ty, _tz)
    assy.add(p_ee_005_02, name="EE-005-02", color=C_GREEN)

    p_std_ee_005_03 = make_std_ee_005_03()
    p_std_ee_005_03 = p_std_ee_005_03.translate((0.0, 0.0, -54.0))
    p_std_ee_005_03 = _station_transform(p_std_ee_005_03, _a, _tx, _ty, _tz)
    assy.add(p_std_ee_005_03, name="STD-EE-005-03", color=C_STD_CONN)

    # ═══════ 信号调理模块 (0.0°) ═══════

    p_ee_006_01 = make_ee_006_01()
    p_ee_006_01 = p_ee_006_01.translate((0.0, 0.0, 147.5))
    assy.add(p_ee_006_01, name="EE-006-01", color=C_BRONZE)

    p_ee_006_03 = make_ee_006_03()
    p_ee_006_03 = p_ee_006_03.translate((0.0, 0.0, 187.0))
    assy.add(p_ee_006_03, name="EE-006-03", color=C_BRONZE)

    p_std_ee_006_04 = make_std_ee_006_04()
    p_std_ee_006_04 = p_std_ee_006_04.translate((0.0, 0.0, 231.0))
    assy.add(p_std_ee_006_04, name="STD-EE-006-04", color=C_STD_CONN)

    p_std_ee_006_05 = make_std_ee_006_05()
    p_std_ee_006_05 = p_std_ee_006_05.translate((0.0, 0.0, 251.0))
    assy.add(p_std_ee_006_05, name="STD-EE-006-05", color=C_STD_CONN)

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
