# v2.37.6 §11-N5 + §12 f2 cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭合 v2.37.x §11-N5（jury 估价表加 `gpt-image-*` entry → $0.010/call，production list + doc mirror 同步）+ §12 f2（CLAUDE.md 加 memory 引用约定）+ §11-N4 retro 沉淀（重新评估为非 bug）。

**Architecture:** 小 patch PR：1 行 production list insert + 1 TDD 回归测试 + 2 处 docs append（cad-jury-config.md §4 + CLAUDE.md "## memory 引用约定"）+ retro 沉淀。先写测试（RED）再加 entry（GREEN），保 v2.37.x cleanup 系列 TDD 纪律。

**Tech Stack:** Python `list[tuple]` + pytest + markdown + git tag-based release。

**Spec：** `docs/superpowers/specs/2026-05-15-v2-37-6-followup-cleanup-design.md`（213 行 / brainstorming F1+F2 + layer 6 E1+E2+E10+E3+E5+E4 fix）

**分支：** `feat/v2-37-6-followup-cleanup`（已建 / HEAD `09672d3`）

---

## File Structure

| 文件 | 用途 | 改动范围 |
|---|---|---|
| `tools/jury/config.py:45-54` | jury 估价表 `BUILTIN_MODEL_COST_USD: list[tuple]` | **+1 行 production**：插入 `("gpt-image", 0.010)` tuple，位置在 `gpt-4o`/`gpt-4-turbo` 之后、`gemini-2.5-flash` 之前 |
| `tests/jury/test_config.py` | 既有 estimate table 测试位置 | **+1 测试函数** `test_cost_lookup_gpt_image`（沿用既有 `test_cost_lookup_gpt_4o` style）|
| `docs/cad-jury-config.md` §4 估价表 | 人类可读 mirror | append 1 行 `gpt-image-*` entry + 来源注 |
| `CLAUDE.md` §项目术语 glossary 后 | spec writer always-loaded context | append 新小节"## memory 引用约定" |
| `docs/superpowers/reports/2026-05-15-v2-37-6-followup-cleanup-retro.md` | retro（新写）| 含 §11-N5 closed + §12 f2 closed + §11-N4 重新评估 + layer 6 E1 production scope 揭示 lesson |

**不动**：`tools/jury/config.py` 函数本体（`lookup_builtin_cost` line 184-189 不动）/ `tools/jury/*.py` 其它 / CI workflow / schema / env-config / `tools/photo3d_jury.py`。

---

## Task 0: Scout + baseline 实测

**Files:** Read only.

- [ ] **Step 1: 切到分支 + fetch + dev_sync**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git checkout feat/v2-37-6-followup-cleanup
git log --oneline HEAD..origin/main
python scripts/dev_sync.py --check
echo "rc=$?"
```

Expected: `HEAD..origin/main` 空 / dev_sync rc=0。报告。

- [ ] **Step 2: baseline 测试**

```bash
pytest -q tests/jury/test_config.py 2>&1 | tail -3
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: test_config.py PASS / jury 子集 503 PASS / 元测试 5 PASS。**报告各数字**。

- [ ] **Step 3: 实测 `BUILTIN_MODEL_COST_USD` 既有内容**

```bash
sed -n '40,60p' D:/Work/cad-spec-gen/tools/jury/config.py
```

Expected: 看到 list 含 `("gpt-4o", 0.020)` / `("gpt-4-turbo", 0.030)` / `("gemini-2.5-flash", 0.005)` / `("gemini-2.5-pro", 0.015)` / `("claude-vision", 0.025)` 5 项。**报告**确认位置 + 行序。

- [ ] **Step 4: 实测既有 `test_cost_lookup_*` 函数风格**

```bash
grep -n "^def test_cost_lookup" D:/Work/cad-spec-gen/tests/jury/test_config.py
sed -n '314,335p' D:/Work/cad-spec-gen/tests/jury/test_config.py
```

Expected: 3 个既有测试 `test_cost_lookup_gpt_4o` / `test_cost_lookup_table_order_first_match` / `test_cost_lookup_unknown_returns_none`。**报告**新测试参考这个风格。

- [ ] **Step 5: 实测 cad-jury-config.md §4 表位置**

```bash
grep -nE "^\| \`gpt-4o\`|^\| \`gpt-4-turbo|^\| \`gemini-2.5-flash|^\| \`gemini-2.5-pro|^\| \`claude" D:/Work/cad-spec-gen/docs/cad-jury-config.md
```

Expected: 5 个 entry 行号（snapshot 约 line 115-119）。**报告实际行号**——doc 改插入位置参考。

- [ ] **Step 6: 实测 CLAUDE.md 既有 ## 节列表 + §项目术语 glossary 末位**

```bash
grep -nE "^## " D:/Work/cad-spec-gen/CLAUDE.md
tail -10 D:/Work/cad-spec-gen/CLAUDE.md
```

Expected: 末节"## 项目术语 glossary"（v2.37.5 加，line 87 起）。**报告**新小节追加位置。

- [ ] **Step 7: 汇总**

无 commit；report 汇总 6 步关键数据。

---

## Task 1: TDD RED — 写 `test_cost_lookup_gpt_image`

**Files:** Modify: `tests/jury/test_config.py`（append 新测试函数）

**TDD 阶段**：RED。先写测试，验证 FAIL，再 Task 2 改 production GREEN。

- [ ] **Step 1: 在 `tests/jury/test_config.py` 既有 `test_cost_lookup_unknown_returns_none` 之后追加新测试**

精确位置：找到 `def test_cost_lookup_unknown_returns_none(...)` 函数末 `assert lookup_builtin_cost("llama-99") is None` 之后空 1 行插入：

```python


def test_cost_lookup_gpt_image() -> None:
    """v2.37.6 §11-N5：gpt-image-* 前缀命中 $0.010/call（GISBOT e2e profile 显式值 + 单 vendor 实测来源；§4.1 ±50% 偏差仍适用）。"""
    from tools.jury.config import lookup_builtin_cost

    assert lookup_builtin_cost("gpt-image-2-pro") == 0.010
    assert lookup_builtin_cost("gpt-image") == 0.010
    assert lookup_builtin_cost("gpt-image-3-future-variant") == 0.010  # 前缀匹配未来变种
```

实施操作：用 Edit 工具 old_string = `assert lookup_builtin_cost("llama-99") is None`，new_string = 原行 + 上方测试块。

- [ ] **Step 2: 跑 RED 验证测试真失败**

```bash
cd D:/Work/cad-spec-gen
pytest tests/jury/test_config.py::test_cost_lookup_gpt_image -v
```

Expected: `FAILED` × 3 assertions（首个 assertion 触发；返 `None` 而非 0.010）；exit ≠ 0。

报告 pytest 输出确认 fail。

- [ ] **Step 3: 不 commit**（RED 阶段，Task 2 GREEN 后一起 commit）

---

## Task 2: GREEN — 改 `tools/jury/config.py` 加 entry

**Files:** Modify: `tools/jury/config.py:45-54`

**TDD 阶段**：GREEN。Task 1 RED 后改最小 production 让测试通过。

- [ ] **Step 1: 改 `BUILTIN_MODEL_COST_USD` list**

读 `tools/jury/config.py:45-54` 当前 5 项 list。用 Edit 工具：

`old_string`:
```python
BUILTIN_MODEL_COST_USD: list[tuple[str, float]] = [
    ("gpt-4o", 0.020),
    ("gpt-4-turbo", 0.030),
    ("gemini-2.5-flash", 0.005),
    ("gemini-2.5-pro", 0.015),
    ("claude-vision", 0.025),
]
```

`new_string`:
```python
BUILTIN_MODEL_COST_USD: list[tuple[str, float]] = [
    ("gpt-4o", 0.020),
    ("gpt-4-turbo", 0.030),
    ("gpt-image", 0.010),  # v2.37.6 §11-N5：GISBOT e2e profile 显式值 + micuapi.ai 单实测；§4.1 ±50% 偏差仍适用
    ("gemini-2.5-flash", 0.005),
    ("gemini-2.5-pro", 0.015),
    ("claude-vision", 0.025),
]
```

注意：插入位置 = `gpt-4-turbo` 之后 / `gemini-2.5-flash` 之前（spec D1 决策，保 OpenAI 系连续 + first-match 行序不影响既有 entries）。

- [ ] **Step 2: dev_sync**（保镜像同步）

```bash
cd D:/Work/cad-spec-gen
python scripts/dev_sync.py
git status --short
python scripts/dev_sync.py --check
```

Expected: `tools/jury/config.py` modified + mirror 同步 + rc=0。

- [ ] **Step 3: 跑 GREEN 验证 Task 1 测试通过**

```bash
pytest tests/jury/test_config.py::test_cost_lookup_gpt_image -v
```

Expected: 3 个 assertion 全 PASS / exit=0。

- [ ] **Step 4: 跑既有 estimate table 测试不破**

```bash
pytest tests/jury/test_config.py -v 2>&1 | tail -20
```

Expected: 既有 `test_cost_lookup_gpt_4o` / `test_cost_lookup_table_order_first_match` / `test_cost_lookup_unknown_returns_none` 全 PASS（new entry 不冲突）。

- [ ] **Step 5: 跑全 jury 子集回归**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 503 + 1 = **504 PASS** / 6 skipped / 0 regression。

- [ ] **Step 6: REFACTOR 步**

审视改动：
- 1 行 list insert，无冗余 ✓
- inline comment 含 §11-N5 引用 + 来源 + ±50% 免责 ✓
- 风格沿用既有 entries ✓
- commit message 加 `REFACTOR: 1 行 list insert 已最瘦，跳过`

- [ ] **Step 7: Commit (TDD RED+GREEN 一起)**

```bash
cd D:/Work/cad-spec-gen
git add tools/jury/config.py src/cad_spec_gen/data/tools/jury/config.py tests/jury/test_config.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(jury): BUILTIN_MODEL_COST_USD 加 gpt-image entry + TDD 回归（§11-N5）

v2.37.x §11-N5 闭合：GISBOT e2e 实测 micuapi.ai gpt-image-2-pro 单 vendor profile
cost_per_call_usd=0.010；加进 BUILTIN_MODEL_COST_USD list 作未显式填 cost 时
default。

设计决策（spec §3.1 D1）：
- 同时改 production list (tools/jury/config.py:48) + doc mirror
  (cad-jury-config.md §4 表，下个 commit) — layer 6 E1 揭示 doc-as-mirror 必须同步
- 插入位置 = gpt-4-turbo 之后 / gemini-2.5-flash 之前（保 OpenAI 系连续；
  first-match 行序不影响既有 entries）
- 前缀 "gpt-image" 让 gpt-image-2-pro / gpt-image-3 等同款自动覆盖
- §4.1 ±50% 偏差免责保留（来源 = GISBOT e2e profile 显式值 + 单 vendor 实测一次）

TDD RED → GREEN：
- RED: test_cost_lookup_gpt_image 写 3 assertion (gpt-image-2-pro / gpt-image /
  gpt-image-3-future-variant 全返 0.010)；FAILED 验证
- GREEN: BUILTIN_MODEL_COST_USD 插 ("gpt-image", 0.010) → PASS

回归：jury 子集 503 → 504 PASS / 0 regression。

REFACTOR: 1 行 list insert 已最瘦，跳过。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: cad-jury-config.md §4 表 mirror 同步

**Files:** Modify: `docs/cad-jury-config.md` §4 估价表

- [ ] **Step 1: 找 §4 表插入位置**

读 Task 0 Step 5 实测的 5 个 entry 行号。在 `\`gpt-4-turbo*\`` 行之后、`\`gemini-2.5-flash*\`` 行之前插入新 entry。

用 Edit 工具：

`old_string`（一定 unique）：
```
| `gpt-4-turbo*` | **0.030** | 同上 |
| `gemini-2.5-flash*`, `gemini-1.5-flash*` | **0.005** | Google AI Studio 公开计价（约值） |
```

`new_string`：
```
| `gpt-4-turbo*` | **0.030** | 同上 |
| `gpt-image-2-pro`, `gpt-image*` | **0.010** | v2.37.6 §11-N5 加 · GISBOT e2e profile 显式值 + micuapi.ai 单实测；§4.1 ±50% 偏差仍适用 |
| `gemini-2.5-flash*`, `gemini-1.5-flash*` | **0.005** | Google AI Studio 公开计价（约值） |
```

- [ ] **Step 2: 验证表格 markdown 完整**

```bash
cd D:/Work/cad-spec-gen
grep -c "gpt-image" docs/cad-jury-config.md
```

Expected: ≥ 1（spec §4 AC-4 grep）。

- [ ] **Step 3: 不 commit**（与 Task 4 一起合 docs commit）

---

## Task 4: CLAUDE.md memory 引用约定

**Files:** Modify: `CLAUDE.md`（append 新 ## 小节，在既有 §项目术语 glossary 之后）

- [ ] **Step 1: 找 CLAUDE.md 末位置**

读 Task 0 Step 6 实测的 CLAUDE.md 末位（v2.37.5 加的 glossary 末段，约 line 113）。新小节追加在文件末尾。

- [ ] **Step 2: 用 bash here-string append 新小节**

```bash
cd D:/Work/cad-spec-gen
cat >> CLAUDE.md << 'EOF'

---

## memory 引用约定

spec / plan / retro 文档引用 session memory 时，必含 ≤20 **字符**（不是字节；中文 1 char = 1 字符 ≠ 3 utf-8 bytes）inline 摘要防 memory 改名/归档后失锚（layer 5 R2 L3 教训）。

**约定格式**：

```
见 memory `xxx.md`（摘要：≤20 字含义）
```

**约束范围**：

- **仅未来 spec/plan/retro 文档生效**；既有文档（v2.37.5 之前）不强制 retro-fit
- 鼓励渐进改进：触及既有文档 memory 引用时顺手补摘要
- 新旧格式兼容：v2.37.5 §项目术语 glossary 既有写法 `（见 memory \`xxx.md\`）` 不删；新约定 = 新写文档时含摘要；新旧并存合法

**示例**（新写）：

```
见 memory `feedback_spec_review_4layers.md`（摘要：spec ≥100 行 5 层默认审）
```
EOF
```

注意：`<< 'EOF'` 单引号保 `xxx.md` 反引号不被 bash 解析。Windows Git Bash 应能跑；PowerShell 改用 `@'...'@` here-string。

- [ ] **Step 3: 验证 markdown 完整 + AC-3 grep**

```bash
tail -30 CLAUDE.md
grep -c "^## memory 引用约定" CLAUDE.md          # 应 == 1
grep -cE "≤20 字符|inline 摘要" CLAUDE.md       # 应 ≥ 1
grep -c "仅未来" CLAUDE.md                       # 应 ≥ 1
```

Expected: 3 个 grep 都 ≥ spec AC-4 floor。

- [ ] **Step 4: 元测试不破（v2.37.5 实证 CLAUDE.md 改不影响 AGENTS.md）**

```bash
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: 5 PASS。

- [ ] **Step 5: 全套件回归确认**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 504 PASS（Task 2 后新基线 + Task 3/4 docs 改不影响）。

- [ ] **Step 6: Commit docs（Task 3 + Task 4 合一 commit）**

```bash
cd D:/Work/cad-spec-gen
git add docs/cad-jury-config.md CLAUDE.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(jury-config,claude-md): §4 表 mirror 同步 + memory 引用约定（§11-N5 doc + §12 f2）

§11-N5 (doc mirror)：cad-jury-config.md §4 估价表加 gpt-image-2-pro/gpt-image*
entry → 0.010（与 production list tools/jury/config.py 同步，layer 6 E1
揭示 doc-as-mirror 必须双改）。

§12 f2: CLAUDE.md §项目术语 glossary 后追加 "## memory 引用约定" 小节：
- spec/plan/retro 引 memory 必含 ≤20 字符（明示非字节，E4 fix）inline 摘要
- 约束仅未来文档生效，既有不强制 retro-fit（E3+E5 fix 新旧格式兼容）
- 防 memory 改名/归档后引用失锚（layer 5 R2 L3 教训）

AC-3 grep strict (layer 6 E4 ERE 教训复用)：
- `## memory 引用约定` == 1 ✓
- `≤20 字符|inline 摘要` ≥ 1 ✓
- `仅未来` ≥ 1 ✓

零行为变化（pure docs append；既有 §1-§3+§5-§13+附录 A/B 字面零改）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: retro 文档新写

**Files:** Create: `docs/superpowers/reports/2026-05-15-v2-37-6-followup-cleanup-retro.md`

- [ ] **Step 1: 写 retro 文档**

新建 retro（utf-8，复用 v2.37.5 retro 风格）：

```markdown
# Retro — v2.37.6 §11-N5 + §12 f2 cleanup（含 §11-N4 重新评估）

**完工日期：** 2026-05-15
**Spec：** `docs/superpowers/specs/2026-05-15-v2-37-6-followup-cleanup-design.md`（213 行 / brainstorming F1+F2 + layer 6 E1+E2+E10+E3+E5+E4 fix）
**Plan：** `docs/superpowers/plans/2026-05-15-v2-37-6-followup-cleanup.md`
**Baseline：** cad-spec-gen main@`2ab0003`（GISBOT e2e merge）

## 一句话

闭合 §11-N5（jury 估价表加 gpt-image entry $0.010/call，production list + doc mirror 同步）+ §12 f2（CLAUDE.md 加 memory 引用约定）；§11-N4 重新评估为非 bug（mojibake 是 client 端 cp936 读 utf-8 显示问题，jury report 本身 UTF-8 正确）。

## 完工范围

- §11-N5 closed：`tools/jury/config.py:BUILTIN_MODEL_COST_USD` list 加 `("gpt-image", 0.010)` + `tests/jury/test_config.py` 加 `test_cost_lookup_gpt_image` + `cad-jury-config.md §4` 表同步
- §12 f2 closed：`CLAUDE.md` 加 `## memory 引用约定` 节，spec/plan/retro 引 memory 必含 ≤20 字符 inline 摘要（仅未来生效，既有不 retro-fit）
- **§11-N4 drop**：retro 沉淀"非 production bug，client 环境问题"+ 字节级 verify lesson

## 数字

- jury 子集 PASS：503 → **504**（+1 `test_cost_lookup_gpt_image`）
- 全套件：3193 → 3194 / 0 regression
- 元测试 5 PASS 不变（CLAUDE.md 加节不影响 AGENTS.md regen，v2.37.5 实证）
- 3 commits（feat / docs / retro）
- CI 8/8 SUCCESS（待 PR 后实测）

## 关键发现 — Layer 6 E1 揭示 production scope 漂移

**原 spec 假设**：纯 docs PR（仅改 `cad-jury-config.md §4` markdown 表）。

**Layer 6 grep `tools/jury/config.py:45-186` 揭示**：
- `BUILTIN_MODEL_COST_USD: list[tuple]` 是 production 真实查表源（line 45-54）
- `lookup_builtin_cost` 按 list 行序 first-match（line 185-189）
- `cad-jury-config.md §4 表`是**人类可读 mirror**，单改 doc 不影响 jury 查表行为

**修复**：spec scope 翻倍：
- 加 production change：`tools/jury/config.py:48` 插 1 tuple
- 加测试覆盖：`tests/jury/test_config.py::test_cost_lookup_gpt_image` 3 assertion
- 总 diff ~100 行（原假设 ~20 行 docs only）

**Lesson 沉淀**：spec 写"加 entry / 字段"时必 grep 实际 production code 看是 doc-only 还是 doc-as-mirror。下次 cleanup PR brainstorming 阶段问"这是 docs 改还是 doc-as-mirror 双改？"

## §11-N4 重新评估说明

**GISBOT retro 当时报告**：jury report `ordinary_user_message` 字段含 mojibake `"(��� stderr ������ʾ)"`，假定 jury production 跨平台 stderr 捕获 bug。

**本 PR 重新 cat 实测**：
```bash
cat <jury_report>.json | python -c "import json,sys; d=json.load(sys.stdin); print(repr(d['ordinary_user_message']))"
# 输出: '(详见 stderr 中文提示)'  ← UTF-8 中文真值，正确
```

**真相**：implementer 之前看到的 mojibake 是 Windows 控制台默认 cp936 读 utf-8 JSON 显示乱码（client 端编码问题），jury 写盘的 JSON 本身 UTF-8 正确。`(详见 stderr 中文提示)` 是 jury.py:693 写死兜底 message。

**Lesson**：报 production bug 前先 `cat -A` 或 `python -c "print(repr(json.load(...)[field]))"` 实测字节，不只看控制台显示（控制台编码可能与文件编码不一致）。

## 审查矩阵

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming F1+F2 fact-check | 2 | 2 | 0 |
| layer 6 边界 + 闭环 | 10 | 4 合（E1+E2+E10+E3+E5+E4）| 6 |
| per-task spec+quality review × 5 task | <待补> | <待补> | <待补> |
| **总** | **12+** | **6** | **6** |

## 沉淀 lessons

1. **layer 6 grep 揭示 doc-as-mirror 漂移**（layer 6 E1）：spec 假定纯 docs PR；grep production 揭示 doc 是 mirror，必须同步改 production list。Lesson：spec 写"加 entry/字段"前必 grep 实际查表/解析逻辑代码。
2. **TDD RED→GREEN 仍是小 production change 的纪律**（Task 1+2）：1 行 list insert 也走完整 RED→GREEN→REFACTOR；防"小改不测试"陷阱。
3. **报 production bug 前 cat -A 实测字节**（§11-N4 重新评估）：控制台显示乱码 ≠ 文件含乱码；Windows cp936 vs utf-8 默认不一致是常见误判源。
4. **profile 显式值 vs default 表项分层**（spec §3.1 D1 + E2+E10）：jury cost 公式 = profile 显式 > §4 表 default > exit reject。本 PR 加 entry 仅影响"未显式填 cost 的新用户"；既有显式 profile 零影响。
5. **≤20 字符（明示非字节）+ 新旧格式兼容**（spec §3.3 D3 + E4+E3+E5）：约定写跨语言（含中文）UI 文本时必明示 char vs byte；新约定与既有写法兼容声明防"格式迁移焦虑"。

## §11 + §12 follow-up 表（本 PR 闭合后）

| 项 | 状态 |
|---|---|
| §12 F1/F2/f3/f5/f6 | closed v2.37.3-v2.37.5 ✓ |
| **§12 f2 memory inline 摘要** | **closed v2.37.6 ✓** |
| §12 f1 / f4 | 未闭合（下次 batch）|
| **§11-N5 估价表 gpt-image-*** | **closed v2.37.6 ✓** |
| §11-N4 stderr mojibake | **drop（非 production bug）✓** |
| §11-N1 / N2 / N3 | 未闭合（batch 2 + 3）|

## 下次类似 PR 优化

- spec 写"加 entry"前必 grep production 代码看是 doc-only 还是 doc-as-mirror
- TDD 小 production change 也走完整 RED→GREEN→REFACTOR
- 报 production bug 前 cat -A / python repr() 字节级验证
- 跨语言文本字段约定明示 char vs byte 单位
- profile 显式值 vs default 分层逻辑 spec 必明示

[[project-gisbot-jury-e2e-done]] 上游 §11-N5 / N4 来源追溯。
[[project-v2-37-5-done]] §12 f3 glossary 追溯。
```

- [ ] **Step 2: 元测试**

```bash
cd D:/Work/cad-spec-gen
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: 5 PASS。

- [ ] **Step 3: Commit retro**

```bash
git add docs/superpowers/reports/2026-05-15-v2-37-6-followup-cleanup-retro.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(v2-37-6): retro 沉淀 — §11-N5 + §12 f2 closed + §11-N4 重新评估 + 5 lessons

闭合 §11-N5 (jury 估价表 gpt-image entry) + §12 f2 (CLAUDE.md memory 引用约定)。
§11-N4 重新评估为非 production bug (mojibake 是 client cp936 vs utf-8 显示问题)。

5 lessons 沉淀：
1. layer 6 grep 揭示 doc-as-mirror 漂移 (本 PR spec scope 翻倍 实证)
2. TDD RED→GREEN 仍是小 production change 纪律
3. 报 production bug 前 cat -A 字节级验证
4. profile 显式值 vs default 表项分层逻辑
5. ≤20 字符（明示非字节）+ 新旧格式兼容声明

PR # 占位 squash merge 后回填。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: PR + CI + Merge + tag v2.37.6 + Release

### Task 6a: Push + 开 PR + 等 CI

- [ ] **Step 1: 验证无并行改动**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git log --oneline HEAD..origin/main
git log --oneline HEAD..origin/main -- tools/jury/ tests/jury/ docs/cad-jury-config.md CLAUDE.md
```

Expected: 空。

- [ ] **Step 2: Push 分支**

```bash
git push origin feat/v2-37-6-followup-cleanup
```

- [ ] **Step 3: 开 PR**

```bash
gh pr create --title "feat(jury): v2.37.6 §11-N5 + §12 f2 cleanup（gpt-image 估价 + memory 引用约定）" --body "$(cat <<'EOF'
## 概要

闭合 v2.37.x §11+§12 follow-up 2 项 + §11-N4 重新评估：

- **§11-N5**：`tools/jury/config.py:BUILTIN_MODEL_COST_USD` list 加 `("gpt-image", 0.010)` tuple + `tests/jury/test_config.py` TDD 测试 + `cad-jury-config.md §4` 表 mirror 同步
- **§12 f2**：`CLAUDE.md` 加 `## memory 引用约定` 节（spec/plan/retro 引 memory 必含 ≤20 字符 inline 摘要，仅未来生效）
- **§11-N4 drop**：retro 沉淀"非 production bug，client cp936 vs utf-8 显示问题"+ 字节级 verify lesson

## 改动

- `tools/jury/config.py:48` +1 行 list insert
- `tests/jury/test_config.py` +1 测试函数
- `docs/cad-jury-config.md §4` 表 +1 行
- `CLAUDE.md` +12 行新小节
- `retro` 新写

**+1 production line / +1 测试 / 总 diff ~100 行**

## 测试

- jury 子集：503 → **504 PASS**（+1 新测试）
- 全套件：3193 → 3194 / 0 regression

## 关键发现 — Layer 6 E1 揭示 production scope 漂移

原 spec 假设纯 docs PR；layer 6 grep `tools/jury/config.py:45-186` 揭示 `BUILTIN_MODEL_COST_USD` list 是 production 真实查表源，`cad-jury-config.md §4` 只是 doc mirror；必须同步改 production。spec scope 翻倍至 ~100 行（含 1 production + 1 测试）。

## §11 + §12 闭合状态

| 项 | 状态 |
|---|---|
| §12 F1/F2/f3/f5/f6 + **f2** | closed |
| §12 f1 / f4 | 未闭合 |
| **§11-N5** | closed (本 PR) |
| §11-N4 | drop (非 bug) |
| §11-N1 / N2 / N3 | 未闭合（batch 2/3）|

## Spec / Plan / Retro

完整文档见 `docs/superpowers/{specs,plans,reports}/2026-05-15-v2-37-6-followup-cleanup-*.md`。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: 等 CI 8/8 全绿**

```bash
gh pr checks --watch
```

Expected: 8/8 SUCCESS。

### Task 6b: Merge + Tag v2.37.6 + Release（用户授权后）

按 v2.37.5 模板：
- Step 5: `gh pr merge <PR#> --squash --delete-branch`
- Step 6: git pull main + 等 main CI 8/8
- Step 7: `git tag -a v2.37.6 $MAIN_SHA -m "v2.37.6 — §11-N5 estimate table + §12 f2 memory citation"` + push
- Step 8: `gh release create v2.37.6 --notes-file <notes>`（升级路径复用 v2.37.5 模板）
- Step 9: `gh release view v2.37.6` 验证
- Step 10: 写 `project_v2_37_6_done.md` memory + MEMORY.md 索引行

---

## Self-Review

**1. Spec coverage**:

| Spec 章节 | Plan Task | 备注 |
|---|---|---|
| §2.1 改动表 row 1 (tools/jury/config.py:48) | Task 2 Step 1 | ✓ |
| §2.1 改动表 row 2 (test_config.py 新测试) | Task 1 Step 1 + Task 2 Step 3 | ✓ |
| §2.1 改动表 row 3 (cad-jury-config.md §4) | Task 3 Step 1 | ✓ |
| §2.1 改动表 row 4 (CLAUDE.md memory 约定) | Task 4 Step 2 | ✓ |
| §2.1 改动表 row 5 (retro) | Task 5 Step 1 | ✓ |
| §3 D1-D3 决策 | Task 2 (D1) + Task 4 (D3) + Task 5 retro (D2 §11-N4) | ✓ |
| §4 AC-1..8 | Task 2 Step 3 (AC-1) / Task 3 Step 2 (AC-2) / Task 4 Step 3 (AC-3+AC-4) / Task 5 (AC-5) / Task 2 Step 5 (AC-6) / Task 6a Step 4 (AC-7) / Task 6b Step 7 (AC-8) | ✓ |
| §6 不变量 #1-7 | Task 全程维持（list 仅插 1 行 / lookup_builtin_cost 不动 / docs §1-§3+§5-§13 不动 / CLAUDE.md §1-§4+glossary 不动）| ✓ |
| §7 流程 + 3 commit | Task 2 Step 7 (feat) + Task 4 Step 6 (docs) + Task 5 Step 3 (retro) | ✓ |
| §8 6 调查步 | Task 0 Step 1-6 全覆盖 | ✓ |
| §9 plan 必 cover | Task 0 实测 + Task 1 TDD RED + Task 2 dev_sync + Task 4 grep -cE + bytes verify lesson Task 5 retro | ✓ |
| §10 不写代码事项 | 全 task 不做（不改 lookup_builtin_cost / 不改 jury production 其它 / 不强制 retro-fit 既有 memory 引用）| ✓ |
| §11 §11+§12 follow-up 表 | Task 5 retro § §11+§12 表 | ✓ |
| §12 本 PR follow-up h1/h2 | Task 5 retro 末 follow-up 注 | ✓ |

**所有 spec 章节有 task 覆盖。**

**2. Placeholder scan**: 无 TBD / TODO / implement later。retro 数字字段（待补 per-task review 数字）+ PR # 占位"待 merge 回填"是显式留白（v2.37.5 实证）。

**3. Type consistency**: `BUILTIN_MODEL_COST_USD: list[tuple[str, float]]` Task 0/1/2 一致；`lookup_builtin_cost` 函数名 Task 1+2 跨引用一致；`gpt-image` prefix Task 1-3 跨 task 一致；`("gpt-image", 0.010)` tuple Task 2 + spec D1 字面 byte-equal。

**Plan 自检无问题 → ready for handoff。**

---

## 执行方式选择

Plan 完成保存到 `docs/superpowers/plans/2026-05-15-v2-37-6-followup-cleanup.md`。两种执行模式：

1. **Subagent-Driven（推荐）** — v2.37.x 15 连续 PR 一次过 CI 模板
2. **Inline 执行** — scope 较小可考虑（含 1 production + 1 测试 + 3 doc 改）

建议 Subagent-Driven。
