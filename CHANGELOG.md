# Changelog

All notable changes to this project are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For releases prior to v2.8.0, see the per-version `RELEASE_v*.md` files at the repository root.

---

## [2.9.0] — 2026-04-11

**Theme:** Section-header walker + granularity enforcement + vendor STEP auto-synthesizer.

See [`RELEASE_v2.9.0.md`](RELEASE_v2.9.0.md) for the full release notes. Summary:

### Added
- **`cad_spec_section_walker.py`** (~770 lines) — stateful Markdown walker that attributes `模块包络尺寸` envelope markers to BOM assemblies via 4-tier hybrid matching: Tier 0 (`_find_nearest_assembly` regression guard) / Tier 1 (structured pattern — `工位N`, `第N级`, `模块N`) / Tier 2 (dual-path CJK char + ASCII word subsequence) / Tier 3 (CJK bigram + ASCII word Jaccard similarity). Two-phase dispatch: `_match_header` at header-push time, `_match_context` at envelope-emit time with a 500-char window. Per-instance regex compilation — no module-level state. Subsystem configurable via `trigger_terms` / `station_patterns` / `axis_label_default` / `bom_pno_prefixes` constructor kwargs.
- **Six-step granularity enforcement chain**: `WalkerOutput.granularity` → `extract_part_envelopes` dict → `§6.4` `粒度` column → `parse_envelopes` header-name lookup → `PartQuery.spec_envelope_granularity` → `JinjaPrimitiveAdapter` REJECTS `station_constraint` envelopes for per-part sizing. Guarded by `tests/test_walker_downstream_integration.py::test_station_constraint_not_used_as_part_size`.
- **`adapters/parts/vendor_synthesizer.py`** (329 lines) — factory registry that builds dimensionally-accurate parametric stand-ins for vendor parts (Maxon GP22C, LEMO FGG, ATI Nano17). `StepPoolAdapter` auto-invokes the synthesizer on missing STEP files, warming `~/.cad-spec-gen/step_cache/` so fresh projects with only a design doc route vendor BOM rows to real geometry without hand-crafted YAML.
- **`parts_resolver.keyword_contains` matcher** — substring match across BOTH `name_cn` and `material` columns. Default `parts_library.default.yaml` uses this to cover project-specific vendor-name placement variations.
- **`cad_pipeline.py spec --out-dir <path>`** — redirect subsystem output to a custom directory so tests can run the full pipeline against `tmp_path` without mutating `cad/<subsystem>/`.
- **113 new tests** across 6 new test files + 2 existing file extensions: unit (73), fixtures (13), cross-subsystem isolation + determinism (3), real-doc integration (3), six-step enforcement (1), rendering (1), plus adapter/resolver/codegen extensions.

### Changed
- **`cad_spec_extractors.extract_part_envelopes` return type**: `dict` → `tuple[dict, WalkerReport]`. `WalkerReport` carries `unmatched`, `stats`, and `feature_flag_enabled`. `cad_spec_gen.py:656` updated to destructure.
- **`cad_spec_extractors.py` P2 block** replaced by walker invocation. Legacy regex block preserved behind `CAD_SPEC_WALKER_ENABLED=0` feature flag as `_legacy_p2_regex_block` helper (will be removed in v2.10).
- **`codegen/gen_assembly.py::parse_envelopes`** return shape: `dict[pno, (w,d,h)]` → `dict[pno, {"dims": (w,d,h), "granularity": str}]`. Positional `cells[3]` dims lookup unchanged; granularity read by header name with `"part_envelope"` default for legacy §6.4 tables. `codegen/gen_parts.py` and `codegen/gen_params.py` legacy callers unwrap via `isinstance(env, dict)` check for backward compat.
- **`parts_resolver.PartQuery`** gains `spec_envelope_granularity: str = "part_envelope"` field. Default safe for all legacy callers.
- **`adapters/parts/jinja_primitive_adapter._resolve_dims_from_spec_envelope_or_lookup`** REJECTS envelopes whose granularity is not `"part_envelope"`, falling through to `lookup_std_part_dims`.
- **`cad_spec_gen.py §6.4` rendering** — imports legend constants from the walker module (`TIER_LEGEND_MD`, `CONFIDENCE_LEGEND_MD`, `GRANULARITY_LEGEND_MD`, `CONFIDENCE_VERIFY_THRESHOLD`, `UNMATCHED_SUGGESTIONS`). First 5 columns preserved (positional compat with `parse_envelopes`); new audit columns appended: `| 轴向标签 | 置信度 | 粒度 | 理由 | 备注`. Confidence <0.75 rendered as `**0.62 VERIFY**`. New `§6.4.1 未匹配的包络` subsection with reason-driven suggestion templates.
- **`cad_spec_extractors._find_nearest_assembly`** parametrized with `bom_pno_prefixes` kwarg. Auto-derives from BOM via `pno.rsplit('-', 1)[0]` when not supplied, so Tier 0 regression guard generalizes beyond `GIS-EE-NNN` to arbitrary `XYZ-ABC-NNN` subsystems.
- **`hatch_build._PIPELINE_TOOLS`** ships `cad_spec_section_walker.py` in the wheel.
- **`tools/synthesize_demo_step_files.py`** refactored as a thin CLI wrapper around `vendor_synthesizer.py`.

### Fixed
- **GISBOT end-effector envelope attribution** — the walker correctly attributes all 4 station envelopes in the real `04-末端执行机构设计.md` document (previously returned zero). Validated by `tests/test_section_walker_real_docs.py::test_end_effector_docs_match_four_stations`.
- **`codegen/gen_std_parts.py` `step_import` path resolver** now handles absolute paths for shared-cache STEP hits. Previously unconditionally wrapped the path with `os.path.join(_here, "..", "..", step_path)` which broke on absolute cache paths.
- **`src/cad_spec_gen/render_3d.py _get_bounding_sphere`** now uses axis-aligned bounding box center instead of the vertex centroid. Vertex density on one side of the model (fine curved surfaces) no longer biases the camera framing. The radius is the half-diagonal — a tight upper bound that guarantees the sphere encloses all geometry.
- **`cad_pipeline.py` `_run_subprocess`** gains `warn_exit_codes` parameter so callers can mark specific exit codes as "completed with warnings" rather than hard failures. Used by `gen_parts.py` where exit=2 means scaffolds were emitted with TODO markers (valid scaffolds, just unfinalized).
- **`cad_pipeline.py` `_deploy_tool_modules`** adds `cad_spec_defaults.py` to the deployed tool list so `draw_three_view.save()` can lazy-import its surface roughness and part-no helper tables at runtime.

### Validation
- **Tests: 383 passed, 3 skipped, 1 deselected** (up from 270 baseline; +113 new tests, 0 regressions)
- **Real-doc integration**: end_effector 4/4 station envelopes matched via Tier 1; lifting_platform skipped (documented known limitation — sparse data); `--out-dir` flag preserves `cad/end_effector/` mtimes across a full pipeline run
- **Determinism**: walker output is byte-identical under `PYTHONHASHSEED=random` (subprocess test validates stable `(-score, pno)` tie-break sort keys in Tier 2/3)
- **Cross-subsystem isolation**: two `SectionWalker` instances with different `trigger_terms` in one process produce independent output and have distinct compiled regexes
- **Backwards compatibility**: feature flag `CAD_SPEC_WALKER_ENABLED=0` falls back to the legacy P2 regex block without requiring a code revert

### Migration notes
See [`RELEASE_v2.9.0.md`](RELEASE_v2.9.0.md) § "Migration notes" for the `extract_part_envelopes` return-type change, `PartQuery` constructor update for manual walker-envelope consumers, the rollback feature flag, and non-GISBOT subsystem kwargs.

### Files
- New: `cad_spec_section_walker.py`, `adapters/parts/vendor_synthesizer.py`, `RELEASE_v2.9.0.md`, 6 new test files, 13 synthetic fixtures, 2 BOM YAML fixtures + regenerator
- Modified: `cad_spec_extractors.py`, `cad_spec_gen.py`, `codegen/gen_assembly.py`, `codegen/gen_std_parts.py`, `codegen/gen_parts.py`, `codegen/gen_params.py`, `parts_resolver.py`, `adapters/parts/jinja_primitive_adapter.py`, `adapters/parts/step_pool_adapter.py`, `parts_library.default.yaml`, `tools/synthesize_demo_step_files.py`, `cad_pipeline.py`, `hatch_build.py`, `src/cad_spec_gen/render_3d.py`, `docs/pipeline_architecture.md`, `docs/PARTS_LIBRARY.md`, `README.md`
- Version metadata: `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`

---

## [2.8.2] — 2026-04-10

**Theme:** Flange visual fidelity + GLB per-part bbox correctness + Phase B vendor STEP coverage expansion.

### Added
- **`tools/synthesize_demo_step_files.py`** — generates dimensionally accurate parametric stand-in STEP files for vendor parts that the project doesn't have real STEP downloads for. Ships three demo parts:
  - Maxon GP22C 53:1 planetary gearhead (Φ24 × 48 mm + Φ6 × 12 mm output)
  - LEMO FGG.0B.307 push-pull plug (Φ8.6 × 37 mm + hex collet + cable tail)
  - ATI Nano17 6-axis force/torque sensor (Φ17 × 14.5 mm + cable tab)
  Documentation links to the official vendor STEP download pages so users can swap in real files.
- **`codegen/consolidate_glb.py`** — post-export GLB merger that collapses CadQuery's per-face mesh split back into one mesh per part. Groups sibling Mesh nodes by `_<digit>` suffix prefix and concatenates them into a single Trimesh under the canonical part name. Gracefully no-ops when `trimesh` is not installed (the helper handles the import probe internally).
- **9 new tests** in `tests/test_consolidate_glb.py` across three layers: prefix grouping logic (4), trimesh availability gating (2), full round-trip on a 2-part fixture (3 — gated by `@pytest.mark.skipif`).
- **Auto-invocation** of the GLB consolidator from `cad_pipeline.py build` between `build_all.py` completion and DXF rendering. Logs `[consolidate_glb] N components → M consolidated parts` so the user can see it run.
- **GISBOT `parts_library.yaml`** updated with 7 new exact-part_no STEP routes covering the GP22C reducer, ATI Nano17 sensor, and 5 LEMO connector instances (the same model is used in 5 different cable harnesses).

### Changed
- **`templates/part_module.py.j2` (`disc_arms` block)** — arm boxes now extend 2 mm INSIDE the disc cylinder edge (`_arm_overlap`) instead of being tangent to it. Without this overlap, OCCT's `union()` of arm + disc was returning a `Compound([disc, arm])` of disjoint Solids rather than a single fused Solid (because the tangent contact has zero volume). The visible tip of the arm is unchanged.
- **`templates/assembly.py.j2`** — docstring update only; the GLB consolidator call lives in `cad_pipeline.py` (cleaner pipeline-vs-generated-code separation).
- **`cad_pipeline.py`** — `cmd_build` now runs the consolidator on all `*_assembly.glb` files in `DEFAULT_OUTPUT` after `build_all.py` succeeds. The step is wrapped in `try/except ImportError` so projects without `trimesh` continue silently.

### Fixed
- **Multi-solid bug in `disc_arms` template**: `make_ee_001_01()` was returning a `cq.Workplane` whose `.val()` was a Compound with **5 disconnected Solids** because the 4 arm boxes were tangent to the disc cylinder edge (zero-volume overlap). After the `_arm_overlap = 2 mm` fix, `.Solids()` returns 1 fused Solid. Verification on the GISBOT flange:
  - Before: `.Solids() = 5`, `.Faces() = 51`, single fused solid: NO
  - After: `.Solids() = 1`, `.Faces() = 35`, single fused solid: YES
  - bbox unchanged (171×171×25), volume unchanged (310 cm³)
- **`EE-001-01` GLB parent component bbox**: was a degenerate `6 × 0 × 8 mm` representing one tiny face. After the multi-solid fix + the consolidator post-process, it is now `171 × 171 × 25 mm` with 4536 mesh triangles representing the entire flange. The same fix applies to all 39 BOM parts in the GISBOT end_effector.
- **CadQuery per-face GLB split**: `cq.Assembly.save("file.glb", "GLTF")` walks each part's OCCT topology and emits one Mesh node per Face — a 100-face part becomes 100 sibling glTF nodes. This is hard-coded behavior in OCCT's `RWGltf_CafWriter` (no flag to suppress it). The new `consolidate_glb.py` post-process collapses sibling components back into per-part meshes, taking GISBOT from 321 components down to 39.

### Phase B coverage impact

GISBOT end_effector library coverage went from **2.9% → 23.5%** (1 → 8 STEP routes), an 8x improvement on the same BOM. The 26 remaining `jinja_primitive` parts are vendor-specific items that bd_warehouse genuinely cannot model (sensors, pumps, seals, custom gear sets) — the new coverage report makes it clear which ones could be upgraded by adding STEP files.

### Validation
- Tests: **169 passed** (was 160 in v2.8.1 — +9 new consolidator tests, 0 regressions)
- GISBOT end_effector pipeline: codegen + build + DXF render + assembly validation all pass
- ASSEMBLY_REPORT: `1 WARNING` (the pre-existing 002-04 5 mm gap), F4 max_extent=402 mm, F5=86.7% — identical to v2.8.1
- Build log shows `[consolidate_glb] EE-000_assembly.glb: 321 components → 39 consolidated parts`

### Files
- New: `codegen/consolidate_glb.py`, `tests/test_consolidate_glb.py`, `tools/synthesize_demo_step_files.py`
- Modified: `templates/part_module.py.j2`, `templates/assembly.py.j2`, `cad_pipeline.py`, `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`, `CHANGELOG.md`

---

## [2.8.1] — 2026-04-09

**Theme:** Registry inheritance + coverage report — close the parts library "user can't tell what's happening" loop.

### Added
- **`extends: default`** in `parts_library.yaml`. Project YAML can now inherit from the skill-shipped `parts_library.default.yaml` instead of completely replacing it. Project mappings are **prepended** to default mappings (project rules win first-hit-wins, default rules act as fallback for parts the project doesn't explicitly cover). Project top-level keys (`step_pool`, `bd_warehouse`, `partcad`, `version`) override default top-level keys shallowly. Unknown `extends:` values are logged as warnings and the project YAML is loaded standalone.
- **Resolver coverage report** in `gen_std_parts.py`. Replaces the previous one-line summary with a per-adapter table showing which specific parts each adapter handled, plus an aggregate row and a hint footer pointing at `docs/PARTS_LIBRARY.md` for upgrading fallback parts. Format is plain ASCII (one box-drawing dash) so it renders correctly on every CI runner including Windows GBK consoles.
- New `PartsResolver.coverage_report()` and `PartsResolver.decisions_by_adapter()` methods.
- 13 new tests in `tests/test_parts_resolver.py`: 6 for `extends: default` merge semantics (prepend ordering, top-level override, drops `extends` key from result, unknown value graceful fallback, kill switch, no-extends backwards compat) + 7 for coverage report (empty state, grouping, jinja-last ordering, truncation of long lists, conditional hint footer, ASCII-only output, decisions_by_adapter shape).

### Changed
- `parts_resolver.load_registry()` rewritten to handle the inheritance step. The legacy "first-file-wins" search path is preserved exactly when `extends:` is absent — projects without `extends:` continue to behave like v2.8.0.
- `codegen/gen_std_parts.py` end-of-run output: replaces `[gen_std_parts] resolver decisions: a=N, b=M` with the multi-line coverage report.
- `D:/Work/cad-tests/GISBOT/parts_library.yaml` migrated to `extends: default`. The previous hardcoded MR105ZZ → bd_warehouse `M4-9-2.5` (Φ4×Φ9×2.5) override has been removed — it was wrong (MR105ZZ is Φ5×Φ10×4 and bd_warehouse 0.2.0 has no exact equivalent). The bearing now correctly falls through to `jinja_primitive` with the right Φ10×4 dimensions, and the file documents why with an inline comment.
- `docs/PARTS_LIBRARY.md` documents the new inheritance pattern, the coverage report format, and a troubleshooting section explaining the three common reasons parts end up in `jinja_primitive` (bd_warehouse category not covered, miniature/non-ISO size, name keywords don't match).

### Fixed
- **GISBOT MR105ZZ misclassification**: the previous v2.8.0 GISBOT yaml hardcoded the bearing to `SingleRowDeepGrooveBallBearing(M4-9-2.5)` which is bd_warehouse's 618/4 (Φ4×Φ9×2.5) — wrong inner, outer, and width. The bearing now uses `jinja_primitive` with correct Φ10 OD × 4 mm width from the BOM material column.
- **Sparse-yaml trap**: a project that wrote a 3-rule `parts_library.yaml` previously **completely replaced** the default registry, silently disabling the category-driven `bearing → bd_warehouse` / `fastener → bd_warehouse` rules. With `extends: default` projects can keep their YAML sparse without losing default coverage. The trap is documented in `docs/PARTS_LIBRARY.md`.

### Compatibility
- **Backwards compatible.** Projects without `extends:` in their `parts_library.yaml` continue to use the legacy first-file-wins behavior. The `CAD_PARTS_LIBRARY_DISABLE=1` kill switch still short-circuits before any YAML is parsed.
- **No new pipeline intermediate files.** Coverage report is stdout-only.
- **Test suite**: 160 passed, 0 skipped (was 145 in v2.8.0; +13 new + 2 previously-skipped optional `bd_warehouse` tests now passing under `PYTHONUTF8=1`).

### Validation
- Full `tests/` suite: 160 passed
- GISBOT end_effector pipeline (Phase 1 spec → Phase 2 codegen → Phase 3 build): all phases pass, ASSEMBLY_REPORT identical to v2.8.0 (1 WARNING for the pre-existing 002-04 5 mm gap edge case, F4 max_extent=402 mm, F5=86.7 % completeness)
- Resolver coverage report on GISBOT correctly shows `step_pool=1, jinja_primitive=33` with the hint footer

---

## [2.8.0] — 2026-04-09

**Theme:** Parts library system + assembly coherence consolidation.

Full notes: [`RELEASE_v2.8.0.md`](RELEASE_v2.8.0.md)

### Added
- **Parts library system** (Phase A + B + C) — adapter-based resolver dispatching purchased BOM rows to one of:
  - `bd_warehouse` (parametric bearings, fasteners, threaded parts) via `BdWarehouseAdapter`
  - Local STEP file pool via `StepPoolAdapter`
  - `partcad` package manager via `PartCADAdapter` (opt-in)
  - `JinjaPrimitiveAdapter` (terminal byte-identical fallback)
- New `parts_resolver.py` core: `PartQuery`, `ResolveResult`, `PartsResolver`, registry loader, `bd_to_cq()` helper
- New `parts_library.yaml` registry format (project-local, optional) with ordered mapping rules: exact `part_no`, `part_no_glob`, `category` + `name_contains` / `material_contains` keywords
- New `catalogs/bd_warehouse_catalog.yaml` — 76 ISO bearing designations across 5 classes + 7 fastener classes, extracted from `bd_warehouse` 0.2.0 CSVs
- New `parts_library.default.yaml` — skill-shipped tiered default registry
- New optional extras in `pyproject.toml`: `parts_library`, `parts_library_bd`, `parts_library_pc`
- New §6.4 source tag namespace `P7:STEP` / `P7:BW` / `P7:PC` for parts-library-derived envelopes (with `P7:*(override_P5)` / `P7:*(override_P6)` variants)
- New P5 (chain_span) and P6 (`_guess_geometry`) envelope backfill loops in `cad_spec_gen.py`
- First CI workflow `.github/workflows/tests.yml` — Linux + Windows × Python 3.10/3.11/3.12 matrix + a `regression` job that enforces byte-identical legacy output via `CAD_PARTS_LIBRARY_DISABLE=1`
- Upstream monitor `tools/check_bd_warehouse_upstream.py` for gumyr/bd_warehouse#75
- New documentation `docs/PARTS_LIBRARY.md` (architecture, mapping vocabulary, kill switches, troubleshooting)
- New tests: `tests/test_parts_resolver.py` (24), `tests/test_parts_adapters.py` (22 + 2 optional live)
- New env var kill switch `CAD_PARTS_LIBRARY_DISABLE=1`
- New CLI hint: `--parts-library PATH` propagated through `cad_pipeline.py`

### Changed
- `codegen/gen_std_parts.py` — `_GENERATORS` dispatch removed, `for p in parts:` delegates to `resolver.resolve()`. Public function signature unchanged. Three generated body forms (`codegen` / `step_import` / `python_import`) all preserve the `make_*() → cq.Workplane` zero-arg contract.
- Generated `std_*.py` files are self-contained — `_bd_to_cq()` helper is inlined per file (not imported), so they work without skill root on `sys.path`.
- `templates/part_module.py.j2` + `gen_parts._guess_geometry()` — flange `disc_arms` template rewritten: arms now extend outward from the disc edge with R=65 mm mounting platforms; renders as a recognizable 4-arm hub instead of a plain disc.
- `BdWarehouseAdapter._auto_extract_size_from_text()` — rewrote to use longest-key substring matching against `iso_designation_map` first (handles `NU2204` / `7202B` / `623-2Z`), then falls back to digit-only `iso_bearing` regex. Fastener path also matches bare `M\d+` for washers/nuts written without an explicit length. Routing smoke test: 2/10 → 10/10 hits.
- `parts_library.default.yaml` — tiered class selection: specific bearing classes first (cylindrical / tapered / angular / capped), generic deep-groove last; specific fastener head types first, `HexHeadScrew` / `HexNut` / `PlainWasher` last.
- `cad_spec_extractors._match_name_to_bom()` — added `assembly_pno` scoping parameter to prevent cross-assembly name leak; 2-char prefix matching is disabled when unscoped.
- `cad_spec_extractors.parse_assembly_pose()` — §6.2 assy regex now accepts optional 4-segment `part_no` like `(GIS-EE-001-08)`, stripping back to the parent prefix; layer parsing terminates on any `### ` subsection.
- `cad_spec_extractors.compute_serial_offsets()` — connection-only chain nodes (e.g. `[4×M3螺栓]`) no longer advance the cursor; multi-node sub-chains accumulate top/bottom per pno across the chain and emit a single span result.
- `gen_assembly._resolve_child_offsets()` — auto-stack respects container envelope bounds (wraps cursor at the largest envelope); high-confidence §6.3 entries bypass the outlier guard; §6.2 author Z values take priority over §9.2 contact constraints; disc-spring washers snap to the nearest already-positioned part in the same assembly.
- `gen_assembly._STD_PART_CATEGORIES` — added `"other"` so 阻尼垫 / 配重块 / 刮涂头 etc. are no longer dropped at assembly time.
- `JinjaPrimitiveAdapter` — `"other"` removed from `_SKIP_CATEGORIES`, new `_gen_generic()` block emits a default box when dims are missing.
- `cad_spec_gen.py` P7 backfill — uses `cad_paths.PROJECT_ROOT` for `parts_library.yaml` lookup (was incorrectly using design doc's grandparent).
- `tests/test_prompt_builder.py` — rewritten from scratch against the current `enhance_prompt.py` API (10 scenarios). Old tests targeted deleted `prompt_builder.py` symbols.
- Skill metadata updated: `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`, `src/cad_spec_gen/__init__.py`, `pyproject.toml` → 2.8.0.

### Fixed
1. Connection-only chain nodes added a phantom 20 mm cursor advance (`compute_serial_offsets()`)
2. Cross-assembly BOM name matching leaked across stations (`_match_name_to_bom()`)
3. §6.2 assy regex rejected 4-segment `part_no`s (`parse_assembly_pose()`)
4. `parse_assembly_pose` did not terminate §6.2 layer parsing on `### ` subsections
5. Multi-node sub-chain spans were overwritten instead of accumulated
6. §6.4 envelope backfill missing for chain spans and `_guess_geometry()` results
7. Auto-stack ignored container envelope bounds, causing 300+ mm cumulative drops below station housings
8. §6.3 high-confidence entries were rejected by the §6.4 outlier guard when envelope coverage was low
9. §9.2 auto-derived contact constraints overrode author-provided §6.2 Z values
10. Disc-spring washers were stacked far below their host PEEK ring (no fastener-accessory snap)
11. `"other"`-category parts (阻尼垫 / 配重块 / 刮涂头) produced no geometry, breaking F5 completeness
12. `_STD_PART_CATEGORIES` in `gen_assembly.py` was missing `"other"`
13. P7 envelope backfill used the wrong project root for `parts_library.yaml` lookup
14. `BdWarehouseAdapter` size extraction missed `NU2204` / `7202B` / `623-2Z` (suffix-stripping regex)
15. Generated `std_*.py` could not import `_bd_to_cq` from `parts_resolver` at build time on machines without the skill on `sys.path` (helper now inlined)
16. Missing `import os` in `cad_spec_gen.py` after the P6 backfill addition

### Safety guarantees
- `make_*() → cq.Workplane` contract unchanged
- `CAD_SPEC.md` schema unchanged
- No new pipeline intermediate files
- Byte-identical regression: `CAD_PARTS_LIBRARY_DISABLE=1` or absent `parts_library.yaml` produces 0-diff `gen_std_parts.py` output vs v2.7.1
- `bd_warehouse` and `partcad` are truly optional — lazy imports, graceful fallback
- P1..P4 envelope source tiers (author-provided) are never overridden by P7

### Known limitations
- `bd_warehouse` Windows CJK locales hit `UnicodeDecodeError` on CSV read. Workaround: `PYTHONUTF8=1` (already in CI). Upstream fix: gumyr/bd_warehouse#75.
- GISBOT 002-04 刮涂头 has a 5 mm pre-existing F1 gap; accepted as-is.

### Validation
- Tests: 135 passed, 2 skipped (optional live `bd_warehouse`)
- Byte-identical regression: 0 diff with kill switch
- End-to-end on `04-末端执行机构设计.md`: all 4 phases pass, both `step_pool` and `bd_warehouse` paths exercised, 7 PNG views rendered.

---

## [2.7.1] — 2026-04-09

Assembly positioning fix release. 4 bugs in `gen_assembly._resolve_child_offsets()` causing floating / overlapping components in GLB output. See [`RELEASE_v2.7.1.md`](RELEASE_v2.7.1.md).

## [2.7.0] — 2026-04-09

Assembly constraint declaration system: §9.2 auto-derived from connection matrix, fit codes (H7/m6) extraction, GATE-3.5 assembly validator (F1–F5 sanity checks).

## [2.5.0] — 2026-04-08

§6.3 per-part positioning, §6.4 envelope dimensions, §9.1 assembly exclusions consumed by `gen_assembly.py`. See [`RELEASE_v2.5.0.md`](RELEASE_v2.5.0.md).

## [2.4.1] — 2026-04-07

Hotfixes for v2.4.0 (review pipeline, bom_parser).

## [2.4.0] — 2026-04-07

Review pipeline: design review → DESIGN_REVIEW.md → user iterate / `--auto-fill` / `--proceed`.

## [2.3.0] — 2026-04-07

View-aware AI enhancement materials, MATERIAL_PRESETS unification.

## [2.2.2] — 2026-04-03

Cable / harness length capping, std-part dimension lookup via parameter table.

## [2.2.1] — 2026-04-03

Auto-annotation in HLR sheets, near-real flange / bracket geometry inference, per-part offset positioning. See [`RELEASE_v2.1.2.md`](RELEASE_v2.1.2.md) (release note kept under the prior numbering).

## [2.1.1] — 2026-04-02

Hotfix release.

## [2.1.0] — 2026-03-31

Multi-view consistency, viewpoint lock, image role separation. See [`RELEASE_v2.1.0.md`](RELEASE_v2.1.0.md), [`RELEASE_v2.1.1.md`](RELEASE_v2.1.1.md).

## [2.0.0] — 2026-03-30

Major release: 6-phase unified pipeline orchestrator (`cad_pipeline.py`).

## [1.9.0] — 2026-03-29

Pre-2.0 stabilization.

## Earlier releases

See git history (`git log v1.7.0..v1.9.0`) for v1.7.x – v1.9.0.

[2.8.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.8.0
[2.7.1]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.7.1
[2.7.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.7.0
[2.5.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.5.0
[2.4.1]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.4.1
[2.4.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.4.0
[2.3.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.3.0
[2.2.2]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.2.2
[2.2.1]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.2.1
[2.1.1]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.1.1
[2.1.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.1.0
[2.0.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.0.0
[1.9.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v1.9.0
