# v2.37.3 §12 F1+F2 cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭合 v2.37.2 §12 预登记 2 项 follow-up — F1 抽 `_get_urlopen_request(m)` test helper 消除 2 处 mock 内部解构耦合 + F2 `tools/jury/llm_client.py:105` 注释中间插 1 行实测 rationale；发 v2.37.3 patch tag。

**Architecture:** 极小 pure refactor + 纯注释 PR：F1 在 `tests/jury/test_llm_client.py` 加 module-level helper（放在 `_make_cm` 邻近 line 67 之后）并替换 2 处 inline 解构（line 312 + line 336-337）；F2 仅在 production 文件加 1 行注释，零行为变化。

**Tech Stack:** Python 3.10-3.12 + pytest + ruff + git tag-based release（不 bump 版本文件）。

**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-3-mock-helper-line-rationale-design.md`（190 行 / 2 层审查 inline 修 E1+E2）

**分支：** `feat/v2-37-3-mock-helper-line-rationale`（已建 / HEAD `ecc215a`）

---

## File Structure

| 文件 | 用途 | Canonical / Mirror |
|---|---|---|
| `tests/jury/test_llm_client.py` | 加 `_get_urlopen_request(m: MagicMock)` helper module-level；替换 line ~312 + line ~336-337 两处 `m.call_args[0][0]` 解构 | tests/ 路径，无镜像 |
| `tools/jury/llm_client.py:105-107` | 原 2 行 `# v2.37.2 §11 #6` 注释中间插 1 行实测数据 | **canonical**（`src/cad_spec_gen/data/tools/jury/llm_client.py` 镜像 dev_sync 同步）|
| `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md` §9.3 §11 follow-up 表 | 不动 line 72 / 77（v2.37.2 已 closed）；本 PR 仅在 retro 文档登记 v2.37.3 closed | 仅 docs/ |
| `docs/superpowers/reports/2026-05-14-v2-37-3-mock-helper-line-rationale-retro.md` | retro 文档（新写） | 仅 docs/ |

**不动文件**：`.github/workflows/tests.yml`（CI gate 既存）；`tools/jury/verdict.py`（v2.37.2 已闭合）；任何 schema / config 文件。

---

## Task 0: Scout + baseline 实测

**Files:**
- Read only：`tests/jury/test_llm_client.py` / `tools/jury/llm_client.py` / 跑 baseline pytest

- [ ] **Step 1: 切到 PR 分支并 fetch 验证无并行改动**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git checkout feat/v2-37-3-mock-helper-line-rationale
git log --oneline HEAD..origin/main
```

Expected: `HEAD..origin/main` 为空。

- [ ] **Step 2: 验证 canonical / mirror 守卫**

```bash
git ls-files | grep -E 'jury/llm_client\.py$'
git ls-files -v | grep -E 'jury/llm_client\.py'
```

Expected: `tools/jury/llm_client.py` 在 git tracked，无 `S` skip-worktree 标志。

- [ ] **Step 3: Baseline `dev_sync --check` 干净（spec §9 + v2.37.2 R5 D2 教训）**

```bash
python scripts/dev_sync.py --check
echo "rc=$?"
```

Expected: `rc=0`。若非 0：先 `python scripts/dev_sync.py` 同步 mirror 后再 `--check` 验 0；仍非 0 → abort BLOCKED 给 controller。

- [ ] **Step 4: 实测 baseline PASS 数**

```bash
pytest -q tests/jury/test_llm_client.py 2>&1 | tail -3
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: test_llm_client.py 14 passed（v2.37.2 后）；jury 子集 503 passed。

- [ ] **Step 5: 验证 call site 位置（line shift 防御）**

```bash
grep -n "call_args\[0\]\[0\]" tests/jury/test_llm_client.py
```

Expected: 2 行命中（v2.37.2 后近似 line 312 + line 337）；记录**实际**行号给 Task 1 使用（spec 说 ~312 / ~336-337 是近似）。

- [ ] **Step 6: 验证 helper 插入位置**

```bash
grep -n "^def _make_cm\|^def _mock_response" tests/jury/test_llm_client.py
```

Expected: 2 行命中（v2.37.2 后近似 line 40 + line 61）；新 helper 放在 `_make_cm` 函数 def 之后（一般在 line ~67-68 空行后）。

- [ ] **Step 7: 验证 max_tokens line 位置**

```bash
grep -n "max_tokens" tools/jury/llm_client.py
```

Expected: 1 行命中（v2.37.2 后近似 line 107，注释在 line 105-106）。

- [ ] **Step 8: 记录 baseline 给后续 task 引用**

无 commit；只在 session 记 baseline 数字 + 实际行号。

---

## Task 1: F1 — 抽 `_get_urlopen_request` helper 并替换 2 call site

**Files:**
- Modify: `tests/jury/test_llm_client.py`（加 helper + 改 2 处 call site）

**TDD 模式**：无 RED phase（pure refactor；既有 14 测试就是 GREEN safety net）。

- [ ] **Step 1: 加 module-level helper**

在 `tests/jury/test_llm_client.py` 的 `_make_cm` 函数 def 之后（Task 0 Step 6 实测位置），追加：

```python
def _get_urlopen_request(m: MagicMock) -> object:
    """从 `urlopen` mock 拿到测试发出的 ``urllib.request.Request`` 对象。

    ``patch("tools.jury.llm_client.urlopen")`` 后 ``m.call_args[0][0]`` 是
    被 patch 时存的 Request 实例（mock 框架返回 Any/MagicMock）。
    返回类型不标 ``-> Request`` 避免新增 ``from urllib.request import Request`` import；
    调用方按需访问 ``.get_header(...)`` / ``.data`` / ``.full_url`` 等。

    v2.37.3 §12 F1 抽取：消除 line ~312 + ~337 两处 inline 解构耦合。
    """
    return m.call_args[0][0]
```

注意：返回类型 annotation 写 `-> object` 而非 `-> Request`（spec §3.2 D2 决策——避免新增 import），调用方需要 type 时可 cast。或直接省略 annotation。**实施者按 lint 约定决定**：

- 若 `ruff check` 在 tests/jury/ 强制返回类型 annotation → 用 `-> object` 或 `-> Any`（加 `from typing import Any`）
- 若不强制 → 省略 `-> ...`

实测：先尝试不带 annotation `def _get_urlopen_request(m: MagicMock):`，跑 `ruff check tests/jury/test_llm_client.py` 看是否报错；不报错则保持不带 annotation 最瘦。

- [ ] **Step 2: 替换 line ~312（UA 测试） call site**

定位 `req = m.call_args[0][0]`（Task 0 Step 5 实测行号），改为：

```python
req = _get_urlopen_request(m)
```

下方 `req.get_header("User-agent")` 等代码不动。

- [ ] **Step 3: 替换 line ~336-337（max_tokens 测试） call site**

定位以下 2 行（Task 0 Step 5 实测行号）：

```python
        call_args = m.call_args
        request_obj = call_args[0][0]  # 第 1 个位置参数是 Request
```

替换为 1 行：

```python
        request_obj = _get_urlopen_request(m)
```

下方 `body_bytes: bytes = request_obj.data` 等代码不动。

- [ ] **Step 4: AC-2b strict 验证（spec §4 AC-2b）**

```bash
grep -c "^def _get_urlopen_request" tests/jury/test_llm_client.py
grep -c "_get_urlopen_request(m)" tests/jury/test_llm_client.py
grep -c "m\.call_args\[0\]\[0\]" tests/jury/test_llm_client.py
```

Expected:
- `^def _get_urlopen_request` 计数 **= 1**（恰 1 个 def）
- `_get_urlopen_request(m)` 计数 **≥ 3**（1 def 行 + 2 call site）
- `m.call_args[0][0]` 计数 **= 0**（原 inline 解构全消除）

任何一项不满足 → 回到 Step 1-3 修正。

- [ ] **Step 5: 跑全 test_llm_client.py 验证零行为变化**

```bash
pytest -q tests/jury/test_llm_client.py 2>&1 | tail -3
```

Expected: 14 passed（与 Task 0 baseline 一致；不增不减）。

- [ ] **Step 6: ruff check**

```bash
ruff check tests/jury/test_llm_client.py
```

Expected: All checks passed。

- [ ] **Step 7: REFACTOR 步显式确认**

审视 Step 1 helper：
- 是否过度抽象？→ 1 行 function body 极简 ✓
- Naming 与既有 `_make_cm` / `_mock_response` 风格一致？→ `_X` 前缀 + 动词短语 ✓
- 是否引入新 import？→ 否（`MagicMock` 既有 import）✓
- Commit message 加："REFACTOR: helper 1 行 body 已最瘦，无进一步可清"

- [ ] **Step 8: Commit**

```bash
cd D:/Work/cad-spec-gen
git add tests/jury/test_llm_client.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(test): 抽 _get_urlopen_request helper 消除 mock 内部解构耦合（§12 F1）

v2.37.2 Task 4 code-review 提出：tests/jury/test_llm_client.py 有 2 处
m.call_args[0][0] inline 解构（UA 测试 + max_tokens 测试）耦合到 urllib Request
内部约定；抽 _get_urlopen_request(m) helper 单一化耦合点。

设计决策（spec §3.1 D1 + §3.2 D2）：
- 单 helper 返 m.call_args[0][0]，调用方按需 .get_header / .data
- 不加 -> Request annotation（避免新增 from urllib.request import Request）
- 当前 2 处 call site，预防性 refactor 非 DRY-3+ 触发

AC-2b grep strict 验证（spec §4）：
- ^def _get_urlopen_request == 1
- _get_urlopen_request(m) ≥ 3
- m.call_args[0][0] == 0

Pure refactor 零行为变化；14 既有测试 PASS 不变 = GREEN safety net。

REFACTOR: helper 1 行 body 已最瘦，无进一步可清。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: F2 — `tools/jury/llm_client.py:105` 注释扩 rationale

**Files:**
- Modify: `tools/jury/llm_client.py:105-107`

- [ ] **Step 1: 改 canonical 实现**

定位 `tools/jury/llm_client.py:105-108`（Task 0 Step 7 实测）：

```python
            # v2.37.2 §11 #6：512 → 1024 给 12 features_status + 5 standard check + reason
            # 留响应空间；finish_reason='length' 仍走 needs_review 兜底（不变量 §6 #10）。
            "max_tokens": 1024,
```

中间插 1 行（保现 2 行结构，中间添实测 rationale；spec §3.3 D3）：

```python
            # v2.37.2 §11 #6：512 → 1024 给 12 features_status + 5 standard check + reason
            # 实测 micuapi.ai 长输出 ~800 token；1024 = 2× 余量留未来 12+ features_status 序列化扩展空间。
            # 留响应空间；finish_reason='length' 仍走 needs_review 兜底（不变量 §6 #10）。
            "max_tokens": 1024,
```

- [ ] **Step 2: dev_sync 同步镜像**

```bash
cd D:/Work/cad-spec-gen
python scripts/dev_sync.py
git status --short
python scripts/dev_sync.py --check
```

Expected: `tools/jury/llm_client.py` modified（mirror 自动同步 gitignored）；`--check` rc=0。

- [ ] **Step 3: 跑回归确认零行为变化（注释改不影响测试）**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 503 passed / 6 skipped（与 Task 0 / Task 1 后基线一致）。

- [ ] **Step 4: ruff check**

```bash
ruff check tools/jury/llm_client.py
```

Expected: All checks passed。

- [ ] **Step 5: REFACTOR 步显式确认**

审视 Step 1 注释：
- 实测数据 ~800 token + 2× 余量 在注释中 ✓
- "12+ features_status 扩展空间" 给未来扩 max_tokens 留判断依据 ✓
- 总 3 行注释仍 < 100 col ✓
- Commit message 加："REFACTOR: 注释扩 1 行实测 rationale，无其它冗余"

- [ ] **Step 6: Commit**

```bash
git add tools/jury/llm_client.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(jury): max_tokens 1024 line 注释加实测 rationale（§12 F2）

v2.37.2 Task 4 code-review 提出：tools/jury/llm_client.py:105-107 现 2 行注释
只引 spec §11 #6 + §6 #10 不说"为什么 1024 而非其它值"；插 1 行实测数据
（"micuapi.ai ~800 token / 2× 余量"）减少 git blame 跳转。

设计决策（spec §3.3 D3）：
- 保现 2 行结构 + 中间插 1 行实测数据
- 总 3 行注释，< 100 col，可读性保留

零行为变化（仅注释）。

REFACTOR: 注释扩 1 行实测 rationale，无其它冗余。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: STATUS 文档 + retro 写

**Files:**
- Create: `docs/superpowers/reports/2026-05-14-v2-37-3-mock-helper-line-rationale-retro.md`

**STATUS doc 不动**：v2.37.2 已在 line 72 / 77 标 closed；本 PR 只在 retro 文档登记 v2.37.3。

- [ ] **Step 1: 写 retro 文档**

新建 `docs/superpowers/reports/2026-05-14-v2-37-3-mock-helper-line-rationale-retro.md`：

```markdown
# Retro — v2.37.3 §12 F1+F2 cleanup

**完工日期：** 2026-05-14
**PR：** #N（占位，merge 后回填）
**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-3-mock-helper-line-rationale-design.md`（190 行 / 2 层审查 inline 修 E1+E2）
**Plan：** `docs/superpowers/plans/2026-05-14-v2-37-3-mock-helper-line-rationale.md`
**Baseline：** main@`82ecd7a`（v2.37.2 merge）→ merge@<sha>（占位回填）

## 一句话

v2.37.2 §12 预登记 2 项 follow-up（F1 抽 `_get_urlopen_request` mock helper + F2 `max_tokens` line 注释加实测 rationale）；pure refactor + 纯注释 PR，零行为变化。

## 完工范围

- §12 F1 closed：`_get_urlopen_request(m)` helper 抽取，消除 `m.call_args[0][0]` 2 处 inline 解构耦合
- §12 F2 closed：`tools/jury/llm_client.py:105` 注释中间插 1 行实测 ~800 token / 2× 余量 rationale

## 数字

- jury 子集 PASS：503 → 503（pure refactor 不增不减 + 注释零影响）
- 全套件 PASS：3193 → 3193 / 17 skipped / 0 regression
- diff stat：~25 行代码 + ~80 行 retro 文档
- 3 commits（refactor + docs + retro）
- CI 8/8 SUCCESS（待 PR 后实测）

## 2 层 + brainstorming 漂移修审查统计

| Layer | findings | inline 修 |
|---|---|---|
| brainstorming F1+F2 漂移 fix | 2 | 2 |
| layer 6 边界 + 闭环 | 7 | 2（E1+E2）/ 5 接受（描述精度）|
| **总** | **9** | **4** |

## 沉淀 lessons

- **brainstorming 阶段 spec 漂移**：v2.37.2 retro 已沉淀「writing-plans 入口 scout grep 必跑」；本 PR brainstorming 写 spec 时再踩一次（spec §12 vs STATUS §9.3 §11 表混淆）—— 主 agent 自审节段需固化 grep 验证 spec 假设
- **AC strict 验证升级**：spec §4 AC-2b 把 review 找的 "AC 不够 strict" finding 转化为可机器执行的 grep 断言（`grep -c "^def _get_urlopen_request" == 1`），plan task 实施时直接跑当 acceptance 检查
- **Plan 必 cover 项的 spec 化**：v2.37.2 baseline dirty abort（R5 D2）从 plan 阶段 hidden lesson 升级到 spec §9 plan 必 cover 显式列项—— 跨 PR 教训复用机制

## §12 follow-up 残留（不阻断 v2.37.3）

v2.37.2 spec §12 预登记 6 项 layer 5 五角色还在等独立 PR：f1（max_tokens sunset）/ f2（memory inline 摘要）/ f3（spec mini-glossary）/ f4（N≥50 批量成本）/ f5（user-visible 6-key 注释）/ f6（jury_config schema 不变声明）。

## 下次类似 PR 优化

- brainstorming 写 spec 时 grep 验证 doc 章节存在性（避免 §12 vs §9.3 §11 误拏）
- pure refactor PR 的 AC 必含 grep strict 验证（不只"既有测试 PASS 不变"间接证明）
- super 小 PR（25 行 diff）的 spec 适度，185 行 spec/diff ~7:1 比例临界 — 接受 OR 缩简

[[project-v2-37-2-done]] 上游 §12 F1+F2 由本 PR 闭合。
```

- [ ] **Step 2: 跑元测试**

```bash
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: 全 PASS。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/reports/2026-05-14-v2-37-3-mock-helper-line-rationale-retro.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(v2-37-3): retro 沉淀 — §12 F1+F2 closed + 2 层审查 lesson

闭合 v2.37.2 §12 预登记 F1 (mock helper) + F2 (line rationale) 两项；
retro 沉淀 brainstorming spec 漂移修 + layer 6 边界审查 lesson。

PR # 占位字段在 squash merge 后回填。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: PR 全流程

**Files:** 无文件改动；纯 git / GitHub 操作。

按 v2.37.2 模板拆 2 阶段：4a 是 push + open PR + 等 CI（可自动）；4b 是 merge + tag + Release（需用户授权）。

### Task 4a: Push + 开 PR + 等 CI

- [ ] **Step 1: PR push 前并行改动验证**

```bash
git fetch origin main
git log --oneline HEAD..origin/main
```

Expected: 空。

- [ ] **Step 2: Push 分支**

```bash
git push origin feat/v2-37-3-mock-helper-line-rationale
```

- [ ] **Step 3: 开 PR**

```bash
gh pr create --title "refactor(jury): v2.37 §12 F1+F2 cleanup（v2.37.3）" --body "$(cat <<'EOF'
## 概要

闭合 v2.37.2 §12 预登记 2 项 follow-up：

- **§12 F1**：抽 `_get_urlopen_request(m)` test helper 消除 `tests/jury/test_llm_client.py` 2 处 `m.call_args[0][0]` inline 解构耦合
- **§12 F2**：`tools/jury/llm_client.py:105` 注释中间插 1 行实测 rationale（"micuapi.ai ~800 token / 2× 余量"）

## 改动

- `tests/jury/test_llm_client.py` 加 `_get_urlopen_request` helper + 替换 2 call site
- `tools/jury/llm_client.py` 1 行注释插入
- retro 文档新写

**0 schema / 0 env-config / 0 production logic / 0 behavior** —— pure refactor + 纯注释。

## 测试

- jury 子集：503 PASS 不变（refactor 不增减测试）
- 全套件：3193 PASS / 0 regression

## 审查层数

brainstorming (F1+F2 漂移修) + layer 6 边界审查 (E1+E2 inline 修) = 9 findings 总，4 inline 修。

## Spec / Plan / Retro

- Spec: `docs/superpowers/specs/2026-05-14-v2-37-3-mock-helper-line-rationale-design.md`
- Plan: `docs/superpowers/plans/2026-05-14-v2-37-3-mock-helper-line-rationale.md`
- Retro: `docs/superpowers/reports/2026-05-14-v2-37-3-mock-helper-line-rationale-retro.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: 等 CI 8/8 全绿**

```bash
gh pr checks --watch
```

Expected: 8/8 SUCCESS。Transient flake 容忍 = 连续 2 次同 failure signature 才视为 regression。

### Task 4b: Merge + Tag + Release（需用户授权后另行 dispatch）

- [ ] **Step 5-10**：见 v2.37.2 Plan Task 7 步骤 5-10 同模板（squash merge → 等 main CI 全绿 → tag v2.37.2 → Release create → 写 memory）。

发 GitHub Release 时 notes 模板复用 v2.37.2 升级路径段（git+https / Release zip / 本地 dev）。

写完后写 memory `project_v2_37_3_done.md` + 加 MEMORY.md 索引。

---

## Self-Review

**1. Spec coverage**:

| Spec 章节 | Plan Task | 备注 |
|---|---|---|
| §2.1 改动表 row 1 (test_llm_client.py) | Task 1 全 | ✓ |
| §2.1 改动表 row 2 (llm_client.py:105) | Task 2 全 | ✓ |
| §2.1 改动表 row 3 (STATUS doc 不动) | Task 3 注明不动 | ✓ |
| §2.1 改动表 row 4 (retro 新写) | Task 3 Step 1 | ✓ |
| §3 D1-D4 决策 | Task 1 (D1/D2/D4) / Task 2 (D3) / Task 1 (D4 no-RED) | ✓ |
| §4 AC-1..7 | Task 1 Step 5 (AC-1) / Task 1 Step 4 (AC-2/2b) / Task 1-2 Step 6 (AC-3) / Task 2 Step 1 (AC-4) / Task 1 Step 5 + Task 2 Step 3 (AC-5) / Task 4 Step 4 (AC-6) / Task 4b (AC-7) | ✓ |
| §6 不变量 #1-7 | Task 1-3 全程维持（不动 verdict.py / 不加 env / dev_sync 同步 / 不动 CI） | ✓ |
| §7 流程 + 3 commit 拆分 | Task 1 + Task 2 + Task 3 三 commit | ✓ |
| §8 6 调查步 | Task 0 全覆盖 | ✓ |
| §9 plan 必 cover | Task 0 Step 3 (baseline dirty abort) + Task 1-2 Step 2 (dev_sync git status) + Task 4a Step 1 (git fetch verify) | ✓ |
| §10 不写代码事项 | 全 task 不做（不二分 helper / 不加 annotation / 不动 line 296） | ✓ |
| §11 §12 表 | Task 3 retro 中已注 closed v2.37.3 | ✓ |
| §12 本 PR follow-up (g1 命名风格统一度) | Task 1 Step 7 REFACTOR 步显式审视 + 接受 | ✓ |

**所有 spec 章节有 task 覆盖。**

**2. Placeholder scan**: 无 TBD / TODO / "implement later"。PR # 在 Task 3 retro + Task 4 Release notes 标"待 merge 后回填"是显式留白模式（v2.37.2 实证）。

**3. Type consistency**: Helper signature `_get_urlopen_request(m: MagicMock)` 在 Task 1 各 step 一致；返回类型 annotation 在 Task 1 Step 1 显式说明"不加 `-> Request` annotation"在 Task 1 Step 7 REFACTOR 确认 ✓

**4. 跨 task 引用一致性**: Task 0 实测的 baseline 数字 / 行号在 Task 1+2 步骤注明"近似行号"+ 引用 Task 0 实测结果 ✓

**Plan 自检无问题 → ready for handoff。**

---

## 执行方式选择

Plan 完成保存到 `docs/superpowers/plans/2026-05-14-v2-37-3-mock-helper-line-rationale.md`。两种执行模式：

1. **Subagent-Driven（推荐）** — 主 agent 每 task 派发 fresh subagent，两阶段 review；v2.37.2 实证模板可复用
2. **Inline 执行** — 主 agent 本 session 直接跑全部 task，checkpoint 暂停让用户审；scope 极小可考虑

按 v2.37.2 实证（11 PR 连续一次过 CI），建议 **Subagent-Driven**。
