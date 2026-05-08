"""3 层确定性产品目标解析器。

层 1：subsystem class 识别（subsystem_keywords.json）
层 2：KPI 抽取（kpi_patterns.json，regex + context_terms 双条件）
层 3：歧义检测（数字共享按 char 距离独立判定）
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from tools.project_guide_dict import ProductGoalDictionary, load_dictionary


SubsystemStatus = Literal["implemented", "not_yet_implemented", "ambiguous", "unknown"]
KpiStatus = Literal["extracted", "ambiguous", "missing"]

# 数字与 context_term ±20 字符内才视为同一语义；超距离视为不相关，避免误抽
_DISTANCE_WINDOW = 20


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

    # 层 2：仅对 implemented 子系统抽 KPI；其余状态 kpis 保持空 dict
    if subsystem_class and subsystem_status == "implemented":
        kpis = _extract_kpis_for_subsystem(
            text, normalized, subsystem_class, dictionary, evidence
        )
        # 外部已确认的 KPI 直接覆盖，跳过启发式
        if confirmed_kpis:
            for k, v in confirmed_kpis.items():
                if k in kpis:
                    kpis[k] = KpiExtraction(
                        kpi_name=k,
                        value=v,
                        unit=kpis[k].unit,
                        evidence_token=str(v),
                        rule="confirmed_kpi",
                        status="extracted",
                    )
    else:
        kpis = {}

    return ProductGoalParseResult(
        raw_text=text,
        subsystem_class=subsystem_class,
        subsystem_status=subsystem_status,
        kpis=kpis,
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


def _extract_kpis_for_subsystem(
    raw_text: str,
    normalized: str,
    subsystem_class: str,
    dictionary: ProductGoalDictionary,
    evidence: list[dict[str, Any]],
) -> dict[str, KpiExtraction]:
    """对 implemented 子系统跑所有 KPI 抽取，未命中标 missing。"""
    extractions: dict[str, KpiExtraction] = {}
    kpi_specs = dictionary.kpi_patterns[subsystem_class]

    for kpi_name, spec in kpi_specs.items():
        extracted = _extract_single_kpi(raw_text, normalized, kpi_name, spec, evidence)
        extractions[kpi_name] = extracted
    return extractions


def _raw_token_for_match(
    raw_text: str,
    normalized: str,
    match: "re.Match[str]",
) -> str:
    """从原文取 match 区间对应的子串。

    NFKC 在 ASCII 路径与全角→半角场景下保持 char 数 1:1
    （len(raw)==len(normalized)），此时 match.start()/end() 在两个串上索引等价，
    可直接切 raw_text。极少数 NFKC 拆分（⅔ → 2/3、㎡ → m2）会让 normalized 比
    raw_text 长，索引域错位 → fallback 到 match.group(0)（normalized 串上 token，
    与现状等价不优于 normalized）。
    """
    if len(raw_text) == len(normalized):
        return raw_text[match.start():match.end()]
    return match.group(0)


def _extract_single_kpi(
    raw_text: str,
    normalized: str,
    kpi_name: str,
    spec: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> KpiExtraction:
    """单 KPI 抽取：regex 短路命中 + ±20 字符 context_terms 距离判定。

    schema v2：spec["regex"] 为 [{pattern, factor}] 对象数组；factor 直接随 entry 携带。
    """
    context_terms = spec["context_terms"]
    unit = spec["unit"]
    value_shape = spec.get("value_shape", "single")

    # 收集所有 context_terms 的出现位置（同 term 多次出现亦记录）
    context_positions: list[int] = []
    for term in context_terms:
        idx = 0
        while True:
            pos = normalized.find(term, idx)
            if pos < 0:
                break
            context_positions.append(pos)
            idx = pos + len(term)

    if not context_positions:
        return KpiExtraction(
            kpi_name=kpi_name,
            value=None,
            unit=unit,
            evidence_token=None,
            rule="no_context",
            status="missing",
        )

    # 按 yaml 顺序短路 regex（首条命中即返回）
    for regex_idx, regex_entry in enumerate(spec["regex"]):
        pattern = regex_entry["pattern"]
        factor = regex_entry["factor"]
        compiled = re.compile(pattern)
        for match in compiled.finditer(normalized):
            number_start = match.start()
            number_end = match.end()
            # 数字块端点距 context 任一端点最近距离
            min_dist = min(
                min(abs(cp - number_start), abs(cp - number_end))
                for cp in context_positions
            )
            if min_dist > _DISTANCE_WINDOW:
                continue

            value: float | tuple[float, float]
            if value_shape == "pair":
                value = (float(match.group(1)), float(match.group(2)))
            else:
                raw = float(match.group(1))
                value = raw * factor   # factor=1 时不变

            raw_token = _raw_token_for_match(raw_text, normalized, match)
            evidence.append({
                "token": raw_token,
                "matched": kpi_name,
                "rule": f"regex+context:{context_terms[0]}",
                "regex_index": regex_idx,
            })
            return KpiExtraction(
                kpi_name=kpi_name,
                value=value,
                unit=unit,
                evidence_token=raw_token,
                rule=f"regex+context:{context_terms[0]}",
                status="extracted",
            )

    return KpiExtraction(
        kpi_name=kpi_name,
        value=None,
        unit=unit,
        evidence_token=None,
        rule="no_match",
        status="missing",
    )


__all__ = [
    "KpiExtraction",
    "ProductGoalParseResult",
    "SubsystemStatus",
    "KpiStatus",
    "parse_product_goal",
]
