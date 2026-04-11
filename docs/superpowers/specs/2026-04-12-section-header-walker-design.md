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
- **G2** — Replace the existing P2 block in `cad_spec_extractors.extract_part_envelopes()` with an invocation of the walker. Preserve all other priority tiers (P1, P3, P4, P5, P6) unchanged.
- **G3** — Handle the 3 matching strategies (pattern, subsequence, Jaccard) with explicit tier tagging in the envelope `source` field so downstream code and tests can see which tier produced each envelope.
- **G4** — Pass the GISBOT end-effector design doc test: 4+ station envelopes attached to the correct `GIS-EE-00N` assemblies in the generated `§6.4` table.
- **G5** — Pass the lifting-platform design doc test: 2+ envelope attachments where the source doc has envelopes (sparser data — this test validates walker generality, not coverage).
- **G6** — All 10 synthetic fixture docs produce the expected walker output, including the `UNMATCHED` bucket for deliberately unmatchable cases.
- **G7** — Never raise exceptions from the walker; never crash `extract_part_envelopes`; never silently drop envelopes (all unmatched attempts are logged at WARNING).
- **G8** — Preserve the effective priority order: P1 > P2 > P4 > P3 > P5 > P6. The walker produces P2 output which can still be overwritten by P1 (structured parameter tables) when present.

## 3. Non-Goals

- Fixing the visible "floating parts" problem in the GLB assembly (see Background §1 layer 3).
- Updating `assembly_validator.py` F1/F3 thresholds to use envelope data (separate follow-up).
- Traditional Chinese character normalization (`殼體` ↔ `壳体`) — deferred to Spec 2 §17.
- GB/T material alias handling (`45#钢` ↔ `Q235`) — deferred to Spec 2 §17.
- Vendor STEP routing for LEMO/Maxon/ATI parts — deferred follow-up.
- Per-part envelope distribution from station envelopes — deferred follow-up.
- Fuzzy matching beyond character-subsequence and Jaccard (e.g., Levenshtein, embeddings) — deferred.
- Chain-syntax (`A → B → C`) extraction — already handled by `compute_serial_offsets` in P5, not touched.

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
│    │    ├── _match_section_to_assembly(header, bom) → MatchResult  │
│    │    │    ├── Tier 1: _match_by_pattern()                        │
│    │    │    ├── Tier 2: _match_by_chinese_subsequence()            │
│    │    │    └── Tier 3: _match_by_jaccard()                        │
│    │    └── extract_envelopes() → list[WalkerOutput]                │
│    │                                                                 │
│    ├── P1: 零件级参数表 (unchanged — runs AFTER P2, overwrites)    │
│    ├── P5: 全局参数回填 (unchanged)                                 │
│    └── P6: _guess_geometry 回填 (unchanged)                         │
└──────────────────────────────────────────────────────────────────────┘
```

**Why a new module instead of adding to `cad_spec_extractors.py`**: testability and reusability. The walker is complex enough (~300 LOC) to deserve its own test file. The class-based design also makes it reusable by Spec 2 §17's Chinese keyword expansion work later.

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
    tier: int                   # 1, 2, or 3
    confidence: float           # 0.0-1.0


@dataclass(frozen=True)
class EnvelopeData:
    type: str                   # "box" or "cylinder"
    dims: dict                  # {"w": ..., "d": ..., "h": ...} for box
                                # {"d": ..., "h": ...} for cylinder


@dataclass(frozen=True)
class WalkerOutput:
    matched_pno: str | None     # BOM part_no, or None if UNMATCHED
    envelope_type: str          # "box" or "cylinder"
    dims: dict                  # copied from EnvelopeData.dims
    tier: int | None            # 1/2/3 if matched, None if UNMATCHED
    confidence: float           # 0.0 if UNMATCHED, else MatchResult.confidence
    header_text: str            # innermost section header text, or "" if none
    line_number: int            # 0-indexed line number of the envelope marker
```

**Envelope attribution rule**: when an envelope marker is found, attribute it to the **innermost frame that has a non-None `match`** by walking up the stack. If no frame has a match, produce an `UNMATCHED` entry with the raw current-frame header text and log a WARNING. This ensures sections that didn't match a BOM assembly (e.g., "4.1.2 各工位机械结构" — a meta-header that doesn't correspond to a single assembly) don't swallow envelopes; they get pushed down to their child sections.

## 6. Matching Strategies (3 tiers)

All matching is done against a **normalized** form of the section header. Pre-normalization is applied once per header before tier invocation:

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
        # Find BOM assemblies that ALSO contain this category marker,
        # sorted by the number in their name (stable order).
        candidates = [
            a for a in bom_data.get("assemblies", [])
            if re.search(fr"{category}\s*\d+", a.get("name", ""))
        ]
        candidates.sort(key=lambda a: int(
            re.search(fr"{category}\s*(\d+)", a["name"]).group(1)
        ))
        # Pick the candidate whose number matches idx
        for a in candidates:
            m2 = re.search(fr"{category}\s*(\d+)", a["name"])
            if int(m2.group(1)) == idx:
                return MatchResult(pno=a["part_no"], tier=1, confidence=1.0)
    return None
```

**Confidence = 1.0** because pattern extraction is unambiguous when it fires.

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
        return None  # header has no Chinese content; tier 3 may still find something
    for a in bom_data.get("assemblies", []):
        bom_cn = _chinese_only(a.get("name", ""))
        if not bom_cn:
            continue
        if _is_subsequence(bom_cn, header_cn):
            return MatchResult(pno=a["part_no"], tier=2, confidence=0.85)
    return None
```

**Confidence = 0.85** — high but not perfect, because subsequence matching can have false positives if BOM names are very short (e.g., a 2-character BOM name like `"壳体"` might match almost any header containing `"壳"` and `"体"` in order).

**Handles the example**: header `"工位1(0°)：耦合剂涂抹模块"` → Chinese-only = `"工位耦合剂涂抹模块"`. BOM `"工位1涂抹模块"` → Chinese-only = `"工位涂抹模块"`. Is `"工位涂抹模块"` a subsequence of `"工位耦合剂涂抹模块"`? 工→工 ✓ 位→位 ✓ 涂→涂 ✓ (skip 耦合剂) 抹→抹 ✓ 模→模 ✓ 块→块 ✓. **YES** — match returned.

**First match wins**: if multiple BOM assemblies satisfy the subsequence check, the first one in BOM order is returned. This is good enough for the GISBOT case because Tier 1 handles the station numbering correctly before Tier 2 ever runs. Tier 2 is only reached when numbering patterns don't apply.

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
    best = None
    second_best_score = 0.0
    for a in bom_data.get("assemblies", []):
        bom_tokens = _tokenize(a.get("name", ""))
        if not bom_tokens:
            continue
        intersection = len(header_tokens & bom_tokens)
        union = len(header_tokens | bom_tokens)
        score = intersection / union if union > 0 else 0
        if score >= threshold:
            if best is None or score > best[1]:
                second_best_score = best[1] if best else 0.0
                best = (a["part_no"], score)
            elif score == best[1]:
                # Tie — abstain to avoid false positives
                return None
    if best is None:
        return None
    # If the top score is very close to the second, abstain
    if second_best_score > 0 and (best[1] - second_best_score) < 0.1:
        return None
    return MatchResult(pno=best[0], tier=3, confidence=best[1])
```

**Threshold = 0.5** — conservative. Higher produces fewer false positives but misses more real matches.

**Tie handling**: if two BOM assemblies have identical top scores, or scores within 0.1 of each other, the walker abstains (returns `None`) rather than guessing. This matters because the UNMATCHED logging gives users a clear signal to fix their section headers.

## 7. Envelope Marker Recognition

Identical to the current regex set from Spec 1's partial fix (commit `f55350e`), except extracted into a helper function for testability:

```python
_ENVELOPE_BOX_RE = re.compile(
    r"模块包络尺寸(?:\*\*)?[：:]\s*"
    r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
    r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
    r"(\d+(?:\.\d+)?)\s*mm"
)

_ENVELOPE_CYLINDER_RE = re.compile(
    r"模块包络尺寸(?:\*\*)?[：:]\s*"
    r"[ΦφØ∅](\d+(?:\.\d+)?)\s*[×xX]\s*"
    r"(\d+(?:\.\d+)?)\s*mm"
)

def _extract_envelope_from_line(line: str) -> EnvelopeData | None:
    m = _ENVELOPE_BOX_RE.search(line)
    if m:
        return EnvelopeData(
            type="box",
            dims={"w": float(m.group(1)), "d": float(m.group(2)), "h": float(m.group(3))},
        )
    m = _ENVELOPE_CYLINDER_RE.search(line)
    if m:
        return EnvelopeData(
            type="cylinder",
            dims={"d": float(m.group(1)), "h": float(m.group(2))},
        )
    return None
```

**Note**: this regex is the CURRENT Spec 1 fix (already merged). The walker reuses it — there's no new regex work here, only new state management.

## 8. Integration with `extract_part_envelopes`

The existing P2 block (lines 1155-1193 in `cad_spec_extractors.py`) is **replaced** by a walker invocation. All other priority tiers are untouched.

```python
# In extract_part_envelopes() — replacing the existing P2 block

# --- P2: Section walker (NEW) ---
try:
    from cad_spec_section_walker import SectionWalker
    walker = SectionWalker(lines, bom_data)
    for entry in walker.extract_envelopes():
        if entry.matched_pno is None:
            # UNMATCHED — logged by the walker, skipped here
            continue
        pno = entry.matched_pno
        # Only set if no higher-priority tier has already written an envelope
        # (P1 runs AFTER this block and can still overwrite P2 results)
        if pno not in result:
            result[pno] = {
                "type": entry.envelope_type,
                "source": f"P2:section_walker:tier{entry.tier}",
                **entry.dims,
            }
except Exception as exc:
    # Walker errors never abort spec extraction — log and move on
    import logging
    logging.getLogger(__name__).warning(
        "Section walker failed, skipping P2 envelope extraction: %s", exc
    )
```

**Execution order** (existing — unchanged): P3 → P4 → **P2 (new walker)** → P1 → P5 → P6. Later writes overwrite earlier ones in the `result` dict, so the effective priority is P1 > P2 > P4 > P3 > P5 > P6. The section walker produces P2 output, which will be overwritten by any P1 entry (structured parameter table) for the same `part_no`.

**Defensive depth**: the `try/except` at the integration point is defensive — the walker's own contract is "never raises", but we wrap the call anyway so a bug in the walker can't abort the entire spec extraction pipeline.

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

1. **Priority order preserved**: P1 > P2 > P4 > P3 > P5 > P6. The walker is P2, writes before P1 runs, and is overwritten by P1 on conflict.
2. **Never raises**: `SectionWalker.extract_envelopes()` catches all internal exceptions, returns what's been collected so far. Integration point adds a second try/except for defensive depth.
3. **Never silently drops**: all envelope lines the walker finds are either (a) attributed to a matched assembly OR (b) logged as UNMATCHED. Zero are simply ignored.
4. **Tier tagging**: every matched envelope carries `source = f"P2:section_walker:tier{N}"` so downstream code and humans can see which tier made the match.
5. **UNMATCHED visibility**: `walker.unmatched` is a public list property for test assertions and future `cad-lib report` integration. It contains `WalkerOutput` records with `matched_pno=None` and the raw header text.
6. **No regex duplication**: the envelope box and cylinder regexes are defined ONCE in `cad_spec_section_walker.py` and the walker is the only consumer. `cad_spec_extractors.py` no longer has inline envelope regexes (the old P2 block is gone).
7. **Deterministic output**: given identical inputs (same `lines` + same `bom_data`), the walker produces identical output across runs. Used by test assertions.
8. **No intermediate products touched**: only skill-level files (walker module + extractor update + hatch_build). No changes to `cad/<subsystem>/*` or `src/cad_spec_gen/data/python_tools/*` (latter auto-regenerates).

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

Documented here for the backlog:

1. **Visual floating parts fix** — vendor STEP routing for LEMO/Maxon/ATI + per-part envelope distribution from station envelopes. This is the next follow-up spec after this one ships.

2. **Assembly validator F3 tightening** — once envelopes are reliably populated, update `assembly_validator.py` to use envelope-derived compactness thresholds instead of the current fixed 40mm.

3. **Traditional Chinese character normalization** — Spec 2 §17 territory. When that work starts, the walker's pre-normalization step should gain an optional `opencc` or hand-maintained S↔T mapping.

4. **GB/T material alias handling** — Spec 2 §17 territory.

5. **English-language design docs** — the current spec's Tier 3 Jaccard handles mixed content, but a pure-English doc would benefit from word-level matching with stop words. Not needed for the Chinese-primary pipeline.

---

**End of design spec.**
