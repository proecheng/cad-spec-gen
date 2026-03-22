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

`/cad-help` 支持 **14 种意图**，覆盖 CAD 混合渲染管线全生命周期：

| # | 意图 | 触发示例 | 说明 |
|---|------|----------|------|
| 1 | 环境检查 | "需要安装什么？" "运行环境" | 逐项检测 Python / CadQuery / Blender / Gemini 等 7 项依赖 |
| 2 | 验证配置 | "验证配置" "config对不对" | 校验 render_config.json 的 6 项完整性 |
| 3 | 下一步 | "下一步做什么？" "怎么继续" | 扫描项目产物，按优先级推荐下一步操作 |
| 4 | 新子系统 | "怎么开始新子系统？" | Quick Start 3 步引导 |
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

## 管线架构

```
┌─────────────────────────────────────────────────────────────┐
│                    CAD 混合渲染管线                           │
│                                                              │
│  设计文档 (.md)                                              │
│      ↓ 参数提取                                              │
│  CadQuery 参数化建模 → STEP + DXF + GLB                     │
│      ↓                                                       │
│  Blender Cycles CPU 渲染 → 5 视角 PNG（几何 100% 精确）       │
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
├── render_config.json     渲染配置 (材质/相机/爆炸规则)
└── render_config.py       配置引擎 (15 种材质预设)

tools/hybrid_render/
├── check_env.py           环境检查 (--json)
├── validate_config.py     配置验证 (<config.json>)
└── prompt_builder.py      Prompt 模板生成 (--config --type)

tools/
└── bom_parser.py          BOM 零件树解析 (--json --summary)

# Gemini AI 工具（用户自行配置路径）
# gemini_gen.py             Gemini 图生图 (--image png "prompt")
```

## 15 种材质预设

| 分类 | 预设名 | 中文 | 外观 |
|------|--------|------|------|
| 金属 | brushed_aluminum | 拉丝铝 | 银白, metallic=1.0 |
| | polished_steel | 抛光钢 | 亮银 |
| | black_anodized | 黑色阳极氧化铝 | 深黑 |
| | cast_iron | 铸铁 | 深灰 |
| | brass | 黄铜 | 金黄 |
| | copper | 紫铜 | 红铜色 |
| | titanium | 钛合金 | 浅灰 |
| | raw_steel | 未处理钢 | 灰 |
| 塑料 | peek_natural | PEEK 本色 | 米黄 |
| | nylon_white | 尼龙白 | 白 |
| | abs_dark_gray | ABS 深灰 | 深灰 |
| 其他 | rubber_black | 橡胶黑 | 黑, roughness=0.85 |
| | glass_clear | 透明玻璃 | 透明 |
| | ceramic_white | 陶瓷白 | 白 |
| | carbon_fiber | 碳纤维 | 深黑 |

## 典型工作流

### 从零渲染一个子系统

```bash
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

### AI 增强工作流（5视角完整流程）

Blender渲染完成后，将5张PNG增强为照片级JPG：

```bash
# 步骤1: 读取 render_config.json 中的材质描述
cat cad/end_effector/render_config.json | jq '.prompt_vars'

# 步骤2: 填充prompt模板并逐视角执行
# V1/V2/V3 → templates/prompt_enhance.txt（标准视角）
python gemini_gen.py --image V1_front_iso.png \
  "Keep ALL geometry EXACTLY unchanged. This is a front-left isometric view
   of a precision robotic end effector. Apply photorealistic materials:
   - 银色法兰: 拉丝铝合金 7075-T6
   - 琥珀色环: PEEK工程塑料，半透明
   - 蓝/绿/铜/紫工位: 阳极氧化铝
   Studio lighting, neutral gradient background. 8K quality."

# V4 → templates/prompt_exploded.txt（爆炸图，保留间距）
python gemini_gen.py --image V4_exploded.png \
  "Keep ALL geometry EXACTLY unchanged. Exploded view — keep gaps visible..."

# V5 → templates/prompt_ortho.txt（正交图，无透视畸变）
python gemini_gen.py --image V5_ortho_front.png \
  "Keep ALL geometry EXACTLY unchanged. Front orthographic projection..."
```

**核心原则：**
- Prompt首行必须写 "Keep ALL geometry EXACTLY unchanged"
- 材质描述来源于 `render_config.json` 的 `prompt_vars` 字段
- 3套模板对应不同视角类型（标准/爆炸/正交）
- 输出：每张约6MB JPG，照片级影棚品质
- 双输出：PNG用于工程审图/加工参考，JPG用于答辩/展示/商业计划书

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
