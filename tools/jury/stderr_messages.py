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
