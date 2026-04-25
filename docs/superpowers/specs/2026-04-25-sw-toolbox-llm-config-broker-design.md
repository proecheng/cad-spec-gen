# SW Toolbox 配置名 LLM-broker 设计

**日期**：2026-04-25
**状态**：设计已确认，待计划
**作者**：Claude Sonnet 4.6 + procheng
**关联**：session 31 后续 — 修复 Phase D 路径 B：`gen_std_parts.py` 让 ShowConfiguration2 取尺寸匹配的 SW Toolbox STEP

---

## 1. 背景与问题

### 1.1 现状

`cad_pipeline.py codegen` 会调 `gen_std_parts.py`，后者用 `parts_resolver.PartsResolver` 解析 BOM 标准件，匹配 `sw_toolbox_adapter.SwToolboxAdapter`（COM 适配器）后生成 `std_*.py`。`std_*.py` 在 build phase 加载 STEP 文件并装配进 GLB。

预热步骤 `sw-warmup`（B2）已为 SW Toolbox 里 330 个 SLDPRT 文件各导出 **1 个默认配置 STEP**，缓存到 `~/.cad-spec-gen/step_cache/sw_toolbox/<standard>/<subcategory>/<part>.step`。

### 1.2 缺陷

`sw_toolbox_adapter.resolve()` 当前对**含 `config_name_resolver` 标准化规则**的 BOM 行（仅 GB/T 紧固件）才会构造 `target_config`，触发 ShowConfiguration2 重新导出尺寸匹配的 STEP；其他类别（O 型圈、轴承、定位销等）`target_config = None` → 命中预热的默认配置 STEP（**尺寸通常错** —— 例如 BOM 要 Φ80×2.4，缓存里却是 Φ28×1.9）→ GLB 加载错尺寸的 SW 几何。

session 31 后用户跑 GISBOT 端到端，发现新生成的 GLB（6.7 MB）里 SW Toolbox 零件尺寸完全跑偏。当时为应急，把 `std_*.py` 全替换成 canonical CadQuery 近似体（GLB 1.8 MB，尺寸正确但**完全没有 SW 几何**），用户反馈："新生成的 GLB 还不如改进前，没有看到 SW 模型库被使用"。

### 1.3 根因

1. 预热缓存 STEP 路径不带 config 后缀 → 任意 BOM 尺寸都"命中"默认配置 STEP
2. `_build_candidate_config` 只覆盖 `GB/T` 标准+尺寸格式（fastener），seal/bearing/locating 等格式不被识别
3. SW Toolbox 各 SLDPRT 内部的 configuration 命名规则**不可预知**（不同零件命名风格不同：`80×2.4` vs `GB1235-80x2.4` vs `M8 X 20`），无法靠正则枚举

### 1.4 用户目标

> "我想看到 SW 模型库的零件出现在 GLB 里，且尺寸正确"

需要一种机制：在 codegen 时主动列出 SLDPRT 真实可用的 configuration 列表，匹配 BOM 尺寸到正确 config，再调 ShowConfiguration2 + 导出 STEP。当含糊或匹配失败时，**与用户交互**而非静默选错或放弃 SW。

---

## 2. 设计原则与约束

继承 `project_north_star.md` 的 5 条北极星：

1. **零配置**：默认行为正确，不要求用户改 yaml
2. **稳定可靠**：失败模式清晰、可恢复
3. **结果准确**：宁可问用户也不静默错配
4. **SW 装即用**：SW + Toolbox 装好就能跑
5. **傻瓜式操作**：把"判断 SW config 名"这件需要专业知识的事，封装成"看几个候选选一个"的简单选择

新增一条约束（来自本次澄清）：

6. **LLM 与用户交互的角色由 agent 承担**，不在 pipeline 内嵌任何 LLM API 调用。pipeline 输出结构化的"待决策"数据，跑该 skill 的 LLM agent（Claude / Codex / Gemini Agent 等）读数据后向用户提问。这样 skill 与具体 LLM 解耦。

---

## 3. 架构

### 3.1 模块新增

`adapters/solidworks/sw_config_broker.py`（新文件，~250 行）：把"如何为某 BOM 行匹配 SW Toolbox 配置名"这件事封装成**单一职责**模块。`sw_toolbox_adapter.resolve()` 委托给它，自身只管 SLDPRT 匹配 + STEP 导出编排。

`adapters/solidworks/sw_list_configs_worker.py`（新文件，~50 行）：独立 subprocess 用 SW COM 列出某 SLDPRT 的所有 configuration 名称，stdout 输出 JSON list。复用 `sw_convert_worker.py` 的 subprocess + timeout + 退出码契约模式。

### 3.2 数据流

```
gen_std_parts.py
    │
    │ for each BOM row:
    ▼
parts_resolver.resolve_one(bom_row)
    │
    ▼
sw_toolbox_adapter.resolve(query, spec)
    │ 1. token 匹配找到 SLDPRT (现有逻辑不变)
    ▼
sw_config_broker.resolve_config_for_part(bom_row, sldprt, project_root, interactive)
    │
    ├─[1] 读 .cad-spec-gen/spec_decisions.json 命中 → 返回 cached_decision
    │
    ├─[2] 调 SW COM list_configurations(sldprt) → 缓存到内存
    │
    ├─[3] _match_config_by_rule (BOM dim → config) 命中 → 返回 auto
    │
    ├─[4] CAD_NONINTERACTIVE=1 → 写 pending + 返回 fallback_cadquery
    │
    └─[5] 默认交互模式 → 写 pending + 抛 NeedsUserDecision

回到 gen_std_parts.py：
    │
    ├─ NeedsUserDecision → 累积到 pending 列表
    │
    └─ 全部 BOM 跑完后：
        ├─ pending 非空 → 写汇总报告 + exit 7
        └─ pending 空 → 正常生成 std_*.py
```

### 3.3 Agent 介入点（不在 pipeline 内）

pipeline `exit 7` → agent 读 `<project>/.cad-spec-gen/sw_config_pending.json` → **逐零件问用户** → 写 `<project>/.cad-spec-gen/spec_decisions.json` → 删除 pending → 重跑 codegen。

这一段属于 skill 文档的运行时约定，由 `.claude/commands/cad-codegen.md` 描述（agent 看 skill 文档知道该这么做）。

### 3.4 边界

- broker 对外只暴露 `resolve_config_for_part(bom_row, sldprt_path, project_root, *, interactive=True) -> ConfigResolution`
- broker **无持久 state**（决策状态全在 `spec_decisions.json` 文件里）
- 唯一例外是 process-local 内存缓存：模块级 `_CONFIG_LIST_CACHE: dict[str, list[str]]` 用于 COM 调用 dedup（重启即清，仅生命周期 = 一次 codegen 进程）

---

## 4. 核心组件

### 4.1 数据类与异常

```python
@dataclass
class ConfigResolution:
    config_name: str | None       # None = fallback to CadQuery
    source: str                    # "cached_decision" | "auto" | "fallback_cadquery"
    confidence: float              # 0.0-1.0；auto 来源带分数
    available_configs: list[str]   # 列出的所有候选（pending 文件参考）
    notes: str = ""                # 失败原因或解释


class NeedsUserDecision(Exception):
    """broker 写完 pending 后抛此异常；
    sw_toolbox_adapter 捕获 → return miss（不污染 resolve 主流程返回类型）"""
    def __init__(self, part_no: str, pending_record: dict):
        self.part_no = part_no
        self.pending_record = pending_record
```

### 4.2 公开 API

```python
def resolve_config_for_part(
    bom_row: dict,           # 含 part_no, name_cn, material 等
    sldprt_path: str,
    project_root: str,
    *,
    interactive: bool = True,  # False = CI 模式
) -> ConfigResolution:
    """主入口。失败模式：NeedsUserDecision (interactive) / fallback_cadquery (CI)"""
```

### 4.3 私有辅助

```python
def _list_configs_via_com(sldprt_path: str) -> list[str]
def _load_decisions_file(project_root: str) -> dict[str, dict]
def _save_decisions_file(project_root: str, decisions: dict) -> None
def _append_pending(project_root: str, record: dict) -> None
def _match_config_by_rule(bom_row: dict, available: list[str]) -> tuple[str, float] | None
def _build_pending_record(bom_row, sldprt, available, attempted_match) -> dict
```

### 4.4 关键决策

1. **`_list_configs_via_com` 走独立 subprocess** —— 复用 `sw_convert_worker.py` 模式，新建 `sw_list_configs_worker.py`，不污染现有 convert worker
2. **`_match_config_by_rule` 两层匹配 + 置信度阈值**：
   - **L1 精确归一化（confidence=1.0）**：尺寸抽取 → 与候选 config 字符串归一化后**等值比对**（统一 `×`→`x`、`Φ`→`""`、去 `[-_\s]`、lowercase）
   - **L2 包含子串（confidence=0.7）**：候选 config 字符串归一化后**包含**归一化尺寸 token（如 "GB1235-80x2.4" 包含 "80x2.4"）
   - 命中返回 `(matched_config, confidence_score)`；同时多个 L2 命中时取**字符串最短**的（最少干扰），未命中 → None
   - **`AUTO_MATCH_THRESHOLD = 0.7`**：confidence ≥ 0.7 → 直接 source="auto" 不走 pending；< 0.7 → 抛 NeedsUserDecision（建议选项里仍把这些"差点匹配"列在 suggested_options）
3. **决策文件 `schema_version` 字段**：未来 bump 时旧文件触发提示而不是静默失效
4. **NeedsUserDecision 异常 vs return tuple**：强制 sw_toolbox_adapter 显式处理（不能误用为 hit），异常携带 pending_record 方便测试 assert
5. **process-local config 缓存**：模块级 dict `_CONFIG_LIST_CACHE: dict[str, list[str]]`，按 sldprt 绝对路径 key，重启即清

---

## 5. 决策文件 + Pending 文件 schema

### 5.1 `<project>/.cad-spec-gen/spec_decisions.json`

```json
{
  "schema_version": 1,
  "subsystem": "end_effector",
  "last_updated": "2026-04-25T22:30:00+00:00",
  "decisions": {
    "GIS-EE-001-03": {
      "bom_dim_signature": "FKM Φ80×2.4",
      "sldprt_filename": "o-rings series a gb.sldprt",
      "decision": "use_config",
      "config_name": "80×2.4",
      "user_note": "确认使用 SW 配置 80×2.4",
      "decided_at": "2026-04-25T22:25:11+00:00"
    }
  },
  "decisions_history": [
    {
      "part_no": "GIS-EE-001-03",
      "previous_decision": {
        "bom_dim_signature": "FKM Φ80×2.4",
        "config_name": "80×2.4",
        "decided_at": "2026-04-20T10:00:00+00:00"
      },
      "invalidated_at": "2026-04-25T22:25:11+00:00",
      "invalidation_reason": "config_name_not_in_available_configs"
    }
  ]
}
```

**`decision` 三种取值：**
- `use_config` — 用 SW 真配置（最常见）
- `fallback_cadquery` — 用 CadQuery 近似体（spec 正确但 SW 无对应规格）
- `spec_amended` — 用户已改 spec，决策记录新尺寸

### 5.2 决策失效条件

broker 检查每个 cached decision，对应 `invalidation_reason` 字符串值（写入 `decisions_history`）：

| 失效条件 | `invalidation_reason` |
|---------|----------------------|
| 当前 BOM 行 `material` 字段与 cached `bom_dim_signature` 不一致 | `bom_dim_signature_changed` |
| 当前 SLDPRT 文件名与 cached `sldprt_filename` 不一致 | `sldprt_filename_changed` |
| cached `config_name` 不在当前 `available_configs` 里 | `config_name_not_in_available_configs` |

失效时 broker：
1. 把旧决策完整复制到 `decisions_history` 数组，附上 `invalidated_at` ISO 时间戳和 `invalidation_reason`
2. 删除 `decisions[part_no]`
3. 走正常解析流程（COM 列 config + 规则匹配 + 必要时写 pending）

`decisions_history` 仅用于审计，broker 不读它做决策。

### 5.3 `<project>/.cad-spec-gen/sw_config_pending.json`

```json
{
  "schema_version": 1,
  "subsystem": "end_effector",
  "generated_at": "2026-04-25T22:25:00+00:00",
  "pending_count": 3,
  "items": [
    {
      "part_no": "GIS-EE-001-03",
      "name_cn": "O型圈",
      "material": "FKM Φ80×2.4",
      "sldprt_path": "C:/SOLIDWORKS Data/browser/GB/o-rings/all o-rings/o-rings series a gb.sldprt",
      "available_configs": ["28×1.9", "35×2.0", "50×2.4", "80×2.4", "100×3.0"],
      "attempted_match": null,
      "match_failure_reason": "no_exact_or_fuzzy_match_with_high_confidence",
      "suggested_options": [
        {"action": "use_config", "config_name": "80×2.4", "rationale": "字面完全匹配 BOM Φ80×2.4"},
        {"action": "fallback_cadquery", "rationale": "SW 配置略有差异时可用尺寸正确的近似体"}
      ]
    }
  ]
}
```

**`match_failure_reason` 枚举：**

| 值 | 触发条件 |
|---|---------|
| `no_exact_or_fuzzy_match_with_high_confidence` | 规则匹配未达 confidence ≥ 0.7 阈值（最常见） |
| `com_open_failed` | `_list_configs_via_com` subprocess 失败 / 超时 |
| `empty_config_list` | SLDPRT 只有 "Default" 配置 |
| `multiple_high_confidence_matches` | 两个以上候选都 ≥ 0.7 且分数相同（罕见） |

**`suggested_options` 是关键** —— broker 在抛异常前先尝试的"差点就匹配"候选，agent 把这些选项呈现给用户，用户大多数情况下选第一个就行，不需要从 60 个 config 里盲选。`suggested_options[].action` 取值：`use_config` | `fallback_cadquery` | `spec_amended`（与 decisions 文件 `decision` 字段相同枚举）。

### 5.4 Pending 文件生命周期

- pipeline 写完 pending → exit 7
- agent 读 → 逐项问用户 → 写 spec_decisions.json
- agent 重跑 codegen 前**删除 pending**（不删则下次仍报）
- 决策完整 → 项目继续；决策残缺 → pending 留着，下次 codegen 累积到剩余项

---

## 6. 错误处理 + 回退

| 失败模式 | 处理 |
|---------|------|
| **COM open 失败**（SLDPRT 损坏 / SW hung / 子进程超时 20s） | broker 写 pending：`match_failure_reason="com_open_failed"`，suggested = fallback_cadquery |
| **配置列表为空**（SLDPRT 只有 "Default"） | pending：`available_configs=["Default"]`，suggested = use_config "Default" |
| **decisions.json 损坏**（用户手动编辑破坏 JSON） | **fail loud**：pipeline exit 1 + 报错"decisions 文件第 N 行 syntax error"；**不静默重建**（避免丢历史决策） |
| **decisions.json schema 升级**（code 升 schema_version != 1） | 阻塞 + 提示"决策 schema 已升级，请重跑交互"；不自动 migrate |
| **CI 模式 (CAD_NONINTERACTIVE=1)** | broker 不抛 NeedsUserDecision；改返回 `ConfigResolution(None, source="fallback_cadquery")` + **依然写 pending**（事后审阅） |
| **决策的 config_name 失效**（SW 升级后该 config 改名） | broker 自动 invalidate 该决策 → 挪入 `decisions_history` → 重写 pending |
| **多零件需决策** | gen_std_parts.py 遍历所有 BOM 累积 pending → 单次 exit 7 一次性报 |
| **并发跑 codegen** | 文件锁 `<project>/.cad-spec-gen/lock`（msvcrt.locking）；阻塞第二个进程到第一个完成 |

**SW 整体不可用**（未装 / COM down）：
- `sw_toolbox_adapter.is_available()` 早返回 False → broker 不被调用
- 所有零件按现有逻辑走 bd_warehouse → CadQuery
- 不生成 pending（无意义）

**Skill metadata 更新（必做）：**
- `.claude/commands/cad-codegen.md` 增加段："⚠️ 当 pipeline 退 exit 7：必须读 `<project>/.cad-spec-gen/sw_config_pending.json`，逐项询问用户，写决策回 `spec_decisions.json`，删除 pending，重跑"
- 同步到 `src/cad_spec_gen/data/commands/en/cad-codegen.md` 英文版
- `dev_sync.py` 同步到 AGENTS.md（v2.19.0）

---

## 7. 测试策略

### 7.1 三层金字塔

| 层 | 文件 | 覆盖 |
|---|------|------|
| **单元** | `tests/test_sw_config_broker.py` | `_match_config_by_rule` 边界（unicode `×`/`x`、大小写、空格/连字符）；`_load_decisions_file` schema 校验；`_append_pending` 去重；`NeedsUserDecision` 异常携带正确 record |
| **集成** | `tests/test_sw_toolbox_adapter_with_broker.py` | mock `_list_configs_via_com` 返回固定列表 → 跑完整 resolve 流程；测 3 路径：cached_decision hit / auto match / pending fallback |
| **E2E（真 SW，可选）** | `tests/test_sw_config_broker_real.py` `@pytest.mark.requires_solidworks` | 真 SW：O型圈 SLDPRT 列配置 + match Φ80×2.4 + 导 STEP；Windows + SW 装机才跑，CI 跳过 |

### 7.2 必须覆盖的关键用例

1. **TDD RED → GREEN 第一案**：BOM `{"part_no":"X","material":"FKM Φ80×2.4"}` + available `["28×1.9","80×2.4"]` → assert `ConfigResolution(config_name="80×2.4", source="auto")`
2. **决策缓存命中**：spec_decisions.json 已有该零件决策 → broker 不调 COM，直接返回 cached_decision
3. **决策 invalidate**：spec_decisions.json 的 config_name="80×2.4" 但 available 变成 `["80x2.4 (FKM)"]` → broker 自动挪历史 + 重写 pending
4. **CI 模式**：`CAD_NONINTERACTIVE=1` 环境下 broker **不抛异常**而是 fallback；pending 文件依然写入
5. **gen_std_parts 集成**：mock broker 返回 NeedsUserDecision → gen_std_parts 累积、最后 exit 7、生成 std_*.py 跳过 pending 部分
6. **decisions.json 损坏 fail-loud**：故意写错 JSON syntax → pipeline 报具体行号、不静默重建
7. **并发锁**：两个并行进程同时跑 codegen → 第二个阻塞到第一个释放锁

### 7.3 测试基础设施

- 复用现有 conftest 的 `requires_solidworks` marker（session 9 设的）
- 新增 fixture `tmp_project_dir`：tmp 目录里建空 `.cad-spec-gen/`，赋予 `CAD_PROJECT_ROOT` env
- mock COM worker 用 monkeypatch `subprocess.run` 返回预设 stdout（按 worker 的 JSON 输出契约）

### 7.4 Pre-flight 验证（防 CI 漂移）

- 写完代码必须跑 `.venv/Scripts/python.exe -m pytest tests/test_sw_*.py -v` 三连绿
- 然后裸 `pytest tests/test_sw_*.py` 模拟 CI 环境（per `feedback_preflight_mirror_ci.md`）

### 7.5 回归保障（手动）

- GISBOT 端到端 smoke：`CAD_PROJECT_ROOT=D:/Work/cad-tests/GISBOT cad_pipeline.py codegen → exit 7`，检查 pending 含 ~3 个零件
- 手动答 3 个决策后重跑 → 检查 std_*.py 含 SW STEP 路径（不是 CadQuery 近似）
- GLB 重建 → 检查文件大小在 [3, 8] MB 区间（既非 1.8MB CadQuery 也非 6.7MB 错配 STEP）

---

## 8. 验收标准

| AC | 描述 | 验证方法 |
|----|------|---------|
| **AC-1** | broker 能列出 SW Toolbox SLDPRT 的所有 config 名 | E2E 测试：O 型圈 SLDPRT → 列出 ≥1 个 config |
| **AC-2** | broker 能用规则匹配 BOM Φ80×2.4 → "80×2.4" config | 单元测试：固定 available 列表，assert config_name |
| **AC-3** | 含糊匹配触发 NeedsUserDecision + 写正确 pending JSON | 单元测试：assert 异常 + JSON schema |
| **AC-4** | spec_decisions.json 命中跳过 COM | 集成测试：mock COM 抛异常，决策命中应不触发该 mock |
| **AC-5** | decisions invalidate 自动挪 history | 集成测试：改 available 列表，assert decisions_history 新增 |
| **AC-6** | CI 模式 (`CAD_NONINTERACTIVE=1`) fallback 不抛 | 集成测试：env 设置后 broker 返回 fallback_cadquery |
| **AC-7** | decisions.json 损坏 fail-loud | 集成测试：写错 JSON → pytest.raises with 行号 message |
| **AC-8** | gen_std_parts.py exit 7 累积报告 | 集成测试：mock 多个 NeedsUserDecision → 单次退出码 7 + pending 含全部 |
| **AC-9** | GISBOT 真跑端到端：决策填完后 GLB 含 SW 几何 | 手动 smoke：GLB 在 [3, 8] MB；用 Blender open 看 O 型圈截面是 SW 真实形状不是数学圆环 |
| **AC-10** | Skill 文档更新：cad-codegen.md 含 exit 7 处理流程 | grep `.claude/commands/cad-codegen.md` 含 "exit 7"；dev_sync 后 AGENTS.md 同步 |

---

## 9. 范围与非目标

### 9.1 范围内

- `adapters/solidworks/sw_config_broker.py` 新模块
- `adapters/solidworks/sw_list_configs_worker.py` 新 worker
- `sw_toolbox_adapter.resolve()` 接入 broker（替换现有 `_build_candidate_config` + cache 命中逻辑）
- `gen_std_parts.py` 接住 NeedsUserDecision + 累积 pending + exit 7
- 决策文件 schema 文档化
- 8 类错误处理实现
- 测试三层金字塔 + 7 关键用例
- Skill 文档更新（中文 + 英文 + AGENTS.md）

### 9.2 非范围

- **不改其他 adapter**（bd_warehouse / step_pool / partcad / 自定义 part 走原路径，broker 只对 SW Toolbox 命中的零件起作用）
- **不重写 sw-warmup**（B2 预热默认配置 STEP 仍保留作为 fallback，但 broker 优先用动态导出）
- **不引入 LLM API 直接调用**（LLM-用户交互在 agent 层，pipeline 仅产 pending 数据）
- **不改 BOM 解析层**（不动 `bom_parser.py` 的 category 路由规则）
- **不动 build_all.py**（接收的 std_*.py 长相不变，只是 STEP 路径变成 config-suffixed 缓存路径）
- **不实现自动 spec 修订**（用户选 `spec_amended` 后必须手动改 CAD_SPEC.md，broker 不写设计文档）

---

## 10. 假设与未知

### 10.1 已验证假设

- ✅ `model.ConfigurationManager.GetConfigurationNames()` 是 SW COM API 标准调用（已在 `sw_convert_worker.py:81` 使用）
- ✅ `model.ShowConfiguration2(name)` 接 string 即可切换配置（已在 `sw_convert_worker.py:90` 使用）
- ✅ SW Toolbox 的 SLDPRT 文件路径稳定可访问（GISBOT 已通过 toolbox_index.json 验证 `C:\SOLIDWORKS Data\browser\` 路径有效）
- ✅ msvcrt.locking 在 Windows 下可作文件锁（标准库，不引新依赖）

### 10.2 待验证假设

- ⚠️ **SW Toolbox SLDPRT 内部 configuration 数量不会过大**（O 型圈 SLDPRT 假设 < 100 个 config）。若实际有 1000+ config，列表 + UI 选择需分页。**验证方式**：执行计划第一步真跑 SW COM 列 GISBOT 用到的 5 个 SLDPRT，记数。
- ⚠️ **SW Toolbox config 命名一致性**：假设同一 SLDPRT 内 config 名格式一致（都是 "DxL" 或都是 "GB-XXXX-DxL"），不会混合两种格式。**验证方式**：同上 SW COM 列出后人工巡检命名规律。
- ⚠️ **L2 子串匹配 false positive 风险**：候选 "M6 X 20" 与 "M16 X 20" 都含 "20"，BOM 要 "M16" 时是否会误命中 "M6"？**验证方式**：单元测试穷举 fastener 类边界。

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

继承 `CAD_NONINTERACTIVE` 等环境变量从 `cad_paths.py` 读取，不在 broker 内 hardcode 名称（broker 只读 `os.environ` 标准 key）。

---

## 12. 后续工作（不在本 spec 内）

- v2.20.0：上线 broker；GISBOT 验收 GLB 含 SW 几何
- v2.21.0：sw-warmup 增 `--bom <CAD_SPEC.md>` 模式：预扫 BOM 提前为所有匹配零件做 ShowConfiguration2 导出，避免首次 codegen 慢
- v2.22.0：决策文件 import/export 跨项目复用（用户可把通用决策导出为 yaml 上传 git）

---

_本文档由 brainstorming 阶段 5 段确认产出；下一步 writing-plans 拆任务。_
