# /cad-spec — 从设计文档生成 CAD Spec

用户输入: $ARGUMENTS

## 指令

运行 CAD Spec 生成器，从设计文档提取结构化参数/公差/BOM等数据。这是 6 阶段管线的 **Phase 1**。

### 路由规则

1. **无参数** → 显示用法：
   ```
   用法: /cad-spec <design_doc.md> [--force] [--review] [--review-only] [--auto-fill]

   示例:
     /cad-spec docs/design/04-末端执行机构设计.md
     /cad-spec docs/design/04-末端执行机构设计.md --review
     /cad-spec docs/design/05-电气系统与信号调理.md --force
     /cad-spec --all --review

   也可通过统一管线执行:
     python cad_pipeline.py spec --design-doc docs/design/04-*.md --auto-fill
   ```

2. **`--all`** → 处理全部子系统：
   ```bash
   python cad_spec_gen.py --all --config config/gisbot.json
   ```

3. **文件路径** → 处理单个文档：
   ```bash
   python cad_spec_gen.py $ARGUMENTS --config config/gisbot.json
   ```

4. **`--review` 或 `--review-only`** → 设计审查工作流：
   ```bash
   # 仅审查（推荐首次使用）
   python cad_spec_gen.py <doc.md> --config config/gisbot.json --review-only --force

   # 审查 + 生成
   python cad_spec_gen.py <doc.md> --config config/gisbot.json --review --force
   ```

### 审查工作流（当使用 --review 或通过管线执行时）

`cad_pipeline.py spec` 和 `cad_pipeline.py full` 自动执行两阶段交互式审查：

**Phase 1a — 生成审查报告**：
1. 运行 `cad_spec_gen.py --review-only`，提取数据并执行设计审查引擎（力学/装配/材质/完整性）
2. 输出 `DESIGN_REVIEW.md` + `DESIGN_REVIEW.json`

**Phase 1b — 交互式用户选择**：
3. 在终端显示审查摘要（CRITICAL/WARNING/INFO/OK 计数 + 各问题条目）
4. **交互式提示用户选择**：
   - 有 CRITICAL 时：
     - **「1. 继续审查」** → 管线暂停 (exit 2)，用户逐项修正后重新运行
     - **「2. 中止」** → 管线停止 (exit 1)，先手动修正设计文档
   - 有 WARNING（无 CRITICAL）时：
     - **「1. 继续审查」** → 暂停，逐项讨论问题
     - **「2. 自动补全」** → 自动填入可计算的默认值（螺栓力矩、单位、粗糙度等），然后生成 CAD_SPEC.md
     - **「3. 下一步」** → 按现有数据直接生成 CAD_SPEC.md（不补全缺失项）
   - 无问题时 → 自动进入下一步
5. 用户选择后，运行 `cad_spec_gen.py --review [--auto-fill]` 生成 CAD_SPEC.md

**注意**：
- 通过 `--auto-fill` CLI 标志可跳过交互，直接执行自动补全
- **不直接修改用户的设计文档**，所有修改仅反映在 CAD_SPEC.md 中

### 生成后汇总

读取输出的 CAD_SPEC.md 并汇总：
- 提取到的参数、紧固件、BOM零件数量
- 任何 CRITICAL 或 WARNING 缺失数据项
- 设计审查结果（如有）
- 输出文件位置

### 下一步

CAD_SPEC.md 生成后，建议用户：
- **`/cad-codegen <子系统>`** → 自动生成 CadQuery 脚手架代码（Phase 2）
- **`python cad_pipeline.py full`** → 一键执行全部 6 阶段管线
- **`/mechdesign <子系统>`** → 手动参数化建模流程（需要更精细的几何控制时）
