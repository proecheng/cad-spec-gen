# Enhancement Summary Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface `ENHANCEMENT_REPORT.json` accepted/preview/blocked delivery status in `photo3d-autopilot` and `photo3d-run` so ordinary users know whether the photorealistic output is deliverable after enhancement checking.

**Architecture:** Keep CAD gate and enhancement acceptance as separate layers. `photo3d-autopilot` derives the expected enhancement report path only from the current run's indexed `render_manifest` path, reads it when present, and never scans render directories. `photo3d-run` treats enhancement delivery states as terminal statuses and writes the summary into `PHOTO3D_RUN.json`.

**Tech Stack:** Python 3.10+, pytest, existing `tools/photo3d_autopilot.py`, `tools/photo3d_loop.py`, generated mirrors via `scripts/dev_sync.py`.

---

## File Structure

- Modify `tests/test_photo3d_autopilot.py`: TDD coverage for accepted/preview/blocked enhancement summaries.
- Modify `tests/test_photo3d_loop.py`: TDD coverage that `photo3d-run` surfaces enhancement delivery status.
- Modify `tools/photo3d_autopilot.py`: read current-run `ENHANCEMENT_REPORT.json` from the indexed render manifest directory.
- Modify `tools/photo3d_loop.py`: add terminal statuses and include `enhancement_summary` in the loop report.
- Generated mirrors under `src/cad_spec_gen/data/tools/`: update only via `python scripts/dev_sync.py`.
- Modify `docs/PROGRESS.md` and `docs/superpowers/README.md`: update board and next steps.

## Invariants

- Do not run `enhance` or `enhance-check` from `photo3d-run`.
- Do not scan for newest files or enhanced images.
- Only consider `ENHANCEMENT_REPORT.json` beside the active run's indexed `render_manifest.json`.
- Reject or ignore reports whose `run_id`, `subsystem`, or `render_manifest` binding does not match the current run.
- `accepted` means deliverable, `preview` means preview only, `blocked` means not deliverable.
- Missing enhancement report keeps the current `ready_for_enhancement` behavior and recommends `enhance`.

## Task 1: Autopilot Enhancement Summary TDD

**Files:**
- Modify: `tests/test_photo3d_autopilot.py`

- [x] **Step 1: Add failing accepted-summary test**

Append:

```python
def test_cmd_photo3d_autopilot_reports_accepted_enhancement_delivery(tmp_path, monkeypatch):
    import cad_pipeline
    from tools.artifact_index import accept_run_baseline

    fixture = _contracts(tmp_path)
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    accept_run_baseline(index, "RUN001")
    fixture["index_path"].write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_json(
        fixture["render_dir"] / "ENHANCEMENT_REPORT.json",
        {
            "schema_version": 1,
            "run_id": "RUN001",
            "subsystem": "demo",
            "status": "accepted",
            "delivery_status": "accepted",
            "ordinary_user_message": "增强一致性验收通过，可作为照片级交付。",
            "render_manifest": "cad/output/renders/demo/RUN001/render_manifest.json",
            "enhancement_report": "cad/output/renders/demo/RUN001/ENHANCEMENT_REPORT.json",
            "view_count": 1,
            "enhanced_view_count": 1,
            "blocking_reasons": [],
        },
    )
    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_photo3d_autopilot(
        SimpleNamespace(
            subsystem="demo",
            artifact_index=str(fixture["index_path"]),
            change_scope=None,
            baseline_signature=None,
            output=None,
        )
    )

    assert rc == 0
    report = json.loads((fixture["run_dir"] / "PHOTO3D_AUTOPILOT.json").read_text(encoding="utf-8"))
    assert report["status"] == "enhancement_accepted"
    assert report["enhancement_summary"]["status"] == "accepted"
    assert report["enhancement_summary"]["enhancement_report"] == "cad/output/renders/demo/RUN001/ENHANCEMENT_REPORT.json"
    assert report["next_action"]["kind"] == "delivery_complete"
    assert report["artifacts"]["enhancement_report"] == "cad/output/renders/demo/RUN001/ENHANCEMENT_REPORT.json"
```

- [x] **Step 2: Add preview/blocked tests**

Add tests with the same setup, changing `status` / `delivery_status` to `preview` and `blocked`, expecting autopilot statuses `enhancement_preview` and `enhancement_blocked`, and next action kinds `review_enhancement_preview` / `fix_enhancement_blockers`.

- [x] **Step 3: Verify RED**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest tests\test_photo3d_autopilot.py::test_cmd_photo3d_autopilot_reports_accepted_enhancement_delivery -q
```

Expected before implementation: FAIL because `enhancement_summary` does not exist and status remains `ready_for_enhancement`.

## Task 2: Implement Autopilot Summary

**Files:**
- Modify: `tools/photo3d_autopilot.py`

- [x] **Step 1: Add summary loading**

Implement helpers:

```python
def _enhancement_summary_for_run(root: Path, subsystem: str, run_id: str, artifacts: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    render_manifest = artifacts.get("render_manifest")
    render_dir = _render_dir_from_manifest_path(render_manifest)
    if not render_dir:
        return None, None
    report_rel = f"{render_dir}/ENHANCEMENT_REPORT.json"
    report_path = _resolve_project_path(root, report_rel, "enhancement report")
    if not report_path.is_file():
        return None, report_rel
    report = load_json_required(report_path, "enhancement report")
    if str(report.get("run_id") or "") != run_id or str(report.get("subsystem") or "") != subsystem:
        return None, report_rel
    if str(report.get("render_manifest") or "") != render_manifest:
        return None, report_rel
    return _compact_enhancement_summary(report, report_rel), report_rel
```

And `_compact_enhancement_summary` with stable fields: `status`, `delivery_status`, `ordinary_user_message`, `enhancement_report`, `render_manifest`, `view_count`, `enhanced_view_count`, `blocking_reasons`.

- [x] **Step 2: Alter `_next_action`**

If `gate_status` is not blocked, accepted baseline exists, and summary exists:

- `accepted` -> `enhancement_accepted`, next action `delivery_complete`
- `preview` -> `enhancement_preview`, next action `review_enhancement_preview`
- `blocked` -> `enhancement_blocked`, next action `fix_enhancement_blockers`

Missing summary keeps `ready_for_enhancement`.

- [x] **Step 3: Run autopilot tests**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest tests\test_photo3d_autopilot.py -q
```

Expected: PASS.

## Task 3: Photo3D Run Loop Summary

**Files:**
- Modify: `tests/test_photo3d_loop.py`
- Modify: `tools/photo3d_loop.py`

- [x] **Step 1: Add failing run-loop test**

Add a test that creates accepted baseline plus `ENHANCEMENT_REPORT.json`, runs `run_photo3d_loop`, and expects:

```python
assert report["status"] == "enhancement_accepted"
assert report["enhancement_summary"]["status"] == "accepted"
assert report["rounds"][0]["enhancement_summary"]["status"] == "accepted"
assert report["next_action"]["kind"] == "delivery_complete"
```

- [x] **Step 2: Implement loop support**

Add terminal statuses `enhancement_accepted`, `enhancement_preview`, `enhancement_blocked`, include `enhancement_summary` at top level and per round, and update `_ordinary_user_message()` for the three statuses.

- [x] **Step 3: Run loop tests**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest tests\test_photo3d_loop.py -q
```

Expected: PASS.

## Task 4: Sync, Docs, Verification

**Files:**
- Generated mirrors: `src/cad_spec_gen/data/tools/photo3d_autopilot.py`, `src/cad_spec_gen/data/tools/photo3d_loop.py`
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`

- [x] **Step 1: Run dev sync**

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' scripts\dev_sync.py
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' scripts\dev_sync.py --check
```

- [x] **Step 2: Run compatibility matrix**

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
```

- [x] **Step 3: Update progress board**

Mark enhancement summary guide as Done, move next recommendation to new user project guide, and record verification.

---

## Self-Review Notes

- Spec coverage: report discovery, accepted/preview/blocked statuses, run loop surfacing, docs, mirrors, and no-scanning invariant are covered.
- Type consistency: `enhancement_summary` is a dict or `None`; statuses use `enhancement_accepted`, `enhancement_preview`, `enhancement_blocked`.
- Boundary consistency: CAD gate remains unchanged; enhancement acceptance is only read after gate pass/warning and accepted baseline.
