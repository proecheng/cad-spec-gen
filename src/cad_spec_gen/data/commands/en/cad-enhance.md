# /cad-enhance — Gemini AI Enhancement (Blender PNG → Photo-Realistic JPG)

User input: $ARGUMENTS

## Instructions

Enhance Blender Cycles rendered PNG images into photo-realistic JPGs. Geometry is 100% locked — only surface material appearance is changed.

### Routing Rules

1. **No arguments** → Show usage:
   ```
   /cad-enhance <png_path>                    — Enhance a single image
   /cad-enhance --all --dir <render_dir>      — Enhance all V*.png in directory
   /cad-enhance --view V1 --dir <render_dir>  — Enhance specific view
   ```

2. **With arguments** → Execute enhancement:
   - Read the target subsystem's `render_config.json` for material descriptions (`prompt_vars.material_descriptions`)
   - Select prompt template based on filename:
     - V1/V2/V3 → `templates/prompt_enhance.txt`
     - V4 → `templates/prompt_exploded.txt`
     - V5 → `templates/prompt_ortho.txt`
   - Fill template placeholders with variables from render_config.json
   - Execute `python gemini_gen.py --image <input.png> "<filled prompt>"` (gemini_gen.py path located via `which gemini_gen.py` or env var `GEMINI_GEN_PATH`)
   - Copy output JPG to same directory as input PNG, named `*_enhanced.jpg`

### Core Principles

- **Geometry lock**: First line of prompt must state "Keep ALL geometry EXACTLY unchanged"
- **Material source**: All material descriptions read from render_config.json `prompt_vars`, never fabricated
- **View consistency**: Different views use different templates — exploded views preserve spacing, orthographic views have no perspective

### Standard Parts Enhancement

Prompt templates include `{standard_parts_description}` placeholder, filled from `render_config.json`'s `standard_parts` array:

```json
"standard_parts": [
  {"visual_cue": "Small cylinder (Φ22×68mm) under flange", "real_part": "Maxon ECX motor, silver housing..."},
  {"visual_cue": "Annular rings at bearing locations", "real_part": "MR105ZZ ball bearing, chrome steel..."}
]
```

Gemini receives simplified geometry location + real part appearance description, enhancing simplified shapes to realistic look. If `standard_parts` is empty, placeholder is replaced with empty string — no impact on existing workflow.

### Model Selection

`pipeline_config.json` `enhance` section configures Gemini model:

```json
"enhance": {
  "model": "nano_banana_2",
  "models": {
    "nano_banana": "gemini-2.5-flash-image",
    "nano_banana_pro": "gemini-3-pro-image-preview",
    "nano_banana_2": "gemini-3.1-flash-image"
  }
}
```

- `model` field selects current model alias
- `models` dict maps alias → Gemini API model ID
- Passed via `--model <id>` argument to `gemini_gen.py`
- Switch models by changing `pipeline_config.json` `model` value only
