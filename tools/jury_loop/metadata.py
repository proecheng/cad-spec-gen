"""sidecar metadata schema + 路径净化 + 写盘 — Task 4.2（A-3 + SEC-MAJOR-2 + SEC-MINOR-2）。

按 spec §4.4：
- 锁 22 字段 + 嵌套 baseline / retry，字段顺序与 spec 块定义一致。
- 写盘前必经路径净化 (`_validate_view_basename`) 与 secrets 净化
  (`tools.jury_loop.secrets_scrubber.scrub_secrets`)。
- 5 状态形态共用 `write_sidecar`，通过 `_STATUS_DEFAULTS` 表填默认值；
  调用方显式参数覆盖默认。
- `write_degraded_sidecar` 给 cmd_enhance 视角级异常隔离用（spec line 261-265）。

设计选择：
- 用普通 dict + `_FIELD_ORDER` 列表锁顺序而非 dataclass：22 个字段含 4 层嵌套
  且大量为 `Optional`，dataclass 表达不如 dict-of-dict 直接；Python 3.7+ dict
  保序天然满足 spec §4.4 字段顺序约束。
- `loop_status_zh` 由 `_LOOP_STATUS_ZH_MAP` 机器映射（spec §4.6 锁文案，禁自由翻译）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

from tools.jury_loop.secrets_scrubber import scrub_secrets


class _MissingType:
    """Sentinel 类型：用于区分"调用方未传"与"调用方显式传 None"。

    经典 Python 默认值难题：`x: int | None = None` 无法表达"未传 → 走 default
    形态规则；显式 None → force_retry 形态实际数值为 null"。引入 sentinel
    类型后联合类型 `int | None | _MissingType` 可类型安全表达三态。
    """

    _instance: "_MissingType | None" = None

    def __new__(cls) -> "_MissingType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


_MISSING: Final[_MissingType] = _MissingType()


# ---------------------------------------------------------------------------
# Schema 字段顺序（spec §4.4 块定义保序）
# ---------------------------------------------------------------------------

_FIELD_ORDER: tuple[str, ...] = (
    "$schema_version",
    "view",
    "backend",
    "loop_eligible",
    "loop_status",
    "loop_skipped_reason",
    "delivered_kind",
    "baseline",
    "retry",
    "tags_parsed",
    "rules_hit",
    "rules_missed_tags",
    "llm_fallback_used",
    "prompt_addons_applied",
    "param_overrides_applied",
    "user_friendly_summary",
    "loop_status_zh",
    "retry_score_delta",
    "delivered_score_delta",
    "extra_cost_usd",
    "warnings",
    "errors",
)


class SidecarSchema:
    """schema 版本与字段顺序常量容器。

    该类不实例化；纯命名空间，便于 import + IDE 跳转。dataclass 化反而增加
    使用复杂度（22 字段含 4 层嵌套且大量 Optional），故保留为类常量。
    """

    SCHEMA_VERSION: int = 1
    FIELD_ORDER: tuple[str, ...] = _FIELD_ORDER


# ---------------------------------------------------------------------------
# loop_status → 中文映射（spec §4.6 锁文案）
# ---------------------------------------------------------------------------

_LOOP_STATUS_ZH_MAP: dict[str, str] = {
    "delivered_baseline": "已交付首轮图（多种原因之一）",
    "delivered_retry": "重试成功，已交付重试图",
    "loop_disabled": "该 backend 不支持闭环优化",
    "above_threshold": "首轮分数已达标，无需重试",
    "cost_capped": "闭环预算耗尽，剩余视角接受首轮图",
    "no_tags_parsed": "评分反馈未识别已知问题，接受首轮图",
    "no_rules_hit_no_llm": "规则库未匹配，AI 兜底已关闭，接受首轮图",
    "jury_unavailable": "AI 评分不可用，接受首轮图",
    "empty_reason": "AI 评分未返回反馈文本，接受首轮图",
    "llm_fallback_failed": "AI 兜底翻译失败，接受首轮图",
    "retry_failed": "重试调用失败，接受首轮图",
    "retry_rate_limited": "服务限流，请稍后重试",
    "retry_quota_exceeded": "服务账户余额不足，请充值后重试",
    "retry_auth_failed": "API key 无效，请检查配置",
}


# ---------------------------------------------------------------------------
# 路径净化（SEC-MAJOR-2）
# ---------------------------------------------------------------------------

#: 合法 view basename：首字符必须字母/数字/下划线（拒前导短横，避免下游 CLI
#: 把 `-V1_enhanced.jpg` 误解为 flag）；后续字符可含连字符；总长 1-64。
_VIEW_BASENAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,63}$")


def _validate_view_basename(view: str) -> str:
    """验证 view 是纯 basename；不通过抛 ValueError。

    拒绝条件：
    - 空串
    - 含 `/` 或 `\\` 路径分隔符
    - 含 `..`
    - POSIX/Windows 绝对路径前缀（`/abs` / `C:\\...`）
    - 字符不在 `[A-Za-z0-9_-]` 范围（避免空格/Unicode/特殊字符意外）

    通过时原样返回 view，方便调用方链式使用。
    """
    if not view:
        raise ValueError("view 不能为空")
    if not _VIEW_BASENAME_PATTERN.fullmatch(view):
        raise ValueError(
            f"view 必须是纯 basename（只含字母/数字/下划线/连字符，长度 1-64）："
            f"拒绝 {view!r}"
        )
    return view


# ---------------------------------------------------------------------------
# 5 状态形态默认字段
# ---------------------------------------------------------------------------

#: spec §4.4 各形态的默认字段集；调用方传参覆盖。
#: 注意 baseline / retry 不在默认表中——形态特定的 verdict 由调用方传入。
_STATUS_DEFAULTS: dict[str, dict[str, Any]] = {
    "loop_disabled": {
        "loop_eligible": False,
        "delivered_kind": "baseline",
        "retry": None,
        "tags_parsed": [],
        "prompt_addons_applied": [],
        "extra_cost_usd": 0,
        "retry_score_delta": None,
        "delivered_score_delta": 0,
        "user_friendly_summary": "该 backend 不支持闭环优化",
    },
    "above_threshold": {
        "delivered_kind": "baseline",
        "retry": None,
        "retry_score_delta": None,
        "delivered_score_delta": 0,
    },
    # delivered_baseline 系列共用：retry=null / score_delta=null/0
    "_delivered_baseline_common": {
        "delivered_kind": "baseline",
        "retry": None,
        "retry_score_delta": None,
        "delivered_score_delta": 0,
    },
}

#: 走 _delivered_baseline_common 默认的 loop_status 集合。
_DELIVERED_BASELINE_STATUSES = frozenset({
    "delivered_baseline",
    "jury_unavailable",
    "empty_reason",
    "no_tags_parsed",
    "no_rules_hit_no_llm",
    "llm_fallback_failed",
    "cost_capped",
    "retry_failed",
    "retry_rate_limited",
    "retry_quota_exceeded",
    "retry_auth_failed",
})


def _resolve_status_defaults(loop_status: str) -> dict[str, Any]:
    """根据 loop_status 取该形态的默认字段集。"""
    if loop_status in _STATUS_DEFAULTS:
        return dict(_STATUS_DEFAULTS[loop_status])
    if loop_status in _DELIVERED_BASELINE_STATUSES:
        return dict(_STATUS_DEFAULTS["_delivered_baseline_common"])
    # delivered_retry / 未识别 status：无形态默认，调用方完全自定义
    return {}


def _build_above_threshold_summary(baseline: dict[str, Any] | None) -> str:
    """spec line 528：'首轮分数 78 已达标，无需重试'。

    注意：`isinstance(True, int)` 在 Python 中为 True；显式排除 bool，避免
    病态输入产生 '首轮分数 True 已达标' 这类无意义文案。
    """
    if baseline:
        score = baseline.get("photoreal_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            return f"首轮分数 {score} 已达标，无需重试"
    return "首轮分数已达标，无需重试"


# ---------------------------------------------------------------------------
# 主写盘函数
# ---------------------------------------------------------------------------


def write_sidecar(
    *,
    view: str,
    render_dir: Path,
    backend: str,
    loop_status: str,
    loop_skipped_reason: str | None = None,
    delivered_kind: str | None = None,
    baseline: dict[str, Any] | None = None,
    retry: dict[str, Any] | None = None,
    tags_parsed: list[str] | None = None,
    rules_hit: list[str] | None = None,
    rules_missed_tags: list[str] | None = None,
    llm_fallback_used: bool = False,
    prompt_addons_applied: list[str] | None = None,
    param_overrides_applied: dict[str, Any] | None = None,
    user_friendly_summary: str | None = None,
    retry_score_delta: int | None | _MissingType = _MISSING,
    delivered_score_delta: int | None | _MissingType = _MISSING,
    extra_cost_usd: float | None | _MissingType = _MISSING,
    warnings: list[str] | None = None,
    errors: list[dict[str, Any]] | None = None,
    loop_eligible: bool | None = None,
) -> Path:
    """写 `<render_dir>/<view>_enhance_meta.json` 并返回路径。

    - `view` 必须是纯 basename，违例抛 ValueError（SEC-MAJOR-2）。
    - 字段顺序按 `_FIELD_ORDER` 锁死（spec §4.4）。
    - `errors[].message_summary` 与 `retry.backend_payload` 写盘前过 `scrub_secrets`
      （SEC-MINOR-2）。
    - 缺省字段按 `_STATUS_DEFAULTS` + loop_status 表填；调用方显式传参覆盖。
    """
    safe_view = _validate_view_basename(view)

    # spec §4.4 line 529-530：delivered_retry 必须配 delivered_kind="retry"
    # （pick_max_jury 与 force_retry 两形态均如此）；否则下游 loop_summary 与
    # photo3d_autopilot 会基于 delivered_kind 误分类。提前拒绝静默不一致。
    if loop_status == "delivered_retry" and delivered_kind != "retry":
        raise ValueError(
            f"loop_status='delivered_retry' 必须显式 delivered_kind='retry'，"
            f"得到 delivered_kind={delivered_kind!r}（spec §4.4 line 529-530）"
        )

    defaults = _resolve_status_defaults(loop_status)

    # 生成最终字段值——调用方显式传入则用之，否则取 defaults，否则给最终缺省。
    payload: dict[str, Any] = {
        "$schema_version": SidecarSchema.SCHEMA_VERSION,
        "view": safe_view,
        "backend": backend,
        "loop_eligible": loop_eligible if loop_eligible is not None
                          else defaults.get("loop_eligible", True),
        "loop_status": loop_status,
        "loop_skipped_reason": loop_skipped_reason,
        "delivered_kind": delivered_kind or defaults.get("delivered_kind", "baseline"),
        "baseline": baseline,
        "retry": _scrub_retry(retry if retry is not None else defaults.get("retry")),
        "tags_parsed": tags_parsed if tags_parsed is not None
                        else defaults.get("tags_parsed", []),
        "rules_hit": rules_hit if rules_hit is not None else [],
        "rules_missed_tags": rules_missed_tags if rules_missed_tags is not None else [],
        "llm_fallback_used": llm_fallback_used,
        "prompt_addons_applied": prompt_addons_applied if prompt_addons_applied is not None
                                   else defaults.get("prompt_addons_applied", []),
        "param_overrides_applied": param_overrides_applied if param_overrides_applied is not None
                                     else {},
        "user_friendly_summary": _resolve_summary(
            loop_status, user_friendly_summary, baseline, defaults
        ),
        "loop_status_zh": _LOOP_STATUS_ZH_MAP.get(loop_status, loop_status),
        "retry_score_delta": (
            defaults.get("retry_score_delta")
            if isinstance(retry_score_delta, _MissingType)
            else retry_score_delta
        ),
        "delivered_score_delta": (
            defaults.get("delivered_score_delta", 0)
            if isinstance(delivered_score_delta, _MissingType)
            else delivered_score_delta
        ),
        "extra_cost_usd": (
            defaults.get("extra_cost_usd", 0)
            if isinstance(extra_cost_usd, _MissingType)
            else extra_cost_usd
        ),
        "warnings": warnings if warnings is not None else [],
        "errors": _scrub_errors(errors if errors is not None else []),
    }

    # 字段顺序锁——按 _FIELD_ORDER 重组（防止上面 dict 字面量顺序漂移）。
    ordered = {key: payload[key] for key in _FIELD_ORDER}

    sidecar_path = render_dir / f"{safe_view}_enhance_meta.json"
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return sidecar_path


def _resolve_summary(
    loop_status: str,
    user_summary: str | None,
    baseline: dict[str, Any] | None,
    defaults: dict[str, Any],
) -> str:
    """生成 user_friendly_summary：调用方显式 > defaults > 动态生成。"""
    if user_summary is not None:
        return user_summary
    if "user_friendly_summary" in defaults:
        return str(defaults["user_friendly_summary"])
    if loop_status == "above_threshold":
        return _build_above_threshold_summary(baseline)
    # delivered_retry / 未识别状态：调用方应当自己拼摘要；保底给空串
    return ""


def _scrub_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """errors[].message_summary 与 user_action_hint 经 scrub_secrets。"""
    scrubbed = []
    for entry in errors:
        scrubbed.append({
            **entry,
            "message_summary": scrub_secrets(entry.get("message_summary", ""), max_len=200),
            "user_action_hint": scrub_secrets(entry.get("user_action_hint", "")),
        })
    return scrubbed


def _scrub_retry(retry: dict[str, Any] | None) -> dict[str, Any] | None:
    """retry.backend_payload 经 scrub_secrets（递归净化 dict 中的 token/Authorization）。"""
    if retry is None:
        return None
    scrubbed = dict(retry)
    if "backend_payload" in scrubbed and scrubbed["backend_payload"] is not None:
        scrubbed["backend_payload"] = scrub_secrets(scrubbed["backend_payload"])
    if "final_prompt" in scrubbed and scrubbed["final_prompt"] is not None:
        scrubbed["final_prompt"] = scrub_secrets(scrubbed["final_prompt"])
    return scrubbed


# ---------------------------------------------------------------------------
# write_degraded_sidecar — cmd_enhance 视角级异常隔离
# ---------------------------------------------------------------------------


def write_degraded_sidecar(
    *,
    view: str,
    render_dir: Path,
    error: BaseException,
) -> Path:
    """cmd_enhance 视角级异常隔离时写降级 sidecar（spec line 261-265）。

    - loop_status="retry_failed"（兜底子状态）。
    - errors[] 含一条记录，message_summary = scrub_secrets(str(error), max_len=200)。
    - 路径净化与 write_sidecar 同条件（SEC-MAJOR-2）。
    """
    return write_sidecar(
        view=view,
        render_dir=render_dir,
        backend="unknown",
        loop_status="retry_failed",
        loop_skipped_reason="cmd_enhance 视角处理时发生未捕获异常",
        baseline=None,
        retry=None,
        errors=[{
            "code": "cmd_enhance_uncaught_exception",
            "message_summary": str(error),
            "user_action_hint": "查看 sidecar.errors[].message_summary 排查；如重复发生请提交 issue",
        }],
        user_friendly_summary="该视角增强中断，已回退首轮图",
    )
