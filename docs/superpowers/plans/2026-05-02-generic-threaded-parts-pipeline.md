# Generic Threaded Parts Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Implementation Status

Status as of 2026-05-04: this plan is now an archived implementation plan, not an open scratch draft.

- Tasks 1-6 landed on `main` through the generic threaded / Photo3D work chain, including `603fda0 feat(parts): 增加参数化梯形丝杠生成器` and `ca22f7d feat(codegen): 将标准化自制件纳入模型库路由`.
- The original checkbox list below is preserved as the execution checklist used to build the feature; it is not the current project kanban.
- Task 7's older `tools/photo3d_report.py` sketch was superseded by the contract-driven Photo3D pipeline in `docs/superpowers/plans/2026-05-02-contract-driven-photo3d-pipeline.md`, including `photo3d`, `ACTION_PLAN.json`, `LLM_CONTEXT_PACK.json`, and explicit `accept-baseline`.
- Remaining product work is tracked in `docs/PROGRESS.md`: ordinary-user Photo3D autopilot, broader common model-library coverage, and enhancement acceptance scoring.

**Goal:** Add a reusable threaded/transmission part pipeline so parts like `SLP-P01` lead screws are generated from generic library rules instead of hand-tuned one-off CadQuery modules.

**Architecture:** Extend the existing `PartsResolver` and `parts_library.default.yaml` path instead of creating a parallel model system. Classify threaded/lead-screw BOM rows as `transmission`, parse screw parameters from BOM text, §6.4 envelopes, and explicit `parts_library.yaml` mappings, generate CadQuery or library-backed geometry through a new curated parametric adapter, and write geometry-quality evidence for both purchased and custom library-routed parts. Rendering and AI enhancement remain downstream consumers of CAD-layer geometry instead of image-only thread illusions.

**Tech Stack:** Python 3.10+, pytest, CadQuery, existing `PartsResolver`, `codegen/gen_parts.py`, `codegen/gen_std_parts.py`, `parts_library.default.yaml`, optional future `cq_warehouse`.

---

## Current Baseline

The project already has a strong generic model-library skeleton:

- `parts_resolver.py` dispatches YAML mappings to `step_pool`, `bd_warehouse`, `sw_toolbox`, `partcad`, and `jinja_primitive`.
- `parts_library.default.yaml` has default rules for fasteners, bearings, transmission-like vendor stand-ins, and SolidWorks Toolbox fallbacks.
- `codegen/gen_std_parts.py` writes geometry-quality reports under `cad/<subsystem>/.cad-spec-gen/geometry_report.json`.
- `codegen/gen_parts.py` currently owns all `自制` leaf parts and emits custom modules directly.
- `SLP-P01` is currently generated as `cad/lifting_platform/p01.py`; its source says `Simplified as stepped cylinder (no thread detail)`.

The problem is not Phase 5 enhancement. The lead screw is already a smooth stepped cylinder in Phase 2/3 CAD geometry, so downstream renders and AI enhancers can only fake thread appearance. The fix belongs in Phase 2/3.

## Scope

This plan implements a generic path for **standardized custom/mechanical transmission parts**:

- Lead screws: `Tr16×4`, `T16`, `梯形丝杠`, `lead screw`.
- Threaded rods/screws where thread is a primary visual/mechanical feature.
- Future-compatible structure for gears, sprockets, pulleys, couplers, and shafts.

This plan does **not** implement every vendor catalog or a full external CAD marketplace. It creates the reusable pipeline seam so additional model sources can be added by mapping, not by editing each generated part file.

## File Structure

- Create `adapters/parts/parametric_transmission.py`
  - Own curated CadQuery builders for reusable transmission parts.
  - First builder: `make_trapezoidal_lead_screw(...)`.
  - Keep implementation independent of any one subsystem.
- Create `adapters/parts/parametric_transmission_adapter.py`
  - `PartsAdapter` implementation that parses registry `spec.template` and emits `ResolveResult(kind="codegen")`.
  - First template: `trapezoidal_lead_screw`.
- Modify `parts_resolver.py`
  - Register the new adapter.
  - Infer `PartCategory.STANDARD_TRANSMISSION` for the new adapter.
- Modify `bom_parser.py`
  - Improve `classify_part()` so `丝杠`, `lead screw`, `Tr16×4`, and `T16` classify as `transmission`.
- Modify `parts_library.default.yaml`
  - Add conservative default rules for lead screws before generic transmission fallback.
  - Do not put `SLP-P01`-specific shaft lengths in the global default file.
- Create `codegen/library_routing.py`
  - Own the single predicate for "自制 but resolver/library-routed" rows.
  - Own the module/function naming convention for resolver-routed custom rows.
- Modify `codegen/gen_std_parts.py`
  - Allow `自制` rows to be handled by resolver when `codegen/library_routing.py` says they are library-routed.
  - Keep ordinary custom plates/brackets in `gen_parts.py`.
- Modify `codegen/gen_parts.py`
  - Skip custom rows that are handled by the same resolver-backed library route.
- Modify `codegen/gen_build.py`
  - Export resolver-routed custom modules through the `std_*` STEP build path instead of the DXF-only custom path.
- Modify `codegen/gen_assembly.py`
  - Import resolver-routed custom rows from `std_*` modules just like purchased/standard rows.
- Modify `tools/model_audit.py` or report writing path
  - Include resolver-routed standardized custom parts in geometry reports.
- Later create `tools/photo3d_report.py`
  - Summarize model coverage, render coverage, enhancement backend, and image quality checks for generic product runs.
- Later modify `cad_pipeline.py`
  - Add `photo3d` or `full --photo` as the productized one-command path for photo-grade outputs.
- Add tests:
  - `tests/test_bom_classifier_threaded_parts.py`
  - `tests/test_parametric_transmission.py`
  - `tests/test_parametric_transmission_adapter.py`
  - `tests/test_library_routing.py`
  - `tests/test_custom_parts_resolver_routing.py`
  - `tests/test_lifting_platform_lead_screw_pipeline.py`
  - Later `tests/test_photo3d_autopilot.py`

## Data Contracts

Default mapping shape:

```yaml
- match:
    category: transmission
    keyword_contains: ["丝杠", "梯形丝杠", "lead screw", "leadscrew", "T16"]
  adapter: parametric_transmission
  spec:
    template: trapezoidal_lead_screw
    parameter_source: bom_text_or_project_mapping
    defaults:
      root_diameter_mm: null
      thread_length_mm: null
      lower_shaft_diameter_mm: null
      lower_shaft_length_mm: 0.0
      upper_shaft_diameter_mm: null
      upper_shaft_length_mm: 0.0
      visual_thread: true
      normalize_origin: center_xy_bottom_z
```

Project-specific mapping for `SLP-P01` should live in project `parts_library.yaml`, not in the global default file:

```yaml
mappings:
  - match:
      part_no: SLP-P01
    adapter: parametric_transmission
    spec:
      template: trapezoidal_lead_screw
      defaults:
        outer_diameter_mm: 16.0
        pitch_mm: 4.0
        total_length_mm: 350.0
        thread_length_mm: 230.0
        lower_shaft_diameter_mm: 12.0
        lower_shaft_length_mm: 70.0
        upper_shaft_diameter_mm: 12.0
        upper_shaft_length_mm: 40.0
```

Parameter precedence:

1. Explicit values in the matched mapping `spec.defaults`.
2. Parsed BOM/spec text such as `Tr16×4`, `T16`, `L350`.
3. §6.4 envelope, using the largest dimension as total length and the smallest circular envelope dimension as outer diameter.
4. Conservative template fallback values only when they do not invent subsystem-specific shaft details.

`thread_length_mm: null` means "derive thread length from shaft lengths": `total_length_mm - lower_shaft_length_mm - upper_shaft_length_mm`. It does not mean "thread the full total length" unless both shaft lengths are zero.

Adapter result contract:

```python
ResolveResult(
    status="hit",
    kind="codegen",
    adapter="parametric_transmission",
    geometry_source="PARAMETRIC_TEMPLATE",
    geometry_quality="B",
    validated=True,
    requires_model_review=False,
    source_tag="parametric_transmission:trapezoidal_lead_screw(Tr16x4,L350)",
)
```

Generated module contract:

- Resolver/library-routed modules use the existing `std_*` prefix and expose `make_std_*() -> cq.Workplane`.
- In this plan, `std_*` means "resolver-generated geometry module", not only purchased/standard BOM rows.
- Local origin is `center_xy_bottom_z`: XY centered on shaft axis, Z=0 at bottom tip.
- Overall bounding box for `SLP-P01` remains close to `16 × 16 × 350 mm`.
- The thread body contains visible helical CAD geometry or a deterministic visual thread cue.
- Build/render downstream sees CAD-layer geometry, not an image-only illusion.
- The first implementation is render/recognition grade, not a manufacturing-grade swept trapezoidal thread profile or vendor STEP.

## Task 1: Classify Lead Screws as Transmission Parts

**Files:**
- Modify: `bom_parser.py`
- Create: `tests/test_bom_classifier_threaded_parts.py`

- [ ] **Step 1: Write failing classifier tests**

Create `tests/test_bom_classifier_threaded_parts.py`:

```python
from bom_parser import classify_part


def test_trapezoidal_lead_screw_classifies_as_transmission():
    assert classify_part("丝杠 L350", "Tr16×4, 45#钢") == "transmission"


def test_t16_lead_screw_classifies_as_transmission():
    assert classify_part("T16 丝杠", "L350 pitch 4") == "transmission"


def test_english_lead_screw_classifies_as_transmission():
    assert classify_part("Lead screw Tr16x4", "350mm steel") == "transmission"


def test_plain_support_shaft_does_not_become_transmission():
    assert classify_part("导向轴 L296", "GCr15 Φ10×296") != "transmission"
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_bom_classifier_threaded_parts.py -q
```

Expected: at least the lead screw cases fail or classify as `other`.

- [ ] **Step 3: Implement minimal classifier update**

In `bom_parser.py::classify_part()`, add lead-screw terms to the existing transmission branch. Use combined `name + material` lowercased text:

```python
threaded_transmission_keywords = [
    "丝杠",
    "lead screw",
    "leadscrew",
    "trapezoidal screw",
    "梯形螺纹",
]
if any(k in text for k in threaded_transmission_keywords):
    return "transmission"
if re.search(r"\btr\s*\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?\b", text, re.I):
    return "transmission"
if re.search(r"\bt\s*\d+\b", text, re.I) and ("螺母" in text or "丝杠" in text):
    return "transmission"
```

- [ ] **Step 4: Verify classifier tests pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_bom_classifier_threaded_parts.py tests/test_bom_classifier_new_categories.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add bom_parser.py tests/test_bom_classifier_threaded_parts.py
git commit -m "feat(parts): 识别丝杠为传动件"
```

## Task 2: Add Reusable Parametric Lead-Screw Builder

**Files:**
- Create: `adapters/parts/parametric_transmission.py`
- Create: `tests/test_parametric_transmission.py`

- [ ] **Step 1: Write failing geometry tests**

Create `tests/test_parametric_transmission.py`:

```python
import math

import cadquery as cq

from adapters.parts.parametric_transmission import make_trapezoidal_lead_screw


def _bbox(obj):
    bb = obj.val().BoundingBox()
    return (
        round(bb.xlen, 1),
        round(bb.ylen, 1),
        round(bb.zlen, 1),
    )


def test_trapezoidal_lead_screw_preserves_overall_envelope():
    screw = make_trapezoidal_lead_screw(
        outer_diameter_mm=16.0,
        pitch_mm=4.0,
        total_length_mm=350.0,
        thread_length_mm=230.0,
        lower_shaft_diameter_mm=12.0,
        lower_shaft_length_mm=70.0,
        upper_shaft_diameter_mm=12.0,
        upper_shaft_length_mm=40.0,
    )

    assert _bbox(screw) == (16.0, 16.0, 350.0)


def test_trapezoidal_lead_screw_has_visible_thread_cues():
    screw = make_trapezoidal_lead_screw(
        outer_diameter_mm=16.0,
        pitch_mm=4.0,
        total_length_mm=120.0,
        thread_length_mm=80.0,
        lower_shaft_diameter_mm=12.0,
        lower_shaft_length_mm=20.0,
        upper_shaft_diameter_mm=12.0,
        upper_shaft_length_mm=20.0,
    )

    solids = screw.val().Solids()
    assert len(solids) >= 1
    # Thread geometry should have enough edges/faces to be visually distinct
    # from a plain stepped cylinder.
    assert len(screw.val().Edges()) > 80
    assert len(screw.val().Faces()) > 20
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_parametric_transmission.py -q
```

Expected: import failure for `adapters.parts.parametric_transmission`.

- [ ] **Step 3: Implement a deterministic visual-thread CadQuery builder**

Create `adapters/parts/parametric_transmission.py`:

```python
from __future__ import annotations

import math

import cadquery as cq


def _ring(z: float, outer_d: float, inner_d: float, height: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .workplane(offset=z)
        .circle(outer_d / 2.0)
        .circle(inner_d / 2.0)
        .extrude(height)
    )


def _helical_thread_cues(
    *,
    outer_diameter_mm: float,
    root_diameter_mm: float,
    pitch_mm: float,
    thread_length_mm: float,
    start_z_mm: float,
    starts: int = 1,
) -> cq.Workplane:
    """Build a visual helical thread cue that keeps bbox deterministic.

    This is a rendering/recognition-grade thread, not a manufacturing-grade
    swept trapezoidal profile. The builder creates many short tangent ribs
    around the root cylinder so the model reads as a visibly threaded lead screw in
    Blender and AI enhancement while keeping build time predictable.
    """
    root_r = root_diameter_mm / 2.0
    outer_r = outer_diameter_mm / 2.0
    rib_depth = max(0.2, outer_r - root_r)
    rib_width = max(0.35, pitch_mm * 0.28)
    rib_height = max(0.35, pitch_mm * 0.18)
    segments_per_turn = 18
    turns = max(1, int(math.ceil(thread_length_mm / pitch_mm)))
    total_segments = turns * segments_per_turn

    ribs = cq.Workplane("XY")
    for start in range(starts):
        phase = start * 360.0 / starts
        for i in range(total_segments):
            z = start_z_mm + min(thread_length_mm - rib_height, i * pitch_mm / segments_per_turn)
            angle = phase + i * 360.0 / segments_per_turn
            radial_center = root_r + rib_depth / 2.0
            rib = (
                cq.Workplane("XY")
                .box(rib_depth, rib_width, rib_height, centered=(True, True, False))
                .translate((radial_center, 0, z))
                .rotate((0, 0, 0), (0, 0, 1), angle)
            )
            ribs = ribs.union(rib)
    return ribs


def make_trapezoidal_lead_screw(
    *,
    outer_diameter_mm: float,
    pitch_mm: float,
    total_length_mm: float,
    thread_length_mm: float | None = None,
    lower_shaft_diameter_mm: float | None = None,
    lower_shaft_length_mm: float = 0.0,
    upper_shaft_diameter_mm: float | None = None,
    upper_shaft_length_mm: float = 0.0,
    root_diameter_mm: float | None = None,
    starts: int = 1,
) -> cq.Workplane:
    """Return a centered-XY, bottom-Z lead screw with visible helical thread."""
    outer_d = float(outer_diameter_mm)
    pitch = float(pitch_mm)
    total_l = float(total_length_mm)
    lower_l = max(0.0, float(lower_shaft_length_mm))
    upper_l = max(0.0, float(upper_shaft_length_mm))
    thread_l = float(thread_length_mm) if thread_length_mm is not None else total_l - lower_l - upper_l
    thread_l = max(0.0, min(thread_l, total_l - lower_l - upper_l))
    root_d = float(root_diameter_mm) if root_diameter_mm else max(outer_d - pitch * 0.55, outer_d * 0.72)
    lower_d = float(lower_shaft_diameter_mm) if lower_shaft_diameter_mm else root_d
    upper_d = float(upper_shaft_diameter_mm) if upper_shaft_diameter_mm else root_d

    body = cq.Workplane("XY").circle(root_d / 2.0).extrude(0.001)
    if lower_l:
        body = body.union(cq.Workplane("XY").circle(lower_d / 2.0).extrude(lower_l))
    thread_root = (
        cq.Workplane("XY")
        .workplane(offset=lower_l)
        .circle(root_d / 2.0)
        .extrude(thread_l)
    )
    thread_cues = _helical_thread_cues(
        outer_diameter_mm=outer_d,
        root_diameter_mm=root_d,
        pitch_mm=pitch,
        thread_length_mm=thread_l,
        start_z_mm=lower_l,
        starts=starts,
    )
    upper_z = lower_l + thread_l
    upper = (
        cq.Workplane("XY")
        .workplane(offset=upper_z)
        .circle(upper_d / 2.0)
        .extrude(max(0.0, total_l - upper_z))
    )

    body = body.union(thread_root).union(thread_cues).union(upper)
    # Deterministic final cutter keeps ribs inside the requested OD and length.
    clip = cq.Workplane("XY").circle(outer_d / 2.0).extrude(total_l)
    body = body.intersect(clip)
    try:
        body = body.faces(">Z").edges().chamfer(0.12)
        body = body.faces("<Z").edges().chamfer(0.12)
    except Exception:
        pass
    return body
```

- [ ] **Step 4: Verify geometry tests pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_parametric_transmission.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Export a quick STEP smoke file**

Run:

```powershell
@'
import cadquery as cq
from adapters.parts.parametric_transmission import make_trapezoidal_lead_screw

s = make_trapezoidal_lead_screw(
    outer_diameter_mm=16,
    pitch_mm=4,
    total_length_mm=350,
    thread_length_mm=230,
    lower_shaft_diameter_mm=12,
    lower_shaft_length_mm=70,
    upper_shaft_diameter_mm=12,
    upper_shaft_length_mm=40,
)
cq.exporters.export(s, "cad/output/SLP-P01_threaded_smoke.step")
print(s.val().BoundingBox().xlen, s.val().BoundingBox().ylen, s.val().BoundingBox().zlen)
'@ | .venv\Scripts\python.exe -
```

Expected: bbox is approximately `16 16 350`; output file is ignored under `cad/output`.

- [ ] **Step 6: Commit**

```powershell
git add adapters/parts/parametric_transmission.py tests/test_parametric_transmission.py
git commit -m "feat(parts): 增加参数化梯形丝杠生成器"
```

## Task 3: Add Parametric Transmission Adapter

**Files:**
- Create: `adapters/parts/parametric_transmission_adapter.py`
- Modify: `parts_resolver.py`
- Create: `tests/test_parametric_transmission_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_parametric_transmission_adapter.py`:

```python
from adapters.parts.parametric_transmission_adapter import ParametricTransmissionAdapter
from parts_resolver import PartQuery, ResolveResult


def test_adapter_parses_tr16x4_l350_from_query_text():
    adapter = ParametricTransmissionAdapter()
    query = PartQuery(
        part_no="SLP-P01",
        name_cn="丝杠 L350",
        material="Tr16×4, 45#钢",
        category="transmission",
        make_buy="自制",
        spec_envelope=(16.0, 16.0, 350.0),
    )

    result = adapter.resolve(
        query,
        {"template": "trapezoidal_lead_screw", "defaults": {"thread_length_mm": 230.0}},
    )

    assert result.status == "hit"
    assert result.kind == "codegen"
    assert result.adapter == "parametric_transmission"
    assert result.geometry_source == "PARAMETRIC_TEMPLATE"
    assert result.geometry_quality == "B"
    assert "make_trapezoidal_lead_screw" in result.body_code
    assert "outer_diameter_mm=16.0" in result.body_code
    assert "pitch_mm=4.0" in result.body_code
    assert "total_length_mm=350.0" in result.body_code


def test_adapter_misses_unknown_template():
    adapter = ParametricTransmissionAdapter()
    query = PartQuery(
        part_no="P-001",
        name_cn="丝杠",
        material="Tr16x4",
        category="transmission",
        make_buy="自制",
    )

    result = adapter.resolve(query, {"template": "unknown"})

    assert result.status == "miss"
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_parametric_transmission_adapter.py -q
```

Expected: import failure for adapter.

- [ ] **Step 3: Implement adapter**

Create `adapters/parts/parametric_transmission_adapter.py`:

```python
from __future__ import annotations

import re
from typing import Optional

from adapters.parts.base import PartsAdapter


class ParametricTransmissionAdapter(PartsAdapter):
    name = "parametric_transmission"

    def is_available(self):
        return True, None

    def can_resolve(self, query) -> bool:
        return query.category == "transmission"

    def resolve(self, query, spec: dict, mode: str = "codegen"):
        from parts_resolver import ResolveResult

        template = spec.get("template")
        if template != "trapezoidal_lead_screw":
            return ResolveResult.miss()
        params = _parse_lead_screw_params(query, spec)
        if params is None:
            return ResolveResult.miss()
        body = _emit_lead_screw_body(params)
        return ResolveResult(
            status="hit",
            kind="codegen",
            adapter=self.name,
            body_code=body,
            real_dims=(params["outer_diameter_mm"], params["outer_diameter_mm"], params["total_length_mm"]),
            source_tag=(
                "parametric_transmission:"
                f"trapezoidal_lead_screw(Tr{params['outer_diameter_mm']:g}x{params['pitch_mm']:g},"
                f"L{params['total_length_mm']:g})"
            ),
            geometry_source="PARAMETRIC_TEMPLATE",
            geometry_quality="B",
            validated=True,
            requires_model_review=False,
        )

    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        params = _parse_lead_screw_params(query, spec)
        if params is None:
            return None
        return (params["outer_diameter_mm"], params["outer_diameter_mm"], params["total_length_mm"])


def _parse_lead_screw_params(query, spec: dict) -> dict | None:
    text = f"{query.name_cn} {query.material}"
    defaults = dict(spec.get("defaults") or {})
    env_dims = tuple(float(x) for x in (query.spec_envelope or ()) if x is not None)

    outer_d = _float_or_none(defaults.get("outer_diameter_mm"))
    pitch = _float_or_none(defaults.get("pitch_mm"))
    length = _float_or_none(defaults.get("total_length_mm"))

    tr = re.search(r"\btr\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\b", text, re.I)
    if tr:
        outer_d = outer_d if outer_d is not None else float(tr.group(1))
        pitch = pitch if pitch is not None else float(tr.group(2))
    else:
        t = re.search(r"\bt\s*(\d+(?:\.\d+)?)\b", text, re.I)
        if t and outer_d is None:
            outer_d = float(t.group(1))
    if outer_d is None and env_dims:
        outer_d = float(min(env_dims))
    if outer_d is None or pitch is None:
        return None

    length_match = re.search(r"\bL\s*(\d+(?:\.\d+)?)\b", text, re.I)
    if length is None and length_match:
        length = float(length_match.group(1))
    elif length is None and env_dims:
        length = float(max(env_dims))
    if length is None:
        return None

    lower_l = _float_or_none(defaults.get("lower_shaft_length_mm"))
    upper_l = _float_or_none(defaults.get("upper_shaft_length_mm"))
    lower_l = 0.0 if lower_l is None else max(0.0, lower_l)
    upper_l = 0.0 if upper_l is None else max(0.0, upper_l)
    available_thread_l = max(0.0, length - lower_l - upper_l)
    thread_l = _float_or_none(defaults.get("thread_length_mm"))
    thread_l = available_thread_l if thread_l is None else max(0.0, min(thread_l, available_thread_l))

    return {
        "outer_diameter_mm": outer_d,
        "pitch_mm": pitch,
        "total_length_mm": length,
        "thread_length_mm": thread_l,
        "lower_shaft_diameter_mm": _float_or_none(defaults.get("lower_shaft_diameter_mm")) or max(outer_d * 0.75, outer_d - pitch),
        "lower_shaft_length_mm": lower_l,
        "upper_shaft_diameter_mm": _float_or_none(defaults.get("upper_shaft_diameter_mm")) or max(outer_d * 0.75, outer_d - pitch),
        "upper_shaft_length_mm": upper_l,
        "root_diameter_mm": _float_or_none(defaults.get("root_diameter_mm")) or max(outer_d - pitch * 0.55, outer_d * 0.72),
        "starts": int(defaults.get("starts") or 1),
    }


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _emit_lead_screw_body(params: dict) -> str:
    lines = [
        "    from adapters.parts.parametric_transmission import make_trapezoidal_lead_screw",
        "    return make_trapezoidal_lead_screw(",
    ]
    for key in (
        "outer_diameter_mm",
        "pitch_mm",
        "total_length_mm",
        "thread_length_mm",
        "lower_shaft_diameter_mm",
        "lower_shaft_length_mm",
        "upper_shaft_diameter_mm",
        "upper_shaft_length_mm",
        "root_diameter_mm",
        "starts",
    ):
        lines.append(f"        {key}={params[key]!r},")
    lines.append("    )")
    return "\n".join(lines)
```

- [ ] **Step 4: Register adapter in `parts_resolver.py`**

In `default_resolver()`, register after `StepPoolAdapter` and before `PartCADAdapter`:

```python
try:
    from adapters.parts.parametric_transmission_adapter import ParametricTransmissionAdapter
    resolver.register_adapter(ParametricTransmissionAdapter())
except ImportError as e:
    if logger:
        logger(f"  [resolver] ParametricTransmissionAdapter unavailable: {e}")
```

Update category inference:

```python
_ADAPTER_NAME_TO_PART = {
    "jinja_primitive": PartCategory.CUSTOM,
    "parametric_transmission": PartCategory.STANDARD_TRANSMISSION,
}
```

- [ ] **Step 5: Verify adapter tests pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_parametric_transmission_adapter.py tests/test_parts_resolver.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add adapters/parts/parametric_transmission_adapter.py parts_resolver.py tests/test_parametric_transmission_adapter.py
git commit -m "feat(resolver): 接入参数化传动件适配器"
```

## Task 4: Route Standardized Custom Parts Through Resolver

**Files:**
- Create: `codegen/library_routing.py`
- Modify: `codegen/gen_std_parts.py`
- Modify: `codegen/gen_parts.py`
- Modify: `codegen/gen_build.py`
- Modify: `codegen/gen_assembly.py`
- Modify: `parts_library.default.yaml`
- Modify: `parts_library.yaml`
- Create: `tests/test_library_routing.py`
- Create: `tests/test_custom_parts_resolver_routing.py`

- [ ] **Step 1: Write failing shared routing tests**

Create `tests/test_library_routing.py`:

```python
from types import SimpleNamespace

from parts_resolver import PartQuery


def test_library_routing_identifies_resolver_routed_custom_lead_screw():
    from codegen.library_routing import build_library_part_query, is_library_routed_row

    rules = [
        {
            "match": {"category": "transmission", "keyword_contains": ["丝杠"]},
            "adapter": "parametric_transmission",
        }
    ]
    resolver = SimpleNamespace(matching_rules=lambda query: rules)
    part = {
        "part_no": "TST-P01",
        "name_cn": "丝杠 L350",
        "material": "Tr16×4, 45#钢",
        "make_buy": "自制",
    }

    query = build_library_part_query(
        part,
        category="transmission",
        envelope=(16.0, 16.0, 350.0),
        project_root=".",
    )

    assert isinstance(query, PartQuery)
    assert query.part_no == "TST-P01"
    assert query.spec_envelope == (16.0, 16.0, 350.0)
    assert is_library_routed_row(
        part,
        category="transmission",
        resolver=resolver,
        query=query,
    ) is True


def test_library_routing_does_not_route_plain_custom_plate():
    from codegen.library_routing import build_library_part_query, is_library_routed_row

    resolver = SimpleNamespace(matching_rules=lambda query: [])
    part = {
        "part_no": "TST-100",
        "name_cn": "安装板",
        "material": "6061-T6 铝 100×80×8mm",
        "make_buy": "自制",
    }
    query = build_library_part_query(
        part,
        category="other",
        envelope=(100.0, 80.0, 8.0),
        project_root=".",
    )

    assert is_library_routed_row(
        part,
        category="other",
        resolver=resolver,
        query=query,
    ) is False


def test_std_module_naming_is_shared_for_library_routed_custom_rows():
    from codegen.library_routing import library_make_function, library_module_name

    assert library_module_name("SLP-P01") == "std_p01"
    assert library_make_function("SLP-P01") == "make_std_p01"
```

- [ ] **Step 2: Verify shared routing tests fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_library_routing.py -q
```

Expected: import failure for `codegen.library_routing`.

- [ ] **Step 3: Add shared routing module**

Create `codegen/library_routing.py`:

```python
from __future__ import annotations

from cad_spec_defaults import strip_part_prefix
from parts_resolver import PartQuery


LIBRARY_ROUTED_CUSTOM_CATEGORIES = {"transmission", "elastic", "locating", "seal"}
LIBRARY_ROUTED_ADAPTERS = {"parametric_transmission", "step_pool", "partcad"}


def library_suffix(part_no: str) -> str:
    suffix = strip_part_prefix(part_no).lower().replace("-", "_")
    if suffix and suffix[0].isdigit():
        suffix = "p" + suffix
    return suffix


def library_module_name(part_no: str) -> str:
    return f"std_{library_suffix(part_no)}"


def library_make_function(part_no: str) -> str:
    return f"make_{library_module_name(part_no)}"


def build_library_part_query(
    part: dict,
    *,
    category: str,
    envelope,
    project_root: str,
) -> PartQuery:
    spec_envelope = envelope
    granularity = "part_envelope"
    if isinstance(envelope, dict):
        spec_envelope = envelope.get("dims")
        granularity = envelope.get("granularity") or "part_envelope"
    return PartQuery(
        part_no=part["part_no"],
        name_cn=part["name_cn"],
        material=part.get("material", ""),
        category=category,
        make_buy=part.get("make_buy", ""),
        spec_envelope=spec_envelope,
        spec_envelope_granularity=granularity,
        project_root=project_root,
    )


def is_library_routed_row(
    part: dict,
    *,
    category: str,
    resolver,
    query: PartQuery,
) -> bool:
    make_buy = part.get("make_buy", "")
    if "外购" in make_buy or "标准" in make_buy:
        return True
    if "自制" not in make_buy:
        return False
    if category not in LIBRARY_ROUTED_CUSTOM_CATEGORIES:
        return False
    matching_rules = getattr(resolver, "matching_rules", None)
    if matching_rules is None:
        return False
    for rule in matching_rules(query):
        if rule.get("adapter") in LIBRARY_ROUTED_ADAPTERS:
            return True
    return False
```

- [ ] **Step 4: Verify shared routing tests pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_library_routing.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Write failing end-to-end routing tests**

Create `tests/test_custom_parts_resolver_routing.py`:

```python
from pathlib import Path

from codegen.gen_assembly import generate_assembly
from codegen.gen_build import generate_build_tables, parse_bom_tree
from codegen.gen_parts import generate_part_files
from codegen.gen_std_parts import generate_std_part_files


CAD_SPEC = """# CAD Spec — 测试升降平台 (TST)

## 5. BOM

| 料号 | 名称 | 材质/型号 | 数量 | 自制/外购 | 单价 |
| --- | --- | --- | --- | --- | --- |
| TST-P01 | 丝杠 L350 | Tr16×4, 45#钢 | 2 | 自制 | — |
| TST-100 | 安装板 | 6061-T6 铝 100×80×8mm | 1 | 自制 | — |

## 6.4 零件包络尺寸

| 料号 | 包络尺寸 |
| --- | --- |
| TST-P01 | φ16×350 mm |
| TST-100 | 100×80×8 mm |
"""


def test_resolver_generates_standardized_custom_lead_screw(tmp_path):
    spec = tmp_path / "cad" / "demo" / "CAD_SPEC.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(CAD_SPEC, encoding="utf-8")

    generated, skipped, resolver, pending = generate_std_part_files(
        str(spec),
        str(spec.parent),
        mode="force",
    )

    generated_names = {Path(p).name for p in generated}
    assert "std_p01.py" in generated_names
    content = (spec.parent / "std_p01.py").read_text(encoding="utf-8")
    assert "make_trapezoidal_lead_screw" in content
    assert "Geometry source: PARAMETRIC_TEMPLATE" in content


def test_custom_generator_skips_resolver_routed_lead_screw_but_keeps_plate(tmp_path):
    spec = tmp_path / "cad" / "demo" / "CAD_SPEC.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(CAD_SPEC, encoding="utf-8")

    generated, skipped = generate_part_files(str(spec), str(spec.parent), mode="force")

    generated_names = {Path(p).name for p in generated}
    assert "p01.py" not in generated_names
    assert "p100.py" in generated_names


def test_build_tables_export_resolver_routed_custom_as_std_step(tmp_path):
    spec = tmp_path / "cad" / "demo" / "CAD_SPEC.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(CAD_SPEC, encoding="utf-8")

    parts = parse_bom_tree(str(spec))
    tables = generate_build_tables(parts, spec_path=str(spec))

    std_modules = {row["module"] for row in tables["std_step_builds"]}
    dxf_modules = {row["module"] for row in tables["dxf_builds"]}
    assert "std_p01" in std_modules
    assert "p01" not in dxf_modules
    assert "p100" in dxf_modules


def test_assembly_imports_resolver_routed_custom_from_std_module(tmp_path):
    spec = tmp_path / "cad" / "demo" / "CAD_SPEC.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(CAD_SPEC, encoding="utf-8")

    source = generate_assembly(str(spec))

    assert "from std_p01 import make_std_p01" in source
    assert "from p01 import make_p01" not in source
    assert "make_std_p01()" in source
```

- [ ] **Step 6: Verify end-to-end routing tests fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_custom_parts_resolver_routing.py -q
```

Expected: no `std_p01.py`, `gen_parts` still generates `p01.py`, `build_all.py` tables route `TST-P01` to DXF, and assembly imports `p01.py`.

- [ ] **Step 7: Add conservative default lead-screw mapping**

In `parts_library.default.yaml`, place before the generic `category: transmission` fallback:

```yaml
  - match:
      category: transmission
      keyword_contains: ["丝杠", "梯形丝杠", "lead screw", "leadscrew", "T16"]
    adapter: parametric_transmission
    spec:
      template: trapezoidal_lead_screw
      defaults:
        pitch_mm: null
        thread_length_mm: null
        lower_shaft_diameter_mm: null
        lower_shaft_length_mm: 0.0
        upper_shaft_diameter_mm: null
        upper_shaft_length_mm: 0.0
```

- [ ] **Step 8: Add project-specific `SLP-P01` mapping**

Because `cad/lifting_platform/CAD_SPEC.md` currently has an empty BOM material/model cell for `SLP-P01`, `Tr16×4` only appears elsewhere in the spec. Insert an exact `part_no` rule under the existing project `parts_library.yaml` `mappings:` list so the real lifting-platform sample routes deterministically before broader text extraction is added:

```yaml
- match:
    part_no: SLP-P01
  adapter: parametric_transmission
  spec:
    template: trapezoidal_lead_screw
    defaults:
      outer_diameter_mm: 16.0
      pitch_mm: 4.0
      total_length_mm: 350.0
      thread_length_mm: 230.0
      lower_shaft_diameter_mm: 12.0
      lower_shaft_length_mm: 70.0
      upper_shaft_diameter_mm: 12.0
      upper_shaft_length_mm: 40.0
```

- [ ] **Step 9: Let `gen_std_parts.py` include resolver-routed custom rows**

Import the shared helpers:

```python
from codegen.library_routing import build_library_part_query, is_library_routed_row
```

Update both prewarm and generation loops to build the query before deciding whether to continue:

```python
category = classify_part(p["name_cn"], p["material"])
env = envelopes.get(p["part_no"])
query = build_library_part_query(
    p,
    category=category,
    envelope=env,
    project_root=project_root,
)
is_library_row = is_library_routed_row(
    p,
    category=category,
    resolver=resolver,
    query=query,
)
if not is_library_row:
    continue
```

- [ ] **Step 10: Let `gen_parts.py` skip resolver-routed custom rows**

Construct one resolver before the part loop, not one resolver per part:

```python
from bom_parser import classify_part
from codegen.library_routing import build_library_part_query, is_library_routed_row
from parts_resolver import default_resolver

project_root = str(Path(spec_path).resolve().parent.parent.parent)
resolver = default_resolver(project_root=project_root)
```

In the custom loop after `envelope = envelopes.get(p["part_no"])`:

```python
category = classify_part(p["name_cn"], p.get("material", ""))
query = build_library_part_query(
    p,
    category=category,
    envelope=envelope,
    project_root=project_root,
)
if is_library_routed_row(
    p,
    category=category,
    resolver=resolver,
    query=query,
):
    skipped.append(out_file)
    continue
```

- [ ] **Step 11: Let `gen_build.py` use the same routing**

Change `generate_build_tables(parts: list)` to accept `spec_path: str | None = None` so it can parse §6.4 envelopes and build a resolver when called from `main()`.

```python
def generate_build_tables(parts: list, spec_path: str | None = None) -> dict:
    project_root = None
    resolver = None
    envelopes = {}
    if spec_path:
        from codegen.gen_assembly import parse_envelopes
        from parts_resolver import default_resolver

        envelopes = parse_envelopes(spec_path)
        project_root = str(Path(spec_path).resolve().parent.parent.parent)
        resolver = default_resolver(project_root=project_root)
```

Inside the row loop, before the existing `"自制"` branch:

```python
category = classify_part(name, p.get("material", ""))
if resolver is not None and project_root is not None:
    from codegen.library_routing import (
        build_library_part_query,
        is_library_routed_row,
        library_make_function,
        library_module_name,
    )

    query = build_library_part_query(
        p,
        category=category,
        envelope=envelopes.get(pno),
        project_root=project_root,
    )
    if is_library_routed_row(
        p,
        category=category,
        resolver=resolver,
        query=query,
    ) and "自制" in p.get("make_buy", ""):
        mod = library_module_name(pno)
        func = library_make_function(pno)
        std_step_builds.append({
            "label": f"[模型库] {re.sub(r'[（(].*$', '', name).strip()}",
            "module": mod,
            "func": func,
            "filename": f"{pno}_std.step",
        })
        continue
```

Update `main()`:

```python
tables = generate_build_tables(parts, spec_path=spec_path)
```

- [ ] **Step 12: Let `gen_assembly.py` import resolver-routed custom rows from `std_*`**

In `generate_assembly()`, build `project_root`, `resolver`, and envelopes once near the existing `children` processing setup:

```python
from codegen.library_routing import (
    build_library_part_query,
    is_library_routed_row,
    library_make_function,
    library_module_name,
)
from parts_resolver import default_resolver

project_root = str(Path(spec_path).resolve().parent.parent.parent)
resolver = default_resolver(project_root=project_root)
envelopes = parse_envelopes(spec_path)
```

Before the current standard/purchased branch at `make_buy = child.get("make_buy", "")`, compute:

```python
category = classify_part(child["name_cn"], child.get("material", ""))
query = build_library_part_query(
    child,
    category=category,
    envelope=envelopes.get(child["part_no"]),
    project_root=project_root,
)
library_routed = is_library_routed_row(
    child,
    category=category,
    resolver=resolver,
    query=query,
)
```

Then replace the top-level branch with:

```python
if "外购" in make_buy or "标准" in make_buy or library_routed:
    if category not in _STD_PART_CATEGORIES:
        continue
    std_mod = library_module_name(child["part_no"])
    std_func = library_make_function(child["part_no"])
    color_info = _STD_COLOR_MAP.get(category, ("C_STD_SENSOR", 0.2, 0.2, 0.2))
    # keep the existing placement loop and std_func_imports append unchanged
else:
    # keep the existing custom-made import path
```

- [ ] **Step 13: Verify routing tests pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_library_routing.py tests/test_custom_parts_resolver_routing.py tests/test_gen_assembly.py tests/test_gen_std_parts_preflight_integration.py -q
```

Expected: selected tests pass.

- [ ] **Step 14: Commit**

```powershell
git add codegen/library_routing.py codegen/gen_std_parts.py codegen/gen_parts.py codegen/gen_build.py codegen/gen_assembly.py parts_library.default.yaml parts_library.yaml tests/test_library_routing.py tests/test_custom_parts_resolver_routing.py
git commit -m "feat(codegen): 将标准化自制件纳入模型库路由"
```

## Task 5: Audit and Report Standardized Custom Geometry

**Files:**
- Modify: `codegen/gen_std_parts.py`
- Modify: `tools/model_audit.py`
- Create: `tests/test_lifting_platform_lead_screw_pipeline.py`

- [ ] **Step 1: Write failing vertical pipeline test**

Create `tests/test_lifting_platform_lead_screw_pipeline.py`:

```python
import json
from pathlib import Path

from codegen.gen_std_parts import generate_std_part_files


ROOT = Path(__file__).resolve().parent.parent
LIFTING_SPEC = ROOT / "cad" / "lifting_platform" / "CAD_SPEC.md"
LIFTING_DIR = ROOT / "cad" / "lifting_platform"


def test_lifting_platform_lead_screw_is_reported_as_parametric_template():
    generated, skipped, resolver, pending = generate_std_part_files(
        str(LIFTING_SPEC),
        str(LIFTING_DIR),
        mode="force",
    )

    std_p01 = LIFTING_DIR / "std_p01.py"
    assert std_p01.is_file()
    content = std_p01.read_text(encoding="utf-8")
    assert "make_trapezoidal_lead_screw" in content

    report = json.loads(
        (LIFTING_DIR / ".cad-spec-gen" / "geometry_report.json").read_text(encoding="utf-8")
    )
    p01 = next(row for row in report["decisions"] if row["part_no"] == "SLP-P01")
    assert p01["adapter"] == "parametric_transmission"
    assert p01["geometry_source"] == "PARAMETRIC_TEMPLATE"
    assert p01["geometry_quality"] == "B"
```

- [ ] **Step 2: Verify test fails before full report support**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_lifting_platform_lead_screw_pipeline.py -q
```

Expected: test fails until `SLP-P01` is routed and reported.

- [ ] **Step 3: Ensure geometry report includes standardized custom rows**

If Task 4 already records `SLP-P01`, no code change is needed. If `geometry_report.json` excludes custom rows, update the decision writer in `codegen/gen_std_parts.py` so every resolver-routed row is logged through `resolver.geometry_decisions()`.

- [ ] **Step 4: Update `model-audit` wording without changing status semantics**

Current `tools/model_audit.py` sets status from `requires_model_review` and missing STEP paths; do not replace that with a simple worst-quality rule. Add output wording/tests so B-grade parametric template rows are visible but remain pass when `requires_model_review=False` and no STEP path is missing:

```text
B = curated parametric template; visually and dimensionally useful, not vendor STEP.
```

- [ ] **Step 5: Verify audit tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_lifting_platform_lead_screw_pipeline.py tests/test_model_audit_cli.py tests/test_resolve_report.py -q
```

Expected: selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add codegen/gen_std_parts.py tools/model_audit.py tests/test_lifting_platform_lead_screw_pipeline.py
git commit -m "feat(audit): 报告参数化自制传动件质量"
```

## Task 6: Rebuild Lifting Platform and Verify V1 Lead Screw

**Files:**
- Generated/ignored: `cad/output/**`
- Possibly modified/generated tracked files:
  - `cad/lifting_platform/std_p01.py`
  - `cad/lifting_platform/build_all.py` or assembly imports only if generation changes tracked scaffold behavior

- [ ] **Step 1: Run focused codegen for lifting platform**

Run:

```powershell
.venv\Scripts\python.exe cad_pipeline.py codegen --subsystem lifting_platform --force
```

Expected:

- `cad/lifting_platform/std_p01.py` exists.
- `cad/lifting_platform/std_p01.py` imports `make_trapezoidal_lead_screw`.
- `cad/lifting_platform/p01.py` is no longer used by assembly for `SLP-P01`.

- [ ] **Step 2: Run build**

Run:

```powershell
.venv\Scripts\python.exe cad_pipeline.py build --subsystem lifting_platform
```

Expected:

- `cad/output/SLP-000_assembly.glb` generated.
- `assembly_validator.py` gate passes.
- No `FileNotFoundError` for `SLP-P01`.

- [ ] **Step 3: Render V1**

Run:

```powershell
.venv\Scripts\python.exe cad_pipeline.py render --subsystem lifting_platform --views V1
```

Expected:

- A new `V1_front_iso_*.png` appears under `cad/output/renders`.
- The central lead screw has visible helical thread cues before AI enhancement.

- [ ] **Step 4: Render full view set if V1 is good**

Run:

```powershell
.venv\Scripts\python.exe cad_pipeline.py render --subsystem lifting_platform
```

Expected:

- V1-V6 render without crashes.
- V4 orthographic projection issue remains a separate follow-up unless fixed by unrelated geometry changes.

- [ ] **Step 5: Enhance V1 after CAD-layer thread geometry is present**

Use the existing backend first:

```powershell
.venv\Scripts\python.exe cad_pipeline.py enhance --subsystem lifting_platform --backend engineering
```

Then optionally run `gpt-image-2-pro` as an experimental backend comparison against the new V1 source image.

- [ ] **Step 6: Verify tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_bom_classifier_threaded_parts.py tests/test_parametric_transmission.py tests/test_parametric_transmission_adapter.py tests/test_custom_parts_resolver_routing.py tests/test_lifting_platform_lead_screw_pipeline.py -q
.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected: focused tests and full suite pass; no whitespace errors.

- [ ] **Step 7: Commit final integration**

```powershell
git add cad/lifting_platform/std_p01.py cad/lifting_platform/build_all.py cad/lifting_platform/assembly.py
git commit -m "feat(lifting-platform): 使用参数化丝杠模型"
```

Only stage tracked generated/scaffold changes that are actually modified. Do not stage `cad/output/**`.

## Task 7: Photo-Grade Autopilot for Generic Products

This task productizes the broader goal: a user should be able to bring a different product, run one command, and get the best available photo-grade 3D output with explicit quality evidence instead of hand-tuning every part.

**Files:**
- Modify: `cad_pipeline.py`
- Modify: `prompt_data_builder.py`
- Modify: `pipeline_config.json`
- Create: `tools/photo3d_report.py`
- Create: `tests/test_photo3d_autopilot.py`

- [ ] **Step 1: Write failing photo3d report tests**

Create `tests/test_photo3d_autopilot.py`:

```python
from pathlib import Path


def test_photo3d_report_blocks_photo_mode_when_key_visible_parts_are_low_quality(tmp_path):
    from tools.photo3d_report import build_photo3d_report

    report = build_photo3d_report(
        subsystem="demo",
        geometry_report={
            "decisions": [
                {
                    "part_no": "P-001",
                    "name_cn": "丝杠",
                    "geometry_quality": "D",
                    "geometry_source": "JINJA_PRIMITIVE",
                    "requires_model_review": True,
                    "metadata": {"visual_priority": "hero"},
                }
            ]
        },
        render_manifest={"files": ["V1_front_iso.png"]},
        render_config={"materials": {"P-001": {"preset": "dark_steel"}}},
        enhanced_files=[],
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"] == [
        "hero part P-001 has geometry_quality=D"
    ]


def test_photo3d_report_allows_photo_mode_for_b_or_better_visible_parts(tmp_path):
    from tools.photo3d_report import build_photo3d_report

    report = build_photo3d_report(
        subsystem="demo",
        geometry_report={
            "decisions": [
                {
                    "part_no": "P-001",
                    "name_cn": "丝杠",
                    "geometry_quality": "B",
                    "geometry_source": "PARAMETRIC_TEMPLATE",
                    "requires_model_review": False,
                    "metadata": {"visual_priority": "hero"},
                }
            ]
        },
        render_manifest={"files": ["V1_front_iso.png"]},
        render_config={"materials": {"P-001": {"preset": "dark_steel"}}},
        enhanced_files=["V1_front_iso_enhanced.jpg"],
    )

    assert report["status"] == "pass"
    assert report["geometry_ready_count"] == 1
    assert report["enhanced_count"] == 1


def test_photo3d_backend_prefers_hard_geometry_lock_when_available(monkeypatch):
    from tools.photo3d_report import choose_photo3d_backend

    monkeypatch.setenv("FAL_KEY", "test")
    assert choose_photo3d_backend({"enhance": {"backend": "gemini"}}) == "fal_comfy"
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_photo3d_autopilot.py -q
```

Expected: import failure for `tools.photo3d_report`.

- [ ] **Step 3: Implement `tools/photo3d_report.py`**

```python
from __future__ import annotations

import os
from typing import Any


QUALITY_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "unknown": 0}


def _quality(value: Any) -> str:
    q = str(value or "unknown").upper()
    return q if q in QUALITY_ORDER else "unknown"


def _is_hero(decision: dict[str, Any]) -> bool:
    metadata = decision.get("metadata") or {}
    return metadata.get("visual_priority") in {"hero", "high"}


def choose_photo3d_backend(config: dict[str, Any]) -> str:
    if os.environ.get("FAL_KEY"):
        return "fal_comfy"
    enhance = config.get("enhance") or {}
    backend = enhance.get("backend") or "engineering"
    if backend in {"fal_comfy", "fal", "comfyui", "gemini", "engineering"}:
        return backend
    return "engineering"


def build_photo3d_report(
    *,
    subsystem: str,
    geometry_report: dict[str, Any],
    render_manifest: dict[str, Any],
    render_config: dict[str, Any],
    enhanced_files: list[str],
    backend: str | None = None,
) -> dict[str, Any]:
    decisions = [
        row for row in geometry_report.get("decisions", [])
        if isinstance(row, dict)
    ]
    blocking_reasons: list[str] = []
    geometry_ready_count = 0
    for row in decisions:
        quality = _quality(row.get("geometry_quality"))
        if QUALITY_ORDER[quality] >= QUALITY_ORDER["B"]:
            geometry_ready_count += 1
        if _is_hero(row) and QUALITY_ORDER[quality] < QUALITY_ORDER["B"]:
            blocking_reasons.append(
                f"hero part {row.get('part_no')} has geometry_quality={quality}"
            )
        if row.get("requires_model_review") is True and _is_hero(row):
            reason = f"hero part {row.get('part_no')} requires model review"
            if reason not in blocking_reasons:
                blocking_reasons.append(reason)

    render_files = list(render_manifest.get("files") or [])
    if not render_files:
        blocking_reasons.append("no render manifest files found")

    materials = render_config.get("materials") or {}
    if not materials:
        blocking_reasons.append("render_config has no materials")

    status = "blocked" if blocking_reasons else "pass"
    return {
        "schema_version": 1,
        "subsystem": subsystem,
        "status": status,
        "backend": backend,
        "blocking_reasons": blocking_reasons,
        "geometry_total": len(decisions),
        "geometry_ready_count": geometry_ready_count,
        "render_count": len(render_files),
        "enhanced_count": len(enhanced_files),
        "materials_count": len(materials),
    }
```

- [ ] **Step 4: Verify photo3d report tests pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_photo3d_autopilot.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Add `photo3d` command skeleton to `cad_pipeline.py`**

Add a command that performs the same phases a user expects from the full pipeline, but inserts photo-grade gates:

1. Run or require `codegen`, `build`, and `render`.
2. Read `geometry_report.json`; block photo mode when hero/high-visibility parts are below B quality.
3. Validate `render_config.json` material coverage.
4. Choose backend with `choose_photo3d_backend()`.
5. Run `enhance` with the selected backend.
6. Write `cad/<subsystem>/.cad-spec-gen/PHOTO3D_REPORT.json`.

Keep the first implementation conservative: it can call existing command functions and write the report; it does not need a new renderer.

- [ ] **Step 6: Enrich generic prompt data for non-SLP products**

Update `prompt_data_builder.py` so `standard_parts` and `material_descriptions` are derived from `render_config.json` plus geometry decisions when no hand-written prompt vars exist:

```python
standard_parts.append({
    "visual_cue": f"{row['part_no']} {row['name_cn']}",
    "real_part": f"{row['geometry_source']} / quality {row['geometry_quality']}",
})
```

Do not inject lifting-platform-specific text into other layouts.

- [ ] **Step 7: Add photo3d acceptance tests**

Extend `tests/test_photo3d_autopilot.py` with CLI-level tests for:

- `photo3d` writes `PHOTO3D_REPORT.json`.
- hard-lock backend is selected when `FAL_KEY` exists.
- report is `blocked` when hero geometry is D/E.
- report is `pass` when hero geometry is B/A and enhanced files exist.

- [ ] **Step 8: Verify photo3d tests and focused pipeline tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_photo3d_autopilot.py tests/test_model_audit_cli.py tests/test_render_config_autogen.py -q
```

Expected: selected tests pass.

- [ ] **Step 9: Commit**

```powershell
git add cad_pipeline.py prompt_data_builder.py pipeline_config.json tools/photo3d_report.py tests/test_photo3d_autopilot.py
git commit -m "feat(photo3d): 增加照片级出图自动质量门"
```

## Future Extension: External Libraries

After this plan lands, add external sources in this order:

1. `cq_warehouse_adapter`
   - Best fit for CadQuery-native thread/fastener/chain/sprocket parts.
   - Use when `cq_warehouse` is installed.
   - Fall back to `parametric_transmission` when unavailable.
2. SolidWorks generated threads
   - Use for users with SolidWorks when a real vendor STEP is unavailable.
   - Keep it opt-in because COM generation is slow and machine-specific.
3. Vendor/marketplace importers
   - TraceParts, MISUMI, McMaster-Carr, 3D ContentCentral, or user STEP pool.
   - Prefer explicit user approval and provenance capture.

## Execution Order

1. Task 1: classify lead screws correctly.
2. Task 2: build reusable CadQuery lead-screw geometry.
3. Task 3: expose the geometry through a resolver adapter.
4. Task 4: route standardized custom rows through resolver/codegen.
5. Task 5: report standardized custom geometry quality.
6. Task 6: regenerate lifting platform and verify V1 before AI enhancement.
7. Task 7: add generic photo-grade autopilot and quality reporting.

## Acceptance Criteria

- `SLP-P01` no longer relies on a one-off smooth-cylinder `p01.py` path.
- `SLP-P01` is generated through a generic resolver/template path.
- `cad/lifting_platform/.cad-spec-gen/geometry_report.json` includes `SLP-P01` with `adapter=parametric_transmission` and `geometry_quality=B` or better.
- A fresh V1 render shows visible thread geometry before Phase 5 enhancement.
- `photo3d` quality gate blocks D/E hero geometry and reports what the user must improve before AI enhancement.
- Photo-grade enhancement uses the best available geometry-lock backend and writes `PHOTO3D_REPORT.json`.
- Existing外购/标准件 behavior remains unchanged.
- Full pytest passes.

## Recorded Decisions and Remaining Review Questions

- Decision recorded for this plan: `SLP-P01` uses `geometry_quality=B` as a curated parametric template; `A` remains reserved for real/vendor/validated STEP sources.
- Decision recorded for this plan: the first implementation uses our own CadQuery visual-thread builder; optional `cq_warehouse` support is a later adapter.
- Decision recorded for this plan: resolver/library-routed custom rows reuse `std_*.py` modules; no new `lib_*` prefix in the first implementation.
- For performance, do we accept visual-thread ribs for render fidelity, or do we need swept trapezoidal thread profiles even if build time increases?
