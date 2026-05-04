# Common Model Library Batch 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the default parts library with a second batch of reusable purchased-part families so new products get recognizable CAD geometry without project-specific rules.

**Architecture:** Keep reusable category and keyword routing in `parts_library.default.yaml`, with project `parts_library.yaml` still allowed to override using real STEP/SolidWorks/Toolbox models. Add only B-grade `JinjaPrimitiveAdapter` templates that can be parameterized from BOM text, default dimensions, or §6.4 part envelopes, and require every generated shape to stay inside reported `real_dims`. Avoid broad fallback boxes for flexible/ambiguous parts; unmatched cable-like or ambiguous rows should still skip or fall through with review requirements rather than pretending to be accurate.

**Tech Stack:** Python 3.10+, pytest, CadQuery, YAML-driven `PartsResolver`, `scripts/dev_sync.py` mirrors.

---

## Scope

Batch 2 covers reusable families that appear across many mechanical products and can be represented safely as bounded B-grade parametric templates:

- Linear guide rail and carriage: `MGN12H`, `MGN15H`, `HGW15`, `HGH15`, `直线导轨`, `滑块`.
- Generic clamping/flexible couplings: names like `L050 联轴器`, `L070 联轴器`, `夹紧联轴器`, `flexible coupling`.
- Generic GT2 timing pulleys and belts: parse tooth count, bore, belt width, and loop length where present.
- Spur gears and sprockets: parse module/tooth count or use bounded fallback dimensions.
- Common terminal blocks and circular connectors: `KF301`, `Phoenix`, `M12 4pin/5pin`, `端子`, `接线端子`.
- Pneumatic accessories: solenoid valve, regulator/filter, one-touch fitting, and generic thin cylinder variants.

Out of scope for this batch:

- Real vendor STEP acquisition, web scraping, or SolidWorks COM exports.
- Project-specific dimensions that only make sense for one subsystem.
- Full standards-compliant tooth profiles for gears/pulleys; visual teeth or bounded simplified profiles are acceptable when metadata marks B-grade parametric template.
- Flexible hose/cable global routing through an assembly; only bounded visual stubs with explicit harness/tube/fitting intent are allowed.

---

## File Structure

- `tests/test_common_model_library_batch_2.py`: new red/green tests for classification, reusable templates, route ordering, and geometry envelope constraints.
- `bom_parser.py`: category keyword updates only where required to classify common rows into existing reusable categories.
- `cad_spec_defaults.py`: default dimensions and model keys for Batch 2 families.
- `adapters/parts/jinja_primitive_adapter.py`: new reusable B-grade template generators and `_specialized_template()` routing.
- `parts_library.default.yaml`: explicit default routing rules before terminal fallback.
- `tests/test_parts_library_standard_categories.py`: rule-presence tests for default route ordering.
- `tests/test_jinja_generators_new.py`: update older project-specific template expectations only when generalized template IDs replace specific names.
- `docs/PROGRESS.md` and `docs/superpowers/README.md`: round-end progress and plan index.

---

### Task 1: Red Tests for Batch 2 Coverage

**Files:**
- Create: `tests/test_common_model_library_batch_2.py`
- Modify: none

- [ ] **Step 1: Write failing coverage tests**

Create `tests/test_common_model_library_batch_2.py` with:

```python
from __future__ import annotations

import pytest

from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from bom_parser import classify_part
from parts_resolver import PartQuery, default_resolver


def _q(category: str, name: str, material: str = "") -> PartQuery:
    return PartQuery(
        part_no="B2-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.mark.parametrize(
    ("name", "material", "expected"),
    [
        ("MGN12H 直线导轨滑块", "", "bearing"),
        ("L050 夹紧联轴器", "Φ6.35×25mm", "transmission"),
        ("GT2 30T 同步带轮", "孔径8mm 6mm带宽", "transmission"),
        ("1模20齿直齿轮", "m=1 z=20 孔径6mm", "transmission"),
        ("KF301 接线端子", "3P 5.08mm", "connector"),
        ("M12 5芯航空插头", "", "connector"),
        ("二位五通电磁阀", "DC24V", "pneumatic"),
        ("快插气管接头", "PC6-01", "pneumatic"),
    ],
)
def test_batch_2_common_names_classify_to_reusable_categories(
    name: str,
    material: str,
    expected: str,
) -> None:
    assert classify_part(name, material) == expected


@pytest.mark.parametrize(
    ("category", "name", "material", "template", "dims"),
    [
        ("bearing", "MGN12H 直线导轨滑块", "", "linear_guide_carriage", (45, 27, 15)),
        ("transmission", "L050 夹紧联轴器", "Φ6.35×25mm", "clamping_coupling_lxx", (20, 20, 25)),
        ("transmission", "GT2 30T 同步带轮", "孔径8mm 6mm带宽", "gt2_timing_pulley", (19.1, 19.1, 10)),
        ("transmission", "1模20齿直齿轮", "m=1 z=20 孔径6mm", "spur_gear", (22, 22, 8)),
        ("connector", "KF301 接线端子", "3P 5.08mm", "terminal_block", (15.24, 8, 10)),
        ("connector", "M12 5芯航空插头", "", "m12_connector", (12, 12, 18)),
        ("pneumatic", "二位五通电磁阀", "DC24V", "pneumatic_solenoid_valve", (45, 22, 28)),
        ("pneumatic", "快插气管接头", "PC6-01", "pneumatic_push_fitting", (12, 12, 22)),
    ],
)
def test_batch_2_jinja_templates_are_b_grade_reusable_families(
    category: str,
    name: str,
    material: str,
    template: str,
    dims: tuple[float, float, float],
) -> None:
    result = JinjaPrimitiveAdapter().resolve(_q(category, name, material), {})

    assert result.status == "hit"
    assert result.geometry_source == "PARAMETRIC_TEMPLATE"
    assert result.geometry_quality == "B"
    assert result.requires_model_review is False
    assert result.metadata["template"] == template
    assert result.metadata["template_scope"] == "reusable_part_family"
    assert result.real_dims == dims


@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("bearing", "MGN12H 直线导轨滑块", ""),
        ("transmission", "L050 夹紧联轴器", "Φ6.35×25mm"),
        ("transmission", "GT2 30T 同步带轮", "孔径8mm 6mm带宽"),
        ("transmission", "1模20齿直齿轮", "m=1 z=20 孔径6mm"),
        ("connector", "KF301 接线端子", "3P 5.08mm"),
        ("connector", "M12 5芯航空插头", ""),
        ("pneumatic", "二位五通电磁阀", "DC24V"),
        ("pneumatic", "快插气管接头", "PC6-01"),
    ],
)
def test_batch_2_template_geometry_stays_within_reported_real_dims(
    category: str,
    name: str,
    material: str,
) -> None:
    import cadquery as cq

    result = JinjaPrimitiveAdapter().resolve(_q(category, name, material), {})
    namespace = {"cq": cq}
    exec(f"def _make():\n{result.body_code}\n", namespace)
    shape = namespace["_make"]()
    bbox = shape.val().BoundingBox()

    assert result.real_dims is not None
    actual = (bbox.xlen, bbox.ylen, bbox.zlen)
    for measured, expected in zip(actual, result.real_dims):
        assert measured <= expected + 1e-6


@pytest.mark.parametrize(
    ("query", "expected_category"),
    [
        (_q("bearing", "MGN12H 直线导轨滑块"), "bearing"),
        (_q("transmission", "GT2 30T 同步带轮", "孔径8mm 6mm带宽"), "transmission"),
        (_q("connector", "KF301 接线端子", "3P 5.08mm"), "connector"),
        (_q("pneumatic", "二位五通电磁阀", "DC24V"), "pneumatic"),
    ],
)
def test_default_library_has_explicit_batch_2_rules_before_terminal_fallback(
    query: PartQuery,
    expected_category: str,
) -> None:
    resolver = default_resolver(project_root="__missing_project__")

    rules = resolver.matching_rules(query, adapter_name="jinja_primitive")

    assert rules
    assert rules[0]["match"].get("category") == expected_category
```

- [ ] **Step 2: Verify tests are red**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_2.py -q
```

Expected: FAIL because Batch 2 templates and default routes do not exist yet.

---

### Task 2: Classifier and Dimension Defaults

**Files:**
- Modify: `bom_parser.py`
- Modify: `cad_spec_defaults.py`

- [ ] **Step 1: Add only reusable classifier keywords**

Update `bom_parser.py`:

```python
("bearing",   ["轴承", "bearing", "MR1", "ZZ", "688", "608", "滚珠", "LM10", "LM12",
               "LM16", "LM20", "LMU", "KFL", "KP0", "KP1", "UCP", "UCF", "法兰座",
               "直线导轨", "滑块", "linear guide", "MGN", "HGW", "HGH"]),
...
("pneumatic", ["气缸", "pneumatic", "cylinder actuator", "air cylinder",
               "MGPM", "MGPL", "SDA", "CQ2", "SCJ", "电磁阀", "solenoid valve",
               "气管接头", "快插", "push fitting", "PC6", "PC8", "调压阀", "过滤减压阀"]),
...
("connector", ["连接器", "connector", "LEMO", "SMA", "Molex", "ZIF", "插座", "插头",
               "端子", "接线端子", "terminal block", "KF301", "Phoenix", "航空插头"]),
```

Do not add broad keywords like `阀` alone because they can misclassify fluid pumps or process valves.

- [ ] **Step 2: Add default dimensions**

Add to `STD_PART_DIMENSIONS`:

```python
    # --- Linear guide families ---
    "MGN12H": {"w": 45, "d": 27, "h": 15, "rail_w": 12, "rail_h": 8, "rail_l": 80},
    "MGN15H": {"w": 55, "d": 32, "h": 20, "rail_w": 15, "rail_h": 10, "rail_l": 100},
    "HGW15": {"w": 47, "d": 34, "h": 24, "rail_w": 15, "rail_h": 12, "rail_l": 110},
    "HGH15": {"w": 34, "d": 39, "h": 28, "rail_w": 15, "rail_h": 12, "rail_l": 110},
    # --- Transmission visual families ---
    "L050": {"d": 20, "l": 25, "bore_d": 6.35},
    "L070": {"d": 25, "l": 30, "bore_d": 6.35},
    "GT2 30T": {"od": 19.1, "w": 10, "id": 8, "teeth": 30, "belt_w": 6},
    # --- Connectors / terminals ---
    "KF301": {"w": 15.24, "d": 8, "h": 10, "pins": 3, "pitch": 5.08},
    "M12 5芯": {"d": 12, "l": 18, "pins": 5},
    "M12 4芯": {"d": 12, "l": 18, "pins": 4},
    # --- Pneumatic accessories ---
    "二位五通": {"w": 45, "d": 22, "h": 28},
    "电磁阀": {"w": 45, "d": 22, "h": 28},
    "PC6": {"d": 12, "l": 22, "tube_d": 6},
    "PC8": {"d": 14, "l": 25, "tube_d": 8},
```

If an existing key overlaps, keep the more specific key first in dict order so Pass 1 matching remains deterministic.

- [ ] **Step 3: Run red tests again**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_2.py::test_batch_2_common_names_classify_to_reusable_categories -q
```

Expected: PASS for classification, while template tests still fail.

---

### Task 3: Reusable B-Grade Templates

**Files:**
- Modify: `adapters/parts/jinja_primitive_adapter.py`
- Modify: `tests/test_jinja_generators_new.py` only if old project-specific IDs need to become generic IDs.

- [ ] **Step 1: Add helper parsers**

Near the existing parser helpers, add bounded parsing helpers:

```python
def _parse_first_int_after(pattern: str, text: str, default: int) -> int:
    m = re.search(pattern, text, re.IGNORECASE)
    return int(m.group(1)) if m else default


def _parse_first_float_after(pattern: str, text: str, default: float) -> float:
    m = re.search(pattern, text, re.IGNORECASE)
    return float(m.group(1)) if m else default
```

Use exact patterns at call sites; do not infer from unrelated numbers such as part numbers unless the pattern is explicit.

- [ ] **Step 2: Add bounded generator functions**

Add reusable generator functions:

```python
def _gen_linear_guide_carriage(dims: dict) -> str:
    ...


def _gen_clamping_coupling_lxx(dims: dict) -> str:
    ...


def _gen_gt2_timing_pulley(dims: dict) -> str:
    ...


def _gen_spur_gear(dims: dict) -> str:
    ...


def _gen_terminal_block(dims: dict, pins: int) -> str:
    ...


def _gen_pneumatic_solenoid_valve(dims: dict) -> str:
    ...


def _gen_pneumatic_push_fitting(dims: dict) -> str:
    ...
```

Rules for each generator:

- The final bounding box must be within the `dims` returned by `_specialized_template()`.
- Use visual teeth/grooves only as bounded cuts/unions; never grow past `od`, `w`, `d`, or `h`.
- For couplings, support `d`, `l`, `bore_d`; default `bore_d` must be clamped below `d * 0.72`.
- For terminal blocks, use `w = pins * pitch`, with pin pockets and screw heads bounded inside `h`.
- For valves and fittings, render ports/coils as bounded details inside the reported rectangular or cylindrical envelope.

- [ ] **Step 3: Wire `_specialized_template()`**

Add cases before old specific cases:

```python
    if category == "bearing" and _contains_any(
        text, ["直线导轨", "linear guide", "MGN", "HGW", "HGH", "滑块"]
    ):
        ...
        return {
            "template": "linear_guide_carriage",
            "body_code": _gen_linear_guide_carriage(tpl_dims),
            "dims": tpl_dims,
            "metadata": dict(reusable_parametric_template),
        }
```

Then generic cases for:

- `clamping_coupling_lxx`: match `联轴器`, `coupling`, `L050`, `L070`.
- `gt2_timing_pulley`: match `GT2` and `带轮/pulley`, parse `(\d+)T`, `孔径`, `带宽`.
- `spur_gear`: match `齿轮/spur gear`, parse `m` and `z` from `m=1 z=20`, `1模20齿`.
- `terminal_block`: match `端子`, `terminal block`, `KF301`, `Phoenix`.
- `m12_connector`: extend existing M12 logic to category `connector` as well as `other`.
- `pneumatic_solenoid_valve`: match `电磁阀`, `solenoid valve`.
- `pneumatic_push_fitting`: match `快插`, `PC6`, `PC8`, `push fitting`.

Keep old wrappers such as `clamping_coupling_l070` if tests or downstream generated files expect them, but make new generic template names the preferred return value when a family pattern matches.

- [ ] **Step 4: Run focused template tests**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_2.py tests\test_jinja_generators_new.py -q
```

Expected: Batch 2 template tests pass; if old jinja tests fail only because a specific template ID became a generic family ID, update the test expectation to the generic ID and keep negative tests that prove unrelated parts do not hit the family template.

---

### Task 4: Default Registry Routes and Rule Tests

**Files:**
- Modify: `parts_library.default.yaml`
- Modify: `tests/test_parts_library_standard_categories.py`

- [ ] **Step 1: Add explicit default rules before terminal fallback**

Insert after the first-batch common electromechanical block or fold into that block:

```yaml
  - match:
      category: bearing
      keyword_contains: ["直线导轨", "linear guide", "MGN", "HGW", "HGH", "滑块"]
    adapter: jinja_primitive

  - match:
      category: transmission
      keyword_contains: ["联轴器", "coupling", "GT2", "带轮", "pulley", "齿轮", "spur gear"]
    adapter: jinja_primitive

  - match:
      category: connector
      keyword_contains: ["端子", "接线端子", "terminal block", "KF301", "Phoenix", "M12"]
    adapter: jinja_primitive

  - match:
      category: pneumatic
      keyword_contains: ["电磁阀", "solenoid valve", "快插", "push fitting", "气管接头", "PC6", "PC8"]
    adapter: jinja_primitive
```

Important ordering:

- Keep vendor STEP and SolidWorks/Toolbox rules above default B-grade templates.
- For `bearing`, do not steal normal ball bearing rows from `bd_warehouse`/Toolbox; require linear guide keywords.
- For `transmission`, leave lead screw rules above generic transmission jinja route.

- [ ] **Step 2: Add route-presence tests**

Extend `tests/test_parts_library_standard_categories.py`:

```python
@pytest.mark.parametrize(
    ("category", "name", "material"),
    [
        ("bearing", "MGN12H 直线导轨滑块", ""),
        ("transmission", "GT2 30T 同步带轮", "孔径8mm 6mm带宽"),
        ("connector", "KF301 接线端子", "3P 5.08mm"),
        ("pneumatic", "二位五通电磁阀", "DC24V"),
    ],
)
def test_common_model_batch_2_rule_exists_before_terminal_fallback(
    category: str,
    name: str,
    material: str,
) -> None:
    query = PartQuery(
        part_no="B2-DEFAULT-RULE",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )
    rules = default_resolver(project_root="__missing_project__").matching_rules(
        query,
        adapter_name="jinja_primitive",
    )

    assert rules
    assert rules[0]["match"].get("category") == category
```

- [ ] **Step 3: Run route tests**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_2.py tests\test_parts_library_standard_categories.py -q
```

Expected: PASS.

---

### Task 5: Reports, Mirrors, and Final Verification

**Files:**
- Modify: `docs/PROGRESS.md`
- Modify: `docs/superpowers/README.md`
- Mirror updates via `scripts/dev_sync.py`

- [ ] **Step 1: Update progress docs**

Update `docs/PROGRESS.md`:

- Current branch: `codex/common-model-library-batch-2`.
- Board row: `常用模型库扩展第二批`.
- Verification rows for Batch 2 tests and sync checks.
- Current risks: B-grade templates are visual stand-ins; real vendor STEP still overrides via project library.

Update `docs/superpowers/README.md`:

- Add this plan to the current documents table.
- Mark Batch 2 as current branch work.

- [ ] **Step 2: Sync mirrors**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
```

`dev_sync.py` may return non-zero when it updates ignored mirrors; re-run `--check` must pass.

- [ ] **Step 3: Final verification**

Run:

```powershell
D:\Work\cad-spec-gen\.venv\Scripts\python.exe -m pytest tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q
D:\Work\cad-spec-gen\.venv\Scripts\python.exe scripts\dev_sync.py --check
git diff --check
```

Expected: all pass, no mirror drift, no whitespace errors.

- [ ] **Step 4: Commit**

Run:

```powershell
git add bom_parser.py cad_spec_defaults.py adapters/parts/jinja_primitive_adapter.py parts_library.default.yaml tests/test_common_model_library_batch_2.py tests/test_parts_library_standard_categories.py tests/test_jinja_generators_new.py docs/PROGRESS.md docs/superpowers/README.md docs/superpowers/plans/2026-05-04-common-model-library-batch-2.md
git add -f src/cad_spec_gen/data/codegen/gen_std_parts.py
git commit -m "feat(parts-library): 扩展常用模型库第二批"
```

Only add tracked mirror files if `git status --short` shows them. Do not force-add ignored generated data directories wholesale.

---

## Self-Review Notes

- Spec coverage: plan covers classification, dimensions, templates, default routes, geometry envelope constraints, docs, mirrors, and final tests.
- Placeholder scan: no `TBD`, `TODO`, or open-ended "write tests" steps remain.
- Type consistency: template IDs in tests match planned `_specialized_template()` return values: `linear_guide_carriage`, `clamping_coupling_lxx`, `gt2_timing_pulley`, `spur_gear`, `terminal_block`, `m12_connector`, `pneumatic_solenoid_valve`, `pneumatic_push_fitting`.
- Boundary guard: plan requires explicit keywords for linear guides, connectors, transmission families, and pneumatic accessories; it avoids broad `bearing`, `connector`, or `pneumatic` catch-alls that would steal real-model routes.
