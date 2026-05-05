# Model Quality User Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn existing model-library geometry decisions into an ordinary-user model quality report that can be reused by `model-audit`, `project-guide`, and `photo3d-deliver`.

**Architecture:** Keep `geometry_report.json` and active-run `MODEL_CONTRACT.json` as facts; add a derived `model_quality_summary` view with stable machine-readable status, user labels, part-level messages, and next actions. `model-audit` remains geometry-report-only and read-only; `project-guide` reads the default subsystem report if it exists; `photo3d-deliver` prefers the active run `MODEL_CONTRACT.json` to avoid stale project-level drift.

**Tech Stack:** Python 3.10+, pytest, existing `tools.contract_io`, `tools.path_policy`, and `cad_pipeline.py` CLI wiring.

---

## File Structure

- Modify `tools/model_audit.py`: add reusable `build_model_quality_summary()`, source/quality label maps, public path sanitization, JSON/text output fields.
- Modify `tools/project_guide.py`: read `cad/<subsystem>/.cad-spec-gen/geometry_report.json` when present and embed `model_quality_summary` plus a compact `stage_status.model_quality`.
- Modify `tools/photo3d_delivery_pack.py`: derive delivery `model_quality_summary` from active-run `MODEL_CONTRACT.json` when present, copy it as existing evidence, and mention it in delivery `README.md`.
- Modify `cad_pipeline.py`: update help text for `model-audit`, `project-guide`, and `photo3d-deliver`.
- Modify tests: `tests/test_model_audit_cli.py`, `tests/test_project_guide.py`, `tests/test_photo3d_delivery_pack.py`, `tests/test_photo3d_user_flow.py`.
- Modify docs: `docs/PROGRESS.md`, `docs/superpowers/README.md`.

## Contract

`model_quality_summary` schema v1 is a derived user view, not a new source of geometry truth. Required top-level fields:

- `source`: `geometry_report` or `model_contract`
- `source_report`: project-relative path when inside project, otherwise a safe display path
- `binding_status`: `project_report` or `active_run_model_contract`
- `readiness_status`: `ready`, `needs_review`, `blocked`, or `not_available`
- `photoreal_risk`: `low`, `medium`, `high`, `blocked`, or `unknown`
- `quality_counts`, `source_counts`, `review_recommended_count`, `blocking_count`
- `part_summaries[]` with part number, name, quality/source labels, `user_status`, `user_message`, and `suggested_action`
- `recommended_next_action` with a stable `kind`

Rules:

- `blocked`: any missing STEP path or any `E` quality.
- `needs_review`: any `requires_model_review`, `C`, `D`, or unknown quality, with no blockers.
- `ready`: all parts are `A` or `B`, no missing STEP, no review flag.
- Public summary paths are project-relative or `cache://...`; absolute outside-project paths are not copied into the user-facing summary.
- `model-audit.status` remains backward compatible (`pass`, `review_required`, `missing_step`) so existing strict behavior is unchanged.

## Tasks

### Task 1: Model Audit Summary

- Write a failing JSON test in `tests/test_model_audit_cli.py` asserting `model_quality_summary`, source counts, part summaries, and recommended next action.
- Implement `build_model_quality_summary()` in `tools/model_audit.py`.
- Run `python -m pytest tests\test_model_audit_cli.py -q`.

### Task 2: Project Guide Surface

- Write a failing test in `tests/test_project_guide.py` for canonical `geometry_report.json` embedding.
- Implement read-only embedding in `tools/project_guide.py`; no resolver calls, no output-directory scans, no next-action mutation.
- Run `python -m pytest tests\test_project_guide.py -q`.

### Task 3: Delivery Pack Surface

- Write a failing test in `tests/test_photo3d_delivery_pack.py` for active-run `MODEL_CONTRACT.json` model quality summary.
- Implement delivery summary from already validated `source_reports["model_contract"]`.
- Run `python -m pytest tests\test_photo3d_delivery_pack.py -q`.

### Task 4: CLI Help, Packaging, Docs

- Update `cad_pipeline.py` help text and `tests/test_photo3d_user_flow.py`.
- Update `docs/PROGRESS.md` and `docs/superpowers/README.md`.
- Run:

```powershell
python scripts\dev_sync.py --check
python -m pytest tests\test_model_audit_cli.py tests\test_project_guide.py tests\test_photo3d_delivery_pack.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
git diff --check
```

## Review Notes

- This plan intentionally avoids per-device fixes and per-part special cases.
- The derived summary is a user view, not a new source of geometry truth.
- Delivery uses active-run `MODEL_CONTRACT.json` to prevent stale `geometry_report.json` drift from becoming final evidence.
