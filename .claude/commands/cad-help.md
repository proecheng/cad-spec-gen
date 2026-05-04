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

3. **Photo3D / 照片级一键出图请求**（当用户说 photo3d、photo3d-autopilot、photo3d-action、照片级、傻瓜式出图、pass/warning/blocked、accepted/preview/blocked、run_id、baseline、动作计划或让其他大模型继续时）：

   - 普通用户推荐命令：`python cad_pipeline.py photo3d-autopilot --subsystem <name>`；底层门禁命令：`python cad_pipeline.py photo3d --subsystem <name>`。
   - 运行前确认目标子系统；不要用产品名、目录名相似度或旧 PNG 猜测目标。
   - 这些命令只读取当前 `run_id` 在 `ARTIFACT_INDEX.json` 中登记的产物，不能扫描目录猜最新文件。
   - `photo3d-autopilot` 会先运行 `photo3d` 门禁，再写 `PHOTO3D_AUTOPILOT.json`：`blocked` 时指向 `ACTION_PLAN.json` / `LLM_CONTEXT_PACK.json`；`pass` / `warning` 且没有 accepted baseline 时，只建议用户确认后显式运行 `python cad_pipeline.py accept-baseline --subsystem <name>`；已有 `accepted_baseline_run_id` 时，才建议进入增强。它不会静默接受 baseline，也不会切换 `active_run_id`。
   - `photo3d-action` 是确认后执行层：默认 `python cad_pipeline.py photo3d-action --subsystem <name>` 只预览并写 `PHOTO3D_ACTION_RUN.json`；用户确认后才运行 `python cad_pipeline.py photo3d-action --subsystem <name> --confirm`。它只执行当前 `active_run_id` 的 `ACTION_PLAN.json` 中 low-risk、无需用户输入、白名单内的 `product-graph` / `build` / `render` CLI 动作；这些 CLI 必须写成 run-aware wrapper：`python cad_pipeline.py photo3d-recover --subsystem <name> --run-id <run_id> --artifact-index cad/<name>/.cad-spec-gen/ARTIFACT_INDEX.json --action product-graph|build|render`，禁止回退到裸 `product-graph` / `build` / `render --subsystem <name>`。用户输入类动作继续询问用户。它不会扫描目录猜最新文件，不会运行增强，也不会接受 baseline。当 `--confirm` 的 low-risk CLI 全部成功，且没有用户输入、人工复查或 rejected actions 时，它会自动重跑 `photo3d-autopilot`，并把下一步摘要写入 `PHOTO3D_ACTION_RUN.json` 的 `post_action_autopilot`；preview、执行失败、仍有用户输入或 rejected actions 时不会自动重跑。
   - 解释门禁状态（Gate status）：
     - `pass`：CAD 契约门禁通过，可以进入增强阶段。
     - `warning`：CAD 契约门禁通过但有非阻断警告，只能带着警告进入增强或先人工复核。
     - `blocked`：CAD 契约门禁失败，不运行 AI 增强。
   - 解释增强交付状态（Enhancement delivery status，增强完成后的上层语义）：
     - `accepted`：CAD 门禁和增强一致性都通过，可作为照片级交付图。
     - `preview`：CAD 门禁通过，但增强一致性未验证或未通过，只能作为预览。
     - `blocked`：CAD 门禁失败，增强不得执行。
     - 当前门禁阶段的 `PHOTO3D_REPORT.json` 只会把 `enhancement_status` 写成 `not_run` 或 `blocked`；`accepted` / `preview` 属于后续增强交付层。
   - 阻断时读取并解释：
     - `PHOTO3D_REPORT.json`：普通用户中文阻断原因。
     - `PHOTO3D_AUTOPILOT.json`：普通用户本轮下一步报告。
     - `ACTION_PLAN.json`：允许大模型执行的下一步动作。
     - `LLM_CONTEXT_PACK.json`：给其他大模型的当前 run 最小上下文。
     - `PHOTO3D_ACTION_RUN.json`：`photo3d-action` 的预览/执行报告，列出 executable/user_input/rejected/executed actions；`post_action_autopilot` 记录成功确认执行后的自动重跑摘要。
   - 路径隔离：每次运行都有独立 `run_id`；契约在 `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/`，渲染图在 `cad/output/renders/<subsystem>/<run_id>/`。
   - 旧产物清理：只能清理不再被 `active_run_id` 引用的旧 run/render 目录，不能把旧 PNG 当成本轮通过证据。
   - 接受基准：首次 `pass` 只作为候选基准；用户确认当前 `PHOTO3D_REPORT.json` 后，运行 `python cad_pipeline.py accept-baseline --subsystem <name>`。报告会记录关键契约的 `artifact_hashes`；命令只接受 `pass` / `warning` 报告，并校验报告路径、artifact 路径和当前文件哈希都与 `ARTIFACT_INDEX.json` 中同一 run 一致，再把 `run_id` 写入 `accepted_baseline_run_id`。它不会切换 `active_run_id`，也不会扫描目录猜最新产物；需要指定历史 run 时传 `--run-id <run_id>`。
   - 基线复用：后续 `photo3d --change-scope <CHANGE_SCOPE.json>` 会自动使用 `accepted_baseline_run_id` 对应的 `ASSEMBLY_SIGNATURE.json`；仍可用 `--baseline-signature <path>` 显式覆盖。
   - 漂移处理：后续用 `baseline` / `CHANGE_SCOPE.json` 检查实例数量、bbox、位置和旋转漂移；未授权漂移保持 `blocked`，有意变更必须写入 `CHANGE_SCOPE.json` 并标注为 authorized。
   - 大模型只能依据 `ACTION_PLAN.json` 执行；低风险 CLI 恢复动作走 `photo3d-action` 预览/确认执行，底层命令必须经 `photo3d-recover --run-id <run_id> --artifact-index <path>` 绑定当前 run。如果动作需要用户输入，询问用户，不要虚构路径或模型。

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
- **Photo3D 契约门禁（v2.25+）**：照片级出图前普通用户运行 `python cad_pipeline.py photo3d-autopilot --subsystem <name>`，它先运行底层 `python cad_pipeline.py photo3d --subsystem <name>`，再写 `PHOTO3D_AUTOPILOT.json` 下一步报告。它绑定 `run_id`、`ARTIFACT_INDEX.json`、产品图、模型契约、装配签名、渲染清单和 baseline；门禁状态是 `pass` / `warning` / `blocked`，增强交付状态才是 `accepted` / `preview` / `blocked`。用户确认 `pass` / `warning` 报告后运行 `python cad_pipeline.py accept-baseline --subsystem <name>` 写入 `accepted_baseline_run_id`，后续 `photo3d --change-scope` 自动复用该基线。`blocked` 时写 `PHOTO3D_REPORT.json`、`ACTION_PLAN.json`、`LLM_CONTEXT_PACK.json`，autopilot 报告只指向允许动作。低风险 CLI 恢复动作必须先用 `python cad_pipeline.py photo3d-action --subsystem <name>` 预览，用户确认后加 `--confirm` 执行并写 `PHOTO3D_ACTION_RUN.json`；动作计划里的 CLI 必须是 `photo3d-recover --run-id <run_id> --artifact-index <path>`，由 wrapper 写回当前 run 产物。当动作全部成功且无人工输入/复查/rejected actions 时会自动重跑 `photo3d-autopilot`，并把下一步写入 `post_action_autopilot`。大模型必须按动作计划继续，不能扫描目录猜最新文件，也不能用 AI 增强补 CAD 阶段缺失结构。
- **法兰 F1+F3 + GLB consolidator**（v2.8.2+）：`disc_arms` 几何模板重写——arm + platform 贯通整个 disc 厚度,加 chamfer/fillet polish。`codegen/consolidate_glb.py` 在 build 后自动合并 CadQuery 的 per-face mesh 拆分,使每个 BOM part 在 GLB 里是单个 mesh node(GISBOT: 321 → 39 components)
- **Phase B 多 vendor STEP**（v2.8.2+）：`tools/synthesize_demo_step_files.py` 生成 Maxon GP22C / LEMO FGG.0B / ATI Nano17 等参数化 stand-in STEP 文件,用于演示 step pool 路径。真实 vendor STEP 应替换这些占位符
- **只读阶段零副作用**：审查、候选展示、报告诊断只能使用 `inspect` / `probe` 或既有决策日志；不得为展示选项启动 SolidWorks COM 导出、生成 STEP 缓存或改写模型库。注意 legacy `probe_dims()` 仍可能为 vendor stand-in 预热共享缓存；需要绝对只读时优先使用 `cad_pipeline.py model-audit`、`resolve(..., mode="probe")` 或既有 `geometry_report.json`。
- 排错（troubleshoot）：先问用户具体报错信息，再对照排错指南定位
- 状态（status）：扫描 cad/ 和 cad/output/ 目录，统计产物数量
- 所有动作输出简洁明了，用 ✅/❌/⚠️ 标记状态
