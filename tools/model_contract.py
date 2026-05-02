from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.contract_io import file_sha256, load_json_required, stable_json_hash, write_json_atomic
from tools.path_policy import assert_within_project, project_relative


QUALITY_GRADES = ("A", "B", "C", "D", "E")
BLOCKING_QUALITIES = {"D", "E"}
BLOCKING_PRIORITIES = {"hero", "high"}


def build_model_contract(
    project_root: str | Path,
    product_graph: dict[str, Any] | str | Path,
    resolver_decisions: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    path_context_hash: str | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    graph, graph_source = _load_product_graph(product_graph, root)
    decisions_by_part_no = _index_resolver_decisions(resolver_decisions or [])

    required_parts = [
        part for part in graph.get("parts", [])
        if part.get("part_no") and part.get("render_policy") != "excluded"
    ]
    contract_decisions = []
    missing_total = 0
    quality_counts = {grade: 0 for grade in QUALITY_GRADES}

    for part in required_parts:
        part_no = str(part["part_no"])
        raw_decision = decisions_by_part_no.get(part_no)
        if raw_decision is None:
            missing_total += 1
            decision = _missing_decision(part)
        else:
            decision = _normalize_decision(root, part, raw_decision)
            if decision["geometry_source"] == "MISSING":
                missing_total += 1
        quality = decision.get("geometry_quality") or "E"
        if quality not in quality_counts:
            quality = "E"
            decision["geometry_quality"] = "E"
        quality_counts[quality] += 1
        contract_decisions.append(decision)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id or graph.get("run_id"),
        "subsystem": graph.get("subsystem"),
        "path_context_hash": path_context_hash or graph.get("path_context_hash"),
        "product_graph_hash": stable_json_hash(graph),
        "source_paths": graph_source["source_paths"],
        "source_hashes": graph_source["source_hashes"],
        "coverage": {
            "required_total": len(required_parts),
            "decided_total": len(contract_decisions),
            "missing_total": missing_total,
        },
        "quality_counts": quality_counts,
        "decisions": contract_decisions,
    }


def write_model_contract(
    project_root: str | Path,
    product_graph: dict[str, Any] | str | Path,
    resolver_decisions: list[dict[str, Any]] | None = None,
    output: str | Path | None = None,
    *,
    run_id: str | None = None,
    path_context_hash: str | None = None,
) -> Path:
    root = Path(project_root).resolve()
    contract = build_model_contract(
        root,
        product_graph,
        resolver_decisions=resolver_decisions,
        run_id=run_id,
        path_context_hash=path_context_hash,
    )
    if output is None:
        output_path = root / ".cad-spec-gen" / "MODEL_CONTRACT.json"
    else:
        requested = Path(output)
        output_path = requested if requested.is_absolute() else root / requested
        output_path = output_path.resolve()
        assert_within_project(output_path, root, "model contract output")
    return write_json_atomic(output_path, contract)


def blocked_required_decisions(contract: dict[str, Any]) -> list[dict[str, Any]]:
    blocked = []
    for decision in contract.get("decisions", []):
        if (
            decision.get("visual_priority") in BLOCKING_PRIORITIES
            and decision.get("geometry_quality") in BLOCKING_QUALITIES
        ):
            blocked.append(decision)
    return blocked


def model_contract_blocks_photo_gate(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return blocked_required_decisions(contract)


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


def _missing_decision(part: dict[str, Any]) -> dict[str, Any]:
    return _base_decision(
        part,
        {
            "adapter": "(none)",
            "geometry_source": "MISSING",
            "geometry_quality": "E",
            "validated": False,
            "requires_model_review": True,
            "review_reasons": ["missing_geometry_decision"],
        },
    )


def _normalize_decision(
    project_root: Path,
    part: dict[str, Any],
    raw_decision: dict[str, Any],
) -> dict[str, Any]:
    decision = _base_decision(part, raw_decision)
    review_reasons = list(decision["review_reasons"])
    path_info = _resolve_source_path(project_root, raw_decision)
    if path_info.get("outside_project") or path_info.get("cache_uri"):
        reason = (
            "cache_uri_requires_project_import"
            if path_info.get("cache_uri")
            else "outside_project_step"
        )
        review_reasons.append(reason)
        decision.update({
            "geometry_quality": "E",
            "validated": False,
            "requires_model_review": True,
            "source_path_rel_project": None,
            "source_path_abs_resolved": None,
        })
    else:
        decision.update({
            "source_path_rel_project": path_info.get("rel_project"),
            "source_path_abs_resolved": path_info.get("abs_resolved"),
        })
    if decision["geometry_quality"] == "E" and "e_quality_geometry" not in review_reasons:
        review_reasons.append("e_quality_geometry")
    if decision["geometry_quality"] == "D" and "d_quality_geometry" not in review_reasons:
        review_reasons.append("d_quality_geometry")
    decision["review_reasons"] = review_reasons
    return decision


def _index_resolver_decisions(decisions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        part_no = decision.get("part_no")
        if not part_no:
            continue
        key = str(part_no)
        if key in result:
            raise ValueError(f"Duplicate geometry decision for part_no: {key}")
        result[key] = dict(decision)
    return result


def _base_decision(part: dict[str, Any], raw_decision: dict[str, Any]) -> dict[str, Any]:
    quality = raw_decision.get("geometry_quality") or "E"
    if quality not in QUALITY_GRADES:
        quality = "E"
    metadata = raw_decision.get("metadata") or {}
    review_reasons = list(raw_decision.get("review_reasons") or [])
    warnings = raw_decision.get("warnings") or []
    for warning in warnings:
        if isinstance(warning, str):
            review_reasons.append(warning)
    bbox = (
        raw_decision.get("bbox_mm")
        or raw_decision.get("real_dims")
        or metadata.get("bbox_mm")
        or part.get("bbox_expected_mm")
    )
    return {
        "part_no": part["part_no"],
        "name_cn": part.get("name_cn", raw_decision.get("name_cn", "")),
        "visual_priority": part.get("visual_priority", "normal"),
        "render_policy": part.get("render_policy", "required"),
        "adapter": raw_decision.get("adapter") or "(none)",
        "geometry_source": raw_decision.get("geometry_source") or "MISSING",
        "geometry_quality": quality,
        "validated": bool(raw_decision.get("validated", False)),
        "requires_model_review": bool(
            raw_decision.get("requires_model_review", quality in BLOCKING_QUALITIES)
        ),
        "review_reasons": review_reasons,
        "bbox_mm": _float_list_or_none(bbox),
        "origin_policy": raw_decision.get("origin_policy")
        or metadata.get("origin_policy")
        or metadata.get("normalize_origin")
        or "as_source",
        "coordinate_frame": raw_decision.get("coordinate_frame")
        or metadata.get("coordinate_frame")
        or "cadquery_default",
        "scale_policy": raw_decision.get("scale_policy")
        or metadata.get("scale_policy")
        or "millimeter_1_to_1",
        "source_path_rel_project": None,
        "source_path_abs_resolved": None,
        "source_hash": (
            raw_decision.get("source_hash")
            or raw_decision.get("hash")
            or metadata.get("source_hash")
        ),
        "dimensional_confidence": _normalize_confidence(
            raw_decision.get("dimensional_confidence")
            or metadata.get("dimensional_confidence"),
            quality,
        ),
        "visual_confidence": _normalize_confidence(
            raw_decision.get("visual_confidence")
            or metadata.get("visual_confidence"),
            quality,
        ),
    }


def _resolve_source_path(project_root: Path, raw_decision: dict[str, Any]) -> dict[str, Any]:
    source_path = raw_decision.get("source_path") or raw_decision.get("step_path")
    if not source_path:
        return {}
    if str(source_path).startswith("cache://"):
        return {"cache_uri": True}

    path = Path(str(source_path))
    resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
    try:
        rel_project = project_relative(resolved, project_root)
    except ValueError:
        return {"outside_project": True}
    return {
        "rel_project": rel_project,
        "abs_resolved": str(resolved),
    }


def _float_list_or_none(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _normalize_confidence(value: Any, quality: str) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"high", "medium", "low", "none"}:
            return normalized
    if isinstance(value, (int, float)):
        if value >= 0.8:
            return "high"
        if value >= 0.5:
            return "medium"
        if value > 0:
            return "low"
        return "none"
    return _default_confidence(quality)


def _default_confidence(quality: str) -> str:
    return {
        "A": "high",
        "B": "high",
        "C": "medium",
        "D": "low",
        "E": "none",
    }.get(quality, "none")
