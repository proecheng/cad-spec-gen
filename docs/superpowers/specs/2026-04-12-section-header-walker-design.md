# Section Header Walker + Envelope Extraction Foundation — Design Spec

**Date**: 2026-04-12
**Status**: Ready for implementation planning
**Parent context**: follow-up to Spec 1 Foundation (merged 2026-04-11). Addresses the envelope-extraction bug chain surfaced during the GISBOT end-to-end validation that Spec 1's partial regex fix could not fully resolve.
**Scope**: **foundation only** — close the data gap from design-doc prose to `§6.4 零件包络尺寸` in generated CAD_SPEC.md. Does NOT fix the visible "floating parts" problem in the GLB assembly; that remains a separate follow-up requiring vendor STEP routing and/or per-part envelope distribution.

---

## 1. Background

During Spec 1 end-to-end validation on the real GISBOT end-effector design document (`D:/Work/cad-tests/04-末端执行机构设计.md`), we discovered that `cad_spec_extractors.extract_part_envelopes()` returned **zero envelopes** even though the source document contains four explicit `模块包络尺寸` markers. Diagnosing the bug chain revealed three layers:

1. **Regex bug** (already fixed in Spec 1 commit `f55350e`): the P2 pattern `模块包络尺寸[：:]` did not handle markdown bold wrappers (`模块包络尺寸**：`). Also added `Φd×h` cylinder form. After the fix, the regex matches 4/4 envelope lines on the real doc.

2. **Assembly-matching bug** (this spec fixes): even after the regex matches the envelope markers, `_find_nearest_assembly()` returns `None` for all four because its two strategies — (a) regex scan for explicit `GIS-EE-NNN` part numbers in the 500-character context window, and (b) first-4-character substring match of BOM assembly names — both fail. The design doc uses Chinese section headings (`**工位1(0°)：耦合剂涂抹模块**`) that differ from the BOM-normalized names (`工位1涂抹模块`) generated later by `cad_spec_gen.py`. The 4-character prefix `"工位1涂"` is not a substring of `"工位1(0°)：耦合剂涂抹"`, so strategy (b) fails.

3. **Distribution gap** (out of scope, deferred): even with (1) and (2) fixed, the extracted envelopes are STATION-level (e.g., `GIS-EE-002: 60×40×290mm`), not per-part. The std parts inside that station (LEMO connectors, bearings, springs) still have no individual envelope data and fall back to minimum primitives (`Φ10×25mm`). This is what produces the visible "floating parts" symptom in the GLB. Fixing it requires either (a) rules to distribute station envelopes to sub-parts, or (b) vendor STEP routing (LEMO/Maxon), or (c) per-part prose extraction from the material column. All three are out of scope for this spec.

The goal of this spec is to close layer (2) with a proper **stateful section walker** that tracks the active section as it reads the document linearly and attributes each envelope to the correct BOM assembly via a **3-tier hybrid matching strategy**. This unblocks any future follow-up work that needs reliable `§6.4` data.

## 2. Goals

- **G1** — Produce a working `cad_spec_section_walker.py` module with a `SectionWalker` class that reads design-doc lines linearly, maintains a stack of active sections, and emits envelope attribution records.
- **G2** — Replace the existing P2 block in `cad_spec_extractors.extract_part_envelopes()` with an invocation of the walker. Preserve all other priority tiers unchanged: P1/P3/P4 stay in `cad_spec_extractors.py`; P5/P6/P7 stay in `cad_spec_gen.py` (lines 712, 759, 764).
- **G3** — Handle the 3 matching strategies (pattern, subsequence, Jaccard) with explicit tier tagging in the envelope `source` field so downstream code and tests can see which tier produced each envelope.
- **G4** — Pass the GISBOT end-effector design doc test: 4+ station envelopes attached to the correct `GIS-EE-00N` assemblies in the generated `§6.4` table.
- **G5** — Pass the lifting-platform design doc test: 2+ envelope attachments where the source doc has envelopes (sparser data — this test validates walker generality, not coverage).
- **G6** — All 10 synthetic fixture docs produce the expected walker output, including the `UNMATCHED` bucket for deliberately unmatchable cases.
- **G7** — Never raise exceptions from the walker; never crash `extract_part_envelopes`; never silently drop envelopes (all unmatched attempts are logged at WARNING *and* surfaced in the generated CAD_SPEC.md §6.4 section).
- **G8** — Preserve the actual effective priority order (verified against `cad_spec_extractors.py` + `cad_spec_gen.py` code): **P1 > P2 > P4 > P3 > P7 > P5/P6**. The walker produces P2 output; P2 is listed in `_PROTECTED_TIERS` in `cad_spec_gen.py:793` so the downstream P7 (parts_library probing) cannot overwrite it. The effective priority is a cross-module invariant enforced via explicit protection, NOT just write-ordering inside one function.
- **G9** — Preserve the existing `_find_nearest_assembly` explicit-part-number match as a **Tier 0 fallback** inside the walker. This avoids a regression where a walker import failure would remove the capability to match envelopes on docs that already contain explicit `GIS-EE-NNN` references in prose.
- **G10** — Surface match source, tier, confidence, and unmatched envelopes in the rendered §6.4 markdown so shop-floor users and QA inspectors can audit the data without reading Python logs.
- **G11** — Tag every envelope's semantic `granularity` (`station_constraint` | `part_envelope` | `component`) so downstream code cannot silently misuse a station-level constraint as a per-part sizing directive.

## 3. Non-Goals and Explicit Scoping

### 3.1 Out of scope

- Fixing the visible "floating parts" problem in the GLB assembly (see Background §1 layer 3).
- Updating `assembly_validator.py` F1/F3 thresholds to use envelope data (separate follow-up).
- Traditional Chinese character normalization (`殼體` ↔ `壳体`) — deferred to Spec 2 §17.
- GB/T material alias handling (`45#钢` ↔ `Q235`) — deferred to Spec 2 §17.
- Vendor STEP routing for LEMO/Maxon/ATI parts — deferred follow-up.
- Per-part envelope distribution from station envelopes — deferred follow-up.
- Fuzzy matching beyond character-subsequence and Jaccard (e.g., Levenshtein, embeddings) — deferred.
- Chain-syntax (`A → B → C`) extraction — already handled by `compute_serial_offsets` in P5, not touched.
- Compound envelope lines (e.g., `50×40×120mm box + Φ25×110mm cylinder`) — the walker extracts the FIRST shape from such lines and logs a WARNING that the second shape was discarded. Proper compound handling requires `list[EnvelopeData]` + a breakdown in §6.4 and is deferred.
- Revision diffing / override sidecar for shop-floor corrections — deferred follow-up.

### 3.2 Document format scoping (IMPORTANT)

This walker is scoped to Chinese engineering documents that use the GISBOT project's conventions:

- **Envelope trigger term**: `模块包络尺寸`. This is a GISBOT-project compound term, NOT a standard GB/T terminology. GB/T 4458 uses `外形尺寸` and `总体尺寸`; other projects may use `外包络尺寸`, `轮廓尺寸`, `整体尺寸`. The walker exposes a module-level constant `ENVELOPE_TRIGGER_TERMS = ("模块包络尺寸",)` that can be extended per-project. **Default matches only GISBOT's term**; adding others is a one-line change documented as a configuration point.
- **Section numbering patterns**: `工位N`, `第N级`, `模块N`, `第N部分`. These reflect GISBOT's rotary-station / level / module conventions. Projects in other engineering domains (fixture tooling, hydraulic systems, electrical enclosures) may use `夹具位N`, `I级`, `甲`, etc. Tier 1 Pattern Extraction will return `None` for these, correctly falling through to Tier 2/3. The walker does NOT claim cross-domain generality for Tier 1.
- **Dimension axis labels**: the walker preserves the parenthetical label after a dimension (e.g., `60×40×290mm (宽×深×高)`) in `EnvelopeData.axis_label`. When the label is present, downstream code can use it to map dimensions to coordinate axes; when absent, the walker DEFAULTS to `宽×深×高` ordering and emits a WARNING asking the designer to add the label.

If this walker is ever used on a non-GISBOT document corpus, the expected outcomes are (a) correct Tier 2/3 matching if section headers carry enough Chinese characters, (b) UNMATCHED envelopes for unfamiliar conventions, and (c) zero false-positive confident matches. The spec's test coverage validates (c) via the no-BOM-match fixture (`05_no_bom_match.md`) and the ambiguous-tokens fixture (`06_ambiguous_tokens.md`).

## 4. Architecture

A new module `cad_spec_section_walker.py` sits at the repo root alongside `cad_spec_extractors.py` and `cad_spec_reviewer.py`. It exports a `SectionWalker` class and the supporting dataclasses.

```
┌──────────────────────────────────────────────────────────────────────┐
│  cad_spec_extractors.extract_part_envelopes(lines, bom_data, ...)    │
│                                                                      │
│    ├── P3: BOM 材质列 (unchanged)                                   │
│    ├── P4: 视觉标识表 size 列 (unchanged)                           │
│    │                                                                 │
│    ├── P2: SectionWalker (NEW — replaces old regex block)           │
│    │    │                                                           │
│    │    ├── _parse_section_header(line) → (level, text) | None     │
│    │    ├── _extract_envelope_from_line(line) → EnvelopeData | None │
│    │    ├── _match_section_to_assembly(header, bom):                │
│    │    │    ├── Tier 0: _find_nearest_assembly() [regression guard]│
│    │    │    ├── Tier 1: _match_by_pattern() [w/ ambiguity abstain] │
│    │    │    ├── Tier 2: _match_by_chinese_subsequence() [w/ ties]  │
│    │    │    └── Tier 3: _match_by_jaccard() [w/ tie abstain]       │
│    │    └── extract_envelopes() → list[WalkerOutput]                │
│    │                                                                 │
│    └── P1: 零件级参数表 (unchanged — runs AFTER P2, overwrites)    │
└──────────────────────────────────────────────────────────────────────┘
       │
       ▼ returns result dict
┌──────────────────────────────────────────────────────────────────────┐
│  cad_spec_gen.py — continues processing the returned envelope dict  │
│                                                                      │
│    ├── P5: 全局参数回填 (line 712 — chain_span)                     │
│    ├── P6: _guess_geometry 回填 (line 759)                          │
│    └── P7: parts_library probing (line 764)                         │
│          ├── _OVERRIDABLE_TIERS = ("P5:", "P6:")                    │
│          └── _PROTECTED_TIERS = ("P1:", "P2:", "P3:", "P4:")        │
│                                                                      │
│    └── §6.4 rendering (line 308-321 + new 6.4.1 section) ──────────►│
│         Includes source / tier / confidence / granularity columns  │
│         and renders walker.unmatched as a §6.4.1 "review required" │
│         subsection.                                                 │
└──────────────────────────────────────────────────────────────────────┘
```

**Effective cross-module priority**: **P1 > P2 > P4 > P3 > P7 > P5/P6**. Within `extract_part_envelopes`, P1 runs last and overwrites P2. After return, P7 can only override entries sourced from P5/P6 (explicit allowlist), NOT P1/P2/P3/P4 (explicit protection).

**Why a new module instead of adding to `cad_spec_extractors.py`**: testability and reusability. The walker is complex enough (~300 LOC) to deserve its own test file. The class-based design also makes it reusable by Spec 2 §17's Chinese keyword expansion work later — §17's planned extension pattern is constructor-time BOM normalization (pass a pre-normalized BOM dict), NOT subclassing. This is called out explicitly so §17 doesn't accidentally pick a fragile extension mechanism.

**Module-level contract**:
- `SectionWalker.__init__(lines: list[str], bom_data: dict)` — construct with the design doc lines and the parsed BOM
- `SectionWalker.extract_envelopes() → list[WalkerOutput]` — return all matched and unmatched envelopes
- `SectionWalker.unmatched: list[WalkerOutput]` — property exposing only the UNMATCHED entries (for tests and future `cad-lib report` integration)
- Never raises. Internal exceptions are caught and logged at DEBUG.

## 5. Section Header Recognition

The walker recognizes two types of section headers:

| # | Pattern | Regex | Example |
|---|---------|-------|---------|
| 1 | Markdown hash headers | `^(#{1,6})\s+(.+)$` | `### 4.1.2 各工位机械结构` |
| 2 | Standalone bold on own line | `^\*\*([^*]+)\*\*\s*$` | `**工位1(0°)：耦合剂涂抹模块**` |

**Explicitly NOT a section header**: bullet-list bold items like `- **模块包络尺寸**：60×40×290mm` or `- **FFC规格**：20芯`. Validated against the real end-effector document:
- 51 lines match the bullet-bold-with-colon pattern (all property labels or envelope markers, NONE are section boundaries)
- 4 lines match standalone-bold-on-own-line (exactly the 4 station headers: `工位1`, `工位2`, `工位3`, `工位4`)

Treating bullet-bolds as section headers would cause the walker to reset its state on every property label line, including the envelope marker itself. **This is why the pattern is deliberately excluded.**

**Stack-based state model**: the walker maintains a stack of active section frames. Each frame has a level (1-6 for markdown, or 100 for bold-as-heading). When a new header at level N is pushed, all frames with level ≥ N are popped first. Bold-as-heading (level 100) is always deeper than any markdown header, so bold headers live inside markdown sections and are popped when the markdown section changes.

```python
@dataclass(frozen=True)
class SectionFrame:
    level: int                  # 1-6 for markdown, 100 for bold-as-heading
    header_text: str            # normalized header content (bold markers stripped)
    match: MatchResult | None   # BOM assembly match, if any


@dataclass(frozen=True)
class MatchResult:
    pno: str                    # BOM part_no
    tier: int                   # 0, 1, 2, or 3 (0 = _find_nearest_assembly fallback)
    confidence: float           # 0.0-1.0


@dataclass(frozen=True)
class EnvelopeData:
    """Immutable envelope data. Hashable so it can live in sets and dict keys.

    dims is a tuple of (name, value) pairs, not a dict, because dict is not
    hashable and would break frozen=True's hashability contract.
    """
    type: str                         # "box" or "cylinder"
    dims: tuple[tuple[str, float], ...]  # (("w", 60.0), ("d", 40.0), ("h", 290.0))
                                         # for cylinder: (("d", 45.0), ("h", 120.0))
    axis_label: str | None = None     # parenthetical label if present, e.g. "宽×深×高"

    def dims_dict(self) -> dict:
        """Convert tuple back to dict for convenient access."""
        return dict(self.dims)


@dataclass(frozen=True)
class WalkerOutput:
    matched_pno: str | None     # BOM part_no, or None if UNMATCHED
    envelope_type: str          # "box" or "cylinder"
    dims: tuple[tuple[str, float], ...]  # immutable dims, same shape as EnvelopeData.dims
    tier: int | None            # 0/1/2/3 if matched, None if UNMATCHED
    confidence: float           # 0.0 if UNMATCHED, else MatchResult.confidence
    header_text: str            # innermost section header text, or "" if none
    line_number: int            # 0-indexed line number of the envelope marker
    granularity: str            # "station_constraint" (walker default for Tier 0/1/2/3)
                                # or "part_envelope" (reserved for future per-part prose
                                # extraction — not produced by this spec)
    axis_label: str | None = None
    source_line: str = ""       # raw unmodified source line for traceability

    def dims_dict(self) -> dict:
        return dict(self.dims)
```

**Why `tuple[tuple[str, float], ...]` instead of `dict`**: `frozen=True` on a dataclass prevents attribute reassignment but does NOT freeze a mutable `dict` field — the class becomes non-hashable, which silently breaks any test or future code that uses sets or dict keys. The tuple representation preserves immutability and hashability at a small ergonomic cost (recovered via the `dims_dict()` helper).

**`granularity` field** — every envelope the walker produces is tagged `"station_constraint"` because the walker only extracts station-level `模块包络尺寸` prose markers, which semantically mean "this module must fit within this bounding box" — NOT "any individual part inside is this size". Downstream code must respect this semantic: `gen_assembly.py` can use it as a container height for stacking; `gen_std_parts.py` MUST NOT use it to size individual purchased parts. A future spec that adds per-part extraction will produce `"part_envelope"` records; those can be used directly for sizing. See §15 for the downstream-consumer follow-up that needs to honor this distinction.

**`axis_label` field** — preserves the parenthetical dimension-order label (e.g., `"宽×深×高"`, `"长×宽×高"`, `"W×D×H"`) so downstream code can map dims to coordinate axes correctly. When absent, the walker defaults to `宽×深×高` ordering for box envelopes and emits a WARNING — but the WARNING is emitted at WALK time, logged, and counted in `walker.axis_label_warnings` for test assertions.

**Envelope attribution rule**: when an envelope marker is found, attribute it to the **innermost frame that has a non-None `match`** by walking up the stack. If no frame has a match, produce an `UNMATCHED` entry with the raw current-frame header text and log a WARNING. This ensures sections that didn't match a BOM assembly (e.g., "4.1.2 各工位机械结构" — a meta-header that doesn't correspond to a single assembly) don't swallow envelopes; they get pushed down to their child sections.

## 6. Matching Strategies (4 tiers — Tier 0 added for regression protection)

**Tier 0** is a regression-protection fallback inherited from the old code path. The existing `_find_nearest_assembly()` function (in `cad_spec_extractors.py`) already handles the case where a design doc has explicit `GIS-EE-NNN` part numbers in the 500-character context window before an envelope marker. That case DOES work today for some designs. If we removed this path and only shipped the section walker's 3 tiers, any design doc that used explicit part_no references (rather than section headers) would REGRESS to zero envelopes. Tier 0 preserves this existing capability by running first, using the legacy context-window scan.

- **Tier 0**: existing `_find_nearest_assembly(context, bom_data)` — explicit part_no regex scan in the 500-char context window. Confidence = 1.0 when it fires. This is the regression-protection safety net.
- **Tier 1**: pattern extraction (`工位N`, `第N级`, `模块N`, `第N部分`) with ambiguity detection.
- **Tier 2**: Chinese-character subsequence match with tie-detection (multiple BOM candidates → abstain).
- **Tier 3**: mixed CJK bigram + ASCII word Jaccard similarity with the existing tie-abstention logic.

Matching is done against a **normalized** form of the section header. Pre-normalization is applied once per header before tier invocation:

```python
def _normalize_header(text: str) -> str:
    """Strip markdown artifacts and collapse whitespace. Returns the
    semantic content of the header, preserving original characters for
    tier 2/3 matching which operates on character content."""
    text = re.sub(r"\*\*", "", text)                # strip markdown bold
    text = re.sub(r"^#{1,6}\s*", "", text)          # strip markdown header hashes
    text = re.sub(r"\s+", " ", text).strip()        # collapse whitespace
    return text
```

The walker tries tiers in order, accepting the first successful match. Each tier returns `(pno, confidence) | None`.

### 6.1 Tier 1 — Pattern extraction (highest priority)

Looks for structured numbering patterns commonly used in Chinese engineering docs. If a pattern matches the header, extract the index N and look up the Nth BOM assembly of that category.

```python
_STATION_PATTERNS = [
    (r"工位\s*(\d+)", "工位"),
    (r"第\s*(\d+)\s*级", "级"),
    (r"模块\s*(\d+)", "模块"),
    (r"第\s*(\d+)\s*部分", "部分"),
]

def _match_by_pattern(header: str, bom_data: dict) -> MatchResult | None:
    for regex, category in _STATION_PATTERNS:
        m = re.search(regex, header)
        if not m:
            continue
        idx = int(m.group(1))
        # Find all BOM assemblies whose names contain a numbered category
        # marker matching our extracted idx.
        idx_re = re.compile(fr"{category}\s*(\d+)")
        matching = []
        for a in bom_data.get("assemblies", []):
            m2 = idx_re.search(a.get("name", ""))
            if m2 and int(m2.group(1)) == idx:
                matching.append(a)
        if len(matching) == 0:
            # Pattern fired but BOM has no assembly with this category/idx;
            # fall through to the next pattern and ultimately to Tier 2.
            continue
        if len(matching) >= 2:
            # AMBIGUITY — multiple BOM assemblies with the same 工位N number.
            # Abstain rather than pick one and fake certainty. The walker
            # will try Tier 2 next.
            continue
        return MatchResult(pno=matching[0]["part_no"], tier=1, confidence=1.0)
    return None
```

**Confidence = 1.0** when a unique match is found. **Ambiguity handling**: if the BOM has two or more assemblies with the same category/number (e.g., both `工位1涂抹模块` and `工位1驱动模块`), Tier 1 abstains rather than silently picking the first. This prevents the "Tier 1 false positives at confidence 1.0" failure mode the mechanical reviewer flagged.

**Handles the end-effector case**: header `"工位1(0°)：耦合剂涂抹模块"` → pattern `工位(\d+)` extracts `1` → BOM assembly `工位1涂抹模块` (part_no `GIS-EE-002`) → returned.

### 6.2 Tier 2 — Chinese-character subsequence match

When pattern extraction fails (header has no structured numbering), try matching by characters. Strip all non-Chinese characters from both the header and each BOM assembly name, then check if the BOM's characters appear as a **subsequence** in the header's characters.

```python
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]+")

def _chinese_only(text: str) -> str:
    return "".join(_CHINESE_RE.findall(text))

def _is_subsequence(needle: str, haystack: str) -> bool:
    """Check if all characters of needle appear in haystack in order."""
    it = iter(haystack)
    return all(ch in it for ch in needle)

def _match_by_chinese_subsequence(header: str, bom_data: dict) -> MatchResult | None:
    header_cn = _chinese_only(header)
    if not header_cn:
        return None  # header has no Chinese content; Tier 3 may still find something
    matches = []
    for a in bom_data.get("assemblies", []):
        bom_cn = _chinese_only(a.get("name", ""))
        if not bom_cn:
            continue
        if _is_subsequence(bom_cn, header_cn):
            # Density score: how much of the haystack is actually "used"
            # by the subsequence. A 2-char BOM name inside a 20-char header
            # has lower density than a 5-char BOM name inside a 10-char header.
            density = len(bom_cn) / len(header_cn)
            matches.append((a["part_no"], density, len(bom_cn)))

    if not matches:
        return None
    if len(matches) == 1:
        return MatchResult(pno=matches[0][0], tier=2, confidence=0.85)

    # Multiple subsequence matches — rank by density (longer BOM names
    # relative to header length are better) and check for ties.
    matches.sort(key=lambda m: (-m[1], -m[2]))
    top = matches[0]
    runner_up = matches[1]
    # If two matches have near-identical density, abstain to avoid
    # false positives (Mechanical reviewer concern: shared-infrastructure
    # subsections might subsequence-match multiple BOM assemblies).
    if abs(top[1] - runner_up[1]) < 0.1:
        return None  # ambiguous — fall through to Tier 3
    return MatchResult(pno=top[0], tier=2, confidence=0.85)
```

**Confidence = 0.85** — high but not perfect, because subsequence matching can have false positives if BOM names are very short.

**Tie detection**: if two or more BOM assemblies match with near-identical density (within 0.1), Tier 2 abstains and falls through to Tier 3 — or ultimately to UNMATCHED. This addresses the mechanical reviewer's concern that a meta-section like `4.1 工位通用规范` could subsequence-match multiple stations and produce false attributions.

**Handles the example**: header `"工位1(0°)：耦合剂涂抹模块"` → Chinese-only = `"工位耦合剂涂抹模块"` (9 chars). BOM `"工位1涂抹模块"` → Chinese-only = `"工位涂抹模块"` (6 chars). Subsequence check: 工→工 ✓ 位→位 ✓ 涂→涂 ✓ (skip 耦合剂) 抹→抹 ✓ 模→模 ✓ 块→块 ✓ **YES**. Density = 6/9 = 0.67. If no other BOM assembly has a competing density, Tier 2 returns `GIS-EE-002`.

### 6.3 Tier 3 — Mixed-token Jaccard similarity

Last-resort fallback for headers that have no Chinese content (e.g., English section titles) OR where Tier 2's subsequence check is too strict (e.g., out-of-order terms).

Tokenization handles both Chinese bigrams and ASCII words:

```python
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_RUN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")

def _tokenize(text: str) -> set[str]:
    """Produce a set of tokens mixing CJK bigrams and ASCII words."""
    tokens = set()
    # CJK bigrams
    for run in _CJK_RUN_RE.findall(text):
        for i in range(len(run) - 1):
            tokens.add(run[i:i+2])
    # ASCII words, lowercased
    for word in _ASCII_RUN_RE.findall(text):
        if len(word) >= 2:
            tokens.add(word.lower())
    return tokens


def _match_by_jaccard(header: str, bom_data: dict,
                     threshold: float = 0.5) -> MatchResult | None:
    header_tokens = _tokenize(header)
    if not header_tokens:
        return None
    # Collect ALL scores ≥ threshold, then rank — this fixes the
    # "second_best_score not updated on non-best iterations" bug where
    # a later candidate with a close-but-not-best score was ignored in
    # the gap check.
    scored = []
    for a in bom_data.get("assemblies", []):
        bom_tokens = _tokenize(a.get("name", ""))
        if not bom_tokens:
            continue
        intersection = len(header_tokens & bom_tokens)
        union = len(header_tokens | bom_tokens)
        score = intersection / union if union > 0 else 0.0
        if score >= threshold:
            scored.append((a["part_no"], score))

    if not scored:
        return None
    scored.sort(key=lambda x: -x[1])
    best_pno, best_score = scored[0]
    if len(scored) >= 2:
        _, second_score = scored[1]
        # Exact tie → abstain
        if second_score == best_score:
            return None
        # Near-tie (within 0.1) → abstain to avoid false positives
        if (best_score - second_score) < 0.1:
            return None
    return MatchResult(pno=best_pno, tier=3, confidence=best_score)
```

**Bug fix note**: the previous draft of this code had a latent bug where `second_best_score` was only updated inside the `if best is None or score > best[1]` branch, meaning a later candidate with a close-but-not-best score never contributed to the tie-detection. The fixed version collects all above-threshold scores first, then sorts and checks the top two, which handles the case correctly regardless of iteration order over the BOM.

**Threshold = 0.5** — conservative. Higher produces fewer false positives but misses more real matches.

**Tie handling**: if two BOM assemblies have identical top scores, or scores within 0.1 of each other, the walker abstains (returns `None`) rather than guessing. This matters because the UNMATCHED logging gives users a clear signal to fix their section headers.

## 7. Envelope Marker Recognition

Identical to the current regex set from Spec 1's partial fix (commit `f55350e`), except extracted into a helper function for testability:

```python
# Envelope trigger terms — configurable for projects beyond GISBOT.
# Default matches ONLY '模块包络尺寸'; other projects can extend.
ENVELOPE_TRIGGER_TERMS = ("模块包络尺寸",)

def _build_envelope_regex(pattern_body: str) -> re.Pattern:
    """Build a regex for envelope detection, allowing configurable trigger terms.

    Handles BOTH bold-before-colon (`模块包络尺寸**：`) AND bold-around-value
    (`模块包络尺寸：**60×40×290mm**`) patterns. Also allows an optional
    parenthetical label after the dimensions for axis order preservation.
    """
    trigger = "|".join(re.escape(t) for t in ENVELOPE_TRIGGER_TERMS)
    return re.compile(
        fr"(?:{trigger})(?:\*\*)?[：:]\s*"   # label + optional bold close + colon
        fr"(?:\*\*)?\s*"                      # optional bold OPEN around value
        fr"{pattern_body}"
        fr"\s*(?:\*\*)?"                      # optional bold CLOSE around value
        fr"(?:\s*[(（]([^)）]+)[)）])?"       # optional parenthetical axis label
    )

_ENVELOPE_BOX_RE = _build_envelope_regex(
    r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
    r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
    r"(\d+(?:\.\d+)?)\s*mm"
)

_ENVELOPE_CYLINDER_RE = _build_envelope_regex(
    r"[ΦφØ∅](\d+(?:\.\d+)?)\s*[×xX]\s*"
    r"(\d+(?:\.\d+)?)\s*mm"
)

def _extract_envelope_from_line(line: str) -> EnvelopeData | None:
    m = _ENVELOPE_BOX_RE.search(line)
    if m:
        axis_label = m.group(4) if len(m.groups()) >= 4 else None
        return EnvelopeData(
            type="box",
            dims=(("w", float(m.group(1))),
                  ("d", float(m.group(2))),
                  ("h", float(m.group(3)))),
            axis_label=axis_label,
        )
    m = _ENVELOPE_CYLINDER_RE.search(line)
    if m:
        axis_label = m.group(3) if len(m.groups()) >= 3 else None
        return EnvelopeData(
            type="cylinder",
            dims=(("d", float(m.group(1))), ("h", float(m.group(2)))),
            axis_label=axis_label,
        )
    return None
```

**Regex changes from Spec 1's partial fix**:
1. `ENVELOPE_TRIGGER_TERMS` is now a module-level constant, making the `模块包络尺寸` hardcode configurable. Projects using `外形尺寸`, `总体尺寸`, or `外包络尺寸` can extend the tuple.
2. Handles **bold around the value** too: `模块包络尺寸：**60×40×290mm**` was not matched by the Spec 1 regex, which only handled bold-before-colon. Real Markdown commonly bolds the value.
3. Captures the optional parenthetical axis label (e.g., `(宽×深×高)`) for preservation in `EnvelopeData.axis_label`.

**Compound envelope limitation**: a line like `模块包络尺寸：50×40×120mm + Φ25×110mm溶剂储罐` will match the box form FIRST and return a single `EnvelopeData`. The cylinder portion is discarded and the walker emits a WARNING `"compound envelope truncated at line N: keeping first shape only"`. Proper compound handling requires changing `EnvelopeData` to support multi-shape records and is deferred (see §3.1). This is a known limitation for the GISBOT station 3 envelope.

## 8. Integration with `extract_part_envelopes`

The existing P2 block (lines 1155-1193 in `cad_spec_extractors.py`) is **replaced** by a walker invocation. All other priority tiers are untouched.

```python
# In extract_part_envelopes() — replacing the existing P2 block

# --- P2: Section walker (NEW) ---
# ImportError is caught SEPARATELY at ERROR level because a missing walker
# module indicates a deployment/packaging bug (Spec 1 Phase 5 missed
# something) rather than a runtime problem. Silent WARNING would hide
# this class of failure. Runtime exceptions from the walker itself are
# still caught at WARNING via the outer except block.
import logging
_log = logging.getLogger("cad_spec_extractors")

try:
    from cad_spec_section_walker import SectionWalker
except ImportError as exc:
    _log.error(
        "cad_spec_section_walker module not found — P2 envelope extraction "
        "DISABLED. This is a packaging bug; check hatch_build.py:_PIPELINE_TOOLS. "
        "Error: %s", exc
    )
    SectionWalker = None

if SectionWalker is not None:
    try:
        walker = SectionWalker(lines, bom_data)
        outputs = walker.extract_envelopes()
        for entry in outputs:
            if entry.matched_pno is None:
                # UNMATCHED — walker already logged it and recorded it in
                # walker.unmatched. Skipped here but will be rendered in §6.4
                # as a "review required" note by the CAD_SPEC.md generator.
                continue
            pno = entry.matched_pno
            # Only set if no higher-priority tier (P3 or P4, which ran before
            # us) has already written an envelope. P1 runs AFTER this block
            # and can still overwrite P2 results.
            if pno not in result:
                result[pno] = {
                    "type": entry.envelope_type,
                    "source": f"P2:section_walker:tier{entry.tier}",
                    "granularity": entry.granularity,
                    "axis_label": entry.axis_label,
                    "confidence": entry.confidence,
                    "source_line": entry.source_line,
                    **dict(entry.dims),
                }
        # Expose unmatched envelopes for §6.4 rendering and cad-lib report
        result.setdefault("_meta", {})["walker_unmatched"] = [
            {
                "header": o.header_text,
                "type": o.envelope_type,
                "dims": dict(o.dims),
                "line_number": o.line_number,
                "source_line": o.source_line,
            }
            for o in outputs if o.matched_pno is None
        ]
    except Exception as exc:
        _log.warning(
            "Section walker runtime failure, skipping P2 envelope "
            "extraction for this document: %s", exc
        )
```

**Execution order** (verified against `cad_spec_extractors.py` + `cad_spec_gen.py` actual code):
1. In `cad_spec_extractors.extract_part_envelopes()`: P3 → P4 → **P2 (walker)** → P1, later writes overwriting. Later-executed tiers win on conflict. After this function returns, the in-function effective priority is **P1 > P2 > P4 > P3** (P1 wrote last, P3 wrote first).
2. In `cad_spec_gen.py` (called after `extract_part_envelopes` returns): P5 backfill (line 712) → P6 backfill (line 759) → P7 parts_library probing (line 764).
3. P7 respects `_PROTECTED_TIERS = ("P1:", "P2:", "P3:", "P4:")` (line 793) and only overrides entries with `_OVERRIDABLE_TIERS = ("P5:", "P6:")` sources. P1/P2/P3/P4 entries are sacrosanct against P7.

**Resulting cross-module effective priority**: **P1 > P2 > P4 > P3 > P7 > P5/P6**. The walker produces P2 output which is protected from P7 override by the explicit allowlist in `cad_spec_gen.py`, and is overridable only by P1 (which runs last in the same function) for parts that appear in a structured parameter table.

**Defensive depth**: two-layer exception handling. ImportError is caught separately at ERROR level (packaging bug); any other exception from the walker is caught at WARNING (runtime issue). Both paths preserve the remaining P1/P3/P4/P5/P6/P7 pipeline execution.

### 8.1 §6.4 rendering changes

The existing `§6.4 零件包络尺寸` table in generated CAD_SPEC.md (produced by `cad_spec_gen.py:308-321`) currently shows columns `料号 | 名称 | 尺寸 | 来源`. This spec adds visible audit columns:

```markdown
### 6.4 零件包络尺寸

> NOTE: This table lists **station-level (assembly-level) envelopes** extracted
> from design-doc prose. Individual component envelopes for sub-parts (purchased
> connectors, bearings, motors) are pending vendor STEP data and are NOT listed
> here. See §16 items 1-2 for the planned follow-up work (downstream
> parent-assembly lookup + vendor STEP routing).

| 料号 | 名称 | 尺寸 | 轴向标签 | 来源 | 置信度 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| GIS-EE-001 | 法兰总成 | 90×90×25mm | — | P1:param_table | 1.00 | — |
| GIS-EE-002 | 工位1涂抹模块 | 60×40×290mm | 宽×深×高 | P2:walker:tier1 | 1.00 | station_constraint |
| GIS-EE-003 | 工位2 AE检测模块 | Φ45×120mm | — | P2:walker:tier1 | 1.00 | station_constraint |
| GIS-EE-005 | 工位4 UHF模块 | Φ50×85mm | — | P2:walker:tier3 | **0.62 — VERIFY** | station_constraint, low confidence |

#### 6.4.1 未匹配的包络 (Unmatched envelopes — manual review required)

The walker found the following envelopes in the source document but could not
match them to any BOM assembly:

| 行号 | 原始文字 | 建议 |
| --- | --- | --- |
| 183 | `- **模块包络尺寸**：Φ30×45mm` | 无匹配 BOM assembly. 可能原因: 章节标题与 BOM 名称差异大, 或属于未声明的子模块 |
```

**Rendering rules** in `cad_spec_gen.py`:
1. Every row shows `来源` column with the full tier string (`P2:walker:tier1`, etc.) so the data lineage is traceable.
2. `置信度` column shows `confidence` as a two-decimal float. If confidence < 0.75, render with **`VERIFY`** suffix in bold to draw QA attention.
3. `备注` column shows `granularity` (`station_constraint` for all walker output in this spec) and any known limitations (e.g., `compound truncated`).
4. If `_meta["walker_unmatched"]` is non-empty, emit a subsection `6.4.1 未匹配的包络` listing line number, original text, and a suggestion. This makes the quality gap visible on the shop floor.
5. If the walker produced ZERO matched envelopes on a document that has envelope marker lines, emit a PROMINENT warning at the top of §6.4 suggesting traditional-character encoding mismatch or missing section headers.

These rendering rules are NEW — they require a small addition to `cad_spec_gen.py:308-321`. The addition is part of this spec's implementation scope.

## 9. Error Handling and Logging

| Failure mode | Behavior | Log level |
|--------------|----------|-----------|
| BOM is None (bom_data parameter not provided) | Walker returns empty list immediately without processing | DEBUG |
| BOM empty (has no assemblies) | Walker still walks the document and emits envelopes, but ALL are UNMATCHED because there's nothing to match against | WARNING (once per call) |
| Section header matches no BOM assembly | Push frame with `match=None`; envelope attributes to closest ancestor with a match, or UNMATCHED if none | DEBUG |
| Envelope line found but has no parent section frame (e.g., appears before any header) | Emit UNMATCHED entry with `header_text=""` | WARNING |
| Regex matches envelope marker but dimension parsing fails | Log diagnostic, skip the line | INFO |
| Exception anywhere inside the walker | Caught at `extract_envelopes()` top level, return what's been collected so far | DEBUG |
| Exception propagates from walker to `extract_part_envelopes` | Caught at integration point, log and skip P2 entirely | WARNING |

**UNMATCHED logging format**: `WARNING: section walker: envelope 60×40×290mm in section '工位1(0°)：耦合剂涂抹模块' — no BOM assembly matched (tiers 1/2/3 all failed)`. This gives the user actionable information about what went wrong.

**No stack trace spam**: the walker uses structured logging (module-name logger) so users can suppress it with `logging.getLogger("cad_spec_section_walker").setLevel(logging.ERROR)` if they're running in a noisy pipeline.

## 10. File Layout

### 10.1 Skill-Level Files (AUTHORIZED TO MODIFY)

| File | Action | Purpose |
|------|--------|---------|
| `cad_spec_section_walker.py` | **Create** (repo root) | New module with `SectionWalker` class + matching strategies + dataclasses |
| `cad_spec_extractors.py` | Modify (replace P2 block ~15 lines) | Wire the walker into `extract_part_envelopes` |
| `hatch_build.py` | Modify (add 1 entry to `_PIPELINE_TOOLS`) | Ship `cad_spec_section_walker.py` in the wheel |

### 10.2 Tests and Fixtures

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_section_walker_unit.py` | Create | Layer 1: unit tests for state machine, matching strategies, normalization |
| `tests/test_section_walker_fixtures.py` | Create | Layer 2: 10 synthetic fixture docs with known expected output |
| `tests/test_section_walker_real_docs.py` | Create | Layer 3: real-data integration tests on the 2 design docs |
| `tests/fixtures/section_walker/01_clean_station.md` | Create | Standard `**工位N(angle°)：name**` format (end-effector style) |
| `tests/fixtures/section_walker/02_no_parenthetical.md` | Create | `**工位N：name**` without `(angle°)` |
| `tests/fixtures/section_walker/03_markdown_hashes.md` | Create | `### 工位N name` style |
| `tests/fixtures/section_walker/04_nested_subsections.md` | Create | Envelope inside a subsection (walker should walk up) |
| `tests/fixtures/section_walker/05_no_bom_match.md` | Create | Section header no BOM assembly matches (→ UNMATCHED) |
| `tests/fixtures/section_walker/06_ambiguous_tokens.md` | Create | Two BOM assemblies score identically (→ abstain → UNMATCHED) |
| `tests/fixtures/section_walker/07_multiple_envelopes_one_section.md` | Create | Section has 2 envelopes (both attributed) |
| `tests/fixtures/section_walker/08_envelope_before_any_section.md` | Create | Envelope appears before first header (→ UNMATCHED) |
| `tests/fixtures/section_walker/09_cylinder_form.md` | Create | `Φd×h` envelope form |
| `tests/fixtures/section_walker/10_english_header.md` | Create | `## Station 1: Applicator` — tier 3 Jaccard |
| `tests/fixtures/real_doc_boms/end_effector.yaml` | Create (generated) | Pre-computed BOM from `04-末端执行机构设计.md` |
| `tests/fixtures/real_doc_boms/lifting_platform.yaml` | Create (generated) | Pre-computed BOM from `19-液压钳升降平台设计.md` |
| `tests/fixtures/real_doc_boms/_regenerate.py` | Create | Utility script to regenerate the two BOM YAML files |

### 10.3 Files That Auto-Regenerate (DO NOT Hand-Edit)

- `src/cad_spec_gen/data/python_tools/cad_spec_section_walker.py` — build-generated mirror via `hatch_build.py:PYTHON_TOOLS` after the module is added to the list
- `src/cad_spec_gen/data/python_tools/cad_spec_extractors.py` — build-generated mirror (already existed)

### 10.4 Files NEVER Touched (INTERMEDIATE PRODUCTS)

- `cad/<subsystem>/*` — never modified by this spec's implementation
- Generated `CAD_SPEC.md` files — only regenerated via `cad_pipeline.py spec` runs, which exercise the new walker naturally

## 11. Testing Strategy

### 11.1 Layer 1 — Unit tests (`@pytest.mark.fast`)

Target: `tests/test_section_walker_unit.py`

- `_normalize_header` correctly strips markdown bold, header hashes, and whitespace for all combinations
- `_parse_section_header` returns `(level, text)` for markdown headers (levels 1-6), `(100, text)` for standalone bold, and `None` for bullet-bolds or regular lines
- `_extract_envelope_from_line` extracts box and cylinder forms with and without markdown bold
- `_match_by_pattern` correctly maps `工位1`, `工位2`, ..., `第1级`, `模块3` to Nth BOM assembly
- `_match_by_chinese_subsequence` correctly matches `"工位1涂抹模块"` as a subsequence of `"工位耦合剂涂抹模块"` after Chinese-only filtering
- `_match_by_jaccard` picks the correct candidate above threshold, abstains on ties, abstains when top score is within 0.1 of second-best
- `_tokenize` produces correct bigrams for CJK and words for ASCII
- Section stack correctly pushes, pops on re-entering shallower section, handles level-100 bold frames inside markdown sections
- Envelope attribution walks up the stack to find the innermost matched frame
- Envelope with no matched parent becomes UNMATCHED with proper header text

### 11.2 Layer 2 — Synthetic fixtures (`@pytest.mark.fast`)

Target: `tests/test_section_walker_fixtures.py`

Each fixture under `tests/fixtures/section_walker/` is paired with an expected-output JSON embedded in the test file. Running the walker against the fixture must produce the expected sequence of matched + unmatched envelopes with the correct tier tags.

Fixture coverage (10 files — see §10.2):

| # | File | What it tests | Expected |
|---|------|---------------|----------|
| 01 | `clean_station.md` | End-effector style `**工位N(angle°)：name**` | 4 matched via Tier 1 |
| 02 | `no_parenthetical.md` | `**工位N：name**` without angle | 4 matched via Tier 1 |
| 03 | `markdown_hashes.md` | `### 工位N name` markdown header | 4 matched via Tier 1 |
| 04 | `nested_subsections.md` | Envelope inside a subsection that has no BOM match | Matched via stack walk-up |
| 05 | `no_bom_match.md` | Section header no BOM assembly matches | UNMATCHED |
| 06 | `ambiguous_tokens.md` | Two BOM assemblies with identical Jaccard scores | UNMATCHED (tier 3 abstain) |
| 07 | `multiple_envelopes_one_section.md` | Section has 2 envelopes | Both attributed to same assembly |
| 08 | `envelope_before_any_section.md` | Envelope before any header | UNMATCHED |
| 09 | `cylinder_form.md` | `Φd×h` envelope form | Cylinder type envelope |
| 10 | `english_header.md` | `## Station 1: Applicator` | Tier 3 Jaccard match |

### 11.3 Layer 3 — Real design doc tests (`@pytest.mark.integration`)

Target: `tests/test_section_walker_real_docs.py`

Uses **pre-computed BOM YAML files** at `tests/fixtures/real_doc_boms/*.yaml` to avoid the chicken-and-egg of needing `extract_bom` to work during test collection. The YAML files are generated once by running `tests/fixtures/real_doc_boms/_regenerate.py` (a one-line helper that calls `extract_bom()` on each source doc and dumps the result).

| Test | Input | Expectation |
|------|-------|-------------|
| `test_end_effector_docs` | `04-末端执行机构设计.md` + end_effector BOM | ≥4 envelopes matched, all to `GIS-EE-00N` station assemblies, zero UNMATCHED in the station envelope set |
| `test_lifting_platform_docs` | `19-液压钳升降平台设计.md` + lifting_platform BOM | ≥2 envelopes matched (sparser data) |

If the lifting platform test reveals that the walker's tier strategies don't handle that doc's conventions, the result is a known-limitation log entry plus a test skip (NOT a failure). Documenting the gap is more valuable than forcing a design change mid-spec.

### 11.4 Regression

Full suite must go from 270 → 290+ passing, with 0 failures. No existing test broken. The walker is purely additive (replaces one P2 block with another that produces at least as much coverage).

## 12. Data Consistency Invariants

1. **Priority order preserved (cross-module)**: **P1 > P2 > P4 > P3 > P7 > P5/P6**. The walker is P2, writes before P1 runs in `extract_part_envelopes`, and is protected from P7 override via `_PROTECTED_TIERS` in `cad_spec_gen.py:793`. There is a test (`test_priority_invariant_p2_not_overridden_by_p7`) that verifies this by constructing a BOM where P7 would overwrite a P2 entry and asserting the P2 entry survives.
2. **Never raises**: `SectionWalker.extract_envelopes()` catches all internal exceptions, returns what's been collected so far (not what's raised). Integration point adds TWO separate except blocks: one for ImportError (ERROR level — packaging bug) and one for general Exception (WARNING level — runtime issue).
3. **Never silently drops**: all envelope lines the walker finds are either (a) attributed to a matched assembly OR (b) surfaced as UNMATCHED in the generated §6.4.1 subsection. Zero are simply ignored.
4. **Tier tagging**: every matched envelope carries `source = f"P2:section_walker:tier{N}"` (where N is 0/1/2/3). Tier 0 = legacy `_find_nearest_assembly` fallback; Tiers 1/2/3 = walker's hybrid matching.
5. **Granularity tagging**: every envelope produced by this spec's walker carries `granularity = "station_constraint"`. Downstream code MUST NOT treat station constraints as per-part sizing directives. Future per-part extraction work will produce `granularity = "part_envelope"` for entries that CAN be used for sizing.
6. **Axis label preservation**: parenthetical dimension-order labels are captured in `axis_label` field and surfaced in §6.4 rendering. When absent, the walker defaults to `宽×深×高` and logs a WARNING.
7. **UNMATCHED visibility**: `walker.unmatched` is a public list property exposed via `result["_meta"]["walker_unmatched"]` so `cad_spec_gen.py` can render it in the generated §6.4.1 subsection.
8. **Deterministic output**: given identical inputs (same `lines` + same `bom_data`), the walker produces identical output across runs. Test coverage in `test_section_walker_unit.py` runs the walker twice on the same fixture and asserts output equality.
9. **No regex duplication**: the envelope box and cylinder regexes are defined ONCE in `cad_spec_section_walker.py`. `cad_spec_extractors.py` no longer has inline envelope regexes (the old P2 block is deleted).
10. **Tier 0 regression protection**: the walker incorporates `_find_nearest_assembly` as Tier 0 so documents with explicit `GIS-EE-NNN` part_no references in prose context keep working even if Tier 1/2/3 abstain.
11. **No intermediate products touched**: only skill-level files (walker module + extractor update + generator render update + hatch_build). No changes to `cad/<subsystem>/*` or `src/cad_spec_gen/data/python_tools/*` (latter auto-regenerates via hatch).

## 13. Phased Delivery

| Phase | Scope | LOC | Dependencies |
|-------|-------|-----|--------------|
| P0 | Test infrastructure — `tests/fixtures/real_doc_boms/_regenerate.py` + generate the 2 BOM YAML files | ~50 | None |
| P1 | `cad_spec_section_walker.py` module — dataclasses + `_normalize_header` + `_extract_envelope_from_line` + `_is_section_header` | ~100 | P0 |
| P2 | Matching strategies — `_match_by_pattern` + `_match_by_chinese_subsequence` + `_match_by_jaccard` + helpers | ~150 | P1 |
| P3 | `SectionWalker` class — state machine + `extract_envelopes()` method + attribution logic | ~100 | P2 |
| P4 | Integration — replace P2 block in `cad_spec_extractors.py` | ~20 | P3 |
| P5 | Synthetic fixture tests — 10 fixture files + `test_section_walker_fixtures.py` | ~300 (mostly fixture content) | P4 |
| P6 | Unit tests — `test_section_walker_unit.py` | ~400 | P2 (can run in parallel with P3-P5) |
| P7 | Real doc tests — `test_section_walker_real_docs.py` | ~100 | P0 + P4 |
| P8 | `hatch_build.py` update — add walker module to `_PIPELINE_TOOLS` | ~2 | P1 |

**Approx total**: ~1200 LOC (including test fixture content and test boilerplate).

**Parallelism**: P1/P2/P3/P6 form the core critical path. P5 (fixtures) and P7 (real docs) can run in parallel with unit tests (P6) once the walker code exists. P8 can go in at any point after P1.

## 14. Success Criteria

- Running `cad_pipeline.py spec --design-doc 04-末端执行机构设计.md --proceed --auto-fill` produces a `cad/end_effector/CAD_SPEC.md` with a `### 6.4 零件包络尺寸` section containing ≥4 station entries (one per 工位N station that has a `模块包络尺寸` declaration in the source).
- Running the same command on `19-液压钳升降平台设计.md` produces a CAD_SPEC.md with ≥2 entries in `§6.4`.
- All 10 synthetic fixture tests pass.
- All unit tests pass.
- Full regression: 270 → 290+ passing, 0 failures, 0 new skips (except the one documented skip if the lifting platform walker can't handle the doc's conventions).
- `walker.unmatched` is exposed and populated correctly in fixture 05, 06, and 08 tests.
- The `hatch_build.py` addition is minimal (1 line in `_PIPELINE_TOOLS`) and doesn't require other changes.

## 15. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Lifting platform doc uses conventions the 3 tiers don't handle | Document as known limitation, mark test as skip with reason. Do NOT add more tiers mid-spec. |
| Tier 3 Jaccard threshold (0.5) is wrong for some docs | Log the actual score at DEBUG so users can tune if needed. Keep threshold as a module constant, not buried in code. |
| BOM YAML fixtures go stale if `extract_bom` output format changes | The `_regenerate.py` helper is checked in; CI can run it and diff against the committed YAML. Not in this spec but noted. |
| Walker module grows beyond ~500 LOC | Split matching strategies into separate files (`_tiers.py`) if complexity explodes. Not needed for MVP. |
| UNMATCHED logging becomes noise in normal pipeline runs | Use module-name logger so users can suppress via standard Python logging config. |
| Performance: walker runs on every line + every match runs all 3 tiers | Walker is O(lines × bom_size × tier_count). For a 1000-line doc with 10 BOM assemblies, that's 30K simple operations. Negligible compared to the rest of the pipeline (`build_all.py` is 8+ seconds). |

## 16. Out-of-Scope Follow-Ups

Documented here for the backlog. Each item was surfaced during adversarial review by one or more of the 5 reviewers (architect, programmer, 3D designer, mechanical designer, assembly worker).

1. **Downstream parent-assembly lookup in `gen_std_parts.py`** (surfaced by 3D designer #1) — the walker produces envelopes keyed by station assembly part_no (e.g., `GIS-EE-002`), but `gen_std_parts.py` looks up envelopes keyed by individual part_no (e.g., `GIS-EE-002-05`). The keys never match, so no individual std part gets sized. The 10-line fix is to add parent-assembly fallback lookup in `_envelope_to_spec_envelope`. This is the **immediate next follow-up** — without it, the walker's envelope data is invisible to std part sizing. **Pairs well with a `granularity` check** so the parent-assembly fallback only applies when appropriate.

2. **Visual floating parts fix** (surfaced by 3D designer #6, Assembly worker #1) — vendor STEP routing for LEMO/Maxon/ATI via `step_pool_adapter` + per-part envelope distribution from station envelopes using §6.2 stack order as the distribution hint. Requires item 1 as prerequisite.

3. **Assembly validator F3 tightening** (surfaced by Mechanical designer #4) — once envelopes are reliably populated AND granularity-tagged, update `assembly_validator.py` to use envelope-derived compactness thresholds. The granularity tag prevents the validator from using a `station_constraint` as a per-part size check.

4. **Traditional Chinese character normalization** — Spec 2 §17 territory. Walker's pre-normalization step gains an optional `opencc` or hand-maintained S↔T mapping. Until this lands, traditional-character source docs produce empty §6.4 — the walker emits a PROMINENT warning in the generated §6.4 when zero envelopes matched on a document that HAS envelope marker lines, so the failure is visible (Assembly worker #7).

5. **GB/T material alias handling** — Spec 2 §17 territory.

6. **Compound envelope support** (surfaced by 3D designer #2, Mechanical designer #5) — `EnvelopeData` extends to support `list[tuple[shape, dims]]` so lines like `50×40×120mm + Φ25×110mm` preserve both shapes. Required for the GISBOT station 3 solvent tank attachment.

7. **Configurable `ENVELOPE_TRIGGER_TERMS`** (surfaced by Mechanical designer #1) — the constant is declared in this spec but only the GISBOT term is populated. Projects using `外形尺寸`, `总体尺寸`, or `外包络尺寸` would extend the tuple. This is a one-line config change when a new project needs it, documented here as a maintenance point.

8. **Revision diffing** (surfaced by Assembly worker #6) — when the pipeline regenerates §6.4, compare against the previous version and emit a changelog block for envelopes that moved between assemblies or became UNMATCHED. Not technically hard but requires storing previous state in the worktree or a cache.

9. **Override sidecar for shop-floor corrections** (surfaced by Assembly worker #3) — a `walker_overrides.yaml` file in the project that pins specific envelope → assembly mappings by line number. Pipeline reads overrides before publishing §6.4. Enables QA inspectors to correct false positives without editing source design docs.

10. **Cross-domain test corpus** (surfaced by Architect #8, Mechanical designer #7) — add synthetic test fixtures for fixture-tooling, hydraulic, and electrical-enclosure domains to validate that the 3-tier strategy either matches correctly or fails gracefully. The current 2-doc real test corpus is all GISBOT, which does not validate generality claims.

11. **CI enforcement of BOM fixture freshness** (surfaced by Architect #4) — add a CI step that runs `tests/fixtures/real_doc_boms/_regenerate.py` and diffs the output. If fixture files change, fail the CI with a message asking the engineer to review and commit the new BOM fixtures. Prevents the Layer 3 tests from silently going stale.

12. **English-language design docs** — pure-English section headers would benefit from word-level matching with stop words. Not needed for the Chinese-primary pipeline.

13. **`SectionWalker` interface commitment for Spec 2 §17** (surfaced by Architect #6) — when Spec 2 §17 adds traditional character normalization and GB/T aliases, it should EXTEND the walker via constructor-time BOM normalization rather than subclassing. The recommended pattern: `normalized_bom = apply_s_t_and_alias_normalization(bom_data); walker = SectionWalker(lines, normalized_bom)`. Document this here so §17 doesn't accidentally lock in a fragile extension mechanism.

---

**End of design spec.**
