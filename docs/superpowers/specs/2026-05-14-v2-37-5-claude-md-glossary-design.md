# 设计：v2.37.5 §12 f3 cleanup — CLAUDE.md 项目术语 glossary

- **日期**：2026-05-14
- **基线**：main@`5f074f5`（v2.37.4 merge 后；working tree clean）
- **分支**：`feat/v2-37-5-claude-md-glossary`（待建）
- **目标版本**：v2.37.5（patch release / 纯 git tag + GitHub Release / 不 bump 版本文件）
- **规模**：小 单 PR；总 diff ≈ 90-95 行（CLAUDE.md +30 / retro +60）
- **状态**：brainstorming 完成；待用户复审 → writing-plans

---

## 1. 背景与目标

v2.37.2 §12 预登记 layer 5 R2 L4：spec / plan / retro 反复出现项目内部 jargon（北极星 5 gate / canonical-mirror / §11 vs §12 follow-up 轨道 / pure refactor PR 等）但未在任何地方集中定义，新工程师/读者第一次接触需翻 30+ memory 才能理解。

**解决**：`CLAUDE.md` append §"项目术语 glossary"节，10 项核心术语 2-3 行 def + memory 引用；CLAUDE.md 是 always-loaded context，所有 spec writer 主 agent 都看到，单点权威。

**北极星 5 gate**：零配置 ✓ / 稳定可靠 ✓ / 结果准确 ✓ / 傻瓜式 ✓ / SW 装即用 ✓；Windows-only ✓。

---

## 2. 范围

### 2.1 In-scope

| 文件 | 改动 | 行数 |
|---|---|---|
| `CLAUDE.md` | append 新节"## 项目术语 glossary"（在"## 提交规范"节之后），含 10 项术语 | ~30-35 行 |
| `AGENTS.md` | dev_sync.py 自动 regen（CLAUDE.md 改 → AGENTS.md 可能 regen）| 可能 +0-5 行 |
| `docs/superpowers/reports/2026-05-14-v2-37-5-claude-md-glossary-retro.md`（新写）| retro 文档 | ~60 行 |

**总 diff ≈ 90-100 行**

### 2.2 Out-of-scope

- 0 production code / 0 测试 / 0 schema / 0 env-config 改
- 不建 ADR 体系（如 `docs/superpowers/adrs/`）
- 不建 `docs/PROJECT_CONVENTIONS.md` 独立 doc（D1 决策落 CLAUDE.md 单点）
- 不改 `dev_sync.py` 逻辑
- §12 残留 3 项（f1 max_tokens sunset / f2 spec memory inline 摘要 / f4 N≥50 批量成本）
- CLAUDE.md 既有 §1-§4（Superpowers 工作流 / TDD / 调试 / 并行任务）+ §技术规范 + §语言规范 + §提交规范 字面零改

---

## 3. Glossary 10 项术语清单（spec 锁定，plan 内嵌完整文本）

每项格式 = `**术语名** — 1 行含义；见 memory \`xxx.md\` 或 spec §X.Y`：

| # | 术语 | 1 行含义 | 来源 |
|---|---|---|---|
| 1 | **北极星 5 gate** | 零配置 / 稳定可靠 / 结果准确 / SW 装即用 / 傻瓜式操作；任何新 plan 必过 | memory `project_north_star.md` |
| 2 | **v2.25+ tag-only release** | 纯 git tag + GitHub Release notes 发布；不 bump `pyproject.toml` 版本（停留 `2.24.0`）；用户用 `pip install git+https://...@vX.Y.Z` 安装 | memory `project_current_status.md` / `project_v2_31_1_packaging_cleanup.md` |
| 3 | **canonical / mirror** | `tools/jury/*.py` 是 canonical（git tracked）；`src/cad_spec_gen/data/tools/jury/*.py` 是 mirror（gitignored，`scripts/dev_sync.py` 同步）；`hatch_build.py` COPY_DIRS 打包发用户 | memory `feedback_subagent_cwd_drift.md` / v2.37.2 spec §6 #7-#9 |
| 4 | **§11 vs §12 follow-up 轨道** | §11 = 项目级 STATUS doc（如 `JURY_MATCHES_SPEC_STATUS.md`）的 follow-up；§12 = 单个 spec doc 自身 PR-self follow-up；两个独立轨道不混 | memory `project_v2_37_4_done.md` |
| 5 | **pure refactor PR / no-RED phase** | refactor/docs PR 既有测试就是 GREEN safety net，不需 RED 阶段；TDD R-only 模式；commit body 必显式标注 | v2.37.3 spec §3.4 D4 |
| 6 | **5 层 + 1 scout 审查** | self / cynical re-read / code-spec 对照 / edge-case hunter / 5 角色 + dry-run 五层 + writing-plans 入口 scout grep；spec ≥100 行默认走 | memory `feedback_spec_review_4layers.md` |
| 7 | **subagent-driven 模式** | 主 agent 每 plan task 派发 fresh subagent，2 阶段 review（spec compliance + code quality）；fresh context 防污染；连续 13+ PR 一次过 CI 实证 | memory `feedback_subagent_driven_main_agent_scouts.md` |
| 8 | **layer 6 grep AC predicates** | spec AC grep strict 验证用 exclusion-zone（`grep -v` 排除 helper 自身）或 indent-anchor（`grep "    pattern"` 限 test-body）；OR pattern 用 `-cE` 显式 ERE 不用 `\|` BRE | v2.37.3/v2.37.4 retro |
| 9 | **sw-smoke CI flake** | `.github/workflows/sw-smoke.yml` 的 `actions/upload-artifact@v7` 步是已知 transient flake 点；与 `tests.yml` 8 job release gate 无关 | memory `feedback_sw_runner_infra.md` |
| 10 | **plan-drift 5 分类** | spec 写时假设漂移：(a) API 不存在 (b) 路径假设错 (c) 测试 helper 误用 (d) 实现细节 bug (e) 参数签名；plan 第 0 task scout grep 防御 | memory `feedback_plan_drift_taxonomy.md` |

### 3.1 完整 markdown 文本（plan Task 1 逐字写入 CLAUDE.md）

```markdown
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

---

## 4. 设计决策

### 4.1 D1 — 落地 CLAUDE.md 而非新建独立 doc

**抉择**：append 到 `CLAUDE.md` 末尾。

**理由**：CLAUDE.md 是 session 启动 always-loaded context，所有 spec writer 主 agent 必看；83 → ~115 行仍轻量；单点权威无 cross-link 维护成本。

### 4.2 D2 — 每项术语 2-3 行（term + 含义 + memory 引用）

**抉择**：每项 = 粗体术语名 + 1 行含义 + memory 引用，不展开决策史/例子。

**理由**：保持 mini-glossary 性质；深入查阅按 memory 引用追溯（项目 memory 体系已成熟）。

### 4.3 D3 — 10 项术语固定，scope 锁死

**抉择**：spec §3 表锁 10 项术语，plan 逐字照抄到 CLAUDE.md。

**理由**：避免 scope creep（加 20+ 项）；新术语沉淀需进 glossary 时开独立 follow-up PR（spec §12 g1 触发条件 = "同一术语在 ≥ 3 份 spec/plan/retro 出现"）。

### 4.4 D4 — 章节位置 = CLAUDE.md 末尾

**抉择**：append 在"## 提交规范"节之后；不插入中间。

**理由**：保既有节序不变；glossary reference 性质放末尾合理（既有节"必走流程"性质放前）。

---

## 5. 验收

- **AC-1** `CLAUDE.md` 加新节"## 项目术语 glossary"含 10 项术语
- **AC-2** 每项术语包含：(a) **粗体术语名** (b) 1 行含义 (c) memory 引用（`见 memory ...md` 或 spec §X.Y 引用）
- **AC-3** grep strict 验证（layer 6 E4 教训复用，OR pattern 用 `-cE`）：
  - `grep -c "## 项目术语 glossary" CLAUDE.md` == **1**
  - `grep -cE "北极星 5 gate|canonical / mirror|pure refactor PR|subagent-driven|layer 6 grep" CLAUDE.md` ≥ **5**（10 项术语关键短语至少 5 项出现）
  - `grep -c "新增术语门槛" CLAUDE.md` == **1**（spec §3.1 末段"新增术语门槛"治理规则）
- **AC-4** retro 文档新写 ≥ 30 行；含 §12 f3 closed 标记 + 沉淀 lessons
- **AC-5** 全套件 PASS 不变（CLAUDE.md 改可能触发 `tests/test_agents_md.py` 元测试；plan task 0 实测 baseline + Task 1 后跑 `python scripts/dev_sync.py` 重生 AGENTS.md + 元测试一起跑）
- **AC-6** CI 8/8 SUCCESS
- **AC-7** 发 v2.37.5 patch tag + GitHub Release

---

## 6. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| `tests/test_agents_md.py` 元测试 fail | **中**（CLAUDE.md 变 → dev_sync regen AGENTS.md → 元测试断言可能 fail）| plan task 0 实测 baseline；Task 1 实施完跑 `dev_sync.py` regen AGENTS.md + 元测试 ≤ 5s 内验证 |
| AGENTS.md 100 字描述截断 | 低（CLAUDE.md 新节是独立 ## 不进 skill 表）| AGENTS.md 既有 skill 表行不影响 |
| memory 引用失锚（memory 改名 / 删）| 低-中（v2.37.3 layer 5 R2 L3 教训）| 每项术语含 memory file 名 + 1 行含义可独立读懂；memory 删/改名后 glossary 仍可用 |
| 10 项术语未来过期 | 低 | spec §3 锁今天 snapshot；过期开 follow-up PR 改；spec §3.1 末段"新增术语门槛"治理规则 |
| 新工程师不查 memory 看 glossary 误用术语 | 低 | 每项含 1 行含义已自洽；memory 是"深入查阅"非"必须"|

---

## 7. 不变量

1. 0 production code / 0 测试 / 0 schema / 0 env-config 改
2. CLAUDE.md 既有 §1-§4（Superpowers 工作流 / TDD / 调试 / 并行任务）+ §技术规范 + §语言规范 + §提交规范 字面零改动
3. 既有 `docs/` 无改动
4. `scripts/dev_sync.py` 逻辑不动
5. 仅 append 新节 + 可能伴随 `AGENTS.md` 自动 regen 同步

---

## 8. 流程

```
brainstorming（本 spec）→ writing-plans → 3 task plan → execute
  ↓
Pure docs（无 RED phase）+ dev_sync.py 重生 AGENTS.md
  ↓
self-review → CI → squash merge → 等 main CI → tag v2.37.5 → Release
```

提交 2 commit：
1. `docs(claude-md): 加 §项目术语 glossary 10 项核心术语（§12 f3）` — CLAUDE.md +（dev_sync regen 后）可能 AGENTS.md
2. `docs(v2-37-5): retro 沉淀` — retro doc

### 8.1 Rollback 流程

pure docs PR rollback 极低风险。若用户报"glossary 措辞误导"：
- `git revert <v2.37.5 merge_sha>` 回退 CLAUDE.md 改动
- 发 v2.37.6 修措辞
- GitHub Release UI 标 v2.37.5 "Pre-release"

---

## 9. Plan 调查步（plan 第 0 task 跑）

1. `cd D:/Work/cad-spec-gen && git status --short && git log --oneline -3` — 验证 baseline main@`5f074f5` clean
2. `python scripts/dev_sync.py --check` rc=0 — baseline 镜像干净（v2.37.3 R5 D2 教训）
3. `pytest -q tests/jury/ tests/jury_loop/ tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3` — baseline PASS 数实测（v2.37.4 后 = 503 jury + 5 元测试）
4. `grep -nE "^## " CLAUDE.md` — 实测既有 ## 节列表（"提交规范"是最后一节，appen 位置 = 该节末行之后）
5. `wc -l CLAUDE.md AGENTS.md` — 实测两文件当前行数（baseline 用于 Task 1 后增量验证）
6. `python scripts/dev_sync.py --check` 跑后看是否输出涉 AGENTS.md（确认 CLAUDE.md → AGENTS.md regen 链）

---

## 10. Plan 必 cover 项

- 每 commit 含 canonical 改 + 可能伴随 AGENTS.md regen（CLAUDE.md 不进 dev_sync mirror，但 AGENTS.md 是 dev_sync 重生产物）
- PR push 前 `git fetch origin main` 无并行改 CLAUDE.md
- baseline `dev_sync --check` rc=0 验证后再 task（v2.37.3 R5 D2）
- AC-3 grep `-cE` OR pattern（v2.37.4 layer 6 E4）
- spec §3 表 10 项术语 plan 实施时**逐字照抄**到 CLAUDE.md（不微调措辞）
- Task 1 实施完必跑 `python scripts/dev_sync.py` regen AGENTS.md + `pytest tests/test_agents_md.py tests/test_no_tracked_mirror.py` 验证元测试不 break

---

## 11. v2.37.2 §12 follow-up 表（本 PR 闭合 f3）

| # | 严重度 | 内容 | 状态 |
|---|---|---|---|
| F1 | LOW | mock helper 抽取 | closed v2.37.3 ✓ |
| F2 | LOW | line 105 注释扩 rationale | closed v2.37.3 ✓ |
| **f3** | **LOW** | **spec mini-glossary** | **closed v2.37.5**（本 PR）|
| f5 | LOW | user-visible 6-key debug 注释 | closed v2.37.4 ✓ |
| f6 | LOW | schema 不变 + DISABLE_LLM no-op | closed v2.37.4 ✓ |
| f1 | LOW | max_tokens sunset 条件 | 未闭合 |
| f2 | LOW | spec memory inline 摘要 | 未闭合 |
| f4 | LOW | N≥50 批量成本 | 未闭合 |

> v2.37.3 retro 沉淀的 2 项新 §11 follow-up（AC grep exclusion-zone + commit body 不自报 col）不属本 §12 表，独立轨道追踪（§11/§12 follow-up 轨道区分）。

---

## 12. 本 PR 自身 follow-up

| # | 严重度 | 内容 | 来源 |
|---|---|---|---|
| g1 | LOW | 未来 glossary 新术语沉淀加入 CLAUDE.md；触发条件 = 同一术语在 ≥ 3 份 spec/plan/retro 重复出现 | spec §3.1 末段"新增术语门槛" |
