# product-goal 多轮渐进确认设计文档（Phase 1 入口前移 — A）

**作者**：proecheng
**日期**：2026-05-09
**状态**：spec 待审
**前置 spec**：`2026-04-26-product-goal-design.md`（v2.25.0 已发布；`--product-goal` 一次说全模式）
**关联**：`project_current_status.md` 后续工作队列 #5"Phase 1 入口继续前移"

---

## 修订历史

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-05-09 | 初稿（brainstorm 4 决策点收敛后落盘）|
| 1.1 | 2026-05-09 | Task 4 implementer 实测发现 spec §3.3 break-change 描述与 v2.25.0 实际不符（v2.25.0 `command_return_code_for_project_guide` line 195 已经把 `needs_kpi_confirmation` 放在 0-set 中）；删除 §1.4 / §2.3 / §3.3 / §5.3 / §7.3 / §9.1 / §10 DoD #3 的 break-change 标记 + §7.3 整段重写为"v2.31.0 无 break-change（仅扩展异步多轮模式）"|

---

## 1. 背景与北极星对齐

### 1.1 v2.25.0 现状与外行用户痛点

v2.25.0 已落 `cad-spec-gen --product-goal "<自然语言>"` 入口；3 层确定性识别（19 类子系统 + 6 KPI + 歧义检测）+ 7 状态机。

**外行用户痛点**：
- ❌ **必须一次说全**：业务目标 + 子系统类别 + 全部 KPI（lifting=load_kg/stroke_mm/platform_size_mm）
- ❌ **缺一个 KPI 就 reject**：跳到 needs_kpi_confirmation 状态，用户重打整句
- ❌ **无渐进式补全**：用户首次只想说"做升降平台"，必须在第一句就知道还要 3 个 KPI 怎么填

### 1.2 Phase 1 入口前移目标

让外行用户**渐进式补全**：第一次说大方向，系统主动追问 KPI；用户每次答 1+ 项；系统记忆已答项，最后所有 KPI 齐了进入 ready_for_cad_spec。

### 1.3 北极星 5 gate 对齐

| Gate | 提升点 |
|---|---|
| 零配置 | 状态文件写 cwd；不引入新 home dir 配置 |
| 稳定可靠 | 状态字段完全确定性合并；round 计数器防死循环；错误路径不污染 state |
| 结果准确 | parse_product_goal 接口完全复用（不改解析层）；--answer 严格 KPI schema 校验 |
| SW 装即用 | 无 SW 涉及 |
| 傻瓜式操作 | 不必一次说全；外行用户被系统引导逐项补全 |

### 1.4 已收敛决策点（brainstorm session 摘要）

- **scope**：仅 A 多轮渐进确认；B 项目向导记忆 / C 类别扩展（19→30+）推迟独立 PR（C 是 YAGNI；B 看 A 上线后用户重复跑频率）
- **交互模式**：异步状态机 + `--resume` flag（不阻塞 stdin；CI / LLM 助手代填友好；与现有 --from-design-doc / --subsystem 模式一致）
- **状态文件位置**：`./PROJECT_GOAL_STATE.json`（cwd；project-local；避免 chicken-egg：subsystem 还未确认时 active run dir 还不存在）
- **cli 入口语义**：`--product-goal` 与 `--resume` 共存且互斥；`--product-goal` 不全时进入异步多轮模式（写 state + exit=0）；`--resume --answer key=value` 续答（可重复传多 --answer）
- **break-change**：**v2.31.0 无 break-change**（spec rev 1.1 修订）。Task 4 implementer 实测：v2.25.0 `command_return_code_for_project_guide` 已经把 `needs_kpi_confirmation` 放在 0-set 中（`tools/project_guide.py` line 195）；本 PR 仅扩展异步多轮模式（写 state file + 改造 ordinary_user_message），不改 exit code 行为

---

## 2. 范围与非目标

### 2.1 范围（in-scope）

1. 新建 `tools/product_goal_state.py` 模块：`PROJECT_GOAL_STATE.json` schema + `read_state` / `write_state` / `delete_state` / `validate_answer` helper
2. 改 `cad_pipeline.py` parser：加 `--resume` `--answer key=value (可重复)` flag；`--resume` 与 `--product-goal` argparse mutually_exclusive
3. 改 `cad_pipeline.py:cmd_project_guide`（约 line 3700）：加 --resume 路径分支（读 state → 合并 --answer → 调 parse_product_goal）
4. 改 `tools/project_guide.py:write_project_goal_guide`：缺 KPI 时**先写 state file**；ordinary_user_message 改为引导加 --resume；exit code 不变（v2.25.0 已经返 0）
5. 改 `tools/project_guide.py:command_return_code_for_project_guide`：needs_kpi_confirmation 改 0；ready_for_cad_spec 时若有 state file 顺手清理
6. 加测试：单元（state helper）+ 集成（cli --resume 完整流程）+ 回归守门（v2.25.0 一次说全行为不变）
7. 文档：`docs/PROGRESS.md` v2.31.0 入口 + README 用法示例 + `docs/cad-jury-config.md` 不动（无关）

### 2.2 非目标（out-of-scope）

- ❌ B 项目向导记忆（跨 session 持久化已确认子系统/KPI）：推到独立 PR；先看 A 上线后用户重复跑频率
- ❌ C 类别扩展（19→30+）：YAGNI；现 19 类已覆盖 robotic/automation 主流；等用户实际 unknown_subsystem 反馈再扩
- ❌ 不改 `parse_product_goal` 接口（v2.25.0 已有 confirmed_kpis 参数直接复用）
- ❌ 不改 19 类子系统词典 / 6 KPI patterns（不动 dictionary）
- ❌ 不引入 stdin 同步交互（异步状态机一选）
- ❌ 不引入 home dir 配置（state 写 cwd）
- ❌ 不动 jury / handoff / autopilot 等 v2.27.0+ cli

### 2.3 兼容性承诺

- v2.25.0 一次说全行为完全保持（缺 KPI 时**唯一变化**：多写一个 state file + ordinary_user_message 改为引导 --resume；exit code 不变，v2.25.0 已经返 0）
- v2.25.0 19 个 product_goal 测试全 PASS
- `parse_product_goal()` 公开 API 完全保持
- `PROJECT_GUIDE.json` schema 不升 version；新 status 值不引入

---

## 3. 架构

### 3.1 上下文图

```
用户首次跑（一次说全 — v2.25.0 行为保持）：
$ cad-spec-gen --product-goal "做升 50kg 行程 800mm 600x600 平台升降平台"
        │
        ▼
parse_product_goal → subsystem + 全部 KPI 齐
        │
        ▼ missing_kpis=[]
write_project_goal_guide → PROJECT_GUIDE.json (status=ready_for_cad_spec)
不写 state；exit=0；用户继续跑 spec 生成

用户首次跑（不全 — NEW 渐进路径）：
$ cad-spec-gen --product-goal "做升降平台"
        │
        ▼
parse_product_goal → kpis={} / missing=[load_kg, stroke_mm, platform_size_mm]
        │
        ▼ missing_kpis ≠ []
[NEW] write_state(./PROJECT_GOAL_STATE.json, ...)
write_project_goal_guide → PROJECT_GUIDE.json (status=needs_kpi_confirmation)
ordinary_user_message = "下一步：cad-spec-gen --resume --answer load_kg=50"
exit=0（v2.25.0 已经返 0；本 PR 不改 exit code）

用户续答：
$ cad-spec-gen --resume --answer load_kg=50 --answer stroke_mm=800
        │
        ▼
[NEW] read_state(./PROJECT_GOAL_STATE.json) → state
合并 confirmed_kpis = state.confirmed_kpis | --answer
parse_product_goal(text=state.raw_text, confirmed_kpis=合并后)
        │
        ▼ 仍缺 platform_size_mm
更新 state file；status=needs_kpi_confirmation；exit=0

最后一答：
$ cad-spec-gen --resume --answer platform_size_mm=600x600
        │
        ▼
全 KPI 齐 → delete_state(./PROJECT_GOAL_STATE.json)
status=ready_for_cad_spec；exit=0
```

### 3.2 文件布局

```
tools/product_goal_state.py            ← 新文件（schema + read/write/delete helper + validate_answer）（~120 行）
cad_pipeline.py                        ← parser 加 --resume / --answer (~25 行) +
                                        cmd_project_guide --resume 分支（~50 行）
tools/project_guide.py                 ← write_project_goal_guide 缺 KPI 写 state + exit code 改 (~30 行) +
                                        command_return_code_for_project_guide 调整（~10 行）
tests/test_product_goal_state.py       ← 新文件（state helper 单测 ~200 行）
tests/test_cad_pipeline_resume.py      ← 新文件（cli --resume 集成 ~250 行）
tests/test_project_guide_progressive.py ← 新文件（write_project_goal_guide 渐进路径 ~150 行）
docs/PROGRESS.md                       ← v2.31.0 入口（~10 行）
README.md                              ← 加多轮渐进示例（~25 行）
```

**不改文件**：`tools/product_goal_parser.py`（解析层完全复用）/ `tools/project_guide_dict/*.json`（词典不变）/ `tools/photo3d_*.py` / jury 子模块。

### 3.3 模块契约

#### `tools/product_goal_state.py`（新模块）

```python
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_GOAL_STATE_FILENAME = "PROJECT_GOAL_STATE.json"
SCHEMA_VERSION = 1
MAX_ROUND = 20  # 死循环保护

# 字段类型表（KPI schema；从 kpi_patterns.json 派生但本 PR 硬编码兜底）
KPI_VALUE_TYPES: dict[str, str] = {
    "load_kg": "float",
    "stroke_mm": "float",
    "platform_size_mm": "size_pair",  # "AxB" 或 (A, B)
    "rot_range_deg": "float",
    "switch_time_s": "float",
    "flange_dia_mm": "float",
}


def state_path(cwd: Path | None = None) -> Path:
    """返回 state file 绝对路径（cwd / PROJECT_GOAL_STATE.json）"""
    return (cwd or Path.cwd()) / PROJECT_GOAL_STATE_FILENAME


def read_state(cwd: Path | None = None) -> dict[str, Any] | None:
    """读 state file；不存在返 None；JSON 损坏抛 ValueError 含详细原因"""
    ...


def write_state(state: dict[str, Any], cwd: Path | None = None) -> Path:
    """写 state file；自动加 schema_version / updated_at；返写入路径
    raises OSError if cwd 不可写"""
    ...


def delete_state(cwd: Path | None = None) -> None:
    """删 state file；不存在静默"""
    ...


def validate_answer(key: str, value: str, kpi_value_types: Mapping[str, str] = KPI_VALUE_TYPES) -> Any:
    """校验 --answer key=value：
    - key ∈ kpi_value_types ∪ {"subsystem"}
    - value 按类型解析（float / int / "AxB" / str）
    抛 ValueError 含具体原因（中文提示）
    返解析后值（float / tuple[float, float] / str）"""
    ...
```

#### `cad_pipeline.py` parser

```python
# 在 cmd_project_guide 子解析器加：
p.add_argument("--resume", action="store_true",
               help="续答多轮渐进确认；从 ./PROJECT_GOAL_STATE.json 读上次状态")
p.add_argument("--answer", action="append", default=[],
               metavar="KEY=VALUE",
               help="多轮渐进答案；可重复（如 --answer load_kg=50 --answer stroke_mm=800）")

# argparse 互斥
group = p.add_mutually_exclusive_group()
group.add_argument("--product-goal", ...)  # 现有
group.add_argument("--resume", ...)  # 新加
```

#### `cad_pipeline.py:cmd_project_guide` 改造

```python
def cmd_project_guide(args):
    # ... 现有 imports ...

    if getattr(args, "resume", False):
        # NEW: --resume 路径
        from tools.product_goal_state import read_state, write_state, delete_state, validate_answer

        state = read_state()
        if state is None:
            log.error("./PROJECT_GOAL_STATE.json 不存在；先跑 cad-spec-gen --product-goal \"...\" 起手")
            return 2

        # 校验 round 防死循环
        if state.get("round", 0) >= MAX_ROUND:
            log.error(f"已续答 {state['round']}+ 轮仍未完整；建议检查 --answer 是否覆盖 missing_kpis")
            return 2

        # 解析 --answer
        confirmed_kpis = dict(state.get("confirmed_kpis", {}))
        confirmed_subsystem = state.get("confirmed_subsystem")
        for kv in args.answer:
            if "=" not in kv:
                log.error(f"--answer 需要 key=value 格式：{kv!r}")
                return 2
            key, value_str = kv.split("=", 1)
            try:
                parsed = validate_answer(key.strip(), value_str.strip())
            except ValueError as exc:
                log.error(str(exc))
                return 2
            if key.strip() == "subsystem":
                confirmed_subsystem = parsed
            else:
                confirmed_kpis[key.strip()] = parsed

        # 调 parse_product_goal + write_project_goal_guide
        report = write_project_goal_guide(
            PROJECT_ROOT,
            state["raw_text"],
            confirmed_subsystem=confirmed_subsystem,
            confirmed_kpis=confirmed_kpis,
            design_doc=state.get("design_doc"),
            output_path=getattr(args, "output", None),
            _state_round=state.get("round", 1) + 1,  # 内部参数；递增轮数
        )
        # write_project_goal_guide 内部决定写/删 state file
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return command_return_code_for_project_guide(report)

    # 现有 --product-goal 路径不动
    if getattr(args, "product_goal", None) is not None:
        ...
```

#### `tools/project_guide.py:write_project_goal_guide` 改造

```python
def write_project_goal_guide(
    project_root: Path,
    raw_text: str,
    *,
    design_doc: str | None = None,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, Any] | None = None,
    output_path: Path | None = None,
    _state_round: int = 1,  # 内部参数；--resume 时递增
) -> dict[str, Any]:
    # ... 现有 parse_product_goal 调用 + status 决策 ...

    # NEW: 写/删 state file 决策
    from tools.product_goal_state import write_state, delete_state, state_path

    missing_kpis = [...]  # 从 parse 结果派生
    if status == "needs_kpi_confirmation" and missing_kpis:
        # 写 state file
        write_state({
            "schema_version": 1,
            "raw_text": raw_text,
            "subsystem_class": parse_result.subsystem_class,
            "subsystem_status": parse_result.subsystem_status,
            "confirmed_subsystem": confirmed_subsystem,
            "confirmed_kpis": dict(confirmed_kpis or {}),
            "missing_kpis": missing_kpis,
            "design_doc": design_doc,
            "round": _state_round,
            "created_at": ...,  # 仅首轮写；后续轮保持
            "updated_at": now_utc_iso(),
        })
        # 改 ordinary_user_message：引导用户加 --resume --answer
        report["ordinary_user_message"] = (
            f"已识别为{parse_result.subsystem_class}。还缺 KPI: {', '.join(missing_kpis)}。\n"
            f"  下一步答任一项：cad-spec-gen --resume --answer {missing_kpis[0]}=<值>\n"
            f"  状态已记到 ./PROJECT_GOAL_STATE.json；可断点续答"
        )
    elif status == "ready_for_cad_spec":
        # 全 KPI 齐 → 删 state file（如果存在）
        delete_state()

    return report
```

#### `command_return_code_for_project_guide` 改造

**spec rev 1.1 修订**：v2.25.0 `tools/project_guide.py` line 184-199 已经把 `needs_kpi_confirmation` 放在 0-set 中（与 `ready_for_cad_spec` / `needs_subsystem_confirmation` / `unknown_subsystem` / `not_yet_implemented` 同段）。本 PR **不改** `command_return_code_for_project_guide`，仅复用现状。下表是 v2.25.0 既存行为（仅作 reader 参考）：

```python
def command_return_code_for_project_guide(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {
        "needs_subsystem_confirmation",
        "needs_init",
        "needs_design_doc",
        "needs_spec",
        "needs_codegen",
        "needs_build_render",
        "ready_for_photo3d_run",
        "needs_product_goal",
        "needs_kpi_confirmation",   # v2.25.0 已经在 0-set；本 PR 不改
        "ready_for_cad_spec",
        "unknown_subsystem",
        "not_yet_implemented",
    } else 1
```

### 3.4 不变量

1. **state file 唯一位置**：`./PROJECT_GOAL_STATE.json`（cwd）；不写 home dir / 不写 active run dir
2. **state 写入原子性**：复用 `tools/contract_io.py:write_json_atomic`（与其他 .json 输出一致）
3. **--answer 类型校验严格**：key ∈ kpi_value_types ∪ {subsystem}；value 按类型解析；任一失败 exit=2 + state 不修改
4. **round ≤ MAX_ROUND=20**：超出抛 ValueError；防死循环
5. **created_at 不被覆盖**：首轮 write_state 设；后续 --resume 保持原值；只更新 updated_at
6. **state 与 PROJECT_GUIDE.json 解耦**：PROJECT_GUIDE.json 仍按 v2.25.0 schema 输出；state 是独立辅助文件
7. **`parse_product_goal` 接口不动**：仅在 cli 层做 state 持久化与合并；解析层完全复用
8. **--product-goal / --resume 互斥**：argparse mutually_exclusive_group 强制
9. **错误路径不修改 state**：所有 exit=2 路径 state file 保持上一轮内容
10. **encoding 强制**：state file 读写 `encoding="utf-8"` + `json.dumps(ensure_ascii=False, indent=2)`（沿用 jury v1 invariant 12）

---

## 4. 数据流

### 4.1 PROJECT_GOAL_STATE.json schema

```json
{
  "schema_version": 1,
  "raw_text": "做升降平台",
  "subsystem_class": "lifting_platform",
  "subsystem_status": "implemented",
  "confirmed_subsystem": null,
  "confirmed_kpis": {
    "load_kg": 50,
    "stroke_mm": 800
  },
  "missing_kpis": ["platform_size_mm"],
  "design_doc": null,
  "created_at": "2026-05-09T18:00:00Z",
  "updated_at": "2026-05-09T18:05:00Z",
  "round": 2
}
```

### 4.2 完整流程（一次说全 + 渐进 3 轮 + 边界）

详见 §3.1 上下文图。

### 4.3 边界路径处理

| 场景 | 行为 |
|---|---|
| 用户答错 key（不在 KPI 列表）| ValueError + 中文提示 + state 不修改 |
| 用户答错 value 类型 | ValueError + 中文提示 + state 不修改 |
| state file 不存在但跑 --resume | FileNotFoundError + 提示先 --product-goal |
| state file JSON 损坏 | ValueError 含解析错误 + 提示删后重启 |
| state file schema_version 不识别 | ValueError + 提示版本不匹配 |
| round > 20 | ValueError + state 不更新 |
| --resume 与 --product-goal 同传 | argparse error |
| cwd 不可写 | OSError + 提示路径权限 |

---

## 5. 错误处理

### 5.1 错误分类

参 §4.3 边界路径表。所有错误路径：
- exit=2
- 中文 stderr 提示含具体下一步动作
- state file 不修改（用户重试有干净起点）

### 5.2 ordinary_user_message 模板（中文人话）

```python
# 起手不全：
"已识别为升降平台。还缺 KPI: 载重(load_kg) / 升降行程(stroke_mm) / 平台尺寸(platform_size_mm)。\n"
"  下一步答任一项：cad-spec-gen --resume --answer load_kg=50\n"
"  状态已记到 ./PROJECT_GOAL_STATE.json；可断点续答"

# 续答仍缺：
"已记录 load_kg=50。还缺 KPI: stroke_mm / platform_size_mm。\n"
"  cad-spec-gen --resume --answer stroke_mm=<值>"

# 全部完成：
"✓ 全部 KPI 已确认。下一步：cad-spec-gen --subsystem lifting_platform --design-doc ..."

# 错误路径：
"✗ --answer key 'load' 不在 KPI 列表 [load_kg, stroke_mm, platform_size_mm]"
"✗ --answer value 'fifty' 解析失败：load_kg 期望 float"
"✗ ./PROJECT_GOAL_STATE.json 不存在；先跑 cad-spec-gen --product-goal \"...\" 起手"
```

### 5.3 break-change 标记

**spec rev 1.1：v2.31.0 无 break-change**。v2.25.0 `command_return_code_for_project_guide` 已经把 `needs_kpi_confirmation` 放在 0-set 中（参 §3.3 改造段）；本 PR 仅扩展异步多轮模式（写 state + ordinary_user_message 改造），不改 exit code 行为。

判定"用户输入不全"的推荐方式（v2.25.0 起就一致）：

```bash
status=$(jq -r .status PROJECT_GUIDE.json)
if [ "$status" = "needs_kpi_confirmation" ]; then
    echo "需续答 KPI"
fi
```

---

## 6. 测试策略

### 6.1 TDD 节奏

每用例 RED → GREEN → REFACTOR → Commit。

### 6.2 单元 — `tests/test_product_goal_state.py`

| 测试 | 预期 |
|---|---|
| `test_read_state_missing_returns_none` | 文件不存在 → None |
| `test_read_state_valid_returns_dict` | 合法 JSON → dict |
| `test_read_state_corrupt_raises_value_error` | JSON 损坏 → ValueError |
| `test_read_state_unsupported_schema_version` | schema_version != 1 → ValueError |
| `test_write_state_creates_file` | 写后文件存在含期望字段 |
| `test_write_state_preserves_created_at` | 首次写 set；后续写不覆盖 |
| `test_write_state_updates_updated_at` | 后续写更新 updated_at |
| `test_write_state_uses_atomic` | 复用 write_json_atomic（mock 验证）|
| `test_delete_state_removes_file` | 删后文件不存在 |
| `test_delete_state_idempotent_when_missing` | 文件不存在静默不抛 |
| `test_validate_answer_kpi_float_ok` | load_kg=50 → 50.0 |
| `test_validate_answer_kpi_size_pair_ok` | platform_size_mm=600x600 → (600, 600) |
| `test_validate_answer_unknown_key_raises` | foo=bar → ValueError 中文 |
| `test_validate_answer_wrong_value_type_raises` | load_kg=fifty → ValueError 中文 |

### 6.3 集成 — `tests/test_cad_pipeline_resume.py`

| 测试 | 预期 |
|---|---|
| `test_full_one_shot_no_state_written` | 一次说全 → ready_for_cad_spec / 无 state file |
| `test_partial_first_call_writes_state_exit_0` | 起手不全 → exit=0 + state file 含 missing_kpis |
| `test_resume_single_answer_updates_state` | --resume --answer load_kg=50 → state 含 load_kg / 仍缺其他 |
| `test_resume_multiple_answers_accepted` | --resume --answer A=1 --answer B=2 → 两个都合并 |
| `test_resume_complete_deletes_state` | 答完最后一项 → ready_for_cad_spec / state file 删 |
| `test_answer_invalid_key_exit_2_state_unchanged` | --answer foo=bar → exit=2 + state 内容不变 |
| `test_answer_invalid_value_exit_2_state_unchanged` | --answer load_kg=fifty → exit=2 |
| `test_resume_without_state_exit_2` | state 不存在 + --resume → exit=2 |
| `test_resume_corrupt_state_exit_2` | state JSON 损坏 + --resume → exit=2 |
| `test_round_exceeds_max_exit_2` | round=21 → exit=2 |
| `test_resume_and_product_goal_mutually_exclusive` | 同传 → argparse error |
| `test_state_round_increments_per_resume` | 每次 --resume round+=1 |
| `test_subsystem_answer_overrides_state_class` | --answer subsystem=end_effector → confirmed_subsystem 更新 |

### 6.4 集成 — `tests/test_project_guide_progressive.py`

| 测试 | 预期 |
|---|---|
| `test_write_project_goal_guide_writes_state_when_missing_kpis` | parse 缺 KPI → state file 落盘 |
| `test_write_project_goal_guide_deletes_state_when_complete` | parse 全齐 → state file 删（如果存在）|
| `test_write_project_goal_guide_no_state_when_one_shot_complete` | 一次说全 + 全齐 → 不写 state |
| `test_command_return_code_needs_kpi_confirmation_returns_0` | break-change 守门 |
| `test_ordinary_user_message_contains_resume_hint` | needs_kpi_confirmation 文案含 --resume + --answer |

### 6.5 回归守门

- v2.25.0 现有 19 个 product_goal 测试全 PASS（特别注意 needs_kpi_confirmation 测试用例的 exit code 期望从 1→0 迁移）
- `tests/test_project_guide_*.py` 全 PASS

### 6.6 CI 矩阵

- Linux + Windows 都跑（cwd / Path 行为一致）
- mypy strict + ruff clean
- coverage：本 PR 新加路径 ≥90%

---

## 7. 兼容性与迁移

### 7.1 cli 层

- `--product-goal "..."` 一次说全行为完全保持（v2.25.0）
- 新增 `--resume` `--answer key=value`
- argparse 强制 --resume 与 --product-goal 互斥

### 7.2 报告 schema

- `PROJECT_GUIDE.json` schema_version 不升；现有字段保持
- 新加 `PROJECT_GOAL_STATE.json` schema_version=1（新文件，独立 schema）

### 7.3 v2.31.0 无 break-change（spec rev 1.1 修订）

**v2.31.0 无 break-change**：v2.25.0 `tools/project_guide.py:command_return_code_for_project_guide` line 184-199 已经把 `needs_kpi_confirmation` 放在 0-set 中（与 `ready_for_cad_spec` / `unknown_subsystem` / `not_yet_implemented` 同段）；本 PR 仅扩展异步多轮模式（写 `./PROJECT_GOAL_STATE.json` + 改造 ordinary_user_message 引导 `--resume`），不改 exit code 行为。

不需要任何迁移脚本。判定"用户输入不全"的方式（v2.25.0 起就一致）：

```bash
cad-spec-gen --product-goal "$GOAL" > guide.json
status=$(jq -r .status guide.json)
if [ "$status" = "ready_for_cad_spec" ]; then
    echo "OK"
elif [ "$status" = "needs_kpi_confirmation" ]; then
    echo "需续答 KPI（cad-spec-gen --resume --answer key=value）"
fi
```

### 7.4 文档迁移

- `docs/PROGRESS.md` 加 v2.31.0 入口（明示 v2.31.0 无 break-change；spec rev 1.1）
- `README.md` 用法示例增多轮渐进
- 本 spec commit

---

## 8. 实施顺序（plan 阶段拆分预想）

预估 plan 阶段 ~7-9 task：

1. **C0 准备**：建分支（已建）+ spec commit + grep 守门
2. **C1 product_goal_state.py 模块**：14 单测 RED → 实现 → GREEN
3. **C2 cad_pipeline.py parser 加 --resume/--answer**：argparse 互斥 + 集成入口
4. **C3 cmd_project_guide --resume 分支**：读 state + 合并 --answer + 调 parse + write_state
5. **C4 write_project_goal_guide 改造**：缺 KPI 写 state + 完整删 state + 改 message
6. **C5 command_return_code_for_project_guide 改造**：needs_kpi_confirmation 返 0
7. **C6 集成测试**：13 cli 用例 + 5 project_guide 用例
8. **C7 全量回归 + break-change 守门 + 北极星 5 gate**
9. **C8 文档 + PR + tag v2.31.0**

---

## 9. 风险与已知 unknown

### 9.1 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| ~~break-change exit code 影响 CI 脚本~~（spec rev 1.1 已删除） | ~~用户脚本可能误判~~ | **v2.25.0 已经返 0；本 PR 不改 exit code 行为；无 break-change 风险** |
| state file 遗留 cwd 污染 | 用户切目录后看到陌生 state | gitignore 加 PROJECT_GOAL_STATE.json + ready_for_cad_spec 时清理 |
| round > 20 死循环保护误伤 | 用户合法多轮答问被阻 | MAX_ROUND=20 足够覆盖 6 KPI × 3 重试；用户极少踩到 |
| --answer 类型校验偏严 | 用户输错格式被 reject | 中文提示含具体期望类型；用户可重答 |
| KPI_VALUE_TYPES 硬编码与 kpi_patterns.json 漂移 | 双源真相不一致 | plan task 0 grep 守门 + spec invariant 钉死 |
| Windows / Linux cwd 行为差异 | 测试 flake | 统一用 Path.cwd() + tmp_path fixture |

### 9.2 已知 unknown

- 用户实际多轮答问的最常见 patterns（一次答 1 个 vs 一次答多个）—— 上线后看实际数据
- `PROJECT_GOAL_STATE.json` gitignore 模板是否已有；plan task 0 grep 验证

### 9.3 不接受的风险（Red Team 防线）

- **不允许**：state file 写非 cwd 路径
- **不允许**：错误路径修改 state 内容
- **不允许**：parse_product_goal 接口被改动
- **不允许**：跨 product-goal 主题状态混用（每次一次说全 / --resume 续答严格隔离）

---

## 10. 验收标准（DoD）

1. **测试**：所有 §6 测试 PASS（14 单元 + 13 cli 集成 + 5 guide 集成 = 32 用例）
2. **回归**：`tests/` 全量 PASS 不少于 v2.30.0 基线（≥2725 PASS）
3. **v2.25.0 老用例 0 迁移**（spec rev 1.1 修订）：v2.25.0 `command_return_code_for_project_guide` 已经把 `needs_kpi_confirmation` 放在 0-set 中；本 PR 不改 exit code 行为，老用例 0 迁移负担；spec / PROGRESS / README 明示"v2.31.0 无 break-change"
4. **mypy strict + ruff clean**（本 PR 改的所有文件）
5. **CI**：Linux + Windows 双平台全绿
6. **coverage**：本 PR 新加路径 ≥90%
7. **文档**：PROGRESS v2.31.0 入口 + README 多轮渐进示例 + 本 spec commit
8. **北极星 5 gate**：
   - 零配置：✓ state 写 cwd 不引入 home dir 配置
   - 稳定可靠：✓ round 防死循环 + 错误不污染 state + atomic write
   - 结果准确：✓ parse_product_goal 接口完全复用 + 严格类型校验
   - SW 装即用：✓ 无 SW 涉及
   - 傻瓜式操作：✓ 不必一次说全 + 中文文案引导每一步
9. **schema 钉死**：PROJECT_GOAL_STATE.json 字段集 + PROJECT_GUIDE.json status 枚举值不变（仅 exit code 改）
10. **PR 流程**：feat/product-goal-progressive → PR → CI 全绿 → squash merge → tag v2.31.0 + GitHub Release

---

## 11. 后续 (v3 路线，不在本 PR)

- B 项目向导记忆：跨 session 持久化已确认子系统/KPI（看 A 上线后用户重复跑同项目频率决定）
- C 类别扩展 19→30+：等用户实际反馈 unknown_subsystem 才扩
- 多 KPI 同步答问范式（如 LLM 助手代填多 --answer）
- 更精细的 KPI 校验规则（unit / range / pattern）

---

## 附录 A：参考文件

| 文件 | 用途 |
|---|---|
| `tools/product_goal_parser.py` | v2.25.0 解析层（不改）|
| `tools/project_guide_dict/subsystem_keywords.json` | 19 类子系统词典（不改）|
| `tools/project_guide_dict/kpi_patterns.json` | 6 KPI patterns（不改）|
| `tools/project_guide.py:write_project_goal_guide` | v2.25.0 现有；本 PR 改造 |
| `tools/contract_io.py:write_json_atomic` | atomic write helper（state file 写盘复用）|
| `docs/superpowers/specs/2026-04-26-product-goal-design.md` | v2.25.0 spec |
| `CLAUDE.md` | 项目工作流约束 |
