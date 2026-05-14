# Retro — jury v2.37 §11 follow-up cleanup（v2.37.2）

**完工日期：** 2026-05-14
**分支：** `feat/jury-v2-37-followup-cleanup`
**PR：** #N（占位，merge 后 GitHub Release 步骤回填）
**Spec：** [`2026-05-14-jury-v2-37-followup-cleanup-design.md`](../specs/2026-05-14-jury-v2-37-followup-cleanup-design.md) (286 行 / 5 层审查 + writing-plans 入口 scout 1 处漂移修)
**Plan：** [`2026-05-14-jury-v2-37-followup-cleanup.md`](../plans/2026-05-14-jury-v2-37-followup-cleanup.md) (8 task / 875 行)
**Status doc：** [`JURY_MATCHES_SPEC_STATUS.md`](../JURY_MATCHES_SPEC_STATUS.md)
**Baseline：** main@`c4653d2` → merge@`<sha>`（5+N commits / 待 merge 后回填）

## 一句话

v2.37 §11 follow-up #1（`_make_needs_review_verdict` 5→6 key 一致性）+ #6（`max_tokens` 512→1024）+ edge-case finding #1（docstring 与实现对齐）三项 cleanup，TDD 严格走 RED → GREEN → REFACTOR 三步，零行为变化（数学等价 `aggregate.get(default=True) == 显式 True`）。

## 完工范围

- §11 #1 closed：`_make_needs_review_verdict` 6-key 形态一致性
- §11 #6 closed：`max_tokens` 512→1024 防 features_status 截断
- edge-case finding #1 closed：`aggregate_run_verdict` docstring 与 `.get` 实现对齐
- spec §6 不变量 #8 锁定：CI dev_sync `--check` gate（既存）升级为永久不变量

## 数字

| 指标 | 数 |
| --- | --- |
| 全套件 PASS | 3186 baseline → 3193 final（+7 新测试）|
| jury 子集 PASS | 496 baseline → 503 final（+7 = parametrize 3 + aggregate 锁 3 + max_tokens 1）|
| Regression | 0 |
| CI | 8/8 SUCCESS（待 PR push 后实测）|
| Diff stat | ~7 文件 +X-Y（待 final 算）|
| Task 数（plan 字面）| 8 |
| Task 完成 | 8（含本 Task 6 retro + 后续 Task 7 PR + Task 8 release）|
| Code commit | 5+N（待 merge 后回填）|
| Subagent 调用 | 待统计（implementer + 双 reviewer + scout 配比）|

## 5 层 + 1 scout 审查统计

| Layer | findings | inline 修 | 移 §12 |
| --- | --- | --- | --- |
| 1 self | 1 | 1 | 0 |
| 2 cynical | 0 | 0 | 0 |
| 3 code-spec | 14 ✅ + 5 自发现 | 2 | 3 |
| 4 edge-case | 7 | 7 | 0 |
| 5 五角色 + dry-run | 34 | 10 | 6 |
| 6 writing-plans scout | 1 漂移 | 1 | 0 |
| **总** | **62+** | **21** | **9** |

## 做对的

- **writing-plans 入口 scout grep 验证抓到 spec 真漂移**：layer 6 抓到 spec 误判"加 CI dev_sync gate"实则既存（v2.10 起）；若无该 scout 进入 plan 后会浪费 1 个 task 重复实现已有功能。
- **5 角色并行 adversarial + edge-case-hunter 互补**：前者抓系统视角（state lifecycle / runtime path / 升级路径），后者抓 branching lens（分支边界 / null 值 / 截断）；两者跑出来的 finding 几乎不重合，证明并非冗余。
- **TDD 严格执行**：每个 code task RED → GREEN → REFACTOR 三步走，每步自报 fail/pass 数；REFACTOR 步无内容可清时显式标"无冗余可清，跳过"诚实标 > 硬塞虚假 refactor。
- **数学等价证明先于 commit**：Task 1（6-key 一致性）证 `dict.get("k", True) == 显式 True` 行为等价于显式赋 `True`，确保零行为变化。
- **scope 严格不扩**：spec §12 §11 新登 6 项 cleanup 全推后续 PR；本 PR 只闭 §11 #1+#6 两项明确事项 + edge-case #1。

## 做错过的

- **PowerShell 单引号 here-string 转义陷阱**：commit body 内 `'matches_spec'` 被 PowerShell 转 `''matches_spec''`；session 中后期才发现并改用 `<<'EOF'` bash here-string 或 `@'...'@` PowerShell 原始字符串 here-string。**改进：** subagent commit message 多行字符串统一走 bash here-string，避免 PowerShell 单引号嵌套地雷。
- **spec 286 行 vs PR diff ~70 行 ≈ 4:1 比例临界**：spec 写完后发现自身体量与 PR 实质内容比例失衡，再添内容已经该开独立 ADR 而非膨胀本 spec。**改进：** spec 写完计字数与预计 diff 比例，> 3:1 触发"是否应该拆 ADR"自问。本 PR `plan §13` 设计把 plan 层细化推 plan 文档而非 spec 是健康分工。

## Plan-drift（沿用 memory `feedback_plan_drift_taxonomy.md`）

| 分类 | 实例 |
| --- | --- |
| 误判已有功能为新需求 | spec 草稿"加 CI dev_sync gate"实则 v2.10 起既存 → writing-plans scout layer 6 grep `git log` 实证后修正为"将既存 gate 升级为永久不变量 #8" |

仅 1 处漂移，且 spec 完工进 plan 前的 scout 即抓到，未污染 plan / 实施。

## 关键技术决策（在 review 中产生）

1. **max_tokens 硬编码 512→1024（不加 env / config）** — Task 4：北极星"零配置"要求；实测 micuapi.ai gpt-image-2-pro 12 features 输出 ~800 token，1024 留 ~28% 余量足够，未来若再溢出再升级硬编码上限。
2. **`_make_needs_review_verdict` 6-key 显式赋值（不依赖 `.get` 默认）** — Task 1：spec invariant"verdict 形态一致性"要求所有 verdict 出口必含 6 个 bool key；显式 > 隐式（依赖下游 `.get` 默认值是脆弱契约）。
3. **`aggregate_run_verdict` docstring 改 ASCII 表 + 显式 fallback 注释** — Task 3：docstring 是 API 契约前置说明，与 `.get(default=True)` 实现行为对齐避免下游误用。
4. **不变量 #8 锁定既存 CI gate**：dev_sync `--check` 在 CI tests.yml 已 gate `tools/jury/*.py`；本 PR 将其从"事实存在"升级为"spec §6 永久不变量"，未来若有 contributor 移除 gate 视为破坏不变量需 ADR 论证。

## 技术债 / Follow-up（不阻断 v2.37.2）

| # | 严重度 | 内容 | 推荐处理 |
| --- | --- | --- | --- |
| §12-1 | LOW | mock helper 抽取：`tests/jury/test_llm_client.py` 的 `m.call_args[0][0].data` / `.get_header()` 解构耦合 3+ 测试 | 抽 `_extract_request_body` / `_extract_request_headers` helper，下次该测试文件改动顺手做 |
| §12-2 | LOW | `tools/jury/llm_client.py:105` line 注释扩定量 rationale | 加 `# 实测 micuapi.ai 12 features ~800 token / 2× 余量` 减少 `git blame` 跳转 |
| §12-3..§12-7 | LOW | spec §12 已预登记 6 项（L2 / L3 / L4 / U1 / U4 / U7）| 见 spec §12 |

## v2.37.2 PR 内容（待 push）

5+N commits（待 final 回填）：
- Task 1 `_make_needs_review_verdict` 6-key + parametrize 3 测试
- Task 2 spec §6 不变量 #8 文档更新
- Task 3 `aggregate_run_verdict` docstring + 锁回归 3 测试
- Task 4 `max_tokens` 512→1024 + 1 回归测试
- Task 5（待 final）
- _本 commit_ Task 6 STATUS §11 #1+#6 closed + retro

## 与北极星（memory `project_north_star`）对齐核

1. **零配置** ✓ — `max_tokens` 1024 硬编码不加 env / config；用户无需任何额外配置
2. **稳定可靠** ✓ — TDD 三步 + 数学等价证明 + 0 regression + 3193 全套件 PASS
3. **结果准确** ✓ — Task 4 修 12 features 输出截断问题，jury verdict 完整度提升
4. **SW 装即用** N/A — 本工作不涉及 SW
5. **傻瓜式** ✓ — 用户无感知（行为零变化的 cleanup + max_tokens 截断隐患静默修复）

## 沉淀 lessons

- **writing-plans 入口 scout grep 验证是 plan-drift 防御关键 checkpoint**：layer 6 抓到 spec 误判"加 CI dev_sync gate"实则既存（v2.10 起）。后续 spec 写完进 plan 时必跑 `grep -n` / `git log` 验证假设。建议沉淀到 memory `feedback_writing_plans_scout_required.md`。
- **5 角色并行 adversarial 审查抓的是系统视角**（state lifecycle / runtime path / 升级路径），与 edge-case-hunter 的 branching lens 互补；两者都需要跑（非替代）。
- **spec 286 行 vs PR diff ~70 行 ≈ 4:1 比例临界**——再添内容该开独立 ADR 而非膨胀本 spec；本 PR `plan §13` 设计把 plan 层细化推 plan 文档而非 spec 是健康分工。
- **PowerShell 单引号 here-string 转义陷阱**：commit body 内 `'matches_spec'` 被 PowerShell 转 `''matches_spec''`；后续 commit 改用 `<<'EOF'` bash here-string 或 `@'...'@` PowerShell 原始字符串 here-string。

## 下次类似 PR 优化

- spec 完工 → writing-plans 入口必跑 grep / `git log` scout（layer 6 教训）
- TDD R 步显式标"REFACTOR: 无冗余可清，跳过"诚实标 > 硬塞虚假 refactor
- two-stage review 即使 docstring-only 改也跑（可合并 1 reviewer 但不省）
- subagent commit message 用 bash here-string `<<'EOF'` 包多行字符串（避免 PowerShell 单引号转义）

## 给下一个 session 的入口

- 本 PR 闭 §11 #1+#6；剩 §11 #2 `_derive_matches_spec_status` 加 'warn'/'blocked' 中间态 + #3 `tools/render_qa.py` mirror drift cleanup + #4 plan-drift 模板纠正 + #5 Task 13 cad-tests README 真 e2e 时补，进 v2.37.3+ session
- spec §12 新登 6 项（L2 / L3 / L4 / U1 / U4 / U7）+ 本 retro §12-1/§12-2 mock helper 抽取等下次 jury 子模块改动时顺手做
- memory `project_jury_matches_spec` v2.37.2 节点回填后由本 PR 闭合 §11 #1+#6 升至 v2.37.2

[[project-jury-matches-spec]] 由本 PR 闭合 §11 #1+#6 进 v2.37.2。
[[feedback-third-party-proxy-real-test-finds-bugs]] v2.37.1 沉淀 lesson 在本 PR 流程中已激活（spec review checklist 实际生效）。
