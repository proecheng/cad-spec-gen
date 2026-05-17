# v2.37.13b P3 Retro — ruff cleanup P3 完工 + P1→P2→P3 系列收官 + v2.37.13a §11-N5 沉淀

**日期**：2026-05-17
**PR**：#95 (v2.37.13b) + #94 (v2.37.13a 集成沉淀)
**merge SHA**：5a59740 (P3) / a95ec47 (v2.37.13a)
**spec**：`docs/superpowers/specs/2026-05-17-v2-37-13b-ruff-cleanup-p3-design.md` (rev 1.3 / 777 行)
**plan**：`docs/superpowers/plans/2026-05-17-v2-37-13b-ruff-cleanup-p3.md` (1001 行 / 8 task)

---

## §1 摘要

P3 (v2.37.13b) 是 ruff cleanup 三批链的最后一批，清 E402 (74) + E741 (46) + F821 (3) 共 123 errors → 0。同步落地 `[tool.ruff]` config 锁 12 规则 + per-file-ignores 11 globs + CI ruff-strict job + 删 P2 26 处冗余 file-scoped noqa（§11-N1 真闭合）。

本 retro 集中沉淀：
1. **v2.37.13a §11-N5 latent bug triage**（PR #94）— 2 latent bug 决策 + characterization regression tests
2. **P1→P2→P3 三批 cleanup 系列收官表**（420 ruff codes 全清零）
3. **7 项工艺 lesson**（v2.37 系列复用）

---

## §2 关键数据

| 维度 | 数据 |
|---|---|
| P3 ruff errors 清零 | 123 → 0（E402 74 + E741 46 + F821 3） |
| E741 跨文件范围 | 8 个文件（spec drift fix：spec 假设 1 文件实际 8） |
| E741 文件分布 | jinja_primitive 35 + sw_parametric 1 + cq_to_dxf×3（2 文件） + cad_spec_extractors 2 + cad_spec_gen 3 + cad_spec_reviewer 2 |
| E741 决策表分布 | 39 length rename / 5 列表推导（layer/line） / 1 迭代变量（layer） / 1 数学保留 NOQA（惯性矩 I 公式） |
| [tool.ruff] config | 12 select + 11 per-file-ignores globs（含 `cad/**/*.py` 双星 + `adapters/parts/*.py` + `cad/end_effector/*.py` — 3 spec drift fix） |
| 删 P2 冗余 noqa | 26 处（25 cad scaffolds + 1 codegen 模板） |
| CI jobs | 9/9 SUCCESS（~7m 7s wall）— ruff-strict job 新加入 + 漂移防御 fixture |
| pytest baseline | 3239 → 3241 PASS（P3 +2 regression tests） |
| spec drift inline 修复 | 3 处（Task 0 scout 抓 2 + Task 3 抓 1），无升级 |
| 项目连续一次过 PR | 25 PR CI 一次过零 hotfix（项目纪录延续） |

---

## §3 §11 follow-up 状态

### 3.1 本 PR 系列闭合

| ID | 项目 | 状态 | 闭合方式 |
|---|---|---|---|
| **§11-N1** | P3 [tool.ruff] config + per-file-ignores 替 P2 noqa | ✅ 闭合 | commit 3+4（pyproject + 删 26 noqa） |
| **§11-N2** | P3 CI ruff-strict job | ✅ 闭合 | commit 5（.github/workflows/tests.yml +34 行） |
| **§11-N5** | F841 latent bug triage（2 dead code sites） | ✅ 闭合 | v2.37.13a PR #94（本 retro §4 集中沉淀） |
| **§11-N6** | noqa_lint.py reusable script | **关闭 as superseded** | pyproject config + CI gate 已替代，无需独立脚本 |

### 3.2 仍 open 项

| ID | 项目 | 触发条件 |
|---|---|---|
| **§11-N3** | dev_sync codegen regen marker（防止 codegen 生成的 file 漂移） | 下次新增几何零件类型触发 |
| **§11-N4** | git LFS 迁移（仓总尺寸 > 100 MB） | 仓总尺寸 > 100MB 触发 |

### 3.3 本 retro 新登记

| ID | 项目 | 推迟优先级 |
|---|---|---|
| **§11-N10** | E741 决策表分类后行号偏移容忍机制 — Task 2 实施时 ~5 行偏移在 AC-8b consistency check 内有效；P4 spec 可正式定义 ±5 行窗口约束 | P4 cleanup spec 起 |
| **§11-N11** | spec §5 AC-5 阈值公式与 P3 实际 scope 微误差（E741 实际跨 37 个变量 > AC-5 公式 30 门槛，实质 OK）→ 未来 cleanup spec AC-5 公式应按当批 ruff codes scope 重算，不抄前批 | 下次 cleanup spec rev 0 起 |
| **§11-N12** | Task 0 scout 应枚举 per-file-ignores glob 候选文件数（P3 实施期发现 spec §3.1.D 漏 `adapters/parts` + `cad/end_effector` 共 8 个 E402 / 11 文件） | ✅ **closed** — `tools/dev/lint_scope_audit.py` 落地（spec rev 1.3 / 4 轮审查 31 fix / 18 tests）；PR #<填> / merge SHA `<填>` / release tag `<填>`（命名 user 决策） |

---

## §4 v2.37.13a §11-N5 latent bug triage 集中沉淀

PR #94（merge a95ec47，tag v2.37.13a）triage 了 P2 §11-N5 中 F841 fallback W=11 ≥ 5 触发的 2 个 latent bug sites。

### Bug 1：`bd_warehouse_adapter.py:295` — 螺纹长度 `l` 死代码

**现象**：`l = float(m.group(2))` 解析 "M6×20" 长度字段后，`l` 从未被使用（csv_key 只用 `d`/`pitch`）。

**根因分析**：
- `M6×20` 格式 regex 的 group 2 捕获 length (`20`)，但 BD 仓库 csv_key 格式为 `"M6-1.0"`（仅直径+螺距），长度信息 by-design 丢弃
- group 2 的真实作用：验证输入为 `M{d}×{length}` 格式（拒绝裸 `M6`），是隐式格式校验器
- catalog yaml line 211 对照确认 by-design

**修法（Option A）**：
- 删 `l = float(m.group(2))` 死赋值
- 加注释 `# group 2 = 螺纹长度；by-design 不进 csv_key（仅格式校验，见 catalog yaml L211）`
- regex 保留不动（group 2 仍作格式验证器）

**行为保留**：M6×20 → csv_key `"M6-1.0"` 不变；length 信息丢弃 by-design。

**characterization test**：`test_bd_warehouse_metric_screw_drops_length_by_design` — pin csv_key 行为（防止将来有人"修"这个"bug"真的把长度加进去）。

### Bug 2：`fal_enhancer.py:173` — `_find_depth_for_png` 中 `exr_exact` 死代码

**现象**：`exr_exact = path / stem / (stem + "_depth.exr")` 及相关 `stem` 变量从未使用（函数实际靠 glob 模式匹配）。

**根因分析**：
- 原始设计可能意图"精确路径 + glob 两路"，但 glob 分支已全覆盖，精确路径分支从未被到达
- `_find_depth_for_png` 现行逻辑：glob `*_depth_*.exr` → 过滤 view_key → 取第一个

**修法**：
- 删 `stem` + `exr_exact` 死代码两行
- 重写 docstring：`"Single-step glob + view-key filter"` 替代原来误导性描述

**行为保留**：V1 PNG → V1_depth_*.exr 仍正确匹配；V2 排除逻辑不变。

**characterization test**：`test_fal_enhancer_find_depth_via_glob_view_key` — pin glob+view_key 行为（防止 dead code 删除引入真正的行为回归）。

### §11-N5 结案

F841 fallback W=11 ≥ 5 触发了 triage，triage 结论：
- 2 处 dead code 确认为 latent（非故意 NOQA）
- 修法均为"删死代码 + 补注释/docstring"，无行为变更
- characterization TDD 证实"no behavior change"
- §11-N5 正式关闭

---

## §5 P1 → P2 → v2.37.13a → P3 三批 cleanup 系列收官表

| 维度 | P1 v2.37.11 | P2 v2.37.12 | v2.37.13a | **P3 v2.37.13b** |
|---|---|---|---|---|
| **ruff codes** | F401+F541+F811+E401 | F841+F405+F403+E731+E702 | （清 2 noqa F841） | E402+E741+F821 |
| **errors 数量** | 154 | 143 | （dead code triage） | **123** |
| **修法** | safe `--fix` 双步自动修复 | manual + scope-aware noqa + 决策表 | characterization TDD | per-file-ignores + 按决策表 rename + TYPE_CHECKING |
| **spec rev** | 5（v2.37.11 P1） | 1.2 | 无 spec（TDD-only） | **1.3** |
| **spec 层级** | L5 cascade | L1-L5 cascade | self-review | **L1-L5 + user review × 2** |
| **spec fix 数** | 21 | 47 | 0（无 spec） | **30** |
| **spec 行数** | ~250 | 713 | （轻量） | **777** |
| **plan 行数** | ~400 | 902 | 497 | **1001** |
| **PR** | #90 | #92 | #94 | **#95** |
| **Release** | v2.37.11 | v2.37.12 | v2.37.13a | **v2.37.13b** |
| **工艺亮点** | safe-fix 工艺奠基 | scope-aware noqa + latent bug discovery | characterization TDD 验证"无行为变更" | config 锁 + per-file-ignores + CI gate 自动化 enforce |
| **CI 一次过** | ✅ | ✅ | ✅ | ✅（含新 ruff-strict） |
| **实施时长** | ~3h | ~5h（含 spec 写作） | ~1.5h | ~4h |

**系列总计**：420 ruff codes 全清零；项目无 ruff backlog；future 漂移由 CI ruff-strict gate 自动 enforce。

---

## §6 工艺 lesson 沉淀（v2.37 系列复用）

| ID | lesson |
|---|---|
| **L-1** | spec ≥ 500 行 5 层 cascade（L1 self / L2 code-spec 对照 / L3 dry-run / L4 adversarial / L5 实操可执行性）+ user review 多轮 = 大型 spec 必经流程 — P3 spec rev 1.3 经 3 轮累计 30 fix 实证 |
| **L-2** | scout-driven plan 修正 — Task 0 scout 抓 spec drift 是项目工艺（P3 抓 2 + Task 3 实施抓 1 = 3 spec drift inline 修复无升级） |
| **L-3** | per-file-ignores 双星 `cad/**/*.py` 比单星 `cad/lifting_platform/*.py` 等更稳 — future subsystem 增量自动 cover，无需手动更新 |
| **L-4** | CI ruff/mypy 等工具版本必 pin（与本地 .venv 一致）— ruff 0.15 → 0.16 行为差异历史教训（见 memory `feedback_preflight_mirror_ci.md`（摘要：pre-flight 必须完全模仿 CI 命令））|
| **L-5** | 决策表分类（E741 4 类 + 1 NOQA case）+ AC consistency check 脚本 = 比盲改稳健；数学保留 case（惯性矩 `I`）防 mechanical rename 降可读性 |
| **L-6** | subagent-driven 模型分级（haiku/sonnet/opus）= cost-quality 平衡 — P3 实证 opus 仅用于 Task 2（46 决策点高判断密度），haiku 覆盖机械 rename |
| **L-7** | tag-only release + 独立 retro PR + 集中 §11 闭合沉淀 = v2.37.X 系列标准工艺（见 memory `project_v2_31_1_packaging_cleanup.md`（摘要：v2.25+ tag-only release 模式））|

---

## §7 数据总结

| 维度 | 数据 |
|---|---|
| **P3 文档总计** | spec rev 1.3 (777) + plan (1001) + retro (~400) = ~2178 行 |
| **code diff** | ~120 行（8 file E741 rename + 3 file TYPE_CHECKING + pyproject 39 行 + 删 26 noqa + CI +34 行） |
| **git commits** | plan (1) + commit 1-5 + retro (1) = 7 commits |
| **PR** | #95（P3 主）+ 本 retro PR |
| **Release** | v2.37.13b（tag-only） |
| **ruff backlog** | 0（全清零；future 漂移由 CI ruff-strict gate enforce） |
| **pytest PASS** | 3239 → 3241（P3 +2 regression tests） |
| **CI 连续一次过** | 25 PR（项目纪录持续延续） |
| **工艺亮点** | 3 spec drift 全 inline 修复 + CI 9/9 一次过零 hotfix + 三批 cleanup 收官 |

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
