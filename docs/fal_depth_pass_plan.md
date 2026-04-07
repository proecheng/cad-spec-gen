# fal.ai Depth Pass 启用方案（二审修订版）

> 问题：fal 后端 canny-only 模式效果差（颜色失真、几何不锁定）
> 根因：Blender 不输出 depth EXR → fal 只有 canny 单约束
> 约束：不修改中间产物（render_3d.py 等），只改共享工具/模板
> 二审：修复 compositor 节点冲突、view_name 推断、渲染浪费、节点累积

---

## 1. 当前断裂点

```
render_config.py:setup_render_passes()   ← 完整实现，但从未被调用
    ↓
render_3d.py (产物)                      ← 不调用 setup_render_passes()
    ↓
Blender 只输出 RGB PNG，不输出 depth EXR
    ↓
fal_enhancer._find_depth_for_png() → "No depth map found"
    ↓
canny-only 模式 → 几何锁定不足 → 效果差
```

## 2. 一审方案问题（已否决）

render_pre handler + setup_render_passes() 方案有 4 个致命问题：
1. setup_render_passes() 的 `tree.nodes.clear()` 会摧毁 render_label_utils 的节点
2. view_name 从 camera 名推断不可靠（各子系统命名不同）
3. backend=fal 但 Phase 5 降级到 gemini → depth 白渲染
4. handler 在 7 视角渲染中累积 7 组重复节点

## 3. 二审方案：独立 depth-only 后渲染脚本

### 核心思路

**不在 render_3d.py 的渲染过程中注入 depth**，而是在 Phase 4 正常渲染
RGB 完成后，用一个**独立的轻量级 Blender 脚本**单独渲染 depth pass。

优势：
- **不干扰主渲染**：render_3d.py 的 compositor/label pass 完全不受影响
- **按需执行**：只在 Phase 5 实际需要 depth 时才渲染（不在 Phase 4 提前渲染）
- **不改产物**：独立脚本是共享工具，不是 render_3d.py 的一部分

### 数据流

```
Phase 4: cmd_render → render_3d.py → V1-V7 RGB PNG（不变）
    ↓
Phase 5: cmd_enhance (backend=fal)
    ↓ 检查：有 depth EXR？
    ↓ 无 → 调用 render_depth_only.py（新增共享工具）
    ↓
Blender -b -P render_depth_only.py --glb <path> --views V1,V2... --output-dir <dir>
    ↓ 极简脚本：加载 GLB → 对每个视角设相机 → 只渲染 depth pass
    ↓ 输出：V1_depth.exr, V2_depth.exr, ...
    ↓
fal_enhancer._find_depth_for_png() 找到 EXR
    ↓ convert_depth_exr_to_png() → PNG
    ↓ 上传 RGB + depth → fal.ai 双 ControlNet
```

### 不修改的文件
- `cad/<any>/render_3d.py` — 产物，不动
- `cad/<any>/render_config.json` — 产物，不动
- `render_config.py:setup_render_passes()` — 不调用（避免 clear nodes 问题）

### 修改/新增的文件

| 文件 | 类型 | 改动 |
|------|------|------|
| `render_depth_only.py` | **新增**共享工具 | 极简 Blender 脚本：GLB→depth EXR |
| `cad_pipeline.py` | 共享工具 | cmd_enhance：fal 缺 depth 时自动调用 render_depth_only.py |
| `cad_paths.py` | 共享工具 | SHARED_TOOL_FILES 不需加（此脚本不部署到子系统） |

## 4. 详细设计

### 4a. render_depth_only.py（新增共享工具）

极简 Blender 脚本（~80行），只做一件事：加载 GLB → 渲染 depth EXR。

```python
"""render_depth_only.py — 独立 depth pass 渲染脚本。

从 GLB 加载场景 → 对每个视角渲染 depth-only pass → 输出 EXR。
极简设计：不触碰主渲染的 compositor 节点，不依赖 render_config.py。

调用方式：
    blender -b -P render_depth_only.py -- \\
        --glb path/to/assembly.glb \\
        --config path/to/render_config.json \\
        --output-dir path/to/renders
"""
# 脚本逻辑：
# 1. 解析 --glb, --config, --output-dir
# 2. 导入 GLB
# 3. 从 render_config.json 读取 camera 列表（azimuth/elevation/distance）
# 4. 对每个视角：
#    a. 设置 camera 位置（复用 render_config.py:camera_to_blender）
#    b. 设置 Cycles 极简渲染（samples=1，只需 depth 不需质量）
#    c. 设置 compositor：Render Layers → depth → File Output (EXR)
#    d. bpy.ops.render.render()
#    e. 输出 {view_key}_depth.exr
# 5. 退出
```

**关键设计**：
- `samples=1`：depth pass 不需要多采样，1 sample 即精确（Cycles Z-pass）
- 渲染时间：7 视角 × 1 sample ≈ 10-15 秒（vs 主渲染 6 分钟）
- 独立 compositor：不与 render_3d.py 共享任何节点

### 4b. cad_pipeline.py cmd_enhance 按需触发

```python
# cmd_enhance() — 在 fal 后端处理前
if _active_backend == "fal":
    # 检查是否已有 depth
    _sample_png = pngs[0] if pngs else None
    if _sample_png:
        from fal_enhancer import _find_depth_for_png
        _depth, _is_tmp = _find_depth_for_png(_sample_png)
        if _is_tmp and _depth:
            os.remove(_depth)
        if not _depth:
            # 无 depth → 自动渲染
            log.info("  No depth maps found — rendering depth-only pass...")
            _depth_ok = _render_depth_only(render_dir, args, _pcfg)
            if not _depth_ok:
                log.warning("  Depth render failed — fal will use canny-only mode")
```

### 4c. _render_depth_only() 辅助函数

```python
def _render_depth_only(render_dir, args, pcfg):
    """调用 render_depth_only.py 生成 depth EXR。"""
    blender = get_blender_path()
    if not blender:
        return False
    
    sub_dir = get_subsystem_dir(args.subsystem)
    config_path = os.path.join(sub_dir, "render_config.json") if sub_dir else None
    
    # 找 GLB
    glb_path = None
    if config_path and os.path.isfile(config_path):
        with open(config_path) as f:
            rc = json.load(f)
        glb_name = rc.get("subsystem", {}).get("glb_file", "")
        for search_dir in [render_dir, DEFAULT_OUTPUT, os.environ.get("CAD_OUTPUT_DIR", "")]:
            candidate = os.path.join(search_dir, glb_name)
            if os.path.isfile(candidate):
                glb_path = candidate
                break
    
    if not glb_path:
        log.warning("  Cannot find GLB for depth rendering")
        return False
    
    depth_script = os.path.join(SKILL_ROOT, "render_depth_only.py")
    cmd = [blender, "-b", "-P", depth_script, "--",
           "--glb", glb_path,
           "--config", config_path,
           "--output-dir", render_dir]
    
    ok, _ = _run_subprocess(cmd, "render depth-only pass", timeout=120)
    return ok
```

## 5. 降级与通用性

### fal 不可用时的降级

```
fal_enhancer 尝试增强
    ├─ depth 存在 → 双 ControlNet (depth + canny) → 最佳效果
    ├─ depth 不存在（render_depth_only 失败或无 Blender）
    │   → canny-only 模式 → 效果较差但仍可用
    │   → 如果连续失败 → 降级到 gemini
    └─ fal API 本身失败 → 降级到 gemini → 再失败 → engineering
```

### 无 Blender 时

depth 渲染需要 Blender。如果 Blender 不可用：
- _render_depth_only() 返回 False
- fal 用 canny-only 模式（效果差但可运行）
- 如果 canny-only 效果太差 → 自动降级到 gemini

### 无 fal-client / 无 FAL_KEY 时

不触发 depth 渲染（_active_backend 不是 fal）→ 零开销。

### 已有 depth 时

_find_depth_for_png() 直接找到 → 不重复渲染。支持用户手动预渲染 depth。

## 6. 审查清单

| # | 要点 | 状态 |
|---|------|------|
| 1 | 不修改产物 (render_3d.py, render_config.json) | ✅ |
| 2 | 不干扰主渲染的 compositor / label pass | ✅ （独立脚本独立 session） |
| 3 | view_name 不靠推断 | ✅ （从 render_config.json camera keys 读取） |
| 4 | depth 按需渲染，不浪费 | ✅ （Phase 5 fal 缺 depth 时才触发） |
| 5 | 降级链完整：depth→canny-only→gemini→engineering | ✅ |
| 6 | 无 Blender 时优雅降级 | ✅ |
| 7 | 已有 depth 不重复渲染 | ✅ |
| 8 | depth 来自 Cycles 精确计算 | ✅ |
| 9 | samples=1 极快（10-15秒） | ✅ |
| 10 | 对所有子系统通用 | ✅ |
