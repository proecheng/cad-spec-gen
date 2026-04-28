# Parts Library & Geometry Quality System

**Added in:** v2.8.0
**Current implemented baseline:** v2.21.2 parts library + geometry quality reports + model choice persistence
**Merged execution plan:** v0.4 — 2026-04-28
**Scope:** Phase 1 spec/review + Phase 2 codegen + SolidWorks optional assets + user model selection

## 文档定位

本文是模型库与几何质量改进的**唯一权威执行文档**。原 `docs/design/solidworks-integration-plan.md` 的 SolidWorks 材质、Toolbox、COM 导出、模型决策通道内容已并入本文；旧文件只保留迁移指针，避免继续维护两套方案。

本文同时记录两类内容：

- **已实现契约**：当前代码已经实现并可依赖的行为，例如 `parts_library.yaml`、`PartsResolver`、`StepPoolAdapter`、`BdWarehouseAdapter`、`SwToolboxAdapter`、`PartCADAdapter`、`JinjaPrimitiveAdapter`、P7 包络回填、coverage report、`GeometryDecision`、`geometry_report.json`、resolver `inspect/probe/export/codegen` 模式、结构化模型选择、用户 STEP 持久化闭环。
- **后续契约**：仍需补强但不阻塞现有管线的改进方向，例如统一 `ProjectContext`、更完整的 STEP import/bbox 校验、`MECH_TEMPLATE` 半参数模板、`sw_export_plan.json` 候选计划。

执行优先级：

1. **模型库增强优先**：真实 STEP / SW Toolbox STEP / bd_warehouse / PartCAD / 半参数模板优先，材质库只作为渲染增强。
2. **用户选择必须可执行**：用户指定 STEP 后必须落到 `std_parts/` + `parts_library.yaml`，或先进入待应用记录再显式编译为 registry；不能只写自由文本补充。
3. **报告必须来自同一次决策**：`geometry_report.json` 和 `resolve_report` 默认消费 codegen 真实决策日志，不能为生成报告再次调用有副作用的 `resolve()`；独立报告 API 只能用 `inspect` 兜底。
4. **只读阶段零副作用**：审查、预览、候选收集、报告诊断不得触发 SolidWorks COM 导出、vendor STEP 合成或缓存写入。Phase 1 `probe_dims()` 的 legacy vendor cache warmup 是当前兼容行为，后续应收敛到显式 `export` / warmup。
5. **路径必须统一**：项目根、子系统目录、缓存目录、报告目录由同一个 `ProjectContext` 解析，避免 `output/`、`cad/`、cwd、`artifacts/` 漂移。

## Overview

The parts library system lets you replace the simplified primitive geometry
that `gen_std_parts.py` generates for purchased (外购) BOM parts with real
parametric or vendor-provided CAD geometry from multiple sources:

| Source | Adapter / config key | Status | Best for |
|--------|----------------------|--------|----------|
| **Local STEP files** — vendor STEP downloads in `std_parts/` | adapter `step_pool`, `StepPoolAdapter`, config `step_pool` | implemented | Branded parts (Maxon motors, LEMO connectors, ATI sensors) |
| **Shared-cache vendor synthesizer** — generated STEP stand-ins under user cache | adapter `step_pool` with `spec.synthesizer` | implemented | Fresh projects without hand-downloaded vendor STEP |
| **bd_warehouse** — parametric hardware library | adapter `bd_warehouse`, `BdWarehouseAdapter` | implemented, optional dependency | Standard ISO/DIN bearings and fasteners |
| **SolidWorks Toolbox STEP** — locally exported Toolbox geometry | adapter `sw_toolbox`, class `SwToolboxAdapter`, config `solidworks_toolbox` | implemented; `inspect/probe` cache miss does not export | GB/ISO/DIN standard parts on Windows machines with SolidWorks |
| **PartCAD packages** — cross-project parametric package manager | adapter `partcad`, `PartCADAdapter`, config `partcad.enabled: true` | implemented, opt-in | Organization-wide reusable parts |
| **Mechanical templates** — semi-parametric recognizable geometry | planned `MECH_TEMPLATE` source | planned | Custom or purchased parts where no vendor model exists |
| **Jinja primitive fallback** — legacy generated geometry | adapter `jinja_primitive`, `JinjaPrimitiveAdapter` | implemented terminal fallback | Last resort visualization only |

All enhanced sources are **optional**. The terminal fallback remains
`JinjaPrimitiveAdapter`, so the pipeline can still produce visualization
geometry even without local STEP files, optional libraries, or SolidWorks.

Status note: `SwToolboxAdapter` may export via COM only in production modes (`export` / `codegen`) after routing has chosen a Toolbox part. Read-only modes (`inspect` / `probe`) skip COM export on cache miss, so review and envelope probing stay side-effect-free.

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
        │   resolve(PartQuery, mode=inspect|probe|export|codegen) → ResolveResult
        │   probe_dims(PartQuery) → (w,d,h) | None
        │   geometry_decisions() → list[dict]
        ▼
YAML mapping dispatch (first matching mapping wins):
        ├─ step_pool        → StepPoolAdapter
        ├─ bd_warehouse     → BdWarehouseAdapter
        ├─ sw_toolbox       → SwToolboxAdapter
        ├─ partcad          → PartCADAdapter
        └─ jinja_primitive  → JinjaPrimitiveAdapter
```

Two injection points:

1. **Phase 1 spec-gen** (`cad_spec_gen.py`) — `resolver.probe_dims()` fills
   the §6.4 envelope table with library-derived dimensions, tagged
   `P7:<ADAPTER>`.
2. **Phase 2 codegen** (`codegen/gen_std_parts.py`) — `resolver.resolve()`
   produces a `ResolveResult` that tells the code emitter how to build the
   `make_std_*()` function body.

Important consistency rule: adapter registration order in `default_resolver()`
is not the routing priority. Routing priority comes from the effective
`mappings:` list after `extends: default` is merged. Project mappings are
prepended, then default mappings run as fallback.

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

# Optional: SolidWorks Toolbox COM automation on Windows
pip install pywin32
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
| `step_pool`, `bd_warehouse`, `solidworks_toolbox`, `partcad`, `version` (top-level keys) | Project values **override** default values shallowly. |
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
visually prominent. When SolidWorks Toolbox handles rows, the adapter row is
reported as `sw_toolbox`.

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
| `keyword_contains: [...]` | list\|str | Any substring match in either `name_cn` or `material`; preferred for vendor model names that may appear in either column |
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

When both `file` and `file_template` are present, `file` is authoritative.
Use this when a user has selected an exact STEP file and you want to keep a
template fallback in the same rule for later cleanup.

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

Path safety:

- Relative `file` / `file_template` results are normalized before lookup and
  must stay inside `step_pool.root` or `step_pool.cache`.
- `../`, drive-relative paths such as `C:foo.step`, and absolute
  `file_template` results are rejected as `miss` with an unsafe-path warning.
- Absolute `file` paths are still accepted for compatibility, but project-
  relative paths remain the portable form.

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

### `adapter: sw_toolbox` spec

Requires a Windows machine with SolidWorks, usable Toolbox data, `pywin32`,
and a healthy COM conversion session. Top-level config lives under
`solidworks_toolbox:`; mapping rules use adapter key `sw_toolbox`.

| Key | Type | Description |
|-----|------|-------------|
| `standard: str\|list[str]` | required | Toolbox standard to search, e.g. `GB`, `ISO`, `DIN`, or `[GB, ISO, DIN]` |
| `subcategories: list[str]` | required | Toolbox folders to search, e.g. `["bolts and studs", "nuts", "screws"]` |
| `part_category: str` | recommended | Expected normalized part category, e.g. `fastener`, `bearing`, `seal`, `locating` |

Example:

```yaml
solidworks_toolbox:
  enabled: auto
  standards: [GB, ISO, DIN]
  min_score: 0.30

mappings:
  - match: {category: fastener, make_buy: "标准"}
    adapter: sw_toolbox
    spec:
      standard: GB
      subcategories: ["bolts and studs", "nuts", "screws", "washers and rings"]
      part_category: fastener
```

Mode behavior: `SwToolboxAdapter.resolve(..., mode="inspect"|"probe")`
does not export STEP via COM on cache miss. Only `mode="export"` and
`mode="codegen"` may trigger conversion after routing has selected a Toolbox
part.

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
| `P7:sw_toolbox` | SolidWorks Toolbox cached STEP bbox |
| `P7:PC` | PartCAD package BBox |
| `P7:STEP(override_P5)` etc. | P7 overriding a lower-confidence tier |

**Priority rules:**
- `P1..P4` (author-provided) — **never** overridden by P7
- `P5..P6` (auto-inferred) — **overridden** by P7 when any library adapter
  returns dims (library data is more authoritative than heuristics)
- No envelope — **filled** by P7 if any adapter hits

## Implemented contract: geometry decisions

This section is the merged contract for model-library routing, geometry
quality reporting, and user model selection. It replaces the old split
between this document and `docs/design/solidworks-integration-plan.md`.

### Review findings closed in the current baseline

The v2.21.2 baseline closes the main integration gaps found during review:

| Code point | Current baseline |
|---|---|
| `cad_spec_gen.py::_flatten_review_items()` | Preserves `geometry` review groups, `group_action`, `parts`, `candidates`, quality fields, path metadata, hashes, and review flags in `DESIGN_REVIEW.json`. |
| `cad_pipeline.py::_save_supplements()` | Extracts structured model choices, writes `model_choices.json`, copies selected STEP files into `std_parts/user_provided/`, and prepends `parts_library.yaml` mappings. |
| `parts_resolver.py::ResolveResult` | Carries geometry source, A-E quality, validation state, hash, path kind, warnings, and `requires_model_review`. |
| `parts_resolver.py::resolve_report()` | Builds from decision logs by default; the standalone fallback uses read-only `inspect` mode only. |
| `codegen/gen_std_parts.py` | Writes `cad/<subsystem>/.cad-spec-gen/geometry_report.json` from the same decisions used to emit `std_*.py`. |
| `adapters/parts/sw_toolbox_adapter.py::resolve()` | `inspect` / `probe` cache misses return a miss with warnings and do not start COM export; `export` / `codegen` may export when explicitly selected. |

### GeometryDecision

`GeometryDecision` is the single record for one BOM row's geometry choice.
It is generated from the actual `ResolveResult` used by codegen.

```python
@dataclass
class GeometryDecision:
    part_no: str
    name_cn: str
    make_buy: str
    category: str

    adapter: str                    # step_pool / sw_toolbox / bd_warehouse / partcad / jinja_primitive
    result_kind: str                # codegen / step_import / python_import / miss
    geometry_source: str            # REAL_STEP / SW_TOOLBOX_STEP / BD_WAREHOUSE / PARTCAD / MECH_TEMPLATE / LLM_CADQUERY / JINJA_PRIMITIVE / MISSING
    geometry_quality: str           # A / B / C / D / E

    path: str | None = None
    path_kind: str = "none"         # project_relative / shared_cache / absolute / none
    validated: bool = False
    bbox: tuple[float, float, float] | None = None
    hash: str | None = None

    source_tag: str = ""
    user_choice: bool = False
    requires_model_review: bool = False
    suggested_user_action: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

Quality levels:

| Level | Sources | User meaning |
|---|---|---|
| A | `REAL_STEP`, `SW_TOOLBOX_STEP` | Real or official standard geometry; best for visual fidelity and assembly placeholder accuracy |
| B | `BD_WAREHOUSE`, `PARTCAD` | Parametric library geometry; size is credible, appearance detail depends on the library |
| C | `MECH_TEMPLATE` | Recognizable semi-parametric shape; better than an envelope, not a vendor model |
| D | `JINJA_PRIMITIVE`, unvalidated `LLM_CADQUERY` | Simplified stand-in for rough visualization |
| E | `MISSING` | No usable geometry |

`ResolveResult` keeps all existing fields and appends optional fields:

```python
geometry_source: str = ""
geometry_quality: str = ""
path_kind: str = ""
validated: bool = False
hash: str | None = None
requires_model_review: bool = False
```

Backwards compatibility rule: old call sites keep reading `kind`, `adapter`,
`step_path`, `source_tag`, and `metadata`; reports use
`ResolveResult.to_geometry_decision(query)`.

`GeometryCandidate` is read-only candidate data shown to users before a
choice is applied:

```python
@dataclass
class GeometryCandidate:
    candidate_id: str
    part_no: str
    label: str
    adapter: str                    # step_pool / sw_toolbox / bd_warehouse / partcad / mech_template
    geometry_source: str
    geometry_quality: str
    path: str | None = None
    path_kind: str = "none"
    bbox: tuple[float, float, float] | None = None
    confidence: float = 0.0
    requires_export: bool = False
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

Candidate IDs are stable within one run but are not long-term facts. A user
selection becomes durable only after it is written to `parts_library.yaml`.

### Files and facts

| File | Location | Role | Authority |
|---|---|---|---|
| `parts_library.yaml` | `<project_root>/parts_library.yaml` | User-confirmed long-term mappings | authoritative |
| `std_parts/` | `<project_root>/std_parts/` | Project-portable STEP model pool | authoritative |
| `model_choices.json` | `cad/<subsystem>/.cad-spec-gen/model_choices.json` | Interaction audit and pending choices | not authoritative unless applied to registry |
| `geometry_report.json` | `cad/<subsystem>/.cad-spec-gen/geometry_report.json` | Actual codegen geometry quality report | report authority |
| `sw_export_plan.json` | `cad/<subsystem>/.cad-spec-gen/sw_export_plan.json` | Read-only SolidWorks export candidates | not authoritative |
| `sw_config_pending.json` | current code writes project-local `.cad-spec-gen/sw_config_pending.json` | Existing pending Toolbox configuration decisions | pending state |
| `resolve_report.json` | current code writes `artifacts/{run_id}/resolve_report.json` | Adapter routing trace | debug/report only |

Rules:

1. User-provided STEP files are copied into `std_parts/` by default and then referenced through project-relative `step_pool` mappings.
2. `parts_library.yaml` uses `extends: default`; new user mappings are prepended ahead of default rules.
3. `model_choices.json` does not directly drive the resolver. It records what happened during interaction until a choice is applied to `parts_library.yaml`.
4. Long-lived mappings must not rely on absolute paths unless the user explicitly accepts poor portability.
5. `step_pool.spec.file` is relative to `step_pool.root`; after copying to `std_parts/custom/foo.step`, write `custom/foo.step`, not `std_parts/custom/foo.step`.
6. `geometry_report.json` records what codegen actually used. It must not list candidates as if they were applied models.

### ProjectContext (planned cleanup)

Path logic should be centralized in a later cleanup pass:

```python
@dataclass
class ProjectContext:
    project_root: Path
    subsystem: str
    subsystem_dir: Path              # cad/<subsystem>
    hidden_dir: Path                 # cad/<subsystem>/.cad-spec-gen
    std_parts_dir: Path              # <project_root>/std_parts
    parts_library_path: Path         # <project_root>/parts_library.yaml
    artifacts_dir: Path | None
```

`ProjectContext` will replace scattered uses of `os.getcwd()`,
`spec_path.parent.parent.parent`, `output/<subsystem>`, and ad hoc
`artifacts/{run_id}` path construction.

### Resolver modes

Implemented mode split:

| Mode | Allowed actions | Forbidden actions | Purpose |
|---|---|---|---|
| `inspect` | Match rules, list candidates, read lightweight indexes | COM export, STEP synthesis, cache writes | Show options before user interaction |
| `probe` | Read existing STEP bbox and catalog dimensions through `resolve(..., mode="probe")` | Generate new STEP, write files | Read-only dimension check |
| `export` | SolidWorks COM export, vendor synthesizer cache write | Generate `std_*.py` | Explicit model preparation / warmup |
| `codegen` | Resolve real geometry and generate code; may export only under explicit policy | Report-time re-resolution | Phase 2 production generation |

Current API:

```python
class PartsResolver:
    def resolve(self, query: PartQuery, mode: ResolveMode = "codegen") -> ResolveResult: ...
    def geometry_decisions(self) -> list[dict]: ...
    # Future: def inspect_candidates(self, query: PartQuery) -> list[GeometryCandidate]: ...
```

Report API:

```python
def resolve_report(..., allow_inspect_fallback: bool = True) -> ResolveReport:
    """Serialize existing decisions; inspect fallback is read-only."""
```

### User interaction

When the design document is incomplete or written in non-professional terms,
the skill should ask about consequences and choices, not adapter internals.

First show a summary:

```text
我发现 12 个外购/标准件缺少高质量模型：
- 3 个建议补真实 STEP（电机、减速器、传感器）
- 5 个可由 SolidWorks Toolbox 导出
- 4 个可以先用简化占位

你希望怎么处理？
1. 自动查找可用模型，找不到的先用占位（推荐）
2. 我逐个指定 STEP 文件
3. 全部先用简化占位
4. 暂时跳过这些零件
```

Then ask only about high-impact parts:

```text
减速电机 GIS-EE-001-05 当前只有简化外形。
可选：
1. 使用项目模型库中的 maxon/ecx_22l.step（推荐，质量 A）
2. 我指定一个 STEP 文件
3. 先使用可辨识占位模型（质量 D）
4. 暂时不生成该零件
```

High-impact score:

```text
impact_score =
  volume_rank * 0.30
  + assembly_visibility * 0.25
  + fallback_penalty * 0.25
  + repeat_count * 0.10
  + category_priority * 0.10
```

Initial category priority:

| Category | Priority |
|---|---|
| motor / gearbox / sensor / connector / actuator | high |
| bearing / fastener / locating / seal | medium |
| cable / wire / label | low or intentional skip |

When the user provides a STEP file, the implemented baseline does this:

1. Validate `part_no`, path existence, and `.step` / `.stp` extension.
2. Compute SHA256 for provenance.
3. Copy into `std_parts/user_provided/<safe_name>.step`.
4. Update `parts_library.yaml` atomically with a prepended `step_pool` mapping whose `spec.file` is relative to `step_pool.root`.
5. Record choices and application results in `model_choices.json`.

Still planned: import the STEP with CadQuery to verify geometry readability,
record bbox/unit checks, and mark large §6.4 envelope mismatches as
`requires_model_review=true`.

### SolidWorks integration

SolidWorks is an optional source for local assets. It must never be required
for a project to run.

| Component | Current/planned path | Role |
|---|---|---|
| `sw_detect.py` | `adapters/solidworks/sw_detect.py` | Detect Windows, SW version, install paths, Toolbox path, COM, and `pywin32` |
| `sw_material_bridge.py` | `adapters/solidworks/sw_material_bridge.py` | Parse local `.sldmat` into material props / render presets |
| `sw_texture_backfill.py` / texture resolver | `adapters/solidworks/` | Resolve local appearance textures where available |
| `sw_toolbox_catalog.py` | `adapters/solidworks/sw_toolbox_catalog.py` | Build/read Toolbox catalog index and match BOM tokens |
| `sw_com_session.py` / workers | `adapters/solidworks/` | Guard SolidWorks COM conversion and avoid long hangs |
| `SwToolboxAdapter` | `adapters/parts/sw_toolbox_adapter.py` | Route standard parts to cached/exported Toolbox STEP |

SolidWorks compliance rules:

| Action | Policy |
|---|---|
| Read local `.sldmat` / appearance metadata | Allowed at runtime on the user's licensed machine |
| Copy textures or exported STEP into local cache | Allowed for local use; do not commit generated SW assets |
| Automate SLDPRT to STEP conversion | Allowed only as user-local runtime operation |
| Bundle Dassault `.sldmat`, `.sldprt`, textures, or extracted data in git | Forbidden |

SolidWorks degradation:

| Scenario | Behavior |
|---|---|
| Non-Windows platform | SW sources unavailable; resolver falls through |
| SolidWorks missing | No SW candidates as executable options; show advisory only |
| SolidWorks version too old | Materials may be best effort; Toolbox COM disabled |
| `pywin32` missing | Toolbox export unavailable; material-only code may still work |
| COM failure or circuit breaker trip | Current part falls through to next adapter |
| Ambiguous Toolbox configuration | Write pending state; do not export a guessed configuration |

### Pipeline integration baseline

Phase 1 `spec/review`:

- Supports a `geometry` review category.
- `_flatten_review_items()` preserves `group_action`, `parts`,
  `candidates`, `current_quality`, `recommended_quality`, and
  `suggested_user_action`.
- Old agents may ignore unknown fields; new agents use them for model
  selection.

Example:

```json
{
  "id": "G1",
  "category": "geometry",
  "severity": "WARNING",
  "check": "外购件缺少高质量模型",
  "group_action": true,
  "parts": [
    {
      "part_no": "GIS-EE-001-05",
      "name_cn": "减速电机",
      "current_quality": "D",
      "recommended_quality": "A",
      "candidates": []
    }
  ]
}
```

Phase 2 `codegen`:

1. Construct all `PartQuery` rows from BOM.
2. Prewarm candidates with `mode="inspect"` only when a UI/report needs them.
3. Resolve each row with `mode="codegen"`.
4. Convert each real result into `GeometryDecision`.
5. Generate `std_*.py`.
6. Write `cad/<subsystem>/.cad-spec-gen/geometry_report.json`.
7. Build `resolve_report` from the same decision log; standalone report calls
   may use read-only `inspect` fallback for compatibility.

Phase 3 `build/render`:

- Generated module docstrings include geometry source, quality, validation,
  and STEP hash when available.
- Build errors surface missing path / invalid model details before generic
  `FileNotFoundError`.

### Implementation status

| Stage | Status | Main changes | Acceptance |
|---|---|---|---|
| M0 | planned | Add `ProjectContext`; document schemas | New files land in stable project/subsystem locations |
| M1 | implemented | Extend `ResolveResult`; add `GeometryDecision` | Adapter hits produce A-E quality |
| M2 | implemented | Add `inspect/probe/export/codegen` | `inspect` writes nothing and does not start COM export |
| M3 | implemented | Build reports from decision log; add `geometry_report.json` | Codegen reports do not call production `resolve()` again |
| M4 | implemented, import validation pending | Validate path/ext, copy, hash, atomically update YAML | A user-provided STEP is imported on next codegen |
| M5 | implemented | Preserve candidates and group actions | Agent can ask batch model questions |
| M6 | planned | `sw_export_plan.json` candidate list; explicit export only | Review stage never triggers export |
| M7 | partial | Migration/user docs are maintained here; generated docstring enrichment remains future | Users can see source/quality in reports today |

### Test coverage

| Test | Status | Coverage |
|---|---|---|
| `test_design_review_geometry_schema.py` | implemented | `DESIGN_REVIEW.json` preserves geometry groups and candidates |
| `test_model_choices_persistence.py` | implemented | User choices write `model_choices.json` and can be applied to `parts_library.yaml` |
| `test_parts_resolver.py` | implemented | Resolver modes and geometry quality defaults |
| `test_resolve_report.py` | implemented | Report consumes decision log; inspect fallback is read-only |
| `test_parts_library_writer_roundtrip.py` | planned | `extends: default` survives; new mappings prepend without corrupting YAML structure |
| `test_step_user_provided_validation.py` | planned | STEP import bbox, unit sanity, and copy into `std_parts/` |
| `test_codegen_docstring_geometry_quality.py` | planned | Generated modules include source/quality/validated metadata |
| `test_project_context_paths.py` | planned | `.cad-spec-gen`, `std_parts/`, and `parts_library.yaml` paths are stable |

### Edge cases

| Edge case | Handling |
|---|---|
| User gives an absolute STEP path | Copy to `std_parts/` by default; direct absolute mapping only by explicit opt-in |
| STEP file is corrupted or cannot import | Do not write `parts_library.yaml`; record failure in `model_choices.json` |
| STEP bbox differs greatly from §6.4 envelope | Mark `requires_model_review=true`; ask user to confirm units or model |
| SolidWorks not installed | Hide SW export as an executable option; show advisory only |
| SolidWorks configuration ambiguous | Write `sw_config_pending.json` / `sw_export_plan.json`; do not export guessed config |
| Multiple models have same display name | Show bbox, path, and short hash; persist selected candidate |
| `parts_library.yaml` missing | Create minimal `extends: default` + `mappings:` file before adding user mapping |
| Existing hand-written mappings | Prepend user mapping; do not reorder or delete old mappings |
| Large BOM | Ask only high-impact questions; record batch policy and unresolved items in report |

### Success criteria

1. When the user says “these parts use this real STEP,” the next `codegen`
   actually imports those STEP files.
2. `geometry_report.json` shows A/B/C/D/E counts, current source, remaining
   simplified placeholders, and upgrade suggestions.
3. Machines without SolidWorks still run the full pipeline.
4. Review/report/preview stages never start SolidWorks or write STEP caches.
5. Model-library improvements cover motors, reducers, sensors, connectors,
   actuators, seals, locating parts, and other high-impact purchased geometry,
   not just material appearance.

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

solidworks_toolbox:
  enabled: false  # skip all sw_toolbox-targeted rules
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
- [`adapters/parts/sw_toolbox_adapter.py`](../adapters/parts/sw_toolbox_adapter.py) — SolidWorks Toolbox adapter (`sw_toolbox`)
- [`adapters/solidworks/`](../adapters/solidworks/) — SolidWorks detection, catalog, material, and COM helpers
- [`sw_preflight/`](../sw_preflight/) — current preflight, dry-run, report, and early user-provided STEP flow
- [gumyr/bd_warehouse](https://github.com/gumyr/bd_warehouse) — upstream bd_warehouse project
- [partcad/partcad](https://github.com/partcad/partcad) — upstream PartCAD project
