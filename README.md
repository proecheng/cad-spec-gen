# CAD Spec Generator — Universal AI Skill for CAD Pipelines

> **From Markdown to machining-ready drawings and photorealistic renders — powered by any LLM.**

A **cross-platform AI skill** for the complete CAD pipeline. Works with Claude Code, GPT-4, GLM-4, Qwen, LangChain, AutoGen, Dify — or any LLM with shell execution. One skill gives your AI agent the ability to: extract specs from design docs, generate GB/T-compliant 2D drawings, produce geometrically accurate 3D renders, and create photorealistic presentation images.

## Use with Any LLM

| Platform | How to Install |
|----------|---------------|
| **Any LLM + Shell** | Paste [`system_prompt.md`](system_prompt.md) as system message |
| **Claude Code** | `python install.py --platform claude-code --target your-project/` |
| **GPT-4 / Assistants** | Upload `system_prompt.md` + enable Code Interpreter ([guide](adapters/openai/README.md)) |
| **LangChain / AutoGen** | `from adapters.langchain.tools import cad_tools` ([guide](adapters/langchain/README.md)) |
| **Dify / Coze** | Import `system_prompt.md` to knowledge base ([guide](adapters/dify/README.md)) |

All tools are **plain Python CLI scripts** — no framework lock-in, no vendor dependency.

```
Design Document (.md)
    ↓ cad_spec_gen.py — extract 9 categories of structured data
CAD_SPEC.md (single source of truth for all downstream CAD work)
    ↓ CadQuery parametric modeling
STEP + DXF (GB/T national-standard 2D drawings) + GLB
    ↓ Blender Cycles CPU rendering
5-view PNG — 100% geometry-accurate, cross-view consistent
    ↓ AI enhancement (reskin only, geometry locked)
Photorealistic JPG — presentation / defense / business plan ready
    ↓ annotate_render.py — PIL-based component labels (CN/EN)
Labeled JPG — with leader lines and component names
```

## Why This Tool?

| Pain Point | How We Solve It |
|------------|----------------|
| Design docs have scattered parameters, tolerances, BOM across 600+ lines | **One command** extracts all 9 data categories into a single structured spec |
| Pure text-to-image AI gets ~42% geometry accuracy | **Hybrid pipeline**: Blender renders exact geometry first, AI only "reskins" the surface |
| "What should I do next?" is hard to answer in a complex pipeline | **Natural-language assistant** scans your project artifacts and recommends the next action |
| Cross-view consistency is poor with AI-generated images | **Blender-first** approach locks geometry across all 5 standard views; AI inherits consistency |
| 2D drawings don't follow national standards | **GB/T compliant**: first-angle projection, FangSong font, 12-layer DXF with 0.5mm line widths |
| Hard to integrate with other LLMs (GPT, GLM, Qwen...) | **LLM-agnostic**: pure Python CLI + `system_prompt.md` + platform adapters |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Platform Adapters  (pick one, or use system_prompt.md)   │
│  ├── claude-code/  → .claude/commands/ slash commands     │
│  ├── openai/       → Function Calling JSON schema         │
│  ├── langchain/    → LangChain/AutoGen Tool wrapper       │
│  └── dify/         → Knowledge base import guide          │
├──────────────────────────────────────────────────────────┤
│  Universal Skill Layer                                    │
│  ├── skill.json         → machine-readable skill manifest │
│  ├── system_prompt.md   → paste into any LLM              │
│  └── skill_cad_help.md  → 15-intent knowledge base        │
├──────────────────────────────────────────────────────────┤
│  Tool Layer  (pure Python CLI, no LLM dependency)         │
│  ├── cad_spec_gen.py    → spec extraction                 │
│  ├── bom_parser.py      → BOM parsing                     │
│  └── config/templates/  → subsystem configs               │
└──────────────────────────────────────────────────────────┘
```

## Pipeline Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                   CAD Hybrid Rendering Pipeline                 │
│                                                                 │
│  1. SPEC EXTRACTION (this repo)                                 │
│     Design doc (.md) → cad_spec_gen.py → CAD_SPEC.md            │
│     9 sections: params, tolerances, fasteners, connections,     │
│     BOM tree, assembly pose, visual IDs, render plan, gaps      │
│                                                                 │
│  2. PARAMETRIC MODELING                                         │
│     CAD_SPEC.md → CadQuery scripts → STEP + GLB + DXF          │
│     - 3D: assemblies with precise mate constraints              │
│     - 2D: GB/T A3 drawings, 3-view + section views              │
│                                                                 │
│  3. 3D RENDERING (Blender Cycles CPU)                           │
│     GLB → 5-view PNG (geometry 100% accurate)                   │
│     15 PBR material presets · spherical camera system            │
│     Standard views: front-iso / rear / side / exploded / ortho  │
│                                                                 │
│  4. AI ENHANCEMENT (optional)                                   │
│     PNG → photorealistic JPG (reskin only, geometry locked)     │
│     Prompt: "Keep ALL geometry EXACTLY" + material description  │
│                                                                 │
│  Output:  PNG → engineering review / machining reference        │
│           JPG → presentations / proposals / business plans      │
└────────────────────────────────────────────────────────────────┘
```

## Key Features

### Spec Extraction (`cad_spec_gen.py`)
- **9-section structured output**: parameters, tolerances, fasteners, connection matrix, BOM tree, assembly pose, visual IDs, render plan, completeness report
- **Idempotent**: MD5-based skip — won't regenerate if source unchanged
- **Auto-defaults**: standard bolt torques (8.8 grade), surface Ra by material type
- **Derived calculations**: total cost, part count, BOM completeness %
- **Configurable**: subsystem mapping via JSON config, no hardcoded paths

### Interactive Help (15 Intents)
- **Natural language** — no need to memorize CLI syntax, just ask in plain language
- **15 intents**: environment check, config validation, next-step recommendation, materials, camera, exploded view, rendering, AI enhancement, troubleshooting, file structure, status, cross-model integration, parts/BOM, CAD spec
- **Smart "what's next?"** — scans project artifacts (STEP/DXF/GLB/PNG/JPG) and recommends the highest-priority next action

### 2D Engineering Drawings
- **GB/T national standard**: first-angle projection, A3 sheet, title block
- **12-layer DXF** system with 0.5mm line widths per GB/T 17450
- **FangSong font**, 3.5mm annotation height
- Section views (A-A cut lines), datum triangles, default Ra callouts

### 3D Rendering
- **Blender Cycles CPU** — works on remote desktops without GPU
- **5 standard views**: V1 front-iso, V2 rear-oblique, V3 side-elevation, V4 exploded, V5 ortho-front
- **15 PBR material presets**: brushed aluminum, PEEK, carbon fiber, rubber, glass, etc.
- **Exploded views**: radial / axial / custom explosion with assembly lines
- **Config-driven**: `render_config.json` controls materials, cameras, explosion rules

### AI Enhancement (Hybrid Rendering)
- **Geometry-locked**: Blender PNG provides exact geometry; AI only changes surface appearance
- **Cross-view consistent**: all 5 views share the same 3D source
- **Dual output**: PNG for engineering, JPG for presentation
- **Prompt templates**: auto-generated from render config variables

## Quick Start

```bash
git clone https://github.com/proecheng/cad-spec-gen.git
cd cad-spec-gen

# Generate CAD spec from a design document
python cad_spec_gen.py examples/04-末端执行机构设计.md \
    --config config/gisbot.json \
    --output-dir ./output

# Check output
cat output/end_effector/CAD_SPEC.md
```

### AI Enhancement Quick Start

After Blender renders your 5-view PNGs, enhance them to photorealistic JPGs:

```bash
# Enhance standard views (V1/V2/V3) using prompt template
python gemini_gen.py --image V1_front_iso.png \
    "Keep ALL geometry EXACTLY unchanged. Apply photorealistic materials..."

# Enhance exploded view (V4) — preserves explosion gaps
python gemini_gen.py --image V4_exploded.png \
    "Keep ALL geometry EXACTLY unchanged. This is an exploded view..."

# Enhance orthographic view (V5) — no perspective distortion
python gemini_gen.py --image V5_ortho_front.png \
    "Keep ALL geometry EXACTLY unchanged. Front orthographic projection..."
```

3 prompt templates provided in `templates/`:
- `prompt_enhance.txt` — V1/V2/V3 standard views
- `prompt_exploded.txt` — V4 exploded view (preserves gaps)
- `prompt_ortho.txt` — V5 orthographic (no perspective)

Fill `{product_name}`, `{view_description}`, `{material_descriptions}` from `render_config.json`.
Output: ~6MB JPG per view, 5460×3072, photorealistic studio quality.

### Component Label Annotation

After AI enhancement, add component labels (Chinese/English) via PIL:

```bash
# Annotate single image with Chinese labels
python annotate_render.py V1_enhanced.jpg --config render_config.json --lang cn

# Batch annotate all views in both languages
python annotate_render.py --all --dir ./renders --config render_config.json --lang cn
python annotate_render.py --all --dir ./renders --config render_config.json --lang en
```

Labels are defined in `render_config.json`:
- `components` section: maps IDs to CN/EN names + BOM IDs (from design doc §X.8 BOM)
- `labels` section: per-view coordinates for **visible** components only (occluded = not labeled)
- Coordinates at 1920×1080 reference, auto-scaled to actual image size

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
```

### Process all subsystems at once

```bash
python cad_spec_gen.py --all --config config/gisbot.json --doc-dir docs/design
```

### BOM parser (standalone)

```bash
python bom_parser.py examples/04-末端执行机构设计.md          # tree view
python bom_parser.py examples/04-末端执行机构设计.md --json   # JSON output
python bom_parser.py examples/04-末端执行机构设计.md --summary # one-line summary
```

## Configuration

Create a JSON config file (see `config/gisbot.json` for a full 18-subsystem example):

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
    }
  }
}
```

## 15 PBR Material Presets

| Category | Presets |
|----------|---------|
| Metal | `brushed_aluminum` `polished_steel` `black_anodized` `cast_iron` `brass` `copper` `titanium` `raw_steel` |
| Plastic | `peek_natural` `nylon_white` `abs_dark_gray` |
| Other | `rubber_black` `glass_clear` `ceramic_white` `carbon_fiber` |

## Documentation

| Document | Language | Description |
|----------|----------|-------------|
| [System Prompt](system_prompt.md) | EN | Universal system prompt — paste into any LLM |
| [Skill Manifest](skill.json) | — | Machine-readable skill definition |
| [User Guide (English)](docs/cad-help-guide-en.md) | EN | Full feature walkthrough, 15 intents, workflows |
| [User Guide (Chinese)](docs/cad-help-guide-zh.md) | 中文 | 完整功能说明、15种意图、典型工作流 |
| [Agent Integration Guide](docs/cad_pipeline_agent_guide.md) | 中文 | LLM/Agent framework integration (GPT, GLM, LangChain, etc.) |
| [CAD Spec Template](templates/cad_spec_template.md) | — | Output format reference with all 9 sections |
| [AI Prompt Templates](templates/) | EN | 3 prompt templates for Gemini AI enhancement (standard/exploded/ortho) |

## Project Structure

```
├── skill.json                      # Machine-readable skill manifest
├── system_prompt.md                # Universal system prompt (any LLM)
├── skill_cad_help.md               # Skill knowledge (15 intents + actions)
├── install.py                      # Cross-platform installer
├── cad_spec_gen.py                 # Main generator (CLI entry point)
├── cad_spec_extractors.py          # 8 extraction functions + table parser
├── cad_spec_defaults.py            # Standard defaults & completeness rules
├── bom_parser.py                   # BOM table parser (also standalone CLI)
├── annotate_render.py              # PIL-based component label annotation (CN/EN)
├── adapters/
│   ├── claude-code/
│   │   ├── commands/cad-help.md    # Claude Code slash command
│   │   ├── commands/cad-spec.md    # Claude Code slash command
│   │   ├── commands/cad-enhance.md # Claude Code slash command (AI enhance)
│   │   └── install.sh             # One-click Claude Code installer
│   ├── openai/
│   │   ├── functions.json         # OpenAI Function Calling schema
│   │   └── README.md              # GPT-4 / Assistants setup guide
│   ├── langchain/
│   │   ├── tools.py               # LangChain Tool wrapper
│   │   └── README.md              # LangChain / AutoGen setup guide
│   └── dify/
│       └── README.md              # Dify / Coze setup guide
├── config/
│   └── gisbot.json                # Example: 18-subsystem config
├── templates/
│   ├── cad_spec_template.md       # Output template reference
│   ├── prompt_enhance.txt         # AI prompt: standard views (V1-V3)
│   ├── prompt_exploded.txt        # AI prompt: exploded view (V4)
│   └── prompt_ortho.txt           # AI prompt: orthographic view (V5)
├── examples/
│   └── 04-末端执行机构设计.md       # Example design document
└── docs/
    ├── cad-help-guide-en.md       # User guide (English)
    ├── cad-help-guide-zh.md       # User guide (Chinese)
    └── cad_pipeline_agent_guide.md # Cross-LLM agent integration guide
```

## License

MIT
