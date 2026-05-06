# Session Handoff — 2026-05-06

## Current Repository State

- Working directory: `D:\Work\cad-spec-gen`
- Active branch: `main`
- Git state at handoff: clean working tree after final push.
- Remote push status: pushed successfully after an earlier temporary GitHub port 443 connectivity failure.
- Remaining worktree: `.worktrees/generic-threaded-photo-autopilot` on `codex/generic-threaded-photo-autopilot`; it is unrelated to the latest completed work and should not be touched unless the user explicitly resumes it.

Latest local commits:

| Commit | Purpose |
| --- | --- |
| `397f733 docs(progress): 记录会话交接` | Adds this handoff report and links it from the project documentation index. |
| `8b3d5b4 docs(progress): 记录新用户入口合并状态` | Records local merge, validation, and the earlier temporary push failure in the project board. |
| `0ac375a feat(project-guide): 增加设计文档入口向导` | Adds `project-guide --from-design-doc` entry mode. |
| `4220b16 docs(progress): 记录模型质量摘要合并状态` | Records the previous model quality summary merge. |
| `2ab8da2 feat(model-quality): 输出普通用户模型质量摘要` | Adds user-facing model quality summaries. |

## Completed In This Session

- Added `project-guide --from-design-doc --design-doc <path>`.
- Entry mode reads exactly one explicit design document and writes `.cad-spec-gen/project-guide/PROJECT_GUIDE.json`.
- Entry status is `needs_subsystem_confirmation`; `next_action.kind` is `confirm_subsystem`.
- The report only suggests subsystem candidates and preview `project-guide --subsystem ... --design-doc ...` commands.
- It does not scan `docs/design`, scan `cad`, guess latest runs, initialize subsystems, generate spec/code/build/render/enhance artifacts, accept baselines, or mutate pipeline state beyond writing the entry guide.
- Updated CLI help, Chinese/English skill docs, `skill.json`, generated mirrors under `src/cad_spec_gen/data/*`, project board, Superpowers README, and the implementation plan.
- Cleaned the completed feature worktree and branch: `.worktrees/new-user-entry-guide`, `codex/new-user-entry-guide`.

## Validation Snapshot

Run on the feature branch before merge:

- `python -m pytest tests\test_project_guide.py -q` -> `16 passed, 1 warning`
- `python -m pytest tests\test_photo3d_user_flow.py -q` -> `14 passed, 1 warning`
- `python -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` -> `172 passed, 1 warning`
- `python scripts\dev_sync.py --check` -> passed
- `git diff --check` -> passed

Run again on local `main` after fast-forward merge:

- `python scripts\dev_sync.py --check` -> passed
- `python -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` -> `172 passed, 1 warning`
- `git diff --check` -> passed

Known warning: existing pytest warning for unknown `env` config option.

## Next Recommended Work

1. Continue Phase 1 -> Phase 6 new-user entry work: move from explicit design-document entry to a fuller "product goal + design document + missing parameter confirmation" guide.
2. Prepare real AI backend adapter admission for providers such as `gpt-image-2-pro`: configuration isolation, allowlisted preset, same-run enhancement/check loop, multi-view consistency tests, and no secret persistence or URL/key leakage.
3. Improve Phase 4 -> Phase 6 per-view visible instance evidence so render completeness relies less on warnings.
4. Improve Phase 6 delivery README with thumbnails, model quality summary, semantic/material review status, and next actions.

## Required Reference Documents For New Session

Read these first:

- `docs/PROGRESS.md`
- `docs/superpowers/README.md`
- `docs/superpowers/plans/2026-05-06-new-user-entry-guide.md`
- `docs/superpowers/plans/2026-05-05-model-quality-user-report.md`
- `docs/superpowers/runbooks/common-model-family-admission.md`
- `docs/superpowers/specs/common_model_family_admission.json`
- `AGENTS.md`

For the current feature behavior, inspect:

- `tools/project_guide.py`
- `cad_pipeline.py`
- `tests/test_project_guide.py`
- `tests/test_photo3d_user_flow.py`
- `docs/cad-help-guide-zh.md`
- `.claude/commands/cad-help.md`
- `skill_cad_help.md`
- `skill.json`

## Operating Rules To Preserve

- All user-facing replies should be Chinese.
- Avoid temporary, device-specific tightening. Prefer generic contracts, stable data structures, explicit path policy, and regression tests.
- Use TDD for behavior changes: write failing tests, verify red, implement, verify green.
- After touching mirrored docs/tools/metadata, run:
  - `python scripts\dev_sync.py`
  - `python scripts\dev_sync.py --check`
- Before claiming completion, run relevant pytest suites and `git diff --check`.
- Update `docs/PROGRESS.md` and `docs/superpowers/README.md` at the end of each completed round.
- Use worktrees for feature work and clean completed worktrees/branches promptly.
- Do not touch `.worktrees/generic-threaded-photo-autopilot` unless that feature is explicitly resumed.
