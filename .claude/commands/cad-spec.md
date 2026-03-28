# /cad-spec — 从设计文档生成 CAD Spec

用户输入: $ARGUMENTS

## 指令

运行 CAD Spec 生成器，从设计文档提取结构化参数/公差/BOM等数据。这是 6 阶段管线的 **Phase 1**。

### 路由规则

1. **无参数** → 显示用法：
   ```
   用法: /cad-spec <design_doc.md> [--force] [--review-only] [--auto-fill] [--supplements '{...}']

   示例:
     /cad-spec docs/design/04-末端执行机构设计.md
     /cad-spec docs/design/04-末端执行机构设计.md --review-only
     /cad-spec docs/design/05-电气系统与信号调理.md --force
     /cad-spec --all

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

4. **`--review-only`** → Agent 驱动设计审查工作流（推荐）：
   ```bash
   # Step 1: 生成审查报告（无交互，立即返回）
   python cad_pipeline.py spec --subsystem <名称> --design-doc <doc.md> --review-only

   # Step 2a: Agent 逐项讨论后，传入补充数据 + 自动补全
   python cad_pipeline.py spec --subsystem <名称> --supplements '{"B2": "壳体连接至安装支架，M4×8螺栓"}' --auto-fill

   # Step 2b: 或直接自动补全（无需补充数据）
   python cad_pipeline.py spec --subsystem <名称> --auto-fill

   # Step 2c: 或按现有数据直接生成（跳过补全）
   python cad_pipeline.py spec --subsystem <名称> --proceed
   ```

### Agent 审查工作流

`cad_pipeline.py spec` 采用无交互 Agent 驱动模式，分两步执行：

**Step 1 — 生成审查报告** (`--review-only`)：
1. 运行 `cad_spec_gen.py --review-only`，提取数据并执行设计审查引擎（力学/装配/材质/完整性）
2. 输出 `output/<subsystem>/DESIGN_REVIEW.md` + `DESIGN_REVIEW.json`
3. 打印审查摘要（CRITICAL/WARNING/INFO/OK 计数 + 各问题条目）后**立即退出（exit 0）**
4. Agent 读取 `DESIGN_REVIEW.json`，与用户讨论各 WARNING/CRITICAL 问题

**Step 2 — 生成 CAD_SPEC.md**（根据讨论结果选一）：
- **`--supplements '{...}' [--auto-fill]`** → Agent 将用户确认的补充数据以 JSON 传入，写入 `user_supplements.json` 并追加到 CAD_SPEC.md；`--auto-fill` 同时自动填充可计算默认值
- **`--auto-fill`** → 自动填充所有可计算默认值（螺栓力矩、单位、粗糙度等），生成 CAD_SPEC.md
- **`--proceed`** → 按现有数据直接生成 CAD_SPEC.md（不补全缺失项）

**`--supplements` JSON 格式**：
```json
{
  "B2": "壳体连接至安装支架，M4×8螺栓，4处",
  "M01": "总重量: 2.3kg",
  "D2": "齿轮泵额定压力: 15MPa"
}
```
键为 DESIGN_REVIEW.json 中的 `id` 字段，值为用户确认的补充内容。

**注意**：
- 整个流程**无 `input()` 调用**，Agent 完全通过 CLI 参数驱动
- **不直接修改用户的设计文档**，所有修改仅反映在 CAD_SPEC.md 中
- CRITICAL 问题需用户手动修改设计文档后重跑 `--review-only`

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
