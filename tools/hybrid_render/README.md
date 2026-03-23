# Hybrid Rendering Pipeline — Universal Toolkit

Data-driven Blender + Gemini AI rendering for any mechanical subsystem.

## Quick Start (3 steps)

```bash
# 1. Check environment
python tools/hybrid_render/check_env.py

# 2. Validate config (dry-run, no Blender needed)
python tools/hybrid_render/validate_config.py cad/end_effector/render_config.json

# 3. Render all views
blender.exe -b -P cad/end_effector/render_3d.py -- \
    --config cad/end_effector/render_config.json --all
```

## Full Workflow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
│ CadQuery     │───>│ GLB assembly │───>│ Blender     │───>│ PNG      │
│ (parametric) │    │ (.glb file)  │    │ Cycles CPU  │    │ (exact)  │
└─────────────┘    └──────────────┘    └─────────────┘    └────┬─────┘
                                                               │
                                                               v
                                                         ┌──────────┐
                                                         │ Gemini AI│
                                                         │ --image  │
                                                         └────┬─────┘
                                                               │
                                                               v
                                                         ┌──────────┐
                                                         │ JPG      │
                                                         │ (photo-  │
                                                         │  real)   │
                                                         └──────────┘
```

**Key principle**: Blender renders geometry-exact PNG; Gemini only enhances materials/lighting ("reskins"), never modifies geometry.

## Configuration System

Each subsystem has one `render_config.json` with 5 sections:

| Section | Purpose |
|---------|---------|
| `subsystem` | Name, part prefix, GLB file, bounding radius |
| `materials` | Part name patterns → PBR material presets + overrides |
| `camera` | Named view presets (Cartesian or spherical coordinates) |
| `explode` | Explosion rules: radial, linear, or custom displacement |
| `prompt_vars` | Product name + material descriptions for Gemini prompts |

### Creating a config for a new subsystem

1. Copy `docs/templates/render_config_template.json` to `cad/<subsystem>/render_config.json`
2. Fill in subsystem name, GLB filename, bounding radius
3. Map part name patterns to material presets
4. Define camera views (see Camera Modes below)
5. Validate: `python tools/hybrid_render/validate_config.py cad/<subsystem>/render_config.json`

### Backward compatibility

The `--config` flag is optional. Without it, render scripts use their hardcoded defaults (end effector values). This ensures existing workflows are not broken.

## Material Presets (15 built-in)

| Preset | Color | Metallic | Roughness | Use case |
|--------|-------|----------|-----------|----------|
| `brushed_aluminum` | Silver | 1.0 | 0.18 | Machined aluminum parts |
| `anodized_blue` | Blue | 0.85 | 0.22 | Color-coded modules |
| `anodized_green` | Green | 0.85 | 0.22 | Color-coded modules |
| `anodized_purple` | Purple | 0.85 | 0.22 | Color-coded modules |
| `anodized_red` | Red | 0.85 | 0.22 | Color-coded modules |
| `black_anodized` | Black | 0.85 | 0.30 | Housings, covers |
| `bronze` | Bronze | 0.90 | 0.25 | Decorative/copper alloy |
| `copper` | Copper | 1.0 | 0.15 | Electrical contacts |
| `gunmetal` | Dark gray | 0.90 | 0.25 | Drive assemblies |
| `dark_steel` | Dark | 0.90 | 0.28 | Motor housings |
| `stainless_304` | Bright silver | 1.0 | 0.15 | Stainless steel parts |
| `peek_amber` | Amber | 0.0 | 0.30 | PEEK plastic (SSS) |
| `black_rubber` | Black | 0.0 | 0.75 | Rubber/elastomer |
| `white_nylon` | White | 0.0 | 0.45 | 3D printed parts |
| `polycarbonate_clear` | Clear | 0.0 | 0.05 | Transparent covers |

Override any preset value in the config:

```json
{
  "cover": {
    "preset": "anodized_blue",
    "overrides": { "roughness": 0.35 },
    "label": "Cover plate (rougher finish)"
  }
}
```

## Camera Modes

Two coordinate systems supported, auto-detected:

**Cartesian** (explicit position):
```json
{
  "name": "V1_front_iso",
  "location": [500, -500, 350],
  "target": [0, 0, 100],
  "description": "Front-left isometric"
}
```

**Spherical** (angle-based):
```json
{
  "name": "V2_rear_oblique",
  "azimuth_deg": 135,
  "elevation_deg": 40,
  "distance_factor": 2.5,
  "description": "Rear-right overhead"
}
```

Orthographic mode: add `"ortho": true, "ortho_scale": 500`.

Camera distance auto-scales with `bounding_radius_mm`.

## Capability Levels

Detected by `check_env.py`:

| Level | Name | Tools Required | Output |
|-------|------|----------------|--------|
| 5 | FULL | CadQuery + ezdxf + matplotlib + Blender + Gemini | Full pipeline |
| 4 | RENDER | CadQuery + Blender | STEP/GLB + 3D renders |
| 3 | CAD | CadQuery + ezdxf | STEP + 2D DXF drawings |
| 2 | IMPORT | Pre-built GLB files | Manual Blender import |
| 1 | MINIMAL | Python only | Prompt text for manual use |

```bash
# Check your level
python tools/hybrid_render/check_env.py

# Machine-readable output
python tools/hybrid_render/check_env.py --json
```

## Explode Views

Three explosion types:

- **radial**: Stations displaced outward along mounting angles
- **linear**: Parts displaced along a single axis
- **custom**: Per-part displacement vectors

```bash
blender.exe -b -P cad/end_effector/render_exploded.py -- \
    --config cad/end_effector/render_config.json \
    --spread 80 --z-spread 60
```

CLI flags override config values which override hardcoded defaults.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `check_env.py` shows wrong level | Ensure you run with the Python that has cadquery installed |
| Materials not applied | Check part name patterns in config match GLB object names (case-insensitive) |
| Camera too close/far | Adjust `bounding_radius_mm` in config (auto-detected from GLB as fallback) |
| Blender not found | Set `BLENDER_PATH` env var or install to `tools/blender/` |
| Lighting too bright/dim | Energy auto-scales with bounding radius; check `bounding_radius_mm` |

## File Structure

```
tools/hybrid_render/
├── README.md              # This file
├── check_env.py           # Environment detector (Level 1-5)
├── validate_config.py     # Config dry-run validator
└── render_config.py       # Config engine (also in cad/end_effector/)

cad/<subsystem>/
├── render_config.json     # Per-subsystem rendering config
├── render_config.py       # Config engine (stdlib-only, Blender-safe)
├── render_3d.py           # Blender renderer (--config flag)
└── render_exploded.py     # Exploded view renderer (--config flag)

docs/templates/
├── render_config_template.json    # Blank config template
└── rendering_data_template.md     # §X.10 rendering data template (6 tables)
```

## For AI Coding Assistants

This toolkit is designed to work with any AI coding assistant (Claude Code, Cursor, Windsurf, Codex, etc.):

1. **Config is self-documenting**: `render_config_template.json` has `_comment` fields
2. **CLI is self-documenting**: All scripts support `--help`
3. **No proprietary dependencies**: stdlib Python + Blender (free) + optional Gemini
4. **Dry-run validation**: `validate_config.py` catches errors without launching Blender
5. **Graceful degradation**: Works at whatever capability level is available

### New subsystem checklist

- [ ] Create `cad/<name>/render_config.json` from template
- [ ] Set `subsystem.glb_file` to your assembly GLB filename
- [ ] Map part patterns to material presets in `materials` section
- [ ] Define at least V1 (isometric) camera view
- [ ] Run `validate_config.py` to verify
- [ ] Add `--config render_config.json` to your render commands
- [ ] (Optional) Fill `prompt_vars` for Gemini AI enhancement
- [ ] (Optional) Fill `explode` rules for exploded view
