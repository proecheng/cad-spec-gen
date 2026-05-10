"""CP-5 orchestrator：jury→prompt 闭环单视角主入口。

按 spec rev 3（docs/superpowers/specs/2026-05-10-cp5-orchestrator-design.md）实现：
- 单视角原子单元；多视角调度由 cmd_enhance（CP-7）管
- 6 内部 helper：_check_pre_jury_gates / _rename_baseline_as_final / _call_jury_subprocess /
  _classify_backend_error / _apply_overrides / _finalize（按后续 task 增量实现）
- 顶层 Precondition fail-fast：baseline_path 不存在 raise FileNotFoundError；
  view 名注入 raise ValueError（_validate_view_basename）；都不写 sidecar
- 已知失败正常路径写富 sidecar；未知 Exception 调 metadata.write_degraded_sidecar 后 re-raise
"""
from __future__ import annotations

import json as _json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import enhance_budget
from enhance_budget import LoopBudget
from tools.jury.config import JuryProfile
from tools.jury.verdict import ViewVerdict, parse_view_verdict
from tools.jury_loop import llm_fallback, metadata, reason_parser, rule_table
from tools.jury_loop.backends import (
    BACKEND_REGISTRY,
    BackendAuthError,
    BackendCallError,
    BackendError,
    BackendQuotaExceededError,
    BackendRateLimitError,
    BackendRequest,
    BackendResponse,
)
from tools.jury_loop.config import JuryLoopConfig
from tools.jury_loop.metadata import _validate_view_basename
from tools.jury_loop.score_select import (
    STRATEGY_REGISTRY,
    CandidateImage,
)


def _check_pre_jury_gates(backend_kind: str, config: JuryLoopConfig) -> str | None:
    """Gate-1/2 检查（spec §3 [2]）：返 loop_status 字符串或 None。

    - Gate-1：backend_kind 不在 BACKEND_REGISTRY → loop_disabled
    - Gate-2：config.enabled == False → loop_disabled
    - 通过则返 None，进 jury 阶段
    """
    if backend_kind not in BACKEND_REGISTRY:
        return "loop_disabled"
    if not config.enabled:
        return "loop_disabled"
    return None


def _rename_baseline_as_final(
    baseline_path: Path, view: str, render_dir: Path,
) -> Path:
    """父 spec line 165 N-1 决议：Gate-1/2 退出路径 baseline → V<view>_enhanced.jpg。

    跨平台安全：先 dst.unlink(missing_ok=True) 再 src.replace(dst)（父 spec line 270）。
    OSError 向上抛（顶层 try/except 兜）。
    """
    final_path = render_dir / f"{view}_enhanced.jpg"
    final_path.unlink(missing_ok=True)
    Path(baseline_path).replace(final_path)
    return final_path


def _classify_backend_error(exc: BackendError) -> tuple[str, dict[str, str]]:
    """4 路异常分类 → (loop_status, error_entry)（spec rev 3 决议 #10）。

    错误条目（error_entry）字段集（父 spec §4.4 line 511-514）：
    - code: 机器可读分类标识符（backend_auth_error / backend_rate_limited /
      backend_quota_exceeded / backend_call_error / backend_unknown_error）
    - message_summary: 异常字符串截到 200 字（防 sidecar 膨胀）
    - user_action_hint: 中文用户操作提示（父 spec §4.6 BL-3 中文化）

    fallback：未识别 BackendError 子类（仅继承基类未走 4 已知子类） →
    retry_failed + backend_unknown_error，避免 helper 抛异常使 sidecar 写入丢失。
    """
    msg_summary = str(exc)[:200]
    if isinstance(exc, BackendAuthError):
        return ("retry_auth_failed", {
            "code": "backend_auth_error",
            "message_summary": msg_summary,
            "user_action_hint": "API key 无效，请检查配置后重试",
        })
    if isinstance(exc, BackendRateLimitError):
        return ("retry_rate_limited", {
            "code": "backend_rate_limited",
            "message_summary": msg_summary,
            "user_action_hint": "服务限流，请稍后重试",
        })
    if isinstance(exc, BackendQuotaExceededError):
        return ("retry_quota_exceeded", {
            "code": "backend_quota_exceeded",
            "message_summary": msg_summary,
            "user_action_hint": "服务账户余额不足，请充值后重试",
        })
    if isinstance(exc, BackendCallError):
        return ("retry_failed", {
            "code": "backend_call_error",
            "message_summary": msg_summary,
            "user_action_hint": "重试调用失败，请查看 sidecar.errors[]",
        })
    return ("retry_failed", {
        "code": "backend_unknown_error",
        "message_summary": msg_summary,
        "user_action_hint": "未知 backend 错误；请提交 issue 附完整日志",
    })


def _call_jury_subprocess(
    *,
    view: str,
    image_path: Path,
    project_root: Path,
    jury_profile_path: Path,
    timeout_s: int,
) -> tuple[ViewVerdict | None, str | None]:
    """调 photo3d-jury --single-view 子进程，返 (verdict, error_code)。

    spec rev 3 决议 #9：失败时不丢信息——返第二元素 error_code 让上层填 sidecar.errors[]。

    错误码（4 种）：
    - "timeout"：subprocess.TimeoutExpired
    - "exit_nonzero"：returncode != 0
    - "json_parse_failed"：stdout 非 JSON 或 list 形状不符（非 list / len != 1）
    - "needs_review"：parse_view_verdict 返 verdict.verdict == "needs_review"

    注意：CP-6 Task 6.1 才落地 photo3d-jury --single-view flag；CP-5 测试用
    monkeypatch.setattr 整体替换本 helper，生产 path 暂跑不通（spec §1 非目标）。
    """
    cmd = [
        sys.executable, "-m", "tools.photo3d_jury",
        "--single-view", view,
        "--image", str(image_path),
        "--config", str(jury_profile_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=project_root,
            timeout=timeout_s,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return (None, "timeout")
    if proc.returncode != 0:
        return (None, "exit_nonzero")
    try:
        items = _json.loads(proc.stdout)
    except _json.JSONDecodeError:
        return (None, "json_parse_failed")
    if not isinstance(items, list) or len(items) != 1:
        return (None, "json_parse_failed")
    verdict = parse_view_verdict(_json.dumps(items[0]))
    if verdict.verdict == "needs_review":
        return (None, "needs_review")
    return (verdict, None)


def _view_verdict_to_baseline_dict(
    verdict: ViewVerdict, image_path: Path,
) -> dict[str, Any]:
    """ViewVerdict → sidecar.baseline 4 字段投影（父 spec §4.4 line 478-482）。"""
    return {
        "image_path": str(image_path),
        "photoreal_score": verdict.photoreal_score,
        "semantic_checks": dict(verdict.semantic_checks),
        "reason": verdict.reason,
    }


@dataclass(frozen=True)
class LoopResult:
    """单视角闭环结果（最小契约 / spec rev 3 决议 #3）。

    字段集刻意保持最小：
    - final_path：本视角最终交付图（V<view>_enhanced.jpg 绝对路径）
    - loop_status：spec §4.6 enum 14 项之一

    sidecar 是事实来源——cmd_enhance 视角循环结束后读 sidecar 文件聚合 loop_summary，
    不通过 LoopResult 携带 sidecar 内容（防内存与文件双写一致性问题）。
    """

    final_path: Path
    loop_status: str


def _finalize_baseline_only(
    *,
    view: str,
    render_dir: Path,
    backend: str,
    loop_status: str,
    baseline_path: Path,
    baseline: ViewVerdict | None = None,
    errors: list[dict[str, Any]] | None = None,
    local_extra_cost: float = 0,
    tags_parsed: list[str] | None = None,
    warnings: list[str] | None = None,
) -> LoopResult:
    """所有 baseline-only 退出路径共用：rename baseline → V<view>_enhanced.jpg + 写 sidecar。

    spec rev 3 §3 主流程的"baseline 退出"分支统一收口（Gate-3 / 3.5 / 4 / 5 / 6 / 7 / 8 路径）。
    后续 Task 5.1.7+ 复用本 helper。
    """
    final_path = _rename_baseline_as_final(baseline_path, view, render_dir)
    metadata.write_sidecar(
        view=view,
        render_dir=render_dir,
        backend=backend,
        loop_status=loop_status,
        baseline=(
            _view_verdict_to_baseline_dict(baseline, final_path)
            if baseline is not None
            else None
        ),
        retry=None,
        errors=errors or [],
        tags_parsed=tags_parsed or [],
        extra_cost_usd=local_extra_cost,
        warnings=warnings or [],
    )
    return LoopResult(final_path, loop_status)


def _apply_overrides(
    *,
    prompt: str,
    prompt_addons: list[str],
    param_overrides: dict[str, Any],
    base_params: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """spec rev 3 §3 [6]：合并 rule_table.lookup 命中的 addon/override 到 prompt + params。

    返 (new_prompt, retry_params)；不动 rc（rc 由 cmd_enhance 管，本函数只做局部派生）。

    入参契约：
    - ``param_overrides`` 是 ``RuleTableLookupResult.param_overrides``——已被 lookup
      按 backend_kind 过滤 + clamp 后的扁平 ``{pkey: clamped_val}`` dict，不再嵌套
      ``{backend_kind: {...}}``（rule_table.py:235 验证）。

    new_prompt 拼装：
    - prompt_addons 为空 → 原样返回 prompt
    - 非空 → ``prompt + " | " + ", ".join(prompt_addons)``（spec rev 3 决议：addons
      用 ``, `` join，与 prompt 主干用 `` | `` 隔，下游 backend 可直接拼到 system prompt）

    retry_params 合并语义：
    - ``base_params`` 浅合并 ``param_overrides``
    - 同 key rule 赢（spec rev 3 决议 A-1：规则覆盖 base 默认）
    """
    new_prompt = (
        prompt + " | " + ", ".join(prompt_addons)
        if prompt_addons
        else prompt
    )
    retry_params: dict[str, Any] = {
        **base_params,
        **param_overrides,
    }
    return new_prompt, retry_params


def _finalize(
    *,
    pick_image_path: Path,
    baseline_path: Path,
    retry_path: Path,
    view: str,
    render_dir: Path,
) -> Path:
    """spec rev 3 §3 [10]：把选中张 rename 为 V<view>_enhanced.jpg。

    路径策略（父 spec line 165 N-1 决议 + 跨平台 atomic 守门）：
    - dst.unlink(missing_ok=True) 先清旧 final（防 Windows 上 replace 文件已存在拒绝）
    - Path.replace 原子 rename
    - 选 retry：retry_path → final_path；baseline 保留为 V<view>_enhanced_baseline.jpg
      （命名已是该形态，不动）
    - 选 baseline：baseline → final_path；retry 保留为 V<view>_enhanced_retry.jpg
      （命名已是该形态，不动）

    OSError 不 catch 让顶层 try/except 写 degraded sidecar。
    """
    final_path = render_dir / f"{view}_enhanced.jpg"
    final_path.unlink(missing_ok=True)
    if pick_image_path == retry_path:
        Path(retry_path).replace(final_path)
    else:
        Path(baseline_path).replace(final_path)
    return final_path


def _build_retry_dict(
    *,
    retry_path: Path,
    retry_verdict: ViewVerdict | None,
    request: BackendRequest,
    response: BackendResponse,
) -> dict[str, Any]:
    """spec §4.4 line 530/531：sidecar.retry 字段双形态投影。

    形态 1（retry_verdict is None）—— force_retry 策略：
    - photoreal_score / semantic_checks / reason 全 null（未二轮评分）
    - final_prompt：实际发送给 backend 的 prompt（spec line 530）
    - backend_payload：response.raw_request_summary（用户排障用）

    形态 2（retry_verdict 非 None）—— pick_max_jury 策略：
    - retry verdict 完整投影（无论 pick 是 retry 还是 baseline，spec line 531）；
      让用户能在 sidecar 里观测到二轮评分实际分数与原因，即使最终选回 baseline。
    """
    if retry_verdict is None:
        return {
            "image_path": str(retry_path),
            "photoreal_score": None,
            "semantic_checks": None,
            "reason": None,
            "final_prompt": request.prompt,
            "backend_payload": dict(response.raw_request_summary),
        }
    return {
        "image_path": str(retry_path),
        "photoreal_score": retry_verdict.photoreal_score,
        "semantic_checks": dict(retry_verdict.semantic_checks),
        "reason": retry_verdict.reason,
        "final_prompt": request.prompt,
        "backend_payload": dict(response.raw_request_summary),
    }


def _compute_score_deltas(
    *,
    retry_verdict: ViewVerdict | None,
    baseline_verdict: ViewVerdict,
    pick_image_path: Path,
    retry_path: Path,
) -> tuple[int | None, int | None]:
    """spec §4.4 line 503-504：retry/delivered score delta 计算。

    返 (retry_score_delta, delivered_score_delta)：
    - retry_verdict is None（force_retry 策略，未二轮评分）：返 (None, None)，
      让 sidecar 字段保持 null（spec line 530：force_retry 不可比较所以不打分差）
    - retry_verdict 非 None（pick_max_jury 策略，二轮已评）：
      - retry_score_delta = retry.score - baseline.score（可正/0/负，含降分情况）
      - delivered_score_delta：pick==retry 时 = retry_score_delta；
        pick==baseline（保守退回）时 = 0（实际交付的图就是 baseline，无变化）
    """
    if retry_verdict is None:
        return None, None
    retry_delta = retry_verdict.photoreal_score - baseline_verdict.photoreal_score
    delivered_delta = retry_delta if pick_image_path == retry_path else 0
    return retry_delta, delivered_delta


def run_loop_if_eligible(
    *,
    view: str,
    backend_kind: str,
    rc: dict[str, Any],
    baseline_path: Path,
    base_params: dict[str, Any],
    budget: LoopBudget,
    project_root: Path,
    config: JuryLoopConfig,
    jury_profile: JuryProfile,
    jury_profile_path: Path,
) -> LoopResult:
    """单视角 jury→prompt 闭环主入口（详见 spec rev 3 §3）。

    异常处理（rev 3 简化版）：
    - 已知失败（BackendError 4 子类 + jury subprocess 失败）：内部捕获写富 sidecar
    - 未知 Exception：调 metadata.write_degraded_sidecar(view, error) 后 re-raise；
      cmd_enhance 接 Exception 仅 log 不重写 sidecar（防无限循环）
    - FileNotFoundError（baseline_path 不存在）/ ValueError（view 名注入）：fail-fast
      不写 sidecar；cmd_enhance 仅 log + 跳过该视角

    前置条件：
    - `baseline_path.is_file() == True`（不满足 raise FileNotFoundError）
    - `view` 必须通过 `metadata._validate_view_basename`（不通过 raise ValueError）

    返回：LoopResult.final_path 在所有正常路径（含 8 Gate 退出）= V<view>_enhanced.jpg。
    """
    # Step 0：Precondition fail-fast（不写 sidecar）
    # 顺序固定：先校验 baseline 文件存在 → 后校验 view 名安全
    # 调换顺序会导致 view 名注入时尚未检查 baseline 即抛 ValueError，
    # 调试信息缺失（不知 baseline 是否同时缺）
    if not baseline_path.is_file():
        raise FileNotFoundError(f"baseline_path 不存在：{baseline_path}")
    safe_view = _validate_view_basename(view)
    render_dir = baseline_path.parent

    # Gate-1/2：spec §3 [2]
    gate_status = _check_pre_jury_gates(backend_kind, config)
    if gate_status is not None:
        final_path = _rename_baseline_as_final(baseline_path, safe_view, render_dir)
        metadata.write_sidecar(
            view=safe_view,
            render_dir=render_dir,
            backend=backend_kind,
            loop_status=gate_status,
            baseline=None,
            retry=None,
            extra_cost_usd=0,
            loop_eligible=False,  # rev 3 spec §5 #1 / #2 验收锁
        )
        return LoopResult(final_path, gate_status)

    # Step 2: jury 第一次评 baseline（spec rev 3 §3 line 195+）
    verdict, jury_err = _call_jury_subprocess(
        view=safe_view,
        image_path=baseline_path,
        project_root=project_root,
        jury_profile_path=jury_profile_path,
        timeout_s=config.backend.timeout_s,
    )
    if verdict is None:
        # Gate-3：jury 不可用 → jury_unavailable + sidecar.errors[0].code 保留 4 错误码之一
        return _finalize_baseline_only(
            view=safe_view,
            render_dir=render_dir,
            backend=backend_kind,
            loop_status="jury_unavailable",
            baseline_path=baseline_path,
            errors=[{
                "code": jury_err or "unknown",
                "message_summary": f"jury subprocess 调用失败：{jury_err}",
                "user_action_hint": "查看 sidecar.errors[].code 排查",
            }],
            local_extra_cost=0,
        )

    # Gate-3.5：spec rev 3 决议 #11 empty_reason 锁
    # 用 .strip() == "" 而非 == ""，防全空白字符（"\n  \t"）误判为有内容
    if verdict.reason.strip() == "":
        return _finalize_baseline_only(
            view=safe_view,
            render_dir=render_dir,
            backend=backend_kind,
            loop_status="empty_reason",
            baseline_path=baseline_path,
            baseline=verdict,
            local_extra_cost=0,
        )

    # Step 4: above_threshold（spec rev 3 §3 主流程；锁 ≥ 而非 >，spec §5 #5b）
    threshold: int = config.advanced["threshold"]
    if verdict.photoreal_score >= threshold:
        # user_friendly_summary 由 metadata._build_above_threshold_summary
        # 动态生成（含 score 数字，spec §4.4 line 528）；不显式传 summary。
        return _finalize_baseline_only(
            view=safe_view,
            render_dir=render_dir,
            backend=backend_kind,
            loop_status="above_threshold",
            baseline_path=baseline_path,
            baseline=verdict,
            local_extra_cost=0,
        )

    # Step 5: 估算 retry cost + try_spend（spec rev 3 §3 line 218+）
    # Gate-1 已守 backend_kind 在 BACKEND_REGISTRY，此处直取 adapter
    adapter = BACKEND_REGISTRY[backend_kind]
    request = BackendRequest(
        input_image_path=baseline_path,
        prompt=str(rc.get("prompt", "")),
        params=base_params,
        base_url=config.backend.base_url,
        api_key=os.environ.get(config.backend.api_key_env, ""),
        model_name=config.backend.model_name,
    )
    estimate = enhance_budget.estimate_retry_cost(
        adapter,
        request,
        with_jury=(config.advanced["score_select_strategy"] == "pick_max_jury"),
    )
    local_extra_cost: float = 0.0
    if not budget.try_spend(estimate):
        # 预算不够 retry：写 cost_capped；try_spend 返 False 时未扣额度
        return _finalize_baseline_only(
            view=safe_view,
            render_dir=render_dir,
            backend=backend_kind,
            loop_status="cost_capped",
            baseline_path=baseline_path,
            baseline=verdict,
            local_extra_cost=0,
        )
    local_extra_cost += estimate

    # Step 6: tag 解析（spec rev 3 §3 line 226+）
    # 先 load rule_table 取合并后的 tag_dictionary，传给 parse_reason 让用户
    # yaml 扩 tag 也能被识别（spec §5 #8 锁）。rule_table.load_rule_table 的
    # 用户 yaml 路径校验失败会抛 RuleTableLoadError，由顶层 try/except 兜。
    rule_path = config.advanced.get("rule_table_path")
    rule_tbl = rule_table.load_rule_table(
        user_yaml_path=rule_path,
        project_root=project_root,
    )
    sanitized_reason = reason_parser.reason_sanitized(verdict.reason)
    tags = reason_parser.parse_reason(
        sanitized_reason,
        tag_dictionary=rule_tbl.tag_dictionary,
    )
    if not tags:
        # 已知问题集合外的 reason，无法转 prompt addon → 接受首轮图
        return _finalize_baseline_only(
            view=safe_view,
            render_dir=render_dir,
            backend=backend_kind,
            loop_status="no_tags_parsed",
            baseline_path=baseline_path,
            baseline=verdict,
            local_extra_cost=local_extra_cost,
            tags_parsed=[],
        )

    # Step 7: rule_table.lookup + 可选 llm_fallback（spec rev 3 §3 line 234+）
    hits = rule_table.lookup(rule_tbl, tags, backend_kind)
    # matched_tags 已是 set；显式 set() 转换防字段类型未来变更
    misses = tags - set(hits.matched_tags)
    if misses and config.advanced["llm_fallback"]:
        try:
            extra_addons = llm_fallback.translate(
                unmapped_reason=sanitized_reason,
                sanitized_reason=sanitized_reason,
                profile=jury_profile,
            )
        except Exception:  # noqa: BLE001 — LLM 任何异常降级为空 addons，保 Gate-7 路径
            extra_addons = []
    else:
        extra_addons = []

    if not hits.prompt_addons and not extra_addons:
        # 规则未命中且 llm_fallback 关 / 也没产出 addon → 接受首轮图
        return _finalize_baseline_only(
            view=safe_view,
            render_dir=render_dir,
            backend=backend_kind,
            loop_status="no_rules_hit_no_llm",
            baseline_path=baseline_path,
            baseline=verdict,
            local_extra_cost=local_extra_cost,
            tags_parsed=sorted(tags),
        )

    # Step 7: 应用 prompt addons + param overrides（spec rev 3 §3 [6]）
    new_prompt, retry_params = _apply_overrides(
        prompt=str(rc.get("prompt", "")),
        prompt_addons=list(hits.prompt_addons) + extra_addons,
        param_overrides=hits.param_overrides,
        base_params=base_params,
    )

    # Step 8: 调 backend（4 类 BackendError → Gate-8 分类，spec rev 3 决议 #10）
    retry_request = BackendRequest(
        input_image_path=baseline_path,
        prompt=new_prompt,
        params=retry_params,
        base_url=config.backend.base_url,
        api_key=os.environ.get(config.backend.api_key_env, ""),
        model_name=config.backend.model_name,
    )
    try:
        response = adapter.call(retry_request, timeout=config.backend.timeout_s)
    except BackendError as exc:
        loop_status, error_entry = _classify_backend_error(exc)
        return _finalize_baseline_only(
            view=safe_view,
            render_dir=render_dir,
            backend=backend_kind,
            loop_status=loop_status,
            baseline_path=baseline_path,
            baseline=verdict,
            errors=[error_entry],
            local_extra_cost=local_extra_cost,
            tags_parsed=sorted(tags),
        )

    # cost actual / estimate（spec §4.4 line 502 warnings.cost_estimated_only）
    warnings: list[str] = []
    if response.actual_cost_usd is not None:
        budget.record_actual(response.actual_cost_usd)
        # local_extra_cost 同步用 actual 替换刚才的 estimate（spent 已被 record_actual 修正）
        local_extra_cost = local_extra_cost - estimate + response.actual_cost_usd
    else:
        # adapter 不报实际费用 → 保留 estimate；提示 sidecar 用户
        warnings.append("cost_estimated_only")

    # Step 9: score_select 选张（spec §4.5.2 / 决议 #12 retry_verdict 出口）
    retry_path = response.output_image_path
    candidates = [
        CandidateImage(str(baseline_path), verdict),
        CandidateImage(str(retry_path), None),
    ]
    strategy_cls = STRATEGY_REGISTRY[config.advanced["score_select_strategy"]]
    strategy = strategy_cls()

    def _jury_callable(image_path: str) -> ViewVerdict:
        v, _ = _call_jury_subprocess(
            view=safe_view,
            image_path=Path(image_path),
            project_root=project_root,
            jury_profile_path=jury_profile_path,
            timeout_s=config.backend.timeout_s,
        )
        if v is None:
            # 让 PickMaxJuryStrategy 内 catch Exception 走 baseline fallback
            raise RuntimeError("二轮 jury 调用失败")
        return v

    selection = strategy.select(candidates, _jury_callable, budget)

    # Step 10: finalize rename + 写富 sidecar
    pick_image_path = Path(selection.pick.image_path)
    final_path = _finalize(
        pick_image_path=pick_image_path,
        baseline_path=baseline_path,
        retry_path=retry_path,
        view=safe_view,
        render_dir=render_dir,
    )

    delivered_kind = "retry" if pick_image_path == retry_path else "baseline"
    loop_status_final = (
        "delivered_retry" if delivered_kind == "retry" else "delivered_baseline"
    )
    retry_score_delta, delivered_score_delta = _compute_score_deltas(
        retry_verdict=selection.retry_verdict,
        baseline_verdict=verdict,
        pick_image_path=pick_image_path,
        retry_path=retry_path,
    )

    metadata.write_sidecar(
        view=safe_view,
        render_dir=render_dir,
        backend=backend_kind,
        loop_status=loop_status_final,
        delivered_kind=delivered_kind,
        baseline=_view_verdict_to_baseline_dict(verdict, baseline_path),
        retry=_build_retry_dict(
            retry_path=retry_path,
            retry_verdict=selection.retry_verdict,
            request=retry_request,
            response=response,
        ),
        tags_parsed=sorted(tags),
        rules_hit=list(hits.matched_rule_ids),
        prompt_addons_applied=list(hits.prompt_addons) + extra_addons,
        param_overrides_applied={
            backend_kind: hits.param_overrides,
        },
        retry_score_delta=retry_score_delta,
        delivered_score_delta=delivered_score_delta,
        extra_cost_usd=local_extra_cost,
        warnings=warnings,
        llm_fallback_used=bool(extra_addons),
    )
    return LoopResult(final_path, loop_status_final)
