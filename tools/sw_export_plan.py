"""Read-only SolidWorks Toolbox export planning."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bom_parser import classify_part
from parts_resolver import PartQuery, PartsResolver
from tools.model_context import ModelProjectContext


DEFAULT_TOOLBOX_CONFIG = "Default"


def build_sw_export_plan(
    bom_rows,
    registry,
    context: ModelProjectContext,
    adapter=None,
) -> dict:
    """Build a read-only plan for SolidWorks Toolbox STEP cache candidates."""
    registry = registry or {}
    if adapter is None:
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

        adapter = SwToolboxAdapter(config=registry.get("solidworks_toolbox", {}))

    resolver = PartsResolver(
        project_root=str(context.project_root),
        registry=registry,
    )
    available, unavailable_reason = _adapter_available(adapter)
    candidates = []

    for row in bom_rows or []:
        query = _query_from_bom_row(row, context)
        rules = resolver.matching_rules(query, adapter_name="sw_toolbox")
        if not rules:
            candidates.append(_base_candidate(query, action="no_candidate", warnings=[
                "no matching sw_toolbox registry rule",
            ]))
            continue

        for rule in rules:
            spec = dict(rule.get("spec", {}) or {})
            candidate = _base_candidate(
                query,
                action="unavailable" if not available else "no_candidate",
                rule=rule,
            )
            if not available:
                if unavailable_reason:
                    candidate["warnings"].append(unavailable_reason)
                candidates.append(candidate)
                continue

            try:
                match = adapter.find_sldprt(query, spec)
            except Exception as exc:
                candidate["warnings"].append(f"find_sldprt failed: {exc}")
                candidates.append(candidate)
                continue

            if match is None:
                candidates.append(candidate)
                continue

            part, score = match
            config_name = _part_config_name(part)
            step_path = _step_cache_path(part, registry, adapter, config_name)
            cache_state = "present" if step_path.exists() else "missing"
            action = "reuse_cache" if cache_state == "present" else "export"
            candidate.update({
                "action": action,
                "sldprt_path": str(getattr(part, "sldprt_path", "")),
                "sldprt_filename": getattr(part, "filename", ""),
                "standard": getattr(part, "standard", ""),
                "subcategory": getattr(part, "subcategory", ""),
                "match_score": score,
                "config_match": "matched",
                "config_name": config_name,
                "recommended_operation": action,
                "step_cache_path": str(step_path),
                "cache_state": cache_state,
            })
            candidates.append(candidate)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(context.project_root),
        "subsystem": context.subsystem,
        "candidates": candidates,
    }


def write_sw_export_plan(plan, context: ModelProjectContext) -> Path:
    """Atomically write sw_export_plan.json under the context metadata dir."""
    path = context.sw_export_plan_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
    return path


def _adapter_available(adapter) -> tuple[bool, str | None]:
    try:
        return adapter.is_available()
    except Exception as exc:
        return False, str(exc)


def _query_from_bom_row(row: dict[str, Any], context: ModelProjectContext) -> PartQuery:
    name_cn = row.get("name_cn", "") or row.get("name", "")
    material = row.get("material", "")
    category = row.get("category") or classify_part(name_cn, material)
    return PartQuery(
        part_no=row.get("part_no", "") or row.get("bom_id", ""),
        name_cn=name_cn,
        material=material,
        category=category,
        make_buy=row.get("make_buy", ""),
        project_root=str(context.project_root),
    )


def _base_candidate(
    query: PartQuery,
    *,
    action: str,
    rule: dict | None = None,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "part_no": query.part_no,
        "name_cn": query.name_cn,
        "material": query.material,
        "category": query.category,
        "make_buy": query.make_buy,
        "action": action,
        "adapter": "sw_toolbox",
        "config_match": "n/a",
        "config_name": "",
        "rule_adapter": (rule or {}).get("adapter", ""),
        "rule_match": dict((rule or {}).get("match", {}) or {}),
        "rule_spec": dict((rule or {}).get("spec", {}) or {}),
        "sldprt_path": "",
        "sldprt_filename": "",
        "standard": "",
        "subcategory": "",
        "match_score": None,
        "step_cache_path": "",
        "cache_state": "missing",
        "warnings": list(warnings or []),
    }


def _part_config_name(part) -> str:
    for attr in ("target_config", "config_name", "configuration"):
        value = getattr(part, attr, None)
        if value:
            return str(value)
    return DEFAULT_TOOLBOX_CONFIG


def _step_cache_path(part, registry: dict, adapter, config_name: str) -> Path:
    from adapters.solidworks import sw_toolbox_catalog

    config = getattr(adapter, "config", None) or registry.get("solidworks_toolbox", {})
    cache_root = sw_toolbox_catalog.get_toolbox_cache_root(config)
    stem = Path(getattr(part, "filename", "")).stem
    safe_config = re.sub(r"[^\w.\-]", "_", config_name)
    preferred_stem = f"{stem}_{safe_config}"
    preferred_path = (
        cache_root
        / getattr(part, "standard", "")
        / getattr(part, "subcategory", "")
        / f"{preferred_stem}.step"
    )
    if config_name == DEFAULT_TOOLBOX_CONFIG:
        legacy_path = preferred_path.with_name(f"{stem}.step")
        if legacy_path.exists() and not preferred_path.exists():
            return legacy_path
    return preferred_path
