# /cad-help — CAD 混合渲染管线交互式帮助

一个自然语言驱动的 CAD 渲染管线助手。无需记忆命令语法，用中文提问即可完成环境检查、配置验证、渲染出图、排错等全部操作。

## 快速开始

```
/cad-help                        # 查看帮助面板
/cad-help 需要安装什么？           # 环境检查
/cad-help 下一步做什么？           # 智能推荐
/cad-help 有哪些材质可以用？       # 查看15种PBR预设
/cad-help 末端执行器有哪些零件？    # 零件/BOM解析
/cad-help 其他大模型怎么调用？     # 跨模型集成指南
```

## 功能总览

`/cad-help` 支持 **16 种意图**，覆盖 CAD 混合渲染管线全生命周期：

| # | 意图 | 触发示例 | 说明 |
|---|------|----------|------|
| 1 | 环境检查 | "需要安装什么？" "运行环境" | 逐项检测 Python / CadQuery / Blender / Gemini 等 7 项依赖 |
| 2 | 验证配置 | "验证配置" "config对不对" | 校验 render_config.json 的 6 项完整性 |
| 3 | 下一步 | "下一步做什么？" "怎么继续" | 扫描项目产物，按优先级推荐下一步操作 |
| 4 | 新子系统 | "怎么开始新子系统？" "init" | Quick Start引导 + `init` 脚手架命令 |
| 5 | 材质 | "有哪些材质？" "颜色/外观" | 列出 15 种 PBR 工程材质预设 + 自定义示例 |
| 6 | 相机 | "相机怎么配置？" "视角" | 球坐标 / 笛卡尔坐标 + 5 标准视角说明 |
| 7 | 爆炸图 | "爆炸图怎么设置？" | radial / axial / custom 三种爆炸方式配置 |
| 8 | 渲染 | "怎么渲染？" "出图" | 自动判断状态，运行 Blender 或引导补全前置步骤 |
| 9 | AI增强 | "Gemini怎么用？" "照片级" | Gemini 图生图混合增强流程 + prompt 模板 |
| 10 | 排错 | "报错了" "失败/不行" | 8 类常见问题排错指南 |
| 11 | 文件结构 | "文件都在哪？" | 渲染管线完整目录树 |
| 12 | 状态 | "目前进度如何？" | 扫描各子系统 STEP/DXF/GLB/PNG/JPG 产物统计 |
| 13 | 集成 | "其他大模型怎么调用？" | GLM / GPT / LangChain 等跨框架接入指南 |
| 14 | 零件/BOM | "有哪些零件？" "BOM清单" | 从设计文档自动提取零件树、统计自制/外购/成本 |
| 15 | CAD Spec | "生成spec" "提取参数" | 运行 cad_spec_gen.py 生成 CAD_SPEC.md |
| 16 | 设计审查 | "审查设计" "检查设计" "review" | 工程审查：力学/装配/材质/完整性 → DESIGN_REVIEW.md |

### v2.3.0 新增能力

- **特征提取**：交叉引用 §2 公差、§3 紧固件、§4 连接矩阵、§8 装配序列，自动提取每个零件的孔/槽特征
- **剖面叠加**：含内部特征的零件自动在左视图叠加 A-A 剖面线（孔处不画剖面线，GB/T 4457.5）
- **位置尺寸**：俯视图自动标注孔心到基准边的距离（GB/T 4458.4）
- **正交优先引出线**：孔径标注引出线默认走 0°/90°/180°/270°（原为 45°/135°）
- **动态技术要求位置**：技术要求位置根据布局计算，放在视图下方空白处（原硬编码左上角）
- **材质外观数据源归一**：`render_config.py` 的 `MATERIAL_PRESETS` 是 Blender PBR 和 AI prompt 的唯一数据源
- **视角感知材质描述**：AI prompt 根据相机仰角自动调整菲涅尔/镜面/漫反射描述重点
- **material_type → preset 自动回退**：render_config.json 无材质时从 params.py 自动推导
- **渲染 pass 预留**：可选输出 depth/normal/diffuse pass（schema 已就绪，默认关闭）

## 管线架构

```
┌─────────────────────────────────────────────────────────────┐
│                    CAD 混合渲染管线                           │
│                                                              │
│  设计文档 (.md)                                              │
│      ↓ cad_spec_gen.py --review（可选，推荐）                 │
│  DESIGN_REVIEW.md（A.力学 / B.装配含B5-B8连接检查 /          │
│    C.材质 / D.完整性 审查报告）                                │
│      ↓ 用户选择：「继续审查」↻ /「自动补全」(--auto-fill) /     │
│        「下一步」↓                                             │
│      ↓ 参数提取                                              │
│  CadQuery 参数化建模 → STEP + DXF + GLB                     │
│      ↓                                                       │
│  Blender Cycles CPU 渲染 → N 视角 PNG（几何 100% 精确，默认5个）    │
│      ↓                                                       │
│  Gemini AI 增强 → 照片级 JPG（仅换皮，不改几何）              │
│                                                              │
│  PNG → 审图 / 加工参考                                       │
│  JPG → 展示 / 答辩 / 商业计划书                              │
└─────────────────────────────────────────────────────────────┘
```

## 环境要求

| 组件 | 版本要求 | 用途 | 必需？ |
|------|----------|------|--------|
| Python | 3.10+ | 运行所有脚本 | 是 |
| CadQuery | 2.x | 参数化 3D 建模 | 是 |
| ezdxf | 0.18+ | 2D 工程图 (DXF) | 是 |
| matplotlib | 3.x | DXF → PNG 转换 | 是 |
| Blender | 4.x LTS | Cycles CPU 渲染 | 3D 渲染需要 |
| Gemini API | — | AI 图片增强 | AI 增强需要 |
| 仿宋字体 | — | GB/T 国标工程图 | 2D 图纸需要 |

运行 `/cad-help 运行环境检查` 可一键检测全部依赖。

## 工具脚本一览

```
cad/end_effector/
├── build_all.py           一键构建 (--render 触发 Blender)
├── render_3d.py           Blender 5 视角渲染 (--config --all)
├── render_exploded.py     爆炸图渲染 (--config --spread)
├── render_dxf.py          DXF → PNG 转换
├── render_config.json     渲染配置 (材质/相机/爆炸规则/标准件描述)
└── render_config.py       配置引擎 (15 种材质预设)

codegen/                   代码生成器（从 CAD_SPEC.md 生成脚手架）
├── gen_params.py          §1 参数表 → params.py
├── gen_build.py           §5 BOM树 → build_all.py（含标准件构建表）
├── gen_parts.py           §5 叶零件 → station_*.py 脚手架
├── gen_assembly.py        §4+§5+§6 → assembly.py（含标准件）
└── gen_std_parts.py       §5 外购件 → std_*.py 简化几何（9类）

tools/hybrid_render/
├── check_env.py           环境检查 (--json)
├── validate_config.py     配置验证 (<config.json>)
└── prompt_builder.py      Prompt 模板生成 (--config --type)

tools/
└── bom_parser.py          BOM 零件树解析 (--json --summary)

# Gemini AI 工具（用户自行配置路径）
# gemini_gen.py             Gemini 图生图 (--image png --model <id> "prompt")
```

## 15 种材质预设

| 分类 | 预设名 | 中文 | 外观 |
|------|--------|------|------|
| 金属 | brushed_aluminum | 拉丝铝 | 银白, metallic=1.0 |
| | stainless_304 | 不锈钢304 | 亮银 |
| | black_anodized | 黑色阳极氧化铝 | 深黑 |
| | dark_steel | 暗钢 | 深灰 |
| | bronze | 青铜 | 金棕 |
| | copper | 紫铜 | 红铜色 |
| | gunmetal | 枪灰 | 深蓝灰 |
| | anodized_blue | 蓝色阳极氧化 | 金属蓝 |
| | anodized_green | 绿色阳极氧化 | 金属绿 |
| | anodized_purple | 紫色阳极氧化 | 金属紫 |
| | anodized_red | 红色阳极氧化 | 金属红 |
| 塑料 | peek_amber | PEEK 琥珀色 | 琥珀, 半透明 |
| | white_nylon | 尼龙白 | 白 |
| | black_rubber | 橡胶黑 | 黑, roughness=0.85 |
| | polycarbonate_clear | 聚碳酸酯透明 | 透明 |

## 典型工作流

### 从零渲染一个子系统

> **示例：末端执行器子系统** — 替换路径为你的子系统。

```bash
# 0. 脚手架新子系统（如果是全新项目）
python cad_pipeline.py init --subsystem my_device --name-cn 我的设备 --prefix GIS-MD
# → 自动生成: output/my_device/render_config.json, params.py, docs/design/XX-my_device.md

# 1. 检查环境
python tools/hybrid_render/check_env.py

# 2. 构建 + 渲染
python cad/end_effector/build_all.py --render
# → 输出: 8 STEP + 11 DXF + 1 GLB + 5 PNG

# 3. AI 增强 (可选) — 使用prompt模板
python gemini_gen.py \
  --image cad/output/renders/V1_front_iso.png \
  "Keep ALL geometry EXACTLY unchanged. Apply photorealistic materials..."
# → 输出: 照片级 JPG (~6MB, 5460×3072)
```

### AI 增强工作流（所有配置的视角）

Blender渲染完成后，将所有PNG增强为照片级JPG：

```bash
# 步骤1: 读取 render_config.json 中的材质描述
cat cad/end_effector/render_config.json | jq '.prompt_vars'

# 所有视角 → templates/prompt_enhance_unified.txt（统一模板）
# prompt_data_builder.py 从 params.py 自动生成装配/材质数据
python tools/hybrid_render/prompt_builder.py --config cad/end_effector/render_config.json --view V1
```

**核心原则：**
- 视角锁定（v2.1）：prompt 首行 "Preserve EXACT camera angle, viewpoint, framing"；每视角写入计算方位角/仰角
- 几何锁定：Gemini 靠 prompt 约束；ComfyUI 靠 ControlNet 硬约束
- 多视角一致性：源图第一位（锁构图）+ 参考图第二位（仅风格）+ V1-anchor + 源图不压缩（≤4MB）
- 材质描述来源于 `render_config.json` 的 `prompt_vars` 字段
- 标准件增强描述来源于 `render_config.json` 的 `standard_parts` 数组（`{standard_parts_description}` 占位符）
- Layout 感知：非 radial 子系统不注入硬编码零件描述
- 1套统一模板按相机类型自动切换（标准/爆炸/正交）
- 模型选择：`pipeline_config.json` 的 `enhance.model` 字段选择 Gemini 模型别名
- 时间戳版本：文件命名 `V*_视图名_YYYYMMDD_HHMM_enhanced.ext`，防止覆盖历史版本
- 双输出：PNG用于工程审图/加工参考，JPG用于答辩/展示/商业计划书

### 元件标注（中文/英文）

AI增强完成后，可通过PIL程序化添加元件名称标注（不经过AI生成中文）：

```bash
# 单张图标注
python annotate_render.py V1_enhanced.jpg \
  --config cad/end_effector/render_config.json --lang cn

# 批量标注所有视角（中文）
python annotate_render.py --all --dir assets/images/mechanical \
  --config cad/end_effector/render_config.json --lang cn

# 批量标注所有视角（英文）
python annotate_render.py --all --dir assets/images/mechanical \
  --config cad/end_effector/render_config.json --lang en
```

标注数据来源：
- `render_config.json` 中 `components` 段：元件ID→中英文名+BOM编号（从设计文档§X.8 BOM提取）
- `render_config.json` 中 `labels` 段：每视角可见元件的引线端点坐标 `label:[x,y]`
- **锚点坐标**由渲染阶段自动生成（`render_label_utils.py` 通过 Object Index Mask 计算零件可见像素质心），写入 `<VN>_<name>_labels.json` sidecar 文件。annotate 阶段优先使用 sidecar 中的锚点，确保锚点始终落在零件上

### 单独渲染（已有 GLB）

```bash
# 全部标准视角
tools/blender/blender.exe -b -P cad/end_effector/render_3d.py -- \
  --config cad/end_effector/render_config.json --all

# 爆炸图
tools/blender/blender.exe -b -P cad/end_effector/render_exploded.py -- \
  --config cad/end_effector/render_config.json
```

## 跨模型集成

本管线的底层工具是纯 Python 脚本，**任何能执行 shell 命令的 LLM / Agent 都可以调用**。

| 框架 | 接入方法 |
|------|----------|
| GLM-4 | system prompt 加载通用指南 + Function Calling `run_shell` |
| GPT-4 / Assistants | 上传知识文件 + Code Interpreter |
| LangChain | `ShellTool()` + 通用指南作为 system_message |
| Dify | 知识库导入 + 代码执行节点 |

通用 Agent 集成指南：[`tools/cad_pipeline_agent_guide.md`](tools/cad_pipeline_agent_guide.md)

## 相关命令

| 命令 | 说明 |
|------|------|
| `/cad-help` | 本帮助（自然语言 CAD 管线助手） |
| `/mechdesign` | 参数化机械子系统全流程 |
| `/text-to-image` | Gemini 文生图 / 图生图 |
| `gishelp` | 项目总助手 |

## 许可

本项目为 GISBOT GIS 局放检测机器人的配套 CAD 工具链。
