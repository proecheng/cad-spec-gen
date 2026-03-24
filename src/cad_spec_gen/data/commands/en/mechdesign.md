# /mechdesign — Parametric Mechanical Subsystem CAD Design

User input: $ARGUMENTS

## Instructions

Read the full skill document `skill_mech_design.md` (project root), then execute based on user input:

> **Manual vs Auto**: `/mechdesign` is for **manual** fine-grained modeling (engineer refines geometry step by step).
> For **auto** scaffold generation, use `/cad-codegen` or `python cad_pipeline.py full`.
> Recommended workflow: `/cad-spec` → `/cad-codegen` → `/mechdesign` (auto-generate skeleton first, then manually refine)

### Subcommand Routing

1. **No arguments** (`$ARGUMENTS` is empty) → Show workflow overview:
   - List 6 stages briefly
   - List available subsystems (scan chapter files from `docs/design/`)
   - Show reference implementation `cad/end_effector/` artifact stats

2. **`status`** → Check CAD modeling progress for each subsystem:
   - Scan `cad/*/build_all.py` to find implemented subsystems
   - Scan `cad/output/` to count STEP/DXF/PNG quantities
   - List all `docs/design/` chapters, mark which are modeled and which are pending
   - Recommend next priority

3. **`upgrade`** → Start 2D engineering drawing standards upgrade (V4 plan):
   - Execute Phase 1→1.5→2→3→4
   - Phase 1: drawing.py + draw_three_view.py infrastructure overhaul
   - Phase 1.5: Visual verification test drawings
   - Phase 2: Pick most complex part as template
   - Phase 3: Batch update remaining parts
   - Phase 4: Full validation

4. **`<subsystem name>`** (e.g., `charging_dock`, `chassis`, `battery_box`) → Start full workflow:
   - Confirm target subsystem and corresponding design document (`docs/design/NN-*.md`)
   - Check if `/cad-codegen` scaffold code already exists; if so, build upon it
   - Execute the 6 stages in order per skill_mech_design.md:
     1. Parameter extraction → `params.py` + `tolerances.py`
     2. BOM modeling → `bom.py`
     3. 3D parametric modeling → CadQuery `.py` + `assembly.py`
     4. 2D engineering drawings → GB/T standard A3 DXF (with technical requirements/datum/thread/section views)
     5. Render preview → DXF→PNG (reuse `render_dxf.py`)
     6. One-click build → `build_all.py`
   - Run checkpoint validation after each stage
   - Reusable modules from `cad/end_effector/`: `drawing.py`, `draw_three_view.py`, `render_dxf.py`

## Key Constraints

- All parameters extracted from design documents; params.py is the single source of truth
- 2D engineering drawings are drawn directly from params.py contours, not from 3D→2D projection
- Output to `cad/output/`, tracked in git version control
- Font: FangSong (GB/T 14691), DXF format R2013
- GB/T 4458.1 first-angle projection, A3 sheet (420×297mm)
- Line width system d=0.50mm, replace built-in CENTER/DASHED linetypes with GB/T 17450 patterns
- Dimension text 3.5mm on paper (do not multiply by view scale)
- Each drawing must include: technical requirements zone + default roughness + datum triangle + section lines + thread annotations
- Material names in Chinese standard format ("铝合金" not "Al")

## Automated Pipeline Alternative

If manual fine-grained modeling is not needed, use the automated pipeline for one-shot completion:
```bash
# Full auto pipeline: review → codegen → build → render → enhance → annotate
python cad_pipeline.py full --subsystem <name> --design-doc docs/design/NN-*.md --timestamp
```
Or step by step: `/cad-spec` → `/cad-codegen` → `python cad_pipeline.py build --render`
