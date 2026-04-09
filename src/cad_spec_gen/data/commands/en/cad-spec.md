# /cad-spec — Generate CAD Spec from Design Document

User input: $ARGUMENTS

## Instructions

Run the CAD Spec Generator to extract structured parameters, tolerances, and BOM data from design documents. This is **Phase 1** of the 6-stage pipeline.

### Routing Rules

1. **No arguments** → Show usage:
   ```
   Usage: /cad-spec <design_doc.md> [--force] [--review-only] [--auto-fill] [--supplements '{...}']

   Examples:
     /cad-spec docs/design/04-end-effector-design.md
     /cad-spec docs/design/04-end-effector-design.md --review-only
     /cad-spec docs/design/05-electrical-system.md --force
     /cad-spec --all

   Or run via unified pipeline:
     python cad_pipeline.py spec --design-doc docs/design/04-*.md --auto-fill
   ```

2. **`--all`** → Process all subsystems:
   ```bash
   python cad_pipeline.py spec --all --force
   ```

3. **File path** → Process a single document:
   ```bash
   python cad_pipeline.py spec --subsystem <subsystem> --design-doc $ARGUMENTS --force
   ```

4. **`--review-only`** → Agent-driven design review workflow (recommended):
   ```bash
   # Step 1: Generate review report (non-interactive, returns immediately)
   python cad_pipeline.py spec --subsystem <name> --design-doc <doc.md> --review-only

   # Step 2a: After agent discusses items, pass supplement data + auto-fill
   python cad_pipeline.py spec --subsystem <name> --supplements '{"M03": "L0: mounting plate/fixed/M6×4; L1: flange/rotation/interference fit"}' --auto-fill

   # Step 2b: Or auto-fill directly (no supplement data needed)
   python cad_pipeline.py spec --subsystem <name> --auto-fill

   # Step 2c: Or proceed with existing data (skip fill)
   python cad_pipeline.py spec --subsystem <name> --proceed
   ```

### Agent Review Workflow

`cad_pipeline.py spec` uses a non-interactive agent-driven mode, executed in two steps:

**Step 1 — Generate review report** (`--review-only`):
1. Run `cad_spec_gen.py --review-only`, extract data and run the design review engine (mechanics/assembly/materials/completeness)
2. Output `output/<subsystem>/DESIGN_REVIEW.md` + `DESIGN_REVIEW.json`
3. Print review summary (CRITICAL/WARNING/INFO/OK counts + issue items) then **exit immediately (exit 0)**
4. Agent reads `DESIGN_REVIEW.json` and interacts with user item by item per the protocol below

**Step 2 — Item-by-item review dialogue**:

After reading `DESIGN_REVIEW.json`, the agent processes all WARNING/CRITICAL and `auto_fill: "yes"` INFO items per the following protocol, **one item at a time**:

| Item Type | Agent Behavior |
|-----------|----------------|
| `auto_fill: "yes"` | Infer a specific value from the design doc, show the inferred result, ask: confirm / modify / skip |
| `auto_fill: "no"`, inferable from BOM/connection matrix/parameter table | Agent infers independently, shows in plain language, asks: confirm / modify / skip |
| `auto_fill: "no"`, insufficient context (e.g. missing material) | Offer 3–5 candidate options (inferred from part name/category), let user pick a number, type freely, or skip |
| CRITICAL | Inform that the design document must be fixed, explain why, do not add to supplements |

**Processing principles**:
- Describe issues in plain language; do not expose raw technical IDs (M03/D6 etc.) — say "a data field is missing" instead
- Ask only one item at a time; wait for user response before proceeding to the next
- When inferring, prioritize BOM, connection matrix, and parameter table data from the design document
- Skipped items are not written to supplements

**Phase 1 New Extraction Steps** (v2.5.0+):

In addition to basic parameter/BOM/tolerance extraction, Phase 1 now also runs:
- `extract_part_placements()` — serial chain and non-axial mode extraction, generating per-part positioning data
- `extract_part_envelopes()` — multi-source part dimension collection (BOM material column + parameter table + connection matrix)
- `_apply_exclude_markers()` — negative constraint cross-referencing, marking assembly exclusion items
- `compute_serial_offsets()` — computing Z-axis offsets from serial chains

The generated CAD_SPEC.md therefore gains three new sections:
- **§6.3 Per-Part Positioning**: positioning mode (serial/radial/fixed) and confidence for each part
- **§6.4 Part Envelope Dimensions**: aggregated multi-source envelope dimensions per part (L×W×H or Φd×l)
- **§9 Assembly Constraints**: assembly exclusion list from negative constraint table (non-local assemblies)

**Phase 1 Constraint Declaration System** (v2.7.0+):

`extract_assembly_constraints()` auto-derives §9.2 constraint declarations from the connection matrix:
- **contact constraints**: extracts face contact relationships between parts (e.g. `end face contact` → `contact(A, B, face="end")`)
- **stack_on constraints**: derives stacking order from serial chains (e.g. `stack_on(B, A)` means B stacks on top of A)
- **Fit code extraction**: extracts standard fit codes from connection type column (e.g. `transition fit H7/m6` → `fit="H7/m6"`)
- **EN_PARAM English aliases**: auto-generates English parameter name aliases (e.g. `法兰外径` → `FLANGE_OD`)

The generated CAD_SPEC.md §9.2 contains a constraint declaration table consumed by Phase 2 codegen for precise assembly positioning.

**Phase 1 P7 Envelope Backfill** (v2.8.0+):

If `parts_library.yaml` exists at the project root, Phase 1 adds a **P7 backfill loop** after P5/P6: for every purchased BOM row it calls `parts_resolver.PartsResolver.probe_dims()` and writes library-derived dimensions into §6.4. Source tags:

| Tag | Meaning |
|---|---|
| `P7:STEP` | from a project-local STEP file (`std_parts/`) |
| `P7:BW` | from a `bd_warehouse` parametric part |
| `P7:PC` | from a `partcad` package |
| `P7:STEP(override_P5)` | P7 overrode an earlier P5/P6 auto-inferred row |

P1..P4 (author-provided dimensions) are **never** overridden by P7 — only missing §6.4 rows are filled, and P5/P6 auto-inferred rows are replaced. See `docs/PARTS_LIBRARY.md` for details.

**Step 3 — Generate CAD_SPEC.md** (after all items are processed):

```bash
# With user supplement data (supplements as JSON string)
python cad_pipeline.py spec --subsystem <name> --design-doc <doc.md> \
  --supplements '{"M01": "Total weight: 2.5kg", "D6": "Cast iron"}' --auto-fill

# Auto-fill only
python cad_pipeline.py spec --subsystem <name> --design-doc <doc.md> --auto-fill

# Skip all
python cad_pipeline.py spec --subsystem <name> --design-doc <doc.md> --proceed
```

**supplements JSON format**: Keys are `id` fields from `DESIGN_REVIEW.json`; values are confirmed content strings.

**Notes**:
- The entire flow has no `input()` calls; the agent is driven entirely by dialogue + CLI parameters
- The user's design document is never modified directly; all changes are reflected only in CAD_SPEC.md
- CRITICAL issues require the user to fix the design document and re-run `--review-only`

### Post-generation Summary

Read the generated CAD_SPEC.md and summarize:
- Count of extracted parameters, fasteners, and BOM parts
- Any CRITICAL or WARNING missing data items
- Design review results (if any)
- Output file locations

### Next Steps

After CAD_SPEC.md is generated, recommend:
- **`/cad-codegen <subsystem>`** → Auto-generate CadQuery scaffold code (Phase 2)
- **`python cad_pipeline.py full`** → Run all 6 pipeline stages at once
- **`/mechdesign <subsystem>`** → Manual parametric modeling (for finer geometry control)
