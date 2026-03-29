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
| 1 | `gen_params.py` | `params.py.j2` | §1 全局参数表 | `params.py` — 尺寸常量 |
| 2 | `gen_build.py` | `build_all.py.j2` | §5 BOM树 | `build_all.py` — STEP/STD/DXF 构建表 |
| 3 | `gen_parts.py` | `part_module.py.j2` | §5 BOM(自制叶零件) | `station_*.py` — 零件脚手架 |
| 4 | `gen_assembly.py` | `assembly.py.j2` | §4连接 + §5BOM + §6姿态 | `assembly.py` — 装配结构（含标准件） |
| 5 | `gen_std_parts.py` | — | §5 BOM(外购件) | `std_*.py` — 标准件简化几何 |

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
- 尺寸来源: `cad_spec_defaults.py` → `STD_PART_DIMENSIONS` 查找表
- 输出命名: `std_ee_001_05.py`（`std_` 前缀 + 料号后缀）
- scaffold 模式下不覆盖已有文件

### scaffold vs force 模式

- **scaffold**：仅生成不存在的文件，已有工程师手动修改的文件不会被覆盖
- **force**（`gen_params.py` 默认）：全部重新生成覆盖，适用于首次生成或 CAD_SPEC 大幅变更后的完全重置

> **v2.0 变更**: `gen_params.py` 的默认模式已从 `scaffold` 改为 `force`（每次 codegen 完整重新生成 `params.py`）。`gen_parts.py` 和 `gen_std_parts.py` 新增 `--mode force` 选项。pipeline `codegen --force` 会统一向所有生成器传递 `--mode force`。

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
