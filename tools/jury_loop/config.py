"""enhance.jury_loop 段配置 dataclass + 加载器。

按 spec §4.1 锁定字段集（YAGNI，不扩展）：
    - BackendConfig：retry backend 5 字段（kind / base_url / api_key_env / model_name / timeout_s）
    - JuryLoopConfig：顶层 enabled / cost_cap_usd + 嵌套 backend + advanced dict
    - load_jury_loop_config：DRIFT-MAJOR-4 校验顶层与 advanced 同名 key 共存 → ValueError
    - api_key_env 指向不存在的环境变量 → warn 不抛（启动期柔性；首次 retry 调用时再 hard fail）
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# advanced 段允许出现的 5 个 key；这些 key 不应同时出现在顶层（DRIFT-MAJOR-4）
_ADVANCED_KEYS = frozenset(
    {
        "threshold",
        "max_retries",
        "llm_fallback",
        "rule_table_path",
        "score_select_strategy",
    }
)


@dataclass(frozen=True)
class BackendConfig:
    """retry backend 配置（spec §4.1 backend 子段 5 字段）。"""

    kind: str
    base_url: str
    api_key_env: str
    model_name: str
    timeout_s: int


@dataclass(frozen=True)
class JuryLoopConfig:
    """enhance.jury_loop 解析后 dataclass（spec §4.1）。

    - enabled / cost_cap_usd 顶层默认；
    - backend 必填嵌套；
    - advanced 段以 dict 持有（已校验过同名碰撞）。
    """

    enabled: bool
    cost_cap_usd: float
    backend: BackendConfig
    advanced: dict[str, Any] = field(default_factory=dict)


def load_jury_loop_config(d: dict[str, Any]) -> JuryLoopConfig:
    """从 pipeline_config['enhance']['jury_loop'] dict 解析。

    校验：
        - DRIFT-MAJOR-4：顶层 与 advanced 同名 key 共存 → ValueError
        - api_key_env 指向不存在的环境变量 → warn 不抛
          （启动期柔性，首次 retry 调用时再 hard fail）

    未填顶层 enabled/cost_cap_usd 走默认 True/1.5。
    """
    advanced: dict[str, Any] = dict(d.get("advanced", {}))

    # DRIFT-MAJOR-4：顶层与 advanced 同名 key 共存视作配置错误
    collision = set(d.keys()) & _ADVANCED_KEYS
    if collision:
        raise ValueError(
            f"jury_loop 顶层与 advanced 同名 key 共存：{sorted(collision)}"
            f"（请只在 advanced 段配置）"
        )

    backend_dict = d["backend"]
    backend = BackendConfig(
        kind=str(backend_dict["kind"]),
        base_url=str(backend_dict["base_url"]),
        api_key_env=str(backend_dict["api_key_env"]),
        model_name=str(backend_dict["model_name"]),
        timeout_s=int(backend_dict["timeout_s"]),
    )

    # api_key_env 指向的环境变量缺失 → 启动期 warn，不阻塞
    if not os.environ.get(backend.api_key_env):
        log.warning(
            "api_key_env=%s 在当前环境未设置；首次 retry 调用时将 hard fail",
            backend.api_key_env,
        )

    return JuryLoopConfig(
        enabled=bool(d.get("enabled", True)),
        cost_cap_usd=float(d.get("cost_cap_usd", 1.5)),
        backend=backend,
        advanced=advanced,
    )
