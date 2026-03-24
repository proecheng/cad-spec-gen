# /cad-spec — Generate CAD Spec from Design Document

User input: $ARGUMENTS

## Instructions

Run the CAD Spec generator to extract structured parameters/tolerances/BOM data from design documents. This is **Phase 1** of the 6-stage pipeline.

### Routing Rules

1. **No arguments** → Show usage:
   ```
   Usage: /cad-spec <design_doc.md> [--force] [--review] [--review-only] [--auto-fill]

   Examples:
     /cad-spec docs/design/04-end-effector-design.md
     /cad-spec docs/design/04-end-effector-design.md --review
     /cad-spec docs/design/05-electrical-system.md --force
     /cad-spec --all --review

   Or via the unified pipeline:
     python cad_pipeline.py spec --design-doc docs/design/04-*.md --auto-fill
   ```

2. **`--all`** → Process all subsystems:
   ```bash
   python cad_spec_gen.py --all --config config/gisbot.json
   ```

3. **File path** → Process single document:
   ```bash
   python cad_spec_gen.py $ARGUMENTS --config config/gisbot.json
   ```

4. **`--review` or `--review-only`** → Design review workflow:
   ```bash
   # Review only (recommended for first use)
   python cad_spec_gen.py <doc.md> --config config/gisbot.json --review-only --force

   # Review + generate
   python cad_spec_gen.py <doc.md> --config config/gisbot.json --review --force
   ```

### Review Workflow (when using --review or --review-only)

1. After extraction, automatically run design review engine (Mechanical/Assembly/Material/Completeness)
2. Read the generated `DESIGN_REVIEW.md` and present review summary to user:
   - A. Mechanical review results (cantilever stress, bolt shear, etc.)
   - B. Assembly review results (dimension chains, envelope interference, etc.)
   - C. Material review results (galvanic corrosion, temperature margins, etc.)
   - D. Missing data (CRITICAL/WARNING/INFO)
3. Offer the user three options:
   - **"Continue Review"** → Discuss WARNING/CRITICAL items one by one; user may adjust parameters, review notes recorded in CAD_SPEC.md
   - **"Auto-Fill"** → Automatically fill in computable missing data (bolt torques, units, surface roughness) with defaults, then generate CAD_SPEC.md
     ```bash
     python cad_spec_gen.py <doc.md> --config config/gisbot.json --review --auto-fill
     ```
   - **"Next Step"** → Generate CAD_SPEC.md with existing data as-is (no gap-filling)
4. After user confirms "Next Step" or "Auto-Fill", run full generation
5. **Important: Never modify the user's design document directly** — all changes are reflected only in CAD_SPEC.md

### Pipeline Checkpoint

`cad_pipeline.py full` automatically checks `DESIGN_REVIEW.json` after SPEC completes:
- **CRITICAL** → Pipeline stops (exit 1), must fix before re-running
- **WARNING** → Pipeline stops (exit 2), use `--auto-fill` or `--force` to continue
- **No issues** → Automatically continues to subsequent stages

### Post-Generation Summary

Read the output CAD_SPEC.md and summarize:
- Number of extracted parameters, fasteners, BOM parts
- Any CRITICAL or WARNING missing data items
- Design review results (if applicable)
- Output file locations

### Next Steps

After CAD_SPEC.md is generated, suggest to user:
- **`/cad-codegen <subsystem>`** → Auto-generate CadQuery scaffold code (Phase 2)
- **`python cad_pipeline.py full`** → Run all 6 pipeline stages in one shot
- **`/mechdesign <subsystem>`** → Manual parametric modeling workflow (for finer geometric control)
