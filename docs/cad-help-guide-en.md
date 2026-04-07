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
| 4 | New Subsystem | "how to start a new subsystem?" "init" | Quick Start guide + `init` scaffold command |
| 5 | Materials | "what materials?" "colors" | List 15 PBR engineering material presets + custom examples |
| 6 | Camera | "how to configure camera?" "views" | Spherical / Cartesian coords + N configurable views |
| 7 | Exploded View | "how to set up exploded view?" | radial / axial / custom explosion configuration |
| 8 | Render | "how to render?" "generate images" | Auto-detect state, run Blender or guide through prerequisites |
| 9 | AI Enhancement | "how to enhance?" "photorealistic" "which backend?" | 4-backend AI enhancement: gemini / fal / comfyui / engineering |
| 10 | Troubleshoot | "error" "it failed" | Troubleshooting guide for 8 common issues |
| 11 | File Structure | "where are the files?" | Complete directory tree of the rendering pipeline |
| 12 | Status | "current progress?" | Scan subsystem STEP/DXF/GLB/PNG/JPG artifact counts |
| 13 | Integration | "how to use with other LLMs?" | Cross-framework guide for GLM, GPT, LangChain, etc. |
| 14 | Parts/BOM | "what parts?" "BOM list" | Auto-extract part tree from design docs, with make/buy and cost stats |
| 15 | CAD Spec | "generate spec" "extract parameters" | Run cad_spec_gen.py to produce CAD_SPEC.md |
| 16 | Design Review | "review design" "check design" "审查" | Engineering review: mechanical/assembly/material/completeness → DESIGN_REVIEW.md |

### v2.3.0 New Capabilities

- **Feature Extraction**: Auto-extracts per-part hole/slot features by cross-referencing §2 tolerances, §3 fasteners, §4 connections, §8 assembly sequence
- **Section View Overlay**: Auto-generates A-A section hatch on left view for parts with internal features (holes excluded from hatch per GB/T 4457.5)
- **Position Dimensions**: Hole-center-to-edge distance annotations in top view (GB/T 4458.4)
- **Orthogonal Dim Angles**: Dimension leader lines default to 0°/90°/180°/270° (was 45°/135°)
- **Dynamic Tech Notes**: Technical notes position calculated from layout, placed below views (was hardcoded top-left)
- **Unified Material Appearance**: `MATERIAL_PRESETS` in `render_config.py` is single source of truth for both Blender PBR and AI prompt descriptions
- **View-Aware Material Emphasis**: AI prompt adjusts Fresnel/specular/diffuse emphasis per camera angle
- **material_type → preset Fallback**: Auto-derives render preset from params.py material_type when render_config.json lacks materials
- **Render Passes (preview)**: Optional depth/normal/diffuse pass output from Blender (schema ready, default disabled)
- **Triple-Backend Enhance (v2.3)**: Four backends for AI enhancement — gemini (cloud, ~$0.02/img), fal (fal.ai Flux ControlNet, ~$0.20/img, hard geometry lock), comfyui (local GPU, free), engineering (Blender PBR direct, free, perfect geometry). Auto-detect priority: FAL_KEY→fal, ComfyUI→comfyui, gemini→gemini, else→engineering. Fallback chain: fal→gemini→engineering. CLI: `--backend gemini|fal|comfyui|engineering`

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  CAD Hybrid Rendering Pipeline                │
│                                                               │
│  Design Document (.md)                                        │
│      ↓ cad_spec_gen.py --review (optional, recommended)       │
│  DESIGN_REVIEW.md (A.mechanical / B.assembly incl. B5-B8     │
│    connection checks / C.material / D.completeness)           │
│      ↓ User: "继续审查" / "自动补全" (--auto-fill) / "下一步"    │
│      ↓ Parameter extraction                                   │
│  CadQuery Parametric Modeling → STEP + DXF + GLB              │
│      ↓                                                        │
│  Blender Cycles CPU Rendering → N-view PNG (100% accurate, default 5)  │
│      ↓                                                        │
│  AI Enhancement (4 backends) → Photorealistic JPG (reskin)    │
│    gemini | fal | comfyui | engineering (auto-detect)         │
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
| Gemini API | — | AI image enhancement (gemini backend) | For gemini backend |
| FAL_KEY env var | — | fal.ai Flux ControlNet (fal backend) | For fal backend |
| ComfyUI | localhost:8188 | Local ControlNet (comfyui backend) | For comfyui backend |
| FangSong font | — | GB/T standard drawings | For 2D drawings |

Run `/cad-help check environment` to detect all dependencies at once.

## Tool Scripts

```
cad/end_effector/
├── build_all.py           One-click build (--render triggers Blender)
├── render_3d.py           Blender 5-view rendering (--config --all)
├── render_exploded.py     Exploded view rendering (--config --spread)
├── render_dxf.py          DXF → PNG conversion
├── render_config.json     Render config (materials/cameras/explode rules/standard parts)
└── render_config.py       Config engine (15 material presets)

codegen/                   Code generators (CAD_SPEC.md → scaffold code)
├── gen_params.py          §1 params → params.py
├── gen_build.py           §5 BOM → build_all.py (incl. std parts build table)
├── gen_parts.py           §5 leaf parts → station_*.py scaffolds
├── gen_assembly.py        §4+§5+§6 → assembly.py (incl. std parts)
└── gen_std_parts.py       §5 purchased → std_*.py simplified geometry (9 categories)

tools/hybrid_render/
├── check_env.py           Environment check (--json)
├── validate_config.py     Config validation (<config.json>)
└── prompt_builder.py      Prompt template generator (--config --type)

tools/
└── bom_parser.py          BOM part tree parser (--json --summary)

# Gemini AI tool (user-configured path)
# gemini_gen.py             Gemini image generation (--image png --model <id> "prompt")
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
# 0. Scaffold a new subsystem (for brand-new projects)
python cad_pipeline.py init --subsystem my_device --name-cn 我的设备 --prefix GIS-MD
# → Generates: output/my_device/render_config.json, params.py, docs/design/XX-my_device.md

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

After Blender renders exist, enhance all views to photorealistic JPGs. Four backends are available:

| Backend | Cost | Geometry Lock | GPU Required | Best For |
|---------|------|---------------|--------------|----------|
| `gemini` | ~$0.02/img | Soft (prompt) | No (cloud) | Quick iteration, no GPU |
| `fal` | ~$0.20/img | Hard (depth+canny) | No (cloud) | Best quality, geometry-critical |
| `comfyui` | Free | Hard (ControlNet) | Yes (8GB+) | Offline, full control |
| `engineering` | Free | Perfect (no AI) | No | Budget zero, geometry-only |

**Auto-detect priority**: FAL_KEY env var → ComfyUI running on localhost:8188 → Gemini config → engineering fallback.
**Fallback chain**: fal → gemini → engineering (batch-locked after downgrade to ensure cross-view consistency).

```bash
# Auto-detect best backend
python cad_pipeline.py enhance --subsystem <name>

# Force a specific backend
python cad_pipeline.py enhance --subsystem <name> --backend fal
python cad_pipeline.py enhance --subsystem <name> --backend engineering

# Also works on full pipeline
python cad_pipeline.py full --subsystem <name> --backend gemini
```

**Key principles:**
- Viewpoint lock (v2.1): prompt opens with "Preserve EXACT camera angle, viewpoint, framing"; each view includes computed azimuth/elevation
- Geometry lock: gemini — prompt constraint; fal/comfyui — ControlNet depth+canny hard constraint; engineering — perfect (no AI transform)
- Multi-view consistency: source image FIRST (locks composition) + reference SECOND (style only) + V1-anchor + source uncompressed (≤4MB)
- Material descriptions come from `render_config.json` `prompt_vars`
- Standard parts enhancement descriptions come from `render_config.json` `standard_parts` array (`{standard_parts_description}` placeholder)
- Layout awareness: non-radial subsystems do not inject hardcoded part descriptions
- 1 unified template auto-switches by camera type (standard / exploded / ortho)
- Model selection: `pipeline_config.json` `enhance.model` field selects Gemini model alias
- Timestamp versioning: files named `V*_viewname_YYYYMMDD_HHMM_enhanced.ext` to prevent overwriting

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

Label data sources:
- `render_config.json` `components` section: maps IDs to CN/EN names + BOM IDs (from design doc §X.8 BOM)
- `render_config.json` `labels` section: per-view leader line endpoints `label:[x,y]` for visible components
- **Anchor coordinates** are auto-generated during rendering (`render_label_utils.py` computes visible-pixel centroids via Object Index Mask), written to `<VN>_<name>_labels.json` sidecar files. The annotate phase uses sidecar anchors first, ensuring anchors always land on the component

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
