# /cad-spec — 从设计文档生成 CAD Spec

用户输入: $ARGUMENTS

## 指令

运行 CAD Spec 生成器，从设计文档提取结构化参数/公差/BOM等数据。

### 路由规则

1. **无参数** → 显示用法：
   ```
   用法: /cad-spec <design_doc.md> [--force]

   示例:
     /cad-spec docs/design/04-末端执行机构设计.md
     /cad-spec docs/design/05-电气系统与信号调理.md --force
     /cad-spec --all
   ```

2. **`--all`** → 处理全部子系统：
   ```bash
   python cad_spec_gen.py --all --config config/gisbot.json
   ```

3. **文件路径** → 处理单个文档：
   ```bash
   python cad_spec_gen.py $ARGUMENTS --config config/gisbot.json
   ```

4. 生成后读取输出的 CAD_SPEC.md 并汇总：
   - 提取到的参数、紧固件、BOM零件数量
   - 任何 CRITICAL 或 WARNING 缺失数据项
   - 输出文件位置
