# v2.1.1 — PROJECT_ROOT Path Separation

## Highlights

Output paths (2D drawings, specs, renders) were hardcoded to the skill installation directory (`SKILL_ROOT`), causing all projects to write output into `D:/cad-skill/` regardless of the user's working directory. This release introduces `PROJECT_ROOT` — a separate path concept that directs user-facing output to the correct project directory.

## What's New

### SKILL_ROOT / PROJECT_ROOT Separation

| Path | Purpose | Resolution |
|------|---------|------------|
| `SKILL_ROOT` | Templates, scripts, tools (immutable) | `__file__` directory |
| `PROJECT_ROOT` | Output, design docs (user project) | `CAD_PROJECT_ROOT` env var → `os.getcwd()` |

When running from a user project directory (e.g., `D:/jiehuo/docs/`), output now correctly goes to that project's `cad/output/` instead of the skill's internal directory.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAD_PROJECT_ROOT` | `os.getcwd()` | User project root |
| `CAD_OUTPUT_DIR` | `PROJECT_ROOT/cad/output` | Output directory |
| `BLENDER_PATH` | `SKILL_ROOT/tools/blender/blender.exe` | Blender executable |
| `GEMINI_GEN_PATH` | Sibling `imageProduce/gemini_gen.py` | Gemini script |

### Hardcoded Path Removal

- Removed `D:/cad-skill/tools/blender/blender.exe` from `cad_paths.py` and `pipeline_config.json`
- Removed `D:/imageProduce/gemini_gen.py` from `cad_paths.py`
- `render_dxf.py` now respects `CAD_OUTPUT_DIR` env var (consistent with all other render scripts)

## Code Changes

- **`cad_paths.py`**: Added `PROJECT_ROOT`, updated `get_output_dir()` / `get_subsystem_dir()` defaults, rewrote `get_gemini_script()` to use sibling directory search
- **`cad_pipeline.py`**: 4 path references changed from `SKILL_ROOT` → `PROJECT_ROOT` (design doc, spec output, init output, init doc)
- **`pipeline_config.json`**: `blender_path` changed to relative `tools/blender/blender.exe`
- **`render_dxf.py`**: `OUTPUT_DIR` supports `CAD_OUTPUT_DIR` env var

## Documentation Updates

- **Agent guide**: New §3.0d "路径体系 — SKILL_ROOT vs PROJECT_ROOT" with env var table
- **README**: Updated `cad_paths.py` description
- **Checksums**: 11 entries updated in `.cad_skill_version.json`

## Files Changed (12 files)

**Code (source + root sync):**
- `src/cad_spec_gen/data/python_tools/cad_paths.py`
- `src/cad_spec_gen/data/python_tools/cad_pipeline.py`
- `src/cad_spec_gen/data/python_tools/pipeline_config.json`
- `cad/end_effector/render_dxf.py`

**Documentation:**
- `docs/cad_pipeline_agent_guide.md`
- `README.md`

**Metadata:**
- `skill.json` → v2.1.1
- `.cad_skill_version.json` → v2.1.1
- `pyproject.toml` → v2.1.1
- `src/cad_spec_gen/__init__.py` → v2.1.1

## Backward Compatibility

Non-breaking. When `cwd == SKILL_ROOT` (the previous typical usage), behavior is identical to v2.1.0.

## Install / Upgrade

```bash
pip install --upgrade cad-spec-gen
cad-skill-setup    # re-register to pick up v2.1.1
```
