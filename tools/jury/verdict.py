"""LLM 文本 → 结构化 ViewVerdict（纯函数，无副作用）。

设计约束：
- 解析失败（非 JSON / 非 dict / 缺 semantic_checks）→ verdict=needs_review，仍返回 ViewVerdict。
- photoreal_score 越界 → clamp 到 [0, 100]，记入 parse_anomalies "clamped"。
- reason 含控制字符 / ANSI escape / 超长 → 净化截断，记入 parse_anomalies "reason_sanitized"。
- semantic_checks 5 个 bool key 缺失或类型错 → parse_anomalies "content_keys_mismatch" + needs_review。
- finish_reason ∉ {"stop", None} → parse_anomalies "finish_reason_invalid" + needs_review。
- 决策白名单：parse_anomalies ⊆ {reason_sanitized, clamped} 时仍走 5 bool + score 阈值正常路径。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal


_REASON_MAX_CHARS = 80
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_REQUIRED_BOOL_KEYS: tuple[str, ...] = (
    "geometry_preserved",
    "material_consistent",
    "photorealistic",
    "no_extra_parts",
    "no_missing_parts",
)


@dataclass(frozen=True)
class ViewVerdict:
    """单视角裁决结果（不可变）。"""

    semantic_checks: dict[str, bool]
    photoreal_score: int
    reason: str
    parse_status: Literal["ok"]
    parse_anomalies: list[str] = field(default_factory=list)
    verdict: Literal["accepted", "preview", "needs_review"] = "accepted"


def parse_view_verdict(
    content_text: str,
    *,
    finish_reason: str | None = "stop",
    min_photoreal_score: int = 60,
) -> ViewVerdict:
    """解析 LLM 返回的 content_text + finish_reason → ViewVerdict。

    finish_reason 校验：仅 ``{"stop", None}`` 视为正常。
    """
    anomalies: list[str] = []

    # finish_reason 校验
    if finish_reason not in {"stop", None}:
        anomalies.append("finish_reason_invalid")

    # JSON 解析
    try:
        payload = json.loads(content_text)
    except json.JSONDecodeError:
        anomalies.append("content_not_json")
        return _make_needs_review_verdict(anomalies)

    if not isinstance(payload, dict):
        anomalies.append("content_not_json")
        return _make_needs_review_verdict(anomalies)

    # semantic_checks 字段集
    raw_checks = payload.get("semantic_checks")
    if not isinstance(raw_checks, dict):
        anomalies.append("missing_content")
        return _make_needs_review_verdict(anomalies)

    checks: dict[str, bool] = {}
    keys_ok = True
    for key in _REQUIRED_BOOL_KEYS:
        val = raw_checks.get(key)
        if not isinstance(val, bool):
            keys_ok = False
            checks[key] = False
        else:
            checks[key] = val
    if not keys_ok:
        anomalies.append("content_keys_mismatch")

    # photoreal_score clamp [0, 100]
    raw_score = payload.get("photoreal_score", 0)
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        # bool 是 int 子类，必须先排除；非数值视为字段类型错
        if "content_keys_mismatch" not in anomalies:
            anomalies.append("content_keys_mismatch")
        score = 0
    else:
        score_int = int(raw_score)
        if score_int < 0 or score_int > 100:
            anomalies.append("clamped")
            score = max(0, min(100, score_int))
        else:
            score = score_int

    # reason 控制字符 + ANSI escape + 80 字截
    raw_reason_obj = payload.get("reason", "")
    raw_reason = str(raw_reason_obj) if raw_reason_obj is not None else ""
    sanitized = _ANSI_ESCAPE_RE.sub("", raw_reason)
    sanitized = _CONTROL_CHARS_RE.sub("", sanitized)
    sanitized = sanitized.replace("\n", " ").strip()
    if sanitized != raw_reason:
        anomalies.append("reason_sanitized")
    if len(sanitized) > _REASON_MAX_CHARS:
        sanitized = sanitized[:_REASON_MAX_CHARS]
        if "reason_sanitized" not in anomalies:
            anomalies.append("reason_sanitized")

    # 决策：parse_anomalies ⊆ {reason_sanitized, clamped} → 仍可走 5 boolean + score 阈值
    serious = set(anomalies) - {"reason_sanitized", "clamped"}
    verdict: Literal["accepted", "preview", "needs_review"]
    if serious:
        verdict = "needs_review"
    elif not all(checks.values()):
        verdict = "preview"
    elif score < min_photoreal_score:
        verdict = "preview"
    else:
        verdict = "accepted"

    return ViewVerdict(
        semantic_checks=checks,
        photoreal_score=score,
        reason=sanitized,
        parse_status="ok",
        parse_anomalies=anomalies,
        verdict=verdict,
    )


def _make_needs_review_verdict(anomalies: list[str]) -> ViewVerdict:
    """构造严重错误情况下的 needs_review ViewVerdict（5 bool 全 False / score=0 / reason 空）。"""
    return ViewVerdict(
        semantic_checks={k: False for k in _REQUIRED_BOOL_KEYS},
        photoreal_score=0,
        reason="",
        parse_status="ok",
        parse_anomalies=anomalies,
        verdict="needs_review",
    )
