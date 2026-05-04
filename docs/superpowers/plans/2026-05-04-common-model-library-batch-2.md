# Common Model Library Batch 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the default parts library with a second batch of reusable purchased-part families so new products get recognizable CAD geometry without project-specific rules.

**Architecture:** Keep reusable category and keyword routing in `parts_library.default.yaml`, with project `parts_library.yaml` still allowed to override using real STEP/SolidWorks/Toolbox models. Add only B-grade `JinjaPrimitiveAdapter` templates that can be parameterized from BOM text, default dimensions, or §6.4 part envelopes, and require every generated shape to stay inside reported `real_dims`. Avoid broad fallback boxes for flexible/ambiguous parts; unmatched cable-like or ambiguous rows should still skip or fall through with review requirements rather than pretending to be accurate.

**Tech Stack:** Python 3.10+, pytest, CadQuery, YAML-driven `PartsResolver`, `scripts/dev_sync.py` mirrors.

---

## Scope

Batch 2 covers reusable families that appear across many mechanical products and can be represented safely as bounded B-grade parametric templates:

- Linear guide rail and carriage: `MGN12H`, `MGN15H`, `HGW15`, `HGH15`, `直线导轨`, `导轨滑块`. Do not treat a bare `滑块` token as a linear-guide proof; drawer slides, sliders, and generic moving blocks need more context.
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
- Bare ambiguous tokens such as `滑块`, `PC6`, `PC8`, `M12`, or `connector` alone. They may participate in parsing after an explicit category/context match, but must not create a reusable high-confidence template on their own.

---

## File Structure

- `tests/test_common_model_library_batch_2.py`: new red/green tests for classification, reusable templates, route ordering, route non-stealing, and geometry envelope constraints.
- `bom_parser.py`: category keyword updates only where required to classify common rows into existing reusable categories.
- `cad_spec_defaults.py`: default dimensions and model keys for Batch 2 families.
- `adapters/parts/jinja_primitive_adapter.py`: new reusable B-grade template generators and `_specialized_template()` routing.
- `parts_library.default.yaml`: explicit default routing rules before terminal fallback, with linear-guide rules placed before generic bearing rules and transmission rules folded into the existing transmission block instead of duplicated.
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
        ("HGW15 直线导轨滑块", "", "bearing"),
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
    ("name", "material", "expected"),
    [
        ("M12 电感接近开关", "PNP NO", "sensor"),
        ("608ZZ 深沟球轴承", "", "bearing"),
        ("普通滑块", "POM 20×10×6mm", "other"),
        ("PC6 控制板", "PCB 20×30mm", "other"),
        ("M12 六角螺母", "GB/T 6170", "fastener"),
    ],
)
def test_batch_2_classifier_does_not_steal_ambiguous_rows(
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
        ("connector", "M12 5芯航空插头", "", "m12_connector", (16.2, 16.2, 26.6)),
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
    ("category", "name", "material", "forbidden_template"),
    [
        ("bearing", "608ZZ 深沟球轴承", "", "linear_guide_carriage"),
        ("bearing", "普通滑块", "POM 20×10×6mm", "linear_guide_carriage"),
        ("connector", "M12 电感接近开关", "PNP NO", "m12_connector"),
        ("pneumatic", "PC6 控制板", "PCB 20×30mm", "pneumatic_push_fitting"),
        ("transmission", "同步带 400mm", "GT2 闭环", "gt2_timing_pulley"),
    ],
)
def test_batch_2_templates_require_specific_family_intent(
    category: str,
    name: str,
    material: str,
    forbidden_template: str,
) -> None:
    result = JinjaPrimitiveAdapter().resolve(_q(category, name, material), {})

    assert result.metadata.get("template") != forbidden_template


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
    ("query", "expected_category", "expected_adapter"),
    [
        (_q("bearing", "MGN12H 直线导轨滑块"), "bearing", "jinja_primitive"),
        (_q("transmission", "GT2 30T 同步带轮", "孔径8mm 6mm带宽"), "transmission", "jinja_primitive"),
        (_q("connector", "KF301 接线端子", "3P 5.08mm"), "connector", "jinja_primitive"),
        (_q("pneumatic", "二位五通电磁阀", "DC24V"), "pneumatic", "jinja_primitive"),
    ],
)
def test_default_library_has_explicit_batch_2_rules_before_terminal_fallback(
    query: PartQuery,
    expected_category: str,
    expected_adapter: str,
) -> None:
    resolver = default_resolver(project_root="__missing_project__")

    rules = resolver.matching_rules(query, adapter_name=expected_adapter)

    assert rules
    assert rules[0]["match"].get("category") == expected_category


def test_linear_guide_rule_precedes_generic_bearing_routes_but_not_vendor_steps() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("bearing", "MGN12H 直线导轨滑块")

    matching = resolver.matching_rules(query)

    assert matching[0]["adapter"] == "jinja_primitive"
    assert matching[0]["match"].get("name_contains") == [
        "直线导轨",
        "linear guide",
        "MGN",
        "HGW",
        "HGH",
        "导轨滑块",
    ]


def test_normal_ball_bearing_still_prefers_standard_bearing_routes() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("bearing", "608ZZ 深沟球轴承")

    matching = resolver.matching_rules(query)

    assert matching[0]["adapter"] in {"sw_toolbox", "bd_warehouse"}
    assert matching[0]["adapter"] != "jinja_primitive"


def test_m12_proximity_sensor_keeps_sensor_rule_before_connector_rule() -> None:
    resolver = default_resolver(project_root="__missing_project__")
    query = _q("sensor", "M12 电感接近开关", "PNP NO")

    matching = resolver.matching_rules(query, adapter_name="jinja_primitive")

    assert matching
    assert matching[0]["match"].get("category") == "sensor"
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

Update `bom_parser.py` by adding only context-bearing keywords. Keep ambiguous tokens such as bare `滑块`, `PC6`, `PC8`, and `M12` out of the classifier keyword lists:

```python
("bearing",   ["轴承", "bearing", "MR1", "ZZ", "688", "608", "滚珠", "LM10", "LM12",
               "LM16", "LM20", "LMU", "KFL", "KP0", "KP1", "UCP", "UCF", "法兰座",
               "直线导轨", "导轨滑块", "linear guide", "MGN", "HGW", "HGH"]),
("sensor",    ["传感器", "sensor", "AE", "UHF", "Nano17", "力矩", "检测", "接近开关",
               "光电", "限位", "编码器", "encoder"]),
("pneumatic", ["气缸", "pneumatic", "cylinder actuator", "air cylinder",
               "MGPM", "MGPL", "SDA", "CQ2", "SCJ", "电磁阀", "solenoid valve",
               "气管接头", "快插", "push fitting", "调压阀", "过滤减压阀"]),
("pump",      ["泵", "pump", "齿轮泵"]),
("connector", ["连接器", "connector", "LEMO", "SMA", "Molex", "ZIF", "插座", "插头",
               "端子", "接线端子", "terminal block", "KF301", "Phoenix", "航空插头"]),
```

Do not add broad keywords like `阀` alone because they can misclassify fluid pumps or process valves.
Do not add `M12` to connector classification because M12 is also a common sensor/thread/fastener size; M12 connector templates must be selected by connector context such as `插头`, `航空插头`, or `connector`.

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
For M12 connectors, either make `_gen_m12_connector()` fit inside `(12, 12, 18)` by drawing details inward, or report the true visual envelope `(16.2, 16.2, 26.6)` from `_specialized_template()`. The tests above choose the second path to preserve the existing flange/gland visual detail without lying about `real_dims`.

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
    w = dims.get("w", 45)
    d = dims.get("d", 27)
    h = dims.get("h", 15)
    rail_w = min(dims.get("rail_w", 12), d * 0.72)
    rail_h = min(dims.get("rail_h", 8), h * 0.58)
    rail_l = min(dims.get("rail_l", 80), max(w, d) * 3.5)
    carriage_h = max(h - rail_h, h * 0.38)
    bolt_d = max(min(w, d) * 0.10, 2.0)
    bolt_x = max(w * 0.28, bolt_d)
    bolt_y = max(d * 0.24, bolt_d)
    return f"""    # Linear guide carriage: rail stub, block, bolt counterbores, center groove
    rail = (cq.Workplane("XY")
            .box({rail_l:.3f}, {rail_w:.3f}, {rail_h:.3f}, centered=(True, True, False)))
    block = (cq.Workplane("XY")
             .box({w:.3f}, {d:.3f}, {carriage_h:.3f}, centered=(True, True, False))
             .translate((0, 0, {rail_h:.3f})))
    body = rail.union(block)
    groove = (cq.Workplane("XY")
              .box({w * 0.82:.3f}, {max(d * 0.08, 1.2):.3f}, {carriage_h + 0.2:.3f}, centered=(True, True, False))
              .translate((0, 0, {rail_h + carriage_h * 0.12:.3f})))
    body = body.cut(groove)
    for x in ({-bolt_x:.3f}, {bolt_x:.3f}):
        for y in ({-bolt_y:.3f}, {bolt_y:.3f}):
            pocket = (cq.Workplane("XY")
                      .center(x, y)
                      .circle({bolt_d:.3f})
                      .extrude({carriage_h * 0.35:.3f})
                      .translate((0, 0, {rail_h + carriage_h * 0.65:.3f})))
            body = body.cut(pocket)
    return body"""


def _gen_clamping_coupling_lxx(dims: dict) -> str:
    d = dims.get("d", 25)
    l = dims.get("l", 30)
    bore_d = min(dims.get("bore_d", 6.35), d * 0.72)
    groove_w = max(min(l * 0.06, 1.8), 1.0)
    groove_inner_r = max(d / 2 - 0.8, bore_d / 2 + 1.0)
    slot_w = max(d * 0.12, 2.0)
    screw_d = max(bore_d * 0.55, 3.0)
    return f"""    # Lxx clamping coupling: split cylindrical coupler with twin clamp grooves
    body = cq.Workplane("XY").circle({d/2:.3f}).circle({bore_d/2:.3f}).extrude({l:.3f})
    for z in ({l * 0.28:.3f}, {l * 0.68:.3f}):
        groove = (cq.Workplane("XY")
                  .circle({d/2 + 0.05:.3f})
                  .circle({groove_inner_r:.3f})
                  .extrude({groove_w:.3f})
                  .translate((0, 0, z)))
        body = body.cut(groove)
    split = (cq.Workplane("XY")
             .box({slot_w:.3f}, {d + 0.2:.3f}, {l + 0.2:.3f}, centered=(True, True, False))
             .translate(({d * 0.32:.3f}, 0, -0.1)))
    body = body.cut(split)
    for z in ({l * 0.28:.3f}, {l * 0.68:.3f}):
        screw_socket = (cq.Workplane("YZ")
                        .center(0, z)
                        .circle({screw_d/2:.3f})
                        .extrude({d + 0.4:.3f})
                        .translate(({-(d / 2 + 0.2):.3f}, 0, 0)))
        body = body.cut(screw_socket)
        clamp_band = (cq.Workplane("XY")
                      .circle({d/2:.3f})
                      .circle({max(d/2 - 1.15, bore_d/2 + 1.5):.3f})
                      .extrude({groove_w * 0.65:.3f})
                      .translate((0, 0, z + {groove_w:.3f})))
        body = body.union(clamp_band)
    return body"""


def _gen_gt2_timing_pulley(dims: dict) -> str:
    od = dims.get("od", 16)
    w = dims.get("w", 8)
    bore_d = min(dims.get("id", 6.35), od * 0.72)
    teeth = max(12, min(int(dims.get("teeth", 20)), 80))
    hub_d = min(max(bore_d * 1.45, od * 0.48), od * 0.82)
    tooth_depth = max(od * 0.045, 0.45)
    tooth_w = max(min(od * 3.14159 / teeth * 0.50, od * 0.11), 0.8)
    base_od = max(od - 2 * tooth_depth, bore_d + 2.0)
    tooth_radius = max(base_od / 2 + tooth_depth / 2, bore_d / 2 + 1.0)
    return f"""    # GT2 timing pulley: visual bounded teeth, bore, and center hub
    body = cq.Workplane("XY").circle({base_od/2:.3f}).circle({bore_d/2:.3f}).extrude({w:.3f})
    hub = cq.Workplane("XY").circle({hub_d/2:.3f}).circle({bore_d/2:.3f}).extrude({w:.3f})
    body = body.union(hub)
    for i in range({teeth}):
        angle = i * {360.0 / teeth:.9f}
        tooth = (cq.Workplane("XY")
                 .box({tooth_depth:.3f}, {tooth_w:.3f}, {w:.3f}, centered=(True, True, False))
                 .translate(({tooth_radius:.3f}, 0, 0))
                 .rotate((0, 0, 0), (0, 0, 1), angle))
        body = body.union(tooth)
    return body"""


def _gen_spur_gear(dims: dict) -> str:
    od = dims.get("od", 22)
    w = dims.get("w", 8)
    bore_d = min(dims.get("id", 6), od * 0.60)
    teeth = max(10, min(int(dims.get("teeth", 20)), 96))
    root_od = max(od * 0.82, bore_d + 3.0)
    tooth_depth = max((od - root_od) / 2, 0.6)
    tooth_w = max(min(od * 3.14159 / teeth * 0.45, od * 0.10), 0.7)
    tooth_radius = root_od / 2 + tooth_depth / 2
    return f"""    # Spur gear: bounded visual teeth with bore and root disk
    body = cq.Workplane("XY").circle({root_od/2:.3f}).circle({bore_d/2:.3f}).extrude({w:.3f})
    for i in range({teeth}):
        angle = i * {360.0 / teeth:.9f}
        tooth = (cq.Workplane("XY")
                 .box({tooth_depth:.3f}, {tooth_w:.3f}, {w:.3f}, centered=(True, True, False))
                 .translate(({tooth_radius:.3f}, 0, 0))
                 .rotate((0, 0, 0), (0, 0, 1), angle))
        body = body.union(tooth)
    return body"""


def _gen_terminal_block(dims: dict, pins: int) -> str:
    w = dims.get("w", pins * dims.get("pitch", 5.08))
    d = dims.get("d", 8)
    h = dims.get("h", 10)
    pitch = w / max(pins, 1)
    screw_d = min(pitch * 0.42, d * 0.46)
    pocket_w = min(pitch * 0.62, pitch - 0.25)
    return f"""    # Terminal block: plastic body, bounded screw pockets and wire entries
    body = cq.Workplane("XY").box({w:.3f}, {d:.3f}, {h:.3f}, centered=(True, True, False))
    for i in range({pins}):
        x = (i - ({pins} - 1) / 2.0) * {pitch:.3f}
        screw = (cq.Workplane("XY")
                 .center(x, {d * 0.18:.3f})
                 .circle({screw_d/2:.3f})
                 .extrude({h * 0.22:.3f})
                 .translate((0, 0, {h * 0.74:.3f})))
        entry = (cq.Workplane("XY")
                 .center(x, {-d * 0.38:.3f})
                 .box({pocket_w:.3f}, {d * 0.20:.3f}, {h * 0.30:.3f}, centered=(True, True, False))
                 .translate((0, 0, {h * 0.18:.3f})))
        body = body.cut(screw).cut(entry)
    return body"""


def _gen_pneumatic_solenoid_valve(dims: dict) -> str:
    w = dims.get("w", 45)
    d = dims.get("d", 22)
    h = dims.get("h", 28)
    coil_w = w * 0.34
    body_w = w - coil_w
    port_d = min(d * 0.24, h * 0.16)
    return f"""    # Pneumatic solenoid valve: manifold, coil block, bounded port details
    manifold = (cq.Workplane("XY")
                .box({body_w:.3f}, {d:.3f}, {h * 0.62:.3f}, centered=(True, True, False))
                .translate(({-(coil_w / 2):.3f}, 0, 0)))
    coil = (cq.Workplane("XY")
            .box({coil_w:.3f}, {d * 0.82:.3f}, {h:.3f}, centered=(True, True, False))
            .translate(({body_w / 2:.3f}, 0, 0)))
    body = manifold.union(coil)
    for x in ({-body_w * 0.58:.3f}, {-body_w * 0.30:.3f}, {-body_w * 0.02:.3f}):
        port = (cq.Workplane("XY")
                .center(x, {-d * 0.40:.3f})
                .circle({port_d/2:.3f})
                .extrude({h * 0.20:.3f})
                .translate((0, 0, {h * 0.36:.3f})))
        body = body.cut(port)
    return body"""


def _gen_pneumatic_push_fitting(dims: dict) -> str:
    d = dims.get("d", 12)
    l = dims.get("l", 22)
    tube_d = min(dims.get("tube_d", 6), d * 0.72)
    hex_d = min(d * 0.96, max(tube_d * 1.6, d * 0.72))
    collet_d = min(d, max(tube_d * 1.55, tube_d + 3.0))
    hex_l = l * 0.34
    collet_l = l * 0.32
    thread_l = l - hex_l - collet_l
    return f"""    # Pneumatic push fitting: hex body, threaded stub, push collet, tube bore
    hex_body = cq.Workplane("XY").polygon(6, {hex_d:.3f}).extrude({hex_l:.3f})
    thread = (cq.Workplane("XY")
              .circle({max(tube_d * 0.62, 2.0):.3f})
              .circle({tube_d/2:.3f})
              .extrude({thread_l:.3f})
              .translate((0, 0, {hex_l:.3f})))
    collet = (cq.Workplane("XY")
              .circle({collet_d/2:.3f})
              .circle({tube_d/2:.3f})
              .extrude({collet_l:.3f})
              .translate((0, 0, {hex_l + thread_l:.3f})))
    body = hex_body.union(thread).union(collet)
    return body"""
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
        text, ["直线导轨", "linear guide", "MGN", "HGW", "HGH", "导轨滑块"]
    ):
        defaults = {
            "MGN15H": {"w": 55, "d": 32, "h": 20, "rail_w": 15, "rail_h": 10, "rail_l": 100},
            "MGN12H": {"w": 45, "d": 27, "h": 15, "rail_w": 12, "rail_h": 8, "rail_l": 80},
            "HGW15": {"w": 47, "d": 34, "h": 24, "rail_w": 15, "rail_h": 12, "rail_l": 110},
            "HGH15": {"w": 34, "d": 39, "h": 28, "rail_w": 15, "rail_h": 12, "rail_l": 110},
        }
        tpl_dims = next((value for key, value in defaults.items() if key in text.upper()), defaults["MGN12H"])
        tpl_dims = {**tpl_dims, **{k: dims[k] for k in tpl_dims if k in dims}}
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
- `m12_connector`: extend existing M12 logic to category `connector` as well as `other`; return `dims={"d": 16.2, "l": 26.6}` or an equivalent envelope that contains the existing shell, flange, gland, pins, and key.
- `pneumatic_solenoid_valve`: match `电磁阀`, `solenoid valve`.
- `pneumatic_push_fitting`: match `快插`, `气管接头`, or `push fitting`; use `PC6` / `PC8` only to derive `tube_d` after one of those context tokens is present.

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

- [ ] **Step 1: Add explicit default rules in the correct registry positions**

Do not append all Batch 2 rules after the first-batch block. Insert them in the positions below so first-hit-wins stays correct:

- Insert the linear-guide `bearing` rule after vendor STEP rules and before the first `bd_warehouse`/`sw_toolbox` generic bearing rule.
- Keep existing vendor STEP `connectors/m12_4pin_bulkhead.step` and part-number rules above connector B-grade templates.
- Replace the existing broad `category: transmission` jinja rule at the current transmission block with the narrower two-rule form below; do not create a second generic transmission fallback.
- Keep the `parametric_transmission` lead-screw rule above all generic transmission B-grade routes.
- In the common electromechanical block, replace the broad `category: pneumatic` rule with the explicit pneumatic Batch 2 rule below.

Use these mappings:

```yaml
  - match:
      category: bearing
      name_contains: ["直线导轨", "linear guide", "MGN", "HGW", "HGH", "导轨滑块"]
    adapter: jinja_primitive

  - match:
      category: transmission
      keyword_contains: ["联轴器", "coupling", "GT2", "带轮", "pulley", "齿轮", "spur gear", "同步带"]
    adapter: jinja_primitive
    spec:
      standard: [GB, GB/T]
      subcategories: ["couplings", "timing_pulleys", "spur_gears", "sprockets", "timing_belts"]
      part_category: transmission

  - match:
      category: transmission
    adapter: jinja_primitive
    spec:
      standard: [GB, GB/T]
      subcategories: ["spur_gears", "sprockets"]
      part_category: transmission

  - match:
      category: connector
      name_contains: ["端子", "接线端子", "terminal block", "KF301", "Phoenix", "航空插头", "M12 connector", "M12 插头"]
    adapter: jinja_primitive

  - match:
      category: pneumatic
      keyword_contains: ["电磁阀", "solenoid valve", "快插", "push fitting", "气管接头", "调压阀", "过滤减压阀"]
    adapter: jinja_primitive
```

Important ordering:

- Keep vendor STEP and SolidWorks/Toolbox part-number/vendor rules above default B-grade templates.
- For `bearing`, do not steal normal ball bearing rows from `bd_warehouse`/Toolbox; require linear-guide family keywords and use `name_contains` so a material token cannot hijack a normal bearing row.
- For `connector`, do not use bare `M12` as a route keyword. M12 proximity sensors already have a sensor route and must keep it.
- For `pneumatic`, do not use bare `PC6` / `PC8` as route keywords. They are fitting size clues only after fitting context exists.
- For `transmission`, leave the lead-screw rule above generic transmission routes and avoid duplicate broad `category: transmission` rules.

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


def test_batch_2_linear_guide_route_precedes_generic_bearing_routes() -> None:
    query = PartQuery(
        part_no="B2-LINEAR-GUIDE",
        name_cn="MGN12H 直线导轨滑块",
        material="",
        category="bearing",
        make_buy="外购",
    )

    rules = default_resolver(project_root="__missing_project__").matching_rules(query)

    assert rules[0]["adapter"] == "jinja_primitive"
    assert rules[0]["match"].get("name_contains") == [
        "直线导轨",
        "linear guide",
        "MGN",
        "HGW",
        "HGH",
        "导轨滑块",
    ]


def test_batch_2_normal_bearing_route_is_not_stolen_by_linear_guide() -> None:
    query = PartQuery(
        part_no="B2-BEARING",
        name_cn="608ZZ 深沟球轴承",
        material="",
        category="bearing",
        make_buy="外购",
    )

    rules = default_resolver(project_root="__missing_project__").matching_rules(query)

    assert rules[0]["adapter"] in {"sw_toolbox", "bd_warehouse"}


def test_batch_2_m12_sensor_route_is_not_stolen_by_connector_rule() -> None:
    query = PartQuery(
        part_no="B2-SENSOR",
        name_cn="M12 电感接近开关",
        material="PNP NO",
        category="sensor",
        make_buy="外购",
    )

    rules = default_resolver(project_root="__missing_project__").matching_rules(
        query,
        adapter_name="jinja_primitive",
    )

    assert rules[0]["match"].get("category") == "sensor"
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
git status --short
git add bom_parser.py cad_spec_defaults.py adapters/parts/jinja_primitive_adapter.py parts_library.default.yaml tests/test_common_model_library_batch_2.py tests/test_parts_library_standard_categories.py tests/test_jinja_generators_new.py docs/PROGRESS.md docs/superpowers/README.md docs/superpowers/plans/2026-05-04-common-model-library-batch-2.md
git status --short
git commit -m "feat(parts-library): 扩展常用模型库第二批"
```

If `git status --short` shows mirror files under `src/cad_spec_gen/data/`, add only those exact paths. Use `git add -f <exact ignored mirror path>` only when Git refuses a specific mirror file that `scripts/dev_sync.py --check` requires; do not force-add ignored generated data directories wholesale.

---

## Self-Review Notes

- Spec coverage: plan covers classification, dimensions, templates, default routes, geometry envelope constraints, docs, mirrors, and final tests.
- Placeholder scan: no placeholder tokens or open-ended test-writing steps remain.
- Type consistency: template IDs in tests match planned `_specialized_template()` return values: `linear_guide_carriage`, `clamping_coupling_lxx`, `gt2_timing_pulley`, `spur_gear`, `terminal_block`, `m12_connector`, `pneumatic_solenoid_valve`, `pneumatic_push_fitting`.
- Boundary guard: plan requires explicit keywords for linear guides, connectors, transmission families, and pneumatic accessories; it avoids broad `bearing`, `connector`, or `pneumatic` catch-alls that would steal real-model routes.
