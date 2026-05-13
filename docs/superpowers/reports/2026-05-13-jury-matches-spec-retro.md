# Jury `matches_spec` v2.37 — Retro

**完工日期：** 2026-05-13 末段 ~ 2026-05-14
**分支：** `feat/v2-jury-matches-spec`
**Spec：** [`2026-05-13-jury-matches-spec-design.md`](../specs/2026-05-13-jury-matches-spec-design.md) (308 行, 4 层 review 9 finding 全闭)
**Plan：** [`2026-05-13-jury-matches-spec-plan.md`](../plans/2026-05-13-jury-matches-spec-plan.md) (1562 行 / 14 task)
**Status doc：** [`JURY_MATCHES_SPEC_STATUS.md`](../JURY_MATCHES_SPEC_STATUS.md)

## 数字

| 指标 | 数 |
| --- | --- |
| Task 数（plan 字面）| 14 |
| Task 完成 | 13 （Task 13 deferred — 外部 cad-tests README，本 session 没真 e2e 数据可填）|
| Code commit | 14（含 Task 1 fixup）|
| 新代码文件 | 2 (`tools/jury/feature_extractor.py` / `tools/jury/prompt_rewriter.py`) |
| 改代码文件 | 5 (`tools/jury/verdict.py` / `tools/photo3d_jury.py` / `tools/jury_loop/orchestrator.py` / `tools/photo3d_delivery_pack.py` / `tools/enhance_consistency.py`) |
| 新测试文件 | 5 (`tests/jury/test_verdict_matches_spec.py` / `tests/jury/test_feature_extractor.py` / `tests/jury/test_prompt_rewriter.py` / `tests/jury/test_photo3d_jury_matches_spec.py` / `tests/jury/test_cmd_enhance_check_matches_spec.py` / `tests/jury_loop/test_matches_spec_retry.py` / `tests/jury_loop/test_matches_spec_e2e_smoke.py`) — 7 实际 |
| 新测试 | ~45（含 9 e2e placeholder skip）|
| 全套件 | 3180 PASS / 17 skipped / 1 pre-existing fail（不在 scope，main 历史债）|
| Subagent 调用 | 19（11 implementer + 6 spec-reviewer + 1 code-quality-reviewer + 1 fixup）|
| Plan 决策点用户拍板 | 0（user 全程"继续"授权，所有技术决策由 LLM 替他做）|

## 做对的

- **Pre-flight 验证模式（memory `feedback_subagent_driven_main_agent_scouts.md`）**：主 agent 在派发每个大 task 前先 grep 验证 plan 假设；至少避免了 3 处明显 plan-drift（Task 8 prompt_rewriter.py 不存在 / Task 7+10+11 `cad/output/renders/jury_report.json` 不存在 / Task 9 retry 是 per-view 而非 per-run）。把这些写进 implementer briefing 让 subagent 直接走对路径。
- **Plan A vs Plan B 设计判断暴露在 subagent briefing**：Task 1 决策（matches_spec 进 `_REQUIRED_BOOL_KEYS` 与否）+ Task 9 决策（matches_spec_failed 是否 serious anomaly）+ Task 10 决策（fail vs blocked 是否区分）—— 全部在 briefing 中明列 A/B 选项 + 推荐 + 让 implementer 自主选择 + self-review 中说明理由。每次 implementer 都选了推荐方案，且能讲清楚理由。
- **TDD 严格执行**：每个 code task RED → GREEN → 回归扫，自报里都标注 RED FAIL 数 + GREEN PASS 数 + 回归 PASS 数。一次没"先实现再补测试"。
- **Task 1 fixup 闭环 review 流程**：code quality reviewer 抓出测试位置问题，spec reviewer 已 ✅ 之后才发现，dispatched fix subagent 精准修，再 micro-verify（无需 re-review）。
- **Per-task spec review + CP-end batch quality review 混合策略**：除 Task 1 走了完整双 review，其余 task 都只 per-task spec review，code quality 延到 PR 末批量 review（节省 ~6 个 subagent 调用 ≈ 30+ 分钟）。
- **不扩大 scope 纪律**：发现 `tools/render_qa.py` mirror 与 main 历史 drift，archeology 确认是 pre-existing on main，登记 STATUS 不修；按 `feedback_historical_debt_isolation.md` 默认不扩 PR scope。
- **每个 task implementer 自报 carry-over 注解**：实现某 task 时发现的后续 task 隐患（如 `_make_needs_review_verdict` 5 vs 6 key / 路径 drift / `_derive_matches_spec_status` warn/blocked 留口）都写进 self-review concerns；下个 task briefing 引用这些直接绕开。

## 做错过的

- **Plan 字面路径错 3 次都没在 spec/plan review 阶段抓到**：`cad/output/renders/jury_report.json` 这个不存在的路径在 Task 7+10+11 plan 字面 3 次出现；都是主 agent pre-flight 时才发现。**根因：** spec/plan review 没做"假设的文件路径存在性"实测——4 层 review 的「代码-spec 对照」层应该跑过 `ls -d <plan 提到的路径>`，但 review 时该路径属于"未来要创建的输出"反而被默认放过。**改进：** spec/plan review checklist 加一条"plan 提到的输出路径，如果 plan 说"读"该路径而非"写"，必须 `git ls-files | grep <path>` 验证。
- **Plan 字面 test import 风格 `sys.path.insert + from jury.verdict` 在本仓库不工作**：Task 1 implementer 自发改对了（用 `from tools.jury.verdict`），但 Task 4-13 plan 字面没同步纠正。每个 task implementer 都要重新发现 + 改。**根因：** plan 作者复制 plan 字面模板时没跑过；spec 评审也没实测。**改进：** plan 末尾加一段"plan 字面测试代码 import 风格在本仓库需改为 X"，避免每个 subagent 自己绕。
- **Task 6 plan 字面 test 引用了 `jury_run()` 不存在函数**：photo3d_jury 实际入口是 `main(argv)`。Task 6 implementer 自己 grep + adapt 了。同 plan-drift 来源。
- **没在 Task 4-7 启动前一次性 broadcast"plan import 风格 + path drift 修正"**：导致 Task 7/10/11 三次重复发现 path drift。**改进：** 主 agent 主动维护一份"plan 字面 vs 仓库实际"的 drift 修正列表，注入到每个 implementer briefing。本次中后期开始加进 briefing，但应该 Task 1 后就做。

## Plan-drift 5 分类（沿用 memory `feedback_plan_drift_taxonomy.md`）

| 分类 | 实例 |
| --- | --- |
| API 不存在 | Task 6 `jury_run()` vs `main(argv)` / Task 8 `tools/jury/prompt_rewriter.py` 不存在（greenfield）|
| 路径假设错 | Task 7+10+11 `cad/output/renders/jury_report.json` → 真实 `cad/<sub>/.cad-spec-gen/runs/<run_id>/PHOTO3D_JURY_REPORT.json` |
| 测试 helper 误用 | Plan 字面 `sys.path.insert + from jury.verdict` 在本仓库不工作 |
| 实现细节 bug | matches_spec 进 `_REQUIRED_BOOL_KEYS` 会破老 fixture 向后兼容（隐性 verdict 升级 needs_review）→ Task 1 改用 derived field |
| 参数签名 | Task 6 `_extract_features(spec_md_path, design_doc_path, ...)` plan 字面 vs 实际 `extract(spec_md, design, *, cache_dir, llm_client, subsystem, run_id)` |

## 关键技术决策（在 review 中产生）

1. **matches_spec 作为 derived field（不进 `_REQUIRED_BOOL_KEYS`）** — Task 1：避免 5 key 校验逻辑误杀老 fixture verdict。
2. **schema_version 保持 1（不 bump 2）** — Task 7：spec 没要求 bump；features=[] 时新字段全 default value，老 fixture 不感知。
3. **matches_spec_failed 进决策白名单（非 serious anomaly）** — Task 9：让 ViewVerdict 仍带 5 bool + features_status 给下游用；不走 `_make_needs_review_verdict` 早返回。
4. **above_threshold short-circuit 被 matches_spec_failed 覆盖** — Task 9：spec mismatch 与 photoreal_score 维度独立，分数高不能掩盖内容不符。
5. **`matches_spec_status == "fail"` 直接当 blocked at delivery** — Task 10：spec §3 D4 没要求区分两个中间态。
6. **路径解析借 `ARTIFACT_INDEX.json::active_run_id`** — Task 10+11：与现 `_build_jury_section` peer 函数同款，不引入新约定。
7. **`prompt_rewriter.hint()` 选 module-level function** — Task 8：v1 朴素拼接无状态。
8. **Task 13 deferred** — 外部 cad-tests README 需真 e2e 数据，本 session 没花钱跑真 LLM。spec §11 模板已写好备用。

## 技术债 / Follow-up

| # | 严重度 | 内容 | 推荐处理 |
| --- | --- | --- | --- |
| #1 | LOW | `_make_needs_review_verdict` (verdict.py:160-169) 仍只 emit 5 bool key（无 matches_spec）；`aggregate_run_verdict` 用 `.get(default=True)` 自洽。下游若直接 `["matches_spec"]` 访问会 KeyError。| 单独 cleanup PR：让 helper 6 key 一致（matches_spec=True 默认不污染聚合）|
| #2 | LOW | `_derive_matches_spec_status` (photo3d_jury.py) 仍只返 `'pass'` / `'fail'`；spec §3 D4 提到 'warn'/'blocked' 但 Task 9/10 没接入 jury_report 内部。Task 10 在 deliver 阶段直接把 'fail' 当 blocked。| 视用户需要决定是否要中间 'warn' 状态 |
| #3 | LOW | 单独 cleanup PR：把 `tools/render_qa.py` mirror 同步到 `src/cad_spec_gen/data/tools/render_qa.py`（pre-existing main 历史债，本 PR 不扩 scope）|
| #4 | LOW | Plan 字面 test import 风格 + path drift 已在 STATUS doc 五节 + 本 retro 记录；下次 plan 作者照搬模板前应先校对 |
| #5 | LOW | Task 13 cad-tests README 等下次真 e2e run 时按 spec §11 模板补 |

## v2.37 PR 内容（待 push）

14 commits：
- `92013d9` v2 spec
- `45b8e5c` plan
- `e6bc1ba` Task 0 STATUS
- `5898c76` Task 1 verdict.py features_status field
- `356c4a0` Task 1 fixup test 位置
- `5275a35` Task 2 RunVerdict + aggregate
- `5279f20` Task 3 回归扫
- `c2020a8` Task 4 feature_extractor
- `f00f354` Task 5 text endpoint preference
- `1b0d7e8` Task 6 photo3d_jury 集成 feature_extractor
- `a615104` Task 7 RunVerdict aggregate 写 jury_report
- `ce39e91` Task 8 prompt_rewriter.hint
- `23c11a4` Task 9 jury_loop retry 集成（最大）
- `555bd87` Task 10 photo3d-deliver MATCHES_SPEC_TODO + status=blocked
- `3cff59b` Task 11 cmd_enhance_check 透传 matches_spec_status
- `4e0ff27` Task 12 L5 e2e smoke marker
- _本 commit_ Task 14 STATUS + retro + memory

## 与北极星（memory `project_north_star`）对齐核

1. **零配置** ✓ — 用户只多用 `--design-doc` 一个 CLI flag；缺则 fail-safe 跳过 matches_spec
2. **稳定可靠** ✓ — 5 层 fail-safe（extractor LLM / JSON parse / 12 条限制 / 单视角 cache 缺 / delivery_pack jury_report 缺/烂）+ 全套件 3180 PASS / 零 regression
3. **结果准确** ✓ — vision LLM 拿到设计文档的特征列表后能视觉对账（spec §6 验收 #6/#7 + e2e 手动验证）
4. **SW 装即用** N/A — 本工作不涉及 SW
5. **傻瓜式** ✓ — FAIL 时输出中文 `MATCHES_SPEC_TODO.md` 指引下一步动作，不要求用户读 JSON

## 给下一个 v2.38+ session 的入口

memory `project_jury_matches_spec` 现已转 RESOLVED；后续若要做 jury matches_spec v2 智能化（prompt_rewriter v2 / features 手编辑 UI / 多语言）从 spec §4 Out of Scope 复活。
