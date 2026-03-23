# /mechdesign — 参数化机械子系统 CAD 设计

用户输入: $ARGUMENTS

## 指令

读取完整技能文档 `D:\cad-skill\claude\memory\skill_mech_design.md`，然后根据用户输入执行：

### 子命令路由

1. **无参数**（`$ARGUMENTS` 为空）→ 显示流程概览：
   - 列出 6 个阶段简述
   - 列出可用子系统（从 `docs/design/` 扫描章节文件）
   - 显示参考实现 `D:\cad-skill\cad\end_effector\` 的产物统计

2. **`status`** → 检查各子系统 CAD 建模进度：
   - 扫描 `cad/*/build_all.py` 找已实现的子系统
   - 扫描 `cad/output/` 统计 STEP/DXF/PNG 数量
   - 列出所有 `docs/design/` 章节，标注哪些已建模、哪些待建
   - 推荐下一步优先级

3. **`upgrade`** → 启动2D工程图国标升级（V4方案）：
   - 按 Phase 1→1.5→2→3→4 执行
   - Phase 1: drawing.py + draw_three_view.py 基础设施改造
   - Phase 1.5: 可视化验证测试图
   - Phase 2: 选最复杂零件做模板
   - Phase 3: 批量改其余零件
   - Phase 4: 全量验证

4. **`<子系统名>`**（如 `充电对接机构`、`底盘`、`电池箱`）→ 启动全流程：
   - 确认目标子系统和对应设计文档（`docs/design/NN-*.md`）
   - 按 skill_mech_design.md 中的 6 阶段顺序执行：
     1. 参数提取 → `params.py` + `tolerances.py`
     2. BOM建模 → `bom.py`
     3. 3D参数化建模 → CadQuery `.py` + `assembly.py`
     4. 2D工程图 → GB/T 国标A3 DXF（含技术要求/基准/螺纹/剖视图）
     5. 渲染预览 → DXF→PNG（复用 `render_dxf.py`）
     6. 一键构建 → `build_all.py`
   - 每阶段完成后执行检查点验证
   - 可复用模块从 `D:\cad-skill\cad\end_effector\` 复制：`drawing.py`, `draw_three_view.py`, `render_dxf.py`

## 关键约束

- 所有参数从设计文档提取，params.py 是单一数据源
- 2D 工程图直接从 params.py 绘制轮廓，不依赖 3D→2D 投影
- 输出到 `cad/output/`，已纳入 git 版本管理
- 字体：仿宋体 FangSong（GB/T 14691），DXF 格式 R2013
- GB/T 4458.1 第一角投影法，A3 图纸（420×297mm）
- 线宽体系 d=0.50mm，替换内置 CENTER/DASHED linetype 为 GB/T 17450 模式
- 标注文字 3.5mm 纸面mm（不乘 view scale）
- 每张图必须有：技术要求区 + 默认粗糙度 + 基准三角 + 剖切线 + 螺纹标注
- 材料名使用中文国标格式（"铝合金"非"Al"）
