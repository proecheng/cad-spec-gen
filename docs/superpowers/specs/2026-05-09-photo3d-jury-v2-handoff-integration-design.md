# photo3d-jury v2 — handoff 集成（A1 子集）设计文档

**作者**：proecheng
**日期**：2026-05-09
**状态**：spec 待审
**前置 spec**：`2026-05-08-photo3d-jury-design.md`（v2.27.0 已发布）
**关联 §**：2026-05-08-photo3d-jury-design.md §11"后续 (v2 路线)"中的 A 簇 A1 子集

---

## 修订历史

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-05-09 | 初稿（brainstorm 5 节 + 5 决策点收敛后落盘） |

---

## 1. 背景与北极星对齐

### 1.1 v2.27.0 后用户体验断点

`photo3d-jury` 作为独立 cli 已上线，能自动给出 5 项语义判定 + photoreal_score。但用户的实际工作流是：

```
photo3d-handoff --confirm        # 跑 enhance + enhance-check（已自动 follow-up）
↓ 用户复制粘贴下一步命令
photo3d-jury --subsystem ...     # 手动跑 jury
↓ 用户看 jury accepted 后再复制粘贴
enhance-review --review-input .../jury_review_input.json  # 手动转正式契约
↓ 然后才能 deliver
photo3d-deliver --subsystem ...
```

**断点**：3 步本可一条命令解决。外行用户被强迫记 3 个命令名 + 2 次复制粘贴 + 1 个文件路径。

### 1.2 北极星 5 gate 对齐

| Gate | 本 PR 提升点 |
|---|---|
| 零配置 | jury config 沿用 v1 不变；新 flag `--with-jury` 复用现有 jury config |
| 稳定可靠 | 默认 strict（verdict ≠ accepted 阻断 handoff），降低用户漏看风险 |
| 结果准确 | jury → enhance-review 串联保证 deliver 前必有正式 ENHANCEMENT_REVIEW_REPORT.json |
| SW 装即用 | 无影响（jury 不涉 SW） |
| 傻瓜式操作 | 一条 `photo3d-handoff --with-jury --confirm` 跑完 enhance + check + jury + review |

### 1.3 已收敛决策点（brainstorm session 摘要）

- **范围**：仅 handoff 路径集成 jury（方案 ①）；autopilot 保持 gate-only 不变，仅在 next_action 文案附加 `--with-jury` 推荐命令
- **strict 默认**：jury verdict ≠ accepted → handoff exit≠0；`--no-strict-jury` 反向 opt-out
- **cost 确认**：`--with-jury` 隐含 `--confirm-cost`；handoff 在 jury 跑前 stderr 强制打印估价 + budget 检查；超 budget 仍 exit=3 abort
- **enhance-review 归属**：orchestrator 层（即 handoff 自身）负责，accepted 后调 `enhance-review` subcommand；jury 子模块不动
- **strict/no-strict 边界**：仅 jury **业务质量**类（preview / needs_review）可被 no-strict 降级为警告；jury **工具自身故障**类（lock busy / config 错 / blocked / internal）必须阻断，no-strict 覆盖不了

---

## 2. 范围与非目标

### 2.1 范围（in-scope）

1. `photo3d-handoff` 加 `--with-jury` `--no-strict-jury` 两个 flag
2. `photo3d-handoff --with-jury` orchestrator 串联 5 步（enhance → enhance-check → jury cost-estimate → jury 实跑 → enhance-review）
3. `tools/photo3d_jury.py` 加 `--cost-estimate-only` flag（dry-run 估价 + budget 检查后立即 return；不进 layer 1/2）
4. `cad_pipeline.py:cmd_photo3d_autopilot` 在 `ready_for_enhancement` 状态的 next_action 命令文案追加 `--with-jury`
5. `HANDOFF_RUN.json` schema add-only 加三字段（`jury_status` / `review_status` / `enhance_review_path`）
6. 中文 stderr 文案模板集中在 `tools/jury/stderr_messages.py` 新模板组（命名前缀 `HANDOFF_*`）
7. 文档：`docs/cad-jury-config.md` 加"通过 photo3d-handoff 一条命令跑闭环"章节
8. 全量测试覆盖（单元 + handoff e2e + autopilot 文案校验）

### 2.2 非目标（out-of-scope；推到独立 PR）

- `photo3d-autopilot --with-jury` 端到端化（autopilot 升级为真正 orchestrator）— 属于 spec §11 方案 ②，本 PR 不做
- `photo3d-jury --summary` 跨 run 聚合视图 — 属于 A2 簇
- `photo3d-jury --json` 机器友好输出 — 属于 A2 簇
- `photo3d-recover` 注册 jury 文件 — 属于 A2 簇
- jury 子模块的 4 层判定逻辑改造（`fallback_profile_ids` chain / `anthropic_native` kind / quota tracker 等）— 属于 B/C/D/E 簇
- jury 自身加 `--auto-review` flag — 已决策由 orchestrator 串联，jury 自身不动

### 2.3 非目标的兼容性承诺

- jury v1 cli 行为完全不变（除 `--cost-estimate-only` 这一新 flag 外）
- 独立用户跑 `photo3d-jury` 仍按 v1 流程（不会"突然多跑 enhance-review"）
- `HANDOFF_RUN.json` 现有字段不动；新加字段在不带 `--with-jury` 时**不出现**（不污染回归用户的报告）

---

## 3. 架构

### 3.1 上下文图

```
┌─ 用户视角 ────────────────────────────────────────┐
│ 一条命令：                                          │
│   cad_pipeline.py photo3d-handoff \                │
│     --subsystem <name> --with-jury [--no-strict-jury] --confirm                       │
└────────────────────┬───────────────────────────────┘
                     ↓
┌─ handoff orchestrator (cad_pipeline.py) ──────────┐
│  1. enhance        (现有 cli call)                 │
│  2. enhance-check  (现有 follow-up)                │
│  3. jury --cost-estimate-only  (新 flag, dry-run)  │
│     → stderr 打印估价 + budget 检查                 │
│  4. jury  (jury v1 4 层主流程, --confirm-cost 内传) │
│     → 等 PHOTO3D_JURY_REPORT.json 落盘             │
│     → 读 jury_report.status 决策                    │
│  5. enhance-review (仅 accepted 才调)              │
│     → 写 ENHANCEMENT_REVIEW_REPORT.json            │
│  6. 写 HANDOFF_RUN.json 终态                        │
└─────────────────────────────────────────────────┘

┌─ photo3d-autopilot (本 PR 仅文案改动) ────────────┐
│  ready_for_enhancement 状态 next_action 文案:      │
│    "cad_pipeline.py photo3d-handoff --with-jury --confirm" │
│  其他状态文案不变                                   │
└─────────────────────────────────────────────────┘
```

### 3.2 文件布局

```
cad_pipeline.py                       ← 改 cmd_photo3d_handoff（新增 ~150 行）
                                       + cmd_photo3d_autopilot 文案（~10 行）
tools/photo3d_jury.py                  ← 加 --cost-estimate-only flag（~30 行）
tools/jury/stderr_messages.py          ← 加 HANDOFF_* 模板组（~60 行）
docs/cad-jury-config.md                ← 新增"handoff 一条闭环"章节（~40 行）
tests/test_photo3d_handoff_with_jury.py（新文件，~400 行）
tests/jury/test_photo3d_jury_cli.py    ← 加 --cost-estimate-only 单测（~80 行）
tests/test_cad_pipeline_autopilot.py   ← 加 next_action 含 jury cmd 用例（~30 行）
tests/jury/test_stderr_messages.py     ← 加 HANDOFF_* 模板覆盖测试（~30 行）
```

### 3.3 模块契约

| 模块 / 函数 | 单一职责 | 输入 | 输出 | 不做 |
|---|---|---|---|---|
| `cmd_photo3d_handoff` (修改) | orchestrator：5 步串联、透传 exit code、决定 strict 行为、写 HANDOFF_RUN.json 终态 | argparse.Namespace（含 with_jury / no_strict_jury 等新字段） | exit code（0 / 1 / 2 / 3 / 4 / 10 / 11 / 12 / 99 / review_exit） | 不实现 jury 业务逻辑；不动 enhance/check 已有逻辑 |
| `tools/photo3d_jury.py:main`（修改） | 现有 jury 入口；加 `--cost-estimate-only` 早 return | argv | exit code（含 0 = 估价 ok / 3 = over budget / 2 = config 错） | dry-run 模式不取锁、不 freeze sha256、不读图、不调 LLM |
| `tools/jury/stderr_messages.py`（增） | `HANDOFF_*` 中文文案模板组 | exit_code + context dict | 单字符串（无 `{xxx}` 残留） | 不做 IO；纯 string format |
| `cmd_photo3d_autopilot`（修改） | 现有 autopilot；改 next_action 命令文案 | 同现有 | next_action.command 字段含 `--with-jury` | 不实跑 jury / 不调 enhance |

### 3.4 不变量

1. **autopilot 行为不变**：autopilot 自身不调 jury / 不调 enhance；只在 next_action.command 字符串里追加 `--with-jury` 子串
2. **jury 子模块边界不动**：`tools/jury/{config,cost,llm_client,verdict,redact,deterministic_gate,input_evidence_binding}.py` 全部 0 改动；只在 `tools/jury/stderr_messages.py` add-only 加 HANDOFF 模板组
3. **handoff 调子进程方式**：必须用 `sys.executable + cad_pipeline.py + subcommand` 形式（与现有 enhance-check follow-up 一致），不直接 import 跨模块函数（避免 cli 副作用泄漏）
4. **`HANDOFF_RUN.json` add-only**：现有字段保持不变；新加字段（jury_status / review_status / enhance_review_path / jury_estimated_usd / jury_actual_usd）仅在 `--with-jury` 启用时出现
5. **strict/no-strict 边界硬约束**：
   - 业务质量类（`preview` / `needs_review`）：strict → exit=10/11 abort；no-strict → exit=0 + warning
   - 工具故障类（`blocked` / `JuryLockBusy` / `JuryConfigError` / `JuryInternalError`）：永远阻断，no-strict 不能覆盖
6. **cost 估价 dry-run 必须无副作用**：`--cost-estimate-only` 不取 `.jury.lock`、不 freeze active_run_id 与 sha256、不 hit 网络
7. **estimated_usd 重复打印 ok**：jury 实跑也会打印估价；handoff 在 step 3 dry-run 也打印；用户看两次不算 bug，是稳健性
8. **enhance-review 失败不污染 jury 报告**：`PHOTO3D_JURY_REPORT.json` 保持 jury 自己写完时的内容；handoff 把 review 失败记到 `HANDOFF_RUN.json` 自己的字段
9. **jury_review_input.json 路径来源**：handoff 必须从 `PHOTO3D_JURY_REPORT.json` 读 `review_input_path` 字段，**禁止扫目录猜文件**（北极星硬约束）

---

## 4. 数据流

### 4.1 完整流程

```
photo3d-handoff --confirm --with-jury [--no-strict-jury]
        │
        ▼
1. enhance        ──fail──▶ exit=enhance_exit；HANDOFF_RUN.json{enhance_status:"failed"}；不调后续步
        │ ok（enhance_status:"ok"）
        ▼
2. enhance-check  ──fail──▶ exit=check_exit；HANDOFF_RUN.json{check_status:"failed"}；不调后续步
        │ ok（check_status:"ok"）
        ▼
3. jury --cost-estimate-only
   读 ENHANCEMENT_REPORT.json 的 views 长度 → 算 estimated_usd
   stderr: "jury 预估 0.04 USD / 4 视角 (budget 0.50 USD)"
   ──cost > budget──▶ exit=3；HANDOFF_RUN.json{jury_status:"cost_over_budget", jury_estimated_usd:0.04}
   ──config 错──▶ exit=2；HANDOFF_RUN.json{jury_status:"config_error"}
        │ ok
        ▼
4. jury (实跑，handoff 内传 --confirm-cost)
   等 PHOTO3D_JURY_REPORT.json 落盘
   读 jury_report.status:
   ┌────────────────────────────────────────────────────────────────┐
   │ status         strict           no-strict                      │
   │ accepted       → step 5         → step 5                       │
   │ preview        → exit=10 abort  → 警告 + skip step 5 + exit=0  │
   │ needs_review   → exit=11 abort  → 警告 + skip step 5 + exit=0  │
   │ blocked        → exit=12 abort（**no-strict 不覆盖**）         │
   │ JuryLockBusy   → exit=4   abort（**透传，no-strict 不覆盖**）  │
   │ JuryConfigErr  → exit=2   abort（同上）                        │
   │ JuryInternal   → exit=99  abort（同上）                        │
   └────────────────────────────────────────────────────────────────┘
        │ accepted（jury_status:"accepted"）
        ▼
5. enhance-review --review-input <jury_review_input_path_from_jury_report>
   ──fail──▶ exit=review_exit；HANDOFF_RUN.json{review_status:"failed"}
        │ ok（review_status:"ok"）
        ▼
6. 写 HANDOFF_RUN.json 终态
   {
     handoff_status: "accepted" | "preview" | ... ,
     enhance_status, check_status, jury_status,
     jury_estimated_usd, jury_actual_usd_or_null,
     review_status, enhance_review_path
   }
```

### 4.2 jury 实跑后 handoff_status 决策表

| jury_status | strict | review_status | handoff_status | exit |
|---|---|---|---|---|
| accepted | * | ok | accepted | 0 |
| accepted | * | failed | review_failed | review_exit |
| preview | strict | n/a (skip) | preview_blocked_by_strict | 10 |
| preview | no-strict | n/a (skip) | preview_warning | 0 |
| needs_review | strict | n/a (skip) | needs_review_blocked_by_strict | 11 |
| needs_review | no-strict | n/a (skip) | needs_review_warning | 0 |
| blocked | * | n/a (skip) | jury_blocked | 12 |
| cost_over_budget | * | n/a (skip) | cost_over_budget | 3 |
| config_error | * | n/a (skip) | config_error | 2 |
| lock_busy | * | n/a (skip) | lock_busy | 4 |
| internal_error | * | n/a (skip) | internal_error | 99 |

### 4.3 不带 --with-jury 的回归路径

- handoff 行为完全等同 v2.27.0：跑 enhance + enhance-check follow-up，写 `HANDOFF_RUN.json` 不含 jury 字段
- 测试用例必须显式 assert 不带 `--with-jury` 时 `HANDOFF_RUN.json` 字段集与现有 schema 完全一致

---

## 5. 错误处理

### 5.1 异常分类与 exit code

| 类目 | exit | strict 可降级 | stderr 文案模板 key |
|---|---|---|---|
| enhance 自身失败 | 透传 enhance | n/a | (沿用现有) |
| enhance-check 失败 | 透传 check | n/a | (沿用现有) |
| jury config 错 | 2 | ✗ 永远阻断 | `HANDOFF_JURY_CONFIG_ERROR` |
| jury cost 超 budget | 3 | ✗ 永远阻断 | `HANDOFF_JURY_COST_OVER_BUDGET` |
| jury lock busy | 4 | ✗ 永远阻断 | `HANDOFF_JURY_LOCK_BUSY` |
| jury preview | 10 / 0 | ✓ no-strict 降级为 warning | `HANDOFF_JURY_PREVIEW_STRICT` / `HANDOFF_JURY_PREVIEW_WARNING` |
| jury needs_review | 11 / 0 | ✓ no-strict 降级为 warning | `HANDOFF_JURY_NEEDS_REVIEW_STRICT` / `HANDOFF_JURY_NEEDS_REVIEW_WARNING` |
| jury blocked | 12 | ✗ 永远阻断 | `HANDOFF_JURY_BLOCKED` |
| jury internal | 99 | ✗ 永远阻断 | `HANDOFF_JURY_INTERNAL_ERROR` |
| enhance-review 失败 | 透传 review | n/a | `HANDOFF_REVIEW_FAILED` |

### 5.2 stderr 模板示例（中文人话）

```python
HANDOFF_JURY_PREVIEW_STRICT = (
    "[handoff] jury 判定 preview（5 项语义检查中 {failed_n} 项 false "
    "或 photoreal_score={score} 低于 min_photoreal_score={min}）。\n"
    "  jury 报告：{report_path}\n"
    "  下一步：修 enhance 配置后重跑；或加 --no-strict-jury 仅警告（结果不进 deliver）。"
)

HANDOFF_JURY_PREVIEW_WARNING = (
    "[handoff WARNING] jury 判定 preview，因 --no-strict-jury 仅警告。\n"
    "  jury 报告：{report_path}\n"
    "  注意：本次 handoff 不会自动跑 enhance-review；deliver 会缺 ENHANCEMENT_REVIEW_REPORT.json。"
)

HANDOFF_JURY_BLOCKED = (
    "[handoff ERROR] jury 检测到输入证据漂移（active_run_id 或 sha256 不一致）。\n"
    "  这是工具自身故障，--no-strict-jury 不会覆盖此错误。\n"
    "  下一步：重跑 enhance 后再来；或检查 ARTIFACT_INDEX.json 是否被外部进程修改。"
)

HANDOFF_JURY_LOCK_BUSY = (
    "[handoff ERROR] jury 被另一进程持锁（PID {pid}）。\n"
    "  下一步：等其他 jury 进程结束，或用 ps/Task Manager 杀掉后重跑。\n"
    "  jury 30 分钟内会自动清理 stale lock。"
)
```

### 5.3 集中处理位置

- **唯一入口**：`tools/jury/stderr_messages.py:format_handoff_message(template_key, context)`
- **handoff 调用方**：`cmd_photo3d_handoff` 在每个失败分支唯一通过 `format_handoff_message(...)` 取字符串后 `sys.stderr.write(...)`
- **禁止**：handoff 自己拼字符串、handoff 自己引用文案常量；所有 HANDOFF_* 文案常量都必须落在 `stderr_messages.py` 内

---

## 6. 测试策略

### 6.1 TDD 铁律

每节落 commit 必须先写失败测试再实现。CLAUDE.md 强制：
- RED：先写测试 + 跑确认失败
- GREEN：写最小实现让测试 PASS
- REFACTOR：清理冗余 + 不增多余逻辑

### 6.2 单元测试

| 测试文件 | 用例 | 预期 |
|---|---|---|
| `tests/jury/test_photo3d_jury_cli.py` | `test_cost_estimate_only_dry_run_returns_early` | exit=0 + stderr 含估价 + 不写 PHOTO3D_JURY_REPORT.json |
| `tests/jury/test_photo3d_jury_cli.py` | `test_cost_estimate_only_over_budget_exit_3` | exit=3 + stderr 含 over budget 文案 |
| `tests/jury/test_photo3d_jury_cli.py` | `test_cost_estimate_only_with_confirm_cost_mutually_exclusive` | exit=2 + stderr "两个 flag 不能同时" |
| `tests/jury/test_photo3d_jury_cli.py` | `test_cost_estimate_only_does_not_acquire_lock` | 跑后 .jury.lock 不存在 |
| `tests/jury/test_photo3d_jury_cli.py` | `test_cost_estimate_only_does_not_freeze_sha256` | 跑后报告不包含 sha256 字段（确认未 freeze） |
| `tests/jury/test_stderr_messages.py` | `test_handoff_templates_no_unfilled_placeholders` | 所有 HANDOFF_* 模板 placeholder 全填充 |

### 6.3 handoff 集成测试

新文件：`tests/test_photo3d_handoff_with_jury.py`（~400 行）

mock 策略：
- 用 `subprocess.run` 的 monkeypatch 替代真实子进程；fake exit code + fake stdout/stderr
- 各 step 的 fake 行为通过 fixture 设置，覆盖 14 种用例

| 用例编号 | 场景 | 预期 |
|---|---|---|
| H1 | 不带 --with-jury（回归） | exit=0 + HANDOFF_RUN.json 无 jury 字段 |
| H2 | --with-jury jury accepted + review ok | exit=0 + handoff_status="accepted" |
| H3 | --with-jury jury preview + strict | exit=10 + handoff_status="preview_blocked_by_strict" + 不调 review |
| H4 | --with-jury --no-strict-jury jury preview | exit=0 + handoff_status="preview_warning" + 不调 review |
| H5 | --with-jury jury needs_review + strict | exit=11 + 不调 review |
| H6 | --with-jury --no-strict-jury jury needs_review | exit=0 + warning + 不调 review |
| H7 | --with-jury [--no-strict-jury] jury blocked | exit=12 + handoff_status="jury_blocked" + 不调 review |
| H8 | --with-jury jury lock busy | exit=4 透传 + 不调 review |
| H9 | --with-jury jury config 错 | exit=2 透传 + 不调 review |
| H10 | --with-jury jury cost over budget | exit=3 + handoff_status="cost_over_budget" + 不调 review |
| H11 | --with-jury jury internal | exit=99 透传 + 不调 review |
| H12 | --with-jury jury accepted + review 失败 | exit=review_exit + handoff_status="review_failed" |
| H13 | enhance step 失败 | exit=enhance_exit + 不调 jury（HANDOFF_RUN.json 仅 enhance_status="failed"） |
| H14 | --with-jury 估价 stderr 强制打印 | stderr 含 "jury 预估 X.XX USD" + budget 字符串 |

### 6.4 autopilot 测试

`tests/test_cad_pipeline_autopilot.py` 追加：

| 用例 | 预期 |
|---|---|
| `test_autopilot_ready_for_enhancement_next_action_includes_with_jury` | next_action.command 字符串含 `--with-jury` 子串 |
| `test_autopilot_other_states_do_not_include_with_jury` | 其他状态 next_action 不含 `--with-jury`（避免误导） |

### 6.5 不写的测试（YAGNI 边界）

- 不测真实 LLM 调用：沿用 jury v1 conftest autouse kill switch（`tests/jury/conftest.py`）
- 不测真实 enhance/render：handoff 测试全 mock 子进程
- 不测 jury v1 已覆盖的 4 层判定逻辑：本 PR 不动那部分

### 6.6 CI 矩阵

- Linux + Windows 都跑（subprocess mock 在两平台行为一致）
- mypy strict 必过（jury v1 已上 strict gate；本 PR 改的所有文件保持 strict）
- ruff check + format 必过
- coverage：handoff 新加路径必须 ≥90% 覆盖（与 jury v1 一致）

---

## 7. 兼容性与迁移

### 7.1 cli 层

- 不带 `--with-jury` 跑 `photo3d-handoff`：行为完全等同 v2.27.0；H1 用例守门
- jury v1 独立用户跑 `photo3d-jury`：行为完全等同 v2.27.0；除非显式加 `--cost-estimate-only` flag

### 7.2 报告 schema

- `HANDOFF_RUN.json`：add-only 加 jury_status / review_status / enhance_review_path / jury_estimated_usd / jury_actual_usd 五字段；`schema_version` 不升（按 jury v1 invariant 14 add-only 兼容性宪章）
- `PHOTO3D_JURY_REPORT.json`：完全不变（jury 子模块 0 改）
- `ENHANCEMENT_REVIEW_REPORT.json`：完全不变（enhance-review 子命令不变）

### 7.3 配置

- `~/.claude/cad_jury_config.json`：完全不变（v1 配置直接可用）
- 不引入新环境变量
- 不引入新的 `~/.claude/` 文件

### 7.4 文档迁移

- `docs/cad-jury-config.md` 加新章节"通过 photo3d-handoff 一条命令跑闭环"
- `docs/PROGRESS.md` 加 v2.28.0 入口
- `README.md` 用法示例追加 `--with-jury` 推荐用法（最小改动）

---

## 8. 实施顺序（plan 阶段拆分预想）

预估 plan 阶段会拆 ~12-15 task。粗顺序：

1. **C0 准备**：建分支（已建）+ spec commit
2. **C1 jury --cost-estimate-only**（不依赖 handoff 改动）：先 RED 写 6 单测 → GREEN 实现 jury main 加 flag → REFACTOR
3. **C2 stderr 模板组**：HANDOFF_* 模板 + format_handoff_message + 1 单测
4. **C3 handoff parser**：`--with-jury` `--no-strict-jury` flag 解析；不带 flag 时回归用例 H1 守门
5. **C4 handoff orchestrator step 3 (cost-estimate)**：H10 + H14 + H9（cost over budget / 估价打印 / config 错）
6. **C5 handoff orchestrator step 4 (jury actual)**：H2 + H3 + H4 + H5 + H6 + H7 + H8 + H11（11 用例）
7. **C6 handoff orchestrator step 5 (enhance-review)**：H12（accepted + review 失败）
8. **C7 enhance step 失败回归**：H13
9. **C8 autopilot next_action 文案**：2 单测
10. **C9 文档**：docs/cad-jury-config.md / PROGRESS.md / README.md
11. **C10 全量回归 + ruff/mypy 检查 + 北极星 5 gate 体检**
12. **C11 PR 与 review 流程**

每个 C 段一个 commit；C2-C7 内每个 H 用例独立子任务，先 RED 后 GREEN。

---

## 9. 风险与已知 unknown

### 9.1 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| handoff e2e mock 子进程在 Windows / Linux 行为差异 | 测试 flake | 用 jury v1 conftest 已验证的 monkeypatch subprocess.run pattern |
| `jury_review_input.json` 路径 schema 字段名假设 | handoff 找不到文件 | C5 实施前先 grep jury 实际写入字段；不假设字段名 |
| jury cost 估价依赖 `ENHANCEMENT_REPORT.json` 已存在 | 步骤 3 在步骤 1+2 失败时跑不起来 | 实现保证：handoff 严格 step 顺序，step 3 永远在 step 2 ok 后跑 |
| autopilot next_action 文案变更影响下游脚本（如果有）| 回归 | C8 测试用 substring assert 不用 exact match；命令字符串末尾追加而非中间插入 |
| 用户混淆 `--no-strict-jury` 与 jury v1 的 `--debug-output` 等 flag | 文档不清 | docs/cad-jury-config.md 显式表格列出 flag 矩阵 |

### 9.2 已知 unknown

- handoff 当前 description epilog 的实际文本是否需要重写（行数较多）— C9 阶段决定
- jury `--cost-estimate-only` 是否需要支持 `--profile-id` override — 当前假设跟随 jury v1 默认；C1 阶段验证

### 9.3 不接受的风险（Red Team 防线）

- **不允许**：handoff 自己 import jury 模块函数直接调（破坏 invariant 3 子进程隔离）
- **不允许**：handoff 自己拼 stderr 文案（破坏 invariant 5.3 唯一入口）
- **不允许**：autopilot 实跑 jury 或 enhance（破坏 invariant 1 autopilot 行为不变）
- **不允许**：`--cost-estimate-only` 取锁或 freeze sha256（破坏 invariant 6 dry-run 无副作用）

---

## 10. 验收标准（DoD）

完成本 PR 必须满足：

1. **测试**：所有 §6 测试 PASS（H1-H14 + 6 jury 单测 + 2 autopilot 单测 + stderr 模板覆盖测试）
2. **回归**：`tests/` 全量 PASS 不少于 v2.27.0 基线（≥2622 PASS）
3. **mypy strict**：本 PR 改的所有文件保持 strict 不降级
4. **ruff check + format**：clean，无 violations
5. **CI**：Linux + Windows 双平台全绿
6. **coverage**：本 PR 新增代码路径 ≥90% 覆盖
7. **文档**：
   - `docs/cad-jury-config.md` 加新章节
   - `docs/PROGRESS.md` 加 v2.28.0 入口
   - 本 spec commit 在 `docs/superpowers/specs/`
8. **北极星 5 gate 体检**：每个 gate 都通过
   - 零配置：✓ 不引入新配置
   - 稳定可靠：✓ strict 默认 + 工具故障类必阻断
   - 结果准确：✓ jury → review 串联保证 deliver 前有正式契约
   - SW 装即用：✓ 无 SW 涉及
   - 傻瓜式操作：✓ 一条命令跑闭环
9. **PR 流程**：feature/jury-v2-handoff-integration → PR → CI 全绿 → squash merge → tag v2.28.0 + GitHub Release

---

## 11. 后续 (v3 路线，不在本 PR)

承袭 jury v1 spec §11 列表中本 PR 未覆盖项，按簇拆为独立 PR：

- **A2 簇**：`photo3d-jury --summary` 跨 run 聚合 / `--json` 机器友好 / `photo3d-recover` 注册 jury 文件
- **B 簇**：`anthropic_native` kind / `fallback_profile_ids` chain / 月度 quota tracker / 同 key 跨进程 RPM 协调
- **C 簇**：incremental flush（ctrl-c safe）/ `--max-tokens` 自适应 / 中转商中文 quota 文案匹配
- **D 簇**：cost 自动同步 vendor pricing / multi-dim cost model / per-profile cap override
- **E 簇**：NIQE/BRISQUE Layer 1 扩展 / 多视角投票交叉验证
- **F 簇**：schema_version=2 升级（add-only 加 quota_per_month_usd 等）
- **方案 ② 升级**：autopilot 端到端化（gate-only → 真正 orchestrator）

---

## 附录 A：参考文件

| 文件 | 用途 |
|---|---|
| `docs/superpowers/specs/2026-05-08-photo3d-jury-design.md` | jury v1 设计（架构 / 4 层判定 / 异常类层级 / 不变量） |
| `tools/photo3d_jury.py` | jury main 入口（本 PR 加 `--cost-estimate-only` flag） |
| `tools/jury/cost.py` | cost 估价逻辑（dry-run 模式复用） |
| `tools/jury/stderr_messages.py` | 中文文案模板模块（本 PR add-only 加 HANDOFF_* 组） |
| `cad_pipeline.py:cmd_photo3d_handoff` | handoff 主体（本 PR orchestrator 改造） |
| `cad_pipeline.py:cmd_photo3d_autopilot` | autopilot 主体（本 PR 仅文案改动） |
| `tests/jury/conftest.py` | autouse kill switch + dummy fixture key |
| `CLAUDE.md` | 项目工作流约束（superpowers + TDD + 中文输出） |
