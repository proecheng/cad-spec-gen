"""3 层确定性产品目标解析器。

层 1：subsystem class 识别（subsystem_keywords.json）
层 2：KPI 抽取（kpi_patterns.json，regex + context_terms 双条件）
层 3：歧义检测（数字共享按 char 距离独立判定）
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from tools.project_guide_dict import ProductGoalDictionary, load_dictionary


SubsystemStatus = Literal["implemented", "not_yet_implemented", "ambiguous", "unknown"]
KpiStatus = Literal["extracted", "ambiguous", "missing"]


@dataclass(frozen=True)
class KpiExtraction:
    """单个 KPI 抽取结果。"""

    kpi_name: str
    value: float | tuple[float, float] | None
    unit: str | None
    evidence_token: str | None
    rule: str
    status: KpiStatus


@dataclass(frozen=True)
class ProductGoalParseResult:
    """产品目标解析最终结果。"""

    raw_text: str
    subsystem_class: str | None
    subsystem_status: SubsystemStatus
    kpis: dict[str, KpiExtraction] = field(default_factory=dict)
    parser_evidence: list[dict[str, Any]] = field(default_factory=list)


def parse_product_goal(
    *,
    text: str,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float | tuple[float, float]] | None = None,
    dictionary: ProductGoalDictionary | None = None,
) -> ProductGoalParseResult:
    """3 层确定性解析。Task 4 实施层 1 subsystem class 识别。"""
    if dictionary is None:
        dictionary = load_dictionary()

    if not text or not text.strip():
        return ProductGoalParseResult(
            raw_text=text,
            subsystem_class=None,
            subsystem_status="unknown",
        )

    # NFKC normalize（半/全角统一），保留原大小写到 evidence
    normalized = unicodedata.normalize("NFKC", text)
    evidence: list[dict[str, Any]] = []

    # confirmed_subsystem 强制覆盖（外部已确认的子系统直接采用，跳过启发式）
    if confirmed_subsystem and confirmed_subsystem in dictionary.subsystem_keywords:
        subsystem_class: str | None = confirmed_subsystem
        subsystem_status: SubsystemStatus = dictionary.subsystem_keywords[confirmed_subsystem]["status"]
        evidence.append({
            "token": confirmed_subsystem,
            "matched": "subsystem_class",
            "rule": "confirmed_subsystem",
        })
    else:
        subsystem_class, subsystem_status = _identify_subsystem(
            normalized, dictionary, evidence
        )

    return ProductGoalParseResult(
        raw_text=text,
        subsystem_class=subsystem_class,
        subsystem_status=subsystem_status,
        parser_evidence=evidence,
    )


def _identify_subsystem(
    normalized: str,
    dictionary: ProductGoalDictionary,
    evidence: list[dict[str, Any]],
) -> tuple[str | None, SubsystemStatus]:
    """层 1：primary 命中即定类；只 supporting → ambiguous；全无 → unknown。

    - 单一 primary 命中：返回该子系统及其状态
    - 多 primary 命中（跨子系统）：ambiguous（候选证据全部入 evidence）
    - 仅 supporting 命中：ambiguous
    - 全无命中：unknown
    """
    primary_hits: list[tuple[str, str]] = []
    supporting_hits: list[tuple[str, str]] = []

    for name, entry in dictionary.subsystem_keywords.items():
        primary_match = None
        for term in entry["primary_terms"]:
            if term in normalized:
                primary_match = term
                break

        if primary_match is not None:
            primary_hits.append((name, primary_match))
            continue

        # 仅当 primary 未命中时再检查 supporting，避免重复
        for term in entry.get("supporting_terms", []):
            if term in normalized:
                supporting_hits.append((name, term))
                break

    if len(primary_hits) == 1:
        name, token = primary_hits[0]
        evidence.append({
            "token": token,
            "matched": "subsystem_class",
            "rule": f"primary_terms:{name}",
        })
        return name, dictionary.subsystem_keywords[name]["status"]

    if len(primary_hits) > 1:
        for name, token in primary_hits:
            evidence.append({
                "token": token,
                "matched": "subsystem_class_candidate",
                "rule": f"primary_terms:{name}",
            })
        return None, "ambiguous"

    if supporting_hits:
        for name, token in supporting_hits:
            evidence.append({
                "token": token,
                "matched": "subsystem_class_candidate",
                "rule": f"supporting_terms:{name}",
            })
        return None, "ambiguous"

    return None, "unknown"


__all__ = [
    "KpiExtraction",
    "ProductGoalParseResult",
    "SubsystemStatus",
    "KpiStatus",
    "parse_product_goal",
]
