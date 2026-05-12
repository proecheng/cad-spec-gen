"""render_manifest 逐视角可见实例证据（方案 B — bbox-presence）。

给 render_manifest.json 的每个 view 提供 `visible_instance_ids` = assembly_signature
里「在 GLB 里有有效 bbox」的 instance_id 集（所有视角相同）。配合 render_visual_regression
的并集检查，把「required 件不在 GLB」（= 真的少件）从 warning 升成 blocked；required 件
若在 GLB 必有 bbox → 在集里 → 不 block（无 false-positive）。

逐视角差异化（真 frustum / exploded-aware）是未来增强——只改本模块实现、不改接口。
详见 spec：docs/superpowers/specs/2026-05-12-render-manifest-view-instance-evidence-design.md
"""
from __future__ import annotations

import math
from typing import Any


def _has_valid_bbox(instance: dict[str, Any]) -> bool:
    """instance["bbox_mm"] 是恰 6 个有限数的 list。

    纯防御——assembly_signature.instances[] 里每项按构造都有 GLB 实测 bbox（且
    upstream `_float_list` 保证恰 6 个）；几乎永远为真。**故意不查退化**（[0,0,0,0,0,0]
    仍算有效）：宁可漏不可误——一个 required 件只要在 GLB 里有个 bbox 就算「在」、
    绝不因 bbox 怪异而 false-block。
    """
    bbox = instance.get("bbox_mm")
    return (
        isinstance(bbox, list)
        and len(bbox) == 6
        and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in bbox
        )
    )


def compute_view_visible_instances(
    assembly_signature: dict[str, Any],
    view_ids: list[str],
) -> dict[str, list[str]] | None:
    """每个 view → 「在 GLB 里有有效 bbox 的 instance_id」排序集（所有视角相同）。

    返回 None ⟺ assembly_signature 不是含 list 型 `instances` 的 dict（→ 无证据可算，
    调用方据此不写 visible_instance_ids，manifest 保持「无证据」状态 → 契约层 warn）。
    view_ids 为空 → 返回 {}。
    """
    if not isinstance(assembly_signature, dict):
        return None
    instances = assembly_signature.get("instances")
    if not isinstance(instances, list):
        return None
    valid_ids = sorted({
        str(inst["instance_id"])
        for inst in instances
        if isinstance(inst, dict) and inst.get("instance_id") and _has_valid_bbox(inst)
    })
    return {view: list(valid_ids) for view in view_ids}
