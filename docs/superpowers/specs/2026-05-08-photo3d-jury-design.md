# Photo3D Jury — 自动照片级验收闭环 设计文档

- **日期**：2026-05-08
- **作者**：项目 + Claude（superpowers brainstorming skill 引导）
- **目标版本**：v2.27.0（独立 PR，不与 §11 cleanup 合并）
- **状态**：rev 3（4 层审查全完成；总累计 17+6=23 BLOCKER + 32+12=44 MAJOR + 21+6=27 MINOR = 94 findings 全闭）

## 修订历史

- **rev 1**：初稿 + 自审修字段路径漂移（views[].edge_similarity 顶层 / quality_metrics.effective_contrast_stddev / Layer 0/1 拆分）
- **rev 3**：第 3 层 code-spec 对照实测（grep 真代码）+ 第 4 层 holistic dry-run（4 路径 state lifecycle）共 6 BLOCKER + 12 MAJOR + 6 MINOR = 24 findings 全闭：
  - **CLI 注册纠正**：`photo3d-jury` 走 `cad_pipeline.py jury` subcommand dispatch（与既有 photo3d-* 一致），不走 pyproject `[project.scripts]`
  - **`.jury.lock` 复用既有资产**：抽 `tools/_file_lock.py` 复用 `tools/sw_warmup.py:acquire_warmup_lock` 模式（msvcrt.locking + fcntl.flock），不重发明
  - **lock 释放闭环**：`§3.4` 加不变量 11 try/finally 释放覆盖所有 status + 异常路径；mtime > 30 min 或 PID not exists 自动清理
  - **fail-fast vs fail-soft 区分**：Layer 间硬串行（fail 立即 return）；Layer 2 视角间 fail-soft（继续跑下一视角）显式说明
  - **按 status 字段填充矩阵**：blocked/preview/needs_review/accepted 各 status 下 PHOTO3D_JURY_REPORT.json 字段形态
  - **review-input 必填集**：`source_reports` + 所有 `_sha256` 必填（非可选）；project_relative 已 posix 不重复 .as_posix()
  - **base_url 智能判断**：jury 自己处理 base_url 是否含 `/v1`，与 gemini_gen.py:46 已知 bug 解耦
  - cli 参数互斥矩阵；--list-profiles 输出 schema；needs_review next_step 占位符具体填法
  - assert_within_project 必传 label；HTTPError.url 用 getattr；HTTPConnection.debuglevel 行为限制
  - tests/jury/ 之外 cli 薄壳测试不被 autouse kill switch 覆盖（解决方案）；freeze 是单次 cli 调用 scoped
- **rev 2**：5 角色对抗审查（code-spec drift / edge case / test gap / security / north star compliance）累计 70 findings 全闭：
  - 安全：api_key try/except 兜底防 traceback locals dump / `--config` 路径限制 / 图大小上限 / 视角数硬上限 / TLS 错误类别 / reason 落盘前过滤控制字符
  - 资源/竞态：sha256 freeze 防漂移 / `.jury.lock` 防并发 / active_run_id freeze / socket timeout / Retry-After clamp / cost_per_call_usd=0 旁路 budget 防爆
  - UX：内置 model→cost 估价表（cost_per_call_usd 降为可选 override）/ 4 status 都给 ordinary_user_message + 下一步命令 / stderr 中文人话提示 / `--list-profiles` 故障恢复
  - 决策：photoreal_score 显式不参与 status 决策（但 MIN_PHOTOREAL_SCORE 守门） / needs_review 时不写 jury_review_input.json（或 .partial.json）
  - 测试：Layer 0 专属 test_input_evidence_binding.py / api_key 不落盘 + kill switch 测试归属 / fixture 静态提供 / fixture key 用 `dummy-` 前缀

---

## 1. 背景与北极星对齐

### 1.1 现状

Phase 5 增强 6 个 preset 已能调用真实云端 vision API：

- `fal` / `fal_comfy` — fal.ai Flux ControlNet（FAL_KEY env）
- `gemini` — Gemini OpenAI 兼容（`~/.claude/gemini_image_config.json`）
- `comfyui` — 本地 ComfyUI HTTP
- `engineering` — 零 AI 工程兜底
- `default` — 委派 project enhance config

验收双层已存在：

- **`enhance-check`**（`tools/enhance_consistency.py`）— 确定性层，IoU ≥ 0.85 + pixel metrics
- **`enhance-review`**（`tools/enhancement_semantic_review.py`）— 语义层，5 项 boolean (`geometry_preserved` / `material_consistent` / `photorealistic` / `no_extra_parts` / `no_missing_parts`)，**人工** `--review-input` JSON 填写

### 1.2 真断点

5 项 semantic check 的 `photorealistic` 字段是判定"真照片级"的核心，但**完全靠人工填**。导致：

- 自动管线最多止于 `enhance-check` 的轮廓 / 像素层
- "结果准确"北极星 gate 实际处于"靠用户主观"的状态
- 每次跑完管线都要人工目检 N 视角并写 JSON

### 1.3 本 PR 范围

新增 `photo3d-jury` cli：旁路新工具，**不改既有契约**。读 ENHANCEMENT_REPORT.json，跑 deterministic fast-fail + LLM vision jury，输出两份 JSON（自身报告 + `enhance-review --review-input` 兼容文件）。让 5 项 semantic check 可由配置好的 vision LLM 自动给出。

### 1.4 北极星 5 gate 自检

| Gate | 设计应对 |
|---|---|
| 零配置 | 用户首次跑 jury 才需写 1 份 jury config；无 jury config 时 cli 给清晰错误 + 配置示例链接，不打扰其他工具 |
| 稳定可靠 | LLM 失败默认 `needs_review`（不擅自 accepted）；不自动 fallback 到下一 profile（避免隐式多扣费）；retries 上限固定 |
| 结果准确 | LLM 给 5 boolean + photoreal_score；Layer 0 拦未通过 enhance-check 的输入；Layer 1 拦字段自洽性损坏的输入；NIQE/BRISQUE v2 增强 |
| SW 装即用 | 与 SW 完全无关；配置文件位置与现有 `gemini_image_config.json` 同位（`~/.claude/`） |
| 傻瓜式操作 | 一条 `photo3d-jury --subsystem X`；超 budget 才要 `--confirm-cost`；输出直接喂下一条命令 |

---

## 2. 范围与非目标

### 2.1 In Scope（v1）

- 新 cli `photo3d-jury` + `tools/photo3d_jury.py`
- 新模块组 `tools/jury/`（5 个文件，单一职责）
- 新配置 schema `~/.claude/cad_jury_config.json`（`schema_version=1`，仅 `kind=openai_compat`）
- LLM 调用：`urllib.request` 直接发 HTTP（与现有 `gemini_gen.py` 风格一致；不引新 SDK 依赖）
- 双输出：`PHOTO3D_JURY_REPORT.json` + `jury_review_input.json`（兼容 `enhance-review --review-input`）
- 完整测试矩阵（单元 + 集成 mock HTTP；可选手动真实 LLM 烟测）
- mypy strict + ruff + 95% 覆盖率（与 sw_config_broker 同档）

### 2.2 Out of Scope（v2 或后续）

- `kind = anthropic_native`（v1 仅 openai_compat；Anthropic 用户走中转）
- 自动 fallback profile chain（key 到期自动切下一家）
- 月度 quota tracker（`~/.claude/cad_jury_quota.json`）
- 集成进 `photo3d-handoff --with-jury`（v1 用户独立跑 jury cli）
- 真无参考图像质量分（NIQE / BRISQUE / aesthetic）—— v1 复用现有 `qa_image` 输出
- 多视角投票 / 多 profile 交叉验证

### 2.3 显式不做

- **不读图原始文件**：Layer 0 / Layer 1 都只读 `ENHANCEMENT_REPORT.json` 已落盘字段（顶层 status / quality_summary / per-view edge_similarity / quality_metrics）；保证与 `enhance-check` 0 漂移
- **不修改 active_run 状态**：jury 是旁路工具，不写 `ARTIFACT_INDEX.json`，不切 `active_run_id`
- **不写 api_key 进任何文件**：报告只记 `profile_id` / `model`
- **不打日志带响应体**：错误只记 `http_status` + `error_kind`

---

## 3. 架构

### 3.1 上下文图

```
                ┌────────────────────────────────────────────────┐
                │  现有 Phase 5 验收双层（不动）                  │
                │  ┌──────────────┐    ┌────────────────────┐    │
                │  │enhance-check │ →  │ENHANCEMENT_REPORT  │    │
                │  │(IoU+pixel)   │    │.json (deterministic)│    │
                │  └──────────────┘    └────────────────────┘    │
                │                            ↓                    │
                │  ┌──────────────────────┐  ↓                    │
                │  │enhance-review        │←─┘                    │
                │  │--review-input *.json │←─人工 5 boolean       │
                │  └──────────────────────┘   旧路径仍在           │
                └────────────────────────────────────────────────┘
                                ↓ 不改契约
                ┌─────────────── 新增 ──────────────────────────┐
                │     photo3d-jury  (新 cli)                     │
                │   顶层 try/except 兜底（防 traceback locals    │
                │   dump 含 api_key；redact url/header/body）    │
                │                                                │
                │   入口 → Layer 0 输入证据绑定 + 资源/竞态防护  │
                │           file/run_id/sha256 freeze /          │
                │           delivery_status / quality_summary /  │
                │           views 非空 / max_n_views /            │
                │           max_image_bytes / .jury.lock /       │
                │           --config 路径校验                     │
                │           fail → blocked / exit=1 (lock=4)     │
                │              ↓ pass                             │
                │         Cost 预估（含内置估价表）+ budget 守门 │
                │           fail → exit=3 不写报告                │
                │              ↓ pass                             │
                │         Layer 1 deterministic 字段自洽性        │
                │           per-view edge_similarity /            │
                │           effective_contrast_stddev (None ok)  │
                │           fail → preview，不调 LLM              │
                │              ↓ pass                             │
                │         Layer 2 LLM jury                        │
                │           openai_compat HTTP, 每视角 1 调      │
                │           timeout=60 / Retry-After clamp [1,60]│
                │           失败 → needs_review (该视角)         │
                │              ↓                                  │
                │         photoreal_score gate (≥ min)            │
                │           5 bool 全 true 且 score≥min →accepted │
                │           score<min → preview                   │
                │              ↓                                  │
                │   出口 → (1) PHOTO3D_JURY_REPORT.json (永远)   │
                │          (2) jury_review_input.json             │
                │              (仅 accepted 时写；防污染下游)     │
                └────────────────────────────────────────────────┘
                                ↓
                用户自跑: enhance-review --review-input .../jury_review_input.json
                                ↓
                ENHANCEMENT_REVIEW_REPORT.json (现有契约不改)
```

### 3.2 文件布局

**CLI 注册**：`photo3d-jury` 不走 `pyproject.toml [project.scripts]`；走 `cad_pipeline.py` 现有 subcommand dispatch（与 `photo3d-handoff` / `photo3d-deliver` / `photo3d-recover` 等一致）。即用户调 `cad_pipeline.py jury --subsystem ...`，alias 在 `skill.json` 注册成 `photo3d-jury`。

```
cad_pipeline.py                      ← 既有；加 `jury` subcommand 转发到 tools/photo3d_jury:main
tools/photo3d_jury.py                ← jury 主入口 + 顶层 try/finally 兜底（释放 lock + 防 traceback locals dump）+ 报告组装（薄壳）
tools/_file_lock.py                  ← 抽离 `tools/sw_warmup.py:acquire_warmup_lock` 通用 cross-platform lock context manager（msvcrt.locking + fcntl.flock）；jury 与 sw_warmup 共用
tools/jury/
    __init__.py
    config.py                        ← profile 解析 / active 选取 / 校验 / 内置估价表 / base_url 智能判断（含/v1 跳过）
    cost.py                          ← 预估 + budget 守门
    input_evidence_binding.py        ← Layer 0 + sha256/active_run freeze + 调 _file_lock 创建 .jury.lock + stale 自动清理
    deterministic_gate.py            ← Layer 1 字段自洽性
    llm_client.py                    ← Layer 2 HTTP 调用 + 重试 + redact + kill switch
    verdict.py                       ← LLM 响应 → 结构化 + reason 防 injection（纯函数）
    manual_smoke.py                  ← 手动真实 LLM 烟测脚本（不进 CI / 不计 cov）
tests/jury/
    __init__.py
    conftest.py                      ← autouse kill switch + dummy fixture key（覆盖整个 tests/jury/ 子树）
    test_photo3d_jury_cli.py         ← cli 薄壳测试（**移到 tests/jury/ 下而非 tests/ 顶级**，确保被 autouse 覆盖）
    fixtures/
        sample_enhancement_report.json
        sample_render_manifest.json
        sample_artifact_index.json
        intentional_type_error.py    ← mypy strict negative case
    test_config.py
    test_cost.py
    test_input_evidence_binding.py   ← Layer 0 专属
    test_deterministic_gate.py       ← Layer 1 专属
    test_llm_client.py
    test_verdict.py
    test_photo3d_jury_e2e.py         ← 集成（mock HTTP）+ 链路正反 e2e
docs/cad-jury-config.md              ← 用户级配置说明（key/base_url 怎么填 + host 风险 + TLS CA）
```

### 3.3 模块契约表

| 模块 | 单一职责 | 输入 | 输出 | 不做 |
|---|---|---|---|---|
| `config.py` | profile schema 解析 / active 选取 / 字段校验 / 内置估价表查询 / 顶层 caps（max_image_bytes / max_n_views / min_photoreal_score）解析 | jury config 路径 + 可选 override profile_id | `JuryProfile` dataclass + `JuryCaps` dataclass | 不发 HTTP / 不读图 / 解析后立即丢 raw dict |
| `cost.py` | budget 计算 + 阈值比较 + cost=0 警告 | `JuryProfile.cost_per_call_usd`, `n_views`, `budget_per_run_usd`, `confirm_cost: bool` | `CostDecision{ allowed, estimated_usd, reason }` | 不调 LLM / 不记账 |
| `input_evidence_binding.py` | Layer 0 全责：active_run + sha256 freeze、`.jury.lock`、`--config` 路径校验、图大小预检、max_n_views 校验、所有 blocked 类目 | `argparse.Namespace`（cli 已解析）、project_root、`JuryCaps` | `Layer0Verdict{ pass, frozen_run_id, frozen_sha256, blocking_reasons[] }` 或抛 `JuryConfigError` (exit=2) / `JuryLockBusy` (exit=4) | 不读图（除 size）/ 不调 LLM / 不写报告（cli 写） |
| `deterministic_gate.py` | Layer 1 per-view 字段自洽性（输入到此前已 Layer 0 通过） | `ENHANCEMENT_REPORT.json` dict | `Layer1Verdict{ pass, per_view_failures }` | 不读图 / 不再算指标 / 不引新阈值（沿用 enhance-check 已经判过的字段） |
| `llm_client.py` | Vision API 调用 + 重试 + redact + kill switch + 显式 timeout=60 + debuglevel=0 | `JuryProfile`, `enhanced_image_path`, `prompt`, `max_retries` | `LlmResponse{ content_text, http_status, attempts, latency_ms }` 或抛 `JuryLlmError` 子类（含 `JuryDisabledByEnv`） | 不解析 verdict / 不计费 / 不打日志含 body 或 url 含 query |
| `verdict.py` | LLM 文本 → 结构化 5 boolean + score + reason 防 injection 过滤（纯函数） | `LlmResponse.content_text` | `ViewVerdict{ semantic_checks, photoreal_score, reason_sanitized, parse_status }` | 不调 LLM / 不读文件 |
| `photo3d_jury.py` | cli + 顶层 try/except 兜底（防 traceback locals dump）+ 报告组装（4 status 文案 + next_step）+ status 决策（含 photoreal_score gate） | argv + project_root + subsystem | 写 `PHOTO3D_JURY_REPORT.json`（永远写）+ `jury_review_input.json`（仅 accepted 写） | 不实现具体校验/调用逻辑 |

### 3.4 不变量

1. `config.py` 之外没人读 jury config 文件
2. `llm_client.py` 之外没人调 HTTP
3. `verdict.py` 是无副作用纯函数
4. 所有写入走 `tools/contract_io.py:write_json_atomic` + `tools/path_policy.py:assert_within_project(path, project_root, label)`（**`label` 参数必填**，作错误消息 prefix）；jury 报告字段经 `tools/path_policy.py:project_relative` 后已是 posix（内部已 `.relative_to(root).as_posix()`），**不要重复 `.as_posix()`**
5. api_key 永不进任何 .json / 异常 / 日志 / url query / stack frame long-lived locals
6. **Layer 0 → Layer 1 → Layer 2 串行硬约束**：层间 fail-fast，每层只在前层全 pass 时才跑；fail 立即 return 不跑后续层。**Layer 2 内视角间是 fail-soft**：任一视角 LLM 失败时该视角 verdict=needs_review，**继续跑下一视角**（不 abort 整个 Layer 2）；最终 status 由所有视角汇总后取最高优先级（§4.6）
7. **active_run_id + sha256 在 Layer 0 freeze**：全程不重读；写报告前再算一次若漂移 → status=blocked。Freeze 是单次 cli 调用 scoped 进程内变量；测试用 fixture 必须 reset；不依赖 module-global 持久化
8. **jury_review_input.json 仅 status=accepted 写**：其他 3 状态都不写（防污染下游）
9. **photoreal_score 决策角色**：5 boolean 全 true + score ≥ min_photoreal_score 才 accepted；否则降 preview
10. **api_base_url 智能判断**：jury 自己处理 base_url（含 `/v1` 跳过；不含 `/v1` 自动追加；rstrip 末尾斜杠）；与 `gemini_gen.py:46` 已知 bug（`f"{api_base}/v1/..."` 无脑拼）解耦
11. **`.jury.lock` 必 try/finally 释放**：覆盖所有 status 与未捕获异常路径（实现走 contextmanager pattern）；进程异常退出后 stale lock 自动清理策略：mtime > 30 min **或** 写入的 PID 在系统不存在 → 下一次 cli 自动覆盖 + stderr 警告告知用户残留是哪次 PID（外行用户避坑，不让"傻瓜式"被卡住）

---

## 4. 数据流

### 4.1 输入：jury 配置

`~/.claude/cad_jury_config.json`：

```json
{
  "schema_version": 1,
  "active_profile_id": "gemini-aihubmix",
  "max_image_bytes": 8388608,
  "max_n_views": 32,
  "profiles": [
    {
      "id": "gemini-aihubmix",
      "kind": "openai_compat",
      "api_base_url": "https://aihubmix.com/v1",
      "api_key": "sk-xxx",
      "model": "gemini-2.5-flash",
      "cost_per_call_usd": null,
      "comment": "默认中转，余额充足；cost_per_call_usd=null 时由内置估价表查 model"
    },
    {
      "id": "gpt-4o-native",
      "kind": "openai_compat",
      "api_base_url": "https://api.openai.com/v1",
      "api_key": "sk-yyy",
      "model": "gpt-4o",
      "cost_per_call_usd": 0.020
    }
  ]
}
```

**校验规则**：

- `schema_version == 1`，否则 `JuryConfigSchemaError`
- `active_profile_id` 必须命中 `profiles[].id`
- `profiles` 非空列表
- 每 `profile.id` 唯一；正则 `^[A-Za-z0-9_-]+$`（防 Unicode/含空格 id 在 CI artifact / log 出问题）
- `kind ∈ {"openai_compat"}`（v1）
- `api_base_url` 必须 `https://` 开头（防误填 http）；解析时 `rstrip("/")` 去末尾斜杠
- **base_url 智能 `/v1` 处理**：解析后若已含 `/v1`（如 `https://api.openai.com/v1`）则保留；不含则追加 `/v1`（如 `https://api.openai.com` → `https://api.openai.com/v1`）。jury 调用拼 `{normalized_base}/chat/completions`。这与 `gemini_gen.py:42-46` 无脑拼（任何 base 后强加 `/v1`，会让 `.../v1` + `/v1/chat` = `/v1/v1/chat`）的行为不同；jury 实施 reviewer 必须验证此处不抄旧代码
- `api_key` 非空字符串
- `model` 非空字符串
- `cost_per_call_usd` 可选；`null` 或缺省 → 内置估价表查 `model`（见下）；显式给数字时必须 ≥ 0；显式 `0` 强制要求 `--confirm-cost` 或在 cli 给 prompt 警告"模型免费时 jury 仍可能消耗下游配额"
- 顶层 `max_image_bytes`：可选，默认 `8 * 1024 * 1024`（8 MiB）；任一视角增强图 > 此值 → 该视角 `error_kind=image_too_large` 不调 LLM（防 b64 内存爆 + 单次费用暴涨）
- 顶层 `max_n_views`：可选，默认 `32`；ENHANCEMENT_REPORT.json 中视角数超此值 → 整体 `JuryConfigError`（即使 `--confirm-cost` 也不旁路）
- 解析后只返 `JuryProfile` dataclass + 顶层 caps；原 dict 在 `config.py` 内立即丢弃（防 key 通过返回值泄漏）；`api_key` 装入 dataclass 后，配置加载函数局部不应再保留中间字符串变量

**内置 model→cost 估价表**（`config.py` module-level 常量 `BUILTIN_MODEL_COST_USD`，可被显式 `cost_per_call_usd` override）：

| model 模式（前缀匹配） | 默认 cost_per_call_usd | 说明 |
|---|---|---|
| `gpt-4o`, `gpt-4o-*` | 0.020 | OpenAI 官方公开计价（约值；按 1024×1024 图 + 256 token 输出粗估） |
| `gpt-4-turbo*` | 0.030 | 同上 |
| `gemini-2.5-flash*`, `gemini-1.5-flash*` | 0.005 | Google AI Studio 公开计价（约值） |
| `gemini-2.5-pro*`, `gemini-1.5-pro*` | 0.015 | 同上 |
| `claude-*-vision*`, `claude-3-*` | 0.025 | Anthropic 公开计价（约值） |
| 不匹配 | 由 cli 警告 + 强制 `--confirm-cost` 才能跑（外行用户避坑） |  |

**重要免责**：估价表是 v1 的"约值兜底"，与真实计费可能 ±50% 偏差（vision 实际按 input/output token + image megapixels 多维计费）。用户对成本敏感时应：(a) 先 `--dry-run` 观察 estimated；(b) 显式填 `cost_per_call_usd` 按自己最新观测的真值。

**v1 特殊配置项**（用户可在 jury config 顶层覆盖）：

- `min_photoreal_score`：默认 `60`；LLM 返 `photoreal_score < min_photoreal_score` 时该视角 verdict 退到 `preview`（即使 5 boolean 全 true）。设 `0` 关闭此 gate。详见 §4.6。

### 4.2 LLM prompt 模板（每视角一次）

```text
你是一名 CAD 渲染照片级验收员。下面这张图来自一台机械产品的多视角渲染增强后输出。
请按以下 5 项判断（各只出 true/false）：
1. geometry_preserved   — 几何与设计一致，无明显形变/丢件
2. material_consistent  — 材质风格统一，无明显错配（金属/塑料/橡胶）
3. photorealistic       — 视觉质感像真实拍摄而非 3D 渲染
4. no_extra_parts       — 没有 LLM 凭空加出的零件、装饰、文字
5. no_missing_parts     — 没有把原本存在的零件擦除

另给 photoreal_score（0-100 整数，单独度量第 3 项的强度）。

只返回严格 JSON：
{"semantic_checks":{"geometry_preserved":bool,"material_consistent":bool,
"photorealistic":bool,"no_extra_parts":bool,"no_missing_parts":bool},
"photoreal_score":int,"reason":"<= 80 字"}

不要 markdown 代码块。不要解释。
```

**HTTP body**（严格 OpenAI Chat Completions 兼容，POST 到 `<normalized_base_url>/chat/completions`，其中 `normalized_base_url` 由 `config.py` 智能处理 — `api_base_url` 含 `/v1` 则保留、不含则追加；与 `gemini_gen.py:42-46` 已知 bug 解耦）：

```json
{
  "model": "<profile.model>",
  "messages": [
    {"role": "user", "content": [
      {"type": "text", "text": "<上面的 prompt>"},
      {"type": "image_url",
       "image_url": {"url": "data:image/png;base64,<b64 of enhanced image>"}}
    ]}
  ],
  "max_tokens": 512,
  "temperature": 0.0
}
```

`temperature=0` 是默认，目的是输出稳定。`parse_failed` 后第二次重试也是 `temperature=0`（同次请求同输入应当一致，重试主要为对抗偶发抖动而非求多样性）。

**HTTP 调用约束**：

- `urllib.request.urlopen(req, timeout=60)` 强制；socket 默认无限等会让 jury 在故障 LLM 服务下卡死
- 单视角 `max_total_seconds_per_call=120`（含重试） 超时强行 abort 该视角进入 `error_kind=timeout`
- response charset：按 `Content-Type: application/json; charset=<X>` 解码；缺省 utf-8；中转商返非 utf-8 时 fallback latin-1 不让 UnicodeDecodeError 炸
- `Content-Type` 非 `application/json*` 且 body 不是 JSON → `error_kind=non_json_response`，不重试，避免在 HTML 错误页上无限重试
- 显式 `http.client.HTTPConnection.debuglevel = 0` 写在 `llm_client.py` 顶部 import 后（覆盖外部 logging level=DEBUG / 用户全局 debuglevel=1 的 全 dump 行为，防 Authorization 进 debug log）
- TLS：urllib 默认走系统 SSL；企业 MITM 自签 CA 由用户通过 `SSL_CERT_FILE` env 注入；**严禁** `ssl._create_unverified_context()`（哪怕 env flag 都不允许）
- TLS 校验失败映射 `error_kind=tls_verification_failed`（独立类别，便于用户读报告知道是证书问题）

**关于 `api_base_url` 路径**：spec **不再要求**用户必填完整 `/v1`；`config.py` 在解析时自动判断 base_url 是否含 `/v1`，含则保留、不含则追加（详见 §4.1 校验规则）。这让外行用户填 `https://api.openai.com` 或 `https://api.openai.com/v1` 都能跑（傻瓜式 gate 兼容）。**这与 `gemini_gen.py:42-46` 无脑拼接（任何 base 后强加 `/v1`，会让 `.../v1` 输入产 `/v1/v1/chat` 错路径）的行为不同**——jury 实现禁止抄 gemini_gen 的拼接策略，要在 CP-1 `config.py` 测试用例显式覆盖 4 种 base_url 形态（含/v1 / 不含 / 末尾斜杠 / 无斜杠）防回归。

### 4.3 三层验证（Layer 0 → Layer 1 → Layer 2）执行顺序硬规定

**顺序硬约束**：Layer 0 → Layer 1 → Layer 2 严格串行；Layer 0 fail 即立即 return blocked，**不得**跑 Layer 1；Layer 1 fail 即立即 return preview，**不得**调 LLM。每层都受其前层保证（防止实现 subagent 漂移成"先跑 Layer 1 再 Layer 0"）。

#### Layer 0 — 输入证据绑定 + 资源/竞态防护（jury 入口立即跑，fail → blocked, exit=1）

| 字段 / 校验 | 期望 | fail → status |
|---|---|---|
| `ENHANCEMENT_REPORT.json` 文件存在 + 可读 | yes | `blocked` |
| `report["subsystem"]` | 与 cli `--subsystem` 一致 | `blocked` |
| `report["run_id"]` | 与 ARTIFACT_INDEX `active_run_id` 一致 | `blocked` |
| `index["active_run_id"]` 对应 `index["runs"][active_run_id]["active"] == True` | yes（参考 `enhancement_semantic_review.py:46-48`） | `blocked` |
| `report["status"]` | `"accepted"` | `blocked` |
| `report["delivery_status"]` | `"accepted"`（与 enhance-review 用同一优先级语义；`enhance_consistency.py:191-192` 同时写两字段） | `blocked` |
| `report["quality_summary"]["status"]` | `"accepted"` | `blocked` |
| `report["views"]` | 非空列表（views=[] 视为"无内容假通过"应 blocked） | `blocked` |
| `len(report["views"]) ≤ max_n_views`（默认 32） | yes | `blocked` |
| **每视角增强图大小** `os.path.getsize() ≤ max_image_bytes` | yes | `blocked`（防 b64 内存爆 + 单次费用暴涨） |
| **active_run_id freeze**：jury 在此层一次性读 ARTIFACT_INDEX 取 active_run_id，**全程冻结**用此值；写入路径用冻结值 | — | 写报告前再读 ARTIFACT_INDEX 不一致 → status=`blocked` 且不写文件到新 run dir |
| **sha256 freeze**：jury 在此层计算 ENHANCEMENT_REPORT + render_manifest 的 sha256，全程不再读；写报告前再算一次若漂移 → status=`blocked` | — | 防 Layer 2 LLM 跑 N 分钟时报告被改导致下游 enhance-review hash mismatch |
| **`.jury.lock` 文件锁**：active run dir 内创建 `.jury.lock`（含 PID + ISO timestamp）；已存在 → exit=4 + 提示用户 stale 移除（防并发双跑互相覆盖费用白扣） | — | exit=4，不写报告 |
| `--config <path>` 解析后绝对路径必须满足以下任一：(1) 在 `~/.claude/` 下；(2) 在项目内（`assert_within_project`）；(3) 显式带 `--allow-external-config` flag | — | `blocked` |

**意图**：用户未通过 enhance-check 的报告**根本不应该**进 jury 流程；任何"声称 accepted"的字段不一致 / 资源越界 / 并发冲突在 cli 入口就 fast-fail。

#### Layer 1 — `deterministic_gate.py` 内部自洽性二次验证（defense-in-depth；fail → preview, exit=0）

输入到达此层时，Layer 0 已保证 `report["status"]=="accepted"` / `quality_summary.status=="accepted"` / views 非空且数量在 cap 内 / 每视角图大小合规。本层只做"声称 accepted 时各 per-view 字段是否真自洽"：

| 字段路径 | 期望 | fail → status |
|---|---|---|
| `views[].status`（每视角） | `"accepted"` | `preview` |
| `views[].edge_similarity`（每视角） | `≥ report["min_similarity"]`（缺省 fallback 0.85） | `preview` |
| `views[].quality_metrics`（字段存在） | 非空 dict | `preview` |
| `views[].quality_metrics["effective_contrast_stddev"]` | 非 `None` 且 `≥ MIN_PHOTO_CONTRAST_STDDEV`（12.0；与 `tools/enhance_consistency.py` 同值） | `preview`（None 视作 fail，因 enhance_consistency 在 subject_roi 分支可能写 None） |

**设计意图**：v1 不引入新图像质量指标（NIQE/BRISQUE/aesthetic 留 v2）。Layer 1 角色是"对手工编辑/部分写入损坏的报告做内部矛盾检测"——若顶层声称 accepted 但单视角字段否决，整体降级 preview 且**不调 LLM**（节费）。

**正常情况下**：用户没改过 ENHANCEMENT_REPORT.json 且 enhance-check 跑成功，Layer 1 100% 通过；成本接近 0。NIQE/BRISQUE 真无参考分到 v2 时替换/扩展本层。

阈值常量（12.0）在 `deterministic_gate.py` 顶部 module-level 定义；测试断言 `pytest.approx` 比较它与 `tools/enhance_consistency.py:MIN_PHOTO_CONTRAST_STDDEV` 同值（不用 `is` identity，防 enhance_consistency 改成动态读时静默失效）。

#### Layer 2 — LLM jury（fail → needs_review, exit=0；详见 §5.2）

每视角 1 次 vision API call；解析失败 / HTTP 失败 / quota 等映射到 `error_kind`（§5.2）。整体 status 决策见 §4.6。

### 4.4 输出 1：`PHOTO3D_JURY_REPORT.json`

落 `cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>/PHOTO3D_JURY_REPORT.json`（路径用 forward-slash posix，**不**用 Windows backslash —— 与 `enhance_consistency.py:_norm` / `enhancement_semantic_review.py:_norm` 同口径，防下游 enhance-review path mismatch blocker）：

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-08T12:34:56Z",
  "subsystem": "lifting_platform",
  "run_id": "20260508-123456",
  "status": "accepted",
  "ordinary_user_message": "自动验收通过，可作为 enhance-review 的 review-input 输入。",
  "next_step": "enhance-review --review-input cad/lifting_platform/.cad-spec-gen/runs/20260508-123456/jury_review_input.json",
  "source_reports": {
    "render_manifest":          "cad/output/renders/.../render_manifest.json",
    "render_manifest_sha256":   "sha256:<64hex>",
    "enhancement_report":       "cad/output/renders/.../ENHANCEMENT_REPORT.json",
    "enhancement_report_sha256": "sha256:<64hex>"
  },
  "jury_meta": {
    "profile_id":           "gemini-aihubmix",
    "model":                "gemini-2.5-flash",
    "estimated_cost_usd":   0.030,
    "actual_cost_usd":      0.030,
    "budget_per_run_usd":   0.1,
    "min_photoreal_score":  60,
    "n_views":              6,
    "n_calls":              6,
    "n_retries_total":      1,
    "max_image_bytes":      8388608,
    "max_n_views":          32
  },
  "deterministic_gate": {
    "passed": true,
    "per_view_failures": []
  },
  "views": [
    {
      "view": "iso",
      "verdict": "accepted",
      "semantic_checks": {
        "geometry_preserved":  true,
        "material_consistent": true,
        "photorealistic":      true,
        "no_extra_parts":      true,
        "no_missing_parts":    true
      },
      "photoreal_score": 78,
      "reason": "金属铸件高光一致，背景虚化自然。",
      "llm_meta": {
        "http_status":  200,
        "attempts":     1,
        "latency_ms":   2103,
        "parse_status": "ok",
        "error_kind":   null
      }
    }
  ],
  "blocking_reasons": []
}
```

**关于 `actual_cost_usd`**：每次真发 HTTP 请求都计入 `actual_cost_usd`（含 `network_unreachable` / `rate_limited` / `parse_failed` 等所有重试，因为对方服务通常在 4xx/5xx 也可能扣费 — 保守计入）。`estimated_cost_usd = n_views × cost_per_call_usd`（不含重试估算）。两者偏差 = 重试导致的额外成本，便于用户事后判断是否需要换 profile。

**关于 `reason` 字段防 prompt injection**：

- `reason` 落盘前必须经 `verdict.py` 处理：(a) 截 80 字（基于 Unicode 字符长度）；(b) 剥控制字符 `\x00-\x1f\x7f`；(c) 剥 ANSI escape 序列（防 `cat PHOTO3D_JURY_REPORT.json` 在 terminal 触发注入）；(d) 不接受 newline，多行折叠为空格
- 若 LLM 返超长或含被剥字符，`llm_meta.parse_status="reason_sanitized"`（仍 verdict 走原决策）

**关于 `generated_at`**：必须 UTC ISO8601（如 `2026-05-08T12:34:56Z`）；不接受 local timezone（用 `datetime.now(timezone.utc).isoformat()`）。

**关于 `ordinary_user_message` 与 `next_step`**：每个 status 都必须给（不止 accepted）：

| status | ordinary_user_message | next_step |
|---|---|---|
| `accepted` | "自动验收通过，可作为 enhance-review 的 review-input 输入。" | `enhance-review --review-input <path>/jury_review_input.json` |
| `preview` | "增强图未通过自动验收（{N}/{M} 视角字段自洽性不足或 LLM 判定降级），仅作预览。" | `enhance --provider <preset> --resubmit` 重跑增强或人工目检后手填 review-input |
| `needs_review` | "{K}/{M} 视角自动验收失败（{error_kinds}）；建议重跑或换 profile。" | `photo3d-jury --profile-id <fallback_id>`，其中 `<fallback_id>` 由 jury 直接填**当前 config.profiles 中除 active_profile_id 外按 id 字典序第一个**；若 config 仅 1 profile 则提示 `--list-profiles 后在 ~/.claude/cad_jury_config.json 加新 profile` |
| `blocked` | "证据与 active run 不一致（{first_blocking_code}）；不能作为照片级判定输入。" | `photo3d-recover --subsystem <X>` + 检查 enhance-check 是否真 accepted |

`{N}/{M}` / `{K}/{M}` / `{error_kinds}` / `{first_blocking_code}` / `<fallback_id>` 由实现层填充（不留 `<>` 占位符给用户看到）。

**按 status 的字段填充矩阵**（防止 implementer 漂移：未跑层的字段填什么？）：

| 字段 | accepted | preview (Layer 1 fail) | preview (LLM 5 bool false 或 score 低) | needs_review (LLM 部分失败) | blocked (Layer 0 fail) | blocked (sha freeze drift) |
|---|---|---|---|---|---|---|
| `status` | accepted | preview | preview | needs_review | blocked | blocked |
| `source_reports.*` + `*_sha256` | freeze 值 | freeze 值 | freeze 值 | freeze 值 | 部分填（已计算的部分；未到的留 null）| **freeze 值**（保留，不是 drift 后值） |
| `jury_meta.estimated_cost_usd` | 真值 | 真值 | 真值 | 真值 | 部分跑过 cost 阶段则填，否则 null | 真值 |
| `jury_meta.actual_cost_usd` | 真值 | `0.0`（不调 LLM）| 真值（已调 LLM）| 真值（含失败重试） | `0.0` | 真值（钱已花需用户知）|
| `jury_meta.n_calls` / `n_retries_total` | 真值 | 0 | 真值 | 真值 | 0 | 真值 |
| `deterministic_gate.passed` | true | false | true | true | 未跑则 null（Layer 0 fail 时）| true |
| `deterministic_gate.per_view_failures` | `[]` | 列出 fail 视角 | `[]` | `[]` | null 或 `[]` | `[]` |
| `views[]` | 全 view 全字段 | 全 view（无 LLM 字段）| 全 view 全字段 | 全 view（失败视角 verdict=needs_review + error_kind） | 空 `[]` 或部分 | **全 view 全字段保留**（钱已花的证据） |
| `views[].llm_meta` | 真值 | 全 view 字段缺失（设 null）| 真值 | 部分 view 真值 + 失败 view error_kind | null | 真值 |
| `blocking_reasons[]` | `[]` | `[]` | `[]` | `[]` | 列出 Layer 0 fail 项 | 一条 `freeze_drift` reason + 原 freeze sha256 + 重读 sha256 |
| `next_step` / `ordinary_user_message` | accepted 模板 | preview 模板 | preview 模板 | needs_review 模板（含 fallback_id）| blocked 模板 | blocked 模板（额外提示用户检查谁改了报告）|

### 4.5 输出 2：`jury_review_input.json`（仅 accepted 时写）

**写入条件**：仅当 jury 整体 status = `accepted` 时才写 `jury_review_input.json`；其他 3 种 status 都**不写**该文件，理由：

- `preview` / `needs_review` / `blocked` 任意一种喂给 enhance-review 都会被它拒（因为 enhance-review 要求 5 boolean 全 true 才 accepted；任一 false / 缺失视角即降级）。让 jury 主动不写避免污染，并迫使用户面对 jury 的真实 verdict
- `needs_review` 时部分视角缺 verdict，写出残缺 review-input 直接喂 enhance-review 等于"自动放过这批不完整数据"——违反"稳定可靠"北极星 gate
- 用户若仍想要部分数据：`PHOTO3D_JURY_REPORT.json` 主报告永远写并含全 view 详情；用户可手抄需要的视角进自己的 review-input

兼容 `enhance-review --review-input` 现有 schema（参考 `tools/enhancement_semantic_review.py` `REQUIRED_SEMANTIC_CHECKS` + `_review_input_binding_blockers`）：

```json
{
  "schema_version": 1,
  "review_type": "auto_jury_v1",
  "subsystem": "lifting_platform",
  "run_id": "20260508-123456",
  "source_reports": {
    "render_manifest":          "cad/output/renders/.../render_manifest.json",
    "render_manifest_sha256":   "sha256:<64hex>",
    "enhancement_report":       "cad/output/renders/.../ENHANCEMENT_REPORT.json",
    "enhancement_report_sha256": "sha256:<64hex>"
  },
  "views": [
    {
      "view": "iso",
      "semantic_checks": {
        "geometry_preserved":  true,
        "material_consistent": true,
        "photorealistic":      true,
        "no_extra_parts":      true,
        "no_missing_parts":    true
      },
      "reviewer_notes": "auto_jury photoreal_score=78"
    }
  ]
}
```

**关键字段约束**（防止下游 `enhancement_semantic_review.py:_review_input_binding_blockers` 行 257-301 直接 blocked）：

- `subsystem` **必填** + 必须 == cli `--subsystem`（jury 直接抄）
- `run_id` **必填** + 必须 == jury Layer 0 冻结的 `active_run_id`（不是写报告时再读 ARTIFACT_INDEX，是冻结值）
- `source_reports` **必填**（顶层 dict，缺 dict 本身 → enhance-review `review_source_reports_missing` 直接 blocked）
- `source_reports.render_manifest` **必填**（路径字符串，由 `project_relative()` 产出已是 posix forward-slash，**不**重复 `.as_posix()`）；与 jury Layer 0 当时读到的一致
- `source_reports.enhancement_report` **必填**
- `source_reports.render_manifest_sha256` **必填**：必须 == jury Layer 0 冻结的 sha256；下游 enhance-review 用 `tools/contract_io.py:file_sha256` 重算文件并与本字段比对，差异 → `review_source_report_hash_mismatch` blocked
- `source_reports.enhancement_report_sha256` **必填**：同上
- 注意 sha256 字段值形态是 `"sha256:<64hex>"` 前缀（`contract_io.py:59-64`），不是裸 hex
- **重要**：sha256 不是写报告时再算一次；冻结防止 jury 跑 N 分钟期间被 race condition 改坏 ENHANCEMENT_REPORT 后导致 hash mismatch；若写报告前再次读发现 sha 漂移，jury status=`blocked` 整体重写主报告，不写本文件
- `review_type` 现有 schema 中可选（`enhancement_semantic_review.py:130` 用 `or "unknown"`），jury 强制写 `"auto_jury_v1"` 用于审计追溯（区分自动 vs 人工 review-input）

**`reviewer_notes` 内容**：必含 `auto_jury photoreal_score=<N>`；若 jury 跑过任何重试，追加 `retries=<N>`；若任一视角触发 `parse_status=reason_sanitized`，追加 `sanitized_views=[...]`。

### 4.6 status 取值 + photoreal_score 决策角色

**status 4 取值规则**：

| status | 触发 |
|---|---|
| `accepted` | Layer 0 + Layer 1 全 pass + 所有视角 5 boolean 全 true + 所有视角 `photoreal_score ≥ min_photoreal_score`（默认 60） + 所有视角 `parse_status=ok` |
| `preview` | Layer 1 任一视角 fail；或 LLM 任一视角 5 boolean 任一 false；或任一视角 `photoreal_score < min_photoreal_score`（即使 5 boolean 全 true） |
| `needs_review` | LLM 任一视角 HTTP 失败 / 解析失败 / `error_kind` 非 null（`auth_failed` / `quota_exhausted` / `rate_limited` 等） |
| `blocked` | Layer 0 fail（subsystem 不匹配 / SHA256 漂移 / active_run 不一致 / `report.status != accepted` / `delivery_status != accepted` / `quality_summary.status != accepted` / views=[] / 视角数超 max_n_views / 图大小超 max_image_bytes / lock 已存在 / config 路径越界） |

**优先级**：`blocked > needs_review > preview > accepted`。多种条件命中时取最高优先级。

**photoreal_score 的决策角色**（明示防歧义）：

- 取值范围：LLM 返 `[0, 100]` 整数；越界由 `verdict.py` clamp 到边界 + `parse_status=clamped`
- **不直接决定 status**：5 boolean 才是核心；`photoreal_score` 只在与 `min_photoreal_score`（默认 60）比较时充当**降级触发器**——即"5 boolean 全 true 但 photoreal_score 太低 → preview"，避免"模型说 photorealistic=true 但实际 score 只有 15"的反直觉 accepted
- 用户可在 jury config 顶层 `min_photoreal_score=0` 关掉此 gate（若信任 5 boolean 即可）
- `photoreal_score ≥ min_photoreal_score` 但任一 boolean false → 仍 preview（boolean 优先）

**`reviewer_notes` 中 score 的呈现**（与 §4.5 联动）：score 始终落 reviewer_notes，便于人工事后看；自动决策只看是否过 min_photoreal_score。

### 4.7 调用流程时序

```
$ photo3d-jury --subsystem lifting_platform --confirm-cost
[step 1/7] 读 jury config (~/.claude/cad_jury_config.json) → active=gemini-aihubmix；
            cost_per_call_usd 由 BUILTIN_MODEL_COST_USD 查 model="gemini-2.5-flash" → 0.005 USD
[step 2/7] Layer 0：ARTIFACT_INDEX 取 active_run_id="20260508-123456" → freeze
            ENHANCEMENT_REPORT.json + render_manifest.json sha256 计算 → freeze
            创建 .jury.lock（PID + ISO timestamp）
            校验 delivery_status / quality_summary.status / views 非空 / 视角数 ≤ max_n_views=32
            每视角图大小 ≤ max_image_bytes=8 MiB → 全过
[step 3/7] 预估费用：6 视角 × 0.005 USD = 0.030 USD ≤ 0.1 USD budget → 通过
[step 4/7] Layer 1 deterministic gate：6 视角字段自洽性二次验证全过
[step 5/7] Layer 2 LLM jury：6 视角依次调
              view=iso     [200 attempt=1 lat=2.1s]
              view=front   [200 attempt=1 lat=1.9s]
              ...
[step 6/7] 写报告前：再读一次 sha256 / active_run_id；与 freeze 对比
            若一致 → 继续；若漂移 → status=blocked 写主报告标记 freeze_drift
[step 7/7] photoreal_score gate：所有视角 ≥ 60 → status=accepted
            写 PHOTO3D_JURY_REPORT.json + jury_review_input.json（accepted 才写后者）
            移除 .jury.lock
✓ status=accepted  cost=0.030 USD
下一步: enhance-review --review-input cad/.../jury_review_input.json
```

### 4.8 cli 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--subsystem <name>` | 必填 | 与现有 photo3d-* 一致 |
| `--config <path>` | `~/.claude/cad_jury_config.json` | 解析后路径必须在 `~/.claude/` 或项目内；越界需 `--allow-external-config` |
| `--allow-external-config` | false | 显式允许 `--config` 指向 `~/.claude/` 或项目外的路径（防社工攻击） |
| `--profile-id <id>` | active_profile_id | 临时切 profile 不改 config |
| `--list-profiles` | false | 仅列出可用 profile id + 当前 active；不调 LLM；用于 needs_review 后用户挑下一家 |
| `--budget <usd>` | `0.1` | 单 run 费用上限 USD（外行用户友好，6 视角 × 0.005 ≈ 0.03 充裕）；`> 0` 必须；`< 0` 立即 exit=2；`= 0` 时只允许 cost_per_call_usd=0 的 profile |
| `--confirm-cost` | false | 超 budget 必填；不旁路 max_n_views 硬上限 |
| `--dry-run` | false | 跑 Layer 0 + Layer 1 + cost 预估，**不调 LLM 不写报告**；输出 cost 预估 + Layer 0/1 verdict |
| `--max-retries <n>` | `2` | LLM 失败重试上限；`= 0` 表示首发失败即归类（不重试）；`< 0` 立即 exit=2 |
| `--project-root <path>` | cwd | 与 photo3d-* 一致 |

**cli 参数互斥矩阵**（防 implementer 任选一个漂移）：

| 组合 | 行为 |
|---|---|
| `--list-profiles` 给定 | **优先级最高**，互斥所有其他 flag（除 `--config` 用于读哪个 jury_config 文件）；只列 profile + 当前 active 后 exit=0；不调 LLM、不读 ENHANCEMENT_REPORT、不创建 lock |
| `--dry-run` + `--confirm-cost` | 兼容；dry-run 仍展示超 budget 的 cost decision（不旁路）|
| `--dry-run` + `--profile-id` | 兼容；dry-run 用指定 profile 估价 |
| `--list-profiles` + `--dry-run` | list-profiles 优先；忽略 dry-run |
| `--config` 越界 + `--allow-external-config` 缺 | 立即 exit=2 |

**关于 `--list-profiles` 输出 schema**：

- 输出到 **stdout**（不是 stderr，便于 `photo3d-jury --list-profiles | grep ...`）
- 每行：`<id>\t<kind>\t<model>\t[active]?`（tab 分隔，纯文本，不带 ANSI escape）
- 例：

```
gemini-aihubmix	openai_compat	gemini-2.5-flash	[active]
gpt-4o-native	openai_compat	gpt-4o
```

- 若 config 缺失 / schema 错 → exit=2 + stderr 中文提示同 §7.2
- exit=0 表示成功列出（即使 0 profile，输出空但 exit 0；config 有效但 profiles=[] 不可能因为 §4.1 校验拒）

**关于 stderr 中文人话提示**（外行用户友好）：

- 任何 exit code 1/2/3/4 都必须在 stderr 打印至少一行中文一行人话提示，包含：(a) 问题简述；(b) 推荐下一步命令（可复制粘贴）；(c) docs 链接（最末）
- exit=0 时若 status=`needs_review` / `preview` 也在 stderr 打印 `next_step` 字段内容（与报告里的 `next_step` 同）
- exit code 仅给脚本用；外行用户读 stderr

---

## 5. 错误处理

### 5.1 错误类别 → exit code

| 类别 | 触发场景 | jury 行为 | jury status | exit code |
|---|---|---|---|---|
| **A. 配置错** | jury config 不存在 / `schema_version` 不匹配 / `active_profile_id` 未命中 / `api_base_url` 非 https / id 正则错 / `--config` 越界无 `--allow-external-config` / `--budget < 0` / `--max-retries < 0` / `max_n_views` 超 cap（无视 `--confirm-cost`） | 立即抛 `JuryConfigError`，不发请求 | 不写报告 | 2 |
| **B. 输入证据错（Layer 0）** | ENHANCEMENT_REPORT 不存在 / subsystem 不匹配 / SHA256 漂移（含 freeze 后再读漂移）/ `report["status"] != accepted` / `delivery_status != accepted` / `quality_summary.status != accepted` / active_run `active!=True` 或不存在 / views=[] / 任一视角图大小超 `max_image_bytes` | 写 `PHOTO3D_JURY_REPORT.json` 含 `blocking_reasons[]`，不调 LLM | `blocked` | 1 |
| **B'. 输入自洽性错（Layer 1）** | 顶层声称 accepted 但 per-view 字段矛盾（status/edge_similarity/effective_contrast_stddev=None 或 < 12.0 /quality_metrics 缺）—— 由 `deterministic_gate.py` 检出 | 写报告含 `deterministic_gate.per_view_failures[]`，不调 LLM | `preview` | 0 |
| **C. 成本超额** | `estimated_cost_usd > budget_per_run_usd` 且未带 `--confirm-cost` | 不调 LLM；打印预估 + 命令提示 | 不写报告 | 3 |
| **D. LLM 失败** | 网络/timeout/4xx/5xx/key 过期/限流/解析失败 / 图过大 / 截断 / non-json response；按 `max_retries` 重试后仍失败 | 该视角 verdict=`needs_review` + `llm_meta.error_kind`；继续跑下一视角 | `needs_review`（任意视角失败即整体退到此） | 0 |
| **E. 并发冲突** | `.jury.lock` 已存在（含 PID + ISO timestamp） | 不调 LLM；stderr 打印 stale lock 移除提示 + lock 内容 | 不写报告 | 4 |

注意 D 类返回 exit=0：LLM 失败是"运行成功但结果不完整"，与 `enhance-review needs_review` 同语义。E 类 exit=4 与 D 类区分，便于脚本识别"另一进程在跑"vs"LLM 失败"两种场景。

### 5.2 LLM 错误细分

注：下表"重试次数"上限为 cli `--max-retries`（默认 2，§4.8）；表中数字是默认值下的具体行为。

| `error_kind` | 触发 HTTP/异常 | 是否重试 | 重试细节 |
|---|---|---|---|
| `network_unreachable` | `URLError` / `ConnectionError` / DNS 失败 | 重试 ≤ `max_retries` 次 | 退避 2s/4s |
| `timeout` | socket / urllib timeout（`urlopen(..., timeout=60)` 显式给）；或单视角累计 > 120s 强 abort | 重试 ≤ `max_retries` 次 | 退避 2s/4s |
| `auth_failed` | 401, 403 | **不重试** | key 错重试浪费配额 |
| `rate_limited` | 429 | 重试 ≤ `max_retries` 次 | 默认退避 2s/4s；若 response 含 `Retry-After` header 优先用其值，**clamp 到 `[1, 60]` 秒**（防中转商返 `Retry-After: 86400` 让 jury 卡 1 天）；超 clamp 上限直接归 rate_limited 不再重试 |
| `quota_exhausted` | 402；或 OpenAI/兼容中转 response body JSON 含 `error.code == "insufficient_quota"` | **不重试** | 用户提示换 profile。中文中转商可能返"余额不足"等 zh 文案，v1 不解析 free-form 中文，最终归类回退到 `bad_request` 或 `server_error`；用户可通过 `actual_cost_usd / estimated_cost_usd` 比较 + `error_kind` 判断换 profile（v2 增强中文模式匹配） |
| `bad_request` | 400（含 `context_length_exceeded` 等图过大上游 reject） | **不重试** | schema 错；图过大本地预检通常已挡（见 image_too_large） |
| `server_error` | 500-599 | 重试 ≤ `max_retries` 次 | 退避 2s/4s |
| `parse_failed` | LLM 200 + Content-Type=json 但 JSON 解析失败 | 重试 ≤ 1 次（独立于 max_retries；同 temperature=0） | 退避 1s |
| `truncated` | LLM 200 + `finish_reason=length`（max_tokens 截断） | **不重试** | 同输入同温度必再截断；用户应增大 max_tokens 或换 profile（v2 自动重试增大 limit） |
| `non_json_response` | LLM 200 但 `Content-Type` 非 `application/json*` 且 body 不是 JSON（中转 CDN 错误页 / HTML） | **不重试** | 服务故障；用户换 profile |
| `image_too_large` | 增强图 `os.path.getsize() > max_image_bytes`（默认 8 MiB），由 `llm_client.py` 在发请求前预检 | **不重试** | 用户应在 enhance 阶段约束输出大小 |
| `tls_verification_failed` | `ssl.SSLCertVerificationError` 或类似 | **不重试** | 企业 MITM 自签 CA：用户用 `SSL_CERT_FILE` env 注入；**严禁** unverified context |

### 5.2.1 `.jury.lock` 生命周期 + stale 自动清理

实现走 contextmanager pattern（参考 `tools/sw_warmup.py:acquire_warmup_lock`），抽出 `tools/_file_lock.py` 后两处共用：

```python
# 伪代码（实施时移到 tools/_file_lock.py）
@contextmanager
def jury_lock(active_run_dir: Path) -> Iterator[None]:
    lock_path = active_run_dir / ".jury.lock"
    if lock_path.exists():
        # stale 自动清理判定
        try:
            data = json.loads(lock_path.read_text())
            held_pid = int(data.get("pid", -1))
            held_mtime = lock_path.stat().st_mtime
            now = time.time()
            stale_by_age = (now - held_mtime) > 1800  # 30 min
            stale_by_pid = held_pid > 0 and not _pid_alive(held_pid)
            if stale_by_age or stale_by_pid:
                sys.stderr.write(
                    f"警告：检测到 stale .jury.lock（PID={held_pid}, age={int(now-held_mtime)}s），"
                    f"自动清理后继续。\n"
                )
                lock_path.unlink()
            else:
                raise JuryLockBusy(f"已有 jury 进程在跑：PID={held_pid}")
        except (json.JSONDecodeError, KeyError, ValueError):
            # 损坏 lock 视为 stale
            lock_path.unlink()

    # 创建 lock
    lock_path.write_text(json.dumps({
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }))
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)
```

**关键不变量**：

- `try/finally` 保证 lock 在所有 status / 异常路径都被释放（happy path / Layer 0/1 fail / Layer 2 mid-fail / sha drift / KeyboardInterrupt / SystemExit）
- stale 判定仅用 mtime + PID 双指标（不依赖 jury 进程间通信）；保守默认双指标都满足才清理
- `_pid_alive(pid)` 跨平台：Linux `os.kill(pid, 0)`；Windows `OpenProcess`（msvcrt 没现成接口；用 `subprocess.run(["tasklist", "/FI", f"PID eq {pid}"])` 兜底；或导入 ctypes 调 OpenProcess + GetExitCodeProcess——具体实现选项 plan 阶段决）
- 跨 reboot：mtime 在 reboot 后保留（除非用户清空），所以 mtime > 30 min 的 stale 在 reboot 场景下也能触发清理；保守 OK

### 5.3 安全护栏

1. **Key 永不落盘**：`PHOTO3D_JURY_REPORT.json` 只记 `profile_id` 和 `model`；测试断言 `"api_key"` 字符串和具体 key value 都不出现在落盘 JSON 中
2. **Key 永不出现在错误信息**：
   - `JuryLlmError.__str__` 截断响应体（默认前 128 字符 + "...truncated"）
   - HTTP 错日志只留 `http_status` + `error_kind`，不含 body / headers / url
   - **redact 规则同步覆盖** `getattr(error, "url", "")` / `error.headers` / `error.read()`：仅保留 host + path 模板（不含 query / fragment / Authorization / Cookie / Set-Cookie），防中转商把 `?api_key=xxx` 放 query string 时 url 通过 `urllib.error.HTTPError.url` 属性暴露
     - 注意：`HTTPError` 是 `addinfourl` 的子类，**没有 `geturl()` 方法**（HTTPResponse 才有）；实施时用 `getattr(error, "url", "")` 取属性，避免 AttributeError
   - 顶层 cli 必有 **try/finally** 兜底（不止 try/except）：`finally` 块释放 `.jury.lock` 并 redact 任何要打印的 traceback；`except Exception` 内只打印 `error_kind` + `http_status`（防 Python default `sys.excepthook` 打印 frame locals 含 `api_key` 字符串）
   - `llm_client.py` 内 api_key 读出后立即装入 dataclass / 闭包，**不作为 stack frame 显式 long-lived local 变量**；不作为函数 default 参数（会进 inspect 签名）
   - `http.client.HTTPConnection.debuglevel = 0` 在 `llm_client.py` 顶部 import 后显式设置（这是 **class-level attribute**，影响 jury import 后**新构造**的所有 conn；**不能撤销**外部代码已构造实例的 `conn.debuglevel=1`——但 jury 自己只构造自己的 conn 即可，不会复用外部 conn 实例。测试断言用"jury 模块 import 后 `HTTPConnection.debuglevel` 值为 0"即可，不必模拟"覆盖外部已构造实例"——后者无法实现）
3. **路径策略**：所有写入走 `assert_within_project` + `write_json_atomic`；输出 JSON 的 `source_reports.*` 路径用 `Path.as_posix()`（forward slash），与 enhance-review `_norm` 同口径
4. **active_run 绑定**：jury 不可写入非 active run dir 之外路径；不修改 `ARTIFACT_INDEX.json`；Layer 0 freeze 后写入路径用冻结值，写前再读不一致即 status=blocked
5. **`--config` 任意路径攻击防御**：`--config` 解析后绝对路径必须满足 `~/.claude/` 下或项目内（`assert_within_project`），否则需显式 `--allow-external-config`（防社工诱导 `--config ./evil.json` 把所有图传第三方）
6. **资源/配额硬上限**：
   - `max_image_bytes`（默认 8 MiB）：单视角增强图超此 → `error_kind=image_too_large` 不调 LLM
   - `max_n_views`（默认 32）：报告视角超此 → `JuryConfigError`（即使 `--confirm-cost` 也不旁路，防爆炸 ENHANCEMENT_REPORT.json 烧 key 配额）
7. **prompt injection 防护（reason 字段）**：LLM 返的 `reason` 落盘前过滤控制字符 + ANSI escape + 截 80 字 + 折行（详见 §4.4）
8. **测试 fixture key 形态**：禁用 `sk-` / `pk-` / `gsk_` 等真实 vendor 前缀（GitHub secret scanner 误报会撤销 OpenAI 真 key）；测试中必用 `dummy-not-a-real-key` 或类似**无效**前缀

---

## 6. 测试策略

### 6.1 TDD 节奏

每个组件先写失败测试，再写实现（项目 CLAUDE.md 强制）。每 task ≤ 5 分钟、含验收标准。

### 6.2 单元测试矩阵

| 文件 | 必测场景数 | 关键 case |
|---|---|---|
| `test_config.py` | 18 | schema_version 错 / active_profile_id 不存在 / api_base_url 非 https / cost_per_call_usd 缺省走估价表 / cost_per_call_usd=0 触发 confirm-cost 警告 / kind 仅接受 openai_compat / 多 profile 选 active 命中 / 单 profile / 空 profiles list / id 正则非 ASCII 拒 / id 重复拒 / api_base_url rstrip 末尾斜杠 / **base_url 含 `/v1` 保留** / **base_url 不含 `/v1` 自动追加** / **base_url 末尾斜杠 + `/v1`** / **base_url 末尾斜杠 + 无 `/v1`** / max_image_bytes 默认 8MiB / max_n_views 默认 32 / **解析后 raw dict 立即丢弃**（断言返回 dataclass 不持有 raw dict 引用） / **估价表前缀匹配按表中行序首次命中**（防 gpt-4o-mini 错配 gpt-4-turbo*）|
| `test_cost.py` | 8 | 预估 = N×单价 / 等于 budget 不触发 / 超 budget+无 confirm 拒 / 超+有 confirm 过 / cost=0 永远过 / cost=0 + 默认 budget 仍要求 confirm-cost / N=0 边界 / `--budget=0` + cost>0 拒 |
| `test_input_evidence_binding.py` (Layer 0 新文件) | 16 | 文件不存在 blocked / subsystem 不一致 / run_id 不一致 / `runs[active].active != True` blocked / `report.status != accepted` blocked / `delivery_status != accepted` blocked / `quality_summary.status != accepted` blocked / views=[] blocked / 视角数超 max_n_views blocked / 图大小超 max_image_bytes blocked / `--config` 越界无 `--allow-external-config` blocked / sha256 freeze 后再读漂移 blocked / **Layer 0 全跑完汇总 blocking_reasons[]**（不 short-circuit，外行用户一次看全）/ **lock 重入 stale by PID 自动清理**（PID not exists） / **lock 重入 stale by mtime 自动清理**（mtime > 30 min） / **lock 重入 live 阻塞**（PID alive 且 mtime < 30 min → JuryLockBusy exit=4）|
| `test_deterministic_gate.py` (Layer 1) | 9 | 全 accepted 全 pass / `views[].status` 非 accepted fail / `edge_similarity` < min_similarity fail / `effective_contrast_stddev=None` fail / `effective_contrast_stddev` < 12.0 fail / `quality_metrics` 缺失 fail / 多视角混合（部分 fail）/ 阈值常量与 enhance_consistency 用 `pytest.approx` 同值断言 / `min_similarity` 字段缺失 fallback 0.85 |
| `test_llm_client.py` | 18 | 200 一发命中 / 429 重试通过 / 429 重试 max_retries 次仍 429 → rate_limited / 429 + Retry-After=10s 实际等 10s / Retry-After=86400 clamp 到 60 / 401 不重试 → auth_failed / 402 → quota_exhausted / 500 重试通过 / timeout 重试通过 / DNS 错 → network_unreachable / parse_failed 走 1 次温度 0 重试 + 重试 body 含 temperature=0 断言 / `max_retries=0` 时首发 fail 直接归类（parse_failed 仍允 1 次独立重试）/ truncated（finish_reason=length）不重试 / non_json_response（Content-Type=text/html）不重试 / image_too_large 在发请求前预检不计费 / tls_verification_failed 类别 / 错误 body 不进 log（断言）/ api_key 不进异常 str（断言）/ url query/header 中 api_key 也被 redact / **CAD_JURY_DISABLE_LLM=1 抛 JuryDisabledByEnv 不发请求** / latency_ms 累加 / actual_cost_usd 含失败重试 / `urlopen` 显式 `timeout=60` 验证 / `http.client.HTTPConnection.debuglevel=0` 顶部设置（防 outer ext 注入）|
| `test_verdict.py` | 11 | 标准 JSON / 缺 photoreal_score / boolean 字段非 bool / photoreal_score < 0 clamp / >100 clamp / JSON 含 markdown 包裹 → invalid_json / reason 缺失补空 / Unicode reason / **reason 含控制字符被 strip** / **reason 含 ANSI escape 被 strip** / reason 超 80 字被截 |
| `test_photo3d_jury_cli.py` (位于 `tests/jury/`，cli 薄壳) | 13 | 缺 --subsystem 报错 / config 缺失 exit=2 / 超 budget 无 confirm exit=3 / 输入证据错 exit=1 / 全成功 exit=0 / Layer 1 fail → preview → exit=0 / LLM needs_review → exit=0 / `.jury.lock` 已存在（live PID + recent mtime）→ exit=4 / `.jury.lock` stale（PID not exists）→ 自动清理 + 继续 / `.jury.lock` stale（mtime > 30 min）→ 自动清理 + 继续 / `--list-profiles` 输出 profile 列表（tab 分隔含 active 标记）不调 LLM / `--dry-run` 跑 Layer 0/1 + 预估不写报告 / `--list-profiles` + `--dry-run` 互斥（前者优先）/ stderr 中文人话提示行存在（每 exit code 至少一行）|

### 6.3 集成测试

`test_photo3d_jury_e2e.py` patch `tools.jury.llm_client.urlopen`（patch **被调用方 namespace** 而非 `urllib.request.urlopen` 全局，这是 Python mock 惯例；要求 `llm_client.py` 用 `import urllib.request` 形态而非 `from urllib.request import urlopen`），构造完整 `cad/<subsystem>/.cad-spec-gen/runs/<run>/` 树：

**Fixture 静态来源**：所有 e2e 用 `tests/jury/fixtures/sample_enhancement_report.json` + `sample_render_manifest.json` + `sample_artifact_index.json`（手动构造的合法已 accepted 报告 + ARTIFACT_INDEX.json，conftest 用 sha256 stub 让 freeze 校验通过）；不依赖真 enhance-check 跑出的报告（不稳定且慢）。

| 场景 | 验证 |
|---|---|
| 6 视角全 200 + 全 true + score≥60 | status=accepted / 双输出 JSON 都生成 / cost 累计正确 |
| 6 视角全 200 + 全 true + score=15 | status=preview（min_photoreal_score gate 触发）/ jury_review_input.json **不写** |
| 1 视角 401 | 整体 status=needs_review / 5 视角有 verdict / 1 视角 error_kind=auth_failed / **jury_review_input.json 不写** |
| 全 LLM 成功但 1 视角 5 boolean 任一 false | status=preview / **jury_review_input.json 不写** |
| 全 LLM 成功但 1 视角 photoreal_score < min_photoreal_score | status=preview / **jury_review_input.json 不写** |
| Layer 1 fail | 不调 LLM / status=preview / per_view_failures 列出 / **jury_review_input.json 不写** |
| 输入证据 SHA256 漂移 | status=blocked / blocking_reasons 含 hash mismatch |
| sha256 freeze 后再读漂移（mock：写报告前重读得到不同值） | status=blocked / 不写文件覆盖 |
| Cost 超 budget 无 --confirm-cost | exit=3 / 不写报告 / 不调 LLM |
| `.jury.lock` 已存在 | exit=4 / 不写报告 / 不调 LLM |
| `--dry-run` 模式 | Layer 0/1 跑 / 不调 LLM / 不写报告 / stdout 输出 cost 预估 + Layer 0/1 verdict |
| `--profile-id <next>` override | 切到第二 profile 调用其 api_base_url / 第一 profile 不被使用 |
| 混合 status（Layer 1 部分视角 fail + LLM 部分视角 fail）| status 取最高优先级 needs_review（高于 preview） |
| `--list-profiles` | 列出 profile id + 当前 active / 不调 LLM / exit=0 |
| **api_key 不落盘** | PHOTO3D_JURY_REPORT.json + jury_review_input.json 全文不含 api_key 字符串（用真测试 key 形态 `dummy-not-a-real-key`） |
| **error log 不含 body** | 模拟 401 含敏感 body / mock log handler 校验 stderr 与 log file 不含 body / Authorization / Cookie 字段 |
| **链路 e2e** | jury 出 review-input → `enhance-review --review-input` 跑通 → ENHANCEMENT_REVIEW_REPORT.json status=accepted（用同一 fixture 作 enhance-review 的输入） |
| **链路负向 e2e** | needs_review 时 jury 不写 review-input；用户尝试 `enhance-review --review-input cad/.../jury_review_input.json` 报"文件不存在"（验证 jury 主动不污染下游） |

### 6.4 真实 LLM 烟测（手动，可选）

`tools/jury/manual_smoke.py` 不进 CI（避免烧费 + 网络抖动）：

```bash
python tools/jury/manual_smoke.py --image render.png --profile gemini-aihubmix
```

真发一次 vision call，打印 ViewVerdict + cost；用于人工验明 prompt 与解析。

### 6.5 测试隔离 + 安全阀

参考 memory `feedback_external_subsystem_safety_valve.md`：

1. **env kill switch**：`CAD_JURY_DISABLE_LLM=1` 时 `llm_client.py` 直接抛 `JuryDisabledByEnv`
2. **conftest autouse fixture**：`tests/jury/conftest.py` 默认 `monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")` + 提供 `enable_llm_for_test` opt-in。**所有 jury 测试必须放在 `tests/jury/` 子目录下**（包括 cli 薄壳测试 `test_photo3d_jury_cli.py`）；pytest conftest autouse 仅覆盖同级及子级目录，cli 薄壳若放在 `tests/` 顶级会逃逸 kill switch 引发真发 LLM 烧费风险
3. **module-level `urlopen` patch**：单元测试默认 patch `tools.jury.llm_client.urlopen` 模块属性（要求 `llm_client.py` 用 `from urllib.request import urlopen` 形态）；jury **不沿用** `tests/test_track_c_llm.py:65` 的全局 `patch("urllib.request.urlopen")` 模式（混用会让 fixture 漂移）
4. **fixture key 形态约束**：所有 fixture 中 api_key 必须用 `"dummy-not-a-real-key"` / `"test-fake-key"` 等无效前缀；禁止 `sk-` / `pk-` / `gsk_` 等真实 vendor 前缀（防 GitHub secret scanner 误报撤销 OpenAI 真 key）
5. **跨平台**：jury 不依赖任何 Windows API（无 winreg / ctypes.windll）；测试全 cross-platform（Linux + Windows CI 都跑），不需 `requires_windows` marker
6. **manual_smoke.py 排除**：项目 `pyproject.toml` 现有 `[tool.coverage.run]` 用白名单 `source = [...]` 模式（行 99-118）而非 `omit`；jury 走相同模式：在 `source` 显式列出 `"tools.jury.config"` / `"tools.jury.cost"` / `"tools.jury.input_evidence_binding"` / `"tools.jury.deterministic_gate"` / `"tools.jury.llm_client"` / `"tools.jury.verdict"` / `"tools.photo3d_jury"`（**不**列 `manual_smoke`）。pytest 不需 `--ignore`（manual_smoke 不以 `test_` 开头，pytest collect 不会触碰）；但 `tests/jury/fixtures/intentional_type_error.py` 以 `_` 开头同理 collect 不触发

### 6.6 覆盖率与 lint

- 目标：`tools/jury/*` + `tools/photo3d_jury.py` 行覆盖 ≥ 95%（excluding manual_smoke.py）
- mypy strict（继承 v2.21.1 加的 strict gate）；新增 negative case：CI tool job 直接调 `mypy --strict tools/jury` + 一份**故意写错** type 的 fixture 文件确认 mypy 真生效（不通过 pytest 间接 — 参考 `feedback_ci_mypy_marker_deselect.md` 的 v2.21.1 hotfix 教训）
- ruff check + format 干净
- 加 jury/* 路径到 tests.yml CI cov 分子（参考 `feedback_ci_cov_gate_platform_split.md`）；jury 跨平台跑，cov 分母不需平台 split

---

## 7. 兼容性与迁移

### 7.1 向前兼容

- 不改 `enhance-check` / `enhance-review` 任何字段或 schema
- 不改 `photo3d-handoff` / `photo3d-deliver` / `photo3d-recover` 任何行为
- 不动 `provider_health` / `provider_presets`（jury 是独立 vision 维度，不属于 enhancement provider）

### 7.2 用户首跑

无 `~/.claude/cad_jury_config.json`：

```
$ photo3d-jury --subsystem lifting_platform
ERROR: 未找到 jury 配置文件 ~/.claude/cad_jury_config.json

请创建该文件，最小配置（修改下面 3 处后保存）：

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

完整文档：docs/cad-jury-config.md（含厂商示例、估价表、TLS 企业 CA 配置）

exit code: 2
```

### 7.3 与既有 Gemini config 关系

`~/.claude/gemini_image_config.json`（enhance 用）与 `~/.claude/cad_jury_config.json`（jury 用）是**独立**两份。原因：

- enhance 写图，jury 看图——能力域不同
- 用户可能希望 enhance 用便宜模型，jury 用更贵更准的模型
- jury 多 profile 切换 UX 与 enhance 的单 active 不同

### 7.4 文档更新

- `docs/cad-jury-config.md` 新增（用户级配置说明），必含：
  - 最小配置 JSON 模板 + 字段释义
  - 内置估价表（model 模式 → cost_per_call_usd 默认值），如何 override
  - 已知支持 vision 的中转商示例（aihubmix、SiliconFlow 等）+ 警告每家政策不同
  - **隐私警告**：增强图会以 base64 上传到 `api_base_url`；中转/原生厂商可能记录与训练；机密项目应自托管 endpoint
  - **企业 MITM TLS** 配置：`SSL_CERT_FILE` env 注入企业 CA；jury 严禁 unverified context
  - **`.gitignore` 提醒**：建议 `.gitignore cad/**/.cad-spec-gen/runs/`，避免 PHOTO3D_JURY_REPORT.json 含 `profile_id` / `model` 落 git 暴露计费供应商指纹
  - **key 安全**：禁止 commit jury config 进 git；推荐 `chmod 600 ~/.claude/cad_jury_config.json`
  - **故障恢复**：`--list-profiles` + `--profile-id <next>` 切换；不要在 cli args 直接写 key
- `docs/cad-help-guide-zh.md` / `-en.md` 增 jury 段
- `docs/PROGRESS.md` 增 v2.27.0 条目
- `docs/superpowers/README.md` 增本 spec 链接
- `AGENTS.md` 评估是否需要更新（jury 是新 cli 但不属于 agent 工作流；倾向不改）

---

## 8. 实施顺序（plan 阶段拆分预想）

按 checkpoint 划分，详细 plan 由 writing-plans skill 生成：

- **CP-0 pre-flight + 目录脚手架 + 资产复用**：
  - grep 验证假设（`tools/contract_io.py:write_json_atomic` 签名 / `tools/path_policy.py:assert_within_project(path, project_root, label)` **3 参数全必填** / `tools/path_policy.py:project_relative` 内部已 `.as_posix()` 验证 / `tools/enhancement_semantic_review.py:REQUIRED_SEMANTIC_CHECKS` tuple / `tools/enhancement_semantic_review.py:_review_input_binding_blockers` 行 257-301 `source_reports` 必填集 / `tools/enhance_consistency.py:MIN_PHOTO_CONTRAST_STDDEV` 值 / ENHANCEMENT_REPORT.json `views[]` 实际 keys / `gemini_gen.py:42-46` `/v1` 拼接行为对比 / `runs[active_run_id].active==True` 字段存在 / `tools/sw_warmup.py:acquire_warmup_lock` 现有 lock 实现 / `pyproject.toml [project.scripts]` 与 `cad_pipeline.py` subcommand 注册模式对比 / `.github/workflows/tests.yml` mypy-strict job 调用 CLI 模式 / `tests/test_track_c_llm.py:65` 既有 mock urlopen 模式（jury **不**沿用全局 patch，走模块 namespace）/ `urllib.error.HTTPError` 有 `url` 属性无 `geturl()` 方法）
  - 新建 `tools/jury/__init__.py` / `tests/jury/__init__.py` / `tests/jury/conftest.py`（autouse kill switch）
  - **抽离 `tools/_file_lock.py`**：把 `tools/sw_warmup.py:acquire_warmup_lock` 的 cross-platform 锁实现移到通用模块；`sw_warmup` 与 `jury` 共用；保留原 `acquire_warmup_lock` API 转发到新模块（确保零 sw_warmup 回归）
  - **`cad_pipeline.py` 加 `jury` subcommand**：参考 `photo3d-handoff` / `photo3d-deliver` 既有 dispatch 模式，转发到 `tools.photo3d_jury:main`；alias 在 `skill.json` 注册成 `photo3d-jury`
  - 静态 fixture：`tests/jury/fixtures/sample_enhancement_report.json` + `sample_render_manifest.json` + `sample_artifact_index.json`（覆盖 happy + 4 unhappy 路径输入；conftest sha256 stub）
- **CP-1 config + cost**：`config.py`（含内置估价表 `BUILTIN_MODEL_COST_USD` 模式匹配 + max_image_bytes / max_n_views / id 正则 / api_base_url rstrip / raw dict 不泄漏） + `cost.py` 单元落地（独立无 HTTP）
- **CP-2 input_evidence_binding (Layer 0) + deterministic_gate (Layer 1) + verdict**：
  - Layer 0：active-run 绑定 + sha256 freeze + active_run_id freeze + `.jury.lock` 文件锁 + `--config` 路径校验 + 图大小预检 + max_n_views 校验
  - Layer 1：per-view 字段自洽性
  - `verdict.py` 纯函数：5 boolean / photoreal_score clamp / reason 控制字符 + ANSI escape strip + 80 字截断（独立无 HTTP）
- **CP-3 llm_client**：HTTP 调用 + 重试 + 错误分类（mock urlopen）；显式 timeout=60；显式 `http.client.HTTPConnection.debuglevel=0`；redact url/header/body；Retry-After clamp；CAD_JURY_DISABLE_LLM kill switch；新 error_kind（truncated / non_json_response / image_too_large / tls_verification_failed）
- **CP-4 photo3d_jury cli + e2e**：cli 薄壳（含 `--list-profiles` / `--dry-run` / `--allow-external-config` / stderr 中文人话）+ 顶层 try/except 兜底防 traceback locals dump + 报告组装（4 status ordinary_user_message + next_step + jury_review_input 仅 accepted 写）+ 整套 e2e 跑通（含 fixture 静态来源 + 链路负向 e2e）
- **CP-5 docs + ci + AGENTS 评估**：
  - 用户文档 `docs/cad-jury-config.md`（含估价表、host 风险警告、key 安全建议、TLS 企业 CA、profile 切换 UX）
  - 加 jury/* 路径到 tests.yml CI cov 分子；mypy strict CI tool job 单跑（不走 pytest 间接）
  - `pyproject.toml` 加 `--ignore=tools/jury/manual_smoke.py` + cov omit
  - AGENTS.md 评估（jury 是新 cli 但不属于 agent 工作流）
  - `docs/PROGRESS.md` v2.27.0 条目

预估 22–26 个 task，1 个 PR 闭环。

---

## 9. 风险与已知 unknown

| 风险 | 缓解 |
|---|---|
| LLM 输出 JSON 格式不稳定（即使 prompt 强调） | `verdict.py` 严格 JSON 解析；解析失败重试 1 次温度 0；仍失败 verdict=needs_review |
| `cost_per_call_usd` 与真实 vision API 计费不符（vision 按图片大小/token 计） | 内置估价表是约值；用户可显式覆盖；docs 强调 "近似估算 ±50%" + `--dry-run` 验明 |
| OpenAI-compatible 中转商 vision 支持参差（有的不收 image_url） | manual_smoke.py 验明；docs/cad-jury-config.md 列已知支持 vision 的中转商；不在 schema 层强约束（不可能枚举所有中转） |
| 用户填错 `api_base_url` 不带 `/v1`（OpenAI 兼容路径） | spec 明示用户填完整 base 含 `/v1`；jury 不补全；URL 错由 LLM 调用 4xx 暴露 + error_kind=bad_request 可读错误 |
| Claude/Gemini 等原生 vision API 严格不兼容 OpenAI schema | v1 不支持原生（用户走中转）；v2 加 `kind=anthropic_native` |
| 测试 mock urlopen 漏 patch 导致真实 HTTP 调用 | env kill switch CAD_JURY_DISABLE_LLM=1 在 conftest autouse 默认开 |
| 用户不知道怎么填 cost_per_call_usd | 内置估价表按 model 模式自动给（v1）；docs 列常见 model 实测费用作参考 |
| **LLM prompt injection 让 5 boolean 全 true 自动 accepted** | `min_photoreal_score`（默认 60）gate；MIN_PHOTOREAL_SCORE clamp；reason 落盘前过滤控制字符；spec §11 v2 加多视角投票交叉验证 |
| **HTTP 卡死 / slow loris 攻击** | `urlopen(..., timeout=60)` 强制；单视角累计 120s 超时强 abort；`Retry-After` clamp [1, 60]s |
| **api_key 通过 traceback locals dump 泄漏** | 顶层 cli try/except 兜底；llm_client 内 key 不作 long-lived stack frame local；不作函数 default 参数；`http.client.HTTPConnection.debuglevel=0` 显式覆盖外部设置 |
| **`--config` 任意路径 + `api_base_url` 跳板社工攻击** | `--config` 解析后必须 `~/.claude/` 下或项目内；显式 `--allow-external-config` 才能 override |
| **图过大 b64 内存爆 / 单次费用暴涨** | `max_image_bytes`（默认 8 MiB）+ `max_n_views`（默认 32）双重护栏；前者每视角 fail 一个；后者立即 JuryConfigError 不旁路 confirm-cost |
| **企业 MITM 自签 CA 无错误类别** | 显式 `tls_verification_failed` error_kind；docs 指引 `SSL_CERT_FILE` env 注入 CA |
| **LLM 服务记录用户产品图作训练** | docs/cad-jury-config.md 显著告警；用户对机密项目应自托管 endpoint |
| **GitHub secret scanner 误报夹具 sk- key 撤销 OpenAI 真 key** | fixture 强制 `dummy-not-a-real-key` 形态；CI 加 lint 检查 fixture 文件无真 vendor 前缀 |
| **并发 jury 双跑互相覆盖** | `.jury.lock` 文件锁；exit=4 + 提示 stale 移除 |
| **active_run_id 中途切换 / sha256 中途漂移** | jury Layer 0 freeze 二者；写报告前再读 mismatch → status=blocked 不写新 run dir |
| **needs_review 时部分视角缺 verdict 写出残缺 review-input 污染下游** | jury 仅 status=accepted 才写 jury_review_input.json；其他 3 状态都不写；用户必须手抄需要的视角 |

---

## 10. 验收标准（DoD）

- [ ] 全量回归 ≥ 现有数 + 新增 jury 测试 (`pytest -m "not solidworks_required"`)
- [ ] CI 7/7 SUCCESS（包括 mypy strict + cov ≥ 95%）
- [ ] manual_smoke.py 在用户本地真发一次能拿到合法 verdict（可选）
- [ ] 链路 e2e 测试通过：jury 出 review-input → enhance-review 接受 → ENHANCEMENT_REVIEW_REPORT.json status=accepted
- [ ] 链路负向 e2e：needs_review 时 jury 不写 jury_review_input.json
- [ ] **api_key 不落盘断言**：PHOTO3D_JURY_REPORT.json + jury_review_input.json + 任何 log 全文不含 api_key（用 fixture key `dummy-not-a-real-key` 测）
- [ ] **api_key 不进异常 traceback 断言**：故意触发未捕获异常验证 stderr 不含 key
- [ ] **HTTP 错误日志不含响应体 / Authorization / Cookie 断言**：mock 401 含敏感 body 验证
- [ ] **api_key 不进 url query 断言**：mock 中转商把 key 放 query string，url redact 后不含
- [ ] **资源上限断言**：图过 max_image_bytes / 视角数过 max_n_views 都被挡住，不调 LLM
- [ ] **kill switch 断言**：CAD_JURY_DISABLE_LLM=1 时 llm_client 抛 JuryDisabledByEnv 不发请求
- [ ] **photoreal_score gate 断言**：5 boolean 全 true 但 score < min_photoreal_score 整体 status=preview
- [ ] **fixture key 形态 lint**：CI 加检查 `tests/jury/fixtures/*.json` 不含 `sk-` / `pk-` / `gsk_` 前缀
- [ ] **mypy strict 真生效**：CI tool job 直接调 `mypy --strict tools/jury` 验证不通过 reject case 文件
- [ ] **`.jury.lock` 文件锁**：并发跑两次第二次 exit=4 不写报告
- [ ] **stderr 中文人话提示**：每 exit code 1/2/3/4 都至少一行中文提示 + 下一步命令
- [ ] **4 个 status 都给 ordinary_user_message + next_step**：accepted / preview / needs_review / blocked
- [ ] **timeout 显式断言**：`urlopen` 调用包含 `timeout=60`
- [ ] **`http.client.HTTPConnection.debuglevel=0` 顶部设置**：测试覆盖外部 set debuglevel=1 后 jury 复位为 0
- [ ] docs/cad-jury-config.md / cad-help-guide / PROGRESS.md 更新

---

## 11. 后续 (v2 路线，不在本 PR)

- `kind = anthropic_native`
- `fallback_profile_ids` chain（key 到期自动切下一家；当前 v1 必须用户手动 `--profile-id` override）
- 月度 quota tracker（`~/.claude/cad_jury_quota.json`）
- `photo3d-handoff --with-jury` 集成
- 真无参考图像质量分（NIQE / BRISQUE / aesthetic）扩展 Layer 1（v1 仅做字段自洽性，v2 加真量化指标）
- jury 后自动跑 enhance-review（一条 cli 跑完闭环）
- **incremental flush**：v1 单次原子写最终报告，进程被 ctrl-c 时 view 1-N 内存数据全丢；v2 加每视角完成后立即写 `.partial` 报告（status=`running`），最终改 `running` → 最终 status
- **estimate cost 自动同步真实 vendor pricing**：v1 估价表是 hardcode；v2 加 `cad-jury-prices update` cli 从 vendor 公开 pricing API 拉最新值
- **多视角投票交叉验证**：同视角跑 2-3 个 profile，多数决议；提升对 prompt injection 的鲁棒性
- **中文中转商 quota 文案匹配**：v1 不解析 free-form 中文，归到 `bad_request` / `server_error`；v2 加常见中转商 zh 模式匹配（`余额不足` / `欠费` / `配额已用尽`）
- **`--max-tokens` 自适应**：truncated 时 v1 直接 needs_review；v2 自动重试增大 max_tokens 一档

---

## 附录 A：参考文件

| 文件 | 用途 |
|---|---|
| `tools/enhancement_semantic_review.py` | 现有 5 项 boolean schema + active run 绑定模式 |
| `tools/enhance_consistency.py` | 现有 IoU 0.85 + qa_image 阈值 |
| `tools/contract_io.py` | `write_json_atomic` / `file_sha256` |
| `tools/path_policy.py` | `assert_within_project` / `project_relative` |
| `gemini_gen.py` | OpenAI-compatible HTTP 调用既有风格（base64 image_url + Bearer auth） |
| `tools/photo3d_provider_health.py` | "只查存在性、不做网络探活"原则 |
| memory `feedback_external_subsystem_safety_valve.md` | env kill switch + autouse |
| memory `feedback_preflight_mirror_ci.md` | mock 不等于 CI 真跑，pre-flight 必须镜像 |
| memory `feedback_ci_cov_gate_platform_split.md` | CI cov gate 按平台 split |
| memory `user_simplicity_and_accuracy.md` | 用户要简单 + 准确不要技术细节 |
| memory `project_north_star.md` | 北极星 5 gate |
