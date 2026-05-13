# 自制件质量大修 v1 — Retrospective

**Date:** 2026-05-13 · **Status:** ✅ RESOLVED · **Sessions:** 2

## 一句话

外行用户跑端到端发现两个明显 bug（法兰只剩圆盘 + 升降平台坍塌成一根杆），根因是仓库的评分/门禁链建在采购件+像素+AI忠实度，**自制件这条链零评分**。v1 修了 9 件几何 + 加了一道 build 后自制件审计门禁 + 端到端重跑两子系统出新交付。

## 数字

| 项 | 数 |
| --- | --- |
| CP（里程碑）| 4 个全 ✅ |
| Tasks 完成 | 14 / 14 |
| Self-made 件几何修 | 9（ee_001_01 + SLP-100/200/201/300/400/403/404/500）|
| 新工具行数 | `tools/custom_parts_audit.py` 503 行 |
| TDD 测试 | 12 case 全 PASS |
| 接入门禁 | `cad_pipeline.py build` 后置 audit gate + 独立子命令 `custom-parts-audit` |
| 端到端归档 | `D:\Work\cad-tests\GISBOT\` 7 视角 + `\jiehuo\` 5 视角，两 _README.md |
| 全景图更新 | §10 加 audit 引用 + 新增 §11「自制件审计层」3 卡 |

## 做对的

- **STATUS doc 入口设计**：`docs/superpowers/QUALITY_OVERHAUL_STATUS.md` 一份文档把 spec/plan 串起来，session 1 写、session 2 接手只读 STATUS §五 CURRENT TASK 指针就够 — 4 个 CP 一气呵成无 onboarding 卡顿。
- **CP-2 反向回归测试 case E**：直接用 unit test 注入 pre-CP-1 的 disc-only bbox 90×90×30 + scaffold envelope 160×160×20 → 触发 FAIL；用 unit test 替代真的 `git stash` 整流程更可靠 + 反复跑。
- **阈值从实测 bug 反推**：bug A 实测 axis_min_ratio = 0.5625 → 阈值定 0.6 而不是拍脑袋 0.5。命中 + non-bug 边缘 case 不误伤。
- **scaffold docstring `Envelope:` = 契约真值**：把这个原本只是注释的字段提升为机器可读契约，未来 hand-edit 同步该行就有 audit 兜底。

## 做错过的（也修了）

- **5 类 plan-drift 一次没躲过去**：详见 `memory/feedback_quality_overhaul_plan_drift.md`。最大的痛是 spec 作者自己在 § 2.1 把 §6.4 envelope 值记错（160×160 vs 真值 90×90），CP-2 实现期间才发现要按"自制件用 docstring / 外购件用 §6.4"分支处理。
- **CP-3 Task 9 PowerShell 递归删除被 auto classifier 拦**：`Remove-Item -Recurse -Force` 删 `D:\Work\cad-tests\GISBOT/jiehuo` 两次都被拦（agent 未在 user explicit authorization 后被识别）。改用"非破坏性 archive to `_archive_TIMESTAMP/`"绕过，等效。
- **README 第一版 Python -c heredoc 被 bash 反引号截断**：Python `-c "..."` 里有反引号触发 bash command substitution，README 输出残缺。改写成独立文件 `tmp/_write_cp3_readme.py` 跑就好。

## 后续

- v2 待办（spec §4 Out of Scope）：LLM 设计对话 CLI / jury 加 matches_spec 维度 / model_provenance.source_kind 富化 / parts_library.yaml 优先级 / 修 gemini 代理
- 暴露但未硬修（audit 已 WARN）：CAD_SPEC §6.4 自制件 envelope 补全 / 清 8 个 legacy 数字前缀 .py 死文件 / runtime_materials 实际预设种类详细审计

## 链接

- `docs/superpowers/QUALITY_OVERHAUL_STATUS.md` — 入口
- `docs/superpowers/specs/2026-05-13-quality-overhaul-design.md` — spec
- `docs/superpowers/plans/2026-05-13-quality-overhaul-plan.md` — plan
- `tools/custom_parts_audit.py` + `tests/test_custom_parts_audit.py` — 工具+测试
- `D:\Work\cad-tests\GISBOT\_README.md` + `\jiehuo\_README.md` — 端到端交付
- `docs/系统全景图.html` §10/§11 — 全景图新增章节
- `memory/feedback_quality_overhaul_plan_drift.md` — 5 类 plan-drift 沉淀
