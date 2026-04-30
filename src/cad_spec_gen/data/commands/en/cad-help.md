# /cad-help — CAD Hybrid Rendering Pipeline Interactive Help

User input: $ARGUMENTS

## Instructions

Read the skill document `skill_cad_help.md` (project root), then execute based on user input:

### Routing Rules

1. **No arguments** (`$ARGUMENTS` is empty) → Show help panel:
   - Output the "Help Panel" template from the end of skill_cad_help.md
   - List common question examples in 4 groups: Environment & Setup / Config & Validation / Workflow / Status & Troubleshooting

2. **With arguments** → Intent matching + execution:
   - Extract keywords from `$ARGUMENTS` text
   - Match against the "Intent Matching Table" in skill_cad_help.md, select best match
   - Execute the matched intent's "Action Details" (run programs directly when possible, guide step-by-step when needed)
   - If no intent matches, reply "Could not understand your question" and show the help panel

3. **Full pipeline request** (when user asks for drawing/rendering/full pipeline/complete workflow, or requests both 2D + 3D outputs):

   #### Step 0 — Artifact Scan + Phase Overview (must execute first)

   Scan the target subsystem directory, show the user the status of each phase's artifacts, and wait for the user to choose before executing. **Must not skip this step.**

   **Scan logic**:
   ```
   Phase 1  SPEC      → Check if cad/<subsystem>/CAD_SPEC.md exists + mtime
   Phase 2  CODEGEN   → Check if cad/<subsystem>/build_all.py, params.py, assembly.py exist
   Phase 3  BUILD     → Check cad/output/ for subsystem .step/.glb/.png(DXF→PNG) files + mtime
   Phase 4  RENDER    → Check cad/output/renders/ for subsystem V*.png + count + mtime
   Phase 5  ENHANCE   → Check for *_enhanced.* files
   Phase 6  ANNOTATE  → Check for *_labeled_*.png files
   ```

   **Output format** (example):
   ```
   === Lead-screw Lifting Platform (lifting_platform) — Pipeline Status ===

   Phase 1  SPEC       ✅ CAD_SPEC.md (2026-03-29)
   Phase 2  CODEGEN    ✅ build_all.py + params.py + 7 draw_*.py files
   Phase 3  BUILD      ✅ SLP-000_assembly.glb (2026-03-31)
   Phase 4  RENDER     ✅ 7 PNGs (2026-03-31 14:03)
   Phase 5  ENHANCE    ❌ No enhanced images
   Phase 6  ANNOTATE   ❌ No annotated images

   Choose starting point:
     A. Full rebuild from scratch (overwrite all artifacts, start from Phase 1 SPEC)
     B. Resume from Phase 5 ENHANCE (keep existing SPEC/code/GLB/PNG)
     C. Rebuild specific phases only (specify phase numbers, e.g. "3 4" for BUILD + RENDER)
   ```

   **Option generation rules**:
   - Option A always present: full rebuild from scratch
   - Option B auto-calculated: find the first ❌ phase, suggest resuming from that phase
   - Option C always present: user specifies phases freely
   - If all phases are ✅, option B becomes "All artifacts exist — rebuild anyway?"

   **Wait for user reply, then execute the selected phases.**

   #### Step 1 — Execute Selected Phases

   Based on the user's choice in Step 0:

   - **Choice A (full rebuild)** → Execute the full pipeline flow:
     1. Run Phase 1 SPEC (`--force --review`) to force regeneration
     2. **Must** read `DESIGN_REVIEW.json` and present review summary to user (CRITICAL/WARNING/INFO/OK counts + WARNING item details)
     3. Offer 3 options:
        - "Continue Review" → Discuss WARNING/CRITICAL items one by one, user may adjust parameters
        - "Auto-Fill" → Run `--auto-fill` then continue to subsequent stages
        - "Next Step" → Continue to Phase 2+ with existing data as-is
     4. After user confirms, ask for enhance backend (gemini/comfyui), then execute remaining stages:
        - Phase 2: `codegen --force` (force overwrite existing code)
        - Phase 3: `build` (regenerate STEP + GLB, overwrite old version)
        - Phase 4: `render` (re-render all views, overwrite old PNGs)
        - Phase 5: `enhance` (re-enhance with AI, overwrite old JPGs)
        - Phase 6: `annotate` (re-annotate, overwrite old annotated images)

   - **Choice B (resume)** → Start from the suggested phase, execute sequentially to the last phase:
     - If starting point includes Phase 1 SPEC, execute the review flow (same as Choice A steps 1-3)
     - If starting from Phase 3 BUILD or later, execute directly in order without review
     - If starting point includes Phase 5 ENHANCE, ask for enhance backend (gemini/comfyui) first

   - **Choice C (specific phases)** → Execute only the user-specified phases:
     - If includes Phase 4 RENDER, **must execute Phase 3 BUILD first** (GLB must be consistent with current code)
     - If includes Phase 5 ENHANCE, ask for enhance backend first
     - Execute remaining specified phases in order

   **Must not** skip Step 0 and directly run `cad_pipeline.py full` (pipeline layer also has checkpoint protection).

### Execution Constraints

- Environment check (env_check): Run detection commands one by one, report ✅/❌ status
- Validate config (validate): Read and check render_config.json completeness
- Build: `cad_pipeline.py build` runs build_all.py then **auto-executes render_dxf.py** to convert DXF to PNG engineering drawing preview (if script exists)
- Render: **Whether running the full pipeline or a standalone render, always run `build` first to regenerate the GLB, then execute the Blender render** (GLB is Blender's input and must be consistent with the current design)
- **CAD Spec intent** (`/cad-spec`): Outputs CAD_SPEC.md; v2.5.0+ includes §6.3 per-part positioning, §6.4 part envelope dimensions, §9 assembly constraints; v2.7.0+ adds §9.2 constraint declarations (contact/stack_on/fit codes, auto-derived from connection matrix)
- **Design Review intent** (`/cad-spec --review-only`): v2.5.0+ review items B10 (positioning mode consistency), B11 (envelope coverage), B12 (exclusion legality)
- **GATE-3.5 Assembly Validation** (v2.7.0+): After Phase 3 BUILD, auto-runs `assembly_validator.py` with 5 formula-driven checks (F1 overlap/F2 disconnect/F3 compactness/F4 size ratio/F5 exclusion compliance) → ASSEMBLY_REPORT.json. Four-gate system: GATE-1(review) → GATE-2(TODO scan) → GATE-3(orientation) → GATE-3.5(assembly validation)
- **Parts Library System** (v2.8.0+, v2.21.2 geometry-quality loop): Purchased part geometry source is driven by a `parts_library.yaml` registry — supports project/user STEP pool (`std_parts/`), shared vendor STEP cache, SolidWorks Toolbox STEP, `bd_warehouse`, `partcad`, plus the `jinja_primitive` terminal fallback. Phase 1 P7 envelope backfill writes library-probed sizes into §6.4; Phase 2 codegen uses `resolver.resolve(mode="codegen")` to decide each `make_std_*()` body form (codegen / step_import / python_import). Without a yaml the system is a no-op and output is byte-identical to v2.7.x. Kill switch: `CAD_PARTS_LIBRARY_DISABLE=1`
- **Model choice loop** (v2.21.2+): `DESIGN_REVIEW.json` may carry `geometry` groups, `group_action`, `candidates`, A-E quality grades, and suggested actions. When a user provides a STEP file, the agent must put structured `model_choices` into supplements. The pipeline copies the STEP into `std_parts/user_provided/`, writes `model_choices.json`, prepends `parts_library.yaml`, and the next codegen actually imports that STEP.
- **Registry Inheritance + Coverage / Geometry Report** (v2.8.1+ / v2.21.2+): A `parts_library.yaml` with `extends: default` inherits the skill-shipped default rules, with project mappings prepended. `gen_std_parts.py` prints a per-adapter coverage table and writes `cad/<subsystem>/.cad-spec-gen/geometry_report.json`, showing which parts use real/parametric models, which remain D/E fallback, and how to upgrade them. For a read-only recheck, run `python cad_pipeline.py model-audit --subsystem <name>`; `--strict` returns exit 1 when review-required models or missing STEP paths exist.
- **Flange F1+F3 + GLB consolidator** (v2.8.2+): The `disc_arms` geometry template was rewritten — arms + mounting platforms now span the FULL disc thickness with chamfer/fillet polish. `codegen/consolidate_glb.py` runs automatically after build to merge CadQuery's per-face mesh split, so each BOM part is a single GLB mesh node (GISBOT: 321 → 39 components)
- **Phase B vendor STEP files** (v2.8.2+): `tools/synthesize_demo_step_files.py` generates parametric stand-in STEP files for Maxon GP22C / LEMO FGG.0B / ATI Nano17 etc., demonstrating the step pool routing path. Real vendor STEP files should replace these placeholders
- **Read-only stages are side-effect-free**: review, candidate display, and diagnostics must use `inspect` / `probe` or existing decision logs only; they must not start SolidWorks COM export, synthesize STEP cache files, or rewrite the model registry. Note that legacy `probe_dims()` may still warm shared vendor stand-in cache; prefer `cad_pipeline.py model-audit`, `resolve(..., mode="probe")`, or an existing `geometry_report.json` when absolute read-only behavior is required.
- Troubleshoot: Ask user for specific error message first, then diagnose using troubleshooting guide
- Status: Scan cad/ and cad/output/ directories, count artifacts
- All action outputs should be concise and clear, using ✅/❌/⚠️ status markers
