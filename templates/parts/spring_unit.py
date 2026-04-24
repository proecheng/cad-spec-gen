"""templates/parts/spring_unit.py — 弹簧机构路由描述符（Track C）。"""
from __future__ import annotations

MATCH_KEYWORDS: list[str] = [
    "spring", "spring mechanism", "spring unit",
    "弹簧", "弹簧机构", "压簧", "拉簧", "扭簧",
]
MATCH_PRIORITY: int = 10
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {"od": 20.0, "free_length": 50.0}


def make(params: dict):  # pragma: no cover
    raise NotImplementedError("Use codegen/part_templates/spring_mechanism.py make_spring_mechanism()")
