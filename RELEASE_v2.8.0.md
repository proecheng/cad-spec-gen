# Release v2.8.0 — Parts Library System

**Date:** 2026-04-09

## Summary

Introduces an adapter-based **parts library system** that replaces the simplified primitive geometry `gen_std_parts.py` produces for purchased (外购) BOM parts with real parametric / vendor / package-managed CAD geometry. Three backends — **bd_warehouse**, a **local STEP pool**, and **PartCAD** — plus the legacy `jinja_primitive` fallback are dispatched through a single ordered registry. Selection is driven by an optional project-local `parts_library.yaml`; when absent the pipeline is **byte-identical** to v2.7.1.

This release also bundles a long sequence of assembly-coherence fixes uncovered while validating the parts library on the GISBOT end_effector subsystem (13 root causes in `gen_assembly.py` / `cad_spec_extractors.py` / `cad_spec_gen.py`), a flange geometry rewrite, the project's first CI workflow, and an upstream patch to `bd_warehouse` for Windows CJK locales (gumyr/bd_warehouse#75).

## Highlights

- **Parts library system (Phase A + B + C)** — bd_warehouse, STEP pool, PartCAD adapters with first-hit-wins dispatch, lazy imports, kill switch (`CAD_PARTS_LIBRARY_DISABLE=1`)
- **§6.4 P7 envelope backfill** — Phase 1 probes the resolved adapter and writes real dims into `CAD_SPEC.md`, tagged `P7:STEP` / `P7:BW` / `P7:PC`. Phase 2 reads them via the existing §6.4 priority chain — no new pipeline intermediate files
- **13 assembly coherence fixes** — connection-only chain phantom heights, cross-assembly name leak, §6.2 4-segment regex, sub-section terminator, multi-node sub-chain spans, P5/P6/P7 backfill loops, container-bounded auto-stacking, high-confidence outlier bypass, §6.2 vs §9.2 priority, fastener-accessory snap, "other" category geometry, `_STD_PART_CATEGORIES` sync, P7 PROJECT_ROOT lookup
- **Flange geometry rewrite** — `disc_arms` template now extends arms outward from the disc edge, with mounting platforms aligned to the workstation mount circle. Renders as a recognizable 4-arm rotating hub instead of a plain disc
- **CI workflow** — first `.github/workflows/tests.yml`. Linux + Windows × Python 3.10/3.11/3.12 matrix + a separate `regression` job that proves byte-identical legacy output via `CAD_PARTS_LIBRARY_DISABLE=1`
- **bd_warehouse upstream PR** — gumyr/bd_warehouse#75 fixes a Windows GBK `UnicodeDecodeError` on CSV reads. Workaround in CI: `PYTHONUTF8=1` until merge

## Architecture

```
 parts_library.yaml (project-local, optional)
        │
        ▼
 parts_resolver.PartsResolver
        │   resolve(PartQuery) → ResolveResult
        │   probe_dims(PartQuery) → (w,d,h) | None
        ▼
 Adapter ordered dispatch (first hit wins):
        ├─ StepPoolAdapter      (project std_parts/)
        ├─ BdWarehouseAdapter   (lazy import)
        ├─ PartCADAdapter       (lazy import, opt-in)
        └─ JinjaPrimitiveAdapter (terminal fallback)
```

### Two injection points

| Pipeline phase | Hook | Purpose |
|---|---|---|
| Phase 1 spec-gen | `cad_spec_gen.py` (P7 backfill loop after P5/P6) | `resolver.probe_dims()` for purchased BOM rows → §6.4 tagged `P7:<ADAPTER>` |
| Phase 2 codegen | `codegen/gen_std_parts.py` `for p in parts:` | `resolver.resolve()` → emit `make_*()` body in one of three forms |

### Three generated body forms

| `ResolveResult.kind` | Generated body |
|---|---|
| `codegen` | inline jinja `_gen_*` block (legacy fallback, byte-identical) |
| `step_import` | `cq.importers.importStep("std_parts/...").val()` |
| `python_import` | `from bd_warehouse.bearing import ...` or `partcad.get_part_cadquery(...)` |

All three forms preserve the `make_*() → cq.Workplane` zero-arg contract that `assembly.py` consumes.

## Safety guarantees

1. `make_*() → cq.Workplane` contract unchanged
2. CAD_SPEC.md schema unchanged (§6.4 still uses existing source-tag column, just adds `P7:*` tag values)
3. No new pipeline intermediate files
4. **Byte-identical regression**: with `CAD_PARTS_LIBRARY_DISABLE=1` OR no `parts_library.yaml`, `gen_std_parts.py` output is byte-identical to pre-v2.8.0 — enforced by the `regression` CI job
5. `bd_warehouse` and `partcad` are **truly optional** — lazy imports, graceful fallback to `jinja_primitive` when unavailable
6. Generated `std_*.py` files are **self-contained** — `_bd_to_cq()` helper is inlined (not imported from `parts_resolver`) so the generated code works without skill root on `sys.path`
7. P1..P4 envelope source priorities (author-provided) are **never overridden** by P7. Only missing rows or P5/P6 (auto-inferred) accept P7 backfill.

## Source priority (§6.4)

| Tier | Source | P7 override? |
|---|---|---|
| P1 | author-provided in design doc | never |
| P2 | author-provided in BOM material column | never |
| P3 | parameter table | never |
| P4 | connection matrix | never |
| P5 | chain span (auto) | overridden by P7 |
| P6 | guess_geometry (auto) | overridden by P7 |
| P7 | parts_library probe | — |

## Assembly coherence fixes (carried from in-flight v2.7.x work)

| # | Fix | Site |
|---|---|---|
| 1 | Connection-only chain nodes added phantom 20 mm cursor advance | `cad_spec_extractors.compute_serial_offsets()` |
| 2 | Cross-assembly BOM name matching leaked across stations | `cad_spec_extractors._match_name_to_bom()` (added `assembly_pno` scoping) |
| 3 | §6.2 assy regex rejected 4-segment part_nos like `(GIS-EE-001-08)` | `cad_spec_extractors.parse_assembly_pose()` |
| 4 | `parse_assembly_pose` did not terminate §6.2 on `### ` subsections | same |
| 5 | Multi-node sub-chain span tracking overwritten instead of accumulated | `compute_serial_offsets()` |
| 6 | New P5 (chain_span) and P6 (guess_geometry) backfill loops | `cad_spec_gen.py` |
| 7 | Auto-stack container constraint — wrap cursor at container bbox | `gen_assembly._resolve_child_offsets()` |
| 8 | §6.3 confidence=high bypasses outlier guard | `gen_assembly._resolve_child_offsets()` |
| 9 | §6.2 author Z values overridden by §9.2 contact constraints | `gen_assembly._resolve_child_offsets()` |
| 10 | Disc-spring washers stacked far below host part | `gen_assembly._resolve_child_offsets()` |
| 11 | "other" category parts skipped (no geometry, broke F5) | `adapters/parts/jinja_primitive_adapter.py` + `gen_assembly._STD_PART_CATEGORIES` |
| 12 | `_STD_PART_CATEGORIES` missing "other" | same |
| 13 | P7 lookup used wrong project root | `cad_spec_gen.py` (uses `cad_paths.PROJECT_ROOT`) |

## Flange geometry

`templates/part_module.py.j2` + `gen_parts._guess_geometry()`:

- Arms now extend **outward** from the disc edge by `arm_l` (previously inward, hidden by the disc)
- Each arm terminates in a 40×40 mm mounting platform aligned with the R=65 mm workstation mount circle
- Arm cross-section is 8 mm thick (vs 25 mm disc), flush with disc top face
- Central Φ22 mm bore for the reducer output shaft

## bd_warehouse catalog expansion

`catalogs/bd_warehouse_catalog.yaml` extracted from bd_warehouse 0.2.0 CSVs:

| Class | ISO designations |
|---|---|
| `SingleRowDeepGrooveBallBearing` | 31 (618/619/60/62/63 series) |
| `SingleRowCappedDeepGrooveBallBearing` | 19 (-2Z / -2RS variants) |
| `SingleRowAngularContactBallBearing` | 9 (7200 / 7300 series) |
| `SingleRowCylindricalRollerBearing` | 9 (NU2 / NU3 series) |
| `SingleRowTaperedRollerBearing` | 8 (30200 / 30300 series) |
| Fastener classes | 7 (HexHead, SocketHead, HexNut, PlainWasher, CounterSunk, ButtonHead, SetScrew) |

The `BdWarehouseAdapter._auto_extract_size_from_text()` was rewritten to use **longest-key substring matching** against `iso_designation_map` directly, sorted by length DESC so `NU2204` beats `NU220` on overlap. The previous regex stripped suffixes and missed `NU2204`, `7202B`, `623-2Z`. Fastener path now also matches bare `M\d+` for washers/nuts written without an explicit length.

Routing smoke test went from 2/10 to **10/10 hits**.

## CI workflow

- `.github/workflows/tests.yml` — Linux + Windows × Python 3.10/3.11/3.12 matrix
- Windows job sets `PYTHONUTF8=1` to work around `bd_warehouse` UTF-8 bug (remove once gumyr/bd_warehouse#75 merges)
- Separate `regression` job runs with `CAD_PARTS_LIBRARY_DISABLE=1` to enforce byte-identical legacy output
- `tools/check_bd_warehouse_upstream.py` — periodic monitor for the upstream PR

## File manifest

### New files

| Path | Responsibility |
|---|---|
| `parts_resolver.py` | Resolver core: `PartsResolver`, `PartQuery`, `ResolveResult`, registry loader, `bd_to_cq()` |
| `adapters/parts/__init__.py`, `base.py` | Package + `PartsAdapter` ABC |
| `adapters/parts/jinja_primitive_adapter.py` | Legacy `_gen_motor`/`_gen_bearing`/etc moved verbatim |
| `adapters/parts/bd_warehouse_adapter.py` | Phase A — catalog-driven, lazy bd_warehouse import |
| `adapters/parts/step_pool_adapter.py` | Phase B — STEP file resolver + BoundingBox probe + cache |
| `adapters/parts/partcad_adapter.py` | Phase C — opt-in PartCAD bridge |
| `catalogs/bd_warehouse_catalog.yaml` | 76 ISO bearing designations + 7 fastener classes |
| `parts_library.default.yaml` | Skill-shipped default registry (tiered bearing/fastener routing) |
| `tests/test_parts_resolver.py` | 24 dispatch + YAML tests |
| `tests/test_parts_adapters.py` | 22 adapter tests + 2 optional live |
| `docs/PARTS_LIBRARY.md` | Full user documentation (mapping vocab, kill switches, troubleshooting) |
| `tools/check_bd_warehouse_upstream.py` | gh CLI + source inspection monitor for gumyr/bd_warehouse#75 |
| `.github/workflows/tests.yml` | First CI workflow |

### Modified files

| Path | Change |
|---|---|
| `codegen/gen_std_parts.py` | `_GENERATORS` removed, `for p in parts:` delegates to `resolver.resolve()`. Public function signature unchanged. |
| `cad_spec_gen.py` | New P5/P6/P7 envelope backfill loops; `os` import added |
| `cad_spec_extractors.py` | Fixes #1–#5 above |
| `codegen/gen_assembly.py` | Fixes #7–#10, #12 above |
| `templates/part_module.py.j2` + `codegen/gen_parts.py` | Flange `disc_arms` rewrite |
| `pyproject.toml` | New extras: `parts_library`, `parts_library_bd`, `parts_library_pc`. Version → 2.8.0 |
| `tests/test_gen_assembly.py` | Regression tests for fixes #1, #8 |
| `tests/test_prompt_builder.py` | Rewritten against current `enhance_prompt.py` API |
| `skill.json` + `src/cad_spec_gen/data/skill.json` | v2.8.0 |
| `src/cad_spec_gen/__init__.py` | v2.8.0 |
| `.cad_skill_version.json` | v2.8.0 |

### Files explicitly NOT changed

- `templates/assembly.py.j2` — generated assembly stays contract-compatible
- `cad_spec_extractors.parse_envelopes()` priority chain — only the source tag namespace was extended
- `cad_spec_defaults.STD_PART_DIMENSIONS` — kept as `JinjaPrimitiveAdapter` data source
- `bom_parser.py`, `classify_part()` — unchanged
- `codegen/gen_parts.py` custom-part path — unchanged

## Validation

- **Test suite**: 135 passed, 2 skipped (`@pytest.mark.optional` live `bd_warehouse` tests gracefully skip on import failure)
- **Byte-identical regression**: 0 diff with `CAD_PARTS_LIBRARY_DISABLE=1`
- **End-to-end on `04-末端执行机构设计.md`** (GISBOT end_effector):
  - Phase 1 spec → §6.4 contains 1 `P7:STEP` row (GIS-EE-001-05)
  - Phase 2 codegen → `std_ee_001_05.py` is a STEP import; `std_ee_004_11.py` is a `bd_warehouse` import; remaining 9 std parts are byte-identical jinja
  - Phase 3 build → 1 WARNING (002-04 刮涂头 5 mm gap, pre-existing edge case), F4 max_extent = 402 mm, F5 = 86.7 % completeness
  - Phase 4 render → 7 PNG views generated successfully

## Routing smoke test (10/10)

```
✓ 608ZZ          → SingleRowDeepGrooveBallBearing(M8-22-7)
✓ 6200           → SingleRowDeepGrooveBallBearing(M10-30-9)
✓ 624            → SingleRowDeepGrooveBallBearing(M4-13-5)
✓ NU2204         → SingleRowCylindricalRollerBearing(M20-47-18)
✓ 30203          → SingleRowTaperedRollerBearing(M17-40-13.25)
✓ 7202B          → SingleRowAngularContactBallBearing(M15-35-11)
✓ 623-2Z         → SingleRowCappedDeepGrooveBallBearing(M3-10-4)
✓ M3×10 内六角    → SocketHeadCapScrew(M3-0.5)
✓ M5×16 沉头     → CounterSunkScrew(M5-0.8)
✓ M6 平垫圈      → PlainWasher(M6-1.0)
```

## Kill switches

| Switch | Effect |
|---|---|
| Delete `parts_library.yaml` | Library system fully disabled, 100 % legacy output |
| `CAD_PARTS_LIBRARY_DISABLE=1` env var | Same, forced at runtime |
| Omit `bd_warehouse` extra | bd_warehouse adapter reports unavailable, falls through |
| Omit `partcad` extra + `partcad.enabled: false` | PartCAD adapter never imports |
| Git revert `cad9ea9` + `8241c93` | Full rollback (assembly fixes in `097968f` are independent) |

## Known limitations

- **`bd_warehouse` Windows CJK locales**: `UnicodeDecodeError` on CSV read. Workaround: `PYTHONUTF8=1` (already wired into the Windows CI job). Upstream fix: gumyr/bd_warehouse#75 (submitted by @proecheng, awaiting merge). The test harness wraps the import in `_try_import_bd_warehouse_bearing()` to skip gracefully.
- **`002-04` 刮涂头 5 mm gap**: pre-existing F1 WARNING in the GISBOT end_effector. Edge case in the design doc's chain definition; accepted as-is for v2.8.0.

## Upgrade path

Existing projects with no `parts_library.yaml`: **no action required**, behavior is byte-identical.

Projects that want library resolution:

```bash
pip install cad-spec-gen[parts_library]            # YAML loader only
pip install cad-spec-gen[parts_library,parts_library_bd]   # + bd_warehouse
pip install cad-spec-gen[parts_library,parts_library_pc]   # + partcad
```

Then create `<project_root>/parts_library.yaml` from the documentation in `docs/PARTS_LIBRARY.md`. STEP files go in `<project_root>/std_parts/`.

## Files Changed (high-level)

| Category | Count |
|---|---|
| New parts library files | 14 |
| Modified codegen / spec extraction | 7 |
| New / updated tests | 4 |
| Documentation | 2 |
| CI / tooling | 2 |
| Version metadata | 5 |

See the three constituent commits for line-level detail:

- `097968f` — assembly coherence + flange + test modernization
- `cad9ea9` — parts library system (Phase A + B + C)
- `8241c93` — bd_warehouse catalog expansion + CI + upstream monitor
