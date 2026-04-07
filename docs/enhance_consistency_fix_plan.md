# AI 增强多视角一致性修复方案

> 问题：Gemini 增强后各视角间几何不一致（弹簧位置不同、零件丢失等）
> 根因：Gemini 是 2D→2D 生成模型，不理解 3D 空间，每张图独立"想象"
> 日期：2026-04-07

---

## 1. 问题分析

### 现象

对比 V5 (ortho_front) 和 V7 (section_side) 的增强结果：
- V5 弹簧在法兰上方，V7 弹簧在侧面水平 → **位置不一致**
- V5 有黄色刷子(涂抹头)，V7 没有 → **零件丢失**
- 各视角的零件形态、比例、细节不同 → **非同一物体**

### 根因链

```
Blender PNG (V1-V7)     → 同一 GLB, 几何 100% 一致  ✅
    ↓ Gemini AI
Enhanced JPG (V1-V7)    → 每张独立生成, 几何不一致  ✗
```

Gemini 的行为：看到简化灰色几何体 → "想象"出弹簧、螺栓、刷子等细节 →
每次想象结果不同 → 多视角不一致。

Prompt 中的 "Keep ALL geometry EXACTLY" 是**文本软约束**，
Gemini 不保证遵守。对于复杂机械结构，软约束失效率很高。

### 两种后端对比

| 后端 | 几何锁定方式 | 一致性 | 是否解决此问题 |
|------|-----------|--------|-------------|
| **gemini** | 文本 prompt（软约束） | 低 | 否 |
| **comfyui** | ControlNet depth + canny（硬约束） | 高 | **是** |

## 2. 修复方案

### 核心思路

问题不在 prompt 文本，而在**锁定机制**。文本无法锁几何，
需要用**图像级约束**（depth map, edge map, segmentation mask）。

### 2a. 短期修复：Gemini 后端增加参考图约束（工具层）

**修改文件**：`gemini_gen.py`（共享工具）

Gemini 支持多图输入。当前只传 1 张源图（或 2 张 source + reference）。
增加策略：对每个视角，额外传入**源图的 edge/outline 版本**作为几何参考。

```python
# gemini_gen.py — 增加 edge 参考图
# 在调用 Gemini 前，用 OpenCV Canny 从源 PNG 提取边缘图
# 作为第二张参考图传入，强化几何保持
import cv2
edges = cv2.Canny(cv2.imread(png_path, 0), 50, 150)
cv2.imwrite(edge_path, edges)
# 传给 Gemini: [source_png, edge_png] + prompt
```

**效果**：边缘图提供了像素级的轮廓约束，Gemini 更难"想象"出不存在的结构。
但仍是软约束，不能保证 100% 一致。

### 2b. 中期修复：切换到 ComfyUI 后端（推荐）

**修改文件**：`pipeline_config.json`（共享配置）

ComfyUI 后端使用 **ControlNet depth + canny 双约束**，在扩散过程中
从 noise 层面硬锁几何，只允许表面纹理变化。

```json
{
  "enhance": {
    "backend": "comfyui",
    "comfyui": {
      "host": "127.0.0.1",
      "port": 8188,
      "controlnet_depth_strength": 1.0,
      "controlnet_canny_strength": 0.8
    }
  }
}
```

**效果**：几何硬锁，多视角自然一致（同一 3D 结构从不同角度看，
ControlNet 保证每个像素都在正确位置）。

**依赖**：需要本地 GPU + ComfyUI 服务 + ControlNet 模型。

### 2c. 长期方案：Blender 多 pass + 精确 depth 输入 ComfyUI

**修改文件**：`render_config.py:setup_render_passes()`（已预留）

Phase 4 输出精确 depth EXR → ComfyUI 用精确 depth 替代 MiDAS 估算 →
ControlNet 约束更准确。

### 2d. Gemini 后端的降级策略（不增加代码的改善措施）

如果无法使用 ComfyUI，可在 prompt 中增加以下约束：

**修改文件**：`enhance_prompt.py`（共享工具）

```python
def _build_geometry_lock_reinforcement(rc, view_key):
    """生成强化几何锁定的 prompt 文本。"""
    return (
        "CRITICAL GEOMETRY RULES:\n"
        "- Count the parts in the input image. The output MUST have the EXACT same number.\n"
        "- Do NOT add springs, bolts, gears, or details not visible in the input.\n"
        "- Do NOT change the position, angle, or size of ANY part.\n"
        "- If a part looks like a plain cylinder, keep it as a plain cylinder.\n"
        "  Do NOT add coils, threads, fins, or other details.\n"
        "- The input image is a CAD render with CORRECT geometry.\n"
        "  Your job is ONLY to change surface color/texture/sheen.\n"
    )
```

## 3. 实施优先级

| 优先级 | 方案 | 修改文件 | 效果 | 依赖 |
|--------|------|---------|------|------|
| **P0** | 2d: prompt 强化 | `enhance_prompt.py` | 改善（不保证） | 无 |
| **P1** | 2a: Gemini + edge ref | `gemini_gen.py` | 改善（不保证） | opencv-python |
| **P2** | 2b: ComfyUI 后端 | `pipeline_config.json` | **解决** | GPU + ComfyUI |
| **P3** | 2c: 精确 depth | `render_config.py` | 精确锁定 | P2 + Blender pass |

## 4. 设计约束

- 只改共享工具和配置，不改中间产物
- Gemini 后端的改善是"best effort"，不能保证 100% 一致
- 完全解决需要 ComfyUI (ControlNet 硬约束)
- 所有改动对所有子系统自动生效
