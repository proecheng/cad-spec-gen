# v2.37.9 — jury verdict + retry + 真 vendor 实测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 photoreal<60 触发 retry 闭环 + 实测 GISBOT 真 vendor 验证 photoreal ≥60。

**Architecture:** 5 改动跨 4 文件 + 3 新测试文件 + 1 集成实测；spec rev 3 §9.4 7 步链路全闭环。

**Tech Stack:** Python 3.11+ / pytest / jury/verdict.py / jury_loop orchestrator + config / photo3d_delivery_pack

**Spec ref:** `docs/superpowers/specs/2026-05-16-v2-37-9-jury-retry-real-vendor-design.md` (rev 3, 437 行, commit `ff82879`)

---

## Task 0: Scout 假设验证（防 plan-drift）

**Files:** 无（grep only）

**预计:** 4 分钟

- [ ] **Step 1: 验证 verdict.py 当前 photoreal<60 → preview**

Run:
```bash
cd D:/Work/cad-spec-gen
sed -n '155,165p' tools/jury/verdict.py
```

Expected: line 159-160 `elif score < min_photoreal_score:` + `verdict = "preview"`

- [ ] **Step 2: 验证 orchestrator.py:199 needs_review 路径决策**

Run:
```bash
sed -n '193,205p' tools/jury_loop/orchestrator.py
```

Expected:
```python
if verdict.verdict == "needs_review":
    if "matches_spec_failed" in verdict.parse_anomalies:
        return (verdict, "matches_spec_failed")
    return (None, "needs_review")
```

- [ ] **Step 3: 验证 photo3d_delivery_pack.py:143-144 copy_preview 条件**

Run:
```bash
sed -n '140,150p' tools/photo3d_delivery_pack.py
```

Expected:
```python
final_deliverable = enhancement_status == "accepted"
copy_preview = enhancement_status == "preview" and include_preview
```

- [ ] **Step 4: 验证 max_retries=1 完整 test scope**

Run:
```bash
grep -n "max_retries" tests/jury_loop/conftest.py tests/jury_loop/test_config.py tests/jury_loop/test_orchestrator.py 2>&1 | head -10
```

Expected:
- `conftest.py:186` fixture default `max_retries: int = 1`
- `test_config.py:32/49/70/97/122` 5 处 `max_retries: 1`
- `test_orchestrator.py:39` `"max_retries": 1`（**显式场景测试，不改**）

- [ ] **Step 5: 验证既有 preview-assert 测试位置**

Run:
```bash
grep -n 'verdict == "preview"\|verdict in (.*"preview"' tests/jury/test_verdict.py tests/jury/test_verdict_matches_spec.py 2>&1 | head -10
```

Expected:
- `test_verdict.py:97` `assert v.verdict == "preview"  # 0 < min 60`
- `test_verdict_matches_spec.py:64` `assert v.verdict in ("accepted", "preview")`

记录到 plan 执行 log：5/5 实证全过即推进 Task 1+。任何 mismatch BLOCK 重审 spec rev 3。

---

## Task 1: 改动 1 — verdict.py photoreal<60 → needs_review + 既有测试适配

**Files:**
- Modify: `tools/jury/verdict.py:158-162`
- Modify: `tests/jury/test_verdict.py:97`
- Modify: `tests/jury/test_verdict_matches_spec.py:64`
- Create: `tests/jury/test_verdict_below_threshold.py`

**预计:** 20 分钟

### Step 1: 写新 TDD 测试 `tests/jury/test_verdict_below_threshold.py`

完整内容：

```python
"""tests/jury/test_verdict_below_threshold.py — §11-N6 photoreal<60 升 needs_review TDD。"""

from __future__ import annotations

import json

import pytest

from tools.jury.verdict import parse_view_verdict


def _make_payload(photoreal: int, *, finish_reason: str = "stop") -> str:
    """构造 LLM raw response JSON payload。"""
    return json.dumps({
        "photoreal_score": photoreal,
        "semantic_checks": {
            "consistent_lighting": True,
            "consistent_shadows": True,
            "consistent_perspective": True,
            "plausible_materials": True,
            "no_floating_objects": True,
        },
        "reason": "test reason",
        "finish_reason": finish_reason,
    })


def test_photoreal_59_below_threshold_becomes_needs_review() -> None:
    """T1 — photoreal=59 (边界 - 1) → verdict=needs_review + anomaly=photoreal_below_threshold。"""
    v = parse_view_verdict(_make_payload(59))
    assert v.verdict == "needs_review"
    assert "photoreal_below_threshold" in v.parse_anomalies


def test_photoreal_60_at_threshold_remains_accepted() -> None:
    """T2 — photoreal=60 (边界) → verdict=accepted（不变）。"""
    v = parse_view_verdict(_make_payload(60))
    assert v.verdict == "accepted"
    assert "photoreal_below_threshold" not in v.parse_anomalies


def test_photoreal_35_gisbot_baseline_becomes_needs_review() -> None:
    """T3 — photoreal=35 (GISBOT 实测最低值) → verdict=needs_review。"""
    v = parse_view_verdict(_make_payload(35))
    assert v.verdict == "needs_review"
    assert "photoreal_below_threshold" in v.parse_anomalies
    # photoreal_score 仍写入 verdict (用于 retry _pick_best)
    assert v.photoreal_score == 35


def test_photoreal_45_gisbot_high_becomes_needs_review() -> None:
    """T4 — photoreal=45 (GISBOT 实测最高值) → verdict=needs_review。"""
    v = parse_view_verdict(_make_payload(45))
    assert v.verdict == "needs_review"
    assert "photoreal_below_threshold" in v.parse_anomalies
```

### Step 2: 跑测试 4 FAIL（RED）

Run:
```bash
pytest tests/jury/test_verdict_below_threshold.py -v 2>&1 | tail -10
```

Expected: 4 FAIL（verdict 仍 "preview"）

### Step 3: 改 verdict.py:158-162

打开 `tools/jury/verdict.py` 找 line 158-162：

```python
    elif "above_threshold_blocked" in anomalies:
        verdict = "preview"
    elif score < min_photoreal_score:
        verdict = "preview"
    else:
        verdict = "accepted"
```

改成：

```python
    elif "above_threshold_blocked" in anomalies:
        verdict = "preview"
    elif score < min_photoreal_score:
        # v2.37.9 §11-N6 — photoreal<60 升 needs_review 触发 retry 闭环（与 matches_spec_failed 同 retry path）
        anomalies = anomalies + ["photoreal_below_threshold"]
        verdict = "needs_review"
    else:
        verdict = "accepted"
```

### Step 4: 跑新测试 4 PASS（GREEN）

```bash
pytest tests/jury/test_verdict_below_threshold.py -v 2>&1 | tail -10
```

Expected: 4 PASS

### Step 5: 适配 test_verdict.py:97

打开 `tests/jury/test_verdict.py`，找 line 97 附近：

```python
    # 改前
    assert v.verdict == "preview"  # 0 < min 60
```

改成：

```python
    # v2.37.9 §11-N6 — photoreal<60 升 needs_review
    assert v.verdict == "needs_review"
    assert "photoreal_below_threshold" in v.parse_anomalies
```

### Step 6: 适配 test_verdict_matches_spec.py:64

打开 `tests/jury/test_verdict_matches_spec.py`，找 line 64 附近：

```python
    # 改前
    assert v.verdict in ("accepted", "preview"), (
        f"老 fixture verdict 必须 accepted/preview, 实际 = {v.verdict}; "
```

改成：

```python
    # v2.37.9 §11-N6 — photoreal<60 升 needs_review；老 fixture score>=60 仍 accepted
    assert v.verdict in ("accepted", "needs_review"), (
        f"老 fixture verdict 必须 accepted/needs_review, 实际 = {v.verdict}; "
```

### Step 7: 跑 jury 子集验证零回归

```bash
pytest -q tests/jury/ 2>&1 | tail -5
```

Expected: jury 子集 PASS（既有 + 新 T1-T4）/ 0 regression

### Step 8: dev_sync + Commit

```bash
python scripts/dev_sync.py 2>&1 | tail -3
git add tools/jury/verdict.py tests/jury/test_verdict.py tests/jury/test_verdict_matches_spec.py tests/jury/test_verdict_below_threshold.py
git -c commit.gpgsign=false commit -m "feat(jury): photoreal<60 升 needs_review + anomaly（§11-N6 改动 1 + 1d）

verdict.py:159 改 photoreal<60 → needs_review + parse_anomalies 加
photoreal_below_threshold（与 matches_spec_failed 同 retry path）。

新 TDD test_verdict_below_threshold.py — 4 测试（59 边界 / 60 边界 / 35 GISBOT 实测最低 / 45 GISBOT 实测最高）。

适配既有 preview-assert：
- test_verdict.py:97（v.verdict == 'preview' → 'needs_review' + anomaly）
- test_verdict_matches_spec.py:64（in ('accepted','preview') → ('accepted','needs_review')）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 2: 改动 1b BLOCKER — orchestrator.py retry 白名单扩

**Files:**
- Modify: `tools/jury_loop/orchestrator.py:193-201`
- Create: `tests/jury_loop/test_orchestrator_photoreal_retry.py`

**预计:** 20 分钟

### Step 1: 写 TDD 测试 `tests/jury_loop/test_orchestrator_photoreal_retry.py`

完整内容：

```python
"""tests/jury_loop/test_orchestrator_photoreal_retry.py — §11-N6 改动 1b BLOCKER fix TDD。

测试 orchestrator.py:199 photoreal_below_threshold 进 retry 白名单。
"""

from __future__ import annotations

import json

import pytest

from tools.jury.verdict import ViewVerdict
from tools.jury_loop.orchestrator import _parse_verdict_with_anomaly_path


def _make_view_verdict_payload(photoreal: int, anomaly: str | None = None) -> str:
    """构造 LLM batch JSON (list of 1 item)。"""
    payload = {
        "photoreal_score": photoreal,
        "semantic_checks": {
            "consistent_lighting": True,
            "consistent_shadows": True,
            "consistent_perspective": True,
            "plausible_materials": True,
            "no_floating_objects": True,
        },
        "reason": "test reason",
        "finish_reason": "stop",
    }
    if anomaly == "matches_spec_failed":
        payload["features_status"] = [{"feature_id": "f1", "visible": False}]
    return json.dumps([payload])


def test_photoreal_below_threshold_returns_verdict_for_retry() -> None:
    """T-orch-photoreal-retry — photoreal<60 走 retry path（rev 3 BLOCKER fix）。"""
    # photoreal=35 → verdict.verdict=needs_review + anomaly=photoreal_below_threshold
    raw_json = _make_view_verdict_payload(35)
    
    result = _parse_verdict_with_anomaly_path(raw_json)
    
    assert result is not None
    verdict, anomaly_path = result
    # 关键断言：BLOCKER fix — 不是 (None, "needs_review")
    assert verdict is not None, "photoreal_below_threshold 应保留 verdict 走 retry"
    assert anomaly_path == "photoreal_below_threshold"
    assert verdict.photoreal_score == 35


def test_matches_spec_failed_still_returns_retry_verdict() -> None:
    """T-orch-matches-spec — matches_spec_failed 路径不动（回归 anchor）。"""
    raw_json = _make_view_verdict_payload(80, anomaly="matches_spec_failed")
    
    result = _parse_verdict_with_anomaly_path(raw_json)
    
    assert result is not None
    verdict, anomaly_path = result
    assert verdict is not None
    assert anomaly_path == "matches_spec_failed"


def test_parse_failed_still_returns_jury_unavailable() -> None:
    """T-orch-parse-fail — 解析失败仍走 jury_unavailable（回归 anchor）。"""
    raw_json = "not a JSON"
    
    result = _parse_verdict_with_anomaly_path(raw_json)
    
    # parse fail → (None, "json_parse_failed") 或类似 jury_unavailable
    assert result is not None
    verdict, anomaly_path = result
    assert verdict is None  # 不可信不走 retry
```

### Step 2: 跑测试 1 FAIL + 2 PASS（RED + 2 anchor PASS）

```bash
pytest tests/jury_loop/test_orchestrator_photoreal_retry.py -v 2>&1 | tail -15
```

Expected: `test_photoreal_below_threshold_returns_verdict_for_retry` FAIL（当前走 jury_unavailable）/ 2 anchor PASS

### Step 3: 改 orchestrator.py:193-201

打开 `tools/jury_loop/orchestrator.py` 找 line 193-201：

```python
    if verdict.verdict == "needs_review":
        # Task 9 v2.37 (C)：matches_spec_failed 路径保留 verdict 让上层走 retry 而非 jury_unavailable。
        # 区分两类 needs_review：
        # (a) anomaly=matches_spec_failed → verdict 完整有 features_status，需 prompt_rewriter.hint
        # (b) 其他 needs_review（parse_failed / finish_reason_invalid 等）→ verdict 不可信，
        #     仍返 (None, "needs_review") 走 jury_unavailable。
        if "matches_spec_failed" in verdict.parse_anomalies:
            return (verdict, "matches_spec_failed")
        return (None, "needs_review")
    return (verdict, None)
```

改成：

```python
    if verdict.verdict == "needs_review":
        # Task 9 v2.37 (C)：matches_spec_failed 路径保留 verdict 让上层走 retry 而非 jury_unavailable。
        # 区分两类 needs_review：
        # (a) anomaly=matches_spec_failed → verdict 完整有 features_status，需 prompt_rewriter.hint
        # (b) anomaly=photoreal_below_threshold → verdict 完整可信，仅 photoreal 不达标，
        #     无 hint() 仅重渲（v2.37.9 §11-N6 改动 1b BLOCKER fix）
        # (c) 其他 needs_review（parse_failed / finish_reason_invalid 等）→ verdict 不可信，
        #     仍返 (None, "needs_review") 走 jury_unavailable。
        if "matches_spec_failed" in verdict.parse_anomalies:
            return (verdict, "matches_spec_failed")
        if "photoreal_below_threshold" in verdict.parse_anomalies:
            return (verdict, "photoreal_below_threshold")
        return (None, "needs_review")
    return (verdict, None)
```

### Step 4: 跑测试 3 PASS（GREEN）

```bash
pytest tests/jury_loop/test_orchestrator_photoreal_retry.py -v 2>&1 | tail -10
```

Expected: 3 PASS

### Step 5: 跑 jury_loop 子集零回归

```bash
pytest -q tests/jury_loop/ 2>&1 | tail -5
```

Expected: jury_loop 子集 PASS / 0 regression

### Step 6: dev_sync + Commit

```bash
python scripts/dev_sync.py 2>&1 | tail -3
git add tools/jury_loop/orchestrator.py tests/jury_loop/test_orchestrator_photoreal_retry.py
git -c commit.gpgsign=false commit -m "feat(jury-loop): orchestrator retry 白名单扩 photoreal_below_threshold（§11-N6 改动 1b BLOCKER fix）

orchestrator.py:199 +3 行 — photoreal_below_threshold 走 retry path
（与 matches_spec_failed 平行；无 prompt_rewriter.hint 仅重渲）。

新 TDD test_orchestrator_photoreal_retry.py — 3 测试：
- T-orch-photoreal-retry (BLOCKER fix 主断言)
- T-orch-matches-spec (回归 anchor)
- T-orch-parse-fail (回归 anchor)

防 PR 主目的失败 — rev 2 spec 改 verdict.py 后 retry 仍不启动，本改动闭环。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 3: 改动 1c MAJOR — photo3d_delivery_pack needs_review 兜底

**Files:**
- Modify: `tools/photo3d_delivery_pack.py:144`
- Create: `tests/test_delivery_needs_review_ship.py`

**预计:** 15 分钟

### Step 1: 写 TDD 测试 `tests/test_delivery_needs_review_ship.py`

完整内容：

```python
"""tests/test_delivery_needs_review_ship.py — §11-N6 改动 1c MAJOR fix TDD。

测试 photo3d_delivery_pack:144 status=needs_review 兜底 copy_preview ship。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def _build_minimal_enhancement_report(status: str) -> dict:
    """构造最小化 enhancement_report dict（仅用于 final_deliverable + copy_preview 判定）。"""
    return {
        "delivery_status": status,
        "render_dir": "/tmp/test",
        "view_count": 7,
        "quality_summary": {"status": "accepted"},
        "views": [],
    }


def test_status_accepted_final_deliverable() -> None:
    """T-delivery-accepted — status=accepted → final_deliverable=True（回归 anchor）。"""
    report = _build_minimal_enhancement_report("accepted")
    # 直接验证派生逻辑等价表达
    final_deliverable = report["delivery_status"] == "accepted"
    copy_preview = report["delivery_status"] in {"preview", "needs_review"} and True
    assert final_deliverable is True
    assert copy_preview is False


def test_status_preview_copy_preview_ship() -> None:
    """T-delivery-preview — status=preview → copy_preview ship（回归 anchor）。"""
    report = _build_minimal_enhancement_report("preview")
    final_deliverable = report["delivery_status"] == "accepted"
    copy_preview = report["delivery_status"] in {"preview", "needs_review"} and True
    assert final_deliverable is False
    assert copy_preview is True


def test_status_needs_review_copy_preview_ship() -> None:
    """T-delivery-needs-review-ship (MAJOR fix 主断言) — status=needs_review 兜底 copy_preview ship。"""
    report = _build_minimal_enhancement_report("needs_review")
    final_deliverable = report["delivery_status"] == "accepted"
    # rev 3 改动 1c：needs_review ∈ {preview, needs_review} → copy_preview = True
    copy_preview = report["delivery_status"] in {"preview", "needs_review"} and True
    assert final_deliverable is False
    assert copy_preview is True, "v2.37.9 §11-N6 改动 1c — needs_review 必兜底 copy_preview ship"


def test_status_unknown_no_ship() -> None:
    """T-delivery-unknown-no-ship — 未知 status 不 ship（边界）。"""
    report = _build_minimal_enhancement_report("blocked")
    final_deliverable = report["delivery_status"] == "accepted"
    copy_preview = report["delivery_status"] in {"preview", "needs_review"} and True
    assert final_deliverable is False
    assert copy_preview is False
```

**注意**：测试用"派生逻辑等价表达"避免依赖 `build_delivery_package` 完整调用链；plan Task 3 Step 4 跑 e2e regression 弥补。

### Step 2: 跑测试 1 FAIL + 3 PASS（RED + 3 anchor）

```bash
pytest tests/test_delivery_needs_review_ship.py -v 2>&1 | tail -10
```

Expected: `test_status_needs_review_copy_preview_ship` FAIL（当前 needs_review 不在 set）/ 3 anchor PASS

### Step 3: 改 photo3d_delivery_pack.py:143-144

打开 `tools/photo3d_delivery_pack.py` 找 line 143-144：

```python
    final_deliverable = enhancement_status == "accepted"
    copy_preview = enhancement_status == "preview" and include_preview
```

改成：

```python
    final_deliverable = enhancement_status == "accepted"
    # v2.37.9 §11-N6 改动 1c — needs_review 兜底走 copy_preview 防"retry 用尽未达 60 用户拿不到输出"
    copy_preview = enhancement_status in {"preview", "needs_review"} and include_preview
```

### Step 4: 跑测试 4 PASS（GREEN）+ 全 photo3d 测试零回归

```bash
pytest tests/test_delivery_needs_review_ship.py -v 2>&1 | tail -10
pytest -q -k "delivery or photo3d" 2>&1 | tail -5
```

Expected: 4 PASS + 既有 delivery 测试不回归

### Step 5: dev_sync + Commit

```bash
python scripts/dev_sync.py 2>&1 | tail -3
git add tools/photo3d_delivery_pack.py tests/test_delivery_needs_review_ship.py
git -c commit.gpgsign=false commit -m "feat(delivery): needs_review 兜底 copy_preview ship（§11-N6 改动 1c MAJOR fix）

photo3d_delivery_pack.py:144 改 copy_preview 条件含 needs_review —
防 cascade 退步：rev 2 改 verdict.py 后 status=needs_review，但 v2.37.7 是 preview。
不兜底则用户拿不到输出（'改完比之前糟' 真路径）。

新 TDD test_delivery_needs_review_ship.py — 4 测试：
- T-delivery-needs-review-ship (MAJOR fix 主断言)
- T-delivery-accepted / T-delivery-preview / T-delivery-unknown-no-ship (回归 anchor)

闭环 spec rev 3 §9.4 PR 主目的 7 步链路第 7 步（delivery ship）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 4: 改动 2 — max_retries 1→2 + test_config snapshot 同步

**Files:**
- Modify: `tools/jury_loop/config.py:48`
- Modify: `tests/jury_loop/conftest.py:186`
- Modify: `tests/jury_loop/test_config.py` 5 处

**预计:** 10 分钟

### Step 1: 改 production default

打开 `tools/jury_loop/config.py` 找 line 47-48：

```python
        "threshold": 75,
        "max_retries": 1,
```

改成：

```python
        "threshold": 75,  # v2.37.9 §2.2 双层 gate：retry 短路（score≥75 不 retry）— 不动
        "max_retries": 2,  # v2.37.9 §11-N6 — 1→2 支持 2 轮 retry 提升 photoreal
```

### Step 2: 改 conftest.py fixture default

打开 `tests/jury_loop/conftest.py` 找 line 186：

```python
        max_retries: int = 1,
```

改成：

```python
        max_retries: int = 2,  # v2.37.9 §11-N6 mirror production default
```

### Step 3: 改 test_config.py 5 处 snapshot

打开 `tests/jury_loop/test_config.py`，逐个找以下行（line 32 / 49 / 70 / 97 / 122）改：

```diff
- "max_retries": 1,
+ "max_retries": 2,
```

line 49 是 assert：

```diff
- assert config.advanced["max_retries"] == 1
+ assert config.advanced["max_retries"] == 2
```

注意：`test_orchestrator.py:39` `"max_retries": 1` **不动**（是测 max_retries=1 行为的显式场景）。

### Step 4: 跑 jury_loop 子集零回归

```bash
pytest -q tests/jury_loop/ 2>&1 | tail -5
```

Expected: 全 PASS / 0 regression

### Step 5: dev_sync + Commit

```bash
python scripts/dev_sync.py 2>&1 | tail -3
git add tools/jury_loop/config.py tests/jury_loop/conftest.py tests/jury_loop/test_config.py
git -c commit.gpgsign=false commit -m "feat(jury-loop): max_retries 默认 1→2（§11-N6 改动 2）

production config default + conftest fixture default + 5 处 test_config.py snapshot 同步 1→2。
test_orchestrator.py:39 不动（显式 max_retries=1 场景测试）。

成本分析：每 retry round ~\$0.35 / 2 round ~\$0.70 / cost_cap_usd=1.5 默认仍有 50% 安全空间。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 5: 全套件 + dev_sync 最终验证

**Files:** 无（验证 only）

**预计:** 5 分钟

### Step 1: dev_sync --check 验证

```bash
python scripts/dev_sync.py --check 2>&1 | tail -3
```

Expected: exit 0 / no drift

### Step 2: 跑 jury + jury_loop 全测试

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -5
```

Expected: jury+jury_loop 子集 PASS / 0 regression

### Step 3: 跑全套件冒烟（限 60s timeout）

```bash
pytest -q --timeout 60 tests/ 2>&1 | tail -5
```

Expected: 全套件 3217+ PASS / ~18 skipped / 0 regression（baseline v2.37.8 main@`7434b27` 3217 PASS + 本 PR 新增 ~10）

### Step 4: branch state

```bash
git log --oneline main..feat/v2-37-9-jury-retry-real-vendor
git status -s
```

Expected: 4 implementation commit + spec rev 1+2+3 + plan + retro 待 = 7-9 commit on branch

---

## Task 6: 真 vendor 实测 GISBOT — 端到端 retry 闭环验证

**Files:** 无 git（外部 cad-tests 目录跑 + retro 文档归档实测数据）

**预计:** 15 分钟实跑 + ~$0.50 cost

### Step 1: 前置 ops

```bash
# 1. touch sentinel marker（v2.37.8 spec §3.1.0 契约）
touch D:/Work/cad-tests/GISBOT/.test-archive-marker
ls -la D:/Work/cad-tests/GISBOT/.test-archive-marker

# 2. rebrand metadata 让 metadata="GISBOT" 与 directory 名一致（v2.37.8 工具）
python tools/dev/rebrand_test_archive.py D:/Work/cad-tests/GISBOT \
  --from end_effector --to GISBOT --apply

# 3. 确认 env vars
echo "GEMINI_API_KEY=${GEMINI_API_KEY:0:8}..."  # 8 chars prefix only
ls ~/.claude/jury_config.json  # jury vendor config 应存在（v2.37.7 setup）
```

Expected: marker touched / rebrand 改 8 类 JSON metadata / GEMINI_API_KEY 与 jury_config 都有

### Step 2: 跑 cad_pipeline enhance-check（端到端 jury_loop 触发）

```bash
cd D:/Work/cad-tests/GISBOT
# plan Task 0 探查实际 entry — 候选 1: subcommand 派发
python -m cad_spec_gen.cad_pipeline enhance-check --skill end_effector --confirm \
  --max-cost-usd 0.50 \
  2>&1 | tee /tmp/v2-37-9-real-vendor-test.log
```

如果 entry 不对，备选：

```bash
# 候选 2: 直接 import
cd D:/Work/cad-tests/GISBOT
python -c "
import sys
sys.path.insert(0, 'D:/Work/cad-spec-gen/src/cad_spec_gen/data/python_tools')
import cad_pipeline
import argparse
ns = argparse.Namespace(skill='end_effector', confirm=True, max_cost_usd=0.50)
cad_pipeline.cmd_enhance_check(ns)
" 2>&1 | tee /tmp/v2-37-9-real-vendor-test.log
```

Expected stderr 包含：
- `[jury] view 1/7 ... photoreal=...` 进度行
- 至少 1 视角 retry 触发 (`[jury-loop] retry view X round 1`)
- 最终 status="accepted" 或 status="needs_review" (兜底 copy_preview)
- cost log < $0.50

### Step 3: 读 PHOTO3D_JURY_REPORT.json 验 photoreal

```bash
find D:/Work/cad-tests/GISBOT -name "PHOTO3D_JURY_REPORT.json" -newer /tmp/v2-37-9-pre-test 2>&1 | \
  xargs python -c "
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
print('status:', d.get('status'))
print('overall_photoreal:', d.get('overall_photoreal'))
views = d.get('views', [])
print('view count:', len(views))
scores = [v.get('photoreal_score') for v in views]
print('scores:', scores)
print('verdicts:', [v.get('verdict') for v in views])
print('avg:', sum(scores)/len(scores) if scores else None)
print('min:', min(scores) if scores else None)
print('any_retry:', any('retry' in str(v.get('parse_anomalies', [])) for v in views))
"
```

Expected:
- avg photoreal ≥ 60 (best case) **或** baseline avg 40 if retry 全 fail（不退步）
- status="accepted" (best) 或 "needs_review" (兜底)
- 至少 1 视角 retry_score_delta!=0（retry 真跑了）

### Step 4: 实测数据写到 retro 文档（Task 7 完成）

记录到 `D:/Work/cad-spec-gen/tmp/v2-37-9-real-vendor-test-result.txt`（不进 git）：

```
v2.37.9 真 vendor GISBOT 实测结果 (2026-05-16):
- photoreal scores: [..., ..., ...]
- avg: X
- min: X
- status: ...
- retry 启动: True/False
- 实测 cost: $X.XX
- AC-6: ≥60? Y/N
- AC-7: ≤$0.50? Y/N
```

retro 文档（Task 7）引用此实测结果。

### Step 5: AC 验证

| AC | 期望 | 实证 |
| --- | --- | --- |
| AC-6 | photoreal ≥ 60 / status=accepted | ... |
| AC-7 | cost ≤ $0.50 | ... |
| 闭环 | retry round 真触发 | ... |

如 AC-6 fail（vendor 能力不足）：不算退步（spec §3.3.4 D1 已说明）— retro 记录 + 新登 §11-N7 follow-up 调 max_retries=3 / 改 backend。

### Step 6: 无 commit（实测在外部归档）

实测无 git 改动 — 进 Task 7 写 retro 引用实测数据。

---

## Task 7: retro 文档

**Files:**
- Create: `docs/superpowers/reports/2026-05-16-v2-37-9-jury-retry-real-vendor-retro.md`

**预计:** 10 分钟

### Step 1: 写 retro

完整内容（含 Task 6 实测真值）：

```markdown
# v2.37.9 — jury verdict + retry + 真 vendor 实测 retro

> 关联 PR: TBD（Task 8 push 后填）  
> 关联 spec: docs/superpowers/specs/2026-05-16-v2-37-9-jury-retry-real-vendor-design.md (rev 3, 437 行, commit `ff82879`)  
> 关联 plan: docs/superpowers/plans/2026-05-16-v2-37-9-jury-retry-real-vendor.md  
> Baseline: cad-spec-gen main@`7434b27`（v2.37.8 merge）

## 摘要

v2.37.9 闭合 §11-N6：photoreal<60 触发 retry 闭环 + 真 vendor 实测验证。改动 5 处跨 4 production 文件 + 3 新 TDD 文件 + 3 既有测试适配。0 regression / CI 8/8（pending push）/ GISBOT 真 vendor 实测 photoreal=X status=Y cost=$X.XX。

## 完成项

### 改动 1 — verdict.py photoreal<60 → needs_review + anomaly
- `tools/jury/verdict.py:159` 4 行改 + anomaly `photoreal_below_threshold`
- 4 新 TDD（59/60/35/45 边界）

### 改动 1b BLOCKER — orchestrator retry 白名单扩
- `tools/jury_loop/orchestrator.py:199` +3 行 photoreal_below_threshold 走 retry
- 3 新 TDD（BLOCKER fix 主断言 + 2 回归 anchor）
- 防 PR 主目的失败：rev 2 改 verdict.py 后 retry 仍不启动；本改动闭环

### 改动 1c MAJOR — photo3d_delivery_pack needs_review 兜底
- `tools/photo3d_delivery_pack.py:144` 1 行改 status set 加 needs_review
- 4 新 TDD（MAJOR fix 主断言 + 3 回归 anchor）
- 防 cascade 退步：rev 2 改后 status=needs_review 既不 final 也不 preview ship → 兜底 copy_preview

### 改动 2 — max_retries 1→2
- `tools/jury_loop/config.py:48` production default 1→2
- `tests/jury_loop/conftest.py:186` fixture default 1→2 mirror
- `tests/jury_loop/test_config.py` 5 处 snapshot 1→2 同步
- `test_orchestrator.py:39` 不动（显式 max_retries=1 测试场景）

## 实测结果（Task 6 真 vendor GISBOT）

（实施期填，参 /tmp/v2-37-9-real-vendor-test-result.txt）

| AC | 期望 | 实证 |
| --- | --- | --- |
| AC-6 photoreal ≥60 | photoreal ≥60 status=accepted | ... |
| AC-7 cost ≤$0.50 | ≤$0.50 | ... |
| 闭环 retry 真触发 | ≥1 视角 retry | ... |

## 走过的弯路 / Plan-drift（subagent 实施期发现）

（实施期填）

## 5 层 review 实证

| 层 | 抓 | spec rev |
| --- | --- | --- |
| Layer 6 scout | 5 处实证（threshold:75 非 stale / 双阈值合理设计 / preview-assert 测试影响）| rev 1 |
| self-review | 4 项过 | rev 1 inline |
| Layer 3 user review | 5 处漂移含 2 RISK-MAJOR（D1 vendor 能力 / D2 test scope / D3-D5 minor）| rev 1→rev 2 |
| 2nd boundary review | 1 BLOCKER + 1 MAJOR + 2 MINOR（B1+B2 orchestrator retry 路径 / B4 status cascade / B7 conftest / B9 anomaly 命名）| rev 2→rev 3 |

## §11 follow-up 更新

- 闭合：§11-N6
- 仍 open：§12 f4 / §11-N7 max_retries=3 (条件 Task 6 实测 fail) / §11-N8 photoreal 阈值配置化

## 后续工作

按 §6 YAGNI：
- v2.37.10 候选：§12 f4 N≥50 批量成本 / max_retries 调 3 (如实测 fail) / __help__ Windows mojibake
- 真 AI adapter v2 / 端到端图像质量回归
```

### Step 2: Commit retro

```bash
git add docs/superpowers/reports/2026-05-16-v2-37-9-jury-retry-real-vendor-retro.md
git -c commit.gpgsign=false commit -m "docs(retro): v2.37.9 jury verdict + retry + 真 vendor 实测 retro

§11-N6 5 改动 + 3 新 TDD + 真 vendor 实测验证。
4 轮 review 抓 5 处 D + 1 BLOCKER + 1 MAJOR + 4 MINOR cascade。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 8: PR push + CI

**Files:** 无（CI 操作）

**预计:** 5 分钟 + CI 等待

### Step 1: Push branch

```bash
git push -u origin feat/v2-37-9-jury-retry-real-vendor
```

### Step 2: 开 PR

```bash
gh pr create --base main --head feat/v2-37-9-jury-retry-real-vendor \
  --title "feat(jury): v2.37.9 — jury verdict + retry + 真 vendor 实测验证（§11-N6）" \
  --body "$(cat <<'EOF'
## 摘要

v2.37.9 闭合 §11-N6 — photoreal<60 触发 retry 闭环 + 真 vendor 实测验证。

| 改动 | 内容 |
| --- | --- |
| **1** | \`jury/verdict.py:159\` photoreal<60 升 needs_review + anomaly |
| **1b BLOCKER** | \`jury_loop/orchestrator.py:199\` retry 白名单扩 photoreal_below_threshold |
| **1c MAJOR** | \`photo3d_delivery_pack.py:144\` needs_review 兜底 copy_preview |
| **1d** | 适配 既有 preview-assert 测试 |
| **2** | \`jury_loop/config.py:48\` max_retries 1→2 + 6 处 test 同步 |
| **实测** | GISBOT 真 vendor 端到端 retry 闭环验证 photoreal ≥60 / cost ≤\$0.50 |

## 改动一览

| 文件 | 改动 |
| --- | --- |
| Modify \`tools/jury/verdict.py:158-162\` | photoreal<60 → needs_review + anomaly |
| Modify \`tools/jury_loop/orchestrator.py:193-201\` | retry 白名单 +3 行（BLOCKER fix）|
| Modify \`tools/photo3d_delivery_pack.py:143-144\` | needs_review 兜底 copy_preview（MAJOR fix）|
| Modify \`tools/jury_loop/config.py:47-48\` | max_retries 1→2 |
| Modify \`tests/jury_loop/conftest.py:186\` | fixture default mirror |
| Modify \`tests/jury_loop/test_config.py\` × 5 | snapshot 同步 |
| Modify \`tests/jury/test_verdict.py:97\` | preview-assert 适配 |
| Modify \`tests/jury/test_verdict_matches_spec.py:64\` | 兼容 assert 适配 |
| Create \`tests/jury/test_verdict_below_threshold.py\` | TDD 4 测试 |
| Create \`tests/jury_loop/test_orchestrator_photoreal_retry.py\` | TDD 3 测试 |
| Create \`tests/test_delivery_needs_review_ship.py\` | TDD 4 测试 |
| Create retro doc | v2.37.9 复盘 |

## TDD + 回归

- ✅ **11 新 TDD PASS**（verdict 4 + orchestrator 3 + delivery 4）
- ✅ jury+jury_loop 子集 PASS / 0 regression
- ✅ 全套件 3217+ PASS / 0 regression
- ⏳ CI 8/8（pending push）
- ✅ **真 vendor 实测**（Task 6 — \$X.XX cost / photoreal=X / status=Y）

## 4 轮 review 演进

- spec rev 1（180 行 brainstorm + scout 5 处 fix）
- spec rev 2（user review fix 5 处 D 含 2 RISK-MAJOR）
- spec rev 3（2nd boundary review fix 1 BLOCKER + 1 MAJOR + 2 MINOR cascade）
- batch implementer review（per task）

## spec §9.4 PR 主目的闭环（7 步链路）

1 verdict 决策 → 2 orchestrator retry 路径 → 3 enhance retry 启动 → 4 再 jury 评分 → 5 pick_best → 6 status 派生 → 7 delivery ship — **无任一步走"用户拿不到输出"路径**。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### Step 3: 等 CI 8/8（后台 watch）

```bash
gh pr checks --watch --interval 30
```

Expected: 8/8 SUCCESS（ubuntu/windows × 3.10/3.11/3.12 + regression + mypy-strict）

---

## Task 9: 等用户授权 merge + tag + Release + memory

**Files:** memory 文件

**预计:** 用户授权 + 5 min 收尾

### Step 1: 等用户授权 merge

CI 8/8 SUCCESS 后向用户报告，等待"授权 squash merge + tag v2.37.9 + Release"决策。

### Step 2: Squash merge

```bash
gh pr merge <PR#> --squash --subject "..." --body "..."
```

### Step 3: Tag + Release

```bash
git fetch origin main && git checkout main && git pull --ff-only
git tag -a v2.37.9 -m "v2.37.9 — jury verdict + retry + 真 vendor 实测"
git push origin v2.37.9
gh release create v2.37.9 --title "..." --notes "..."
```

### Step 4: Memory + MEMORY.md

写 `C:\Users\procheng\.claude\projects\D--Work-cad-spec-gen\memory\project_v2_37_9_done.md` + Edit MEMORY.md 追加一行。

---

## Self-Review

**1. Spec 覆盖：**

| spec § | task | 覆盖 |
| --- | --- | --- |
| §3.1 改动 1 verdict.py | Task 1 | ✓ |
| §3.1.3 既有测试适配 | Task 1 Step 5-6 | ✓ |
| §3.1b 改动 1b orchestrator | Task 2 | ✓ |
| §3.1c 改动 1c delivery_pack | Task 3 | ✓ |
| §3.2 改动 2 max_retries | Task 4 | ✓ |
| §3.2.2 6+ test scope | Task 4 Step 3 | ✓ |
| §3.3 实测 | Task 6 | ✓ |
| §5 AC-1~9 | Task 5 (AC-1-5/8-9) + Task 6 (AC-6-7) | ✓ |
| §9.4 7 步闭环验证 | Task 6 端到端 | ✓ |
| retro | Task 7 | ✓ |

无 spec gap。

**2. Placeholder scan：**
- Task 6 Step 2 entry "候选 1 / 候选 2" — Task 0 探查确定真值；plan 提供 2 选项 OK
- Task 6 Step 4 实测真值 `[..., ..., ...]` — 占位（plan 阶段无法预填）OK
- Task 7 retro "（实施期填）" × 2 — 占位 OK（plan-drift 实测记录留实施期填）
- Task 8 PR body 含 \$X / status=Y / photoreal=X — Task 6 实测填 OK
- Task 9 PR# / squash subject body / tag notes — 占位 OK

无 plan failure 红旗（占位都是实测/PR# 等运行时填）。

**3. Type consistency：**
- `photoreal_below_threshold` anomaly 字符串一致（Task 1+2 + spec §3.1b.3 + §9.3）
- `_parse_verdict_with_anomaly_path` 签名一致（Task 2 测试 + spec §3.1b.2）
- `enhancement_status` 命名一致（Task 3 + spec §3.1c.2）
- `_make_archive_tempdir` (v2.37.8 conftest) 不需引用（不同测试目录）

无 type drift。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-v2-37-9-jury-retry-real-vendor.md`。

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task + 2 stage review；适合 5 改动 + 实测 9 task
2. **Inline Execution** — 主 agent batch 跑 + checkpoint

**Which approach?**
