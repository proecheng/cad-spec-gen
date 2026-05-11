"""CP-7 Task 7.1.2：cmd_enhance 视角级 jury_loop hook + 前置状态加载。

cmd_enhance 是 ~700 行 god function；hook 逻辑独立成 module-level 函数：
- 便于单元测试（不必整个 cmd_enhance 跑）
- 异常隔离更显式（每个失败点都有对应 log + 安全返回）
- 后续重构 cmd_enhance（拆 helper）时迁移成本低

两个公开函数：
- `prepare_jury_loop_state(pipeline_config, n_views)` — 视角循环前调一次，加载
  JuryLoopConfig + LoopBudget + JuryProfile；任意步骤失败返 (None, None, None, None)
  表示 hook 整体禁用
- `run_loop_hook_for_view(...)` — 每视角 baseline enhance 成功后调一次；返 v1_anchor
  模式下 V1 hook 的新 hero_image 路径或 None

设计原则（DRIFT-MAJOR-7 视角级隔离）：所有路径只 log 不 raise；保证下一视角不受影响。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from enhance_budget import LoopBudget
from tools.jury_loop import orchestrator
from tools.jury_loop.config import (
    DEFAULT_JURY_LOOP_DICT,
    JuryLoopConfig,
    load_jury_loop_config,
)
from tools.jury_loop.sidecar_skip import should_skip_jury_loop_for_view

if TYPE_CHECKING:
    from tools.jury.config import JuryProfile

log = logging.getLogger(__name__)


def resolve_jury_config_path() -> Path:
    """jury_profile 配置路径 = ~/.claude/cad_jury_config.json。

    与 photo3d_jury.py:115 `_resolve_config_path` 保持一致（无 --config 参数时的默认）。
    cmd_enhance 不暴露 --jury-config CLI flag——外行用户应只编辑 home 配置一次。
    """
    return Path.home() / ".claude" / "cad_jury_config.json"


def prepare_jury_loop_state(
    *,
    pipeline_config: dict[str, Any],
    n_views: int,
) -> tuple[JuryLoopConfig | None, LoopBudget | None, "JuryProfile | None", Path | None]:
    """加载 jury_loop config + LoopBudget + JuryProfile。

    任意步骤失败（config 无效 / enabled=false / jury_profile 加载失败）→ 返
    `(None, None, None, None)` 表示 hook 整体禁用；调用方据此跳过所有 hook 调用。

    Args:
        pipeline_config: `_load_pipeline_config()` 返回的整 dict
        n_views: 本次跑的视角总数（用于 LoopBudget.n_views 必填参数）

    Returns:
        (jury_loop_config, loop_budget, jury_profile, jury_profile_path) —
        要么全 None（hook 禁用），要么 jury_loop_config 非 None 且其余按 enabled 决定。
    """
    enhance_section = pipeline_config.get("enhance") or {}
    jl_dict = enhance_section.get("jury_loop") or DEFAULT_JURY_LOOP_DICT
    try:
        jury_loop_config = load_jury_loop_config(jl_dict)
    except (ValueError, TypeError, KeyError) as e:
        log.warning("jury_loop 配置无效，本次跑跳过闭环：%s", e)
        return None, None, None, None
    if not jury_loop_config.enabled:
        log.info("enhance.jury_loop.enabled=false，本次跑不进入闭环")
        return None, None, None, None
    # JuryProfile 加载——失败则视为整体禁用（视为 loop_disabled 等价）
    try:
        from tools.jury.config import JuryConfigError, load_jury_config
    except ImportError as e:  # pragma: no cover — 包结构损坏极端情况
        log.warning("无法 import tools.jury.config，跳过闭环：%s", e)
        return None, None, None, None
    profile_path = resolve_jury_config_path()
    try:
        jury_profile, _caps = load_jury_config(profile_path)
    except (JuryConfigError, FileNotFoundError, OSError) as e:
        log.warning(
            "jury 未配置或配置错误（%s），本次跑跳过闭环；"
            "如需启用闭环请配置 %s",
            e,
            profile_path,
        )
        return None, None, None, None
    loop_budget = LoopBudget(cap_usd=jury_loop_config.cost_cap_usd, n_views=n_views)
    return jury_loop_config, loop_budget, jury_profile, profile_path


def run_loop_hook_for_view(
    *,
    view_key: str,
    new_path: str | None,
    render_dir: Path,
    rc: dict[str, Any],
    rerun_loop: bool,
    jury_loop_config: JuryLoopConfig | None,
    loop_budget: LoopBudget | None,
    jury_profile: "JuryProfile | None",
    jury_profile_path: Path | None,
    reference_mode: str,
    project_root: Path,
) -> str | None:
    """跑单视角 jury→prompt 闭环 hook。

    `prepare_jury_loop_state` 返回的 4 元素直接传入；调用方对每个视角调一次。

    Returns:
        v1_anchor 模式下 V1 hook 成功后的 final_path 字符串（cmd_enhance 用之
        更新 hero_image，供 V2+ 作 anchor，BL-4 状态传递）；其余情况返 None
        （hook 未跑 / 非 V1 / 失败 / 非 v1_anchor 模式）。

    Side effects: 仅写日志；可能由 orchestrator 写 sidecar 文件。**不 raise**——
    DRIFT-MAJOR-7 视角级异常隔离：每个失败分支都 log 后 return None。
    """
    if (
        jury_loop_config is None
        or not jury_loop_config.enabled
        or loop_budget is None
        or jury_profile is None
        or jury_profile_path is None
    ):
        # prepare_jury_loop_state 保证 enabled+budget 同时为真时 profile/path 也非 None；
        # 此守卫只为给 mypy 收窄类型用，运行时仅是 defensive 短路。
        return None
    if not new_path or not os.path.isfile(new_path):
        # baseline enhance 未定位产物（gemini stdout 解析失败 / table-driven raw_path 为空）
        # → 无 baseline_path 可传给 orchestrator
        return None
    if should_skip_jury_loop_for_view(view_key, render_dir, rerun_loop):
        log.info(
            "  Loop hook skip %s（既有 sidecar fast-path；--rerun-loop 可强制重跑）",
            view_key,
        )
        return None
    try:
        loop_result = orchestrator.run_loop_if_eligible(
            view=view_key,
            backend_kind=jury_loop_config.backend.kind,
            rc=rc,
            baseline_path=Path(new_path),
            base_params={},
            budget=loop_budget,
            project_root=project_root,
            config=jury_loop_config,
            jury_profile=jury_profile,
            jury_profile_path=jury_profile_path,
        )
    except FileNotFoundError as e:
        # Precondition fail-fast：baseline 文件缺失；不写 sidecar 防误覆盖既有产物
        log.warning(
            "  Loop hook precondition failed for %s (baseline missing): %s",
            view_key, e,
        )
        return None
    except ValueError as e:
        # Precondition fail-fast：view 名注入（path traversal 等）；不写 sidecar 同上
        log.error(
            "  Loop hook precondition failed for %s (invalid view): %s",
            view_key, e,
        )
        return None
    except Exception as e:  # noqa: BLE001 — DRIFT-MAJOR-7 视角级隔离
        # 未知 Exception：orchestrator 内层已 write_degraded_sidecar；此处仅 log
        # 不重写 sidecar — `--rerun-loop` 默认 false 时下次会 fast-path 跳过该视角
        log.error("  Loop hook crashed for %s: %s", view_key, e)
        return None

    log.info("  Loop hook %s → %s", view_key, loop_result.loop_status)
    # BL-4 状态传递：v1_anchor 模式 V1 闭环最终交付张作 V2+ anchor
    if reference_mode == "v1_anchor" and view_key == "V1":
        return str(loop_result.final_path)
    return None
