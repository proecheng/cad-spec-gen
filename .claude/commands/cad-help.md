# /cad-help — CAD 混合渲染管线交互式帮助

用户输入: $ARGUMENTS

## 指令

读取技能文档 `skill_cad_help.md`（项目根目录），然后根据用户输入执行：

### 路由规则

1. **无参数**（`$ARGUMENTS` 为空）→ 显示帮助面板：
   - 按 skill_cad_help.md 末尾"帮助面板"模板输出
   - 列出常见问题示例，分为4组：环境与安装 / 配置与验证 / 工作流 / 状态与排错

2. **有参数** → 意图匹配 + 执行：
   - 从 `$ARGUMENTS` 文本提取关键词
   - 对照 skill_cad_help.md 中的"意图匹配表"，选择最佳匹配意图
   - 按该意图的"动作详情"执行（能跑程序的直接跑，需引导的分步展开）
   - 如果匹配不到任何意图，回复"未能理解您的问题"并显示帮助面板

3. **Photo3D / 照片级一键出图请求**（当用户说 project-guide、photo3d、photo3d-run、photo3d-autopilot、photo3d-action、render-visual-check、render-quality-check、enhance-review、照片级、傻瓜式出图、pass/warning/blocked、accepted/preview/blocked、run_id、baseline、动作计划或让其他大模型继续时）：

   - 普通用户和大模型首选只读入口：`python cad_pipeline.py project-guide --subsystem <name> --design-doc <path>`。它写 `PROJECT_GUIDE.json`，在 `init`、`spec`、`codegen`、`build --render`、`photo3d-run` 之间选择下一条安全命令；当前 active run 到 `ready_for_enhancement` 时，可附带白名单 provider preset 选择、普通用户可读选项 `ordinary_user_options`、展示向导 `provider_wizard`、安全配置健康状态 `provider_health` 和 `photo3d-handoff --provider-preset <id>` 预览命令。`ordinary_user_options` 要展示“默认 / 本地工程预览 / 云增强”等标题、说明、适用场景、是否需要配置和健康状态，让用户选项而不是手写 `--backend`；`provider_wizard` 把这些白名单选项组织成 UI/大模型可直接展示的步骤、默认项、预览动作和健康摘要。`provider_health` 只检查本地配置/依赖存在性，不运行增强、不扫描输出目录、不改状态，不暴露环境变量名、key 值、URL、endpoint 或 secret。它 read-only，does not scan directories，does not mutate pipeline state，不接受 baseline，不运行增强，不追加 `--confirm`，也不接受任意 backend、URL、API key、endpoint、模型名或 JSON argv 注入。
   - 已有 active run 后推荐命令：`python cad_pipeline.py photo3d-run --subsystem <name>`；底层单轮报告：`python cad_pipeline.py photo3d-autopilot --subsystem <name>`；底层门禁命令：`python cad_pipeline.py photo3d --subsystem <name>`。
   - Phase 4 渲染视觉/元件一致性检查：`python cad_pipeline.py render-visual-check --subsystem <name>`。它只读取 `ARTIFACT_INDEX.json.active_run_id` 绑定的 `PRODUCT_GRAPH.json`、`ASSEMBLY_SIGNATURE.json` 和 `render_manifest.json`，并写 `RENDER_VISUAL_REGRESSION.json` 到当前 run 目录；有 `accepted_baseline_run_id` 时比较 baseline 的视角、渲染文件、装配实例和可选逐视角实例证据。没有 accepted baseline 时仍检查当前 run 的路径、hash、render_dir、重复视角和产品实例覆盖；如果缺少逐视角实例证据，只能给 warning，不能声称图片内每个元件身份已被证明。它 does not scan directories，不猜最新 PNG，不换 run。
   - Phase 4 Blender 预检和截图/像素质量检查：`python cad_pipeline.py render-quality-check --subsystem <name>`。它只读取 `ARTIFACT_INDEX.json.active_run_id` 绑定的当前 `render_manifest.json`，并写 `RENDER_QUALITY_REPORT.json` 到当前 run 目录；报告包含 `blender_preflight`、`render_quality_summary` 和逐视角 `pixel_metrics`，用于检查 Blender 可执行文件/版本、渲染文件路径和 hash、基础 QA、画布尺寸、主体占比、亮度、对比度、饱和度、边缘密度。缺 Blender、缺图、路径越界、hash 漂移或基础 QA 失败会 blocked；低对比度、边缘密度低或多视角画布不一致是 warning。它是确定性像素证据，不是语义 AI 识别；does not scan directories，不猜最新 PNG，不换 run，也不允许 `render_manifest.json.run_id` 覆盖 `active_run_id`。
   - 运行前确认目标子系统；不要用产品名、目录名相似度或旧 PNG 猜测目标。
   - 这些命令只读取当前 `run_id` 在 `ARTIFACT_INDEX.json` 中登记的产物，不能扫描目录猜最新文件。
   - `photo3d-run` 是傻瓜式多轮向导：它连续运行 `photo3d` gate + `photo3d-autopilot`，写 `PHOTO3D_RUN.json`，并停在 `needs_baseline_acceptance`、`ready_for_enhancement`、`needs_user_input`、`needs_manual_review`、`execution_failed` 或 `loop_limit_reached`。它不会静默接受 baseline，不会运行 enhance，不会切换 `active_run_id`。只有用户明确同意时，才运行 `python cad_pipeline.py photo3d-run --subsystem <name> --confirm-actions`，让向导通过 `photo3d-action` 执行 low-risk 恢复动作。
   - `photo3d-autopilot` 会先运行 `photo3d` 门禁，再写 `PHOTO3D_AUTOPILOT.json`：`blocked` 时指向 `ACTION_PLAN.json` / `LLM_CONTEXT_PACK.json`；`pass` / `warning` 且没有 accepted baseline 时，只建议用户确认后显式运行 `python cad_pipeline.py accept-baseline --subsystem <name>`；已有 `accepted_baseline_run_id` 时，才建议进入增强。它不会静默接受 baseline，也不会切换 `active_run_id`。
   - `photo3d-action` 是确认后执行层：默认 `python cad_pipeline.py photo3d-action --subsystem <name>` 只预览并写 `PHOTO3D_ACTION_RUN.json`；用户确认后才运行 `python cad_pipeline.py photo3d-action --subsystem <name> --confirm`。它只执行当前 `active_run_id` 的 `ACTION_PLAN.json` 中 low-risk、无需用户输入、白名单内的 `product-graph` / `build` / `render` CLI 动作；这些 CLI 必须写成 run-aware wrapper：`python cad_pipeline.py photo3d-recover --subsystem <name> --run-id <run_id> --artifact-index cad/<name>/.cad-spec-gen/ARTIFACT_INDEX.json --action product-graph|build|render`，禁止回退到裸 `product-graph` / `build` / `render --subsystem <name>`。用户输入类动作继续询问用户。它不会扫描目录猜最新文件，不会运行增强，也不会接受 baseline。当 `--confirm` 的 low-risk CLI 全部成功，且没有用户输入、人工复查或 rejected actions 时，它会自动重跑 `photo3d-autopilot`，并把下一步摘要写入 `PHOTO3D_ACTION_RUN.json` 的 `post_action_autopilot`；preview、执行失败、仍有用户输入或 rejected actions 时不会自动重跑。
   - `photo3d-handoff` 是普通用户/大模型“按建议执行”的确认交接入口：默认 `python cad_pipeline.py photo3d-handoff --subsystem <name>` 只读取当前 `PHOTO3D_RUN.json` / `PHOTO3D_AUTOPILOT.json` 并写 `PHOTO3D_HANDOFF.json`；用户确认后才运行 `python cad_pipeline.py photo3d-handoff --subsystem <name> --confirm`。它只执行识别到的当前 `next_action`：`accept-baseline`、`enhance`、`enhance-check` 或 `photo3d-run --confirm-actions`。增强动作可传 `--provider-preset default|engineering|gemini|fal|fal_comfy|comfyui`，例如离线预览用 `python cad_pipeline.py photo3d-handoff --subsystem <name> --provider-preset engineering --confirm`；preset 是白名单，只映射到已支持的 `enhance --backend/--model`，禁止通过 JSON argv 注入任意 backend、URL、API key 或未来模型名。增强执行成功后，它会自动运行同一 active run/render dir 的 `enhance-check`，把复查 subprocess 写入 `PHOTO3D_HANDOFF.json.followup_action`，再无确认重跑一次 `photo3d-run`，把 accepted/preview/blocked 状态写入 `PHOTO3D_HANDOFF.json.post_handoff_photo3d_run`；`executed_with_followup` 表示增强和同 run 验收闭环已完成。它不会扫描目录猜最新文件，不会信任 JSON 里的任意 argv，而是用 `ARTIFACT_INDEX.json`、当前 `active_run_id` 和当前 run/render 路径重构命令。
   - 解释门禁状态（Gate status）：
     - `pass`：CAD 契约门禁通过，可以进入增强阶段。
     - `warning`：CAD 契约门禁通过但有非阻断警告，只能带着警告进入增强或先人工复核。
     - `blocked`：CAD 契约门禁失败，不运行 AI 增强。
   - 解释增强交付状态（Enhancement delivery status，增强完成后的上层语义）：
     - `accepted`：CAD 门禁和增强一致性都通过，可作为照片级交付图。
     - `preview`：CAD 门禁通过，但增强一致性未验证或未通过，只能作为预览。
     - `blocked`：CAD 门禁失败，增强不得执行。
     - 当前门禁阶段的 `PHOTO3D_REPORT.json` 只会把 `enhancement_status` 写成 `not_run` 或 `blocked`；`accepted` / `preview` 属于后续增强交付层。
     - 增强完成后运行 `python cad_pipeline.py enhance-check --subsystem <name> --dir <render_dir>`，只读取显式 render dir 的 `render_manifest.json` 和同目录 `*_enhanced.*`，写 `ENHANCEMENT_REPORT.json`。它要求每个 manifest 视角都有增强图，并检查轮廓相似度、基础图片 QA 和 deterministic multi-view quality；报告包含 `quality_summary`，记录多视角画布一致性、对比度、亮度、饱和度、主体占比等质量证据。它不会扫描目录猜最新文件，也不会接受 render dir 外的增强图。普通用户通过 `photo3d-handoff --confirm` 执行增强时不需要手动运行这一条，handoff 会自动运行并把结果回读到 `post_handoff_photo3d_run`。
     - 如果需要人工/大模型做语义结构、材质一致性和照片级主观复核，运行 `python cad_pipeline.py enhance-review --subsystem <name> --review-input <json>`。该命令只接收显式 review JSON，校验 `run_id`、`subsystem`、`render_manifest.json`、`ENHANCEMENT_REPORT.json` 的路径和 sha256，并按视角检查 `geometry_preserved`、`material_consistent`、`photorealistic`、`no_extra_parts`、`no_missing_parts`，写 `ENHANCEMENT_REVIEW_REPORT.json.semantic_material_review`。它不调用 AI、不接受 backend/model/key/url、不扫描目录、不用复核结果修 CAD 几何；`accepted` 可作为照片级复核证据，`preview` 只能预览，`needs_review` 表示复核输入不完整，`blocked` 表示证据漂移。
   - 最终交付包：当 `ENHANCEMENT_REPORT.json` 为 `accepted` 且 `quality_summary.status` 为 `accepted`，运行 `python cad_pipeline.py photo3d-deliver --subsystem <name>`。它只读取当前 `ARTIFACT_INDEX.json.active_run_id` 绑定的 `render_manifest.json`、`ENHANCEMENT_REPORT.json`、`ENHANCEMENT_REVIEW_REPORT.json`（如存在）、`PHOTO3D_RUN.json` 和契约证据，写 `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/delivery/DELIVERY_PACKAGE.json` 与 `README.md`。默认只有增强状态和 `quality_summary` 都 accepted 才复制最终增强图、源渲染图和可唯一识别的标注图；如果同一 run 已有 `semantic_material_review` 且不是 accepted，或传 `--require-semantic-review` 但缺少 accepted 复核，也只写证据报告，不标记 `final_deliverable`。`preview` / `blocked` 或质量未通过只写证据报告，并记录 `photo_quality_not_accepted` 或 `semantic_review_not_accepted`。它不会扫描目录猜最新文件，不会换 run，也不会接受 subsystem/run_id/render_manifest 漂移；如确实需要预览包，显式传 `--include-preview`，但 `final_deliverable` 仍为 false。
   - 阻断时读取并解释：
     - `PROJECT_GUIDE.json`：只读项目级下一步报告，覆盖 `init/spec/codegen/build-render/photo3d-run` 的交接；到增强入口时可附带白名单 provider preset 选择、普通用户可读选项 `ordinary_user_options`、展示向导 `provider_wizard`、安全配置健康状态 `provider_health` 和 `photo3d-handoff --provider-preset <id>` 预览命令。
     - `RENDER_VISUAL_REGRESSION.json`：`render-visual-check` 的 Phase 4 渲染视觉/元件一致性报告，记录当前 run 与 accepted baseline 的视角、渲染文件、装配实例和逐视角实例证据差异。
     - `RENDER_QUALITY_REPORT.json`：`render-quality-check` 的 Phase 4 Blender 和截图质量报告，记录 `blender_preflight`、`render_quality_summary` 和逐视角 `pixel_metrics`。
     - `PHOTO3D_REPORT.json`：普通用户中文阻断原因。
     - `PHOTO3D_AUTOPILOT.json`：普通用户本轮下一步报告。
     - `ACTION_PLAN.json`：允许大模型执行的下一步动作。
     - `LLM_CONTEXT_PACK.json`：给其他大模型的当前 run 最小上下文。
     - `PHOTO3D_ACTION_RUN.json`：`photo3d-action` 的预览/执行报告，列出 executable/user_input/rejected/executed actions；`post_action_autopilot` 记录成功确认执行后的自动重跑摘要。
     - `PHOTO3D_HANDOFF.json`：`photo3d-handoff` 的预览/执行报告，记录当前来源报告、重构后的安全 argv、执行结果、增强后的 `followup_action`、`post_handoff_photo3d_run`、`executed_with_followup` 或人工处理原因。
     - `PHOTO3D_RUN.json`：`photo3d-run` 的多轮向导报告，列出每轮 gate/autopilot/action 状态、最终停止原因和下一步。
     - `ENHANCEMENT_REPORT.json`：增强交付验收报告，逐视角记录源图、增强图、相似度、QA、`quality_summary` 和 `accepted` / `preview` / `blocked`。
     - `ENHANCEMENT_REVIEW_REPORT.json`：显式人工/大模型复核报告，记录 `semantic_material_review`、源报告路径/hash、逐视角语义结构和材质复核结果。
     - `DELIVERY_PACKAGE.json`：`photo3d-deliver` 的最终交付包清单，记录源报告、源渲染图、增强图、标注图、证据文件、质量摘要、`photo_quality_not_accepted` 等阻断原因和 `final_deliverable` 状态。
   - 路径隔离：每次运行都有独立 `run_id`；契约在 `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/`，渲染图在 `cad/output/renders/<subsystem>/<run_id>/`。
   - 旧产物清理：只能清理不再被 `active_run_id` 引用的旧 run/render 目录，不能把旧 PNG 当成本轮通过证据。
   - 接受基准：首次 `pass` 只作为候选基准；用户确认当前 `PHOTO3D_REPORT.json` 后，运行 `python cad_pipeline.py accept-baseline --subsystem <name>`。报告会记录关键契约的 `artifact_hashes`；命令只接受 `pass` / `warning` 报告，并校验报告路径、artifact 路径和当前文件哈希都与 `ARTIFACT_INDEX.json` 中同一 run 一致，再把 `run_id` 写入 `accepted_baseline_run_id`。它不会切换 `active_run_id`，也不会扫描目录猜最新产物；需要指定历史 run 时传 `--run-id <run_id>`。
   - 基线复用：后续 `photo3d --change-scope <CHANGE_SCOPE.json>` 会自动使用 `accepted_baseline_run_id` 对应的 `ASSEMBLY_SIGNATURE.json`；仍可用 `--baseline-signature <path>` 显式覆盖。
   - 漂移处理：后续用 `baseline` / `CHANGE_SCOPE.json` 检查实例数量、bbox、位置和旋转漂移；未授权漂移保持 `blocked`，有意变更必须写入 `CHANGE_SCOPE.json` 并标注为 authorized。
   - 大模型优先运行/读取 `photo3d-run` 和 `PHOTO3D_RUN.json`；Phase 4 证据要分清：`render-visual-check` 证明视角/元件契约，`render-quality-check` 证明 Blender 环境和截图像素质量，二者都只读当前 active run。用户说“按建议执行”时优先走 `photo3d-handoff` 预览/确认交接。用户要选增强后端时只用 `--provider-preset` 白名单值，例如 `engineering`，不要手写 `--backend` 或复制 JSON 里的任意 argv。增强确认执行后读取 `PHOTO3D_HANDOFF.json.post_handoff_photo3d_run` 和 `ENHANCEMENT_REPORT.json`，不要扫描 render 目录猜最新增强图；如用户或流程要求语义/材质级照片级判断，先生成显式 review JSON，再运行 `enhance-review`，不要让任意模型直接改管线状态。当状态为 `enhancement_accepted` 时运行 `photo3d-deliver` 生成 `DELIVERY_PACKAGE.json`，需要强制语义/材质复核时加 `--require-semantic-review`，不要手工复制图片。需要分步执行 blocked 恢复动作时只能依据 `ACTION_PLAN.json` 执行。低风险 CLI 恢复动作走 `photo3d-action` 预览/确认执行，底层命令必须经 `photo3d-recover --run-id <run_id> --artifact-index <path>` 绑定当前 run。如果动作需要用户输入，询问用户，不要虚构路径或模型。

4. **全管线请求**（当用户要求绘图/渲染/全部流程/走全流程/全管线/full pipeline，或请求同时生成2D+3D产物时）：

   #### Step 0 — 产物扫描 + 阶段总览（必须先执行）

   扫描目标子系统目录，向用户展示各阶段产物状态，等待用户选择后再执行。**禁止跳过此步骤。**

   **扫描逻辑**：
   ```
   Phase 1  SPEC      → 检查 cad/<subsystem>/CAD_SPEC.md 是否存在 + mtime
   Phase 2  CODEGEN   → 检查 cad/<subsystem>/build_all.py, params.py, assembly.py 是否存在
   Phase 3  BUILD     → 检查 cad/output/ 下是否有该子系统的 .step/.glb/.png(DXF→PNG) 文件 + mtime
   Phase 4  RENDER    → 检查 cad/output/renders/ 下是否有该子系统的 V*.png + 数量 + mtime
   Phase 5  ENHANCE   → 检查是否有 *_enhanced.* 文件
   Phase 6  ANNOTATE  → 检查是否有 *_labeled_*.png 文件
   ```

   **输出格式**（示例）：
   ```
   === 丝杠式升降平台 (lifting_platform) — 管线状态 ===

   Phase 1  SPEC       ✅ CAD_SPEC.md (2026-03-29)
   Phase 2  CODEGEN    ✅ build_all.py + params.py + 7个 draw_*.py
   Phase 3  BUILD      ✅ SLP-000_assembly.glb (2026-03-31)
   Phase 4  RENDER     ✅ 7个 PNG (2026-03-31 14:03)
   Phase 5  ENHANCE    ❌ 无增强图
   Phase 6  ANNOTATE   ❌ 无标注图

   请选择起点：
     A. 完全从头重建（覆盖所有已有产物，从 Phase 1 SPEC 开始）
     B. 从 Phase 5 ENHANCE 续跑（保留已有 SPEC/代码/GLB/PNG）
     C. 仅重建指定阶段（请说明阶段编号，如 "3 4" 表示重跑 BUILD + RENDER）
   ```

   **选项生成规则**：
   - 选项 A 始终存在：完全从头重建
   - 选项 B 自动计算：找到第一个 ❌ 阶段，建议从该阶段开始续跑
   - 选项 C 始终存在：用户自由指定阶段
   - 如果全部阶段都是 ✅，选项 B 改为"全部产物已存在，是否重建？"

   **等待用户回复后，按选择执行对应阶段。**

   #### Step 1 — 执行选定阶段

   根据用户在 Step 0 的选择：

   - **选 A（完全从头）**→ 按原有全管线流程执行：
     1. 运行 Phase 1 SPEC（`--force --review`）强制重新生成
     2. **必须**读取 `DESIGN_REVIEW.json` 并向用户展示审查摘要（CRITICAL/WARNING/INFO/OK 计数 + WARNING 条目详情）
     3. 提供 3 选项让用户选择：
        - 「继续审查」→ 逐项讨论 WARNING/CRITICAL，用户可调整参数
        - 「自动补全」→ 运行 `--auto-fill` 后继续后续阶段
        - 「下一步」→ 按现有数据直接继续 Phase 2+
     4. 用户确认后，询问 enhance 后端（gemini/comfyui），再执行后续阶段：
        - Phase 2: `codegen --force`（强制覆盖已有代码）
        - Phase 3: `build`（重新生成 STEP + GLB，覆盖旧版）
        - Phase 4: `render`（重新渲染所有视角，覆盖旧 PNG）
        - Phase 5: `enhance`（重新 AI 增强，覆盖旧 JPG）
        - Phase 6: `annotate`（重新标注，覆盖旧标注图）

   - **选 B（续跑）**→ 从建议的阶段开始，按顺序执行到最后一个阶段：
     - 如果起点包含 Phase 1 SPEC，则执行审查流程（同选 A 的 1-3 步）
     - 如果起点是 Phase 3 BUILD 或之后，直接按顺序执行，无需审查
     - 如果起点包含 Phase 5 ENHANCE，先询问 enhance 后端（gemini/comfyui）

   - **选 C（指定阶段）**→ 仅执行用户指定的阶段：
     - 如果包含 Phase 4 RENDER，**必须先执行 Phase 3 BUILD**（GLB 必须与当前代码一致）
     - 如果包含 Phase 5 ENHANCE，先询问 enhance 后端
     - 其余按指定阶段顺序执行

   **不可**跳过 Step 0 直接执行 `cad_pipeline.py full`（管线层也有断点保护）。

### 执行约束

- 环境检查（env_check）：逐项运行检测命令，汇报 ✅/❌ 状态
- 验证配置（validate）：读取并检查 render_config.json 的完整性
- 构建（build）：`cad_pipeline.py build` 运行 build_all.py 后**自动执行 render_dxf.py** 将 DXF 转为 PNG 工程图预览（如脚本存在）
- 渲染（render）：**无论全管线还是单独渲染，均须先运行 build 重新生成 GLB，再执行 Blender 渲染**（GLB 是 Blender 的输入，必须与当前设计保持一致）
- **CAD Spec 意图**（`/cad-spec`）：输出 CAD_SPEC.md，v2.5.0+ 起包含 §6.3 零件级定位、§6.4 零件包络尺寸、§9 装配约束三个新章节；v2.7.0+ 新增 §9.2 约束声明（contact/stack_on/fit codes，从连接矩阵自动推导）
- **Design Review 意图**（`/cad-spec --review-only`）：v2.5.0+ 审查项 B10（定位模式一致性）、B11（包络尺寸覆盖率）、B12（装配排除合法性）
- **GATE-3.5 装配校验**（v2.7.0+）：Phase 3 BUILD 后自动运行 `assembly_validator.py`，执行 5 项公式驱动检查（F1 重叠/F2 断连/F3 紧凑度/F4 尺寸比/F5 排除合规）→ ASSEMBLY_REPORT.json。四道门控体系：GATE-1(审查) → GATE-2(TODO扫描) → GATE-3(方向校验) → GATE-3.5(装配校验)
- **Parts Library 系统**（v2.8.0+，v2.21.2 几何质量闭环）：外购件几何源由 `parts_library.yaml` 注册表驱动 — 支持项目/用户 STEP 池 (`std_parts/`)、共享 vendor STEP 缓存、SolidWorks Toolbox STEP、`bd_warehouse`、`partcad`，外加 `jinja_primitive` 终极 fallback。Phase 1 P7 包络回填把库探测尺寸写入 §6.4，Phase 2 codegen 用 `resolver.resolve(mode="codegen")` 决定每个 `make_std_*()` 函数体形式（codegen / step_import / python_import）。无 yaml 时系统是 no-op，输出与 v2.7.x 字节级一致。Kill switch: `CAD_PARTS_LIBRARY_DISABLE=1`
- **模型选择闭环**（v2.21.2+）：`DESIGN_REVIEW.json` 可携带 `geometry` 分组、`group_action`、`candidates`、A-E 质量等级和建议动作；用户提供 STEP 时，Agent 必须把结构化 `model_choices` 放入 supplements。管线会复制到 `std_parts/user_provided/`、写 `model_choices.json`、前置更新 `parts_library.yaml`，下一次 codegen 实际导入该 STEP。用户已直接给出可信 STEP 时，可运行 `python cad_pipeline.py model-import --subsystem <name> --part-no <id> --step <path.step>`，命令会复制 STEP、更新 `parts_library.yaml`、写 `model_imports.json` 并校验 resolver 会命中 `step_pool`。
- **Registry inheritance + coverage / geometry report**（v2.8.1+ / v2.21.2+）：`parts_library.yaml` 加 `extends: default` 即可继承 skill 自带的 default 规则,project mappings prepend 到 default 之前。`gen_std_parts.py` 末尾打印 per-adapter 覆盖率表，并写 `cad/<subsystem>/.cad-spec-gen/geometry_report.json`；报告告诉用户哪些零件用了真实/参数化模型、哪些仍是 D/E 级简化 fallback，以及如何升级。需要只读复查时运行 `python cad_pipeline.py model-audit --subsystem <name>`；`--strict` 可用于 CI 中发现需审查模型或缺失 STEP 时返回 exit 1。
- **SW export plan（v2.24.0+）**：当用户询问 SolidWorks/Toolbox 候选导出、缓存复用或导出前检查时，运行 `python cad_pipeline.py sw-export-plan --subsystem <name> [--json]`。该命令只写/读 `cad/<subsystem>/.cad-spec-gen/sw_export_plan.json` 候选计划，候选动作仅为 `reuse_cache` 或 `export`，不会启动 SolidWorks COM 导出；真正导出必须由用户确认后显式执行。
- **Render visual check（v2.25+）**：Phase 4 渲染完成后可运行 `python cad_pipeline.py render-visual-check --subsystem <name>`。该命令只读取 `ARTIFACT_INDEX.json.active_run_id` 的当前产物，写 `RENDER_VISUAL_REGRESSION.json`；检查 render_manifest 子系统/run_id/path_context/hash 链、active render_dir、渲染文件 hash、重复视角、产品图必需实例是否进入运行时装配签名，并与 accepted baseline 比较视角和装配实例。若 baseline/当前 manifest 带逐视角 `visible_instance_ids` 等证据，还会比较每个视角是否丢失已可见实例；没有逐视角证据时只能给 warning，不得假装图片内元件身份已被证明。它 does not scan directories，不猜最新 PNG，不切换 run。
- **Render quality check（v2.25+）**：Phase 4 渲染完成后可运行 `python cad_pipeline.py render-quality-check --subsystem <name>`。该命令只读取 `ARTIFACT_INDEX.json.active_run_id` 和同 run `render_manifest.json`，写 `RENDER_QUALITY_REPORT.json`；检查 `blender_preflight`、渲染文件路径/hash/基础 QA，并写逐视角 `pixel_metrics`。缺 Blender、缺图、路径越界、hash 漂移或 QA 失败 blocked；低对比度、边缘密度低或画布不一致 warning。它是确定性像素证据，不做语义 AI 判断，does not scan directories，不猜最新 PNG，不切换 run。
- **Photo3D 契约门禁（v2.25+）**：照片级出图前普通用户先运行只读 `python cad_pipeline.py project-guide --subsystem <name> --design-doc <path>`，由 `PROJECT_GUIDE.json` 选择 `init/spec/codegen/build-render/photo3d-run` 下一步；到增强入口时它只提供白名单 provider preset 选择、普通用户可读选项 `ordinary_user_options`、展示向导 `provider_wizard`、安全配置健康状态 `provider_health` 和 `photo3d-handoff --provider-preset <id>` 预览命令，不运行增强、不追加 `--confirm`。`provider_health` 只做配置/依赖存在性检查，不能暴露环境变量名、key 值、URL、endpoint 或 secret。已有 active run 后运行 `python cad_pipeline.py photo3d-run --subsystem <name>`，它按当前 active run 连续运行底层 `python cad_pipeline.py photo3d --subsystem <name>` 和 `photo3d-autopilot`，写 `PHOTO3D_RUN.json`，并停在 baseline 确认、增强入口、用户输入、人工复查、执行失败或 loop limit。它绑定 `run_id`、`ARTIFACT_INDEX.json`、产品图、模型契约、装配签名、渲染清单和 baseline；不会接受 baseline，不会运行增强，不会扫描目录猜最新文件。用户说“按建议执行”时优先运行 `python cad_pipeline.py photo3d-handoff --subsystem <name>` 预览当前 `next_action`，确认后运行 `python cad_pipeline.py photo3d-handoff --subsystem <name> --confirm`；该命令写 `PHOTO3D_HANDOFF.json`，只执行 `accept-baseline`、`enhance`、`enhance-check` 或 `photo3d-run --confirm-actions` 交接，不信任 JSON 里的任意 argv。增强 provider 只能用 `--provider-preset default|engineering|gemini|fal|fal_comfy|comfyui` 白名单，示例：`python cad_pipeline.py photo3d-handoff --subsystem <name> --provider-preset engineering --confirm`。用户确认低风险恢复时也可运行 `python cad_pipeline.py photo3d-run --subsystem <name> --confirm-actions`，由 `photo3d-action` 执行允许动作并写 `PHOTO3D_ACTION_RUN.json`。底层单轮命令仍是 `photo3d-autopilot`；用户确认 `pass` / `warning` 报告后运行 `python cad_pipeline.py accept-baseline --subsystem <name>` 写入 `accepted_baseline_run_id`，后续 `photo3d --change-scope` 自动复用该基线。`blocked` 时写 `PHOTO3D_REPORT.json`、`ACTION_PLAN.json`、`LLM_CONTEXT_PACK.json`；动作计划里的 CLI 必须是 `photo3d-recover --run-id <run_id> --artifact-index <path>`，由 wrapper 写回当前 run 产物。大模型优先按 `PHOTO3D_RUN.json` 继续，不能用 AI 增强补 CAD 阶段缺失结构。
- **法兰 F1+F3 + GLB consolidator**（v2.8.2+）：`disc_arms` 几何模板重写——arm + platform 贯通整个 disc 厚度,加 chamfer/fillet polish。`codegen/consolidate_glb.py` 在 build 后自动合并 CadQuery 的 per-face mesh 拆分,使每个 BOM part 在 GLB 里是单个 mesh node(GISBOT: 321 → 39 components)
- **Phase B 多 vendor STEP**（v2.8.2+）：`tools/synthesize_demo_step_files.py` 生成 Maxon GP22C / LEMO FGG.0B / ATI Nano17 等参数化 stand-in STEP 文件,用于演示 step pool 路径。真实 vendor STEP 应替换这些占位符
- **只读阶段零副作用**：审查、候选展示、报告诊断只能使用 `inspect` / `probe` 或既有决策日志；不得为展示选项启动 SolidWorks COM 导出、生成 STEP 缓存或改写模型库。注意 legacy `probe_dims()` 仍可能为 vendor stand-in 预热共享缓存；需要绝对只读时优先使用 `cad_pipeline.py model-audit`、`resolve(..., mode="probe")` 或既有 `geometry_report.json`。
- 排错（troubleshoot）：先问用户具体报错信息，再对照排错指南定位
- 状态（status）：扫描 cad/ 和 cad/output/ 目录，统计产物数量
- 所有动作输出简洁明了，用 ✅/❌/⚠️ 标记状态
