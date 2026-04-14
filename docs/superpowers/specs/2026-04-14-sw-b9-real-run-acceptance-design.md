# SW-B9 真跑验收设计

**日期**: 2026-04-14
**作者**: proecheng + Claude
**关联设计**: `docs/superpowers/specs/2026-04-13-sw-integration-phase-b-design.md` §SW-B9
**关联决策**: 本设计新增决策 #34（见 `docs/superpowers/decisions.md`）

---

## 1. 背景

Phase B design 第 955 行定义 SW-B9 为"`@requires_solidworks` 真实 COM 测试 + 开发机验收"，包含五条子项：

- (a) demo_bom.csv 覆盖率 ≥ 73%
- (b) ≥ 1 个真实项目 BOM（≥ 100 行）覆盖率实测（决策 #29）
- (c) SwComSession 周期重启实测
- (d) 既有装配验证回归 gate（决策 #31）
- (e) ROI 熔断检查（决策 #33）——若真实 BOM 覆盖率 < 55% 降级范围

截至 2026-04-14：Part 2c P0（subprocess-per-convert 守护）+ P1（Part 2b review backlog 清理）已合入 main（PR #1、#2），但 SW-B9 从未真机跑过。既有 `sw-warmup-smoke.log` 是 0 目标空跑，不构成验收。

## 2. 验收口径声明（决策 #34）

本轮 SW-B9 在以下**放宽口径**下执行并判定：

| 原始口径（Phase B design） | 本轮口径 |
|---|---|
| 五条子项全部 pass | 顶层 pass = Stage 0 && Stage 0.5 && Stage A && Stage C && (Stage D \|\| Stage D skipped_with_reason) |
| (b) 真实 BOM ≥ 100 行 | (b) GISBOT CAD_SPEC ~58 行，样本不足事实写入报告（B1 路线） |
| (a)(b) 覆盖率分母 = BOM 总行数 | 分母 = 过滤后标准件行数（category ∈ {fastener, bearing, washer, nut, screw, pin, key} AND make_buy ∈ {标准, 外购标准件}） |
| (d) 装配回归必跑 | (d) 若 `parts_library.yaml` 中无任何零件消费 sw_toolbox backend → skipped_with_reason（GISBOT 走 CadQuery 原生路径） |
| (d) 决策 #31 metadata 写入 + tolerance 放宽落盘 | (d) **只读检测**，输出 pending 清单留给 Phase SW-C |
| (e) 降级范围落到代码 | (e) 仅产出决策，不改代码 |

**严格版 SW-B9 延后**到真正消费 SW Toolbox sldprt 的装配项目样本到位后再跑。本轮通过后 SW-B9 在 Phase B 完成度中按 "**放宽版通过**" 记账。

## 3. 两阶段 PR 策略

| PR | 范围 | 交付物 |
|---|---|---|
| **PR-a**（前置）| GB 紧固件中英文同义词表 + `sw_toolbox_catalog.match_toolbox_part` tokenize 同义词扩展 | `config/toolbox_cn_synonyms.yaml` + catalog 代码改动 + `tests/test_toolbox_cn_synonyms.py` |
| **PR-b**（主体）| SW-B9 真跑验收脚本 + 报告 + 决策日志 | `tools/sw_b9_acceptance.py` + `tools/cad_spec_bom_extractor.py` + `tools/sw_b9_report_builder.py` + `scripts/refresh_gisbot_fixture.py` + 验收报告 + `docs/superpowers/decisions.md` |

PR-a 必须先合入 main，PR-b 才能跑（否则 Stage 0.5 token 健康检查硬失败）。两个 PR 均遵循 TDD + 内审 + code-review 工作流。

## 4. 架构总览

```
tools/sw_b9_acceptance.py （入口）
│
├─ Stage 0    preflight（Toolbox 库探测、index 重建、min_score 校准）
├─ Stage 0.5  token 健康检查（中英文命中率 > 0 硬门）
├─ Stage A    demo_bom.csv 过滤后标准件覆盖率（目标 ≥ 73%）
├─ Stage B    GISBOT CAD_SPEC 过滤后标准件覆盖率（informational）
├─ Stage D-pre 装配回归前置校验（是否有零件消费 sw_toolbox backend）
├─ Stage C    SwComSession 周期重启（真转 STEP，重启前 5 后 3）
├─ Stage D    装配回归 gate（临时 yaml 切换 + SW 进程隔离 + 只读检测）
└─ Stage E    ROI 熔断决策（基于 Stage B 过滤后覆盖率）

产物: artifacts/sw_b9/*.json → tools/sw_b9_report_builder.py → docs/superpowers/reports/sw-b9-acceptance-2026-04-14.md
```

**关键原则**：脚本不重实现任何 SW 交互逻辑；索引/匹配复用既有 `tools/sw_warmup.py`，校准复用 `tools/sw_warmup_calibration.py`，session 重启复用 `adapters/solidworks/sw_com_session.py`。

## 5. Stage 详细设计

### 5.1 Stage 0 — preflight
- 输入：`--toolbox-root "C:/SolidWorks Data/browser"`（默认）、`--rebuild-index`（SW-B9 默认 True）
- 步骤：
  1. 探测 toolbox-root，确认 GB/ISO/DIN 子目录存在
  2. 强制重建 index（`sw_toolbox_catalog.build_toolbox_index(root)`）；若显式 `--no-rebuild-index` 则复用缓存
  3. 跑 `sw_warmup_calibration.py --bom demo_bom.csv` 取推荐 min_score
- 产出：`preflight.json` = `{schema_version, toolbox_root, index_size, min_score_recommended, min_score_used, rebuild_forced}`
- 硬失败条件：toolbox-root 不存在 / index 构建异常 / 索引 0 条记录

### 5.2 Stage 0.5 — token 健康检查
- 输入：`preflight.json`、demo_bom.csv
- 步骤：对 demo_bom.csv 每行做 tokenize → 查 index 命中
  - 统计中文 token 命中率（"螺钉"、"轴承"、"六角"、"内六角"、"垫圈"、"螺母" 等关键词在 index 里的命中行数）
  - 若全部 0 命中 → 硬失败，提示需先合入 PR-a（中英文同义词表）
- 产出：`stage_0_5.json` = `{schema_version, cn_token_hit_rate, pass}`

### 5.3 Stage A — demo_bom.csv 覆盖率
- 输入：demo_bom.csv（15 行，全标准件，过滤后仍 15 行）、Stage 0 的 min_score
- 步骤：
  1. 按 category + make_buy 过滤（demo 本来就全通过）
  2. 对过滤后每行跑 `sw_warmup.find_sldprt_for_bom`
  3. **不做真 STEP 转换**
- 产出：`stage_a.json` = `{schema_version, total_rows=15, standard_rows=15, matched=N, coverage=N/15, target=0.73, pass=bool, unmatched_rows=[...], excluded_rows=[]}`

### 5.4 Stage B — GISBOT 真实 BOM 覆盖率
- 输入：`D:/Work/cad-tests/GISBOT/cad/end_effector/CAD_SPEC.md`
- 步骤：
  1. 调 `tools/cad_spec_bom_extractor.py` 抽 §3 紧固件清单 + §5 BOM 树 → `stage_b_extracted_bom.csv`
  2. 按 category + make_buy 过滤（预计 ~58 行总 → ~20-30 行标准件）
  3. 对过滤后每行跑匹配（同 Stage A）
- 产出：`stage_b.json` = `{schema_version, total_rows=58, standard_rows=N, matched=M, coverage=M/N, sample_size_below_100=true, note="B1: below ≥100 threshold, informational only", excluded_rows=[...], pass=informational}`

### 5.5 Stage D-pre — 装配回归前置校验
- 输入：当前 `parts_library.default.yaml` + 当前装配管线代码
- 步骤：扫 yaml 和 `adapters/parts/` 下所有 adapter 注册情况，判断是否存在任何零件路径经过 `sw_toolbox` backend
- 产出：`stage_d_pre.json` = `{schema_version, sw_toolbox_consumers=[...], has_consumer=bool}`
- 分支：若 `has_consumer == False` → Stage D 直接 `skipped_with_reason="GISBOT 走 CadQuery 原生路径"`，跳过到 Stage E

### 5.6 Stage C — session 周期重启
- 前置：Stage A 的 matched 列表（取前若干）
- 步骤：
  1. 启 `SwComSession`
  2. 真转换前 5 个 matched sldprt → STEP（subprocess-per-convert 守护生效）
  3. 触发 `cycle_restart()`
  4. 重启后再转换 3 个
  5. 校验：STEP 文件大小 > 1KB + OpenCascade 可读
- 产出：`stage_c.json` = `{schema_version, pre_restart_count, post_restart_count, all_steps_valid, restart_duration_s, pass}`

### 5.7 Stage D — 装配回归 gate
- 前置：Stage D-pre 返回 `has_consumer == True`（否则此 stage 跳过）
- 步骤：
  1. 生成两份临时 yaml：`parts_library_toolbox_off.yaml`（sw_toolbox backend 关）、`parts_library_toolbox_on.yaml`（开）
  2. **before 运行**：
     - 指向 off yaml
     - `pytest tests/test_assembly_validator.py tests/test_assembly_coherence.py tests/test_gen_assembly.py --junitxml=stage_d_before.xml -q`
     - 解析 xml → `{passed, failed_tests=[]}`
  3. **SW 进程隔离**（`_clean_sw_state()`）：
     - `SwComSession.quit()`
     - 轮询直到 `psutil` 看不到 sldworks.exe 或 10s 超时
     - 删 `~/.cad-spec-gen/step_cache/sw_toolbox/` 临时文件
  4. **after 运行**：指向 on yaml，同 suite 重跑
  5. 对比：检测 `after.passed < before.passed` 则记录 `regression_detected=True`（不中止，由 F2 继续）
  6. 新增 false positive（after 新失败测试）→ 产 `stage_d_pending_envelope_upgrades.json`（只读，不写 parts_library.yaml）
- 产出：`stage_d.json` = `{schema_version, before_passed, after_passed, before_failed_tests, after_failed_tests, regression_detected, pending_upgrades_count, pass}`

### 5.8 Stage E — ROI 熔断决策
- 输入：Stage B 的 coverage
- 决策：
  - `coverage >= 0.55` → `decision="keep_full"`
  - `coverage < 0.55` → `decision="downgrade_gb_only"`（记录，不改代码；actions 列表给 Phase SW-C）
- 产出：`stage_e.json` = `{schema_version, real_bom_coverage, threshold=0.55, decision, actions_required=[...]}`

## 6. 数据流与产物

```
artifacts/sw_b9/
├── preflight.json
├── stage_0_5.json
├── stage_a.json
├── stage_b_extracted_bom.csv
├── stage_b.json
├── stage_d_pre.json
├── stage_c.json
├── stage_c_steps/*.step       (真转换落盘，保留供复核)
├── parts_library_toolbox_off.yaml  (临时)
├── parts_library_toolbox_on.yaml   (临时)
├── stage_d_before.xml
├── stage_d_after.xml
├── stage_d.json
├── stage_d_pending_envelope_upgrades.json  (可选，仅 regression 时生成)
├── stage_e.json
└── acceptance_summary.json    (顶层，含 schema_version=1 + 5 stage 汇总)

docs/superpowers/reports/
└── sw-b9-acceptance-2026-04-14.md  (人类可读，git commit)

docs/superpowers/
└── decisions.md                (新建，含决策 #34)
```

**所有 json 均含 `schema_version: 1`**；重跑覆盖 `artifacts/sw_b9/` 除非指定 `--output-dir`。

## 7. 错误处理（F2 非终止）

| Stage | 失败含义 | 处置 |
|---|---|---|
| 0 | Toolbox 缺失 / index 0 条 | 硬失败退出 code 2 |
| 0.5 | 中文 token 0 命中 | 硬失败退出 code 2，提示合入 PR-a |
| A | 覆盖率 < 73% | 记录、继续；pass=false 进 summary |
| B | 任何值 | 不判 pass/fail（informational）|
| D-pre | has_consumer=False | 记录、Stage D 跳过 |
| D | after < before | 记录、继续；regression_detected=true |
| C | STEP 非法 / 重启超时 | 记录、继续 |
| E | < 55% | 不算失败，是决策输出 |

**顶层 pass** = `stage_0.pass && stage_0_5.pass && stage_a.pass && stage_c.pass && (stage_d.pass || stage_d.skipped_with_reason)`

**异常兜底**：顶层 try/except，任何 unhandled exception 必须把当前 stage 状态写进 `acceptance_summary.json` 再 exit；SW session 必在 finally Quit；sldworks.exe 残留由 `_clean_sw_state()` 兜底。

## 8. 新增文件清单

### PR-a（前置）
| 文件 | 行数估计 | TDD |
|---|---|---|
| `config/toolbox_cn_synonyms.yaml` | ~30 行 | 否（数据配置）|
| `adapters/solidworks/sw_toolbox_catalog.py` 改动 | +20 行 | 是 |
| `tests/test_toolbox_cn_synonyms.py` | ~80 行 | 先写失败测试 |

### PR-b（主体）
| 文件 | 行数估计 | TDD |
|---|---|---|
| `tools/sw_b9_acceptance.py` | ~200 行 | 编排主体不写集成测；内部 `_clean_sw_state`、`_parse_junit_xml` 等小函数 TDD |
| `tools/cad_spec_bom_extractor.py` | ~80 行 | 是 |
| `tools/sw_b9_report_builder.py` | ~120 行 | 是 |
| `scripts/refresh_gisbot_fixture.py` | ~40 行 | 否（工具脚本）|
| `tests/test_cad_spec_bom_extractor.py` | ~120 行 | 先写失败测试 |
| `tests/test_sw_b9_report_builder.py` | ~100 行 | 先写失败测试 |
| `tests/test_sw_clean_state.py` | ~60 行 | 测试 `_clean_sw_state` |
| `tests/fixtures/gisbot_cad_spec_snippet.md` | ~40 行 | 由 refresh 脚本生成 |
| `tests/fixtures/stage_*_mock.json` | ~50 行 x 5 | report builder 测试输入 |
| `docs/superpowers/decisions.md` | ~30 行 | 新建 |
| `docs/superpowers/reports/sw-b9-acceptance-2026-04-14.md` | ~150 行 | 由 report builder 产出，非手写 |

**总计**: PR-a ~130 行；PR-b ~820 行（含测试与 fixture）

## 9. 测试策略

### PR-a
- `test_toolbox_cn_synonyms.py`：载入 yaml、tokenize 扩展、端到端匹配（"GB/T 70.1 M6×20 内六角圆柱头螺钉" → 命中 GB socket head screw M6×20 sldprt）
- 回归：全量跑 `tests/test_sw_toolbox_*.py` 确保既有行为不变

### PR-b
- 详见第 8 节各测试文件
- 编排主脚本 `sw_b9_acceptance.py` 不写集成测（真跑即是测试）
- 关键小函数（`_clean_sw_state`、`_parse_junit_xml`、stage 过滤逻辑）必须单元测覆盖

### 真跑验收
- 本机 SW 2024 执行 `python tools/sw_b9_acceptance.py`
- 期望产出：`acceptance_summary.json.pass=true`、`docs/superpowers/reports/sw-b9-acceptance-2026-04-14.md`
- 真跑结果本身是 SW-B9 关闭的判据

## 10. 决策日志 #34

新建 `docs/superpowers/decisions.md`，首条记录：

> **#34 SW-B9 验收口径放宽（2026-04-14）**
>
> **决策**：SW-B9 在本轮按 "顶层 pass = Stage A && Stage C && (Stage D \|\| D_skipped)" 判定；(b) 真实 BOM 样本使用 GISBOT ~58 行（低于原门槛 100 行）；(d) 若装配管线无 sw_toolbox 消费者则 skip；(e) 降级仅记录不落盘。
>
> **理由**：GISBOT 为 CadQuery 原生设计项目，其装配管线不消费 SW Toolbox sldprt，(d) 在此样本上为 no-op；无更合适真实项目可用；拖延完整验收阻塞 Phase B 收尾。
>
> **应用方式**：后续引用 SW-B9 "通过" 时须注明"按决策 #34 放宽口径"；严格版 SW-B9 延至有合适样本时重跑。

## 11. 非目标

- 不改 `parts_library.yaml` 生产配置（Stage D 仅临时 yaml）
- 不改 `assembly_validator.py` 的 clash tolerance
- 不引入 pytest-json-report（改用 junitxml + stdlib）
- 不产生覆盖率 CI 趋势数据（一次性验收，非回归门）
- 不包含 Phase SW-C 工作（envelope 升级、tolerance 放宽、降级到仅 GB 的代码落地）

---

**Spec 状态**: Draft，待用户审阅后提交 git，再转 writing-plans。
