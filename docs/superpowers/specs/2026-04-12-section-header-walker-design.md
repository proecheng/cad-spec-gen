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
- **G11** — Tag every envelope's semantic `granularity` (`station_constraint` | `part_envelope` | `component`) so downstream code cannot silently misuse a station-level constraint as a per-part sizing directive, AND propagate the tag end-to-end through `PartQuery.spec_envelope_granularity` into `JinjaPrimitiveAdapter` so the invariant is ENFORCED, not just declared.
- **G12** — **Cross-subsystem isolation**: no walker state (regex caches, trigger terms, station patterns) lives at module level in a way that survives across two `SectionWalker(...)` constructions. Running the walker on `end_effector` then `lifting_platform` in the same Python process MUST yield independent, non-leaking results. All per-subsystem configuration is a constructor kwarg with sane defaults.
- **G13** — **Downstream data-flow consistency**: the walker-produced `§6.4 零件包络尺寸` column order is either (a) backward-compatible with the existing positional-index lookup in `codegen/gen_assembly.py::parse_envelopes()` (line 382, reads `cells[3]` as dims) OR (b) the parser is simultaneously updated to resolve columns by header name. Both walker output and downstream consumer must land in the SAME commit. The walker's envelope data MUST be observably consumed by `codegen/gen_std_parts.py` for matched station assemblies.
- **G14** — **Function-chain consistency**: every matcher function (`_find_nearest_assembly`, `_match_by_pattern`, `_match_by_subsequence`, `_match_by_jaccard`) has a documented signature, the dispatcher passes exactly the right argument shape to each, and the spec shows the canonical `_match_section_to_assembly` signature including the two-phase header-vs-context-window distinction (Tier 0 fires at envelope-emit time with a 500-char context window; Tiers 1/2/3 fire at header-push time with normalized header text).
- **G15** — **Observable, reproducible shop-floor audit trail**: every walker decision (matched or abstained) carries a machine-readable `reason` code (`tier1_unique_match`, `tier2_density_tie`, `tier3_below_threshold`, `no_parent_section`, `empty_bom`, etc.) so `§6.4.1 UNMATCHED` rendering can drive actionable suggestions from data, not hand-written prose. The rendered table includes legend blocks explaining tier, confidence, and granularity semantics for non-developer readers.

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

This walker is **generic by construction** — all project-specific vocabulary is passed in via constructor kwargs with GISBOT defaults. A non-GISBOT subsystem is a call-site change, not a fork or a monkey-patch:

```python
SectionWalker(
    lines, bom_data,
    trigger_terms=("外形尺寸", "总体尺寸"),      # chassis / hydraulic convention
    station_patterns=[(r"单元\s*(\d+)", "单元")], # sensor-head convention
    axis_label_default="长×宽×高",                 # US / L×W×H default
)
```

The configurable surfaces (all have GISBOT defaults):

- **`trigger_terms`**: envelope marker vocabulary. Defaults to `("模块包络尺寸",)` (GISBOT compound term; NOT standard GB/T). Regexes compile lazily inside `__init__` from these terms — no module-level cache. Projects using `外形尺寸`, `总体尺寸`, `外包络尺寸`, `轮廓尺寸`, `整体尺寸` pass them directly.
- **`station_patterns`**: Tier 1 structured-numbering patterns. Defaults to `[(r"工位\s*(\d+)", "工位"), (r"第\s*(\d+)\s*级", "级"), (r"模块\s*(\d+)", "模块"), (r"第\s*(\d+)\s*部分", "部分")]`. A chassis doc passing `[(r"驱动轮\s*(\d+)", "驱动轮"), (r"悬挂\s*([A-Z])", "悬挂")]` gets a working Tier 1. If the list is empty, the walker logs `INFO: Tier 1 patterns empty for this subsystem — relying on Tier 2/3 only` so operators have a visible signal.
- **`axis_label_default`**: dimension-order interpretation when the source doc doesn't provide a parenthetical label. Defaults to `"宽×深×高"`. See §5.2 for the mapping table from label → `(X, Y, Z)` ordering.
- **`bom_pno_prefixes`**: Tier 0 regression-scan prefix set. Defaults to auto-extracted from `bom_data` via `{a["part_no"].rsplit("-", 1)[0] for a in bom_data["assemblies"]}` so any `XYZ-ABC-NNN` shape works. Overrides are only needed when a subsystem uses dotted or slash-separated part numbers.

**Failure modes — "won't match" vs "silently wrong"**: the spec discriminates these two explicitly:

1. **Won't match (graceful degradation, visible)**: trigger term missing → walker emits zero envelopes AND emits `ERROR: walker produced zero output on document with no recognized envelope markers — check trigger_terms configuration`. Tier 1 patterns absent → walker logs INFO and falls through to Tier 2/3. Tier 2 CJK-strip produces empty needle on English BOMs → walker logs DEBUG and falls through to Tier 3 ASCII-word matching.
2. **Silently wrong (BUG — spec guarantees this doesn't happen)**: The guarantees that prevent this are (a) tier abstention on ambiguity, (b) `axis_label_default` explicit mapping — no hidden order assumptions — (c) ERROR log when walker produces zero output on a document that does contain envelope-like prose (heuristic: lines containing digits + `×` + `mm`), and (d) tests in §11.2 validate zero false-positive confident matches on the `05_no_bom_match.md` and `06_ambiguous_tokens.md` fixtures AND the newly-added `11_non_gisbot_chassis.md` fixture.

**Cross-subsystem isolation**: the walker is constructed fresh per `extract_part_envelopes` call. No module-level mutable state. If `cad_pipeline.py` processes `end_effector` and `lifting_platform` back-to-back in one Python process, each subsystem gets its own `SectionWalker` with its own compiled regexes and its own state; envelopes cannot leak.

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
│    │    │ Two-phase matching:                                       │
│    │    │  Phase A (header push): Tier 1/2/3 on header text         │
│    │    │  Phase B (envelope emit): Tier 0 on 500-char context      │
│    │    │                                                           │
│    │    ├── _parse_section_header(line) → (level, text) | None     │
│    │    ├── _extract_envelope_from_line(line) → EnvelopeData | None │
│    │    ├── _match_header(header) → MatchResult | None              │
│    │    │    ├── Tier 1: _match_by_pattern(header, patterns, bom)   │
│    │    │    ├── Tier 2: _match_by_subsequence(header, bom)         │
│    │    │    └── Tier 3: _match_by_jaccard(header, bom)             │
│    │    │    (abstains by returning None at each tier; caller None) │
│    │    ├── _match_context(context_window, bom_pno_prefixes, bom)   │
│    │    │    └── Tier 0: _find_nearest_assembly(ctx, bom_prefixes)  │
│    │    │       [fires at envelope-emit time, NOT header push]      │
│    │    └── extract_envelopes() → (list[WalkerOutput], WalkerStats)  │
│    │                                                                 │
│    └── P1: 零件级参数表 (unchanged — runs AFTER P2, overwrites)    │
└──────────────────────────────────────────────────────────────────────┘
       │
       ▼ returns (envelopes, walker_report) — two-value tuple
┌──────────────────────────────────────────────────────────────────────┐
│  cad_spec_gen.py — continues processing the returned envelope dict  │
│                                                                      │
│    ├── P5: 全局参数回填 (line 712 — chain_span)                     │
│    ├── P6: _guess_geometry 回填 (line 759)                          │
│    └── P7: parts_library probing (line 764)                         │
│          ├── _OVERRIDABLE_TIERS = ("P5:", "P6:")                    │
│          └── _PROTECTED_TIERS = ("P1:", "P2:", "P3:", "P4:")        │
│          (no change — prefix "P2:" already covers "P2:walker:tierN")│
│                                                                      │
│    ├── §6.4 rendering (line 308-321)                                │
│    │   ├── Table columns backward-compat: pno|name|type|dims|source │
│    │   │   — new audit data lives in APPENDED columns so            │
│    │   │   codegen/gen_assembly.py::parse_envelopes cells[3]        │
│    │   │   positional lookup still finds dims.                      │
│    │   ├── Legend block (confidence, tier, granularity semantics)   │
│    │   └── §6.4.1 UNMATCHED subsection w/ machine-reason column     │
│    │                                                                 │
│    └── walker_report propagated into PartQuery.spec_envelope +      │
│         .spec_envelope_granularity via codegen/gen_std_parts.py,    │
│         enforced by adapters/parts/jinja_primitive_adapter.py which │
│         REJECTS station_constraint envelopes for per-part sizing.   │
└──────────────────────────────────────────────────────────────────────┘
```

**Effective cross-module priority**: **P1 > P2 > P4 > P3 > P7 > P5/P6**. Within `extract_part_envelopes`, P1 runs last and overwrites P2. After return, P7 can only override entries sourced from P5/P6 (explicit allowlist), NOT P1/P2/P3/P4 (explicit protection).

**Why a new module instead of adding to `cad_spec_extractors.py`**: testability and reusability. The walker is complex enough (~300 LOC) to deserve its own test file. The class-based design also makes it reusable by Spec 2 §17's Chinese keyword expansion work later — §17's planned extension pattern is constructor-time BOM normalization (pass a pre-normalized BOM dict), NOT subclassing. This is called out explicitly so §17 doesn't accidentally pick a fragile extension mechanism.

**Module-level contract**:

```python
class SectionWalker:
    def __init__(
        self,
        lines: list[str],
        bom_data: dict,
        *,
        trigger_terms: tuple[str, ...] = ("模块包络尺寸",),
        station_patterns: list[tuple[str, str]] | None = None,  # None → GISBOT defaults
        axis_label_default: str = "宽×深×高",
        bom_pno_prefixes: tuple[str, ...] | None = None,  # None → auto-derive from BOM
    ) -> None: ...

    def extract_envelopes(self) -> tuple[list[WalkerOutput], WalkerStats]: ...

    @property
    def unmatched(self) -> list[WalkerOutput]: ...  # subset of first return value
```

- Construct fresh per `extract_part_envelopes()` call. No shared state between walker instances.
- `extract_envelopes()` returns a **two-tuple** `(outputs, stats)`. `outputs` is every attempt (matched + unmatched); `stats` is a `WalkerStats` dataclass carrying counters (`axis_label_default_count`, `tier_histogram`, `unmatched_reasons`) for §6.4 footer rendering. **Two-tuple return is load-bearing** — it avoids polluting the main envelope dict with a `_meta` pseudo-part-number (see §8 integration block).
- Regex compilation happens inside `__init__` using the instance's `trigger_terms`. No module-level regex cache.
- Never raises. Internal exceptions are caught and logged at DEBUG. Returns `(collected_so_far, stats)` on internal error.

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
from typing import Literal

# Reason codes — machine-readable audit trail for every walker decision.
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
]


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
    reason: WalkerReason        # machine-readable explanation of why this tier fired


@dataclass(frozen=True)
class EnvelopeData:
    """Immutable envelope data. Hashable so it can live in sets and dict keys.

    `dims` is always stored in CANONICAL (X, Y, Z) axis order regardless of
    source label — the walker rewrites the tuple at extraction time using the
    axis-label mapping in §5.2. Downstream consumers can rely on dims[0]=X,
    dims[1]=Y, dims[2]=Z without re-parsing axis_label.
    """
    type: Literal["box", "cylinder"]
    dims: tuple[tuple[str, float], ...]  # box: (("x", 60.0), ("y", 40.0), ("z", 290.0))
                                         # cylinder: (("d", 45.0), ("z", 120.0))
    axis_label: str | None = None        # raw source label for audit only (already applied)

    def dims_dict(self) -> dict[str, float]:
        """Return canonical (X, Y, Z)-keyed dict for downstream consumers.
        Always called at the boundary into gen_std_parts / JinjaPrimitiveAdapter —
        these consumers receive dict form, never the tuple form."""
        return dict(self.dims)


@dataclass(frozen=True)
class WalkerOutput:
    matched_pno: str | None     # BOM part_no, or None if UNMATCHED
    envelope_type: Literal["box", "cylinder"]
    dims: tuple[tuple[str, float], ...]  # canonical (X, Y, Z) order, same shape as EnvelopeData.dims
    tier: int | None            # 0/1/2/3 if matched, None if UNMATCHED
    confidence: float           # 0.0 if UNMATCHED, else MatchResult.confidence
    reason: WalkerReason        # machine-readable result code (see WalkerReason literal)
    header_text: str            # innermost section header text, or "" if none
    line_number: int            # 0-indexed line number of the envelope marker
    granularity: Literal["station_constraint", "part_envelope", "component"]
                                # "station_constraint" for every envelope this spec produces;
                                # "part_envelope" reserved for future per-part prose extraction
    axis_label: str | None = None
    source_line: str = ""       # raw unmodified source line for traceability
    candidates: tuple[tuple[str, float], ...] = ()  # near-miss list for §6.4.1 suggestions

    def dims_dict(self) -> dict[str, float]:
        return dict(self.dims)


@dataclass(frozen=True)
class WalkerStats:
    """Counters returned alongside outputs for §6.4 rendering footer."""
    total_envelopes: int
    matched_count: int
    unmatched_count: int
    tier_histogram: tuple[tuple[int, int], ...]       # ((0,2), (1,4), (2,1), (3,0))
    axis_label_default_count: int                      # how many envelopes defaulted the label
    unmatched_reasons: tuple[tuple[WalkerReason, int], ...]  # reason → count
```

**Why `tuple[tuple[str, float], ...]` instead of `dict`**: `frozen=True` on a dataclass prevents attribute reassignment but does NOT freeze a mutable `dict` field — the class becomes non-hashable, which silently breaks any test or future code that uses sets or dict keys. The tuple representation preserves immutability and hashability; `dims_dict()` is the canonical boundary converter called EXACTLY at the point where data crosses into `PartQuery.spec_envelope` in `codegen/gen_std_parts.py:275`. No other caller should invoke `dims_dict()`.

**`granularity` field** — every envelope the walker produces is tagged `"station_constraint"` because the walker only extracts station-level `模块包络尺寸` prose markers. Downstream code MUST NOT treat station constraints as per-part sizing directives. This invariant is **enforced end-to-end**, not just declared:

1. Walker emits `WalkerOutput.granularity = "station_constraint"`
2. Integration block stores `result[pno]["granularity"]` into the envelope dict
3. `codegen/gen_assembly.py::parse_envelopes()` reads `granularity` from the rendered §6.4 table (via header-name lookup — see §8.1) and returns it alongside dims
4. `codegen/gen_std_parts.py:275` constructs `PartQuery(spec_envelope=..., spec_envelope_granularity=<value>)`
5. `parts_resolver.PartQuery` gains a new field `spec_envelope_granularity: str = "part_envelope"` (default is safe for all existing callers that don't set it)
6. `adapters/parts/jinja_primitive_adapter._resolve_dims_from_spec_envelope_or_lookup` **REJECTS** envelopes whose `spec_envelope_granularity != "part_envelope"`, falling through to `lookup_std_part_dims`

This six-step chain turns the granularity tag from documentation into runtime enforcement. Without any one of the six steps, the walker's station envelopes would silently size individual std parts as 60×40×290mm — a catastrophic bug. All six steps are IN SCOPE for this spec.

### 5.1 Axis label canonicalization

The walker rewrites `dims` into canonical `(X, Y, Z)` order at extraction time so downstream `codegen/gen_assembly.py:859` (which uses `env[0]` for radial positioning and `env[2]` for stacking) always receives a consistent frame. The mapping:

| `axis_label` (normalized) | dims[0] → | dims[1] → | dims[2] → | Applies to |
|---|---|---|---|---|
| `宽×深×高` (GISBOT default) | `("x", w)` | `("y", d)` | `("z", h)` | 宽=X, 深=Y, 高=Z |
| `长×宽×高` | `("x", l)` | `("y", w)` | `("z", h)` | 长=X, 宽=Y, 高=Z |
| `W×D×H` | `("x", w)` | `("y", d)` | `("z", h)` | same as 宽×深×高 |
| `L×W×H` | `("x", l)` | `("y", w)` | `("z", h)` | same as 长×宽×高 |
| `长×高×宽` | REJECT | REJECT | REJECT | emit UNMATCHED with `reason="unrecognized_axis_label"` |
| `None` (no label) | use `axis_label_default` kwarg | | | `WalkerStats.axis_label_default_count += 1`, WARNING log |

For cylinders, the parser always emits `(("d", diameter), ("z", height))` — no axis rotation.

**Why rewrite at extraction time, not at consumption time**: if the walker stored raw source-order dims and deferred the mapping to `gen_assembly.py`, every downstream consumer would need the mapping table duplicated. Canonicalizing at extraction means exactly ONE place owns the semantics; every consumer sees `(X, Y, Z)`.

**`axis_label` field** is still carried for audit rendering in §6.4 — it's the RAW source label, but the dims have already been reordered. The `axis_label` cell in the rendered table lets a QC inspector see "the source said 长×宽×高 and we reinterpreted it as (X, Y, Z)" without having to open the source doc.

**Envelope attribution rule**: when an envelope marker is found, attribute it to the **innermost frame that has a non-None `match`** by walking up the stack. If no frame has a match, attempt Tier 0 on a 500-char context window preceding the envelope line. If Tier 0 also abstains, produce an UNMATCHED entry with `reason="no_parent_section"` and log a WARNING.

## 6. Matching Strategies (4 tiers — two-phase dispatch)

The walker runs matching in **two phases** because Tier 0 operates on a different argument shape than Tiers 1/2/3:

**Phase A — Header push time**: when `_parse_section_header(line)` returns a new header, the walker invokes `_match_header(header)` which tries Tier 1 → Tier 2 → Tier 3 in order on the normalized header text. The first non-`None` MatchResult is stored on the new `SectionFrame.match`. If all three abstain, `frame.match = None` and the stack push proceeds.

**Phase B — Envelope emit time**: when `_extract_envelope_from_line(line)` returns an `EnvelopeData`, the walker walks up the stack to find the innermost frame with a non-None match. If every ancestor frame has `match=None`, Tier 0 runs as a LAST-RESORT fallback: `_match_context(context_window, bom_pno_prefixes, bom_data)` takes the 500-char text window ending at the current envelope line's byte offset and runs `_find_nearest_assembly(context, bom_prefixes, bom_data)`. If Tier 0 also abstains, the walker emits `WalkerOutput(..., matched_pno=None, reason="no_parent_section")`.

**Why this split matters** — Tier 0's existing implementation in `cad_spec_extractors.py` takes a 500-character text window, NOT a header string. It scans for explicit `GIS-EE-NNN` part number references in prose. A section header string is only 20-50 characters, so running Tier 0 at header-push time would return None almost always. Tier 0 is meaningful only when anchored at an envelope marker's byte offset. Mixing the two tiers into a single dispatcher with one argument type silently makes Tier 0 dead code — this is the round-2 programmer review's #1 critical finding.

**Canonical dispatcher signatures**:

```python
def _match_header(header: str, bom_data: dict,
                  station_patterns: list[tuple[str, str]]) -> MatchResult | None:
    """Phase A: run Tier 1/2/3 on normalized header text.
    Returns None when all three abstain; caller stores on SectionFrame.match."""
    for tier_fn in (_match_by_pattern, _match_by_subsequence, _match_by_jaccard):
        result = tier_fn(header, bom_data, station_patterns) if tier_fn is _match_by_pattern \
                 else tier_fn(header, bom_data)
        if result is not None:
            return result
    return None


def _match_context(context: str, bom_pno_prefixes: tuple[str, ...],
                   bom_data: dict) -> MatchResult | None:
    """Phase B: run Tier 0 on 500-char context window preceding an envelope line.
    Returns None when no explicit part_no matches."""
    pno = _find_nearest_assembly(context, bom_pno_prefixes, bom_data)
    if pno is None:
        return None
    return MatchResult(pno=pno, tier=0, confidence=1.0, reason="tier0_context_window_match")
```

**Tier 0 prefix extraction** — `_find_nearest_assembly` is modified to take the prefixes set as a parameter instead of hardcoding `GIS-EE-NNN`. The walker passes `self.bom_pno_prefixes`, which defaults to `tuple(sorted({a["part_no"].rsplit("-", 1)[0] for a in bom_data.get("assemblies", [])}))`. For `CHASSIS-DRV-001`, the prefix is `CHASSIS-DRV`; for `GIS-EE-002`, the prefix is `GIS-EE`. Regex is `fr"({'|'.join(re.escape(p) for p in prefixes)})-(\d+)"`. This turns Tier 0 into a subsystem-agnostic regression guard — G9 now holds for every subsystem, not just the end-effector.

**Tier summary**:
- **Tier 0** (envelope-emit time, 500-char context window): `_find_nearest_assembly(context, bom_prefixes, bom_data)` — explicit part_no regex scan. Confidence 1.0.
- **Tier 1** (header-push time, normalized header text): `_match_by_pattern` — structured numbering. Confidence 1.0.
- **Tier 2** (header-push time): `_match_by_subsequence` — Chinese-character subsequence OR English-word subsequence (new: dual-path). Confidence 0.85.
- **Tier 3** (header-push time): `_match_by_jaccard` — mixed CJK bigram + ASCII word Jaccard. Confidence = raw Jaccard score.

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
# Default GISBOT patterns — injected via SectionWalker constructor.
_DEFAULT_STATION_PATTERNS = [
    (r"工位\s*(\d+)", "工位"),
    (r"第\s*(\d+)\s*级", "级"),
    (r"模块\s*(\d+)", "模块"),
    (r"第\s*(\d+)\s*部分", "部分"),
]

def _match_by_pattern(header: str, bom_data: dict,
                      station_patterns: list[tuple[str, str]]) -> MatchResult | None:
    for regex, category in station_patterns:
        m = re.search(regex, header)
        if not m:
            continue
        idx = int(m.group(1))
        idx_re = re.compile(fr"{re.escape(category)}\s*(\d+)")
        matching = []
        for a in bom_data.get("assemblies", []):
            m2 = idx_re.search(a.get("name", ""))
            if m2 and int(m2.group(1)) == idx:
                matching.append(a)
        if len(matching) == 0:
            continue  # pattern fired but no BOM row matches — try next pattern
        if len(matching) >= 2:
            # AMBIGUITY at this pattern — multiple BOM rows share 工位N.
            # Abstain at Tier 1 entirely. Do NOT try the next pattern — if
            # this pattern cannot uniquely identify a BOM row, falling through
            # to another pattern that also matches the header would produce
            # a false-confident Tier 1 hit. Return None to hand off to Tier 2.
            return None
        return MatchResult(pno=matching[0]["part_no"], tier=1,
                           confidence=1.0, reason="tier1_unique_match")
    return None
```

**Confidence = 1.0** when a unique match is found. **Ambiguity handling**: if the first pattern that matches the header has 2+ BOM candidates, Tier 1 returns `None` **immediately**, NOT via `continue`. The earlier draft of this code used `continue` which silently fell through to the next pattern — a header like `工位1+模块3` could ambiguity-abstain on 工位 then false-confidently match 模块3 at tier 1. The round-2 programmer review caught this; fix is `return None` on ambiguity.

**Handles the end-effector case**: header `"工位1(0°)：耦合剂涂抹模块"` → pattern `工位(\d+)` extracts `1` → BOM assembly `工位1涂抹模块` (part_no `GIS-EE-002`) → returned.

### 6.2 Tier 2 — Subsequence match (dual-path: CJK characters OR ASCII words)

When pattern extraction fails, try matching by subsequence. The algorithm runs TWO parallel paths and picks the best score:

- **CJK path**: strip to Chinese-only characters from both sides; check if BOM CJK runs are a character-subsequence of header CJK runs.
- **ASCII path**: tokenize both sides into lowercase ASCII words (length ≥ 2); check if BOM word tokens are a word-subsequence of header word tokens.

Whichever path yields the best density wins. This makes Tier 2 work on all-Chinese BOMs, all-English BOMs, and mixed BOMs — the round-2 architect review caught that the original CJK-only path silently skipped every English-named BOM assembly.

```python
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
    header_cjk = _cjk_only(header)
    header_words = _ascii_words(header)

    matches = []
    for a in bom_data.get("assemblies", []):
        name = a.get("name", "")
        bom_cjk = _cjk_only(name)
        bom_words = _ascii_words(name)

        best_density = 0.0
        # CJK path
        if bom_cjk and header_cjk and _is_char_subsequence(bom_cjk, header_cjk):
            best_density = max(best_density, len(bom_cjk) / max(len(header_cjk), 1))
        # ASCII path
        if bom_words and header_words and _is_word_subsequence(bom_words, header_words):
            best_density = max(best_density, len(bom_words) / max(len(header_words), 1))

        if best_density > 0:
            matches.append((a["part_no"], best_density))

    if not matches:
        return None
    # Stable sort: density desc, then part_no asc for deterministic tie-break
    matches.sort(key=lambda m: (-m[1], m[0]))
    if len(matches) == 1:
        return MatchResult(pno=matches[0][0], tier=2, confidence=0.85,
                           reason="tier2_unique_subsequence")
    top_pno, top_dens = matches[0]
    _, runner_dens = matches[1]
    if abs(top_dens - runner_dens) < 0.1:
        return None  # tie → abstain, fall through to Tier 3
    return MatchResult(pno=top_pno, tier=2, confidence=0.85,
                       reason="tier2_unique_subsequence")
```

**Confidence = 0.85** — high but not perfect.

**Tie detection**: if two or more BOM assemblies match with near-identical density (within 0.1), Tier 2 abstains with `reason="tier2_density_tie"` and falls through to Tier 3.

**Deterministic tie-break**: `sort(key=lambda m: (-m[1], m[0]))` uses part_no alphabetically as the secondary key. This ensures QC audit runs are bit-identical regardless of `PYTHONHASHSEED` or BOM source ordering.

**Handles the example**: header `"工位1(0°)：耦合剂涂抹模块"` → CJK-only = `"工位耦合剂涂抹模块"` (9 chars). BOM `"工位1涂抹模块"` → CJK-only = `"工位涂抹模块"` (6 chars). Subsequence check: 工→工 ✓ 位→位 ✓ 涂→涂 ✓ 抹→抹 ✓ 模→模 ✓ 块→块 ✓ **YES**. Density = 6/9 = 0.67. ASCII path degenerates (no ASCII words). Tier 2 returns `GIS-EE-002`.

**Handles English BOM**: header `"## Main Arm Assembly"` → words `["main", "arm", "assembly"]`. BOM `"Main Arm Module"` → words `["main", "arm", "module"]`. CJK path empty; ASCII path: `module` is NOT a subsequence of `[main, arm, assembly]`, so no match at Tier 2 — Tier 3 Jaccard takes over. If the BOM were `"Main Arm"`, ASCII subsequence `[main, arm]` ⊂ `[main, arm, assembly]` → density 2/3 → match at Tier 2.

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
        return None  # reason="tier3_empty_tokens" logged at caller
    # Collect ALL scores ≥ threshold, then rank.
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
        return None  # reason="tier3_below_threshold" logged at caller
    # Stable deterministic sort: score desc, then part_no asc.
    scored.sort(key=lambda x: (-x[1], x[0]))
    best_pno, best_score = scored[0]
    if len(scored) >= 2:
        _, second_score = scored[1]
        if second_score == best_score:
            return None  # exact tie
        if (best_score - second_score) < 0.1:
            return None  # near-tie
    return MatchResult(pno=best_pno, tier=3, confidence=best_score,
                       reason="tier3_jaccard_match")
```

**Bug fix note**: the previous draft of this code had a latent bug where `second_best_score` was only updated inside the `if best is None or score > best[1]` branch, meaning a later candidate with a close-but-not-best score never contributed to the tie-detection. The fixed version collects all above-threshold scores first, then sorts and checks the top two, which handles the case correctly regardless of iteration order over the BOM.

**Threshold = 0.5** — conservative. Higher produces fewer false positives but misses more real matches.

**Tie handling**: if two BOM assemblies have identical top scores, or scores within 0.1 of each other, the walker abstains (returns `None`) rather than guessing. This matters because the UNMATCHED logging gives users a clear signal to fix their section headers.

## 7. Envelope Marker Recognition

Regex compilation is **per-instance** (inside `SectionWalker.__init__`) so every walker instance has its own compiled patterns bound to its own `trigger_terms`. No module-level regex cache — this is load-bearing for G12 (cross-subsystem isolation).

```python
# GISBOT default. Other subsystems pass their own terms via the constructor kwarg.
_DEFAULT_TRIGGER_TERMS: tuple[str, ...] = ("模块包络尺寸",)


def _build_envelope_regexes(trigger_terms: tuple[str, ...]) -> tuple[re.Pattern, re.Pattern]:
    """Build (box_regex, cylinder_regex) for a given trigger-term set.

    Handles bold-before-colon (`模块包络尺寸**：`), bold-around-value
    (`模块包络尺寸：**60×40×290mm**`), and an optional parenthetical axis label.
    """
    trigger = "|".join(re.escape(t) for t in trigger_terms)
    prelude = fr"(?:{trigger})(?:\*\*)?[：:]\s*(?:\*\*)?\s*"
    suffix = fr"\s*(?:\*\*)?(?:\s*[((]([^))]+)[)）])?"

    box_body = (r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
                r"(\d+(?:\.\d+)?)\s*[×xX]\s*"
                r"(\d+(?:\.\d+)?)\s*mm")
    cyl_body = (r"[ΦφØ∅](\d+(?:\.\d+)?)\s*[×xX]\s*"
                r"(\d+(?:\.\d+)?)\s*mm")
    return (
        re.compile(prelude + box_body + suffix),    # groups: 1=w 2=d 3=h 4=axis_label
        re.compile(prelude + cyl_body + suffix),    # groups: 1=dia 2=h 3=axis_label
    )


# In SectionWalker.__init__:
#   self._box_re, self._cyl_re = _build_envelope_regexes(self.trigger_terms)


def _extract_envelope_from_line(self, line: str) -> EnvelopeData | None:
    m = self._box_re.search(line)
    if m:
        raw = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
        axis_label = m.group(4)
        applied = axis_label or self.axis_label_default
        dims = _canonicalize_box_axes(raw, applied)
        if dims is None:
            # unrecognized label — emit UNMATCHED later with reason
            self._axis_label_rejected = True
            return None
        if axis_label is None:
            self._stats_axis_label_default_count += 1
        return EnvelopeData(type="box", dims=dims, axis_label=axis_label)
    m = self._cyl_re.search(line)
    if m:
        return EnvelopeData(
            type="cylinder",
            dims=(("d", float(m.group(1))), ("z", float(m.group(2)))),
            axis_label=m.group(3),
        )
    return None


_AXIS_LABEL_BOX_MAP: dict[str, tuple[int, int, int]] = {
    # Map from normalized label → (raw_w_index, raw_d_index, raw_h_index)
    # where raw is the tuple captured by the regex in source order.
    # A value like (0, 1, 2) means raw[0]→X, raw[1]→Y, raw[2]→Z.
    "宽×深×高": (0, 1, 2),
    "W×D×H": (0, 1, 2),
    "长×宽×高": (0, 1, 2),   # L=X, W=Y, H=Z — BOM convention: first dim is length
    "L×W×H": (0, 1, 2),
    # Variants with explicit ordering that swap axes
    "深×宽×高": (1, 0, 2),
    "宽×高×深": (0, 2, 1),
    # Any label not in this table is REJECTED (returns None from _canonicalize_box_axes).
}


def _canonicalize_box_axes(
    raw: tuple[float, float, float], label: str
) -> tuple[tuple[str, float], ...] | None:
    """Map source-order dims to canonical (X, Y, Z) order using the label table.
    Return None if the label is not in _AXIS_LABEL_BOX_MAP."""
    label_norm = label.strip().replace(" ", "")
    order = _AXIS_LABEL_BOX_MAP.get(label_norm)
    if order is None:
        return None
    return (
        ("x", raw[order[0]]),
        ("y", raw[order[1]]),
        ("z", raw[order[2]]),
    )
```

**Why per-instance compilation**: the round-2 architect review's C1 finding — two subsystems run back-to-back in one process, each with their own `trigger_terms`, CANNOT share a module-level compiled regex. Pinning compilation to `__init__` makes cross-subsystem isolation automatic. The only cost is ~50μs per walker construction; walker is constructed once per `extract_part_envelopes` call, so this is negligible.

**Why canonicalize dims to (X, Y, Z) at extraction time**: round-2 3D reviewer's #3 critical finding. Without canonicalization, a doc using `长×宽×高` produces `dims[0]=length` (the long dimension), and `codegen/gen_assembly.py:859` positions a 1200mm-wide radial part because it assumes `dims[0]=width`. Canonicalizing once at extraction means every downstream consumer sees the same frame.

**Unrecognized axis labels are REJECTED**, not defaulted — the walker emits UNMATCHED with `reason="unrecognized_axis_label"` so a QC inspector can add the label mapping explicitly rather than getting silently-wrong geometry. The `_AXIS_LABEL_BOX_MAP` is extensible via a followup but its default coverage handles the common Chinese and English conventions.

**Unit scaling — `mm` only in this spec**: the regex is hardcoded `mm`. Sources using `cm` or `m` (chassis, platform subsystems) produce zero envelopes on the "won't match" path (§3.2 failure mode 1) and trigger the ERROR log. Unit scaling is deferred to a follow-up (see §16 item 6 for the concrete addition).

**Compound envelope limitation**: a line like `50×40×120mm + Φ25×110mm` matches the box form first and discards the cylinder. Walker emits WARNING `"compound envelope truncated at line N"`. Deferred per §3.1.

## 8. Integration with `extract_part_envelopes`

The existing P2 block in `cad_spec_extractors.py` (lines 1155-1193) is **replaced** by a walker invocation. `extract_part_envelopes` return type is **changed** from `dict[pno, envelope]` to `tuple[dict[pno, envelope], WalkerReport]` where `WalkerReport` carries UNMATCHED entries, stats, and the feature-flag state. Changing the return type is load-bearing — it cleanly avoids the `_meta["walker_unmatched"]` pseudo-part-number key that round-2 reviewers flagged as iteration-incompatible with every existing consumer.

```python
# In extract_part_envelopes() — replacing the existing P2 block

import logging
_log = logging.getLogger("cad_spec_extractors")

# Feature flag — default ON, but can be disabled by a project that hits a
# regression without having to revert code. Read from env var or pipeline
# config (skill-level config, NOT an intermediate product).
_WALKER_ENABLED = os.environ.get("CAD_SPEC_WALKER_ENABLED", "1") == "1"

# ImportError handled at module top-level with try/except to avoid per-call
# retry log spam in batch mode. See §8.2 for rationale.
try:
    from cad_spec_section_walker import SectionWalker, WalkerReport
    _WALKER_AVAILABLE = True
except ImportError as exc:
    _log.error(
        "cad_spec_section_walker module not found — P2 envelope extraction "
        "DISABLED. This is a packaging bug; check hatch_build.py:_PIPELINE_TOOLS. "
        "Error: %s", exc
    )
    SectionWalker = None
    WalkerReport = None
    _WALKER_AVAILABLE = False

# ... inside extract_part_envelopes():

walker_report = None
if _WALKER_ENABLED and _WALKER_AVAILABLE:
    try:
        walker = SectionWalker(lines, bom_data)
        outputs, stats = walker.extract_envelopes()
        for entry in outputs:
            if entry.matched_pno is None:
                continue  # UNMATCHED goes to walker_report, not result
            pno = entry.matched_pno
            # Unconditional write — NO "if pno not in result" guard.
            # P3 runs before us and P1 runs after us; letting P2 overwrite P3
            # and be overwritten by P1 matches the §12 invariant
            # P1 > P2 > P4 > P3. Adding a guard would silently invert the
            # order (P2 would LOSE to P3 instead of winning). The round-2
            # programmer review (finding #6) caught this contradiction
            # between the earlier guard and the claimed invariant.
            result[pno] = {
                "type": entry.envelope_type,
                "source": f"P2:walker:tier{entry.tier}",
                "granularity": entry.granularity,
                "axis_label": entry.axis_label,
                "confidence": entry.confidence,
                "reason": entry.reason,
                "source_line": entry.source_line,
                **dict(entry.dims),
            }
        walker_report = WalkerReport(
            unmatched=[o for o in outputs if o.matched_pno is None],
            stats=stats,
            feature_flag_enabled=True,
        )
    except Exception as exc:
        _log.warning(
            "Section walker runtime failure, skipping P2 envelope "
            "extraction for this document: %s", exc
        )
        walker_report = WalkerReport(unmatched=[], stats=None,
                                     feature_flag_enabled=True,
                                     runtime_error=str(exc))
elif not _WALKER_ENABLED:
    _log.info("CAD_SPEC_WALKER_ENABLED=0 — falling back to legacy P2 regex block")
    # Legacy P2 regex block preserved behind the flag for one release cycle.
    # This block is a verbatim copy of what lives at cad_spec_extractors.py:1155-1193
    # today and will be deleted in the next spec cycle after real-world
    # rollout validates the walker.
    _legacy_p2_regex_block(lines, bom_data, result)
    walker_report = WalkerReport(unmatched=[], stats=None, feature_flag_enabled=False)

# P1 runs AFTER this block — §12 invariant 1.
# ... return (result, walker_report)
```

**Canonical source tag**: `P2:walker:tier{N}` (not `P2:section_walker:tier{N}`). The §8.1 rendering and the `_PROTECTED_TIERS` prefix match both rely on exactly this form. The prefix `P2:` in `cad_spec_gen.py:793`'s `_PROTECTED_TIERS` already covers every `P2:walker:tier*` value, so NO change to `_PROTECTED_TIERS` is needed.

**Return type change affects callers**: `extract_part_envelopes` callers in `cad_spec_gen.py` currently destructure a dict. The new signature returns a two-tuple `(envelopes, walker_report)`; callers must be updated in the same commit:

```python
# Before (cad_spec_gen.py:~308):
envelopes = extract_part_envelopes(lines, bom_data)

# After:
envelopes, walker_report = extract_part_envelopes(lines, bom_data)
# walker_report is used in §6.4 rendering (see §8.1) and passed into
# render_cad_spec_section_6_4(envelopes, walker_report, bom_obj)
```

The WalkerReport dataclass:

```python
@dataclass(frozen=True)
class WalkerReport:
    unmatched: list[WalkerOutput]
    stats: WalkerStats | None          # None when walker ran legacy block
    feature_flag_enabled: bool          # True = walker path, False = legacy path
    runtime_error: str | None = None    # set if walker raised during extraction
```

**Execution order** (verified against `cad_spec_extractors.py` + `cad_spec_gen.py` actual code):
1. In `cad_spec_extractors.extract_part_envelopes()`: P3 → P4 → **P2 (walker, UNCONDITIONAL WRITE)** → P1, later writes overwriting. After this function returns, in-function effective priority is **P1 > P2 > P4 > P3**.
2. In `cad_spec_gen.py` (called after `extract_part_envelopes` returns): P5 backfill → P6 backfill → P7 parts_library probing.
3. P7 respects `_PROTECTED_TIERS = ("P1:", "P2:", "P3:", "P4:")` and only overrides `_OVERRIDABLE_TIERS = ("P5:", "P6:")` sources. The prefix `"P2:"` covers every `"P2:walker:tierN"` value — no change to `_PROTECTED_TIERS` is needed.

**Resulting cross-module effective priority**: **P1 > P2 > P4 > P3 > P7 > P5/P6**.

**Defensive depth**: Import is at module top-level (once per process); the try/except catches ImportError at ERROR level. Runtime walker exceptions are caught inside `extract_part_envelopes` at WARNING level. Feature flag provides a third layer — `CAD_SPEC_WALKER_ENABLED=0` falls through to the legacy regex block without requiring a code revert.

### 8.2 Downstream consumer updates — MANDATORY in the same commit

The walker's output is **invisible to the 3D builder** unless downstream consumers are updated in the same commit. This is the round-2 3D review's #1 critical finding. The following files MUST be modified together:

1. **`codegen/gen_assembly.py::parse_envelopes()`** (line ~382) — today this reads `cells[3]` by positional index for the dims column. Because §8.1 keeps the existing column order unchanged (`料号 | 零件名 | 类型 | 尺寸(mm) | 来源`) and APPENDS the new audit columns at the end, the existing `cells[3]` lookup continues to work. Additionally, parse_envelopes is extended to read the new `granularity` column BY HEADER NAME (not positional index) so it returns `dict[pno, {"dims": ..., "granularity": ...}]` instead of bare `(w, d, h)` tuples. This is the two-step safety strategy: positional lookup stays stable, new semantics go through header-name lookup.

2. **`parts_resolver.py::PartQuery`** (line ~60) — add field `spec_envelope_granularity: str = "part_envelope"`. Default is safe for every existing caller; only `gen_std_parts.py` sets a non-default value.

3. **`codegen/gen_std_parts.py::_envelope_to_spec_envelope`** (line ~58) and the `PartQuery` constructor call (line ~275) — thread the granularity from `parse_envelopes` output into the `PartQuery`.

4. **`adapters/parts/jinja_primitive_adapter.py::_resolve_dims_from_spec_envelope_or_lookup`** (line ~197) — **REJECT** envelopes whose `spec_envelope_granularity != "part_envelope"`:

```python
def _resolve_dims_from_spec_envelope_or_lookup(query, ...):
    if query.spec_envelope is not None:
        if query.spec_envelope_granularity == "part_envelope":
            return _dims_from_part_envelope(query.spec_envelope)
        # station_constraint or component — DO NOT size an individual part
        # from this envelope. Fall through to the lookup table instead.
        _log.debug("spec_envelope for %s has granularity=%s; deferring to lookup",
                   query.pno, query.spec_envelope_granularity)
    return lookup_std_part_dims(query)
```

This is the six-step enforcement chain for G11. Skipping any step means the walker's station envelopes would silently size individual std parts as 60×40×290mm.

**Invariant test** (§12 new invariant): `test_station_constraint_not_used_as_part_size` constructs a fixture walker output with `granularity="station_constraint"`, runs it through `parse_envelopes` → `PartQuery` → `JinjaPrimitiveAdapter`, and asserts the adapter falls through to `lookup_std_part_dims` rather than returning the walker dims.

### 8.1 §6.4 rendering changes — backward-compatible column order + legend

**Critical constraint from round-2 3D review**: `codegen/gen_assembly.py::parse_envelopes()` reads the dims cell via **positional index** `cells[3]`. If the walker changes the column order so `cells[3]` points at a different column, 100% of walker envelope data silently becomes invisible to the 3D builder. The fix: keep the first five columns backward-compatible, APPEND new audit columns.

**Existing column order (preserved)**: `料号 | 零件名 | 类型 | 尺寸(mm) | 来源`
**New appended columns**: `| 轴向标签 | 置信度 | 粒度 | 理由 | 备注`

`codegen/gen_assembly.py::parse_envelopes()` is simultaneously updated to read the new columns by header name (`headers.index("粒度")`), NOT by positional index. Positional lookup of `cells[3]` still works for the dims column because it hasn't moved.

```markdown
### 6.4 零件包络尺寸

> 说明 / Legend
> - **来源** `P1:...` = 参数表 | `P2:walker:tier0` = 历史 part_no 上下文扫描 (回归保护)
> - **来源** `P2:walker:tier1` = 结构编号精确匹配 | `tier2` = 中文字符子序列 | `tier3` = Jaccard 相似度
> - **置信度**: tier1/tier0 = 1.00 (精确); tier2 = 0.85 (高); tier3 = 原始 Jaccard 分数. <0.75 建议人工验证.
> - **粒度**: `station_constraint` = 工位级外包络 (模块必须装入); `part_envelope` = 单件本体尺寸.
>   **禁止**使用 `station_constraint` 尺寸作为单个采购件的建模尺寸.
> - 本表仅列出**工位级/装配级**包络. 子件 (连接器, 轴承, 电机) 依赖供应商 STEP 数据,
>   见 §16 follow-ups 1-2.

| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 | 轴向标签 | 置信度 | 粒度 | 理由 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GIS-EE-001 | 法兰总成 | box | 90×90×25 | P1:param_table | — | 1.00 | part_envelope | — | — |
| GIS-EE-002 | 工位1涂抹模块 | box | 60×40×290 | P2:walker:tier1 | 宽×深×高 | 1.00 | station_constraint | tier1_unique_match | — |
| GIS-EE-003 | 工位2 AE检测模块 | cylinder | Φ45×120 | P2:walker:tier1 | — | 1.00 | station_constraint | tier1_unique_match | — |
| GIS-EE-005 | 工位4 UHF模块 | cylinder | Φ50×85 | P2:walker:tier3 | — | **0.62 VERIFY** | station_constraint | tier3_jaccard_match | 低置信度 |

> 统计: 4 matched, 1 unmatched, 2 defaulted axis order (see §6.4.1)

#### 6.4.1 未匹配的包络 (Unmatched envelopes — manual review required)

| 行号 | 原始文字 | 理由代码 | 建议 |
| --- | --- | --- | --- |
| 183 | `- **模块包络尺寸**：Φ30×45mm` | `no_parent_section` | 包络位于任何章节标题之前. 检查文档结构, 或将包络移到对应工位章节内. |
| 241 | `- **模块包络尺寸**：50×80×120mm` | `tier2_density_tie` | 章节标题与 2 个 BOM 行均匹配: `工位1涂抹模块`, `工位1耦合剂涂抹`. 在源文档章节标题加入区分关键词. |
```

**Rendering rules** in `cad_spec_gen.py`:

1. **Legend block** is rendered from module constants `cad_spec_section_walker.CONFIDENCE_LEGEND_MD` + `GRANULARITY_LEGEND_MD` + `TIER_LEGEND_MD`. Renderer imports them — single source of truth. Shop-floor changes to terminology only require editing the walker module.
2. **Column order**: first five columns UNCHANGED (`料号 | 零件名 | 类型 | 尺寸(mm) | 来源`) to preserve `parse_envelopes cells[3]` positional compatibility. New audit columns APPENDED AFTER `来源`.
3. `置信度` column shows `confidence` as a two-decimal float. When confidence < 0.75, render with **`VERIFY`** suffix to draw QA attention. Walker provides the threshold as `cad_spec_section_walker.CONFIDENCE_VERIFY_THRESHOLD`.
4. `粒度` column shows `granularity`. The legend block explains the semantics.
5. `理由` column shows the machine `WalkerReason` code (e.g., `tier1_unique_match`). Round-2 assembly-worker finding C2: this is what lets a shop-floor operator tell which kind of fix to apply.
6. If `walker_report.unmatched` is non-empty, emit `§6.4.1 未匹配的包络` with columns `行号 | 原始文字 | 理由代码 | 建议`. The `建议` text is generated from a reason→template map in the walker module (not hand-written prose):

```python
UNMATCHED_SUGGESTIONS: dict[WalkerReason, str] = {
    "no_parent_section": "包络位于任何章节标题之前. 检查文档结构, 或将包络移到对应工位章节内.",
    "tier2_density_tie": "章节标题与 {n} 个 BOM 行均匹配: {candidates}. 在源文档章节标题加入区分关键词.",
    "tier3_jaccard_tie": "章节标题与 {n} 个 BOM 行 Jaccard 相似度并列. 添加更具体的章节命名.",
    "tier3_below_threshold": "所有 BOM 行 Jaccard 分数 < 0.5. 检查章节标题是否使用 BOM 中出现的关键词.",
    "empty_bom": "BOM 为空. 检查 BOM 抽取步骤是否正常.",
    "unrecognized_axis_label": "轴向标签 '{label}' 不在已知映射表. 参见 §5.1 轴向标签表.",
    # ... etc. for every WalkerReason value
}
```

7. If the walker produced ZERO matched envelopes on a document that has lines matching the envelope-heuristic (`\d+×\d+×\d+` prose), emit a PROMINENT warning at the top of §6.4: `⚠️ 检测到 N 行疑似包络但 0 行成功提取 — 检查 ENVELOPE_TRIGGER_TERMS 配置是否包含本项目术语`.

8. **Per-subsystem scope**: `walker_report` is scoped to the current `extract_part_envelopes` call, which is scoped to one subsystem. Two subsystems run in sequence get separate reports; envelopes cannot leak. This is tested via the invariant `test_cross_subsystem_isolation` in §11.1.

**Rendering rules live in `cad_spec_gen.py`** — the walker module exports ONLY data (legend constants, suggestion templates, confidence threshold). The renderer owns layout. Round-2 concern: developer vocabulary leaking to shop-floor output is solved by the imported legend block, which ships in the same module that owns the confidence semantics.

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
| `cad_spec_section_walker.py` | **Create** (repo root) | New module: `SectionWalker`, dataclasses, legend constants, suggestion templates, axis-label table |
| `cad_spec_extractors.py` | Modify (~50 lines: replace P2 block, change return type to tuple, update `_find_nearest_assembly` signature to take `bom_pno_prefixes`) | Wire the walker; Tier 0 prefix-parametric; feature flag + legacy fallback block preserved |
| `cad_spec_gen.py` | Modify (~40 lines in `§6.4` rendering function + destructure `(envelopes, walker_report)` tuple) | Render appended audit columns + legend block + §6.4.1 UNMATCHED subsection from `WalkerReport` |
| `codegen/gen_assembly.py` | Modify (`parse_envelopes` ~10 lines) | Read `粒度` column by header name, return `dict[pno, {"dims": ..., "granularity": ...}]` instead of bare tuple. `cells[3]` positional lookup for dims unchanged. |
| `codegen/gen_std_parts.py` | Modify (~5 lines in `_envelope_to_spec_envelope` + `PartQuery` constructor call) | Thread granularity into `PartQuery.spec_envelope_granularity` |
| `parts_resolver.py` | Modify (+1 field on `PartQuery`) | Add `spec_envelope_granularity: str = "part_envelope"` (default safe for legacy callers) |
| `adapters/parts/jinja_primitive_adapter.py` | Modify (~10 lines in `_resolve_dims_from_spec_envelope_or_lookup`) | **REJECT** envelopes whose granularity != `"part_envelope"`; fall through to `lookup_std_part_dims` |
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
| `tests/fixtures/section_walker/10_english_header.md` | Create | `## Station 1: Applicator` — Tier 3 Jaccard on Chinese BOM + English header |
| `tests/fixtures/section_walker/11_non_gisbot_chassis.md` | Create | Chassis-style doc with `外形尺寸` trigger + `驱动轮N` station patterns — passes via constructor kwargs, NOT code edits. Validates G12 (cross-subsystem isolation) + G15 (won't-match vs silently-wrong discrimination) |
| `tests/fixtures/section_walker/12_english_bom.md` | Create | Pure-English BOM (`Main Arm Module`, `LiDAR Mount`) with pure-English headers — validates Tier 2 ASCII-word subsequence dual path |
| `tests/fixtures/section_walker/13_axis_label_rotation.md` | Create | Box envelope with `长×宽×高` label — validates §5.1 axis canonicalization rotates dims[0] from `l` to `x` without breaking positional meaning |
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
- `_match_by_pattern` correctly maps `工位1`, `工位2`, ..., `第1级`, `模块3` to Nth BOM assembly AND abstains (returns None, NOT continues) when the first matching pattern has ambiguous BOM candidates — regression test for round-2 bug (see §6.1 "Ambiguity handling" note)
- `_match_by_subsequence` dual-path: correctly matches `"工位1涂抹模块"` as a CJK subsequence of `"工位耦合剂涂抹模块"` AND matches `["main", "arm"]` as an ASCII-word subsequence of `["main", "arm", "assembly"]`. Test both paths independently and the mixed case.
- `_match_by_jaccard` picks the correct candidate above threshold, abstains on ties, abstains when top score is within 0.1 of second-best, deterministic tie-break via `(-score, pno)` sort key
- `_tokenize` produces correct bigrams for CJK and words for ASCII
- Section stack correctly pushes, pops on re-entering shallower section, handles level-100 bold frames inside markdown sections
- Envelope attribution walks up the stack to find the innermost matched frame
- Envelope with no matched parent AND no Tier 0 context-window match becomes UNMATCHED with `reason="no_parent_section"` AND proper header text
- **Two-phase matching**: `_match_header(header, bom, patterns)` is called at header push time and receives ONLY the header string; `_match_context(ctx, prefixes, bom)` is called at envelope emit time and receives ONLY the 500-char context window. Test that calling `_match_context` with a header string (wrong argument shape) returns None gracefully and does not raise. Regression test for round-2 programmer review #1.
- **Axis canonicalization**: `_canonicalize_box_axes((60, 40, 290), "宽×深×高")` → `(("x",60),("y",40),("z",290))`; same raw tuple with `"长×宽×高"` label → `(("x",60),("y",40),("z",290))` (position-0 means length, which maps to X); unrecognized label → None.
- **Cross-subsystem isolation (G12)**: `test_cross_subsystem_isolation` constructs two `SectionWalker` instances with **different** `trigger_terms` and **different** `bom_data` in sequence, asserts walker A's output has zero entries from walker B's BOM, and asserts walker A's compiled regexes do not leak into walker B's regexes. This validates that module-level regex state has been eliminated.
- **Tier 0 prefix derivation (G9)**: `test_tier0_uses_bom_derived_prefixes` constructs a BOM with `CHASSIS-DRV-001` part numbers, feeds it to the walker, asserts the walker builds a `(CHASSIS-DRV,)` prefix regex and Tier 0 fires on a context containing `CHASSIS-DRV-001`. Validates the Tier 0 regression guard generalizes beyond `GIS-EE`.
- **Granularity enforcement end-to-end (G11)**: `test_station_constraint_not_used_as_part_size` wires a walker output with `granularity="station_constraint"` through `parse_envelopes` → `PartQuery` → `JinjaPrimitiveAdapter._resolve_dims_from_spec_envelope_or_lookup` and asserts the adapter falls through to `lookup_std_part_dims` instead of sizing a std part as 60×40×290mm. This is the six-step enforcement chain test.

### 11.2 Layer 2 — Synthetic fixtures (`@pytest.mark.fast`)

Target: `tests/test_section_walker_fixtures.py`

Each fixture under `tests/fixtures/section_walker/` is paired with an expected-output JSON embedded in the test file. Running the walker against the fixture must produce the expected sequence of matched + unmatched envelopes with the correct tier tags.

Fixture coverage (13 files — see §10.2):

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
| 11 | `non_gisbot_chassis.md` | Chassis doc, `外形尺寸` trigger, `驱动轮N` patterns via constructor kwargs | 3 matched via Tier 1 (no code edits) |
| 12 | `english_bom.md` | English BOM + English headers | Tier 2 ASCII-word subsequence match |
| 13 | `axis_label_rotation.md` | `模块包络尺寸：1200×60×290mm (长×宽×高)` | dims canonicalized to `(x=1200, y=60, z=290)`, raw label preserved in `axis_label` |

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

1. **Priority order preserved (cross-module)**: **P1 > P2 > P4 > P3 > P7 > P5/P6**. The walker is P2, writes UNCONDITIONALLY (no `if pno not in result` guard — that guard would invert the order by making P2 LOSE to P3). P1 runs after and overwrites. P7 is blocked by the `P2:` prefix in `_PROTECTED_TIERS`. Test: `test_priority_invariant_p2_not_overridden_by_p7`.
2. **Never raises**: `SectionWalker.extract_envelopes()` catches all internal exceptions and returns `(collected_so_far, stats)`. Integration adds THREE layers of defense: (a) ImportError at module top-level ERROR, (b) runtime exceptions at function-level WARNING, (c) `CAD_SPEC_WALKER_ENABLED=0` feature flag falls through to the legacy regex block.
3. **Never silently drops**: every envelope line is either (a) attributed to a matched assembly OR (b) surfaced in `walker_report.unmatched` with a machine-readable `reason` code. Zero are ignored. This is validated per-fixture in §11.2.
4. **Canonical source tag**: every matched envelope carries `source = f"P2:walker:tier{N}"`. The prefix `P2:` matches `_PROTECTED_TIERS` in `cad_spec_gen.py:793` — no change to that constant needed. Rendering, protection, and test-harness string searches all use the same `P2:walker:` form.
5. **Granularity enforcement (six-step chain)**: every envelope this spec's walker produces carries `granularity = "station_constraint"`, and the tag is enforced end-to-end through `parse_envelopes` → `PartQuery.spec_envelope_granularity` → `JinjaPrimitiveAdapter`. The adapter REJECTS station_constraint envelopes for per-part sizing. Test: `test_station_constraint_not_used_as_part_size`.
6. **Canonical (X, Y, Z) axis order at extraction time**: the walker rewrites box dims into `(("x", ...), ("y", ...), ("z", ...))` using the §5.1 axis-label table BEFORE storing. Downstream consumers (`gen_assembly.py:859`, `jinja_primitive_adapter.py`) receive dims in canonical frame and do NOT need to re-parse `axis_label`. Raw source label is preserved in `WalkerOutput.axis_label` for audit.
7. **UNMATCHED carries machine reason**: every UNMATCHED `WalkerOutput` has `reason: WalkerReason` set to one of the literal values, NOT free-form text. The renderer maps reason → suggestion template from `UNMATCHED_SUGGESTIONS` dict. Shop-floor operators can act without developer intervention.
8. **Deterministic output regardless of `PYTHONHASHSEED`**: Tier 2 and Tier 3 sorts use `(-score, pno)` tuple keys so ties break alphabetically — output is bit-identical across runs. Test: `test_walker_deterministic_under_hash_randomization` subprocesses the walker with `PYTHONHASHSEED=random` and diffs against a fixed-seed baseline.
9. **No regex duplication**: envelope regexes are compiled ONCE per-walker-instance inside `SectionWalker.__init__`. `cad_spec_extractors.py` has no inline envelope regexes (old P2 block deleted, kept only behind the feature flag).
10. **Tier 0 regression protection — subsystem-agnostic**: `_find_nearest_assembly(context, bom_pno_prefixes, bom_data)` takes BOM-derived prefixes, NOT hardcoded `GIS-EE`. Works on `CHASSIS-DRV-NNN`, `LIFT-HYD-NNN`, etc. Test: `test_tier0_uses_bom_derived_prefixes`.
11. **Cross-subsystem isolation**: module-level state is IMMUTABLE after import. `ENVELOPE_TRIGGER_TERMS` is only a default constant; every walker instance has its own compiled regexes and its own `station_patterns` / `trigger_terms` / `bom_pno_prefixes`. Running two walkers in sequence within one Python process cannot leak state. Test: `test_cross_subsystem_isolation`.
12. **No intermediate products touched — at edit time OR at runtime**: only skill-level files are modified by this spec's implementation. The walker performs ZERO filesystem writes at runtime (no debug logs, caches, or trained-match files anywhere under `cad/<subsystem>/`). All state is in-memory; all diagnostic output goes to stderr via Python logging. Acceptance tests use `tmp_path` fixtures and a `--out-dir` CLI flag; they never mutate `cad/end_effector/` or any other pinned subsystem directory.
13. **Walker never touches material/color fields**: walker output dict contains `type`, `dims`, `source`, `granularity`, `axis_label`, `confidence`, `reason`, `source_line`. NO `material`, `color`, or `material_tag` keys. P3 material backfill is orthogonal and runs independently. Test: `test_walker_does_not_write_material_field`.
14. **Two-phase matching argument types are enforced**: `_match_header(header: str, ...)` takes a header string; `_match_context(context: str, ...)` takes a 500-char window. Calling `_match_context` with a header or `_match_header` with a context window is a static type error caught at mypy time AND a runtime assertion (`assert len(context) >= 100 or context == ""`).

## 13. Phased Delivery

| Phase | Scope | LOC | Dependencies |
|-------|-------|-----|--------------|
| P0 | Test infrastructure — `tests/fixtures/real_doc_boms/_regenerate.py` + generate 2 BOM YAML fixtures. Write target is explicit absolute path `tests/fixtures/real_doc_boms/<name>.yaml`; helper must NOT write adjacent to source docs in `D:/Work/cad-tests/`. | ~50 | None |
| P1 | `cad_spec_section_walker.py` skeleton — dataclasses (`SectionFrame`, `MatchResult`, `EnvelopeData`, `WalkerOutput`, `WalkerStats`, `WalkerReport`) + `WalkerReason` literal + legend constants + `UNMATCHED_SUGGESTIONS` + `_AXIS_LABEL_BOX_MAP` + `_canonicalize_box_axes` | ~200 | P0 |
| P2 | Matching strategies — `_match_by_pattern`, `_match_by_subsequence` (dual-path CJK+ASCII), `_match_by_jaccard`, `_find_nearest_assembly` (modified to take `bom_pno_prefixes`), `_match_header` dispatcher, `_match_context` dispatcher | ~200 | P1 |
| P3 | `SectionWalker` class — constructor with kwargs (`trigger_terms`, `station_patterns`, `axis_label_default`, `bom_pno_prefixes`), state machine, two-phase `extract_envelopes()` method, attribution logic, per-instance regex compilation | ~150 | P2 |
| P4 | Integration — replace P2 block in `cad_spec_extractors.py`, change return type to `(envelopes, walker_report)`, add `CAD_SPEC_WALKER_ENABLED` feature flag with legacy fallback, update `_find_nearest_assembly` signature | ~60 | P3 |
| P5 | Downstream consumer updates (**mandatory atomic with P4**) — `codegen/gen_assembly.py::parse_envelopes` reads granularity by header name; `parts_resolver.PartQuery` gains `spec_envelope_granularity` field; `codegen/gen_std_parts.py` threads granularity; `adapters/parts/jinja_primitive_adapter.py` REJECTS station_constraint envelopes | ~40 | P4 |
| P6 | `cad_spec_gen.py` §6.4 rendering — destructure `(envelopes, walker_report)` tuple, render new columns, legend block, §6.4.1 UNMATCHED subsection with reason→template suggestions | ~60 | P4 |
| P7 | Synthetic fixture tests — 13 fixture files (10 original + 3 new: non-GISBOT chassis, English BOM, axis-label rotation) + `test_section_walker_fixtures.py` | ~400 | P5 + P6 |
| P8 | Unit tests — `test_section_walker_unit.py` including G9/G11/G12 regression tests + cross-subsystem isolation + determinism under hash randomization | ~500 | P3 (can run in parallel with P4-P7) |
| P9 | Real doc tests — `test_section_walker_real_docs.py` (uses tmp_path + `--out-dir` flag; does NOT touch `cad/end_effector/`) | ~120 | P0 + P5 |
| P10 | `hatch_build.py` update — add walker module to `_PIPELINE_TOOLS` | ~2 | P1 |

**Approx total**: ~1700 LOC (including fixture content, test boilerplate, and downstream consumer updates).

**Parallelism**: P1/P2/P3/P8 form the core critical path. P4 and P5 MUST land in the same commit (changing the return type of `extract_part_envelopes` without updating `cad_spec_gen.py` callers would break the pipeline). P7 and P9 can run in parallel with P8 once P5+P6 exist.

**Feature flag removal**: the legacy P2 regex fallback behind `CAD_SPEC_WALKER_ENABLED=0` is kept for ONE release cycle. The next spec in the sequence deletes the fallback after real-world rollout validates the walker on ≥3 subsystems.

## 14. Success Criteria

**All acceptance tests write to `tmp_path` fixtures via a new `cad_pipeline.py spec --out-dir <tmp>` flag; they NEVER mutate `cad/end_effector/` or any other pinned subsystem directory.** The existing `cad/end_effector/` state is preserved across test runs — this is a round-2 mechanical review C1 requirement (intermediate-product rule).

- **Real-doc end-effector test**: `cad_pipeline.py spec --design-doc 04-末端执行机构设计.md --out-dir <tmp> --proceed --auto-fill` produces `<tmp>/end_effector/CAD_SPEC.md` with a `### 6.4 零件包络尺寸` section containing ≥4 station entries sourced `P2:walker:tier1`.
- **Real-doc lifting-platform test**: same command on `19-液压钳升降平台设计.md` produces `<tmp>/lifting_platform/CAD_SPEC.md` with ≥2 entries in `§6.4`.
- **Non-GISBOT fixture test (G12)**: `test_chassis_fixture` constructs `SectionWalker(lines, bom, trigger_terms=("外形尺寸",), station_patterns=[(r"驱动轮\s*(\d+)", "驱动轮")])` and asserts 3 matched entries — no code edits to the walker module. Validates generality.
- **English BOM fixture test**: `test_english_bom_fixture` feeds an all-English BOM and asserts Tier 2 ASCII-word subsequence path matches `Main Arm` inside `Main Arm Module`.
- **Axis rotation fixture test**: `test_axis_label_canonicalization` feeds a `长×宽×高`-labeled envelope and asserts `dims[0].name == "x"` (not `"l"`) and the value is the length dimension. Validates canonical (X, Y, Z) storage.
- **Cross-subsystem isolation test (G12)**: `test_two_walkers_different_trigger_terms_same_process` constructs walker A with `trigger_terms=("模块包络尺寸",)` and walker B with `trigger_terms=("外形尺寸",)` sequentially in one process, asserts walker A's compiled regex does not match `外形尺寸` lines and walker B's compiled regex does not match `模块包络尺寸` lines — no module-level cache leaks.
- **Granularity enforcement test (G11)**: `test_station_constraint_not_used_as_part_size` — walker output with `granularity="station_constraint"` flows through `parse_envelopes` → `PartQuery` → `JinjaPrimitiveAdapter` and the adapter falls through to `lookup_std_part_dims` (NOT sizes a part as 60×40×290mm).
- **Tier 0 prefix test (G9)**: `test_tier0_matches_non_gisbot_prefix` — BOM with `CHASSIS-DRV-001` entries, context window `"see CHASSIS-DRV-001 specification"`, asserts Tier 0 fires.
- **Determinism test (G15)**: `test_walker_deterministic_under_hash_randomization` subprocesses the walker with `PYTHONHASHSEED=random` and diffs against a fixed-seed baseline.
- All 13 synthetic fixture tests pass.
- All unit tests pass.
- Full regression: 270 → 295+ passing, 0 failures, 0 new skips. The `lifting_platform` test is allowed to skip with a documented reason if the walker legitimately cannot handle the doc's conventions, but NOT as an excuse to hide walker bugs.
- `walker_report.unmatched` is non-empty and correctly populated in fixture 05, 06, and 08 tests.
- **Feature flag rollback drill**: `CAD_SPEC_WALKER_ENABLED=0 pytest` runs the legacy P2 regex block and the full suite still passes — validates the rollback path works without requiring a code revert.
- The `hatch_build.py` addition is minimal (1 line in `_PIPELINE_TOOLS`) and doesn't require other changes.
- **Intermediate-product audit**: `git status` after a full test run shows ZERO modifications to `cad/end_effector/**` or `cad/lifting_platform/**`. Enforced in CI via a test that snapshots those paths before and after the test suite.

## 15. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Walker misbehaves on a production subsystem post-deploy | `CAD_SPEC_WALKER_ENABLED=0` environment variable falls back to the legacy P2 regex block without requiring a code revert. Legacy block kept for one release cycle. |
| Column-order change breaks `codegen/gen_assembly.py::parse_envelopes cells[3]` positional lookup | §8.1 keeps the first five columns in the existing order (`料号 | 零件名 | 类型 | 尺寸(mm) | 来源`); new audit columns are APPENDED. Positional `cells[3]` still resolves to dims. New semantics (granularity) go through header-name lookup. |
| Changing `extract_part_envelopes` return type from dict to tuple breaks callers | All callers in `cad_spec_gen.py` are updated in the same commit (P4+P6 land together). CI catches any uncaught caller on first test run. |
| Cross-subsystem state leak via module-level regex cache | Regexes compiled per-walker-instance in `__init__`. Module-level constants are IMMUTABLE. `test_cross_subsystem_isolation` asserts this. |
| Two walker construction sites in tests silently share state | Dedicated regression test — round-2 architect review C1. |
| `granularity` tag not propagated through PartQuery → JinjaPrimitiveAdapter | Six-step enforcement chain documented in §5 + test `test_station_constraint_not_used_as_part_size`. Missing any step fails the test. |
| Axis label mismatch silently rotates 3D geometry 90° | Canonical (X, Y, Z) rewrite at extraction time via `_AXIS_LABEL_BOX_MAP`. Unrecognized labels REJECT rather than default silently. Test `test_axis_label_canonicalization`. |
| Tier 0 hardcoded `GIS-EE-NNN` regex fails on chassis/lifting subsystems | Prefix set is derived from BOM data at walker-construction time. Test `test_tier0_uses_bom_derived_prefixes`. |
| Lifting platform doc uses conventions the tiers don't handle | Documented known limitation, test can skip with reason. |
| Tier 3 Jaccard threshold (0.5) is wrong for some docs | Log actual score at DEBUG. Threshold is module constant, not buried. |
| BOM YAML fixtures go stale if `extract_bom` output format changes | `_regenerate.py` checked in; CI diff deferred to follow-up #12. |
| UNMATCHED logging becomes noise | Module-name logger supports standard suppression. |
| Performance | O(lines × bom × tiers); 30K ops for a 1000-line doc — negligible vs `build_all.py` 8s. |

## 16. Out-of-Scope Follow-Ups

Backlog items. Round-2 review REMOVED several items that were previously here (parent-assembly fallback, configurable trigger terms, cross-subsystem generality, granularity enforcement) — they are now **in scope** in §5, §7, §8.2, §10.1, and §12. Items that remain out of scope:

1. **Visual floating parts fix** (3D #6, Assembly #1) — vendor STEP routing for LEMO/Maxon/ATI via `step_pool_adapter` + per-part envelope distribution from station envelopes. This is the logical next spec in the sequence; it consumes the envelope data this spec produces.

2. **Assembly validator F3 tightening** (Mechanical #4) — once envelopes are reliably populated AND granularity-enforced end-to-end, update `assembly_validator.py` to use envelope-derived compactness thresholds.

3. **Traditional Chinese character normalization** — Spec 2 §17 territory. Walker's pre-normalization step gains an optional `opencc` or hand-maintained S↔T mapping. Until this lands, traditional-character source docs produce the G15 "won't match, visibly flagged" failure mode (ERROR log, not silent).

4. **GB/T material alias handling** — Spec 2 §17 territory.

5. **Compound envelope support** (3D #2, Mechanical #5) — `EnvelopeData` extends to support `list[tuple[shape, dims]]` so lines like `50×40×120mm + Φ25×110mm` preserve both shapes. Required for the GISBOT station 3 solvent tank attachment.

6. **Unit scaling (cm/m)** — extend `_build_envelope_regexes` to match `\s*(mm|cm|m)\b` and apply a scale factor. Chassis and lifting-platform docs commonly use meter-scale dimensions. Code impact is localized to the regex + a scale lookup in `_extract_envelope_from_line`; the change is small but deferred here to keep this spec focused on the assembly-matching bug chain.

7. **Single-dim / disc envelope support** — `Φ60mm` (disc) or `长1200mm` (linear rod) are not handled by box/cylinder regexes. Adds a third `_ENVELOPE_DISC_RE` and `type="disc"` enum value.

8. **Tolerance preservation** (Mechanical I2) — `EnvelopeData` gains a `tolerances: tuple[tuple[str, float, float], ...] | None` field and the regex parses `60 ± 0.5 × 40 ± 0.3 × 290mm`. Needed for F1/F5 assembly-fit validation but not for nominal sizing.

9. **Revision diffing** (Assembly #6) — when the pipeline regenerates §6.4, compare against the previous version and emit a changelog for envelopes that moved between assemblies.

10. **Override sidecar for shop-floor corrections** (Assembly #3) — a `walker_overrides.yaml` file at `parts_library.<project>.yaml` level (skill-level config, NOT in `cad/<subsystem>/`) that pins specific envelope → assembly mappings. Enables QA inspectors to correct false positives without editing source design docs OR intermediate products.

11. **Cross-domain real-doc corpus** (Architect #8) — add real docs (not just synthetic fixtures) from fixture-tooling, hydraulic, and electrical-enclosure projects. This spec ships with one new synthetic chassis fixture (`11_non_gisbot_chassis.md`) which validates the `SectionWalker(trigger_terms=...)` config surface but is still synthetic.

12. **CI enforcement of BOM fixture freshness** (Architect #4) — CI step that runs `tests/fixtures/real_doc_boms/_regenerate.py` and diffs; fails if fixtures drift.

13. **`--walker-trace` CLI flag for bug reporting** (Assembly C4) — `cad_pipeline.py spec --walker-trace` dumps a per-tier, per-candidate score trace alongside CAD_SPEC.md so shop-floor bug reports can carry reproduction evidence.

14. **Bilingual rendering locale** (Assembly I3) — `CAD_SPEC_LOCALE` env var controls whether §6.4 headers render in Chinese, English, or bilingual. Default Chinese is fine for GISBOT.

15. **Assembly bounding-box sanity check** (Assembly I2) — after `cad_pipeline.py build`, a post-step reads `assembly_report.json` and flags walker envelopes whose dims exceed 2× the built-bbox corresponding extent. Cheap catch for OCR typos and unit confusion.

16. **`SectionWalker` interface commitment for Spec 2 §17** (Architect #6) — when Spec 2 §17 adds traditional character normalization and GB/T aliases, extend via constructor-time BOM normalization, not subclassing: `normalized_bom = apply_s_t_and_alias_normalization(bom_data); walker = SectionWalker(lines, normalized_bom)`.

---

**End of design spec.**
