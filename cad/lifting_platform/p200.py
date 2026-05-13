"""左支撑条 (SLP-200)

Hand-completed 2026-05-13 (CP-1 Task 5c, quality overhaul) —
50×8×280 mm 竖直立柱（局部 Z 即装配 Z）+ 顶/底两端各 2×M5 安装孔。
Source: CAD_SPEC.md §3 紧固件 + §6.2 装配层叠 step 2/8（连接 KFL001 + 上板）
Material: Al 6061-T6 阳极氧化
"""

from __future__ import annotations

import cadquery as cq
from params import SUP_BAR_W, SUP_BAR_T, SUP_BAR_LEN


def make_p200() -> cq.Workplane:
    """SLP-200 左支撑条 — 50(W)×8(T)×280(LEN) 竖直立柱。

    局部坐标系：X=宽、Y=厚（沿装配中心朝外）、Z=高（装配立刻沿 +Z 升起，
    无需 rotation；assembly_layout 只对它做平移到 X=-80）。
    Envelope: 50 × 8 × 280 mm
    """
    body = cq.Workplane("XY").box(
        SUP_BAR_W, SUP_BAR_T, SUP_BAR_LEN,
        centered=(True, True, False),
    )
    # 顶部 M5 安装孔 (连上板 KFL001 基板)：2×Φ5.5 at (±15, 0, top)
    for _dx in (-15.0, 15.0):
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(_dx, 0.0, SUP_BAR_LEN - 6.0))
            .circle(2.75).extrude(6.0)
        )
    # 底部 M5 安装孔 (连下板 KFL001 基板)：2×Φ5.5 at (±15, 0, bottom)
    for _dx in (-15.0, 15.0):
        body = body.cut(
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(_dx, 0.0, 0.0))
            .circle(2.75).extrude(6.0)
        )
    return body


def _orientation_spec():
    """竖直立柱：主轴 +Z，长宽比 ≈ 280/50 ≈ 5.6。"""
    return {
        "principal_axis": "z",
        "min_ratio": 5.0,
        "doc_ref": "CAD_SPEC.md §3/§6.2 (hand-completed 2026-05-13)",
    }


# Backward-compatible alias
p200 = make_p200
