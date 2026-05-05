# Semantic Material Quality Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, active-run-bound semantic/material review layer for enhanced Photo3D images so ordinary users and LLMs can submit structured review evidence without relying on directory guesses, arbitrary AI backends, or product-specific rules.

**Architecture:** Create a separate `enhance-review` command and `ENHANCEMENT_REVIEW_REPORT.json` rather than overloading deterministic `quality_summary`. The command ingests an explicit human/LLM review JSON, binds it to `ARTIFACT_INDEX.json.active_run_id`, the same-run `render_manifest.json`, and the same-run `ENHANCEMENT_REPORT.json`, then writes a review report in the active run directory. `photo3d-deliver` includes this evidence when present and can require it with `--require-semantic-review`.

**Tech Stack:** Python 3.10+, existing `tools.contract_io`, `tools.path_policy`, pytest, project `dev_sync.py` mirror pipeline.

---

## Data Contract

Review input is explicit JSON supplied by `--review-input`; the pipeline never calls a cloud model in this step and never scans directories for newest images.

Required review input shape for an accepted report:

```json
{
  "schema_version": 1,
  "run_id": "RUN001",
  "subsystem": "demo",
  "review_type": "human",
  "source_reports": {
    "render_manifest": "cad/output/renders/demo/RUN001/render_manifest.json",
    "render_manifest_sha256": "<sha256>",
    "enhancement_report": "cad/output/renders/demo/RUN001/ENHANCEMENT_REPORT.json",
    "enhancement_report_sha256": "<sha256>"
  },
  "views": [
    {
      "view": "V1",
      "semantic_checks": {
        "geometry_preserved": true,
        "material_consistent": true,
        "photorealistic": true,
        "no_extra_parts": true,
        "no_missing_parts": true
      },
      "reviewer_notes": "Looks consistent."
    }
  ]
}
```

Required semantic checks are generic and product-agnostic:

```python
REQUIRED_SEMANTIC_CHECKS = (
    "geometry_preserved",
    "material_consistent",
    "photorealistic",
    "no_extra_parts",
    "no_missing_parts",
)
```

Status rules:

- `accepted`: deterministic enhancement evidence is accepted, source report paths and hashes match, every expected view appears exactly once, and every required semantic check is `true`.
- `preview`: the evidence is bound correctly, but at least one semantic/material quality check is `false`; it can be shown to users but is not final delivery.
- `needs_review`: the evidence is bound correctly, but at least one required semantic check is missing or non-boolean.
- `blocked`: run/subsystem/source-report path/hash/view identity drift, duplicate views, missing views, extra views, or deterministic enhancement evidence not accepted.

`photo3d-deliver` behavior:

- If no `ENHANCEMENT_REVIEW_REPORT.json` exists and `--require-semantic-review` is not set, delivery remains backward compatible and records `semantic_material_review.status == "not_run"`.
- If `--require-semantic-review` is set, missing or non-accepted semantic review blocks final delivery.
- If a same-run review report exists and its status is not `accepted`, final delivery is blocked even without `--require-semantic-review`, because the user has already supplied negative review evidence for this run.

## Files

- Create `tools/enhancement_semantic_review.py`: active-run semantic/material review ingestion and report writing.
- Create `tests/test_enhancement_semantic_review.py`: TDD coverage for accepted input, data drift, view drift, CLI behavior, and delivery integration.
- Modify `tools/photo3d_delivery_pack.py`: include optional review report, copy it as evidence, and add `--require-semantic-review` gate.
- Modify `cad_pipeline.py`: add `cmd_enhance_review`, parser help, dispatch, and `photo3d-deliver --require-semantic-review`.
- Modify `tests/test_photo3d_packaging_sync.py`: include the new tool in packaged mirror checks.
- Modify `tests/test_photo3d_user_flow.py`: require CLI help, docs, and metadata terms for `enhance-review` and `ENHANCEMENT_REVIEW_REPORT.json`.
- Modify `src/cad_spec_gen/data/skill.json`, `skill_cad_help.md`, and generated docs through `scripts/dev_sync.py`.
- Modify `docs/PROGRESS.md` and `docs/superpowers/README.md`: update the board and plan index.

---

### Task 1: RED Tests For Review Report

**Files:**
- Create: `tests/test_enhancement_semantic_review.py`

- [ ] **Step 1: Write failing tests**

Add tests that create a current Photo3D fixture, write an accepted `ENHANCEMENT_REPORT.json`, then verify:

```python
def test_enhance_review_accepts_bound_semantic_evidence(tmp_path):
    from tools.enhancement_semantic_review import write_enhancement_review_report

    fixture = _contracts(tmp_path)
    enhancement_path = _write_enhancement_report(fixture)
    review_input = _write_review_input(fixture, enhancement_path)

    report = write_enhancement_review_report(
        tmp_path,
        "demo",
        review_input_path=review_input,
        artifact_index_path=fixture["index_path"],
    )

    assert report["status"] == "accepted"
    assert report["semantic_material_review"]["status"] == "accepted"
    assert report["source_reports"]["render_manifest"].endswith("render_manifest.json")
    assert report["source_reports"]["enhancement_report"].endswith("ENHANCEMENT_REPORT.json")
    assert report["source_reports"]["review_input"].endswith("ENHANCEMENT_REVIEW_INPUT.json")
    assert (fixture["run_dir"] / "ENHANCEMENT_REVIEW_REPORT.json").is_file()
```

Also add focused tests for:

```python
def test_enhance_review_blocks_source_report_hash_drift(tmp_path): ...
def test_enhance_review_blocks_missing_view(tmp_path): ...
def test_enhance_review_marks_failed_material_check_as_preview(tmp_path): ...
def test_enhance_review_marks_missing_check_as_needs_review(tmp_path): ...
def test_cmd_enhance_review_writes_report(tmp_path, monkeypatch): ...
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_enhancement_semantic_review.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.enhancement_semantic_review'`.

---

### Task 2: Implement Review Tool

**Files:**
- Create: `tools/enhancement_semantic_review.py`
- Modify: `cad_pipeline.py`
- Test: `tests/test_enhancement_semantic_review.py`

- [ ] **Step 1: Implement minimal review builder**

Implement public functions:

```python
def build_enhancement_review_report(
    project_root: str | Path,
    subsystem: str,
    *,
    review_input_path: str | Path,
    artifact_index_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]: ...

def write_enhancement_review_report(...) -> dict[str, Any]: ...

def command_return_code_for_enhancement_review(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {"accepted", "preview", "needs_review"} else 1
```

The implementation must:

- Resolve `ARTIFACT_INDEX.json` from explicit `--artifact-index` or `cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json`.
- Use only `active_run_id`; never accept a `run_id` from review input as the active source.
- Require output path to stay inside `cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>/` and be named `ENHANCEMENT_REVIEW_REPORT.json`.
- Resolve the active run manifest from the artifact index, then require `ENHANCEMENT_REPORT.json` beside the active manifest.
- Verify current `ENHANCEMENT_REPORT.json` is bound to the same run, subsystem, manifest path, self path, render dir, and `quality_summary.status == "accepted"`.
- Validate review input source report paths and hashes against current files.
- Validate expected view set from `ENHANCEMENT_REPORT.json.views`.
- Write a stable, ordinary-user-readable report with `semantic_material_review`, `views`, `warnings`, and `blocking_reasons`.

- [ ] **Step 2: Add CLI**

Add:

```powershell
python cad_pipeline.py enhance-review --subsystem <name> --review-input <json>
```

Parser terms must mention `ENHANCEMENT_REVIEW_REPORT.json`, active run binding, no scanning, no cloud call, `accepted/preview/needs_review/blocked`, and `--artifact-index`.

- [ ] **Step 3: Run focused tests**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_enhancement_semantic_review.py -q
```

Expected: PASS.

---

### Task 3: Delivery Integration

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`
- Modify: `cad_pipeline.py`
- Test: `tests/test_enhancement_semantic_review.py`, `tests/test_photo3d_delivery_pack.py`

- [ ] **Step 1: Add failing delivery tests**

Add tests that verify:

```python
def test_photo3d_delivery_pack_includes_accepted_semantic_review_evidence(tmp_path): ...
def test_photo3d_delivery_pack_blocks_existing_preview_semantic_review(tmp_path): ...
def test_photo3d_delivery_pack_requires_semantic_review_when_requested(tmp_path): ...
def test_cmd_photo3d_deliver_accepts_require_semantic_review_flag(tmp_path, monkeypatch): ...
```

- [ ] **Step 2: Implement delivery gate**

Add `require_semantic_review: bool = False` to `run_photo3d_delivery_pack`.

Add summary behavior:

```python
"semantic_material_review": {
    "schema_version": 1,
    "status": "not_run" | "accepted" | "preview" | "needs_review" | "blocked",
    "review_report": "cad/<subsystem>/.cad-spec-gen/runs/<run_id>/ENHANCEMENT_REVIEW_REPORT.json" | None
}
```

Block final delivery when:

- `require_semantic_review` is true and report is missing.
- Review report exists and status is not `accepted`.
- Review report run_id/subsystem/source report path/hash binding drifts.

Copy `ENHANCEMENT_REVIEW_REPORT.json` into delivery evidence when present.

- [ ] **Step 3: Run focused tests**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_enhancement_semantic_review.py tests\test_photo3d_delivery_pack.py -q
```

Expected: PASS.

---

### Task 4: Docs, Metadata, And Packaged Mirrors

**Files:**
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `tests/test_photo3d_packaging_sync.py`
- Modify: `src/cad_spec_gen/data/skill.json`
- Modify: `skill_cad_help.md`
- Generated by sync: `.claude/commands/cad-help.md`, `docs/cad-help-guide-zh.md`, `src/cad_spec_gen/data/tools/enhancement_semantic_review.py`, `src/cad_spec_gen/data/python_tools/cad_pipeline.py`, `src/cad_spec_gen/data/knowledge/skill_cad_help_zh.md`

- [ ] **Step 1: Add failing contract tests**

Require:

- `enhance-review` in `USER_FLOW_TERMS`.
- `ENHANCEMENT_REVIEW_REPORT.json` and `semantic_material_review` in docs and help.
- `enhancement_review` tool metadata with CLI `python cad_pipeline.py enhance-review --subsystem <name> --review-input <json>`.
- New tool mirror in `PHOTO3D_CONTRACT_TOOL_FILES`.

- [ ] **Step 2: Update metadata and source docs**

Update skill metadata and `skill_cad_help.md` to say:

- This is an explicit human/LLM review evidence ingestion command.
- It does not call AI, does not accept backend/model/key/url, and does not scan directories.
- It binds to active run, source report paths, source report hashes, and view ids.
- It is optional unless `photo3d-deliver --require-semantic-review` is used or a same-run review report already exists.

- [ ] **Step 3: Sync generated files**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py
```

Then add ignored mirrors with `git add -f` during commit preparation.

- [ ] **Step 4: Run docs and sync tests**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
```

Expected: PASS.

---

### Task 5: Board Update And Verification

**Files:**
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`
- Modify: this plan file

- [ ] **Step 1: Update board**

Mark "语义/材质级增强质量复核" as Done, raise Phase 5/6 progress only after tests pass, and set the next queue item to the common model library next batch.

- [ ] **Step 2: Final verification**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_enhancement_semantic_review.py tests\test_enhance_consistency.py tests\test_photo3d_delivery_pack.py tests\test_photo3d_handoff.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
git diff --check
```

Expected:

- `dev_sync.py --check` passes.
- Focused Photo3D/Phase 5/6 tests pass.
- `git diff --check` has no whitespace errors.

- [ ] **Step 3: Commit**

Use:

```powershell
git add tests/test_enhancement_semantic_review.py tools/enhancement_semantic_review.py tools/photo3d_delivery_pack.py cad_pipeline.py tests/test_photo3d_user_flow.py tests/test_photo3d_packaging_sync.py src/cad_spec_gen/data/skill.json skill_cad_help.md .claude/commands/cad-help.md docs/cad-help-guide-zh.md src/cad_spec_gen/data/tools/enhancement_semantic_review.py src/cad_spec_gen/data/python_tools/cad_pipeline.py src/cad_spec_gen/data/knowledge/skill_cad_help_zh.md docs/PROGRESS.md docs/superpowers/README.md docs/superpowers/plans/2026-05-05-semantic-material-quality-review.md
git commit -m "feat(photo3d): 增加语义材质复核"
```

---

## Self-Review

Spec coverage:

- Active-run binding is covered by Task 2.
- Data/path/hash drift is covered by Task 1 and Task 3.
- Function consistency is covered by public `build_*/write_*/command_return_code_*` functions matching existing tools.
- Boundary with deterministic quality is explicit: semantic review sits above `quality_summary`, and delivery can require it without making cloud AI a hard dependency.
- Ordinary-user/LLM operation is explicit: the command ingests structured evidence and does not accept backend/model/key/url/argv.

Placeholder scan:

- No TBD/TODO placeholders remain in the executable tasks.

Type consistency:

- Command name: `enhance-review`.
- Report name: `ENHANCEMENT_REVIEW_REPORT.json`.
- Summary object: `semantic_material_review`.
- Review input flag: `--review-input`.
