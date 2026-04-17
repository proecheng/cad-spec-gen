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

**baseline 记录**（填入本 runbook 本节）：

- 首跑日期：`____`
- `skip-guard: total=X skipped=Y real=Z`：`____`
- `sw-inspect-deep.json.layers.dispatch.data.elapsed_ms`：`____` ms

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
