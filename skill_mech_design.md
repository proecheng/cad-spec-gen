# skill_mech_design — 参数化机械子系统 CAD 设计知识库

## 概述

`/mechdesign` 用于**手动**精细参数化建模。与 `/cad-codegen`（自动脚手架）互补：
- **推荐工作流**: `/cad-spec` → `/cad-codegen`（自动骨架）→ `/mechdesign`（手动完善几何）
- **完全手动**: `/mechdesign <子系统名>` 从零开始 6 阶段建模

---

## 6 阶段流程

### Phase 1: 参数提取 → params.py + tolerances.py

**输入**: 设计文档（`docs/design/NN-*.md` 或绝对路径如 `D:/jiehuo/docs/NN-*.md`，§X.4 详细设计）
**输出**: `cad/<subsystem>/params.py`（单一数据源）

规则：
- 所有尺寸从设计文档提取，**不凭空编造**
- 参数命名描述性：`FLANGE_R`, `ARM_WIDTH`, `MOTOR_OD`（不用 `L`, `W`, `DIA`）
- 工位参数加前缀：`S1_BODY_W`, `S2_SPRING_OD`, `S3_BRUSH_W`, `S4_BRACKET_H`
- 公差单独到 `tolerances.py`：`FLANGE_R_TOL = (0, -0.05)`
- 单位统一 mm，角度统一度
- 使用 `math.radians()` 转换
- 一个参数只赋值一次，不重复

示例结构：
```python
# params.py — 末端执行器参数（单一数据源）
import math

# ── 法兰 ──
FLANGE_R = 55.0          # 法兰外径 mm (设计文档 §4.4.1)
FLANGE_THICK = 8.0       # 铝法兰厚度 mm
PEEK_THICK = 3.0         # PEEK绝缘环厚度 mm

# ── 工位布局 ──
NUM_STATIONS = 4
STATION_ANGLES = [i * 360 / NUM_STATIONS for i in range(NUM_STATIONS)]
MOUNT_CENTER_R = 40.0    # 安装中心半径 mm
```

### Phase 2: BOM 建模 → bom.py

**输入**: 设计文档 §X.8 BOM 表（从实际设计文档路径读取）
**输出**: `cad/<subsystem>/bom.py`（零件清单 + 成本汇总）

规则：
- 区分自制件/外购件
- 自制件需精确 CadQuery 建模
- 外购件用简化几何（圆柱、方盒）仅供渲染可视化
- 料号格式 `GIS-XX-NNN`（总成）/ `GIS-XX-NNN-NN`（零件）

### Phase 3: 3D 参数化建模 → CadQuery .py + assembly.py

**输入**: params.py + 设计文档几何描述
**输出**: 各零件 `.py` + `assembly.py` → STEP + GLB

关键原则：
- **所有尺寸引用 params.py**，函数体内不出现魔术数字
- `from params import *` 后直接使用变量名
- 每个零件一个 `make_<part>()` 函数，返回 `cq.Workplane` 或 `cq.Assembly`
- assembly.py 使用 `cq.Assembly` 组装所有零件，用 `mates` 约束位置
- 导出 STEP（加工）和 GLB（渲染）两种格式

CadQuery 常用模式：
```python
import cadquery as cq
from params import *

def make_flange():
    return (
        cq.Workplane("XY")
        .circle(FLANGE_R).extrude(FLANGE_THICK)
        .faces(">Z").workplane()
        .circle(BORE_R).cutThruAll()
        # 安装孔
        .faces(">Z").workplane()
        .polarArray(MOUNT_CENTER_R, 0, 360, NUM_STATIONS)
        .circle(MOUNT_HOLE_R).cutThruAll()
    )
```

### Phase 4: 2D 工程图 → GB/T 国标 A3 DXF

**输入**: params.py 参数（直接绘制轮廓，不从 3D 投影）
**输出**: `cad/output/EE-NNN-NN_name.dxf`

GB/T 国标要求：
- **投影法**: GB/T 4458.1 第一角投影法
- **图纸**: A3 (420×297mm)
- **字体**: 仿宋体 FangSong (GB/T 14691)
- **线宽**: d=0.50mm 体系 (GB/T 17450)
- **标注文字**: 3.5mm 纸面高度（不乘 view scale）
- **DXF 格式**: R2013

12 层 DXF 体系：
| 层名 | 颜色 | 用途 |
|------|------|------|
| 0-outline | white | 可见轮廓（粗实线 d） |
| 1-hidden | cyan | 不可见轮廓（虚线 d/2） |
| 2-center | red | 中心线（点划线 d/3） |
| 3-dimension | green | 尺寸标注 |
| 4-section | yellow | 剖面线（45° 细实线） |
| 5-notes | magenta | 技术要求文字 |
| 6-title | white | 标题栏 |
| 7-border | white | 图框 |
| 8-section-line | red | 剖切线 A-A |
| 9-datum | green | 基准三角 |
| 10-thread | cyan | 螺纹标注（细实线 3/4 圈） |
| 11-surface | magenta | 表面粗糙度 |

每张图必须包含：
- 技术要求区（右上角 or 标题栏上方）
- 默认粗糙度符号 Ra
- 基准三角（至少 1 个 A 基准）
- 剖切线（如有内部特征）
- 螺纹标注（如有螺纹孔）
- 材料名用中文国标格式（"铝合金" 非 "Al"）

### Phase 5: 渲染预览 → DXF→PNG

**工具**: `cad/<subsystem>/render_dxf.py`
**输出**: 与 DXF 同名的 .png 文件

```bash
python cad/<subsystem>/render_dxf.py                    # 渲染全部
python cad/<subsystem>/render_dxf.py file1.dxf file2.dxf  # 渲染指定
```

### Phase 6: 一键构建 → build_all.py

**工具**: `cad/<subsystem>/build_all.py`
**输出**: `cad/output/` 下所有 STEP + DXF + GLB

```bash
python cad/<subsystem>/build_all.py               # 构建 STEP + DXF
python cad/<subsystem>/build_all.py --render       # 构建 + Blender 渲染
python cad/<subsystem>/build_all.py --dry-run      # 仅验证导入
# Note: 通过 cad_pipeline.py build 调用时，会自动运行 render_dxf.py 将 DXF 转为 PNG 预览图
```

build_all.py 结构：
- `_STEP_BUILDS` 列表：(label, module, function, filename)
- `_DXF_BUILDS` 列表：(label, module, function)
- `build_all()` 函数依次构建所有零件

---

## 检查点验证

每阶段完成后验证：

| 阶段 | 验证方法 |
|------|----------|
| params.py | 所有参数有设计文档出处，无魔术数字 |
| bom.py | 总数与设计文档 §X.8 BOM 一致 |
| 零件 .py | `make_*()` 返回有效实体，无 TODO 占位 |
| assembly.py | GLB 可在 Blender 中打开查看 |
| DXF | 线宽/字体/层名符合 GB/T，标题栏完整 |
| build_all.py | `--dry-run` 通过，所有模块可导入 |

---

## 三道门控（质量关卡）

管线在三个关键节点设有强制检查，任一失败均会中止后续阶段：

| 门控 | 触发时机 | 检查内容 | 失败处理 |
|------|----------|----------|----------|
| **门控1** DESIGN_REVIEW CRITICAL | SPEC 阶段末 | `cad_spec_reviewer.py` 发现 CRITICAL 级问题 | 打印问题列表，要求用户确认后方可继续 |
| **门控2** TODO 扫描 | CODEGEN 阶段末 | `gen_parts.py` 扫描所有新生成文件中的 `TODO:` 标记 | exit code 2，打印文件名+行号+内容，禁止进入 BUILD |
| **门控3** 方位检查 | BUILD 阶段前 | `orientation_check.py` 断言包围盒主轴与设计文档一致 | exit code 非0，打印轴向偏差，禁止构建；可用 `--skip-orientation` 强制绕过（不推荐）|

### 门控2 详细规则

`gen_parts.py` 生成脚手架后立即扫描所有新文件的 `TODO:` 标记：
- **有未填 TODO** → 打印 WARNING 列表，以 **exit code 2** 退出
- **全部填写** → 正常退出（exit code 0），继续 BUILD

### 门控3 详细规则

`orientation_check.py` 由用户或 codegen 在子系统目录下创建，内容断言构建后模型的包围盒主轴方向：
```python
# 示例: orientation_check.py
assert abs(bb.xmax - bb.xmin - EXPECTED_X) < TOL, f"X 轴尺寸偏差: {bb.xmax-bb.xmin:.1f} vs {EXPECTED_X}"
```
- 文件不存在 → 跳过门控（非强制）
- 文件存在且失败 → BUILD 中止
- `--skip-orientation` 标志可绕过（仅调试用）

---

## 参考实现

`cad/end_effector/` 是完整的参考实现：

```
cad/end_effector/
├── params.py              # ~220 参数
├── tolerances.py          # 公差定义
├── bom.py                 # BOM 清单
├── flange.py              # 法兰 3D
├── station1_applicator.py # 涂覆工位
├── station2_ae.py         # 声发射工位
├── station3_cleaner.py    # 清洁工位
├── station4_uhf.py        # UHF工位
├── drive_assembly.py      # 驱动总成
├── assembly.py            # 总装配 → STEP + GLB
├── drawing.py             # 2D 绘图引擎
├── draw_three_view.py     # 三视图模板
├── draw_flange.py         # 法兰工程图
├── draw_station1.py       # 各工位工程图
├── ...
├── render_config.json     # 渲染配置
├── render_3d.py           # Blender 渲染
├── render_exploded.py     # 爆炸图
├── render_dxf.py          # DXF→PNG
└── build_all.py           # 一键构建
```

---

## 与自动管线的协作

| 场景 | 推荐方式 |
|------|----------|
| 首次建模 | `/cad-spec` → `/cad-codegen` → `/mechdesign` 完善 |
| 已有脚手架 | `/mechdesign <子系统>` 在脚手架基础上完善几何 |
| 仅调参数 | 编辑 `params.py`，重新 `build_all.py` |
| 新增零件 | 手写 `make_*()` 函数，加入 `build_all.py` |
| 仅渲染 | `python cad_pipeline.py render --subsystem <name>` |
| 全自动 | `python cad_pipeline.py full --subsystem <name> --design-doc <doc>` |

---

## 关键约束

1. **params.py 是单一数据源** — 所有尺寸从此文件引用
2. **不修改用户设计文档** — 变更仅在 CAD_SPEC.md 和代码中
3. **2D 直接绘制** — 从 params.py 画轮廓，不做 3D→2D 投影
4. **GB/T 国标** — 第一角投影、仿宋体、12层DXF、d=0.50mm 线宽
5. **输出统一** — 所有产物到 `cad/output/`
6. **关键尺寸不可随意修改** — 从设计文档明确规定的参数须严格遵守，修改前核对原始章节
