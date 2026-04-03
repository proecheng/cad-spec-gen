# skill_mech_design — Parametric Mechanical Subsystem CAD Design Knowledge Base

## Overview

`/mechdesign` is used for **manual** fine-grained parametric modelling. It complements `/cad-codegen` (automatic scaffolding):
- **Recommended workflow**: `/cad-spec` -> `/cad-codegen` (auto scaffold) -> `/mechdesign` (manually refine geometry)
- **Fully manual**: `/mechdesign <subsystem>` starts the full 6-phase modelling process from scratch

---

## 6-Phase Workflow

### Phase 1: Parameter Extraction -> params.py + tolerances.py

**Input**: Design document (`docs/design/NN-*.md` or absolute path such as `D:/jiehuo/docs/NN-*.md`, section X.4 detailed design)
**Output**: `cad/<subsystem>/params.py` (single source of truth)

Rules:
- All dimensions are extracted from the design document -- **never fabricated**
- Use descriptive parameter names: `FLANGE_R`, `ARM_WIDTH`, `MOTOR_OD` (not `L`, `W`, `DIA`)
- Prefix station parameters: `S1_BODY_W`, `S2_SPRING_OD`, `S3_BRUSH_W`, `S4_BRACKET_H`
- Tolerances go in a separate `tolerances.py`: `FLANGE_R_TOL = (0, -0.05)`
- Units: mm throughout; angles in degrees
- Use `math.radians()` for conversion
- Each parameter is assigned exactly once -- no duplicates

Example structure:
```python
# params.py -- end-effector parameters (single source of truth)
import math

# -- Flange --
FLANGE_R = 55.0          # flange outer radius mm (design doc S4.4.1)
FLANGE_THICK = 8.0       # aluminium flange thickness mm
PEEK_THICK = 3.0         # PEEK insulating ring thickness mm

# -- Station layout --
NUM_STATIONS = 4
STATION_ANGLES = [i * 360 / NUM_STATIONS for i in range(NUM_STATIONS)]
MOUNT_CENTER_R = 40.0    # mounting centre radius mm
```

### Phase 2: BOM Modelling -> bom.py

**Input**: Design document section X.8 BOM table (read from the actual design document path)
**Output**: `cad/<subsystem>/bom.py` (parts list + cost summary)

Rules:
- Distinguish in-house parts from purchased parts
- In-house parts require accurate CadQuery modelling
- Purchased parts use simplified geometry (cylinders, boxes) for render visualisation only
- Part number format: `GIS-XX-NNN` (assembly) / `GIS-XX-NNN-NN` (part)

### Phase 3: 3D Parametric Modelling -> CadQuery .py + assembly.py

**Input**: params.py + design document geometry descriptions
**Output**: Individual part `.py` files + `assembly.py` -> STEP + GLB

Key principles:
- **All dimensions reference params.py** -- no magic numbers inside function bodies
- After `from params import *`, use variable names directly
- One `make_<part>()` function per part, returning `cq.Workplane` or `cq.Assembly`
- assembly.py uses `cq.Assembly` to assemble all parts, with `mates` constraints for positioning
- Export both STEP (machining) and GLB (rendering) formats

Common CadQuery patterns:
```python
import cadquery as cq
from params import *

def make_flange():
    return (
        cq.Workplane("XY")
        .circle(FLANGE_R).extrude(FLANGE_THICK)
        .faces(">Z").workplane()
        .circle(BORE_R).cutThruAll()
        # mounting holes
        .faces(">Z").workplane()
        .polarArray(MOUNT_CENTER_R, 0, 360, NUM_STATIONS)
        .circle(MOUNT_HOLE_R).cutThruAll()
    )
```

### Phase 4: 2D Engineering Drawings -> GB/T National Standard A3 DXF

**Input**: params.py parameters (draw profiles directly -- no 3D projection)
**Output**: `cad/output/EE-NNN-NN_name.dxf`

GB/T national standard requirements:
- **Projection method**: GB/T 4458.1 first-angle projection
- **Sheet size**: A3 (420x297 mm)
- **Font**: FangSong (GB/T 14691)
- **Line width**: d=0.50 mm system (GB/T 17450)
- **Annotation text**: 3.5 mm paper height (do not multiply by view scale)
- **DXF format**: R2013

12-layer DXF system:
| Layer | Colour | Purpose |
|-------|--------|---------|
| 0-outline | white | Visible outlines (thick solid line d) |
| 1-hidden | cyan | Hidden outlines (dashed line d/2) |
| 2-center | red | Centre lines (chain line d/3) |
| 3-dimension | green | Dimension annotations |
| 4-section | yellow | Section hatching (45-degree thin solid line) |
| 5-notes | magenta | Technical requirements text |
| 6-title | white | Title block |
| 7-border | white | Drawing border |
| 8-section-line | red | Section cut line A-A |
| 9-datum | green | Datum triangle |
| 10-thread | cyan | Thread annotation (thin solid line, 3/4 arc) |
| 11-surface | magenta | Surface roughness |

Every drawing must include:
- Technical requirements zone (upper-right corner or above title block)
- Default roughness symbol Ra
- Datum triangle (at least one A datum)
- Section cut line (if internal features exist)
- Thread annotation (if threaded holes exist)
- Material names in Chinese national standard format ("aluminium alloy", not "Al")

#### Drawing function origin convention (mandatory)

Every drawing function in `draw_*.py` has the signature `func(msp, ox, oy, scale)` where **(ox, oy) is the view centre**.
Layout calculators `calc_multi_view_layout` / `calc_three_view_layout` return the **centre** of each view's bbox.

**Centre-centre convention is mandatory**:

```python
def my_front_view(msp, ox, oy, scale):
    """ox, oy = view centre."""
    s = scale
    hw = PART_W / 2 * s   # half-width
    hh = PART_H / 2 * s   # half-height
    # outline expands symmetrically from (ox, oy)
    msp.add_lwpolyline([
        (ox - hw, oy - hh), (ox + hw, oy - hh),
        (ox + hw, oy + hh), (ox - hw, oy + hh), (ox - hw, oy - hh)
    ], dxfattribs={"layer": "OUTLINE"})
```

Forbidden patterns (cause views to exceed sheet border):
- Do not use `oy` to `oy + ht` (bottom-Y)
- Do not use `ox` to `ox + w*s` (left-X)
- Do not pass half-dimensions as bbox

**bbox must use full dimensions** (width x height), not half:

```python
sheet.draw_front(my_front_view, bbox=(PART_W, PART_H))      # correct: full size
sheet.draw_front(my_front_view, bbox=(PART_W/2, PART_H/2))  # wrong: half size
```

### Phase 5: Render Preview -> DXF to PNG

**Tool**: `cad/<subsystem>/render_dxf.py`
**Output**: .png file with same name as the DXF

```bash
python cad/<subsystem>/render_dxf.py                    # render all
python cad/<subsystem>/render_dxf.py file1.dxf file2.dxf  # render specific files
```

### Phase 6: One-Click Build -> build_all.py

**Tool**: `cad/<subsystem>/build_all.py`
**Output**: All STEP + DXF + GLB files under `cad/output/`

```bash
python cad/<subsystem>/build_all.py               # build STEP + DXF
python cad/<subsystem>/build_all.py --render       # build + Blender render
python cad/<subsystem>/build_all.py --dry-run      # import validation only
# Note: when invoked via cad_pipeline.py build, render_dxf.py is auto-run to convert DXF to PNG previews
```

build_all.py structure:
- `_STEP_BUILDS` list: (label, module, function, filename)
- `_DXF_BUILDS` list: (label, module, function)
- `build_all()` function builds all parts sequentially

---

## Checkpoint Validation

Validate after each phase:

| Phase | Validation Method |
|-------|-------------------|
| params.py | All parameters traceable to design document, no magic numbers |
| bom.py | Total count matches design document section X.8 BOM |
| Part .py | `make_*()` returns valid solid, no TODO placeholders |
| assembly.py | GLB opens correctly in Blender |
| DXF | Line widths / fonts / layer names conform to GB/T, title block complete |
| build_all.py | `--dry-run` passes, all modules importable |

---

## Three Quality Gates

The pipeline enforces mandatory checks at three key points; any failure aborts subsequent phases:

| Gate | Trigger Point | Check Content | Failure Handling |
|------|---------------|---------------|------------------|
| **Gate 1** DESIGN_REVIEW CRITICAL | End of SPEC phase | `cad_spec_reviewer.py` finds CRITICAL-level issues | Prints issue list; requires user confirmation before proceeding |
| **Gate 2** TODO Scan | End of CODEGEN phase | `gen_parts.py` scans all newly generated files for `TODO:` markers | Exit code 2; prints filename + line number + content; blocks entry to BUILD |
| **Gate 3** Orientation Check | Before BUILD phase | `orientation_check.py` asserts bounding-box principal axes match design document | Non-zero exit code; prints axis deviation; blocks build; can bypass with `--skip-orientation` (not recommended) |

### Gate 2 Detailed Rules

`gen_parts.py` scans all new files for `TODO:` markers immediately after scaffold generation:
- **Unfilled TODOs present** -> prints WARNING list and exits with **exit code 2**
- **All TODOs filled** -> exits normally (exit code 0) and proceeds to BUILD

### Gate 3 Detailed Rules

`orientation_check.py` is created by the user or codegen under the subsystem directory. It asserts that the built model's bounding-box principal axis orientation is correct:
```python
# Example: orientation_check.py
assert abs(bb.xmax - bb.xmin - EXPECTED_X) < TOL, f"X axis deviation: {bb.xmax-bb.xmin:.1f} vs {EXPECTED_X}"
```
- File does not exist -> gate is skipped (not mandatory)
- File exists and fails -> BUILD is aborted
- `--skip-orientation` flag can bypass (debug use only)

---

## Reference Implementation

`cad/end_effector/` is the complete reference implementation:

```
cad/end_effector/
+-- params.py              # ~220 parameters
+-- tolerances.py          # tolerance definitions
+-- bom.py                 # BOM list
+-- flange.py              # flange 3D
+-- station1_applicator.py # applicator station
+-- station2_ae.py         # acoustic emission station
+-- station3_cleaner.py    # cleaner station
+-- station4_uhf.py        # UHF station
+-- drive_assembly.py      # drive assembly
+-- assembly.py            # final assembly -> STEP + GLB
+-- drawing.py             # 2D drawing engine
+-- draw_three_view.py     # three-view template
+-- draw_flange.py         # flange engineering drawing
+-- draw_station1.py       # station engineering drawings
+-- ...
+-- render_config.json     # render configuration
+-- render_3d.py           # Blender render
+-- render_exploded.py     # exploded view
+-- render_dxf.py          # DXF to PNG
+-- build_all.py           # one-click build
```

---

## Collaboration with Auto Pipeline

| Scenario | Recommended Approach |
|----------|----------------------|
| First-time modelling | `/cad-spec` -> `/cad-codegen` -> `/mechdesign` to refine |
| Existing scaffold | `/mechdesign <subsystem>` to refine geometry on top of scaffold |
| Parameter tuning only | Edit `params.py`, re-run `build_all.py` |
| Adding new parts | Write `make_*()` function manually, add to `build_all.py` |
| Render only | `python cad_pipeline.py render --subsystem <name>` |
| Fully automatic | `python cad_pipeline.py full --subsystem <name> --design-doc <doc>` |

---

## Key Constraints

1. **params.py is the single source of truth** -- all dimensions are referenced from this file
2. **Do not modify user design documents** -- changes go only in CAD_SPEC.md and code
3. **2D direct drawing** -- draw profiles from params.py; no 3D-to-2D projection
4. **GB/T national standard** -- first-angle projection, FangSong font, 12-layer DXF, d=0.50 mm line width
5. **Unified output** -- all artefacts go to `cad/output/`
6. **Critical dimensions must not be changed arbitrarily** -- parameters explicitly specified in the design document must be strictly followed; verify against the original section before modifying
