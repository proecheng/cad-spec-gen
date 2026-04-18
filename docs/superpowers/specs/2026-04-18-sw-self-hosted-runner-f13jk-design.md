# SW self-hosted runner F-1.3j workspace ACL 修复 + F-1.3k K1 第二数据点 设计

**承接**：决策 #39 / F-1.3 / Phase F.2（main@50f6a0c，F.2 PASS pickup-only，run 24598627853，已证实自启动链路 C1+C2+C3+C4-pickup 全 PASS，但 sw-smoke workflow 内部 `actions/checkout@v6` 因 `.pytest_cache` EPERM scandir 失败 → K1 第二数据点未拿到）

**关联文档**：

- F.1 spec：`docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md`
- F.2 spec：`docs/superpowers/specs/2026-04-18-sw-runner-f2-design.md`
- runbook：`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`（§7 F.2 段列出 F-1.3j / F-1.3k follow-up 必要）
- decisions：`docs/superpowers/decisions.md` #39（不新增 decision 号，本稿是 #39 运维 follow-up）

**澄清问答锁定**（brainstorming 5 轮 + 1 次现场诊断）：Q1=B（j+k 合并一 spec）/ Q2=B（先抓根因再设计 fix）/ Q3=A（立即现场 admin handle + icacls 诊断；现场证据替代了原计划的 Q4 fix-shape 假设题）/ Q4=B（一次性 admin fix + workflow pre-checkout 兜底 step）/ Q5=B（AC-3 dispatch.elapsed_ms ∈ [3000, 15000] ms 的合理波动区间）

---

## 1. 背景与根因

### 1.1 F.2 失败现象回顾

runbook §7 F.2 段已记录（2026-04-18，run 24598627853）：

```
warning: could not open directory '.pytest_cache/': Permission denied
warning: failed to remove .pytest_cache/: Directory not empty
##[warning]Unable to clean or reset the repository. The repository will be recreated instead.
##[error]File was unable to be removed Error: EPERM: operation not permitted, scandir
'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'
```

pickup 5s ✅ → checkout step ❌ → 后续 5 个 step 全 skipped（含 sw-inspect emit + schema assert + artifact upload）→ K1 第二数据点无数据。

### 1.2 诊断数据（2026-04-18，本稿 brainstorming Q3 现场抓取）

admin PowerShell on CC-PC 跑 `icacls` 对比 `.pytest_cache` 与其父目录 workspace 根：

| 路径 | ghrunner 权限 | 继承标记 |
|---|---|---|
| `D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\` | `(I)(OI)(CI)(M)` Modify | ✅ 有 `(I)` 继承 |
| `.pytest_cache\` | **无条目** | ❌ **无 `(I)`**，不继承 |
| `.pytest_cache\v\` | **无条目** | ❌ **无 `(I)`**，不继承 |

`.pytest_cache` 的 ACL 只含 3 项：`NT AUTHORITY\SYSTEM:(OI)(CI)(F)`、`BUILTIN\Administrators:(OI)(CI)(F)`、`OWNER RIGHTS:(OI)(CI)(F)`。**ghrunner 完全不在授权列表里，且不继承父目录**。

### 1.3 根因

F.1 首跑 baseline（runbook §7 明确："runner 配置：procheng session（F.1 手工启动）"）：
- runner 以 **procheng（Administrators 组成员）** 身份跑
- pytest 创建 `.pytest_cache` 时，OS 给目录设了 protected ACL（仅 Owner + Administrators + SYSTEM，不继承父 workspace 的 ACL）
- 具体机制：Windows admin 身份下某些 API 会创建 "unprotected-but-explicit-ACL" 目录，继承链断在这里

F.2 切换到 **ghrunner（Users 组，非 admin）** 身份长驻：
- `actions/checkout@v6` 内 `git clean -ffdx` 用 ghrunner 身份尝试递归删 `.pytest_cache`
- ghrunner **无 read 权限** → scandir EPERM → checkout 整步失败
- `clean: true` 的 recreate-workspace fallback 也因同一 EPERM 无法递归删除 → job 红

### 1.4 根因**不是**什么（排除清单，避免未来误诊）

| 曾经的假设 | 为什么不是 |
|---|---|
| SW COM subprocess 句柄泄漏 | 现场 scandir 目录无锁，所有子文件完整可读；进程列表也无 SLDWORKS/python 残留 |
| Windows Defender 实时扫描持锁 | Defender 锁是瞬态毫秒级，不会跨 24h 持续 |
| pytest tempdir 句柄未关闭 | LastWriteTime = 2026-04-17 16:09 是 F.1 baseline 时间，F.2 那次（2026-04-18）根本没新写入 |
| 文件 readonly 属性 | `Get-ChildItem` 看 Mode 全是 `-a----`，无 readonly/hidden/system |

---

## 2. 范围

### 2.1 本 spec 覆盖

- ✅ **F-1.3j**：一次性 admin 手工清掉 F.1 遗留的 protected-ACL `.pytest_cache` + 所有 `__pycache__` 残留
- ✅ **F-1.3j**：sw-smoke.yml 在 `actions/checkout@v6` 之前增加 `Pre-checkout workspace cleanup` step（pwsh / best-effort / 使用 `$env:GITHUB_WORKSPACE` 不绑定 runner 路径）
- ✅ **F-1.3k**：修复后 dispatch 一次 sw-smoke，采集 `dispatch.elapsed_ms` 作为 K1 第二数据点
- ✅ runbook §7 F.2 段**之后**追加"F-1.3j+k 修复记录 + K1 第二数据点"新块

### 2.2 不在范围

- ❌ **F-1.3a**（dashboard）/ **F-1.3b**（workflow_dispatch full input）/ **F-1.3c**（二号机 runner-group）/ **F-1.3d**（actionlint pre-commit）/ **F-1.3e**（降级路径）/ **F-1.3f**（K3 门槛）/ **F-1.3g**（tests.yml composite 迁移）/ **F-1.3h**（toolbox_index.by_standard 断言）/ **F-1.3i**（step summary consume JSON）—— runbook §10 各自独立 backlog
- ❌ **本地 ps1 脚本归属**（`pc7-baseline.ps1` / `setup-runner-task.ps1`）—— F.2 期间临时辅助脚本，独立 5 分钟决策（commit 进 `scripts/runner/` / `.gitignore` / 删）
- ❌ **decisions.md 新增决策号** —— 本稿是 #39 运维 follow-up，不新增编号
- ❌ **sw-warmup / Stage C 在 sw-smoke 内跑** —— F.2 spec §0.3 已明确 sw-smoke 承诺边界不含 STEP 转换正确性
- ❌ **SW Dispatch 性能回归深诊断** —— 若 AC-3 区间外（< 3s 或 > 15s），单独开 F-1.3l follow-up

---

## 3. 修复方案

### 3.1 P1 一次性手工 fix（admin PowerShell，一次）

以 proecheng（admin）身份在 PowerShell 执行（手抄 runbook 内命令，不写脚本）：

```powershell
# P1.1 验证污染目录存在（sanity check）
Test-Path 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'
# 期望：True

# P1.2 admin 强删（Administrators 组有 Full 权限，无视 protected ACL）
Remove-Item -Recurse -Force 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'

# P1.3 同时清掉可能的 __pycache__ 残留（同根因波及）
Get-ChildItem -Path 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen' `
              -Filter '__pycache__' -Recurse -Force -Directory -EA SilentlyContinue |
  Remove-Item -Recurse -Force

# P1.4 验证清空
Test-Path 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'
# 期望：False
```

**为什么不写成 ps1 脚本**：一次性动作，写脚本反而引入"哪天有人定时跑误删别的目录"的复发风险；手抄命令路径写死在 runbook 里，每次执行需人工核对路径，比脚本更安全。

**为什么不用 `icacls /grant`**：授权修复治标（给 ghrunner 补权限），删除修复治本（污染目录消失，下次由 ghrunner 重建时自然继承父 workspace 的 `ghrunner:(I)(M)` ACL，问题永不复发）。

### 3.2 P2 workflow 兜底 step（sw-smoke.yml）

在 `.github/workflows/sw-smoke.yml` 的 `actions/checkout@v6` step **之前**插入：

```yaml
      - name: Pre-checkout workspace cleanup (F-1.3j 防 protected-ACL 残留)
        shell: pwsh
        run: |
          $ws = $env:GITHUB_WORKSPACE
          if (-not $ws -or -not (Test-Path $ws)) {
            Write-Host "workspace not yet created, skip"
            exit 0
          }
          $cache = Join-Path $ws '.pytest_cache'
          if (Test-Path $cache) {
            Write-Host "Removing $cache (best-effort)"
            Remove-Item -Recurse -Force $cache -ErrorAction SilentlyContinue
            if (Test-Path $cache) {
              Write-Warning "still present after best-effort, will let checkout retry handle"
            }
          }
          Get-ChildItem -Path $ws -Filter '__pycache__' -Recurse -Force -Directory -EA SilentlyContinue |
            Remove-Item -Recurse -Force -EA SilentlyContinue
```

**关键设计决策**：

| 决策 | 取舍理由 |
|---|---|
| `shell: pwsh` 而非 `bash` | PowerShell `-EA SilentlyContinue` + `Test-Path` 语义比 bash `rm -rf 2>/dev/null` 更精确，失败容忍可控 |
| 用 `$env:GITHUB_WORKSPACE` 而非硬编码 `D:\actions-runner\_work\...` | 不绑死 runner 路径，将来若 runner 迁机 / 换盘符不破 |
| `if (-not Test-Path $ws)` 守卫 | 首次 checkout 前 workspace 不存在，避免 step 报错 |
| **best-effort 不 fail step** | 防御性 step 自身不能阻塞流程；若 ghrunner 也删不掉，让 `actions/checkout` 的 `clean: true` 走 recreate-workspace fallback 自行重建 |
| 不动 `clean: true` | 保留 git clean 语义，与 F.1 D4 long-lived runner 清场策略一致 |
| 不加 `if:` 条件 | 每次都跑，幂等 + 开销 < 1s（只 Test-Path + Remove-Item），不值得加条件节流 |

### 3.3 P3 K1 第二数据点采集

P1 + P2 完成并 merge 到 main 后，merge 事件自动触发 sw-smoke：

- 该次 run 的 `sw-inspect-deep.json` artifact 的 `layers.dispatch.data.elapsed_ms` 字段 = K1 第二数据点
- 与 F.1 baseline（run 24554801242，dispatch.elapsed_ms = 5492ms）对照

**不另起 workflow_dispatch**：merge 触发的 run 与 dispatch 触发的 run 对 K1 指标含义等价（都是真 SW COM 冷启动）；省一次 license 占用 + 57s 物理跑。

---

## 4. 验收标准（Q6 选 B）

| # | 检查项 | 通过标准 | 取值来源 |
|---|---|---|---|
| AC-1 | sw-smoke workflow 跑完 | `conclusion=success` | `gh run view <run-id>` / GitHub UI |
| AC-2 | sw-inspect-deep.json 字段完备 | 含 `layers.dispatch.data.elapsed_ms` 数值字段 | `tools/assert_sw_inspect_schema.py` step 自动 fail-fast；无需人工核 |
| AC-3 | dispatch 性能在合理区间 | `dispatch.elapsed_ms ∈ [3000, 15000] ms`（下限 3000ms 物理下限 / 上限 15000ms ≈ 2.7× F.1 baseline 5492ms） | 下载 artifact `sw-inspect-deep.json`，`jq .layers.dispatch.data.elapsed_ms` |
| AC-4 | junit 真测试覆盖 | `total=2 skipped=0 real=2` | workflow 内 Skip-guard step 已硬断言 `real >= 1`；AC-4 加严到 `real == 2` 需人工核 junit xml |
| AC-5 | runbook §7 同步 | F.2 段之后追加"F-1.3j+k 修复记录 + K1 第二数据点"块，含 P3 的 run URL + dispatch.elapsed_ms 数值 | git diff 核对 |

**AC-3 区间选择依据**：

- F.1 baseline N=1（5492ms）→ 本次 K1 第二数据点 N=2
- 统计意义弱（N<30 + 无 σ），不使用对称的 ±X% 窗口，而是物理下限 + 工程上限组合
- 窗口下限 **3000ms**：物理下限（真 SW COM Dispatch 至少需要 ~3s 加载 .dll + 初始化 COM 接口）；如果显著低于此值说明被 attach 而非冷启动，是隐性回归
- 窗口上限 **15000ms**（≈ 2.7× F.1 baseline）：超出说明有真 SW 性能回归 / Windows boot 异常 / 磁盘 I/O 异常，需单独 F-1.3l follow-up 排查

**AC-4 是对 F.1 skip-guard 的加严**：

- workflow 内 skip-guard 只 assert `real >= 1`（防 marker 全量 skip）
- AC-4 加严到 `real == 2`（`test_fast_real_smoke` + `test_deep_real_smoke` 双 PASS），手动核一次避免未来 marker 变更让单个测试静默被 skip

---

## 5. runbook §7 同步内容

在 `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` §7 现有 F.2 验收块**之后**追加新块：

```markdown
**F-1.3j workspace ACL 修复 + F-1.3k K1 第二数据点**（2026-04-18，PASS）：

- 修复日期：2026-04-18
- 根因：F.1 baseline 跑（procheng admin session）创建的 `.pytest_cache` 持有 protected ACL（仅 Owner/Admin/SYSTEM Full，无 ghrunner 条目且不继承），F.2 切到 ghrunner 身份后 `git clean -ffdx` 无权 scandir 触发 EPERM
- 一次性手工 fix：admin PowerShell `Remove-Item -Recurse -Force` 清掉 `D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache` + 所有 `__pycache__` 残留
- 防御性变更：`.github/workflows/sw-smoke.yml` 在 `actions/checkout@v6` 之前新增 `Pre-checkout workspace cleanup` step（pwsh / best-effort / 使用 `$env:GITHUB_WORKSPACE` 不绑定 runner 路径）
- 验证 run：<run URL 回填>
- AC-1 conclusion: success
- AC-2/3 K1 第二数据点：`dispatch.elapsed_ms = <数值> ms`（F.1 baseline = 5492ms 对照）
- AC-4 junit: total=2 skipped=0 real=2
- 后续状态：runner long-lived 在线，sw-smoke 重新进入 ready-for-merge 状态
```

---

## 6. 推 main 节奏

> **编号说明**：本节用 S1..S6（"step"）以避免与 §3.1-3.3 的 P1/P2/P3（fix work parts）混淆。S 与 P 不一一对应。

| 节点 | 动作 | commit 策略 | 触发 sw-smoke？ |
|---|---|---|---|
| S1 | admin PowerShell 跑 §3.1（P1 一次性 fix） | 不 commit（手工动作） | 否 |
| S2 | 改 sw-smoke.yml 加 §3.2（P2 cleanup step） | 1 commit on feature branch | 否（feature branch push 不触发） |
| S3 | 本地 `actionlint .github/workflows/sw-smoke.yml` | 不 commit（预检） | 否 |
| S4 | PR + merge to main | merge commit | **是**（merge 后自动触发，对应 §3.3 P3 数据采集） |
| S5 | 等 sw-smoke 跑完，核 AC-1..4 | 不 commit | — |
| S6 | runbook §7 回填 §5 新块（含 run URL + dispatch.elapsed_ms 数值） | 1 commit on main，message 末尾加 `[skip smoke]` | 否（[skip smoke] 跳过无意义触发） |

**关键设计决策**：

| 决策 | 取舍 |
|---|---|
| S2 不直接 push main | feature branch 过渡方便 S4 一次 review；虽然 sw-smoke 只监听 main 所以 push main 也 OK，但走 PR 保留审查轨迹 |
| S4 merge 即验证 | merge 自动触发的 sw-smoke 与 workflow_dispatch 触发对 K1 指标语义等价，省一次 SW 冷启 |
| S6 单独 commit 回填 runbook | 数据更新与代码变更解耦；`[skip smoke]` 避免纯文档 commit 触发 ~57s 物理跑 |

---

## 7. 风险与回滚

### 7.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| P1 admin Remove-Item 误删（手抄路径出错） | 低 | 中 | 命令前 `Test-Path` 验证；目标路径写死到 `.pytest_cache` 子目录，root 级别误删可能性低 |
| P4 merge 后 sw-smoke 仍红（fix 未根治） | 低 | 中 | 查 `actions/checkout@v6` step log 是否仍 EPERM；若 EPERM 消失但其他 step 红 → 问题不在本 spec 范围（独立排查） |
| AC-3 `dispatch.elapsed_ms` 越界（< 3s 或 > 15s） | 低 | 低 | < 3s 几乎不可能（物理下限）；> 15s 提示 SW Dispatch 真有回归或 Windows boot 异常，记 F-1.3l follow-up |
| 兜底 step 在 ghrunner 身份下也被 ACL 拒 | 中 | 低 | best-effort 已覆盖：silent fail 不阻塞，让 `actions/checkout` 的 recreate-workspace fallback 接管；AC-1 仍能 pass |
| P1 后短期内又有人手工跑 procheng admin pytest 污染 workspace | 极低 | 高（复发） | runbook §5 已规定 long-lived ghrunner；本 spec 不加额外约束（不值得为低概率事件加流程负担） |
| `$env:GITHUB_WORKSPACE` 在某些 runner 版本下未定义 | 极低 | 低 | step 内已 `if (-not $ws)` 守卫，未定义直接 skip（等价 no-op） |

### 7.2 回滚方案

| 失败场景 | 回滚动作 |
|---|---|
| P2 commit 导致 yaml 语法错 | `git revert <commit>`；P1 清掉的 workspace 不影响（下次跑会 recreate） |
| P4 merge 后 sw-smoke 持续红，排查需时间 | commit message 加 `[skip smoke]` / `[skip sw-smoke]`（D15 已存在）临时跳过；不阻塞其他 PR；同时开 F-1.3l follow-up |
| 极端（workflow 损坏无法临时跳过） | Settings → Actions → sw-smoke → Disable workflow（与 runbook §8.3 license 冲突应急路径相同） |

---

## 8. 非功能约束（N-要求）

| # | 约束 | 理由 |
|---|---|---|
| N-1 | P2 cleanup step 开销 < 1s | 只 Test-Path + Remove-Item，避免给 CI 总耗时（目前 ~57s）引入明显回归 |
| N-2 | P2 step 不引入对 ghrunner 的新权限要求 | 本稿明确不动 ACL（不 icacls /grant），ghrunner 权限面保持 runbook §2 现状 |
| N-3 | 本 spec 不改 F.2 基础工作（runner 注册 / Task Scheduler / Autologon） | F.2 PASS pickup-only 是既成事实，本稿只修 workflow 内部 step |
| N-4 | runbook §7 文字追加，不动 F.1/F.2 历史块 | 历史数据不可篡改，时间轴完整 |

---

## 9. 后续非本 spec follow-up

| 编号 | 描述 | 触发条件 |
|---|---|---|
| F-1.3l | 若 AC-3 越界（dispatch.elapsed_ms < 3s 或 > 15s），排查 SW Dispatch 性能回归 | AC-3 fail |
| ps1 整理 | `pc7-baseline.ps1` / `setup-runner-task.ps1` 决定 commit / gitignore / 删 | 独立 5 分钟决策 |
| F-1.3a | sw-smoke JSON artifact → dashboard（K1 ≥ 10 点时） | K1 累积到 10 点 |

---

## 10. 附录：诊断证据原始输出（brainstorming Q3 现场抓取）

```
$ icacls 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache'
.pytest_cache NT AUTHORITY\SYSTEM:(OI)(CI)(F)
              BUILTIN\Administrators:(OI)(CI)(F)
              OWNER RIGHTS:(OI)(CI)(F)

$ icacls 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen'
cad-spec-gen  CC-PC\ghrunner:(I)(OI)(CI)(M)          ← 父有 ghrunner:(M)
              BUILTIN\Administrators:(I)(F)
              BUILTIN\Administrators:(I)(OI)(CI)(IO)(F)
              NT AUTHORITY\SYSTEM:(I)(F)
              NT AUTHORITY\SYSTEM:(I)(OI)(CI)(IO)(F)
              NT AUTHORITY\Authenticated Users:(I)(M)
              NT AUTHORITY\Authenticated Users:(I)(OI)(CI)(IO)(M)
              BUILTIN\Users:(I)(RX)
              BUILTIN\Users:(I)(OI)(CI)(IO)(GR,GE)

$ icacls 'D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache\v'
v NT AUTHORITY\SYSTEM:(I)(OI)(CI)(F)               ← 子目录继承（I）但仍无 ghrunner
  BUILTIN\Administrators:(I)(OI)(CI)(F)
  OWNER RIGHTS:(I)(OI)(CI)(F)
```

对照点：父目录有 `ghrunner:(I)(M)` 条目 + `(I)` 标记表示正常继承；`.pytest_cache` 完全没有 `ghrunner` 条目也没有 `(I)`（ACL 链断在这里）。

目录时间戳：`LastWriteTime: 2026/4/17 16:09:38` → 对应 F.1 baseline run 24554801242（2026-04-17 首跑），不是 F.2 失败（2026-04-18）产生的新文件。

---

**版本记录**：v1 初稿（brainstorming 6 轮 Q&A + 现场诊断后）
