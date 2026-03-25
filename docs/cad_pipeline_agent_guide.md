# CAD 混合渲染管线 — 通用 Agent 集成指南

> 本文档面向任意 LLM / Agent 框架（GLM、GPT、Qwen、LangChain、AutoGen、Dify 等）。
> 不依赖 Claude Code，只需 **shell 执行能力** 即可调用全部工具。

---

## 1. 管线概览

```
设计文档 → [Phase 1] 设计审查 → [Phase 2] 代码生成 → [Phase 3] CadQuery构建 → [Phase 4] Blender渲染 → [Phase 5] AI增强 → [Phase 6] 标注
              ↓                      ↓                     ↓                      ↓                      ↓                    ↓
      DESIGN_REVIEW.md        params.py等脚手架       STEP/DXF/GLB           N视角PNG              照片级JPG           标注JPG
                               (Jinja2模板)           (几何精确)
```

**统一入口**: `cad_pipeline.py` 编排全部 6 阶段，支持 `--dry-run`、`--timestamp`、`--skip-*` 等标志。

```bash
python cad_pipeline.py full --subsystem end_effector --design-doc docs/design/04-*.md --timestamp
```

**能力等级**（由 `check_env.py --json` 自动检测）：

| 等级 | 能力 | 所需依赖 |
|------|------|----------|
| 5 FULL | 设计审查 + 代码生成 + CAD + 2D + 3D渲染 + AI增强 | Python + Jinja2 + CadQuery + ezdxf + matplotlib + Blender + Gemini |
| 4 RENDER | CAD + 2D + 3D渲染 | Python + CadQuery + ezdxf + matplotlib + Blender |
| 3 CAD | CAD + 2D工程图 | Python + CadQuery + ezdxf + matplotlib |
| 2 IMPORT | 仅导入GLB查看 | Blender |
| 1 MINIMAL | 仅生成prompt文本 | Python (stdlib) |

---

## 2. 环境准备

### 2.0 一键安装（推荐）

```bash
pip install cad-spec-gen        # 安装技能包（含 Jinja2）
cad-skill-setup                 # 交互式向导：语言选择 → 环境检测 → 依赖安装 → 技能注册
cad-skill-check                 # 检查环境状态
```

### 2.1 检查当前环境

```bash
cad-skill-check                                 # 推荐
cad-skill-check --json                          # 机器可读JSON
python tools/hybrid_render/check_env.py         # 传统方式（人类可读）
python tools/hybrid_render/check_env.py --json  # 传统方式（JSON）
```

### 2.2 安装依赖

```bash
# 通过 cad-skill-setup 自动安装（推荐），或手动：
pip install cadquery ezdxf matplotlib Jinja2
```

### 2.3 Blender（3D渲染需要）

下载 Blender 4.2 LTS portable 到 `tools/blender/`，或设置环境变量：
```bash
export BLENDER_PATH=/path/to/blender
```

### 2.4 Gemini AI（图片增强需要）

运行配置向导：
```bash
python gemini_gen.py --config
```
输入：API Key、API Base URL、Model 名、输出目录。
配置保存在 `~/.config/gemini_image_config.json`（路径可自定义）。

---

## 3. 工具清单与 CLI 接口

### 3.0 cad_pipeline.py — 统一管线编排器

```bash
python cad_pipeline.py <command> [OPTIONS]
```

| 子命令 | 阶段 | 说明 |
|--------|------|------|
| `spec` | Phase 1 | 设计审查 + CAD_SPEC.md 生成 |
| `codegen` | Phase 2 | 从 CAD_SPEC.md 生成 CadQuery 脚手架（Jinja2） |
| `build` | Phase 3 | CadQuery 构建 STEP + DXF + GLB |
| `render` | Phase 4 | Blender Cycles 渲染 N 视角 PNG |
| `enhance` | Phase 5 | Gemini AI 增强 |
| `annotate` | Phase 6 | PIL 标注组件名称 |
| `full` | 全部 | 依次执行 Phase 1-6，任一阶段失败即停止 |
| `status` | — | 显示所有子系统建模进度 |
| `env-check` | — | 验证依赖环境 |

常用标志：`--dry-run`（仅验证）、`--timestamp`（输出文件名加时间戳）、`--skip-spec`/`--skip-codegen`（跳过阶段）

### 3.0b codegen/ — 代码生成器（Jinja2）

```bash
python cad_pipeline.py codegen --subsystem <name> [--force]
```

从 `cad/<subsystem>/CAD_SPEC.md` 读取结构化数据，通过 `templates/*.j2` 模板生成：

| 生成器 | 输入(CAD_SPEC) | 输出 |
|--------|----------------|------|
| `codegen/gen_params.py` | §1 参数表 | `params.py` |
| `codegen/gen_build.py` | §5 BOM树 | `build_all.py`（含 `_STD_STEP_BUILDS` 标准件表） |
| `codegen/gen_parts.py` | §5 叶零件 | `station_*.py` 脚手架 |
| `codegen/gen_assembly.py` | §4连接+§5BOM+§6姿态 | `assembly.py`（含标准件导入+颜色） |
| `codegen/gen_std_parts.py` | §5 外购件 | `std_*.py` 简化几何（9类标准件） |

scaffold 模式（默认）不覆盖已有文件；`--force` 全部重新生成。

> **⚠ 重要**: codegen 生成的脚手架是**不完整的**。`params.py` 使用行号命名（如 `PARAM_L123`），需要手动改为描述性名称；`build_all.py` 的模块引用可能与实际文件名不匹配；`assembly.py` 的装配逻辑需手写。**在进入 Phase 3 BUILD 之前，必须手动完善这些文件。**

### 3.0c pipeline_config.json — 持久化配置

```json
{
  "blender_path": "D:/cad-skill/tools/blender/blender.exe",
  "cadquery_python": "python",
  "render": {"engine": "CYCLES", "samples": 512, "resolution": [1920, 1080]},
  "timestamp": {"enabled": true, "format": "%Y%m%d_%H%M"},
  "enhance": {
    "model": "nano_banana_2",
    "models": {
      "nano_banana": "gemini-2.5-flash-image",
      "nano_banana_pro": "gemini-3-pro-image-preview",
      "nano_banana_2": "gemini-3.1-flash-image"
    },
    "resolution": "2k",
    "timeout": 180
  }
}
```

管线自动读取此文件获取 Blender 路径和渲染设置。也可通过环境变量覆盖：
- `BLENDER_PATH` — Blender 可执行文件路径
- `CAD_OUTPUT_DIR` — 输出目录
- `GEMINI_GEN_PATH` — Gemini 脚本路径

### 3.1 build_all.py — 一键构建

```bash
python cad/end_effector/build_all.py           # 仅构建 STEP + DXF
python cad/end_effector/build_all.py --render  # 构建 + Blender渲染
```

- **输入**: `params.py`（参数）、各零件 `.py` 脚本
- **输出**: `cad/output/` 下 8 STEP + 11 DXF + 1 GLB（+ PNG if --render）

### 3.2 render_3d.py — Blender Cycles 渲染

```bash
tools/blender/blender.exe -b -P cad/end_effector/render_3d.py -- [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--glb <PATH>` | GLB文件路径 | 自动检测 cad/output/EE-000_assembly.glb |
| `--config <PATH>` | render_config.json | 无（使用硬编码） |
| `--view <V1\|V2\|V3\|V5>` | 渲染单个视角 | V1 |
| `--all` | 渲染全部标准视角 | false |
| `--samples <INT>` | Cycles采样数 | 256 |
| `--resolution <W> <H>` | 输出分辨率 | 1920 1080 |
| `--output-dir <PATH>` | 输出目录 | cad/output/renders/ |

**输出**: V1_front_iso.png, V2_rear_oblique.png, V3_side_elevation.png, V5_ortho_front.png

### 3.3 render_exploded.py — 爆炸图渲染

```bash
tools/blender/blender.exe -b -P cad/end_effector/render_exploded.py -- [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--glb <PATH>` | GLB文件路径 | 自动检测 |
| `--config <PATH>` | render_config.json | 无 |
| `--spread <FLOAT>` | 径向爆炸距离(mm) | 70 |
| `--z-spread <FLOAT>` | Z轴爆炸距离(mm) | 50 |
| `--samples <INT>` | Cycles采样数 | 128 |
| `--resolution <W> <H>` | 输出分辨率 | 1920 1080 |

**输出**: V4_exploded.png

### 3.4 render_dxf.py — DXF 转 PNG

```bash
python cad/end_effector/render_dxf.py                        # 渲染全部DXF
python cad/end_effector/render_dxf.py file1.dxf file2.dxf    # 渲染指定DXF
```

- **输出**: 同目录下同名 .png

### 3.5 prompt_builder.py — Prompt 模板生成

```bash
python tools/hybrid_render/prompt_builder.py --config <render_config.json> [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--config <PATH>` | render_config.json（必需） | — |
| `--type <enhance\|exploded\|ortho>` | 模板类型 | enhance |
| `--list` | 列出可用模板类型 | — |

**输出**: prompt 文本到 stdout

### 3.6 validate_config.py — 配置验证

```bash
python tools/hybrid_render/validate_config.py <render_config.json>
```

- 退出码 0=通过, 1=失败
- 检查: 材质/相机/爆炸规则/prompt变量

### 3.7 bom_parser.py — BOM 解析器

```bash
python tools/bom_parser.py docs/design/04-末端执行机构设计.md           # 树形输出
python tools/bom_parser.py docs/design/04-末端执行机构设计.md --json    # JSON输出
python tools/bom_parser.py docs/design/04-末端执行机构设计.md --summary # 仅统计
```

- **输入**: 设计文档 Markdown (含 §X.8 BOM 表)
- **输出**: 零件树 / JSON / 统计摘要
- **解析规则**: 表头含 `料号`+`名称`、总成行3段加粗、零件行4段、单价支持 `元×N`

### 3.8 gemini_gen.py — Gemini 图生图

```bash
# 文生图
python gemini_gen.py "描述文本"

# 图生图（混合增强）
python gemini_gen.py --image base.png "增强指令"

# 指定模型
python gemini_gen.py --image base.png --model gemini-3.1-flash-image "增强指令"

# 查看配置
python gemini_gen.py --show-config

# 重新配置
python gemini_gen.py --config
```

- **配置文件**: `~/.config/gemini_image_config.json`（路径可自定义）
- **输出**: `<output_dir>/gemini_YYYYMMDD_HHMMSS.png`（直接调用时）
- **管线调用时**: `cad_pipeline.py enhance` 自动重命名为 `V*_视图名_YYYYMMDD_HHMM_enhanced.ext`（与源 PNG 同目录）
- **模型选择**: `pipeline_config.json` 的 `enhance` 段配置模型别名→API model ID 映射

#### 标准件增强

prompt 模板包含 `{standard_parts_description}` 占位符，由 `render_config.json` 的 `standard_parts` 数组填充：

```json
"standard_parts": [
  {"visual_cue": "Small cylinder (Φ22×68mm) under flange", "real_part": "Maxon ECX motor, silver housing..."},
  {"visual_cue": "Annular rings at bearing locations", "real_part": "MR105ZZ ball bearing, chrome steel..."}
]
```

Gemini 收到简化几何的位置描述 + 真实零件外观描述，将简化形状增强为逼真外观。

---

## 4. render_config.json 配置格式

```json
{
  "subsystem_id": "EE",
  "subsystem_name": "末端执行器",
  "glb_path": "cad/output/EE-000_assembly.glb",
  "materials": [
    {"part_pattern": "flange*", "preset": "brushed_aluminum"},
    {"part_pattern": "peek_ring*", "preset": "peek_natural"},
    {"part_pattern": "sensor*", "custom": {"color": [0.2, 0.3, 0.8, 1.0], "metallic": 0.5, "roughness": 0.3}}
  ],
  "cameras": {
    "V1_front_iso": {"type": "spherical", "azimuth": 35, "elevation": 25, "distance_factor": 2.5},
    "V2_rear_oblique": {"type": "spherical", "azimuth": 215, "elevation": 20, "distance_factor": 2.8},
    "V3_side_elevation": {"type": "spherical", "azimuth": 90, "elevation": 0, "distance_factor": 2.5},
    "V4_exploded": {"type": "spherical", "azimuth": 35, "elevation": 35, "distance_factor": 3.5},
    "V5_ortho_front": {"type": "spherical", "azimuth": 0, "elevation": 0, "distance_factor": 2.5}
  },
  "explode_rules": [
    {"group": "station1", "part_pattern": "station1_*", "axis": "radial", "distance_factor": 1.5}
  ],
  "prompt_vars": {
    "product_name": "GIS局放检测末端执行器",
    "material_lines": "铝合金法兰(银白), PEEK绝缘环(米黄), 不锈钢弹簧(亮银)"
  },
  "resolution": {"width": 1920, "height": 1080},
  "standard_parts": [
    {"visual_cue": "Small cylinder under flange", "real_part": "Maxon ECX motor, silver aluminum housing"},
    {"visual_cue": "Annular rings at bearing seats", "real_part": "MR105ZZ ball bearing, chrome steel"}
  ]
}
```

### 15种材质预设名

| 金属 | 工程塑料 | 其他 |
|------|----------|------|
| brushed_aluminum | peek_natural | rubber_black |
| polished_steel | nylon_white | glass_clear |
| black_anodized | abs_dark_gray | ceramic_white |
| cast_iron | | carbon_fiber |
| brass, copper, titanium, raw_steel | | |

---

## 5. 典型工作流

### 5.1 从零构建一个子系统

```bash
# Step 1: 检查环境
python cad_pipeline.py env-check

# Step 2: 一键全流程（自动 6 阶段）
python cad_pipeline.py full --subsystem end_effector \
  --design-doc docs/design/04-末端执行机构设计.md --timestamp
# → 输出: DESIGN_REVIEW.md + CAD_SPEC.md + *.py脚手架 + STEP/DXF/GLB + PNG + JPG

# 或者分步执行:
# Step 2a: 设计审查 + 规范化
python cad_pipeline.py spec --design-doc docs/design/04-*.md --auto-fill

# Step 2b: 代码生成
python cad_pipeline.py codegen --subsystem end_effector

# Step 2c: 手动完善几何（可选）
# 编辑 cad/end_effector/station_*.py 完善零件细节

# Step 2d: 构建 + 渲染
python cad_pipeline.py build --subsystem end_effector
python cad_pipeline.py render --subsystem end_effector --timestamp

# Step 2e: AI增强 (可选)
python cad_pipeline.py enhance --dir cad/output/renders
```

### 5.2 仅渲染（已有GLB）

```bash
# 标准5视角
tools/blender/blender.exe -b -P cad/end_effector/render_3d.py -- \
  --config cad/end_effector/render_config.json --all

# 爆炸图
tools/blender/blender.exe -b -P cad/end_effector/render_exploded.py -- \
  --config cad/end_effector/render_config.json
```

### 5.3 仅AI增强（已有PNG）

```bash
python gemini_gen.py --image V1_front_iso.png \
  "Keep ALL geometry EXACTLY. Photorealistic studio rendering..."
```

---

## 6. Agent 接入模板

### 6.1 System Prompt 模板

```
你是一个 CAD 渲染助手。你可以执行 shell 命令来操作以下工具:

- cad_pipeline.py: 统一管线编排器 (spec/codegen/build/render/enhance/annotate/full)
- build_all.py: 参数化3D建模，生成 STEP/DXF/GLB
- render_3d.py: Blender Cycles CPU 渲染 N视角PNG
- render_exploded.py: 爆炸图渲染
- render_dxf.py: DXF工程图转PNG
- codegen/gen_*.py: 从 CAD_SPEC.md 自动生成 CadQuery 脚手架（Jinja2 模板）
- prompt_builder.py: 生成 Gemini AI增强 prompt
- gemini_gen.py: Gemini 图生图
- validate_config.py: 验证 render_config.json
- check_env.py: 环境能力检测

工作目录: <YOUR_PROJECT_ROOT>
配置文件: pipeline_config.json（Blender路径、渲染参数）
子系统配置: cad/<subsystem>/render_config.json

推荐使用 cad_pipeline.py full 一键执行全流程。
```

### 6.2 Function/Tool 定义（OpenAI 格式）

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "run_shell",
        "description": "执行 shell 命令",
        "parameters": {
          "type": "object",
          "properties": {
            "command": {"type": "string", "description": "要执行的命令"}
          },
          "required": ["command"]
        }
      }
    }
  ]
}
```

### 6.3 LangChain 示例

```python
from langchain.agents import initialize_agent
from langchain.tools import ShellTool

guide = open("tools/cad_pipeline_agent_guide.md").read()
agent = initialize_agent(
    tools=[ShellTool()],
    llm=your_llm,
    agent_type="zero-shot-react-description",
    system_message=guide
)
agent.run("帮我渲染末端执行器的5个视角")
```

---

## 7. 目录结构

```
cad_pipeline.py                    ← 统一管线编排器 (6 阶段)
cad_paths.py                       ← 路径解析（Blender、子系统、输出目录）
pipeline_config.json               ← 持久化配置（Blender路径、渲染参数、时间戳）

codegen/                           ← 代码生成器（Jinja2）
├── gen_params.py                  ← §1 参数表 → params.py
├── gen_build.py                   ← §5 BOM → build_all.py（含标准件构建表）
├── gen_parts.py                   ← §5 叶零件 → station_*.py 脚手架
├── gen_assembly.py                ← §4+§5+§6 → assembly.py（含标准件）
└── gen_std_parts.py               ← §5 外购件 → std_*.py 简化几何

templates/                         ← Jinja2 模板
├── params.py.j2                   ← params.py 生成模板
├── build_all.py.j2                ← build_all.py 生成模板
├── part_module.py.j2              ← 零件模块脚手架模板
├── assembly.py.j2                 ← 装配脚手架模板（含标准件导入+颜色）
├── std_part.py.j2                 ← 标准件 CadQuery 简化几何模板
├── cad_spec_template.md           ← CAD_SPEC 输出格式模板
├── design_review_template.md      ← 设计审查输出模板
├── prompt_enhance.txt             ← AI prompt: 标准视角 (V1-V3)
├── prompt_exploded.txt            ← AI prompt: 爆炸图 (V4)
└── prompt_ortho.txt               ← AI prompt: 正交投影 (V5)

cad/end_effector/              ← 参考实现 (§4末端执行器)
├── params.py                  ← 参数数据源
├── tolerances.py              ← 公差定义
├── bom.py                     ← BOM清单
├── flange.py                  ← 法兰3D
├── station1~4_*.py            ← 各工位3D
├── drive_assembly.py          ← 驱动总成
├── assembly.py                ← 总装配 → STEP + GLB
├── drawing.py                 ← 2D引擎 (GB/T国标)
├── draw_three_view.py         ← 三视图模板
├── draw_*.py                  ← 各零件工程图
├── render_config.json         ← 渲染配置
├── render_config.py           ← 配置引擎 (15材质预设)
├── render_3d.py               ← Blender渲染
├── render_exploded.py         ← 爆炸图渲染
├── render_dxf.py              ← DXF→PNG
└── build_all.py               ← 一键构建

tools/hybrid_render/           ← 混合渲染工具
├── check_env.py               ← 环境检查
├── prompt_builder.py          ← Prompt生成
└── validate_config.py         ← 配置验证

tools/bom_parser.py            ← BOM解析器 (设计文档→零件树JSON)

tools/blender/blender.exe      ← Blender 4.2 LTS
gemini_gen.py                  ← Gemini图生图工具（用户自行配置路径）

cad/output/                    ← 所有输出
├── *.step, *.glb              ← 3D模型
├── *.dxf                      ← 2D工程图
└── renders/*.png              ← 渲染结果
```
