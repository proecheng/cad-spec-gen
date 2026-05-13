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
| 2-3 | verdict.py 扩 RunVerdict + summary | ⏳ |
| 4-5 | feature_extractor.py | ⏳ |
| 6-7 | photo3d_jury 整合 | ⏳ |
| 8 | prompt_rewriter hint | ⏳ |
| 9 | jury_loop retry 集成 | ⏳ |
| 10 | delivery_pack TODO 写入 | ⏳ |
| 11 | cmd_enhance_check 透传 | ⏳ |
| 12 | L5 e2e marker fixture | ⏳ |
| 13 | README 模板 + cad-tests 验收页 | ⏳ |
| 14 | 最终验证 + 文档对齐 + retro | ⏳ |

## 四、CURRENT TASK 指针
**Task 1 完成（方案 A：matches_spec 为 derived field，不进 `_REQUIRED_BOOL_KEYS`）；下 Task = Task 2 RunVerdict 多视角聚合。**

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
