# Photo3D Interactive Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a foolproof `photo3d-handoff` command that lets ordinary users or LLM agents preview and, only after explicit confirmation, execute the current Photo3D next action without path/run drift.

**Architecture:** `photo3d-run` and `photo3d-autopilot` remain report-only next-step generators. A new `tools/photo3d_handoff.py` reads the current active run from `ARTIFACT_INDEX.json`, loads `PHOTO3D_RUN.json` or `PHOTO3D_AUTOPILOT.json` from that run directory, classifies the current `next_action`, writes `PHOTO3D_HANDOFF.json`, and executes only allowlisted confirmed handoffs. It rebuilds command arguments from trusted run state instead of blindly trusting stale report argv.

**Tech Stack:** Python 3.10+, pytest, existing `tools.contract_io`, `tools.path_policy`, `tools.artifact_index`, `cad_pipeline.py`, `scripts/dev_sync.py` mirrors.

---

## Scope

In scope:

- Add `photo3d-handoff --subsystem <name>` as a preview-by-default command.
- Add `--confirm` to execute the current handoff when it is safe and explicitly confirmed.
- Support these next actions:
  - `accept_baseline`: run the existing baseline acceptance logic for the active run.
  - `run_enhancement`: invoke `cad_pipeline.py enhance` with the current run render directory.
  - `run_enhance_check`: invoke `cad_pipeline.py enhance-check` with the current run render directory. This is enabled when the user asks to execute handoff after enhancement outputs already exist or when a report provides that next action.
  - `confirm_action_plan`: delegate to `photo3d-run --confirm-actions` with the same artifact index.
- Reject `delivery_complete`, `review_enhancement_preview`, `fix_enhancement_blockers`, user-input, manual-review, and unknown actions as non-executable handoffs.
- Require all paths to remain inside the project and current active run/render directory.
- Keep default behavior non-mutating except for writing `PHOTO3D_HANDOFF.json`.

Out of scope:

- Running enhancement without user confirmation.
- Accepting baseline inside `photo3d-run`.
- Guessing latest render folders or scanning unrelated directories.
- Executing arbitrary argv from JSON reports.
- Replacing `photo3d-action` low-risk recovery behavior.

---

## File Structure

- Create `tools/photo3d_handoff.py`: next-action loader, classifier, command builder, confirmed execution, report writer.
- Create `tests/test_photo3d_handoff.py`: red/green coverage for preview, confirm, path/run binding, rejection, CLI wrapper.
- Modify `cad_pipeline.py`: add `cmd_photo3d_handoff`, parser, command dispatch.
- Modify `tests/test_photo3d_user_flow.py`: help text and skill metadata expectations.
- Modify `tests/test_photo3d_packaging_sync.py`: include packaged mirror coverage for `photo3d_handoff.py`.
- Modify `src/cad_spec_gen/data/skill.json`: add tool metadata and update cad-help description.
- Modify `docs/cad-help-guide-zh.md`, `docs/PROGRESS.md`, `docs/superpowers/README.md`: record the new handoff flow and this round.
- Run `scripts/dev_sync.py` to mirror `tools/photo3d_handoff.py`, `cad_pipeline.py`, docs, and metadata.

---

### Task 1: Red Tests for Handoff

**Files:**
- Create: `tests/test_photo3d_handoff.py`
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `tests/test_photo3d_packaging_sync.py`

- [ ] **Step 1: Add failing tests**

Add tests that assert:

- Previewing `accept_baseline` writes `PHOTO3D_HANDOFF.json`, status `awaiting_confirmation`, does not mutate `accepted_baseline_run_id`, and reconstructs argv with explicit `--artifact-index` and `--run-id`.
- Confirming `accept_baseline` calls the same validation path as `cmd_accept_baseline`, updates `accepted_baseline_run_id`, writes `status: executed`, then reruns `photo3d-run` to surface the next handoff.
- Previewing `run_enhancement` does not execute a subprocess and binds `--dir cad/output/renders/<subsystem>/<run_id>`.
- Confirming `run_enhancement` executes with `sys.executable`, current project cwd, explicit `--subsystem`, explicit `--dir`, and stores stdout/stderr/returncode.
- `run_enhance_check` only uses the active run render directory and rejects mismatched `render_manifest` paths.
- `confirm_action_plan` delegates to `photo3d-run --confirm-actions --artifact-index <path>`.
- Unknown or terminal actions return `needs_manual_review` and do not execute.
- Report path overrides must stay in current active run directory and must be named `PHOTO3D_HANDOFF.json`.
- Help text and `skill.json` expose `photo3d-handoff`.
- Packaged mirror list includes `photo3d_handoff.py`.

- [ ] **Step 2: Verify red**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_user_flow.py::test_photo3d_handoff_help_explains_confirmed_handoff_flow tests\test_photo3d_packaging_sync.py::test_photo3d_contract_tools_have_packaged_mirrors -q
```

Expected: FAIL because `tools/photo3d_handoff.py`, CLI, metadata, and mirror coverage do not exist yet.

---

### Task 2: Implement Handoff Tool

**Files:**
- Create: `tools/photo3d_handoff.py`

- [ ] **Step 1: Add loader and path guards**

Implement:

- `run_photo3d_handoff(project_root, subsystem, *, artifact_index_path=None, source=None, confirm=False, output_path=None)`
- Resolve `ARTIFACT_INDEX.json`; verify `subsystem`, `active_run_id`, and active run entry.
- Resolve run directory as `cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>`.
- `source=None` loads `PHOTO3D_RUN.json` if present, otherwise `PHOTO3D_AUTOPILOT.json`.
- `source="run"` only loads `PHOTO3D_RUN.json`; `source="autopilot"` only loads `PHOTO3D_AUTOPILOT.json`.
- Reject payload `run_id` or `subsystem` drift.
- Output defaults to run dir `PHOTO3D_HANDOFF.json`; override must stay in run dir and keep that filename.

- [ ] **Step 2: Add action classification**

Classify `next_action.kind` into:

- executable:
  - `accept_baseline`
  - `run_enhancement`
  - `run_enhance_check`
  - `confirm_action_plan`
- manual:
  - `delivery_complete`
  - `review_enhancement_preview`
  - `fix_enhancement_blockers`
  - `provide_user_input`
  - `manual_review`
  - unknown actions

For executable actions, rebuild argv from trusted inputs:

- `accept_baseline`: `[sys.executable, "cad_pipeline.py", "accept-baseline", "--subsystem", subsystem, "--artifact-index", <index_rel>, "--run-id", active_run_id]`
- `run_enhancement`: `[sys.executable, "cad_pipeline.py", "enhance", "--subsystem", subsystem, "--dir", <render_dir_rel>]`
- `run_enhance_check`: `[sys.executable, "cad_pipeline.py", "enhance-check", "--subsystem", subsystem, "--dir", <render_dir_rel>]`
- `confirm_action_plan`: `[sys.executable, "cad_pipeline.py", "photo3d-run", "--subsystem", subsystem, "--artifact-index", <index_rel>, "--confirm-actions"]`

Never copy raw argv from report JSON.

- [ ] **Step 3: Add execution and post-handoff summary**

Preview:

- Write report with `status: awaiting_confirmation`.
- Do not mutate artifact index.
- Do not run subprocess.

Confirmed:

- For `accept_baseline`, import and call an extracted helper from `cad_pipeline.py` or an internal function that preserves the same validation checks as `cmd_accept_baseline`.
- For subprocess-backed handoffs, execute with `cwd=project_root`, `shell=False`, `capture_output=True`, UTF-8 replacement.
- After successful `accept_baseline` or `confirm_action_plan`, rerun `run_photo3d_loop(..., max_rounds=1, confirm_actions=False)` and store compact `post_handoff_photo3d_run`.
- For failed subprocess returncode, write `execution_failed`.

- [ ] **Step 4: Add return-code helper**

Implement `command_return_code(report)`:

- Return `0` for `awaiting_confirmation`, `executed`, `executed_with_followup`, `needs_manual_review` when no execution failed.
- Return `1` for `execution_failed`, path/run validation errors, no matching executable when confirmed, or blocked validation.

---

### Task 3: CLI and Packaging Integration

**Files:**
- Modify: `cad_pipeline.py`
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `tests/test_photo3d_packaging_sync.py`
- Modify: `src/cad_spec_gen/data/skill.json`

- [ ] **Step 1: Add CLI command**

Add:

```powershell
python cad_pipeline.py photo3d-handoff --subsystem <name>
python cad_pipeline.py photo3d-handoff --subsystem <name> --confirm
```

Options:

- `--artifact-index`
- `--source run|autopilot`
- `--confirm`
- `--output`

- [ ] **Step 2: Add help and metadata text**

Help must say:

- Preview by default.
- `--confirm` executes only recognized current next actions.
- It never scans directories, never trusts arbitrary argv, and keeps all output in the active run directory.
- It is the ordinary-user/LLM bridge after `photo3d-run`.

- [ ] **Step 3: Add packaging mirror coverage**

Add `photo3d_handoff.py` to `PHOTO3D_CONTRACT_TOOL_FILES`.

---

### Task 4: Docs, Sync, and Verification

**Files:**
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`
- Modify: `docs/cad-help-guide-zh.md`

- [ ] **Step 1: Update docs**

Record:

- New board item: Photo3D confirmed handoff.
- New boundary: handoff is preview by default; `--confirm` only executes current active run next action; no scan/latest guessing; no arbitrary argv.
- Next step: decide whether to add provider-specific enhancement presets or a UI wizard.

- [ ] **Step 2: Run sync**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
```

- [ ] **Step 3: Run focused regression**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_loop.py tests\test_photo3d_autopilot.py tests\test_photo3d_action_runner.py tests\test_photo3d_accept_baseline.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
```

- [ ] **Step 4: Run final checks**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
```

---

### Task 5: Commit and Finish

**Files:**
- All changed files above.

- [ ] **Step 1: Commit feature**

Commit:

```powershell
git add tools/photo3d_handoff.py cad_pipeline.py tests/test_photo3d_handoff.py tests/test_photo3d_user_flow.py tests/test_photo3d_packaging_sync.py src/cad_spec_gen/data/skill.json docs/cad-help-guide-zh.md docs/PROGRESS.md docs/superpowers/README.md docs/superpowers/plans/2026-05-05-photo3d-interactive-handoff.md
git commit -m "feat(photo3d): 增加确认式下一步交接入口"
```

- [ ] **Step 2: Finish branch**

After tests pass, use the finishing branch workflow:

- Merge to `main`.
- Verify on `main`.
- Push.
- Clean `codex/photo3d-interactive-actions` worktree/branch.
- Update docs one final time to record push/cleanup.

---

## Self-Review Notes

- Spec coverage: preview, explicit confirmation, baseline, enhance, enhance-check, action-plan confirmation, no arbitrary argv, active run binding, output path guard, docs, metadata, sync checks are covered.
- Placeholder scan: no TBD/TODO implementation placeholder remains.
- Type consistency: command name is `photo3d-handoff`; report file is `PHOTO3D_HANDOFF.json`; source values are `run` and `autopilot`; statuses are `awaiting_confirmation`, `executed`, `executed_with_followup`, `needs_manual_review`, `execution_failed`.
- Boundary guard: `photo3d-run` remains non-mutating for baseline/enhance; `photo3d-handoff --confirm` is the new explicit mutation/execution boundary.
