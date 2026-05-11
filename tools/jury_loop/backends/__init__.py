"""BackendAdapter 注册表与内置 adapter 自动加载。

启动时调 _register_builtin_adapters() lazy-import 3 个内置实例（防循环依赖）。
用户 plugin 通过 register_backend(adapter) 接入第三方 vendor。
"""
from __future__ import annotations

import importlib
import warnings

from .protocol import (
    BackendAdapter,
    BackendAuthError,
    BackendCallError,
    BackendError,
    BackendQuotaExceededError,
    BackendRateLimitError,
    BackendRequest,
    BackendResponse,
)

__all__ = [
    "BACKEND_REGISTRY",
    "register_backend",
    "BackendAdapter",
    "BackendError",
    "BackendAuthError",
    "BackendRateLimitError",
    "BackendQuotaExceededError",
    "BackendCallError",
    "BackendRequest",
    "BackendResponse",
]

BACKEND_REGISTRY: dict[str, BackendAdapter] = {}


def register_backend(adapter: BackendAdapter) -> None:
    """注册一个 backend adapter；以 adapter.kind 作 key。

    Raises:
        TypeError: adapter 未实现 BackendAdapter Protocol（@runtime_checkable）。
        ValueError: adapter.kind 已在 BACKEND_REGISTRY，防 plugin 误覆盖内置。
    """
    if not isinstance(adapter, BackendAdapter):
        raise TypeError(
            f"adapter 必须实现 BackendAdapter Protocol，得到 {type(adapter).__name__}"
        )
    kind = adapter.kind
    if kind in BACKEND_REGISTRY:
        raise ValueError(
            f"backend kind {kind!r} 已注册；不允许重复（内置 / plugin 冲突？）"
        )
    BACKEND_REGISTRY[kind] = adapter


# 内置 adapter 模块 → 类名映射（Task 2.5.2/2.5.3/2.5.4 创建）
_BUILTIN_ADAPTERS: tuple[tuple[str, str], ...] = (
    (".gemini_chat_image", "GeminiChatImageAdapter"),
    (".openai_images_edit", "OpenAIImagesEditAdapter"),
    (".comfyui_workflow_cloud", "ComfyUIWorkflowCloudAdapter"),
)


def _register_builtin_adapters() -> None:
    """启动一次：lazy import 3 个内置 adapter 注册到 BACKEND_REGISTRY。

    模块缺失时仅 warn 不抛——Task 2.5.1 落地后 2.5.2/3/4 未做时本包仍可 import。
    所有 adapter 到位后此函数静默成功；plugin 用 register_backend 单独注册。
    """
    for module_name, class_name in _BUILTIN_ADAPTERS:
        try:
            module = importlib.import_module(module_name, package=__name__)
            adapter_cls = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            warnings.warn(
                f"内置 adapter {module_name}.{class_name} 未加载：{e}",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        register_backend(adapter_cls())


_register_builtin_adapters()
