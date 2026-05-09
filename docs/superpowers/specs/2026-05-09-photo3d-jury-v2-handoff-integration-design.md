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
| 1.1 | 2026-05-09 | spec 自审发现 2 处事实错误；修：(1) 复用 jury 已有 `--dry-run` flag 替代新加 `--cost-estimate-only`，jury 子模块零改动；(2) `jury_review_input.json` 路径走 subsystem + run_id 约定路径（不读 jury report 字段） |
| 1.2 | 2026-05-09 | 5 角色并行对抗审查（API / Edge / UX / Test / Security）合并 26 CRITICAL + 19 MAJOR：重写 §3.2 (orchestrator 在 `tools/photo3d_handoff.py:run_photo3d_handoff` 不在 cad_pipeline.py)；§3.3 命令归属 + command_return_code 接口扩展；§3.4 invariants 重写（jury blocked 走 status 字段 / dry-run 不取锁 / handoff 自加 .handoff.lock / path traversal 防御 / subprocess argv list / env 不注入 / stderr redact 透传 / PHOTO3D_HANDOFF.json 落盘契约）；§4.1 加 step 0 fail-fast jury config 预检；§4.2 决策表加 unexpected exit code / review_exit clamp；§5.1-5.3 错误矩阵 + redact 链；§6 测试用例 H1 加 golden snapshot / H16-H22 补 path traversal/损坏 review_input/unexpected exit/工具故障类 strict×双向；§9 race window 假设修正；§10 DoD cov source / platform split 显式 cite |
| 1.3 | 2026-05-09 | 第 3 层"代码-spec 对照实测"抓 5 大 BLOCKER（v1.0/v1.1/v1.2 共同的 brainstorm 事实错误，对抗审都没抓到）：(1) `format_stderr_message` 签名是 keyword-only `(*, exit_code, status, error_kind, context)`，分派维度三元组是 `(exit_code, status, error_kind)` 而非 spec 写的 `(exit_code, error_kind, context)`；内部是 if/elif 分支，不是 `_TEMPLATES` 字典；(2) autopilot `next_action` 字段是 `argv` list (+ 可选 `cli` string)，不是 `command` string；且 autopilot ready_for_enhancement 推荐 `enhance` subcommand 而非 `photo3d-handoff` — 整个 autopilot 集成基于错误前提，**v1.3 把 autopilot 文案变更全部移出范围**（推到独立 PR）；(3) `photo3d-handoff` cli 不是固定 5 步串联，是 `next_action.kind` driven dispatcher — jury 应嵌入 `_run_enhancement_followup` 在 enhance-check follow-up 之后；(4) 输出文件名是 `PHOTO3D_HANDOFF.json` 不是 `HANDOFF_RUN.json`；(5) PHOTO3D_HANDOFF.json 现有 `status` 字段命名冲突 — `handoff_status` 字段更名为 `jury_handoff_status` 与现有 `status` 字段共存（不同维度，前者是 jury 验收维度，后者是 handoff 执行阶段维度） |

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

- **范围**：仅 handoff 路径集成 jury（方案 ①）；autopilot v1.3 第 3 层审查发现当前 ready_for_enhancement 推荐 enhance 不推荐 handoff，**集成移出本 PR 范围**，推到 A1.1 独立 PR
- **strict 默认**：jury verdict ≠ accepted → handoff exit≠0；`--no-strict-jury` 反向 opt-out
- **cost 确认**：`--with-jury` 隐含 `--confirm-cost`；handoff 在 jury 跑前 stderr 强制打印估价 + budget 检查；超 budget 仍 exit=3 abort
- **enhance-review 归属**：orchestrator 层（即 handoff 自身）负责，accepted 后调 `enhance-review` subcommand；jury 子模块不动
- **strict/no-strict 边界**：仅 jury **业务质量**类（preview / needs_review）可被 no-strict 降级为警告；jury **工具自身故障**类（lock busy / config 错 / blocked / internal）必须阻断，no-strict 覆盖不了

---

## 2. 范围与非目标

### 2.1 范围（in-scope）

1. `photo3d-handoff` 加 `--with-jury` `--no-strict-jury` 两个 flag（在 `cad_pipeline.py` 子解析器层注册；解析后由 orchestrator 主体接收）
2. **orchestrator 主体改在 `tools/photo3d_handoff.py:run_photo3d_handoff`**：jury hook 嵌入 `_run_enhancement_followup`，在现有 `_execute_enhance_check_followup` 之后新增 `_run_jury_followup`（仅 `with_jury=True` 时触发）；handoff 主体 22 行薄壳保持不变
3. `tools/photo3d_handoff.py:command_return_code` 接口签名 `(report: dict[str, Any]) -> int` **保持不变**；扩展点：当 `report` 含新加 `jury_handoff_status` 字段时按 §4.2 决策表映射到新 exit code 段；现有 `status ∈ {awaiting_confirmation, executed, executed_with_followup, execution_failed, needs_manual_review}` 0/1 映射保持不变
4. **jury 嵌入点**：仅当 next_action.kind == "run_enhancement" + `--with-jury` 启用时触发；其他 next_action.kind（如 `accept_baseline` / `confirm_action_plan`）不影响
5. `photo3d-handoff --with-jury` 在 `_run_enhancement_followup` 内串联 5 步（**step 0 fail-fast jury 预检** → enhance（已由 `_execute_selected_action` 跑过）→ enhance-check（已由 `_execute_enhance_check_followup` 跑过）→ step 3 jury --dry-run 估价 → step 4 jury 实跑 → step 5 enhance-review）
6. **`tools/photo3d_jury.py` 不动**：复用 jury v1 已有的 `--dry-run` flag（已存在于 v2.27.0）；行为详细见 §3.3 表 + invariant 6
7. `PHOTO3D_HANDOFF.json` schema add-only 加六字段（`jury_handoff_status` / `jury_status` / `jury_estimated_usd` / `jury_actual_usd` / `review_status` / `enhance_review_path`）；**字段名钉死**；现有 `status` 字段（值 awaiting_confirmation 等）共存不动
8. 中文 stderr 文案模板集中在 `tools/jury/stderr_messages.py` 现有 `format_stderr_message(*, exit_code, status, error_kind, context)` keyword-only 签名 / 三元组 `(exit_code, status, error_kind)` 分派 / if/elif 内部分支（**复用现有结构而非新增字典或 string-key 分派**）；新增 13 个 `handoff_*` error_kind
9. 文档：`docs/cad-jury-config.md` 加"通过 photo3d-handoff 一条命令跑闭环"章节
10. 全量测试覆盖（单元 + handoff e2e）；含 H16-H22 新增对抗用例（path traversal / 损坏 review_input / unexpected exit code / 工具故障类 strict×no-strict 双向 / config 缺失 fail-fast）
11. **handoff 自身互斥锁**：handoff 在 jury hook 之前（即 enhance-check follow-up 完成后）acquire `<run_dir>/.handoff.lock`（与 jury `.jury.lock` 不同文件、不同生命周期）覆盖 jury hook 全程，防同机并发跑两次 handoff
12. **README 文档示例追加**：README.md 用法示例追加"`photo3d-handoff --with-jury --confirm` 一条命令跑闭环"段（不改默认推荐）

### 2.2 移出范围（pushed to next PR）

- ❌ `cad_pipeline.py:cmd_photo3d_autopilot` 改 next_action 推荐 `--with-jury` —— **v1.3 移出范围**：autopilot 当前 `ready_for_enhancement` 状态推荐的是 `enhance` subcommand（`next_action.kind == "run_enhancement"`，argv = `["python", "cad_pipeline.py", "enhance", ...]`），**不推荐 photo3d-handoff**；`enhance` 不识别 `--with-jury`，加上去会 argparse 错。autopilot 行为重设计需要新增"已跑 enhance 但未跑 handoff"的中间状态分支，超出本 PR 用户体验集成范围；推到 A1.1 独立 PR
- ❌ autopilot 集成相关测试（`tests/test_cad_pipeline_autopilot.py` next_action 含 jury cmd 用例）—— v1.3 同步移出

### 2.3 非目标（out-of-scope；推到独立 PR）

- `photo3d-autopilot --with-jury` 端到端化（autopilot 升级为真正 orchestrator）— 属于 spec §11 方案 ②，本 PR 不做
- `photo3d-jury --summary` 跨 run 聚合视图 — 属于 A2 簇
- `photo3d-jury --json` 机器友好输出 — 属于 A2 簇
- `photo3d-recover` 注册 jury 文件 — 属于 A2 簇
- jury 子模块的 4 层判定逻辑改造（`fallback_profile_ids` chain / `anthropic_native` kind / quota tracker 等）— 属于 B/C/D/E 簇
- jury 自身加 `--auto-review` flag — 已决策由 orchestrator 串联，jury 自身不动

### 2.4 非目标的兼容性承诺

- jury v1 cli 行为**完全不变**（本 PR 不动 jury 子模块任何代码；handoff 复用 v1 已有的 `--dry-run` flag）
- 独立用户跑 `photo3d-jury` 仍按 v1 流程（不会"突然多跑 enhance-review"）
- `PHOTO3D_HANDOFF.json` 现有字段不动；新加字段在不带 `--with-jury` 时**不出现**（不污染回归用户的报告）

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
│  3. jury --dry-run  (复用 v1 已有 flag, 估价 + budget 检查)  │
│     → stderr 打印估价 + budget 检查                 │
│  4. jury  (jury v1 4 层主流程, --confirm-cost 内传) │
│     → 等 PHOTO3D_JURY_REPORT.json 落盘             │
│     → 读 jury_report.status 决策                    │
│  5. enhance-review (仅 accepted 才调)              │
│     → 写 ENHANCEMENT_REVIEW_REPORT.json            │
│  6. 写 PHOTO3D_HANDOFF.json 终态                        │
└─────────────────────────────────────────────────┘

┌─ photo3d-autopilot (本 PR 不改) ──────────────────┐
│  v1.3 第 3 层审查发现 autopilot 当前 ready_for_     │
│  enhancement 状态推荐的是 enhance 命令（不是         │
│  photo3d-handoff），加 --with-jury 不通顺；          │
│  autopilot 集成移出本 PR 范围，推到 A1.1 独立 PR     │
└─────────────────────────────────────────────────┘
```

### 3.2 文件布局

```
cad_pipeline.py                       ← cmd_photo3d_handoff parser add-only 加 --with-jury / --no-strict-jury（~25 行）；
                                       cmd_photo3d_autopilot 不动（v1.3 移出范围）
tools/photo3d_handoff.py              ← run_photo3d_handoff add-only 接受 with_jury / no_strict_jury 关键字参数（~10 行）
                                       _run_enhancement_followup 扩展加 jury hook（~30 行）
                                       新加 _run_jury_followup helper（~150 行）+ _validate_run_id_format helper（~10 行）
                                       + clamp_review_exit helper（~10 行）
                                       command_return_code 扩展（~30 行）
tools/jury/stderr_messages.py          ← format_stderr_message 内 if/elif 分支 add-only 加 13 个 handoff_* error_kind（~80 行；
                                       签名 `(*, exit_code, status="", error_kind="", context)` 不动）
docs/cad-jury-config.md                ← 新增"handoff 一条闭环"章节（~40 行）
docs/PROGRESS.md                       ← 加 v2.28.0 入口（~5 行）
README.md                              ← 用法示例追加 --with-jury 推荐（~10 行）
tests/test_photo3d_handoff_with_jury.py（新文件，~600 行；含 H1-H23 共 27 用例 含 H7/8/9/11 双向）
tests/jury/test_stderr_messages.py     ← 加 handoff_* error_kind 模板覆盖测试（~50 行）

注：
- `tools/photo3d_jury.py` 与其他 jury 子模块文件 0 改动；handoff 复用 jury v1 已有的 `--dry-run` flag
- `tools/photo3d_autopilot.py` 不动（v1.3 第 3 层审查发现 autopilot ready_for_enhancement 推荐 enhance 不推荐 handoff，集成推到独立 PR）
- `tests/test_cad_pipeline_autopilot.py` 不改（v1.3 同步移出）
```

### 3.3 模块契约

| 模块 / 函数 | 单一职责 | 输入 | 输出 | 不做 |
|---|---|---|---|---|
| `cad_pipeline.py:cmd_photo3d_handoff`（薄壳，仅加 parser 注册） | argparse 子解析器加 `--with-jury` `--no-strict-jury`；args 透传 `tools/photo3d_handoff.py:run_photo3d_handoff` | argv | run_photo3d_handoff 返回值 | 不实现 orchestrator |
| `tools/photo3d_handoff.py:run_photo3d_handoff`（主改动） | orchestrator：6 步串联（含 step 0 fail-fast）、读 jury report status 字段判定 / 透传 jury exit、决定 strict 行为、写 PHOTO3D_HANDOFF.json 终态、acquire `.handoff.lock` | args + project_root | report dict | 不实现 jury 业务逻辑；不动 enhance/check 已有逻辑；不直接 import jury 模块函数 |
| `tools/photo3d_handoff.py:command_return_code`（扩展） | 把 report 终态映射到 exit code；现有签名 `(report: dict[str, Any]) -> int` 不变；扩展点：当 `report` 含新加 `jury_handoff_status` 字段时按 §4.2 决策表映射；现有 `status ∈ {awaiting_confirmation, executed, executed_with_followup, execution_failed, needs_manual_review}` 0/1 映射保持不变 | report dict（含新 jury_status / jury_handoff_status 字段） | exit code ∈ {0, 1, 2, 3, 4, 10, 11, 12, 13, 20, 21, 22, 23, 24, 25, 99} | 不做副作用 |
| `tools/photo3d_jury.py`（不动） | jury v1 已有 `--dry-run` flag（v2.27.0 落地）：跑 Layer 0（不取 `.jury.lock`）+ Layer 1 deterministic_gate + cost gate 后 print + return；**Layer 2 才 acquire `.jury.lock`** | argv | exit code（0 = 估价 ok 或 jury 内部 fail soft / 1 = layer0 blocking / 2 = config 错 / 3 = over budget；其他 exit 由 jury v1 已有路径决定） | 本 PR 不改 jury 子模块任何代码 |
| `tools/jury/stderr_messages.py:format_stderr_message`（add-only 扩展） | 复用现有 keyword-only 签名 `(*, exit_code: int, status: str = "", error_kind: str = "", context: dict[str, Any]) -> str`；分派维度三元组是 **(exit_code, status, error_kind)**；内部是 if/elif 分支（**不是 _TEMPLATES 字典**）；本 PR 在该函数加 if 分支处理 `error_kind ∈ {handoff_jury_preview, handoff_jury_needs_review, handoff_jury_blocked, handoff_jury_lock_busy, handoff_jury_internal_error, handoff_jury_config_error, handoff_jury_cost_over_budget, handoff_review_failed, handoff_review_input_missing, handoff_review_input_corrupt, handoff_unexpected_jury_exit, handoff_handoff_lock_busy, handoff_jury_preflight_config_missing}`（13 个新 error_kind） | exit_code + status + error_kind + context dict (keyword-only) | 单字符串（无 `{xxx}` 残留；输出前由调用方过 `redact.py:redact_traceback_str`） | 不做 IO；纯 string format；**不引入新签名 / 不创建并行的 string-key 分派函数** |
| `cmd_photo3d_autopilot`（**v1.3 不动**） | autopilot 行为完全保持现状；本 PR 不改 | n/a | n/a | n/a |

### 3.4 不变量

1. **autopilot 完全不动**（v1.3 修正 v1.2 错判）：本 PR 不改 `tools/photo3d_autopilot.py` 任何代码；不改 next_action 字段；autopilot ready_for_enhancement 状态推荐 enhance 命令（next_action.argv = `["python", "cad_pipeline.py", "enhance", ...]`）的现状保持。autopilot 集成推到 A1.1 独立 PR（需先重设计 autopilot 增加"已 enhance 未 handoff"的中间状态）
2. **jury 子模块边界不动**：`tools/jury/{config,cost,llm_client,verdict,redact,deterministic_gate,input_evidence_binding}.py` 与 `tools/photo3d_jury.py` 全部 0 改动；只在 `tools/jury/stderr_messages.py` 的 `format_stderr_message` 函数 add-only 扩展 `error_kind` 枚举支持 `handoff_*` 前缀（不引入并行的 string-key 分派接口）
3. **handoff 调子进程方式**：必须用 `subprocess.run([sys.executable, str(cad_pipeline_py_path), subcommand, *args], shell=False, ...)` argv list 形式（**禁止字符串拼接 + shell=True**，防 Windows cmd `&` `|` `^` 等元字符注入）；**禁止**直接 import jury 模块函数（避免 cli 副作用泄漏）；**子进程 env 不注入任何凭据**：`subprocess.run(env=os.environ.copy())` 即可，handoff 自己不读 / 不传 jury api_key / 不复制任何 `OPENAI_API_KEY` 等敏感环境变量
4. **`PHOTO3D_HANDOFF.json` 落盘契约**：
   - 路径 = `<project_root>/cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>/PHOTO3D_HANDOFF.json`（active_run_id 取自 `ARTIFACT_INDEX.json` step 0 时刻 freeze；不重读）
   - 写入走 `tools/contract_io.py:write_json_atomic` + `tools/path_policy.py:assert_within_project(path, project_root, "HANDOFF_RUN")` 三参数全填（继承 jury v1 invariant 4）
   - schema add-only：现有字段集严格保持；新加字段（`jury_status` / `jury_estimated_usd` / `jury_actual_usd` / `review_status` / `enhance_review_path`）**仅在** `--with-jury` 启用时出现；不带 flag 时 H1 golden snapshot 守门
   - **永远写**：handoff 主体用 `try/finally` 包裹 step 0-6 全程，任意 step 异常退出（含 KeyError / OSError / SIGKILL 信号 handler 可拦截路径）必落盘 partial state（缺失字段为 null，已完成字段保留）
5. **strict/no-strict 边界硬约束**：
   - 业务质量类（jury report `status ∈ {preview, needs_review}`）：strict → exit=10/11 abort；no-strict → exit=0 + warning
   - 工具故障类（jury report `status == "blocked"` / handoff 检测的 `JuryLockBusy` / `JuryConfigError` / `JuryInternalError` / unexpected jury exit / handoff 自身 `.handoff.lock` busy）：**永远阻断**，no-strict 不能覆盖
   - 工具故障类的"永远阻断"必须 H7/H8/H9/H11 + 对应 `--no-strict-jury` 变体（H7b/H8b/H9b/H11b）双向用例守门
6. **dry-run 行为校正（v1.2 修正 v1.1 错判）**：jury v1 现有 `--dry-run` 实际行为（grep 实证 `tools/photo3d_jury.py` 行 95/236/248）：跑 Layer 0 input_evidence_binding（**不取 `.jury.lock`**——`.jury.lock` 在 Layer 2 取，dry-run 在 cost gate 之前 return 不触达）+ Layer 1 deterministic_gate + cost gate 后 stdout `[dry-run] estimated=X.XX USD, allowed=Y` + return 0/3；**dry-run 不写 `PHOTO3D_JURY_REPORT.json`**；handoff step 3 与 step 4 之间没有"自己锁释放后被抢"的 race（dry-run 根本不取锁）；**handoff 自身 `.handoff.lock` 在 step 0 之前 acquire** 覆盖 step 0-6 全程，防同机并发跑两次 handoff
7. **jury return 0 但 status="blocked" 判定**：jury 实跑遇 freeze drift 时**写 `PHOTO3D_JURY_REPORT.json` `status="blocked"` 后 return 0**（非 exit≠0）；handoff 必须**先读 PHOTO3D_JURY_REPORT.json `status` 字段** 再决定 jury_status，**不能仅靠 exit code 判定**；exit code 与 status 字段的判定优先级：(a) exit code ∈ {2, 4, 99}（jury 自己已 fail-fast 写 stderr）→ 直接透传不读 report；(b) exit code ∈ {0, 1, 3} → 读 report `status` 字段；(c) exit code 为其他值（130 / 137 / SIGTERM / 等 unexpected）→ 归 `unexpected_jury_exit`，exit=25 阻断
8. **estimated_usd 单源打印**：jury 实跑会打印估价；handoff dry-run 也会触发 jury 自己打印（jury stdout `[dry-run] ...`）；handoff **不**自行重复打印估价，**只**在 dry-run 失败（exit=3 budget 超）时输出中文人话提示。用户最多看到 jury 自打的英文一行 + handoff 中文一行（含错误处置建议），不重复
9. **enhance-review 失败不污染 jury 报告**：`PHOTO3D_JURY_REPORT.json` 保持 jury 自己写完时的内容；handoff 把 review 失败记到 `PHOTO3D_HANDOFF.json` 自己的字段（review_status / enhance_review_path）
10. **jury_review_input.json 路径走约定 + path traversal 防御**：
    - handoff 通过 `subsystem`（自身 args）+ jury report 的 `run_id` 字段构造路径
    - **run_id 字段格式校验**（防 path traversal）：必须 `re.fullmatch(r"^[A-Za-z0-9_\-]+$", run_id)`；不匹配 → exit=13 `handoff_review_input_missing` 子类目 `run_id_format`
    - 路径 = `<project_root>/cad/<subsystem>/.cad-spec-gen/runs/<run_id>/jury_review_input.json`
    - 构造后立即 `tools/path_policy.py:assert_within_project(path, project_root, "jury_review_input")` 三参数全填（防 subsystem 含 `..` 越界）
    - 再 `Path.exists()` 校验 + `Path.is_file()` 校验
    - **禁止扫目录猜文件**（北极星硬约束）
    - 缺路径报 `handoff_review_input_missing`，文件损坏（非合法 JSON）报 `handoff_review_input_corrupt` 子类目；测试用例 H15 / H16 / H17 守门
11. **subprocess 调用契约**：
    - 必须 `subprocess.run([list], shell=False, capture_output=True, text=True, timeout=...)`
    - **subsystem / run_id / profile_id / budget 等用户可控值**必须作为 argv list 元素，**不允许** f-string / `+` / `%s` 拼成单字符串
    - 测试用例必须 assert `monkeypatch.setattr("subprocess.run", fake)` 接收的第一个位置参数是 `list[str]` 且 `shell` 关键字 ∉ kwargs 或 `shell=False`
12. **stderr 透传 redact 链**：
    - handoff 透传 jury / enhance / enhance-review 子进程 stderr 前必走 `tools/jury/redact.py:redact_traceback_str` + `redact_body`（jury v1 invariant 5 兜底沿用）
    - handoff 自身 stderr 文案常量必须固定，禁止动态 `f"... {api_key} ..."` 模板（即使变量名不叫 api_key 也禁）
    - HANDOFF stderr 模板**仅显示** profile_id（不显示 model / base_url / api_key），防 model 名意外含敏感前缀
13. **encoding 强制（沿用 jury v1 invariant 12）**：handoff 所有文件 IO 必传 `encoding="utf-8"`；`json.dumps(..., ensure_ascii=False, indent=2)` 中文不转义
14. **`.handoff.lock` 生命周期**：
    - 路径 = `<project_root>/cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>/.handoff.lock`
    - 用 `tools/_file_lock.py`（jury v1 设计沿用；若 v1 没抽出则本 PR 不抽，handoff 直接复用 jury `.jury.lock` 同机制写另一文件）
    - try/finally 释放；stale lock 自动清理：mtime > 30 min 或 PID 不在系统 → 下次 cli 自动覆盖 + stderr 警告
    - acquire 失败 → exit=24 `handoff_handoff_lock_busy`
15. **add-only schema 兼容性宪章（沿用 jury v1 invariant 14）**：本 PR add-only 加字段不需升 `PHOTO3D_HANDOFF.json` `schema_version`；只有删字段、改字段语义、改字段类型才需升

---

## 4. 数据流

### 4.1 完整流程

**关键修正（v1.3）**：handoff 不是"5 步固定串联 cli"，是 **next_action.kind driven dispatcher** + follow-up 嵌入模型。jury hook 仅在 `next_action.kind == "run_enhancement"` 且 `--with-jury` 启用时触发。

```
photo3d-handoff --confirm --with-jury [--no-strict-jury]
        │
        ▼ (现有流程保持不变)
读 PHOTO3D_RUN.json / PHOTO3D_AUTOPILOT.json 的 next_action
        │
        ▼
_classify_next_action → selected_action（kind ∈ {run_enhancement, accept_baseline, confirm_action_plan, ...}）
        │
        ▼
[现有逻辑] 若 kind != run_enhancement：按既有路径处理；--with-jury 不影响（H-NJ 用例守门）
        │
        ▼ kind == "run_enhancement" + --confirm
_execute_selected_action 跑 enhance subprocess（enhance 失败 → status="execution_failed" 现有路径）
        │ enhance returncode == 0
        ▼
_run_enhancement_followup 入口
        │
        ▼
[现有] _execute_enhance_check_followup 跑 enhance-check（失败 → 透传现有路径）
        │ ok
        ▼
————————— 以下是本 PR jury hook 嵌入点 —————————

step J0 acquire <run_dir>/.handoff.lock（防同机并发；with_jury=False 时跳过此 step）
   ──acquire 失败──▶ jury_handoff_status="handoff_lock_busy" exit=24

step J0.5 fail-fast jury 配置预检
   调 `python cad_pipeline.py jury --dry-run --subsystem <s> --profile-id <p>`（jury 自身会走 config 加载 + Layer 0）
   ──jury return ∈ {1, 2}（layer0/config 错）──▶ jury_handoff_status="preflight_config_missing" exit=2
   ──jury return == 0──▶ continue (估价已得，但 jury 此时只到 Layer 0 + cost gate 之前；为避免重跑 dry-run 浪费 IO，
                          v1.3 决策：J0.5 与 step 3 dry-run 合并为同一次调用，本调用既做预检又做估价)

step 3 jury --dry-run（实际就是 J0.5 的同一次调用）
   stdout: "[dry-run] estimated=0.04 USD, allowed=True"  (jury 自打)
   ──jury return 3 (cost over budget)──▶ jury_handoff_status="cost_over_budget" exit=3
                                        + jury_estimated_usd 字段
                                        + stderr 中文提示
   ──jury return ∈ {1, 2}──▶ 透传 jury exit；jury_handoff_status="config_error" 或 "blocked"
   ──jury return ∈ {130, 137, 其他}──▶ jury_handoff_status="unexpected_jury_exit" exit=25
        ▼
step 4 jury 实跑（jury return 0 后才走；handoff 显式传 `--confirm-cost`；jury Layer 2 取 `.jury.lock`）
   等 PHOTO3D_JURY_REPORT.json 落盘
   优先级判定（invariant 7）：
   (a) jury exit ∈ {2, 4, 99}                  → 透传 exit；不读 report
   (b) jury exit ∈ {0, 1, 3}                   → 读 PHOTO3D_JURY_REPORT.json 的 status 字段
   (c) jury exit ∈ {130, 137, 其他 unexpected} → exit=25 handoff_unexpected_jury_exit
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ jury exit │ jury status (若读)  │ strict           │ no-strict          │
   ├─────────────────────────────────────────────────────────────────────────┤
   │ 0         │ accepted            │ → step 5         │ → step 5           │
   │ 0         │ preview             │ → exit=10        │ → warning + exit=0 │
   │ 0         │ needs_review        │ → exit=11        │ → warning + exit=0 │
   │ 0         │ blocked (sha drift) │ → exit=12（**no-strict 不覆盖**）   │
   │ 1         │ (layer0 blocking)   │ → exit=12（同 blocked 类目）        │
   │ 2         │ (config 错)         │ → exit=2 透传（**永远阻断**）       │
   │ 3         │ (cost gate)         │ → exit=3 透传 不应该到 step 4     │
   │ 4         │ (lock busy)         │ → exit=4 透传（**永远阻断**）       │
   │ 99        │ (internal)          │ → exit=99 透传（**永远阻断**）      │
   │ 其他       │ -                   │ → exit=25 unexpected_jury_exit     │
   └─────────────────────────────────────────────────────────────────────────┘
        │ accepted（jury_status:"accepted"）
        ▼
step 5 enhance-review subprocess
   路径构造（invariant 10）：
     校验 jury report run_id 字段格式 `^[A-Za-z0-9_\-]+$`
     review_input_path = <project_root>/cad/<subsystem>/.cad-spec-gen/runs/<run_id>/jury_review_input.json
     assert_within_project(review_input_path, project_root, "jury_review_input")
     校验 .exists() + .is_file()
     校验 json.loads(read_text(encoding="utf-8")) 不抛
   ──run_id 格式不合法──▶ exit=13 handoff_review_input_missing("run_id_format")
   ──path 不存在──▶ exit=13 handoff_review_input_missing("not_found")
   ──path 在 project root 之外──▶ exit=13 handoff_review_input_missing("path_traversal")
   ──读取 / JSON 解析失败──▶ exit=23 handoff_review_input_corrupt
   ──enhance-review 子进程 fail──▶ exit=clamp_review_exit(review_exit)
                                  + PHOTO3D_HANDOFF.json{review_status:"failed", review_raw_exit:N}
        │ ok（review_status:"ok"）
        ▼
step 6 写 PHOTO3D_HANDOFF.json 终态（add-only 字段，与现有 status 字段共存）
   现有字段（保持不变）：schema_version / generated_at / run_id / subsystem / source / source_report
                       / confirmed / status / ordinary_user_message / selected_action
                       / manual_action / executed_action / followup_action
                       / post_handoff_photo3d_run / artifacts
   新加字段（仅 --with-jury 启用时出现）：
   {
     jury_handoff_status: "accepted" | "preview_warning" | "review_failed" | ... ,
     jury_status: str,                        # jury 报告的 status，或 handoff 自己的工具故障类目
     jury_estimated_usd: float,
     jury_actual_usd: float | null,           # 字段名钉死，不带 _or_null 后缀
     review_status: str,                      # ok | failed | input_missing | input_corrupt
     enhance_review_path: str | null,
     jury_raw_exit: int | null,               # 仅 jury_status="unexpected_exit" 时非 null
     review_raw_exit: int | null,             # review 失败时记原始 exit
   }
        │
        ▼
step 7 release `.handoff.lock`（finally 块；whether or not with_jury，with_jury=False 时本 step 之前 step 不取锁也无须释放）

clamp_review_exit:
  review_exit ∈ {0}      → 0
  review_exit ∈ {1}      → 20  (handoff_review_failed)
  review_exit ∈ {2}      → 21  (clamp 防与 handoff exit=2 撞码)
  review_exit ∈ {3}      → 22
  review_exit ∈ 其他      → 23  (透传含义模糊归 corrupt 类目；仍记 review_raw_exit)
```

### 4.2 jury 实跑后 jury_handoff_status 决策表

注：`jury_handoff_status` 是 PHOTO3D_HANDOFF.json 新增字段（仅 `--with-jury` 启用时出现），与现有 `status` 字段（值 awaiting_confirmation/executed/executed_with_followup/execution_failed/needs_manual_review，handoff 执行阶段维度）**共存不冲突**。

| jury_status | strict | review_status | jury_handoff_status | exit |
|---|---|---|---|---|
| accepted | * | ok | accepted | 0 |
| accepted | * | failed | review_failed | clamp_review_exit(review_raw) |
| accepted | * | input_missing | review_input_missing | 13 |
| accepted | * | input_corrupt | review_input_corrupt | 23 |
| preview | strict | n/a (skip) | preview_blocked_by_strict | 10 |
| preview | no-strict | n/a (skip) | preview_warning | 0 |
| needs_review | strict | n/a (skip) | needs_review_blocked_by_strict | 11 |
| needs_review | no-strict | n/a (skip) | needs_review_warning | 0 |
| blocked | * | n/a (skip) | jury_blocked | 12 |
| cost_over_budget | * | n/a (skip) | cost_over_budget | 3 |
| config_error | * | n/a (skip) | config_error | 2 |
| lock_busy | * | n/a (skip) | lock_busy | 4 |
| internal_error | * | n/a (skip) | internal_error | 99 |
| unexpected_exit | * | n/a (skip) | unexpected_jury_exit | 25 |
| (handoff 自身) | * | n/a (skip) | handoff_lock_busy | 24 |
| (handoff preflight) | * | n/a (skip) | preflight_config_missing | 2 |

**jury_handoff_status 字段值钉死**：上表 `jury_handoff_status` 列字符串值是契约；测试 H1-H23 必须 assert PHOTO3D_HANDOFF.json 写出的 `jury_handoff_status` 字符串与表完全一致（防拼写错如 `config_err` vs `config_error`）。

### 4.3 不带 --with-jury 的回归路径

- handoff 行为完全等同 v2.27.0：跑 enhance + enhance-check follow-up，写 `PHOTO3D_HANDOFF.json` 不含 jury 字段
- 测试用例必须显式 assert 不带 `--with-jury` 时 `PHOTO3D_HANDOFF.json` 字段集与现有 schema 完全一致

---

## 5. 错误处理

### 5.1 异常分类与 exit code

| 类目 | exit | strict 可降级 | stderr error_kind |
|---|---|---|---|
| enhance 自身失败 | 透传 enhance | n/a | (沿用现有) |
| enhance-check 失败 | 透传 check | n/a | (沿用现有) |
| handoff preflight: jury config 缺失 | 2 | ✗ | `handoff_jury_preflight_config_missing` |
| handoff 自身 lock busy | 24 | ✗ | `handoff_handoff_lock_busy` |
| jury config 错 | 2 | ✗ | `handoff_jury_config_error` |
| jury cost 超 budget | 3 | ✗ | `handoff_jury_cost_over_budget` |
| jury lock busy | 4 | ✗ | `handoff_jury_lock_busy` |
| jury preview | 10 / 0 | ✓ | `handoff_jury_preview` (context["mode"]="strict"/"warning") |
| jury needs_review | 11 / 0 | ✓ | `handoff_jury_needs_review` (context["mode"]="strict"/"warning") |
| jury blocked | 12 | ✗ | `handoff_jury_blocked` |
| jury internal | 99 | ✗ | `handoff_jury_internal_error` |
| jury unexpected exit (130/137/其他) | 25 | ✗ | `handoff_unexpected_jury_exit` (context["raw_exit"]=N) |
| enhance-review 失败（review_raw=1） | 20 | n/a | `handoff_review_failed` |
| enhance-review 失败（review_raw=2） | 21 | n/a | `handoff_review_failed` |
| enhance-review 失败（review_raw=3） | 22 | n/a | `handoff_review_failed` |
| enhance-review 子进程其他异常 | 23 | n/a | `handoff_review_input_corrupt` |
| review_input 路径缺失（含 path traversal） | 13 | n/a | `handoff_review_input_missing` (context["reason"]∈{"not_found", "run_id_format", "path_traversal"}) |

**POSIX 兼容性脚注**：handoff exit code 段（10/11/12/13/20/21/22/23/24/25）属于业务自定义码，不与 POSIX 保留段（126 / 127 / 128+N 信号）冲突；CI 配置 retry-on-exit 时需显式排除 10-25 段，否则会误重试用户操作错误。

### 5.2 stderr 模板示例（中文人话；外行用户可操作）

模板在 `tools/jury/stderr_messages.py:format_stderr_message` 函数内 if/elif 分支 add-only 加入（**不是 `_TEMPLATES` 字典 — 现有实现是 if/elif 分支**）。新加 13 个 `error_kind` 处理分支，按 `(exit_code, error_kind)` 选模板字符串后 `.format(**context)` 填充：

```python
# (exit_code, "handoff_jury_preview", mode="strict")
"jury 判定 preview（5 项语义检查中 {failed_n} 项 false 或 photoreal_score={score} 低于 min_photoreal_score={min_score}）。\n"
"  jury 报告：{report_path}\n"
"  ① 改善：检查 enhance 输出是否清晰；调整 enhance config；或换 provider preset\n"
"  ② 跳过：加 --no-strict-jury 仅警告（但结果不会进入 deliver；需手动跑 enhance-review）"

# (exit_code, "handoff_jury_blocked")
"jury 检测到输入证据漂移（active_run_id 或 sha256 不一致）。\n"
"  这是工具自身故障，--no-strict-jury 也不会跳过。\n"
"  ① 重跑：cad_pipeline.py photo3d-handoff --with-jury --confirm 重新走一遍\n"
"  ② 检查：是否其他工具/脚本同时改 ARTIFACT_INDEX.json（CI 多 worker / 双窗口）"

# (exit_code, "handoff_jury_lock_busy")
"jury 被另一 photo3d-jury 进程持锁。\n"
"  ① 等待：其他 jury 进程结束（一次跑 ~30s）；30 分钟无响应自动清理\n"
"  ② 主动放弃：本次 handoff 退出；不会破坏数据；可稍后重跑"
# 注：不要求外行用户用 Task Manager / ps 查 PID；超 30 分钟自动清理已托底

# (exit_code, "handoff_handoff_lock_busy")
"另一个 photo3d-handoff 进程正在跑同 subsystem（防止数据冲突）。\n"
"  请等当前进程结束（约 5-15 分钟，含 enhance + jury + review）"

# (exit_code, "handoff_jury_preflight_config_missing")
"jury 配置缺失或格式错（路径：{config_path}）。\n"
"  下一步：参见 docs/cad-jury-config.md 配置 jury_config.json；本次 handoff 已立即退出，未跑 enhance（不浪费 LLM 额度）"

# (exit_code, "handoff_review_input_missing")
"jury 判定 accepted 但 enhance-review 输入缺失（{reason}）。\n"
"  原因 {reason}：not_found = 文件不存在；run_id_format = jury 写的 run_id 含非法字符；path_traversal = 路径越界\n"
"  这是 bug，请提 issue 并附 PHOTO3D_JURY_REPORT.json"

# (exit_code, "handoff_unexpected_jury_exit")
"jury 进程异常退出（exit code = {raw_exit}）。\n"
"  常见原因：被 Ctrl-C 打断（130） / OOM kill（137） / 系统 SIGTERM\n"
"  ① 重跑 handoff；② 若反复出现，看 jury stderr 详细输出（已脱敏）"
```

**外行用户优先**：所有模板必须给"下一步动作"清单，禁止只描述错误现象不给出路。

### 5.3 集中处理位置 + redact 链

- **唯一入口**：`tools/jury/stderr_messages.py:format_stderr_message(*, exit_code, status, error_kind, context)`（**keyword-only 签名**；沿用 jury v1 三元组 `(exit_code, status, error_kind)` 分派接口；本 PR 不引入并行函数）
- **handoff 调用方**：`tools/photo3d_handoff.py:run_photo3d_handoff` 在每个失败分支唯一通过 `format_stderr_message(exit_code=N, status=..., error_kind="handoff_...", context={...})` 取字符串后写 stderr；从 `tools/jury/redact.py:redact_traceback_str` 兜底过一次再写
- **子进程 stderr 透传**：handoff 不直接 `print(subprocess.stderr.decode())`；必须先 `redact_traceback_str(subprocess.stderr)` 后再 stderr 写
- **stderr 模板内容限制**：context 字典的 value 仅允许 profile_id / run_id / 文件路径（已 path_policy 校验过的项目内路径）/ 数值（cost / view 数）/ 整数 exit code；**禁止** model 名 / base_url / 任意 api_key prefix / 任何环境变量值
- **禁止**：handoff 自己拼字符串、handoff 自己保留 string-key 文案常量、并行 string-key 分派函数；所有 `handoff_*` error_kind 模板都必须落在 `format_stderr_message` 函数内 if/elif 分支中（**不是** `_TEMPLATES` 字典 — 该字典在 v2.27.0 实现里不存在）

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
| `tests/jury/test_stderr_messages.py` | `test_handoff_error_kinds_no_unfilled_placeholders` | 13 个 `handoff_*` error_kind 在 `format_stderr_message(exit_code=..., error_kind=...)` 输出无 `{xxx}` 残留（用合法 context fixture 调每个 error_kind） |
| `tests/jury/test_stderr_messages.py` | `test_handoff_error_kinds_dispatch_complete` | 用每个 `handoff_*` error_kind 调 `format_stderr_message`，输出非空且不命中 fallback `f"✗ ...（{error_kind}）..."` 兜底分支 |
| `tests/jury/test_stderr_messages.py` | `test_handoff_templates_no_secret_leakage` | grep `format_stderr_message` 函数源码（`inspect.getsource`），不含 `api_key` `base_url` `model` 字面量字符串作为模板 placeholder |
| `tests/test_photo3d_handoff_with_jury.py` | `test_clamp_review_exit_mapping` | clamp_review_exit(0)→0, (1)→20, (2)→21, (3)→22, (其他)→23 |
| `tests/test_photo3d_handoff_with_jury.py` | `test_validate_run_id_format_rejects_traversal` | `validate_run_id("../etc/passwd")` 返 False；`validate_run_id("20260509-123456")` 返 True |

注：jury `--dry-run` flag 已存在 v2.27.0，本 PR plan task 0 必须先 grep 确认现有单测路径与覆盖范围（不假设）。

### 6.3 handoff 集成测试

新文件：`tests/test_photo3d_handoff_with_jury.py`（~600 行）

**mock 策略（钉死防假绿）**：
- patch target 必须是 `tools.photo3d_handoff.subprocess.run`（不是 `subprocess.run` 全局）
- fake 函数签名：`def fake_run(argv, *, shell=False, capture_output=True, text=True, timeout=None, env=None, **kw) -> CompletedProcess`
- **每个用例必须 assert 至少一次**：`argv` 是 `list[str]` 且第 0 元素 == `sys.executable` 且第 1 元素以 "cad_pipeline.py" 结尾
- **每个用例必须 assert**：`shell` 关键字未传入 / 或为 False
- **每个用例必须 assert**：`env` 不含 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 等敏感键（继承的不算 handoff 主动注入）
- fixture `fake_enhancement_report` 在 tmp_path 写 `ENHANCEMENT_REPORT.json` 含 `views: [{}, {}, {}, {}]`（n_views=4）；H14 估价测试依赖
- fixture `fake_jury_report_<status>` 在 tmp_path 的 jury run_dir 写 `PHOTO3D_JURY_REPORT.json` 各种 status；H2-H7 用

| 用例编号 | 场景 | 预期 | 守门 invariant |
|---|---|---|---|
| H1 | 不带 --with-jury（回归 + golden snapshot） | exit=0/1（按现有 status 映射）+ PHOTO3D_HANDOFF.json 字段 keyset 与 v2.27.0 基线 snapshot 完全一致（fixture 存 `tests/fixtures/photo3d_handoff_v2_27_0.json`）；不出现 `jury_*` 字段 | inv 4 add-only |
| H1b | --with-jury 但 next_action.kind == "accept_baseline" | jury hook 不触发；exit + 字段集与 v2.27.0 现有路径完全一致；不出现 `jury_*` 字段 | inv 1（jury 嵌入点限制） |
| H1c | --with-jury 但 confirm=False（preview 模式 awaiting_confirmation） | jury hook 不触发；exit + 字段集与现有 awaiting_confirmation 路径一致；不出现 `jury_*` 字段 | inv 1 |
| H2 | --with-jury jury accepted + review ok (jury exit=0 status="accepted") | exit=0 + jury_handoff_status="accepted" + jury_actual_usd 字段是 float | inv 4/7 |
| H3 | --with-jury jury preview + strict | exit=10 + jury_handoff_status="preview_blocked_by_strict" + 不调 review + stderr 含 handoff_jury_preview 模板渲染文本 | inv 5 业务降级 |
| H4 | --with-jury --no-strict-jury jury preview | exit=0 + jury_handoff_status="preview_warning" + 不调 review | inv 5 业务降级 |
| H5 | --with-jury jury needs_review + strict | exit=11 + 不调 review | inv 5 |
| H6 | --with-jury --no-strict-jury jury needs_review | exit=0 + warning + 不调 review | inv 5 |
| H7a | --with-jury jury blocked + strict | exit=12 + jury_handoff_status="jury_blocked" + 不调 review | inv 5 工具故障 |
| H7b | --with-jury **--no-strict-jury** jury blocked | exit=12（**no-strict 不覆盖**）+ 不调 review | inv 5 双向 |
| H8a | --with-jury jury lock busy (jury exit=4) | exit=4 透传 + 不调 review | inv 5 |
| H8b | --with-jury **--no-strict-jury** jury lock busy | exit=4 透传（**no-strict 不覆盖**） | inv 5 双向 |
| H9a | --with-jury jury config 错 (jury exit=2) | exit=2 透传 + 不调 review | inv 5 |
| H9b | --with-jury **--no-strict-jury** jury config 错 | exit=2 透传（**no-strict 不覆盖**） | inv 5 双向 |
| H10 | --with-jury jury cost over budget (dry-run jury exit=3) | exit=3 + jury_handoff_status="cost_over_budget" + jury_estimated_usd 字段 + 不调 review；**enhance 已跑过**（dry-run 在 step 3 不在 step 0） | inv 6 / inv 8 |
| H11a | --with-jury jury internal (exit=99) | exit=99 透传 + 不调 review | inv 5 |
| H11b | --with-jury **--no-strict-jury** jury internal | exit=99 透传（**no-strict 不覆盖**） | inv 5 双向 |
| H12 | --with-jury jury accepted + review 失败 (review exit=1) | exit=20 (clamp) + jury_handoff_status="review_failed" + review_raw_exit=1 字段 | inv 8 review_exit clamp |
| H13 | enhance step 失败 (enhance exit=1) | exit=1 透传 + 不调 jury（PHOTO3D_HANDOFF.json 仅 enhance_status="failed"） | inv 4 |
| H14 | --with-jury jury exit=3 时 stderr 含中文估价文案 | H10 同测；stderr 含 "jury 预估 X.XX USD" + budget 字符串 | inv 8 |
| H15 | --with-jury accepted + review_input 约定路径不存在 | exit=13 + jury_handoff_status="review_input_missing" + reason="not_found" | inv 10 |
| H16 | --with-jury accepted + jury report run_id="../etc/passwd" | exit=13 + reason="run_id_format" + 不调 review | inv 10 path traversal |
| H17 | --with-jury accepted + jury_review_input.json 是损坏 JSON | exit=23 + jury_handoff_status="review_input_corrupt" + 不调 review | inv 10 |
| H18 | --with-jury jury 进程 SIGINT (exit=130) | exit=25 + jury_handoff_status="unexpected_jury_exit" + jury_raw_exit=130 + 不调 review | inv 7 |
| H19 | --with-jury jury 进程 OOM (exit=137) | exit=25 + jury_raw_exit=137 | inv 7 |
| H20 | --with-jury fail-fast jury config 缺失 | exit=2 + jury_handoff_status="preflight_config_missing" + **不调 enhance**（防 enhance 白花钱） | step 0.5 |
| H21 | --with-jury 同 subsystem 已有 handoff 在跑 (`.handoff.lock` busy) | exit=24 + jury_handoff_status="handoff_lock_busy" + 不调 enhance | inv 14 |
| H22 | --with-jury subprocess argv 形式 | fake_run.call_args_list 每次第 0 位置参数 isinstance(list) + shell ∉ kwargs + env 不主动注入敏感键 | inv 3/11 |
| H23 | --with-jury crash mid-step（mock enhance 抛 OSError） | PHOTO3D_HANDOFF.json 仍写出（finally 块），enhance_status="crashed" | inv 4 永远写 |

### 6.4 autopilot 测试（v1.3 移出本 PR）

autopilot 集成 v1.3 移出范围（§2.2）；本 PR 不加 autopilot 测试用例；推到 A1.1 独立 PR。

仅保留**回归守门**（在现有 `tests/test_cad_pipeline_autopilot.py` 内本 PR 不动；CI 全量跑确认 autopilot 行为未受 handoff 改动牵连）。

### 6.5 不写的测试（YAGNI 边界）

- 不测真实 LLM 调用：沿用 jury v1 conftest autouse kill switch（`tests/jury/conftest.py`）
- 不测真实 enhance/render：handoff 测试全 mock 子进程
- 不测 jury v1 已覆盖的 4 层判定逻辑：本 PR 不动那部分

### 6.6 CI 矩阵

- Linux + Windows 都跑（subprocess mock 在两平台行为一致）
- mypy strict 必过：本 PR 改的 `tools/photo3d_handoff.py` / `tools/jury/stderr_messages.py` / `cad_pipeline.py` 保持 strict（不降级；jury v1 已上 mypy strict CI gate）
- ruff check + format 必过
- coverage：
  - **cov source explicit list**：`--cov=tools.photo3d_handoff --cov=tools.jury.stderr_messages`（不依赖默认 `--cov` source 自动发现）
  - **platform split**：Linux job 与 Windows job 分别 explicit 列 cov source（沿用 memory `feedback_ci_cov_gate_platform_split`：requires_solidworks 模块 Linux 全 SKIP 拖死 gate 教训；本 PR 模块均 platform-agnostic 但仍按规范分列）
  - 阈值：本 PR 新加路径 ≥90% 覆盖；测量命令 `uv run pytest tests/test_photo3d_handoff_with_jury.py tests/jury/test_stderr_messages.py --cov=tools.photo3d_handoff --cov=tools.jury.stderr_messages --cov-fail-under=90`

---

## 7. 兼容性与迁移

### 7.1 cli 层

- 不带 `--with-jury` 跑 `photo3d-handoff`：行为完全等同 v2.27.0；H1 用例守门
- jury v1 独立用户跑 `photo3d-jury`：行为完全等同 v2.27.0（本 PR 不改 jury 任何代码）

### 7.2 报告 schema

- `PHOTO3D_HANDOFF.json`：add-only 加 jury_status / review_status / enhance_review_path / jury_estimated_usd / jury_actual_usd 五字段；`schema_version` 不升（按 jury v1 invariant 14 add-only 兼容性宪章）
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

预估 plan 阶段会拆 ~14-16 task。粗顺序：

1. **C0 准备 + 验证现有事实**：spec commit（已）；plan task 0 加 grep 守门：confirm jury `--dry-run` 现有单测路径 + confirm `command_return_code` 当前签名 + confirm autopilot next_action 数据结构
2. **C1 stderr 模板组扩展**：在 `format_stderr_message` keyword-only 签名 `(*, exit_code, status, error_kind, context)` 的 if/elif 分支 add-only 加 13 个 `handoff_*` error_kind 模板 + 3 单测（no_unfilled_placeholders / dispatch_complete / no_secret_leakage）
3. **C2 handoff parser 注册**：cad_pipeline.py 子解析器加 `--with-jury` `--no-strict-jury`；H1 golden snapshot 守门
4. **C3 handoff 自身 lock + fail-fast preflight**：实现 step 0 `.handoff.lock` + step 0.5 jury config 预检；H20 + H21
5. **C4 handoff orchestrator step 1-2 (enhance + check)**：H13 + H23（crash mid-step）
6. **C5 handoff orchestrator step 3 (jury --dry-run)**：H10 + H14 + H9a/b（cost over budget / 估价文案 / config 错双向）
7. **C6 handoff orchestrator step 4 (jury 实跑)**：H2 + H3 + H4 + H5 + H6 + H7a/b + H8a/b + H11a/b + H18 + H19（13 用例；含 unexpected exit 130/137）
8. **C7 handoff orchestrator step 5 (enhance-review)**：H12 + H15 + H16 + H17（accepted + review 失败 / 路径不存在 / path traversal / 损坏 JSON）
9. **C8 subprocess argv 形式守门**：H22（专用 invariant 11 守门）
10. **C9 文档**：docs/cad-jury-config.md / PROGRESS.md / README.md（README 仅列 `--with-jury` 为推荐选项，不改默认推荐）
11. **C10 全量回归 + ruff/mypy strict 检查 + cov ≥90% + 北极星 5 gate 体检**
12. **C11 PR 与 review 流程**

注：v1.2 草拟的 autopilot next_action 文案任务 **v1.3 移出本 PR 范围**（autopilot 当前推荐 enhance 不推荐 handoff，集成需先重设计 autopilot 增加新中间状态分支；推到 A1.1 独立 PR）。

每个 C 段一个 commit；C1-C9 内每个 H 用例独立子任务，先 RED 后 GREEN。

**plan task 0 grep 守门清单**（防 spec 假设漂移；session 39 教训）：
- `grep -n "def run_photo3d_handoff\|def command_return_code" tools/photo3d_handoff.py` → 确认行号与签名
- `grep -n "test_dry_run" tests/jury/` → 确认 jury --dry-run 现有单测覆盖范围
- `grep -n "next_action" tools/photo3d_autopilot.py cad_pipeline.py` → 确认 autopilot next_action 数据结构
- `grep -n "_TEMPLATES\|format_stderr_message" tools/jury/stderr_messages.py` → 确认现有三元组分派内部存储结构
- `grep -rn "run_id" tools/photo3d_jury.py` → 确认 jury report run_id 字段写入位置 + 格式

---

## 9. 风险与已知 unknown

### 9.1 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| handoff e2e mock 子进程在 Windows / Linux 行为差异 | 测试 flake | patch target 钉死 `tools.photo3d_handoff.subprocess.run`；fake 函数签名固定；H22 专用守门 |
| 同机并发跑 photo3d-handoff（双 terminal / CI 多 worker）| 数据 corruption 或 race | invariant 14 handoff 自身 `.handoff.lock` 覆盖 step 0-6；H21 守门 |
| jury report `run_id` 字段被恶意改写为 `..` 路径 | path traversal 攻击 | invariant 10 三层守门：正则格式校验 + `assert_within_project` + `.is_file()`；H16 守门 |
| `jury_review_input.json` 是损坏 JSON | enhance-review 报错信息混淆 | invariant 10 校验 `json.loads()`；exit=23 独立类目；H17 守门 |
| jury 进程被 SIGINT / SIGKILL（exit=130/137 等 unexpected）| handoff 静默走入 step 5 | invariant 7 优先级判定 (c) 分支：unexpected → exit=25；H18 + H19 守门 |
| jury cost 估价依赖 `ENHANCEMENT_REPORT.json` 已存在 | 步骤 3 在步骤 1+2 失败时跑不起来 | 实现保证：handoff 严格 step 顺序 |
| jury config 缺失但用户已跑了 5 分钟 enhance | LLM 额度白花 | step 0.5 fail-fast preflight 在 step 1 之前；H20 守门；jury config 缺失立即 exit=2 |
| handoff stderr 透传 jury subprocess stderr 含 traceback | 潜在 api_key / 路径泄漏 | invariant 12 stderr 透传必走 `redact_traceback_str` + `redact_body` |
| handoff 子进程 env 注入凭据 | 凭据扩散到子进程 | invariant 3 `env=os.environ.copy()` 不主动注入；H22 assert env 不含敏感键的主动注入 |
| `--no-strict-jury` 命名歧义（用户误以为"跳过 jury"）| UX 混淆 | docs/cad-jury-config.md 显式表格列出 strict/no-strict 行为；模板含"加 --no-strict-jury 仅警告（结果不进入 deliver）"明确措辞 |
| autopilot next_action 子串误判（subsystem 名含 `--with-jury`）| 测试假绿 | autopilot 测试用 token 边界正则；invariant 1 + 6.4 守门 |
| review 子进程 exit code 与 handoff exit 段撞码 | 用户从 exit code 判断不出阶段 | clamp_review_exit 函数 1→20/2→21/3→22/其他→23 |
| step 4 后 ARTIFACT_INDEX.json 被外部进程改 | jury report 内 run_id 失效 | H 用例 fixture 不模拟（实战频率低）；如有问题靠 invariant 14 handoff lock 兜底 |
| 双 stderr 估价打印（jury + handoff）造成用户困惑 | 看到两次估价 | invariant 8 单源打印：handoff 不重复打印估价，仅在 over budget 时打中文提示 |

### 9.2 已知 unknown

- handoff 当前 description epilog 的实际文本是否需要重写（行数较多）— C8 阶段决定
- jury `--dry-run` 是否需要 handoff 显式传 `--budget`/`--profile-id` — 当前假设走 jury v1 默认；C3 阶段验证

### 9.3 不接受的风险（Red Team 防线）

- **不允许**：handoff 自己 import jury 模块函数直接调（破坏 invariant 3 子进程隔离）
- **不允许**：handoff 自己拼 stderr 文案（破坏 invariant 5.3 唯一入口）
- **不允许**：handoff stderr 用 f-string 含变量名 api_key/base_url/model（防意外泄漏）
- **不允许**：autopilot 实跑 jury 或 enhance（破坏 invariant 1 autopilot 行为不变）
- **不允许**：handoff 修改 jury 子模块的任何文件（除 `tools/jury/stderr_messages.py` 的 `_TEMPLATES` 字典 add-only 扩展）
- **不允许**：handoff 调子进程用 shell=True 或字符串拼接 argv（防注入）
- **不允许**：handoff 用并行的 string-key 分派函数 `format_handoff_message`（必须复用 `format_stderr_message` 三元组分派）
- **不允许**：handoff 写 PHOTO3D_HANDOFF.json 不走 `write_json_atomic` + `assert_within_project` 三参数

---

## 10. 验收标准（DoD）

完成本 PR 必须满足：

1. **测试**：所有 §6 测试 PASS（H1-H23 共 29 用例：H1/H1b/H1c 三回归 + H7a/H7b/H8a/H8b/H9a/H9b/H11a/H11b 工具故障双向 + H2/H3/H4/H5/H6/H10/H12-H23 单 = 29 用例 + 5 stderr 模板/clamp/格式单测；**autopilot 测试本 PR 不加**）
2. **回归**：`tests/` 全量 PASS 不少于 v2.27.0 基线（≥2622 PASS）
3. **mypy strict**：本 PR 改的所有文件（tools/photo3d_handoff.py / tools/jury/stderr_messages.py / cad_pipeline.py）保持 strict 不降级；不允许 `# type: ignore` 无注释（CLAUDE.md）
4. **ruff check + format**：clean，无 violations
5. **CI**：Linux + Windows 双平台全绿
6. **coverage**：
   - 命令：`uv run pytest tests/test_photo3d_handoff_with_jury.py tests/jury/test_stderr_messages.py --cov=tools.photo3d_handoff --cov=tools.jury.stderr_messages --cov-fail-under=90`
   - **cov source explicit list**（不依赖默认发现）
   - **Linux + Windows 各自独立测**（platform split）
7. **文档**：
   - `docs/cad-jury-config.md` 加 "通过 photo3d-handoff 一条命令跑闭环" 章节，含 `--with-jury` `--no-strict-jury` flag 矩阵
   - `docs/PROGRESS.md` 加 v2.28.0 入口
   - 本 spec commit 在 `docs/superpowers/specs/`
   - `README.md` 用法示例追加 `--with-jury` 推荐用法（不改默认推荐）
8. **北极星 5 gate 体检**（每条须有具体证据）：
   - 零配置：✓ 不引入新配置；jury config 缺失时 step 0.5 fail-fast 立即报错引导用户到 `docs/cad-jury-config.md`，不跑 enhance（不浪费 LLM 额度）
   - 稳定可靠：✓ strict 默认 + 工具故障类必阻断；`.handoff.lock` 防同机并发；invariant 7 优先级判定杜绝 jury exit code 静默漏判；invariant 6 dry-run 不取锁消除 race window
   - 结果准确：✓ jury accepted → enhance-review 串联保证 deliver 前必有正式 ENHANCEMENT_REVIEW_REPORT.json；review_input path traversal / 损坏 JSON 三层守门
   - SW 装即用：✓ 无 SW 涉及
   - 傻瓜式操作：✓ 一条 `photo3d-handoff --with-jury --confirm` 跑完整闭环；模板含"下一步动作"清单不要求外行用 Task Manager
9. **schema 钉死**：PHOTO3D_HANDOFF.json 字段 keyset 与 §4.2 决策表 + 数据流 §4.1 步骤 6 完全一致；`jury_handoff_status` 字符串值与决策表完全一致（H1-H23 各用例 assert 字段值）；现有 `status` 字段（值 awaiting_confirmation 等）的枚举值与 v2.27.0 完全一致 H1 守门
10. **PR 流程**：feature/jury-v2-handoff-integration → PR → CI 全绿 → squash merge → tag v2.28.0 + GitHub Release

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
| `tools/photo3d_jury.py` | jury main 入口（本 PR 不动；复用 v1 已有 `--dry-run` flag） |
| `tools/jury/cost.py` | cost 估价逻辑（dry-run 模式复用） |
| `tools/jury/stderr_messages.py` | 中文文案模板模块（本 PR add-only 加 HANDOFF_* 组） |
| `cad_pipeline.py:cmd_photo3d_handoff` | handoff 主体（本 PR orchestrator 改造） |
| `cad_pipeline.py:cmd_photo3d_autopilot` | autopilot 主体（本 PR 仅文案改动） |
| `tests/jury/conftest.py` | autouse kill switch + dummy fixture key |
| `CLAUDE.md` | 项目工作流约束（superpowers + TDD + 中文输出） |
