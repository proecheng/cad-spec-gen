# CAD Spec Generator — A Claude Code Skill

> **From Markdown to machining-ready drawings and photorealistic renders — in one command.**

A **Claude Code Skill** for the complete AI-assisted CAD pipeline. Install it in any project, type `/cad-help` or `/cad-spec`, and let Claude handle everything: extract specs from design docs, generate GB/T-compliant 2D drawings, produce geometrically accurate 3D renders, and create photorealistic presentation images.

## What is a Claude Code Skill?

[Claude Code Skills](https://docs.anthropic.com/en/docs/claude-code) are reusable slash commands that extend Claude's capabilities. Once installed, you can:

```
/cad-help                           # Smart assistant — "what should I do next?"
/cad-help what materials are available?  # Natural language queries
/cad-spec examples/04-*.md         # Generate structured CAD spec
/cad-spec --all                    # Process all subsystems at once
```

### Install as a Claude Code Skill

```bash
# 1. Clone into your project (or as a standalone tool)
git clone https://github.com/proecheng/cad-spec-gen.git

# 2. Copy slash commands into your project's .claude/commands/
cp -r cad-spec-gen/.claude/commands/* your-project/.claude/commands/

# 3. Copy skill knowledge file
cp cad-spec-gen/skill_cad_help.md your-project/

# 4. Now use /cad-help and /cad-spec in Claude Code!
```

Or use standalone without Claude Code — all tools are plain Python CLI scripts.

```
Design Document (.md)
    ↓ cad_spec_gen.py — extract 9 categories of structured data
CAD_SPEC.md (single source of truth for all downstream CAD work)
    ↓ CadQuery parametric modeling
STEP + DXF (GB/T national-standard 2D drawings) + GLB
    ↓ Blender Cycles CPU rendering
5-view PNG — 100% geometry-accurate, cross-view consistent
    ↓ Gemini AI enhancement (reskin only, geometry locked)
Photorealistic JPG — presentation / defense / business plan ready
```

## Why This Tool?

| Pain Point | How We Solve It |
|------------|----------------|
| Design docs have scattered parameters, tolerances, BOM across 600+ lines | **One command** extracts all 9 data categories into a single structured spec |
| Pure text-to-image AI gets ~42% geometry accuracy | **Hybrid pipeline**: Blender renders exact geometry first, AI only "reskins" the surface |
| "What should I do next?" is hard to answer in a complex pipeline | **`/cad-help` natural-language assistant** scans your project artifacts and recommends the next action |
| Cross-view consistency is poor with AI-generated images | **Blender-first** approach locks geometry across all 5 standard views; AI inherits consistency |
| 2D drawings don't follow national standards | **GB/T compliant**: first-angle projection, FangSong font, 12-layer DXF with 0.5mm line widths |
| Hard to integrate with other LLMs (GPT, GLM, Qwen...) | **LLM-agnostic**: pure Python CLI tools — any agent with shell execution can drive the pipeline |

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
│  4. AI ENHANCEMENT (Gemini, optional)                           │
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

### Interactive Help (`/cad-help`)
- **Natural language** — no need to memorize CLI syntax, just ask in plain language
- **14 intents**: environment check, config validation, next-step recommendation, materials, camera, exploded view, rendering, AI enhancement, troubleshooting, file structure, status, cross-model integration, parts/BOM
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
- **Geometry-locked**: Blender PNG provides exact geometry; Gemini only changes surface appearance
- **Cross-view consistent**: all 5 views share the same 3D source
- **Dual output**: PNG for engineering, JPG for presentation
- **Prompt templates**: auto-generated from render config variables

### Cross-Model Integration
- **LLM-agnostic**: all tools are plain Python CLI scripts
- Works with GPT-4, GLM-4, Qwen, LangChain, AutoGen, Dify — anything with shell execution
- Agent integration guide included (`docs/cad_pipeline_agent_guide.md`)

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
| [User Guide (English)](docs/cad-help-guide-en.md) | EN | Full feature walkthrough, 14 intents, workflows |
| [User Guide (Chinese)](docs/cad-help-guide-zh.md) | 中文 | 完整功能说明、14种意图、典型工作流 |
| [Agent Integration Guide](docs/cad_pipeline_agent_guide.md) | 中文 | LLM/Agent framework integration (GPT, GLM, LangChain, etc.) |
| [CAD Spec Template](templates/cad_spec_template.md) | — | Output format reference with all 9 sections |

## Project Structure

```
├── .claude/
│   └── commands/
│       ├── cad-help.md              # Skill: /cad-help slash command
│       └── cad-spec.md              # Skill: /cad-spec slash command
├── skill_cad_help.md                # Skill knowledge (14 intents + actions)
├── cad_spec_gen.py                  # Main generator (CLI entry point)
├── cad_spec_extractors.py           # 8 extraction functions + table parser
├── cad_spec_defaults.py             # Standard defaults & completeness rules
├── bom_parser.py                    # BOM table parser (also standalone CLI)
├── config/
│   └── gisbot.json                  # Example: 18-subsystem GISBOT config
├── templates/
│   └── cad_spec_template.md         # Output template reference
├── examples/
│   └── 04-末端执行机构设计.md         # Example design document
└── docs/
    ├── cad-help-guide-en.md         # User guide (English)
    ├── cad-help-guide-zh.md         # User guide (Chinese)
    └── cad_pipeline_agent_guide.md  # Cross-LLM agent integration guide
```

## License

MIT
