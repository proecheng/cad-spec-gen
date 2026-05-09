# cad_jury_config.json — Photo3D Jury 用户级配置说明

`photo3d-jury` 子命令读取一份用户级配置，把 photo3d 增强结果交给 vision LLM 做语义/材质级自动验收。本文档面向**外行用户**（不熟悉 OpenAI 计费、TLS、企业代理）说明：

- 配置文件放哪、最小可跑的 JSON 模板
- 每个字段含义、合法取值、默认值
- 内置估价表（model 模式 → 单次调用费用）
- 隐私与安全警告
- 企业 MITM TLS 自签 CA 注入方法
- 已知支持 vision 的 OpenAI 兼容中转商
- 故障恢复（profile 切换、`--list-profiles`、`--last-status`）
- 必须加进 `.gitignore` 的路径

> 这份文档是 `cad_pipeline.py photo3d-jury` 的唯一权威配置说明；其他文档（cad-help-guide / spec rev 5）只引用本文档的字段定义，不在那里复述细节。

---

## 1. 文件位置

```
~/.claude/cad_jury_config.json
```

- 路径必须在用户主目录 `.claude/` 下；这是 jury 默认查找位置，无需 `--config`
- 也可以显式 `photo3d-jury --config <abs_path>`，但路径必须满足以下任一：
  1. 在 `~/.claude/` 下
  2. 在当前项目目录内
  3. 显式带 `--allow-external-config` flag（防社工攻击）
- 推荐 Linux/macOS 设权限 `chmod 600 ~/.claude/cad_jury_config.json`（Windows 文件夹默认即用户私有，仍需检查不要把整个 `~/.claude` 共享出去）
- **绝对禁止** commit 进 git；本文件含 `api_key`

---

## 2. 最小配置（schema_version=1，1 profile）

```json
{
  "schema_version": 1,
  "active_profile_id": "main",
  "profiles": [
    {
      "id": "main",
      "kind": "openai_compat",
      "api_base_url": "https://你的中转或厂商.com/v1",
      "api_key": "sk-在厂商网站申请",
      "model": "gemini-2.5-flash"
    }
  ]
}
```

复制上面 8 行后，**只改 3 处即可跑**：

1. `api_base_url` — 中转商或原生厂商的 OpenAI 兼容 base URL
2. `api_key` — 在厂商网站申请的 key
3. `model` — vision 模型名（见 §4 内置估价表选一个）

跑：

```bash
photo3d-jury --subsystem lifting_platform --dry-run
```

`--dry-run` 不发请求，先看 Layer 0/1 是否通过 + 估算 cost。读到「Layer 0 OK / Layer 1 OK / 估算 0.030 USD」即可去掉 `--dry-run` 真跑。

---

## 3. 字段说明

### 3.1 顶层字段

| 字段 | 类型 | 默认 | 含义 / 合法取值 |
|---|---|---|---|
| `schema_version` | int | 必填 | 仅 `1` 或 `2`；其他值（0 / 3+）→ exit=2。本版本 jury 是 v1，遇 v2 进 forward-compat 模式（仅读 v1 字段，未知字段 stderr 警告） |
| `active_profile_id` | str | 必填 | 必须命中 `profiles[].id`；用户 cli `--profile-id <id>` 临时覆盖不改 config |
| `profiles` | list | 必填 | 至少 1 个 profile；每个 profile 的 `id` 唯一 |
| `max_image_bytes` | int | `8388608`（8 MiB） | 单视角增强图最大字节数；范围 `[1024, 1<<30]`（1 KiB - 1 GiB）；超此值 jury 不发请求（防 b64 内存爆 + 单次费用暴涨） |
| `max_n_views` | int | `32` | 单 run 最大视角数；范围 `[1, 1024]`；ENHANCEMENT_REPORT 视角数超此值 → blocked，**`--confirm-cost` 也不旁路** |
| `min_photoreal_score` | int | `60` | 整体 verdict gate：LLM 返 `photoreal_score < min_photoreal_score` 时该视角退到 `preview`（即使 5 项 boolean 全 true）；范围 `[0, 100]`；`= 0` 关闭此 gate |

### 3.2 profile 字段

| 字段 | 类型 | 必填 | 含义 / 合法取值 |
|---|---|---|---|
| `id` | str | 必填 | profile 唯一标识；正则 `^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$`（首字符非 `-` 防 argparse 误识为 flag；长度 ≤ 64 防撑爆日志） |
| `kind` | str | 必填 | v1 仅支持 `"openai_compat"`（OpenAI Chat Completions 兼容格式 + base64 image_url）；v2 计划加 `"anthropic_native"` |
| `api_base_url` | str | 必填 | 必须 `https://` 开头（不接受 `http://`）；解析时 `urlparse().hostname` 必须非空；末尾斜杠会被自动 `rstrip('/')` |
| `api_key` | str | 必填 | 不能仅含空格；不会出现在任何报告 / log / stderr / debug-output 文件 |
| `model` | str | 必填 | vision 能力的模型名（如 `gpt-4o`、`gemini-2.5-flash`）；空字符串或仅空格会被 reject |
| `cost_per_call_usd` | float / null | 可选 | `null` 或缺省 → 走内置估价表（见 §4）；显式给数字时必须 `math.isfinite()` 且 `0 ≤ x < 1000`；显式 `0` 强制要求 `--confirm-cost`（除非 `--budget=0` 双 0 最严守门则免） |

### 3.3 base_url 智能 `/v1` 处理（仅 `kind == openai_compat`）

不管你填 `https://api.openai.com` 还是 `https://api.openai.com/v1`，jury 都能识别并拼出正确路径 `<base>/chat/completions`：

| 你写的 `api_base_url` | jury 内部归一化后 | 真实请求 URL |
|---|---|---|
| `https://api.openai.com` | `https://api.openai.com/v1` | `https://api.openai.com/v1/chat/completions` |
| `https://api.openai.com/v1` | `https://api.openai.com/v1` | `https://api.openai.com/v1/chat/completions` |
| `https://api.openai.com/v1/` | `https://api.openai.com/v1` | `https://api.openai.com/v1/chat/completions` |
| `https://aihubmix.com/v1` | `https://aihubmix.com/v1` | `https://aihubmix.com/v1/chat/completions` |

> 历史注意：`gemini_gen.py:42-46` 旧代码会无脑在任何 base 后强加 `/v1`，导致 `.../v1` 输入产 `/v1/v1/chat` 错路径。jury 实现**不沿用**这个旧行为；本节智能拼接已经过 4 种 base 形态测试覆盖。

---

## 4. 内置 model → cost 估价表（`BUILTIN_MODEL_COST_USD`）

当 profile 的 `cost_per_call_usd` 为 `null` 或缺省时，jury 按 `model` 名前缀匹配查表：

| model 模式（前缀匹配） | 默认 `cost_per_call_usd` (USD/call) | 说明 |
|---|---|---|
| `gpt-4o`, `gpt-4o-*` | **0.020** | OpenAI 官方公开计价（约值；按 1024×1024 图 + 256 token 输出粗估） |
| `gpt-4-turbo*` | **0.030** | 同上 |
| `gemini-2.5-flash*`, `gemini-1.5-flash*` | **0.005** | Google AI Studio 公开计价（约值） |
| `gemini-2.5-pro*`, `gemini-1.5-pro*` | **0.015** | 同上 |
| `claude-*-vision*`, `claude-3-*` | **0.025** | Anthropic 公开计价（约值） |
| 不匹配上面任一前缀 | — | jury 不放行；cli 警告 + 强制 `--confirm-cost` 才能跑（外行避坑） |

### 4.1 重要免责

估价表是 v1 的**约值兜底**，与真实计费可能 ±50% 偏差（vision 实际按 input/output token + image megapixels 多维计费）。对成本敏感时建议：

1. 先 `photo3d-jury --subsystem X --dry-run` 看 estimated_cost_usd
2. 显式在 profile 写 `"cost_per_call_usd": 0.012`（按你最近一次实测值）覆盖估价表

### 4.2 估价表过期机制

`BUILTIN_MODEL_COST_USD_BUILT_AT = "2026-05-08"`（spec 落地日期）。jury 启动时若任一 profile `cost_per_call_usd=null` 且距 BUILT_AT > **180 天** → stderr 警告：

```
⚠ 内置估价表已 N 天未更新（建于 2026-05-08）；实际 vendor 计费可能已偏离 ±50%
  建议在 profile 显式填 cost_per_call_usd 或加 --confirm-cost
```

警告**不阻塞执行**；v2 计划加 `cad-jury-prices update` cli 自动同步真实 vendor pricing。

### 4.3 显式覆盖示例

```json
{
  "schema_version": 1,
  "active_profile_id": "gpt4o-precise",
  "profiles": [
    {
      "id": "gpt4o-precise",
      "kind": "openai_compat",
      "api_base_url": "https://api.openai.com/v1",
      "api_key": "sk-xxx",
      "model": "gpt-4o",
      "cost_per_call_usd": 0.0185
    }
  ]
}
```

`0.0185` 来自用户上周实测 6 视角 × 平均费用 / 6；写死数字后估价表不再生效。

---

## 5. 隐私与安全警告（必读）

### 5.1 增强图会以 base64 上传

jury Layer 2 把每张 enhanced PNG/JPG 完整 base64 嵌进 `data:image/png;base64,...` 发到 `api_base_url`：

- 中转商可能**记录请求体**作日志（是否合规取决于厂商隐私政策）
- 中转商或原生厂商可能**用于训练**（是否 opt-out 取决于厂商账户设置）
- **机密项目应自托管 vision endpoint**（vLLM / Ollama vision 等本地部署），把 `api_base_url` 指向局域网

### 5.2 `api_key` 不落盘断言

jury 严格守规：

- `PHOTO3D_JURY_REPORT.json` 全文不含 `api_key`
- `jury_review_input.json` 全文不含 `api_key`
- `jury_debug_<view>.json`（`--debug-output` 写）不含 `api_key`
- stderr / stdout 任何输出不含 `api_key`
- 异常 traceback 不含 `api_key`（顶层 try/except 兜底；`http.client.HTTPConnection.debuglevel=0` 显式覆盖外部 logging）

但**用户责任**：

- 不要 commit `~/.claude/cad_jury_config.json` 进 git
- 不要把 key 直接写在 `--api-key` cli flag（jury 不接受此 flag；只能从 config 读）
- 多人共用机器时 `chmod 600 ~/.claude/cad_jury_config.json`

### 5.3 `.gitignore` 提醒

建议项目根 `.gitignore` 加：

```gitignore
cad/**/.cad-spec-gen/runs/
~/.claude/cad_jury_config.json
```

原因：

- `PHOTO3D_JURY_REPORT.json` 含 `profile_id` / `model` / `api_base_url` 主机名 / `vendor_request_id`，落进 git 会**暴露你的计费供应商指纹**
- `jury_review_input.json` 含 enhanced 图片摘要 + run-level 元信息，机密项目不应进公开仓
- 第二行只是补充防御；正常情况 `~/.claude/` 在用户主目录下，不会被项目 git 追踪

---

## 6. TLS 与企业 MITM 自签 CA

jury **严禁** `ssl._create_unverified_context()`（哪怕通过 env flag 都不允许）。企业 MITM 代理用户应通过 `SSL_CERT_FILE` env 注入 CA bundle：

### 6.1 Linux / macOS

```bash
# 假设公司 CA 在 /etc/ssl/corp-ca.pem
export SSL_CERT_FILE=/etc/ssl/corp-ca.pem
photo3d-jury --subsystem lifting_platform
```

### 6.2 Windows PowerShell

```powershell
$env:SSL_CERT_FILE = "C:\Users\<you>\corp-ca.pem"
photo3d-jury --subsystem lifting_platform
```

### 6.3 Windows cmd.exe

```cmd
set SSL_CERT_FILE=C:\Users\<you>\corp-ca.pem
photo3d-jury --subsystem lifting_platform
```

### 6.4 TLS 校验失败如何识别

如果证书链不通，jury 报告会有 `error_kind=tls_verification_failed`（独立类别，区别于 `network_unreachable`）；stderr 提示：

```
✗ TLS 校验失败：vision 服务证书链不被系统信任
  企业代理用户：export SSL_CERT_FILE=<你的公司 CA bundle>
  详见 docs/cad-jury-config.md §6
```

---

## 7. 已知支持 vision 的 OpenAI 兼容中转商示例

> 以下是 spec 落地时（2026-05-08）已知支持 OpenAI Chat Completions vision schema（`messages[].content[].type=image_url`）的中转商示例。**每家政策不同**，使用前请自行确认 (a) 是否 vision 计费正常 (b) 是否记录与训练 (c) 是否需要专门开通 vision 权限。

| 厂商 | base_url 示例 | 已知支持模型 | 备注 |
|---|---|---|---|
| OpenAI 原生 | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo` | 计费透明；隐私政策见 OpenAI 官网 |
| Aihubmix | `https://aihubmix.com/v1` | `gpt-4o`, `gemini-2.5-flash`, `claude-3-5-sonnet` | 中转聚合多家；vision 需在控制台确认开通 |
| SiliconFlow | `https://api.siliconflow.cn/v1` | 部分开源 vision 模型（确认控制台 model list） | 国内访问稳定 |
| 自托管 vLLM | `https://your-vllm.local/v1` | 自部署任意支持 vision 的开源模型（如 Qwen2-VL、InternVL） | **机密项目首选**；不离开局域网 |
| 自托管 Ollama | `http://localhost:11434/v1` | `llama3.2-vision` 等 | 本地零成本；jury 校验 `https://` → 需配 https 反代 |

> jury 不内嵌任何中转商白名单；上表只是"用户社区已实测可跑"的参考。新中转商上线后用户可自行尝试，schema 校验只看 `https://` + 非空 hostname 形态。

---

## 8. 故障恢复

### 8.1 列出可用 profile

```bash
photo3d-jury --list-profiles
```

输出 tab 分隔到 stdout（便于 grep / awk）：

```
gemini-aihubmix	openai_compat	gemini-2.5-flash	0.005	[active]
gpt-4o-native	openai_compat	gpt-4o	0.020
```

每行 5 列：`<id>` `<kind>` `<model>` `<cost_per_call_usd>` `[active]?`

`cost_per_call_usd` 列：profile 显式给数字时直接显示数字；走估价表时显示 `est:0.005`。

`--list-profiles` **不调 LLM**、不读 ENHANCEMENT_REPORT、不创建 lock。

### 8.2 临时切换 profile（不改 config）

`needs_review` 时通常想换一家更准的：

```bash
photo3d-jury --subsystem lifting_platform --profile-id gpt-4o-native
```

`--profile-id` 临时覆盖 `active_profile_id`；本次跑结束后下次默认仍是 config 里的 active。

### 8.3 复述上次状态（不调 LLM）

事后想看上一次 jury 跑了啥：

```bash
photo3d-jury --subsystem lifting_platform --last-status
```

读最新 active_run 的 `PHOTO3D_JURY_REPORT.json`，把 `status` / `ordinary_user_message` / `next_step` / `first_blocking_reason` 一屏打印出来。**不调 LLM 不写盘**。

### 8.4 重跑保护

既有 `PHOTO3D_JURY_REPORT.json` 时 jury 默认归档前次为：

```
PHOTO3D_JURY_REPORT.20260508T123456Z.a1b2c3.json
```

（紧凑格式无冒号避免 Windows NTFS 拒；`a1b2c3` 是原文件 sha256[:6] 防同秒重跑冲突。）

`--force` 强制覆盖时仍归档但用固定后缀 `PHOTO3D_JURY_REPORT.forced.json`（用户明示丢历史）。

### 8.5 4xx 错误时的诊断

`error_kind ∈ {parse_failed, non_json_response, bad_request}` 时 jury 自动写脱敏诊断文件：

```
cad/<sub>/.cad-spec-gen/runs/<run>/jury_debug_<view>.json
```

含 body 摘要 / status / vendor_request_id（去 api_key / Authorization / Cookie）；用于向中转商提 ticket。

---

## 9. 多 profile 配置示例（推荐）

外行用户也建议至少配 2 个 profile：1 个便宜 / 1 个更准，需要时用 `--profile-id` 切换。

```json
{
  "schema_version": 1,
  "active_profile_id": "gemini-flash-cheap",
  "max_image_bytes": 8388608,
  "max_n_views": 32,
  "min_photoreal_score": 60,
  "profiles": [
    {
      "id": "gemini-flash-cheap",
      "kind": "openai_compat",
      "api_base_url": "https://aihubmix.com/v1",
      "api_key": "sk-xxx",
      "model": "gemini-2.5-flash",
      "cost_per_call_usd": null
    },
    {
      "id": "gpt-4o-precise",
      "kind": "openai_compat",
      "api_base_url": "https://api.openai.com/v1",
      "api_key": "sk-yyy",
      "model": "gpt-4o",
      "cost_per_call_usd": 0.020
    },
    {
      "id": "self-hosted-qwen2vl",
      "kind": "openai_compat",
      "api_base_url": "https://vllm.lan.local/v1",
      "api_key": "any-non-empty",
      "model": "Qwen/Qwen2-VL-7B-Instruct",
      "cost_per_call_usd": 0.0
    }
  ]
}
```

使用：

```bash
# 默认 profile（gemini-flash-cheap）+ dry-run 估价
photo3d-jury --subsystem lifting_platform --dry-run

# 真跑默认 profile
photo3d-jury --subsystem lifting_platform

# 不达标时换 GPT-4o
photo3d-jury --subsystem lifting_platform --profile-id gpt-4o-precise

# 机密项目走自托管（cost=0 双 0 最严守门，无需 --confirm-cost）
photo3d-jury --subsystem lifting_platform --profile-id self-hosted-qwen2vl --budget 0
```

---

## 10. 同 vendor key 跨进程并发警告

多 subsystem 并发跑 jury（不同 active_run_dir，jury 锁不冲突）共用同一 vendor key 时，可能撞 vendor per-key RPM（每分钟请求数）。v1 由 `--max-retries` 退避兜底；建议**同 key 串行**：

```bash
# 串行（推荐）
photo3d-jury --subsystem lifting_platform
photo3d-jury --subsystem end_effector

# 并行（可能限流）
photo3d-jury --subsystem lifting_platform &
photo3d-jury --subsystem end_effector &
wait
```

v2 计划加跨进程信号量协调。

---

## 11. NAS / SMB share 警告

**严禁**把 `cad/` 放到 NAS / SMB / 网络驱动器上。jury 的 `.jury.lock` 文件锁、sha256 freeze、原子写、mtime 判 stale 都依赖**本地 fs 语义**；网络 fs 上 mtime 可能 stale 几分钟，导致并发误判 / 自动清理 stale lock 失误 / atomic rename 跨 drive 失败兜底走 `shutil.move`（已实现，但仍非首选场景）。

---

## 附录 A：完整 cli flag 速查

详见 cad-help-guide §7.3.1，本附录是缩略表：

| flag | 默认 | 含义 |
|---|---|---|
| `--subsystem <name>` | 必填（除 `--list-profiles` / `--last-status`） | 与 photo3d-* 一致 |
| `--config <path>` | `~/.claude/cad_jury_config.json` | 路径必须 `~/.claude/` 或项目内；越界需 `--allow-external-config` |
| `--allow-external-config` | false | 显式允许 `--config` 越界 |
| `--profile-id <id>` | active_profile_id | 临时切 profile |
| `--list-profiles` | false | 列 profile；不调 LLM |
| `--last-status` | false | 复述上次 jury 报告；不调 LLM |
| `--budget <usd>` | `0.1` | 单 run 费用上限；NaN/inf/负数 → exit=2；`= 0` 时只允许 cost=0 profile |
| `--confirm-cost` | false | 超 budget 必填；不旁路 `max_n_views` |
| `--dry-run` | false | 跑 Layer 0/1 + cost 预估，不调 LLM 不写报告 |
| `--max-retries <n>` | `2` | LLM 失败重试上限；`< 0` → exit=2 |
| `--debug-output <path>` | 自动 | 4xx/parse_failed 时落脱敏 jury_debug_<view>.json |
| `--force` | false | 既有报告时不归档强制覆盖（默认是归档后再写） |
| `--project-root <path>` | cwd | 与 photo3d-* 一致 |

---

## 附录 B：exit code 速查

| exit | 含义 | 典型恢复 |
|---|---|---|
| 0 | 成功（status=accepted/preview/needs_review） | 看 stderr 模板提示 |
| 1 | Layer 0 输入证据错（blocked） | 检查 enhance-check 是否真 accepted；跑 `photo3d-recover` |
| 2 | 配置错（jury config / cli flag） | 看 stderr 哪个字段错；改 config 或 cli |
| 3 | 成本超 budget 未确认 | 加 `--confirm-cost` 或调 `--budget` |
| 4 | `.jury.lock` 已存在（另一进程在跑） | 等它结束或检查 stale lock |
| 99 | 工具内部错误 | 提 issue 附 PHOTO3D_JURY_REPORT.json + cli args（已 redact） |

---

## 相关文档

- [cad-help-guide-zh §7.3.1](cad-help-guide-zh.md#731-完整-photo3d-闭环-cli-序列外行用户必读)：完整 4 步 photo3d 闭环（handoff → jury → enhance-review → deliver）
- [photo3d-jury spec rev 5](superpowers/specs/2026-05-08-photo3d-jury-design.md)：架构、契约、测试、安全护栏的完整设计
- [photo3d-jury plan](superpowers/plans/2026-05-08-photo3d-jury-plan.md)：27 task 实施计划
