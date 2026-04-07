# 自动标注与通用性修复方案

> 版本: 1.1 | 日期: 2026-04-07 | 状态: **v2.3.0 已实施**
> 相关实施文档: `2d_drawing_fix_plan.md`（教授审图意见修复方案，已完成）
>
> 本文档记录三轮审查后的完整修改方案。目标：
> 1. 修复自动生成图纸无 GB/T 标注的根因
> 2. 消除管道中所有设备专属硬编码，保证通用性
> 3. 保证标注位置合理、清晰可读、字体合规

---

## 目录

1. [问题诊断](#1-问题诊断)
2. [数据管道断裂分析](#2-数据管道断裂分析)
3. [通用性审计](#3-通用性审计)
4. [标注放置与可读性设计](#4-标注放置与可读性设计)
5. [修改清单](#5-修改清单)
6. [详细设计](#6-详细设计)
7. [实施顺序](#7-实施顺序)
8. [验证矩阵](#8-验证矩阵)
9. [引用标准](#9-引用标准)

---

## 1. 问题诊断

### 1.1 现象

自动生成的 2D 工程图（如 `EE-006-01_壳体_含散热鳍片.png`）三视图只有空白矩形轮廓，
缺失所有 GB/T 标注内容：无尺寸标注、无形位公差、无表面粗糙度、无中心线。
标题栏和技术要求区正常。

### 1.2 根因（两层）

**根因 1 — `auto_three_view()` 只投影几何轮廓，零标注**

`cq_to_dxf.py:224` 的 `auto_three_view()` 使用 OCC HLR 做正交投影，
仅产出 OUTLINE/HIDDEN 两个图层的几何边线，不调用任何 `drawing.py` 中的标注函数。

**根因 2 — Jinja2 模板无标注生成步骤**

`templates/part_module.py.j2:99` 生成的 `draw_*_sheet()` 函数仅：

```python
auto_three_view(solid, sheet)   # 只投影轮廓
return sheet.save(output_dir)   # 直接保存，中间无标注
```

对比手工绘图文件（如 `cad/end_effector/draw_flange.py`）有数百行标注代码，
手动调用 `add_linear_dim()`、`add_diameter_dim()`、`add_gdt_frame()`、`add_surface_symbol()` 等。
自动生成路径完全缺失这些调用。

### 1.3 GB/T 合规性缺口

| 标准 | 要求 | 当前状态 | 根因 |
|------|------|----------|------|
| GB/T 4458.4 | 外形尺寸标注 | **缺失** | auto_three_view 无标注步骤 |
| GB/T 4458.4 | 孔/圆直径标注 | **缺失** | 同上 |
| GB/T 4458.4 | 公差文本 (±X) | **缺失** | §2.1 数据未流入绘图管道 |
| GB/T 4458.1 | 中心线/对称线 | **缺失** | 无对称性/圆心检测 |
| GB/T 131-2006 | 个别面粗糙度 | **缺失** | §2.3 数据未流入绘图管道 |
| GB/T 131-2006 | 默认粗糙度符号 | ⚠️ 硬编码 "al" | material_type 未从 material 字段派生 |
| GB/T 1182-2018 | 形位公差框 | **缺失** | §2.2 数据未流入绘图管道 |
| GB/T 1804-m | 技术要求选取 | ⚠️ 硬编码 "al" | 同上 material_type |
| GB/T 10609.1 | 标题栏 | ✅ 正常 | — |
| GB/T 10609.1 | 图框 | ✅ 正常 | — |
| GB/T 14692-2008 | 投影符号 | ✅ 正常 | — |
| GB/T 14691-1993 | 仿宋字体 | ✅ 正常 | — |

---

## 2. 数据管道断裂分析

### 2.1 当前数据流（存在断裂）

```
CAD_SPEC.md
  §1 全局参数表 ──→ gen_params.py ──→ params.py              ✅ 已通
  §2.1 尺寸公差 ──→ extract_tolerances() ──→ data dict       ✅ 已提取
  §2.2 形位公差 ──→ extract_tolerances() ──→ data dict       ✅ 已提取
  §2.3 表面处理 ──→ extract_tolerances() ──→ data dict       ✅ 已提取
                                               │
                                    reviewer + apply_auto_fill()
                                               │
                                    CAD_SPEC.md 补全 / DESIGN_REVIEW.json
                                               │
                                    ──── 断裂 ──── (codegen 不读 §2 数据)
                                               │
  §5 BOM ──→ gen_parts.py ──→ template ──→ 生成代码中无标注   ❌ 断裂
```

核心断裂点：`gen_parts.py` 只读 §5 BOM，不读 §2 公差/表面数据，
也不消费 `apply_auto_fill()` 的补全结果。

### 2.2 修复后的数据流

```
                          ┌─────────────────────────────┐
                          │      CAD_SPEC.md            │
                          │  (Single Source of Truth)    │
                          └─────┬───┬───┬───┬───┬───────┘
                                │   │   │   │   │
          ┌─────────────────────┘   │   │   │   └──────────────────────┐
          ▼                         ▼   │   ▼                          ▼
    §标题 项目名/子系统名       §1 参数  │  §5 BOM                  §2 公差/表面
          │                     │       │    │                         │
          │              gen_params.py  │    │                         │
          │                     │       │    │                         │
          │                  params.py  │    │                         │
          │                             │    │                         │
          │              ┌──────────────┘    │                         │
          │              ▼                   ▼                         │
          │         cad_spec_gen.py ───→ reviewer ──→ apply_auto_fill  │
          │              │                   │           (补全 Ra/力矩) │
          │              │                   ▼                         │
          │              │            DESIGN_REVIEW.json               │
          │              │              (诊断用, 不入 codegen)          │
          │              │                                             │
          └──────┐       │       ┌─────────────────────────────────────┘
                 ▼       ▼       ▼
              gen_parts.py（增强版）
              ├─ 读 §5 BOM → part_no, material, name_cn
              ├─ 读 §标题 → project_name, subsystem_name
              ├─ 读 §2.1 → dim_tolerances (按零件过滤)
              ├─ 读 §2.2 → gdt (按零件过滤)
              ├─ 读 §2.3 → surfaces (按零件过滤)
              └─ classify_material_type(material) → material_type
                           │
                           ▼
                   part_module.py.j2
                           │
                    ┌──────┴──────┐
                    ▼             ▼
            make_xxx()    draw_xxx_sheet()
            (3D 几何)      ├─ ThreeViewSheet(project_name=..., ...)
                           ├─ auto_three_view(solid, sheet)
                           ├─ auto_annotate(solid, sheet, meta)
                           └─ sheet.save(material_type=...)
                                     │
                              ┌──────┴──────┐
                              ▼             ▼
                          .dxf 文件     .png 文件
```

### 2.3 一致性校验点

| 校验 | 位置 | 方法 |
|------|------|------|
| §2.1 param 名与 §1 参数名一致 | reviewer 新增审查项 | dim_tol.name ∈ param_names |
| material_type 派生一致 | `classify_material_type()` 统一函数 | `MATERIAL_TYPE_KEYWORDS` 驱动 |
| 技术要求与 material_type 一致 | `add_technical_notes(material_type=)` | 已有机制，需传入正确值 |
| 默认 Ra 与 material_type 一致 | `add_default_roughness(ra=)` | 已有机制，需传入正确值 |
| dim_tol.label 与实际尺寸值一致 | auto_annotate 运行时 | nominal 与 bbox 测量值交叉校验 |

---

## 3. 通用性审计

### 3.1 CRITICAL — 设备名称硬编码

| 文件 : 行号 | 硬编码内容 | 影响 |
|---|---|---|
| `drawing.py:963` | `"GISBOT 双模态GIS局放检测机器人 — 末端执行器"` | 所有项目的标题栏都显示 GISBOT |
| `drawing.py:1116` | `"GISBOT 末端执行器"` | legacy 函数同上 |
| `draw_three_view.py:43` | `designer: str = "GISBOT"` | 设计栏默认填 GISBOT |

**修复**：`add_gb_title_block()` 新增 `project_name`、`subsystem_name` 参数，
由 `ThreeViewSheet` 传入，来源是 CAD_SPEC.md 标题行。

### 3.2 CRITICAL — 零件编号前缀硬编码

| 文件 : 行号 | 硬编码 | 影响 |
|---|---|---|
| `draw_three_view.py:240` | `part_no.replace('GIS-', '')` | 非 GIS- 前缀的编号不能正确生成文件名 |
| `codegen/gen_parts.py:36` | `re.sub(r"^GIS-", "", part_no)` | 同上 |
| `codegen/gen_build.py:105,152` | `re.sub(r"^GIS-\w+-", "", part_no)` | 同上 |

**修复**：提取通用函数 `strip_part_prefix(part_no)` — 取第一个 `-` 之后的内容，不绑定 "GIS"。

### 3.3 CRITICAL — `_slug()` 硬编码中文→英文映射

`draw_three_view.py:247-266` 有 11 个 GISBOT 专属零件名映射
（法兰本体→flange, PEEK绝缘环→peek_ring …）。其他设备的零件名不在此表中。

**修复**：删除硬编码映射表，改为通用方案：
- 优先用 pypinyin 音译（如果可用）
- fallback：保留 ASCII 字符，替换其他为 `_`
- 截断至 40 字符避免过长

### 3.4 CRITICAL — 默认 material_type fallback 到 "al"

| 位置 | 问题 |
|---|---|
| `drawing.py:834` | `material_type: str = "al"` 默认铝 |
| `drawing.py:847` | `_TECH_NOTES.get(material_type, TECH_NOTES_AL)` fallback 铝 |
| `draw_three_view.py:127` | `save(material_type="al")` 默认铝 |

**修复**：删除默认值，调用方必须显式传入。template 中从 BOM material 通过
`classify_material_type()` 派生。`classify_material_type()` 无匹配时返回 `None`，
调用方应处理 `None`（报 WARNING 并使用通用技术要求）。

### 3.5 CRITICAL — reviewer 中的设备专属检查

| 位置 | 内容 |
|---|---|
| `cad_spec_reviewer.py:128-131` | 硬编码 4 工位 (S1_~S4_) |
| `cad_spec_reviewer.py:254-271` | PEEK/法兰外径干涉检查 |
| `cad_spec_reviewer.py:274-299` | 4 工位包络干涉 |
| `cad_spec_extractors.py:476` | 跳过 GIS-EE-006 |

**修复**：
- 工位数：从 params 中动态检测 `S\d+_` pattern
- PEEK/法兰检查：移至可选配置或删除
- GIS-EE-006 硬编码：删除

### 3.6 WARNING — 其他硬编码

| 文件 : 行号 | 硬编码 | 修复方式 |
|---|---|---|
| `codegen/gen_parts.py:116-117` | `mount_bolt_pcd=28.0, mount_bolt_num=4` | 删除，不生成安装孔代码 |
| `codegen/gen_parts.py:40-62` | `_guess_envelope()` 硬编码默认值 | 从 BOM material 字段解析尺寸 |
| `codegen/gen_build.py:170` | `"[标准件]"` 中文标签 | 保留（是 UI 显示文本非数据） |
| `drawing.py:147` | `simfang.ttf` 字体 | GB/T 14691 规定仿宋，保留（标准常量非硬编码） |
| `cad_pipeline.py:56` | `"gisbot.json"` 配置文件名 | 参数化或改为通用名 `pipeline_config.json` |

### 3.7 不可硬编码元素清单

| 元素 | 数据源 | 错误做法 | 正确做法 |
|---|---|---|---|
| 项目名 | CAD_SPEC.md 标题行 | 写死 "GISBOT" | 解析标题传入 |
| 子系统名 | CAD_SPEC.md 标题行 | 写死 "末端执行器" | 解析标题传入 |
| 零件编号前缀 | BOM part_no 首段 | `"GIS-"` | 动态提取 |
| material_type | BOM material 字段 | 默认 "al" | `classify_material_type()` |
| 默认 Ra | `SURFACE_RA[material]` 查表 | 写死 3.2 | 查表结果传入 |
| 公差文本 | CAD_SPEC §2.1 dim_tols | 写死 "±0.1" | 解析 `label` 字段 |
| GD&T 内容 | CAD_SPEC §2.2 gdt | 写死符号/值/基准 | 解析各列 |
| 技术要求 | material_type → 预设集 | TECH_NOTES_AL fallback | 必须匹配实际材质 |
| 尺寸值 | 几何 bbox 实测 | 写死 "50" | `get_projected_bbox()` |

可作为常量的（来自 GB/T 标准，不依赖项目）：

| 常量 | 值 | 来源 |
|---|---|---|
| `DIM_TEXT_H` | 3.5 mm | GB/T 14691 标准系列 |
| `DIM_ARROW` | 3.0 mm | GB/T 4457.4 |
| `A3_W × A3_H` | 420 × 297 mm | GB/T 10609.1 |
| `MARGIN_BIND` | 25.0 mm | GB/T 10609.1 |
| `MARGIN_STD` | 10.0 mm | GB/T 10609.1 |
| 图层定义 | `LAYERS` 列表 | GB/T 4457.4 |

---

## 4. 标注放置与可读性设计

### 4.1 问题

手工图中每个标注的位置由工程师精确指定。自动标注不能依赖人工坐标，
需要解决以下问题：

| 问题 | 风险 | GB/T 依据 |
|---|---|---|
| 尺寸线与轮廓重叠 | 不可读 | GB/T 4458.4 §4.2：第一道距轮廓 ≥10mm |
| 多条尺寸线互相重叠 | 不可读 | GB/T 4458.4 §4.2：各道间距 ≥7mm |
| 文字与文字重叠 | 不可读 | GB/T 4458.4 §5.6：文字不得被遮挡 |
| 直径标注引出线交叉 | 混乱 | GB/T 4458.4 §5.3：引出线应避免交叉 |
| 小零件缩放后标注挤成一团 | 不可读 | — 需自适应裁减 |

### 4.2 放置常量（全部来自 GB/T 标准）

```python
# 新增于 drawing.py
DIM_FIRST_OFFSET = 10.0     # 第一道尺寸线距轮廓最小距离 (mm 纸面)  GB/T 4458.4 §4.2
DIM_CHAIN_STEP = 7.0        # 各道尺寸线间距 (mm 纸面)              GB/T 4458.4 §4.2
DIM_TEXT_MARGIN = 1.5        # 文字与其他元素最小间距 (mm 纸面)
CENTERLINE_OVERSHOOT = 3.0   # 中心线超出轮廓的长度 (mm 纸面)       GB/T 4458.1 §4.3
```

这些值来自国标，适用于所有机械图纸，不属于硬编码。

### 4.3 尺寸链递进偏移

```
轮廓边线
  │
  │←── 10mm ──→│  第 1 道尺寸线（距轮廓 ≥10mm）
  │←── 17mm ──→│  第 2 道尺寸线（+7mm）
  │←── 24mm ──→│  第 3 道尺寸线（+7mm）
```

实现：每个视图维护两个 offset 栈（水平方向 + 垂直方向），
新增尺寸线时自动取下一个可用偏移。

```python
def _next_dim_offset(used_offsets: list) -> float:
    """计算下一条尺寸线的偏移量，自动递进。"""
    if not used_offsets:
        return DIM_FIRST_OFFSET
    return max(used_offsets) + DIM_CHAIN_STEP
```

### 4.4 直径标注角度分配

自动检测到的圆，按数量均匀分配引出线角度，避免交叉：

```python
def _allocate_dim_angles(count: int) -> list:
    """为多个圆分配不重叠的引出线角度。"""
    base_angles = [45, 135, -45, -135, 30, 150, -30, -150]
    return [base_angles[i % len(base_angles)] for i in range(count)]
```

### 4.5 文字碰撞检测

维护已放置标注的 bbox 列表，新标注放置前检查是否重叠：

```python
@dataclass
class LabelRect:
    x: float; y: float; w: float; h: float

def _check_collision(new: LabelRect, placed: list, margin: float = 1.0) -> bool:
    """检查新标注是否与已有标注重叠。"""
    for r in placed:
        if (new.x < r.x + r.w + margin and new.x + new.w > r.x - margin and
            new.y < r.y + r.h + margin and new.y + new.h > r.y - margin):
            return True
    return False
```

若碰撞，沿引出线方向平移文字直到不碰撞；超出视图区域则放弃该标注。

### 4.6 小零件自适应裁减

当纸面视图尺寸过小时，按优先级截断标注数量：

```python
DIM_PRIORITY = [
    "overall",      # 外形总尺寸（最高优先）
    "tolerance",    # 有公差的关键尺寸
    "diameter",     # 圆/孔直径
    "feature",      # 一般特征尺寸
]

def _compute_max_dims(paper_bbox_w: float, paper_bbox_h: float) -> int:
    """根据纸面上视图尺寸，计算最多能放多少条尺寸线。
    规则：尺寸区域不超过视图短边的 40%。
    """
    short_side = min(paper_bbox_w, paper_bbox_h)
    dim_zone = short_side * 0.4
    return max(1, int(dim_zone / DIM_CHAIN_STEP))
```

### 4.7 字体大小合规性

| 元素 | 当前字高 | GB/T 14691 标准系列 | 是否需修正 |
|---|---|---|---|
| 尺寸文字 | 3.5 mm (`DIM_TEXT_H`) | 2.5, 3.5, 5, 7, 10, 14 | ✅ 合规 |
| 标题栏标签 | 2.0 mm | — | ✅ 可接受 |
| 标题栏值 | 2.5 mm | 2.5 | ✅ 合规 |
| 视图标签 | 5.0 mm | 5 | ✅ 合规 |
| 技术要求标题 | 3.0 mm | 非标准系列 | ❌ **应改为 3.5** |
| 技术要求正文 | 2.5 mm | 2.5 | ✅ 合规 |
| GD&T 框文字 | 2.0 mm | — | ✅ 框内可接受 |
| Ra 符号文字 | 2.5 mm | 2.5 | ✅ 合规 |

修正：`drawing.py` `add_technical_notes()` 中标题行字高 3.0 → 3.5。

### 4.8 纸面坐标系 vs 模型坐标系

标注的字高、偏移、间距都在**纸面 mm** 中计算（不随 scale 变化）。
几何轮廓的坐标已被 scale 缩放到纸面。`auto_annotate()` 中的关键规则：

```python
# 偏移量是纸面 mm，不乘 scale（因为标注在纸面坐标系绘制）
dim_offset = DIM_FIRST_OFFSET           # 纸面 10mm ✅

# bbox 测量值需要乘 scale 才是纸面尺寸
paper_width = bbox_width * scale        # 纸面宽度

# 视图中心 (ox, oy) 已经是纸面坐标
# 标注起点 = 轮廓边 + 偏移
dim_base_x = ox + paper_width / 2 + dim_offset   # 纸面坐标
```

---

## 5. 修改清单

### 5.1 总览

| # | 文件 | 修改类型 | 通用性 | 标注 | 批次 |
|---|---|---|---|---|---|
| 1 | `cad_spec_defaults.py` | 新增函数 | ✅ | ✅ | 1 |
| 2 | `drawing.py` — `strip_part_prefix()` | 新增函数 | ✅ | — | 1 |
| 3 | `drawing.py` — `_slug()` 通用化 | 重写函数 | ✅ | — | 1 |
| 4 | `drawing.py:963,1116` — 标题栏参数化 | 修改函数签名 | ✅ | — | 2 |
| 5 | `drawing.py:834,847` — 删除 "al" 默认值 | 修改默认值 | ✅ | — | 2 |
| 6 | `drawing.py:852` — 技术要求字高修正 | 修改常量 | — | ✅ | 2 |
| 7 | `drawing.py` — 新增放置引擎 | 新增函数 | — | ✅ | 3 |
| 8 | `draw_three_view.py:43` — designer 默认空 | 修改默认值 | ✅ | — | 2 |
| 9 | `draw_three_view.py:240` — 通用前缀剥离 | 修改函数 | ✅ | — | 1 |
| 10 | `draw_three_view.py:247-266` — 通用 slug | 替换函数 | ✅ | — | 1 |
| 11 | `draw_three_view.py` — 新增构造参数 | 修改类 | ✅ | — | 2 |
| 12 | `draw_three_view.py:127` — save 无默认 material_type | 修改签名 | ✅ | — | 2 |
| 13 | `cq_to_dxf.py` — 新增 `auto_annotate()` | 新增函数 | — | ✅ | 3 |
| 14 | `codegen/gen_parts.py` — 解析 §2 + §标题 | 增强函数 | ✅ | ✅ | 3 |
| 15 | `codegen/gen_parts.py:36` — 通用前缀剥离 | 修改函数 | ✅ | — | 1 |
| 16 | `codegen/gen_parts.py:116-117` — 删除螺栓硬编码 | 删除 | ✅ | — | 2 |
| 17 | `codegen/gen_build.py:105,152` — 通用前缀 | 修改函数 | ✅ | — | 1 |
| 18 | `templates/part_module.py.j2` — 生成标注调用 | 增强模板 | ✅ | ✅ | 3 |
| 19 | `cad_spec_reviewer.py` — 新增 3 个审查项 | 新增 | — | ✅ | 3 |
| 20 | `cad_spec_reviewer.py:128,254,274` — 动态工位数 | 修改 | ✅ | — | 2 |
| 21 | `cad_spec_extractors.py:476` — 删除 GIS-EE-006 | 删除 | ✅ | — | 2 |
| 22 | `src/cad_spec_gen/data/` 镜像同步 | 同步 | ✅ | ✅ | 3 |

**约束**：不修改 `.claude/commands/`、`.claude/skills/`、任何 skill 定义文件。

### 5.2 审查环节新增审查项

在 `cad_spec_reviewer.py` 的 `review_completeness()` 中新增：

```
D+N: "§2.1 尺寸公差不足"
  — 条件：自制零件数 > 0 且 dim_tols 条目数 < 自制零件数 × 2
  — severity: WARNING
  — auto_fill: 否（公差不能随意补，需设计师确认）

D+N: "尺寸公差参数名无法匹配 params.py"
  — 条件：dim_tols 中 50%+ 的 name 不在 §1 参数表中
  — severity: WARNING
  — auto_fill: 否

D+N: "零件材质无法推断 material_type"
  — 条件：对自制零件调用 classify_material_type() 返回 None
  — severity: WARNING
  — auto_fill: 否（需用户确认材质分类）
```

### 5.3 自动补全环节修改

在 `apply_auto_fill()` 中新增 material_type 派生：

```python
# 在 apply_auto_fill() 中新增:
# --- material_type 派生 ---
bom = data.get("bom")
if bom:
    for assy in bom.get("assemblies", []):
        for part in assy.get("parts", []):
            mat = part.get("material", "")
            if mat and not part.get("material_type"):
                mtype = classify_material_type(mat)
                if mtype:
                    part["material_type"] = mtype
                    changelog.append({
                        "field": f"bom.{part['name']}.material_type",
                        "old": "—", "new": mtype,
                        "source": f"classify_material_type({mat!r})",
                    })
```

---

## 6. 详细设计

### 6.1 `classify_material_type()` — 通用材质分类

位置：`cad_spec_defaults.py` 新增

```python
MATERIAL_TYPE_KEYWORDS = {
    "al":     ["铝", "Al", "7075", "6061", "6063", "2024", "5052",
               "铝合金", "aluminum", "aluminium"],
    "steel":  ["钢", "Steel", "SUS", "不锈钢", "Q235", "45钢",
               "碳钢", "合金钢", "弹簧钢"],
    "peek":   ["PEEK"],
    "nylon":  ["尼龙", "PA66", "PA6", "POM", "塑料", "ABS",
               "PC", "Nylon"],
    "rubber": ["硅橡胶", "FKM", "NBR", "EPDM", "橡胶",
               "Shore", "rubber", "silicone"],
}

def classify_material_type(material: str) -> str | None:
    """从 BOM material 字段推断 material_type。

    遍历 MATERIAL_TYPE_KEYWORDS 查找关键词匹配。
    无匹配时返回 None（不静默 fallback）。

    Returns:
        "al" | "steel" | "peek" | "nylon" | "rubber" | None
    """
    for mtype, keywords in MATERIAL_TYPE_KEYWORDS.items():
        if any(kw.lower() in material.lower() for kw in keywords):
            return mtype
    return None
```

### 6.2 `strip_part_prefix()` — 通用编号前缀剥离

位置：`drawing.py` 新增（同时被 `draw_three_view.py`、`gen_parts.py`、`gen_build.py` 复用）

```python
def strip_part_prefix(part_no: str) -> str:
    """通用前缀剥离：去掉第一段（首个 '-' 之前）。

    GIS-EE-001-01 → EE-001-01
    ACME-PLT-002  → PLT-002
    NOPREFIX      → NOPREFIX (无 '-' 则原样返回)
    """
    idx = part_no.find("-")
    return part_no[idx + 1:] if idx >= 0 else part_no
```

### 6.3 `_slug()` — 通用文件名 slug

位置：`draw_three_view.py` 替换现有 `_slug()`

```python
def _slug(name: str) -> str:
    """通用中英文名→文件名安全字符串。"""
    try:
        from pypinyin import lazy_pinyin
        slug = "_".join(lazy_pinyin(name))
    except ImportError:
        slug = "".join(c if c.isalnum() or c == '_' else '_' for c in name)
    # 去除连续下划线、首尾下划线、截断
    slug = re.sub(r"_+", "_", slug).strip("_").lower()
    return slug[:40] if slug else "unnamed"
```

### 6.4 `auto_annotate()` — 标注引擎

位置：`cq_to_dxf.py` 新增

```python
def auto_annotate(
    solid: cq.Workplane,
    sheet: "ThreeViewSheet",
    annotation_meta: dict = None,
):
    """几何驱动 + Spec 驱动的自动标注引擎。

    分两阶段工作：
    1. 几何驱动（无需 spec 数据）：
       - 外形尺寸：每个视图的 bbox → add_linear_dim (GB/T 4458.4)
       - 圆/圆弧直径：HLR 投影中的 Circle 边 → add_diameter_dim (GB/T 4458.4)
       - 中心线：圆心加十字，bbox 对称轴加细点画线 (GB/T 4458.1)

    2. Spec 驱动（从 annotation_meta 传入，可选）：
       - 公差文本：§2.1 tolerance → 覆盖尺寸文本 (GB/T 4458.4)
       - 形位公差：§2.2 GD&T → add_gdt_frame (GB/T 1182-2018)
       - 个别面粗糙度：§2.3 Ra → add_surface_symbol (GB/T 131-2006)

    annotation_meta 结构（全部来自 CAD_SPEC.md 解析）:
    {
        "dim_tolerances": [
            {"name": str, "nominal": str, "upper": str, "lower": str,
             "fit_code": str, "label": str}
        ],
        "gdt": [
            {"symbol": str, "value": str, "datum": str, "parts": str}
        ],
        "surfaces": [
            {"part": str, "ra": str, "process": str}
        ],
    }

    无 annotation_meta 时仅做几何驱动标注。
    """
```

内部实现要点：

1. **获取布局信息**：从 sheet 获取各视图的 origin (ox, oy) 和 scale
2. **几何分析**：对每个视图调用 `_extract_edges()` 获取投影边，分类为 LINE/CIRCLE/ARC/POLYLINE
3. **外形尺寸**：从所有边计算 bbox → 在主视图标宽和高，俯视图标深度
4. **圆直径**：筛选 CIRCLE 类型边 → 按大小排序 → 分配引出线角度 → add_diameter_dim
5. **中心线**：圆心加十字 → add_centerline_cross；视图 bbox 中心加水平/垂直中心线
6. **公差标注**（需 meta）：匹配 dim_tol.name 与几何尺寸 → 覆盖标注文本
7. **GD&T**（需 meta）：在主视图旁放置形位公差框
8. **表面粗糙度**（需 meta）：在主视图轮廓边放置 Ra 符号
9. **碰撞检测**：维护 `placed_labels` 列表，每次放置前检查
10. **裁减**：超过 `_compute_max_dims()` 限制时按优先级丢弃低优先级标注

### 6.5 `ThreeViewSheet` 构造函数增强

位置：`draw_three_view.py` 修改

```python
class ThreeViewSheet:
    def __init__(self, part_no: str, name: str, material: str,
                 scale: str, weight_g: float, date: str,
                 designer: str = "",            # 不默认 "GISBOT"
                 checker: str = "",
                 project_name: str = "",        # 新增
                 subsystem_name: str = "",      # 新增
                 ):
```

`save()` 方法签名修改：

```python
def save(self, output_dir: str, material_type: str) -> str:
    # material_type 无默认值，调用方必须传入
    ...
    add_gb_title_block(
        msp, ...,
        project_name=self.project_name,
        subsystem_name=self.subsystem_name,
    )
```

### 6.6 `gen_parts.py` 增强

位置：`codegen/gen_parts.py` 修改 `generate_part_files()`

新增功能：
1. 解析 CAD_SPEC.md 标题行 → `project_name`, `subsystem_name`
2. 调用 `extract_tolerances()` → 按零件名过滤 dim_tols/gdt/surfaces
3. 调用 `classify_material_type()` → material_type
4. 传入模板

```python
# 解析 §标题
spec_text = Path(spec_path).read_text(encoding="utf-8")
m_title = re.search(r"# CAD Spec\s*—\s*(.+?)(?:\s*\(|$)", spec_text)
project_name = ""           # 从上层 config 传入或默认空
subsystem_name = m_title.group(1) if m_title else ""

# 解析 §2
from cad_spec_extractors import extract_tolerances
tol_data = extract_tolerances(spec_text.splitlines())

# 为每个零件过滤标注数据
part_tols = [t for t in tol_data["dim_tols"] if _matches_part(t, p)]
part_gdt = [g for g in tol_data["gdt"] if _matches_part(g, p)]
part_surfaces = [s for s in tol_data["surfaces"] if _matches_part(s, p)]
mat_type = classify_material_type(p["material"])

# 传入模板
content = template.render(
    ...existing params...,
    material_type=mat_type or "al",    # None 时 fallback + 报 WARNING
    project_name=project_name,
    subsystem_name=subsystem_name,
    dim_tolerances=part_tols,
    gdt_entries=part_gdt,
    surface_ra=part_surfaces,
    default_ra=SURFACE_RA.get(mat_type, 3.2) if mat_type else 3.2,
)
```

### 6.7 `part_module.py.j2` 模板增强

位置：`templates/part_module.py.j2` 修改 `draw_*_sheet()` 块

```jinja2
{% if has_dxf %}
def draw_{{ func_name }}_sheet(output_dir: str = None) -> str:
    """Generate DXF three-view drawing for {{ part_no }}."""
    from draw_three_view import ThreeViewSheet
    from cq_to_dxf import auto_three_view, auto_annotate
    from datetime import date

    solid = make_{{ func_name }}()
    sheet = ThreeViewSheet(
        part_no="{{ part_no }}",
        name="{{ part_name_cn }}",
        material="{{ material }}",
        scale="1:1",
        weight_g=0,
        date=date.today().isoformat(),
        project_name="{{ project_name }}",
        subsystem_name="{{ subsystem_name }}",
    )
    auto_three_view(solid, sheet)

    # GB/T 标注 — 数据全部来自 CAD_SPEC.md，不硬编码
    auto_annotate(solid, sheet, annotation_meta={
        "dim_tolerances": {{ dim_tolerances | tojson }},
        "gdt": {{ gdt_entries | tojson }},
        "surfaces": {{ surface_ra | tojson }},
    })

    return sheet.save(output_dir, material_type="{{ material_type }}")
{% endif %}
```

### 6.8 `add_gb_title_block()` 参数化

位置：`drawing.py` 修改函数签名

```python
def add_gb_title_block(msp, part_no, name, material, scale, weight_g,
                       designer, checker, date,
                       project_name="",       # 新增
                       subsystem_name="",     # 新增
                       origin=(230.0, 10.0), layer="BORDER"):
    ...
    # Row 3: 项目信息（使用传入值，不硬编码）
    yr3 = y0 + 3 * rh
    if project_name and subsystem_name:
        title_text = f"{project_name} — {subsystem_name}"
    elif project_name:
        title_text = project_name
    elif subsystem_name:
        title_text = subsystem_name
    else:
        title_text = ""
    msp.add_text(title_text, height=3.0,
                 dxfattribs={"layer": "TEXT", "color": 7}
                 ).set_placement((x0 + 2, yr3 + 2))
```

---

## 7. 实施顺序

### 批次 1 — 基础设施（其他修改的依赖项）

| # | 文件 | 修改 |
|---|---|---|
| 1 | `cad_spec_defaults.py` | 新增 `classify_material_type()` + `MATERIAL_TYPE_KEYWORDS` |
| 2 | `drawing.py` | 新增 `strip_part_prefix()` |
| 3 | `draw_three_view.py` | 通用 `_slug()` 替代硬编码映射 |
| 9 | `draw_three_view.py:240` | 使用 `strip_part_prefix()` |
| 15 | `codegen/gen_parts.py:36` | 使用 `strip_part_prefix()` |
| 17 | `codegen/gen_build.py:105,152` | 使用 `strip_part_prefix()` |

### 批次 2 — 通用性修复（消除所有设备专属硬编码）

| # | 文件 | 修改 |
|---|---|---|
| 4 | `drawing.py:963,1116` | 标题栏参数化 project_name |
| 5 | `drawing.py:834,847` | 删除 "al" 默认值 |
| 6 | `drawing.py:852` | 技术要求标题字高 3.0 → 3.5 |
| 8 | `draw_three_view.py:43` | designer 默认空 |
| 11 | `draw_three_view.py` | ThreeViewSheet 新增 project_name/subsystem_name |
| 12 | `draw_three_view.py:127` | save() 无默认 material_type |
| 16 | `codegen/gen_parts.py:116-117` | 删除 mount_bolt 硬编码 |
| 20 | `cad_spec_reviewer.py:128,254,274` | 动态工位数 + 移除设备专属检查 |
| 21 | `cad_spec_extractors.py:476` | 删除 GIS-EE-006 硬编码 |

### 批次 3 — 标注引擎 + 管道打通

| # | 文件 | 修改 |
|---|---|---|
| 7 | `drawing.py` | 新增放置引擎函数 |
| 13 | `cq_to_dxf.py` | 新增 `auto_annotate()` |
| 14 | `codegen/gen_parts.py` | 增强：解析 §2 + §标题 |
| 18 | `templates/part_module.py.j2` | 生成标注调用 |
| 19 | `cad_spec_reviewer.py` | 新增 3 个标注审查项 |
| 22 | `src/cad_spec_gen/data/` 镜像 | 同步全部修改 |

### 批次依赖关系

```
批次 1 (基础设施)
  │
  ▼
批次 2 (通用性修复)  ← 依赖批次 1 的 strip_part_prefix, classify_material_type
  │
  ▼
批次 3 (标注引擎)    ← 依赖批次 2 的 ThreeViewSheet 参数化、material_type 无默认值
```

---

## 8. 验证矩阵

方案实施完成后，逐项验证：

### 8.1 通用性验证

| 测试场景 | 验证点 | 预期结果 |
|---|---|---|
| 新建非 GIS 前缀项目 `ACME-PLT-001` | 编号处理 | 文件名 `PLT-001_xxx.dxf` |
| 材质为 PEEK | material_type | "peek"，技术要求为 PEEK 版 |
| 材质为 "SUS316L不锈钢" | material_type | "steel"，默认 Ra=1.6 |
| 材质为 "碳纤维复合材料" | material_type | `None` → WARNING 报告 |
| 标题栏 | 项目名 | 显示传入的 project_name |
| 文件名 slug | 任意中文名 | pinyin 音译或 ASCII 化 |

### 8.2 标注验证

| 测试场景 | 验证点 | 预期结果 |
|---|---|---|
| §2 完全为空 | 几何标注 | 仍有外形尺寸 + 中心线 |
| §2.1 有公差 | 公差文本 | 尺寸上显示 "90±0.1" |
| §2.2 有 GD&T | 形位公差框 | 视图旁有公差框 |
| §2.3 有 Ra | 表面粗糙度 | 轮廓边有 Ra 符号 |
| 零件很小 (5×5mm) | 标注裁减 | 只标 1 条外形尺寸 |
| 零件很大 (500×300mm) | 标注间距 | 尺寸线间距 ≥7mm 纸面 |
| 多个圆同视图 | 引出线 | 角度不交叉 |
| 标注互相碰撞 | 碰撞检测 | 文字不重叠 |

### 8.3 管道一致性验证

| 测试场景 | 验证点 | 预期结果 |
|---|---|---|
| 修改 §2.1 公差后重新 codegen | 数据流通 | 新标注反映新公差值 |
| apply_auto_fill 补全 Ra 后重新 codegen | 补全传递 | 图纸有补全后的 Ra |
| §2.1 param 名拼写错误 | reviewer 检查 | 报 WARNING "无法匹配" |

---

## 9. 引用标准

| 标准号 | 名称 | 本方案引用 |
|---|---|---|
| GB/T 4457.4-2002 | 图线 | 图层定义、线宽、线型 |
| GB/T 4458.1-2002 | 三视图 | 投影方向、中心线规则 |
| GB/T 4458.4-2003 | 尺寸标注 | 尺寸线间距、公差标注格式、文字位置 |
| GB/T 4458.6-2002 | 剖视图 | 剖切线标注（现有功能） |
| GB/T 4459.1-1995 | 螺纹画法 | 螺纹标注（现有功能） |
| GB/T 10609.1 | 图框/标题栏 | A3 图框尺寸、标题栏布局 |
| GB/T 14691-1993 | 字体 | 仿宋体、字高标准系列 |
| GB/T 14692-2008 | 投影法 | 第一角投影 |
| GB/T 1182-2018 | 形位公差 | 公差框格式 |
| GB/T 131-2006 | 表面粗糙度 | Ra 符号格式、放置规则 |
| GB/T 1804-2000 | 一般公差 | 技术要求引用 |
| GB/T 17450-1998 | 线型 dash/gap | 虚线和点划线图案 |
