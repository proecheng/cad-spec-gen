"""templates/parts/cantilever_arm.py — 悬臂/连杆路由描述符（Track C）。

几何由 codegen/part_templates/arm.py make_arm() 实现；
此文件仅为 route() 提供关键词发现入口。
"""
from __future__ import annotations

MATCH_KEYWORDS: list[str] = [
    "cantilever", "arm", "connecting rod",
    "悬臂", "臂", "连杆", "摇臂",
]
MATCH_PRIORITY: int = 10
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {"length": 100.0, "width": 20.0, "thickness": 5.0}


def make(params: dict):  # pragma: no cover
    raise NotImplementedError("Use codegen/part_templates/arm.py make_arm()")
