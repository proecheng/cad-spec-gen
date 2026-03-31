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
   Phase 3  BUILD     → Check cad/output/ for subsystem .step/.glb files + mtime
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
- Render: **Whether running the full pipeline or a standalone render, always run `build` first to regenerate the GLB, then execute the Blender render** (GLB is Blender's input and must be consistent with the current design)
- Troubleshoot: Ask user for specific error message first, then diagnose using troubleshooting guide
- Status: Scan cad/ and cad/output/ directories, count artifacts
- All action outputs should be concise and clear, using ✅/❌/⚠️ status markers
