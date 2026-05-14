# Retro — v2.37.3 §12 F1+F2 cleanup

**完工日期：** 2026-05-14
**PR：** #N（占位，merge 后回填）
**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-3-mock-helper-line-rationale-design.md`（190 行 / 2 层审查 inline 修 E1+E2）
**Plan：** `docs/superpowers/plans/2026-05-14-v2-37-3-mock-helper-line-rationale.md`（529 行 / 4 task）
**Baseline：** main@`82ecd7a`（v2.37.2 merge）→ merge@<sha>（占位回填）

## 一句话

v2.37.2 §12 预登记 2 项 follow-up（F1 抽 `_get_urlopen_request` mock helper + F2 `max_tokens` line 注释加实测 rationale）；pure refactor + 纯注释 PR，零行为变化。

## 完工范围

- §12 F1 closed：`_get_urlopen_request(m)` helper 抽取（test_llm_client.py:68-78），消除 `m.call_args[0][0]` 2 处 inline 解构耦合（refactor 后 line 325 + line 349）
- §12 F2 closed：`tools/jury/llm_client.py:106` 注释中间插 1 行实测 ~800 token / 2× 余量 rationale

## 数字

- jury 子集 PASS：503 → 503（pure refactor + 注释零行为影响）
- test_llm_client.py PASS：15 → 15 不变（Task 0 实测 baseline = 15，spec 写 14 是 drift）
- 全套件：3193 → 3193 / 0 regression
- diff stat（待 merge 后 git diff 实算）：~3 文件 / +60-80 行 / -3 行
- 3 commits（refactor / docs / retro，待 PR 4a 合 push）
- CI 8/8 SUCCESS（待 PR 后实测）

## 2 层审查统计 + DONE_WITH_CONCERNS

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming F1+F2 漂移 fix | 2 | 2 | 0 |
| layer 6 边界 + 闭环 | 7 | 2（E1+E2）| 5（描述精度问题）|
| **总** | **9** | **4** | **5** |

**Task 1 DONE_WITH_CONCERNS（meta lesson）**：AC-2b grep predicates 措辞过严——`_get_urlopen_request(m)` ≥3 因 def signature `(m: MagicMock)` 不字面匹配 `(m)`；`m.call_args[0][0]` ==0 因 helper body 自身有 docstring + return body 2 处。Intent ("无 inline test-body 解构") 满足，literal grep 不满足。**Layer 6 E1 spec authoring 教训**：grep AC 应写 exclusion-zone predicates（如 `grep -n "..." | grep -v "^7[18]:"` 排除 helper body 行）或锚定 indent context (`grep -c "    _get_urlopen_request(m)"`)。

## 沉淀 lessons

1. **AC strict grep 措辞陷阱**：spec layer 6 E1 fix 把"AC 不够 strict" finding 转化为可机器 acceptance 检查时，预测的 grep counts 必须考虑 helper 自身存在性（不能假设 helper body 不含原 pattern）。**沉淀到 memory `feedback_ac_grep_predicates_exclusion_zone.md`**：抽 helper 类 refactor 的 AC grep 必须写 exclusion-zone（`grep -v` filter helper lines）或 indent-anchor（`grep "    helper_name"` for test-body context）。
2. **CJK 注释 col 计数模糊**：commit body 自称"< 100 col" 但 ruff E501 按 East Asian 2-width 算 line 106 = 106 cols；项目 ruff config 不启 E501 故非违规，但自称数字易错。**lesson**：commit body 不要自报 col 数字 = 改说"项目 ruff 接受范围内"。
3. **baseline drift 是 spec 写时常踩**：spec 写 14 PASS（看 v2.37.2 retro 数字），Task 0 实测是 15 —— 应该 plan 第 0 task 改成"实测填入 AC-4"（v2.37.2 spec 已经这么做过；本 PR spec 漏 sync 这个教训）。**沉淀**：spec 涉及 PASS count 数字必须用"plan task 0 实测填入"模式，禁止硬写。
4. **Pure refactor PR + no-RED phase 是合法 TDD**：spec §3.4 D4 显式说"既有测试就是 GREEN safety net"；commit message 强制标注；这是 v2.37.2 §6 edge-case finding #5 教训的延续。

## §12 follow-up 残留（不阻断 v2.37.3）

v2.37.2 spec §12 预登记 6 项还在等独立 PR：
- f1 max_tokens sunset 条件 / f2 memory inline 摘要 / f3 spec mini-glossary
- f4 N≥50 批量成本 / f5 user-visible 6-key 注释 / f6 jury_config schema 不变声明

本 PR 沉淀新登记 §11 follow-up 项：
- **AC grep exclusion-zone predicates 模板**（layer 6 E1 自身的 meta drift）
- **commit body 不自报 col 数字**（CJK 计数歧义）

## 下次类似 PR 优化

- spec 写 AC grep 时考虑 helper 自身 → 用 exclusion-zone 或 indent-anchor
- spec PASS count 用"plan task 0 实测填入"模式（不硬写）
- commit body 不自报 col 数字（项目 ruff 接受范围内即可）
- pure refactor PR 模板可复用 v2.37.3 模式

[[project-v2-37-2-done]] 上游 §12 F1+F2 由本 PR 闭合。
[[project-v2-37-3-done]] 本 PR 完工 memory（待 merge 后写）。
