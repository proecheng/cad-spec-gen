# cad-spec-gen 规划文档索引

本目录是 cad-spec-gen 的 Superpowers 计划、规格、报告和运行手册入口。
每轮工作结束后，先更新 [项目看板](../PROGRESS.md)，再按需补充本目录下的计划或报告。

## 最新更新

2026-05-05：Phase 2 常用模型库第五批已快进合并到 `main` 并通过主线复验：新增 [Common Model Library Batch 5 执行计划](plans/2026-05-05-common-model-library-batch-5.md)，按通用模型族准入清单加入方形法兰伺服电机、行星减速机、拖链段、DIN 导轨继电器模块、按钮/操作盒。合并前审查发现 route 别名可能拿到错误 fallback 尺寸、`interface relay` 路由和 adapter 模板 gate 不一致；现已修复，并把 route 别名的 template、real_dims、lookup dims 一致性纳入准入测试。当前总体能力进展约 84%，下一步是推送和清理 `.worktrees/common-model-library-batch-5`。详见 [项目看板](../PROGRESS.md)。

## 当前主入口

| 文档 | 用途 |
| --- | --- |
| [`../PROGRESS.md`](../PROGRESS.md) | 用户看板：当前走到哪、下一步做什么、哪些风险还在 |
| [`decisions.md`](decisions.md) | 已做过的重要架构/流程决策 |
| [`plans/2026-05-02-contract-driven-photo3d-pipeline.md`](plans/2026-05-02-contract-driven-photo3d-pipeline.md) | Photo3D 契约驱动管线方案 |
| [`plans/2026-05-02-generic-threaded-parts-pipeline.md`](plans/2026-05-02-generic-threaded-parts-pipeline.md) | 通用传动件/丝杠类零件管线归档计划 |
| [`plans/2026-05-04-enhancement-consistency-acceptance.md`](plans/2026-05-04-enhancement-consistency-acceptance.md) | 增强一致性验收执行计划 |
| [`plans/2026-05-04-build-artifact-backfill.md`](plans/2026-05-04-build-artifact-backfill.md) | build 恢复证据回填执行计划 |
| [`plans/2026-05-04-enhancement-summary-guide.md`](plans/2026-05-04-enhancement-summary-guide.md) | 增强交付摘要接入向导计划 |
| [`plans/2026-05-04-project-guide.md`](plans/2026-05-04-project-guide.md) | 新用户只读项目向导执行计划 |
| [`plans/2026-05-04-common-model-library-expansion.md`](plans/2026-05-04-common-model-library-expansion.md) | 常用模型库扩展第一批执行计划 |
| [`plans/2026-05-04-common-model-library-batch-2.md`](plans/2026-05-04-common-model-library-batch-2.md) | 常用模型库扩展第二批计划 |
| [`plans/2026-05-04-common-model-library-batch-3.md`](plans/2026-05-04-common-model-library-batch-3.md) | 常用模型库扩展第三批计划 |
| [`plans/2026-05-05-common-model-library-batch-4.md`](plans/2026-05-05-common-model-library-batch-4.md) | 常用模型库扩展第四批计划 |
| [`plans/2026-05-05-common-model-library-batch-5.md`](plans/2026-05-05-common-model-library-batch-5.md) | 常用模型库扩展第五批计划 |
| [`plans/2026-05-05-common-model-family-admission.md`](plans/2026-05-05-common-model-family-admission.md) | 通用模型族准入清单执行计划 |
| [`plans/2026-05-05-photo3d-interactive-handoff.md`](plans/2026-05-05-photo3d-interactive-handoff.md) | Photo3D 确认式 handoff 执行计划 |
| [`plans/2026-05-05-photo3d-provider-presets.md`](plans/2026-05-05-photo3d-provider-presets.md) | Photo3D 增强 provider preset 安全交接计划 |
| [`plans/2026-05-05-project-guide-provider-presets.md`](plans/2026-05-05-project-guide-provider-presets.md) | Project-guide provider preset 选择执行计划 |
| [`plans/2026-05-05-provider-choice-user-copy.md`](plans/2026-05-05-provider-choice-user-copy.md) | Provider preset 普通用户可读选项执行计划 |
| [`plans/2026-05-05-provider-ui-wizard.md`](plans/2026-05-05-provider-ui-wizard.md) | Provider UI wizard 执行计划 |
| [`plans/2026-05-05-provider-health-check.md`](plans/2026-05-05-provider-health-check.md) | Provider 配置健康检查执行计划 |
| [`plans/2026-05-05-enhance-check-handoff-loop.md`](plans/2026-05-05-enhance-check-handoff-loop.md) | 增强执行与验收闭环执行计划 |
| [`plans/2026-05-05-photo3d-delivery-pack.md`](plans/2026-05-05-photo3d-delivery-pack.md) | Photo3D 最终交付包执行计划 |
| [`plans/2026-05-05-render-visual-regression.md`](plans/2026-05-05-render-visual-regression.md) | Phase 4 渲染视觉/元件一致性门禁执行计划 |
| [`plans/2026-05-05-photo3d-quality-gate.md`](plans/2026-05-05-photo3d-quality-gate.md) | Phase 5/6 多视角照片级质量门禁执行计划 |
| [`plans/2026-05-05-render-quality-check.md`](plans/2026-05-05-render-quality-check.md) | Phase 4 Blender 预检与截图像素质量门禁执行计划 |
| [`plans/2026-05-05-semantic-material-quality-review.md`](plans/2026-05-05-semantic-material-quality-review.md) | Phase 5/6 语义/材质级增强质量复核执行计划 |
| [`runbooks/common-model-family-admission.md`](runbooks/common-model-family-admission.md) | 新模型族进入默认库的人工/大模型操作手册 |
| [`specs/common_model_family_admission.json`](specs/common_model_family_admission.json) | 新模型族准入的机读测试清单 |
| [`reports/model-quality-final-2026-05-02.md`](reports/model-quality-final-2026-05-02.md) | 模型质量最终审查摘要 |

## 目录约定

| 目录 | 内容 | 何时更新 |
| --- | --- | --- |
| `plans/` | 可执行计划、任务拆分、阶段方案 | 开始较大改动前；计划有重大变化时 |
| `specs/` | 设计规格、契约、接口说明 | 行为边界或数据结构稳定后 |
| `reports/` | 审查结果、质量报告、验收记录 | 完成审查、验收、回归或用户要求复盘时 |
| `runbooks/` | 可重复操作手册 | 涉及环境、CI、SolidWorks、Blender 或人工步骤时 |

## 每轮工作结束要做

1. 更新 [`../PROGRESS.md`](../PROGRESS.md)：
   - 最新提交或当前分支
   - 本轮完成项
   - 验证命令和结果
   - 下一步建议
   - 未跟踪或不应提交的文件
2. 如果新增或修改了计划、规格、报告、runbook，更新本索引。
3. 保持项目规则：
   - `python scripts/dev_sync.py --check`
   - `python -m pytest -q` 或与本轮范围匹配的测试
   - 不把运行时产物、客户数据、临时 worktree 缓存纳入提交

## 当前后续工作队列

| 顺序 | 所属 Phase | 工作 | 目标 |
| --- | --- | --- | --- |
| Done | Phase 5 ENHANCE | Provider preset UI wizard | 已新增 `PROJECT_GUIDE.json.provider_wizard`，把 `ordinary_user_options` 接成普通用户/UI/大模型可选、默认只读预览的增强后端选择向导 |
| Done | Phase 5 ENHANCE | Provider 配置健康检查 | 已新增 `provider_health`，判断本地/云增强 provider 是否可用，同时不泄漏 key、URL、endpoint 或 secret |
| Done | Phase 5 -> Phase 6 | 增强执行 + `enhance-check` 闭环 | provider 选择后由 `photo3d-handoff --confirm` 自动执行增强、验收复查和 `photo3d-run` 回读，输出 accepted/preview/blocked 和下一步 |
| Done | Phase 6 ANNOTATE / DELIVER | 最终交付包 | 已新增 `photo3d-deliver`，汇总增强图、标注图、源渲染、证据报告和用户摘要到 `DELIVERY_PACKAGE.json` |
| Done | Phase 4 RENDER | Blender 视觉回归和元件一致性检查（契约层） | 已新增 `render-visual-check`，通用防止渲染图少视角/少元件、旧 run 混用、视角证据漂移 |
| Done | Phase 5 -> Phase 6 | 多视角照片级质量验收（确定性契约层） | 已新增 `quality_summary`、逐视角 `quality_metrics` 和 `photo_quality_not_accepted`，防止低质量增强图进入最终交付 |
| Done | Phase 4 RENDER | Blender 环境预检和截图级回归（确定性像素层） | 已新增 `render-quality-check`，用 `RENDER_QUALITY_REPORT.json` 证明 Blender 预检、路径/hash/QA 和逐视角像素质量 |
| Done | Phase 5 -> Phase 6 | 语义/材质级增强质量复核 | 已新增 `enhance-review`、`ENHANCEMENT_REVIEW_REPORT.json.semantic_material_review` 和 `photo3d-deliver --require-semantic-review`，显式复核证据仍绑定 active run 和 source report hash |
| Done | Phase 2 CODEGEN | 常用模型库第五批 | 已按准入清单扩展五个跨产品高频外购件族，并通过第五批范围门禁 |
| 1 | Phase 2 CODEGEN | 推送并清理第五批 | 第五批已进入主线，下一步推送远端并清理本轮临时 worktree/分支 |
| 2 | Phase 2 -> Phase 6 | 模型质量报告用户化 | 让普通用户知道每个零件是真 STEP、库模板还是 fallback，并知道哪些需要复核 |
| 3 | Phase 1 -> Phase 6 | 新用户项目入口再简化 | 把全管线串成少提问、多确认的项目向导 |
| 4 | Phase 5 ENHANCE | 真实 AI backend adapter 准入 | `gpt-image-2-pro` 等新后端进入白名单前，先补配置隔离、同 run 验收和多视角一致性测试 |

历史已完成项保留在 [项目看板](../PROGRESS.md) 的验证记录和对应 `plans/` 文档中；本 README 只展示当前入口和后续队列，避免把进度读成流水账。
