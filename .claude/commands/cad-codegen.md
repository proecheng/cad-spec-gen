---
name: cad-codegen
description: "Phase 2: Generate CadQuery scaffold code (params.py, build_all.py, assembly.py, part modules) from CAD_SPEC.md using Jinja2 templates."
---

# /cad-codegen — 从 CAD_SPEC.md 生成 CadQuery 脚手架代码

用户输入: $ARGUMENTS

## 指令

从 CAD_SPEC.md 的结构化数据，通过 Jinja2 模板自动生成 CadQuery Python 脚本。

### 前置条件

- 目标子系统目录下已有 `CAD_SPEC.md`（由 `/cad-spec` 生成）
- 已安装 Jinja2（`pip install Jinja2`）

### 路由规则

1. **无参数** → 显示用法：
   ```
   用法: /cad-codegen <subsystem> [--force]

   示例:
     /cad-codegen end_effector            # scaffold 模式（不覆盖已有文件）
     /cad-codegen end_effector --force    # 强制覆盖全部生成文件
     /cad-codegen 充电对接机构             # 支持中文别名
   ```

2. **`<子系统名>`** → 执行代码生成：
   ```bash
   python cad_pipeline.py codegen --subsystem <subsystem>
   ```

3. **`<子系统名> --force`** → 强制覆盖模式：
   ```bash
   python cad_pipeline.py codegen --subsystem <subsystem> --force
   ```

### 生成后自动检查（门控2）

`gen_parts.py` 生成脚手架后立即扫描所有新文件中的 `TODO:` 标记：

- **有未填 TODO** → 打印 WARNING 列表（文件名 + 行号 + 内容），以 **exit code 2** 退出
- **全部填写完毕** → 打印 `All coordinate system blocks filled. Ready for build.`

每个生成的 `<part>.py` 文件头包含强制坐标系声明块，**必须**填写后才能进入 Phase 3：

```python
# ┌─ COORDINATE SYSTEM (MUST fill before coding geometry) ──────────────────┐
# Local origin : <填写：如 bottom-left corner of mounting face>
# Principal axis: <填写：如 extrude along +Z (axial), body height = PARAM_H>
# Assembly orient: <填写：如 rotate X+90deg → axis becomes +Y (radial)>
# Design doc ref : <填写：如 §4.1.2 L176 — "储罐轴线与悬臂共线（径向）">
# └──────────────────────────────────────────────────────────────────────────┘
```

> 三道门控：门控1（DESIGN_REVIEW CRITICAL）→ 门控2（TODO扫描）→ 门控3（orientation_check.py）

代码生成分 5 步，使用 `codegen/` 目录下的生成器 + `templates/` 下的 Jinja2 模板：

| 步骤 | 生成器 | 模板 | 输入(CAD_SPEC) | 输出 |
|------|--------|------|----------------|------|
| 1 | `gen_params.py` | `params.py.j2` | §1 全局参数表 + §6.2 装配层叠 | `params.py` — 尺寸常量 + 派生装配参数 |
| 2 | `gen_build.py` | `build_all.py.j2` | §5 BOM树 | `build_all.py` — STD STEP + DXF 构建表 |
| 3 | `gen_parts.py` | `part_module.py.j2` | §5 BOM(自制叶零件) + §2 公差/表面 + §标题 | `ee_NNN_NN.py` — 零件脚手架（含自动标注） |
| 4 | `gen_assembly.py` | `assembly.py.j2` | §4连接 + §5BOM + §6姿态 | `assembly.py` — 装配结构（含方向变换） |
| 5 | `gen_std_parts.py` | — | §5 BOM(外购件) | `std_ee_NNN_NN.py` — 标准件简化几何 |

**命名规则**：零件编号通过 `strip_part_prefix()` 通用前缀剥离（不绑定 "GIS-"），如 `GIS-EE-001-01` → `ee_001_01.py` / `make_ee_001_01()`；外购件 `std_ee_001_03.py` / `make_std_ee_001_03()`

**自动标注**（v2.2.0+）：`gen_parts.py` 现在还解析 CAD_SPEC.md 的 §2 公差/表面数据和标题行，传入模板。生成的 `draw_*_sheet()` 函数自动调用 `auto_annotate(solid, sheet, annotation_meta={...})`，在 HLR 投影后添加 GB/T 合规标注：
- **几何驱动**（无需 §2 数据）：外形尺寸、圆直径、中心线
- **Spec 驱动**（从 §2 注入）：公差文本、形位公差框、个别面粗糙度
- **材质分类**：`classify_material_type(material)` 自动推断 material_type（al/steel/peek/nylon/rubber），驱动技术要求和默认 Ra 选取
- **项目名参数化**：`ThreeViewSheet` 接收 `project_name`/`subsystem_name`（从 spec 标题解析），标题栏不再硬编码

**派生参数**：`gen_params.py` 自动从 §6.2 装配层叠表提取 `MOUNT_CENTER_R`（工位安装半径）、`STATION_ANGLES`（工位角度列表）等装配级参数，写入 `params.py` 的 `Derived (computed)` 区。

**方向变换**：`gen_assembly.py` 读取 §6.2 的 `轴线方向` 列，按零件名匹配子句（如 "壳体轴沿-Z，储罐轴∥XY"），对需要旋转的零件生成 `rotate()` 代码。优先级：盘面∥XY / 环∥XY → 无旋转 > 沿-Z / 垂直 → 无旋转 > ∥XY / 水平 → 绕X轴转90°。

### 标准件自动生成（步骤 5）

`gen_std_parts.py` 从 BOM 中提取所有 `外购` 零件，按名称/型号自动分类后生成简化 CadQuery 几何：

| 分类 | 简化几何 | 示例型号 |
|------|---------|---------|
| motor | 圆柱 + 轴 | Maxon ECX SPEED 22L |
| reducer | 圆柱（较粗） | Maxon GP22C |
| spring | 环形碟片 | DIN 2093 A6 |
| bearing | 内外环 | MR105ZZ, 688ZZ |
| sensor | 圆柱/方盒 | ATI Nano17, I300-UHF |
| pump | 方盒 + 管口 | 齿轮泵 |
| connector | 小圆柱 | LEMO FGG.0B |
| seal | 圆环体 | FKM O型圈 |
| tank | 圆柱 | 不锈钢储罐 |

- 跳过 `fastener`（太小）和 `cable`（柔性体）
- **尺寸三级查找**: `cad_spec_defaults.py` → `lookup_std_part_dims()`:
  1. 型号匹配（如 `GP22C` → d=22, l=35）
  2. 正则提取 BOM 材质字段中的 `Φd×l` / `w×h×l` 模式（如 `Φ25×110mm` → d=25, l=110）
  3. 分类 fallback（如 `_tank` → d=38, l=280）
- 输出命名: `std_ee_001_05.py`（`std_` 前缀 + 料号后缀）
- scaffold 模式下不覆盖已有文件

### scaffold vs force 模式

- **scaffold**：仅生成不存在的文件，已有工程师手动修改的文件不会被覆盖
- **force**（`gen_params.py` 默认）：全部重新生成覆盖，适用于首次生成或 CAD_SPEC 大幅变更后的完全重置

### 生成后汇总

执行完毕后向用户报告：
- 每个生成器的执行结果（成功/跳过/失败）
- 生成或更新的文件列表
- 下一步建议：`/mechdesign <子系统>` 手动完善几何细节，或 `python cad_pipeline.py build` 直接构建

### 与其他命令的关系

```
/cad-spec → CAD_SPEC.md    (Phase 1: 规范化)
/cad-codegen → *.py 脚手架  (Phase 2: 代码生成)  ← 你在这里
/mechdesign → 手动完善几何   (手动阶段)
cad_pipeline.py build       (Phase 3: 构建)
cad_pipeline.py render      (Phase 4: 渲染)
cad_pipeline.py full        (一键全流程)
```
