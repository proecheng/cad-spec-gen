# Jury matches_spec — 跨会话状态文档（v2.37 主线）

> 任何会话开工前先读这一份。

## 一、用大白话说我们在干嘛
让 photo3d-jury 看图后能说"设计文档里说应有的 4 条法兰悬臂，图里我看见了吗"。

## 二、5 条验收（spec §6 透传 + 本地补）
1. L1 parse 老 jury fixture 仍 PASS（向后兼容）
2. L2 aggregate 真值表 PASS
3. L3 feature_extractor mock + fail-safe + 12 限制 PASS
4. L4 retry 集成 mock PASS
5. e2e 跑（手动）：end_effector 现状 PASS + 故意 break 后 FAIL with anchor `flange_arms_4` missing

## 三、Task 进度表
| Task | 内容 | 状态 |
| --- | --- | --- |
| 0 | STATUS + grep verify | ✅ |
| 1 | verdict.py 扩 features_status + matches_spec aggregate | ✅ |
| 2 | verdict.py 加 RunVerdict + aggregate_run_verdict | ✅ |
| 3 | jury/jury_loop + 大套件回归扫 | ✅ |
| 4 | feature_extractor.py 核心 + 4 L3 test | ✅ |
| 5 | feature_extractor text/vision endpoint (F8) | ✅ |
| 6 | photo3d_jury extractor 启动调 + vision prompt 附 features + view_verdict.features_status | ✅ |
| 7 | photo3d_jury 写 jury_report.json (RunVerdict) | ⏳ |
| 8 | prompt_rewriter hint | ⏳ |
| 9 | jury_loop retry 集成 | ⏳ |
| 10 | delivery_pack TODO 写入 | ⏳ |
| 11 | cmd_enhance_check 透传 | ⏳ |
| 12 | L5 e2e marker fixture | ✅ |
| 13 | README 模板 + cad-tests 验收页 | ⏸ deferred — 等下次真 e2e run 时按 spec §11 模板补到外部 `D:\Work\cad-tests\<sub>\_README.md`（仓库外不入 git）|
| 14 | 最终验证 + 文档对齐 + retro | ✅ |

## 四、CURRENT TASK 指针
**全部完成 ✅** —— Tasks 0-12 + 14 全 ✅ / Task 13 deferred（外部目录）。

**最终套件：** 3180 passed / 17 skipped / 1 pre-existing fail（不在 scope，main 历史债）。

**Retro：** [`docs/superpowers/reports/2026-05-13-jury-matches-spec-retro.md`](reports/2026-05-13-jury-matches-spec-retro.md)。

**下一步等用户决策：**
1. push 分支 + 开 PR + 等 CI + merge + tag v2.37.0 + Release（标准化流程，需用户确认）
2. 或者本地 review 几个 commit 再决定

### Task 13 deferred 理由

Plan Step 3 字面：「cad-tests/ 是仓库外目录，本步只在外目录操作不入 git」。本 session 没跑真 e2e（没用 GEMINI_API_KEY 花钱跑 photo3d-jury 真 LLM），所以没有真实 matches_spec_features.json + jury_report 数据可填。spec §11 模板已写好备用；等下次真 e2e run 时按模板补到 `D:\Work\cad-tests\GISBOT\_README.md` + `D:\Work\cad-tests\jiehuo\_README.md` 即可。不阻断 v2.37 PR merge。

### Tasks 7-12 增量决策

- **Task 7**：扩展现 `PHOTO3D_JURY_REPORT.json` schema 加 3 字段（overall_matches_spec / per_view_failed_features / matches_spec_status）；schema_version 保持 1；不创建 plan 字面提到的不存在的 `cad/output/renders/jury_report.json`。
- **Task 8**：`prompt_rewriter.hint()` 选 module-level function（v1 朴素拼接无需 class）。
- **Task 9**：(A)+(B)+(C) 三 touch point 全实施 —— parse_view_verdict 决策升级 + single-view 接 feature cache + orchestrator 调 hint()。matches_spec_failed 进决策白名单（非 serious）；above_threshold 短路被 matches_spec_failed 覆盖（spec mismatch 与 photoreal_score 独立）。
- **Task 10**：simplest path —— `matches_spec_status == "fail"` 直接当 blocked at delivery；DELIVERY_PACKAGE.json status 新增 "blocked" 值；TODO 在 subsystem level（不是 run level）。
- **Task 11**：实现层选 `enhance_consistency.py::build_enhancement_report`（不是 cmd_enhance_check 本身）——quality_summary 在哪组装就在哪加 key。
- **Task 12**：3 placeholder skip cases；marker `requires_jury_loop_e2e` pyproject.toml:94 已配；CI 自动 skip + internal `pytest.skip()` 防误跑双保险。

### Task 6 选择 + 关键决策

- **CLI 新增 2 flag**：`--spec-md`（可 derive 默认 `cad/<subsystem>/CAD_SPEC.md`）+ `--design-doc`（无 convention 必须用户指明，缺则跳）
- **不动 `_JURY_PROMPT` 模板字面**：新增 `_build_view_prompt(view, features)` helper，features=0 时返回原 `_JURY_PROMPT`，向后兼容 v2.36 老 fixture
- **per-process extractor 调用**：新增 `_extract_features_for_run` helper 在 main() Layer 1 后调 1 次（不是 per-view）
- **text endpoint adapter**：`_FeatureExtractorClient` wrapper 复用 `jury_loop.llm_fallback._request_chat_text`（`noqa: SLF001`），不引入新配置项
- **view_verdict 透传 `features_status`**：Task 1 已 wire `ViewVerdict.features_status` 字段，本 task 把它写进 dict
- **fail-safe 双层防御**：spec_md/design_doc 不存在或缺 → 返 []；extractor 抛任何异常 → 兜底 []（与 feature_extractor 内自有 fail-safe 叠加）
- **测试策略**：4 个 `_build_view_prompt` 单元 + 4 个 `_extract_features_for_run` 单元 + 3 个 main() 集成断（extract 仅调 1 次 / view_verdict 含 features_status / 不传 design_doc 时 extract 不调）；11 PASS / jury+jury_loop 470 PASS / 0 regression

### Task 3 回归 sweep 发现 — pre-existing main 历史债（不阻断 jury 主线）

- 跑 `python -m pytest tests/ -q --timeout 60` 全套件 **1 fail（其他 547 PASS / 3 skipped）**
- Fail: `tests/test_backend_packaging_contract.py::test_contract_gate_tools_are_mirrored_for_packaged_installs`
- 根因：`tools/render_qa.py`（commit `46f7d9b` 改了 `MIN_OBJECT_OCCUPANCY=0.01→0.004` + 加 5 行注释）与 mirror `src/cad_spec_gen/data/tools/render_qa.py` 未同步
- archeology 确认：`git checkout main && pytest tests/test_backend_packaging_contract.py` 同 fail，**与 jury matches_spec scope 无关**
- 排除该 deselect 后跑全套件：**3135 passed / 14 skipped**（jury matches_spec Task 1+2 零 regression）
- 后续处理建议：单独 cleanup PR 把 `src/cad_spec_gen/data/tools/render_qa.py` 同步到 `tools/render_qa.py`，或问用户是否在本 PR 末顺手修。**默认 = 不扩大本 PR scope（memory `feedback_historical_debt_isolation.md`）**

### Task 2 选择 + 关键决策
- HEAD-UP 2：**不动** `_make_needs_review_verdict`；`aggregate_run_verdict` 用 `.get("matches_spec", True)` 自洽 back-compat 路径
- 额外加防御 `and "feature_id" in f` 在失败 features 过滤里（防 malformed feature dict KeyError）
- import 风格统一 `from tools.jury.verdict import ...`（plan 字面 `sys.path.insert + from jury.verdict` 是 plan-drift，已记录给后续 Task 用）

### Task 1 选择 + 关键决策
- **方案 A**（matches_spec 不进 `_REQUIRED_BOOL_KEYS`）选择理由：matches_spec 本是从 features_status aggregate 出来的派生字段，不是 LLM 直接 emit 的 bool；放进 `_REQUIRED_BOOL_KEYS` 会让所有不含该字段的老 fixture 触发 content_keys_mismatch → needs_review，silently break spec §6 验收 #1 + spec §8 不变量 #1。
- 额外加 1 个防御测试 `test_parse_view_verdict_back_compat_verdict_not_needs_review` 硬保障 verdict 不被升级 + content_keys_mismatch 不出现，防未来 plan-drift。
- features_status 非 list（如 dict/str）→ anomalies 加 "features_status_invalid"（serious 集合非空）→ verdict 升级 needs_review；matches_spec 退化为 True 不污染聚合。

## 五、不变量（spec §8 重述）
1. 不动 _REQUIRED_BOOL_KEYS 现有 5 个 key 语义
2. feature 抽取永远 per-process 不变 per-view
3. matches_spec FAIL 不阻断 enhance（走 retry）
4. fail-safe：extractor 挂 → matches_spec=true 不阻断
5. 不跑 cad_pipeline.py full

## 六、Task 0 grep 结果（F5 BLOCKER 前置验证 — PASS）

主 agent 预探查确认 spec §5.1 F5 假设成立：

- `tools/jury_loop/orchestrator.py` line 1-2 docstring：「单视角原子单元；多视角调度由 cmd_enhance（CP-7）管」
- `tools/jury_loop/orchestrator.py:192`：retry 触发条件 `if verdict.verdict == "needs_review": return (None, "needs_review")`
- `tools/jury_loop/cmd_enhance_hook.py:1`：「视角级 jury_loop hook」

→ Task 9 可按 spec §5.1 per-view retry 方案直接实施，无需升级决策。

## 七、Plan-drift 预发现（主 agent pre-flight 记录）

主 agent 预探查时发现 Task 8 中一处假设不准确：

- `tools/jury/prompt_rewriter.py` **不存在** —— plan 写 `Modify: tools/jury/prompt_rewriter.py` 实为 **Create**（plan 自注「如不存在则查实际路径」已预留）。

Task 8 执行时按 Create 走；后续 task 8 implementer 应优先把 hint() 接口直接放在新文件 `tools/jury/prompt_rewriter.py`。
