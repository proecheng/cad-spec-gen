# 渲染回归报告

## 渲染状态

| 模式 | 状态 |
|------|------|
| baseline | ✅ 成功 |
| enhanced | ✅ 成功 |

## Feature 断言

| 断言 | 结果 |
|------|------|
| F1 base_color_texture 字段存在 | ✅ base_color_texture 字段存在 |
| F2 SW_TEXTURES_DIR 目录存在且非空 | ✅ 25 个文件/子目录 |
| F3 sw_toolbox 命中数 ≥ 1（项目级） | ❌ sw_toolbox 命中 0 次（来自 20260425-112739，最近 artifact 需刷新） |
| F4 enhanced PNG 大小 > baseline 5% | ❌ +0.0%（Track A 管线断点：render_3d.py 未调用 load_runtime_materials_override，create_pbr_material 不支持图像纹理节点） |
| F5 所有 PNG 非全黑 | ✅ 所有 PNG 非全黑 |

## 图片索引

| 视图 | baseline | enhanced |
|------|----------|----------|
| V1_front_iso | baseline/end_effector/V1_front_iso.png | enhanced/end_effector/V1_front_iso.png |
| V2_rear_oblique | baseline/end_effector/V2_rear_oblique.png | enhanced/end_effector/V2_rear_oblique.png |
| V3_side_elevation | baseline/end_effector/V3_side_elevation.png | enhanced/end_effector/V3_side_elevation.png |
| V4_exploded | baseline/end_effector/V4_exploded.png | enhanced/end_effector/V4_exploded.png |
| V5_ortho_front | baseline/end_effector/V5_ortho_front.png | enhanced/end_effector/V5_ortho_front.png |

## 发现摘要

- **F4 根因（Track A 管线断点）**：`render_3d.py` 从未调用 `render_config.load_runtime_materials_override()`，`CAD_RUNTIME_MATERIAL_PRESETS_JSON` env var 被忽略。且 `create_pbr_material()` 仅处理 PBR 数值，不挂 `ShaderNodeTexImage` 节点。需在 `render_3d.py` 修复后重跑验证 F4。
- **V4_exploded 缺失**：`render_3d.py --all` 跳过 type=exploded 视图，仅渲染 4/5 视图，V4 需 `render_exploded.py`。
- **F3 说明**：最近 resolve_report 来自旧 artifact（20260425-112739）；重新运行 `sw-inspect --resolve-report` 后应有 sw_toolbox 命中。

## 肉眼观察（人工填写）

### V1_front_iso
- baseline: ___
- enhanced: ___
- 改善描述: ___ （注：当前 baseline==enhanced，Track A 管线修复后重新比较）

### V2_rear_oblique
- baseline: ___
- enhanced: ___
- 改善描述: ___

### V3_side_elevation
- baseline: ___
- enhanced: ___
- 改善描述: ___

### V4_exploded
- baseline: ___
- enhanced: ___
- 改善描述: ___

### V5_ortho_front
- baseline: ___
- enhanced: ___
- 改善描述: ___
