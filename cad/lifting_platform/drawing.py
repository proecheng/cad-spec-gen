"""
ezdxf 2D Engineering Drawing Engine — Common Utilities (V4)

GB/T 国标工程图引擎，经三轮对抗性审查（合规性/实现可行性/加工实用性）。

引用标准：
  GB/T 4457.4-2002  图线        GB/T 17450-1998  linetype dash/gap
  GB/T 4458.1-2002  三视图      GB/T 4458.4-2003  尺寸标注
  GB/T 4458.6-2002  剖视图      GB/T 4457.5-2013  剖面线
  GB/T 4459.1-1995  螺纹画法    GB/T 14692-2008   投影法
  GB/T 10609.1      图框/标题栏  GB/T 14691-1993   字体(仿宋)
  GB/T 1804-2000    一般公差     GB/T 131-2006     表面粗糙度
  GB/T 1182-2018    形位公差

Dependencies: ezdxf >= 1.4
"""

import math
from typing import List, Optional, Sequence, Tuple

import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from ezdxf.math import Vec2

# ─── Constants ────────────────────────────────────────────────────────────────

# A3 landscape paper (mm)
A3_W, A3_H = 420.0, 297.0

# ─── Dimension / Arrow module constants (GB/T 4458.4) ─────────────────────────
DIM_TEXT_H = 3.5                        # 尺寸文字高度 mm (GB/T 标准系列)
DIM_ARROW = 3.0                         # 箭头长度 mm
ARROW_HALF_ANGLE = math.radians(15)     # GB/T 4457.4: 30° 总角
DIM_EXT_BEYOND = 2.0                    # 界线超出尺寸线 2mm
DIM_EXT_OFFSET = 1.0                    # 界线偏移被注点 1mm
DIM_GAP = 1.0                           # 文字间距 1mm

# ─── Layer definitions (GB/T 4457.4, d=0.50mm) ───────────────────────────────
# (name, color_index, lineweight_100ths_mm, linetype)
LAYERS = [
    ("OUTLINE",       7, 50, "Continuous"),   # 粗实线 d=0.50mm 可见轮廓
    ("THIN",          7, 25, "Continuous"),    # 细实线 d/2=0.25mm
    ("DIM",           3, 25, "Continuous"),    # 尺寸标注 (绿)
    ("GDT",           1, 25, "Continuous"),    # 形位公差 (红)
    ("CENTER",        1, 25, "CENTER"),        # 细点画线 d/2 (内置被替换)
    ("HIDDEN",        8, 25, "DASHED"),        # 细虚线 d/2 (内置被替换)
    ("HATCH",         8, 18, "Continuous"),    # 剖面线
    ("TEXT",          7, 25, "Continuous"),     # 注释文字
    ("BORDER",        7, 50, "Continuous"),     # 图框
    ("SECTION_CUT",   1, 50, "CENTER"),        # 剖切线（端部叠加粗实线段）
    ("BREAK_LINE",    7, 25, "Continuous"),     # 断裂线
    ("THREAD_MINOR",  7, 25, "Continuous"),     # 螺纹小径(细实线/3/4弧)
]

# ─── Technical notes presets ──────────────────────────────────────────────────
TECH_NOTES_AL = [
    "技术要求:",
    "1. 未注公差按 GB/T 1804-m",
    "2. 未注外倒角 C0.5, 精密孔口倒角 C0.2",
    "3. 锐边去毛刺, O型圈槽口 R0.1~R0.2",
    "4. 表面处理: 硬质阳极氧化, 膜厚≥25μm",
    "5. 未注粗糙度 Ra3.2",
    "6. 零件打标: 料号+批次号, 字高2mm",
]

TECH_NOTES_PEEK = [
    "技术要求:",
    "1. 未注公差按 GB/T 1804-m",
    "2. 注塑后去飞边, 锐边去毛刺",
    "3. 未注粗糙度 Ra1.6",
    "4. 材料: PEEK (Victrex 450G 或等效)",
    "5. 零件打标: 料号+批次号, 字高1.5mm",
]

TECH_NOTES_STEEL = [
    "技术要求:",
    "1. 未注公差按 GB/T 1804-m",
    "2. 未注外倒角 C0.3",
    "3. 锐边去毛刺",
    "4. 表面处理: 镀锌钝化",
    "5. 未注粗糙度 Ra3.2",
]

TECH_NOTES_NYLON = [
    "技术要求:",
    "1. 未注公差按 GB/T 1804-m",
    "2. 注塑后去飞边, 锐边去毛刺",
    "3. 未注粗糙度 Ra1.6",
    "4. 材料: PA66 (尼龙66) 或等效",
    "5. 零件打标: 料号+批次号, 字高1.5mm",
]

TECH_NOTES_RUBBER = [
    "技术要求:",
    "1. 未注公差按 GB/T 1804-m",
    "2. 模压后修除飞边, 分型线残余≤0.3mm",
    "3. 硬度: Shore A 40±5",
    "4. 未注粗糙度 Ra3.2",
]

_TECH_NOTES = {
    "al": TECH_NOTES_AL, "peek": TECH_NOTES_PEEK, "steel": TECH_NOTES_STEEL,
    "nylon": TECH_NOTES_NYLON, "rubber": TECH_NOTES_RUBBER,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Document creation
# ═══════════════════════════════════════════════════════════════════════════════

def create_drawing(title: str = "", scale: float = 1.0) -> Tuple[Drawing, Modelspace]:
    """Create a new DXF drawing with GB/T layers, linetypes, and dimension style.

    Returns (doc, msp) tuple.
    """
    doc = ezdxf.new("R2013", setup=True)
    doc.units = units.MM

    # ── Replace built-in linetypes with GB/T 17450 patterns (d=0.5mm) ──
    # 替换而非新建名字 → 已有 linetype="CENTER"/"DASHED" 的代码自动生效
    for lt_name in ("DASHED", "DASHED2", "DASHEDX2"):
        if lt_name in doc.linetypes:
            doc.linetypes.remove(lt_name)
    doc.linetypes.add("DASHED",
                      pattern=[7.5, 6.0, -1.5],
                      description="GB/T 17450 dashed 12d/3d (d=0.5)")

    for lt_name in ("CENTER", "CENTER2", "CENTERX2"):
        if lt_name in doc.linetypes:
            doc.linetypes.remove(lt_name)
    doc.linetypes.add("CENTER",
                      pattern=[15.5, 12.0, -1.5, 0.5, -1.5],
                      description="GB/T 17450 center 24d/3d/1d/3d (d=0.5)")

    # ── Chinese font: 仿宋体 (GB/T 14691-1993) ──
    std = doc.styles.get("Standard")
    std.dxf.font = "simfang.ttf"
    std.set_extended_font_data("FangSong")

    # ── Add layers ──
    for name, color, lw, lt in LAYERS:
        doc.layers.add(name, color=color, lineweight=lw, linetype=lt)

    # ── ISO dimension style ──
    _setup_dimstyle(doc)

    msp = doc.modelspace()
    return doc, msp


def _setup_dimstyle(doc: Drawing):
    """Configure GB/T 4458.4 compliant dimension style."""
    name = "ISO-25"
    try:
        style = doc.dimstyles.new(name)
    except Exception:
        style = doc.dimstyles.get(name)

    style.dxf.dimtxt = DIM_TEXT_H           # 文字高度 (纸面mm)
    style.dxf.dimasz = DIM_ARROW            # 箭头大小
    style.dxf.dimexe = DIM_EXT_BEYOND       # 界线超出
    style.dxf.dimexo = DIM_EXT_OFFSET       # 界线偏移
    style.dxf.dimgap = DIM_GAP              # 文字间距
    style.dxf.dimdec = 1                    # 小数位
    style.dxf.dimclrd = 3                   # 尺寸线颜色 = 绿
    style.dxf.dimclre = 3                   # 界线颜色 = 绿
    style.dxf.dimtad = 1                    # 文字在尺寸线上方
    style.dxf.dimtxsty = "Standard"


# ═══════════════════════════════════════════════════════════════════════════════
# Dimension helpers
# ═══════════════════════════════════════════════════════════════════════════════

def add_linear_dim(msp: Modelspace, p1: Tuple[float, float],
                   p2: Tuple[float, float], offset: float,
                   text: str = "", angle: float = None,
                   layer: str = "DIM"):
    """Add a linear dimension between two points.

    Args:
        p1, p2: endpoint coordinates
        offset: perpendicular distance from the line to place dim
        text: override text (e.g. "25±0.5"); empty = auto
        angle: explicit angle in degrees; None = auto-detect
    """
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    if angle is None:
        angle = math.degrees(math.atan2(dy, dx))

    # Midpoint offset perpendicular to the dim line
    perp = math.radians(angle + 90)
    mx = (p1[0] + p2[0]) / 2 + offset * math.cos(perp)
    my = (p1[1] + p2[1]) / 2 + offset * math.sin(perp)

    dim = msp.add_linear_dim(
        base=(mx, my),
        p1=p1,
        p2=p2,
        angle=angle,
        dimstyle="ISO-25",
        # 不带 override — 由 dimstyle 统一控制
    )
    if text:
        dim.set_text(text)
    dim.render()
    return dim


def add_diameter_dim(msp: Modelspace, center: Tuple[float, float],
                     radius: float, angle_deg: float = 45.0,
                     text: str = "", layer: str = "DIM"):
    """Add a diameter dimension using a leader + text annotation.

    手工绘制（非ezdxf dim entity），跨DXF viewer兼容性更好。
    """
    rad = math.radians(angle_deg)
    p_inner = (center[0] - radius * math.cos(rad),
               center[1] - radius * math.sin(rad))
    p_outer = (center[0] + radius * math.cos(rad),
               center[1] + radius * math.sin(rad))

    # Draw the dim line through center
    msp.add_line(p_inner, p_outer, dxfattribs={"layer": layer, "color": 3})

    # Arrowheads
    _add_arrow(msp, p_outer, angle_deg + 180, layer=layer)
    _add_arrow(msp, p_inner, angle_deg, layer=layer)

    # Text at leader end
    text_pos = (p_outer[0] + 5 * math.cos(rad),
                p_outer[1] + 5 * math.sin(rad))
    if not text:
        text = f"\u03a6{radius * 2:.1f}"
    msp.add_text(text, height=DIM_TEXT_H,
                 dxfattribs={"layer": layer, "color": 3}).set_placement(text_pos)


def add_radius_dim(msp: Modelspace, center: Tuple[float, float],
                   radius: float, angle_deg: float = 45.0,
                   text: str = "", layer: str = "DIM"):
    """Add a radius dimension (leader from center to arc)."""
    rad = math.radians(angle_deg)
    p_arc = (center[0] + radius * math.cos(rad),
             center[1] + radius * math.sin(rad))

    msp.add_line(center, p_arc, dxfattribs={"layer": layer, "color": 3})
    _add_arrow(msp, p_arc, angle_deg + 180, layer=layer)

    text_pos = (p_arc[0] + 4 * math.cos(rad),
                p_arc[1] + 4 * math.sin(rad))
    if not text:
        text = f"R{radius:.1f}"
    msp.add_text(text, height=DIM_TEXT_H,
                 dxfattribs={"layer": layer, "color": 3}).set_placement(text_pos)


def _add_arrow(msp: Modelspace, tip: Tuple[float, float],
               angle_deg: float, size: float = DIM_ARROW,
               layer: str = "DIM"):
    """Draw a filled arrowhead at *tip* pointing in *angle_deg*.

    GB/T 4457.4: 30 degree total angle (15 degree half-angle).
    """
    rad = math.radians(angle_deg)
    base_l = (tip[0] + size * math.cos(rad + ARROW_HALF_ANGLE),
              tip[1] + size * math.sin(rad + ARROW_HALF_ANGLE))
    base_r = (tip[0] + size * math.cos(rad - ARROW_HALF_ANGLE),
              tip[1] + size * math.sin(rad - ARROW_HALF_ANGLE))
    msp.add_lwpolyline([tip, base_l, base_r, tip], close=True,
                       dxfattribs={"layer": layer, "color": 3})


# ═══════════════════════════════════════════════════════════════════════════════
# GD&T feature control frame (GB/T 1182-2018)
# ═══════════════════════════════════════════════════════════════════════════════

def add_gdt_frame(msp: Modelspace, pos: Tuple[float, float],
                  entries: Sequence[Tuple[str, str, str]],
                  layer: str = "GDT"):
    """Draw a GD&T feature control frame.

    Args:
        pos: bottom-left corner
        entries: list of (symbol, tolerance_value, datum) tuples
            e.g. [("\u2b2d", "\u03a60.02", "A")]
    """
    cell_w = 18.0
    cell_h = 6.0
    x0, y0 = pos

    for i, (sym, val, datum) in enumerate(entries):
        y = y0 + i * cell_h

        # Three cells: symbol | value | datum
        msp.add_lwpolyline(
            [(x0, y), (x0 + cell_w * 3, y),
             (x0 + cell_w * 3, y + cell_h),
             (x0, y + cell_h), (x0, y)],
            dxfattribs={"layer": layer, "color": 1},
        )
        msp.add_line((x0 + cell_w, y), (x0 + cell_w, y + cell_h),
                     dxfattribs={"layer": layer, "color": 1})
        msp.add_line((x0 + cell_w * 2, y), (x0 + cell_w * 2, y + cell_h),
                     dxfattribs={"layer": layer, "color": 1})

        th = 2.0
        msp.add_text(sym, height=th,
                     dxfattribs={"layer": layer, "color": 1}
                     ).set_placement((x0 + cell_w * 0.5, y + 1.5))
        msp.add_text(val, height=th,
                     dxfattribs={"layer": layer, "color": 1}
                     ).set_placement((x0 + cell_w * 1.1, y + 1.5))
        msp.add_text(datum, height=th,
                     dxfattribs={"layer": layer, "color": 1}
                     ).set_placement((x0 + cell_w * 2.2, y + 1.5))


# ═══════════════════════════════════════════════════════════════════════════════
# Datum symbol (GB/T 1182-2018)
# ═══════════════════════════════════════════════════════════════════════════════

def add_datum_symbol(msp: Modelspace, attach_point: Tuple[float, float],
                     label: str = "A", direction: str = "up",
                     layer: str = "GDT"):
    """Draw datum triangle + letter box at attach_point.

    GB/T 1182-2018: equilateral triangle (side=5mm) with base on surface,
    connected to a square box containing the datum letter.

    Args:
        attach_point: point on the datum surface/axis
        label: datum letter (A, B, C...)
        direction: "up"|"down"|"left"|"right" — triangle points away from surface
    """
    x, y = attach_point
    tri_side = 5.0
    tri_h = tri_side * math.sqrt(3) / 2  # ~4.33mm
    box_size = 6.0

    # Direction vectors
    offsets = {
        "up":    (0, 1),
        "down":  (0, -1),
        "left":  (-1, 0),
        "right": (1, 0),
    }
    dx, dy = offsets.get(direction, (0, 1))

    # Triangle vertices: base centered at attach_point, apex pointing in direction
    if direction in ("up", "down"):
        p0 = (x - tri_side / 2, y)
        p1 = (x + tri_side / 2, y)
        p2 = (x, y + dy * tri_h)
        box_center = (x, y + dy * (tri_h + box_size / 2 + 0.5))
    else:
        p0 = (x, y - tri_side / 2)
        p1 = (x, y + tri_side / 2)
        p2 = (x + dx * tri_h, y)
        box_center = (x + dx * (tri_h + box_size / 2 + 0.5), y)

    # Filled triangle
    msp.add_lwpolyline([p0, p1, p2, p0], close=True,
                       dxfattribs={"layer": layer, "color": 1})

    # Letter box
    bx, by = box_center
    half = box_size / 2
    msp.add_lwpolyline([
        (bx - half, by - half), (bx + half, by - half),
        (bx + half, by + half), (bx - half, by + half),
        (bx - half, by - half),
    ], dxfattribs={"layer": layer, "color": 1})

    # Letter
    msp.add_text(label, height=3.5,
                 dxfattribs={"layer": layer, "color": 1}
                 ).set_placement((bx, by - 1.5))

    # Connection line from triangle apex to box
    if direction in ("up", "down"):
        line_start = p2
        line_end = (bx, by - dy * half)
    else:
        line_start = p2
        line_end = (bx - dx * half, by)
    msp.add_line(line_start, line_end,
                 dxfattribs={"layer": layer, "color": 1})


# ═══════════════════════════════════════════════════════════════════════════════
# Surface roughness symbols (GB/T 131-2006)
# ═══════════════════════════════════════════════════════════════════════════════

def add_surface_symbol(msp: Modelspace, pos: Tuple[float, float],
                       ra: float, layer: str = "GDT"):
    """Draw a surface roughness symbol (check mark + Ra value).

    Approximately 8mm wide x 6mm tall.
    """
    x, y = pos
    pts = [
        (x, y + 4),
        (x + 2, y),
        (x + 4, y + 6),
        (x + 6, y + 6),
    ]
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "color": 1})
    msp.add_line((x + 4, y + 6), (x + 10, y + 6),
                 dxfattribs={"layer": layer, "color": 1})
    msp.add_text(f"Ra{ra}", height=2.5,
                 dxfattribs={"layer": layer, "color": 1}
                 ).set_placement((x + 4.5, y + 7))


def add_default_roughness(msp: Modelspace, ra: float = 3.2,
                          pos: Tuple[float, float] = (390.0, 278.0),
                          layer: str = "GDT"):
    """Draw default surface roughness symbol at upper-right corner.

    GB/T 131-2006: parenthesized Ra symbol means "all surfaces not
    individually marked".
    """
    x, y = pos
    # Parentheses
    msp.add_text("(", height=4.0,
                 dxfattribs={"layer": layer, "color": 1}
                 ).set_placement((x - 2, y - 1))
    # Roughness symbol
    pts = [
        (x, y + 3),
        (x + 1.5, y),
        (x + 3, y + 5),
        (x + 5, y + 5),
    ]
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "color": 1})
    msp.add_line((x + 3, y + 5), (x + 8, y + 5),
                 dxfattribs={"layer": layer, "color": 1})
    msp.add_text(f"Ra{ra}", height=2.5,
                 dxfattribs={"layer": layer, "color": 1}
                 ).set_placement((x + 3.5, y + 6))
    msp.add_text(")", height=4.0,
                 dxfattribs={"layer": layer, "color": 1}
                 ).set_placement((x + 12, y - 1))


# ═══════════════════════════════════════════════════════════════════════════════
# Section hatch (GB/T 4457.5)
# ═══════════════════════════════════════════════════════════════════════════════

def add_section_hatch(msp: Modelspace, boundary_points: Sequence[Tuple[float, float]],
                      pattern: str = "ANSI31", scale: float = 1.0,
                      layer: str = "HATCH"):
    """Add cross-hatch fill to a closed boundary.

    Args:
        boundary_points: list of (x, y) vertices forming a closed polygon
        pattern: ANSI31=45 degree (general metal), ANSI32=crosshatch, ANSI37=rubber
        scale: pattern scale factor (independent of $LTSCALE)
    """
    hatch = msp.add_hatch(color=8, dxfattribs={"layer": layer})
    hatch.set_pattern_fill(pattern, scale=scale)
    hatch.paths.add_polyline_path(
        [Vec2(p) for p in boundary_points],
        is_closed=True,
    )
    return hatch


# ═══════════════════════════════════════════════════════════════════════════════
# Section symbol (GB/T 4458.6)
# ═══════════════════════════════════════════════════════════════════════════════

def add_section_symbol(msp: Modelspace,
                       start: Tuple[float, float],
                       end: Tuple[float, float],
                       label: str = "A",
                       arrow_dir: str = "left",
                       stroke_len: float = 8.0,
                       layer_cut: str = "SECTION_CUT",
                       layer_outline: str = "OUTLINE"):
    """Draw GB/T 4458.6 section cutting symbol.

    - Middle: chain line (CENTER linetype via SECTION_CUT layer)
    - Both ends: thick solid strokes + arrows pointing toward projection
    - Letters at arrow tips

    Args:
        start, end: endpoints of the cutting line
        label: section letter (A, B, etc.) — produces "A-A" label
        arrow_dir: "left"|"right"|"up"|"down" — arrows point toward section view
        stroke_len: length of thick end strokes (mm)
    """
    sx, sy = start
    ex, ey = end

    # Main cutting line (chain line pattern via layer)
    msp.add_line(start, end, dxfattribs={"layer": layer_cut, "linetype": "CENTER"})

    # Direction of cutting line
    line_angle = math.atan2(ey - sy, ex - sx)
    line_len = math.hypot(ex - sx, ey - sy)

    # Thick end strokes (粗实线)
    cos_a, sin_a = math.cos(line_angle), math.sin(line_angle)
    # Start end
    s_end = (sx + stroke_len * cos_a, sy + stroke_len * sin_a)
    msp.add_line(start, s_end,
                 dxfattribs={"layer": layer_outline, "lineweight": 50})
    # End end
    e_start = (ex - stroke_len * cos_a, ey - stroke_len * sin_a)
    msp.add_line(e_start, end,
                 dxfattribs={"layer": layer_outline, "lineweight": 50})

    # Arrow direction
    arrow_dirs = {
        "left": math.pi,
        "right": 0,
        "up": math.pi / 2,
        "down": -math.pi / 2,
    }
    arr_angle = math.degrees(arrow_dirs.get(arrow_dir, math.pi))

    # Arrows at start and end, perpendicular to cutting line
    arrow_offset = 3.0
    for px, py in [start, end]:
        arr_rad = arrow_dirs.get(arrow_dir, math.pi)
        arr_tip = (px + arrow_offset * math.cos(arr_rad),
                   py + arrow_offset * math.sin(arr_rad))
        _add_arrow(msp, arr_tip, arr_angle + 180, size=DIM_ARROW, layer="GDT")

        # Label letter outside the arrow
        label_offset = arrow_offset + DIM_ARROW + 2
        lx = px + label_offset * math.cos(arr_rad)
        ly = py + label_offset * math.sin(arr_rad)
        msp.add_text(label, height=DIM_TEXT_H,
                     dxfattribs={"layer": "TEXT", "color": 1}
                     ).set_placement((lx, ly - 1.5))


# ═══════════════════════════════════════════════════════════════════════════════
# View labels (GB/T 4458.1 / 4458.6)
# ═══════════════════════════════════════════════════════════════════════════════

def add_section_view_label(msp: Modelspace, pos: Tuple[float, float],
                           label: str = "A", layer: str = "TEXT"):
    """Draw section view title, e.g. 'A-A', centered above the view.

    GB/T 4458.6: section view title uses the same letter pair as the cut line.
    """
    text = f"{label}-{label}"
    msp.add_text(text, height=5.0,
                 dxfattribs={"layer": layer, "color": 7}
                 ).set_placement(pos)


def add_detail_label(msp: Modelspace, pos: Tuple[float, float],
                     label: str = "I", scale_factor: float = 2.0,
                     layer: str = "TEXT"):
    """Draw detail view title, e.g. 'I (2:1)', centered above the view."""
    text = f"{label} ({scale_factor:.0f}:1)"
    msp.add_text(text, height=5.0,
                 dxfattribs={"layer": layer, "color": 7}
                 ).set_placement(pos)


def add_detail_circle(msp: Modelspace, center: Tuple[float, float],
                      radius: float, label: str = "I",
                      layer: str = "THIN"):
    """Draw detail enlargement circle + label on source view.

    GB/T 4458.1: thin solid circle with label letter nearby.
    """
    msp.add_circle(center, radius,
                   dxfattribs={"layer": layer})
    msp.add_text(label, height=DIM_TEXT_H,
                 dxfattribs={"layer": "TEXT", "color": 7}
                 ).set_placement((center[0] + radius + 2, center[1] + radius + 1))


def add_auxiliary_label(msp: Modelspace, pos: Tuple[float, float],
                        label: str = "C", layer: str = "TEXT"):
    """Draw auxiliary (向视图) view title, e.g. 'C向'."""
    msp.add_text(f"{label}向", height=5.0,
                 dxfattribs={"layer": layer, "color": 7}
                 ).set_placement(pos)


# ═══════════════════════════════════════════════════════════════════════════════
# Section hatch with cavities (GB/T 4457.5)
# ═══════════════════════════════════════════════════════════════════════════════

def add_section_hatch_with_holes(
    msp: Modelspace,
    outer_boundary: Sequence[Tuple[float, float]],
    inner_boundaries: Sequence[Sequence[Tuple[float, float]]] = (),
    pattern: str = "ANSI31",
    scale: float = 1.0,
    layer: str = "HATCH",
):
    """Add hatch to a solid region with inner cavities subtracted.

    Use this for section views: outer_boundary is the cut profile of the
    solid material, inner_boundaries are cavities/holes to exclude from
    hatching.

    Args:
        outer_boundary: vertices of the outer cut profile (closed polygon)
        inner_boundaries: list of cavity vertex lists to subtract
        pattern: ANSI31=metal 45°, ANSI37=rubber, ANSI32=crosshatch
        scale: hatch pattern scale
    """
    hatch = msp.add_hatch(color=8, dxfattribs={"layer": layer})
    hatch.set_pattern_fill(pattern, scale=scale)
    # Outer boundary (CCW = solid)
    hatch.paths.add_polyline_path(
        [Vec2(p) for p in outer_boundary], is_closed=True)
    # Inner boundaries (CW = holes)
    for cavity in inner_boundaries:
        hatch.paths.add_polyline_path(
            [Vec2(p) for p in cavity], is_closed=True)
    return hatch


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-view layout calculator
# ═══════════════════════════════════════════════════════════════════════════════

def calc_multi_view_layout(
    views: dict,
    paper: Tuple[float, float] = (420.0, 297.0),
    title_h: float = 56.0,
    gap: float = 25.0,
) -> dict:
    """Calculate layout for flexible view configurations.

    Supports standard 3-view + additional section/detail/auxiliary views.

    Args:
        views: dict mapping position keys to (width, height) tuples.
            Standard keys: "front", "top", "left"
            Additional keys: "section_right", "section_below",
                             "detail_br", "auxiliary_br"
            Each value is (width_mm, height_mm) at 1:1 scale.
        paper: paper size
        title_h: title block height
        gap: inter-view gap

    Returns:
        dict with "{key}_origin": (x, y) and "scale": float
    """
    draw_left = 25.0
    draw_right = paper[0] - 10.0
    draw_bottom = 10.0 + title_h
    draw_top = paper[1] - 10.0
    avail_w = draw_right - draw_left
    avail_h = draw_top - draw_bottom

    fw, fh = views.get("front", (1, 1))
    tw, th = views.get("top", (fw, 1))
    lw, lh = views.get("left", (1, fh))

    # Compute total needed width/height
    total_w = fw + gap + lw
    total_h = fh + gap + th

    # If there's a section view to the right of left view
    sr = views.get("section_right", None)
    if sr:
        total_w += gap + sr[0]

    # If there's a detail view below-right
    dbr = views.get("detail_br", None)

    # Scale to fit
    scale_w = (avail_w - 40) / total_w if total_w > 0 else 1.0
    scale_h = (avail_h - 30) / total_h if total_h > 0 else 1.0
    scale = min(scale_w, scale_h, 1.0)

    sgap = gap * scale
    result = {"scale": scale}

    # Front view origin
    # Center the group horizontally and vertically
    total_sw = total_w * scale
    total_sh = total_h * scale
    cx = draw_left + (avail_w - total_sw) / 2
    cy = draw_bottom + (avail_h - total_sh) / 2

    if "top" in views:
        front_y = cy + th * scale + sgap
    else:
        front_y = cy + (avail_h - fh * scale) / 2
    front_x = cx

    result["front_origin"] = (front_x, front_y)

    if "top" in views:
        result["top_origin"] = (front_x, cy)

    if "left" in views:
        result["left_origin"] = (front_x + fw * scale + sgap, front_y)

    if sr:
        lx = front_x + fw * scale + sgap
        if "left" in views:
            lx += lw * scale + sgap
        result["section_right_origin"] = (lx, front_y)

    if dbr:
        # Place detail view below the left/section area
        dx = front_x + fw * scale + sgap
        dy = cy
        result["detail_br_origin"] = (dx, dy)

    # Section below front (replaces or supplements top)
    sb = views.get("section_below", None)
    if sb:
        result["section_below_origin"] = (front_x, cy)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Thread representation (GB/T 4459.1)
# ═══════════════════════════════════════════════════════════════════════════════

def add_thread_hole(msp: Modelspace, center: Tuple[float, float],
                    major_d: float, minor_d: float,
                    thread_spec: str = "M3\u00d70.5",
                    depth: Optional[float] = None,
                    is_end_view: bool = True,
                    scale: float = 1.0,
                    layer: str = "OUTLINE"):
    """Draw GB/T 4459.1 internal thread representation + callout.

    End view: minor dia = full circle (thick), major dia = 3/4 arc (thin)
    Side view: minor = thick parallel lines, major = thin parallel lines + termination

    Args:
        center: center point
        major_d: major (nominal) diameter
        minor_d: minor (root) diameter
        thread_spec: e.g. "M3x0.5"
        depth: None = through hole, number = blind hole depth
        is_end_view: True for end view, False for side view
        scale: view scale factor
    """
    cx, cy = center
    s = scale
    r_major = (major_d / 2) * s
    r_minor = (minor_d / 2) * s

    if is_end_view:
        # Minor diameter: full circle, thick (OUTLINE)
        msp.add_circle((cx, cy), r_minor,
                       dxfattribs={"layer": layer})
        # Major diameter: 3/4 arc, thin (THREAD_MINOR)
        # Gap at upper-right quadrant (0-90 degrees missing)
        msp.add_arc((cx, cy), r_major, start_angle=90, end_angle=0,
                    dxfattribs={"layer": "THREAD_MINOR"})
    else:
        # Side view: parallel lines
        # Minor diameter (thick, visible)
        msp.add_line((cx - r_minor, cy), (cx + r_minor, cy),
                     dxfattribs={"layer": layer})
        msp.add_line((cx - r_minor, cy), (cx + r_minor, cy),
                     dxfattribs={"layer": layer})
        # Major diameter (thin)
        msp.add_line((cx - r_major, cy), (cx + r_major, cy),
                     dxfattribs={"layer": "THREAD_MINOR"})

    # Callout text
    callout = f"{thread_spec} \u901a" if depth is None else f"{thread_spec}-{depth}\u6df1"
    text_offset = r_major + 3 * s
    msp.add_text(callout, height=DIM_TEXT_H,
                 dxfattribs={"layer": "DIM", "color": 3}
                 ).set_placement((cx + text_offset, cy - 1.5))


# ═══════════════════════════════════════════════════════════════════════════════
# Center lines
# ═══════════════════════════════════════════════════════════════════════════════

def add_centerline_cross(msp: Modelspace, center: Tuple[float, float],
                         size: float = 8.0, layer: str = "CENTER"):
    """Draw center-mark cross at given point."""
    cx, cy = center
    msp.add_line((cx - size, cy), (cx + size, cy),
                 dxfattribs={"layer": layer, "linetype": "CENTER"})
    msp.add_line((cx, cy - size), (cx, cy + size),
                 dxfattribs={"layer": layer, "linetype": "CENTER"})


def add_centerline_h(msp: Modelspace, y: float, x1: float, x2: float,
                     layer: str = "CENTER"):
    """Horizontal centerline."""
    msp.add_line((x1, y), (x2, y),
                 dxfattribs={"layer": layer, "linetype": "CENTER"})


def add_centerline_v(msp: Modelspace, x: float, y1: float, y2: float,
                     layer: str = "CENTER"):
    """Vertical centerline."""
    msp.add_line((x, y1), (x, y2),
                 dxfattribs={"layer": layer, "linetype": "CENTER"})


# ═══════════════════════════════════════════════════════════════════════════════
# Technical notes (技术要求)
# ═══════════════════════════════════════════════════════════════════════════════

def add_technical_notes(msp: Modelspace,
                        notes: Optional[List[str]] = None,
                        material_type: str = "al",
                        pos: Tuple[float, float] = (27.0, 275.0),
                        layer: str = "TEXT"):
    """Draw technical notes block in upper-left area of drawing frame.

    Args:
        notes: custom notes list; None = use preset for material_type
        material_type: "al" | "peek" | "steel"
        pos: top-left position of the notes block
    """
    if notes is None:
        notes = _TECH_NOTES.get(material_type, TECH_NOTES_AL)

    x, y = pos
    line_spacing = 5.0
    for i, line in enumerate(notes):
        h = 3.0 if i == 0 else 2.5
        msp.add_text(line, height=h,
                     dxfattribs={"layer": layer}
                     ).set_placement((x, y - i * line_spacing))


# ═══════════════════════════════════════════════════════════════════════════════
# GB/T A3 图框 + 国标标题栏 + 三视图布局
# ═══════════════════════════════════════════════════════════════════════════════

def add_border_frame(msp: Modelspace, width: float = 420.0,
                     height: float = 297.0, layer: str = "BORDER"):
    """A3 图框：外框 + 内框（左侧留25mm装订边，其余10mm边距）。

    GB/T 10609.1: 外框 d/2=0.25mm (细线), 内框 d=0.50mm (粗线)。
    """
    # 外框 (细线)
    msp.add_lwpolyline(
        [(0, 0), (width, 0), (width, height), (0, height), (0, 0)],
        dxfattribs={"layer": layer, "lineweight": 25},
    )
    # 内框（装订边25mm，其余10mm）— 粗线
    left = 25.0
    right = width - 10.0
    bottom = 10.0
    top = height - 10.0
    msp.add_lwpolyline(
        [(left, bottom), (right, bottom), (right, top),
         (left, top), (left, bottom)],
        dxfattribs={"layer": layer, "lineweight": 50},
    )
    return left, bottom, right, top


def add_gb_title_block(msp: Modelspace, part_no: str, name: str,
                       material: str, scale: str, weight_g: float,
                       designer: str, checker: str, date: str,
                       origin: Tuple[float, float] = (230.0, 10.0),
                       layer: str = "BORDER"):
    """GB/T 10609.1 标题栏 180x56mm，位于图框右下角。

    布局（从下往上 7 行，每行 8mm）：
      Row 0: 料号(part_no) | 图纸名称(name)
      Row 1: 材料(material) | 比例(scale) | 重量(weight)
      Row 2: 设计(designer) | 校核(checker) | 日期(date)
      Row 3-6: 项目名/单位/标准/图号 (简化)
    """
    x0, y0 = origin
    w = 180.0
    rh = 8.0  # row height
    rows = 7
    h = rh * rows  # 56mm

    # 外框 (粗线 d=0.50mm)
    msp.add_lwpolyline(
        [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h),
         (x0, y0 + h), (x0, y0)],
        dxfattribs={"layer": layer, "lineweight": 50},
    )

    # 水平分割线
    for i in range(1, rows):
        msp.add_line((x0, y0 + i * rh), (x0 + w, y0 + i * rh),
                     dxfattribs={"layer": layer})

    # 垂直分割（第0~2行分3列：col0=40, col1=90, col2=50）
    c1 = 40.0
    c2 = 130.0
    for i in range(3):
        yr = y0 + i * rh
        msp.add_line((x0 + c1, yr), (x0 + c1, yr + rh),
                     dxfattribs={"layer": layer})
        msp.add_line((x0 + c2, yr), (x0 + c2, yr + rh),
                     dxfattribs={"layer": layer})

    th_label = 2.0
    th_value = 2.5

    # Row 0: 料号 | 名称
    msp.add_text("零件编号", height=th_label,
                 dxfattribs={"layer": "TEXT", "color": 7}
                 ).set_placement((x0 + 2, y0 + 2))
    msp.add_text(part_no, height=th_value,
                 dxfattribs={"layer": "TEXT", "color": 7}
                 ).set_placement((x0 + c1 + 2, y0 + 2))
    msp.add_text(name, height=th_value,
                 dxfattribs={"layer": "TEXT", "color": 7}
                 ).set_placement((x0 + c2 + 2, y0 + 2))

    # Row 1: 材料 | 比例 | 重量
    yr1 = y0 + rh
    msp.add_text("材料", height=th_label,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + 2, yr1 + 2))
    msp.add_text(material, height=th_value,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + c1 + 2, yr1 + 2))
    msp.add_text(f"比例 {scale}  重量 {weight_g:.0f}g", height=th_value,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + c2 + 2, yr1 + 2))

    # Row 2: 设计 | 校核 | 日期
    yr2 = y0 + 2 * rh
    msp.add_text("设计", height=th_label,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + 2, yr2 + 2))
    msp.add_text(designer, height=th_value,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + c1 + 2, yr2 + 2))
    msp.add_text(f"校核 {checker}", height=th_value,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + c2 + 2, yr2 + 2))
    msp.add_text(date, height=th_value,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + w - 25, yr2 + 2))

    # Rows 3-6: project info
    yr3 = y0 + 3 * rh
    msp.add_text("GISBOT 双模态GIS局放检测机器人 \u2014 末端执行器", height=3.0,
                 dxfattribs={"layer": "TEXT", "color": 7}
                 ).set_placement((x0 + 2, yr3 + 2))

    yr4 = y0 + 4 * rh
    msp.add_text("投影法: GB/T 14692-2008 第一角", height=2.5,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + 2, yr4 + 2))
    msp.add_text("A3 (420\u00d7297)  单位: mm", height=2.5,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + 100, yr4 + 2))

    yr5 = y0 + 5 * rh
    msp.add_text("视图: GB/T 4458.1  公差: GB/T 1804-m", height=2.5,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + 2, yr5 + 2))
    msp.add_text("图框: GB/T 10609.1", height=2.5,
                 dxfattribs={"layer": "TEXT"}).set_placement((x0 + 120, yr5 + 2))

    yr6 = y0 + 6 * rh
    msp.add_text(f"图号: {part_no}", height=3.0,
                 dxfattribs={"layer": "TEXT", "color": 7}
                 ).set_placement((x0 + 2, yr6 + 2))


def calc_three_view_layout(
    front_wh: Tuple[float, float],
    top_wh: Tuple[float, float],
    left_wh: Tuple[float, float],
    paper: Tuple[float, float] = (420.0, 297.0),
    title_h: float = 56.0,
    gap: float = 30.0,
) -> dict:
    """根据三个视图的宽高自动计算居中布局位置。

    第一角投影法布局：
      主视图(front) 在左上，俯视图(top) 在主视图正下方，
      左视图(left) 在主视图正右方。

    Returns:
        dict with keys: front_origin, top_origin, left_origin, scale
        每个 origin 是 (x, y) 表示视图左下角坐标。
    """
    fw, fh = front_wh
    tw, th = top_wh
    lw, lh = left_wh

    # 可用绘图区域（去掉边距和标题栏）
    draw_left = 25.0
    draw_right = paper[0] - 10.0
    draw_bottom = 10.0 + title_h
    draw_top = paper[1] - 10.0

    avail_w = draw_right - draw_left
    avail_h = draw_top - draw_bottom

    # 三视图总需要的空间
    total_w = fw + gap + lw
    total_h = fh + gap + th

    # 计算缩放因子使图形适合图纸
    scale_w = (avail_w - 40) / total_w
    scale_h = (avail_h - 30) / total_h
    scale = min(scale_w, scale_h, 1.0)

    # 缩放后的尺寸
    sfw, sfh = fw * scale, fh * scale
    stw, sth = tw * scale, th * scale
    slw, slh = lw * scale, lh * scale
    sgap = gap * scale

    # 居中计算
    total_sw = sfw + sgap + slw
    total_sh = sfh + sgap + sth

    cx = draw_left + (avail_w - total_sw) / 2
    cy = draw_bottom + (avail_h - total_sh) / 2

    # 主视图左下角
    front_x = cx
    front_y = cy + sth + sgap

    # 俯视图左下角（在主视图正下方，X对齐）
    top_x = cx
    top_y = cy

    # 左视图左下角（在主视图正右方，Y底部对齐 = "高平齐"）
    left_x = cx + sfw + sgap
    left_y = front_y

    return {
        "front_origin": (front_x, front_y),
        "top_origin": (top_x, top_y),
        "left_origin": (left_x, left_y),
        "scale": scale,
        "front_size": (sfw, sfh),
        "top_size": (stw, sth),
        "left_size": (slw, slh),
    }


def add_projection_symbol(msp: Modelspace, pos: Tuple[float, float],
                          layer: str = "BORDER"):
    """GB/T 第一角投影符号（截圆锥 + 圆）。

    符号约 12mm 宽 x 10mm 高。
    """
    x, y = pos
    # 等腰梯形（截圆锥侧视图）
    msp.add_lwpolyline([
        (x, y + 2), (x + 8, y),
        (x + 8, y + 10), (x, y + 8), (x, y + 2),
    ], dxfattribs={"layer": layer, "lineweight": 50})
    # 右侧圆（投影面上的圆形投影）
    msp.add_circle((x + 12, y + 5), 3.0,
                   dxfattribs={"layer": layer, "lineweight": 50})
    # 圆心的水平线
    msp.add_line((x + 9, y + 5), (x + 15, y + 5),
                 dxfattribs={"layer": layer, "lineweight": 25})


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy compatibility — keep old add_title_block for any code still using it
# ═══════════════════════════════════════════════════════════════════════════════

def add_title_block(msp: Modelspace, part_no: str, title: str,
                    material: str, scale: str, date: str,
                    origin: Tuple[float, float] = (0, -50),
                    layer: str = "BORDER"):
    """Legacy simplified title block. Use add_gb_title_block instead."""
    x0, y0 = origin
    w, h = 180, 40

    msp.add_lwpolyline(
        [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)],
        dxfattribs={"layer": layer, "lineweight": 50},
    )

    for dy in [10, 20, 30]:
        msp.add_line((x0, y0 + dy), (x0 + w, y0 + dy),
                     dxfattribs={"layer": layer})

    msp.add_line((x0 + 50, y0), (x0 + 50, y0 + h),
                 dxfattribs={"layer": layer})

    labels = [("零件编号", part_no), ("名称", title),
              ("材料", material), (f"比例 {scale}", f"日期 {date}")]
    for i, (lbl, val) in enumerate(labels):
        yy = y0 + i * 10 + 2
        msp.add_text(lbl, height=2.0,
                     dxfattribs={"layer": "TEXT"}).set_placement((x0 + 2, yy))
        msp.add_text(val, height=3.0,
                     dxfattribs={"layer": "TEXT"}).set_placement((x0 + 55, yy))

    msp.add_text("GISBOT 末端执行器", height=3.5,
                 dxfattribs={"layer": "TEXT", "color": 7}
                 ).set_placement((x0 + w / 2, y0 + h + 3))


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience aliases used by draw_*.py part drawing modules
# ═══════════════════════════════════════════════════════════════════════════════

LAYER_HIDDEN: str = "HIDDEN"
LAYER_CENTER: str = "CENTER"


def add_line(msp: Modelspace,
             p1: Tuple[float, float], p2: Tuple[float, float],
             layer: str = "OUTLINE") -> None:
    """Thin wrapper: add a plain line entity."""
    msp.add_line(p1, p2, dxfattribs={"layer": layer})


def add_circle(msp: Modelspace,
               center: Tuple[float, float], radius: float,
               layer: str = "OUTLINE") -> None:
    """Thin wrapper: add a circle entity."""
    msp.add_circle(center, radius, dxfattribs={"layer": layer})


def dim_linear(msp: Modelspace,
               dim_p1: Tuple[float, float], dim_p2: Tuple[float, float],
               feat_p1: Tuple[float, float], feat_p2: Tuple[float, float],
               text: str = "",
               angle: Optional[float] = None) -> None:
    """Linear dimension: dim line at dim_p1/dim_p2, measuring feat_p1→feat_p2."""
    # Compute perpendicular offset from feature line to dimension line.
    # For horizontal dims offset is in Y; for vertical dims in X.
    dx = feat_p2[0] - feat_p1[0]
    dy = feat_p2[1] - feat_p1[1]
    if abs(dy) <= abs(dx):  # horizontal
        offset = dim_p1[1] - feat_p1[1]
    else:                   # vertical
        offset = dim_p1[0] - feat_p1[0]
    add_linear_dim(msp, feat_p1, feat_p2, offset, text, angle=angle)


def dim_diameter(msp: Modelspace,
                 center: Tuple[float, float], radius: float,
                 text: str = "") -> None:
    """Diameter dimension alias."""
    add_diameter_dim(msp, center, radius, text=text)


def add_centerline(msp: Modelspace,
                   p1: Tuple[float, float], p2: Tuple[float, float]) -> None:
    """Draw a CENTER-linetype line between two points."""
    msp.add_line(p1, p2, dxfattribs={"layer": LAYER_CENTER, "linetype": "CENTER"})


def add_centerline_circle(msp: Modelspace,
                          center: Tuple[float, float], radius: float) -> None:
    """Draw a CENTER-linetype circle (pitch circle / centerline circle)."""
    msp.add_circle(center, radius,
                   dxfattribs={"layer": LAYER_CENTER, "linetype": "CENTER"})


LAYER_VISIBLE: str = "OUTLINE"


def add_arc(msp: Modelspace,
           center: Tuple[float, float], radius: float,
           start_angle: float, end_angle: float,
           layer: str = "OUTLINE") -> None:
    """Thin wrapper: add an arc entity (angles in degrees)."""
    msp.add_arc(center, radius, start_angle, end_angle,
                dxfattribs={"layer": layer})


def dim_radius(msp: Modelspace,
              center: Tuple[float, float], radius: float,
              text: str = "") -> None:
    """Radius dimension alias."""
    add_radius_dim(msp, center, radius, text=text)


def add_hatch(msp: Modelspace,
             boundary_points: Sequence[Tuple[float, float]],
             layer: str = "HATCH",
             pattern: str = "ANSI31",
             scale: float = 1.0) -> None:
    """Thin wrapper: add a hatched region from a closed boundary polygon."""
    add_section_hatch(msp, boundary_points, layer=layer,
                      pattern=pattern, scale=scale)


def add_thread_symbol(msp: Modelspace,
                      x1: float, x2: float, cy: float,
                      major_r: float, minor_r: float,
                      scale: float = 1.0) -> None:
    """Draw GB/T 4459.1 external thread symbol on a side view.

    Draws two solid lines at ±major_r (outline) and two hidden lines at
    ±minor_r (minor diameter), spanning x1→x2.
    """
    # Major diameter — solid outline
    msp.add_line((x1, cy + major_r), (x2, cy + major_r),
                 dxfattribs={"layer": "OUTLINE"})
    msp.add_line((x1, cy - major_r), (x2, cy - major_r),
                 dxfattribs={"layer": "OUTLINE"})
    # Minor diameter — hidden (dashed)
    msp.add_line((x1, cy + minor_r), (x2, cy + minor_r),
                 dxfattribs={"layer": LAYER_HIDDEN})
    msp.add_line((x1, cy - minor_r), (x2, cy - minor_r),
                 dxfattribs={"layer": LAYER_HIDDEN})
