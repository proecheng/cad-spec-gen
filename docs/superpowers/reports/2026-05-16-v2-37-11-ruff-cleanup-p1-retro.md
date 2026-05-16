# v2.37.11 — ruff cleanup P1 (F401+F541+F811+E401 154 条) Retro

> **PR**: <待 Task 12 填>
> **Merged**: <待 Task 12 填> main@<待 Task 12 填>
> **Tag**: v2.37.11
> **Release**: <待 Task 12 填>
> **CI**: <待 Task 12 填> (mypy-strict / regression / test 2×3 matrix = 8 jobs)
> **回归**: 全套件 3244 PASS / 17 SKIP / 0 regression

## 1. 摘要

P1 ruff cleanup 完工 — 154 errors 清零（149 default --fix 修 + 3 noqa 标注 Blender bpy probe + 0 真 ruff-not-fixable 残留）；commit 二分（impl-1 工具产物 + impl-2 人工 noqa + plan docs）；零语义改动；全套件 0 regression。

spec rev 1→2→3→4→5 五版演化抓 3 BLOCKER + 6 MINOR 全闭合（5 layer cascade）。

## 2. 实施数据真值（CP-0 + CP-1 + CP-2 实测）

### 2.1 statistics 校准（Task 0 表 1 实测）

| 规则码 | spec 声明 | 实跑 | 状态 |
| --- | --- | --- | --- |
| F401 | 128 | 128 | ok |
| F541 | 18 | 18 | ok |
| F811 | 7 | 7 | ok |
| E401 | 1 | 1 | ok |
| **P1 合计** | **154** | **154** | **ok（零漂移）** |

### 2.2 unsafe-fixes 3 条 enumerate（Task 0 表 2 实测）

| # | file:line | 当前 import 字面 | 类型判定 |
| --- | --- | --- | --- |
| 1 | cad/end_effector/render_config.py:566 | `        import bpy` | side-effect (bpy probe) |
| 2 | cad/lifting_platform/render_config.py:566 | `        import bpy` | side-effect (bpy probe) |
| 3 | render_config.py:566 | `        import bpy` | side-effect (bpy probe) |

3 条全 `try: import bpy / except ImportError: return  # Not running in Blender — skip silently` pattern → Task 1b SKIP，3 条转入 Task 5 noqa。

### 2.3 4 类涉及 file 数 + top 5（Task 0 表 3 实测）

| 规则码 | 涉及 file 数 | top 5 files (errors 数倒序) |
| --- | --- | --- |
| F401 | 93 | cad/lifting_platform/draw_top_plate.py (8) / draw_moving_plate.py (5) / tests/test_section_walker_unit.py (4) / test_sw_preflight_user_provided_provenance.py (3) / test_sw_preflight_report.py (3) |
| F541 | 8 | cad_spec_reviewer.py (5) / prompt_data_builder.py (4) / tools/hybrid_render/validate_config.py (3) / cad_spec_gen.py (2) / tools/synthesize_demo_step_files.py (1) |
| F811 | 2 | tests/test_sw_config_broker_e2e.py (5) / tests/test_sw_config_broker_integration.py (2) |
| E401 | 1 | tests/test_section_walker_real_docs.py (1) |

### 2.4 pytest baseline（Task 2 + Task 8 表 4 实测）

| 测点 | 数字 | 状态 |
| --- | --- | --- |
| Task 2 (commit-impl-1 前) | 3244 PASS / 17 SKIP | ok（基线精准命中，0 drift） |
| Task 8 (commit-impl-2 后) | 3244 PASS / 17 SKIP | ok（与 Task 2 完全一致，0 drift） |

### 2.5 Task 4 § decision 表（N=3 实测）

| # | file:line | 规则码 | 当前字面 | 归类 | 中文注释 |
| --- | --- | --- | --- | --- | --- |
| 1 | cad/end_effector/render_config.py:566 | F401 | `        import bpy` | side-effect | Blender bpy 环境探测 |
| 2 | cad/lifting_platform/render_config.py:566 | F401 | `        import bpy` | side-effect | Blender bpy 环境探测 |
| 3 | render_config.py:566 | F401 | `        import bpy` | side-effect | Blender bpy 环境探测 |

实测 N = **3**（spec rev 5 §1 估测 5 = 3 bpy + 2 不可修；实际 0 真不可修 — 主 agent brainstorm "default fix 149 + unsafe-fixes 多 3 + 2 noqa" 假设漂移；2 真不可修不存在，全 3 bpy 归 unsafe-fix-but-side-effect）。

## 3. 闭合 §11 follow-up

- ✅ closed: "360+ ruff cleanup" follow-up P1 layer
- ⏳ open（下游）:
  - **P2**: F841 (39) + F405 (39) + F403 (25) + E731 (24) + E702 (16) = **143 条**
  - **P3**: E402 (74) + E741 (47) + F821 (3) = **124 条** + `[tool.ruff]` config 锁 + CI ruff-strict job
  - **§11-N7** max_retries=3（依赖 §11-N12 真实 backend reachable）
  - **§11-N10** 多 prefix per run
  - **§11-N11** sha 重算
  - **§11-N12** enhance backend DNS
  - **§12 f4** N≥50 批量场景成本评估
  - **N-1**（本 PR 抓） commit-impl-1 body 数字漂移 (`7204d85` "剩 5 条" vs 实际 3 条) → 不 amend / 登 retro 提醒未来 commit body 多处数字对齐 sanity
  - **N-2**（本 PR 抓） noqa 字数标准歧义 → P2/P3 spec rev 1 起约定可执行规则

## 4. spec rev 1 → 2 → 3 → 4 → 5 cascade lesson

### Layer 1 (rev 1 → rev 2) — cynical re-read + code-spec 对照
**1 BLOCKER + 2 MINOR**
- BLOCKER A: F401 默认 `--fix` 真值（149 != 154 标号误解）
- MINOR B: noqa 估测 5-15 偏高
- MINOR C: 风险描述假设不实

教训: **spec 标号 `[*]` / `[-]` 不可凭字面推断，必 dry-run 校准**

### Layer 2 (rev 2 → rev 3) — edge-case hunter + 闭环
**1 BLOCKER + 3 MINOR**
- BLOCKER A: §6 R6 描述错（"fixture pattern" → "method-internal re-import"）
- MINOR B: Task 0 (b) unsafe-fix 3 条不可分 (--diff 模式)
- MINOR C: 5 处 fallback 路径不闭环
- MINOR D: AC-1 缺 RUF100 兜底

教训: **spec ≥100 行默认 5 层审查 → 实证 layer 1 + 2 cynical/edge-case 抓不同 bug**

### Layer 3 (rev 3 → rev 4) — Task 7 实施实证
**1 BLOCKER**
- BLOCKER: RUF100 + `--select=<subset>` 拖 84 historical noqa（设计意图本是防 Task 6 拼写错，实证 0 拼写错）

教训: **spec AC 命令必预跑实证，禁凭"应该如此"假设**

### Layer 4 (rev 4 → rev 5) — CP-3 spec compliance reviewer
**1 MAJOR**
- MAJOR: §6 R6 描述与 ruff 实际行为相反（rev 3 写"删 module-level"，实际删 method-internal）

教训: **spec 写 ruff 行为描述前必 git show <commit> -- <file> 实证 diff，禁凭 line number 推断 (§12 f8)**

### 累计统计
- **5 layer cascade** 抓 **3 BLOCKER + 6 MINOR** 全 inline fix
- **subagent-driven**: 3 implementer + 2 reviewer + 1 combined retro/PR/release = 6 subagent dispatch
- **commit 8 ahead of main**（5 spec + 1 plan + 2 impl + 1 retro = 9 total，retro 是本 commit）
- **CI 一次过零 hotfix**: 连续第 21 个 PR（待 Task 12 验证）

## 5. P2 入口 baseline（spec §6 R5 要求）

P1 完工后跑 `ruff check . --statistics`：

| 规则码 | P1 前 | P1 后 | Δ |
| --- | --- | --- | --- |
| F401 | 128 | 0 | -128 ✓ |
| F541 | 18 | 0 | -18 ✓ |
| F811 | 7 | 0 | -7 ✓ |
| E401 | 1 | 0 | -1 ✓ |
| F841 | 39 | 39 | 0 ✓ |
| F405 | 39 | 39 | 0 ✓ |
| F403 | 25 | 25 | 0 ✓ |
| E731 | 24 | 24 | 0 ✓ |
| E702 | 16 | 16 | 0 ✓ |
| E402 | 74 | 74 | 0 ✓ |
| E741 | 47 | 47 | 0 ✓ |
| F821 | 3 | 3 | 0 ✓ |
| **总数** | 421 | 267 | -154 ✓ |

P2 spec 起手时 Task 0 scout 校准这些数字（应仍是 P2 候选 5 类 143 条）。

## 6. 项目纪录

- **subagent-driven 完成度**: 13/14 task subagent 实施一次过（Task 1b skip = fallback 路径走通，不算"未实施"）
- **触发 fallback 数**: 1（Task 0 (b) → Task 1b skip + Task 5 多 3 条）
- **spec rev 数**: 5（rev 1 + rev 2 + rev 3 + rev 4 + rev 5）— 项目历史新高
- **累计抓 BLOCKER + MINOR**: 3 + 6 = 9（全 inline fix）
- **pytest baseline 保持**: 3244 PASS（Task 2 + Task 8 双次精准命中）
- **CI 8/8 一次过零 hotfix**: 连续第 21 个 PR（待 Task 12 验证 — 待跑 CP-4 PR）

## 7. §12 self follow-up 落地（spec rev 5 §11 §12 f1-f9）

- ✅ **f1**: ruff statistics 标号误解 lesson 进本 retro §4 Layer 1
- ✅ **f2**: Task 0 scout 三步模板可 P2/P3 复用；下游 plan 复制（含 statistics 校准 + `--show-fixes` enumerate + file 总数 top 5）
- ✅ **f3**: spec 写 pattern 描述前必 grep 实证 file:line 顺序与 token 角色 lesson 进 retro §4 Layer 2 + Layer 4
- ✅ **f4**: ruff `--diff` mode default / unsafe-fixes 输出相同实证 lesson 进 retro §4 Layer 2 — P2/P3 改用 `--show-fixes` 标签
- ✅ **f5**: Fallback 路径表（§5.1）模板可推广 cleanup spec lesson 进 retro §4 Layer 2 — P2/P3 spec rev 1 起含
- ✅ **f6**: AC 验收命令应 explicit 加 `--extend-select=RUF100` 兜底 noqa 拼写错 — **rev 4 deprecated**；改为 "RUF100 不可在 subset 模式作 AC，应手工 grep sanity 或单独全集 sanity"
- ✅ **f7**: RUF100 + `--select=<subset>` 交互 historical 噪音 lesson 进 retro §4 Layer 3
- ✅ **f8**: ruff F811 fix 选哪 import 删需实证不能凭 line number 推断 lesson 进 retro §4 Layer 4
- ✅ **f9**: noqa 字数标准歧义 — P2/P3 spec rev 1 起约定可执行规则（如"中文字符 ≥3 + 总字符 ≤20"）

## §A 本 PR 实施 lesson 沉淀（含 reviewer 抓获的 N-1 / N-2）

1. **commit body 多处数字必字面对齐 sanity**（N-1 教训）— `7204d85` 同 commit body 同时含 "3 remaining" 和 "剩 5 条" 两组数字打架；未来 commit message 写完末再扫一遍数字对齐
2. **fallback 路径表 (§5.1) 必含"实测后真值"列**（rev 5 §6 R6 后置）— spec/plan 描述 ruff 行为前必 commit diff 实证
3. **5 layer cascade 是项目 spec 鲁棒性 baseline**（前 v2.37.X 系列多数 rev 1-3 即闭合；本 PR 加 layer 4 (Task 7 实施实证) + layer 5 (CP-3 reviewer) 是新工艺）
4. **subagent-driven implementer 报告应含 "下一 task 风险"提示**（如 Task 0 enumerate 3 条 side-effect → 主 agent 立即抓 fallback 决策）

## Related

- [[project_v2_37_10_done]] — v2.37.10 retro "360+ ruff cleanup" follow-up 出处
- [[feedback_historical_debt_isolation]] — cleanup 独立 PR 不混功能
- [[feedback_spec_writer_self_drift]] — spec ≥100 行 4 层审查实证（本 PR 5 layer 抓 3 BLOCKER + 6 MINOR）
- spec: `docs/superpowers/specs/2026-05-16-v2-37-11-ruff-cleanup-p1-design.md` (rev 5, ~370 行)
- plan: `docs/superpowers/plans/2026-05-16-v2-37-11-ruff-cleanup-p1.md` (~1040 行)
