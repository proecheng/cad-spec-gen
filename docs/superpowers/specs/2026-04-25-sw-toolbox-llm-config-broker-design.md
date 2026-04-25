# SW Toolbox 配置名 LLM-broker 设计 (rev 2)

**日期**：2026-04-25
**状态**：设计已确认（rev 2 修订完 14 项一致性/通用性/交互问题），待计划
**作者**：Claude Sonnet 4.6 + procheng
**关联**：session 31 后续 — 修复 Phase D 路径 B：`gen_std_parts.py` 让 ShowConfiguration2 取尺寸匹配的 SW Toolbox STEP

---

## 1. 背景与问题

### 1.1 现状

`cad_pipeline.py codegen` 会调 `gen_std_parts.py`，后者用 `parts_resolver.PartsResolver` 解析 BOM 标准件，匹配 `sw_toolbox_adapter.SwToolboxAdapter`（COM 适配器）后生成 `std_*.py`。`std_*.py` 在 build phase 加载 STEP 文件并装配进 GLB。

预热步骤 `sw-warmup`（B2）已为 SW Toolbox 里 330 个 SLDPRT 文件各导出 **1 个默认配置 STEP**，缓存到 `~/.cad-spec-gen/step_cache/sw_toolbox/<standard>/<subcategory>/<part>.step`。

### 1.2 缺陷

`sw_toolbox_adapter.resolve()` 当前对**含 `config_name_resolver` 标准化规则**的 BOM 行（仅 GB/T 紧固件）才会构造 `target_config`，触发 ShowConfiguration2 重新导出尺寸匹配的 STEP；其他类别（O 型圈、轴承、定位销等）`target_config = None` → 命中预热的默认配置 STEP（**尺寸通常错** —— 例如 BOM 要 Φ80×2.4，缓存里却是 Φ28×1.9）→ GLB 加载错尺寸的 SW 几何。

session 31 后用户跑 GISBOT 端到端，发现新生成的 GLB（6.7 MB）里 SW Toolbox 零件尺寸完全跑偏。当时为应急把 `std_*.py` 全替换成 canonical CadQuery 近似体（GLB 1.8 MB，尺寸正确但**完全没有 SW 几何**），用户反馈："新生成的 GLB 还不如改进前，没有看到 SW 模型库被使用"。

### 1.3 根因

1. 预热缓存 STEP 路径不带 config 后缀 → 任意 BOM 尺寸都"命中"默认配置 STEP
2. `_build_candidate_config` 只覆盖 `GB/T` 标准+尺寸格式（fastener），seal/bearing/locating 等格式不被识别
3. SW Toolbox 各 SLDPRT 内部的 configuration 命名规则**不可预知**（不同零件命名风格不同：`80×2.4` vs `GB1235-80x2.4` vs `M8 X 20`），无法靠正则枚举

### 1.4 用户目标

> "我想看到 SW 模型库的零件出现在 GLB 里，且尺寸正确"

需要一种机制：在 codegen 时主动列出 SLDPRT 真实可用的 configuration 列表，匹配 BOM 尺寸到正确 config，再调 ShowConfiguration2 + 导出 STEP。当含糊或匹配失败时，**与用户交互**而非静默选错或放弃 SW。

---

## 2. 设计原则与约束

继承 `project_north_star.md` 的 5 条北极星 + 本 spec 新增 2 条：

1. **零配置**：默认行为正确，不要求用户改 yaml
2. **稳定可靠**：失败模式清晰、可恢复
3. **结果准确**：宁可问用户也不静默错配
4. **SW 装即用**：SW + Toolbox 装好就能跑
5. **傻瓜式操作**：把"判断 SW config 名"这件需要专业知识的事，封装成"看几个候选选一个"的简单选择
6. **LLM-用户交互在 agent 层**，不在 pipeline 内嵌任何 LLM API 调用。pipeline 输出结构化的"待决策"数据，跑该 skill 的 LLM agent（Claude / Codex / Gemini Agent 等）读数据后向用户提问。这样 skill 与具体 LLM 解耦
7. **不静默绕过 SW**：当 SW 可用且 BOM 行匹配到 SW Toolbox SLDPRT 时，broker **永远不能在没有用户显式同意的情况下回退到 CadQuery 近似体**。回退必须是用户的明确动作（决策文件里写 fallback_cadquery / 显式设 `CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery` 环境变量）。命令行用户也能看到清晰的 stdout 提示

---

## 3. 架构

### 3.1 模块新增

`adapters/solidworks/sw_config_broker.py`（新文件，~280 行）：把"如何为某 BOM 行匹配 SW Toolbox 配置名"这件事封装成**单一职责**模块。`sw_toolbox_adapter.resolve()` 委托给它，自身只管 SLDPRT 匹配 + STEP 导出编排。

`adapters/solidworks/sw_list_configs_worker.py`（新文件，~50 行）：独立 subprocess 用 SW COM 列出某 SLDPRT 的所有 configuration 名称，stdout 输出 JSON list。复用 `sw_convert_worker.py` 的 subprocess + timeout + 退出码契约模式。

### 3.2 数据流

```
gen_std_parts.py
    │
    │ for each BOM row in subsystem:
    ▼
parts_resolver.resolve_one(bom_row)
    │
    ▼
sw_toolbox_adapter.resolve(query, spec)
    │ 1. token 匹配找到 SLDPRT (现有逻辑不变)
    ▼
sw_config_broker.resolve_config_for_part(bom_row, sldprt_path, subsystem=...)
    │
    ├─[1] 必须先调 SW COM 列当前 available_configs (process-local cache 复用)
    │
    ├─[2] 读 .cad-spec-gen/spec_decisions.json[subsystem][part_no]
    │     ├─ 命中 + decision 仍有效 → 返回对应 ConfigResolution
    │     │   - decision="use_config" + config_name 仍在 available → source="cached_decision", config_name 用旧值
    │     │   - decision="fallback_cadquery" → source="cached_decision", config_name=None
    │     └─ 命中但 stale → 挪入 decisions_history + 走 [3]
    │
    ├─[3] _match_config_by_rule (BOM dim → available)
    │     └─ confidence ≥ 0.7 命中 → 返回 source="auto"
    │
    └─[4] 含糊匹配（未命中或多解）：
          ├─ os.environ["CAD_AMBIGUOUS_CONFIG_POLICY"] == "fallback_cadquery"
          │  → 返回 source="policy_fallback", config_name=None（用户已显式同意）
          │  + 仍然写 pending（事后审阅）
          │
          └─ 默认 (policy="halt")：抛 NeedsUserDecision(pending_record_dict)
             ⚠️ broker 自身不写 pending 文件 — 仅在异常里携带 record

回到 gen_std_parts.py：
    │
    ├─ 捕获 NeedsUserDecision → 累积 record 到 list
    │
    └─ 全部 BOM 跑完后：
        ├─ 累积 list 非空 →
        │   1. 原子写 .cad-spec-gen/sw_config_pending.json (含全部 records)
        │   2. stdout 打印人读摘要（即使没 agent 也能看懂下一步）
        │   3. exit 7
        │
        └─ 累积 list 空 → 正常生成 std_*.py + exit 0
```

### 3.3 Agent 介入点（不在 pipeline 内）

pipeline `exit 7` → agent 读 `<project>/.cad-spec-gen/sw_config_pending.json` → **逐零件问用户** → 写 `<project>/.cad-spec-gen/spec_decisions.json` → 删除 pending → 重跑 codegen。

这一段属于 skill 文档的运行时约定，由 `.claude/commands/cad-codegen.md` 描述（agent 看 skill 文档知道该这么做）。

**非 agent 用户路径（命令行直接跑）：** pipeline stdout 的人读摘要必须自包含足够信息让用户手工编辑 pending → 决策。stdout 摘要示例：

```
⚠️ codegen 暂停：3 个零件需要确认 SW Toolbox 配置（subsystem=end_effector）

零件 1/3 — GIS-EE-001-03 (O型圈 Φ80×2.4)
  SW 候选配置：["28×1.9", "35×2.0", "80×2.4", "100×3.0"]
  建议：选 "80×2.4"（字面完全匹配 BOM）
  其他选项：fallback_cadquery（用 CadQuery 近似，尺寸正确但无 SW 几何）

零件 2/3 — ...
零件 3/3 — ...

请二选一处理：
  [推荐] 用 /cad-codegen skill —— agent 会逐零件向你提问，自动写决策回 spec_decisions.json
  [手动] 按 §5.1 schema 编辑 D:/.../GISBOT/.cad-spec-gen/spec_decisions.json
         在 decisions_by_subsystem.end_effector 下添加每个 part_no 的决策项，
         删除 sw_config_pending.json，再跑 cad_pipeline.py codegen
```

### 3.4 边界

- broker 对外只暴露 `resolve_config_for_part(bom_row, sldprt_path, *, subsystem) -> ConfigResolution`
- broker **无持久 state**（决策状态全在 `spec_decisions.json` 文件里）
- 唯一例外是 process-local 内存缓存：模块级 `_CONFIG_LIST_CACHE: dict[str, list[str]]` 用于 COM 调用 dedup（重启即清，仅生命周期 = 一次 codegen 进程）
- broker **不接受 project_root 参数** —— 从 `cad_paths.PROJECT_ROOT` 模块级常量直接读（与 cad_paths 单一同源，避免参数漂移）
- broker **不接受 policy 参数** —— 从 `os.environ["CAD_AMBIGUOUS_CONFIG_POLICY"]` 直接读（默认 "halt"），简化 API

---

## 4. 核心组件

### 4.1 数据类与异常

```python
@dataclass
class ConfigResolution:
    config_name: str | None        # None = fallback to CadQuery（用户/policy 显式同意）
    source: str                     # "cached_decision" | "auto" | "policy_fallback"
    confidence: float               # 见下表
    available_configs: list[str]   # COM 列出的当前候选（cache hit 路径也已 COM 校验）
    notes: str = ""                 # 失败/匹配解释

# confidence 取值表：
# source="cached_decision":  1.0 （用户已确认）
# source="auto" + L1 精确:    1.0 （字面完全匹配）
# source="auto" + L2 子串:    0.7 ~ 0.95 （依命中长度）
# source="policy_fallback":   0.0 （非匹配，env var 强制 fallback）


class NeedsUserDecision(Exception):
    """broker 在含糊匹配 + policy="halt" 时抛此异常；
    sw_toolbox_adapter 捕获后 return miss；
    gen_std_parts 累积所有抛出的 record 后一次性写 pending 文件。

    broker 自身不写 pending（rev 2 修订）—— 异常携带 record，避免进程崩溃时部分写入。"""

    def __init__(self, part_no: str, subsystem: str, pending_record: dict):
        self.part_no = part_no
        self.subsystem = subsystem
        self.pending_record = pending_record  # 完整的 sw_config_pending.json item 子结构
        super().__init__(f"User decision needed for {subsystem}/{part_no}")
```

### 4.2 公开 API

```python
def resolve_config_for_part(
    bom_row: dict,           # 含 part_no, name_cn, material 等
    sldprt_path: str,
    *,
    subsystem: str,          # 用于 spec_decisions.json 子键定位（必填，无默认）
) -> ConfigResolution:
    """主入口。

    流程：COM list → cache lookup → rule match → policy decision

    返回：ConfigResolution

    抛出：
    - NeedsUserDecision：含糊匹配且 policy=halt（默认）
    - decisions.json 损坏 → ValueError(含行号)（fail-loud，不静默重建）

    依赖（隐式读）：
    - cad_paths.PROJECT_ROOT
    - os.environ["CAD_AMBIGUOUS_CONFIG_POLICY"]（默认 "halt"）
    """
```

### 4.3 私有辅助

```python
def _build_bom_dim_signature(bom_row: dict) -> str:
    """组合 part_no/name_cn/material 等所有可能含尺寸的字段为稳定签名。
    例：{"part_no":"X","name_cn":"O型圈","material":"FKM Φ80×2.4"} → "O型圈|FKM Φ80×2.4"
    用于 cache invalidation 比对（bom_dim_signature_changed 触发）。"""

def _list_configs_via_com(sldprt_path: str) -> list[str]:
    """SW COM 列 SLDPRT 配置；内部封装 _CONFIG_LIST_CACHE 缓存按 sldprt 绝对路径 key。
    失败 → 返回 [] 并在 _CONFIG_LIST_CACHE 标记失败状态（避免重试）。
    其他模块只看公开 API，不直接读写 _CONFIG_LIST_CACHE。"""

def _load_decisions_envelope() -> dict:
    """从 cad_paths.PROJECT_ROOT/.cad-spec-gen/spec_decisions.json 读完整 envelope。
    文件不存在 → 返回空 envelope（含 schema_version=2 + 空 decisions_by_subsystem）。
    JSON syntax error → raise ValueError(f"decisions 文件第 {line} 行 syntax error: {detail}")"""

def _save_decisions_envelope(envelope: dict) -> None:
    """原子写入 spec_decisions.json（先写 .tmp 再 rename）。"""

def _get_decision_for_part(envelope: dict, subsystem: str, part_no: str) -> dict | None:
    """从 envelope["decisions_by_subsystem"][subsystem][part_no] 取，缺失返回 None。"""

def _validate_cached_decision(
    decision: dict,
    current_bom_signature: str,
    current_sldprt_filename: str,
    current_available_configs: list[str],
) -> tuple[bool, str | None]:
    """三项失效检查；返回 (is_valid, invalidation_reason)。
    is_valid=True 时 reason=None；False 时 reason ∈ {bom_dim_signature_changed,
    sldprt_filename_changed, config_name_not_in_available_configs}。"""

def _move_decision_to_history(envelope: dict, subsystem: str, part_no: str,
                              invalidation_reason: str) -> None:
    """把 envelope[decisions_by_subsystem][subsystem][part_no] 拷贝到 envelope[decisions_history]
    并删除原位。in-place 修改 envelope；调用方负责 _save_decisions_envelope。"""

def _match_config_by_rule(
    bom_dim_signature: str,
    available: list[str],
) -> tuple[str, float] | None:
    """两层匹配；返回 (matched_config, confidence) 或 None。"""

def _build_pending_record(
    bom_row: dict,
    sldprt_path: str,
    available: list[str],
    match_failure_reason: str,
    attempted_match: dict | None,
) -> dict:
    """构造单 item 的 sw_config_pending.json 子结构。
    schema 按 match_failure_reason 分支（详见 §5.3）。"""
```

### 4.4 关键决策

1. **`_list_configs_via_com` 走独立 subprocess** —— 复用 `sw_convert_worker.py` 模式，新建 `sw_list_configs_worker.py`，不污染现有 convert worker。退出码契约：0=成功（stdout JSON list）/ 4=COM 异常 / 64=参数错。timeout 初值 15s。

2. **`_match_config_by_rule` 两层匹配 + 置信度阈值**：
   - **L1 精确归一化（confidence=1.0）**：`bom_dim_signature` 提取尺寸 token → 与候选 config 字符串归一化后**等值比对**（统一 `×→x`、`Φ→""`、去 `[-_\s]`、lowercase）
   - **L2 包含子串（confidence=0.7~0.95）**：候选 config 字符串归一化后**包含**归一化尺寸 token；confidence = `min(0.95, 0.7 + len(sized_token)/100)`（命中越长越可信，避免短 token 假阳性）
   - 命中返回 `(matched_config, confidence_score)`；同一 confidence 多个候选时取**字符串最短**的（最少干扰），未命中 → None
   - **`AUTO_MATCH_THRESHOLD = 0.7`**：confidence ≥ 0.7 → 直接 source="auto" 不走 pending；< 0.7 或 None → 走 [4] 含糊路径

3. **缓存命中策略 = "调 COM 校验 + 跳过用户提问"**（rev 2 锁定）：
   - 即使 spec_decisions.json 已有该零件决策，broker 也**必须先调 COM 列当前 available_configs**
   - 用 `_validate_cached_decision` 三项检查（bom_dim_signature / sldprt_filename / config_name 仍在 available_configs）
   - 全过 → 直接返回 `ConfigResolution(source="cached_decision", config_name=decision.config_name, confidence=1.0)`
   - 任一失效 → 挪入 decisions_history + 走规则匹配 / 含糊处理
   - **不省 COM 调用** —— 决策缓存的价值在"跳过用户提问"，不在"跳过 COM"
   - GISBOT 5 个 SW 命中零件的 codegen 增量约 15-25s（COM 列配置，每零件 3-5s）

4. **fallback 永远是用户显式动作**（rev 2 新增）：
   - 默认 policy="halt"：含糊匹配 → exit 7，无静默 fallback
   - `CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery` 用户显式 opt-in → 含糊匹配自动用 CadQuery 近似 + 仍写 pending（事后审阅）
   - 没有第三种"系统智能猜测 fallback"的路径

5. **决策文件 `schema_version` 字段**：本 rev bump 到 2（因 subsystem 嵌套 schema 变更）；未来 bump 时旧文件触发提示而不是静默失效

6. **NeedsUserDecision 异常携带 record，broker 不写文件**（rev 2 修订）：
   - 异常 = 单零件 record；gen_std_parts 累积后**一次性原子写**全 pending 文件
   - 优点：进程中途崩溃不留半截 pending；测试好 mock；broker 单一职责

7. **broker 无 project_root 参数**（rev 2）：从 `cad_paths.PROJECT_ROOT` 直接读，避免 caller 传错路径

---

## 5. 决策文件 + Pending 文件 schema

### 5.1 `<project>/.cad-spec-gen/spec_decisions.json`（schema v2）

```json
{
  "schema_version": 2,
  "last_updated": "2026-04-25T22:30:00+00:00",
  "decisions_by_subsystem": {
    "end_effector": {
      "GIS-EE-001-03": {
        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
        "sldprt_filename": "o-rings series a gb.sldprt",
        "decision": "use_config",
        "config_name": "80×2.4",
        "user_note": "确认使用 SW 配置 80×2.4",
        "decided_at": "2026-04-25T22:25:11+00:00"
      },
      "GIS-EE-002-02": {
        "bom_dim_signature": "微型轴承|MR105ZZ",
        "sldprt_filename": "miniature radial ball bearings gb.sldprt",
        "decision": "fallback_cadquery",
        "config_name": null,
        "user_note": "SW 该型号缺失，确认 spec 正确，用 CadQuery 近似",
        "decided_at": "2026-04-25T22:25:32+00:00"
      }
    },
    "electrical": {
      "GIS-EL-002-01": {
        "bom_dim_signature": "...",
        "sldprt_filename": "...",
        "decision": "use_config",
        "config_name": "...",
        "user_note": "...",
        "decided_at": "..."
      }
    }
  },
  "decisions_history": [
    {
      "subsystem": "end_effector",
      "part_no": "GIS-EE-001-03",
      "previous_decision": {
        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
        "sldprt_filename": "o-rings series a gb.sldprt",
        "decision": "use_config",
        "config_name": "80×2.4",
        "user_note": "...",
        "decided_at": "2026-04-20T10:00:00+00:00"
      },
      "invalidated_at": "2026-04-25T22:25:11+00:00",
      "invalidation_reason": "config_name_not_in_available_configs"
    }
  ]
}
```

**`decision` 取值（rev 2 移除 `spec_amended`）：**

| 值 | 语义 | broker 命中后行为 |
|---|------|------------------|
| `use_config` | 用 SW 真配置 | 返回 `ConfigResolution(source="cached_decision", config_name=decision.config_name)` |
| `fallback_cadquery` | spec 正确但 SW 无对应规格，用 CadQuery 近似 | 返回 `ConfigResolution(source="cached_decision", config_name=None)` |

`spec_amended` 已移除：用户改 CAD_SPEC.md 后 BOM 的 dim_signature 自然变化，缓存自动失效；不需单独的 decision 取值表达"用户已修订 spec"，用 user_note 自由记录即可。

**`bom_dim_signature` 定义**：`f"{name_cn}|{material}"`（rev 2 明确）。
- 例 1（fastener，尺寸在 material）：`"内六角螺栓|GB/T 70.1 M8×20"`
- 例 2（bearing，尺寸在 name_cn）：`"深沟球轴承 6205|GCr15"`
- 例 3（seal）：`"O型圈|FKM Φ80×2.4"`
- 缺字段当空字符串：`f"{name_cn or ''}|{material or ''}"`

### 5.2 决策失效条件 + 校验流程

broker 在每次缓存命中时强制 COM 调用 + 三项校验（rev 2 锁定）：

| 失效条件 | `invalidation_reason` |
|---------|----------------------|
| 当前 BOM 的 `_build_bom_dim_signature(bom_row)` 与 cached `bom_dim_signature` 不一致 | `bom_dim_signature_changed` |
| 当前 SLDPRT 文件名（`Path(sldprt_path).name`）与 cached `sldprt_filename` 不一致 | `sldprt_filename_changed` |
| `decision="use_config"` 且 `cached.config_name` 不在 `_list_configs_via_com()` 当前返回的 `available_configs` 里 | `config_name_not_in_available_configs` |

**注意**：`decision="fallback_cadquery"` 跳过第三项检查（无 config_name 可校）。

失效时 broker 调用 `_move_decision_to_history` → 删除原位 → 调用 `_save_decisions_envelope` → 然后走 [3] 规则匹配。

`decisions_history` 仅用于审计，broker 不读它做决策。

### 5.3 `<project>/.cad-spec-gen/sw_config_pending.json`（schema v2）

```json
{
  "schema_version": 2,
  "generated_at": "2026-04-25T22:25:00+00:00",
  "pending_count": 3,
  "items_by_subsystem": {
    "end_effector": [
      {
        "part_no": "GIS-EE-001-03",
        "name_cn": "O型圈",
        "material": "FKM Φ80×2.4",
        "bom_dim_signature": "O型圈|FKM Φ80×2.4",
        "sldprt_path": "C:/SOLIDWORKS Data/browser/GB/o-rings/all o-rings/o-rings series a gb.sldprt",
        "sldprt_filename": "o-rings series a gb.sldprt",
        "available_configs": ["28×1.9", "35×2.0", "50×2.4", "80×2.4", "100×3.0"],
        "attempted_match": null,
        "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence",
        "suggested_options": [
          {"action": "use_config", "config_name": "80×2.4", "rationale": "字面完全匹配 BOM Φ80×2.4"},
          {"action": "fallback_cadquery", "rationale": "SW 配置略有差异时可用尺寸正确的近似体"}
        ]
      }
    ],
    "electrical": []
  }
}
```

**`match_failure_reason` 枚举与 schema 分支：**

| 值 | 触发条件 | available_configs | suggested_options 内容 |
|---|---------|-------------------|----------------------|
| `no_exact_or_fuzzy_match_with_high_confidence` | 规则匹配未达 confidence ≥ 0.7 阈值（最常见） | 完整列表 | 推 best L2 近似（confidence < 0.7 但最高的） + fallback_cadquery |
| `multiple_high_confidence_matches` | 两个以上候选都 ≥ 0.7 且分数相同（罕见） | 完整列表 | 列出全部 ≥ 0.7 的候选作 use_config 选项 + fallback_cadquery |
| `com_open_failed` | `_list_configs_via_com` subprocess 失败 / 超时 | `[]`（COM 失败拿不到列表）| 仅 fallback_cadquery 一项 |
| `empty_config_list` | SLDPRT 只有 "Default" 配置 | `["Default"]` | use_config "Default" + fallback_cadquery |

**`suggested_options[].action` 枚举与 `decision` 字段同源：** `use_config` | `fallback_cadquery`（rev 2 删除 `spec_amended`）。

**`suggested_options` 是关键** —— broker 在抛异常前先尝试的"差点就匹配"候选，agent / 用户基本只需选第一个，不必从 60 个 config 里盲选。

### 5.4 Pending 文件生命周期

- pipeline 在 `gen_std_parts.py` 末尾**一次性原子写** pending（broker 自身不写）
- `items_by_subsystem` 按本次 codegen 跑的 subsystem 累积；其他 subsystem 的旧 pending 数据**会被覆盖**（因为本次跑没有它们的信息，无法判断旧条目是否仍有效）
- 多 subsystem 用户工作流：跑完 end_effector 决策 → 删 pending → 跑 electrical → 决策 → 删 pending（不要跨 subsystem 累积 pending）
- agent 重跑 codegen 前**必须删除 pending**（不删则下次仍报旧条目）
- 决策完整 → 项目继续；决策残缺 → pending 留着，下次 codegen 累积到剩余项

---

## 6. 错误处理 + 回退

| 失败模式 | 处理 |
|---------|------|
| **COM open 失败**（SLDPRT 损坏 / SW hung / 子进程超时 15s） | broker 写 pending：`match_failure_reason="com_open_failed"`，`available_configs=[]`，suggested_options 仅 `fallback_cadquery` |
| **配置列表为空**（SLDPRT 只有 "Default"） | pending：`available_configs=["Default"]`，suggested = `use_config "Default"` + `fallback_cadquery` |
| **decisions.json JSON syntax 损坏**（用户手动编辑破坏 JSON） | **fail loud**：pipeline exit 1 + 报错"decisions 文件第 N 行 syntax error: <detail>"；**不静默重建**（避免丢历史决策） |
| **decisions.json schema_version 不一致**（code 升级但 file 是旧版） | 阻塞 + 提示"决策 schema 已升级 v{old}→v{new}，请重跑 codegen 让 agent 引导重新决策"；不自动 migrate（旧 schema 字段语义可能已变，自动转换有错配风险） |
| **`CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery`** | broker 不抛 NeedsUserDecision；返回 `ConfigResolution(source="policy_fallback", config_name=None, confidence=0.0)` + **依然累积 pending record**（事后审阅）|
| **`CAD_AMBIGUOUS_CONFIG_POLICY=halt`（默认）** | 含糊匹配抛 NeedsUserDecision；gen_std_parts 累积 → exit 7 |
| **决策的 config_name 失效**（SW 升级后该 config 改名） | broker 自动 invalidate → 挪入 decisions_history → 重写 pending |
| **多零件需决策** | gen_std_parts.py 遍历所有 BOM 累积 pending → 单次 exit 7 一次性报 |
| **并发跑 codegen** | 文件锁 `<project>/.cad-spec-gen/lock`（msvcrt.locking）；阻塞第二个进程到第一个完成 |

**SW 整体不可用**（未装 / COM down）：
- `sw_toolbox_adapter.is_available()` 早返回 False → broker 不被调用
- 所有零件按现有逻辑走 bd_warehouse → CadQuery
- 不生成 pending（无意义）
- ⚠️ 该路径**不是**违反原则 7 —— 因为 SW 不可用根本谈不上"绕过 SW"

**Skill metadata 更新（必做）：**
- `.claude/commands/cad-codegen.md` 增加段："⚠️ 当 pipeline 退 exit 7：必须读 `<project>/.cad-spec-gen/sw_config_pending.json`，逐项询问用户，写决策回 `spec_decisions.json` 的 `decisions_by_subsystem[<subsystem>][<part_no>]`，删除 pending，重跑"
- 同步到 `src/cad_spec_gen/data/commands/en/cad-codegen.md` 英文版
- `dev_sync.py` 同步到 AGENTS.md（v2.19.0）

---

## 7. 测试策略

### 7.1 三层金字塔

| 层 | 文件 | 覆盖 |
|---|------|------|
| **单元** | `tests/test_sw_config_broker.py` | `_build_bom_dim_signature` 三种 BOM 形式；`_match_config_by_rule` 边界（unicode `×`/`x`、大小写、空格/连字符、L2 子串假阳性 M6 vs M16）；`_load_decisions_envelope` schema v2 与损坏检测；`_validate_cached_decision` 三项 invalidation 分别触发；`NeedsUserDecision` 异常携带正确 record + subsystem |
| **集成** | `tests/test_sw_toolbox_adapter_with_broker.py` | mock `_list_configs_via_com` 返回固定列表 → 跑完整 resolve 流程；测 4 路径：cached_decision 命中 / cached invalidate / auto match / pending halt |
| **E2E（真 SW，可选）** | `tests/test_sw_config_broker_real.py` `@pytest.mark.requires_solidworks` | 真 SW：O型圈 SLDPRT 列配置 + match Φ80×2.4 + 导 STEP；Windows + SW 装机才跑，CI 跳过；测 COM list 实际延迟（验证 §10.2 的 3-5s 假设） |

### 7.2 必须覆盖的关键用例

1. **TDD RED → GREEN 第一案**：BOM `{"part_no":"X","name_cn":"O型圈","material":"FKM Φ80×2.4"}` + available `["28×1.9","80×2.4"]` → assert `ConfigResolution(config_name="80×2.4", source="auto", confidence=1.0)`
2. **决策缓存命中（仍调 COM 校验，但跳用户提问）**：
   - spec_decisions.json 已有该零件 use_config decision
   - mock `_list_configs_via_com` 返回包含 cached config_name 的列表（校验通过）
   - assert broker 调了 COM（mock 调用次数 ≥ 1）
   - assert 返回 source="cached_decision"
3. **决策 invalidate（cached config 不在 available 里）**：cached config="80×2.4" 但 available 变成 `["80x2.4 (FKM)"]` → broker 自动挪 decisions_history + 重新走规则匹配（这次 L2 命中 "80x2.4 (FKM)"）
4. **`CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery` 静默 fallback**：env 设置 + 含糊匹配 → broker 不抛、返回 `ConfigResolution(source="policy_fallback", config_name=None, confidence=0.0)` + 仍累积 pending record
5. **`CAD_AMBIGUOUS_CONFIG_POLICY=halt`（默认）= 严格 halt**：env 未设 + 含糊匹配 → broker 抛 NeedsUserDecision；assert pending_record subsystem 字段正确
6. **gen_std_parts 集成**：mock broker 抛 3 个 NeedsUserDecision（不同 subsystem）→ assert pipeline 调用 _save_decisions_envelope 0 次 + 调用 pending 文件原子写 1 次（含全部 3 项嵌套到正确 subsystem）+ exit 7 + 生成 std_*.py 跳过 pending 部分
7. **decisions.json 损坏 fail-loud**：故意写错 JSON syntax → `_load_decisions_envelope` raise `ValueError`，message 含具体行号
8. **多 subsystem 决策隔离**：同一 part_no "GIS-X-001" 在 end_effector 和 electrical 各有独立决策 → broker 用 subsystem 参数定位正确分支
9. **bom_dim_signature 三场景**：fastener / bearing / seal 各一组 BOM → assert signature 字符串符合 `f"{name_cn}|{material}"` 格式
10. **L2 子串假阳性防御**：available=["M6×20","M16×20"]，BOM material="GB/T 70.1 M16×20" → 必须命中 "M16×20" 不是 "M6×20"
11. **stdout 人读摘要存在**：mock 3 个 pending → 抓 stdout，assert 含 "请二选一处理" / "选 1" / "选 2" 等关键引导字符串
12. **并发锁**：两个并行进程同时跑 codegen → 第二个阻塞到第一个释放锁

### 7.3 测试基础设施

- 复用现有 conftest 的 `requires_solidworks` marker（session 9 设的）
- 新增 fixture `tmp_project_dir`：tmp 目录里建空 `.cad-spec-gen/`，赋予 `CAD_PROJECT_ROOT` env，重新 import `cad_paths` 让模块级常量重算
- mock COM worker 用 monkeypatch `subprocess.run` 返回预设 stdout（按 worker 的 JSON 输出契约）
- Decision/pending 文件 fixture：用 `tmp_path` 写预制 JSON，让 broker 读

### 7.4 Pre-flight 验证（防 CI 漂移）

- 写完代码必须跑 `.venv/Scripts/python.exe -m pytest tests/test_sw_*.py -v` 三连绿
- 然后裸 `pytest tests/test_sw_*.py` 模拟 CI 环境（per `feedback_preflight_mirror_ci.md`）

### 7.5 回归保障（手动）

- GISBOT 端到端 smoke：`CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT cad_pipeline.py codegen → exit 7`，检查 pending 含 ~3 个零件 + stdout 含人读摘要
- 用 `/cad-codegen` skill 让 Claude 引导填决策 → spec_decisions.json 写入 → 删除 pending → 重跑 → exit 0 + 生成的 std_*.py 含 SW STEP 路径（不是 CadQuery 近似）
- GLB 重建 → 检查文件大小在 [3, 8] MB 区间（既非 1.8MB CadQuery 也非 6.7MB 错配 STEP）
- 用 Blender open GLB → O 型圈截面是 SW 真实形状（半圆截面 + 准确的 80×2.4 比例），不是数学圆环

---

## 8. 验收标准

| AC | 描述 | 验证方法 |
|----|------|---------|
| **AC-1** | broker 能列出 SW Toolbox SLDPRT 的所有 config 名 | E2E 测试：O 型圈 SLDPRT → 列出 ≥1 个 config |
| **AC-2** | broker 能用规则匹配 BOM Φ80×2.4 → "80×2.4" config，confidence=1.0 | 单元测试 7.2 #1 |
| **AC-3** | 含糊匹配触发 NeedsUserDecision + 异常携带正确 record（不写 pending 文件） | 单元测试 7.2 #5 |
| **AC-4** | spec_decisions.json 命中**仍调 COM 校验**（不跳过 COM）| 集成测试 7.2 #2 |
| **AC-5** | decisions invalidate 三项触发条件分别工作 + 自动挪 history | 集成测试 7.2 #3 + 单元测试三 invalidation |
| **AC-6** | 默认 policy="halt"（无 env var）时严格不 fallback | 集成测试 7.2 #5 |
| **AC-7** | `CAD_AMBIGUOUS_CONFIG_POLICY=fallback_cadquery` 显式 opt-in 才 fallback | 集成测试 7.2 #4 |
| **AC-8** | decisions.json 损坏 fail-loud 含行号 | 集成测试 7.2 #7 |
| **AC-9** | gen_std_parts.py exit 7 累积 pending 一次性原子写（含 multi-subsystem 嵌套）| 集成测试 7.2 #6 |
| **AC-10** | 多 subsystem 决策隔离 | 集成测试 7.2 #8 |
| **AC-11** | stdout 人读摘要让命令行用户也能动手处理 | 集成测试 7.2 #11 |
| **AC-12** | GISBOT 真跑端到端：决策填完后 GLB 含 SW 几何 | 手动 smoke §7.5 |
| **AC-13** | Skill 文档更新：cad-codegen.md 含 exit 7 处理流程 | grep `.claude/commands/cad-codegen.md` 含 "exit 7"；dev_sync 后 AGENTS.md 同步 |

---

## 9. 范围与非目标

### 9.1 范围内

- `adapters/solidworks/sw_config_broker.py` 新模块
- `adapters/solidworks/sw_list_configs_worker.py` 新 worker
- `sw_toolbox_adapter.resolve()` 接入 broker（替换现有 `_build_candidate_config` + cache 命中逻辑）
- `gen_std_parts.py` 接住 NeedsUserDecision + 累积 pending + exit 7 + stdout 摘要 + 原子写
- 决策文件 schema v2 + Pending 文件 schema v2 文档化
- 9 类错误处理实现（含 schema mismatch / fallback policy）
- 测试三层金字塔 + 12 关键用例
- Skill 文档更新（中文 + 英文 + AGENTS.md）

### 9.2 非范围

- **不改其他 adapter**（bd_warehouse / step_pool / partcad / 自定义 part 走原路径，broker 只对 SW Toolbox 命中的零件起作用）
- **不重写 sw-warmup**（B2 预热默认配置 STEP 仍保留作为 fallback，但 broker 优先用动态导出）
- **不引入 LLM API 直接调用**（LLM-用户交互在 agent 层，pipeline 仅产 pending 数据）
- **不改 BOM 解析层**（不动 `bom_parser.py` 的 category 路由规则）
- **不动 build_all.py**（接收的 std_*.py 长相不变，只是 STEP 路径变成 config-suffixed 缓存路径）
- **不实现自动 spec 修订**（用户改 CAD_SPEC.md 自己来；broker 不写设计文档）
- **不实现 decisions.json 自动 schema migration**（schema v1→v2 等 bump 时阻塞用户重做交互）

---

## 10. 假设与未知

### 10.1 已验证假设

- ✅ `model.ConfigurationManager.GetConfigurationNames()` 是 SW COM API 标准调用（已在 `sw_convert_worker.py:81` 使用）
- ✅ `model.ShowConfiguration2(name)` 接 string 即可切换配置（已在 `sw_convert_worker.py:90` 使用）
- ✅ SW Toolbox 的 SLDPRT 文件路径稳定可访问（GISBOT 已通过 toolbox_index.json 验证 `C:\SOLIDWORKS Data\browser\` 路径有效）
- ✅ msvcrt.locking 在 Windows 下可作文件锁（标准库，不引新依赖）
- ✅ `cad_paths.PROJECT_ROOT` 是模块级常量，broker 直接 import 即可

### 10.2 待验证假设

- ⚠️ **SW Toolbox SLDPRT 内部 configuration 数量不会过大**（O 型圈 SLDPRT 假设 < 100 个 config）。若实际有 1000+ config，列表 + UI 选择需分页。**验证方式**：执行计划第一步真跑 SW COM 列 GISBOT 用到的 5 个 SLDPRT，记数。
- ⚠️ **SW Toolbox config 命名一致性**：假设同一 SLDPRT 内 config 名格式一致（都是 "DxL" 或都是 "GB-XXXX-DxL"），不会混合两种格式。**验证方式**：同上 SW COM 列出后人工巡检命名规律。
- ⚠️ **L2 子串匹配 false positive 风险**：候选 "M6 X 20" 与 "M16 X 20" 都含 "20"，BOM 要 "M16" 时是否会误命中 "M6"？**验证方式**：单元测试 7.2 #10 穷举 fastener 类边界。
- ⚠️ **COM list_configs 延迟假设 3-5s/SLDPRT**：rev 2 缓存命中策略基于此估算 GISBOT 增量 15-25s。**验证方式**：E2E 测试 7.1 第三层实测后调整 timeout 与文档。

### 10.3 未知

- 🔴 **SW Toolbox 不同 standard（GB / ISO / DIN）下同一 SLDPRT 的 config 命名风格是否相同**：暂无数据，需运行时观察。Mitigation：broker 的匹配规则按 standard 分组，发现不一致时各自配置。
- 🔴 **Subprocess timeout 选什么值**：`sw_convert_worker` 用 20s（基于真 smoke 实测），`sw_list_configs_worker` 应该比 convert 快（无 SaveAs3 写盘）。**初值定 15s**，第一次真跑后调整。

---

## 11. 实施约束

继承 `CLAUDE.md` 的 Superpowers 工作流：

1. **TDD 铁律**：每个公开函数先写失败测试，再写实现，测试通过后不加额外逻辑
2. **plan 阶段**：用 `superpowers:writing-plans` 拆成每步 2-5 分钟子任务
3. **execute 阶段**：用 `superpowers:executing-plans` subagent 并行执行，每检查点暂停确认
4. **复审**：每任务完调用 `superpowers:requesting-code-review` + `receiving-code-review`
5. **语言**：所有输出中文（代码标识符英文）
6. **commit 格式**：`feat(sw_config_broker): <中文描述>` / `test(sw_config_broker): ...` / `fix(...)`

环境变量从 `os.environ` 标准 key 读取（不在 broker 内 hardcode 名称）：
- `CAD_PROJECT_ROOT`：通过 `cad_paths.PROJECT_ROOT` 间接生效
- `CAD_AMBIGUOUS_CONFIG_POLICY`：broker 直接读，默认 "halt"

---

## 12. 后续工作（不在本 spec 内）

- v2.20.0：上线 broker；GISBOT 验收 GLB 含 SW 几何
- v2.21.0：sw-warmup 增 `--bom <CAD_SPEC.md>` 模式：预扫 BOM 提前为所有匹配零件做 ShowConfiguration2 导出 + 列 config 名，避免首次 codegen 慢
- v2.22.0：决策文件 import/export 跨项目复用（用户可把通用决策导出为 yaml 上传 git）
- v2.23.0：考虑 `cad_pipeline.py codegen --apply-decisions` 子命令把 pending.json 中用户填的 user_choice 字段自动转写到 spec_decisions.json（替代当前 §3.3 "[手动]"路径里的人肉编辑步骤）

---

_本文档 rev 2 由代码审查反馈驱动重写：13 项一致性问题 + 1 项新约束（不静默绕过 SW）已全部堵掉；下一步 writing-plans 拆任务。_
