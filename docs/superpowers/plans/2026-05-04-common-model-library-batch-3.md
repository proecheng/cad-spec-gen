# Common Model Library Batch 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third batch of reusable purchased-part model families so more new products get recognizable B-grade CAD geometry without project-specific tuning.

**Architecture:** Keep default routing explicit, ordered, and category-scoped. Real project STEP/SolidWorks/Toolbox routes stay ahead of B-grade Jinja templates; new templates are only for clear reusable families and must keep generated geometry inside reported `real_dims`. Broad words such as `支撑座`, `模块`, `阀`, `DIN`, or `导轨` are not enough by themselves.

**Tech Stack:** Python 3.10+, pytest, CadQuery, YAML-driven `PartsResolver`, `JinjaPrimitiveAdapter`, `scripts/dev_sync.py` mirrors.

**Execution status (2026-05-04):** Implemented and verified on branch `codex/common-model-library-batch-3`. Focused Batch 3 tests, default-route ordering tests, range regression, `dev_sync --check`, and `git diff --check` passed. During regression, the existing `KFL001` dedicated template was restored ahead of the new mounted-bearing family, codifying the general rule that exact mature templates outrank broader reusable families.

---

## Scope

Batch 3 covers four cross-product families:

- Bearing/support units: `UCP204`, `KP08`, `KFL001`, `轴承座`, `pillow block`, plus motion support blocks such as `BK12` / `BF12` when paired with `支撑座` / `support block`.
- Standard linear modules: `KK60`, `KK86`, `直线模组`, `线性模组`, `滑台模组`, `linear module`, `linear actuator module`.
- Pneumatic distribution and conditioning: `阀岛`, `valve manifold`, `过滤减压阀`, `调压过滤器`, `FRL`, `filter regulator`, `air regulator`.
- DIN rail electrical parts: `DIN导轨端子`, `DIN rail terminal`, `DIN导轨电源`, `DIN rail power supply`, `DIN导轨继电器`, `DIN rail relay`.

Out of scope:

- Real vendor STEP acquisition or web scraping.
- Full vendor-accurate rail/module internals.
- Broad category capture from `阀`, `模块`, `支撑座`, `DIN`, `导轨`, `BK`, `BF`, or `35mm` alone.
- Replacing existing A/B library routes for ordinary bearings, fasteners, or project STEP rules.

---

## File Structure

- Create `tests/test_common_model_library_batch_3.py`: red/green coverage for classification, B-grade templates, negative cases, route ordering, and geometry envelope constraints.
- Modify `bom_parser.py`: add only context-bearing keywords needed for Batch 3.
- Modify `cad_spec_defaults.py`: add default dimensions and category scopes for Batch 3 model keys.
- Modify `adapters/parts/jinja_primitive_adapter.py`: add reusable B-grade template generators and `_specialized_template()` routing.
- Modify `parts_library.default.yaml`: insert explicit routes before generic fallbacks in first-hit-wins order.
- Modify `tests/test_parts_library_standard_categories.py`: add registry ordering tests for Batch 3.
- Modify `docs/PROGRESS.md` and `docs/superpowers/README.md`: record this round and the next step.

---

### Task 1: Red Tests for Batch 3

**Files:**
- Create: `tests/test_common_model_library_batch_3.py`
- Modify: `tests/test_parts_library_standard_categories.py`

- [x] **Step 1: Add failing tests**

Add tests that assert the expected reusable templates:

- `UCP204 轴承座` -> `bearing` -> `mounted_bearing_support` -> `(127, 38, 65)`.
- `BK12 丝杠支撑座` -> `transmission` -> `lead_screw_support_block` -> `(60, 25, 43)`.
- `KK60 直线模组` -> `transmission` -> `linear_motion_module` -> `(300, 60, 45)`.
- `4联阀岛` -> `pneumatic` -> `pneumatic_valve_manifold` -> `(90, 32, 36)`.
- `过滤减压阀` -> `pneumatic` -> `pneumatic_filter_regulator` -> `(42, 42, 90)`.
- `DIN导轨端子` -> `connector` -> `din_rail_terminal_block` -> `(5.2, 45, 35)`.
- `DIN导轨电源` -> `other` -> `din_rail_device` -> `(90, 60, 55)`.

Add negative tests for:

- `普通支撑座` stays `other` and does not hit support templates.
- `DIN912 内六角螺钉` stays `fastener`.
- `阀体安装板` stays `other`.
- `608ZZ 深沟球轴承` still prefers standard bearing routes.
- `BK12 丝杠支撑座` must not be stolen by the generic lead-screw route.
- `DIN导轨端子` must not fall into the generic PCB terminal-block template.

- [x] **Step 2: Verify red**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_3.py -q
```

Expected: FAIL because the new templates and routes do not exist yet.

---

### Task 2: Classifier and Dimensions

**Files:**
- Modify: `bom_parser.py`
- Modify: `cad_spec_defaults.py`

- [x] **Step 1: Add classifier keywords**

Use only explicit context:

- `bearing`: add `轴承座`, `pillow block`, `flange bearing`.
- `transmission`: add `直线模组`, `线性模组`, `滑台模组`, `linear module`, `linear actuator module`.
- `pneumatic`: add `阀岛`, `valve manifold`, `FRL`, `filter regulator`, `air regulator`, `调压过滤器`.
- `connector`: add `DIN导轨端子`, `DIN rail terminal`.
- `other`: add `DIN导轨`, `DIN rail`, `35mm导轨`, `导轨电源`, `导轨继电器`.

Do not add bare `支撑座`, `模块`, `阀`, `DIN`, `导轨`, `BK`, `BF`, or `35mm`.

- [x] **Step 2: Add category-scoped defaults**

Add `STD_PART_DIMENSIONS` keys:

- `UCP204`: `{"w": 127, "d": 38, "h": 65, "bore_d": 20, "mount_d": 12}`
- `KP08`: `{"w": 55, "d": 13, "h": 27, "bore_d": 8, "mount_d": 5}`
- `BK12`: `{"w": 60, "d": 25, "h": 43, "bore_d": 12, "mount_d": 5}`
- `BF12`: `{"w": 60, "d": 20, "h": 35, "bore_d": 12, "mount_d": 5}`
- `KK60`: `{"w": 300, "d": 60, "h": 45, "carriage_w": 80}`
- `KK86`: `{"w": 400, "d": 86, "h": 65, "carriage_w": 110}`
- `阀岛`: `{"w": 90, "d": 32, "h": 36, "stations": 4}`
- `过滤减压阀`: `{"w": 42, "d": 42, "h": 90}`
- `DIN导轨端子`: `{"w": 5.2, "d": 45, "h": 35}`
- `DIN导轨电源`: `{"w": 90, "d": 60, "h": 55}`

Add matching `STD_PART_DIMENSION_CATEGORIES` entries so material text from another family cannot steal dimensions.

---

### Task 3: B-Grade Template Generators

**Files:**
- Modify: `adapters/parts/jinja_primitive_adapter.py`

- [x] **Step 1: Add bounded generator functions**

Add reusable generators:

- `_gen_mounted_bearing_support()`
- `_gen_lead_screw_support_block()`
- `_gen_linear_motion_module()`
- `_gen_pneumatic_valve_manifold()`
- `_gen_pneumatic_filter_regulator()`
- `_gen_din_rail_terminal_block()`
- `_gen_din_rail_device()`

Each generator must use only cuts/unions bounded by its `dims`.

- [x] **Step 2: Wire `_specialized_template()`**

Insert cases before broader existing cases:

- Bearing support before generic bearing catalog routes; exact mature templates such as `KFL001` stay ahead of the broader mounted-bearing family.
- Transmission support block before lead-screw nut and before generic transmission B-grade routes.
- Linear motion module before generic transmission gear/pulley routes.
- Valve manifold / filter regulator before solenoid/fitting/cylinder pneumatic routes.
- DIN rail terminal before generic terminal block.
- DIN rail device under `other` before generic `other` block.

---

### Task 4: Default Registry Ordering

**Files:**
- Modify: `parts_library.default.yaml`
- Modify: `tests/test_parts_library_standard_categories.py`

- [x] **Step 1: Insert routes**

Insert:

- `category: bearing` + `name_contains: ["轴承座", "pillow block", "flange bearing", "UCP", "UCF", "KP08", "KFL"]` after vendor STEP and before generic bearing catalog routes.
- `category: transmission` + `keyword_contains: ["BK12", "BF12", "支撑座", "support block"]` before the lead-screw route, because support blocks can include `丝杠` in their name but are not screws.
- `category: transmission` + `keyword_contains: ["直线模组", "线性模组", "滑台模组", "linear module", "linear actuator module", "KK60", "KK86"]` before generic transmission fallbacks.
- Extend pneumatic accessory route with `阀岛`, `valve manifold`, `FRL`, `filter regulator`, `air regulator`, `调压过滤器`.
- Add `category: connector` + `name_contains: ["DIN导轨端子", "DIN rail terminal"]` before generic terminal-block route if needed.
- Add `category: other` + `keyword_contains: ["DIN导轨", "DIN rail", "35mm导轨", "导轨电源", "导轨继电器"]` before terminal fallback.

Never route by bare `DIN`, `阀`, `模块`, `支撑座`, `BK`, or `BF` alone.

---

### Task 5: Verification, Docs, and Commit

**Files:**
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`
- Mirror updates via `scripts/dev_sync.py`

- [x] **Step 1: Run focused and range tests**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py -q
```

- [x] **Step 2: Sync mirrors**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
```

- [x] **Step 3: Final checks**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
```

- [x] **Step 4: Commit**

Commit with:

```powershell
git commit -m "feat(parts-library): 扩展常用模型库第三批"
```

---

## Self-Review Notes

- Spec coverage: classification, default dimensions, template implementation, default route ordering, negative cases, geometry envelope, docs, and sync checks are covered.
- Placeholder scan: no broad open-ended implementation step is left without concrete files and checks.
- Type consistency: template IDs are `mounted_bearing_support`, `lead_screw_support_block`, `linear_motion_module`, `pneumatic_valve_manifold`, `pneumatic_filter_regulator`, `din_rail_terminal_block`, and `din_rail_device`.
- Boundary guard: all new routes require category plus explicit family context; broad tokens are intentionally excluded.
