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

3. **全管线请求**（当用户要求绘图/渲染/全部流程/走全流程/全管线/full pipeline，或请求同时生成2D+3D产物时）：

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
- 排错（troubleshoot）：先问用户具体报错信息，再对照排错指南定位
- 状态（status）：扫描 cad/ 和 cad/output/ 目录，统计产物数量
- 所有动作输出简洁明了，用 ✅/❌/⚠️ 标记状态
