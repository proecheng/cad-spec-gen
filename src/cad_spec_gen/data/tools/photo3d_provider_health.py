from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping


Status = str
ModuleChecker = Callable[[str], bool]


def provider_health_for_presets(
    presets: list[dict[str, Any]],
    project_root: str | Path,
    *,
    env: Mapping[str, str] | None = None,
    home_dir: str | Path | None = None,
    module_available: ModuleChecker | None = None,
) -> list[dict[str, Any]]:
    root = Path(project_root).resolve()
    env_map = env if env is not None else os.environ
    home = Path(home_dir).resolve() if home_dir is not None else Path.home()
    can_import = module_available or _module_available
    enhance_cfg = _load_enhance_config(root)
    presets_by_backend = {
        str(preset.get("backend")): preset
        for preset in presets
        if preset.get("backend")
    }

    return [
        _health_for_preset(
            preset,
            root,
            env_map=env_map,
            home_dir=home,
            module_available=can_import,
            enhance_cfg=enhance_cfg,
            presets_by_backend=presets_by_backend,
        )
        for preset in presets
    ]


def summarize_provider_health(health: list[dict[str, Any]]) -> dict[str, Any]:
    available = [
        item["provider_preset"] for item in health if item["status"] == "available"
    ]
    needs_setup = [
        item["provider_preset"] for item in health if item["status"] == "needs_setup"
    ]
    unknown = [item["provider_preset"] for item in health if item["status"] == "unknown"]
    return {
        "source": "provider_health",
        "mutates_pipeline_state": False,
        "executes_enhancement": False,
        "does_not_scan_directories": True,
        "available_provider_presets": available,
        "needs_setup_provider_presets": needs_setup,
        "unknown_provider_presets": unknown,
    }


def _health_for_preset(
    preset: dict[str, Any],
    root: Path,
    *,
    env_map: Mapping[str, str],
    home_dir: Path,
    module_available: ModuleChecker,
    enhance_cfg: dict[str, Any],
    presets_by_backend: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    preset_id = str(preset["id"])
    backend = preset.get("backend")
    required_capabilities = _required_capabilities(preset)
    checked_by = ["provider_preset"]

    if preset_id == "default":
        checked_by.append("project_configuration")
        configured_backend = str(enhance_cfg.get("backend") or "").strip()
        delegated = presets_by_backend.get(configured_backend)
        if delegated:
            delegated_health = _health_for_preset(
                delegated,
                root,
                env_map=env_map,
                home_dir=home_dir,
                module_available=module_available,
                enhance_cfg=enhance_cfg,
                presets_by_backend=presets_by_backend,
            )
            status = str(delegated_health["status"])
            hint = (
                "项目默认增强配置当前可用；真正执行仍在 handoff 确认边界之后。"
                if status == "available"
                else "项目默认增强配置还需要补齐依赖；可改选已可用 provider 或先完成配置。"
            )
            required_capabilities = delegated_health["required_capabilities"]
            checked_by.extend(
                item
                for item in delegated_health["checked_by"]
                if item not in checked_by and item != "provider_preset"
            )
        else:
            status = "available"
            hint = "使用项目当前增强配置；真正执行仍在 handoff 确认边界之后。"
    elif backend == "engineering":
        status = "available"
        hint = "本地工程预览无需云端凭据；可作为照片级增强前的结构复查兜底。"
        checked_by.append("local_pipeline")
    elif backend == "gemini":
        checked_by.extend(["local_file_presence", "user_configuration_presence"])
        status = (
            "available"
            if _gemini_script_exists(root, env_map)
            and _gemini_config_present(home_dir)
            else "needs_setup"
        )
        hint = (
            "Gemini 云增强配置已就绪。"
            if status == "available"
            else "需要先配置 Gemini 云增强访问，再执行 handoff。"
        )
    elif backend == "fal":
        checked_by.extend(["environment_presence", "python_module_presence"])
        status = (
            "available"
            if _has_env_value(env_map, "FAL_KEY") and module_available("fal_client")
            else "needs_setup"
        )
        hint = (
            "fal 云增强依赖已就绪。"
            if status == "available"
            else "需要先配置 fal 云端凭据并安装客户端依赖。"
        )
    elif backend == "fal_comfy":
        checked_by.extend(
            [
                "environment_presence",
                "python_module_presence",
                "workflow_template_presence",
            ]
        )
        status = (
            "available"
            if _has_env_value(env_map, "FAL_KEY")
            and module_available("fal_client")
            and module_available("PIL")
            and module_available("numpy")
            and _template_exists(root, enhance_cfg, "fal_comfy", "fal_comfy_workflow_template.json")
            else "needs_setup"
        )
        hint = (
            "fal Comfy 云增强依赖已就绪。"
            if status == "available"
            else "需要先完成 fal Comfy 云端凭据、客户端依赖和工作流模板配置。"
        )
    elif backend == "comfyui":
        checked_by.extend(
            [
                "environment_presence",
                "python_module_presence",
                "workflow_template_presence",
            ]
        )
        status = (
            "available"
            if _comfy_root_present(env_map, enhance_cfg)
            and all(module_available(name) for name in ("requests", "PIL", "cv2", "numpy"))
            and _template_exists(root, enhance_cfg, "comfyui", "comfyui_workflow_template.json")
            else "needs_setup"
        )
        hint = (
            "本地 ComfyUI 增强依赖已就绪。"
            if status == "available"
            else "需要先准备本地 ComfyUI 目录、Python 依赖和工作流模板。"
        )
    else:
        status = "unknown"
        hint = "该 provider preset 没有专用健康规则；保持只读展示，执行前仍需人工确认。"

    return {
        "provider_preset": preset_id,
        "status": status,
        "ordinary_user_status": _ordinary_status(status),
        "setup_hint": hint,
        "checked_by": checked_by,
        "required_capabilities": required_capabilities,
        "mutates_pipeline_state": False,
        "executes_enhancement": False,
        "does_not_scan_directories": True,
    }


def _required_capabilities(preset: dict[str, Any]) -> list[str]:
    backend = preset.get("backend")
    capabilities: list[str] = []
    if preset.get("requires_cloud_key"):
        capabilities.append("cloud_credentials")
    if backend in {"fal", "fal_comfy"}:
        capabilities.append("python_client")
    if backend in {"fal_comfy", "comfyui"}:
        capabilities.append("workflow_template")
    if backend == "comfyui":
        capabilities.extend(["local_gpu_runtime", "local_service"])
    if backend == "engineering":
        capabilities.append("local_pipeline")
    if not capabilities:
        capabilities.append("project_configuration")
    return capabilities


def _ordinary_status(status: Status) -> str:
    labels = {
        "available": "可用",
        "needs_setup": "需要配置",
        "unknown": "未知",
    }
    return labels.get(status, "未知")


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _load_enhance_config(root: Path) -> dict[str, Any]:
    cfg_path = root / "pipeline_config.json"
    if not cfg_path.is_file():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    enhance = data.get("enhance")
    return enhance if isinstance(enhance, dict) else {}


def _gemini_script_exists(root: Path, env_map: Mapping[str, str]) -> bool:
    configured = env_map.get("GEMINI_GEN_PATH", "")
    if configured and Path(configured).is_file():
        return True
    return (root / "gemini_gen.py").is_file()


def _gemini_config_present(home_dir: Path) -> bool:
    cfg_path = home_dir / ".claude" / "gemini_image_config.json"
    if not cfg_path.is_file():
        return False
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("api_key") and data.get("api_base_url"))


def _has_env_value(env_map: Mapping[str, str], name: str) -> bool:
    return bool(str(env_map.get(name, "")).strip())


def _template_exists(
    root: Path,
    enhance_cfg: dict[str, Any],
    backend: str,
    default_name: str,
) -> bool:
    backend_cfg = enhance_cfg.get(backend)
    if not isinstance(backend_cfg, dict):
        backend_cfg = {}
    configured = str(backend_cfg.get("workflow_template") or "")
    candidate = Path(configured) if configured else Path("templates") / default_name
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.is_file()


def _comfy_root_present(
    env_map: Mapping[str, str],
    enhance_cfg: dict[str, Any],
) -> bool:
    comfy_cfg = enhance_cfg.get("comfyui")
    if not isinstance(comfy_cfg, dict):
        comfy_cfg = {}
    candidates = [
        str(comfy_cfg.get("root") or ""),
        str(env_map.get("COMFYUI_ROOT", "") or ""),
    ]
    return any(Path(candidate).is_dir() for candidate in candidates if candidate)
