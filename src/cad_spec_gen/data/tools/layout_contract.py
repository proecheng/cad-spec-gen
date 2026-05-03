from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.contract_io import stable_json_hash, write_json_atomic


LAYOUT_CONTRACT_SCHEMA_VERSION = 1


def build_layout_contract(
    product_graph: dict[str, Any],
    *,
    generated_files: list[str | Path],
    manual_overrides: dict[str, Any] | list[dict[str, Any]] | None = None,
    force_layout: bool = False,
) -> dict[str, Any]:
    """Build LAYOUT_CONTRACT.json from explicit product instances and overrides."""
    product_instances = _product_instance_ids(product_graph)
    normalized_overrides = normalize_manual_overrides(manual_overrides)
    override_instance_ids = [item["instance_id"] for item in normalized_overrides]
    product_instance_set = set(product_instances)
    override_instance_set = set(override_instance_ids)
    unlaid_out_instances = [
        instance_id
        for instance_id in product_instances
        if instance_id not in override_instance_set
    ]
    orphan_overrides = [
        instance_id
        for instance_id in override_instance_ids
        if instance_id not in product_instance_set
    ]
    blocking_reasons = []
    warnings = []
    if orphan_overrides:
        blocking_reasons.append({
            "code": "orphan_layout_overrides",
            "instance_ids": orphan_overrides,
            "message": "Manual layout references instances that are not present in PRODUCT_GRAPH.json.",
        })
    if unlaid_out_instances:
        warnings.append({
            "code": "unlaid_out_instances",
            "instance_ids": unlaid_out_instances,
            "message": "PRODUCT_GRAPH.json contains instances without manual layout overrides.",
        })
    status = "blocked" if blocking_reasons else ("warning" if warnings else "ok")

    return {
        "schema_version": LAYOUT_CONTRACT_SCHEMA_VERSION,
        "contract_name": "LAYOUT_CONTRACT",
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": product_graph.get("run_id", ""),
        "subsystem": product_graph.get("subsystem", ""),
        "product_graph_hash": stable_json_hash(product_graph),
        "generated_files": [Path(path).as_posix() for path in generated_files],
        "ownership": {
            "generated": [Path(path).as_posix() for path in generated_files],
            "manual": ["assembly_layout.py"],
            "stable_entry": "assembly.py",
        },
        "manual_layout": {
            "path": "assembly_layout.py",
            "force_layout": bool(force_layout),
            "preserved": False,
            "layout_rebuilt": bool(force_layout),
        },
        "product_instances": product_instances,
        "instance_mapping": normalized_overrides,
        "unlaid_out_instances": unlaid_out_instances,
        "orphan_overrides": orphan_overrides,
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
    }


def normalize_manual_overrides(
    manual_overrides: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    if not manual_overrides:
        return []

    if isinstance(manual_overrides, dict):
        rows = [
            _manual_override_row(assembly_name, value)
            for assembly_name, value in manual_overrides.items()
        ]
    elif isinstance(manual_overrides, list):
        rows = [_manual_override_row_from_mapping(item) for item in manual_overrides]
    else:
        raise TypeError("manual_overrides must be a dict or list of objects")

    seen_assembly_names: set[str] = set()
    seen_instance_ids: set[str] = set()
    normalized = []
    for row in rows:
        assembly_name = row["assembly_name"]
        instance_id = row["instance_id"]
        if assembly_name in seen_assembly_names:
            raise ValueError(f"duplicate manual layout assembly_name: {assembly_name}")
        if instance_id in seen_instance_ids:
            raise ValueError(f"duplicate manual layout instance_id: {instance_id}")
        seen_assembly_names.add(assembly_name)
        seen_instance_ids.add(instance_id)
        normalized.append({
            "assembly_name": assembly_name,
            "instance_id": instance_id,
            "owner": row.get("owner", "manual"),
        })
    return normalized


def should_preserve_manual_layout(
    layout_path: str | Path,
    *,
    force_layout: bool = False,
) -> bool:
    return Path(layout_path).is_file() and not force_layout


def manual_overrides_from_layout_file(layout_path: str | Path) -> list[dict[str, str]]:
    path = Path(layout_path)
    if not path.is_file():
        return []
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "MANUAL_LAYOUT_OVERRIDES"
                   for target in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(
                f"MANUAL_LAYOUT_OVERRIDES in {path} must be a literal dict/list"
            ) from exc
        return normalize_manual_overrides(value)
    return []


def write_layout_contract(path: str | Path, contract: dict[str, Any]) -> Path:
    return write_json_atomic(path, contract)


def _product_instance_ids(product_graph: dict[str, Any]) -> list[str]:
    instances = product_graph.get("instances", [])
    if not isinstance(instances, list):
        raise ValueError("PRODUCT_GRAPH instances must be a list")

    result = []
    seen: set[str] = set()
    for item in instances:
        if not isinstance(item, dict):
            raise ValueError("PRODUCT_GRAPH instance must be an object")
        if item.get("render_policy") == "excluded":
            continue
        instance_id = str(item.get("instance_id") or "")
        if not instance_id:
            continue
        if instance_id in seen:
            raise ValueError(f"duplicate PRODUCT_GRAPH instance_id: {instance_id}")
        seen.add(instance_id)
        result.append(instance_id)
    return result


def _manual_override_row(assembly_name: str, value: Any) -> dict[str, str]:
    if isinstance(value, str):
        instance_id = value
    elif isinstance(value, dict):
        instance_id = str(value.get("instance_id") or "")
    else:
        raise TypeError(f"manual layout override for {assembly_name} must be str or object")

    row = {
        "assembly_name": str(assembly_name),
        "instance_id": instance_id,
        "owner": "manual",
    }
    return _validate_manual_override_row(row)


def _manual_override_row_from_mapping(item: dict[str, Any]) -> dict[str, str]:
    if not isinstance(item, dict):
        raise TypeError("manual override item must be an object")
    row = {
        "assembly_name": str(item.get("assembly_name") or ""),
        "instance_id": str(item.get("instance_id") or ""),
        "owner": str(item.get("owner") or "manual"),
    }
    return _validate_manual_override_row(row)


def _validate_manual_override_row(row: dict[str, str]) -> dict[str, str]:
    if not row["assembly_name"]:
        raise ValueError("manual layout override missing assembly_name")
    if not row["instance_id"]:
        raise ValueError("manual layout override missing instance_id")
    if row.get("owner") != "manual":
        raise ValueError("manual layout override owner must be manual")
    return row
