# Assembly Coherence Fix — Parts Connect Together

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the generated assembly so parts are physically touching and correctly sized, instead of scattered across 360mm of Z-axis.

**Architecture:** Three-layer fix: (A) `gen_parts.py` reads §6.4 envelopes for accurate dimensions, (B) `gen_assembly.py` uses anchor-relative stacking instead of cumulative offsets, (C) `gen_std_parts.py` also reads §6.4 for purchased part sizing. All changes are in `codegen/` — no template changes needed.

**Tech Stack:** Python 3.10+, regex parsing, Jinja2 templates (existing)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `codegen/gen_parts.py` | Modify | Add `_parse_envelopes()` to read §6.4; use it as Priority 0 in `_guess_geometry()` |
| `codegen/gen_assembly.py` | Modify | Replace cumulative stacking with anchor-relative positioning in `_resolve_child_offsets()` |
| `codegen/gen_std_parts.py` | Modify | Add §6.4 envelope lookup as highest-priority dimension source |
| `tests/test_assembly_coherence.py` | Create | Regression tests for positioning and envelope parsing |

---

### Task 1: Parse §6.4 Envelope Table (shared parser)

**Files:**
- Modify: `codegen/gen_assembly.py:321-338` (existing `_parse_dims_text`)
- Create: `tests/test_assembly_coherence.py`

The §6.4 table has this format:
```
| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |
| GIS-EE-001-01 | 法兰本体 | cylinder | Φ90.0×25.0 | P4:visual |
| GIS-EE-006-01 | 壳体 | box | 140.0×100.0×55.0 | P3:BOM |
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assembly_coherence.py
"""Regression tests for assembly coherence fixes."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_parse_envelopes_from_spec():
    """§6.4 table should parse into {part_no: (w, d, h)} dict."""
    from codegen.gen_assembly import parse_envelopes
    spec = os.path.join(os.path.dirname(__file__), "..", "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.isfile(spec):
        # Use test fixture
        spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    # Must find at least one entry
    assert len(envs) > 0
    # Check structure: each value is (w, d, h) tuple
    for pno, dims in envs.items():
        assert len(dims) == 3, f"{pno}: expected 3-tuple, got {dims}"
        assert all(isinstance(v, float) for v in dims), f"{pno}: non-float in {dims}"


def _write_fixture_spec():
    """Create minimal CAD_SPEC.md fixture with §6.4 table."""
    import tempfile
    content = """# CAD Spec — Test (TEST)

## 6. 装配姿态与定位

### 6.4 零件包络尺寸

| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |
| --- | --- | --- | --- | --- |
| TEST-001-01 | 法兰本体 | cylinder | Φ90.0×25.0 | P4:visual |
| TEST-001-02 | PEEK绝缘段 | cylinder | Φ86.0×5.0 | P3:BOM |
| TEST-006-01 | 壳体 | box | 140.0×100.0×55.0 | P3:BOM |
"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_parse_envelopes_cylinder():
    """Cylinder format: Φ90.0×25.0 → (90.0, 90.0, 25.0)."""
    from codegen.gen_assembly import parse_envelopes
    spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    assert envs["TEST-001-01"] == (90.0, 90.0, 25.0)


def test_parse_envelopes_box():
    """Box format: 140.0×100.0×55.0 → (140.0, 100.0, 55.0)."""
    from codegen.gen_assembly import parse_envelopes
    spec = _write_fixture_spec()
    envs = parse_envelopes(spec)
    assert envs["TEST-006-01"] == (140.0, 100.0, 55.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_assembly_coherence.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_envelopes'`

- [ ] **Step 3: Implement `parse_envelopes()` in gen_assembly.py**

Add this function after `_parse_dims_text()` (around line 339):

```python
def parse_envelopes(spec_path: str) -> dict:
    """Parse §6.4 envelope dimensions table from CAD_SPEC.md.

    Returns {part_no: (w, d, h)} where w,d,h are floats in mm.
    For cylinders: w=d=diameter, h=length.
    For boxes: w,d,h as given.
    """
    try:
        text = Path(spec_path).read_text(encoding="utf-8")
    except Exception:
        return {}

    envelopes = {}
    in_section = False

    for line in text.splitlines():
        if "### 6.4" in line and "包络" in line:
            in_section = True
            continue
        if in_section and (line.startswith("## ") or
                          (line.startswith("### ") and "6.4" not in line)):
            break
        if not in_section or not line.startswith("|") or "---" in line:
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = cells[1:-1] if len(cells) >= 2 else cells
        if len(cells) < 4 or cells[0] == "料号":
            continue

        pno = cells[0]
        if not re.match(r"[A-Z]+-", pno):
            continue

        dims_text = cells[3] if len(cells) > 3 else ""
        parsed = _parse_dims_text(dims_text)
        if parsed:
            envelopes[pno] = parsed

    return envelopes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_assembly_coherence.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codegen/gen_assembly.py tests/test_assembly_coherence.py
git commit -m "feat: add parse_envelopes() to read §6.4 envelope table"
```

---

### Task 2: gen_parts.py reads §6.4 envelopes (Priority 0 for geometry)

**Files:**
- Modify: `codegen/gen_parts.py:44-116` (`_guess_geometry`) and `codegen/gen_parts.py:204` (call site)
- Modify: `tests/test_assembly_coherence.py`

Currently `_guess_geometry(name_cn, material)` only reads BOM material text and keyword heuristics. After this task, it will accept an optional `envelope` parameter from §6.4 as highest priority.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assembly_coherence.py`:

```python
def test_guess_geometry_uses_envelope():
    """§6.4 envelope should override BOM-based dimension guessing."""
    from codegen.gen_parts import _guess_geometry
    # Without envelope: 法兰+悬臂 → hardcoded d=80
    geom_old = _guess_geometry("法兰本体（含十字悬臂）", "7075-T6铝合金")
    assert geom_old["d"] == 80.0  # old hardcoded value

    # With envelope from §6.4: Φ90×25 → d=90, t=25
    geom_new = _guess_geometry("法兰本体（含十字悬臂）", "7075-T6铝合金",
                               envelope=(90.0, 90.0, 25.0))
    assert geom_new["d"] == 90.0
    assert geom_new["envelope_h"] == 25.0


def test_guess_geometry_box_envelope():
    """Box envelope should produce box geometry."""
    from codegen.gen_parts import _guess_geometry
    geom = _guess_geometry("壳体（含散热鳍片）", "6063铝合金",
                           envelope=(140.0, 100.0, 55.0))
    assert geom["type"] == "box"
    assert geom["w"] == 140.0
    assert geom["h"] == 55.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_assembly_coherence.py::test_guess_geometry_uses_envelope -v`
Expected: FAIL with `TypeError: _guess_geometry() got unexpected keyword argument 'envelope'`

- [ ] **Step 3: Add `envelope` parameter to `_guess_geometry()`**

In `codegen/gen_parts.py`, modify `_guess_geometry` signature and add Priority 0 block at the top:

```python
def _guess_geometry(name_cn: str, material: str, envelope: tuple = None) -> dict:
    """Infer approximate geometry type and dimensions for a custom part.

    Priority 0: §6.4 envelope dimensions (most accurate, multi-source).
    Priority 1: Parse explicit dimensions from BOM material column.
    Priority 2: Keyword-based heuristics from part name.
    """
    # ── Priority 0: §6.4 envelope (from parse_envelopes) ──
    if envelope:
        w, d, h = envelope
        is_round = abs(w - d) < 0.1  # w ≈ d → cylindrical
        if is_round:
            # Check for disc_arms special case
            if "法兰" in name_cn and "悬臂" in name_cn:
                arm_l = max(20.0, round(w * 0.5 - d / 4, 1))
                return {"type": "disc_arms", "d": w, "arm_l": arm_l,
                        "arm_w": 12.0, "t": h, "arm_count": 4,
                        "envelope_w": w + arm_l * 2, "envelope_d": d + arm_l * 2,
                        "envelope_h": h}
            if "环" in name_cn or "绝缘" in name_cn:
                return {"type": "ring", "od": w, "id": round(w * 0.75, 1), "h": h,
                        "envelope_w": w, "envelope_d": d, "envelope_h": h}
            return {"type": "cylinder", "d": w, "h": h,
                    "envelope_w": w, "envelope_d": d, "envelope_h": h}
        else:
            if "支架" in name_cn and ("L" in name_cn or "抱箍" in name_cn):
                return {"type": "l_bracket", "w": w, "d": d, "h": h, "t": 3.0,
                        "envelope_w": w, "envelope_d": d, "envelope_h": h}
            return {"type": "box", "w": w, "d": d, "h": h,
                    "envelope_w": w, "envelope_d": d, "envelope_h": h}

    # ── Priority 1: Parse explicit dimensions from material text ──
    # ... (existing code unchanged)
```

- [ ] **Step 4: Wire up envelope lookup at the call site**

In `codegen/gen_parts.py`, around the `generate_part_modules()` function, add envelope loading before the parts loop:

```python
    # Parse §6.4 envelope dimensions (most accurate source)
    from codegen.gen_assembly import parse_envelopes
    envelopes = parse_envelopes(spec_path)

    for p in parts:
        # ...existing filters...

        envelope = envelopes.get(p["part_no"])
        geom = _guess_geometry(p["name_cn"], p["material"], envelope=envelope)
```

- [ ] **Step 5: Run all tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_assembly_coherence.py -v`
Expected: all 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add codegen/gen_parts.py tests/test_assembly_coherence.py
git commit -m "feat: gen_parts reads §6.4 envelopes as Priority 0 geometry source"
```

---

### Task 3: Fix assembly stacking — anchor-relative positioning

**Files:**
- Modify: `codegen/gen_assembly.py:398-501` (`_resolve_child_offsets`)
- Modify: `tests/test_assembly_coherence.py`

This is the core fix. Currently auto-stacked parts accumulate `cursor += extent + gap` from 0, producing large offsets. The fix uses §6.2 **anchor points** (parts with explicit Z values) and fills gaps between anchors using actual envelope heights.

**New algorithm:**
1. Collect anchors from §6.2/§6.3 (parts with known Z values)
2. For each sub-assembly, sort parts by BOM order
3. Parts with anchors: use their Z directly
4. Parts without anchors: stack adjacently from nearest anchor, using §6.4 heights
5. Default stacking gap = 0mm (parts touch), not 2mm

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assembly_coherence.py`:

```python
def test_flange_assembly_z_span():
    """法兰总成 parts should span ≤100mm, not 360mm."""
    spec = os.path.join(os.path.dirname(__file__), "..",
                        "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.isfile(spec):
        import pytest
        pytest.skip("No end_effector CAD_SPEC.md available")

    from codegen.gen_assembly import _resolve_child_offsets, _extract_all_layer_poses
    from codegen.gen_assembly import parse_assembly_pose, parse_envelopes
    from codegen.gen_build import parse_bom_tree

    parts = parse_bom_tree(spec)
    pose = parse_assembly_pose(spec)
    layer_poses = _extract_all_layer_poses(pose, parts)
    offsets = _resolve_child_offsets(parts, layer_poses, spec)

    # Collect Z offsets for GIS-EE-001-xx parts (法兰总成)
    flange_zs = [off[2] for pno, off in offsets.items()
                 if pno.startswith("GIS-EE-001-")]
    if not flange_zs:
        import pytest
        pytest.skip("No flange parts found")

    z_span = max(flange_zs) - min(flange_zs)
    assert z_span <= 120.0, (
        f"法兰总成 Z-span is {z_span:.0f}mm (should be ≤120mm). "
        f"Parts are still scattered."
    )


def test_station_parts_compact():
    """Each workstation's parts should span ≤200mm along stacking axis."""
    spec = os.path.join(os.path.dirname(__file__), "..",
                        "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.isfile(spec):
        import pytest
        pytest.skip("No end_effector CAD_SPEC.md available")

    from codegen.gen_assembly import _resolve_child_offsets, _extract_all_layer_poses
    from codegen.gen_assembly import parse_assembly_pose
    from codegen.gen_build import parse_bom_tree

    parts = parse_bom_tree(spec)
    pose = parse_assembly_pose(spec)
    layer_poses = _extract_all_layer_poses(pose, parts)
    offsets = _resolve_child_offsets(parts, layer_poses, spec)

    for station_prefix in ["GIS-EE-002-", "GIS-EE-003-", "GIS-EE-004-", "GIS-EE-005-"]:
        station_zs = [off[2] for pno, off in offsets.items()
                      if pno.startswith(station_prefix)]
        if not station_zs:
            continue
        z_span = max(station_zs) - min(station_zs)
        assert z_span <= 200.0, (
            f"{station_prefix} Z-span is {z_span:.0f}mm (should be ≤200mm)"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_assembly_coherence.py::test_flange_assembly_z_span -v`
Expected: FAIL with `Z-span is 359mm (should be ≤120mm)`

- [ ] **Step 3: Rewrite `_resolve_child_offsets()` with anchor-relative stacking**

Replace the auto-stacking logic in `_resolve_child_offsets()` (lines 470-500 approximately) with:

```python
        if not auto_queue:
            continue

        # ── NEW: Envelope-aware anchor-relative stacking ──
        envelopes = parse_envelopes(spec_path) if spec_path else {}

        def _get_height(child):
            """Get part height from §6.4 envelope, BOM dims, or default."""
            env = envelopes.get(child["part_no"])
            if env:
                return env[2]  # h component
            text = child.get("material", "") + " " + child.get("name_cn", "")
            dims = _parse_dims_text(text)
            if dims:
                return dims[2]  # h component
            return 15.0  # conservative default

        # Sort auto_queue by BOM order (already in BOM order from parse)
        # Find nearest anchor Z to seed the stack
        anchor_zs = [result[cpno][2] for cpno in result
                     if cpno.startswith(prefix + "-")]
        if anchor_zs:
            # Stack downward from the lowest anchor (workstation-side convention)
            seed_z = min(anchor_zs)
        else:
            # No anchor: start from the assembly's base Z (usually 0 or from §6.2)
            assy_z = sp.get("z", 0.0) if sp.get("z") is not None else 0.0
            seed_z = assy_z

        # Determine stacking direction from axis_dir
        default_direction = _infer_stack_direction(assy_axis_dir)
        dz_sign = default_direction[2]  # -1 for downward, +1 for upward
        if dz_sign == 0:
            dz_sign = -1  # default downward

        cursor_z = seed_z
        for child in auto_queue:
            cpno = child["part_no"]
            h = _get_height(child)

            # Place part: bottom at cursor, center at cursor + h/2 * direction
            if dz_sign < 0:
                # Stacking downward: cursor moves to more negative Z
                center_z = cursor_z - h / 2.0
                cursor_z -= h  # next part starts below this one
            else:
                # Stacking upward
                center_z = cursor_z + h / 2.0
                cursor_z += h

            # Check for per-part horizontal direction override
            clause = _match_axis_clause(assy_axis_dir, child["name_cn"])
            if clause and any(k in clause for k in ["∥XY", "水平", "径向"]):
                # This part's axis is horizontal — offset in X, not Z
                result[cpno] = (round(center_z, 1), 0, 0)
            else:
                result[cpno] = (0, 0, round(center_z, 1))
```

Also set `_STACK_GAP_MM = 0.0` at line 341 to eliminate gaps.

- [ ] **Step 4: Run tests**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_assembly_coherence.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codegen/gen_assembly.py tests/test_assembly_coherence.py
git commit -m "fix: anchor-relative stacking eliminates scattered assembly positioning"
```

---

### Task 4: gen_std_parts.py reads §6.4 envelopes

**Files:**
- Modify: `codegen/gen_std_parts.py` (dimension lookup)

Currently `gen_std_parts.py` uses a 3-tier lookup: model match → BOM regex → category fallback. Add §6.4 envelope as Priority 0 (before model match).

- [ ] **Step 1: Find the dimension lookup code**

In `codegen/gen_std_parts.py`, find where dimensions are resolved. Look for `lookup_std_part_dims` or the dimension selection block.

- [ ] **Step 2: Add §6.4 envelope as highest-priority source**

At the start of the per-part dimension resolution, add:

```python
    # Priority 0: §6.4 envelope (most accurate multi-source data)
    from codegen.gen_assembly import parse_envelopes
    envelopes = parse_envelopes(spec_path)

    # ...inside the per-part loop, before existing dim lookup:
    env = envelopes.get(child["part_no"])
    if env:
        w, d, h = env
        if abs(w - d) < 0.1:  # cylindrical
            dims = {"d": w, "l": h}
        else:
            dims = {"w": w, "d": d, "h": h}
    else:
        dims = lookup_std_part_dims(...)  # existing fallback
```

- [ ] **Step 3: Run build test**

```bash
cd D:/Work/cad-spec-gen
CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT python cad_pipeline.py codegen --subsystem end_effector --force
```

Verify no errors (exit code 0 or 2 for TODO warnings).

- [ ] **Step 4: Commit**

```bash
git add codegen/gen_std_parts.py
git commit -m "feat: gen_std_parts reads §6.4 envelopes for accurate purchased part sizing"
```

---

### Task 5: Integration test — full pipeline rebuild + visual verify

**Files:**
- No code changes — this is a verification task

- [ ] **Step 1: Clean test output**

```bash
rm -rf D:/Work/cad-tests/GISBOT/cad/end_effector/*.py
rm -rf D:/Work/cad-tests/GISBOT/cad/output/*
```

- [ ] **Step 2: Re-run Phase 1 SPEC (should be cached)**

```bash
cd D:/Work/cad-spec-gen
CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT python cad_pipeline.py spec \
  --subsystem end_effector \
  --design-doc "D:/Work/cad-tests/04-末端执行机构设计.md" \
  --auto-fill --force
```

- [ ] **Step 3: Re-run Phase 2 CODEGEN**

```bash
CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT python cad_pipeline.py codegen \
  --subsystem end_effector --force
```

Auto-fill any TODO markers as before.

- [ ] **Step 4: Re-run Phase 3 BUILD**

```bash
CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT python cad_pipeline.py build \
  --subsystem end_effector --skip-orientation
```

Expected: BUILD succeeds, GLB exported.

- [ ] **Step 5: Re-run Phase 4 RENDER**

```bash
CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT python cad_pipeline.py render \
  --subsystem end_effector
```

Expected: 7 views rendered.

- [ ] **Step 6: Visual verification**

Open the rendered V1 and V5 PNGs. Verify:
- Parts are visually grouped (not scattered)
- 法兰总成 in center appears as a compact disc, not a vertical tower
- 4 workstation modules hang below the flange at 0°/90°/180°/270°
- No parts floating far from the main body

- [ ] **Step 7: Commit test results**

```bash
git add -A
git commit -m "test: verify assembly coherence fix with end_effector pipeline"
```
