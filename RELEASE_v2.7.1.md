# Release v2.7.1 — Assembly Positioning Fix

**Date:** 2026-04-09

## Summary

Fixes 4 bugs in `codegen/gen_assembly.py:_resolve_child_offsets()` that caused floating and overlapping components in generated GLB files. All changes are internal to `_resolve_child_offsets()`; function interface `{part_no: (dx,dy,dz)}` is unchanged.

## Bug Fixes

### Fix A: Orphan detection with positioned children

Assemblies whose *children* have explicit §6.2 positions (e.g. GIS-EE-001 法兰总成) were falsely flagged as orphan because the assembly-level row was missing from §6.2. This overrode the stacking direction to `+Z` (upward) instead of the correct `-Z` (downward for hanging workstation modules).

**Root cause:** `is_orphan` only checked the assembly's own `layer_poses` entry, not its children's.

**Fix:** Added `has_positioned_children` check — if any child has explicit Z or `is_origin`, the assembly is not orphan.

### Fix B: z_is_top group sequential stacking

Combined §6.2 entries like "ECX 22L电机+GP22C减速器 | Z=+73mm(向上)" assigned `z=73, z_is_top=True` to *both* the motor and reducer via keyword matching. Both parts were then placed with their bottom face at Z=73, overlapping completely.

Additionally, the z_is_top conversion (`z = z - envelope_height`) silently failed when §6.4 envelopes were missing, leaving parts at the raw top-of-stack Z value.

**Fix:** z_is_top parts are now deferred into `_z_top_deferred` during the main loop, then resolved as groups: parts sharing the same z_top value are stacked sequentially from top downward. Height fallback chain: §6.4 envelope → BOM text dimensions → even split of total height.

### Fix C: Auto-stacking formula for bottom-at-Z=0 parts

The auto-stacking formula used `center_z = cursor ± h/2`, which assumes part geometry is centered on Z. But all parts use `centered=(True,True,False)` — bottom face at Z=0, extending upward. This produced gaps or overlaps between consecutive auto-stacked parts of different heights.

**Fix:** Changed to `offset_z = cursor` (downward: `cursor -= h` then use cursor; upward: use cursor then `cursor += h`). Parts now stack flush with no gaps.

### Fix D: Seed from occupied-extent boundary

Auto-stacked parts seeded from the extremal anchor Z value filtered by stacking direction. For upward stacking, this used `max(anchor bottom Z)` which is the bottom face of the highest part — auto-stacked parts would overlap with that part's body.

**Fix:** Downward stacking seeds from `min(bottom face Z)`. Upward stacking seeds from `max(bottom Z + envelope height)` — the actual top face of the highest part.

## Code Review Follow-up Fixes

- **Negative z_top heights:** `z_top / len(group)` → `abs(z_top) / len(group)` to prevent negative heights when z_top < 0.
- **Redundant file I/O:** Hoisted `parse_envelopes()` and `parse_constraints()` before the assembly loop (was called 3× per assembly). Eliminated redundant `_envelopes_for_constraint` variable.
- **Dead code removal:** Removed unused constants `_STACK_GAP_MM`, `_MAX_STACK_DEPTH_MM`, `_ORPHAN_BASE_Z`.

## Test Changes

### Updated
- `test_integration_end_effector` — assertion 3 updated: checks motor/reducer non-overlap instead of raw Z=73 literal.

### Added (6 new tests)
- `test_orphan_false_when_children_positioned` — Fix A regression guard
- `test_z_is_top_group_no_overlap` — Fix B: two parts sharing z_is_top don't overlap, combined top = z_top, bottom at reference
- `test_z_is_top_single_part` — Fix B: single part with known BOM dimensions
- `test_z_is_top_negative` — Fix B: negative z_top produces correct downward stacking
- `test_auto_stack_adjacent_contact` — Fix C: differently-sized parts are flush (gap = 0)
- `test_seed_does_not_overlap_explicit_parts` — Fix D: auto-stacked part below explicit anchor

## Verification

- 22 gen_assembly tests pass (16 existing + 6 new)
- 8 assembly_coherence tests pass (no regression)
- 6 assembly_validator tests pass (no regression)
- Integration test with GISBOT 末端執行器 (48 parts / 6 assemblies) passes

## Files Changed

| File | Change |
|------|--------|
| `codegen/gen_assembly.py` | 4 fixes in `_resolve_child_offsets()` + perf + cleanup |
| `tests/test_gen_assembly.py` | 1 updated + 6 new tests |
| `skill.json` | v2.7.1, updated cad-codegen description |
| `skill_cad_help.md` | Added v2.7.1 codegen notes + troubleshooting Q&A |
| `pyproject.toml` | v2.7.1 |
| `src/cad_spec_gen/__init__.py` | v2.7.1 (was v2.4.1) |
| `.cad_skill_version.json` | v2.7.1 |
| `src/cad_spec_gen/data/codegen/gen_assembly.py` | Synced from working copy |
| `src/cad_spec_gen/data/skill.json` | Synced from working copy |
