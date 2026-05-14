# 设计：v2.37.4 §12 f5+f6 cleanup — cad-jury-config.md 输出字段语义 + 版本承诺

- **日期**：2026-05-14
- **基线**：main@`a5f8c95`（v2.37.3 merge 后；working tree clean）
- **分支**：`feat/v2-37-4-jury-config-docs-cleanup`（待建）
- **目标版本**：v2.37.4（patch release / 纯 git tag + GitHub Release / 不 bump 版本文件）
- **规模**：极小 单 PR；总 diff ≈ 100-120 行（文档 + retro）
- **状态**：brainstorming 完成；待用户复审 → writing-plans

---

## 1. 背景与目标

v2.37.2 §12 预登记 6 项 layer 5 五角色 follow-up 中 2 项 user-visible 文档型：

- **f5** layer 5 R3 U4：用户读 `PHOTO3D_JURY_REPORT.json` 或 `ENHANCEMENT_REPORT.json` 看到 `semantic_checks` 段，特别是 v2.37.2 后 `_make_needs_review_verdict` 早返回路径产 6-key dict（5 项 boolean=False + `matches_spec=True`），可能困惑"为什么 5 项全 False 却 matches_spec=True 通过？"——需要 user-facing doc 说明 matches_spec 是 derived field（基于 features_status aggregate）+ 缺数据默认 True 是兜底语义。

- **f6** layer 5 R3 U5+U7：用户跨 v2.37 patch 版本升级（v2.37.1 → v2.37.2 → ...）担心 `~/.claude/cad_jury_config.json` 是否需迁移；以及 `CAD_JURY_DISABLE_LLM=1` kill switch 在各 patch 间行为是否变——需要 user-facing 版本承诺声明。

**核心约束：零代码改动 / 零行为变化** —— 全部是 user-visible 文档新加章节。

**北极星 5 gate**：零配置 ✓ / 稳定可靠 ✓（声明 schema 不变 + DISABLE_LLM 路径不变）/ 结果准确 ✓ / 傻瓜式 ✓（FAQ 解释 derived field）/ SW 装即用 ✓。

---

## 2. 范围

### 2.1 In-scope

| 文件 | 改动 | 行数 |
|---|---|---|
| `docs/cad-jury-config.md` | 加新章节 **§12 PHOTO3D_JURY_REPORT 输出字段语义**（f5）；插入位置 = 既有 §11 NAS warning 之后、附录 A 之前 | ~25-30 行 |
| 同上文件 | 加新章节 **§13 v2.37.x 版本承诺与不变量（user-facing）**（f6）；插入位置 = §12 之后、附录 A 之前 | ~15-20 行 |
| `docs/superpowers/reports/2026-05-14-v2-37-4-jury-config-docs-cleanup-retro.md`（新写）| retro 文档 | ~60 行 |

**总 diff ≈ 100-120 行（含 retro）**

### 2.2 Out-of-scope

- 任何 production code（`tools/jury/*.py`）改动
- 任何测试改动
- 任何 schema / config 字段加减
- CI workflow 改
- §12 残留 4 项（f1 max_tokens sunset / f2 memory inline 摘要 / f3 spec mini-glossary / f4 N≥50 批量成本）
- 改 cad-jury-config.md 既有 §1-§11 / 附录 A/B 字面（仅 append，不动既有）
- 更新 jury-loop-config.md（关联文档，与本 PR 无直接职责重叠）

---

## 3. 设计决策

### 3.1 D1 — 两节合并到 cad-jury-config.md，不另开新文档

**抉择**：在既有 `docs/cad-jury-config.md`（519 行，jury 唯一权威配置 doc）插入 §12 + §13。

**理由**：cad-jury-config.md line 14 自称"唯一权威配置说明；其他文档只引用本文档的字段定义"。schema 语义 / 不变量归这里最自然。

### 3.2 D2 — §12 f5 措辞侧重 derived vs measured 区分

**抉择**：§12 标题 = "PHOTO3D_JURY_REPORT 输出字段语义"；内容含：

1. **6 字段对照表**：明示 5 项 boolean (`geometry_preserved` / `material_consistent` / `photorealistic` / `no_extra_parts` / `no_missing_parts`) 是 **measured**（LLM 直接观察），`matches_spec` 是 **derived field**（基于 features_status aggregate）
2. **常见 FAQ**："5 项全 False 但 matches_spec=True 是 bug 吗？"——明确**不是**：是 `_make_needs_review_verdict` 早返回路径的兜底语义（缺 features_status 时 matches_spec 默认 True，spec §6 不变量 #11 向后兼容）

### 3.3 D3 — §13 f6 措辞侧重用户升级零迁移

**抉择**：§13 标题 = "v2.37.x 版本承诺与不变量（user-facing）"；3 条声明 + 边界澄清：

1. `schema_version=1` 在整个 v2.37.x patch 系列（v2.37.0 / v2.37.1 / v2.37.2 / v2.37.3 / v2.37.4 / 未来 v2.37.x）字段集不变
2. `CAD_JURY_DISABLE_LLM=1` 是 v2.37.x 唯一 env 形态 kill switch 路径（不增新 env）；用户也可通过删 / 改坏 `~/.claude/cad_jury_config.json` 间接禁用（jury 自动 silently skip），但这不是 env 路径
3. v2.37.0 起所有 jury sidecar / verdict 存档（含 v2.37.0 5-key / v2.37.2+ 6-key）反序列化到 v2.37.4 零迁移（5-key 自动按 True 兜底，v2.37.2 不变量 #11 锁定）

**边界澄清（layer 6 E2 + E8）**：
- **下限**：本承诺仅覆盖 v2.37.x 内升级；v2.36 ← → v2.37.x 跨 minor 兼容性 spec §3.2 D2（v2.37.0 加 matches_spec 维度）已设计向后兼容（feature_extractor + aggregate `.get` 兜底），但本承诺不显式覆盖；若用户从 v2.36 升 v2.37.4 应验证一次
- **上限**：本承诺**仅至 next major version（v2.38.0）前**有效；v2.38.0 可能引 breaking schema change，到时另立承诺

### 3.4 D4 — 章节编号插入位置

**抉择**：在 cad-jury-config.md 既有 `## 11. NAS / SMB share 警告` 之后、`## 附录 A：完整 cli flag 速查` 之前插入 §12 + §13。

**理由**：保持既有 §1-§11 编号不变 + 附录顺移不需重新编号（附录用字母 A/B 而非数字，不冲突）。

**行号引用约束（layer 6 E10）**：spec 内"line 14 / 402 / 408"等 cad-jury-config.md 行号为 spec 写时 snapshot；docs 可能在 PR 实施前被其它分支改而 shift。**plan task 0 必须实测重新定位** §11 末行号 + 附录 A 起始行号（grep `^## 11\.|^## 附录 A`），不假设 line 402/408 精确不变（v2.37.3 spec §13 R4 D2 教训复用）。

---

## 4. 验收标准

- **AC-1** `docs/cad-jury-config.md` 加 §12 PHOTO3D_JURY_REPORT 输出字段语义：≥ 1 张对照表（6 字段 measured/derived 标记）+ ≥ 1 段 FAQ 解释 needs_review 路径 matches_spec=True
- **AC-2** `docs/cad-jury-config.md` 加 §13 v2.37.x 版本承诺与不变量：3 条声明 explicit
- **AC-3** §13 grep strict 关键短语（plan task 0 + Task 1 验证）：
  - `grep -c "schema_version=1" docs/cad-jury-config.md` ≥ 2（既有 §3.1 表 + 新 §13）
  - `grep -c "CAD_JURY_DISABLE_LLM" docs/cad-jury-config.md` ≥ 1（新 §13）
  - `grep -cE "零迁移|不变量 #11" docs/cad-jury-config.md` ≥ 1（新 §13；**ERE 模式 `-E` 让 `|` 直接表 OR**；BRE `\|` 在 Windows grep 上不生效是 layer 6 E4 finding）
  - 或拆 2 grep 计数加总：`grep -c "零迁移" ... + grep -c "不变量 #11" ...` ≥ 1（implementer 选其一）
- **AC-4** retro 文档新写 ≥ 30 行；含完工 §12 f5+f6 标记 + 沉淀 lessons
- **AC-5** 全套件 PASS 不变（docs-only）3193 PASS / 0 regression
- **AC-6** CI 8/8 SUCCESS（含 mypy-strict / regression / 6 test matrix）
- **AC-7** 发 v2.37.4 patch tag + GitHub Release（升级路径模板复用 v2.37.3）

---

## 5. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| §12/§13 章节编号与既有附录冲突 | 低（既有 §1-§11 数字 + 附录 A/B 字母不冲突）| Task 0 grep `^## ` 实测确认 |
| 元测试 `tests/test_agents_md.py` 触发 | 极低（cad-jury-config.md 不进 AGENTS.md skill 表）| Task 元测试覆盖 |
| 用户读 §12 后误解 matches_spec 真假语义 | 中（措辞精度影响）| §12 FAQ 段必含"derived field / 缺数据默认 True / 不变量 #11" 关键短语 |
| 用户读 §13 后假设 v2.38.x 也不破坏 schema | 低（§13 显式说"v2.37.x patch 系列"限定）| §13 措辞含 "v2.37.x patch" 限定词；major version 行为不承诺 |

---

## 6. 不变量

1. 0 production code 改 / 0 测试改 / 0 schema 改 / 0 env-config 改
2. `docs/cad-jury-config.md` 既有 §1-§11 + 附录 A/B 字面零改动（仅 append 新 §12+§13）
3. v2.37.x 之前所有 spec 不变量保留（v2.37.2 §6 #1-#11 全部不动）
4. retro 文档独立新写不影响他人

---

## 7. 流程

```
brainstorming（本 spec）→ writing-plans → 2-3 task plan → execute
  ↓
docs 改动（pure documentation；无 RED phase）
  ↓
self-review → CI → squash merge → 等 main CI → tag v2.37.4 → Release
```

提交 2 commit：
1. `docs(jury-config): 加 §12 输出字段语义 + §13 版本承诺不变量（§12 f5+f6）` — cad-jury-config.md
2. `docs(v2-37-4): retro 沉淀` — retro doc

也可合 1 commit；plan 决定。中文 commit body + `docs(...):` prefix + Co-Authored-By。

### 7.1 Rollback 流程

pure docs PR rollback 极低风险。若发布后用户报"§12 措辞导致更困惑"或"§13 声明误导"：
- `git revert <v2.37.4 merge_sha>` 回退两节
- 发 v2.37.5 重写措辞
- GitHub Release UI 标 v2.37.4 "Pre-release" + ⚠️ banner（v2.37.2 D7 模式）

---

## 8. Plan 调查步（plan 第 0 task 跑）

1. `cd D:/Work/cad-spec-gen && git status --short && git log --oneline -3` — 验证 baseline main@`a5f8c95` clean
2. `python scripts/dev_sync.py --check` rc=0 — 既有镜像干净（虽然 docs 不进镜像，仍验证 baseline state）
3. `pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3` — baseline 503 PASS（v2.37.3 后）
4. `grep -nE "^## (11\.|附录 A)" docs/cad-jury-config.md` — 实测既有 §11 末行号 + 附录 A 起始行号（spec D4 插入点；**spec 内 line 14/402/408 是 snapshot，实测覆盖之**——layer 6 E10）
5. `grep -n "schema_version=1\|CAD_JURY_DISABLE_LLM\|matches_spec" docs/cad-jury-config.md` — 已有用法（避免 §13 与既有 §3 表重复定义）

---

## 9. Plan 必 cover 项（writing-plans inline 拾起）

- 每 commit 内含 docs 改动（无 canonical/mirror 同步需求；docs 不进 dev_sync）
- PR push 前 `git fetch origin main` 验证无并行改动（M1）
- baseline `dev_sync --check` rc=0 验证后再开 task（v2.37.3 Task 0 教训复用）
- AC-3 grep strict 关键短语**必须用 exclusion-zone 或 indent-anchor**（v2.37.3 AC-2b meta-drift 教训）：例如 `grep -c "schema_version=1" docs/cad-jury-config.md` 实际计数包含既有 §3.1 用法 + 新 §13 用法，预期 ≥2 是 inclusive

---

## 10. 不写代码 / 不进 plan 的事

- 不改 cad-jury-config.md 既有 §1-§11 字面
- 不新开独立文档（如 `docs/jury-output-fields.md` / `docs/jury-invariants.md`）
- 不动 jury-loop-config.md（关联但非本 PR scope）
- 不改 production code / 测试 / schema
- 不开 §12 残留 4 项（f1-f4）

---

## 11. v2.37.2 §12 follow-up 表（本 PR 闭合 2 项）

| # | 严重度 | 内容 | 状态 |
|---|---|---|---|
| F1 | LOW | mock helper 抽取 | closed v2.37.3 ✓ |
| F2 | LOW | line 105 注释扩 rationale | closed v2.37.3 ✓ |
| f1 | LOW | max_tokens sunset 条件 | 未闭合 |
| f2 | LOW | spec memory inline 摘要 | 未闭合 |
| f3 | LOW | spec mini-glossary | 未闭合 |
| f4 | LOW | N≥50 批量成本评估 | 未闭合 |
| **f5** | **LOW** | **user-visible 6-key debug 注释** | **closed v2.37.4**（本 PR）|
| **f6** | **LOW** | **schema 不变 + DISABLE_LLM no-op** | **closed v2.37.4**（本 PR）|

> **Note**：v2.37.3 retro 沉淀的 2 项新 §11 follow-up（AC grep exclusion-zone predicates 模板 + commit body 不自报 col 数字）**不属本 §12 表**（来源不同：layer 5 五角色 vs v2.37.3 实施期 meta-lesson）；独立轨道追踪在项目级 STATUS doc 或下次 cleanup PR 中决定时机。

---

## 12. 本 PR 自身 follow-up

| # | 严重度 | 内容 | 来源 |
|---|---|---|---|
| h1 | LOW | 若 jury-loop-config.md 也需 cross-link 到 §12/§13（用户读 loop_summary 后翻 cad-jury-config.md 找字段语义路径）| §10 Out-of-scope |
