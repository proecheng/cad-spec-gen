"""Layer 1 — 字段自洽性二次验证。

输入到此前已 Layer 0 通过；本层仅在 report 顶层声称 accepted 时检查 per-view 字段是否真自洽。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 与 tools/enhance_consistency.py:MIN_PHOTO_CONTRAST_STDDEV 同值
MIN_PHOTO_CONTRAST_STDDEV = 12.0
DEFAULT_MIN_SIMILARITY = 0.85


@dataclass(frozen=True)
class Layer1Verdict:
    """Layer 1 字段自洽性裁决（不可变）。"""

    passed: bool
    per_view_failures: list[dict[str, Any]] = field(default_factory=list)


def run_layer1(report: dict[str, Any]) -> Layer1Verdict:
    """运行 Layer 1 自洽性检查。

    检查项：
    - view.status == "accepted"
    - view.edge_similarity >= report.min_similarity (fallback 0.85)
    - view.quality_metrics.effective_contrast_stddev 非 None 且 >= 12.0
    """
    failures: list[dict[str, Any]] = []
    min_similarity = float(report.get("min_similarity", DEFAULT_MIN_SIMILARITY))

    for view in report.get("views", []):
        view_name = view.get("view", "")
        reasons: list[str] = []

        if view.get("status") != "accepted":
            reasons.append(f"view_status_not_accepted (got: {view.get('status')})")

        edge_sim = view.get("edge_similarity")
        if edge_sim is None or float(edge_sim) < min_similarity:
            reasons.append(f"edge_similarity below {min_similarity} (got: {edge_sim})")

        qm = view.get("quality_metrics")
        if not isinstance(qm, dict) or not qm:
            reasons.append("quality_metrics missing or empty")
        else:
            ecs = qm.get("effective_contrast_stddev")
            if ecs is None:
                reasons.append("effective_contrast_stddev is None")
            elif float(ecs) < MIN_PHOTO_CONTRAST_STDDEV:
                reasons.append(
                    f"effective_contrast_stddev below "
                    f"{MIN_PHOTO_CONTRAST_STDDEV} (got: {ecs})"
                )

        if reasons:
            failures.append({"view": view_name, "reasons": reasons})

    return Layer1Verdict(passed=not failures, per_view_failures=failures)
