"""中文人话提示模板集中。

模板覆盖 exit_code × status × error_kind；所有 placeholder 由 cli 填充实际值，
禁止 ``{xxx}`` 残留给用户看到。

调用方应保证 ``context`` 中含模板所需键；缺键时使用空字符串/0 作为安全 fallback，
但任何 placeholder 名（如 ``fallback_id``）不应出现在最终输出。
"""

from __future__ import annotations

from typing import Any


def format_stderr_message(
    *,
    exit_code: int,
    status: str = "",
    error_kind: str = "",
    context: dict[str, Any],
) -> str:
    """根据 ``exit_code`` + ``status``/``error_kind`` 选择中文人话模板填充。

    参数:
        exit_code: jury 进程退出码（0/1/2/3/4/99）。
        status: 仅 exit_code=0/1 时区分（accepted/preview/needs_review/blocked）。
        error_kind: exit_code=2/3/4/99 时区分错误细类。
        context: 模板填充上下文；调用方负责填实际值，禁止留 placeholder 名。

    返回:
        填好实际值的中文 stderr 提示串；禁止含 ``{xxx}`` 残留。
    """
    # === v2.28.0 handoff 集成模板（spec §5.2 + §5.2.1） ===
    # handoff_* error_kind 的分派以 error_kind 为优先维度，必须在 exit_code 块之前匹配
    # （否则 exit_code=2 等内部 fallback 会先吃掉 handoff_jury_config_error 等三元组）
    if error_kind == "handoff_jury_preview":
        failed_n = context.get("failed_n", 0)
        score = context.get("score", 0)
        min_score = context.get("min_score", 0)
        report_path = context.get("report_path", "")
        mode = context.get("mode", "strict")
        if mode == "strict":
            return (
                f"jury 判定 preview（5 项语义检查中 {failed_n} 项 false 或 photoreal_score={score} 低于 min_photoreal_score={min_score}）。\n"
                f"  jury 报告：{report_path}\n"
                "  ① 改善：检查 enhance 输出是否清晰；调整 enhance config；或换 provider preset（具体可改项见 docs/cad-enhance-config.md）\n"
                "  ② 跳过：加 --no-strict-jury 仅警告（但结果不会进入 deliver；需手动跑 enhance-review）"
            )
        return (
            f"[WARNING] jury 判定 preview，因 --no-strict-jury 仅警告。\n"
            f"  jury 报告：{report_path}\n"
            "  注意：本次 handoff 不会自动跑 enhance-review；deliver 会缺 ENHANCEMENT_REVIEW_REPORT.json。"
        )

    if error_kind == "handoff_jury_needs_review":
        failed_views = context.get("failed_views", [])
        vendor_request_id = context.get("vendor_request_id") or "(无)"
        report_path = context.get("report_path", "")
        mode = context.get("mode", "strict")
        prefix = "jury 工具调用失败" if mode == "strict" else "[WARNING] jury 工具调用失败"
        return (
            f"{prefix}（{len(failed_views)} 视角；vendor_request_id={vendor_request_id}）。\n"
            f"  jury 报告：{report_path}\n"
            "  ① 重跑：jury 偶发失败常自愈\n"
            "  ② 换 profile：jury config active_profile_id 切到备用\n"
            "  ③ 检查 api_key 是否到期 / 是否被 vendor rate-limit"
        )

    if error_kind == "handoff_jury_blocked":
        report_path = context.get("report_path", "")
        return (
            "jury 检测到输入证据漂移（active_run_id 或 sha256 不一致）。\n"
            "  这是工具自身故障，--no-strict-jury 也不会跳过。\n"
            f"  jury 报告：{report_path}\n"
            "  ① 重跑：cad_pipeline.py photo3d-handoff --with-jury --confirm 重新走一遍\n"
            "  ② 检查：是否其他工具/脚本同时改 ARTIFACT_INDEX.json（CI 多 worker / 双窗口）"
        )

    if error_kind == "handoff_jury_lock_busy":
        mins = context.get("lock_mtime_minutes_ago", 0)
        lock_path = context.get("lock_path", "")
        return (
            f"jury 被另一 photo3d-jury 进程持锁（lock 文件 mtime={mins} 分钟前）。\n"
            "  ① 等待：其他 jury 进程结束（一次跑 ~30s）；30 分钟无响应自动清理\n"
            "  ② 主动放弃：本次 handoff 退出；不会破坏数据；可稍后重跑\n"
            f"  ③ 紧急清理（仅在确认无其他 photo3d-jury 进程时）：删 {lock_path} 后重跑"
        )

    if error_kind == "handoff_jury_internal_error":
        tb = context.get("redacted_traceback", "")
        return (
            "jury 内部异常（已脱敏 traceback）：\n"
            f"  {tb}\n"
            "  这是 bug，请提 issue 并附 PHOTO3D_JURY_REPORT.json"
        )

    if error_kind == "handoff_jury_config_error":
        cp = context.get("config_path", "~/.claude/cad_jury_config.json")
        return (
            f"jury 配置文件 {cp} 解析失败（jury 子进程报错）。\n"
            "  详见 jury 自身 stderr；修后重跑。"
        )

    if error_kind == "handoff_jury_cost_over_budget":
        est = context.get("estimated_usd", 0.0)
        budget = context.get("budget_usd", 0.0)
        n_views = context.get("n_views", 0)
        return (
            f"[handoff] jury 预估 {est:.2f} USD / {n_views} 视角 (budget {budget:.2f} USD)\n"
            f"jury 估价超过 budget。改 budget 或减视角后重跑。"
        )

    if error_kind == "handoff_review_failed":
        raw = context.get("review_raw_exit", 0)
        rp = context.get("report_path", "")
        return (
            f"enhance-review 转正式契约失败（review exit={raw}）。\n"
            f"  jury 报告已写在 {rp}，可手动重跑：\n"
            f"  python cad_pipeline.py enhance-review --review-input <run_dir>/jury_review_input.json"
        )

    if error_kind == "handoff_review_input_missing":
        rip = context.get("review_input_path", "")
        reason = context.get("reason", "")
        return (
            f"jury 判定 accepted 但 enhance-review 输入缺失（{reason}）。\n"
            f"  路径：{rip}\n"
            "  原因 not_found = 文件不存在；run_id_format = jury 写的 run_id 含非法字符；path_traversal = 路径越界\n"
            "  这是 bug，请提 issue 并附 PHOTO3D_JURY_REPORT.json"
        )

    if error_kind == "handoff_review_input_corrupt":
        rip = context.get("review_input_path", "")
        pe = context.get("parse_error", "")
        return (
            f"jury_review_input.json 是损坏 JSON：{rip}\n"
            f"  解析错误：{pe}\n"
            "  这是 jury 写盘 bug，请提 issue 并附文件原始字节"
        )

    if error_kind == "handoff_unexpected_jury_exit":
        raw = context.get("raw_exit", 0)
        return (
            f"jury 进程异常退出（exit code = {raw}）。\n"
            "  常见原因：被 Ctrl-C 打断（130） / OOM kill（137） / 超时（timeout） / 系统 SIGTERM\n"
            "  ① 重跑 handoff；② 若反复出现，看 jury stderr 详细输出（已脱敏）"
        )

    if error_kind == "handoff_handoff_lock_busy":
        mins = context.get("lock_mtime_minutes_ago", 0)
        lock_path = context.get("lock_path", "")
        return (
            f"另一个 photo3d-handoff 进程正在跑同 subsystem（lock mtime={mins} 分钟前）。\n"
            "  请等当前进程结束(约 5-15 分钟，含 enhance + jury + review）；\n"
            f"  ③ 紧急清理（仅在确认无其他 photo3d-handoff 进程时）：删 {lock_path} 后重跑"
        )

    if error_kind == "handoff_jury_preflight_config_missing":
        cp = context.get("config_path", "~/.claude/cad_jury_config.json")
        return (
            f"jury 配置缺失或格式错（路径：{cp}）。\n"
            "  最小配置示例（写到 ~/.claude/cad_jury_config.json）：\n"
            '    {{"profiles": [{{"id": "default", "kind": "openai_compat", "api_base_url": "https://api.openai.com", "api_key": "sk-...", "model": "gpt-4o", "cost_per_call_usd": 0.01}}], "active_profile_id": "default", "budget_per_run_usd": 0.50}}\n'
            "  详细参数（含中转商 base_url / TLS CA）见 docs/cad-jury-config.md。\n"
            "  注：jury 估价产生的 USD 费用计入此 api_key 对应 LLM 服务商账单。\n"
            "  本次 handoff 已立即退出，未跑 enhance（不浪费 LLM 额度）"
        )

    if error_kind == "handoff_awaiting_confirmation_with_jury":
        argv_with_confirm = context.get("argv_with_confirm", "")
        return (
            "已找到可交接的下一步（含 jury 验收 + enhance-review 闭环）；预览模式不执行。\n"
            f"  下一步：加 --confirm 重跑：\n"
            f"    {argv_with_confirm}\n"
            "  或不带 --with-jury 走简化路径（仅 enhance + check 不跑 jury）"
        )

    if exit_code == 0 and status == "accepted":
        cost = context.get("actual_cost_usd", 0)
        path = context.get("jury_review_input_abs_path", "")
        return (
            f"✓ 自动验收通过（成本 ${cost} USD）。"
            f"下一步：enhance-review --review-input {path}"
        )

    if exit_code == 0 and status == "preview":
        n_failed = context.get("n_failed", 0)
        total = context.get("total", 0)
        path = context.get("photo3d_jury_report_abs_path", "")
        return (
            f"△ 自动验收降级为预览（{n_failed}/{total} 视角不达标）。"
            f"先看 {path} 里 views[].verdict 找原因；"
            "可重跑 enhance --provider <preset> --resubmit 或人工目检后手填 review-input。"
        )

    if exit_code == 0 and status == "needs_review":
        n_failed = context.get("n_failed", 0)
        total = context.get("total", 0)
        kinds = context.get("error_kinds", "")
        cost = context.get("actual_cost_usd", 0)
        sub = context.get("subsystem", "")
        fb = context.get("fallback_id", "")
        return (
            f"⚠ {n_failed}/{total} 视角验收失败（{kinds}）；已花费 ${cost} USD。"
            f"建议换 profile：photo3d-jury --subsystem {sub} --profile-id {fb}。"
            "文档：docs/cad-jury-config.md"
        )

    if exit_code == 1 and status == "blocked":
        code = context.get("first_blocking_code", "")
        if code == "freeze_drift":
            cost = context.get("actual_cost_usd", 0)
            return (
                f"✗ jury 跑期间报告被改坏（sha drift）。已花费 ${cost} USD 但结果作废。"
                "检查 ENHANCEMENT_REPORT.json 是否有别的进程在改写。"
            )
        sub = context.get("subsystem", "")
        return (
            f"✗ 输入证据与 active run 不一致（{code}）。"
            f"检查 enhance-check 是否真 accepted：photo3d-recover --subsystem {sub} 后再跑 jury。"
        )

    if exit_code == 2:
        if error_kind == "schema_version_invalid":
            actual = context.get("actual", "")
            return (
                f"✗ jury 配置 schema_version={actual} 不被本版本支持（仅 1 或 2）。"
                "建议改成 1 或升级 photo3d-jury。"
            )
        if error_kind == "profile_id_invalid":
            bad = context.get("bad_id", "")
            ch = context.get("first_bad_char", "")
            cand = context.get("sanitized_candidate", "")
            return (
                f"✗ profile id `{bad}` 含非法字符 `{ch}`，仅允许 [A-Za-z0-9_-]。"
                f"建议改成 `{cand}`。"
            )
        if error_kind == "config_path_external":
            abs_p = context.get("abs", "")
            return (
                f"✗ --config 路径 {abs_p} 不在 ~/.claude/ 或项目内。"
                "如确认信任此文件请加 --allow-external-config；否则修正 --config。"
            )
        if error_kind == "config_missing":
            path = context.get("config_path", "~/.claude/cad_jury_config.json")
            return f"✗ 未找到 jury 配置文件 {path}。最小配置示例见 docs/cad-jury-config.md。"
        return f"✗ 配置错（{error_kind}）。详见 docs/cad-jury-config.md。"

    if exit_code == 3:
        est = context.get("estimated_cost_usd", 0)
        budget = context.get("budget_per_run_usd", 0)
        n_views = context.get("n_views", 0)
        per = context.get("cost_per_call_usd", 0)
        return (
            f"△ 预估成本 ${est} USD 超 budget ${budget}（{n_views} 视角 × ${per}）。"
            "加 --confirm-cost 或调高 --budget 重跑。"
        )

    if exit_code == 4:
        if error_kind == "lock_stale_cleaned":
            pid = context.get("held_pid", "")
            age = context.get("age_min", 0)
            return f"ⓘ 检测到 stale .jury.lock（PID={pid}，age={age} 分钟），自动清理后继续。"
        pid = context.get("held_pid", "")
        age = context.get("age_seconds", 0)
        return (
            f"△ 已有 jury 进程在跑（PID={pid}，{age}s 前启动）。"
            "等它结束或 ctrl-c 它后重试。"
        )

    if exit_code == 99:
        exc = context.get("exception_type", "Exception")
        return (
            f"✗ 工具内部错误（{exc}）。"
            "请提 issue 附 PHOTO3D_JURY_REPORT.json + 命令行参数（api_key 已 redact）。"
        )

    return (
        f"jury 已退出 (exit_code={exit_code}, status={status}, error_kind={error_kind})"
    )
