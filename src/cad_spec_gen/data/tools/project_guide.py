from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import unicodedata
from typing import Any, Mapping

from tools.contract_io import load_json_required, write_json_atomic
from tools.model_audit import build_model_quality_summary
from tools.path_policy import assert_within_project, project_relative
from tools.photo3d_provider_health import (
    provider_health_for_presets,
    summarize_provider_health,
)
from tools.photo3d_provider_presets import DEFAULT_PROVIDER_PRESET, public_provider_presets


CODEGEN_SENTINELS = ("params.py", "build_all.py", "assembly.py")
PROJECT_ENTRY_GUIDE_DIR = Path(".cad-spec-gen") / "project-guide"

# ===== §11.M-5/M-3: 共享常量（_safe_cli_token 与 _classify_unsafe_reason 共用） =====
_SAFE_CLI_PATTERN = re.compile(r"[A-Za-z0-9_.\-]+")
# CJK Unified (U+4E00-U+9FFF) + Ext-A (U+3400-U+4DBF)
_CJK_PATTERN = re.compile(r"[一-鿿㐀-䶿]")
_WIN_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")

_UNSAFE_MESSAGE_TEMPLATES = {
    "windows_path": (
        "<Windows 路径含反斜杠/冒号；请用 forward slash 或加双引号包裹路径>"
    ),
    "chinese_text": (
        "<user_text 含中文；请用 --confirm-X flag 直接传值，不通过自然语言>"
    ),
    "special_chars": (
        "<user_text 含特殊字符（引号/换行等）；"
        "请用 --confirm-X flag 直接传值，不通过自然语言>"
    ),
}

_CJK_TOKEN_MAP = {
    "升": "sheng",
    "降": "jiang",
    "平": "ping",
    "台": "tai",
    "设": "she",
    "计": "ji",
}


def write_project_entry_guide(
    project_root: str | Path,
    design_doc: str | Path,
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Write a read-only design-document entry guide before subsystem selection."""
    root = Path(project_root).resolve()
    design_doc_path = _resolve_project_path(root, design_doc, "design document")
    if not design_doc_path.is_file():
        raise FileNotFoundError(f"design document not found: {design_doc_path}")
    design_doc_rel = project_relative(design_doc_path, root)
    target = _project_entry_guide_target(root, output_path)
    candidates = _subsystem_candidates_for_design_doc(design_doc_path)
    options = [
        _confirm_subsystem_option(candidate["subsystem"], design_doc_rel)
        for candidate in candidates
    ]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_mode": "design_doc",
        "status": "needs_subsystem_confirmation",
        "ordinary_user_message": _ordinary_user_message(
            "needs_subsystem_confirmation"
        ),
        "mutates_pipeline_state": False,
        "does_not_scan_directories": True,
        "design_doc": {
            "path": design_doc_rel,
            "exists": True,
        },
        "subsystem_candidates": candidates,
        "next_action": {
            "kind": "confirm_subsystem",
            "requires_user_confirmation": True,
            "options": options,
        },
        "artifacts": {
            "project_guide": project_relative(target, root),
        },
    }
    write_json_atomic(target, report)
    return report


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
    model_quality_summary = _model_quality_summary(root, subsystem_dir)

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
            model_quality_summary=model_quality_summary,
        ),
        "next_action": next_action,
        "artifacts": {
            "project_guide": project_relative(target, root),
        },
    }
    if provider_choice:
        report["provider_choice"] = provider_choice
        report["provider_wizard"] = _provider_wizard(provider_choice)
    if model_quality_summary:
        report["model_quality_summary"] = model_quality_summary
    if index_path:
        report["artifacts"]["artifact_index"] = project_relative(index_path, root)
    write_json_atomic(target, report)
    return report


def command_return_code_for_project_guide(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {
        "needs_subsystem_confirmation",
        "needs_init",
        "needs_design_doc",
        "needs_spec",
        "needs_codegen",
        "needs_build_render",
        "ready_for_photo3d_run",
        # rev 4 DR-3：product_goal 入口的 informative/actionable 状态
        "needs_product_goal",
        "needs_kpi_confirmation",
        "ready_for_cad_spec",
        "unknown_subsystem",
        "not_yet_implemented",
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
    model_quality_summary: dict[str, Any] | None = None,
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
        "model_quality": _model_quality_stage_status(
            root,
            subsystem_dir,
            model_quality_summary,
        ),
    }


def _model_quality_summary(
    root: Path,
    subsystem_dir: Path,
) -> dict[str, Any] | None:
    report_path = subsystem_dir / ".cad-spec-gen" / "geometry_report.json"
    if not report_path.is_file():
        return None
    geometry_report = load_json_required(report_path, "geometry report")
    return build_model_quality_summary(
        geometry_report,
        report_path=report_path,
        source="geometry_report",
        binding_status="project_report",
        project_root=root,
    )


def _model_quality_stage_status(
    root: Path,
    subsystem_dir: Path,
    model_quality_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    report_path = subsystem_dir / ".cad-spec-gen" / "geometry_report.json"
    if not model_quality_summary:
        return {
            "exists": False,
            "path": project_relative(report_path, root),
            "readiness_status": "not_available",
            "photoreal_risk": "unknown",
        }
    return {
        "exists": True,
        "path": project_relative(report_path, root),
        "readiness_status": model_quality_summary["readiness_status"],
        "photoreal_risk": model_quality_summary["photoreal_risk"],
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
    provider_health = provider_health_for_presets(presets, root)
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
        provider_health,
    )
    return {
        "kind": "select_enhancement_provider",
        "requires_user_confirmation": True,
        "source_report": project_relative(source_path, root),
        "default_provider_preset": DEFAULT_PROVIDER_PRESET,
        "provider_presets": presets,
        "provider_health": provider_health,
        "provider_health_summary": summarize_provider_health(provider_health),
        "ordinary_user_options": ordinary_user_options,
        "handoff_actions": handoff_actions,
    }


def _ordinary_user_provider_options(
    presets: list[dict[str, Any]],
    handoff_actions: list[dict[str, Any]],
    provider_health: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions_by_preset = {
        str(action["provider_preset"]): action for action in handoff_actions
    }
    health_by_preset = {
        str(item["provider_preset"]): item for item in provider_health
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
            "health": health_by_preset[preset_id],
        }
        if "cli" in action:
            option["cli"] = action["cli"]
        options.append(option)
    return options


def _provider_wizard(provider_choice: dict[str, Any]) -> dict[str, Any]:
    default_provider = str(provider_choice["default_provider_preset"])
    options = []
    for option in provider_choice["ordinary_user_options"]:
        preview_action: dict[str, Any] = {
            "kind": "preview_photo3d_handoff",
            "requires_user_confirmation": True,
            "argv": option["argv"],
        }
        if "cli" in option:
            preview_action["cli"] = option["cli"]
        options.append(
            {
                "provider_preset": option["provider_preset"],
                "title": option["ordinary_user_title"],
                "summary": option["ordinary_user_summary"],
                "recommended_when": option["recommended_when"],
                "requires_setup": bool(option["requires_setup"]),
                "requires_user_confirmation": True,
                "is_default": option["provider_preset"] == default_provider,
                "health": option["health"],
                "preview_action": preview_action,
            }
        )
    return {
        "kind": "provider_preset_selection_wizard",
        "source": "provider_choice.ordinary_user_options",
        "mutates_pipeline_state": False,
        "executes_enhancement": False,
        "does_not_scan_directories": True,
        "default_provider_preset": default_provider,
        "health_summary": provider_choice["provider_health_summary"],
        "steps": [
            {
                "id": "choose_provider",
                "title": "选择增强方式",
                "description": "从白名单 provider preset 中选择一个普通用户可读选项。",
            },
            {
                "id": "preview_handoff",
                "title": "预览交接命令",
                "description": "只生成 photo3d-handoff --provider-preset 预览命令，不执行增强。",
            },
            {
                "id": "confirm_handoff",
                "title": "显式确认执行",
                "description": "真正执行仍需用户在 photo3d-handoff 边界显式确认。",
            },
        ],
        "options": options,
    }


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
        "needs_subsystem_confirmation": "项目向导已读取设计文档；请先确认要创建或继续的子系统名称。",
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


def _project_entry_guide_target(
    root: Path,
    output_path: str | Path | None,
) -> Path:
    guide_dir = (root / PROJECT_ENTRY_GUIDE_DIR).resolve()
    target = _resolve_project_path(
        root,
        output_path or guide_dir / "PROJECT_GUIDE.json",
        "project entry guide output",
    )
    try:
        target.relative_to(guide_dir)
    except ValueError as exc:
        raise ValueError("PROJECT_GUIDE.json output must stay in .cad-spec-gen/project-guide") from exc
    if target.name != "PROJECT_GUIDE.json":
        raise ValueError("project entry guide output must be PROJECT_GUIDE.json")
    return target


def _subsystem_candidates_for_design_doc(design_doc_path: Path) -> list[dict[str, Any]]:
    stem = re.sub(r"^\d+[-_ ]*", "", design_doc_path.stem).strip()
    subsystem = _safe_subsystem_slug(stem) or "subsystem"
    return [
        {
            "subsystem": subsystem,
            "source": "design_doc_filename",
            "confidence": "medium",
            "reason": "由显式设计文档文件名派生；需要用户确认后才进入子系统流程。",
        }
    ]


def _safe_subsystem_slug(text: str) -> str:
    tokens: list[str] = []
    ascii_buffer: list[str] = []

    def flush_ascii() -> None:
        if ascii_buffer:
            token = "".join(ascii_buffer).strip("_")
            if token:
                tokens.append(token)
            ascii_buffer.clear()

    normalized = unicodedata.normalize("NFKD", text)
    for char in normalized:
        if char.isascii() and char.isalnum():
            ascii_buffer.append(char.lower())
            continue
        flush_ascii()
        if char in _CJK_TOKEN_MAP:
            tokens.append(_CJK_TOKEN_MAP[char])
        elif "\u4e00" <= char <= "\u9fff":
            tokens.append(f"u{ord(char):x}")
        elif char in {"-", "_", " ", "."}:
            flush_ascii()
    flush_ascii()
    slug = "_".join(token for token in tokens if token)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if slug and slug[0].isdigit():
        slug = f"subsystem_{slug}"
    return slug[:80]


def _confirm_subsystem_option(subsystem: str, design_doc_rel: str) -> dict[str, Any]:
    argv = [
        "python",
        "cad_pipeline.py",
        "project-guide",
        "--subsystem",
        subsystem,
        "--design-doc",
        design_doc_rel,
    ]
    option: dict[str, Any] = {
        "subsystem": subsystem,
        "argv": argv,
    }
    if _safe_cli_token(subsystem):
        option["cli"] = " ".join(argv)
    return option


def _resolve_project_path(project_root: Path, path: str | Path, label: str) -> Path:
    requested = Path(path)
    resolved = requested if requested.is_absolute() else project_root / requested
    resolved = resolved.resolve()
    assert_within_project(resolved, project_root, label)
    return resolved


def _safe_cli_token(value: str) -> bool:
    """token 校验（subsystem 名等用）。

    与 _classify_unsafe_reason 共用 _SAFE_CLI_PATTERN，避免字面发散；
    注意：empty 在此返 False（不算合法 token），而 _classify_unsafe_reason("") 返 "safe"
    （含义"无需降级"），两者语义有别。
    """
    return bool(_SAFE_CLI_PATTERN.fullmatch(value or ""))


def _classify_unsafe_reason(value: str) -> str:
    """分类 user_text 不安全原因，给出精确下一步提示。

    返回值（按优先级）：'safe' | 'chinese_text' | 'windows_path' | 'special_chars'。
    优先级（互斥）：safe > chinese_text > windows_path > special_chars。

    Empty string 与 None：value 必须为 str；调用方（_sanitize_preview_cli）已用
    `or ""` 兜底 None。empty 时返 "safe"——含义"无 unsafe 内容需要降级"，与
    _safe_cli_token("") = False 不同（后者用于 token 校验，empty 不算合法 token）。

    日文 Kanji 命中 CJK Unified 范围会归 chinese_text；Hangul / 假名归
    special_chars——本管线针对中文用户的产品边界。
    """
    if not value:
        return "safe"
    if _SAFE_CLI_PATTERN.fullmatch(value):
        return "safe"
    if _CJK_PATTERN.search(value):
        return "chinese_text"
    if _WIN_PATH_PATTERN.match(value):
        return "windows_path"
    return "special_chars"


def write_project_goal_guide(
    project_root: str | Path,
    product_goal: str,
    *,
    design_doc: str | Path | None = None,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float | tuple[float, float]] | None = None,
    output_path: str | Path | None = None,
    _state_round: int = 1,
) -> dict[str, Any]:
    """产品目标自然语言入口；写 PROJECT_GUIDE.json + 异步多轮 state（v2.31.0+）。

    与 write_project_entry_guide 平行；不动 pipeline state，纯只读。
    v2.31.0 break-change：needs_kpi_confirmation 走异步多轮模式 → cwd 写 state file；
    ready_for_cad_spec / 其他终态删 state file（如存在）。

    Args:
        _state_round: v2.31.0 内部参数；--resume 时从 state.round + 1 传入；
            首轮（一次未给全 KPI）默认 1。
    """
    from tools.product_goal_parser import parse_product_goal
    from tools.product_goal_state import delete_state, write_state

    root = Path(project_root).resolve()
    target = _project_entry_guide_target(root, output_path)

    parse_result = parse_product_goal(
        text=product_goal,
        confirmed_subsystem=confirmed_subsystem,
        confirmed_kpis=confirmed_kpis,
    )

    status, next_action = _derive_goal_status_and_next_action(
        parse_result, design_doc, root
    )

    # v2.31.0：缺 KPI → 写 state file（cwd）；ready_for_cad_spec → 删 state file
    if status == "needs_kpi_confirmation":
        missing_kpis = list(next_action.get("missing_kpis", []))
        write_state({
            "raw_text": parse_result.raw_text,
            "subsystem_class": parse_result.subsystem_class,
            "subsystem_status": parse_result.subsystem_status,
            "confirmed_subsystem": confirmed_subsystem,
            "confirmed_kpis": dict(confirmed_kpis or {}),
            "missing_kpis": missing_kpis,
            "design_doc": str(design_doc) if design_doc else None,
            "round": _state_round,
        })
        ordinary_message = _ordinary_user_message_for_progressive(
            parse_result.subsystem_class,
            missing_kpis,
            already_confirmed=dict(confirmed_kpis or {}),
        )
    else:
        # 离开"待补 KPI"续答模式 → 清场 state file（幂等；不存在不报错）
        # 覆盖：ready_for_cad_spec / needs_design_doc / needs_subsystem_confirmation /
        #       unknown_subsystem / not_yet_implemented / needs_product_goal
        delete_state()
        ordinary_message = _ordinary_user_message_for_goal(status)

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_mode": "product_goal",
        "status": status,
        "ordinary_user_message": ordinary_message,
        "mutates_pipeline_state": False,
        "does_not_scan_directories": True,
        "product_goal": _serialize_parse_result(parse_result),
        "next_action": next_action,
        "artifacts": {
            "project_guide": project_relative(target, root),
        },
    }

    write_json_atomic(target, report)
    return report


def _ordinary_user_message_for_progressive(
    subsystem_class: str | None,
    missing_kpis: list[str],
    already_confirmed: Mapping[str, Any],
) -> str:
    """v2.31.0 多轮渐进 needs_kpi_confirmation 文案（含 --resume hint）。"""
    subsystem_label = subsystem_class or "(未识别)"
    confirmed_lines = ""
    if already_confirmed:
        confirmed_str = ", ".join(
            f"{k}={v}" for k, v in sorted(already_confirmed.items())
        )
        confirmed_lines = f"\n  已记录：{confirmed_str}"

    first_missing = missing_kpis[0] if missing_kpis else "<KEY>"
    missing_str = " / ".join(missing_kpis)
    return (
        f"已识别为 {subsystem_label}。还缺 KPI：{missing_str}。{confirmed_lines}\n"
        f"  下一步答任一项：cad-spec-gen project-guide --resume "
        f"--answer {first_missing}=<值>\n"
        f"  状态已记到 ./PROJECT_GOAL_STATE.json；可断点续答"
    )


def _sanitize_preview_cli(
    action: dict[str, Any],
    parse_result: Any,
) -> dict[str, Any]:
    """检查 next_action.preview_cli 是否含 user text；含且 unsafe 则降级。

    设计原则（spec rev 4 DR-4 + M-4）：
    - 当 preview_cli 真的把 raw_text 拼进去时，必须用 _classify_unsafe_reason 校验
    - reason 分类对应 _UNSAFE_MESSAGE_TEMPLATES 三类文案
    - 不变量：preview_cli_unsafe=True ⇔ unsafe_reason 存在；safe 路径下两字段都不写
    """
    raw_text = getattr(parse_result, "raw_text", None) or ""
    if not raw_text:
        return action
    cli = action.get("preview_cli")
    if not isinstance(cli, str):
        return action
    if raw_text not in cli:
        return action
    reason = _classify_unsafe_reason(raw_text)
    if reason == "safe":
        return action
    action["preview_cli_unsafe"] = True
    action["unsafe_reason"] = reason
    action["preview_cli"] = _UNSAFE_MESSAGE_TEMPLATES[reason]
    return action


# ===== I-4: 7 per-status builder（spec rev 4 §I-4） =====
def _action_for_needs_product_goal(parse_result: Any) -> dict[str, Any]:
    return {
        "kind": "supply_product_goal",
        "preview_cli": (
            'python cad_pipeline.py project-guide --product-goal "<描述你的产品>"'
        ),
    }


def _action_for_needs_subsystem_confirmation(parse_result: Any) -> dict[str, Any]:
    return {
        "kind": "confirm_subsystem",
        "preview_cli": (
            'python cad_pipeline.py project-guide --product-goal "..." '
            "--confirm-subsystem <lifting_platform|end_effector>"
        ),
    }


def _action_for_unknown_subsystem(parse_result: Any) -> dict[str, Any]:
    return {
        "kind": "list_supported_subsystems",
        "supported": ["lifting_platform", "end_effector"],
    }


def _action_for_not_yet_implemented(parse_result: Any) -> dict[str, Any]:
    return {
        "kind": "wait_for_implementation",
        "alternatives": {
            "implemented_subsystems": ["lifting_platform", "end_effector"],
            "switch_example": (
                'python cad_pipeline.py project-guide --product-goal "做升降平台 50kg"'
            ),
            "feedback_url": "https://github.com/proecheng/cad-spec-gen/issues/new",
        },
    }


def _action_for_needs_kpi_confirmation(
    parse_result: Any, missing: list[str]
) -> dict[str, Any]:
    return {
        "kind": "supply_missing_kpis",
        "missing_kpis": missing,
        "preview_cli": _build_kpi_preview_cli(parse_result.subsystem_class, missing),
    }


def _action_for_needs_design_doc(parse_result: Any) -> dict[str, Any]:
    return {
        "kind": "supply_design_doc",
        "preview_cli": (
            f"python cad_pipeline.py project-guide "
            f'--product-goal "{parse_result.raw_text}" '
            f"--design-doc docs/design/<chapter>-{parse_result.subsystem_class}.md"
        ),
    }


def _action_for_ready_for_cad_spec(
    parse_result: Any, design_doc: "str | Path"
) -> dict[str, Any]:
    return {
        "kind": "run_cad_spec",
        "preview_cli": (
            f"python cad_pipeline.py spec --subsystem {parse_result.subsystem_class} "
            f"--design-doc {design_doc}"
        ),
    }


def _derive_goal_status_and_next_action(
    parse_result: Any,
    design_doc: str | Path | None,
    root: Path,
) -> tuple[str, dict[str, Any]]:
    """从 parse 结果派生 status + next_action。

    路由层：决定 status，调对应 builder，最后统一过 _sanitize_preview_cli。
    """
    if not parse_result.raw_text or not parse_result.raw_text.strip():
        status = "needs_product_goal"
        action = _action_for_needs_product_goal(parse_result)
    elif parse_result.subsystem_status == "ambiguous":
        status = "needs_subsystem_confirmation"
        action = _action_for_needs_subsystem_confirmation(parse_result)
    elif parse_result.subsystem_status == "unknown":
        status = "unknown_subsystem"
        action = _action_for_unknown_subsystem(parse_result)
    elif parse_result.subsystem_status == "not_yet_implemented":
        status = "not_yet_implemented"
        action = _action_for_not_yet_implemented(parse_result)
    else:
        # implemented 分支
        missing = [
            name for name, k in parse_result.kpis.items() if k.status != "extracted"
        ]
        if missing:
            status = "needs_kpi_confirmation"
            action = _action_for_needs_kpi_confirmation(parse_result, missing)
        elif not design_doc:
            status = "needs_design_doc"
            action = _action_for_needs_design_doc(parse_result)
        else:
            status = "ready_for_cad_spec"
            action = _action_for_ready_for_cad_spec(parse_result, design_doc)

    return status, _sanitize_preview_cli(action, parse_result)


def _ordinary_user_message_for_goal(status: str) -> str:
    return {
        "needs_product_goal": "请用 --product-goal \"<描述你的产品>\" 启动。",
        "needs_subsystem_confirmation": "产品类别含混，请用 --confirm-subsystem <name> 指定。",
        "not_yet_implemented": "该子系统在路线图但尚未实现；可考虑 lifting_platform 或 end_effector。",
        "unknown_subsystem": "未识别此产品类别；当前支持 lifting_platform、end_effector。",
        "needs_kpi_confirmation": "请用 --confirm-X flag 补齐缺失 KPI 后重跑。",
        "needs_design_doc": "KPI 已齐，请用 --design-doc <path> 提供设计文档后重跑。",
        "ready_for_cad_spec": "一切就绪，可执行 cad-spec 生成 CAD_SPEC.md。",
    }.get(status, "(未知状态)")


def _build_kpi_preview_cli(subsystem: str, missing: list[str]) -> str:
    """构造缺失 KPI 的 confirm CLI 模板。"""
    flag_map = {
        "load_kg": "--confirm-load 50",
        "stroke_mm": "--confirm-stroke 200",
        "platform_size_mm": "--confirm-platform-size 350x230",
        "rot_range_deg": "--confirm-rot-range 135",
        "switch_time_s": "--confirm-switch-time 1.5",
        "flange_dia_mm": "--confirm-flange-dia 90",
    }
    flags = " ".join(flag_map[k] for k in missing if k in flag_map)
    return f"python cad_pipeline.py project-guide --product-goal \"...\" {flags}"


def _serialize_parse_result(parse_result: Any) -> dict[str, Any]:
    kpi_extracted: dict[str, Any] = {}
    kpi_missing: list[str] = []
    for name, k in parse_result.kpis.items():
        if k.status == "extracted":
            # tuple value（如 platform_size_mm）改为 list 以便 JSON 序列化
            value = list(k.value) if isinstance(k.value, tuple) else k.value
            kpi_extracted[name] = value
        else:
            kpi_missing.append(name)
    return {
        "text": parse_result.raw_text,
        "subsystem_class": parse_result.subsystem_class,
        "subsystem_status": parse_result.subsystem_status,
        "kpi_extracted": kpi_extracted,
        "kpi_missing": kpi_missing,
        "parser_evidence": parse_result.parser_evidence,
    }
