from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_PROVIDER_PRESET = "default"


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
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
            "ordinary_user_label": self.label,
            "backend": self.backend,
            "model": self.model,
            "requires_cloud_key": self.requires_cloud_key,
            "argv_suffix": self.argv_suffix(),
        }


_PRESETS = (
    ProviderPreset(
        id="default",
        label="使用项目增强配置",
    ),
    ProviderPreset(
        id="engineering",
        label="本地工程预览",
        backend="engineering",
    ),
    ProviderPreset(
        id="gemini",
        label="Gemini 云增强",
        backend="gemini",
        requires_cloud_key=True,
    ),
    ProviderPreset(
        id="fal",
        label="fal 云增强",
        backend="fal",
        requires_cloud_key=True,
    ),
    ProviderPreset(
        id="fal_comfy",
        label="fal Comfy 云增强",
        backend="fal_comfy",
        requires_cloud_key=True,
    ),
    ProviderPreset(
        id="comfyui",
        label="本地 ComfyUI 增强",
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
