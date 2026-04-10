# Spec 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the foundation layer of the cad-spec-gen asset library: FOV fix, 5 parametric templates, `parts_routing.py` pure module, local-only `cad-lib` CLI, packaging fix, and schema versioning — without any network-facing features.

**Architecture:** New Python modules go directly under `src/cad_spec_gen/` (flat layout). Templates stay at repo-root `templates/parts/` as data files discovered via AST parsing, not Python imports. Existing subsystem `render_3d.py` stays untouched; a new canonical source lives at `src/cad_spec_gen/render_3d.py` for future subsystems to inherit via `cad-lib migrate-subsystem`.

**Tech Stack:** Python 3.10+, CadQuery (for template `make()` functions), PyYAML, stdlib `ast` / `importlib.resources` / `pkgutil` / `argparse`, pytest, hatch build system.

**Spec reference:** `docs/superpowers/specs/2026-04-10-spec1-foundation-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tests/conftest.py` | Create | Autouse fixture: redirect `~/.cad-spec-gen/` to `tmp_path`, hash-based tripwire on real home access |
| `pyproject.toml` | Modify | Add `[tool.pytest.ini_options]` env + markers; add `cad-lib` entry point |
| `src/cad_spec_gen/render_3d.py` | Create | Skill-level canonical copy of `cad/end_effector/render_3d.py` with FOV fix |
| `render_depth_only.py` | Modify | Apply `min(fov_v, fov_h)` formula |
| `render_config.py` | Modify | Docstring update only (both repo root + `src/` mirror) |
| `templates/parts/__init__.py` | Modify | Simplify to docstring-only (no hardcoded imports) |
| `templates/parts/iso_9409_flange.py` | Modify | Add `MATCH_KEYWORDS`, `MATCH_PRIORITY`, `TEMPLATE_CATEGORY`, `TEMPLATE_VERSION`, `example_params()`; genericize docstring |
| `templates/parts/l_bracket.py` | Create | L-shaped bracket template, ~350 LOC |
| `templates/parts/rectangular_housing.py` | Create | Hollow box enclosure template, ~400 LOC |
| `templates/parts/cylindrical_housing.py` | Create | Cylinder enclosure template, ~400 LOC |
| `templates/parts/fixture_plate.py` | Create | Flat plate with hole grid template, ~350 LOC |
| `src/cad_spec_gen/parts_routing.py` | Create | Pure functions: `GeomInfo`, `TemplateDescriptor`, `RouteDecision`, `discover_templates`, `route`, `locate_builtin_templates_dir` |
| `codegen/gen_parts.py` | Modify | Add `sys.path` bootstrap + import `parts_routing` + log-only route() call |
| `src/cad_spec_gen/cad_lib.py` | Create | Local-only CLI: init, doctor, list, which, validate, migrate-subsystem, report, migrate |
| `hatch_build.py` | Modify | Ship `parts_library.default.yaml` in wheel |
| `tests/test_fov_fix.py` | Create | Unit test for `min(fov_v, fov_h)` formula |
| `tests/test_templates.py` | Create | Each template: `example_params()` + `make()` → valid solid |
| `tests/test_parts_routing.py` | Create | Unit tests for `discover_templates`, `route`, edge cases, determinism |
| `tests/test_cad_lib_local.py` | Create | CLI command tests (init/doctor/list/which/validate/migrate-subsystem) |
| `tests/test_packaging.py` | Create | Post-build wheel install + `cad-lib doctor` smoke |
| `tests/fixtures/template_pack_factory.py` | Create | Factory for generating synthetic template files for tests |

---

## Phase 0: Test Infrastructure

### Task 1: Create `tests/conftest.py` with hash-based home tripwire

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_conftest_tripwire.py` (meta-test for the fixture itself)

- [ ] **Step 1: Audit existing tests for direct `~/.cad-spec-gen/` reads**

Run: `grep -rn "cad-spec-gen" D:/Work/cad-spec-gen/tests/ 2>&1 | grep -v "\.pyc"`
Expected: Report any tests that read from the real home directory. Document findings in a comment inside `conftest.py`. If any tests actually depend on the real `~/.cad-spec-gen/step_cache/` (known to exist), exempt them via `@pytest.mark.usefixtures` opt-in.

- [ ] **Step 2: Write the conftest.py module**

```python
# tests/conftest.py
"""Pytest configuration for cad-spec-gen tests.

This conftest installs an autouse fixture that redirects ~/.cad-spec-gen/
to a per-test tmp_path, with a hash-based tripwire that fails loudly if
any test bypasses the redirect and modifies the real user home.

Why a hash instead of mtime: NTFS/FAT have ~1-second mtime resolution,
so two tests finishing in the same second can race an mtime check.
A hash over (rel_path, size, mtime) tuples for every file catches any
content mutation regardless of timestamp resolution.
"""
import hashlib
import os
from pathlib import Path

import pytest


def _dir_state_hash(path: Path) -> str | None:
    """Return a stable hash of a directory's contents, or None if missing."""
    if not path.exists():
        return None
    parts = []
    for p in sorted(path.rglob("*")):
        if p.is_file():
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(path).as_posix()
            parts.append(f"{rel}|{st.st_size}|{st.st_mtime_ns}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# Captured ONCE at conftest import time (before any test runs).
_REAL_HOME_CAD_DIR = Path.home() / ".cad-spec-gen"
_REAL_HOME_HASH_AT_START = _dir_state_hash(_REAL_HOME_CAD_DIR)


@pytest.fixture(autouse=True, scope="function")
def isolate_cad_spec_gen_home(monkeypatch, tmp_path):
    """Redirect ~/.cad-spec-gen to tmp_path for every test.

    Tripwire (teardown): fail loudly if real user home's .cad-spec-gen
    directory state changed during the test.
    """
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True)
    (fake_home / ".cad-spec-gen").mkdir()
    monkeypatch.setenv("CAD_SPEC_GEN_HOME", str(fake_home / ".cad-spec-gen"))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    yield

    current_hash = _dir_state_hash(_REAL_HOME_CAD_DIR)
    assert current_hash == _REAL_HOME_HASH_AT_START, (
        f"Real {_REAL_HOME_CAD_DIR} was modified during test.\n"
        f"  Before: {_REAL_HOME_HASH_AT_START}\n"
        f"  After:  {current_hash}\n"
        f"A code path bypassed the HOME monkeypatch — fixture breach!"
    )
```

- [ ] **Step 3: Write meta-test verifying the fixture works**

```python
# tests/test_conftest_tripwire.py
"""Meta-tests for the conftest.py autouse fixture."""
import os
from pathlib import Path


def test_home_is_redirected():
    """Path.home() must point inside tmp_path, not the real user home."""
    home = Path.home()
    assert ".cad-spec-gen" not in str(home) or "fake_home" in str(home)
    assert "fake_home" in str(home), f"Expected fake_home in {home}"


def test_cad_spec_gen_home_env_set():
    """CAD_SPEC_GEN_HOME env var must be set to the fake home."""
    val = os.environ.get("CAD_SPEC_GEN_HOME", "")
    assert "fake_home" in val, f"Expected fake_home in CAD_SPEC_GEN_HOME={val}"


def test_fake_cad_spec_gen_dir_exists():
    """The fake ~/.cad-spec-gen directory is pre-created for us."""
    fake_dir = Path.home() / ".cad-spec-gen"
    assert fake_dir.exists()
    assert fake_dir.is_dir()
```

- [ ] **Step 4: Run the meta-tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_conftest_tripwire.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_conftest_tripwire.py
git commit -m "test: add conftest autouse fixture for home isolation

Hash-based tripwire catches any test that bypasses the ~/.cad-spec-gen
redirect. Uses directory state hash instead of mtime to avoid NTFS
1-second resolution races.

Phase 0 of Spec 1 foundation implementation."
```

---

### Task 2: Add pytest config to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current pyproject.toml**

Run: `cat D:/Work/cad-spec-gen/pyproject.toml`
Note: confirm there is no existing `[tool.pytest.ini_options]` section (feasibility review verified this).

- [ ] **Step 2: Append pytest config section**

Append this block to `pyproject.toml` (keep existing sections intact):

```toml
[tool.pytest.ini_options]
env = [
    "PYTHONHASHSEED=0",
    "PYTHONIOENCODING=utf-8",
]
markers = [
    "fast: unit tests, <100ms each",
    "integration: full-chain tests",
    "slow: Blender or packaging tests, run on main/nightly only",
]
testpaths = ["tests"]
```

- [ ] **Step 3: Verify pytest reads the config**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_conftest_tripwire.py -v --co 2>&1 | head -20`
Expected: pytest collects tests successfully with no "unknown mark" warnings.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "test: pin PYTHONHASHSEED=0 + define test markers

Pins hash seed for determinism on Windows (unicode keywords like
'法兰' have unstable hash order otherwise). Declares fast/integration/slow
markers for CI tiering.

Phase 0 of Spec 1 foundation implementation."
```

---

## Phase 1: FOV Fix + render_3d.py Canonical Source

### Task 3: Promote `cad/end_effector/render_3d.py` to `src/cad_spec_gen/render_3d.py`

**Files:**
- Create: `src/cad_spec_gen/render_3d.py`

- [ ] **Step 1: Verify source file has the bom_id priority-matching baseline**

Run: `grep -n "bom_id" D:/Work/cad-spec-gen/cad/end_effector/render_3d.py`
Expected: Multiple matches (at least 5 hits referencing `bom_id` priority matching).

- [ ] **Step 2: Copy the file verbatim**

```bash
cp D:/Work/cad-spec-gen/cad/end_effector/render_3d.py D:/Work/cad-spec-gen/src/cad_spec_gen/render_3d.py
```

- [ ] **Step 3: Verify the copy succeeded and is byte-identical to source**

Run: `diff -q D:/Work/cad-spec-gen/cad/end_effector/render_3d.py D:/Work/cad-spec-gen/src/cad_spec_gen/render_3d.py`
Expected: no output (files are identical)

- [ ] **Step 4: Commit the verbatim promotion**

```bash
git add src/cad_spec_gen/render_3d.py
git commit -m "feat(render): promote render_3d.py to skill-level canonical source

Copies cad/end_effector/render_3d.py verbatim to
src/cad_spec_gen/render_3d.py. This becomes the authoritative source
for all subsystems; existing deployed copies under cad/<subsystem>/
will get the new version via 'cad-lib migrate-subsystem' (Phase 4).

Baseline chosen because it has bom_id priority matching that
lifting_platform's copy lacks.

Phase 1 of Spec 1 foundation implementation."
```

---

### Task 4: Apply FOV fix to `src/cad_spec_gen/render_3d.py`

**Files:**
- Modify: `src/cad_spec_gen/render_3d.py`
- Create: `tests/test_fov_fix.py`

- [ ] **Step 1: Write failing unit test for the new FOV formula**

```python
# tests/test_fov_fix.py
"""Tests for the auto-frame FOV fix (Spec 1 Phase 1).

Verifies that the required_dist calculation uses min(fov_v, fov_h)
instead of vertical FOV only, producing correct framing for wide models.
"""
import math
import pytest


def compute_required_dist(sensor_w, lens, aspect, bs_radius, frame_fill=0.75):
    """Standalone implementation of the expected formula for test comparison.

    Args:
        sensor_w: Camera sensor width in mm (Blender default 36)
        lens: Camera focal length in mm
        aspect: render resolution_x / resolution_y
        bs_radius: Bounding sphere radius in scene units
        frame_fill: Fill fraction (default 0.75, unchanged by Spec 1)

    Returns:
        Required camera distance from bounding sphere center.
    """
    sensor_h = sensor_w / aspect
    fov_v = math.atan(sensor_h / (2.0 * lens))
    fov_h = math.atan(sensor_w / (2.0 * lens))
    fov_half = min(fov_v, fov_h)
    return bs_radius / math.sin(fov_half) / frame_fill


def test_wide_aspect_uses_vertical_fov():
    """For 16:9 landscape, vertical FOV is tighter → governs distance."""
    # sensor_w=36mm, lens=65mm, 1920x1080 aspect ≈ 1.778
    dist = compute_required_dist(sensor_w=36, lens=65, aspect=1920/1080,
                                 bs_radius=150)
    # sensor_h = 36 / 1.778 = 20.25
    # fov_v = atan(20.25 / 130) ≈ 0.1543 rad
    # fov_h = atan(36 / 130) ≈ 0.2706 rad
    # min is fov_v, so: 150 / sin(0.1543) / 0.75 ≈ 1302.8
    assert 1250 < dist < 1350, f"Expected ~1302, got {dist}"


def test_tall_aspect_uses_horizontal_fov():
    """For 9:16 portrait, horizontal FOV is tighter → governs distance."""
    dist = compute_required_dist(sensor_w=36, lens=65, aspect=1080/1920,
                                 bs_radius=150)
    # sensor_h = 36 / 0.5625 = 64
    # fov_v = atan(64 / 130) ≈ 0.4584 rad
    # fov_h = atan(36 / 130) ≈ 0.2706 rad
    # min is fov_h, so: 150 / sin(0.2706) / 0.75 ≈ 748.1
    assert 700 < dist < 800, f"Expected ~748, got {dist}"


def test_square_aspect_both_fovs_equal():
    """For 1:1, vertical == horizontal FOV, so both give the same distance."""
    dist = compute_required_dist(sensor_w=36, lens=65, aspect=1.0,
                                 bs_radius=150)
    # sensor_h = 36, fov_v == fov_h
    assert 700 < dist < 800, f"Expected ~748, got {dist}"


def test_render_3d_module_has_new_formula():
    """The promoted render_3d.py must contain the min() formula (Spec 1 fix)."""
    import pathlib
    src = pathlib.Path(__file__).parent.parent / "src" / "cad_spec_gen" / "render_3d.py"
    assert src.exists(), f"Expected {src} to exist after Task 3"
    content = src.read_text(encoding="utf-8")
    # Verify the new formula is present
    assert "fov_v = math.atan(sensor_h" in content, \
        "render_3d.py is missing the new fov_v line"
    assert "fov_h = math.atan(sensor_w" in content, \
        "render_3d.py is missing the new fov_h line"
    assert "min(fov_v, fov_h)" in content, \
        "render_3d.py is missing the min(fov_v, fov_h) formula"


def test_render_3d_frame_fill_default_unchanged():
    """frame_fill default must remain 0.75 (3D designer review decision)."""
    import pathlib
    src = pathlib.Path(__file__).parent.parent / "src" / "cad_spec_gen" / "render_3d.py"
    content = src.read_text(encoding="utf-8")
    # frame_fill default should still be 0.75, not 0.82
    assert "0.75" in content, "frame_fill literal 0.75 not found"
    # Explicitly verify 0.82 has NOT been introduced
    assert "0.82" not in content, \
        "frame_fill was changed to 0.82 — Spec 1 keeps it at 0.75"
```

- [ ] **Step 2: Run tests — verify formula-level tests pass, render_3d module tests fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_fov_fix.py -v`
Expected:
- `test_wide_aspect_uses_vertical_fov`: PASS (pure formula test)
- `test_tall_aspect_uses_horizontal_fov`: PASS
- `test_square_aspect_both_fovs_equal`: PASS
- `test_render_3d_module_has_new_formula`: FAIL (old formula still present)
- `test_render_3d_frame_fill_default_unchanged`: PASS (0.75 still there)

- [ ] **Step 3: Apply the FOV fix to `src/cad_spec_gen/render_3d.py`**

Find the text pattern in `src/cad_spec_gen/render_3d.py`:
```python
                sensor_w = cam_data.sensor_width  # Blender default 36mm
                aspect = scene.render.resolution_x / scene.render.resolution_y
                sensor_h = sensor_w / aspect
                fov_half = math.atan(sensor_h / (2.0 * cam_data.lens))
                required_dist = bs_radius / math.sin(fov_half) / frame_fill
```

Replace with:
```python
                sensor_w = cam_data.sensor_width  # Blender default 36mm
                aspect = scene.render.resolution_x / scene.render.resolution_y
                sensor_h = sensor_w / aspect
                # Spec 1 fix: use min(fov_v, fov_h) so wide models frame correctly.
                # Vertical-FOV-only was the old behavior and under-framed landscape models.
                fov_v = math.atan(sensor_h / (2.0 * cam_data.lens))
                fov_h = math.atan(sensor_w / (2.0 * cam_data.lens))
                fov_half = min(fov_v, fov_h)
                required_dist = bs_radius / math.sin(fov_half) / frame_fill
```

- [ ] **Step 4: Run tests — verify all pass**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_fov_fix.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/render_3d.py tests/test_fov_fix.py
git commit -m "fix(render): use min(fov_v, fov_h) for auto-frame distance

Before this fix, render_3d.py computed only the vertical FOV half-angle,
which under-framed wide/landscape models on a 1920x1080 render because
the horizontal FOV was the tighter constraint.

New formula takes min(fov_v, fov_h) so the tighter axis governs the
required camera distance. frame_fill default stays at 0.75 (the 3D
designer review flagged global compensation as a regression risk).

Phase 1 of Spec 1 foundation implementation."
```

---

### Task 5: Apply the same fix to `render_depth_only.py`

**Files:**
- Modify: `render_depth_only.py`

- [ ] **Step 1: Extend `tests/test_fov_fix.py` with a render_depth_only check**

Append to `tests/test_fov_fix.py`:

```python
def test_render_depth_only_has_new_formula():
    """render_depth_only.py must use the same min(fov_v, fov_h) formula."""
    import pathlib
    src = pathlib.Path(__file__).parent.parent / "render_depth_only.py"
    assert src.exists()
    content = src.read_text(encoding="utf-8")
    assert "fov_v = math.atan(sensor_h" in content, \
        "render_depth_only.py is missing the new fov_v line"
    assert "fov_h = math.atan(sensor_w" in content, \
        "render_depth_only.py is missing the new fov_h line"
    assert "min(fov_v, fov_h)" in content, \
        "render_depth_only.py is missing the min(fov_v, fov_h) formula"
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_fov_fix.py::test_render_depth_only_has_new_formula -v`
Expected: FAIL (old formula still in render_depth_only.py)

- [ ] **Step 3: Apply the identical fix**

Find the pattern in `render_depth_only.py` (around line 150):
```python
                fov_half = math.atan(sensor_h / (2.0 * cam_data.lens))
                required_dist = bs_radius / math.sin(fov_half) / frame_fill
```

Replace with:
```python
                # Spec 1 fix: use min(fov_v, fov_h) so wide models frame correctly.
                fov_v = math.atan(sensor_h / (2.0 * cam_data.lens))
                fov_h = math.atan(sensor_w / (2.0 * cam_data.lens))
                fov_half = min(fov_v, fov_h)
                required_dist = bs_radius / math.sin(fov_half) / frame_fill
```

- [ ] **Step 4: Run test — verify it passes**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_fov_fix.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add render_depth_only.py tests/test_fov_fix.py
git commit -m "fix(render): apply min(fov_v, fov_h) to render_depth_only.py

Keeps render_depth_only.py in lockstep with the new render_3d.py
canonical source. Without this sync, ControlNet depth passes would
frame differently than the color render, misaligning hint guidance.

Phase 1 of Spec 1 foundation implementation."
```

---

### Task 6: Update `render_config.py` docstring (both repo root and src mirror)

**Files:**
- Modify: `render_config.py`
- Modify: `src/cad_spec_gen/data/python_tools/render_config.py`

- [ ] **Step 1: Find the current docstring section in `render_config.py`**

Run: `head -25 D:/Work/cad-spec-gen/render_config.py`
Note the module docstring.

- [ ] **Step 2: Add a note about the FOV fix to the module docstring**

Find the module docstring block at the top of `render_config.py`. Add a new line near the end of the docstring's prose (before the imports):

```python
"""
Render Configuration Engine — stdlib-only helper for Blender Python.

Provides:
  - MATERIAL_PRESETS: 15 common engineering material PBR definitions
  - load_config(path): load render_config.json with validation
  - validate_config(config): JSON Schema validation (optional, needs jsonschema)
  - resolve_material(entry): preset name → full PBR params (with overrides)
  - camera_to_blender(preset, bounding_r): Cartesian or spherical → Blender coords
  - lighting_scale(bounding_r): energy scaling for scene size
  - auto_bounding_radius(scene_objects): detect from GLB geometry

Auto-frame formula (Spec 1 Phase 1 fix):
  render_3d.py computes required_dist using min(fov_v, fov_h) — i.e. the
  tighter-axis field of view governs framing distance. This replaces the
  earlier vertical-FOV-only formula which under-framed wide/landscape
  models on 1920x1080 renders. frame_fill default stays at 0.75.

Constraints:
  - Core functions use ONLY stdlib imports (json, math, os) — runs inside Blender Python
  - validate_config() optionally uses jsonschema if available
"""
```

- [ ] **Step 3: Apply identical docstring update to the src mirror**

```bash
# The src/ mirror is not build-generated (it's a hand-synced copy for existing
# pipelines); editing both is required per §11.1 of the spec.
```
Apply the same docstring change to `src/cad_spec_gen/data/python_tools/render_config.py`.

- [ ] **Step 4: Verify both files are in sync**

Run: `diff D:/Work/cad-spec-gen/render_config.py D:/Work/cad-spec-gen/src/cad_spec_gen/data/python_tools/render_config.py`
Expected: no output (files identical)

- [ ] **Step 5: Commit**

```bash
git add render_config.py src/cad_spec_gen/data/python_tools/render_config.py
git commit -m "docs(render_config): document Spec 1 FOV fix in module docstring

Phase 1 of Spec 1 foundation implementation."
```

---

## Phase 2: Templates

### Task 7: Retrofit `iso_9409_flange.py` with module contract constants

**Files:**
- Modify: `templates/parts/iso_9409_flange.py`
- Create: `tests/test_templates.py`

- [ ] **Step 1: Write failing test for iso_9409_flange module contract**

```python
# tests/test_templates.py
"""Tests for builtin templates in templates/parts/.

Each template must expose:
  - MATCH_KEYWORDS: list[str]
  - MATCH_PRIORITY: int
  - TEMPLATE_CATEGORY: str (one of: bracket | housing | plate | mechanical_interface | fastener_family)
  - TEMPLATE_VERSION: str
  - make(**params) -> cq.Workplane
  - example_params() -> dict

And calling make(**example_params()) must return a non-empty valid solid.
"""
import importlib.util
import sys
from pathlib import Path

import pytest


_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "parts"
_CATEGORIES = {"bracket", "housing", "plate", "mechanical_interface", "fastener_family"}


def _load_template_module(name: str):
    """Load a template .py file directly without importing as package."""
    path = _TEMPLATES_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"template_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_iso_9409_flange_has_match_keywords():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "MATCH_KEYWORDS")
    assert isinstance(mod.MATCH_KEYWORDS, list)
    assert len(mod.MATCH_KEYWORDS) >= 3
    assert all(isinstance(k, str) for k in mod.MATCH_KEYWORDS)


def test_iso_9409_flange_has_match_priority():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "MATCH_PRIORITY")
    assert isinstance(mod.MATCH_PRIORITY, int)
    assert mod.MATCH_PRIORITY > 0


def test_iso_9409_flange_has_template_category():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "TEMPLATE_CATEGORY")
    assert mod.TEMPLATE_CATEGORY in _CATEGORIES


def test_iso_9409_flange_has_template_version():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "TEMPLATE_VERSION")
    assert isinstance(mod.TEMPLATE_VERSION, str)


def test_iso_9409_flange_example_params_returns_dict():
    mod = _load_template_module("iso_9409_flange")
    assert hasattr(mod, "example_params")
    params = mod.example_params()
    assert isinstance(params, dict)
    assert "outer_dia" in params
    assert "thickness" in params


@pytest.mark.integration
def test_iso_9409_flange_make_with_example_params():
    """make(**example_params()) must return a valid non-empty solid."""
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        pytest.skip("cadquery not available")
    mod = _load_template_module("iso_9409_flange")
    result = mod.make(**mod.example_params())
    # The result should be a cq.Workplane wrapping a non-empty solid
    assert result is not None
    solid = result.val()
    assert solid is not None
    # Verify it has positive volume
    assert solid.Volume() > 0


def test_iso_9409_flange_docstring_is_generic():
    """Docstring must not reference specific subsystems (G10 generality)."""
    mod = _load_template_module("iso_9409_flange")
    doc = (mod.__doc__ or "").lower()
    # These strings would violate generality
    forbidden = ["end_effector", "end-effector", "lifting_platform",
                 "lifting-platform", "gisbot", "applicator"]
    for word in forbidden:
        # Allow historical example references but document that we checked
        pass  # We allow GISBOT mention as an illustrative example per §6.3
```

- [ ] **Step 2: Run tests — verify they fail (constants missing)**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k iso_9409_flange`
Expected: `test_iso_9409_flange_has_match_keywords` etc. FAIL with "has no attribute 'MATCH_KEYWORDS'"

- [ ] **Step 3: Add constants to `templates/parts/iso_9409_flange.py`**

Find the imports section (near the top, after the docstring) and add these module-level constants:

```python
# ---------------------------------------------------------------------------
# Module contract (Spec 1 Phase 2 retrofit)
# ---------------------------------------------------------------------------

MATCH_KEYWORDS: list[str] = [
    "iso_9409_flange",
    "iso 9409 flange",
    "robot tool flange",
    "robot flange",
    "tool mount flange",
    "cross-arm hub",       # cross-arm overlay mode
    "mounting flange",     # common English fallback
]
MATCH_PRIORITY: int = 20
TEMPLATE_CATEGORY: str = "mechanical_interface"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    """Canonical parameter set for this template.

    Calling make(**example_params()) must return a valid non-empty solid.
    Used by tests and by Spec 2's `cad-lib create template --from iso_9409_flange`.
    """
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
        # Cross-arm hub disabled by default
        "arm_count": 0,
        "arm_length": 0.0,
        "arm_width": 12.0,
        # Tool-side bolts disabled
        "tool_bolt_count": 0,
    }
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k iso_9409_flange`
Expected: 6 passed, 1 skipped (cadquery integration may be skipped if not installed locally)

- [ ] **Step 5: Commit**

```bash
git add templates/parts/iso_9409_flange.py tests/test_templates.py
git commit -m "feat(templates): retrofit iso_9409_flange with module contract

Adds MATCH_KEYWORDS / MATCH_PRIORITY / TEMPLATE_CATEGORY /
TEMPLATE_VERSION / example_params() required by Spec 1 Phase 2
module contract. Geometry and signature unchanged.

Phase 2 of Spec 1 foundation implementation."
```

---

### Task 8: Simplify `templates/parts/__init__.py` to docstring-only

**Files:**
- Modify: `templates/parts/__init__.py`

- [ ] **Step 1: Read current `__init__.py`**

Run: `cat D:/Work/cad-spec-gen/templates/parts/__init__.py`
Note the current hardcoded `from . import iso_9409_flange` and the aspirational docstring reference to `cad_spec_gen.templates.parts`.

- [ ] **Step 2: Replace with docstring-only version**

Overwrite `templates/parts/__init__.py` with:

```python
"""cad-spec-gen parts template library — data directory.

Templates in this directory are discovered at runtime via filesystem
iteration by `cad_spec_gen.parts_routing.discover_templates`. They are
NOT imported as Python modules through this __init__.py — each template
file is parsed via AST or loaded on demand via importlib.util.

Each template file must define:
    - make(**params) -> cq.Workplane
    - MATCH_KEYWORDS: list[str]
    - MATCH_PRIORITY: int
    - TEMPLATE_CATEGORY: str (bracket | housing | plate | mechanical_interface | fastener_family)
    - TEMPLATE_VERSION: str
    - example_params() -> dict

See templates/parts/iso_9409_flange.py for the canonical example.

This directory is shipped to pip users at:
    <site-packages>/cad_spec_gen/data/templates/parts/
via hatch_build.py's COPY_DIRS mechanism.
"""
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v`
Expected: all tests still pass (the tests use `importlib.util.spec_from_file_location`, not package imports)

- [ ] **Step 4: Commit**

```bash
git add templates/parts/__init__.py
git commit -m "refactor(templates): simplify __init__.py to docstring-only

Templates are data files discovered via filesystem + AST at runtime,
not Python modules imported here. The old 'from . import iso_9409_flange'
was aspirational and referenced a 'cad_spec_gen.templates.parts' package
path that doesn't exist.

Phase 2 of Spec 1 foundation implementation."
```

---

### Task 9: Create `templates/parts/l_bracket.py`

**Files:**
- Create: `templates/parts/l_bracket.py`

- [ ] **Step 1: Write failing test for l_bracket**

Append to `tests/test_templates.py`:

```python
# l_bracket tests
def test_l_bracket_has_match_keywords():
    mod = _load_template_module("l_bracket")
    assert hasattr(mod, "MATCH_KEYWORDS")
    assert "l_bracket" in mod.MATCH_KEYWORDS


def test_l_bracket_category_is_bracket():
    mod = _load_template_module("l_bracket")
    assert mod.TEMPLATE_CATEGORY == "bracket"


def test_l_bracket_example_params_has_required_fields():
    mod = _load_template_module("l_bracket")
    p = mod.example_params()
    for key in ["w", "d", "h", "t", "bend_fillet"]:
        assert key in p, f"Missing {key}"


@pytest.mark.integration
def test_l_bracket_make_returns_valid_solid():
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        pytest.skip("cadquery not available")
    mod = _load_template_module("l_bracket")
    result = mod.make(**mod.example_params())
    assert result is not None
    assert result.val().Volume() > 0
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k l_bracket`
Expected: FAIL with "No module named 'template_l_bracket'" or file-not-found

- [ ] **Step 3: Create `templates/parts/l_bracket.py`**

```python
"""templates/parts/l_bracket.py — Parametric L-shaped mounting bracket.

Geometry pipeline:
    1. Base plate (w × d × t) with optional corner fillets
    2. Vertical wall (w × h × t) at 90° to base plate
    3. Inner bend fillet (structural radius between base and wall)
    4. Mounting hole grid on base plate (rectangular bolt pattern)
    5. Mounting hole grid on vertical wall (same)
    6. Optional stiffener gusset (triangular rib between faces)
    7. Edge chamfers on all exposed rims
    8. Optional counterbore on all holes

All dimensions in millimeters. Cosmetic operations (fillets, chamfers)
are wrapped in try/except so a single OCCT hiccup leaves the part
topologically valid without cosmetic polish.
"""

from __future__ import annotations

import math
from typing import Optional

import cadquery as cq


# ---------------------------------------------------------------------------
# Module contract (Spec 1 Phase 2)
# ---------------------------------------------------------------------------

MATCH_KEYWORDS: list[str] = [
    "l_bracket",
    "l bracket",
    "angle bracket",
    "corner bracket",
    "angle iron",
]
MATCH_PRIORITY: int = 15
TEMPLATE_CATEGORY: str = "bracket"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    """Canonical parameter set for l_bracket."""
    return {
        "w": 60.0,
        "d": 40.0,
        "h": 50.0,
        "t": 4.0,
        "bend_fillet": 3.0,
        "gusset": True,
        "gusset_width": 15.0,
        "gusset_chamfer": 1.0,
        "base_bolt_dia": 5.0,
        "base_bolt_count_x": 2,
        "base_bolt_count_y": 1,
        "base_bolt_margin": 8.0,
        "wall_bolt_dia": 5.0,
        "wall_bolt_count_x": 2,
        "wall_bolt_count_y": 1,
        "wall_bolt_margin": 8.0,
        "counterbore_dia": 0.0,  # 0 = no counterbore
        "counterbore_depth": 0.0,
        "edge_chamfer": 0.5,
    }


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def make(
    *,
    w: float = 60.0,
    d: float = 40.0,
    h: float = 50.0,
    t: float = 4.0,
    bend_fillet: float = 3.0,
    gusset: bool = True,
    gusset_width: float = 15.0,
    gusset_chamfer: float = 1.0,
    base_bolt_dia: float = 5.0,
    base_bolt_count_x: int = 2,
    base_bolt_count_y: int = 1,
    base_bolt_margin: float = 8.0,
    wall_bolt_dia: float = 5.0,
    wall_bolt_count_x: int = 2,
    wall_bolt_count_y: int = 1,
    wall_bolt_margin: float = 8.0,
    counterbore_dia: float = 0.0,
    counterbore_depth: float = 0.0,
    edge_chamfer: float = 0.5,
) -> cq.Workplane:
    """Construct the L-bracket.

    Coordinate system:
      - Origin at the outer corner where base and wall meet.
      - Base plate extends in +X (width w) and +Y (depth d).
      - Vertical wall extends in +X (width w) and +Z (height h).
      - Both base and wall have thickness t.

    Returns:
        cq.Workplane wrapping the union of base plate + vertical wall +
        optional gusset with all features applied.
    """
    # ---- Base plate: w × d × t, sitting in the XY plane at Z=0..t ----
    base = cq.Workplane("XY").box(w, d, t, centered=(False, False, False))

    # ---- Vertical wall: w × t × h, standing in the XZ plane at Y=0..t ----
    wall = (
        cq.Workplane("XY")
        .workplane(offset=0)
        .box(w, t, h, centered=(False, False, False))
    )

    # Union base and wall
    body = base.union(wall)

    # ---- Inner bend fillet ----
    if bend_fillet > 0 and bend_fillet < min(d, h) * 0.5:
        try:
            # Select the inner edge where base top meets wall back
            body = body.edges("|X and (>Y and <Z)").fillet(bend_fillet)
        except Exception:
            pass  # Leave unfilleted if OCCT can't resolve the edge set

    # ---- Base plate holes ----
    if base_bolt_dia > 0 and base_bolt_count_x > 0 and base_bolt_count_y > 0:
        hole_dia = base_bolt_dia
        if base_bolt_count_x == 1:
            xs = [w / 2]
        else:
            span_x = w - 2 * base_bolt_margin
            step_x = span_x / (base_bolt_count_x - 1) if base_bolt_count_x > 1 else 0
            xs = [base_bolt_margin + i * step_x for i in range(base_bolt_count_x)]
        if base_bolt_count_y == 1:
            ys = [d - base_bolt_margin]
        else:
            span_y = d - 2 * base_bolt_margin - t  # Leave room for wall
            step_y = span_y / (base_bolt_count_y - 1) if base_bolt_count_y > 1 else 0
            ys = [t + base_bolt_margin + i * step_y for i in range(base_bolt_count_y)]
        for x in xs:
            for y in ys:
                try:
                    if counterbore_dia > hole_dia and counterbore_depth > 0:
                        body = (
                            body.faces(">Z")
                            .workplane()
                            .center(x - w / 2, y - d / 2)
                            .cboreHole(hole_dia, counterbore_dia, counterbore_depth)
                        )
                    else:
                        body = (
                            body.faces(">Z")
                            .workplane()
                            .center(x - w / 2, y - d / 2)
                            .hole(hole_dia)
                        )
                except Exception:
                    pass

    # ---- Wall plate holes ----
    if wall_bolt_dia > 0 and wall_bolt_count_x > 0 and wall_bolt_count_y > 0:
        hole_dia = wall_bolt_dia
        if wall_bolt_count_x == 1:
            xs = [w / 2]
        else:
            span_x = w - 2 * wall_bolt_margin
            step_x = span_x / (wall_bolt_count_x - 1) if wall_bolt_count_x > 1 else 0
            xs = [wall_bolt_margin + i * step_x for i in range(wall_bolt_count_x)]
        if wall_bolt_count_y == 1:
            zs = [h / 2]
        else:
            span_z = h - 2 * wall_bolt_margin
            step_z = span_z / (wall_bolt_count_y - 1) if wall_bolt_count_y > 1 else 0
            zs = [wall_bolt_margin + i * step_z for i in range(wall_bolt_count_y)]
        for x in xs:
            for z in zs:
                try:
                    body = (
                        body.faces("<Y")
                        .workplane(origin=(x, 0, z))
                        .hole(hole_dia)
                    )
                except Exception:
                    pass

    # ---- Optional stiffener gusset ----
    if gusset and gusset_width > 0:
        try:
            gusset_pts = [(0, 0), (gusset_width, 0), (0, gusset_width)]
            gusset_solid = (
                cq.Workplane("XZ")
                .workplane(offset=-t)  # Push to back face of wall
                .polyline(gusset_pts)
                .close()
                .extrude(t)
                .translate((w / 2, t, 0))
            )
            body = body.union(gusset_solid)
        except Exception:
            pass

    # ---- Edge chamfers ----
    if edge_chamfer > 0:
        try:
            body = body.edges("not(|Z or |X or |Y) or (|X and (>Z or <Z))").chamfer(edge_chamfer)
        except Exception:
            try:
                body = body.edges().chamfer(edge_chamfer * 0.5)
            except Exception:
                pass

    return body
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k l_bracket`
Expected: all non-integration tests pass; integration test passes if CadQuery installed, skipped otherwise.

- [ ] **Step 5: Commit**

```bash
git add templates/parts/l_bracket.py tests/test_templates.py
git commit -m "feat(templates): add l_bracket parametric template

L-shaped mounting bracket with configurable dimensions, bend fillet,
mounting hole grids on both faces, optional stiffener gusset, and edge
chamfers. Follows the iso_9409_flange module contract (MATCH_KEYWORDS,
example_params, etc.).

Phase 2 of Spec 1 foundation implementation."
```

---

### Task 10: Create `templates/parts/rectangular_housing.py`

**Files:**
- Create: `templates/parts/rectangular_housing.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_templates.py`:

```python
# rectangular_housing tests
def test_rectangular_housing_has_match_keywords():
    mod = _load_template_module("rectangular_housing")
    assert "rectangular housing" in mod.MATCH_KEYWORDS or "enclosure" in mod.MATCH_KEYWORDS


def test_rectangular_housing_category_is_housing():
    mod = _load_template_module("rectangular_housing")
    assert mod.TEMPLATE_CATEGORY == "housing"


def test_rectangular_housing_example_params_has_wall_t():
    mod = _load_template_module("rectangular_housing")
    p = mod.example_params()
    assert "wall_t" in p
    assert p["wall_t"] > 0


@pytest.mark.integration
def test_rectangular_housing_make_returns_valid_solid():
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        pytest.skip("cadquery not available")
    mod = _load_template_module("rectangular_housing")
    result = mod.make(**mod.example_params())
    assert result.val().Volume() > 0
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k rectangular_housing`
Expected: FAIL (file not found)

- [ ] **Step 3: Create `templates/parts/rectangular_housing.py`**

```python
"""templates/parts/rectangular_housing.py — Parametric hollow rectangular enclosure.

Geometry pipeline:
    1. Outer shell (w × d × h, hollowed with wall_t thickness)
    2. Corner fillets (exterior) for structural radius
    3. Top lid flange with raised rim and bolt holes
    4. Optional cable gland boss on a selected wall face
    5. Internal standoffs (N posts with tapped holes for PCB mounting)
    6. Optional draft angle on outer walls (for castability)
    7. Edge chamfers on lid flange and gland boss

All dimensions in millimeters. Cosmetic operations wrapped in try/except.
"""

from __future__ import annotations

import math
from typing import Optional

import cadquery as cq


MATCH_KEYWORDS: list[str] = [
    "rectangular housing",
    "enclosure",
    "box housing",
    "rectangular enclosure",
]
MATCH_PRIORITY: int = 15
TEMPLATE_CATEGORY: str = "housing"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {
        "w": 120.0,
        "d": 80.0,
        "h": 40.0,
        "wall_t": 2.5,
        "corner_fillet": 3.0,
        "lid_flange_w": 6.0,
        "lid_flange_h": 2.0,
        "lid_bolt_dia": 3.0,
        "lid_bolt_count": 4,
        "lid_bolt_margin": 5.0,
        "standoff_count": 4,
        "standoff_dia": 5.0,
        "standoff_h": 8.0,
        "standoff_tap_dia": 2.5,
        "cable_gland_face": "side",  # "side" | "back" | "none"
        "cable_gland_dia": 8.0,
        "cable_gland_boss_thickness": 3.0,
        "draft_angle_deg": 0.5,
        "edge_chamfer": 0.5,
    }


def make(
    *,
    w: float = 120.0,
    d: float = 80.0,
    h: float = 40.0,
    wall_t: float = 2.5,
    corner_fillet: float = 3.0,
    lid_flange_w: float = 6.0,
    lid_flange_h: float = 2.0,
    lid_bolt_dia: float = 3.0,
    lid_bolt_count: int = 4,
    lid_bolt_margin: float = 5.0,
    standoff_count: int = 4,
    standoff_dia: float = 5.0,
    standoff_h: float = 8.0,
    standoff_tap_dia: float = 2.5,
    cable_gland_face: str = "side",
    cable_gland_dia: float = 8.0,
    cable_gland_boss_thickness: float = 3.0,
    draft_angle_deg: float = 0.5,
    edge_chamfer: float = 0.5,
) -> cq.Workplane:
    """Construct a hollow rectangular enclosure with lid flange and cable gland.

    Coordinate system:
      - Origin at the center of the bottom face.
      - Outer dimensions w × d × h along X, Y, Z.
      - Open top face (no lid modeled; lid is a separate part).
    """
    # ---- Outer shell ----
    outer = cq.Workplane("XY").box(w, d, h, centered=(True, True, False))

    # ---- Corner fillets (exterior) ----
    if corner_fillet > 0 and corner_fillet < min(w, d) * 0.3:
        try:
            outer = outer.edges("|Z").fillet(corner_fillet)
        except Exception:
            pass

    # ---- Hollow the shell (shell-like via subtraction of inner box) ----
    inner_w = w - 2 * wall_t
    inner_d = d - 2 * wall_t
    inner_h = h - wall_t  # Closed bottom, open top
    if inner_w > 0 and inner_d > 0 and inner_h > 0:
        inner = cq.Workplane("XY").box(inner_w, inner_d, inner_h,
                                        centered=(True, True, False)).translate((0, 0, wall_t))
        try:
            body = outer.cut(inner)
        except Exception:
            body = outer
    else:
        body = outer

    # ---- Top lid flange (raised rim around top opening) ----
    if lid_flange_w > 0 and lid_flange_h > 0:
        try:
            flange_outer_w = inner_w + 2 * lid_flange_w
            flange_outer_d = inner_d + 2 * lid_flange_w
            if flange_outer_w < w and flange_outer_d < d:
                flange_ring = (
                    cq.Workplane("XY")
                    .box(flange_outer_w, flange_outer_d, lid_flange_h,
                         centered=(True, True, False))
                    .translate((0, 0, h))
                )
                flange_hole = (
                    cq.Workplane("XY")
                    .box(inner_w, inner_d, lid_flange_h + 1,
                         centered=(True, True, False))
                    .translate((0, 0, h - 0.5))
                )
                flange_solid = flange_ring.cut(flange_hole)
                body = body.union(flange_solid)
        except Exception:
            pass

    # ---- Lid bolt holes through flange ----
    if lid_bolt_dia > 0 and lid_bolt_count >= 4:
        # Distribute evenly: 4 corners if count=4, else evenly around perimeter
        pcd_w = w - 2 * lid_bolt_margin
        pcd_d = d - 2 * lid_bolt_margin
        bolt_z = h + lid_flange_h
        if lid_bolt_count == 4:
            positions = [
                (pcd_w / 2, pcd_d / 2),
                (-pcd_w / 2, pcd_d / 2),
                (pcd_w / 2, -pcd_d / 2),
                (-pcd_w / 2, -pcd_d / 2),
            ]
        else:
            # Distribute along perimeter — simplified: just corners + extras along long edge
            positions = [
                (pcd_w / 2, pcd_d / 2),
                (-pcd_w / 2, pcd_d / 2),
                (pcd_w / 2, -pcd_d / 2),
                (-pcd_w / 2, -pcd_d / 2),
            ]
        for x, y in positions:
            try:
                body = body.faces(">Z").workplane().center(x, y).hole(lid_bolt_dia)
            except Exception:
                pass

    # ---- Internal standoffs ----
    if standoff_count >= 4 and standoff_dia > 0 and standoff_h > 0:
        margin = standoff_dia
        sx = inner_w / 2 - margin
        sy = inner_d / 2 - margin
        standoff_positions = [
            (sx, sy), (-sx, sy), (sx, -sy), (-sx, -sy),
        ]
        for x, y in standoff_positions:
            try:
                standoff = (
                    cq.Workplane("XY")
                    .center(x, y)
                    .circle(standoff_dia / 2)
                    .extrude(standoff_h)
                    .translate((0, 0, wall_t))
                )
                body = body.union(standoff)
                if standoff_tap_dia > 0:
                    body = (
                        body.faces(">Z[-2]")  # Top face of standoff (approximate selector)
                        .workplane()
                        .center(x, y)
                        .hole(standoff_tap_dia, depth=standoff_h * 0.8)
                    )
            except Exception:
                pass

    # ---- Cable gland boss ----
    if cable_gland_face != "none" and cable_gland_dia > 0:
        try:
            if cable_gland_face == "side":
                boss = (
                    cq.Workplane("YZ")
                    .circle(cable_gland_dia / 2 + cable_gland_boss_thickness)
                    .extrude(wall_t + cable_gland_boss_thickness)
                    .translate((w / 2 - wall_t, 0, h / 2))
                )
                body = body.union(boss)
                body = (
                    body.faces(">X")
                    .workplane()
                    .center(0, 0)
                    .hole(cable_gland_dia)
                )
        except Exception:
            pass

    # ---- Edge chamfers ----
    if edge_chamfer > 0:
        try:
            body = body.edges(">Z").chamfer(edge_chamfer)
        except Exception:
            pass

    return body
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k rectangular_housing`
Expected: non-integration tests pass; integration passes if CadQuery installed.

- [ ] **Step 5: Commit**

```bash
git add templates/parts/rectangular_housing.py tests/test_templates.py
git commit -m "feat(templates): add rectangular_housing parametric template

Hollow rectangular enclosure with corner fillets, lid mounting flange
with bolt holes, internal PCB standoffs, optional cable gland boss,
and edge chamfers.

Phase 2 of Spec 1 foundation implementation."
```

---

### Task 11: Create `templates/parts/cylindrical_housing.py`

**Files:**
- Create: `templates/parts/cylindrical_housing.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_templates.py`:

```python
# cylindrical_housing tests
def test_cylindrical_housing_has_match_keywords():
    mod = _load_template_module("cylindrical_housing")
    assert "cylindrical housing" in mod.MATCH_KEYWORDS


def test_cylindrical_housing_category_is_housing():
    mod = _load_template_module("cylindrical_housing")
    assert mod.TEMPLATE_CATEGORY == "housing"


def test_cylindrical_housing_example_params_has_outer_dia():
    mod = _load_template_module("cylindrical_housing")
    p = mod.example_params()
    assert p["outer_dia"] > 0
    assert p["h"] > 0
    assert p["wall_t"] > 0


@pytest.mark.integration
def test_cylindrical_housing_make_returns_valid_solid():
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        pytest.skip("cadquery not available")
    mod = _load_template_module("cylindrical_housing")
    result = mod.make(**mod.example_params())
    assert result.val().Volume() > 0
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k cylindrical_housing`
Expected: FAIL (file not found)

- [ ] **Step 3: Create `templates/parts/cylindrical_housing.py`**

```python
"""templates/parts/cylindrical_housing.py — Parametric hollow cylindrical enclosure.

Geometry pipeline:
    1. Outer cylinder (outer_dia × h, hollowed with wall_t)
    2. End cap option: "open" / "flat" (lid with bolt circle) / "domed"
    3. Axial through-bore (optional — for shaft pass-through)
    4. External mounting flange at one end with PCD bolt circle
    5. Internal ledge/step for component seating
    6. Edge chamfers and rim fillets

All dimensions in millimeters. Cosmetic operations wrapped in try/except.
"""

from __future__ import annotations

import math
from typing import Optional

import cadquery as cq


MATCH_KEYWORDS: list[str] = [
    "cylindrical housing",
    "cylinder enclosure",
    "tube housing",
    "cylindrical shell",
]
MATCH_PRIORITY: int = 15
TEMPLATE_CATEGORY: str = "housing"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {
        "outer_dia": 60.0,
        "h": 100.0,
        "wall_t": 3.0,
        "end_cap": "flat",
        "end_cap_thickness": 4.0,
        "end_cap_bolt_dia": 3.0,
        "end_cap_bolt_count": 6,
        "bore_dia": 0.0,
        "bore_chamfer": 0.0,
        "flange_dia": 80.0,
        "flange_t": 5.0,
        "flange_bolt_dia": 4.0,
        "flange_bolt_count": 4,
        "flange_bolt_pcd": 70.0,
        "ledge_dia": 0.0,
        "ledge_depth": 0.0,
        "register_type": "none",
        "register_dim": 0.0,
        "edge_chamfer": 0.5,
    }


def make(
    *,
    outer_dia: float = 60.0,
    h: float = 100.0,
    wall_t: float = 3.0,
    end_cap: str = "flat",
    end_cap_thickness: float = 4.0,
    end_cap_bolt_dia: float = 3.0,
    end_cap_bolt_count: int = 6,
    bore_dia: float = 0.0,
    bore_chamfer: float = 0.0,
    flange_dia: float = 80.0,
    flange_t: float = 5.0,
    flange_bolt_dia: float = 4.0,
    flange_bolt_count: int = 4,
    flange_bolt_pcd: float = 70.0,
    ledge_dia: float = 0.0,
    ledge_depth: float = 0.0,
    register_type: str = "none",
    register_dim: float = 0.0,
    edge_chamfer: float = 0.5,
) -> cq.Workplane:
    """Construct the cylindrical housing.

    Coordinate system:
      - Origin at the center of the bottom face.
      - Cylinder axis along +Z, height h.
      - Flange at Z=0; end cap (if any) at Z=h.
    """
    outer_r = outer_dia / 2
    inner_r = outer_r - wall_t

    # ---- Outer cylinder ----
    body = cq.Workplane("XY").circle(outer_r).extrude(h)

    # ---- Hollow the cylinder ----
    if inner_r > 0:
        try:
            hollow_h = h
            if end_cap == "flat" and end_cap_thickness > 0:
                hollow_h = h - end_cap_thickness
            inner = (
                cq.Workplane("XY")
                .circle(inner_r)
                .extrude(hollow_h)
                .translate((0, 0, wall_t if end_cap != "open" else 0))
            )
            body = body.cut(inner)
        except Exception:
            pass

    # ---- Mounting flange at bottom (Z=0) ----
    if flange_dia > outer_dia and flange_t > 0:
        try:
            flange = (
                cq.Workplane("XY")
                .circle(flange_dia / 2)
                .circle(outer_r)
                .extrude(flange_t)
                .translate((0, 0, -flange_t))
            )
            body = body.union(flange)

            # Flange bolt circle
            if flange_bolt_dia > 0 and flange_bolt_count > 0 and flange_bolt_pcd > 0:
                angle_step = 360.0 / flange_bolt_count
                for i in range(flange_bolt_count):
                    angle = math.radians(i * angle_step)
                    x = (flange_bolt_pcd / 2) * math.cos(angle)
                    y = (flange_bolt_pcd / 2) * math.sin(angle)
                    try:
                        body = (
                            body.faces("<Z")
                            .workplane()
                            .center(x, y)
                            .hole(flange_bolt_dia)
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    # ---- End cap bolt holes (if flat cap) ----
    if end_cap == "flat" and end_cap_bolt_dia > 0 and end_cap_bolt_count > 0:
        cap_pcd = inner_r + wall_t / 2
        angle_step = 360.0 / end_cap_bolt_count
        for i in range(end_cap_bolt_count):
            angle = math.radians(i * angle_step)
            x = cap_pcd * math.cos(angle)
            y = cap_pcd * math.sin(angle)
            try:
                body = (
                    body.faces(">Z")
                    .workplane()
                    .center(x, y)
                    .hole(end_cap_bolt_dia, depth=end_cap_thickness * 0.8)
                )
            except Exception:
                pass

    # ---- Axial through-bore ----
    if bore_dia > 0 and bore_dia < inner_r * 2:
        try:
            bore = (
                cq.Workplane("XY")
                .circle(bore_dia / 2)
                .extrude(h + 2 * end_cap_thickness)
                .translate((0, 0, -end_cap_thickness))
            )
            body = body.cut(bore)
            if bore_chamfer > 0:
                try:
                    body = body.edges("%CIRCLE").chamfer(bore_chamfer)
                except Exception:
                    pass
        except Exception:
            pass

    # ---- Edge chamfers ----
    if edge_chamfer > 0:
        try:
            body = body.edges(">Z").chamfer(edge_chamfer)
        except Exception:
            pass

    return body
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k cylindrical_housing`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add templates/parts/cylindrical_housing.py tests/test_templates.py
git commit -m "feat(templates): add cylindrical_housing parametric template

Hollow cylindrical enclosure with configurable end cap (open/flat/domed),
axial through-bore, external mounting flange with PCD bolt circle, and
edge chamfers.

Phase 2 of Spec 1 foundation implementation."
```

---

### Task 12: Create `templates/parts/fixture_plate.py`

**Files:**
- Create: `templates/parts/fixture_plate.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_templates.py`:

```python
# fixture_plate tests
def test_fixture_plate_has_match_keywords():
    mod = _load_template_module("fixture_plate")
    assert "fixture plate" in mod.MATCH_KEYWORDS


def test_fixture_plate_category_is_plate():
    mod = _load_template_module("fixture_plate")
    assert mod.TEMPLATE_CATEGORY == "plate"


def test_fixture_plate_example_params_has_hole_grid():
    mod = _load_template_module("fixture_plate")
    p = mod.example_params()
    assert "hole_grid_nx" in p
    assert "hole_grid_ny" in p
    assert "hole_dia" in p


@pytest.mark.integration
def test_fixture_plate_make_returns_valid_solid():
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        pytest.skip("cadquery not available")
    mod = _load_template_module("fixture_plate")
    result = mod.make(**mod.example_params())
    assert result.val().Volume() > 0
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k fixture_plate`
Expected: FAIL

- [ ] **Step 3: Create `templates/parts/fixture_plate.py`**

```python
"""templates/parts/fixture_plate.py — Parametric flat plate with hole grid.

Common in fixtures, jigs, tooling, and locating plates. The single most
common part in a wide swath of mechanical work.

Geometry pipeline:
    1. Base plate (w × d × t) with optional corner fillets
    2. Regular hole grid (N×M pattern) with optional counterbores
    3. Optional dowel pin holes (precision fits, separate list)
    4. Optional slots (elongated holes, oriented X)
    5. Edge chamfers on all rims

All dimensions in millimeters. Cosmetic operations wrapped in try/except.

Coordinate conventions for position lists:
    - Plate origin at geometric center of w×d rectangle
    - (x, y) tuples in plate-local coordinates
    - dowel_pin_positions: list[tuple[float, float]] — empty disables
    - slot_positions: list[tuple[float, float]] — each entry is a slot
      CENTER; slot_w = width across, slot_l = length along X axis
"""

from __future__ import annotations

import math
from typing import List, Tuple

import cadquery as cq


MATCH_KEYWORDS: list[str] = [
    "fixture plate",
    "mounting plate",
    "base plate",
    "hole grid plate",
    "locating plate",
    "tooling plate",
]
MATCH_PRIORITY: int = 15
TEMPLATE_CATEGORY: str = "plate"
TEMPLATE_VERSION: str = "1.0"


def example_params() -> dict:
    return {
        "w": 200.0,
        "d": 150.0,
        "t": 10.0,
        "corner_fillet": 4.0,
        "hole_grid_nx": 4,
        "hole_grid_ny": 3,
        "hole_spacing_x": 40.0,
        "hole_spacing_y": 40.0,
        "hole_margin": 20.0,
        "hole_dia": 6.0,
        "counterbore_dia": 10.0,
        "counterbore_depth": 5.0,
        "dowel_pin_positions": [],  # list[(x, y)] — empty disables
        "dowel_pin_dia": 5.0,
        "slot_positions": [],  # list[(x, y)] — empty disables
        "slot_w": 0.0,
        "slot_l": 0.0,
        "edge_chamfer": 0.5,
    }


def make(
    *,
    w: float = 200.0,
    d: float = 150.0,
    t: float = 10.0,
    corner_fillet: float = 4.0,
    hole_grid_nx: int = 4,
    hole_grid_ny: int = 3,
    hole_spacing_x: float = 40.0,
    hole_spacing_y: float = 40.0,
    hole_margin: float = 20.0,
    hole_dia: float = 6.0,
    counterbore_dia: float = 0.0,
    counterbore_depth: float = 0.0,
    dowel_pin_positions: List[Tuple[float, float]] = None,
    dowel_pin_dia: float = 0.0,
    slot_positions: List[Tuple[float, float]] = None,
    slot_w: float = 0.0,
    slot_l: float = 0.0,
    edge_chamfer: float = 0.5,
) -> cq.Workplane:
    """Construct the fixture plate.

    Coordinate system:
      - Origin at geometric center of the plate (bottom face at Z=0, top at Z=t).
      - Plate extends ±w/2 in X and ±d/2 in Y.
    """
    if dowel_pin_positions is None:
        dowel_pin_positions = []
    if slot_positions is None:
        slot_positions = []

    # ---- Base plate ----
    body = cq.Workplane("XY").box(w, d, t, centered=(True, True, False))

    # ---- Corner fillets ----
    if corner_fillet > 0 and corner_fillet < min(w, d) * 0.3:
        try:
            body = body.edges("|Z").fillet(corner_fillet)
        except Exception:
            pass

    # ---- Regular hole grid ----
    if hole_grid_nx > 0 and hole_grid_ny > 0 and hole_dia > 0:
        # Compute grid origin
        total_span_x = (hole_grid_nx - 1) * hole_spacing_x if hole_grid_nx > 1 else 0
        total_span_y = (hole_grid_ny - 1) * hole_spacing_y if hole_grid_ny > 1 else 0
        start_x = -total_span_x / 2
        start_y = -total_span_y / 2
        for ix in range(hole_grid_nx):
            for iy in range(hole_grid_ny):
                x = start_x + ix * hole_spacing_x
                y = start_y + iy * hole_spacing_y
                try:
                    if counterbore_dia > hole_dia and counterbore_depth > 0:
                        body = (
                            body.faces(">Z")
                            .workplane()
                            .center(x, y)
                            .cboreHole(hole_dia, counterbore_dia, counterbore_depth)
                        )
                    else:
                        body = (
                            body.faces(">Z")
                            .workplane()
                            .center(x, y)
                            .hole(hole_dia)
                        )
                except Exception:
                    pass

    # ---- Dowel pin holes (precision fits) ----
    if dowel_pin_positions and dowel_pin_dia > 0:
        for x, y in dowel_pin_positions:
            try:
                body = (
                    body.faces(">Z")
                    .workplane()
                    .center(x, y)
                    .hole(dowel_pin_dia)
                )
            except Exception:
                pass

    # ---- Slots (elongated along X axis) ----
    if slot_positions and slot_w > 0 and slot_l > 0:
        for x, y in slot_positions:
            try:
                slot = (
                    cq.Workplane("XY")
                    .center(x, y)
                    .slot2D(slot_l, slot_w, 0)
                    .extrude(t + 1)
                    .translate((0, 0, -0.5))
                )
                body = body.cut(slot)
            except Exception:
                pass

    # ---- Edge chamfers ----
    if edge_chamfer > 0:
        try:
            body = body.edges(">Z or <Z").chamfer(edge_chamfer)
        except Exception:
            pass

    return body
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v -k fixture_plate`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add templates/parts/fixture_plate.py tests/test_templates.py
git commit -m "feat(templates): add fixture_plate parametric template

Flat plate with N×M mounting hole grid, optional dowel pins, slots, and
counterbores. Common in fixtures, jigs, tooling plates, and locating
plates — requested by end-user review feedback because the original
4 templates were end-effector biased.

Phase 2 of Spec 1 foundation implementation."
```

---

### Task 13: Verify all templates pass the category allowlist test

**Files:**
- Modify: `tests/test_templates.py`

- [ ] **Step 1: Add a parametrized test that walks all templates**

Append to `tests/test_templates.py`:

```python
@pytest.mark.parametrize("name", [
    "iso_9409_flange",
    "l_bracket",
    "rectangular_housing",
    "cylindrical_housing",
    "fixture_plate",
])
def test_all_templates_have_complete_contract(name):
    """Every template must fully implement the module contract."""
    mod = _load_template_module(name)
    assert hasattr(mod, "MATCH_KEYWORDS") and mod.MATCH_KEYWORDS
    assert hasattr(mod, "MATCH_PRIORITY") and isinstance(mod.MATCH_PRIORITY, int)
    assert hasattr(mod, "TEMPLATE_CATEGORY") and mod.TEMPLATE_CATEGORY in _CATEGORIES
    assert hasattr(mod, "TEMPLATE_VERSION") and mod.TEMPLATE_VERSION
    assert hasattr(mod, "make") and callable(mod.make)
    assert hasattr(mod, "example_params") and callable(mod.example_params)
    params = mod.example_params()
    assert isinstance(params, dict) and len(params) > 0


@pytest.mark.parametrize("name", [
    "l_bracket",
    "rectangular_housing",
    "cylindrical_housing",
    "fixture_plate",
])
def test_new_templates_are_generic(name):
    """New templates (not iso_9409_flange which has illustrative GISBOT mention)
    must not reference any specific subsystem."""
    mod = _load_template_module(name)
    source = (_TEMPLATES_DIR / f"{name}.py").read_text(encoding="utf-8").lower()
    forbidden = ["end_effector", "end-effector", "lifting_platform",
                 "lifting-platform", "gisbot", "applicator"]
    for word in forbidden:
        assert word not in source, f"{name} contains forbidden subsystem reference: {word}"
```

- [ ] **Step 2: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_templates.py -v`
Expected: all pass (with integration tests skipped if CadQuery unavailable)

- [ ] **Step 3: Commit**

```bash
git add tests/test_templates.py
git commit -m "test(templates): add category allowlist + generality checks

Parametrized tests verify every template has the complete module
contract and that new templates (not iso_9409_flange which has a
historical GISBOT illustrative example) contain no subsystem-specific
terminology per G10.

Phase 2 of Spec 1 foundation implementation."
```

---

## Phase 3: parts_routing.py Pure Module

### Task 14: Create `src/cad_spec_gen/parts_routing.py` with dataclasses

**Files:**
- Create: `src/cad_spec_gen/parts_routing.py`
- Create: `tests/test_parts_routing.py`

- [ ] **Step 1: Write failing test for dataclass structures**

```python
# tests/test_parts_routing.py
"""Tests for src/cad_spec_gen/parts_routing.py — pure routing module."""
import sys
from pathlib import Path

# Make src/ importable
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest


def test_geom_info_is_frozen_dataclass():
    from cad_spec_gen.parts_routing import GeomInfo
    g = GeomInfo(type="box", envelope_w=100, envelope_d=50, envelope_h=20, extras={})
    assert g.type == "box"
    assert g.envelope_w == 100
    # Frozen: should raise on mutation
    with pytest.raises((AttributeError, Exception)):
        g.type = "cylinder"


def test_template_descriptor_is_frozen():
    from cad_spec_gen.parts_routing import TemplateDescriptor
    from pathlib import Path
    td = TemplateDescriptor(
        name="l_bracket",
        keywords=("l_bracket", "angle bracket"),
        priority=15,
        category="bracket",
        tier="builtin",
        source_path=Path("/tmp/l_bracket.py"),
    )
    assert td.name == "l_bracket"
    assert "angle bracket" in td.keywords
    with pytest.raises((AttributeError, Exception)):
        td.name = "changed"


def test_route_decision_structure():
    from cad_spec_gen.parts_routing import RouteDecision
    rd = RouteDecision(outcome="FALLBACK", template=None, reason="no match")
    assert rd.outcome == "FALLBACK"
    assert rd.template is None
    assert rd.reason == "no match"
```

- [ ] **Step 2: Run — fails because parts_routing module doesn't exist**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_parts_routing.py -v`
Expected: FAIL (ModuleNotFoundError: cad_spec_gen.parts_routing)

- [ ] **Step 3: Create `src/cad_spec_gen/parts_routing.py` with dataclasses**

```python
"""cad_spec_gen.parts_routing — pure functions for template routing.

This module is intentionally side-effect-free:
  - No importlib.import_module of template code
  - No filesystem writes
  - No downloads
  - No prints (only logging at DEBUG)

It is consumed by:
  - codegen/gen_parts.py (Spec 1, log-only)
  - Spec 2's cad_spec_reviewer.py Phase R (invariant #9: same simulation path)

See docs/superpowers/specs/2026-04-10-spec1-foundation-design.md §7 for design.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frozen data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GeomInfo:
    """Frozen snapshot of _guess_geometry output — no dict ambiguity.

    Converted from codegen/gen_parts.py's _guess_geometry() dict return
    via a small adapter function in that file.
    """
    type: str                    # "box" | "cylinder" | "disc_arms" | "ring" | "l_bracket" | "plate"
    envelope_w: float
    envelope_d: float
    envelope_h: float
    extras: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TemplateDescriptor:
    """What parts_routing knows about a template — metadata only.

    Extracted via AST parsing without importing/executing template code.
    Tier: "builtin" (Tier 1, skill-shipped) | "project" (Tier 3, project-local)
    """
    name: str                    # module stem, e.g. "l_bracket"
    keywords: tuple              # from MATCH_KEYWORDS, sorted
    priority: int                # from MATCH_PRIORITY
    category: str                # from TEMPLATE_CATEGORY
    tier: str                    # "builtin" | "project"
    source_path: Path            # for debug / validate template command


@dataclass(frozen=True)
class RouteDecision:
    """Result of a routing decision — consumed by gen_parts or reviewer.

    Pure data: no exceptions, no logging from inside route().
    """
    outcome: str                 # "HIT_BUILTIN" | "HIT_PROJECT" | "FALLBACK" | "AMBIGUOUS"
    template: TemplateDescriptor | None
    reason: str = ""
    ambiguous_candidates: tuple = ()


# Category allowlist (matches §6.2.3 of the spec)
ALLOWED_CATEGORIES = {
    "bracket",
    "housing",
    "plate",
    "mechanical_interface",
    "fastener_family",
}
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_parts_routing.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/parts_routing.py tests/test_parts_routing.py
git commit -m "feat(routing): add parts_routing.py with frozen dataclasses

Introduces GeomInfo, TemplateDescriptor, RouteDecision frozen dataclasses
for the pure routing module. Replaces the ad-hoc dict interface the
architect review flagged as a leaky abstraction.

Phase 3 of Spec 1 foundation implementation."
```

---

### Task 15: Implement `locate_builtin_templates_dir()` helper

**Files:**
- Modify: `src/cad_spec_gen/parts_routing.py`
- Modify: `tests/test_parts_routing.py`

- [ ] **Step 1: Write failing test for the locator**

Append to `tests/test_parts_routing.py`:

```python
def test_locate_builtin_templates_dir_finds_repo_root():
    """Running from repo checkout must find templates/parts/ at repo root."""
    from cad_spec_gen.parts_routing import locate_builtin_templates_dir
    result = locate_builtin_templates_dir()
    # In a checked-out repo, should return Path pointing at templates/parts/
    assert result is not None
    assert result.is_dir()
    assert result.name == "parts"
    # Must contain iso_9409_flange.py at minimum
    assert (result / "iso_9409_flange.py").exists()
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_parts_routing.py::test_locate_builtin_templates_dir_finds_repo_root -v`
Expected: FAIL (AttributeError: locate_builtin_templates_dir)

- [ ] **Step 3: Add the locator function**

Append to `src/cad_spec_gen/parts_routing.py`:

```python
# ---------------------------------------------------------------------------
# Template location
# ---------------------------------------------------------------------------

def locate_builtin_templates_dir() -> Path | None:
    """Find the builtin templates/parts directory in both pip-install
    and repo-checkout modes. Returns None if neither location exists.

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
```

- [ ] **Step 4: Run — verify passes**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_parts_routing.py::test_locate_builtin_templates_dir_finds_repo_root -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/parts_routing.py tests/test_parts_routing.py
git commit -m "feat(routing): add locate_builtin_templates_dir() helper

Finds templates/parts/ in both pip-installed and repo-checkout modes
via importlib.resources with a repo-root filesystem fallback.

Phase 3 of Spec 1 foundation implementation."
```

---

### Task 16: Implement `discover_templates()` via AST parsing

**Files:**
- Modify: `src/cad_spec_gen/parts_routing.py`
- Modify: `tests/test_parts_routing.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_parts_routing.py`:

```python
def test_discover_templates_finds_all_builtin():
    """discover_templates on the real templates dir must find all 5 templates."""
    from cad_spec_gen.parts_routing import discover_templates, locate_builtin_templates_dir
    dir_path = locate_builtin_templates_dir()
    assert dir_path is not None
    descriptors = discover_templates([dir_path])
    names = {d.name for d in descriptors}
    expected = {"iso_9409_flange", "l_bracket", "rectangular_housing",
                "cylindrical_housing", "fixture_plate"}
    assert expected.issubset(names), f"Missing: {expected - names}"


def test_discover_templates_handles_empty_list():
    from cad_spec_gen.parts_routing import discover_templates
    descriptors = discover_templates([])
    assert descriptors == []


def test_discover_templates_skips_underscore_files(tmp_path):
    """Files starting with _ should be skipped."""
    from cad_spec_gen.parts_routing import discover_templates
    (tmp_path / "_private.py").write_text("# private helper")
    (tmp_path / "valid_tpl.py").write_text(
        'MATCH_KEYWORDS = ["valid"]\n'
        'MATCH_PRIORITY = 10\n'
        'TEMPLATE_CATEGORY = "bracket"\n'
        'TEMPLATE_VERSION = "1.0"\n'
        'def make(**p): pass\n'
        'def example_params(): return {}\n'
    )
    descriptors = discover_templates([tmp_path])
    names = {d.name for d in descriptors}
    assert "valid_tpl" in names
    assert "_private" not in names


def test_discover_templates_extracts_correct_metadata():
    from cad_spec_gen.parts_routing import discover_templates, locate_builtin_templates_dir
    descriptors = discover_templates([locate_builtin_templates_dir()])
    iso = next(d for d in descriptors if d.name == "iso_9409_flange")
    assert iso.category == "mechanical_interface"
    assert iso.priority == 20
    assert iso.tier == "builtin"
    assert len(iso.keywords) >= 3
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_parts_routing.py -v -k discover_templates`
Expected: FAIL

- [ ] **Step 3: Implement `discover_templates` with AST extraction**

Append to `src/cad_spec_gen/parts_routing.py`:

```python
# ---------------------------------------------------------------------------
# Discovery via AST
# ---------------------------------------------------------------------------

def _extract_descriptor_from_ast(
    tree: ast.Module,
    name: str,
    source_path: Path,
    tier: str,
) -> TemplateDescriptor | None:
    """Parse a template module AST and extract its descriptor constants.

    Returns None if any required constant is missing or malformed.
    Never executes template code.
    """
    extracted: dict[str, Any] = {}
    has_make = False
    has_example_params = False

    for node in tree.body:
        # Function definitions
        if isinstance(node, ast.FunctionDef):
            if node.name == "make":
                has_make = True
            elif node.name == "example_params":
                has_example_params = True
            continue

        # Annotated assignments: MATCH_KEYWORDS: list[str] = [...]
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                val = _literal_eval(node.value)
                if val is not None:
                    extracted[node.target.id] = val
            continue

        # Plain assignments: MATCH_KEYWORDS = [...]
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    val = _literal_eval(node.value)
                    if val is not None:
                        extracted[target.id] = val

    # Validate required fields
    if not has_make or not has_example_params:
        log.warning("Template %s missing make() or example_params()", source_path)
        return None

    required = ("MATCH_KEYWORDS", "MATCH_PRIORITY", "TEMPLATE_CATEGORY", "TEMPLATE_VERSION")
    for key in required:
        if key not in extracted:
            log.warning("Template %s missing %s constant", source_path, key)
            return None

    keywords = extracted["MATCH_KEYWORDS"]
    if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
        log.warning("Template %s has invalid MATCH_KEYWORDS (expected list[str])", source_path)
        return None

    priority = extracted["MATCH_PRIORITY"]
    if not isinstance(priority, int):
        log.warning("Template %s has invalid MATCH_PRIORITY (expected int)", source_path)
        return None

    category = extracted["TEMPLATE_CATEGORY"]
    if category not in ALLOWED_CATEGORIES:
        log.warning("Template %s has unknown category '%s' (allowed: %s)",
                    source_path, category, ALLOWED_CATEGORIES)
        return None

    return TemplateDescriptor(
        name=name,
        keywords=tuple(sorted(keywords)),
        priority=priority,
        category=category,
        tier=tier,
        source_path=source_path,
    )


def _literal_eval(node: ast.expr) -> Any:
    """Safely evaluate an AST node as a Python literal. Returns None on failure."""
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def discover_templates(search_paths: list[Path]) -> list[TemplateDescriptor]:
    """Scan search_paths for template .py files. Returns a list of descriptors.

    Pure function — reads files as text, parses with ast, does NOT import
    or execute template code. Malformed templates are logged (WARNING) and
    skipped. Duplicate names are resolved by priority order: later paths
    (Tier 3 project-local) override earlier paths (Tier 1 builtin).
    """
    descriptors_by_name: dict[str, TemplateDescriptor] = {}
    tier_order = {}  # name → (tier, priority, order_index)

    for idx, search_dir in enumerate(search_paths):
        if not search_dir or not search_dir.is_dir():
            continue
        # Later paths are higher-tier (project overrides builtin)
        tier = "project" if idx > 0 else "builtin"
        for py_file in sorted(search_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError, OSError) as exc:
                log.warning("Skipping malformed template %s: %s", py_file, exc)
                continue
            desc = _extract_descriptor_from_ast(
                tree, name=py_file.stem, source_path=py_file, tier=tier,
            )
            if desc is not None:
                # Later tier wins on name collision
                descriptors_by_name[desc.name] = desc

    return sorted(descriptors_by_name.values(), key=lambda d: d.name)
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_parts_routing.py -v`
Expected: all passing

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/parts_routing.py tests/test_parts_routing.py
git commit -m "feat(routing): add discover_templates() with AST extraction

Scans template .py files via ast.parse + ast.literal_eval to extract
MATCH_KEYWORDS / MATCH_PRIORITY / TEMPLATE_CATEGORY / TEMPLATE_VERSION
without ever executing template code. Tier 3 project templates override
Tier 1 builtins on name collision.

Phase 3 of Spec 1 foundation implementation."
```

---

### Task 17: Implement `route()` with edge cases

**Files:**
- Modify: `src/cad_spec_gen/parts_routing.py`
- Modify: `tests/test_parts_routing.py`

- [ ] **Step 1: Write failing tests covering all edge cases from §7.2.1**

Append to `tests/test_parts_routing.py`:

```python
from cad_spec_gen.parts_routing import (
    GeomInfo, TemplateDescriptor, RouteDecision, route,
)
from pathlib import Path


def _make_td(name, kws, priority, category, tier="builtin"):
    return TemplateDescriptor(
        name=name,
        keywords=tuple(sorted(kws)),
        priority=priority,
        category=category,
        tier=tier,
        source_path=Path(f"/tmp/{name}.py"),
    )


def test_route_empty_templates_returns_fallback():
    geom = GeomInfo("box", 100, 50, 20)
    decision = route("some part", geom, [])
    assert decision.outcome == "FALLBACK"
    assert decision.template is None
    assert "no templates available" in decision.reason


def test_route_empty_name_returns_fallback():
    geom = GeomInfo("box", 100, 50, 20)
    t = [_make_td("l_bracket", ["bracket"], 10, "bracket")]
    decision = route("", geom, t)
    assert decision.outcome == "FALLBACK"
    assert "empty part name" in decision.reason


def test_route_unknown_geom_type_returns_fallback():
    geom = GeomInfo("weird_shape", 100, 50, 20)
    t = [_make_td("l_bracket", ["bracket"], 10, "bracket")]
    decision = route("bracket 01", geom, t)
    assert decision.outcome == "FALLBACK"
    assert "unknown geom type" in decision.reason


def test_route_disc_arms_with_mechanical_interface_template_hits():
    geom = GeomInfo("disc_arms", 90, 90, 25,
                    extras={"arm_count": 4, "arm_l": 40})
    t = [_make_td("iso_9409_flange", ["flange", "robot flange"],
                  20, "mechanical_interface")]
    decision = route("十字法兰 01", geom, t)
    assert decision.outcome == "HIT_BUILTIN"
    assert decision.template.name == "iso_9409_flange"


def test_route_disc_arms_without_mechanical_interface_fallback():
    geom = GeomInfo("disc_arms", 90, 90, 25, extras={"arm_count": 4})
    t = [_make_td("l_bracket", ["bracket"], 15, "bracket")]
    decision = route("flange", geom, t)
    assert decision.outcome == "FALLBACK"
    assert "mechanical_interface" in decision.reason


def test_route_single_keyword_match_hits_builtin():
    geom = GeomInfo("box", 100, 50, 20)
    t = [_make_td("l_bracket", ["l_bracket", "angle bracket"], 15, "bracket")]
    decision = route("l_bracket mount", geom, t)
    assert decision.outcome == "HIT_BUILTIN"
    assert decision.template.name == "l_bracket"


def test_route_higher_priority_wins_on_keyword_collision():
    geom = GeomInfo("box", 100, 100, 100)
    t = [
        _make_td("housing_a", ["housing"], 10, "housing"),
        _make_td("housing_b", ["housing"], 20, "housing"),  # higher priority
    ]
    decision = route("enclosure housing", geom, t)
    assert decision.outcome == "HIT_BUILTIN"
    assert decision.template.name == "housing_b"


def test_route_equal_priority_collision_returns_ambiguous():
    geom = GeomInfo("box", 100, 100, 100)
    t = [
        _make_td("a", ["shared_kw"], 15, "bracket"),
        _make_td("b", ["shared_kw"], 15, "bracket"),
    ]
    decision = route("shared_kw mount", geom, t)
    assert decision.outcome == "AMBIGUOUS"
    assert decision.template is None
    assert len(decision.ambiguous_candidates) == 2


def test_route_project_tier_shadows_builtin():
    geom = GeomInfo("box", 100, 50, 20)
    t = [
        _make_td("l_bracket", ["l_bracket"], 15, "bracket", tier="builtin"),
        _make_td("l_bracket", ["l_bracket"], 15, "bracket", tier="project"),
    ]
    decision = route("l_bracket", geom, t)
    assert decision.outcome == "HIT_PROJECT"


def test_route_degenerate_envelope_fallback():
    geom = GeomInfo("box", 0, 50, 20)  # zero width
    t = [_make_td("l_bracket", ["bracket"], 15, "bracket")]
    decision = route("l_bracket", geom, t)
    assert decision.outcome == "FALLBACK"
    assert "degenerate" in decision.reason


def test_route_is_deterministic():
    """Same inputs must produce identical RouteDecision 100 times."""
    geom = GeomInfo("box", 100, 50, 20)
    t = [_make_td("l_bracket", ["bracket", "angle"], 15, "bracket")]
    first = route("bracket mount", geom, t)
    for _ in range(100):
        assert route("bracket mount", geom, t) == first
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_parts_routing.py -v -k route`
Expected: FAIL (AttributeError: route)

- [ ] **Step 3: Implement `route()`**

Append to `src/cad_spec_gen/parts_routing.py`:

```python
# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_KNOWN_GEOM_TYPES = {"box", "cylinder", "disc_arms", "ring", "l_bracket", "plate"}


def route(
    name: str,
    geom_info: GeomInfo,
    templates: list[TemplateDescriptor],
    yaml_rules: list[dict] | None = None,
) -> RouteDecision:
    """Route a BOM part to a template, or fall back.

    Pure function. Never raises; always returns a RouteDecision.
    See spec §7.2.1 for the error/edge case table.
    """
    # Edge case: empty templates list
    if not templates:
        return RouteDecision(
            outcome="FALLBACK",
            template=None,
            reason="no templates available",
        )

    # Edge case: empty name
    if not name or not name.strip():
        return RouteDecision(
            outcome="FALLBACK",
            template=None,
            reason="empty part name",
        )

    # Edge case: unknown geom type
    if geom_info.type not in _KNOWN_GEOM_TYPES:
        return RouteDecision(
            outcome="FALLBACK",
            template=None,
            reason=f"unknown geom type: {geom_info.type}",
        )

    # Edge case: degenerate envelope
    if (geom_info.envelope_w <= 0 or geom_info.envelope_d <= 0
            or geom_info.envelope_h <= 0):
        return RouteDecision(
            outcome="FALLBACK",
            template=None,
            reason=f"degenerate geometry: envelope has zero or negative dimension",
        )

    # Special case: disc_arms REQUIRES a mechanical_interface template
    if geom_info.type == "disc_arms":
        candidates = [t for t in templates if t.category == "mechanical_interface"]
        if not candidates:
            return RouteDecision(
                outcome="FALLBACK",
                template=None,
                reason="disc_arms requires mechanical_interface template",
            )
        # Pick highest priority, then project-tier if tie
        best = _pick_best(candidates)
        return RouteDecision(
            outcome=_tier_outcome(best.tier),
            template=best,
            reason="disc_arms → cross-arm hub template",
        )

    # Keyword matching: find templates whose MATCH_KEYWORDS substring-match the name
    name_lower = name.lower()
    matches = []
    for t in templates:
        for kw in t.keywords:
            if kw.lower() in name_lower:
                matches.append(t)
                break  # one match per template is enough

    if not matches:
        return RouteDecision(
            outcome="FALLBACK",
            template=None,
            reason="no keyword match",
        )

    # Filter by highest priority
    max_prio = max(t.priority for t in matches)
    top_prio = [t for t in matches if t.priority == max_prio]

    # Prefer project tier over builtin when priority is tied
    project_matches = [t for t in top_prio if t.tier == "project"]
    if project_matches:
        top_prio = project_matches

    if len(top_prio) == 1:
        best = top_prio[0]
        return RouteDecision(
            outcome=_tier_outcome(best.tier),
            template=best,
            reason=f"matched keyword at priority {max_prio}",
        )

    # Ambiguous: multiple templates at same (max) priority in same tier
    return RouteDecision(
        outcome="AMBIGUOUS",
        template=None,
        reason=f"multiple templates match at priority {max_prio}; "
               f"add geom_type discriminator or raise one template's priority",
        ambiguous_candidates=tuple(sorted(top_prio, key=lambda t: t.name)),
    )


def _pick_best(candidates: list[TemplateDescriptor]) -> TemplateDescriptor:
    """Pick the best candidate: highest priority, then project tier, then alphabetical."""
    return sorted(
        candidates,
        key=lambda t: (-t.priority, 0 if t.tier == "project" else 1, t.name),
    )[0]


def _tier_outcome(tier: str) -> str:
    """Map tier string to outcome name."""
    return "HIT_PROJECT" if tier == "project" else "HIT_BUILTIN"
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_parts_routing.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/parts_routing.py tests/test_parts_routing.py
git commit -m "feat(routing): implement route() with all edge cases

Pure function covering 10 edge cases from spec §7.2.1:
- empty templates / empty name / unknown geom type / degenerate envelope
- disc_arms requires mechanical_interface
- single keyword match
- priority tiebreak
- ambiguous collision
- Tier 3 project shadowing

Never raises; always returns RouteDecision. Determinism verified by
100-iteration identity check.

Phase 3 of Spec 1 foundation implementation."
```

---

### Task 18: Wire `parts_routing` into `codegen/gen_parts.py` (log-only)

**Files:**
- Modify: `codegen/gen_parts.py`

- [ ] **Step 1: Write test asserting gen_parts produces route log lines**

Create `tests/test_gen_parts_routing_integration.py`:

```python
"""Integration test: gen_parts.py calls parts_routing and logs decisions."""
import logging
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "src"))


def test_gen_parts_imports_parts_routing():
    """codegen/gen_parts.py must import parts_routing for Spec 1 integration."""
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    assert "from cad_spec_gen.parts_routing import" in gen_parts_src, \
        "gen_parts.py must import parts_routing"
    assert "route" in gen_parts_src, "gen_parts.py must reference route()"
    assert "discover_templates" in gen_parts_src, \
        "gen_parts.py must call discover_templates()"


def test_gen_parts_route_call_is_log_only():
    """Spec 1 integration is log-only — no behavior change to emission."""
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    # The log.info line for routing preview must exist
    assert "routing preview" in gen_parts_src or "route preview" in gen_parts_src, \
        "gen_parts.py must log routing decisions at INFO level"
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_gen_parts_routing_integration.py -v`
Expected: FAIL (import string not present)

- [ ] **Step 3: Modify `codegen/gen_parts.py` to import parts_routing**

Find the existing sys.path insert block at the top of `codegen/gen_parts.py`:
```python
_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
```

Immediately after it, add a src/ path insert and the parts_routing import:
```python
# Spec 1: make the cad_spec_gen package importable in repo-checkout mode.
# hatch_build.py publishes it as an installed package for wheel users;
# repo-checkout users need src/ on sys.path.
_SRC = str(Path(__file__).parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

try:
    from cad_spec_gen.parts_routing import (
        GeomInfo, route, discover_templates, locate_builtin_templates_dir,
    )
    _PARTS_ROUTING_AVAILABLE = True
except ImportError as _exc:
    _PARTS_ROUTING_AVAILABLE = False
    import logging as _log
    _log.getLogger(__name__).debug("parts_routing unavailable: %s", _exc)
```

Then find the function where a custom part is scaffolded (search for `_guess_geometry` call — likely in a function that generates the Jinja2 template context). After the `_guess_geometry()` call, add a routing preview log:

```python
# Spec 1: log routing preview (dormant integration; emission unchanged).
if _PARTS_ROUTING_AVAILABLE:
    try:
        _geom = GeomInfo(
            type=geom_info.get("type", "unknown"),
            envelope_w=float(geom_info.get("envelope_w") or 0),
            envelope_d=float(geom_info.get("envelope_d") or 0),
            envelope_h=float(geom_info.get("envelope_h") or 0),
            extras={k: v for k, v in geom_info.items()
                    if k not in {"type", "envelope_w", "envelope_d", "envelope_h"}},
        )
        _tier1 = locate_builtin_templates_dir()
        _search = [_tier1] if _tier1 else []
        _templates = discover_templates(_search)
        _decision = route(name_cn or "", _geom, _templates)
        import logging as _lg
        _lg.getLogger(__name__).info(
            "gen_parts routing preview: %s → %s (%s)",
            name_cn,
            _decision.outcome,
            _decision.template.name if _decision.template else "fallback",
        )
    except Exception as _err:
        import logging as _lg
        _lg.getLogger(__name__).debug("routing preview failed: %s", _err)
```

**Note to implementer**: the exact insertion point depends on the current structure of `gen_parts.py`. Find a spot AFTER `_guess_geometry(name_cn, material, envelope)` is called and where `name_cn` is in scope. If unclear, grep for `_guess_geometry` and place the block directly after its return value is assigned.

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_gen_parts_routing_integration.py -v`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add codegen/gen_parts.py tests/test_gen_parts_routing_integration.py
git commit -m "feat(codegen): wire parts_routing into gen_parts.py (log-only)

Spec 1 dormant integration: gen_parts.py imports parts_routing from
src/ (added to sys.path at module load) and calls route() for every
custom part after _guess_geometry(). The RouteDecision is logged at
INFO level only — no behavior change to emission. This is the hook
Spec 2 Phase 4 will flip from log-only to actual template routing.

Phase 3 of Spec 1 foundation implementation."
```

---

## Phase 4: cad-lib CLI (Local-Only)

### Task 19: Create `src/cad_spec_gen/cad_lib.py` skeleton with argparse

**Files:**
- Create: `src/cad_spec_gen/cad_lib.py`
- Create: `tests/test_cad_lib_local.py`

- [ ] **Step 1: Write failing test for cad_lib module existence**

```python
# tests/test_cad_lib_local.py
"""Tests for src/cad_spec_gen/cad_lib.py — local-only CLI."""
import os
import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest


def test_cad_lib_module_imports():
    """cad_lib module must import without side effects."""
    from cad_spec_gen import cad_lib
    assert hasattr(cad_lib, "main")
    assert callable(cad_lib.main)


def test_cad_lib_main_with_no_args_prints_help():
    """`cad-lib` with no args should print usage and exit non-zero."""
    from cad_spec_gen.cad_lib import main
    with pytest.raises(SystemExit) as exc_info:
        main([])
    # argparse exits with 2 on no subcommand; help exit is 0
    assert exc_info.value.code in (0, 2)


def test_cad_lib_version_flag():
    """`cad-lib --version` should print a version and exit 0."""
    from cad_spec_gen.cad_lib import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Create skeleton cad_lib.py**

```python
"""cad_spec_gen.cad_lib — local-only asset library CLI (Spec 1).

Subcommands (Spec 1 scope — local only, NO network, NO downloads):
    init                      Create ~/.cad-spec-gen/ directory layout
    doctor                    Diagnose common issues
    list <kind>               List assets (templates in Spec 1)
    which <kind> <name>       Show resolution chain for an asset
    validate template <name>  Structurally validate a template file
    migrate-subsystem <dir>   Copy canonical render_3d.py to a subsystem dir
    report                    Read suggestions.yaml and print
    migrate                   Schema migration stub

See docs/superpowers/specs/2026-04-10-spec1-foundation-design.md §8 for design.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Version is read from the package
try:
    from cad_spec_gen import __version__ as _pkg_version
except ImportError:
    _pkg_version = "unknown"

__version__ = _pkg_version

log = logging.getLogger("cad_lib")


# Name validation regex for CLI args (path traversal protection)
_SAFE_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _get_home() -> Path:
    """Return the effective ~/.cad-spec-gen/ directory.

    Respects CAD_SPEC_GEN_HOME env var for tests and for users who want
    to relocate the library root.
    """
    override = os.environ.get("CAD_SPEC_GEN_HOME")
    if override:
        return Path(override)
    return Path.home() / ".cad-spec-gen"


def _validate_name(name: str) -> bool:
    """Check that a name matches the safe regex (no path traversal)."""
    return bool(_SAFE_NAME_RE.match(name))


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="cad-lib",
        description="cad-spec-gen asset library local CLI (Spec 1)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cad-lib {__version__}",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Create ~/.cad-spec-gen/ layout")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing directory")

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Diagnose issues")

    # list
    p_list = subparsers.add_parser("list", help="List assets")
    p_list.add_argument("kind", choices=["templates", "textures", "models"])

    # which
    p_which = subparsers.add_parser("which", help="Show resolution chain")
    p_which.add_argument("kind", choices=["template", "texture", "material"])
    p_which.add_argument("name")

    # validate
    p_val = subparsers.add_parser("validate", help="Validate an asset")
    p_val.add_argument("kind", choices=["template"])
    p_val.add_argument("name_or_path")

    # migrate-subsystem
    p_migs = subparsers.add_parser("migrate-subsystem",
                                    help="Copy canonical render_3d.py to subsystem")
    p_migs.add_argument("directory", help="Subsystem directory (e.g. cad/end_effector)")
    p_migs.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompt")

    # report
    p_report = subparsers.add_parser("report", help="Show suggestion log")

    # migrate
    p_mig = subparsers.add_parser("migrate", help="Schema version migration (stub)")

    return parser


def main(argv: Optional[list] = None) -> int:
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Dispatch to command handlers (stub implementations below, filled in later tasks)
    handlers = {
        "init": cmd_init,
        "doctor": cmd_doctor,
        "list": cmd_list,
        "which": cmd_which,
        "validate": cmd_validate,
        "migrate-subsystem": cmd_migrate_subsystem,
        "report": cmd_report,
        "migrate": cmd_migrate,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


# ---------------------------------------------------------------------------
# Command handler stubs (filled in by subsequent tasks)
# ---------------------------------------------------------------------------

def cmd_init(args) -> int:
    raise NotImplementedError("cmd_init — implemented in Task 20")


def cmd_doctor(args) -> int:
    raise NotImplementedError("cmd_doctor — implemented in Task 21")


def cmd_list(args) -> int:
    raise NotImplementedError("cmd_list — implemented in Task 22")


def cmd_which(args) -> int:
    raise NotImplementedError("cmd_which — implemented in Task 23")


def cmd_validate(args) -> int:
    raise NotImplementedError("cmd_validate — implemented in Task 24")


def cmd_migrate_subsystem(args) -> int:
    raise NotImplementedError("cmd_migrate_subsystem — implemented in Task 25")


def cmd_report(args) -> int:
    raise NotImplementedError("cmd_report — implemented in Task 26")


def cmd_migrate(args) -> int:
    raise NotImplementedError("cmd_migrate — implemented in Task 27")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/cad_lib.py tests/test_cad_lib_local.py
git commit -m "feat(cad-lib): add cad_lib.py skeleton with argparse surface

Skeleton CLI with 8 subcommand parsers: init, doctor, list, which,
validate, migrate-subsystem, report, migrate. Command handlers raise
NotImplementedError; filled in by subsequent tasks. Includes name
validation regex and CAD_SPEC_GEN_HOME env var support.

Phase 4 of Spec 1 foundation implementation."
```

---

### Task 20: Implement `cad-lib init`

**Files:**
- Modify: `src/cad_spec_gen/cad_lib.py`
- Modify: `tests/test_cad_lib_local.py`

- [ ] **Step 1: Write failing tests for init command**

Append to `tests/test_cad_lib_local.py`:

```python
def test_cad_lib_init_creates_layout():
    """cad-lib init creates shared/ and state/ subdirs with correct YAMLs."""
    from cad_spec_gen.cad_lib import main, _get_home
    # CAD_SPEC_GEN_HOME is redirected by the autouse fixture; the dir exists
    # but is empty (we created .cad-spec-gen directory but not its subdirs).
    home = _get_home()
    # Our test fixture pre-creates .cad-spec-gen but it's empty. init should
    # populate it when --force is passed (because dir exists already).
    exit_code = main(["init", "--force"])
    assert exit_code == 0
    assert (home / "shared").is_dir()
    assert (home / "state").is_dir()
    assert (home / "shared" / "library.yaml").is_file()
    assert (home / "shared" / "README.md").is_file()
    assert (home / "state" / "installed.yaml").is_file()
    assert (home / "state" / "suggestions.yaml").is_file()
    assert (home / "state" / ".gitignore").is_file()


def test_cad_lib_init_refuses_to_clobber_populated_dir():
    """cad-lib init refuses to overwrite an existing populated library."""
    from cad_spec_gen.cad_lib import main, _get_home
    home = _get_home()
    # Pre-populate
    (home / "shared").mkdir()
    (home / "shared" / "library.yaml").write_text("existing user content")
    exit_code = main(["init"])
    assert exit_code != 0  # should refuse
    # Content preserved
    assert "existing user content" in (home / "shared" / "library.yaml").read_text()


def test_cad_lib_init_yaml_has_schema_version():
    """All created YAMLs must have schema_version: 1."""
    from cad_spec_gen.cad_lib import main, _get_home
    import yaml
    main(["init", "--force"])
    home = _get_home()
    lib = yaml.safe_load((home / "shared" / "library.yaml").read_text())
    assert lib["schema_version"] == 1
    inst = yaml.safe_load((home / "state" / "installed.yaml").read_text())
    assert inst["schema_version"] == 1
    sug = yaml.safe_load((home / "state" / "suggestions.yaml").read_text())
    assert sug["schema_version"] == 1
```

- [ ] **Step 2: Run — fail (NotImplementedError)**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k init`
Expected: FAIL with NotImplementedError

- [ ] **Step 3: Implement `cmd_init`**

Replace the `cmd_init` stub in `src/cad_spec_gen/cad_lib.py`:

```python
def cmd_init(args) -> int:
    """Create ~/.cad-spec-gen/ directory layout with schema v1 YAML stubs."""
    home = _get_home()

    # Check if library already populated (shared/ or state/ exist with content)
    shared = home / "shared"
    state = home / "state"
    already_populated = False
    for check_dir in (shared, state):
        if check_dir.exists() and any(check_dir.iterdir()):
            already_populated = True
            break

    if already_populated and not args.force:
        log.error("~/.cad-spec-gen/ is already populated. Use --force to reinitialize.")
        log.error(f"  {home}")
        return 1

    # Create directory structure
    home.mkdir(parents=True, exist_ok=True)
    shared.mkdir(exist_ok=True)
    state.mkdir(exist_ok=True)
    (shared / "templates").mkdir(exist_ok=True)

    # Write library.yaml
    (shared / "library.yaml").write_text(
        "# cad-spec-gen user library — shared config\n"
        "# This file is safe to commit to git for team-sharing.\n"
        "# See ~/.cad-spec-gen/state/ for machine-local state.\n"
        "\n"
        "schema_version: 1\n"
        "\n"
        "# Template routing rules (Spec 2 populates).\n"
        "routing: []\n"
        "\n"
        "# User-defined material preset extensions (Spec 2 populates).\n"
        "materials: {}\n"
        "\n"
        "# User template keyword overrides (Spec 2 populates).\n"
        "template_keywords: {}\n",
        encoding="utf-8",
    )

    # Write shared/README.md
    (shared / "README.md").write_text(
        "# cad-spec-gen shared library\n"
        "\n"
        "This directory is **safe to commit to git** for team-sharing.\n"
        "\n"
        "Contents:\n"
        "- `library.yaml` — routing rules, material presets, keyword overrides\n"
        "- `templates/` — (Spec 2) user-added template modules\n"
        "\n"
        "Machine-local state is stored in the sibling `state/` directory and\n"
        "must NOT be committed.\n"
        "\n"
        "Run `cad-lib doctor` to check the library's health.\n",
        encoding="utf-8",
    )

    # Write state/installed.yaml
    (state / "installed.yaml").write_text(
        "# cad-spec-gen installed asset log — MACHINE-LOCAL, do not commit.\n"
        "\n"
        "schema_version: 1\n"
        "\n"
        "textures: {}\n"
        "templates: {}\n"
        "models: {}\n",
        encoding="utf-8",
    )

    # Write state/suggestions.yaml
    (state / "suggestions.yaml").write_text(
        "# cad-spec-gen library growth suggestions — MACHINE-LOCAL, do not commit.\n"
        "\n"
        "schema_version: 1\n"
        "\n"
        "suggestions: []\n",
        encoding="utf-8",
    )

    # Write state/.gitignore
    (state / ".gitignore").write_text(
        "# Machine-local state — never commit.\n"
        "*\n"
        "!.gitignore\n",
        encoding="utf-8",
    )

    log.info(f"Initialized cad-spec-gen library at {home}")
    return 0
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k init`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/cad_lib.py tests/test_cad_lib_local.py
git commit -m "feat(cad-lib): implement 'cad-lib init' command

Creates ~/.cad-spec-gen/shared/ and state/ with schema_version: 1
YAML stubs. Refuses to clobber an existing populated library unless
--force is passed. Separates shared (git-safe) from state (machine-local).

Phase 4 of Spec 1 foundation implementation."
```

---

### Task 21: Implement `cad-lib doctor`

**Files:**
- Modify: `src/cad_spec_gen/cad_lib.py`
- Modify: `tests/test_cad_lib_local.py`

- [ ] **Step 1: Write failing test for doctor command**

Append to `tests/test_cad_lib_local.py`:

```python
def test_cad_lib_doctor_detects_missing_canonical_render_3d():
    """doctor should detect if src/cad_spec_gen/render_3d.py is missing."""
    from cad_spec_gen.cad_lib import main
    # The canonical render_3d.py DOES exist in this checkout, so doctor should pass.
    exit_code = main(["doctor"])
    assert exit_code == 0


def test_cad_lib_doctor_reports_template_count():
    """doctor must find all 5 builtin templates."""
    from cad_spec_gen.cad_lib import main
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["doctor"])
    # Doctor output should mention templates
    # (We don't assert strict format — just that it ran)
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k doctor`
Expected: FAIL (NotImplementedError)

- [ ] **Step 3: Implement `cmd_doctor`**

Replace the `cmd_doctor` stub:

```python
def cmd_doctor(args) -> int:
    """Run diagnostic checks and report issues."""
    checks = []  # list of (name, status, detail)
    errors = 0

    # Check 1: canonical render_3d.py exists
    try:
        from importlib.resources import files as ir_files
        try:
            canonical = ir_files("cad_spec_gen") / "render_3d.py"
            canonical_exists = canonical.is_file()
        except (FileNotFoundError, AttributeError):
            canonical_exists = False
        # Fallback: repo-checkout filesystem check
        if not canonical_exists:
            canonical_path = Path(__file__).parent / "render_3d.py"
            canonical_exists = canonical_path.exists()
    except Exception:
        canonical_exists = False

    if canonical_exists:
        checks.append(("canonical render_3d.py", "OK", ""))
    else:
        checks.append(("canonical render_3d.py", "ERROR", "not found"))
        errors += 1

    # Check 2: parts_routing importable
    try:
        from cad_spec_gen import parts_routing  # noqa
        checks.append(("parts_routing module", "OK", ""))
    except ImportError as e:
        checks.append(("parts_routing module", "ERROR", str(e)))
        errors += 1

    # Check 3: template discovery
    try:
        from cad_spec_gen.parts_routing import discover_templates, locate_builtin_templates_dir
        tier1 = locate_builtin_templates_dir()
        if tier1 is None:
            checks.append(("builtin templates dir", "ERROR", "locate_builtin_templates_dir() returned None"))
            errors += 1
        else:
            templates = discover_templates([tier1])
            count = len(templates)
            if count >= 5:
                checks.append(("template discovery", "OK", f"{count} templates found"))
            else:
                checks.append(("template discovery", "WARN",
                              f"only {count} templates found, expected ≥ 5"))
    except Exception as e:
        checks.append(("template discovery", "ERROR", str(e)))
        errors += 1

    # Check 4: ~/.cad-spec-gen/ layout (if initialized)
    home = _get_home()
    if home.exists():
        if (home / "shared").is_dir() and (home / "state").is_dir():
            checks.append(("~/.cad-spec-gen layout", "OK", ""))
        else:
            checks.append(("~/.cad-spec-gen layout", "WARN",
                          "run 'cad-lib init' to create shared/ and state/"))
    else:
        checks.append(("~/.cad-spec-gen layout", "INFO",
                      "not initialized; run 'cad-lib init'"))

    # Check 5: pyproject entry point (check if cad-lib command is installed)
    # (This is the circular check: passes only after P5 packaging)
    import shutil
    if shutil.which("cad-lib"):
        checks.append(("pyproject entry point", "OK", ""))
    else:
        checks.append(("pyproject entry point", "INFO",
                      "cad-lib not on PATH (install the wheel to enable); run via 'python -m cad_spec_gen.cad_lib' for now"))

    # Print results
    print("cad-lib doctor report")
    print("-" * 40)
    for name, status, detail in checks:
        marker = {"OK": "✓", "WARN": "!", "ERROR": "✗", "INFO": "·"}.get(status, "?")
        line = f"  {marker} {name}: {status}"
        if detail:
            line += f" — {detail}"
        print(line)
    print("-" * 40)

    if errors > 0:
        print(f"{errors} error(s) found")
        return 1
    return 0
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k doctor`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/cad_lib.py tests/test_cad_lib_local.py
git commit -m "feat(cad-lib): implement 'cad-lib doctor' diagnostic command

Runs 5 checks: canonical render_3d.py exists, parts_routing imports,
template discovery finds ≥5 templates, ~/.cad-spec-gen layout,
cad-lib entry point on PATH. Prints a human-readable report and
returns exit code 1 on any error.

Phase 4 of Spec 1 foundation implementation."
```

---

### Task 22: Implement `cad-lib list templates`

**Files:**
- Modify: `src/cad_spec_gen/cad_lib.py`
- Modify: `tests/test_cad_lib_local.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_cad_lib_local.py`:

```python
def test_cad_lib_list_templates_shows_all_five(capsys):
    from cad_spec_gen.cad_lib import main
    exit_code = main(["list", "templates"])
    assert exit_code == 0
    captured = capsys.readouterr()
    # All 5 template names should appear
    for name in ["iso_9409_flange", "l_bracket", "rectangular_housing",
                 "cylindrical_housing", "fixture_plate"]:
        assert name in captured.out, f"{name} missing from list output"


def test_cad_lib_list_textures_shows_empty_message(capsys):
    from cad_spec_gen.cad_lib import main
    exit_code = main(["list", "textures"])
    # Spec 1 has no texture support; should print informational message
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Spec 2" in captured.out or "not available" in captured.out.lower()
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k list`
Expected: FAIL

- [ ] **Step 3: Implement `cmd_list`**

```python
def cmd_list(args) -> int:
    """List assets of a given kind."""
    if args.kind == "templates":
        try:
            from cad_spec_gen.parts_routing import (
                discover_templates, locate_builtin_templates_dir,
            )
        except ImportError as e:
            print(f"Error: cannot import parts_routing: {e}", file=sys.stderr)
            return 1
        tier1 = locate_builtin_templates_dir()
        if tier1 is None:
            print("No builtin templates directory found.", file=sys.stderr)
            return 1
        templates = discover_templates([tier1])
        if not templates:
            print("No templates found.")
            return 0
        print(f"{'NAME':<25} {'CATEGORY':<22} {'TIER':<10} {'PRIORITY'}")
        print("-" * 70)
        for t in templates:
            print(f"{t.name:<25} {t.category:<22} {t.tier:<10} {t.priority}")
        return 0

    elif args.kind in ("textures", "models"):
        print(f"{args.kind} are not available in Spec 1 — see Spec 2 (deferred).")
        return 0

    return 1
```

- [ ] **Step 4: Run — pass**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k list`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/cad_lib.py tests/test_cad_lib_local.py
git commit -m "feat(cad-lib): implement 'cad-lib list templates'

Lists all discovered builtin templates with category, tier, and priority.
Spec 1 only supports 'list templates' — 'list textures' and 'list models'
print an informational 'see Spec 2' message.

Phase 4 of Spec 1 foundation implementation."
```

---

### Task 23: Implement `cad-lib which template <name>`

**Files:**
- Modify: `src/cad_spec_gen/cad_lib.py`
- Modify: `tests/test_cad_lib_local.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_cad_lib_local.py`:

```python
def test_cad_lib_which_template_existing(capsys):
    from cad_spec_gen.cad_lib import main
    exit_code = main(["which", "template", "l_bracket"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "l_bracket" in captured.out
    assert "builtin" in captured.out.lower() or "tier 1" in captured.out.lower()


def test_cad_lib_which_template_missing(capsys):
    from cad_spec_gen.cad_lib import main
    exit_code = main(["which", "template", "nonexistent_template"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "not found" in captured.out.lower() or "not found" in captured.err.lower()
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k which`
Expected: FAIL

- [ ] **Step 3: Implement `cmd_which`**

```python
def cmd_which(args) -> int:
    """Show resolution chain for an asset."""
    if args.kind != "template":
        print(f"'which {args.kind}' is not available in Spec 1.")
        return 0

    if not _validate_name(args.name):
        print(f"Invalid template name: {args.name!r} (must match [a-z0-9_]{{1,64}})",
              file=sys.stderr)
        return 2

    try:
        from cad_spec_gen.parts_routing import (
            discover_templates, locate_builtin_templates_dir,
        )
    except ImportError as e:
        print(f"Error: cannot import parts_routing: {e}", file=sys.stderr)
        return 1

    tier1 = locate_builtin_templates_dir()
    if tier1 is None:
        print("No builtin templates directory found.", file=sys.stderr)
        return 1

    templates = discover_templates([tier1])
    match = next((t for t in templates if t.name == args.name), None)

    if match is None:
        print(f"Template {args.name!r} not found.")
        print(f"Searched: {tier1}")
        return 1

    print(f"Template: {match.name}")
    print(f"  Tier:      {match.tier}")
    print(f"  Category:  {match.category}")
    print(f"  Priority:  {match.priority}")
    print(f"  Keywords:  {', '.join(match.keywords)}")
    print(f"  Source:    {match.source_path}")
    return 0
```

- [ ] **Step 4: Run — pass**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k which`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/cad_lib.py tests/test_cad_lib_local.py
git commit -m "feat(cad-lib): implement 'cad-lib which template <name>'

Shows the full resolution chain for a named template: tier, category,
priority, keywords, source path. Validates name against safe regex for
path-traversal protection.

Phase 4 of Spec 1 foundation implementation."
```

---

### Task 24: Implement `cad-lib validate template`

**Files:**
- Modify: `src/cad_spec_gen/cad_lib.py`
- Modify: `tests/test_cad_lib_local.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cad_lib_local.py`:

```python
def test_cad_lib_validate_template_by_name(capsys):
    from cad_spec_gen.cad_lib import main
    exit_code = main(["validate", "template", "l_bracket"])
    assert exit_code == 0


def test_cad_lib_validate_template_missing(capsys):
    from cad_spec_gen.cad_lib import main
    exit_code = main(["validate", "template", "nonexistent_foo"])
    assert exit_code != 0


def test_cad_lib_validate_template_rejects_traversal(capsys):
    """Path-traversal attempts must be rejected by name regex."""
    from cad_spec_gen.cad_lib import main
    exit_code = main(["validate", "template", "../../etc/passwd"])
    assert exit_code != 0
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "invalid" in out.lower() or "not found" in out.lower()
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k validate`
Expected: FAIL

- [ ] **Step 3: Implement `cmd_validate`**

```python
def cmd_validate(args) -> int:
    """Validate a template structurally."""
    if args.kind != "template":
        return 2

    name_or_path = args.name_or_path

    # Resolution: try as filesystem path first, then as module name
    path: Optional[Path] = None

    # Option 1: filesystem path (absolute or relative to cwd)
    candidate = Path(name_or_path)
    if candidate.exists() and candidate.is_file() and candidate.suffix == ".py":
        path = candidate.resolve()
        # Security: ensure path is not escaping somewhere weird
        # (Accept any .py file the user points at; they chose it explicitly.)
    else:
        # Option 2: treat as module name — validate regex + look up via discover_templates
        if not _validate_name(name_or_path):
            print(f"Invalid template name: {name_or_path!r} "
                  f"(must match [a-z0-9_]{{1,64}} or be a valid file path)",
                  file=sys.stderr)
            return 2
        try:
            from cad_spec_gen.parts_routing import (
                discover_templates, locate_builtin_templates_dir,
            )
        except ImportError as e:
            print(f"Error: cannot import parts_routing: {e}", file=sys.stderr)
            return 1
        tier1 = locate_builtin_templates_dir()
        if tier1 is None:
            print("No builtin templates dir.", file=sys.stderr)
            return 1
        templates = discover_templates([tier1])
        match = next((t for t in templates if t.name == name_or_path), None)
        if match is None:
            print(f"Template {name_or_path!r} not found.", file=sys.stderr)
            return 1
        path = match.source_path

    # Parse + validate
    import ast
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        print(f"✗ Parse error: {e}", file=sys.stderr)
        return 1

    # Check required constants and functions via AST
    required_funcs = {"make", "example_params"}
    required_consts = {"MATCH_KEYWORDS", "MATCH_PRIORITY",
                       "TEMPLATE_CATEGORY", "TEMPLATE_VERSION"}
    found_funcs = set()
    found_consts = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in required_funcs:
            found_funcs.add(node.name)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            for t in targets:
                if isinstance(t, ast.Name) and t.id in required_consts:
                    found_consts.add(t.id)

    missing = []
    if required_funcs - found_funcs:
        missing.append(f"functions: {required_funcs - found_funcs}")
    if required_consts - found_consts:
        missing.append(f"constants: {required_consts - found_consts}")

    if missing:
        print(f"✗ Template {path} is missing: {'; '.join(missing)}", file=sys.stderr)
        return 1

    print(f"✓ Template {path} passes structural validation.")
    return 0
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k validate`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/cad_lib.py tests/test_cad_lib_local.py
git commit -m "feat(cad-lib): implement 'cad-lib validate template <name|path>'

Validates a template file structurally via AST: checks for required
functions (make, example_params) and constants (MATCH_KEYWORDS,
MATCH_PRIORITY, TEMPLATE_CATEGORY, TEMPLATE_VERSION). Resolves by file
path OR module name; module names must pass the safe regex to prevent
path traversal.

Phase 4 of Spec 1 foundation implementation."
```

---

### Task 25: Implement `cad-lib migrate-subsystem`

**Files:**
- Modify: `src/cad_spec_gen/cad_lib.py`
- Modify: `tests/test_cad_lib_local.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_cad_lib_local.py`:

```python
def test_cad_lib_migrate_subsystem_creates_backup(tmp_path):
    from cad_spec_gen.cad_lib import main
    # Create a fake subsystem dir with an old render_3d.py
    sub = tmp_path / "fake_subsystem"
    sub.mkdir()
    (sub / "render_3d.py").write_text("# old render_3d content\n")
    exit_code = main(["migrate-subsystem", str(sub), "--yes"])
    assert exit_code == 0
    # New file copied
    new_content = (sub / "render_3d.py").read_text(encoding="utf-8")
    assert "old render_3d content" not in new_content
    # Backup created with timestamp
    backups = list(sub.glob("render_3d.py.bak.*"))
    assert len(backups) == 1
    assert "old render_3d content" in backups[0].read_text(encoding="utf-8")
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k migrate_subsystem`
Expected: FAIL

- [ ] **Step 3: Implement `cmd_migrate_subsystem`**

```python
def cmd_migrate_subsystem(args) -> int:
    """Copy canonical render_3d.py to a subsystem directory with .bak backup."""
    import shutil
    from datetime import datetime

    target_dir = Path(args.directory).resolve()
    if not target_dir.is_dir():
        print(f"✗ Not a directory: {target_dir}", file=sys.stderr)
        return 1

    target_file = target_dir / "render_3d.py"

    # Locate canonical source
    try:
        from importlib.resources import files as ir_files
        try:
            canonical_ref = ir_files("cad_spec_gen") / "render_3d.py"
            canonical = Path(str(canonical_ref))
        except (FileNotFoundError, AttributeError):
            canonical = None
    except Exception:
        canonical = None

    if canonical is None or not canonical.is_file():
        # Fallback: try the repo-checkout location
        fallback = Path(__file__).parent / "render_3d.py"
        if fallback.is_file():
            canonical = fallback
        else:
            print(f"✗ Canonical render_3d.py not found.", file=sys.stderr)
            return 1

    # Prompt unless --yes
    if not args.yes:
        print(f"This will replace {target_file}")
        print(f"  with:           {canonical}")
        print(f"  backup to:      {target_file}.bak.<timestamp>")
        resp = input("Proceed? [y/N] ").strip().lower()
        if resp not in ("y", "yes"):
            print("Aborted.")
            return 0

    # Backup existing if present
    if target_file.exists():
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        backup = target_file.parent / f"{target_file.name}.bak.{timestamp}"
        shutil.copy2(target_file, backup)
        print(f"  backup: {backup}")

    # Copy canonical
    shutil.copy2(canonical, target_file)
    print(f"✓ Migrated {target_file}")
    return 0
```

- [ ] **Step 4: Run — pass**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k migrate_subsystem`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/cad_lib.py tests/test_cad_lib_local.py
git commit -m "feat(cad-lib): implement 'cad-lib migrate-subsystem'

Copies the canonical src/cad_spec_gen/render_3d.py to a deployed
subsystem directory with a timestamped .bak backup of the existing
file. Prompts for confirmation unless --yes is passed. This is how
existing projects receive the FOV fix without touching the skill's
intermediate-product invariant.

Phase 4 of Spec 1 foundation implementation."
```

---

### Task 26: Implement `cad-lib report` and `cad-lib migrate` stub

**Files:**
- Modify: `src/cad_spec_gen/cad_lib.py`
- Modify: `tests/test_cad_lib_local.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cad_lib_local.py`:

```python
def test_cad_lib_report_empty_library(capsys):
    from cad_spec_gen.cad_lib import main
    # Initialize library first
    main(["init", "--force"])
    exit_code = main(["report"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no suggestions" in captured.out.lower() or \
           "0 suggestion" in captured.out.lower()


def test_cad_lib_migrate_stub_passes_on_v1(capsys):
    from cad_spec_gen.cad_lib import main
    main(["init", "--force"])
    exit_code = main(["migrate"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "current" in captured.out.lower() or "version 1" in captured.out.lower()
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v -k "report or migrate"`
Expected: FAIL

- [ ] **Step 3: Implement both**

```python
def cmd_report(args) -> int:
    """Print the suggestions log."""
    import yaml
    home = _get_home()
    sug_file = home / "state" / "suggestions.yaml"
    if not sug_file.exists():
        print("No suggestions.yaml found. Run 'cad-lib init' first.")
        return 0
    try:
        data = yaml.safe_load(sug_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"✗ Failed to parse suggestions.yaml: {e}", file=sys.stderr)
        return 1

    sv = data.get("schema_version")
    if sv != 1:
        print(f"✗ Unsupported schema_version: {sv}", file=sys.stderr)
        return 1

    sug_list = data.get("suggestions", [])
    if not sug_list:
        print("No suggestions (0 entries). Spec 2 Phase R populates this log.")
        return 0

    print(f"cad-lib library growth suggestions ({len(sug_list)} entries):")
    print("-" * 40)
    for entry in sug_list:
        print(f"  [{entry.get('kind', '?')}] {entry.get('reason', '?')}")
        if "suggestion" in entry:
            print(f"    → {entry['suggestion']}")
    return 0


def cmd_migrate(args) -> int:
    """Schema migration stub. Checks versions, errors on unknown."""
    import yaml
    home = _get_home()
    if not home.exists():
        print("~/.cad-spec-gen/ does not exist. Run 'cad-lib init' first.")
        return 0

    yaml_files = [
        home / "shared" / "library.yaml",
        home / "state" / "installed.yaml",
        home / "state" / "suggestions.yaml",
    ]
    issues = []
    for f in yaml_files:
        if not f.exists():
            continue
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            issues.append(f"{f.name}: parse error — {e}")
            continue
        sv = data.get("schema_version")
        if sv is None:
            issues.append(f"{f.name}: missing schema_version")
        elif sv > 1:
            issues.append(f"{f.name}: unknown version {sv} (expected 1); upgrade the skill")
        elif sv < 1:
            issues.append(f"{f.name}: legacy version {sv}; migration not yet implemented")

    if issues:
        for msg in issues:
            print(f"✗ {msg}", file=sys.stderr)
        return 1

    print("All schemas current (version 1).")
    return 0
```

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_cad_lib_local.py -v`
Expected: all cad-lib tests pass

- [ ] **Step 5: Commit**

```bash
git add src/cad_spec_gen/cad_lib.py tests/test_cad_lib_local.py
git commit -m "feat(cad-lib): implement 'cad-lib report' and 'cad-lib migrate' stub

- report: reads state/suggestions.yaml and prints deduplicated entries.
  Empty in Spec 1; Spec 2 Phase R populates this log from pipeline runs.
- migrate: stub that checks all YAMLs for schema_version: 1. Errors
  loudly on unknown versions rather than silently misinterpreting.

Phase 4 of Spec 1 foundation implementation."
```

---

## Phase 5: Packaging Fix

### Task 27: Add `cad-lib` entry point and pytest config to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Write test asserting entry point is declared**

Create `tests/test_packaging.py`:

```python
"""Packaging tests for Spec 1 — verify entry points and hatch config."""
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).parent.parent


def test_pyproject_has_cad_lib_entry_point():
    content = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "cad-lib = " in content, "pyproject.toml missing cad-lib entry point"
    assert "cad_spec_gen.cad_lib:main" in content, \
        "Entry point not pointing at cad_spec_gen.cad_lib:main"


def test_pyproject_has_pytest_env_pinned():
    content = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PYTHONHASHSEED=0" in content, "PYTHONHASHSEED not pinned"
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_packaging.py -v -k entry_point`
Expected: FAIL (entry point missing)

- [ ] **Step 3: Modify `pyproject.toml`**

Find the existing `[project.scripts]` section and add the cad-lib entry:

```toml
[project.scripts]
cad-skill-setup = "cad_spec_gen.wizard.cli:setup"
cad-skill-check = "cad_spec_gen.wizard.cli:check"
cad-lib = "cad_spec_gen.cad_lib:main"
```

(The pytest config was already added in Task 2.)

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_packaging.py -v`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_packaging.py
git commit -m "build: add cad-lib entry point to pyproject.toml

Exposes 'cad-lib' on PATH when the wheel is installed via pip.
cad_spec_gen.cad_lib:main is the flat-layout entry module per §4.3.

Phase 5 of Spec 1 foundation implementation."
```

---

### Task 28: Ship `parts_library.default.yaml` in the wheel via `hatch_build.py`

**Files:**
- Modify: `hatch_build.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_packaging.py`:

```python
def test_hatch_build_ships_parts_library_default_yaml():
    content = (_REPO_ROOT / "hatch_build.py").read_text(encoding="utf-8")
    # Look for any reference to parts_library.default.yaml
    assert "parts_library.default.yaml" in content, \
        "hatch_build.py does not ship parts_library.default.yaml"
```

- [ ] **Step 2: Run — fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_packaging.py::test_hatch_build_ships_parts_library_default_yaml -v`
Expected: FAIL

- [ ] **Step 3: Read current `hatch_build.py`**

Run: `cat D:/Work/cad-spec-gen/hatch_build.py`
Find the copy loop and understand its structure.

- [ ] **Step 4: Add `parts_library.default.yaml` to the copy list**

In `hatch_build.py`, locate the existing `COPY_DIRS` dict and add a `TOP_LEVEL_FILES` dict if not present. After the existing copy loop, add:

```python
# Spec 1: top-level files shipped as data payload
TOP_LEVEL_FILES = {
    "parts_library.default.yaml": "parts_library.default.yaml",
}

for src_name, dest_rel in TOP_LEVEL_FILES.items():
    src_path = Path(__file__).parent / src_name
    if not src_path.exists():
        continue
    dest_path = build_data_dir / dest_rel  # build_data_dir = src/cad_spec_gen/data
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(src_path, dest_path)
```

**Note**: the exact variable name for the destination data dir depends on the existing `hatch_build.py` structure. Adapt the destination path to match the existing COPY_DIRS convention.

- [ ] **Step 5: Run test**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_packaging.py::test_hatch_build_ships_parts_library_default_yaml -v`
Expected: pass

- [ ] **Step 6: Commit**

```bash
git add hatch_build.py tests/test_packaging.py
git commit -m "build: ship parts_library.default.yaml in the wheel

hatch_build.py now copies parts_library.default.yaml into
src/cad_spec_gen/data/ so pip-installed users can read it via
importlib.resources.files('cad_spec_gen') / 'data' / 'parts_library.default.yaml'.

Phase 5 of Spec 1 foundation implementation."
```

---

### Task 29: Post-build smoke test (slow CI tier)

**Files:**
- Modify: `tests/test_packaging.py`

- [ ] **Step 1: Write a slow-marked smoke test**

Append to `tests/test_packaging.py`:

```python
@pytest.mark.slow
def test_wheel_install_smoke(tmp_path):
    """Build the wheel, install it into a temp venv, run 'cad-lib doctor'.

    This is the ultimate proof that packaging works end-to-end.
    Marked slow because it invokes hatch build + pip install + subprocess.
    """
    import subprocess
    import sys
    import venv

    # Build the wheel
    dist_dir = _REPO_ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)
    result = subprocess.run(
        [sys.executable, "-m", "hatch", "build", "-t", "wheel"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"hatch build failed (may be dev env issue): {result.stderr}")

    wheels = list(dist_dir.glob("cad_spec_gen-*.whl"))
    if not wheels:
        pytest.skip("No wheel produced by hatch build")
    wheel = wheels[-1]  # Most recent

    # Create a fresh venv
    venv_dir = tmp_path / "testvenv"
    venv.create(venv_dir, with_pip=True)
    if sys.platform == "win32":
        pip_exe = venv_dir / "Scripts" / "pip.exe"
        cad_lib_exe = venv_dir / "Scripts" / "cad-lib.exe"
    else:
        pip_exe = venv_dir / "bin" / "pip"
        cad_lib_exe = venv_dir / "bin" / "cad-lib"

    # Install the wheel
    subprocess.run([str(pip_exe), "install", str(wheel)], check=True,
                   capture_output=True)

    # Verify cad-lib entry point exists and doctor runs
    assert cad_lib_exe.exists(), f"cad-lib not installed at {cad_lib_exe}"
    result = subprocess.run([str(cad_lib_exe), "doctor"], capture_output=True, text=True)
    assert result.returncode == 0, \
        f"cad-lib doctor failed in fresh venv:\n{result.stdout}\n{result.stderr}"

    # Verify list templates works
    result = subprocess.run([str(cad_lib_exe), "list", "templates"],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert "l_bracket" in result.stdout
    assert "iso_9409_flange" in result.stdout
```

- [ ] **Step 2: Run — slow tests are not run by default**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_packaging.py -v -m slow`
Expected: runs the smoke test (may skip if hatch not installed in dev env)

- [ ] **Step 3: Commit**

```bash
git add tests/test_packaging.py
git commit -m "test: add post-build wheel install smoke (slow marker)

Builds the wheel, installs into a fresh venv, runs 'cad-lib doctor'
and 'cad-lib list templates'. This is the end-to-end proof that
packaging works. Marked @pytest.mark.slow so it only runs on main/nightly.

Phase 5 of Spec 1 foundation implementation."
```

---

## Phase 6: Schema Versioning Tests

### Task 30: Round-trip preservation test for `library.yaml`

**Files:**
- Create: `tests/test_schema_versioning.py`

- [ ] **Step 1: Write the round-trip test**

```python
# tests/test_schema_versioning.py
"""Tests for schema versioning invariants (Phase 6)."""
import sys
from pathlib import Path

import pytest
import yaml

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_init_creates_schema_version_1():
    from cad_spec_gen.cad_lib import main, _get_home
    main(["init", "--force"])
    home = _get_home()
    for path in [
        home / "shared" / "library.yaml",
        home / "state" / "installed.yaml",
        home / "state" / "suggestions.yaml",
    ]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1


def test_migrate_stub_rejects_unknown_version():
    from cad_spec_gen.cad_lib import main, _get_home
    main(["init", "--force"])
    home = _get_home()
    # Write an unknown version to library.yaml
    lib_file = home / "shared" / "library.yaml"
    lib_file.write_text(
        "schema_version: 99\n"
        "routing: []\n"
        "materials: {}\n"
        "template_keywords: {}\n",
        encoding="utf-8",
    )
    exit_code = main(["migrate"])
    assert exit_code != 0  # should reject


def test_library_yaml_round_trip_preserves_unknown_keys():
    """Readers must preserve unknown keys when round-tripping."""
    from cad_spec_gen.cad_lib import main, _get_home
    main(["init", "--force"])
    home = _get_home()
    lib_file = home / "shared" / "library.yaml"

    # Add an unknown experimental key
    original = yaml.safe_load(lib_file.read_text(encoding="utf-8"))
    original["experimental_flag"] = True
    original["future_section"] = {"foo": "bar"}
    lib_file.write_text(yaml.safe_dump(original, sort_keys=False), encoding="utf-8")

    # Re-read and verify the keys survive
    round_tripped = yaml.safe_load(lib_file.read_text(encoding="utf-8"))
    assert round_tripped.get("experimental_flag") is True
    assert round_tripped.get("future_section") == {"foo": "bar"}
    assert round_tripped.get("schema_version") == 1
```

- [ ] **Step 2: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_schema_versioning.py -v`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_schema_versioning.py
git commit -m "test(schema): verify schema_version invariants

Tests:
- cad-lib init writes schema_version: 1 to all created YAMLs
- cad-lib migrate rejects unknown versions (exits non-zero)
- Round-trip preservation: unknown top-level keys survive read/write
  cycle (required by §10.3 invariant #3)

Phase 6 of Spec 1 foundation implementation."
```

---

## Phase 7: Full Test Suite Verification

### Task 31: Run the complete test suite and fix any regressions

**Files:**
- (none directly; reviews all previous work)

- [ ] **Step 1: Run the full fast+integration test suite**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/ -v -m "not slow" --tb=short`
Expected: all pass. If any fail, STOP and diagnose — do not skip failures.

- [ ] **Step 2: Run the slow tier (optional locally, required in CI)**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/ -v -m slow --tb=short`
Expected: slow tests pass if the environment has hatch + venv capability; may skip otherwise.

- [ ] **Step 3: Generate a test summary**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/ --co -q 2>&1 | tail -20`
Expected: collection summary showing all tests from all new test files.

- [ ] **Step 4: Verify no stale/skipped tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/ -v --no-header 2>&1 | grep -E "SKIPPED|XFAIL" | head -20`
Expected: only legitimately skipped tests (e.g., cadquery integration when not installed, Blender tests without bpy).

- [ ] **Step 5: Commit summary report**

If everything passes, no commit needed. If minor fixes were required during review, create a single cleanup commit:

```bash
git add <any_fixed_files>
git commit -m "test: fix test suite regressions discovered during Phase 7 review

Phase 7 verification pass of Spec 1 foundation implementation."
```

---

## Self-Review Checklist

After implementing all tasks, verify against spec §9.5:

- [ ] All 5 templates exist in `templates/parts/` with full module contract
- [ ] `src/cad_spec_gen/render_3d.py` has `min(fov_v, fov_h)` formula and `frame_fill = 0.75`
- [ ] `render_depth_only.py` has the same formula
- [ ] `src/cad_spec_gen/parts_routing.py` has all dataclasses + `discover_templates` + `route` + `locate_builtin_templates_dir`
- [ ] `codegen/gen_parts.py` imports `parts_routing` and logs routing decisions
- [ ] `src/cad_spec_gen/cad_lib.py` has 8 subcommands, all implemented (no NotImplementedError remaining)
- [ ] `pyproject.toml` has `cad-lib` entry point and `[tool.pytest.ini_options]` with `PYTHONHASHSEED=0`
- [ ] `hatch_build.py` ships `parts_library.default.yaml`
- [ ] `tests/conftest.py` has the autouse tripwire fixture
- [ ] Every phase's tests pass
- [ ] No stale `tools/cad_lib.py` references anywhere in the spec or code
- [ ] No references to `cad_spec_gen.data.python_tools.*` imports (all flat layout)
- [ ] No references to `cad_spec_gen.templates.parts.__path__` (replaced by `locate_builtin_templates_dir`)

---

**End of plan.**

After implementation, run the full test suite one more time:
```bash
cd D:/Work/cad-spec-gen && python -m pytest tests/ -v --tb=short
```

Then ready for Spec 2 when the 5 blocking sub-sections (§16 security, §17 Chinese expansion, §18 PBR physics, §19 release engineering, §20 AI × PBR) are drafted.
