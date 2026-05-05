# Common Model Library Batch 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Phase 2 with a fifth batch of explicit, reusable purchased-part model families for automation equipment without adding project-specific or broad-token routing.

**Architecture:** Batch 5 continues the YAML-first resolver pattern: real STEP, vendor cache, SolidWorks/Toolbox, bd_warehouse, and project rules remain ahead of B-grade templates. New B-grade Jinja templates require both category and explicit family intent, and each family adds positive, negative, route, dimension, geometry, and admission-manifest coverage.

**Tech Stack:** Python 3.10+, pytest, CadQuery, `PartsResolver`, `JinjaPrimitiveAdapter`, `parts_library.default.yaml`, `scripts/dev_sync.py`.

---

## Scope

Batch 5 covers five cross-product families:

- Servo motor with square flange: `60法兰伺服电机`, `AC servo motor`, `servo motor 60mm`.
- Planetary gearbox / reducer: `PLE60 行星减速机`, `planetary gearbox`, `planetary reducer`.
- Drag chain segment: `Igus 拖链段`, `塑料拖链段`, `drag chain segment`, `cable carrier`.
- Slim DIN relay module: `DIN导轨继电器模块`, `DIN rail relay module`, `interface relay`.
- Operator control box: `按钮盒`, `操作盒`, `control station`, `operator box`.

Out of scope:

- Vendor-specific STEP acquisition.
- Full cable routing, flexible drag-chain kinematics, or detailed relay internals.
- Capturing broad tokens such as `伺服`, `行星`, `拖链`, `继电器`, `按钮`, `box`, `module`, or `DIN` without explicit family context.

---

## File Structure

- Create: `tests/test_common_model_library_batch_5.py`
- Modify: `bom_parser.py`
- Modify: `cad_spec_defaults.py`
- Modify: `adapters/parts/jinja_primitive_adapter.py`
- Modify: `parts_library.default.yaml`
- Modify: `tests/test_parts_library_standard_categories.py`
- Modify: `docs/superpowers/specs/common_model_family_admission.json`
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`

---

### Task 1: Red Tests

- [x] Add `tests/test_common_model_library_batch_5.py` covering classification, B-grade template metadata, negative cases, geometry bounds, default route ordering, and category-scoped dimensions.
- [x] Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_5.py -q
```

Expected: fail before implementation.

Observed: failed before implementation with 16 missing-route/template/classification failures, then passed after implementation.

### Task 2: Classifier and Dimensions

- [x] Add only explicit classifier keywords for the five families.
- [x] Add category-scoped dimensions:
  - `60法兰伺服电机`: `{w: 60, d: 60, h: 115, body_h: 85, shaft_d: 14}`
  - `PLE60`: `{w: 60, d: 60, h: 70, shaft_d: 14}`
  - `Igus 拖链段`: `{w: 120, d: 30, h: 18, link_count: 8}`
  - `DIN导轨继电器模块`: `{w: 6.2, d: 78, h: 90}`
  - `按钮盒`: `{w: 80, d: 70, h: 65, button_count: 2}`

### Task 3: Template Generators

- [x] Add bounded B-grade generators:
  - `_gen_square_flange_servo_motor`
  - `_gen_planetary_gearbox`
  - `_gen_drag_chain_segment`
  - `_gen_din_rail_relay_module`
  - `_gen_operator_control_box`
- [x] Wire `_specialized_template()` so exact mature routes stay ahead of broader families.

### Task 4: Registry and Admission Manifest

- [x] Add explicit default registry routes before terminal fallback and before broader DIN/cable/reducer routes when needed.
- [x] Add representative Batch 5 positive, negative, route, dimension, and geometry cases to `common_model_family_admission.json`.

### Task 5: Verification and Commit

- [x] Run focused range tests:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_5.py tests\test_common_model_family_admission.py tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_jinja_generators_new.py -q
```

- [x] Run sync and whitespace checks:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
```

- [x] Final focused suite with mirror tests:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_5.py tests\test_common_model_family_admission.py tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
```

Observed:

- Focused range: `330 passed, 7 warnings`.
- `scripts/dev_sync.py` synced three local install mirrors, then `scripts/dev_sync.py --check` passed.
- Final focused suite: `514 passed, 2 skipped, 11 warnings`.
- `git diff --check` passed with Windows line-ending warnings only.

---

## Self-Review

- Scope uses explicit category plus family intent only.
- No project `part_no`, device-specific placement, render-fix, or one-off asset path enters the default library.
- New families update both dedicated batch tests and the admission manifest.
- Code review found and fixed route-alias drift: every public `keyword_contains` alias for Batch 5 now resolves to the same template, `real_dims`, and `lookup_std_part_dims()` defaults as its canonical family name.
- `interface relay` now participates in the same DIN relay-module adapter gate that the default registry exposes.
