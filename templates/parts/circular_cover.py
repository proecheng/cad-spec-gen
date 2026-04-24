"""templates/parts/circular_cover.py — 圆形端盖路由描述符（Track C）。"""
from __future__ import annotations

MATCH_KEYWORDS: list[str] = [
    "cover", "end cap", "circular cover",
    "盖", "端盖", "封盖", "盖板",
]
MATCH_PRIORITY: int = 10
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {"od": 60.0, "thickness": 8.0}


def make(params: dict):  # pragma: no cover
    raise NotImplementedError("Use codegen/part_templates/cover.py make_cover()")
