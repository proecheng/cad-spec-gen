# Model Quality Round 1 — end_effector baseline

## Scope

- Branch: `codex/model-quality-round1`
- Subsystem: `cad/end_effector`
- Goal: establish a concrete low-quality geometry backlog before replacing simplified Python-generated models with real STEP / SolidWorks Toolbox / bd_warehouse / semi-parametric templates.

## Commands run

```powershell
.venv\Scripts\python.exe cad_pipeline.py codegen --subsystem end_effector
.venv\Scripts\python.exe cad_pipeline.py build --subsystem end_effector
.venv\Scripts\python.exe cad_pipeline.py render --subsystem end_effector --view V1 --timestamp --output-dir <absolute-artifact-dir>
```

Notes:

- `codegen` succeeded and wrote `cad/end_effector/.cad-spec-gen/geometry_report.json`.
- `build` succeeded, including DXF to PNG preview generation and GATE-3.5 assembly validation.
- A first render attempt with a relative `--output-dir` returned zero detected PNGs. Re-running `render` with an absolute output directory and `--view V1` succeeded. This looks like a pipeline output path/detection issue, not a model or Blender failure.

## Geometry quality summary

Source: `cad/end_effector/.cad-spec-gen/geometry_report.json`

| Metric | Value |
|---|---:|
| Total resolver decisions | 32 |
| A quality real STEP | 9 |
| D quality `jinja_primitive` fallback | 23 |
| B/C quality parameter/template model | 0 |
| E missing geometry | 0 |

Adapter split:

| Adapter | Count | Meaning |
|---|---:|---|
| `step_pool` | 9 | Real STEP from shared cache |
| `jinja_primitive` | 23 | Simplified generated placeholder geometry |

## Existing A-grade model hits

| Part no | Name | Source |
|---|---|---|
| GIS-EE-001-05 | 伺服电机 | `step_pool` Maxon ECX STEP |
| GIS-EE-001-06 | 行星减速器 | `step_pool` Maxon GP22C STEP |
| GIS-EE-002-05 | LEMO插头 | `step_pool` LEMO FGG STEP |
| GIS-EE-003-01 | AE传感器 | `step_pool` ATI Nano17 STEP |
| GIS-EE-003-02 | 六轴力传感器 | `step_pool` ATI Nano17 STEP |
| GIS-EE-003-08 | LEMO插头 | `step_pool` LEMO FGG STEP |
| GIS-EE-004-13 | LEMO插头 | `step_pool` LEMO FGG STEP |
| GIS-EE-005-03 | LEMO插头 | `step_pool` LEMO FGG STEP |
| GIS-EE-006-04 | LEMO插座 | `step_pool` LEMO FGG STEP |

## D-grade low-quality backlog

| Priority | Part no | Name | Current source | Recommended upgrade |
|---|---|---|---|---|
| P1 | GIS-EE-001-10 | ZIF连接器 | `jinja_primitive:connector` | Add real vendor STEP or connector semi-parametric template |
| P1 | GIS-EE-001-09 | FFC线束总成 | `jinja_primitive:connector` | Cable/FFC template with ribbon geometry and connector ends |
| P1 | GIS-EE-006-02 | 信号调理PCB | `jinja_primitive:other` | PCB template with board outline, thickness, connector pads |
| P1 | GIS-EE-006-05 | SMA穿壁连接器 | `jinja_primitive:connector` | Real SMA STEP or RF connector template |
| P1 | GIS-EE-006-06 | M12防水诊断接口 | `jinja_primitive:other` | Real M12 STEP or circular connector template |
| P1 | GIS-EE-005-01 | I300-UHF-GT传感器 | `jinja_primitive:sensor` | Vendor STEP / cylindrical sensor template with cable exit |
| P1 | GIS-EE-003-06 | 压力阵列 | `jinja_primitive:other` | Sensor-array template with pad grid / carrier board |
| P2 | GIS-EE-002-02 | 储罐 | `jinja_primitive:tank` | Tank template with caps, ports, seam, transparent option |
| P2 | GIS-EE-002-03 | 齿轮泵 | `jinja_primitive:pump` | Pump template or vendor STEP |
| P2 | GIS-EE-002-04 | 刮涂头 | `jinja_primitive:other` | Applicator/scraper template with blade and outlet |
| P2 | GIS-EE-004-08 | 溶剂储罐（活塞式正压密封） | `jinja_primitive:tank` | Small tank template with piston/cap/port details |
| P2 | GIS-EE-004-09 | 微量泵（溶剂喷射） | `jinja_primitive:pump` | Micro-pump template or vendor STEP |
| P2 | GIS-EE-004-02 | 清洁带盒（供带卷轴+收带卷轴+10m无纺布带） | `jinja_primitive:other` | Cassette template with two reels and belt path |
| P3 | GIS-EE-001-04 | 碟形弹簧垫圈 | `jinja_primitive:spring` | bd_warehouse / SW Toolbox washer or disc-spring template |
| P3 | GIS-EE-001-07 | 弹簧销组件（含弹簧） | `jinja_primitive:spring` | Locating-pin + spring sub-template |
| P3 | GIS-EE-004-06 | 恒力弹簧（供带侧张力） | `jinja_primitive:spring` | Constant-force spring / spiral strip template |
| P3 | GIS-EE-004-04 | 齿轮减速组（电机→收带卷轴） | `jinja_primitive:reducer` | Gear train template with visible gears/shafts |
| P3 | GIS-EE-004-03 | 微型电机 | `jinja_primitive:motor` | Small DC motor vendor STEP or motor template |
| P3 | GIS-EE-004-07 | 光电编码器（带面余量） | `jinja_primitive:sensor` | Encoder template / vendor STEP |
| P3 | GIS-EE-003-05 | 阻尼垫 | `jinja_primitive:other` | Rubber pad template |
| P3 | GIS-EE-003-07 | 配重块 | `jinja_primitive:other` | Mass block template with fastener holes |
| P3 | GIS-EE-004-05 | 弹性衬垫 | `jinja_primitive:other` | Elastomer liner template |
| P3 | GIS-EE-004-10 | 配重块 | `jinja_primitive:other` | Mass block template with fastener holes |

## Build and assembly validation findings

`cad_pipeline.py build --subsystem end_effector` completed successfully, but `ASSEMBLY_REPORT.json` reports 9 warnings:

- Floating/gap warnings: STD-EE-002-05, STD-EE-003-02, STD-EE-003-08, STD-EE-004-06, STD-EE-004-11.
- Size mismatch warnings: STD-EE-001-07, STD-EE-001-09, EE-003-03, EE-003-04.

These warnings overlap with D-grade fallback parts, so model-quality work should address both geometry source and envelope/placement consistency.

## Path and data-consistency observations

- A-grade STEP hits currently point to absolute shared-cache paths under `C:/Users/procheng/.cad-spec-gen/step_cache/...`. That is acceptable as a local runtime report, but future portable reports should preserve logical source identity in addition to absolute paths.
- `codegen` synchronized `cad/end_effector/cad_spec_defaults.py` with root `cad_spec_defaults.py`, adding `_locating`, `_elastic`, and `_transmission` fallback dimensions to the subsystem copy. This removes a local helper drift exposed by the diagnostic run.
- `cad_pipeline.py render --output-dir <relative path>` produced no detected PNGs, while the same render with an absolute output directory succeeded. Follow-up should normalize render output directories to absolute paths before spawning Blender and before manifest detection.

## Recommended next implementation slice

1. Fix `cmd_render` output-dir normalization so relative output paths are made absolute before Blender invocation and manifest scanning.
2. Add connector/electrical templates first: ZIF, FFC ribbon, PCB, SMA, M12. These are high-visibility and currently all D-grade.
3. Add tank/pump/applicator/cleaning cassette templates next, because they dominate the station-level appearance.
4. Route disc springs, spring pins, washers, and connector standards through bd_warehouse / SW Toolbox where available before falling back to templates.
