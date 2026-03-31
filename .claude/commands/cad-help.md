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

3. **全管线请求**（当用户要求"全部流程"/"走全流程"/"全管线"/"full pipeline"时）：
   > **重建原则：每次全管线均从头完整重建，覆盖所有已有产物（SPEC、GLB、PNG、JPG 等）。不检查已有文件是否存在，不跳过任何阶段。**
   1. 先运行 Phase 1 SPEC（含 `--force --review`）强制重新生成
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
   5. **不可**跳过此步骤直接执行 `cad_pipeline.py full`（管线层也有断点保护）

### 执行约束

- 环境检查（env_check）：逐项运行检测命令，汇报 ✅/❌ 状态
- 验证配置（validate）：读取并检查 render_config.json 的完整性
- 渲染（render）：**无论全管线还是单独渲染，均须先运行 build 重新生成 GLB，再执行 Blender 渲染**（GLB 是 Blender 的输入，必须与当前设计保持一致）
- 排错（troubleshoot）：先问用户具体报错信息，再对照排错指南定位
- 状态（status）：扫描 cad/ 和 cad/output/ 目录，统计产物数量
- 所有动作输出简洁明了，用 ✅/❌/⚠️ 标记状态
