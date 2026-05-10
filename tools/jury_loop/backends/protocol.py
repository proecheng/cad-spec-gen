"""BackendAdapter Protocol + 4 类异常分类 + Request/Response NamedTuple。

按 spec §2.1：所有内置 + 用户 plugin adapter 必实现此 Protocol。
4 类异常映射到 sidecar.errors[].kind 供 orchestrator 写 retry_failed 子状态。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple, Protocol, runtime_checkable


class BackendRequest(NamedTuple):
    """retry 调用 backend 的请求载荷。"""

    input_image_path: Path
    prompt: str
    params: dict[str, Any]
    base_url: str
    api_key: str
    model_name: str


class BackendResponse(NamedTuple):
    """retry 完成的产物。actual_cost_usd 为 None 时 LoopBudget 用 estimate。"""

    output_image_path: Path
    actual_cost_usd: float | None
    raw_request_summary: dict[str, Any]


@runtime_checkable
class BackendAdapter(Protocol):
    """所有内置 + 用户 plugin 必实现此 Protocol。

    @runtime_checkable 让 isinstance(obj, BackendAdapter) 在运行时工作；
    register_backend() 据此拦截不合规 plugin。
    """

    @property
    def kind(self) -> str:
        ...

    @property
    def known_params(self) -> dict[str, tuple[float | None, float | None]]:
        """该 backend 支持的参数 → (min, max)。(None, None) 表示非数值字段
        （如 openai 的 quality/style/size），rule_table 仅做存在性 + 类型校验，不 clamp。"""
        ...

    def supports_controlnet(self) -> bool:
        ...

    def estimate_cost_usd(self, request: BackendRequest) -> float:
        ...

    def call(self, request: BackendRequest, timeout: float) -> BackendResponse:
        ...


class BackendError(Exception):
    """所有 backend 失败异常的基类；orchestrator catch 此即可。"""


class BackendAuthError(BackendError):
    """API key 无效 / 401 / 403。→ retry_auth_failed 子状态。"""


class BackendRateLimitError(BackendError):
    """429 / Retry-After。→ retry_rate_limited 子状态。"""


class BackendQuotaExceededError(BackendError):
    """402 / billing / insufficient_quota。→ retry_quota_exceeded 子状态。"""


class BackendCallError(BackendError):
    """其他 vendor 错误（HTTP 500 / 解析失败 / 文件写入冲突）。→ retry_failed 兜底。"""
