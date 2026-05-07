# 产品目标自然语言入口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `project-guide` 入口前移到产品目标自然语言模式（外行用户用一句话即可启动管线，3 层确定性词典识别 + KPI 抽取 + 缺失参数确认），并存于现有 `--from-design-doc` / `--subsystem` 模式而非替代。

**Architecture:** 3 层确定性解析器（subsystem 识别 / KPI 抽取 / 歧义检测）→ `write_project_goal_guide` 入口函数（与既有 `write_project_entry_guide` 平行）→ `cmd_project_guide` dispatch 加分支（dispatch fallback 而非 error）→ JSON 词典随 `tools/` 递归镜像自动同步。

**Tech Stack:** Python 3.11+ / pytest / dataclass + Literal types / json.loads（不引入 PyYAML 到 base install）/ NFKC unicode 归一 / 复用现有 `tools/path_policy.assert_within_project`、`tools/contract_io.write_json_atomic`、`tools/project_guide.py:624 _safe_cli_token`。

**关键参考**：

- spec：`docs/superpowers/specs/2026-05-07-product-goal-entry-design.md`（rev 4，714 行）
- 工作树：`.worktrees/product-goal-entry/`，分支 `codex/product-goal-entry`
- 项目规范：项目根 `CLAUDE.md`（TDD 铁律、中文输出、dev_sync 守护）

---

## 文件结构

### 新建文件

| 路径 | 职责 | 来源 |
|---|---|---|
| `tools/project_guide_dict/__init__.py` | 加载 JSON 字典 + dataclass 自校验；导出 `load_dictionary()` / `ProductGoalDictionary` | spec §解析器结构 |
| `tools/project_guide_dict/subsystem_keywords.json` | 第 1 层词典：19 类子系统 keyword + status | spec §第 1 层 |
| `tools/project_guide_dict/kpi_patterns.json` | 第 2 层词典：6 个 KPI（lifting + EE 各 3）regex + context_terms | spec §第 2 层 |
| `tools/product_goal_parser.py` | 3 层解析器；导出 `parse_product_goal()` / `ProductGoalParseResult` / `KpiExtraction` | spec §关键 API 签名 |
| `tests/test_product_goal_parser.py` | 解析器单元测试（≥15 例 + rev 4 dry-run 场景） | spec §测试矩阵 |
| `tests/test_project_goal_guide.py` | 入口端到端测试（≥13 例覆盖 7 状态 + 5 dry-run 场景） | spec §测试矩阵 |

### 修改文件

| 路径 | 改动 | 行数估计 |
|---|---|---|
| `tools/project_guide.py` | 新增 `write_project_goal_guide()` + `_subsystem_candidates_for_product_goal()` + 6 个状态对应的 `_ordinary_user_message()` 分支 | +180 |
| `cad_pipeline.py` | 扩展 `cmd_project_guide` dispatch（含 default fallback）+ 加 7 个新 CLI flag + `_collect_confirmed_kpis()` helper | +60 |
| `tests/test_project_guide.py` | 新增 2 例向后兼容测试 | +50 |
| `docs/cad-help-guide-zh.md` | 新模式用户文档 | +30 |
| `docs/cad-help-guide-en.md` | 新模式英文文档 | +30 |
| `.claude/commands/cad-help.md` | skill cmd 帮助 | +20 |
| `skill_cad_help_zh.md` / `skill.json` | skill metadata | +15 |

### 自动镜像（dev_sync 递归同步 `tools/`）

- `src/cad_spec_gen/data/tools/project_guide_dict/{__init__.py, subsystem_keywords.json, kpi_patterns.json}`
- `src/cad_spec_gen/data/tools/{product_goal_parser.py, project_guide.py}`

**镜像列表无需手动添加**——`hatch_build.py:62 COPY_DIRS = {"tools": "tools"}` 已递归镜像 `tools/`。

---

## 检查点（5 个 CHECKPOINT）

| CP | 完成态 | 用户确认动作 |
|---|---|---|
| **CP-1** | Task 0-3 完成（pre-flight 验证 + JSON 字典 + 加载器） | 字典 schema 设计是否合理？支持 19 类是否充分？ |
| **CP-2** | Task 4-7 完成（3 层解析器 + override） | 解析器对边界（NFKC / 数字共享 / regex 短路）行为是否符合预期？ |
| **CP-3** | Task 8-10 完成（入口函数 + 7 状态分流 + safe escaping） | 7 状态映射 + alternatives 字段是否清楚易懂？ |
| **CP-4** | Task 11-12 完成（CLI dispatch + 向后兼容测试） | 既有 16 个 test_project_guide.py 是否仍 pass？ dispatch fallback 是否符合预期？ |
| **CP-5** | Task 13-14 完成（dev_sync verify + 文档 + metadata） | 安装版镜像无漂移？文档可读？准备开 PR？ |

---

## Task 0：Pre-flight 假设验证（main agent 执行，不派 subagent）

**Files:** 仅读取，不修改

**目的**：按 memory `feedback_subagent_driven_main_agent_scouts.md` + `feedback_plan_drift_taxonomy.md` 5 类预防——派 subagent 前 grep 验证 spec 假设是否真实，避免后续 subagent 按错的假设实施。

- [ ] **Step 1：验证现有函数存在**

```bash
grep -n "def assert_within_project" tools/path_policy.py
grep -n "def write_json_atomic" tools/contract_io.py
grep -n "def _safe_cli_token" tools/project_guide.py
grep -n "def write_project_entry_guide" tools/project_guide.py
grep -n "def _subsystem_candidates_for_design_doc" tools/project_guide.py
grep -n "def _ordinary_user_message" tools/project_guide.py
grep -n "def cmd_project_guide" cad_pipeline.py
```

预期：每条都返回 1 个 hit。任何缺失即标 BLOCKER 并停下与用户对齐。

- [ ] **Step 2：验证字段名 alignment**

```bash
grep -n 'entry_mode' tools/project_guide.py
```

预期：`entry_mode = "design_doc"`（spec rev 3 已对齐，验证无新漂移）。

- [ ] **Step 3：验证 hatch_build COPY_DIRS 含 tools**

```bash
grep -A4 "COPY_DIRS = {" hatch_build.py
```

预期：`"tools": "tools"` 在内（确认递归镜像）。

- [ ] **Step 4：验证 _safe_cli_token 实现细节**

```bash
sed -n '624,640p' tools/project_guide.py
```

预期：`re.fullmatch(r"[A-Za-z0-9_.-]+", value or "")`——这意味着任何中文/空格/`"` 都会 unsafe → preview_cli 必然降级，不依赖"是否含特殊字符"区分。

- [ ] **Step 5：验证 cad-spec subcommand design_doc 处理**

```bash
sed -n '1768,1780p' cad_pipeline.py
```

预期：`if not design_doc or not os.path.isfile(design_doc): log.error("Design doc not found...")`——确认 design_doc 是 cad-spec 硬性要求（rev 4 needs_design_doc 状态的根据）。

- [ ] **Step 6：记录验证结果到 plan-drift checklist（无 commit）**

如果上述任一检查与 spec 假设不符，**停下**用户对齐；否则继续。

---

## Task 1：JSON 字典文件创建

**Files:**
- Create: `tools/project_guide_dict/subsystem_keywords.json`
- Create: `tools/project_guide_dict/kpi_patterns.json`
- Test: `tests/test_product_goal_parser.py`（首次创建文件）

- [ ] **Step 1：写失败测试 — 字典文件存在 + 19 类齐全**

```python
# tests/test_product_goal_parser.py
"""产品目标解析器单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DICT_DIR = REPO_ROOT / "tools" / "project_guide_dict"


def test_subsystem_keywords_json_exists_and_covers_all_19_subsystems():
    path = DICT_DIR / "subsystem_keywords.json"
    assert path.is_file(), f"missing: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))

    expected_implemented = {"lifting_platform", "end_effector"}
    expected_not_yet = {
        "navigation", "motion_ctrl", "electrical", "communication",
        "charging", "couplant", "detection", "integration", "output",
        "patent", "plan", "power", "robot_platform", "safety",
        "software", "sys_arch", "budget",
    }
    expected = expected_implemented | expected_not_yet

    assert set(data.keys()) == expected, f"差异：{set(data.keys()) ^ expected}"
    for name in expected_implemented:
        assert data[name]["status"] == "implemented", f"{name} 应为 implemented"
    for name in expected_not_yet:
        assert data[name]["status"] == "not_yet_implemented", f"{name} 应为 not_yet_implemented"


def test_kpi_patterns_json_has_3_kpis_per_implemented_subsystem():
    path = DICT_DIR / "kpi_patterns.json"
    assert path.is_file(), f"missing: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))

    assert set(data.keys()) == {"lifting_platform", "end_effector"}

    assert set(data["lifting_platform"].keys()) == {"load_kg", "stroke_mm", "platform_size_mm"}
    assert set(data["end_effector"].keys()) == {"rot_range_deg", "switch_time_s", "flange_dia_mm"}

    # 每个 KPI 必有 regex (list) + context_terms (list) + unit (str)
    for subsystem, kpis in data.items():
        for kpi_name, kpi in kpis.items():
            assert isinstance(kpi.get("regex"), list) and kpi["regex"], f"{subsystem}.{kpi_name} regex 缺"
            assert isinstance(kpi.get("context_terms"), list) and kpi["context_terms"], f"{subsystem}.{kpi_name} context_terms 缺"
            assert isinstance(kpi.get("unit"), str), f"{subsystem}.{kpi_name} unit 缺"
```

- [ ] **Step 2：跑测试验证失败**

```bash
cd .worktrees/product-goal-entry && python -m pytest tests/test_product_goal_parser.py -v
```

预期：FAIL — `FileNotFoundError: missing: tools/project_guide_dict/subsystem_keywords.json`

- [ ] **Step 3：创建 subsystem_keywords.json**

```json
{
  "lifting_platform": {
    "status": "implemented",
    "primary_terms": ["升降平台", "升降台", "lifting platform", "提升台"],
    "supporting_terms": ["升降", "提升", "lift", "升起"]
  },
  "end_effector": {
    "status": "implemented",
    "primary_terms": ["末端执行", "末端工具", "end effector", "EE"],
    "supporting_terms": ["末端", "夹爪", "翻转工具", "工具切换"]
  },
  "navigation": {
    "status": "not_yet_implemented",
    "primary_terms": ["导航", "navigation", "SLAM"],
    "supporting_terms": ["路径规划", "定位"]
  },
  "motion_ctrl": {
    "status": "not_yet_implemented",
    "primary_terms": ["运动控制", "motion control", "motion_ctrl"],
    "supporting_terms": ["伺服", "电机控制"]
  },
  "electrical": {
    "status": "not_yet_implemented",
    "primary_terms": ["电气系统", "electrical system", "配电"],
    "supporting_terms": ["供电", "线缆"]
  },
  "communication": {
    "status": "not_yet_implemented",
    "primary_terms": ["通信", "communication", "总线"],
    "supporting_terms": ["CAN", "RS485", "Ethernet"]
  },
  "charging": {
    "status": "not_yet_implemented",
    "primary_terms": ["充电", "charging", "充电桩"],
    "supporting_terms": ["快充", "对接"]
  },
  "couplant": {
    "status": "not_yet_implemented",
    "primary_terms": ["耦合剂", "couplant", "超声耦合"],
    "supporting_terms": ["耦合", "超声"]
  },
  "detection": {
    "status": "not_yet_implemented",
    "primary_terms": ["检测", "detection", "传感"],
    "supporting_terms": ["传感器", "探测"]
  },
  "integration": {
    "status": "not_yet_implemented",
    "primary_terms": ["集成", "integration", "总成"],
    "supporting_terms": ["装配", "整机"]
  },
  "output": {
    "status": "not_yet_implemented",
    "primary_terms": ["输出", "output", "执行输出"],
    "supporting_terms": ["输出端", "动作输出"]
  },
  "patent": {
    "status": "not_yet_implemented",
    "primary_terms": ["专利", "patent"],
    "supporting_terms": ["专利布局", "知识产权"]
  },
  "plan": {
    "status": "not_yet_implemented",
    "primary_terms": ["规划", "plan", "项目规划"],
    "supporting_terms": ["计划"]
  },
  "power": {
    "status": "not_yet_implemented",
    "primary_terms": ["电源", "power", "供电系统"],
    "supporting_terms": ["电池", "电源管理"]
  },
  "robot_platform": {
    "status": "not_yet_implemented",
    "primary_terms": ["机器人平台", "robot platform", "底盘平台"],
    "supporting_terms": ["机器人", "底盘"]
  },
  "safety": {
    "status": "not_yet_implemented",
    "primary_terms": ["安全", "safety", "安全系统"],
    "supporting_terms": ["急停", "安全门"]
  },
  "software": {
    "status": "not_yet_implemented",
    "primary_terms": ["软件", "software", "上位机"],
    "supporting_terms": ["代码", "应用"]
  },
  "sys_arch": {
    "status": "not_yet_implemented",
    "primary_terms": ["系统架构", "system architecture", "sys_arch"],
    "supporting_terms": ["架构"]
  },
  "budget": {
    "status": "not_yet_implemented",
    "primary_terms": ["预算", "budget", "成本"],
    "supporting_terms": ["造价"]
  }
}
```

- [ ] **Step 4：创建 kpi_patterns.json**

```json
{
  "lifting_platform": {
    "load_kg": {
      "regex": ["(\\d+(?:\\.\\d+)?)\\s*(?:kg|公斤|千克)"],
      "context_terms": ["载荷", "承载", "负载", "升起", "举起", "提升", "升"],
      "unit": "kg",
      "slot": "capability_1"
    },
    "stroke_mm": {
      "regex": [
        "(\\d+(?:\\.\\d+)?)\\s*(?:mm|毫米)",
        "(\\d+(?:\\.\\d+)?)\\s*(?:cm|厘米)",
        "(\\d+(?:\\.\\d+)?)\\s*m(?![ms])"
      ],
      "context_terms": ["行程", "升高", "升程", "stroke", "travel"],
      "unit": "mm",
      "unit_normalize": {"cm": 10, "m": 1000, "厘米": 10, "米": 1000},
      "slot": "capability_2"
    },
    "platform_size_mm": {
      "regex": ["(\\d+)\\s*[x×]\\s*(\\d+)\\s*(?:mm|毫米)?"],
      "context_terms": ["平台", "platform", "尺寸", "外形", "包络", "面积"],
      "unit": "mm",
      "value_shape": "pair",
      "slot": "envelope"
    }
  },
  "end_effector": {
    "rot_range_deg": {
      "regex": ["[±]?\\s*(\\d+(?:\\.\\d+)?)\\s*[°度]"],
      "context_terms": ["翻转", "旋转", "rotation", "rotate"],
      "unit": "deg",
      "slot": "capability_1"
    },
    "switch_time_s": {
      "regex": ["(\\d+(?:\\.\\d+)?)\\s*(?:s|秒)"],
      "context_terms": ["切换", "switch"],
      "unit": "s",
      "slot": "capability_2"
    },
    "flange_dia_mm": {
      "regex": [
        "Φ\\s*(\\d+(?:\\.\\d+)?)",
        "(\\d+)\\s*mm\\s*法兰",
        "flange\\s*(\\d+)"
      ],
      "context_terms": ["法兰", "flange"],
      "unit": "mm",
      "slot": "envelope"
    }
  }
}
```

- [ ] **Step 5：跑测试验证通过**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：PASS（2 例）

- [ ] **Step 6：commit**

```bash
git -C .worktrees/product-goal-entry add tools/project_guide_dict/ tests/test_product_goal_parser.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 增加子系统识别与 KPI 抽取词典 JSON"
```

---

## Task 2：词典加载器（dataclass + 自校验）

**Files:**
- Create: `tools/project_guide_dict/__init__.py`
- Test: `tests/test_product_goal_parser.py`（追加测试）

- [ ] **Step 1：写失败测试 — load_dictionary() 返回 ProductGoalDictionary，schema 错抛 RuntimeError**

```python
# 追加到 tests/test_product_goal_parser.py
def test_load_dictionary_returns_validated_object():
    from tools.project_guide_dict import load_dictionary, ProductGoalDictionary

    d = load_dictionary()
    assert isinstance(d, ProductGoalDictionary)
    assert "lifting_platform" in d.subsystem_keywords
    assert "load_kg" in d.kpi_patterns["lifting_platform"]


def test_load_dictionary_raises_on_missing_file(tmp_path):
    from tools.project_guide_dict import load_dictionary

    (tmp_path / "subsystem_keywords.json").write_text("{}", encoding="utf-8")
    # 缺 kpi_patterns.json
    with pytest.raises(RuntimeError, match="kpi_patterns.json"):
        load_dictionary(dict_root=tmp_path)


def test_load_dictionary_raises_on_implemented_subsystem_missing_kpis(tmp_path):
    from tools.project_guide_dict import load_dictionary

    (tmp_path / "subsystem_keywords.json").write_text(
        json.dumps({"lifting_platform": {"status": "implemented", "primary_terms": ["升降"], "supporting_terms": []}}),
        encoding="utf-8",
    )
    (tmp_path / "kpi_patterns.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="lifting_platform.*kpi_patterns"):
        load_dictionary(dict_root=tmp_path)
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：FAIL — `ModuleNotFoundError: tools.project_guide_dict`

- [ ] **Step 3：实现 `tools/project_guide_dict/__init__.py`**

```python
"""加载子系统识别 + KPI 抽取词典；dataclass 自校验。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DEFAULT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ProductGoalDictionary:
    """3 层确定性解析器词典聚合体。"""

    subsystem_keywords: dict[str, dict[str, Any]]
    kpi_patterns: dict[str, dict[str, dict[str, Any]]]

    def __post_init__(self) -> None:
        for name, entry in self.subsystem_keywords.items():
            status = entry.get("status")
            if status not in {"implemented", "not_yet_implemented"}:
                raise RuntimeError(f"subsystem_keywords[{name}].status 非法：{status!r}")
            if not entry.get("primary_terms"):
                raise RuntimeError(f"subsystem_keywords[{name}].primary_terms 不能为空")

        implemented = {n for n, e in self.subsystem_keywords.items() if e.get("status") == "implemented"}
        kpi_keys = set(self.kpi_patterns.keys())
        if implemented - kpi_keys:
            missing = implemented - kpi_keys
            raise RuntimeError(f"implemented 子系统缺少 kpi_patterns 条目：{missing}")

        for subsystem, kpis in self.kpi_patterns.items():
            for kpi_name, kpi in kpis.items():
                if not isinstance(kpi.get("regex"), list) or not kpi["regex"]:
                    raise RuntimeError(f"kpi_patterns[{subsystem}.{kpi_name}].regex 必须是非空列表")
                if not isinstance(kpi.get("context_terms"), list) or not kpi["context_terms"]:
                    raise RuntimeError(f"kpi_patterns[{subsystem}.{kpi_name}].context_terms 必须是非空列表")
                if "unit" not in kpi:
                    raise RuntimeError(f"kpi_patterns[{subsystem}.{kpi_name}].unit 缺")


def load_dictionary(*, dict_root: Path | None = None) -> ProductGoalDictionary:
    """从 JSON 文件加载词典；缺文件 / schema 错 → RuntimeError。"""
    root = dict_root or _DEFAULT_ROOT
    keywords_path = root / "subsystem_keywords.json"
    patterns_path = root / "kpi_patterns.json"

    if not keywords_path.is_file():
        raise RuntimeError(f"subsystem_keywords.json 不存在：{keywords_path}")
    if not patterns_path.is_file():
        raise RuntimeError(f"kpi_patterns.json 不存在：{patterns_path}")

    keywords = json.loads(keywords_path.read_text(encoding="utf-8"))
    patterns = json.loads(patterns_path.read_text(encoding="utf-8"))

    return ProductGoalDictionary(
        subsystem_keywords=keywords,
        kpi_patterns=patterns,
    )


__all__ = ["ProductGoalDictionary", "load_dictionary"]
```

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：PASS（5 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tools/project_guide_dict/__init__.py tests/test_product_goal_parser.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 增加词典加载器与 dataclass 自校验"
```

---

## Task 3：解析器骨架 + ProductGoalParseResult dataclass

**Files:**
- Create: `tools/product_goal_parser.py`
- Test: `tests/test_product_goal_parser.py`（追加）

- [ ] **Step 1：写失败测试 — parse_product_goal 空字符串返回 needs_product_goal**

```python
# 追加
def test_parse_empty_text_returns_no_subsystem():
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="")
    assert result.subsystem_class is None
    assert result.subsystem_status == "unknown"
    assert result.kpis == {}
    assert result.raw_text == ""
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：FAIL — `ModuleNotFoundError: tools.product_goal_parser`

- [ ] **Step 3：实现 `tools/product_goal_parser.py` 骨架（仅 dataclass + 空实现）**

```python
"""3 层确定性产品目标解析器。

层 1：subsystem class 识别（subsystem_keywords.json）
层 2：KPI 抽取（kpi_patterns.json，regex + context_terms 双条件）
层 3：歧义检测（数字共享按 char 距离独立判定）
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from tools.project_guide_dict import ProductGoalDictionary, load_dictionary


SubsystemStatus = Literal["implemented", "not_yet_implemented", "ambiguous", "unknown"]
KpiStatus = Literal["extracted", "ambiguous", "missing"]


@dataclass(frozen=True)
class KpiExtraction:
    kpi_name: str
    value: float | tuple[float, float] | None
    unit: str | None
    evidence_token: str | None
    rule: str
    status: KpiStatus


@dataclass(frozen=True)
class ProductGoalParseResult:
    raw_text: str
    subsystem_class: str | None
    subsystem_status: SubsystemStatus
    kpis: dict[str, KpiExtraction] = field(default_factory=dict)
    parser_evidence: list[dict[str, Any]] = field(default_factory=list)


def parse_product_goal(
    *,
    text: str,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float | tuple[float, float]] | None = None,
    dictionary: ProductGoalDictionary | None = None,
) -> ProductGoalParseResult:
    """3 层确定性解析。"""
    if dictionary is None:
        dictionary = load_dictionary()

    if not text or not text.strip():
        return ProductGoalParseResult(
            raw_text=text,
            subsystem_class=None,
            subsystem_status="unknown",
        )

    # NFKC normalize（半/全角统一），保留原大小写到 evidence
    normalized = unicodedata.normalize("NFKC", text)

    # 占位：后续 task 补 3 层逻辑
    return ProductGoalParseResult(
        raw_text=text,
        subsystem_class=None,
        subsystem_status="unknown",
    )


__all__ = [
    "KpiExtraction",
    "ProductGoalParseResult",
    "SubsystemStatus",
    "KpiStatus",
    "parse_product_goal",
]
```

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：PASS（6 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tools/product_goal_parser.py tests/test_product_goal_parser.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 增加解析器骨架与 dataclass"
```

---

## CHECKPOINT 1（Task 0-3 完成）

**用户确认问题**：
1. 19 类子系统词典是否覆盖你预期的产品域？
2. 6 个 KPI 是否能覆盖外行用户最常表达的场景？
3. dataclass 校验严格度是否合适（schema 错就抛 RuntimeError 不静默）？

**确认后进入 CP-2（Task 4-7）。**

---

## Task 4：第 1 层 subsystem class 识别

**Files:**
- Modify: `tools/product_goal_parser.py`
- Test: `tests/test_product_goal_parser.py`（追加）

- [ ] **Step 1：写失败测试 — primary_terms 命中即定类（6 positive + 6 negative + ambiguous）**

```python
# 追加
@pytest.mark.parametrize("text,expected_class,expected_status", [
    ("做一个升降平台", "lifting_platform", "implemented"),
    ("我要个 lifting platform", "lifting_platform", "implemented"),
    ("末端执行机构", "end_effector", "implemented"),
    ("end effector 设计", "end_effector", "implemented"),
    ("做导航 SLAM", "navigation", "not_yet_implemented"),
    ("一个充电桩", "charging", "not_yet_implemented"),
])
def test_subsystem_primary_terms_match_directly(text, expected_class, expected_status):
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text=text)
    assert result.subsystem_class == expected_class, f"识别错：{result.subsystem_class}"
    assert result.subsystem_status == expected_status


def test_subsystem_supporting_only_marks_ambiguous():
    """仅 supporting_terms 命中（无 primary）→ ambiguous。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降 50kg")  # "升降" 是 lifting 的 supporting，无 primary
    assert result.subsystem_class is None
    assert result.subsystem_status == "ambiguous"


def test_unknown_subsystem_returns_unknown():
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="做一个不存在的产品类型 xyzzy")
    assert result.subsystem_class is None
    assert result.subsystem_status == "unknown"
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：FAIL — 8 例新测试，所有都 unknown 不匹配预期

- [ ] **Step 3：实现第 1 层 subsystem 识别**

替换 `parse_product_goal` 占位逻辑：

```python
def parse_product_goal(
    *,
    text: str,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float | tuple[float, float]] | None = None,
    dictionary: ProductGoalDictionary | None = None,
) -> ProductGoalParseResult:
    if dictionary is None:
        dictionary = load_dictionary()

    if not text or not text.strip():
        return ProductGoalParseResult(
            raw_text=text, subsystem_class=None, subsystem_status="unknown"
        )

    normalized = unicodedata.normalize("NFKC", text)
    evidence: list[dict[str, Any]] = []

    # confirmed_subsystem 强制覆盖
    if confirmed_subsystem and confirmed_subsystem in dictionary.subsystem_keywords:
        subsystem_class = confirmed_subsystem
        subsystem_status = dictionary.subsystem_keywords[confirmed_subsystem]["status"]
        evidence.append({
            "token": confirmed_subsystem,
            "matched": "subsystem_class",
            "rule": "confirmed_subsystem",
        })
    else:
        subsystem_class, subsystem_status = _identify_subsystem(normalized, dictionary, evidence)

    return ProductGoalParseResult(
        raw_text=text,
        subsystem_class=subsystem_class,
        subsystem_status=subsystem_status,
        parser_evidence=evidence,
    )


def _identify_subsystem(
    normalized: str,
    dictionary: ProductGoalDictionary,
    evidence: list[dict[str, Any]],
) -> tuple[str | None, SubsystemStatus]:
    primary_hits: list[tuple[str, str]] = []   # (subsystem_name, matched_token)
    supporting_hits: list[tuple[str, str]] = []

    for name, entry in dictionary.subsystem_keywords.items():
        for term in entry["primary_terms"]:
            if term in normalized:
                primary_hits.append((name, term))
                break
        else:
            for term in entry.get("supporting_terms", []):
                if term in normalized:
                    supporting_hits.append((name, term))
                    break

    if len(primary_hits) == 1:
        name, token = primary_hits[0]
        evidence.append({"token": token, "matched": "subsystem_class", "rule": f"primary_terms:{name}"})
        return name, dictionary.subsystem_keywords[name]["status"]

    if len(primary_hits) > 1:
        for name, token in primary_hits:
            evidence.append({"token": token, "matched": "subsystem_class_candidate", "rule": f"primary_terms:{name}"})
        return None, "ambiguous"

    if supporting_hits:
        for name, token in supporting_hits:
            evidence.append({"token": token, "matched": "subsystem_class_candidate", "rule": f"supporting_terms:{name}"})
        return None, "ambiguous"

    return None, "unknown"
```

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：PASS（14 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tools/product_goal_parser.py tests/test_product_goal_parser.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 实现第 1 层子系统类别识别"
```

---

## Task 5：第 2 层 KPI 抽取 + 单位归一

**Files:**
- Modify: `tools/product_goal_parser.py`
- Test: `tests/test_product_goal_parser.py`（追加）

- [ ] **Step 1：写失败测试 — KPI 抽取双条件 + 单位归一 + platform_size pair**

```python
# 追加
def test_kpi_extracted_when_regex_and_context_both_hit():
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="做一个能升 50kg 的升降平台")
    assert result.subsystem_class == "lifting_platform"
    assert result.kpis["load_kg"].value == 50
    assert result.kpis["load_kg"].status == "extracted"
    assert result.kpis["load_kg"].unit == "kg"


def test_kpi_missing_when_only_regex_hits_no_context():
    """50kg 但无任何 lifting context_term → load_kg 应 missing。"""
    from tools.product_goal_parser import parse_product_goal

    # 此 case 无"载荷/承载/负载/升起/举起/提升/升"等 context
    result = parse_product_goal(text="做一个升降平台 50kg")
    # "升降平台" 含"升"但"升"距离 50kg < 20，应抽到
    assert result.kpis["load_kg"].status == "extracted"

    result2 = parse_product_goal(text="做一个 lifting platform，重量 50kg")
    # 此处 context_terms 都不命中（无"载荷/升起/提升/升"），但 lifting platform 中 lift 不在 context_terms 内
    # 50 应 missing
    assert result2.kpis["load_kg"].status == "missing"


def test_stroke_unit_normalize_mm_cm_m_all_normalize_to_mm():
    from tools.product_goal_parser import parse_product_goal

    for text, expected in [
        ("升降平台 行程 200mm", 200.0),
        ("升降平台 行程 20cm", 200.0),
        ("升降平台 行程 0.2m", 200.0),
    ]:
        result = parse_product_goal(text=text)
        assert result.kpis["stroke_mm"].value == expected, f"{text}: {result.kpis['stroke_mm'].value}"


def test_platform_size_extracts_pair():
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 350x230 平台")
    assert result.kpis["platform_size_mm"].value == (350.0, 230.0)
    assert result.kpis["platform_size_mm"].status == "extracted"


def test_nfkc_normalize_fullwidth_digits():
    from tools.product_goal_parser import parse_product_goal

    # 全角数字 １００ 应等价 100
    result = parse_product_goal(text="升降平台 升起 １００kg")
    assert result.kpis["load_kg"].value == 100
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：FAIL — kpi 字段不存在或值不对

- [ ] **Step 3：实现第 2 层 KPI 抽取**

在 `tools/product_goal_parser.py` 加入：

```python
import re

_DISTANCE_WINDOW = 20  # ±20 字符上下文窗口


def _extract_kpis_for_subsystem(
    normalized: str,
    subsystem_class: str,
    dictionary: ProductGoalDictionary,
    evidence: list[dict[str, Any]],
) -> dict[str, KpiExtraction]:
    """对一个 subsystem 跑所有 KPI 抽取，未命中标 missing。"""
    extractions: dict[str, KpiExtraction] = {}
    kpi_specs = dictionary.kpi_patterns[subsystem_class]

    for kpi_name, spec in kpi_specs.items():
        extracted = _extract_single_kpi(normalized, kpi_name, spec, evidence)
        extractions[kpi_name] = extracted
    return extractions


def _extract_single_kpi(
    normalized: str,
    kpi_name: str,
    spec: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> KpiExtraction:
    """单 KPI 抽取：regex 短路命中 + ±20 字符 context_terms。"""
    context_terms = spec["context_terms"]
    unit = spec["unit"]
    unit_normalize = spec.get("unit_normalize") or {}
    value_shape = spec.get("value_shape", "single")

    # 找所有 context_terms 在 normalized 中的位置
    context_positions: list[int] = []
    for term in context_terms:
        idx = 0
        while True:
            pos = normalized.find(term, idx)
            if pos < 0:
                break
            context_positions.append(pos)
            idx = pos + len(term)

    if not context_positions:
        # 无 context → missing
        return KpiExtraction(
            kpi_name=kpi_name, value=None, unit=unit,
            evidence_token=None, rule="no_context", status="missing",
        )

    # 按 yaml 顺序短路 regex
    for regex_idx, pattern in enumerate(spec["regex"]):
        compiled = re.compile(pattern)
        for match in compiled.finditer(normalized):
            number_start = match.start()
            number_end = match.end()
            min_dist = min(
                min(abs(cp - number_start), abs(cp - number_end))
                for cp in context_positions
            )
            if min_dist > _DISTANCE_WINDOW:
                continue

            # 命中
            if value_shape == "pair":
                value: float | tuple[float, float] = (float(match.group(1)), float(match.group(2)))
            else:
                raw = float(match.group(1))
                # 单位归一（按 regex_idx 选择）
                if regex_idx > 0 and unit_normalize:
                    # 第 2/3 条 regex 对应 cm/m，乘以倍率
                    unit_keys = list(unit_normalize.keys())
                    if regex_idx - 1 < len(unit_keys):
                        raw = raw * unit_normalize[unit_keys[regex_idx - 1]]
                value = raw

            evidence.append({
                "token": match.group(0),
                "matched": kpi_name,
                "rule": f"regex+context:{context_terms[0]}",
                "regex_index": regex_idx,
            })
            return KpiExtraction(
                kpi_name=kpi_name, value=value, unit=unit,
                evidence_token=match.group(0),
                rule=f"regex+context:{context_terms[0]}",
                status="extracted",
            )

    return KpiExtraction(
        kpi_name=kpi_name, value=None, unit=unit,
        evidence_token=None, rule="no_match", status="missing",
    )
```

并修改主函数 `parse_product_goal`，在 subsystem_class 是 "implemented" 时调用：

```python
    if subsystem_class and subsystem_status == "implemented":
        kpis = _extract_kpis_for_subsystem(normalized, subsystem_class, dictionary, evidence)
        # confirmed_kpis 覆盖
        if confirmed_kpis:
            for k, v in confirmed_kpis.items():
                if k in kpis:
                    kpis[k] = KpiExtraction(
                        kpi_name=k, value=v, unit=kpis[k].unit,
                        evidence_token=str(v), rule="confirmed_kpi", status="extracted",
                    )
    else:
        kpis = {}

    return ProductGoalParseResult(
        raw_text=text,
        subsystem_class=subsystem_class,
        subsystem_status=subsystem_status,
        kpis=kpis,
        parser_evidence=evidence,
    )
```

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：PASS（19 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tools/product_goal_parser.py tests/test_product_goal_parser.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 实现第 2 层 KPI 抽取与单位归一"
```

---

## Task 6：第 3 层歧义检测 + confirmed override 边界

**Files:**
- Modify: `tools/product_goal_parser.py`
- Test: `tests/test_product_goal_parser.py`（追加）

- [ ] **Step 1：写失败测试 — 数字共享 / 真冲突 / confirmed 覆盖**

```python
def test_numbers_can_be_shared_across_kpis_no_conflict():
    """50kg + 50mm 各归各位，不算冲突。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 升 50kg 行程 50mm")
    assert result.kpis["load_kg"].value == 50
    assert result.kpis["load_kg"].status == "extracted"
    assert result.kpis["stroke_mm"].value == 50
    assert result.kpis["stroke_mm"].status == "extracted"


def test_confirmed_kpis_override_parser():
    from tools.product_goal_parser import parse_product_goal

    # 自然语言抽到 50，confirmed 传 100
    result = parse_product_goal(
        text="升降平台 升 50kg",
        confirmed_kpis={"load_kg": 100.0},
    )
    assert result.kpis["load_kg"].value == 100
    assert result.kpis["load_kg"].rule == "confirmed_kpi"


def test_confirmed_subsystem_overrides_parser():
    from tools.product_goal_parser import parse_product_goal

    # 自然语言识别为 EE，confirmed 强制 lifting
    result = parse_product_goal(
        text="末端执行机构",
        confirmed_subsystem="lifting_platform",
    )
    assert result.subsystem_class == "lifting_platform"


def test_kpi_extraction_does_not_leak_cad_param_names():
    """入口层和 CAD 层严格分离：kpis 字段绝不含 PARAM_L25 / SENSOR_STROKE 等。"""
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text="升降平台 升 50kg 行程 200mm 350x230 平台")
    for kpi in result.kpis.values():
        forbidden = {"PARAM_L25", "PARAM_L27", "SENSOR_STROKE", "PITCH"}
        assert kpi.kpi_name not in forbidden
        if kpi.evidence_token:
            assert kpi.evidence_token not in forbidden
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：PASS（前几个 confirmed 测试可能已通过 task 5 实现，验证哪些 fail 后修）

- [ ] **Step 3：补缺失逻辑**

主函数 `parse_product_goal` 已含 `confirmed_kpis` 和 `confirmed_subsystem` 处理。如某测试 fail，按 fail 信息修。

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：PASS（23 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tools/product_goal_parser.py tests/test_product_goal_parser.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 完善 confirmed override 边界与歧义测试"
```

---

## Task 7：not_yet_implemented + ambiguous 子系统场景测试

**Files:**
- Test: `tests/test_product_goal_parser.py`（追加最后一批）

- [ ] **Step 1：写测试 — 17 个 not_yet_implemented 各 1 例 + 输入校验**

```python
@pytest.mark.parametrize("text,expected_class", [
    ("做导航 SLAM", "navigation"),
    ("运动控制系统", "motion_ctrl"),
    ("电气系统设计", "electrical"),
    ("通信总线", "communication"),
    ("充电桩", "charging"),
    ("耦合剂", "couplant"),
    ("检测传感", "detection"),
    ("集成总成", "integration"),
    ("输出端", "output"),
    ("专利布局", "patent"),
    ("项目规划", "plan"),
    ("电源系统", "power"),
    ("机器人平台", "robot_platform"),
    ("安全系统", "safety"),
    ("软件代码", "software"),
    ("系统架构", "sys_arch"),
    ("预算成本", "budget"),
])
def test_not_yet_implemented_subsystem_recognized(text, expected_class):
    from tools.product_goal_parser import parse_product_goal

    result = parse_product_goal(text=text)
    assert result.subsystem_class == expected_class
    assert result.subsystem_status == "not_yet_implemented"
    assert result.kpis == {}  # not_yet_implemented 不抽 KPI


def test_unknown_input_examples():
    from tools.product_goal_parser import parse_product_goal

    for text in ["xyz123 abc", "做一个未知设备", "完全不相关的文字"]:
        result = parse_product_goal(text=text)
        assert result.subsystem_status == "unknown"
```

- [ ] **Step 2：跑测试验证通过**

```bash
python -m pytest tests/test_product_goal_parser.py -v
```

预期：PASS（41 例：23 + 17 not_yet + 1 unknown）

- [ ] **Step 3：commit**

```bash
git -C .worktrees/product-goal-entry add tests/test_product_goal_parser.py
git -C .worktrees/product-goal-entry commit -m "test(product-goal): 补 17 个 not_yet_implemented + unknown 场景"
```

---

## CHECKPOINT 2（Task 4-7 完成）

**用户确认问题**：
1. 41 个解析器测试全 PASS 后，对 NFKC / 数字共享 / regex 短路行为是否符合预期？
2. confirmed override 优先级（confirmed > 自然语言）是否符合"用户主导"原则？
3. parser_evidence 字段是否够透明可审？

**确认后进入 CP-3（Task 8-10）。**

---

## Task 8：write_project_goal_guide 入口骨架（4 简单状态）

**Files:**
- Modify: `tools/project_guide.py`
- Create: `tests/test_project_goal_guide.py`

- [ ] **Step 1：写失败测试 — 4 简单状态（needs_product_goal / unknown / not_yet_implemented / needs_subsystem_confirmation）**

```python
# tests/test_project_goal_guide.py
"""产品目标入口端到端测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_empty_product_goal_writes_needs_product_goal_guide(tmp_path):
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(tmp_path, product_goal="")

    assert report["entry_mode"] == "product_goal"
    assert report["status"] == "needs_product_goal"
    assert report["mutates_pipeline_state"] is False
    assert report["does_not_scan_directories"] is True
    assert report["next_action"]["kind"] == "supply_product_goal"
    assert "schema_version" in report
    assert "generated_at" in report
    assert "ordinary_user_message" in report

    target = tmp_path / ".cad-spec-gen" / "project-guide" / "PROJECT_GUIDE.json"
    assert target.is_file()


def test_unknown_subsystem_returns_terminal_status(tmp_path):
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(tmp_path, product_goal="完全未知的 xyzzy 设备")

    assert report["status"] == "unknown_subsystem"
    assert report["next_action"]["kind"] == "list_supported_subsystems"


def test_not_yet_implemented_includes_alternatives(tmp_path):
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(tmp_path, product_goal="做导航 SLAM")

    assert report["status"] == "not_yet_implemented"
    assert report["next_action"]["kind"] == "wait_for_implementation"
    alts = report["next_action"]["alternatives"]
    assert "lifting_platform" in alts["implemented_subsystems"]
    assert "end_effector" in alts["implemented_subsystems"]
    assert "switch_example" in alts


def test_ambiguous_subsystem_writes_needs_subsystem_confirmation(tmp_path):
    from tools.project_guide import write_project_goal_guide

    # "升降"是 supporting_terms，无 primary → ambiguous
    report = write_project_goal_guide(tmp_path, product_goal="升降 50kg 设备")

    assert report["status"] == "needs_subsystem_confirmation"
    assert report["next_action"]["kind"] == "confirm_subsystem"
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_project_goal_guide.py -v
```

预期：FAIL — `write_project_goal_guide` 未定义

- [ ] **Step 3：实现 `write_project_goal_guide`（追加到 `tools/project_guide.py`）**

```python
# 追加到 tools/project_guide.py 末尾
def write_project_goal_guide(
    project_root: str | Path,
    product_goal: str,
    *,
    design_doc: str | Path | None = None,
    confirmed_subsystem: str | None = None,
    confirmed_kpis: Mapping[str, float | tuple[float, float]] | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """产品目标自然语言入口；写 PROJECT_GUIDE.json。"""
    from tools.product_goal_parser import parse_product_goal

    root = Path(project_root).resolve()
    target = _project_entry_guide_target(root, output_path)

    parse_result = parse_product_goal(
        text=product_goal,
        confirmed_subsystem=confirmed_subsystem,
        confirmed_kpis=confirmed_kpis,
    )

    status, next_action = _derive_status_and_next_action(parse_result, design_doc, root)

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_mode": "product_goal",
        "status": status,
        "ordinary_user_message": _ordinary_user_message_for_goal(status),
        "mutates_pipeline_state": False,
        "does_not_scan_directories": True,
        "product_goal": _serialize_parse_result(parse_result),
        "next_action": next_action,
        "artifacts": {
            "project_guide": project_relative(target, root),
        },
    }

    write_json_atomic(target, report)
    return report


def _derive_status_and_next_action(parse_result, design_doc, root):
    """从 parse 结果派生 status + next_action。"""
    if not parse_result.raw_text or not parse_result.raw_text.strip():
        return "needs_product_goal", {
            "kind": "supply_product_goal",
            "preview_cli": "python cad_pipeline.py project-guide --product-goal \"<描述你的产品>\"",
        }

    if parse_result.subsystem_status == "ambiguous":
        return "needs_subsystem_confirmation", {
            "kind": "confirm_subsystem",
            "preview_cli": "python cad_pipeline.py project-guide --product-goal \"...\" --confirm-subsystem <lifting_platform|end_effector>",
        }

    if parse_result.subsystem_status == "unknown":
        return "unknown_subsystem", {
            "kind": "list_supported_subsystems",
            "supported": ["lifting_platform", "end_effector"],
        }

    if parse_result.subsystem_status == "not_yet_implemented":
        return "not_yet_implemented", {
            "kind": "wait_for_implementation",
            "alternatives": {
                "implemented_subsystems": ["lifting_platform", "end_effector"],
                "switch_example": 'python cad_pipeline.py project-guide --product-goal "做升降平台 50kg"',
                "feedback_url": "https://github.com/proecheng/cad-spec-gen/issues/new",
            },
        }

    # implemented 分支留给 task 9（needs_kpi / needs_design_doc / ready_for_cad_spec）
    return "needs_kpi_confirmation", {
        "kind": "supply_missing_kpis",
        "preview_cli": "python cad_pipeline.py project-guide --product-goal \"...\" --confirm-X ...",
    }


def _ordinary_user_message_for_goal(status: str) -> str:
    return {
        "needs_product_goal": "请用 --product-goal \"<描述你的产品>\" 启动。",
        "needs_subsystem_confirmation": "产品类别含混，请用 --confirm-subsystem <name> 指定。",
        "not_yet_implemented": "该子系统在路线图但尚未实现；可考虑 lifting_platform 或 end_effector。",
        "unknown_subsystem": "未识别此产品类别；当前支持 lifting_platform、end_effector。",
        "needs_kpi_confirmation": "请用 --confirm-X flag 补齐缺失 KPI 后重跑。",
        "needs_design_doc": "KPI 已齐，请用 --design-doc <path> 提供设计文档后重跑。",
        "ready_for_cad_spec": "一切就绪，可执行 cad-spec 生成 CAD_SPEC.md。",
    }.get(status, "(未知状态)")


def _serialize_parse_result(parse_result) -> dict[str, Any]:
    kpi_extracted: dict[str, Any] = {}
    kpi_missing: list[str] = []
    for name, k in parse_result.kpis.items():
        if k.status == "extracted":
            kpi_extracted[name] = k.value
        else:
            kpi_missing.append(name)
    return {
        "text": parse_result.raw_text,
        "subsystem_class": parse_result.subsystem_class,
        "subsystem_status": parse_result.subsystem_status,
        "kpi_extracted": kpi_extracted,
        "kpi_missing": kpi_missing,
        "parser_evidence": parse_result.parser_evidence,
    }
```

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_project_goal_guide.py -v
```

预期：PASS（4 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tools/project_guide.py tests/test_project_goal_guide.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 增加 write_project_goal_guide 入口与 4 状态分流"
```

---

## Task 9：needs_design_doc + ready_for_cad_spec + needs_kpi_confirmation

**Files:**
- Modify: `tools/project_guide.py`
- Test: `tests/test_project_goal_guide.py`（追加）

- [ ] **Step 1：写失败测试 — 3 状态分流（KPI 缺/齐 × design_doc 缺/齐）**

```python
# 追加
def test_needs_kpi_when_subsystem_clear_but_kpis_missing(tmp_path):
    from tools.project_guide import write_project_goal_guide

    # 仅 product_goal，缺 KPI
    report = write_project_goal_guide(tmp_path, product_goal="做一个升降平台")

    assert report["status"] == "needs_kpi_confirmation"
    assert "load_kg" in report["product_goal"]["kpi_missing"]
    assert "stroke_mm" in report["product_goal"]["kpi_missing"]
    assert "platform_size_mm" in report["product_goal"]["kpi_missing"]
    assert report["next_action"]["kind"] == "supply_missing_kpis"


def test_needs_design_doc_when_kpis_complete_but_no_design_doc(tmp_path):
    """rev 4 DR-1：KPI 齐 + 无 design_doc → needs_design_doc（非 ready）。"""
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(
        tmp_path,
        product_goal="升降平台 升 50kg 行程 200mm 平台 350x230",
    )

    assert report["status"] == "needs_design_doc"
    assert report["next_action"]["kind"] == "supply_design_doc"
    assert report["product_goal"]["kpi_missing"] == []


def test_ready_for_cad_spec_when_kpis_and_design_doc_both_present(tmp_path):
    from tools.project_guide import write_project_goal_guide

    design_doc = tmp_path / "docs" / "design" / "XX-lifting_platform.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# 设计文档", encoding="utf-8")

    report = write_project_goal_guide(
        tmp_path,
        product_goal="升降平台 升 50kg 行程 200mm 平台 350x230",
        design_doc=design_doc,
    )

    assert report["status"] == "ready_for_cad_spec"
    assert report["next_action"]["kind"] == "run_cad_spec"
    assert "lifting_platform" in report["next_action"]["preview_cli"]


def test_confirmed_kpis_can_complete_missing_kpis(tmp_path):
    from tools.project_guide import write_project_goal_guide

    design_doc = tmp_path / "docs" / "design" / "XX-lifting_platform.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# 设计文档", encoding="utf-8")

    report = write_project_goal_guide(
        tmp_path,
        product_goal="做一个升降平台",
        confirmed_kpis={
            "load_kg": 50.0,
            "stroke_mm": 200.0,
            "platform_size_mm": (350.0, 230.0),
        },
        design_doc=design_doc,
    )

    assert report["status"] == "ready_for_cad_spec"
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_project_goal_guide.py -v
```

预期：FAIL — `_derive_status_and_next_action` implemented 分支当前只返回 needs_kpi_confirmation

- [ ] **Step 3：扩展 implemented 分支**

在 `tools/project_guide.py` 中替换 `_derive_status_and_next_action` 的 `# implemented 分支` 注释起的部分：

```python
    # implemented 分支：KPI 完整性检查 → design_doc 检查
    missing = [name for name, k in parse_result.kpis.items() if k.status != "extracted"]
    if missing:
        return "needs_kpi_confirmation", {
            "kind": "supply_missing_kpis",
            "missing_kpis": missing,
            "preview_cli": _build_kpi_preview_cli(parse_result.subsystem_class, missing),
        }

    if not design_doc:
        return "needs_design_doc", {
            "kind": "supply_design_doc",
            "preview_cli": (
                f"python cad_pipeline.py project-guide --product-goal \"...\" "
                f"--design-doc docs/design/<chapter>-{parse_result.subsystem_class}.md"
            ),
        }

    return "ready_for_cad_spec", {
        "kind": "run_cad_spec",
        "preview_cli": (
            f"python cad_pipeline.py spec --subsystem {parse_result.subsystem_class} "
            f"--design-doc {design_doc}"
        ),
    }


def _build_kpi_preview_cli(subsystem: str, missing: list[str]) -> str:
    """构造缺失 KPI 的 confirm CLI 模板。"""
    flag_map = {
        "load_kg": "--confirm-load 50",
        "stroke_mm": "--confirm-stroke 200",
        "platform_size_mm": "--confirm-platform-size 350x230",
        "rot_range_deg": "--confirm-rot-range 135",
        "switch_time_s": "--confirm-switch-time 1.5",
        "flange_dia_mm": "--confirm-flange-dia 90",
    }
    flags = " ".join(flag_map[k] for k in missing if k in flag_map)
    return f"python cad_pipeline.py project-guide --product-goal \"...\" {flags}"
```

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_project_goal_guide.py -v
```

预期：PASS（8 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tools/project_guide.py tests/test_project_goal_guide.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 实现 needs_design_doc + ready_for_cad_spec 分流"
```

---

## Task 10：preview_cli 安全降级 + path_policy 守护

**Files:**
- Modify: `tools/project_guide.py`
- Test: `tests/test_project_goal_guide.py`（追加）

- [ ] **Step 1：写失败测试 — preview_cli 含 user text 时降级 + 输出路径越界**

```python
def test_preview_cli_unsafe_when_text_contains_special_chars(tmp_path):
    """rev 4 DR-4：含 \" 转义触发降级。"""
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(
        tmp_path,
        product_goal='升降平台 升 50kg "高精度" 平台 350x230 行程 200mm',
    )

    # 因含中文 + " → _safe_cli_token 必返 false
    assert report["next_action"].get("preview_cli_unsafe") is True
    # 降级文案不含原 user text
    cli = report["next_action"].get("preview_cli", "")
    assert '"高精度"' not in cli
    assert "请用 --confirm" in cli or "用 --confirm" in cli


def test_output_path_outside_project_guide_dir_rejected(tmp_path):
    from tools.project_guide import write_project_goal_guide

    bad_output = tmp_path / "elsewhere" / "PROJECT_GUIDE.json"
    bad_output.parent.mkdir(parents=True)

    with pytest.raises(ValueError, match="PROJECT_GUIDE.json"):
        write_project_goal_guide(
            tmp_path,
            product_goal="做一个升降平台",
            output_path=bad_output,
        )


def test_no_forbidden_secrets_in_report(tmp_path):
    """复用既有 _assert_no_forbidden_fields 守护 — 报告永不含 api_key/url 等敏感字段。"""
    from tools.project_guide import write_project_goal_guide

    report = write_project_goal_guide(
        tmp_path,
        product_goal="升降平台 升 50kg 行程 200mm 平台 350x230",
    )

    forbidden = {"api_key", "key", "secret", "url", "base_url", "endpoint"}

    def _walk(value):
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value), f"forbidden: {value}"
            for v in value.values():
                _walk(v)
        elif isinstance(value, list):
            for v in value:
                _walk(v)

    _walk(report)
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_project_goal_guide.py -v
```

预期：FAIL — preview_cli 当前直接拼接 user text

- [ ] **Step 3：补 preview_cli 降级逻辑**

修改 `_derive_status_and_next_action` 使所有返回 next_action 时套 `_sanitize_preview_cli`：

```python
def _sanitize_preview_cli(action: dict[str, Any], parse_result) -> dict[str, Any]:
    """检查 next_action 中所有 preview_cli 是否含 user text；含则降级。"""
    if not parse_result.raw_text:
        return action

    cli = action.get("preview_cli")
    if cli and parse_result.raw_text in cli:
        # cli 含原 user text；用 _safe_cli_token 校验
        if not _safe_cli_token(parse_result.raw_text):
            action["preview_cli_unsafe"] = True
            action["preview_cli"] = (
                "<user_text 含特殊字符；请用 --confirm-X flag 直接传值，不通过自然语言>"
            )
    return action
```

并在 `_derive_status_and_next_action` 末尾把 `next_action` 套这个函数：

```python
    # ... 函数末尾每个 return 改为：
    # return status, _sanitize_preview_cli(next_action, parse_result)
```

实施时把所有 `return "...", { ... }` 改为先把 dict 赋给变量再走 `_sanitize_preview_cli`。

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_project_goal_guide.py -v
```

预期：PASS（11 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tools/project_guide.py tests/test_project_goal_guide.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 增加 preview_cli 安全降级与 forbidden 字段守护"
```

---

## CHECKPOINT 3（Task 8-10 完成）

**用户确认问题**：
1. 7 状态机（needs_product_goal / unknown / not_yet / ambiguous / needs_kpi / needs_design_doc / ready）是否覆盖所有合理路径？
2. ordinary_user_message 文案是否对外行用户够友好？
3. preview_cli 降级（中文 → unsafe）是否可接受？还是该改 `_safe_cli_token` 放宽中文？

**注意**：当前实现因 `_safe_cli_token` 严格，**所有中文 user text 都会触发降级**。这是 spec rev 4 DR-4 已知行为，确认是否合适。

**确认后进入 CP-4（Task 11-12）。**

---

## Task 11：CLI flags + cmd_project_guide dispatch 扩展

**Files:**
- Modify: `cad_pipeline.py`
- Test: `tests/test_project_goal_guide.py`（追加 CLI 集成）

- [ ] **Step 1：写失败测试 — CLI 解析 + dispatch fallback**

```python
def test_cli_no_flag_writes_needs_product_goal_guide(tmp_path, capsys, monkeypatch):
    """rev 4 DR-3：dispatch 默认分支不 error，写 informative guide。"""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from cad_pipeline import cmd_project_guide

    monkeypatch.chdir(tmp_path)

    args = type("Args", (), {
        "product_goal": None,
        "from_design_doc": False,
        "subsystem": None,
        "design_doc": None,
        "output": None,
        "artifact_index": None,
        "confirm_subsystem": None,
        "confirm_load": None, "confirm_stroke": None, "confirm_platform_size": None,
        "confirm_rot_range": None, "confirm_switch_time": None, "confirm_flange_dia": None,
    })()

    rc = cmd_project_guide(args)
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert rc == 0  # 不 error
    assert report["status"] == "needs_product_goal"
    assert report["entry_mode"] == "product_goal"


def test_cli_collect_confirmed_kpis_handles_unit_suffixes(tmp_path, capsys, monkeypatch):
    """--confirm-load 50kg / 50 / 0.05t 都应解析。"""
    from cad_pipeline import _collect_confirmed_kpis

    args = type("Args", (), {
        "confirm_load": "50kg",
        "confirm_stroke": "200",
        "confirm_platform_size": "350x230",
        "confirm_rot_range": None,
        "confirm_switch_time": None,
        "confirm_flange_dia": None,
    })()

    kpis = _collect_confirmed_kpis(args)
    assert kpis["load_kg"] == 50.0
    assert kpis["stroke_mm"] == 200.0
    assert kpis["platform_size_mm"] == (350.0, 230.0)
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_project_goal_guide.py -v
```

预期：FAIL — `_collect_confirmed_kpis` 不存在 + dispatch 当前默认分支 error return 1

- [ ] **Step 3：在 `cad_pipeline.py` 改 cmd_project_guide + 加 _collect_confirmed_kpis + 加 7 个 CLI flag**

找到 `cmd_project_guide` 函数（约 3663 行）改成：

```python
def cmd_project_guide(args):
    """生成普通用户/大模型只读项目下一步向导。"""
    from tools.project_guide import (
        command_return_code_for_project_guide,
        write_project_entry_guide,
        write_project_goal_guide,
        write_project_guide,
    )

    if getattr(args, "product_goal", None) is not None:  # 新增分支（最高优先级）
        report = write_project_goal_guide(
            PROJECT_ROOT,
            args.product_goal or "",
            design_doc=getattr(args, "design_doc", None),
            confirmed_subsystem=getattr(args, "confirm_subsystem", None),
            confirmed_kpis=_collect_confirmed_kpis(args),
            output_path=getattr(args, "output", None),
        )
    elif getattr(args, "from_design_doc", False):
        if not getattr(args, "design_doc", None):
            log.error("--design-doc is required with --from-design-doc")
            return 1
        report = write_project_entry_guide(
            PROJECT_ROOT,
            args.design_doc,
            output_path=getattr(args, "output", None),
        )
    elif args.subsystem:
        report = write_project_guide(
            PROJECT_ROOT,
            args.subsystem,
            design_doc=getattr(args, "design_doc", None),
            artifact_index_path=getattr(args, "artifact_index", None),
            output_path=getattr(args, "output", None),
        )
    else:
        # rev 4 DR-3：default 分支不再 error；写 informative guide
        report = write_project_goal_guide(
            PROJECT_ROOT,
            "",
            output_path=getattr(args, "output", None),
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    log.info("PROJECT_GUIDE: %s", report.get("ordinary_user_message"))
    return command_return_code_for_project_guide(report)


def _collect_confirmed_kpis(args) -> dict[str, float | tuple[float, float]] | None:
    """从 args 收集 --confirm-X flag 转 KPI dict。"""
    import re as _re

    flag_to_kpi = {
        "confirm_load": ("load_kg", "single"),
        "confirm_stroke": ("stroke_mm", "single"),
        "confirm_platform_size": ("platform_size_mm", "pair"),
        "confirm_rot_range": ("rot_range_deg", "single"),
        "confirm_switch_time": ("switch_time_s", "single"),
        "confirm_flange_dia": ("flange_dia_mm", "single"),
    }
    result: dict[str, float | tuple[float, float]] = {}
    for flag, (kpi_name, shape) in flag_to_kpi.items():
        raw = getattr(args, flag, None)
        if raw is None:
            continue
        if shape == "pair":
            m = _re.match(r"\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)", str(raw))
            if m:
                result[kpi_name] = (float(m.group(1)), float(m.group(2)))
        else:
            m = _re.match(r"\s*(\d+(?:\.\d+)?)", str(raw))
            if m:
                result[kpi_name] = float(m.group(1))
    return result or None
```

找到 `project-guide` argparse 块（约 4537 行 `parser.add_subparsers().add_parser("project-guide", ...)` 后的 add_argument 区），追加 7 个 flag：

```python
    p_project_guide.add_argument("--product-goal", type=str, default=None,
                                  help="自然语言产品目标（外行用户入口）")
    p_project_guide.add_argument("--confirm-subsystem", type=str, default=None)
    p_project_guide.add_argument("--confirm-load", type=str, default=None,
                                  help="升降平台载荷 kg；接受 '50' 或 '50kg'")
    p_project_guide.add_argument("--confirm-stroke", type=str, default=None)
    p_project_guide.add_argument("--confirm-platform-size", type=str, default=None,
                                  help="平台尺寸，例 '350x230'")
    p_project_guide.add_argument("--confirm-rot-range", type=str, default=None)
    p_project_guide.add_argument("--confirm-switch-time", type=str, default=None)
    p_project_guide.add_argument("--confirm-flange-dia", type=str, default=None)
```

- [ ] **Step 4：跑测试验证通过**

```bash
python -m pytest tests/test_project_goal_guide.py -v
```

预期：PASS（13 例）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add cad_pipeline.py tests/test_project_goal_guide.py
git -C .worktrees/product-goal-entry commit -m "feat(product-goal): 增加 CLI flags 与 dispatch fallback"
```

---

## Task 12：现有 test_project_guide.py 向后兼容

**Files:**
- Test: `tests/test_project_guide.py`（追加）

- [ ] **Step 1：先跑既有 16 例确认不破坏**

```bash
python -m pytest tests/test_project_guide.py -v
```

预期：16 PASS（现有测试不修改）

- [ ] **Step 2：追加向后兼容测试**

```python
# 追加到 tests/test_project_guide.py
def test_legacy_entry_mode_still_writes_design_doc_value(tmp_path):
    """既有 --from-design-doc 路径写 entry_mode='design_doc'。"""
    from tools.project_guide import write_project_entry_guide

    design_doc = tmp_path / "docs" / "design" / "04-升降平台.md"
    design_doc.parent.mkdir(parents=True)
    design_doc.write_text("# 升降平台", encoding="utf-8")

    report = write_project_entry_guide(tmp_path, design_doc)
    assert report["entry_mode"] == "design_doc"  # 不漂到 "from_design_doc"


def test_old_project_guide_json_without_new_fields_still_readable(tmp_path):
    """旧 PROJECT_GUIDE.json 没 entry_mode 字段，新 reader 不应 KeyError。"""
    import json

    target = tmp_path / ".cad-spec-gen" / "project-guide" / "PROJECT_GUIDE.json"
    target.parent.mkdir(parents=True)

    # 模拟旧 schema：无 entry_mode、无 product_goal
    old_report = {
        "schema_version": 1,
        "status": "needs_subsystem_confirmation",
        "subsystem_candidates": [],
    }
    target.write_text(json.dumps(old_report), encoding="utf-8")

    # 读取应不抛
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded.get("entry_mode") is None  # 优雅 None
    assert loaded.get("product_goal") is None
```

- [ ] **Step 3：跑测试验证通过**

```bash
python -m pytest tests/test_project_guide.py -v
```

预期：18 PASS（16 既有 + 2 新）

- [ ] **Step 4：跑全部解析器 + 入口测试，验证 plan 整体**

```bash
python -m pytest tests/test_product_goal_parser.py tests/test_project_guide.py tests/test_project_goal_guide.py -v
```

预期：~72 PASS（41 parser + 18 既有 + 13 新 e2e）

- [ ] **Step 5：commit**

```bash
git -C .worktrees/product-goal-entry add tests/test_project_guide.py
git -C .worktrees/product-goal-entry commit -m "test(product-goal): 增加既有 entry_mode + 旧 schema 向后兼容测试"
```

---

## CHECKPOINT 4（Task 11-12 完成）

**用户确认问题**：
1. 既有 16 个 `test_project_guide.py` 全 PASS 确认无回归？
2. dispatch fallback 行为符合预期（无 flag 不再 error，写 needs_product_goal guide）？
3. CLI `--confirm-load 50kg` / `--confirm-load 50` 都接受是否合理？

**确认后进入 CP-5（Task 13-14）。**

---

## Task 13：dev_sync 镜像验证

**Files:** 仅验证，不修改

- [ ] **Step 1：跑 dev_sync 同步并 check**

```bash
python scripts/dev_sync.py
python scripts/dev_sync.py --check
```

预期：sync 输出新增 `tools/project_guide_dict/*.json` + `tools/product_goal_parser.py` 镜像；check 之后无漂移。

- [ ] **Step 2：验证安装版镜像存在**

```bash
ls src/cad_spec_gen/data/tools/project_guide_dict/
ls src/cad_spec_gen/data/tools/product_goal_parser.py
```

预期：3 个文件 + 1 个文件存在。

- [ ] **Step 3：commit（如有镜像生成）**

```bash
git -C .worktrees/product-goal-entry status --short
# 如有 src/cad_spec_gen/data/tools/* 新文件，使用 -f（被 .gitignore 忽略需强制）
git -C .worktrees/product-goal-entry add -f src/cad_spec_gen/data/tools/project_guide_dict/ src/cad_spec_gen/data/tools/product_goal_parser.py
git -C .worktrees/product-goal-entry commit -m "chore(sync): 纳入产品目标入口安装版镜像"
```

---

## Task 14：文档 + skill metadata

**Files:**
- Modify: `docs/cad-help-guide-zh.md`、`docs/cad-help-guide-en.md`、`.claude/commands/cad-help.md`、`skill_cad_help_zh.md`、`skill.json`
- Test: `tests/test_photo3d_user_flow.py`（追加 docs 描述断言）

- [ ] **Step 1：写失败测试 — docs 包含新模式描述**

```python
# 追加到 tests/test_photo3d_user_flow.py
def test_cad_help_docs_describe_product_goal_entry_mode():
    repo_root = Path(__file__).resolve().parents[1]
    paths = [
        repo_root / "docs" / "cad-help-guide-zh.md",
        repo_root / ".claude" / "commands" / "cad-help.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "--product-goal" in text, f"{path} 缺 --product-goal"
        assert "needs_kpi_confirmation" in text or "需要 KPI" in text
        assert "needs_design_doc" in text or "需要设计文档" in text


def test_skill_metadata_advertises_product_goal_entry():
    repo_root = Path(__file__).resolve().parents[1]
    import json
    skill = json.loads((repo_root / "skill.json").read_text(encoding="utf-8"))

    description = json.dumps(skill, ensure_ascii=False)
    assert "--product-goal" in description, "skill.json 缺 --product-goal 提及"
```

- [ ] **Step 2：跑测试验证失败**

```bash
python -m pytest tests/test_photo3d_user_flow.py -v -k "product_goal"
```

预期：FAIL — 文档未含 `--product-goal`

- [ ] **Step 3：更新 docs/cad-help-guide-zh.md**

加一段（示意，按现有结构插入对应章节）：

```markdown
### 新用户最简启动：产品目标自然语言入口（v2.25+）

不需要设计文档也能启动管线，外行用户用一句产品目标即可开始：

```bash
# 完全空启动 → 系统提示需要产品目标
python cad_pipeline.py project-guide

# 仅自然语言 → 系统识别子系统并列出缺失 KPI
python cad_pipeline.py project-guide --product-goal "做一个能升 50kg 的升降平台"

# 补齐 KPI → 系统提示需要设计文档
python cad_pipeline.py project-guide \
    --product-goal "升降平台" \
    --confirm-load 50 --confirm-stroke 200 --confirm-platform-size 350x230

# 加上设计文档 → 进入 CAD_SPEC 阶段
python cad_pipeline.py project-guide \
    --product-goal "升降平台" \
    --confirm-load 50 --confirm-stroke 200 --confirm-platform-size 350x230 \
    --design-doc docs/design/XX-lifting_platform.md
```

支持的子系统：`lifting_platform`、`end_effector`（其他 17 类在路线图）。

支持的 KPI：
- `lifting_platform`：`--confirm-load <kg>` / `--confirm-stroke <mm>` / `--confirm-platform-size <W×D mm>`
- `end_effector`：`--confirm-rot-range <°>` / `--confirm-switch-time <s>` / `--confirm-flange-dia <mm>`
```

英文版 `cad-help-guide-en.md` 加平行段。

- [ ] **Step 4：更新 .claude/commands/cad-help.md + skill_cad_help_zh.md + skill.json**

加 `--product-goal` 入口提及（参考既有 `--from-design-doc` 段落格式）。

- [ ] **Step 5：跑测试验证通过**

```bash
python -m pytest tests/test_photo3d_user_flow.py -v -k "product_goal"
```

预期：PASS（2 例）

- [ ] **Step 6：跑 dev_sync 镜像更新 + 全套回归**

```bash
python scripts/dev_sync.py
python scripts/dev_sync.py --check

python -m pytest tests/test_product_goal_parser.py tests/test_project_goal_guide.py tests/test_project_guide.py tests/test_photo3d_user_flow.py tests/test_photo3d_packaging_sync.py tests/test_dev_sync_check.py tests/test_data_dir_sync.py -v
```

预期：dev_sync check 通过；所有相关测试 PASS。

- [ ] **Step 7：commit**

```bash
git -C .worktrees/product-goal-entry add docs/ .claude/commands/cad-help.md skill_cad_help_zh.md skill.json tests/test_photo3d_user_flow.py
git -C .worktrees/product-goal-entry add -f src/cad_spec_gen/data/  # 镜像同步
git -C .worktrees/product-goal-entry commit -m "docs(product-goal): 增加产品目标入口用户文档与 skill 元数据"
```

---

## CHECKPOINT 5（Task 13-14 完成）

**用户确认问题**：
1. dev_sync 无漂移确认？
2. 文档对外行用户友好？
3. 全部测试 PASS（41 parser + 13 e2e + 18 既有 + 2 docs = ~74 测试）确认？
4. 准备开 PR 到 main？

**确认后**：

- 更新 `docs/PROGRESS.md` 看板（Phase 1 进度 87% → ~89%）
- 更新 `docs/superpowers/README.md`
- push 分支
- 开 PR

---

## 风险与回滚

| 风险 | 应对 |
|---|---|
| 既有 16 个 `test_project_guide.py` 测试 break | Task 12 必跑既有测试无修改 PASS；任何 break 立即 stop |
| dev_sync 漂移漏检 | Task 13 强制 `--check` 验证 |
| `_safe_cli_token` 太严导致所有用户 text unsafe | CP-3 已显式与用户确认；如需放宽，独立 PR 改进而不在本 plan 内 |
| `cad-spec` 接口变化导致 ready_for_cad_spec preview_cli 失效 | Task 0 grep 已锁定接口；如未来变化在 spec 漂移检查另开 |
| 词典不全，外行用户的措辞不识别 | 设计已显式标 `unknown_subsystem`，给用户反馈链接占位；后续按真实使用反馈扩展 |

---

## 测试覆盖总览

| 测试文件 | 既有 | 新增 | 总计 |
|---|---|---|---|
| `tests/test_product_goal_parser.py` | 0 | ~41 | ~41 |
| `tests/test_project_goal_guide.py` | 0 | ~13 | ~13 |
| `tests/test_project_guide.py` | 16 | 2 | 18 |
| `tests/test_photo3d_user_flow.py`（部分） | (现有) | 2 | (现有+2) |
| **本 plan 新增测试** | — | **~58** | — |
