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
# matches_spec 为 derived field —— 从 features_status aggregate 推导（all visible），
# 不参与 keys_ok 校验。保持 _REQUIRED_BOOL_KEYS 不变是 spec §8 不变量 #1（不动现有 5 key 语义）
# 与 §6 验收 #1（向后兼容：无 features_status 老 fixture 不被升级为 needs_review）的硬保障。


@dataclass(frozen=True)
class ViewVerdict:
    """单视角裁决结果（不可变）。"""

    semantic_checks: dict[str, bool]
    photoreal_score: int
    reason: str
    parse_status: Literal["ok"]
    parse_anomalies: list[str] = field(default_factory=list)
    verdict: Literal["accepted", "preview", "needs_review"] = "accepted"
    features_status: list[dict[str, object]] = field(default_factory=list)


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

    # features_status aggregation → matches_spec (derived field, 不进 _REQUIRED_BOOL_KEYS)
    raw_features = payload.get("features_status", [])
    features_status: list[dict[str, object]] = []
    if not isinstance(raw_features, list):
        # 非 list（如 dict / str / int）→ 空 list + anomaly；matches_spec 退化为 True（向后兼容）
        anomalies.append("features_status_invalid")
        checks["matches_spec"] = True
    elif not raw_features:
        # 空 list（含老 fixture 无字段默认 []）→ matches_spec 默认 True（向后兼容）
        checks["matches_spec"] = True
    else:
        # 有 features → all visible 才 True；非 dict 条目跳过（容忍）
        valid_features = [f for f in raw_features if isinstance(f, dict)]
        features_status = valid_features
        checks["matches_spec"] = all(bool(f.get("visible", False)) for f in valid_features)

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

    # Task 9 v2.37：matches_spec=False (features_status 非空 + 任一 invisible) → 升级 needs_review
    # 触发 jury_loop retry 路径（spec §3 F5）。features_status 为空（老 fixture）matches_spec=True
    # → has_real_feature_fail=False → 决策维持原态（向后兼容硬保障）。
    has_real_feature_fail = bool(features_status) and not checks.get(
        "matches_spec", True
    )
    if has_real_feature_fail and "matches_spec_failed" not in anomalies:
        anomalies.append("matches_spec_failed")

    # 决策：parse_anomalies ⊆ {reason_sanitized, clamped} → 仍可走 5 boolean + score 阈值
    # Task 9：matches_spec_failed 是"真有 spec 不符"信号，与 reason_sanitized/clamped 同
    # 属白名单——单独走 needs_review 分支，不当 serious 处理（serious 强制 5 bool 全 False
    # 报废 verdict）。
    serious = set(anomalies) - {"reason_sanitized", "clamped", "matches_spec_failed"}
    verdict: Literal["accepted", "preview", "needs_review"]
    if serious:
        verdict = "needs_review"
    elif has_real_feature_fail:
        # matches_spec FAIL → needs_review → orchestrator retry 路径（Task 9 集成）
        verdict = "needs_review"
    elif not all(checks.values()):
        # v2.37.9 §11-N6 改动 1e — semantic_check=False 升 needs_review 触发 retry (rev 4 真 vendor 实测 fix)
        anomalies = anomalies + ["semantic_checks_failed"]
        verdict = "needs_review"
    elif score < min_photoreal_score:
        # v2.37.9 §11-N6 — photoreal<60 升 needs_review 触发 retry 闭环（与 matches_spec_failed 同 retry path）
        anomalies = anomalies + ["photoreal_below_threshold"]
        verdict = "needs_review"
    else:
        verdict = "accepted"

    return ViewVerdict(
        semantic_checks=checks,
        photoreal_score=score,
        reason=sanitized,
        parse_status="ok",
        parse_anomalies=anomalies,
        verdict=verdict,
        features_status=features_status,
    )


@dataclass(frozen=True)
class RunVerdict:
    """整 photo3d-jury 进程的 jury-level summary (v2.37+)。

    聚合多视角 ViewVerdict 给 prompt_rewriter 用：
    - overall_matches_spec: 所有视角 matches_spec 都 True 才 True
    - per_view_failed_features: {view_id: [feature_id]} 列出每个视角的 invisible feature
    """

    view_verdicts: dict[str, ViewVerdict]
    overall_matches_spec: bool
    per_view_failed_features: dict[str, list[str]] = field(default_factory=dict)


def aggregate_run_verdict(view_verdicts: dict[str, ViewVerdict]) -> RunVerdict:
    """聚合多视角 verdict → RunVerdict（spec §5.2.2 F1 修复落地）。

    - ``overall_matches_spec`` = all(view.semantic_checks.get("matches_spec", True)
      for view)；用 .get(default=True) 防御性兜底，覆盖 v2.37.1 历史 5-key 存档反
      序列化场景（spec §6 不变量 #11）。v2.37.2 起 _make_needs_review_verdict 也
      返回 6-key 含 matches_spec=True，与 .get 默认数学等价（零行为变化）。
    - ``per_view_failed_features`` = {view_id: [feature_id]} 仅含至少 1 invisible
      feature 的 view，给 prompt_rewriter (Task 4) 提供 per_view_failed_features
      反馈数据。
    """
    overall = all(
        v.semantic_checks.get("matches_spec", True) for v in view_verdicts.values()
    )
    failed: dict[str, list[str]] = {}
    for view_id, v in view_verdicts.items():
        missing = [
            str(f["feature_id"])
            for f in v.features_status
            if isinstance(f, dict) and not f.get("visible", True) and "feature_id" in f
        ]
        if missing:
            failed[view_id] = missing
    return RunVerdict(
        view_verdicts=view_verdicts,
        overall_matches_spec=overall,
        per_view_failed_features=failed,
    )


def _make_needs_review_verdict(anomalies: list[str]) -> ViewVerdict:
    """构造严重错误情况下的 needs_review ViewVerdict（5 bool 全 False / score=0 / reason 空）。

    v2.37.2 §11 #1：加 matches_spec=True 第 6 key，与 normal path 形态一致；
    与 aggregate_run_verdict line 199 的 .get("matches_spec", True) 默认在所有现有
    调用路径上数学等价 → 零行为变化。
    semantic_checks dict key 顺序固定为 _REQUIRED_BOOL_KEYS + ('matches_spec',)
    末位（spec §6 #11 + plan task 必 cover Q6）。
    """
    semantic_checks: dict[str, bool] = {k: False for k in _REQUIRED_BOOL_KEYS}
    semantic_checks["matches_spec"] = True
    return ViewVerdict(
        semantic_checks=semantic_checks,
        photoreal_score=0,
        reason="",
        parse_status="ok",
        parse_anomalies=anomalies,
        verdict="needs_review",
    )
