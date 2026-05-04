# Enhancement Consistency Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a run-aware enhancement acceptance report so photorealistic images are delivered as `accepted`, `preview`, or `blocked` based on source render consistency instead of raw generation success.

**Architecture:** Extend `tools/enhance_consistency.py` from single-image comparison to a batch report builder. The report reads a current run render manifest, matches each source view to an enhanced image in the same render directory, validates view coverage and shape/occlusion consistency, writes `ENHANCEMENT_REPORT.json`, and never scans outside the explicit render directory.

**Tech Stack:** Python 3.12, Pillow image masks, existing render manifest contract, argparse CLI in `cad_pipeline.py`, pytest.

---

### Task 1: Batch Consistency Contract

**Files:**
- Modify: `tests/test_enhance_consistency.py`
- Modify: `tools/enhance_consistency.py`

- [ ] **Step 1: Write failing tests**

Add tests for:
- all manifest views have matching enhanced files and identical masks -> `accepted`;
- missing enhanced view -> `blocked`;
- shifted or cropped enhanced view -> `preview`;
- enhanced file outside render dir -> rejected.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/test_enhance_consistency.py -q`

Expected: fails because `write_enhancement_report` does not exist.

- [ ] **Step 3: Implement batch report**

Add `build_enhancement_report(...)` and `write_enhancement_report(...)` with:
- `schema_version: 1`
- `status: accepted|preview|blocked`
- `delivery_status` same as `status`
- `run_id`, `subsystem`, `render_manifest`, `enhancement_report`
- per-view `source_image`, `enhanced_image`, `edge_similarity`, `source_qa`, `enhanced_qa`
- `blocking_reasons`

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_enhance_consistency.py -q`

### Task 2: CLI And User Flow

**Files:**
- Modify: `cad_pipeline.py`
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `tests/test_photo3d_packaging_sync.py`
- Modify: `skill.json`
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `.claude/commands/cad-help.md`
- Modify: `skill_cad_help.md`

- [ ] **Step 1: Add failing CLI/help/metadata tests**

Require:
- `python cad_pipeline.py enhance-check --help` documents `ENHANCEMENT_REPORT.json`, `accepted/preview/blocked`, `--dir`, and no directory guessing outside render manifest.
- skill metadata exposes `enhance_check`.
- packaging mirrors still include `enhance_consistency.py`.

- [ ] **Step 2: Implement CLI**

Add `cmd_enhance_check` and parser:
- `python cad_pipeline.py enhance-check --subsystem <name> --dir cad/output/renders/<name>/<run_id>`
- optional `--manifest`
- optional `--output`
- optional `--min-similarity`

- [ ] **Step 3: Sync mirrors**

Run: `python scripts/dev_sync.py`

### Task 3: Progress And Verification

**Files:**
- Modify: `docs/PROGRESS.md`

- [ ] **Step 1: Update board**

Move enhancement consistency validation to Done and set the next item to build artifact backfill / higher-level project guide.

- [ ] **Step 2: Verify**

Run:
- `python scripts/dev_sync.py --check`
- focused Photo3D/enhancement tests
- `python -m pytest -q`

- [ ] **Step 3: Commit**

Commit with:

```bash
git commit -m "feat(photo3d): 增加增强一致性验收"
```
