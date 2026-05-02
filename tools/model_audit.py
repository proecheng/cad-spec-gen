"""cad_pipeline.py model-audit 子命令实现。

只读取 codegen 已写出的 geometry_report.json，不调用 resolver，也不触发
SolidWorks/STEP 生成。这个命令的职责是把模型库质量事实变成可重复审计输出。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from cad_paths import PROJECT_ROOT
from tools.model_context import ModelProjectContext

_QUALITY_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "unknown": 0}
_QUALITY_DESCRIPTIONS = {
    "B": "B = curated parametric template; visually and dimensionally useful, not vendor STEP.",
}
_CACHE_URI_PREFIX = "cache://"


def _project_root() -> Path:
    return Path(PROJECT_ROOT).resolve()


def _resolve_report_path(args: argparse.Namespace) -> Path:
    project_root = getattr(args, "project_root", None) or PROJECT_ROOT
    report = getattr(args, "report", None)
    if report:
        expanded = os.path.expandvars(os.path.expanduser(str(report)))
        p = Path(expanded)
        if p.is_absolute():
            return p
        return Path(project_root).expanduser().resolve() / p

    subsystem = getattr(args, "subsystem", None)
    if not subsystem:
        raise ValueError("--subsystem or --report is required")
    ctx = ModelProjectContext.for_subsystem(
        subsystem,
        project_root=project_root,
    )
    return ctx.geometry_report_path


def _resolve_step_path(step_path: str) -> Path:
    if step_path.startswith(_CACHE_URI_PREFIX):
        from adapters.parts.vendor_synthesizer import resolve_cache_path

        cache_rel = step_path[len(_CACHE_URI_PREFIX) :].replace("\\", "/")
        return resolve_cache_path(cache_rel)

    expanded = os.path.expandvars(os.path.expanduser(str(step_path)))
    p = Path(expanded)
    if p.is_absolute():
        return p
    return _project_root() / p


def _quality_counts(decisions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        quality = str(decision.get("geometry_quality") or "unknown")
        counts[quality] = counts.get(quality, 0) + 1
    return dict(
        sorted(
            counts.items(),
            key=lambda item: (-_QUALITY_ORDER.get(item[0], -1), item[0]),
        )
    )


def _audit_item(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "part_no": decision.get("part_no") or "",
        "name_cn": decision.get("name_cn") or "",
        "geometry_quality": decision.get("geometry_quality") or "unknown",
        "geometry_source": decision.get("geometry_source") or "",
        "adapter": decision.get("adapter") or "",
        "source_tag": decision.get("source_tag") or "",
        "step_path": decision.get("step_path"),
    }


def build_model_audit(
    report: dict[str, Any],
    *,
    report_path: Path,
    subsystem: str | None = None,
) -> dict[str, Any]:
    """Build a normalized audit payload from an existing geometry report."""
    decisions = report.get("decisions") or []
    if not isinstance(decisions, list):
        decisions = []
    decisions = [d for d in decisions if isinstance(d, dict)]

    review_required: list[dict[str, Any]] = []
    missing_step_paths: list[dict[str, Any]] = []
    for decision in decisions:
        quality = str(decision.get("geometry_quality") or "unknown")
        if decision.get("requires_model_review") is True or quality in {"D", "E"}:
            review_required.append(_audit_item(decision))

        step_path = decision.get("step_path")
        if step_path:
            resolved = _resolve_step_path(str(step_path))
            if not resolved.is_file():
                item = _audit_item(decision)
                item["resolved_step_path"] = str(resolved)
                missing_step_paths.append(item)

    quality_counts = _quality_counts(decisions)
    worst_quality = "unknown"
    for quality in quality_counts:
        if worst_quality == "unknown" or _QUALITY_ORDER.get(
            quality, 0
        ) < _QUALITY_ORDER.get(worst_quality, 0):
            worst_quality = quality

    if review_required:
        status = "review_required"
    elif missing_step_paths:
        status = "missing_step"
    else:
        status = "pass"

    return {
        "schema_version": 1,
        "status": status,
        "subsystem": subsystem,
        "report_path": str(report_path),
        "total": len(decisions),
        "quality_counts": quality_counts,
        "worst_quality": worst_quality,
        "review_required_count": len(review_required),
        "missing_step_count": len(missing_step_paths),
        "review_required": review_required,
        "missing_step_paths": missing_step_paths,
    }


def _print_text(payload: dict[str, Any]) -> None:
    subsystem = payload.get("subsystem") or "(report)"
    print(f"=== model-audit: {subsystem} ===")
    print(f"geometry_report: {payload['report_path']}")
    print(f"status: {payload['status']}")
    print(f"total: {payload['total']}")
    counts = payload.get("quality_counts") or {}
    if counts:
        print("quality: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        for quality in counts:
            description = _QUALITY_DESCRIPTIONS.get(str(quality))
            if description:
                print(f"  {description}")
    print(f"review_required: {payload['review_required_count']}")
    print(f"missing_step_paths: {payload['missing_step_count']}")

    if payload.get("review_required"):
        print()
        print("Parts requiring model review:")
        for item in payload["review_required"]:
            print(
                "  - "
                f"{item['part_no']} {item['name_cn']} | "
                f"quality={item['geometry_quality']} "
                f"source={item['geometry_source']} "
                f"adapter={item['adapter']}"
            )

    if payload.get("missing_step_paths"):
        print()
        print("Missing STEP paths:")
        for item in payload["missing_step_paths"]:
            print(
                "  - "
                f"{item['part_no']} {item['name_cn']} -> "
                f"{item['resolved_step_path']}"
            )

    if payload["status"] != "pass":
        print()
        print("Next:")
        print("  - 为 review_required 零件提供可信 STEP，或补充 parts_library.yaml 映射。")
        print("  - 通过 spec supplements 的 model_choices 写入用户选择后重新 codegen。")


def run_model_audit(args: argparse.Namespace) -> int:
    try:
        report_path = _resolve_report_path(args)
    except ValueError as exc:
        print(f"[model-audit] {exc}", file=sys.stderr)
        return 2

    if not report_path.is_file():
        print(
            f"[model-audit] geometry_report.json 不存在: {report_path}",
            file=sys.stderr,
        )
        return 2

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[model-audit] geometry_report.json 不是合法 JSON: {exc}", file=sys.stderr)
        return 2

    payload = build_model_audit(
        report,
        report_path=report_path,
        subsystem=getattr(args, "subsystem", None),
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)

    if getattr(args, "strict", False) and payload["status"] != "pass":
        return 1
    return 0
