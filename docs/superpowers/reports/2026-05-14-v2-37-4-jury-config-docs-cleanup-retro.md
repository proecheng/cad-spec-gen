# Retro — v2.37.4 §12 f5+f6 cleanup

**完工日期：** 2026-05-14
**PR：** #N（占位，merge 后回填）
**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-4-jury-config-docs-cleanup-design.md`（198 行 / brainstorming F1 fix + layer 6 E2+E4+E10 fix）
**Plan：** `docs/superpowers/plans/2026-05-14-v2-37-4-jury-config-docs-cleanup.md`（508 行 / 3 task）
**Baseline：** main@`a5f8c95`（v2.37.3 merge）→ merge@<sha>（占位回填）

## 一句话

v2.37.2 §12 预登记 layer 5 R3 user-visible 文档型 2 项闭合：f5 cad-jury-config.md §12 PHOTO3D_JURY_REPORT 输出字段语义（5 measured + 1 derived 对照 + FAQ）+ f6 §13 v2.37.x 版本承诺与不变量（user-facing）；pure docs append PR，零行为变化。

## 完工范围

- §12 f5 closed：`docs/cad-jury-config.md` §12 加 6 字段对照表 + FAQ "5F+matches_spec=True 兜底语义不是 bug" + v2.37.2 之前存档兼容说明
- §12 f6 closed：`docs/cad-jury-config.md` §13 加 3 条声明（schema 不变 / DISABLE_LLM=1 唯一 env / 存档零迁移）+ 边界澄清（下限 v2.36 不覆盖 / 上限 v2.38.0 失效）
- 既有 §1-§11 + 附录 A/B + 尾部 section 字面零改

## 数字

- jury 子集 PASS：503 → 503 不变（docs 改零影响）
- 元测试 PASS：5 → 5 不变
- 全套件 PASS：3193 → 3193 / 17 skipped / 0 regression
- diff stat：1 文件 / +54 行（Task 1 §12+§13） + retro 新 ~60 行（Task 2）
- §12 @ line 408 / §13 @ line 443 / 附录 A 下移 408→462
- AC-3 grep strict: schema_version=1 1→2 ✓ / CAD_JURY_DISABLE_LLM 0→1 ✓ / 零迁移|不变量 #11 0→3 ✓
- 3 commits（spec / plan / Task 1 docs + Task 2 retro）
- CI 8/8 SUCCESS（待 PR 后实测）

## 2 层 + per-task review 审查统计

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming 数据/漂移 | 1 (F1) | 1 | 0 |
| layer 6 边界 + 闭环 | 10 | 3（E2/E4/E10）| 7 |
| per-task spec+quality review × 2 task | 待补 | 待补 | 待补 |
| **总** | **11+** | **4+** | **7+** |

## 沉淀 lessons

1. **grep BRE/ERE 兼容性陷阱**：layer 6 E4 抓到 `grep -c "X\|Y"` 在 BRE / BSD grep / Windows MSYS grep 下 `\|` 不识别为 OR；必须 `grep -cE` 或拆 2 grep 计数加总。**lesson**：spec AC grep strict 使用 OR pattern 时必声明 `-E` 显式 ERE 模式或拆单 pattern。
2. **sunset 边界双限**：v2.37 系列承诺措辞必含下限（v2.36 跨 minor 是否覆盖）+ 上限（v2.38.0 major 失效）；省略易引读者推广误解。**lesson**：版本承诺 spec 必显式声明覆盖区间两端。
3. **行号引用 snapshot 标记**：spec 引用其它 doc 的 line number 时必声明"snapshot；plan task 0 实测重定位"（v2.37.3 R4 D2 教训"baseline drift"扩展到行号 drift）。
4. **§11/§12 不同 follow-up 轨道**：v2.37.x patch 的 PR-self §12 follow-up vs 项目级 §11 follow-up 是两个独立轨道；新增 follow-up 项必明确归哪个轨道避免读者混淆。

## §12 follow-up 残留（不阻断）

v2.37.2 spec §12 预登记 6 项闭合状态：
- F1 mock helper 抽取 → closed v2.37.3 ✓
- F2 line 105 注释扩 rationale → closed v2.37.3 ✓
- f1 max_tokens sunset → 未闭合
- f2 spec memory inline 摘要 → 未闭合
- f3 spec mini-glossary → 未闭合
- f4 N≥50 批量成本 → 未闭合
- f5 user-visible 6-key 注释 → closed v2.37.4 ✓
- f6 schema 不变 + DISABLE_LLM no-op → closed v2.37.4 ✓

剩 f1-f4 留独立 PR；本 PR 自身 follow-up（spec §12 h1）= jury-loop-config.md cross-link 到 cad-jury-config.md §12/§13（user 读 loop_summary 后翻字段语义路径），可放下次 cleanup。

## 下次类似 PR 优化

- spec AC grep OR pattern 必声明 `-cE` 或拆单 pattern
- 版本承诺 spec 必显式声明下限 + 上限
- spec 引其它 doc 行号必声明 snapshot + plan 实测
- pure docs PR 模板 = v2.37.4 模式（无 RED / grep strict AC / 风格沿用既有）

[[project-v2-37-3-done]] 上游 §12 F1+F2 + §11 follow-up 2 项追溯到 v2.37.3 retro。
[[project-v2-37-2-done]] 上游 §12 全表来源。
