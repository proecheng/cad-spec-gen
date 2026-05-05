# cad-spec-gen 规划文档索引

本目录是 cad-spec-gen 的 Superpowers 计划、规格、报告和运行手册入口。
每轮工作结束后，先更新 [项目看板](../PROGRESS.md)，再按需补充本目录下的计划或报告。

## 最新更新

2026-05-05：常用模型库扩展第三批已合并并推送到 `origin/main`，`codex/common-model-library-batch-3` worktree/分支已清理；新增 mounted bearing/support、BK/BF support block、KK linear module、valve manifold/FRL、DIN rail terminal/device B 级模板；补充显式分类、category-scoped 尺寸、默认库顺序和包络测试，并恢复精确成熟模板优先于新增通用族模板的规则。详见 [项目看板](../PROGRESS.md) 和 [第三批计划](plans/2026-05-04-common-model-library-batch-3.md)。

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

| 优先级 | 工作 | 目标 |
| --- | --- | --- |
| Done | 常用模型库扩展第三批 | 已合并并推送到 `origin/main`；已清理第三批 worktree/分支 |
| Done | 常用模型库扩展第二批 | 已合并并推送到 `origin/main`；已清理第二批 worktree/分支 |
| Done | 常用模型库扩展第一批 | 已合并到 `main` 并推送；默认库 motor/sensor/cable/pneumatic 显式路由和 LMxxUU、NEMA、圆柱接近传感器、线束可视段、紧凑气缸 B 级模板已可用 |
| Done | 更高层项目向导 | 已新增只读 `project-guide` / `PROJECT_GUIDE.json`，把 init/spec/codegen/build-render/photo3d-run 的下一步统一给普通用户和大模型 |
| Done | 第二批计划审查 | 已补误分类/误抢路由反例、默认库顺序、模板包络和路径/镜像边界 |
| P1 | 大模型交互动作 | 将 baseline 接受、增强、enhance-check 等确认点做成更清晰的下一步动作 |
| P2 | 文档包清理 | 将历史长计划保留在 `plans/`，把当前状态集中在 `docs/PROGRESS.md` |
