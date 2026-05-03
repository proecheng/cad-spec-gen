from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.artifact_index import get_active_artifacts
from tools.change_scope import evaluate_change_scope, load_change_scope
from tools.contract_io import file_sha256, load_json_required, stable_json_hash, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.render_qa import manifest_blocks_enhance


QUALITY_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
DEFAULT_HERO_MIN_QUALITY = "B"
DEFAULT_HIGH_MIN_QUALITY = "C"


def run_photo3d_gate(
    project_root: str | Path,
    subsystem: str,
    *,
    artifact_index_path: str | Path | None = None,
    change_scope_path: str | Path | None = None,
    baseline_signature_path: str | Path | None = None,
    output_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    index_path = _resolve_project_path(
        root,
        artifact_index_path or Path("cad") / subsystem / ".cad-spec-gen" / "ARTIFACT_INDEX.json",
        "artifact index",
    )
    index = load_json_required(index_path, "artifact index")
    if index.get("subsystem") != subsystem:
        raise ValueError(f"artifact index subsystem mismatch: {index.get('subsystem')} != {subsystem}")
    active_run_id = index.get("active_run_id")
    artifacts = get_active_artifacts(index)

    artifact_paths = {
        key: _resolve_project_path(root, value, f"artifact {key}")
        for key, value in artifacts.items()
    }
    required = {"product_graph", "model_contract", "assembly_signature", "render_manifest"}
    missing = sorted(required - set(artifact_paths))
    if missing:
        run_dir = _default_run_dir(root, subsystem, str(active_run_id or "unknown"))
        report = _build_report(
            subsystem=subsystem,
            run_id=str(active_run_id or ""),
            path_context_hash=None,
            status="blocked",
            blocking_reasons=[
                {
                    "code": "artifact_index_missing_required_artifact",
                    "artifact": key,
                    "message": "产物索引缺少照片级门禁必需契约。",
                }
                for key in missing
            ],
            warnings=[],
            counts={},
            artifacts=_relative_artifacts(root, artifact_paths),
            enhancement_status="blocked",
        )
        return _finalize_report(root, report, output_path or run_dir / "PHOTO3D_REPORT.json", run_dir)

    product_graph = load_json_required(artifact_paths["product_graph"], "product graph")
    model_contract = load_json_required(artifact_paths["model_contract"], "model contract")
    assembly_signature = load_json_required(artifact_paths["assembly_signature"], "assembly signature")
    render_manifest = load_json_required(artifact_paths["render_manifest"], "render manifest")

    run_id = str(active_run_id or product_graph.get("run_id") or "")
    run_dir = _default_run_dir(root, subsystem, run_id)
    path_context_hash = product_graph.get("path_context_hash")
    blocking_reasons: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    contracts = {
        "product_graph": product_graph,
        "model_contract": model_contract,
        "assembly_signature": assembly_signature,
        "render_manifest": render_manifest,
    }
    blocking_reasons.extend(_check_identity(subsystem, run_id, path_context_hash, contracts))
    blocking_reasons.extend(_check_hash_chain(product_graph, model_contract, assembly_signature, render_manifest))
    blocking_reasons.extend(_check_product_instances(product_graph, assembly_signature))
    blocking_reasons.extend(_check_model_quality(model_contract, config or {}))
    blocking_reasons.extend(_check_assembly_signature(assembly_signature))
    blocking_reasons.extend(_check_render_manifest(root, render_manifest))

    if change_scope_path is not None:
        scope_path = _resolve_project_path(root, change_scope_path, "change scope")
        change_scope = load_change_scope(scope_path)
        baseline_signature = None
        if baseline_signature_path is not None:
            baseline_signature = load_json_required(
                _resolve_project_path(root, baseline_signature_path, "baseline assembly signature"),
                "baseline assembly signature",
            )
        change_report = evaluate_change_scope(
            change_scope,
            current_signature=assembly_signature,
            baseline_signature=baseline_signature,
            current_model_contract=model_contract,
        )
        blocking_reasons.extend(list(change_report.get("blocking_reasons") or []))
        warnings.extend(list(change_report.get("warnings") or []))

    status = "blocked" if blocking_reasons else ("warning" if warnings else "pass")
    report = _build_report(
        subsystem=subsystem,
        run_id=run_id,
        path_context_hash=path_context_hash,
        status=status,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
        counts={
            "product_instances": len([
                item for item in product_graph.get("instances", [])
                if isinstance(item, dict) and item.get("render_policy") != "excluded"
            ]),
            "assembly_instances": len([
                item for item in assembly_signature.get("instances", [])
                if isinstance(item, dict)
            ]),
            "render_files": len([
                item for item in render_manifest.get("files", [])
                if isinstance(item, dict)
            ]),
        },
        artifacts=_relative_artifacts(root, artifact_paths),
        enhancement_status="blocked" if status == "blocked" else "not_run",
    )
    return _finalize_report(root, report, output_path or run_dir / "PHOTO3D_REPORT.json", run_dir)


def _check_identity(
    subsystem: str,
    run_id: str,
    path_context_hash: str | None,
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    reasons = []
    for name, payload in contracts.items():
        if not payload.get("path_context_hash"):
            reasons.append({
                "code": "path_context_hash_missing",
                "contract": name,
                "message": "照片级契约缺少路径上下文哈希，不能防止路径漂移。",
            })
        if payload.get("subsystem") != subsystem:
            reasons.append({
                "code": "subsystem_mismatch",
                "contract": name,
                "expected": subsystem,
                "actual": payload.get("subsystem"),
                "message": "契约子系统与当前 photo3d 请求不一致。",
            })
        if payload.get("run_id") != run_id:
            reasons.append({
                "code": "run_id_mismatch",
                "contract": name,
                "expected": run_id,
                "actual": payload.get("run_id"),
                "message": "契约不属于当前 run_id。",
            })
        if payload.get("path_context_hash") != path_context_hash:
            reasons.append({
                "code": "path_context_hash_mismatch",
                "contract": name,
                "expected": path_context_hash,
                "actual": payload.get("path_context_hash"),
                "message": "契约路径上下文不一致。",
            })
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
            reasons.append({
                "code": f"{code.removesuffix('_mismatch')}_missing",
                "expected": expected,
                "actual": None,
                "message": "契约缺少必需的上游哈希绑定。",
            })
        elif actual != expected:
            reasons.append({
                "code": code,
                "expected": expected,
                "actual": actual,
                "message": message,
            })
    return reasons


def _check_product_instances(
    product_graph: dict[str, Any],
    assembly_signature: dict[str, Any],
) -> list[dict[str, Any]]:
    expected = {
        str(instance.get("instance_id")): instance
        for instance in product_graph.get("instances", [])
        if isinstance(instance, dict)
        and instance.get("instance_id")
        and instance.get("required", True) is not False
        and instance.get("render_policy") == "required"
    }
    actual = {
        str(instance.get("instance_id"))
        for instance in assembly_signature.get("instances", [])
        if isinstance(instance, dict) and instance.get("instance_id")
    }
    return [
        {
            "code": "missing_required_instance",
            "instance_id": instance_id,
            "part_no": expected[instance_id].get("part_no"),
            "message": "产品图中的必需实例没有进入运行时装配签名。",
        }
        for instance_id in sorted(set(expected) - actual)
    ]


def _check_model_quality(
    model_contract: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    gate_config = config.get("photo3d_gate", config)
    hero_min = gate_config.get("hero_min_quality", DEFAULT_HERO_MIN_QUALITY)
    high_min = gate_config.get("high_min_quality", DEFAULT_HIGH_MIN_QUALITY)
    reasons = []
    for decision in model_contract.get("decisions", []):
        if not isinstance(decision, dict) or decision.get("render_policy") == "excluded":
            continue
        priority = decision.get("visual_priority", "normal")
        min_quality = hero_min if priority == "hero" else high_min if priority == "high" else None
        if min_quality and _quality_rank(decision.get("geometry_quality")) < _quality_rank(min_quality):
            reasons.append({
                "code": "model_quality_below_threshold",
                "part_no": decision.get("part_no"),
                "visual_priority": priority,
                "geometry_quality": decision.get("geometry_quality"),
                "min_quality": min_quality,
                "message": "模型质量不足，不能作为照片级通过证据。",
            })
    return reasons


def _check_assembly_signature(assembly_signature: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = []
    if assembly_signature.get("source_mode") != "runtime":
        reasons.append({
            "code": "assembly_signature_not_runtime",
            "source_mode": assembly_signature.get("source_mode"),
            "message": "照片级门禁必须使用运行时装配签名，静态预检不能通过。",
        })
    reasons.extend(list(assembly_signature.get("blocking_reasons") or []))
    return reasons


def _check_render_manifest(project_root: Path, render_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = manifest_blocks_enhance(render_manifest)
    render_dir = _resolve_project_path(
        project_root,
        render_manifest.get("render_dir_abs_resolved")
        or render_manifest.get("render_dir")
        or render_manifest.get("render_dir_rel_project")
        or ".",
        "render manifest render_dir",
    )
    for entry in render_manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        path_value = entry.get("path_abs_resolved") or entry.get("path_rel_project") or entry.get("path")
        if not path_value:
            reasons.append({
                "code": "render_file_path_missing",
                "message": "渲染清单缺少图片路径。",
            })
            continue
        image_path = _resolve_project_path(project_root, path_value, "render file")
        try:
            image_path.relative_to(render_dir)
        except ValueError:
            reasons.append({
                "code": "render_file_outside_render_dir",
                "path": project_relative(image_path, project_root),
                "message": "渲染图片不在当前 render_dir 内。",
            })
            continue
        if not image_path.is_file():
            reasons.append({
                "code": "render_file_missing",
                "path": project_relative(image_path, project_root),
                "message": "渲染图片文件不存在。",
            })
            continue
        actual_hash = file_sha256(image_path)
        expected_hash = entry.get("sha256")
        if not expected_hash:
            reasons.append({
                "code": "render_file_hash_missing",
                "path": project_relative(image_path, project_root),
                "message": "渲染图片缺少 sha256 绑定，不能作为照片级增强输入。",
            })
        elif actual_hash != expected_hash:
            reasons.append({
                "code": "render_file_hash_mismatch",
                "path": project_relative(image_path, project_root),
                "expected": expected_hash,
                "actual": actual_hash,
                "message": "渲染图片内容已不同于 RENDER_MANIFEST.json 登记的文件。",
            })
    return reasons


def _quality_rank(quality: Any) -> int:
    return QUALITY_ORDER.get(str(quality or "E").upper(), 0)


def _build_report(
    *,
    subsystem: str,
    run_id: str,
    path_context_hash: str | None,
    status: str,
    blocking_reasons: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    counts: dict[str, int],
    artifacts: dict[str, str],
    enhancement_status: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "subsystem": subsystem,
        "path_context_hash": path_context_hash,
        "status": status,
        "ordinary_user_message": _ordinary_user_message(status, blocking_reasons, warnings),
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "counts": counts,
        "artifacts": artifacts,
        "enhancement_status": enhancement_status,
    }


def _ordinary_user_message(
    status: str,
    blocking_reasons: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    if status == "pass":
        return "照片级 CAD 门禁通过，可以进入增强阶段。"
    if status == "warning":
        first_warning = warnings[0].get("message") if warnings else "存在非阻断警告。"
        return f"照片级 CAD 门禁基本通过，但仍有警告：{first_warning}"
    first_reason = blocking_reasons[0].get("message") if blocking_reasons else "存在阻断问题。"
    return f"照片级出图已停止：{first_reason}"


def _write_report(project_root: Path, report: dict[str, Any], output_path: str | Path) -> dict[str, Any]:
    target = _resolve_project_path(project_root, output_path, "photo3d report output")
    write_json_atomic(target, report)
    return report


def _finalize_report(
    project_root: Path,
    report: dict[str, Any],
    output_path: str | Path,
    run_dir: Path,
) -> dict[str, Any]:
    target = _resolve_project_path(project_root, output_path, "photo3d report output")
    report.setdefault("artifacts", {})["photo3d_report"] = project_relative(target, project_root)
    if report.get("status") == "blocked":
        from tools.photo3d_actions import build_action_plan, build_llm_context_pack

        action_plan_path = _resolve_project_path(project_root, run_dir / "ACTION_PLAN.json", "action plan output")
        llm_pack_path = _resolve_project_path(project_root, run_dir / "LLM_CONTEXT_PACK.json", "llm context output")
        report["artifacts"]["action_plan"] = project_relative(action_plan_path, project_root)
        report["artifacts"]["llm_context_pack"] = project_relative(llm_pack_path, project_root)
        action_plan = build_action_plan(project_root, report)
        llm_context_pack = build_llm_context_pack(project_root, report, action_plan)
        write_json_atomic(action_plan_path, action_plan)
        write_json_atomic(llm_pack_path, llm_context_pack)
    write_json_atomic(target, report)
    return report


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved


def _default_run_dir(project_root: Path, subsystem: str, run_id: str) -> Path:
    return project_root / "cad" / subsystem / ".cad-spec-gen" / "runs" / run_id


def _relative_artifacts(project_root: Path, artifacts: dict[str, Path]) -> dict[str, str]:
    return {
        key: project_relative(path, project_root)
        for key, path in artifacts.items()
    }
