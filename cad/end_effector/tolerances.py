"""
Tolerance & GD&T Data — §4.4.1 (lines 349–405)

Paired with params.py (nominal geometry). This file holds dimensional
tolerances, geometric tolerances, and surface finish specs extracted from
docs/design/04-末端执行机构设计.md.

Used by draw_flange.py / draw_station2_ae.py to annotate 2D DXF drawings.
"""

from dataclasses import dataclass, field


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class DimTol:
    """Dimensional tolerance for a single feature."""
    nominal: float
    upper: float
    lower: float
    fit_code: str = ""
    label: str = ""

    @property
    def text(self) -> str:
        """Format for DXF dimension override, e.g. 'Φ90±0.1' or 'Φ22H7'."""
        if self.fit_code:
            return f"Φ{self.nominal:.0f}{self.fit_code}"
        if self.upper == -self.lower:
            return f"{self.nominal:.6g}±{self.upper:.6g}"
        return f"{self.nominal:.6g} {self.upper:+.6g}/{self.lower:+.6g}"

    @property
    def dia_text(self) -> str:
        """Same as text but with Φ prefix for diameters."""
        if self.fit_code:
            return f"Φ{self.nominal:.0f}{self.fit_code}"
        if self.upper == -self.lower:
            return f"Φ{self.nominal:.6g}±{self.upper:.6g}"
        return f"Φ{self.nominal:.6g} {self.upper:+.6g}/{self.lower:+.6g}"


@dataclass
class GDT:
    """Geometric tolerance (form/position)."""
    symbol: str      # ⌭ coaxiality, ∥ parallelism, etc. (ASCII fallback used in DXF)
    value: float     # mm or degrees
    datum: str       # datum reference letter/description
    label: str = ""

    @property
    def text(self) -> str:
        if "°" in str(self.value) or self.label.endswith("°"):
            return f"{self.symbol} {self.value}°  [{self.datum}]"
        return f"{self.symbol} Φ{self.value}  [{self.datum}]" if "同轴" in self.label \
            else f"{self.symbol} {self.value}  [{self.datum}]"


@dataclass
class SurfaceFinish:
    """Surface roughness and treatment."""
    ra: float        # Ra in µm
    treatment: str   # e.g. "硬质阳极氧化 HV>400"
    label: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# §4.4.1 法兰本体尺寸公差 (lines 353–367)
# ═══════════════════════════════════════════════════════════════════════════════

FLANGE_OD_TOL = DimTol(90.0, 0.1, -0.1, label="法兰外径")
CENTER_HOLE_TOL = DimTol(22.0, 0.021, 0.0, fit_code="H7", label="中心孔")
AL_THICK_TOL = DimTol(25.0, 0.5, -0.5, label="铝合金段厚度")
TOTAL_THICK_TOL = DimTol(30.0, 0.5, -0.5, label="总厚度")
ARM_WIDTH_TOL = DimTol(12.0, 0.2, -0.2, label="悬臂截面宽")
ARM_THICK_TOL = DimTol(8.0, 0.2, -0.2, label="悬臂截面厚")
ARM_LENGTH_TOL = DimTol(40.0, 0.3, -0.3, label="悬臂长度")
MOUNT_R_TOL = DimTol(65.0, 0.3, -0.3, label="安装面中心距")
MOUNT_FACE_TOL = DimTol(40.0, 0.2, -0.2, label="安装面尺寸")
ISO9409_PCD_TOL = DimTol(50.0, 0.0, 0.0, label="ISO 9409 PCD")  # standard
SPRING_PIN_HOLE_TOL = DimTol(4.0, 0.012, 0.0, fit_code="H7", label="弹簧销孔")
PEEK_BOLT_PCD_TOL = DimTol(70.0, 0.2, -0.2, label="PEEK固定PCD")
PEEK_OD_TOL = DimTol(86.0, 0.05, -0.05, label="PEEK外径")
PEEK_ID_TOL = DimTol(40.0, 0.1, -0.1, label="PEEK内径")
PEEK_THICK_TOL = DimTol(5.0, 0.2, -0.2, label="PEEK厚度")

# O-ring groove (line 390)
ORING_GROOVE_W_TOL = DimTol(3.2, 0.05, -0.05, label="O-ring槽宽")
ORING_GROOVE_D_TOL = DimTol(1.8, 0.05, -0.05, label="O-ring槽深")
ORING_CENTER_TOL = DimTol(80.0, 0.1, -0.1, label="O-ring中心径")

# Collect all dimensional tolerances
ALL_DIM_TOLS = [
    FLANGE_OD_TOL, CENTER_HOLE_TOL, AL_THICK_TOL, TOTAL_THICK_TOL,
    ARM_WIDTH_TOL, ARM_THICK_TOL, ARM_LENGTH_TOL, MOUNT_R_TOL,
    MOUNT_FACE_TOL, ISO9409_PCD_TOL, SPRING_PIN_HOLE_TOL,
    PEEK_BOLT_PCD_TOL, PEEK_OD_TOL, PEEK_ID_TOL, PEEK_THICK_TOL,
    ORING_GROOVE_W_TOL, ORING_GROOVE_D_TOL, ORING_CENTER_TOL,
]

# ═══════════════════════════════════════════════════════════════════════════════
# §4.4.1 形位公差 (lines 399–404)
# ═══════════════════════════════════════════════════════════════════════════════

GDT_COAXIALITY = GDT("⌭", 0.02, "旋转轴", label="中心孔同轴度")
GDT_PARALLELISM = GDT("∥", 0.02, "旋转轴垂直面", label="ISO 9409面平行度")
GDT_EQUAL_HEIGHT = GDT("=", 0.05, "法兰端面", label="悬臂等高度")
GDT_ANGULAR = GDT("∠", 0.05, "基准0°标记", label="弹簧销角度位置")  # degrees

ALL_GDTS = [GDT_COAXIALITY, GDT_PARALLELISM, GDT_EQUAL_HEIGHT, GDT_ANGULAR]

# ═══════════════════════════════════════════════════════════════════════════════
# §4.4.1 表面处理 (lines 393–396)
# ═══════════════════════════════════════════════════════════════════════════════

SURF_CRITICAL = SurfaceFinish(0.8, "硬质阳极氧化 HV>400", label="关键配合面")
SURF_ISO = SurfaceFinish(0.8, "硬质阳极氧化", label="ISO 9409安装面")
SURF_GENERAL = SurfaceFinish(3.2, "普通阳极氧化+黑色", label="一般外表面")

ALL_SURFACES = [SURF_CRITICAL, SURF_ISO, SURF_GENERAL]
