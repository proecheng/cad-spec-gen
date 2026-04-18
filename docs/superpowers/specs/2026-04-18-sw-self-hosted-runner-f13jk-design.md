# SW self-hosted runner F-1.3j workspace ACL 修复 + F-1.3k K1 第二数据点 设计

**承接**：决策 #39 / F-1.3 / Phase F.2（main@50f6a0c，F.2 PASS pickup-only，run 24598627853，已证实自启动链路 C1+C2+C3+C4-pickup 全 PASS，但 sw-smoke workflow 内部 `actions/checkout@v6` 因 `.pytest_cache` EPERM scandir 失败 → K1 第二数据点未拿到）

**关联文档**：

- F.1 spec：`docs/superpowers/specs/2026-04-17-sw-self-hosted-runner-design.md`
- F.2 spec：`docs/superpowers/specs/2026-04-18-sw-runner-f2-design.md`
- runbook：`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`（§7 F.2 段列出 F-1.3j / F-1.3k follow-up 必要）
- decisions：`docs/superpowers/decisions.md` #39（不新增 decision 号，本稿是 #39 运维 follow-up）

**澄清问答锁定**（brainstorming 5 轮 + 1 次现场诊断）：Q1=B（j+k 合并一 spec）/ Q2=B（先抓根因再设计 fix）/ Q3=A（立即现场 admin handle + icacls 诊断；现场证据替代了原计划的 Q4 fix-shape 假设题）/ Q4=B（一次性 admin fix + workflow pre-checkout 兜底 step）/ Q5=B（AC-3 dispatch.elapsed_ms 的合理波动区间，端点与 attached 守卫见 v2 §4）

**审查修订记录**：

- v1：初稿（brainstorming 5 轮 Q&A + 1 次 admin icacls 现场诊断后）
- **v2（本稿）**：5 角色 adversarial 审查（系统分析师 / 系统架构师 / 3D 设计师 / 软件测试员 / 机械设计师）一致 REVISE，6 触类 P1 + 6 项高价值 P2 + 2 项 P1 衍生共 14 项合入：
  - **P1-A 状态机/触发等价**（架构师+机械）：§3.3 改用 workflow_dispatch + 显式声明 F.2 pickup-only → clean 升级判据
  - **P1-B AC-3 实现矛盾**（3D，已实证 sw_probe.py:572 attached 硬编码 elapsed_ms=0）：AC-3 加 `attached_existing_session == false` 守卫
  - **P1-C materials 隐式承诺**（3D）：新增 AC-2.5 `materials.sldmat_files > 0`
  - **P1-D composite 漂移 + GITHUB_WORKSPACE 假设**（架构师）：§3.2 加可选 composite 抽取选项 + 守卫强化
  - **P1-E AC-2 fail-fast 击穿**（测试员，已实证 sw-smoke.yml:59 `\|\| true`）：新增 §3.4 删 `\|\| true`
  - **P1-F AC-4 无 automated**（测试员）：新增 §3.4 改 skip-guard `real == 2`
  - **P1 衍生 G/H**（分析师）：§3.2 决策表补 `clean: false` 拒绝行 / runbook 模板加 K1 区间合规判读
  - **P2 高价值**：silent-fail 加 `::warning::` annotation（L）/ pre-cleanup 加 Stop-Process SLDWORKS（O）/ §2.2 cleanup 范围白名单（P）/ AC-3 写闭区间 `>=,<=`（Q）/ §9 加 dry-run task（R）/ runbook 模板加 F.2 §0.2 八条承诺复核行（T）

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

> **本 spec 在 F.2 spec §10 backlog 编号对应**：F-1.3j（workspace cleanup）+ F-1.3k（K1 第二数据点）；不新增 decision 号，是 #39 运维 follow-up（U：机械设计师跨 spec 时间轴可读性诉求）

### 2.1 本 spec 覆盖

- ✅ **F-1.3j**：一次性 admin 手工清掉 F.1 遗留的 protected-ACL `.pytest_cache` + 所有 `__pycache__` 残留
- ✅ **F-1.3j**：sw-smoke.yml 在 `actions/checkout@v6` 之前增加 `Pre-checkout workspace cleanup` step（pwsh / best-effort / 使用 `$env:GITHUB_WORKSPACE` 不绑定 runner 路径，含 SW 残留进程清理 + GitHub workflow command annotation）
- ✅ **F-1.3j 衍生 sw-smoke.yml 修复**（详见 §3.4）：删除 line 59 `|| true`（修复 P1-E）/ Skip-guard 断言由 `real >= 1` 加严到 `real == 2`（修复 P1-F）
- ✅ **F-1.3k**：修复后**通过 workflow_dispatch 显式触发**（不依赖 merge 自动触发，避免 GitHub webhook 路径假设；详见 §3.3）一次 sw-smoke，采集 `dispatch.elapsed_ms` 作为 K1 第二数据点
- ✅ runbook §7 F.2 段**之后**追加"F-1.3j+k 修复记录 + K1 第二数据点"新块（含 F.2 §0.2 八条承诺复核 checklist + K1 区间合规判读）
- ✅ **F.2 状态机升级**：本 spec 全 PASS 时，runbook §7 F.2 块的 "PASS pickup-only" 升级为 "PASS clean"（详见 §3.3）

### 2.2 不在范围

- ❌ **F-1.3a**（dashboard）/ **F-1.3b**（workflow_dispatch full input）/ **F-1.3c**（二号机 runner-group）/ **F-1.3d**（actionlint pre-commit）/ **F-1.3e**（降级路径）/ **F-1.3f**（K3 门槛）/ **F-1.3g**（tests.yml composite 迁移）/ **F-1.3h**（toolbox_index.by_standard 断言）/ **F-1.3i**（step summary consume JSON）—— runbook §10 各自独立 backlog
- ❌ **本地 ps1 脚本归属**（`pc7-baseline.ps1` / `setup-runner-task.ps1`）—— F.2 期间临时辅助脚本，独立 5 分钟决策（commit 进 `scripts/runner/` / `.gitignore` / 删）
- ❌ **decisions.md 新增决策号** —— 本稿是 #39 运维 follow-up，不新增编号
- ❌ **sw-warmup / Stage C 在 sw-smoke 内跑** —— F.2 spec §0.3 已明确 sw-smoke 承诺边界不含 STEP 转换正确性
- ❌ **SW Dispatch 性能回归深诊断** —— 若 AC-3 区间外或越上限警示档，单独开 F-1.3l follow-up
- ❌ **抽 cleanup 到 composite action** —— v2 评审建议（架构师 P1#2 part 1）但权衡为低优先级 follow-up（F-1.3m）：本 spec 内联实现 + 标注扩展点；composite 抽取与 F-1.3g（tests.yml 迁移）合并做更经济（详见 §3.2 决策表）

**Cleanup step 范围白名单（P：3D 设计师 P2#2 防止未来误删 sw-warmup 产物）**：

本 spec P2 cleanup step **仅**操作以下两类路径，**严禁扩展**到其他工作目录：

| 路径模式 | 处理 | 理由 |
|---|---|---|
| `<workspace>/.pytest_cache/` | 整目录 Remove-Item -Recurse -Force | 本 spec 唯一根因目标 |
| `<workspace>/**/__pycache__/` | 全树递归 Remove-Item | 同根因可能波及（同 protected-ACL 模式） |
| `<workspace>/_warmup_cache/` | **不动** | 未来 F-1.3b sw-warmup 中间产物 |
| `<workspace>/*.tmp.step` `<workspace>/*.step` | **不动** | sw-warmup / Stage C STEP 输出 |
| `<workspace>/artifacts/` | **不动** | sw_b9 / Stage C 报告产物 |
| 其他任何路径 | **不动** | 任何扩展须先开新 spec 评审 |

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
          # P2-O：兜底 kill SW 残留进程（防上一次跑异常退出留 SLDWORKS.exe 持锁，与 runbook §8.3 license 应急路径对齐）
          Get-Process SLDWORKS -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "Stopping orphan SLDWORKS PID=$($_.Id) StartTime=$($_.StartTime)"
            $_ | Stop-Process -Force -ErrorAction SilentlyContinue
          }

          # P2-D part 2：守卫强化 — workspace 未定义 / 空字符串 / 不存在 三种均跳过
          $ws = $env:GITHUB_WORKSPACE
          if (-not $ws -or $ws.Trim() -eq '' -or -not (Test-Path -LiteralPath $ws)) {
            Write-Host "workspace not yet created or undefined, skip"
            exit 0
          }

          # 仅清理 §2.2 白名单内路径
          $cache = Join-Path $ws '.pytest_cache'
          if (Test-Path -LiteralPath $cache) {
            Write-Host "Removing $cache (best-effort)"
            Remove-Item -Recurse -Force -LiteralPath $cache -ErrorAction SilentlyContinue
            # P2-L：silent-fail 可观测性 — 失败时发 GitHub workflow command annotation
            if (Test-Path -LiteralPath $cache) {
              Write-Host "::warning title=cleanup_residual::pre-checkout cleanup left .pytest_cache; ACL drift suspected; checkout fallback will attempt recreate"
            }
          }
          Get-ChildItem -Path $ws -Filter '__pycache__' -Recurse -Force -Directory -EA SilentlyContinue |
            Remove-Item -Recurse -Force -EA SilentlyContinue
```

**关键设计决策**：

| 决策 | 取舍理由 |
|---|---|
| `shell: pwsh` 而非 `bash` | PowerShell `-EA SilentlyContinue` + `Test-Path` 语义比 bash `rm -rf 2>/dev/null` 更精确，失败容忍可控 |
| 用 `$env:GITHUB_WORKSPACE` 而非硬编码 `D:\actions-runner\_work\...` | 不绑死 runner 路径，将来若 runner 迁机 / 换盘符不破；守卫强化后覆盖 undefined / empty / nonexistent 三种异常 |
| **拒绝备选 `clean: false`**（G：分析师 P1#1 决策记录）| runbook §7 F.2 段提了"用 `clean: false` 跳过 git clean"作为备选；本 spec 拒绝该方案，理由 = 与 F.1 D4 long-lived runner 清场策略冲突（不清场会持续累积 stale artifact），且 `clean: false` 只回避错误不修根因（首次失败仍会停留），cleanup step 一次开销 < 1s 远低于 stale artifact 调试时间 |
| **拒绝备选 `icacls /grant`** | 见 §3.1 末尾理由（治标 vs 治本） |
| **拒绝备选抽 composite action**（D part 1：架构师 P1#2 部分采纳）| F.1 D14 已建 `setup-cad-env` 范式；本 spec 选择内联实现 + §2.2 排除项 + §9 标注 follow-up F-1.3m，理由 = 单 step 抽 composite ROI 低（一次复用都没有，F-1.3g tests.yml 迁移触发时一并抽更经济）；当前 cleanup 内容固定不需 input/output 接口 |
| **best-effort 不 fail step** | 防御性 step 自身不能阻塞流程；若 ghrunner 也删不掉，让 `actions/checkout` 的 `clean: true` 走 recreate-workspace fallback 自行重建 |
| **silent-fail 可观测性**（L：3 角色合并）| best-effort 但**不静默** — 失败时通过 `::warning::` GitHub workflow command 在 Actions UI 顶部显示 annotation，避免长期失败被掩盖；连续失败可在 F-1.3l 触发条件里加"≥ 2 次连续 cleanup_residual annotation 升级 issue" |
| **SW 残留进程 pre-kill**（O：3D P2#1）| 在删 cache 前先 `Stop-Process SLDWORKS`，防 SW 异常退出留进程持锁 `__pycache__` 子文件 |
| 不动 `clean: true` | 保留 git clean 语义，与 F.1 D4 long-lived runner 清场策略一致 |
| 不加 `if:` 条件 | 每次都跑，幂等 + 开销 < 1.5s（只 Get-Process + Test-Path + Remove-Item），不值得加条件节流 |

### 3.3 P3 K1 第二数据点采集（v2 改用 workflow_dispatch）

**变更说明（A：架构师 P1#1 + 机械设计师 P1#1）**：v1 原计划用 merge to main 自动触发 sw-smoke 顺带采 K1，v2 改为**显式 workflow_dispatch 触发**。

P1 + P2 + §3.4 改动 merge 到 main 后，**手动**通过 GitHub UI（Actions → sw-smoke → Run workflow，ref=main）或 `gh workflow run sw-smoke.yml --ref main` 触发：

- 该次 run 的 `sw-inspect-deep.json` artifact 的 `layers.dispatch.data.elapsed_ms` 字段 = K1 第二数据点
- 与 F.1 baseline（run 24554801242，dispatch.elapsed_ms = 5492ms）对照

**为什么改 workflow_dispatch**：

| 原因 | 详细 |
|---|---|
| **触发等价性可论证**（机械 P1#1） | merge to main 走 `push` event，与 `workflow_dispatch` event 在 GitHub webhook 分发路径上不一定等价（protected branch / required reviewers / squash merge 时 head_commit 字段为合并提交而非原 commit），无法独立验证；workflow_dispatch 与 F.2 T3 / runbook §7 既有验证完全一致，**承袭已验证路径** |
| **F.2 §0.2 承诺 1 一致性**（机械 P1#1） | F.2 §0.2 承诺"链路层：runner 自启动 OK，下次 push main 自动 pickup" — 这条承诺在本 spec 不复验证（`push main` 自动触发与 `workflow_dispatch` 共享同一 runner / 同一 workflow，只在 GitHub event 入口分叉，本 spec 不引入新 runner 假设故承诺仍 hold） |
| **可控 + 显式** | 手动触发避免开发者意外 push（如纯文档 commit 不希望触发）的边界 case；与 §6 S6 `[skip smoke]` 形成"显式触发 + 显式跳过"的对称语义 |

**F.2 状态机升级声明（A：架构师 P1#1）**：

- F.2 spec §1.3 定义 "PASS pickup-only" 为非终态，runbook §7 F.2 段明确 "未修复前不要推 main"
- 本 spec 全 AC（AC-1..5）PASS 时，runbook §7 F.2 块的状态从 "PASS pickup-only" **升级为 "PASS clean"**
- **升级判据 = 本 spec AC-1..5 全 PASS** AND **F.2 段引用的 F-1.3j / F-1.3k follow-up 标注为 closed**
- 升级动作（详见 §5）：在 §7 F-1.3j+k 新块**末尾**追加一行 "🎉 F.2 → PASS clean，原 F.2 块 'PASS pickup-only' 状态正式升级"，并在 F.2 块开头加一行 "状态：→ 升级见 F-1.3j+k 块（2026-04-18）"

### 3.4 P4 sw-smoke.yml 衍生修复（v2 新增）

5 角色审查实证发现 sw-smoke.yml 现有两处 P1 缺陷，与 F-1.3j 同期修复（分别对应 AC-2 fail-fast 真兑现 + AC-4 真自动化）：

**P4-E 删 line 59 `|| true`**（测试员 P1#1，已实证）：

当前 `.github/workflows/sw-smoke.yml:59`：

```bash
python cad_pipeline.py sw-inspect --deep --json > sw-inspect-deep.json || true
python tools/assert_sw_inspect_schema.py sw-inspect-deep.json
```

`|| true` 吞掉 sw-inspect 退出码，sw-inspect 自身 crash 写空文件时下游 schema assert 抛 `JSONDecodeError`（不是 spec AC-2 描述的"具体字段名 AssertionError"），承诺不兑现。

修法：

```bash
# 直接让 sw-inspect 退出码传染 step（删 || true）
python cad_pipeline.py sw-inspect --deep --json > sw-inspect-deep.json
python tools/assert_sw_inspect_schema.py sw-inspect-deep.json
```

副作用：若 sw-inspect 启动失败（如 SW Dispatch 整步 fail），artifact 上传 step 仍 `if: always()` 保留 partial 输出（line 73），不丢调试现场。

**P4-F Skip-guard 加严 `real == 2`**（测试员 P1#2 + 分析师 P1#2 部分采纳）：

当前 `.github/workflows/sw-smoke.yml:51`：

```python
assert real >= 1, 'expected >= 1 real testcase, got 0 — @requires_solidworks 可能被全量 skip'
```

修法：

```python
assert real == 2, f'expected exactly 2 real testcases (test_fast_real_smoke + test_deep_real_smoke), got {real} — marker 漂移或新测试未授 @requires_solidworks'
```

理由：当前 `tests/test_sw_inspect_real.py` 固定 2 个测试（fast + deep）；将来如有第 3 个真 SW 测试，必须先改本 assert（强制 reviewer 显式确认增量），符合 spec AC-4 加严意图，把"AC-4 需人工核"升级为"workflow 内自动断言"。

---

## 4. 验收标准（v2 修订）

| # | 检查项 | 通过标准 | verification mode | 取值来源 |
|---|---|---|---|---|
| AC-1 | sw-smoke workflow 跑完 | `conclusion=success` | manual eyeball | `gh run view <run-id>` / GitHub UI |
| AC-2 | sw-inspect-deep.json schema 字段完备 | 含 `layers.dispatch.data.elapsed_ms` 数值字段；并且 `tools/assert_sw_inspect_schema.py` 退出码 = 0 | auto via workflow（§3.4 P4-E 已删 `\|\| true`，sw-inspect 退出码不再被吞） | workflow step "Emit sw-inspect JSON artifact" 红即 AC-2 fail |
| **AC-2.5（v2 新增 C）** | materials.sldmat_files 业务承诺（继承 F.2 §0.2 第 3 条） | `layers.materials.data.sldmat_files > 0` | auto via test | `tests/test_sw_inspect_real.py::test_deep_real_smoke` 内已硬断（line 50-53），失败将让 sw-smoke "Run SW real smoke" step 红 → AC-1 连带 fail |
| **AC-3（v2 修订 B+Q）** | dispatch 性能在合理区间且为真冷启动 | `attached_existing_session == false` **AND** `3000 <= dispatch.elapsed_ms <= 15000`（端点闭区间含 3000 / 15000） | auto via script | 下载 artifact `sw-inspect-deep.json`，`jq -e '.layers.dispatch.data.attached_existing_session == false and (.layers.dispatch.data.elapsed_ms >= 3000) and (.layers.dispatch.data.elapsed_ms <= 15000)'`；K1 区间合规判读详见 §5 模板 |
| **AC-4（v2 修订 F）** | junit 真测试覆盖 | `total=2 skipped=0 real=2` | auto via workflow（§3.4 P4-F 已把 skip-guard 断言改为 `real == 2`） | workflow Skip-guard step 失败即 AC-4 fail，无需人工核 junit xml |
| AC-5 | runbook §7 同步 | F.2 段开头加状态升级行 + F.2 段之后追加"F-1.3j+k 修复记录 + K1 第二数据点"块（含 8 条 F.2 §0.2 承诺复核 + K1 区间合规判读 + state upgrade 收尾） | manual git diff | `git diff origin/main..HEAD -- docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` 含期望 patch |

**AC-2.5 设计依据（C：3D 设计师 P1#2）**：

- F.2 spec §0.2 承诺第 3 条 "materials 业务回归：`materials.sldmat_files > 0`（`test_deep_real_smoke` 已断言）"
- 本 spec 修复后若 ghrunner 首次冷启 SW、`C:\Users\ghrunner\AppData\Roaming\SolidWorks\` 默认 .sldmat 路径未初始化 → sldmat_files 可能 = 0
- AC-2.5 显式锁定该业务承诺，避免本 spec 通过但破承诺的隐性回归
- 实现已在测试代码中（无需新加），AC-2.5 只是在文档层把"测试已覆盖"显式登记为本 spec 的验收口径

**AC-3 区间选择依据（v2 修订 B + 3D P1#1）**：

- F.1 baseline N=1（5492ms）→ 本次 K1 第二数据点 N=2，统计意义弱（N<30 + 无 σ），不使用对称的 ±X% 窗口
- **新增 attached 守卫**：`adapters/solidworks/sw_probe.py:572` 实证 attached existing session 走 `elapsed_ms = 0 / severity = warn`（不是"小一点的值"），如果不显式守卫，AC-3 写"低于 3000ms 判 fail"会与 sw-inspect 实际行为冲突 → 用 `attached_existing_session == false` 守卫，把"必须冷启动"的语义说清楚
- 窗口下限 **3000ms**：真 SW COM Dispatch 冷启动物理下限（spike 实测 5492ms，3000ms 是 ~0.55× 余量边界，更小则可能是某种部分 attach / dll preload 异常）
- 窗口上限 **15000ms**（≈ 2.7× F.1 baseline）：超出说明 SW Dispatch 真有性能回归 / Windows boot 异常 / 磁盘 I/O 异常 / ghrunner 首次 SW 冷启 user data 重建未完，需单独 F-1.3l follow-up 排查
- 警示档（v2 新增，机械 P1#2）：[10000, 15000] 视为 ⚠️ "性能接近上限"，runbook 模板必须显式标注 + 建议下次推 sw_warmup 改动前先重测；详见 §5 模板

**AC-4 升级路径（v2 修订 F）**：

- v1：workflow 内 skip-guard 仅 assert `real >= 1`（防 marker 全量 skip），AC-4 加严到 `real == 2` 需人工核 junit xml
- v2：§3.4 P4-F 把 workflow skip-guard 断言**直接改成** `real == 2`，AC-4 升级为 "auto via workflow"，无人工 verification 需求

---

## 5. runbook §7 同步内容

**两处改动**：

1. F.2 块开头加状态升级行（升级判据见 §3.3 末尾）
2. F.2 块**之后**追加新块（v2 模板）

### 5.1 F.2 块开头加状态升级行

定位 runbook §7 F.2 验收块的第一行（`**F.2 完整生产链路验收记录**...`），其下追加一行：

```markdown
**状态：→ 2026-04-18 升级见 F-1.3j+k 块（PASS pickup-only → PASS clean）**
```

### 5.2 F.2 块之后追加新块（v2 模板）

```markdown
**F-1.3j workspace ACL 修复 + F-1.3k K1 第二数据点**（2026-04-18，PASS / state upgrade carrier）：

- 修复日期：2026-04-18
- 根因：F.1 baseline 跑（procheng admin session）创建的 `.pytest_cache` 持有 protected ACL（仅 Owner/Admin/SYSTEM Full，无 ghrunner 条目且不继承），F.2 切到 ghrunner 身份后 `git clean -ffdx` 无权 scandir 触发 EPERM
- 一次性手工 fix：admin PowerShell `Remove-Item -Recurse -Force` 清掉 `D:\actions-runner\_work\cad-spec-gen\cad-spec-gen\.pytest_cache` + 所有 `__pycache__` 残留
- 防御性变更：`.github/workflows/sw-smoke.yml` 在 `actions/checkout@v6` 之前新增 `Pre-checkout workspace cleanup` step（pwsh / best-effort / 使用 `$env:GITHUB_WORKSPACE` 不绑定 runner 路径 / 含 SW 残留进程清理 + `::warning::` annotation）
- 衍生修复：line 59 删 `|| true`（修 AC-2 fail-fast 击穿）/ line 51 skip-guard 由 `real >= 1` 加严到 `real == 2`（修 AC-4 自动化）
- **验证 run**：<run URL 回填>（workflow_dispatch 显式触发，非 push）

**AC 验收结果**：

- AC-1 conclusion: ✅ success
- AC-2 schema fail-fast: ✅（assert_sw_inspect_schema.py exit=0，含 dispatch.elapsed_ms）
- AC-2.5 materials 业务承诺: ✅ `materials.sldmat_files = <数值>` (> 0)
- AC-3 K1 第二数据点：`dispatch.elapsed_ms = <数值> ms` / `attached_existing_session = false`
  - F.1 baseline 对照：5492 ms
  - K1 区间合规判读：[ ] 正常区间 [3000, 10000] / [ ] ⚠️ 警示区间 [10001, 15000] / [ ] ❌ 越界（触发 F-1.3l）
  - Δ vs baseline：(K1 - 5492) / 5492 × 100 = <±X%>
- AC-4 junit: ✅ total=2 skipped=0 real=2（workflow 自动断言，无需 manual）
- AC-5 文档同步: ✅ 本块 + F.2 状态升级行

**F.2 §0.2 八条承诺复核**（机械设计师消费视角）：

承诺侧：
- [ ] 链路层 — runner 自启动 OK，workflow_dispatch 触发 pickup（push main 路径未在本 spec 复验，依据共享 runner / 同 workflow 论据继承 F.2 PASS pickup-only 结论）
- [ ] schema 回归 — `assert_sw_inspect_schema.py` PASS，sw-inspect JSON v1 字段不漂
- [ ] materials 业务回归 — `materials.sldmat_files > 0`（test_deep_real_smoke 已断言）
- [ ] 运行时回归 — 真 SW Dispatch 5492 ms ± Δ 量级未异常退化（K1 第二点见 AC-3）

不承诺侧（不变）：
- [ ] toolbox 业务层回归 ❌ 未在 sw-smoke 内（F-1.3h 待办）
- [ ] STEP 转换正确性 ❌ 未跑 sw-warmup / Stage C
- [ ] 永久有效 ❌ 90 天 token 轮换 + Windows / SW 升级须复验
- [ ] 跨机器 ❌ F.2 仅本机 procheng-sw-smoke 验证

**后续状态**：runner long-lived 在线，sw-smoke 重新进入 ready-for-merge 状态。

🎉 **F.2 → PASS clean，原 F.2 块 "PASS pickup-only" 状态正式升级**（升级判据 = 本块 AC-1..5 全 ✅ + F-1.3j / F-1.3k follow-up 标注 closed）
```

> 模板里的 `<数值>` / `<run URL 回填>` / 复核 checkbox 均为占位，由 §6 S6 验收 + S7 文档 commit 阶段填实。

---

## 6. 推 main 节奏（v2 修订）

> **编号说明**：本节用 S1..S7（"step"）以避免与 §3.1-3.4 的 P1/P2/P3/P4（fix work parts）混淆。S 与 P 不一一对应。

| 节点 | 动作 | commit 策略 | 触发 sw-smoke？ |
|---|---|---|---|
| S1 | admin PowerShell 跑 §3.1（P1 一次性 fix） | 不 commit（手工动作） | 否 |
| S2 | 改 sw-smoke.yml 加 §3.2（P2 cleanup step）+ §3.4 删 `\|\| true` + 改 `real == 2` | 1 commit on feature branch | 否（feature branch push 不触发） |
| **S2.5（v2 新增 R）** | 本地 dry-run pwsh cleanup 脚本（3 fixture：workspace 不存在 / 含 .pytest_cache / 不设 GITHUB_WORKSPACE），核每个分支输出符合预期 | 不 commit（手工预检） | 否 |
| S3 | 本地 `actionlint .github/workflows/sw-smoke.yml` | 不 commit（预检） | 否 |
| S4 | PR + merge to main | merge commit | 是（merge 自动触发会跑一次 sw-smoke，**但本 spec K1 数据点不依赖此次** — 该次跑用作"修复有效性烟雾"，K1 第二数据点统一以 S5 为准） |
| **S5（v2 修订 A）** | **手动 `gh workflow run sw-smoke.yml --ref main`** 触发 K1 第二数据点采集 run | 不 commit | **是**（workflow_dispatch 显式触发，与 F.2 T3 一致） |
| S6 | 等 S5 跑完，下载 artifact，核 AC-1..AC-5（含 AC-2.5 / AC-3 attached 守卫 + 区间判读 / AC-4 自动） | 不 commit | — |
| S7 | runbook §7 回填 §5 模板（含 F.2 状态升级行 + 新块 K1 数据 + 8 条承诺 checkbox） | 1 commit on main，message 末尾加 `[skip smoke]` | 否（`[skip smoke]` 跳过无意义触发） |

**关键设计决策**：

| 决策 | 取舍 |
|---|---|
| S2 不直接 push main | feature branch 过渡方便 S4 一次 review；走 PR 保留审查轨迹 |
| **S2.5 dry-run 3 fixture**（R：测试员 P2#2）| cleanup step 含 3 个新分支（workspace nonexistent / cache present / SW 残留进程），actionlint 只查 yaml 语法不查 pwsh 逻辑；S2.5 在本机模拟环境跑一遍，确认 `Write-Host` 输出符合预期 |
| **S4 merge 跑当烟雾，不当 K1 来源**（A 修订）| merge 自动触发的 push event run 用作"修复立即生效"信号；K1 数据点统一走 S5 workflow_dispatch，避免 push event vs workflow_dispatch event 路径假设歧义 |
| **S5 workflow_dispatch 显式触发**（A 修订）| 与 F.2 T3 / runbook §7 既有验证完全一致；可控触发避免边界 case |
| S7 单独 commit 回填 runbook | 数据更新与代码变更解耦；`[skip smoke]` 避免纯文档 commit 触发 ~57s 物理跑 |

---

## 7. 风险与回滚

### 7.1 风险矩阵（v2 修订）

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| S1 admin Remove-Item 误删（手抄路径出错） | 低 | 中 | 命令前 `Test-Path` 验证；目标路径写死到 `.pytest_cache` 子目录，root 级别误删可能性低 |
| S4/S5 sw-smoke 仍红（fix 未根治） | 低 | 中 | 查 `actions/checkout@v6` step log 是否仍 EPERM；若 EPERM 消失但其他 step 红 → 问题不在本 spec 范围（独立排查） |
| AC-3 越界 `dispatch.elapsed_ms < 3000` AND attached=false（真冷启动但极低值） | 极低 | 低 | 物理下限；触发即开 F-1.3l 排查 SW Dispatch 异常 |
| AC-3 越上限 `dispatch.elapsed_ms > 15000` | 低 | 低 | 提示 SW Dispatch 真有回归或 Windows boot 异常，记 F-1.3l follow-up |
| **AC-3 警示档 [10000, 15000]**（机械 P1#2）| 中 | 低 | runbook 模板必须显式标注 ⚠️ 接近上限 + 建议下次推 sw_warmup 改动前先重测 |
| AC-3 attached_existing_session=true（被 attach 而非冷启） | 中 | 中 | 检查 ghrunner session 是否有 SLDWORKS 残留；本 spec §3.2 P2-O 已加 pre-cleanup `Stop-Process SLDWORKS`，主动避免；AC-3 兜底守卫确保此情况判 fail 不被 silent pass |
| 兜底 step 在 ghrunner 身份下也被 ACL 拒 | 中 | 低 | best-effort 已覆盖：silent fail 不阻塞，让 `actions/checkout` 的 recreate-workspace fallback 接管；AC-1 仍能 pass；同时 `::warning::` annotation 让 Actions UI 可见，避免长期失败被掩盖 |
| **silent-fail 长期未察觉**（L：3 角色合并）| 低 | 中 | `::warning title=cleanup_residual::` annotation 在 Actions UI 顶部显示；F-1.3l 触发条件加"≥ 2 次连续 cleanup_residual annotation 升级 issue" |
| **消费者误诊（CI 红被误判为代码问题）**（机械 P2#2）| 中 | 中 | cleanup step name 含 `(F-1.3j 防 protected-ACL 残留)` 后缀，Actions UI 一眼可辨；annotation title 含 `cleanup_residual` 关键字 |
| S1 后短期内又有人手工跑 procheng admin pytest 污染 workspace | 极低 | 高（复发） | runbook §5 已规定 long-lived ghrunner；本 spec 不加额外约束（不值得为低概率事件加流程负担） |
| `$env:GITHUB_WORKSPACE` 在某些 runner 版本下未定义 / 空字符串 | 极低 | 低 | step 内已强化守卫覆盖 `-not $ws -or $ws.Trim() -eq '' -or -not (Test-Path -LiteralPath $ws)`，未定义直接 skip（等价 no-op） |

### 7.2 回滚方案

| 失败场景 | 回滚动作 |
|---|---|
| S2 commit 导致 yaml 语法错 | `git revert <commit>`；S1 清掉的 workspace 不影响（下次跑会 recreate） |
| S4 / S5 sw-smoke 持续红，排查需时间 | commit message 加 `[skip smoke]` / `[skip sw-smoke]`（D15 已存在）临时跳过；不阻塞其他 PR；同时开 F-1.3l follow-up |
| §3.4 P4-E 删 `\|\| true` 后 sw-inspect 偶发 crash 让 sw-smoke 转红率上升 | revert §3.4 P4-E（恢复 `\|\| true`）；改为在 `tools/assert_sw_inspect_schema.py` 内加 `JSONDecodeError` 友好包装（保留信息但不影响 fail-fast） |
| §3.4 P4-F `real == 2` 在新增第 3 个真测试时阻塞 | 该次 PR 必须**同时**改 skip-guard 数字（设计意图，强制 reviewer 显式确认增量）；非 emergency 不绕过 |
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
| **F-1.3l**（v2 修订） | 若 AC-3 越界（< 3000ms 真冷启 / > 15000ms / attached=true 多次连续）或 cleanup `::warning::` annotation 连续 ≥ 2 次，排查 SW Dispatch 性能回归 / runner 状态 | 任一触发条件 fail |
| **F-1.3m**（v2 新增 D 余量） | 抽 cleanup step 到 `.github/actions/preclean-workspace/action.yml` composite | F-1.3g（tests.yml 迁移）一并做时；或第 2 个 workflow 复用本 cleanup 时 |
| **F-1.3n**（v2 新增 V 架构师 P3） | cleanup 路径列表抽成 step env 变量 `PRECLEAN_GLOBS` | F-1.3m 落地后或 cleanup 范围首次扩展时 |
| **F-1.3o**（v2 新增 Y 机械 P3） | 季度健康检查清单（与 #39 90 天 token 轮换合并）：admin PowerShell 跑 `icacls` 验证 `.pytest_cache` 含 ghrunner:(I) 条目 | 90 天周期 |
| **F-1.3p**（v2 新增 S 测试员 P2#4） | CODEOWNERS 加 `.github/workflows/sw-smoke.yml @procheng` + runbook §7 加 pre-flight checklist 防回归 | sw-smoke.yml 出现首次未授权改动时 |
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

**版本记录**：

- v1：初稿（brainstorming 5 轮 Q&A + 1 次 admin icacls 现场诊断后）
- **v2（本稿）**：5 角色 adversarial 审查（系统分析师 / 系统架构师 / 3D 设计师 / 软件测试员 / 机械设计师）一致 REVISE，14 项合入：
  - 6 触类 P1（A 状态机/触发等价 / B AC-3 实现矛盾 / C materials 隐式承诺 / D composite + GITHUB_WORKSPACE / E `\|\| true` 击穿 / F AC-4 自动化）
  - 2 P1 衍生（G `clean: false` 决策 / H K1 区间合规判读）
  - 6 高价值 P2（L silent-fail annotation / O Stop-Process / P cleanup 白名单 / Q 闭区间 / R dry-run task / T 八条承诺复核）
  - 主要新增：§3.4（sw-smoke.yml 衍生修复）/ §2.2 cleanup 白名单 / AC-2.5 / S2.5 dry-run / S5 workflow_dispatch / 状态升级声明
  - 主要修订：§3.2 决策表（+5 行）/ §3.3 trigger 改 workflow_dispatch / §4 AC-3 加 attached 守卫 + 闭区间 / §5 模板大幅扩展 / §7 风险矩阵更新 P→S + 新增 4 行 / §9 follow-up 增 F-1.3m/n/o/p
