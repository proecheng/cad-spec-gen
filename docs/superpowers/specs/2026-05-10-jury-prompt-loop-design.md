# SP1：Jury → Prompt 反馈闭环设计稿

- **日期**：2026-05-10
- **作者**：proecheng + Claude Opus 4.7
- **状态**：brainstorm 完成，待用户审 → writing-plans
- **前置**：v2.31.1（PR #66）已发布；jury v2 (`tools/jury/`) 已落地；enhance 4 backend (`gemini` / `comfyui` / `fal` / `fal_comfy` / `engineering`) 已通
- **后续子项目**：SP2（Reference 图库 + IP-Adapter）、SP3（多 sample A/B 选优）、SP4（wizard 引导选型）、SP5（LoRA 微调，可选）

## §1 项目目标与北极星 gate

### 目标
现有 enhance 输出 jury 评分中 5 boolean 通常能过，但 `photoreal_score` 卡在 40-60 区间，质感是"CAD 渲染调"而非"产品手册/电商详情页调"。SP1 的目标是建立 **jury → prompt 反馈闭环**：

- 跑完 baseline enhance → jury 评分 → score 低于阈值时**自动**用 jury 反馈调整 prompt（+ 可选 ControlNet/denoise 参数，仅当 backend 支持）→ retry 一次 → 二轮 jury 选 score 更高的那张交付
- **预期收益**：单视角 photoreal_score +20-30 分，5 视角平均 60→80
- **不在 SP1 scope**：reference 图库（SP2）、多 sample 并行选优（SP3）、wizard 选型 UI（SP4）、LoRA 训练（SP5）、第三方 backend plugin（SP1.5）

### Backend 多元化（不绑定单一 vendor）
SP1 不绑定 fal.ai 或任何单一 vendor。设计为**可插拔 BackendAdapter Protocol**：用户在 pipeline_config 里写 `backend_kind` + `base_url` + `api_key_env` + `model_name` 即可接入任意兼容的画图代理模型。SP1 内置 3 个 adapter 起步：
- `gemini_chat_image`：chat-completions 传图式（适配 gemini banana pro 系 / openai gpt-4o vision-image / 类 chat-completions 多模态 API）
- `openai_images_edit`：`/v1/images/edits` REST 风格（适配 gpt-image-2 / stability.ai img2img / 兼容 endpoints）
- `comfyui_workflow_cloud`：ComfyUI workflow JSON 上传到任意兼容云（默认 base_url 指向 fal.ai 的 ComfyUI 服务；用户可改 base_url 接 RunComfy / Comfy Cloud / 自部署 ComfyUI server / 任何兼容 vendor）；**支持 ControlNet hard lock**（canny + depth），适合需要严格几何锁的场景

第三方 vendor adapter 由用户 plugin 注入（SP1.5 工作）。SP1 锁住"内置 3 adapter + 注册表 + 用户配置接入新 vendor 必须实现 BackendAdapter Protocol"的形态契约。

### 北极星 5 gate 自检

| Gate | SP1 兑现方式 |
|---|---|
| 零配置 | `enhance.jury_loop.enabled=true` 默认开启；threshold/cost_cap 有 sane defaults；用户接入新 backend 仅需 base_url + api_key_env + model_name |
| 稳定可靠 | 任何失败路径回退 baseline，**永不阻塞交付**（§5） |
| 结果准确 | retry 优先走支持 ControlNet hard lock 的 backend (`comfyui_workflow_cloud` 内置，可指任何 ComfyUI 兼容云)；通用 backend 靠 jury 二轮评分兜底"不会降分"语义 |
| SW 装即用 | 闭环只跑 cloud backend，与 SolidWorks 解耦；engineering / comfyui 本地 backend 不参与闭环（NO-OP） |
| 傻瓜式 | 用户感知 = "score 低自动重试一次更好的"；中文 summary 写进顶层报告；vendor 切换无须改代码仅改 config |

## §2 模块边界与放置

### 不改的上游
- `cad_pipeline.py:cmd_enhance` 现有的 backend 分发逻辑保留
- `tools/jury/` 现有 jury v2 评分体系保留；仅扩接口（B-2 见 §6）
- `pipeline_config.json` 现有 `enhance.fal` / `enhance.fal_comfy` 段保留

### 新增模块（命名空间 `tools/jury_loop/`）
src 包内 canonical 路径：`src/cad_spec_gen/data/tools/jury_loop/`（**唯一权威位置**；`cad/` 与 `tools/` 都不放规则资源——避免 v2.10 漂移类问题再现，参考 `feedback_historical_debt_isolation.md`）

```
src/cad_spec_gen/data/tools/jury_loop/
├── __init__.py
├── reason_parser.py       # jury reason 文本 → tags 集合（纯函数）
├── rule_table.py          # tags + backend_kind → (prompt_addons, param_overrides)
├── llm_fallback.py        # 规则表 miss 的 tags → addons（复用 jury llm_client）
├── score_select.py        # 选张策略 Protocol + 实现
├── secrets_scrubber.py    # 净化 errors / payload 中的 API key
├── metadata.py            # sidecar metadata.json schema + 写出
├── orchestrator.py        # 视角级 hook 主入口
├── backends/              # ★ 新增：BackendAdapter 抽象与内置实现
│   ├── __init__.py        # BACKEND_REGISTRY 注册表 + register_backend()
│   ├── protocol.py        # BackendAdapter Protocol + BackendRequest/Response NamedTuple
│   ├── gemini_chat_image.py     # chat-completions 传图式（gemini banana / gpt-4o vision-image）
│   ├── openai_images_edit.py    # /v1/images/edits REST 风格（gpt-image-2 / stability.ai）
│   └── comfyui_workflow_cloud.py  # 包装现有 fal_comfy_enhancer.py（baseline 模块名保留）；base_url 默认 fal.ai 但用户可改 RunComfy / Comfy Cloud / 自部署 ComfyUI 等任意兼容 vendor；保 ControlNet hard lock
└── rules/
    └── photoreal_v1.yaml  # 内置规则表（≈15-20 tags 起步）
```

### 改既有
| 文件 | 改动 |
|---|---|
| `cad_pipeline.py` | `cmd_enhance` 内循环改为视角级（B-1）：每个视角跑完 baseline 后调 `orchestrator.run_loop_if_eligible(view, backend, ...)` |
| `pipeline_config.json` | 新增 `enhance.jury_loop` 段（schema 见 §4） |
| `tools/jury/` | photo3d-jury CLI 加 `--single-view <V>` flag（B-2）；不破 batch 模式 |
| ENHANCEMENT_REPORT.json | 顶层加 `loop_summary` 段（D-3 见 §7） |

### 模块单句话职责
- **reason_parser**：纯函数，输入 jury `ViewVerdict.reason`（≤80 字英文），输出 `set[str]`（tags 子集，元素 ∈ `BUILTIN_TAGS`）
- **rule_table**：纯函数 + YAML 加载，输入 `(tags: set[str], backend_kind: str)`，输出 `(prompt_addons: list[str], param_overrides: dict[str, Any])`。`backend_kind` 是注册到 BACKEND_REGISTRY 的字符串 key，不限 fal/fal_comfy
- **llm_fallback**：当 rule_table miss 部分 tags 时调用，输入 `unmapped_reason: str`，输出 `prompt_addons: list[str]`（不产 param_overrides）
- **orchestrator**：唯一持副作用模块，单视角 hook，调上述 + jury subprocess + 二次 enhance（通过 BACKEND_REGISTRY 拿到 adapter）+ 选张
- **metadata**：sidecar `<view>_enhance_meta.json` 的 schema 守门 + 写出
- **rules/photoreal_v1.yaml**：内置规则表，schema_version=1，~15-20 tag 起步
- **backends/protocol.py**：定义 `BackendAdapter` Protocol（详见 §2.1）+ `BackendRequest` / `BackendResponse` NamedTuple
- **backends/{gemini_chat_image,openai_images_edit,comfyui_workflow_cloud}.py**：3 内置 adapter，封装协议差异
- **backends/__init__.py**：`BACKEND_REGISTRY: dict[str, BackendAdapter]` 注册表，启动时自动注册内置 3 adapter；`register_backend(kind, adapter)` 函数给未来 plugin 用

### §2.1 BackendAdapter Protocol

```python
# backends/protocol.py
from typing import Protocol, NamedTuple, Any
from pathlib import Path


class BackendRequest(NamedTuple):
    """retry 调用 backend 的请求载荷。"""
    input_image_path: Path           # baseline 图（img2img 起点）
    prompt: str                      # 文本 prompt（含 prompt_addons 已拼好）
    params: dict[str, Any]           # rule_table 的 param_overrides，仅含该 backend_kind 已知的 keys
    base_url: str                    # API endpoint
    api_key: str                     # 已从 env 读出的 raw key
    model_name: str                  # 用户指定的 model 名


class BackendResponse(NamedTuple):
    """retry 完成的产物。"""
    output_image_path: Path          # 写盘的 retry 图
    actual_cost_usd: float | None    # 实际计费（若 vendor API 返回）；None 时 LoopBudget 用 estimate
    raw_request_summary: dict        # 用于 sidecar.backend_payload（已 scrub_secrets）


class BackendAdapter(Protocol):
    """所有内置 + 用户 plugin 必实现此 Protocol。"""

    @property
    def kind(self) -> str:
        """注册到 BACKEND_REGISTRY 的字符串 key。如 'gemini_chat_image' / 'openai_images_edit' / 'comfyui_workflow_cloud'。"""
        ...

    @property
    def known_params(self) -> dict[str, tuple[float, float]]:
        """该 backend 支持的参数集 + 范围 (min, max)。rule_table.lookup 按此切分参数。"""
        ...

    def supports_controlnet(self) -> bool:
        """是否支持 ControlNet 几何 hard lock。comfyui_workflow_cloud=True；其他通用=False。
        rule_table 在 supports_controlnet=False 时不会注入 canny/depth_strength 这类 ControlNet 参数。"""
        ...

    def estimate_cost_usd(self, request: BackendRequest) -> float:
        """retry 前预估单次调用成本（用于 LoopBudget.try_spend）。"""
        ...

    def call(self, request: BackendRequest, timeout: float) -> BackendResponse:
        """同步调用 backend API；失败应抛带分类的异常 (BackendAuthError / BackendRateLimitError /
        BackendQuotaExceededError / BackendCallError 兜底)。orchestrator 据此映射 retry_failed 子状态。"""
        ...
```

异常分类（统一在 `backends/protocol.py`）：
```python
class BackendError(Exception): ...
class BackendAuthError(BackendError): ...                # → retry_auth_failed
class BackendRateLimitError(BackendError): ...           # → retry_rate_limited
class BackendQuotaExceededError(BackendError): ...       # → retry_quota_exceeded
class BackendCallError(BackendError): ...                # → retry_failed (兜底)
```

每个内置 adapter 必须把 vendor 原生 HTTP 错误映射到这 4 类异常之一；orchestrator 不直接看 HTTP 码。

### 边界检查
- reason_parser 不依赖 jury 内部结构，仅看字符串
- rule_table 不依赖 backend 实现，仅按 backend key 切 param 子集
- orchestrator 不重复 jury 逻辑（subprocess 调既有 CLI），不重复 enhance 逻辑（import 既有 `enhance_image()`）
- llm_fallback 复用 `tools/jury/llm_client.py` 的 client 实例化，但 prompt template 完全不同（jury = vision LLM 看图打分；fallback = text LLM 把 reason 翻译成增强词）

## §3 数据流与时序

### 单视角闭环时序

```
[1] cmd_enhance 跑 baseline            V<i> → V<i>_enhanced_baseline.jpg
       │
       ▼
[2] orchestrator.run_loop_if_eligible(view=V<i>, backend_kind, rc, baseline_path, ...)
       │ Gate-1: backend_kind ∉ BACKEND_REGISTRY
       │     → 重命名 baseline 为最终交付名 V<i>_enhanced.jpg；return loop_status=loop_disabled
       │     注：local-only backend (engineering / comfyui) 不注册到 REGISTRY；
       │     云端 generic backend (gemini_chat_image / openai_images_edit / comfyui_workflow_cloud / 用户 plugin) 都注册。
       │ Gate-2: enhance.jury_loop.enabled == false
       │     → 同 Gate-1
       │
       ▼
[3] photo3d-jury --subsystem <name> --single-view V<i> --image V<i>_enhanced_baseline.jpg
                                                       → ViewVerdict（含 photoreal_score, reason, semantic_checks）
       │ Gate-3: jury 失败 / 返 score 但 reason 空
       │     → loop_status: jury_unavailable | empty_reason；接受 baseline
       │ Gate-4: photoreal_score ≥ jury_loop.threshold（默认 75）
       │     → loop_status: above_threshold；接受 baseline
       │ Gate-5: 累计 cost_so_far + 估算 retry_cost > cost_cap
       │     → loop_status: cost_capped；接受 baseline
       │
       ▼
[4] sanitized_reason = reason_sanitized(verdict.reason)   # SEC-MAJOR-3 防 prompt injection
       tags = reason_parser(sanitized_reason)
       │ Gate-6: tags == ∅
       │     → loop_status: no_tags_parsed；接受 baseline
       │
       ▼
[5] hits = rule_table.lookup(tags, backend)
       │ misses = tags - hits.matched_tags
       │ if misses 且 enhance.jury_loop.llm_fallback==true:
       │     extra_addons = llm_fallback.translate(misses, sanitized_reason)  # 同样传净化版
       │ else:
       │     extra_addons = []
       │ Gate-7: hits == ∅ and extra_addons == []
       │     → loop_status: no_rules_hit_no_llm；接受 baseline
       │
       ▼
[6] orchestrator.apply_overrides(rc_for_retry,
                                 prompt_addons=hits.prompt_addons + extra_addons,
                                 param_overrides=hits.param_overrides[backend])
       │ - rc_for_retry 是 rc 深拷贝，不污染主 config
       │ - prompt: 原 prompt + " | " + addons.join(", ")
       │ - params: base_config[backend] 浅合并 rule_overrides[backend]，rule 赢（A-1）
       │
       ▼
[7] cmd_enhance 二次跑                  V<i> → V<i>_enhanced_retry.jpg
       │ Gate-8: retry 失败（HTTP / timeout / 文件写入冲突）
       │     → loop_status: retry_failed；接受 baseline
       │
       ▼
[8] [仅当 score_select_strategy == "pick_max_jury"，§4.5]
    photo3d-jury --subsystem <name> --single-view V<i> --image V<i>_enhanced_retry.jpg
       │     → retry_verdict（B-2 视角级 jury 二次调用）
       │     // 失败时 retry_verdict = None，treat as 选 baseline
       │
       ▼
[9] 选张（按 score_select_strategy 分支）：
       │ if score_select_strategy == "pick_max_jury":
       │     if retry_verdict is None: pick = baseline      # 二轮 jury 失败，按保守选 baseline
       │     elif retry_verdict.photoreal_score > baseline_verdict.photoreal_score: pick = retry
       │     else: pick = baseline                          # retry 平 / 降分 → 选 baseline（保守）
       │ elif score_select_strategy == "force_retry":
       │     pick = retry                                   # 不二轮 jury，强制接受 retry 输出
       │     # 当 retry 失败 ([7] Gate-8) 已经走过 retry_failed → 接受 baseline 路径，到不了这里
       │
       ▼
[10] 最终交付：将 pick 重命名为 V<i>_enhanced.jpg，另一张保留为 V<i>_enhanced_<otherkind>.jpg
       │ - delivered_kind = "retry" or "baseline"
       │ - 写 sidecar V<i>_enhance_meta.json（§4 schema）
       │ - 累计 loop_summary.{triggered, skipped, total_retries, extra_cost_usd, score_delta}
```

### 多视角推进（v1_anchor 串行 / 非 anchor 并行）

```
reference_mode == "v1_anchor":
    V1 闭环 → 选中高分张作 final_v1
    V2 baseline 用 final_v1 作 anchor → V2 闭环 → 选中高分张作 final_v2
    V3 baseline 用 final_v1 作 anchor （anchor 始终 V1，不滚动）
    ...
    （A-5：V2-V5 用 V1 final 不是 V1 baseline）

reference_mode == "none":
    V1-V5 各自独立闭环，可并行（受 fal API 并发限）
```

### 实现注记

- **跨视角 cost 累计 + 模块归属（M-1 + M-13）**：LoopBudget 提升为通用模块 `src/cad_spec_gen/data/python_tools/enhance_budget.py`（**不**放在 jury_loop 命名空间内），跨 SP1 / SP3 / 未来 SP 共享。
  - 接口：`LoopBudget(cost_cap_usd: float, n_views: int)` 构造；`budget.estimate_remaining()` / `budget.try_spend(amount: float) -> bool`（原子操作，返 True=允许并扣减、False=超 cap） / `budget.spent: float` 只读属性。
  - 线程安全：内部用 `threading.Lock` 保护 spent 的读-改-写。`reference_mode=none` 并行模式下多视角并发调 `try_spend` 仍正确（不会出现"两个视角各估算 spent + retry_cost < cap，都放行，实际合计超 cap"）。
  - cmd_enhance 在视角循环开始前实例化，单视角 hook 接收对象引用并 mutate；写入最终 `loop_summary.extra_cost_usd`。
  - **N-9 (retry 中途失败)**：retry HTTP 失败但 vendor API 可能已扣费——`try_spend` 在 retry 调用**前**估算扣减；retry 失败时不退还（vendor 已扣费实情）。spec 在 user_friendly_summary 解释"重试调用失败但仍可能产生 vendor 端费用，请到对应 vendor dashboard 核对"。
- **v1_anchor 路径传递（BL-4 hero_image 状态）**：现有 `cmd_enhance` 已有 `reference_mode=v1_anchor` 处理逻辑（在 enhance_image 调用处用 V1 enhanced 路径，局部变量 `hero_image`）。SP1 必须保证：
  - V1 orchestrator 完成 [10] 重命名（pick → `V1_enhanced.jpg`）后，**立即**把最终交付路径写回 cmd_enhance 局部 `hero_image` 变量（通过返回值或共享 state 对象）；orchestrator 接口签名包含 `out_hero_image: list | None` 或返回 `(delivered_path: Path, ...)`，cmd_enhance 接收后赋值给 hero_image。
  - 这样 V2 进入时的 anchor 永远指向 `V1_enhanced.jpg`（即用户最终拿到的 V1 张），不会错误地指向已被重命名/删除的 `V1_enhanced_baseline.jpg`。
  - L2 测试覆盖：retry 成功后 V2 anchor 路径 == `V1_enhanced.jpg`（path equality assertion）；retry 失败回 baseline 后 V2 anchor 路径 == `V1_enhanced.jpg`（即 baseline 被重命名为 final 名）。
- **视角串行约束**：reference_mode=v1_anchor 时 cmd_enhance 视角循环必须串行（V1 hook 完才进 V2）；reference_mode=none 时可保留现有并行实现，依赖 LoopBudget 线程锁。
- **视角级异常隔离（DRIFT-MAJOR-7）**：cmd_enhance 视角循环必须以 try/except 包住 orchestrator 调用，捕获**所有** Exception（不仅 IOError）：
  ```python
  for view in views:
      try:
          orchestrator.run_loop_if_eligible(view, backend, rc, baseline_path, budget, hero_image)
      except Exception as e:
          # 写降级 sidecar：loop_status=retry_failed, errors[] 含 scrub_secrets(traceback)
          metadata.write_degraded_sidecar(view, error=e)
          # 不重新抛——继续 V<i+1>
  ```
  L2 测试覆盖：orchestrator raise 任意 Exception 时其他视角不受影响 + sidecar 写降级形态。
- **跨平台 rename（DRIFT-MAJOR-2）**：§3 [10] 文件重命名禁用 `os.rename`（Windows dst 已存在抛 FileExistsError，Linux 静默覆盖）。强制语义：`Path(dst).unlink(missing_ok=True); Path(src).replace(dst)`。L2 fixture 加"dst 已存在"case 锁跨平台行为。
- **subprocess 解释器（DRIFT-MAJOR-5）**：所有 subprocess 调 `python -m tools.photo3d_jury` 必须用 `[sys.executable, "-m", ...]`（继承父进程解释器与 sys.path），禁用 `["python", ...]`。否则 wizard 创建的 venv 会被绕过去找系统 Python。
- **retry 成本估算（TRAP-10）**：每个 BackendAdapter 自己实现 `estimate_cost_usd(request) -> float`，LoopBudget 调用之而非读硬编码常量表。`enhance_budget.py` 仅保留 `JURY_LLM_CALL_COST_USD = 0.005` 常量（jury LLM 调用成本与 backend 无关）。
  ```python
  # backends/comfyui_workflow_cloud.py 示例：
  def estimate_cost_usd(self, request: BackendRequest) -> float:
      return 0.18   # TODO: 实测后调；若 vendor 返回 actual billing 字段，由 budget.record_actual 修正

  # backends/gemini_chat_image.py 示例（按 model 分价）：
  def estimate_cost_usd(self, request: BackendRequest) -> float:
      pricing = {"gemini-3-pro-image-preview": 0.04, "gemini-2.5-flash-image": 0.01}
      return pricing.get(request.model_name, 0.05)
  ```
  pick_max_jury 模式下单视角 try_spend 估算 = `adapter.estimate_cost_usd(request) + JURY_LLM_CALL_COST_USD`；force_retry = `adapter.estimate_cost_usd(request)`。retry 完成后若 BackendResponse.actual_cost_usd 不为 None 则 `budget.record_actual(actual_cost_usd)` 修正 spent；为 None 则在 sidecar.warnings 加 `cost_estimated_only`。

## §4 配置 schema

### 4.1 `pipeline_config.json` 新增段（M-5 中文化 + M-6 advanced 折叠 + M-8 显式数字）

顶层只暴露 2 个 key（主开关 + 紧急刹车），其他高级项收进 `advanced` 子段，外行用户默认无需触碰。

```jsonc
{
  "enhance": {
    "backend": "fal_comfy",
    // ... 既有 fal/fal_comfy/comfyui/gemini/engineering 段不变 ...
    "jury_loop": {
      "_doc": "AI 评分反馈闭环：跑完一次后若分数低于阈值，自动重试一次更好的图。需 backend_kind 注册到 BACKEND_REGISTRY（gemini_chat_image / openai_images_edit / comfyui_workflow_cloud / 用户 plugin），本地 backend (engineering / 本机 comfyui server) 不参与，自动忽略。",

      "enabled": true,
      "_enabled_doc": "总开关。true = 启用闭环 / false = 跑一次就交付。",

      "cost_cap_usd": 1.5,
      "_cost_cap_doc": "全口径预算上限（含重试 + 二轮评分 + AI 兜底翻译 token 费）。约 ¥10 人民币 / 单次跑全 5 视角；超额自动停。默认 1.5 = 5 视角×0.25 + 安全余量。如视角数明显不同，可手动调。",

      "backend": {
        "_backend_doc": "闭环 retry 调用的 backend 配置。SP1 内置 3 种 kind；用户切 vendor 仅改这个段。",
        "kind": "gemini_chat_image",
        "_kind_doc": "可选值：gemini_chat_image (chat-completions 传图，适配 gemini banana / openai gpt-4o vision-image) / openai_images_edit (REST /v1/images/edits，适配 gpt-image-2 / stability.ai img2img) / comfyui_workflow_cloud (ComfyUI workflow JSON 上传到任意兼容云：fal.ai / RunComfy / Comfy Cloud / 自部署，唯一支持 ControlNet 几何 hard lock 的内置选项) / 用户 plugin 注册的其他 kind。",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "_base_url_doc": "API endpoint URL。default 是 gemini chat-completions endpoint；切其他 vendor 改这里。",
        "api_key_env": "GEMINI_API_KEY",
        "_api_key_env_doc": "API key 来自哪个环境变量名。建议用 env 不直接写明文 key 进 config 防误提交。常见值：GEMINI_API_KEY / OPENAI_API_KEY / FAL_KEY / 自定义。",
        "model_name": "gemini-3-pro-image-preview",
        "_model_name_doc": "vendor 模型 ID。kind=gemini_chat_image 用 gemini-* / kind=openai_images_edit 用 gpt-image-2 / kind=comfyui_workflow_cloud 不需要（用 workflow JSON 内嵌的 checkpoint 决定）。",
        "timeout_s": 180,
        "_timeout_doc": "单次 retry 调用超时（秒）。"
      },

      "advanced": {
        "_advanced_doc": "高级项，默认请勿动。仅当你明确知道在做什么再调。",

        "threshold": 75,
        "_threshold_doc": "photoreal_score < threshold 才触发 retry。独立于 jury 顶层 min_photoreal_score（默认 60，决定 jury 自身 accepted/preview status）。65=低槛 / 75=默认 / 85=严苛。",

        "max_retries": 1,
        "_max_retries_doc": "重试轮数上限。SP1 仅支持 1，多轮在后续版本探索。",

        "llm_fallback": true,
        "_llm_fallback_doc": "规则库未匹配的反馈词是否找 AI 翻译成提示词。关闭则未匹配即放弃重试。约 ¥0.05/视角额外 LLM token 费用，已计入 cost_cap_usd 预算。",

        "rule_table_path": null,
        "_rule_table_path_doc": "null = 用内置 photoreal_v1.yaml；显式路径则在内置之上 merge 用户 yaml。yaml schema_version 不匹配时直接报错（不静默丢弃用户规则）。",

        "score_select_strategy": "pick_max_jury",
        "_strategy_doc": "重试后挑哪张：pick_max_jury = 再评分一次挑高分图（推荐，更安全）/ force_retry = 直接用重试图（省一次评分费但可能更差）。SP3 多 sample 落地时会扩第三种 pick_best_of_n。",

        "_protocol_note": "score_select_strategy 在实现层是可插拔 Strategy Protocol（不是固定 enum），新增策略只需注册新 Protocol 实现，不破现有契约。"
      }
    }
  }
}
```

**配置项可见性约束**：顶层 `enabled` + `cost_cap_usd` 在 wizard 默认配置生成时显式写入；`advanced.*` 全部由 schema default 兜底，不写入用户 pipeline_config.json，仅当用户主动 override 时才出现。这样外行用户的 config 文件极简。

**顶层 vs advanced 同名禁共存（DRIFT-MAJOR-4）**：用户配置中**禁止**在顶层与 advanced 中同时指定同名 key（如 `enabled` 既出现在顶层又出现在 advanced 内）。schema 校验阶段 hard fail 提示 "key '<name>' 同时出现在顶层与 advanced，请移除其一"。这避免实施层因合并优先级歧义引入隐性 bug。L1 测试加 fixture 锁此契约。

**LLM fallback vendor 明示（OPS-MAJOR-4）**：`llm_fallback` 默认复用 jury 的 LLM 服务（`jury_config` 里的 `model`，gemini 系或后续 swap）—— 即 vision 与 text 同 vendor 同 client。**SP1 不支持单独配置 fallback LLM**（如想用不同 vendor 须等 SP1.5）。如果 jury vendor 服务挂，jury_unavailable 与 llm_fallback_failed 同时触发——`loop_status` 优先级取 `jury_unavailable`（因为 [3] Gate-3 已经早跳出，根本进不到 [5]）。一旦 SP1.5 引入 `llm_fallback_model` 单独配置，spec 须更新此条说明。

### 4.2 内置规则表 schema (`rules/photoreal_v1.yaml`)

```yaml
schema_version: 1
rules:
  - id: plastic_look_to_metallic
    when_tags: [plastic_look]
    prompt_addons:
      - "matte metallic finish, anodized aluminum"
      - "subtle anisotropic reflections"
    param_overrides:
      # 顶层 key 是 backend_kind（注册到 BACKEND_REGISTRY 的字符串），不限内置 3 种
      gemini_chat_image:        { temperature: 0.3, top_p: 0.9 }
      openai_images_edit:       { quality: "hd", style: "natural" }
      comfyui_workflow_cloud:   { denoise_strength: 0.45, cfg_scale: 7.5 }
      # rule 在某 backend_kind 下没参数可调时，省略该 key 即可（参见下条 rule）

  - id: flat_lighting_to_studio
    when_tags: [flat_light]
    prompt_addons:
      - "studio softbox lighting from left, fill light from right"
      - "subtle rim light, gradient seamless backdrop"
    param_overrides: {}

  - id: soft_edge_to_sharp
    when_tags: [soft_edge, blurry]
    prompt_addons:
      - "razor-sharp product edges, crisp specular highlights"
    param_overrides:
      # 仅 comfyui_workflow_cloud 支持 ControlNet 边缘锁；其他 backend 此规则只贡献 prompt_addons
      comfyui_workflow_cloud:   { canny_strength: 0.95, canny_end_pct: 0.95 }

  - id: dull_color_to_vibrant
    when_tags: [dull_color, washed_out]
    prompt_addons:
      - "vivid saturated product colors, professional color grading"
    param_overrides: {}

  - id: dark_to_brighter
    when_tags: [dark_overall]
    prompt_addons: ["bright key light, high-key product photography"]
    param_overrides:
      comfyui_workflow_cloud:   { denoise_strength: 0.4 }
      gemini_chat_image:        { temperature: 0.4 }

  - id: cluttered_bg_to_clean
    when_tags: [cluttered_bg, distracting_bg]
    prompt_addons: ["seamless white backdrop, isolated product, clean studio background"]
    param_overrides: {}

tag_dictionary:
  plastic_look:    ["plastic", "toy-like", "rubbery", "matte plastic"]
  flat_light:      ["flat lighting", "no shadows", "ambient only", "diffuse"]
  soft_edge:       ["soft edge", "blurry edge", "out of focus", "fuzzy"]
  blurry:          ["blurry", "low resolution", "out of focus"]
  dull_color:      ["dull", "muted", "low contrast"]
  washed_out:      ["washed out", "faded", "desaturated"]
  dark_overall:    ["too dark", "underexposed", "low light"]
  cluttered_bg:    ["cluttered background", "busy background"]
  distracting_bg:  ["distracting background", "noisy backdrop"]
  # 其他备选 tag（rule 暂未配，留白等用户/后续迭代）：
  dull_metal: []
  fake_glass: []
  missing_pbr: []
  harsh_shadow: []
  blown_highlights: []
  jagged: []
  oversharpened: []
  oversaturated: []
  color_cast: []
  dirty_bg: []
```

### 4.3 用户覆写 yaml 合并语义
- 内置 `photoreal_v1.yaml` 永远先加载（schema_version=1 锁）
- **YAML 加载安全（SEC-MAJOR-1）**：所有 yaml 加载必须用 `yaml.safe_load`；禁用 `yaml.load`（默认 Loader 反序列化任意 Python 对象 = RCE 漏洞 CVE-2017-18342）。`rule_table.py` import 时通过 lint 锁住（添加 ruff rule `UP` 类 yaml.unsafe-load 或自定义 grep guard 测试）
- **用户 yaml 路径限制（SEC-MAJOR-1）**：`enhance.jury_loop.advanced.rule_table_path` 必须解析为 `project_root` 子路径内（用 `Path(path).resolve().is_relative_to(project_root.resolve())` 校验）；超出范围 hard fail "rule_table_path 必须在项目目录内"
- 合并语义：
  - `rules`：同 id → 用户替换内置（**保持内置在合并 list 中的位置不变**）；新 id → **追加到 list 末尾**；用户 rules 内部相对顺序保留；不允许删除内置 rule（用户想关闭某条 rule 应在 yaml 里 `rules: [{id: foo, _disabled: true}]`，spec v1 不实现 disabled，留 v2）
  - `tag_dictionary`：同 tag key → 用户 patterns 追加（不替换）；新 tag key → 追加；不对称设计的理由是"内置 patterns 是该 tag 的官方判定基线，用户应当扩展而非替换；tag 含义本身（key）才允许重定义"
  - **多规则同时命中合并顺序（DRIFT-MAJOR-1）**：合并后的 list 顺序 = 内置规则按 yaml 出现顺序（替换不动位置） + 用户新增规则按 yaml 末尾追加。`rule_table.lookup()` 遍历此顺序应用 prompt_addons / param_overrides，"后到先得"覆盖语义按合并 list 顺序判定。L1 测试加 3 条 fixture 锁此契约（替换/追加/混合）
- **schema_version 不匹配处理（BL-5 + SEC-MINOR-3 修正）**：用户 yaml `schema_version` 缺失或不被引擎支持时，**降级为 `loop_status=loop_disabled`** + 显式 warn 写到 sidecar.warnings[] 与 stderr，**而不是 orchestrator 全程 exit 非零**。rationale：CI 环境用户提交错误 config 不应阻塞整个 enhance/CI（避免 DoS）；但失败必须显式可见——`loop_status=loop_disabled` 配合 warn 既不静默丢用户规则，也不让单一配置错误拖垮整个 pipeline。**唯一**例外：内置 `photoreal_v1.yaml` 加载失败仍然 hard fail（这是 packaging bug 不是 user 输入问题）—— 但见下条懒加载策略
- **内置 yaml 懒加载（OPS-MINOR-6）**：内置 `photoreal_v1.yaml` 不在模块 import 时 parse；模块 import 时仅检查包内资源**存在**（`importlib.resources.files("cad_spec_gen.data.tools.jury_loop.rules") / "photoreal_v1.yaml"` 调 `.is_file()`），实际 parse 推到 `orchestrator.run_loop_if_eligible()` 首次调用。这样：
  - pip 装包漏 yaml 不会让整个 cad_pipeline import 失败（只阻塞 enhance 闭环路径）
  - codegen / render / 普通 jury 等无关功能不受影响
  - 闭环首次调用时 yaml 缺失 → 降级 `loop_disabled` + warn "内置 photoreal_v1.yaml 缺失，请重装 cad-spec-gen 修复 packaging"
  - 内置 yaml 解析失败（语法错）仍 hard fail 抛 import-time exception——这种情况是 dev 改 yaml 写错语法的开发期事故，应阻塞 release 而非 silently degrade
- **schema_version 演进策略（BL-1 向前兼容降级）**：
  - 引擎 vN 加载 yaml schema_version=M 的兼容矩阵：N == M → 全字段生效；N > M（旧 yaml 在新引擎下） → **未知字段忽略**，已知字段全生效，引擎仅写一行 info "用户 yaml 为旧版 schema vM，已按兼容模式加载"；N < M（新 yaml 在旧引擎下） → hard fail（同上）
  - "v1 yaml 永远可被 vN 引擎加载"是不可破坏的契约——这意味着 v2 引擎对 yaml 新增字段必须是可选的（缺省值能 fall back 到 v1 行为），不允许"v2 必填字段"破坏 v1 yaml
  - SP1 实现仅锁 schema_version=1；vN 引擎的扩展由 SP2+ 落地时引入，但策略约束在此 spec 锁死，避免 SP2 写代码时偷懒破契约

- **param_overrides 结构与合并约束（M-11 + M-12）**：
  - **结构**：`param_overrides[backend_kind]` 必须是 **flat key-value dict**（一级），值类型限定为 `int | float | str | bool`。**禁止**嵌套 dict（如 `{"controlnet": {"weight": 0.8}}` 不被接受），避免浅合并 vs 深合并的歧义。yaml 加载时若发现嵌套 dict 值，hard fail（schema 校验阶段，不延迟到 runtime）
  - **合并语义**：base_config[backend_kind] 与 rule_overrides[backend_kind] 浅合并（rule 赢），等价 `{**base, **override}`；多规则同时命中时按规则在 yaml 中的出现顺序后到先得
  - **值范围校验（M-12）按 backend_kind 维度切分**：每个 BackendAdapter 通过 `known_params` 属性声明自己支持的参数集 + 范围 (min, max)。`rule_table.lookup(tags, backend_kind)` 时：
    1. 通过 `BACKEND_REGISTRY[backend_kind].known_params` 拿到该 backend 的参数白名单
    2. 该 backend 段下的已知 key + 类型 int|float|bool|str 越界 → clamp 到边界 + sidecar.warnings[] 加 `param_clamped: <kind>.<key>=<orig>→<clamped>`
    3. 该 backend 段下的未知 key（不在 known_params 表）→ 静默忽略 + sidecar.warnings[] 加 `unknown_param: <kind>.<key>`
    4. 已知 key 但值类型错（如 `canny_strength: "high"`） → hard fail（schema 阶段）
  - 内置 adapter 的 known_params 示例：
    - `comfyui_workflow_cloud`：`{"denoise_strength": (0.0, 1.0), "cfg_scale": (1.0, 30.0), "canny_strength": (0.0, 1.0), "canny_end_pct": (0.0, 1.0), "depth_strength": (0.0, 1.0), "steps": (1, 200), "guidance_scale": (1.0, 30.0)}`
    - `gemini_chat_image`：`{"temperature": (0.0, 2.0), "top_p": (0.0, 1.0), "top_k": (1, 100)}`
    - `openai_images_edit`：`{"quality": (None, None), "style": (None, None), "n": (1, 4), "size": (None, None)}`（None 表示非数值参数，仅做存在性 + 类型校验，不 clamp）
  - 用户 plugin adapter 自管 `known_params`，与内置同等地位

- **yaml 字段集 closed schema（DRIFT-MINOR-6）**：rule yaml 是 closed schema，即仅允许下列字段集：
  - 顶层：`schema_version` / `rules` / `tag_dictionary` / `_*` (任意下划线开头字段允许，作扩展位)
  - rules item：`id` / `when_tags` / `prompt_addons` / `param_overrides` / `_*` / `_disabled`（v2 启用）
  - 任何**非下划线开头**的未知字段 → **hard fail** 提示"unknown field <name>，是否拼写错误？"。下划线开头字段（如 `_doc` / `_notes`）允许，作 yaml 注释/扩展位
  - rationale：拼写错误（如 `prompt_addon` 漏 s）会被 schema 校验立即抓到，不会静默丢用户配置；下划线规则给未来扩展留位且不破现有契约

### 4.4 sidecar metadata schema (A-3 + BL-2 + BL-3 + M-9)

文件：`<render_dir>/<view>_enhance_meta.json`，永远写。

**schema 演进策略（BL-2 additive-only）**：sidecar 字段集采用 additive-only 演进。SP1 锁 `$schema_version=1` 字段集见下；后续 SP2-5 仅追加新字段、不删除旧字段、不改字段类型。`$schema_version` 仅在引入"语义不向后兼容变更"时才升大版（v1→v2 实际 SP1-5 内可能永不发生）。**所有消费方（包括内部 orchestrator、photo3d_autopilot、外部解析器）必须容忍未知字段**——这是契约级约束，写进 spec 不允许打破。

```jsonc
{
  "$schema_version": 1,
  "view": "V1",                              // string，与 manifest view key 一致
  "backend": "fal_comfy",                    // string ∈ {gemini, comfyui, fal, fal_comfy, engineering}
  "loop_eligible": true,                     // bool，false 表示 backend 不在 {fal, fal_comfy} 或 jury_loop.enabled=false
  "loop_status": "delivered_retry",          // enum，见 §4.5
  "loop_skipped_reason": null,               // string | null，loop_status != delivered_* 时填
  "delivered_kind": "retry",                 // enum: "baseline" | "retry"
  "baseline": {
    "image_path": "V1_enhanced_baseline.jpg",
    "photoreal_score": 58,
    "semantic_checks": {"geometry_preserved": true, "material_consistent": true, "photorealistic": false, "no_extra_parts": true, "no_missing_parts": true},
    "reason": "plastic look, flat lighting"
  },
  "retry": {                                  // null 当 retry 未跑
    "image_path": "V1_enhanced_retry.jpg",
    "photoreal_score": 78,
    "semantic_checks": { /* 同上结构 */ },
    "reason": "improved metallic finish",
    "final_prompt": "<完整 prompt 字符串>",     // OPS-MAJOR-1 实拼后传给 fal 的 prompt（≤4000 字截断）
    "backend_payload": {                       // OPS-MAJOR-1 实发 fal payload（API key 已 redact）
      /* comfyui_workflow_cloud 时含 cfg_scale / steps / canny_strength / depth_strength / seed / ...；
         force_retry 模式下也写（虽然没二轮 jury，但实拼 payload 必须留）；
         经 scrub_secrets() 后写出，永不含 FAL_KEY / OPENAI_API_KEY / GEMINI_API_KEY */
    }
  },
  "tags_parsed": ["plastic_look", "flat_light"],
  "rules_hit": ["plastic_look_to_metallic", "flat_lighting_to_studio"],
  "rules_missed_tags": [],
  "llm_fallback_used": false,
  "prompt_addons_applied": ["matte metallic finish, anodized aluminum", "studio softbox lighting from left, fill light from right"],
  "param_overrides_applied": {"comfyui_workflow_cloud": {"denoise_strength": 0.45, "cfg_scale": 7.5}},
  "user_friendly_summary": "已自动重试 1 次，画面质感分数从 58 提升到 78（提升 20）。",  // D-1 中文
  "loop_status_zh": "重试成功，已交付重试图",  // BL-3 中文化 loop_status，与 4.6 enum 一一映射
  "retry_score_delta": 20,                   // int|null，retry 跑通后 retry.score - baseline.score；可正/0/负；retry 未跑或 force_retry 未二轮评分则为 null
  "delivered_score_delta": 20,               // int|null，最终交付张相对 baseline 的净收益；pick_max_jury 模式下永 ≥ 0；force_retry 模式下永为 null（无法对比）；retry 未跑时为 0
  "extra_cost_usd": 0.18,                    // float，retry+二轮 jury 累计估算
  "warnings": [                              // list[str]，e.g. "unknown_param: comfyui_workflow_cloud.bogus_param"
    /* "rule_table:user_yaml_ignored: schema mismatch v=2 != 1" 当 BL-5 hard fail 触发不会到这；但 5.11 unknown_param 仍走这里 */
  ],
  "errors": [                                // list[ErrorEntry]，retry/jury 失败堆栈摘要 + 用户操作提示
    /* {
      "code": "retry_http_timeout",
      "message_summary": "fal API 调用超时（≤200 字堆栈摘要，已经过 scrub_secrets 净化）",
      "user_action_hint": "网络超时，请检查代理/重试一次；持续失败可调高 enhance.fal_comfy.timeout"
    } */
  ]
}
```

#### 写盘前必须经过的安全过滤（SEC-MAJOR-2 + SEC-MINOR-2）

`metadata.write_sidecar(view, ...)` 实现层强制：
- **路径净化（SEC-MAJOR-2）**：sidecar 文件名中嵌入的 `<view>` 字段先调 `Path(view).name` 取 basename + 验证不含 `..` / 路径分隔符 / 绝对路径前缀；不通过则抛 ValueError 拒绝写入。同样适用于 `<view>_enhanced_retry.jpg` / `<view>_enhanced_baseline.jpg` / `<view>_enhanced.jpg` 一切以 view 为前缀的文件名。这阻止 manifest-controlled 的 `view: "../../etc/passwd"` 攻击
- **secrets 净化（SEC-MINOR-2）**：`errors[].message_summary` 写入前必须经 `scrub_secrets(text, env_prefixes=["FAL", "OPENAI", "GEMINI", "ANTHROPIC"])` 处理——按已知 env var 前缀正则替换 `<KEY>=<value>` 与 `Bearer <token>` 形式为 `[REDACTED]`；同样适用于 `backend_payload`（fal 请求体可能含 Authorization header 残留）
- 工具函数：`tools/jury_loop/secrets_scrubber.py`，纯函数，单独 L1 测试覆盖（10+ 个 fixture：FAL_KEY 直接出现 / Bearer token / Authorization header / 嵌套 dict 内的 key 字段）

#### sidecar 在特殊状态下的形态约定
- `loop_status == "loop_disabled"`：`loop_eligible=false` / `delivered_kind="baseline"` / `baseline.image_path` 是最终交付名 `V<i>_enhanced.jpg`（N-1 决议：Gate-1/Gate-2 提前退出时直接重命名 `_baseline.jpg → _enhanced.jpg`，等同步骤 [10] 简化路径）/ `retry=null` / `tags_parsed=[]` / `prompt_addons_applied=[]` / `extra_cost_usd=0` / `retry_score_delta=null` / `delivered_score_delta=0` / `user_friendly_summary="该 backend 不支持闭环优化"`
- `loop_status == "above_threshold"`：`delivered_kind="baseline"` / `baseline` 含完整 jury verdict / `retry=null` / `retry_score_delta=null` / `delivered_score_delta=0` / `user_friendly_summary` 形如 "首轮分数 78 已达标，无需重试"
- `loop_status == "delivered_retry"` (pick_max_jury)：`delivered_kind="retry"` / `baseline` 与 `retry` 字段都有完整 verdict / `retry_score_delta = retry.photoreal_score - baseline.photoreal_score`（必为正，因为 pick_max_jury 选了 retry 必然 retry.score > baseline.score） / `delivered_score_delta = retry_score_delta`
- `loop_status == "delivered_retry"` (force_retry)：`delivered_kind="retry"` / `baseline` 含完整 verdict 但 `retry.photoreal_score=null` + `retry.semantic_checks=null` + `retry.reason=null`（force_retry 不二轮评分） / `retry.final_prompt` + `retry.backend_payload` 仍写（OPS-MAJOR-1 复盘需要） / `retry_score_delta=null` / `delivered_score_delta=null`
- `loop_status == "delivered_baseline"`（retry 跑通但 baseline 高分被选）：`delivered_kind="baseline"` / `baseline` + `retry` 都有 verdict / `retry_score_delta` 可能为 0 或负（实际收益） / `delivered_score_delta = 0`（最终交付的是 baseline）
- 其他 `delivered_baseline` 系列（jury_unavailable / no_tags_parsed / cost_capped / retry_failed 等）：`delivered_kind="baseline"` / `retry=null`（retry 未跑） / `retry_score_delta=null` / `delivered_score_delta=0`

字段保持可序列化稳定结构——下游解析按 additive-only 契约容忍未知字段；缺省值统一用 `null`/`[]`/`0` 而非省略。`retry_score_delta` 与 `delivered_score_delta` 双字段设计（M-9）：前者度量 retry 实际效果（可负，做后续优化数据），后者度量用户实际拿到的提升（永非负，进 loop_summary 平均）。

### 4.5 `score_select_strategy` 语义（C-3 决议 + M-2 可插拔 Protocol）

#### 4.5.1 SP1 内置两种策略

| 取值 | 流程 | 适用 |
|---|---|---|
| `pick_max_jury`（**默认**） | retry 跑完后**再**调 jury 一次（§3 [8]）；比较 baseline / retry 的 `photoreal_score`；选高分张。retry 平/降分时选 baseline（保守）；二轮 jury 失败时选 baseline。 | 推荐：付一次额外 jury 调用换"不会降分"安全网 |
| `force_retry` | retry 跑完后**不**再调 jury（§3 [8] 跳过）；强制选 retry 张。仅当 retry 本身失败（HTTP/timeout）才回退 baseline。 | cost 极敏感场景；接受"偶发降分"风险 |

二选一在 `pipeline_config.json` 的 `enhance.jury_loop.advanced.score_select_strategy` 设置。MEDIUM 起步默认即可，只在用户实测大量数据后才考虑切 force_retry。

#### 4.5.2 实现：可插拔 Strategy Protocol（不是 enum）

```python
# tools/jury_loop/score_select.py
from typing import Protocol, NamedTuple

class CandidateImage(NamedTuple):
    image_path: str
    verdict: ViewVerdict | None  # None 表示尚未评分

class SelectionResult(NamedTuple):
    pick: CandidateImage
    extra_jury_calls: int   # 0 = 不需要额外 jury 调用，1+ = 实际调用次数
    rationale: str          # 用于 sidecar.user_friendly_summary 拼接

class ScoreSelectStrategy(Protocol):
    def select(self,
               candidates: list[CandidateImage],
               jury_callable: Callable[[str], ViewVerdict],
               budget: LoopBudget) -> SelectionResult: ...

# SP1 实现两个策略：
class PickMaxJuryStrategy: ...      # 二张候选 + 二轮 jury
class ForceRetryStrategy: ...        # 二张候选 + 不二轮 jury，强选 retry
# SP3 落地时新增（不破契约）：
# class PickBestOfNStrategy: ...     # N 张候选 + N-1 轮 jury，挑最高
```

config 层 `score_select_strategy` 字符串 → Strategy 实例的注册表在 `score_select.py` 维护：`STRATEGY_REGISTRY: dict[str, type[ScoreSelectStrategy]]`。新增策略只需注册新 key，orchestrator 调用方代码不改。

**SP3 兼容性约束**：`candidates: list[CandidateImage]` 设计为列表（不是 Tuple[base, retry]），SP3 多 sample 时直接传 N 张；SP1 始终传 2 张（baseline + retry）。这是 SP1 必须遵守的接口契约，不能为方便临时改成 2-tuple。

### 4.6 `loop_status` enum (A-4 + BL-3 中文化)

| enum (英文，写代码 / 测试用) | 中文 (写 sidecar.loop_status_zh / log 用) | 含义 |
|---|---|---|
| `delivered_baseline` | "已交付首轮图（多种原因之一）" | 接受 baseline 交付的统称（具体原因看 `loop_skipped_reason` 字段） |
| `delivered_retry` | "重试成功，已交付重试图" | retry 跑通且二轮 jury 选中（pick_max_jury 模式） |
| `loop_disabled` | "该 backend 不支持闭环优化" | jury_loop.enabled=false 或 backend_kind 未注册到 BACKEND_REGISTRY |
| `above_threshold` | "首轮分数已达标，无需重试" | baseline score ≥ threshold |
| `cost_capped` | "闭环预算耗尽，剩余视角接受首轮图" | 累计成本超 cap |
| `no_tags_parsed` | "评分反馈未识别已知问题，接受首轮图" | jury reason 里没有任何已知 tag 关键词 |
| `no_rules_hit_no_llm` | "规则库未匹配，AI 兜底已关闭，接受首轮图" | rule_table 全 miss 且 llm_fallback 关闭 |
| `jury_unavailable` | "AI 评分不可用，接受首轮图" | jury subprocess 失败/网络/API key 失效 |
| `empty_reason` | "AI 评分未返回反馈文本，接受首轮图" | jury 返回但 reason 字段空 |
| `llm_fallback_failed` | "AI 兜底翻译失败，接受首轮图" | 规则表**全** miss + LLM 调用失败；规则表部分命中时 LLM 失败不阻断 retry，落 warnings[] |
| `retry_failed` | "重试调用失败，接受首轮图" | retry enhance 调用泛化失败（HTTP / timeout / 写文件冲突 / 未识别错误） |
| `retry_rate_limited` | "服务限流，请稍后重试" | retry 收到 429 / Too Many Requests / Retry-After header |
| `retry_quota_exceeded` | "服务账户余额不足，请充值后重试" | retry 收到 402 / Payment Required / quota exceeded 错误码 |
| `retry_auth_failed` | "API key 无效，请检查配置" | retry 收到 401 / 403 / Invalid API key |

固化含义：以 `delivered_` 前缀的两个是终态成功；其余皆"接受 baseline" 的具体原因细分。所有 sidecar 写出时 `loop_status_zh` 必须按此表机器映射，禁止自由翻译。

**retry 错误码细分映射规则（OPS-MAJOR-5）**：fal API 返回错误时 orchestrator 按下列优先级匹配状态：
- HTTP 401/403 + body 含 "invalid" / "auth" → `retry_auth_failed`
- HTTP 402 / body 含 "quota" / "balance" / "insufficient" → `retry_quota_exceeded`
- HTTP 429 / 含 Retry-After header → `retry_rate_limited`
- 其他 HTTP 4xx/5xx / timeout / 网络错误 → `retry_failed`（兜底）

`user_action_hint` 按上表中文文案给出（写进 errors[].user_action_hint）。

## §5 错误处理（共性 + 详细列）

### 共性原则
1. **永不阻塞交付**：任何失败回退 baseline，至少让用户拿到 baseline
2. **metadata.json 是事实来源**：每个视角写一份 sidecar；`errors[]` 内是堆栈摘要（≤200 字/条）
3. **顶层报告也要可见**：ENHANCEMENT_REPORT.json 顶层 `loop_summary` 段聚合所有视角的 `loop_status`（§7）
4. **log level 层次**：fatal/error 不存在；warn = jury/yaml schema 不可用；info = loop_skipped_*；debug = tag 命中详情
5. **预算守门次序**：每次 retry 前估算成本 → 累计 > cap → 接受 baseline；cap 默认 `n_views × 0.25 USD`，启动时计算；用户显式数值则锁死（C-4）

### 失败矩阵

| 失败点 | loop_status | 用户日志（中文） |
|---|---|---|
| 5.1 backend_kind 未注册到 BACKEND_REGISTRY | `loop_disabled` | （无 warning） |
| 5.2 jury_loop.enabled=false | `loop_disabled` | （无 warning） |
| 5.3 jury subprocess 失败 | `jury_unavailable` | warn `Jury 不可用，跳过 prompt 闭环；接受 baseline` |
| 5.4 jury 返 score 但 reason 空 | `empty_reason` | warn `Jury 未给出反馈文本；接受 baseline` |
| 5.5 reason_parser 0 tag 命中 | `no_tags_parsed` | info `Jury 反馈中未识别已知问题；接受 baseline` |
| 5.6 rule_table 全 miss + llm_fallback=false | `no_rules_hit_no_llm` | info `规则表未命中，LLM 回退已关闭；接受 baseline` |
| 5.7 LLM fallback 调用失败 | `llm_fallback_failed`（仅当规则表也全 miss） | warn `LLM 回退失败；接受 baseline` |
| 5.8 retry HTTP 失败 / timeout | `retry_failed` | error `重试失败，接受 baseline；详见 sidecar.errors[]` |
| 5.9 retry 写文件冲突 | `retry_failed` | error 同上 |
| 5.10 yaml schema_version 不匹配 | （启动时事件，不影响某视角 status） | warn `用户规则表 schema 版本不兼容，使用内置 v1` |
| 5.11 yaml param_overrides 含未知 key | （写入 metadata.warnings） | （单视角 warning，不阻塞） |
| 5.12 cost cap 触发 | `cost_capped` | warn `闭环预算耗尽；剩余视角接受 baseline；调高 enhance.jury_loop.cost_cap_usd 解除` |
| 5.13 二轮 jury 失败（C-3 路径） | `delivered_baseline`（按"二轮 jury 不可用 → 选 baseline"语义） | info `二轮评分失败，按 baseline 交付` |

### Hard fail 极少例外
- 内置 `photoreal_v1.yaml` 加载失败 → **import-time 抛异常**（这是 packaging bug 不是 user 输入问题）

## §6 photo3d-jury CLI 扩接口（B-2）

### 现有 batch 模式（不破）
入口：`tools/photo3d_jury.py:main(argv)`，argparse-based。现有 flags 见 `_build_parser()`：`--subsystem` / `--config` / `--profile-id` / `--list-profiles` / `--last-status` / `--budget` / `--confirm-cost` / `--dry-run` / `--max-retries` / `--debug-output` / `--force` / `--project-root`。

```
python -m tools.photo3d_jury --subsystem lifting_platform [其他 flags]
# 评所有视角；输出 PHOTO3D_JURY_REPORT.json 到 render dir
```

### 新增两个 flag（M-3 batch / M-10 失败语义 / N-3 隐藏 help / N-8 LLM key）

```
python -m tools.photo3d_jury --subsystem <name> --single-view V1 --image <path1> [<path2> ...]
# --single-view <V>:    只评指定视角；
# --image PATH [PATH ...]: 待评图片路径，nargs='+' 支持 batch（M-3：SP3 多 sample 时一次评 N 张，
#                          SP1 闭环传单张时 list 长度 = 1，行为不变）。
# 输出 stdout 一段 JSON（list[ViewVerdict]，每张图一项），不写盘。
```

#### 输出 JSON 结构（一张图为列表的一个元素）

```json
[
  {
    "view": "V1",
    "image_path": "V1_enhanced_baseline.jpg",
    "verdict": "preview",
    "photoreal_score": 58,
    "semantic_checks": {
      "geometry_preserved": true,
      "material_consistent": true,
      "photorealistic": false,
      "no_extra_parts": true,
      "no_missing_parts": true
    },
    "reason": "plastic look, flat lighting",
    "parse_status": "ok",
    "parse_anomalies": []
  }
  // 多张时此处会有多个 dict
]
```

#### CLI 失败语义契约（M-10 + SEC-MINOR-4）
- 成功：`exit code = 0`，stdout 必须是合法 JSON list；stderr 仅写人类可读 log（不影响调用方解析）
- 失败：`exit code != 0`，stderr 含错误信息；stdout **不**保证有合法 JSON（可能为空或 partial）
- 调用方（orchestrator）对**任一**情况走 `loop_status = jury_unavailable`：
  - `subprocess` 返非 0 exit code
  - stdout 不是合法 JSON（`json.JSONDecodeError`）
  - stdout JSON 非 list 或 list 长度 != len(--image)
  - 任一元素的 `verdict` 是 "needs_review"（按 jury v2 spec 表示 LLM 解析失败）
  - **stdout 字节超过 1 MiB**（SEC-MINOR-4 防 OOM）：orchestrator 必须用 `subprocess.Popen` + 手动 `read(MAX_STDOUT_BYTES)` 循环代替 `subprocess.run(capture_output=True)`，超出立即 kill 子进程并走 `jury_unavailable`

#### 实现细节
- 在 `_build_parser` 加 `--single-view` 和 `--image` 两 flag
- 两个 flag 都用 `argparse.SUPPRESS` 隐藏 help 输出（**N-3**：外行用户不会误用）；保留功能但 help 里不展示
- `main()` 检测到 `--single-view` 时跳过 batch 全视角循环 + 跳过 PHOTO3D_JURY_REPORT.json 写盘；遍历 `--image` 列表，每张图跑一次 LLM 调用 + verdict 解析；最后把 list[dict] 序列化打到 stdout
- `--image` 在 `--single-view` 模式下必填（argparse `required` 配合自定义 validator）
- LLM 调用复用 `tools/jury/llm_client.py` 的现有 client（**N-8 jury LLM key 来源**：与 batch 模式同 key 来源，从 jury config profile 读，不需要用户额外配 key；与 enhance backend 的 FAL_KEY 是**两个不同账户**，wizard 与文档需明示这点）

#### 与 batch 模式 budget 解耦
`--single-view` 模式不参与 batch 模式的 `--budget` / `--max-retries` 统计（batch 累计是 photo3d_jury 自己的预算守门）；闭环 cost 由调用方 (orchestrator) 通过 `LoopBudget` 累计到 `loop_summary.extra_cost_usd`。两套 budget 在 SP1 不互通；如果有需要后续 SP 可统一。

### `cad-spec-gen enhance` 入口 CLI 加 `--rerun-loop` flag（OPS-MAJOR-3）

cmd_enhance 加 `--rerun-loop` 命令行 flag（默认 false），语义：
- false（默认，幂等模式）：检测到视角对应的 sidecar `<view>_enhance_meta.json` 已存在且 `loop_status` ∈ {`delivered_baseline`, `delivered_retry`} → **跳过该视角的 enhance + 闭环**，直接复用既有产物（fast path，避免重复花钱）
- true（强制重跑）：忽略既有 sidecar，所有视角全部重新跑 baseline + 闭环；旧 sidecar 被覆盖

用户场景：
- 修改 rule yaml 后想重刷 5 视角 → `cad-spec-gen enhance --rerun-loop`
- 普通跑 = 默认幂等，重复执行不烧钱

幂等性约束：sidecar `loop_status ∈ {jury_unavailable, retry_failed, retry_rate_limited, ...}` 这类**临时性失败**状态默认**仍然重试**（不进 fast path），相当于"上次失败这次再试"；持久性失败（`retry_auth_failed` / `retry_quota_exceeded`）默认进 fast path（避免无意义重试），用 `--rerun-loop` 才能重试。

输出 JSON 结构：
```json
{
  "view": "V1",
  "image_path": "V1_enhanced_baseline.jpg",
  "verdict": "preview",
  "photoreal_score": 58,
  "semantic_checks": { /* 5 boolean */ },
  "reason": "plastic look, flat lighting",
  "parse_status": "ok",
  "parse_anomalies": []
}
```

实现：在现有 `photo3d_jury` CLI 入口加 argparse 分支；调用 jury LLM 时只传单视角 image，其余 batch logic 跳过。

## §7 顶层报告 `loop_summary` （D-3）

### ENHANCEMENT_REPORT.json 顶层加段（M-4 loop_type + M-7 headline 置顶）：

```json
{
  // ... 现有字段不变 ...
  "loop_summary": {
    "$schema_version": 1,
    "loop_type": "single_retry",
    /* loop_type ∈ {"single_retry", "multi_sample"}；SP1 始终 "single_retry"；
       SP3 多 sample 落地后会出 "multi_sample"。下游解析按 loop_type 分支字段。 */

    /* —— M-7 headline：用户最关心的三数字置顶 —— */
    "headline": {
      "improved_views": 1,
      "score_gain_total": 20,
      "extra_cost_cny": 1.30
    },
    "user_friendly_summary": "5 视角中：3 张 baseline 接受（已达标）/ 1 张闭环成功（提升 20 分）/ 1 张 AI 评分不可用回退 baseline。本次额外花费约 ¥1.30。",

    /* —— 详细统计字段（外行可不看） —— */
    "n_views": 5,
    "loop_eligible_views": 5,
    "delivered_baseline_count": 3,
    "delivered_retry_count": 1,
    "skipped_count": 1,
    "skipped_reasons": {"jury_unavailable": 1},
    "total_retries": 1,
    "extra_cost_usd": 0.18,
    "score_gain_avg": 4.0,
    "score_gain_total": 20

    /* score_gain_* 字段统计的是 delivered_score_delta（永非负，反映用户实际拿到的提升），
       不是 retry_score_delta（可负，retry 实际效果）。
       后者保留在视角级 sidecar 里供数据分析用。 */
  }
}
```

**字段顺序约束**：JSON 字段在序列化时按上述顺序写出（用 dict / OrderedDict 保序）。`headline` + `user_friendly_summary` 紧随 `$schema_version` / `loop_type` 之后，确保用户打开文件第一屏就能看到三数字 + 中文摘要；详细统计后置。

**人民币换算（M-8）**：`extra_cost_cny = round(extra_cost_usd * 7.2, 2)`（汇率常量在 `enhance_budget.py` 模块顶部，写明"近似换算，参考用，实际以服务商账单为准"）。汇率漂移随时调整不视为 schema 变更。

**回滚兼容性（OPS-MAJOR-2）**：当 `enhance.jury_loop.enabled == false` 时，**整段 `loop_summary` 完全省略不写入** ENHANCEMENT_REPORT.json（不是写空对象 / 不是写 `loop_summary: null`）。rationale：用户从 SP1 回退到 SP0 (v2.31.x) 二进制时，老版解析器 (autopilot / 用户脚本) 没有"容忍未知字段"契约（那是 SP1 引入的契约），多出 `loop_summary` 段会被当作 schema drift 报错。enabled=false 时不写该段，回滚路径 = "改 enabled=false 即可"，无需手动清理 ENHANCEMENT_REPORT。

L3 契约测试加 fixture：enabled=false 跑完 enhance 后 ENHANCEMENT_REPORT.json **不**应包含 `loop_summary` key（用 `assert "loop_summary" not in report`）。

### CLI / log 末尾摘要
跑完 enhance 后 log info 一行（D-5）：
```
Loop summary: 5 views, 3 baseline-accept, 1 retry-success (+20), 1 jury-skip; extra cost $0.18
```

## §8 测试策略

### 测试金字塔（数量级）

| 层级 | 数量 | 内容 |
|---|---|---|
| L1 单元（含 property） | 35-45 | reason_parser / rule_table / orchestrator 纯逻辑 + 2 hypothesis property |
| L2 集成（mock） | 8-12 | orchestrator + jury subprocess mock + enhance_image mock + retry 流程 |
| L3 契约 | 5-8 | yaml 加载 / 用户 override / sidecar metadata schema / `loop_summary` schema |
| L4 端到端 smoke | 3 | 真 fal API（marker `requires_fal_key`） |

### L1 单元（关键 case）

**reason_parser**
- 单 tag / 多 tag / 无 tag 命中
- 大小写不敏感
- 用户 tag_dictionary extend 追加，不替换内置
- 边界：空字符串 / 极长字符串 / 中文 reason（防御）
- **L1-prop-1** `@hypothesis.given(text=text(alphabet=string.ascii_letters+string.digits+" .,;-", max_size=80))` reason_parser 总返 `set[str]`，元素 ⊆ `BUILTIN_TAGS`，纯函数（同输入同输出）。**alphabet 必须限定**为 jury 实际可能输出的字符集（≤80 字英文字母+数字+标点）—— 否则默认 `text()` 会喂代理对/控制字符，把 reason_parser 测崩，但那不是真实使用场景，反而会被实施者用"宽容 catch all"绕过去掩盖真 bug

**rule_table**
- 单/多规则命中合并；prompt_addons 顺序保留 + 去重
- 无规则命中 → 返合规空（不抛异常）
- param_overrides per-backend 隔离（fal 段不漏 fal_comfy）
- schema_version 不匹配回退内置
- 用户 yaml 同 id 替换 / 新 id 追加 / tag_dict extend
- **L1-prop-2** `@hypothesis.given(tags=sets(sampled_from(BUILTIN_TAGS)))` lookup 返合规结构；空集 → 空合规结果不抛异常

**orchestrator**（纯逻辑部分用 stub 隔离 IO）
- score ≥ threshold → 直接返 baseline，不调 retry
- threshold 边界：score == threshold 视为接受
- cost cap 触发 → 接受 baseline
- v1_anchor 串行 vs 非 anchor 并行决策
- pick_max_jury：retry > baseline → 选 retry；retry < baseline → 选 baseline；retry == baseline → 选 baseline（决策保守优先 baseline）
- pick_max_jury：二轮 jury 失败 → 选 baseline

### L2 集成
- jury subprocess mock 返合法 JSON → 全流程
- jury 不可用 → loop_skipped, loop_status=jury_unavailable
- LLM fallback mock → addons 注入流程
- retry mock fal_comfy → 文件写出 + sidecar metadata
- enhance_image 用 monkeypatch（不起本地 ComfyUI / 不调真 fal）
- **视角异常隔离（DRIFT-MAJOR-7）**：orchestrator raise 任意 Exception 时其他视角不受影响 + sidecar 写降级形态（`retry_failed` + `errors[]` 含 scrub_secrets 后的 traceback）
- **跨平台 rename（DRIFT-MAJOR-2）**：dst 已存在的 fixture 验证 Path.replace 行为正确（不抛 FileExistsError）
- **顶层/advanced 同名（DRIFT-MAJOR-4）**：fixture 同时写顶层与 advanced 中的 enabled，验证 schema 校验阶段 hard fail
- **stdout cap（SEC-MINOR-4）**：subprocess 模拟返回 > 1 MiB stdout，验证 orchestrator kill 子进程 + 走 jury_unavailable
- **secrets scrub（SEC-MINOR-2）**：errors message 含 FAL_KEY=xxx 时，sidecar 写出后字符串经 `assert "FAL_KEY" not in sidecar_text and "[REDACTED]" in sidecar_text`
- **路径净化（SEC-MAJOR-2）**：manifest 含 `view: "../../etc/passwd"` 触发 ValueError 拒绝写入，不写 sidecar 到非法位置
- **rule_table_path 范围（SEC-MAJOR-1）**：用户 yaml 指向 project_root 外路径触发 hard fail
- **rerun-loop fast path（OPS-MAJOR-3）**：sidecar 已存在 + loop_status=delivered_retry 时默认 skip；--rerun-loop=true 时强制重跑

### L3 契约
- 内置 photoreal_v1.yaml 加载 schema 自检
- 用户 yaml + 内置 yaml merge 顺序契约（fixtures 6+ 个 case）
- sidecar metadata.json 字段集 JSON Schema 锁
- ENHANCEMENT_REPORT.json `loop_summary` 段 JSON Schema 锁

### L4 端到端（marker `@pytest.mark.requires_fal_key + @pytest.mark.slow`）
- **L4-1 提分检验**：真 fal_comfy 跑 1 张已知低分 baseline → 触发 retry → 验证最终 score 提升 > 5（10 次取均值，统计意义）
- **L4-2 防误触发** ✓ Q16 加固：跑一张 baseline 已 score ≥ threshold 的图（fixture），断言 `loop_triggered=False, loop_status=above_threshold`
- **L4-3 anchor 串行**：v1_anchor 模式跑 V1+V2，断言 V2 用的是 V1 final（retry 后）作 anchor

CI 默认 skip L4；本地 `pytest --run-slow` 触发。

### 依赖注入 / mock 策略
- jury subprocess：`monkeypatch subprocess.run` 注入预设 stdout JSON
- enhance_image：`monkeypatch importlib.import_module("fal_comfy_enhancer").enhance_image` 注入 lambda 写假图
- LLM client：`monkeypatch tools.jury.llm_client.LlmClient.call` 注入预设 LlmResponse

## §9 风险与权衡

| 风险 | 应对 |
|---|---|
| 规则表覆盖度不够 → photoreal_score 提升不显著 | LLM fallback 兜底；后续 SP1.5 迭代追加规则；L4-1 测验提供反馈 |
| LLM fallback 调用费 + 不稳定 | 默认开启但可用 `llm_fallback=false` 关；规则表命中即跳 LLM |
| retry 后反而降分 | 二轮 jury 选高分（C-3）；选张保守优先 baseline |
| cost 失控 | 预算 cap，默认 `n_views×0.25`；超额接受 baseline + 提示用户调高 |
| v1_anchor 串行降低吞吐 | 视角串行是现有 reference_mode=v1_anchor 的固有约束，闭环没引入新瓶颈；reference_mode=none 时并行不变 |
| jury LLM 评分主观 | 二轮 jury 用同一 model 同一 prompt template，相对值仍可信；绝对值用户可调 threshold |
| 通用 backend 不支持 ControlNet 几何锁，retry 改几何 | 1. retry 选张靠 jury 二轮 `geometry_preserved` 5 boolean 兜底（改几何会被打 false 导致 score 降，pick_max_jury 选 baseline）；2. fal_comfy 内置选项保留作"高质量几何锁路径"；3. spec §1 北极星表"结果准确"已澄清：通用 backend 靠 jury 兜底而非硬锁 |
| 用户接入未测试过的 vendor 出错 | BackendAdapter Protocol 强制定义异常分类（auth/rate_limit/quota/call）；adapter 未抛分类异常时 fall through 到 BackendCallError → retry_failed；写 sidecar.errors[] 帮用户复盘 |
| 通用 backend 可能漏报 actual_cost_usd 导致 budget 估算偏差 | adapter 返 None 时 budget 用 estimate；sidecar.warnings 写 `cost_estimated_only` 让用户知情；vendor 实测后调 estimate 常量 |

## §10 不在 SP1 scope（移交后续子项目）

| 子项目 | 不做的内容 | 理由 |
|---|---|---|
| SP1.5 | 第三方 BackendAdapter plugin 注入机制 | SP1 已锁 BackendAdapter Protocol + BACKEND_REGISTRY 形态契约；plugin 注入 (entrypoint discovery / 动态 import 用户 adapter) 由 SP1.5 单独 spec |
| SP2 | reference 图库 / IP-Adapter / Flux Kontext 接入 | 需先 SP1 提供质量度量基线；rule yaml schema 演进按 BL-1 约定（v1 yaml 永远可加载） |
| SP3 | 多 sample 并行 + jury 选最高 | 不抢 SP1 retry-once 决议；SP3 应**复用** `rule_table.lookup()` 接口（`enhance_budget.LoopBudget`、`score_select.ScoreSelectStrategy`、`photo3d-jury --image nargs='+' batch` 三处 SP1 已预留 SP3 兼容点） |
| SP4 | wizard 引导选 backend / 配 key / 跑试验图 | 装即用 gate 闭合，需 SP1-3 都稳；wizard 可基于 BACKEND_REGISTRY 动态列出可选 backend_kind |
| SP5 | LoRA 微调 | 需 SP3 累积训练数据 |

### N-7 photo3d_autopilot 集成影响评估

photo3d_autopilot 现有逻辑（`tools/photo3d_autopilot.py`）输出 `enhancement_status` 状态机（`accepted` / `preview` / `blocked` / `not_run` / `enhancement_blocked` / `enhancement_preview` / `enhancement_accepted`），输入读 ENHANCEMENT_REPORT.json。SP1 落地后影响：

| autopilot 行为 | SP1 落地是否影响 | 处理 |
|---|---|---|
| 读 ENHANCEMENT_REPORT.json 顶层既有字段 | 不影响（additive-only，§4.4 约束） | 不改 autopilot |
| `enhancement_status` 状态机决策逻辑 | 不影响（autopilot 不读 sidecar 也不读 loop_summary） | 不改 autopilot |
| 用户报告 / "下一步" 推荐文案 | **建议**显示 loop_summary.headline 让用户看到提分数据 | SP1 内**可选**追加：autopilot 在 "enhancement_accepted" 路径输出文案前先读 loop_summary.headline 拼到推荐报告里。如果 SP1 时间紧，可以推迟到 SP4 wizard 工作时一起做（登记 §11 follow-up） |
| budget / cost 跨 SP 协调 | 不影响（LoopBudget 跨 SP 共享但 autopilot 不参与 budget） | 不改 |

**SP1 决议**：autopilot 读 loop_summary 的可选文案集成**推迟**到 SP4 wizard，本 spec 仅写入 §11 follow-up；**autopilot 状态机本身保持透明**（即 SP1 对 autopilot 是只追加不修改的扩展）。

## §11 后续 follow-up（spec 内不办）

### 推迟到 v2 / SP1.5
- 用户 yaml `_disabled: true` 关闭某条 rule（v1 不实现）
- per-backend 不同 threshold（v1 单 threshold 全局；某些 backend 可能本身分数偏低，v2 可分）
- 跨视角学习：V1 改善的 prompt 是否能直接用到 V2-V5 baseline（v2 探索）
- 三轮 retry：实证 max_retries=2 收益是否值得（v2 + cost 数据驱动）
- 用户 in-loop：jury 打分后弹 UI 让用户自选"接受 / 重试 / 切 backend"（v2，违反 SP1 自动定位）

### 推迟到 SP4 wizard（用户友好性）
- **N-2** 终端 log warn vs info 区分外行无感 → SP4 wizard 安装时统一为"X 视角未优化"风格的中文聚合 log
- **N-5** llm_fallback 默认开但需在 wizard 提示用户"AI 兜底翻译会产生 token 费"（spec §4.1 _doc 已写但 wizard 引导更直观）
- **N-7 后半** photo3d_autopilot 推荐报告读 loop_summary.headline 拼接（SP1 透明扩展，SP4 集成）

### 推迟到数据驱动决策
- **N-10** rule_table yaml 加载 cache：SP1 实现按"每次视角调用都重新加载"以保正确性；性能瓶颈实测后再加 module-level cache
- **N-12** L4-1 deterministic：SP1 跑 10 次取均值的 smoke 是人工质量回归，不进 CI；后续若有 ground-truth 数据集则升 deterministic
- **N-13** tag_dictionary vs rule 同 key 的"追加 vs 替换"不对称：spec §4.3 已加注释解释，是否升级为对称设计在大量用户反馈后再决
- **N-14** rule_table 部分命中 + LLM fallback 失败的边界：spec §4.6 enum 表已加注释（部分命中时 LLM 失败不阻断 retry，落 warnings[]），仍可能在实施时发现细节遗漏

### 实施期可能浮现
- 某规则触发后 prompt 长度爆炸（拼太长 token 超限）→ 实施 fallback 截断策略
- LLM fallback 返回有害词（注入 prompt 攻击）→ SP1 已对 jury reason 做 sanitize（§3 [4]），但 LLM fallback 返回值进 prompt 前**也**应 sanitize（实施期补强；spec §3 [5] 应在 SP1 实施时直接补这一步）

### 推迟到 SP4 / 后续 release
- **OPS-MINOR-7** 跨次运行规则命中率 / 提分分布聚合（dashboard / SQLite/CSV 落库），SP1.5 / SP4 wizard 收尾时做
- **OPS-MINOR-8** sidecar 与 ENHANCEMENT_REPORT 导出诊断包时自动 redact `C:\\Users\\<姓名>\\...` / SW 项目元数据中的作者名（在 SEC-MINOR-2 secrets_scrubber 之上扩 user_redactor 模块；SP1 仅做 secrets，OPS-MINOR-8 加 PII redact 在后续）
- **DRIFT-MINOR-8** L4-1 fixture 用 git LFS 提交固定 PNG（path: `tests/fixtures/jury_loop/known_low_score_v1.jpg`） + commit `expected_baseline_verdict.json` 锁基线 score；SP1 实施时如果有现成低分图可临时本地 fixture，正式入 git LFS 推迟 SP4
- **DRIFT-MINOR-13 (UX N-13)** tag_dictionary vs rule 同 key 的"追加 vs 替换"不对称设计：spec §4.3 已加注释解释，是否升级为对称设计在大量用户反馈后再决
