# ── AUTO-DEPLOYED from project root. DO NOT EDIT THIS COPY. ──────────
# Authoritative source: D:\Work\cad-spec-gen/cq_to_dxf.py
# Deployed by: cad_pipeline.py _deploy_tool_modules()
# To modify, edit the root copy and re-run: python cad_pipeline.py codegen
# ─────────────────────────────────────────────────────────────────────
"""
cq_to_dxf.py — CadQuery 3D Solid → ezdxf 2D Three-View Projection Bridge

Uses OCC HLRBRep_Algo (Hidden Line Removal) for true orthographic projection
with visible/hidden edge classification per GB/T 4458.1.

Usage:
    from cq_to_dxf import auto_three_view
    sheet = ThreeViewSheet(...)
    auto_three_view(solid, sheet)
    sheet.save(output_dir)

No hardcoded part information — pure geometry library.
"""

import math
from typing import List, Tuple, Optional

import cadquery as cq

from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_UniformDeflection
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle


def _convex_hull(points):
    """Compute convex hull of 2D points (Andrew's monotone chain).

    Returns list of (x, y) vertices in counter-clockwise order.
    Used by auto_section_overlay to build the actual cross-section
    outer boundary from HLR projected edge endpoints.
    """
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# ── GB/T 14692-2008 First Angle Projection View Directions ──────────────────
# Each view is defined by (eye_direction, x_direction):
#   eye_direction = where the camera looks FROM (normal to projection plane)
#   x_direction  = horizontal axis on the projection plane (right = +X in DXF)
#
# GB/T first angle:
#   Front (主视图): look along +Y → project onto XZ plane
#   Top   (俯视图): look along +Z → project onto XY plane (below front view)
#   Left  (左视图): look along -X → project onto YZ plane (right of front view)
VIEW_DIRS = {
    "front": (gp_Dir(0, 1, 0), gp_Dir(1, 0, 0)),   # look +Y, X→right
    "top":   (gp_Dir(0, 0, 1), gp_Dir(1, 0, 0)),   # look +Z, X→right
    "left":  (gp_Dir(-1, 0, 0), gp_Dir(0, 1, 0)),  # look -X, Y→right
}


def _hlr_project(shape, eye_dir: gp_Dir, x_dir: gp_Dir):
    """Run OCC HLR projection and return (visible_compound, hidden_compound)."""
    hlr = HLRBRep_Algo()
    hlr.Add(shape)
    projector = HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), eye_dir, x_dir))
    hlr.Projector(projector)
    hlr.Update()
    hlr.Hide()
    hlr_shapes = HLRBRep_HLRToShape(hlr)

    visible = hlr_shapes.VCompound()
    hidden = hlr_shapes.HCompound()
    return visible, hidden


def _extract_edges(compound, offset_x: float, offset_y: float,
                   scale: float) -> List[Tuple]:
    """Extract edges from an OCC compound as drawable primitives.

    Returns list of tuples:
      ("LINE", x1, y1, x2, y2)
      ("ARC", cx, cy, radius, start_angle_deg, end_angle_deg)
      ("POLYLINE", [(x1,y1), (x2,y2), ...])  — for splines/complex curves
    """
    if compound.IsNull():
        return []

    result = []
    explorer = TopExp_Explorer(compound, TopAbs_EDGE)

    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        adaptor = BRepAdaptor_Curve(edge)
        curve_type = adaptor.GetType()

        if curve_type == GeomAbs_Line:
            p1 = adaptor.Value(adaptor.FirstParameter())
            p2 = adaptor.Value(adaptor.LastParameter())
            result.append((
                "LINE",
                p1.X() * scale + offset_x, -p1.Y() * scale + offset_y,
                p2.X() * scale + offset_x, -p2.Y() * scale + offset_y,
            ))

        elif curve_type == GeomAbs_Circle:
            circ = adaptor.Circle()
            cx = circ.Location().X() * scale + offset_x
            cy = -circ.Location().Y() * scale + offset_y
            r = circ.Radius() * scale
            f = adaptor.FirstParameter()
            l = adaptor.LastParameter()

            if abs(l - f - 2 * math.pi) < 0.01:
                # Full circle
                result.append(("CIRCLE", cx, cy, r))
            else:
                # Arc — convert parameter to angle in degrees
                # HLR projects circles; angles are in the projection plane
                start_deg = math.degrees(f)
                end_deg = math.degrees(l)
                # Flip Y: negate angles
                result.append(("ARC", cx, cy, r, -end_deg, -start_deg))

        else:
            # BSpline / other — tessellate to polyline
            deflection = GCPnts_UniformDeflection(adaptor, 0.1 * scale)
            if deflection.IsDone() and deflection.NbPoints() >= 2:
                pts = []
                for i in range(1, deflection.NbPoints() + 1):
                    p = deflection.Value(i)
                    pts.append((
                        p.X() * scale + offset_x,
                        -p.Y() * scale + offset_y,
                    ))
                result.append(("POLYLINE", pts))

        explorer.Next()

    return result


def _draw_edges(msp, edges: List[Tuple], layer: str):
    """Draw extracted edges onto an ezdxf modelspace."""
    for e in edges:
        if e[0] == "LINE":
            _, x1, y1, x2, y2 = e
            msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})

        elif e[0] == "CIRCLE":
            _, cx, cy, r = e
            msp.add_circle((cx, cy), r, dxfattribs={"layer": layer})

        elif e[0] == "ARC":
            _, cx, cy, r, start_deg, end_deg = e
            msp.add_arc((cx, cy), r, start_deg, end_deg,
                        dxfattribs={"layer": layer})

        elif e[0] == "POLYLINE":
            _, pts = e
            if len(pts) >= 2:
                msp.add_lwpolyline(pts, dxfattribs={"layer": layer})


def project_view(solid: cq.Workplane, view_name: str,
                 msp, ox: float, oy: float, scale: float):
    """Project a CadQuery solid onto a named view and draw to ezdxf msp.

    Args:
        solid: CadQuery Workplane containing the 3D solid
        view_name: "front", "top", or "left"
        msp: ezdxf Modelspace
        ox, oy: origin offset for this view on the drawing sheet
        scale: drawing scale factor
    """
    shape = solid.val().wrapped
    eye_dir, x_dir = VIEW_DIRS[view_name]
    visible, hidden = _hlr_project(shape, eye_dir, x_dir)

    # Center the projection: compute projected bounding box
    vis_edges = _extract_edges(visible, 0, 0, 1.0)
    hid_edges = _extract_edges(hidden, 0, 0, 1.0)

    all_pts = []
    for e in vis_edges + hid_edges:
        if e[0] == "LINE":
            all_pts.extend([(e[1], e[2]), (e[3], e[4])])
        elif e[0] in ("CIRCLE", "ARC"):
            all_pts.append((e[1], e[2]))
        elif e[0] == "POLYLINE":
            all_pts.extend(e[1])

    if not all_pts:
        return

    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2

    # Re-extract with centering + scale + offset
    vis_edges = _extract_edges(visible, ox - cx * scale, oy - cy * scale, scale)
    hid_edges = _extract_edges(hidden, ox - cx * scale, oy - cy * scale, scale)

    _draw_edges(msp, vis_edges, "OUTLINE")
    _draw_edges(msp, hid_edges, "HIDDEN")


def get_projected_bbox(solid: cq.Workplane, view_name: str) -> Tuple[float, float]:
    """Get the (width, height) of a projected view at 1:1 scale.

    Returns (w, h) in mm — used for ThreeViewSheet layout calculation.
    """
    shape = solid.val().wrapped
    eye_dir, x_dir = VIEW_DIRS[view_name]
    visible, hidden = _hlr_project(shape, eye_dir, x_dir)

    all_pts = []
    for compound in (visible, hidden):
        edges = _extract_edges(compound, 0, 0, 1.0)
        for e in edges:
            if e[0] == "LINE":
                all_pts.extend([(e[1], e[2]), (e[3], e[4])])
            elif e[0] in ("CIRCLE", "ARC"):
                r = e[3]
                all_pts.extend([(e[1] - r, e[2] - r), (e[1] + r, e[2] + r)])
            elif e[0] == "POLYLINE":
                all_pts.extend(e[1])

    if not all_pts:
        return (1, 1)

    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    return (max(xs) - min(xs), max(ys) - min(ys))


def auto_three_view(solid: cq.Workplane, sheet):
    """Auto-project a CadQuery solid into front/top/left views on a ThreeViewSheet.

    This is the main entry point for template-generated DXF functions.
    Registers view callbacks that use OCC HLR projection.

    Args:
        solid: CadQuery Workplane with the 3D geometry
        sheet: ThreeViewSheet instance (from draw_three_view.py)
    """
    front_bbox = get_projected_bbox(solid, "front")
    top_bbox = get_projected_bbox(solid, "top")
    left_bbox = get_projected_bbox(solid, "left")

    def _make_view_callback(view_name):
        def draw(msp, ox, oy, scale):
            project_view(solid, view_name, msp, ox, oy, scale)
        return draw

    sheet.draw_front(_make_view_callback("front"), front_bbox)
    sheet.draw_top(_make_view_callback("top"), top_bbox)
    sheet.draw_left(_make_view_callback("left"), left_bbox)

    # Store bbox info for auto_annotate to use
    sheet._auto_bboxes = {
        "front": front_bbox,
        "top": top_bbox,
        "left": left_bbox,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-annotation engine (GB/T 4458.4 + GB/T 4458.1 + GB/T 131 + GB/T 1182)
# ═══════════════════════════════════════════════════════════════════════════════


def _detect_circles(solid: cq.Workplane, view_name: str) -> List[Tuple]:
    """Detect projected circles in a view.

    Returns list of (cx, cy, radius) at 1:1 scale (unscaled, uncentered).
    """
    shape = solid.val().wrapped
    eye_dir, x_dir = VIEW_DIRS[view_name]
    visible, _hidden = _hlr_project(shape, eye_dir, x_dir)

    circles = []
    edges = _extract_edges(visible, 0, 0, 1.0)
    for e in edges:
        if e[0] == "CIRCLE":
            _, cx, cy, r = e
            circles.append((cx, cy, r))
    return circles


def auto_annotate(solid: cq.Workplane, sheet, annotation_meta: dict = None):
    """几何驱动 + Spec 驱动的自动标注引擎。

    在 auto_three_view() 之后调用。分两阶段：

    1. 几何驱动（无需 spec 数据）：
       - 外形尺寸：每个视图的 bbox → add_linear_dim (GB/T 4458.4)
       - 圆直径：检测到的 Circle → add_diameter_dim (GB/T 4458.4)
       - 中心线：圆心十字 + 视图对称轴 (GB/T 4458.1)

    2. Spec 驱动（从 annotation_meta 传入，可选）：
       - 公差文本：§2.1 tolerance → 覆盖尺寸文本 (GB/T 4458.4)
       - 形位公差：§2.2 GD&T → add_gdt_frame (GB/T 1182-2018)
       - 个别面粗糙度：§2.3 Ra → add_surface_symbol (GB/T 131-2006)

    Args:
        solid: CadQuery Workplane (same one passed to auto_three_view)
        sheet: ThreeViewSheet (after auto_three_view registered views)
        annotation_meta: optional dict with keys:
            "dim_tolerances": [{name, nominal, upper, lower, fit_code, label}]
            "gdt": [{symbol, value, datum, parts}]
            "surfaces": [{part, ra, process}]
    """
    from drawing import (
        add_linear_dim, add_diameter_dim,
        add_centerline_cross, add_centerline_h, add_centerline_v,
        add_gdt_frame, add_surface_symbol,
        AnnotationPlacer, allocate_dim_angles,
        DIM_FIRST_OFFSET, DIM_TEXT_H, CENTERLINE_OVERSHOOT,
    )

    meta = annotation_meta or {}
    msp = sheet.msp

    # Retrieve layout info — we need origins and scale from the sheet
    # after save() is called, but we annotate before save().
    # So we compute layout ourselves using the stored bboxes.
    bboxes = getattr(sheet, "_auto_bboxes", {})
    if not bboxes:
        return  # No views registered

    from drawing import calc_three_view_layout
    front_wh = bboxes.get("front", (1, 1))
    top_wh = bboxes.get("top", (front_wh[0], 1))
    left_wh = bboxes.get("left", (1, front_wh[1]))
    layout = calc_three_view_layout(front_wh, top_wh, left_wh)
    scale = layout["scale"]

    # ── Phase 1: Geometry-driven annotations ─────────────────────────────────

    views_info = {
        "front": {"bbox": front_wh, "origin": layout["front_origin"]},
        "top":   {"bbox": top_wh,   "origin": layout["top_origin"]},
        "left":  {"bbox": left_wh,  "origin": layout["left_origin"]},
    }

    for view_name, vinfo in views_info.items():
        bbox_w, bbox_h = vinfo["bbox"]
        ox, oy = vinfo["origin"]
        paper_w = bbox_w * scale
        paper_h = bbox_h * scale

        placer = AnnotationPlacer()
        max_dims = placer.max_dims_for_view(paper_w, paper_h)
        dim_count = 0

        # ── Overall dimensions ───────────────────────────────────────────────
        # Width dimension (horizontal, below the view)
        if dim_count < max_dims:
            h_off = placer.next_h_offset()
            p1 = (ox - paper_w / 2, oy - paper_h / 2 - h_off)
            p2 = (ox + paper_w / 2, oy - paper_h / 2 - h_off)
            dim_text = f"{bbox_w:.1f}"

            # Check if any tolerance matches this dimension
            tol_label = _match_tolerance(meta, bbox_w, ["W", "OD", "DIA", "WIDTH"])
            if tol_label:
                dim_text = tol_label

            add_linear_dim(msp, p1, p2, offset=0, text=dim_text, angle=0)
            dim_count += 1

        # Height dimension (vertical, right of the view) — only for front view
        if view_name == "front" and dim_count < max_dims:
            v_off = placer.next_v_offset()
            p1 = (ox + paper_w / 2 + v_off, oy - paper_h / 2)
            p2 = (ox + paper_w / 2 + v_off, oy + paper_h / 2)
            dim_text = f"{bbox_h:.1f}"

            tol_label = _match_tolerance(meta, bbox_h, ["H", "THICK", "HEIGHT"])
            if tol_label:
                dim_text = tol_label

            add_linear_dim(msp, p1, p2, offset=0, text=dim_text, angle=90)
            dim_count += 1

        # Depth dimension (俯视图 or 左视图 — the dimension orthogonal to front)
        if view_name == "top" and dim_count < max_dims:
            h_off = placer.next_h_offset()
            p1 = (ox - paper_w / 2, oy - paper_h / 2 - h_off)
            p2 = (ox + paper_w / 2, oy - paper_h / 2 - h_off)
            dim_text = f"{bbox_h:.1f}"

            tol_label = _match_tolerance(meta, bbox_h, ["D", "DEPTH", "L"])
            if tol_label:
                dim_text = tol_label

            add_linear_dim(msp,
                           (ox - paper_w / 2, oy + paper_h / 2 + h_off),
                           (ox + paper_w / 2, oy + paper_h / 2 + h_off),
                           offset=0, text=dim_text, angle=0)
            dim_count += 1

        # ── Circle / hole diameters ──────────────────────────────────────────
        circles_raw = _detect_circles(solid, view_name)
        if circles_raw:
            # Deduplicate by approximate radius (within 0.5mm)
            unique_circles = []
            seen_radii = set()
            for cx, cy, r in sorted(circles_raw, key=lambda c: c[2], reverse=True):
                r_key = round(r, 0)
                if r_key not in seen_radii:
                    unique_circles.append((cx, cy, r))
                    seen_radii.add(r_key)

            angles = allocate_dim_angles(len(unique_circles))
            # Compute projection center for offset
            all_pts = []
            for cx, cy, r in circles_raw:
                all_pts.extend([(cx - r, cy - r), (cx + r, cy + r)])
            if all_pts:
                xs = [p[0] for p in all_pts]
                ys = [p[1] for p in all_pts]
                proj_cx = (min(xs) + max(xs)) / 2
                proj_cy = (min(ys) + max(ys)) / 2
            else:
                proj_cx = proj_cy = 0

            for i, (raw_cx, raw_cy, raw_r) in enumerate(unique_circles):
                if dim_count >= max_dims:
                    break
                # Transform to paper coordinates (centered on view origin)
                paper_cx = ox + (raw_cx - proj_cx) * scale
                paper_cy = oy + (-raw_cy + proj_cy) * scale  # Y flipped in HLR
                paper_r = raw_r * scale

                if paper_r < 1.0:  # Too small to label
                    continue

                dim_text = f"\u03a6{raw_r * 2:.1f}"
                tol_label = _match_tolerance(meta, raw_r * 2, ["OD", "ID", "DIA", "BORE", "HOLE"])
                if tol_label:
                    dim_text = tol_label

                add_diameter_dim(msp, (paper_cx, paper_cy), paper_r,
                                 angle_deg=angles[i], text=dim_text)
                dim_count += 1

        # ── Center lines ─────────────────────────────────────────────────────
        # View center cross (if view has reasonable symmetry)
        overshoot = CENTERLINE_OVERSHOOT
        add_centerline_h(msp, oy,
                         ox - paper_w / 2 - overshoot,
                         ox + paper_w / 2 + overshoot)
        add_centerline_v(msp, ox,
                         oy - paper_h / 2 - overshoot,
                         oy + paper_h / 2 + overshoot)

        # Circle center crosses
        if circles_raw:
            for raw_cx, raw_cy, raw_r in unique_circles[:4]:  # Limit to 4
                paper_cx = ox + (raw_cx - proj_cx) * scale
                paper_cy = oy + (-raw_cy + proj_cy) * scale
                paper_r = raw_r * scale
                if paper_r >= 2.0:
                    add_centerline_cross(msp, (paper_cx, paper_cy),
                                         size=paper_r + overshoot)

        # ── Position dimensions (GB/T 4458.4: 位置尺寸) ─────────────────────
        # 标注孔心到基准边（左/底）的距离，仅在俯视图标注，限 ≤4 组
        if view_name == "top" and circles_raw:
            _MAX_POS_DIMS = 4
            pos_dim_count = 0
            # 对称去重：按 abs(cx) + abs(cy) 排序，取不同位置的孔
            seen_positions = set()
            pos_circles = []
            for raw_cx, raw_cy, raw_r in unique_circles:
                key = (round(abs(raw_cx), 0), round(abs(raw_cy), 0))
                if key not in seen_positions:
                    pos_circles.append((raw_cx, raw_cy, raw_r))
                    seen_positions.add(key)

            for raw_cx, raw_cy, raw_r in pos_circles:
                if pos_dim_count >= _MAX_POS_DIMS:
                    break
                paper_cx = ox + (raw_cx - proj_cx) * scale
                paper_cy = oy + (-raw_cy + proj_cy) * scale

                # 水平位置尺寸：孔心到左边缘
                dist_h = raw_cx - (-bbox_w / 2)  # raw coords: center-based
                if dist_h > 1.0 and abs(dist_h - bbox_w) > 1.0:
                    h_off = placer.next_h_offset()
                    left_edge_x = ox - paper_w / 2
                    add_linear_dim(msp,
                                   (left_edge_x, oy - paper_h / 2 - h_off),
                                   (paper_cx, oy - paper_h / 2 - h_off),
                                   offset=0, text=f"{dist_h:.1f}", angle=0)
                    pos_dim_count += 1

                if pos_dim_count >= _MAX_POS_DIMS:
                    break

                # 垂直位置尺寸：孔心到底边缘
                # HLR 中 Y 翻转，raw_cy 对应实际 Y 坐标
                dist_v = -raw_cy - (-bbox_h / 2)
                if dist_v > 1.0 and abs(dist_v - bbox_h) > 1.0:
                    v_off = placer.next_v_offset()
                    bottom_edge_y = oy - paper_h / 2
                    add_linear_dim(msp,
                                   (ox + paper_w / 2 + v_off, bottom_edge_y),
                                   (ox + paper_w / 2 + v_off, paper_cy),
                                   offset=0, text=f"{dist_v:.1f}", angle=90)
                    pos_dim_count += 1

    # ── Phase 2: Spec-driven annotations (front view only) ───────────────────

    front_ox, front_oy = layout["front_origin"]
    front_paper_w = front_wh[0] * scale
    front_paper_h = front_wh[1] * scale

    # GD&T frames (GB/T 1182-2018)
    gdt_entries = meta.get("gdt", [])
    if gdt_entries:
        gdt_x = front_ox + front_paper_w / 2 + DIM_FIRST_OFFSET + 15
        gdt_y = front_oy + front_paper_h / 4
        gdt_tuples = []
        for g in gdt_entries[:3]:  # Max 3 GD&T frames
            sym = g.get("symbol", "")
            val = g.get("value", "")
            dat = g.get("datum", "")
            if sym or val:
                gdt_tuples.append((sym, val, dat))
        if gdt_tuples:
            add_gdt_frame(msp, (gdt_x, gdt_y), gdt_tuples)

    # Surface roughness symbols (GB/T 131-2006)
    surfaces = meta.get("surfaces", [])
    if surfaces:
        surf_x = front_ox - front_paper_w / 2 - 5
        surf_y = front_oy + front_paper_h / 4
        for i, s in enumerate(surfaces[:2]):  # Max 2 surface symbols
            ra_text = s.get("ra", "")
            if ra_text:
                # Extract numeric Ra value
                import re as _re
                m = _re.search(r"(\d+\.?\d*)", str(ra_text))
                if m:
                    ra_val = float(m.group(1))
                    add_surface_symbol(msp, (surf_x, surf_y - i * 12), ra_val)


# ═══════════════════════════════════════════════════════════════════════════════
# Section overlay (GB/T 4458.6 — 叠加剖面线到已有视图)
# ═══════════════════════════════════════════════════════════════════════════════


def auto_section_overlay(
    solid: cq.Workplane,
    sheet,
    cut_plane: str = "YZ",
    label: str = "A",
    hatch_on: str = "left",
    indicator_on: str = "top",
):
    """在已有视图上叠加剖面线 + 在另一视图上画剖切指示线。

    叠加模式：不替换 auto_three_view 注册的视图，只在其上额外绘制：
    1. 在 hatch_on 视图上叠加剖面线（实体区域画 45° 斜线，孔区域留白）
    2. 在 indicator_on 视图上画 A-A 剖切指示线
    3. 在 hatch_on 视图上方标注 "A-A"

    Args:
        solid: CadQuery Workplane (same one passed to auto_three_view)
        sheet: ThreeViewSheet (after auto_three_view registered views)
        cut_plane: "YZ" (cuts along X, projects left view) or "XZ" (cuts along Y)
        label: section letter (e.g. "A" → "A-A")
        hatch_on: which view to overlay hatch on ("left" or "front")
        indicator_on: which view to draw cut indicator on ("top" or "front")
    """
    from drawing import (
        add_section_hatch_with_holes, add_section_cut_indicator,
        add_section_view_label, calc_three_view_layout,
    )

    bboxes = getattr(sheet, "_auto_bboxes", {})
    if not bboxes:
        return

    front_wh = bboxes.get("front", (1, 1))
    top_wh = bboxes.get("top", (front_wh[0], 1))
    left_wh = bboxes.get("left", (1, front_wh[1]))
    layout = calc_three_view_layout(front_wh, top_wh, left_wh)
    scale = layout["scale"]
    msp = sheet.msp

    # ── 1. Determine hatch view and compute layout ────────────────────────
    if cut_plane == "YZ":
        hatch_view = "left"
        ind_view = "top"
    else:
        hatch_view = "front"
        ind_view = "left"

    hatch_ox, hatch_oy = layout[f"{hatch_view}_origin"]
    hatch_wh = bboxes[hatch_view]
    hatch_pw = hatch_wh[0] * scale
    hatch_ph = hatch_wh[1] * scale

    # ── 2. Build hatch boundaries from actual 3D geometry ──────────────────
    # Use HLR visible edges to extract the REAL outer profile (not bbox rectangle).
    # This handles non-rectangular cross-sections (cylinders, L-brackets, etc.)
    shape_wrapped = solid.val().wrapped
    eye_dir, x_dir = VIEW_DIRS[hatch_view]
    visible, hidden = _hlr_project(shape_wrapped, eye_dir, x_dir)

    # Collect ALL projected points for centering
    vis_edges = _extract_edges(visible, 0, 0, 1.0)
    hid_edges = _extract_edges(hidden, 0, 0, 1.0)
    all_edges = vis_edges + hid_edges
    all_pts = []
    for e in all_edges:
        if e[0] == "LINE":
            all_pts.extend([(e[1], e[2]), (e[3], e[4])])
        elif e[0] in ("CIRCLE", "ARC"):
            all_pts.append((e[1], e[2]))
        elif e[0] == "POLYLINE":
            all_pts.extend(e[1])

    if all_pts:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        proj_cx = (min(xs) + max(xs)) / 2
        proj_cy = (min(ys) + max(ys)) / 2
    else:
        proj_cx = proj_cy = 0

    # Build outer boundary from visible LINE edges (the actual cross-section outline).
    # Collect line endpoints, then compute convex hull as the outer hatch boundary.
    # This correctly handles any cross-section shape (box, cylinder, L-bracket, etc.)
    outline_pts = []
    for e in vis_edges:
        if e[0] == "LINE":
            for px, py in [(e[1], e[2]), (e[3], e[4])]:
                paper_px = hatch_ox + (px - proj_cx) * scale
                paper_py = hatch_oy + (-py + proj_cy) * scale
                outline_pts.append((paper_px, paper_py))

    if len(outline_pts) >= 3:
        outer = _convex_hull(outline_pts)
    else:
        # Fallback: use bbox rectangle (only if HLR produced no lines)
        half_w = hatch_pw / 2
        half_h = hatch_ph / 2
        outer = [
            (hatch_ox - half_w, hatch_oy - half_h),
            (hatch_ox + half_w, hatch_oy - half_h),
            (hatch_ox + half_w, hatch_oy + half_h),
            (hatch_ox - half_w, hatch_oy + half_h),
        ]

    # Detect circles in the hatch view to build inner (exclusion) boundaries
    circles = _detect_circles(solid, hatch_view)
    inner_boundaries = []

    for raw_cx, raw_cy, raw_r in circles:
        paper_cx = hatch_ox + (raw_cx - proj_cx) * scale
        paper_cy = hatch_oy + (-raw_cy + proj_cy) * scale
        paper_r = raw_r * scale
        if paper_r < 0.5:
            continue
        # Approximate circle as polygon for hatch exclusion
        n_seg = 24
        circle_pts = []
        for j in range(n_seg):
            angle = 2 * math.pi * j / n_seg
            circle_pts.append((
                paper_cx + paper_r * math.cos(angle),
                paper_cy + paper_r * math.sin(angle),
            ))
        inner_boundaries.append(circle_pts)

    # Draw hatch (GB/T 4457.5: 45° hatching for metal, holes excluded)
    if inner_boundaries:
        add_section_hatch_with_holes(msp, outer, inner_boundaries,
                                     pattern="ANSI31", scale=1.0)
    else:
        # No holes → simple hatch
        from drawing import add_section_hatch
        add_section_hatch(msp, outer, pattern="ANSI31", scale=1.0)

    # ── 3. Draw section cut indicator on source view ────────────────────────
    ind_ox, ind_oy = layout[f"{ind_view}_origin"]
    ind_wh = bboxes[ind_view]
    ind_pw = ind_wh[0] * scale
    ind_ph = ind_wh[1] * scale

    if cut_plane == "YZ":
        # Vertical cut line on top view (through center X=0)
        cut_p1 = (ind_ox, ind_oy - ind_ph / 2 - 3)
        cut_p2 = (ind_ox, ind_oy + ind_ph / 2 + 3)
    else:
        # Horizontal cut line on left view (through center Y=0)
        cut_p1 = (ind_ox - ind_pw / 2 - 3, ind_oy)
        cut_p2 = (ind_ox + ind_pw / 2 + 3, ind_oy)

    add_section_cut_indicator(msp, label, cut_p1, cut_p2)

    # ── 4. Label the section view ───────────────────────────────────────────
    label_x = hatch_ox - 5
    label_y = hatch_oy + hatch_ph / 2 + 5
    add_section_view_label(msp, (label_x, label_y), label)


def _match_tolerance(meta: dict, measured_value: float,
                     name_hints: List[str]) -> Optional[str]:
    """Try to match a measured dimension to a tolerance entry.

    Returns the tolerance label string if matched, else None.
    """
    tols = meta.get("dim_tolerances", [])
    if not tols:
        return None
    for t in tols:
        name = t.get("name", "")
        # Check if any hint keyword is in the param name
        if not any(h in name.upper() for h in name_hints):
            continue
        # Check if nominal value is close to measured value
        nominal_str = t.get("nominal", "")
        import re as _re
        m = _re.search(r"(\d+\.?\d*)", nominal_str)
        if m:
            nominal = float(m.group(1))
            if abs(nominal - measured_value) < 0.5:  # within 0.5mm
                return t.get("label", "") or nominal_str
    return None
