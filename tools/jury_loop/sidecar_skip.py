"""CP-7 Task 7.1.0：jury_loop sidecar fast-path skip 判定（OPS-MAJOR-3）。

视角级 `--rerun-loop` 默认 false 时，若该视角的 sidecar `<view>_enhance_meta.json`
（orchestrator 实际写出的文件，spec §4.4）已记录一个"终态"`loop_status`（spec §4.6），
则跳过该视角的 jury loop hook 调用，避免重复 jury subprocess + retry backend 调用浪费成本。

fast-path skip-set（spec §6.2 OPS-MAJOR-3）：
- 已成功交付：`delivered_baseline` / `delivered_retry` / `above_threshold`
- 持久失败重跑无意义：`retry_auth_failed` / `retry_quota_exceeded`（修 key / 充值后用 --rerun-loop 才重试）
- 临时/可恢复失败（`jury_unavailable` / `retry_failed` / `retry_rate_limited` / `cost_capped` / ...）
  默认**仍然重试**，不在此集合（cost_capped 在新一次 cmd_enhance 跑里走新 LoopBudget，给它再一次机会）

容错原则：sidecar 不存在 / 损坏 / 读失败 / 缺 loop_status → 返 False（重跑），不阻断流水线。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

#: spec §6.2：默认幂等模式下 fast-path 跳过的 loop_status 集合（终态）。
_FAST_PATH_SKIP_STATUSES = frozenset(
    {
        "delivered_retry",
        "delivered_baseline",
        "above_threshold",
        "retry_auth_failed",
        "retry_quota_exceeded",
    }
)


def should_skip_jury_loop_for_view(
    view: str,
    render_dir: Path,
    rerun_loop: bool,
) -> bool:
    """判定本视角是否 fast-path 跳过 jury_loop hook。

    Args:
        view: 视角 key（如 "V1"）；调用方已用 metadata._validate_view_basename 校验
        render_dir: 当前 render 目录（含 `<view>_enhance_meta.json` sidecar）
        rerun_loop: --rerun-loop CLI flag；True 时强制重跑（即使 sidecar 是终态）

    Returns:
        True  → 跳过本视角的 hook 调用（fast-path）
        False → 正常进入 hook（首次跑 / 强制重跑 / sidecar 缺失/损坏 / 上次是临时失败需重试）
    """
    if rerun_loop:
        return False
    sidecar = render_dir / f"{view}_enhance_meta.json"
    if not sidecar.is_file():
        return False
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("sidecar %s 损坏/读失败，重跑视角：%s", sidecar, e)
        return False
    return data.get("loop_status") in _FAST_PATH_SKIP_STATUSES
