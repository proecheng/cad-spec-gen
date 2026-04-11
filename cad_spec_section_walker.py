# cad_spec_section_walker.py
"""Stateful Markdown section walker that attributes envelope markers to BOM
assemblies via 4-tier hybrid matching.

See docs/superpowers/specs/2026-04-12-section-header-walker-design.md for
the design rationale, adversarial review findings, and invariants.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger("cad_spec_section_walker")

# ─── Default vocabulary (GISBOT) — overridable via constructor kwargs ───────

_DEFAULT_TRIGGER_TERMS: tuple[str, ...] = ("模块包络尺寸",)

_DEFAULT_STATION_PATTERNS: list[tuple[str, str]] = [
    (r"工位\s*(\d+)", "工位"),
    (r"第\s*(\d+)\s*级", "级"),
    (r"模块\s*(\d+)", "模块"),
    (r"第\s*(\d+)\s*部分", "部分"),
]

_DEFAULT_AXIS_LABEL: str = "宽×深×高"

# ─── Tunable thresholds ─────────────────────────────────────────────────────

CONFIDENCE_VERIFY_THRESHOLD: float = 0.75
TIER2_SUBSEQUENCE_CONFIDENCE: float = 0.85
TIER3_JACCARD_THRESHOLD: float = 0.5
AMBIGUITY_GAP: float = 0.1

# ─── Legend blocks rendered into §6.4 by cad_spec_gen.py ────────────────────

TIER_LEGEND_MD: str = (
    "- **来源** `P1:...` = 参数表 | `P2:walker:tier0` = 历史 part_no 上下文扫描 (回归保护)\n"
    "- **来源** `P2:walker:tier1` = 结构编号精确匹配 | `tier2` = 字符/单词子序列 | "
    "`tier3` = Jaccard 相似度"
)

CONFIDENCE_LEGEND_MD: str = (
    "- **置信度**: tier0/tier1 = 1.00 (精确); tier2 = 0.85 (高); "
    "tier3 = 原始 Jaccard 分数. <0.75 建议人工验证."
)

GRANULARITY_LEGEND_MD: str = (
    "- **粒度**: `station_constraint` = 工位级外包络 (模块必须装入); "
    "`part_envelope` = 单件本体尺寸.\n"
    "  **禁止**使用 `station_constraint` 尺寸作为单个采购件的建模尺寸."
)

# ─── Machine-readable result codes ──────────────────────────────────────────

WalkerReason = Literal[
    "tier0_context_window_match",
    "tier1_unique_match",
    "tier1_ambiguous_multiple_bom",
    "tier2_unique_subsequence",
    "tier2_density_tie",
    "tier2_no_cjk_content",
    "tier3_jaccard_match",
    "tier3_jaccard_tie",
    "tier3_below_threshold",
    "tier3_empty_tokens",
    "no_parent_section",
    "empty_bom",
    "all_tiers_abstained",
    "unrecognized_axis_label",
]

UNMATCHED_SUGGESTIONS: dict[str, str] = {
    "no_parent_section": "包络位于任何章节标题之前. 检查文档结构, 或将包络移到对应工位章节内.",
    "tier1_ambiguous_multiple_bom": "章节编号匹配到 {n} 个 BOM 行. 在源文档章节标题加入区分关键词.",
    "tier2_density_tie": "章节标题与 {n} 个 BOM 行子序列匹配: {candidates}. 添加更具体的章节命名.",
    "tier3_jaccard_tie": "章节标题与 {n} 个 BOM 行 Jaccard 相似度并列. 添加更具体的章节命名.",
    "tier3_below_threshold": ("所有 BOM 行 Jaccard 分数 < 0.5. "
                               "检查章节标题是否使用 BOM 中出现的关键词."),
    "all_tiers_abstained": "四个匹配层全部放弃. 检查章节标题与 BOM 名称是否差异过大.",
    "empty_bom": "BOM 为空. 检查 BOM 抽取步骤是否正常.",
    "unrecognized_axis_label": "轴向标签不在已知映射表. 参见设计规格 §5.1 轴向标签表.",
}

# ─── Dataclasses ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MatchResult:
    """Result of a single tier's attempt to match a header or context to BOM."""
    pno: str
    tier: int                # 0 / 1 / 2 / 3
    confidence: float        # 0.0 – 1.0
    reason: str              # WalkerReason literal value


@dataclass(frozen=True)
class SectionFrame:
    """One level of the section-header stack."""
    level: int                          # 1–6 markdown, 100 = standalone bold
    header_text: str                    # normalized header content
    match: MatchResult | None           # assembly match if any tier fired


@dataclass(frozen=True)
class EnvelopeData:
    """Immutable envelope data. Always stored in canonical (X, Y, Z) axis
    order — the walker rewrites source-order dims using the §5.1 axis label
    table at extraction time. Downstream consumers rely on dims[0]=X,
    dims[1]=Y, dims[2]=Z without re-parsing axis_label.
    """
    type: Literal["box", "cylinder"]
    dims: tuple[tuple[str, float], ...]
    axis_label: str | None = None

    def dims_dict(self) -> dict[str, float]:
        return dict(self.dims)


@dataclass(frozen=True)
class WalkerOutput:
    """One envelope attribution attempt (matched or unmatched)."""
    matched_pno: str | None
    envelope_type: Literal["box", "cylinder"]
    dims: tuple[tuple[str, float], ...]
    tier: int | None
    confidence: float
    reason: str                  # WalkerReason literal
    header_text: str
    line_number: int
    granularity: Literal["station_constraint", "part_envelope", "component"]
    axis_label: str | None = None
    source_line: str = ""
    candidates: tuple[tuple[str, float], ...] = ()

    def dims_dict(self) -> dict[str, float]:
        return dict(self.dims)


@dataclass(frozen=True)
class WalkerStats:
    """Counters surfaced in the rendered §6.4 footer."""
    total_envelopes: int
    matched_count: int
    unmatched_count: int
    tier_histogram: tuple[tuple[int, int], ...]
    axis_label_default_count: int
    unmatched_reasons: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class WalkerReport:
    """Return value of extract_part_envelopes() alongside the envelope dict."""
    unmatched: tuple[WalkerOutput, ...]
    stats: WalkerStats | None
    feature_flag_enabled: bool
    runtime_error: str | None = None


# ─── Axis label canonicalization ────────────────────────────────────────────

_AXIS_LABEL_BOX_MAP: dict[str, tuple[int, int, int]] = {
    # Map normalized label → (raw_index_for_X, raw_index_for_Y, raw_index_for_Z)
    # "宽×深×高" means raw[0]=width=X, raw[1]=depth=Y, raw[2]=height=Z → (0, 1, 2)
    "宽×深×高": (0, 1, 2),
    "W×D×H": (0, 1, 2),
    "长×宽×高": (0, 1, 2),   # length=X, width=Y, height=Z (position-0 is X regardless)
    "L×W×H": (0, 1, 2),
    # Swapped orders
    "深×宽×高": (1, 0, 2),   # raw[0]=depth→Y, raw[1]=width→X, raw[2]=height→Z
    "宽×高×深": (0, 2, 1),   # raw[0]=width→X, raw[1]=height→Z, raw[2]=depth→Y
    "高×宽×深": (1, 2, 0),
    "长×高×宽": (0, 2, 1),
}


def _canonicalize_box_axes(
    raw: tuple[float, float, float],
    label: str,
) -> tuple[tuple[str, float], ...] | None:
    """Map source-order box dims to canonical (X, Y, Z) order via the label map.

    Returns None when the label is not in _AXIS_LABEL_BOX_MAP — the caller
    must surface this as UNMATCHED with reason='unrecognized_axis_label'
    rather than silently defaulting.
    """
    label_norm = re.sub(r"\s+", "", label or "")
    order = _AXIS_LABEL_BOX_MAP.get(label_norm)
    if order is None:
        return None
    return (
        ("x", raw[order[0]]),
        ("y", raw[order[1]]),
        ("z", raw[order[2]]),
    )


# ─── Envelope regex builder ─────────────────────────────────────────────────


def _build_envelope_regexes(
    trigger_terms: tuple[str, ...],
) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Build (box_regex, cylinder_regex) for a given trigger-term set.

    Handles bold-before-colon (`模块包络尺寸**：`), bold-around-value
    (`模块包络尺寸：**60×40×290mm**`), and an optional parenthetical axis label.

    Called per-walker-instance inside SectionWalker.__init__ — NO module-level
    cache. This is load-bearing for G12 cross-subsystem isolation.
    """
    trigger = "|".join(re.escape(t) for t in trigger_terms)
    prelude = fr"(?:{trigger})(?:\*\*)?[：:]\s*(?:\*\*)?\s*"
    # optional closing bold + optional parenthetical label (supports both ASCII and full-width parens)
    suffix = r"\s*(?:\*\*)?(?:\s*[(（]([^)）]+)[)）])?"

    box_body = (
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*mm"
    )
    cyl_body = (
        r"[ΦφØ∅](\d+(?:\.\d+)?)\s*[×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*mm"
    )
    box_re = re.compile(prelude + box_body + suffix)      # groups: 1=w 2=d 3=h 4=axis_label
    cyl_re = re.compile(prelude + cyl_body + suffix)      # groups: 1=dia 2=h 3=axis_label
    return box_re, cyl_re
