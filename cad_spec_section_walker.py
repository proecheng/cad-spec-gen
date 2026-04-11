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


# ─── Section header parsing ─────────────────────────────────────────────────

_HASH_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_STANDALONE_BOLD_RE = re.compile(r"^\*\*([^*]+)\*\*\s*$")

BOLD_HEADER_LEVEL: int = 100  # sentinel: always deeper than any markdown hash


def _normalize_header(text: str) -> str:
    """Strip markdown artifacts and collapse whitespace; return the semantic
    content of the header, preserving original characters for tier 2/3
    matching which operates on character content."""
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_section_header(line: str) -> tuple[int, str] | None:
    """Return (level, normalized_text) or None.

    - Markdown `#` headers (levels 1-6) → (1..6, text)
    - Standalone `**bold**` on its own line → (BOLD_HEADER_LEVEL, text)
    - Bullet-list bold items (`- **label**:value`) → None (property label, not header)
    - Anything else → None
    """
    if not line or not line.strip():
        return None
    m = _HASH_HEADER_RE.match(line)
    if m:
        level = len(m.group(1))
        return (level, _normalize_header(m.group(2)))
    m = _STANDALONE_BOLD_RE.match(line)
    if m:
        return (BOLD_HEADER_LEVEL, _normalize_header(m.group(1)))
    return None


# ─── Tier 1: structured pattern matching ────────────────────────────────────


def _match_by_pattern(
    header: str,
    bom_data: dict,
    station_patterns: list[tuple[str, str]],
) -> MatchResult | None:
    """Extract an (index, category) from a structured pattern and find the
    matching BOM assembly. Abstains (returns None) on ambiguity AT THE
    FIRST pattern that matches — does NOT fall through to the next
    pattern, which would produce false-confident matches.

    Each entry in station_patterns is (header_regex, category_prefix).
    BOM names are scanned using both the category_prefix (for prefix-style
    patterns like 工位N) and the header_regex itself (for interleaved patterns
    like 第N级, 第N部分) to ensure consistent matching across all pattern types.
    """
    for regex, category in station_patterns:
        m = re.search(regex, header)
        if not m:
            continue
        idx = int(m.group(1))
        # Build two candidate regexes:
        # 1. category-prefix style: "工位\s*(\d+)" for names like "工位1涂抹模块"
        # 2. header-regex reuse: same pattern applied to BOM names (handles
        #    interleaved patterns like "第\s*(\d+)\s*级" for "第2级支撑")
        prefix_re = re.compile(fr"{re.escape(category)}\s*(\d+)")
        full_re = re.compile(regex)
        matching = []
        for assy in bom_data.get("assemblies", []):
            name = assy.get("name", "")
            found = False
            m2 = prefix_re.search(name)
            if m2 and int(m2.group(1)) == idx:
                found = True
            if not found:
                m3 = full_re.search(name)
                if m3 and int(m3.group(1)) == idx:
                    found = True
            if found:
                matching.append(assy)
        if len(matching) == 0:
            # This pattern fired but BOM has no row — fall through to next pattern.
            continue
        if len(matching) >= 2:
            # Ambiguity at THIS pattern — abstain entirely. Returning None
            # hands off to Tier 2, NOT to the next pattern in the list.
            return None
        return MatchResult(
            pno=matching[0]["part_no"],
            tier=1,
            confidence=1.0,
            reason="tier1_unique_match",
        )
    return None


# ─── Tier 2: dual-path subsequence matching ─────────────────────────────────

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _cjk_only(text: str) -> str:
    return "".join(_CJK_RE.findall(text))


def _ascii_words(text: str) -> list[str]:
    return [w.lower() for w in _ASCII_WORD_RE.findall(text) if len(w) >= 2]


def _is_char_subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


def _is_word_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(w in it for w in needle)


def _match_by_subsequence(header: str, bom_data: dict) -> MatchResult | None:
    """Tier 2: CJK character subsequence OR ASCII word subsequence.

    Dual-path: runs both paths in parallel and picks the better density.
    Abstains on ties (density gap < AMBIGUITY_GAP).
    """
    header_cjk = _cjk_only(header)
    header_words = _ascii_words(header)

    matches: list[tuple[str, float]] = []
    for assy in bom_data.get("assemblies", []):
        name = assy.get("name", "")
        bom_cjk = _cjk_only(name)
        bom_words = _ascii_words(name)

        best_density = 0.0
        if bom_cjk and header_cjk and _is_char_subsequence(bom_cjk, header_cjk):
            best_density = max(best_density, len(bom_cjk) / max(len(header_cjk), 1))
        if bom_words and header_words and _is_word_subsequence(bom_words, header_words):
            best_density = max(best_density, len(bom_words) / max(len(header_words), 1))

        if best_density > 0:
            matches.append((assy["part_no"], best_density))

    if not matches:
        return None

    # Stable deterministic sort: density desc, then part_no asc.
    matches.sort(key=lambda m: (-m[1], m[0]))
    if len(matches) == 1:
        return MatchResult(
            pno=matches[0][0], tier=2,
            confidence=TIER2_SUBSEQUENCE_CONFIDENCE,
            reason="tier2_unique_subsequence",
        )

    top_pno, top_dens = matches[0]
    _, runner_dens = matches[1]
    if abs(top_dens - runner_dens) < AMBIGUITY_GAP:
        return None  # tie → abstain

    return MatchResult(
        pno=top_pno, tier=2,
        confidence=TIER2_SUBSEQUENCE_CONFIDENCE,
        reason="tier2_unique_subsequence",
    )


# ─── Tier 3: Jaccard mixed-token similarity ─────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Produce CJK bigrams + ASCII words (length ≥ 2, lowercased)."""
    tokens: set[str] = set()
    for run in _CJK_RE.findall(text):
        for i in range(len(run) - 1):
            tokens.add(run[i:i + 2])
    for word in _ASCII_WORD_RE.findall(text):
        if len(word) >= 2:
            tokens.add(word.lower())
    return tokens


def _match_by_jaccard(
    header: str,
    bom_data: dict,
    threshold: float = TIER3_JACCARD_THRESHOLD,
) -> MatchResult | None:
    """Tier 3: mixed CJK bigram + ASCII word Jaccard similarity.

    Collects all above-threshold scores, sorts with deterministic tie-break
    `(-score, pno)`, abstains on exact ties and near-ties.
    """
    header_tokens = _tokenize(header)
    if not header_tokens:
        return None

    scored: list[tuple[str, float]] = []
    for assy in bom_data.get("assemblies", []):
        bom_tokens = _tokenize(assy.get("name", ""))
        if not bom_tokens:
            continue
        intersection = len(header_tokens & bom_tokens)
        union = len(header_tokens | bom_tokens)
        score = intersection / union if union > 0 else 0.0
        if score >= threshold:
            scored.append((assy["part_no"], score))

    if not scored:
        return None

    scored.sort(key=lambda x: (-x[1], x[0]))
    best_pno, best_score = scored[0]
    if len(scored) >= 2:
        _, runner_score = scored[1]
        if runner_score == best_score:
            return None
        if (best_score - runner_score) < AMBIGUITY_GAP:
            return None

    return MatchResult(
        pno=best_pno, tier=3, confidence=best_score,
        reason="tier3_jaccard_match",
    )


# ─── Two-phase match dispatchers ────────────────────────────────────────────


def _match_header(
    header: str,
    bom_data: dict,
    station_patterns: list[tuple[str, str]],
) -> MatchResult | None:
    """Phase A: run Tier 1 → 2 → 3 on a section header.

    Called at header-push time inside SectionWalker.walk(). The first
    non-None tier result wins; returns None when all three abstain.
    """
    result = _match_by_pattern(header, bom_data, station_patterns)
    if result is not None:
        return result
    result = _match_by_subsequence(header, bom_data)
    if result is not None:
        return result
    return _match_by_jaccard(header, bom_data)


def _match_context(
    context: str,
    bom_pno_prefixes: tuple[str, ...],
    bom_data: dict,
) -> MatchResult | None:
    """Phase B: Tier 0 — lazy import of the legacy helper.

    Called at envelope-emit time with the 500-char preceding window.
    Imports `_find_nearest_assembly` locally because `cad_spec_extractors`
    imports this module transitively at P2 integration time — module-level
    import would create a cycle.
    """
    from cad_spec_extractors import _find_nearest_assembly
    pno = _find_nearest_assembly(context, bom_data, bom_pno_prefixes)
    if pno is None:
        return None
    return MatchResult(
        pno=pno, tier=0, confidence=1.0,
        reason="tier0_context_window_match",
    )


# ─── SectionWalker class ────────────────────────────────────────────────────


class SectionWalker:
    """Stateful walker that tracks active section headers + attributes
    envelope markers to BOM assemblies via 4-tier hybrid matching.

    Construction is the only state boundary — one instance per
    extract_part_envelopes() call. NO module-level mutable state.
    """

    def __init__(
        self,
        lines: list[str],
        bom_data: dict,
        *,
        trigger_terms: tuple[str, ...] = _DEFAULT_TRIGGER_TERMS,
        station_patterns: list[tuple[str, str]] | None = None,
        axis_label_default: str = _DEFAULT_AXIS_LABEL,
        bom_pno_prefixes: tuple[str, ...] | None = None,
    ) -> None:
        self.lines = list(lines)
        self.bom_data = bom_data or {"assemblies": []}
        self.trigger_terms = tuple(trigger_terms)
        self.station_patterns = (
            list(station_patterns) if station_patterns is not None
            else list(_DEFAULT_STATION_PATTERNS)
        )
        self.axis_label_default = axis_label_default

        # Derive BOM prefixes when not supplied.
        if bom_pno_prefixes is None:
            derived: set[str] = set()
            for assy in self.bom_data.get("assemblies", []):
                pno = assy.get("part_no", "")
                if "-" in pno:
                    derived.add(pno.rsplit("-", 1)[0])
            self.bom_pno_prefixes = tuple(sorted(derived))
        else:
            self.bom_pno_prefixes = tuple(bom_pno_prefixes)

        # Per-instance compiled envelope regexes — NO module-level cache.
        self._box_re, self._cyl_re = _build_envelope_regexes(self.trigger_terms)

        # Per-instance counters (written during walk).
        self._axis_label_default_count = 0

        # Caches for public API.
        self._outputs: list[WalkerOutput] = []
        self._stats: WalkerStats | None = None

    def _extract_envelope_from_line(self, line: str) -> EnvelopeData | None:
        """Extract a box or cylinder envelope from one line.

        Applies axis-label canonicalization: box dims are rewritten to
        canonical (X, Y, Z) order using _AXIS_LABEL_BOX_MAP. An unknown
        axis label returns None (the caller surfaces it as UNMATCHED with
        reason='unrecognized_axis_label'). When no label is present, the
        walker's `axis_label_default` is applied and the default-counter
        increments.
        """
        m = self._box_re.search(line)
        if m:
            raw = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
            raw_label = m.group(4)
            effective_label = raw_label or self.axis_label_default
            dims = _canonicalize_box_axes(raw, effective_label)
            if dims is None:
                # Unknown label — caller will handle UNMATCHED.
                return None
            if raw_label is None:
                self._axis_label_default_count += 1
            return EnvelopeData(type="box", dims=dims, axis_label=raw_label)

        m = self._cyl_re.search(line)
        if m:
            return EnvelopeData(
                type="cylinder",
                dims=(("d", float(m.group(1))), ("z", float(m.group(2)))),
                axis_label=m.group(3),
            )
        return None
