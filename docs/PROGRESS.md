# cad-spec-gen 项目看板

> 本文件是每轮工作结束后给用户看的进度入口。
> 更新规则：每轮完成实现、审查、合并或重要验证后，更新「最新状态」「看板」「下一步建议」「验证记录」。

## 最新状态

| 字段 | 当前值 |
| --- | --- |
| 更新日期 | 2026-05-05 |
| 当前分支 | `codex/common-model-library-batch-4` worktree：`.worktrees/common-model-library-batch-4` |
| 最新功能基线 | `54fd9cc feat(parts-library): 扩展常用模型库第三批` |
| 最新合并/进度提交 | `d07c30c docs(progress): 记录第三批推送清理` |
| 最新归档计划提交 | `9ed3280 docs(project): 归档通用传动件计划` |
| 最近验证 | 第四批最终范围回归 `pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` -> `454 passed, 2 skipped` |
| 同步检查 | `python scripts/dev_sync.py --check` -> 通过；`git diff --check` -> 通过 |
| 当前未跟踪 | `docs/superpowers/plans/2026-05-05-common-model-library-batch-4.md`、`tests/test_common_model_library_batch_4.py` 待纳入第四批提交 |

## 一句话结论

Photo3D 契约驱动出图主线已进入“只读项目向导 + 常用模型库第一批 + 多轮向导 + 报告 + 确认执行 + run-aware 恢复 + build 证据回填 + 执行后自动回看下一步 + 增强后交付摘要”阶段：普通用户和大模型可先运行 `project-guide` 生成 `PROJECT_GUIDE.json`，再按报告进入 `init/spec/codegen/build --render/photo3d-run`；常见外购件优先通过默认库显式规则命中可复用 B 级参数化模板，已有 active run 后继续用 run_id、artifact index、产品图、模型契约、装配签名、装配报告、装配 GLB/STEP、渲染清单、变更范围、显式 accepted baseline、`PHOTO3D_RUN.json`、`PHOTO3D_AUTOPILOT.json`、`ACTION_PLAN.json`、`PHOTO3D_ACTION_RUN.json` 和 `ENHANCEMENT_REPORT.json` 保护照片级 3D 出图。

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
| Done | 新用户项目向导 | 其他产品进入管线时尽量少问技术细节 | 新增只读 `project-guide`，写 `PROJECT_GUIDE.json`；只读取显式 `--subsystem`、可选 `--design-doc`、固定 `CAD_SPEC.md` / codegen 哨兵和显式/默认 `ARTIFACT_INDEX.json` active run；输出下一条安全 `argv` | 下一步扩展模型库类别 |
| Done | 常用模型库扩展第一批 | 对其他设备也能复用，不围绕单个元件临时特判 | 已在默认库加入 motor、sensor、cable、pneumatic 显式规则；Jinja 适配器支持 LMxxUU、NEMA17/23、M8/M12/M18 接近传感器、线束可视段、紧凑气缸 B 级模板；包络测试保护 `real_dims` 不超界 | 继续扩展 linear guide、常见联轴器/皮带/齿轮、端子/接插件和更多气动件 |
| Done | 常用模型库扩展第二批 | 继续减少项目特判，让更多产品零配置获得可辨识常用件 | 已合并并推送到 `origin/main`；实现 linear guide、通用联轴器、GT2 带轮、直齿轮、端子/M12 接插件、电磁阀、快插接头 B 级模板；默认库显式路由在真实 STEP/厂商规则之后、通用轴承/终端 fallback 之前；新增 category-scoped 尺寸匹配防止 material 描述跨类别抢尺寸；范围回归通过；已清理 `codex/common-model-library-batch-2` worktree/分支 | 已进入第三批跨产品高频模型库扩展 |
| Done | 常用模型库扩展第三批 | 扩展更多跨产品高频外购件，继续减少单设备临时调参 | 已实现 mounted bearing/support、BK/BF support block、KK linear module、valve manifold/FRL、DIN rail terminal/device B 级模板；新增分类、category-scoped 尺寸、默认库显式顺序规则和负例；回归中恢复 `KFL001` 精确模板优先，形成“精确成熟模板优先于通用族模板”的通用规则；已推送到 `origin/main` 并清理 worktree/分支 | 进入下一批跨产品高频模型库或大模型交互动作 |
| In Progress | 常用模型库扩展第四批 | 覆盖小型电气箱/面板控件、传感器安装附件、真空元件、铝型材/角码 | 已实现 electrical enclosure、22mm panel pushbutton、sensor mounting bracket、vacuum ejector/cup、2020/2040 T-slot extrusion、2020 corner bracket B 级模板；新增显式分类、category-scoped 尺寸、默认库显式路由和宽词负例；范围回归通过 | 跑最终回归、提交、合并到 `main`、推送并清理 worktree/分支 |

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
- `project-guide` 只读，除了写 `PROJECT_GUIDE.json` 不修改管线状态；它不扫描目录、不猜最新 run、不接受 baseline、不运行增强，只按显式输入和固定契约路径给出下一条安全命令。
- 常用模型库扩展只把明确、可参数化、跨项目复用的类别放进 `parts_library.default.yaml`；项目真实 STEP、SolidWorks/Toolbox 或用户导入模型仍应通过项目前置规则覆盖默认 B 级模板。
- 新增线束模板只覆盖明确“线束 / harness / FFC”意图；普通拖链段、柔性同轴等未命中可复用线束模板时继续 `skip`，防止退回无意义盒子。
- 第二批常用模型库不使用裸 `滑块`、`M12`、`PC6/PC8` 等短 token 抢类别或路由；这些 token 只能在已有明确 family intent 后作为尺寸/针数/管径解析线索。
- 第三批常用模型库不使用裸 `DIN`、`阀`、`模块`、`支撑座`、`BK`、`BF` 或 `35mm` 抢类别/路由；只有类别和明确 family intent 同时成立才进入 B 级模板。
- 第四批常用模型库不使用裸 `柜`、`板`、`支架`、`接头`、`型材`、`真空`、`按钮`、`M12`、`2020` 或 `IP65` 抢类别/路由；只有类别和明确 family intent 同时成立才进入 B 级模板。
- 精确成熟模板优先于新增通用族模板；例如已有专用模板的型号不能被更宽的默认 family route 抢走。
- 默认尺寸查询支持 category-scoped key，防止 `material` 中的别族描述（例如泵的“电磁阀式”）覆盖 `name_cn` 中更具体的同类零件尺寸。
- 新增可复用模板必须保持生成几何不超过 `real_dims`，否则会污染后续装配、渲染和照片级增强的契约证据。
- `warning` 可以接受为 baseline，但应在看板或报告里明确剩余风险。
- 被 `.gitignore` 忽略的 `src/cad_spec_gen/data/*` 镜像仍由 `dev_sync.py` 维护；每轮结束必须跑 `python scripts/dev_sync.py --check`。`skill.json` metadata 现在也纳入同步/检查范围，避免安装版 skill 描述漂移。

## 下一步建议

1. 完成第四批最终回归、提交、合并、推送，并清理 `codex/common-model-library-batch-4` worktree/分支。
2. 继续把“一键接受 baseline”“运行增强”“运行 enhance-check”这些人工确认点做成更清晰的大模型交互动作。
3. 把四批模型库沉淀为“添加新族模板的准入清单”：显式分类、默认路由顺序、category-scoped 尺寸、专用模板优先、包络不超界、真实模型优先。

## 验证记录

| 日期 | 命令 | 结果 |
| --- | --- | --- |
| 2026-05-05 | `git worktree add .worktrees\common-model-library-batch-4 -b codex/common-model-library-batch-4` | 已创建第四批计划 worktree |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py -q` | 第四批 worktree 基线 `141 passed, 7 warnings` |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_4.py tests\test_parts_library_standard_categories.py -q` | 先红后绿，最终 `73 passed, 7 warnings`；覆盖第四批分类、模板、负例、默认路由和包络不超 `real_dims` |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py -q` | 第四批范围回归 `323 passed, 2 skipped, 11 warnings` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 第四批同步后通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 第四批最终回归 `454 passed, 2 skipped, 11 warnings` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 第四批最终同步检查通过 |
| 2026-05-05 | `git diff --check` | 第四批最终空白检查通过 |
| 2026-05-04 | `git push origin main` | 已推送 `main` 到远端，`cea6e1b..b6555ce` |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_batch_3.py -q` | 第三批实现后 `44 passed, 7 warnings`；覆盖分类、模板、负例、包络不超 `real_dims` |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_batch_3.py tests\test_parts_library_standard_categories.py -q` | 第三批默认库顺序补测后 `68 passed, 7 warnings` |
| 2026-05-04 | `python -m pytest tests\test_jinja_generators_new.py::test_lifting_platform_curated_parts_report_b_grade_parametric_templates tests\test_jinja_generators_new.py::test_lifting_platform_template_geometry_stays_within_reported_real_dims tests\test_common_model_library_batch_3.py -q` | 回归修正后 `66 passed, 7 warnings`；恢复 `KFL001` 精确模板优先于新增通用轴承座模板 |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py -q` | 第三批范围回归 `274 passed, 2 skipped, 11 warnings` |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 第三批同步后通过；安装版镜像无漂移 |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 第三批最终回归 `405 passed, 2 skipped, 11 warnings` |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 第三批最终同步检查通过 |
| 2026-05-04 | `git diff --check` | 第三批最终空白检查通过 |
| 2026-05-04 | `git merge --ff-only codex/common-model-library-batch-3` | 第三批已快进合并到 `main` |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 第三批合并到 `main` 后 `405 passed, 2 skipped, 11 warnings` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 第三批合并到 `main` 后通过 |
| 2026-05-05 | `git diff --check` | 第三批合并到 `main` 后通过 |
| 2026-05-05 | `git push origin main` | 已推送 `main` 到远端，`6029f1a..121aa53` |
| 2026-05-05 | `git worktree remove .worktrees\common-model-library-batch-3`；`git branch -d codex/common-model-library-batch-3` | 已清理第三批已合并 worktree/分支 |
| 2026-05-04 | `git worktree remove .worktrees\common-model-library-batch-2`；`git branch -d codex/common-model-library-batch-2` | 已清理第二批已合并 worktree/分支；保留其他独立 worktree |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 推送和清理后复查通过 |
| 2026-05-04 | `git diff --check` | 推送和清理后复查通过 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 文档收尾后 `134 passed` |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `352 passed, 2 skipped, 11 warnings` |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `git diff --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 审查修正后 `352 passed, 2 skipped, 11 warnings`；补充覆盖泵 material 中“电磁阀式”不抢类别、英文气动附件优先于泛气动模板 |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 第二批最终范围回归 `349 passed, 2 skipped, 11 warnings` |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 第二批实现后通过；安装版镜像无漂移 |
| 2026-05-04 | `git diff --check` | 第二批实现后通过 |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_batch_2.py tests\test_jinja_generators_new.py tests\test_parts_library_standard_categories.py -q` | 第二批实现阶段回归 `147 passed, 7 warnings`；覆盖分类、默认路由、模板包络、M12/PC6/滑块误抢、category-scoped 尺寸防漂移 |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py -q` | 第二批计划审查修订后 `34 passed, 7 warnings` |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 第二批计划审查修订后通过 |
| 2026-05-04 | `git diff --check` | 第二批计划审查修订后通过 |
| 2026-05-04 | `git push origin main` | 已推送 `main` 到远端，`b958712..cea6e1b` |
| 2026-05-04 | `git worktree add .worktrees/common-model-library-batch-2 -b codex/common-model-library-batch-2` | 已创建第二批计划 worktree |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py -q` | 第二批计划 worktree 基线 `34 passed` |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 新 worktree 填充 ignored 镜像后通过 |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `298 passed, 2 skipped` |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `git diff --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `python -m pytest tests\test_common_model_library_expansion.py -q` | 先红后绿，最终 `26 passed`；覆盖分类、默认路由、可复用 B 级模板、线束 codegen 和新增模板包络不超 `real_dims` |
| 2026-05-04 | `python -m pytest tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_resolve_report.py tests\test_parts_library_integration.py tests\test_parts_library_standard_categories.py tests\test_common_model_library_expansion.py -q` | `208 passed, 2 skipped`；覆盖适配器、默认库、报告和通用模型库扩展 |
| 2026-05-04 | `python scripts\dev_sync.py` | 同步安装版镜像；跟踪镜像 `src/cad_spec_gen/data/codegen/gen_std_parts.py` 更新 |
| 2026-05-04 | `python scripts\dev_sync.py --check` | 通过；镜像无漂移 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_autopilot.py::test_cmd_photo3d_autopilot_reports_accepted_enhancement_delivery -q` | 先红后绿，覆盖 `ENHANCEMENT_REPORT.json accepted` 接入 autopilot |
| 2026-05-04 | `python -m pytest tests\test_photo3d_autopilot.py -q` | `12 passed`；覆盖 accepted/preview/blocked 和错 run/manifest 绑定不污染当前 run |
| 2026-05-04 | `python -m pytest tests\test_photo3d_loop.py -q` | `6 passed`；覆盖 `photo3d-run` 顶层 `enhancement_summary` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；`photo3d_autopilot.py`、`photo3d_loop.py` 镜像同步 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `159 passed` |
| 2026-05-04 | `python -m pytest -q` | `2048 passed, 18 skipped, 10 warnings`；全量测试生成的 `cad/lifting_platform/std_*.py` 噪音已清理 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py -q` | 合并到 `main` 后 `18 passed` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 合并到 `main` 后通过 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `141 passed` |
| 2026-05-04 | `python -m pytest tests\test_project_guide.py -q` | 先红后绿，最终 `8 passed`；覆盖只读项目向导、显式设计文档、active run 绑定、子系统不匹配和输出路径约束 |
| 2026-05-04 | `python -m pytest tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | 先红后绿，最终 `12 passed`；覆盖 `project-guide` CLI help、metadata、cad-help 文档和工具镜像 |
| 2026-05-04 | `python -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | `151 passed` |
| 2026-05-04 | `python scripts/dev_sync.py --check` | 通过；`project_guide.py`、CLI、metadata、帮助文档镜像无漂移 |
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
