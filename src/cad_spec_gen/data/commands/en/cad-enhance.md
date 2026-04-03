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
[WARN] Stable Diffusion base model not found → recommend downloading realisticVisionV60B1.safetensors
```

When components are missing, the script outputs the corresponding download/install commands.

### ComfyUI How It Works

- Auto-generates a depth map (MiDaS) + canny edge map for each PNG
- These two control images constrain SD generation — **geometry is hard-locked by the images**, independent of text prompts
- Submits workflow JSON via `localhost:8188` REST API and polls for results
- Workflow template located at `templates/comfyui_workflow_template.json`

### Layout Routing (v2.0)

`prompt_data_builder.py` auto-routes prompt data generation based on subsystem layout type:

| `render_config.json` `layout.type` | Route | Behavior |
|-------------------------------------|-------|----------|
| `radial` (or params.py contains `STATION_ANGLES`/`MOUNT_CENTER_R`) | `_generate_radial_prompt_data()` | Full 4-station descriptions, N1-N10 constraints, standard parts list (end-effector specific) |
| `linear` / `cartesian` / `custom` | `_generate_generic_prompt_data()` | Material descriptions derived from `rc["materials"]` only; `assembly_description`/`negative_constraints`/`standard_parts` use **user-written values** from render_config.json |

Non-radial subsystems (e.g., lifting_platform) do **not** inject any end-effector-specific terminology (flange, PEEK, station, cable chain, etc.), preventing Gemini from hallucinating phantom parts.

### Multi-View Consistency (v2.1)

Four-layer consistency defense for the Gemini backend:

1. **Viewpoint Lock**
   - `enhance_prompt.py`'s `_camera_to_view_description()` auto-computes azimuth/elevation from camera location vectors in `render_config.json`
   - Each view gets a unique description, e.g. "rear-left oblique view at 25° elevation, 222° azimuth (50mm perspective)"
   - Prompt template opens with `VIEWPOINT & GEOMETRY LOCK — HIGHEST PRIORITY`

2. **Image Role Separation (IMAGE ROLES)**
   - Source image placed **first** in the content array (locks composition), reference image placed **second** (provides material style only)
   - Prompt explicitly instructs: "Image 1 = SOURCE — preserve EXACT viewpoint; Image 2 = STYLE REFERENCE ONLY"
   - Style anchor text no longer contains phrases like "match lighting angle" that could contaminate viewpoint

3. **V1-anchor Reference Image**
   - V1 enhanced result serves as the material style reference for subsequent views (`reference_mode: "v1_anchor"`)
   - Reference image conveys only material texture and color, not viewpoint
   - Reference image compressed to 1280×720 q90

4. **Source Image High-Fidelity**
   - Source images ≤4MB are sent uncompressed — original 1920×1080 PNG (~1.5MB) sent as-is
   - Full spatial detail preserved, helping Gemini recognize the source viewpoint

**Related config (pipeline_config.json):**
```json
"enhance": {
  "temperature": 0.2,
  "seed_from_image": true,
  "reference_mode": "v1_anchor"
}
```

### Core Principles

- **Viewpoint Lock**: Prompt opens with "Preserve the EXACT camera angle, viewpoint, and framing"; each view includes specific azimuth/elevation; IMAGE ROLES clearly separate source composition from reference style
- **Geometry Lock**: Gemini mode — prompt says "Keep ALL geometry EXACTLY unchanged"; ComfyUI mode — enforced by ControlNet hard constraints
- **Material Source**: All material descriptions read from render_config.json `prompt_vars` and `materials` — never fabricated
- **Layout Awareness**: Non-radial layout subsystems do not inject hardcoded part descriptions

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
  "checkpoint": "realisticVisionV60B1_v51VAE.safetensors",
  "controlnet_depth_model": "control_v11f1p_sd15_depth.pth",
  "controlnet_canny_model": "control_v11p_sd15_canny.pth",
  "steps": 28,
  "cfg_scale": 7.0,
  "denoise_strength": 0.55,
  "timeout": 300
}
```
