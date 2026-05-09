"""jury 配置解析 — JuryProfile / JuryCaps dataclass + 估价表 + base_url 智能。

不发 HTTP / 不读图 / 解析后立即丢 raw dict 防 key 通过返回值泄漏。
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class JuryConfigError(Exception):
    """业务输入错（exit=2）。"""


class JuryConfigSchemaError(JuryConfigError):
    """schema 不识别（exit=2 子类）。"""


@dataclass(frozen=True)
class JuryProfile:
    id: str
    kind: str
    api_base_url: str  # 已 normalize（rstrip "/" + smart /v1）
    api_key: str
    model: str
    cost_per_call_usd: Optional[float]


@dataclass(frozen=True)
class JuryCaps:
    max_image_bytes: int
    max_n_views: int
    min_photoreal_score: int


# 内置估价表：model 模式（前缀匹配按行序首次命中）→ cost_per_call_usd 默认值
# 与真实 vendor pricing 可能 ±50% 偏差，仅作 v1 约值兜底
BUILTIN_MODEL_COST_USD: list[tuple[str, float]] = [
    ("gpt-4o", 0.020),
    ("gpt-4-turbo", 0.030),
    ("gemini-2.5-flash", 0.005),
    ("gemini-1.5-flash", 0.005),
    ("gemini-2.5-pro", 0.015),
    ("gemini-1.5-pro", 0.015),
    ("claude-3", 0.025),
    ("claude-vision", 0.025),
]
BUILTIN_MODEL_COST_USD_BUILT_AT = "2026-05-08"

_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")
_DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_DEFAULT_MAX_N_VIEWS = 32
_DEFAULT_MIN_PHOTOREAL_SCORE = 60


def load_jury_config(config_path: Path) -> tuple[JuryProfile, JuryCaps]:
    """读 + 校验 config，返 (active JuryProfile, JuryCaps)。原 dict 立即丢弃。"""
    if not config_path.exists():
        raise JuryConfigError(f"未找到 jury 配置文件 {config_path}")
    raw = json.loads(config_path.read_text(encoding="utf-8"))

    schema_version = raw.get("schema_version")
    if schema_version not in {1, 2}:
        raise JuryConfigSchemaError(
            f"schema_version={schema_version} 不被支持（仅 1 或 2）"
        )
    if schema_version == 2:
        sys.stderr.write(
            "警告：本 jury 版本是 v1，忽略 schema_version=2 中的未知字段。\n"
        )

    active_id = raw.get("active_profile_id")
    profiles_raw = raw.get("profiles", [])
    if not isinstance(profiles_raw, list) or not profiles_raw:
        raise JuryConfigError("profiles 必须是非空列表")

    seen_ids: set[str] = set()
    active_profile_raw = None
    for p in profiles_raw:
        pid = p.get("id", "")
        if not _PROFILE_ID_RE.match(pid):
            raise JuryConfigError(
                f"profile id `{pid}` 不合法（首字符非 ASCII 字母/数字/下划线、长度 > 64、或含非法字符）"
            )
        if pid in seen_ids:
            raise JuryConfigError(f"profile id `{pid}` 重复")
        seen_ids.add(pid)
        if pid == active_id:
            active_profile_raw = p

    if active_profile_raw is None:
        raise JuryConfigError(f"active_profile_id `{active_id}` 不在 profiles 中")

    profile = _parse_profile(active_profile_raw)
    caps = _parse_caps(raw)
    # raw 立即丢弃；不返回 dict 防 key 泄漏
    del raw, profiles_raw, active_profile_raw
    return profile, caps


def _parse_profile(p: dict[str, object]) -> JuryProfile:
    """解析单 profile + 字段校验 + base_url 智能 normalize。"""
    if p.get("kind") not in {"openai_compat"}:
        raise JuryConfigError(f"kind={p.get('kind')} 不被支持（v1 仅 openai_compat）")
    api_base_url = str(p.get("api_base_url", "")).rstrip("/")
    if not api_base_url.startswith("https://"):
        raise JuryConfigError(f"api_base_url 必须 https:// 开头，得到 `{api_base_url}`")
    parsed = urlparse(api_base_url)
    if not parsed.hostname:
        raise JuryConfigError(f"api_base_url hostname 不能为空：{api_base_url}")
    # 智能 /v1：含则保留，不含则追加（仅 kind=openai_compat）
    # 边界：仅识别后缀 `/v1`；vendor 用 `/v1beta` / `/v2` 等变体路径需用户填完整 base_url
    # （避免误追加 → `/v1beta/v1` 错路径，会被 LLM 调用 4xx fail-fast 暴露而非 silent corruption）
    if not api_base_url.endswith("/v1") and "/v1/" not in api_base_url + "/":
        api_base_url = api_base_url + "/v1"

    api_key = str(p.get("api_key", "")).strip()
    if not api_key:
        raise JuryConfigError("api_key 不能为空")
    model = str(p.get("model", "")).strip()
    if not model:
        raise JuryConfigError("model 不能为空")

    cost_raw = p.get("cost_per_call_usd")
    cost: Optional[float]
    if cost_raw is None:
        cost = lookup_builtin_cost(model)
    else:
        if (
            not isinstance(cost_raw, (int, float))
            or not math.isfinite(cost_raw)
            or cost_raw < 0
            or cost_raw >= 1000
        ):
            raise JuryConfigError(
                f"cost_per_call_usd={cost_raw} 不合法（必须 finite + 0 <= x < 1000）"
            )
        cost = float(cost_raw)

    return JuryProfile(
        id=str(p["id"]),
        kind=str(p["kind"]),
        api_base_url=api_base_url,
        api_key=api_key,
        model=model,
        cost_per_call_usd=cost,
    )


def _parse_caps(raw: dict[str, object]) -> JuryCaps:
    max_image_bytes = raw.get("max_image_bytes", _DEFAULT_MAX_IMAGE_BYTES)
    max_n_views = raw.get("max_n_views", _DEFAULT_MAX_N_VIEWS)
    min_photoreal_score = raw.get("min_photoreal_score", _DEFAULT_MIN_PHOTOREAL_SCORE)

    if not isinstance(max_image_bytes, int) or not (
        1024 <= max_image_bytes <= (1 << 30)
    ):
        raise JuryConfigSchemaError(
            f"max_image_bytes={max_image_bytes} 必须 int [1024, 1<<30]"
        )
    if not isinstance(max_n_views, int) or not (1 <= max_n_views <= 1024):
        raise JuryConfigSchemaError(f"max_n_views={max_n_views} 必须 int [1, 1024]")
    if not isinstance(min_photoreal_score, int) or not (
        0 <= min_photoreal_score <= 100
    ):
        raise JuryConfigSchemaError(
            f"min_photoreal_score={min_photoreal_score} 必须 int [0, 100]"
        )

    return JuryCaps(
        max_image_bytes=max_image_bytes,
        max_n_views=max_n_views,
        min_photoreal_score=min_photoreal_score,
    )


def lookup_builtin_cost(model: str) -> Optional[float]:
    """按表中行序首次前缀命中。"""
    for prefix, cost in BUILTIN_MODEL_COST_USD:
        if model.startswith(prefix):
            return cost
    return None
