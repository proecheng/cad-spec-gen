# Assembly Validator (GATE-3.5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a post-build assembly validator that detects floating parts, size mismatches, and scattered stations using engineering formulas derived from the spec data — no hardcoded thresholds.

**Architecture:** New `assembly_validator.py` loads `make_assembly()` from the subsystem, extracts per-part world-space bounding boxes via CadQuery, runs 5 checks (F1-F5) with thresholds derived from §6.4 envelopes and §2 tolerances, writes `ASSEMBLY_REPORT.json`. Integrated into `cad_pipeline.py:cmd_build` as a non-blocking post-build step.

**Tech Stack:** Python 3.10+, CadQuery (bounding box API), existing `parse_envelopes()` and `parse_bom_tree()`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `assembly_validator.py` | Create | Load assembly, extract per-part BBox, run F1-F5 checks, write report |
| `cad_pipeline.py` | Modify (cmd_build, ~line 1050) | Call validator after successful build |
| `tests/test_assembly_validator.py` | Create | Unit tests for AABB distance, threshold derivation, check logic |

---

### Task 1: assembly_validator.py — core validation engine

**Files:**
- Create: `assembly_validator.py`
- Create: `tests/test_assembly_validator.py`

- [ ] **Step 1: Write failing tests for AABB distance and threshold derivation**

```python
# tests/test_assembly_validator.py
"""Tests for assembly_validator.py."""
import os
import sys
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_aabb_distance_overlapping():
    """Overlapping AABBs should have distance 0."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)  # (xmin, ymin, zmin, xmax, ymax, zmax)
    b = (5, 5, 5, 15, 15, 15)
    assert aabb_distance(a, b) == 0.0


def test_aabb_distance_separated():
    """Separated AABBs: d = sqrt(dx^2 + dy^2 + dz^2)."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)
    b = (20, 0, 0, 30, 10, 10)  # 10mm gap on X axis
    assert aabb_distance(a, b) == 10.0


def test_aabb_distance_diagonal():
    """Diagonal separation: d = sqrt(10^2 + 10^2 + 10^2)."""
    from assembly_validator import aabb_distance
    a = (0, 0, 0, 10, 10, 10)
    b = (20, 20, 20, 30, 30, 30)
    expected = math.sqrt(10**2 + 10**2 + 10**2)
    assert abs(aabb_distance(a, b) - expected) < 0.01


def test_derive_disconnect_threshold_from_tolerances():
    """Threshold = 3 * RSS(tolerances) + 0.3mm ISO 2768-m margin."""
    from assembly_validator import derive_disconnect_threshold
    # 4 tolerances of 0.1mm each: RSS = sqrt(4 * 0.01) = 0.2mm
    # threshold = 3 * 0.2 + 0.3 = 0.9mm
    tolerances = [0.1, 0.1, 0.1, 0.1]
    threshold = derive_disconnect_threshold(tolerances, min_part_size=50.0)
    expected = 3.0 * math.sqrt(sum(t**2 for t in tolerances)) + 0.3
    assert abs(threshold - expected) < 0.01


def test_derive_disconnect_threshold_no_tolerances():
    """Without tolerance data: fallback to 5% of smallest part size."""
    from assembly_validator import derive_disconnect_threshold
    threshold = derive_disconnect_threshold([], min_part_size=40.0)
    assert abs(threshold - 2.0) < 0.01  # 0.05 * 40 = 2.0


def test_derive_compactness_threshold():
    """Compactness = sum(heights) * packing_factor."""
    from assembly_validator import derive_compactness_threshold
    heights = [25.0, 5.0, 68.0, 8.0]  # sum = 106
    threshold = derive_compactness_threshold(heights)
    assert abs(threshold - 106.0 * 2.0) < 0.01  # packing_factor = 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_assembly_validator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'assembly_validator'`

- [ ] **Step 3: Implement assembly_validator.py**

```python
#!/usr/bin/env python3
"""
Assembly Validator (GATE-3.5) — Post-build geometry sanity checks.

Loads the assembly from make_assembly(), extracts per-part world-space
bounding boxes, runs 5 checks (F1-F5) with thresholds derived from
the spec data. Writes ASSEMBLY_REPORT.json.

Usage:
    python assembly_validator.py cad/end_effector/ [--spec CAD_SPEC.md]

Formulas:
    AABB distance:  d = sqrt(sum(max(0, max(aMin[k]-bMax[k], bMin[k]-aMax[k]))^2))
    Disconnect:     gap > 3 * RSS(tolerances) + 0.3mm  (ISO 2768-m margin)
    Fallback:       gap > 0.05 * min_part_characteristic_size
    Compactness:    z_span <= sum(part_heights) * packing_factor (2.0)
    Size check:     0.5 <= actual/expected <= 2.0  (scaffold precision)
"""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Pure geometry functions (no CadQuery dependency — testable standalone)
# ═══════════════════════════════════════════════════════════════════════════

def aabb_distance(a: tuple, b: tuple) -> float:
    """Minimum 3D distance between two AABBs.

    Each AABB is (xmin, ymin, zmin, xmax, ymax, zmax).
    Returns 0.0 if boxes overlap.

    Formula: d = sqrt(sum(max(0, max(aMin[k]-bMax[k], bMin[k]-aMax[k]))^2))
    Reference: standard AABB separation test, exact for axis-aligned boxes.
    """
    d_sq = 0.0
    for k in range(3):
        gap = max(0.0, max(a[k] - b[k + 3], b[k] - a[k + 3]))
        d_sq += gap * gap
    return math.sqrt(d_sq)


def derive_disconnect_threshold(tolerances: list, min_part_size: float) -> float:
    """Compute disconnect gap threshold from spec tolerance data.

    With tolerances: 3-sigma RSS stack + ISO 2768-m general tolerance margin.
        threshold = 3 * sqrt(sum(ti^2)) + 0.3mm

    Without tolerances: 5% of smallest part characteristic size.
        threshold = 0.05 * min_part_size

    Returns threshold in mm.
    """
    if tolerances:
        rss = math.sqrt(sum(t ** 2 for t in tolerances))
        return 3.0 * rss + 0.3
    return 0.05 * min_part_size


def derive_compactness_threshold(part_heights: list,
                                  packing_factor: float = 2.0) -> float:
    """Compute max plausible Z-span for a set of stacked parts.

    threshold = sum(part_heights) * packing_factor

    packing_factor accounts for gaps, offsets, and non-axial parts.
    Typical mechanical assemblies: 1.2 (tight) to 2.0 (loose scaffold).
    """
    return sum(part_heights) * packing_factor


# ═══════════════════════════════════════════════════════════════════════════
# Assembly introspection (requires CadQuery)
# ═══════════════════════════════════════════════════════════════════════════

def extract_part_bboxes(assy) -> dict:
    """Extract world-space AABB for each named part in a CadQuery Assembly.

    Returns {name: (xmin, ymin, zmin, xmax, ymax, zmax)}.
    Uses shape.moved(loc) to get world-space coordinates.
    """
    bboxes = {}
    for name, sub in assy.objects.items():
        if sub.obj is None:
            continue
        shape = sub.obj.val() if hasattr(sub.obj, "val") else sub.obj
        moved = shape.moved(sub.loc)
        bb = moved.BoundingBox()
        bboxes[name] = (bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax)
    return bboxes


# ═══════════════════════════════════════════════════════════════════════════
# Check functions
# ═══════════════════════════════════════════════════════════════════════════

def check_f1_floating(bboxes: dict, threshold: float) -> list:
    """F1: Detect floating parts via contact graph.

    Build undirected graph: edge exists if AABB distance <= threshold.
    Parts with degree 0 are FLOATING.
    """
    names = list(bboxes.keys())
    adjacency = {n: set() for n in names}

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            d = aabb_distance(bboxes[names[i]], bboxes[names[j]])
            if d <= threshold:
                adjacency[names[i]].add(names[j])
                adjacency[names[j]].add(names[i])

    issues = []
    for name in names:
        if not adjacency[name]:
            # Find nearest neighbor for reporting
            min_d = float("inf")
            nearest = ""
            for other in names:
                if other == name:
                    continue
                d = aabb_distance(bboxes[name], bboxes[other])
                if d < min_d:
                    min_d = d
                    nearest = other
            issues.append({
                "part": name,
                "gap_mm": round(min_d, 1),
                "nearest": nearest,
            })
    return issues


def check_f2_size_mismatch(bboxes: dict, envelopes: dict) -> list:
    """F2: Check part BBox dimensions vs §6.4 expected envelopes.

    Flag if any axis ratio < 0.5 or > 2.0 (scaffold precision band).
    """
    issues = []
    for name, bbox in bboxes.items():
        # Extract part_no from assembly name (e.g. "EE-001-01" or "STD-GIS-EE-001-03")
        pno_match = re.search(r"(GIS-[A-Z]+-\d+-\d+)", name)
        if not pno_match:
            # Try format "EE-001-01" → "GIS-EE-001-01"
            m2 = re.match(r"([A-Z]+-\d+-\d+)", name)
            if m2:
                pno = "GIS-" + m2.group(1)
            else:
                continue
        else:
            pno = pno_match.group(1)

        if pno not in envelopes:
            continue

        expected = envelopes[pno]
        actual = (bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2])

        # Sort both to compare largest-to-largest (orientation-independent)
        a_sorted = sorted(actual, reverse=True)
        e_sorted = sorted(expected, reverse=True)

        for k in range(3):
            if e_sorted[k] < 0.1:
                continue  # skip near-zero
            ratio = a_sorted[k] / e_sorted[k]
            if ratio < 0.5 or ratio > 2.0:
                issues.append({
                    "part": name,
                    "part_no": pno,
                    "axis": k,
                    "actual": round(a_sorted[k], 1),
                    "expected": round(e_sorted[k], 1),
                    "ratio": round(ratio, 2),
                })
                break  # one issue per part is enough

    return issues


def check_f3_compactness(bboxes: dict, envelopes: dict,
                          station_prefixes: list) -> list:
    """F3: Check Z-span compactness per station.

    Threshold = sum(envelope heights for station parts) * 2.0.
    """
    issues = []
    for prefix in station_prefixes:
        station_bboxes = {n: b for n, b in bboxes.items()
                          if prefix.replace("GIS-", "") in n}
        if not station_bboxes:
            continue

        z_vals = []
        for b in station_bboxes.values():
            z_vals.extend([b[2], b[5]])  # zmin, zmax
        if not z_vals:
            continue
        z_span = max(z_vals) - min(z_vals)

        # Derive threshold from §6.4 envelope heights
        heights = []
        for pno, env in envelopes.items():
            if pno.startswith(prefix):
                heights.append(env[2])
        if not heights:
            heights = [20.0]  # fallback

        threshold = derive_compactness_threshold(heights)
        if z_span > threshold:
            issues.append({
                "station": prefix,
                "z_span": round(z_span, 1),
                "threshold": round(threshold, 1),
                "sum_heights": round(sum(heights), 1),
            })

    return issues


def check_f4_centroid(bboxes: dict) -> dict:
    """F4: Check if assembly centroid is near origin."""
    if not bboxes:
        return {"center_offset": 0.0, "ok": True}

    centers = []
    for bbox in bboxes.values():
        cx = (bbox[0] + bbox[3]) / 2
        cy = (bbox[1] + bbox[4]) / 2
        cz = (bbox[2] + bbox[5]) / 2
        centers.append((cx, cy, cz))

    centroid = tuple(sum(c[k] for c in centers) / len(centers) for k in range(3))
    offset = math.sqrt(sum(c ** 2 for c in centroid))

    # Threshold: 30% of assembly max extent
    all_coords = [v for bbox in bboxes.values() for v in bbox]
    max_extent = max(all_coords) - min(all_coords) if all_coords else 1.0
    ok = offset <= 0.3 * max_extent

    return {
        "centroid": [round(c, 1) for c in centroid],
        "center_offset": round(offset, 1),
        "max_extent": round(max_extent, 1),
        "ok": ok,
    }


def check_f5_completeness(bboxes: dict, bom_parts: list) -> dict:
    """F5: Check that assembly contains expected BOM parts.

    Counts non-assembly, non-fastener, non-cable parts in BOM.
    """
    from bom_parser import classify_part
    skip_cats = {"fastener", "cable"}
    expected_parts = []
    for p in bom_parts:
        if p.get("is_assembly"):
            continue
        cat = classify_part(p.get("name_cn", ""), p.get("material", ""))
        if cat in skip_cats:
            continue
        expected_parts.append(p["part_no"])

    expected_count = len(expected_parts)
    actual_count = len(bboxes)
    completeness = actual_count / expected_count if expected_count > 0 else 1.0

    return {
        "expected": expected_count,
        "actual": actual_count,
        "completeness_pct": round(completeness * 100, 1),
        "ok": completeness >= 0.7,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def validate_assembly(sub_dir: str, spec_path: str = None,
                       output_dir: str = None) -> dict:
    """Run all 5 checks on the assembly in sub_dir.

    Returns the full report dict and writes ASSEMBLY_REPORT.json.
    """
    # Add sub_dir to path so we can import assembly module
    if sub_dir not in sys.path:
        sys.path.insert(0, sub_dir)

    # Import assembly
    try:
        from assembly import make_assembly
    except ImportError as e:
        return {"error": f"Cannot import assembly: {e}"}

    # Build assembly and extract bounding boxes
    assy = make_assembly()
    bboxes = extract_part_bboxes(assy)

    if not bboxes:
        return {"error": "No parts found in assembly"}

    # Load spec data
    if spec_path is None:
        spec_path = os.path.join(sub_dir, "CAD_SPEC.md")

    envelopes = {}
    bom_parts = []
    tolerances = []
    if os.path.isfile(spec_path):
        from codegen.gen_assembly import parse_envelopes
        from codegen.gen_build import parse_bom_tree
        envelopes = parse_envelopes(spec_path)
        bom_parts = parse_bom_tree(spec_path)

        # Extract tolerance values from §2 for RSS calculation
        text = Path(spec_path).read_text(encoding="utf-8")
        for m in re.finditer(r"[±]\s*(\d+(?:\.\d+)?)\s*mm", text):
            tolerances.append(float(m.group(1)))

    # Derive thresholds
    min_part_size = min(
        (max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) for b in bboxes.values()),
        default=20.0
    )
    disconnect_threshold = derive_disconnect_threshold(tolerances, min_part_size)

    # Detect station prefixes from BOM
    station_prefixes = []
    for p in bom_parts:
        if p.get("is_assembly"):
            pno = p["part_no"]
            if re.match(r"[A-Z]+-[A-Z]+-\d+$", pno):
                station_prefixes.append(pno)

    # Run checks
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "subsystem": os.path.basename(sub_dir),
        "total_parts": len(bboxes),
        "thresholds": {
            "disconnect_mm": round(disconnect_threshold, 2),
            "disconnect_method": "3σ RSS + ISO 2768-m" if tolerances else "5% min_part_size",
            "tolerance_count": len(tolerances),
        },
        "checks": {
            "F1_floating": check_f1_floating(bboxes, disconnect_threshold),
            "F2_size_mismatch": check_f2_size_mismatch(bboxes, envelopes),
            "F3_compactness": check_f3_compactness(bboxes, envelopes, station_prefixes),
            "F4_centroid": check_f4_centroid(bboxes),
            "F5_completeness": check_f5_completeness(bboxes, bom_parts),
        },
    }

    # Summary
    warning_count = (
        len(report["checks"]["F1_floating"]) +
        len(report["checks"]["F2_size_mismatch"]) +
        len(report["checks"]["F3_compactness"]) +
        (0 if report["checks"]["F4_centroid"]["ok"] else 1) +
        (0 if report["checks"]["F5_completeness"]["ok"] else 1)
    )
    report["summary"] = f"{warning_count} WARNING"

    # Write report
    out_dir = output_dir or os.path.join(sub_dir, "..", "output")
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "ASSEMBLY_REPORT.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report


def main():
    parser = argparse.ArgumentParser(description="Assembly Validator (GATE-3.5)")
    parser.add_argument("sub_dir", help="Subsystem directory (e.g. cad/end_effector/)")
    parser.add_argument("--spec", help="Path to CAD_SPEC.md")
    parser.add_argument("--output-dir", help="Output directory for report")
    args = parser.parse_args()

    report = validate_assembly(args.sub_dir, args.spec, args.output_dir)

    if "error" in report:
        print(f"[ERROR] {report['error']}")
        sys.exit(1)

    # Print summary
    print(f"[GATE-3.5] Assembly Validation: {report['summary']}")
    print(f"  Parts: {report['total_parts']}")
    print(f"  Disconnect threshold: {report['thresholds']['disconnect_mm']:.1f}mm "
          f"({report['thresholds']['disconnect_method']})")

    for issue in report["checks"]["F1_floating"]:
        print(f"  [F1 FLOATING] {issue['part']} — gap {issue['gap_mm']}mm to {issue['nearest']}")
    for issue in report["checks"]["F2_size_mismatch"]:
        print(f"  [F2 SIZE] {issue['part']} — actual {issue['actual']}mm vs expected {issue['expected']}mm (ratio {issue['ratio']})")
    for issue in report["checks"]["F3_compactness"]:
        print(f"  [F3 COMPACT] {issue['station']} — Z-span {issue['z_span']}mm > threshold {issue['threshold']}mm")
    if not report["checks"]["F4_centroid"]["ok"]:
        f4 = report["checks"]["F4_centroid"]
        print(f"  [F4 CENTROID] offset {f4['center_offset']}mm (max_extent {f4['max_extent']}mm)")
    if not report["checks"]["F5_completeness"]["ok"]:
        f5 = report["checks"]["F5_completeness"]
        print(f"  [F5 BOM] {f5['actual']}/{f5['expected']} parts ({f5['completeness_pct']}%)")

    print(f"  Report: ASSEMBLY_REPORT.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/Work/cad-spec-gen && python -m pytest tests/test_assembly_validator.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add assembly_validator.py tests/test_assembly_validator.py
git commit -m "feat: add assembly_validator.py (GATE-3.5) with formula-derived thresholds"
```

---

### Task 2: Pipeline integration — call validator after build

**Files:**
- Modify: `cad_pipeline.py:1050-1066` (cmd_build, after DXF rendering)

- [ ] **Step 1: Add validator call to cmd_build**

In `cad_pipeline.py`, after the DXF→PNG rendering block (around line 1063), add:

```python
    # ── Post-build: Assembly validation (GATE-3.5) ──────────────────────────
    validator_script = os.path.join(SKILL_ROOT, "assembly_validator.py")
    spec_in_sub = os.path.join(sub_dir, "CAD_SPEC.md")
    if os.path.isfile(validator_script) and os.path.isfile(spec_in_sub):
        log.info("[Phase 3 GATE-3.5] Running assembly validation ...")
        ok_val, _ = _run_subprocess(
            [sys.executable, validator_script, sub_dir,
             "--spec", spec_in_sub,
             "--output-dir", DEFAULT_OUTPUT],
            "assembly_validator.py", dry_run=args.dry_run, timeout=120
        )
        if not ok_val:
            log.warning("Assembly validation failed (non-fatal)")
    # ─────────────────────────────────────────────────────────────────────────
```

- [ ] **Step 2: Test the integration**

```bash
cd D:/Work/cad-spec-gen
CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT python cad_pipeline.py build --subsystem end_effector --skip-orientation
```

Expected output should include `[GATE-3.5] Assembly Validation: N WARNING` line.

- [ ] **Step 3: Verify ASSEMBLY_REPORT.json is written**

```bash
cat D:/Work/cad-tests/GISBOT/cad/output/ASSEMBLY_REPORT.json | python -m json.tool | head -20
```

- [ ] **Step 4: Commit**

```bash
git add cad_pipeline.py
git commit -m "feat: integrate assembly_validator into build pipeline (GATE-3.5)"
```
