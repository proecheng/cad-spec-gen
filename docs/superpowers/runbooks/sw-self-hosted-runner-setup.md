# SW self-hosted runner setup runbook

承接决策 #39 / F-1.3 实施。本文档是**开发者物理配置 runner 的 SOP**，
与 workflow YAML 等代码改动分离。

---

## 1. 前置要求

- Windows 11（21H2+）
- SolidWorks 2024+ 持久授权（非网络浮动；若是浮动许可，见第 8 节）
- 机器可联网（runner 需与 github.com 保持 TLS 连通）
- Python 3.12 预装（或允许 workflow 里 `actions/setup-python@v6` 在线下载）
- **Git for Windows 已安装**（提供 Git Bash 给 workflow 里 `shell: bash` 的
  step 使用；T3 code review 指出这是 self-hosted 场景下与 GitHub-hosted
  `windows-latest` 镜像的关键差异点）。验证：
  ```powershell
  where.exe bash
  # 预期输出 C:\Program Files\Git\bin\bash.exe（或等价路径）
  # 若仅返回 scoop/chocolatey 的 git.exe 路径不含 bash.exe，需重装完整 Git for Windows
  ```
- **gh CLI ≥ 2.20**（验证：`gh --version`；F-1.3j+k 的 runner Idle 检查 + workflow_dispatch 触发 + artifact 下载链路依赖此版本）

## 2. 创建 `ghrunner` 账户

以管理员身份启动 PowerShell：

```powershell
net user ghrunner "<强密码>" /add
net localgroup Users ghrunner /add
# 确认 ghrunner 不在 Administrators 组：
net localgroup Administrators
```

收敛权限：

**1. 禁用 RDP 访问**（防止外网 brute-force 拿 ghrunner 的 shell）

Windows 11 Pro / Enterprise — `gpedit.msc` 路径：

```
Win+R → gpedit.msc → 回车
→ Computer Configuration
  → Windows Settings
    → Security Settings
      → Local Policies
        → User Rights Assignment
          → Deny log on through Remote Desktop Services
            → Properties → Add User or Group... → ghrunner → OK
```

Windows 11 Home（无 `gpedit.msc`）替代方案：

```powershell
# 以管理员身份在 PowerShell 跑。Home 版需手动 edit secedit 策略：
secedit /export /cfg $env:TEMP\secpol.cfg
# 打开 $env:TEMP\secpol.cfg，找到 SeDenyRemoteInteractiveLogonRight 这行
# 追加 ghrunner 的 SID（用 `whoami /user` 先查 ghrunner SID，或用账户名）
secedit /configure /db $env:WINDIR\security\local.sdb /cfg $env:TEMP\secpol.cfg /areas USER_RIGHTS
```

若 Home 版 secedit 也不顺利 — 至少确保 ghrunner 账户**无 admin 权限 + 密码强**，此时即使 RDP 可达，攻击者拿到的也是受限 shell（降级但可接受）。

**2. 文件系统隔离**（防 ghrunner 读到开发者个人文件）

```powershell
# 拒绝 ghrunner 对开发者主目录的读写：
icacls C:\Users\proecheng /deny "ghrunner:(OI)(CI)(R,W,D)"
# 验证：
icacls C:\Users\proecheng | findstr ghrunner
```

或图形界面：资源管理器右键 `C:\Users\proecheng` → Properties → Security → Edit → Add ghrunner → 勾选 Deny column 的 Read / Write / Modify。

## 3. 开机自动登录配置

**不**用注册表明文 `DefaultPassword`（物理接触者可直接读）。用 Sysinternals **Autologon** 工具（LSA-encrypted 存储）：

1. 下载 https://learn.microsoft.com/en-us/sysinternals/downloads/autologon
2. 以管理员身份运行 `Autologon.exe`
3. Username = `ghrunner`、Domain = `.`、Password = 第 2 节设置的密码
4. Enable

验证：重启机器，应自动登录到 ghrunner 桌面。

## 4. 下载并安装 GitHub Actions Runner

1. GitHub → repo Settings → Actions → Runners → New self-hosted runner → Windows x64
2. **先以管理员身份预建 `D:\actions-runner` 并授权 ghrunner**（否则标准用户 ghrunner 后续 extract 会 Access Denied）：
   ```powershell
   New-Item -ItemType Directory -Force D:\actions-runner
   icacls D:\actions-runner /grant "ghrunner:(OI)(CI)M"
   ```
3. 按页面给出的 PowerShell 命令下载 + 解压到 `D:\actions-runner`
4. 校验 SHA256：
   ```powershell
   Get-FileHash -Algorithm SHA256 actions-runner-win-x64-*.zip
   # 对比 GitHub 页面给出的 expected SHA256
   ```

## 5. 注册 runner（long-lived，D4）

以 `ghrunner` 账户登录（**非管理员** PowerShell），在 `D:\actions-runner` 跑一行命令（PowerShell 续行符 `` ` `` 后不能有空格，建议直接一行）：

```powershell
cd D:\actions-runner
.\config.cmd --url https://github.com/proecheng/cad-spec-gen --token <one-time-registration-token> --labels solidworks --replace
```

注意：
- **不**加 `--ephemeral`（D4：ephemeral 需要长期 PAT 自动重注册，破坏账户隔离）
- token 从"New self-hosted runner"页面复制，1 小时有效
- `--labels solidworks` 必填；另两个 label `self-hosted` / `Windows` GitHub 自动附加
- `--replace`：首次注册可省；重注册（§9 轮换）必加；**多 runner 场景禁用**（会清掉同名 runner）

### SW 用户数据隔离

首次在 ghrunner session 启动 SolidWorks：
- `File → Options → Reset All` 清掉可能从 proecheng 继承的默认设置
- 或手动删除 `C:\Users\ghrunner\AppData\Roaming\SolidWorks\`（首启会重建）

## 6. Task Scheduler 自动启动

`Task Scheduler → Create Task`（不是 Create Basic Task）：

- General
  - Name: `GitHub Actions Runner (sw-smoke)`
  - Run only when user is logged on（**不**勾 Run whether user is logged on or not，这等价于 Service 模式）
  - Configure for: Windows 11
- Triggers
  - New → Begin the task: `At log on` → Specific user: `ghrunner`
- Actions
  - New → Program: `D:\actions-runner\run.cmd`
  - Start in: `D:\actions-runner`
- Conditions
  - 取消勾选 "Start the task only if the computer is on AC power"
- Settings
  - If the task fails, restart every: `1 minute`, up to `3` times

保存，提示输入 ghrunner 密码。

## 7. 首次跑 sw-smoke 验证

1. GitHub repo → Actions → sw-smoke → Run workflow（workflow_dispatch）
2. 观察 Actions 页：runner 应 pickup job 并跑完
3. 下载 `sw-smoke-artifacts`：
   - `sw-smoke-junit.xml`：workflow skip-guard 硬门槛 `real >= 1`；当前 testcase 总数为 2（`test_fast_real_smoke` + `test_deep_real_smoke`），首跑 baseline 期望 `skipped == 0, real == 2`
   - `sw-inspect-deep.json`：记录 `layers.dispatch.data.elapsed_ms` 作为 K1 第一个数据点
4. CI 页 Job Summary 区块应直接显示 sw-inspect text 输出（D16 / §4.7）

**baseline 记录**（F-1.3 首跑 run 24554801242）：

- 首跑日期：**2026-04-17**
- junit：`total=2 skipped=0 real=2`（`test_fast_real_smoke` + `test_deep_real_smoke` 双 PASS）
- `sw-inspect-deep.json.overall.elapsed_ms`：**8349 ms**（端到端）
- `sw-inspect-deep.json.layers.dispatch.data.elapsed_ms`：**5492 ms**（SW COM Dispatch 冷启——K1 第一个数据点）
- `sw-inspect-deep.json.layers.toolbox_index.data.entry_count`：**1844**（19 standards）
- `sw-inspect-deep.json.layers.materials.data.sldmat_files`：**6**
- CI 总耗时：57s（pytest ~6s + sw-inspect emit ~8s + setup/artifact ~43s）
- runner 配置：procheng session（F.1 手工启动），F.2 完整生产链路验证（重启 + Autologon + Task Scheduler）待后续

**F.2 完整生产链路验收记录**（2026-04-18，PASS pickup-only，run 24598627853）：

**状态：→ 2026-04-18 F-1.3j+k AC-3 间歇性 fail（5 点 2/5 越界，触发 F-1.3l 根因调查）；状态保留 PASS pickup-only，等 F-1.3l 关闭后再升级 PASS clean**

- 验收日期：**2026-04-18**
- 触发方式：手动 `gh workflow run sw-smoke.yml --ref main`（workflow_dispatch）
- run URL：https://github.com/proecheng/cad-spec-gen/actions/runs/24598627853
- host_fingerprint：`CC-PC` / Windows 11 build 26200
- runner_version：`2.333.1`（来自 `D:\actions-runner\bin\Runner.Listener.exe` ProductVersion；install zip = `actions-runner-win-x64-2.333.1.zip`）
- 链路检查点：
  - **C1 Autologon**：PASS（用户肉眼确认 ghrunner 桌面自动登入；含 P2.5 等 30s）
  - **C2 Task Scheduler + daemon**：PASS（LastRunTime=`2026-04-18 14:03:05`，LastTaskResult=`267009`，Runner.Listener PID=`12180` StartTime=`2026-04-18 14:03:15`）
  - **C3 runner online**：PASS（runner `procheng-sw-smoke` 在 ghrunner 登录后 <15s status=online，T2 iter 1/12 即命中 baseline offline→online transition）
  - **C4 workflow pickup + run**：**PASS pickup-only**（dispatch → pickup `5s`，但 conclusion=failure；jobs[0].startedAt=`06:14:43Z` 非 null，pickup 层 OK，workflow 内部 step 红）
- 失败 step 详情：
  - step name：`Run actions/checkout@v6`（step #2）
  - failure 类型：self-hosted runner workspace 残留 `.pytest_cache` 目录有 EPERM scandir 锁
  - failure log 摘要：
    ```
    warning: could not open directory '.pytest_cache/': Permission denied
    warning: failed to remove .pytest_cache/: Directory not empty
    ##[warning]Unable to clean or reset the repository. The repository will be recreated instead.
    ##[error]File was unable to be removed Error: EPERM: operation not permitted, scandir
    'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'
    ```
  - 后续 skipped steps：`Setup CAD env (composite)` / `Run SW real smoke (pytest 回归)` / `Skip-guard (ET-based, D10)` / `Emit sw-inspect JSON artifact` / `upload-artifact@v4` 全部 skipped
- 与 F.1 对比：CI 总耗时 `30s`（F.1=57s，因 checkout 失败提前结束）；K1 dispatch.elapsed_ms **不可获取**（workflow 未跑到 sw-inspect step），需作为 follow-up 单独再跑；pickup_latency=`5s` 优于 F.1 baseline（含真 SW Dispatch 冷启 5492ms）
- 结论：**F-1.3 Phase F.2 PASS pickup-only**，自动化生产链路端到端通（reboot → Autologon → Task Scheduler → run.cmd → GitHub online → workflow pickup 5s 全 OK），但 sw-smoke workflow 内部 actions/checkout 失败需独立排查
- **必须立即另起 follow-up**（runbook §10 backlog 候选 / GitHub issue / 项目 todo）：
  - **F-1.3j**（新建）：清理 `D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache` workspace 锁；考虑给 sw-smoke.yml 加 pre-checkout cleanup step（admin PS `Remove-Item -Recurse -Force`），或用 `clean: false` 跳过 git clean 步骤
  - **F-1.3k**（新建）：F.2 K1 baseline 补点 — workspace 修复后单独 re-dispatch sw-smoke 一次拿 sw-inspect-deep.json 的 dispatch.elapsed_ms（与 F.1 5492ms 对照）
- **推 main 风险**：**HIGH**（CI 会 checkout 失败），未修 F-1.3j 前**不要推 main**
- F.2 后状态：runner long-lived 在线（Listener PID=12180）；下次 push main 会自动触发但会因 workspace 锁失败；当日有效，token 90 d 轮换 / Windows 大版本升级后须复跑 F.2

**F-1.3j workspace ACL 修复 + F-1.3k K1 第二数据点**（2026-04-18，AC-3 间歇性 fail / state kept at PASS pickup-only）：

- 修复日期：2026-04-18
- 根因：F.1 baseline 跑（procheng admin session）创建的 `.pytest_cache` 持有 protected ACL（仅 Owner/Admin/SYSTEM Full，无 ghrunner 条目且不继承），F.2 切到 ghrunner 身份后 `git clean -ffdx` 无权 scandir 触发 EPERM
- 一次性手工 fix：admin PowerShell `Remove-Item -Recurse -Force` 清掉 `D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache` + 所有 `__pycache__` 残留
- 防御性变更：`.github/workflows/sw-smoke.yml` 在 `actions/checkout@v6` 之前新增 `Pre-checkout workspace cleanup` step（pwsh / best-effort / `$env:GITHUB_WORKSPACE` 三重守卫 / SW 残留进程清理 + `::warning::cleanup_residual` annotation）
- 衍生修复：`Emit sw-inspect JSON artifact` 删 `|| true`（修 AC-2 fail-fast 击穿）/ skip-guard 由 `real >= 1` 加严到 `real == 2`（修 AC-4 自动化）
- 验证 run（workflow_dispatch，K1 新数据点）：
  - run-B 24605253673：https://github.com/proecheng/cad-spec-gen/actions/runs/24605253673
  - run-C 24605350467：https://github.com/proecheng/cad-spec-gen/actions/runs/24605350467
  - K4 24605595945：https://github.com/proecheng/cad-spec-gen/actions/runs/24605595945
  - K5 24605597487：https://github.com/proecheng/cad-spec-gen/actions/runs/24605597487

**AC 验收结果**：

- AC-1 conclusion: ✅ success（4 个 run 全 success）
- AC-2 schema fail-fast: ✅（assert_sw_inspect_schema.py exit=0，含 `layers.dispatch.data.elapsed_ms`）
- AC-2.5 materials 业务承诺: ✅ `layers.materials.data.sldmat_files = 6` (> 0) — 4 个 run 全一致
- AC-3 K1 第二数据点：**❌ 间歇性 fail**（5 点 2/5 越界下沿；attached_existing_session=false 全程成立）
  - 数据点 cluster 分析：

    | run | event | elapsed_ms | 距前一 run | AC-3 [3000, 15000] |
    |---|---|---|---|---|
    | F.1 baseline | push | 5492 | — | ✅ |
    | run-B (本次) | dispatch | 306 | SW 物理退出 ~8min | ❌ 越界下沿 |
    | run-C (本次) | dispatch | 314 | run-B + 5min | ❌ 越界下沿 |
    | K4 (本次) | dispatch | 3295 | run-C + 14min | ✅ |
    | K5 (本次) | dispatch | 3295 | K4 + 1min 串行 | ✅（与 K4 bit-exact） |

  - 假设（待 F-1.3l 验证）：触发条件与 **recent physical SW activity** 相关；物理 SW 退出 < ~15min 内，dispatch 走某种浅层路径跑出 ~310ms，即使 `attached_existing_session=false`；超过 ~15min 后回到 ~3295ms 正常冷启
  - Δ vs F.1 baseline 5492ms：{-94.4%, -94.3%, -40.0%, -40.0%}
- AC-4 junit: ✅ total=2 skipped=0 real=2（4 个 run 全一致，workflow skip-guard 自动断言）
- AC-5 文档同步: ✅ 本块 + F.2 状态升级行 + §1 gh CLI 前置 + §8.3 自动化补充

**F.2 §0.2 八条承诺复核**（机械设计师消费视角）：

承诺侧：
- [x] 链路层 — runner 自启动 OK，workflow_dispatch 触发 pickup 秒级
- [x] schema 回归 — `assert_sw_inspect_schema.py` PASS，sw-inspect JSON v1 字段不漂
- [x] materials 业务回归 — `layers.materials.data.sldmat_files = 6 > 0`（test_deep_real_smoke 已断言）
- [ ] **运行时回归 — ❌ 真 SW Dispatch elapsed_ms 间歇性越界下沿**（run-B/C 306/314ms vs F.1 5492ms），F-1.3l 调研中

不承诺侧（不变）：
- [ ] toolbox 业务层回归 ❌ 未在 sw-smoke 内（F-1.3h 待办）
- [ ] STEP 转换正确性 ❌ 未跑 sw-warmup / Stage C
- [ ] 永久有效 ❌ 90 天 token 轮换 + Windows / SW 升级须复验
- [ ] 跨机器 ❌ F.2 仅本机 procheng-sw-smoke 验证

**后续状态**：runner long-lived 在线，sw-smoke 重新进入 ready-for-merge 状态（AC-1/2/2.5/4 绿，AC-3 间歇性 fail 不阻断日常 merge — 触发条件罕见）。

❌ **F.2 状态保留 PASS pickup-only**（未升级到 PASS clean，因 AC-3 间歇性 fail 未闭环）；F-1.3l 关闭 + 至少 6 个数据点一致落在 [3000, 15000] 区间后升级

---

**F-1.3l follow-up — dispatch.elapsed_ms 双峰分布根因调查**（2026-04-18 起触发）：

- **现象**：K1 5 点数据 `{5492, 306, 314, 3295, 3295}`，呈双模态分布（~310ms cluster + ~3295ms cluster + 孤立 5492ms）；后续 cluster 切换与最近一次物理 SW 活动时间间隔相关（<15min → ~310ms / >15min → ~3295ms）
- **关键事实**：两个 cluster 中 `attached_existing_session=false` 全程成立；所以不是 attach/cache 路径明面可判定
- **猜测路径**（F-1.3l spec 起草时验证）：
  1. SW license daemon idle timeout — 持久授权下某种 license context 有 ~15min 生命周期，超时后下次冷启需重 license check
  2. SW COM server registration cache — pywin32 Dispatch 路径在 COM registration 热时走 inline，冷时走 out-of-process
  3. Windows Defender 实时扫描 — 物理 SW 启动后 Defender scan cache 标记 SLDWORKS.exe 为 known-good，加速后续 launch
- **验证步骤**（F-1.3l plan 草案）：
  1. 在 sw_probe.py 里给 dispatch 阶段加 per-step timing（Dispatch / Revision / Visible=False / ExitApp 分别计时），重现 run-B/C 和 K4/K5 看哪一步差异
  2. 补充 `probe_dispatch` 的 SwInfo 数据：license session ID / COM registration age / Defender status
  3. 连续跑 10-20 次 dispatch，每次间隔 5min 递增（5/10/15/20/25min），确认 15min 阈值是否真实且单调
- **关闭条件**：
  - (a) 找到具体根因 + 文档化 → 若是预期行为，AC-3 区间调整为 `[100, 15000]` 保留上沿警示档
  - (b) 若是代码 bug（误走浅层 path）→ 修 sw_probe.py 让两种情况都跑完整 lifecycle
  - (c) F-1.3l spec + plan + 至少 6 个 K1 数据点一致落在新区间后关闭
- **优先级**：中 — AC-1/2/2.5/4 绿，日常 merge 不受影响；但 AC-3 未闭环 F.2 状态机卡在 PASS pickup-only

## 8. 故障排查

### 8.1 Runner offline

- Actions → Runners 页显示红点 → ghrunner session 未登录或 `run.cmd` 崩溃
- **先查 ghrunner 是否真的自动登录了**（Autologon 会被 Windows Update / LSA 重置 / 密码变更静默失效）：
  - 物理/远程到机器看屏幕；若停在登录画面 → Autologon 失效
  - 重跑 `Autologon.exe` 输密码 + Enable → 重启验证自动登录
- 若已登录但 runner 仍 offline：以 ghrunner 登录，检查 `D:\actions-runner\_diag\` 最新日志

### 8.2 SW Dispatch 失败

- 确认 runner **不**以 Service 身份跑（见第 6 节 "Run only when user is logged on"）
- 确认 ghrunner session 是交互式 GUI 会话（能手动启动 SolidWorks）

### 8.3 License 冲突（"SolidWorks is being used by..."）

如果 license 是 per-user：
- 合并前关闭你的 SW 实例，或 commit message 加 `[skip smoke]` / `[skip sw-smoke]`（D15）
- 持续冲突可在 Actions → sw-smoke → Disable workflow 临时关闭

**自动化补充**（F-1.3j+k 起）：sw-smoke `Pre-checkout workspace cleanup` step 已加 `Stop-Process SLDWORKS` 兜底 kill 残留进程（详见 F-1.3j+k 块 + spec §3.2 P2-O），处理人手动关 SW 与本自动化互补。

### 8.4 积压 queued job 清理

`gh run cancel` **不支持** `--all` flag（常见误记）。用显式 id 循环：

```powershell
# PowerShell（runner 主机原生）
gh run list --workflow=sw-smoke --status=queued --json databaseId --jq '.[].databaseId' | ForEach-Object { gh run cancel $_ }
```

或 bash：

```bash
gh run list --workflow=sw-smoke --status=queued --json databaseId --jq '.[].databaseId' | xargs -I{} gh run cancel {}
```

### 8.5 Network license / 浮动许可首次 smoke license swap

若 SW 是网络浮动许可，ghrunner 首次启动 SW 会与你的 session 争 license。
**本 F-1.3 不覆盖此场景**；若需支持，参考 SolidWorks Admin Portal 的 multi-seat
配置；或按 §8 F-1.3e 降级为本地跑路径。

## 9. 90 天 token 轮换 SOP

目的：控制 runner credential 泄漏窗口（虽 GitHub 无强制过期，手动轮换是最佳实践）。

**正确顺序**（避免 local `.credentials` 与 GitHub 端状态失步）：

1. **准备**：Settings → Actions → Runners → 选中本 runner → `...` → Remove → 页面会给出一次性 **removal token**（1h 有效）+ 对应的 `config.cmd remove --token` 命令。**暂不点** "I've removed it"
2. 以 ghrunner 登录，`D:\actions-runner`：
   ```powershell
   cd D:\actions-runner
   .\config.cmd remove --token <removal-token>
   # 预期 "Runner removed successfully"
   ```
3. 返回 GitHub UI 点 "I've removed it"（若条目已自动消失则跳过）
4. 在 repo Settings → Actions → Runners → New self-hosted runner 获取**新** registration token
5. 按 §5 重新注册（不需要重跑 Autologon / Task Scheduler / 目录权限准备）

**中途失败的回退**（例如 removal token 1h 已过期或 config.cmd 找不到）：

```powershell
# 强制本地清除 .credentials，让 runner 彻底脱绑
.\config.cmd remove --local
```

然后 GitHub UI 手工点 Remove，再从步骤 4 开始。

日历提醒：每 90 天跑一次。

## 10. 卸载

**顺序重要**（若先删 ghrunner 账户，Autologon 会引用不存在的用户导致下次开机登录回环）：

1. **先** Autologon.exe → Disable（清 LSA credential，防循环）
2. 获取一次性 removal token：Settings → Actions → Runners → 选中 runner → `...` → Remove（页面给出 token 和命令）
3. 以 ghrunner 登录执行：
   ```powershell
   cd D:\actions-runner
   .\config.cmd remove --token <removal-token>
   ```
4. Task Scheduler 删除 "GitHub Actions Runner (sw-smoke)"
5. 如不再需要 ghrunner 账户：`net user ghrunner /delete`
6. 重启验证：主账户能正常登录，无登录回环
