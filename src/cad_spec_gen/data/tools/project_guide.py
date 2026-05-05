from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from tools.contract_io import load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative
from tools.photo3d_provider_presets import DEFAULT_PROVIDER_PRESET, public_provider_presets


CODEGEN_SENTINELS = ("params.py", "build_all.py", "assembly.py")


def write_project_guide(
    project_root: str | Path,
    subsystem: str,
    *,
    design_doc: str | Path | None = None,
    artifact_index_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    subsystem_dir = (root / "cad" / subsystem).resolve()
    assert_within_project(subsystem_dir, root, "subsystem directory")

    design_doc_rel = None
    if design_doc:
        design_doc_path = _resolve_project_path(root, design_doc, "design document")
        if not design_doc_path.is_file():
            raise FileNotFoundError(f"design document not found: {design_doc_path}")
        design_doc_rel = project_relative(design_doc_path, root)

    index_path = None
    index = None
    if artifact_index_path:
        index_path = _resolve_project_path(root, artifact_index_path, "artifact index")
        index = load_json_required(index_path, "artifact index")
    else:
        default_index = subsystem_dir / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
        if default_index.is_file():
            index_path = default_index.resolve()
            index = load_json_required(index_path, "artifact index")

    if index is not None and index.get("subsystem") != subsystem:
        raise ValueError(f"artifact index subsystem mismatch: {index.get('subsystem')} != {subsystem}")

    active_run_id = _active_run_id(index)
    run_dir = subsystem_dir / ".cad-spec-gen" / "runs" / active_run_id if active_run_id else None
    target = _project_guide_target(root, subsystem_dir, run_dir, output_path)

    status, next_action = _next_action(
        root,
        subsystem,
        subsystem_dir,
        design_doc_rel=design_doc_rel,
        index_path=index_path,
        active_run_id=active_run_id,
    )
    provider_choice = _provider_choice(
        root,
        subsystem,
        run_dir,
        index_path,
        active_run_id,
    )

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "subsystem": subsystem,
        "run_id": active_run_id,
        "status": status,
        "ordinary_user_message": _ordinary_user_message(status),
        "mutates_pipeline_state": False,
        "does_not_scan_directories": True,
        "stage_status": _stage_status(
            root,
            subsystem_dir,
            design_doc_rel=design_doc_rel,
            index_path=index_path,
            active_run_id=active_run_id,
        ),
        "next_action": next_action,
        "artifacts": {
            "project_guide": project_relative(target, root),
        },
    }
    if provider_choice:
        report["provider_choice"] = provider_choice
    if index_path:
        report["artifacts"]["artifact_index"] = project_relative(index_path, root)
    write_json_atomic(target, report)
    return report


def command_return_code_for_project_guide(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {
        "needs_init",
        "needs_design_doc",
        "needs_spec",
        "needs_codegen",
        "needs_build_render",
        "ready_for_photo3d_run",
    } else 1


def _next_action(
    root: Path,
    subsystem: str,
    subsystem_dir: Path,
    *,
    design_doc_rel: str | None,
    index_path: Path | None,
    active_run_id: str | None,
) -> tuple[str, dict[str, Any]]:
    if not subsystem_dir.is_dir():
        argv = ["python", "cad_pipeline.py", "init", "--subsystem", subsystem]
        return "needs_init", _action("run_init", argv, subsystem=subsystem)

    spec_path = subsystem_dir / "CAD_SPEC.md"
    if not spec_path.is_file():
        if not design_doc_rel:
            return (
                "needs_design_doc",
                {
                    "kind": "provide_design_doc",
                    "requires_user_confirmation": False,
                    "required_input": "--design-doc",
                },
            )
        argv = [
            "python",
            "cad_pipeline.py",
            "spec",
            "--subsystem",
            subsystem,
            "--design-doc",
            design_doc_rel,
        ]
        return "needs_spec", _action("run_spec", argv, subsystem=subsystem)

    missing_codegen = [
        name for name in CODEGEN_SENTINELS if not (subsystem_dir / name).is_file()
    ]
    if missing_codegen:
        argv = ["python", "cad_pipeline.py", "codegen", "--subsystem", subsystem]
        action = _action("run_codegen", argv, subsystem=subsystem)
        action["missing_files"] = missing_codegen
        return "needs_codegen", action

    if not active_run_id or not index_path:
        argv = ["python", "cad_pipeline.py", "build", "--subsystem", subsystem, "--render"]
        return "needs_build_render", _action("run_build_render", argv, subsystem=subsystem)

    argv = [
        "python",
        "cad_pipeline.py",
        "photo3d-run",
        "--subsystem",
        subsystem,
        "--artifact-index",
        project_relative(index_path, root),
    ]
    return "ready_for_photo3d_run", _action("run_photo3d_guide", argv, subsystem=subsystem)


def _action(kind: str, argv: list[str], *, subsystem: str) -> dict[str, Any]:
    action: dict[str, Any] = {
        "kind": kind,
        "requires_user_confirmation": False,
        "argv": argv,
    }
    if _safe_cli_token(subsystem):
        action["cli"] = " ".join(argv)
    return action


def _stage_status(
    root: Path,
    subsystem_dir: Path,
    *,
    design_doc_rel: str | None,
    index_path: Path | None,
    active_run_id: str | None,
) -> dict[str, Any]:
    codegen_files = {
        name: (subsystem_dir / name).is_file() for name in CODEGEN_SENTINELS
    }
    return {
        "subsystem_dir": {
            "exists": subsystem_dir.is_dir(),
            "path": project_relative(subsystem_dir, root),
        },
        "design_doc": {
            "provided": bool(design_doc_rel),
            "path": design_doc_rel,
        },
        "spec": {
            "exists": (subsystem_dir / "CAD_SPEC.md").is_file(),
            "path": project_relative(subsystem_dir / "CAD_SPEC.md", root),
        },
        "codegen": {
            "ready": all(codegen_files.values()),
            "files": codegen_files,
        },
        "artifact_index": {
            "exists": bool(index_path and index_path.is_file()),
            "path": project_relative(index_path, root) if index_path else None,
            "active_run_id": active_run_id,
        },
    }


def _provider_choice(
    root: Path,
    subsystem: str,
    run_dir: Path | None,
    index_path: Path | None,
    active_run_id: str | None,
) -> dict[str, Any] | None:
    if not run_dir or not index_path or not active_run_id:
        return None
    source_path, source = _current_photo3d_source(root, run_dir)
    if not source_path or not source:
        return None
    if source.get("subsystem") != subsystem or str(source.get("run_id") or "") != active_run_id:
        return None
    next_action = source.get("next_action") or {}
    if source.get("status") != "ready_for_enhancement":
        return None
    if next_action.get("kind") != "run_enhancement":
        return None

    index_rel = project_relative(index_path, root)
    presets = public_provider_presets()
    handoff_actions = []
    for preset in presets:
        preset_id = str(preset["id"])
        argv = [
            "python",
            "cad_pipeline.py",
            "photo3d-handoff",
            "--subsystem",
            subsystem,
            "--artifact-index",
            index_rel,
            "--provider-preset",
            preset_id,
        ]
        action: dict[str, Any] = {
            "provider_preset": preset_id,
            "ordinary_user_label": preset.get("ordinary_user_label") or preset.get("label"),
            "requires_user_confirmation": True,
            "argv": argv,
        }
        if _safe_cli_token(subsystem):
            action["cli"] = " ".join(argv)
        handoff_actions.append(action)
    ordinary_user_options = _ordinary_user_provider_options(
        presets,
        handoff_actions,
    )
    return {
        "kind": "select_enhancement_provider",
        "requires_user_confirmation": True,
        "source_report": project_relative(source_path, root),
        "default_provider_preset": DEFAULT_PROVIDER_PRESET,
        "provider_presets": presets,
        "ordinary_user_options": ordinary_user_options,
        "handoff_actions": handoff_actions,
    }


def _ordinary_user_provider_options(
    presets: list[dict[str, Any]],
    handoff_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions_by_preset = {
        str(action["provider_preset"]): action for action in handoff_actions
    }
    options = []
    for preset in presets:
        preset_id = str(preset["id"])
        action = actions_by_preset[preset_id]
        option = {
            "provider_preset": preset_id,
            "ordinary_user_title": preset["ordinary_user_title"],
            "ordinary_user_summary": preset["ordinary_user_summary"],
            "recommended_when": preset["recommended_when"],
            "requires_setup": bool(preset["requires_setup"]),
            "requires_user_confirmation": True,
            "argv": action["argv"],
        }
        if "cli" in action:
            option["cli"] = action["cli"]
        options.append(option)
    return options


def _current_photo3d_source(
    root: Path,
    run_dir: Path,
) -> tuple[Path | None, dict[str, Any] | None]:
    for filename in ("PHOTO3D_RUN.json", "PHOTO3D_AUTOPILOT.json"):
        path = (run_dir / filename).resolve()
        try:
            path.relative_to(run_dir.resolve())
        except ValueError:
            continue
        assert_within_project(path, root, filename)
        if path.is_file():
            return path, load_json_required(path, filename)
    return None, None


def _ordinary_user_message(status: str) -> str:
    messages = {
        "needs_init": "项目向导未找到子系统目录；下一步先初始化子系统。",
        "needs_design_doc": "项目向导需要显式设计文档路径；请重新运行并传 --design-doc。",
        "needs_spec": "项目向导已拿到设计文档；下一步生成 CAD_SPEC.md。",
        "needs_codegen": "项目向导发现 CAD_SPEC.md 已存在；下一步生成 CadQuery 代码。",
        "needs_build_render": "项目向导发现代码已就绪；下一步构建并渲染，生成当前 run 证据。",
        "ready_for_photo3d_run": "项目向导发现当前 active run；下一步运行 Photo3D 多轮向导。",
    }
    return messages.get(status, "项目向导已停止。")


def _active_run_id(index: dict[str, Any] | None) -> str | None:
    if not index:
        return None
    active_run_id = str(index.get("active_run_id") or "")
    if not active_run_id:
        return None
    run = (index.get("runs") or {}).get(active_run_id) or {}
    if not run.get("active"):
        return None
    return active_run_id


def _project_guide_target(
    root: Path,
    subsystem_dir: Path,
    run_dir: Path | None,
    output_path: str | Path | None,
) -> Path:
    default_target = (run_dir or subsystem_dir / ".cad-spec-gen") / "PROJECT_GUIDE.json"
    target = _resolve_project_path(root, output_path or default_target, "project guide output")
    expected_dir = (run_dir or subsystem_dir / ".cad-spec-gen").resolve()
    try:
        target.relative_to(expected_dir)
    except ValueError as exc:
        raise ValueError("PROJECT_GUIDE.json output must stay in the selected guide directory") from exc
    if target.name != "PROJECT_GUIDE.json":
        raise ValueError("project guide output must be PROJECT_GUIDE.json")
    return target


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved


def _safe_cli_token(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", value or ""))
