# Render Quality Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic Phase 4 Blender preflight and screenshot/pixel quality report so ordinary users and LLM agents can verify render environment and rendered image quality before enhancement.

**Architecture:** Create a new `render-quality-check` command instead of expanding `render-visual-check`; the former owns Blender environment and pixel evidence, while the latter remains the component/view contract gate. The new tool reads only `ARTIFACT_INDEX.json.active_run_id` and same-run `render_manifest.json`, writes `RENDER_QUALITY_REPORT.json` under the active run directory, and never scans render folders for newest images.

**Tech Stack:** Python 3.10+, Pillow image statistics, `subprocess.run` for Blender `--version`, existing `artifact_index`, `contract_io`, `path_policy`, `render_qa`, `dev_sync.py`, pytest.

---

### Task 1: Active-Run Render Quality Tool

**Files:**
- Create: `tools/render_quality_check.py`
- Test: `tests/test_render_quality_check.py`

- [x] **Step 1: Write failing tests**

Add tests that:
- A valid active run with a fake Blender version runner writes `RENDER_QUALITY_REPORT.json`, status `pass`, `blender_preflight.status == "pass"`, and per-view `pixel_metrics`.
- A missing Blender path blocks with `blender_not_found`.
- A low-contrast render stays active-run bound and returns `warning` with `render_quality_low_contrast`.
- A render file hash drift blocks with `render_file_hash_mismatch`.
- Manifest `run_id` drift keeps the report bound to `ARTIFACT_INDEX.json.active_run_id`.
- Render directory drift blocks with `render_dir_not_active_run`.

- [x] **Step 2: Run tests to verify RED**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_render_quality_check.py -q`

Expected: import or assertion failures because `tools.render_quality_check` does not exist.

- [x] **Step 3: Implement minimal tool**

Create `tools/render_quality_check.py` with:
- `run_render_quality_check(project_root, subsystem, artifact_index_path=None, output_path=None, blender_path=None, version_runner=None)`
- `command_return_code_for_render_quality_check(report)`
- Active-run artifact loading through `ARTIFACT_INDEX.json`.
- Blender preflight: path present, executable exists, `--background --version` return code zero, parsed version string.
- Per-view pixel metrics: width, height, object occupancy, luminance mean, contrast stddev, saturation mean, edge density.
- Blocking only for hard failures: missing active artifacts, wrong subsystem/run, render file missing/outside current render dir/hash drift, render QA failure, Blender missing/unusable.
- Warning for visual quality concerns: low contrast, low edge density, inconsistent canvas.
- Output path must remain inside `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/`.
- `ARTIFACT_INDEX.json.active_run_id` remains the report/output anchor even if `render_manifest.json.run_id` drifts.

- [x] **Step 4: Run tests to verify GREEN**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_render_quality_check.py -q`

Expected: all new render quality tests pass.

### Task 2: CLI, Metadata, Packaged Mirrors

**Files:**
- Modify: `cad_pipeline.py`
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `tests/test_photo3d_packaging_sync.py`
- Modify: `skill.json`

- [x] **Step 1: Write failing CLI/docs tests**

Add assertions that:
- `python cad_pipeline.py render-quality-check --help` mentions `RENDER_QUALITY_REPORT.json`, Blender preflight, pixel quality, and active run.
- Skill metadata has a `render_quality_check` tool with the expected CLI.
- Packaged mirrors include `render_quality_check.py`.

- [x] **Step 2: Run tests to verify RED**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q`

Expected: help/metadata/mirror assertions fail before CLI and metadata updates.

- [x] **Step 3: Implement CLI and metadata**

In `cad_pipeline.py`:
- Add `cmd_render_quality_check(args)`.
- Add `render-quality-check` parser with `--subsystem`, `--artifact-index`, `--blender`, and `--output`.
- Add it to the command dispatch table.

In `skill.json`:
- Add `render_quality_check` tool metadata.
- Update cad-help description to include `RENDER_QUALITY_REPORT.json`.

In `tests/test_photo3d_packaging_sync.py`:
- Add `render_quality_check.py` to the mirrored Photo3D/Phase 4 contract tool set.

- [x] **Step 4: Sync generated mirrors**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py`

- [x] **Step 5: Run scoped verification**

Run:
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check`
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_render_quality_check.py tests\test_render_visual_regression.py tests\test_render_qa.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q`
- `git diff --check`

Expected: all pass.

### Task 3: User-Facing Docs And Board

**Files:**
- Modify: `.claude/commands/cad-help.md`
- Modify: `skill_cad_help.md`
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`

- [x] **Step 1: Write failing docs assertions**

Extend existing user-flow docs assertions to require:
- `render-quality-check`
- `RENDER_QUALITY_REPORT.json`
- `blender_preflight`
- `pixel_metrics`

- [x] **Step 2: Run docs tests to verify RED**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py -q`

Expected: docs assertions fail until command docs and mirrors are updated.

- [x] **Step 3: Update docs and board**

Document:
- `render-visual-check` = view/component contract evidence.
- `render-quality-check` = Blender environment and screenshot/pixel evidence.
- The new report is deterministic evidence, not semantic AI inspection.
- The command is active-run bound and does not scan directories or switch runs.

- [x] **Step 4: Sync mirrors and verify**

Run:
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py`
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check`
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_render_quality_check.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q`
- `git diff --check`

Expected: all pass.

---

## Self-Review

- Spec coverage: The plan adds Blender preflight, screenshot/pixel evidence, active-run binding, CLI/docs/metadata/mirrors, and board updates.
- Placeholder scan: No TBD/TODO placeholders remain.
- Type consistency: `RENDER_QUALITY_REPORT.json`, `blender_preflight`, `render_quality_summary`, and `pixel_metrics` are named consistently across tasks.
