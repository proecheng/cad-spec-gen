# Photo3D Run Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a foolproof Photo3D multi-round guide that advances the current active run until it reaches a user decision, manual review, baseline confirmation, enhancement handoff, or a configured loop limit.

**Architecture:** Add a small orchestration layer `tools/photo3d_loop.py` that reuses `run_photo3d_gate`, `write_photo3d_autopilot_report`, and `run_photo3d_action` instead of duplicating recovery logic. The loop is run-aware: it resolves all paths through the explicit artifact index and active run, writes `PHOTO3D_RUN.json` inside the active run directory, and stops rather than guessing when user input, baseline acceptance, enhancement, manual review, or failure is required.

**Tech Stack:** Python 3.12, argparse CLI in `cad_pipeline.py`, existing Photo3D JSON contracts, pytest.

---

### Task 1: Add Loop Contract Tests

**Files:**
- Create: `tests/test_photo3d_loop.py`

- [ ] **Step 1: Write failing tests**

Add tests proving that `photo3d-run`:
- writes `PHOTO3D_RUN.json` in the active run directory,
- stops at baseline acceptance without silently accepting,
- confirms and executes low-risk blocked recovery actions when `--confirm-actions` is supplied,
- does not continue if action output still needs user input or manual review.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/test_photo3d_loop.py -q`

Expected: import or CLI failures because `tools.photo3d_loop` and `cmd_photo3d_run` do not exist yet.

### Task 2: Implement Loop Orchestrator

**Files:**
- Create: `tools/photo3d_loop.py`

- [ ] **Step 1: Implement minimal orchestrator**

Create `run_photo3d_loop(project_root, subsystem, *, artifact_index_path=None, max_rounds=3, confirm_actions=False, output_path=None)`:
- Load `ARTIFACT_INDEX.json` and active run.
- For each round, run `run_photo3d_gate`, then `write_photo3d_autopilot_report`.
- If autopilot status is `blocked` and `confirm_actions` is true, run `run_photo3d_action(..., confirm=True)`.
- Continue only when action status is `executed` and `post_action_autopilot.rerun` is true and that post-action status is still `blocked`.
- Stop on `needs_baseline_acceptance`, `ready_for_enhancement`, `needs_user_input`, `needs_manual_review`, `execution_failed`, `awaiting_confirmation`, `loop_limit_reached`.
- Write one `PHOTO3D_RUN.json` report with `rounds`, `status`, `next_action`, and artifact paths.

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest tests/test_photo3d_loop.py -q`

Expected: loop tests pass.

### Task 3: Add CLI And Packaging

**Files:**
- Modify: `cad_pipeline.py`
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `tests/test_photo3d_packaging_sync.py`
- Modify: `skill.json`
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `.claude/commands/cad-help.md`
- Modify: `skill_cad_help.md`

- [ ] **Step 1: Add failing CLI/help/packaging tests**

Extend tests to require:
- `python cad_pipeline.py photo3d-run --help` documents `PHOTO3D_RUN.json`, `--max-rounds`, `--confirm-actions`, no scanning, no baseline/enhancement side effects.
- skill metadata exposes `photo3d_run`.
- packaged tool mirror includes `photo3d_loop.py`.

- [ ] **Step 2: Implement CLI**

Add `cmd_photo3d_run` and parser entry:
- `python cad_pipeline.py photo3d-run --subsystem <name>`
- `--artifact-index`
- `--max-rounds`
- `--confirm-actions`
- `--output`

- [ ] **Step 3: Sync generated mirrors**

Run: `python scripts/dev_sync.py`

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_photo3d_loop.py tests/test_photo3d_user_flow.py tests/test_photo3d_packaging_sync.py tests/test_dev_sync_check.py tests/test_data_dir_sync.py -q`

### Task 4: Update Progress Board And Verify

**Files:**
- Modify: `docs/PROGRESS.md`

- [ ] **Step 1: Update board**

Move “傻瓜式照片级 3D 流程” forward with `photo3d-run`, note current limits, and set the next recommended work to enhancement consistency validation.

- [ ] **Step 2: Final verification**

Run:
- `python scripts/dev_sync.py --check`
- `python -m pytest -q`

- [ ] **Step 3: Commit**

Commit with:

```bash
git commit -m "feat(photo3d): 增加多轮出图向导"
```
