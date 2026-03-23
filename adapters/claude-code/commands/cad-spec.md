# /cad-spec — 从设计文档生成 CAD Spec

用户输入: $ARGUMENTS

## 指令

运行 CAD Spec 生成器，从设计文档提取结构化参数/公差/BOM等数据。

### 路由规则

1. **无参数** → 显示用法：
   ```
   用法: /cad-spec <design_doc.md> [--force] [--review] [--review-only] [--auto-fill]

   示例:
     /cad-spec docs/design/04-末端执行机构设计.md
     /cad-spec docs/design/04-末端执行机构设计.md --review
     /cad-spec docs/design/05-电气系统与信号调理.md --force
     /cad-spec --all --review
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

### 审查工作流（当使用 --review 或 --review-only 时）

1. 提取数据后自动运行设计审查引擎（力学/装配/材质/完整性）
2. 读取生成的 `DESIGN_REVIEW.md`，向用户展示审查摘要：
   - A. 力学审查结果（悬臂应力、螺栓剪切等）
   - B. 装配审查结果（尺寸链、包络干涉、悬空零件、连接方式等）
   - C. 材质审查结果（电偶腐蚀、温度裕度等）
   - D. 缺失数据（CRITICAL/WARNING/INFO + 可自动补全项）
3. 向用户提供选项：
   - **「继续审查」** → 逐项讨论 WARNING/CRITICAL，用户可调整参数，审查结果记入 CAD_SPEC.md 备注
   - **「自动补全」** → 对可自动计算的缺失项（螺栓力矩、单位、粗糙度等）自动补全并写入 CAD_SPEC.md，然后展示变更清单
   - **「下一步」** → 接受当前结果，按现有数据生成 CAD_SPEC.md
4. 用户确认「下一步」后，运行不带 --review-only 的完整生成
5. **重要：不直接修改用户的设计文档**，所有修改仅反映在 CAD_SPEC.md 中

### 自动补全工作流（--auto-fill）

当审查发现可自动计算的缺失数据时：
1. 螺栓缺少力矩 → 按8.8级标准力矩补全
2. 参数缺少单位 → 按参数名模式推断（OD/ID→mm, WEIGHT→g, ANGLE→°）
3. 零件缺少表面粗糙度 → 按材质默认Ra补全
4. 补全后自动重新生成 CAD_SPEC.md

### 生成后汇总

读取输出的 CAD_SPEC.md 并汇总：
- 提取到的参数、紧固件、BOM零件数量
- 任何 CRITICAL 或 WARNING 缺失数据项
- 设计审查结果（如有）
- 输出文件位置
