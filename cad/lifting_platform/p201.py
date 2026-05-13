"""右支撑条 (SLP-201)

Hand-completed 2026-05-13 (CP-1 Task 5c, quality overhaul) —
50×8×280 mm 竖直立柱，几何与 SLP-200 完全一致（镜像在 assembly_layout 里做）。

Envelope: 50.0 x 8.0 x 280.0 mm  (CP-1 Task 5c hand-completed 2026-05-13)
Doc:  CAD_SPEC.md §6.2 step 1-3 + draw_support_bar.py 注释；params.py::SUP_BAR_LEN=280
"""

from __future__ import annotations

from p200 import make_p200


def make_p201():
    """右支撑条复用左支撑条几何；镜像由 assembly_layout 的 X=+80 平移完成。"""
    return make_p200()


# Backward-compatible alias
p201 = make_p201
