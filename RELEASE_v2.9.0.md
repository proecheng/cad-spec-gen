# v2.9.0 — Section-header walker + granularity enforcement + vendor synthesizer

**Release date:** 2026-04-11
**Theme:** Close the envelope-attribution data gap from Markdown design docs to bd_warehouse builders, enforce station-vs-part semantics end-to-end, and warm vendor STEP caches automatically on fresh projects.

---

## TL;DR

- **New module `cad_spec_section_walker.py`** (~770 lines) — a stateful Markdown walker that attributes `模块包络尺寸` envelope markers to BOM assemblies via 4-tier hybrid matching, replacing the broken substring-based P2 regex block.
- **Six-step granularity enforcement chain**: station-level envelopes can no longer silently size individual purchased parts. `JinjaPrimitiveAdapter` REJECTS `station_constraint` envelopes and falls through to `lookup_std_part_dims`.
- **Vendor STEP auto-synthesizer**: `parts_library.default.yaml` ships mappings that point at the shared cache (`~/.cad-spec-gen/step_cache/`); first-use auto-writes parametric stand-ins for Maxon/LEMO/ATI parts. Fresh projects with only a design doc route vendor rows to real geometry without hand-crafted YAML.
- **Cross-subsystem configuration**: `SectionWalker` takes kwargs for `trigger_terms`, `station_patterns`, `axis_label_default`, `bom_pno_prefixes` — non-GISBOT subsystems (chassis, lifting platform, English-BOM projects) work without code edits.
- **Feature flag `CAD_SPEC_WALKER_ENABLED=0`** falls back to the legacy P2 regex block (preserved for one release cycle of rollback safety).
- **113 new tests** (270 → 383), zero regressions.

---

## The problem this solves

During the v2.8.2 end-to-end validation on the real GISBOT end-effector design document, `cad_spec_extractors.extract_part_envelopes()` returned **zero envelopes** despite the source containing four explicit `模块包络尺寸` markers. Diagnosing the bug chain revealed three layers:

1. **Regex bug** — the old regex `模块包络尺寸[：:]` didn't handle markdown bold wrappers. Fixed in v2.8.2 commit `f55350e`.
2. **Assembly-matching bug** — even after the regex matched, `_find_nearest_assembly()` returned `None` for all four because its first-4-character substring match of BOM assembly names was too strict. The design doc used `工位1(0°)：耦合剂涂抹模块` section headers, and the BOM-normalized name `工位1涂抹模块` has no 4-char prefix substring in the header.
3. **Distribution gap** — even after (1) and (2) are fixed, station-level envelopes would have been silently used to size individual std parts inside the station, producing LEMO connectors sized as 60×40×290 mm.

v2.9.0 ships the fixes for layers 2 and 3.

---

## What's new

### `cad_spec_section_walker.py` — 4-tier hybrid matching

A new module at the repo root. Walks design-doc lines linearly, tracks an active section stack, and emits envelope attribution records via 4 tiers:

- **Tier 0** — `_find_nearest_assembly` on a 500-char context window (regression guard for docs that contain explicit `GIS-EE-NNN` part_no references in prose). Confidence 1.0.
- **Tier 1** — structured pattern extraction (`工位N`, `第N级`, `模块N`, `第N部分`). Abstains on ambiguity (multiple BOM rows share the same station number). Confidence 1.0.
- **Tier 2** — dual-path subsequence matching. CJK character subsequence OR ASCII word subsequence, whichever gives the best density. Abstains on near-tie (gap < 0.1). Confidence 0.85. Fixes the v2.8.2 round-2 architect review's finding that CJK-only matching silently skipped every English-named BOM assembly.
- **Tier 3** — mixed CJK-bigram + ASCII-word Jaccard similarity, threshold 0.5. Stable `(-score, pno)` tie-break sort for deterministic output under `PYTHONHASHSEED=random`.

**Two-phase dispatch**: `_match_header(header, bom, patterns)` runs Tier 1/2/3 at header-push time; `_match_context(context, bom_pno_prefixes, bom)` runs Tier 0 at envelope-emit time with a 500-char window. Two separate functions with different argument shapes prevent Tier 0 from becoming dead code (round-2 programmer review #1 finding).

**Per-instance configuration** — no module-level state:
```python
SectionWalker(
    lines, bom_data,
    trigger_terms=("外形尺寸",),             # chassis / hydraulic convention
    station_patterns=[(r"驱动轮\s*(\d+)", "驱动轮")],  # sensor-head convention
    axis_label_default="长×宽×高",            # US / L×W×H default
    bom_pno_prefixes=("CHASSIS-DRV",),       # tier 0 prefix override
)
```
All four kwargs have GISBOT defaults so existing call sites don't change. Regex compilation is per-instance inside `__init__` — two walkers with different `trigger_terms` running back-to-back in one process cannot share state.

### Six-step granularity enforcement chain

The walker tags every envelope with `granularity: Literal["station_constraint", "part_envelope", "component"]`. Every envelope this spec produces is tagged `"station_constraint"` because `模块包络尺寸` semantically means "this module must fit within this bounding box" — NOT "any individual part inside is this size". The tag is enforced end-to-end:

1. Walker emits `WalkerOutput.granularity = "station_constraint"`
2. `extract_part_envelopes` writes `result[pno]["granularity"]` into the envelope dict
3. `cad_spec_gen.py` `§6.4 零件包络尺寸` rendering adds a `粒度` column
4. `codegen/gen_assembly.py::parse_envelopes` reads the column by header name (positional `cells[3]` dims lookup unchanged for backward compat)
5. `codegen/gen_std_parts.py` threads the value into `PartQuery.spec_envelope_granularity` (new field, default `"part_envelope"` safe for all legacy callers)
6. `adapters/parts/jinja_primitive_adapter.py::_resolve_dims_from_spec_envelope_or_lookup` **REJECTS** envelopes with granularity != `"part_envelope"` and falls through to `lookup_std_part_dims`

Without this six-step chain, a walker-produced 60×40×290 mm station constraint would silently size a LEMO connector as 60×40×290 mm. The invariant is guarded by `tests/test_walker_downstream_integration.py::test_station_constraint_not_used_as_part_size`.

### Canonical (X, Y, Z) axis order at extraction time

Box dims are rewritten to canonical order using `_AXIS_LABEL_BOX_MAP` at extraction time. Downstream `codegen/gen_assembly.py:859` (which uses `env[0]` for radial positioning and `env[2]` for stacking axis) always receives a consistent frame regardless of whether the source label was `宽×深×高`, `长×宽×高`, or `W×D×H`. Unrecognized labels return `None` (no silent defaulting); the caller surfaces them as UNMATCHED with `reason="unrecognized_axis_label"`. Comma-prefix fallback handles real-doc variants like `宽×深×高，含储罐延伸` by matching the pre-comma portion.

### Vendor STEP auto-synthesizer

`adapters/parts/vendor_synthesizer.py` (329 lines, new) — a factory registry that builds dimensionally-accurate parametric stand-ins for vendor parts:

- Maxon GP22C 53:1 planetary gearhead
- LEMO FGG.0B.307 push-pull plug
- ATI Nano17 6-axis force/torque sensor
- plus any factory registered under `spec.synthesizer`

`step_pool_adapter` auto-invokes the synthesizer when a referenced STEP file is missing, writing the result into the shared cache (`~/.cad-spec-gen/step_cache/` or `$CAD_SPEC_GEN_STEP_CACHE`). Real vendor STEP files still win when present at the same path. `parts_library.default.yaml` ships vendor mappings using the new `keyword_contains` matcher (substring across BOM `name_cn` OR `material`) so one default rule covers project-specific naming variations.

### `§6.4` rendering upgrade

The generated `§6.4 零件包络尺寸` table now includes:

1. **Legend block** rendered from walker module constants (`TIER_LEGEND_MD`, `CONFIDENCE_LEGEND_MD`, `GRANULARITY_LEGEND_MD`) — single source of truth for shop-floor terminology.
2. **Appended audit columns**: `| 轴向标签 | 置信度 | 粒度 | 理由 | 备注`. First 5 columns unchanged so `parse_envelopes cells[3]` positional dims lookup stays backward-compatible.
3. **Confidence VERIFY flag** when confidence < 0.75 renders as `**0.62 VERIFY**`.
4. **`§6.4.1 未匹配的包络` subsection** when `walker_report.unmatched` is non-empty. Columns: `行号 | 原始文字 | 理由代码 | 建议`. Suggestions are formatted from `UNMATCHED_SUGGESTIONS` templates keyed on the machine-readable `WalkerReason` code — the shop floor can act without opening the walker module or asking a developer.

### `cad_pipeline.py spec --out-dir` flag

The `spec` subcommand gains `--out-dir <path>` so tests can redirect subsystem output to `tmp_path` instead of mutating `cad/<subsystem>/` (round-2 mechanical review's intermediate-product rule). The new `tests/test_section_walker_real_docs.py::test_cad_pipeline_out_dir_flag_isolates_writes` asserts that running the pipeline with `--out-dir` leaves `cad/end_effector/` file mtimes unchanged.

### Adjacent improvements shipped in v2.9.0

- **`fix(codegen)`** — `step_import` path resolver now handles absolute paths for shared-cache hits (previously unconditionally wrapped with `os.path.join(_here, "..", "..", step_path)` which broke on absolute cache paths).
- **`feat(parts_resolver)`** — new `keyword_contains` matcher searches both `name_cn` and `material` columns for any of the provided keywords. Useful for vendor part lookups where the model name may appear in either column.
- **`chore(pipeline)`** — `cad_spec_defaults.py` added to the subsystem tool-deploy list so `draw_three_view.save()` can lazy-import its surface roughness and part-no helper tables at runtime. `_run_subprocess` gains `warn_exit_codes` parameter so callers can mark specific exit codes as "completed with warnings" (used by `gen_parts.py` where exit=2 means scaffolds were emitted with TODO markers — valid scaffolds, just unfinalized).
- **`fix(render)`** — `_get_bounding_sphere` in `src/cad_spec_gen/render_3d.py` now uses the axis-aligned bounding box center instead of the vertex centroid. Vertex density on one side of the model no longer biases camera framing.

---

## Breaking changes (internal API)

- **`cad_spec_extractors.extract_part_envelopes` return type**: `dict` → `tuple[dict, WalkerReport]`. All callers updated in the same commit (`cad_spec_gen.py:656` destructures the tuple). External consumers using the Python module would need to update their unpacking — this is documented as a v2.9.0 migration note. The `CAD_SPEC_WALKER_ENABLED=0` feature flag falls back to the legacy code path, but the return type is still a tuple in both paths.

- **`parts_resolver.PartQuery`** gains `spec_envelope_granularity: str = "part_envelope"` field. Default is safe for all existing callers.

- **`codegen/gen_assembly.py::parse_envelopes`** return shape: `dict[pno, (w,d,h)]` → `dict[pno, {"dims": (w,d,h), "granularity": str}]`. Legacy callers in `gen_parts.py` and `gen_params.py` unwrap via `isinstance(env, dict)` check (backward compat).

---

## Test coverage

| Layer | Count | What it validates |
|-------|-------|---|
| Walker unit tests | 73 | Dataclasses, axis canonicalization, envelope regex, section parsing, 4 matching tiers, 2-phase dispatchers, constructor kwargs, walk state machine, stats |
| Cross-subsystem isolation + determinism | 3 | Two walkers with different kwargs in one process; `PYTHONHASHSEED=random` subprocess determinism |
| Synthetic fixtures | 13 | 10 GISBOT path coverage + 3 generality (non-GISBOT chassis, English BOM, axis rotation) |
| Real-doc integration | 3 | End-effector ≥4 matches, lifting-platform ≥2 matches (skip-allowed), `--out-dir` isolation |
| Six-step granularity chain | 1 | End-to-end: walker → parse_envelopes → PartQuery → adapter rejects station_constraint |
| §6.4 rendering | 1 | Legend + new columns + UNMATCHED subsection |
| Downstream codegen threading | 2 | `parse_envelopes` granularity + backward compat |
| Adapter granularity rejection | 2 | station_constraint rejected, part_envelope accepted |
| PartQuery field | 2 | Default + explicit assignment |
| `_find_nearest_assembly` prefix param | 4 | Auto-derive + explicit + empty + name-fallback |
| **Total new tests** | **113** | |
| **Suite state** | **383 passed, 3 skipped, 1 deselected** | up from 270 baseline — zero regressions |

---

## Validation

- Full test suite: **383 passed, 3 skipped, 1 deselected** on the merged main
- **`test_end_effector_docs_match_four_stations`** PASSES on the real 48-part GISBOT end-effector design doc after the walker fix + the `切向宽×径向深×轴向高` axis label additions + comma-prefix fallback
- **`test_cad_pipeline_out_dir_flag_isolates_writes`** PASSES — `cad/end_effector/` file mtimes are unchanged before/after running `cad_pipeline.py spec --out-dir <tmp>`
- **Six-step granularity enforcement** test passes against a synthetic `station_constraint` row in §6.4 — the adapter correctly falls through to `lookup_std_part_dims` instead of sizing a LEMO connector as 60×40×290 mm

---

## Files

**New (15 production + 6 test)**:
- `cad_spec_section_walker.py` (770 lines)
- `adapters/parts/vendor_synthesizer.py` (329 lines)
- `tests/test_section_walker_unit.py` (~760 lines, 73 tests)
- `tests/test_section_walker_fixtures.py` (~170 lines, 13 tests)
- `tests/test_section_walker_real_docs.py` (~90 lines, 3 tests)
- `tests/test_walker_downstream_integration.py` (60 lines, 1 test)
- `tests/test_walker_rendering.py` (~117 lines)
- `tests/fixtures/real_doc_boms/_regenerate.py` + two generated BOM YAMLs + `__init__.py`
- `tests/fixtures/section_walker/01..13_*.md` (13 synthetic fixture docs)

**Modified**:
- `cad_spec_extractors.py` — P2 block replaced by walker invocation + feature flag + `_legacy_p2_regex_block` preserved + `_find_nearest_assembly` parametric prefixes
- `cad_spec_gen.py` — destructure `(part_envelopes, walker_report)` tuple + §6.4 rendering upgraded
- `codegen/gen_assembly.py` — `parse_envelopes` returns dict shape; header-name lookup for `粒度`
- `codegen/gen_std_parts.py` — `_envelope_to_spec_envelope` + new `_envelope_to_granularity`; threads granularity into `PartQuery`
- `codegen/gen_parts.py`, `codegen/gen_params.py` — unwrap new dict shape via comprehension
- `parts_resolver.py` — `PartQuery.spec_envelope_granularity` field + `keyword_contains` matcher rule
- `adapters/parts/jinja_primitive_adapter.py` — rejects `station_constraint` envelopes for per-part sizing
- `adapters/parts/step_pool_adapter.py` — auto-invokes `vendor_synthesizer` on missing STEP file
- `parts_library.default.yaml` — vendor STEP mappings via `keyword_contains`; shared-cache anchor
- `tools/synthesize_demo_step_files.py` — refactored as CLI wrapper around `vendor_synthesizer`
- `cad_pipeline.py` — `--out-dir` flag for spec subcommand; `warn_exit_codes` soft-fail; `cad_spec_defaults.py` in deploy list
- `hatch_build.py` — ships `cad_spec_section_walker.py` in the wheel
- `src/cad_spec_gen/render_3d.py` — bounding sphere uses AABB center (framing fix)
- `docs/pipeline_architecture.md`, `docs/PARTS_LIBRARY.md`, `README.md`, `CHANGELOG.md` — updated
- Version metadata: `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json` → 2.9.0

---

## Migration notes

**If you call `extract_part_envelopes` from external Python code**:
```python
# Before (v2.8.2):
envelopes = extract_part_envelopes(lines, bom_data)

# After (v2.9.0):
envelopes, walker_report = extract_part_envelopes(lines, bom_data)
# walker_report is a WalkerReport dataclass with:
#   .unmatched: tuple[WalkerOutput, ...]
#   .stats: WalkerStats | None
#   .feature_flag_enabled: bool
#   .runtime_error: str | None
```

**If you construct `PartQuery` manually** with a walker-produced envelope, set `spec_envelope_granularity` explicitly:
```python
PartQuery(
    ...,
    spec_envelope=(60.0, 40.0, 290.0),
    spec_envelope_granularity="station_constraint",  # NEW — will be rejected by adapter
)
```
Otherwise the default `"part_envelope"` is used (backward compat).

**If the walker misbehaves** on a subsystem post-deploy:
```bash
CAD_SPEC_WALKER_ENABLED=0 python cad_pipeline.py spec ...
```
falls back to the legacy P2 regex block. Preserved for one release cycle (will be removed in v2.10).

**For non-GISBOT subsystems**, pass constructor kwargs to `SectionWalker`:
```python
walker = SectionWalker(
    lines, bom,
    trigger_terms=("外形尺寸", "总体尺寸"),
    station_patterns=[(r"驱动轮\s*(\d+)", "驱动轮")],
    axis_label_default="长×宽×高",
)
```

---

## Design spec + implementation plan

The full design rationale (including two rounds of adversarial review with 5 reviewer roles) and the 24-task TDD implementation plan are archived under:

- `docs/superpowers/specs/2026-04-12-section-header-walker-design.md` (1100 lines)
- `docs/superpowers/plans/2026-04-12-section-header-walker.md` (3648 lines)

---

**Co-Authored-By:** Claude Opus 4.6 (1M context) <noreply@anthropic.com>
