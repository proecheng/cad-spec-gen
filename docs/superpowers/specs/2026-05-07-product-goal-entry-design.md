# 设计文档：Phase 1 新用户入口前移到产品目标自然语言模式

**日期**：2026-05-07
**作者**：brainstorming session
**rev**：3（实地核验代码后修订：4 数据漂移 + 3 函数一致性 + 3 管线融合 + 1 路径全闭）
**目标**：把 `project-guide` 入口前移一步——外行用户不写设计文档也能启动，只用一句产品目标自然语言（如"做一个升 50kg 的升降平台"），系统识别子系统类别 + 抽取顶层 KPI + 标记缺失项，让用户用 `--confirm-X` flag 一次性补齐后进入既有 Phase 1 流程

## rev 2 → rev 3 修订记录（2026-05-07）

实地 grep 现有代码后发现 spec 与代码漂移，11 项一次闭合：

- **D-1**：`entry_mode` 名 `from_design_doc` → `design_doc`（与现有 `tools/project_guide.py:33` 对齐）
- **D-2**：PyYAML 不是 base install 依赖（仅在 `parts_library` extras）→ **改用 JSON 字典**（`subsystem_keywords.json` + `kpi_patterns.json`），不引入新依赖
- **D-3**：补齐既有 PROJECT_GUIDE.json schema 必要字段（`schema_version` / `generated_at` / `ordinary_user_message` / `mutates_pipeline_state` / `does_not_scan_directories` / `artifacts.project_guide`）
- **D-4**：`_safe_cli_token` 显式声明从 `tools/project_guide.py:_safe_cli_token` 复用（**不**复用 photo3d_actions / photo3d_autopilot 那两个版本）
- **F-1**：`write_project_goal_guide` 签名对齐现有 `write_project_entry_guide`（首参 `project_root`，必带 `output_path` keyword）
- **F-2**：明确新增 `_subsystem_candidates_for_product_goal` 函数（与现有 `_subsystem_candidates_for_design_doc` 平行，不修改后者）
- **F-3**：补 `cmd_project_guide` dispatch 扩展伪代码（在现有 if/elif 链加新分支）
- **M-1**：声明新 `next_action.kind` 值（`supply_product_goal` / `supply_missing_kpis` / `wait_for_implementation` / `list_supported_subsystems` / `run_cad_spec`）是**文档化字符串**，不被任何现有产线代码自动 dispatch
- **M-2**：schema_version 保持 1（向后兼容加字段）；新增 status 值不 bump（既有 reader 都通过 `dict.get(status)` 不做 enum 限制）
- **M-3**：新模式必保留 `mutates_pipeline_state=false` / `does_not_scan_directories=true` 不变量字段
- **P-1**：`tools/project_guide_dict/` 子目录参考现有 `tools/hybrid_render/` import 风格

---

## rev 1 → rev 2 修订记录（2026-05-07）

按 4 角色（机械设计 / 3D 建模 / 程序员 / 潜在用户）对抗审查后修订：

- **C-1（机械+3D 建模）**：KPI ↔ CAD 参数对应关系全部显式列表（§KPI 映射表）；说清 `load_kg` 是 **用户表达层**，下游 cad-spec 才决定填 `PARAM_L25` / `PARAM_L27`；`flange_dia_mm → FLANGE_DIA = FLANGE_BODY_OD`（同一外径）
- **C-2（3D 建模）**：lifting_platform KPI 替换 `speed_mm_s` → `platform_size_mm`（外行更可能说外形包络）
- **C-3（3D 建模）**：跨子系统统一 KPI 选择原则——3 槽：`capability_1` / `capability_2` / `envelope`
- **C-4（程序员）**：regex multi-pattern 优先级显式声明（"最具体单位优先"，mm > cm > m）
- **C-5（程序员）**：距离度量定义 NFKC normalize 后的 char index；不同 KPI 的数字共享允许（按各自 context_terms 距离独立判定）
- **C-6（程序员）**：PROJECT_GUIDE.json schema 向后兼容——所有新字段 optional + 现有 16 例测试不破坏的回归测试
- **C-7（潜在用户）**：加 §扩展指南——加新子系统 / 新 KPI 的 minimum file checklist
- **I-1～I-7（KPI 选择类，已并入 C-1～C-3）**：通过引入"用户表达层 vs CAD 参数层"的双层抽象 + 跨子系统 3 槽统一原则解决
- **附带（程序员）**：unicode NFKC normalize 策略 / yaml schema 工具选型（pyyaml + dataclass 自校）/ preview_cli 转义复用 `_safe_cli_token` / CLI flag 与 KPI key 显式映射表

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

**并存，不替代**。`cmd_project_guide` dispatch 扩展（rev 3 显式）：

```python
def cmd_project_guide(args):
    if getattr(args, "product_goal", None):                 # 新增分支（最高优先级）
        report = write_project_goal_guide(
            PROJECT_ROOT,
            args.product_goal,
            design_doc=getattr(args, "design_doc", None),
            confirmed_subsystem=getattr(args, "confirm_subsystem", None),
            confirmed_kpis=_collect_confirmed_kpis(args),  # helper 解析 6 个 --confirm-X
            output_path=getattr(args, "output", None),
        )
    elif getattr(args, "from_design_doc", False):          # 既有
        report = write_project_entry_guide(...)            # 不改
    elif args.subsystem:                                   # 既有
        report = write_project_guide(...)                  # 不改
    else:
        log.error("--product-goal, --from-design-doc, or --subsystem is required")
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return command_return_code_for_project_guide(report)
```

**`entry_mode` 取值对齐现有代码**（rev 3 修正）：

| 模式 | `entry_mode` 值 | 入口函数 |
|---|---|---|
| 既有：`--from-design-doc` | `design_doc`（**非** `from_design_doc`） | `write_project_entry_guide` |
| 既有：`--subsystem` | `subsystem` | `write_project_guide` |
| **新增**：`--product-goal` | `product_goal` | `write_project_goal_guide` |

### `PROJECT_GUIDE.json` 新字段

扩展现有 schema（rev 3：补齐既有字段；新模式必保留 `mutates_pipeline_state` / `does_not_scan_directories` 不变量）：

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-07T...",
  "entry_mode": "product_goal",
  "status": "needs_kpi_confirmation",
  "ordinary_user_message": "请补充缺失的 KPI（行程外形等），用 --confirm-X flag 重跑",
  "mutates_pipeline_state": false,
  "does_not_scan_directories": true,
  "artifacts": {
    "project_guide": ".cad-spec-gen/project-guide/PROJECT_GUIDE.json"
  },
  "product_goal": {
    "text": "做一个能升 50kg、行程 200mm 的升降平台",
    "subsystem_class": "lifting_platform",
    "subsystem_status": "implemented",
    "kpi_extracted": {"load_kg": 50, "stroke_mm": 200},
    "kpi_missing": ["platform_size_mm"],
    "parser_evidence": [
      {"token": "升降平台", "matched": "subsystem_class", "rule": "primary_terms[0]"},
      {"token": "50kg", "matched": "load_kg", "rule": "regex+context:升"},
      {"token": "200mm", "matched": "stroke_mm", "rule": "regex+context:行程"}
    ]
  },
  "next_action": {
    "kind": "supply_missing_kpis",
    "preview_cli": "python cad_pipeline.py project-guide --product-goal \"...\" --confirm-platform-size 350x230"
  }
}
```

### 新状态码

| 状态 | 含义 | next_action.kind |
|---|---|---|
| `needs_product_goal` | 没传 `--product-goal` 也没 `--design-doc` | `supply_product_goal` |
| `needs_subsystem_confirmation` | 自然语言含混 / 多类匹配 | `confirm_subsystem`（**复用既有 entry_guide 同名值**） |
| `not_yet_implemented` | 命中 17 个文档化但未实现类别 | `wait_for_implementation` |
| `unknown_subsystem` | 完全未识别 | `list_supported_subsystems` |
| `needs_kpi_confirmation` | 类别清晰但 KPI 缺失/含混 | `supply_missing_kpis` |
| `ready_for_cad_spec` | 一切齐备 | `run_cad_spec` |

**rev 3 显式声明**：`next_action.kind` 是**文档化字符串**——产线代码（cad-spec、build、render、photo3d、enhance 等下游）**不会**自动 dispatch 这些值。它们只是给用户和大模型看的"建议"。所以新增这些值不会破坏任何现有路径，也不必新增任何 dispatcher。

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

**文件**：`tools/project_guide_dict/subsystem_keywords.json`（rev 3：改 JSON，避免引入 PyYAML 到 base install）

```yaml
# 以下例为 yaml 写法便于阅读；实际文件是等价 JSON
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
# 其余 16 个 not_yet_implemented 类别（plan 阶段枚举到 json）：
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

**文件**：`tools/project_guide_dict/kpi_patterns.json`（rev 3：改 JSON）

```yaml
# 以下例为 yaml 写法便于阅读；实际文件是等价 JSON
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
  platform_size_mm:
    regex: ['(\d+)\s*[x×]\s*(\d+)\s*(?:mm|毫米)?']    # 抓两个数字
    context_terms: ["平台", "platform", "尺寸", "外形", "包络", "面积"]
    unit: mm
    value_shape: pair                                  # tuple (W, D)
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

### 解析器歧义优先级（rev 2 显式声明）

**输入预处理**（必做，按顺序）：

1. `unicodedata.normalize("NFKC", text)` — 全角数字/全角空格/Φ 全角统一
2. 全部小写化（仅英文部分）

**regex multi-pattern 优先级**：

- 同一 KPI 列多个 regex 时，按 json 数组中**声明顺序短路匹配**（最具体单位优先）
- 例：`stroke_mm` 列 `[mm, cm, m]` 三个 regex
  - 输入 `200mm` → 第 1 个命中 → `stroke_mm = 200`
  - 输入 `20cm` → 第 1 个不命中（因 `cm` 不含 `mm` 模式）→ 第 2 个命中 → 归一 `stroke_mm = 200`
  - 输入 `0.2m` → 前 2 个不命中 → 第 3 个命中（带 `(?![ms])` 负向预查保证不撞 `ms`/`mm`）→ 归一 `stroke_mm = 200`
- 同一 token 命中多个 regex → 取**第一个命中**（不取最长匹配，避免 `200cm` 被 `m` regex 也命中产生歧义）

**距离度量**：

- 单位是 NFKC normalize 后的 **char index**（不是 byte / token）
- 距离 = `min(|context_pos - number_start|, |context_pos - number_end|)`
- ±20 char 是软窗口；超出窗口仍允许，但 `parser_evidence` 标 `weak`

**数字共享规则**（rev 2 明确）：

- 不同 KPI 之间允许共享同一 token：`"50kg 平台 + 升 50mm"` 中两个 50 各归各位（一个匹配 load 因近 "kg"，一个匹配 stroke 因近 "mm"）——**不算歧义**
- 真冲突 = 同一数字 + 多个 KPI 都能匹配 + context_terms 距离相等：`"50 升降"` 中 `50` 既能算 load（"升"在 context）又能算 stroke（"升"在 stroke 的 "升高/升程"）→ `status: ambiguous`，让用户用 `--confirm-X` 显式

---

## KPI ↔ CAD 参数映射（rev 2 新增）

**核心抽象**：KPI 是**用户表达层**，CAD 参数是**实现层**。两层分离：

- 入口模式（本 spec）只输出 `kpi_extracted.<kpi_name> = <value>`，**不指定 CAD 参数**
- 下游 cad-spec / supplementation 流程根据用户进一步信息决定填哪个 CAD 参数
- 一对多 / 一对一 / 含混都允许，由下游处理

**映射表**：

| KPI 名 | CAD 参数对应 | 映射类型 | 说明 |
|---|---|---|---|
| `load_kg` | `PARAM_L25` 或 `PARAM_L27` | 一对多 | 工件载重 vs 平台额定载荷由下游决定（CAD_SPEC 历史债，不在本 spec 修复范围） |
| `stroke_mm` | `SENSOR_STROKE` | 一对一 | 行程下极限到上极限距离 |
| `platform_size_mm` | `(PARAM_L394, PARAM_L395)` | 一对多（pair） | W × D 平台尺寸；下游可能拆 X/Y |
| `rot_range_deg` | `ROT_RANGE` | 一对一 | 旋转范围（±角度由 CAD_SPEC 公差列承载） |
| `switch_time_s` | `SWITCH_T` | 一对一 | 切换时间，影响 motor torque selection |
| `flange_dia_mm` | `FLANGE_DIA = FLANGE_BODY_OD` | 一对一 | 圆盘外径（CAD_SPEC §1 简化命名 §3 完整命名，同一物理量） |

**含混标注**（已知 limitation，不阻塞 rev 2）：

- `load_kg` 工程语义不明（额定/动/静/含安全系数）→ 入口层不区分，原样向下传；cad-spec supplementation 阶段补充
- `platform_size_mm` 是平台外形包络还是工作台面有效面积 → 同上，原样向下传

---

## 跨子系统统一 KPI 选择原则（rev 2 新增）

为保证未来加新子系统时 KPI 选择有据可依，确立 **3 槽统一原则**：

| 槽 | 含义 | lifting_platform | end_effector |
|---|---|---|---|
| `capability_1` | 主要功能能力（最显眼的性能数字） | `load_kg` 载荷 | `rot_range_deg` 翻转范围 |
| `capability_2` | 次要功能能力（功能完整性） | `stroke_mm` 行程 | `switch_time_s` 切换时间 |
| `envelope` | 外形/接口包络（用户可视化的尺寸） | `platform_size_mm` 平台尺寸 W×D | `flange_dia_mm` 法兰外径 |

**新加子系统时的选择义务**：

- 必须填齐 3 槽
- 每槽的 KPI 必须能用**单条自然语言短语表达**（"50kg 载荷" / "翻转 ±135°"），且**单位明确**
- 每槽的 KPI 必须**显式映射**到 CAD_SPEC 的某/某些参数（一对一、一对多、含混都允许，但映射类型必须声明）
- 不允许槽留空——如果某子系统真的没有该槽对应概念（如 software 子系统没有 envelope），子系统应被标 `not_yet_implemented` 或 `unknown`，而不是缺槽实现

**3 槽外维度的处理**（rev 2 显式声明 YAGNI 边界）：

工程上有大量 KPI 不进 3 槽——下表举例，**这些维度由现有 cad-spec supplementation 流程承接，不在入口层收集**：

| 维度 | lifting_platform 例 | end_effector 例 | 为什么不在入口层 |
|---|---|---|---|
| 精度 | POS_ACC=0.1mm（重复定位精度） | SPRING_POS_ACC=0.2°（弹簧定位精度） | 用户语言里很少提，提了也单位含糊（"高精度"≠数字） |
| 占空比 / 工时 | PARAM_L470=10h | — | 不直接驱动几何，属选型层（电机连续工作能力） |
| 驱动方式 | 电动 / 气动 | 电动 / 气动 / 液压 | 离散值不是数字，不适合 regex 抽取 |
| 工件数 / 工位数 | — | 单工位 vs 多工位翻转 | 同上 |
| 速度 | SPEED=20mm/s | — | 不直接驱动几何，属 motor selection 层 |

入口层的承诺收窄到"用户最易表达 + 数字化 + 直接对应外形包络或主能力"的 3 项；其余在 cad-spec 阶段通过现有 supplementation 机制（`DESIGN_REVIEW.json` warning/critical 门禁）补充。

---

## PROJECT_GUIDE.json 向后兼容（rev 2 新增）

**约束**：

- 所有新字段（`entry_mode`、`product_goal.*`）在 schema 中必须 **optional**
- `entry_mode` 缺省值是 `"legacy"`（既有 `--from-design-doc` / `--subsystem` 路径写入）
- 现有 16 例 `tests/test_project_guide.py` **必须不修改不破坏**（plan 第 0 task 必跑红测验证）
- 所有 reader（`_provider_choice`、`_subsystem_candidates_for_design_doc`、`build_model_quality_summary` 等）对 `product_goal` 字段的访问都必须 `dict.get(..., None)` 或 `try/except KeyError`

**回归测试**：

- `test_project_guide.py` 既有 16 例全部跑过且不修改
- 新加 1 例：旧 PROJECT_GUIDE.json（无 `entry_mode` / `product_goal` 字段）能被新代码读取并写入正确状态

---

## 扩展指南（rev 2 新增）

潜在用户加新子系统的最小 file checklist：

| 步骤 | 文件 | 改动 |
|---|---|---|
| 1 | `tools/project_guide_dict/subsystem_keywords.json` | 加 `<new_subsystem>` 顶层 key（status / primary_terms / supporting_terms） |
| 2 | `tools/project_guide_dict/kpi_patterns.json` | 加 `<new_subsystem>` 顶层 key（3 槽 KPI：capability_1 / capability_2 / envelope） |
| 3 | `cad_pipeline.py` | 加对应 `--confirm-<kpi>` flag（如新 KPI 名是 `xxx_unit` → flag 是 `--confirm-xxx`） |
| 4 | `tests/test_product_goal_parser.py` | 加 positive + negative + 1 ambiguous case |
| 5 | `tests/test_project_goal_guide.py` | 加 e2e 1 例（新子系统从识别到 ready_for_cad_spec） |
| 6 | `cad/<new_subsystem>/` | 加目录 + `params.py` + `CAD_SPEC.md`（status 才能从 `not_yet_implemented` 升 `implemented`） |
| 7 | `scripts/dev_sync.py --check` | 跑通确保安装版镜像无漂移 |

**说明**：

- 步骤 1-5 让入口层识别新子系统，**status 仍是 `not_yet_implemented`**
- 步骤 6 真正补齐 CAD 实现后，更新步骤 1 的 `status: implemented`
- 步骤 7 是项目级硬约束，每次改字典 json 必跑

**KPI 命名规约**：

- 蛇形小写：`load_kg`、`platform_size_mm`、`rot_range_deg`
- 单位后缀必须是 SI 基本单位或派生单位的小写形式：`kg` / `mm` / `s` / `deg`、`mm_per_s`
- 复合 KPI（如 platform_size 是 W×D pair）用单位后缀表示主要单位，`value_shape: pair` 在 json 显式声明

---

## 实现骨架

### 文件布局

新增：

```
tools/
├── product_goal_parser.py            # 3 层确定性解析器
└── project_guide_dict/
    ├── __init__.py                    # 加载 json 词典 + dataclass 自校验
    ├── subsystem_keywords.json        # 第 1 层
    └── kpi_patterns.json              # 第 2 层

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
# tools/project_guide.py 新增（rev 3：签名对齐现有 write_project_entry_guide 风格）
def write_project_goal_guide(
    project_root: str | Path,           # 位置参数（与 write_project_entry_guide 对齐）
    product_goal: str,                  # 位置参数
    *,
    design_doc: str | Path | None = None,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float | tuple[float, float]] | None = None,  # tuple 支持 platform_size pair
    output_path: str | Path | None = None,  # 与现有 entry_guide 一致
) -> dict[str, Any]: ...

# 新辅助函数（与现有 _subsystem_candidates_for_design_doc 平行，不修改后者）
def _subsystem_candidates_for_product_goal(
    parse_result: ProductGoalParseResult,
) -> list[dict[str, Any]]: ...
```

### CLI 接入（`cad_pipeline.py`）

```python
parser.add_argument("--product-goal", type=str, help="自然语言产品目标")
parser.add_argument("--confirm-subsystem", type=str)
# 显式 KPI confirm flags（lifting + EE 共 6 个）
parser.add_argument("--confirm-load", type=str, help="升降平台载荷 (kg)")
parser.add_argument("--confirm-stroke", type=str)
parser.add_argument("--confirm-platform-size", type=str, help="升降平台尺寸 W×D (mm)，例 '350x230'")
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
| `--confirm-platform-size` | mm × mm | `350x230` / `350×230` / `350x230mm` |
| `--confirm-rot-range` | ° | ° / 度（前缀 `±` 接受但只取数值） |
| `--confirm-switch-time` | s | s / 秒 |
| `--confirm-flange-dia` | mm | mm（前缀 `Φ` 接受但只取数值） |

无法解析时（如 `--confirm-load abc` / `--confirm-load 50ml`）→ 写 `kpi_extracted[load_kg].status = "ambiguous"` + `parser_evidence` 标 `confirm_flag_invalid`，让用户改正。

### CLI flag ↔ KPI key 显式映射表（rev 2 新增）

CLI flag 名（kebab-case，去单位后缀）≠ KPI key 名（snake_case，含单位后缀）。**必须有显式 mapping，不让代码读者自己猜**。

| CLI flag | KPI key | 子系统 | 槽 |
|---|---|---|---|
| `--confirm-load` | `load_kg` | lifting_platform | capability_1 |
| `--confirm-stroke` | `stroke_mm` | lifting_platform | capability_2 |
| `--confirm-platform-size` | `platform_size_mm` | lifting_platform | envelope |
| `--confirm-rot-range` | `rot_range_deg` | end_effector | capability_1 |
| `--confirm-switch-time` | `switch_time_s` | end_effector | capability_2 |
| `--confirm-flange-dia` | `flange_dia_mm` | end_effector | envelope |
| `--confirm-subsystem` | `<subsystem_class>` | (跨子系统) | meta |

实现层这张表存在 `tools/project_guide_dict/__init__.py`，作为 `CLI_FLAG_TO_KPI_KEY` 常量；`cad_pipeline.py` argparse 解析后查表把 args 转 KPI dict 给 parser。

### 实现层关键约束（rev 2 新增）

| 约束 | 说明 | 复用现有资产 |
|---|---|---|
| Unicode normalize | 所有用户输入 NFKC normalize 后再 regex（含 `--product-goal` text 和 `--confirm-X` value） | `tools/project_guide.py` 已 `import unicodedata`，复用 |
| 字典加载 | `json.loads(Path(...).read_text("utf-8"))` + dataclass 自校（`ProductGoalDictionary` 加 `__post_init__` 校验 schema） | rev 3 改：避免引入 PyYAML 到 base install（PyYAML 仅在 `parts_library` extras） |
| Path 越界 | 所有路径写入走 `assert_within_project` | `tools/path_policy.py` 已存在 |
| 文件原子写 | PROJECT_GUIDE.json 走 `write_json_atomic` | `tools/contract_io.py` 已存在 |
| Shell 转义 | preview_cli 中的 user text 必须经 `_safe_cli_token` 校验；含特殊字符 → 写 `next_action.preview_cli_unsafe = true` 并降级为不带 user text 的通用提示 | **复用 `tools/project_guide.py:624 _safe_cli_token`**（rev 3：明确不复用 `tools/photo3d_actions.py` / `tools/photo3d_autopilot.py` 的同名 duplicate） |

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
4. 词典 json 缺失 / 格式错 → entry 函数抛 `RuntimeError`，不静默 fallback
5. `parser_evidence` 字段对每个抽取的 KPI 都有条目，可审计
6. `--confirm-X` 与自然语言冲突时 confirm 胜出（确定性优先于解析）
7. `entry_mode = "product_goal"` 永远写入（与现有 `--from-design-doc` 区分）
8. 安装版镜像 `src/cad_spec_gen/data/project_guide_dict/*.json` 有 `dev_sync --check` 守护

### `tests/test_project_guide.py`（已有，扩展）

- 不破坏现有 16 个测试
- 新加 2 例：
  - `--product-goal` 和 `--from-design-doc` 都不传时 status 仍是 `needs_subsystem_confirmation`（兼容）
  - 旧 PROJECT_GUIDE.json（无 `entry_mode` / `product_goal` 字段）能被新代码读取（向后兼容回归测试）

### rev 2 新增测试

**P-C1 / P-C2 解析器歧义优先级**（加入 `test_product_goal_parser.py`）：

1. regex multi-pattern 短路：`200mm` / `20cm` / `0.2m` 都归一 `stroke_mm = 200`，且 `parser_evidence.rule` 显示命中第几条 regex
2. 距离度量：`"50kg 平台 升 50mm"` 中两个 50 各归各位（不算冲突）
3. 真冲突：`"50 升降"` 中单个 50 + "升" 同时是 load 和 stroke 的 context → status `ambiguous`
4. NFKC：`"100kg" / "１００kg" / "100ｋｇ"` 都归到 `load_kg = 100`
5. preview_cli 转义：含 `"` / newline 的 product_goal → `preview_cli_unsafe = true` 不直接拼

**C-7 扩展指南可执行性**（加入 `test_project_goal_guide.py`）：

6. 加一个 `mock_subsystem`（仅在测试中存在的 json 块）→ parser 能识别它 + 走完 needs_kpi → ready 流程，验证扩展路径可行

**KPI ↔ CAD 参数映射约束**（加入 `test_product_goal_parser.py`）：

7. `kpi_extracted` 输出**绝不**含 CAD 参数名（`PARAM_L25` / `SENSOR_STROKE`）—— 入口层和 CAD 层严格分离

---

## TDD 节奏（按项目 CLAUDE.md）

1. 词典 json 先写（含 dataclass 自校验测试）→ 红测：词典加载报错
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
- **dev_sync**：词典 json 必须纳入安装版镜像，`dev_sync --check` 守护
- **YAGNI**：不收 14-30 个全量 CAD 参数；只收 1-3 个外行表达层；剩余交给现有 supplementation
