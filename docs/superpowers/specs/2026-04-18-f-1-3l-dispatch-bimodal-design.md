# F-1.3l: SW COM Dispatch elapsed_ms 双峰分布根因调查 — 设计稿

- **Date**：2026-04-18
- **Status**：Design (brainstorming 产出，待 writing-plans)
- **Origin**：F-1.3j+k 收尾遗留（commit `b0f9c00`）；AC-3 K1 5 点 2/5 越界下沿，双峰 ~310ms / ~3295ms
- **上位追溯**：`memory/project_f13jk_handoff.md` §⏭️ F-1.3l 下次开工指南
- **优先级**：中（日常 merge 不阻断；F.2 状态机卡在 PASS pickup-only，F-1.3l 关闭后升级 PASS clean）
- **时间预算**：1-2 calendar days（根因档）

---

## 1. 背景

### 1.1 问题陈述

F-1.3j+k 在 sw-smoke CI 采到 K1 5 数据点，发现 `sw-inspect-deep.json.layers.dispatch.data.elapsed_ms` 呈**双峰分布**：

| run | event | elapsed_ms | 间隔（距前次物理 SW 活动） | AC-3 [3000, 15000] |
|---|---|---|---|---|
| F.1 24554801242 | push | 5492 | — | ✅ |
| run-B 24605253673 | dispatch | 306 | ~8min | ❌ |
| run-C 24605350467 | dispatch | 314 | +5min | ❌ |
| K4 24605595945 | dispatch | 3295 | +14min | ✅ |
| K5 24605597487 | dispatch | 3295 | +1min 串行 | ✅ bit-exact K4 |

**表现**：两个 cluster ~310ms（"浅档"）和 ~3295ms（"深档"），疑似与"物理 SW 最近活动时间间隔"正相关（< ~15min → 浅档，> ~15min → 深档）。F.1 5492ms 孤立点疑似"OS cold + Defender 首扫 SLDWORKS.exe" outlier。

**关键事实**：`attached_existing_session=false` 全程成立 — 不是明面的 attach/cache 路径。

### 1.2 目标

定位双峰根因，并基于根因决定 AC-3 区间是需要调整（预期行为）还是需要修代码（sw_probe bug）。

### 1.3 三条备选假设

1. **H1 — SW license daemon idle timeout** 生命周期 ~15min
2. **H2 — SW COM server registration cache** 热冷切换（in-process vs out-of-process）
3. **H3 — Windows Defender 实时扫描 cache age-out**

---

## 2. Scope（brainstorming 锁定）

| 维度 | 决策 |
|---|---|
| 目标档 | **根因驱动**（必须定位到具体机制，而非仅调 AC-3 区间） |
| 数据采集 | **主动脚本梯度扫描**（占用 runner 约 4-6 小时一次） |
| 破坏性实验 | **非侵入 Defender + 允许 license kill + 允许 COM API 替换** |
| 代码持久度 | **per-step timing 永久合入 main / 3 条假设专用探针临时** |

---

## 3. 架构

两阶段 + 分层持久化。

```
Phase 1：仪器化基础设施（永久合入 main，TDD 严格）
├── probe_dispatch 重构：单点 elapsed_ms → 4 段 per-step timing
│   字段：dispatch_ms / revision_ms / visible_ms / exitapp_ms
├── t0 起点迁移：ThreadPoolExecutor.submit 之后 → worker 函数第一行
├── sw_inspect 输出 schema 新增 4 个 optional 字段（向下兼容）
├── assert_sw_inspect_schema.py (AC-2) 断言 per-step 存在 + 总和 ≈ elapsed_ms
└── 单测覆盖冷启 / attach / timeout / 异常路径全集

Phase 2：3 假设验证（临时探针 + 实验脚本）
│   **实验前**：
│     - workflow 文件 `runs-on` 临时改为 `[self-hosted, f13l-exclusive]` 挡 sw-smoke CI
│       （GitHub Actions workflow 层改动，非 runner settings；见 §10 R8）
│     - 新建 `F13L_REVERT_CHECKLIST.md` 记录所有临时变动点
│   **对照原则**：严格交替（奇 = 干预 / 偶 = baseline），**不得**用"前 N / 后 N"
│
│   **职责分工**（关键：解决早退出 vs ≥20 点样本量矛盾）：
│     - H1 / H2 = **根因证伪**：允许早退出（命中即停）
│     - H3 = **timing 分布采样**：**始终执行**（为 §8 AC-3 区间公式提供 ≥ 20 点分布）
│       例外：若 Phase 2 判定分支为"代码 bug"（§8 分支 B），H3 跳过（bug 修后 CI 重采）
│
├── H1 license daemon（先，最便宜；证伪型）
│   ├── 临时探针：license_session_age_sec
│   └── 交替实验：10 轮，奇数轮前 Stop-Process sldWorkerManager / 偶数轮 baseline
│   判定后：HIT → 跳 H2，直接跑 H3；FALSIFIED → 进 H2；INCONCLUSIVE → 补 +5 点重判
│
├── H2 COM ROT / registration cache（次；证伪型）
│   ├── 临时探针：com_rot_entry_count / com_registration_timestamp
│   ├── **前置等价性 baseline**：同进程连续调 `Dispatch` 10 次 + `CoCreateInstanceEx` 10 次，
│   │   确认无干预条件下两 API 的 per_step timing 无系统差
│   │   - 系统差 < 20% → 进主实验
│   │   - 系统差 ≥ 20% → 放弃 H2（CSV `hypothesis` 字段标 `H2-abandoned`），直接跳 H3；
│   │     runbook §7 记录"H2 因 API 语义差异无法归因，未证伪也未命中"
│   └── 交替实验：10 轮，奇数轮 DEBUG_USE_COCREATEINSTANCEEX=1 / 偶数轮 baseline
│   判定后：HIT → 跳 H3；FALSIFIED → 进 H3；INCONCLUSIVE → 补 +5 点重判
│
└── H3 Defender scan cache + timing 分布采样（始终跑，除非判定为分支 B）
    ├── 临时探针：defender_last_scan_age_sec / defender_rtp_state
    ├── 间隔梯度 5/10/15/20/30/45/60min × 3 次 = 21 点
    └── Get-MpComputerStatus 只读，顺路收集做相关性分析
    判定：相关性分析产出 H3 HIT / FALSIFIED 结论（不影响是否继续跑，H3 就是终点）

Phase 3：根因确认 + AC-3 调整
├── runbook §7 新增"F-1.3l 根因"子段（一句话结论 + 数据链接）
├── AC-3 区间调整（预期 [100, 15000]，具体值由 Phase 2 数据决定）
└── ≥ 6 次 sw-smoke CI 一致落在新区间 → F.2 状态 PASS pickup-only → PASS clean

临时探针 revert
└── chore(f-1-3l): 收尾 — 删除 DEBUG 开关 + 实验脚本 + 临时字段
```

**关键不变量**：
- Phase 1 改动**不依赖**任何假设成立，per-step timing 对未来所有 dispatch 调查都有价值
- H1 / H2 是**根因证伪型**实验，允许命中早退出；H3 是**timing 分布采样型**实验，始终执行（除非分支 B 跳过）
- runner 占用分批：Phase 1 只跑本地 pytest + CI 冒烟；Phase 2 每轮实验 30-45 分钟 runner 独占

---

## 4. 组件清单

### Phase 1（永久合入 main）

| 文件 | 变动 |
|---|---|
| `adapters/solidworks/sw_probe.py` | `probe_dispatch` 重构：worker 返回 `per_step_ms` dict；`t0` 起点移入 worker；`ProbeResult.data` 新增 `per_step_ms` 字段；模块级常量 `PER_STEP_SENTINEL_RAISED = -1` / `PER_STEP_SENTINEL_UNREACHED = 0` 定义（供未来其他 probe_* 函数复用） |
| `adapters/solidworks/sw_inspect_schema.py` 或 `.json` | `layers.dispatch.data` 新增 4 个 optional int 字段 |
| `tools/assert_sw_inspect_schema.py` | AC-2 断言补 per-step：4 字段存在 + 冷启路径总和 ≈ `elapsed_ms`（±50ms） |
| `tests/test_sw_probe_dispatch_per_step.py`（新建） | 覆盖冷启 / attach / timeout / 3 步异常 / t0 起点回归 |
| `tests/test_assert_schema_per_step.py`（新建） | 覆盖 schema 新断言的 happy / 缺字段 / 类型错 / 总和超差 4 case |
| `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` | §7 F-1.3l follow-up 段补"Phase 1 完成"标记 |

### Phase 2（临时探针 + 实验脚本；调查完毕 revert）

| 文件 | 类型 | 用途 |
|---|---|---|
| `scripts/f13l_run.ps1` | 新建·临时 | **一键入口**：`--phase 2 --auto-chain` 按 H1→H2→H3 串行跑，命中即停 |
| `scripts/f13l_h1_license_test.ps1` | 新建·临时 | H1 交替实验脚本，10 轮 CSV 输出 |
| `scripts/f13l_h2_com_api_test.py` | 新建·临时 | H2 前置等价 baseline 20 点 + 交替实验 10 轮 CSV |
| `scripts/f13l_h3_gradient_scan.ps1` | 新建·临时 | H3 间隔梯度 5/10/15/20/30/45/60min × 3 次 = 21 点 |
| `scripts/f13l_analyze.py` | 新建·临时 | **一键分析**：`--csv X.csv --hypothesis H1` 读 CSV → pandas groupby → 输出"命中 / 证伪 / 需补数据"三态决策 |
| `adapters/solidworks/sw_probe.py` | 临时 patch | `DEBUG_USE_COCREATEINSTANCEEX` 开关；`probe_investigation_env()` 不进 schema |
| `f2-evidence-f13l/` | 新建·gitignored | CSV 数据归档（本地磁盘） |
| `F13L_REVERT_CHECKLIST.md` | 新建·临时 | 调查开始时写，收尾 revert 时逐项勾（防漏删） |

### Phase 3（根因确认后改动）

| 文件 | 变动 |
|---|---|
| `tools/assert_sw_inspect_schema.py` | AC-3 下限：3000 → 100（或根因决定的新下限）；上限保留 15000 |
| `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` | §7 新增"F-1.3l 根因记录"子段 |
| `tests/test_assert_schema_ac3.py` | 新下限边界测试 |

---

## 5. 数据流

### Phase 1（永久）

```
sw_inspect CLI
  └─> probe_dispatch(timeout=60)
        ├─ attach 路径 → per_step_ms={全 0}; elapsed_ms=0
        ├─ timeout → dispatch_ms=timeout_sec*1000; 其他 3 段=0
        ├─ 单步异常 → 完成段真实值; 失败段=-1 (哨兵); 未到达段=0
        └─ 冷启 → 4 段都有真实值; elapsed_ms = sum(per_step_ms.values())

sw_inspect 输出
  └─> sw-inspect-deep.json
        layers.dispatch.data.{elapsed_ms, per_step_ms: {...}, ...}

assert_sw_inspect_schema.py (AC-2)
  └─> 断言 per_step_ms 4 字段存在 + 冷启路径总和 ≈ elapsed_ms（±50ms）
        失败 → rc=65 (schema) / rc=66 (总和超差)
```

### Phase 2（临时）

**统一 CSV schema**（所有 H1/H2/H3 脚本都输出完全相同的 17 列；不适用字段填空 → pandas 读为 NaN）：

| 列 | 类型 | H1 | H2 | H3 | 说明 |
|---|---|---|---|---|---|
| `hypothesis` | str | `H1` | `H2` | `H3` | 实验标签，便于合并多 CSV 分析 |
| `iter` | int | ✓ | ✓ | ✓ | 本实验内第几次 |
| `ts_utc` | str | ✓ | ✓ | ✓ | ISO8601 |
| `kill_flag` | int | 0/1 | — | — | H1 专用：1 = 干预前 Stop-Process；其他留空 |
| `com_api_flag` | int | — | 0/1 | — | H2 全程填（baseline 的 20 点 = Dispatch 10 + CoCreateInstanceEx 10；main 的 10 点 = 奇偶交替） |
| `baseline_phase` | str | — | `pre` / `main` | — | H2 前置等价 baseline 20 点（`pre`）vs 主实验 10 点（`main`） |
| `interval_min` | int | — | — | ✓ | H3 专用：距前次 Dispatch 分钟数 |
| `dispatch_ms` | int | ✓ | ✓ | ✓ | 空字段 = 未运行到；详见 §6 哨兵约定 |
| `revision_ms` | int | ✓ | ✓ | ✓ | 同上 |
| `visible_ms` | int | ✓ | ✓ | ✓ | 同上 |
| `exitapp_ms` | int | ✓ | ✓ | ✓ | 同上 |
| `elapsed_ms` | int | ✓ | ✓ | ✓ | sw_inspect 顶层字段（冷启应 = 4 段和） |
| `attached_existing_session` | bool | ✓ | ✓ | ✓ | 若 true → 整行视为无效（过滤）|
| `license_session_age_sec` | int | ✓ | — | — | H1 临时探针 |
| `com_rot_entry_count` | int | — | ✓ | — | H2 临时探针 |
| `com_registration_timestamp` | str | — | ✓ | — | H2 临时探针 |
| `defender_last_scan_age_sec` | int | — | — | ✓ | H3 临时探针 |

**流程**：

```
PS1 实验脚本（e.g. f13l_h1_license_test.ps1）
  ├─ loop 10 次:
  │    if iter % 2 == 1 (奇): Stop-Process sldWorkerManager -Force; sleep 30s
  │    $result = python -m tools.sw_inspect --layer dispatch --json
  │    $env = python -c "from adapters.solidworks.sw_probe import probe_investigation_env; print(probe_investigation_env())"
  │    追加 CSV 一行（17 列统一 schema；不适用列留空；哨兵 -1 序列化为空 → pandas NaN）
  └─> f2-evidence-f13l/h1_license.csv

一键分析（scripts/f13l_analyze.py）
  └─ pandas.read_csv(na_values=['', '-1'])
        .pipe(lambda df: df[df['attached_existing_session'] != True])  # 过滤 attach 行
        .dropna(subset=['dispatch_ms'])                                # 过滤"抛异常"行
        .groupby(flag).describe()
        两组 per_step_ms 中位数差 ≥ 2x → 输出 "HIT"
        两组差 < 1.5x → 输出 "FALSIFIED"
        1.5x ≤ 差 < 2x → 输出 "INCONCLUSIVE, need +5 samples"
        （注意：attach 行不删除而过滤，保留原始行便于"偶发 attach 频率"事后追溯；
         详见 §6 "CSV 语义取舍"段）
```

---

## 6. 错误处理

| 错误类别 | `per_step_ms` 行为 | severity | hint |
|---|---|---|---|
| pywin32 缺失 | 全 0 | fail | 装 `[solidworks]` extra |
| attach 路径（GetObject OK + 读 Revision 异常） | 全 0 | fail | 同现有 |
| 冷启 Dispatch timeout | `dispatch_ms=timeout_sec*1000`，其他 3 段=0 | fail | 检查许可证 / 位数 / progid |
| 冷启单步异常 | 完成段真实值；失败段=-1（哨兵）；未到达段=0 | fail | print `str(exc)` |
| 非异常崩溃（进程 die） | 已记录段值 + `exit_app_ms=0` | fail | fallback catch-all |

**关键设计决策**：
- **哨兵 -1 vs 0** 严格区分"运行过但抛异常"vs"没运行到"；分析时 -1 可 filter
- **JSON 字段内部**保留真实值 -1 / 0；**CSV 序列化**时，-1 → 空字段（便于 pandas 读为 NaN，避免 `mean()` 把 -1 当合法值计算）；0 保持为 "0"（表示"有意义的零"，attach 路径）
- `scripts/f13l_analyze.py` 开头统一 `df = pd.read_csv(path, na_values=['', '-1'])` + `df.dropna(subset=['dispatch_ms'])` 预处理
- **schema 对异常路径宽松**：AC-2 只断言"字段存在 + 类型 int"，不断言"总和 = elapsed_ms"（异常路径总和不等是合法）
- **Phase 2 实验脚本单轮失败不中断 loop**：跑 10 轮某次 COM 抖动只丢一行 CSV，不全废

**CSV 语义取舍**（显式标注，未来维护者参考）：
- CSV 中 -1（抛异常）和空字段（不适用列）经 `na_values=['', '-1']` 后都 → NaN，下游**无法区分**两者。取舍原因：统一为 NaN 让 pandas 分析代码简洁（一次 dropna 两种都过滤），符合本 spec "用户零操作"原则
- 代价：未来若需分析"异常率"（e.g. "ExitApp 多久抛一次"），CSV 不够；需要回去看 sw-inspect JSON 原始输出
- attach 路径整行**不删除**而是 analyze 时**过滤不参与统计**，保留行便于事后追溯"偶发 attach 事件频率"

**回滚保证**：
- H1 `finally` 段确保 Ctrl+C 时不留"license daemon kill 但没重启"状态（Windows service 自拉起，无需手动恢复）
- H2 `DEBUG_USE_COCREATEINSTANCEEX` 进程内环境变量，脚本结束自动失效

**特别不处理**：
- runner 宕机 / 断网 — 不做断点续跑；重头来一次
- 硬件时钟漂移 — `_time.perf_counter()` monotonic，免疫 NTP 同步

---

## 7. 测试策略

### Phase 1（Linux CI 全跑，TDD 严格）

`tests/test_sw_probe_dispatch_per_step.py`：

1. `test_cold_dispatch_per_step_sum_matches_elapsed` — mock 各步耗时；断言 sum ∈ [elapsed-50, elapsed+50]
2. `test_attach_path_per_step_all_zero` — mock GetObject 成功；per_step 全 0；`attached_existing_session=True`
3. `test_timeout_path_per_step` — mock `future.result` 抛 TimeoutError；`dispatch_ms=timeout_sec*1000` 其他=0
4. `test_revision_step_raises` — mock `_app.RevisionNumber` 抛；`revision_ms=-1`，其他填 0 或真实值
5. `test_visible_step_raises` — 同上
6. `test_exitapp_step_raises` — 同上
7. `test_per_step_all_int_types` — AC-2 schema 前置条件
8. `test_worker_t0_start_inside_worker`（回归钉子）— mock `ThreadPoolExecutor.submit` 睡眠 500ms 再调 worker；断言 `dispatch_ms < 100ms`（若 t0 被误放在 submit 前会 fail）

`tests/test_assert_schema_per_step.py`：

1. `test_schema_accepts_valid_per_step`
2. `test_schema_rejects_missing_per_step_field` → rc=65
3. `test_schema_rejects_non_int_per_step_value` → rc=65
4. `test_schema_rejects_sum_mismatch_cold_path` → rc=66
5. `test_schema_accepts_sum_mismatch_exception_path`（异常路径总和不等合法）

**TDD 严格顺序**（RED → GREEN → REFACTOR）：
1. test 1 RED → 最小实现：worker 返回 dict → GREEN
2. test 8 RED → t0 移入 worker → GREEN
3. test 2 / 3 / 4 / 5 / 6 / 7 逐个 RED → GREEN
4. schema 测试 1-5 逐个 RED → GREEN

### Phase 1 集成测试（Windows runner，手动触发）

- sw-smoke CI 现有 7 AC 全绿（AC-1/2/2.5/4 必须保持绿；AC-3 仍允许间歇 fail）
- sw-inspect-deep.json 真实产出 `per_step_ms` 4 字段
- `assert_sw_inspect_schema.py` 在真 SW 数据上不抛 schema error

### Phase 2 测试层（极简）

- 实验脚本**不写单测**（一次性用完即 revert，ROI 低）
- PS1 `$ErrorActionPreference='Stop'` + 每步 try/catch
- CSV 输出前最小 validation：
  * 列数 == 预期（17 列）
  * 该实验**应填字段**无 NaN（见 §5 schema 表 "H1/H2/H3" 列的 ✓ 或 0/1 标记；不适用列留空是合法的）
  * 例：H1 脚本输出的行必须有 `kill_flag / dispatch_ms ... /license_session_age_sec` 非 NaN；
       `com_api_flag / baseline_phase / interval_min / com_rot_* / defender_*` 留空为合法

### Phase 3 测试层

- `test_ac3_lower_bound_shallow_median_half_passes`（浅档中位数 × 0.5 边界合法）
- `test_ac3_upper_bound_deep_median_2x_passes`（深档中位数 × 2 边界合法）
- `test_ac3_below_lower_bound_fails`（比浅档中位 × 0.5 还小的异常点 → fail）
- `test_ac3_above_upper_bound_fails`（比深档中位 × 2 还大的异常点 → fail）
- `test_ac3_old_lower_3000ms_now_within_range`（旧下限 3000ms 数据点在新区间内）

---

## 8. 关闭条件

全部满足才关闭 F-1.3l：

1. **Phase 1 永久改动合入 main**
   - 所有 Phase 1 单测 GREEN
   - sw-smoke CI 7 AC 全绿（AC-3 仍允许间歇 fail）
   - code-review 无阻断性问题

2. **Phase 2 至少 1 条假设有明确结论**
   - **HIT**：H1/H2/H3 之一被实验数据证实（`scripts/f13l_analyze.py` 输出 `HIT`，两组中位数差 ≥ 2x）
   - **INCONCLUSIVE 处理路径**（差 1.5-2x）：
     * 该假设自动补采 +5 点，最多补 2 轮（共 10 点新数据）
     * 第 2 轮后仍 INCONCLUSIVE → 视为 FALSIFIED，进入下一假设
     * 根据"用户零操作"原则，`scripts/f13l_run.ps1 --auto-chain` 内部自动执行此补采流程
   - **全伪**（H1/H2 FALSIFIED + H3 相关性无统计意义）：
     * 触发 F-1.3l-Q2 升级假设
     * **升级路径**：新开 `docs/superpowers/specs/YYYY-MM-DD-f-1-3l-q2-design.md`（不追加本 spec），引用本 spec 的 Phase 2 CSV 数据作为"已证伪基线"
     * F-1.3l 本 spec 状态改为"closed-inconclusive"，F.2 维持 PASS pickup-only 不降级
   - **H2-abandoned**（§3 定义）：视为 FALSIFIED，继续 H3

3. **AC-3 区间调整有数据支撑**（公式必须保留回归保护能力，不得 tautology）
   - **样本量门槛**：Phase 2 H3 梯度扫描 21 点 + H1/H2 已采集点，合计 ≥ 20 点；
     且**浅档 ≥ 5 点 / 深档 ≥ 5 点**（任一档 < 5 点 → 延长 H3 采样至满足）
   - **分支 A — 根因 by design，双峰保留**（预期多数场景）：
     * 新下限 = **浅档中位数 × 0.5**（若异常比浅档还快 ≥ 2x，仍能报警；不是 min-20% 这种画靶命中式）
     * 新上限 = **深档中位数 × 2**（若异常比深档还慢 ≥ 2x，仍能报警）
     * 例：浅档中位 310ms / 深档中位 3295ms → 新区间 `[155, 6590]`
   - **分支 B — 根因是 bug 已修，双峰塌缩成单峰**（Phase 2 H3 跳过）：
     * Phase 3 fix merge 后，CI 采新点（无 Phase 2 数据可用）
     * 新下限 = 单峰中位数 × 0.5
     * 新上限 = 单峰中位数 × 2
     * 单峰样本量门槛 ≥ 10 点
   - 区间调整 PR 合入 main

4. **runbook §7 F-1.3l 根因记录段写入**
   - 一句话结论（"根因是 X，表现为 Y，因此 AC-3 调整为 [a, b]"）
   - 数据链接（`f2-evidence-f13l/` CSV 的 git sha + 行数）
   - 未来如何复现验证（3-5 行）

5. **≥ 6 次 sw-smoke CI run 的 timing 分布与 Phase 2 实测一致**
   - **分支 A**（双峰保留）：6 次 run 至少有 2 个点落在浅档 ± 50% + 2 个点落在深档 ± 50%，
     不得出现落入"两峰之间谷值（e.g. 500-2000ms）"的异常点（否则说明区间过宽丢失回归保护）
   - **分支 B**（单峰）：6 次 run 均落在单峰中位数 × 0.5 ~ × 2 区间内
   - F.2 状态机从 PASS pickup-only → PASS clean

6. **临时探针 git revert**
   按 `F13L_REVERT_CHECKLIST.md`（Phase 2 开工时建）逐项勾。**仅 Phase 2 临时改动需 revert；Phase 1 / Phase 3 永久改动保留**：
   - [ ] `DEBUG_USE_COCREATEINSTANCEEX` 开关从 `sw_probe.py` 删除
   - [ ] `probe_investigation_env()` 函数从 `sw_probe.py` 删除
   - [ ] `scripts/f13l_run.ps1`
   - [ ] `scripts/f13l_h1_license_test.ps1`
   - [ ] `scripts/f13l_h2_com_api_test.py`
   - [ ] `scripts/f13l_h3_gradient_scan.ps1`
   - [ ] `scripts/f13l_analyze.py`
   - [ ] `F13L_REVERT_CHECKLIST.md` 本身（最后）
   - [ ] workflow 文件 `runs-on` 从 `[self-hosted, f13l-exclusive]` 恢复 `[self-hosted]`（行号记在 checklist）
   - [ ] `f2-evidence-f13l/` 保留 CSV 但 `.gitignore`（本地磁盘归档；§8.4 runbook 记录 git sha 指针）
   - **保留不 revert**：`per_step_ms` 字段、schema 迁移、AC-2/AC-3 断言调整、Phase 1 单测 — 这些是 F-1.3l 留下的永久基础设施
   - commit message：`chore(f-1-3l): 移除临时探针 + F-1.3l 收尾`

### 分支：根因找到但不修代码

若根因是"SW COM 的预期行为"（e.g. license daemon idle timeout 本来就是设计如此）：
- AC-3 区间扩为 `[100, 15000]`
- sw_probe 代码**不修**
- runbook 标注为"by design, accepted"
- F.2 状态机照常升级 PASS clean

### 分支：根因找到且是代码 bug

若根因是 sw_probe 代码错误（e.g. attach 路径探测误判 / GetObject 在 ROT miss 时返回 stale proxy）：
- 开 F-1.3l-fix 子任务单独走 TDD 修代码
- AC-3 区间**不变**（维持 `[3000, 15000]`），等修完后期望双峰塌缩成单峰
- F.2 状态机升级条件改为"fix merge + 6 次 run 一致"

---

## 9. 不做清单（YAGNI）

- ❌ 实时监控 dashboard — 一次性调查，非长期 SRE 任务
- ❌ 假设 4+（SW 启动抖动 / Windows Update / Hyper-V 抢占）— 仅当 3 条全伪才升级到 F-1.3l-Q2（不在当前 spec 范围）
- ❌ 跨 runner / 跨机器复现 — 当前只一台 self-hosted runner，样本足够；future work
- ❌ 修 `probe_dispatch` 的 ThreadPoolExecutor 软超时妥协（已知问题）
- ❌ F-1.3l 发现反哺 Phase B Part 2 的 sldprt→STEP 监控（另一 spec 的事）
- ❌ 给临时探针写单测（ROI 低）

---

## 10. 风险与缓解

| ID | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | 3 条假设全伪 | 中 | 调查失败，AC-3 无法下调 | 触发 F-1.3l-Q2 开新 spec；F.2 仍保持 PASS pickup-only 不降级 |
| R2 | Phase 1 TDD 破坏 AC-2 现有断言 | 低 | sw-smoke CI 回归 | `test_schema_accepts_sum_mismatch_exception_path` 显式覆盖异常路径宽松断言 |
| R3 | Phase 2 实验脚本污染 runner 环境 | 低 | 后续 CI 失败 | `$ErrorActionPreference='Stop'` + `finally` 恢复；license daemon 自拉起无需手动；`f13l-exclusive` label 隔离 CI |
| R4 | 根因找到是代码 bug 但修代码风险高 | 低 | Phase 1 白做 | 分支路径已在 §8 覆盖；`test_worker_t0_start_inside_worker` 回归保障 |
| R5 | per_step_ms 字段在下游消费者（未来的监控 dashboard）被误解 | 低 | 误报误警 | attach/timeout/异常路径的 per_step 语义在 §6 文档化 + schema 注释里 |
| R6 | H1 实验总时长 ~15min 与假设阈值自相关 | 中 | 实验结论不可信（数据一致性 bug） | §3 明确"严格交替奇偶轮"；相邻两轮间隔差异 ≤ 30s（奇数轮 +Stop+sleep 30s / 偶数轮无），远 << 假设 ~15min 阈值两个量级，故混淆风险可接受 |
| R7 | H2 `CoCreateInstanceEx` vs `Dispatch` 语义差异混入实验 | 中 | H2 结论无法归因于 ROT | §3 H2 前置等价 baseline 20 点；系统差 ≥ 20% 时 H2-abandoned（§8 关闭条件 2）|
| R8 | workflow `runs-on` 临时改 `f13l-exclusive` 被误合 main | 中 | 非 F-1.3l 期间 sw-smoke CI 找不到 runner，所有 PR 卡住 | `F13L_REVERT_CHECKLIST.md` 强制列 workflow 文件行号；Phase 2 开工时在 PR 草稿里单独开子 commit，便于回滚 |

---

## 11. 参考

- 上游 spec：`docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md`
- F.2 spec：`docs/superpowers/specs/2026-04-18-sw-runner-f2-design.md`
- F-1.3j+k spec：`docs/superpowers/specs/2026-04-18-sw-self-hosted-runner-f13jk-design.md`
- runbook：`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` §7
- handoff memory：`memory/project_f13jk_handoff.md`
- 代码：`adapters/solidworks/sw_probe.py:509-678`（当前 `probe_dispatch` 实现）
