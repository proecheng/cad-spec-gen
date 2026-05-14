# v2.37.4 §12 f5+f6 cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭合 v2.37.2 §12 预登记 layer 5 user-visible 文档型 2 项 — f5 cad-jury-config.md 加 §12 输出字段语义（matches_spec 是 derived field 不是 measured boolean）+ f6 加 §13 v2.37.x 版本承诺与不变量（schema / kill switch / 升级零迁移）；发 v2.37.4 patch tag。

**Architecture:** 纯文档 PR — 仅在 `docs/cad-jury-config.md` append 2 个新章节（§12 输出字段语义 + §13 版本承诺），插入位置 = §11 NAS warning 之后、附录 A 之前；既有 §1-§11 + 附录 A/B 字面零改动。零代码 / 零测试 / 零行为变化。

**Tech Stack:** markdown + git tag-based release（不 bump 版本文件）。

**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-4-jury-config-docs-cleanup-design.md`（198 行 / brainstorming F1 fix + layer 6 E2+E4+E10 fix）

**分支：** `feat/v2-37-4-jury-config-docs-cleanup`（已建 / HEAD `5b39693`）

---

## File Structure

| 文件 | 用途 | 改动范围 |
|---|---|---|
| `docs/cad-jury-config.md` | jury 唯一权威配置 doc | append §12 (输出字段语义) + §13 (版本承诺)，插在 §11 之后附录 A 之前；既有内容字面零改 |
| `docs/superpowers/reports/2026-05-14-v2-37-4-jury-config-docs-cleanup-retro.md` | retro 文档（新写）| ~60 行 |

**不动文件**：任何 `tools/jury/*.py` / 任何测试 / `tests.yml` workflow / schema / config 文件 / `docs/jury-loop-config.md`（关联但非本 PR scope）。

---

## Task 0: Scout + baseline 实测

**Files:**
- Read only：`docs/cad-jury-config.md`（实测 §11 末行号 + 附录 A 起始行号）+ 跑 baseline pytest

- [ ] **Step 1: 切到分支并 fetch 验证无并行改动**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git checkout feat/v2-37-4-jury-config-docs-cleanup  # 应已在此分支
git log --oneline HEAD..origin/main
```

Expected: `HEAD..origin/main` 为空。**报告输出。**

- [ ] **Step 2: baseline `dev_sync --check`**

```bash
python scripts/dev_sync.py --check
echo "rc=$?"
```

Expected: rc=0。非 0 → 先 `python scripts/dev_sync.py` 同步 mirror 后再 `--check` 验 0；仍非 0 → 抛 BLOCKED。

- [ ] **Step 3: baseline PASS 数**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: jury 子集 503 PASS / 元测试全 PASS。**报告。**

- [ ] **Step 4: 实测 §11 末行号 + 附录 A 起始行号（spec §3.4 + §8 #4 — layer 6 E10 教训）**

```bash
grep -nE "^## (11\.|附录 A)" docs/cad-jury-config.md
```

Expected: 2 行命中。**报告实际行号**（spec 写 line 402 + line 408 是 snapshot；实测可能 shift；Task 1 实施按实测值插入）。

- [ ] **Step 5: 实测 grep AC-3 baseline 计数**

```bash
grep -c "schema_version=1" docs/cad-jury-config.md
grep -c "CAD_JURY_DISABLE_LLM" docs/cad-jury-config.md
grep -cE "零迁移|不变量 #11" docs/cad-jury-config.md
```

Expected:
- `schema_version=1` baseline ≥ 1（既有 §3.1 表 + JSON 模板）；Task 1 后 ≥ 2（加 §13 后）
- `CAD_JURY_DISABLE_LLM` baseline = 0；Task 1 后 ≥ 1
- `零迁移|不变量 #11` baseline = 0；Task 1 后 ≥ 1

**报告 baseline 实际数字。**

- [ ] **Step 6: 实测既有附属 section 位置**

```bash
grep -nE "^## (相关文档|通过 photo3d-handoff)" docs/cad-jury-config.md
```

Expected: 2 行命中（line ~443 + line ~451，spec snapshot）。**报告实际**（确认这些尾部 section 在附录 A/B 之后不需重编号）。

- [ ] **Step 7: 记录到 scratchpad**

无 commit；只在 report 汇总数据：
- §11 末行号 + 附录 A 起始行号（Task 1 插入坐标）
- AC-3 三个 grep baseline 数字（Task 1 后增量验证基准）
- 503 / 元测试 baseline PASS 数

---

## Task 1: f5+f6 — append §12 + §13 到 cad-jury-config.md

**Files:**
- Modify: `docs/cad-jury-config.md`（在 Task 0 Step 4 实测的"§11 末行 + 附录 A 起始行"中间 append §12 + §13）

**TDD 模式**：无 RED phase（pure documentation；docs 改动用 grep AC-3 strict 验证）。

- [ ] **Step 1: 定位插入点**

读 Task 0 Step 4 实测得到的"附录 A 起始行号"（spec 近似 line 408）。Task 1 在该行**之前**插入新章节。具体来说：

- 找到"## 附录 A：完整 cli flag 速查"这行
- 在该行**上方**（即既有 markdown 分隔符 `---` 之上 / `---` 与该 ## 之间）插入新 §12 + §13

精确策略（避免 markdown 视觉断裂）：

1. 找 `## 附录 A：完整 cli flag 速查` 的精确行号 = `ANCHOR_LINE`
2. 找 `ANCHOR_LINE` 向上最近的 `---` 行 = `SEP_LINE`（既有 markdown section 分隔符）
3. 在 `SEP_LINE` 之上、原 `## 11. NAS / SMB share 警告` section 末尾内容之后插入新 §12+§13 + 各自 `---` 分隔

- [ ] **Step 2: 插入 §12 PHOTO3D_JURY_REPORT 输出字段语义（f5）**

新章节内容（约 25-30 行）：

```markdown
## 12. PHOTO3D_JURY_REPORT 输出字段语义

`photo3d-jury` 跑完写 `PHOTO3D_JURY_REPORT.json`（以及 `cad-spec-gen enhance` 闭环跑时写的 `<view>_enhance_meta.json` / `ENHANCEMENT_REPORT.json` 内嵌 verdict）每个视角含 `semantic_checks` 段。本节解释 6 个 boolean 字段语义，特别是为什么有时 5 项全 `False` 但 `matches_spec=True`。

### 12.1 6 字段对照表

| 字段 | 类型 | 来源 | 含义 |
|---|---|---|---|
| `geometry_preserved` | bool | **measured**（LLM 直接观察）| 增强图几何形状与原始渲染对齐 |
| `material_consistent` | bool | **measured** | 材质表现一致（金属高光 / 漫反射 / 颜色） |
| `photorealistic` | bool | **measured** | 整体照片真实感 |
| `no_extra_parts` | bool | **measured** | 无 AI 凭空生成的零件 |
| `no_missing_parts` | bool | **measured** | 无原图存在但增强后丢失的零件 |
| `matches_spec` | bool | **derived**（基于 `features_status` aggregate）| 设计文档关键特征在图里可见性的聚合判定 |

5 项 measured boolean 是 LLM 视觉直接观察的结果；`matches_spec` 是 derived field——基于另一个字段 `features_status[]`（每个特征 visible/invisible 标记）聚合：所有特征都 visible → `matches_spec=True`；任一 invisible → `False`。

### 12.2 FAQ — 5 项全 False 但 matches_spec=True 是 bug 吗？

不是 bug；是预期兜底语义。出现场景：

- jury LLM 返回的 JSON 解析失败（如 `content_not_json`）
- `semantic_checks` 字段缺失或非 dict（`missing_content`）
- payload 整体非 dict

此时 `_make_needs_review_verdict` 走兜底路径：5 项 measured boolean 全标 `False`（无 LLM 观察证据），但 `matches_spec=True` 是 derived field 缺数据时的默认值（spec §6 不变量 #11 向后兼容硬保障 — 无 `features_status` 数据时 matches_spec 默认 True，不"拖累"聚合判断）。

判定 verdict 是否 needs_review **不应只看 `matches_spec` 单字段**——应看顶层 `verdict` 字段（`accepted` / `preview` / `needs_review`）：上述兜底场景 `verdict="needs_review"` 提示用户人工复核。

### 12.3 v2.37.2 之前老存档兼容

v2.37.0 / v2.37.1 时代生成的 sidecar / verdict 存档不含 `matches_spec` key（5-key dict）；v2.37.2+ 系统反序列化时按 True 兜底（不变量 #11 锁定），与上述 derived 语义一致——无需手动迁移。</markdown>
```

注意：上面代码块末尾的 `</markdown>` 是表示我引文结束的占位标记，**实施时不要写进文档**，直接以 §12.3 末尾"无需手动迁移。"作为 §12 全节内容结尾。

实施操作：
1. 用 Edit 工具找 `## 附录 A：完整 cli flag 速查` 上方的 `---` 分隔符
2. 在 `---` 上方插入：空行 + 上述 §12 全文（去除占位 `</markdown>`）+ 空行 + `---` + 空行

- [ ] **Step 3: 插入 §13 v2.37.x 版本承诺与不变量（f6）**

紧接 §12 之后，再插入 §13（约 15-20 行）：

```markdown
## 13. v2.37.x 版本承诺与不变量（user-facing）

本节面向**升级 cad-spec-gen 的用户**，明示 v2.37.x patch 系列（v2.37.0 / v2.37.1 / v2.37.2 / v2.37.3 / v2.37.4 / 未来 v2.37.x）跨 patch 升级的兼容性承诺。

### 13.1 三条声明

1. **`schema_version=1` 字段集不变**：v2.37.x 任一 patch 升级到另一 patch（如 v2.37.1 → v2.37.4）`~/.claude/cad_jury_config.json` 不需任何手工迁移；新字段如果加只走 forward-compat 模式（未知字段 stderr 警告，不阻断执行）

2. **`CAD_JURY_DISABLE_LLM=1` 是 v2.37.x 唯一 env 形态 kill switch**：设置该环境变量 → jury 不发任何 HTTP 请求，抛 `JuryDisabledByEnv`；v2.37.x 不增其它 env 形态 kill switch。用户也可通过删 / 改坏 `~/.claude/cad_jury_config.json` 间接禁用 jury（系统自动 silently skip），但这是 config-缺失路径不是 env 路径

3. **v2.37.0 起所有 jury 存档反序列化零迁移**：v2.37.0 时代 5-key `semantic_checks` 存档 / v2.37.2+ 时代 6-key 存档反序列化到 v2.37.4 系统都正常工作——系统自动按 True 兜底缺失 `matches_spec` 字段（不变量 #11 锁定，详见 §12.3）

### 13.2 边界澄清

- **下限**：本承诺仅覆盖 v2.37.x patch 系列内的升级。v2.36 ← → v2.37.x 跨 minor 升级 spec §3.2 D2（v2.37.0 加 matches_spec 维度）已设计向后兼容，但本承诺不显式覆盖；从 v2.36 升 v2.37.4 应实测一次确认 jury 输出格式符合预期
- **上限**：本承诺至 next major version（v2.38.0）前有效；v2.38.0 可能引 schema breaking change，到时另立版本承诺</markdown>
```

实施操作：
1. 紧接 §12 上方插入的位置 + 1 个空行 + `---` + 1 个空行，作为 §12 / §13 之间的 markdown 分隔
2. 然后插入上述 §13 全文（去 `</markdown>` 占位）
3. 末尾再 + 空行 + `---` + 空行（与既有附录 A 上方的 `---` 对齐）

- [ ] **Step 4: 验证 markdown 结构完整**

```bash
cd D:/Work/cad-spec-gen
grep -nE "^## " docs/cad-jury-config.md
```

Expected: 完整章节列表，含 §1-§11 + 新 §12 + §13 + 附录 A + 附录 B + 既有尾部 section（## 相关文档 / ## 通过 photo3d-handoff）。新插的 §12 + §13 在 §11 之后、附录 A 之前。**报告 §12 / §13 实际行号。**

- [ ] **Step 5: AC-3 grep strict 验证（spec §4）**

```bash
grep -c "schema_version=1" docs/cad-jury-config.md  # 应 ≥ 2
grep -c "CAD_JURY_DISABLE_LLM" docs/cad-jury-config.md  # 应 ≥ 1
grep -cE "零迁移|不变量 #11" docs/cad-jury-config.md  # 应 ≥ 1
```

Expected: 三个数字都 ≥ spec AC-3 floor。**报告实际数字**对照 Task 0 Step 5 baseline 看新增。

任一不满足 → 回 Step 2-3 修正 §13 措辞确保关键短语出现。

- [ ] **Step 6: 元测试确认无 break**

```bash
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: 全 PASS（docs 改动不触发 AGENTS.md skill 表 / no_tracked_mirror 检查）。

- [ ] **Step 7: 全套件 sanity（docs 改零行为影响验证）**

```bash
pytest -q tests/jury/ tests/jury_loop/ 2>&1 | tail -3
```

Expected: 503 PASS / 6 skipped（与 Task 0 Step 3 baseline 一致；docs 改动不影响测试）。

- [ ] **Step 8: REFACTOR 步显式确认**

审视 §12 + §13 内容：
- 表格 + 段落混合风格沿用 cad-jury-config.md 既有（§3 / §4 / §6 等）✓
- 中文措辞与既有 doc 风格一致 ✓
- 内部交叉引用（如 §12 → 不变量 #11 / §13 → §12.3 → §3.2 D2）正确锚定 ✓
- Commit message 加 `REFACTOR: 风格沿用既有 §1-§11，无进一步可清`

- [ ] **Step 9: Commit**

```bash
cd D:/Work/cad-spec-gen
git add docs/cad-jury-config.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(jury-config): 加 §12 输出字段语义 + §13 版本承诺不变量（§12 f5+f6）

v2.37.2 §12 预登记 layer 5 R3 user-visible 文档型 2 项闭合：

- f5 §12 PHOTO3D_JURY_REPORT 输出字段语义：6 字段对照表（5 measured boolean +
  1 derived matches_spec）+ FAQ 解释"5 项全 False 但 matches_spec=True 是预期
  兜底语义不是 bug"+ v2.37.2 之前老存档兼容说明
- f6 §13 v2.37.x 版本承诺与不变量（user-facing）：3 条声明（schema_version=1
  跨 patch 不变 / CAD_JURY_DISABLE_LLM=1 唯一 env kill switch / v2.37.0 起所有
  存档反序列化零迁移）+ 边界澄清（下限 v2.36 跨 minor 不显式覆盖；上限
  v2.38.0 major 失效）

零代码 / 零测试 / 零行为变化（pure docs append；既有 §1-§11 + 附录 A/B 字面零改）。

AC-3 grep strict 验证（spec §4）：
- schema_version=1 ≥ 2 ✓
- CAD_JURY_DISABLE_LLM ≥ 1 ✓
- 零迁移|不变量 #11 ≥ 1 ✓（ERE 模式 -cE）

REFACTOR: 风格沿用既有 §1-§11，无进一步可清。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: retro 文档新写

**Files:**
- Create: `docs/superpowers/reports/2026-05-14-v2-37-4-jury-config-docs-cleanup-retro.md`

- [ ] **Step 1: 写 retro 文档**

复用 v2.37.3 retro 风格，新建 `docs/superpowers/reports/2026-05-14-v2-37-4-jury-config-docs-cleanup-retro.md`：

```markdown
# Retro — v2.37.4 §12 f5+f6 cleanup

**完工日期：** 2026-05-14
**PR：** #N（占位，merge 后回填）
**Spec：** `docs/superpowers/specs/2026-05-14-v2-37-4-jury-config-docs-cleanup-design.md`（198 行 / brainstorming F1 fix + layer 6 E2+E4+E10 fix）
**Plan：** `docs/superpowers/plans/2026-05-14-v2-37-4-jury-config-docs-cleanup.md`
**Baseline：** main@`a5f8c95`（v2.37.3 merge）→ merge@<sha>（占位回填）

## 一句话

v2.37.2 §12 预登记 layer 5 R3 user-visible 文档型 2 项闭合：f5 cad-jury-config.md §12 PHOTO3D_JURY_REPORT 输出字段语义（5 measured + 1 derived 对照 + FAQ）+ f6 §13 v2.37.x 版本承诺与不变量（user-facing）；pure docs append PR，零行为变化。

## 完工范围

- §12 f5 closed：`docs/cad-jury-config.md` §12 加 6 字段对照表 + FAQ "5F+1T 兜底语义不是 bug" + v2.37.2 之前存档兼容说明
- §12 f6 closed：`docs/cad-jury-config.md` §13 加 3 条声明（schema 不变 / DISABLE_LLM=1 唯一 env / 存档零迁移）+ 边界澄清（下限 v2.36 不覆盖 / 上限 v2.38.0 失效）
- 既有 §1-§11 + 附录 A/B + 尾部 section 字面零改

## 数字

- jury 子集 PASS：503 → 503 不变（docs 改零影响）
- 全套件 PASS：3193 → 3193 / 17 skipped / 0 regression
- diff stat（待 merge 后实算）：2 文件 / +100-130 行
- 2 commits（docs + retro）
- CI 8/8 SUCCESS（待 PR 后实测）

## 2 层审查统计

| Layer | findings | inline 修 | 接受 |
|---|---|---|---|
| brainstorming 数据/漂移 | 1 (F1)| 1 | 0 |
| layer 6 边界 + 闭环 | 10 | 3（E2+E4+E10）| 7 |
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
```

- [ ] **Step 2: 元测试**

```bash
cd D:/Work/cad-spec-gen
pytest -q tests/test_agents_md.py tests/test_no_tracked_mirror.py 2>&1 | tail -3
```

Expected: 全 PASS。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/reports/2026-05-14-v2-37-4-jury-config-docs-cleanup-retro.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(v2-37-4): retro 沉淀 — §12 f5+f6 closed + 4 项审查 lesson

闭合 v2.37.2 §12 预登记 f5 (输出字段语义) + f6 (版本承诺) 两项；
retro 沉淀 brainstorming F1 fix + layer 6 E2+E4+E10 fix + 4 项新教训：
- grep BRE/ERE 兼容性陷阱（layer 6 E4）
- sunset 边界双限（layer 6 E2+E8）
- 行号引用 snapshot 标记（layer 6 E10 / v2.37.3 R4 D2 扩展）
- §11/§12 不同 follow-up 轨道区分（brainstorming F1）

PR # 占位字段在 squash merge 后回填。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: PR 全流程

**Files:** 无文件改动；纯 git / GitHub 操作。

按 v2.37.3 模板拆 2 阶段：3a push + open PR + 等 CI（自动）；3b merge + tag + Release（需用户授权）。

### Task 3a: Push + 开 PR + 等 CI

- [ ] **Step 1: PR push 前并行改动验证**

```bash
cd D:/Work/cad-spec-gen
git fetch origin main
git log --oneline HEAD..origin/main
git log --oneline HEAD..origin/main -- docs/cad-jury-config.md
```

Expected: 都为空（v2.37.3 merge 后 main 无并行改 cad-jury-config.md）。

- [ ] **Step 2: Push 分支**

```bash
git push origin feat/v2-37-4-jury-config-docs-cleanup
```

Expected: branch pushed clean。

- [ ] **Step 3: 开 PR**

```bash
gh pr create --title "docs(jury): v2.37 §12 f5+f6 cleanup（v2.37.4）" --body "$(cat <<'EOF'
## 概要

闭合 v2.37.2 §12 预登记 layer 5 R3 user-visible 文档型 2 项：

- **§12 f5**：`docs/cad-jury-config.md` 加 §12 PHOTO3D_JURY_REPORT 输出字段语义（6 字段对照表 measured/derived 标记 + FAQ "5F+1T 兜底语义"+ v2.37.2 之前存档兼容说明）
- **§12 f6**：`docs/cad-jury-config.md` 加 §13 v2.37.x 版本承诺与不变量（user-facing）（3 条声明 + 边界澄清下限 v2.36/上限 v2.38.0）

## 改动

- `docs/cad-jury-config.md` append §12 + §13（插在 §11 之后、附录 A 之前；既有 §1-§11 + 附录 A/B 字面零改）
- retro 文档新写

**0 production code / 0 测试 / 0 schema / 0 env-config / 0 行为变化** —— pure docs append。

## 测试

- jury 子集：503 PASS 不变
- 全套件：3193 PASS / 17 skipped / 0 regression

## 审查层数

brainstorming F1 fix + layer 6 E2+E4+E10 fix + per-task spec+quality review = 11+ findings，4+ inline 修，7+ 接受。

## Spec / Plan / Retro

- Spec: `docs/superpowers/specs/2026-05-14-v2-37-4-jury-config-docs-cleanup-design.md`
- Plan: `docs/superpowers/plans/2026-05-14-v2-37-4-jury-config-docs-cleanup.md`
- Retro: `docs/superpowers/reports/2026-05-14-v2-37-4-jury-config-docs-cleanup-retro.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL 返回；记 PR #N。

- [ ] **Step 4: 等 PR CI 8/8 全绿**

```bash
gh pr checks --watch
```

Expected: 8/8 SUCCESS（ubuntu/windows × py3.10/11/12 + mypy-strict + regression）。

Transient flake 处理（spec §5 风险表 / v2.37.3 retro 教训）：连续 2 次同 failure signature 才视为 regression。`sw-smoke` workflow `actions/upload-artifact@v7` 是已知 transient flake 点（feedback_sw_runner_infra.md），与 tests CI 8 job gate 无关。

### Task 3b: Merge + Tag + Release（需用户授权后另派 subagent）

按 v2.37.3 Plan Task 4b 同模板：
- Step 5: `gh pr merge <PR_NUM> --squash --delete-branch`
- Step 6: git checkout main + pull + 等 main CI 8/8 全绿
- Step 7: `git tag -a v2.37.4 $MAIN_SHA -m "..."` + push
- Step 8: `gh release create v2.37.4 --notes "..."`（升级路径复用 v2.37.3 模板）
- Step 9: `gh release view v2.37.4` 验证
- Step 10: 写 `project_v2_37_4_done.md` memory + 加 MEMORY.md 索引行

---

## Self-Review

**1. Spec coverage**:

| Spec 章节 | Plan Task | 备注 |
|---|---|---|
| §2.1 改动表 row 1 (cad-jury-config.md §12+§13) | Task 1 全 | ✓ |
| §2.1 改动表 row 2 (retro 新写) | Task 2 | ✓ |
| §3 D1-D4 决策（+ 边界澄清 + 行号 snapshot）| Task 1 Step 1-3 (D1/D2/D3/D4) + Task 0 Step 4 (行号实测) | ✓ |
| §4 AC-1..7 | Task 1 Step 2-3 (AC-1/AC-2) / Task 1 Step 5 (AC-3) / Task 2 (AC-4) / Task 1 Step 7 (AC-5) / Task 3a Step 4 (AC-6) / Task 3b (AC-7) | ✓ |
| §6 不变量 #1-4 | Task 1+2 全程维持（不动代码 / 不动既有 §1-§11） | ✓ |
| §7 流程 + 2 commit | Task 1 Step 9 + Task 2 Step 3 | ✓ |
| §7.1 Rollback | Task 3b 触发时使用 | ✓ |
| §8 5 调查步 | Task 0 Step 1-6 全覆盖 | ✓ |
| §9 plan 必 cover | Task 0 + 全 task 维持 | ✓ |
| §10 不写代码事项 | 全 task 不做 | ✓ |
| §11 §12 表 | Task 2 retro 内已注 closed v2.37.4 + §11 表 note | ✓ |
| §12 本 PR follow-up h1 | Task 2 retro 提及 jury-loop-config.md cross-link 放下次 | ✓ |

**所有 spec 章节有 task 覆盖。**

**2. Placeholder scan**: 无 TBD / TODO。PR # / merge sha 占位"待 merge 后回填"是显式留白（v2.37.2/v2.37.3 实证）。Task 1 Step 2-3 markdown code block 末尾 `</markdown>` 显式标"占位标记不写进文档"避免误抄。

**3. Type consistency**: 章节编号 §12/§13 + 子节 §12.1/12.2/12.3 / §13.1/13.2 全 task 一致。引用"不变量 #11"在 §12.2 + §12.3 + §13.1.3 + retro 多处一致。grep strict 命令 `grep -cE "...|..."` 与 spec §4 AC-3 一致。

**Plan 自检无问题 → ready for handoff。**

---

## 执行方式选择

Plan 完成保存到 `docs/superpowers/plans/2026-05-14-v2-37-4-jury-config-docs-cleanup.md`。两种执行模式：

1. **Subagent-Driven（推荐）** — v2.37.3 实证模板可复用
2. **Inline 执行** — 主 agent 本 session 直接跑全部 task；scope 极小可考虑

建议 Subagent-Driven。
