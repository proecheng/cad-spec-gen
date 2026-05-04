# cad-spec-gen 项目看板

> 本文件是每轮工作结束后给用户看的进度入口。
> 更新规则：每轮完成实现、审查、合并或重要验证后，更新「最新状态」「看板」「下一步建议」「验证记录」。

## 最新状态

| 字段 | 当前值 |
| --- | --- |
| 更新日期 | 2026-05-04 |
| 主分支 | `main` |
| 最新功能基线 | `547239c feat(photo3d): 增加显式基线接受流程` |
| 最近验证 | `python -m pytest -q` -> `1985 passed, 12 skipped, 14 warnings` |
| 同步检查 | `python scripts/dev_sync.py --check` -> 通过 |
| 当前未跟踪 | `docs/superpowers/plans/2026-05-02-generic-threaded-parts-pipeline.md` |

## 一句话结论

Photo3D 契约驱动出图主线已经合并到 `main`：当前管线能用 run_id、artifact index、产品图、模型契约、装配签名、渲染清单、变更范围和显式 accepted baseline 保护照片级 3D 出图，不再依赖“临时收紧”或扫描最新目录猜测产物。

## 看板

| 状态 | 工作项 | 目标 | 当前结果 | 下一步 |
| --- | --- | --- | --- | --- |
| Done | 通用传动/丝杠类零件模型路由 | 让常见传动件走模型库/参数化适配器，而不是每个设备手调 | 已新增 BOM 分类、参数化传动件、resolver 路由和测试 | 扩展更多常用机械类别 |
| Done | 模型库调用闭环 | 让 purchased/std parts 优先走用户 STEP、缓存、SolidWorks/Toolbox、bd_warehouse/PartCAD，再 fallback | 已有 `parts_library.yaml`、`geometry_report.json`、`model-audit` | 加强模型质量报告和用户导入体验 |
| Done | 产品图与路径契约 | 防止不同 run、不同目录、旧产物混用 | 已有 `PRODUCT_GRAPH.json`、`RUN_MANIFEST`、`ARTIFACT_INDEX.json`、path context | 把普通用户提示再做成更傻瓜式动作 |
| Done | Photo3D 契约门禁 | AI 增强前先证明 CAD 几何和渲染证据可信 | 已有 `photo3d` gate，输出 `PHOTO3D_REPORT.json`、`ACTION_PLAN.json`、`LLM_CONTEXT_PACK.json` | 接入默认用户流程，减少手工命令组合 |
| Done | 显式接受 baseline | 用户确认后才把当前 pass/warning run 作为漂移基线 | 已有 `accept-baseline`，记录 `accepted_baseline_run_id`，并校验报告路径、artifact 路径、文件哈希 | 后续在 UI/向导里暴露为“一键接受本轮基线” |
| Done | 项目看板和规划索引 | 每轮结束后给用户看当前进度、验证和下一步 | 新增 `docs/PROGRESS.md`、`docs/superpowers/README.md`，并在根 README 加入口 | 后续每轮结束更新本看板 |
| In Progress | 傻瓜式照片级 3D 流程 | 非编程用户只说需求，大模型按动作计划推进 | 已有动作计划和上下文包；流程文档已写入 skill | 做成更固定的 round-end 报告和下一步建议 |
| Planned | 常用模型库扩展 | 对其他设备也能复用，不围绕单个元件临时特判 | 已有 adapter/resolver 基础 | 建议按类别扩展：fastener、bearing、linear guide、motor、sensor、cable、pneumatic |
| Planned | 渲染/增强自动验收 | 照片级输出不仅生成，还能解释是否可交付 | 已有 enhancement status 概念和 render manifest | 建立增强前后的一致性评分、视角完整性、无遮挡检查 |
| Planned | 新用户项目向导 | 其他产品进入管线时尽量少问技术细节 | 现有 `cad_pipeline.py init/spec/codegen/photo3d` 可组合 | 设计 `cad_pipeline.py autopilot` 或 skill-level checklist |

## 当前能力边界

- CAD 阶段必须由结构化契约证明，AI 增强不能补 CAD 阶段缺失的零件、位置或数量。
- 第一次 `photo3d pass` 只是候选基线；用户确认后运行 `python cad_pipeline.py accept-baseline --subsystem <name>` 才成为 accepted baseline。
- `accept-baseline` 不扫描目录、不选择最新文件、不切换 `active_run_id`；它只接受同一 run 中路径和哈希都匹配的 `PHOTO3D_REPORT.json`。
- `warning` 可以接受为 baseline，但应在看板或报告里明确剩余风险。
- 被 `.gitignore` 忽略的 `src/cad_spec_gen/data/*` 镜像仍由 `dev_sync.py` 维护；每轮结束必须跑 `python scripts/dev_sync.py --check`。

## 下一步建议

1. 把本看板作为每轮交付固定入口：每轮结束先更新 `docs/PROGRESS.md`，再在最终回复里摘录「本轮完成 / 验证 / 下一步」。
2. 整理并决定是否纳入 `docs/superpowers/plans/2026-05-02-generic-threaded-parts-pipeline.md`。它当前是未跟踪文件。
3. 下一轮优先做“普通用户 Photo3D autopilot”：把 `photo3d -> 读报告 -> 执行动作计划 -> accept-baseline -> change-scope` 串成更少命令的用户流程。
4. 随后扩展常用模型库类别，目标是其他设备也能尽量自动得到可信几何，而不是对单个零件临时加规则。

## 验证记录

| 日期 | 命令 | 结果 |
| --- | --- | --- |
| 2026-05-04 | `python -m pytest -q` | `1985 passed, 12 skipped, 14 warnings` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_test_infra_contract.py tests\test_photo3d_accept_baseline.py tests\test_photo3d_user_flow.py -q` | `26 passed, 1 warning` |
| 2026-05-04 | `python -m pytest tests\test_agents_md.py tests\test_codex_skill_register.py tests\test_version_contract.py -q` | `7 passed, 1 warning` |

## 每轮结束模板

```text
本轮完成：
- ...

验证：
- ...

当前风险：
- ...

下一步建议：
1. ...
2. ...
```
