# cad-spec-gen 项目看板

> 本文件是每轮工作结束后给用户看的进度入口。
> 更新规则：每轮完成实现、审查、合并或重要验证后，更新「最新状态」「看板」「下一步建议」「验证记录」。

## 最新状态

| 字段 | 当前值 |
| --- | --- |
| 更新日期 | 2026-05-05 |
| 当前主线 | `main` 已推送；`codex/enhance-check-loop` worktree/分支已清理 |
| 管线 Phase 数 | 6 个：SPEC / CODEGEN / BUILD / RENDER / ENHANCE / ANNOTATE |
| 总体能力进展 | 约 74%（按 6 个 Phase 的工程化能力估算，不代表某个具体产品一次出图进度） |
| 当前主攻 Phase | Phase 6 ANNOTATE / DELIVER：Phase 5 -> 6 的增强执行 + enhance-check 闭环本轮完成，下一步是最终交付包 |
| 最新功能基线 | 增强执行 + `enhance-check` 闭环（本轮完成）；上一轮为 Provider 配置健康检查 |
| 最新合并/进度提交 | `c853ad9 docs(progress): 记录增强闭环合并验证`；功能提交为 `ec92cb2 feat(photo3d): 串联增强执行和验收闭环` |
| 最新归档计划提交 | `9ed3280 docs(project): 归档通用传动件计划` |
| 最近验证 | `python -m pytest tests\test_photo3d_handoff.py tests\test_enhance_consistency.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` -> `206 passed` |
| 同步检查 | `python scripts/dev_sync.py --check` -> 通过；`git diff --check` -> 通过（仅 Windows 行尾提示） |
| 当前未跟踪 | 无；本轮新增计划文档已纳入提交。另有独立旧 worktree `.worktrees/generic-threaded-photo-autopilot`，本轮不触碰 |

## 一句话结论

cad-spec-gen 已形成 6 阶段 CAD 混合渲染管线。现在不是围绕某个零件做临时调参，而是在把“其他用户、其他产品也能傻瓜式出照片级 3D 图”的通用流程补齐：Phase 1-4 的 CAD/渲染证据链已基本可用，Phase 5 已把 provider 选择、配置健康、确认式增强执行和同 run 验收闭环接进普通用户/大模型流程，Phase 6 下一步要把 accepted/preview/blocked 的结果打包成可交付图片包和证据摘要。

## 进度口径

- 下面百分比是“管线能力建设进展”，不是某个具体产品本轮出图进度。
- `Done` 表示已经有代码、文档或测试保护并合并过；`In progress` 表示当前主攻；`Next` 表示后续建议顺序。
- 跨 Phase 能力，例如路径契约、run manifest、项目向导和大模型 handoff，会挂在最主要受益的 Phase 下，同时在备注里标明影响范围。

## Phase 总览

| Phase | 做什么 | 关键产物 | 进展 | 当前判断 |
| --- | --- | --- | --- | --- |
| Phase 1 SPEC | 从设计文档抽取结构化 CAD 规格，并做设计审查 | `CAD_SPEC.md`、`DESIGN_REVIEW.json`、补充参数 | 85% | 已有结构化章节、审查门禁和模型选择补充；下一步是把新用户输入做得更少、更稳 |
| Phase 2 CODEGEN | 从 Spec 生成 CadQuery 代码、BOM 路由和标准件模型 | `params.py`、`build_all.py`、`assembly.py`、`std_*.py` | 82% | 模型库、resolver、四批常用模型族和准入清单已成型；仍需继续扩展跨产品高频件 |
| Phase 3 BUILD | 构建 STEP/GLB/工程图预览，并登记构建证据 | `.step`、`.glb`、DXF/PNG、`ASSEMBLY_REPORT.json` | 76% | run-aware recover、artifact backfill 和装配校验已完成；还要增强更多失败恢复和边界测试 |
| Phase 4 RENDER | 用 Blender 渲染多视角 3D 图，并绑定当前 run | `render_manifest.json`、多视角 `V*.png` | 72% | 路径契约和当前 run 绑定已建立；后续要补视觉回归、Blender 预检和更稳定的材质/灯光策略 |
| Phase 5 ENHANCE | 把 CAD 渲染图增强到照片级，并做一致性验收 | `*_enhanced.*`、`ENHANCEMENT_REPORT.json`、provider preset | 78% | provider 白名单、普通用户文案、handoff、enhance-check、UI wizard、配置健康检查和增强后自动验收回读已接入；剩余是更多视觉质量验收 |
| Phase 6 ANNOTATE / DELIVER | 标注、交付最终图片包和证据摘要 | `*_labeled_*.png`、交付报告、可读摘要 | 40% | 增强交付状态已能从 handoff 闭环透出；“傻瓜式最终交付包”和可视化验收还不够完整 |

**总体进展：约 74%。** 最大剩余缺口不在单个零件，而在 Phase 6 和 Phase 4：把已经验收的增强结果变成可交付图片包，同时用视觉回归和元件一致性检查继续防止渲染阶段的通用漂移。

## 当前 Phase 明细

### Phase 1 SPEC：85%

已完成：
- `CAD_SPEC.md` 生成、设计审查、§6.3/§6.4/§9 装配约束等结构化信息。
- `DESIGN_REVIEW.json` 的 warning/critical 门禁和补充参数机制。
- 模型选择补充可以把用户提供的 STEP 结构化写入后续流程。

剩余：
- 把 `project-guide` 的新用户入口继续前移，减少用户对子系统名、设计文档路径、补充参数的手工输入。
- 更系统地测试不同产品类型下的规格缺失、歧义和回填策略。

### Phase 2 CODEGEN：82%

已完成：
- CadQuery scaffold、标准件生成、模型库 resolver、`parts_library.yaml` 继承规则。
- 常用模型库四批扩展，以及“新增模型族必须有 positive/negative/route/precedence/dimension/geometry 测试”的准入清单。
- 真实 STEP、用户 STEP、SolidWorks/Toolbox、bd_warehouse、PartCAD 和 fallback 的优先级边界。

剩余：
- 继续扩展跨产品高频件，但按准入清单做，不再按某个设备临时收紧。
- 增强模型质量报告，让普通用户知道哪些零件是真模型、哪些只是 B/C/D 级替代。

### Phase 3 BUILD：76%

已完成：
- build 后构建 STEP/GLB、装配校验、运行时签名和 build artifact backfill。
- `photo3d-recover` 让恢复动作绑定当前 run，不猜最新目录、不创建新 run。

剩余：
- 增强构建失败时的可恢复动作，覆盖更多 optional artifact 和配置缺失边界。
- 把 build 阶段结果在项目向导里展示得更可读。

### Phase 4 RENDER：72%

已完成：
- Blender 渲染产物通过 `render_manifest.json` 与当前 run 绑定。
- `photo3d` gate、`photo3d-run`、`photo3d-action` 防止旧图、旧路径、旧 run 混用。

剩余：
- 加入更系统的 Blender 环境预检、视角/灯光/材质质量检查和截图级回归。
- 把“渲染图比上一轮少元件”这类问题固化成通用数量/身份/视角一致性检查。

### Phase 5 ENHANCE：78%

已完成：
- `enhance-check` 要求增强图与源图、视角、render dir 一致；不会猜多候选。
- `photo3d-handoff --provider-preset` 只允许白名单 provider，不信任 JSON 任意 argv，不暴露 key/url/secret。
- `PROJECT_GUIDE.json` 已输出 `provider_choice.ordinary_user_options`，普通用户能看到“默认 / 本地工程预览 / 云增强”等选项。
- `PROJECT_GUIDE.json` 新增 `provider_wizard`，把 `ordinary_user_options` 组织成 UI/大模型可直接展示的步骤、默认项和预览动作；默认只预览，不执行增强，不加 `--confirm`。
- `PROJECT_GUIDE.json` 新增 `provider_health` 和 `provider_wizard.options[].health`，只读判断 provider 是否可用或需配置；检查配置/依赖存在性，不运行增强、不扫描输出目录、不泄漏 key、URL、endpoint 或 secret。
- `photo3d-handoff --confirm` 在增强成功后自动运行同一 active run/render dir 的 `enhance-check`，把 subprocess 写入 `followup_action`，再无确认回读一次 `photo3d-run`，把 accepted/preview/blocked 写入 `post_handoff_photo3d_run`。
- `enhance-check` blocked 返回非零但写出有效 `ENHANCEMENT_REPORT.json` 时，handoff 仍会暴露 `enhancement_blocked` 和下一步；增强失败会跳过 follow-up，follow-up 阶段 run 漂移会写 `execution_failed` 报告。

剩余：
- 增强结果的视觉质量验收还需要继续扩展，尤其是多视角一致性、材质一致性和照片级质量评分。
- 若要加入 `gpt-image-2-pro`，必须先做真实 backend adapter、配置隔离、一致性验收和安全测试，再进入白名单。

### Phase 6 ANNOTATE / DELIVER：40%

已完成：
- 管线已有标注阶段的产物扫描口径。
- 增强验收报告已经能给出 accepted/preview/blocked 交付状态。
- `photo3d-handoff` 已把增强后的交付状态带回 `PHOTO3D_HANDOFF.json.post_handoff_photo3d_run`，普通用户和大模型不需要扫描目录判断增强是否可交付。

剩余：
- 做最终交付包：原始渲染、增强图、标注图、证据报告和可读摘要一并归档。
- 在项目向导里把“已可交付 / 只能预览 / 被阻断”的原因讲清楚。
- 多视角照片级一致性仍需更严格的视觉和语义验收。

## 后续执行队列

| 顺序 | 工作 | 所属 Phase | 为什么排这里 | 完成后用户会看到什么 |
| --- | --- | --- | --- | --- |
| Done | Provider preset UI wizard | Phase 5 | 已有 `ordinary_user_options` 数据，已接成普通用户可选界面/报告 | `PROJECT_GUIDE.json.provider_wizard` 可直接给 UI/大模型展示 |
| Done | Provider 配置健康检查 | Phase 5 | wizard 需要知道哪些选项当前可用，但不能泄漏 key/url | 向导显示“可用/需配置/未知”，仍不展示密钥、URL 或 endpoint |
| Done | 增强执行 + enhance-check 闭环入口 | Phase 5 -> Phase 6 | 选择 provider 后要自然进入增强验收，而不是让用户手拼下一条命令 | 增强完成后自动给出 accepted/preview/blocked 和下一步 |
| 1 | 最终交付包 | Phase 6 | 照片级结果需要可交付，不只是生成一张图 | 一个目录里有增强图、标注图、证据报告和用户摘要 |
| 2 | Blender 视觉回归和元件一致性检查 | Phase 4 | 防止出现“新渲染比旧渲染少元件”的通用问题 | 渲染阶段能报告元件数量/身份/视角证据是否漂移 |
| 3 | 常用模型库下一批 | Phase 2 | 继续提高不同产品零配置成图质量 | 更多常见外购件自动走可辨识 B 级或真实模型 |
| 4 | 新用户项目入口再简化 | Phase 1 -> Phase 6 | 把全流程串成少提问、多确认的项目向导 | 用户只说产品和目标，系统按 Phase 给下一步 |

## 当前能力边界

- CAD 阶段必须由结构化契约证明，AI 增强不能补 CAD 阶段缺失的零件、位置或数量。
- 第一次 `photo3d pass` 只是候选基线；用户确认后运行 `python cad_pipeline.py accept-baseline --subsystem <name>` 才成为 accepted baseline。
- `accept-baseline` 不扫描目录、不选择最新文件、不切换 `active_run_id`；它只接受同一 run 中路径和哈希都匹配的 `PHOTO3D_REPORT.json`。
- `photo3d-autopilot` 只写下一步报告，不静默接受 baseline，不切换 `active_run_id`；增强建议必须带当前 run 的 `--dir cad/output/renders/<subsystem>/<run_id>`；若当前 run 的 `render_manifest.json` 同目录已有匹配的 `ENHANCEMENT_REPORT.json`，则只读取该报告的交付摘要。
- `photo3d-run` 是普通用户多轮向导，写 `PHOTO3D_RUN.json`；默认不执行恢复动作，只有 `--confirm-actions` 才通过 `photo3d-action` 执行白名单 low-risk 动作。它不接受 baseline、不运行增强、不切换 `active_run_id`，遇到用户输入、人工复查、执行失败或 `--max-rounds` 会停下。
- `photo3d-action` 默认只预览，不执行；只有 `--confirm` 才执行当前 active run `ACTION_PLAN.json` 中 low-risk、无需用户输入、白名单内的 `product-graph` / `build` / `render` CLI。它不运行增强、不接受 baseline、不切换 `active_run_id`，输出必须留在当前 run 目录。
- `photo3d-handoff` 默认只预览当前 `PHOTO3D_RUN.json` / `PHOTO3D_AUTOPILOT.json` 的 `next_action`，写 `PHOTO3D_HANDOFF.json`；只有 `--confirm` 才执行 `accept-baseline`、`enhance`、`enhance-check` 或 `photo3d-run --confirm-actions` 这类已识别交接。增强执行成功后，它会自动运行同一 active run/render dir 的 `enhance-check`，写 `followup_action`，再无确认回读一次 `photo3d-run`，写 `post_handoff_photo3d_run`；它不扫描目录猜最新文件、不信任 JSON 中任意 argv、不切换 `active_run_id`，输出必须留在当前 run 目录。
- `photo3d-handoff --provider-preset` 只对 `run_enhancement` 生效，允许值是 `default`、`engineering`、`gemini`、`fal`、`fal_comfy`、`comfyui`；未知 preset 会进入 `needs_manual_review`，不会执行 subprocess。preset 只能映射到已支持的 `enhance --backend/--model` 参数，不能把任意 URL、API key、未来模型名或 JSON 里的任意 argv 变成命令。
- `photo3d-handoff` 的增强闭环状态：`executed_with_followup` 表示增强执行和同 run 验收回读完成；增强 subprocess 失败时不会运行 follow-up；follow-up 阶段 `active_run_id` 漂移、报告缺失或回读失败时写 `execution_failed` 和 `followup_action.stderr`，而不是无报告退出。
- `photo3d-autopilot` 在 ready_for_enhancement 时公开 `provider_presets` 和 `default_provider_preset`，但默认 `argv/cli` 保持既有增强命令，让项目配置仍然可以决定默认后端；普通用户或大模型需要指定后端时，应通过 `photo3d-handoff --provider-preset <id>`。
- `public_provider_presets()` 的公开信息只允许稳定展示字段和受信任 argv 后缀；不得暴露 API key、URL、endpoint、secret 等配置字段。
- `ACTION_PLAN.json` 中自动恢复 CLI 必须是 `photo3d-recover --subsystem <name> --run-id <run_id> --artifact-index <path> --action product-graph|build|render`；裸 `product-graph` / `build` / `render --subsystem <name>` 会被 `photo3d-action` 拒绝。
- `post_action_autopilot` 的自动重跑判定看整份 `ACTION_PLAN.json`，不只看 `--action-id` 选中的动作；只要仍有用户输入、人工复查、rejected/skipped 动作、未执行完全部 low-risk CLI、任一 CLI 失败或 `active_run_id` 在执行/重跑过程中变化，就不会自动重跑。
- `photo3d-recover` 不扫描目录、不切换 `active_run_id`、不创建新 run；`product-graph` 写入当前 run `PRODUCT_GRAPH.json`，`render` 使用当前 run 渲染目录，`build` 完成后回填当前 run 的运行时装配签名，并在存在时回填 `ASSEMBLY_REPORT.json`、刷新后的 `MODEL_CONTRACT.json`、确定的装配 GLB/STEP。
- `photo3d-recover build` 对 GLB/STEP 不按最新文件、默认前缀或设备名猜测；优先使用 `render_config.json` 中 `subsystem.glb_file` 指向的 `cad/output` 内文件，缺少配置时只接受 `cad/output/*_assembly.glb` / `*_assembly.step` 的唯一候选。
- `enhance-check` 只读取显式 `--dir` 的 `render_manifest.json` 和同目录 `*_enhanced.*`；增强图、报告、manifest 源图都必须留在同一 render dir/当前项目内。
- `enhance-check` 不会在同一视角有多个增强图时猜一个；这种歧义直接 `blocked` 并在 `ENHANCEMENT_REPORT.json` 写出候选列表。
- `ENHANCEMENT_REPORT.json` 的 `accepted` 才能作为交付；`preview` 只能预览，`blocked` 表示缺视角、路径越界、同视角多候选或输入不完整。
- `photo3d-run` 不运行增强、不运行 `enhance-check`、不扫描增强图；它只把已存在且 run/subsystem/render_manifest 都匹配的 `ENHANCEMENT_REPORT.json` 摘要写进 `PHOTO3D_RUN.json`。
- `project-guide` 只读，除了写 `PROJECT_GUIDE.json` 不修改管线状态；它不扫描目录、不猜最新 run、不接受 baseline、不运行增强，只按显式输入和固定契约路径给出下一条安全命令。
- `project-guide` 只有在当前 active run 的 `PHOTO3D_RUN.json` / `PHOTO3D_AUTOPILOT.json` 与 subsystem、`active_run_id` 匹配，且状态为 `ready_for_enhancement`、`next_action.kind` 为 `run_enhancement` 时，才附带 `provider_choice`；选项来自 provider preset 白名单，handoff 示例是预览命令，不带 `--confirm`。
- `project-guide.provider_choice.ordinary_user_options` 是给普通用户/UI/大模型展示的首选入口，字段包含标题、说明、推荐场景、是否需要配置和预览命令；它与 `provider_presets` 同序，且不会绕过 `photo3d-handoff` 的确认边界。
- `project-guide.provider_wizard` 只从 `ordinary_user_options` 派生，组织为选择 provider、预览 handoff、显式确认三步；它不执行增强、不追加 `--confirm`、不扫描目录，也不暴露 key/url/endpoint/secret。
- `project-guide.provider_health` 由 provider preset 白名单驱动，只检查配置/依赖存在性并输出“可用/需配置/未知”；它不运行增强、不做网络探活、不扫描输出目录、不暴露环境变量名、key 值、URL、endpoint 或 secret。
- 常用模型库扩展只把明确、可参数化、跨项目复用的类别放进 `parts_library.default.yaml`；项目真实 STEP、SolidWorks/Toolbox 或用户导入模型仍应通过项目前置规则覆盖默认 B 级模板。
- 新增线束模板只覆盖明确“线束 / harness / FFC”意图；普通拖链段、柔性同轴等未命中可复用线束模板时继续 `skip`，防止退回无意义盒子。
- 第二批常用模型库不使用裸 `滑块`、`M12`、`PC6/PC8` 等短 token 抢类别或路由；这些 token 只能在已有明确 family intent 后作为尺寸/针数/管径解析线索。
- 第三批常用模型库不使用裸 `DIN`、`阀`、`模块`、`支撑座`、`BK`、`BF` 或 `35mm` 抢类别/路由；只有类别和明确 family intent 同时成立才进入 B 级模板。
- 第四批常用模型库不使用裸 `柜`、`板`、`支架`、`接头`、`型材`、`真空`、`按钮`、`M12`、`2020` 或 `IP65` 抢类别/路由；只有类别和明确 family intent 同时成立才进入 B 级模板。
- 新增默认模型族必须同步更新 `docs/superpowers/specs/common_model_family_admission.json`；至少包含 positive、negative、route、precedence、dimension、geometry 六类代表性 case，并通过 `tests/test_common_model_family_admission.py`。
- 默认模型族准入不得把项目级 `part_no`、设备名、装配位置或某一次渲染修补写入 skill-wide 默认库；需要真实模型时优先走项目/用户 STEP、vendor cache、SolidWorks/Toolbox、bd_warehouse 或 PartCAD。
- 精确成熟模板优先于新增通用族模板；例如已有专用模板的型号不能被更宽的默认 family route 抢走。
- 默认尺寸查询支持 category-scoped key，防止 `material` 中的别族描述（例如泵的“电磁阀式”）覆盖 `name_cn` 中更具体的同类零件尺寸。
- 新增可复用模板必须保持生成几何不超过 `real_dims`，否则会污染后续装配、渲染和照片级增强的契约证据。
- `warning` 可以接受为 baseline，但应在看板或报告里明确剩余风险。
- 被 `.gitignore` 忽略的 `src/cad_spec_gen/data/*` 镜像仍由 `dev_sync.py` 维护；每轮结束必须跑 `python scripts/dev_sync.py --check`。`skill.json` metadata 现在也纳入同步/检查范围，避免安装版 skill 描述漂移。

## 下一步建议

1. Phase 6：设计最终交付包，把增强图、标注图、源渲染、证据报告和用户摘要放在一个可审计目录。
2. Phase 4：补 Blender 视觉回归和元件一致性检查，通用防止“新图比旧图少元件”这类问题。
3. Phase 5：继续扩展增强质量验收，覆盖多视角一致性、材质一致性和照片级质量评分。
4. Phase 2：按通用模型族准入清单继续扩展下一批常用件，不做单设备临时收紧。
5. Phase 1 -> Phase 6：继续简化新用户项目入口，把全流程串成少提问、多确认的项目向导。

## 验证记录

| 日期 | 命令 | 结果 |
| --- | --- | --- |
| 2026-05-05 | `git worktree add .worktrees\enhance-check-loop -b codex/enhance-check-loop` | 已创建增强执行 + enhance-check 闭环 worktree；旧独立 worktree `.worktrees/generic-threaded-photo-autopilot` 未触碰 |
| 2026-05-05 | `python scripts\dev_sync.py` / `python scripts\dev_sync.py --check` / `python -m pytest tests\test_photo3d_handoff.py tests\test_enhance_consistency.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | 新 worktree ignored mirror 填充后基线通过：`67 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py::test_photo3d_handoff_confirm_enhancement_runs_enhance_check_and_loop tests\test_photo3d_handoff.py::test_photo3d_handoff_confirm_enhancement_surfaces_blocked_enhance_check tests\test_photo3d_handoff.py::test_photo3d_handoff_confirm_enhancement_skips_check_when_enhance_fails -q` | 增强后自动复查闭环核心红绿测试最终 `3 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py::test_photo3d_handoff_confirm_enhancement_reports_followup_active_run_drift -q` | 红测阶段无 `PHOTO3D_HANDOFF.json` 报告；实现后 follow-up run 漂移写入 `execution_failed` 和 `followup_action.stderr` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py tests\test_enhance_consistency.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py -q` | 当前聚焦回归 `46 passed` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 增强闭环同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_user_flow.py::test_photo3d_handoff_help_explains_confirmed_handoff_flow tests\test_photo3d_user_flow.py::test_cad_help_docs_describe_photo3d_foolproof_user_flow tests\test_photo3d_user_flow.py::test_skill_metadata_advertises_photo3d_and_llm_action_reports -q` | 文档/metadata 增强闭环指引 `3 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py tests\test_enhance_consistency.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 增强闭环范围回归 `206 passed` |
| 2026-05-05 | `git diff --check` | 通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git merge --ff-only codex/enhance-check-loop` | 增强闭环已快进合并到 `main`，功能提交 `ec92cb2` |
| 2026-05-05 | `python scripts\dev_sync.py --check` / `python -m pytest tests\test_photo3d_handoff.py tests\test_enhance_consistency.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` / `git diff --check` | 合并到 `main` 后通过：`206 passed`，无同步漂移，空白检查通过 |
| 2026-05-05 | `git worktree add .worktrees\provider-health-check -b codex/provider-health-check` | 已创建 provider 配置健康检查 worktree；旧独立 worktree `.worktrees/generic-threaded-photo-autopilot` 未触碰 |
| 2026-05-05 | `python scripts\dev_sync.py --check` / `python -m pytest tests\test_project_guide.py tests\test_photo3d_provider_presets.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | 新 worktree ignored mirror 填充后基线通过：`25 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_provider_health.py tests\test_project_guide.py::test_project_guide_provider_wizard_embeds_safe_provider_health tests\test_photo3d_user_flow.py::test_project_guide_help_explains_read_only_user_flow tests\test_photo3d_user_flow.py::test_cad_help_docs_describe_photo3d_foolproof_user_flow tests\test_photo3d_user_flow.py::test_skill_metadata_advertises_photo3d_and_llm_action_reports -q` | 红测阶段因缺少 `photo3d_provider_health`、`provider_wizard.health_summary` 和文档/metadata `provider_health` 指引失败 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_provider_health.py tests\test_project_guide.py::test_project_guide_provider_wizard_embeds_safe_provider_health tests\test_project_guide.py::test_project_guide_exposes_provider_choices_when_ready_for_enhancement -q` | provider health 核心实现后 `4 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_provider_health.py::test_provider_health_default_follows_configured_backend -q` | 红测阶段发现 `default` 不能固定可用；实现后跟随 `pipeline_config.json` 默认 backend 健康状态 |
| 2026-05-05 | `python scripts\dev_sync.py --check` | provider health 同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_provider_health.py tests\test_project_guide.py tests\test_photo3d_provider_presets.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | provider health 范围回归 `164 passed` |
| 2026-05-05 | `git diff --check` | provider health 分支空白检查通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git worktree add .worktrees\provider-ui-wizard -b codex/provider-ui-wizard` | 已创建 provider UI wizard worktree；旧独立 worktree `.worktrees/generic-threaded-photo-autopilot` 未触碰 |
| 2026-05-05 | `python scripts\dev_sync.py --check` / `python -m pytest tests\test_project_guide.py tests\test_photo3d_provider_presets.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | 新 worktree ignored mirror 填充后基线通过：`25 passed` |
| 2026-05-05 | `python -m pytest tests\test_project_guide.py::test_project_guide_exposes_provider_choices_when_ready_for_enhancement tests\test_project_guide.py::test_project_guide_ignores_stale_provider_choice_report -q` | 红测阶段因缺少 `provider_wizard` 失败；实现后相关测试通过 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_user_flow.py::test_project_guide_help_explains_read_only_user_flow tests\test_photo3d_user_flow.py::test_cad_help_docs_describe_photo3d_foolproof_user_flow tests\test_photo3d_user_flow.py::test_skill_metadata_advertises_photo3d_and_llm_action_reports -q` | 文档/metadata `provider_wizard` 指引 `3 passed` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | provider UI wizard 分支同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_project_guide.py tests\test_photo3d_provider_presets.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | provider UI wizard 分支范围回归 `159 passed` |
| 2026-05-05 | `git diff --check` | provider UI wizard 分支空白检查通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git worktree add .worktrees\phase-progress-board -b codex/phase-progress-board` | 已创建看板重构 worktree；旧独立 worktree `.worktrees/generic-threaded-photo-autopilot` 未触碰 |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 看板重构后同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 看板重构后文档/包装范围回归 `137 passed` |
| 2026-05-05 | `git diff --check` | 看板重构后空白检查通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git worktree add .worktrees\provider-choice-user-copy -b codex/provider-choice-user-copy` | 已创建 provider 选项文案 worktree |
| 2026-05-05 | `python -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | 新 worktree ignored mirror 填充后基线 `23 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_provider_presets.py -q` | 红测阶段因缺少 `ordinary_user_title` 等字段失败；实现后 `2 passed` |
| 2026-05-05 | `python -m pytest tests\test_project_guide.py::test_project_guide_exposes_provider_choices_when_ready_for_enhancement -q` | 红测阶段因缺少 `ordinary_user_options` 失败；实现后通过 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_user_flow.py::test_cad_help_docs_describe_photo3d_foolproof_user_flow tests\test_photo3d_user_flow.py::test_skill_metadata_advertises_photo3d_and_llm_action_reports -q` | 文档/metadata `ordinary_user_options` 指引 `2 passed` |
| 2026-05-05 | `python scripts\dev_sync.py` | 已同步 provider presets、project guide、CLI、cad-help 和 skill metadata 安装版镜像 |
| 2026-05-05 | `python scripts\dev_sync.py --check` | provider 选项文案分支同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_provider_presets.py tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | provider 选项文案分支范围回归 `159 passed` |
| 2026-05-05 | `git diff --check` | provider 选项文案分支空白检查通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git commit -m "feat(photo3d): 增加 provider 普通用户选项"` | 已提交功能分支实现 `bfae729` |
| 2026-05-05 | `git merge --ff-only codex/provider-choice-user-copy` | 已快进合并到 `main` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_provider_presets.py tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `159 passed` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 合并到 `main` 后通过；安装版镜像无漂移 |
| 2026-05-05 | `git diff --check` | 合并到 `main` 后通过 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 进度文档收尾后 `137 passed` |
| 2026-05-05 | `git commit -m "docs(progress): 记录 provider 普通用户选项合并验证"` | 已提交合并验证记录 `e3e93d1` |
| 2026-05-05 | `git push origin main` | 已推送 `main` 到远端，`5cc48fe..e3e93d1` |
| 2026-05-05 | `git worktree remove .worktrees\provider-choice-user-copy`；`git branch -d codex/provider-choice-user-copy`；`git worktree prune` | 已清理 provider 选项文案 worktree/分支；保留另一个含未提交改动的独立 worktree |
| 2026-05-05 | `git worktree add .worktrees\project-guide-provider-presets -b codex/project-guide-provider-presets` | 已创建 project-guide provider preset worktree |
| 2026-05-05 | `python -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | 新 worktree ignored mirror 填充后基线 `21 passed` |
| 2026-05-05 | `python -m pytest tests\test_project_guide.py -q` | 先红后绿，最终 `10 passed`；覆盖 `provider_choice` 只在当前 run 增强入口出现，且过期 run 报告不会污染项目向导 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_user_flow.py::test_cad_help_docs_describe_photo3d_foolproof_user_flow tests\test_photo3d_user_flow.py::test_skill_metadata_advertises_photo3d_and_llm_action_reports -q` | 文档/metadata provider preset 指引 `2 passed` |
| 2026-05-05 | `python scripts\dev_sync.py` | 已同步 `project_guide.py`、`cad_pipeline.py`、cad-help 文档和 skill metadata 的安装版镜像 |
| 2026-05-05 | `python scripts\dev_sync.py --check` | project-guide provider preset 分支同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | project-guide provider preset 分支范围回归 `157 passed` |
| 2026-05-05 | `git diff --check` | project-guide provider preset 分支空白检查通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git commit -m "feat(project-guide): 增加增强 provider preset 选择"` | 已提交功能分支实现 `1ce807a` |
| 2026-05-05 | `git merge --ff-only codex/project-guide-provider-presets` | 已快进合并到 `main` |
| 2026-05-05 | `python -m pytest tests\test_project_guide.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `157 passed` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 合并到 `main` 后通过；安装版镜像无漂移 |
| 2026-05-05 | `git diff --check` | 合并到 `main` 后通过 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 进度文档收尾后 `137 passed` |
| 2026-05-05 | `git commit -m "docs(progress): 记录 project-guide provider preset 合并验证"` | 已提交合并验证记录 `431edb2` |
| 2026-05-05 | `git push origin main` | 已推送 `main` 到远端，`e955905..431edb2` |
| 2026-05-05 | `git worktree remove .worktrees\project-guide-provider-presets`；`git branch -d codex/project-guide-provider-presets`；`git worktree prune` | 已清理 project-guide provider preset worktree/分支；保留另一个含未提交改动的独立 worktree |
| 2026-05-05 | `git worktree add .worktrees\model-family-admission -b codex/model-family-admission` | 已创建通用模型族准入 worktree |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 本轮 worktree 基线 `411 passed, 7 warnings` |
| 2026-05-05 | `python -m pytest tests\test_common_model_family_admission.py -q` | 红测阶段因缺少 admission manifest/runbook 失败；补齐后 `8 passed, 7 warnings` |
| 2026-05-05 | `python -m pytest tests\test_common_model_family_admission.py tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_jinja_generators_new.py -q` | 准入清单范围回归 `286 passed, 7 warnings` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 准入清单同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `git diff --check` | 准入清单空白检查通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git merge --ff-only codex/model-family-admission` | 准入清单已快进合并到 `main` |
| 2026-05-05 | `python -m pytest tests\test_common_model_family_admission.py tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_jinja_generators_new.py -q` | 合并到 `main` 后 `286 passed, 7 warnings` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 合并到 `main` 后通过；安装版镜像无漂移 |
| 2026-05-05 | `git diff --check` | 合并到 `main` 后通过 |
| 2026-05-05 | `git worktree add .worktrees\photo3d-provider-presets -b codex/photo3d-provider-presets` | 已创建 Photo3D provider preset worktree |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py -q` | 新 worktree 初始化前因 ignored mirror 缺失失败；运行 `python scripts\dev_sync.py` 填充镜像后基线 `23 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_autopilot.py::test_cmd_photo3d_autopilot_with_accepted_baseline_recommends_enhancement tests\test_photo3d_handoff.py::test_photo3d_handoff_preview_enhancement_appends_trusted_provider_preset tests\test_photo3d_handoff.py::test_photo3d_handoff_rejects_unknown_provider_preset tests\test_photo3d_user_flow.py::test_photo3d_handoff_help_explains_confirmed_handoff_flow -q` | 红测阶段覆盖缺 `provider_presets`、缺 preset argv、安全阻断和 help 缺参；实现后相关用例通过 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py -q` | handoff provider preset 回归 `13 passed`；覆盖默认 preset、CLI override、JSON provider_preset、恶意 JSON argv 不可信、未知 preset 阻断 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_user_flow.py::test_cad_help_docs_describe_photo3d_foolproof_user_flow tests\test_photo3d_user_flow.py::test_skill_metadata_advertises_photo3d_and_llm_action_reports tests\test_photo3d_user_flow.py::test_photo3d_handoff_help_explains_confirmed_handoff_flow -q` | 文档/metadata/provider preset 帮助 `3 passed` |
| 2026-05-05 | `python scripts\dev_sync.py` | 已同步 `cad_pipeline.py`、Photo3D tools、cad-help、skill metadata 的安装版镜像 |
| 2026-05-05 | `python scripts\dev_sync.py --check` | provider preset 分支同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | provider preset 分支范围回归 `179 passed` |
| 2026-05-05 | `git diff --check` | provider preset 分支空白检查通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git commit -m "feat(photo3d): 增加增强 provider preset 交接"` | 已提交 provider preset 功能分支实现 `bdf4c26` |
| 2026-05-05 | `git merge --ff-only codex/photo3d-provider-presets` | 已快进合并到 `main` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_autopilot.py tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `179 passed` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 合并到 `main` 后通过；安装版镜像无漂移 |
| 2026-05-05 | `git diff --check` | 合并到 `main` 后通过 |
| 2026-05-05 | `git commit -m "docs(progress): 记录 provider preset 合并验证"` | 已提交合并验证记录 `55be4af` |
| 2026-05-05 | `git push origin main` | 已推送 `main` 到远端，`ac9168f..55be4af` |
| 2026-05-05 | `git worktree remove .worktrees\photo3d-provider-presets`；`git branch -d codex/photo3d-provider-presets` | 已清理 provider preset worktree/分支；保留另一个含未提交改动的独立 worktree |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 推送和清理后复查通过；安装版镜像无漂移 |
| 2026-05-05 | `git worktree add .worktrees\photo3d-interactive-actions -b codex/photo3d-interactive-actions` | 已创建确认式 handoff worktree |
| 2026-05-05 | `python -m pytest tests\test_photo3d_loop.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 新 worktree 初始化前因 ignored mirror 缺失出现 dev_sync mirror 失败；运行 `python scripts\dev_sync.py` 填充后同命令 `149 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_user_flow.py::test_photo3d_handoff_help_explains_confirmed_handoff_flow tests\test_photo3d_packaging_sync.py::test_photo3d_contract_tools_have_packaged_mirrors -q` | 红测阶段 `10 failed`；实现后当前 `10 passed` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py::test_photo3d_handoff_rejects_terminal_delivery_action tests\test_photo3d_handoff.py::test_photo3d_handoff_confirm_unknown_action_is_blocked -q` | 返回码语义红绿测试；最终 `2 passed`，已知人工动作不再当命令失败，未知动作仍阻断 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py::test_photo3d_handoff_rejects_mismatched_enhance_check_manifest tests\test_photo3d_handoff.py::test_photo3d_handoff_confirm_enhance_check_uses_active_render_dir -q` | manifest 漂移红绿测试；最终 `2 passed`，显式旧 run manifest 阻断，当前 run manifest 才执行 |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_loop.py tests\test_photo3d_autopilot.py tests\test_photo3d_action_runner.py tests\test_photo3d_accept_baseline.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 功能分支范围回归 `202 passed` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 功能分支同步检查通过；安装版镜像无漂移 |
| 2026-05-05 | `git diff --check` | 功能分支空白检查通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git commit -m "feat(photo3d): 增加确认式下一步交接入口"` | 已提交功能分支实现 `92347c6` |
| 2026-05-05 | `git merge --ff-only codex/photo3d-interactive-actions` | 已快进合并到 `main` |
| 2026-05-05 | `python -m pytest tests\test_photo3d_handoff.py tests\test_photo3d_loop.py tests\test_photo3d_autopilot.py tests\test_photo3d_action_runner.py tests\test_photo3d_accept_baseline.py tests\test_photo3d_user_flow.py tests\test_photo3d_packaging_sync.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 合并到 `main` 后 `202 passed` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 合并到 `main` 后通过；安装版镜像无漂移 |
| 2026-05-05 | `git diff --check` | 合并到 `main` 后通过 |
| 2026-05-05 | `git commit -m "docs(progress): 记录 handoff 合并验证"` | 已提交合并验证记录 `66f6fda` |
| 2026-05-05 | `git push origin main` | 已推送 `main` 到远端，`c74f56d..66f6fda` |
| 2026-05-05 | `git worktree remove .worktrees\photo3d-interactive-actions`；`git branch -d codex/photo3d-interactive-actions` | 已清理 handoff worktree/分支；保留另一个含未提交改动的独立 worktree |
| 2026-05-05 | `git worktree add .worktrees\common-model-library-batch-4 -b codex/common-model-library-batch-4` | 已创建第四批计划 worktree |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py -q` | 第四批 worktree 基线 `141 passed, 7 warnings` |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_4.py tests\test_parts_library_standard_categories.py -q` | 先红后绿，最终 `73 passed, 7 warnings`；覆盖第四批分类、模板、负例、默认路由和包络不超 `real_dims` |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py -q` | 第四批范围回归 `323 passed, 2 skipped, 11 warnings` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 第四批同步后通过；安装版镜像无漂移 |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 第四批最终回归 `454 passed, 2 skipped, 11 warnings` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 第四批最终同步检查通过 |
| 2026-05-05 | `git diff --check` | 第四批最终空白检查通过 |
| 2026-05-05 | `git commit -m "feat(parts-library): 扩展常用模型库第四批"` | 已提交第四批实现 `c4226a3` |
| 2026-05-05 | `git merge --ff-only codex/common-model-library-batch-4` | 第四批已快进合并到 `main` |
| 2026-05-05 | `python -m pytest tests\test_common_model_library_batch_4.py tests\test_common_model_library_batch_3.py tests\test_common_model_library_batch_2.py tests\test_common_model_library_expansion.py tests\test_parts_library_standard_categories.py tests\test_parts_adapters.py tests\test_jinja_generators_new.py tests\test_dev_sync_check.py tests\test_data_dir_sync.py -q` | 第四批合并到 `main` 后 `454 passed, 2 skipped, 11 warnings` |
| 2026-05-05 | `python scripts\dev_sync.py --check` | 第四批合并到 `main` 后通过 |
| 2026-05-05 | `git diff --check` | 第四批合并到 `main` 后通过；仅 Windows 行尾提示 |
| 2026-05-05 | `git commit -m "docs(progress): 记录第四批模型库合并验证"` | 已提交合并验证记录 `c515536` |
| 2026-05-05 | `git push origin main` | 已推送 `main` 到远端，`d07c30c..c515536` |
| 2026-05-05 | `git worktree remove .worktrees\common-model-library-batch-4`；`git branch -d codex/common-model-library-batch-4` | 已清理第四批已合并 worktree/分支；保留另一个含未提交改动的独立 worktree |
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
