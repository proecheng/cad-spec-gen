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

### 生成内容

代码生成分 4 步，使用 `codegen/` 目录下的生成器 + `templates/` 下的 Jinja2 模板：

| 步骤 | 生成器 | 模板 | 输入(CAD_SPEC) | 输出 |
|------|--------|------|----------------|------|
| 1 | `gen_params.py` | `params.py.j2` | §1 全局参数表 | `params.py` — 尺寸常量 |
| 2 | `gen_build.py` | `build_all.py.j2` | §5 BOM树 | `build_all.py` — STEP/DXF 构建表 |
| 3 | `gen_parts.py` | `part_module.py.j2` | §5 BOM(叶零件) | `station_*.py` — 零件脚手架 |
| 4 | `gen_assembly.py` | `assembly.py.j2` | §4连接 + §5BOM + §6姿态 | `assembly.py` — 装配结构 |

### scaffold vs force 模式

- **scaffold**（默认）：仅生成不存在的文件，已有工程师手动修改的文件不会被覆盖
- **force**：全部重新生成覆盖，适用于首次生成或 CAD_SPEC 大幅变更后的完全重置

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
