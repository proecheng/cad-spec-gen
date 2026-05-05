# Provider Choice User Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make enhancement provider presets directly usable by ordinary users and LLM agents as stable, user-readable choices instead of only backend-flavored CLI options.

**Architecture:** Keep provider execution strictly tied to the existing whitelist in `tools/photo3d_provider_presets.py`. Add presentation metadata to each preset and expose a derived `ordinary_user_options` list in `PROJECT_GUIDE.json`; do not add new providers, URLs, API keys, model names, or execution paths.

**Tech Stack:** Python 3.10+, pytest, existing Photo3D/project-guide reports, `scripts/dev_sync.py`.

---

## File Map

| File | Responsibility |
| --- | --- |
| `tools/photo3d_provider_presets.py` | Source of truth for provider preset ids plus ordinary-user title, summary, setup hint, and recommendation text. |
| `tools/project_guide.py` | Convert preset metadata plus safe preview argv into `provider_choice.ordinary_user_options`. |
| `tests/test_photo3d_provider_presets.py` | Prove every preset has stable user-facing copy and no unsafe executable metadata. |
| `tests/test_project_guide.py` | Prove `PROJECT_GUIDE.json` exposes display-ready provider options while keeping preview handoff commands safe. |
| `docs/cad-help-guide-zh.md`, `skill_cad_help.md`, `.claude/commands/cad-help.md`, `cad_pipeline.py`, `skill.json` | User/LLM help text for choosing provider preset by readable option. |
| `docs/PROGRESS.md`, `docs/superpowers/README.md` | Round-end board and index. |

## Contract

- Provider ids remain `default`, `engineering`, `gemini`, `fal`, `fal_comfy`, `comfyui`.
- No `gpt-image-2-pro`, OpenClaude URL, API key, arbitrary backend, or future model is added.
- Every public preset includes:
  - `ordinary_user_title`
  - `ordinary_user_summary`
  - `recommended_when`
  - `requires_setup`
- `project-guide.provider_choice.ordinary_user_options` is display-ready and ordered the same as `provider_presets`.
- Each ordinary-user option includes `provider_preset`, display copy, `requires_setup`, `requires_user_confirmation`, `argv`, and safe `cli` only when the subsystem token is safe.
- `project-guide` remains read-only and preview-only; `ordinary_user_options` must not include `--confirm`.

## Tasks

### Task 1: Red Tests For Provider Preset Copy

**Files:**
- Create: `tests/test_photo3d_provider_presets.py`

- [x] Add a test that calls `public_provider_presets()` and asserts each preset contains `ordinary_user_title`, `ordinary_user_summary`, `recommended_when`, and `requires_setup`.
- [x] Assert `default` reads as a default/project-config option, `engineering` reads as an offline/local engineering preview, and cloud presets are marked as requiring setup.
- [x] Assert no preset contains unsafe keys such as `api_key`, `base_url`, `url`, or `secret`.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_provider_presets.py -q
```

Expected: fail because the new user-copy fields are absent.

### Task 2: Red Tests For Project Guide Options

**Files:**
- Modify: `tests/test_project_guide.py`

- [x] Extend `test_project_guide_exposes_provider_choices_when_ready_for_enhancement` to assert `provider_choice.ordinary_user_options` exists.
- [x] Assert the option ids are the same as `provider_presets`.
- [x] Assert the `engineering` option has a user title/summary/recommendation and preview `photo3d-handoff --provider-preset engineering` argv without `--confirm`.
- [x] Assert cloud options expose `requires_setup == True`.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_project_guide.py::test_project_guide_exposes_provider_choices_when_ready_for_enhancement -q
```

Expected: fail because `ordinary_user_options` is absent.

### Task 3: Minimal Implementation

**Files:**
- Modify: `tools/photo3d_provider_presets.py`
- Modify: `tools/project_guide.py`

- [x] Add frozen dataclass fields `ordinary_user_title`, `ordinary_user_summary`, `recommended_when`, and `requires_setup`.
- [x] Keep `ordinary_user_label` as a compatibility alias for `ordinary_user_title`.
- [x] Add copy for the existing six provider ids only.
- [x] Add `_ordinary_user_provider_options(...)` in `tools/project_guide.py` that maps presets and preview handoff actions by provider id.
- [x] Add `ordinary_user_options` to `provider_choice`.

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_provider_presets.py tests\test_project_guide.py -q
```

Expected: pass.

### Task 4: Docs, Sync, Verify, Merge

**Files:**
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: docs/metadata listed in File Map
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`

- [x] Extend docs tests to require `ordinary_user_options` or equivalent ordinary-user option guidance.
- [x] Update CLI/help/docs/metadata to tell ordinary users to choose from named preset options, not hand-write backend/model flags.
- [x] Run `python scripts/dev_sync.py`.
- [x] Run full scoped verification:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_provider_presets.py tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
git diff --check
```

- [ ] Commit, merge to `main`, rerun scoped verification, push, and clean `.worktrees/provider-choice-user-copy` plus `codex/provider-choice-user-copy`.

## Self Review

- Scope is generic and provider-agnostic.
- No provider adapter or backend execution behavior changes.
- `project-guide` stays read-only.
- Data fields are stable enough for UI/LLM consumption.
- Tests protect against secret URL/key leakage in preset metadata.
