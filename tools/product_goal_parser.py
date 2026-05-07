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
    """3 层确定性解析。Task 3 仅占位，后续 task 4-6 补 3 层逻辑。"""
    if dictionary is None:
        dictionary = load_dictionary()

    if not text or not text.strip():
        return ProductGoalParseResult(
            raw_text=text,
            subsystem_class=None,
            subsystem_status="unknown",
        )

    # NFKC normalize（半/全角统一），保留原大小写到 evidence
    _normalized = unicodedata.normalize("NFKC", text)

    # 占位：后续 task 4-6 补 3 层逻辑
    return ProductGoalParseResult(
        raw_text=text,
        subsystem_class=None,
        subsystem_status="unknown",
    )


__all__ = [
    "KpiExtraction",
    "ProductGoalParseResult",
    "SubsystemStatus",
    "KpiStatus",
    "parse_product_goal",
]
