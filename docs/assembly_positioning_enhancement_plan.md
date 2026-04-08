# 3D 装配定位全链路增强方案

> **状态**: P0+P1a+P1b+P2 已实施，代码审查通过（4轮审查 + 2轮代码审查）  
> **作者**: Claude + procheng  
> **日期**: 2026-04-08  
> **关联问题**: GISBOT 渲染中零件分离/悬浮

---

## 一、问题定性

当前管线对 3D 装配定位的处理是**"事后启发式"**——提取器只从源文档的 §X.10.1
表格中抽取 6 行总成级层叠数据（Z/R/θ），Phase 2 的 `gen_assembly.py` 对无显式定位的零件
用尺寸估算 + 2mm 间隙堆叠。48 个零件中仅约 6 个有显式位置，其余 42 个靠猜测。

```
源文档 58KB ──提取器──→ CAD_SPEC.md 21KB ──codegen──→ assembly.py
     ↓                      ↓                          ↓
  丰富的空间信息          只保留6行总成级Z/R/θ        70%零件靠猜测堆叠
  (ASCII图、串联链、      零件级定位全部丢失          → 零件分离/悬浮
   零件尺寸表、否定约束)
```

**核心原则**：3D 装配定位应当是**"提取驱动"**——提取器尽量从源文档中抽取所有空间关系
信息，不足之处由审查器标出，由自动推算+用户确认补全，代码生成器消费结构化数据而非猜测。

---

## 二、修改范围与影响文件

> **关键约束**：所有改动必须针对管线 skill 自身的代码文件（提取器、默认值填充器、
> 审查器、渲染器、代码生成器、模板、skill 定义），**不得手动修改 CAD_SPEC.md 等中间产物**。
> 中间产物的内容变化必须完全由管线代码的改动自然产生。

### 2.1 改动文件清单

| 文件（均为 skill/管线代码） | 角色 | 改动级别 |
|---|---|---|
| `cad_spec_extractors.py` | 提取器 | **重大** — 新增 2 个函数，增强 3 个函数 |
| `cad_spec_defaults.py` | 默认值填充 + 推算 | **重大** — 新增定位推算逻辑，扩展 `STD_PART_DIMENSIONS` |
| `cad_spec_reviewer.py` | 审查器 | **重大** — 新增 7 项装配定位审查规则 |
| `cad_spec_gen.py` | 规格渲染器 | **中等** — 新增 §6.3/§6.4/§9 渲染 |
| `cad_pipeline.py` | 管线编排器 | **轻微** — Phase 1a 调用新增提取函数 |
| `codegen/gen_assembly.py` | 装配代码生成器 | **中等** — 消费新增结构化定位数据 |
| `templates/assembly.py.j2` | 装配代码模板 | **轻微** — 排除标记 + 注释标记 |
| `.claude/commands/cad-spec.md` | Skill 定义 | **轻微** — 审查项说明更新 |

> **注**：`bom_parser.py` 不改动。零件包络尺寸提取由新增的
> `extract_part_envelopes()` 完成（从多来源交叉收集），不修改 BOM 解析器本身的
> 输出 schema。这保证了 BOM 下游消费者（`gen_build.py`、`gen_parts.py` 等）不受影响。

### 2.2 不改动的文件

| 文件/目录 | 原因 |
|---|---|
| `cad/<subsystem>/CAD_SPEC.md` | **中间产物**，由 `cad_spec_gen.py` 自动生成 |
| `cad/<subsystem>/assembly.py` | **中间产物**，由 `codegen/gen_assembly.py` 自动生成 |
| `cad/<subsystem>/params.py` | **中间产物**，由 `codegen/gen_params.py` 自动生成 |
| `cad/<subsystem>/ee_*.py`, `std_*.py` | **中间产物**，由 codegen 自动生成 |
| `cad/<subsystem>/build_all.py` | **中间产物**，由 codegen 自动生成 |
| `cad/<subsystem>/render_3d.py` | 渲染脚本，不依赖装配定位改动 |
| `codegen/gen_std_parts.py` | 简化几何足够定位使用；精确几何后续手工精修 |
| `codegen/gen_params.py` | 参数提取逻辑不变 |
| `codegen/gen_build.py` | 构建表逻辑不变 |

---

## 三、坐标约定（本方案全文遵守）

> 以下约定与现有代码一致，列出以确保所有角色（建模、设计、装配）理解一致。

### 3.0.1 零件本体坐标系

- **原点**：零件底面中心，Z=0
- **主轴方向**：+Z 向上拉伸，高度 h 后顶面在 Z=h
- **依据**：`gen_parts.py` 生成的所有零件遵循此约定（如 `cq.Workplane("XY").extrude(h)`）

### 3.0.2 装配中的 translate 语义

- `translate((0, 0, z))` 将零件**底面**移动到 Z=z（零件顶面在 Z=z+h）
- **现有 gen_assembly.py 约定**：auto-stacking 计算的 z 值是零件**中心**位置
  （`center = cursor + extent/2`），直接作为 translate 参数。由于零件底面在原点，
  translate 后零件底面在 z，中心在 z+h/2，顶面在 z+h。
- **本方案统一为**：§6.3 中的"底面Z"记录的是**零件底面位置**（不是中心），
  与 translate 参数直接对应。gen_assembly 消费 §6.3 时不再做 ±h/2 调整。
- **新旧约定切换**：同一总成内的零件必须全部使用同一约定。
  gen_assembly 判断逻辑：该总成有 §6.3 数据 → **全部零件**用底面Z约定（含回退的零件）；
  该总成无 §6.3 数据 → **全部零件**用现有 center 约定（完全回退）。
  不允许同一总成内混用两种约定。

### 3.0.3 偏移坐标系

- §6.2（总成级）的 Z/R/θ 是**全局坐标**（相对于装配体原点）
- §6.3（零件级）的累积Z 是**工位局部坐标**（相对于工位安装面，安装面=Z=0）
- gen_assembly 的 `_station_transform()` 负责将工位局部坐标转换到全局坐标

### 3.0.4 堆叠方向

- 堆叠方向由 §6.2 的 `axis_dir` 列决定，不硬编码
- 常见方向：`(0,0,-1)` 向下悬挂、`(0,0,+1)` 向上堆叠、`(1,0,0)` 水平延伸
- 默认方向 `(0,0,-1)` 仅当 §6.2 未指定时使用
- 第一个零件底面在 Z=0（紧贴安装面），向堆叠方向延伸
  → 例如向下堆叠时 translate(0,0,-h)，向上堆叠时 translate(0,0,0)

---

## 四、提取器改造（`cad_spec_extractors.py`）

> **语言假设**：当前提取器的正则模式和关键词（如"径向"、"侧壁"、"安装于"）
> 面向**中文设计文档**。如需支持英文或其他语言的源文档，需为每种语言
> 补充关键词映射表（如 `"radially outward"` → `radial_extend`），
> 提取逻辑本身不变。
>
> **结构假设**：提取器假设源文档使用 Markdown 格式，含有标准表格（`|...|`）
> 和 fenced code block（\`\`\`）。不依赖特定子系统的料号前缀
> （如 `GIS-EE-`），料号模式从 config 中的 `prefix` 字段动态获取。

### 4.1 新增：`extract_part_placements()` — 零件级定位提取

> 本函数统一处理两类定位信息：(a) 串联堆叠链（axial_stack 模式）和
> (b) 非轴向定位描述（radial_extend/side_mount/coaxial/lateral_array 模式）。
> 串联堆叠链的提取逻辑见下文 4.1.1，非轴向模式见 §4.6。

#### 4.1.1 串联堆叠链提取（axial_stack 模式）

**动机**：源文档中各子总成可能有零件级的串联装配关系图（→ 箭头链和 ASCII art），
包含精确的零件名称和尺寸，例如：

```
悬臂安装面(40×40mm)
  → [4×M3×6螺栓, PCD=28mm] → 力传感器KWR42(Φ42×20mm, 70g)
  → [4×M3螺栓, PCD=36mm] → 弹簧限力上端板(Φ12×2mm)
  → 弹簧(Φ8×12mm自由长)+导向轴(Φ4×15mm)+套筒(Φ12×14mm)
  → 弹簧限力下端板(Φ12×2mm)
  → [4×M3螺栓] → 柔性关节(Φ30×15mm)
  → AE探头TWAE-03(Φ28×26mm)
```

从此类文本可精确计算每个零件的 Z 偏移，无需猜测。

**提取策略**：

1. 搜索源文档中的 fenced code block（\`\`\`包裹）和正文，匹配含 `→` 的多行文本
2. 每个节点提取：零件名称、尺寸（Φd×h / W×D×H）、连接方式（`[...]` 包裹的文本）
3. 节点的 part_name 与 BOM 零件的 name_cn 做模糊匹配（前 2-4 个中文字符），
   匹配成功则填充 part_no
4. 链的方向从所属工位的 §6.2 axis_dir 继承，默认 (0, 0, -1)

**输出 schema**：
```python
[
  {
    "assembly": "GIS-EE-003",           # 所属总成（从上下文推断）
    "anchor": "悬臂安装面",               # 链起点
    "direction": (0, 0, -1),             # 堆叠方向向量
    "chain": [
      {
        "part_name": "力传感器KWR42",
        "part_no": "GIS-EE-003-02",     # BOM 交叉匹配结果
        "dims": {"type": "cylinder", "d": 42, "h": 20},
        "connection": "4×M3×6螺栓",
        "sub_assembly": null,            # 非子总成内部件
      },
      {
        "part_name": "弹簧限力上端板",
        "part_no": null,                 # 非独立 BOM 件
        "dims": {"type": "disc", "d": 12, "h": 2},
        "connection": "4×M3螺栓",
        "sub_assembly": "GIS-EE-003-03", # ← 归属于弹簧限力机构总成
      },
      {
        "part_name": "弹簧+导向轴+套筒",
        "part_no": null,
        "dims": {"type": "cylinder", "d": 12, "h": 14},
        "connection": "压入",
        "sub_assembly": "GIS-EE-003-03",
      },
      {
        "part_name": "弹簧限力下端板",
        "part_no": null,
        "dims": {"type": "disc", "d": 12, "h": 2},
        "connection": "4×M3螺栓",
        "sub_assembly": "GIS-EE-003-03",
      },
      # ... 后续节点
    ]
  }
]
```

**`sub_assembly` 归属标记**：当连续的 `part_no=null` 节点的零件名与
某个 BOM 子总成的零件级参数表中的零件匹配时，自动填充该子总成的 part_no。
归属标记规则：
- 搜索 BOM 中标记为"自制"且名称含"总成"/"组件"的条目
- 在源文档中查找该子总成的零件级参数表（含"零件|规格|材质"列头的子表格）
- 将参数表中的零件名与链节点名模糊匹配
- 连续匹配同一子总成的节点标记相同的 `sub_assembly` 值

**子总成合并规则**（在 `compute_serial_offsets()` 中）：
- 连续的同一 `sub_assembly` 节点合并为一个单元
- 合并后的 part_no = sub_assembly 值（如 GIS-EE-003-03）
- 合并后的总高度 = 各子节点高度之和（2+14+2=18mm）
- 合并后的底面Z = 第一个子节点的底面Z
- 合并结果**同时更新 §6.4 包络尺寸表**（覆盖从 BOM 材质列猜测的值）
- §6.3 零件级定位表中只出现合并后的一行

**边界处理**：
- 链中节点无法匹配 BOM 也无法归属子总成 → `part_no: null, sub_assembly: null`，
  由审查器报 WARNING
- 链中节点无尺寸 → 标记 `dims: null`，由审查器报 WARNING
- 一个总成有多条链（不同方向堆叠）→ 各条链独立存储

### 4.2 新增：`extract_part_envelopes()` — 零件级包络尺寸提取

**动机**：零件尺寸分散在源文档的多个位置（BOM 材质列、零件级参数表、
模块包络尺寸描述、视觉标识表），当前只在 gen_assembly.py 中临时从 BOM
材质列 ad-hoc 解析。

**信息来源及优先级**：

| 优先级 | 来源 | 定位方式 | 示例 |
|--------|------|---------|------|
| P1 | 零件级参数表 | 含"外形"/"尺寸"列的子表格 | `壳体主体 \| 外形尺寸 \| 60×40×55mm` |
| P2 | 叙述文字中的包络描述 | 正则匹配"模块包络尺寸：..." | `模块包络尺寸：50×40×120mm` |
| P3 | BOM 材质列 | `_parse_dims_text()` 解析 | `不锈钢Φ38×280mm` |
| P4 | §X.10.2 视觉标识表的"外形尺寸"列 | 已有字段 | `Φ42×120(总长)` |
| P5 | 全局参数表 | 参数名含 OD/THICK/ENVELOPE | `FLANGE_BODY_OD=90` |

**合并规则**：同一零件有多个来源时，高优先级覆盖低优先级。

**输出 schema**：
```python
{
  "GIS-EE-001-01": {"type": "disc", "d": 90, "h": 25, "source": "P5:params"},
  "GIS-EE-002-02": {"type": "cylinder", "d": 38, "h": 280, "source": "P3:BOM"},
  "GIS-EE-003-02": {"type": "cylinder", "d": 42, "h": 20, "source": "P1:零件表"},
  "GIS-EE-004-01": {"type": "box", "w": 50, "d": 40, "h": 120, "source": "P2:叙述"},
}
```

### 4.3 改进：`extract_assembly_pose()` — 结构化解析 + 排除标记

**当前问题**：offset 和 axis_dir 列为原始文本，下游需重复解析。

**改进 (a) — offset 结构化**：

提取时解析 `Z=+73mm(向上)` 为数值，保留原文用于显示：
```python
{
  "level": "L2",
  "part": "ECX 22L电机+GP22C减速器",
  "offset": "Z=+73mm(向上)",           # 保持原文（向 CAD_SPEC.md 渲染用）
  "offset_parsed": {                    # 新增结构化字段
    "z": 73.0, "r": null, "theta": null, "is_origin": false
  },
  "axis_dir": "轴沿Z",
  "axis_dir_parsed": [                  # 新增结构化字段
    {"keyword": "", "direction": (0,0,1), "rotation": null}
  ],
}
```

**改进 (b) — axis_dir 多子句结构化**：

对如 `"壳体轴沿-Z（垂直向下），储罐轴∥XY（水平径向外伸）"` 的多子句文本，
提取时分离为独立子句并解析方向：
```python
"axis_dir_parsed": [
  {"keyword": "壳体", "direction": (0,0,-1), "rotation": null},
  {"keyword": "储罐", "direction": (1,0,0), "rotation": {"axis": (1,0,0), "angle": 90}},
]
```

> **rotation 约定**：使用 `{"axis": (x,y,z), "angle": degrees}` 而非字符串
> 简写，与 CadQuery 的 `.rotate(origin, axis, angle)` 参数直接对应。
> `null` 表示不旋转。

**改进 (c) — 排除标记**：

当前 BUG-10 修复直接丢弃 EE-006 行。改为**保留但标记 `exclude: true`**：
```python
{
  "part": "信号调理模块 (GIS-EE-006)",
  "exclude": true,
  "exclude_reason": "安装在J3-J4连杆上，不属于末端执行器",
  # ... 其余字段照常
}
```

这样审查器可以检查 BOM/assembly 排除一致性。

**影响范围**：`assembly.layers` 增加 `exclude` 字段后，所有消费 layers 的代码
都需要过滤 `exclude=true` 的行：
- `extract_connection_matrix()` — 不为 excluded 行生成连接记录
- `cad_spec_reviewer.py` — B1/B5 悬空检查排除 excluded 零件
- `cad_spec_gen.py` — 渲染 §6.2 时显示排除标记
- `codegen/gen_assembly.py` — 跳过 excluded 总成

### 4.4 改进：`extract_connection_matrix()` — 增加配合信息

**当前问题**：`fit` 字段永远为空（line 574 硬编码 `""`），无配合距离。

**改进内容**：

1. 从源文档中搜索与 partA/partB 相关段落的配合代号（正则 `[A-Z]\d+/[a-z]\d+`），填充 `fit` 字段
2. 从 §6.2 offset 列提取父子件间距，填充 `axial_gap`
3. 从紧固件清单提取 PCD

```python
{
  "partA": "法兰本体",
  "partB": "PEEK绝缘环",
  "type": "6×M3+碟簧垫圈",
  "fit": "H7/h7",              # ← 从源文档配合描述提取
  "torque": "0.7±0.1Nm",
  "axial_gap": 0.0,            # ← 新增：轴向(Z方向)间距(mm)
  "radial_clearance": 0.02,    # ← 新增：径向间隙(mm)，仅记录
  "pcd": 70.0,                 # ← 新增：螺栓圆分布直径
  "order": 6,
}
```

**axial_gap 与 radial_clearance 的区别**：

| 字段 | 含义 | 消费者 | 示例 |
|------|------|--------|------|
| `axial_gap` | 两零件配合面在堆叠方向上的间距 | `compute_serial_offsets()` — 累积到 Z 偏移中 | 碟簧垫圈压缩后≈0.5mm |
| `radial_clearance` | 两零件径向配合面的间隙 | 审查器 B13 干涉检查 — 不影响 Z 定位 | 台阶止口 H7/h7 间隙 0.01~0.04mm |

**取值约定**：
- `axial_gap = 0`：面接触（螺栓法兰连接、胶粘、焊接）
- `axial_gap > 0`：轴向有间隙（如碟簧、垫片、弹性元件压缩后的残余间隙）
- `axial_gap < 0`：轴向过盈（极少见）；3D 定位中视为 0
- `radial_clearance >= 0`：径向间隙；<0 为过盈配合（如轴承压入），3D 定位中视为同轴

**对 Z 偏移计算的影响**（在 `compute_serial_offsets()` 中）：
```
cursor = partA_bottom - partA_height   # partA 底面
cursor -= axial_gap                     # 跳过间隙
partB_bottom = cursor - partB_height   # partB 底面
```
```

### 4.5 改进：`extract_render_plan()` — 否定约束分类

**当前状态**：否定约束已提取（lines 772-787），但全部归入 `constraints` 列表，
不区分装配约束和渲染约束。

**改进**：根据描述文本中的关键词自动分类：

| constraint_type | 匹配关键词 | 消费者 |
|---|---|---|
| `assembly_exclude` | "不在...上"、"不画"、"排除"、"不属于" | gen_assembly 排除模块 |
| `orientation_lock` | "仅在"、"NEVER"、"始终"、"⊥"、"∥" | gen_assembly 校验朝向 |
| `position_lock` | "安装在...末端"、"R=XXmm" | gen_assembly 校验径向位置 |
| `geometry_void` | "空的"、"无任何"、"不要发明" | 渲染阶段/通用 |

每条约束新增 `target_parts` 字段：从描述文本中提取料号（正则匹配 `GIS-[A-Z]+-\d+`）
或零件名。

### 4.6 新增：非轴向定位模式提取

**动机**：串联堆叠链只能表达沿一个轴的线性堆叠关系。但实际装配中有大量零件
不在堆叠轴上，而是侧装、径向外伸、共轴压入、并列排布等。

**源文档中的典型场景**：

| 场景 | 源文档描述 | 定位模式 |
|------|-----------|---------|
| 储液罐水平外伸 | "Φ38×280mm，沿悬臂径向向外延伸" | `radial_extend` |
| 溶剂罐侧壁竖直 | "安装于壳体切向外侧壁，与模块主体并排竖直" | `side_mount` |
| LEMO 插头侧面 | "安装于模块侧面（朝向法兰中心方向）" | `side_mount` |
| 轴承压入卷轴 | "微型深沟球轴承 MR105ZZ，不锈钢轴" | `coaxial` |
| 双卷轴并列 | "并列布置，间距30mm（中心距）" | `lateral_array` |
| 配重块在端部 | "安装于模块顶部（远离清洁窗口端）" | `extremity` |

**5 种定位模式**：

```python
PLACEMENT_MODES = {
    "axial_stack":    # → 链式串联堆叠（§4.1 已处理）
    "radial_extend":  # 零件从父件沿 XY 方向向外延伸
    "side_mount":     # 零件安装在父件的侧面
    "coaxial":        # 零件与父件孔/轴共轴
    "lateral_array":  # 多个零件在 XY 平面内并排
}
```

#### 4.6.1 提取策略

在 `extract_part_placements()` 中，对不在 → 链中的零件，
扫描其所属总成章节的叙述文本，按关键词分类：

```python
# 径向外伸
re.search(r'(沿.{0,4}径向|轴线与悬臂共线).{0,6}(向外|外伸|延伸)', text)
→ mode = "radial_extend"

# 侧壁安装
re.search(r'(安装于|位于).{0,4}(侧壁|侧面|外侧)', text)
→ mode = "side_mount"

# 共轴/压入
re.search(r'(压入|嵌入|过盈配合)', text)
→ mode = "coaxial"

# 并列排布
m = re.search(r'(并列|并排).{0,6}间距\s*(\d+)\s*mm', text)
→ mode = "lateral_array", pitch = float(m.group(2))

# 端部安装
re.search(r'(安装于|位于).{0,4}(顶部|底部|末端|端部)', text)
→ mode = "extremity"
```

**输出 schema**（与串联链 schema 并列，统一存入 `placements` 列表）：
```python
{
  "part_no": "GIS-EE-002-02",     # 储液罐
  "assembly": "GIS-EE-002",
  "mode": "radial_extend",
  "params": {
    "direction": "radial_outward",  # 沿悬臂径向向外
    "rotation": {"axis": (1,0,0), "angle": 90},  # 轴从Z转到XY
  },
  "source": "text:§4.1.2",
  "confidence": "medium",
}
```

**XY 偏移推算规则**（在 `infer_part_offsets()` 中）：

| 模式 | 推算公式 | 所需数据 |
|------|---------|---------|
| `radial_extend` | `offset_x = 父件宽/2 + 本件半径` | 父件包络(§6.4) + 本件包络(§6.4) |
| `side_mount` | `offset_x = 父件宽/2 + 本件直径/2` | 同上 |
| `coaxial` | `offset_xy = 父件孔心坐标` | 父件几何（理想为从3D查询；近似为父件中心） |
| `lateral_array` | `offset_x = ±pitch/2` | 文本中提取的间距 |
| `extremity` | `offset_z = 父件底面（或顶面）` | 父件Z + 父件高度 |

> **置信度**：由于 XY 偏移通常从几何关系推算（非源文档显式给出），
> 非轴向定位模式的默认置信度为 `medium`，审查报告中标记为"需用户确认"。

**对下游的影响**：

- §6.3 零件级定位表增加 `模式` 和 `XY偏移` 列：
  ```
  | 序 | 料号 | 零件名 | 模式 | 底面Z | XY偏移 | 旋转 | 来源 | 置信度 |
  | 5 | GIS-EE-002-02 | 储液罐 | radial_extend | 0 | X=+49 | RX90° | text | medium |
  ```
- `gen_assembly.py` 消费时根据 `模式` 决定先 rotate 还是先 translate
- 审查器 B13（Z偏移碰撞）扩展为包含 XY 偏移的**3D 包络碰撞检测**

---

## 五、默认值填充与推算逻辑（`cad_spec_defaults.py`）

### 5.1 新增：`compute_serial_offsets()` — 从串联链计算 Z 偏移

```
输入：extract_part_placements() 返回的 axial_stack 链
      + part_envelopes（§4.2 提取的）
      + connections（§4.4 提取的，含 axial_gap）
输出：每个链节点的底面偏移（局部坐标，安装面=原点）

算法（方向参数化，适用于 -Z/+Z/+X 等任意堆叠方向）：
  d = chain.direction              # 如 (0,0,-1) 或 (0,0,+1) 或 (1,0,0)
  sign = d[2] if d[2]!=0 else (d[0] if d[0]!=0 else d[1])  # 主轴符号
  cursor = 0.0                     # 安装面位置（局部坐标原点）
  
  for i, node in enumerate(chain.chain):
      h = node.dims.h（优先用链中尺寸，否则从 part_envelopes 查找）
      
      # 查找与前一零件之间的 axial_gap
      gap = 0.0
      if i > 0:
          conn = find_connection(chain.chain[i-1], node, connections)
          if conn and conn.get("axial_gap"):
              gap = conn["axial_gap"]
      
      cursor += sign * gap            # 沿堆叠方向跳过间隙
      if sign < 0:
          bottom = cursor - h         # 向下：底面 = cursor - h
      else:
          bottom = cursor             # 向上/向右：底面 = cursor
      
      # 转为 translate 参数（沿主轴方向）
      offset = (d[0]*abs(bottom), d[1]*abs(bottom), d[2]*abs(bottom))
      result[node.part_no] = {
          "offset": offset,           # ← 直接对应 translate 参数
          "source": "serial_chain",
          "confidence": "high"
      }
      cursor = bottom if sign < 0 else (cursor + h)  # 推进到下一零件起始面
```

> **方向参数化**：算法不假设 -Z 方向。堆叠方向从 chain.direction 获取，
> 可处理向下悬挂 `(0,0,-1)`、向上堆叠 `(0,0,+1)`、水平延伸 `(1,0,0)` 等场景。

> **与 §3.0.2 一致**：z 值 = translate 参数 = 零件底面位置。
> gen_assembly 消费时直接使用，不做 ±h/2 调整。
> **与 §4.4 衔接**：axial_gap 从连接矩阵中查找，参与累积偏移计算。

### 5.2 新增：`infer_part_offsets()` — 残余零件偏移推算

对于未被串联链和非轴向模式覆盖的零件：

```
推算优先级：
1. 连接关系推算 — 从连接矩阵找到已定位的父零件 + 子零件高度
   → 子零件 Z = 父零件底面Z - 子零件高度（沿堆叠方向）
   → confidence = "medium"

2. 类别启发式 — 按零件类别推断定位模式：
   → confidence = "low"

3. 残余堆叠（现有 gen_assembly 行为，保留为最后手段）
   → confidence = "stacked"
```

**类别启发式的默认规则**（可被 §6.2 axis_dir 覆盖）：

| 零件类别 | 默认模式 | 默认方向 | 适用前提 |
|---------|---------|---------|---------|
| motor/reducer | axial_stack | 与主堆叠方向相反（如主向-Z则motor在+Z） | 源文档未指定方向时 |
| sensor | axial_stack | 堆叠末端 | 通用 |
| connector | side_mount | 父件侧面 | 通用 |
| seal/spring | axial_stack | 紧邻配合零件 | 通用 |
| tank | radial_extend 或 axial_stack | 取决于 axis_dir 子句 | 需 axis_dir 判断 |

> **通用性说明**：以上默认规则为经验性设定。不同设备类型（旋转法兰、直线滑台、
> 机械臂末端执行器等）的零件布局差异很大。当 §6.2 axis_dir 有明确描述时，
> 以文档描述为准；默认规则仅在完全无信息时使用。

### 5.3 改进：`check_completeness()` — 增加定位完整性检查项

现有 M01~M07 之后增加：

| 检查ID | 检查内容 | 严重度 | 可自动填充 |
|--------|---------|--------|-----------|
| M08 | BOM 中自制件是否都有包络尺寸 | WARNING | 部分是（从 BOM 材质列推断） |
| M09 | 每个总成是否有 ≥1 条串联链或显式零件级偏移 | WARNING | 部分是（如有串联链则自动计算） |
| M10 | 是否存在排除总成（BOM有但§6.2标记exclude的） | INFO | 是（自动标记） |

---

## 六、审查器改造（`cad_spec_reviewer.py`）

### 6.1 新增审查规则

| 规则ID | 审查项 | 严重度 | 检查逻辑 |
|--------|--------|--------|---------|
| **B10** | 孤儿总成 | CRITICAL | BOM 总成 ∉ §6.2 layers 且 ∉ 排除列表 → 必须有定位或标记排除 |
| **B11** | 零件缺少包络尺寸 | WARNING | §6.4 中缺失条目的自制件 |
| **B12** | 总成缺少零件级定位 | WARNING | §6.3 中总成子表为空或零件覆盖率 < 50% |
| **B13** | 包络碰撞 | WARNING | 同一总成内两个零件的 3D 包络重叠（Z范围 + XY偏移，考虑包络尺寸） |
| **B14** | 排除一致性 | CRITICAL | §6.2 标记 exclude 但 BOM 无对应总成，或反之 |
| **B15** | 串联链-BOM 不匹配 | INFO | 串联链中的零件名无法匹配到 BOM 料号 |
| **B16** | 堆叠总高 vs 包络不一致 | WARNING | §6.3 累积Z总高 vs 总成包络高度差距 > 30% |

### 6.2 改进现有审查规则

| 规则ID | 当前行为 | 改进后 |
|--------|---------|--------|
| **M02** | 仅检查 `assembly.layers` 是否非空 | 增加：检查每行是否有有效 Z/R/θ 数值 |
| **B1** | 悬空零件报 WARNING | 排除 §9 中标记 exclude 的零件后再检查 |
| **B5** | 同 B1 | 区分"真悬空"和"已排除" |

### 6.3 审查报告输出格式

在 DESIGN_REVIEW.md 中增加 **E. 装配定位审查** 区域：

```markdown
## E. 装配定位审查

### 定位覆盖率
- BOM 零件数（不含排除项）: 42
- 显式定位 (§6.2): 6 (14%)
- 串联链推算: 18 (43%)
- 连接推算: 8 (19%)
- 启发式: 6 (14%)
- 残余堆叠: 4 (10%)
- 合计覆盖: 42/42 (100%)

### 需用户确认项
| # | 总成 | 零件 | 当前Z(mm) | 来源 | 建议操作 |
|---|------|------|----------|------|---------|
| P1 | GIS-EE-002 | 齿轮泵 | Z=-32.0 | 启发式 | 请确认安装位置 |
| P2 | GIS-EE-004 | 恒力弹簧 | Z=-188.0 | 残余堆叠 | 可能不准，请提供参考 |
```

---

## 七、规格渲染器改造（`cad_spec_gen.py`）

> 以下所有改动通过修改 `cad_spec_gen.py` 的渲染逻辑实现。
> `cad_spec_gen.py` 是**管线代码**，改动后会自动在 CAD_SPEC.md（中间产物）中
> 产生新的章节。中间产物本身不手动编辑。

### 7.1 扩展 CAD_SPEC §6.2 装配层叠表

增加 `料号` 和 `排除` 列：
```
| 层级 | 零件/模块 | 料号 | 固定/运动 | 连接方式 | 偏移(Z/R/θ) | 轴线方向 | 排除 |
```

### 7.2 新增 CAD_SPEC §6.3 零件级定位表

按总成分组，记录每个零件在**工位局部坐标系**下的偏移（见 §3.0.3）：

```markdown
（以下为 CAD_SPEC.md 中自动渲染的示例输出）

#### GIS-EE-003 AE检测模块

| 序 | 料号 | 零件名 | 模式 | 高度 | 底面Z | XY偏移 | 旋转 | 来源 | 置信度 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | GIS-EE-003-02 | 六轴力传感器 | axial_stack | 20 | -20.0 | — | — | chain | high |
| 2 | GIS-EE-003-03 | 弹簧限力机构 | axial_stack | 18 | -38.0 | — | — | chain(合并) | high |
| 3 | GIS-EE-003-04 | 柔性关节 | axial_stack | 15 | -53.0 | — | — | chain | high |

#### GIS-EE-002 涂抹模块

| 序 | 料号 | 零件名 | 模式 | 高度 | 底面Z | XY偏移 | 旋转 | 来源 | 置信度 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | GIS-EE-002-01 | 壳体 | axial_stack | 55 | -55.0 | — | — | chain | high |
| 2 | GIS-EE-002-02 | 储液罐 | radial_extend | 280 | 0 | X=+49 | RX90° | text | medium |
| 3 | GIS-EE-002-03 | 齿轮泵 | axial_stack | 25 | -80.0 | — | — | infer | low |
```

> **关键约定**：
> - "底面Z"列直接对应 `translate((0, 0, z))` 参数（局部坐标，安装面=Z=0）
> - "XY偏移"列对应 `translate((x, y, 0))`（仅非 axial_stack 模式有值）
> - gen_assembly 按 `模式` 决定操作顺序：axial_stack → 仅 translate；
>   radial_extend → 先 rotate 再 translate；side_mount → 仅 translate(x,y,z)

### 7.3 新增 CAD_SPEC §6.4 零件包络尺寸表

```markdown
（以下为 CAD_SPEC.md 中自动渲染的示例输出）

| 料号 | 零件名 | 类型 | 尺寸(mm) | 来源 |
|---|---|---|---|---|
| GIS-EE-001-01 | 法兰本体 | disc | Φ90×25 | params |
| GIS-EE-002-02 | 储液罐 | cylinder | Φ38×280 | BOM |
```

### 7.4 新增 CAD_SPEC §9 装配约束

```markdown
（以下为 CAD_SPEC.md 中自动渲染的示例输出）

### 9.1 装配排除
| 料号 | 名称 | 原因 | 来源 |
|---|---|---|---|
| GIS-EE-006 | 信号调理模块 | J3-J4连杆安装，不在本装配体内 | N5 |

### 9.2 方向约束
| 约束ID | 目标零件 | 规则 | 说明 |
|---|---|---|---|
| N2 | 电机+减速器 | only_positive_z | 仅在+Z侧(臂侧) |
| N9 | 弹簧限力机构 | axis_perpendicular_to_flange | 轴线⊥法兰面 |
| N10 | 工位模块(全部) | hang_negative_z | 沿-Z悬挂，NEVER水平 |
```

---

## 八、代码生成器改造（`codegen/gen_assembly.py`）

> `gen_assembly.py` 是管线代码（Phase 2），它**读取** CAD_SPEC.md（Phase 1 的
> 输出/中间产物）作为输入，**生成** assembly.py（Phase 2 的输出/中间产物）。
> 以下改动均针对 `gen_assembly.py` 本身的解析和生成逻辑。

### 8.1 消费 CAD_SPEC §6.3 零件级定位表

新增 `_parse_part_positions(spec_path)` 函数，从 CAD_SPEC.md §6.3 读取
每个零件的结构化偏移（含模式、底面Z、XY偏移、旋转）。

**在 `_resolve_child_offsets()` 中的优先级调整**：
```
1. §6.3 中 confidence=high/user_confirmed → 直接使用
2. §6.3 中 confidence=medium → 使用，assembly.py 加注释标记
3. §6.3 中 confidence=low → 使用，assembly.py 加 "# TODO: verify"
4. §6.3 中无此零件 → 回退到现有启发式堆叠（保留为后备）
```

**按定位模式生成代码**：
```python
if mode == "axial_stack":
    # 仅 translate
    part = part.translate((0, 0, bottom_z))
elif mode == "radial_extend":
    # 先 rotate 再 translate
    part = part.rotate((0,0,0), rotation["axis"], rotation["angle"])
    part = part.translate((xy_offset_x, xy_offset_y, bottom_z))
elif mode == "side_mount":
    # 仅 translate（含 XY 偏移）
    part = part.translate((xy_offset_x, xy_offset_y, bottom_z))
elif mode == "coaxial":
    # translate 到父件孔心
    part = part.translate((parent_bore_x, parent_bore_y, bottom_z))
elif mode == "lateral_array":
    # translate 含 pitch 偏移
    part = part.translate((pitch_offset, 0, bottom_z))
elif mode == "extremity":
    # 放置在父件的顶端或底端
    part = part.translate((0, 0, extremity_z))
```

### 8.2 消费 CAD_SPEC §9.1 排除标记

```python
# 在 generate_assembly() 中：
exclusions = parse_assembly_exclusions(spec_path)
excluded_pnos = {e["part_no"] for e in exclusions}
for assy in assemblies:
    if assy["part_no"] in excluded_pnos:
        continue   # 不生成该总成及其子零件的装配代码
```

### 8.3 消费 CAD_SPEC §6.4 包络尺寸表

替代现有 `_parse_dims_text()` 对 BOM 材质列的 ad-hoc 解析：
```python
# 优先从 §6.4 查找
envelope = part_envelopes.get(child["part_no"])
if envelope:
    dims = (envelope["w"], envelope["d"], envelope["h"])
else:
    dims = _parse_dims_text(material_text)  # 回退
```

### 8.4 消费 CAD_SPEC §9.2 方向约束

在 `_axis_dir_to_local_transform()` 中交叉校验：
- 如果 §9.2 有 `orientation_lock`，以其为准
- 如果 §6.2 axis_dir 与 §9.2 矛盾，输出编译期警告

### 8.5 模板改动（`templates/assembly.py.j2`）

轻微改动：为 confidence != "high" 的零件偏移生成注释标记：
```python
# [confidence: medium] Source: connection_inference
p_std_ee_004_08 = p_std_ee_004_08.translate((0.0, 0.0, -99.0))
```

---

## 九、Skill 交互流程改造

### 9.1 Phase 1 审查流程增强

修改 `.claude/commands/cad-spec.md` 和 `cad_pipeline.py`：

```
用户提供设计文档
        │
        ▼
[Phase 1a] 提取 + 推算 + 审查（--review-only）
  ├── 提取 8 类常规数据（不变）
  ├── extract_serial_stacking() ← 新增
  ├── extract_part_envelopes() ← 新增
  ├── compute_serial_offsets() ← 新增：从串联链计算 Z
  ├── infer_part_offsets() ← 新增：残余零件推算
  ├── 运行审查器 A-E 五项（含新增 B10-B16 + E 定位专项）
  └── 生成 DESIGN_REVIEW.json/md
        │
        ▼
[Agent 展示审查结果]
  ├── CRITICAL: 必须修正（孤儿总成、排除不一致）
  ├── WARNING (定位): 低置信度偏移列表
  ├── WARNING (其他): 常规问题
  └── 展示定位覆盖率总览
        │
        ▼
[用户补充/确认] ← 通过 --supplements 传入
  ├── 确认推算值：P1: OK
  ├── 修改推算值：P2: Z=-25.0
  ├── 提供串联链：P3: (文字描述)
  └── 标记无关：P4: skip（不影响建模的纯电气件）
        │
        ▼
[Phase 1b] 合并补充，生成 CAD_SPEC.md
  §6.2 + §6.3 + §6.4 + §9 全部自动生成
```

### 9.2 用户补充方式

审查报告中低置信度的零件，用户可选择：

| 操作 | 用户输入示例 | 效果 |
|------|------------|------|
| 确认 | `P1: OK` | confidence 提升为 `user_confirmed` |
| 修改 Z 值 | `P2: Z=-25.0` | 使用用户提供的值 |
| 提供串联链 | `P3: 泵安装在壳体底部内腔，距底面5mm` | 提取器解析后计算 Z |
| 跳过 | `P4: skip` | 不写入 §6.3（使用残余堆叠） |
| 自动填充 | `--auto-fill` | 所有可推算项自动填充 |

---

## 十、材质库与标准件尺寸数据源

### 10.1 现状

管线中**已有**标准件尺寸库和材质属性数据：

- `cad_spec_defaults.py` 中的 `STD_PART_DIMENSIONS` dict（~40 条记录），
  覆盖 Maxon 电机/减速器、DIN 碟簧、微型轴承、传感器、LEMO/SMA 连接器、泵等
- `lookup_std_part_dims()` 三级查找：精确型号匹配 → 正则尺寸提取 → 类别回退
- `MATERIAL_DENSITY`（13 种）、`MATERIAL_YIELD_STRENGTH`（16 种）、
  `MATERIAL_MAX_TEMP`（14 种）等材质属性 dict

**瓶颈不在几何生成，而在尺寸数据覆盖率**。当 BOM 中出现未收录型号时，
只能回退到粗略的类别默认值（如 `_motor → d=22, l=50`）。

### 10.2 建议方案

#### 方案 A：扩展现有 `STD_PART_DIMENSIONS`（推荐优先实施）

**不新建文件**，直接在现有 `cad_spec_defaults.py` 的 `STD_PART_DIMENSIONS` dict
中补充条目。优先补充以下常见但缺失的零件族：

```python
# 在 STD_PART_DIMENSIONS 中新增：
# --- Linear Bearings ---
"LM6UU":  {"od": 12, "id": 6, "w": 19},
"LM8UU":  {"od": 15, "id": 8, "w": 24},
"LM10UU": {"od": 19, "id": 10, "w": 29},
"LM12UU": {"od": 21, "id": 12, "w": 30},
# --- More Deep Groove Bearings (ISO 15) ---
"6000ZZ":  {"od": 26, "id": 10, "w": 8},
"6001ZZ":  {"od": 28, "id": 12, "w": 8},
"6200ZZ":  {"od": 30, "id": 10, "w": 9},
"6201ZZ":  {"od": 32, "id": 12, "w": 10},
# --- NEMA Stepper Motors ---
"NEMA 17":  {"w": 42.3, "h": 42.3, "l": 48, "shaft_d": 5, "shaft_l": 24},
"NEMA 23":  {"w": 57, "h": 57, "l": 56, "shaft_d": 6.35, "shaft_l": 24},
# --- Common Tanks/Cylinders (GB/T) ---
"_tank_small": {"d": 25, "l": 110},
"_tank_large": {"d": 38, "l": 280},
```

同时扩展材质属性，新增 `color` 字段供 `gen_assembly.py` 自动分配渲染色：

```python
MATERIAL_PROPS = {
    "7075-T6": {"density": 2.81, "color": (0.15, 0.15, 0.15),
                "ra_default": 3.2, "material_type": "al"},
    "PEEK":    {"density": 1.31, "color": (0.85, 0.65, 0.13),
                "ra_default": 3.2, "material_type": "peek"},
    "SUS316L": {"density": 7.98, "color": (0.82, 0.82, 0.85),
                "ra_default": 1.6, "material_type": "steel"},
    "SUS304":  {"density": 7.93, "color": (0.80, 0.80, 0.83),
                "ra_default": 1.6, "material_type": "steel"},
    "FKM":     {"density": 1.80, "color": (0.08, 0.08, 0.08),
                "ra_default": 6.3, "material_type": "rubber"},
    # ...
}
```

**优势**：零新增依赖、零额外文件、与现有查找逻辑完全兼容。
**消费场景**：
- `gen_std_parts.py`：按材质密度 + 包络尺寸估算重量
- `gen_assembly.py`：按材质颜色自动分配渲染色
- `cad_spec_reviewer.py`：材质兼容性检查

#### 方案 B：集成 cq_warehouse CSV 数据（轴承、紧固件精确尺寸）

| 库 | URL | API | 覆盖范围 | 授权 |
|---|---|---|---|---|
| [cq_warehouse](https://github.com/gumyr/cq_warehouse) | Python 包 | CadQuery 原生 | 轴承(deep groove)、紧固件(ISO 4762等)、链轮 | Apache 2.0 |
| [bd_warehouse](https://github.com/gumyr/bd_warehouse) | Python 包 | build123d | 同上 + 法兰、管件、齿轮 | Apache 2.0 |

**关键发现**：cq_warehouse 内部使用 **CSV 文件**存储尺寸数据（OD, ID, W 等），
可以直接读取 CSV 作为尺寸查找表，**无需运行 CadQuery 几何生成**。这意味着：
- 仅提取 CSV → 补充到 `STD_PART_DIMENSIONS`，零运行时开销
- 需要精确几何时（如渲染中的螺栓），可调用参数化模型替代简化圆柱

**集成方式**：
```python
# 在 cad_spec_defaults.py 中：
# pip install cq_warehouse
# 仅用其 CSV 数据查表，不生成几何：
from cq_warehouse.bearing import SingleRowDeepGrooveBallBearing
bearing = SingleRowDeepGrooveBallBearing(size="M8-22-7")  # → OD=22, ID=8, W=7
```

**限制**：不覆盖电机、传感器、泵、连接器、储罐 — 这些仍需方案 A 的手工维护。

#### 方案 C：在线 API（仅作为数据采集渠道）

| 来源 | API 形式 | 实用性 | 说明 |
|------|---------|--------|------|
| [TraceParts](https://developers.traceparts.com/v2/) | REST API | **中** | 有公开 API，可批量查尺寸并缓存到本地 |
| [McMaster-Carr](https://www.mcmaster.com/help/api/) | REST API | **低** | 需客户认证、限速、美标为主 |
| [MatWeb](https://www.matweb.com/) | 无 API | **仅参考** | 10万+材料，手工查阅扩展 MATERIAL_PROPS |
| 3DContentCentral / GrabCAD / CADENAS | 无公开 API | **不推荐** | 无法程序化查询 |

**结论**：云端 API 不适合作为管线运行时依赖（离线场景、中国标准件覆盖差），
但 TraceParts 可作为**一次性数据采集工具**：查询 → 缓存到 `STD_PART_DIMENSIONS`。

#### 不推荐的方案

| 库/API | 原因 |
|--------|------|
| pymatgen / Materials Project | 计算材料科学领域，不涉及工程合金 |
| OpenBOM | BOM 管理工具，无标准件尺寸数据库 |
| `materials` PyPI 包 | 面向物理材料（铜、水、空气），非工程合金 |
| `mechmat` PyPI 包 | 空框架，需用户自行填充数据 |
| cqparts | 基于 CadQuery 1.x，与当前 2.x 不兼容 |

### 10.3 实施建议

| 阶段 | 内容 | 涉及文件 | 工作量 |
|------|------|---------|--------|
| **立即** | 扩展 `STD_PART_DIMENSIONS` + 新增 `MATERIAL_PROPS` | `cad_spec_defaults.py` | 小 |
| **短期** | 提取 cq_warehouse CSV 数据补充轴承/紧固件尺寸 | `cad_spec_defaults.py` | 中 |
| **中期** | 用 TraceParts 批量采集特定厂商零件尺寸并缓存 | `cad_spec_defaults.py` | 中 |

---

## 十一、数据流与向后兼容

### 11.1 完整数据流

```
源文档 ──extract_part_placements()─→ placements[]（含 axial_stack 链 + 非轴向模式）
       ──extract_part_envelopes()──→ envelopes{}
       ──extract_assembly_pose()───→ assembly{layers[], coord_sys[]}（含 exclude 标记）
       ──extract_connection_matrix()→ connections[]（含 axial_gap/radial_clearance）
       ──extract_render_plan()─────→ constraints[]（含分类后的否定约束）
                │
                ▼
         cad_spec_defaults.py
           ├── compute_serial_offsets(placements, envelopes, connections)
           │     → 串联链 Z 偏移（含 axial_gap）+ 子总成合并
           ├── compute_placement_offsets(placements, envelopes)
           │     → 非轴向模式 XY/旋转偏移
           ├── infer_part_offsets(bom, connections, ...)
           │     → 补充残余零件偏移
           └── check_completeness() → issues[] (含 M08~M10)
                │
                ▼
         data = {
           "assembly": {
             "layers": [...],              # 含 exclude 标记
             "coord_sys": [...],
             "part_offsets": {...},         # ← 新增（全部零件的偏移，含模式/置信度）
           },
           "part_envelopes": {...},         # ← 新增
           "constraints_classified": [...], # ← 新增
           ... (params, bom, fasteners 等不变)
         }
                │
                ▼
         cad_spec_gen.py → render_spec()
           渲染 §6.2(含排除列) + §6.3(零件级，含模式/XY偏移) + §6.4(包络) + §9(约束)
                │
                ▼
         CAD_SPEC.md（中间产物）
                │
                ▼
         codegen/gen_assembly.py
           读取 §6.3(按 mode 决定 rotate/translate 顺序) + §6.4 + §9
```

### 11.2 向后兼容

**原则**：无串联链的旧版源文档，经改造后的管线应产生与当前版本**功能等价**的输出。

| 场景 | 行为 |
|------|------|
| 源文档无 `→` 串联链 | `extract_part_placements()` 的 axial_stack 部分返回空 → `infer_part_offsets()` 走启发式 → 与当前行为相同 |
| 源文档无非轴向描述关键词 | `extract_part_placements()` 的非轴向部分返回空 → 无 XY 偏移 → 与当前行为相同 |
| 源文档无否定约束表 | `extract_render_plan().constraints` 为空 → 无排除/方向约束 → gen_assembly 走现有逻辑 |
| 源文档无零件级参数表 | `extract_part_envelopes()` 仅从 BOM 材质列提取 → 与当前 `_parse_dims_text()` 等价 |
| 连接矩阵无 axial_gap | `compute_serial_offsets()` 中 gap=0 → 紧贴堆叠 → 与当前行为相同 |
| CAD_SPEC.md 无 §6.3 | gen_assembly 的 `_parse_part_positions()` 返回空 → 回退到 `_resolve_child_offsets()` 现有逻辑 |

### 11.3 串联链中子总成件的处理

源文档中某些 BOM 件本身是子总成（如 GIS-EE-003-03 弹簧限力机构总成），
其内部子零件在串联链中作为独立节点出现，但 BOM 中只有一条总成记录：

```
BOM:  GIS-EE-003-03 | 弹簧限力机构总成 | 自制 | 300元

零件级参数表（6个子零件）：
  压缩弹簧 | Φ8×12mm    | SUS304
  导向轴   | Φ4×15mm    | SUS303
  上端板   | Φ12×2mm    | 7075-T6
  下端板   | Φ12×2mm    | 7075-T6
  套筒     | Φ12×14mm   | 7075-T6
  垫片     | Φ8×0.5mm   | SUS304

串联链中出现方式：
  → 弹簧限力上端板(Φ12×2mm)        ← sub_assembly: GIS-EE-003-03
  → 弹簧+导向轴+套筒(Φ12×14mm)    ← sub_assembly: GIS-EE-003-03
  → 弹簧限力下端板(Φ12×2mm)        ← sub_assembly: GIS-EE-003-03
```

**处理规则**：

**(a) 识别**：通过 §4.1 中的 `sub_assembly` 归属标记，连续节点被识别为
同一子总成的内部件。

**(b) 合并**：`compute_serial_offsets()` 将连续的同 `sub_assembly` 节点
合并为一个定位单元：
- 合并后 part_no = `GIS-EE-003-03`
- 合并后总高度 = 2+14+2 = 18mm
- 合并后底面Z = 第一个子节点（上端板）的底面Z

**(c) 回写包络**：合并后的总高度（18mm）写入 §6.4 包络尺寸表，
**覆盖**从 BOM 材质列猜测的不准确值。这确保 gen_parts 生成的
简化几何高度与实际装配一致。

**(d) §6.3 输出**：只出现合并后的一行：
```
| 3 | GIS-EE-003-03 | 弹簧限力机构总成 | 18 | -38.0 | — | chain(合并) | high |
```
内部子零件不在 §6.3 中展开——它们是子总成的实现细节，
3D 装配体中该子总成只表现为一个 18mm 高的整体件。

**(e) 非连续的子总成子零件**：如果子总成的子零件在链中不连续出现
（中间穿插了其他零件），则不执行合并，各节点独立定位，审查器报 WARNING
提示可能的串联链错误。

---

## 十二、实施优先级与依赖关系

```
P0 ─────→ P2（gen_assembly 消费排除标记）
P1a ────→ P2（§6.3/§6.4 渲染需要 P1a 的数据）
P1b ────→ P2（envelopes 数据供 §6.4 渲染）
P0+P1+P2 → P3（用户交互基于 P2 的审查报告）
P3 ─────→ P4（标准件库扩展独立于主流程）
```

| 优先级 | 改动 | 涉及文件 | 依赖 | 效果 |
|--------|------|---------|------|------|
| **P0** | §6.2 增加排除列 + gen_assembly 跳过排除总成 | extractors, gen, gen_assembly | 无 | EE-006 悬浮问题立即消除 |
| **P1a** | `extract_part_placements()`（串联链 + 非轴向模式提取） + `compute_serial_offsets()` + 子总成合并 | extractors, defaults | 无 | 工位内零件定位从猜测→链式推算 |
| **P1b** | `extract_part_envelopes()` + 本地标准件库扩展 | extractors, defaults | 无 | 零件尺寸覆盖率 ~20% → ~70% |
| **P2** | §6.3/§6.4/§9 渲染 + gen_assembly 消费（含按 mode 生成代码） | gen, gen_assembly | P0, P1a, P1b | 端到端打通：结构化数据 → 代码 |
| **P2** | B10~B16 审查规则 + E区域报告 | reviewer | P1a, P1b | 定位完整性审查 |
| **P2** | `axial_gap`/`radial_clearance` 连接矩阵增强 | extractors | P1a | 配合距离参与 Z 计算 |
| **P3** | 用户交互引导（定位确认流程） | pipeline, skill | P2 | 引导用户补全低置信度数据 |
| **P3** | 否定约束分类 + 方向约束校验 | extractors, reviewer, gen_assembly | P0 | 自动校验方向/排除约束 |
| **P4** | cq_warehouse 集成 + TraceParts 缓存 | defaults | 无 | 标准件尺寸精度提升 |

> **P0/P1a/P1b 可并行实施**，各自独立。P2 是集成点，依赖 P0+P1a+P1b 全部完成。

---

## 十三、预期效果

| 指标 | 当前 | P0 | P1+P2 | P3 | P4 |
|------|------|-----|-------|-----|-----|
| 有定位的零件占比 | 12% | 12% | ~80% | ~95% | ~95% |
| EE-006 悬浮 | 存在 | 消除 | 消除 | 消除 | 消除 |
| 轴向零件间距准确度 | 猜测 | 猜测 | 链式推算 | 用户确认 | 用户确认 |
| 非轴向零件(储罐/侧装件)定位 | 无 | 无 | 模式识别+XY推算 | +用户确认 | +用户确认 |
| 子总成包络准确度 | 材质列猜测 | 材质列猜测 | 串联链合并 | 串联链合并 | 串联链合并 |
| 标准件尺寸准确度 | ~20% | ~20% | ~70% | ~70% | ~90% |
| 审查能发现的定位问题 | 0种 | 1种 | 7种 | 7种+交互 | 7种+交互 |
| 定位来源可追溯 | 不可 | 部分 | 全部标记 | 全部+签收 | 全部+签收 |

---

## 十四、验证方法

### 14.1 功能验证（以 GISBOT 末端执行机构为例）

1. **P0 验证**：重新运行管线，确认排除模块不出现在 assembly.py 中
2. **P1+P2 验证**：比对 §6.3 自动生成的 Z 偏移与源文档串联图的手算值
3. **P3 验证**：模拟用户补充流程，确认低置信度项可被确认/修改
4. **渲染验证**：重新生成 STEP → Blender 渲染，目视确认零件不再分离

### 14.2 向后兼容验证

对无串联链的已有子系统（如 lifting_platform）运行改造后的管线，确认输出不变。

### 14.3 通用性验证

使用以下差异化场景构造测试用例，确认管线不依赖特定子系统的零件类型/布局：

| 场景 | 差异点 | 验证内容 |
|------|--------|---------|
| 直线滑台 | 无旋转法兰，零件沿单轴排列 | axis_dir 全为(0,0,+1)，无 R/θ 坐标 |
| 多自由度夹爪 | 多层嵌套总成，平行连杆 | 子总成合并、lateral_array 模式 |
| 纯外购件装配 | 无自制件、无串联链 | 全部走 infer_part_offsets() + 标准件库查找 |
| 英文设计文档 | 无中文关键词 | 正则关键词匹配回退到零结果，全走启发式（退化优雅） |
| 极简 BOM（<10件） | 无子总成、无否定约束 | 所有新增功能返回空→行为等同改造前 |

---

## 附录：多角色审查纪要

> 2026-04-08 第一轮审查

| # | 审查角色 | 问题 | 处置 |
|---|---------|------|------|
| R1 | 程序员 | §6 文档子节编号与 CAD_SPEC.md 章节号混淆 | **已修复**：文档用大节号(七/八)，引用 CAD_SPEC 时统一加"CAD_SPEC"前缀 |
| R2 | 程序员 | `cad_pipeline.py` 未列入改动文件清单 | **已修复**：§2.1 补充 |
| R3 | 程序员 | `bom_parser.py` 列入但无改动细节 | **已修复**：移出文件清单，§4.2 明确由 `extract_part_envelopes()` 独立处理 |
| R4 | 架构师 | `assembly.layers` 增加 exclude 后所有消费者需过滤 | **已修复**：§4.3 列出 4 个受影响的消费者 |
| R5 | 架构师 | defaults→gen 数据流路径不清晰 | **已修复**：新增 §11.1 完整数据流图 |
| R6 | 架构师 | 缺少向后兼容说明 | **已修复**：新增 §11.2 退化行为表 |
| R7 | 3D建模 | 零件原点(底面Z=0) vs translate(中心位置)不一致 | **已修复**：新增 §3 坐标约定，§7.2 明确"底面Z"列含义，§5.1 算法改为底面Z |
| R8 | 3D建模 | §6.3 的 Z 是全局还是局部坐标？ | **已修复**：§3.0.3 明确——§6.3 为工位局部坐标，`_station_transform()` 转全局 |
| R9 | 3D建模 | rotation `"rx90"` 字符串不规范 | **已修复**：改为 `{"axis":(1,0,0), "angle":90}` 与 CadQuery 对应 |
| R10 | 机械设计 | mating_distance 未区分接触/间隙/过盈 | **已修复**（R2）：拆分为 `axial_gap`（影响Z计算）+ `radial_clearance`（仅记录），§4.4 详述消费规则 |
| R11 | 装配人员 | 串联链为线性模型，不支持径向装配 | **已修复**（R2）：新增 §4.6 定义 5 种定位模式（radial_extend/side_mount/coaxial/lateral_array/extremity），含关键词提取 + XY偏移推算 |
| R12 | 装配人员 | 子总成件在链中的处理 | **已修复**（R2）：§4.1 新增 `sub_assembly` 归属标记 + §11.3 合并规则（连续节点→合并为单元→回写包络高度） |

> 2026-04-08 第三轮审查（一致性 + 通用性）

| # | 审查角色 | 问题 | 处置 |
|---|---------|------|------|
| C1 | 程序员 | §4.6 引入 `extract_part_placements()` 但其余章节仍引用旧名 | **已修复**：统一为 `extract_part_placements()`，§4.1 改为该函数的子节 |
| C2 | 架构师 | §11.1 数据流不含 placements 和 axial_gap | **已修复**：数据流图全面更新 |
| C3 | 3D建模 | §7.2 表格式缺 mode/XY 列 | **已修复**：新增模式、XY偏移列，含两个总成的完整示例 |
| C4 | 程序员 | §5.1 算法未引用 axial_gap | **已修复**：算法中加入 connection 查找和 gap 消费 |
| C5 | 架构师 | §8 未说明如何按 placement mode 生成代码 | **已修复**：§8.1 新增 5 种模式的代码生成伪码 |
| C6 | 审查器 | B13 仍说"Z范围重叠"而非 3D 碰撞 | **已修复**：改为"3D 包络重叠" |
| C7 | 程序员 | §10 子节编号与 §9 冲突 | **已修复**：改为 10.1/10.2/10.3 |
| G1 | 通用性 | §3.0.4 "向-Z悬挂"是 GISBOT 专有 | **已修复**：改为"由 §6.2 axis_dir 决定，默认(0,0,-1)" |
| G2 | 通用性 | §5.2 类别→方向映射为特定设备假设 | **已修复**：改为可覆盖的默认表 + 通用性说明 |
| G3 | 通用性 | 正则关键词仅中文 | **已修复**：§4 开头增加语言假设说明 + 扩展建议 |
| G4 | 通用性 | §14 验证仅 GISBOT | **已修复**：新增 §14.3 通用性验证场景表（5种差异化测试用例） |

> 2026-04-08 第四轮审查（执行顺序 + 逻辑一致性）

| # | 类型 | 问题 | 处置 |
|---|------|------|------|
| L1 | 命名残留 | §12 仍引用旧名 `extract_serial_stacking()` | **已修复**：改为 `extract_part_placements()` |
| L2 | 算法缺陷 | §5.1 算法硬编码向下堆叠，不支持其他方向 | **已修复**：改为方向参数化算法，用 chain.direction 驱动 |
| L3 | 数值矛盾 | §11.3(d) 示例 `Z=-40.0` 与 §7.2 的 `-38.0` 不一致 | **已修复**：统一为 -38.0（= -20 - 18） |
| L4 | 模式遗漏 | §8.1 代码伪码缺 extremity 模式 | **已修复**：补充 extremity 分支 |
| L5 | 约定冲突 | 底面Z(新) vs center(旧) 同一总成内可能混用 | **已修复**：§3.0.2 增加切换规则——同一总成内全部用同一约定，不混用 |
| L6 | 依赖不清 | §12 P1/P2 依赖关系不明确 | **已修复**：增加依赖关系图 + 表中增加"依赖"列，明确 P0/P1a/P1b 可并行、P2 是集成点 |
