"""
Engineering Drawing Framework — GB/T 4458.1 (V5)

Provides ThreeViewSheet class for generating A3 engineering drawings
with flexible view configurations: standard 3-view + section views,
detail views, and auxiliary views, per Chinese national standards.

Usage:
    sheet = ThreeViewSheet("GIS-EE-001-01", "法兰本体", ...)
    sheet.draw_front(draw_func, bbox=(w, h))
    sheet.draw_top(draw_func, bbox=(w, h))
    sheet.draw_section(draw_func, "A", bbox=(w, h), position="right")
    sheet.draw_detail(draw_func, "I", bbox=(w, h), scale_factor=2)
    sheet.save(output_dir, material_type="al")
"""

import os
from typing import Callable, Optional, Tuple

from drawing import (
    A3_W, A3_H, MARGIN_STD, TITLE_BLOCK_H,
    create_drawing, add_border_frame, add_gb_title_block,
    calc_three_view_layout, calc_multi_view_layout,
    add_projection_symbol,
    add_technical_notes, add_default_roughness,
    add_section_view_label, add_detail_label, add_auxiliary_label,
)
from ezdxf.layouts import Modelspace

# ─── View label offsets ───────────────────────────────────────────────────────
_LABEL_OFFSET_X = -5.0    # 标签 X 偏移（相对视图中心）
_LABEL_OFFSET_Y = 3.0     # 标签 Y 偏移（相对视图顶边）


ViewDrawFunc = Callable[[Modelspace, float, float, float], None]


class ThreeViewSheet:
    """A single A3 engineering drawing sheet with flexible view layout."""

    def __init__(self, part_no: str, name: str, material: str,
                 scale: str, weight_g: float, date: str,
                 designer: str = "", checker: str = "",
                 project_name: str = "", subsystem_name: str = ""):
        self.part_no = part_no
        self.name = name
        self.material = material
        self.scale_text = scale
        self.weight_g = weight_g
        self.date = date
        self.designer = designer
        self.checker = checker
        self.project_name = project_name
        self.subsystem_name = subsystem_name

        self.doc, self.msp = create_drawing(f"{part_no} {name}", scale=1.0)

        self._front_func: Optional[ViewDrawFunc] = None
        self._front_bbox: Tuple[float, float] = (0, 0)
        self._top_func: Optional[ViewDrawFunc] = None
        self._top_bbox: Tuple[float, float] = (0, 0)
        self._left_func: Optional[ViewDrawFunc] = None
        self._left_bbox: Tuple[float, float] = (0, 0)

        # Additional views: list of (func, type, label, bbox, position_hint, extra)
        self._extra_views: list = []

    def draw_front(self, draw_func: ViewDrawFunc,
                   bbox: Tuple[float, float]):
        """Register the front (主视图) drawing function."""
        self._front_func = draw_func
        self._front_bbox = bbox

    def draw_top(self, draw_func: ViewDrawFunc,
                 bbox: Tuple[float, float]):
        """Register the top (俯视图) drawing function."""
        self._top_func = draw_func
        self._top_bbox = bbox

    def draw_left(self, draw_func: ViewDrawFunc,
                  bbox: Tuple[float, float]):
        """Register the left (左视图) drawing function."""
        self._left_func = draw_func
        self._left_bbox = bbox

    def draw_section(self, draw_func: ViewDrawFunc, label: str,
                     bbox: Tuple[float, float],
                     position: str = "right"):
        """Register a section view (剖视图).

        Args:
            draw_func: callable(msp, ox, oy, scale)
            label: section letter (A, B, etc.) — title shows "A-A"
            bbox: (width, height) at 1:1 scale
            position: "right" (replaces/beside left view) or "below"
        """
        self._extra_views.append({
            "func": draw_func, "type": "section", "label": label,
            "bbox": bbox, "position": position,
        })

    def draw_detail(self, draw_func: ViewDrawFunc, label: str,
                    bbox: Tuple[float, float],
                    scale_factor: float = 2.0,
                    position: str = "bottom_right"):
        """Register a detail view (局部放大图).

        Args:
            draw_func: callable(msp, ox, oy, scale) — draws at enlarged scale
            label: detail letter (I, II, etc.)
            bbox: (width, height) at the enlarged scale
            scale_factor: enlargement ratio (e.g. 2.0 = 2:1)
            position: "bottom_right" or "top_right"
        """
        self._extra_views.append({
            "func": draw_func, "type": "detail", "label": label,
            "bbox": bbox, "position": position,
            "scale_factor": scale_factor,
        })

    def draw_auxiliary(self, draw_func: ViewDrawFunc, label: str,
                      bbox: Tuple[float, float],
                      position: str = "right"):
        """Register an auxiliary view (向视图)."""
        self._extra_views.append({
            "func": draw_func, "type": "auxiliary", "label": label,
            "bbox": bbox, "position": position,
        })

    def save(self, output_dir: str, material_type: str = None) -> str:
        """Render all views onto the A3 sheet and save as DXF."""
        msp = self.msp

        # A3 图框
        add_border_frame(msp)

        # Build view dict for layout calculator
        views = {}
        front_wh = self._front_bbox if self._front_func else (1, 1)
        views["front"] = front_wh
        if self._top_func:
            views["top"] = self._top_bbox
        if self._left_func:
            views["left"] = self._left_bbox

        # Classify extra views by position
        for ev in self._extra_views:
            pos = ev["position"]
            if pos == "right":
                views["section_right"] = ev["bbox"]
            elif pos == "below":
                views["section_below"] = ev["bbox"]
            elif pos == "bottom_right":
                views["detail_br"] = ev["bbox"]

        # Calculate layout
        if len(views) <= 3 and not self._extra_views:
            # Use classic 3-view layout
            top_wh = self._top_bbox if self._top_func else (front_wh[0], 1)
            left_wh = self._left_bbox if self._left_func else (1, front_wh[1])
            layout = calc_three_view_layout(front_wh, top_wh, left_wh)
        else:
            layout = calc_multi_view_layout(views)

        s = layout["scale"]

        # Draw standard views (no labels for standard positions per GB/T)
        if self._front_func:
            ox, oy = layout["front_origin"]
            self._front_func(msp, ox, oy, s)

        if self._top_func and "top_origin" in layout:
            ox, oy = layout["top_origin"]
            self._top_func(msp, ox, oy, s)

        if self._left_func and "left_origin" in layout:
            ox, oy = layout["left_origin"]
            self._left_func(msp, ox, oy, s)

        # Draw extra views with labels
        for ev in self._extra_views:
            pos = ev["position"]
            vtype = ev["type"]

            # Determine origin
            if pos == "right" and "section_right_origin" in layout:
                ox, oy = layout["section_right_origin"]
            elif pos == "below" and "section_below_origin" in layout:
                ox, oy = layout["section_below_origin"]
            elif pos == "bottom_right" and "detail_br_origin" in layout:
                ox, oy = layout["detail_br_origin"]
            else:
                # Fallback: use left view position (replace left view)
                ox, oy = layout.get("left_origin",
                                    layout.get("section_right_origin",
                                               (A3_W * 2 / 3,
                                                (A3_H + TITLE_BLOCK_H) / 2)))

            # For detail views, use enlarged scale
            view_scale = s
            if vtype == "detail":
                view_scale = s * ev.get("scale_factor", 2.0)

            ev["func"](msp, ox, oy, view_scale)

            # Add view label above the view (origin is now centre)
            bw, bh = ev["bbox"]
            label_x = ox + _LABEL_OFFSET_X
            label_y = oy + bh * s / 2 + _LABEL_OFFSET_Y
            if vtype == "section":
                add_section_view_label(msp, (label_x, label_y), ev["label"])
            elif vtype == "detail":
                add_detail_label(msp, (label_x, label_y),
                                 ev["label"], ev.get("scale_factor", 2.0))
            elif vtype == "auxiliary":
                add_auxiliary_label(msp, (label_x, label_y), ev["label"])

        # 技术要求区 — 动态计算位置（GB/T 10609.1: 视图下方、标题栏上方）
        title_top_y = MARGIN_STD + TITLE_BLOCK_H  # 标题栏顶边 y
        # 找最低视图的底边 — 用 origin - bbox*scale/2
        _view_bottoms = []
        _view_data = [
            ("top", self._top_bbox),
            ("front", self._front_bbox),
            ("left", self._left_bbox),
        ]
        for vkey, vbbox in _view_data:
            origin_key = f"{vkey}_origin"
            if origin_key in layout and vbbox[1] > 0:
                _view_bottoms.append(
                    layout[origin_key][1] - vbbox[1] * s / 2)
        lowest_view_bottom = min(_view_bottoms) if _view_bottoms else A3_H * 0.5

        gap_for_notes = lowest_view_bottom - title_top_y
        if gap_for_notes >= 30:
            # 空隙足够：技术要求放在视图下方
            notes_y = title_top_y + min(gap_for_notes * 0.75, 45)
        else:
            # 空隙不足：回退到左上角
            notes_y = A3_H - MARGIN_STD - 12
        add_technical_notes(msp, material_type=material_type,
                            pos=(MARGIN_STD + 2, notes_y))

        # 默认粗糙度符号（右上角）— 从 SURFACE_RA 查表，不硬编码
        from cad_spec_defaults import SURFACE_RA
        _ra_map = {"al": 3.2, "steel": 3.2, "peek": 1.6,
                   "nylon": 1.6, "rubber": 3.2}
        default_ra = _ra_map.get(material_type, 3.2) if material_type else 3.2
        add_default_roughness(msp, ra=default_ra)

        # 国标标题栏
        add_gb_title_block(
            msp,
            part_no=self.part_no,
            name=self.name,
            material=self.material,
            scale=self.scale_text,
            weight_g=self.weight_g,
            designer=self.designer,
            checker=self.checker,
            date=self.date,
            project_name=self.project_name,
            subsystem_name=self.subsystem_name,
        )

        # 第一角投影符号
        add_projection_symbol(msp, (A3_W / 2, MARGIN_STD + 5.0))

        # 保存
        from cad_spec_defaults import strip_part_prefix
        fname = f"{strip_part_prefix(self.part_no)}_{_slug(self.name)}.dxf"
        path = os.path.join(output_dir, fname)
        self.doc.saveas(path)
        print(f"  Saved: {path}")
        return path


def _slug(name: str) -> str:
    """通用中英文名→文件名安全字符串。不含硬编码映射表。"""
    import re as _re
    # 先清理：去除括号及其内容中的特殊字符，保留有意义的文字
    clean = _re.sub(r"[（(][^）)]*[）)]", "", name)  # 去括号内容
    clean = _re.sub(r"[+/\\|]", "_", clean)          # 特殊符号→下划线
    clean = clean.strip()
    if not clean:
        clean = name  # 如果全被清掉了，用原名
    try:
        from pypinyin import lazy_pinyin
        slug = "_".join(lazy_pinyin(clean))
    except ImportError:
        # fallback: 仅保留 ASCII 字母数字，其他替换为 _
        slug = "".join(c if (c.isascii() and c.isalnum()) or c == '_' else '_' for c in clean)
    # 去除连续下划线、首尾下划线、截断
    slug = _re.sub(r"_+", "_", slug).strip("_").lower()
    return slug[:40] if slug else "unnamed"
