"""
Top-Level Assembly — 丝杠式升降平台 (SLP-000)

Auto-generated scaffold by codegen/gen_assembly.py
Source: D:\Work\cad-spec-gen\cad\lifting_platform\CAD_SPEC.md
Generated: 2026-05-06 12:21

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
import os
import params  # noqa: F401

ASSEMBLY_PART_NO = "SLP-000"


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
    from p02 import make_p02
    from std_p01 import make_std_p01
    from std_c01 import make_std_c01
    from std_c02 import make_std_c02
    from std_c03 import make_std_c03
    from std_c04 import make_std_c04
    from std_c05 import make_std_c05
    from std_c06 import make_std_c06
    from std_c07 import make_std_c07
    from std_c08 import make_std_c08
    from std_f11 import make_std_f11
    from std_f12 import make_std_f12
    from std_f13 import make_std_f13

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
    C_STD_TRANS = cq.Color(0.7, 0.42, 0.2)
    C_STD_BEARING = cq.Color(0.6, 0.6, 0.65)
    C_STD_MOTOR = cq.Color(0.75, 0.75, 0.78)
    C_STD_OTHER = cq.Color(0.45, 0.45, 0.5)
    C_STD_SEAL = cq.Color(0.08, 0.08, 0.08)
    C_STD_SENSOR = cq.Color(0.2, 0.2, 0.2)

    # ═══════ 未分组 (0.0°) ═══════

    p_p100_slp_100_01 = make_p100()
    assy.add(p_p100_slp_100_01, name="SLP-100#01", color=C_DARK)

    p_p200_slp_200_01 = make_p200()
    assy.add(p_p200_slp_200_01, name="SLP-200#01", color=C_DARK)

    p_p201_slp_201_01 = make_p201()
    assy.add(p_p201_slp_201_01, name="SLP-201#01", color=C_DARK)

    p_p300_slp_300_01 = make_p300()
    assy.add(p_p300_slp_300_01, name="SLP-300#01", color=C_DARK)

    p_p400_slp_400_01 = make_p400()
    assy.add(p_p400_slp_400_01, name="SLP-400#01", color=C_DARK)

    p_p403_slp_403_01 = make_p403()
    assy.add(p_p403_slp_403_01, name="SLP-403#01", color=C_DARK)

    p_p404_slp_404_01 = make_p404()
    assy.add(p_p404_slp_404_01, name="SLP-404#01", color=C_DARK)

    p_p500_slp_500_01 = make_p500()
    assy.add(p_p500_slp_500_01, name="SLP-500#01", color=C_DARK)

    p_std_p01_slp_p01_01 = make_std_p01()
    assy.add(p_std_p01_slp_p01_01, name="SLP-P01#01", color=C_STD_TRANS)

    p_std_p01_slp_p01_02 = make_std_p01()
    assy.add(p_std_p01_slp_p01_02, name="SLP-P01#02", color=C_STD_TRANS)

    p_p02_slp_p02_01 = make_p02()
    assy.add(p_p02_slp_p02_01, name="SLP-P02#01", color=C_DARK)

    p_p02_slp_p02_02 = make_p02()
    assy.add(p_p02_slp_p02_02, name="SLP-P02#02", color=C_DARK)

    p_std_c01_slp_c01_01 = make_std_c01()
    assy.add(p_std_c01_slp_c01_01, name="SLP-C01#01", color=C_STD_TRANS)

    p_std_c01_slp_c01_02 = make_std_c01()
    assy.add(p_std_c01_slp_c01_02, name="SLP-C01#02", color=C_STD_TRANS)

    p_std_c02_slp_c02_01 = make_std_c02()
    assy.add(p_std_c02_slp_c02_01, name="SLP-C02#01", color=C_STD_BEARING)

    p_std_c02_slp_c02_02 = make_std_c02()
    assy.add(p_std_c02_slp_c02_02, name="SLP-C02#02", color=C_STD_BEARING)

    p_std_c03_slp_c03_01 = make_std_c03()
    assy.add(p_std_c03_slp_c03_01, name="SLP-C03#01", color=C_STD_BEARING)

    p_std_c03_slp_c03_02 = make_std_c03()
    assy.add(p_std_c03_slp_c03_02, name="SLP-C03#02", color=C_STD_BEARING)

    p_std_c03_slp_c03_03 = make_std_c03()
    assy.add(p_std_c03_slp_c03_03, name="SLP-C03#03", color=C_STD_BEARING)

    p_std_c03_slp_c03_04 = make_std_c03()
    assy.add(p_std_c03_slp_c03_04, name="SLP-C03#04", color=C_STD_BEARING)

    p_std_c04_slp_c04_01 = make_std_c04()
    assy.add(p_std_c04_slp_c04_01, name="SLP-C04#01", color=C_STD_TRANS)

    p_std_c04_slp_c04_02 = make_std_c04()
    assy.add(p_std_c04_slp_c04_02, name="SLP-C04#02", color=C_STD_TRANS)

    p_std_c05_slp_c05_01 = make_std_c05()
    assy.add(p_std_c05_slp_c05_01, name="SLP-C05#01", color=C_STD_TRANS)

    p_std_c06_slp_c06_01 = make_std_c06()
    assy.add(p_std_c06_slp_c06_01, name="SLP-C06#01", color=C_STD_TRANS)

    p_std_c07_slp_c07_01 = make_std_c07()
    assy.add(p_std_c07_slp_c07_01, name="SLP-C07#01", color=C_STD_MOTOR)

    p_std_c08_slp_c08_01 = make_std_c08()
    assy.add(p_std_c08_slp_c08_01, name="SLP-C08#01", color=C_STD_OTHER)

    p_std_f11_slp_f11_01 = make_std_f11()
    assy.add(p_std_f11_slp_f11_01, name="SLP-F11#01", color=C_STD_SEAL)

    p_std_f11_slp_f11_02 = make_std_f11()
    assy.add(p_std_f11_slp_f11_02, name="SLP-F11#02", color=C_STD_SEAL)

    p_std_f11_slp_f11_03 = make_std_f11()
    assy.add(p_std_f11_slp_f11_03, name="SLP-F11#03", color=C_STD_SEAL)

    p_std_f11_slp_f11_04 = make_std_f11()
    assy.add(p_std_f11_slp_f11_04, name="SLP-F11#04", color=C_STD_SEAL)

    p_std_f12_slp_f12_01 = make_std_f12()
    assy.add(p_std_f12_slp_f12_01, name="SLP-F12#01", color=C_STD_SENSOR)

    p_std_f12_slp_f12_02 = make_std_f12()
    assy.add(p_std_f12_slp_f12_02, name="SLP-F12#02", color=C_STD_SENSOR)

    p_std_f13_slp_f13_01 = make_std_f13()
    assy.add(p_std_f13_slp_f13_01, name="SLP-F13#01", color=C_STD_OTHER)

    p_std_f13_slp_f13_02 = make_std_f13()
    assy.add(p_std_f13_slp_f13_02, name="SLP-F13#02", color=C_STD_OTHER)

    p_std_f13_slp_f13_03 = make_std_f13()
    assy.add(p_std_f13_slp_f13_03, name="SLP-F13#03", color=C_STD_OTHER)

    p_std_f13_slp_f13_04 = make_std_f13()
    assy.add(p_std_f13_slp_f13_04, name="SLP-F13#04", color=C_STD_OTHER)

    return assy


def export_assembly(output_dir: str, glb: bool = True) -> str:
    """Build and export the full assembly STEP (and optionally GLB).

    The GLB is post-processed by `cad_pipeline.py build` to collapse
    CadQuery's per-face mesh split into per-part meshes — see
    `codegen/consolidate_glb.py`.
    """
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
