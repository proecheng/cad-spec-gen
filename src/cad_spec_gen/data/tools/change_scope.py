from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.contract_io import file_sha256, load_json_required, stable_json_hash, write_json_atomic
from tools.path_policy import assert_within_project, project_relative


DEFAULT_TOLERANCES = {
    "bbox_size_abs_mm": 1.0,
    "bbox_size_rel": 0.03,
    "center_abs_mm": 1.0,
    "center_rel_of_assembly_diag": 0.01,
    "rotation_deg": 1.0,
}

NO_BASELINE_WARNING = {
    "code": "no_accepted_baseline",
    "message": "首轮运行没有已接受基准，只能建立候选基准，不能证明漂移稳定。",
}


def build_default_change_scope(
    *,
    run_id: str,
    subsystem: str,
    path_context_hash: str,
    baseline_run_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "subsystem": subsystem,
        "path_context_hash": path_context_hash,
        "baseline_run_id": baseline_run_id or "",
        "allowed_part_nos": [],
        "allowed_instance_ids": [],
        "allowed_change_types": ["material_refinement"],
        "tolerances": dict(DEFAULT_TOLERANCES),
    }


def load_change_scope(path: str | Path) -> dict[str, Any]:
    return load_json_required(path, "change scope")


def write_change_scope(
    project_root: str | Path,
    output: str | Path,
    scope: dict[str, Any],
) -> Path:
    root = Path(project_root).resolve()
    target = Path(output)
    target = target if target.is_absolute() else root / target
    target = target.resolve()
    assert_within_project(target, root, "change scope output")
    return write_json_atomic(target, scope)


def evaluate_change_scope(
    scope: dict[str, Any],
    *,
    current_signature: dict[str, Any],
    baseline_signature: dict[str, Any] | None = None,
    current_model_contract: dict[str, Any] | None = None,
    baseline_model_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings = []
    blocking_reasons = []
    drift_items = []
    baseline_status = "bound"
    observed_hashes = _observed_hashes(
        current_signature,
        baseline_signature,
        current_model_contract,
        baseline_model_contract,
    )

    if not baseline_signature:
        baseline_status = "candidate_only"
        warnings.append(dict(NO_BASELINE_WARNING))
        current_reasons = _current_binding_reasons(scope, current_signature, current_model_contract)
        if current_reasons:
            blocking_reasons.extend(current_reasons)
            return _report(
                scope,
                current_signature,
                status="blocked",
                baseline_status=baseline_status,
                warnings=warnings,
                blocking_reasons=blocking_reasons,
                drift_items=[],
                observed_hashes=observed_hashes,
            )
        return _report(
            scope,
            current_signature,
            status="warning",
            baseline_status=baseline_status,
            warnings=warnings,
            blocking_reasons=blocking_reasons,
            drift_items=drift_items,
            observed_hashes=observed_hashes,
        )

    current_reasons = _current_binding_reasons(scope, current_signature, current_model_contract)
    if current_reasons:
        blocking_reasons.extend(current_reasons)
        return _report(
            scope,
            current_signature,
            status="blocked",
            baseline_status="current_mismatch",
            warnings=warnings,
            blocking_reasons=blocking_reasons,
            drift_items=[],
            observed_hashes=observed_hashes,
        )

    binding_reasons = _baseline_binding_reasons(
        scope,
        baseline_signature,
        baseline_model_contract,
        observed_hashes,
    )
    if binding_reasons:
        blocking_reasons.extend(binding_reasons)
        return _report(
            scope,
            current_signature,
            status="blocked",
            baseline_status="mismatch",
            warnings=warnings,
            blocking_reasons=blocking_reasons,
            drift_items=[],
            observed_hashes=observed_hashes,
        )

    drift_items = _compare_signatures(scope, current_signature, baseline_signature)
    blocking_reasons.extend(_blocking_from_drift(drift_items))
    status = "blocked" if blocking_reasons else "pass"
    return _report(
        scope,
        current_signature,
        status=status,
        baseline_status=baseline_status,
        warnings=warnings,
        blocking_reasons=blocking_reasons,
        drift_items=drift_items,
        observed_hashes=observed_hashes,
    )


def evaluate_change_scope_from_files(
    project_root: str | Path,
    scope_path: str | Path,
    current_signature_path: str | Path,
    baseline_signature_path: str | Path | None = None,
    *,
    current_model_contract_path: str | Path | None = None,
    baseline_model_contract_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    scope = load_json_required(_project_path(root, scope_path, "change scope"), "change scope")
    current_signature = load_json_required(
        _project_path(root, current_signature_path, "current assembly signature"),
        "current assembly signature",
    )
    baseline_signature = None
    if baseline_signature_path:
        baseline_signature = load_json_required(
            _project_path(root, baseline_signature_path, "baseline assembly signature"),
            "baseline assembly signature",
        )
    current_model_contract = None
    if current_model_contract_path:
        current_model_contract = load_json_required(
            _project_path(root, current_model_contract_path, "current model contract"),
            "current model contract",
        )
    baseline_model_contract = None
    if baseline_model_contract_path:
        baseline_model_contract = load_json_required(
            _project_path(root, baseline_model_contract_path, "baseline model contract"),
            "baseline model contract",
        )
    report = evaluate_change_scope(
        scope,
        current_signature=current_signature,
        baseline_signature=baseline_signature,
        current_model_contract=current_model_contract,
        baseline_model_contract=baseline_model_contract,
    )
    report["source_paths"] = {
        "CHANGE_SCOPE.json": project_relative(_project_path(root, scope_path, "change scope"), root),
        "current_assembly_signature": project_relative(
            _project_path(root, current_signature_path, "current assembly signature"),
            root,
        ),
    }
    report["source_hashes"] = {
        "CHANGE_SCOPE.json": file_sha256(_project_path(root, scope_path, "change scope")),
        "current_assembly_signature": file_sha256(
            _project_path(root, current_signature_path, "current assembly signature")
        ),
    }
    return report


def _project_path(root: Path, path: str | Path, label: str) -> Path:
    target = Path(path)
    resolved = target if target.is_absolute() else root / target
    resolved = resolved.resolve()
    assert_within_project(resolved, root, label)
    return resolved


def _report(
    scope: dict[str, Any],
    current_signature: dict[str, Any],
    *,
    status: str,
    baseline_status: str,
    warnings: list[dict[str, Any]],
    blocking_reasons: list[dict[str, Any]],
    drift_items: list[dict[str, Any]],
    observed_hashes: dict[str, str | None],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": scope.get("run_id") or current_signature.get("run_id"),
        "subsystem": scope.get("subsystem") or current_signature.get("subsystem"),
        "path_context_hash": scope.get("path_context_hash") or current_signature.get("path_context_hash"),
        "status": status,
        "baseline_status": baseline_status,
        "allowed_part_nos": list(scope.get("allowed_part_nos") or []),
        "allowed_instance_ids": list(scope.get("allowed_instance_ids") or []),
        "allowed_change_types": list(scope.get("allowed_change_types") or []),
        "tolerances": _tolerances(scope),
        "observed_hashes": observed_hashes,
        "drift_items": drift_items,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def _observed_hashes(
    current_signature: dict[str, Any],
    baseline_signature: dict[str, Any] | None,
    current_model_contract: dict[str, Any] | None,
    baseline_model_contract: dict[str, Any] | None,
) -> dict[str, str | None]:
    return {
        "current_assembly_signature_hash": stable_json_hash(current_signature),
        "baseline_assembly_signature_hash": (
            stable_json_hash(baseline_signature) if baseline_signature is not None else None
        ),
        "current_model_contract_hash": (
            stable_json_hash(current_model_contract) if current_model_contract is not None else None
        ),
        "baseline_model_contract_hash": (
            stable_json_hash(baseline_model_contract) if baseline_model_contract is not None else None
        ),
    }


def _baseline_binding_reasons(
    scope: dict[str, Any],
    baseline_signature: dict[str, Any],
    baseline_model_contract: dict[str, Any] | None,
    observed_hashes: dict[str, str | None],
) -> list[dict[str, Any]]:
    reasons = []
    expected_run_id = scope.get("baseline_run_id")
    if expected_run_id and baseline_signature.get("run_id") != expected_run_id:
        reasons.append(_binding_reason(
            "baseline_run_id_mismatch",
            expected_run_id,
            baseline_signature.get("run_id"),
        ))

    expected_path_context = scope.get("baseline_path_context_hash")
    if expected_path_context and baseline_signature.get("path_context_hash") != expected_path_context:
        reasons.append(_binding_reason(
            "baseline_path_context_mismatch",
            expected_path_context,
            baseline_signature.get("path_context_hash"),
        ))

    expected_product_graph = scope.get("baseline_product_graph_hash")
    if expected_product_graph and baseline_signature.get("product_graph_hash") != expected_product_graph:
        reasons.append(_binding_reason(
            "baseline_product_graph_hash_mismatch",
            expected_product_graph,
            baseline_signature.get("product_graph_hash"),
        ))

    expected_model = scope.get("baseline_model_contract_hash")
    if expected_model and observed_hashes.get("baseline_model_contract_hash") != expected_model:
        reasons.append(_binding_reason(
            "baseline_model_contract_hash_mismatch",
            expected_model,
            observed_hashes.get("baseline_model_contract_hash"),
        ))

    expected_signature = scope.get("baseline_assembly_signature_hash")
    if expected_signature and observed_hashes.get("baseline_assembly_signature_hash") != expected_signature:
        reasons.append(_binding_reason(
            "baseline_assembly_signature_hash_mismatch",
            expected_signature,
            observed_hashes.get("baseline_assembly_signature_hash"),
        ))

    if baseline_model_contract is not None:
        model_path_hash = baseline_model_contract.get("path_context_hash")
        if model_path_hash and model_path_hash != baseline_signature.get("path_context_hash"):
            reasons.append(_binding_reason(
                "baseline_model_path_context_mismatch",
                baseline_signature.get("path_context_hash"),
                model_path_hash,
            ))
        model_graph_hash = baseline_model_contract.get("product_graph_hash")
        if model_graph_hash and model_graph_hash != baseline_signature.get("product_graph_hash"):
            reasons.append(_binding_reason(
                "baseline_model_product_graph_mismatch",
                baseline_signature.get("product_graph_hash"),
                model_graph_hash,
            ))
    return reasons


def _current_binding_reasons(
    scope: dict[str, Any],
    current_signature: dict[str, Any],
    current_model_contract: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    reasons = []
    expected_path_context = scope.get("path_context_hash")
    if expected_path_context and current_signature.get("path_context_hash") != expected_path_context:
        reasons.append({
            "code": "current_path_context_mismatch",
            "expected": expected_path_context,
            "actual": current_signature.get("path_context_hash"),
            "message": "当前契约与 CHANGE_SCOPE.json 不属于同一路径上下文。",
        })

    if current_model_contract is not None:
        model_path_hash = current_model_contract.get("path_context_hash")
        if model_path_hash and model_path_hash != current_signature.get("path_context_hash"):
            reasons.append({
                "code": "current_model_path_context_mismatch",
                "expected": current_signature.get("path_context_hash"),
                "actual": model_path_hash,
                "message": "当前模型契约与当前装配签名不属于同一路径上下文。",
            })
        model_graph_hash = current_model_contract.get("product_graph_hash")
        if model_graph_hash and model_graph_hash != current_signature.get("product_graph_hash"):
            reasons.append({
                "code": "current_model_product_graph_mismatch",
                "expected": current_signature.get("product_graph_hash"),
                "actual": model_graph_hash,
                "message": "当前模型契约与当前装配签名不属于同一产品图。",
            })
    return reasons


def _binding_reason(code: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "code": code,
        "expected": expected,
        "actual": actual,
        "message": "基准契约绑定不匹配，不能用于本轮漂移比较。",
    }


def _compare_signatures(
    scope: dict[str, Any],
    current_signature: dict[str, Any],
    baseline_signature: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_by_id = _instances_by_id(baseline_signature)
    current_by_id = _instances_by_id(current_signature)
    items: list[dict[str, Any]] = []

    for instance_id in sorted(set(baseline_by_id) - set(current_by_id)):
        baseline = baseline_by_id[instance_id]
        items.append(_drift_item(
            scope,
            "missing_required_instance",
            instance_id,
            baseline.get("part_no"),
            actual=False,
            expected=True,
            allowed=False,
        ))
    for instance_id in sorted(set(current_by_id) - set(baseline_by_id)):
        current = current_by_id[instance_id]
        items.append(_drift_item(
            scope,
            "new_instance",
            instance_id,
            current.get("part_no"),
            actual=True,
            expected=False,
            allowed=_is_authorized(scope, instance_id, current.get("part_no"), "count_change"),
        ))

    baseline_counts = _counts_by_part_no(baseline_by_id.values())
    current_counts = _counts_by_part_no(current_by_id.values())
    for part_no in sorted(set(baseline_counts) | set(current_counts)):
        before = baseline_counts.get(part_no, 0)
        after = current_counts.get(part_no, 0)
        if before != after:
            items.append({
                "code": "unexpected_count_change",
                "part_no": part_no,
                "baseline_count": before,
                "current_count": after,
                "allowed": _is_authorized(scope, "", part_no, "count_change"),
                "message": "实例数量变化未被当前变更范围授权。",
            })

    for instance_id in sorted(set(baseline_by_id) & set(current_by_id)):
        baseline = baseline_by_id[instance_id]
        current = current_by_id[instance_id]
        part_no = current.get("part_no") or baseline.get("part_no")
        items.extend(_compare_instance_geometry(scope, instance_id, part_no, current, baseline))
    return items


def _compare_instance_geometry(
    scope: dict[str, Any],
    instance_id: str,
    part_no: str | None,
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    tolerances = _tolerances(scope)
    items = []
    baseline_size = _vector(baseline.get("size_mm") or _bbox_size(baseline.get("bbox_mm")))
    current_size = _vector(current.get("size_mm") or _bbox_size(current.get("bbox_mm")))
    size_threshold = [
        max(tolerances["bbox_size_abs_mm"], abs(value) * tolerances["bbox_size_rel"])
        for value in baseline_size
    ]
    size_delta = [current_size[index] - baseline_size[index] for index in range(3)]
    if _exceeds(size_delta, size_threshold):
        items.append(_drift_item(
            scope,
            "unexpected_bbox_size_drift",
            instance_id,
            part_no,
            actual_delta=size_delta,
            threshold=size_threshold,
            baseline=baseline_size,
            current=current_size,
            change_type="geometry_refinement",
        ))

    baseline_center = _vector(baseline.get("center_mm"))
    current_center = _vector(current.get("center_mm"))
    center_threshold = [tolerances["center_abs_mm"]] * 3
    center_delta = [current_center[index] - baseline_center[index] for index in range(3)]
    if _exceeds(center_delta, center_threshold):
        items.append(_drift_item(
            scope,
            "unexpected_center_drift",
            instance_id,
            part_no,
            actual_delta=center_delta,
            threshold=center_threshold,
            baseline=baseline_center,
            current=current_center,
            change_type="move",
        ))

    baseline_rotation = _rotation(baseline)
    current_rotation = _rotation(current)
    rotation_delta = [
        _shortest_angle_delta(current_rotation[index], baseline_rotation[index])
        for index in range(3)
    ]
    rotation_threshold = [tolerances["rotation_deg"]] * 3
    if _exceeds(rotation_delta, rotation_threshold):
        items.append(_drift_item(
            scope,
            "unexpected_transform_drift",
            instance_id,
            part_no,
            actual_delta=rotation_delta,
            threshold=rotation_threshold,
            baseline=baseline_rotation,
            current=current_rotation,
            change_type="move",
        ))
    return items


def _drift_item(
    scope: dict[str, Any],
    code: str,
    instance_id: str,
    part_no: str | None,
    *,
    actual: Any = None,
    expected: Any = None,
    actual_delta: list[float] | None = None,
    threshold: list[float] | None = None,
    baseline: Any = None,
    current: Any = None,
    allowed: bool | None = None,
    change_type: str = "geometry_refinement",
) -> dict[str, Any]:
    computed_allowed = _is_authorized(scope, instance_id, part_no, change_type) if allowed is None else allowed
    item = {
        "code": code,
        "instance_id": instance_id,
        "part_no": part_no,
        "allowed": computed_allowed,
        "message": _drift_message(code),
    }
    if actual is not None:
        item["actual"] = actual
    if expected is not None:
        item["expected"] = expected
    if actual_delta is not None:
        item["actual_delta"] = _round_list(actual_delta)
    if threshold is not None:
        item["threshold"] = _round_list(threshold)
    if baseline is not None:
        item["baseline"] = _round_list(baseline) if isinstance(baseline, list) else baseline
    if current is not None:
        item["current"] = _round_list(current) if isinstance(current, list) else current
    return item


def _blocking_from_drift(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reasons = []
    seen = set()
    count_changed_parts = {
        item.get("part_no")
        for item in items
        if item.get("code") == "unexpected_count_change" and not item.get("allowed")
    }
    for item in items:
        if item.get("allowed"):
            continue
        if item.get("code") == "new_instance" and item.get("part_no") in count_changed_parts:
            continue
        key = (item["code"], item.get("instance_id"), item.get("part_no"))
        if key in seen:
            continue
        seen.add(key)
        reasons.append({
            "code": item["code"],
            "instance_id": item.get("instance_id"),
            "part_no": item.get("part_no"),
            "message": item.get("message"),
        })
    return reasons


def _is_authorized(
    scope: dict[str, Any],
    instance_id: str,
    part_no: str | None,
    change_type: str,
) -> bool:
    if change_type not in set(scope.get("allowed_change_types") or []):
        return False
    allowed_instances = set(scope.get("allowed_instance_ids") or [])
    allowed_parts = set(scope.get("allowed_part_nos") or [])
    return bool((instance_id and instance_id in allowed_instances) or (part_no and part_no in allowed_parts))


def _instances_by_id(signature: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(instance["instance_id"]): instance
        for instance in signature.get("instances", [])
        if isinstance(instance, dict) and instance.get("instance_id")
    }


def _counts_by_part_no(instances) -> dict[str, int]:
    counts: dict[str, int] = {}
    for instance in instances:
        part_no = str(instance.get("part_no") or "")
        if not part_no:
            continue
        counts[part_no] = counts.get(part_no, 0) + 1
    return counts


def _tolerances(scope: dict[str, Any]) -> dict[str, float]:
    tolerances = dict(DEFAULT_TOLERANCES)
    tolerances.update(scope.get("tolerances") or {})
    return {key: float(value) for key, value in tolerances.items()}


def _bbox_size(bbox: Any) -> list[float]:
    values = _vector(bbox, length=6)
    return [
        values[3] - values[0],
        values[4] - values[1],
        values[5] - values[2],
    ]


def _rotation(instance: dict[str, Any]) -> list[float]:
    transform = instance.get("transform") or {}
    return _vector(transform.get("rotation_deg"))


def _vector(values: Any, *, length: int = 3) -> list[float]:
    if values is None:
        return [0.0] * length
    result = [float(value) for value in values]
    if len(result) != length:
        raise ValueError(f"Expected vector length {length}, got {values!r}")
    return result


def _exceeds(delta: list[float], threshold: list[float]) -> bool:
    return any(abs(delta[index]) > threshold[index] for index in range(len(delta)))


def _shortest_angle_delta(current: float, baseline: float) -> float:
    return (float(current) - float(baseline) + 180.0) % 360.0 - 180.0


def _round_list(values: list[float]) -> list[float]:
    return [round(float(value), 6) for value in values]


def _drift_message(code: str) -> str:
    messages = {
        "missing_required_instance": "基准中的必需实例在当前装配中缺失。",
        "new_instance": "当前装配出现了基准中不存在的实例。",
        "unexpected_count_change": "实例数量变化未被当前变更范围授权。",
        "unexpected_bbox_size_drift": "实例包络尺寸漂移超过当前变更范围阈值。",
        "unexpected_center_drift": "实例中心位置漂移超过当前变更范围阈值。",
        "unexpected_transform_drift": "实例旋转漂移超过当前变更范围阈值。",
    }
    return messages.get(code, "当前变化未被变更范围授权。")
