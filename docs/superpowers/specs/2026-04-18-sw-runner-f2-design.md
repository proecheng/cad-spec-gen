# SW self-hosted runner F-1.3 Phase F.2 完整生产链路验收设计

**承接**：决策 #39 / F-1.3 / Phase F.1（main@25a467d，runbook §7 F.1 baseline 已落，runner `procheng-sw-smoke` 已注册并跑绿 2 次）

**关联文档**：

- spec：`docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md`（F.1 设计）
- plan：`docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md`（F.1 计划）
- runbook：`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`
- decisions：`docs/superpowers/decisions.md` #39

**澄清问答锁定**（brainstorming 5 轮，每轮单选）：Q1=A（Task 已注册但从未触发）/ Q2=B（runner online + workflow_dispatch 跑绿）/ Q3=2（脚本不归 F.2）/ Q4=B（单次标准修复后 abort）/ Q5=B（runbook §7 扩展记录）

**审查修订记录**：

- v1：初稿（brainstorming 5 轮 Q&A 锁定后）
- v1.1：自审 3 项（嵌套 fence / memory 路径 / grep 判据）
- v2：5 角色 adversarial（系统分析师/架构师/3D 设计师/软件测试员/机械设计师）一致 NO → P1×5 + P2×4 + P3×4 共 13 项合入
- v3：代码-spec 对照 5 项（`.runner` 无 agentVersion / PC3 脚本依赖 / PC4 reg query / Listener vs Worker / artifact download）
- **v3.5（本稿）**：holistic 终审 + execution dry-run，1 BLOCKER + 4 P2 + 3 小修：
  - **BLOCKER 修**：PowerShell 跨 reboot 变量丢失 → PC7 加 Export-Clixml / T1 加 Import-Clixml
  - **PC7 加硬约束**：baseline runner_status 必须 = offline，否则 abort（T2 transition 检测前提）
  - §1.3 表头修语义 / §3.2 C2 加"需 admin" / §3.2 C3 修法加优先序 / §6.2 加 pickup 失败 → FAIL / §5.5 加 commit message 模板 / §3.1 加 timeline 说明（期望 vs 上限）

---

## 0. 业务动机与 PASS 承诺边界

### 0.1 为什么 F.2 重要

没 F.2 → runner 在"机器需重启"场景下从未真正验证自启动链路（F.1 期间 runner 是 proecheng session 手工 `run.cmd` 拉起的）。直接业务影响：

- **任何重启事件后**（Windows Update 强制重启 / 物理停电 / 90 天凭证轮换 / SW 升级）→ runner 可能静默掉线，**没人知道**
- **机械/3D 设计师推 `sw_toolbox_adapter` / `sw_warmup` 改动** → CI 不跑 → 真 SW 回归漏到生产 → 装配错件 / STEP 出料退化

F.2 锁定的是**最低保证**：机器复活后链路能自动重建，无需人工介入。

### 0.2 F.2 PASS 给消费者的承诺

- ✅ **链路层**：runner 自启动 OK，下次 `push main` 自动 pickup（含 commit 触发 / dispatch 触发等价）
- ✅ **schema 回归**：`tools/assert_sw_inspect_schema.py` PASS、sw-inspect JSON v1 字段不漂
- ✅ **materials 业务回归**：`materials.sldmat_files > 0`（`test_deep_real_smoke` 已断言）
- ✅ **运行时回归**：真 SW Dispatch 仍可用、5492 ms ± Δ 量级未异常退化

### 0.3 F.2 PASS **不**代表（消费者必须明白）

- ❌ **toolbox 业务层回归**：`toolbox_index.by_standard` 至少 1 个 GB 标准件 entry 的断言**未在 sw-smoke 内**（推迟到 F-1.3h）。toolbox parser 退化（GB 标准件 0 命中）F.2 不会 catch
- ❌ **STEP 转换正确性**：sw-smoke 不跑 sw-warmup / Stage C，STEP 出料质量未验
- ❌ **永久有效**：runner 凭证 90 天有效（决策 #39 提醒），SW license / Windows Update / 网络配置变更都可能让链路在数天/数周后静默失效。**F.2 PASS 仅代表当日链路 OK**
- ❌ **跨机器**：F.2 在本机 procheng-sw-smoke 通，不证明换一台机器/账户也 OK

### 0.4 周期性复验提醒

| 触发条件 | 是否需要复跑 F.2 |
|---|---|
| 决策 #39 90 天 token 轮换 | **是**（runbook §9 + 复跑 F.2）|
| Windows 大版本升级 | **是** |
| SolidWorks 升级 | **建议** |
| 物理停电 / 计划性维护重启 | 否，但应观察 runner 状态 |

---

## 1. Scope / Non-Goals

### 1.1 Scope（F.2 验证什么）

证明一条 4 环节自启动链路在 zero human intervention 下可走通：

```
机器重启 → Autologon 登 ghrunner → Task Scheduler 触发 run.cmd → runner 在 GitHub 上线
            └──肉眼观察──┘    └──Get-ScheduledTaskInfo──┘  └──gh api──┘
```

加 1 条尾巴 pickup 验证：`workflow_dispatch` → runner 自动 pickup → conclusion=success。

### 1.2 Non-Goals（F.2 明确不做）

- ❌ 不优化 runner 启动时长（哪怕 Autologon 要 30 s 也 OK）
- ❌ 不动 `sw-smoke.yml` workflow 本身（F.1 已证绿）
- ❌ 不把 `setup-runner-task.ps1` 入 git（Q3 定了拆出，独立 chore）
- ❌ 不清理 `.claude/settings.local.json` drift（无关）
- ❌ 不做 license 冲突 / 网络浮动许可验证（runbook §8.5 明说不覆盖）
- ❌ 不启动长期可观测性（dashboard / K 指标历史图——是 F-1.3a 的事）
- ❌ 不新增 pytest / contract test（无新代码可测）
- ❌ 不补 toolbox `by_standard` 业务断言（推迟到 F-1.3h）

### 1.3 失败语义（PASS clean / PASS pickup-only / FAIL 三档定义）

| 状态 | 定义 | 给消费者的信号 |
|---|---|---|
| **PASS clean** | 4 检查点 C1-C4 全 PASS **且** sw-smoke conclusion=success（含所有 §6.3 隐式 regression 全绿）| 链路通 + 回归无退化，可推 main 不必特别警惕 |
| **PASS pickup-only** | C1-C3 全 PASS、C4 pickup 层 OK 但 sw-smoke workflow 内部有 step 红 | 链路通但**有未处理回归**，必须立即另起 issue 处理 step 失败、推 main 风险高 |
| **FAIL** | C1-C3 任一失败、或 C4 pickup 层失败 | 链路未恢复，下次 push 不会被 CI 消费，**绝不能继续推 main** |

任一环节失败 → 允许单次标准修复 → 仍失败即 FAIL（按 §4 流程 abort，失败现象记 F-1.3 backlog，**当次不追深度修复**）。

---

## 2. 组件与人机分工

### 2.1 人工侧（必须人肉）

| ID | 动作 | 成功信号 | 预计 |
|---|---|---|---|
| P1 | 触发重启：`shutdown /r /t 0` 或物理按键 | 机器关机进入冷启 | ~1 min |
| P2 | 肉眼观察登录屏 | 不停在登录画面，跳到 ghrunner 桌面 | ~30 s |
| P2.5 | **等 ~30 s 让 run.cmd 完成启动**（Task Scheduler 触发 + Runner.Listener 启动 + GitHub 握手） | 不要立刻切走 | ~30 s |
| P3 | `Ctrl+Alt+Del` → **Switch User** → proecheng → 输密码 | proecheng 桌面打开、可启动 Claude Code | ~30 s |
| P4 | 告诉我："到 proecheng 了" | 一句话即可 | — |

**重要 1**：P3 必须用 **Switch User**（不是 Logout / Sign out）。Switch User 保留 ghrunner session 在后台让 run.cmd daemon 继续跑；Logout 会杀 session、F.2 直接失败。

**重要 2**：P2.5 不能省。Task Scheduler 的 AtLogOn trigger 在 logon 完成后触发，但 run.cmd → Runner.Listener.exe → GitHub 握手有 15-30 s 延迟。如果 P3 切走太快，run.cmd 仍可能完成（后台进程不依赖 GUI），但 T2 第一轮查 runner online 可能误失败、走入不必要的 C3 修复路径。

### 2.2 工具侧（我做）

| ID | 动作 | 命令要点 | 成功判据 | 超时 |
|---|---|---|---|---|
| T1 | 查 Task 触发 + daemon 进程 | `Get-ScheduledTaskInfo` + `Get-Process -Name Runner.Listener` | `LastRunTime > reboot_time` **且** `LastTaskResult = 267009`（任务正在跑）**且** **Runner.Listener**（注意：是 daemon，**不是** 跑 job 时短暂出现的 Runner.Worker）进程存在、StartTime > reboot_time | 即时 |
| T2 | 等 runner 上线（与 baseline 对比） | `gh api ...runners` 轮询 + 与 PC7 baseline 比较 | `status=online, busy=false` **且** `runner.id` 同一个但 GitHub 端检测到状态变化（避免 stale heartbeat 假阳）| 15 s × 12 = 3 min（v2 从 v1 的 2min 放宽 1min，已采纳）|
| T3 | 触发 dispatch | `gh workflow run sw-smoke.yml --ref main` | 返回 run ID | 即时 |
| T4 | 等 workflow 跑完 | `gh run watch <id> --exit-status` | `status=completed`，conclusion 用于判定 PASS clean / pickup-only | 5 min（F.1 baseline 57 s × 5σ） |
| T5 | 抓证据 | run URL / LastRunTime / duration / `host_fingerprint` / `runner_version` | 给 §7 模板字段填值 | 即时 |

### 2.3 合流点

> P4（你说"到 proecheng 了"）→ 我连续执行 T1→T5，中间你不动

---

## 3. 时序与检查点

### 3.0 Precondition 自检（reboot **前**必跑）

reboot 不可逆。任一项失败 → 停止 F.2、修完前置再开始。我执行，结果反馈给你确认。

| ID | 检查 | 命令 | 通过 | 不通过修法 |
|---|---|---|---|---|
| PC1 | gh CLI 已登录 | `gh auth status` | "Logged in to github.com" | `gh auth login` |
| PC2 | admin PowerShell | `[Security.Principal.WindowsPrincipal]([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")` | True | 重开 admin PS |
| PC3 | Task 条目存在 | `Get-ScheduledTask -TaskName 'GitHub Actions Runner (sw-smoke)'` | 返回 1 项，State=Ready | （若 `setup-runner-task.ps1` 仍在工作树）重跑脚本（admin），或按 runbook §6 GUI 重建 Task |
| PC4 | Autologon 目标 = ghrunner | `(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon').DefaultUserName` | 返回 `ghrunner` | 重跑 Sysinternals `Autologon.exe` 配 ghrunner |
| PC5 | runner 注册文件存在 | `Test-Path D:\actions-runner\.runner` | True | 按 runbook §5 重新注册 runner |
| PC6 | 网络可达 api.github.com | `gh api user --jq .login` | 返回 `proecheng` | 检查网络 / 代理 |
| PC7 | **记 baseline + 持久化到磁盘**（关键，给 T1/T2 用）| 写 `(reboot_time, runner_status, runner_id)` 到磁盘文件（reboot 摧毁 PS session 内变量，必须 Export-Clixml）| baseline 文件存在于约定路径 + `runner_status == 'offline'` **必须成立**（否则 T2 transition 检测失效）| — |

PC7 baseline 例：
```
reboot_time   = 2026-04-18 14:30:00（即将重启的时间）
runner_status = offline（当前确认；若为 online 则 reboot 前必须先停 runner，否则 F.2 abort）
runner_id     = 12345678（gh api 返回）
持久化文件   = D:\actions-runner\f2-baseline.xml（Export-Clixml）
```

**关键约束**：

- baseline 必须 `Export-Clixml` 到磁盘文件（T0 命令清单已含），否则 reboot 后 T1 重开 admin PS 时 `$rebootTime` = `$null`，PowerShell 5.1 中 `[DateTime] -gt $null` 返回 `$true` → C2 / C3 判据**假阳性 PASS**
- baseline `runner_status` 若不是 `offline`，T2 transition 检测（offline→online）逻辑不工作 → 需 abort F.2、先停 runner（PowerShell `Stop-ScheduledTask -TaskName 'GitHub Actions Runner (sw-smoke)'` + 等 ghrunner session 内 run.cmd 自然退出 + 等 GitHub 端 status=offline）后重开 F.2

### 3.1 顺利 path（端到端 ~10 分钟）

> 说明：以下 timeline 是**期望耗时**（best case，基于 F.1 经验：runner 上线 ~30 s、sw-smoke ~60 s）。§2.2 表里的 timeout 是**容忍上限**（T2=3min / T4=5min），仅在异常时才会跑满。


```
 T=0    我：跑 §3.0 PC1-PC7 precondition 自检 → 全 PASS 才继续
        你：保存 proecheng 未存的工作（重启会丢编辑器状态）
                              │
 T+1min P1 你触发重启
                              │
 T+3min P2 肉眼：ghrunner 桌面出现？           [C1 检查点]
                              │
 T+3.5min P2.5 等 ~30s 让 run.cmd / Runner.Listener 启动 + GitHub 握手
                              │
 T+4min P3 Switch User → proecheng → 输密码
                              │
 T+5min P4 你开 Claude，告诉我"到 proecheng 了"
                              │
 T+5min ──── 合流 ────
                              │
 T+6min T1 LastRunTime > reboot_time + Runner.Listener 进程存在？  [C2 检查点]
                              │
 T+8min T2 runner status=online 且不是 stale？                    [C3 检查点]
                              │
 T+8min T3 gh workflow run sw-smoke.yml --ref main → run ID
                              │
 T+9min T4 conclusion=success（或 conclusion=failure 走 §3.3 二分）  [C4 检查点]
                              │
 T+10min T5 抓数据 → §7 PASS clean / PASS pickup-only / FAIL 模板 → git commit
```

### 3.2 检查点定义

| 检查点 | 失败现象 | 单次标准修复（Q4=B）| 修后再试 |
|---|---|---|---|
| **C1** Autologon 不登 | 卡登录画面 / 默认登成 proecheng | (a) 验证 PC4：`reg query ... DefaultUserName` 是否真 ghrunner; (b) 不是→重跑 `Autologon.exe`; (c) 是→`shutdown /r /t 0` 再来 | P2 再看一次；仍失败 = FAIL |
| **C2** Task 未触发 / daemon 没起 | `LastRunTime ≤ reboot_time`（仍 1999 或时间未更新）/ `LastTaskResult = 267011`（从未跑）/ Runner.Listener 进程不存在 | (a) PowerShell `Start-ScheduledTask -TaskName 'GitHub Actions Runner (sw-smoke)'` 手动拉起 **(需 admin shell)**; (b) 等 10 s 再查 | T1 再查；仍同失败状态 = FAIL |
| **C3** runner offline | T2 超时 3 min 仍 `status=offline` | 按优先序：(1) 先看 `D:\actions-runner\_diag\Runner_*.log` 最新一份末 30 行；(2) 若日志显示网络错误 → 查 `gh api user` 验证 token / 网络；(3) 若日志显示进程异常退出 → 重启 run.cmd（在 ghrunner session 内 `D:\actions-runner\run.cmd`）；(4) 其他情况记 backlog | T2 再轮询；仍 offline = FAIL |
| **C4** workflow 失败 | `conclusion=failure` | **二分判定**（§3.3）：pickup 层失败 = F.2 FAIL；workflow 内部 step 红 = **PASS pickup-only** | — |

**注意**：C2 LastTaskResult 语义已重写：

- `267009` (`SCHED_S_TASK_RUNNING`) = **PASS** —— run.cmd daemon 正在跑（这是常态）
- `0` (`S_OK`) = **可疑** —— daemon 已成功退出，对 long-lived runner 而言反而异常 → 触发 §4.3 僵尸 / 退出诊断
- `267011` (`SCHED_S_TASK_HAS_NOT_RUN`) = **FAIL** —— 任务从未触发
- 其他非 0 退出码 = **FAIL** + 抓 _diag

### 3.3 C4 二分判定细则

抓 `gh run view <id> --json jobs` 看：

- 若 `jobs[0].startedAt = null`（job 从未开始）→ **pickup 层失败** → F.2 FAIL（runner 没接到，可能 label 漂移）
- 若 `jobs[0].startedAt != null` 且某个 step `conclusion=failure` → **workflow 内部失败** → F.2 **PASS pickup-only**（pickup 通了），另起 issue 排查具体 step
- 若 `jobs[0].startedAt != null` 且所有 step `conclusion=skipped` 但 job 整体 `conclusion=success` → 这是 sw-smoke `if:` skip 语义生效，**正常**（commit 含 `[skip smoke]`）→ 不应在 F.2 触发，dispatch 时 head_commit=null contains() 返回 false 不会 skip

---

## 4. 错误处理与失败出口

### 4.1 失败分级

- **链路失败**（C1-C3）：F.2 判 FAIL，按 §3.2 单次修复后 abort
- **C4 二分**（§3.3）：pickup 层 = FAIL；workflow 内部 = PASS pickup-only（必须另起 issue）
- **工具失败**（gh auth / PowerShell 权限 / 网络）：不算 F.2 失败，修工具后重试该步
- **PC1-PC7 自检失败**：**根本不进 F.2**，先修 precondition

### 4.2 FAIL 时证据要写

哪怕 C1 就卡住，也按 §5 模板填能拿到的字段。这是下次 brainstorming 的诊断输入。最小 FAIL 证据：

- 失败检查点（C1/C2/C3/C4-pickup）
- 单次修复尝试做了什么、为什么没用
- `Get-ScheduledTaskInfo` 完整输出
- `Get-Process Runner.Listener` 输出（PID / StartTime 是关键）
- `gh api runners` 完整输出（含 PC7 baseline 对照）
- 若 C3：`D:\actions-runner\_diag\*.log` 末 30 行
- 若 C4-pickup：`gh run view <id> --json jobs` 完整输出
- 若 C4 内部失败（PASS pickup-only）：建议 `gh run download $runId --name sw-smoke-artifacts` 抓 `sw-inspect-deep.json` + `sw-smoke-junit.xml` 进 evidence 目录

### 4.3 状态清理

**默认什么都不清**。
- ghrunner session 保留运行（即使 FAIL，便于下次诊断）
- Task Scheduler 条目保留
- 不回滚 runbook，commit message 改成 `docs(sw-self-hosted-runner): F.2 FAIL at C<n> / 证据回填`

**僵尸 / 异常残留判定**（如 C2 LastTaskResult=0 这种"任务退出了但 daemon 应该常驻"的怪态）：

```powershell
# 1. 查所有 Runner.Listener 进程
Get-Process -Name Runner.Listener -ErrorAction SilentlyContinue |
  Select-Object Id, StartTime, Path, CPU
# 0 行 = daemon 真没在跑（C2 PASS=False）
# 多行 = 有僵尸残留，按 PID 杀：Stop-Process -Id <pid>
# 1 行但 StartTime < reboot_time = 重启前的进程没被清，环境异常，记 backlog
```

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
| `gh api` 输出 empty / `$r` 为 `$null` | 网络抖 / jq 路径错 | 加 `if (-not $r) { Write-Warning "empty"; continue }` 防假阳跳出 |

---

## 5. 证据落地（runbook §7 模板）

### 5.1 落点

`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` §7 末尾、F.1 baseline 段落**之后**，追加新段落（同级 bold），不重排 §7 结构。

### 5.2 PASS clean 模板（4 检查点 + workflow 全绿）

```markdown
**F.2 完整生产链路验收记录**（2026-04-XX，PASS clean，run XXXXXXX）：

- 验收日期：**2026-04-XX**
- 触发方式：手动 `gh workflow run sw-smoke.yml --ref main`（workflow_dispatch）
- run URL：https://github.com/proecheng/cad-spec-gen/actions/runs/XXXXXXX
- host_fingerprint：`<hostname>` / Windows 11 build XXXXX
- runner_version：`<X.XXX.X>`（来自 `D:\actions-runner\bin\Runner.Listener.exe` ProductVersion；附录 A T5 命令；**不**取自 `.runner` 文件——实测该文件不含版本字段）
- 链路检查点：
  - **C1 Autologon**：PASS（重启后 ~XXs ghrunner 桌面出现）
  - **C2 Task Scheduler + daemon**：PASS（LastRunTime=`2026-04-XX HH:MM:SS`，LastTaskResult=`267009`，Runner.Listener PID=`XXXX` StartTime=`HH:MM:SS`）
  - **C3 runner online**：PASS（runner `procheng-sw-smoke` 在 ghrunner 登录后 ~XXs status=online，与 baseline offline 形成对照）
  - **C4 workflow pickup + run**：PASS（dispatch → pickup ~XXs → conclusion=success，总耗时 XXs）
- 与 F.1 对比：CI 总耗时 XXs（F.1=57s）；K1 dispatch.elapsed_ms=XXXX ms（F.1=5492ms）
- 结论：**F-1.3 Phase F.2 PASS clean**，自动化生产链路端到端通 + sw-smoke 回归全绿
- F.2 后状态：runner long-lived，下次 push main 自动触发无需人介入；当日有效，token 90 d 轮换 / Windows 大版本升级后须复跑
```

### 5.2.1 PASS pickup-only 模板（链路通但 workflow 内部红）

```markdown
**F.2 完整生产链路验收记录**（2026-04-XX，PASS pickup-only，run XXXXXXX）：

- 验收日期：**2026-04-XX**
- 触发方式 / run URL / host / runner_version：（同 §5.2）
- 链路检查点：
  - **C1 / C2 / C3**：PASS（同 §5.2 字段）
  - **C4 workflow pickup + run**：PASS pickup-only（dispatch → pickup ~XXs，但 conclusion=failure；jobs[0].startedAt 非 null，step `<step name>` 红）
- 失败 step 详情：
  - step name：`<step>`
  - failure log 摘要：`<前 200 字>`
- 结论：**F-1.3 Phase F.2 PASS pickup-only**，链路通但有未处理 workflow 内部回归
- 必须立即另起 issue：[issue link 或 "TODO"]
- 推 main 风险：**HIGH**（CI 会失败），未修复前不要推 main
```

### 5.3 FAIL 模板（备用）

```markdown
**F.2 验收尝试记录**（2026-04-XX，FAIL at C<n>）：

- 尝试日期：**2026-04-XX**
- host_fingerprint / runner_version：（同 §5.2）
- 失败检查点：**C<n>**（现象：....）
- 单次修复尝试：....（依据 runbook §X.X / Q4=B）
- 修复后结果：仍失败
- 诊断证据（fenced code block 单独贴在条目下）：
  - `Get-ScheduledTaskInfo` 完整输出：[PASTE_PS_OUTPUT]
  - `Get-Process Runner.Listener` 输出：[PASTE_PS_OUTPUT]
  - `gh api runners` 完整输出：[PASTE_JSON_OUTPUT]
  - `_diag/*.log` 末 30 行（仅 C3 失败时填）：[PASTE_LOG]
  - `gh run view <id> --json jobs`（仅 C4 失败时填）：[PASTE_JSON_OUTPUT]
- 下次行动：另起 brainstorming 专题分析 C<n>，本 F.2 不追修
- 当前 ghrunner session 状态：保留运行
```

### 5.4 联动更新

无论 PASS clean / PASS pickup-only / FAIL，更新 auto-memory 两份文件（路径在 repo 外、不入 git）：

- `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\solidworks_asset_extraction.md`：F.2 bullet 改写为对应状态 "Phase F.2 PASS clean"/"PASS pickup-only"/"attempted FAIL at C<n>"
- `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\MEMORY.md`：description 行摘掉 "剩余 F.2"

### 5.5 git commit message 模板（按状态）

| 状态 | commit message |
|---|---|
| PASS clean | `docs(sw-self-hosted-runner): F.2 PASS clean / runbook §7 回填` |
| PASS pickup-only | `docs(sw-self-hosted-runner): F.2 PASS pickup-only / runbook §7 回填 + 待 issue #X` |
| FAIL at C\<n\> | `docs(sw-self-hosted-runner): F.2 FAIL at C<n> / 证据回填` |

`git add docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` 后 commit；spec/plan **不**入此 commit（已在 brainstorming/writing-plans 阶段独立 commit）。

### 5.6 不更新

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
| 回归测试（隐式）| sw-smoke 自身 | T4 conclusion=success → PASS clean；conclusion=failure 且 pickup OK → PASS pickup-only；pickup 失败 → FAIL |
| 文档准确性测试 | spec 自审 | §5 模板填完后 placeholder 数 = 0 |

### 6.3 隐式 regression 覆盖（精确清单）

T4 触发的 sw-smoke 跑等效再做一次 F.1，**实际**覆盖的回归项（已对照 `.github/workflows/sw-smoke.yml` L19+L37+L60 + `tests/test_sw_inspect_real.py` 验证）：

| 回归项 | 在 sw-smoke 哪里 | 业务价值 |
|---|---|---|
| ✅ runner labels `[self-hosted, windows, solidworks]` 匹配 | sw-smoke.yml L19 `runs-on` | pickup 层基础 |
| ✅ `pytest tests/test_sw_inspect_real.py -m requires_solidworks` 跑过 | sw-smoke.yml L37-39 | 真 SW Dispatch 仍可用 |
| ✅ skip-guard `real >= 1` 成立 | sw-smoke.yml L41-52 ET-based | @requires_solidworks 没被全量 skip |
| ✅ `materials.sldmat_files > 0`（**关键业务断言**）| `test_deep_real_smoke` 内 | .sldmat 解析未退化 |
| ✅ `assert_sw_inspect_schema.py` PASS | sw-smoke.yml L60 | sw-inspect JSON v1 字段未漂移 |

**未覆盖**（消费者必须知道）：

| 未覆盖项 | 推迟到 | 当前风险 |
|---|---|---|
| ❌ `toolbox_index.by_standard` 至少 1 个 GB 标准件 entry | F-1.3h（conftest HOME redirect 待解）| toolbox parser 退化（GB 标准件 0 命中）F.2 不会 catch |
| ❌ STEP 转换 round-trip 质量 | sw-warmup / Stage C 范畴 | STEP 出料退化 F.2 不会 catch |
| ❌ COM 稳定性长期统计 | F-1.3a 可观测性 | 间歇 COM 失败被 mask |

任一已覆盖项红 → 走 §3.3 二分（pickup 通 = PASS pickup-only，必须另起 issue）。

### 6.4 完成判据（"何时能宣告 F.2 done"）

按 superpowers:verification-before-completion 精神，硬门槛 4 项：

1. **§5 PASS 模板字段全部填完**（验证：`grep -E '\[PASTE_|XXXXXXX|2026-04-XX HH:MM:SS' runbook §7 F.2 段落` 返回 0 行 —— 排除 `~XXs` / `procheng-sw-smoke` 这类正文 false-positive）
2. **runbook §7 改动落地 git**（验证：`git log --oneline -1 docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` 是 F.2 commit）
3. **memory 两个文件均更新**（验证：`Read` 工具读 `solidworks_asset_extraction.md` 看 F.2 bullet 已改写；`Read` 读 `MEMORY.md` 看 description 已摘 "剩余 F.2"。memory 在 repo 外的 `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\`，git diff 不可见）
4. **runner 仍在 GitHub 端 online**（验证：`gh api runners` 返回 `status=online`，证明 F.2 后链路真持续）

四项全满足 → 才说 "F.2 done"。

---

## 附录 A：T0-T5 命令清单（执行用）

### T0 — Precondition 自检（PC1-PC7）

```powershell
# PC1
gh auth status

# PC2
([Security.Principal.WindowsPrincipal]([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")

# PC3
Get-ScheduledTask -TaskName 'GitHub Actions Runner (sw-smoke)' |
  Select-Object TaskName, State

# PC4 — Autologon 目标账户（用 Get-ItemProperty 比 reg query 简洁）
(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon').DefaultUserName
# 期望返回单值字符串 'ghrunner'

# PC5
Test-Path D:\actions-runner\.runner

# PC6
gh api user --jq .login

# PC7 — baseline 记录 + 持久化（关键，修 holistic 终审 BLOCKER）
# reboot 摧毁所有 PS session 内变量；必须 Export-Clixml 到磁盘文件
# 否则 T1 重开 admin PS 后 $rebootTime = $null，PowerShell 5.1 中
# [DateTime] -gt $null 返 $true → C2 / C3 假阳性 PASS

$rebootTime = Get-Date
$rebootTimeStr = $rebootTime.ToString("yyyy-MM-dd HH:mm:ss")
Write-Host "reboot_time baseline: $rebootTimeStr"

$baselineRunner = gh api repos/proecheng/cad-spec-gen/actions/runners |
                  ConvertFrom-Json |
                  Select-Object -ExpandProperty runners |
                  Where-Object { $_.name -eq 'procheng-sw-smoke' }
Write-Host "baseline runner status: $($baselineRunner.status), id: $($baselineRunner.id)"

# 强制约束：baseline status 必须 = offline，否则 T2 transition 检测失效
if ($baselineRunner.status -ne 'offline') {
  Write-Error "PC7 FAIL: baseline runner status = $($baselineRunner.status)，期望 offline。先停 runner 再开 F.2。"
  exit 1
}

# 持久化到磁盘（跨 reboot 关键）
$baseline = @{
  reboot_time   = $rebootTime
  runner_status = $baselineRunner.status
  runner_id     = $baselineRunner.id
}
$baselinePath = 'D:\actions-runner\f2-baseline.xml'
$baseline | Export-Clixml $baselinePath
Write-Host "baseline persisted to: $baselinePath"
```

### T1 — Task Scheduler 状态 + daemon 进程

```powershell
# 关键第一步：从磁盘加载 PC7 baseline（reboot 后新 PS session 必须重新 import）
$baselinePath = 'D:\actions-runner\f2-baseline.xml'
if (-not (Test-Path $baselinePath)) {
  Write-Error "T1 ABORT: baseline file 不存在 ($baselinePath)，PC7 没跑或 reboot 前未持久化。"
  exit 1
}
$baseline = Import-Clixml $baselinePath
$rebootTime = $baseline.reboot_time
$baselineRunner = @{ status = $baseline.runner_status; id = $baseline.runner_id }
Write-Host "loaded baseline: reboot_time=$rebootTime / runner=$($baselineRunner.status)/$($baselineRunner.id)"

# Task Scheduler 视角
$taskInfo = Get-ScheduledTaskInfo -TaskName 'GitHub Actions Runner (sw-smoke)'
Write-Host "LastRunTime: $($taskInfo.LastRunTime) | LastTaskResult: $($taskInfo.LastTaskResult)"
Write-Host "C2 判据：LastRunTime > reboot_time ? $($taskInfo.LastRunTime -gt $rebootTime)"
Write-Host "C2 判据：LastTaskResult == 267009 ? $($taskInfo.LastTaskResult -eq 267009)"

# daemon 视角
$listener = Get-Process -Name Runner.Listener -ErrorAction SilentlyContinue
if ($listener) {
  Write-Host "Runner.Listener PID=$($listener.Id) StartTime=$($listener.StartTime)"
  Write-Host "C2 判据：StartTime > reboot_time ? $($listener.StartTime -gt $rebootTime)"
} else {
  Write-Warning "Runner.Listener 进程不存在 → C2 FAIL"
}
```

### T2 — runner 上线轮询（与 baseline 对照）

```powershell
$max = 12
for ($i = 1; $i -le $max; $i++) {
  try {
    $apiOut = gh api repos/proecheng/cad-spec-gen/actions/runners
    if (-not $apiOut) {
      Write-Warning "[$i/$max] gh api empty output, retry"
      Start-Sleep -Seconds 15; continue
    }
    $r = $apiOut | ConvertFrom-Json |
         Select-Object -ExpandProperty runners |
         Where-Object { $_.name -eq 'procheng-sw-smoke' }
    Write-Host "[$i/$max] status=$($r.status) busy=$($r.busy) (baseline was: $($baselineRunner.status))"
    if ($r.status -eq 'online' -and $baselineRunner.status -eq 'offline') {
      Write-Host "C3 PASS: runner transitioned offline→online"
      break
    }
    if ($r.status -eq 'online' -and $baselineRunner.status -eq 'online') {
      Write-Warning "stale heartbeat 风险（baseline 已 online），等下一轮变化"
    }
  } catch {
    Write-Warning "[$i/$max] gh api error: $_"
  }
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
# 退出码 0 → conclusion=success；非 0 → conclusion=failure，进 §3.3 二分
```

### T5 — 抓证据

```powershell
# workflow 维度
gh run view $runId --json databaseId,url,createdAt,updatedAt,conclusion,jobs |
  ConvertFrom-Json | Format-List

# host_fingerprint
$hostInfo = "{0} / Windows 11 build {1}" -f $env:COMPUTERNAME, (Get-WmiObject -Class Win32_OperatingSystem).BuildNumber
Write-Host "host_fingerprint: $hostInfo"

# runner_version：注意 .runner 文件不含 agentVersion 字段（实测仅有
# agentId/agentName/poolId/serverUrl/workFolder 等）。版本来自 Listener exe 的 ProductVersion，
# 或 install zip 文件名（如 actions-runner-win-x64-2.333.1.zip）。
$runnerVersion = (Get-Item D:\actions-runner\bin\Runner.Listener.exe).VersionInfo.ProductVersion
Write-Host "runner_version (from Runner.Listener.exe): $runnerVersion"
# 兜底：列出 install zip 文件名
Get-ChildItem D:\actions-runner -Filter 'actions-runner-win-x64-*.zip' |
  Select-Object -ExpandProperty Name

# 可选：下载 sw-smoke artifact 到本地（含 sw-inspect-deep.json + sw-smoke-junit.xml）
# 仅 PASS pickup-only / FAIL 时建议跑，常规 PASS clean 不需要
# gh run download $runId --name sw-smoke-artifacts --dir .\f2-evidence-$runId
```

---

## 附录 B：变更影响清单

| 文件 | 变更性质 | 来自 |
|---|---|---|
| `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` | §7 追加 F.2 段（PASS clean / PASS pickup-only / FAIL）| §5.1 |
| `memory/solidworks_asset_extraction.md` | F.2 bullet 改写 | §5.4 |
| `memory/MEMORY.md` | description 摘掉 "剩余 F.2" | §5.4 |
| `docs/superpowers/specs/2026-04-18-sw-runner-f2-design.md` | 本 spec（v2 含 5 角色审查修订）| 本文件 |
| `docs/superpowers/plans/2026-04-18-sw-runner-f2.md` | 实施计划（writing-plans 阶段建）| 下一步 |

不变更（明确）：

- `setup-runner-task.ps1`（保持 untracked，按 Q3 拆出独立 chore）
- `.claude/settings.local.json`（drift 无关）
- `sw-smoke.yml` / `setup-cad-env/action.yml` / `tools/sw_inspect.py`
- `decisions.md`（F.2 非决策）
- `tests/test_sw_inspect_real.py`（不加 toolbox 业务断言，推迟 F-1.3h）
