"""L3 富化 Envelope：为无模板或 L2 失败的自制件生成比裸 box 更真实的几何。

所有比例为命名常量，tpl_type 复用 _BUILTIN_KEYWORDS 键名。
"""
from __future__ import annotations

import math

# ── 比例常量 ──────────────────────────────────────────────────────────────────
_ENRICH_FLANGE_ID_RATIO   = 0.50   # 中心孔 id = od × 此值
_ENRICH_FLANGE_PCD_RATIO  = 0.75   # 螺栓孔 PCD = od × 此值
_ENRICH_HOUSING_SLOT_W    = 0.30   # 侧面开口宽 = w × 此值
_ENRICH_HOUSING_SLOT_H    = 0.40   # 侧面开口高 = h × 此值
_ENRICH_DEFAULT_FILLET    = 3.0    # mm，通用圆角
_ENRICH_DEFAULT_CBORE_D   = 10.0   # mm，默认沉孔直径
_ENRICH_DEFAULT_CBORE_H   = 5.0    # mm，默认沉孔深度
_ENRICH_BOLT_COUNT        = 6      # 默认螺栓孔数


def _make_enriched_envelope(
    tpl_type: str,
    w: float,
    d: float,
    h: float,
) -> "cq.Workplane":
    """生成比裸 envelope 更真实的近似几何。

    tpl_type 对应 _BUILTIN_KEYWORDS 键名（flange/housing/bracket/plate/arm/cover/sleeve/spring_mechanism）。
    所有操作包裹在 try/except，OCCT 失败时回退到带圆角的 box。
    """
    import cadquery as cq

    od = max(w, d)

    try:
        if tpl_type == "flange":
            return _enrich_flange(cq, od, h)
        elif tpl_type == "housing":
            return _enrich_housing(cq, w, d, h)
        elif tpl_type in ("bracket", "plate", "arm"):
            return _enrich_plate_like(cq, w, d, h)
        else:
            return _enrich_default(cq, w, d, h)
    except Exception:
        try:
            return _enrich_default(cq, w, d, h)
        except Exception:
            return cq.Workplane("XY").box(w, d, h)


def _enrich_flange(cq, od: float, h: float):
    id_ = round(od * _ENRICH_FLANGE_ID_RATIO, 2)
    pcd = round(od * _ENRICH_FLANGE_PCD_RATIO, 2)
    bolt_r = round(pcd * 0.04, 2)
    body = (
        cq.Workplane("XY")
        .circle(od / 2).extrude(h)
        .cut(cq.Workplane("XY").circle(id_ / 2).extrude(h))
    )
    for i in range(_ENRICH_BOLT_COUNT):
        ang = math.radians(360 / _ENRICH_BOLT_COUNT * i)
        bx = round(pcd / 2 * math.cos(ang), 4)
        by = round(pcd / 2 * math.sin(ang), 4)
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(bx, by, 0))
            .circle(bolt_r).extrude(h)
        )
    try:
        body = body.edges("|Z").chamfer(min(_ENRICH_DEFAULT_FILLET, od * 0.02))
    except Exception:
        pass
    return body


def _enrich_housing(cq, w: float, d: float, h: float):
    wall = min(w, d) * 0.12
    body = (
        cq.Workplane("XY").box(w, d, h)
        .cut(cq.Workplane("XY")
             .box(w - wall * 2, d - wall * 2, h - wall)
             .translate((0, 0, wall / 2)))
    )
    slot_w = round(w * _ENRICH_HOUSING_SLOT_W, 2)
    slot_h = round(h * _ENRICH_HOUSING_SLOT_H, 2)
    body = body.cut(
        cq.Workplane("XZ")
        .transformed(offset=cq.Vector(0, d / 2, 0))
        .rect(slot_w, slot_h).extrude(wall + 1)
    )
    try:
        body = body.edges("|Z").fillet(_ENRICH_DEFAULT_FILLET)
    except Exception:
        pass
    return body


def _enrich_plate_like(cq, w: float, d: float, h: float):
    body = cq.Workplane("XY").box(w, d, h)
    hole_r = min(w, d) * 0.04
    for sx in (-1, 1):
        for sy in (-1, 1):
            hx = sx * w * 0.35
            hy = sy * d * 0.35
            body = body.cut(
                cq.Workplane("XY")
                .transformed(offset=cq.Vector(hx, hy, 0))
                .circle(hole_r).extrude(h)
            )
    try:
        body = body.edges("|Z").fillet(_ENRICH_DEFAULT_FILLET)
    except Exception:
        pass
    return body


def _enrich_default(cq, w: float, d: float, h: float):
    body = cq.Workplane("XY").box(w, d, h)
    cbore_r = min(_ENRICH_DEFAULT_CBORE_D / 2, min(w, d) * 0.15)
    cbore_r = max(cbore_r, 0.5)  # OCCT 最小精度保护
    cbore_h = min(_ENRICH_DEFAULT_CBORE_H, h * 0.4)
    body = body.cut(
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, h / 2 - cbore_h))
        .circle(cbore_r).extrude(cbore_h + 1)
    )
    try:
        body = body.edges("|Z").fillet(_ENRICH_DEFAULT_FILLET)
    except Exception:
        pass
    return body
