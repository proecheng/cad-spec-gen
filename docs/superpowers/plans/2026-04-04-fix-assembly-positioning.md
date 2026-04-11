# Fix Assembly Per-Part Positioning — Implementation Plan (Rev.2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `codegen/gen_assembly.py` and `templates/assembly.py.j2` so that codegen produces assembly.py files with correct per-part positioning — no overlapping parts, no lost Z offsets, and automatic stacking for station-internal parts.

**Architecture:** Three-layer fix: (1) enhance the §6.2 parser to extract ALL position data including Z-only offsets and name-based fallback for rows without part_no; (2) add an offset resolver that computes per-part `(dx, dy, dz)` using explicit §6.2 data + per-part axis_dir sub-clause matching + auto-stacking from envelope dimensions; (3) update the Jinja2 template to render per-part translate calls. Data flows: `CAD_SPEC.md §6.2` → `_extract_all_layer_poses()` → `_resolve_child_offsets()` → template `local_offset`.

**Tech Stack:** Python 3.10+, Jinja2, regex, CadQuery (Workplane.translate)

---

## Root Cause Summary

`gen_assembly.py:_extract_station_pose()` only matches §6.2 rows containing **both** `θ=` and `R=`, silently dropping rows with Z-only offsets (flange-internal parts L1–L4). Rows without a `GIS-XX-NNN` part number (e.g., "ECX 22L电机+GP22C减速器" with Z=+73mm) are also silently dropped. Additionally, station children all receive the same `(tx, ty, tz)` with no per-part relative offset. The template has no `translate()` slot for per-part positioning.

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `codegen/gen_assembly.py` | Modify | Add `_extract_all_layer_poses()`, `_parse_dims_text()`, `_resolve_child_offsets()`, `_match_axis_clause()`. Update `generate_assembly()`. |
| `templates/assembly.py.j2` | Modify | Add per-part `translate()` rendering slot. |
| `tests/test_gen_assembly.py` | Create | Unit tests for new parsers and offset resolver. |

No new modules are created. All logic stays in `gen_assembly.py`. Dimension parsing reuses the same regex patterns as `gen_parts._guess_geometry()` (duplicated as a small local function to avoid cross-generator coupling).

## Data Flow Diagram

```
CAD_SPEC.md §6.2 装配层叠表
  ├─ rows with part_no (GIS-XX-NNN)  ──┐
  ├─ rows without part_no              ──┤  _extract_all_layer_poses(pose, bom_parts)
  │   (name-keyword fallback → BOM)    ──┤       ↓
  └─ axis_dir column                   ──┘  layer_poses: {part_no: {z, r, θ, axis_dir}}
                                                 ↓
CAD_SPEC.md §5 BOM                       _resolve_child_offsets()
  ├─ parse_bom_tree()              ──→       ↓
  ├─ material field dims           ──→   per_part_offsets: {part_no: "(dx, dy, dz)"}
  └─ axis_dir sub-clause per part  ──→       ↓
                                         generate_assembly()
                                              ↓
                                         assembly.py.j2  →  assembly.py
```

## Consistency Contract

1. **§6.2 explicit Z/R/θ always wins** — auto-stacking never overrides an explicit offset from the design spec.
2. **Per-part axis_dir sub-clause** — if axis_dir contains comma-separated clauses (e.g., "壳体轴沿-Z，储罐轴∥XY"), each child part matches its own clause for both rotation AND stacking direction.
3. **Local offset applied before station transform** — in the station-local frame (pre-rotation). The Jinja2 rendering order is: `make()` → `rotate()` → `translate(local)` → `_station_transform()`.
4. **Part_no matching with name fallback** — `GIS-XX-NNN(-NN)?` pattern is the primary key. For §6.2 rows without part_no, name keywords are matched against BOM entries as fallback.
5. **Non-radial parts get Z-only offset** — parts not in a radial station (e.g., flange internals) get `translate((0, 0, z))` directly, no station_transform.
6. **Part origin convention** — all `ee_*.py` scaffolds place the part bottom face at Z=0 (extrude upward). Auto-stacking relies on this: the first part's bottom sits at the computed offset, and extends upward by its height.
7. **Orphan assemblies** — assemblies with no §6.2 pose and no parent pose get a safe default offset (Z=+assembly_envelope_h) to avoid overlapping with the main assembly.

## Out of Scope

- **Flange diameter Φ80→Φ90**: `gen_parts.py:_guess_geometry()` defaults to Φ80 instead of reading `params.py:FLANGE_DIA`. Tracked separately; not a gen_assembly/template issue.

---

## Task 1: Unit tests for layer pose extraction

**Files:**
- Create: `tests/test_gen_assembly.py`

- [ ] **Step 1: Create test file with fixtures**

```python
# tests/test_gen_assembly.py
"""Tests for codegen/gen_assembly.py positioning logic."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "codegen"))


@pytest.fixture
def sample_layers():
    """Simulated parse_assembly_pose() output with mixed offset types."""
    return {"layers": [
        {"level": "L1", "part": "适配板 (GIS-XX-001-08)", "fix_move": "固定",
         "connection": "4×M6", "offset": "基准原点", "axis_dir": "盘面∥XY"},
        {"level": "L2", "part": "ECX 22L电机+GP22C减速器", "fix_move": "固定",
         "connection": "4×M3", "offset": "Z=+73mm(向上)", "axis_dir": "轴沿Z"},
        {"level": "L3", "part": "法兰 Φ90mm (GIS-XX-001-01)", "fix_move": "旋转",
         "connection": "过盈配合", "offset": "Z=0(参考面)", "axis_dir": "盘面∥XY"},
        {"level": "L4", "part": "PEEK环 (GIS-XX-001-02)", "fix_move": "随旋转",
         "connection": "6×M3", "offset": "Z=-27mm(向下)", "axis_dir": "盘面∥XY"},
        {"level": "L5a", "part": "工位A (GIS-XX-002)", "fix_move": "随旋转",
         "connection": "4×M3", "offset": "R=65mm, θ=0°", "axis_dir": "轴沿-Z"},
        {"level": "L5b", "part": "工位B (GIS-XX-003)", "fix_move": "随旋转",
         "connection": "4×M3", "offset": "R=65mm, θ=90°", "axis_dir": "轴沿-Z"},
    ]}


@pytest.fixture
def sample_bom_for_layers():
    """BOM parts for name-fallback matching in layer pose extraction."""
    return [
        {"part_no": "GIS-XX-001-05", "name_cn": "伺服电机", "is_assembly": False,
         "material": "Maxon ECX SPEED 22L", "make_buy": "外购", "quantity": "1"},
        {"part_no": "GIS-XX-001-06", "name_cn": "行星减速器", "is_assembly": False,
         "material": "Maxon GP22C", "make_buy": "外购", "quantity": "1"},
    ]


def test_extract_z_only(sample_layers, sample_bom_for_layers):
    from gen_assembly import _extract_all_layer_poses
    poses = _extract_all_layer_poses(sample_layers, sample_bom_for_layers)
    # L1: origin
    assert poses["GIS-XX-001-08"]["z"] == 0.0
    assert poses["GIS-XX-001-08"]["is_origin"] is True
    # L3: explicit Z=0
    assert poses["GIS-XX-001-01"]["z"] == 0.0
    # L4: negative Z
    assert poses["GIS-XX-001-02"]["z"] == -27.0


def test_extract_radial(sample_layers, sample_bom_for_layers):
    from gen_assembly import _extract_all_layer_poses
    poses = _extract_all_layer_poses(sample_layers, sample_bom_for_layers)
    assert poses["GIS-XX-002"]["r"] == 65.0
    assert poses["GIS-XX-002"]["theta"] == 0.0
    assert poses["GIS-XX-003"]["theta"] == 90.0


def test_extract_axis_dir(sample_layers, sample_bom_for_layers):
    from gen_assembly import _extract_all_layer_poses
    poses = _extract_all_layer_poses(sample_layers, sample_bom_for_layers)
    assert poses["GIS-XX-001-01"]["axis_dir"] == "盘面∥XY"
    assert poses["GIS-XX-002"]["axis_dir"] == "轴沿-Z"


def test_extract_name_fallback(sample_layers, sample_bom_for_layers):
    """L2 row has no part_no — should match BOM entry by '电机' keyword."""
    from gen_assembly import _extract_all_layer_poses
    poses = _extract_all_layer_poses(sample_layers, sample_bom_for_layers)
    # Motor (GIS-XX-001-05) matched via '电机' keyword in "ECX 22L电机+GP22C减速器"
    assert "GIS-XX-001-05" in poses
    assert poses["GIS-XX-001-05"]["z"] == 73.0


def test_extract_empty():
    from gen_assembly import _extract_all_layer_poses
    assert _extract_all_layer_poses({"layers": []}, []) == {}
    assert _extract_all_layer_poses({}, []) == {}
```

- [ ] **Step 2: Run tests — expect ImportError (function doesn't exist yet)**

Run: `cd D:\Work\cad-spec-gen && python -m pytest tests/test_gen_assembly.py -v`
Expected: FAIL with `ImportError: cannot import name '_extract_all_layer_poses'`

- [ ] **Step 3: Commit test skeleton**

```bash
git add tests/test_gen_assembly.py
git commit -m "test: add test skeleton for gen_assembly layer pose extraction"
```

---

## Task 2: Implement `_extract_all_layer_poses()`

**Files:**
- Modify: `codegen/gen_assembly.py:218-259` (replace `_extract_station_pose`)

- [ ] **Step 1: Add `_extract_all_layer_poses()` below `_extract_origin_axis()`**

Insert after line 277 in `codegen/gen_assembly.py`:

```python
def _match_bom_by_keywords(part_text: str, bom_parts: list) -> list:
    """Match §6.2 part_text against BOM entries by name keywords.

    Splits part_text into Chinese character runs and tries to match
    each BOM entry's name_cn. Returns list of matched part_no strings.

    Example: "ECX 22L电机+GP22C减速器" → keywords ["电机", "减速器"]
             → matches BOM entries "伺服电机" (GIS-XX-001-05)
               and "行星减速器" (GIS-XX-001-06)
    """
    # Extract Chinese keyword segments (≥2 chars)
    keywords = re.findall(r"[\u4e00-\u9fff]{2,}", part_text)
    if not keywords:
        return []

    matched = []
    for part in bom_parts:
        if part.get("is_assembly"):
            continue
        name = part.get("name_cn", "")
        for kw in keywords:
            if kw in name:
                matched.append(part["part_no"])
                break
    return matched


def _extract_all_layer_poses(pose: dict, bom_parts: list = None) -> dict:
    """Extract per-part positioning from §6.2 layer stacking table.

    Unlike _extract_station_pose (which only captures θ+R pairs), this
    function captures ALL positioning data:
      - Z-only offsets  (e.g. "Z=+73mm")
      - R+θ radial positions (e.g. "R=65mm, θ=0°")
      - "基准原点" as Z=0, is_origin=True
      - axis_dir text for each entry

    For rows without a GIS-XX-NNN part number (e.g. "ECX 22L电机+GP22C减速器"),
    falls back to name-keyword matching against bom_parts.

    Returns {part_no: {"z": float|None, "r": float|None, "theta": float|None,
                        "axis_dir": str, "is_origin": bool}}.
    """
    if bom_parts is None:
        bom_parts = []
    result = {}

    for layer in pose.get("layers", []):
        part_text = layer.get("part", "")
        offset_text = layer.get("offset", "")
        axis_dir = layer.get("axis_dir", "")

        # Skip rows with no useful offset
        if not offset_text or offset_text.strip() in ("—", "-", ""):
            # Still try to index if part_no exists (for axis_dir propagation)
            m_pno = re.search(r"(GIS-\w+-\d+(?:-\d+)?)", part_text)
            if m_pno:
                result.setdefault(m_pno.group(1), {
                    "z": None, "r": None, "theta": None,
                    "axis_dir": axis_dir, "is_origin": False})
            continue

        # Parse offset values
        entry = {"z": None, "r": None, "theta": None,
                 "axis_dir": axis_dir, "is_origin": False}

        # "基准原点" → Z=0, origin marker
        if "基准" in offset_text or "原点" in offset_text:
            entry["z"] = 0.0
            entry["is_origin"] = True

        # Z=±NNNmm (with optional parenthetical)
        m_z = re.search(r"Z\s*=\s*([+-]?\d+(?:\.\d+)?)\s*mm", offset_text)
        if m_z:
            entry["z"] = float(m_z.group(1))

        # Z=0 written as "Z=0(参考面)" — no "mm" suffix
        if entry["z"] is None:
            m_z0 = re.search(r"Z\s*=\s*0(?:\s*\(|$)", offset_text)
            if m_z0:
                entry["z"] = 0.0

        # R=NNNmm (also handle ≈)
        m_r = re.search(r"R\s*[=≈]\s*(\d+(?:\.\d+)?)\s*mm", offset_text)
        if m_r:
            entry["r"] = float(m_r.group(1))

        # θ=NNN°
        m_theta = re.search(r"θ\s*=\s*(\d+(?:\.\d+)?)\s*°?", offset_text)
        if m_theta:
            entry["theta"] = float(m_theta.group(1))

        # Determine target part_no(s) for this row
        m_pno = re.search(r"(GIS-\w+-\d+(?:-\d+)?)", part_text)
        if m_pno:
            result[m_pno.group(1)] = entry
        else:
            # Name-keyword fallback: match BOM entries
            matched_pnos = _match_bom_by_keywords(part_text, bom_parts)
            for pno in matched_pnos:
                result[pno] = dict(entry)  # copy so each gets independent dict

    return result
```

- [ ] **Step 2: Run tests**

Run: `cd D:\Work\cad-spec-gen && python -m pytest tests/test_gen_assembly.py -v`
Expected: All 5 tests PASS (including `test_extract_name_fallback` which verifies motor Z=+73)

- [ ] **Step 3: Commit**

```bash
git add codegen/gen_assembly.py tests/test_gen_assembly.py
git commit -m "feat: add _extract_all_layer_poses() with name-fallback matching"
```

---

## Task 3: Add dimension parser and tests

**Files:**
- Modify: `codegen/gen_assembly.py`
- Modify: `tests/test_gen_assembly.py`

- [ ] **Step 1: Add dimension tests**

Append to `tests/test_gen_assembly.py`:

```python
def test_parse_dims_text_cylinder():
    from gen_assembly import _parse_dims_text
    w, d, h = _parse_dims_text("SUS316L不锈钢 Φ38×280mm")
    assert (w, d, h) == (38.0, 38.0, 280.0)


def test_parse_dims_text_box():
    from gen_assembly import _parse_dims_text
    w, d, h = _parse_dims_text("6063铝合金 140×100×55mm")
    assert (w, d, h) == (140.0, 100.0, 55.0)


def test_parse_dims_text_diameter_only():
    from gen_assembly import _parse_dims_text
    w, d, h = _parse_dims_text("PEEK Φ86mm")
    assert w == 86.0
    assert h > 0  # auto-estimated


def test_parse_dims_text_no_dims():
    from gen_assembly import _parse_dims_text
    assert _parse_dims_text("7075-T6铝合金") is None
    assert _parse_dims_text("") is None
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `cd D:\Work\cad-spec-gen && python -m pytest tests/test_gen_assembly.py::test_parse_dims_text_cylinder -v`
Expected: FAIL

- [ ] **Step 3: Implement `_parse_dims_text()`**

Add to `codegen/gen_assembly.py` (below `_extract_all_layer_poses`):

```python
def _parse_dims_text(text: str):
    """Extract (w, d, h) envelope from a text containing dimension specs.

    Handles:
      - Cylinder:  "Φ38×280mm" → (38, 38, 280)
      - Box:       "140×100×55mm" → (140, 100, 55)
      - Disc:      "Φ86mm" → (86, 86, estimated_h)

    Returns (w, d, h) tuple or None if no dimensions found.
    """
    if not text:
        return None

    # Cylinder: Φd×h
    m = re.search(r"[Φφ](\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm", text)
    if m:
        d, h = float(m.group(1)), float(m.group(2))
        return (d, d, h)

    # Box: w×d×h (three numbers separated by ×)
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm",
        text)
    if m:
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)))

    # Diameter only: Φd
    m = re.search(r"[Φφ](\d+(?:\.\d+)?)\s*mm", text)
    if m:
        d = float(m.group(1))
        return (d, d, max(5.0, round(d * 0.25, 1)))

    return None
```

- [ ] **Step 4: Run tests**

Run: `cd D:\Work\cad-spec-gen && python -m pytest tests/test_gen_assembly.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add codegen/gen_assembly.py tests/test_gen_assembly.py
git commit -m "feat: add _parse_dims_text() for envelope dimension extraction"
```

---

## Task 4: Implement `_resolve_child_offsets()` and tests

**Files:**
- Modify: `codegen/gen_assembly.py`
- Modify: `tests/test_gen_assembly.py`

This is the core algorithm. It computes a `(dx, dy, dz)` local offset for each child part within each assembly.

### Algorithm

```
For each assembly:
  1. Collect all child parts from BOM
  2. For each child:
     a. If child part_no has explicit Z in layer_poses → use as local Z offset
     b. Else → queue for auto-stacking
  3. Auto-stack queued parts:
     a. For each child, match its axis_dir sub-clause from parent assembly's
        axis_dir field (e.g. "壳体轴沿-Z，储罐轴∥XY" → 壳体 gets -Z, 储罐 gets +X)
     b. Group by stacking direction
     c. Sort each group: custom-made bodies first → then by size descending
     d. cursor starts at 0 (positive scalar distance along direction)
        → offset_vector = direction * cursor
        → cursor += part_extent + gap
```

### Key design: cursor is always a positive scalar

The `direction` vector (e.g. `(0,0,-1)` for -Z) handles the sign.
`cursor` is the scalar distance traveled along that direction and always increases.
`offset = direction * cursor` produces the correct signed vector.

```
Example: -Z stacking, direction=(0,0,-1)
  Part 1 (body h=55):  cursor=0   → offset=(0,0,0)    → cursor=57
  Part 2 (pump h=20):  cursor=57  → offset=(0,0,-57)   → cursor=79
  Part 3 (conn h=20):  cursor=79  → offset=(0,0,-79)   → cursor=101
```

- [ ] **Step 1: Add tests for offset resolution**

Append to `tests/test_gen_assembly.py`:

```python
@pytest.fixture
def sample_bom():
    """Minimal BOM tree with one assembly + 3 children."""
    return [
        {"part_no": "GIS-XX-002", "name_cn": "工位A", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-002-01", "name_cn": "壳体", "is_assembly": False,
         "material": "铝合金 60×40×55mm", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-002-02", "name_cn": "储罐", "is_assembly": False,
         "material": "不锈钢 Φ38×280mm", "make_buy": "外购", "quantity": "1"},
        {"part_no": "GIS-XX-002-03", "name_cn": "泵", "is_assembly": False,
         "material": "—", "make_buy": "外购", "quantity": "1"},
    ]


def test_offsets_explicit_z(sample_bom):
    """Parts with explicit Z in layer_poses get that Z directly."""
    from gen_assembly import _resolve_child_offsets
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0, "axis_dir": "轴沿-Z",
                        "is_origin": False},
        "GIS-XX-002-01": {"z": -10.0, "r": None, "theta": None,
                           "axis_dir": "", "is_origin": False},
    }
    offsets = _resolve_child_offsets(sample_bom, layer_poses)
    assert offsets["GIS-XX-002-01"] == (0, 0, -10.0)


def test_offsets_auto_stack_no_overlap(sample_bom):
    """Parts without explicit Z get auto-stacked — all offsets distinct."""
    from gen_assembly import _resolve_child_offsets
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0, "axis_dir": "轴沿-Z",
                        "is_origin": False},
    }
    offsets = _resolve_child_offsets(sample_bom, layer_poses)
    zs = [offsets[p["part_no"]][2] for p in sample_bom if not p["is_assembly"]]
    assert len(set(zs)) == len(zs), f"Duplicate Z offsets: {zs}"
    # -Z stacking: all Z should be ≤ 0
    assert all(z <= 0 for z in zs), f"Expected all Z ≤ 0 for -Z stacking: {zs}"


def test_offsets_auto_stack_order(sample_bom):
    """Auto-stacked parts: body (自制) closest to mount, bought parts further."""
    from gen_assembly import _resolve_child_offsets
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0, "axis_dir": "轴沿-Z",
                        "is_origin": False},
    }
    offsets = _resolve_child_offsets(sample_bom, layer_poses)
    z_body = offsets["GIS-XX-002-01"][2]   # 壳体 (自制)
    z_tank = offsets["GIS-XX-002-02"][2]   # 储罐 (外购)
    z_pump = offsets["GIS-XX-002-03"][2]   # 泵 (外购)
    # Body should be closest to mount (least negative Z for -Z stacking)
    assert z_body >= z_tank, f"Body {z_body} should be above tank {z_tank}"
    assert z_body >= z_pump, f"Body {z_body} should be above pump {z_pump}"


def test_offsets_per_part_axis_dir():
    """Parts with different axis_dir sub-clauses get different stacking axes."""
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-002", "name_cn": "涂抹工位", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-002-01", "name_cn": "壳体", "is_assembly": False,
         "material": "铝合金 60×40×55mm", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-002-02", "name_cn": "储罐", "is_assembly": False,
         "material": "不锈钢 Φ38×280mm", "make_buy": "外购", "quantity": "1"},
    ]
    layer_poses = {
        "GIS-XX-002": {"z": None, "r": 65, "theta": 0,
                        "axis_dir": "壳体轴沿-Z（垂直向下），储罐轴∥XY（水平径向外伸）",
                        "is_origin": False},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    # 壳体: -Z stacking → only Z component non-zero
    assert offsets["GIS-XX-002-01"][0] == 0  # no X offset
    assert offsets["GIS-XX-002-01"][2] <= 0  # -Z
    # 储罐: ∥XY stacking → X component non-zero
    assert offsets["GIS-XX-002-02"][0] != 0  # has X offset (radial)
    assert offsets["GIS-XX-002-02"][2] == 0  # no Z


def test_offsets_no_layer_data(sample_bom):
    """When no layer_poses exist, still produce non-overlapping offsets."""
    from gen_assembly import _resolve_child_offsets
    offsets = _resolve_child_offsets(sample_bom, {})
    zs = [offsets[p["part_no"]][2] for p in sample_bom if not p["is_assembly"]]
    assert len(set(zs)) == len(zs), f"Duplicate Z offsets: {zs}"


def test_offsets_non_radial():
    """Flange-internal parts (non-radial) get Z offsets from layer_poses."""
    from gen_assembly import _resolve_child_offsets
    bom = [
        {"part_no": "GIS-XX-001", "name_cn": "法兰总成", "is_assembly": True,
         "material": "—", "make_buy": "总成", "quantity": "1"},
        {"part_no": "GIS-XX-001-01", "name_cn": "法兰", "is_assembly": False,
         "material": "铝合金", "make_buy": "自制", "quantity": "1"},
        {"part_no": "GIS-XX-001-02", "name_cn": "PEEK环", "is_assembly": False,
         "material": "PEEK", "make_buy": "自制", "quantity": "1"},
    ]
    layer_poses = {
        "GIS-XX-001-01": {"z": 0.0, "r": None, "theta": None,
                           "axis_dir": "盘面∥XY", "is_origin": False},
        "GIS-XX-001-02": {"z": -27.0, "r": None, "theta": None,
                           "axis_dir": "盘面∥XY", "is_origin": False},
    }
    offsets = _resolve_child_offsets(bom, layer_poses)
    assert offsets["GIS-XX-001-01"] == (0, 0, 0.0)
    assert offsets["GIS-XX-001-02"] == (0, 0, -27.0)
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `cd D:\Work\cad-spec-gen && python -m pytest tests/test_gen_assembly.py::test_offsets_explicit_z -v`
Expected: FAIL

- [ ] **Step 3: Implement helper functions**

Add to `codegen/gen_assembly.py`:

```python
_STACK_GAP_MM = 2.0  # gap between auto-stacked parts


def _infer_stack_direction(axis_dir: str) -> tuple:
    """Convert axis_dir text to a unit stacking vector (dx, dy, dz).

    Returns the direction in which child parts accumulate from the mount point.
    Default: (0, 0, -1) = hang downward.
    """
    if not axis_dir:
        return (0, 0, -1)
    # "+Z" / "向上" → stack upward
    if any(k in axis_dir for k in ["沿+Z", "+Z", "向上"]):
        return (0, 0, 1)
    # "-Z" / "向下" / "垂直" → stack downward (most common)
    if any(k in axis_dir for k in ["沿-Z", "-Z", "向下", "垂直"]):
        return (0, 0, -1)
    # "∥XY" / "水平" / "径向" → stack radially outward (+X in local frame)
    if any(k in axis_dir for k in ["∥XY", "水平", "径向"]):
        return (1, 0, 0)
    return (0, 0, -1)


def _match_axis_clause(axis_dir: str, part_name: str) -> str:
    """Find the axis_dir sub-clause relevant to a specific part.

    axis_dir may contain comma-separated sub-clauses for different parts,
    e.g. "壳体轴沿-Z（垂直向下），储罐轴∥XY（水平径向外伸）".
    Matches by part_name keywords (first 2-3 chars).

    Returns the matched sub-clause, or empty string if no match.
    """
    if not axis_dir or not part_name:
        return ""
    clauses = re.split(r"[，,]", axis_dir)
    if len(clauses) <= 1:
        return ""  # single clause = applies to all
    for clause in clauses:
        # Match by first 2 chars of part_name (e.g. "壳体", "储罐")
        for n in (3, 2):
            if len(part_name) >= n and part_name[:n] in clause:
                return clause.strip()
    return ""


def _part_height_along(dims, direction: tuple) -> float:
    """Return the part's extent along the given stacking direction.

    dims: (w, d, h) tuple or None.
    direction: unit vector (dx, dy, dz).
    """
    if dims is None:
        return 20.0  # fallback
    w, d, h = dims
    # Map direction to dimension: X→w, Y→d, Z→h
    ax, ay, az = abs(direction[0]), abs(direction[1]), abs(direction[2])
    if az >= ax and az >= ay:
        return h
    if ax >= ay:
        return w
    return d


def _stack_sort_key(child: dict, dims_map: dict, direction: tuple) -> tuple:
    """Sort key for auto-stacking: custom bodies first, then by extent.

    Priority: custom-made (自制) > purchased (外购)
              body/housing (壳体/本体/支架) > other
              larger extent > smaller
    Parts closest to mount surface sort first (lowest key).
    """
    is_custom = "自制" in child.get("make_buy", "")
    is_body = any(k in child["name_cn"]
                  for k in ("壳体", "本体", "支架", "框架", "基座"))
    extent = _part_height_along(dims_map.get(child["part_no"]), direction)
    return (-int(is_custom), -int(is_body), -extent)
```

- [ ] **Step 4: Implement `_resolve_child_offsets()`**

```python
def _resolve_child_offsets(parts: list, layer_poses: dict) -> dict:
    """Compute per-part local offsets for all non-assembly parts.

    Uses §6.2 explicit positions when available; auto-stacks remaining
    parts along the parent assembly's axis_dir. For multi-clause axis_dir
    (e.g. "壳体轴沿-Z，储罐轴∥XY"), each child matches its own sub-clause
    to determine its individual stacking direction.

    Part origin convention: all ee_*.py scaffolds place the part bottom
    face at Z=0 (extrude upward). Auto-stacking offsets position the
    part's bottom face at the computed offset point.

    Returns {part_no: (dx, dy, dz)}.
    """
    result = {}

    # Group parts by parent assembly
    assemblies = [p for p in parts if p["is_assembly"]]
    children_of = {}
    for assy in assemblies:
        prefix = assy["part_no"]
        children_of[prefix] = [
            p for p in parts
            if p["part_no"].startswith(prefix + "-") and not p["is_assembly"]
        ]

    for assy in assemblies:
        prefix = assy["part_no"]
        children = children_of.get(prefix, [])
        if not children:
            continue

        # Assembly-level axis_dir (may contain multi-clause)
        assy_pose = layer_poses.get(prefix, {})
        assy_axis_dir = assy_pose.get("axis_dir", "")
        default_direction = _infer_stack_direction(assy_axis_dir)

        # Separate children into explicit-positioned and auto-stack
        auto_queue = []
        for child in children:
            cpno = child["part_no"]
            if cpno in layer_poses and layer_poses[cpno].get("z") is not None:
                z = layer_poses[cpno]["z"]
                result[cpno] = (0, 0, z)
            else:
                auto_queue.append(child)

        if not auto_queue:
            continue

        # Parse dimensions for auto-queue parts
        dims_map = {}
        for child in auto_queue:
            text = child.get("material", "") + " " + child.get("name_cn", "")
            dims_map[child["part_no"]] = _parse_dims_text(text)

        # Group by per-part stacking direction (from axis_dir sub-clause)
        direction_groups = {}  # {direction_tuple: [children]}
        for child in auto_queue:
            clause = _match_axis_clause(assy_axis_dir, child["name_cn"])
            if clause:
                child_direction = _infer_stack_direction(clause)
            else:
                child_direction = default_direction
            direction_groups.setdefault(child_direction, []).append(child)

        # Stack each direction group independently
        for direction, group in direction_groups.items():
            group.sort(key=lambda c: _stack_sort_key(c, dims_map, direction))
            cursor = 0.0  # positive scalar distance along direction
            for child in group:
                cpno = child["part_no"]
                dims = dims_map.get(cpno)
                extent = _part_height_along(dims, direction)

                # offset_vector = direction * cursor
                dx = round(direction[0] * cursor, 1)
                dy = round(direction[1] * cursor, 1)
                dz = round(direction[2] * cursor, 1)
                result[cpno] = (dx, dy, dz)

                cursor += extent + _STACK_GAP_MM  # always positive

    return result
```

- [ ] **Step 5: Run tests**

Run: `cd D:\Work\cad-spec-gen && python -m pytest tests/test_gen_assembly.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add codegen/gen_assembly.py tests/test_gen_assembly.py
git commit -m "feat: add _resolve_child_offsets() with per-part axis_dir and correct cursor math"
```

---

## Task 5: Update `generate_assembly()` to pass offsets to template

**Files:**
- Modify: `codegen/gen_assembly.py:279-452` (the `generate_assembly` function)

- [ ] **Step 1: Replace `_extract_station_pose` call with new functions**

In `generate_assembly()`, replace lines 311-314:

```python
    # OLD:
    # station_poses = _extract_station_pose(pose)
    # NEW:
    layer_poses = _extract_all_layer_poses(pose, parts)

    # Compute per-part local offsets (explicit §6.2 + auto-stacking)
    part_offsets = _resolve_child_offsets(parts, layer_poses)
```

- [ ] **Step 2: Update station_entry construction to use layer_poses**

Replace the station pose lookup (old lines 397-409) with:

```python
        # Look up this assembly's pose from §6.2
        sp = layer_poses.get(pno, {})
        is_radial = sp.get("r") is not None and sp.get("theta") is not None

        station_entry = {
            "name_cn": name,
            "angle": sp.get("theta", 0.0),
            "is_radial": is_radial,
            "parts": station_parts,
        }
        if is_radial:
            station_entry["mount_radius"] = sp["r"]
            station_entry["base_z"] = sp.get("z") or 0.0
```

- [ ] **Step 3: Add `local_offset` to each part dict**

Inside the loop that builds `station_parts` (both custom and std branches), add `local_offset` from the computed offsets.

For **custom parts** (the `else` branch):

```python
                offset = part_offsets.get(child["part_no"])
                offset_str = (f"({offset[0]}, {offset[1]}, {offset[2]})"
                              if offset and offset != (0, 0, 0) else "")

                station_parts.append({
                    "var": var_name,
                    "make_call": f"{ee_func}()",
                    "local_transform": local_xform,
                    "local_offset": offset_str,
                    "orient_doc_ref": orient_ref or "",
                    "orient_rule": "",
                    "assy_name": f"{prefix_short}-{suffix}-{c_suffix}",
                    "color_var": c_color,
                })
```

Same pattern for **standard parts** (the `if "外购"` branch):

```python
                offset = part_offsets.get(child["part_no"])
                offset_str = (f"({offset[0]}, {offset[1]}, {offset[2]})"
                              if offset and offset != (0, 0, 0) else "")

                station_parts.append({
                    "var": var_name,
                    "make_call": f"{std_func}()",
                    "local_transform": local_xform,
                    "local_offset": offset_str,
                    # ... rest unchanged
                })
```

- [ ] **Step 4: Handle orphan assemblies (no §6.2 pose)**

After the station loop, add a check for assemblies that have no layer_pose AND whose parent also has no pose. These would overlap at origin. Add a safe default offset:

```python
        # Orphan assembly: no §6.2 pose, would overlap at origin
        if not is_radial and not any(
            layer_poses.get(c["part_no"], {}).get("z") is not None
            for c in children
        ):
            # Place above main assembly to avoid overlap
            orphan_z = 100.0  # safe default: 100mm above origin
            for part_dict in station_parts:
                if not part_dict.get("local_offset"):
                    part_dict["local_offset"] = f"(0, 0, {orphan_z})"
                    orphan_z += 30.0
```

- [ ] **Step 5: Remove old `_extract_station_pose` function**

Delete the old `_extract_station_pose()` function (old lines 218-259). It is fully replaced by `_extract_all_layer_poses()`.

- [ ] **Step 6: Verify no remaining references**

Run: `cd D:\Work\cad-spec-gen && grep -rn "_extract_station_pose" codegen/ templates/ tests/`
Expected: No matches.

- [ ] **Step 7: Commit**

```bash
git add codegen/gen_assembly.py
git commit -m "feat: wire per-part offsets into generate_assembly() with orphan handling"
```

---

## Task 6: Update `assembly.py.j2` template

**Files:**
- Modify: `templates/assembly.py.j2:69-81`

- [ ] **Step 1: Add local_offset translate slot**

Replace the part rendering block (lines 69-81) with:

```jinja2
{% for part in station.parts %}

    {{ part.var }} = {{ part.make_call }}
{% if part.local_transform %}
    # Orient: {{ part.orient_doc_ref | default('') }}
    # Rule:   {{ part.orient_rule | default('') }}
    {{ part.var }} = {{ part.local_transform }}
{% endif %}
{% if part.local_offset %}
    {{ part.var }} = {{ part.var }}.translate({{ part.local_offset }})
{% endif %}
{% if station.is_radial %}
    {{ part.var }} = _station_transform({{ part.var }}, _a, _tx, _ty, _tz)
{% endif %}
    assy.add({{ part.var }}, name="{{ part.assy_name }}", color={{ part.color_var }})
{% endfor %}
```

**Rendering order enforced by template:**
1. `make()` — geometry at local origin (bottom face at Z=0)
2. `rotate()` — orient part per axis_dir
3. `translate(local_offset)` — position within station's local frame
4. `_station_transform()` — rotate + translate to radial station position

- [ ] **Step 2: Verify template renders correctly**

Run the codegen on the actual spec and inspect the output:

```bash
cd D:\Work\cad-spec-gen
python codegen/gen_assembly.py cad/end_effector/CAD_SPEC.md --mode force -o /tmp/test_assembly.py
head -180 /tmp/test_assembly.py
```

Expected in output:
- Flange parts should have `.translate((0, 0, -27.0))` etc.
- Motor parts should have `.translate((0, 0, 73.0))` (from name-fallback match)
- Station parts should have `.translate(...)` before `_station_transform(...)`
- No parts should have `translate((0, 0, 0))` (filtered out by empty-string check)
- 储罐 should have an X-component offset (horizontal), not Z-only

- [ ] **Step 3: Commit**

```bash
git add templates/assembly.py.j2
git commit -m "feat: add per-part translate() slot in assembly template"
```

---

## Task 7: Integration test — full codegen → build cycle

**Files:**
- Modify: `tests/test_gen_assembly.py`

- [ ] **Step 1: Add integration test**

Append to `tests/test_gen_assembly.py`:

```python
def test_integration_end_effector():
    """Generate assembly.py for end_effector and verify positioning correctness."""
    spec_path = os.path.join(
        os.path.dirname(__file__), "..", "cad", "end_effector", "CAD_SPEC.md")
    if not os.path.exists(spec_path):
        pytest.skip("end_effector CAD_SPEC.md not found")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from codegen.gen_build import parse_bom_tree
    from gen_assembly import generate_assembly, _extract_all_layer_poses
    from gen_assembly import parse_assembly_pose, _resolve_child_offsets

    content = generate_assembly(spec_path)
    parts = parse_bom_tree(spec_path)
    pose = parse_assembly_pose(spec_path)
    layer_poses = _extract_all_layer_poses(pose, parts)
    offsets = _resolve_child_offsets(parts, layer_poses)

    # 1. Zero offset should never emit a translate call
    assert ".translate((0, 0, 0))" not in content, \
        "Zero offset should not emit a translate call"
    assert ".translate((0.0, 0.0, 0.0))" not in content

    # 2. PEEK ring Z=-27 must be present (from explicit §6.2)
    assert "-27" in content, "PEEK ring Z=-27 offset not found in output"

    # 3. Motor Z=+73 must be present (from name-fallback matching)
    assert "73" in content, "Motor Z=+73 offset not found in output"

    # 4. Each station should have at least one translate before _station_transform
    lines = content.splitlines()
    stations_with_translate = 0
    for i, line in enumerate(lines):
        if "_station_transform" in line:
            # Check preceding 8 lines for a .translate() on same var
            var = line.strip().split("=")[0].strip()
            window = "\n".join(lines[max(0, i - 8):i])
            if ".translate(" in window and var in window:
                stations_with_translate += 1
    assert stations_with_translate >= 4, \
        f"Expected ≥4 station parts with translate, got {stations_with_translate}"

    # 5. Offsets map should have no duplicate positions within any assembly
    assemblies = [p for p in parts if p["is_assembly"]]
    for assy in assemblies:
        prefix = assy["part_no"]
        child_offsets = [
            offsets[p["part_no"]]
            for p in parts
            if p["part_no"].startswith(prefix + "-")
            and not p["is_assembly"]
            and p["part_no"] in offsets
        ]
        if len(child_offsets) > 1:
            assert len(set(child_offsets)) == len(child_offsets), \
                f"Duplicate offsets in {prefix}: {child_offsets}"
```

- [ ] **Step 2: Run the full test suite**

Run: `cd D:\Work\cad-spec-gen && python -m pytest tests/test_gen_assembly.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full pipeline rebuild**

```bash
cd D:\Work\cad-spec-gen
CAD_OUTPUT_DIR="D:/Work/cad-tests/GISBOT" python cad_pipeline.py codegen --subsystem end_effector --force
CAD_OUTPUT_DIR="D:/Work/cad-tests/GISBOT" python cad_pipeline.py build --subsystem end_effector --skip-orientation
```

Verify:
- `cad/end_effector/assembly.py` contains `.translate()` calls
- Build produces `EE-000_assembly.glb` without errors
- Visual inspection: flange disc visible, parts not overlapping at station centers

- [ ] **Step 4: Commit**

```bash
git add tests/test_gen_assembly.py
git commit -m "test: add comprehensive integration test for assembly positioning"
```

---

## Task 8: Clean up and document

**Files:**
- Modify: `codegen/gen_assembly.py`

- [ ] **Step 1: Verify `_extract_station_pose` is fully removed**

Run: `grep -rn "station_pose\|_extract_station" codegen/ templates/`
Expected: Only `_extract_all_layer_poses` and `layer_poses` references remain.

- [ ] **Step 2: Update docstring in `generate_assembly()`**

```python
def generate_assembly(spec_path: str) -> str:
    """Generate assembly.py scaffold content.

    Reads §5 BOM, §4 connections, §6 assembly pose from CAD_SPEC.md.
    Computes per-part positioning:
      - Explicit: Z/R/θ from §6.2 layer stacking table (part_no or name-fallback)
      - Per-part axis: multi-clause axis_dir matched by part name keywords
      - Auto-stacked: parts without explicit positions stacked along their
        matched axis_dir with envelope-based spacing
      - Orphan assemblies: no §6.2 pose → safe default offset to avoid overlap
    Part origin convention: bottom face at Z=0, extrude upward.
    """
```

- [ ] **Step 3: Final test run**

Run: `cd D:\Work\cad-spec-gen && python -m pytest tests/test_gen_assembly.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add codegen/gen_assembly.py
git commit -m "chore: remove deprecated _extract_station_pose, document positioning contract"
```

---

## Review Findings — Resolved

| # | 严重度 | 问题 | 解决方式 | 所在 Task |
|---|--------|------|---------|-----------|
| 1 | 🔴 P0 | cursor 方向乘法 Bug | cursor 始终为正标量，direction 负责符号 | Task 4 |
| 2 | 🔴 P0 | 无 part_no 行丢弃电机 Z=+73mm | `_match_bom_by_keywords()` 名称回退匹配 | Task 2 |
| 3 | 🟡 P1 | 工位内零件多轴线方向 | `_match_axis_clause()` + 按方向分组堆叠 | Task 4 |
| 4 | 🟡 P1 | 堆叠排序应优先主体结构件 | `_stack_sort_key()`: 自制→壳体→尺寸 | Task 4 |
| 5 | 🟡 P1 | GIS-EE-006 无 pose 默认偏移 | orphan assembly 检测 + Z=+100mm 安全偏移 | Task 5 |
| 6 | 🟢 P2 | 零件原点约定文档化 | `_resolve_child_offsets` docstring 声明约定 | Task 4 |
| 7 | 🟢 P2 | 法兰 Φ80→Φ90（范围外） | 记录在 Out of Scope 节 | Header |
| 8 | 🔵 测试 | auto_stack 测试加强顺序校验 | `test_offsets_auto_stack_order` 验证排序 | Task 4 |
| 9 | 🔵 测试 | 集成测试补充断言 | 5 项断言：零偏移、PEEK、电机、translate 顺序、去重 | Task 7 |

## Edge Cases Handled

| Scenario | Behavior |
|----------|----------|
| §6.2 row has Z but no R/θ | Z offset applied as non-radial translate |
| §6.2 row has R/θ but no Z | Radial station transform, children auto-stacked from Z=0 |
| §6.2 row has "基准原点" | Z=0, is_origin=True |
| §6.2 row has no part_no | Name-keyword fallback matches BOM entries |
| §6.2 row offset is "—" | Row indexed for axis_dir only, no position |
| §6.2 is empty or missing | All parts auto-stacked with default -Z direction |
| axis_dir has multi-clause | Each child matches its own sub-clause for stacking direction |
| Part has no dimensions | Fallback 20mm extent used for spacing |
| offset = (0, 0, 0) | No `.translate()` emitted (filtered by empty string check) |
| Orphan assembly (no pose) | Safe default offset Z=+100mm to avoid overlap |
| Multiple subsystems | Algorithm is generic — uses part_no prefix grouping, not hardcoded names |
