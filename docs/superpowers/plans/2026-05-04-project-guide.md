# Project Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only `project-guide` command that tells ordinary users and LLM agents the next safe CAD/Photo3D action for a subsystem without scanning for newest artifacts or mutating pipeline state.

**Architecture:** Add a focused `tools/project_guide.py` decision layer that reads only explicit inputs and fixed subsystem contract paths. The guide writes `PROJECT_GUIDE.json` beside the current run when an active run exists, otherwise under `cad/<subsystem>/.cad-spec-gen/`, and returns a single `next_action.argv` suitable for LLM-controlled follow-up.

**Tech Stack:** Python stdlib, existing `tools.contract_io`, `tools.path_policy`, `tools.photo3d_loop` report contracts, `cad_pipeline.py` argparse dispatch, `scripts/dev_sync.py`.

---

## Boundary Rules

- `project-guide` is read-only except for writing its own `PROJECT_GUIDE.json`.
- It does not run `init`, `spec`, `codegen`, `build`, `render`, `photo3d-run`, `accept-baseline`, `enhance`, or `enhance-check`.
- It does not scan directories for newest renders, latest reports, or newest run folders.
- It uses only:
  - explicit `--subsystem`
  - optional explicit `--design-doc`
  - optional explicit `--artifact-index`
  - fixed paths such as `cad/<subsystem>/CAD_SPEC.md`, `cad/<subsystem>/build_all.py`, and `cad/<subsystem>/.cad-spec-gen/ARTIFACT_INDEX.json`
  - current `active_run_id` inside the explicitly resolved artifact index
- It treats missing inputs as user-facing stages, not as reasons to guess.

## File Map

- Create `tools/project_guide.py`
  - Responsibility: pure-ish read-only stage detection, next action selection, `PROJECT_GUIDE.json` writing.
- Modify `cad_pipeline.py`
  - Responsibility: register `project-guide` CLI, dispatch to `tools.project_guide`.
- Modify `hatch_build.py`
  - Responsibility: include `project_guide.py` in Photo3D tool mirror coverage if needed through `tools/` copy already covered; no flat python-tools change needed.
- Modify `skill.json`
  - Responsibility: advertise `project_guide` for installed skill metadata and AGENTS.md generation.
- Modify `skill_cad_help.md`, `docs/cad-help-guide-zh.md`, `.claude/commands/cad-help.md`
  - Responsibility: document ordinary-user first command and strict no-scan/no-mutate boundary.
- Modify `tests/test_project_guide.py`
  - Responsibility: unit/CLI coverage for stage selection, path binding, and non-mutation behavior.
- Modify `tests/test_photo3d_user_flow.py`
  - Responsibility: help/metadata/docs coverage for `project-guide`.
- Modify `tests/test_photo3d_packaging_sync.py`
  - Responsibility: include `project_guide.py` in contract tool mirror set.
- Modify `docs/PROGRESS.md`, `docs/superpowers/README.md`
  - Responsibility: board and index update at the end of the round.

## Task 1: Add Failing Project Guide Tests

**Files:**
- Create: `tests/test_project_guide.py`

- [ ] **Step 1: Write failing tests for first-run and active-run guide behavior**

```python
import json
from pathlib import Path
from types import SimpleNamespace


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_project_guide_recommends_init_when_subsystem_is_missing(tmp_path):
    from tools.project_guide import write_project_guide

    report = write_project_guide(tmp_path, "demo")

    assert report["status"] == "needs_init"
    assert report["next_action"]["kind"] == "run_init"
    assert report["next_action"]["argv"] == [
        "python",
        "cad_pipeline.py",
        "init",
        "--subsystem",
        "demo",
    ]
    assert report["mutates_pipeline_state"] is False
    assert report["artifacts"]["project_guide"] == "cad/demo/.cad-spec-gen/PROJECT_GUIDE.json"


def test_project_guide_uses_explicit_design_doc_for_spec(tmp_path):
    from tools.project_guide import write_project_guide

    subsystem_dir = tmp_path / "cad" / "demo"
    subsystem_dir.mkdir(parents=True)
    design_doc = tmp_path / "docs" / "design" / "demo.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# demo", encoding="utf-8")

    report = write_project_guide(tmp_path, "demo", design_doc=design_doc)

    assert report["status"] == "needs_spec"
    assert report["next_action"]["kind"] == "run_spec"
    assert report["next_action"]["argv"] == [
        "python",
        "cad_pipeline.py",
        "spec",
        "--subsystem",
        "demo",
        "--design-doc",
        "docs/design/demo.md",
    ]


def test_project_guide_does_not_guess_design_doc_when_missing(tmp_path):
    from tools.project_guide import write_project_guide

    (tmp_path / "cad" / "demo").mkdir(parents=True)

    report = write_project_guide(tmp_path, "demo")

    assert report["status"] == "needs_design_doc"
    assert report["next_action"]["kind"] == "provide_design_doc"
    assert "argv" not in report["next_action"]


def test_project_guide_routes_active_run_to_photo3d_run_without_switching_run(tmp_path):
    from tools.project_guide import write_project_guide

    run_dir = tmp_path / "cad" / "demo" / ".cad-spec-gen" / "runs" / "RUN001"
    run_dir.mkdir(parents=True)
    _write_json(
        tmp_path / "cad" / "demo" / ".cad-spec-gen" / "ARTIFACT_INDEX.json",
        {
            "schema_version": 1,
            "subsystem": "demo",
            "active_run_id": "RUN001",
            "accepted_baseline_run_id": None,
            "runs": {"RUN001": {"run_id": "RUN001", "active": True, "artifacts": {}}},
        },
    )
    for name in ("CAD_SPEC.md", "params.py", "build_all.py", "assembly.py"):
        (tmp_path / "cad" / "demo" / name).write_text("ok", encoding="utf-8")

    report = write_project_guide(tmp_path, "demo")

    assert report["status"] == "ready_for_photo3d_run"
    assert report["run_id"] == "RUN001"
    assert report["next_action"]["kind"] == "run_photo3d_guide"
    assert report["next_action"]["argv"] == [
        "python",
        "cad_pipeline.py",
        "photo3d-run",
        "--subsystem",
        "demo",
        "--artifact-index",
        "cad/demo/.cad-spec-gen/ARTIFACT_INDEX.json",
    ]
    written_index = json.loads(
        (tmp_path / "cad" / "demo" / ".cad-spec-gen" / "ARTIFACT_INDEX.json").read_text(
            encoding="utf-8"
        )
    )
    assert written_index["active_run_id"] == "RUN001"
    assert (run_dir / "PROJECT_GUIDE.json").is_file()


def test_project_guide_cli_writes_report(tmp_path, monkeypatch):
    import cad_pipeline

    monkeypatch.setattr(cad_pipeline, "PROJECT_ROOT", str(tmp_path))

    rc = cad_pipeline.cmd_project_guide(
        SimpleNamespace(
            subsystem="demo",
            design_doc=None,
            artifact_index=None,
            output=None,
        )
    )

    assert rc == 0
    report = json.loads(
        (tmp_path / "cad" / "demo" / ".cad-spec-gen" / "PROJECT_GUIDE.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "needs_init"
```

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_project_guide.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.project_guide'` or missing `cmd_project_guide`.

## Task 2: Implement Read-Only Project Guide

**Files:**
- Create: `tools/project_guide.py`
- Modify: `cad_pipeline.py`

- [ ] **Step 1: Implement `tools/project_guide.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.contract_io import load_json_required, write_json_atomic
from tools.path_policy import assert_within_project, project_relative


def write_project_guide(
    project_root: str | Path,
    subsystem: str,
    *,
    design_doc: str | Path | None = None,
    artifact_index_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    ...
```

Implement exact behavior:

- Resolve every input through `assert_within_project`.
- If `cad/<subsystem>/` is missing:
  - status `needs_init`
  - next action `init --subsystem <name>`
  - output `cad/<subsystem>/.cad-spec-gen/PROJECT_GUIDE.json`
- If `CAD_SPEC.md` is missing and `--design-doc` is missing:
  - status `needs_design_doc`
  - next action kind `provide_design_doc`
- If `CAD_SPEC.md` is missing and `--design-doc` is present:
  - status `needs_spec`
  - next action `spec --subsystem <name> --design-doc <rel>`
- If core codegen files are missing:
  - status `needs_codegen`
  - next action `codegen --subsystem <name>`
- If no active artifact index exists:
  - status `needs_build_render`
  - next action `build --subsystem <name> --render`
- If artifact index exists:
  - require `index["subsystem"] == subsystem`
  - if `active_run_id` is empty or run entry inactive:
    - status `needs_build_render`
  - otherwise:
    - status `ready_for_photo3d_run`
    - run_id = active run id
    - next action `photo3d-run --subsystem <name> --artifact-index <rel>`
    - output goes to `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/PROJECT_GUIDE.json`

Every report includes:

```python
{
    "schema_version": 1,
    "generated_at": "...",
    "subsystem": subsystem,
    "run_id": run_id_or_none,
    "status": status,
    "ordinary_user_message": "...",
    "mutates_pipeline_state": False,
    "does_not_scan_directories": True,
    "stage_status": {...},
    "next_action": {...},
    "artifacts": {"project_guide": "...", "artifact_index": "... if present"},
}
```

- [ ] **Step 2: Register CLI in `cad_pipeline.py`**

Add:

```python
def cmd_project_guide(args):
    from tools.project_guide import command_return_code_for_project_guide, write_project_guide

    report = write_project_guide(
        PROJECT_ROOT,
        args.subsystem,
        design_doc=getattr(args, "design_doc", None),
        artifact_index_path=getattr(args, "artifact_index", None),
        output_path=getattr(args, "output", None),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return command_return_code_for_project_guide(report)
```

Register parser:

```python
p_project_guide = sub.add_parser(
    "project-guide",
    help="Read-only ordinary-user project next-step guide",
    ...
)
p_project_guide.add_argument("--subsystem", "-s", required=True)
p_project_guide.add_argument("--design-doc", default=None)
p_project_guide.add_argument("--artifact-index", default=None)
p_project_guide.add_argument("--output", default=None)
```

Add dispatch key `"project-guide": cmd_project_guide`.

- [ ] **Step 3: Run tests to verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\test_project_guide.py -q`

Expected: `5 passed`.

## Task 3: Add Help, Metadata, and Mirror Coverage

**Files:**
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `tests/test_photo3d_packaging_sync.py`
- Modify: `skill.json`
- Modify: `skill_cad_help.md`
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `.claude/commands/cad-help.md`

- [ ] **Step 1: Add failing user-flow tests**

Add assertions:

```python
def test_project_guide_help_explains_read_only_user_flow():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "project-guide", "--help"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    help_text = result.stdout
    for term in (
        "project-guide",
        "PROJECT_GUIDE.json",
        "普通用户",
        "大模型",
        "read-only",
        "does not scan directories",
        "does not mutate pipeline state",
        "photo3d-run",
        "enhance-check",
        "accept-baseline",
    ):
        assert term in help_text
```

Update metadata test to require `project_guide`.

Update packaging sync set to include `project_guide.py`.

- [ ] **Step 2: Run user-flow tests to verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q`

Expected: FAIL because help/metadata/mirror docs do not mention `project-guide`.

- [ ] **Step 3: Update metadata/docs**

Add `project_guide` tool to `skill.json`:

```json
{
  "name": "project_guide",
  "description": "Read-only ordinary-user and LLM project guide: writes PROJECT_GUIDE.json, selects the next safe command across init/spec/codegen/build-render/photo3d-run/enhance-check/accept-baseline handoff, uses explicit subsystem/design-doc/artifact-index inputs, does not scan directories, and does not mutate pipeline state.",
  "cli": "python cad_pipeline.py project-guide --subsystem <name> --design-doc <path>"
}
```

Document in the three CAD help docs that the first command for ordinary users is:

```bash
python cad_pipeline.py project-guide --subsystem <name> --design-doc <path>
```

- [ ] **Step 4: Run `scripts/dev_sync.py`**

Run: `.venv\Scripts\python.exe scripts\dev_sync.py`

Expected: mirrors update, exit 1 if files were changed.

- [ ] **Step 5: Run user-flow tests to verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q`

Expected: pass.

## Task 4: Verification, Board Update, Commit

**Files:**
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`

- [ ] **Step 1: Run focused regression matrix**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run sync check**

Run: `.venv\Scripts\python.exe scripts\dev_sync.py --check`

Expected: `dev_sync: all mirrors up to date.`

- [ ] **Step 3: Update board and index**

Update `docs/PROGRESS.md`:

- latest feature baseline: `feat(project-guide): 增加只读项目向导`
- board item Done: `新用户项目向导`
- next recommendation moves to `常用模型库扩展`
- verification records include focused matrix and sync check.

Update `docs/superpowers/README.md`:

- add this plan to the main document table.
- update current queue to show `project-guide` complete.

- [ ] **Step 4: Commit**

Run:

```powershell
git status --short
git add tools/project_guide.py cad_pipeline.py tests/test_project_guide.py tests/test_photo3d_user_flow.py tests/test_photo3d_packaging_sync.py skill.json skill_cad_help.md docs/cad-help-guide-zh.md .claude/commands/cad-help.md src/cad_spec_gen/data docs/PROGRESS.md docs/superpowers/README.md docs/superpowers/plans/2026-05-04-project-guide.md AGENTS.md
git commit -m "feat(project-guide): 增加只读项目向导"
```

- [ ] **Step 5: Final status**

Run:

```powershell
git status --short --branch
git log -1 --oneline
```

Expected: branch clean, latest commit is the feature commit.

