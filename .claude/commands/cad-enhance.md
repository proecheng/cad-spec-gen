# /cad-enhance — AI 增强（Blender PNG → 照片级 JPG）

用户输入: $ARGUMENTS

## 指令

将 Blender Cycles 渲染的 PNG 图片增强为照片级 JPG。几何形状 100% 锁定，仅更换表面材质外观。

支持四种后端：**Gemini**（云端 AI）、**fal.ai**（云端 ControlNet 硬锁）、**ComfyUI**（本地 GPU）、**工程模式**（无 AI）。

### 路由规则

1. **无参数** → 显示用法：
   ```
   /cad-enhance <subsystem>                           — 增强当前 manifest 的所有视角
   /cad-enhance <subsystem> --backend gemini          — Gemini AI（云端，快速）
   /cad-enhance <subsystem> --backend fal             — fal.ai Flux ControlNet（云端，几何硬锁）
   /cad-enhance <subsystem> --backend comfyui         — ComfyUI ControlNet（本地 GPU）
   /cad-enhance <subsystem> --backend engineering     — 工程模式（无 AI，Blender 直出）
   /cad-enhance --env-check                           — 检测环境
   ```

2. **有参数但未指定 `--backend`** → 先询问用户选择后端：

   读取 `pipeline_config.json` 的 `enhance.backend` 当前值，然后向用户展示：

   ```
   当前默认后端：<backend>（来自 pipeline_config.json）

   请选择增强后端：
   A. Gemini      — 云端 AI，无需 GPU，~$0.02/张（外观好但几何可能微变）
   B. fal.ai      — 云端 ControlNet，~$0.20/张（几何硬锁，多视角一致）
   C. ComfyUI     — 本地 GPU，免费（需 GPU 8GB+，几何硬锁）
   D. 工程模式    — 无 AI，Blender PBR 直接后处理，免费（几何 100% 准确）
   E. 保持默认（<backend>）
   ```

   - 用户选 A / 输入 `gemini` → 使用 gemini
   - 用户选 B / 输入 `fal` → 检查 FAL_KEY 环境变量，就绪后执行
   - 用户选 C / 输入 `comfyui` → 运行 `comfyui_env_check.py`，就绪后执行
   - 用户选 D / 输入 `engineering` / 输入 `工程` → 直接执行（零依赖）
   - 用户选 E 或直接回车 → 使用当前默认后端
   - 用户说"不要 AI" / "精确" / "工程图" → 推荐工程模式
   - 用户说"最好的效果" / "高质量" → 推荐 gemini（外观最佳）或 engineering（几何最佳）
   - 用户说"fal" → 提醒：fal 目前为实验性后端，Flux 模型对简化 CAD 几何效果不佳（红绿噪点/色彩失真），建议改用 gemini 或 engineering

3. **有参数且已指定 `--backend`** → 跳过询问，直接执行增强：
   - 若 `--backend comfyui`：先运行 `python comfyui_env_check.py`，若环境未就绪则展示安装指引并询问是否继续
   - 读取对应子系统的 `render_config.json` 获取材质描述（`prompt_vars.material_descriptions`）
   - 使用统一 prompt 模板 `templates/prompt_enhance_unified.txt`
     - 按 `render_config.json` 的 `camera.V*.type` 字段自动切换视角特定内容
     - `prompt_data_builder.py` 从 `params.py` 自动生成材质/装配/约束数据
   - 将输出文件重命名为 `V*_视图名_YYYYMMDD_HHMM_enhanced.ext`（与源 PNG 同目录），时间戳防止覆盖历史版本

### 后端选择

| 后端 | 适用场景 | 几何保真 | 成本 | 依赖 | 推荐度 |
|------|----------|---------|------|------|--------|
| `engineering` | 工程审查、图纸配图 | **完美（物理渲染）** | 免费，0.1s/张 | 无（Pillow 可选） | ⭐⭐⭐⭐⭐ 推荐 |
| `gemini` | 快速演示、商业计划书 | 中（AI 可能微调几何） | ~$0.02/张 | Gemini API Key | ⭐⭐⭐⭐ 推荐 |
| `fal` | 实验性 — 未来详细3D模型 | 高（ControlNet 硬锁） | ~$0.20/张 | FAL_KEY 环境变量 | ⭐ 实验性 |
| `comfyui` | 本地 GPU 用户 | 高（ControlNet 硬锁） | 免费 | GPU 8GB+，ComfyUI | 未测试 |

> **推荐组合**：精确工程图用 `engineering`，展示/答辩用 `gemini`。
> **fal 实验性说明**：Flux 模型对简化 CadQuery 几何产生红绿噪点和色彩失真，ControlNet 架构本身可行但 Flux 基模型不适合 CAD 简化几何。保留供未来详细 3D 模型使用。
> **comfyui 说明**：与 fal 相同的 ControlNet 原理但使用 SD1.5（更适合 CAD），本版本未实测。

**故障降级**：fal → gemini → engineering（连续 2 次失败自动切换，批次内锁定）

**切换后端（三种方式，优先级从高到低）：**

```bash
# 1. CLI 参数（临时）
python cad_pipeline.py enhance --subsystem end_effector --backend fal

# 2. 修改 pipeline_config.json（持久）
"enhance": { "backend": "comfyui" }

# 3. 默认为 gemini，无需修改
```

### ComfyUI 环境检测

首次使用 ComfyUI 前运行：

```bash
python comfyui_env_check.py
```

输出示例：
```
[OK]  GPU: NVIDIA RTX 3080 (CUDA 12.1)
[OK]  ComfyUI 服务运行中 (localhost:8188)
[OK]  ControlNet 模型: control_v11p_sd15_depth.pth
[OK]  ControlNet 模型: control_v11p_sd15_canny.pth
[WARN] Stable Diffusion 基础模型未找到 → 建议下载 realisticVisionV60B1.safetensors
```

缺少组件时，脚本会输出对应的下载/安装指令。

### ComfyUI 工作原理

- 为每张 PNG 自动生成 depth map（MiDaS）+ canny 边缘图
- 以这两张控制图约束 SD 生成，**几何由图像硬锁**，不依赖文字指令
- 通过 `localhost:8188` REST API 提交 workflow JSON，轮询结果
- workflow 模板位于 `templates/comfyui_workflow_template.json`

### Layout 路由（v2.0 新增）

`prompt_data_builder.py` 根据子系统 layout 类型自动路由 prompt 数据生成策略：

| `render_config.json` 的 `layout.type` | 路由 | 行为 |
|---------------------------------------|------|------|
| `radial`（或 params.py 含 `STATION_ANGLES`/`MOUNT_CENTER_R`） | `_generate_radial_prompt_data()` | 完整的 4 工位描述、N1-N10 约束、标准件列表（末端执行器专用） |
| `linear` / `cartesian` / `custom` | `_generate_generic_prompt_data()` | 仅从 `rc["materials"]` 派生材质描述；`assembly_description`/`negative_constraints`/`standard_parts` 使用 render_config.json 中**用户手写的值** |

非 radial 子系统（如 lifting_platform）**不会**注入任何末端执行器专用术语（flange、PEEK、station、cable chain 等），避免 Gemini 生成幽灵零件。

### 多视角一致性（v2.1 新增）

Gemini 后端的四层一致性防线：

1. **视角锁定（Viewpoint Lock）**
   - `enhance_prompt.py` 的 `_camera_to_view_description()` 从 `render_config.json` 的 camera 位置向量自动计算方位角/仰角
   - 每个视角生成唯一描述，如 "rear-left oblique view at 25° elevation, 222° azimuth (50mm perspective)"
   - prompt 模板首行为 `VIEWPOINT & GEOMETRY LOCK — HIGHEST PRIORITY`

2. **图片角色分离（IMAGE ROLES）**
   - 源图放在 content 数组**第一位**（锁定构图），参考图放**第二位**（仅提供材质风格）
   - prompt 中明确指示："Image 1 = SOURCE — preserve EXACT viewpoint; Image 2 = STYLE REFERENCE ONLY"
   - 风格锚定文本**不再**包含 "match lighting angle" 等可能污染视角的词语

3. **V1-anchor 参考图**
   - V1 增强结果作为后续视角的材质风格参考（`reference_mode: "v1_anchor"`）
   - 参考图仅传递材质纹理和色彩，不传递视角
   - 参考图压缩至 1280×720 q90

4. **源图高保真**
   - 源图 ≤4MB 时不压缩，直接发送原始 1920×1080 PNG（~1.5MB）
   - 保留完整空间细节，帮助 Gemini 识别源图视角

**相关配置（pipeline_config.json）：**
```json
"enhance": {
  "temperature": 0.2,
  "seed_from_image": true,
  "reference_mode": "v1_anchor"
}
```

### 核心原则

- **视角锁定**：prompt 首行 "Preserve the EXACT camera angle, viewpoint, and framing"；每视角写入具体方位角/仰角；IMAGE ROLES 明确分离源图构图和参考图风格
- **几何锁定**：Gemini 模式下 prompt 写 "Keep ALL geometry EXACTLY unchanged"；ComfyUI 模式下由 ControlNet 硬约束
- **材质来源**：所有材质描述从 render_config.json `prompt_vars` 和 `materials` 读取，不要凭空编造
- **Layout 感知**：非 radial 布局的子系统不注入硬编码零件描述

### 标准件增强

prompt 模板包含 `{standard_parts_description}` 占位符，由 `render_config.json` 的 `standard_parts` 数组填充：

```json
"standard_parts": [
  {"visual_cue": "Small cylinder (Φ22×68mm) under flange", "real_part": "Maxon ECX motor, silver housing..."},
  {"visual_cue": "Annular rings at bearing locations", "real_part": "MR105ZZ ball bearing, chrome steel..."}
]
```

两种后端均使用此描述。如 `standard_parts` 为空，占位符替换为空字符串，不影响现有流程。

### Gemini 模型选择

`pipeline_config.json` 的 `enhance` 段配置 Gemini 模型：

```json
"enhance": {
  "backend": "gemini",
  "model": "nano_banana_4k",
  "models": {
    "nano_banana": "gemini-2.5-flash-image",
    "nano_banana_pro": "gemini-3-pro-image-preview",
    "nano_banana_2": "gemini-3.1-flash-image",
    "nano_banana_4k": "gemini-3-pro-image-preview-4k"
  }
}
```

- `model` 字段选择当前使用的模型别名
- `models` 字典映射别名 → Gemini API model ID
- 通过 `--model <id>` 参数传递给 `gemini_gen.py`
- 切换模型只需修改 `pipeline_config.json` 的 `model` 值

### ComfyUI 配置

```json
"comfyui": {
  "host": "127.0.0.1",
  "port": 8188,
  "workflow_template": "templates/comfyui_workflow_template.json",
  "checkpoint": "realisticVisionV60B1_v51VAE.safetensors",
  "controlnet_depth_model": "control_v11f1p_sd15_depth.pth",
  "controlnet_canny_model": "control_v11p_sd15_canny.pth",
  "steps": 28,
  "cfg_scale": 7.0,
  "denoise_strength": 0.55,
  "timeout": 300
}
```
