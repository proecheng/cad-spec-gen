# Model Quality Round 2 — end_effector P2 templates

## Scope

- Branch: `codex/model-quality-round2`
- Subsystem: `cad/end_effector`
- Goal: upgrade the P2 fluid / cleaning backlog from generic `jinja_primitive` placeholders to reusable semi-parametric templates, and correct the FFC visual envelope so validation no longer compares a ribbon against a cylinder.

## Commands run

```powershell
.venv\Scripts\python.exe -m pytest tests\test_jinja_generators_new.py -q
.venv\Scripts\python.exe codegen\gen_std_parts.py cad\end_effector\CAD_SPEC.md --output-dir cad\end_effector --mode force
.venv\Scripts\python.exe cad_pipeline.py build --subsystem end_effector
.venv\Scripts\python.exe cad_pipeline.py render --subsystem end_effector --view V1 --timestamp --output-dir <temp-render-dir>
.venv\Scripts\python.exe scripts\dev_sync.py
.venv\Scripts\python.exe -m pytest tests\test_jinja_generators_new.py tests\test_parts_adapters.py tests\test_parts_resolver.py tests\test_parts_library_integration.py tests\test_assembly_coherence.py -q
```

Notes:

- The new tests were first run red: all six P2 template cases fell through to legacy fallback geometry, and `GIS-EE-001-09` still parsed as `(10, 10, 50)`.
- `gen_std_parts.py --mode force` also attempted local STEP routing for unrelated parts. Those absolute-cache rewrites were intentionally not kept in this branch.
- `cad_pipeline.py build --subsystem end_effector` completed successfully, including DXF preview generation and GATE-3.5 assembly validation.
- `cad_pipeline.py render --subsystem end_effector --view V1` completed successfully and wrote a one-file manifest under the system temp directory.

## Geometry quality summary

Source: `cad/end_effector/.cad-spec-gen/geometry_report.json`

| Metric | Round 1 after P1 | Round 2 after P2 |
|---|---:|---:|
| Total resolver decisions | 32 | 32 |
| A quality real STEP | 9 | 9 |
| C quality semi-parametric template | 7 | 13 |
| D quality fallback primitive | 16 | 10 |
| E missing geometry | 0 | 0 |

## Upgraded P2 parts

| Part no | Name | Template | Improvement |
|---|---|---|---|
| GIS-EE-002-02 | 储罐 | `fluid_reservoir` | Cylinder now includes caps, clamp bands, and fill boss. |
| GIS-EE-002-03 | 齿轮泵 | `gear_pump` | Box placeholder now shows pump housing, twin gear cover, and ports. |
| GIS-EE-002-04 | 刮涂头 | `scraper_head` | Generic cylinder replaced with clamp bar, rubber blade, and mounting holes. |
| GIS-EE-004-02 | 清洁带盒 | `cleaning_tape_cassette` | Generic cylinder replaced with cassette body, two reels, and tape path. |
| GIS-EE-004-08 | 溶剂储罐 | `solvent_cartridge` | Cylinder now shows piston cartridge caps and M8-style quick connector. |
| GIS-EE-004-09 | 微量泵 | `micro_dosing_pump` | Box placeholder now shows solenoid body, coil, and dosing nozzles. |

## FFC envelope correction

`CAD_SPEC.md §6.4` now records:

| Part no | Old envelope | New envelope |
|---|---|---|
| GIS-EE-001-09 | `cylinder Φ10×50` | `box 12.0×50.0×1.0` |

This matches the `ffc_ribbon` visual stub: the actual cable remains 500 mm in metadata, while the rendered model intentionally limits the visible segment to 50 mm.

## Assembly validation findings

After build, `cad/output/ASSEMBLY_REPORT.json` still reports 9 warnings overall, but the prior `GIS-EE-001-09` FFC size mismatch is gone.

Current `F2_size_mismatch` entries:

| Part no | Reason |
|---|---|
| GIS-EE-001-07 | Spring-pin assembly still modeled wider than the old envelope. |
| GIS-EE-003-03 | Self-made spring force limiter geometry differs from envelope. |
| GIS-EE-003-04 | Self-made flexible joint geometry differs from envelope. |

## Remaining model-quality backlog

Priority for the next slice:

1. `GIS-EE-004-03` micro DC motor: vendor STEP or small motor template.
2. `GIS-EE-004-04` gear reducer group: visible gear train / shafts.
3. `GIS-EE-004-06` constant-force spring: spiral strip template instead of disc spring.
4. `GIS-EE-004-07` photoelectric encoder: sensor body with optical face.
5. `GIS-EE-001-07` spring-pin assembly: pin + spring sub-template, also fixes one validation mismatch.
