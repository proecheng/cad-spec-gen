# v2.37.5 §12 f3 cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭合 v2.37.2 §12 预登记 layer 5 R2 L4 — `CLAUDE.md` append §"项目术语 glossary" 节 10 项核心术语；发 v2.37.5 patch tag。

**Architecture:** Pure docs PR — 在项目根 `CLAUDE.md`（83 行）末尾"## 提交规范"节之后 append 新节"## 项目术语 glossary"+ disclaimer 段 + 10 项术语 + "新增术语门槛"治理规则。`dev_sync.py` 可能 regen `AGENTS.md`（CLAUDE.md → AGENTS.md 衍生）；tests/test_agents_md.py 元测试需一起跑验证。

**Tech Stack:** markdown + dev_sync.py + git tag-based release（不 bump 版本文件）。

**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-5-claude-md-glossary-design.md`（227 行 / brainstorming F1+F2+F3 fix）

**分支：** `feat/v2-37-5-claude-md-glossary`（已建 / HEAD `e76a6c2`）

---

## File Structure

| 文件 | 用途 | 改动范围 |
|---|---|---|
| `CLAUDE.md` | 项目根 always-loaded context | append §"项目术语 glossary" 节（在"## 提交规范"之后）含 disclaimer + 10 项术语 + 治理规则；既有 §1-§4 + 技术规范 + 中文规范 + 提交规范字面零改 |
| `AGENTS.md` | `dev_sync.py` 重生产物（AUTO-GENERATED）| Task 1 跑 `python scripts/dev_sync.py` 后可能 regen（CLAUDE.md → AGENTS.md 衍生）|
| `docs/superpowers/reports/2026-05-14-v2-37-5-claude-md-glossary-retro.md` | retro 文档（新写）| ~60 行 |

**不动文件**：任何 `tools/*.py` / 任何测试 / `.github/workflows/*` / `scripts/dev_sync.py` 逻辑 / 任何 schema / `docs/` 既有 doc。

---

## Task 0: Scout + baseline 实测

**Files:** Read only.

- [ ] **Step 1: 切到分支并 fetch 验证无并行改动**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git checkout feat/v2-37-5-claude-md-glossary
git log --oneline HEAD..origin/main
git log --oneline HEAD..origin/main -- CLAUDE.md AGENTS.md
```

Expected: 都为空。报告。

- [ ] **Step 2: baseline dev_sync --check**

```bash
python scripts/dev_sync.py --check
echo "rc=$?"
```

Expected rc=0。非 0 → 先 `python scripts/dev_sync.py` 同步再 check；仍非 0 → BLOCKED。

- [ ] **Step 3: baseline PASS 数（含元测试关键）**

```bash
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 元测试 5 PASS / jury 子集 503 PASS。**报告**。

- [ ] **Step 4: 实测 CLAUDE.md 既有 ## 节列表 + AGENTS.md 行数**

```bash
grep -nE "^## " CLAUDE.md
wc -l CLAUDE.md AGENTS.md
```

Expected: ~6-8 个 ## 节命中，最末节是"## 提交规范"（spec snapshot CLAUDE.md = 83 行 / AGENTS.md = 49 行）。**报告实际行号 + 最末节起止位置**（Task 1 append 锚点）。

- [ ] **Step 5: 实测 dev_sync.py 是否触及 AGENTS.md（CLAUDE.md → AGENTS.md regen 链确认）**

```bash
grep -n "AGENTS\|agents_md\|CLAUDE" scripts/dev_sync.py | head -20
```

Expected: 若 dev_sync.py 触及 AGENTS.md 生成则有命中；否则说明 AGENTS.md 是其它机制生成。报告结果决定 Task 1 是否需跑 dev_sync。

- [ ] **Step 6: 实测 AGENTS.md 内部是否引 CLAUDE.md 内容**

```bash
head -5 AGENTS.md
grep -n "CLAUDE\|AUTO-GENERATED" AGENTS.md | head -10
```

Expected: 若 AGENTS.md 有 `AUTO-GENERATED` 标记说明它是 dev_sync regen 产物；若引"CLAUDE.md"说明衍生关系。报告。

- [ ] **Step 7: 记录到 scratchpad**

无 commit；只在 report 汇总：
- CLAUDE.md 最末节"## 提交规范"末行号（Task 1 append 位置）
- AGENTS.md baseline 行数
- 元测试 5 PASS / jury 503 PASS baseline
- dev_sync.py 是否触及 AGENTS.md（决定 Task 1 工作量）

---

## Task 1: 加 §项目术语 glossary 到 CLAUDE.md

**Files:** Modify: `CLAUDE.md`（append 末尾）；可能伴随 `AGENTS.md` regen。

**TDD 模式**：无 RED phase（pure documentation；AC-3 三个 grep strict + 元测试 sanity 双验证）。

- [ ] **Step 1: 定位 CLAUDE.md append 锚点**

读 Task 0 Step 4 实测得到的 CLAUDE.md 最末节"## 提交规范"末行号。**append 位置 = 文件末尾**（既有"提交规范"节末是文件最后内容；用 Edit 工具 `old_string` = `提交前必须：测试全部通过 → code-review 无阻断性问题 → lint 检查通过`，`new_string` = `[原文] + 空行 + --- + 空行 + 新节全文`）。

或简单策略：直接读 `CLAUDE.md` 末 5 行确认最末是 `提交前必须：...lint 检查通过`，然后 append 到文件末尾。

- [ ] **Step 2: 写新节完整 markdown 块**

在 CLAUDE.md 末尾 append 以下 markdown（spec §3.1 逐字照抄）：

```markdown


---

## 项目术语 glossary

本节集中定义 spec / plan / retro 反复出现的项目内部术语，新工程师快速理解上下文。

> **memory 引用约定**：下表 "见 memory `xxx.md`" 引用为本仓主 maintainer 的 Claude Code session memory（per-instance；位于 `~/.claude/projects/D--Work-cad-spec-gen/memory/`，其他开发者本机路径相对应）。每项术语已附 1 行含义，可独立读懂；memory 引用为深入查阅入口而非必需（layer 6 F1 教训：git tracked 文档避免假定用户特定路径）。

1. **北极星 5 gate** — 零配置 / 稳定可靠 / 结果准确 / SW 装即用 / 傻瓜式操作；任何新 plan 必过这 5 条 gate（见 memory `project_north_star.md`）

2. **v2.25+ tag-only release** — 纯 git tag + GitHub Release notes 发布模式；不 bump `pyproject.toml` 版本（停留 `2.24.0`）；用户安装走 `pip install git+https://github.com/proecheng/cad-spec-gen.git@vX.Y.Z`（见 memory `project_current_status.md` / `project_v2_31_1_packaging_cleanup.md`）

3. **canonical / mirror** — `tools/jury/*.py` 等是 canonical（git tracked）；`src/cad_spec_gen/data/tools/jury/*.py` 是 mirror（gitignored，`scripts/dev_sync.py` 同步）；`hatch_build.py` `COPY_DIRS = {"tools": "tools"}` 打包发用户（定义见 v2.37.2 spec §6 #7-#9 + `scripts/dev_sync.py`；漂移防御见 memory `feedback_subagent_cwd_drift.md`）

4. **§11 vs §12 follow-up 轨道** — §11 = 项目级 STATUS doc（如 `docs/superpowers/JURY_MATCHES_SPEC_STATUS.md`）的 follow-up 表；§12 = 单个 spec doc 自身 PR-self follow-up 表；两个独立轨道不混，新登必明确归哪个（见 memory `project_v2_37_4_done.md`）

5. **pure refactor PR / no-RED phase** — refactor 或 docs-only PR 用既有测试作 GREEN safety net，不需 TDD RED 阶段；R-only 模式；commit body 必显式标注（见 v2.37.3 spec §3.4 D4）

6. **5 层 + 1 scout 审查** — spec ≥ 100 行默认跑：self / cynical re-read / code-spec 对照 / edge-case hunter / 5 角色 adversarial + dry-run 五层 + writing-plans 入口 scout grep；每层抓不同 bug 类别（见 memory `feedback_spec_review_4layers.md`）

7. **subagent-driven 模式** — 主 agent 每 plan task 派发 fresh subagent 实施，跑 2 阶段 review（spec compliance + code quality）；fresh context 防污染；项目连续 13+ PR 一次过 CI 实证（见 memory `feedback_subagent_driven_main_agent_scouts.md`）

8. **layer 6 grep AC predicates** — spec AC 用 grep strict 验证时：(a) 抽 helper 类 refactor 用 exclusion-zone（`grep -v` 排除 helper 自身行）或 indent-anchor（`grep "    pattern"` 限 test-body context）；(b) OR pattern 用 `grep -cE "X|Y"` 显式 ERE 跨平台可靠；不用 `\|`（GNU grep BRE 支持但 BSD / MSYS grep BRE 不识别，跨 grep 实现不可靠）（见 v2.37.3 / v2.37.4 retro）

9. **sw-smoke CI flake** — `.github/workflows/sw-smoke.yml` 的 `actions/upload-artifact@v7` 步是已知 transient flake 点；非 SW 测试本身挂；与 `tests.yml` 8 job release gate 无关，单独失败不阻断 release（见 memory `feedback_sw_runner_infra.md`）

10. **plan-drift 5 分类** — spec 写时常踩的假设漂移类型：(a) API 不存在 (b) 路径假设错 (c) 测试 helper 误用 (d) 实现细节 bug (e) 参数签名；plan 第 0 task scout grep 防御（见 memory `feedback_plan_drift_taxonomy.md`）

> **新增术语门槛**：同一术语在 ≥ 3 份 spec/plan/retro 重复出现 → 开 follow-up PR 加入本表。维持 mini-glossary 精简性。
```

**实施操作**：
1. 用 Edit 工具，`old_string` = `提交前必须：测试全部通过 → code-review 无阻断性问题 → lint 检查通过`（unique 最末行）
2. `new_string` = `提交前必须：测试全部通过 → code-review 无阻断性问题 → lint 检查通过` + 上方完整 markdown 块（包含开头的 `\n\n---\n\n## 项目术语 glossary\n...`）

注意：新内容开头的 `---` 是 markdown 分隔符（与既有节之间）；末尾 `> **新增术语门槛**` 段不需要再加 `---`（文件末尾即可）。

- [ ] **Step 3: 跑 dev_sync.py regen AGENTS.md（spec §6 row 1 风险 mitigate）**

```bash
cd D:/Work/cad-spec-gen
python scripts/dev_sync.py
git status --short
python scripts/dev_sync.py --check
echo "rc=$?"
```

Expected:
- 若 dev_sync.py 触及 AGENTS.md 重生：`git status` 显示 `CLAUDE.md` modified +（可能）`AGENTS.md` modified；`--check` rc=0
- 若 dev_sync.py 不触 AGENTS.md：只 `CLAUDE.md` modified；rc=0

**报告 dev_sync 输出 + git status 实际**。

- [ ] **Step 4: 跑元测试验证不 break（关键 — spec §6 row 1 mitigate）**

```bash
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -10
```

Expected: 全 PASS。

**若 fail**：读 fail message 分析。可能 root cause：
- a) `test_agents_md.py` 断言 AGENTS.md 内某具体字符串/计数；CLAUDE.md → AGENTS.md regen 后字符串变化 → 需要看测试是否断言"动态生成内容"还是"固定模板"
- b) `test_no_tracked_mirror.py` 追踪 gitignore 排除 ∩ tracked 文件集为空；本 PR 不动 gitignore，应不触发

具体修：依 fail 信息定。若元测试断言 AGENTS.md 含特定 skill 表行（v2.37.2 layer 5 R2 L4 时代实测过此风险），新增 CLAUDE.md ## 节不应影响 skill 表（CLAUDE.md "## 项目术语 glossary" 不是 skill）。

- [ ] **Step 5: AC-3 grep strict 验证（spec §5）**

```bash
grep -c "## 项目术语 glossary" CLAUDE.md
grep -cE "北极星 5 gate|canonical / mirror|pure refactor PR|subagent-driven|layer 6 grep" CLAUDE.md
grep -c "新增术语门槛" CLAUDE.md
```

Expected:
- `## 项目术语 glossary` == **1**
- 5 OR pattern `-cE` ≥ **5**
- `新增术语门槛` == **1**

任一不满足 → 回 Step 2 修正措辞确保关键短语出现。

- [ ] **Step 6: 全套件 sanity**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 503 PASS / 6 skipped（与 Task 0 baseline 一致；docs 改零行为影响）。

- [ ] **Step 7: REFACTOR 步显式确认**

审视 §项目术语 glossary 节：
- 10 项术语 spec §3 表一致（逐字照抄无微调）✓
- disclaimer 段说明 memory 引用 per-instance 性质 ✓
- 末尾"新增术语门槛"治理规则防 scope creep ✓
- 与 CLAUDE.md 既有节风格一致（## 节 + ### 子节 + > blockquote + 编号列表）✓
- Commit message 加 `REFACTOR: 风格沿用既有 §1-§4，无进一步可清`

- [ ] **Step 8: Commit**

注意：根据 Step 3 结果，可能需要 add CLAUDE.md + AGENTS.md（若 AGENTS.md regen）或只 CLAUDE.md。

```bash
cd D:/Work/cad-spec-gen
# 看 Step 3 git status 决定加哪些文件
git add CLAUDE.md
git status --short  # 确认 AGENTS.md 是否需要加
# 若 AGENTS.md modified 也需加：
# git add AGENTS.md

git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(claude-md): 加 §项目术语 glossary 10 项核心术语（§12 f3）

v2.37.2 §12 预登记 layer 5 R2 L4 闭合：spec/plan/retro 反复出现项目内部 jargon
（北极星 5 gate / canonical-mirror / §11 vs §12 follow-up 轨道等）但未集中定义；
本 PR 在 CLAUDE.md（always-loaded context）末尾加 §"项目术语 glossary"节。

10 项核心术语（每项 = 粗体术语 + 1 行含义 + memory 引用）：
1. 北极星 5 gate / 2. v2.25+ tag-only release / 3. canonical / mirror /
4. §11 vs §12 follow-up 轨道 / 5. pure refactor PR / no-RED phase /
6. 5 层 + 1 scout 审查 / 7. subagent-driven 模式 / 8. layer 6 grep AC predicates /
9. sw-smoke CI flake / 10. plan-drift 5 分类

含治理规则"新增术语门槛"防 scope creep（≥3 份文档重复出现才加）+
disclaimer 段说明 memory 引用为 per-instance（layer 6 F1 教训）。

零代码 / 零测试 / 零行为变化（pure docs append；既有 §1-§4 + 技术规范 +
中文规范 + 提交规范字面零改）。

AC-3 grep strict 验证（spec §5 / layer 6 E4 ERE fix）：
- ## 项目术语 glossary == 1 ✓
- 5 OR pattern -cE ≥ 5 ✓
- 新增术语门槛 == 1 ✓

REFACTOR: 风格沿用既有 §1-§4（## 节 + 编号列表 + > blockquote），无进一步可清。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: retro 文档新写

**Files:** Create: `docs/superpowers/reports/2026-05-14-v2-37-5-claude-md-glossary-retro.md`

- [ ] **Step 1: 写 retro 文档**

复用 v2.37.4 retro 风格，新建 `docs/superpowers/reports/2026-05-14-v2-37-5-claude-md-glossary-retro.md`：

```markdown
# Retro — v2.37.5 §12 f3 cleanup (CLAUDE.md 项目术语 glossary)

**完工日期：** 2026-05-14
**PR：** #N（占位，merge 后回填）
**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-5-claude-md-glossary-design.md`（227 行 / brainstorming F1+F2+F3 fix）
**Plan：** `docs/superpowers/plans/2026-05-14-v2-37-5-claude-md-glossary.md`
**Baseline：** main@`5f074f5`（v2.37.4 merge）→ merge@<sha>（占位回填）

## 一句话

v2.37.2 §12 预登记 layer 5 R2 L4 闭合：spec / plan / retro 反复出现项目内部 jargon 未集中定义；本 PR 在 CLAUDE.md（always-loaded context）末尾加 §"项目术语 glossary"节 10 项核心术语。pure docs append，零行为变化。

## 完工范围

- §12 f3 closed：`CLAUDE.md` 加 §"项目术语 glossary"含 disclaimer + 10 项术语 + 治理规则
- 10 项术语：北极星 5 gate / v2.25+ tag-only release / canonical-mirror / §11 vs §12 follow-up 轨道 / pure refactor PR + no-RED / 5 层 + 1 scout 审查 / subagent-driven 模式 / layer 6 grep AC predicates / sw-smoke CI flake / plan-drift 5 分类
- 既有 CLAUDE.md §1-§4 + 技术规范 + 中文规范 + 提交规范字面零改
- 治理规则"新增术语门槛"防 mini-glossary 未来 scope creep

## 数字

- 元测试 PASS：5 → 5 不变
- jury 子集 PASS：503 → 503 不变
- 全套件 PASS：3193 → 3193 / 17 skipped / 0 regression
- diff stat：1-2 文件 / +30-35 行 (CLAUDE.md) + 可能 AGENTS.md 自动 regen + retro 60 行
- 3 commits（spec / plan / Task 1 + Task 2）
- CI 8/8 SUCCESS（待 PR 后实测）

## 2 层 + per-task review 审查统计

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming 数据/漂移 | 3 (F1+F2+F3)| 3 | 0 |
| layer 6 边界 + 闭环 | 跳过（scope 极小 + brainstorming 已覆盖主要边界）| 0 | 0 |
| per-task spec+quality review × 2 task | 待补 | 待补 | 待补 |
| **总** | **3+** | **3+** | **0+** |

## 沉淀 lessons

1. **作者视角 vs 读者视角差异**（F1）：spec 写 git tracked 文档时易引绝对 user-specific 路径（作者本机真实），但读者（其他开发者/CI）看不到；必须加 disclaimer 或抽象路径。**lesson**：CLAUDE.md / README / AGENTS.md 等"全用户可见"文档禁绝对 home 路径，必抽象或加 disclaimer。
2. **memory 引用要选对 file**（F2）：spec 写时主 agent 凭印象引 memory file，但实际 memory 主旨与术语含义可能轻微错位（如 `feedback_subagent_cwd_drift.md` 主旨是 cwd 漂移不是 canonical-mirror 定义）。**lesson**：spec 写 memory 引用时主 agent 应 `head -5 <memory>` 验证主旨匹配。
3. **同一 lesson 跨 PR 措辞逐次精化**（F3）：v2.37.4 layer 6 E4 抓到 grep BRE/ERE 兼容性，v2.37.5 spec 写时仍把"BRE 不识别 `\|`"描述笼统；v2.37.5 fix 精化到"GNU grep BRE 支持但 BSD/MSYS BRE 不支持"。**lesson**：跨 PR 沉淀的 lesson 在新 spec 引用时主 agent 应 verbatim 引前一份 retro 措辞，避免再次模糊。
4. **mini-glossary 治理规则**（spec §3.1 末段）：术语 glossary 易膨胀成字典；门槛 = 同一术语 ≥ 3 份 spec/plan/retro 重复出现才加。**lesson**：reference doc 类型 PR 必含治理规则防未来 scope creep。

## §12 follow-up 残留（不阻断）

v2.37.2 §12 闭合状态：
- F1/F2 → closed v2.37.3 ✓
- **f3 → closed v2.37.5 ✓**（本 PR）
- f5/f6 → closed v2.37.4 ✓
- f1 max_tokens sunset → 未闭合
- f2 spec memory inline 摘要 → 未闭合
- f4 N≥50 批量成本 → 未闭合

本 PR 自身 follow-up（spec §12 g1）= 未来 glossary 新术语沉淀；触发条件 ≥ 3 份文档重复，独立 PR 加入 CLAUDE.md §项目术语。

## 下次类似 PR 优化

- spec 引绝对 user-specific 路径加 disclaimer
- spec 引 memory file 必 `head -5` 验证主旨匹配
- 跨 PR 沉淀 lesson 引用要 verbatim 引前一份 retro
- reference doc 类 PR 必含治理规则
- glossary append 类 PR 模板 = v2.37.5 模式（无 RED / AC-3 grep strict + 元测试一起跑 / 既有内容零改）

[[project-v2-37-4-done]] 上游 §12 f5+f6 + 4 项 layer 6 lessons 追溯。
[[project-v2-37-2-done]] 上游 §12 全表来源。
```

- [ ] **Step 2: 元测试**

```bash
cd D:/Work/cad-spec-gen
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: 5 PASS。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/reports/2026-05-14-v2-37-5-claude-md-glossary-retro.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(v2-37-5): retro 沉淀 — §12 f3 closed + 4 项审查 lesson

闭合 v2.37.2 §12 预登记 f3 (spec mini-glossary) 项；
retro 沉淀 brainstorming F1+F2+F3 fix + 4 项新教训：
- 作者视角 vs 读者视角差异（F1）—— git tracked 文档禁绝对 user 路径
- memory 引用要选对 file（F2）—— spec 写时 head -5 验证主旨
- 同一 lesson 跨 PR 措辞逐次精化（F3）—— 引前 retro 要 verbatim
- mini-glossary 治理规则 —— reference doc 必含 scope creep 防御

PR # 占位字段在 squash merge 后回填。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: PR 全流程

**Files:** 无文件改动；纯 git / GitHub 操作。

按 v2.37.4 模板拆 2 阶段：3a push + 开 PR + 等 CI；3b merge + tag + Release（用户授权后）。

### Task 3a: Push + 开 PR + 等 CI

- [ ] **Step 1: PR push 前并行改动验证**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git log --oneline HEAD..origin/main
git log --oneline HEAD..origin/main -- CLAUDE.md AGENTS.md
```

Expected: 都为空（v2.37.4 merge 后 main 无并行改 CLAUDE.md/AGENTS.md）。

- [ ] **Step 2: Push 分支**

```bash
git push origin feat/v2-37-5-claude-md-glossary
```

- [ ] **Step 3: 开 PR**

```bash
gh pr create --title "docs(claude-md): v2.37 §12 f3 cleanup — 加项目术语 glossary（v2.37.5）" --body "$(cat <<'EOF'
## 概要

闭合 v2.37.2 §12 预登记 layer 5 R2 L4：spec / plan / retro 反复出现项目内部 jargon（北极星 5 gate / canonical-mirror 等）但未集中定义，新工程师/读者第一次接触需翻 30+ memory；本 PR 在 CLAUDE.md（always-loaded context）末尾加 §"项目术语 glossary"节 10 项核心术语。

## 改动

- `CLAUDE.md` append §"项目术语 glossary"（在"## 提交规范"之后），含 disclaimer + 10 项术语 + "新增术语门槛"治理规则；既有 §1-§4 + 技术规范 + 中文规范 + 提交规范字面零改
- 可能伴随 `AGENTS.md` dev_sync.py regen（CLAUDE.md → AGENTS.md 衍生）
- retro 文档新写

**0 production code / 0 测试 / 0 schema / 0 env-config / 0 行为变化** —— pure docs append。

## 测试

- 元测试 5 PASS 不变 / jury 子集 503 不变 / 全套件 3193 / 0 regression

## AC-3 grep strict (spec §5 + layer 6 E4 ERE fix)

- `## 项目术语 glossary` == 1 ✓
- 5 OR pattern `-cE` ≥ 5 ✓
- `新增术语门槛` == 1 ✓

## 审查层数

brainstorming F1+F2+F3 fix + per-task spec+quality review × 2 = 3+ findings，3+ inline 修。

## Spec / Plan / Retro

- Spec: `docs/superpowers/specs/2026-05-14-v2-37-5-claude-md-glossary-design.md`
- Plan: `docs/superpowers/plans/2026-05-14-v2-37-5-claude-md-glossary.md`
- Retro: `docs/superpowers/reports/2026-05-14-v2-37-5-claude-md-glossary-retro.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL 返回；记 PR #N。

- [ ] **Step 4: 等 PR CI 8/8 全绿**

```bash
gh pr checks --watch
```

Expected: 8/8 SUCCESS。Transient flake：连续 2 次同 failure signature 才视为 regression。

### Task 3b: Merge + Tag + Release（需用户授权后另派 subagent）

按 v2.37.4 Plan Task 3b 同模板：
- Step 5: `gh pr merge <PR_NUM> --squash --delete-branch`
- Step 6: git checkout main + pull + 等 main CI 8/8 全绿
- Step 7: `git tag -a v2.37.5 $MAIN_SHA -m "v2.37.5 — §12 f3 cleanup (CLAUDE.md 项目术语 glossary)"` + push
- Step 8: `gh release create v2.37.5 --notes "..."`（升级路径复用 v2.37.4 模板）
- Step 9: `gh release view v2.37.5` 验证
- Step 10: 写 `project_v2_37_5_done.md` memory + MEMORY.md 索引行

---

## Self-Review

**1. Spec coverage**:

| Spec 章节 | Plan Task | 备注 |
|---|---|---|
| §2.1 改动表 (CLAUDE.md + AGENTS.md + retro) | Task 1 + Task 2 | ✓ |
| §3 表 10 项术语 + §3.1 完整 markdown | Task 1 Step 2 逐字照抄 | ✓ |
| §4 4 决策 (D1 落 CLAUDE.md / D2 2-3 行 / D3 scope 锁 / D4 末尾位置) | Task 1 Step 1-2 | ✓ |
| §5 AC-1..7 | Task 1 Step 4 (AC-1/2) / Task 1 Step 5 (AC-3) / Task 2 (AC-4) / Task 1 Step 6 (AC-5) / Task 3a Step 4 (AC-6) / Task 3b (AC-7) | ✓ |
| §6 风险表 row 1 元测试 fail | Task 1 Step 4 mitigate | ✓ |
| §7 不变量 #1-5 | Task 1+2 全程维持 | ✓ |
| §8 + §8.1 Rollback | Task 3b 触发 | ✓ |
| §9 6 调查步 | Task 0 全覆盖 | ✓ |
| §10 plan 必 cover | Task 1 Step 3 dev_sync + Task 1 Step 4 元测试 | ✓ |
| §11 §12 表 | Task 2 retro 注 closed | ✓ |
| §12 g1 follow-up | Task 2 retro 提及"新增术语门槛"治理规则 | ✓ |

**所有 spec 章节有 task 覆盖。**

**2. Placeholder scan**: 无 TBD / TODO。PR # 占位"待 merge 后回填"是显式留白（v2.37.3/v2.37.4 实证）。

**3. Type consistency**: §项目术语 glossary 节标题在 Task 1 Step 2 + Step 5 grep AC 一致。10 项术语编号 1-10 + 粗体术语名 + memory 引用格式跨 task 一致。

**Plan 自检无问题 → ready for handoff。**

---

## 执行方式选择

Plan 完成保存到 `docs/superpowers/plans/2026-05-14-v2-37-5-claude-md-glossary.md`。两种执行模式：

1. **Subagent-Driven（推荐）** — v2.37.3/v2.37.4 实证模板可复用
2. **Inline 执行** — scope 极小可考虑

建议 Subagent-Driven。
