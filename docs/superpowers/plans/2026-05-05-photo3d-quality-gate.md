# Photo3D Multi-View Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic multi-view photoreal delivery quality gate to `enhance-check` and `photo3d-deliver` so accepted enhancement evidence includes cross-view quality metrics instead of only per-view shape checks.

**Architecture:** Extend `tools/enhance_consistency.py` rather than adding a new user-facing command. `enhance-check` will continue writing `ENHANCEMENT_REPORT.json`, now with a `quality_summary` object and per-view `quality_metrics`; `photo3d-deliver` will copy this summary into `DELIVERY_PACKAGE.json` and refuse final delivery when quality status is not accepted. The gate remains run/path bound through the existing explicit render dir and active-run delivery contracts.

**Tech Stack:** Python 3.10+, Pillow image statistics, existing `qa_image`, `write_json_atomic`, `dev_sync.py`, pytest.

---

### Task 1: Quality Metrics In Enhancement Report

**Files:**
- Modify: `tools/enhance_consistency.py`
- Test: `tests/test_enhance_consistency.py`

- [x] **Step 1: Write failing tests**

Add tests that:
- Accepted multi-view enhancements include `quality_summary.status == "accepted"`.
- A low-contrast enhanced view becomes `preview` with `photo_quality_low_contrast`.
- A mixed-size enhanced view becomes `preview` with `photo_quality_inconsistent_canvas`.

- [x] **Step 2: Run tests to verify RED**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_enhance_consistency.py -q`

Expected: new assertions fail because `quality_summary` and quality reason codes do not exist yet.

- [x] **Step 3: Implement minimal quality metrics**

In `tools/enhance_consistency.py`:
- Add per-image metrics: width, height, luminance mean, contrast stddev, saturation mean, object occupancy from existing `qa_image`.
- Add `quality_summary` with status `accepted` / `preview`, warnings, per-view count, min thresholds, and canvas size consistency.
- Treat quality warnings as preview, not blocked, unless input is missing or ambiguous.

- [x] **Step 4: Run tests to verify GREEN**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_enhance_consistency.py -q`

Expected: all enhancement consistency tests pass.

### Task 2: Delivery Package Consumes Quality Summary

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`
- Test: `tests/test_photo3d_delivery_pack.py`

- [x] **Step 1: Write failing tests**

Add tests that:
- Accepted delivery package copies `quality_summary` from `ENHANCEMENT_REPORT.json`.
- A report with `delivery_status == "accepted"` but `quality_summary.status == "preview"` is not `final_deliverable`.

- [x] **Step 2: Run tests to verify RED**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_delivery_pack.py -q`

Expected: tests fail because delivery package does not read `quality_summary`.

- [x] **Step 3: Implement delivery check**

In `tools/photo3d_delivery_pack.py`:
- Read `quality_summary` from the enhancement report.
- Add it to `DELIVERY_PACKAGE.json`.
- If enhancement status is accepted but `quality_summary.status != "accepted"`, set `final_deliverable = false`, add blocking reason `photo_quality_not_accepted`, and do not copy final images.

- [x] **Step 4: Run tests to verify GREEN**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_delivery_pack.py -q`

Expected: all delivery pack tests pass.

### Task 3: CLI, Docs, Metadata, Mirrors

**Files:**
- Modify: `cad_pipeline.py`
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `tests/test_photo3d_packaging_sync.py`
- Modify: `skill.json`
- Modify: `.claude/commands/cad-help.md`
- Modify: `skill_cad_help.md`
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`

- [x] **Step 1: Write failing docs/user-flow tests**

Add assertions that `enhance-check --help`, CAD help docs, and skill metadata mention `quality_summary`, multi-view quality, and `photo_quality_not_accepted`.

- [x] **Step 2: Run tests to verify RED**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q`

Expected: docs/metadata assertions fail before text updates and mirrors are synced.

- [x] **Step 3: Update CLI help and docs**

Describe:
- `enhance-check` computes `quality_summary`.
- `photo3d-deliver` only final-delivers accepted enhancement with accepted quality summary.
- This is deterministic quality evidence, not semantic AI judgment.

- [x] **Step 4: Sync generated mirrors**

Run: `D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py`

- [x] **Step 5: Run full scoped verification**

Run:
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check`
- `D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_enhance_consistency.py tests\test_photo3d_delivery_pack.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q`
- `git diff --check`

Expected: all pass.

---

## Self-Review

- Spec coverage: The plan covers quality evidence in `ENHANCEMENT_REPORT.json`, delivery refusal in `DELIVERY_PACKAGE.json`, and user-facing docs/metadata.
- Placeholder scan: No TBD/TODO placeholders remain.
- Type consistency: Uses `quality_summary.status`, `quality_metrics`, and reason codes consistently across tests, tools, and docs.
