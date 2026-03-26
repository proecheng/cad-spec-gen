# 技能：参数化机械子系统设计

## 触发条件
当用户要求设计一个新的机械子系统（如底盘、伸缩臂、充电对接机构等）时，按本流程执行。
关键词：`机械设计`、`CAD建模`、`工程图`、`新建子系统`、`mech`

## 前置条件
- 该子系统已有设计文档（`docs/design/NN-*.md`），包含参数表、公差表、BOM
- 已安装 cadquery, ezdxf, matplotlib

## 文件结构模板

```
D:/cad-skill/cad/<subsystem>/
├── params.py              ← 阶段1：几何参数（单一数据源）
├── tolerances.py          ← 阶段1：公差/GD&T/表面粗糙度
├── bom.py                 ← 阶段2：结构化BOM + CSV导出
├── <part1>.py             ← 阶段3：CadQuery 3D零件
├── <part2>.py             ←
├── assembly.py            ← 阶段3：总成装配
├── drawing.py             ← 阶段4：ezdxf 2D引擎（可复用 end_effector/drawing.py）
├── draw_three_view.py     ← 阶段4：ThreeViewSheet 三视图A3框架（可复用）
├── draw_<part1>.py        ← 阶段4：2D工程图（视图函数 + sheet组装）
├── draw_<part2>.py        ←
├── render_dxf.py          ← 阶段5a：DXF→PNG渲染（可复用 end_effector/render_dxf.py）
├── render_config.json     ← 阶段5b：渲染配置（材质/相机/爆炸/prompt变量）
├── render_config.py       ← 阶段5b：配置引擎（预设库+加载+缩放，stdlib-only）
├── render_3d.py           ← 阶段5b：Blender Cycles 照片级3D渲染（--config支持）
├── render_exploded.py     ← 阶段5b：Blender 爆炸图渲染（--config支持）
└── build_all.py           ← 阶段6：一键构建（--render 触发Blender渲染+Gemini增强）
```

输出到 `D:/GISBOT/cad/output/` （已在 .gitignore 中排除）

## 执行步骤

### 阶段 0.5：CAD Spec 生成（自动）

每次启动 mechdesign <子系统> 时首先执行：

1. 定位设计文档：`SUBSYSTEM_MAP[章节号]` → `docs/design/NN-*.md`
2. 运行：`python D:/cad-skill/tools/cad_spec_gen.py <doc_path>`
3. 输出：`D:/cad-skill/cad/<subsystem>/CAD_SPEC.md`（9节固定格式，单一数据源）
4. 检查 §9 缺失数据报告：
   - **CRITICAL** → 暂停，报告缺失项，请用户补充设计文档或确认
   - **WARNING** → 列出默认值，请用户确认后继续
   - 全部通过 → 进入阶段1
5. 后续阶段数据源映射：
   - 阶段1 params.py ← CAD_SPEC §1 全局参数表
   - 阶段1 tolerances.py ← CAD_SPEC §2 公差与表面处理
   - 阶段2 bom.py ← CAD_SPEC §5 BOM树
   - 阶段3 assembly.py ← CAD_SPEC §4 连接矩阵 + §6 装配姿态
   - 阶段5b render_config.json ← CAD_SPEC §7 视觉标识 + §8 渲染规划

**检查点**: CAD_SPEC.md 存在且 §9 无 CRITICAL 项。

**工具**:
- CLI: `python D:/cad-skill/tools/cad_spec_gen.py <path> [--force] [--all]`
- 提取器: `D:/cad-skill/tools/cad_spec_extractors.py`（8个提取函数 + 通用表格解析器）
- 默认值: `D:/cad-skill/tools/cad_spec_defaults.py`（标准力矩/公差/粗糙度/密度）
- 模板: `D:/cad-skill/docs/templates/cad_spec_template.md`

### 阶段 1：参数提取（params.py + tolerances.py）

**目标**：从设计文档提取所有数值，建立单一参数源。

1. 读取对应设计章节 `docs/design/NN-*.md`
2. 创建 `params.py`：
   - 每个参数一行，带中文注释 + 设计文档行号引用
   - 按子系统功能分区（用 `# ═══` 分隔符）
   - 单位统一：mm / degrees / grams（文件头声明）
   - 派生量用表达式（如 `FLANGE_R = FLANGE_OD / 2.0`）
   - 命名规范：`大写_下划线`，前缀区分子模块（如 `S1_`=工位1, `S2_`=工位2）

3. 创建 `tolerances.py`：
   - 数据类：`DimTol(nominal, upper, lower, fit_code, label)`
   - 数据类：`GDT(symbol, value, datum)`
   - 数据类：`SurfaceFinish(ra, treatment)`
   - 从设计文档公差表逐条提取

**检查点**：参数数量应与设计文档一致，无遗漏。

### 阶段 2：BOM建模（bom.py）

**目标**：结构化BOM数据，支持CSV/Markdown导出。

1. 从设计文档BOM表提取数据
2. 复用 `BOMItem` 数据类结构：
   ```python
   @dataclass
   class BOMItem:
       part_no: str      # 编号规则：GIS-XX-NNN-NN
       name: str         # 中文名称
       material: str     # 材质/型号（GB/T格式，如"7075-T6 铝合金"）
       qty: int          # 数量
       make_buy: str     # 自制/外购/总成
       unit_price: float # 单价(元)
       weight_g: float   # 重量(g)
       parent: str       # 父总成编号
       notes: str        # 备注
       drawing: str      # 关联工程图文件名
   ```
3. 提供 CLI：`--csv` / `--markdown` / 默认打印表格

**检查点**：`python bom.py` 运行无错，总成本和总重量与设计文档一致。

### 阶段 3：3D 参数化建模（CadQuery）

**目标**：每个自制零件一个 `.py` 脚本，总成一个 `assembly.py`。

1. 每个脚本顶部 `from params import ...`（只导入需要的参数）
2. 建模策略：
   - 旋转体 → `Workplane.circle().extrude().revolve()`
   - 板件 → `Workplane.rect().extrude()` + 布尔运算
   - 孔位 → `Workplane.pushPoints().hole()` / `.cboreHole()`
   - 圆角/倒角 → `.fillet()` / `.chamfer()`
3. 每个脚本暴露 `make_<part>()` 函数，返回 `cq.Workplane` 或 `cq.Assembly`
4. `assembly.py`：
   - 用 `cq.Assembly` 组合所有零件
   - 相对定位（translate/rotate），不用绝对坐标
   - 暴露 `export_assembly(output_dir)` 函数
5. 导出 STEP AP214 格式：`cq.exporters.export(shape, path)`

**检查点**：每个零件单独可导出STEP，在CAD查看器中尺寸正确。

### 阶段 3.5：渲染数据提取（从设计文档生成3D渲染数据表）

**目标**：从设计文档中提取结构化数据，填充 §X.10 3D渲染数据章节的5张表格，供文生图技能消费。

**前提**：设计文档已包含 §X.1 结构参数、§X.6 紧固件清单、§X.8 BOM（即阶段1-2产出可用）。

**步骤**：

1. **填写表1：装配层叠结构表**
   - 数据来源：§X.1 各模块详细设计 + §X.6 紧固件清单
   - 从基座/机械臂端到工作端，按物理连接顺序排列
   - 标明每层的固定/运动关系（对应 assembly.py 的定位逻辑）
   - 写明连接方式（螺栓规格×数量、过盈配合等级、粘接等）

2. **填写表2：视觉标识表**
   - 数据来源：§X.8 BOM（材质列）+ §X.1（外形尺寸）
   - 为每个零件分配唯一视觉标签（相对尺寸词+固定方向词+颜色）
   - 相似零件必须有可区分的标签（如两个银色圆柱→LONG/SHORT）
   - material_type 与 drawing.py 技术要求区匹配

3. **填写表3：迭代渲染分组表**
   - 分组算法（通用）：
     - Step 1 = 主体框架/底座（所有后续步骤的锚点）
     - Step 2~3 = 前景模块（等轴测视角下最显眼的）
     - Step 4~N = 背景/被遮挡模块
     - 每步最多3个紧密相关零件
     - 总步数 ≈ ceil(零件数 / 2.5) + 1（底图）
   - 标注每步的画面位置（用image坐标：左前/右前/左后/右后）
   - 写明prompt要点（从表2提取唯一标签）

4. **填写表4：视角规划表**
   - 至少3个视角：等轴测（全貌）+ 爆炸图（装配层级）+ 三视图（标注）
   - 每个视角标注可见/遮挡模块
   - 仰角/方位角建议值

5. **填写表5：否定约束表**
   - 从设计文档中识别AI容易犯错的几何关系
   - 典型约束类型：
     - 空腔/通孔约束（"此处为空，不要补零件"）
     - 方向约束（"电机仅在X侧"）
     - 尺寸约束（"A始终比B长"）
     - 存在性约束（"不要发明未描述的零件"）

**检查点**：
- [ ] 5张表格数据与设计文档/BOM一致（零件数、材质、尺寸）
- [ ] 表2每个零件有唯一视觉标签，相似零件可区分
- [ ] 表3分组数合理（ceil(N/2.5)+1），每步≤3零件
- [ ] 表4至少3个视角，可见性列完整
- [ ] 表5至少包含"不要发明零件"约束
- [ ] **表0装配姿态定义**：明确坐标系原点、X/Y/Z轴方向、法兰面朝向（水平/竖直），所有后续表格的方向描述必须引用此坐标系
- [ ] 表1每行有"模块轴线方向"列，使用坐标系术语（沿Z / ∥XY / ⊥法兰面），禁止模糊词"向下""水平"
- [ ] 表2"方向约束"列使用坐标系术语（∥法兰面 / ⊥法兰面 / 沿-Z），禁止无参考系的"horizontal""vertical"

### 阶段 4：2D 工程图（ezdxf — GB/T 国标工程图）

**目标**：每个自制零件一张可直接用于加工的 GB/T 国标 A3 工程图。

经过三轮对抗性审查（R1合规性 → R2实现可行性 → R3加工实用性），最终方案如下。

#### 4.1 引用标准体系

| 标准号 | 内容 | 应用场景 |
|--------|------|---------|
| GB/T 4457.4-2002 | 图线（线型/线宽） | 图层定义、linetype模式 |
| GB/T 17450-1998 | 图线dash/gap模式 | 自定义CENTER/DASHED linetype |
| GB/T 4458.1-2002 | 三视图投影（第一角） | 视图布局、对齐规则 |
| GB/T 4458.4-2003 | 尺寸标注 | dimstyle参数、箭头、文字高度 |
| GB/T 4458.6-2002 | 剖视图 | 剖切符号、剖面线、全剖/半剖/局部剖 |
| GB/T 4457.5-2013 | 剖面线 | hatch图案选择 |
| GB/T 4459.1-1995 | 螺纹画法 | 内/外螺纹表示 |
| GB/T 14692-2008 | 投影法标识 | 第一角投影符号 |
| GB/T 10609.1 | 图框/标题栏 | A3图框(25mm装订边) + 180×56mm标题栏 |
| GB/T 14691-1993 | 工程制图字体 | 仿宋体(FangSong) |
| GB/T 1804-2000 | 一般公差 | 未注公差等级(m) |
| GB/T 131-2006 | 表面粗糙度符号 | 默认Ra + 关键面Ra标注 |
| GB/T 1182-2018 | 形位公差 | GD&T框 + 基准定义 |

#### 4.2 复用通用引擎

从 `D:/cad-skill/cad/end_effector/` 复制或导入：

- **`drawing.py`** — 基础绘图引擎（全部函数列表）：

  **文档创建**：
  - `create_drawing(title, scale)` — 创建R2013文档 + 仿宋字体 + 替换linetype + 图层 + dimstyle

  **尺寸标注**（模块常量控制参数）：
  - `add_linear_dim(msp, p1, p2, offset, text, angle)` — 线性标注(ezdxf原生dim entity)
  - `add_diameter_dim(msp, center, radius, angle_deg, text)` — 直径标注(手工leader，跨viewer兼容)
  - `add_radius_dim(msp, center, radius, angle_deg, text)` — 半径标注
  - `_add_arrow(msp, tip, angle_deg, size)` — 30°填充箭头

  **GD&T / 表面 / 基准**：
  - `add_gdt_frame(msp, pos, entries)` — 特征控制框
  - `add_surface_symbol(msp, pos, ra)` — 表面粗糙度符号(GB/T 131)
  - `add_datum_symbol(msp, attach_point, label, direction)` — 基准三角+字母框(GB/T 1182)
  - `add_default_roughness(msp, ra, pos)` — 图框右上角默认粗糙度符号

  **中心线 / 隐藏线**：
  - `add_centerline_cross(msp, center, size)` — 中心十字
  - `add_centerline_h(msp, y, x1, x2)` / `add_centerline_v(msp, x, y1, y2)` — 水平/垂直中心线

  **剖视图/局部放大/向视图辅助函数**：
  - `add_section_view_label(msp, pos, label)` — 剖视图标题, e.g. "A-A"
  - `add_detail_label(msp, pos, label, scale_factor)` — 局部放大标题, e.g. "I (2:1)"
  - `add_detail_circle(msp, center, radius, label)` — 源视图上的放大圈+标签
  - `add_auxiliary_label(msp, pos, label)` — 向视图标题, e.g. "C向"
  - `add_section_hatch_with_holes(msp, outer_boundary, inner_boundaries, pattern, scale)` — 带内腔扣除的剖面线填充

  **多视图布局**：
  - `calc_multi_view_layout(views, paper, title_h, gap)` — 灵活布局（支持 section_right/section_below/detail_br）

  **剖视图**：
  - `add_section_hatch(msp, boundary_points, pattern, scale)` — 剖面线填充
  - `add_section_symbol(msp, start, end, label, arrow_dir)` — GB/T 4458.6 剖切符号

  **螺纹**：
  - `add_thread_hole(msp, center, major_d, minor_d, thread_spec, depth, is_end_view)` — GB/T 4459.1 螺纹画法+标注

  **制造注释**：
  - `add_technical_notes(msp, notes, material_type, pos)` — 技术要求区(含默认注释集)

  **图框/标题栏/布局**：
  - `add_border_frame(msp, 420, 297)` — A3图框（25mm装订边）
  - `add_gb_title_block(msp, ...)` — GB/T 10609.1 标题栏（180×56mm）
  - `calc_three_view_layout(front_wh, top_wh, left_wh)` — 自动计算视图位置+缩放
  - `add_projection_symbol(msp, pos)` — 第一角投影符号

- **`draw_three_view.py`** — ThreeViewSheet 框架类：
  ```python
  sheet = ThreeViewSheet(part_no, name, material, scale, weight_g, date)
  sheet.draw_front(draw_func, bbox=(w,h))   # draw_func(msp, ox, oy, scale)
  sheet.draw_top(draw_func, bbox=(w,h))
  sheet.draw_left(draw_func, bbox=(w,h))     # 对称件可省略
  sheet.draw_section(draw_func, label, bbox, position)  # 剖视图(position="right"/"below")
  sheet.draw_detail(draw_func, label, bbox, scale_factor, position)  # 局部放大(position="bottom_right")
  sheet.draw_auxiliary(draw_func, label, bbox, position)  # 向视图
  sheet.save(output_dir, material_type="al") -> str
  # save() 自动调用: border + layout + 技术要求 + 默认粗糙度 + 标题栏 + 投影符号
  # 自动选择 calc_three_view_layout（≤3标准视图）或 calc_multi_view_layout（含扩展视图）
  ```

#### 4.3 线型/线宽体系（GB/T 4457.4 + GB/T 17450）

基本线宽 **d = 0.50mm**（A3小零件推荐值），粗细比 **2:1**。

| 图层 | 颜色 | 线宽 | 线型 | 用途 |
|------|------|------|------|------|
| OUTLINE | 7 (白) | 0.50mm (d) | Continuous | 可见轮廓（粗实线） |
| THIN | 7 | 0.25mm (d/2) | Continuous | 尺寸线/引出线（细实线） |
| DIM | 3 (绿) | 0.25mm | Continuous | 尺寸标注 |
| GDT | 1 (红) | 0.25mm | Continuous | 形位公差 |
| CENTER | 1 | 0.25mm | CENTER¹ | 中心线/对称线（细点画线） |
| HIDDEN | 8 (灰) | 0.25mm | DASHED¹ | 不可见轮廓（细虚线） |
| HATCH | 8 | 0.18mm | Continuous | 剖面线 |
| TEXT | 7 | 0.25mm | Continuous | 注释文字 |
| BORDER | 7 | 0.50mm | Continuous | 图框 |
| SECTION_CUT | 1 | 0.50mm | CENTER¹ | 剖切线（端部叠加粗实线段） |
| BREAK_LINE | 7 | 0.25mm | Continuous | 断裂线 |
| THREAD_MINOR | 7 | 0.25mm | Continuous | 螺纹小径(细实线/3/4弧) |

¹ 内置linetype被替换为GB/T 17450模式：

```python
# 在 create_drawing() 中替换（不新建名字，已有代码自动生效）：
doc.linetypes.remove("DASHED")
doc.linetypes.add("DASHED",
    pattern=[7.5, 6.0, -1.5],                  # 12d划, 3d隔
    description="GB/T 17450 dashed (d=0.5)")

doc.linetypes.remove("CENTER")
doc.linetypes.add("CENTER",
    pattern=[15.5, 12.0, -1.5, 0.5, -1.5],     # 24d长划/3d隔/1d短划/3d隔
    description="GB/T 17450 center (d=0.5)")

# 不设 $LTSCALE（保持1.0），linetype pattern按纸面mm设计
# hatch pattern scale 由 set_pattern_fill() 的 scale 参数独立控制
```

**关键决策**：替换而非新建 linetype name → 所有已有 `linetype="CENTER"` / `"DASHED"` 的代码自动受益。

#### 4.4 尺寸标注体系（GB/T 4458.4）

```python
# ── 模块常量（drawing.py 顶部）──
DIM_TEXT_H         = 3.5                    # mm (GB/T标准系列: 2.5/3.5/5)
DIM_ARROW          = 3.0                    # mm (≈文字高度)
ARROW_HALF_ANGLE   = math.radians(15)       # GB/T 4457.4: 30°总角
DIM_EXT_BEYOND     = 2.0                    # 界线超出尺寸线 2mm
DIM_EXT_OFFSET     = 1.0                    # 界线偏移被注点 1mm
DIM_GAP            = 1.0                    # 文字间距 1mm
```

**dimstyle "ISO-25"**：
```python
dimtxt = DIM_TEXT_H      # 不乘scale，纸面mm
dimasz = DIM_ARROW
dimexe = DIM_EXT_BEYOND
dimexo = DIM_EXT_OFFSET
dimgap = DIM_GAP
dimtad = 1               # 文字在尺寸线上方
```

**重要规则**：
- `add_linear_dim()` 不带 hardcoded override，由 dimstyle 控制
- `add_diameter_dim()` / `add_radius_dim()` 使用模块常量（手工绘制，不走dimstyle）
- `_add_arrow()` 半角 = `ARROW_HALF_ANGLE` (15°)，size = `DIM_ARROW` (3.0mm)
- **所有标注/注释文字高度为纸面mm（不乘view scale）**

#### 4.5 字体（GB/T 14691）

```python
# 工程图专用字体：仿宋体（非宋体）
std.dxf.font = "simfang.ttf"
std.set_extended_font_data("FangSong")
```

#### 4.6 三视图布局（GB/T 4458.1 第一角投影法）

```
┌──────────────────────────────────────────────────┐
│ (默认粗糙度)                          (Ra3.2)   │
│  技术要求:                                       │
│  1. 未注公差按GB/T 1804-m                        │
│  2. ...                                          │
│                                                  │
│  ┌──────────┐        ┌──────────┐               │
│  │  主视图   │        │  左视图   │               │
│  │          │        │          │               │
│  └──────────┘        └──────────┘               │
│  ┌──────────┐        ┌──────────┐               │
│  │  俯视图   │        │  剖视图   │(A-A等)       │
│  │          │        │          │               │
│  └──────────┘        └──────────┘               │
│  ⊿ ┌────────────────────────────────────────┐   │
│    │              标题栏 180×56              │   │
│    └────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

对齐规则（由 `calc_three_view_layout` 坐标约束保证）：
- **长对正**：主视图↔俯视图 X对齐
- **高平齐**：主视图↔左视图 Y对齐（底部对齐）
- **宽相等**：俯视图Y深度 = 左视图X深度

**不画投影连接线**（成品图不需要）。
**不画标准位置视图标签**（标准位置不需要"主视图"/"俯视图"/"左视图"标签）。
仅对非标准视图（剖视图/局部视图/旋转视图）标注标签如 "A-A"。

#### 4.7 剖视图（GB/T 4458.6）

**剖切符号**：`add_section_symbol(msp, start, end, label, arrow_dir)`
- 中间段：CENTER linetype（SECTION_CUT图层）
- 两端：叠加粗实线短段(5~10mm) + 箭头（指向投影方向）
- 标注字母(A, B等)在箭头外侧

**剖面线**（GB/T 4457.5）：
- **单件图**：统一 ANSI31（45° 等距细实线），间距由 `scale` 参数控制
- **装配剖视图/多材料组合件**：不同材料不同图案
  - 铝合金 → ANSI31（45°单向线）
  - 钢 → ANSI32（交叉线）
  - PEEK/塑料 → ANSI32
  - 橡胶/弹性体 → ANSI37

**剖视类型选择**：
| 零件特征 | 推荐剖视 | 实现方式 |
|---------|---------|---------|
| 对称旋转体（法兰、适配板） | 半剖 | 中心线左半外形+右半剖面，手工画两半 |
| 壳体/箱体 | 全剖 | 整个视图画剖面 |
| 局部内部特征（支架传感器孔） | 局部剖 | 波浪断裂线分界 |
| 薄片件（翻盖） | 不剖 | 外形+hidden线已足够 |

**半剖实现指南**（不做通用函数，各零件手工实现）：
- 中心线左侧：画外形轮廓 + 隐藏线(HIDDEN)
- 中心线右侧：画剖面轮廓 + 剖面线(add_section_hatch)
- 中心线(CENTER)分界

#### 4.8 螺纹画法（GB/T 4459.1）

`add_thread_hole(msp, center, major_d, minor_d, thread_spec, depth, is_end_view)`

**端视图**：
- 小径（牙底）= 粗实线全圆（OUTLINE图层）
- 大径（牙顶）= 细实线3/4圆弧（THREAD_MINOR图层），缺口在右上象限
- `msp.add_arc(center, major_d/2, start_angle=0, end_angle=270)`

**侧视图**：
- 小径 = 粗实线一对平行线
- 大径 = 细实线一对平行线
- 螺纹终止线 = 粗实线

**标注格式**：
- 通孔：`M3×0.5 通` 或 `6-Φ3.2 通`（光孔）
- 盲孔：`M3×0.5-6深`（有效螺纹深度）
- 需同时标注钻孔深度（盲孔）

#### 4.9 制造注释体系（技术要求 + 默认粗糙度 + 基准）

**技术要求区**：`add_technical_notes(msp, notes, material_type, pos)`
位置：图框内左上角区域(≈x=27, y=220)

按材料类型预置：

**铝合金件** (material_type="al")：
```
技术要求:
1. 未注公差按 GB/T 1804-m
2. 未注外倒角 C0.5, 精密孔口倒角 C0.2
3. 锐边去毛刺, O型圈槽口 R0.1~R0.2
4. 表面处理: 硬质阳极氧化, 膜厚≥25µm
5. 未注粗糙度 Ra3.2
6. 零件打标: 料号+批次号, 字高2mm
```

**PEEK件** (material_type="peek")：
```
技术要求:
1. 未注公差按 GB/T 1804-m
2. 注塑后去飞边, 锐边去毛刺
3. 未注粗糙度 Ra1.6
4. 材料: PEEK (Victrex 450G 或等效)
5. 零件打标: 料号+批次号, 字高1.5mm
```

**钢件** (material_type="steel")：
```
技术要求:
1. 未注公差按 GB/T 1804-m
2. 未注外倒角 C0.3
3. 锐边去毛刺
4. 表面处理: 镀锌钝化
5. 未注粗糙度 Ra3.2
```

**尼龙件** (material_type="nylon")：
```
技术要求:
1. 未注公差按 GB/T 1804-m
2. 注塑后去飞边, 锐边去毛刺
3. 未注粗糙度 Ra1.6
4. 材料: PA66 (尼龙66) 或等效
5. 零件打标: 料号+批次号, 字高1.5mm
```

**橡胶件** (material_type="rubber")：
```
技术要求:
1. 未注公差按 GB/T 1804-m
2. 模压后修除飞边, 分型线残余≤0.3mm
3. 硬度: Shore A 40±5
4. 未注粗糙度 Ra3.2
```

**默认粗糙度符号**：`add_default_roughness(msp, ra, pos)`
- 位置：图框右上角 (≈395, 280)
- 带括号的Ra符号（GB/T 131-2006），表示"未单独标注的所有表面"
- 铝件/钢件/橡胶 Ra3.2，PEEK/尼龙 Ra1.6

**基准符号**：`add_datum_symbol(msp, attach_point, label, direction)`
- 等边三角形(边长5mm) + 方框字母
- 底边附着在基准面/轴线上
- **GD&T框引用的基准必须在图上有对应三角标注**
- 典型基准定义：A=主轴线/主孔轴线, B=主安装面, C=定位特征

#### 4.10 材料标注规范

材料名称使用中文国标格式（非西方缩写）：
| BOM/设计文档中 | 标题栏中应写 |
|---------------|-------------|
| 7075-T6 Al | 7075-T6 铝合金 |
| SUS304 | SUS304 不锈钢 |
| PEEK | PEEK (聚醚醚酮) 或含牌号 |
| PA66 | PA66 (尼龙66) |
| 65Mn弹簧钢 | 65Mn 弹簧钢 |

#### 4.11 图框线宽（GB/T 10609.1）

修改 entity-level override（非图层）：
- `add_border_frame()`：外框 lineweight=25 (0.25mm, 细线)，内框 lineweight=50 (0.50mm=d, 粗线)
- `add_gb_title_block()`：外框 lineweight=50 (0.50mm=d)

#### 4.12 视图绘制函数签名与规范

```python
def part_front_view(msp, ox, oy, scale):
    """在 (ox, oy) 为原点、按 scale 缩放绘制主视图。"""
    s = scale
    # 几何：msp.add_lwpolyline / add_circle / add_line
    # 图层：OUTLINE=可见轮廓, HIDDEN=不可见轮廓, CENTER=中心线
    # 尺寸：add_linear_dim / add_diameter_dim（文字高度不乘s）
    # 剖面：add_section_hatch (单件图统一ANSI31)
    # 螺纹：add_thread_hole
    # 基准：add_datum_symbol
```

**关键规范**：
- 直接从 params.py 绘制 2D 轮廓，不依赖 3D→2D 投影
- 标注从 tolerances.py 取公差文本
- **所有标注/注释文字高度为纸面mm（不乘scale）**
- 坐标乘 scale，文字高度不乘 scale
- 每个视图必须包含：可见轮廓(OUTLINE) + 不可见轮廓(HIDDEN) + 中心线(CENTER) + 完整尺寸链
- **GB/T 4458.4 标注规则（V5强制）**：
  - 尺寸标注仅用数字+标准符号（Φ、R、C、M、PCD），**不得附加零件名称或功能描述**
  - 错误示例：`"泵腔 Φ20×25"`, `"止口 3"`, `"鳍片8"`, `"t=3"`, `"总高43"`
  - 正确示例：`"Φ20"`, `"3"`, `"8"`, `"3"`, `"43"`
  - 材料信息**仅在标题栏和技术要求区出现**，不在视图中标注
  - **不可见内部结构用 HIDDEN 图层（虚线），不得用 THIN（细实线）**
  - 剖面切穿的特征在剖视图中变为可见轮廓(OUTLINE)，非切穿的深层结构仍为HIDDEN

#### 4.13 小件缩放策略
- 标准件：1:1 或 1:2（由 calc_three_view_layout 自动计算）
- 小型轴类（Φ<30mm）：2:1
- 薄片件（t<5mm）：5:1
- 对称旋转体：可省略左视图（2-view sheet）

#### 4.14 3D渲染数据章节规范（设计文档新增）

任何子系统的设计文档如果要支持CAD建模+3D渲染，必须在末尾新增 `§X.10 3D渲染数据` 章节，包含5张结构化表格：

| 表格 | 章节号 | CAD消费 | 文生图消费 |
|------|--------|---------|-----------|
| 装配层叠结构表 | §X.10.1 | assembly.py 零件定位 | ASSEMBLY STRUCTURE段 |
| 视觉标识表 | §X.10.2 | material_type + drawing.py | GEOMETRY ANCHOR段 |
| 迭代渲染分组表 | §X.10.3 | — | 迭代步骤prompt |
| 视角规划表 | §X.10.4 | — | IMAGE LAYOUT + VISIBILITY段 |
| 否定约束表 | §X.10.5 | — | CRITICAL CONSTRAINTS段 |

**表格模板**（见 `docs/design/04-末端执行机构设计.md` §4.10 作为范例）：

**表1 装配层叠结构表**：
```
| 层级 | 零件/模块 | 固定/运动 | 连接方式 | 安装面朝向 | 相对上一层偏移 |
```

**表2 视觉标识表**：
```
| 零件 | 材质 | 表面颜色 | 唯一标签 | 外形尺寸(mm) | 方向约束 |
```
- 唯一标签 = 相对尺寸词(LONG/SHORT) + 颜色 + 形状
- 相似零件必须有可区分标签

**表3 迭代渲染分组表**：
```
| 步骤 | 添加内容 | 画面位置 | prompt要点 | 依赖步骤 |
```
- 分组规则：Step 1=框架, 前景优先, 每步≤3零件
- 总步数 = ceil(零件数/2.5) + 1

**表4 视角规划表**：
```
| 视角ID | 名称 | 仰角/方位 | 可见模块 | 被遮挡模块 | 重点表达 |
```
- 最少3视角（等轴测+爆炸图+三视图）

**表5 否定约束表**：
```
| 约束ID | 约束描述 | 原因 |
```
- 至少包含"不要发明未描述的零件"

**设计文档最低必需章节**（支持CAD+渲染）：
```
§X.1   功能与结构参数         ← CAD: params.py
§X.4   概念设计尺寸表         ← CAD: tolerances.py
§X.6   紧固件清单             ← CAD: assembly.py + 文生图: MOUNTING FACES
§X.8   BOM树与零件编号        ← CAD: bom.py + 文生图: 材质颜色
§X.10  3D渲染数据（新增）     ← 文生图: 迭代流水线
```

**检查点**：
- [ ] 每张图有 A3图框 + 第一角投影符号 + GB/T标题栏
- [ ] 三视图对齐正确（长对正/高平齐/宽相等）
- [ ] 技术要求区完整（按材料类型）
- [ ] 默认粗糙度符号在右上角
- [ ] 所有GD&T引用的基准有对应三角标注
- [ ] 螺纹标注含规格+深度/通
- [ ] 有剖视图的零件有对应剖切线
- [ ] 材料名使用中文国标格式

### 阶段 5：渲染

#### 5a. DXF→PNG 预览（render_dxf.py）

**目标**：DXF → PNG 本地预览（无需安装CAD软件）。

1. **直接复用** `D:/cad-skill/cad/end_effector/render_dxf.py`（无需修改）
2. 关键配置：
   - 黑色背景（`BG_COLOR = "#000000"`）——DXF color 7(白色)文字可见
   - `ColorPolicy.COLOR`（不做黑白互换）
   - `HatchPolicy.NORMAL`
   - 中文字体通过 matplotlib rcParams 设置（FangSong 或 SimSun fallback）
3. 运行：`python render_dxf.py` 渲染 D:/GISBOT/cad/output/ 下所有DXF

#### 5b. Blender Cycles 照片级3D渲染（render_3d.py + render_exploded.py）

**目标**：CAD几何驱动的照片级渲染，100%空间精确。

**技术路线**：`CadQuery Assembly → GLB → Blender Cycles CPU → PNG`

**优势**（相比文生图）：
- 几何100%精确（来自CAD模型，非AI想象）
- 跨视角完全一致（同一模型不同角度）
- PBR材质可控（铝/PEEK/钢/橡胶参数化）
- 无需GPU/OpenGL（Cycles CPU软件光追，RDP会话可用）

**依赖**：Blender 4.x portable（`D:/cad-skill/tools/blender/blender.exe`）

**配置系统**（通用化，W4/W12）：

渲染参数已从脚本硬编码提取为JSON配置文件 `render_config.json`：
- **材质映射**：`materials` 节 → 零件名模式到预设名的映射（15种内置预设，见 `render_config.py MATERIAL_PRESETS`）
- **相机预设**：`camera` 节 → 支持笛卡尔(location+target)和球坐标(azimuth_deg+elevation_deg)双模式
- **爆炸参数**：`explode` 节 → 径向展开角度/距离/Z偏移规则
- **灯光自适应**：能量∝(bounding_radius/300)²，从GLB自动检测包围盒(W14)
- **Prompt变量**：`prompt_vars` 节 → 产品名+各零件材质描述，供AI增强prompt使用

配置文件位置：`D:/cad-skill/cad/<subsystem>/render_config.json`
空白模板：`D:/cad-skill/docs/templates/render_config_template.json`
配置引擎：`D:/cad-skill/cad/<subsystem>/render_config.py`（stdlib-only，Blender Python可用）

**使用**：
```bash
# 使用配置文件渲染（推荐，通用方式）
D:/cad-skill/tools/blender/blender.exe -b -P render_3d.py -- --config render_config.json --all
D:/cad-skill/tools/blender/blender.exe -b -P render_exploded.py -- --config render_config.json
# 不使用配置文件（向后兼容，使用硬编码默认值）
D:/cad-skill/tools/blender/blender.exe -b -P render_3d.py -- --all
D:/cad-skill/tools/blender/blender.exe -b -P render_3d.py -- --view V1
# 一键构建+渲染
python build_all.py --render
```

#### 5c. 混合渲染管线：Blender CAD + Gemini AI 增强（推荐）

**目标**：结合CAD几何精度与AI照片级材质，生成**双用途**图像——既能给用户/客户展示，也能作为加工参考。

**技术路线**：
```
CadQuery Assembly → GLB → Blender Cycles CPU → 基础PNG（几何精确）
    → Gemini AI 图像编辑（--image 模式）→ 照片级增强JPG（材质逼真）
```

**核心优势**：
- **几何100%精确**：来自CAD参数化模型（Blender渲染），非AI空间推理（~42%准确率）
- **材质照片级**：Gemini AI增强金属反射/SSS/环境光/阴影，远超Blender Cycles CPU效果
- **跨视角一致**：5张图基于同一GLB模型，零件形态/比例/位置完全一致
- **双用途输出**：PNG精确几何→加工/审图；JPG照片级→展示/答辩/商业计划书
- **配置驱动**：材质/相机/prompt变量从`render_config.json`读取，新子系统只需填配置

**工作流步骤**：

1. **生成GLB**：`python build_all.py`（在STEP导出后自动导出GLB）
2. **Blender渲染5视角**：
   ```bash
   D:/cad-skill/tools/blender/blender.exe -b -P render_3d.py -- --config render_config.json --all   # V1/V2/V3/V5
   D:/cad-skill/tools/blender/blender.exe -b -P render_exploded.py -- --config render_config.json   # V4
   ```
   输出：`D:/GISBOT/cad/output/renders/V1_front_iso.png` ~ `V5_ortho_front.png`

3. **复制基础渲染到bananapro/**：
   ```bash
   cp D:/GISBOT/cad/output/renders/V*.png bananapro/
   ```

4. **Gemini AI增强**（统一模板，按视角类型自动切换）：
   ```bash
   # 所有视角使用统一模板 prompt_enhance_unified.txt
   # prompt_data_builder.py 从 params.py 自动生成装配/材质/约束数据
   python tools/hybrid_render/prompt_builder.py --config cad/end_effector/render_config.json --view V1
   # 或通过 cad_pipeline.py enhance --subsystem end_effector 批量增强
   ```
   输出：`bananapro/gemini_YYYYMMDD_HHMMSS.jpg`（5张增强图）

**Prompt模板生成**：

统一模板 `prompt_enhance_unified.txt`，9 段结构（§1几何锁定 §2坐标系 §3视角 §4装配结构 §5材质 §6标准件 §7否定约束 §8多视角一致性 §9环境灯光）。

按 `render_config.json` 的 `camera.V*.type` 字段自动切换视角特定内容：
| type | 用途 | 风格要点 |
|------|------|---------|
| standard | V1/V2/V3 | 产品摄影：3点布光+金属反射 |
| exploded | V4 | 爆炸图：保留间距+浮动阴影 |
| ortho | V5 | 正交投影：无透视畸变 |
| section | V6 | 剖面图：切面材质+截面线 |

装配/材质/约束数据由 `prompt_data_builder.py` 从 `params.py` 自动生成。

**Prompt编写要点**（R8-R11验证）：
- **第一行必须写**："Keep ALL geometry and proportions EXACTLY as shown"
- **只描述材质增强**：逐零件按颜色对应写PBR材质
- **不描述几何**：几何来自CAD渲染，Gemini只负责"换皮"
- **不超过20行**：prompt过长会导致Gemini过度修改几何
- **材质描述来源**：`render_config.json → prompt_vars.material_descriptions`

**输出文件用途对照**：

| 文件 | 用途 | 几何精度 | 视觉质量 |
|------|------|---------|---------|
| `D:/GISBOT/cad/output/*.step` | 加工/3D打印 | ★★★★★ | N/A |
| `D:/GISBOT/cad/output/*.dxf` | 2D工程图发图 | ★★★★★ | N/A |
| `D:/GISBOT/cad/output/renders/V*.png` | 审图/尺寸确认 | ★★★★★ | ★★★☆☆ |
| `bananapro/gemini_*.jpg` | 展示/答辩/商业计划书 | ★★★★☆ | ★★★★★ |

**注意事项**：
- Gemini API可能偶尔连接失败，失败时重试即可（不改prompt）
- Gemini增强后的JPG几何可能有微小偏差（<2%），不可用于尺寸测量
- 如需更新渲染：修改CAD模型 → 重新build_all.py → 重新Blender渲染 → 重新Gemini增强
- 新子系统创建自己的 `render_config.json`（从 `D:/cad-skill/docs/templates/render_config_template.json` 复制）
- 新子系统创建3份prompt文件（从配置的 `prompt_vars` 段生成材质描述行）
- 配置引擎 `render_config.py` 仅用stdlib（json/math/os），可在Blender Python中运行(W10)

### 阶段 6：一键构建（build_all.py）

**目标**：单一入口，从零生成全部产物。

```python
def build_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. STEP 导出
    for each part:
        shape = make_<part>()
        cq.exporters.export(shape, path)

    # 2. Assembly
    export_assembly(OUTPUT_DIR)

    # 3. DXF 工程图
    for each draw function:
        draw_<part>(OUTPUT_DIR)

    # 4. PNG 渲染（可选）
    from render_dxf import render_all
    render_all(OUTPUT_DIR)

    # 5. BOM CSV
    from bom import to_csv
    to_csv(os.path.join(OUTPUT_DIR, "BOM.csv"))

    # 6. Blender 3D渲染（可选，需 --render）
    #    D:/cad-skill/tools/blender/blender.exe -b -P render_3d.py -- --all
    #    D:/cad-skill/tools/blender/blender.exe -b -P render_exploded.py

    # 7. Gemini AI增强（可选，需手动执行或脚本化）
    #    见阶段5c混合渲染管线

    # 8. 汇报
    print(f"{n} STEP + {m} DXF + BOM generated")
```

**检查点**：`python build_all.py` 一次通过，无错误。

## 常见陷阱

| 问题 | 解决方案 |
|------|---------|
| ezdxf `set_font()` 报错 | 用 `style.set_extended_font_data("FangSong")` + `style.dxf.font = "simfang.ttf"` |
| LibreCAD 不显示中文 | 已知限制，用 render_dxf.py 生成PNG预览 |
| DXF color 7 在白底PNG上不可见 | 渲染用黑底 + `ColorPolicy.COLOR` |
| `MatplotlibBackend` 不接受 `params` 参数 | 字体通过 `plt.rcParams` 设置，不传给后端 |
| Windows控制台 GBK 编码错误 | 用 `python -X utf8` 运行，或避免特殊Unicode字符 |
| CadQuery Assembly 导出为空 | 确保每个零件都 `add()` 到 Assembly，且有 `name` 参数 |
| STEP 文件很大 | 正常，3D几何体通常 50~500KB |
| 内置linetype被替换后centerline函数不生效 | 替换名字保持"CENTER"/"DASHED"，不新建名字 |
| dimstyle修改后尺寸文字高度不变 | 检查是否有 `override={"dimtxt": ...}` 硬编码覆盖 |
| `add_diameter_dim` 不受dimstyle影响 | 该函数为手工绘制，需使用模块常量 DIM_TEXT_H/DIM_ARROW |
| 标注文字过小不可读 | 检查是否误乘了 view scale，文字高度应为纸面mm |
| $LTSCALE 污染图框/标题栏 | 不设全局$LTSCALE，linetype pattern直接按纸面mm设计 |
| 基准字母在GD&T框中无对应三角 | 每个datum引用必须在视图上有 add_datum_symbol() |
| 螺纹孔无深度/通标注 | add_thread_hole() 必须传 depth 或 through 参数 |
| 材料名写"Al"/"SS"被退图 | 使用中文："铝合金"/"不锈钢" |
| Blender渲染材质太平/不明显 | 用混合管线(阶段5c)：Blender出PNG，Gemini AI增强材质 |
| Gemini增强后几何变形 | prompt首行写"Keep ALL geometry EXACTLY"，只描述材质不描述几何 |
| Gemini API连接失败 | 直接重试，不改prompt；偶发性连接问题 |
| 新子系统无prompt数据 | 运行 `python prompt_data_builder.py --cad-dir cad/<subsystem> --update-config` 自动生成 |

## 质量检查清单

### 参数与BOM
- [ ] params.py 参数数量与设计文档一致
- [ ] tolerances.py 覆盖所有公差/GD&T条目
- [ ] bom.py 零件数量、总成本、总重量与设计文档一致
- [ ] bom.py 材料名与各 draw_*.py 标题栏材料一致（无矛盾）

### 3D建模
- [ ] 每个自制零件有对应的 3D 脚本
- [ ] STEP 文件可在 FreeCAD/CAD Viewer 中打开

### 2D工程图（加工发图检查）
- [ ] 每个自制零件有 GB/T 三视图 A3 图纸
- [ ] A3图框(25mm装订边) + 第一角投影符号 + GB/T标题栏
- [ ] 线型正确：粗实线(0.5mm)/细实线(0.25mm)/虚线(DASHED)/点画线(CENTER)
- [ ] 三视图对齐：长对正/高平齐/宽相等
- [ ] 技术要求区完整（按材料类型：铝/PEEK/钢）
- [ ] 默认粗糙度符号在图框右上角
- [ ] 关键配合面有单独Ra标注
- [ ] 所有GD&T引用的基准有对应基准三角标注
- [ ] 螺纹标注含规格+深度(盲)/通 — 无遗漏
- [ ] 有剖视图的零件有对应剖切线(带箭头+字母)
- [ ] 材料名使用中文国标格式
- [ ] 尺寸链完整、无冗余、无过约束
- [ ] 标注文字3.5mm仿宋体，纸面可读
- [ ] 箭头30°、界线超出2mm

### 构建与渲染
- [ ] `build_all.py` 一键运行无错误
- [ ] DXF 文件可在 AutoCAD/DWG TrueView 中打开
- [ ] PNG预览渲染正确（render_dxf.py）
- [ ] Blender 3D渲染5视角PNG生成（render_3d.py + render_exploded.py）
- [ ] Gemini AI增强5张JPG生成（混合管线阶段5c）
- [ ] 增强前PNG（几何精确）保留用于审图
- [ ] 增强后JPG（照片级）用于展示/答辩
- [ ] 所有文件已 git commit

## 参考实现
完整示例见 `D:/cad-skill/cad/end_effector/`（§4末端执行器，14个脚本，8个STEP，11张GB/T三视图DXF，48零件BOM）

## 2D工程图升级实施顺序（V4方案）

当需要将现有工程图从"草图级"升级到"可加工级"时，按以下阶段执行：

```
Phase 1   — 基础设施: drawing.py + draw_three_view.py
            (linetype替换/常量/dimstyle/字体/箭头/图框线宽/新函数)
Phase 1.5 — 可视化验证: 测试图(矩形+圆+全部线型+标注+螺纹+基准+技术要求)
            → ezdxf matplotlib渲染 + LibreCAD/DWG TrueView外部验证
Phase 2   — 模板零件: 选最复杂零件做模板(如法兰: 半剖+螺纹+基准+完整标注)
Phase 3   — 批量: 按模板改其余零件
Phase 4   — 全量验证: build_all.py → render_dxf.py → 逐张检查
```

## 3D渲染提示词编写规范（文生图配合）

当需要为机械子系统生成3D渲染图（使用文生图技能）时，提示词必须包含以下结构化内容，否则AI绘图模型无法正确表达零件间的装配关系。

### 必需章节

| 章节 | 内容 | 原因 |
|------|------|------|
| **ASSEMBLY STRUCTURE** | 从机械臂侧到工作端的层叠顺序，标明哪些是固定件、哪些是旋转件 | 避免电机位置/旋转关系画错 |
| **KINEMATIC CHAIN** | 传动链：电机→减速器→轴连接→旋转件，写明扭矩传递方式 | 避免"轴悬浮"不连接 |
| **MOUNTING FACES** | 每个连接点的螺栓规格、数量、PCD，安装面朝向（正面/背面） | 避免零件朝向错误 |
| **CABLE ROUTING** | 线缆走线路径、固定方式、分侧规则（动力线vs信号线） | 避免拖链悬浮 |

### 关键术语规则

- 建立"正面/背面"或"工位侧/机械臂侧"术语对，在prompt中全程一致使用
- 每个工位模块必须说明：安装面位置→主体延伸方向→工作端朝向→连接器位置
- 弹簧销/定位销必须说明：安装在哪个零件上（固定端还是旋转端），销入哪个零件的孔

### 多视角渲染建议

| 视角 | 重点表达 | 仰角/方位 |
|------|---------|----------|
| 前左等轴测 | 全貌+各工位分布+PEEK色带 | 30°/45° |
| 后右俯视 | 电机+减速器+拖链走线+后部模块 | 40°/225° |
| 纯侧视 | 层叠结构(Al+PEEK)+弹簧限力串联 | 0°/90° |
| 爆炸图 | 装配层级(LEVEL 1~4)+每个零件分离 | 30°/45° |
| 三视图 | 第一角投影+标注+螺栓孔位 | 正投影 |

### 提示词模板

```
Photorealistic 3D CAD rendering, [视角描述], of [产品名称].

ASSEMBLY STRUCTURE (from arm-side to work-side):
[层叠顺序，标明固定件/旋转件，扭矩传递方式]

MAIN BODY:
[主体几何描述，材质/表面处理，尺寸]

SUBASSEMBLIES:
[各模块描述，每个包含：安装方式→主体尺寸→工作端→连接器位置]

CABLE MANAGEMENT:
[线缆走线，固定端/活动端，分侧规则]

LIGHTING AND BACKGROUND:
[灯光、背景、渲染风格]
```

### R8审查发现的典型缺陷

| 缺陷 | 渲染后果 | 修复方法 |
|------|---------|---------|
| 未写明旋转/固定关系 | 电机跟着法兰转 | 加"motor is FIXED to arm, flange ROTATES" |
| 未写轴连接方式 | 输出轴悬浮在中心孔中 | 加"interference fit"/"spline"等 |
| 未写正面/背面 | 工位模块安装到背面 | 用"front face (toward GIS shell)"统一 |
| 未写弹簧销位置 | 定位机构不可见 | 加"spring pin detent holes at R=42mm on flange edge" |
| 未写拖链固定 | 拖链飘在空中 | 加"fixed end bolted to adapter plate, moving end to flange" |
| 未写信号调理模块 | 3D图遗漏重要组件 | 加"mounted on robot arm J3-J4 link, off-flange" |

### R9新增：跨视角一致性三条强制规则

**规则1 — GEOMETRY ANCHOR段**：所有视角prompt必须共用同一段几何锚点描述（含每个模块的安装半径R=XXmm、附属件精确方向）。禁止在不同视角prompt中对同一零件使用不同尺寸或措辞。

**规则2 — 绝对方向术语**：禁止"outward""alongside""below"等相对/模糊方向。改用"radially outward along arm axis""parallel to rotation axis""on +X tangential side wall"等绝对方向。

**规则3 — VISIBILITY声明**：每张视角prompt必须声明哪些零件可见/遮挡/部分可见，防止AI在零件应被遮挡时凭空画出（导致大小位置错误）。

### R10新增：四条多视角一致性强化规则

**规则4 — 画面坐标定位法(IMAGE LAYOUT)**：每个视角prompt必须追加IMAGE LAYOUT段，用画面坐标（image-TOP/BOTTOM/LEFT/RIGHT/FOREGROUND/BACKGROUND）描述关键零件在该张图片中的实际位置。物理坐标（front/rear/radially）AI不理解在2D投影中的方向。

**规则5 — 显式否定约束(NEVER段)**：每个prompt末尾加CRITICAL CONSTRAINTS，用大写NEVER列出3~5条禁止行为（如"NO mechanism from flange center toward workstation side"），抑制AI的创造性补全倾向。

**规则6 — 相似零件唯一视觉标签**：当prompt中有多个相似零件（如两个银色圆柱），必须用唯一标签区分：相对尺寸词(LONG/SHORT) + 固定方向词(ALWAYS horizontal/vertical) + 颜色区分。

**规则7 — Prompt长度控制(≤50行)**：GEOMETRY ANCHOR ≤15行，每视角只展开可见的2~3个工位，不可见工位一句话提及。IMAGE LAYOUT+VISIBILITY+CONSTRAINTS合计 ≤15行。总prompt ≤50行，防止注意力衰减。
