"""templates/parts/cylindrical_sleeve.py — 套筒路由描述符（Track C）。"""
from __future__ import annotations

MATCH_KEYWORDS: list[str] = [
    "sleeve", "cylindrical sleeve", "bushing",
    "套筒", "套管", "衬套", "轴套",
]
MATCH_PRIORITY: int = 10
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {"od": 40.0, "length": 60.0}


def make(params: dict):  # pragma: no cover
    raise NotImplementedError("Use codegen/part_templates/sleeve.py make_sleeve()")
