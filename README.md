# CAD Spec Generator — Universal AI Skill for CAD Pipelines

> **From Markdown to machining-ready drawings and photorealistic renders — powered by any LLM.**

A **cross-platform AI skill** for the complete CAD pipeline. Works with Claude Code, GPT-4, GLM-4, Qwen, LangChain, AutoGen, Dify — or any LLM with shell execution. One skill gives your AI agent the ability to: extract specs from design docs, generate GB/T-compliant 2D drawings, produce geometrically accurate 3D renders, and create photorealistic presentation images.

## Installation

### From PyPI (Recommended)

```bash
pip install cad-spec-gen
cad-skill-setup
```

The interactive wizard guides you through:
1. Language selection (中文 / English)
2. Environment detection (Python, CadQuery, ezdxf, Blender, etc.)
3. Optional dependency installation
4. Blender configuration
5. Pipeline config generation
6. Skill file registration

Non-interactive mode: `cad-skill-setup --lang en --target . --skip-deps`

Check environment: `cad-skill-check`

After installation, type `/cad-help` in Claude Code to get started.

**Manual skill registration** (if not using `cad-skill-setup`):
- **Project-level**: `.claude/commands/*.md` (legacy) — auto-discovered in project dir
- **Global (recommended)**: Copy to `~/.claude/skills/<name>/SKILL.md` with YAML frontmatter for all-project access

### Update

```bash
pip install --upgrade cad-spec-gen
cad-skill-setup --update
```

### Other Platforms

| Platform | How to Install |
|----------|---------------|
| **Any LLM + Shell** | Paste [`system_prompt.md`](system_prompt.md) as system message |
| **GPT-4 / Assistants** | Upload `system_prompt.md` + enable Code Interpreter ([guide](adapters/openai/README.md)) |
| **LangChain / AutoGen** | `from adapters.langchain.tools import cad_tools` ([guide](adapters/langchain/README.md)) |
| **Dify / Coze** | Import `system_prompt.md` to knowledge base ([guide](adapters/dify/README.md)) |

All tools are **plain Python CLI scripts** — no framework lock-in, no vendor dependency.

```
Design Document (.md)
    ↓ cad_spec_gen.py --review — mechanical / assembly / material / completeness checks
DESIGN_REVIEW.md (issues & recommendations, user iterates or proceeds)
    ↓ cad_spec_gen.py — extract 9 categories of structured data
CAD_SPEC.md (single source of truth for all downstream CAD work)
    ↓ codegen/gen_*.py — Jinja2 templates → CadQuery scaffolds
params.py + build_all.py + station_*.py + std_*.py + assembly.py (per-part offsets + station transforms, generic part number support)
    ↓ CadQuery parametric modeling
STEP + STD-STEP (standard parts) + DXF (GB/T 2D drawings) + GLB
    ↓ render_dxf.py — auto DXF→PNG engineering drawing previews (if script exists)
DXF PNG previews (for design review)
    ↓ Blender Cycles rendering (GPU auto-detect, CPU fallback)
N-view PNG — 100% geometry-accurate, cross-view consistent (default 5, configurable)
    ↓ AI enhancement (reskin only, geometry locked) — Gemini or ComfyUI
       python cad_pipeline.py enhance --subsystem <name> [--dir <dir>] [--model <key>]
Photorealistic PNG — presentation / defense / business plan ready
    ↓ python cad_pipeline.py annotate — PIL-based component labels (CN/EN)
Labeled PNG — with leader lines and component names
```

## Why This Tool?

| Pain Point | How We Solve It |
|------------|----------------|
| Design docs have scattered parameters, tolerances, BOM across 600+ lines | **One command** extracts all 9 data categories into a single structured spec |
| Design docs may have engineering errors (stress, fit, material) | **Design review** checks mechanics, assembly, materials, completeness before CAD |
| Pure text-to-image AI gets ~42% geometry accuracy | **Hybrid pipeline**: Blender renders exact geometry first, AI only "reskins" the surface |
| "What should I do next?" is hard to answer in a complex pipeline | **Natural-language assistant** scans your project artifacts and recommends the next action |
| Cross-view consistency is poor with AI-generated images | **Blender-first** approach locks geometry across all views; AI inherits consistency |
| 2D drawings don't follow national standards | **GB/T compliant**: first-angle projection, FangSong font, 12-layer DXF with 0.5mm line widths |
| Hard to integrate with other LLMs (GPT, GLM, Qwen...) | **LLM-agnostic**: pure Python CLI + `system_prompt.md` + platform adapters |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Platform Adapters  (pick one, or use system_prompt.md)   │
│  ├── .claude/commands/ → Claude Code slash commands        │
│  ├── openai/       → Function Calling JSON schema         │
│  ├── langchain/    → LangChain/AutoGen Tool wrapper       │
│  └── dify/         → Knowledge base import guide          │
├──────────────────────────────────────────────────────────┤
│  Universal Skill Layer                                    │
│  ├── skill.json         → machine-readable skill manifest │
│  ├── system_prompt.md   → paste into any LLM              │
│  └── skill_cad_help.md  → 16-intent knowledge base        │
├──────────────────────────────────────────────────────────┤
│  Tool Layer  (pure Python CLI, no LLM dependency)         │
│  ├── cad_pipeline.py    → unified 6-phase orchestrator    │
│  ├── cad_spec_gen.py    → spec extraction                 │
│  ├── cad_spec_reviewer.py → design review (4 categories)  │
│  ├── codegen/gen_*.py   → Jinja2 code generation          │
│  ├── bom_parser.py      → BOM parsing                     │
│  └── config/templates/  → subsystem configs + Jinja2 .j2  │
└──────────────────────────────────────────────────────────┘
```

## Pipeline Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                   CAD Hybrid Rendering Pipeline                 │
│                                                                 │
│  1. DESIGN REVIEW (optional, recommended)                         │
│     Design doc (.md) → cad_spec_gen.py --review                   │
│     → DESIGN_REVIEW.md (A.mechanical / B.assembly incl. B5-B8    │
│       floating parts & connection checks / C.material / D.gaps)  │
│     User: "继续审查" / "自动补全" (--auto-fill) / "下一步"          │
│  ✋ [GATE-1] CRITICAL issues block SPEC phase until confirmed     │
│                                                                 │
│  2. SPEC EXTRACTION (this repo)                                   │
│     Design doc (.md) → cad_spec_gen.py → CAD_SPEC.md            │
│     9 sections: params, tolerances, fasteners, connections,     │
│     BOM tree, assembly pose, visual IDs, render plan, gaps      │
│                                                                 │
│  3. CODE GENERATION (Jinja2)                                      │
│     CAD_SPEC.md → codegen/gen_*.py → params.py + build_all.py   │
│     + station_*.py scaffolds + std_*.py (standard parts)         │
│     + assembly.py (per-part offsets + station radial transforms)  │
│     Templates: templates/*.j2 (scaffold mode, never overwrites) │
│     ⚠ Scaffolds are incomplete: params.py needs correct naming,  │
│     build_all.py needs valid module refs, assembly.py needs       │
│     hand-written mate logic. Complete before Phase 4.             │
│     v2.2.3: cable/harness lengths auto-capped for visualization  │
│  ✋ [GATE-2] TODO scan — exit code 2 if unfilled TODO: markers   │
│                                                                 │
│  4. PARAMETRIC MODELING                                         │
│  ✋ [GATE-3] orientation_check.py — asserts bounding-box axes    │
│     CadQuery scripts → STEP + GLB + DXF                        │
│     - 3D: assemblies with precise mate constraints              │
│     - 2D: GB/T A3 drawings, 3-view + section views              │
│                                                                 │
│  5. 3D RENDERING (Blender Cycles, GPU auto-detect)                │
│     GLB → N-view PNG (geometry 100% accurate, default 5 views)  │
│     15 PBR material presets · spherical camera system            │
│     Default views: front-iso / rear / side / exploded / ortho   │
│     Views are config-driven: render_config.json camera section   │
│                                                                 │
│  6. AI ENHANCEMENT (optional)                                   │
│     PNG → photorealistic JPG (reskin only, geometry locked)     │
│     Prompt: "Keep ALL geometry EXACTLY" + material description  │
│     Standard parts: simplified shapes → realistic appearance    │
│     Material bridging: bom_id→component→material auto-lookup    │
│     Model: configurable via pipeline_config.json (Nano Banana)  │
│                                                                 │
│  Output:  PNG → engineering review / machining reference        │
│           JPG → presentations / proposals / business plans      │
└────────────────────────────────────────────────────────────────┘
```

## Quality Gates

Three mandatory checkpoints block the pipeline on failure:

| Gate | Phase | Check | Exit code |
|------|-------|-------|-----------|
| Gate 1 — CRITICAL review | SPEC | `cad_spec_reviewer.py` finds CRITICAL issues | non-0, user must confirm |
| Gate 2 — TODO scan | CODEGEN | Generated scaffold files contain unfilled `TODO:` markers | 2, prints file:line list |
| Gate 3 — Orientation check | BUILD (pre) | `orientation_check.py` asserts bounding-box principal axes match design doc | non-0; bypass with `--skip-orientation` |

Gate 3 is skipped if `orientation_check.py` does not exist in the subsystem directory (non-mandatory for new subsystems).

## Key Features

### Spec Extraction (`cad_spec_gen.py`)
- **9-section structured output**: parameters, tolerances, fasteners, connection matrix, BOM tree, assembly pose, visual IDs, render plan, completeness report
- **Design review mode** (`--review`): mechanical stress (A1-A3), assembly fit & connection graph (B1-B8), material compatibility (C1-C3), completeness gaps (D1+) → `DESIGN_REVIEW.md`
- **User-driven iteration**: 3 options — "继续审查" (iterate) / "自动补全" (`--auto-fill`, computes missing torques/Ra/units) / "下一步" (proceed)
- **Idempotent**: MD5-based skip — won't regenerate if source unchanged
- **Auto-defaults**: standard bolt torques (8.8 grade), surface Ra by material type
- **Derived calculations**: total cost, part count, BOM completeness %
- **Configurable**: subsystem mapping via JSON config, no hardcoded paths
- **Generic part numbers**: supports any prefix format (GIS-EE-xxx, SLP-xxx, ACME-xxx) — not limited to GIS
- **Flat BOM support**: subsystems without sub-assembly hierarchy are handled correctly

### Interactive Help (16 Intents)
- **Natural language** — no need to memorize CLI syntax, just ask in plain language
- **16 intents**: environment check, config validation, next-step recommendation, materials, camera, exploded view, rendering, AI enhancement, troubleshooting, file structure, status, cross-model integration, parts/BOM, CAD spec, design review
- **Smart "what's next?"** — scans project artifacts (STEP/DXF/GLB/PNG/JPG) and recommends the highest-priority next action

### 2D Engineering Drawings
- **GB/T national standard**: first-angle projection, A3 sheet, title block
- **12-layer DXF** system with 0.5mm line widths per GB/T 17450
- **FangSong font**, 3.5mm annotation height
- Section views (A-A cut lines), datum triangles, default Ra callouts

### 3D Rendering
- **Blender Cycles** with GPU auto-detect (OptiX > CUDA > HIP > OneAPI > CPU fallback) — also works on remote desktops without GPU
- **5 standard views** (default, configurable per subsystem): V1 front-iso, V2 rear-oblique, V3 side-elevation, V4 exploded, V5 ortho-front
- **15 PBR material presets**: brushed aluminum, PEEK, carbon fiber, rubber, glass, etc.
- **Exploded views**: radial / axial / custom explosion with assembly lines
- **Config-driven**: `render_config.json` controls materials, cameras, explosion rules
- **Material bridging**: `resolve_bom_materials()` auto-derives PBR materials from BOM part IDs via bom_id→component→material lookup chain; auto-creates missing entries with consistency validation

### AI Enhancement (Hybrid Rendering)
- **Geometry-locked**: Blender PNG provides exact geometry; AI only changes surface appearance
- **Standard parts**: simplified CadQuery shapes (motors, bearings, springs) enhanced to realistic appearance via `{standard_parts_description}` prompt
- **Cross-view consistent**: all 5 views share the same 3D source
- **Dual output**: PNG for engineering, JPG for presentation
- **Prompt templates**: auto-generated from render config variables
- **Model selection**: configurable via `pipeline_config.json` — Nano Banana / Nano Banana Pro / Nano Banana 2

## Quick Start

> **Two reference subsystems included**: End Effector (GIS-EE, radial layout, 24 parts) and Lifting Platform (SLP, vertical linear actuator, 32 parts). Adapt paths for your own subsystem.

```bash
# Scaffold a new subsystem (generates render_config.json, params.py, design doc template)
python cad_pipeline.py init --subsystem robot_arm --name-cn 机器人臂 --prefix RA
# → output/robot_arm/render_config.json, output/robot_arm/params.py, docs/design/XX-robot_arm.md

# One-click full pipeline (all 6 phases)
python cad_pipeline.py full --subsystem end_effector \
    --design-doc docs/design/04-末端执行机构设计.md --timestamp

# Or step-by-step:

# Phase 1: Design review + spec (recommended first)
python cad_pipeline.py spec --design-doc docs/design/04-末端执行机构设计.md --auto-fill
# → cad/end_effector/DESIGN_REVIEW.md + CAD_SPEC.md

# Phase 2: Generate CadQuery scaffolds
python cad_pipeline.py codegen --subsystem end_effector
# → params.py, build_all.py, station_*.py, std_*.py, assembly.py

# Phase 3-4: Build + render
python cad_pipeline.py build --subsystem end_effector
python cad_pipeline.py render --subsystem end_effector --timestamp
# Note: view script selection is automatic from render_config.json `type` field
# (type=exploded → render_exploded.py, type=section → render_section.py, etc.)

# Phase 5-6: AI enhance + annotate (optional)
# enhance auto-reads render_manifest.json (only current-session renders); use --dir to override
python cad_pipeline.py enhance --subsystem end_effector
python cad_pipeline.py annotate --subsystem end_effector --lang cn,en

# Check pipeline status
python cad_pipeline.py status

# Check environment
python cad_pipeline.py env-check
```

### AI Enhancement Quick Start

After Blender renders your PNGs, enhance them to photorealistic images via the pipeline.
Two backends are supported: **Gemini** (cloud, default) and **ComfyUI** (local GPU, ControlNet geometry lock).

**v2.1 — Multi-view consistency (Gemini):** four-layer defense ensures each view keeps its correct camera angle after enhancement: auto-computed azimuth/elevation written into prompt, source image placed first (locks composition), V1 result used as material anchor for V2–VN, source PNG sent at full resolution (≤4 MB uncompressed).

**First-time Gemini setup** — configure your API proxy:
```bash
python gemini_gen.py --config
# Prompts for: API Key, API Base URL (your proxy), model name, output dir
# Saved to: ~/.claude/gemini_image_config.json
```

```bash
# Default: Gemini backend, auto-read render_manifest.json
python cad_pipeline.py enhance --subsystem <name>

# Specify custom output directory (also reads manifest from that dir)
python cad_pipeline.py enhance --dir /path/to/renders

# Override model temporarily
python cad_pipeline.py enhance --dir /path/to/renders --model nano_banana_pro

# ComfyUI backend (requires local GPU + ComfyUI running)
python cad_pipeline.py enhance --subsystem <name> --backend comfyui

# Check ComfyUI environment manually before first use
python comfyui_env_check.py
```

The enhance step automatically:
- Reads `render_manifest.json` from `--dir` or default renders dir to process only latest render files
- Auto-enriches prompt data from `params.py` via `prompt_data_builder.py` (materials, assembly description, constraints)
- **Gemini** (v2.1): geometry and viewpoint locked via prompt — auto-computed camera angle (azimuth/elevation), source image first, V1-anchor reference, full-res PNG input
- **ComfyUI**: uses ControlNet depth+canny to hard-lock geometry; requires local GPU
- Skips `*_enhanced.*` files to prevent re-processing

Switch backend permanently in `pipeline_config.json`:
```json
"enhance": { "backend": "comfyui" }
```

Output: `<render_dir>/<VN>_<name>_<timestamp>_enhanced.png` per view, photorealistic studio quality.

### Component Label Annotation

After AI enhancement, add component labels (Chinese/English) via PIL:

```bash
# Annotate all views in Chinese (auto-reads manifest)
python cad_pipeline.py annotate --subsystem <name> --lang cn

# Annotate from a specific directory
python cad_pipeline.py annotate --dir /path/to/renders --lang cn,en
```

Labels are defined in `render_config.json`:
- `components` section: maps IDs to CN/EN names + BOM IDs (from design doc §X.8 BOM)
- `labels` section: per-view coordinates for **visible** components only (occluded = not labeled)
- Coordinates at 1920×1080 reference (configurable via `reference_resolution`), auto-scaled to actual image size

## Adding a New Subsystem

### Option A: One-command scaffold (recommended)

```bash
python cad_pipeline.py init --subsystem <your_subsystem> --name-cn <中文名> --prefix <PREFIX>
```

Generates three files automatically:
- `output/<your_subsystem>/render_config.json` — camera views (V1-V5), materials, CN/EN component names
- `output/<your_subsystem>/params.py` — dimension skeleton
- `docs/design/XX-<your_subsystem>.md` — design doc template

Then edit each file and run the full pipeline:
```bash
python cad_pipeline.py full --subsystem <your_subsystem> --design-doc docs/design/XX-<your_subsystem>.md
```

### Option B: Manual setup

1. **Create directory and config**:
   ```bash
   mkdir cad/<your_subsystem>/
   cp templates/render_config_template.json cad/<your_subsystem>/render_config.json
   ```
   Edit `render_config.json` — fill in subsystem info, materials, camera views, and components.

2. **Auto-generate scaffolds** (if design doc exists):
   ```bash
   python cad_pipeline.py spec --design-doc docs/design/NN-*.md
   python cad_pipeline.py codegen --subsystem <your_subsystem>
   ```

3. **Refine scaffolds**: Edit generated files — params.py needs correct descriptive parameter names (codegen produces line-number based names), build_all.py needs valid module references, assembly.py needs real mate logic. Replace placeholder boxes in station_*.py with actual CadQuery geometry.

4. **Build + render**:
   ```bash
   python cad_pipeline.py full --subsystem <your_subsystem> --skip-spec --skip-codegen --timestamp
   ```

See `templates/render_config_template.json` for field documentation.

## Usage

```
python cad_spec_gen.py [FILES...] --config CONFIG [OPTIONS]

Required:
  --config PATH         JSON config with subsystem mapping

Options:
  --output-dir DIR      Output directory (default: ./output)
  --doc-dir DIR         Design docs directory for --all
  --all                 Process all NN-*.md in doc-dir
  --force               Force regeneration (ignore MD5 check)
  --review              Run design review before spec generation
  --review-only         Run design review only (no spec generation)
  --auto-fill           Auto-fill computable missing values (torques, units, Ra)
```

### Process all subsystems at once

```bash
python cad_spec_gen.py --all --config config/gisbot.json --doc-dir docs/design
```

### BOM parser (standalone)

```bash
python bom_parser.py examples/04-末端执行机构设计.md          # tree view (GIS-EE format)
python bom_parser.py examples/04-末端执行机构设计.md --json   # JSON output
python bom_parser.py examples/04-末端执行机构设计.md --summary # one-line summary
# Supports any BOM table header: 料号/图号/编号 + 名称 + 数量 (+ optional 材质/类型/备注)
```

## Configuration

Create a JSON config file (see `config/gisbot.json` for a full 19-subsystem example):

```json
{
  "doc_dir": "docs/design",
  "output_dir": "./output",
  "subsystems": {
    "04": {
      "name": "End Effector",
      "prefix": "GIS-EE",
      "cad_dir": "end_effector",
      "aliases": ["ee", "end_effector"]
    },
    "19": {
      "name": "Lifting Platform",
      "prefix": "SLP",
      "cad_dir": "lifting_platform",
      "aliases": ["升降", "lifting"]
    }
  }
}
```

## 15 PBR Material Presets

| Category | Presets |
|----------|---------|
| Metal | `brushed_aluminum` `stainless_304` `black_anodized` `dark_steel` `bronze` `copper` `gunmetal` `anodized_blue` `anodized_green` `anodized_purple` `anodized_red` |
| Plastic | `peek_amber` `white_nylon` `black_rubber` `polycarbonate_clear` |

## Documentation

| Document | Language | Description |
|----------|----------|-------------|
| [System Prompt](system_prompt.md) | EN | Universal system prompt — paste into any LLM |
| [Skill Manifest](skill.json) | — | Machine-readable skill definition |
| [User Guide (English)](docs/cad-help-guide-en.md) | EN | Full feature walkthrough, 16 intents, workflows |
| [User Guide (Chinese)](docs/cad-help-guide-zh.md) | 中文 | 完整功能说明、16种意图、典型工作流 |
| [Agent Integration Guide](docs/cad_pipeline_agent_guide.md) | 中文 | LLM/Agent framework integration (GPT, GLM, LangChain, etc.) |
| [CAD Spec Template](templates/cad_spec_template.md) | — | Output format reference with all 9 sections |
| [AI Prompt Templates](templates/) | EN | Unified prompt template (`prompt_enhance_unified.txt`) with auto view-type switching (standard/exploded/ortho/section) |

## Project Structure

```
├── skill.json                      # Machine-readable skill manifest
├── system_prompt.md                # Universal system prompt (any LLM)
├── skill_cad_help.md               # Skill knowledge (16 intents + actions)
├── cad_pipeline.py                 # Unified 6-phase pipeline orchestrator
├── cad_paths.py                    # Path resolution (SKILL_ROOT / PROJECT_ROOT / Blender / Gemini)
├── render_config.py                # Render config engine (15 material presets + material bridging)
├── pipeline_config.json            # Persistent config (Blender path, render settings)
├── cad_spec_gen.py                 # Spec extraction (CLI entry point)
├── cad_spec_extractors.py          # 8 extraction functions + table parser
├── cad_spec_defaults.py            # Standard defaults, engineering constants
├── cad_spec_reviewer.py            # Design review engine (4 categories)
├── bom_parser.py                   # BOM table parser (also standalone CLI)
├── annotate_render.py              # PIL-based component label annotation (CN/EN)
├── enhance_prompt.py               # Prompt builder for AI enhancement phase
├── prompt_data_builder.py          # Auto-generates material/assembly data from params.py
├── comfyui_enhancer.py             # ComfyUI backend: ControlNet depth+canny geometry lock
├── comfyui_env_check.py            # ComfyUI environment validator (GPU, models, server mode)
├── codegen/                        # Jinja2 code generation from CAD_SPEC.md
│   ├── gen_params.py               # §1 params → params.py
│   ├── gen_build.py                # §5 BOM → build_all.py (STEP + STD + DXF)
│   ├── gen_parts.py                # §5 custom leaf parts → station_*.py scaffolds
│   ├── gen_std_parts.py            # §5 purchased parts → std_*.py (simplified geometry)
│   └── gen_assembly.py             # §4+§5+§6 → assembly.py (incl. standard parts)
├── templates/
│   ├── params.py.j2                # Jinja2: params.py generation
│   ├── build_all.py.j2             # Jinja2: build_all.py generation
│   ├── part_module.py.j2           # Jinja2: part module scaffold
│   ├── assembly.py.j2              # Jinja2: assembly scaffold
│   ├── cad_spec_template.md        # Output template reference
│   ├── design_review_template.md   # Design review output template
│   ├── prompt_enhance_unified.txt  # AI prompt: all views (unified template)
│   └── prompt_section.txt          # Section view prompt template
├── gemini_gen.py                   # Gemini image generation (OpenAI-compatible API)
├── .claude/commands/               # Claude Code slash commands (5 commands, legacy format)
├── adapters/
│   ├── openai/
│   │   ├── functions.json         # OpenAI Function Calling schema
│   │   └── README.md              # GPT-4 / Assistants setup guide
│   ├── langchain/
│   │   ├── tools.py               # LangChain Tool wrapper
│   │   └── README.md              # LangChain / AutoGen setup guide
│   └── dify/
│       └── README.md              # Dify / Coze setup guide
├── config/
│   └── gisbot.json                # Example: 19-subsystem config
├── cad/
│   ├── end_effector/              # Reference: radial 4-station layout (GIS-EE, 24 parts)
│   └── lifting_platform/         # Reference: vertical linear actuator (SLP, 32 parts)
├── examples/
│   └── 04-末端执行机构设计.md       # Example design document
└── docs/
    ├── cad-help-guide-en.md       # User guide (English)
    ├── cad-help-guide-zh.md       # User guide (Chinese)
    └── cad_pipeline_agent_guide.md # Cross-LLM agent integration guide
```

## License

MIT
