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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enhance_budget import LoopBudget
from tools.jury.config import JuryProfile
from tools.jury_loop.config import JuryLoopConfig
from tools.jury_loop.metadata import _validate_view_basename


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
    raise NotImplementedError(
        f"Task 5.1.4+ 完整实现 view={safe_view}；当前为骨架"
    )
