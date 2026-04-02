# Release v2.1.2 — Auto DXF→PNG + gemini_gen.py Integration

**Date:** 2026-04-02

## Highlights

1. **Post-build auto DXF→PNG rendering** — `cad_pipeline.py build` now automatically runs `render_dxf.py` after `build_all.py`, converting all GB/T 2D engineering drawings (DXF) to PNG preview images. Skipped gracefully if `render_dxf.py` does not exist in the subsystem directory; failure is non-fatal (DXF files are still available).

2. **gemini_gen.py included in repo** — The Gemini image generation script is now shipped with the skill. Previously it was an external dependency requiring manual installation. Supports OpenAI-compatible API proxies with configurable `~/.claude/gemini_image_config.json`. Output always saved as JPG for consistency.

3. **Skill format migration guide** — Documentation now covers both legacy `.claude/commands/` format and the recommended `~/.claude/skills/*/SKILL.md` global registration method.

## Code Changes

### cad_pipeline.py
- Added post-build DXF→PNG step in `cmd_build()` (lines 720-731)
- Auto-detects `render_dxf.py` in subsystem dir after `build_all.py` completes
- Non-fatal: logs warning on failure, does not block pipeline

### gemini_gen.py (NEW)
- OpenAI-compatible `/v1/chat/completions` endpoint for Gemini image editing
- Supports `--prompt-file`, `--image`, `--reference`, `--model`, `--seed`, `--temperature`
- Reads config from `~/.claude/gemini_image_config.json`
- Cloudflare-compatible User-Agent header
- Always outputs JPG (converts from any API response format via Pillow)
- Stdout protocol: `图片已保存: <path>` for pipeline integration

### pipeline_config.json
- `enhance.model` field now accepts raw Gemini API model IDs directly (e.g., `gemini-3-pro-image-preview`) in addition to abstract keys from the `models` dict

## Documentation Updates

| File | Change |
|------|--------|
| `system_prompt.md` | Phase 3 BUILD description now includes DXF→PNG post-build step |
| `skill_cad_help.md` | Render section clarifies auto DXF→PNG; technical constraints updated |
| `skill_mech_design.md` | Phase 6 build_all.py note added for DXF→PNG auto-trigger |
| `skill.json` | v2.1.2; gemini_gen.py description corrected; Phase 3 stages updated; pipeline overview updated |
| `README.md` | Pipeline flowchart includes DXF→PNG step; gemini_gen.py in file tree; skill registration guide |
| `.cad_skill_version.json` | All checksums refreshed; gemini_gen.py entry added |
| `.claude/commands/cad-help.md` | Phase 3 scan logic updated; build constraint added |

## Pipeline Phase 3 BUILD (updated flow)

```
orientation_check.py       (GATE-3: axis validation)
    ↓ pass
build_all.py               (STEP + DXF + GLB generation)
    ↓ success
render_dxf.py              (DXF → PNG auto-conversion)  ← NEW
```

## Upgrade

```bash
pip install --upgrade cad-spec-gen
cad-skill-setup --update
```

## Files Changed

| File | Status |
|------|--------|
| `cad_pipeline.py` | Modified |
| `gemini_gen.py` | **New** |
| `pipeline_config.json` | Modified |
| `skill.json` | Modified |
| `system_prompt.md` | Modified |
| `skill_cad_help.md` | Modified |
| `skill_mech_design.md` | Modified |
| `README.md` | Modified |
| `.cad_skill_version.json` | Modified |
| `RELEASE_v2.1.2.md` | **New** |
