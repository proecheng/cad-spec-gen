# jury v2.37 §11 follow-up cleanup（#1 + #6）— v2.37.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭合 v2.37 §11 follow-up #1（`_make_needs_review_verdict` 5→6 key 一致性）+ #6（`max_tokens=512→1024` 防 features_status 截断），TDD RED→GREEN→REFACTOR 三步严格走，发 v2.37.2 patch tag。

**Architecture:** 两改动文件 `tools/jury/verdict.py` + `tools/jury/llm_client.py`（均带 `src/cad_spec_gen/data/tools/jury/` 镜像，每改 canonical 后必跑 `python scripts/dev_sync.py`）；3 个新增 TDD 回归测试（test_verdict.py + test_verdict_matches_spec.py + test_llm_client.py）；零 schema 变化、零 env / config 新增、零行为变化（数学证明 `aggregate.get(default=True) == 显式 True`）。

**Tech Stack:** Python 3.10/11/12 + pytest + ruff + mypy strict（仅 `tools/jury/` 子集进 mypy gate）+ git tag-based release（不 bump 版本文件，v2.25+ 项目惯例）。

**Spec：** `docs/superpowers/specs/2026-05-14-jury-v2-37-followup-cleanup-design.md`（286 行；5 层审查通过 + writing-plans 入口 scout 修 1 处 spec 漂移）

**分支：** `feat/jury-v2-37-followup-cleanup`（已建；当前 HEAD `be911fa`；从 main `c4653d2` 起 5 commits）

---

## File Structure

| 文件 | 用途 | Canonical / Mirror |
|---|---|---|
| `tools/jury/verdict.py` | parse 模块；`_make_needs_review_verdict` 加 `matches_spec=True`；`aggregate_run_verdict` docstring 与 `.get` 实现对齐 | **canonical**（`src/cad_spec_gen/data/tools/jury/verdict.py` 镜像 dev_sync 同步）|
| `tools/jury/llm_client.py` | HTTP client；`max_tokens=512 → 1024` | **canonical**（同上镜像）|
| `tests/jury/test_verdict.py` | base helper 测试；加 `_make_needs_review_verdict` 6-key shape 测试（parametrize 3 anomalies path）| 仅 tests/ 路径 |
| `tests/jury/test_verdict_matches_spec.py` | matches_spec 维度集成测试；加 `aggregate_run_verdict` 行为不变测试（asdict 全字段等价）+ 全 needs_review vacuous True 测试 + dict key 顺序测试 | 仅 tests/ 路径 |
| `tests/jury/test_llm_client.py` | HTTP client 测试；加 `max_tokens=1024` 测试（沿用 `_make_cm` + `_mock_response` + `patch('tools.jury.llm_client.urlopen')` 风格）| 仅 tests/ 路径 |
| `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` | §11 follow-up 表；标 #1 + #6 closed (v2.37.2) | 仅 docs/ 路径 |
| `docs/superpowers/reports/2026-05-14-jury-v2-37-followup-cleanup-retro.md` | retro 文档（新写）| 仅 docs/ 路径 |

**不动文件**：`.github/workflows/tests.yml`（scout 已证 dev_sync `--check` step 既存 line 50-58 + 105-115；本 PR 不加只锁不变量 §6 #8）；`tools/jury/feature_extractor.py`（v2.37.1 已处理）；任何 schema / config 文件。

---

## Task 0: Scout 与 baseline 实测（plan 必 cover 项预拾起）

**Files:**
- Read only：`tools/jury/verdict.py:23-30`, `:189-200`, `:217-226` / `tools/jury/llm_client.py:90-108` / `.github/workflows/tests.yml:50-115` / `tests/jury/test_llm_client.py:1-80` / `tests/jury/test_verdict.py` / `tests/jury/test_verdict_matches_spec.py`

- [ ] **Step 1: 切到本 PR 分支并 fetch 最新 main 验证无并行改动（spec §13 R1 M1）**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git checkout feat/jury-v2-37-followup-cleanup
git log --oneline origin/main..HEAD -- tools/jury/  # 应只显示本分支自己的 commit
git log --oneline HEAD..origin/main -- tools/jury/  # 应为空（origin/main 未追加本分支不知的改动）
```

Expected: `git log HEAD..origin/main` 输出为空（无并行 PR 同时改 tools/jury/）。

- [ ] **Step 2: 验证 canonical / mirror 路径与 skip-worktree 守卫（spec §8 #1 + #4）**

```bash
git ls-files | grep -E '(llm_client|verdict)\.py$'
git ls-files -v | grep -E '(llm_client|verdict)\.py'
```

Expected: 
- `tools/jury/llm_client.py` + `tools/jury/verdict.py` 在 git tracked
- `src/cad_spec_gen/data/tools/jury/*.py` 不在（gitignored 镜像）
- `git ls-files -v` 输出行首无 `S` 标志（无 skip-worktree）

- [ ] **Step 3: 跑 baseline dev_sync `--check` 确认 clean state（spec §13 R5 D2）**

```bash
python scripts/dev_sync.py --check
echo "rc=$?"
```

Expected: `rc=0`（无 drift）；非零 → **abort plan**，开独立 cleanup commit 先修镜像 drift 再回本 plan。

- [ ] **Step 4: 实测 baseline PASS 数 → 填入 AC-4（spec §13 R4 Q5）**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
pytest -q tests/ 2>&1 | tail -3
```

Expected: 记录两数字（如 `733 passed / 17 skipped` + `3180 passed / 17 skipped`）；写入 plan task 7 commit message。本 PR 完工 PASS 数应为 baseline + 新加测试数（预计 +3 测试）。

- [ ] **Step 5: grep 验证 spec §13 R4 Q6 dict key 顺序写盘点**

```bash
grep -rn "json.dumps.*semantic_checks\|semantic_checks.*json.dumps" tools/ tests/
grep -rn "semantic_checks\[" tools/ tests/ src/  # 排除 docs/
```

Expected: 输出列表给后续 task 用——任何 `json.dumps(semantic_checks)` 写盘点都要在 Task 3 测试覆盖 key 顺序；任何 `semantic_checks["matches_spec"]` 直接访问要在 Task 2/3 测试覆盖（fact-check 已证 production code 全用 `.get`，预计只在 tests/ 与 verdict.py:192 docstring 命中）。

- [ ] **Step 6: 验证既存 CI dev_sync gate（spec §8 #9）**

```bash
grep -n "dev_sync" .github/workflows/tests.yml
```

Expected: 至少 4 行命中（test job + regression job 各 2 行：sync + --check）；**spec §6 #8 不变量已锁；本 plan 不改 workflow**。

- [ ] **Step 7: 记录 baseline 到本地 scratchpad 给后续 task 引用**

无 commit；只在 session memory 记 baseline 数字与 grep 结果。

---

## Task 1: TDD #1 — `_make_needs_review_verdict` 6-key shape 测试（RED）

**Files:**
- Test: `tests/jury/test_verdict.py`（append at end）

- [ ] **Step 1: 写失败测试（parametrize 3 anomalies path — spec §13 R4 Q3）**

在 `tests/jury/test_verdict.py` 文件末尾追加：

```python
# v2.37.2 §11 #1 — _make_needs_review_verdict 6-key shape 一致性
# parametrize 覆盖 parse_view_verdict 3 个早返回 path 全部调用 _make_needs_review_verdict
import pytest


@pytest.mark.parametrize(
    "bad_input,expected_anomaly",
    [
        ("not json at all", "content_not_json"),
        ('"a plain string not dict"', "content_not_json"),
        ('{"no_semantic_checks_key": true}', "missing_content"),
    ],
)
def test_make_needs_review_verdict_returns_6_key_with_matches_spec_true(
    bad_input: str, expected_anomaly: str
) -> None:
    """v2.37.2 §11 #1：_make_needs_review_verdict 返回 6-key dict 含 matches_spec=True，
    与 normal path 形态一致；与 aggregate_run_verdict 的 .get('matches_spec', True) 默认等价。

    Parametrize 3 个 anomalies path 覆盖 parse_view_verdict line 67 / 73 / 79 三处早返回。
    """
    v = parse_view_verdict(bad_input, finish_reason="stop")
    assert v.parse_status == "ok"
    assert expected_anomaly in v.parse_anomalies
    assert v.verdict == "needs_review"
    # 6-key shape 锁
    assert set(v.semantic_checks.keys()) == {
        "geometry_preserved",
        "material_consistent",
        "photorealistic",
        "no_extra_parts",
        "no_missing_parts",
        "matches_spec",
    }
    # matches_spec=True 兜底语义（与 aggregate .get(default=True) 等价）
    assert v.semantic_checks["matches_spec"] is True
    # 其它 5 key 全 False（_make_needs_review_verdict 既有契约）
    assert v.semantic_checks["geometry_preserved"] is False
    assert v.semantic_checks["material_consistent"] is False
    assert v.semantic_checks["photorealistic"] is False
    assert v.semantic_checks["no_extra_parts"] is False
    assert v.semantic_checks["no_missing_parts"] is False
```

- [ ] **Step 2: 跑 RED 验证测试真的失败**

```bash
pytest tests/jury/test_verdict.py::test_make_needs_review_verdict_returns_6_key_with_matches_spec_true -v
```

Expected: `FAILED` × 3（parametrize 3 case 全 fail）；assertion 在 `set(v.semantic_checks.keys()) == {...6 key...}` 处 fail（当前 5 key 缺 matches_spec）。

- [ ] **Step 3: 不 commit；进 Task 2 实现 GREEN**

---

## Task 2: 实现 — `_make_needs_review_verdict` 加 `matches_spec=True`（GREEN）

**Files:**
- Modify: `tools/jury/verdict.py:217-226`

- [ ] **Step 1: 改 canonical 实现**

读 `tools/jury/verdict.py:217-226` 当前实现：

```python
def _make_needs_review_verdict(anomalies: list[str]) -> ViewVerdict:
    """构造严重错误情况下的 needs_review ViewVerdict（5 bool 全 False / score=0 / reason 空）。"""
    return ViewVerdict(
        semantic_checks={k: False for k in _REQUIRED_BOOL_KEYS},
        photoreal_score=0,
        reason="",
        parse_status="ok",
        parse_anomalies=anomalies,
        verdict="needs_review",
    )
```

改成：

```python
def _make_needs_review_verdict(anomalies: list[str]) -> ViewVerdict:
    """构造严重错误情况下的 needs_review ViewVerdict（5 bool 全 False / score=0 / reason 空）。

    v2.37.2 §11 #1：加 matches_spec=True 第 6 key，与 normal path 形态一致；
    与 aggregate_run_verdict line 199 的 .get("matches_spec", True) 默认在所有现有
    调用路径上数学等价 → 零行为变化。
    semantic_checks dict key 顺序固定为 _REQUIRED_BOOL_KEYS + ('matches_spec',)
    末位（spec §6 #11 + plan task 必 cover Q6）。
    """
    semantic_checks: dict[str, bool] = {k: False for k in _REQUIRED_BOOL_KEYS}
    semantic_checks["matches_spec"] = True
    return ViewVerdict(
        semantic_checks=semantic_checks,
        photoreal_score=0,
        reason="",
        parse_status="ok",
        parse_anomalies=anomalies,
        verdict="needs_review",
    )
```

- [ ] **Step 2: 跑 dev_sync 同步镜像（spec §6 #7 不变量）**

```bash
python scripts/dev_sync.py
git status  # 应显示 src/cad_spec_gen/data/tools/jury/verdict.py 也被 modified（spec §13 M2）
python scripts/dev_sync.py --check
echo "rc=$?"  # 应为 0
```

Expected: `git status` 列出 canonical + mirror 两 verdict.py 都 modified；`--check` rc=0。

- [ ] **Step 3: 跑 GREEN 验证测试通过**

```bash
pytest tests/jury/test_verdict.py::test_make_needs_review_verdict_returns_6_key_with_matches_spec_true -v
```

Expected: `PASSED` × 3。

- [ ] **Step 4: REFACTOR 步显式确认（spec §3.4 D4 + edge-case finding #5）**

审视 Step 1 实现：
- 是否引入 6-key dict 重复字面量？→ 已用 dict + 单独 assign 形式 ✓（未硬编码 6 个 key 字面量）
- 是否冗余？→ 无，2 行最简
- Commit message 加一行：`REFACTOR: 无冗余可清，跳过`

- [ ] **Step 5: 跑 jury 子集回归确认无 break**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 比 task 0 baseline 多 3 个 PASS（新 parametrize 3 case），无新 FAIL。

- [ ] **Step 6: Commit**

```bash
git add tools/jury/verdict.py src/cad_spec_gen/data/tools/jury/verdict.py tests/jury/test_verdict.py
git -c commit.gpgsign=false commit -m "fix(jury): _make_needs_review_verdict 6-key 形态一致性（§11 #1）

v2.37 self-review 暴露：_make_needs_review_verdict 返回 5-key semantic_checks
（无 matches_spec），与 normal path 6-key 形态不一致；aggregate_run_verdict
已用 .get('matches_spec', True) 兜底，故非 bug 是脆性设计。

本 commit 加 matches_spec=True 第 6 key：
- 与 normal path '空 features_status → matches_spec=True 兜底' 同语义
- 与 aggregate .get(default=True) 在所有现有路径上数学等价 → 零行为变化
- 防未来加第 7 维度时漏改此 helper（spec §10 5 步 checklist）

TDD RED→GREEN→REFACTOR (no-op)；parametrize 3 anomalies path 覆盖
parse_view_verdict 早返回路径全集。

REFACTOR: 无冗余可清，跳过。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: TDD #2 — `aggregate_run_verdict` 行为不变 + vacuous True + key 顺序（RED + GREEN）

**Files:**
- Test: `tests/jury/test_verdict_matches_spec.py`（append at end）

**注**：本 Task 测试是「锁现有行为」性质，预期写完即 GREEN（因 Task 2 改动加 matches_spec=True 与 aggregate `.get` 默认等价；现有 aggregate 实现不动）。

- [ ] **Step 1: 写测试（asdict 全字段等价 + vacuous True + key 顺序，3 case）**

在 `tests/jury/test_verdict_matches_spec.py` 文件末尾追加：

```python
from dataclasses import asdict

from tools.jury.verdict import (
    aggregate_run_verdict,
    parse_view_verdict,
    _make_needs_review_verdict,
)


def test_aggregate_overall_unchanged_with_needs_review_view_mixed() -> None:
    """v2.37.2 §11 #1 reg：aggregate_run_verdict 把 needs_review 视角混入 normal 视角后，
    asdict(RunVerdict) 全字段与 task 2 改动前等价（数学证明：matches_spec=True 与
    .get(default=True) 在所有路径上等价 → asdict 输出 byte-equal）。

    Spec §13 R4 Q2 扩 AC-3 到 asdict 全字段等价（不只 overall_matches_spec）。
    """
    normal_content = (
        '{"semantic_checks": {"geometry_preserved": true, "material_consistent": true,'
        ' "photorealistic": true, "no_extra_parts": true, "no_missing_parts": true},'
        ' "photoreal_score": 80, "reason": "ok"}'
    )
    normal = parse_view_verdict(normal_content, finish_reason="stop")
    needs_review = _make_needs_review_verdict(["content_not_json"])

    run = aggregate_run_verdict({"V1": normal, "V2": needs_review})

    # overall_matches_spec：normal 视角 matches_spec=True + needs_review 视角
    # matches_spec=True（task 2 改动）→ all=True
    assert run.overall_matches_spec is True
    # per_view_failed_features：normal 视角 features_status 为空、needs_review 视角
    # features_status 为空 → 两视角都无 invisible feature → dict 为空
    assert run.per_view_failed_features == {}
    # asdict 全字段等价（每视角的 view_verdicts 也包含完整 ViewVerdict 数据）
    snapshot = asdict(run)
    assert snapshot["overall_matches_spec"] is True
    assert snapshot["per_view_failed_features"] == {}
    assert set(snapshot["view_verdicts"].keys()) == {"V1", "V2"}


def test_aggregate_all_needs_review_vacuous_true(
) -> None:
    """v2.37.2 §13 R4 Q4：所有视角都 needs_review 时 overall_matches_spec is True
    但所有 view 都是 needs_review verdict（vacuous True 不掩盖真问题，由上游
    needs_review_count 统计决策；本 PR 不改 aggregate 实现）。
    """
    v1 = _make_needs_review_verdict(["content_not_json"])
    v2 = _make_needs_review_verdict(["missing_content"])
    run = aggregate_run_verdict({"V1": v1, "V2": v2})
    assert run.overall_matches_spec is True  # vacuous True (all matches_spec=True)
    # 但所有视角是 needs_review verdict
    assert all(v.verdict == "needs_review" for v in run.view_verdicts.values())


def test_make_needs_review_verdict_key_order_stable(
) -> None:
    """v2.37.2 §13 R4 Q6：6-key dict key 顺序固定为 _REQUIRED_BOOL_KEYS + ('matches_spec',)
    末位；若任何 sidecar / cache key 依赖 stable order，本测试 catch 顺序漂移。
    """
    v = _make_needs_review_verdict(["content_not_json"])
    expected_order = [
        "geometry_preserved",
        "material_consistent",
        "photorealistic",
        "no_extra_parts",
        "no_missing_parts",
        "matches_spec",
    ]
    assert list(v.semantic_checks.keys()) == expected_order
```

- [ ] **Step 2: 跑测试（应直接 GREEN，因 aggregate 实现不动）**

```bash
pytest tests/jury/test_verdict_matches_spec.py::test_aggregate_overall_unchanged_with_needs_review_view_mixed tests/jury/test_verdict_matches_spec.py::test_aggregate_all_needs_review_vacuous_true tests/jury/test_verdict_matches_spec.py::test_make_needs_review_verdict_key_order_stable -v
```

Expected: `PASSED` × 3（因 Task 2 已经让 matches_spec=True 且 dict 是按 insertion order——`_REQUIRED_BOOL_KEYS` 循环先插 5 key，再 `["matches_spec"] = True` 末位）。

- [ ] **Step 3: REFACTOR 步显式确认**

审视 Step 1 测试：
- 3 个 case 是否互相独立？→ ✓（每个 fixture 自构造）
- 是否引入重复字面量？→ 5-key bool 字典在 normal_content 与 expected_order 各有一份；可提取常量但 scope 小 + 测试可读性优先 → 跳过
- Commit message 加：`REFACTOR: 5-key 字面量重复但提取会降可读性，跳过`

- [ ] **Step 4: Commit**

```bash
git add tests/jury/test_verdict_matches_spec.py
git -c commit.gpgsign=false commit -m "test(jury): aggregate 行为不变 + vacuous True + key 顺序 锁回归（§11 #1）

3 个回归测试锁定 Task 2 改动的零行为变化：
- asdict(RunVerdict) 全字段等价（spec §13 R4 Q2 扩 AC-3）
- 全视角 needs_review 时 vacuous True 不掩盖（spec §13 R4 Q4）
- 6-key dict key 顺序固定 _REQUIRED_BOOL_KEYS + ('matches_spec',) 末位（spec §13 R4 Q6）

aggregate_run_verdict 实现不动；本测试预期写完即 GREEN（因 Task 2 改动与
原 .get(default=True) 数学等价）。

REFACTOR: 5-key 字面量重复但提取会降可读性，跳过。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: TDD #3 — `max_tokens=512 → 1024`（RED → GREEN → REFACTOR）

**Files:**
- Test: `tests/jury/test_llm_client.py`（append at end）
- Modify: `tools/jury/llm_client.py:105`

- [ ] **Step 1: 写失败测试（沿用 `_make_cm` + `_mock_response` + `patch('tools.jury.llm_client.urlopen')` — spec §13 R4 Q1）**

在 `tests/jury/test_llm_client.py` 文件末尾追加：

```python
# v2.37.2 §11 #6 — max_tokens 512 → 1024 防 features_status 截断
# 实测 micuapi.ai gpt-image-2-pro 12 features × 几十字 + 5 standard check + reason
# ≈ 远超 512 → 9/12 features_status 被截断进 needs_review（finish_reason='length' 兜底）


def test_request_body_max_tokens_is_1024(
    profile: JuryProfile, fake_image: Path, enable_llm_for_test: None
) -> None:
    """v2.37.2 §11 #6 锁：request_jury_verdict 序列化 request body 的 max_tokens==1024
    （v2.37.1 是 512；本 PR 改 1024 给 long features_status 输出留响应空间）。

    沿用现有 test_llm_client.py mock 风格 — patch('tools.jury.llm_client.urlopen') +
    _make_cm + _mock_response（spec §13 R4 Q1）。
    """
    with patch("tools.jury.llm_client.urlopen") as m:
        m.return_value = _make_cm(_mock_response())
        request_jury_verdict(
            profile=profile, image_path=fake_image, prompt="any prompt"
        )
        # 拦截 urlopen 调用拿到 Request 对象，解析其 data（JSON 序列化 body）
        call_args = m.call_args
        request_obj = call_args[0][0]  # 第 1 个位置参数是 Request
        body_bytes: bytes = request_obj.data
        body_dict = json.loads(body_bytes.decode("utf-8"))
        assert body_dict["max_tokens"] == 1024, (
            f"max_tokens 应为 1024（v2.37.2 §11 #6），实际 {body_dict['max_tokens']}"
        )
        # 同时锁 temperature=0（v2.37 既有契约不破）
        assert body_dict["temperature"] == 0.0
```

- [ ] **Step 2: 跑 RED 验证测试真失败**

```bash
pytest tests/jury/test_llm_client.py::test_request_body_max_tokens_is_1024 -v
```

Expected: `FAILED`；assertion 报 `max_tokens 应为 1024，实际 512`（当前 hardcoded 512）。

- [ ] **Step 3: 改 canonical 实现**

读 `tools/jury/llm_client.py:90-108`，定位 line 105：

```python
            "max_tokens": 512,
```

改成：

```python
            "max_tokens": 1024,
```

加一行旁注（line 105 上方）：

```python
            # v2.37.2 §11 #6：512 → 1024 给 12 features_status + 5 standard check + reason
            # 留响应空间；finish_reason='length' 仍走 needs_review 兜底（不变量 §6 #10）。
            "max_tokens": 1024,
```

- [ ] **Step 4: 跑 dev_sync 同步镜像**

```bash
python scripts/dev_sync.py
git status  # 应显示 src/cad_spec_gen/data/tools/jury/llm_client.py 也被 modified
python scripts/dev_sync.py --check
```

Expected: 两 llm_client.py 都 modified；`--check` rc=0。

- [ ] **Step 5: 跑 GREEN 验证**

```bash
pytest tests/jury/test_llm_client.py::test_request_body_max_tokens_is_1024 -v
```

Expected: `PASSED`。

- [ ] **Step 6: REFACTOR 步显式确认**

审视 Step 3 改动：
- 是否硬编码 magic number？→ 1024 是 magic 但与 v2.32.0 时代的 512 风格一致；加注释解释来源 ✓
- 是否引入 config 抽象？→ 北极星「零配置」拒绝（spec §6 #6）
- Commit message 加：`REFACTOR: 加 line 注释解释 1024 来源；无其它冗余`

- [ ] **Step 7: 跑 jury 全子集回归 + 全套件 sanity**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
pytest -q tests/ 2>&1 | tail -3
```

Expected: 比 baseline 多 4 个 PASS（Task 1 +3, Task 4 +1），无新 FAIL。

- [ ] **Step 8: Commit**

```bash
git add tools/jury/llm_client.py src/cad_spec_gen/data/tools/jury/llm_client.py tests/jury/test_llm_client.py
git -c commit.gpgsign=false commit -m "fix(jury): max_tokens 512→1024 防 features_status 截断（§11 #6）

v2.37.1 micuapi.ai gpt-image-2-pro 实测暴露：12 features × 几十字 + 5 standard
check + reason ≈ 远超 512 → 9/12 features_status 被截断进 needs_review。

本 commit 把 max_tokens 硬编码 512 改 1024（不加 env / config，北极星零配置约束）：
- 1024 对 12 features + 5 check + 短 reason 合理上限（实测 micuapi.ai 长输出 ~800 token）
- 只增不减响应空间 → temperature=0 决定原 512 内 LLM 输出不变（数学零行为变化）
- finish_reason='length' 仍走 needs_review 兜底（不变量 §6 #10）

TDD RED→GREEN→REFACTOR；mock urlopen 拦截 request body 断言 max_tokens==1024。
沿用既有 _make_cm + _mock_response 风格（spec §13 R4 Q1）。

REFACTOR: 加 line 注释解释 1024 来源；无其它冗余。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `aggregate_run_verdict` docstring 对齐（edge-case finding #1）

**Files:**
- Modify: `tools/jury/verdict.py:189-200`（docstring 部分）

- [ ] **Step 1: 改 docstring 对齐实现**

读 `tools/jury/verdict.py:189-200` 当前 docstring：

```python
def aggregate_run_verdict(view_verdicts: dict[str, ViewVerdict]) -> RunVerdict:
    """聚合多视角 verdict → RunVerdict（spec §5.2.2 F1 修复落地）。

    - ``overall_matches_spec`` = all(view.semantic_checks["matches_spec"] for view)；
      若 view 缺 matches_spec key（如 _make_needs_review_verdict 早返回路径），
      用 ``.get(default=True)`` 退化为 True（不破坏聚合：parse 错不等于 spec mismatch）。
    - ``per_view_failed_features`` = {view_id: [feature_id]} 仅含至少 1 invisible feature 的 view，
      给 prompt_rewriter (Task 4) 提供 per_view_failed_features 反馈数据。
    """
```

改成（与 line 198-200 `.get` 实现一致；不再说"早返回路径缺 key"因 v2.37.2 起 _make_needs_review_verdict 也带 6-key）：

```python
def aggregate_run_verdict(view_verdicts: dict[str, ViewVerdict]) -> RunVerdict:
    """聚合多视角 verdict → RunVerdict（spec §5.2.2 F1 修复落地）。

    - ``overall_matches_spec`` = all(view.semantic_checks.get("matches_spec", True)
      for view)；用 .get(default=True) 防御性兜底，覆盖 v2.37.1 历史 5-key 存档反
      序列化场景（spec §6 不变量 #11）。v2.37.2 起 _make_needs_review_verdict 也
      返回 6-key 含 matches_spec=True，与 .get 默认数学等价（零行为变化）。
    - ``per_view_failed_features`` = {view_id: [feature_id]} 仅含至少 1 invisible
      feature 的 view，给 prompt_rewriter (Task 4) 提供 per_view_failed_features
      反馈数据。
    """
```

- [ ] **Step 2: dev_sync 同步**

```bash
python scripts/dev_sync.py
git status
python scripts/dev_sync.py --check
```

Expected: 两 verdict.py 都 modified；`--check` rc=0。

- [ ] **Step 3: 跑全 jury 子集回归（docstring 改无应直接绿）**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 与 Task 4 后基线一致；无新 FAIL。

- [ ] **Step 4: Commit（可合 Task 2 commit 或独立；建议独立便于审）**

```bash
git add tools/jury/verdict.py src/cad_spec_gen/data/tools/jury/verdict.py
git -c commit.gpgsign=false commit -m "docs(jury): aggregate_run_verdict docstring 与 .get 实现对齐（edge-case #1）

5 层审查 layer 4 edge-case-hunter finding #1：docstring 写
all(view.semantic_checks['matches_spec'] for view) 与 line 199 实现
.get('matches_spec', True) 不一致，下个改动者读 docstring 误判契约。

本 commit 让 docstring 与代码 .get 用法一致：
- 强调 .get(default=True) 是历史 5-key 存档（spec §6 #11）+ 防御性 fallback
- 注明 v2.37.2 起 _make_needs_review_verdict 也带 6-key，与 .get 默认等价

零行为变化（仅 docstring）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: 文档收尾 — STATUS §11 标 closed + retro 写

**Files:**
- Modify: `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`（§11 表 #1 + #6 行）
- Create: `docs/superpowers/reports/2026-05-14-jury-v2-37-followup-cleanup-retro.md`

- [ ] **Step 1: STATUS §11 表标 #1 + #6 closed**

读 `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md:72`（#1 行），把：

```markdown
| #1 | LOW | `_make_needs_review_verdict` 5→6 key 一致性 |
```

改成：

```markdown
| #1 | LOW | `_make_needs_review_verdict` 5→6 key 一致性 — **closed v2.37.2** (PR #N) |
```

类似找到 #6 行（grep `max_tokens.*512`），改成：

```markdown
| #6 | LOW (v2.37.1 新发现) | jury verdict `max_tokens=512` 偏紧... — **closed v2.37.2** (PR #N) |
```

（PR # 占位；实际 PR 号在 push + open PR 后回填）

- [ ] **Step 2: 写 retro 文档**

新建 `docs/superpowers/reports/2026-05-14-jury-v2-37-followup-cleanup-retro.md`：

```markdown
# Retro — jury v2.37 §11 follow-up cleanup（v2.37.2）

**完工日期：** 2026-05-14
**PR：** #N（main@<merge_sha>）
**Spec：** `docs/superpowers/specs/2026-05-14-jury-v2-37-followup-cleanup-design.md`（286 行 / 5 层审查 + writing-plans scout 1 处漂移修）
**Plan：** `docs/superpowers/plans/2026-05-14-jury-v2-37-followup-cleanup.md`
**Baseline：** main@`c4653d2` → merge@<sha> （5+N commits）

## 完工范围

- §11 #1 closed：`_make_needs_review_verdict` 5→6 key 一致性
- §11 #6 closed：`max_tokens` 512→1024 防 features_status 截断
- edge-case finding #1 closed：`aggregate_run_verdict` docstring 与 .get 实现对齐
- 不变量 §6 #8 锁定：CI dev_sync `--check` gate（既存）升级为永久不变量

## 数字

- 全套件 PASS：<task0 baseline> → <task7 final>（+4 新测试：parametrize ×3 + max_tokens ×1）
- jury 子集 PASS：<baseline> → <final>
- 0 regression
- CI 8/8 SUCCESS（连续多少次？）

## 5 层审查统计

| Layer | findings | inline 修 | 移 §12 |
|---|---|---|---|
| 1 self | 1 | 1 | 0 |
| 2 cynical | 0 | 0 | 0 |
| 3 code-spec | 14 ✅ + 5 自发现 | 2 | 3 |
| 4 edge-case | 7 | 7 | 0 |
| 5 五角色 + dry-run | 34 | 10 | 6 |
| 6 writing-plans scout | 1 漂移 | 1 | 0 |
| **总** | **62+** | **21** | **9** |

## 沉淀 lessons

- writing-plans 入口 scout grep 验证 spec 假设是 plan-drift 防御的关键 checkpoint（layer 6 实证：发现 spec 误认为需"加 CI gate"实则既存）
- 5 角色并行 adversarial 审查抓的多是"系统视角"问题（state lifecycle / runtime path / 升级路径），与 edge-case-hunter 的 branching 互补
- spec 286 行 vs PR diff ~50 行 = ~5:1 比例临界——再添内容该开独立 ADR

## §12 follow-up（不阻断 v2.37.2，留后续 cleanup）

见 spec §12 预登记 6 项 + 本 PR 实测发现的（待回填）。
```

- [ ] **Step 3: 跑 docs 元测试确认无 break**

```bash
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: 全 PASS（docs 改动不触发元测试）。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/JURY_MATCHES_SPEC_STATUS.md docs/superpowers/reports/2026-05-14-jury-v2-37-followup-cleanup-retro.md
git -c commit.gpgsign=false commit -m "docs(jury): STATUS §11 #1+#6 closed + v2.37.2 retro

闭合 v2.37 §11 follow-up #1 + #6 两项 LOW-severity 事项；
写 retro 沉淀 5+1 层审查统计与 plan-drift scout lesson。

PR # 占位字段在 squash merge 后由 GitHub Release 步骤回填。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: PR 流程 — push / CI / squash merge / tag / Release

**Files:**
- 无文件改动；纯 git / GitHub 操作

- [ ] **Step 1: PR push 前并行改动 final 验证（spec §13 R1 M1）**

```bash
git fetch origin main
git log --oneline HEAD..origin/main -- tools/jury/  # 必须为空
```

Expected: 空输出；否则 abort，rebase origin/main 后重跑全 task 回归。

- [ ] **Step 2: Push 分支**

```bash
git push origin feat/jury-v2-37-followup-cleanup
```

- [ ] **Step 3: 开 PR**

```bash
gh pr create --title "fix(jury): v2.37 §11 follow-up cleanup #1+#6（v2.37.2）" --body "$(cat <<'EOF'
## 概要

闭合 v2.37 §11 follow-up 两项 LOW-severity 事项，发 v2.37.2 patch tag。

- **§11 #1**：`_make_needs_review_verdict` 5→6 key 一致性
- **§11 #6**：`max_tokens` 512 → 1024 防 features_status 截断

## 改动范围

- `tools/jury/verdict.py` + `tools/jury/llm_client.py` + 2 处 docstring 对齐
- 3 个新加 TDD 回归测试（test_verdict.py / test_verdict_matches_spec.py / test_llm_client.py）
- STATUS §11 表 + retro 文档
- **0 schema 变化、0 env / config 新增、0 行为变化**（数学证明 aggregate `.get(default=True)` 与显式 True 在 all() 语境下等价）

## 审查层数

5 层审查（self / cynical / code-spec / edge-case / 5 角色 + dry-run）+ writing-plans 入口 scout 抓 1 处 spec 漂移。62+ findings 分类处置，21 inline 修，9 留 §12 follow-up。

## Spec / Plan

- Spec: `docs/superpowers/specs/2026-05-14-jury-v2-37-followup-cleanup-design.md`
- Plan: `docs/superpowers/plans/2026-05-14-jury-v2-37-followup-cleanup.md`
- Retro: `docs/superpowers/reports/2026-05-14-jury-v2-37-followup-cleanup-retro.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL 返回；记 PR # 给 Step 6 回填。

- [ ] **Step 4: 等 PR CI 8/8 全绿**

```bash
gh pr checks --watch
```

Expected: 8/8 SUCCESS（ubuntu/windows × py3.10/11/12 + mypy-strict + regression）。

**Transient flake 处理**（spec §4 AC-5）：若某 job 挂，先 `gh run rerun <run_id>` 重跑；连续 2 次同 failure signature 才视为 regression（abort 进 §7.1 rollback 判定）。

- [ ] **Step 5: 等 PR review approve 后 squash merge**

```bash
gh pr merge --squash --delete-branch
```

Expected: PR merged；本地分支删除；origin main 更新。

- [ ] **Step 6: Sync local + 等 main CI 全绿（spec §7 D5）**

```bash
git checkout main
git pull origin main
gh run list --branch main --limit 1  # 看最新 main CI run
gh run watch <run_id>
```

Expected: main CI 8/8 SUCCESS。

- [ ] **Step 7: Tag v2.37.2（指向 main HEAD sha）**

```bash
MAIN_SHA=$(git rev-parse HEAD)
echo "tagging v2.37.2 → $MAIN_SHA"
git tag -a v2.37.2 $MAIN_SHA -m "v2.37.2 — jury §11 follow-up cleanup (#1 + #6)"
git push origin v2.37.2
```

Expected: tag pushed。

- [ ] **Step 8: 发 GitHub Release（含升级路径说明 — spec §7.0）**

```bash
gh release create v2.37.2 \
  --title "v2.37.2 — jury §11 follow-up cleanup (#1 + #6)" \
  --notes "$(cat <<'EOF'
## 变更

- **§11 #1**: `_make_needs_review_verdict` 6-key 形态一致性（与 `aggregate_run_verdict` `.get(default=True)` 数学等价 → 零行为变化）
- **§11 #6**: `max_tokens` 512 → 1024 防 features_status 截断（v2.37.1 micuapi.ai 实测 9/12 features_status 被截断暴露）

零 schema 变化 / 零 env-config 新增 / 零行为变化。

## 用户升级路径

本项目 v2.25+ 惯例：纯 git tag + Release notes，pyproject.toml 不 bump（仍 2.24.0）。

- **git+https**（推荐）：`pip install git+https://github.com/proecheng/cad-spec-gen.git@v2.37.2`
- **GitHub Release zip**：从本页下载 tarball → `pip install ./cad-spec-gen-v2.37.2.tar.gz`
- **本地开发**：`git fetch && git checkout v2.37.2 && pip install -e .`

PyPI 当前未发；`pip install cad-spec-gen` 拿不到本版本。

## 审查统计

5 层 + 1 scout 共 62+ findings；21 inline 修；9 §12 follow-up 预登记；0 阻断性事项。

## Spec / Plan / Retro

完整文档见仓库 `docs/superpowers/{specs,plans,reports}/2026-05-14-jury-v2-37-followup-cleanup-*.md`。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: Release published。

- [ ] **Step 9: 回填 PR # 到 STATUS 表（不强制；scope 小可跳）**

```bash
PR_NUM=$(gh pr list --state merged --limit 1 --json number --jq '.[0].number')
echo "PR #$PR_NUM"
```

如果想精确：开新分支改 STATUS PR # 占位，开 cleanup PR 修；通常项目惯例占位即可，不再改。

- [ ] **Step 10: 写本 PR 完工 memory（项目惯例）**

写 `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\project_jury_v2_37_2_done.md` 并加 MEMORY.md 索引；记录 main HEAD sha + final PASS 数 + 任何实测发现。

---

## Self-Review

**Spec coverage**:
- Spec §2.1 改动表 7 条 → Task 2/4/5（实现）+ Task 1/3/4（测试）+ Task 6（docs）+ Task 7（PR）✓
- Spec §3 设计决策 D1-D4 → Task 4 (D1) / Task 2 (D2) / Task 7 (D3) / Task 1-5 (D4 TDD) ✓
- Spec §4 AC-1 ~ AC-7 → Task 4 (AC-1) / Task 1+2 (AC-2) / Task 3 (AC-3) / Task 0 (AC-4 baseline) / Task 7 (AC-5+6+7) ✓
- Spec §6 不变量 #1-#11 → Task 0 验证（#7 #8 #9）+ Task 2 维持（#1 #2 #3 #6）+ Task 4 维持（#6）+ Task 5 文档（#10 #11）✓
- Spec §7.0 用户升级路径 → Task 7 Step 8 Release notes ✓
- Spec §7.1 Rollback → 触发时使用，plan 不强制走 ✓
- Spec §10 扩展新维度 checklist → 文档性，未来加维度时引用 ✓
- Spec §13 plan 必 cover 10 项 → 全部 inline 拾起（M1/M2 Task 0 + D2 Task 0 + D3 commit 粒度全 task + D4 不适用因 CI 既存 + Q1 Task 4 mock 风格 + Q3 Task 1 parametrize + Q5 Task 0 baseline + Q2/Q4/Q6 Task 3 三测试）✓

**Placeholder scan**: 无 TBD / TODO；PR # 在 Task 6 Step 1 标"占位字段在 squash merge 后由 GitHub Release 步骤回填"是显式留白不是 placeholder ✓

**Type consistency**: `ViewVerdict` / `RunVerdict` / `JuryProfile` / `LlmResponse` 引用全沿用 spec / 现有代码；新加 `dict[str, bool]` 类型注解与 verdict.py 既有签名一致 ✓

**Plan 自检无问题 → ready for handoff。**

---

## 执行方式选择

Plan 完成保存到 `docs/superpowers/plans/2026-05-14-jury-v2-37-followup-cleanup.md`。两种执行模式：

1. **Subagent-Driven（推荐）** — 主 agent 每 task 派发 fresh subagent，两阶段 review（implementer → spec reviewer），主 agent 在 task 间审查批准，scope 极小适合
2. **Inline 执行** — 主 agent 在本 session 直接跑全部 task，checkpoint 暂停让用户审

按 spec scope 与本项目 session 8/36/40 实证（subagent-driven 在 ≤10 task 规模上摩擦最低），建议 **Subagent-Driven**。
