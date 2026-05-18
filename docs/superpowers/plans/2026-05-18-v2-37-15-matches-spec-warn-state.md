# v2.37.15 — `_derive_matches_spec_status` 扩 'warn' 中间态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `_derive_matches_spec_status` 加入 `'warn'` 中间态（部分视角失败），同时闭合 §11 #2 (warn 中间态) + §11 #3 (mirror drift archeology)。

**Architecture:** 用 `RunVerdict.view_verdicts` + `per_view_failed_features` 双条件防御（`passing_views > 0 ∧ failed_views > 0` → warn；否则 fail），与 RunVerdict 数据契约完全解耦。下游 enhance / delivery / TODO writer **早已 anticipated 'warn'**（spec §9.2.1），整条 jury → enhance → delivery 透传链 zero 代码改动。

**Tech Stack:** Python 3.11+ / pytest / pyproject 配置 ruff / mypy strict / `scripts/dev_sync.py` canonical-mirror 同步。

**Spec**：`docs/superpowers/specs/2026-05-18-v2-37-15-matches-spec-warn-state-design.md` (rev 3, 401 行, commit `89bd76a`)
**Branch**：`feat/v2-37-15-matches-spec-warn`
**Release 承诺**：v2.37.15（tag-only）

---

## 文件结构（locked）

| 文件 | 角色 | 改动类型 |
|---|---|---|
| `tools/photo3d_jury.py:195-211` | canonical（git tracked，37639 字节） | 行为变更（deriver 双条件 + docstring） |
| `src/cad_spec_gen/data/tools/photo3d_jury.py` | mirror（gitignored） | dev_sync 同步 |
| `tools/photo3d_delivery_pack.py:555` | canonical | 注释 v2.37.15 语义校准（函数体不动） |
| `src/cad_spec_gen/data/tools/photo3d_delivery_pack.py:555` | mirror | dev_sync 同步 |
| `tests/jury/test_photo3d_jury_matches_spec.py` | git tracked | 修 1 fixture (B-2) + 补 8 新 deriver 直测 |
| `tests/jury/test_cmd_enhance_check_matches_spec.py` | git tracked | 加 AC-6 透传 'warn' 用例 |
| `tests/jury_loop/test_matches_spec_e2e_smoke.py` | git tracked | docstring 注脚（M-2，纯文档） |
| `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §9.3 | git tracked | #2 closed v2.37.15 + #3 closed-by-v2.31.1 |

**不动文件**（spec §4.4 函数体层）：
- `photo3d_delivery_pack._check_matches_spec_failed_blocked` 函数体（仅 line 555 注释）
- `photo3d_delivery_pack._write_matches_spec_todo` 函数体（line 554-556 fallback 已 cover defensive UX）
- `enhance_consistency._read_jury_matches_spec_status`（透传层 anticipated 'warn'）
- PHOTO3D_JURY_REPORT schema_version 仍 1

---

## Task 0：Scout grep + 基线验证（plan-drift 5 分类预防）

**Files:**
- Read: `tools/photo3d_jury.py`, `tools/photo3d_delivery_pack.py`, `tests/jury/test_photo3d_jury_matches_spec.py`, `tests/jury/test_cmd_enhance_check_matches_spec.py`

- [ ] **Step 1: 锁 canonical / mirror 路径**

Run:
```bash
git ls-files tools/photo3d_jury.py tools/photo3d_delivery_pack.py
git check-ignore src/cad_spec_gen/data/tools/photo3d_jury.py src/cad_spec_gen/data/tools/photo3d_delivery_pack.py
diff tools/photo3d_jury.py src/cad_spec_gen/data/tools/photo3d_jury.py
stat -c "%s %n" tools/photo3d_jury.py src/cad_spec_gen/data/tools/photo3d_jury.py
```
Expected:
- 前两文件 tracked，后两 gitignored（命中 `.gitignore`）
- diff 空，字节相等（37639 / photo3d_jury.py）

- [ ] **Step 2: 验证 `_derive_matches_spec_status` 调用点唯一**

Run: `grep -rn "_derive_matches_spec_status" --include="*.py"`
Expected: 仅 3 处命中：
- `tools/photo3d_jury.py:195` (canonical 定义)
- `tools/photo3d_jury.py:750` (canonical 调用)
- mirror 两份对应行（dev_sync 同步）

如有第 4 处命中 → STOP，先改 spec。

- [ ] **Step 3: 验证下游消费方 anticipated 'warn'（spec §9.2.1 证据）**

Run:
```bash
grep -n "'warn'\|warn / 缺失\|matches_spec_status='fail' 但 per_view_failed_features 空" tools/photo3d_delivery_pack.py src/cad_spec_gen/data/tools/enhance_consistency.py
```
Expected:
- `enhance_consistency.py:565` 含 `"'pass' | 'fail' | 'warn'（jury 真实值）"`
- `photo3d_delivery_pack.py:447` 含 `"matches_spec_status 不是 'fail'（pass / warn / 缺失）"`
- `photo3d_delivery_pack.py:555` 含 `"matches_spec_status='fail' 但 per_view_failed_features 空（极端边界）"`

任一缺失 → STOP，先核查 spec rev 3 §9.2.1 引用是否过时。

- [ ] **Step 4: 跑基线 pytest 验证起点 GREEN**

Run:
```bash
python -m pytest tests/jury/test_photo3d_jury_matches_spec.py tests/jury/test_cmd_enhance_check_matches_spec.py -v 2>&1 | tail -20
```
Expected: 全部 PASS（含 `test_photo3d_jury_report_includes_run_verdict_aggregate` 的 `'fail'` assert）。

如有 fail → STOP，先修。

- [ ] **Step 5: 跑 dev_sync 验证 base 状态干净**

Run:
```bash
python scripts/dev_sync.py 2>&1 | tail -10
git status --short
```
Expected: 工作树仍 clean（无 mirror drift）。

- [ ] **Step 6: 不 commit（Task 0 是 read-only scout）**

---

## Task 1：修 AC-1a 现有 fixture（B-2 破坏-修复式 TDD RED 触发）

**Files:**
- Modify: `tests/jury/test_photo3d_jury_matches_spec.py:489-556`

- [ ] **Step 1: rename + 改 docstring + 改 assert**

改 `tests/jury/test_photo3d_jury_matches_spec.py` 中 `test_photo3d_jury_report_includes_run_verdict_aggregate`：

1. rename → `test_photo3d_jury_partial_fail_yields_warn_status`
2. docstring 改为：
```python
"""跑完所有视角后 PHOTO3D_JURY_REPORT.json 顶层应含 overall_matches_spec
+ per_view_failed_features + matches_spec_status。

场景：iso visible=True，front visible=False（fx1 missing）= partial fail
→ overall_matches_spec=False / per_view_failed_features={"front": ["fx1"]}
/ matches_spec_status='warn'（v2.37.15 起 partial fail = warn，单元层 AC-1a；
v2.37.14 之前归 'fail'）。
"""
```
3. assert 改为：
```python
assert rep["matches_spec_status"] == "warn", (
    f"matches_spec_status 应 'warn'（v2.37.15 起 partial fail = warn）；"
    f"实际 {rep.get('matches_spec_status')!r}"
)
```

- [ ] **Step 2: 跑测试验证 RED**

Run: `python -m pytest tests/jury/test_photo3d_jury_matches_spec.py::test_photo3d_jury_partial_fail_yields_warn_status -v`
Expected: FAIL — assert 报 `matches_spec_status 应 'warn'，实际 'fail'`（因为 deriver 还是 binary）

- [ ] **Step 3: commit RED**

```bash
git add tests/jury/test_photo3d_jury_matches_spec.py
git commit -m "test(jury): v2.37.15 AC-1a — partial fail fixture 改 'warn' assert（B-2 RED）

修 test_photo3d_jury_report_includes_run_verdict_aggregate：
- rename → test_photo3d_jury_partial_fail_yields_warn_status
- docstring v2.37.15 语义校准（partial fail = warn）
- assert 'fail' → 'warn'

RED 阶段：deriver 未改，pytest 应 FAIL。Task 3 GREEN。"
```

---

## Task 2：加 8 个 deriver 直测 fixture（AC-1b/c/d, 2, 3, 4, 5, 8 RED）

**Files:**
- Modify: `tests/jury/test_photo3d_jury_matches_spec.py`（追加 8 测试函数 + helper）

- [ ] **Step 1: 文件顶加 import + helper（如未有）**

确保文件含：
```python
from tools.photo3d_jury import _derive_matches_spec_status
from tools.jury.verdict import RunVerdict, ViewVerdict
```

加 helper：
```python
def _make_view_verdict(
    *, matches_spec: bool, has_features: bool = True
) -> ViewVerdict:
    """构造测 ViewVerdict — matches_spec 直接控制 semantic_checks。"""
    semantic_checks = {
        "anchor_visible": True,
        "no_obvious_missing": True,
        "no_extra_anomaly": True,
        "shape_proportions": True,
        "viewpoint_correct": True,
        "matches_spec": matches_spec,
    }
    features_status = (
        [{"feature_id": "f1", "visible": matches_spec}] if has_features else []
    )
    return ViewVerdict(
        semantic_checks=semantic_checks,
        photoreal_score=85,
        reason="",
        parse_status="ok",
        parse_anomalies=[],
        verdict="accepted" if matches_spec else "needs_review",
        features_status=features_status,
    )


def _make_run_verdict(
    *, total: int, failed: int, force_overall: bool | None = None
) -> RunVerdict:
    """构造测 RunVerdict — 直接控制 total / failed 计数。

    Args:
        total: 总视角数
        failed: 失败视角数（必须 <= total，除非测试 AC-8 defensive）
        force_overall: 显式覆盖 overall_matches_spec（用于 AC-8 构造非法 RunVerdict）
    """
    view_verdicts: dict[str, ViewVerdict] = {}
    per_view_failed: dict[str, list[str]] = {}
    for i in range(total):
        view_id = f"v{i + 1}"
        is_failed = i < failed
        view_verdicts[view_id] = _make_view_verdict(matches_spec=not is_failed)
        if is_failed:
            per_view_failed[view_id] = ["f1"]
    overall = (failed == 0) if force_overall is None else force_overall
    return RunVerdict(
        view_verdicts=view_verdicts,
        overall_matches_spec=overall,
        per_view_failed_features=per_view_failed,
    )
```

- [ ] **Step 2: 加 AC-1b 测试**

```python
def test_derive_status_partial_fail_1_of_3_yields_warn() -> None:
    """AC-1b：3 views, 1 failed → 'warn'（决策表 #3）。"""
    run = _make_run_verdict(total=3, failed=1)
    assert _derive_matches_spec_status(run) == "warn"
```

- [ ] **Step 3: 加 AC-1c 测试**

```python
def test_derive_status_partial_fail_2_of_5_yields_warn() -> None:
    """AC-1c：5 views, 2 failed → 'warn'（决策表 #4）。"""
    run = _make_run_verdict(total=5, failed=2)
    assert _derive_matches_spec_status(run) == "warn"
```

- [ ] **Step 4: 加 AC-1d 测试**

```python
def test_derive_status_partial_fail_4_of_5_yields_warn_boundary() -> None:
    """AC-1d：5 views, 4 failed（passing_views=1 边界）→ 'warn'（决策表 #5）。"""
    run = _make_run_verdict(total=5, failed=4)
    assert _derive_matches_spec_status(run) == "warn"
```

- [ ] **Step 5: 加 AC-2 测试**

```python
def test_derive_status_all_views_fail_yields_fail() -> None:
    """AC-2：3 views, 3 failed → 'fail'（决策表 #6，passing=0）。"""
    run = _make_run_verdict(total=3, failed=3)
    assert _derive_matches_spec_status(run) == "fail"
```

- [ ] **Step 6: 加 AC-3 测试**

```python
def test_derive_status_all_views_pass_yields_pass() -> None:
    """AC-3：2 views, 0 failed → 'pass'（决策表 #1）。"""
    run = _make_run_verdict(total=2, failed=0)
    assert _derive_matches_spec_status(run) == "pass"
```

- [ ] **Step 7: 加 AC-4 测试**

```python
def test_derive_status_empty_run_verdict_yields_pass() -> None:
    """AC-4：空 RunVerdict (total=0) → 'pass'（决策表 #2，空集 all=True）。"""
    run = _make_run_verdict(total=0, failed=0)
    assert _derive_matches_spec_status(run) == "pass"
```

- [ ] **Step 8: 加 AC-5 测试**

```python
def test_derive_status_single_view_fail_yields_fail() -> None:
    """AC-5：1 view, 1 failed → 'fail'（决策表 #7，passing=0 单视角无 partial）。"""
    run = _make_run_verdict(total=1, failed=1)
    assert _derive_matches_spec_status(run) == "fail"
```

- [ ] **Step 9: 加 AC-8 defensive 测试**

```python
def test_derive_status_overall_false_with_no_per_view_evidence_yields_fail_defensive() -> None:
    """AC-8：构造 RunVerdict overall=False ∧ per_view_failed_features={}
    模拟 LLM 异常路径（features_status 含 visible:False 但缺 feature_id）→ 'fail' defensive。

    决策表 #8。spec §3.1 双条件防御命中 fail。
    """
    # force_overall=False 模拟非法构造（aggregate_run_verdict 不会自然产此态，
    # 但 features_status 缺 feature_id 异常路径下可达 — 见 spec §5 I-6 撤回说明）
    run = _make_run_verdict(total=1, failed=0, force_overall=False)
    assert _derive_matches_spec_status(run) == "fail", (
        "defensive: overall=False ∧ per_view_failed_features={} → 'fail'，"
        "不返 'warn'（双条件 passing > 0 ∧ failed > 0 不满足）"
    )
```

- [ ] **Step 10: 跑测试验证 RED**

Run: `python -m pytest tests/jury/test_photo3d_jury_matches_spec.py -v -k "derive_status" 2>&1 | tail -20`
Expected:
- AC-3 / AC-4 (`yields_pass`) → PASS（'pass' 是现行为，deriver 返回 'pass'）
- AC-2 / AC-5 / AC-8 (`yields_fail`) → PASS（'fail' 是现 deriver fallback）
- AC-1b / AC-1c / AC-1d (`yields_warn`) → FAIL（deriver 当前没返 'warn'，返 'fail'）

→ 3 RED + 5 GREEN 是预期状态。

- [ ] **Step 11: commit RED**

```bash
git add tests/jury/test_photo3d_jury_matches_spec.py
git commit -m "test(jury): v2.37.15 AC-1b/c/d/2/3/4/5/8 — deriver 直测 8 fixture（RED）

新加 8 个 deriver 单元测试 + 2 helper (_make_view_verdict / _make_run_verdict)：
- AC-1b: 3 views, 1 failed → warn
- AC-1c: 5 views, 2 failed → warn
- AC-1d: 5 views, 4 failed（passing=1 边界）→ warn
- AC-2: 3 views, 3 failed → fail
- AC-3: 2 views, 0 failed → pass
- AC-4: 空 RunVerdict → pass
- AC-5: 单视角失败 → fail
- AC-8: defensive — overall=False ∧ per_view_failed_features={} → fail

RED 阶段：AC-1b/c/d 未 GREEN（deriver 还是 binary）。Task 3 实施 deriver。"
```

---

## Task 3：实现 deriver 双条件防御（GREEN 阶段，全 AC 一次通过）

**Files:**
- Modify: `tools/photo3d_jury.py:195-211`（canonical）
- Sync: `src/cad_spec_gen/data/tools/photo3d_jury.py`（mirror，dev_sync）

- [ ] **Step 1: 改 `_derive_matches_spec_status` 实现**

替换 `tools/photo3d_jury.py:195-211` 整段为：

```python
def _derive_matches_spec_status(run: RunVerdict) -> str:
    """v2.37.15：派生 matches_spec_status ∈ {'pass', 'warn', 'fail'}。

    决策表（用 RunVerdict 现有字段直接派生，零 schema 变动）：

    - 'pass'：所有视角 matches_spec=True（含 total_views=0 空集 all=True）
    - 'warn'：部分视角失败 — passing_views > 0 AND failed_views > 0
    - 'fail'：所有视角都失败 OR 失败视角无 feature-level 证据（防御性）

    判定用「双条件 warn」防御性写法，不依赖 aggregate_run_verdict 构造不变量：
    - LLM 输出异常路径（features_status 含 visible:False 但缺 feature_id）下，
      aggregate_run_verdict 构造的 RunVerdict 可能 overall_matches_spec=False
      但 per_view_failed_features={}。此时 failed_views=0，passing_views=total_views，
      落 'fail' 分支（保守 — 不假装 partial visible）。

    Args:
        run: aggregate_run_verdict 返回的 RunVerdict

    Returns:
        'pass' | 'warn' | 'fail'
    """
    if run.overall_matches_spec:
        return "pass"
    total_views = len(run.view_verdicts)
    failed_views = len(run.per_view_failed_features)
    # 注：aggregate_run_verdict 构造保证 failed.keys ⊆ view_verdicts.keys，
    # 故 passing_views >= 0；非法 fixture 构造（phantom key）下 passing_views
    # 可负，但短路 `passing_views > 0` 下负数也走 False，仍正确 fall 'fail'。
    passing_views = total_views - failed_views
    # warn 双条件 — 必须同时满足：至少 1 视角通过 + 至少 1 视角显式 feature-level 失败
    if passing_views > 0 and failed_views > 0:
        return "warn"
    return "fail"
```

- [ ] **Step 2: 跑 dev_sync 同步 mirror**

Run: `python scripts/dev_sync.py 2>&1 | tail -5`
Expected: 提示 `tools/photo3d_jury.py → src/cad_spec_gen/data/tools/photo3d_jury.py` 同步成功。

验证 byte-equal:
```bash
diff tools/photo3d_jury.py src/cad_spec_gen/data/tools/photo3d_jury.py
```
Expected: 空输出（byte-equal）。

- [ ] **Step 3: 跑 deriver 单测验证 GREEN**

Run: `python -m pytest tests/jury/test_photo3d_jury_matches_spec.py -v -k "derive_status or partial_fail_yields_warn" 2>&1 | tail -20`
Expected: AC-1a + AC-1b/c/d + AC-2/3/4/5/8 全部 PASS（9 个测试）。

- [ ] **Step 4: 跑 jury 全套件验证无回归**

Run: `python -m pytest tests/jury/ tests/jury_loop/ -v 2>&1 | tail -30`
Expected: 全 PASS（含 e2e smoke skip）。

如有 fail → STOP，逐一诊断（可能是 partial fail fixture 漏 update 或 LLM 异常路径未 cover）。

- [ ] **Step 5: commit GREEN**

```bash
git add tools/photo3d_jury.py src/cad_spec_gen/data/tools/photo3d_jury.py
git commit -m "feat(jury): v2.37.15 — _derive_matches_spec_status 双条件防御实现（GREEN）

_derive_matches_spec_status 改用双条件防御：
- pass: overall_matches_spec=True（early return）
- warn: passing_views > 0 ∧ failed_views > 0
- fail: 全失败 OR LLM 异常路径 defensive

docstring 写明决策表 + I-6 不依赖 + AC-8 异常路径处理。
passing_views 计算附防御性注释（phantom key 仍正确 fall 'fail'）。

GREEN：AC-1a + AC-1b/c/d + AC-2/3/4/5/8 共 9 deriver 测试全过。
canonical + mirror 通过 dev_sync 同步保 byte-equal。"
```

---

## Task 4：AC-6 — enhance-check 透传 'warn' 测试

**Files:**
- Modify: `tests/jury/test_cmd_enhance_check_matches_spec.py`（加 1 测试）

- [ ] **Step 1: 复用 `test_enhance_check_transits_matches_spec_status_pass` pattern 加 'warn' 用例**

加到文件末尾（或紧邻 pass/fail 测试之后）：

```python
def test_enhance_check_transits_matches_spec_status_warn(tmp_path: Path) -> None:
    """AC-6：matches_spec_status='warn' 透传到 ENHANCEMENT_REPORT.quality_summary
    且 delivery_status='accepted'（不 blocked，与 'fail' 路径区别）。"""
    cs_dir = tmp_path / "cad" / "lifting_platform" / ".cad-spec-gen"
    run_dir = cs_dir / "runs" / "test-run-warn"
    run_dir.mkdir(parents=True)
    (cs_dir / "ARTIFACT_INDEX.json").write_text(
        json.dumps({"active_run_id": "test-run-warn"}), encoding="utf-8"
    )
    (run_dir / "PHOTO3D_JURY_REPORT.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "subsystem": "lifting_platform",
                "overall_matches_spec": False,
                "per_view_failed_features": {"front": ["fx1"]},
                "matches_spec_status": "warn",
            }
        ),
        encoding="utf-8",
    )
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    manifest = {
        "subsystem": "lifting_platform",
        "schema_version": 1,
        "views": [],
    }
    (render_dir / "render_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    report = build_enhancement_report(
        project_root=tmp_path, render_dir=render_dir
    )

    assert report["quality_summary"]["matches_spec_status"] == "warn", (
        f"应透传 matches_spec_status=warn；实际 quality_summary={report['quality_summary']}"
    )
    assert report["delivery_status"] == "accepted", (
        f"'warn' 不阻断 delivery_status；实际 {report['delivery_status']!r}"
    )
```

注：`build_enhancement_report` import 来自 `enhance_consistency`。若 fixture pattern 与现有测试不同，参考同文件 `test_enhance_check_transits_matches_spec_status_pass` (line ~66-99) 完整复用。

- [ ] **Step 2: 跑测试验证 GREEN**

Run: `python -m pytest tests/jury/test_cmd_enhance_check_matches_spec.py::test_enhance_check_transits_matches_spec_status_warn -v`
Expected: PASS（下游 anticipated 'warn'，无需改实现即 GREEN）。

如 FAIL → 检查 `_read_jury_matches_spec_status` (line 549-595) 是否真的透传任意 enum 值。

- [ ] **Step 3: commit GREEN**

```bash
git add tests/jury/test_cmd_enhance_check_matches_spec.py
git commit -m "test(jury): v2.37.15 AC-6 — enhance-check 透传 'warn' GREEN

新加 test_enhance_check_transits_matches_spec_status_warn：
- 模拟 PHOTO3D_JURY_REPORT.matches_spec_status='warn'
- 验证 quality_summary.matches_spec_status='warn'
- 验证 delivery_status='accepted'（不 blocked）

下游 enhance_consistency._read_jury_matches_spec_status 早已 anticipated 'warn'
（line 565 docstring），无需改实现即 GREEN。"
```

---

## Task 5：注释更新 photo3d_delivery_pack.py:555（R2-3 + R2-6）

**Files:**
- Modify: `tools/photo3d_delivery_pack.py:555`（canonical）
- Sync: `src/cad_spec_gen/data/tools/photo3d_delivery_pack.py`（mirror）

- [ ] **Step 1: 改 line 555 注释**

替换 `tools/photo3d_delivery_pack.py:554-556` 原注释：

```python
    if not listed:
        # matches_spec_status='fail' 但 per_view_failed_features 空（极端边界）
        lines.append("- (无具体特征条目，请查 PHOTO3D_JURY_REPORT.json 排查)")
```

改为：

```python
    if not listed:
        # matches_spec_status='fail' 但 per_view_failed_features 空
        # （v2.37.15 起 = features_status 异常路径 defensive，或 jury 解析失败）
        lines.append("- (无具体特征条目，请查 PHOTO3D_JURY_REPORT.json 排查)")
```

**只改注释，函数体一行不动。**

- [ ] **Step 2: dev_sync 同步 mirror**

Run: `python scripts/dev_sync.py 2>&1 | tail -5`

验证:
```bash
diff tools/photo3d_delivery_pack.py src/cad_spec_gen/data/tools/photo3d_delivery_pack.py
```
Expected: 空（byte-equal）。

- [ ] **Step 3: 跑 photo3d_delivery_pack 测试验证零回归**

Run: `python -m pytest tests/test_photo3d_delivery_pack.py -v 2>&1 | tail -10`
Expected: 全 PASS（注释改不影响行为）。

- [ ] **Step 4: commit**

```bash
git add tools/photo3d_delivery_pack.py src/cad_spec_gen/data/tools/photo3d_delivery_pack.py
git commit -m "chore(delivery): v2.37.15 注释 v2.37.15 语义校准（line 555）

_write_matches_spec_todo 中 line 554-556 的 fallback message 注释更新：
原 \"（极端边界）\" → \"v2.37.15 起 = features_status 异常路径 defensive，
或 jury 解析失败\"。

函数体一行不动；fallback message 与 AC-8 defensive UX 闭环（spec §9.2.1）。
canonical + mirror dev_sync byte-equal。"
```

---

## Task 6：M-2 docstring 注脚（test_matches_spec_e2e_smoke.py）

**Files:**
- Modify: `tests/jury_loop/test_matches_spec_e2e_smoke.py`（line 34-47 区段 docstring）

- [ ] **Step 1: 加 docstring 注脚**

改 `test_e2e_matches_spec_fail_when_arms_removed` 函数 docstring 顶部加注脚：

```python
def test_e2e_matches_spec_fail_when_arms_removed() -> None:
    """反向：故意 break ee_001_01.py 删 4 臂 union -> matches_spec FAIL with missing flange_arms_4。

    注（v2.37.15）：本 fixture 假设全视角 features 集合相同（全删 flange_arms_4 → 全失败）→
    matches_spec_status='fail'。若 features 出现 per-view 差异（部分视角缺特征），
    partial fail 应为 'warn' 而非 'fail'。

    手动跑步骤：
    ...
    """
```

只加 docstring，函数体仍 `pytest.skip(...)`，零行为变化。

- [ ] **Step 2: 验证 marker 仍 skip**

Run: `python -m pytest tests/jury_loop/test_matches_spec_e2e_smoke.py -v 2>&1 | tail -10`
Expected: 3 测试全 SKIP（`requires_jury_loop_e2e` marker）。

- [ ] **Step 3: commit**

```bash
git add tests/jury_loop/test_matches_spec_e2e_smoke.py
git commit -m "docs(test): v2.37.15 M-2 — e2e smoke docstring 加 v2.37.15 注脚

test_e2e_matches_spec_fail_when_arms_removed 加 docstring 注脚：
说明本 fixture 全视角同步删 flange_arms_4，故 status='fail'；
未来 per-view 差异场景应区分 'warn'（partial fail）。

零行为变化（marker requires_jury_loop_e2e 仍 skip）。"
```

---

## Task 7：STATUS doc §9.3 闭合 #2 + #3（AC-7）

**Files:**
- Modify: `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §9.3 表

- [ ] **Step 1: 改 §9.3 表 #2 行**

找到 `JURY_MATCHES_SPEC_STATUS.md` §9.3 `| #2 | LOW |` 这一行（line ~73），改 content：

原：
```markdown
| #2 | LOW | `_derive_matches_spec_status` 加 'warn'/'blocked' 中间态 |
```

改为：
```markdown
| #2 | LOW | `_derive_matches_spec_status` 加 'warn'/'blocked' 中间态 — **closed v2.37.15**（实现 'warn' 部分视角失败 + drop 'blocked' 占位，详 [v2.37.15 spec](specs/2026-05-18-v2-37-15-matches-spec-warn-state-design.md) §2-§3） |
```

- [ ] **Step 2: 改 §9.3 表 #3 行**

原：
```markdown
| #3 | LOW | `tools/render_qa.py` mirror drift cleanup（pre-existing main 历史债）|
```

改为：
```markdown
| #3 | LOW | `tools/render_qa.py` mirror drift cleanup — **closed-by-v2.31.1**（archeology 注脚：`35629fa chore(packaging): 清理 v2.10 遗留 tracked mirror（55 文件 git rm --cached）` 已把 mirror 从 git tracked 移除 + `scripts/dev_sync.py` 接管同步 → drift 不再可能发生；v2.37.15 spec §1.3 追注闭合，无需改代码） |
```

- [ ] **Step 3: 跑 markdown link 检查（可选，但若仓有 link check 工具）**

如有 `markdownlint` 或类似，跑一次。否则跳过。

- [ ] **Step 4: commit**

```bash
git add docs/superpowers/JURY_MATCHES_SPEC_STATUS.md
git commit -m "docs(status): v2.37.15 AC-7 — §9.3 表闭合 #2 + #3

§9.3 follow-up 表：
- #2 (warn 中间态) 标 closed v2.37.15，指向 v2.37.15 spec
- #3 (render_qa.py mirror drift) 标 closed-by-v2.31.1，archeology 注脚指
  35629fa（v2.31.1 packaging cleanup git rm --cached 55 mirror）

不动 #4 (plan-drift 模板) / #5 (Task 13 cad-tests README) — 仍 open，下次触发。"
```

---

## Task 8：最终验证 + 准备 PR（CP-末 quality review）

**Files:**
- Read all changed files + run full test suite + CI lint/mypy gate

- [ ] **Step 1: 跑全套件 pytest 验证零回归**

Run:
```bash
python -m pytest -v 2>&1 | tail -30
```
Expected: 全 PASS（含 jury / jury_loop / enhance_consistency / delivery_pack）。

如有 fail → 逐一诊断。常见原因：
- 漏 dev_sync（mirror 未同步）→ 跑 `python scripts/dev_sync.py`
- 测试 fixture 旧 'fail' 期望未改 → grep `"== 'fail'"` 检查

- [ ] **Step 2: 跑 ruff check + format**

Run:
```bash
ruff check tools/ src/ tests/
ruff format --check tools/ src/ tests/
```
Expected: 全 PASS（0 errors / 0 format diff）。

如有 fail → `ruff format tools/ src/ tests/` 修。

- [ ] **Step 3: 跑 mypy strict（仅 CI gate 范围）**

Run:
```bash
mypy --strict tools/enhance_consistency.py tools/render_qa.py tools/path_policy.py tools/view_instance_evidence.py 2>&1 | tail -5
```
Expected: `Success: no issues found`。

如有 fail → 不属本 PR scope，但需诊断是否本 PR 引入（B-1 双条件改了 type 推断？）。

- [ ] **Step 4: 跑 git log 自审 commit 序列**

Run: `git log --oneline origin/main..HEAD`
Expected: 看到约 11 commit（3 spec rev + 7 task + 1 final）。检查：
- commit message 中文规范
- type(scope): 描述 格式
- 无 `WIP` / `fixup` 残留

- [ ] **Step 5: 检查 spec / plan 是否锁档**

Run:
```bash
git status --short
git diff --stat origin/main..HEAD
```
Expected: 工作树 clean；diff 在预期文件范围内（~120 lines code + ~150 lines test + ~30 lines docs）。

- [ ] **Step 6: push + 准备 PR**

Run:
```bash
git push -u origin feat/v2-37-15-matches-spec-warn
gh pr create --title "feat(jury): v2.37.15 — _derive_matches_spec_status 扩 'warn' 中间态 + §11 #3 archeology 闭合" --body "$(cat <<'EOF'
## 概述

实现 `_derive_matches_spec_status` 'warn' 中间态（部分视角失败），同时闭合 §11 follow-up #2 + #3。

## 改动

- **行为**：partial fail（部分视角失败）现归 `'warn'`（不阻断 delivery），全视角失败仍归 `'fail'`（delivery blocked）；'pass' 触发条件不变
- **schema_version 仍 1**（enum 值扩展向后兼容）
- **下游 chain zero 代码改动**（spec §9.2.1 — enhance / delivery / TODO writer 早已 anticipated 'warn'）

## §11 follow-up

- #2 (warn 中间态) ✅ closed v2.37.15
- #3 (mirror drift) ✅ closed-by-v2.31.1（archeology 追注）

## 文档

- spec: `docs/superpowers/specs/2026-05-18-v2-37-15-matches-spec-warn-state-design.md` (rev 3, 401 行)
- plan: `docs/superpowers/plans/2026-05-18-v2-37-15-matches-spec-warn-state.md`

## 审查

- spec 2 轮 4 层审查（11 处 fix 全闭，真闭环 gap = 0）
- 9 AC（含 AC-8 defensive 异常路径）
- canonical/mirror dev_sync byte-equal

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7: 监控 CI（不阻塞，用户决定 merge）**

Run: `gh pr checks --watch` 或 PR 页面观察 8/8 SUCCESS。

PR merge + tag v2.37.15 + GitHub Release 由用户触发（项目惯例：tag-only release）。

---

## Self-Review

### Spec 覆盖

| spec 要求 | 实施 task |
|---|---|
| §3.1 deriver 实现 | Task 3 |
| §3.2 决策表 8 行 | Task 2 (AC-1b/c/d/2/3/4/5/8 1:1 对应 #3-#8) + AC-1a (#3 family 2-view) Task 1 |
| §4.1 主代码（jury + delivery_pack 注释）| Task 3 + Task 5 |
| §4.2 测试 修+补 | Task 1 (修) + Task 2 (补) + Task 4 (AC-6) + Task 6 (M-2) |
| §4.3 文档（STATUS doc） | Task 7 |
| §4.5 canonical / mirror dev_sync | Task 3 step 2 + Task 5 step 2 |
| §5 不变量 I-1～I-7 | Task 3（实现）+ Task 2 (AC-8 verify) |
| §6 AC-1a/b/c/d, 2, 3, 4, 5, 6, 7, 8 | Task 1 (1a) + Task 2 (1b/c/d, 2, 3, 4, 5, 8) + Task 4 (6) + Task 7 (7) |
| §7 §11 follow-up 闭合 | Task 7 |
| §9 release notes 草稿 | Task 8 step 6 PR body 引用 |

无 spec 要求遗漏 ✅

### 占位扫描

- 无 "TBD" / "TODO" / "implement later"
- Task 1 step 1 完整改动指令（含 rename / docstring / assert 三处）
- Task 2 每个测试 step 含完整代码
- Task 3 step 1 deriver 全实现代码
- Task 4 step 1 完整 fixture
- Task 5 step 1 前后对照 diff
- Task 8 step 6 PR body 完整模板

无占位 ✅

### 类型一致性

- `_derive_matches_spec_status(run: RunVerdict) -> str` 签名 Task 2 helper + Task 3 实现一致
- `RunVerdict` / `ViewVerdict` import 路径 `tools.jury.verdict` Task 2 step 1 与 spec §3.1 一致
- 测试函数命名 Task 2 与 spec §4.2.1 表 8 行 1:1 对应

无类型/命名不一致 ✅

---

## Plan 完成 — 落地 `docs/superpowers/plans/2026-05-18-v2-37-15-matches-spec-warn-state.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
