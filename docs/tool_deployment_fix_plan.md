# 工具文件部署机制修复方案

> 根因：v2.3 所有 2D 工程图修复（7 项教授意见）未生效
> 日期：2026-04-07
> 优先级：P0（阻塞所有 v2.3 功能）

---

## 1. 问题现象

在 end_effector 子系统全管线测试中，教授 7 项审图意见的修复**全部未生效**：
- 位置尺寸：无
- 剖面叠加：无
- 正交引出线：无
- 动态技术要求位置：无

## 2. 根因

### 2a. 工具文件有 4 份副本，修改了错误的位置

v2.3 的修改全部落在 `cad/lifting_platform/` 的副本上，但**部署源是项目根目录**。

```
项目根目录 (SKILL_ROOT)        ← 部署源（_deploy_tool_modules 从这里复制）
  drawing.py                   ← 旧版！v2.3 改动不在这里
  cq_to_dxf.py                ← 旧版！
  draw_three_view.py           ← 旧版！
      ↓ _deploy_tool_modules() 复制
cad/end_effector/              ← 得到旧版
cad/lifting_platform/          ← v2.3 改动在这里，但不是部署源
src/.../python_tools/          ← PyPI 打包源，也是旧版
```

### 2b. _deploy_tool_modules() 缺少关键文件

当前部署清单（cad_pipeline.py:72）：
```python
tool_files = ["drawing.py", "draw_three_view.py", "cq_to_dxf.py", "render_dxf.py", "render_config.py"]
```

缺少：`cad_spec_defaults.py`（draw_three_view.py 的 import 依赖）

### 2c. 三个部署机制不一致

| 机制 | 触发时机 | 源 | 目标 | 部署的文件 |
|------|---------|---|------|-----------|
| `_deploy_tool_modules()` | codegen 阶段 | 项目根 | cad/\<sub\>/ | 5 个（缺 cad_spec_defaults.py） |
| setup wizard | pip install | src/.../python_tools/ | 项目根 | 不同的清单 |
| hatch_build.py | wheel 构建 | 项目根 | src/.../python_tools/ | 又一个不同的清单 |

## 3. 修复方案

### 3a. 权威源确认 + 同步所有副本

**权威源：项目根目录**。所有修改只在这里进行。

立即同步：
```
cad/lifting_platform/{drawing,cq_to_dxf,draw_three_view}.py  →  项目根/
项目根/  →  cad/end_effector/
项目根/  →  src/cad_spec_gen/data/python_tools/
```

### 3b. _deploy_tool_modules() 补全部署清单

```python
tool_files = [
    "drawing.py",
    "draw_three_view.py", 
    "cq_to_dxf.py",
    "render_dxf.py",
    "render_config.py",
    "cad_spec_defaults.py",   # ← 新增
]
```

### 3c. hatch_build.py 和 skill_register.py 统一清单

三个清单合并为一个常量 `SHARED_TOOL_FILES`，在 cad_paths.py 中定义，
三个部署机制都引用同一个清单。

### 3d. 防止未来改错位置

在每个子系统副本的文件头加入部署标记：
```python
# ── AUTO-DEPLOYED from project root. DO NOT EDIT HERE. ──
# Edit the authoritative copy at: {SKILL_ROOT}/{filename}
# Deployed by: cad_pipeline.py _deploy_tool_modules()
```

## 4. 实施步骤

| # | 操作 | 文件 |
|---|------|------|
| 1 | 从 lifting_platform 副本同步到项目根 | drawing.py, cq_to_dxf.py, draw_three_view.py |
| 2 | 补全 _deploy_tool_modules 清单 | cad_pipeline.py |
| 3 | 统一 SHARED_TOOL_FILES 常量 | cad_paths.py |
| 4 | 更新 hatch_build.py 清单 | hatch_build.py |
| 5 | 更新 skill_register.py 清单 | skill_register.py |
| 6 | 同步到所有子系统 + 打包目录 | 自动（运行 codegen 或手动） |
| 7 | 重新生成 SLP-100 验证 7 项修复 | p100.py 重新生成 |
