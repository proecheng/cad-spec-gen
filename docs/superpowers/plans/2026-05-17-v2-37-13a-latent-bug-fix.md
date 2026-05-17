# v2.37.13a §11-N5 latent bug triage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 v2.37.12 F841 决策中发现的 2 处死代码（`bd_warehouse_adapter.py:295` 的 `l = float(m.group(2))` + `fal_enhancer.py:170-173` 的 `exr_exact = stem.replace(...)` 块），消除 noqa 同时不破坏现有行为。

**Architecture:** 死代码删除走 characterization TDD — 每 bug 先写 regression test 验证当前行为，再删死代码 + 更新注释，verify test 仍 PASS（行为不变）+ ruff F841 exit 0（结构无残留）。2 独立 commits，1 PR (#94)。

**Tech Stack:** pytest（characterization regression）+ ruff F841 gate（结构验证）。无新依赖。

**分支**: `feat/latent-bug-fix-v2.37.13` (off main @ c30e2bc)
**Spec**: 无（scope ~15 行 diff 不及 100 行阈值；brainstorming approved design 见 PR body）
**Brainstorming risk audit**: R-1~R-6 全缓解（详 PR body）；取消 regex 改非捕获 + 取消结构断言 TDD

---

## Task 1: Bug 1 — bd_warehouse_adapter.py 删 metric_screw 死 length 解析

**Files:**
- Test (create): `tests/test_latent_bug_v2_37_13a.py`
- Modify: `adapters/parts/bd_warehouse_adapter.py:295-297`

### Step 1.1 — Plan-drift 自检

- [ ] **Plan-drift 自检**
  - `git status -s` 确认 working tree clean
  - `git rev-parse HEAD` 确认在 `feat/latent-bug-fix-v2.37.13` 分支
  - `grep -n "l = float(m.group(2))" adapters/parts/bd_warehouse_adapter.py` 必返回 line 296
  - `grep -nE "size_patterns:|metric_screw:" catalogs/bd_warehouse_catalog.yaml | head -5` 确认 metric_screw regex 在 catalog

### Step 1.2 — 写 characterization 回归测试 (RED phase)

- [ ] **Create `tests/test_latent_bug_v2_37_13a.py`**

```python
"""§11-N5 latent bug triage — characterization regression tests for v2.37.13a.

These tests verify behavior is preserved across dead-code deletion. Each test
captures current behavior of the affected function so the deletion doesn't
silently regress.
"""
from pathlib import Path

import pytest


def test_bd_warehouse_metric_screw_drops_length_by_design():
    """§11-N5 Bug 1 characterization: M{d}×{length} → 'M{d}-{pitch}' (length intentionally dropped).

    Per catalog yaml line 211: 'Size format: M{d}-{pitch}' — csv_key for screws is
    (diameter, pitch) only. Length is parsed by regex as a format validator
    (rejecting bare 'M6' without ×length) but the numeric length value is not
    used in csv_key construction. This test pins that behavior.
    """
    from adapters.parts.bd_warehouse_adapter import BdWarehouseAdapter

    adapter = BdWarehouseAdapter()
    # Mock class_info with metric_screw pattern (M{d}×{length} or M{d}x{length})
    class_info = {
        "size_patterns": {
            "metric_screw": r"M(\d+(?:\.\d+)?)\s*[×x*]\s*(\d+(?:\.\d+)?)",
        }
    }

    # M6×20 — pitch_map[6] = 1.0 → csv_key "M6-1.0" (length 20 dropped)
    assert adapter._auto_extract_size_from_text("M6×20 内六角螺丝", class_info) == "M6-1.0"
    # M3×10 — pitch_map[3] = 0.5 → csv_key "M3-0.5"
    assert adapter._auto_extract_size_from_text("M3×10", class_info) == "M3-0.5"
    # M8×30 — pitch_map[8] = 1.25 → csv_key "M8-1.25"
    assert adapter._auto_extract_size_from_text("M8×30", class_info) == "M8-1.25"
    # Bare M6 (no ×length) — regex needs group 2; should NOT match metric_screw
    # (falls through to next pattern or returns None)
    assert adapter._auto_extract_size_from_text("M6", class_info) is None
```

### Step 1.3 — Run RED test before fix (sanity: should PASS even before fix because behavior unchanged)

- [ ] **Run test (RED phase but characterization, expect PASS)**

```bash
.venv/Scripts/python.exe -m pytest tests/test_latent_bug_v2_37_13a.py::test_bd_warehouse_metric_screw_drops_length_by_design -v
```

Expected: **PASS** (characterization captures *current* behavior; test passes before fix). This is intentional — characterization TDD captures preserve-behavior intent, not new behavior.

### Step 1.4 — Edit bd_warehouse_adapter.py: 删死代码 + 更新注释

- [ ] **Edit `adapters/parts/bd_warehouse_adapter.py:294-298`**

**Before (current):**
```python
        if rx:
            m = re.search(rx, text)
            if m:
                d = float(m.group(1))
                l = float(m.group(2))  # noqa: F841  # 超规则 残留
                pitch_map = {1.6: 0.35, 2: 0.4, 2.5: 0.45, 3: 0.5,
                             4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25,
                             10: 1.5, 12: 1.75, 14: 2.0, 16: 2.0,
                             20: 2.5, 24: 3.0, 30: 3.5, 36: 4.0}
                pitch = pitch_map.get(d, pitch_map.get(int(d), 0.5))
                return f"M{int(d) if d == int(d) else d}-{pitch}"
```

**After:**
```python
        if rx:
            m = re.search(rx, text)
            if m:
                d = float(m.group(1))
                # regex group 2 (length) is intentionally captured as a format
                # validator (rejects bare "M6" without ×length) but the numeric
                # value is NOT used in csv_key — per catalog yaml line 211:
                # "Size format: M{d}-{pitch}" — length is by-design dropped here
                # (§11-N5 v2.37.13a triage). If a fastener needs length-specific
                # lookup, use spec.size = "M{d}-{pitch}-{l}" explicit override.
                pitch_map = {1.6: 0.35, 2: 0.4, 2.5: 0.45, 3: 0.5,
                             4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25,
                             10: 1.5, 12: 1.75, 14: 2.0, 16: 2.0,
                             20: 2.5, 24: 3.0, 30: 3.5, 36: 4.0}
                pitch = pitch_map.get(d, pitch_map.get(int(d), 0.5))
                return f"M{int(d) if d == int(d) else d}-{pitch}"
```

Use Edit tool with `old_string` matching the `l = float(m.group(2))  # noqa: F841  # 超规则 残留` line exactly; replace with the 6-line comment block.

### Step 1.5 — Verify GREEN + ruff F841 + 全套件

- [ ] **Run characterization test (still PASS — behavior preserved)**
```bash
.venv/Scripts/python.exe -m pytest tests/test_latent_bug_v2_37_13a.py::test_bd_warehouse_metric_screw_drops_length_by_design -v
```
Expected: PASS

- [ ] **Verify ruff F841 clean (no F841 in file, no noqa needed)**
```bash
.venv/Scripts/ruff.exe check --select=F841 adapters/parts/bd_warehouse_adapter.py
```
Expected: `All checks passed!`

- [ ] **Verify no F841 noqa remaining in bd_warehouse_adapter.py**
```bash
grep -n "noqa: F841" adapters/parts/bd_warehouse_adapter.py | wc -l
```
Expected: `0`

- [ ] **Run full pytest suite — no regression**
```bash
.venv/Scripts/python.exe -m pytest -q --no-header 2>&1 | tail -3
```
Expected: PASS count ≥ 3238 (= 3237 baseline + 1 new test), 0 NEW fail (5 pre-existing OK)

### Step 1.6 — Commit Bug 1

- [ ] **Commit**
```bash
git add adapters/parts/bd_warehouse_adapter.py tests/test_latent_bug_v2_37_13a.py
git commit -m "$(cat <<'EOF'
fix(bd-warehouse): §11-N5 删 metric_screw 死 length 解析 + 注释 by-design

v2.37.12 F841 决策发现 _auto_extract_size_from_text 的 metric_screw 分支
捕获 (d, l) 但 csv_key 仅 (d, pitch) — l 是死代码。本 commit 删 Python
`l = float(m.group(2))` + 对应 noqa: F841；regex group 2 保留作"M{d}×{length}"
格式验证器（拒绝裸 'M6' without ×length）；docstring 注释明示设计意图引用
catalog yaml line 211 "Size format: M{d}-{pitch}"。

行为不变（characterization regression test 验证 M6×20 仍 → M6-1.0；M3×10
→ M3-0.5；M8×30 → M8-1.25；bare 'M6' → None）。

§11-N5 triage Option A (删死代码 + 清注释) — 详见 v2.37.12 retro §4.1。
P3 P3 spec 若需 length-aware lookup，用 spec.size = "M{d}-{pitch}-{l}" 显式 override。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Bug 2 — fal_enhancer.py 删 `_find_depth_for_png` 死 `exr_exact` 块

**Files:**
- Test (modify): `tests/test_latent_bug_v2_37_13a.py` (append)
- Modify: `fal_enhancer.py:155-180`

### Step 2.1 — Plan-drift 自检

- [ ] **自检**
  - `git status -s` 确认仅 tmp/ untracked，无 modified
  - `git rev-parse HEAD` 确认是 commit 1 SHA
  - `grep -n "exr_exact" fal_enhancer.py` 必返回 line 172 + 173
  - `grep -nE "_find_depth_for_png" fal_enhancer.py` 确认函数定义

### Step 2.2 — Append characterization test to test file

- [ ] **Append to `tests/test_latent_bug_v2_37_13a.py`**

```python
def test_fal_enhancer_find_depth_via_glob_view_key(tmp_path, monkeypatch):
    """§11-N5 Bug 2 characterization: _find_depth_for_png matches via glob + view_key filter.

    Original code had a docstring promising "Step 1 exact match + Step 2 glob fallback"
    but implementation only ran Step 2 (wide glob filtered by view_key prefix).
    This test pins the actual working behavior: V1 PNG finds V1_depth_*.exr,
    V2_depth_*.exr is correctly excluded.
    """
    from fal_enhancer import _find_depth_for_png

    # Setup: V1 PNG + V1_depth_0001.exr in same dir
    png = tmp_path / "V1_front_iso.png"
    png.write_bytes(b"fake png")
    depth_exr = tmp_path / "V1_depth_0001.exr"
    depth_exr.write_bytes(b"fake exr")
    # V2 EXR should NOT match V1 PNG
    v2_exr = tmp_path / "V2_depth_0001.exr"
    v2_exr.write_bytes(b"fake v2 exr")

    # Mock convert_depth_exr_to_png — we test selection logic, not conversion
    called_with: list[str] = []

    def fake_convert(exr_in: str, png_out: str, rgb_png_path: str | None = None) -> None:
        called_with.append(exr_in)
        Path(png_out).write_bytes(b"fake converted")

    monkeypatch.setattr("fal_enhancer.convert_depth_exr_to_png", fake_convert)

    result_path, is_temp = _find_depth_for_png(str(png))

    # V1 EXR was matched, V2 was not
    assert len(called_with) == 1
    assert "V1_depth" in Path(called_with[0]).name
    assert "V2_depth" not in Path(called_with[0]).name
    assert is_temp is True  # returned tmp file (from convert)
    assert result_path is not None
```

### Step 2.3 — Run characterization test (PASS before fix)

- [ ] **Run test (PASS expected — pins current behavior)**
```bash
.venv/Scripts/python.exe -m pytest tests/test_latent_bug_v2_37_13a.py::test_fal_enhancer_find_depth_via_glob_view_key -v
```
Expected: PASS (characterization captures *current* glob+filter behavior).

### Step 2.4 — Edit fal_enhancer.py: 删死代码 + 重写注释

- [ ] **Edit `fal_enhancer.py:155-180`** (the `_find_depth_for_png` function)

**Before (current):**
```python
def _find_depth_for_png(png_path):
    """Locate the depth EXR/PNG corresponding to a render PNG.

    Search order:
    1. {stem}_depth_.exr (Blender render pass output)
    2. {stem}_depth.png (pre-converted)
    3. {dir}/V{N}_depth_*.exr (glob pattern)

    Returns (depth_png_path, is_temp) or (None, False).
    """
    import glob as _glob

    stem = os.path.splitext(png_path)[0]
    render_dir = os.path.dirname(png_path)

    # 1. Exact match: {stem}_depth_.exr
    exr_exact = stem.replace(os.path.basename(stem),  # noqa: F841  # 超规则 残留
                              os.path.basename(stem).split("_")[0] + "_depth_")
    for exr_candidate in _glob.glob(os.path.join(render_dir, "*depth*.exr")):
        # Match by view key (V1, V2, etc.)
        view_key = os.path.basename(png_path).split("_")[0]  # "V1"
        if view_key.lower() in os.path.basename(exr_candidate).lower():
```

**After:**
```python
def _find_depth_for_png(png_path):
    """Locate the depth EXR/PNG corresponding to a render PNG.

    Search strategy:
    - Glob {dir}/*depth*.exr filtered by view-key prefix (V1, V2, etc.) →
      convert matched EXR to a temp PNG via convert_depth_exr_to_png.
    - Fallback: glob {dir}/*depth*.png filtered by view-key → return as-is.

    The view-key (parsed from png filename leading segment, e.g. "V1_front_iso.png"
    → "V1") is the disambiguator: V1 PNG only matches V1_*depth*.exr, not V2_*depth*.

    Returns (depth_png_path, is_temp) or (None, False).

    Note (§11-N5 v2.37.13a triage): an earlier docstring promised "Step 1 exact
    match by reconstructed prefix + Step 2 glob fallback" but Step 1 was never
    implemented; only Step 2 wide glob + view_key filter ran. The dead
    prefix-construction line and noqa: F841 were removed since the wide-glob
    path is functionally complete.
    """
    import glob as _glob

    stem = os.path.splitext(png_path)[0]
    render_dir = os.path.dirname(png_path)

    for exr_candidate in _glob.glob(os.path.join(render_dir, "*depth*.exr")):
        # Match by view key (V1, V2, etc.)
        view_key = os.path.basename(png_path).split("_")[0]  # "V1"
        if view_key.lower() in os.path.basename(exr_candidate).lower():
```

Use Edit tool: `old_string` matches the full docstring + the `exr_exact = ...` line + closing 2 lines of comment; `new_string` is the rewritten version above (note: `stem` is still computed for `render_dir` use, but `exr_exact` and its comment-block are gone; the original `stem` line is kept because it's used for render_dir computation… actually `render_dir = os.path.dirname(png_path)` doesn't need `stem`. Let me re-check.

Actually `stem = os.path.splitext(png_path)[0]` was used by `exr_exact` (which is being deleted). After deletion, `stem` becomes dead too. Delete it as well:

**Revised After (simpler):**
```python
def _find_depth_for_png(png_path):
    """[docstring as above]"""
    import glob as _glob

    render_dir = os.path.dirname(png_path)

    for exr_candidate in _glob.glob(os.path.join(render_dir, "*depth*.exr")):
        # ... (rest unchanged)
```

Both `stem` and `exr_exact` go. Net deletion 3 lines + docstring rewrite.

### Step 2.5 — Verify GREEN + ruff F841 + 全套件

- [ ] **Run characterization test (still PASS)**
```bash
.venv/Scripts/python.exe -m pytest tests/test_latent_bug_v2_37_13a.py::test_fal_enhancer_find_depth_via_glob_view_key -v
```
Expected: PASS

- [ ] **Verify ruff F841 clean on fal_enhancer.py**
```bash
.venv/Scripts/ruff.exe check --select=F841 fal_enhancer.py
```
Expected: `All checks passed!`

- [ ] **Run full pytest suite (含 2 个新测试)**
```bash
.venv/Scripts/python.exe -m pytest -q --no-header 2>&1 | tail -3
```
Expected: PASS count ≥ 3239 (= 3237 + 2 new tests), 0 NEW fail

### Step 2.6 — Commit Bug 2

- [ ] **Commit**
```bash
git add fal_enhancer.py tests/test_latent_bug_v2_37_13a.py
git commit -m "$(cat <<'EOF'
fix(fal-enhancer): §11-N5 删 _find_depth_for_png 死 exr_exact + 重写 docstring

v2.37.12 F841 决策发现 _find_depth_for_png 的 docstring 承诺 "Step 1 exact
match + Step 2 glob fallback" 但 Step 1 从未实现；`exr_exact = stem.replace(...)`
构造好但永不使用。本 commit 删 stem + exr_exact 死代码 + 对应 noqa: F841；
重写 docstring 描述实际行为（single-step wide glob + view-key prefix filter），
并在 Note 段说明本次清理的来源（§11-N5 v2.37.13a triage）。

行为不变（characterization regression test 验证 V1 PNG 仍正确匹配 V1_depth_*.exr，
V2_depth_*.exr 被 view_key filter 正确排除）。

§11-N5 triage Option A (删死代码 + 清注释) — 详见 v2.37.12 retro §4.2。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 终态 AC + push + PR open

### Step 3.1 — 全局 ruff F841 + pytest baseline 验证

- [ ] **ruff F841 整仓清零**
```bash
.venv/Scripts/ruff.exe check --select=F841 . 2>&1 | tail -3
```
Expected: `All checks passed!`

- [ ] **全套件 pytest 通过**
```bash
.venv/Scripts/python.exe -m pytest -q --no-header 2>&1 | tail -3
```
Expected: PASS ≥ 3239（baseline 3237 + 2 new tests），0 new fail

### Step 3.2 — git log + push

- [ ] **Verify 2 commits**
```bash
git log --oneline main..HEAD
```
Expected: 2 lines starting with `fix(bd-warehouse)` and `fix(fal-enhancer)`.

- [ ] **Push**
```bash
git push -u origin feat/latent-bug-fix-v2.37.13
```

### Step 3.3 — Open PR #94

- [ ] **gh pr create**
```bash
gh pr create \
  --title "fix: §11-N5 latent bug triage — 删 2 处死代码 + 清注释（v2.37.13a）" \
  --body "$(cat <<'EOF'
## 摘要

v2.37.12 F841 决策中发现的 2 处 latent bug 经 brainstorming triage 决定为
"删死代码 + 清注释"（Option A），不是真补行为（Option B 太重）。两处都是
"代码-注释 promise 不一致" 而非真功能缺陷。

## 改动

| Bug | 文件 | 改动 |
|---|---|---|
| 1 | `adapters/parts/bd_warehouse_adapter.py:295-296` | 删 `l = float(m.group(2))` + noqa；regex group 2 保留作格式验证器；注释明示 by-design |
| 2 | `fal_enhancer.py:155-180` | 删 `stem` + `exr_exact` 构造 + noqa；重写 `_find_depth_for_png` docstring |

## TDD

每 bug 1 characterization regression test（不是结构断言）→ 验证行为不变。

- `test_bd_warehouse_metric_screw_drops_length_by_design` (Bug 1)
- `test_fal_enhancer_find_depth_via_glob_view_key` (Bug 2)

## Risk audit

R-1~R-6 6 项风险全 brainstorming 阶段缓解。撤回 unnecessary regex non-capturing 改动 + 撤回结构断言 TDD（太脆）。

## AC

- [x] ruff F841 整仓清零（2 处 noqa 已删）
- [x] pytest baseline 不退化（3237 + 2 new = 3239 PASS expected）
- [x] AGENTS.md 不动
- [x] pyproject.toml version 仍 2.24.0
- [ ] CI 8/8 SUCCESS（待 CI 验）

## 关联

- v2.37.12 retro §4 latent bug 详细分析
- §11-N5 follow-up trigger 闭合（fallback ≥5 触发，2 latent bug 经 triage）

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

记 PR # + URL。

### Step 3.4 — CI watcher

- [ ] **`gh pr checks <PR#> --watch`** until all SUCCESS / 任一 FAIL 则 hotfix

---

## Self-Review

### 1. Spec coverage（无 spec doc，按 design 检查）

| Design 要素 | Plan Task | 状态 |
|---|---|---|
| Bug 1 删 `l = float(m.group(2))` | Task 1 Step 1.4 | ✓ |
| Bug 1 不改 regex（撤回 R-1）| Task 1 Step 1.4 (注释明示) | ✓ |
| Bug 1 docstring 引用 catalog line 211 | Task 1 Step 1.4 注释 | ✓ |
| Bug 2 删 exr_exact 块 | Task 2 Step 2.4 | ✓ |
| Bug 2 重写注释为 single-step | Task 2 Step 2.4 docstring | ✓ |
| Characterization TDD (不是结构断言) | Task 1.2 + Task 2.2 | ✓ |
| 每 bug 1 commit | Task 1.6 + Task 2.6 | ✓ |
| 1 PR (#94) | Task 3.3 | ✓ |
| 不动 AGENTS.md / pyproject | (隐含 — Edit 仅作用于明示 file) | ✓ |
| pytest baseline ≥ 3237 (实际 +2) | Task 3.1 | ✓ |

### 2. Placeholder scan

- ✓ 无 "TBD" / "TODO"
- ✓ 每 Edit 步含完整代码 before/after
- ✓ commit message 模板完整
- ✓ 测试代码完整可运行

### 3. Type consistency

- ✓ `_auto_extract_size_from_text(text: str, class_info: dict)` 与 spec 实测一致
- ✓ `_find_depth_for_png(png_path)` 返回 `(path, is_temp)` 元组与 spec 实测一致
- ✓ `monkeypatch.setattr("fal_enhancer.convert_depth_exr_to_png", ...)` 是否能 patch 取决于 fal_enhancer.py 是否 import `convert_depth_exr_to_png` 在模块顶部 — Task 2 实施前再 grep 实证（risk noted）

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-17-v2-37-13a-latent-bug-fix.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - 主 agent 派 fresh subagent per Task + 两阶段 review

**2. Inline Execution** - 主 agent 直接跑（轻量 plan 1-2 commits 适合 inline）

推荐 **Inline** — 这 PR 工作量 ~30-45 min，subagent dispatch overhead 大于 inline，且 plan 已自审清楚。
