# skill_cad_help — CAD Hybrid Rendering Pipeline Interactive Help

## Search-First Principle

**Before executing any intent action, always search the actual project files first — never assume from memory.**

1. **Search before answering** — For any question like "does a file exist" or "how is a config set", search the filesystem (ls/find/grep or equivalent tools) first, then answer
2. **Multi-path search** — The same information may exist in multiple places (environment variables, config files, code defaults); check all of them:
   - Gemini config: `~/.claude/gemini_image_config.json` > env var `GEMINI_GEN_PATH` > `gemini_gen.py`
   - Render tools: `cad/<subsystem>/render_3d.py` > `tools/blender/`
   - Prompt templates: `templates/` or `enhance_prompt.py`
3. **Record what you find** — Write the actual paths/versions/config values found into the output; do not use placeholder values from templates
4. **Don't guess what's missing** — If something cannot be found, do not assume it exists; mark it ❌ and provide creation/installation guidance

### Known Key Paths (search at runtime — these are examples)

| Component | Typical Path |
|-----------|-------------|
| gemini_gen.py | User-configured via `python gemini_gen.py --config`; path stored in `GEMINI_GEN_PATH` env var |
| Gemini config | `~/.claude/gemini_image_config.json` (api_key, api_base_url, model, output_dir) |
| Blender | `tools/blender/blender.exe` or env var `BLENDER_PATH` |
| Render scripts | `cad/<subsystem>/render_3d.py`, `render_exploded.py`, `render_section.py` |
| Prompt builder | `enhance_prompt.py`, `prompt_data_builder.py` |

## Intent Matching Table

Extract keywords from the user's question text, match to the best intent, then execute the corresponding action.

| Intent | Keywords | Action |
|--------|----------|--------|
| env_check | environment, install, setup, dependencies, requirements, what do I need, env | → Environment Check |
| validate | validate, check config, is config correct, verify, configuration valid | → Validate Configuration |
| next_step | next step, what's next, what to do, how to continue, next, proceed | → Recommend Next Step |
| new_subsys | new subsystem, create new, start, how to begin, quick start, from scratch, initialize, init | → Quick Start Guide + init scaffold |
| material | material, color, preset, appearance, aluminum, steel, plastic, PBR | → Material Preset Table |
| camera | camera, angle, viewpoint, view, shot, perspective | → Camera Configuration |
| explode | explode, exploded, disassemble, take apart, exploded view | → Exploded View Configuration |
| render | render, rendering, generate image, output image, blender, cycles, produce image | → Render Execution/Guide |
| ai_enhance | gemini, AI, enhance, prompt, photo-realistic, enhance, hybrid | → AI Enhancement Guide |
| troubleshoot | error, failed, not working, problem, bug, crash, fix, broken | → Troubleshooting Guide |
| file_struct | file, directory, where is, structure, file tree, tree, layout | → File Structure |
| status | status, progress, which subsystems, progress report | → Subsystem Status |
| integration | integrate, connect, other models, GLM, GPT, LLM, agent, invoke, universal, how to connect, framework | → Integrate Other LLMs/Agents |
| parts | parts, components, modules, BOM, bill of materials, part list, part tree, structure, breakdown, model library, STEP, standard parts | → Parse Design Document BOM / model library guidance |
| spec | CAD_SPEC, spec, specification, extract data, generate spec, parameter extraction, cad_spec | → CAD Spec Generation/Viewing |
| review | review, design review, check design, mechanics, assembly check, design audit | → Design Review |
| photo3d | project-guide, photo3d, photo3d-run, photo3d-autopilot, photo3d-action, photorealistic gate, one click photo, pass, warning, blocked, accepted, preview, run_id, ACTION_PLAN, LLM context | → Photo3D Contract Gate |

---

## Action Details

### 1. env_check — Environment Check

**Search first**: Search actual files before reporting — do not assume from templates.

Perform the following checks and report results:

```
Check items:
1. Python version (requires 3.10+): python --version
2. CadQuery: python -c "import cadquery; print(cadquery.__version__)"
3. ezdxf: python -c "import ezdxf; print(ezdxf.__version__)"
4. matplotlib: python -c "import matplotlib; print(matplotlib.__version__)"
5. Blender: search tools/blender/blender.exe → --version (requires 4.x LTS)
6. GPU rendering: detect GPU in Blender (OptiX/CUDA/HIP/OneAPI)
   - GPU found → automatically uses GPU (render_3d.py/render_exploded.py auto-detect)
   - No GPU → falls back to CPU (works but slower)
   - Can force with --gpu / --cpu flags
7. Gemini AI enhancement (check in priority order, any pass = ✅):
   a. Read ~/.claude/gemini_image_config.json → show api_base_url + model (hide key)
   b. Check env vars GEMINI_GEN_PATH
   c. Check if gemini_gen.py exists: gemini_gen.py or $GEMINI_GEN_PATH
   d. Run python cad_pipeline.py env-check (if it exists)
8. Fonts: check if FangSong font is available
```

Output format (fill with actual values found by searching):
```
Environment Check Results:
  ✅ Python 3.11.9
  ✅ CadQuery 2.7.0
  ✅ ezdxf 1.4.3
  ✅ matplotlib 3.10.8
  ✅ Blender 4.2.10 LTS (tools/blender/blender.exe)
  ⚠️ GPU rendering: no GPU detected — using CPU (slower)
     Tip: NVIDIA GPU can accelerate 5-20x (OptiX/CUDA)
  ✅ Gemini AI: ~/.claude/gemini_image_config.json
     API: https://your-proxy.com/v1
     Model: gemini-3-pro-image-preview
     gemini_gen.py: /path/to/gemini_gen.py
  ✅ FangSong font (C:\Windows\Fonts\simfang.ttf)
```

For missing items, provide installation commands:
- CadQuery: `pip install cadquery`
- ezdxf: `pip install ezdxf`
- matplotlib: `pip install matplotlib`
- Blender: Download Blender 4.2 LTS portable to `tools/blender/`
- Gemini: Run `python gemini_gen.py --config` to launch the configuration wizard

### 2. validate — Validate Configuration

Read the target subsystem's `render_config.json` and check:

```
1. JSON syntax correctness
2. Required fields: subsystem, materials, camera
3. Each entry in materials has part_pattern + preset/custom
4. At least 1 view exists in camera (number of views is not limited to 5; defined by subsystem render_config.json camera section)
5. Preset name is among 15 presets: brushed_aluminum, stainless_304, black_anodized, dark_steel,
   bronze, copper, gunmetal, anodized_blue, anodized_green, anodized_purple, anodized_red,
   peek_amber, white_nylon, black_rubber, polycarbonate_clear
6. axis values in explode are valid (radial/axial/custom)
```

Report format: `✅ Passed` or `❌ Item N failed: specific reason`

### 3. next_step — Recommend Next Step

Scan project status then recommend:

```python
# Decision logic:
1. Scan cad/*/render_config.json to find configured subsystems
2. Scan cad/*/build_all.py to find implemented subsystems
3. Scan cad/output/*.step, *.dxf, *.glb, *.png, *.jpg to count artifacts
4. Check output/ for existing render results
5. Compare with docs/design/ chapter list to find gaps

Recommendation priority:
  a. Has render_config.json but no build_all.py → "Complete 3D modeling"
  b. Has build_all.py but no .glb → "Run build_all.py --render to generate GLB"
  c. Has .glb but no PNG → "Run Blender rendering: render_3d.py"
  d. Has PNG but no JPG → "Run Gemini AI enhancement"
  e. All complete → "Choose next subsystem" (sorted by maturity)
```

### 4. new_subsys — Quick Start 3-Step Guide

```
=== New Subsystem Quick Start ===

Step 0: One-command scaffold (recommended)
  python cad_pipeline.py init --subsystem <name> [--name-cn <Chinese name>] [--prefix <prefix>]
  → Auto-generates three files:
      cad/<name>/render_config.json   (V1-V5 views + 15 materials + components with name_cn/name_en)
      cad/<name>/params.py            (parameter skeleton: envelope dims, material IDs, assembly name)
      docs/design/XX-<name>.md        (chapter template prompting user to fill requirements)
  → Edit the three files as prompted, then run the full pipeline

Step 1: Design normalization
  Extract parameters from design document docs/design/NN-*.md
  python cad_pipeline.py spec --design-doc docs/design/NN-*.md [--auto-fill]
  → Outputs DESIGN_REVIEW.md + CAD_SPEC.md

Step 2: Code generation + parametric modeling
  python cad_pipeline.py codegen --subsystem <name>
  → Generates params.py / build_all.py / station_*.py / assembly.py scaffolds
  (Note: scaffolds are incomplete — manually complete geometry logic before entering BUILD)
  New in v2.2.3: assembly.py now generates per-part offset positioning
  (translate() calls with Z-axis offsets derived from CAD_SPEC.md §6.2),
  on top of station-level radial transforms (_station_transform).
  Standard parts with unrealistic dimensions (e.g. cable length > assembly
  envelope) are auto-capped to visualization-friendly sizes.
  New in v2.21.2: purchased parts are model-library-first. Codegen tries
  project/user STEP, shared vendor STEP cache, SolidWorks Toolbox STEP,
  bd_warehouse, and PartCAD before falling back to simplified CadQuery
  geometry. It writes .cad-spec-gen/geometry_report.json with A-E quality
  grades, so users can see exactly which parts still need better models.
  Run `python cad_pipeline.py model-audit --subsystem <name>` for a
  read-only summary of review-required parts and missing STEP paths.
  Run `python cad_pipeline.py model-import --subsystem <name> --part-no <id>
  --step <path.step>` to copy a user-provided STEP into std_parts/,
  update parts_library.yaml, and verify resolver consumption.
  Run `python cad_pipeline.py sw-export-plan --subsystem <name> [--json]`
  before any SolidWorks Toolbox export. It writes/reads the read-only
  .cad-spec-gen/sw_export_plan.json candidate plan with `reuse_cache` or
  `export` actions only; actual COM export still requires explicit user
  confirmation.
  New in v2.7.1: assembly positioning fixes in _resolve_child_offsets():
  (A) orphan detection checks children positions — assemblies with positioned
      children are no longer falsely flagged as orphan (wrong stacking direction).
  (B) z_is_top combined entries (e.g. "电机+减速器 Z=+73mm") are deferred and
      stacked sequentially from top downward — no overlap, bottom touches reference.
  (C) auto-stack formula uses bottom-at-Z=0 convention — no gaps between parts.
  (D) seed from occupied-extent boundary — auto-stacked parts don't overlap explicit parts.
  New in v2.2.5: codegen supports generic part number prefixes (SLP-xxx,
  ACME-xxx, not just GIS-EE-xxx). BOM parser recognizes "图号"/"编号"
  table headers and "标准件" make_buy type. Flat BOM structures (single
  root assembly without sub-assembly hierarchy) are handled correctly.
  Run /mechdesign <subsystem_name> to launch interactive full workflow

Step 3: Full pipeline
  Run /cad-help full pipeline  or  /cad-help draw
  The agent will scan each phase's artifact status, show an overview table,
  and let you choose the starting point:
  (full rebuild / resume from a phase / rebuild specific phases only)
  Note: Do NOT run cad_pipeline.py full directly — must go through /cad-help Step 0 user confirmation flow
```

### 5. material — Material Preset Table

List the 15 `MATERIAL_PRESETS` from `render_config.py`:

```
=== 15 Engineering Material Presets ===

Metals (11 types):
  brushed_aluminum  — Brushed aluminum (silver-white, metallic=1.0, roughness=0.18, anisotropic=0.6)
  stainless_304     — 304 stainless steel (bright silver, metallic=1.0, roughness=0.15)
  black_anodized    — Black anodized aluminum (deep black, metallic=0.85, roughness=0.30)
  dark_steel        — Dark steel (dark gray, metallic=0.90, roughness=0.28)
  bronze            — Bronze (copper-yellow, metallic=0.90, roughness=0.25)
  copper            — Copper (reddish copper, metallic=1.0, roughness=0.15)
  gunmetal          — Gunmetal (dark gray, metallic=0.90, roughness=0.25)
  anodized_blue     — Blue anodized (blue, metallic=0.85, roughness=0.22)
  anodized_green    — Green anodized (green, metallic=0.85, roughness=0.22)
  anodized_purple   — Purple anodized (purple, metallic=0.85, roughness=0.22)
  anodized_red      — Red anodized (red, metallic=0.85, roughness=0.22)

Engineering Plastics/Rubber (4 types):
  peek_amber        — PEEK amber (yellowish, metallic=0, roughness=0.30, sss=0.08)
  white_nylon       — White nylon (white, metallic=0, roughness=0.45)
  black_rubber      — Black rubber (black, metallic=0, roughness=0.75)
  polycarbonate_clear — Clear polycarbonate (transparent, metallic=0, roughness=0.05, ior=1.58)

Custom example (render_config.json):
  "materials": {
    "flange*": {"preset": "brushed_aluminum"},
    "sensor*": {"color": [0.2, 0.3, 0.8, 1.0], "metallic": 0.5, "roughness": 0.3}
  }

Material Bridging (v2.2.3+):
  render_config.py provides resolve_bom_materials(config) — builds a
  bom_id → component → material lookup chain so the rendering pipeline
  can automatically derive PBR materials from design-document BOM entries.
  Lookup: BOM part ID (e.g. GIS-EE-001-01) → components section (bom_id match)
         → material field → materials section (preset/custom PBR params).
  Auto-generation: render_config.py can auto-create materials + components
  entries from BOM part-level data when they are missing, with consistency
  validation to catch orphan references.
```

### 6. camera — Camera Configuration

```
=== Camera Configuration ===

Two coordinate systems:

1. Spherical coordinates (recommended, intuitive):
   "type": "spherical",
   "azimuth": 45,      // Horizontal angle (0=front, 90=right side, 180=rear)
   "elevation": 30,    // Elevation angle (0=horizontal, 90=directly above)
   "distance_factor": 2.5  // Distance = factor x model bounding sphere radius

2. Cartesian coordinates (precise control):
   "type": "cartesian",
   "x": 0.3, "y": -0.4, "z": 0.2  // Camera position (meters)

Standard 5 views (default; views count and names can be customized in render_config.json):
  V1_front_iso     — Front isometric (az=35, el=25)  → Main showcase image
  V2_rear_oblique  — Rear oblique (az=215, el=20)    → Rear detail
  V3_side_elevation — Side elevation (az=90, el=0)   → Profile/dimensions
  V4_exploded      — Exploded view (az=35, el=35)    → Assembly relationships
  V5_ortho_front   — Front orthographic (az=0, el=0) → Orthographic projection

render_config.json example:
  "camera": {
    "V1": {"name": "V1_front_iso", "type": "spherical", "azimuth": 35, "elevation": 25, "distance_factor": 2.5},
    "V2": {"name": "V2_rear_oblique", "type": "spherical", "azimuth": 215, "elevation": 20, "distance_factor": 2.8}
  }
```

### 7. explode — Exploded View Configuration

```
=== Exploded View Configuration ===

explode_rules in render_config.json:

"explode_rules": [
  {
    "group": "station1",           // Group name
    "part_pattern": "station1_*",  // Match part names
    "axis": "radial",              // radial=outward from center | axial=along Z-axis | custom
    "distance_factor": 1.5         // Explosion distance = factor x part size
  },
  {
    "group": "flange",
    "part_pattern": "flange*",
    "axis": "axial",
    "distance_factor": 2.0
  },
  {
    "group": "sensor",
    "part_pattern": "uhf_*",
    "axis": "custom",
    "direction": [0.5, 0.5, 1.0], // Custom direction vector
    "distance_factor": 1.8
  }
]

axis types:
  radial  — Push outward radially from model center (suitable for rotational parts)
  axial   — Separate along Z-axis (suitable for stacked structures)
  custom  — Custom direction vector direction: [x, y, z]

render_exploded.py automatically draws assembly lines (dashed connectors).
```

### 8. render — Render Execution/Guide

**Principle: Any render/drawing request must first execute Step 0 (artifact scan + user choice) — never start running directly.**

When the agent receives a render request, follow `/cad-help` routing rule #3:
1. Scan the target subsystem's 6 phase artifact statuses
2. Show the user an overview table (✅/❌ for each phase)
3. Present options (full rebuild / resume / specific phases), wait for user choice
4. After user confirms, execute accordingly

**Technical constraints during execution**:
```
Whether running the full pipeline or a standalone render, always run build first
to regenerate GLB, then execute Blender rendering.
GLB is Blender's input and must be consistent with the current code/design.

Note: `cad_pipeline.py build` auto-runs render_dxf.py after build_all.py,
converting all DXF engineering drawings to PNG previews (if render_dxf.py exists).

  # Recommended: build triggers rendering (auto-generates new GLB then renders)
  # Also auto-generates DXF→PNG previews via render_dxf.py
  cd cad/<subsystem> && python build_all.py --render

  # Or two steps: build GLB first, then render specific views
  cd cad/<subsystem> && python build_all.py
  tools/blender/blender.exe -b -P cad/<subsystem>/render_3d.py -- \
    --config cad/<subsystem>/render_config.json

  # Exploded view (GLB must have been regenerated by this build session)
  tools/blender/blender.exe -b -P cad/<subsystem>/render_exploded.py -- \
    --config cad/<subsystem>/render_config.json
```

### 9. ai_enhance — AI Enhancement Guide

**Search first**: Read `~/.claude/gemini_image_config.json` to get actual config before answering.

```
=== Gemini AI Hybrid Enhancement ===

Technical approach: Blender PNG (geometry accurate) → Gemini --image mode → Photo-realistic PNG

First-time setup:
  python gemini_gen.py --config
  # Prompts for: API Key, API Base URL (your proxy), model name, output dir
  # Saved to: ~/.claude/gemini_image_config.json

Actual config (~/.claude/gemini_image_config.json):
  API:    https://your-proxy.com/v1
  Model:  gemini-3-pro-image-preview (or whichever your proxy supports)
  Key:    *** (configured)
  Timeout: 120s

Core tools:
  gemini_gen.py:     gemini_gen.py (global CLI tool)
  check_env.py:      python cad_pipeline.py env-check (environment check)

Prompt templates (templates/ directory):
  templates/prompt_enhance_unified.txt — all views (unified template, auto-switches by camera type)

Template variables (filled from render_config.json prompt_vars):
  {product_name}           ← prompt_vars.product_name
  {view_description}       ← camera.V*.description
  {material_descriptions}  ← prompt_vars.material_descriptions[]

Core principles:
  1. Viewpoint lock: prompt opens with "Preserve EXACT camera angle, viewpoint, framing";
     each view includes computed azimuth/elevation; IMAGE ROLES separate source composition from reference style
  2. Geometry lock: Gemini — prompt constraint; ComfyUI — ControlNet depth+canny hard constraint
  3. Material descriptions are read from render_config.json — never fabricated
  4. Layout awareness: non-radial subsystems do not inject hardcoded part descriptions
  5. Unified template auto-switches by camera type (exploded preserves spacing, orthographic has no perspective)

Multi-view consistency (v2.1):
  Four-layer defense for Gemini backend:
  1. Viewpoint Lock — _camera_to_view_description() computes azimuth/elevation from camera vectors
  2. Image Role Separation — source image FIRST (locks composition), reference SECOND (style only)
  3. V1-anchor Reference — V1 result serves as material style reference for V2-VN
  4. Source High-Fidelity — source ≤4MB sent uncompressed (original 1920×1080 PNG)

Standard workflow:
  1. Confirm Blender PNGs exist (V1~VN, from render_manifest.json)
  2. Read prompt_vars field from render_config.json
  3. Execute (choose one):
     python cad_pipeline.py enhance --subsystem <name>
     python cad_pipeline.py enhance --dir <dir>  # reads manifest from that dir
     python cad_pipeline.py enhance --dir <dir> --model <key>  # override model
     (V1 processed first as style anchor, V2~VN follow)
  4. Output: photo-realistic PNG (timestamped to prevent overwriting history)
  5. Optional: Add component labels (Chinese/English):
     python cad_pipeline.py annotate --dir <dir> --lang cn
     python cad_pipeline.py annotate --dir <dir> --lang en
     Output: *_labeled_cn.png / *_labeled_en.png
     Note: Chinese text is drawn programmatically via PIL+SimHei font, not through AI generation

Dual purpose:
  PNG → Design review/manufacturing reference (100% geometry accurate)
  PNG_enhanced → Presentations/proposals/business plans (visual appeal)
  PNG_labeled → Labeled showcase images (presentations/reports/manuals)

Annotation tool (annotate_render.py):
  Dependency: Pillow (PIL)
  Data source: render_config.json components section (CN/EN names extracted from design doc BOM) + labels section (2D anchor+label position per view per component)
  Data schema:
    "components": {"part_id": {"name_cn": "...", "name_en": "...", "bom_id": "GIS-XX-NNN"}}
    "labels": {"V1": [{"component": "part_id", "anchor": [x,y], "label": [x,y]}]}
  Key requirements:
    - Component names must be extracted verbatim from design document section X.8 BOM — never fabricated
    - Labels per view only annotate components visible in that view (occluded ones are omitted)
    - Coordinates are based on 1920x1080 reference resolution, automatically scaled to actual image size
  Styles: dark (white text on black background) / light (black text on white background), leader lines + dots + semi-transparent background rectangles
  Fonts: Chinese SimHei / English Arial

First-time setup:
  python gemini_gen.py --config
  (Interactive wizard to set API Key / Base URL / Model)
```

### 10. photo3d — Photo3D Contract Gate

**Trigger**: User asks for one-click photorealistic 3D output, photo3d, pass/warning/blocked gate status, accepted/preview/blocked delivery status, baseline drift, or LLM next actions.

Recommended first command for ordinary users and LLM agents:

```bash
python cad_pipeline.py project-guide --subsystem <name> --design-doc <path>
```

`project-guide` is a read-only project guide. It writes `PROJECT_GUIDE.json`, checks the explicit subsystem, optional design document, fixed `CAD_SPEC.md` / codegen sentinels, and the explicitly resolved `ARTIFACT_INDEX.json` active run. It selects the next safe handoff across `init`, `spec`, `codegen`, `build --render`, and `photo3d-run`. It does not scan directories, does not mutate pipeline state, does not accept baseline, and does not run enhancement.

When an active run already exists, the recommended Photo3D command is:

```bash
python cad_pipeline.py photo3d-run --subsystem <name>
```

`photo3d-run` is the foolproof multi-round guide. It runs the current active run through `photo3d` gate + `photo3d-autopilot`, writes `PHOTO3D_RUN.json`, and stops at `needs_baseline_acceptance`, `ready_for_enhancement`, `needs_user_input`, `needs_manual_review`, `execution_failed`, or `loop_limit_reached`. It does not accept baseline, does not run enhancement, does not switch `active_run_id`, and does not scan directories for the newest file. If the report says low-risk recovery is available, the user can explicitly confirm:

```bash
python cad_pipeline.py photo3d-run --subsystem <name> --confirm-actions
```

Single-round autopilot remains available:

```bash
python cad_pipeline.py photo3d-autopilot --subsystem <name>
```

`photo3d-autopilot` first runs the `photo3d` contract gate, then writes `PHOTO3D_AUTOPILOT.json`. The autopilot report is the fixed round-end report for ordinary users and LLMs: when gate status is `blocked`, it points to `ACTION_PLAN.json` / `LLM_CONTEXT_PACK.json`; when gate status is `pass` / `warning` and there is no accepted baseline, it recommends the explicit user-confirmed command `python cad_pipeline.py accept-baseline --subsystem <name>`; when `accepted_baseline_run_id` already exists, it recommends enhancement. It does not accept the baseline silently, does not switch `active_run_id`, and does not scan directories for the newest file.

Confirmed action runner:

```bash
python cad_pipeline.py photo3d-action --subsystem <name>
python cad_pipeline.py photo3d-action --subsystem <name> --confirm
```

`photo3d-action` reads only the current active run's `PHOTO3D_AUTOPILOT.json` and `ACTION_PLAN.json`. Preview mode writes `PHOTO3D_ACTION_RUN.json` without executing. With `--confirm`, it executes only allowlisted low-risk CLI recovery actions (`product-graph`, `build`, `render`) for the same subsystem/run_id and no user input. In `ACTION_PLAN.json`, those CLI actions must use the run-aware wrapper `python cad_pipeline.py photo3d-recover --subsystem <name> --run-id <run_id> --artifact-index cad/<name>/.cad-spec-gen/ARTIFACT_INDEX.json --action product-graph|build|render`; bare `product-graph` / `build` / `render --subsystem <name>` commands are not allowed automatic recoveries. User-input actions stay in the report for the user. When every confirmed low-risk CLI action succeeds and no user-input, manual-review, or rejected action remains, it 自动重跑 `photo3d-autopilot` and writes the next-step summary to `post_action_autopilot` in `PHOTO3D_ACTION_RUN.json`; preview, failed execution, remaining user input, or rejected actions do not rerun autopilot. It does not scan directories for latest artifacts, does not run enhancement, and does not accept baseline.

Confirmed next-action handoff:

```bash
python cad_pipeline.py photo3d-handoff --subsystem <name>
python cad_pipeline.py photo3d-handoff --subsystem <name> --confirm
```

`photo3d-handoff` reads the current active run's `PHOTO3D_RUN.json` or `PHOTO3D_AUTOPILOT.json` and writes `PHOTO3D_HANDOFF.json`. Preview mode is the default. With `--confirm`, it executes only recognized current next actions: `accept-baseline`, `enhance`, `enhance-check`, or `photo3d-run --confirm-actions`. It does not scan directories, never trusts arbitrary argv from JSON reports, and rebuilds argv from `ARTIFACT_INDEX.json`, the current `active_run_id`, and the current run/render paths. Delivery-complete, preview-review, user-input, manual-review, and unknown actions remain manual and are recorded in `PHOTO3D_HANDOFF.json`.

Underlying gate command:

```bash
python cad_pipeline.py photo3d --subsystem <name>
```

The command validates the current `run_id` before any AI enhancement. It reads artifacts only from `ARTIFACT_INDEX.json`; do not scan directories to guess the newest render, and do not fall back to a default path when the user supplied an explicit path.

Required contract chain:

1. `PRODUCT_GRAPH.json` proves what parts and instances should exist.
2. `MODEL_CONTRACT.json` proves each renderable part has a model decision.
3. `ASSEMBLY_SIGNATURE.json` proves the runtime assembly matches those instances.
4. `RENDER_MANIFEST.json` proves PNG outputs came from the current assembly, camera, material config, GLB, and file hashes.
5. Optional `baseline` / `CHANGE_SCOPE.json` proves drift is authorized.

Gate status:

- `pass`: CAD contract gate passed; enhancement may run.
- `warning`: CAD contract gate passed with non-blocking warnings; show warnings before enhancement.
- `blocked`: CAD contract gate failed; do not run AI enhancement.

Enhancement delivery status:

- `accepted`: CAD gate and enhancement consistency pass; image may be delivered.
- `preview`: CAD gate passed, but enhancement consistency is unverified or failed; use only as preview.
- `blocked`: CAD gate failed; enhancement must not run.

At this gate stage, `PHOTO3D_REPORT.json` may include `enhancement_status` as `not_run` or `blocked`; `accepted` / `preview` belong to the later enhancement delivery layer.

After enhancement, run delivery acceptance:

```bash
python cad_pipeline.py enhance-check --subsystem <name> --dir <render_dir>
```

`enhance-check` reads only the explicit render directory's `render_manifest.json` and same-directory `*_enhanced.*` files, then writes `ENHANCEMENT_REPORT.json`. Every manifest view must have a matching enhanced image; source/enhanced shape similarity and basic image QA determine `accepted` / `preview` / `blocked`. It does not scan directories for newest files and does not accept enhanced images outside `--dir`.

Outputs for ordinary users and LLMs:

- `PROJECT_GUIDE.json`: read-only project-level next-step report across init/spec/codegen/build-render/photo3d-run.
- `PHOTO3D_REPORT.json`: Chinese user-facing blocking reasons and status.
- `PHOTO3D_AUTOPILOT.json`: ordinary-user round-end report with the next safe action.
- `ACTION_PLAN.json`: machine-readable next actions such as rerun render, rerun build, request a model, or manual review.
- `LLM_CONTEXT_PACK.json`: compact context pack for other LLMs; it must reference only current `run_id` artifacts registered in `ARTIFACT_INDEX.json`.
- `PHOTO3D_ACTION_RUN.json`: preview/execution report from `photo3d-action`, including executable, user-input, rejected, and executed actions for the current run; `post_action_autopilot` records whether a successful confirmed run automatically reran autopilot and what next action it produced.
- `PHOTO3D_HANDOFF.json`: preview/execution report from `photo3d-handoff`, including the current source report, rebuilt safe argv, execution result, or manual-review reason for the current next action.
- `PHOTO3D_RUN.json`: multi-round report from `photo3d-run`, including each gate/autopilot/action round, final stop reason, and next safe action.
- `ENHANCEMENT_REPORT.json`: enhancement delivery acceptance report with per-view source image, enhanced image, similarity, QA, and `accepted` / `preview` / `blocked` status.

路径隔离 and old artifact cleanup:

- Every run has an isolated `run_id`.
- Contract files live under `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/`.
- Render files live under `cad/output/renders/<subsystem>/<run_id>/`.
- `ARTIFACT_INDEX.json` is the only active-run lookup table; old files do not become valid just because they still exist.
- 旧产物 cleanup may delete stale run/render directories, but never delete files referenced by the current `active_run_id`.

接受基准 / baseline flow:

- The first passing run is only a 候选基准 / candidate baseline.
- The user must confirm the current `PHOTO3D_REPORT.json`, then run `python cad_pipeline.py accept-baseline --subsystem <name>`.
- `PHOTO3D_REPORT.json` records `artifact_hashes` for the required contracts. `accept-baseline` validates that the report path, report artifact paths, and current artifact file hashes all match the same run in `ARTIFACT_INDEX.json`, so stale reports, handwritten reports, and mutated temporary artifacts cannot become baseline evidence.
- `accept-baseline` writes `accepted_baseline_run_id` to `ARTIFACT_INDEX.json`; it accepts only `pass` / `warning` reports, does not switch `active_run_id`, and does not scan directories for the newest artifact.
- Later `photo3d --change-scope <CHANGE_SCOPE.json>` automatically reuses the accepted baseline `ASSEMBLY_SIGNATURE.json`; `--baseline-signature <path>` remains an explicit override.
- Later runs compare against `baseline` / `CHANGE_SCOPE.json`; unauthorized count, bbox, position, or rotation drift must stay `blocked`. Reject accidental drift, or authorize intentional drift in `CHANGE_SCOPE.json` with an `authorized` scope entry.

Agent rule:

- Prefer `photo3d-run` / `PHOTO3D_RUN.json` for ordinary users and LLM-facing next-step loops.
- When the user says to execute the recommendation, prefer `photo3d-handoff` so baseline acceptance, enhancement, enhance-check, and action-plan confirmation all go through one confirmed active-run handoff instead of hand-written shell commands.
- When status is `blocked`, read `ACTION_PLAN.json` and choose only an allowed action.
- Use `photo3d-action` to preview/confirm low-risk CLI recovery actions; do not execute shell strings by hand. Allowed recovery shell commands must be `photo3d-recover` with explicit `--run-id` and `--artifact-index`, so product-graph/build/render outputs stay bound to the current run. After confirmed low-risk actions all succeed, read `post_action_autopilot` instead of guessing the next step, because the command automatically reruns `photo3d-autopilot` only when no user input, manual review, or rejected action remains.
- 不能扫描目录猜最新文件；只能使用当前 `run_id` 在 `ARTIFACT_INDEX.json` 中登记的产物。
- Do not use AI enhancement to repair missing CAD geometry, missing instances, wrong positions, stale renders, or baseline mismatch.
- If the action requires user input, ask for that input instead of inventing a file path or model choice.

### 11. troubleshoot — Troubleshooting Guide

```
=== Common Issue Troubleshooting ===

Q: Blender not found / fails to launch
A: Confirm tools/blender/blender.exe exists, Blender 4.2 LTS portable version

Q: CadQuery import error
A: pip install cadquery  (requires Python 3.10+)

Q: GLB export failed
A: Check that assembly.py correctly generates an Assembly object
   Confirm cad/output/ directory exists

Q: Blender render is all black/all white
A: Check if camera distance in render_config.json is reasonable (distance_factor 2~4)
   Check if lighting is configured

Q: Gemini API error
A: 1. Check if ~/.claude/gemini_image_config.json exists and is properly formatted
   2. Confirm api_base_url and model match your service provider
   3. Check network connectivity (proxy relay may require VPN)
   4. Run python gemini_gen.py --config to reconfigure
   5. Confirm Blender PNGs have been generated

Q: DXF opens with garbled text
A: Confirm FangSong font is installed
   ezdxf version must be >= 0.18

Q: render_config.json fails to load
A: Run /cad-help validate config to check JSON format
   Common issues: trailing commas, non-ASCII quotes, missing required fields

Q: Material not applied
A: Check if part_pattern matches actual part names
   Use python -c "import glob; print(glob.glob('cad/output/*.glb'))" to see actual file names

Q: Render resolution too low
A: render_config.json → "resolution": {"width": 1920, "height": 1080}
   Default is 1280x720

Q: Rendered image is nearly blank / only shows a few stacked boxes
A: 1. Check cad/<subsystem>/CAD_SPEC.md §6.2 — if it says "暂无数据",
      re-run: cad_pipeline.py spec --subsystem <name> --force --auto-fill
      then:   cad_pipeline.py codegen --subsystem <name> --force
      (spec generates §6.2 data; codegen reads it for assembly transforms)
   2. Check assembly.py — if all stations show (0.0°) with no transforms,
      §6.2 data was not consumed; re-run codegen after spec --force
   3. Check assembly.py per-part offsets — each part should have a
      translate() call before _station_transform(). Missing offsets cause
      parts to stack at origin. Re-run codegen --force to regenerate.
   4. Check ee_*.py files — codegen generates approximate geometry
      (cylinder/ring/disc based on BOM dimensions); refine manually if needed
   5. Check std_*.py files — cables/harnesses with unrealistic lengths
      (e.g. 500mm FFC in a 300mm assembly) are auto-capped to ~30mm for
      visualization; if yours still look wrong, re-run codegen --force

Q: Gemini enhanced image looks completely different from source PNG
A: The enhance pipeline has a quality gate that skips blank/near-empty renders.
   If you see "SKIP: render appears blank" in the log, the BUILD phase produced
   invalid output. Fix BUILD first, then re-run enhance.
   If the gate was not triggered but the enhanced image is wrong, the source PNG
   may have too few features for geometry lock to work — improve the 3D model.

Q: GATE-3.5 assembly validation fails (ASSEMBLY_REPORT.json shows FAIL)
A: assembly_validator.py checks 5 formulas post-build:
   F1 Overlap — parts overlapping beyond tolerance → check for colliding parts, adjust offsets
   F2 Disconnect — parts too far apart → check §6.3 positioning data completeness
   F3 Compactness — Z-span too large → check for orphaned parts or wrong stacking order
   F4 Size ratio — part size vs SPEC mismatch → check §6.4 envelope dimensions
   F5 Exclusion — non-local assembly present → check §9.1 exclusion list
   Fix the underlying issue, then re-run: cad_pipeline.py build --subsystem <name>

Q: §9.2 constraints not consumed / assembly still scattered
A: 1. Check CAD_SPEC.md §9.2 section exists (generated by v2.7.0+ cad_spec_gen.py)
   2. Re-run: cad_pipeline.py spec --subsystem <name> --force --auto-fill
   3. Then: cad_pipeline.py codegen --subsystem <name> --force
   4. gen_assembly.py parse_constraints() reads §9.2 for contact/stack_on positioning

Q: GLB has floating or overlapping components (v2.7.1 fix)
A: This was caused by 4 bugs in _resolve_child_offsets() fixed in v2.7.1:
   - Combined §6.2 entries (e.g. "电机+减速器 Z=+73mm") assigned same Z to both parts
   - Auto-stacking formula assumed center-origin but parts have bottom-at-Z=0
   - Orphan detection falsely triggered for assemblies with positioned children
   - Auto-stack seed overlapped with explicitly-placed parts
   Fix: upgrade to v2.7.1 and re-run: cad_pipeline.py codegen --subsystem <name> --force

Q: 外购件看起来还是圆柱/方盒，占位感很强
A: 1. Run `python cad_pipeline.py model-audit --subsystem <name>` and check
      review_required / geometry_quality. D/E means simplified or missing geometry.
   2. If the user has a trusted STEP file, run:
      `python cad_pipeline.py model-import --subsystem <name> --part-no <id> --step <path.step>`
      This copies to std_parts/user_provided/, prepends parts_library.yaml,
      and verifies resolver routing before the next codegen.
   3. In review-driven flows, answer the review prompt with structured model_choices:
      {"model_choices":[{"part_no":"...","step_file":"D:/models/part.step"}]}
   4. Re-run cad_pipeline.py spec --subsystem <name> --supplements '<json>' --auto-fill
      when applying user choices, then re-run codegen/build.
   5. If SolidWorks Toolbox is available, use SW candidates only after user
      confirmation. First run:
      `python cad_pipeline.py sw-export-plan --subsystem <name> --json`
      and show the read-only `sw_export_plan.json` candidates; inspect/probe/report
      stages must not trigger COM export.

Q: Photo3D / photo3d 输出 blocked，下一步怎么办？
A: 打开当前 run 的 `PHOTO3D_REPORT.json` 看中文阻断原因，然后读取
   `ACTION_PLAN.json`。大模型只能执行该文件列出的动作，例如重新渲染、
   重新 build、请求用户提供 STEP 模型或进入人工审查。不要扫描目录猜最新
   PNG，也不要让 AI 增强补齐 CAD 阶段缺失的结构。低风险 CLI 动作先运行
   `python cad_pipeline.py photo3d-action --subsystem <name>` 预览，用户确认后
   再加 `--confirm` 执行；结果写入 `PHOTO3D_ACTION_RUN.json`。动作计划里的
   CLI 必须是 `photo3d-recover --run-id <run_id> --artifact-index <path>`，
   禁止回退到裸 `render/build/product-graph --subsystem <name>`。
```

### 12. file_struct — File Structure

```
=== CAD Rendering Pipeline File Structure ===

cad/<subsystem>/                   ← Each subsystem has its own directory
├── params.py                      ← Single source of truth for parameters
├── *.py                           ← 3D model scripts (parts/assemblies)
├── assembly.py                    ← Main assembly → STEP + GLB (per-part offsets + station transforms)
├── drawing.py                     ← 2D engineering drawing engine (GB/T national standard)
├── draw_*.py                      ← Engineering drawings per part
├── render_dxf.py                  ← DXF→PNG conversion
├── render_config.json             ← Render configuration (materials/camera/explode/labels)
├── render_config.py               ← Config engine (15 material presets)
├── render_3d.py                   ← Blender Cycles render script
├── render_exploded.py             ← Exploded view render script
└── build_all.py                   ← One-click build (--render triggers Blender)

Reference implementation: cad/end_effector/ (section 4 End Effector, 14 scripts, 8 STEP + 11 DXF)

cad/output/                    ← Output directory
├── XX-000_assembly.step/.glb  ← Main assembly
├── XX-NNN_*.step              ← Sub-assembly STEP
├── XX-NNN-NN_*.dxf            ← 2D engineering drawing DXF
└── *.png / *.jpg              ← Render results

templates/                     ← Templates
├── render_config_template.json← Blank render config template (starting point for new subsystems)
├── cad_spec_template.md       ← CAD Spec template
├── prompt_enhance_unified.txt ← AI enhancement prompt: all views (unified template)
└── prompt_section.txt         ← Section view prompt template

cad/<subsystem>/               ← Per-subsystem CAD scripts
├── render_3d.py               ← Blender render script
├── render_exploded.py         ← Exploded view render
├── render_section.py          ← Cross-section render
└── render_config.json         ← Camera/material/prompt config

tools/blender/blender.exe      ← Blender 4.2 LTS portable

gemini_gen.py  ← Gemini image-to-image global tool (outside project)
~/.claude/gemini_image_config.json ← Gemini API config (key/url/model)

cad/<subsystem>/.cad-spec-gen/              ← Photo3D contract state
├── ARTIFACT_INDEX.json                     ← active run_id artifact index
└── runs/<run_id>/
    ├── PRODUCT_GRAPH.json
    ├── MODEL_CONTRACT.json
    ├── ASSEMBLY_SIGNATURE.json
    ├── PHOTO3D_REPORT.json
    ├── PHOTO3D_AUTOPILOT.json
    ├── PHOTO3D_ACTION_RUN.json
    ├── PHOTO3D_RUN.json
    ├── ACTION_PLAN.json
    └── LLM_CONTEXT_PACK.json
```

### 13. status — Subsystem Status

Scan and report:

```python
# Scanning logic:
1. glob cad/*/render_config.json → list of configured subsystems
2. glob cad/*/build_all.py → list of implemented subsystems
3. glob cad/output/*.step → STEP artifact count
4. glob cad/output/*.dxf → DXF artifact count
5. glob cad/output/*.glb → GLB artifact count
6. ls output/*.png, *.jpg → render result count
7. ls docs/design/*.md → all design chapters

# Output:
=== CAD Subsystem Status ===

Completed:
  ✅ end_effector (section 4 End Effector) — 8 STEP, 11 DXF, 1 GLB, 5 PNG, 5 JPG

Pending modeling (sorted by design maturity):
  ⬜ §5  Electrical System (★★★★☆)
  ⬜ §2  System Overview (★★★★☆)
  ⬜ §3  Chassis Navigation (★★★☆☆)
  ...

Recommendation: Next model §5 Electrical System (highest maturity unmodeled chapter)
```

### 14. integration — Integrate Other LLMs / Agents

```
=== Cross-Model Integration Guide ===

This pipeline has 3 layers; other LLMs/Agents only need to interface with the bottom layer tools:

Layer 1: Low-level Python scripts (any LLM/Agent that can execute shell commands can call these)
  ┌──────────────────────────────────────────────────────────────┐
  │ Script                          Purpose       CLI Args       │
  │ build_all.py                   One-click build --render      │
  │ render_3d.py (inside Blender)  3D rendering   --config --view --all │
  │ render_exploded.py (inside Blender) Exploded view --config --spread │
  │ render_dxf.py                  DXF→PNG        [file.dxf ...] │
  │ prompt_builder.py              Generate prompt --config --type │
  │ validate_config.py             Validate config <config.json>  │
  │ check_env.py                   Env check      --json          │
  │ gemini_gen.py                  Image-to-image --image <png> "prompt" │
  └──────────────────────────────────────────────────────────────┘

Layer 2: Skill knowledge documents (can be used directly as system prompt)
  system_prompt.md                     ← Universal system prompt (any LLM)
  skill_cad_help.md                    ← Complete knowledge base (15 intents + actions)
  docs/cad_pipeline_agent_guide.md     ← Detailed Agent integration guide

Layer 3: Platform adapters (install as needed)
  .claude/commands/                    ← Claude Code slash commands
  adapters/openai/functions.json       ← OpenAI Function Calling
  adapters/langchain/tools.py          ← LangChain Tool wrapper
  adapters/dify/README.md              ← Dify/Coze knowledge base import

Integration examples:

  GLM-4 + Function Calling:
    system_prompt = open("tools/cad_pipeline_agent_guide.md").read()
    tools = [{"name": "run_shell", "description": "Execute shell command"}]
    → GLM reads the guide → calls build_all.py / render_3d.py etc. per workflow

  GPT-4 + Assistants API:
    Upload cad_pipeline_agent_guide.md as a knowledge file
    Enable Code Interpreter → can directly run Python scripts

  LangChain / AutoGen / Dify:
    Inject knowledge documents into the Agent's system prompt
    Register shell tool → Agent autonomously calls pipeline scripts

  Any Agent framework:
    1. Feed cad_pipeline_agent_guide.md to the LLM as knowledge
    2. Provide shell/subprocess execution capability
    3. LLM generates and executes commands following the document guidance

Installation (PyPI recommended):
  pip install cad-spec-gen     # Install skill package
  cad-skill-setup              # Interactive wizard (language/env/deps/register)
  cad-skill-check              # Check environment status

Adapters for other platforms: see adapters/ directory (openai, langchain, dify)
```

### 15. parts — Parts/BOM Parsing

**Trigger**: User asks about a subsystem's parts, BOM list, component structure, etc.

**Execution steps**:

1. **Locate subsystem**: Extract subsystem name from user input, match to `docs/design/NN-*.md`
   - If not specified → prompt user to select a subsystem
   - Common mappings: end effector→04, electrical→05, chassis→01, system→02

2. **Run parser**:
   ```bash
   python bom_parser.py docs/design/NN-*design.md          # Tree output
   python bom_parser.py docs/design/NN-*design.md --json   # JSON output
   python bom_parser.py docs/design/NN-*design.md --summary # Statistics only
   ```

3. **Display results**: Output as tree structure (assembly→part hierarchy + make/buy tags + cost summary)

4. **When no BOM found**: If the parser reports "No BOM table found"
   - Prompt: "This subsystem's design document does not yet have a section X.8 BOM chapter"
   - Provide template: `docs/templates/bom_section_template.md`
   - Guide user to fill in using the template

**BOM Markdown specification** (consistent with section 4.8):
- Header row must contain `Part Number` and `Name` columns
- Assembly rows: part number format `GIS-XX-NNN` (3 segments, bold), make/buy column shows `Assembly`
- Part rows: part number format `GIS-XX-NNN-NN` (4 segments), belongs to the nearest assembly row above
- Unit price format: `500 CNY`, `100 CNY x2`, `—`

### 16. spec — CAD Spec Generation/Viewing

**Trigger**: User asks about CAD_SPEC, data extraction, parameter specifications, etc.

**Execution steps**:

1. **Generate CAD_SPEC**: Run the extractor for the specified subsystem
   ```bash
   python cad_spec_gen.py docs/design/NN-*design.md --config config/gisbot.json           # Single subsystem
   python cad_spec_gen.py docs/design/NN-*design.md --config config/gisbot.json --force   # Force regeneration
   python cad_spec_gen.py --all --config config/gisbot.json                                # All 18 subsystems
   ```

2. **View existing CAD_SPEC**: Read `cad/<subsystem>/CAD_SPEC.md`

3. **Check missing items**: Review section 9 Missing Data Report
   - CRITICAL → Inform user which content needs to be added to the design document
   - WARNING → List default values, confirm if acceptable
   - INFO → Optional optimization items

4. **Template**: `templates/cad_spec_template.md` (blank template with filling instructions)

### 17. review — Design Review

**Trigger**: User requests design review, mechanics/assembly/material checks, design audit.

**Execution steps**:

1. **Run review**: Extract data from design document then perform engineering validation
   ```bash
   # Review only (recommended for first use)
   python cad_spec_gen.py docs/design/NN-*design.md --config config/gisbot.json --review-only --force

   # Review + generate CAD_SPEC
   python cad_spec_gen.py docs/design/NN-*design.md --config config/gisbot.json --review --force
   ```

2. **Present review results**: Read `cad/<subsystem>/DESIGN_REVIEW.md` and summarize to user:
   - A. Mechanical review (cantilever bending moment, bolt shear, spring force)
   - B. Assembly review (dimension chain, envelope interference, mounting surface check, floating parts, connection method validation, spatial overlap)
   - C. Material review (galvanic corrosion, temperature margin, strength margin)
   - D. Missing data (CRITICAL/WARNING/INFO + whether auto-fill is possible)

3. **User choices**:
   - **"Continue review"** → Discuss WARNING/CRITICAL items one by one; user can adjust parameters
   - **"Auto-fill"** → Automatically fill computable missing items (bolt torque, units, surface roughness) and write to CAD_SPEC.md
   - **"Next step"** → Accept current results, generate CAD_SPEC.md

4. **Important principle**: Never directly modify the user's design document — all changes are reflected only in CAD_SPEC.md

---

## Help Panel (displayed when no parameters given)

```
=== /cad-help — CAD Hybrid Rendering Pipeline Help ===

Ask your question in natural language, for example:

  Environment & Installation
    /cad-help What needs to be installed?
    /cad-help Run an environment check

  Configuration & Validation
    /cad-help Validate my render_config.json
    /cad-help What materials are available?
    /cad-help How do I configure the camera?
    /cad-help How do I set up an exploded view?

  Workflow
    /cad-help What should I do next?
    /cad-help How do I set up a new subsystem?
    /cad-help How do I render images?
    /cad-help How do I use Gemini AI enhancement?

  Parts & BOM
    /cad-help What parts does the end effector have?
    /cad-help Electrical system BOM list

  Status & Troubleshooting
    /cad-help What is the current progress?
    /cad-help What do I do when I get an error?
    /cad-help Where are all the files?

  Integration
    /cad-help How do other LLMs call this pipeline?
    /cad-help How to integrate with GLM/GPT?
    /cad-help Where is the universal Agent guide?

Tip: No need to memorize command syntax — just describe what you want to do.
```
