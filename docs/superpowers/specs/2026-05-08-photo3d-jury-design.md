# Photo3D Jury — 自动照片级验收闭环 设计文档

- **日期**：2026-05-08
- **作者**：项目 + Claude（superpowers brainstorming skill 引导）
- **目标版本**：v2.27.0（独立 PR，不与 §11 cleanup 合并）
- **状态**：rev 1（待 spec self-review + 用户审）

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
                │   入口 → Layer 0 输入证据绑定                   │
                │           （file/run_id/sha256/顶层 status     │
                │            一致性；fail → blocked）             │
                │              ↓                                  │
                │         Layer 1 deterministic 自洽性            │
                │           （per-view edge_similarity /          │
                │            effective_contrast_stddev /          │
                │            quality_metrics；fail → preview）    │
                │              ↓                                  │
                │         Layer 2 LLM jury                        │
                │           （openai_compat HTTP，每视角 1 调）  │
                │              ↓                                  │
                │   出口 → (1) PHOTO3D_JURY_REPORT.json           │
                │          (2) jury_review_input.json (兼容       │
                │              enhance-review --review-input)     │
                └────────────────────────────────────────────────┘
                                ↓
                用户自跑: enhance-review --review-input .../jury_review_input.json
                                ↓
                ENHANCEMENT_REVIEW_REPORT.json (现有契约不改)
```

### 3.2 文件布局

```
tools/photo3d_jury.py                ← cli 入口 + 报告组装（薄壳）
tools/jury/
    __init__.py
    config.py                        ← profile 解析 / active 选取 / 校验
    cost.py                          ← 预估 + budget 守门
    deterministic_gate.py            ← Layer 1
    llm_client.py                    ← Layer 2 HTTP 调用 + 重试
    verdict.py                       ← LLM 响应 → 结构化（纯函数）
    manual_smoke.py                  ← 手动真实 LLM 烟测脚本（不进 CI）
tests/test_photo3d_jury.py
tests/jury/
    __init__.py
    conftest.py                      ← autouse 关 LLM kill-switch
    test_config.py
    test_cost.py
    test_deterministic_gate.py
    test_llm_client.py
    test_verdict.py
    test_photo3d_jury_e2e.py         ← 集成（mock HTTP）
docs/cad-jury-config.md              ← 用户级配置说明（key/base_url 怎么填）
```

### 3.3 模块契约表

| 模块 | 单一职责 | 输入 | 输出 | 不做 |
|---|---|---|---|---|
| `config.py` | profile schema 解析 / active 选取 / 字段校验 | jury config 路径 + 可选 override profile_id | `JuryProfile` dataclass | 不发 HTTP / 不读图 |
| `cost.py` | budget 计算 + 阈值比较 | `JuryProfile.cost_per_call_usd`, `n_views`, `budget_per_run_usd`, `confirm_cost: bool` | `CostDecision{ allowed, estimated_usd, reason }` | 不调 LLM / 不记账 |
| `deterministic_gate.py` | Layer 1 输入证据自洽性验证（defense-in-depth：报告字段是否真实声称 accepted） | `ENHANCEMENT_REPORT.json` dict | `Layer1Verdict{ pass, per_view_failures }` | 不读图 / 不再算指标 / 不引新阈值（沿用 enhance-check 已经判过的字段） |
| `llm_client.py` | Vision API 调用 + 指数退避 | `JuryProfile`, `enhanced_image_path`, `prompt` | `LlmResponse{ content_text, http_status, attempts, latency_ms }` 或抛 `JuryLlmError` 子类 | 不解析 verdict / 不计费 |
| `verdict.py` | LLM 文本 → 结构化 5 boolean + score（纯函数） | `LlmResponse.content_text` | `ViewVerdict{ semantic_checks, photoreal_score, raw_excerpt, parse_status }` | 不调 LLM / 不读文件 |
| `photo3d_jury.py` | cli + 报告组装 | argv + project_root + subsystem | 写两份 JSON | 不实现具体逻辑 |

### 3.4 不变量

1. `config.py` 之外没人读 jury config 文件
2. `llm_client.py` 之外没人调 HTTP
3. `verdict.py` 是无副作用纯函数
4. 所有写入走 `tools/contract_io.py:write_json_atomic` + `tools/path_policy.py:assert_within_project`（与 enhancement_semantic_review.py 一致）
5. api_key 永不进任何 .json / 异常 / 日志

---

## 4. 数据流

### 4.1 输入：jury 配置

`~/.claude/cad_jury_config.json`：

```json
{
  "schema_version": 1,
  "active_profile_id": "gemini-aihubmix",
  "profiles": [
    {
      "id": "gemini-aihubmix",
      "kind": "openai_compat",
      "api_base_url": "https://aihubmix.com/v1",
      "api_key": "sk-xxx",
      "model": "gemini-2.5-flash",
      "cost_per_call_usd": 0.005,
      "comment": "默认中转，余额充足"
    },
    {
      "id": "gpt-4o-native",
      "kind": "openai_compat",
      "api_base_url": "https://api.openai.com/v1",
      "api_key": "sk-yyy",
      "model": "gpt-4o",
      "cost_per_call_usd": 0.015
    }
  ]
}
```

**校验规则**：

- `schema_version == 1`，否则 `JuryConfigSchemaError`
- `active_profile_id` 必须命中 `profiles[].id`
- `kind ∈ {"openai_compat"}`（v1）
- `api_base_url` 必须 `https://` 开头（防误填 http）
- `api_key` 非空字符串
- `cost_per_call_usd` 缺省视为 `0.0`；必须 ≥ 0
- `model` 非空字符串
- 解析后只返 `JuryProfile` dataclass，原 dict 在 `config.py` 内立即丢弃（防 key 通过返回值泄漏）

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

**HTTP body**（严格 OpenAI Chat Completions 兼容，POST 到 `<api_base_url>/chat/completions`，注意：`api_base_url` 由用户提供完整 base，例如 `https://api.openai.com/v1` 或 `https://aihubmix.com/v1`，jury 拼 `/chat/completions`，不再补 `/v1`）：

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

### 4.3 两个独立验证层（避免条件重复映射两个 status）

为避免同一字段同时映射 `blocked` 和 `preview`，明确分两层：

#### Layer 0 — 输入证据绑定（在 §5.1 行 B 实现，jury 入口立即跑）

| 字段 | 期望 | fail → status |
|---|---|---|
| `ENHANCEMENT_REPORT.json` 文件存在 | yes | `blocked` |
| `report["subsystem"]` | 与 cli `--subsystem` 一致 | `blocked` |
| `report["run_id"]` | 与 ARTIFACT_INDEX active_run_id 一致 | `blocked` |
| `source_reports.*_sha256`（如果输入是带 sha256 的 review-input bridge 场景） | 与文件实际 sha256 一致 | `blocked` |
| `report["status"]` | `"accepted"` | `blocked` |
| `report["quality_summary"]["status"]` | `"accepted"` | `blocked` |

**意图**：用户未通过 enhance-check 的报告**根本不应该**进 jury 流程；这一层在 cli 入口就 fast-fail。

#### Layer 1 — `deterministic_gate.py` 内部自洽性二次验证（defense-in-depth）

输入到达此层时，Layer 0 已保证 `report["status"]=="accepted"` 且 `quality_summary.status=="accepted"`。本层只做"声称 accepted 时各 per-view 字段是否真自洽"：

| 字段路径 | 期望 | fail → status |
|---|---|---|
| `views[].status`（每视角） | `"accepted"` | `preview` |
| `views[].edge_similarity`（每视角） | `≥ report["min_similarity"]`（默认 0.85） | `preview` |
| `views[].quality_metrics["effective_contrast_stddev"]`（每视角） | `≥ MIN_PHOTO_CONTRAST_STDDEV`（12.0；与 `tools/enhance_consistency.py` 同值） | `preview` |
| `views[].quality_metrics`（字段存在） | 非空 dict | `preview` |

**设计意图**：v1 不引入新图像质量指标（NIQE/BRISQUE/aesthetic 留 v2）。Layer 1 角色是"对手工编辑/部分写入损坏的报告做内部矛盾检测"——若顶层声称 accepted 但单视角字段否决，整体降级 preview 且**不调 LLM**（节费）。

**正常情况下**：用户没改过 ENHANCEMENT_REPORT.json 且 enhance-check 跑成功，Layer 1 100% 通过；成本接近 0。NIQE/BRISQUE 真无参考分到 v2 时替换/扩展本层。

阈值常量（12.0）在 `deterministic_gate.py` 顶部 module-level 定义；测试断言它与 `tools/enhance_consistency.py:MIN_PHOTO_CONTRAST_STDDEV` 同值，防止某天 enhance_consistency 改阈值漏跟。

### 4.4 输出 1：`PHOTO3D_JURY_REPORT.json`

落 `cad/<subsystem>/.cad-spec-gen/runs/<active_run_id>/PHOTO3D_JURY_REPORT.json`：

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-08T12:34:56Z",
  "subsystem": "lifting_platform",
  "run_id": "20260508-123456",
  "status": "accepted",
  "ordinary_user_message": "自动验收通过，可作为 enhance-review 的 review-input 输入。",
  "source_reports": {
    "render_manifest":          "cad/output/renders/.../render_manifest.json",
    "render_manifest_sha256":   "<sha256>",
    "enhancement_report":       "cad/output/renders/.../ENHANCEMENT_REPORT.json",
    "enhancement_report_sha256": "<sha256>"
  },
  "jury_meta": {
    "profile_id":           "gemini-aihubmix",
    "model":                "gemini-2.5-flash",
    "estimated_cost_usd":   0.030,
    "actual_cost_usd":      0.030,
    "budget_per_run_usd":   0.5,
    "n_views":              6,
    "n_calls":              6,
    "n_retries_total":      1
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

### 4.5 输出 2：`jury_review_input.json`

兼容 `enhance-review --review-input` 现有 schema（见 `tools/enhancement_semantic_review.py` `REQUIRED_SEMANTIC_CHECKS`）：

```json
{
  "schema_version": 1,
  "review_type": "auto_jury_v1",
  "subsystem": "lifting_platform",
  "run_id": "20260508-123456",
  "source_reports": {
    "render_manifest":          "<同 jury_meta>",
    "render_manifest_sha256":   "<同>",
    "enhancement_report":       "<同>",
    "enhancement_report_sha256": "<同>"
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

`source_reports` 与 SHA256 必须与 jury 当时读到的一致——这是 `enhance-review` 已存在的"绑定 active run"硬要求，jury 直接抄写。

### 4.6 status 取值

| status | 触发 |
|---|---|
| `accepted` | Layer 1 全 pass + 所有视角 5 boolean 全 true |
| `preview` | Layer 1 任一视角 fail；或 LLM 任一视角 5 boolean 任一 false |
| `needs_review` | LLM 任一视角失败/解析失败 |
| `blocked` | 输入证据绑定错（subsystem 不匹配 / SHA256 漂移 / active_run 不一致 / `quality_summary.status != accepted`） |

**优先级**：`blocked > needs_review > preview > accepted`。

### 4.7 调用流程时序

```
$ photo3d-jury --subsystem lifting_platform --confirm-cost
[step 1/6] 读 jury config (~/.claude/cad_jury_config.json) → active=gemini-aihubmix
[step 2/6] Layer 0 输入证据绑定（ENHANCEMENT_REPORT.json + render_manifest.json + ARTIFACT_INDEX.json + sha256/run_id 一致性）
[step 3/6] 预估费用：6 视角 × 0.005 USD = 0.030 USD ≤ 0.5 USD budget → 通过
[step 4/6] Layer 1 deterministic gate：6 视角字段自洽性二次验证全过
[step 5/6] Layer 2 LLM jury：6 视角依次调
              view=iso     [200 attempt=1 lat=2.1s]
              view=front   [200 attempt=1 lat=1.9s]
              ...
[step 6/6] 写 PHOTO3D_JURY_REPORT.json + jury_review_input.json
✓ status=accepted  cost=0.030 USD
下一步: enhance-review --review-input cad/.../jury_review_input.json
```

### 4.8 cli 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--subsystem <name>` | 必填 | 与现有 photo3d-* 一致 |
| `--config <path>` | `~/.claude/cad_jury_config.json` | 测试可改路径 |
| `--profile-id <id>` | active_profile_id | 临时切 profile 不改 config |
| `--budget <usd>` | `0.5` | 单 run 费用上限 |
| `--confirm-cost` | false | 超 budget 必填 |
| `--dry-run` | false | 跑 step 1-3，不调 LLM；输出 cost 预估 |
| `--max-retries <n>` | `2` | LLM 失败重试上限 |
| `--project-root <path>` | cwd | 与 photo3d-* 一致 |

---

## 5. 错误处理

### 5.1 错误类别 → exit code

| 类别 | 触发场景 | jury 行为 | jury status | exit code |
|---|---|---|---|---|
| **A. 配置错** | jury config 不存在 / `schema_version` 不匹配 / `active_profile_id` 未命中 / `api_base_url` 非 https | 立即抛 `JuryConfigError`，不发请求 | 不写报告 | 2 |
| **B. 输入证据错（Layer 0）** | ENHANCEMENT_REPORT 不存在 / subsystem 不匹配 / SHA256 漂移 / `report["status"] != accepted` / `quality_summary.status != accepted` / active_run 不存在 | 写 `PHOTO3D_JURY_REPORT.json` 含 `blocking_reasons[]`，不调 LLM | `blocked` | 1 |
| **B'. 输入自洽性错（Layer 1）** | 顶层声称 accepted 但 per-view 字段矛盾（status/edge_similarity/effective_contrast_stddev/quality_metrics 缺）—— 由 `deterministic_gate.py` 检出 | 写报告含 `deterministic_gate.per_view_failures[]`，不调 LLM | `preview` | 0 |
| **C. 成本超额** | `estimated_cost_usd > budget_per_run_usd` 且未带 `--confirm-cost` | 不调 LLM；打印预估 + 命令提示 | 不写报告 | 3 |
| **D. LLM 失败** | 网络/timeout/4xx/5xx/key 过期/限流；2 次指数退避后仍失败 | 该视角 verdict=`needs_review` + `llm_meta.error_kind`；继续跑下一视角 | `needs_review`（任意视角失败即整体退到此） | 0 |

注意 D 类返回 exit=0：LLM 失败是"运行成功但结果不完整"，与 `enhance-review needs_review` 同语义。

### 5.2 LLM 错误细分

注：下表"重试次数"上限为 cli `--max-retries`（默认 2，§4.8）；表中数字是默认值下的具体行为。

| `error_kind` | 触发 HTTP/异常 | 是否重试 | 重试细节 |
|---|---|---|---|
| `network_unreachable` | `URLError` / `ConnectionError` / DNS 失败 | 重试 ≤ `max_retries` 次 | 退避 2s/4s |
| `timeout` | socket / urllib timeout | 重试 ≤ `max_retries` 次 | 退避 2s/4s |
| `auth_failed` | 401, 403 | **不重试** | key 错重试浪费配额 |
| `rate_limited` | 429 | 重试 ≤ `max_retries` 次 | 退避 2s/4s（若 response 含 `Retry-After` header 优先用其值） |
| `quota_exhausted` | 402；或 OpenAI/兼容中转 response body JSON 含 `error.code == "insufficient_quota"` | **不重试** | 用户提示换 profile。中文中转商可能返"余额不足"等 zh 文案，v1 不解析 free-form 中文，最终归类回退到 `bad_request` 或 `server_error`；用户可通过 `actual_cost_usd / estimated_cost_usd` 比较 + `error_kind` 判断换 profile（v2 增强中文模式匹配） |
| `bad_request` | 400 | **不重试** | schema 错 |
| `server_error` | 500-599 | 重试 ≤ `max_retries` 次 | 退避 2s/4s |
| `parse_failed` | LLM 200 但 JSON 解析失败 | 重试 ≤ 1 次（独立于 max_retries；同 temperature=0） | 退避 1s |

### 5.3 安全护栏

1. **Key 永不落盘**：`PHOTO3D_JURY_REPORT.json` 只记 `profile_id` 和 `model`
2. **Key 永不出现在错误信息**：`JuryLlmError.__str__` 截断响应体；HTTP 错日志只留 status + error_kind
3. **路径策略**：所有写入走 `assert_within_project` + `write_json_atomic`
4. **active_run 绑定**：jury 不可写入非 active run dir 之外路径；不修改 `ARTIFACT_INDEX.json`

---

## 6. 测试策略

### 6.1 TDD 节奏

每个组件先写失败测试，再写实现（项目 CLAUDE.md 强制）。每 task ≤ 5 分钟、含验收标准。

### 6.2 单元测试矩阵

| 文件 | 必测场景数 | 关键 case |
|---|---|---|
| `test_config.py` | 8 | schema_version 错 / active_profile_id 不存在 / api_base_url 非 https / cost_per_call_usd 缺省视为 0 / kind 仅接受 openai_compat / 多 profile 选 active 命中 / 单 profile / 空 profiles list |
| `test_cost.py` | 6 | 预估算 = N×单价 / 等于 budget 不触发 / 超 budget+无 confirm 拒 / 超+有 confirm 过 / cost=0 永远过 / N=0 边界 |
| `test_deterministic_gate.py` | 9 | 全 accepted 全 pass / `views[].status` 非 accepted fail / `edge_similarity` < min_similarity fail / `effective_contrast_stddev` < 12.0 fail / `quality_metrics` 缺失 fail / 多视角混合（部分 fail）/ 阈值常量与 enhance_consistency 同值断言 / `min_similarity` 字段缺失 fallback 0.85 / per_view_failures 列表元素 schema |
| `test_llm_client.py` | 12 | 200 一发命中 / 429 重试通过 / 429 重试 2 次仍 429 → rate_limited / 401 不重试 → auth_failed / 402 → quota_exhausted / 500 重试通过 / timeout 重试通过 / DNS 错 → network_unreachable / parse_failed 走 1 次温度 0 重试 / 错误 body 不进 log / api_key 不进异常 str / latency_ms 累加 |
| `test_verdict.py` | 8 | 标准 JSON / 缺 photoreal_score / boolean 字段非 bool / photoreal_score < 0 clamp / >100 clamp / JSON 含 markdown 包裹 → invalid_json / reason 缺失补空 / Unicode reason |
| `test_photo3d_jury.py` (cli 薄壳) | 5 | 缺 --subsystem 报错 / config 缺失 exit=2 / 超 budget 无 confirm exit=3 / 输入证据错 exit=1 / 全成功 exit=0 |

### 6.3 集成测试

`test_photo3d_jury_e2e.py` patch `urllib.request.urlopen`（不发真实 HTTP），构造完整 `cad/<subsystem>/.cad-spec-gen/runs/<run>/` 树：

| 场景 | 验证 |
|---|---|
| 6 视角全 200 + 全 true | status=accepted / 双输出 JSON 都生成 / cost 累计正确 |
| 1 视角 401 | 整体 status=needs_review / 5 视角有 verdict / 1 视角 error_kind=auth_failed |
| Layer 1 fail | 不调 LLM / status=preview / per_view_failures 列出 |
| 输入证据 SHA256 漂移 | status=blocked / blocking_reasons 含 hash mismatch |
| Cost 超 budget 无 --confirm-cost | exit=3 / 不写报告 / 不调 LLM |
| **链路 e2e** | jury_review_input.json 直接喂给 `enhance-review` 跑通 → ENHANCEMENT_REVIEW_REPORT.json status=accepted |

### 6.4 真实 LLM 烟测（手动，可选）

`tools/jury/manual_smoke.py` 不进 CI（避免烧费 + 网络抖动）：

```bash
python tools/jury/manual_smoke.py --image render.png --profile gemini-aihubmix
```

真发一次 vision call，打印 ViewVerdict + cost；用于人工验明 prompt 与解析。

### 6.5 测试隔离 + 安全阀

参考 memory `feedback_external_subsystem_safety_valve.md`：

1. **env kill switch**：`CAD_JURY_DISABLE_LLM=1` 时 `llm_client.py` 直接抛 `JuryDisabledByEnv`
2. **conftest autouse fixture**：`tests/jury/conftest.py` 默认 `monkeypatch.setenv("CAD_JURY_DISABLE_LLM", "1")` + 提供 `enable_llm_for_test` opt-in
3. **module-level `urlopen` patch**：单元测试默认 patch 掉

### 6.6 覆盖率与 lint

- 目标：`tools/jury/*` + `tools/photo3d_jury.py` 行覆盖 ≥ 95%
- mypy strict（继承 v2.21.1 加的 strict gate）
- ruff check + format 干净
- 加 jury/* 路径到 tests.yml CI cov 分子（参考 `feedback_ci_cov_gate_platform_split.md`）

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
请参考 docs/cad-jury-config.md 创建配置后重跑。
exit code: 2
```

### 7.3 与既有 Gemini config 关系

`~/.claude/gemini_image_config.json`（enhance 用）与 `~/.claude/cad_jury_config.json`（jury 用）是**独立**两份。原因：

- enhance 写图，jury 看图——能力域不同
- 用户可能希望 enhance 用便宜模型，jury 用更贵更准的模型
- jury 多 profile 切换 UX 与 enhance 的单 active 不同

### 7.4 文档更新

- `docs/cad-jury-config.md` 新增（用户级配置说明）
- `docs/cad-help-guide-zh.md` / `-en.md` 增 jury 段
- `docs/PROGRESS.md` 增 v2.27.0 条目
- `docs/superpowers/README.md` 增本 spec 链接
- `AGENTS.md` 评估是否需要更新（jury 是新 cli 但不属于 agent 工作流）

---

## 8. 实施顺序（plan 阶段拆分预想）

按 checkpoint 划分，详细 plan 由 writing-plans skill 生成：

- **CP-0 pre-flight**：grep 验证假设（`tools/contract_io` / `tools/path_policy` / 现有 `enhance-review` 字段名 / `ENHANCEMENT_REPORT.json` 真实字段路径 `views[].edge_similarity` `views[].quality_metrics.effective_contrast_stddev` 等 / `MIN_PHOTO_CONTRAST_STDDEV` 常量同步）
- **CP-1 config + cost**：`config.py` + `cost.py` 单元落地（独立无 HTTP）
- **CP-2 input_evidence_binding (Layer 0) + deterministic_gate (Layer 1) + verdict**：Layer 0 active-run 绑定 + Layer 1 自洽性 + 纯函数 verdict 解析（独立无 HTTP）
- **CP-3 llm_client**：HTTP 调用 + 重试 + 错误分类（mock urlopen）
- **CP-4 photo3d_jury cli + e2e**：cli 薄壳 + 6 视角集成 + 链路 e2e（jury → enhance-review）
- **CP-5 docs + ci**：用户文档 (`docs/cad-jury-config.md`) + CI cov 分子（jury 路径加入 tests.yml） + AGENTS 评估

预估 18–22 个 task，1 个 PR 闭环。

---

## 9. 风险与已知 unknown

| 风险 | 缓解 |
|---|---|
| LLM 输出 JSON 格式不稳定（即使 prompt 强调） | `verdict.py` 严格 JSON 解析；解析失败重试 1 次温度 0；仍失败 verdict=needs_review |
| `cost_per_call_usd` 与真实 vision API 计费不符（vision 按图片大小/token 计） | v1 文档说明 "近似估算" + 实际 cost 不超 budget 才允许；用户可调高/调低 |
| OpenAI-compatible 中转商 vision 支持参差（有的不收 image_url） | manual_smoke.py 验明；docs/cad-jury-config.md 列已知支持 vision 的中转商；不在 schema 层强约束（不可能枚举所有中转） |
| 用户填错 `api_base_url` 不带 `/v1`（OpenAI 兼容路径） | `config.py` 不强校验路径段（中转商路径形态多样）；URL 错由 LLM 调用 4xx 暴露 + error_kind=bad_request 可读错误 |
| Claude/Gemini 等原生 vision API 严格不兼容 OpenAI schema | v1 不支持原生（用户走中转）；v2 加 `kind=anthropic_native` |
| 测试 mock urlopen 漏 patch 导致真实 HTTP 调用 | env kill switch CAD_JURY_DISABLE_LLM=1 在 conftest autouse 默认开 |
| 用户不知道怎么填 cost_per_call_usd | docs 给 GPT-4o / Gemini 2.5 / Claude Vision 当前公开计价的常见示例 |

---

## 10. 验收标准（DoD）

- [ ] 全量回归 ≥ 现有数 + 新增 jury 测试 (`pytest -m "not solidworks_required"`)
- [ ] CI 7/7 SUCCESS（包括 mypy strict + cov ≥ 95%）
- [ ] manual_smoke.py 在用户本地真发一次能拿到合法 verdict（可选）
- [ ] 链路 e2e 测试通过：jury 出 review-input → enhance-review 接受 → ENHANCEMENT_REVIEW_REPORT.json status=accepted
- [ ] PHOTO3D_JURY_REPORT.json / jury_review_input.json 不含 api_key（测试断言）
- [ ] HTTP 错误日志不含响应体（测试断言）
- [ ] docs/cad-jury-config.md / cad-help-guide / PROGRESS.md 更新

---

## 11. 后续 (v2 路线，不在本 PR)

- `kind = anthropic_native`
- `fallback_profile_ids` chain（key 到期自动切下一家）
- 月度 quota tracker
- `photo3d-handoff --with-jury` 集成
- 真无参考图像质量分（NIQE / BRISQUE / aesthetic）扩展 Layer 1（v1 仅做字段自洽性，v2 加真量化指标）
- jury 后自动跑 enhance-review（一条 cli 跑完闭环）

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
