# New User Entry Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let ordinary users start `project-guide` with a design document only and receive a safe confirmation-oriented project entry report instead of hand-picking a subsystem first.

**Architecture:** Keep `project-guide` read-only and non-scanning. Add an explicit `--from-design-doc` entry mode that reads only the provided design document path, derives stable subsystem suggestions from the document filename/title with deterministic sanitization, and writes `PROJECT_GUIDE.json` under `.cad-spec-gen/project-guide/`. The report presents candidate subsystem names, confidence, and preview `project-guide --subsystem ... --design-doc ...` actions; it does not initialize, generate specs, run resolver, choose a latest file, or mutate pipeline state beyond writing the guide.

**Tech Stack:** Python 3.10+, pytest, existing `tools.project_guide`, `tools.path_policy`, `cad_pipeline.py`, `scripts/dev_sync.py`.

---

## File Structure

- Modify `tools/project_guide.py`
  - Add `write_project_entry_guide(project_root, design_doc, output_path=None)`.
  - Add helper functions for deterministic document title extraction, subsystem candidate normalization, stage status, and output target.
  - Keep existing `write_project_guide(project_root, subsystem, ...)` behavior unchanged.
- Modify `cad_pipeline.py`
  - Make `project-guide --subsystem` optional only when `--from-design-doc` is present.
  - Dispatch to `write_project_entry_guide()` for entry mode.
  - Update help text to explain design-doc-only mode and confirmation boundary.
- Modify `tests/test_project_guide.py`
  - Add entry-mode tests for report shape, explicit candidate actions, no scan/no mutation flags, and output-path isolation.
- Modify `tests/test_photo3d_user_flow.py`
  - Update CLI help, docs, and metadata assertions.
- Modify docs and metadata
  - `docs/cad-help-guide-zh.md`
  - `.claude/commands/cad-help.md`
  - `skill_cad_help.md`
  - `skill.json`
  - `docs/PROGRESS.md`
  - `docs/superpowers/README.md`
  - generated mirrors under `src/cad_spec_gen/data/*` via `python scripts/dev_sync.py`.

## Contract

`PROJECT_GUIDE.json` entry-mode schema:

- `schema_version: 1`
- `entry_mode: "design_doc"`
- `status: "needs_subsystem_confirmation"`
- `mutates_pipeline_state: false`
- `does_not_scan_directories: true`
- `design_doc.path`: project-relative path
- `subsystem_candidates[]`
  - `subsystem`
  - `source`
  - `confidence`
  - `reason`
- `next_action.kind: "confirm_subsystem"`
- `next_action.requires_user_confirmation: true`
- `next_action.options[]`
  - `subsystem`
  - `argv`: `python cad_pipeline.py project-guide --subsystem <candidate> --design-doc <path>`
  - `cli` only when the candidate is a safe token
- `artifacts.project_guide`: `.cad-spec-gen/project-guide/PROJECT_GUIDE.json` by default

Boundary rules:

- Missing `--from-design-doc` still requires `--subsystem`; existing CLI behavior remains strict.
- Entry mode reads exactly one explicit design doc; it does not scan `docs/design`, `cad/`, render output, or run directories.
- Candidate names are suggestions only; no subsystem is created and no spec/codegen/build command is executed.
- Output must stay under `.cad-spec-gen/project-guide/PROJECT_GUIDE.json` unless explicitly overridden to the same filename inside that directory.

## Tasks

### Task 1: Entry Report API

**Files:**
- Modify: `tests/test_project_guide.py`
- Modify: `tools/project_guide.py`

- [ ] **Step 1: Write the failing test**

Add a test that writes `docs/design/04-升降平台设计.md`, calls `write_project_entry_guide(tmp_path, design_doc)`, and asserts:

```python
assert report["entry_mode"] == "design_doc"
assert report["status"] == "needs_subsystem_confirmation"
assert report["mutates_pipeline_state"] is False
assert report["does_not_scan_directories"] is True
assert report["design_doc"]["path"] == "docs/design/04-升降平台设计.md"
assert report["next_action"]["kind"] == "confirm_subsystem"
assert report["next_action"]["requires_user_confirmation"] is True
assert report["subsystem_candidates"][0]["subsystem"] == "sheng_jiang_ping_tai_she_ji"
assert report["next_action"]["options"][0]["argv"] == [
    "python", "cad_pipeline.py", "project-guide",
    "--subsystem", "sheng_jiang_ping_tai_she_ji",
    "--design-doc", "docs/design/04-升降平台设计.md",
]
assert report["artifacts"]["project_guide"] == ".cad-spec-gen/project-guide/PROJECT_GUIDE.json"
```

- [ ] **Step 2: Verify red**

Run:

```powershell
python -m pytest tests\test_project_guide.py::test_project_entry_guide_suggests_confirmed_subsystem_from_design_doc -q
```

Expected: fails because `write_project_entry_guide` is missing.

- [ ] **Step 3: Implement minimal API**

Add `write_project_entry_guide()` and helpers in `tools/project_guide.py`. Use `unicodedata.normalize()` and a small pinyin map for common Chinese title characters already likely in mechanical design filenames (`升降平台设计`, plus generic fallback to `part_<hex>` for unknown CJK) so behavior is deterministic without external dependencies.

- [ ] **Step 4: Verify green**

Run the same focused test and expect pass.

### Task 2: CLI Entry Mode

**Files:**
- Modify: `tests/test_project_guide.py`
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `cad_pipeline.py`

- [ ] **Step 1: Write failing CLI tests**

Add a test that calls `cad_pipeline.cmd_project_guide(SimpleNamespace(subsystem=None, design_doc=design_doc, from_design_doc=True, artifact_index=None, output=None))` and asserts return code `0`, report status `needs_subsystem_confirmation`, and output `.cad-spec-gen/project-guide/PROJECT_GUIDE.json`.

Update help assertions to include `--from-design-doc`, `needs_subsystem_confirmation`, and `confirm_subsystem`.

- [ ] **Step 2: Verify red**

Run:

```powershell
python -m pytest tests\test_project_guide.py::test_project_guide_cli_from_design_doc_writes_entry_report tests\test_photo3d_user_flow.py::test_project_guide_help_explains_read_only_user_flow -q
```

Expected: fails because CLI has no `--from-design-doc` and still requires `--subsystem`.

- [ ] **Step 3: Implement CLI dispatch**

Update `cmd_project_guide()` to call `write_project_entry_guide()` only when `args.from_design_doc` is true. Keep the old `--subsystem` error for normal mode. Add argparse flag:

```python
p_project_guide.add_argument(
    "--from-design-doc",
    action="store_true",
    help="Start from one explicit design document and ask the user to confirm a subsystem candidate",
)
```

- [ ] **Step 4: Verify green**

Run the same focused tests and expect pass.

### Task 3: Docs, Metadata, Mirrors

**Files:**
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `.claude/commands/cad-help.md`
- Modify: `skill_cad_help.md`
- Modify: `skill.json`
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`
- Modify generated mirrors via `python scripts/dev_sync.py`

- [ ] **Step 1: Write failing docs/metadata tests**

Extend existing assertions in `tests/test_photo3d_user_flow.py` so project-guide help/docs/metadata mention design-doc-only entry mode, `--from-design-doc`, and `needs_subsystem_confirmation`.

- [ ] **Step 2: Verify red**

Run:

```powershell
python -m pytest tests\test_photo3d_user_flow.py -q
```

Expected: fails on missing docs/metadata strings.

- [ ] **Step 3: Update docs and metadata**

Document that ordinary users may start with:

```powershell
python cad_pipeline.py project-guide --from-design-doc --design-doc <path>
```

Then they choose one suggested subsystem and run the previewed `project-guide --subsystem ... --design-doc ...` command.

- [ ] **Step 4: Sync mirrors and verify**

Run:

```powershell
python scripts\dev_sync.py
python scripts\dev_sync.py --check
python -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
git diff --check
```

Expected: all pass; only pre-existing pytest `env` warning may remain.

## Self-Review

- Spec coverage: The plan covers design-doc-only entry, confirmation boundary, no scanning, CLI, docs, metadata, progress board, and mirrors.
- Placeholder scan: No TBD/TODO placeholders remain.
- Type consistency: Public function names are `write_project_entry_guide()` and existing `write_project_guide()`; CLI flag is consistently `--from-design-doc`; status is consistently `needs_subsystem_confirmation`; next-action kind is `confirm_subsystem`.
