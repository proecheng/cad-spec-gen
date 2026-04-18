# SW self-hosted runner F-1.3 Phase F.2 完整生产链路验收设计

**承接**：决策 #39 / F-1.3 / Phase F.1（main@25a467d，runbook §7 F.1 baseline 已落，runner `procheng-sw-smoke` 已注册并跑绿 2 次）

**关联文档**：

- spec：`docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md`（F.1 设计）
- plan：`docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md`（F.1 计划）
- runbook：`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`
- decisions：`docs/superpowers/decisions.md` #39

**澄清问答锁定**（brainstorming 5 轮，每轮单选）：Q1=A（Task 已注册但从未触发）/ Q2=B（runner online + workflow_dispatch 跑绿）/ Q3=2（脚本不归 F.2）/ Q4=B（单次标准修复后 abort）/ Q5=B（runbook §7 扩展记录）

---

## 1. Scope / Non-Goals

### 1.1 Scope（F.2 验证什么）

证明一条 4 环节自启动链路在 zero human intervention 下可走通：

```
机器重启 → Autologon 登 ghrunner → Task Scheduler 触发 run.cmd → runner 在 GitHub 上线
            └──肉眼观察──┘    └──Get-ScheduledTaskInfo──┘  └──gh api──┘
```

加 1 条尾巴 pickup 验证：`workflow_dispatch` → runner 自动 pickup → conclusion=success（证 F.1 之后没 regression）。

### 1.2 Non-Goals（F.2 明确不做）

- ❌ 不优化 runner 启动时长（哪怕 Autologon 要 30s 也 OK）
- ❌ 不动 `sw-smoke.yml` workflow 本身（F.1 已证绿）
- ❌ 不把 `setup-runner-task.ps1` 入 git（Q3 定了拆出，独立 chore）
- ❌ 不清理 `.claude/settings.local.json` drift（无关）
- ❌ 不做 license 冲突 / 网络浮动许可验证（runbook §8.5 明说不覆盖）
- ❌ 不启动长期可观测性（dashboard / K 指标历史图——是 F-1.3a 的事）
- ❌ 不新增 pytest / contract test（无新代码可测）

### 1.3 失败语义

PASS/FAIL 以 4 环节 + dispatch pickup 是否全绿为准（C1-C4，定义见 §3）。任一环节失败 → 允许单次标准修复 → 仍失败即 FAIL（按 §4 流程 abort，失败现象记 F-1.3 backlog，**当次不追深度修复**）。

---

## 2. 组件与人机分工

### 2.1 人工侧（必须人肉）

| ID | 动作 | 成功信号 | 预计 |
|---|---|---|---|
| P1 | 触发重启：`shutdown /r /t 0` 或物理按键 | 机器关机进入冷启 | ~1 min |
| P2 | 肉眼观察登录屏 | 不停在登录画面，跳到 ghrunner 桌面 | ~30 s |
| P3 | `Ctrl+Alt+Del` → **Switch User** → proecheng → 输密码 | proecheng 桌面打开、可启动 Claude Code | ~30 s |
| P4 | 告诉我："到 proecheng 了" | 一句话即可 | — |

**重要**：P3 必须用 **Switch User**（不是 Logout / Sign out）。Switch User 保留 ghrunner session 在后台让 run.cmd daemon 继续跑；Logout 会杀 session、F.2 直接失败。

### 2.2 工具侧（我做）

| ID | 动作 | 命令 | 成功判据 | 超时 |
|---|---|---|---|---|
| T1 | 查 Task 触发情况 | `Get-ScheduledTaskInfo -TaskName 'GitHub Actions Runner (sw-smoke)'` | `LastRunTime ≠ 1999-11-30` 且 `LastTaskResult ∈ {0, 267009}` | 即时 |
| T2 | 等 runner 上线 | `gh api repos/proecheng/cad-spec-gen/actions/runners --jq ...` 轮询 | `status=online, busy=false` | 15 s × 8 = 2 min |
| T3 | 触发 dispatch | `gh workflow run sw-smoke.yml --ref main` | 返回 run ID | 即时 |
| T4 | 等 workflow 跑完 | `gh run watch <id> --exit-status`（或轮询）| `status=completed, conclusion=success` | 30 s × 40 = 20 min |
| T5 | 抓证据 | run URL / LastRunTime / duration | 给 §7 模板字段填值 | 即时 |

### 2.3 合流点

> P4（你说"到 proecheng 了"）→ 我连续执行 T1→T5，中间你不动

---

## 3. 时序与检查点

### 3.1 顺利 path（端到端 ~10 分钟）

```
 T=0     你：保存 proecheng 未存的工作（重启会丢编辑器状态）
         我：核对 gh auth status / 准备 T1-T5 命令
                            │
 T+1min  P1 重启
                            │
 T+3min  P2 肉眼：ghrunner 桌面出现？           [C1 检查点]
                            │
         ghrunner session 内 Task Scheduler 几秒~几十秒触发 run.cmd
                            │
 T+4min  P3 Switch User → proecheng → 输密码
                            │
 T+5min  P4 你开 Claude，告诉我"到 proecheng 了"
                            │
 T+5min  ──── 合流 ────
                            │
 T+6min  T1 LastRunTime ≠ 1999？                [C2 检查点]
                            │
 T+7min  T2 runner status=online？               [C3 检查点]
                            │
 T+8min  T3 gh workflow run sw-smoke.yml --ref main → run ID
                            │
 T+9min  T4 conclusion=success？                 [C4 检查点]
                            │
 T+10min T5 抓数据 → §7 F.2 段回填 → git add → commit
```

### 3.2 检查点定义

| 检查点 | 失败现象 | 单次标准修复（Q4=B）| 修后再试 |
|---|---|---|---|
| **C1** Autologon 不登 | 卡登录画面 / 默认登成 proecheng | 重跑 `Autologon.exe` 设 ghrunner → 再 `shutdown /r /t 0` 一次 | P2 再看一次；仍失败 = FAIL |
| **C2** Task 未触发 | LastRunTime 仍 `1999-11-30` | Task Scheduler GUI → 右键任务 → Run（手动拉起）| T1 再查；仍 267011 = FAIL |
| **C3** runner offline | T2 超时 2min 仍 `status=offline` | 查 `D:\actions-runner\_diag\*.log` 末段 → 按 runbook §8.1 一次 | T2 再轮询；仍 offline = FAIL |
| **C4** workflow 失败 | `conclusion=failure` | **二分判定**：pickup 层失败 = F.2 FAIL；workflow 内部 step 红 = F.2 PASS + 另起 issue | — |

### 3.3 C4 二分判定细则

抓 `gh run view <id> --json jobs` 看：

- 若 `jobs[0].steps[]` 全部 `conclusion=skipped` 或 job 整体 `startedAt=null` → **pickup 层失败**（runner 没接到 / label 不匹配）→ F.2 FAIL
- 若 `jobs[0].steps[]` 有正常运行的 step（哪怕 fail）→ **workflow 内部失败** → F.2 PASS（pickup 通了），另起 issue 处理失败 step

---

## 4. 错误处理与失败出口

### 4.1 失败分级

- **链路失败**（C1-C4）：F.2 判 FAIL，按 §3.2 单次修复后 abort
- **工具失败**（gh auth / PowerShell 权限 / 网络）：不算 F.2 失败，修工具后重试该步
- **C4 细分**（§3.3）：pickup vs workflow 内部，pickup 才算 F.2 FAIL

### 4.2 FAIL 时证据要写

哪怕 C1 就卡住，也按 §5 模板填能拿到的字段。这是下次 brainstorming 的诊断输入。最小 FAIL 证据：

- 失败检查点（C1/C2/C3/C4-pickup）
- 单次修复尝试做了什么、为什么没用
- `Get-ScheduledTaskInfo` 完整输出
- `gh api runners` 完整输出
- 若 C3：`D:\actions-runner\_diag\*.log` 末 30 行

### 4.3 状态清理

**默认什么都不清**。
- ghrunner session 保留运行（即使 FAIL，便于下次诊断）
- Task Scheduler 条目保留
- 不回滚 runbook，commit message 改成 `docs(sw-self-hosted-runner): F.2 FAIL at C<n> / 证据回填`

例外：若 C3 发现 run.cmd 是僵尸进程残留 → 去 ghrunner session 手动结束。

### 4.4 FAIL 出口

1. runbook §7 写 FAIL section（含证据字段）
2. git commit
3. memory `solidworks_asset_extraction.md` F.2 bullet 改写为 "F.2 attempted <date>, FAIL at C<n>"
4. memory `MEMORY.md` 同步描述
5. 新起一次 brainstorming 分析 C<n> 根因（**不在** F.2 scope）

### 4.5 工具失败常见修复

| 症状 | 诊断 | 修复 |
|---|---|---|
| `gh api` 401/403 | token 过期 | `gh auth status` / `gh auth login` |
| `Get-ScheduledTaskInfo` Access Denied | 非 admin shell | 重开 admin PowerShell |
| `gh workflow run` 422 | workflow 文件 invalid 或 ref 错 | `gh workflow view sw-smoke.yml` 核对 |
| T2/T4 轮询超时 | 网络抖动 | 再轮询一次；仍失败升级为对应 C3/C4 判 |

---

## 5. 证据落地（runbook §7 模板）

### 5.1 落点

`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` §7 末尾、F.1 baseline 段落**之后**，追加新段落（同级 bold），不重排 §7 结构。

### 5.2 PASS 模板

```markdown
**F.2 完整生产链路验收记录**（2026-04-XX，run XXXXXXX）：

- 验收日期：**2026-04-XX**
- 触发方式：手动 `gh workflow run sw-smoke.yml --ref main`（workflow_dispatch）
- run URL：https://github.com/proecheng/cad-spec-gen/actions/runs/XXXXXXX
- 链路检查点：
  - **C1 Autologon**：PASS（重启后 ~XXs ghrunner 桌面出现）
  - **C2 Task Scheduler**：PASS（LastRunTime=`2026-04-XX HH:MM:SS`，LastTaskResult=`0`/`267009`）
  - **C3 runner online**：PASS（runner `procheng-sw-smoke` 在 ghrunner 登录后 ~XXs status=online）
  - **C4 workflow pickup + run**：PASS（dispatch → pickup ~XXs → conclusion=success，总耗时 XXs）
- 与 F.1 对比：CI 总耗时 XXs（F.1=57s）；K1 dispatch.elapsed_ms=XXXX ms（F.1=5492ms）
- 结论：**F-1.3 Phase F.2 PASS**，自动化生产链路端到端通
- F.2 后状态：runner long-lived，下次 push main 自动触发无需人介入
```

### 5.3 FAIL 模板（备用）

```markdown
**F.2 验收尝试记录**（2026-04-XX，FAIL at C<n>）：

- 尝试日期：**2026-04-XX**
- 失败检查点：**C<n>**（现象：....）
- 单次修复尝试：....（依据 runbook §X.X / Q4=B）
- 修复后结果：仍失败
- 诊断证据：
  - `Get-ScheduledTaskInfo` 完整输出：```...```
  - `gh api runners` 完整输出：```...```
  - `_diag/*.log` 末 30 行（仅 C3 失败时填）：```...```
- 下次行动：另起 brainstorming 专题分析 C<n>，本 F.2 不追修
- 当前 ghrunner session 状态：保留运行
```

### 5.4 联动更新

无论 PASS / FAIL：

- `memory/solidworks_asset_extraction.md`：F.2 bullet 改写为 "Phase F.2 PASS（2026-04-XX，run XXX）" 或 "F.2 attempted FAIL at C<n>，见 runbook §7"
- `memory/MEMORY.md`：description 摘掉 "剩余 F.2"

### 5.5 不更新

- ❌ `decisions.md`：F.2 是验收不是决策
- ❌ 独立 `docs/superpowers/reports/` 报告（Q5=B 已选）
- ❌ README CI 段（F.1 已写 sw-smoke）
- ❌ `cad_pipeline_agent_guide.md`（F.2 不引入新 CLI 行为）

---

## 6. 测试策略

### 6.1 不新增任何自动化测试

F.2 不引入新代码，所以：

- 不动 `tools/sw_inspect.py` / `adapters/solidworks/*` / `tools/assert_sw_inspect_schema.py`
- 不加新 `@requires_solidworks` 测试
- 不动 `.github/actions/setup-cad-env/` 或 `sw-smoke.yml`

### 6.2 测试 = §3 时序现场执行 + §5 字段对照

| 测试类型 | 由谁 | 通过判据 |
|---|---|---|
| 链路功能测试 | 你 + 我 | §3.2 的 C1-C4 全 PASS |
| 回归测试（隐式）| sw-smoke 自身 | T4 conclusion=success |
| 文档准确性测试 | spec 自审 | §5 模板填完后 placeholder 数 = 0 |

### 6.3 隐式 regression

T4 触发的 sw-smoke 跑等效再做一次 F.1，顺带验证：

- ✅ `python -m pytest tests/test_sw_inspect_real.py -m requires_solidworks` 仍绿
- ✅ skip-guard `real >= 1` 仍成立
- ✅ `assert_sw_inspect_schema.py` 仍 PASS
- ✅ sw-inspect JSON v1 schema 没漂移
- ✅ runner labels `[self-hosted, Windows, X64, solidworks]` 仍匹配

任一红 → 走 §3.3 二分（F.2 仍判 PASS，另起 issue）。

### 6.4 完成判据（"何时能宣告 F.2 done"）

按 superpowers:verification-before-completion 精神，硬门槛 4 项：

1. §5 PASS 模板所有字段（XX 残留 = 0）填完
2. `git diff` 看到 runbook §7 F.2 段落实际落地
3. memory 两个文件均更新
4. `git log` 看到对应 commit

四项满足 → 才说 "F.2 done"。

---

## 附录 A：T1-T5 命令清单（执行用）

### T1 — Task Scheduler 状态

```powershell
Get-ScheduledTaskInfo -TaskName 'GitHub Actions Runner (sw-smoke)' |
  Select-Object LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns |
  Format-List
```

### T2 — runner 上线轮询

```powershell
$max = 8
for ($i = 1; $i -le $max; $i++) {
  $r = gh api repos/proecheng/cad-spec-gen/actions/runners |
       ConvertFrom-Json |
       Select-Object -ExpandProperty runners |
       Where-Object { $_.name -eq 'procheng-sw-smoke' }
  Write-Host "[$i/$max] status=$($r.status) busy=$($r.busy)"
  if ($r.status -eq 'online') { break }
  Start-Sleep -Seconds 15
}
```

### T3 — 触发 dispatch 并抓 run ID

```powershell
gh workflow run sw-smoke.yml --ref main
Start-Sleep -Seconds 3
$runId = gh run list --workflow=sw-smoke --event=workflow_dispatch --limit=1 --json databaseId --jq '.[0].databaseId'
Write-Host "dispatched run id: $runId"
```

### T4 — 等 workflow 完成

```powershell
gh run watch $runId --exit-status
# 或轮询版本：
# gh run view $runId --json status,conclusion
```

### T5 — 抓证据

```powershell
gh run view $runId --json databaseId,url,createdAt,updatedAt,conclusion,jobs |
  ConvertFrom-Json |
  Format-List
# 同时再跑一次 T1 拿 LastRunTime 真值
```

---

## 附录 B：变更影响清单

| 文件 | 变更性质 | 来自 |
|---|---|---|
| `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` | §7 追加 F.2 段（PASS 或 FAIL）| §5.1 |
| `memory/solidworks_asset_extraction.md` | F.2 bullet 改写 | §5.4 |
| `memory/MEMORY.md` | description 摘掉 "剩余 F.2" | §5.4 |
| `docs/superpowers/specs/2026-04-18-sw-runner-f2-design.md` | 本 spec（新建）| 本文件 |
| `docs/superpowers/plans/2026-04-18-sw-runner-f2.md` | 实施计划（writing-plans 阶段建）| 下一步 |

不变更（明确）：

- `setup-runner-task.ps1`（保持 untracked，按 Q3 拆出独立 chore）
- `.claude/settings.local.json`（drift 无关）
- `sw-smoke.yml` / `setup-cad-env/action.yml` / `tools/sw_inspect.py`
- `decisions.md`（F.2 非决策）
