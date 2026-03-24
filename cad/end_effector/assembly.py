"""
Top-Level Assembly — 末端执行机构 (EE-000)

Auto-generated scaffold by codegen/gen_assembly.py
Source: D:\cad-skill\cad\end_effector\CAD_SPEC.md
Generated: 2026-03-24 22:51

Coordinate system:
- Origin at flange rotation center
- Z=0: back face, Z+: workspace side

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
from params import (
    STATION_ANGLES,
    MOUNT_CENTER_R,
    FLANGE_AL_THICK,
)


def _station_transform(part, angle: float, tx: float, ty: float, tz: float):
    """Apply station rotation + translation."""
    part = part.rotate((0, 0, 0), (0, 0, 1), angle)
    part = part.translate((tx, ty, tz))
    return part


def make_assembly() -> cq.Assembly:
    """Build CadQuery Assembly with split sub-components."""
    from module_001 import make_001_01, make_001_02, make_001_03, make_001_04, make_001_05, make_001_06, make_001_07, make_001_08, make_001_09, make_001_10, make_001_11, make_001_12
    from module_002 import make_002_01, make_002_02, make_002_03, make_002_04, make_002_05
    from module_003 import make_003_01, make_003_02, make_003_03, make_003_04, make_003_05, make_003_06, make_003_07, make_003_08, make_003_09
    from module_004 import make_004_01, make_004_02, make_004_03, make_004_04, make_004_05, make_004_06, make_004_07, make_004_08, make_004_09, make_004_10, make_004_11, make_004_12, make_004_13
    from module_005 import make_005_01, make_005_02, make_005_03
    from module_006 import make_006_01, make_006_02, make_006_03, make_006_04, make_006_05, make_006_06

    assy = cq.Assembly()

    # ── Colors ──
    C_DARK = cq.Color(0.15, 0.15, 0.15)
    C_SILVER = cq.Color(0.8, 0.8, 0.82)
    C_AMBER = cq.Color(0.85, 0.65, 0.13)
    C_BLUE = cq.Color(0.35, 0.55, 0.75)
    C_GREEN = cq.Color(0.15, 0.5, 0.25)
    C_BRONZE = cq.Color(0.7, 0.42, 0.2)
    C_PURPLE = cq.Color(0.5, 0.18, 0.65)
    C_RUBBER = cq.Color(0.1, 0.1, 0.1)

    # ═══════ 法兰总成 (0°) ═══════

    p_001_01 = make_001_01()
    assy.add(p_001_01, name="EE-001-01", color=C_DARK)

    p_001_02 = make_001_02()
    assy.add(p_001_02, name="EE-001-02", color=C_DARK)

    p_001_03 = make_001_03()
    assy.add(p_001_03, name="EE-001-03", color=C_DARK)

    p_001_04 = make_001_04()
    assy.add(p_001_04, name="EE-001-04", color=C_DARK)

    p_001_05 = make_001_05()
    assy.add(p_001_05, name="EE-001-05", color=C_DARK)

    p_001_06 = make_001_06()
    assy.add(p_001_06, name="EE-001-06", color=C_DARK)

    p_001_07 = make_001_07()
    assy.add(p_001_07, name="EE-001-07", color=C_DARK)

    p_001_08 = make_001_08()
    assy.add(p_001_08, name="EE-001-08", color=C_DARK)

    p_001_09 = make_001_09()
    assy.add(p_001_09, name="EE-001-09", color=C_DARK)

    p_001_10 = make_001_10()
    assy.add(p_001_10, name="EE-001-10", color=C_DARK)

    p_001_11 = make_001_11()
    assy.add(p_001_11, name="EE-001-11", color=C_DARK)

    p_001_12 = make_001_12()
    assy.add(p_001_12, name="EE-001-12", color=C_DARK)

    # ═══════ 工位1涂抹模块 (0.0°) ═══════
    _a = 0.0
    _rad = math.radians(_a)
    _tx = MOUNT_CENTER_R * math.cos(_rad)
    _ty = MOUNT_CENTER_R * math.sin(_rad)
    _tz = FLANGE_AL_THICK

    p_002_01 = make_002_01()
    p_002_01 = _station_transform(p_002_01, _a, _tx, _ty, _tz)
    assy.add(p_002_01, name="EE-002-01", color=C_SILVER)

    p_002_02 = make_002_02()
    p_002_02 = _station_transform(p_002_02, _a, _tx, _ty, _tz)
    assy.add(p_002_02, name="EE-002-02", color=C_SILVER)

    p_002_03 = make_002_03()
    p_002_03 = _station_transform(p_002_03, _a, _tx, _ty, _tz)
    assy.add(p_002_03, name="EE-002-03", color=C_SILVER)

    p_002_04 = make_002_04()
    p_002_04 = _station_transform(p_002_04, _a, _tx, _ty, _tz)
    assy.add(p_002_04, name="EE-002-04", color=C_SILVER)

    p_002_05 = make_002_05()
    p_002_05 = _station_transform(p_002_05, _a, _tx, _ty, _tz)
    assy.add(p_002_05, name="EE-002-05", color=C_SILVER)

    # ═══════ 工位2 AE检测模块 (90.0°) ═══════
    _a = 90.0
    _rad = math.radians(_a)
    _tx = MOUNT_CENTER_R * math.cos(_rad)
    _ty = MOUNT_CENTER_R * math.sin(_rad)
    _tz = FLANGE_AL_THICK

    p_003_01 = make_003_01()
    p_003_01 = _station_transform(p_003_01, _a, _tx, _ty, _tz)
    assy.add(p_003_01, name="EE-003-01", color=C_AMBER)

    p_003_02 = make_003_02()
    p_003_02 = _station_transform(p_003_02, _a, _tx, _ty, _tz)
    assy.add(p_003_02, name="EE-003-02", color=C_AMBER)

    p_003_03 = make_003_03()
    p_003_03 = _station_transform(p_003_03, _a, _tx, _ty, _tz)
    assy.add(p_003_03, name="EE-003-03", color=C_AMBER)

    p_003_04 = make_003_04()
    p_003_04 = _station_transform(p_003_04, _a, _tx, _ty, _tz)
    assy.add(p_003_04, name="EE-003-04", color=C_AMBER)

    p_003_05 = make_003_05()
    p_003_05 = _station_transform(p_003_05, _a, _tx, _ty, _tz)
    assy.add(p_003_05, name="EE-003-05", color=C_AMBER)

    p_003_06 = make_003_06()
    p_003_06 = _station_transform(p_003_06, _a, _tx, _ty, _tz)
    assy.add(p_003_06, name="EE-003-06", color=C_AMBER)

    p_003_07 = make_003_07()
    p_003_07 = _station_transform(p_003_07, _a, _tx, _ty, _tz)
    assy.add(p_003_07, name="EE-003-07", color=C_AMBER)

    p_003_08 = make_003_08()
    p_003_08 = _station_transform(p_003_08, _a, _tx, _ty, _tz)
    assy.add(p_003_08, name="EE-003-08", color=C_AMBER)

    p_003_09 = make_003_09()
    p_003_09 = _station_transform(p_003_09, _a, _tx, _ty, _tz)
    assy.add(p_003_09, name="EE-003-09", color=C_AMBER)

    # ═══════ 工位3卷带清洁模块 (180.0°) ═══════
    _a = 180.0
    _rad = math.radians(_a)
    _tx = MOUNT_CENTER_R * math.cos(_rad)
    _ty = MOUNT_CENTER_R * math.sin(_rad)
    _tz = FLANGE_AL_THICK

    p_004_01 = make_004_01()
    p_004_01 = _station_transform(p_004_01, _a, _tx, _ty, _tz)
    assy.add(p_004_01, name="EE-004-01", color=C_BLUE)

    p_004_02 = make_004_02()
    p_004_02 = _station_transform(p_004_02, _a, _tx, _ty, _tz)
    assy.add(p_004_02, name="EE-004-02", color=C_BLUE)

    p_004_03 = make_004_03()
    p_004_03 = _station_transform(p_004_03, _a, _tx, _ty, _tz)
    assy.add(p_004_03, name="EE-004-03", color=C_BLUE)

    p_004_04 = make_004_04()
    p_004_04 = _station_transform(p_004_04, _a, _tx, _ty, _tz)
    assy.add(p_004_04, name="EE-004-04", color=C_BLUE)

    p_004_05 = make_004_05()
    p_004_05 = _station_transform(p_004_05, _a, _tx, _ty, _tz)
    assy.add(p_004_05, name="EE-004-05", color=C_BLUE)

    p_004_06 = make_004_06()
    p_004_06 = _station_transform(p_004_06, _a, _tx, _ty, _tz)
    assy.add(p_004_06, name="EE-004-06", color=C_BLUE)

    p_004_07 = make_004_07()
    p_004_07 = _station_transform(p_004_07, _a, _tx, _ty, _tz)
    assy.add(p_004_07, name="EE-004-07", color=C_BLUE)

    p_004_08 = make_004_08()
    p_004_08 = _station_transform(p_004_08, _a, _tx, _ty, _tz)
    assy.add(p_004_08, name="EE-004-08", color=C_BLUE)

    p_004_09 = make_004_09()
    p_004_09 = _station_transform(p_004_09, _a, _tx, _ty, _tz)
    assy.add(p_004_09, name="EE-004-09", color=C_BLUE)

    p_004_10 = make_004_10()
    p_004_10 = _station_transform(p_004_10, _a, _tx, _ty, _tz)
    assy.add(p_004_10, name="EE-004-10", color=C_BLUE)

    p_004_11 = make_004_11()
    p_004_11 = _station_transform(p_004_11, _a, _tx, _ty, _tz)
    assy.add(p_004_11, name="EE-004-11", color=C_BLUE)

    p_004_12 = make_004_12()
    p_004_12 = _station_transform(p_004_12, _a, _tx, _ty, _tz)
    assy.add(p_004_12, name="EE-004-12", color=C_BLUE)

    p_004_13 = make_004_13()
    p_004_13 = _station_transform(p_004_13, _a, _tx, _ty, _tz)
    assy.add(p_004_13, name="EE-004-13", color=C_BLUE)

    # ═══════ 工位4 UHF模块（方案A） (270.0°) ═══════
    _a = 270.0
    _rad = math.radians(_a)
    _tx = MOUNT_CENTER_R * math.cos(_rad)
    _ty = MOUNT_CENTER_R * math.sin(_rad)
    _tz = FLANGE_AL_THICK

    p_005_01 = make_005_01()
    p_005_01 = _station_transform(p_005_01, _a, _tx, _ty, _tz)
    assy.add(p_005_01, name="EE-005-01", color=C_GREEN)

    p_005_02 = make_005_02()
    p_005_02 = _station_transform(p_005_02, _a, _tx, _ty, _tz)
    assy.add(p_005_02, name="EE-005-02", color=C_GREEN)

    p_005_03 = make_005_03()
    p_005_03 = _station_transform(p_005_03, _a, _tx, _ty, _tz)
    assy.add(p_005_03, name="EE-005-03", color=C_GREEN)

    # ═══════ 信号调理模块 (0°) ═══════

    p_006_01 = make_006_01()
    assy.add(p_006_01, name="EE-006-01", color=C_BRONZE)

    p_006_02 = make_006_02()
    assy.add(p_006_02, name="EE-006-02", color=C_BRONZE)

    p_006_03 = make_006_03()
    assy.add(p_006_03, name="EE-006-03", color=C_BRONZE)

    p_006_04 = make_006_04()
    assy.add(p_006_04, name="EE-006-04", color=C_BRONZE)

    p_006_05 = make_006_05()
    assy.add(p_006_05, name="EE-006-05", color=C_BRONZE)

    p_006_06 = make_006_06()
    assy.add(p_006_06, name="EE-006-06", color=C_BRONZE)

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
