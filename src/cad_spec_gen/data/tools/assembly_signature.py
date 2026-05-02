from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.contract_io import file_sha256, load_json_required, stable_json_hash, write_json_atomic
from tools.path_policy import assert_within_project, project_relative


def build_assembly_signature(
    project_root: str | Path,
    product_graph: dict[str, Any] | str | Path,
    bboxes: dict[str, tuple | list],
    transforms: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    graph, graph_source = _load_product_graph(product_graph, root)
    transforms = transforms or {}
    assembly_part_nos = _assembly_part_nos(graph)
    graph_instances, unique_graph_instances, duplicate_ids = _graph_instances_for_signature(graph)
    runtime_graph_instances = [
        instance for instance in graph_instances
        if not _is_assembly_instance(instance, assembly_part_nos)
    ]
    runtime_instances = [
        instance for instance in unique_graph_instances
        if not _is_assembly_instance(instance, assembly_part_nos)
    ]
    assembly_instances = [
        instance for instance in graph_instances
        if _is_assembly_instance(instance, assembly_part_nos)
    ]
    required_instances = [
        instance for instance in runtime_graph_instances
        if instance.get("required", True) is not False
    ]
    graph_by_id = {str(instance["instance_id"]): instance for instance in runtime_instances}
    required_ids = {str(instance["instance_id"]) for instance in required_instances}

    signature_instances = []
    matched_required_ids = set()
    blocking_reasons = [
        {
            "code": "duplicate_instance_id",
            "instance_id": instance_id,
            "count": count,
            "message": "PRODUCT_GRAPH contains duplicate instance_id values.",
        }
        for instance_id, count in duplicate_ids
    ]

    for object_name in sorted(bboxes):
        bbox = _float_list(bboxes[object_name])
        instance = graph_by_id.get(object_name)
        if instance is None:
            blocking_reasons.append({
                "code": "unmapped_assembly_object",
                "object_name": object_name,
                "message": "Assembly object name does not map to PRODUCT_GRAPH instance_id.",
            })
            continue
        instance_id = str(instance["instance_id"])
        if instance_id in required_ids:
            matched_required_ids.add(instance_id)
        signature_instances.append({
            "instance_id": instance_id,
            "part_no": instance.get("part_no", ""),
            "object_name": object_name,
            "visual_priority": instance.get("visual_priority", "normal"),
            "render_policy": instance.get("render_policy", "required"),
            "bbox_mm": bbox,
            "center_mm": _bbox_center(bbox),
            "size_mm": _bbox_size(bbox),
            "transform": _normalize_transform(transforms.get(object_name)),
        })

    missing_ids = sorted(required_ids - matched_required_ids)
    for missing_id in missing_ids:
        blocking_reasons.append({
            "code": "missing_required_instance",
            "instance_id": missing_id,
            "part_no": graph_by_id.get(missing_id, {}).get("part_no", ""),
            "message": "Required PRODUCT_GRAPH instance is absent from runtime assembly.",
        })

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": "runtime",
        "run_id": graph.get("run_id"),
        "subsystem": graph.get("subsystem"),
        "path_context_hash": graph.get("path_context_hash"),
        "product_graph_hash": stable_json_hash(graph),
        "source_paths": graph_source["source_paths"],
        "source_hashes": graph_source["source_hashes"],
        "coverage": {
            "required_total": len(required_instances),
            "matched_total": len(matched_required_ids),
            "unmatched_object_total": len([
                name for name in bboxes
                if name not in graph_by_id
            ]),
            "missing_instance_total": len(missing_ids),
            "assembly_instance_total": len(assembly_instances),
            "duplicate_instance_total": len(duplicate_ids),
        },
        "instances": signature_instances,
        "blocking_reasons": blocking_reasons,
    }


def write_assembly_signature(
    project_root: str | Path,
    product_graph: dict[str, Any] | str | Path,
    bboxes: dict[str, tuple | list],
    output: str | Path,
    transforms: dict[str, dict[str, Any]] | None = None,
) -> Path:
    root = Path(project_root).resolve()
    output_path = Path(output)
    output_path = output_path if output_path.is_absolute() else root / output_path
    output_path = output_path.resolve()
    assert_within_project(output_path, root, "assembly signature output")
    signature = build_assembly_signature(
        root,
        product_graph,
        bboxes,
        transforms=transforms,
    )
    return write_json_atomic(output_path, signature)


def build_static_preflight_signature(
    project_root: str | Path,
    product_graph: dict[str, Any] | str | Path,
    *,
    reason: str,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    graph, graph_source = _load_product_graph(product_graph, root)
    assembly_part_nos = _assembly_part_nos(graph)
    graph_instances, _, duplicate_ids = _graph_instances_for_signature(graph)
    runtime_instances = [
        instance for instance in graph_instances
        if not _is_assembly_instance(instance, assembly_part_nos)
        and instance.get("required", True) is not False
    ]
    assembly_instances = [
        instance for instance in graph_instances
        if _is_assembly_instance(instance, assembly_part_nos)
    ]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": "static_preflight",
        "run_id": graph.get("run_id"),
        "subsystem": graph.get("subsystem"),
        "path_context_hash": graph.get("path_context_hash"),
        "product_graph_hash": stable_json_hash(graph),
        "source_paths": graph_source["source_paths"],
        "source_hashes": graph_source["source_hashes"],
        "coverage": {
            "required_total": len(runtime_instances),
            "matched_total": 0,
            "unmatched_object_total": 0,
            "missing_instance_total": 0,
            "assembly_instance_total": len(assembly_instances),
            "duplicate_instance_total": len(duplicate_ids),
        },
        "instances": [],
        "blocking_reasons": [{
            "code": "static_preflight_only",
            "message": "Runtime assembly signature is required for photo3d gate.",
            "reason": reason,
        }],
    }


def signature_blocks_photo_gate(signature: dict[str, Any]) -> list[dict[str, Any]]:
    if signature.get("source_mode") != "runtime":
        return list(signature.get("blocking_reasons") or [])
    return list(signature.get("blocking_reasons") or [])


def _load_product_graph(
    product_graph: dict[str, Any] | str | Path,
    project_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    if isinstance(product_graph, dict):
        return dict(product_graph), {"source_paths": {}, "source_hashes": {}}
    graph_path = Path(product_graph)
    resolved = graph_path if graph_path.is_absolute() else project_root / graph_path
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, "product graph")
    return load_json_required(resolved, "product graph"), {
        "source_paths": {
            "PRODUCT_GRAPH.json": project_relative(resolved, project_root),
        },
        "source_hashes": {
            "PRODUCT_GRAPH.json": file_sha256(resolved),
        },
    }


def _graph_instances_for_signature(
    graph: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[str, int]]]:
    instances = [
        instance for instance in graph.get("instances", [])
        if isinstance(instance, dict)
        and instance.get("instance_id")
        and instance.get("render_policy") != "excluded"
    ]
    counts: dict[str, int] = {}
    for instance in instances:
        instance_id = str(instance["instance_id"])
        counts[instance_id] = counts.get(instance_id, 0) + 1
    duplicates = sorted((instance_id, count) for instance_id, count in counts.items() if count > 1)
    unique_instances: list[dict[str, Any]] = []
    seen = set()
    for instance in instances:
        instance_id = str(instance["instance_id"])
        if instance_id in seen:
            continue
        seen.add(instance_id)
        unique_instances.append(instance)
    return instances, unique_instances, duplicates


def _assembly_part_nos(graph: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for part in graph.get("parts", []):
        if not isinstance(part, dict):
            continue
        part_no = part.get("part_no")
        if part_no and _part_row_is_assembly(part):
            result.add(str(part_no))
        parent = part.get("parent_part_no")
        if parent:
            result.add(str(parent))
    for instance in graph.get("instances", []):
        if not isinstance(instance, dict):
            continue
        parent_instance_id = instance.get("parent_instance_id")
        if parent_instance_id:
            result.add(str(parent_instance_id).split("#", 1)[0])
    return result


def _part_row_is_assembly(part: dict[str, Any]) -> bool:
    for key in ("node_type", "part_type", "instance_type", "role"):
        value = str(part.get(key) or "").lower()
        if value in {"assembly", "subassembly", "sub_assembly"}:
            return True
    make_buy = str(part.get("make_buy") or "").strip().lower()
    return make_buy in {"总成", "assembly", "subassembly", "sub_assembly"}


def _is_assembly_instance(instance: dict[str, Any], assembly_part_nos: set[str]) -> bool:
    node_type = str(instance.get("node_type") or instance.get("instance_type") or "").lower()
    if node_type in {"assembly", "subassembly", "sub_assembly"}:
        return True
    role = str(instance.get("role") or "").lower()
    if role in {"assembly", "subassembly", "sub_assembly"}:
        return True
    return str(instance.get("part_no") or "") in assembly_part_nos


def _float_list(values: tuple | list) -> list[float]:
    result = [float(value) for value in values]
    if len(result) != 6:
        raise ValueError(f"bbox must contain 6 numeric values, got {values!r}")
    return result


def _bbox_center(bbox: list[float]) -> list[float]:
    return [
        (bbox[0] + bbox[3]) / 2,
        (bbox[1] + bbox[4]) / 2,
        (bbox[2] + bbox[5]) / 2,
    ]


def _bbox_size(bbox: list[float]) -> list[float]:
    return [
        bbox[3] - bbox[0],
        bbox[4] - bbox[1],
        bbox[5] - bbox[2],
    ]


def _normalize_transform(transform: dict[str, Any] | None) -> dict[str, Any]:
    if not transform:
        return {
            "translation_mm": [0.0, 0.0, 0.0],
            "rotation_deg": [0.0, 0.0, 0.0],
            "matrix": None,
        }
    return {
        "translation_mm": _xyz(transform.get("translation_mm")),
        "rotation_deg": _xyz(transform.get("rotation_deg")),
        "matrix": transform.get("matrix"),
    }


def _xyz(values: Any) -> list[float]:
    if values is None:
        return [0.0, 0.0, 0.0]
    result = [float(value) for value in values]
    if len(result) != 3:
        return [0.0, 0.0, 0.0]
    return result
