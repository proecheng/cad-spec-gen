# Changelog

All notable changes to this project are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For releases prior to v2.8.0, see the per-version `RELEASE_v*.md` files at the repository root.

---

## [2.10.0] — 2026-04-12

**Theme:** data/ mirror 根治 + legacy P2 regex 清除。结构性清理：mirror 文件从 git tracking 移除，改由 dev_sync.py + pre-commit hook 同步；v2.9.0 遗留的 `_legacy_p2_regex_block` 和 `CAD_SPEC_WALKER_ENABLED` feature flag 正式移除。

See [`RELEASE_v2.10.0.md`](RELEASE_v2.10.0.md) for the full release notes.

### Removed
- **`_legacy_p2_regex_block()`** 函数从 `cad_spec_extractors.py` 移除（~50 行）。v2.9.0 引入的 section-header walker 已经过三个版本真实文档验证，不再保留 regex fallback。
- **`CAD_SPEC_WALKER_ENABLED`** 环境变量 feature flag 移除。`import os` 随之删除。P2 分支从三路简化为二路：walker 可用则使用，否则跳过并 log.warning。
- **`src/cad_spec_gen/data/` 下 56 个 mirror 文件**从 git tracking 移除（`git rm --cached`）。涉及 `python_tools/`、`codegen/`、`config/`、`templates/`、`commands/zh/`、`knowledge/*_zh.md`、`system_prompt.md`、`parts_library.default.yaml`。

### Added
- **`scripts/dev_sync.py`** — 用 `ast.parse()` 从 `hatch_build.py` 提取常量列表，MD5 幂等同步 root 源文件到 `data/`。提供 `sync(root)` API 和 CLI 入口（有变更 exit 1，无变更 exit 0）。
- **`.pre-commit-config.yaml`** — local hook，每次 commit 前自动跑 `dev_sync.py`。`always_run: true`，不依赖文件变更检测。

### Changed
- **`tests/test_data_dir_sync.py`** 从 v2.9.2 的 git drift 检测重写为 dev_sync.py 正确性验证。session-scope fixture 跑一次 `sync()`，59 个参数化 case（新增 `commands_zh`、`knowledge_zh`、`system_prompt` 三个分类）共享结果。
- **`.github/workflows/tests.yml`** — `test` 和 `regression` 两个 job 的 pytest 步骤前各加 `python scripts/dev_sync.py`（exit 0/1 正常，exit 2+ 失败）。
- **`.gitignore`** — 追加 10 条 data/ mirror 忽略规则。

### Validation
- **488 passed / 3 skipped** 全套测试（零回归）
- **59 sync case 全通过** `tests/test_data_dir_sync.py`（从 v2.9.2 的 51 扩展到 59）
- `git status` 在 commit 后干净——无假 `M` 标记

### Migration notes
- `CAD_SPEC_WALKER_ENABLED=0` 环境变量不再生效。如果之前设置过，可以安全移除。
- 开发者 `git pull` 后，已被 `git rm --cached` 的 mirror 文件仍在磁盘上但被 `.gitignore` 忽略。首次 clone 的新开发者需要 `pip install pre-commit && pre-commit install`，或手动跑 `python scripts/dev_sync.py`。

### Files
- New: `scripts/dev_sync.py`, `.pre-commit-config.yaml`
- Modified: `cad_spec_extractors.py`, `tests/test_data_dir_sync.py`, `tests/test_envelope_prose_regex.py`, `.github/workflows/tests.yml`, `.gitignore`, `pyproject.toml`, `CHANGELOG.md`, `README.md`
- Version metadata: `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`
- Removed from tracking (git rm --cached): 56 files under `src/cad_spec_gen/data/`

---

## [2.9.2] — 2026-04-12

**Theme:** 渲染层回归覆盖 + 打包 mirror drift 安全网 + 历史 mirror 同步。Test-only patch release — no production code changes beyond one marker registration. 覆盖 v2.9.0 / v2.9.1 期间明确暴露但一直没有自动化测试的三个技术债区：渲染数学层、打包副本 drift、Blender 真实环境 smoke。

See [`RELEASE_v2.9.2.md`](RELEASE_v2.9.2.md) for the full release notes.

### Added

- **`tests/test_data_dir_sync.py`** — Item 4 Path B 安全网。`ast.parse()` 读取 `hatch_build.py` 的 `_PIPELINE_TOOLS` / `COPY_DIRS` / `TOP_LEVEL_FILES` 常量，自动派生 47 个 `(root, src/cad_spec_gen/data/)` 同步对并参数化为独立 case。若 root 源文件被修改但 mirror 未同步，测试 fail 并打印 `cp ... && git add ...` 修复命令。另含 `test_python_tools_has_no_stray_files`（反向哨兵：data/ 下不应有 `_PIPELINE_TOOLS` 外的 .py 文件）和 `test_sync_pair_count_is_nontrivial`（健康检查）。长期方案（v2.10）是把 `data/python_tools/**` 和 `data/codegen/**` 加入 `.gitignore` 并改为 build-time 生成。

- **`tests/test_render_camera_math.py`** — Item 3 Tier 1：`_resolve_camera_coords` 球坐标→笛卡尔数学的 6 个 case。覆盖 0°/90° 轴对齐 / elevation 90° 正上方 / bounding_radius 缺失时 fallback 到 300 / 已预设 location 的幂等性 / 多相机独立解析。

- **`tests/test_view_key.py`** — Item 3 Tier 1：`extract_view_key` 和 `view_sort_key` 的 9 个 case。覆盖时间戳剥离（`V3_side_elevation_20260411_1712.png` → `V3`）/ V10 两位数 / rc 提供的 camera 字典优先 / V1 < V2 < V10 数字序（不是 V1 < V10 < V2 字符串序）/ 未知文件 tier fallback。

- **`tests/test_material_presets.py`** — Item 3 Tier 1：`MATERIAL_PRESETS` 结构契约的 6 个 case。条目数 ≥ 15 / 每条必含 color+metallic+roughness+appearance / RGBA 4-tuple 在 [0,1] / PBR 参数范围 / appearance 非空字符串 / v2.3 dedup 回归（模块级不应再有 `_PRESET_APPEARANCE` 副本字典）。

- **`tests/test_render_3d_structure.py`** — Item 3 Tier 1：`_get_bounding_sphere` v2.9.0 AABB 中心 fix 的 5 个结构性断言（源码字符串检查，不 mock bpy）。文件存在 / `ast.parse()` 通过 / 顶部仍 import bpy+mathutils / 函数体必含 `min(xs)` / `max(xs)` 不含 `sum(xs)` / 半径仍用半对角线公式。

- **`tests/test_render_3d_blender_smoke.py`** — Item 3 Tier 2：render_3d.py 在**真实 Blender 4.2 进程**内的 import smoke（1 个 case）。用 `blender --background --python-expr "import render_3d; print('RENDER3D_OK')"` 启动 headless Blender，断言哨兵字符串出现。覆盖 bpy API 漂移 / 模块级 bpy 调用 / mathutils 导入路径变更等"离线 pytest 完全看不到"的回归。标记为 `@pytest.mark.blender`，默认跳过，`cad_paths.get_blender_path()` 找不到时自动 skip（CI 无 Blender 保持绿色）。~3 秒完成，不渲染像素。

- **`pyproject.toml` 新增 pytest marker `blender`** — 注册 `blender: real Blender headless smoke tests (v2.9.2+); auto-skip if Blender missing`，并更新 `slow` 描述为 `packaging/wheel-build tests` 以消歧。两个 marker 现在职责分明 —— `slow` 专管 wheel 构建，`blender` 专管真实 Blender 环境。

### Changed

- **`src/cad_spec_gen/data/`** 下 8 个文件的历史 drift 追赶入库：`data/codegen/gen_{assembly,params,parts,std_parts}.py` + `data/python_tools/{cad_spec_extractors,cad_spec_gen,draw_three_view,drawing}.py`。这些 mirror 自 v2.9.0 以来就处于"内容和 root 一致但未入 HEAD"的状态，`python -m build --wheel` 跑完后 git 就会冒出假 `M` 标记。本次 commit 一次性追平。
- **`src/cad_spec_gen/data/`** 新增 3 个历史漏 track 的文件入库：`data/parts_library.default.yaml`（v2.8.0 引入的 `TOP_LEVEL_FILES` 没跟着 commit mirror）+ `data/python_tools/cad_spec_section_walker.py`（v2.9.0 新增的 walker 模块漏了 mirror）+ `data/templates/parts/`（v2.9.0 parts library 引入的新目录漏了 mirror）。这些原本只在 build 时生成，现在进 HEAD 让 editable install 和 git clone 一次就能拿到完整树。

### Validation

- **478 passed / 3 skipped / 2 deselected** non-slow non-blender 套（v2.9.1 基线 401 + 本次新增 77，零回归），31.97 秒
- **1 blender case 通过** `tests/test_render_3d_blender_smoke.py`（~3 秒）在真实 Blender 4.2.16 LTS 内验证 render_3d.py 可 import
- **51 drift case 全通过** `tests/test_data_dir_sync.py` 证实所有 mirror 与 root 字节一致

### Files

- New: `tests/test_data_dir_sync.py`, `tests/test_render_camera_math.py`, `tests/test_view_key.py`, `tests/test_material_presets.py`, `tests/test_render_3d_structure.py`, `tests/test_render_3d_blender_smoke.py`, `RELEASE_v2.9.2.md`, `src/cad_spec_gen/data/parts_library.default.yaml`, `src/cad_spec_gen/data/python_tools/cad_spec_section_walker.py`, `src/cad_spec_gen/data/templates/parts/*.py`
- Modified: `pyproject.toml` (version + marker), `README.md` (Latest marker), `CHANGELOG.md`, `src/cad_spec_gen/data/codegen/gen_{assembly,params,parts,std_parts}.py`, `src/cad_spec_gen/data/python_tools/{cad_spec_extractors,cad_spec_gen,draw_three_view,drawing}.py`
- Version metadata: `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`

---

## [2.9.1] — 2026-04-11

**Theme:** End-to-end regression-hardening after a full real-document pipeline test on the GISBOT end-effector design doc. Four skill bugs fixed; no feature work.

See [`RELEASE_v2.9.1.md`](RELEASE_v2.9.1.md) for the full release notes.

### Added
- **`engineering_enhancer.py`** (new, ~75 lines) — zero-AI enhance backend that was already documented in `pipeline_config.json` under `enhance._backend_doc` and `enhance.engineering` but whose implementation was missing. Reads the `sharpness` / `contrast` / `saturation` / `quality` parameters already present in `pipeline_config.json["enhance"]["engineering"]` and applies `PIL.ImageEnhance.Contrast` → `Sharpness` → `Color` to the Blender PNG before saving as JPG. Function signature matches `comfyui_enhancer.enhance_image()` / `fal_enhancer.enhance_image()` so `cad_pipeline.cmd_enhance` drops it into the existing table-driven dispatch. No external dependencies beyond Pillow (already in the `render` extra). Now the default fallback when Gemini / fal / ComfyUI are all unavailable — matches the advertised auto-detect chain.
- `engineering_enhancer.py` added to `hatch_build._PIPELINE_TOOLS` and `cad_spec_gen.wizard.skill_register._PIPELINE_TOOLS` so the wheel ships it and `cad-skill-setup` deploys it to user project roots.

### Fixed
- **`tools/hybrid_render/check_env.py::_find_blender`** missed the `pipeline_config.json` `blender_path` field — inconsistent with `cad_paths.get_blender_path()` which does read it. On machines where Blender is installed outside of `PATH` / `tools/blender/` / `%ProgramFiles%\Blender Foundation\` the env-check reported Level 3 CAD even though the pipeline itself could locate Blender and render fine. Now `_find_blender()` checks (1) `BLENDER_PATH` env var → (2) `pipeline_config.json.blender_path` (new) → (3) project-local portable → (4) `shutil.which` → (5) platform default install locations (`%ProgramFiles%\Blender Foundation\Blender\blender.exe`, `/usr/bin/blender`, `/Applications/Blender.app/Contents/MacOS/Blender`; also new).
- **`assembly_validator.py::check_f2_size_mismatch`** crashed with `TypeError: '<' not supported between instances of 'str' and 'float'` after v2.9.0 changed `codegen/gen_assembly.py::parse_envelopes` to return `{pno: {"dims": (w,d,h), "granularity": str}}` instead of `{pno: (w,d,h)}`. The validator was not updated for the new shape, so `sorted(expected, reverse=True)` sorted dict keys (`["granularity", "dims"]`) and the subsequent numeric comparison on `e_sorted[k]` exploded. New `_envelope_dims(env)` helper tolerates both tuple and dict shapes; `check_f2_size_mismatch` and `check_f3_compactness` both route through it. GATE-3.5 validation no longer aborts builds post-Phase 3.
- **`cad_pipeline.py enhance --backend` argparse choices** was missing `"engineering"` even though `pipeline_config.json._backend_doc` advertised it as a legal value. Invoking `--backend engineering` raised `argparse.ArgumentError` at parse time. Added to `choices=[...]` with updated `help=` text.
- **`cad_pipeline.py::cmd_enhance`** the dispatch had no branch for `"engineering"`, so even with the argparse fix above, any `backend == "engineering"` case would have fallen through to the `else:` branch and been silently re-normalised to `gemini`. New branch loads `engineering_enhancer.enhance_image` into the same `_enhance_fn` / `_enhance_cfg_key` table-driven slots used by `comfyui` / `fal` / `fal_comfy`.

### Validation
- Full end-to-end pipeline run against `D:\Work\cad-tests\04-末端执行机构设计.md` (the GISBOT end-effector chapter) with `CAD_PROJECT_ROOT` redirected to a fresh working directory — verified artifact counts: 26 STEP (11 自制 + 14 std + 1 assembly), 11 DXF + 11 2D-drawing PNG, 14 3D render PNG (7 views × 2 timestamp copies), 7 engineering-enhanced JPG, 7 Chinese-labeled annotated JPG, 1 GLB, 1 ASSEMBLY_REPORT.json. Phases 1–6 all reported OK; GATE-3.5 surfaced 5 legitimate design warnings (4 F1 floating + 1 F2 size mismatch) instead of crashing with a TypeError.

### Files
- New: `engineering_enhancer.py`, `src/cad_spec_gen/data/python_tools/engineering_enhancer.py`, `RELEASE_v2.9.1.md`
- Modified: `tools/hybrid_render/check_env.py`, `assembly_validator.py`, `cad_pipeline.py`, `src/cad_spec_gen/data/python_tools/cad_pipeline.py`, `hatch_build.py`, `src/cad_spec_gen/wizard/skill_register.py`, `README.md`
- Version metadata: `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`

---

## [2.9.0] — 2026-04-11

**Theme:** Section-header walker + granularity enforcement + vendor STEP auto-synthesizer.

See [`RELEASE_v2.9.0.md`](RELEASE_v2.9.0.md) for the full release notes. Summary:

### Added
- **`cad_spec_section_walker.py`** (~770 lines) — stateful Markdown walker that attributes `模块包络尺寸` envelope markers to BOM assemblies via 4-tier hybrid matching: Tier 0 (`_find_nearest_assembly` regression guard) / Tier 1 (structured pattern — `工位N`, `第N级`, `模块N`) / Tier 2 (dual-path CJK char + ASCII word subsequence) / Tier 3 (CJK bigram + ASCII word Jaccard similarity). Two-phase dispatch: `_match_header` at header-push time, `_match_context` at envelope-emit time with a 500-char window. Per-instance regex compilation — no module-level state. Subsystem configurable via `trigger_terms` / `station_patterns` / `axis_label_default` / `bom_pno_prefixes` constructor kwargs.
- **Six-step granularity enforcement chain**: `WalkerOutput.granularity` → `extract_part_envelopes` dict → `§6.4` `粒度` column → `parse_envelopes` header-name lookup → `PartQuery.spec_envelope_granularity` → `JinjaPrimitiveAdapter` REJECTS `station_constraint` envelopes for per-part sizing. Guarded by `tests/test_walker_downstream_integration.py::test_station_constraint_not_used_as_part_size`.
- **`adapters/parts/vendor_synthesizer.py`** (329 lines) — factory registry that builds dimensionally-accurate parametric stand-ins for vendor parts (Maxon GP22C, LEMO FGG, ATI Nano17). `StepPoolAdapter` auto-invokes the synthesizer on missing STEP files, warming `~/.cad-spec-gen/step_cache/` so fresh projects with only a design doc route vendor BOM rows to real geometry without hand-crafted YAML.
- **`parts_resolver.keyword_contains` matcher** — substring match across BOTH `name_cn` and `material` columns. Default `parts_library.default.yaml` uses this to cover project-specific vendor-name placement variations.
- **`cad_pipeline.py spec --out-dir <path>`** — redirect subsystem output to a custom directory so tests can run the full pipeline against `tmp_path` without mutating `cad/<subsystem>/`.
- **113 new tests** across 6 new test files + 2 existing file extensions: unit (73), fixtures (13), cross-subsystem isolation + determinism (3), real-doc integration (3), six-step enforcement (1), rendering (1), plus adapter/resolver/codegen extensions.

### Changed
- **`cad_spec_extractors.extract_part_envelopes` return type**: `dict` → `tuple[dict, WalkerReport]`. `WalkerReport` carries `unmatched`, `stats`, and `feature_flag_enabled`. `cad_spec_gen.py:656` updated to destructure.
- **`cad_spec_extractors.py` P2 block** replaced by walker invocation. Legacy regex block preserved behind `CAD_SPEC_WALKER_ENABLED=0` feature flag as `_legacy_p2_regex_block` helper (will be removed in v2.10).
- **`codegen/gen_assembly.py::parse_envelopes`** return shape: `dict[pno, (w,d,h)]` → `dict[pno, {"dims": (w,d,h), "granularity": str}]`. Positional `cells[3]` dims lookup unchanged; granularity read by header name with `"part_envelope"` default for legacy §6.4 tables. `codegen/gen_parts.py` and `codegen/gen_params.py` legacy callers unwrap via `isinstance(env, dict)` check for backward compat.
- **`parts_resolver.PartQuery`** gains `spec_envelope_granularity: str = "part_envelope"` field. Default safe for all legacy callers.
- **`adapters/parts/jinja_primitive_adapter._resolve_dims_from_spec_envelope_or_lookup`** REJECTS envelopes whose granularity is not `"part_envelope"`, falling through to `lookup_std_part_dims`.
- **`cad_spec_gen.py §6.4` rendering** — imports legend constants from the walker module (`TIER_LEGEND_MD`, `CONFIDENCE_LEGEND_MD`, `GRANULARITY_LEGEND_MD`, `CONFIDENCE_VERIFY_THRESHOLD`, `UNMATCHED_SUGGESTIONS`). First 5 columns preserved (positional compat with `parse_envelopes`); new audit columns appended: `| 轴向标签 | 置信度 | 粒度 | 理由 | 备注`. Confidence <0.75 rendered as `**0.62 VERIFY**`. New `§6.4.1 未匹配的包络` subsection with reason-driven suggestion templates.
- **`cad_spec_extractors._find_nearest_assembly`** parametrized with `bom_pno_prefixes` kwarg. Auto-derives from BOM via `pno.rsplit('-', 1)[0]` when not supplied, so Tier 0 regression guard generalizes beyond `GIS-EE-NNN` to arbitrary `XYZ-ABC-NNN` subsystems.
- **`hatch_build._PIPELINE_TOOLS`** ships `cad_spec_section_walker.py` in the wheel.
- **`tools/synthesize_demo_step_files.py`** refactored as a thin CLI wrapper around `vendor_synthesizer.py`.

### Fixed
- **GISBOT end-effector envelope attribution** — the walker correctly attributes all 4 station envelopes in the real `04-末端执行机构设计.md` document (previously returned zero). Validated by `tests/test_section_walker_real_docs.py::test_end_effector_docs_match_four_stations`.
- **`codegen/gen_std_parts.py` `step_import` path resolver** now handles absolute paths for shared-cache STEP hits. Previously unconditionally wrapped the path with `os.path.join(_here, "..", "..", step_path)` which broke on absolute cache paths.
- **`src/cad_spec_gen/render_3d.py _get_bounding_sphere`** now uses axis-aligned bounding box center instead of the vertex centroid. Vertex density on one side of the model (fine curved surfaces) no longer biases the camera framing. The radius is the half-diagonal — a tight upper bound that guarantees the sphere encloses all geometry.
- **`cad_pipeline.py` `_run_subprocess`** gains `warn_exit_codes` parameter so callers can mark specific exit codes as "completed with warnings" rather than hard failures. Used by `gen_parts.py` where exit=2 means scaffolds were emitted with TODO markers (valid scaffolds, just unfinalized).
- **`cad_pipeline.py` `_deploy_tool_modules`** adds `cad_spec_defaults.py` to the deployed tool list so `draw_three_view.save()` can lazy-import its surface roughness and part-no helper tables at runtime.

### Validation
- **Tests: 383 passed, 3 skipped, 1 deselected** (up from 270 baseline; +113 new tests, 0 regressions)
- **Real-doc integration**: end_effector 4/4 station envelopes matched via Tier 1; lifting_platform skipped (documented known limitation — sparse data); `--out-dir` flag preserves `cad/end_effector/` mtimes across a full pipeline run
- **Determinism**: walker output is byte-identical under `PYTHONHASHSEED=random` (subprocess test validates stable `(-score, pno)` tie-break sort keys in Tier 2/3)
- **Cross-subsystem isolation**: two `SectionWalker` instances with different `trigger_terms` in one process produce independent output and have distinct compiled regexes
- **Backwards compatibility**: feature flag `CAD_SPEC_WALKER_ENABLED=0` falls back to the legacy P2 regex block without requiring a code revert

### Migration notes
See [`RELEASE_v2.9.0.md`](RELEASE_v2.9.0.md) § "Migration notes" for the `extract_part_envelopes` return-type change, `PartQuery` constructor update for manual walker-envelope consumers, the rollback feature flag, and non-GISBOT subsystem kwargs.

### Files
- New: `cad_spec_section_walker.py`, `adapters/parts/vendor_synthesizer.py`, `RELEASE_v2.9.0.md`, 6 new test files, 13 synthetic fixtures, 2 BOM YAML fixtures + regenerator
- Modified: `cad_spec_extractors.py`, `cad_spec_gen.py`, `codegen/gen_assembly.py`, `codegen/gen_std_parts.py`, `codegen/gen_parts.py`, `codegen/gen_params.py`, `parts_resolver.py`, `adapters/parts/jinja_primitive_adapter.py`, `adapters/parts/step_pool_adapter.py`, `parts_library.default.yaml`, `tools/synthesize_demo_step_files.py`, `cad_pipeline.py`, `hatch_build.py`, `src/cad_spec_gen/render_3d.py`, `docs/pipeline_architecture.md`, `docs/PARTS_LIBRARY.md`, `README.md`
- Version metadata: `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`

---

## [2.8.2] — 2026-04-10

**Theme:** Flange visual fidelity + GLB per-part bbox correctness + Phase B vendor STEP coverage expansion.

### Added
- **`tools/synthesize_demo_step_files.py`** — generates dimensionally accurate parametric stand-in STEP files for vendor parts that the project doesn't have real STEP downloads for. Ships three demo parts:
  - Maxon GP22C 53:1 planetary gearhead (Φ24 × 48 mm + Φ6 × 12 mm output)
  - LEMO FGG.0B.307 push-pull plug (Φ8.6 × 37 mm + hex collet + cable tail)
  - ATI Nano17 6-axis force/torque sensor (Φ17 × 14.5 mm + cable tab)
  Documentation links to the official vendor STEP download pages so users can swap in real files.
- **`codegen/consolidate_glb.py`** — post-export GLB merger that collapses CadQuery's per-face mesh split back into one mesh per part. Groups sibling Mesh nodes by `_<digit>` suffix prefix and concatenates them into a single Trimesh under the canonical part name. Gracefully no-ops when `trimesh` is not installed (the helper handles the import probe internally).
- **9 new tests** in `tests/test_consolidate_glb.py` across three layers: prefix grouping logic (4), trimesh availability gating (2), full round-trip on a 2-part fixture (3 — gated by `@pytest.mark.skipif`).
- **Auto-invocation** of the GLB consolidator from `cad_pipeline.py build` between `build_all.py` completion and DXF rendering. Logs `[consolidate_glb] N components → M consolidated parts` so the user can see it run.
- **GISBOT `parts_library.yaml`** updated with 7 new exact-part_no STEP routes covering the GP22C reducer, ATI Nano17 sensor, and 5 LEMO connector instances (the same model is used in 5 different cable harnesses).

### Changed
- **`templates/part_module.py.j2` (`disc_arms` block)** — arm boxes now extend 2 mm INSIDE the disc cylinder edge (`_arm_overlap`) instead of being tangent to it. Without this overlap, OCCT's `union()` of arm + disc was returning a `Compound([disc, arm])` of disjoint Solids rather than a single fused Solid (because the tangent contact has zero volume). The visible tip of the arm is unchanged.
- **`templates/assembly.py.j2`** — docstring update only; the GLB consolidator call lives in `cad_pipeline.py` (cleaner pipeline-vs-generated-code separation).
- **`cad_pipeline.py`** — `cmd_build` now runs the consolidator on all `*_assembly.glb` files in `DEFAULT_OUTPUT` after `build_all.py` succeeds. The step is wrapped in `try/except ImportError` so projects without `trimesh` continue silently.

### Fixed
- **Multi-solid bug in `disc_arms` template**: `make_ee_001_01()` was returning a `cq.Workplane` whose `.val()` was a Compound with **5 disconnected Solids** because the 4 arm boxes were tangent to the disc cylinder edge (zero-volume overlap). After the `_arm_overlap = 2 mm` fix, `.Solids()` returns 1 fused Solid. Verification on the GISBOT flange:
  - Before: `.Solids() = 5`, `.Faces() = 51`, single fused solid: NO
  - After: `.Solids() = 1`, `.Faces() = 35`, single fused solid: YES
  - bbox unchanged (171×171×25), volume unchanged (310 cm³)
- **`EE-001-01` GLB parent component bbox**: was a degenerate `6 × 0 × 8 mm` representing one tiny face. After the multi-solid fix + the consolidator post-process, it is now `171 × 171 × 25 mm` with 4536 mesh triangles representing the entire flange. The same fix applies to all 39 BOM parts in the GISBOT end_effector.
- **CadQuery per-face GLB split**: `cq.Assembly.save("file.glb", "GLTF")` walks each part's OCCT topology and emits one Mesh node per Face — a 100-face part becomes 100 sibling glTF nodes. This is hard-coded behavior in OCCT's `RWGltf_CafWriter` (no flag to suppress it). The new `consolidate_glb.py` post-process collapses sibling components back into per-part meshes, taking GISBOT from 321 components down to 39.

### Phase B coverage impact

GISBOT end_effector library coverage went from **2.9% → 23.5%** (1 → 8 STEP routes), an 8x improvement on the same BOM. The 26 remaining `jinja_primitive` parts are vendor-specific items that bd_warehouse genuinely cannot model (sensors, pumps, seals, custom gear sets) — the new coverage report makes it clear which ones could be upgraded by adding STEP files.

### Validation
- Tests: **169 passed** (was 160 in v2.8.1 — +9 new consolidator tests, 0 regressions)
- GISBOT end_effector pipeline: codegen + build + DXF render + assembly validation all pass
- ASSEMBLY_REPORT: `1 WARNING` (the pre-existing 002-04 5 mm gap), F4 max_extent=402 mm, F5=86.7% — identical to v2.8.1
- Build log shows `[consolidate_glb] EE-000_assembly.glb: 321 components → 39 consolidated parts`

### Files
- New: `codegen/consolidate_glb.py`, `tests/test_consolidate_glb.py`, `tools/synthesize_demo_step_files.py`
- Modified: `templates/part_module.py.j2`, `templates/assembly.py.j2`, `cad_pipeline.py`, `pyproject.toml`, `src/cad_spec_gen/__init__.py`, `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`, `CHANGELOG.md`

---

## [2.8.1] — 2026-04-09

**Theme:** Registry inheritance + coverage report — close the parts library "user can't tell what's happening" loop.

### Added
- **`extends: default`** in `parts_library.yaml`. Project YAML can now inherit from the skill-shipped `parts_library.default.yaml` instead of completely replacing it. Project mappings are **prepended** to default mappings (project rules win first-hit-wins, default rules act as fallback for parts the project doesn't explicitly cover). Project top-level keys (`step_pool`, `bd_warehouse`, `partcad`, `version`) override default top-level keys shallowly. Unknown `extends:` values are logged as warnings and the project YAML is loaded standalone.
- **Resolver coverage report** in `gen_std_parts.py`. Replaces the previous one-line summary with a per-adapter table showing which specific parts each adapter handled, plus an aggregate row and a hint footer pointing at `docs/PARTS_LIBRARY.md` for upgrading fallback parts. Format is plain ASCII (one box-drawing dash) so it renders correctly on every CI runner including Windows GBK consoles.
- New `PartsResolver.coverage_report()` and `PartsResolver.decisions_by_adapter()` methods.
- 13 new tests in `tests/test_parts_resolver.py`: 6 for `extends: default` merge semantics (prepend ordering, top-level override, drops `extends` key from result, unknown value graceful fallback, kill switch, no-extends backwards compat) + 7 for coverage report (empty state, grouping, jinja-last ordering, truncation of long lists, conditional hint footer, ASCII-only output, decisions_by_adapter shape).

### Changed
- `parts_resolver.load_registry()` rewritten to handle the inheritance step. The legacy "first-file-wins" search path is preserved exactly when `extends:` is absent — projects without `extends:` continue to behave like v2.8.0.
- `codegen/gen_std_parts.py` end-of-run output: replaces `[gen_std_parts] resolver decisions: a=N, b=M` with the multi-line coverage report.
- `D:/Work/cad-tests/GISBOT/parts_library.yaml` migrated to `extends: default`. The previous hardcoded MR105ZZ → bd_warehouse `M4-9-2.5` (Φ4×Φ9×2.5) override has been removed — it was wrong (MR105ZZ is Φ5×Φ10×4 and bd_warehouse 0.2.0 has no exact equivalent). The bearing now correctly falls through to `jinja_primitive` with the right Φ10×4 dimensions, and the file documents why with an inline comment.
- `docs/PARTS_LIBRARY.md` documents the new inheritance pattern, the coverage report format, and a troubleshooting section explaining the three common reasons parts end up in `jinja_primitive` (bd_warehouse category not covered, miniature/non-ISO size, name keywords don't match).

### Fixed
- **GISBOT MR105ZZ misclassification**: the previous v2.8.0 GISBOT yaml hardcoded the bearing to `SingleRowDeepGrooveBallBearing(M4-9-2.5)` which is bd_warehouse's 618/4 (Φ4×Φ9×2.5) — wrong inner, outer, and width. The bearing now uses `jinja_primitive` with correct Φ10 OD × 4 mm width from the BOM material column.
- **Sparse-yaml trap**: a project that wrote a 3-rule `parts_library.yaml` previously **completely replaced** the default registry, silently disabling the category-driven `bearing → bd_warehouse` / `fastener → bd_warehouse` rules. With `extends: default` projects can keep their YAML sparse without losing default coverage. The trap is documented in `docs/PARTS_LIBRARY.md`.

### Compatibility
- **Backwards compatible.** Projects without `extends:` in their `parts_library.yaml` continue to use the legacy first-file-wins behavior. The `CAD_PARTS_LIBRARY_DISABLE=1` kill switch still short-circuits before any YAML is parsed.
- **No new pipeline intermediate files.** Coverage report is stdout-only.
- **Test suite**: 160 passed, 0 skipped (was 145 in v2.8.0; +13 new + 2 previously-skipped optional `bd_warehouse` tests now passing under `PYTHONUTF8=1`).

### Validation
- Full `tests/` suite: 160 passed
- GISBOT end_effector pipeline (Phase 1 spec → Phase 2 codegen → Phase 3 build): all phases pass, ASSEMBLY_REPORT identical to v2.8.0 (1 WARNING for the pre-existing 002-04 5 mm gap edge case, F4 max_extent=402 mm, F5=86.7 % completeness)
- Resolver coverage report on GISBOT correctly shows `step_pool=1, jinja_primitive=33` with the hint footer

---

## [2.8.0] — 2026-04-09

**Theme:** Parts library system + assembly coherence consolidation.

Full notes: [`RELEASE_v2.8.0.md`](RELEASE_v2.8.0.md)

### Added
- **Parts library system** (Phase A + B + C) — adapter-based resolver dispatching purchased BOM rows to one of:
  - `bd_warehouse` (parametric bearings, fasteners, threaded parts) via `BdWarehouseAdapter`
  - Local STEP file pool via `StepPoolAdapter`
  - `partcad` package manager via `PartCADAdapter` (opt-in)
  - `JinjaPrimitiveAdapter` (terminal byte-identical fallback)
- New `parts_resolver.py` core: `PartQuery`, `ResolveResult`, `PartsResolver`, registry loader, `bd_to_cq()` helper
- New `parts_library.yaml` registry format (project-local, optional) with ordered mapping rules: exact `part_no`, `part_no_glob`, `category` + `name_contains` / `material_contains` keywords
- New `catalogs/bd_warehouse_catalog.yaml` — 76 ISO bearing designations across 5 classes + 7 fastener classes, extracted from `bd_warehouse` 0.2.0 CSVs
- New `parts_library.default.yaml` — skill-shipped tiered default registry
- New optional extras in `pyproject.toml`: `parts_library`, `parts_library_bd`, `parts_library_pc`
- New §6.4 source tag namespace `P7:STEP` / `P7:BW` / `P7:PC` for parts-library-derived envelopes (with `P7:*(override_P5)` / `P7:*(override_P6)` variants)
- New P5 (chain_span) and P6 (`_guess_geometry`) envelope backfill loops in `cad_spec_gen.py`
- First CI workflow `.github/workflows/tests.yml` — Linux + Windows × Python 3.10/3.11/3.12 matrix + a `regression` job that enforces byte-identical legacy output via `CAD_PARTS_LIBRARY_DISABLE=1`
- Upstream monitor `tools/check_bd_warehouse_upstream.py` for gumyr/bd_warehouse#75
- New documentation `docs/PARTS_LIBRARY.md` (architecture, mapping vocabulary, kill switches, troubleshooting)
- New tests: `tests/test_parts_resolver.py` (24), `tests/test_parts_adapters.py` (22 + 2 optional live)
- New env var kill switch `CAD_PARTS_LIBRARY_DISABLE=1`
- New CLI hint: `--parts-library PATH` propagated through `cad_pipeline.py`

### Changed
- `codegen/gen_std_parts.py` — `_GENERATORS` dispatch removed, `for p in parts:` delegates to `resolver.resolve()`. Public function signature unchanged. Three generated body forms (`codegen` / `step_import` / `python_import`) all preserve the `make_*() → cq.Workplane` zero-arg contract.
- Generated `std_*.py` files are self-contained — `_bd_to_cq()` helper is inlined per file (not imported), so they work without skill root on `sys.path`.
- `templates/part_module.py.j2` + `gen_parts._guess_geometry()` — flange `disc_arms` template rewritten: arms now extend outward from the disc edge with R=65 mm mounting platforms; renders as a recognizable 4-arm hub instead of a plain disc.
- `BdWarehouseAdapter._auto_extract_size_from_text()` — rewrote to use longest-key substring matching against `iso_designation_map` first (handles `NU2204` / `7202B` / `623-2Z`), then falls back to digit-only `iso_bearing` regex. Fastener path also matches bare `M\d+` for washers/nuts written without an explicit length. Routing smoke test: 2/10 → 10/10 hits.
- `parts_library.default.yaml` — tiered class selection: specific bearing classes first (cylindrical / tapered / angular / capped), generic deep-groove last; specific fastener head types first, `HexHeadScrew` / `HexNut` / `PlainWasher` last.
- `cad_spec_extractors._match_name_to_bom()` — added `assembly_pno` scoping parameter to prevent cross-assembly name leak; 2-char prefix matching is disabled when unscoped.
- `cad_spec_extractors.parse_assembly_pose()` — §6.2 assy regex now accepts optional 4-segment `part_no` like `(GIS-EE-001-08)`, stripping back to the parent prefix; layer parsing terminates on any `### ` subsection.
- `cad_spec_extractors.compute_serial_offsets()` — connection-only chain nodes (e.g. `[4×M3螺栓]`) no longer advance the cursor; multi-node sub-chains accumulate top/bottom per pno across the chain and emit a single span result.
- `gen_assembly._resolve_child_offsets()` — auto-stack respects container envelope bounds (wraps cursor at the largest envelope); high-confidence §6.3 entries bypass the outlier guard; §6.2 author Z values take priority over §9.2 contact constraints; disc-spring washers snap to the nearest already-positioned part in the same assembly.
- `gen_assembly._STD_PART_CATEGORIES` — added `"other"` so 阻尼垫 / 配重块 / 刮涂头 etc. are no longer dropped at assembly time.
- `JinjaPrimitiveAdapter` — `"other"` removed from `_SKIP_CATEGORIES`, new `_gen_generic()` block emits a default box when dims are missing.
- `cad_spec_gen.py` P7 backfill — uses `cad_paths.PROJECT_ROOT` for `parts_library.yaml` lookup (was incorrectly using design doc's grandparent).
- `tests/test_prompt_builder.py` — rewritten from scratch against the current `enhance_prompt.py` API (10 scenarios). Old tests targeted deleted `prompt_builder.py` symbols.
- Skill metadata updated: `skill.json`, `src/cad_spec_gen/data/skill.json`, `.cad_skill_version.json`, `src/cad_spec_gen/__init__.py`, `pyproject.toml` → 2.8.0.

### Fixed
1. Connection-only chain nodes added a phantom 20 mm cursor advance (`compute_serial_offsets()`)
2. Cross-assembly BOM name matching leaked across stations (`_match_name_to_bom()`)
3. §6.2 assy regex rejected 4-segment `part_no`s (`parse_assembly_pose()`)
4. `parse_assembly_pose` did not terminate §6.2 layer parsing on `### ` subsections
5. Multi-node sub-chain spans were overwritten instead of accumulated
6. §6.4 envelope backfill missing for chain spans and `_guess_geometry()` results
7. Auto-stack ignored container envelope bounds, causing 300+ mm cumulative drops below station housings
8. §6.3 high-confidence entries were rejected by the §6.4 outlier guard when envelope coverage was low
9. §9.2 auto-derived contact constraints overrode author-provided §6.2 Z values
10. Disc-spring washers were stacked far below their host PEEK ring (no fastener-accessory snap)
11. `"other"`-category parts (阻尼垫 / 配重块 / 刮涂头) produced no geometry, breaking F5 completeness
12. `_STD_PART_CATEGORIES` in `gen_assembly.py` was missing `"other"`
13. P7 envelope backfill used the wrong project root for `parts_library.yaml` lookup
14. `BdWarehouseAdapter` size extraction missed `NU2204` / `7202B` / `623-2Z` (suffix-stripping regex)
15. Generated `std_*.py` could not import `_bd_to_cq` from `parts_resolver` at build time on machines without the skill on `sys.path` (helper now inlined)
16. Missing `import os` in `cad_spec_gen.py` after the P6 backfill addition

### Safety guarantees
- `make_*() → cq.Workplane` contract unchanged
- `CAD_SPEC.md` schema unchanged
- No new pipeline intermediate files
- Byte-identical regression: `CAD_PARTS_LIBRARY_DISABLE=1` or absent `parts_library.yaml` produces 0-diff `gen_std_parts.py` output vs v2.7.1
- `bd_warehouse` and `partcad` are truly optional — lazy imports, graceful fallback
- P1..P4 envelope source tiers (author-provided) are never overridden by P7

### Known limitations
- `bd_warehouse` Windows CJK locales hit `UnicodeDecodeError` on CSV read. Workaround: `PYTHONUTF8=1` (already in CI). Upstream fix: gumyr/bd_warehouse#75.
- GISBOT 002-04 刮涂头 has a 5 mm pre-existing F1 gap; accepted as-is.

### Validation
- Tests: 135 passed, 2 skipped (optional live `bd_warehouse`)
- Byte-identical regression: 0 diff with kill switch
- End-to-end on `04-末端执行机构设计.md`: all 4 phases pass, both `step_pool` and `bd_warehouse` paths exercised, 7 PNG views rendered.

---

## [2.7.1] — 2026-04-09

Assembly positioning fix release. 4 bugs in `gen_assembly._resolve_child_offsets()` causing floating / overlapping components in GLB output. See [`RELEASE_v2.7.1.md`](RELEASE_v2.7.1.md).

## [2.7.0] — 2026-04-09

Assembly constraint declaration system: §9.2 auto-derived from connection matrix, fit codes (H7/m6) extraction, GATE-3.5 assembly validator (F1–F5 sanity checks).

## [2.5.0] — 2026-04-08

§6.3 per-part positioning, §6.4 envelope dimensions, §9.1 assembly exclusions consumed by `gen_assembly.py`. See [`RELEASE_v2.5.0.md`](RELEASE_v2.5.0.md).

## [2.4.1] — 2026-04-07

Hotfixes for v2.4.0 (review pipeline, bom_parser).

## [2.4.0] — 2026-04-07

Review pipeline: design review → DESIGN_REVIEW.md → user iterate / `--auto-fill` / `--proceed`.

## [2.3.0] — 2026-04-07

View-aware AI enhancement materials, MATERIAL_PRESETS unification.

## [2.2.2] — 2026-04-03

Cable / harness length capping, std-part dimension lookup via parameter table.

## [2.2.1] — 2026-04-03

Auto-annotation in HLR sheets, near-real flange / bracket geometry inference, per-part offset positioning. See [`RELEASE_v2.1.2.md`](RELEASE_v2.1.2.md) (release note kept under the prior numbering).

## [2.1.1] — 2026-04-02

Hotfix release.

## [2.1.0] — 2026-03-31

Multi-view consistency, viewpoint lock, image role separation. See [`RELEASE_v2.1.0.md`](RELEASE_v2.1.0.md), [`RELEASE_v2.1.1.md`](RELEASE_v2.1.1.md).

## [2.0.0] — 2026-03-30

Major release: 6-phase unified pipeline orchestrator (`cad_pipeline.py`).

## [1.9.0] — 2026-03-29

Pre-2.0 stabilization.

## Earlier releases

See git history (`git log v1.7.0..v1.9.0`) for v1.7.x – v1.9.0.

[2.8.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.8.0
[2.7.1]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.7.1
[2.7.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.7.0
[2.5.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.5.0
[2.4.1]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.4.1
[2.4.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.4.0
[2.3.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.3.0
[2.2.2]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.2.2
[2.2.1]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.2.1
[2.1.1]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.1.1
[2.1.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.1.0
[2.0.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v2.0.0
[1.9.0]: https://github.com/proecheng/cad-spec-gen/releases/tag/v1.9.0
