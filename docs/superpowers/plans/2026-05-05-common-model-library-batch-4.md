# Common Model Library Batch 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth batch of reusable purchased-part model families so small electrical, sensor accessory, vacuum, and aluminum profile parts get recognizable B-grade CAD geometry without project-specific tuning.

**Architecture:** Default routing remains explicit, ordered, and category-scoped. Project STEP/SolidWorks/Toolbox routes stay ahead of B-grade Jinja templates; exact mature templates outrank broader reusable families. New routes require a clear reusable family phrase such as `IP65 控制箱`, `sensor mounting bracket`, `vacuum ejector`, or `2020铝型材`; broad words such as `柜`, `板`, `支架`, `接头`, `型材`, `真空`, or `按钮` alone are not sufficient.

**Tech Stack:** Python 3.10+, pytest, CadQuery, YAML-driven `PartsResolver`, `JinjaPrimitiveAdapter`, `scripts/dev_sync.py` mirrors.

---

## Scope

Batch 4 covers four cross-product families:

- Small electrical enclosures and panel controls: `IP65 控制箱`, `电气控制箱`, `control enclosure`, `junction box`, `22mm 急停按钮`, `panel pushbutton`, `indicator light`.
- Sensor mounting accessories: `传感器安装支架`, `传感器固定支架`, `sensor mounting bracket`, `sensor bracket`, `E3Z bracket`.
- Vacuum pneumatic parts: `真空发生器`, `vacuum ejector`, `真空吸盘`, `vacuum cup`, `suction cup`.
- Aluminum profile and brackets: `2020铝型材`, `2040铝型材`, `T-slot extrusion`, `V-slot 2020`, `2020角码`, `L型角码`, `aluminum corner bracket`.

Out of scope:

- Real vendor STEP acquisition or web scraping.
- Cabinet-scale sheet-metal assemblies, wiring, door hinges, locks, full DIN rail layouts, or detailed vacuum generator internals.
- Broad category capture from `柜`, `板`, `支架`, `接头`, `型材`, `真空`, `按钮`, `M12`, `2020`, or `IP65` alone.
- Replacing existing A/B routes for sensors, connectors, fasteners, generic pneumatic cylinders, or project STEP rules.

---

## File Structure

- Create `tests/test_common_model_library_batch_4.py`: red/green coverage for classification, B-grade templates, negative cases, route ordering, dimension scope, and geometry envelope constraints.
- Modify `bom_parser.py`: add only context-bearing keywords and one specific sensor-accessory override so sensor brackets do not become sensors.
- Modify `cad_spec_defaults.py`: add default dimensions and category scopes for Batch 4 model keys.
- Modify `adapters/parts/jinja_primitive_adapter.py`: add reusable B-grade template generators and `_specialized_template()` routing.
- Modify `parts_library.default.yaml`: insert explicit routes before generic fallbacks in first-hit-wins order.
- Modify `tests/test_parts_library_standard_categories.py`: add registry ordering and broad-token negative tests for Batch 4.
- Modify `docs/PROGRESS.md` and `docs/superpowers/README.md`: record this round and the next step.

---

### Task 1: Red Tests for Batch 4

**Files:**
- Create: `tests/test_common_model_library_batch_4.py`
- Modify: `tests/test_parts_library_standard_categories.py`

- [x] **Step 1: Add failing tests**

Add tests that assert expected reusable templates:

- `IP65 控制箱` -> `other` -> `electrical_enclosure_box` -> `(160, 120, 80)`.
- `22mm 急停按钮` -> `other` -> `panel_pushbutton_22mm` -> `(30, 30, 45)`.
- `M12 传感器安装支架` -> `other` -> `sensor_mounting_bracket` -> `(50, 32, 28)`.
- `真空发生器` -> `pneumatic` -> `vacuum_ejector` -> `(60, 18, 28)`.
- `真空吸盘` -> `pneumatic` -> `vacuum_suction_cup` -> `(30, 30, 25)`.
- `2020铝型材` -> `other` -> `aluminum_tslot_extrusion` -> `(200, 20, 20)`.
- `2020角码` -> `other` -> `aluminum_corner_bracket` -> `(40, 40, 20)`.

Add negative tests for:

- `普通支架` stays `other` and does not hit sensor bracket templates.
- `按钮标签` stays `other` and does not hit panel pushbutton.
- `真空包装袋` stays `other` and does not hit pneumatic vacuum templates.
- `铝型材手册` stays `other` and does not hit aluminum profile templates.
- `M12 电感接近开关` still prefers the existing cylindrical proximity sensor template.
- `KF301 接线端子` still prefers the existing terminal block template.

- [x] **Step 2: Verify red**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_4.py -q
```

Expected: FAIL because the new templates and routes do not exist yet.

---

### Task 2: Classifier and Dimensions

**Files:**
- Modify: `bom_parser.py`
- Modify: `cad_spec_defaults.py`

- [x] **Step 1: Add classifier keywords**

Use only explicit context:

- Specific pre-rule: if text contains `传感器安装支架`, `传感器固定支架`, `sensor mounting bracket`, `sensor bracket`, or `E3Z bracket`, classify as `other` before the general `sensor` rule.
- `pneumatic`: add `真空发生器`, `vacuum ejector`, `真空吸盘`, `vacuum cup`, `suction cup`.
- `other`: add `IP65 控制箱`, `电气控制箱`, `control enclosure`, `electrical enclosure`, `junction box`, `接线盒`, `22mm 急停按钮`, `急停按钮`, `22mm push button`, `panel pushbutton`, `indicator light`, `指示灯`, `2020铝型材`, `2040铝型材`, `T-slot extrusion`, `V-slot 2020`, `2020角码`, `L型角码`, `aluminum corner bracket`.

Do not add bare `柜`, `板`, `支架`, `接头`, `型材`, `真空`, `按钮`, `M12`, `2020`, or `IP65`.

- [x] **Step 2: Add category-scoped defaults**

Add `STD_PART_DIMENSIONS` keys:

- `IP65 控制箱`: `{"w": 160, "d": 120, "h": 80}`
- `22mm 急停按钮`: `{"w": 30, "d": 30, "h": 45, "hole_d": 22}`
- `M12 传感器安装支架`: `{"w": 50, "d": 32, "h": 28, "hole_d": 12}`
- `真空发生器`: `{"w": 60, "d": 18, "h": 28}`
- `真空吸盘`: `{"w": 30, "d": 30, "h": 25}`
- `2020铝型材`: `{"w": 200, "d": 20, "h": 20, "slot_w": 6}`
- `2040铝型材`: `{"w": 200, "d": 20, "h": 40, "slot_w": 6}`
- `2020角码`: `{"w": 40, "d": 40, "h": 20}`

Add matching `STD_PART_DIMENSION_CATEGORIES` entries so material text from another family cannot steal dimensions.

---

### Task 3: B-Grade Template Generators

**Files:**
- Modify: `adapters/parts/jinja_primitive_adapter.py`

- [x] **Step 1: Add bounded generator functions**

Add reusable generators:

- `_gen_electrical_enclosure_box()`
- `_gen_panel_pushbutton_22mm()`
- `_gen_sensor_mounting_bracket()`
- `_gen_vacuum_ejector()`
- `_gen_vacuum_suction_cup()`
- `_gen_aluminum_tslot_extrusion()`
- `_gen_aluminum_corner_bracket()`

Each generator must use only cuts/unions bounded by its `dims`.

- [x] **Step 2: Wire `_specialized_template()`**

Insert cases before broader existing cases:

- Panel/control enclosure and sensor mounting accessories before generic `other` fallback and before the `other` M12 connector helper.
- Vacuum ejector/cup before generic pneumatic accessory/cylinder routes.
- Aluminum profile/corner bracket before generic `other` fallback.
- Existing exact templates such as `CL57T`, existing sensor templates, `DIN导轨电源`, `DIN导轨端子`, `KF301`, and `M12 接近开关` must remain unbroken.

---

### Task 4: Default Registry Ordering

**Files:**
- Modify: `parts_library.default.yaml`
- Modify: `tests/test_parts_library_standard_categories.py`

- [x] **Step 1: Insert routes**

Insert explicit `jinja_primitive` routes:

- `category: other` + `keyword_contains: ["IP65 控制箱", "电气控制箱", "control enclosure", "electrical enclosure", "junction box", "接线盒"]`.
- `category: other` + `keyword_contains: ["22mm 急停按钮", "急停按钮", "22mm push button", "panel pushbutton", "indicator light", "指示灯"]`.
- `category: other` + `keyword_contains: ["传感器安装支架", "传感器固定支架", "sensor mounting bracket", "sensor bracket", "E3Z bracket"]`.
- `category: pneumatic` + `keyword_contains: ["真空发生器", "vacuum ejector", "真空吸盘", "vacuum cup", "suction cup"]` before generic pneumatic cylinder route.
- `category: other` + `keyword_contains: ["2020铝型材", "2040铝型材", "T-slot extrusion", "V-slot 2020", "2020角码", "L型角码", "aluminum corner bracket"]`.

Never route by bare `柜`, `板`, `支架`, `接头`, `型材`, `真空`, `按钮`, `M12`, `2020`, or `IP65` alone.

---

### Task 5: Verification, Docs, and Commit

**Files:**
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`
- Mirror updates via `scripts/dev_sync.py`

- [x] **Step 1: Run focused and range tests**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py -q
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
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
```

- [x] **Step 4: Commit**

Commit with:

```powershell
git commit -m "feat(parts-library): 扩展常用模型库第四批"
```

Result: committed as `c4226a3 feat(parts-library): 扩展常用模型库第四批`, fast-forward merged to `main`, and verified on `main` with `454 passed, 2 skipped`.

---

## Self-Review Notes

- Spec coverage: classification, default dimensions, template implementation, default route ordering, negative cases, geometry envelope, docs, and sync checks are covered.
- Placeholder scan: no broad open-ended implementation step is left without concrete files and checks.
- Type consistency: template IDs are `electrical_enclosure_box`, `panel_pushbutton_22mm`, `sensor_mounting_bracket`, `vacuum_ejector`, `vacuum_suction_cup`, `aluminum_tslot_extrusion`, and `aluminum_corner_bracket`.
- Boundary guard: all new routes require category plus explicit family context; broad tokens are intentionally excluded.
