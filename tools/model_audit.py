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
from tools.path_policy import project_relative

_QUALITY_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "unknown": 0}
_QUALITY_DESCRIPTIONS = {
    "B": "B = curated parametric template; visually and dimensionally useful, not vendor STEP.",
}
_QUALITY_SCALE = {
    "A": {
        "label": "A级：可信真实/高保真模型",
        "photoreal_risk": "low",
        "review_policy": "通常可直接进入照片级流程，最终交付前确认授权和装配尺寸。",
    },
    "B": {
        "label": "B级：可复用参数化/模型库模板",
        "photoreal_risk": "medium",
        "review_policy": "可进入照片级流程，但建议确认关键外形和品牌细节。",
    },
    "C": {
        "label": "C级：简化模板",
        "photoreal_risk": "high",
        "review_policy": "建议替换为可信 STEP 或人工确认外形后再做最终交付。",
    },
    "D": {
        "label": "D级：简化占位 fallback",
        "photoreal_risk": "high",
        "review_policy": "不建议作为最终照片级输入；应导入真实模型或补模型库规则。",
    },
    "E": {
        "label": "E级：缺失或不可用模型",
        "photoreal_risk": "blocked",
        "review_policy": "会阻断照片级交付；需要先补充可信模型。",
    },
    "unknown": {
        "label": "未知等级：缺少模型质量记录",
        "photoreal_risk": "unknown",
        "review_policy": "需要先复查模型来源，再判断是否可交付。",
    },
}
_SOURCE_KIND_INFO = {
    "real_step": {
        "label": "真实/高保真 STEP 模型",
        "suggested_action": "继续后续 Photo3D 阶段；最终交付前保留来源证据。",
    },
    "user_step": {
        "label": "用户提供 STEP 模型",
        "suggested_action": "确认文件存在、授权可用并与装配尺寸一致。",
    },
    "library_model": {
        "label": "外部参数化模型库",
        "suggested_action": "确认尺寸、版本和库来源适合当前产品。",
    },
    "parametric_template": {
        "label": "通用参数化模板",
        "suggested_action": "可继续预览；最终照片级交付前确认外形是否足够真实。",
    },
    "simplified_template": {
        "label": "简化模板",
        "suggested_action": "建议导入可信 STEP，或人工确认该简化外形可接受。",
    },
    "primitive_fallback": {
        "label": "简化占位 fallback",
        "suggested_action": "应补充真实模型、模型库规则或用户 STEP。",
    },
    "missing": {
        "label": "未生成模型",
        "suggested_action": "先导入可信 STEP 或补充 parts_library.yaml 映射。",
    },
    "unknown": {
        "label": "未知模型来源",
        "suggested_action": "先运行 codegen/model-audit 复查模型来源。",
    },
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
    return _resolve_step_path_for_root(step_path, _project_root())


def _resolve_step_path_for_root(step_path: str, project_root: Path) -> Path:
    if step_path.startswith(_CACHE_URI_PREFIX):
        from adapters.parts.vendor_synthesizer import resolve_cache_path

        cache_rel = step_path[len(_CACHE_URI_PREFIX) :].replace("\\", "/")
        return resolve_cache_path(cache_rel)

    expanded = os.path.expandvars(os.path.expanduser(str(step_path)))
    p = Path(expanded)
    if p.is_absolute():
        return p
    return project_root / p


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


def build_model_quality_summary(
    report: dict[str, Any],
    *,
    report_path: Path,
    source: str = "geometry_report",
    binding_status: str = "project_report",
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build an ordinary-user model quality view from existing model facts."""
    root = Path(project_root).resolve() if project_root is not None else _project_root()
    decisions = _valid_decisions(report)
    part_summaries = [_part_summary(decision, root) for decision in decisions]
    quality_counts = _summary_quality_counts(part_summaries)
    source_counts: dict[str, int] = {}
    for item in part_summaries:
        source_kind = str(item["source_kind"])
        source_counts[source_kind] = source_counts.get(source_kind, 0) + 1

    review_recommended_count = sum(
        1 for item in part_summaries if item["user_status"] != "ready"
    )
    blocking_count = sum(
        1 for item in part_summaries if item["user_status"] == "blocked"
    )
    readiness_status = _readiness_status(part_summaries)
    return {
        "schema_version": 1,
        "source": source,
        "source_report": _public_report_path(report_path, root),
        "binding_status": binding_status,
        "readiness_status": readiness_status,
        "photoreal_risk": _photoreal_risk(part_summaries, readiness_status),
        "ordinary_user_message": _summary_user_message(
            readiness_status,
            review_recommended_count=review_recommended_count,
            blocking_count=blocking_count,
        ),
        "total": len(part_summaries),
        "quality_counts": quality_counts,
        "source_counts": source_counts,
        "review_recommended_count": review_recommended_count,
        "blocking_count": blocking_count,
        "quality_scale": _QUALITY_SCALE,
        "part_summaries": part_summaries,
        "recommended_next_action": _recommended_next_action(
            readiness_status,
            part_summaries,
        ),
    }


def build_model_audit(
    report: dict[str, Any],
    *,
    report_path: Path,
    subsystem: str | None = None,
) -> dict[str, Any]:
    """Build a normalized audit payload from an existing geometry report."""
    decisions = _valid_decisions(report)

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

    payload = {
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
    payload["model_quality_summary"] = build_model_quality_summary(
        report,
        report_path=report_path,
    )
    return payload


def _valid_decisions(report: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = report.get("decisions") or []
    if not isinstance(decisions, list):
        return []
    return [d for d in decisions if isinstance(d, dict)]


def _summary_quality_counts(part_summaries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in part_summaries:
        quality = str(item.get("geometry_quality") or "unknown")
        counts[quality] = counts.get(quality, 0) + 1
    return dict(
        sorted(
            counts.items(),
            key=lambda item: (-_QUALITY_ORDER.get(item[0], -1), item[0]),
        )
    )


def _part_summary(decision: dict[str, Any], project_root: Path) -> dict[str, Any]:
    quality = str(decision.get("geometry_quality") or "unknown")
    if quality not in _QUALITY_SCALE:
        quality = "unknown"
    source_kind = _source_kind(decision)
    missing_step = _step_path_missing(decision, project_root)
    requires_review = bool(decision.get("requires_model_review")) or quality in {
        "C",
        "D",
        "E",
        "unknown",
    }
    if missing_step or quality == "E":
        user_status = "blocked"
    elif requires_review:
        user_status = "needs_review"
    else:
        user_status = "ready"

    source_info = _SOURCE_KIND_INFO[source_kind]
    item = {
        "part_no": decision.get("part_no") or "",
        "name_cn": decision.get("name_cn") or "",
        "geometry_quality": quality,
        "quality_label": _QUALITY_SCALE[quality]["label"],
        "geometry_source": decision.get("geometry_source") or "",
        "source_kind": source_kind,
        "source_label": source_info["label"],
        "adapter": decision.get("adapter") or "",
        "source_tag": decision.get("source_tag") or "",
        "validated": bool(decision.get("validated")),
        "requires_model_review": bool(decision.get("requires_model_review")),
        "missing_step": missing_step,
        "user_status": user_status,
        "user_message": _part_user_message(
            user_status,
            quality=quality,
            source_label=source_info["label"],
            missing_step=missing_step,
        ),
        "suggested_action": _part_suggested_action(
            user_status,
            quality=quality,
            source_action=source_info["suggested_action"],
            missing_step=missing_step,
        ),
    }
    public_step_path = _public_step_path(decision.get("step_path"), project_root)
    if public_step_path:
        item["public_step_path"] = public_step_path
    return item


def _source_kind(decision: dict[str, Any]) -> str:
    source = str(decision.get("geometry_source") or "").strip().upper()
    adapter = str(decision.get("adapter") or "").strip().lower()
    kind = str(decision.get("kind") or "").strip().lower()
    if source == "USER_STEP":
        return "user_step"
    if source in {"REAL_STEP", "SW_TOOLBOX_STEP", "STEP_POOL"} or kind == "step_import":
        return "real_step"
    if source in {"BD_WAREHOUSE", "PARTCAD"} or adapter in {"bd_warehouse", "partcad"}:
        return "library_model"
    if source == "PARAMETRIC_TEMPLATE":
        return "parametric_template"
    if source == "JINJA_TEMPLATE":
        return "simplified_template"
    if source == "JINJA_PRIMITIVE" or adapter == "jinja_primitive":
        return "primitive_fallback"
    if source == "MISSING" or adapter in {"(none)", "(skip)"}:
        return "missing"
    return "unknown"


def _step_path_missing(decision: dict[str, Any], project_root: Path) -> bool:
    step_path = decision.get("step_path")
    if not step_path:
        return False
    return not _resolve_step_path_for_root(str(step_path), project_root).is_file()


def _public_report_path(report_path: Path, project_root: Path) -> str:
    try:
        return project_relative(report_path, project_root)
    except ValueError:
        return report_path.name


def _public_step_path(step_path: Any, project_root: Path) -> str | None:
    if not step_path:
        return None
    raw = str(step_path)
    if raw.startswith(_CACHE_URI_PREFIX):
        return raw
    resolved = _resolve_step_path_for_root(raw, project_root)
    try:
        return project_relative(resolved, project_root)
    except ValueError:
        return None


def _readiness_status(part_summaries: list[dict[str, Any]]) -> str:
    if not part_summaries:
        return "not_available"
    if any(item["user_status"] == "blocked" for item in part_summaries):
        return "blocked"
    if any(item["user_status"] == "needs_review" for item in part_summaries):
        return "needs_review"
    return "ready"


def _photoreal_risk(
    part_summaries: list[dict[str, Any]],
    readiness_status: str,
) -> str:
    if readiness_status in {"blocked", "not_available"}:
        return readiness_status if readiness_status == "blocked" else "unknown"
    risks = [
        _QUALITY_SCALE.get(str(item.get("geometry_quality")), _QUALITY_SCALE["unknown"])[
            "photoreal_risk"
        ]
        for item in part_summaries
    ]
    if "high" in risks:
        return "high"
    if "medium" in risks:
        return "medium"
    if "unknown" in risks:
        return "unknown"
    return "low"


def _summary_user_message(
    readiness_status: str,
    *,
    review_recommended_count: int,
    blocking_count: int,
) -> str:
    if readiness_status == "ready":
        return "模型质量摘要显示所有零件都有可用模型，可继续照片级流程。"
    if readiness_status == "needs_review":
        return (
            f"模型质量摘要发现 {review_recommended_count} 个零件建议复核；"
            "最终照片级交付前应确认外形、尺寸和来源。"
        )
    if readiness_status == "blocked":
        return (
            f"模型质量摘要发现 {blocking_count} 个阻断项；"
            "请先补充可信模型或修正缺失 STEP。"
        )
    return "暂未找到模型质量决策；请先运行 codegen 生成 geometry_report.json。"


def _part_user_message(
    user_status: str,
    *,
    quality: str,
    source_label: str,
    missing_step: bool,
) -> str:
    if missing_step:
        return f"{source_label} 的文件路径当前不可用，不能作为照片级交付证据。"
    if user_status == "ready":
        return f"{source_label}，质量等级 {quality}，可继续作为照片级输入。"
    if user_status == "needs_review":
        return f"{source_label}，质量等级 {quality}，最终交付前建议复核。"
    return f"{source_label}，质量等级 {quality}，需要先补模型或替换来源。"


def _part_suggested_action(
    user_status: str,
    *,
    quality: str,
    source_action: str,
    missing_step: bool,
) -> str:
    if missing_step:
        return "重新导入该 STEP，或更新 parts_library.yaml 指向项目内可信文件。"
    if quality == "E":
        return "导入可信 STEP 或补充模型库规则后重新 codegen。"
    if user_status == "ready":
        return source_action
    return _QUALITY_SCALE[quality]["review_policy"]


def _recommended_next_action(
    readiness_status: str,
    part_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    if readiness_status == "blocked":
        if any(item["missing_step"] for item in part_summaries):
            return {
                "kind": "import_missing_models",
                "requires_user_confirmation": False,
                "message": "优先导入缺失 STEP 或修正模型库路径，然后重新 codegen/model-audit。",
            }
        return {
            "kind": "import_missing_models",
            "requires_user_confirmation": False,
            "message": "存在 E 级或缺失模型；请先导入可信模型或补模型库规则。",
        }
    if readiness_status == "needs_review":
        return {
            "kind": "review_models",
            "requires_user_confirmation": False,
            "message": "复核 C/D/unknown 或 requires_model_review 零件，再决定是否进入最终照片级交付。",
        }
    if readiness_status == "ready":
        return {
            "kind": "continue_photo3d",
            "requires_user_confirmation": False,
            "message": "可继续 Phase 4/5/6；最终交付仍需保留模型来源证据。",
        }
    return {
        "kind": "none",
        "requires_user_confirmation": False,
        "message": "暂无模型质量报告；请先运行 codegen。",
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
