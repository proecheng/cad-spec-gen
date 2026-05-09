# SP1：Jury → Prompt 反馈闭环设计稿

- **日期**：2026-05-10
- **作者**：proecheng + Claude Opus 4.7
- **状态**：brainstorm 完成，待用户审 → writing-plans
- **前置**：v2.31.1（PR #66）已发布；jury v2 (`tools/jury/`) 已落地；enhance 4 backend (`gemini` / `comfyui` / `fal` / `fal_comfy` / `engineering`) 已通
- **后续子项目**：SP2（Reference 图库 + IP-Adapter）、SP3（多 sample A/B 选优）、SP4（wizard 引导选型）、SP5（LoRA 微调，可选）

## §1 项目目标与北极星 gate

### 目标
现有 enhance 输出 jury 评分中 5 boolean 通常能过，但 `photoreal_score` 卡在 40-60 区间，质感是"CAD 渲染调"而非"产品手册/电商详情页调"。SP1 的目标是建立 **jury → prompt 反馈闭环**：

- 跑完 baseline enhance → jury 评分 → score 低于阈值时**自动**用 jury 反馈调整 prompt + ControlNet/denoise 参数 → retry 一次 → 二轮 jury 选 score 更高的那张交付
- **预期收益**：单视角 photoreal_score +20-30 分，5 视角平均 60→80
- **不在 SP1 scope**：reference 图库（SP2）、多 sample 并行选优（SP3）、wizard 选型 UI（SP4）、LoRA 训练（SP5）

### 北极星 5 gate 自检

| Gate | SP1 兑现方式 |
|---|---|
| 零配置 | `enhance.jury_loop.enabled=true` 默认开启；threshold/cost_cap 有 sane defaults |
| 稳定可靠 | 任何失败路径回退 baseline，**永不阻塞交付**（§5） |
| 结果准确 | retry 走 fal_comfy ControlNet hard lock，不改几何；二轮 jury 选高分 |
| SW 装即用 | 闭环只跑 cloud backend (`fal` / `fal_comfy`)，与 SolidWorks 解耦 |
| 傻瓜式 | 用户感知 = "score 低自动重试一次更好的"；中文 summary 写进顶层报告 |

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
├── rule_table.py          # tags + backend → (prompt_addons, param_overrides) （纯函数 + YAML 加载）
├── llm_fallback.py        # 规则表 miss 的 tags → addons（复用 jury llm_client，不同 prompt template）
├── orchestrator.py        # 视角级 hook：调度 baseline → jury → retry 决策 → 二轮 jury → 选张
├── metadata.py            # sidecar metadata.json 的 schema + 写出
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
- **rule_table**：纯函数 + YAML 加载，输入 `(tags: set[str], backend: Literal["fal","fal_comfy"])`，输出 `(prompt_addons: list[str], param_overrides: dict[str, Any])`
- **llm_fallback**：当 rule_table miss 部分 tags 时调用，输入 `unmapped_reason: str`，输出 `prompt_addons: list[str]`（不产 param_overrides）
- **orchestrator**：唯一持副作用模块，单视角 hook，调上述 3 个 + jury subprocess + 二次 enhance + 选张
- **metadata**：sidecar `<view>_enhance_meta.json` 的 schema 守门 + 写出
- **rules/photoreal_v1.yaml**：内置规则表，schema_version=1，~15-20 tag 起步

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
[2] orchestrator.run_loop_if_eligible(view=V<i>, backend, rc, baseline_path, ...)
       │ Gate-1: backend ∉ {"fal", "fal_comfy"}
       │     → 重命名 baseline 为最终交付名 V<i>_enhanced.jpg；return
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
[4] tags = reason_parser(verdict.reason)
       │ Gate-6: tags == ∅
       │     → loop_status: no_tags_parsed；接受 baseline
       │
       ▼
[5] hits = rule_table.lookup(tags, backend)
       │ misses = tags - hits.matched_tags
       │ if misses 且 enhance.jury_loop.llm_fallback==true:
       │     extra_addons = llm_fallback.translate(misses, verdict.reason)
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

- **跨视角 cost 累计**：cmd_enhance 在视角循环开始前实例化一个 `LoopBudget(cost_cap_usd, n_views)` 对象（位于 `tools/jury_loop/orchestrator.py` 内或独立 `budget.py`，单视角 hook 接收并 mutate）。每次进入 `run_loop_if_eligible` 传入该对象；orchestrator 在 [3] Gate-5 检查 `budget.spent + estimate(retry_cost) > budget.cap` → 接受 baseline；retry 跑通后 `budget.spent += actual_cost`。budget 对象同时累计 `extra_cost_usd` 写入最终 `loop_summary`。
- **v1_anchor 路径传递**：现有 `cmd_enhance` 已有 `reference_mode=v1_anchor` 处理逻辑（在 enhance_image 调用处用 V1 enhanced 路径）。SP1 闭环不改 anchor 决议机制——只确保 V1 闭环跑完后，V1 final 路径写入 manifest/rc 后，cmd_enhance 进入 V2 时拿到的是更新后的 V1 final 路径。orchestrator 不直接持 anchor，由 cmd_enhance 读盘后传给 enhance_image。
- **视角串行约束**：reference_mode=v1_anchor 时 cmd_enhance 视角循环必须串行（V1 hook 完才进 V2）；reference_mode=none 时可保留现有并行实现。

## §4 配置 schema

### 4.1 `pipeline_config.json` 新增段

```jsonc
{
  "enhance": {
    "backend": "fal_comfy",
    // ... 既有 fal/fal_comfy/comfyui/gemini/engineering 段不变 ...
    "jury_loop": {
      "_doc": "Jury → prompt 反馈闭环。仅 fal/fal_comfy backend 有效，其他 backend NO-OP。",
      "enabled": true,
      "threshold": 75,
      "_threshold_doc": "photoreal_score < threshold 才触发 retry。独立于 jury 顶层 min_photoreal_score（默认 60，决定 jury status accepted/preview）。65=低槛 / 75=默认 / 85=严苛。",
      "max_retries": 1,
      "cost_cap_usd": null,
      "_cost_cap_doc": "null = 自动按 n_views×0.25 USD；显式数值则锁死该值。每次 retry 前累计估算超过即接受 baseline。",
      "llm_fallback": true,
      "_llm_fallback_doc": "rule_table 未命中的 tags 是否找 LLM 翻译；关闭则未命中即放弃 retry。",
      "rule_table_path": null,
      "_rule_table_path_doc": "null = 用内置 photoreal_v1.yaml；显式路径则在内置之上 merge 用户 yaml。",
      "score_select_strategy": "pick_max_jury",
      "_strategy_doc": "二轮如何选张：pick_max_jury（二轮 jury 选高分，C-3 决议）/ force_retry（不二轮强制 retry，cost-1 jury 但有降分风险）。"
    }
  }
}
```

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
      fal:        { canny_strength: 0.65, depth_strength: 0.6, guidance_scale: 4.0 }
      fal_comfy:  { denoise_strength: 0.45, cfg_scale: 7.5 }

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
      fal:        { canny_strength: 0.85, canny_end_pct: 0.95 }
      fal_comfy:  { canny_strength: 0.95 }

  - id: dull_color_to_vibrant
    when_tags: [dull_color, washed_out]
    prompt_addons:
      - "vivid saturated product colors, professional color grading"
    param_overrides: {}

  - id: dark_to_brighter
    when_tags: [dark_overall]
    prompt_addons: ["bright key light, high-key product photography"]
    param_overrides:
      fal_comfy:  { denoise_strength: 0.4 }

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
- 用户 `enhance.jury_loop.rule_table_path` 指向的 yaml schema_version 必须 == 1，否则 warn + 仅用内置（C-1）
- 合并语义：
  - `rules`：同 id → 用户替换内置；新 id → 追加；不允许删除内置 rule（用户想关闭某条 rule 应在 yaml 里 `rules: [{id: foo, _disabled: true}]`，spec v1 不实现 disabled，留 v2）
  - `tag_dictionary`：同 tag key → 用户 patterns 追加（不替换）；新 tag key → 追加

### 4.4 sidecar metadata schema (A-3)

文件：`<render_dir>/<view>_enhance_meta.json`，永远写。

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
    "reason": "improved metallic finish"
  },
  "tags_parsed": ["plastic_look", "flat_light"],
  "rules_hit": ["plastic_look_to_metallic", "flat_lighting_to_studio"],
  "rules_missed_tags": [],
  "llm_fallback_used": false,
  "prompt_addons_applied": ["matte metallic finish, anodized aluminum", "studio softbox lighting from left, fill light from right"],
  "param_overrides_applied": {"fal_comfy": {"denoise_strength": 0.45, "cfg_scale": 7.5}},
  "user_friendly_summary": "已自动重试 1 次，画面质感分数从 58 提升到 78（提升 20）。",  // D-1 中文
  "score_delta": 20,                         // int，0 当无 retry；负值表示 retry 后降分被舍弃
  "extra_cost_usd": 0.18,                    // float，retry+二轮 jury 累计估算
  "warnings": [],                            // list[str]，e.g. "unknown_param: fal_comfy.bogus_param"
  "errors": []                               // list[str]，retry/jury 失败堆栈摘要
}
```

#### sidecar 在特殊状态下的形态约定
- `loop_status == "loop_disabled"`：`loop_eligible=false` / `delivered_kind="baseline"` / `baseline.image_path` 是最终交付名（无 `_baseline` 后缀，因为没有备份文件）/ `retry=null` / `tags_parsed=[]` / `prompt_addons_applied=[]` / `extra_cost_usd=0` / `user_friendly_summary="该 backend 不支持闭环优化"`
- `loop_status == "above_threshold"`：`delivered_kind="baseline"` / `baseline` 含完整 jury verdict / `retry=null` / `user_friendly_summary` 形如 "首轮分数 78 已达标，无需重试"
- `loop_status == "delivered_retry"`：`delivered_kind="retry"` / `baseline` 与 `retry` 字段都有完整 verdict / `score_delta = retry.photoreal_score - baseline.photoreal_score`（必为正）
- 其他 `delivered_baseline` 系列状态：`delivered_kind="baseline"` / `retry` 视乎是否跑通可能为 null 或带值（带值时 `score_delta` 可能为 0 或负，表示 retry 跑通但选 baseline）

字段保持可序列化稳定结构——下游解析 JSON Schema 锁字段集；缺省值统一用 `null`/`[]`/`0` 而非省略。

### 4.5 `score_select_strategy` 语义（C-3 决议下展开）

| 取值 | 流程 | 适用 |
|---|---|---|
| `pick_max_jury`（**默认**） | retry 跑完后**再**调 jury 一次（§3 [8]）；比较 baseline / retry 的 `photoreal_score`；选高分张。retry 平/降分时选 baseline（保守）；二轮 jury 失败时选 baseline。 | 推荐：付一次额外 jury 调用换"不会降分"安全网 |
| `force_retry` | retry 跑完后**不**再调 jury（§3 [8] 跳过）；强制选 retry 张。仅当 retry 本身失败（HTTP/timeout）才回退 baseline。 | cost 极敏感场景；接受"偶发降分"风险 |

二选一在 `pipeline_config.json` 的 `enhance.jury_loop.score_select_strategy` 设置。MEDIUM 起步默认即可，只在用户实测大量数据后才考虑切 force_retry。

### 4.6 `loop_status` enum (A-4)

```
delivered_baseline      // 接受 baseline 交付（多种原因之一）
delivered_retry         // retry 跑通且选中
loop_disabled           // jury_loop.enabled=false 或 backend 不在 fal/fal_comfy
above_threshold         // baseline score ≥ threshold，无需 retry
cost_capped             // 累计成本超 cap
no_tags_parsed          // jury reason 里没有任何已知 tag 关键词
no_rules_hit_no_llm     // rule_table 全 miss 且 llm_fallback 关闭
jury_unavailable        // jury subprocess 失败/网络
empty_reason            // jury 返回但 reason 字段空
llm_fallback_failed     // 规则表全 miss + LLM 调用失败
retry_failed            // retry enhance 调用失败
```

固化含义：以 `delivered_` 前缀的两个是终态成功；其余皆"接受 baseline" 的具体原因细分。

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
| 5.1 backend 不在 fal/fal_comfy | `loop_disabled` | （无 warning） |
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

### 新增两个 flag

```
python -m tools.photo3d_jury --subsystem <name> --single-view V1 --image <path>
# --single-view <V>: 只评指定视角；
# --image <path>:    覆盖该视角默认从 manifest 取的图片路径（必填于 --single-view 模式）；
# 输出 stdout 一段 JSON（与 PHOTO3D_JURY_REPORT.json 中该视角子结构同 schema），不写盘。
```

输出 JSON 结构（与 ViewVerdict 一一对应）：
```json
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
```

实现：在 `_build_parser` 加 `--single-view` `--image` 两 flag；`main()` 检测到 `--single-view` 时跳过 batch 全视角循环 + 跳过 PHOTO3D_JURY_REPORT.json 写盘；只跑该视角的 LLM 调用 + verdict 解析；将单视角 dict 序列化打到 stdout。`--image` 在 `--single-view` 模式下必填，否则 argparse error。

约束：`--single-view` 模式不参与 `--budget` / `--max-retries` 的 batch 累计统计（只跑一次 LLM 调用，cost 由调用方累计到 enhance 闭环的 `loop_summary.extra_cost_usd`）。

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

### ENHANCEMENT_REPORT.json 顶层加段：
```json
{
  // ... 现有字段不变 ...
  "loop_summary": {
    "$schema_version": 1,
    "n_views": 5,
    "loop_eligible_views": 5,
    "delivered_baseline_count": 3,
    "delivered_retry_count": 1,
    "skipped_count": 1,
    "skipped_reasons": {"jury_unavailable": 1},
    "total_retries": 1,
    "extra_cost_usd": 0.18,
    "score_delta_avg": 4.0,
    "score_delta_total": 20,
    "user_friendly_summary": "5 视角中：3 张 baseline 接受（已达标）/ 1 张闭环成功（提升 20 分）/ 1 张 jury 不可用回退 baseline。"
  }
}
```

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
- **L1-prop-1** `@hypothesis.given(text=text())` reason_parser 总返 `set[str]`，元素 ⊆ `BUILTIN_TAGS`，纯函数（同输入同输出）

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

## §10 不在 SP1 scope（移交后续子项目）

| 子项目 | 不做的内容 | 理由 |
|---|---|---|
| SP2 | reference 图库 / IP-Adapter / Flux Kontext 接入 | 需先 SP1 提供质量度量基线 |
| SP3 | 多 sample 并行 + jury 选最高 | 不抢 SP1 retry-once 决议；SP1 落地后用 jury_loop 数据评估是否升 |
| SP4 | wizard 引导选 backend / 配 key / 跑试验图 | 装即用 gate 闭合，需 SP1-3 都稳 |
| SP5 | LoRA 微调 | 需 SP3 累积训练数据 |

## §11 后续 follow-up（spec 内不办）

- 用户 yaml `_disabled: true` 关闭某条 rule（v1 不实现，v2 加）
- per-backend 不同 threshold（v1 单 threshold 全局；某些 backend 可能本身分数偏低，v2 可分）
- 跨视角学习：V1 改善的 prompt 是否能直接用到 V2-V5 baseline（v2 探索）
- 三轮 retry：实证 max_retries=2 收益是否值得（v2 + cost 数据驱动）
- 用户 in-loop：jury 打分后弹 UI 让用户自选"接受 / 重试 / 切 backend"（v2，违反 SP1 自动定位）
