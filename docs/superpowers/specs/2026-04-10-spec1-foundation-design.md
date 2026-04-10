# Spec 1 — Foundation: FOV Fix, Template Authority, Routing Module, Packaging

**Date**: 2026-04-10
**Status**: Ready for implementation planning
**Companion**: [Spec 2 — Asset Library](./2026-04-10-asset-library-and-pipeline-enhancements-design.md) (deferred)
**Scope**: Minimal foundation that ships user value quickly AND prepares the ground for Spec 2's larger asset library vision. Has zero network surface, zero arbitrary-code-execution surface beyond what already exists, and zero breaking visual changes.

---

## 1. Relationship to Spec 2

This spec is Phase 1 of a two-phase delivery. It deliberately **excludes** (all deferred to Spec 2):

- PBR texture downloads and the asset manifest
- `cad-lib install` / `add` / `import` commands — anything network-facing
- Template auto-routing from BOM to templates (full version)
- Review dimension E (asset library readiness)
- Chinese keyword table expansion and GB alias tables
- Material preset three-tier merging (user `materials.yaml`, project overrides)
- Community templates or remote manifests
- `~/.cad-spec-gen/textures/` and `~/.cad-spec-gen/models/` directories

**Why the split**: Two rounds of multi-perspective review surfaced 50+ issues, including a security audit rating the original unified spec at **2/10** due to the plugin-system / auto-download / no-signing / checksum-as-theater combination. Spec 1 avoids all of that by containing zero network-facing or trust-boundary-crossing features. Spec 2 cannot be finalized until:

1. Spec 1 ships successfully
2. A `§16 Security Model` is drafted and security-reviewed for Spec 2
3. Chinese keyword table is expanded against real BOM data
4. 3D designer's PBR physics corrections are validated
5. Release-engineering story (feature flags, migration guide, CHANGELOG) is finalized for Spec 2

Spec 1 ships **immediate user value** (FOV fix, 5 templates, existing-subsystem migration) while **unblocking Spec 2 architecturally** (extracting the routing module, establishing `render_3d.py` canonical source, fixing packaging, establishing schema versioning).

## 2. Goals

- **G1 — Fix auto-frame for wide models** without changing visual framing of existing correctly-framed models
- **G2 — Ship 5 realistic parametric templates** generic to any mechanical subsystem: `iso_9409_flange` (retrofit with module contract), `l_bracket`, `rectangular_housing`, `cylindrical_housing`, `fixture_plate`
- **G3 — Establish skill-level canonical source for `render_3d.py`** (currently only exists as drifted project copies)
- **G4 — Extract `parts_routing.py` pure function module** — prepares Spec 2 Phase R by giving gen_parts and the future reviewer a single shared decision path (prevents the architect's "aspirational invariant" concern)
- **G5 — Fix packaging gap** — `hatch_build.py` currently does not ship `tools/`, `catalogs/`, `parts_library.default.yaml`, or `render_3d.py` to pip users. Build + smoke-test in CI.
- **G6 — Local-only `cad-lib` CLI scaffold**: `init | list | doctor | which | validate template` — NO install, NO download, NO import commands
- **G7 — Schema versioning foundation** — all new YAML files ship with `schema_version: 1`; `cad-lib migrate` is a stub command that errors on unknown versions
- **G8 — Migration command `cad-lib migrate-subsystem <dir>`** — copies the new canonical `render_3d.py` into existing `cad/<subsystem>/` deployments (with `.bak` backup) so existing projects actually receive the FOV fix
- **G9 — Feature flag infrastructure** — reserve env var names so Spec 2 features can ship behind off-by-default gates
- **G10 — Generality** — every template docstring, example, and test fixture uses neutral industrial vocabulary; zero references to `end_effector`, `lifting_platform`, `GISBOT`, or any specific subsystem name
- **G11 — No intermediate-product changes** — only skill-level files are modified; `cad/<subsystem>/` contents are only touched by the explicit, user-invoked `cad-lib migrate-subsystem` command

## 3. Non-Goals

Everything listed under §1 as "deferred to Spec 2". Plus:

- Changing `frame_fill` default from 0.75 (3D designer flagged global 0.75→0.82 as a visual regression vector; the new FOV formula alone is the fix, the default compensation is dropped)
- Retrofitting the `cad-lib` CLI verb surface for future install/add/import commands — those are designed in Spec 2 as a unified `cad-lib add {kind} <name>` pattern and should not be front-run by inconsistent v1 verbs
- Any change to `cad_spec_reviewer.py` — Phase R (review dimension E) is entirely a Spec 2 feature
- Auto-discovery across multiple tiers — Spec 1 only scans `templates/parts/` (Tier 1) and project-local `templates/parts/` (Tier 3 override). No Tier 2 `~/.cad-spec-gen/templates/`.

## 4. Architecture (Spec 1 scope)

### 4.1 Two-Tier Discovery (Spec 1 minimum)

```
Tier 1 — Built-in (ships with skill)
    <skill>/templates/parts/*.py               5 base templates + dynamic __init__.py

Tier 3 — Project local (override, highest priority)
    <project>/templates/parts/*.py             Project-specific templates (if any)
```

Spec 2 adds Tier 2 (`~/.cad-spec-gen/templates/`). Spec 1's `parts_routing.py` accepts a `search_paths: list[Path]` parameter so the Tier 2 path can slot in later without interface change.

### 4.2 File Layout — Canonical Sources After Spec 1

| File | Canonical location | Notes |
|------|-------------------|-------|
| `render_config.py` | repo root + `src/cad_spec_gen/data/python_tools/render_config.py` | existing |
| `render_depth_only.py` | repo root | existing, no mirror |
| `render_3d.py` | `src/cad_spec_gen/render_3d.py` | **NEW canonical** — promoted from `cad/end_effector/render_3d.py`; flat layout per §4.3 |
| `codegen/gen_parts.py` | repo root (hand-edited) + `src/cad_spec_gen/data/codegen/gen_parts.py` (build-generated mirror, do NOT edit by hand) | existing |
| `parts_routing.py` | `src/cad_spec_gen/parts_routing.py` | **NEW** — pure functions; flat layout per §4.3 |
| `cad_lib.py` | `src/cad_spec_gen/cad_lib.py` | **NEW** — local-only CLI; flat layout per §4.3 |
| `templates/parts/*.py` | repo root | existing (iso_9409_flange) + 4 new; shipped to `src/cad_spec_gen/data/templates/parts/` via `hatch_build.py` COPY_DIRS (existing behavior) |
| `parts_library.default.yaml` | repo root | existing |
| `catalogs/library_manifest.yaml` | **deferred to Spec 2** | not created in Spec 1 |

### 4.3 Decision: Authoritative Locations Going Forward

The existing repo has no uniform mirror policy (some files have `src/` mirrors, some don't), AND `src/cad_spec_gen/data/` is **not a Python package** (no `__init__.py` files) — it's a file-payload tree populated by `hatch_build.py` for the wheel. This blocks the naive approach of putting new Python modules under `src/cad_spec_gen/data/python_tools/` with expectation of `from cad_spec_gen.data.python_tools.X import Y` working, because the import will fail.

**Decision — Option A (flat `src/cad_spec_gen/` layout for new Python modules)**:

- **New Python modules** (`parts_routing.py`, `render_3d.py`, `cad_lib.py`) go directly under `src/cad_spec_gen/` — at the same level as the existing `src/cad_spec_gen/cli.py` and `src/cad_spec_gen/wizard/` subpackage. These ARE real Python modules and can be imported as `from cad_spec_gen.parts_routing import ...`, matching existing convention.

- **Data files** (`templates/parts/*.py` currently at repo root) continue to be treated as data — not as importable Python subpackages. They're shipped via `hatch_build.py` COPY_DIRS to `src/cad_spec_gen/data/templates/parts/` at build time. Discovery uses filesystem iteration + AST parsing (invariant #4), not `importlib.import_module`. See §6.3 for the template discovery helper (`locate_builtin_templates_dir`).

- **Files with an existing `src/cad_spec_gen/data/python_tools/` mirror** (`render_config.py` only, in Spec 1 scope) → keep both in sync via existing `hatch_build.py:PYTHON_TOOLS` copy list. No change to their location.

- **Repo-root-only files** (`render_depth_only.py`, `codegen/gen_parts.py`) → remain authoritative at repo root; only `codegen/gen_parts.py` gets mirrored via `hatch_build.py` COPY_DIRS automatically. The `src/cad_spec_gen/data/codegen/gen_parts.py` mirror is build-generated, never hand-edited.

**Why not move everything to `src/cad_spec_gen/data/python_tools/`?** Because that path is not an importable Python package. Creating the missing `__init__.py` files and updating hatch_build.py to preserve them during payload assembly is fragile (every build has to reconcile hand-written init files with a copy-based build hook). The flat layout under `src/cad_spec_gen/` avoids this problem entirely and matches the existing `cli.py` + `wizard/` convention.

This decision is documented here so future contributors don't re-debate it.

## 5. Phase 1 — Auto-Frame FOV Fix

### 5.1 Problem Statement

`cad/end_effector/render_3d.py:586` (and its lifting_platform clone + `render_depth_only.py:146`) computes only the vertical FOV half-angle:

```python
fov_half = math.atan(sensor_h / (2.0 * cam_data.lens))
required_dist = bs_radius / math.sin(fov_half) / frame_fill
```

For a 1920×1080 landscape render, vertical FOV is narrower than horizontal. Wide models (e.g., a 300×60×40 mm rail assembly) fit the bounding sphere vertically but end up either loosely framed or unnecessarily distant.

### 5.2 Fix

Use the **minimum** of vertical and horizontal half-angles (= the tighter constraint):

```python
fov_v = math.atan(sensor_h / (2.0 * cam_data.lens))
fov_h = math.atan(sensor_w / (2.0 * cam_data.lens))
fov_half = min(fov_v, fov_h)
required_dist = bs_radius / math.sin(fov_half) / frame_fill
```

### 5.3 `frame_fill` Default: UNCHANGED at 0.75

**Important**: The original spec proposed compensating the default from 0.75 → 0.82 to preserve existing framing on square-ish models. The 3D designer review flagged this as a silent global visual regression:

> "Parts that previously had clean negative space around them will now crop into the safe margins; isometric hero shots will suddenly have the bounding sphere kissing the frame edge. Existing goldens break silently."

**Decision**: Keep `frame_fill = 0.75`. The new `min(fov_v, fov_h)` formula is the correct fix and should stand on its own. Wide models will reframe honestly (slightly tighter than before, which is what users asked for); square-ish models are unaffected because `fov_v ≈ fov_h` when the bounding sphere approaches the render aspect ratio.

### 5.4 File Operations — Phase 1

**Step 1 — Promote `render_3d.py` to skill-level canonical source**:
Copy `cad/end_effector/render_3d.py` verbatim to `src/cad_spec_gen/render_3d.py`. The end_effector copy is chosen because it has the `bom_id` priority-matching logic that `lifting_platform/render_3d.py` lacks — it's the more feature-complete baseline.

**Step 2 — Apply the FOV fix**:
Modify only the new canonical file (`src/cad_spec_gen/render_3d.py`). Find the pattern:
```python
fov_half = math.atan(sensor_h / (2.0 * cam_data.lens))
required_dist = bs_radius / math.sin(fov_half) / frame_fill
```
Replace with:
```python
fov_v = math.atan(sensor_h / (2.0 * cam_data.lens))
fov_h = math.atan(sensor_w / (2.0 * cam_data.lens))
fov_half = min(fov_v, fov_h)  # Spec 1 fix: use tighter-axis FOV for wide models
required_dist = bs_radius / math.sin(fov_half) / frame_fill
```
Line numbers are intentionally not cited — the existing `cad/end_effector/render_3d.py` has uncommitted changes (see `git status`) that may shift them by implementation time. Anchor on the text pattern.

**Step 3 — Same fix in `render_depth_only.py`**:
Modify `render_depth_only.py` (repo root, no mirror) with the identical formula swap — same before/after text pattern as Step 2. `frame_fill` default stays 0.75 (the existing `config.get("frame_fill", 0.75)` call stays as-is).

**Step 4 — Docstring update in `render_config.py`**:
Add a one-paragraph explanation that auto-frame now uses `min(fov_v, fov_h)` — update both the repo root and `src/cad_spec_gen/data/python_tools/` mirror.

**Step 5 — Do NOT modify `cad/end_effector/render_3d.py` or `cad/lifting_platform/render_3d.py`**:
Propagation to deployed subsystems is Phase 5 (`cad-lib migrate-subsystem`), not Phase 1.

### 5.5 Acceptance

- Unit test: given `(sensor_w=36, sensor_h=20.25, lens=65)` and `bs_radius=150`, new formula returns `required_dist` within 1% of `150 / sin(atan(36/130)) / 0.75`
- Visual test: render a 300×60×40 mm wide model at 1920×1080 with preset V1; bounding sphere horizontal extent fits within the frame (silhouette bounding box area ≥ 85% of frame area × 0.75²)
- Visual test: render a 100×100×100 cube at 1920×1080 with preset V1; silhouette area within 5% of the pre-change baseline
- `render_depth_only.py` depth pass renders the same model at the same framing as `render_3d.py` (no ControlNet drift)

## 6. Phase 2 — Base Templates (5 templates, Tier 1)

### 6.1 Templates to Ship

Each template follows the `iso_9409_flange.py` design philosophy (functional realism, 300-400 LOC, cosmetic ops wrapped in try/except, pure CadQuery, self-contained, no cross-template deps). All templates use **generic industrial terminology** — no references to end_effector, lifting_platform, or any specific subsystem.

#### 6.1.1 `iso_9409_flange.py` (existing — retrofit only)
Add module-level constants required by Phase 3 (§6.2 contract) without changing geometry. No breaking changes. Also update docstring example from "GISBOT four-station end effector" to "generic robot tool interface" for G10 compliance.

#### 6.1.2 `l_bracket.py` (NEW)
Base plate + vertical wall with inner bend fillet, mounting holes on both faces, optional stiffener gusset, edge chamfers.

Parameters: `w, d, h, t, bend_fillet, gusset, gusset_width, gusset_chamfer, base_bolt_dia, base_bolt_count_x, base_bolt_count_y, base_bolt_margin, wall_bolt_dia, wall_bolt_count_x, wall_bolt_count_y, wall_bolt_margin, counterbore_dia, counterbore_depth, edge_chamfer`

#### 6.1.3 `rectangular_housing.py` (NEW)
Hollow rectangular enclosure with lid flange, corner fillets, optional cable gland boss, internal PCB standoffs.

Parameters: `w, d, h, wall_t, corner_fillet, lid_flange_w, lid_flange_h, lid_bolt_dia, lid_bolt_count, lid_bolt_margin, standoff_count, standoff_dia, standoff_h, standoff_tap_dia, cable_gland_face, cable_gland_dia, cable_gland_boss_thickness, draft_angle_deg, edge_chamfer`

#### 6.1.4 `cylindrical_housing.py` (NEW)
Hollow cylindrical enclosure with configurable end caps, axial through-bore, mounting flange, internal ledge.

Parameters: `outer_dia, h, wall_t, end_cap, end_cap_thickness, end_cap_bolt_dia, end_cap_bolt_count, bore_dia, bore_chamfer, flange_dia, flange_t, flange_bolt_dia, flange_bolt_count, flange_bolt_pcd, ledge_dia, ledge_depth, register_type, register_dim, edge_chamfer`

#### 6.1.5 `fixture_plate.py` (NEW — added per end-user review feedback)

**Why this template**: The end-user review flagged that the 4 original templates were end-effector-biased and offered nothing to users doing fixtures, jigs, tooling, or locating plates. A `fixture_plate` is the single most common part in a huge swath of mechanical work — flat plate with a regular hole grid, optional dowel pins, optional counterbores.

Geometry pipeline:
1. Base plate (w × d × t) with optional corner fillets
2. Regular hole grid (N×M pattern or freeform list) with optional counterbores
3. Optional dowel pin holes (precision fits, distinguishable from bolt holes)
4. Optional slots (elongated holes, oriented X or Y)
5. Edge chamfers on all rims

Parameters: `w, d, t, corner_fillet, hole_grid_nx, hole_grid_ny, hole_spacing_x, hole_spacing_y, hole_margin, hole_dia, counterbore_dia, counterbore_depth, dowel_pin_positions, dowel_pin_dia, slot_positions, slot_w, slot_l, edge_chamfer`

Where `hole_grid_nx=0 or hole_grid_ny=0` disables the regular grid (for freeform hole plates).

### 6.2 Module-Level Contract

Every template module (including the `iso_9409_flange` retrofit) exposes:

```python
# Module-level constants (read by parts_routing.py)
MATCH_KEYWORDS: list[str] = ["keyword1", "keyword2", ...]   # English only in Spec 1
MATCH_PRIORITY: int = 10                                     # higher wins; default 10
TEMPLATE_CATEGORY: str = "bracket"                           # bracket | housing | plate | mechanical_interface
TEMPLATE_VERSION: str = "1.0"

def make(**params) -> cq.Workplane: ...                      # existing contract
def example_params() -> dict: ...                            # NEW — returns a complete valid parameter dict
```

**`MATCH_KEYWORDS` scope in Spec 1**:
- English terminology only (`l_bracket`, `enclosure`, `cylindrical housing`, `fixture_plate`, `mounting plate`, `robot flange`)
- Chinese keyword support is **deferred to Spec 2** where the Chinese engineering expert review's 40-entry expansion + traditional character normalization + regex infix support will be properly designed
- This avoids shipping a half-baked Chinese keyword table that Spec 2 would need to overhaul

**`example_params()` contract**: calling `make(**example_params())` must return a valid non-empty solid. This is verified by Spec 1's test suite and used by Spec 2's `cad-lib create template --from <base>` for scaffolding.

### 6.2.1 Worked Example: `iso_9409_flange` Retrofit

The existing template gets these constants added at the top of the module (after imports, before the `make()` definition). Geometry and signature are untouched.

```python
# templates/parts/iso_9409_flange.py

MATCH_KEYWORDS: list[str] = [
    "iso_9409_flange",
    "iso 9409 flange",
    "robot tool flange",
    "robot flange",
    "tool mount flange",
    "cross-arm hub",       # cross-arm overlay mode
    "mounting flange",     # common English fallback
]
MATCH_PRIORITY: int = 20   # high priority — this is a specialized template
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    """Canonical parameter set for this template. Calling
    make(**example_params()) must return a valid non-empty solid."""
    return {
        "outer_dia": 90.0,
        "thickness": 25.0,
        "outer_fillet": 2.0,
        "central_bore_dia": 32.0,
        "central_bore_chamfer": 1.5,
        "iso_pcd": 50.0,
        "iso_bolt_dia": 6.0,
        "iso_bolt_count": 4,
        "iso_counterbore_dia": 10.0,
        "iso_counterbore_depth": 6.0,
        "iso_start_angle_deg": 45.0,
        # Cross-arm hub (disc_arms mode) — 4 arms, disabled by default here
        "arm_count": 0,
        "arm_length": 0.0,
        "arm_width": 12.0,
        # Tool-side bolts disabled
        "tool_bolt_count": 0,
    }
```

### 6.2.2 Worked Examples for the 4 New Templates

Each new template declares its constants at the top of its module. Values below are the spec's authoritative source — implementers copy these verbatim:

```python
# templates/parts/l_bracket.py
MATCH_KEYWORDS = ["l_bracket", "l bracket", "angle bracket", "corner bracket", "angle iron"]
MATCH_PRIORITY = 15
TEMPLATE_CATEGORY = "bracket"
TEMPLATE_VERSION = "1.0"
# example_params() returns: w=60, d=40, h=50, t=4, bend_fillet=3,
#   gusset=True, gusset_width=15, base_bolt_dia=5, base_bolt_count_x=2,
#   base_bolt_count_y=1, wall_bolt_dia=5, wall_bolt_count_x=2, wall_bolt_count_y=1,
#   base_bolt_margin=8, wall_bolt_margin=8, edge_chamfer=0.5, counterbore_dia=0
```

```python
# templates/parts/rectangular_housing.py
MATCH_KEYWORDS = ["rectangular housing", "enclosure", "box housing", "rectangular enclosure"]
MATCH_PRIORITY = 15
TEMPLATE_CATEGORY = "housing"
TEMPLATE_VERSION = "1.0"
# example_params() returns: w=120, d=80, h=40, wall_t=2.5, corner_fillet=3,
#   lid_flange_w=6, lid_flange_h=2, lid_bolt_dia=3, lid_bolt_count=4,
#   lid_bolt_margin=5, standoff_count=4, standoff_dia=5, standoff_h=8,
#   standoff_tap_dia=2.5, cable_gland_face="side", cable_gland_dia=8,
#   cable_gland_boss_thickness=3, draft_angle_deg=0.5, edge_chamfer=0.5
```

```python
# templates/parts/cylindrical_housing.py
MATCH_KEYWORDS = ["cylindrical housing", "cylinder enclosure", "tube housing", "cylindrical shell"]
MATCH_PRIORITY = 15
TEMPLATE_CATEGORY = "housing"
TEMPLATE_VERSION = "1.0"
# example_params() returns: outer_dia=60, h=100, wall_t=3, end_cap="flat",
#   end_cap_thickness=4, end_cap_bolt_dia=3, end_cap_bolt_count=6,
#   bore_dia=0, bore_chamfer=0, flange_dia=80, flange_t=5,
#   flange_bolt_dia=4, flange_bolt_count=4, flange_bolt_pcd=70,
#   ledge_dia=0, ledge_depth=0, register_type="none", register_dim=0, edge_chamfer=0.5
```

```python
# templates/parts/fixture_plate.py
MATCH_KEYWORDS = ["fixture plate", "mounting plate", "base plate", "hole grid plate",
                  "locating plate", "tooling plate"]
MATCH_PRIORITY = 15
TEMPLATE_CATEGORY = "plate"
TEMPLATE_VERSION = "1.0"
# example_params() returns: w=200, d=150, t=10, corner_fillet=4,
#   hole_grid_nx=4, hole_grid_ny=3, hole_spacing_x=40, hole_spacing_y=40,
#   hole_margin=20, hole_dia=6, counterbore_dia=10, counterbore_depth=5,
#   dowel_pin_positions=[], dowel_pin_dia=5, slot_positions=[], slot_w=0, slot_l=0,
#   edge_chamfer=0.5
```

**`dowel_pin_positions` and `slot_positions` format**: each is a list of `(x, y)` float tuples in plate-local coordinates (origin at plate center). Empty list = feature disabled. Slot entries also require `slot_w` (width across) and `slot_l` (length along the X axis; rotate by including the rotated equivalent coordinates). This is documented in `fixture_plate.py`'s docstring and verified by its `make()` parameter handling.

### 6.2.3 Category Allowlist

`TEMPLATE_CATEGORY` must be one of: `bracket | housing | plate | mechanical_interface | fastener_family`. This allowlist is enforced by `parts_routing.discover_templates` — templates with unknown categories are skipped with a WARNING log. Future categories are added by extending this constant in both the spec and `parts_routing.py`.

### 6.3 Dynamic Template Discovery

Templates live at repo-root `templates/parts/` and ship inside the wheel at `<site-packages>/cad_spec_gen/data/templates/parts/` via `hatch_build.py`. In neither location are they a real Python subpackage (no `__init__.py` promoting them to `cad_spec_gen.templates.parts`). Discovery therefore uses **filesystem iteration**, not `importlib.import_module` + `pkgutil.iter_modules`.

The helper lives in `parts_routing.py` (Phase 3) so both `gen_parts.py` and future Spec 2 consumers share it:

```python
# src/cad_spec_gen/parts_routing.py

from pathlib import Path

def locate_builtin_templates_dir() -> Path | None:
    """Find the builtin templates/parts directory in both pip-install and
    repo-checkout modes. Returns None if neither location exists.

    Resolution order:
      1. Pip-installed: <cad_spec_gen package>/data/templates/parts/
      2. Repo-checkout: <repo_root>/templates/parts/
    """
    # Option 1: pip-installed — templates shipped as package data
    try:
        import importlib.resources as ir
        pkg_data = ir.files("cad_spec_gen") / "data" / "templates" / "parts"
        if pkg_data.is_dir():
            return Path(str(pkg_data))
    except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError):
        pass

    # Option 2: repo-checkout — templates at repo root
    # This file lives at src/cad_spec_gen/parts_routing.py
    # → repo root = parents[2]
    repo_root = Path(__file__).resolve().parents[2]
    repo_templates = repo_root / "templates" / "parts"
    if repo_templates.is_dir():
        return repo_templates

    return None


def discover_templates(search_paths: list[Path]) -> list[TemplateDescriptor]:
    """Scan search_paths for template .py files. Extracts MATCH_KEYWORDS /
    MATCH_PRIORITY / TEMPLATE_CATEGORY / TEMPLATE_VERSION via AST parse — never
    imports or executes template code. Malformed templates are logged and skipped."""
    import ast
    descriptors = []
    for search_dir in search_paths:
        if not search_dir or not search_dir.is_dir():
            continue
        for py_file in sorted(search_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError) as exc:
                log.warning("Skipping malformed template %s: %s", py_file, exc)
                continue
            desc = _extract_descriptor_from_ast(tree, name=py_file.stem, source_path=py_file)
            if desc is not None:
                descriptors.append(desc)
    return descriptors
```

**`templates/parts/__init__.py` is simplified** to a thin docstring file that no longer hardcodes template imports — it exists only to allow `templates/parts/` to be discoverable as a directory when the repo is on sys.path. Example replacement:

```python
"""cad-spec-gen parts template library — data directory.

Templates in this directory are discovered at runtime via filesystem
iteration by `cad_spec_gen.parts_routing.discover_templates`. They are
NOT imported as Python modules here.

Each template file must define: make(**params) -> cq.Workplane,
MATCH_KEYWORDS, MATCH_PRIORITY, TEMPLATE_CATEGORY, TEMPLATE_VERSION,
example_params() -> dict.

See templates/parts/iso_9409_flange.py for the canonical example.
"""
```

**Why AST-based discovery instead of `importlib`?** Four reasons:
1. **Security posture for Spec 2**: when Spec 2 adds `~/.cad-spec-gen/shared/templates/`, user/community templates must not execute at discovery time. AST parse is safe; `importlib.import_module` is not.
2. **Works without a Python subpackage**: no `__init__.py` required at `templates/parts/` in the wheel; no fight with hatch_build.py's file-payload model.
3. **Frozen install compatible**: `importlib.resources.files()` works with wheel-installed packages AND editable installs; no zipapp-specific fallback needed.
4. **Fast**: AST parse of ~400-line template files is ~1ms each; the whole discovery pass is negligible compared to CadQuery model building.

### 6.4 Files Modified / Added — Phase 2

**Added**:
- `templates/parts/l_bracket.py`
- `templates/parts/rectangular_housing.py`
- `templates/parts/cylindrical_housing.py`
- `templates/parts/fixture_plate.py`

**Modified**:
- `templates/parts/__init__.py` — dynamic discovery
- `templates/parts/iso_9409_flange.py` — add `MATCH_KEYWORDS`, `MATCH_PRIORITY`, `TEMPLATE_CATEGORY`, `TEMPLATE_VERSION`, `example_params()` (non-breaking); generic docstring

## 7. Phase 3 — `parts_routing.py` Pure Function Module

### 7.1 Why This Matters

The first round of architect review flagged that Spec 2's invariant "E dimension and resolver share the same simulation path" is aspirational unless structurally enforced. The fix is to extract the matching logic into a pure module that both `gen_parts.py` and Spec 2's `cad_spec_reviewer.py` will import.

**Doing this in Spec 1** — before Spec 2's full auto-routing lands — means Spec 2's Phase R can consume a stable, tested interface rather than racing against a moving target. Without this extraction, Spec 2 has to refactor `gen_parts.py` under time pressure, which is a known failure mode.

### 7.2 Module Interface

```python
# src/cad_spec_gen/parts_routing.py

from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class GeomInfo:
    """Frozen snapshot of _guess_geometry output — no dict ambiguity."""
    type: str                         # "box" | "cylinder" | "disc_arms" | "l_bracket" | ...
    envelope_w: float
    envelope_d: float
    envelope_h: float
    extras: dict[str, Any]            # type-specific fields (arm_count, etc.)

@dataclass(frozen=True)
class TemplateDescriptor:
    """What parts_routing knows about a template, without importing it."""
    name: str                         # module name
    keywords: tuple[str, ...]         # from MATCH_KEYWORDS
    priority: int                     # from MATCH_PRIORITY
    category: str                     # from TEMPLATE_CATEGORY
    tier: str                         # "builtin" | "project"

@dataclass(frozen=True)
class RouteDecision:
    """Result of a routing decision — consumed by emitter OR reviewer."""
    outcome: str                      # "HIT_BUILTIN" | "HIT_PROJECT" | "FALLBACK" | "AMBIGUOUS"
    template: TemplateDescriptor | None
    ambiguous_candidates: tuple[TemplateDescriptor, ...] = ()
    reason: str = ""                  # human-readable explanation


def discover_templates(search_paths: list[Path]) -> list[TemplateDescriptor]:
    """Scan search_paths for template modules matching the contract.
    Pure function — no side effects except reading .py files."""

def route(
    name: str,
    geom_info: GeomInfo,
    templates: list[TemplateDescriptor],
    yaml_rules: list[dict] | None = None,
) -> RouteDecision:
    """Given a part name + geometry + available templates, return a routing decision.
    Pure function — no side effects. Used by gen_parts.py AND future reviewer."""
```

### 7.2.1 `route()` Error and Edge Cases

| Input condition | `RouteDecision.outcome` | `.template` | `.reason` |
|----------------|------------------------|-------------|-----------|
| `templates == []` (empty library) | `"FALLBACK"` | `None` | `"no templates available"` |
| `name == ""` or `name is None` | `"FALLBACK"` | `None` | `"empty part name"` |
| `geom_info.type` not in `{box, cylinder, disc_arms, ring, l_bracket, plate}` (unknown) | `"FALLBACK"` | `None` | `f"unknown geom type: {geom_info.type}"` |
| `geom_info.type == "disc_arms"` with NO template of category `"mechanical_interface"` | `"FALLBACK"` | `None` | `"disc_arms requires mechanical_interface template"` |
| `geom_info.type == "disc_arms"` WITH `iso_9409_flange` (or other cross-arm-capable template) in library | `"HIT_BUILTIN"` | `iso_9409_flange descriptor` | `"disc_arms → cross-arm hub template"` |
| Exactly one template matches keyword + geom_type | `"HIT_BUILTIN"` or `"HIT_PROJECT"` | matched template | keyword that matched |
| Two templates match with identical `MATCH_PRIORITY` and no `geom_type` discriminator | `"AMBIGUOUS"` | `None` (see `ambiguous_candidates`) | `"multiple templates match keyword '<kw>'; add geom_type rule or raise priority"` |
| Two templates match, one has higher `MATCH_PRIORITY` | higher-priority template wins as `HIT_*` | higher-priority | — |
| Tier 3 and Tier 1 templates have the same module name | Tier 3 wins as `HIT_PROJECT` | Tier 3 descriptor | `"project override (tier 3 shadows tier 1)"` |
| YAML rule in `yaml_rules` explicitly routes to a template that isn't in `templates` (missing template) | `"FALLBACK"` | `None` | `f"YAML rule specified template '{name}' but it is not installed"` |
| `geom_info.envelope_w <= 0` or other degenerate envelope | `"FALLBACK"` | `None` | `"degenerate geometry: envelope has zero or negative dimension"` |

All error cases are **pure data** — no exceptions raised, no logging from inside `route()`. Callers decide how to surface each outcome.

The `disc_arms` cases are important because `_guess_geometry()` in `codegen/gen_parts.py` currently returns `type="disc_arms"` for parts like "十字法兰" (see `gen_parts.py` around line 78). `parts_routing.py` must recognize this type and dispatch it to `iso_9409_flange` when available, otherwise Spec 1's dormant integration would log spurious "FALLBACK" for parts that DO have a matching template.

### 7.3 Properties of this Module

- **No side effects**: no `importlib.import_module`, no file writes, no downloads, no prints. Just data in, data out.
- **No Python importing of templates**: `discover_templates` reads module files as text via AST to extract `MATCH_KEYWORDS` / `MATCH_PRIORITY` / `TEMPLATE_CATEGORY` without executing module-level code. This also contributes to Spec 2's security posture — auditing `~/.cad-spec-gen/templates/` for descriptors won't trigger RCE.
- **Stable data shapes**: all types are frozen dataclasses, not dicts. The architect review's concern about "leaky dict-key interfaces" is addressed structurally.
- **Deterministic**: given identical inputs, always produces identical `RouteDecision`. No hash-iteration order dependency.

### 7.4 `gen_parts.py` Integration in Spec 1

`gen_parts.py` currently uses `_guess_geometry()` + inline Jinja2 branching. Spec 1 **does not** change the Jinja2 fallback behavior — Phase 4 of Spec 2 will add the full routing path. Spec 1's scope is limited to:

1. **Only `codegen/gen_parts.py` at repo root is hand-edited.** The `src/cad_spec_gen/data/codegen/gen_parts.py` "mirror" is written by `hatch_build.py` at build time — do not touch it by hand, it regenerates from the repo-root file.

2. `codegen/gen_parts.py` adds at the top (after the existing `sys.path.insert` block for repo root):
   ```python
   # Make the new cad_spec_gen package importable in repo-checkout mode.
   # hatch_build.py publishes it as an installed package for wheel users;
   # repo-checkout users need src/ on sys.path.
   _SRC = Path(__file__).parent.parent / "src"
   if str(_SRC) not in sys.path:
       sys.path.insert(0, str(_SRC))

   from cad_spec_gen.parts_routing import route, discover_templates, GeomInfo, locate_builtin_templates_dir
   ```

3. Constructs `GeomInfo` from `_guess_geometry()`'s output via a small adapter function (existing dict → frozen dataclass).

4. Calls `discover_templates([tier1_path, tier3_path])` where:
   - `tier1_path = locate_builtin_templates_dir()` — helper in `parts_routing.py` that finds `templates/parts/` via `importlib.resources.files("cad_spec_gen") / "data" / "templates" / "parts"` for pip-installed mode, falling back to repo-root `templates/parts/` for repo-checkout mode. See §6.3 for the helper's exact implementation.
   - `tier3_path = Path(project_root) / "templates" / "parts"` — project-local override if present

5. Calls `route(name_cn, geom_info, templates)` but only uses the returned `RouteDecision` for log output at INFO level:
   ```python
   log.info("gen_parts routing preview: %s → %s (%s)",
            part_name,
            decision.outcome,
            decision.template.name if decision.template else "fallback")
   ```

6. No behavior change to emission: the Jinja2 fallback path remains the only path in Spec 1.

**What this accomplishes**: Spec 1 ships the routing module + integration but keeps it dormant. Spec 2 flips the switch when auto-routing lands, plus the full Chinese keyword table. The log line is observable during codegen runs so teams can start seeing "what would route where" before committing to the behavior change.

**Why templates stay at repo root**: `templates/parts/*.py` are treated as **data files** (not Python subpackages). They're shipped via `hatch_build.py` COPY_DIRS to `src/cad_spec_gen/data/templates/parts/` in the wheel. Discovery uses filesystem iteration + AST parsing (per invariant #4), not `importlib.import_module`. This avoids the need to create `src/cad_spec_gen/templates/parts/__init__.py` or otherwise restructure the templates tree.

### 7.5 Tests

Pure unit tests with no filesystem / no Blender:

- `discover_templates(path)` returns correct descriptors for a fixture dir with 3 valid + 1 invalid template
- `route(name, geom_info, templates)` returns `HIT_BUILTIN` for an exact keyword match
- `route` returns `AMBIGUOUS` when two templates match with identical priority
- `route` returns `HIT_PROJECT` when a Tier 3 template shadows a Tier 1 template of the same name
- `route` returns `FALLBACK` when no keyword matches
- AST-based descriptor extraction handles malformed templates gracefully (returns `None`, logs warning)
- Same inputs → byte-identical outputs (run 100 times with `PYTHONHASHSEED` varied)

## 8. Phase 4 — `cad-lib` CLI (Local-Only Subset)

### 8.1 Command Scope — Spec 1

**Only local, read-only, non-network commands:**

| Command | Description |
|---------|-------------|
| `cad-lib init` | Create `~/.cad-spec-gen/` directory layout (state subdirs, empty config yamls with `schema_version: 1`) |
| `cad-lib doctor` | Diagnose common issues: `render_3d.py` version diff vs canonical (compares any `cad/<subsystem>/render_3d.py` against `src/cad_spec_gen/render_3d.py`), `locate_builtin_templates_dir()` returns a valid directory, expected templates are discoverable via `discover_templates`, pyproject `cad-lib` entry point present, `~/.cad-spec-gen/` layout matches expected structure |
| `cad-lib list templates` | Show Tier 1 + Tier 3 templates, with their tier and category |
| `cad-lib which template <name>` | Show resolution chain for a template name — which tier provides it, what other tiers are shadowed |
| `cad-lib validate template <name_or_path>` | Run structural validation on a template. `<name_or_path>` resolution order: (1) if it matches an existing file path (absolute or relative to cwd), use that file; (2) else treat as a module name and look it up via `discover_templates` across Tier 1 and Tier 3. Validation steps: AST parse, check `make` + `MATCH_KEYWORDS` + `TEMPLATE_CATEGORY` + `example_params` presence, call `example_params()` to get a dict, optionally call `make(**example_params())` to verify a valid non-empty solid. Name validation regex `^[a-z0-9_]{1,64}$` applies to the name form. |
| `cad-lib migrate-subsystem <dir>` | Copy new canonical `render_3d.py` to `<dir>/render_3d.py` with `.bak` backup. See §8.3. |
| `cad-lib report` | Read `~/.cad-spec-gen/state/suggestions.yaml` (if present) and print deduplicated fallback suggestions. Empty in Spec 1 since nothing writes suggestions yet. |
| `cad-lib migrate` | Stub. Errors with `schema_version` mismatch if encountered. Real migrations are Spec 2's problem. |

**Explicitly NOT in Spec 1**: `install`, `add`, `import`, `sync`, `install-all`, `create template` (all network-facing or code-moving). Those are Spec 2.

### 8.2 `~/.cad-spec-gen/` Layout — Spec 1 Minimal

**Split into shared and state subdirs** (per end-user review feedback on git-sharing):

```
~/.cad-spec-gen/
├── shared/                           # git-safe: user can `git init shared/` to sync across machines
│   ├── templates/                    # (reserved, empty in Spec 1 — Spec 2 uses it)
│   ├── library.yaml                  # schema_version: 1; empty sections
│   └── README.md                     # "this dir is safe to git-sync"
└── state/                            # machine-local, NEVER git-sync
    ├── .gitignore                    # ignores everything in state/
    ├── installed.yaml                # schema_version: 1; empty
    └── suggestions.yaml              # schema_version: 1; empty
```

`cad-lib init` creates this layout and writes a `.gitignore` in `shared/` with `../state/` excluded. The default `.gitignore` pattern means a user who runs `git init` on the parent `~/.cad-spec-gen/` gets a sane default that keeps state out of git.

### 8.3 `cad-lib migrate-subsystem <dir>` Details

```
$ cad-lib migrate-subsystem cad/end_effector
Checking cad/end_effector/render_3d.py ...
  Deployed version: has vertical-FOV-only formula (old)
  Canonical version: has min(fov_v, fov_h) formula (new)
  Diff: 12 lines changed, 4 lines added

This will:
  - Copy src/cad_spec_gen/render_3d.py → cad/end_effector/render_3d.py
  - Back up current file to cad/end_effector/render_3d.py.bak.2026-04-10-143015
  - Local modifications to the deployed copy (e.g., bom_id priority logic) will be preserved
    IF they were already merged into the canonical source during Phase 1.

Proceed? [y/N]
```

**Key invariant**: The command is interactive and requires user confirmation. It never silently overwrites. It only operates on `render_3d.py` in Spec 1 — Spec 2 may add more files to the migration set. Backup files use ISO timestamp suffix so multiple runs don't overwrite each other's `.bak`.

### 8.4 Feature Flag Infrastructure (§G9)

`cad-lib` reads a small set of env vars with prefix `CAD_SPEC_GEN_*`. Spec 1 reserves the names but only implements a few:

| Env var | Default | Spec 1 behavior | Spec 2 use |
|---------|---------|----------------|------------|
| `CAD_SPEC_GEN_HOME` | `~/.cad-spec-gen` | Override user library root | Same |
| `CAD_SPEC_GEN_OFFLINE` | `0` | (unused, reserved) | `1` disables all network in Spec 2 |
| `CAD_SPEC_GEN_AUTO_DOWNLOAD` | `0` | (unused, reserved) | `1` allows auto-download of textures ONLY (per security review) |
| `CAD_SPEC_GEN_TEMPLATE_ROUTING` | `0` | (unused, reserved) | `1` enables Spec 2 auto-routing |
| `CAD_SPEC_GEN_PBR_TEXTURES` | `0` | (unused, reserved) | `1` enables Spec 2 PBR texture system |
| `CAD_SPEC_GEN_REVIEW_DIMENSION_E` | `0` | (unused, reserved) | `1` enables Spec 2 Phase R |
| `PYTHONHASHSEED` | (not set) | Tests set to `0` for determinism | Same |

Reserving names in Spec 1 avoids rename churn when Spec 2 ships. All default to off, consistent with the security posture of "no network unless explicitly opted in".

### 8.5 Files Added — Phase 4

**Single authoritative source**: `src/cad_spec_gen/cad_lib.py` — the CLI is a real Python module inside the package (flat layout decision from §4.3), not a script in `tools/` + mirror. Stdlib + PyYAML only.

**Entry point**: `pyproject.toml` `[project.scripts] cad-lib = "cad_spec_gen.cad_lib:main"`.

**No `tools/cad_lib.py`**: earlier drafts of this spec proposed a `tools/` script + `src/` mirror pair (matching some other tools in the repo). The feasibility review flagged that this requires `src/cad_spec_gen/data/python_tools/` to be a Python package, which it isn't. The flat layout is simpler: the module lives at `src/cad_spec_gen/cad_lib.py` only. For repo-checkout users who want to invoke it without installing the wheel, `python -m cad_spec_gen.cad_lib` works as long as `src/` is on `sys.path` (same pattern used by `codegen/gen_parts.py`).

## 9. Phase 5 — Packaging Fix

### 9.1 Current State

DevOps review found that `hatch_build.py` ships `PYTHON_TOOLS` and `COPY_DIRS` but NOT:

- `parts_library.default.yaml` (existing, never packaged — blocks `cad-lib doctor` from reading defaults)
- `catalogs/library_manifest.yaml` (deferred to Spec 2; Spec 1 doesn't need this)

The three new Python modules (`render_3d.py`, `parts_routing.py`, `cad_lib.py`) do NOT need `hatch_build.py` changes because they live directly under `src/cad_spec_gen/` (flat layout per §4.3) and are picked up by the existing `[tool.hatch.build.targets.wheel] packages = ["src/cad_spec_gen"]` directive. Templates under `templates/parts/*.py` are already copied by existing `COPY_DIRS["templates"] = "templates"` to `src/cad_spec_gen/data/templates/`.

### 9.2 Fix Scope — Spec 1

**Note**: Under the flat layout decision (§4.3), `render_3d.py`, `parts_routing.py`, and `cad_lib.py` all live DIRECTLY under `src/cad_spec_gen/` — they are real Python modules in the wheel. They are picked up automatically by `[tool.hatch.build.targets.wheel] packages = ["src/cad_spec_gen"]` in `pyproject.toml`. **No `hatch_build.py` changes are needed for these three files.**

What `hatch_build.py` still needs:

1. **`parts_library.default.yaml`** — currently NOT shipped. Add it to the `COPY_DIRS` or as a new standalone entry. Concrete fix (paste this into `hatch_build.py`):
   ```python
   # In hatch_build.py, alongside the existing COPY_DIRS:
   TOP_LEVEL_FILES = {
       "parts_library.default.yaml": "parts_library.default.yaml",
   }

   # In the copy loop, after COPY_DIRS processing:
   for src_name, dest_rel in TOP_LEVEL_FILES.items():
       src_path = repo_root / src_name
       dest_path = build_data_dir / dest_rel
       dest_path.parent.mkdir(parents=True, exist_ok=True)
       shutil.copy2(src_path, dest_path)
   ```
   This puts `parts_library.default.yaml` into `src/cad_spec_gen/data/parts_library.default.yaml` in the wheel. Code that needs to read it uses `importlib.resources.files("cad_spec_gen") / "data" / "parts_library.default.yaml"`.

2. **`templates/parts/*.py`** — VERIFIED already copied via existing `COPY_DIRS["templates"] = "templates"`, which recursively copies the whole `templates/` directory (including `templates/parts/`) to `src/cad_spec_gen/data/templates/`. **No change needed.** This is consistent with §6.3's `locate_builtin_templates_dir` helper, which looks up templates via `importlib.resources.files("cad_spec_gen") / "data" / "templates" / "parts"`.

3. **Pre-existing `hatch_build.py:38` bug** — the file imports `SHARED_TOOL_FILES` from `cad_paths` but that symbol does not exist in `cad_paths.py`; it always falls through to the hardcoded fallback at lines 42-43. This is a pre-existing bug, not introduced by Spec 1, but flagged here because Phase 5 implementers will be editing this file anyway. Consider fixing the import while editing (5-minute side quest) OR leaving it alone if out of scope.

Also add `[project.scripts]` entry point for `cad-lib` in `pyproject.toml`:
```toml
[project.scripts]
cad-skill-setup = "cad_spec_gen.wizard.cli:setup"       # existing
cad-skill-check = "cad_spec_gen.wizard.cli:check"       # existing
cad-lib = "cad_spec_gen.cad_lib:main"                   # NEW
```

And add pytest env config:
```toml
[tool.pytest.ini_options]
env = [
    "PYTHONHASHSEED=0",
    "PYTHONIOENCODING=utf-8",
]
markers = [
    "fast: unit tests, <100ms each",
    "integration: full-chain tests",
    "slow: Blender or packaging tests, ran on main/nightly only",
]
```

### 9.3 Post-Build Smoke Test (new CI gate)

Add to CI:
```bash
pip install dist/*.whl
cad-lib doctor
cad-lib list templates  # must show 5 templates
python -c "from cad_spec_gen.parts_routing import route, discover_templates; print('OK')"
```

Any non-zero exit fails the build. This catches the exact class of packaging bug the DevOps review identified.

### 9.4 Files Modified

- `hatch_build.py` — add missing entries to COPY_DIRS / PYTHON_TOOLS
- `pyproject.toml` — `[project.scripts]` entry point
- `.github/workflows/<ci>.yml` or equivalent — smoke test step

## 10. Phase 6 — Schema Versioning Foundation

### 10.1 Invariant

Every YAML file Spec 1 creates under `~/.cad-spec-gen/` ships with:

```yaml
schema_version: 1
# ... other fields
```

Readers MUST:
- Refuse to operate on unknown `schema_version` values (print clear error, suggest `cad-lib migrate`)
- Ignore unknown top-level keys at a given schema version (forward compat)
- Round-trip-preserve unknown keys when writing (don't silently drop user additions)

### 10.2 Canonical v1 YAML Files — Created by `cad-lib init`

#### `~/.cad-spec-gen/shared/library.yaml`

```yaml
# cad-spec-gen user library — shared config
# This file is safe to commit to a git repository for team-sharing.
# See ~/.cad-spec-gen/state/ for machine-local state (NEVER commit).

schema_version: 1

# Template routing rules (Spec 2 will populate; empty in Spec 1).
# Each rule: {name_contains: [...], geom_type: "...", template: "name",
#             param_map: {template_param: source_field}}
routing: []

# User-defined material preset extensions (Spec 2 will populate).
# Keys follow MATCH_KEYWORDS convention; values are PBR parameter dicts
# compatible with render_config.MATERIAL_PRESETS format.
materials: {}

# User template keyword overrides (Spec 2 will populate).
# Format: {<template_name>: {add: [kw1, kw2], remove: [kw3]}}
template_keywords: {}
```

#### `~/.cad-spec-gen/shared/README.md`

```markdown
# cad-spec-gen shared library

This directory is **safe to commit to git** for team-sharing.

Contents:
- `library.yaml` — routing rules, material presets, keyword overrides
- `templates/` — (Spec 2) user-added template modules
- `textures/` — (Spec 2) PBR texture packs

Machine-local state is stored in the sibling `state/` directory and
must NOT be committed. A `.gitignore` is automatically created there.

Run `cad-lib doctor` to check the library's health.
```

#### `~/.cad-spec-gen/state/installed.yaml`

```yaml
# cad-spec-gen installed asset log — MACHINE-LOCAL, do not commit.
# Maintained by `cad-lib install` (Spec 2). Spec 1 creates this empty.

schema_version: 1

# Installed texture packs: {key: {installed_at, source_url, checksum_sha256, local_path}}
textures: {}

# Installed community templates: {name: {installed_at, source, based_on, checksum}}
templates: {}

# Installed model packages: {name: {installed_at, source, variants}}
models: {}
```

#### `~/.cad-spec-gen/state/suggestions.yaml`

```yaml
# cad-spec-gen library growth suggestions — MACHINE-LOCAL, do not commit.
# Auto-appended by gen_parts.py and cad_spec_reviewer.py when they fall back
# to Jinja2 primitives or scalar material defaults. Spec 1 creates this empty;
# Spec 2 writes entries as pipeline runs accumulate fallback data.

schema_version: 1

suggestions: []
# Each entry:
#   - timestamp: ISO-8601 UTC
#     kind: template | texture | material
#     reason: human-readable explanation
#     keyword: the BOM keyword that triggered the fallback (optional)
#     geom_type: the geometry type from _guess_geometry (optional)
#     suggestion: copy-pasteable cad-lib command
```

#### `~/.cad-spec-gen/state/.gitignore`

```
# Machine-local state — never commit.
*
!.gitignore
```

### 10.3 Reader Invariants

All Spec 1 code that loads any of these YAMLs follows these rules:

1. **Refuse unknown versions**: if `schema_version` is missing or > 1, print a clear error (`"unsupported library version N; expected 1; run 'cad-lib migrate'"`) and exit with non-zero. Never silently attempt to interpret unknown formats.
2. **Ignore unknown top-level keys**: for forward compatibility, readers accept unknown keys at schema version 1 and preserve them when re-writing. Writers use PyYAML with `default_flow_style=False` and `sort_keys=False` so order is stable.
3. **Round-trip preservation**: if `cad-lib doctor` reads `library.yaml` with an unknown `experimental_flag: true` at the top level, and later a write operation touches the file, `experimental_flag: true` must still be present afterward. Tested by a round-trip test fixture.

### 10.4 `cad-lib migrate` Stub

In Spec 1, `cad-lib migrate` is a stub that:
- Checks current `schema_version` of every YAML
- If all are version 1 → prints "all schemas current"
- If any are > 1 → errors "unknown version, please upgrade the skill"
- If any are < 1 → errors "legacy format, migration not yet implemented" (Spec 2 writes actual migrations)

This reserves the command surface without committing to migration logic yet.

## 11. Files Modified / Added — Complete List

### 11.1 Skill-Level Files (AUTHORIZED TO MODIFY)

**Pipeline tools**:

| File | Location | Mirror | Change |
|------|----------|--------|--------|
| `render_config.py` | repo root | `src/cad_spec_gen/data/python_tools/render_config.py` (build-generated, auto-synced by `hatch_build.py:PYTHON_TOOLS`) | docstring only; edit repo-root copy only |
| `render_depth_only.py` | repo root | — (no mirror) | FOV formula fix (text-pattern anchor, see §5.4) |
| `render_3d.py` | **NEW at** `src/cad_spec_gen/render_3d.py` (flat layout per §4.3) | — | Step 1: copy baseline from `cad/end_effector/render_3d.py`; Step 2: apply FOV fix |
| `parts_routing.py` | **NEW at** `src/cad_spec_gen/parts_routing.py` (flat layout) | — | new pure-function module |
| `cad_lib.py` | **NEW at** `src/cad_spec_gen/cad_lib.py` (flat layout) | — | new local-only CLI |
| `codegen/gen_parts.py` | repo root ONLY (hand-edited) | `src/cad_spec_gen/data/codegen/gen_parts.py` (**build-generated**, do NOT edit by hand — regenerated from repo root on every `hatch build`) | add `sys.path` insert for `src/` + import `parts_routing` + adapter for `_guess_geometry` → `GeomInfo` + log-only route call |

**Templates** (Tier 1, repo root):
- `templates/parts/__init__.py` — dynamic discovery rewrite
- `templates/parts/iso_9409_flange.py` — module contract retrofit + docstring generality
- `templates/parts/l_bracket.py` — NEW
- `templates/parts/rectangular_housing.py` — NEW
- `templates/parts/cylindrical_housing.py` — NEW
- `templates/parts/fixture_plate.py` — NEW

**CLI tools**:
- `src/cad_spec_gen/cad_lib.py` — NEW, single authoritative location (no `tools/` + mirror pair; see §8.5 rationale)

**Packaging**:
- `hatch_build.py` — add missing files to COPY_DIRS / PYTHON_TOOLS
- `pyproject.toml` — `[project.scripts]` entry point + pytest env (`PYTHONHASHSEED=0`, `PYTHONIOENCODING=utf-8`)

**Tests** (all NEW — `tests/conftest.py` does not currently exist; verified via `ls tests/`):
- `tests/conftest.py` — **NEW** — autouse fixture: redirect `Path.home()` and `CAD_SPEC_GEN_HOME` to `tmp_path`, hash-based tripwire on real home access (see §13.1). Requires Phase 0 audit of existing tests for pre-existing HOME reads before landing.
- `tests/test_parts_routing.py` — NEW
- `tests/test_templates.py` — NEW (each template: `example_params()` + `make()` → valid solid)
- `tests/test_cad_lib_local.py` — NEW (init, doctor, list, which, validate, migrate-subsystem)
- `tests/test_fov_fix.py` — NEW
- `tests/test_packaging.py` — NEW (post-build smoke)
- `tests/fixtures/template_pack_factory.py` — NEW (factory pattern per QA review)

### 11.2 Files NEVER Touched (INTERMEDIATE PRODUCTS)

- `cad/end_effector/*` — any file under any subsystem dir, unless explicitly via `cad-lib migrate-subsystem`
- `cad/lifting_platform/*`
- Any `ee_*.py`, `std_*.py`, `assembly.py`, `build_all.py`, `params.py`, `render_config.json`

### 11.3 Runtime-Created by `cad-lib init`

- `~/.cad-spec-gen/shared/` (dir)
- `~/.cad-spec-gen/shared/library.yaml`
- `~/.cad-spec-gen/shared/README.md`
- `~/.cad-spec-gen/state/` (dir)
- `~/.cad-spec-gen/state/.gitignore`
- `~/.cad-spec-gen/state/installed.yaml`
- `~/.cad-spec-gen/state/suggestions.yaml`

## 12. Data Consistency Invariants — Spec 1

These must hold across all phases:

1. **FOV formula**: `min(fov_v, fov_h)` in both `src/cad_spec_gen/render_3d.py` (new canonical) and `render_depth_only.py`. **`frame_fill` default stays at 0.75 everywhere**.

2. **Template contract**: every template in `templates/parts/` (existing + new) exposes `make`, `MATCH_KEYWORDS`, `MATCH_PRIORITY`, `TEMPLATE_CATEGORY`, `TEMPLATE_VERSION`, `example_params`. Missing any → template is skipped by discovery with a WARNING log.

3. **`parts_routing` is the single source of truth for matching decisions**: `gen_parts.py` (and, in Spec 2, `cad_spec_reviewer.py`) NEVER duplicates the keyword/priority/AMBIGUOUS logic. Any new matching behavior goes into `parts_routing.py` first.

4. **Dynamic discovery via AST, not execution**: `discover_templates` reads `.py` files as text and parses with `ast.parse` to extract descriptors. It does NOT `importlib.import_module` third-party paths. (Tier 1 builtin templates are imported via normal package mechanism because they're trusted skill code; Tier 3 project templates are descriptor-scanned only in Spec 1, actual `make()` invocation happens during the existing `gen_parts.py` Jinja2 path which is unchanged.)

5. **Never overwrite without confirmation**: `cad-lib init` refuses to clobber an existing `~/.cad-spec-gen/`; `cad-lib migrate-subsystem` always writes `.bak` and always prompts.

6. **No network operations**: Spec 1 code paths contain zero `urllib`, `requests`, `http.client`, `socket.create_connection`. Grep-enforced in CI.

7. **No `importlib.import_module` of `~/.cad-spec-gen/` paths**: Spec 1 only imports from the skill package itself and from project-local `templates/parts/`. Grep-enforced in CI.

8. **All new YAML has `schema_version: 1`**: readers reject unknown versions; writers preserve unknown keys round-trip.

9. **`PYTHONHASHSEED=0` in test env** + every text-mode file open uses `newline="\n"` — determinism under Windows.

10. **No intermediate products touched**: grep-enforced in CI — CI fails if a PR diff touches `cad/*/render_3d.py` or `cad/*/render_config.py` outside of explicit test fixtures.

11. **Generality**: grep-enforced in CI — new templates must not contain the strings `end_effector`, `lifting_platform`, `GISBOT`, `ee_`, `std_ee_`, `applicator`.

## 13. Testing Strategy — Spec 1

### 13.1 Test Infrastructure (precedes all other tests)

**`tests/conftest.py`**:

```python
# tests/conftest.py
import hashlib
import os
import pytest
from pathlib import Path


def _dir_state_hash(path: Path) -> str | None:
    """Return a stable hash of a directory's contents (files + sizes + mtimes),
    or None if it doesn't exist. Used as a tamper-evidence snapshot for the
    real ~/.cad-spec-gen/ during the test session.

    Why a hash instead of a bare mtime: NTFS/FAT have ~1-second mtime resolution,
    so two tests finishing in the same second can race the mtime check. A hash
    over (rel_path, size, mtime) tuples for every file in the tree catches any
    content mutation regardless of timestamp resolution.
    """
    if not path.exists():
        return None
    parts = []
    for p in sorted(path.rglob("*")):
        if p.is_file():
            st = p.stat()
            rel = p.relative_to(path).as_posix()
            parts.append(f"{rel}|{st.st_size}|{st.st_mtime_ns}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# Captured ONCE when conftest is first imported — pytest imports conftest.py
# before running any tests, so this is a session-start snapshot.
_REAL_HOME_CAD_DIR = Path.home() / ".cad-spec-gen"
_REAL_HOME_HASH_AT_START = _dir_state_hash(_REAL_HOME_CAD_DIR)


@pytest.fixture(autouse=True, scope="function")
def isolate_cad_spec_gen_home(monkeypatch, tmp_path):
    """Redirect ~/.cad-spec-gen to tmp_path for every test.

    Tripwire (teardown): if the real user home's .cad-spec-gen directory
    state changes during the test run, fail loudly. This catches forgotten
    monkeypatches that bypassed the HOME redirect and wrote to the real home.
    """
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True)
    # Pre-create .cad-spec-gen so "refuse-to-clobber-existing-dir" tests can
    # assert on its presence. Tests that need a clean slate can os.rmdir it.
    (fake_home / ".cad-spec-gen").mkdir()
    monkeypatch.setenv("CAD_SPEC_GEN_HOME", str(fake_home / ".cad-spec-gen"))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    yield

    # Tripwire check — real user home must be byte-identical to session start.
    current_hash = _dir_state_hash(_REAL_HOME_CAD_DIR)
    assert current_hash == _REAL_HOME_HASH_AT_START, (
        f"Real {_REAL_HOME_CAD_DIR} was modified during test.\n"
        f"  Before: {_REAL_HOME_HASH_AT_START}\n"
        f"  After:  {current_hash}\n"
        f"A code path bypassed the HOME/CAD_SPEC_GEN_HOME monkeypatch — "
        f"fixture breach! Find the unprotected filesystem call and wrap it."
    )
```

**Audit of pre-existing tests before landing this fixture**: the feasibility review flagged that existing tests might already read `~/.cad-spec-gen/` without monkeypatching. Before adding this autouse fixture, run `grep -r "cad-spec-gen" tests/` to list any such tests and verify they pass with the new redirect. If any test genuinely needs to read the real home (e.g., a smoke test for install detection), exempt it with `@pytest.fixture.disable` or scope the fixture to opt-in via `pytest.mark.usefixtures` instead of autouse. This audit is part of Phase 0 delivery, not an afterthought.

Pytest env in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
env = [
    "PYTHONHASHSEED=0",
    "PYTHONIOENCODING=utf-8",
]
markers = [
    "fast: unit tests, <100ms each",
    "integration: full-chain tests",
    "slow: Blender or packaging tests, ran on main/nightly only",
]
```

### 13.2 Phase 1 Tests (FOV Fix)

- **Unit**: `test_fov_formula_min_vs_vertical` — with synthetic bounding sphere + sensor params, verify `min(fov_v, fov_h)` returns expected distance
- **Silhouette regression**: render wide model (300×60×40) and square model (100×100×100), compare silhouette bbox via `scikit-image regionprops` on binarized alpha, tolerance 2% area / 2px bbox-edge
- **Golden format**: goldens stored as `.npy` arrays, not PNGs (avoid encoder drift)
- **Blender version pin**: test skipped (not failed) if Blender version differs from pinned; `pytest.importorskip("bpy")`
- **Marker**: `@pytest.mark.slow`

### 13.3 Phase 2 Tests (Templates)

- For each template (including `iso_9409_flange`): call `make(**example_params())`, assert `isSolid()` and `Volume() > 0`
- Generality grep test: `assert "end_effector" not in open(template_file).read()` for each new template file
- `MATCH_KEYWORDS` non-empty and all-lowercase for each template
- `TEMPLATE_CATEGORY` in allowed set
- Dynamic discovery test: drop a fixture template in `tmp_path`, call `_discover_builtin_templates`-equivalent, verify it's discovered
- Marker: `@pytest.mark.fast` for contract tests, `@pytest.mark.integration` for full `make()` invocation

### 13.4 Phase 3 Tests (`parts_routing`)

- `route(name, geom_info, templates)` table-driven: 20+ parametrized cases covering HIT_BUILTIN, HIT_PROJECT, AMBIGUOUS, FALLBACK
- Determinism: same inputs, 100 iterations under randomized `PYTHONHASHSEED`, byte-identical `RouteDecision` outputs
- `discover_templates` AST-only: verify no `importlib.import_module` is called by patching it to raise
- Tier 3 shadows Tier 1 with same name
- Marker: `@pytest.mark.fast`

### 13.5 Phase 4 Tests (`cad-lib` Local)

- `cad-lib init` creates full layout with correct `schema_version: 1` values
- `cad-lib init` refuses to clobber existing dir
- `cad-lib doctor` detects missing `render_3d.py` canonical
- `cad-lib list templates` shows all 5 templates
- `cad-lib which template l_bracket` shows Tier 1 and absence of Tier 2/3
- `cad-lib validate template <good_file>` passes; `<bad_file>` (missing `MATCH_KEYWORDS`) fails with clear message
- `cad-lib validate template <traversal_attempt>` refuses `../../etc/passwd` via regex
- `cad-lib migrate-subsystem <fake_dir>` creates `.bak` with timestamp suffix, copies canonical, prompts
- `cad-lib migrate` stub errors correctly on unknown version
- Name validation regex test: `cad-lib validate template ../../bashrc` → rejected
- Marker: `@pytest.mark.fast`

### 13.6 Phase 5 Tests (Packaging)

- Build wheel locally: `hatch build`
- Install into fresh venv: `pip install dist/*.whl`
- `cad-lib doctor` exit 0
- `cad-lib list templates` outputs 5 lines
- `python -c "from cad_spec_gen.parts_routing import route"` imports cleanly
- Marker: `@pytest.mark.slow`

### 13.7 CI Tiering

```
# Every push / PR
pytest -m "fast or integration"       # target: <3 min, no Blender, no venv builds

# main branch + nightly
pytest -m "slow"                       # Blender visual regression + packaging

# Release branch
pytest                                 # full suite
```

### 13.8 Determinism Assertions — Concrete

For invariant #9 ("same inputs → identical outputs"), tests use byte-level comparison:
```python
def test_routing_deterministic(self):
    inputs = make_route_inputs()
    result1 = route(*inputs)
    result2 = route(*inputs)
    assert dataclasses.asdict(result1) == dataclasses.asdict(result2)
    # Serialize and byte-compare
    assert json.dumps(dataclasses.asdict(result1), sort_keys=True).encode() == \
           json.dumps(dataclasses.asdict(result2), sort_keys=True).encode()
```

## 14. Phased Delivery

### 14.1 Corrected Dependency Graph

The feasibility review corrected the original phasing. The real graph is:

```
P0 (test infra — conftest.py + pyproject pytest env)
    │
    ├──► P1 (FOV fix + render_3d.py canonical) ──┐
    ├──► P2 (5 templates + discovery helper)  ───┤
    ├──► P3 (parts_routing.py pure module)    ───┤
    │                                            ├──► P4 (cad-lib local CLI) ──► P5 (packaging + CI smoke)
    │                                            │                           │
    │                                            │                           └──► P6 (schema YAML writers, parallel to P5)
```

| Phase | Scope | Deps | Approx. LOC |
|-------|-------|------|------------|
| **P0** | Test infrastructure: `tests/conftest.py` autouse fixture (§13.1) + `pyproject.toml` `[tool.pytest.ini_options]` env (`PYTHONHASHSEED=0`, `PYTHONIOENCODING=utf-8`, `markers`) + audit of existing tests for HOME reads | **Gates P1-P6 tests** (none of them should run without it) | ~50 |
| **P1** | FOV fix: create `src/cad_spec_gen/render_3d.py` (baseline copy from `cad/end_effector/render_3d.py`) + apply `min(fov_v, fov_h)` formula + `render_depth_only.py` sync + `render_config.py` docstring update | P0 (for tests) | ~50 |
| **P2** | 4 new templates (`l_bracket`, `rectangular_housing`, `cylindrical_housing`, `fixture_plate`) + `iso_9409_flange` retrofit with module contract constants + `templates/parts/__init__.py` simplification (docstring-only, no hardcoded imports) | P0 (for tests) | ~1500 |
| **P3** | `src/cad_spec_gen/parts_routing.py` (pure functions — `GeomInfo`, `TemplateDescriptor`, `RouteDecision`, `discover_templates`, `route`, `locate_builtin_templates_dir`) + `codegen/gen_parts.py` log-only integration | P0 (for tests) | ~500 |
| **P4** | `src/cad_spec_gen/cad_lib.py` local CLI (`init`, `doctor`, `list templates`, `which template`, `validate template`, `migrate-subsystem`, `report`, `migrate` stub) + reserved feature-flag env var infrastructure | P0 + **P1** (for `migrate-subsystem` to have a canonical source to copy) + **P2** (for `list templates` to have anything to show) + **P3** (for `validate template` and `which` to call `discover_templates`/`route`) | ~700 |
| **P5** | `hatch_build.py` adds `parts_library.default.yaml` shipping + `pyproject.toml` `[project.scripts] cad-lib` entry point + CI post-build smoke test (pip install + `cad-lib doctor` + `cad-lib list templates`) | P0 + **P1 + P2 + P3 + P4** (ships their files in the wheel; smoke test imports and invokes them) | ~50 code + CI yaml |
| **P6** | `cad-lib init` YAML writers with `schema_version: 1` + `cad-lib migrate` stub + tripwire test for round-trip key preservation | P4 (needs `cad-lib init` command) | ~100 |

### 14.2 Parallelism — What's Actually True

**Verified independent**:
- **P1, P2, P3 are fully independent** of each other — they touch disjoint files. `parts_routing.py` in P3 does not import P2 templates (it reads them via AST). P1's FOV fix doesn't touch any codegen path.
- **P6 is independent of P5** once P4 is done — both depend on P4 but not on each other.

**Verified serial**:
- **P4 joins on P1 + P2 + P3**: `cad-lib doctor` checks canonical `render_3d.py` exists (P1), `cad-lib list templates` enumerates P2's templates, `cad-lib validate template` and `which` call P3's `parts_routing.py`.
- **P5 joins on P1 + P2 + P3 + P4**: the wheel build ships all their files, and the CI smoke test exercises all of them end-to-end.

**P5 circular dependency with P4's `doctor` test**: `cad-lib doctor` (P4) checks "pyproject `cad-lib` entry point present" which is a P5 deliverable. P4's doctor test for that specific check must be marked `@pytest.mark.xfail(reason="entry point lands in P5")` until P5 merges, then flipped to a passing test.

### 14.3 Corrected MVP Claim

**The original spec's "P1 + P2 + P5 alone" MVP claim was wrong.** P5 cannot build a working wheel without P3's `parts_routing.py` (P5's CI smoke test imports it) and without P4's `cad-lib` entry point (P5's CI smoke test invokes it).

**True minimum viable shipment**: **P0 + P1 + P2 + P3 + P4 + P5**. That's five implementation phases plus test infra. Everything is required.

**P6 is the only legitimately optional phase** for a first minor release — if P6 is skipped, `cad-lib init` can still run but writes YAML files without the `schema_version` key. Degraded (breaks forward-compat with Spec 2) but not crashing. Recommendation: do not skip P6; it's ~100 LOC and Spec 2 depends on the foundation.

### 14.4 Recommended Delivery Order

**Single engineer (walking skeleton)**:
1. **P0** — test infra (~30 min, gates everything)
2. **P1** — FOV fix (smallest ship, visible win)
3. **P3** — routing module (hardest conceptually, get it done while context is fresh)
4. **P2** — templates (parallelizable per-file; commits incrementally)
5. **P4** — CLI (all dependencies in place)
6. **P5** + **P6** in parallel — packaging and schema writers

**Two engineers**:
- Eng A: P0 → P1 → P3 → P5 (CLI-adjacent, packaging)
- Eng B: P2 (all 5 templates) → P4 → P6
- Join at P4/P5 boundary

**Three engineers**:
- Day 1: pair on P0; then split P1/P2/P3 one per engineer
- Day 2: one engineer does P4 while the other two finish P2 tail or draft P5 scaffolding
- Day 3: P5 + P6

### 14.5 Critical Path

Longest chain in wall-clock: **P0 → P3 → P4 → P5**. P3 is the critical-path phase because it's the largest conceptually-new module (~500 LOC with AST parsing, frozen dataclasses, and determinism tests) and because both P4 and P5 depend on it. P2 is larger in raw LOC (~1500) but embarrassingly parallel across 5 independent template files — it does not gate the critical path with more than one engineer.

## 15. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| `importlib.resources.files("cad_spec_gen")` behavior differs between editable install and wheel install | `locate_builtin_templates_dir()` has an explicit repo-root fallback path (§6.3); `test_parts_routing.py` exercises both branches via monkeypatched paths |
| `parts_routing` dormant integration gets forgotten before Spec 2 | Add a doctor check: "parts_routing.route is imported but RouteDecision is never consumed by gen_parts emission — ready for Spec 2 auto-routing" |
| User runs `cad-lib migrate-subsystem` and loses local customizations | Always backup to `.bak.<timestamp>`; migrate command prints diff and prompts; never skip confirmation |
| `cad-lib` CLI ships without pip entry point → users can only call via `python -m cad_spec_gen.cad_lib` | §9.3 post-build smoke test catches this (runs `cad-lib doctor` via the entry point) |
| Dynamic template discovery executes malicious top-level code in a user-added template | Spec 1 does NOT add Tier 2 (`~/.cad-spec-gen/shared/templates/`); Tier 3 project templates are scanned via AST only in Spec 1's `parts_routing`. Actual template execution still happens in `gen_parts.py`'s existing Jinja2 path, which is pre-existing behavior. |
| Test fixture leaks real home | Session autouse fixture + tripwire + mandatory `Path.home()` monkeypatch |
| `render_3d.py` canonical diverges from deployed copies after Phase 1 | Acceptable in Spec 1 — `cad-lib migrate-subsystem` is the user-invoked sync mechanism; `cad-lib doctor` warns about drift |

## 16. Open Questions (non-blocking)

- Whether `fixture_plate` should include threaded insert holes as a separate feature or via a `hole_type` parameter — defer to implementation; the `example_params()` in §6.2.2 omits inserts, implementer can add if trivial
- Whether `cad-lib doctor` should emit exit code != 0 on warnings (for CI) or only on errors — default to errors-only in Spec 1, add `--strict` in Spec 2 alongside Phase R
- Whether to fix the pre-existing `hatch_build.py:38` `SHARED_TOOL_FILES` import bug (flagged in §9.2) during Phase 5 or leave it alone — recommendation: fix it since the implementer will be editing the file anyway

## 17. Explicit Non-Features (to kill confusion)

Things that sound like Spec 1 but are **NOT**:

- "Just a small download" — no. Zero network in Spec 1.
- "Maybe a quick PBR preview" — no. Spec 2.
- "The review check for missing templates" — no. Spec 2.
- "Chinese keyword support for the templates" — no. Spec 2 (and will need the full expansion from the Chinese engineering review).
- "A GB/T fastener lookup table" — no. Spec 2.
- "Team-sharing of installed templates via the git-ready `shared/` dir" — the dir is created and gitignored correctly, but the user putting templates in it and git-syncing is a user-workflow matter; Spec 1 doesn't automate it.

---

**End of Spec 1 — Foundation.**

Next: implementation planning via the `writing-plans` skill.
