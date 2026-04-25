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
| F3 sw_toolbox 命中数 ≥ 1（项目级） | ❌ sw_toolbox 命中 0 次（来自 20260425-112739） |
| F4 enhanced PNG 大小 > baseline 5% | ✅ 全视图总大小比：+6.1%（6,899,151B / 6,502,195B）  各视图: V1_front_iso:+1% V2_rear_oblique:+3% V3_side_elevation:+1% V5_ortho_front:+19% |
| F5 所有 PNG 非全黑 | ✅ 所有 PNG 非全黑 |

## 图片索引

| 视图 | baseline | enhanced |
|------|----------|----------|
| V1_front_iso | baseline/end_effector/V1_front_iso.png | enhanced/end_effector/V1_front_iso.png |
| V2_rear_oblique | baseline/end_effector/V2_rear_oblique.png | enhanced/end_effector/V2_rear_oblique.png |
| V3_side_elevation | baseline/end_effector/V3_side_elevation.png | enhanced/end_effector/V3_side_elevation.png |
| V4_exploded | baseline/end_effector/V4_exploded.png | enhanced/end_effector/V4_exploded.png |
| V5_ortho_front | baseline/end_effector/V5_ortho_front.png | enhanced/end_effector/V5_ortho_front.png |

## 肉眼观察（人工填写）

### V1_front_iso
- baseline: ___
- enhanced: ___
- 改善描述: ___

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
