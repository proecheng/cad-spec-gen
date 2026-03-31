# /cad-enhance — AI Enhancement (Blender PNG → Photorealistic JPG)

User input: $ARGUMENTS

## Instructions

Enhance Blender Cycles rendered PNG images into photorealistic JPG. Geometry is 100% locked — only surface material appearance is changed.

Supports two backends: **Gemini** (cloud API, no GPU required) and **ComfyUI** (local, requires GPU, stronger multi-view consistency).

### Routing Rules

1. **No arguments** → Show usage:
   ```
   /cad-enhance <subsystem>                           — enhance all views in current manifest
   /cad-enhance <subsystem> --backend gemini          — force Gemini backend
   /cad-enhance <subsystem> --backend comfyui         — force ComfyUI backend
   /cad-enhance --env-check                           — check if ComfyUI environment is ready
   ```

2. **With arguments but no `--backend`** → Ask user to choose backend:

   Read `pipeline_config.json` `enhance.backend` current value, then show:

   ```
   Current default backend: <backend> (from pipeline_config.json)

   Choose enhancement backend:
   A. Gemini (recommended) — Cloud API, no GPU needed, works out of the box
   B. ComfyUI              — Local GPU, ControlNet geometry lock, stronger multi-view consistency (requires 8GB+ GPU)
   C. Keep default (<backend>)
   ```

   - User selects A → use `gemini` backend
   - User selects B → run `python comfyui_env_check.py` first; if ready, proceed; if components missing, show install guide and ask whether to continue
   - User selects C or presses Enter → use current default backend
   - User reply contains `gemini` / `A` → use gemini
   - User reply contains `comfyui` / `B` → use comfyui

3. **With arguments and `--backend` specified** → Skip prompt, execute enhancement directly:
   - If `--backend comfyui`: run `python comfyui_env_check.py` first; if not ready, show install guide and ask whether to continue
   - Read `render_config.json` for the subsystem to get material descriptions (`prompt_vars.material_descriptions`)
   - Use unified prompt template `templates/prompt_enhance_unified.txt`
     - Auto-switch view-specific content based on `camera.V*.type` field in `render_config.json`
     - `prompt_data_builder.py` auto-generates material/assembly/constraint data from `params.py`
   - Rename output files to `V*_viewname_YYYYMMDD_HHMM_enhanced.ext` (same directory as source PNG); timestamp prevents overwriting history

### Backend Selection

| Backend | Use Case | Dependencies | Consistency |
|---------|----------|-------------|-------------|
| `gemini` | No GPU / quick trial | Gemini API Key | Medium (AI may occasionally shift viewpoint) |
| `comfyui` | Multi-view consistency | Local 8GB+ GPU, ComfyUI + ControlNet | High (depth+canny geometry hard-lock) |

**Switch backend (three methods, priority high to low):**

```bash
# 1. CLI argument (temporary)
python cad_pipeline.py enhance --subsystem end_effector --backend comfyui

# 2. Edit pipeline_config.json (persistent)
"enhance": { "backend": "comfyui" }

# 3. Default is gemini, no change needed
```

### ComfyUI Environment Check

Before using ComfyUI for the first time, run:

```bash
python comfyui_env_check.py
```

Sample output:
```
[OK]  GPU: NVIDIA RTX 3080 (CUDA 12.1)
[OK]  ComfyUI service running (localhost:8188)
[OK]  ControlNet model: control_v11p_sd15_depth.pth
[OK]  ControlNet model: control_v11p_sd15_canny.pth
[WARN] Checkpoint: realisticVisionV60B1_v51VAE.safetensors not found
       → Download from CivitAI and place in ComfyUI/models/checkpoints/
```

If `[WARN]` or `[FAIL]` items are present, the tool shows targeted installation instructions.

### Execution Commands

```bash
# Gemini backend
python cad_pipeline.py enhance --subsystem end_effector --backend gemini

# ComfyUI backend
python cad_pipeline.py enhance --subsystem end_effector --backend comfyui

# Enhance specific directory
python cad_pipeline.py enhance --subsystem end_effector --backend gemini \
  --dir cad/output/end_effector/20240315_143022/
```

### Unified Prompt Template

All enhancements use `templates/prompt_enhance_unified.txt` — a single template covering all view types:

```
[SYSTEM]
You are an industrial product visualization expert. ...

[TASK]
Enhance this Blender render into a photorealistic product image.

[GEOMETRY LOCK — CRITICAL]
Do NOT change: part shapes, dimensions, proportions, assembly relationships, camera angle, ...

[VIEW TYPE: {view_type}]
{view_specific_instructions}

[MATERIAL]
{material_descriptions}

[ASSEMBLY]
{assembly_context}
```

`prompt_data_builder.py` automatically fills `{material_descriptions}`, `{assembly_context}` and other placeholders from `params.py` at runtime (in-memory, no disk write).

### View Type Dispatch

Based on `camera.V*.type` in `render_config.json`, the template auto-selects view-specific instructions:

| View Type | Instructions Focus |
|-----------|-------------------|
| `perspective` | Global material quality, lighting realism |
| `orthographic` | No perspective distortion, engineering accuracy |
| `exploded` | Preserve part spacing, show assembly relationships |
| `section` | Interior structure visible, cut surface material |

Each view type uses a different template segment to ensure exploded views retain spacing and orthographic views have no perspective.

### Standard Parts Enhancement

The prompt template includes a `{standard_parts_description}` placeholder filled from the `standard_parts` array in `render_config.json`:

```json
"standard_parts": [
  {"visual_cue": "Small cylinder (Φ22×68mm) under flange", "real_part": "Maxon ECX motor, silver housing..."},
  {"visual_cue": "Annular rings at bearing locations", "real_part": "MR105ZZ ball bearing, chrome steel..."}
]
```

Both backends use this description. If `standard_parts` is empty, the placeholder is replaced with an empty string without affecting the existing workflow.

### Gemini Model Selection

Configure the Gemini model in the `enhance` section of `pipeline_config.json`:

```json
"enhance": {
  "backend": "gemini",
  "model": "nano_banana_4k",
  "models": {
    "nano_banana": "gemini-2.5-flash-image",
    "nano_banana_pro": "gemini-3-pro-image-preview",
    "nano_banana_2": "gemini-3.1-flash-image",
    "nano_banana_4k": "gemini-3-pro-image-preview-4k"
  }
}
```

- `model` field selects the current model alias
- `models` dict maps alias → Gemini API model ID
- Passed to `gemini_gen.py` via `--model <id>` parameter
- To switch models, only change the `model` value in `pipeline_config.json`

### ComfyUI Configuration

```json
"comfyui": {
  "host": "127.0.0.1",
  "port": 8188,
  "workflow_template": "templates/comfyui_workflow_template.json",
  "sd_model": "realisticVisionV60B1.safetensors",
  "controlnet_depth": "control_v11p_sd15_depth.pth",
  "controlnet_canny": "control_v11p_sd15_canny.pth",
  "steps": 28,
  "cfg_scale": 7.0,
  "denoise_strength": 0.55,
  "timeout": 300
}
```
