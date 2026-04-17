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
  `windows-latest` 镜像的关键差异点）

## 2. 创建 `ghrunner` 账户

以管理员身份启动 PowerShell：

```powershell
net user ghrunner "<强密码>" /add
net localgroup Users ghrunner /add
# 确认 ghrunner 不在 Administrators 组：
net localgroup Administrators
```

收敛权限：
- 禁用 RDP 对 ghrunner 的访问（gpedit / 组策略 `Deny log on through Remote Desktop Services`）
- 文件系统：开发者个人文件夹（如 `C:\Users\proecheng`）对 `ghrunner` 拒绝读写（右键属性 → 安全 → 编辑）

## 3. 开机自动登录配置

**不**用注册表明文 `DefaultPassword`（物理接触者可直接读）。用 Sysinternals **Autologon** 工具（LSA-encrypted 存储）：

1. 下载 https://learn.microsoft.com/en-us/sysinternals/downloads/autologon
2. 以管理员身份运行 `Autologon.exe`
3. Username = `ghrunner`、Domain = `.`、Password = 第 2 节设置的密码
4. Enable

验证：重启机器，应自动登录到 ghrunner 桌面。

## 4. 下载并安装 GitHub Actions Runner

1. GitHub → repo Settings → Actions → Runners → New self-hosted runner → Windows x64
2. 按页面给出的 PowerShell 命令下载 + 解压到 `D:\actions-runner`（独立盘，隔离日常 dev 盘）
3. 校验 SHA256（页面同时给出）

## 5. 注册 runner（long-lived，D4）

以 `ghrunner` 账户登录，在 `D:\actions-runner` 跑：

```powershell
cd D:\actions-runner
.\config.cmd --url https://github.com/proecheng/cad-spec-gen `
             --token <one-time-registration-token> `
             --labels solidworks `
             --replace
```

注意：
- **不**加 `--ephemeral`（D4：ephemeral 需要长期 PAT 自动重注册，破坏账户隔离）
- token 从"New self-hosted runner"页面复制，1 小时有效
- `--labels solidworks` 必填；另两个 label `self-hosted` / `Windows` GitHub 自动附加

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
   - `sw-smoke-junit.xml`：ET 解析应得 `total >= 2, skipped == 0, real >= 2`（首跑 baseline）
   - `sw-inspect-deep.json`：记录 `layers.dispatch.data.elapsed_ms` 作为 K1 第一个数据点
4. CI 页 Job Summary 区块应直接显示 sw-inspect text 输出（D16 / §4.7）

**baseline 记录**（填入本 runbook 本节）：

- 首跑日期：`____`
- `skip-guard: total=X skipped=Y real=Z`：`____`
- `sw-inspect-deep.json.layers.dispatch.data.elapsed_ms`：`____` ms

## 8. 故障排查

### 8.1 Runner offline

- Actions → Runners 页显示红点 → ghrunner session 未登录或 `run.cmd` 崩溃
- 以 ghrunner 登录，检查 `D:\actions-runner\_diag\` 最新日志

### 8.2 SW Dispatch 失败

- 确认 runner **不**以 Service 身份跑（见第 6 节 "Run only when user is logged on"）
- 确认 ghrunner session 是交互式 GUI 会话（能手动启动 SolidWorks）

### 8.3 License 冲突（"SolidWorks is being used by..."）

如果 license 是 per-user：
- 合并前关闭你的 SW 实例，或 commit message 加 `[skip smoke]` / `[skip sw-smoke]`（D15）
- 持续冲突可在 Actions → sw-smoke → Disable workflow 临时关闭

### 8.4 积压 queued job 清理

```bash
gh run list --workflow=sw-smoke --status=queued
gh run cancel --all  # 或逐个 cancel
```

### 8.5 Network license / 浮动许可首次 smoke license swap

若 SW 是网络浮动许可，ghrunner 首次启动 SW 会与你的 session 争 license。
**本 F-1.3 不覆盖此场景**；若需支持，参考 SolidWorks Admin Portal 的 multi-seat
配置；或按 §8 F-1.3e 降级为本地跑路径。

## 9. 90 天 token 轮换 SOP

目的：控制 runner credential 泄漏窗口（虽 GitHub 无强制过期，手动轮换是最佳实践）。

1. Settings → Actions → Runners → 找到本 runner → Remove
2. 以 ghrunner 登录，`D:\actions-runner` 跑 `.\config.cmd remove`
3. 按第 5 节重新注册（获取新 registration token）

日历提醒：每 90 天跑一次。

## 10. 卸载

```powershell
cd D:\actions-runner
.\config.cmd remove --token <one-time-removal-token>
```

之后：
- Task Scheduler 删除"GitHub Actions Runner (sw-smoke)"
- 如不再需要 ghrunner 账户：`net user ghrunner /delete`
- Autologon 工具 → Disable
