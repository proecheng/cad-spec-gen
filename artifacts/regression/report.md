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
| F3 sw_toolbox 命中数 ≥ 1（项目级） | ✅ sw_toolbox 命中 3 次（来自 20260425-185131，O型圈/定位销/微型轴承） |
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

## 肉眼观察（2026-04-25 session 29）

### V1_front_iso
- baseline: 铝合金白色壳体、黑色电机、金色 PEEK 环颜色分明，材质识别度高
- enhanced: 整体偏灰调，铝合金表面出现细微金属拉丝纹理，PEEK 金环颜色略减弱
- 改善描述: 表面真实感提升（金属拉丝），色彩区分度小幅下降；+1% 体积差符合视觉量

### V2_rear_oblique
- baseline: 颜色区分清晰，纯色材质，背面视角干净
- enhanced: 表面纹理更丰富，立体感增强，整体偏中灰调
- 改善描述: 纹理细节可见，背面金属质感改善；+3% 体积差

### V3_side_elevation
- baseline: 侧视角，简洁纯色
- enhanced: 侧面纹理轻微可见
- 改善描述: 与 V1 类似，微小纹理增益；+1% 体积差

### V4_exploded
- baseline: 无（render_3d.py --all 跳过 exploded 视图，V4 需单独 render_exploded.py）
- enhanced: 无
- 改善描述: N/A

### V5_ortho_front
- baseline: 正射影正面，大矩形块呈浅灰白，颜色区分度高
- enhanced: **顶部大矩形块出现明显机织/编织纹理**（carbon_fiber_weave 预设生效），整体灰度对比度显著提高，纹理细节丰富
- 改善描述: 编织纹理非常显著，是体积差 +19% 的主要来源；视觉真实感大幅提升
