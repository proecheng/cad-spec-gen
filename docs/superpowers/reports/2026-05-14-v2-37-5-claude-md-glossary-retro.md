# Retro — v2.37.5 §12 f3 cleanup (CLAUDE.md 项目术语 glossary)

**完工日期：** 2026-05-14
**PR：** #N（占位，merge 后回填）
**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-5-claude-md-glossary-design.md`（227 行 / brainstorming F1+F2+F3 fix）
**Plan：** `docs/superpowers/plans/2026-05-14-v2-37-5-claude-md-glossary.md`（494 行 / 3 task）
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
- diff stat：1 文件 / +30 行（CLAUDE.md 83→113）+ retro 新写 ~70 行
- 3 commits（spec + plan + Task 1 + Task 2）
- CI 8/8 SUCCESS（待 PR 后实测）

## 2 层 + per-task review 审查统计

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming 数据/漂移 | 3 (F1+F2+F3) | 3 | 0 |
| layer 6 边界 + 闭环 | 跳过（scope 极小，brainstorming 已覆盖主要边界）| 0 | 0 |
| per-task spec+quality review × 2 task | 0 阻断 | 0 | 0 |
| **总** | **3+** | **3+** | **0+** |

## 沉淀 lessons

1. **作者视角 vs 读者视角差异**（F1）：spec 写 git tracked 文档时易引绝对 user-specific 路径（作者本机真实），但读者（其他开发者/CI）看不到；必须加 disclaimer 或抽象。**lesson**：CLAUDE.md / README / AGENTS.md 等"全用户可见"文档禁绝对 home 路径，必抽象或加 disclaimer。
2. **memory 引用要选对 file**（F2）：spec 写时主 agent 凭印象引 memory file，但 memory 主旨与术语含义可能轻微错位（`feedback_subagent_cwd_drift.md` 主旨是 cwd 漂移不是 canonical-mirror 定义）。**lesson**：spec 写 memory 引用时主 agent 应 `head -5 <memory>` 验证主旨匹配。
3. **同一 lesson 跨 PR 措辞逐次精化**（F3）：v2.37.4 layer 6 E4 抓 grep BRE/ERE 兼容；v2.37.5 spec 仍把"BRE 不识别 `\|`"描述笼统；v2.37.5 fix 精化到"GNU grep BRE 支持但 BSD/MSYS BRE 不支持"。**lesson**：跨 PR 沉淀 lesson 引前一份 retro 措辞要 verbatim 避免再次模糊。
4. **mini-glossary 治理规则**（spec §3.1 末段）：术语 glossary 易膨胀；门槛 = 同一术语 ≥ 3 份 spec/plan/retro 重复出现才加。**lesson**：reference doc 类型 PR 必含治理规则防未来 scope creep。
5. **Task 0 scout 翻 spec 假设**（实施期发现）：spec §6 row 1 风险"CLAUDE.md → AGENTS.md regen 触发元测试 fail"被 Task 0 scout grep `dev_sync.py` 证伪——AGENTS.md 实际衍生自 `src/cad_spec_gen/data/skill.json`，与 CLAUDE.md 无关。**lesson**：spec 写时凭印象判定的"X → Y 衍生关系"风险，plan task 0 必 grep 实测证伪/证实，避免下游 task 走多余 mitigate 步骤。

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
- spec 假设的"X → Y 衍生关系"plan task 0 必 grep 实测证伪/证实

[[project-v2-37-4-done]] 上游 §12 f5+f6 + 4 项 layer 6 lessons 追溯。
[[project-v2-37-2-done]] 上游 §12 全表来源。
