# Parts Library System

**Added in:** v2.8.0  •  **v2.9.0 additions:** vendor STEP auto-synthesizer + `keyword_contains` matcher + `spec_envelope_granularity` enforcement
**Scope:** Phase 2 codegen + Phase 1 spec-gen envelope backfill

## Overview

The parts library system lets you replace the simplified primitive geometry
that `gen_std_parts.py` generates for purchased (外购) BOM parts with real
parametric or vendor-provided CAD geometry from three sources:

| Source | Adapter | Best for |
|--------|---------|----------|
| **bd_warehouse** — parametric hardware library (bearings, fasteners, threaded parts) | `BdWarehouseAdapter` | Standard ISO/DIN hardware |
| **Local STEP files** — vendor STEP downloads in `std_parts/` | `StepPoolAdapter` | Branded parts (Maxon motors, LEMO connectors, ATI sensors) |
| **PartCAD packages** — cross-project parametric package manager | `PartCADAdapter` | Organization-wide reusable parts |

All three sources are **optional**. Without a `parts_library.yaml` in the
project root, the pipeline behaves exactly like pre-v2.8.0 (byte-identical
output verified by regression test).

## v2.9.0: Shared-cache vendor synthesizer

As of v2.9.0, `parts_library.default.yaml` ships vendor STEP mappings that
point at the **shared cache** (`~/.cad-spec-gen/step_cache/` or
`$CAD_SPEC_GEN_STEP_CACHE`). On first use, `StepPoolAdapter` calls
`adapters/parts/vendor_synthesizer.py` to write a dimensionally-accurate
parametric stand-in for each vendor part into the cache, so a fresh project
with only a design document can route vendor BOM rows (Maxon GP22C, LEMO FGG,
ATI Nano17, …) to real geometry **without** a hand-crafted project-level
`parts_library.yaml`. To use real vendor STEP files instead, drop them at
`~/.cad-spec-gen/step_cache/<vendor>/<model>.step` — the adapter prefers an
existing file over the synthesizer, and project-local `std_parts/` is still
searched first.

Default mappings in v2.9.0 use the new `keyword_contains` matcher, which
searches BOTH the BOM `name_cn` column AND the `material` column. Vendor
model names commonly appear in either column (e.g. `name_cn="伺服电机"` +
`material="Maxon ECX SPEED 22L"` in one project, `name_cn="Maxon ECX"` in
another), so matching across both columns eliminates project-specific rule
duplication.

## v2.9.0: Granularity enforcement (`spec_envelope_granularity`)

`PartQuery` gained a `spec_envelope_granularity: str = "part_envelope"` field
that flows through the entire envelope chain (section walker → extractor →
`gen_assembly.parse_envelopes` → `PartQuery` → `JinjaPrimitiveAdapter`).
`JinjaPrimitiveAdapter._resolve_dims_from_spec_envelope_or_lookup` REJECTS
any envelope whose granularity is not `"part_envelope"` and falls through to
`lookup_std_part_dims` instead. This prevents station-level envelopes
(`station_constraint`, produced by the new section walker) from silently
sizing individual purchased parts as the full station bounding box — which
was the catastrophic bug the v2.9.0 walker spec's round-2 review identified.
End-to-end regression test at
`tests/test_walker_downstream_integration.py::test_station_constraint_not_used_as_part_size`.

## Architecture

```
parts_library.yaml (project-local, optional)
        │
        ▼
PartsResolver (parts_resolver.py)
        │   resolve(PartQuery) → ResolveResult
        │   probe_dims(PartQuery) → (w,d,h) | None
        ▼
Adapter ordered dispatch (first hit wins):
        ├─ StepPoolAdapter      (project std_parts/)
        ├─ BdWarehouseAdapter   (optional import)
        ├─ PartCADAdapter       (optional import, opt-in)
        └─ JinjaPrimitiveAdapter (terminal fallback — current _gen_* dispatch)
```

Two injection points:

1. **Phase 1 spec-gen** (`cad_spec_gen.py`) — `resolver.probe_dims()` fills
   the §6.4 envelope table with library-derived dimensions, tagged
   `P7:<ADAPTER>`.
2. **Phase 2 codegen** (`codegen/gen_std_parts.py`) — `resolver.resolve()`
   produces a `ResolveResult` that tells the code emitter how to build the
   `make_std_*()` function body.

## Quick start

### Step 1: Install optional dependencies

The base pipeline requires only `cadquery` + `jinja2`. Parts library
features require additional packages:

```bash
# Minimum: YAML parser for registry loading
pip install cad-spec-gen[parts_library]

# Optional: bd_warehouse parametric parts
pip install bd_warehouse

# Optional: PartCAD package manager
pip install partcad
```

> **Windows note:** On non-UTF-8 locales (zh-CN, ja-JP, ko-KR), either set
> `PYTHONUTF8=1` before running the pipeline, OR wait for upstream fix
> [gumyr/bd_warehouse#75](https://github.com/gumyr/bd_warehouse/pull/75) to
> be released.

### Step 2: Create a `parts_library.yaml` at your project root

The recommended pattern (since v2.8.1) is to inherit from the
skill-shipped default registry via `extends: default` and only list the
project-specific overrides. The default ships with category-driven rules
for bearings + fasteners → `bd_warehouse`, and a terminal fallback to
`jinja_primitive`.

```yaml
extends: default

step_pool:
  root: std_parts/
  cache: ~/.cad-spec-gen/step_cache/

mappings:
  # Project-specific overrides — these are PREPENDED to default mappings
  # and tried first (first-hit-wins).

  # Exact part_no override — point at a vendor STEP file
  - match: {part_no: "MYPROJ-001-05"}
    adapter: step_pool
    spec: {file: "maxon/ecx_22l_68mm.step"}

  # Anything not matched here flows into the default rules:
  #   bearing → bd_warehouse (specific class first, generic last)
  #   fastener → bd_warehouse (head-type first, hex/washer/nut last)
  #   everything else → jinja_primitive
```

If you do **not** use `extends: default`, your mappings completely
replace the default registry — including the terminal fallback. In that
case you must include your own `{any: true → jinja_primitive}` rule:

```yaml
# Legacy / pre-v2.8.1 style: complete replacement
version: 1
mappings:
  - match: {part_no: "MYPROJ-001-05"}
    adapter: step_pool
    spec: {file: "maxon/ecx_22l_68mm.step"}
  - match: {category: bearing, name_contains: ["608", "6200"]}
    adapter: bd_warehouse
    spec: {class: SingleRowDeepGrooveBallBearing}
  - match: {any: true}
    adapter: jinja_primitive
```

#### `extends: default` merge semantics

| What | How it merges |
|------|---------------|
| `mappings:` (list) | Project mappings are **prepended** to default mappings. Project rules win first-hit-wins; default rules act as a fallback for parts the project does not explicitly cover. |
| `step_pool`, `bd_warehouse`, `partcad`, `version` (top-level keys) | Project values **override** default values shallowly. |
| Unknown `extends:` value (e.g. `extends: foo`) | Logged as warning; project YAML is loaded standalone (no inheritance). |

The merge is intentionally NOT a deep merge. List-vs-dict semantics in
deep-merging YAML configs are a footgun; shallow override + mapping
prepend gives you what you actually want without surprises.

### Step 3: Drop STEP files into `std_parts/`

```
<project_root>/
├── parts_library.yaml
├── std_parts/
│   └── maxon/
│       └── ecx_22l_68mm.step
├── cad/
│   └── end_effector/
│       └── CAD_SPEC.md
```

### Step 4: Run the pipeline as usual

```bash
python cad_pipeline.py spec --subsystem end_effector --design-doc docs/04-*.md
python cad_pipeline.py codegen --subsystem end_effector
python cad_pipeline.py build --subsystem end_effector
```

The spec output will show P7 envelope backfills:

```
  §6.4 Envelopes: 17 parts
  §6.4 Backfilled: 5 envelopes from guess_geometry
  §6.4 P7 parts_library: filled 1, overrode 0
```

And `cad/end_effector/CAD_SPEC.md` §6.4 will contain:

```
| MYPROJ-001-05 | 伺服电机 | cylinder | Φ28×80 | P7:STEP |
```

The generated `std_myproj_001_05.py` will use `cq.importers.importStep()`
to load the real STEP file.

## Coverage report

Since v2.8.1, `gen_std_parts.py` prints a per-adapter coverage report at
the end of code generation, telling you exactly which parts went where:

```
[gen_std_parts] resolver coverage:
[gen_std_parts]   step_pool          1  GIS-EE-001-05
[gen_std_parts]   bd_warehouse       2  GIS-EE-002-11, GIS-EE-002-12
[gen_std_parts]   jinja_primitive   31  GIS-EE-001-03, GIS-EE-001-04 ... (and 28 more)
[gen_std_parts]   ─────────────────────────────────────────────────────────────────
[gen_std_parts]   Total: 34 parts | Library hits: 3 (8.8%) | Fallback: 31 (91.2%)
[gen_std_parts]
[gen_std_parts]   31 parts use simplified geometry. To upgrade them: add a STEP file
[gen_std_parts]   under std_parts/, write a parts_library.yaml rule, or set
[gen_std_parts]   `extends: default` to inherit category-driven routing.
```

The hint footer is suppressed when there are no `jinja_primitive`
fallbacks (i.e. every part has a real library backing). Library backends
are listed before `jinja_primitive` so the most informative rows are
visually prominent.

If you see most of your BOM in the `jinja_primitive` row and your YAML
already has `extends: default`, the explanation is usually one of:

1. **`bd_warehouse` does not cover that category.** It only ships ISO 15
   bearings + ISO 4014/4762 fasteners. Motors, sensors, connectors,
   pumps, seals, etc. are out of scope. Solution: drop a vendor STEP
   file under `std_parts/` and add a `step_pool` rule.
2. **The bearing/fastener size is not in `bd_warehouse`'s catalog.**
   Miniature bearings (e.g. MR105ZZ Φ5×Φ10×4) are a Japanese standard
   that ISO 15 does not include. Solution: same — drop a STEP file.
3. **`name_contains` keywords don't match.** Open
   `parts_library.default.yaml` and check the keyword lists; if your
   BOM uses different terminology, add a project-specific rule that
   prepends the right keywords.

## Mapping rule vocabulary

Each rule under `mappings:` has a `match:` block (conditions AND'd together)
and an `adapter:` + `spec:` target. Rules are evaluated top-to-bottom;
first match wins.

### `match:` conditions

| Key | Type | Semantics |
|-----|------|-----------|
| `any: true` | bool | Unconditional (use for the terminal fallback rule) |
| `part_no: "EXACT"` | str | Exact part_no equality |
| `part_no_glob: "PATTERN*"` | str | fnmatch-style glob |
| `category: "bearing"` | str | Match the `classify_part()` output |
| `name_contains: [...]` | list\|str | Any substring match in `name_cn`, case-insensitive |
| `material_contains: [...]` | list\|str | Any substring match in `material` column |
| `make_buy: "外购"` | str | Substring match in make_buy column |

### `adapter: jinja_primitive` spec

No spec fields. Uses `classify_part()` to dispatch to the appropriate
`_gen_<category>()` function from the legacy dispatch table. This is the
terminal fallback and produces the same output as pre-v2.8.0.

### `adapter: step_pool` spec

| Key | Type | Description |
|-----|------|-------------|
| `file: str` | required | STEP file path relative to `step_pool.root` |
| `file_template: str` | alternative | Template with `{part_no}`, `{name}`, `{normalize(name)}` placeholders |

Examples:

```yaml
# Exact file
- match: {part_no: "GIS-EE-001-05"}
  adapter: step_pool
  spec: {file: "maxon/ecx_22l.step"}

# Name-driven template
- match: {category: motor, name_contains: ["Maxon"]}
  adapter: step_pool
  spec: {file_template: "maxon/{normalize(name)}.step"}
```

Path resolution order:
1. `<project_root>/<step_pool.root>/<spec.file>` — project-local pool
2. `<step_pool.cache>/<spec.file>` — shared user cache (e.g.
   `~/.cad-spec-gen/step_cache/`)
3. Fall through to next rule on miss

### `adapter: bd_warehouse` spec

| Key | Type | Description |
|-----|------|-------------|
| `class: str` | required | bd_warehouse class name (e.g. `SingleRowDeepGrooveBallBearing`) |
| `size: str` | optional | Literal size string (e.g. `"M8-22-7"`) |
| `size_from: str` | optional | `"name"` or `"material"` — extract size from BOM field |
| `size_from: dict` | optional | `{regex: "X(\\d+)", template: "M{0}-6"}` — regex + format template |
| `extra_args: dict` | optional | Additional kwargs passed to the class constructor |

The catalog file `catalogs/bd_warehouse_catalog.yaml` maps the class name
to a static list of ISO designations (608, 6200, etc.) and size patterns.

Example:

```yaml
- match: {category: bearing, name_contains: ["MR105"]}
  adapter: bd_warehouse
  spec:
    class: SingleRowDeepGrooveBallBearing
    size: "M4-9-2.5"  # 618/4 is the closest ISO match for MR105
    extra_args:
      bearing_type: "SKT"
```

### `adapter: partcad` spec

Requires `partcad.enabled: true` at the top level.

| Key | Type | Description |
|-----|------|-------------|
| `part_ref: str` | required | PartCAD reference `"package:part_name"` |
| `params: dict` | optional | Parameters dict passed to `get_part_cadquery` |

Example:

```yaml
partcad:
  enabled: true
  config_path: ./partcad.yaml  # optional; partcad searches upward by default

mappings:
  - match: {part_no: "MYPROJ-001-06"}
    adapter: partcad
    spec:
      part_ref: "myorg_parts:gp22c_reducer"
      params: {gear_ratio: 53}
```

## Data consistency (§6.4 backfill)

Phase 1 calls `resolver.probe_dims()` for every purchased BOM row during
spec-gen. The returned dimensions are written into §6.4 with a `P7` source
tag, classified by which adapter produced them:

| Source tag | Origin |
|------------|--------|
| `P1:*` — `P4:*` | Author-provided (design doc) |
| `P5:chain_span` | Serial chain reconstruction |
| `P6:guess_geometry` | `gen_parts._guess_geometry()` heuristics |
| `P7:STEP` | step_pool real BBox |
| `P7:BW` | bd_warehouse catalog dims |
| `P7:PC` | PartCAD package BBox |
| `P7:STEP(override_P5)` etc. | P7 overriding a lower-confidence tier |

**Priority rules:**
- `P1..P4` (author-provided) — **never** overridden by P7
- `P5..P6` (auto-inferred) — **overridden** by P7 when any library adapter
  returns dims (library data is more authoritative than heuristics)
- No envelope — **filled** by P7 if any adapter hits

## Generated code forms

### `kind="codegen"` (jinja_primitive fallback)

Same as pre-v2.8.0:

```python
def make_std_ee_004_11() -> cq.Workplane:
    """GIS-EE-004-11: 微型轴承 — simplified bearing geometry."""
    # Simplified bearing: outer ring + inner ring + gap
    outer = cq.Workplane("XY").circle(5.0).circle(4.0).extrude(4)
    inner = cq.Workplane("XY").circle(2.6).circle(2.5).extrude(4)
    body = outer.union(inner)
    return body
```

### `kind="step_import"` (step_pool)

```python
def make_std_ee_001_05() -> cq.Workplane:
    """GIS-EE-001-05: 伺服电机 — imported from STEP file."""
    import os
    _here = os.path.dirname(os.path.abspath(__file__))
    _step_path = os.path.join(_here, "..", "..", "std_parts/maxon/ecx_22l_68mm.step")
    _step_path = os.path.normpath(_step_path)
    if not os.path.isfile(_step_path):
        raise FileNotFoundError(f"STEP file missing: {_step_path}")
    return cq.importers.importStep(_step_path)
```

### `kind="python_import"` (bd_warehouse)

```python
def _bd_to_cq(bd_part):
    """Convert a build123d Part to a CadQuery Workplane (self-contained)."""
    wrapped = getattr(bd_part, "wrapped", None)
    inner = getattr(wrapped, "wrapped", wrapped)
    return cq.Workplane("XY").newObject([cq.Solid(inner)])

def make_std_ee_004_11() -> cq.Workplane:
    """GIS-EE-004-11: 微型轴承 — bd_warehouse part."""
    from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing
    _bd_part = SingleRowDeepGrooveBallBearing(size='M4-9-2.5', bearing_type='SKT')
    return _bd_to_cq(_bd_part)
```

### `kind="python_import"` (partcad)

```python
def make_std_ee_001_06() -> cq.Workplane:
    """GIS-EE-001-06: 减速器 — partcad package part."""
    import partcad as pc
    _solid = pc.get_part_cadquery('myorg_parts:gp22c_reducer')
    return cq.Workplane("XY").newObject([_solid])
```

All four forms preserve the `make_*() → cq.Workplane` contract, so
`assembly.py` is oblivious to which adapter produced each part.

## Kill switches

### Disable the entire parts library system

```bash
# Per-invocation
CAD_PARTS_LIBRARY_DISABLE=1 python cad_pipeline.py spec ...

# Permanent: delete parts_library.yaml from the project root
rm parts_library.yaml
```

With the kill switch active, the resolver initializes with only the
`JinjaPrimitiveAdapter` and produces byte-identical output to pre-v2.8.0.

### Disable a single adapter

```yaml
bd_warehouse:
  enabled: false  # skip all bd_warehouse-targeted rules

partcad:
  enabled: false  # skip all partcad-targeted rules
```

Unhit rules fall through to the next matching rule, eventually reaching
the `{any: true}` fallback.

## Test strategy

### Unit tests (always run)

```bash
python -m pytest tests/test_parts_resolver.py tests/test_parts_adapters.py
```

Exercises:
- `_match_rule()` semantics (exact, glob, category, keyword, AND logic)
- `PartsResolver` dispatch (priority, fallback chain, exception handling)
- `JinjaPrimitiveAdapter` pins the pre-refactor `_gen_*` outputs
- `BdWarehouseAdapter` catalog-level checks (no bd_warehouse install needed)
- `StepPoolAdapter` with fixture STEP files generated by CadQuery
- `PartCADAdapter` opt-in gating and graceful degradation

### Optional live tests

```bash
# Requires: pip install bd_warehouse; set PYTHONUTF8=1 on Windows zh-CN
python -m pytest tests/test_parts_adapters.py::TestBdWarehouseLiveIntegration
```

### Byte-identical regression (the core safety net)

```bash
# Capture baseline before applying a parts_library.yaml
CAD_PARTS_LIBRARY_DISABLE=1 python cad_pipeline.py codegen --subsystem end_effector --force
# Compare against master — should be 0 diff
diff -r cad/end_effector/std_*.py <baseline>/
```

## Troubleshooting

### "WARNING: Could not load _guess_geometry"

This is the separate Phase 1 backfill helper (not the parts library). Fix
by ensuring `os` is imported in `cad_spec_gen.py` (fixed in v2.8.0).

### "STEP file not found"

The `step_pool.root` path is project-relative. Verify:

```bash
ls <project_root>/std_parts/<subpath>/
```

Absolute paths in `spec.file` work too but hurt project portability.

### Generated `make_*()` function raises `ModuleNotFoundError: No module named 'bd_warehouse'`

bd_warehouse is lazy-imported inside the function body, so spec-gen
machines don't need it. But the build machine does. Either:

```bash
pip install bd_warehouse
```

Or disable the bd_warehouse rules in `parts_library.yaml` (fallback to
jinja_primitive):

```yaml
bd_warehouse:
  enabled: false
```

### Assembly validator reports gaps after enabling parts library

The new envelopes are more accurate than the old heuristic guesses, which
means the assembly might shift slightly. Re-run the validator and inspect
the `F1_floating` report. Most shifts are < 1mm and within tolerance.

If a specific part's library dim conflicts with a tight design tolerance,
you can force it back to the author-provided P1..P4 value by editing §6.4
directly (P7 never overrides P1..P4).

## See also

- [`parts_library.default.yaml`](../parts_library.default.yaml) — shipped default registry
- [`catalogs/bd_warehouse_catalog.yaml`](../catalogs/bd_warehouse_catalog.yaml) — bd_warehouse class catalog
- [`parts_resolver.py`](../parts_resolver.py) — core resolver implementation
- [`adapters/parts/`](../adapters/parts/) — adapter implementations
- [gumyr/bd_warehouse](https://github.com/gumyr/bd_warehouse) — upstream bd_warehouse project
- [partcad/partcad](https://github.com/partcad/partcad) — upstream PartCAD project
