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

3. **Full pipeline request** (when user asks for "full pipeline" / "run all stages" / "complete workflow"):
   > **Rebuild Principle: Every full pipeline run starts from scratch, overwriting all existing artifacts (SPEC, GLB, PNG, JPG, etc.). Never check whether files exist — never skip any stage.**
   1. Run Phase 1 SPEC first (with `--force --review`) to force regeneration
   2. **Must** read `DESIGN_REVIEW.json` and present review summary to user (CRITICAL/WARNING/INFO/OK counts + WARNING item details)
   3. Offer 3 options for user to choose:
      - "Continue Review" → Discuss WARNING/CRITICAL items one by one, user may adjust parameters
      - "Auto-Fill" → Run `--auto-fill` then continue to subsequent stages
      - "Next Step" → Continue to Phase 2+ with existing data as-is
   4. After user confirms, ask for enhance backend (gemini/comfyui), then execute remaining stages:
      - Phase 2: `codegen --force` (force overwrite existing code)
      - Phase 3: `build` (regenerate STEP + GLB, overwrite old version)
      - Phase 4: `render` (re-render all views, overwrite old PNGs)
      - Phase 5: `enhance` (re-enhance with AI, overwrite old JPGs)
      - Phase 6: `annotate` (re-annotate, overwrite old annotated images)
   5. **Must not** skip this step and directly run `cad_pipeline.py full` (pipeline layer also has checkpoint protection)

### Execution Constraints

- Environment check (env_check): Run detection commands one by one, report ✅/❌ status
- Validate config (validate): Read and check render_config.json completeness
- Render: **Whether running the full pipeline or a standalone render, always run `build` first to regenerate the GLB, then execute the Blender render** (GLB is Blender's input and must be consistent with the current design)
- Troubleshoot: Ask user for specific error message first, then diagnose using troubleshooting guide
- Status: Scan cad/ and cad/output/ directories, count artifacts
- All action outputs should be concise and clear, using ✅/❌/⚠️ status markers
