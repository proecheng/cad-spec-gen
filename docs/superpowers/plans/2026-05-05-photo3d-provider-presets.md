# Photo3D Provider Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe Photo3D enhancement provider presets so ordinary users and LLM agents can choose a known enhancement route without hand-writing backend/model arguments.

**Architecture:** Provider presets are a small whitelist shared by `photo3d-autopilot` and `photo3d-handoff`. Autopilot exposes the available presets and the default recommendation as structured data; handoff rebuilds trusted argv from `ARTIFACT_INDEX.json`, the active run id, the current render directory, and a known preset. JSON-reported argv remains advisory and is never executed directly.

**Tech Stack:** Python 3.10+, argparse CLI, existing Photo3D run artifacts, pytest, `scripts/dev_sync.py` packaged mirror sync.

---

## File Map

| File | Responsibility |
| --- | --- |
| `tools/photo3d_provider_presets.py` | New shared preset catalog and whitelist helpers. |
| `tools/photo3d_autopilot.py` | Attach `provider_presets` and `default_provider_preset` to `run_enhancement` next actions. |
| `tools/photo3d_handoff.py` | Accept an optional provider preset and append only trusted backend/model flags for `run_enhancement`. |
| `cad_pipeline.py` | Add `photo3d-handoff --provider-preset` and pass it to the handoff tool. |
| `tests/test_photo3d_autopilot.py` | Prove ready-for-enhancement reports expose structured provider choices. |
| `tests/test_photo3d_handoff.py` | Prove preview/confirm use trusted presets and reject unknown or malicious preset input. |
| `tests/test_photo3d_user_flow.py` | Prove CLI help explains provider presets to ordinary users/LLMs. |
| `tests/test_photo3d_packaging_sync.py` | Include the new preset module in packaged mirror coverage. |
| `docs/PROGRESS.md` | Round-end user board update. |
| `docs/superpowers/README.md` | Planning index update. |

## Preset Contract

Preset ids are stable machine values:

| id | backend | model | Use |
| --- | --- | --- | --- |
| `default` | none | none | Use project or environment enhancement config exactly as today. |
| `engineering` | `engineering` | none | Local/low-risk engineering preview route. |
| `gemini` | `gemini` | none | Existing Gemini cloud backend. |
| `fal` | `fal` | none | Existing fal backend. |
| `fal_comfy` | `fal_comfy` | none | Existing fal Comfy backend. |
| `comfyui` | `comfyui` | none | Existing local ComfyUI backend. |

No OpenClaude URL, API key, or future model name is embedded. A future `gpt-image-2-pro` route must first add a real `cad_pipeline.py enhance` backend or provider adapter and tests; until then it is not a preset.

## Tasks

### Task 1: Autopilot Exposes Provider Presets

**Files:**
- Modify: `tests/test_photo3d_autopilot.py`
- Create: `tools/photo3d_provider_presets.py`
- Modify: `tools/photo3d_autopilot.py`
- Modify: `tests/test_photo3d_packaging_sync.py`

- [ ] **Step 1: Write the failing test**

Add assertions to `test_cmd_photo3d_autopilot_with_accepted_baseline_recommends_enhancement`:

```python
    presets = report["next_action"]["provider_presets"]
    assert report["next_action"]["default_provider_preset"] == "default"
    assert [preset["id"] for preset in presets] == [
        "default",
        "engineering",
        "gemini",
        "fal",
        "fal_comfy",
        "comfyui",
    ]
    assert presets[0]["backend"] is None
    assert presets[1]["argv_suffix"] == ["--backend", "engineering"]
```

- [ ] **Step 2: Run red test**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_autopilot.py::test_cmd_photo3d_autopilot_with_accepted_baseline_recommends_enhancement -q
```

Expected: fail because `provider_presets` is missing.

- [ ] **Step 3: Implement the shared preset catalog**

Create `tools/photo3d_provider_presets.py` with a frozen catalog, `public_provider_presets()`, and `trusted_provider_argv_suffix(preset_id)`.

- [ ] **Step 4: Attach presets in autopilot**

In `tools/photo3d_autopilot.py`, import `DEFAULT_PROVIDER_PRESET` and `public_provider_presets`, then add:

```python
"default_provider_preset": DEFAULT_PROVIDER_PRESET,
"provider_presets": public_provider_presets(),
```

only to `run_enhancement` actions.

- [ ] **Step 5: Add packaging coverage**

Add `photo3d_provider_presets.py` to `PHOTO3D_CONTRACT_TOOL_FILES`.

- [ ] **Step 6: Run green test**

Run the same focused autopilot test. Expected: pass.

### Task 2: Handoff Uses Only Trusted Presets

**Files:**
- Modify: `tests/test_photo3d_handoff.py`
- Modify: `tools/photo3d_handoff.py`
- Modify: `cad_pipeline.py`

- [ ] **Step 1: Write failing tests**

Add tests that prove:

```python
report = handoff.run_photo3d_handoff(
    tmp_path,
    "demo",
    artifact_index_path=fixture["index_path"],
    source="run",
    provider_preset="engineering",
)
assert report["selected_action"]["provider_preset"]["id"] == "engineering"
assert report["selected_action"]["argv"][-2:] == ["--backend", "engineering"]
```

and:

```python
report = handoff.run_photo3d_handoff(
    tmp_path,
    "demo",
    artifact_index_path=fixture["index_path"],
    source="run",
    confirm=True,
    provider_preset="gpt-image-2-pro",
)
assert report["status"] == "needs_manual_review"
assert "unknown provider preset" in report["selected_action"]["reason"]
```

and:

```python
_write_photo3d_run(
    fixture,
    {
        "kind": "run_enhancement",
        "provider_preset": "engineering",
        "argv": ["python", "cad_pipeline.py", "enhance", "--backend", "gemini"],
    },
    status="ready_for_enhancement",
)
report = handoff.run_photo3d_handoff(..., confirm=True)
assert report["executed_action"]["argv"][-2:] == ["--backend", "engineering"]
```

- [ ] **Step 2: Run red tests**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_handoff.py -q
```

Expected: fail because `provider_preset` is not accepted or not added to argv.

- [ ] **Step 3: Add handoff argument and validation**

Add `provider_preset: str | None = None` to `run_photo3d_handoff`, thread it into `_classify_next_action`, and validate with `trusted_provider_argv_suffix()`.

- [ ] **Step 4: Rebuild trusted enhancement argv with suffix**

Extend `_trusted_argv(..., provider_preset)` so `run_enhancement` appends only the trusted suffix. `default` appends nothing.

- [ ] **Step 5: Preserve public report clarity**

Expose `provider_preset` in `selected_action` as a public preset dict. Unknown preset returns `classification: manual`, status `needs_manual_review`, and never runs subprocess.

- [ ] **Step 6: Add CLI flag**

In `cad_pipeline.py`, add:

```python
p_photo3d_handoff.add_argument(
    "--provider-preset",
    default=None,
    help="Enhancement provider preset for run_enhancement: default, engineering, gemini, fal, fal_comfy, comfyui",
)
```

and pass it to `run_photo3d_handoff`.

- [ ] **Step 7: Run green tests**

Run focused handoff tests. Expected: pass.

### Task 3: Help, Sync, Docs, Verification

**Files:**
- Modify: `tests/test_photo3d_user_flow.py`
- Modify: `docs/cad-help-guide-zh.md`
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`

- [ ] **Step 1: Write failing help test**

Add `--provider-preset`, `provider preset`, and `engineering` to `test_photo3d_handoff_help_explains_confirmed_handoff_flow`.

- [ ] **Step 2: Run red help test**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_user_flow.py::test_photo3d_handoff_help_explains_confirmed_handoff_flow -q
```

Expected: fail until CLI help text includes provider presets.

- [ ] **Step 3: Update docs**

Update `docs/cad-help-guide-zh.md` to show:

```powershell
python cad_pipeline.py photo3d-handoff --subsystem <name> --provider-preset engineering
python cad_pipeline.py photo3d-handoff --subsystem <name> --provider-preset engineering --confirm
```

and state that preset ids are whitelisted and do not allow arbitrary backend/model strings.

- [ ] **Step 4: Run sync**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
```

Expected: sync updates packaged mirrors; check passes.

- [ ] **Step 5: Run focused verification**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
git diff --check
```

Expected: all tests pass; no whitespace errors.

- [ ] **Step 6: Update board and index**

Update `docs/PROGRESS.md` and `docs/superpowers/README.md` with the current branch, feature, verification results, and next-step recommendations.

- [ ] **Step 7: Commit, merge, push, clean**

Run:

```powershell
git add tools/photo3d_provider_presets.py tools/photo3d_autopilot.py tools/photo3d_handoff.py cad_pipeline.py tests/test_photo3d_autopilot.py tests/test_photo3d_handoff.py tests/test_photo3d_user_flow.py tests/test_photo3d_packaging_sync.py docs/cad-help-guide-zh.md docs/PROGRESS.md docs/superpowers/README.md docs/superpowers/plans/2026-05-05-photo3d-provider-presets.md src/cad_spec_gen/data/tools/photo3d_provider_presets.py src/cad_spec_gen/data/tools/photo3d_autopilot.py src/cad_spec_gen/data/tools/photo3d_handoff.py src/cad_spec_gen/data/skill.json src/cad_spec_gen/data/commands/en/cad-help.md
git commit -m "feat(photo3d): 增加增强 provider preset 交接"
cd D:\Work\cad-spec-gen
git pull --ff-only origin main
git merge --ff-only codex/photo3d-provider-presets
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
git push origin main
git worktree remove .worktrees\photo3d-provider-presets
git branch -d codex/photo3d-provider-presets
```

Expected: branch merged to `main`, pushed, and used worktree/branch cleaned.

## Self Review

- Spec coverage: The plan covers provider preset declaration, autopilot exposure, handoff execution, CLI help, docs, sync, board update, merge/push/cleanup.
- Placeholder scan: No TBD/TODO placeholders remain.
- Type consistency: The public field name is consistently `provider_preset`; the CLI option is `--provider-preset`; the autopilot list is `provider_presets`; the default id is `default_provider_preset`.
