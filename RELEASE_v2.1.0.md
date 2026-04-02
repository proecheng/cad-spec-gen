# v2.1.0 — Multi-View Consistency for Gemini Enhancement

## Highlights

Gemini AI enhancement now preserves source image viewing angles across all views. Previously, all enhanced images came back as front-isometric regardless of input viewpoint. This release implements a **four-layer consistency defense** that ensures V1 (front), V2 (rear), V3 (side), V4 (ortho), etc. each maintain their correct camera angle after enhancement.

## What's New

### Multi-View Consistency (4-layer defense)

| Layer | Mechanism | Implementation |
|-------|-----------|----------------|
| 1. Viewpoint Lock | Auto-compute azimuth/elevation from camera vectors | `enhance_prompt.py` → `_camera_to_view_description()` |
| 2. Image Role Separation | Source image FIRST (locks composition), reference SECOND (style only) | `gemini_gen.py` content array order |
| 3. V1-anchor Reference | V1 enhanced result serves as material style reference for V2-VN | `cad_pipeline.py` → `reference_mode: "v1_anchor"` |
| 4. Source High-Fidelity | Source images ≤4MB sent uncompressed (original 1920x1080 PNG) | `_compress_for_api()` threshold raised to 4MB |

### Code Changes

- **`enhance_prompt.py`**: New `_camera_to_view_description()` function computes human-readable view descriptions (e.g., "rear-left oblique view at 25° elevation, 222° azimuth (50mm perspective)") from `render_config.json` camera location vectors. Rewrote `_build_consistency_rules()` style anchor text to explicitly exclude viewpoint contamination.

- **`prompt_enhance_unified.txt`**: Complete rewrite — opens with `VIEWPOINT & GEOMETRY LOCK — HIGHEST PRIORITY`, adds `{image_roles}` and `{view_camera_description}` placeholders, explicit "Change ONLY surface textures" instruction.

- **`gemini_gen.py`**: Swapped multi-image input order from [reference, source, text] to [source, reference, text]. Source image now positioned first to lock composition.

- **`cad_pipeline.py`**: `_compress_for_api()` threshold raised from 300KB to 4MB — Blender PNGs (~1.5MB) are sent as-is without lossy compression. Reference image compression changed from 960x540/q82 to 1280x720/q90.

### Documentation Updates

All skill documentation updated to reflect v2.1 changes:

- Command docs: `cad-enhance.md` (zh/en/active) — new "Multi-View Consistency" section
- Knowledge files: `skill_cad_help_en.md`, `skill_cad_help_zh.md` — updated core principles (5 items)
- System prompt: `system_prompt.md` — Phase 5 key principles updated
- Architecture docs: `pipeline_architecture.md` — Phase 5 flow diagram updated
- Agent guide: `cad_pipeline_agent_guide.md` — new v2.1 consistency table
- Help guides: `cad-help-guide-en.md`, `cad-help-guide-zh.md` — key principles updated

## Root Causes Addressed

1. **`view_descriptions` empty** → all views described as "isometric view" in prompt → fixed by auto-computing from camera vectors
2. **V1 reference image contaminated composition** → Gemini copied V1's viewpoint, not just style → fixed by image order swap + explicit IMAGE ROLES
3. **Source images over-compressed** → 1.5MB PNG → 23KB JPEG, spatial detail lost → fixed by raising threshold to 4MB
4. **Prompt lacked explicit camera angle language** → no anchor/delta separation → fixed by computed azimuth/elevation per view
5. **Style anchor text too vague** → "match lighting angle" misinterpreted as "match viewpoint" → fixed by rewriting to explicitly exclude viewpoint

## Files Changed (25 files, +1149 / -648)

**Code (source + root sync):**
- `src/cad_spec_gen/data/python_tools/enhance_prompt.py`
- `src/cad_spec_gen/data/python_tools/cad_pipeline.py`
- `src/cad_spec_gen/data/python_tools/pipeline_config.json`
- `src/cad_spec_gen/data/templates/prompt_enhance_unified.txt`
- `gemini_gen.py` (external tool at `D:/imageProduce/`)

**Documentation:**
- `src/cad_spec_gen/data/commands/{zh,en}/cad-enhance.md`
- `src/cad_spec_gen/data/knowledge/skill_cad_help_{en,zh}.md`
- `src/cad_spec_gen/data/system_prompt.md`
- `docs/pipeline_architecture.md`
- `docs/cad_pipeline_agent_guide.md`
- `docs/cad-help-guide-{en,zh}.md`

**Metadata:**
- `skill.json` → v2.1.0
- `.cad_skill_version.json` → v2.1.0 (10 checksums updated)

## Configuration

New/updated fields in `pipeline_config.json`:

```json
"enhance": {
  "temperature": 0.2,
  "seed_from_image": true,
  "reference_mode": "v1_anchor"
}
```

## Requirements

- Python >= 3.10
- Jinja2 >= 3.0
- Optional: `cadquery`, `ezdxf`, `matplotlib`, `Pillow`, Blender 4.x, Gemini API

## Install / Upgrade

```bash
pip install --upgrade cad-spec-gen
cad-skill-setup    # re-register to pick up v2.1 commands
```
