# cad-spec-gen 项目看板

> 本文件是每轮工作结束后给用户看的进度入口。
> 更新规则：每轮完成实现、审查、合并或重要验证后，更新「最新状态」「看板」「下一步建议」「验证记录」。

## 最新状态

| 字段 | 当前值 |
| --- | --- |
| 更新日期 | 2026-05-04 |
| 主分支 | `main` |
| 最新功能基线 | `feat(photo3d): 接入增强交付摘要` |
| 最新合并提交 | `b540400 merge: 合并 build 恢复证据回填` |
| 最新归档计划提交 | `9ed3280 docs(project): 归档通用传动件计划` |
| 最近验证 | 本分支 `python -m pytest -q` -> `2048 passed, 18 skipped, 10 warnings` |
| 同步检查 | `python scripts/dev_sync.py --check` -> 通过 |
| 当前未跟踪 | 无 |

## 一句话结论

Photo3D 契约驱动出图主线已进入“多轮向导 + 报告 + 确认执行 + run-aware 恢复 + build 证据回填 + 执行后自动回看下一步 + 增强后交付摘要”阶段：当前管线能用 run_id、artifact index、产品图、模型契约、装配签名、装配报告、装配 GLB/STEP、渲染清单、变更范围、显式 accepted baseline、`PHOTO3D_RUN.json`、`PHOTO3D_AUTOPILOT.json`、`ACTION_PLAN.json`、`PHOTO3D_ACTION_RUN.json` 和 `ENHANCEMENT_REPORT.json` 保护照片级 3D 出图；普通用户优先运行 `photo3d-run`，到 `ready_for_enhancement` 后显式运行 `enhance`，再用 `enhance-check --dir <render_dir>` 生成 `accepted/preview/blocked` 交付状态，随后 `photo3d-run` 会读取当前 run 的报告并给出“可交付/仅预览/阻断”的统一下一步。

## 看板

| 状态 | 工作项 | 目标 | 当前结果 | 下一步 |
| --- | --- | --- | --- | --- |
| Done | 通用传动/丝杠类零件模型路由 | 让常见传动件走模型库/参数化适配器，而不是每个设备手调 | 已新增 BOM 分类、参数化传动件、resolver 路由和测试 | 扩展更多常用机械类别 |
| Done | 模型库调用闭环 | 让 purchased/std parts 优先走用户 STEP、缓存、SolidWorks/Toolbox、bd_warehouse/PartCAD，再 fallback | 已有 `parts_library.yaml`、`geometry_report.json`、`model-audit` | 加强模型质量报告和用户导入体验 |
| Done | 产品图与路径契约 | 防止不同 run、不同目录、旧产物混用 | 已有 `PRODUCT_GRAPH.json`、`RUN_MANIFEST`、`ARTIFACT_INDEX.json`、path context | 把普通用户提示再做成更傻瓜式动作 |
| Done | Photo3D 契约门禁 | AI 增强前先证明 CAD 几何和渲染证据可信 | 已有 `photo3d` gate，输出 `PHOTO3D_REPORT.json`、`ACTION_PLAN.json`、`LLM_CONTEXT_PACK.json` | 已接增强一致性验收 |
| Done | 显式接受 baseline | 用户确认后才把当前 pass/warning run 作为漂移基线 | 已有 `accept-baseline`，记录 `accepted_baseline_run_id`，并校验报告路径、artifact 路径、文件哈希 | 后续在 UI/向导里暴露为“一键接受本轮基线” |
| Done | 普通用户 Photo3D autopilot | 把门禁结果转成固定 round-end 下一步报告 | 新增 `photo3d-autopilot`，写 `PHOTO3D_AUTOPILOT.json`；blocked 指向动作计划；pass/warning 无 baseline 时只建议显式接受；已有 baseline 时建议带 `--dir` 的当前 run 增强命令 | 已在帮助中说明增强后运行 `enhance-check` |
| Done | Photo3D 确认执行层 | 让普通用户/大模型只在确认后执行低风险恢复动作 | 新增 `photo3d-action`：默认预览并写 `PHOTO3D_ACTION_RUN.json`；`--confirm` 后仅执行当前 run `ACTION_PLAN.json` 中 `product-graph` / `build` / `render` 低风险 CLI；用户输入类动作继续询问 | 已接入 action 后 autopilot 循环 |
| Done | Photo3D action 后 autopilot 循环 | 低风险恢复动作成功后自动给出下一步，不让用户反复猜命令 | `photo3d-action --confirm` 在所有已确认 low-risk CLI 成功、整份动作计划没有用户输入/人工复查/rejected/skipped 动作、且 `active_run_id` 执行前后未漂移时，会自动重跑 `photo3d` gate + `photo3d-autopilot`，并写入 `post_action_autopilot` | 已被 `photo3d-run` 多轮向导串联 |
| Done | Photo3D run-aware 恢复 wrapper | 让 `product-graph` / `build` / `render` 恢复动作绑定当前 run，不再依赖默认目录或新建 run | 新增 `photo3d-recover --subsystem <name> --run-id <run_id> --artifact-index <path> --action product-graph|build|render`；action plan 生成 wrapper argv；action runner 拒绝旧式裸 `render/build/product-graph --subsystem`；wrapper 校验 `active_run_id` 后写回当前 run artifacts | 已接 build artifact backfill |
| Done | 项目看板和规划索引 | 每轮结束后给用户看当前进度、验证和下一步 | 新增 `docs/PROGRESS.md`、`docs/superpowers/README.md`，并在根 README 加入口 | 后续每轮结束更新本看板 |
| Done | 通用传动件计划归档 | 清理未跟踪计划文档，避免计划/看板漂移 | `2026-05-02-generic-threaded-parts-pipeline.md` 已补执行状态并纳入索引 | 后续扩展机械类别时另开新计划 |
| Done | 傻瓜式照片级 3D 流程 | 非编程用户只说需求，大模型按动作计划推进 | 新增 `photo3d-run`，写 `PHOTO3D_RUN.json`；默认只预览并停在低风险动作确认点，`--confirm-actions` 后串联 `photo3d-action`，连续推进到用户输入、人工复查、baseline 确认、增强入口、执行失败或 `--max-rounds` | 下一步接更高层项目向导 |
| Done | 增强一致性验收 | 照片级输出不仅生成，还能解释是否可交付 | 新增 `tools/enhance_consistency.py` 批量报告与 `cad_pipeline.py enhance-check`；从 `render_manifest.json` 读取视角，要求增强图在同一 render dir、每个视角唯一匹配；输出 `ENHANCEMENT_REPORT.json` 的 `accepted/preview/blocked` | 下一步把验收摘要回写到更高层 Photo3D/project guide |
| Done | Build artifact backfill | 恢复动作后把更多运行时证据登记回当前 run | `photo3d-recover build` 成功后回填当前 run 的 `ASSEMBLY_SIGNATURE.json`、`ASSEMBLY_REPORT.json`、刷新后的 `MODEL_CONTRACT.json`、确定的装配 GLB/STEP；optional 产物只在精确路径、配置路径或唯一候选存在时登记 | 下一步把增强验收摘要接入 `photo3d-run` / 项目向导 |
| Done | 增强报告接入向导 | 普通用户完成 enhance-check 后不再猜下一步 | `photo3d-autopilot` / `photo3d-run` 只从当前 run 的 `render_manifest` 同目录读取 `ENHANCEMENT_REPORT.json`，输出 `enhancement_accepted` / `enhancement_preview` / `enhancement_blocked` 和 `enhancement_summary` | 下一步设计新用户项目向导 |
| Planned | 常用模型库扩展 | 对其他设备也能复用，不围绕单个元件临时特判 | 已有 adapter/resolver 基础 | 建议按类别扩展：fastener、bearing、linear guide、motor、sensor、cable、pneumatic |
| Planned | 新用户项目向导 | 其他产品进入管线时尽量少问技术细节 | 现有 `cad_pipeline.py init/spec/codegen/photo3d` 可组合 | 设计 `cad_pipeline.py autopilot` 或 skill-level checklist |

## 当前能力边界

- CAD 阶段必须由结构化契约证明，AI 增强不能补 CAD 阶段缺失的零件、位置或数量。
- 第一次 `photo3d pass` 只是候选基线；用户确认后运行 `python cad_pipeline.py accept-baseline --subsystem <name>` 才成为 accepted baseline。
- `accept-baseline` 不扫描目录、不选择最新文件、不切换 `active_run_id`；它只接受同一 run 中路径和哈希都匹配的 `PHOTO3D_REPORT.json`。
- `photo3d-autopilot` 只写下一步报告，不静默接受 baseline，不切换 `active_run_id`；增强建议必须带当前 run 的 `--dir cad/output/renders/<subsystem>/<run_id>`；若当前 run 的 `render_manifest.json` 同目录已有匹配的 `ENHANCEMENT_REPORT.json`，则只读取该报告的交付摘要。
- `photo3d-run` 是普通用户多轮向导，写 `PHOTO3D_RUN.json`；默认不执行恢复动作，只有 `--confirm-actions` 才通过 `photo3d-action` 执行白名单 low-risk 动作。它不接受 baseline、不运行增强、不切换 `active_run_id`，遇到用户输入、人工复查、执行失败或 `--max-rounds` 会停下。
- `photo3d-action` 默认只预览，不执行；只有 `--confirm` 才执行当前 active run `ACTION_PLAN.json` 中 low-risk、无需用户输入、白名单内的 `product-graph` / `build` / `render` CLI。它不运行增强、不接受 baseline、不切换 `active_run_id`，输出必须留在当前 run 目录。
- `ACTION_PLAN.json` 中自动恢复 CLI 必须是 `photo3d-recover --subsystem <name> --run-id <run_id> --artifact-index <path> --action product-graph|build|render`；裸 `product-graph` / `build` / `render --subsystem <name>` 会被 `photo3d-action` 拒绝。
- `post_action_autopilot` 的自动重跑判定看整份 `ACTION_PLAN.json`，不只看 `--action-id` 选中的动作；只要仍有用户输入、人工复查、rejected/skipped 动作、未执行完全部 low-risk CLI、任一 CLI 失败或 `active_run_id` 在执行/重跑过程中变化，就不会自动重跑。
- `photo3d-recover` 不扫描目录、不切换 `active_run_id`、不创建新 run；`product-graph` 写入当前 run `PRODUCT_GRAPH.json`，`render` 使用当前 run 渲染目录，`build` 完成后回填当前 run 的运行时装配签名，并在存在时回填 `ASSEMBLY_REPORT.json`、刷新后的 `MODEL_CONTRACT.json`、确定的装配 GLB/STEP。
- `photo3d-recover build` 对 GLB/STEP 不按最新文件、默认前缀或设备名猜测；优先使用 `render_config.json` 中 `subsystem.glb_file` 指向的 `cad/output` 内文件，缺少配置时只接受 `cad/output/*_assembly.glb` / `*_assembly.step` 的唯一候选。
- `enhance-check` 只读取显式 `--dir` 的 `render_manifest.json` 和同目录 `*_enhanced.*`；增强图、报告、manifest 源图都必须留在同一 render dir/当前项目内。
- `enhance-check` 不会在同一视角有多个增强图时猜一个；这种歧义直接 `blocked` 并在 `ENHANCEMENT_REPORT.json` 写出候选列表。
- `ENHANCEMENT_REPORT.json` 的 `accepted` 才能作为交付；`preview` 只能预览，`blocked` 表示缺视角、路径越界、同视角多候选或输入不完整。
- `photo3d-run` 不运行增强、不运行 `enhance-check`、不扫描增强图；它只把已存在且 run/subsystem/render_manifest 都匹配的 `ENHANCEMENT_REPORT.json` 摘要写进 `PHOTO3D_RUN.json`。
- `warning` 可以接受为 baseline，但应在看板或报告里明确剩余风险。
- 被 `.gitignore` 忽略的 `src/cad_spec_gen/data/*` 镜像仍由 `dev_sync.py` 维护；每轮结束必须跑 `python scripts/dev_sync.py --check`。`skill.json` metadata 现在也纳入同步/检查范围，避免安装版 skill 描述漂移。

## 下一步建议

1. 下一轮优先设计新用户项目向导，把 `init/spec/codegen/photo3d-run/enhance-check` 串成更少技术选项的傻瓜式流程。
2. 再继续常用模型库扩展，按类别扩展 fastener、bearing、linear guide、motor、sensor、cable、pneumatic，而不是围绕单个设备或元件特判。
3. 后续把“一键接受 baseline”“运行增强”“运行 enhance-check”这些人工确认点做成更清晰的大模型交互动作。

## 验证记录

| 日期 | 命令 | 结果 |
| --- | --- | --- |
| 2026-05-04 | `python -m pytest tests\test_photo3d_autopilot.py::test_cmd_photo3d_autopilot_reports_accepted_enhancement_delivery -q` | 先红后绿，覆盖 `ENHANCEMENT_REPORT.json accepted` 接入 autopilot |
| 2026-05-04 | `python -m pytest tests\test_photo3d_autopilot.py -q` | `12 passed`；覆盖 accepted/preview/blocked 和错 run/manifest 绑定不污染当前 run |
| 2026-05-04 | `python -m pytest tests\test_photo3d_loop.py -q` | `6 passed`；覆盖 `photo3d-run` 顶层 `enhancement_summary` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；`photo3d_autopilot.py`、`photo3d_loop.py` 镜像同步 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `158 passed` |
| 2026-05-04 | `python -m pytest -q` | `2048 passed, 18 skipped, 10 warnings`；全量测试生成的 `cad/lifting_platform/std_*.py` 噪音已清理 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_recover.py::test_photo3d_recover_build_backfills_current_run_build_artifacts -q` | 先红后绿，覆盖 build recovery 回填 `ASSEMBLY_REPORT.json`、刷新 `MODEL_CONTRACT.json`、装配 GLB/STEP |
| 2026-05-04 | `python -m pytest tests\test_photo3d_recover.py::test_photo3d_recover_build_accepts_configured_output_relative_glb_path -q` | 先红后绿，覆盖 `render_config.json` 配置相对子路径时不能回退误选其他装配文件 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_recover.py -q` | `7 passed` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；`photo3d_recover.py` 安装版镜像无漂移 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_recover.py tests\test_photo3d_action_runner.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `181 passed` |
| 2026-05-04 | `python -m pytest -q` | `2043 passed, 18 skipped, 10 warnings`；全量测试生成的 `cad/lifting_platform/std_*.py` 噪音已清理 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `133 passed`；规划索引更新后复查 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_recover.py -q` | 合并到 `main` 后 `7 passed` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `133 passed` |
| 2026-05-04 | `python -m pytest tests\test_enhance_consistency.py -q` | `11 passed`；覆盖批量验收、空 manifest 阻断、缺视角、轮廓漂移、路径越界、manifest 路径稳定、同视角多增强图不猜测、CLI accepted/blocked |
| 2026-05-04 | `python -m pytest tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | `11 passed`；覆盖 `enhance-check` help、metadata、文档与工具镜像同步 |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；CLI、metadata、工具镜像无漂移 |
| 2026-05-04 | `python -m pytest tests\test_enhance_consistency.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `152 passed` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `python -m pytest tests\test_enhance_consistency.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `152 passed` |
| 2026-05-04 | `python -m pytest -q` | `2039 passed, 18 skipped, 10 warnings`；全量测试生成的 `cad/lifting_platform/std_*.py` 噪音已清理 |
| 2026-05-04 | `python -m pytest -q` | 合并到 `main` 后 `2044 passed, 14 skipped, 8 warnings`；全量测试生成的 `cad/lifting_platform/std_*.py` 噪音已清理 |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 全量测试后复查通过 |
| 2026-05-04 | `python -m pytest tests\test_enhance_consistency.py -q` | 新增空 manifest 阻断回归后 `11 passed` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 最终复查通过 |
| 2026-05-04 | `python -m pytest -q` | `1985 passed, 12 skipped, 14 warnings` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_test_infra_contract.py tests\test_photo3d_accept_baseline.py tests\test_photo3d_user_flow.py -q` | `26 passed, 1 warning` |
| 2026-05-04 | `python -m pytest tests\test_agents_md.py tests\test_codex_skill_register.py tests\test_version_contract.py -q` | `7 passed, 1 warning` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；通用传动件计划归档后无镜像漂移 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_test_infra_contract.py tests\test_photo3d_accept_baseline.py tests\test_photo3d_user_flow.py tests\test_photo3d_autopilot.py tests\test_dev_sync_check.py -q` | `38 passed, 1 warning` |
| 2026-05-04 | `python -m pytest tests\test_data_dir_sync.py -q` | `123 passed, 1 warning` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；metadata 与 tools mirror 均无漂移 |
| 2026-05-04 | `python -m pytest -q` | `1994 passed, 16 skipped, 13 warnings` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；`photo3d_action_runner.py` 镜像同步 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py tests\test_photo3d_autopilot.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py -q` | `30 passed, 1 warning` |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py tests\test_photo3d_autopilot.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_gate_contract.py tests\test_photo3d_accept_baseline.py tests\test_dev_sync_check.py -q` | `52 passed, 1 warning` |
| 2026-05-04 | `python -m pytest -q` | `2009 passed, 17 skipped, 16 warnings` |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py::test_photo3d_action_does_not_rerun_autopilot_when_unselected_user_input_remains -q` | 先红后绿，覆盖 `--action-id` 下整份计划仍有用户输入时不能自动重跑 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py -q` | `19 passed, 1 warning` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；action runner 镜像无漂移 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py tests\test_photo3d_autopilot.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_gate_contract.py tests\test_photo3d_accept_baseline.py tests\test_dev_sync_check.py -q` | `57 passed, 1 warning` |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py::test_photo3d_action_does_not_rerun_autopilot_when_unselected_cli_remains -q` | 先红后绿，覆盖 `--action-id` 下未执行完全部 low-risk CLI 时不能自动重跑 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py::test_photo3d_action_blocks_post_autopilot_when_active_run_id_changes -q` | 先红后绿，覆盖执行期间 `active_run_id` 漂移时阻断 post-action autopilot |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py -q` | `21 passed, 1 warning` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；审查修正后 action runner 镜像无漂移 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py tests\test_photo3d_autopilot.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_gate_contract.py tests\test_photo3d_accept_baseline.py tests\test_dev_sync_check.py -q` | `59 passed, 1 warning` |
| 2026-05-04 | `python -m pytest -q` | `2017 passed, 16 skipped, 16 warnings` |
| 2026-05-04 | `python -m pytest tests\test_photo3d_recover.py tests\test_photo3d_llm_action_plan.py::test_render_stale_reason_generates_rerun_render_action tests\test_photo3d_llm_action_plan.py::test_missing_render_manifest_artifact_generates_rerun_render_action tests\test_photo3d_action_runner.py::test_photo3d_action_confirm_executes_low_risk_cli_with_current_interpreter tests\test_photo3d_action_runner.py::test_photo3d_action_confirm_stops_after_first_cli_failure tests\test_photo3d_action_runner.py::test_photo3d_action_rejects_legacy_recovery_cli_without_run_scope -q` | 先红后绿，覆盖 run-aware wrapper 生成、执行、旧式裸恢复命令拒绝 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_recover.py tests\test_photo3d_user_flow.py tests\test_photo3d_autopilot.py tests\test_photo3d_gate_contract.py tests\test_dev_sync_check.py -q` | `54 passed, 1 warning` |
| 2026-05-04 | `python -m pytest tests\test_photo3d_recover.py::test_photo3d_recover_render_stages_current_run_contracts_for_legacy_render_inputs tests\test_photo3d_recover.py::test_photo3d_recover_build_fails_when_runtime_signature_is_not_produced -q` | 先红后绿，覆盖 legacy build/render 输入投影和 build 缺失运行时签名失败 |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；`photo3d_recover.py`、CLI、metadata、帮助文档镜像无漂移 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_recover.py tests\test_photo3d_user_flow.py tests\test_photo3d_autopilot.py tests\test_photo3d_gate_contract.py tests\test_photo3d_accept_baseline.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `189 passed, 1 warning` |
| 2026-05-04 | `python -m pytest -q` | `2023 passed, 16 skipped, 13 warnings` |
| 2026-05-04 | `python -m pytest tests\test_photo3d_llm_action_plan.py::test_action_plan_uses_report_artifact_index_for_run_aware_recovery tests\test_photo3d_action_runner.py::test_photo3d_action_allows_recovery_wrapper_with_custom_artifact_index_path -q` | 先红后绿，覆盖自定义 `--artifact-index` 不回退默认路径 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_action_runner.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_recover.py tests\test_photo3d_user_flow.py tests\test_photo3d_autopilot.py tests\test_photo3d_gate_contract.py tests\test_photo3d_accept_baseline.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `191 passed, 1 warning` |
| 2026-05-04 | `python -m pytest -q` | `2025 passed, 16 skipped, 13 warnings` |
| 2026-05-04 | `python -m pytest -q` | `2023 passed, 18 skipped, 8 warnings` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `python -m pytest -q` | 合并到 `main` 后 `2027 passed, 14 skipped, 8 warnings` |
| 2026-05-04 | `python -m pytest tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | `15 passed` |
| 2026-05-04 | `python -m pytest tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `130 passed` |
| 2026-05-04 | `python -m pytest tests\test_photo3d_loop.py tests\test_photo3d_action_runner.py tests\test_photo3d_autopilot.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_photo3d_llm_action_plan.py tests\test_photo3d_recover.py tests\test_photo3d_gate_contract.py tests\test_photo3d_accept_baseline.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `198 passed` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；`photo3d-run` CLI、metadata、工具镜像无漂移 |
| 2026-05-04 | `python -m pytest -q` | `2030 passed, 18 skipped, 10 warnings` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `python -m pytest -q` | 合并到 `main` 后 `2034 passed, 14 skipped, 8 warnings` |

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
