# TODO Triage Report — 2026-04-28

## 结论

当前 `main`（`7572a33`）上的 TODO 不能按裸文本一概判定为未完成。经本轮盘点：

- 模型库审查 5 条 P1/P2 finding 已关闭，见 `docs/superpowers/reports/review-findings-model-library-2026-04-28.md`。
- `docs/superpowers/plans/` 与 `docs/superpowers/specs/` 中的未勾选 checklist 是历史实施计划残留，不再作为当前活跃待办来源。
- 当前活跃待办收敛为 3 条 backlog，见本文“活跃 Backlog”。
- `cad/` 下生成样例脚手架仍有 TODO，占位本身不影响 skill 包和 CI，但如果这些样例要作为交付模型，需要进入 Backlog-3 清理。

## 盘点范围

本轮只统计 tracked 文件，避免 `.pytest_tmp_*`、本机缓存、测试临时目录造成误判。

| 类别 | 盘点结果 | 判定 |
|---|---:|---|
| `docs/superpowers/plans` unchecked checklist | 2661 条 | 历史计划残留；不作为活跃 TODO |
| `docs/superpowers/specs` unchecked checklist | 90 条 | 历史 spec 验收/风险记录；仅复制到活跃 Backlog 后才继续执行 |
| `docs/superpowers/reports` unchecked checklist | 0 条 | 当前报告无未闭环 checklist |
| `cad/` 生成样例 `TODO:` | 0 条 | TODO-B3 已清理；由 `tests/test_sample_scaffolds_clean.py` 守护 |
| 非 `cad/` 源码/模板 TODO | 保留 | Gate-2 机制、模板默认占位、设计文档模板占位按下文“不再作为活跃 TODO”处理 |

## 活跃 Backlog

| ID | 优先级 | 范围 | 当前状态 | 完成口径 |
|---|---|---|---|---|
| TODO-B1 | P2 | `adapters/parts/step_pool_adapter.py` 的 `spec.file_template` | 已完成：支持 `{normalize(name)}.step` 类模板查找；`file` 优先于 `file_template`；相对路径禁止 `../` 逃逸；新增 adapter/resolver 回归测试 | `tests/test_parts_adapters.py::TestStepPoolAdapter` 与 `tests/test_parts_resolver.py::TestResolverDispatch` 覆盖 |
| TODO-B2 | P1 | 真实 SolidWorks Toolbox/模型库端到端验收 | 已完成：`cad_pipeline.py sw-toolbox-e2e` 与 `sw-smoke full=true` gate 已通过 self-hosted Windows 真实 SolidWorks 验收 | GitHub run `25064438363` 通过，已随 v2.23.0 发布 |
| TODO-B3 | P2 | 生成模型质量与样例脚手架清理 | 已完成：`cad/` 旧样例裸 `TODO:` 清零；`axial_gap` 可从连接矩阵显式轴向间隙字段填充，并参与串联堆叠偏移计算 | `tests/test_connection_matrix_axial_gap.py`、`tests/test_gen_assembly.py`、`tests/test_sample_scaffolds_clean.py` 覆盖 |

## 明确不再作为活跃 TODO 的内容

| 来源 | 原因 | 处理方式 |
|---|---|---|
| `docs/superpowers/plans/*.md` 的 `- [ ]` | 这些文件是 agentic 执行过程记录，很多已由后续 commit、release、CI 或更高层方案替代 | 保留为历史记录；后续执行只看本文 Backlog 或新建 plan |
| `docs/superpowers/specs/*.md` 的验收 checklist | 多数是当时方案的验收草案和风险注记，不等于当前未完成任务 | 只有被复制到本文 Backlog 的条目继续执行 |
| `codegen/gen_parts.py` / `cad_pipeline.py` 中的 TODO scan 文案 | 这是 Gate-2 的产品机制：生成脚手架发现 TODO 时警告/软失败 | 保留 |
| `templates/part_module.py.j2` 中的 `TODO` 默认值 | 这是模板在信息不足时故意生成给用户补全的占位 | 保留；后续通过模型库/几何模板增强减少触发频率 |
| `cad_pipeline.py init` 生成的设计文档 `TODO` | 这是用户新建设计文档模板内容 | 保留 |
| `src/cad_spec_gen/data/*` 镜像中的 TODO 文案 | 由根目录 skill/command/template 同步生成 | 不直接修改；改源文件后跑 `scripts/dev_sync.py` |

## 当前审查闭环证据

最近一次完整验证已经覆盖：

```powershell
python scripts/dev_sync.py --check
python -m pytest tests/ -v --tb=short -m "not mypy" --cov=adapters.solidworks.sw_config_broker --cov=adapters.solidworks.sw_config_lists_cache --cov=adapters.solidworks.sw_list_configs_worker --cov-report=term-missing --cov-fail-under=95
python -m pytest tests/test_parts_resolver.py tests/test_parts_adapters.py -v
python -m mypy --platform=win32 adapters/solidworks/sw_config_broker.py
```

结果：

- 完整 pytest：`1508 passed, 14 skipped, 2 deselected`
- coverage：`95.26%`
- parts resolver kill switch：`83 passed, 2 skipped`
- mypy strict：`Success: no issues found`
- GitHub Actions：`tests` 与 `sw-smoke` 均为 success

## 后续执行建议

1. TODO-B1/TODO-B2/TODO-B3 均已闭环，后续只需在 PR/Release 中保留测试证据。
2. 若继续提升模型质量，下一轮应另开新 backlog，聚焦具体样例的几何重生成或真实 STEP 替换，而不是清理历史 TODO 文案。
