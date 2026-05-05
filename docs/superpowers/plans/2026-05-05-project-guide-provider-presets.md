# Project Guide Provider Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `project-guide` expose ordinary-user enhancement provider choices when the current Photo3D state is ready for enhancement, without mutating pipeline state or trusting arbitrary JSON argv.

**Architecture:** Keep `project-guide` read-only. It will continue to select the safe top-level `photo3d-run` handoff for an active run, and, when the active run's current Photo3D report says `ready_for_enhancement`, attach a provider preset choice block plus safe `photo3d-handoff --provider-preset <id>` commands built from the same whitelist used by handoff. It must not run enhancement, accept baseline, scan render directories, or pick a cloud provider silently.

**Tech Stack:** Python 3.10+, existing `tools.project_guide`, shared `tools.photo3d_provider_presets`, pytest, `scripts/dev_sync.py`.

---

## File Map

| File | Responsibility |
| --- | --- |
| `tools/project_guide.py` | Read current run's `PHOTO3D_RUN.json` / `PHOTO3D_AUTOPILOT.json` and expose provider choices only for `ready_for_enhancement`. |
| `tests/test_project_guide.py` | Prove provider choices appear only at enhancement handoff and remain path/run bound. |
| `cad_pipeline.py` | Help text for project-guide provider choices if needed. |
| `skill_cad_help.md`, `.claude/commands/cad-help.md`, `docs/cad-help-guide-zh.md`, `skill.json` | User/LLM docs and metadata. |
| `docs/PROGRESS.md`, `docs/superpowers/README.md` | Round-end board and index. |

## Contract

- `project-guide` remains read-only except writing `PROJECT_GUIDE.json`.
- Provider choices appear only when the current active-run source report has `status == "ready_for_enhancement"` and `next_action.kind == "run_enhancement"`.
- Choices are built from `public_provider_presets()`.
- The recommended executable boundary is still `photo3d-handoff`, not direct `enhance`.
- The choice block must include safe argv examples:

```json
{
  "kind": "select_enhancement_provider",
  "default_provider_preset": "default",
  "provider_presets": [...],
  "handoff_actions": [
    {
      "provider_preset": "engineering",
      "argv": [
        "python",
        "cad_pipeline.py",
        "photo3d-handoff",
        "--subsystem",
        "demo",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
        "--provider-preset",
        "engineering"
      ]
    }
  ]
}
```

- `project-guide` must not accept arbitrary provider ids from JSON or CLI in this increment.
- It must not add `--confirm` to examples; confirmation remains a separate user boundary.

## Tasks

### Task 1: Red Tests

**Files:**
- Modify: `tests/test_project_guide.py`

- [x] Add `PHOTO3D_RUN.json` fixture with `status: ready_for_enhancement`, `run_id: RUN001`, and `next_action.kind: run_enhancement`.
- [x] Assert `write_project_guide()` still returns `status == "ready_for_photo3d_run"` and `next_action.kind == "run_photo3d_guide"`.
- [x] Assert `report["provider_choice"]["kind"] == "select_enhancement_provider"`.
- [x] Assert provider ids are `default`, `engineering`, `gemini`, `fal`, `fal_comfy`, `comfyui`.
- [x] Assert the engineering handoff argv uses `photo3d-handoff --artifact-index cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json --provider-preset engineering`.
- [x] Add a negative test where `PHOTO3D_RUN.json` belongs to a stale run; assert `provider_choice` is absent.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_project_guide.py -q
```

Expected: fail because `provider_choice` is missing.

### Task 2: Minimal Implementation

**Files:**
- Modify: `tools/project_guide.py`

- [x] Import `DEFAULT_PROVIDER_PRESET` and `public_provider_presets`.
- [x] Add helper `_provider_choice(root, subsystem, run_dir, index_path, active_run_id)`.
- [x] Helper reads `PHOTO3D_RUN.json` first, then `PHOTO3D_AUTOPILOT.json`; if no file, mismatched run/subsystem, or non-enhancement status/action, return `None`.
- [x] Helper returns provider choice dict and preview `photo3d-handoff` argv per preset.
- [x] Add `provider_choice` to top-level report only when helper returns a dict.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_project_guide.py -q
```

Expected: pass.

### Task 3: User Help And Metadata

**Files:**
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `cad_pipeline.py`
- Modify: `skill_cad_help.md`
- Modify: `.claude/commands/cad-help.md`
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `skill.json`

- [x] Extend user-flow tests to require `project-guide` docs mention provider preset choices and `photo3d-handoff --provider-preset`.
- [x] Update CLI help epilog to mention that `PROJECT_GUIDE.json` may expose read-only provider choices and safe handoff commands.
- [x] Update docs/metadata with the same boundary: read-only, no enhancement execution, no arbitrary backend.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py -q
```

Expected: pass.

### Task 4: Sync, Verify, Board, Merge

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
git diff --check
```

Update `docs/PROGRESS.md` and `docs/superpowers/README.md`, commit, merge to `main`, repeat the same verification, push, and clean `.worktrees/project-guide-provider-presets` plus branch.

## Self Review

- Scope is generic, not product-specific.
- No new backend, key, URL, or model name is added.
- `project-guide` stays read-only and does not execute enhancement.
- All provider ids come from the shared whitelist.
