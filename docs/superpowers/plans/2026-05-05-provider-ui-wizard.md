# Provider UI Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a display-ready, read-only provider selection wizard in `PROJECT_GUIDE.json` so ordinary users, UI clients, and LLM agents can choose an enhancement provider without hand-writing backend arguments.

**Architecture:** Keep `project-guide` as the single read-only entry point. When the active run is at `ready_for_enhancement`, derive `provider_wizard` from the existing allowlisted `provider_choice.ordinary_user_options`; the wizard contains ordered steps, selectable cards, default selection, preview-only handoff commands, and confirmation boundaries. It does not execute enhancement, add providers, accept arbitrary provider ids, scan render directories, or expose secrets.

**Tech Stack:** Python 3.10+, existing `tools.project_guide`, `tools.photo3d_provider_presets`, `cad_pipeline.py`, pytest, `scripts/dev_sync.py`.

---

## File Map

| File | Responsibility |
| --- | --- |
| `tools/project_guide.py` | Build `provider_wizard` from `ordinary_user_options` only when `provider_choice` is valid for the current active run. |
| `tests/test_project_guide.py` | Prove wizard structure, option order, default selection, preview-only argv, no secret/config drift, and absence when provider choice is stale. |
| `tests/test_photo3d_user_flow.py` | Protect CLI help, docs, and skill metadata wording for provider wizard. |
| `cad_pipeline.py` | Document that `project-guide` writes a read-only `provider_wizard`. |
| `skill_cad_help.md`, `.claude/commands/cad-help.md`, `docs/cad-help-guide-zh.md`, `skill.json` | User/LLM docs and metadata for the wizard boundary. |
| `docs/PROGRESS.md`, `docs/superpowers/README.md` | Round-end board and index updates. |

## Contract

- `provider_wizard` appears only when `provider_choice` appears.
- Wizard options are derived from `provider_choice.ordinary_user_options`, not from arbitrary JSON, CLI input, environment variables, or directory scans.
- Wizard option ids remain `default`, `engineering`, `gemini`, `fal`, `fal_comfy`, `comfyui`.
- Every option includes display copy, `requires_setup`, `is_default`, and a preview action.
- Preview action uses `photo3d-handoff --provider-preset <id>` and does not include `--confirm`.
- Wizard states the confirmation boundary: selection previews the next command; execution still requires explicit handoff confirmation.
- No URL, endpoint, API key, secret, or unimplemented provider is exposed.

## Tasks

### Task 1: Red Tests For Wizard Structure

**Files:**
- Modify: `tests/test_project_guide.py`

- [ ] Extend `test_project_guide_exposes_provider_choices_when_ready_for_enhancement` to assert:
  - `report["provider_wizard"]["kind"] == "provider_preset_selection_wizard"`
  - `provider_wizard["source"] == "provider_choice.ordinary_user_options"`
  - `provider_wizard["mutates_pipeline_state"] is False`
  - `provider_wizard["executes_enhancement"] is False`
  - `provider_wizard["does_not_scan_directories"] is True`
  - `provider_wizard["default_provider_preset"] == "default"`
  - `provider_wizard["steps"]` has three ordered steps: choose provider, preview handoff, confirm outside the wizard.
  - `provider_wizard["options"]` has the same ids/order as `ordinary_user_options`.
  - The engineering option preview argv equals its ordinary-user argv and does not contain `--confirm`.
  - Every wizard option has no forbidden fields: `api_key`, `key`, `secret`, `url`, `base_url`, `endpoint`.
- [ ] Extend the stale report test to assert `provider_wizard` is also absent.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_project_guide.py::test_project_guide_exposes_provider_choices_when_ready_for_enhancement tests\test_project_guide.py::test_project_guide_ignores_stale_provider_choice_report -q
```

Expected: fail because `provider_wizard` is missing.

### Task 2: Minimal Wizard Implementation

**Files:**
- Modify: `tools/project_guide.py`

- [ ] Add `_provider_wizard(provider_choice)` that builds a stable dict from `ordinary_user_options`.
- [ ] Add `provider_wizard` beside `provider_choice` only when provider choice exists.
- [ ] Copy safe display fields only: ids, title, summary, recommendation, setup flag, confirmation flag, preview argv/cli.
- [ ] Mark the default option by comparing with `default_provider_preset`.
- [ ] Keep preview argv exactly as the ordinary-user option argv; do not append `--confirm`.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_project_guide.py -q
```

Expected: pass.

### Task 3: Help And Metadata

**Files:**
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `cad_pipeline.py`
- Modify: `skill_cad_help.md`
- Modify: `.claude/commands/cad-help.md`
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `skill.json`

- [ ] Extend user-flow tests to require `provider_wizard`.
- [ ] Update `project-guide --help` to mention the wizard is read-only, preview-only, and derived from `ordinary_user_options`.
- [ ] Update cad-help docs and skill metadata with the same boundary.
- [ ] Run `python scripts/dev_sync.py` after metadata/help changes.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py -q
```

Expected: pass.

### Task 4: Verify, Board, Merge, Cleanup

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_project_guide.py tests\test_photo3d_provider_presets.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
git diff --check
```

Update `docs/PROGRESS.md` and `docs/superpowers/README.md`, commit, merge to `main`, repeat the same scoped verification, push, remove `.worktrees/provider-ui-wizard`, delete `codex/provider-ui-wizard`, and prune worktrees.

## Self Review

- Scope is generic and not product-specific.
- No provider execution behavior changes.
- No new backend, key, URL, endpoint, or model name enters the whitelist.
- The wizard is derived from existing allowlisted options and is safe for UI/LLM consumption.
