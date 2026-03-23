# End Effector — Parametric CAD Module

Reference implementation for the CAD pipeline. 4-station rotary end effector for GIS partial discharge detection.

## Files

| File | Purpose |
|------|---------|
| `params.py` | Single source of truth for all dimensions |
| `flange.py` | Main flange body + PEEK insulation ring |
| `station1_applicator.py` | Couplant applicator module |
| `station2_ae.py` | Acoustic emission sensor module |
| `station3_cleaner.py` | Tape cleaning module |
| `station4_uhf.py` | UHF antenna module |
| `drive_assembly.py` | Motor + gearbox + adapter plate |
| `assembly.py` | Full assembly → STEP + GLB |
| `build_all.py` | One-click build (STEP + DXF + optional render) |
| `render_config.json` | Materials, cameras, explode rules, labels |
| `render_config.py` | Config engine (15 material presets) |
| `render_3d.py` | Blender Cycles renderer (V1-V3, V5) |
| `render_exploded.py` | Blender exploded view renderer (V4) |
| `draw_*.py` | GB/T three-view DXF engineering drawings |
| `drawing.py` | 2D drawing engine |

## Quick Start

```bash
# Build all STEP + DXF
python build_all.py

# Build + Blender render
python build_all.py --render

# Dry-run (validate imports)
python build_all.py --dry-run
```

## Output

- 8 STEP files → `cad/output/EE-*.step`
- 11 DXF drawings → `cad/output/EE-*.dxf`
- 1 GLB assembly → `cad/output/EE-000_assembly.glb`
- 5 PNG renders → `cad/output/renders/V*.png`
