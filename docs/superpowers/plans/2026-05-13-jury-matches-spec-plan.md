# Jury `matches_spec` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 6th boolean dimension `matches_spec` to photo3d-jury that asks the vision LLM "does this rendered image contain the key features the design doc says it should?" — closing the gap that existing `geometry_preserved` only checks "AI didn't alter source PNG".

**Architecture:** Each photo3d-jury process calls 1 extra LLM (`feature_extractor`) to pull a feature list from `CAD_SPEC.md` + `examples/*设计.md` once; cached to `cad/<sub>/.cad-spec-gen/matches_spec_features.json`. Each per-view vision call gets that list and reports `features_status: [{feature_id, visible, reason}]`. Aggregate at run-scope → `RunVerdict.overall_matches_spec = all(view.matches_spec)`. FAIL feeds existing SP1 jury→prompt retry loop with `prompt_rewriter.hint(view_id, missing_features)`. After N=3 retries still FAIL → write `MATCHES_SPEC_TODO.md` + mark `DELIVERY_PACKAGE.json status=blocked`. Feature extraction LLM failure → `matches_spec=true` (fail-safe).

**Tech Stack:** Python 3.10+ / dataclasses / Jinja2 templates (existing jury prompt) / pytest+mock for L1-L4 / `requires_jury_loop_e2e` pytest marker for L5.

**Spec:** `docs/superpowers/specs/2026-05-13-jury-matches-spec-design.md`

---

## 怎么用这份 plan

- 每个 task 含：**文件 / 步骤（含 code/命令/期望输出）/ 验收**
- Task 粒度 **2–5 分钟**（LLM mock 测试除外）
- 完成一个 task → 在 task 标题前打 `✅` + STATUS doc CURRENT TASK 指针更新；FAIL 打 `❌` + 1–2 行原因
- 卡 30 分钟 → 停下，记 STATUS doc，等下一会话
- 改 tracked file 前 `git status` 看脏文件（除已知的）
- 不许触发 spec §8 不变量

---

## Task 0 · STATUS doc + 实施前 grep verify

**Files:**
- Create: `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`

**目标：** 建跨会话入口 + 验证 spec F5 假设（SP1 jury_loop retry 是 per-view 还是 per-run granularity）。

- [ ] **Step 1: 写 STATUS doc 骨架**

写 `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`，包含：

```markdown
# Jury matches_spec — 跨会话状态文档（v2.37 主线）

> 任何会话开工前先读这一份。

## 一、用大白话说我们在干嘛
让 photo3d-jury 看图后能说"设计文档里说应有的 4 条法兰悬臂，图里我看见了吗"。

## 二、5 条验收（spec §6 透传 + 本地补）
1. L1 parse 老 jury fixture 仍 PASS（向后兼容）
2. L2 aggregate 真值表 PASS
3. L3 feature_extractor mock + fail-safe + 12 限制 PASS
4. L4 retry 集成 mock PASS
5. e2e 跑（手动）：end_effector 现状 PASS + 故意 break 后 FAIL with anchor `flange_arms_4` missing

## 三、Task 进度表
| Task | 内容 | 状态 |
| --- | --- | --- |
| 0 | STATUS + grep verify | ⏳ |
| 1-3 | verdict.py 扩 RunVerdict + features_status | ⏳ |
| 4-5 | feature_extractor.py | ⏳ |
| 6-7 | photo3d_jury 整合 | ⏳ |
| 8 | prompt_rewriter hint | ⏳ |
| 9 | jury_loop retry 集成 | ⏳ |
| 10 | delivery_pack TODO 写入 | ⏳ |
| 11 | cmd_enhance_check 透传 | ⏳ |
| 12 | L5 e2e marker fixture | ⏳ |
| 13 | README 模板 + cad-tests 验收页 | ⏳ |
| 14 | 最终验证 + 文档对齐 + retro | ⏳ |

## 四、CURRENT TASK 指针
**Task 0 in progress.**

## 五、不变量（spec §8 重述）
1. 不动 _REQUIRED_BOOL_KEYS 现有 5 个 key 语义
2. feature 抽取永远 per-process 不变 per-view
3. matches_spec FAIL 不阻断 enhance（走 retry）
4. fail-safe：extractor 挂 → matches_spec=true 不阻断
5. 不跑 cad_pipeline.py full
```

- [ ] **Step 2: grep jury_loop 验证 retry granularity 假设（F5 BLOCKER 前置验证）**

```bash
grep -rn "retry\|verdict.*needs_review\|view_id\|attempt" tools/jury_loop/ src/cad_spec_gen/jury_loop/ 2>&1 | head -30
ls tools/jury_loop/
```

观察现 retry 是 per-view 还是 per-run；记录到 STATUS doc 五节"Task 0 grep 结果"附注。如果 per-view → spec §5.1 假设成立，正常继续。如果 per-run → 标记 BLOCKER → 暂停plan + 升级 spec 决策。

- [ ] **Step 3: 验收**

STATUS doc 写完 + grep 结果记录 + 假设确认。

```bash
cat docs/superpowers/JURY_MATCHES_SPEC_STATUS.md | head -20
```

期望：STATUS 文件存在且结构齐全。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/JURY_MATCHES_SPEC_STATUS.md
git commit -m "docs(jury-matches-spec): Task 0 — STATUS doc + retry granularity verify

跨会话状态文档骨架 + grep tools/jury_loop/ 验证 spec F5 BLOCKER 前置假设（retry 是 per-view）。"
```

---

## Task 1 · `verdict.py` 扩 `_REQUIRED_BOOL_KEYS` + features_status（RED → GREEN）

**Files:**
- Modify: `tools/jury/verdict.py`
- Create: `tests/test_jury_matches_spec_aggregate.py`

**目标：** ViewVerdict 加 `features_status: list[dict] = field(default_factory=list)`，`_REQUIRED_BOOL_KEYS` 末尾加 `"matches_spec"`，parse 兼容老 fixture（无 features_status → matches_spec=true）。

- [ ] **Step 1: RED — 写失败测试**

`tests/test_jury_matches_spec_aggregate.py`：

```python
"""L1+L2: ViewVerdict parse 兼容 + matches_spec aggregate 真值表。"""

from __future__ import annotations

import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from jury.verdict import parse_view_verdict, ViewVerdict


def test_parse_view_verdict_back_compat_no_features_status():
    """L1 老 fixture (无 features_status) → matches_spec 默认 True。"""
    content = json.dumps({
        "semantic_checks": {
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        "photoreal_score": 80,
        "reason": "ok",
    })
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.parse_status == "ok"
    assert v.semantic_checks["matches_spec"] is True, "无 features 时 matches_spec 默认 True"
    assert v.features_status == []


def test_parse_view_verdict_with_features_all_visible():
    """L2 所有 features visible → matches_spec True。"""
    content = json.dumps({
        "semantic_checks": {
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        "photoreal_score": 80,
        "reason": "ok",
        "features_status": [
            {"feature_id": "flange_arms_4", "visible": True, "reason": "4 arms visible"},
            {"feature_id": "peek_ring", "visible": True, "reason": "ring at base"},
        ],
    })
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.semantic_checks["matches_spec"] is True
    assert len(v.features_status) == 2


def test_parse_view_verdict_with_one_feature_invisible():
    """L2 任一 feature invisible → matches_spec False。"""
    content = json.dumps({
        "semantic_checks": {
            "geometry_preserved": True,
            "material_consistent": True,
            "photorealistic": True,
            "no_extra_parts": True,
            "no_missing_parts": True,
        },
        "photoreal_score": 80,
        "reason": "ok",
        "features_status": [
            {"feature_id": "flange_arms_4", "visible": False, "reason": "disc only"},
            {"feature_id": "peek_ring", "visible": True, "reason": "ring at base"},
        ],
    })
    v = parse_view_verdict(content, finish_reason="stop")
    assert v.semantic_checks["matches_spec"] is False
    assert v.features_status[0]["visible"] is False
```

- [ ] **Step 2: 跑测试看 RED**

```bash
python -m pytest tests/test_jury_matches_spec_aggregate.py -v
```

期望：3 test FAIL（`matches_spec` 字段不存在 / features_status 字段不存在）。

- [ ] **Step 3: GREEN — 扩 verdict.py**

修改 `tools/jury/verdict.py`：

```python
# 顶部常量改
_REQUIRED_BOOL_KEYS: tuple[str, ...] = (
    "geometry_preserved",
    "material_consistent",
    "photorealistic",
    "no_extra_parts",
    "no_missing_parts",
    "matches_spec",  # NEW v2.37: 设计文档语义对账
)


# ViewVerdict 加字段（注意 frozen=True 需要 field(default_factory=list)）
from dataclasses import field

@dataclass(frozen=True)
class ViewVerdict:
    semantic_checks: dict[str, bool]
    photoreal_score: int
    reason: str
    parse_status: Literal["ok"]
    parse_anomalies: list[str] = field(default_factory=list)
    verdict: Literal["accepted", "preview", "needs_review"] = "accepted"
    features_status: list[dict] = field(default_factory=list)  # NEW
```

修 parse_view_verdict — 在已有 5 key 校验逻辑之后，加一段：

```python
# matches_spec aggregate (v2.37+)
features_status = payload.get("features_status", [])
if not isinstance(features_status, list):
    features_status = []
    anomalies.append("features_status_invalid")

# aggregate: 无 features → True（向后兼容）；所有 visible → True；任一 invisible → False
if features_status:
    checks["matches_spec"] = all(
        bool(f.get("visible", False))
        for f in features_status
        if isinstance(f, dict)
    )
else:
    checks["matches_spec"] = True  # backward compat
```

把 features_status 透传到 ViewVerdict 构造里。

- [ ] **Step 4: 跑测试看 GREEN**

```bash
python -m pytest tests/test_jury_matches_spec_aggregate.py -v
```

期望：3 test PASS。

- [ ] **Step 5: 回归验证**

```bash
python -m pytest tests/jury/ -q
```

期望：所有现有 jury 测试仍 PASS（向后兼容验证）。

- [ ] **Step 6: Commit**

```bash
git add tools/jury/verdict.py tests/test_jury_matches_spec_aggregate.py
git commit -m "feat(jury): Task 1 — ViewVerdict 加 features_status + matches_spec aggregate

_REQUIRED_BOOL_KEYS += 'matches_spec'；ViewVerdict 加 features_status
field(default_factory=list)；parse_view_verdict aggregate rules: 无 features
默认 True 向后兼容；3 test PASS（L1 兼容 + L2 真值表 2 个）。"
```

---

## Task 2 · `verdict.py` 加 `RunVerdict` + `aggregate_run_verdict()`（spec F1 修复落地）

**Files:**
- Modify: `tools/jury/verdict.py`
- Modify: `tests/test_jury_matches_spec_aggregate.py`

**目标：** 加 jury-level summary 数据类（spec §5.2.2 F1 BLOCKER 修复要求）。

- [ ] **Step 1: RED — 写测试**

在 `tests/test_jury_matches_spec_aggregate.py` 末尾追加：

```python
def test_aggregate_run_verdict_all_views_pass():
    from jury.verdict import aggregate_run_verdict, ViewVerdict

    v1 = ViewVerdict(
        semantic_checks={"matches_spec": True, "geometry_preserved": True,
                         "material_consistent": True, "photorealistic": True,
                         "no_extra_parts": True, "no_missing_parts": True},
        photoreal_score=80, reason="ok", parse_status="ok",
        features_status=[{"feature_id": "f1", "visible": True, "reason": "ok"}],
    )
    v2 = ViewVerdict(
        semantic_checks={"matches_spec": True, "geometry_preserved": True,
                         "material_consistent": True, "photorealistic": True,
                         "no_extra_parts": True, "no_missing_parts": True},
        photoreal_score=80, reason="ok", parse_status="ok",
        features_status=[{"feature_id": "f1", "visible": True, "reason": "ok"}],
    )
    run = aggregate_run_verdict({"V1": v1, "V2": v2})
    assert run.overall_matches_spec is True
    assert run.per_view_failed_features == {}


def test_aggregate_run_verdict_one_view_fails():
    from jury.verdict import aggregate_run_verdict, ViewVerdict

    v_pass = ViewVerdict(
        semantic_checks={"matches_spec": True, "geometry_preserved": True,
                         "material_consistent": True, "photorealistic": True,
                         "no_extra_parts": True, "no_missing_parts": True},
        photoreal_score=80, reason="ok", parse_status="ok",
        features_status=[{"feature_id": "f1", "visible": True, "reason": "ok"}],
    )
    v_fail = ViewVerdict(
        semantic_checks={"matches_spec": False, "geometry_preserved": True,
                         "material_consistent": True, "photorealistic": True,
                         "no_extra_parts": True, "no_missing_parts": True},
        photoreal_score=80, reason="missing arms", parse_status="ok",
        features_status=[
            {"feature_id": "flange_arms_4", "visible": False, "reason": "disc only"},
            {"feature_id": "peek_ring", "visible": True, "reason": "ring ok"},
        ],
    )
    run = aggregate_run_verdict({"V1": v_pass, "V4": v_fail})
    assert run.overall_matches_spec is False
    assert run.per_view_failed_features == {"V4": ["flange_arms_4"]}
```

- [ ] **Step 2: 跑测试看 RED**

```bash
python -m pytest tests/test_jury_matches_spec_aggregate.py::test_aggregate_run_verdict_all_views_pass tests/test_jury_matches_spec_aggregate.py::test_aggregate_run_verdict_one_view_fails -v
```

期望：FAIL with "aggregate_run_verdict / RunVerdict not defined"。

- [ ] **Step 3: GREEN — 加 RunVerdict + 聚合函数**

在 `tools/jury/verdict.py` ViewVerdict 之后追加：

```python
@dataclass(frozen=True)
class RunVerdict:
    """整 photo3d-jury 进程的 jury-level summary (v2.37+)。"""
    view_verdicts: dict[str, ViewVerdict]
    overall_matches_spec: bool
    per_view_failed_features: dict[str, list[str]] = field(default_factory=dict)


def aggregate_run_verdict(view_verdicts: dict[str, ViewVerdict]) -> RunVerdict:
    """聚合多视角 verdict → RunVerdict。

    overall_matches_spec = all(view.semantic_checks["matches_spec"] for view)
    per_view_failed_features = {view_id: [feature_id]} 给 prompt_rewriter 用
    """
    overall = all(
        v.semantic_checks.get("matches_spec", True) for v in view_verdicts.values()
    )
    failed: dict[str, list[str]] = {}
    for view_id, v in view_verdicts.items():
        missing = [
            f["feature_id"] for f in v.features_status
            if isinstance(f, dict) and not f.get("visible", True)
        ]
        if missing:
            failed[view_id] = missing
    return RunVerdict(
        view_verdicts=view_verdicts,
        overall_matches_spec=overall,
        per_view_failed_features=failed,
    )
```

- [ ] **Step 4: 跑测试看 GREEN**

```bash
python -m pytest tests/test_jury_matches_spec_aggregate.py -v
```

期望：5 test 全 PASS（3 老 + 2 新）。

- [ ] **Step 5: Commit**

```bash
git add tools/jury/verdict.py tests/test_jury_matches_spec_aggregate.py
git commit -m "feat(jury): Task 2 — RunVerdict + aggregate_run_verdict（F1 BLOCKER 修复）

加 jury-level summary 类 + 聚合函数：overall_matches_spec / per_view_failed_features。
2 新 test PASS。"
```

---

## Task 3 · 现有 fixture / smoke 兼容性回归扫一遍

**Files:**
- 检查所有 `tests/jury_loop/` `tests/jury/` 现有测试

**目标：** 全套件 PASS（无 regression）。

- [ ] **Step 1: 跑所有 jury 相关测试**

```bash
python -m pytest tests/jury/ tests/jury_loop/ -q
```

期望：全 PASS。如有 FAIL → 看是 parse 兼容性破了（处理 features_status absent case），修 verdict.py。

- [ ] **Step 2: 跑大套件烟雾**

```bash
python -m pytest tests/ -q -x --timeout 60 2>&1 | tail -10
```

期望：现有 jury 系列测试全 PASS。其他测试不受本 task 影响（仅改 verdict.py 内 dataclass + parse 逻辑）。

- [ ] **Step 3: Commit（如果有兼容性 micro-fix）**

```bash
git add tools/jury/verdict.py
git commit -m "fix(jury): Task 3 — features_status absent 兼容性 micro-fix（如有）"
```

如果 step 1+2 都直接 PASS 且不需要 fix → 跳过 commit。

---

## Task 4 · `feature_extractor.py` RED+GREEN（核心模块）

**Files:**
- Create: `tools/jury/feature_extractor.py`
- Create: `tests/test_jury_feature_extractor.py`

**目标：** 写 `extract()` 函数：读 spec/design doc → LLM call → 输出 JSON{features} → cache 落盘 → 失败 fail-safe 返回空 features。

- [ ] **Step 1: RED — 写 4 个测试**

`tests/test_jury_feature_extractor.py`：

```python
"""L3 feature_extractor 单元测试 — mock LLM + cache + fail-safe + 12 限制。"""

from __future__ import annotations

import json
import pathlib
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from jury.feature_extractor import extract, _MAX_FEATURES


def _mock_llm_returning(features: list[dict]) -> MagicMock:
    """构造一个返回 features JSON 的假 LLM client。"""
    client = MagicMock()
    client.complete.return_value = json.dumps({"features": features})
    return client


def test_extract_happy_path_writes_cache_and_returns_features(tmp_path: pathlib.Path):
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n\nFLANGE_BODY_OD = 90 mm\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("法兰应含 4 条径向悬臂\n", encoding="utf-8")
    cache_dir = tmp_path / ".cad-spec-gen"

    features = [
        {"feature_id": "flange_arms_4",
         "description_cn": "法兰 4 条径向悬臂",
         "expected_in_views": ["V4", "V5"],
         "doc_ref": "design.md L1"},
    ]
    client = _mock_llm_returning(features)

    result = extract(spec_md, design, cache_dir=cache_dir, llm_client=client,
                    subsystem="end_effector", run_id="test-run")

    assert len(result["features"]) == 1
    assert result["features"][0]["feature_id"] == "flange_arms_4"
    # 落盘到 cache 文件
    cache_file = cache_dir / "matches_spec_features.json"
    assert cache_file.exists()
    cached = json.loads(cache_file.read_text(encoding="utf-8"))
    assert cached["subsystem"] == "end_effector"


def test_extract_llm_failure_returns_empty_features_no_raise(tmp_path: pathlib.Path):
    """fail-safe：LLM 抛异常 → 返回 {features: []}（pipeline 继续）。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    client = MagicMock()
    client.complete.side_effect = RuntimeError("503 backend down")

    result = extract(spec_md, design, cache_dir=tmp_path, llm_client=client,
                    subsystem="end_effector", run_id="test-run")
    assert result == {"features": [], "parse_anomalies": ["feature_extraction_failed"]}


def test_extract_truncates_at_12_features(tmp_path: pathlib.Path):
    """spec D6 / §5.2.1：超过 12 条截断 + parse_anomalies。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    too_many = [
        {"feature_id": f"f{i}", "description_cn": f"feature {i}",
         "expected_in_views": None, "doc_ref": ""}
        for i in range(20)
    ]
    client = _mock_llm_returning(too_many)

    result = extract(spec_md, design, cache_dir=tmp_path, llm_client=client,
                    subsystem="end_effector", run_id="test-run")
    assert len(result["features"]) == _MAX_FEATURES
    assert "feature_extraction_truncated" in result.get("parse_anomalies", [])


def test_extract_invalid_json_returns_empty_features(tmp_path: pathlib.Path):
    """LLM 返回非 JSON → fail-safe 不阻断。"""
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    client = MagicMock()
    client.complete.return_value = "not a json at all"

    result = extract(spec_md, design, cache_dir=tmp_path, llm_client=client,
                    subsystem="end_effector", run_id="test-run")
    assert result["features"] == []
    assert "feature_extraction_failed" in result.get("parse_anomalies", [])
```

- [ ] **Step 2: 跑测试看 RED**

```bash
python -m pytest tests/test_jury_feature_extractor.py -v
```

期望：FAIL with "No module named 'jury.feature_extractor'".

- [ ] **Step 3: GREEN — 写 feature_extractor.py**

`tools/jury/feature_extractor.py`：

```python
"""LLM 特征抽取（matches_spec 维度）：从 CAD_SPEC + design doc 拉关键特征列表。

Per spec D1/D7：每个 photo3d-jury 进程调 1 次；text-only endpoint 优先 + vision fallback；
LLM 失败 → fail-safe 返回空 features；超过 12 条截断。
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

_MAX_FEATURES = 12

_PROMPT_TEMPLATE = """\
你是一个 CAD/工业设计领域的特征抽取助手。任务：从下列设计文档片段提取**关键可见特征**，
让视觉 LLM 后续能据此对账渲染图。

要求：
- 仅抽对一张实物渲染图**肉眼能看见**的几何 / 装配 / 颜色 / 位置特征
- 不抽尺寸数字 / 公差 / 材质牌号 这种"看不见但能写出来"的元数据
- 最多 12 条；每条 1 行中文描述（≤40 字）
- 输出严格 JSON：{{"features": [{{"feature_id": "snake_case", "description_cn": "...", "expected_in_views": ["V4","V5"]或null, "doc_ref": "文件名:section/line"}}]}}
- expected_in_views = null 表示所有视角应可见；列表表特定视角应可见
- feature_id 使用 ASCII snake_case，<32 字符，唯一

--- CAD_SPEC.md 内容 ---
{spec_content}

--- 设计文档内容 ---
{design_content}

--- 输出 JSON ---
"""


def extract(
    spec_md_path: pathlib.Path,
    design_doc_path: pathlib.Path,
    *,
    cache_dir: pathlib.Path,
    llm_client: Any,
    subsystem: str,
    run_id: str,
) -> dict:
    """抽取特征列表并落盘 cache。

    Returns:
        {"features": [...], "parse_anomalies": [...]}（异常时 features=[] + anomalies 含 cause）
    """
    anomalies: list[str] = []

    # 读源文件（不存在 → fail-safe）
    try:
        spec_content = spec_md_path.read_text(encoding="utf-8")[:8000]  # 截前 8k 控 token
    except (OSError, UnicodeDecodeError):
        anomalies.append("spec_md_unreadable")
        spec_content = ""
    try:
        design_content = design_doc_path.read_text(encoding="utf-8")[:8000]
    except (OSError, UnicodeDecodeError):
        anomalies.append("design_doc_unreadable")
        design_content = ""

    # 调 LLM
    prompt = _PROMPT_TEMPLATE.format(spec_content=spec_content, design_content=design_content)
    try:
        raw = llm_client.complete(prompt)
    except Exception:  # 任何 LLM 异常 → fail-safe
        return {"features": [], "parse_anomalies": ["feature_extraction_failed"]}

    # parse JSON
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"features": [], "parse_anomalies": ["feature_extraction_failed"]}

    features = payload.get("features", [])
    if not isinstance(features, list):
        return {"features": [], "parse_anomalies": ["feature_extraction_failed"]}

    # 截断
    if len(features) > _MAX_FEATURES:
        features = features[:_MAX_FEATURES]
        anomalies.append("feature_extraction_truncated")

    result = {"features": features, "parse_anomalies": anomalies}

    # 落盘 cache（best-effort，写失败不影响返回）
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_payload = {
            "schema_version": 1,
            "subsystem": subsystem,
            "run_id": run_id,
            "source_files": [str(spec_md_path), str(design_doc_path)],
            "features": features,
            "parse_anomalies": anomalies,
        }
        (cache_dir / "matches_spec_features.json").write_text(
            json.dumps(cache_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass

    return result
```

- [ ] **Step 4: 跑测试看 GREEN**

```bash
python -m pytest tests/test_jury_feature_extractor.py -v
```

期望：4 test PASS。

- [ ] **Step 5: Commit**

```bash
git add tools/jury/feature_extractor.py tests/test_jury_feature_extractor.py
git commit -m "feat(jury): Task 4 — feature_extractor.py + 4 L3 test PASS

LLM 抽 matches_spec features 列表；text-only prompt + JSON 输出；
fail-safe (LLM 抛 / 非 JSON → 空 features)；超 12 条截断；落盘 cache。"
```

---

## Task 5 · feature_extractor LLM client 接口 + text/vision endpoint 抽象（spec F8）

**Files:**
- Modify: `tools/jury/feature_extractor.py`
- Modify: `tests/test_jury_feature_extractor.py`

**目标：** 实现 spec D7/F8：text-only endpoint 优先 + vision fallback。`llm_client.complete()` 接口 if 有 `complete_text` 方法则用 text，否则 fallback 到 `complete`。

- [ ] **Step 1: RED — 加测试**

在 `tests/test_jury_feature_extractor.py` 末尾追加：

```python
def test_extract_prefers_text_endpoint_when_available(tmp_path: pathlib.Path):
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    client = MagicMock()
    client.complete_text = MagicMock(return_value=json.dumps({"features": []}))
    client.complete = MagicMock(return_value=json.dumps({"features": []}))

    extract(spec_md, design, cache_dir=tmp_path, llm_client=client,
            subsystem="end_effector", run_id="test")

    # 优先 text endpoint
    client.complete_text.assert_called_once()
    client.complete.assert_not_called()


def test_extract_falls_back_to_complete_when_no_text_endpoint(tmp_path: pathlib.Path):
    spec_md = tmp_path / "CAD_SPEC.md"
    spec_md.write_text("# Spec\n", encoding="utf-8")
    design = tmp_path / "design.md"
    design.write_text("design\n", encoding="utf-8")

    client = MagicMock(spec=["complete"])  # 仅 complete，无 complete_text
    client.complete.return_value = json.dumps({"features": []})

    extract(spec_md, design, cache_dir=tmp_path, llm_client=client,
            subsystem="end_effector", run_id="test")

    client.complete.assert_called_once()
```

- [ ] **Step 2: 跑测试看 RED**

```bash
python -m pytest tests/test_jury_feature_extractor.py::test_extract_prefers_text_endpoint_when_available -v
```

期望：FAIL（当前 extract 只调 complete）。

- [ ] **Step 3: GREEN — 改 extract LLM 调用逻辑**

在 `tools/jury/feature_extractor.py` 把 `llm_client.complete(prompt)` 行改成：

```python
    # text endpoint 优先（spec F8）；vision fallback
    try:
        if hasattr(llm_client, "complete_text"):
            raw = llm_client.complete_text(prompt)
        else:
            raw = llm_client.complete(prompt)
    except Exception:
        return {"features": [], "parse_anomalies": ["feature_extraction_failed"]}
```

- [ ] **Step 4: 跑测试看 GREEN**

```bash
python -m pytest tests/test_jury_feature_extractor.py -v
```

期望：6 test 全 PASS（4 旧 + 2 新）。

- [ ] **Step 5: Commit**

```bash
git add tools/jury/feature_extractor.py tests/test_jury_feature_extractor.py
git commit -m "feat(jury): Task 5 — feature_extractor text endpoint preference (F8)

extract() 优先 llm_client.complete_text()，无则 fallback 到 complete()。
6/6 test PASS。"
```

---

## Task 6 · `photo3d_jury.py` 启动调 extractor + vision prompt 附 features

**Files:**
- Modify: `tools/photo3d_jury.py`
- Modify: `tests/test_photo3d_jury.py`

**目标：** photo3d_jury 进程启动时调一次 feature_extractor.extract() 拿到 features 列表；每视角 vision LLM call 的 prompt 末尾附加该视角相关 features（按 expected_in_views 过滤）。

- [ ] **Step 1: 看现 photo3d_jury 流程**

```bash
grep -n "def \|vision\|complete\|client" tools/photo3d_jury.py 2>&1 | head -30
```

定位到主入口函数 + LLM 调用点。

- [ ] **Step 2: RED — 加 photo3d_jury 集成测试**

在 `tests/test_photo3d_jury.py`（如不存在则创建）加：

```python
def test_photo3d_jury_calls_feature_extractor_once_per_process(monkeypatch, tmp_path):
    """spec D1：每进程 1 次抽特征，不是 per-view。"""
    from unittest.mock import MagicMock, patch
    import sys; sys.path.insert(0, "tools")

    extract_mock = MagicMock(return_value={"features": [], "parse_anomalies": []})
    with patch("jury.feature_extractor.extract", extract_mock):
        # 模拟 jury 跑 3 视角的 main entry
        # 假设 photo3d_jury 有 jury_run() 函数；按实际接口调
        from photo3d_jury import jury_run  # 名字可能不同，按 step 1 调整
        jury_run(subsystem="end_effector",
                 views=["V1", "V2", "V3"],
                 # ... other args ...
                 )
    assert extract_mock.call_count == 1, "feature_extractor 应每进程仅调 1 次"
```

如 photo3d_jury 实际入口签名不同 → 按 step 1 grep 结果调整测试。

- [ ] **Step 3: 跑测试看 RED**

```bash
python -m pytest tests/test_photo3d_jury.py -v -k "calls_feature_extractor"
```

期望：FAIL（extract 还没被调）。

- [ ] **Step 4: GREEN — 集成到 photo3d_jury.py**

在 photo3d_jury main entry（step 1 找到的）开头调 extractor 一次：

```python
# photo3d_jury.py 顶部
from jury.feature_extractor import extract as _extract_features


def jury_run(subsystem: str, views: list[str], ..., spec_md_path=None, design_doc_path=None, ...):
    # ── NEW v2.37: 进程启动抽 features 一次 ──
    features_result = {"features": [], "parse_anomalies": []}
    if spec_md_path and design_doc_path:
        cache_dir = pathlib.Path("cad") / subsystem / ".cad-spec-gen"
        features_result = _extract_features(
            spec_md_path, design_doc_path,
            cache_dir=cache_dir,
            llm_client=llm_client,  # 用 jury 已有 client
            subsystem=subsystem,
            run_id=run_id,
        )
    features = features_result["features"]

    # 每视角 vision call prompt 附 features
    for view in views:
        relevant = [
            f for f in features
            if not f.get("expected_in_views") or view in f["expected_in_views"]
        ]
        # 把 relevant 列表序列化进 prompt（参考 _PROMPT_VIEW_TEMPLATE 现有结构）
        vision_prompt = _build_view_prompt(view, image, relevant_features=relevant)
        # ... 调 vision LLM ...
```

按 photo3d_jury 现有结构调整，确保：
1. extractor 仅调 1 次（进程级 cache）
2. vision prompt 包含 features 列表 + 输出 schema 要求含 features_status

- [ ] **Step 5: 跑测试看 GREEN**

```bash
python -m pytest tests/test_photo3d_jury.py -v
```

期望：现有 photo3d_jury 测试仍 PASS + 新测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add tools/photo3d_jury.py tests/test_photo3d_jury.py
git commit -m "feat(jury): Task 6 — photo3d_jury 集成 feature_extractor + features in vision prompt

进程启动调 extract() 一次（spec D1 per-process）；每视角 vision prompt 按 expected_in_views
过滤后附 features 列表；要求 vision LLM 返回 features_status。"
```

---

## Task 7 · photo3d_jury 写 `jury_report.json` 含 RunVerdict（F2 wire）

**Files:**
- Modify: `tools/photo3d_jury.py`
- Modify: `tests/test_photo3d_jury.py`

**目标：** spec §5.3 F2 wire：photo3d_jury 跑完所有视角后聚合 RunVerdict 写到 `cad/output/renders/jury_report.json`，含顶层 `overall_matches_spec` + `per_view_failed_features` + per-view 详情。

- [ ] **Step 1: RED — 加测试**

```python
def test_photo3d_jury_writes_jury_report_with_run_verdict(monkeypatch, tmp_path):
    """jury_report.json 写完整 RunVerdict + 顶层 overall_matches_spec 字段。"""
    import json, pathlib
    from unittest.mock import MagicMock

    # 1) Stub LLM 让 jury 跑 2 视角 V1 PASS, V4 FAIL
    fake_view_responses = {
        "V1": json.dumps({
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": True, "no_extra_parts": True,
                                "no_missing_parts": True},
            "photoreal_score": 80, "reason": "ok",
            "features_status": [{"feature_id": "flange_arms_4", "visible": True, "reason": "ok"}],
        }),
        "V4": json.dumps({
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": True, "no_extra_parts": True,
                                "no_missing_parts": True},
            "photoreal_score": 60, "reason": "disc only",
            "features_status": [{"feature_id": "flange_arms_4", "visible": False, "reason": "missing"}],
        }),
    }
    # 2) 实际 mock pattern 按 grep 现 photo3d_jury 主入口签名调整（client / view loop 入口）
    # 3) 调 photo3d_jury 主 run 函数

    # 4) 断言：jury_report.json 写了且含必要字段
    report_path = tmp_path / "cad/output/renders/jury_report.json"
    # (jury 写在 cad/output/renders/，按实现指向 tmp_path 或 monkeypatch CAD_OUTPUT)
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == 2
    assert report["overall_matches_spec"] is False
    assert report["per_view_failed_features"] == {"V4": ["flange_arms_4"]}
    assert report["matches_spec_status"] == "fail"  # Task 9 之前先 fail；retry 接入后改 blocked
    assert report["views"]["V1"]["semantic_checks"]["matches_spec"] is True
    assert report["views"]["V4"]["semantic_checks"]["matches_spec"] is False
    assert report["views"]["V4"]["features_status"][0]["feature_id"] == "flange_arms_4"
```

注：mock pattern 细节按 Task 6 Step 1 grep 结果填（photo3d_jury 现 LLM client 注入点 + view loop 入口）；这里给的是必有 assertion + report 结构骨架，实施者按 grep 结果补 setup。

- [ ] **Step 2: GREEN — 集成 aggregate_run_verdict**

photo3d_jury main entry 结尾：

```python
from jury.verdict import aggregate_run_verdict

# 跑完所有视角后
view_verdicts = {view: parse_view_verdict(...) for view in views}
run_verdict = aggregate_run_verdict(view_verdicts)

# 写 jury_report.json
report = {
    "schema_version": 2,  # bump from 1: now含 matches_spec
    "subsystem": subsystem,
    "run_id": run_id,
    "overall_matches_spec": run_verdict.overall_matches_spec,
    "per_view_failed_features": run_verdict.per_view_failed_features,
    "matches_spec_status": _derive_status(run_verdict),  # pass/warn/fail/blocked
    "views": {
        view: {
            "semantic_checks": v.semantic_checks,
            "photoreal_score": v.photoreal_score,
            "reason": v.reason,
            "features_status": v.features_status,
            "verdict": v.verdict,
            "parse_anomalies": v.parse_anomalies,
        }
        for view, v in view_verdicts.items()
    },
}
report_path = pathlib.Path("cad/output/renders/jury_report.json")
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
```

加 `_derive_status` helper：

```python
def _derive_status(run_verdict: RunVerdict) -> str:
    """retry attempts not tracked here yet — Task 9 wire；先 pass/fail。"""
    return "pass" if run_verdict.overall_matches_spec else "fail"
```

- [ ] **Step 3: 跑测试**

```bash
python -m pytest tests/test_photo3d_jury.py -v
```

期望：测试 PASS + 现有 jury 测试不破。

- [ ] **Step 4: Commit**

```bash
git add tools/photo3d_jury.py tests/test_photo3d_jury.py
git commit -m "feat(jury): Task 7 — photo3d_jury 写 jury_report.json 含 RunVerdict（F2 wire）

aggregate_run_verdict + 顶层 overall_matches_spec / matches_spec_status / per_view_failed_features
+ schema_version bump 1→2。给 cmd_enhance_check (Task 11) 透传准备好数据源。"
```

---

## Task 8 · `prompt_rewriter.py` 加 `hint(view_id, missing_features)` 接口（F5）

**Files:**
- Modify: `tools/jury/prompt_rewriter.py`（如不存在则查实际路径）
- Modify: `tests/jury_loop/` 相关测试

**目标：** prompt rewriter 接受 missing features hint 并把 feature 名拼到 enhance prompt。

- [ ] **Step 1: 看现 prompt_rewriter 结构**

```bash
find tools src -name "prompt_rewriter*" 2>&1 | head -5
grep -rn "def hint\|def rewrite\|missing" tools/jury* src/cad_spec_gen/jury* 2>&1 | head -20
```

- [ ] **Step 2: RED — 写测试**

```python
def test_prompt_rewriter_hint_appends_missing_features():
    from jury.prompt_rewriter import PromptRewriter

    rw = PromptRewriter(...)  # 按现实例化签名
    base = "base prompt for V4 enhance"
    out = rw.hint(view_id="V4", missing_features=["flange_arms_4", "peek_ring"],
                  base_prompt=base)
    assert "flange_arms_4" in out
    assert "peek_ring" in out
    assert "V4" in out
```

- [ ] **Step 3: GREEN — 加 hint 方法**

```python
def hint(self, *, view_id: str, missing_features: list[str], base_prompt: str) -> str:
    """注入 missing features 名到 enhance prompt 末尾。"""
    if not missing_features:
        return base_prompt
    feature_list = ", ".join(missing_features)
    suffix = f"\n\n[matches_spec 反馈 / 视角 {view_id}] 上次未在图里看到以下特征：{feature_list}。\n请在新一轮增强时**保留并强调**这些几何/装配特征的可见性。"
    return base_prompt + suffix
```

- [ ] **Step 4: 跑测试 PASS**

```bash
python -m pytest tests/jury_loop/ -v -k "hint"
```

- [ ] **Step 5: Commit**

```bash
git add tools/jury/prompt_rewriter.py tests/...
git commit -m "feat(jury): Task 8 — prompt_rewriter.hint(view_id, missing_features) (F5)

per-view scope 注入 missing features 名到 enhance prompt 末尾，供 jury_loop retry 用。"
```

---

## Task 9 · jury_loop retry 集成（matches_spec FAIL → needs_review → retry）

**Files:**
- Modify: `tools/jury_loop/` 主调度（按 Task 0 grep 结果调整）
- Test: `tests/jury_loop/test_matches_spec_retry.py`

**目标：** 把 matches_spec=false 接进现有 SP1 retry 闭环。

- [ ] **Step 1: 看现 jury_loop 怎么决定 retry**

```bash
grep -rn "needs_review\|verdict\|retry" tools/jury_loop/ src/cad_spec_gen/jury_loop/ 2>&1 | head -25
```

记录现有 retry 触发条件 + N=3 配置位置。

- [ ] **Step 2: RED — 写测试**

```python
def test_jury_loop_retries_when_matches_spec_false(monkeypatch, tmp_path):
    """matches_spec=false → 视角 verdict=needs_review → retry 该视角。"""
    import json
    from unittest.mock import MagicMock

    # Stub vision LLM: 第一次返回 features_status[0].visible=False, 第二次 True
    call_count = {"vision": 0}
    fake_responses = [
        # 第一次 — fail
        json.dumps({
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": True, "no_extra_parts": True,
                                "no_missing_parts": True},
            "photoreal_score": 70, "reason": "missing arms",
            "features_status": [{"feature_id": "flange_arms_4", "visible": False, "reason": "disc"}],
        }),
        # 第二次（retry）— pass
        json.dumps({
            "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                                "photorealistic": True, "no_extra_parts": True,
                                "no_missing_parts": True},
            "photoreal_score": 85, "reason": "ok",
            "features_status": [{"feature_id": "flange_arms_4", "visible": True, "reason": "4 arms"}],
        }),
    ]

    def fake_vision(prompt, **_):
        call_count["vision"] += 1
        return fake_responses[min(call_count["vision"] - 1, len(fake_responses) - 1)]

    # 调 jury_loop 主入口（具体名按 Task 9 Step 1 grep 结果）
    # 断言：vision 被调 2 次（第一次 fail 后 retry）
    assert call_count["vision"] == 2, f"应触发 1 次 retry，实际 vision 调 {call_count['vision']} 次"

    # 断言：第二次 prompt 含 missing feature 名（prompt_rewriter.hint 注入）
    # final RunVerdict.overall_matches_spec == True


def test_jury_loop_writes_todo_after_n_retries(tmp_path):
    """3 次 retry 都 matches_spec=false → 写 MATCHES_SPEC_TODO.md + status=blocked。"""
    import json

    # Stub LLM 永远返回 matches_spec=false
    always_fail_response = json.dumps({
        "semantic_checks": {"geometry_preserved": True, "material_consistent": True,
                            "photorealistic": True, "no_extra_parts": True,
                            "no_missing_parts": True},
        "photoreal_score": 60, "reason": "disc only",
        "features_status": [{"feature_id": "flange_arms_4", "visible": False, "reason": "missing"}],
    })

    # 调 jury_loop（mock 永远返回 fail）
    # 期望：调用 N=3 次后停 + jury_report.json.matches_spec_status='blocked'
    assert ...  # call_count == 1 + N=3 = 4 (initial + 3 retries) 按实际语义
    # 注：MATCHES_SPEC_TODO.md 由 Task 10 photo3d-deliver 阶段写，不在 jury_loop；此处只验证 status
```

- [ ] **Step 3: GREEN — 接入 retry 决策**

在 jury_loop retry decision 处加：

```python
# 已有：if view.verdict == "needs_review": retry...
# 新：如果 view.semantic_checks["matches_spec"] is False:
#   → 把 view.verdict 设为 "needs_review"（如果尚未）
#   → retry 时通过 prompt_rewriter.hint() 注入 per_view_failed_features
```

- [ ] **Step 4: 测试 PASS + 跑全 jury_loop 测试套件**

```bash
python -m pytest tests/jury_loop/ -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/jury_loop/ tests/jury_loop/
git commit -m "feat(jury): Task 9 — jury_loop retry 接入 matches_spec（per-view scope, F5）

matches_spec=false → 视角 verdict=needs_review → retry；
retry prompt 通过 prompt_rewriter.hint() 注入 missing features 名列表。"
```

---

## Task 10 · `photo3d_delivery_pack.py` 写 MATCHES_SPEC_TODO.md + 标 blocked

**Files:**
- Modify: `tools/photo3d_delivery_pack.py`
- Test: `tests/test_photo3d_delivery_pack.py`

**目标：** 重试 N 次后仍 FAIL → photo3d-deliver 读 jury_report.json，写 `cad/<sub>/.cad-spec-gen/MATCHES_SPEC_TODO.md` 中文人话清单 + `DELIVERY_PACKAGE.json status=blocked`。

- [ ] **Step 1: 看现 photo3d_delivery_pack 结构**

```bash
grep -n "def \|status\|blocked" tools/photo3d_delivery_pack.py 2>&1 | head -30
```

- [ ] **Step 2: RED — 加测试**

```python
def test_delivery_pack_writes_todo_when_jury_report_fails(tmp_path):
    """jury_report.json.matches_spec_status == 'blocked' → 写 TODO.md + DELIVERY status=blocked。"""
    import json, pathlib

    # 1) Fixture: 准备 jury_report.json + matches_spec_features.json
    sub = "end_effector"
    cs_dir = tmp_path / "cad" / sub / ".cad-spec-gen"
    cs_dir.mkdir(parents=True)
    (cs_dir / "matches_spec_features.json").write_text(json.dumps({
        "schema_version": 1, "subsystem": sub, "run_id": "test",
        "features": [
            {"feature_id": "flange_arms_4", "description_cn": "法兰 4 条径向悬臂",
             "expected_in_views": ["V4"], "doc_ref": "examples/04-末端执行机构设计.md §3"},
            {"feature_id": "peek_ring", "description_cn": "PEEK 绝缘环",
             "expected_in_views": None, "doc_ref": "CAD_SPEC.md §6.2"},
        ],
    }, ensure_ascii=False), encoding="utf-8")

    renders_dir = tmp_path / "cad" / "output" / "renders"
    renders_dir.mkdir(parents=True)
    (renders_dir / "jury_report.json").write_text(json.dumps({
        "schema_version": 2, "subsystem": sub, "run_id": "test",
        "overall_matches_spec": False,
        "matches_spec_status": "blocked",
        "per_view_failed_features": {
            "V4": ["flange_arms_4"],
            "V6": ["peek_ring"],
        },
        "views": {},  # 简化
    }, ensure_ascii=False), encoding="utf-8")

    # 2) 调 run_photo3d_delivery_pack（具体签名按 grep 结果调）
    # (monkeypatch CAD_OUTPUT / cwd 到 tmp_path)

    # 3) 断言：TODO 文件写好 + 内容含两特征
    todo_path = cs_dir / "MATCHES_SPEC_TODO.md"
    assert todo_path.exists(), "MATCHES_SPEC_TODO.md 应生成"
    todo = todo_path.read_text(encoding="utf-8")
    assert "flange_arms_4" in todo
    assert "法兰 4 条径向悬臂" in todo  # 反查 description_cn 成功
    assert "peek_ring" in todo
    assert "PEEK 绝缘环" in todo
    assert "V4" in todo and "V6" in todo  # 每个特征列出哪些 view 缺
    assert "建议下一步" in todo  # 模板尾部

    # 4) 断言 DELIVERY_PACKAGE.json 标 blocked
    delivery_path = ...  # 按实际产物路径
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    assert delivery["status"] == "blocked"
    assert "matches_spec_fail_after_retries" in delivery.get("blocking_reasons", [])
```

- [ ] **Step 3: GREEN — 加 TODO 生成 helper**

`tools/photo3d_delivery_pack.py`：

```python
def _write_matches_spec_todo(jury_report: dict, todo_path: pathlib.Path) -> None:
    """生成 MATCHES_SPEC_TODO.md（spec §5.2.3 模板）。"""
    failed = jury_report.get("per_view_failed_features", {})
    if not failed:
        return  # 没有 fail 不写
    lines = [
        "# 自制件特征对账 — 未达标",
        f"日期：{datetime.date.today().isoformat()} · 子系统：{jury_report.get('subsystem','?')}"
        f" · 重试 3/3 次仍 FAIL",
        "",
        "## 应有但未见的特征",
        "",
    ]
    # 反查 features.json 拿 description_cn + doc_ref
    cache_dir = todo_path.parent
    features_path = cache_dir / "matches_spec_features.json"
    features_meta = {}
    if features_path.exists():
        cached = json.loads(features_path.read_text(encoding="utf-8"))
        features_meta = {f["feature_id"]: f for f in cached.get("features", [])}

    listed_features = set()
    for view, fids in failed.items():
        for fid in fids:
            if fid in listed_features:
                continue
            listed_features.add(fid)
            meta = features_meta.get(fid, {})
            desc = meta.get("description_cn", "(描述缺失)")
            ref = meta.get("doc_ref", "")
            lines.append(f"- [ ] **{fid}** — {desc}" + (f"（设计文档：{ref}）" if ref else ""))
            # 列出哪些 view 看不到
            for v, vfids in failed.items():
                if fid in vfids:
                    view_reason = ""  # 可从 jury_report.views[v].features_status 反查 reason
                    lines.append(f"  - {v}：{view_reason or '未见'}")

    lines += [
        "",
        "## 建议下一步",
        f"1. 重 build：检查相关 `cad/{jury_report.get('subsystem','?')}/*.py` 是否真画了该特征",
        f"2. 跑 `python cad_pipeline.py custom-parts-audit --subsystem {jury_report.get('subsystem','?')}` 看几何审计",
        "3. 若 audit PASS 但 jury 仍 FAIL → 调相机角度 `render_config.json`",
    ]
    todo_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

调用位置（按现 delivery_pack 流程接入）：

```python
def run_photo3d_delivery_pack(...) -> dict:
    # ... 现有逻辑 ...
    jury_report_path = pathlib.Path("cad/output/renders/jury_report.json")
    jury_report = json.loads(jury_report_path.read_text(encoding="utf-8")) if jury_report_path.exists() else {}

    if jury_report.get("matches_spec_status") == "blocked":
        todo_path = pathlib.Path("cad") / sub / ".cad-spec-gen" / "MATCHES_SPEC_TODO.md"
        _write_matches_spec_todo(jury_report, todo_path)
        delivery_status = "blocked"
        blocking_reasons.append("matches_spec_fail_after_retries")
```

- [ ] **Step 4: 测试 PASS**

```bash
python -m pytest tests/test_photo3d_delivery_pack.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/photo3d_delivery_pack.py tests/test_photo3d_delivery_pack.py
git commit -m "feat(jury): Task 10 — photo3d-deliver 写 MATCHES_SPEC_TODO.md + status=blocked

matches_spec_status='blocked' 时按 spec §5.2.3 模板生成 TODO；DELIVERY_PACKAGE.json
blocking_reasons += matches_spec_fail_after_retries。"
```

---

## Task 11 · `cad_pipeline.py::cmd_enhance_check` 透传 matches_spec_status（F2 wire 末段）

**Files:**
- Modify: `cad_pipeline.py::cmd_enhance_check`
- Test: relevant cad_pipeline test

**目标：** enhance-check 读 `cad/output/renders/jury_report.json` 拿 `matches_spec_status` 字段，加进 `quality_summary.matches_spec_status` 输出。

- [ ] **Step 1: 看现 cmd_enhance_check 输出 quality_summary 在哪**

```bash
grep -n "quality_summary\|matches_spec\|jury_report" cad_pipeline.py 2>&1 | head -20
```

- [ ] **Step 2: RED — 加测试**

```python
def test_enhance_check_transits_matches_spec_status(tmp_path, monkeypatch):
    """cmd_enhance_check 应把 jury_report.json.matches_spec_status 透传到 quality_summary。"""
    import json, pathlib
    from types import SimpleNamespace
    import sys; sys.path.insert(0, ".")
    from cad_pipeline import cmd_enhance_check

    # 1) Fixture: 在 args.dir 下写 jury_report.json
    renders = tmp_path / "renders"
    renders.mkdir()
    (renders / "jury_report.json").write_text(json.dumps({
        "schema_version": 2,
        "matches_spec_status": "pass",
    }, ensure_ascii=False), encoding="utf-8")

    # 2) 准备 args 模拟（subsystem + dir + 其他必填字段）
    args = SimpleNamespace(
        subsystem="end_effector",
        dir=str(renders),
        # ... 其他 cmd_enhance_check 现 args 字段按 cad_pipeline 现签名补 ...
    )

    # 3) Stub 其他 enhance-check 内部调用让它不真跑（仅验透传逻辑）
    # ...

    # 4) 调 cmd_enhance_check，读 ENHANCEMENT_REPORT.json
    rc = cmd_enhance_check(args)
    report_path = renders / "ENHANCEMENT_REPORT.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["quality_summary"]["matches_spec_status"] == "pass", \
        f"应透传 matches_spec_status=pass，实际：{report.get('quality_summary')}"
```

- [ ] **Step 3: GREEN — 透传**

```python
# cad_pipeline.py::cmd_enhance_check
def cmd_enhance_check(args):
    # ... 现有逻辑 ...
    # NEW: 读 jury_report.json matches_spec_status
    jury_path = pathlib.Path(args.dir) / "jury_report.json" if args.dir else None
    matches_spec_status = None
    if jury_path and jury_path.exists():
        try:
            jury = json.loads(jury_path.read_text(encoding="utf-8"))
            matches_spec_status = jury.get("matches_spec_status")
        except (json.JSONDecodeError, OSError):
            pass
    quality_summary["matches_spec_status"] = matches_spec_status  # 可能 None
```

- [ ] **Step 4: 测试 PASS**

```bash
python -m pytest tests/ -k "enhance_check" -v
```

- [ ] **Step 5: Commit**

```bash
git add cad_pipeline.py tests/
git commit -m "feat(jury): Task 11 — cmd_enhance_check 透传 matches_spec_status（F2 wire 末段）

读 cad/output/renders/jury_report.json 的 matches_spec_status 字段，
加进 ENHANCEMENT_REPORT.json.quality_summary。"
```

---

## Task 12 · L5 e2e smoke fixture + marker

**Files:**
- Create: `tests/jury_loop/test_matches_spec_e2e_smoke.py`

**目标：** 真 LLM + real fixture 烟雾测试。CI skip（`requires_jury_loop_e2e` marker），手动跑。

- [ ] **Step 1: 看现 marker 配置**

```bash
grep -n "requires_jury_loop_e2e" tests/conftest.py pyproject.toml 2>&1 | head -10
```

- [ ] **Step 2: 写 3 个 e2e case**

```python
"""L5 e2e smoke (manual, requires GEMINI_API_KEY + 花钱)。"""

import pytest

pytestmark = pytest.mark.requires_jury_loop_e2e


def test_e2e_matches_spec_pass_on_v2_36_1_main_end_effector():
    """v2.36.1 main GISBOT 归档 / 法兰 4 臂已画 → matches_spec PASS。
    Acceptance #6 (F6 fixed): features ≥3 含 anchor flange_arms_4。"""
    # 调真 photo3d-jury on D:/Work/cad-tests/GISBOT/04_render + 05_enhance
    # 断言：features_count >= 3, "flange_arms_4" in features
    # 断言：matches_spec=True
    pytest.skip("manual e2e — requires GEMINI_API_KEY + 已存在的 GISBOT 归档")


def test_e2e_matches_spec_fail_when_arms_removed():
    """反向：故意 break ee_001_01.py 删 4 臂 union → matches_spec FAIL with missing flange_arms_4。"""
    pytest.skip("manual e2e — needs git stash + rebuild")


def test_e2e_features_extraction_stable_across_3_runs():
    """spec §7 risk: 跑 3 次比 features 集合一致（temperature=0 验证）。"""
    pytest.skip("manual e2e — 3x cost")
```

- [ ] **Step 3: Commit**

```bash
git add tests/jury_loop/test_matches_spec_e2e_smoke.py
git commit -m "test(jury-matches-spec): Task 12 — L5 e2e smoke 3 case + requires_jury_loop_e2e marker

PASS/FAIL/stability 三 case；CI skip；手动跑（GEMINI_API_KEY + 花钱）。"
```

---

## Task 13 · `cad-tests/<sub>/_README.md` 加「特征对账」section + spec §11 模板对齐

**Files:**
- Modify: `D:\Work\cad-tests\GISBOT\_README.md`
- Modify: `D:\Work\cad-tests\jiehuo\_README.md`

**目标：** 用户最终 review 时能在 _README 一处看到特征对账状态（spec §11 + F4 修复要求）。

- [ ] **Step 1: 看 spec §11 模板**

按 `docs/superpowers/specs/2026-05-13-jury-matches-spec-design.md` §11 注脚。

- [ ] **Step 2: 手工补 section（按真实 jury_report.json 数据）**

如果本次有跑 jury 真实结果，按数据填；如无 → 写"v2.37 已实施，等下次 photo3d-jury 跑产生 matches_spec_features.json 后自动填"占位。

- [ ] **Step 3: Commit**

```bash
git add ...  # 注意：cad-tests/ 是仓库外目录，本步只在外目录操作不入 git
# 改记到 STATUS doc step 完成
```

---

## Task 14 · 最终验证 + 文档对齐 + retro

**Files:**
- Modify: `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`
- Create: `docs/superpowers/reports/2026-05-13-jury-matches-spec-retro.md`
- Modify: `memory/MEMORY.md` + `memory/project_quality_overhaul.md`（或新 memory）

**目标：** 整套件 PASS + 文档闭环 + memory pointer 更新。

- [ ] **Step 1: 跑全套件**

```bash
python -m pytest tests/ -q
```

期望：全 PASS（含本 plan 新加的 L1-L4 + 现有 jury 系列）。

- [ ] **Step 2: STATUS doc 全 ✅**

更新 `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` 三节 task 表全 ✅ + 五节 CURRENT TASK 改成"全部完成"。

- [ ] **Step 3: 写 retro doc**

`docs/superpowers/reports/2026-05-13-jury-matches-spec-retro.md`（≤30 行）记：
- 做对的（如 TDD 14 task 跑通 / spec adversarial review 9 finding 全闭）
- 做错过的（如 task 6/7 grep 假设错的话）
- 数字（task 数、test 数、commit 数、token cost 估）

- [ ] **Step 4: memory 更新**

`memory/MEMORY.md` 加一行：
```
- [jury matches_spec v2.37 RESOLVED](project_jury_matches_spec.md) — ...
```

新 memory `project_jury_matches_spec.md` 标 RESOLVED + 含 PR# + tag v2.37.0。

- [ ] **Step 5: Commit + PR + tag**

```bash
git add docs/ memory/
git commit -m "docs(jury-matches-spec): Task 14 — STATUS 收尾 + retro + memory pointer"
git push -u origin feat/v2-jury-matches-spec
gh pr create --base main --title "feat: jury matches_spec 维度 (v2.37) — 设计文档语义对账" --body "..."
# 等 CI 全绿
gh pr merge --merge --delete-branch
git checkout main && git pull --ff-only
git tag v2.37.0 <merge-sha>
git push origin v2.37.0
gh release create v2.37.0 --title "..." --notes "..."
```

---

## ✋ CHECKPOINT 完成条件

- ✅ Task 1-14 全部 ✅
- ✅ `python -m pytest tests/ -q` 全 PASS
- ✅ STATUS doc + retro + memory 三处一致
- ✅ PR merged + v2.37.0 tag + GitHub Release published
- ✅ spec §6 7 条 acceptance 全 PASS（L1-L4 mock 跑 + L5 e2e 至少手跑 #6+#7 验收）

---

## 验收 / Cleanup

- 跑 `python cad_pipeline.py custom-parts-audit --subsystem end_effector` 仍 WARN（v1 audit 不受影响）
- 跑 `python cad_pipeline.py build --subsystem end_effector` 仍 audit gate 正常（不破 v1 CP-2）
- 看 `cad/end_effector/.cad-spec-gen/matches_spec_features.json` 已生成
- 看 `cad/output/renders/jury_report.json::matches_spec_status` 字段存在
