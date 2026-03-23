# /cad-help — Interactive CAD Hybrid Rendering Pipeline Assistant

A natural-language-driven assistant for the CAD rendering pipeline. No need to memorize command syntax — just ask questions in plain language to check environments, validate configs, render images, troubleshoot issues, and more.

## Quick Start

```
/cad-help                              # Show help panel
/cad-help what do I need to install?   # Environment check
/cad-help what should I do next?       # Smart recommendation
/cad-help what materials are available? # View 15 PBR presets
/cad-help what parts in end effector?  # Parts/BOM parsing
/cad-help how to integrate with other LLMs? # Cross-model guide
```

## Feature Overview

`/cad-help` supports **16 intents** covering the entire CAD hybrid rendering pipeline lifecycle:

| # | Intent | Trigger Examples | Description |
|---|--------|-----------------|-------------|
| 1 | Environment Check | "what do I need?" "check env" | Detect 7 dependencies: Python, CadQuery, Blender, Gemini, etc. |
| 2 | Validate Config | "validate config" "is my config correct?" | Check render_config.json completeness (6 checks) |
| 3 | Next Step | "what's next?" "what should I do?" | Scan project artifacts, recommend next action by priority |
| 4 | New Subsystem | "how to start a new subsystem?" | Quick Start 3-step guide |
| 5 | Materials | "what materials?" "colors" | List 15 PBR engineering material presets + custom examples |
| 6 | Camera | "how to configure camera?" "views" | Spherical / Cartesian coords + N configurable views |
| 7 | Exploded View | "how to set up exploded view?" | radial / axial / custom explosion configuration |
| 8 | Render | "how to render?" "generate images" | Auto-detect state, run Blender or guide through prerequisites |
| 9 | AI Enhancement | "how to use Gemini?" "photorealistic" | Gemini image-to-image hybrid enhancement workflow |
| 10 | Troubleshoot | "error" "it failed" | Troubleshooting guide for 8 common issues |
| 11 | File Structure | "where are the files?" | Complete directory tree of the rendering pipeline |
| 12 | Status | "current progress?" | Scan subsystem STEP/DXF/GLB/PNG/JPG artifact counts |
| 13 | Integration | "how to use with other LLMs?" | Cross-framework guide for GLM, GPT, LangChain, etc. |
| 14 | Parts/BOM | "what parts?" "BOM list" | Auto-extract part tree from design docs, with make/buy and cost stats |
| 15 | CAD Spec | "generate spec" "extract parameters" | Run cad_spec_gen.py to produce CAD_SPEC.md |
| 16 | Design Review | "review design" "check design" "审查" | Engineering review: mechanical/assembly/material/completeness → DESIGN_REVIEW.md |

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  CAD Hybrid Rendering Pipeline                │
│                                                               │
│  Design Document (.md)                                        │
│      ↓ cad_spec_gen.py --review (optional, recommended)       │
│  DESIGN_REVIEW.md (mechanical/assembly/material/completeness) │
│      ↓ User: iterate ("继续审查") or proceed ("下一步")          │
│      ↓ Parameter extraction                                   │
│  CadQuery Parametric Modeling → STEP + DXF + GLB              │
│      ↓                                                        │
│  Blender Cycles CPU Rendering → N-view PNG (100% accurate, default 5)  │
│      ↓                                                        │
│  Gemini AI Enhancement → Photorealistic JPG (reskin only)     │
│                                                               │
│  PNG → Engineering review / machining reference               │
│  JPG → Presentations / proposals / business plans             │
└──────────────────────────────────────────────────────────────┘
```

## Requirements

| Component | Version | Purpose | Required? |
|-----------|---------|---------|-----------|
| Python | 3.10+ | Run all scripts | Yes |
| CadQuery | 2.x | Parametric 3D modeling | Yes |
| ezdxf | 0.18+ | 2D engineering drawings (DXF) | Yes |
| matplotlib | 3.x | DXF → PNG conversion | Yes |
| Blender | 4.x LTS | Cycles CPU rendering | For 3D rendering |
| Gemini API | — | AI image enhancement | For AI enhancement |
| FangSong font | — | GB/T standard drawings | For 2D drawings |

Run `/cad-help check environment` to detect all dependencies at once.

## Tool Scripts

```
cad/end_effector/
├── build_all.py           One-click build (--render triggers Blender)
├── render_3d.py           Blender 5-view rendering (--config --all)
├── render_exploded.py     Exploded view rendering (--config --spread)
├── render_dxf.py          DXF → PNG conversion
├── render_config.json     Render config (materials/cameras/explode rules)
└── render_config.py       Config engine (15 material presets)

tools/hybrid_render/
├── check_env.py           Environment check (--json)
├── validate_config.py     Config validation (<config.json>)
└── prompt_builder.py      Prompt template generator (--config --type)

tools/
└── bom_parser.py          BOM part tree parser (--json --summary)

# Gemini AI tool (user-configured path)
# gemini_gen.py             Gemini image generation (--image png "prompt")
```

## 15 Material Presets

| Category | Preset Name | Description | Appearance |
|----------|-------------|-------------|------------|
| Metal | brushed_aluminum | Brushed Aluminum | Silver, metallic=1.0 |
| | stainless_304 | Stainless Steel 304 | Bright silver |
| | black_anodized | Black Anodized Aluminum | Deep black |
| | dark_steel | Dark Steel | Dark gray |
| | bronze | Bronze | Golden-brown |
| | copper | Copper | Reddish-copper |
| | gunmetal | Gunmetal | Dark blue-gray |
| | anodized_blue | Blue Anodized | Metallic blue |
| | anodized_green | Green Anodized | Metallic green |
| | anodized_purple | Purple Anodized | Metallic purple |
| | anodized_red | Red Anodized | Metallic red |
| Plastic | peek_amber | PEEK Amber | Amber, semi-transparent |
| | white_nylon | Nylon White | White |
| | black_rubber | Black Rubber | Black, roughness=0.85 |
| | polycarbonate_clear | Polycarbonate Clear | Transparent |

## Typical Workflows

### Build & Render from Scratch

> **Example: End Effector subsystem** — adapt paths for your own subsystem.

```bash
# 1. Check environment
python tools/hybrid_render/check_env.py

# 2. Build + render
python cad/end_effector/build_all.py --render
# → Output: 8 STEP + 11 DXF + 1 GLB + 5 PNG

# 3. AI enhancement (optional) — use prompt templates
python gemini_gen.py \
  --image cad/output/renders/V1_front_iso.png \
  "Keep ALL geometry EXACTLY unchanged. Apply photorealistic materials..."
# → Output: photorealistic JPG (~6MB, 5460×3072)
```

### AI Enhancement Workflow (all configured views)

After Blender renders exist, enhance all views to photorealistic JPGs:

```bash
# Step 1: Read render_config.json for material descriptions
cat cad/end_effector/render_config.json | jq '.prompt_vars'

# Step 2: Fill prompt template and run for each view
# V1/V2/V3 → templates/prompt_enhance.txt (standard views)
python gemini_gen.py --image V1_front_iso.png \
  "Keep ALL geometry EXACTLY unchanged. This is a front-left isometric view
   of a precision robotic end effector. Apply photorealistic materials:
   - Silver flange: brushed aluminum 7075-T6
   - Amber ring: PEEK translucent
   - Blue/Green/Bronze/Purple stations: anodized aluminum
   Studio lighting, neutral gradient background. 8K quality."

# V4 → templates/prompt_exploded.txt (preserves explosion gaps)
python gemini_gen.py --image V4_exploded.png \
  "Keep ALL geometry EXACTLY unchanged. Exploded view — keep gaps visible..."

# V5 → templates/prompt_ortho.txt (no perspective distortion)
python gemini_gen.py --image V5_ortho_front.png \
  "Keep ALL geometry EXACTLY unchanged. Front orthographic projection..."
```

**Key principles:**
- Prompt line 1 MUST say "Keep ALL geometry EXACTLY unchanged"
- Material descriptions come from `render_config.json` `prompt_vars`
- 3 templates for different view types (standard / exploded / ortho)
- Output: ~6MB JPG per view, photorealistic studio quality

### Component Label Annotation (CN/EN)

After AI enhancement, add component labels programmatically via PIL (Chinese text is NOT AI-generated):

```bash
# Annotate single image with Chinese labels
python annotate_render.py V1_enhanced.jpg \
  --config cad/end_effector/render_config.json --lang cn

# Batch annotate all views (Chinese)
python annotate_render.py --all --dir assets/images/mechanical \
  --config cad/end_effector/render_config.json --lang cn

# Batch annotate all views (English)
python annotate_render.py --all --dir assets/images/mechanical \
  --config cad/end_effector/render_config.json --lang en
```

Label data in `render_config.json` has two sections:
- `components`: maps IDs to CN/EN names + BOM IDs (sourced from design doc §X.8 BOM)
- `labels`: per-view coordinates for **visible** components only (occluded components not labeled)

### Render Only (GLB already exists)

```bash
# All standard views
tools/blender/blender.exe -b -P cad/end_effector/render_3d.py -- \
  --config cad/end_effector/render_config.json --all

# Exploded view
tools/blender/blender.exe -b -P cad/end_effector/render_exploded.py -- \
  --config cad/end_effector/render_config.json
```

## Cross-Model Integration

The underlying tools are plain Python scripts — **any LLM or Agent framework with shell execution capability can drive the entire pipeline**.

| Framework | Integration Method |
|-----------|--------------------|
| GLM-4 | Load universal guide as system prompt + Function Calling with `run_shell` |
| GPT-4 / Assistants | Upload knowledge file + Code Interpreter |
| LangChain | `ShellTool()` + universal guide as system_message |
| AutoGen | Register shell executor + universal guide |
| Dify | Import to knowledge base + code execution node |

Universal Agent integration guide: [`tools/cad_pipeline_agent_guide.md`](tools/cad_pipeline_agent_guide.md)

### Minimal Integration (2 Steps)

```python
# 1. Feed knowledge to your LLM
guide = open("tools/cad_pipeline_agent_guide.md").read()

# 2. Give the LLM shell execution capability
# → The LLM follows the guide to call: build_all.py → render_3d.py → gemini_gen.py
```

## Related Commands

| Command | Description |
|---------|-------------|
| `/cad-help` | This help (natural language CAD pipeline assistant) |
| `/mechdesign` | Parametric mechanical subsystem full workflow |
| `/text-to-image` | Gemini text-to-image / image-to-image |
| `gishelp` | Project-level assistant |

## License

This is part of the GISBOT GIS Partial Discharge Detection Robot CAD toolchain.
