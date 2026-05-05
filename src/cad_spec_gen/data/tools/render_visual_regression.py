from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.artifact_index import get_accepted_baseline, get_active_artifacts
from tools.contract_io import file_sha256, load_json_required, stable_json_hash, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.render_qa import manifest_blocks_enhance


REQUIRED_ACTIVE_ARTIFACTS = {
    "product_graph",
    "model_contract",
    "assembly_signature",
    "render_manifest",
}


def run_render_visual_regression(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    baseline_manifest_path: str | Path | None = None,
    baseline_signature_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Check active-run render evidence against product contracts and baseline."""
    root = Path(project_root).resolve()
    index_path = _resolve_project_path(
        root,
        artifact_index_path
        or Path("cad") / subsystem / ".cad-spec-gen" / "ARTIFACT_INDEX.json",
        "artifact index",
    )
    index = load_json_required(index_path, "artifact index")
    if index.get("subsystem") != subsystem:
        raise ValueError(
            f"artifact index subsystem mismatch: {index.get('subsystem')} != {subsystem}"
        )

    active_run_id = str(index.get("active_run_id") or "")
    active_run_dir = _default_run_dir(root, subsystem, active_run_id or "unknown")
    artifact_paths: dict[str, Path] = {}
    blocking_reasons: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    active_artifacts = get_active_artifacts(index)
    for key, raw_path in active_artifacts.items():
        artifact_paths[key] = _resolve_project_path(root, raw_path, f"artifact {key}")
    missing = sorted(REQUIRED_ACTIVE_ARTIFACTS - set(artifact_paths))
    blocking_reasons.extend(
        {
            "code": "artifact_index_missing_required_artifact",
            "artifact": key,
            "message": "渲染视觉回归检查缺少当前 active run 的必需契约产物。",
        }
        for key in missing
    )

    contracts: dict[str, dict[str, Any]] = {}
    for key in sorted(REQUIRED_ACTIVE_ARTIFACTS & set(artifact_paths)):
        contracts[key] = load_json_required(artifact_paths[key], key)

    product_graph = contracts.get("product_graph", {})
    model_contract = contracts.get("model_contract", {})
    assembly_signature = contracts.get("assembly_signature", {})
    render_manifest = contracts.get("render_manifest", {})
    run_id = active_run_id or str(render_manifest.get("run_id") or product_graph.get("run_id") or "")
    active_run_dir = _default_run_dir(root, subsystem, run_id or "unknown")

    if len(contracts) == len(REQUIRED_ACTIVE_ARTIFACTS):
        path_context_hash = product_graph.get("path_context_hash")
        blocking_reasons.extend(
            _check_identity(subsystem, run_id, path_context_hash, contracts)
        )
        blocking_reasons.extend(
            _check_hash_chain(
                product_graph,
                model_contract,
                assembly_signature,
                render_manifest,
            )
        )
        blocking_reasons.extend(_check_active_render_dir(root, subsystem, run_id, render_manifest))
        blocking_reasons.extend(
            _check_render_files(root, render_manifest, artifact_paths.get("render_manifest"))
        )
        blocking_reasons.extend(_check_manifest_view_set(render_manifest))
        blocking_reasons.extend(_check_current_instances(product_graph, assembly_signature))
        current_view_evidence = _view_instance_evidence(render_manifest)
        if current_view_evidence:
            blocking_reasons.extend(
                _check_current_view_instance_union(product_graph, current_view_evidence)
            )
        else:
            warnings.append(
                {
                    "code": "render_view_instance_evidence_missing",
                    "message": (
                        "当前 render_manifest.json 没有逐视角实例可见性证据；"
                        "已完成视角/装配契约检查，但不能证明每张图内的元件身份。"
                    ),
                }
            )

    baseline = _load_baseline_context(
        root,
        index,
        baseline_manifest_path=baseline_manifest_path,
        baseline_signature_path=baseline_signature_path,
    )
    if baseline.get("status") == "available" and render_manifest and assembly_signature:
        blocking_reasons.extend(
            _compare_baseline_views(baseline["render_manifest"], render_manifest)
        )
        blocking_reasons.extend(
            _compare_baseline_instances(
                baseline["assembly_signature"],
                assembly_signature,
            )
        )
        baseline_evidence = _view_instance_evidence(baseline["render_manifest"])
        current_evidence = _view_instance_evidence(render_manifest)
        if baseline_evidence and current_evidence:
            blocking_reasons.extend(
                _compare_baseline_view_evidence(baseline_evidence, current_evidence)
            )
        elif baseline_evidence and not current_evidence:
            blocking_reasons.append(
                {
                    "code": "render_view_instance_evidence_missing_from_current",
                    "message": (
                        "accepted baseline 已有逐视角实例可见性证据，"
                        "但当前 render_manifest.json 丢失了这类证据。"
                    ),
                }
            )

    status = "blocked" if blocking_reasons else ("warning" if warnings else "pass")
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "subsystem": subsystem,
        "status": status,
        "ordinary_user_message": _ordinary_user_message(status, blocking_reasons, warnings),
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "counts": _counts(product_graph, assembly_signature, render_manifest, baseline),
        "current": {
            "run_id": run_id,
            "render_dir": _render_dir_rel(root, render_manifest),
            "views": _manifest_views(render_manifest),
            "instance_ids": _assembly_instance_ids(assembly_signature),
        },
        "baseline": _baseline_summary(root, baseline),
        "artifacts": _relative_artifacts(root, artifact_paths),
        "artifact_hashes": _artifact_hashes(artifact_paths),
    }
    target = _resolve_project_path(
        root,
        output_path or active_run_dir / "RENDER_VISUAL_REGRESSION.json",
        "render visual regression report output",
    )
    try:
        target.relative_to(active_run_dir.resolve())
    except ValueError as exc:
        raise ValueError("render visual regression output must stay in the active run directory") from exc
    report["artifacts"]["render_visual_regression"] = project_relative(target, root)
    write_json_atomic(target, report)
    return report


def command_return_code_for_render_visual_regression(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {"pass", "warning"} else 1


def _check_identity(
    subsystem: str,
    run_id: str,
    path_context_hash: str | None,
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    reasons = []
    for name, payload in contracts.items():
        if not payload.get("path_context_hash"):
            reasons.append(
                {
                    "code": "path_context_hash_missing",
                    "contract": name,
                    "message": "渲染视觉契约缺少路径上下文哈希，不能防止路径漂移。",
                }
            )
        if payload.get("subsystem") != subsystem:
            reasons.append(
                {
                    "code": "subsystem_mismatch",
                    "contract": name,
                    "expected": subsystem,
                    "actual": payload.get("subsystem"),
                    "message": "契约子系统与当前 render-visual-check 请求不一致。",
                }
            )
        if payload.get("run_id") != run_id:
            reasons.append(
                {
                    "code": "run_id_mismatch",
                    "contract": name,
                    "expected": run_id,
                    "actual": payload.get("run_id"),
                    "message": "契约不属于当前 active_run_id。",
                }
            )
        if payload.get("path_context_hash") != path_context_hash:
            reasons.append(
                {
                    "code": "path_context_hash_mismatch",
                    "contract": name,
                    "expected": path_context_hash,
                    "actual": payload.get("path_context_hash"),
                    "message": "契约路径上下文不一致。",
                }
            )
    return reasons


def _check_hash_chain(
    product_graph: dict[str, Any],
    model_contract: dict[str, Any],
    assembly_signature: dict[str, Any],
    render_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    product_hash = stable_json_hash(product_graph)
    model_hash = stable_json_hash(model_contract)
    assembly_hash = stable_json_hash(assembly_signature)
    checks = [
        (
            "model_contract_product_graph_hash_mismatch",
            model_contract.get("product_graph_hash"),
            product_hash,
            "模型契约没有绑定当前产品图。",
        ),
        (
            "assembly_signature_product_graph_hash_mismatch",
            assembly_signature.get("product_graph_hash"),
            product_hash,
            "装配签名没有绑定当前产品图。",
        ),
        (
            "assembly_signature_model_contract_hash_mismatch",
            assembly_signature.get("model_contract_hash"),
            model_hash,
            "装配签名没有绑定当前模型契约。",
        ),
        (
            "render_manifest_product_graph_hash_mismatch",
            render_manifest.get("product_graph_hash"),
            product_hash,
            "渲染清单没有绑定当前产品图。",
        ),
        (
            "render_manifest_model_contract_hash_mismatch",
            render_manifest.get("model_contract_hash"),
            model_hash,
            "渲染清单没有绑定当前模型契约。",
        ),
        (
            "render_manifest_assembly_signature_hash_mismatch",
            render_manifest.get("assembly_signature_hash"),
            assembly_hash,
            "渲染清单没有绑定当前运行时装配签名。",
        ),
    ]
    reasons = []
    for code, actual, expected, message in checks:
        if actual is None:
            reasons.append(
                {
                    "code": f"{code.removesuffix('_mismatch')}_missing",
                    "expected": expected,
                    "actual": None,
                    "message": "契约缺少必需的上游哈希绑定。",
                }
            )
        elif actual != expected:
            reasons.append(
                {
                    "code": code,
                    "expected": expected,
                    "actual": actual,
                    "message": message,
                }
            )
    return reasons


def _check_active_render_dir(
    project_root: Path,
    subsystem: str,
    run_id: str,
    render_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    if not render_manifest:
        return []
    render_dir = _manifest_render_dir(project_root, render_manifest)
    expected = (project_root / "cad" / "output" / "renders" / subsystem / run_id).resolve()
    if render_dir != expected:
        return [
            {
                "code": "render_dir_not_active_run",
                "expected": project_relative(expected, project_root),
                "actual": project_relative(render_dir, project_root),
                "message": "渲染清单的 render_dir 不属于当前 active run。",
            }
        ]
    return []


def _check_render_files(
    project_root: Path,
    render_manifest: dict[str, Any],
    manifest_path: Path | None,
) -> list[dict[str, Any]]:
    reasons = manifest_blocks_enhance(render_manifest)
    render_dir = _manifest_render_dir(project_root, render_manifest)
    for entry in render_manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path_abs_resolved") or entry.get("path_rel_project") or entry.get("path")
        if not raw_path:
            reasons.append(
                {
                    "code": "render_file_path_missing",
                    "message": "渲染清单缺少图片路径。",
                }
            )
            continue
        image_path = _resolve_project_path(project_root, raw_path, "render file")
        try:
            image_path.relative_to(render_dir)
        except ValueError:
            reasons.append(
                {
                    "code": "render_file_outside_render_dir",
                    "path": project_relative(image_path, project_root),
                    "message": "渲染图片不在当前 render_dir 内。",
                }
            )
            continue
        if not image_path.is_file():
            reasons.append(
                {
                    "code": "render_file_missing",
                    "path": project_relative(image_path, project_root),
                    "message": "渲染图片文件不存在。",
                }
            )
            continue
        expected_hash = entry.get("sha256")
        actual_hash = file_sha256(image_path)
        if not expected_hash:
            reasons.append(
                {
                    "code": "render_file_hash_missing",
                    "path": project_relative(image_path, project_root),
                    "message": "渲染图片缺少 sha256 绑定，不能作为回归证据。",
                }
            )
        elif expected_hash != actual_hash:
            reasons.append(
                {
                    "code": "render_file_hash_mismatch",
                    "path": project_relative(image_path, project_root),
                    "expected": expected_hash,
                    "actual": actual_hash,
                    "message": "渲染图片内容已不同于 render_manifest.json 登记的文件。",
                }
            )
    if manifest_path and _manifest_render_dir(project_root, render_manifest) != manifest_path.parent.resolve():
        reasons.append(
            {
                "code": "render_manifest_not_in_render_dir",
                "manifest": project_relative(manifest_path, project_root),
                "render_dir": project_relative(_manifest_render_dir(project_root, render_manifest), project_root),
                "message": "render_manifest.json 不在其声明的 render_dir 中。",
            }
        )
    return reasons


def _check_manifest_view_set(render_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = []
    seen: set[str] = set()
    for entry in _manifest_file_entries(render_manifest):
        view = str(entry.get("view") or "")
        if not view:
            reasons.append(
                {
                    "code": "render_view_missing",
                    "message": "渲染清单中的文件条目缺少 view 字段。",
                }
            )
            continue
        if view in seen:
            reasons.append(
                {
                    "code": "render_view_duplicate",
                    "view": view,
                    "message": "同一 render_manifest.json 中重复登记了同一视角。",
                }
            )
        seen.add(view)
    return reasons


def _check_current_instances(
    product_graph: dict[str, Any],
    assembly_signature: dict[str, Any],
) -> list[dict[str, Any]]:
    required = _required_product_instance_ids(product_graph)
    actual = set(_assembly_instance_ids(assembly_signature))
    missing = sorted(required - actual)
    return [
        {
            "code": "assembly_instance_missing_from_product_graph",
            "instance_id": instance_id,
            "message": "产品图中的必需实例没有进入当前运行时装配签名。",
        }
        for instance_id in missing
    ]


def _check_current_view_instance_union(
    product_graph: dict[str, Any],
    current_view_evidence: dict[str, set[str]],
) -> list[dict[str, Any]]:
    required = _required_product_instance_ids(product_graph)
    visible_union = set().union(*current_view_evidence.values()) if current_view_evidence else set()
    missing = sorted(required - visible_union)
    if not missing:
        return []
    return [
        {
            "code": "render_evidence_missing_required_instance",
            "missing_instance_ids": missing,
            "message": "逐视角渲染证据没有覆盖产品图中的全部必需实例。",
        }
    ]


def _compare_baseline_views(
    baseline_manifest: dict[str, Any],
    current_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_views = set(_manifest_views(baseline_manifest))
    current_views = set(_manifest_views(current_manifest))
    missing = sorted(baseline_views - current_views)
    return [
        {
            "code": "render_view_missing_from_baseline",
            "view": view,
            "message": "当前渲染清单比 accepted baseline 少了视角。",
        }
        for view in missing
    ]


def _compare_baseline_instances(
    baseline_signature: dict[str, Any],
    current_signature: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_instances = set(_assembly_instance_ids(baseline_signature))
    current_instances = set(_assembly_instance_ids(current_signature))
    missing = sorted(baseline_instances - current_instances)
    return [
        {
            "code": "assembly_instance_missing_from_baseline",
            "instance_id": instance_id,
            "message": "当前运行时装配签名比 accepted baseline 少了实例。",
        }
        for instance_id in missing
    ]


def _compare_baseline_view_evidence(
    baseline_evidence: dict[str, set[str]],
    current_evidence: dict[str, set[str]],
) -> list[dict[str, Any]]:
    reasons = []
    for view, baseline_instances in sorted(baseline_evidence.items()):
        current_instances = current_evidence.get(view, set())
        missing = sorted(baseline_instances - current_instances)
        if missing:
            reasons.append(
                {
                    "code": "render_view_instance_missing_from_baseline",
                    "view": view,
                    "missing_instance_ids": missing,
                    "message": "当前视角可见实例证据比 accepted baseline 少。",
                }
            )
    return reasons


def _load_baseline_context(
    project_root: Path,
    index: dict[str, Any],
    *,
    baseline_manifest_path: str | Path | None,
    baseline_signature_path: str | Path | None,
) -> dict[str, Any]:
    if baseline_manifest_path is not None or baseline_signature_path is not None:
        if baseline_manifest_path is None or baseline_signature_path is None:
            raise ValueError("baseline manifest and baseline signature must be provided together")
        manifest_path = _resolve_project_path(project_root, baseline_manifest_path, "baseline render manifest")
        signature_path = _resolve_project_path(project_root, baseline_signature_path, "baseline assembly signature")
        manifest = load_json_required(manifest_path, "baseline render manifest")
        signature = load_json_required(signature_path, "baseline assembly signature")
        return {
            "status": "available",
            "run_id": str(manifest.get("run_id") or signature.get("run_id") or "explicit"),
            "render_manifest": manifest,
            "assembly_signature": signature,
            "artifacts": {
                "render_manifest": manifest_path,
                "assembly_signature": signature_path,
            },
        }
    try:
        baseline_artifacts = get_accepted_baseline(index)
    except ValueError:
        return {"status": "not_configured"}

    signature_path = _resolve_project_path(
        project_root,
        baseline_artifacts["assembly_signature"],
        "accepted baseline assembly signature",
    )
    render_manifest_raw = baseline_artifacts.get("render_manifest")
    if not render_manifest_raw:
        return {
            "status": "signature_only",
            "run_id": baseline_artifacts["run_id"],
            "assembly_signature": load_json_required(signature_path, "accepted baseline assembly signature"),
            "artifacts": {"assembly_signature": signature_path},
        }
    manifest_path = _resolve_project_path(
        project_root,
        render_manifest_raw,
        "accepted baseline render manifest",
    )
    return {
        "status": "available",
        "run_id": baseline_artifacts["run_id"],
        "render_manifest": load_json_required(manifest_path, "accepted baseline render manifest"),
        "assembly_signature": load_json_required(signature_path, "accepted baseline assembly signature"),
        "artifacts": {
            "render_manifest": manifest_path,
            "assembly_signature": signature_path,
        },
    }


def _counts(
    product_graph: dict[str, Any],
    assembly_signature: dict[str, Any],
    render_manifest: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, int]:
    baseline_manifest = baseline.get("render_manifest") or {}
    baseline_signature = baseline.get("assembly_signature") or {}
    return {
        "product_instances": len(_required_product_instance_ids(product_graph)),
        "current_instances": len(_assembly_instance_ids(assembly_signature)),
        "current_views": len(_manifest_views(render_manifest)),
        "current_render_files": len(_manifest_file_entries(render_manifest)),
        "baseline_instances": len(_assembly_instance_ids(baseline_signature)),
        "baseline_views": len(_manifest_views(baseline_manifest)),
        "baseline_render_files": len(_manifest_file_entries(baseline_manifest)),
    }


def _baseline_summary(project_root: Path, baseline: dict[str, Any]) -> dict[str, Any]:
    status = baseline.get("status", "not_configured")
    if status != "available":
        return {"status": status}
    manifest = baseline.get("render_manifest") or {}
    signature = baseline.get("assembly_signature") or {}
    artifacts = baseline.get("artifacts") or {}
    return {
        "status": status,
        "run_id": baseline.get("run_id"),
        "render_dir": _render_dir_rel(project_root, manifest),
        "views": _manifest_views(manifest),
        "instance_ids": _assembly_instance_ids(signature),
        "artifacts": {
            key: project_relative(path, project_root)
            for key, path in artifacts.items()
        },
    }


def _manifest_file_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in manifest.get("files", []) if isinstance(entry, dict)]


def _manifest_views(manifest: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(entry.get("view"))
            for entry in _manifest_file_entries(manifest)
            if entry.get("view")
        }
    )


def _view_instance_evidence(manifest: dict[str, Any]) -> dict[str, set[str]]:
    evidence: dict[str, set[str]] = {}
    keys = (
        "visible_instance_ids",
        "instance_ids",
        "visible_instances",
        "component_instance_ids",
        "rendered_instance_ids",
    )
    for entry in _manifest_file_entries(manifest):
        view = str(entry.get("view") or "")
        if not view:
            continue
        values: list[Any] = []
        for key in keys:
            raw = entry.get(key)
            if isinstance(raw, list):
                values.extend(raw)
        instances = {
            str(value.get("instance_id") if isinstance(value, dict) else value)
            for value in values
            if value
        }
        if instances:
            evidence[view] = instances
    return evidence


def _required_product_instance_ids(product_graph: dict[str, Any]) -> set[str]:
    return {
        str(instance.get("instance_id"))
        for instance in product_graph.get("instances", [])
        if isinstance(instance, dict)
        and instance.get("instance_id")
        and instance.get("required", True) is not False
        and instance.get("render_policy") == "required"
    }


def _assembly_instance_ids(assembly_signature: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(instance.get("instance_id"))
            for instance in assembly_signature.get("instances", [])
            if isinstance(instance, dict) and instance.get("instance_id")
        }
    )


def _manifest_render_dir(project_root: Path, render_manifest: dict[str, Any]) -> Path:
    raw = (
        render_manifest.get("render_dir_abs_resolved")
        or render_manifest.get("render_dir")
        or render_manifest.get("render_dir_rel_project")
    )
    if not raw:
        raise ValueError("render manifest is missing render_dir")
    return _resolve_project_path(project_root, raw, "render manifest render_dir")


def _render_dir_rel(project_root: Path, render_manifest: dict[str, Any]) -> str | None:
    if not render_manifest:
        return None
    try:
        return project_relative(_manifest_render_dir(project_root, render_manifest), project_root)
    except (KeyError, TypeError, ValueError):
        return None


def _ordinary_user_message(
    status: str,
    blocking_reasons: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    if status == "pass":
        return "渲染视觉一致性检查通过，可以继续照片级增强或交付验收。"
    if status == "warning":
        first = warnings[0].get("message") if warnings else "存在非阻断警告。"
        return f"渲染视觉一致性基本通过，但仍有警告：{first}"
    first = blocking_reasons[0].get("message") if blocking_reasons else "存在阻断问题。"
    return f"渲染视觉一致性检查已停止：{first}"


def _default_run_dir(project_root: Path, subsystem: str, run_id: str) -> Path:
    return project_root / "cad" / subsystem / ".cad-spec-gen" / "runs" / run_id


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved


def _relative_artifacts(project_root: Path, artifacts: dict[str, Path]) -> dict[str, str]:
    return {key: project_relative(path, project_root) for key, path in artifacts.items()}


def _artifact_hashes(artifacts: dict[str, Path]) -> dict[str, str]:
    return {
        key: file_sha256(path)
        for key, path in artifacts.items()
        if path.is_file()
    }
