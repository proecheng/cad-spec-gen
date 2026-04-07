# 三后端增强方案：Gemini + fal.ai + 工程模式

> 目标：管线支持三种 Phase 5 ENHANCE 后端
> 原则：只改共享工具/模板，不改中间产物，数据流一致
> 日期：2026-04-07

---

## 1. 三种后端定位

| 后端 | 适用场景 | 几何保真 | 每张成本 | 依赖 |
|------|---------|---------|---------|------|
| `gemini` | 快速演示、商业计划书 | 软约束（prompt） | ~$0.02 | Gemini API key |
| `fal` | 高质量渲染、多视角一致 | 硬锁（ControlNet depth+canny） | ~$0.20 | fal.ai API key |
| `engineering` | 工程审查、图纸配图 | 完美（物理渲染） | 免费 | 无 |

---

## 2. 数据流

```
Phase 4 RENDER (Blender Cycles)
    ↓ 输出: V*.png (RGB) + V*_depth_.exr (可选, render_passes.enabled)
    ↓
Phase 5 ENHANCE
    ├─ backend=gemini   → gemini_gen.py (现有)
    ├─ backend=fal      → fal_enhancer.py (新增) ← 需要 depth PNG
    └─ backend=engineering → 无 AI, 直接后处理 Blender PNG
    ↓ 输出: V*_enhanced.jpg (统一命名, 统一存放)
    ↓
Phase 6 ANNOTATE (读同一目录下的 enhanced 文件)
```

### fal.ai 后端数据流细节

```
V1.png (Blender RGB)
    ↓ fal_enhancer.py
    ├─ 上传到 fal storage → render_url
    ├─ V1_depth.png (从 EXR 转换) → depth_url
    ├─ prompt (unified template, 同 Gemini)
    ↓
fal-ai/flux-general API
    ├─ controlnets[0]: canny (from render_url, strength=0.8)
    ├─ controlnets[1]: depth (from depth_url, strength=0.95)
    ↓
output image URL → 下载 → V1_enhanced.jpg
```

### 工程模式数据流

```
V1.png (Blender Cycles, PBR 材质, 512 samples)
    ↓ _engineering_postprocess()
    ├─ 轻度后处理: 锐化 + 对比度微调 + 转 JPG 95%
    ↓
V1_enhanced.jpg (几何 100% 一致, 确定性输出)
```

---

## 3. 修改文件清单

| # | 文件 | 类型 | 改动 |
|---|------|------|------|
| 1 | `fal_enhancer.py` | **新增** 共享工具 | fal.ai ControlNet 增强函数 |
| 2 | `cad_pipeline.py` | 共享工具 | cmd_enhance 增加 fal + engineering 分支 |
| 3 | `pipeline_config.json` | 共享配置 | 增加 fal + engineering 配置段 |
| 4 | `cad_paths.py` | 共享工具 | SHARED_TOOL_FILES 增加 fal_enhancer.py |
| 5 | `render_config.py` | 共享工具 | depth EXR→PNG 转换函数 |

**不改的文件**：
- enhance_prompt.py — prompt 对所有后端通用
- templates/prompt_enhance_unified.txt — 模板不变
- gemini_gen.py — 不动
- comfyui_enhancer.py — 不动
- render_3d.py — 不动
- render_config.json — 产物，不手改

---

## 4. 详细设计

### 4a. fal_enhancer.py（新增共享工具）

```python
def enhance_image(png_path, prompt, fal_cfg, view_key, rc):
    """fal.ai Flux ControlNet 增强。

    函数签名与 comfyui_enhancer.enhance_image() 一致。

    Args:
        png_path: 源 PNG 路径
        prompt: 统一增强 prompt（同 Gemini/ComfyUI）
        fal_cfg: pipeline_config.json["enhance"]["fal"] dict
        view_key: "V1", "V2" 等
        rc: render_config.json dict

    Returns:
        str: 输出图片路径（调用方负责重命名）
    """
```

关键实现：
- 从 png_path 推导 depth 路径：`{stem}_depth_.exr` → 转 PNG
- 上传 RGB + depth 到 fal storage
- 调用 `fal-ai/flux-general`，双 ControlNet
- 下载结果到临时文件，返回路径
- prompt 截取前 500 字符作为正向提示（同 ComfyUI 做法）

### 4b. cad_pipeline.py cmd_enhance 分支

```python
# 现有 line ~1272
if backend == "fal":
    from fal_enhancer import enhance_image as enhance_with_fal
elif backend == "comfyui":
    from comfyui_enhancer import enhance_image as enhance_with_comfyui
elif backend == "engineering":
    pass  # 无需导入，内联处理
else:
    backend = "gemini"
    ...
```

工程模式内联处理（不需要独立模块）：
```python
if backend == "engineering":
    # 直接后处理 Blender PNG → JPG
    from PIL import Image, ImageEnhance
    img = Image.open(png)
    img = ImageEnhance.Sharpness(img).enhance(1.3)
    img = ImageEnhance.Contrast(img).enhance(1.1)
    out_path = png.replace('.png', '_enhanced.jpg')
    img.save(out_path, 'JPEG', quality=95)
    # 统一命名逻辑（与 Gemini/ComfyUI 一致）
```

### 4c. pipeline_config.json 配置段

```json
{
  "enhance": {
    "backend": "gemini",
    "fal": {
      "model": "fal-ai/flux-general",
      "controlnet_canny": "InstantX/FLUX.1-dev-Controlnet-Canny",
      "controlnet_depth": "Shakker-Labs/FLUX.1-dev-ControlNet-Depth",
      "canny_strength": 0.8,
      "depth_strength": 0.95,
      "steps": 28,
      "guidance_scale": 3.5,
      "timeout": 120
    },
    "engineering": {
      "sharpness": 1.3,
      "contrast": 1.1,
      "quality": 95
    }
  }
}
```

### 4d. depth EXR→PNG 转换

fal.ai 需要 PNG 格式的 depth map，但 Blender 输出 EXR。
在 `render_config.py` 增加转换函数：

```python
def convert_depth_exr_to_png(exr_path, output_path=None):
    """将 Blender 32-bit float depth EXR 转换为 0-255 灰度 PNG。

    归一化：near=白(255), far=黑(0)。
    """
```

`fal_enhancer.py` 在上传前调用此函数。

---

## 5. 数据一致性验证

| 步骤 | gemini | fal | engineering |
|------|--------|-----|-------------|
| 输入 PNG | V*.png | V*.png | V*.png |
| 输入 depth | 不需要 | V*_depth_.exr → PNG | 不需要 |
| prompt 来源 | unified template | unified template | 不需要 |
| 输出命名 | {stem}_{ts}_enhanced.jpg | {stem}_{ts}_enhanced.jpg | {stem}_{ts}_enhanced.jpg |
| 输出目录 | 与源 PNG 同目录 | 与源 PNG 同目录 | 与源 PNG 同目录 |
| hero_image | V1 swatch | V1 swatch（可选） | 不需要 |
| Phase 6 消费 | render_manifest.json | render_manifest.json | render_manifest.json |

**输出命名和目录对 Phase 6 ANNOTATE 透明**——annotate 只找 `*_enhanced.jpg`，不关心哪个后端生成的。

---

## 6. fal.ai depth 输入的前提条件

fal.ai 需要 depth PNG。两种获取方式：

**方式 A（推荐）：Blender render pass**
- render_config.json 设 `render_passes.enabled=true, passes=["depth"]`
- Phase 4 输出 `V*_depth_.exr`
- fal_enhancer.py 自动转 EXR→PNG

**方式 B（fallback）：从 RGB 估算**
- 当 depth EXR 不存在时，用 MiDAS 从 RGB PNG 估算 depth
- 精度低于 Blender 直出，但无需修改 render 配置

fal_enhancer.py 优先用方式 A，fallback 到方式 B。

---

## 7. 实施步骤

| # | 操作 | 文件 |
|---|------|------|
| 1 | 新建 fal_enhancer.py | 项目根目录（共享工具）|
| 2 | render_config.py 增加 depth EXR→PNG 转换 | 共享工具 |
| 3 | cad_pipeline.py cmd_enhance 增加 fal + engineering 分支 | 共享工具 |
| 4 | pipeline_config.json 增加 fal + engineering 配置段 | 共享配置 |
| 5 | cad_paths.py SHARED_TOOL_FILES 增加 fal_enhancer.py | 共享工具 |
| 6 | 同步到 src/ 打包目录 | 打包 |
| 7 | 验证三种后端 | 测试 |

---

## 8. 用户交互设计

### 后端选择优先级

```
CLI --backend 参数  >  pipeline_config.json  >  自动检测
```

**自动检测逻辑**（`_auto_detect_backend()`，在 cmd_enhance 中）：
```python
def _auto_detect_backend():
    """无配置时自动选择最佳可用后端。"""
    # 1. fal: 检查 FAL_KEY 环境变量 + fal-client 已安装
    if os.environ.get("FAL_KEY") and _can_import("fal_client"):
        return "fal"
    # 2. comfyui: 检查 localhost:8188 可达
    if _comfyui_reachable():
        return "comfyui"
    # 3. gemini: 检查 gemini 配置文件存在
    if get_gemini_script():
        return "gemini"
    # 4. engineering: 始终可用（零依赖）
    return "engineering"
```

### CLI 用法

```bash
# 使用项目默认后端
python cad_pipeline.py enhance --subsystem end_effector

# 一次性指定后端
python cad_pipeline.py enhance --backend fal
python cad_pipeline.py enhance --backend engineering

# 全管线（后端从 pipeline_config.json 读取）
python cad_pipeline.py full --subsystem end_effector

# 全管线 + 指定后端
python cad_pipeline.py full --backend engineering
```

### API key 管理

| 后端 | 凭证 | 存储位置 |
|------|------|---------|
| gemini | API key | `~/.claude/gemini_image_config.json`（现有） |
| fal | FAL_KEY | 环境变量 `FAL_KEY`（fal-client 自动读取） |
| comfyui | 无 | 本地服务（localhost:8188） |
| engineering | 无 | 无需凭证 |

**不在 pipeline_config.json 中存 API key**——避免 git 提交泄露。

### 跨阶段联动

当 `backend=fal` 时，Phase 4 RENDER 需要输出 depth pass。
`cmd_full()` 和 `cmd_render()` 自动处理：

```python
# cmd_render 中：
if enhance_backend == "fal":
    # 自动设置环境变量，让 render_3d.py 启用 depth pass
    os.environ["CAD_RENDER_DEPTH"] = "1"
    log.info("  Auto-enabled depth pass for fal backend")
```

render_3d.py 检查此环境变量（在 setup_render_passes 中）。
**无需修改 render_config.json**——环境变量是临时的。

### 依赖检测

```python
# cmd_enhance 中 fal 后端预检：
if backend == "fal":
    try:
        import fal_client
    except ImportError:
        log.error("fal-client not installed. Run: pip install fal-client")
        return 1
    if not os.environ.get("FAL_KEY"):
        log.error("FAL_KEY environment variable not set. Get key at https://fal.ai/dashboard/keys")
        return 1
```

## 9. 健壮性设计（二审补充）

### 9a. 故障自动降级链

```python
FALLBACK_CHAIN = {
    "fal": ["gemini", "engineering"],
    "gemini": ["engineering"],
    "comfyui": ["gemini", "engineering"],
    "engineering": [],  # 永远成功
}
```

规则：
- 某后端连续失败 2 次 → 降级到链中下一个
- **降级后本批次锁定**——不再回升，避免同批次材质风格混杂
- 降级时 `log.warning("Backend %s failed, falling back to %s")`

### 9b. Flux prompt 蒸馏

fal_enhancer.py 的 prompt 处理独立于 Gemini/ComfyUI：

```python
def _distill_prompt_for_flux(full_prompt, rc, view_key):
    """从 unified prompt 提取 Flux 风格的短描述 (~200 chars)。
    
    Flux 不需要否定指令("do NOT")，只需要正向描述。
    格式: "photorealistic [product], [materials], [lighting], 4k"
    """
    product = rc.get("prompt_vars", {}).get("product_name", "mechanical assembly")
    # 从 material_descriptions 提取前 3 个材质
    mat_descs = rc.get("prompt_vars", {}).get("material_descriptions", [])
    mat_text = ", ".join(d.get("material_desc", "")[:40] for d in mat_descs[:3])
    return (
        f"photorealistic product render, {product}, "
        f"{mat_text}, "
        f"studio lighting, sharp focus, 4k professional product photography"
    )
```

### 9c. 工程模式零依赖

```python
if backend == "engineering":
    try:
        from PIL import Image, ImageEnhance
        # Pillow 可用：轻度后处理
        img = Image.open(png)
        img = ImageEnhance.Sharpness(img).enhance(cfg.get("sharpness", 1.3))
        img.save(out_path, "JPEG", quality=cfg.get("quality", 95))
    except ImportError:
        # Pillow 不可用：直接复制 PNG（零依赖 fallback）
        import shutil
        shutil.copy2(png, out_path.replace(".jpg", ".png"))
```

### 9d. 陈旧文件清理

cmd_enhance 开始前：
```python
# 清理目标目录中上次运行的增强文件（防止 Phase 6 拿到旧后端的产物）
for stale in glob.glob(os.path.join(render_dir, "*_enhanced.*")):
    os.remove(stale)
    log.info("  Cleaned stale: %s", os.path.basename(stale))
```

### 9e. depth 分辨率同步

```python
def convert_depth_exr_to_png(exr_path, rgb_png_path=None):
    """EXR→PNG，强制与 RGB PNG 同分辨率。"""
    # ...
    if rgb_png_path:
        rgb_w, rgb_h = Image.open(rgb_png_path).size
        if (depth_w, depth_h) != (rgb_w, rgb_h):
            depth_img = depth_img.resize((rgb_w, rgb_h), Image.LANCZOS)
    # ...
```

### 9f. 成本保护

```python
if backend == "fal" and not getattr(args, "yes", False):
    n_images = len(pngs)
    est_cost = n_images * 0.20
    log.info("  fal.ai estimated cost: $%.2f (%d images × $0.20)", est_cost, n_images)
    if est_cost > 1.0:
        log.warning("  Cost exceeds $1.00. Use --yes to skip confirmation.")
        # 在非交互模式下继续，交互模式下可加 input() 确认
```

### 9g. 增强结果质量门控

```python
def _check_enhanced_quality(enhanced_path, source_path):
    """检查增强结果是否可接受。"""
    enhanced_size = os.path.getsize(enhanced_path)
    source_size = os.path.getsize(source_path)
    # 增强图不应比源图小太多（可能是纯黑/残缺）
    if enhanced_size < source_size * 0.1:
        return False, "Enhanced image suspiciously small"
    # 增强图不应是纯色
    try:
        from PIL import Image
        img = Image.open(enhanced_path)
        variance = img.convert("L").getdata()
        import statistics
        if statistics.variance(variance) < 10:
            return False, "Enhanced image appears to be solid color"
    except Exception:
        pass  # PIL 不可用时跳过方差检查
    return True, "OK"
```

### 9h. fal.ai 上传重试

```python
def _upload_with_retry(file_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            return fal_client.upload_file(file_path)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Upload failed after {max_retries} attempts: {e}")
```

## 10. 最终审查清单

| # | 要点 | 状态 |
|---|------|------|
| 1 | 数据源唯一：prompt 来自 unified template，depth 来自 Blender render pass | ✅ |
| 2 | 只改共享工具：fal_enhancer.py + cad_pipeline.py + render_config.py + pipeline_config.json + cad_paths.py | ✅ |
| 3 | 不改产物：render_config.json / render_3d.py / assembly.py 不动 | ✅ |
| 4 | 输出一致性：三后端统一 {stem}_{ts}_enhanced.jpg，Phase 6 透明消费 | ✅ |
| 5 | 向后兼容：默认 backend=gemini | ✅ |
| 6 | 跨阶段联动：fal 自动启用 depth pass | ✅ |
| 7 | 依赖优雅降级：fal-client/Pillow 未装 → 明确提示或自动 fallback | ✅ |
| 8 | API key 安全：环境变量，不写入可提交文件 | ✅ |
| 9 | 故障降级链：fal→gemini→engineering，降级后锁定本批次 | ✅ |
| 10 | Flux prompt 蒸馏：独立于 Gemini 长 prompt，~200 chars 正向描述 | ✅ |
| 11 | 工程模式零依赖：Pillow fallback 到 shutil.copy | ✅ |
| 12 | 陈旧文件清理：cmd_enhance 开始前删旧 enhanced 文件 | ✅ |
| 13 | depth 分辨率同步：EXR→PNG 强制与 RGB 同尺寸 | ✅ |
| 14 | 成本保护：fal 首次使用打印估算 + >$1 提醒 | ✅ |
| 15 | 增强结果质检：文件大小 + 方差检查，防纯黑/残缺 | ✅ |
| 16 | fal 上传重试：3 次指数退避 | ✅ |
| 17 | 自动检测：零配置首次使用自动选最佳后端 | ✅ |
