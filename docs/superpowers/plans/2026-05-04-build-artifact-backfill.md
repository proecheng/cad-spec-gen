# Build Artifact Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `photo3d-recover build` copy and register all stable build evidence for the current active run, without scanning for newest files or adding product-specific shortcuts.

**Architecture:** Keep `ARTIFACT_INDEX.json` as the only recovery state source. After a successful build, copy required run-native JSON artifacts from exact `cad/output/runs/<run_id>/` paths, and copy optional assembly deliverables from deterministic `cad/output` candidates into `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/`. Optional artifacts are only registered when an exact configured or unambiguous current build artifact exists.

**Tech Stack:** Python 3.10+, pytest, existing `tools/photo3d_recover.py`, `scripts/dev_sync.py` generated mirrors.

---

## File Structure

- Modify `tests/test_photo3d_recover.py`: add focused TDD coverage for build backfill behavior.
- Modify `tools/photo3d_recover.py`: add generic artifact copy helpers and build output candidate resolution.
- Generated mirror `src/cad_spec_gen/data/tools/photo3d_recover.py`: update only via `python scripts/dev_sync.py`.
- Modify `docs/PROGRESS.md`: mark this round done, record verification, and advance next recommendations.

## Invariants

- `run_id` must equal `active_run_id`; recovery must not switch or create an active run.
- Required build artifact remains `ASSEMBLY_SIGNATURE.json`; build recovery fails if it is absent from `cad/output/runs/<run_id>/`.
- `ASSEMBLY_REPORT.json` is optional but deterministic: only copy from `cad/output/runs/<run_id>/ASSEMBLY_REPORT.json`.
- `MODEL_CONTRACT.json` refresh is optional and deterministic: copy from `cad/<subsystem>/.cad-spec-gen/MODEL_CONTRACT.json` when present after build.
- GLB/STEP are optional assembly deliverables: prefer `cad/<subsystem>/render_config.json` `subsystem.glb_file`; derive matching STEP from that GLB stem; otherwise register only when `cad/output/*_assembly.glb` or `cad/output/*_assembly.step` has exactly one candidate.
- Never choose by mtime, newest file, default subsystem prefix, or device-specific name.
- Never register an optional artifact unless the copied target path exists in the current run directory.

## Task 1: TDD Build Backfill Coverage

**Files:**
- Modify: `tests/test_photo3d_recover.py`

- [x] **Step 1: Add failing test for required and optional build artifacts**

Append this test to `tests/test_photo3d_recover.py`:

```python
def test_photo3d_recover_build_backfills_current_run_build_artifacts(tmp_path):
    from tools.photo3d_recover import run_photo3d_recover

    fixture = _contracts(tmp_path)
    output_dir = tmp_path / "cad" / "output"
    run_output_dir = output_dir / "runs" / "RUN001"
    _write_json(run_output_dir / "ASSEMBLY_SIGNATURE.json", {"schema_version": 1, "source_mode": "runtime"})
    _write_json(run_output_dir / "ASSEMBLY_REPORT.json", {"summary": "0 WARNING"})
    _write_json(
        tmp_path / "cad" / "demo" / ".cad-spec-gen" / "MODEL_CONTRACT.json",
        {"schema_version": 1, "refreshed": True},
    )
    (tmp_path / "cad" / "demo" / "render_config.json").write_text(
        json.dumps({"subsystem": {"glb_file": "DEMO-000_assembly.glb"}}),
        encoding="utf-8",
    )
    (output_dir / "DEMO-000_assembly.glb").write_bytes(b"glb")
    (output_dir / "DEMO-000_assembly.step").write_text("STEP", encoding="utf-8")

    report = run_photo3d_recover(
        tmp_path,
        "demo",
        "RUN001",
        artifact_index_path=fixture["index_path"],
        action="build",
        build_runner=lambda args: 0,
    )

    assert report["returncode"] == 0
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    artifacts = index["runs"]["RUN001"]["artifacts"]
    assert artifacts["assembly_signature"] == "cad/demo/.cad-spec-gen/runs/RUN001/ASSEMBLY_SIGNATURE.json"
    assert artifacts["assembly_report"] == "cad/demo/.cad-spec-gen/runs/RUN001/ASSEMBLY_REPORT.json"
    assert artifacts["model_contract"] == "cad/demo/.cad-spec-gen/runs/RUN001/MODEL_CONTRACT.json"
    assert artifacts["assembly_glb"] == "cad/demo/.cad-spec-gen/runs/RUN001/DEMO-000_assembly.glb"
    assert artifacts["assembly_step"] == "cad/demo/.cad-spec-gen/runs/RUN001/DEMO-000_assembly.step"
    assert (fixture["run_dir"] / "ASSEMBLY_REPORT.json").is_file()
    assert (fixture["run_dir"] / "MODEL_CONTRACT.json").is_file()
    assert (fixture["run_dir"] / "DEMO-000_assembly.glb").read_bytes() == b"glb"
    assert (fixture["run_dir"] / "DEMO-000_assembly.step").read_text(encoding="utf-8") == "STEP"
```

- [x] **Step 2: Run the new test and verify RED**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest tests\test_photo3d_recover.py::test_photo3d_recover_build_backfills_current_run_build_artifacts -q
```

Expected: FAIL because `assembly_report`, `assembly_glb`, and `assembly_step` are not registered.

- [x] **Step 3: Add failing test for ambiguous GLB/STEP candidates**

Append this test:

```python
def test_photo3d_recover_build_does_not_guess_ambiguous_assembly_deliverables(tmp_path):
    from tools.photo3d_recover import run_photo3d_recover

    fixture = _contracts(tmp_path)
    output_dir = tmp_path / "cad" / "output"
    run_output_dir = output_dir / "runs" / "RUN001"
    _write_json(run_output_dir / "ASSEMBLY_SIGNATURE.json", {"schema_version": 1, "source_mode": "runtime"})
    (output_dir / "A-000_assembly.glb").write_bytes(b"a")
    (output_dir / "B-000_assembly.glb").write_bytes(b"b")
    (output_dir / "A-000_assembly.step").write_text("A", encoding="utf-8")
    (output_dir / "B-000_assembly.step").write_text("B", encoding="utf-8")

    report = run_photo3d_recover(
        tmp_path,
        "demo",
        "RUN001",
        artifact_index_path=fixture["index_path"],
        action="build",
        build_runner=lambda args: 0,
    )

    assert report["returncode"] == 0
    index = json.loads(fixture["index_path"].read_text(encoding="utf-8"))
    artifacts = index["runs"]["RUN001"]["artifacts"]
    assert "assembly_glb" not in artifacts
    assert "assembly_step" not in artifacts
```

- [x] **Step 4: Run the ambiguity test and verify RED or protect existing absence**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest tests\test_photo3d_recover.py::test_photo3d_recover_build_does_not_guess_ambiguous_assembly_deliverables -q
```

Expected: PASS under current code only because deliverables are not implemented yet. Keep it as a guardrail for the next implementation step.

## Task 2: Implement Generic Backfill Helpers

**Files:**
- Modify: `tools/photo3d_recover.py`

- [x] **Step 1: Add imports and constants**

Change the imports at the top of `tools/photo3d_recover.py` to include `json`, and add artifact candidate constants near `RECOVERY_ACTIONS`:

```python
import json
import re
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any, Callable
```

```python
RUN_BUILD_JSON_ARTIFACTS = (
    ("assembly_signature", "ASSEMBLY_SIGNATURE.json", True),
    ("assembly_report", "ASSEMBLY_REPORT.json", False),
)
BUILD_PROJECT_JSON_ARTIFACTS = (
    (
        "model_contract",
        Path("cad") / "{subsystem}" / ".cad-spec-gen" / "MODEL_CONTRACT.json",
        "MODEL_CONTRACT.json",
    ),
)
```

- [x] **Step 2: Replace build post-processing block**

Replace the single `_copy_run_output_artifact(...)` call in the `action == "build"` branch with:

```python
        if not _backfill_build_artifacts(root, subsystem, run_id, run_dir, artifacts):
            return _report(index_path, subsystem, run_id, action, 1, artifacts)
```

- [x] **Step 3: Add helper implementations**

Add these helpers after `_copy_run_output_artifact(...)`:

```python
def _backfill_build_artifacts(
    root: Path,
    subsystem: str,
    run_id: str,
    run_dir: Path,
    artifacts: dict[str, str],
) -> bool:
    output_dir = root / "cad" / "output"
    run_output_dir = output_dir / "runs" / run_id
    for artifact_key, filename, required in RUN_BUILD_JSON_ARTIFACTS:
        copied = _copy_run_output_artifact(
            root,
            source=run_output_dir / filename,
            target=run_dir / filename,
            artifact_key=artifact_key,
            artifacts=artifacts,
        )
        if required and not copied:
            return False

    for artifact_key, source_template, filename in BUILD_PROJECT_JSON_ARTIFACTS:
        source = root / Path(str(source_template).format(subsystem=subsystem))
        _copy_run_output_artifact(
            root,
            source=source,
            target=run_dir / filename,
            artifact_key=artifact_key,
            artifacts=artifacts,
        )

    for artifact_key, source in _assembly_deliverable_sources(root, subsystem):
        _copy_run_output_artifact(
            root,
            source=source,
            target=run_dir / source.name,
            artifact_key=artifact_key,
            artifacts=artifacts,
        )
    return True
```

```python
def _assembly_deliverable_sources(root: Path, subsystem: str) -> list[tuple[str, Path]]:
    output_dir = root / "cad" / "output"
    configured_glb = _configured_assembly_glb(root, subsystem)
    if configured_glb:
        result = [("assembly_glb", configured_glb)]
        configured_step = configured_glb.with_suffix(".step")
        if configured_step.is_file():
            result.append(("assembly_step", configured_step))
        return result

    result: list[tuple[str, Path]] = []
    unique_glb = _unique_assembly_deliverable(output_dir, ".glb")
    if unique_glb:
        result.append(("assembly_glb", unique_glb))
    unique_step = _unique_assembly_deliverable(output_dir, ".step")
    if unique_step:
        result.append(("assembly_step", unique_step))
    return result
```

```python
def _configured_assembly_glb(root: Path, subsystem: str) -> Path | None:
    config_path = root / "cad" / subsystem / "render_config.json"
    if not config_path.is_file():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    glb_file = ((config.get("subsystem") or {}).get("glb_file") or "")
    if not isinstance(glb_file, str) or not glb_file:
        return None
    candidate = Path(glb_file)
    if candidate.is_absolute():
        try:
            assert_within_project(candidate.resolve(), root, "configured assembly glb")
        except ValueError:
            return None
        resolved = candidate.resolve()
    else:
        if candidate.name != glb_file or candidate.name in {".", ".."}:
            return None
        resolved = (root / "cad" / "output" / candidate.name).resolve()
    if not resolved.is_file():
        return None
    return resolved
```

```python
def _unique_assembly_deliverable(output_dir: Path, suffix: str) -> Path | None:
    candidates = sorted(output_dir.glob(f"*_assembly{suffix}"))
    candidates = [path.resolve() for path in candidates if path.is_file()]
    if len(candidates) != 1:
        return None
    return candidates[0]
```

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest tests\test_photo3d_recover.py -q
```

Expected: all `test_photo3d_recover.py` tests pass.

## Task 3: Sync Mirrors And Compatibility Checks

**Files:**
- Modify generated mirror by command: `src/cad_spec_gen/data/tools/photo3d_recover.py`

- [x] **Step 1: Run dev sync**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' scripts\dev_sync.py
```

Expected: generated mirror updates if needed.

- [x] **Step 2: Verify sync**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' scripts\dev_sync.py --check
```

Expected: PASS.

- [x] **Step 3: Run Photo3D compatibility matrix**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest tests\test_photo3d_recover.py tests\test_photo3d_action_runner.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
```

Expected: PASS.

## Task 4: Documentation And Final Verification

**Files:**
- Modify: `docs/PROGRESS.md`

- [x] **Step 1: Update progress board**

Change `docs/PROGRESS.md`:

```markdown
| Done | Build artifact backfill | 恢复动作后把更多运行时证据登记回当前 run | `photo3d-recover build` 成功后回填当前 run 的 `ASSEMBLY_SIGNATURE.json`、`ASSEMBLY_REPORT.json`、刷新后的 `MODEL_CONTRACT.json`、确定的装配 GLB/STEP；optional 产物只在精确路径或唯一候选存在时登记 | 下一步把 `ENHANCEMENT_REPORT.json` 摘要接入 `photo3d-run` / 项目向导 |
```

Update current status and next-step list so build artifact backfill is no longer listed as next.

- [x] **Step 2: Run full tests when feasible**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' -m pytest -q
```

Expected: PASS. If generated CAD noise appears under `cad/lifting_platform/std_*.py`, inspect it and clean only known test-generated noise before final status.

- [x] **Step 3: Final sync check**

Run:

```powershell
& 'D:\Work\cad-spec-gen\.venv\Scripts\python.exe' scripts\dev_sync.py --check
```

Expected: PASS.

---

## Self-Review Notes

- Spec coverage: all requested backfill artifacts are covered without making them required except the runtime signature that already gates Photo3D.
- Placeholder scan: no `TBD` or open-ended implementation placeholders remain.
- Type/path consistency: artifact keys are `assembly_report`, `assembly_glb`, `assembly_step`, and existing `model_contract` / `assembly_signature`; all copied targets are under `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/`.
