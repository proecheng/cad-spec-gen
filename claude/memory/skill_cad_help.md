# skill_cad_help — CAD 混合渲染管线交互式帮助

## 搜索优先原则

**每个意图动作执行前，必须先搜索项目实际文件，不要凭记忆假设。**

1. **先搜后答** — 对任何涉及"某个文件在不在""某个配置怎么设的"的问题，先搜索文件系统（ls/find/grep 或等效工具），再回答
2. **多路径搜索** — 同一信息可能存在于多处（环境变量、配置文件、代码默认值），全部检查：
   - Gemini 配置：`~/.config/gemini_image_config.json` > 环境变量 `GEMINI_API_KEY` > `gemini_gen.py` 代码默认值
   - 渲染工具：`tools/hybrid_render/` > `cad/end_effector/` > `tools/blender/`
   - prompt模板：`templates/prompt_*.txt`（3套：enhance/exploded/ortho）
3. **搜到即记录** — 搜索到的实际路径/版本/配置值，直接写进输出，不用模板中的占位值
4. **不猜测缺失** — 搜不到的不要假设存在，标注 ❌ 并给出创建/安装指引

### Known Key Paths (search at runtime — these are examples)

| Component | Typical Path |
|-----------|-------------|
| gemini_gen.py | User-configured (search `which gemini_gen.py` or project config) |
| Gemini config | `~/.config/gemini_image_config.json` or env var `GEMINI_API_KEY` |
| Hybrid render tools | `tools/hybrid_render/` (check_env.py, prompt_builder.py) |
| Blender | `tools/blender/blender.exe` or env var `BLENDER_PATH` |
| Render config engine | `cad/<subsystem>/render_config.py` |
| Prompt templates | `tools/hybrid_render/prompts/` or `cad/<subsystem>/prompt_*.txt` |

## 意图匹配表

从用户问题文本提取关键词，匹配到最佳意图后执行对应动作。

| 意图 | 关键词 | 动作 |
|------|--------|------|
| env_check | 运行环境, 安装, 环境, 依赖, 需要什么, requirements, install, env | → 环境检查 |
| validate | 验证, 检查配置, config对不对, validate, 配置正确 | → 验证配置 |
| next_step | 下一步, 接下来, 做什么, 怎么继续, next, what to do | → 推荐下一步 |
| new_subsys | 新子系统, 新建, 开始, 怎么开始, quick start, 从零, 初始化 | → Quick Start引导 |
| material | 材质, 颜色, preset, 外观, material, 铝, 钢, 塑料, PBR | → 材质预设表 |
| camera | 相机, 视角, 角度, camera, 拍摄, 视图, view | → 相机配置说明 |
| explode | 爆炸, explode, 分解, 拆开, 展开图 | → 爆炸图配置 |
| render | 渲染, render, 画图, 出图, blender, cycles, 生成图片 | → 渲染执行/引导 |
| ai_enhance | gemini, AI, 增强, prompt, 照片级, enhance, 混合 | → AI增强说明 |
| troubleshoot | 报错, error, 失败, 不行, 问题, bug, 出错, 崩溃, fix | → 排错指南 |
| file_struct | 文件, 目录, 在哪, 结构, 文件树, tree, layout | → 文件结构 |
| status | 状态, 进度, 哪些子系统, status, progress | → 子系统状态 |
| integration | 集成, 接入, 其他模型, GLM, GPT, LLM, agent, 调用, 通用, 怎么接, 框架 | → 集成其他LLM/Agent |
| parts | 零件, 部件, 模块, BOM, 清单, 有哪些零件, 零件树, 结构, 物料, 分解 | → 解析设计文档BOM |
| spec | CAD_SPEC, spec, 规范, 提取数据, 生成spec, 参数提取, cad_spec | → CAD Spec生成/查看 |

---

## 动作详情

### 1. env_check — 环境检查

**搜索优先**：先搜实际文件再报告，不凭模板假设。

执行以下检查并汇报结果：

```
检查项:
1. Python 版本 (需 3.10+): python --version
2. CadQuery: python -c "import cadquery; print(cadquery.__version__)"
3. ezdxf: python -c "import ezdxf; print(ezdxf.__version__)"
4. matplotlib: python -c "import matplotlib; print(matplotlib.__version__)"
5. Blender: 搜索 tools/blender/blender.exe → --version (需 4.x LTS)
6. GPU渲染: 在Blender中检测GPU (OptiX/CUDA/HIP/OneAPI)
   - 有GPU → 自动使用GPU (render_3d.py/render_exploded.py自动检测)
   - 无GPU → 回落CPU（可用但较慢）
   - 可通过 --gpu / --cpu 强制指定
7. Gemini AI增强 (按优先级逐项检查，任一通过即✅):
   a. 读取 ~/.config/gemini_image_config.json → 显示 api_base_url + model (隐藏key)
   b. 检查环境变量 GEMINI_API_KEY / GOOGLE_API_KEY
   c. 检查 gemini_gen.py 是否存在: gemini_gen.py 或 $GEMINI_GEN_PATH
   d. 运行 tools/hybrid_render/check_env.py (如存在)
8. 字体: 检查 FangSong (仿宋) 字体是否可用
```

输出格式（用实际搜索到的值填充）：
```
环境检查结果:
  ✅ Python 3.11.9
  ✅ CadQuery 2.7.0
  ✅ ezdxf 1.4.3
  ✅ matplotlib 3.10.8
  ✅ Blender 4.2.10 LTS (tools/blender/blender.exe)
  ⚠️ GPU渲染: 无GPU检测到 — 使用CPU (较慢)
     提示: 如有NVIDIA GPU环境可自动加速5-20倍 (OptiX/CUDA)
  ✅ Gemini AI: ~/.config/gemini_image_config.json
     API: https://generativelanguage.googleapis.com/v1beta
     模型: gemini-2.0-flash-preview-image-generation
     gemini_gen.py: gemini_gen.py
  ✅ FangSong 仿宋字体 (C:\Windows\Fonts\simfang.ttf)
```

缺失项给出安装命令：
- CadQuery: `pip install cadquery`
- ezdxf: `pip install ezdxf`
- matplotlib: `pip install matplotlib`
- Blender: 下载 Blender 4.2 LTS portable 到 `tools/blender/`
- Gemini: 运行 `python gemini_gen.py --config` 启动配置向导

### 2. validate — 验证配置

读取目标子系统的 `render_config.json`，检查：

```
1. JSON语法正确性
2. 必需字段: subsystem, materials, camera
3. materials 中每个条目有 part_pattern + preset/custom
4. camera 中至少1个视角存在（视角数不限于5个，按子系统 render_config.json camera 段定义）
5. preset名在15种预设中: brushed_aluminum, stainless_304, black_anodized, dark_steel,
   bronze, copper, gunmetal, anodized_blue, anodized_green, anodized_purple, anodized_red,
   peek_amber, white_nylon, black_rubber, polycarbonate_clear
6. explode 中 axis 值合法 (radial/axial/custom)
```

报告格式：`✅ 通过` 或 `❌ 第N项失败: 具体原因`

### 3. next_step — 推荐下一步

扫描项目状态后推荐：

```python
# 决策逻辑:
1. 扫描 cad/*/render_config.json 找已配置的子系统
2. 扫描 cad/*/build_all.py 找已实现的子系统
3. 扫描 cad/output/*.step, *.dxf, *.glb, *.png, *.jpg 统计产物
4. 检查 bananapro/ 中已有的渲染结果
5. 对比 docs/design/ 章节列表，找出差距

推荐优先级:
  a. 有 render_config.json 但无 build_all.py → "完成3D建模"
  b. 有 build_all.py 但无 .glb → "运行 build_all.py --render 生成GLB"
  c. 有 .glb 但无 PNG → "运行 Blender 渲染: render_3d.py"
  d. 有 PNG 但无 JPG → "运行 Gemini AI增强"
  e. 全部完成 → "选择下一个子系统" (按成熟度排序推荐)
```

### 4. new_subsys — Quick Start 3步引导

```
═══ 新子系统 Quick Start ═══

Step 1: 创建目录和配置
  mkdir cad/<subsystem_name>/
  复制模板: docs/templates/render_config_template.json → cad/<name>/render_config.json
  编辑 render_config.json 填写子系统信息（视角数、零件列表、材质等均可自定义）

Step 2: 参数化建模
  从设计文档 docs/design/NN-*.md 提取参数
  运行 /mechdesign <子系统名> 启动全流程
  (或手动创建 params.py → 3D脚本 → assembly.py → build_all.py)

Step 3: 渲染出图
  python build_all.py --render    # 生成 STEP + DXF + GLB + Blender PNG
  # 可选: AI增强
  python render_3d.py --config render_config.json   # 单独渲染
```

### 5. material — 材质预设表

列出 `render_config.py` 中的 15 种 `MATERIAL_PRESETS`：

```
═══ 15种工程材质预设 ═══

金属类 (11种):
  brushed_aluminum  — 拉丝铝 (银白, metallic=1.0, roughness=0.18, anisotropic=0.6)
  stainless_304     — 304不锈钢 (亮银, metallic=1.0, roughness=0.15)
  black_anodized    — 黑色阳极氧化铝 (深黑, metallic=0.85, roughness=0.30)
  dark_steel        — 深色钢 (深灰, metallic=0.90, roughness=0.28)
  bronze            — 青铜 (铜黄, metallic=0.90, roughness=0.25)
  copper            — 紫铜 (红铜色, metallic=1.0, roughness=0.15)
  gunmetal          — 枪灰色 (深灰, metallic=0.90, roughness=0.25)
  anodized_blue     — 蓝色阳极氧化 (蓝, metallic=0.85, roughness=0.22)
  anodized_green    — 绿色阳极氧化 (绿, metallic=0.85, roughness=0.22)
  anodized_purple   — 紫色阳极氧化 (紫, metallic=0.85, roughness=0.22)
  anodized_red      — 红色阳极氧化 (红, metallic=0.85, roughness=0.22)

工程塑料/橡胶 (4种):
  peek_amber        — PEEK琥珀色 (米黄, metallic=0, roughness=0.30, sss=0.08)
  white_nylon       — 尼龙白 (白, metallic=0, roughness=0.45)
  black_rubber      — 橡胶黑 (黑, metallic=0, roughness=0.75)
  polycarbonate_clear — 透明聚碳酸酯 (透明, metallic=0, roughness=0.05, ior=1.58)

自定义示例 (render_config.json):
  "materials": {
    "flange*": {"preset": "brushed_aluminum"},
    "sensor*": {"color": [0.2, 0.3, 0.8, 1.0], "metallic": 0.5, "roughness": 0.3}
  }
```

### 6. camera — 相机配置说明

```
═══ 相机配置 ═══

两种坐标系:

1. 球坐标 (推荐，直观):
   "type": "spherical",
   "azimuth": 45,      // 水平角度 (0=正前, 90=右侧, 180=正后)
   "elevation": 30,    // 仰角 (0=水平, 90=正上方)
   "distance_factor": 2.5  // 距离 = factor × 模型包围球半径

2. 笛卡尔坐标 (精确控制):
   "type": "cartesian",
   "x": 0.3, "y": -0.4, "z": 0.2  // 相机位置 (米)

标准5视角 (默认，可在 render_config.json 中自定义视角数和名称):
  V1_front_iso     — 正面等距 (az=35, el=25)  → 主展示图
  V2_rear_oblique  — 背面斜视 (az=215, el=20) → 背部细节
  V3_side_elevation — 侧视图 (az=90, el=0)    → 轮廓/尺寸
  V4_exploded      — 爆炸图 (az=35, el=35)    → 装配关系
  V5_ortho_front   — 正视图 (az=0, el=0)      → 正交投影

render_config.json 示例:
  "camera": {
    "V1": {"name": "V1_front_iso", "type": "spherical", "azimuth": 35, "elevation": 25, "distance_factor": 2.5},
    "V2": {"name": "V2_rear_oblique", "type": "spherical", "azimuth": 215, "elevation": 20, "distance_factor": 2.8}
  }
```

### 7. explode — 爆炸图配置

```
═══ 爆炸图配置 ═══

render_config.json 中的 explode_rules:

"explode_rules": [
  {
    "group": "station1",           // 组名
    "part_pattern": "station1_*",  // 匹配零件名
    "axis": "radial",              // radial=径向 | axial=沿Z轴 | custom
    "distance_factor": 1.5         // 爆炸距离 = factor × 零件尺寸
  },
  {
    "group": "flange",
    "part_pattern": "flange*",
    "axis": "axial",
    "distance_factor": 2.0
  },
  {
    "group": "sensor",
    "part_pattern": "uhf_*",
    "axis": "custom",
    "direction": [0.5, 0.5, 1.0], // 自定义方向向量
    "distance_factor": 1.8
  }
]

axis 类型:
  radial  — 从模型中心沿径向外推 (适合旋转体零件)
  axial   — 沿Z轴方向分离 (适合层叠结构)
  custom  — 自定义方向向量 direction: [x, y, z]

render_exploded.py 会自动绘制装配线(虚线连接器)。
```

### 8. render — 渲染执行/引导

判断用户需求后执行或引导：

```
情况A: 用户想直接渲染 → 运行命令
  # Blender Cycles渲染 (几何精确PNG)
  cd cad/<subsystem> && python build_all.py --render

  # 或单独渲染特定视角
  tools/blender/blender.exe -b -P cad/end_effector/render_3d.py -- \
    --config cad/end_effector/render_config.json

  # 爆炸图
  tools/blender/blender.exe -b -P cad/end_effector/render_exploded.py -- \
    --config cad/end_effector/render_config.json

情况B: 用户还没有GLB → 引导先构建
  1. python cad/end_effector/build_all.py  → 生成 STEP + DXF
  2. build_all.py 中 assembly.py 导出 GLB
  3. 再 --render 触发 Blender

情况C: 用户想渲染其他子系统 → 检查是否有 render_config.json
```

### 9. ai_enhance — AI增强说明

**搜索优先**：先读 `~/.config/gemini_image_config.json` 获取实际配置，再回答。

```
═══ Gemini AI 混合增强 ═══

技术路线: Blender PNG (几何精确) → Gemini --image模式 → 照片级 JPG

实际配置 (~/.config/gemini_image_config.json):
  API:    https://generativelanguage.googleapis.com/v1beta (或自定义代理)
  模型:   gemini-2.0-flash-preview-image-generation
  Key:    *** (已配置)
  超时:   120s

核心工具:
  gemini_gen.py:     gemini_gen.py (全局命令行工具)
  check_env.py:      tools/hybrid_render/check_env.py (环境检查)

prompt模板 (templates/ 目录):
  templates/prompt_enhance_unified.txt — all views (unified template, auto-switches by camera type)

模板变量 (从 render_config.json prompt_vars 填充):
  {product_name}           ← prompt_vars.product_name
  {view_description}       ← camera.V*.description
  {material_descriptions}  ← prompt_vars.material_descriptions[]

核心原则:
  1. prompt首行必须写 "Keep ALL geometry EXACTLY unchanged"
  2. 材质描述从 render_config.json 读取，不凭空编造
  3. 统一模板按相机类型自动切换（爆炸图保留间距，正交图无透视）
  4. 几何100%锁定，Gemini只"换皮"不改形状

5视角增强标准工作流:
  1. 确认5张 Blender PNG 已存在 (V1~V5)
  2. 读取 render_config.json 的 prompt_vars 字段
  3. 逐视角用统一模板填充并执行:
     python tools/hybrid_render/prompt_builder.py --config cad/<subsystem>/render_config.json --view V1
     (V1~V5 均使用 prompt_enhance_unified.txt，按 camera type 自动切换)
  4. 输出: ~6MB JPG/张, 5460×3072, 照片级影棚品质
  5. 可选: 添加元件标注 (中文/英文):
     python annotate_render.py --all --dir <输出目录> --config render_config.json --lang cn
     python annotate_render.py --all --dir <输出目录> --config render_config.json --lang en
     输出: *_labeled_cn.jpg / *_labeled_en.jpg
     注意: 中文文字用PIL+SimHei字体程序化绘制，不经过AI生成

双用途:
  PNG → 审图/加工参考 (几何100%精确)
  JPG → 展示/答辩/商业计划书 (视觉吸引力)
  JPG_labeled → 带元件标注的展示图 (答辩/报告/说明书)

标注工具 (annotate_render.py):
  依赖: Pillow (PIL)
  数据源: render_config.json 的 components 段(从设计文档BOM提取的中英文名) + labels 段(每视角每元件的2D锚点+标签位置)
  数据架构:
    "components": {"part_id": {"name_cn": "...", "name_en": "...", "bom_id": "GIS-XX-NNN"}}
    "labels": {"V1": [{"component": "part_id", "anchor": [x,y], "label": [x,y]}]}
  关键规范:
    - components 名称必须从设计文档§X.8 BOM原文提取，不可自行编造
    - labels 每视角仅标注该视角可见的元件（被遮挡的不标）
    - 坐标基于1920×1080参考分辨率，自动按实际图片尺寸缩放
  样式: dark(白字黑底) / light(黑字白底)，引线+圆点+半透明背景矩形
  字体: 中文SimHei(黑体) / 英文Arial

首次配置:
  python gemini_gen.py --config
  (交互式向导，设置 API Key / Base URL / Model)
```

### 10. troubleshoot — 排错指南

```
═══ 常见问题排错 ═══

Q: Blender 找不到 / 启动失败
A: 确认 tools/blender/blender.exe 存在，Blender 4.2 LTS portable版

Q: CadQuery import 报错
A: pip install cadquery  (需要 Python 3.10+)

Q: GLB 导出失败
A: 检查 assembly.py 是否正确生成了 Assembly 对象
   确认 cad/output/ 目录存在

Q: Blender 渲染全黑/全白
A: 检查 render_config.json 中相机距离是否合理 (distance_factor 2~4)
   检查灯光是否配置

Q: Gemini API 报错
A: 1. 检查 ~/.config/gemini_image_config.json 是否存在且格式正确
   2. 确认 api_base_url 和 model 是否匹配你的服务商
   3. 检查网络连接 (中转代理可能需要科学上网)
   4. 运行 python gemini_gen.py --config 重新配置
   5. 确认 Blender PNG 已生成

Q: DXF 打开乱码
A: 确认 FangSong 字体已安装
   ezdxf 版本需 >= 0.18

Q: render_config.json 加载失败
A: 运行 /cad-help 验证配置 检查JSON格式
   常见: 尾逗号、中文引号、缺少必需字段

Q: 材质不生效
A: 检查 part_pattern 是否匹配实际零件名
   用 python -c "import glob; print(glob.glob('cad/output/*.glb'))" 看实际文件名

Q: 渲染分辨率太低
A: render_config.json → "resolution": {"width": 1920, "height": 1080}
   默认 1280×720
```

### 11. file_struct — 文件结构

```
═══ CAD渲染管线文件结构 ═══

cad/<subsystem>/                   ← 每个子系统独立目录
├── params.py                      ← 参数单一数据源
├── *.py                           ← 3D模型脚本 (零件/装配)
├── assembly.py                    ← 总装配 → STEP + GLB
├── drawing.py                     ← 2D工程图引擎 (GB/T国标)
├── draw_*.py                      ← 各零件工程图
├── render_dxf.py                  ← DXF→PNG转换
├── render_config.json             ← 渲染配置 (材质/相机/爆炸/标注)
├── render_config.py               ← 配置引擎 (15材质预设)
├── render_3d.py                   ← Blender Cycles渲染脚本
├── render_exploded.py             ← 爆炸图渲染脚本
└── build_all.py                   ← 一键构建 (--render触发Blender)

参考实现: cad/end_effector/ (§4末端执行器, 14脚本, 8 STEP + 11 DXF)

cad/output/                    ← 输出目录
├── XX-000_assembly.step/.glb  ← 总装配
├── XX-NNN_*.step              ← 子装配STEP
├── XX-NNN-NN_*.dxf            ← 2D工程图DXF
└── *.png / *.jpg              ← 渲染结果

templates/                     ← 模板
├── render_config_template.json← 空白渲染配置模板（新子系统起点）
├── cad_spec_template.md       ← CAD Spec模板
├── prompt_enhance_unified.txt ← AI增强prompt: all views (unified template)
├── prompt_enhance.txt         ← (legacy, unused)
├── prompt_exploded.txt        ← (legacy, unused)
└── prompt_ortho.txt           ← (legacy, unused)

tools/hybrid_render/           ← 混合渲染工具
├── check_env.py               ← 环境检查脚本
└── prompt_builder.py          ← Prompt模板生成

tools/blender/blender.exe      ← Blender 4.2 LTS portable

gemini_gen.py  ← Gemini图生图全局工具 (项目外)
~/.config/gemini_image_config.json ← Gemini API配置 (key/url/model)
```

### 12. status — 子系统状态

扫描并报告：

```python
# 扫描逻辑:
1. glob cad/*/render_config.json → 已配置子系统列表
2. glob cad/*/build_all.py → 已实现子系统列表
3. glob cad/output/*.step → STEP产物数
4. glob cad/output/*.dxf → DXF产物数
5. glob cad/output/*.glb → GLB产物数
6. ls bananapro/*.png, *.jpg → 渲染结果数
7. ls docs/design/*.md → 全部设计章节

# 输出:
═══ CAD子系统状态 ═══

已完成:
  ✅ end_effector (§4末端执行器) — 8 STEP, 11 DXF, 1 GLB, 5 PNG, 5 JPG

待建模 (按设计成熟度排序):
  ⬜ §5  电气系统 (★★★★☆)
  ⬜ §2  系统总体 (★★★★☆)
  ⬜ §3  底盘导航 (★★★☆☆)
  ...

推荐: 下一步建模 §5 电气系统 (成熟度最高的未建模章节)
```

### 13. integration — 集成其他 LLM / Agent

```
═══ 跨模型集成指南 ═══

本管线分3层，其他LLM/Agent只需对接底层工具即可:

第1层: 底层Python脚本 (任何能执行shell的LLM/Agent均可调用)
  ┌──────────────────────────────────────────────────────────────┐
  │ 脚本                          用途          CLI参数            │
  │ build_all.py                 一键构建      --render           │
  │ render_3d.py (Blender内)     3D渲染        --config --view --all │
  │ render_exploded.py (Blender内) 爆炸图      --config --spread  │
  │ render_dxf.py                DXF→PNG       [file.dxf ...]     │
  │ prompt_builder.py            生成prompt     --config --type    │
  │ validate_config.py           验证配置       <config.json>      │
  │ check_env.py                 环境检查       --json             │
  │ gemini_gen.py                图生图         --image <png> "prompt" │
  └──────────────────────────────────────────────────────────────┘

第2层: 技能知识文档 (可直接作为 system prompt)
  system_prompt.md                     ← 通用系统提示词 (任何LLM)
  skill_cad_help.md                    ← 完整知识库 (15意图+动作)
  docs/cad_pipeline_agent_guide.md     ← 详细Agent集成指南

第3层: 平台适配器 (按需选装)
  adapters/claude-code/commands/       ← Claude Code 斜杠命令
  adapters/openai/functions.json       ← OpenAI Function Calling
  adapters/langchain/tools.py          ← LangChain Tool wrapper
  adapters/dify/README.md              ← Dify/Coze 知识库导入

接入示例:

  GLM-4 + Function Calling:
    system_prompt = open("tools/cad_pipeline_agent_guide.md").read()
    tools = [{"name": "run_shell", "description": "执行shell命令"}]
    → GLM读取指南 → 按流程调用 build_all.py / render_3d.py 等

  GPT-4 + Assistants API:
    上传 cad_pipeline_agent_guide.md 为知识文件
    启用 Code Interpreter → 可直接运行Python脚本

  LangChain / AutoGen / Dify:
    将知识文档注入 Agent 的 system prompt
    注册 shell tool → Agent 自主调用管线脚本

  任何 Agent 框架:
    1. 给 LLM 喂 cad_pipeline_agent_guide.md 作为知识
    2. 提供 shell/subprocess 执行能力
    3. LLM 按文档指引生成命令并执行

通用版导出:
  python install.py --platform system-prompt  # 导出通用系统提示词
  python install.py --platform openai         # 导出 OpenAI Function schema
```

### 14. parts — 零件/BOM 解析

**触发**: 用户询问某子系统有哪些零件、BOM清单、部件结构等。

**执行步骤**:

1. **定位子系统**: 从用户输入提取子系统名称，匹配 `docs/design/NN-*.md`
   - 如未指定 → 提示选择子系统
   - 常用映射: 末端/执行器→04, 电气→05, 底盘→01, 系统→02

2. **运行解析器**:
   ```bash
   python bom_parser.py docs/design/NN-*设计.md          # 树形输出
   python bom_parser.py docs/design/NN-*设计.md --json   # JSON输出
   python bom_parser.py docs/design/NN-*设计.md --summary # 仅统计
   ```

3. **展示结果**: 以树形结构输出（总成→零件层级 + 自制/外购标记 + 价格统计）

4. **无BOM时**: 如果解析器报 "未找到 BOM 表"
   - 提示: "该子系统设计文档尚无 §X.8 BOM 章节"
   - 给出模板: `docs/templates/bom_section_template.md`
   - 引导用户按模板补充

**BOM Markdown 规范**（与 §4.8 一致）:
- 表头行必须含 `料号` 和 `名称` 列
- 总成行: 料号格式 `GIS-XX-NNN`（3段，加粗），自制/外购列写 `总成`
- 零件行: 料号格式 `GIS-XX-NNN-NN`（4段），归属最近的上方总成
- 单价格式: `500元`、`100元×2`、`—`

### 15. spec — CAD Spec 生成/查看

**触发**: 用户询问 CAD_SPEC、数据提取、参数规范等。

**执行步骤**:

1. **生成 CAD_SPEC**: 对指定子系统运行提取器
   ```bash
   python cad_spec_gen.py docs/design/NN-*设计.md --config config/gisbot.json           # 单个子系统
   python cad_spec_gen.py docs/design/NN-*设计.md --config config/gisbot.json --force   # 强制重生成
   python cad_spec_gen.py --all --config config/gisbot.json                              # 全部18个子系统
   ```

2. **查看已有 CAD_SPEC**: 读取 `cad/<subsystem>/CAD_SPEC.md`

3. **检查缺失项**: 查看 §9 缺失数据报告
   - CRITICAL → 告知用户需在设计文档补充哪些内容
   - WARNING → 列出默认值，确认可否接受
   - INFO → 可选优化项

4. **模板**: `docs/templates/cad_spec_template.md`（空白模板带填写说明）

---

## 帮助面板（无参数时显示）

```
═══ /cad-help — CAD混合渲染管线帮助 ═══

直接用自然语言提问，例如:

  环境与安装
    /cad-help 需要安装什么？
    /cad-help 运行环境检查

  配置与验证
    /cad-help 验证我的render_config.json
    /cad-help 有哪些材质可以用？
    /cad-help 相机怎么配置？
    /cad-help 爆炸图怎么设置？

  工作流
    /cad-help 下一步做什么？
    /cad-help 怎么给新子系统配置？
    /cad-help 怎么渲染出图？
    /cad-help Gemini AI增强怎么用？

  零件与BOM
    /cad-help 末端执行器有哪些零件？
    /cad-help 电气系统BOM清单

  状态与排错
    /cad-help 目前进度如何？
    /cad-help 报错了怎么办？
    /cad-help 文件都在哪？

  集成与接入
    /cad-help 其他大模型怎么调用？
    /cad-help GLM/GPT怎么接入？
    /cad-help 通用Agent指南在哪？

提示: 无需记住命令语法，描述你想做的事即可。
```
