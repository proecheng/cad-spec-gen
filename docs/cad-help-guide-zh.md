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

`/cad-help` 支持 **17 种意图**，覆盖 CAD 混合渲染管线全生命周期：

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
| 9 | AI增强 | "怎么增强？" "照片级" "哪个后端？" | 4种后端AI增强：gemini / fal / comfyui / engineering |
| 10 | 排错 | "报错了" "失败/不行" | 8 类常见问题排错指南 |
| 11 | 文件结构 | "文件都在哪？" | 渲染管线完整目录树 |
| 12 | 状态 | "目前进度如何？" | 扫描各子系统 STEP/DXF/GLB/PNG/JPG 产物统计 |
| 13 | 集成 | "其他大模型怎么调用？" | GLM / GPT / LangChain 等跨框架接入指南 |
| 14 | 零件/BOM | "有哪些零件？" "BOM清单" | 从设计文档自动提取零件树、统计自制/外购/成本 |
| 15 | CAD Spec | "生成spec" "提取参数" | 运行 cad_spec_gen.py 生成 CAD_SPEC.md |
| 16 | 设计审查 | "审查设计" "检查设计" "review" | 工程审查：力学/装配/材质/完整性 → DESIGN_REVIEW.md |
| 17 | Photo3D 契约出图 | "照片级一键出图" "photo3d" "检查照片级门禁" | 普通用户优先运行 `python cad_pipeline.py project-guide --subsystem <name> --design-doc <path>` 写 `PROJECT_GUIDE.json`；已有 active run 后可运行 `render-visual-check` 写 `RENDER_VISUAL_REGRESSION.json`，运行 `render-quality-check` 写 `RENDER_QUALITY_REPORT.json`，再进入 `photo3d-run` 验证当前 `run_id` 的契约链并写 `PHOTO3D_RUN.json` |

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
- **四后端增强 (v2.3)**：AI增强支持四种后端 — engineering（Blender PBR直出JPG，免费，完美几何，**推荐用于精确工程图**）、gemini（云端，~$0.02/张，**推荐用于外观展示**）、fal（fal.ai Flux ControlNet，~$0.20/张，**实验性** — 对简化CAD几何效果不佳）、comfyui（本地GPU，免费，本版本未测试）。CLI：`--backend gemini|fal|comfyui|engineering`

### v2.5.0 新增能力 — 装配定位增强

- **零件级定位（§6.3）**：从设计文档的 → 语法中提取串行堆叠链，通过方向感知算法计算每个零件的 Z 偏移量。支持 axial_stack（轴向堆叠）、radial_extend（径向延伸）、side_mount（侧挂）、coaxial（同轴）、lateral_array（横向阵列）五种模式。
- **零件包络提取（§6.4）**：从 5 个来源采集零件尺寸（零件参数表、正文叙述、BOM 材料列、视觉 ID 表、全局参数），按优先级合并去重。
- **装配约束（§9）**：将设计文档中的负向约束分类为装配排除项（不属于本装配体的零件）和方向锁定项（方向约束）。
- **增强审查器**：新增 B10（孤立装配体）、B11（缺少包络尺寸）、B12（定位覆盖率 < 50%）三项审查检查。
- **排除标记**：在负向约束中被标注为"不在本体上"的装配体，将自动从代码生成中排除。

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
│  AI 增强（4种后端）→ 照片级 JPG（仅换皮，不改几何）          │
│    gemini | fal | comfyui | engineering（自动检测）           │
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
| Gemini API | — | AI 图片增强（gemini后端） | gemini后端需要 |
| FAL_KEY 环境变量 | — | fal.ai Flux ControlNet（fal后端） | fal后端需要 |
| ComfyUI | localhost:8188 | 本地 ControlNet（comfyui后端） | comfyui后端需要 |
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

### Photo3D 一键照片级契约门禁

普通用户和大模型优先从只读项目向导开始：

```bash
python cad_pipeline.py project-guide --subsystem <name> --design-doc <path>
```

`project-guide` 会写出 `PROJECT_GUIDE.json`，在 `init`、`spec`、`codegen`、`build --render`、`photo3d-run` 之间选择下一条安全命令。它只读取显式子系统、可选设计文档、固定 `CAD_SPEC.md` / codegen 哨兵文件，以及显式解析的 `ARTIFACT_INDEX.json` 当前 active run；不会扫描目录猜最新文件，不会修改管线状态，不会接受 baseline，也不会运行增强。当前 active run 已到 `ready_for_enhancement` 时，`PROJECT_GUIDE.json` 可附带只读 provider 选择：`ordinary_user_options` 是普通用户可读选项，包含“默认 / 本地工程预览 / 云增强”等标题、说明、适用场景、是否需要配置、`provider_health` 健康状态，以及 `photo3d-handoff --provider-preset <id>` 预览命令；`provider_wizard` 则把这些选项组织成 UI/大模型可直接展示的步骤、默认项、预览动作和健康摘要。所有选项来自白名单 provider preset；`provider_health` 只检查本地配置/依赖存在性，不运行增强、不扫描输出目录、不改状态，也不会暴露环境变量名、key 值、URL、endpoint 或 secret。它不会接受任意 backend、URL、API key、模型名或 JSON argv 注入，wizard 本身也不会追加 `--confirm` 或执行增强。

已有 active run 后，使用多轮向导：

```bash
python cad_pipeline.py photo3d-run --subsystem <name>
```

它会按当前 `active_run_id` 连续运行 `photo3d` 门禁和 `photo3d-autopilot`，并写出 `PHOTO3D_RUN.json`。向导只推进到下一处需要用户决策的位置：`needs_baseline_acceptance`、`ready_for_enhancement`、`needs_user_input`、`needs_manual_review`、`execution_failed` 或 `loop_limit_reached`。它不会静默接受 baseline，不会运行 `enhance`，不会切换 `active_run_id`，也不会扫描目录猜最新文件；要提高轮数可传 `--max-rounds <n>`。

Phase 4 渲染完成后，可先运行渲染视觉/元件一致性检查：

```bash
python cad_pipeline.py render-visual-check --subsystem <name>
```

`render-visual-check` 只读取 `ARTIFACT_INDEX.json.active_run_id` 绑定的 `PRODUCT_GRAPH.json`、`ASSEMBLY_SIGNATURE.json` 和 `render_manifest.json`，写出当前 run 目录下的 `RENDER_VISUAL_REGRESSION.json`。它检查 render manifest 的 subsystem/run_id/path/hash 链、active render_dir、渲染文件 hash、重复视角、产品图必需实例是否进入运行时装配签名；有 `accepted baseline` 时还会比较 baseline 的视角、渲染文件、装配实例和可选逐视角实例证据。没有 accepted baseline 时仍检查当前 run 自身；如果缺少 per-view instance evidence，只能给 warning，不能声称图片内每个元件身份已被证明。该命令 does not scan directories，不猜最新 PNG，不换 run；如需显式历史对比，必须同时传 `--baseline-manifest` 和 `--baseline-signature`。

Phase 4 还可运行 Blender 环境预检和截图/像素级质量检查：

```bash
python cad_pipeline.py render-quality-check --subsystem <name>
```

`render-quality-check` 只读取 `ARTIFACT_INDEX.json.active_run_id` 绑定的当前 `render_manifest.json`，写出当前 run 目录下的 `RENDER_QUALITY_REPORT.json`。报告包含 `blender_preflight`、`render_quality_summary` 和逐视角 `pixel_metrics`：它会检查 Blender 可执行文件和版本预检、渲染文件路径/哈希/基础 QA，并计算画布尺寸、主体占比、亮度、对比度、饱和度、边缘密度等截图质量证据。缺 Blender、缺图、路径越界、hash 漂移或基础 QA 失败会 `blocked`；低对比度、边缘密度低或多视角画布不一致是 `warning`。它是确定性像素证据，不是语义 AI 识别；does not scan directories，不猜最新 PNG，不换 run。

如果 `PHOTO3D_RUN.json` 提示存在低风险恢复动作，用户确认后运行：

```bash
python cad_pipeline.py photo3d-run --subsystem <name> --confirm-actions
```

`--confirm-actions` 只会通过 `photo3d-action` 执行当前 `ACTION_PLAN.json` 中 white-listed、low-risk、无需用户输入的恢复动作；它仍不会接受 baseline 或运行增强。底层单轮下一步报告也可以单独运行：

```bash
python cad_pipeline.py photo3d-autopilot --subsystem <name>
```

`photo3d-autopilot` 会先运行 `photo3d` 契约门禁，再写出 `PHOTO3D_AUTOPILOT.json`。这个报告只给普通用户和大模型一个安全的下一步：`blocked` 时指向 `ACTION_PLAN.json` / `LLM_CONTEXT_PACK.json`；`pass` / `warning` 且没有 accepted baseline 时，建议用户确认后显式运行 `python cad_pipeline.py accept-baseline --subsystem <name>`；已有 `accepted_baseline_run_id` 时，才建议进入增强阶段。`photo3d-autopilot` 不会静默接受 baseline，不会切换 `active_run_id`，也不会扫描目录猜最新文件。

当 `PHOTO3D_AUTOPILOT.json` 指向 `ACTION_PLAN.json` 且动作是低风险 CLI 恢复动作时，普通用户可以先预览：

```bash
python cad_pipeline.py photo3d-action --subsystem <name>
```

确认后再执行：

```bash
python cad_pipeline.py photo3d-action --subsystem <name> --confirm
```

`photo3d-action` 只读取当前 `active_run_id` 的 `PHOTO3D_AUTOPILOT.json` / `ACTION_PLAN.json`，默认只写 `PHOTO3D_ACTION_RUN.json` 预览报告；带 `--confirm` 时也只执行白名单内、无需用户输入、low-risk 的 `product-graph` / `build` / `render` 恢复命令。`ACTION_PLAN.json` 中这些 CLI 必须是 run-aware wrapper：`python cad_pipeline.py photo3d-recover --subsystem <name> --run-id <run_id> --artifact-index cad/<name>/.cad-spec-gen/ARTIFACT_INDEX.json --action product-graph|build|render`；禁止把裸 `product-graph` / `build` / `render --subsystem <name>` 当作自动恢复动作。需要用户输入的动作继续询问用户；它不会扫描目录猜最新文件，不会运行增强，也不会接受 baseline。当 `--confirm` 执行的 low-risk CLI 全部成功，且没有用户输入、人工复查或 rejected actions 时，命令会自动重跑 `photo3d-autopilot`，并把下一步摘要写入 `PHOTO3D_ACTION_RUN.json` 的 `post_action_autopilot`；preview、执行失败、仍有用户输入或 rejected actions 时不会自动重跑。

如果普通用户或大模型只想“执行 `PHOTO3D_RUN.json` 里当前这一步”，使用确认式交接入口：

```bash
python cad_pipeline.py photo3d-handoff --subsystem <name>
python cad_pipeline.py photo3d-handoff --subsystem <name> --confirm
python cad_pipeline.py photo3d-handoff --subsystem <name> --provider-preset engineering
python cad_pipeline.py photo3d-handoff --subsystem <name> --provider-preset engineering --confirm
```

`photo3d-handoff` 会读取当前 `active_run_id` 的 `PHOTO3D_RUN.json`（没有时读 `PHOTO3D_AUTOPILOT.json`），写出 `PHOTO3D_HANDOFF.json`。默认只预览；只有带 `--confirm` 才执行识别到的当前下一步。它支持 `accept-baseline`、`enhance`、`enhance-check` 和 `photo3d-run --confirm-actions` 这几类交接；不会扫描目录猜最新文件，不会信任 JSON 报告里的任意 argv，而是用 `ARTIFACT_INDEX.json`、当前 `run_id` 和当前 render dir 重新构造命令。增强动作可带 `--provider-preset default|engineering|gemini|fal|fal_comfy|comfyui`；preset 是白名单，只能映射到已支持的 `enhance --backend/--model` 参数，不能把任意后端、URL、API key 或未来模型名塞进 JSON 后直接执行。交付完成、增强预览复查、用户输入和人工复查类动作不会自动执行，会保留在 `PHOTO3D_HANDOFF.json` 里让用户处理。

底层门禁命令：

```bash
python cad_pipeline.py photo3d --subsystem <name>
```

该命令不会扫描目录猜最新文件；它只读取当前 `run_id` 在 `ARTIFACT_INDEX.json` 中登记的产物，并校验 `PRODUCT_GRAPH.json`、`MODEL_CONTRACT.json`、`ASSEMBLY_SIGNATURE.json`、`RENDER_MANIFEST.json` 与可选 `baseline` / `CHANGE_SCOPE.json` 是否一致。

门禁状态（Gate status，`photo3d` 命令写入 `PHOTO3D_REPORT.json` 的 `status`）：

- `pass`：CAD 契约门禁通过，可以进入增强阶段。
- `warning`：CAD 契约门禁通过但存在非阻断警告，应先展示警告；用户确认后可进入增强。
- `blocked`：CAD 契约门禁失败，不运行 AI 增强。

增强交付状态（Enhancement delivery status，增强阶段完成后的上层判定）：

- `accepted`：CAD 门禁和增强一致性都通过，可作为照片级交付图。
- `preview`：CAD 门禁通过，但增强一致性未验证或未通过，只能作为预览。
- `blocked`：CAD 门禁失败，增强不得执行。

当前门禁阶段的 `PHOTO3D_REPORT.json` 只会把 `enhancement_status` 写成 `not_run` 或 `blocked`；`accepted` / `preview` 属于后续增强交付层。

增强完成后必须运行增强一致性验收：

```bash
python cad_pipeline.py enhance-check --subsystem <name> --dir <render_dir>
```

`enhance-check` 只读取显式 `--dir` 内的 `render_manifest.json` 和同目录的 `*_enhanced.*` 文件，写出 `ENHANCEMENT_REPORT.json`。它要求 manifest 中每个视角都有对应增强图，并检查源渲染/增强图的轮廓相似度、基础图片 QA 和 deterministic multi-view quality；报告会包含 `quality_summary`，记录多视角画布一致性、对比度、亮度、饱和度、主体占比等质量证据。状态为 `accepted` 才可交付，`preview` 只能预览，`blocked` 表示缺少视角或输入不完整。该命令不会扫描目录猜最新文件，也不会接受 render dir 外的增强图。

如需要语义/材质级照片级复核，可在增强验收 accepted 之后导入显式人工/大模型复核证据：

```bash
python cad_pipeline.py enhance-review --subsystem <name> --review-input <json>
```

`enhance-review` 只读取 `--review-input` 指定的 JSON，写出当前 active run 目录下的 `ENHANCEMENT_REVIEW_REPORT.json`。它会校验 `ARTIFACT_INDEX.json.active_run_id`、`run_id`、`subsystem`、同一 run 的 `render_manifest.json` 和 `ENHANCEMENT_REPORT.json` 路径及 sha256，再按视角记录 `semantic_material_review`，包括 `geometry_preserved`、`material_consistent`、`photorealistic`、`no_extra_parts`、`no_missing_parts` 等通用检查。状态为 `accepted` / `preview` / `needs_review` / `blocked`。该命令不调用 AI、不接受 backend/model/key/url、不扫描目录，也不会用复核结果修补 CAD 几何。

普通用户不需要手动把增强和验收两条命令拼起来：当 `PHOTO3D_RUN.json` 的下一步是增强，且用户确认执行 `python cad_pipeline.py photo3d-handoff --subsystem <name> --confirm` 后，handoff 会先执行同一 active run 的 `enhance`，成功后自动运行同一 render dir 的 `enhance-check`，把复查 subprocess 写入 `PHOTO3D_HANDOFF.json.followup_action`，再无确认重跑一次 `photo3d-run`，把 accepted/preview/blocked 状态写入 `PHOTO3D_HANDOFF.json.post_handoff_photo3d_run`。`executed_with_followup` 表示增强和同 run 验收闭环已完成；即使 `enhance-check` 因 blocked 返回非零，只要写出了有效 `ENHANCEMENT_REPORT.json`，也会通过 `PHOTO3D_RUN.json` 暴露下一步，而不是变成不可读的 subprocess 失败。

增强验收为 `accepted` 后，生成最终交付包：

```bash
python cad_pipeline.py photo3d-deliver --subsystem <name>
```

`photo3d-deliver` 只读取当前 `ARTIFACT_INDEX.json.active_run_id` 绑定的 `render_manifest.json`、`ENHANCEMENT_REPORT.json`、`ENHANCEMENT_REVIEW_REPORT.json`（如存在）、`PHOTO3D_RUN.json` 和契约证据，写出 `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/delivery/DELIVERY_PACKAGE.json` 与 `README.md`。默认只有增强状态为 `accepted` 且 `quality_summary.status` 也为 `accepted`，才会复制最终增强图、源渲染图和可唯一识别的标注图；`preview` / `blocked` 或质量未通过只写证据报告，不标记 `final_deliverable`，也不会当成照片级最终交付。质量未通过时会记录 `photo_quality_not_accepted`。如果同一 run 已有 `semantic_material_review` 且不是 `accepted`，交付会记录 `semantic_review_not_accepted` 并保持 `final_deliverable=false`；若流程要求强制语义/材质复核，运行 `photo3d-deliver --require-semantic-review`，缺少 accepted 复核时记录 `semantic_review_required`。它不会扫描目录猜最新文件，不会换 run，不会接受 subsystem/run_id/render_manifest 漂移；如确实需要预览包，可显式传 `--include-preview`，但 `final_deliverable` 仍为 false。

阻断时会写出：

- `PROJECT_GUIDE.json`：只读项目级下一步报告，覆盖 `init/spec/codegen/build-render/photo3d-run` 的交接；在当前 active run 确认进入增强入口时，可附带白名单 provider preset 选择、普通用户可读选项 `ordinary_user_options`、展示向导 `provider_wizard`、安全配置健康状态 `provider_health` 和 `photo3d-handoff --provider-preset <id>` 预览命令。
- `RENDER_VISUAL_REGRESSION.json`：`render-visual-check` 的 Phase 4 报告，记录当前 run 与 accepted baseline 的视角、渲染文件、装配实例和逐视角实例证据差异。
- `RENDER_QUALITY_REPORT.json`：`render-quality-check` 的 Phase 4 报告，记录 `blender_preflight`、`render_quality_summary` 和逐视角 `pixel_metrics`，用于证明 Blender 环境和截图像素质量。
- `PHOTO3D_REPORT.json`：普通用户可读的中文阻断原因。
- `PHOTO3D_AUTOPILOT.json`：普通用户和大模型本轮下一步报告。
- `ACTION_PLAN.json`：大模型可执行的下一步动作，如重新渲染、重新 build、请求用户提供模型。
- `LLM_CONTEXT_PACK.json`：给其他大模型读取的最小上下文包，只引用当前 `run_id` 的已登记产物。
- `PHOTO3D_ACTION_RUN.json`：`photo3d-action` 的预览/执行结果，只记录当前 run 的动作分类、执行结果和后续人工输入项；成功确认执行后，`post_action_autopilot` 固定记录是否自动重跑以及重跑后的 gate/status/next_action 摘要。
- `PHOTO3D_HANDOFF.json`：`photo3d-handoff` 的预览/执行结果，只针对当前 `PHOTO3D_RUN.json` / `PHOTO3D_AUTOPILOT.json` 的 `next_action`，记录重构后的安全 argv、执行结果、增强后的 `followup_action`、`post_handoff_photo3d_run`、`executed_with_followup` 和必要的人工处理原因。
- `PHOTO3D_RUN.json`：`photo3d-run` 的多轮向导报告，记录每轮 gate/autopilot/action 状态、最终 `next_action` 和停止原因。
- `ENHANCEMENT_REPORT.json`：增强完成后的交付验收报告，记录每个视角的源图、增强图、相似度、QA、`quality_summary` 和 `accepted` / `preview` / `blocked` 状态。
- `ENHANCEMENT_REVIEW_REPORT.json`：显式人工/大模型语义和材质复核报告，记录 `semantic_material_review`、源报告路径/hash、逐视角检查和 `accepted` / `preview` / `needs_review` / `blocked` 状态。
- `DELIVERY_PACKAGE.json`：`photo3d-deliver` 的最终交付包清单，记录源报告、源渲染图、增强图、标注图、证据文件、质量摘要、可选 `semantic_material_review`、`photo_quality_not_accepted` 等阻断原因和 `final_deliverable` 状态。

大模型优先调用 `photo3d-run` 读取 `PHOTO3D_RUN.json`；Phase 4 证据需要分清：`render-visual-check` 证明视角/元件契约，`render-quality-check` 证明 Blender 环境和截图像素质量，二者都只读当前 active run。用户说“按建议执行”时优先调用 `photo3d-handoff` 预览或在用户确认后执行当前 `next_action`，不要自己拼 shell。用户要选择增强后端时只传 `--provider-preset` 白名单值，例如离线预览用 `engineering`，不要手写 `--backend` 或从 JSON 复制任意 argv。增强确认执行后读取 `PHOTO3D_HANDOFF.json.post_handoff_photo3d_run`，不要再扫描 render 目录猜增强是否成功；如果用户或流程需要语义/材质级照片级判断，先生成显式 review JSON，再运行 `enhance-review`，不要让任意模型直接改管线状态；当状态为 `enhancement_accepted` 时，再运行 `photo3d-deliver` 生成 `DELIVERY_PACKAGE.json`，需要强制语义/材质复核时加 `--require-semantic-review`，而不是手工复制图片。需要处理 blocked 恢复动作时，可以调用 `photo3d-action` 预览或在用户确认后执行低风险 CLI 动作。不能扫描目录猜最新文件，也不能用 AI 增强补齐 CAD 阶段缺失的零件、位置或结构。低风险 CLI 的实际命令必须经 `photo3d-recover` 绑定 `--run-id` 与 `--artifact-index`，让恢复产物写回当前 run 的固定路径。

路径隔离与旧产物清理：

- 每次运行都有独立 `run_id`，契约文件写入 `cad/<subsystem>/.cad-spec-gen/runs/<run_id>/`，渲染图写入 `cad/output/renders/<subsystem>/<run_id>/`。
- `ARTIFACT_INDEX.json` 只记录当前 run 的已登记产物；旧产物不会因为文件还存在而自动参与本轮门禁。
- 需要清理旧产物时，只删除过期 run 目录或旧 render 目录；不要删除当前 `active_run_id` 仍引用的文件。

接受基准流程：

- 首次 `pass` 的结果只能作为候选基准；不要伪造历史稳定性。
- 用户确认当前 `PHOTO3D_REPORT.json` 后，运行 `python cad_pipeline.py accept-baseline --subsystem <name>`，把该 `run_id` 写入 `ARTIFACT_INDEX.json` 的 `accepted_baseline_run_id`，并记录为 accepted baseline。
- `PHOTO3D_REPORT.json` 会记录关键契约的 `artifact_hashes`；`accept-baseline` 会校验报告路径、报告中的 artifact 路径、以及当前文件哈希都与 `ARTIFACT_INDEX.json` 中同一 run 一致，防止旧报告、手写报告或被改动后的临时产物成为基线证据。
- 该命令只接受 `pass` / `warning` 的 `PHOTO3D_REPORT.json`，不会切换 `active_run_id`，也不会扫描目录猜最新产物；需要指定历史 run 时传 `--run-id <run_id>`。
- 后续 `photo3d --change-scope <CHANGE_SCOPE.json>` 会自动使用 `accepted_baseline_run_id` 对应的 `ASSEMBLY_SIGNATURE.json`；仍可用 `--baseline-signature <path>` 显式覆盖。
- 后续 `photo3d` 会用 `baseline` / `CHANGE_SCOPE.json` 比较实例数量、位置、bbox 和旋转漂移。误改应回退；有意变更必须在 `CHANGE_SCOPE.json` 中写清授权范围并标注为 authorized，否则漂移保持 `blocked`。

### AI 增强工作流（所有配置的视角）

Blender渲染完成后，将所有PNG增强为照片级JPG。支持四种后端：

| 后端 | 费用 | 几何锁定 | 需要GPU | 适用场景 | 推荐度 |
|------|------|----------|---------|----------|--------|
| `engineering` | 免费，0.1s/张 | 完美（无AI） | 否 | 工程审查、精确图纸 | ⭐⭐⭐⭐⭐ 推荐 |
| `gemini` | ~$0.02/张 | 软锁（prompt） | 否（云端） | 展示/答辩/商业计划书 | ⭐⭐⭐⭐ 推荐 |
| `fal` | ~$0.20/张 | 硬锁（depth+canny） | 否（云端） | 实验性 — 未来详细3D模型 | ⭐ 实验性 |
| `comfyui` | 免费 | 硬锁（ControlNet） | 是（8GB+） | 本版本未测试 | — 未测试 |

> **推荐组合**：精确工程图用 `engineering`，外观展示用 `gemini`。fal 的 Flux 模型对简化 CadQuery 几何产生红绿噪点和色彩失真，保留供未来详细 3D 模型使用。comfyui 使用 SD1.5（比 Flux 更适合 CAD），本版本未实测。

**自动检测优先级**：FAL_KEY环境变量 → ComfyUI运行中(localhost:8188) → Gemini配置 → engineering兜底。
**降级链**：fal → gemini → engineering（降级后锁定后端，确保批次内多视角一致性）。

```bash
# 自动检测最佳后端
python cad_pipeline.py enhance --subsystem <name>

# 指定后端
python cad_pipeline.py enhance --subsystem <name> --backend fal
python cad_pipeline.py enhance --subsystem <name> --backend engineering

# 全流程也支持 --backend
python cad_pipeline.py full --subsystem <name> --backend gemini
```

**核心原则：**
- 视角锁定（v2.1）：prompt 首行 "Preserve EXACT camera angle, viewpoint, framing"；每视角写入计算方位角/仰角
- 几何锁定：gemini 靠 prompt 约束；fal/comfyui 靠 ControlNet depth+canny 硬约束；engineering 完美保真（无AI变换）
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
