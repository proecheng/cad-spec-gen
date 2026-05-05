from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_PROVIDER_PRESET = "default"


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    ordinary_user_title: str
    ordinary_user_summary: str
    recommended_when: str
    requires_setup: bool = False
    backend: str | None = None
    model: str | None = None
    requires_cloud_key: bool = False

    def argv_suffix(self) -> list[str]:
        suffix: list[str] = []
        if self.backend:
            suffix.extend(["--backend", self.backend])
        if self.model:
            suffix.extend(["--model", self.model])
        return suffix

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "ordinary_user_label": self.ordinary_user_title,
            "ordinary_user_title": self.ordinary_user_title,
            "ordinary_user_summary": self.ordinary_user_summary,
            "recommended_when": self.recommended_when,
            "requires_setup": self.requires_setup,
            "backend": self.backend,
            "model": self.model,
            "requires_cloud_key": self.requires_cloud_key,
            "argv_suffix": self.argv_suffix(),
        }


_PRESETS = (
    ProviderPreset(
        id="default",
        label="使用项目增强配置",
        ordinary_user_title="默认：使用项目增强配置",
        ordinary_user_summary="沿用当前项目已经配置好的增强方式，适合不想选择具体后端的普通用户。",
        recommended_when="不确定选哪个，或项目配置已经由团队维护时。",
    ),
    ProviderPreset(
        id="engineering",
        label="本地工程预览",
        ordinary_user_title="本地工程预览",
        ordinary_user_summary="离线生成更清晰的工程预览图，不依赖云端 key，适合先检查结构和视角。",
        recommended_when="需要快速、可控、低成本地做工程预览和结构复查时。",
        backend="engineering",
    ),
    ProviderPreset(
        id="gemini",
        label="Gemini 云增强",
        ordinary_user_title="Gemini 云增强",
        ordinary_user_summary="使用 Gemini 云端图像增强，适合追求更强照片感且已配置云端访问的场景。",
        recommended_when="已经配置 Gemini key/base URL，并愿意使用云增强时。",
        requires_setup=True,
        backend="gemini",
        requires_cloud_key=True,
    ),
    ProviderPreset(
        id="fal",
        label="fal 云增强",
        ordinary_user_title="fal 云增强",
        ordinary_user_summary="使用 fal 云端增强，适合已经接入 fal 服务并需要云端生成速度的场景。",
        recommended_when="已经配置 fal key，并希望使用 fal 的云端图像能力时。",
        requires_setup=True,
        backend="fal",
        requires_cloud_key=True,
    ),
    ProviderPreset(
        id="fal_comfy",
        label="fal Comfy 云增强",
        ordinary_user_title="fal Comfy 云增强",
        ordinary_user_summary="使用 fal 托管的 Comfy 工作流增强，适合团队已有对应工作流配置的场景。",
        recommended_when="已经配置 fal Comfy 工作流，并需要云端 Comfy 风格增强时。",
        requires_setup=True,
        backend="fal_comfy",
        requires_cloud_key=True,
    ),
    ProviderPreset(
        id="comfyui",
        label="本地 ComfyUI 增强",
        ordinary_user_title="本地 ComfyUI 增强",
        ordinary_user_summary="使用本机 ComfyUI 工作流增强，适合已搭好本地 GPU/ComfyUI 环境的用户。",
        recommended_when="本机已有 ComfyUI 服务和工作流，想在本地做更强增强时。",
        requires_setup=True,
        backend="comfyui",
    ),
)

_PRESETS_BY_ID = {preset.id: preset for preset in _PRESETS}


def public_provider_presets() -> list[dict[str, Any]]:
    return [preset.public_dict() for preset in _PRESETS]


def public_provider_preset(preset_id: str | None) -> dict[str, Any] | None:
    preset = _PRESETS_BY_ID.get(preset_id or DEFAULT_PROVIDER_PRESET)
    return preset.public_dict() if preset else None


def trusted_provider_argv_suffix(preset_id: str | None) -> list[str]:
    preset = _PRESETS_BY_ID.get(preset_id or DEFAULT_PROVIDER_PRESET)
    if preset is None:
        raise ValueError(f"unknown provider preset: {preset_id}")
    return preset.argv_suffix()
