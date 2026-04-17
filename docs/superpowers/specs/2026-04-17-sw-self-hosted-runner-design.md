# SW self-hosted runner smoke CI — 设计文档

- **日期**：2026-04-17
- **作者**：proecheng（Claude Code 协作）
- **状态**：design（待实施）
- **归属 phase**：sw-inspect Follow-up F-1.3
- **前置决策**：#37（solidworks optional extra）/ #38（sw-inspect 作为正式诊断入口）
- **实施计划**（待生成）：`docs/superpowers/plans/2026-04-17-sw-self-hosted-runner.md`

---

## 1. 背景与动机

### 1.1 现状

决策 #38 落地 `cad_pipeline.py sw-inspect` 后，深度 smoke 测试 `tests/test_sw_inspect_real.py::TestSwInspectRealSmoke` 用 `@pytest.mark.requires_solidworks` 标记——`tests/conftest.py` 的 `pytest_collection_modifyitems` 钩子在非 Windows / 无 pywin32 / 无 SolidWorks 安装的环境全量 skip。

当前 CI 矩阵 `.github/workflows/tests.yml`：

| job | runner | Python | 真 SW 可达 |
|---|---|---|---|
| `test` | `ubuntu-latest` × `windows-latest` × 3.10/3.11/3.12 | 均 GitHub-hosted | ❌（windows-latest 无 SW 安装）|
| `regression` | `ubuntu-latest` | 3.12 | ❌ |

结果：**真 SW 的 deep smoke 只在开发者本机跑**。合并到 main 的代码若破坏 Dispatch / LoadAddIn / 材质扫描，CI 看不见，要靠开发者下次本机跑才发现。

### 1.2 目标

让决策 #38 提到的 deep smoke 在 CI 有**可追溯**的真 SW 证据：每次 push to main（以及手动触发）自动跑 `test_sw_inspect_real.py` 在真 SolidWorks 环境中，产物 JSON 上传为 artifact。

### 1.3 非目标

- **不**在 pull_request 上跑（public repo 安全前提，见 §3）。
- **不**做 Python 版本矩阵（fast/deep smoke 对 3.10 vs 3.12 不敏感，YAGNI）。
- **不**覆盖 Stage C / sw-warmup 端到端（属 F-4a baseline 范围）。
- **不**做 runner 多机冗余 / 容器化（单机足够；SW 本身 license-per-machine）。
- **不**改动既有 `tests.yml` / `regression` job（隔离原则，新增独立 workflow）。

---

## 2. 决策总览

| # | 决策 | 来源章节 |
|---|---|---|
| D1 | 新建独立 workflow `.github/workflows/sw-smoke.yml`，不改 `tests.yml` | §4.1 |
| D2 | 路径 C1：`push: main` + `workflow_dispatch`，**不**监听 `pull_request` | §3.1 |
| D3 | runner label 组合：`[self-hosted, windows, solidworks]` 三 label 联合定位 | §4.2 |
| D4 | runner 注册用 `--ephemeral`：每 job 执行完自毁并重新注册 | §3.2 |
| D5 | runner **不**装为 Windows Service；用 Task Scheduler at-logon 启动（SW 需交互式 GUI 会话）| §3.3 |
| D6 | 专用受限 Windows 账户（例 `ghrunner`），无 Administrators、无 RDP、无个人文件访问 | §3.2 |
| D7 | `concurrency: { group: sw-smoke, cancel-in-progress: true }`，离线积压只保留最新 | §4.3 |
| D8 | `timeout-minutes: 15`，防 Dispatch 悬挂锁死 runner | §4.3 |
| D9 | 新增 runbook `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`，登记决策 #39 | §5 |
| D10 | Skip-guard：pytest exit code 5（no tests collected）显式当 fail 处理，防 `@requires_solidworks` 逻辑误改后 CI 误绿 | §4.4 |

---

## 3. 安全模型

### 3.1 为什么 public repo + self-hosted = 高风险默认态

GitHub 官方[明确警告](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners#self-hosted-runner-security)：**不要给 public repo 配 self-hosted runner 默认接收 PR**。原因：任何人 fork 仓库后发 PR，workflow 会在你的机器上执行其 PR 分支的代码——等价于给所有互联网用户你机器的代码执行权。

缓解：**不在 `pull_request` 事件上触发 sw-smoke**。触发器只接 `push: branches: [main]`（合并后）和 `workflow_dispatch`（显式手动）。两者都要求代码已通过 main 的保护（或手动启动者是 repo collaborator），因此攻击面归零。

### 3.2 Runner 账户隔离

| 项 | 配置 | 理由 |
|---|---|---|
| 账户 | `ghrunner`（新建本地标准用户）| 不共享开发者日常账户的个人文件 / keychain / SSH key |
| 组 | Users（非 Administrators）| 阻断 job 内提权 |
| RDP | 禁用 | 不给远端登录面 |
| 登录方式 | 仅 console 登录（Task Scheduler at-logon）| 不开放 SMB / WinRM |
| runner 工作目录 | `D:\actions-runner`（独立盘根外）| 隔离日常 dev 盘 |
| token 存储 | runner 自身 `.runner` / `.credentials` 文件，不进 git | GitHub 默认行为，确认不误传 |

### 3.3 Ephemeral runner + 非 Service 模式

- **`--ephemeral`**：注册时加此标志，runner 每跑完一个 job 即退出；下一次需重新获取 token 注册。好处：job 间无状态泄漏；坏处：需要自动化重新注册。用 Task Scheduler 在 runner 退出后重启 + 维护脚本自动注册（runbook §4 覆盖）。
- **不装 Service**：SolidWorks COM 需要交互式用户会话（session 0 隔离问题），runner 以 Service 身份跑会导致 SW Dispatch 失败或静默挂起。改用 `ghrunner` 账户开机自动登录 + Task Scheduler at-logon 启动 `run.cmd`。副作用：机器重启后必须有人确认 `ghrunner` 的自动登录成功（或配置 Autologon）。

### 3.4 Token 轮换

GitHub self-hosted runner registration token 有效期约 1 小时，用于 initial 注册；runner 本身使用长期 credential（存在 `.credentials` 里）。长期 credential 没有 GitHub 侧强制过期，但**runbook 要求 90 天手动轮换**（删除 runner → 重新注册），以控制凭据泄漏窗口。

---

## 4. 组件设计

### 4.1 workflow 文件：`.github/workflows/sw-smoke.yml`

```yaml
name: sw-smoke

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: sw-smoke
  cancel-in-progress: true

jobs:
  sw-smoke:
    runs-on: [self-hosted, windows, solidworks]
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6

      - name: Set up Python 3.12
        uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Install deps
        shell: bash
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[solidworks]"
          pip install pytest pytest-timeout

      - name: Run SW real smoke
        shell: bash
        env:
          PYTHONUTF8: "1"
        run: |
          pytest tests/test_sw_inspect_real.py -v --tb=short \
                 -m requires_solidworks \
                 --junitxml=sw-smoke-junit.xml

      - name: Assert tests actually ran (skip-guard)
        shell: bash
        run: |
          # pytest exit 5 = no tests collected；若 @requires_solidworks gate 逻辑被误改
          # 导致 smoke 全 skip，CI 会绿但无真跑证据。显式断言 junit 报告里 testcase 数 > 0。
          test -f sw-smoke-junit.xml
          count=$(grep -c '<testcase' sw-smoke-junit.xml || true)
          echo "skip-guard: <testcase> count = $count"
          if [ "$count" -lt 2 ]; then
            echo "ERROR: expected ≥ 2 testcases, got $count. @requires_solidworks 可能被全量 skip。"
            exit 1
          fi

      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: sw-smoke-artifacts
          path: |
            sw-smoke-junit.xml
            **/sw_inspect_*.json
          if-no-files-found: ignore
```

### 4.2 runner 标签

三 label 组合 `[self-hosted, windows, solidworks]`：
- `self-hosted`：GitHub 自动保留 label
- `windows`：GitHub 自动保留 label（基于 OS 检测）
- `solidworks`：自定义 label，注册时 `--labels solidworks` 显式加上

为何用三 label：`self-hosted` + `windows` 可能匹配到未来其他用途的 Windows self-hosted runner（如 GPU 测试），`solidworks` label 锁定"这台装了 SW 的机器"。

### 4.3 并发与超时

- `concurrency.group: sw-smoke` + `cancel-in-progress: true`：runner 离线期间积压的 job 只保留最新一次；开机后不会连跑 10 遍陈旧代码。
- `timeout-minutes: 15`：远大于 deep smoke 正常耗时（< 30s Dispatch + < 30s LoadAddIn + 余量），但足以防止 Dispatch 真悬挂把 runner 锁 2 小时。

### 4.4 Skip-guard（D10 展开）

`@requires_solidworks` 是在 `tests/conftest.py` 里靠 `pytest_collection_modifyitems` 动态 skip 的。若未来 refactor 误改该 gate（例如条件反了），test_sw_inspect_real.py 会全量 skip，pytest exit code 仍是 0，CI 绿——但没跑任何真 SW 逻辑。

防御：用 `--junitxml` 输出 junit 报告，workflow 末尾 grep `<testcase` 条数；< 2 直接 `exit 1`。这把"静默全 skip"从 silent success 升级为 loud failure。

---

## 5. 文档产出

### 5.1 Runbook：`docs/superpowers/runbooks/sw-self-hosted-runner-setup.md`

章节：
1. 前置要求（Windows 11 / SolidWorks 2024+ license / 可联网）
2. 创建 `ghrunner` 账户（net user + 组权限收敛清单）
3. 开机自动登录配置（Autologon 工具 vs 注册表 `DefaultUserName`）
4. 下载并安装 GitHub Actions Runner（版本锁 + 校验）
5. 注册 runner：`config.cmd --url ... --token ... --labels solidworks --ephemeral`
6. Task Scheduler 条目（at-logon trigger、working dir、restart on failure）
7. 首次跑 sw-smoke 验证（`workflow_dispatch` 触发 + Actions 页确认）
8. 故障排查：
   - runner offline 诊断
   - SW Dispatch 失败 → 确认非 Service 模式 + user session 活跃
   - 积压 queued job 清理（`gh run cancel`）
9. 90 天 token 轮换 SOP
10. 卸载：`config.cmd remove --token ...` + 清 Task Scheduler

### 5.2 决策日志：`docs/superpowers/decisions.md` 追加 #39

内容要点：
- 路径选择 C1 的理由（不在 PR 跑 = 公开仓库安全前提）
- 不装 Service 的理由（SW 交互式会话约束）
- ephemeral + 专用账户的理由（攻击面收敛）
- 决策生效前提：开发者拥有一台常可开机的 Windows + SW 机器
- Follow-up：若后续有多机需求或 license 冲突，再考虑 F-1.3c（容器 / 多 runner / 预约锁，见 §9）

### 5.3 README / CLAUDE.md

- README CI 段：追加 "sw-smoke: 真 SW 环境回归（self-hosted runner，仅 main push + 手动触发）" 一行
- CLAUDE.md：不改。self-hosted runner 是基础设施而非开发流程

---

## 6. 验收标准

- [ ] `.github/workflows/sw-smoke.yml` 合入 main，语法 `actionlint` 通过
- [ ] self-hosted runner 在 `Settings → Actions → Runners` 页可见，labels 含 `self-hosted`, `Windows`, `solidworks`
- [ ] 至少一次 `push: main` 触发的 sw-smoke 成功 run（绿），Actions 页可下载 `sw-smoke-artifacts`
- [ ] artifact 内 `sw-smoke-junit.xml` 可见 `<testcase>` 条数 ≥ 2（fast + deep 均真跑非 skip）
- [ ] `sw_inspect_*.json`（若 run_sw_inspect 落地产物）可下载并含 `layers.dispatch.data.elapsed_ms`
- [ ] `docs/superpowers/runbooks/sw-self-hosted-runner-setup.md` commit
- [ ] 决策 #39 追加到 `docs/superpowers/decisions.md`
- [ ] 既有 `tests.yml` / `regression` job 零改动（`git diff main -- .github/workflows/tests.yml` 空 diff）
- [ ] Skip-guard 首跑证据：首次成功 `sw-smoke` run 的日志显式可见 "grep -c '<testcase' = 2"（或更高），并在 runbook §7 记录该值作为 baseline；后续若该计数回退到 < 2，skip-guard 即按 §4.4 逻辑 `exit 1` 报错

---

## 7. 风险清单

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| runner token 或 workflow 配置泄漏 | 低 | 攻击者在你机器执行任意代码 | ephemeral + 专用账户无 admin；不在 PR 跑；`.credentials` 不进 git |
| SW license 占用冲突（runner 跑 smoke 时你也在用 SW）| 中 | smoke fail 或你的 SW 报 license unavailable | smoke 单次 < 60s，concurrency 取消；如频繁冲突可手动 disable workflow |
| 机器长期关机 → main 上 smoke 积压 | 高 | Actions 页有大量 Queued，观感差但无实质问题 | `cancel-in-progress: true` 保证只保留最新；runbook 建议定期 `gh run cancel --all` |
| `@requires_solidworks` gate 误改导致全 skip | 低 | CI 绿但无真跑 | §4.4 skip-guard |
| Autologon 密码泄漏（注册表 `DefaultPassword` 明文）| 中 | 物理接触者可拿 runner 账户密码 | 用 Sysinternals Autologon 工具（LSA-encrypted 存）而非注册表明文；账户无 admin 权限限制伤害范围 |
| SolidWorks 2024+ 交互式会话超时自动登出 | 低 | runner session 断 → 后续 job 挂 | 配 Windows 电源方案"从不休眠" + "从不锁屏" for `ghrunner` 账户 |
| GitHub Actions Runner 自升级导致 ephemeral 脚本 break | 低 | Task Scheduler 条目失效 | runbook 要求用官方 `run.cmd`（自带 updater），不 hardcode 版本号 |

---

## 8. 依赖与外部假设

- **SolidWorks license**：假定开发机持久授权（非网络浮动），不因 runner 账户切换失效。若是网络浮动，首次 smoke 可能冲突，需 runbook 追加"license swap"节。
- **GitHub Actions 计费**：self-hosted runner 不消耗 GitHub 配额（public repo 本来也是无限），但 artifact 存储占 GitHub 免费额度 500MB；sw-smoke artifact 每次 < 100KB，可忽略。
- **机器可用性**：F-1.3 价值与 runner 在线率成正比。如果每月在线时间 < 30%，考虑降级为 F-1.3e（见 §9）：仅保留 runbook + 本地 `pwsh scripts/run_sw_smoke.ps1` 产物贴 PR 描述，不开 self-hosted runner。

---

## 9. Follow-up（本设计显式标出的延后项）

| ID | 内容 | 触发条件 |
|---|---|---|
| F-1.3a | 把 sw-smoke 的 JSON artifact 消费到 dashboard（Grafana / GitHub Pages 静态图）| 有 ≥ 20 次 main run 数据 |
| F-1.3b | `workflow_dispatch` 加 input `full: bool`，full=true 时追加跑 sw-warmup / Stage C | F-4a baseline 工作开启时 |
| F-1.3c | 若未来有第二台 SW 机器，加 `runner-group` 做负载均衡 | 出现 license / 可用性冲突时 |
| F-1.3d | 把 `actionlint` 加到 pre-commit + CI（独立于本 F-1.3，但本设计验收依赖 actionlint 通过）| 本 F-1.3 收尾时一并做或另立 |
| F-1.3e | "runner 低在线率"降级路径：runbook + 本地 `pwsh scripts/run_sw_smoke.ps1` 产物贴 PR 描述，不开 self-hosted runner | 若实际开机率 < 30% 且不想维护 runner |
