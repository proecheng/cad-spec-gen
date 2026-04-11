# CAD Pipeline 通用架构文档

> 本文档从代码逻辑（`cad_pipeline.py`）生成，描述管线的通用结构。
> **不依赖任何具体子系统**（如 end_effector），适用于任意 `cad/<subsystem>/` 目录。

---

## 一、全局结构

```
用户设计文档 (*.md)
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                    cad_pipeline.py                          │
│  统一入口，编排 Phase 1~6，支持 --dry-run / --skip-* 标志   │
└─────────────────────────────────────────────────────────────┘
        │
   ┌────┴─────┬──────────┬──────────┬──────────┬──────────┐
   ▼          ▼          ▼          ▼          ▼          ▼
Phase 1    Phase 2    Phase 3    Phase 4    Phase 5    Phase 6
  SPEC     CODEGEN     BUILD     RENDER    ENHANCE   ANNOTATE
```

---

## 二、各阶段详解

### Phase 1 — SPEC（设计审查 + 规格生成）

```
用户设计文档 (docs/design/XX-*.md)
        │
        ▼
  cad_spec_gen.py
        │
        ├─► [1a] 生成 DESIGN_REVIEW.md + DESIGN_REVIEW.json
        │         （逐条检查：CRITICAL / WARNING / OK）
        │
        ├─► [1b] 交互式审查（默认）/ --auto-fill / --proceed / --review-only
        │         CRITICAL > 0 → 阻断管线（exit 1）
        │         Agent模式 → exit 10，等待Agent逐项审查
        │
        ├─► [1c] 生成 CAD_SPEC.md
        │         （参数表：名称 / 值 / 单位 / 公差 / 来源行号）
        │
        ├─► [1d] v2.3: extract_part_features()
        │         交叉引用 §2 公差/§3 紧固件/§4 连接/§8 装配
        │         → 每个零件的孔/槽/沉台特征清单
        │
        ├─► [1e] v2.5: extract_part_placements()
        │         从叙述文字提取串行堆叠链（→ 语法，含围栏代码块）
        │         识别非轴向放置模式：
        │           radial_extend / side_mount / coaxial / lateral_array / extremity
        │         → §6.3 零件级定位（Z 偏移 + mode + confidence + source）
        │
        ├─► [1f] v2.5: extract_part_envelopes()  (v2.9 returns tuple)
        │         从多个来源收集零件包络尺寸，跨模块有效优先级：
        │           P1 零件级参数表 > P2 SectionWalker (v2.9)
        │             > P4 视觉标识表 > P3 BOM材质列
        │             > P7 parts_library > P5/P6 几何回填
        │         v2.9: P2 块由 SectionWalker 取代 — 有状态地
        │         追踪 Markdown 章节栈，用 4 层混合匹配策略
        │         （Tier 0 part_no 回归守护 / Tier 1 结构编号 /
        │         Tier 2 CJK+ASCII 双路子序列 / Tier 3 Jaccard）
        │         把 §6.4 包络标签归属到正确的 BOM 装配体。
        │         尺寸按 (X, Y, Z) 轴向规范化，每个条目携带
        │         granularity 标签（station_constraint | part_envelope）
        │         → 下游 JinjaPrimitiveAdapter 拒绝把
        │         station_constraint 用作单件尺寸。
        │         返回 (envelopes, WalkerReport) 元组，WalkerReport
        │         包含 UNMATCHED 列表 + 统计 + feature flag 状态。
        │         CAD_SPEC_WALKER_ENABLED=0 可回退到旧 regex 块。
        │         → §6.4 零件包络尺寸（增加 粒度 / 理由 / 轴向标签 /
        │           置信度 审计列 + §6.4.1 UNMATCHED 子节）
        │
        └─► [1g] v2.5: _apply_exclude_markers()
                  交叉引用 §8.3 否定约束表
                  → 标记不属于当前装配体的装配（exclude 列）
                  → §9 装配约束（exclusions + constraints）

输出文件：
  cad/<subsystem>/CAD_SPEC.md          （新增 §6.3 / §6.4 / §9，见下）
  cad/<subsystem>/DESIGN_REVIEW.md
  cad/<subsystem>/DESIGN_REVIEW.json
```

**v2.5.0 新增 CAD_SPEC.md 章节：**

| 章节 | 标题 | 内容 |
|------|------|------|
| §6.3 | 零件级定位 | 每个零件的 Z 偏移，含 mode / confidence / source 列 |
| §6.4 | 零件包络尺寸 | 每个零件的包络，含 type / size / source 列 |
| §9   | 装配约束 | 来自否定约束表（§8.3）的装配排除项与约束说明 |

**通用性保证：**
- `cad_spec_gen.py` 从任意设计文档提取参数，不硬编码子系统名
- 参数行号（来源）写入 CAD_SPEC.md，确保可追溯

---

### Phase 2 — CODEGEN（CadQuery 脚手架生成）

```
CAD_SPEC.md
        │
        ├─► gen_params.py    → params.py       （所有尺寸常量，含注释来源行）
        ├─► gen_build.py     → build_all.py    （STEP/DXF导出主脚本）
        ├─► gen_parts.py     → <part>.py ×N   （每个零件的CadQuery模板）
        ├─► gen_std_parts.py → std_<part>.py  （标准件/外购件简化几何模板）
        └─► gen_assembly.py  → assembly.py    （装配体，含 _station_transform + 逐零件偏移）

模式：
  --mode scaffold  仅生成骨架（不覆盖已有文件）
  --mode force     强制覆盖

v2.3.0 新增：
  - gen_parts.py: extract_part_features() 交叉引用 §2/§3/§4/§8 → 零件特征清单
  - part_module.py.j2: 特征生成块（through_hole/counterbore/threaded_hole → CadQuery .hole()）
  - gen_parts.py: needs_section_view 自动检测 → 模板生成 auto_section_overlay() 调用
  - 模糊匹配 _fuzzy_match()：处理"上板"→"上固定板"等中文缩写

v2.5.0 新增：
  - gen_assembly.py 消费 §6.3 / §6.4 / §9：
    • _parse_part_positions()：读取 §6.3，精确定位每个零件（取代启发式堆叠）
    • _parse_excluded_assemblies()：读取 §6.2 exclude 列，跳过非本地装配体
  - 坐标约定（底面 Z 惯例）：
    • §6.3 值 = translate() 参数 = 零件底面的 Z 位置
    • §6.3 使用局部坐标（相对于工位安装面），全局变换由 _station_transform() 处理

v2.2.3 新增：
  - assembly.py 两层定位：零件级 translate()（§6.2 逐行偏移）+ 工位级 _station_transform（径向旋转+平移）
  - 标准件线缆/线束超出装配包络时自动截短至可视化尺寸
  - render_config.py: resolve_bom_materials() 材料桥接 bom_id→component→material 查找链
  - render_config.py: 自动从 BOM 创建缺失的 materials + components 条目，含一致性校验
```

**CadQuery 编码模板（防止脑补的关键约束）：**

> 以下约束由 `src/cad_spec_gen/data/templates/part_module.py.j2` 和 `assembly.py.j2` **自动强制执行**。
> codegen 生成的文件中，所有 TODO 项必须填写，否则 orientation_check.py 会在 Phase 3 门控处报错阻断。

每个生成的 `<part>.py` 文件头部包含**强制坐标系声明块**（来自模板）：

```python
# ┌─ COORDINATE SYSTEM (MUST fill before coding geometry) ──────────────────┐
# Local origin : TODO: e.g. bottom-left corner of mounting face
# Principal axis: TODO: e.g. extrude along +Z (axial), body height = PARAM_H
# Assembly orient: TODO: e.g. rotate X+90deg → axis becomes +Y (radial)
# Design doc ref : TODO: e.g. §4.1.2 L176 — "储罐轴线与悬臂共线（径向）"
# └──────────────────────────────────────────────────────────────────────────┘
#
# DO NOT extrude/rotate based on assumption. Every axis choice must cite
# a design-doc line above. If the doc is ambiguous, raise a DESIGN QUESTION.
```

每个 `make_<part>()` 函数必须包含：

```python
def make_<part_name>() -> cq.Workplane:
    """GIS-EE-XXX-YY: <零件名> — <材质>

    Envelope: W x D x H mm  (per §N.N.N L<行号>)
    Axis: principal axis = +Z before assembly transform  (per §N.N.N L<行号>)
    """
    # Per §N.N.N L<行号>: <尺寸说明>
    body = cq.Workplane("XY").box(PARAM_W, PARAM_D, PARAM_H, centered=(True, True, False))
    return body
```

`assembly.py` 的每个零件定位包含两层变换（来自 `assembly.py.j2`）：

```python
# Layer 1: Per-part offset (from §6.2 per-row Z offset)
<part> = make_<part>()
<part> = <part>.translate((0, 0, -27.0))          # 零件级轴向偏移

# Layer 2: Optional orientation + station-level radial transform
# Orient: Per §N.N.N L<行号>: <零件>轴线∥<平面/方向>
# Rule:   e.g. "tank axis radial (+Y) per §4.1.2 L176 — rotate X+90deg"
<part> = <part>.rotate((0,0,0), (1,0,0), 90)      # +Z → +Y (radial outward)
<part> = _station_transform(<part>, _a, _tx, _ty, _tz)  # 工位级径向定位
```
```

---

### Phase 3 — BUILD（CadQuery 构建 STEP/DXF）

```
[前置门控] orientation_check.py
        │  8项断言：bounding box主轴 vs 设计文档规定方向
        │  FAIL → 阻断，不生成STEP
        │  --skip-orientation 可旁路（不推荐）
        ▼
  build_all.py（由 gen_build.py 生成）
        │
        ├─► 调用 assembly.py → make_assembly()
        ├─► 导出 <subsystem>.step     （几何精确）
        ├─► 导出 <subsystem>.dxf      （工程图）
        └─► 导出 <subsystem>.glb      （Blender用）

输出目录：cad/output/

v2.3.0 DXF 增强：
  - allocate_dim_angles(prefer_orthogonal=True) → 引出线优先水平/垂直
  - auto_annotate: 俯视图自动标注孔心到基准边的位置尺寸（≤4 组，对称去重）
  - auto_section_overlay: 含内部特征的零件自动叠加 A-A 剖面线 + 剖切指示线
  - add_section_hatch_with_holes: 剖面线排除孔区域（GB/T 4457.5）
  - draw_three_view.py:save(): 技术要求位置动态计算（视图下方空白处）
```

**orientation_check.py 通用扩展方式：**
```python
# 新增零件时，在 run_checks() 中追加：
from <station_module> import make_<part>
bb = _bbox(make_<part>())
res.check(
    "<零件名> 轴线方向",
    _principal_axis(bb) == "<x|y|z>",
    f"axis=<轴> [OK] (per §N.N.N L<行号>)",
    f"axis={{_principal_axis(bb)}} -- 应为<轴>，检查 assembly.py"
)
```

---

### Phase 4 — RENDER（Blender Cycles 渲染）

```
<subsystem>.glb
        │
        ▼
  render_config.json  （视角配置，键值动态读取，非硬编码）
        │
        │  camera:{
        │    "V1": {type: standard, ...},
        │    "V2": {type: standard, ...},
        │    "VN": {type: exploded | section | ortho | standard}
        │  }
        │
        ├─► type=standard → render_3d.py    --view VN
        ├─► type=exploded → render_exploded.py
        ├─► type=section  → render_section.py
        └─► type=ortho    → render_3d.py    --view VN --ortho

自动帧取（auto-frame）：
  - 计算场景 bounding sphere → (center, radius)
  - 相机沿视线方向退至 dist = radius / sin(fov/2) / frame_fill
  - frame_fill 来自 render_config.json["frame_fill"]，默认 0.75
  - 不依赖视角数量，N个视角全部自适应

输出：cad/output/renders/<VN>_<name>_<timestamp>.png
输出：cad/output/renders/render_manifest.json  （本次渲染新增文件列表 + 元数据；不含历史遗留文件）
输出：cad/output/renders/<VN>_<name>_labels.json  （标注锚点 sidecar，下详）
```

**标注锚点 sidecar（Object Index Mask）：**

每个视图渲染时，`render_label_utils.py` 自动生成标注锚点 sidecar JSON：

1. 渲染前：给 render_config.json 中标注的零件分配 `pass_index`，通过 Compositor 注入 Object Index 输出节点
2. 渲染时：Cycles 在同一次渲染中同时输出颜色图 + Object Index EXR（零额外开销）
3. 渲染后：读取 EXR，对每个零件计算可见像素质心 → 换算到 1920×1080 参考分辨率 → 写入 sidecar JSON
4. 清理：删除临时 EXR，恢复 Blender 原始状态（compositor 节点、pass_index、use_nodes）

**相比旧方案（`obj.location` 投影）的改进：**
- 锚点位于零件**实际可见面积的中心**，不依赖建模原点位置
- 自动处理遮挡：被遮挡的像素不计入质心
- 分辨率无关：质心像素坐标自动换算到参考分辨率

**Fallback 链：** mask 质心 → `world_to_camera_view` 投影 → render_config.json 默认坐标

---

### Phase 5 — ENHANCE（AI 图像增强）

支持四种后端，由 `pipeline_config.json` 的 `enhance.backend` 字段或 `--backend` CLI 参数控制。
自动检测优先级：`FAL_KEY` 环境变量 → ComfyUI 运行中 → Gemini 配置 → engineering 兜底。
降级链：fal → gemini → engineering（降级后锁定后端，确保批次内一致性）。

```
render_manifest.json
        │  (或 --dir 手动指定目录)
        ▼
  Auto-enrich（P2）：
    params.py → generate_prompt_data() → merge_into_config(rc)
    将零件名/材质/方向信息注入 render_config（内存，不写盘）
        │
        ▼
  build_enhance_prompt(view_key, rc)
    → 为每个视角构建增强 prompt
        │
        ├─► [backend=gemini]
        │     gemini_gen.py  --prompt-file <tmp.txt> --image <VN.png>
        │     V1（基准视角）先处理，建立风格一致性锚点
        │     V2~VN 依次处理，引用 V1 作为风格参考
        │     多视角一致性（v2.1 四层防线）:
        │       1. 视角锁定 — 从相机向量计算方位角/仰角，写入 prompt
        │       2. 图片角色分离 — 源图第一位（锁构图），参考图第二位（仅风格）
        │       3. V1-anchor — V1 增强结果作为后续视角材质参考
        │       4. 源图高保真 — ≤4MB 不压缩，保留完整空间细节
        │     几何锁定：依赖 prompt 文字指令（"Preserve EXACT camera angle, viewpoint"）
        │
        ├─► [backend=fal]  [v2.3 NEW]
        │     fal_enhancer.py
        │     1. 生成 depth map + canny 边缘图（与 comfyui 相同预处理）
        │     2. 提交至 fal.ai Flux ControlNet API（需 FAL_KEY 环境变量）
        │     3. depth + canny 双约束硬锁几何（云端执行）
        │     4. 轮询结果，自动重试
        │     几何锁定：由控制图像硬约束（同 comfyui），但无需本地 GPU
        │     费用：~$0.20/张
        │
        ├─► [backend=comfyui]
        │     comfyui_enhancer.py
        │     1. 生成 depth map（MiDaS）+ canny 边缘图
        │     2. 提交 workflow JSON 至 localhost:8188
        │     3. ControlNet depth + canny 双约束硬锁几何
        │     4. 轮询结果，超时重试
        │     几何锁定：由控制图像硬约束，不依赖文字指令
        │
        └─► [backend=engineering]  [v2.3 NEW]
              无 AI 处理
              1. 读取 Blender PBR 渲染结果（已含材质贴图）
              2. 直接转换 PNG → JPG（质量95%）
              3. 几何完美保真，零费用
              适用场景：无 API 密钥、零预算、或仅需几何展示

输出：cad/output/renders/<VN>_<name>_<timestamp>_enhanced.jpg

v2.3.0 增强（通用，四种后端均受益）：
  - MATERIAL_PRESETS 新增 appearance 字段 → 数据源归一（删除 _PRESET_APPEARANCE）
  - _build_view_material_emphasis(): 根据相机仰角自动补充材质视角描述
    低仰角 → Fresnel edge sheen; 高仰角 → diffuse + AO
  - _derive_materials_from_params(): 当 render_config.json 无材质时,
    从 params.py material_type → default_preset → MATERIAL_PRESETS 自动补充
  - render_config.schema.json: 预留 render_passes + enhance_mode 字段
```

**后端对比：**

| 后端 | 费用 | GPU 要求 | 几何锁定 | 一致性 | 适用场景 | 推荐度 |
|------|------|----------|----------|--------|----------|--------|
| `engineering` | 免费，0.1s/张 | 无 | 完美（无AI） | 完美 | 工程审查、精确图纸 | ⭐⭐⭐⭐⭐ 推荐 |
| `gemini` | ~$0.02/张 | 无（云端） | 软（prompt） | 中 | 展示/答辩/商业计划书 | ⭐⭐⭐⭐ 推荐 |
| `fal` | ~$0.20/张 | 无（云端） | 硬（depth+canny） | 高 | 实验性 — 未来详细3D模型 | ⭐ 实验性 |
| `comfyui` | 免费 | 本地 8GB+ | 硬（ControlNet） | 高 | 本版本未测试 | — 未测试 |

> **推荐**：精确工程图用 `engineering`，外观展示用 `gemini`。
> **fal 实验性**：Flux 模型对简化 CadQuery 几何产生红绿噪点和色彩失真，ControlNet 架构本身可行但 Flux 基模型不适合 CAD 简化几何。
> **comfyui**：与 fal 相同 ControlNet 原理但使用 SD1.5（更适合 CAD），本版本未实测。

**自动检测优先级：**
1. `FAL_KEY` 环境变量存在 → `fal`
2. ComfyUI 服务运行中 (localhost:8188) → `comfyui`
3. Gemini 配置存在 (~/.claude/gemini_image_config.json) → `gemini`
4. 以上均不满足 → `engineering`

**降级链：** fal → gemini → engineering（某后端批次中失败时自动降级，降级后锁定后端防止批次内不一致）

**CLI 用法：**
```bash
# 自动检测
python cad_pipeline.py enhance --subsystem <name>
# 指定后端
python cad_pipeline.py enhance --subsystem <name> --backend fal
# 全流程指定后端
python cad_pipeline.py full --subsystem <name> --backend engineering
```

**环境检测（ComfyUI）：**
```bash
python comfyui_env_check.py
```

---

### Phase 6 — ANNOTATE（标注）

```
enhanced.jpg × N
        │
  render_config.json["labels"]    ← 引线端点 label:[x,y] + 文字
  <VN>_<name>_labels.json         ← 锚点 anchor:[x,y]（由 render 阶段的 Object Index Mask 生成）
        │  sidecar 优先覆盖 config 中的 anchor 坐标
        ▼
  annotate_render.py  --lang cn|en --style clean|dark|light
        │  anchor × (actual_w/ref_w) → 实际像素坐标
        │  绘制：锚点红圆 + 引线 + 文字标签
        └─► 输出标注图

输出：cad/output/renders/<VN>_<name>_labeled_{cn|en}.jpg
```

---

## 三、完整数据流

```
设计文档 (docs/design/XX-*.md)
  │
  ├─[P1]─► CAD_SPEC.md ──────────────────────────────────────────┐
  │         DESIGN_REVIEW.md                                      │
  │                                                               │
  ├─[P2]─► params.py          ← 所有尺寸常量（含来源行号）       │
  │         <part>.py × N     ← CadQuery零件模板（含方向注释）   │
  │         assembly.py       ← 装配体（含 _station_transform）  │
  │         build_all.py      ← 导出脚本                         │
  │         render_config.json ← 视角/标注配置（动态键值）       │
  │                                                               │
  ├─[P3]─► [orientation_check.py 门控]                           │
  │         → <subsystem>.step / .dxf / .glb                     │
  │                                                               │
  ├─[P4]─► render_manifest.json                                  │
  │         → V1.png, V2.png ... VN.png  (N由render_config决定)  │
  │                                                               │
  ├─[P5]─► V1_enhanced.jpg ... VN_enhanced.jpg                   │
  │         (prompt由params.py自动富化，非硬编码)                  │
  │                                                               │
  └─[P6]─► V1_annotated.jpg ... VN_annotated.jpg ◄──────────────┘
            (标注由render_config.json["labels"]驱动)
```

---

## 四、通用性设计原则

### 4.1 不硬编码视角数量
- Phase 4 渲染循环从 `render_config.json["camera"]` 动态读取所有键
- 新增/删除视角只需修改 `render_config.json`，管线代码不变
- `render_manifest.json` 记录实际生成的文件列表，下游阶段从清单读取

### 4.2 不硬编码子系统名
- `get_subsystem_dir(name)` 动态查找 `cad/<name>/` 目录
- `cmd_status()` 遍历 `CAD_DIR` 所有子目录，自动发现子系统
- `cad_pipeline.py init --subsystem <name>` 可创建任意新子系统

### 4.3 CadQuery 编码必须有来源依据
每个零件文件生成时强制包含：

| 必填字段 | 来源 | 检查方式 |
|---|---|---|
| 零件编号 | 设计文档BOM | CAD_SPEC.md |
| 所有尺寸 | `params.py` 常量 | 禁止文件内出现裸数字 |
| 建模轴说明 | 设计文档方向描述 | orientation_check.py |
| 装配旋转注释 | 设计文档轴线规定 | orientation_check.py |

### 4.4 防止「脑补」的三道门控

```
门控1 [P1]：DESIGN_REVIEW.json
  → CRITICAL问题 > 0 时阻断，强制用户补充设计文档
  → 调用者：cad_pipeline.py cmd_spec() → cad_spec_gen.py
  → 输出给：用户交互 / Agent --review-only 模式
  → 参数来源行号写入CAD_SPEC.md，可追溯

门控2 [P2]：gen_parts.py TODO 扫描
  → 调用者：cad_pipeline.py cmd_codegen() → codegen/gen_parts.py
  → 生成脚手架后自动扫描所有新文件中的 TODO: 标记
  → 输出给：终端 WARNING 列表（含文件名 + 行号 + 内容）
  → 阻断：有未填 TODO → exit(2)，cmd_codegen 返回非零，Phase 3 不执行
  → 覆盖：part_module.py.j2 坐标系声明块的每个字段

门控3 [P3]：orientation_check.py
  → 调用者：cad_pipeline.py cmd_build() 前置（L390）
  → bounding box 主轴断言，对比设计文档规定方向
  → 输出给：终端 PASS/FAIL 逐项列表
  → 阻断：任一 FAIL → build_all.py 不运行，不生成 STEP
  → 旁路：--skip-orientation（需显式声明）
  → 新增零件时同步新增断言（约定：不通过检查不提交）
```

**三道门互补关系：**
- 门控1：编码前，拦截设计文档歧义
- 门控2：编码中，强制填写方向来源（TODO不填不能进构建）
- 门控3：构建前，验证几何结果与设计文档一致

**v2.5.0 新增审查检查项（DESIGN_REVIEW.json）：**

| 编号 | 检查项 | 触发条件 |
|------|--------|----------|
| B10  | 孤立装配体 (orphan assemblies) | §9 中存在未被任何工位引用的装配体 |
| B11  | 缺失包络 (missing envelopes) | §6.4 中有零件未提取到包络尺寸 |
| B12  | 定位覆盖率不足 (low positioning coverage) | §6.3 中已定位零件数 / 总零件数 < 阈值 |

---

## 五、新子系统接入步骤

```bash
# 1. 初始化目录结构
python cad_pipeline.py init --subsystem <name>

# 2. 准备设计文档
# docs/design/XX-<name>.md
# 必须包含：参数表、零件清单(BOM)、各零件轴线方向描述

# 3. 生成规格
python cad_pipeline.py spec -s <name> --design-doc docs/design/XX-<name>.md

# 4. 生成代码脚手架
python cad_pipeline.py codegen -s <name>
# → 在 cad/<name>/ 下生成 params.py, <part>.py×N, assembly.py 等
# 注意：模板中 TODO 处需要根据设计文档实现几何体

# 5. 在 orientation_check.py 中为每个零件添加方向断言

# 6. 构建（含方向门控）
python cad_pipeline.py build -s <name>

# 7. 渲染（视角数由 render_config.json 决定）
python cad_pipeline.py render -s <name> --timestamp

# 8. 增强 + 标注
python cad_pipeline.py enhance -s <name>
python cad_pipeline.py annotate -s <name>

# 或一键全流程
python cad_pipeline.py full -s <name>
```

---

## 六、文件目录结构（每个子系统）

```
cad/<subsystem>/
  ├── CAD_SPEC.md              # [P1] 参数规格（含来源行号）
  ├── DESIGN_REVIEW.md         # [P1] 审查报告
  ├── DESIGN_REVIEW.json       # [P1] 机器可读审查结果
  ├── params.py                # [P2] 尺寸常量（全部含注释）
  ├── <part1>.py               # [P2] 零件几何（含坐标系注释）
  ├── <part2>.py               # [P2] ...
  ├── std_<stdpart>.py         # [P2] 标准件简化几何
  ├── assembly.py              # [P2] 装配体（含方向注释）
  ├── build_all.py             # [P2] STEP/DXF/GLB导出
  ├── orientation_check.py     # [P3] 方向预检（门控）
  ├── render_3d.py             # [P4] Blender标准渲染
  ├── render_exploded.py       # [P4] 爆炸图渲染（可选）
  ├── render_section.py        # [P4] 剖面图渲染（可选）
  ├── render_label_utils.py    # [P4] 标注锚点 Object Index Mask（共享模块）
  └── render_config.json       # [P4~P6] 视角+标注配置

cad/output/
  ├── <subsystem>.step
  ├── <subsystem>.dxf
  ├── <subsystem>.glb
  └── renders/
        ├── render_manifest.json
        ├── V1_<name>_<ts>.png
        ├── V1_<name>_labels.json       # 标注锚点 sidecar（Object Index Mask 质心）
        ├── V1_<name>_<ts>_enhanced.jpg
        └── V1_<name>_labeled_{cn|en}.jpg
```
