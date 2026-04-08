# Release v2.5.0 — Assembly Positioning Enhancement

**Date:** 2026-04-08

## Highlights

1. **Part-Level Positioning (§6.3)** — Phase 1 now extracts serial stacking chains from → syntax in design documents and computes per-part Z offsets with a direction-aware algorithm. Supports 5 placement modes: axial_stack, radial_extend, side_mount, coaxial, lateral_array. Parts positioned from chains get `confidence: high`.

2. **Part Envelope Extraction (§6.4)** — Collects part envelope dimensions from 5 sources with priority merging: P1 零件级参数表 > P2 叙述文字包络 > P3 BOM材质列 > P4 视觉标识表 > P5 全局参数. 19 parts auto-dimensioned for GISBOT (up from ~6).

3. **Assembly Constraints (§9)** — Negative constraints from source design documents are now classified into assembly exclusions (parts not in this body) and orientation locks. Assemblies marked `exclude` are automatically omitted from generated assembly code.

4. **Enhanced Reviewer (B10-B12)** — Three new assembly validation checks: B10 orphan assemblies (BOM assembly without positioning or exclude), B11 missing envelopes (custom parts without dimensions), B12 low positioning coverage (<50% of sub-assembly parts).

5. **STD_PART_DIMENSIONS Expansion** — Added 12 new standard part entries (linear bearings LM6UU-LM12UU, deep groove bearings 6000ZZ-6201ZZ, NEMA stepper motors). New `MATERIAL_PROPS` dict with 11 material entries (density, color, Ra, material_type).

## Breaking Changes

- CAD_SPEC.md now has 10 sections (was 9). Old `§9 缺失数据报告` is now `§10`.
- New sections §6.3, §6.4, §9 are conditionally rendered (only when data exists). Old docs without these sections remain compatible.

## Code Changes

### cad_spec_extractors.py (+374 lines)
- `_parse_offset()` / `_parse_axis_dir()` — structured parsing of §6.2 offset/axis_dir text
- `extract_part_envelopes()` — 5-source priority envelope collection
- `extract_part_placements()` — serial chain extraction from → syntax + non-axial mode detection
- `_parse_chain_node()`, `_detect_assembly_context()`, `_extract_non_axial_placements()` — helpers
- `_dims_to_envelope()`, `_match_name_to_bom()`, `_find_nearest_assembly()` — shared helpers
- `extract_assembly_pose()` — removed hardcoded BUG-10 exclusion, added `exclude`/`offset_parsed`/`axis_dir_parsed` fields
- `extract_connection_matrix()` — filters excluded layers via `active_layers`
- `extract_render_plan()` — fixed constraint description column parsing bug (约束ID vs 约束描述 disambiguation)

### cad_spec_defaults.py (+141 lines)
- `STD_PART_DIMENSIONS` — 12 new entries (bearings, motors, tanks)
- `MATERIAL_PROPS` — new dict with 11 materials
- `compute_serial_offsets()` — direction-aware Z offset computation with sub-assembly merging
- `_merge_sub_assemblies()`, `_get_node_height()` — helpers

### cad_spec_gen.py (+161 lines)
- `_apply_exclude_markers()` — generic constraint-based assembly exclusion (replaces hardcoded BUG-10)
- `_lookup_part_name()`, `_format_envelope()` — rendering helpers
- `render_spec()` — new §6.3, §6.4, §9 sections; §6.2 with exclude column
- `process_doc()` — orchestrates new extraction → computation → rendering pipeline

### cad_spec_reviewer.py (+87 lines)
- B10: orphan assemblies (CRITICAL)
- B11: missing envelopes (WARNING)
- B12: low positioning coverage (WARNING)
- Section E: assembly positioning summary in DESIGN_REVIEW.md

### codegen/gen_assembly.py (+93 lines)
- `_parse_excluded_assemblies()` — reads exclude markers from §6.2 (single file read, cached)
- `_parse_part_positions()` — reads §6.3 part-level positions
- `_resolve_child_offsets()` — consumes §6.3 positions as highest priority, falls back to auto-stacking

## Design Documentation

- `docs/assembly_positioning_enhancement_plan.md` — 1142-line design document, 4 rounds of multi-role review
- `docs/superpowers/plans/2026-04-08-assembly-positioning-enhancement.md` — implementation plan

## Verification

Tested end-to-end with GISBOT 末端执行机构 (48 parts / 6 assemblies):
- 6 parts with high-confidence serial chain positions
- 19 parts with envelope dimensions
- GIS-EE-006 correctly excluded (was floating at Z=120+)
- Section numbering 1-10 sequential, no conflicts
- Backward compatible: lifting_platform subsystem output unchanged
