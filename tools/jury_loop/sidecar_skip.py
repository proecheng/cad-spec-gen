"""CP-7 Task 7.1.1：jury_loop sidecar fast-path skip 判定（OPS-MAJOR-3）。

视角级 `--rerun-loop` 默认 false 时，若 `<V>.jury_loop.json` 已存在 `delivered_retry=true`
则跳过该视角的 hook 调用，避免重复 jury subprocess + retry backend 调用浪费成本。

容错原则：sidecar 不存在 / 损坏 / 读失败 → 返 False（重跑），不阻断流水线。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def should_skip_jury_loop_for_view(
    view: str,
    render_dir: Path,
    rerun_loop: bool,
) -> bool:
    """判定本视角是否 fast-path 跳过 jury_loop hook。

    Args:
        view: 视角 key（如 "V1"）；调用方已用 metadata._validate_view_basename 校验
        render_dir: 当前 render 目录（含 `<V>.jury_loop.json` sidecar）
        rerun_loop: --rerun-loop CLI flag；True 时强制重跑（即使 sidecar 已 delivered_retry）

    Returns:
        True  → 跳过本视角的 hook 调用（fast-path）
        False → 正常进入 hook（首次跑 / 强制重跑 / sidecar 损坏 / 上次未 delivered_retry）
    """
    if rerun_loop:
        return False
    sidecar = render_dir / f"{view}.jury_loop.json"
    if not sidecar.is_file():
        return False
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("sidecar %s 损坏/读失败，重跑视角：%s", sidecar, e)
        return False
    return data.get("delivered_retry") is True
