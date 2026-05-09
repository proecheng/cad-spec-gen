"""Layer 0 — 输入证据绑定 + sha256/active_run freeze + 重跑保护。

职责（spec rev 5 §4.4）：
- 读 ARTIFACT_INDEX.json 拿 active_run_id 并冻结
- 读 ENHANCEMENT_REPORT.json 校验状态/字段一致性
- 校验 views 非空、无重复、不超 max_n_views
- 预检每张增强图大小 <= max_image_bytes
- 全部通过后冻结 enhancement_report + render_manifest 的 sha256

本函数只做纯校验 + freeze；lock 由 cli 顶层 contextmanager 管理；
JuryLockBusy 在此重导出仅作类型/异常路径稳定性占位。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools._file_lock import LockBusy as JuryLockBusy
from tools.contract_io import file_sha256
from tools.jury.config import JuryCaps

__all__ = ["JuryLockBusy", "Layer0Verdict", "run_layer0"]


@dataclass(frozen=True)
class Layer0Verdict:
    """Layer 0 判定结果；不可变。

    fail 时 frozen_report 仍尽可能填（spec rev 5 §4.4：blocked 状态报告含 views 字段）。
    """

    passed: bool
    frozen_run_id: str = ""
    frozen_sha256: dict[str, str] = field(default_factory=dict)
    blocking_reasons: list[dict[str, Any]] = field(default_factory=list)
    frozen_report: dict[str, Any] = field(default_factory=dict)


def run_layer0(
    *,
    project_root: Path,
    subsystem: str,
    caps: JuryCaps,
) -> Layer0Verdict:
    """运行 Layer 0 输入证据绑定。

    返回 Layer0Verdict；不创建 lock（lock 由 cli 顶层管理）。

    Args:
        project_root: 项目根目录（含 cad/ 子目录）
        subsystem: 子系统名（用于定位 ARTIFACT_INDEX.json + 校验 report.subsystem 字段）
        caps: 资源上限（max_image_bytes / max_n_views / min_photoreal_score）

    Returns:
        Layer0Verdict — passed=True 表示通过；False 时 blocking_reasons 至少 1 条
    """
    blocking: list[dict[str, Any]] = []

    # 1) ARTIFACT_INDEX active_run_id
    ai_path = project_root / "cad" / subsystem / ".cad-spec-gen" / "ARTIFACT_INDEX.json"
    if not ai_path.exists():
        return Layer0Verdict(
            passed=False,
            blocking_reasons=[{"code": "artifact_index_missing"}],
        )
    try:
        ai = json.loads(ai_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Layer0Verdict(
            passed=False,
            blocking_reasons=[{"code": "artifact_index_unreadable"}],
        )

    active_run_id = str(ai.get("active_run_id", ""))
    runs = ai.get("runs", {})
    run_meta = runs.get(active_run_id, {}) if isinstance(runs, dict) else {}
    if not isinstance(run_meta, dict) or not run_meta.get("active"):
        return Layer0Verdict(
            passed=False,
            blocking_reasons=[{"code": "active_run_not_active"}],
        )

    # 2) ENHANCEMENT_REPORT.json
    render_dir = project_root / "cad" / "output" / "renders" / subsystem / active_run_id
    er_path = render_dir / "ENHANCEMENT_REPORT.json"
    rm_path = render_dir / "render_manifest.json"
    if not er_path.exists():
        blocking.append({"code": "enhancement_report_missing"})
        return Layer0Verdict(passed=False, blocking_reasons=blocking)
    try:
        report_obj = json.loads(er_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        blocking.append({"code": "enhancement_report_unreadable"})
        return Layer0Verdict(passed=False, blocking_reasons=blocking)
    if not isinstance(report_obj, dict):
        blocking.append({"code": "enhancement_report_unreadable"})
        return Layer0Verdict(passed=False, blocking_reasons=blocking)
    report: dict[str, Any] = report_obj

    # 3) 字段校验
    if report.get("subsystem") != subsystem:
        blocking.append(
            {
                "code": "subsystem_mismatch",
                "actual": report.get("subsystem"),
                "expected": subsystem,
            }
        )
    if report.get("run_id") != active_run_id:
        blocking.append(
            {
                "code": "run_id_mismatch",
                "actual": report.get("run_id"),
                "expected": active_run_id,
            }
        )
    if report.get("status") != "accepted":
        blocking.append(
            {"code": "report_status_not_accepted", "actual": report.get("status")}
        )
    if report.get("delivery_status") not in {"accepted", None}:
        blocking.append({"code": "delivery_status_not_accepted"})

    qs_obj = report.get("quality_summary", {})
    qs: dict[str, Any] = qs_obj if isinstance(qs_obj, dict) else {}
    if qs.get("status") != "accepted":
        blocking.append({"code": "quality_summary_not_accepted"})

    views_obj = report.get("views", [])
    views: list[dict[str, Any]] = (
        [v for v in views_obj if isinstance(v, dict)] if isinstance(views_obj, list) else []
    )
    if not views:
        blocking.append({"code": "views_empty"})
    elif len(views) > caps.max_n_views:
        blocking.append(
            {
                "code": "max_n_views_exceeded",
                "actual": len(views),
                "cap": caps.max_n_views,
            }
        )

    seen_view_names: set[str] = set()
    for v in views:
        name = str(v.get("view", ""))
        if name in seen_view_names:
            blocking.append({"code": "duplicate_view", "view": name})
        seen_view_names.add(name)

    # 4) 图大小预检
    for v in views:
        rel = str(v.get("enhanced_image", ""))
        if not rel:
            continue
        img_path = project_root / rel
        try:
            size = img_path.stat().st_size
        except OSError:
            continue  # 缺文件 / 权限错由后续 LLM 阶段处理
        if size > caps.max_image_bytes:
            blocking.append(
                {
                    "code": "image_too_large",
                    "view": v.get("view"),
                    "size": size,
                    "cap": caps.max_image_bytes,
                }
            )

    if blocking:
        # spec rev 5 §4.4：blocked 状态保留 frozen_report 以便上层渲染人话
        return Layer0Verdict(
            passed=False,
            blocking_reasons=blocking,
            frozen_report=report,
        )

    # 5) freeze sha256
    frozen_sha = {
        "enhancement_report": file_sha256(er_path),
        "render_manifest": file_sha256(rm_path) if rm_path.exists() else "",
    }
    return Layer0Verdict(
        passed=True,
        frozen_run_id=active_run_id,
        frozen_sha256=frozen_sha,
        blocking_reasons=[],
        frozen_report=report,
    )
