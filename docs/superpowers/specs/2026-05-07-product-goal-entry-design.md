# 设计文档：Phase 1 新用户入口前移到产品目标自然语言模式

**日期**：2026-05-07
**作者**：brainstorming session
**目标**：把 `project-guide` 入口前移一步——外行用户不写设计文档也能启动，只用一句产品目标自然语言（如"做一个升 50kg 的升降平台"），系统识别子系统类别 + 抽取顶层 KPI + 标记缺失项，让用户用 `--confirm-X` flag 一次性补齐后进入既有 Phase 1 流程

---

## 问题陈述

**现状（v2.24.0）**：

- `project-guide --from-design-doc --design-doc <path>` 是当前最前置入口
- 必须用户先有一个完整设计文档才能启动
- 完全外行用户（"我想做个能升 50kg 的平台"）无法启动管线

**目标**：

- 把入口再前移一步，外行用户只用自然语言产品目标即可启动
- 不引入 LLM、云后端、密钥、网络依赖（守"零配置 / 装即用 / Windows-only"约束）
- 系统识别错或漏识别时，必须显式标记 `needs_user_input`，绝不静默猜测（守"AI 不能补 CAD 缺件"边界）
- 兼容现有 `--from-design-doc` 模式（并存而非替代）

**非目标（YAGNI）**：

- 不做交互式 CLI prompt（不用 `input()`），保持脚本化
- 不做 LLM 自然语言理解（确定性词典已足够）
- 不收集 14-30 个 CAD 全量参数（只收 1-3 个外行能表达的顶层 KPI，剩余交给现有 supplementation 流程）
- 不生成 CAD_SPEC.md 草案（入口纯只读，不动 pipeline state）

---

## 设计

### 数据流

```
[用户自然语言 + 可选设计文档]
      ↓
[3 层确定性词典/regex 解析]
      ↓
{subsystem_class, product_goal, kpi_extracted, kpi_missing, status}
      ↓
[写 .cad-spec-gen/project-guide/PROJECT_GUIDE.json]
      ↓
[输出 next_action.preview_cli 推荐下一条命令]
```

### 与现有 `--from-design-doc` 的关系

**并存，不替代**。模式选择优先级：

1. `--product-goal` 传入 → 走新增 `write_project_goal_guide`
2. `--from-design-doc` + `--design-doc` → 走既有 `write_project_entry_guide`
3. `--subsystem ...` → 走既有 `write_project_guide`
4. 全空 → 现状（按 active run 推断）

### `PROJECT_GUIDE.json` 新字段

扩展现有 schema：

```json
{
  "entry_mode": "product_goal",
  "status": "needs_kpi_confirmation",
  "product_goal": {
    "text": "做一个能升 50kg、行程 200mm 的升降平台",
    "subsystem_class": "lifting_platform",
    "subsystem_status": "implemented",
    "kpi_extracted": {"load_kg": 50, "stroke_mm": 200},
    "kpi_missing": ["speed_mm_s"],
    "parser_evidence": [
      {"token": "升降平台", "matched": "subsystem_class", "rule": "primary_terms[0]"},
      {"token": "50kg", "matched": "load_kg", "rule": "regex+context:升"},
      {"token": "200mm", "matched": "stroke_mm", "rule": "regex+context:行程"}
    ]
  },
  "next_action": {
    "kind": "supply_missing_kpis",
    "preview_cli": "python cad_pipeline.py project-guide --product-goal \"...\" --confirm-speed 20"
  }
}
```

### 新状态码

| 状态 | 含义 | next_action.kind |
|---|---|---|
| `needs_product_goal` | 没传 `--product-goal` 也没 `--design-doc` | `supply_product_goal` |
| `needs_subsystem_confirmation` | 自然语言含混 / 多类匹配 | `confirm_subsystem` |
| `not_yet_implemented` | 命中 17 个文档化但未实现类别 | `wait_for_implementation` |
| `unknown_subsystem` | 完全未识别 | `list_supported_subsystems` |
| `needs_kpi_confirmation` | 类别清晰但 KPI 缺失/含混 | `supply_missing_kpis` |
| `ready_for_cad_spec` | 一切齐备 | `run_cad_spec` |

### 状态机

```
[no input]
   └─ status: needs_product_goal
      └─ user supplies --product-goal "..."
         └─ parse → branch:
            ├─ subsystem ambiguous → needs_subsystem_confirmation
            │    └─ user adds --confirm-subsystem <name>
            │       └─ re-enter parse with subsystem fixed
            ├─ subsystem matches not_yet_implemented → terminal
            ├─ subsystem unknown → terminal (列出 supported)
            └─ subsystem clear:
               ├─ all KPIs extracted → ready_for_cad_spec
               └─ KPIs missing → needs_kpi_confirmation
                  └─ user adds --confirm-load 50 --confirm-stroke 200 ...
                     └─ re-enter parse with KPIs fixed → ready_for_cad_spec
```

---

## 解析器结构（3 层确定性词典）

### 第 1 层：子系统类别识别

**文件**：`tools/project_guide_dict/subsystem_keywords.yaml`

```yaml
lifting_platform:
  status: implemented
  primary_terms: ["升降平台", "升降台", "lifting platform", "提升台"]
  supporting_terms: ["升降", "提升", "lift", "升起"]
end_effector:
  status: implemented
  primary_terms: ["末端执行", "末端工具", "end effector", "EE"]
  supporting_terms: ["末端", "夹爪", "翻转工具", "工具切换"]
navigation:
  status: not_yet_implemented
  primary_terms: ["导航", "navigation", "SLAM"]
  supporting_terms: ["路径规划", "定位"]
# 其余 16 个 not_yet_implemented 类别（plan 阶段枚举到 yaml）：
# motion_ctrl / electrical / communication / charging / couplant / detection
# integration / output / patent / plan / power / robot_platform / safety
# software / sys_arch / budget
```

**完整 19 类清单（与 `cad/<subsystem>/` 目录一一对应）**：

| status | 数量 | 类别 |
|---|---|---|
| `implemented` | 2 | `lifting_platform`、`end_effector` |
| `not_yet_implemented` | 17 | `navigation`、`motion_ctrl`、`electrical`、`communication`、`charging`、`couplant`、`detection`、`integration`、`output`、`patent`、`plan`、`power`、`robot_platform`、`safety`、`software`、`sys_arch`、`budget` |

**匹配规则**：

- 命中任意 `primary_terms` → 直接定 `subsystem_class`
- 仅 `supporting_terms` 命中且无 primary → `subsystem_status = ambiguous` + `status = needs_subsystem_confirmation`
- 多个类的 `primary_terms` 同时命中 → `ambiguous`，按优先级排序后让用户 `--confirm-subsystem`
- 19 类全部不命中 → `subsystem_status = unknown` + 终态

### 第 2 层：KPI 抽取

**文件**：`tools/project_guide_dict/kpi_patterns.yaml`

```yaml
lifting_platform:
  load_kg:
    regex: ['(\d+(?:\.\d+)?)\s*(?:kg|公斤|千克)']
    context_terms: ["载荷", "承载", "负载", "升起", "举起", "提升", "升"]
    unit: kg
  stroke_mm:
    regex: ['(\d+(?:\.\d+)?)\s*(?:mm|毫米)', '(\d+(?:\.\d+)?)\s*(?:cm|厘米)', '(\d+(?:\.\d+)?)\s*m(?![ms])']
    context_terms: ["行程", "升高", "升程", "stroke", "travel"]
    unit: mm
    unit_normalize: {cm: 10, m: 1000, 厘米: 10, 米: 1000}
  speed_mm_s:
    regex: ['(\d+(?:\.\d+)?)\s*(?:mm/s|毫米每秒|mm·s)']
    context_terms: ["速度", "升降速度", "speed"]
    unit: mm_per_s
end_effector:
  rot_range_deg:
    regex: ['[±]?\s*(\d+(?:\.\d+)?)\s*[°度]']
    context_terms: ["翻转", "旋转", "rotation", "rotate"]
    unit: deg
  switch_time_s:
    regex: ['(\d+(?:\.\d+)?)\s*(?:s|秒)']
    context_terms: ["切换", "switch"]
    unit: s
  flange_dia_mm:
    regex: ['Φ\s*(\d+(?:\.\d+)?)', '(\d+)\s*mm\s*法兰', 'flange\s*(\d+)']
    context_terms: ["法兰", "flange"]
    unit: mm
```

**匹配规则**：

- KPI 必须 **regex 命中数字** AND **±20 字符内出现 context_terms 任一** 才算抽到
- 不满足双条件 → `kpi_missing`
- 单位归一：`200mm`/`20cm`/`0.2m` 都归到 `stroke_mm = 200`

### 第 3 层：歧义检测

- 多个 KPI 都能匹配同一数字 → 选 `context_terms` token 距离最近的
- 距离相同 → `status: ambiguous`，必须用户 `--confirm-X` 显式指定
- regex 命中但没 context_terms → 不抽，但记入 `parser_evidence` 让用户审

---

## 实现骨架

### 文件布局

新增：

```
tools/
├── product_goal_parser.py            # 3 层确定性解析器
└── project_guide_dict/
    ├── __init__.py                    # 加载 yaml 词典 + schema 校验
    ├── subsystem_keywords.yaml        # 第 1 层
    └── kpi_patterns.yaml              # 第 2 层

tests/
├── test_product_goal_parser.py        # 解析器单元测试
└── test_project_goal_guide.py         # 入口集成测试

src/cad_spec_gen/data/                 # dev_sync 镜像
└── project_guide_dict/                # 自动同步
```

修改：

```
tools/project_guide.py              # 新增 write_project_goal_guide()
cad_pipeline.py                     # CLI 加 --product-goal 等 flags
scripts/dev_sync.py                 # 把 project_guide_dict/ 加入镜像清单
docs/cad-help-guide-zh.md
docs/cad-help-guide-en.md
.claude/commands/cad-help.md
skill_cad_help_zh.md / skill.json
```

### 关键 API 签名

```python
# tools/product_goal_parser.py
from dataclasses import dataclass
from typing import Any, Literal, Mapping

@dataclass(frozen=True)
class KpiExtraction:
    kpi_name: str
    value: float | None
    unit: str | None
    evidence_token: str | None
    rule: str  # "regex+context:升" / "confirm_flag" / "ambiguous"
    status: Literal["extracted", "ambiguous", "missing"]

@dataclass(frozen=True)
class ProductGoalParseResult:
    subsystem_class: str | None
    subsystem_status: Literal["implemented", "not_yet_implemented", "ambiguous", "unknown"]
    kpis: dict[str, KpiExtraction]
    parser_evidence: list[dict[str, Any]]
    raw_text: str

def parse_product_goal(
    *,
    text: str,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float] | None = None,
    dictionary: ProductGoalDictionary | None = None,  # 注入便于测试
) -> ProductGoalParseResult: ...

def load_dictionary(*, dict_root: Path | None = None) -> ProductGoalDictionary: ...
```

```python
# tools/project_guide.py 新增
def write_project_goal_guide(
    *,
    project_root: Path,
    product_goal: str,
    design_doc: Path | None = None,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float] | None = None,
) -> dict[str, Any]: ...
```

### CLI 接入（`cad_pipeline.py`）

```python
parser.add_argument("--product-goal", type=str, help="自然语言产品目标")
parser.add_argument("--confirm-subsystem", type=str)
# 显式 KPI confirm flags（lifting + EE 共 6 个）
parser.add_argument("--confirm-load", type=str, help="升降平台载荷 (kg)")
parser.add_argument("--confirm-stroke", type=str)
parser.add_argument("--confirm-speed", type=str)
parser.add_argument("--confirm-rot-range", type=str)
parser.add_argument("--confirm-switch-time", type=str)
parser.add_argument("--confirm-flange-dia", type=str)
```

### `--confirm-X` flag 单位语义

每个 `--confirm-X` 接受两种形式：

- **裸数字**（推荐）：`--confirm-load 50` → 默认本 KPI 标准单位（见下表）
- **带单位**（同 regex 解析）：`--confirm-load 50kg`、`--confirm-stroke 0.2m`、`--confirm-rot-range ±135°` → 走单位归一

| flag | 默认单位 | 接受的单位别名 |
|---|---|---|
| `--confirm-load` | kg | kg / 公斤 / 千克 |
| `--confirm-stroke` | mm | mm / cm / m / 毫米 / 厘米 / 米 |
| `--confirm-speed` | mm/s | mm/s / mm·s |
| `--confirm-rot-range` | ° | ° / 度（前缀 `±` 接受但只取数值） |
| `--confirm-switch-time` | s | s / 秒 |
| `--confirm-flange-dia` | mm | mm（前缀 `Φ` 接受但只取数值） |

无法解析时（如 `--confirm-load abc` / `--confirm-load 50ml`）→ 写 `kpi_extracted[load_kg].status = "ambiguous"` + `parser_evidence` 标 `confirm_flag_invalid`，让用户改正。

---

## 测试矩阵

### `tests/test_product_goal_parser.py`（解析器单元测试，~15 例）

1. **subsystem class 识别**：6 例 positive + 6 例 negative + 4 例 ambiguous（仅 supporting_terms）
2. **KPI 抽取双条件**：8 例 positive（context+regex 都命中）+ 4 例 negative（仅 regex 没 context）
3. **单位归一**：`200mm` / `20cm` / `0.2m` 都归到 `stroke_mm = 200`
4. **歧义检测**：`"50kg 平台、行程 50mm"` 中两个 50 各归各位
5. **17 个 not_yet_implemented**：每类至少 1 例 positive
6. **unknown_subsystem**：3 例（如"做个机器人"）
7. **confirm_kpis 覆盖**：parser 抽到 50，confirm_kpis 传 100 → 100 胜出 + evidence 标 `confirm_flag`
8. **confirm_subsystem 强制**：parser 识别成 EE，confirm 传 lifting → 强制 lifting 并重新抽 lifting 的 KPI

### `tests/test_project_goal_guide.py`（端到端入口测试，~8 例）

1. `--product-goal "..."` 写 PROJECT_GUIDE.json 到正确路径（沿用 `path_policy` 守护）
2. 5 种 status 各至少 1 例（needs_product_goal / needs_subsystem / not_yet_implemented / unknown / needs_kpi / ready）
3. `next_action.preview_cli` 永不带 `--confirm` 之外的危险 flag（沿用 `_safe_cli_token`）
4. 词典 yaml 缺失 / 格式错 → entry 函数抛 `RuntimeError`，不静默 fallback
5. `parser_evidence` 字段对每个抽取的 KPI 都有条目，可审计
6. `--confirm-X` 与自然语言冲突时 confirm 胜出（确定性优先于解析）
7. `entry_mode = "product_goal"` 永远写入（与现有 `--from-design-doc` 区分）
8. 安装版镜像 `src/cad_spec_gen/data/project_guide_dict/*.yaml` 有 `dev_sync --check` 守护

### `tests/test_project_guide.py`（已有，扩展）

- 不破坏现有 16 个测试
- 新加 2 例：`--product-goal` 和 `--from-design-doc` 都不传时 status 仍是 `needs_subsystem_confirmation`（兼容）

---

## TDD 节奏（按项目 CLAUDE.md）

1. 词典 yaml 先写（含 schema 校验测试）→ 红测：词典加载报错
2. `parse_product_goal` 红测：subsystem 识别 → 实现层 1
3. KPI 抽取红测 → 实现层 2
4. 歧义检测红测 → 实现层 3
5. `write_project_goal_guide` 红测：写文件 → 实现
6. CLI flags 红测 → 实现接入
7. dev_sync 镜像红测 → 加入镜像清单
8. 文档 / skill metadata 红测 → 更新文档

---

## 北极星 5 gate 检查

| gate | 是否过 | 说明 |
|---|---|---|
| 零配置 | ✅ | 词典随安装版镜像同步，无外部依赖 |
| 稳定可靠 | ✅ | 纯确定性 regex/词典，无 LLM 不确定性；`needs_user_input` 边界明确 |
| 结果准确 | ✅ | 双条件抽取 + 歧义显式化；解析错就标缺失，不静默猜 |
| SW 装即用 | n/a | 本 spec 与 SW 无关，不破坏现有 SW 路径 |
| 傻瓜式操作 | ✅ | 一句自然语言 + 1-3 个 `--confirm-X` flag = 启动管线；single-round batch |

---

## 边界与约束

- **AI 不能补 CAD 缺件**：解析器只识别已知词典；漏识别 → `needs_user_input`，绝不静默猜
- **入口纯只读**：不生成 `CAD_SPEC.md` / `params.py`，不动 `active_run_id`，不调 resolver
- **Windows-only**：词典中文优先，英文别名为辅；不假设 Linux/macOS 行为
- **无 LLM / 无网络**：所有解析在本地完成；不接 cloud API
- **可审计性**：`parser_evidence` 字段必填，让用户能验证解析对不对，发现错就用 `--confirm-X` 覆盖
- **dev_sync**：词典 yaml 必须纳入安装版镜像，`dev_sync --check` 守护
- **YAGNI**：不收 14-30 个全量 CAD 参数；只收 1-3 个外行表达层；剩余交给现有 supplementation
