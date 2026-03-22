# /cad-enhance — Gemini AI 增强（Blender PNG → 照片级 JPG）

用户输入: $ARGUMENTS

## 指令

将 Blender Cycles 渲染的 PNG 图片增强为照片级 JPG。几何形状 100% 锁定，仅更换表面材质外观。

### 路由规则

1. **无参数** → 显示用法：
   ```
   /cad-enhance <png_path>                    — 增强单张图片
   /cad-enhance --all --dir <render_dir>      — 增强目录下所有 V*.png
   /cad-enhance --view V1 --dir <render_dir>  — 增强指定视角
   ```

2. **有参数** → 执行增强：
   - 读取 `render_config.json` 获取材质描述（`prompt_vars.material_descriptions`）
   - 根据文件名选择 prompt 模板：
     - V1/V2/V3 → `templates/prompt_enhance.txt`
     - V4 → `templates/prompt_exploded.txt`
     - V5 → `templates/prompt_ortho.txt`
   - 用 render_config.json 中的变量填充模板占位符
   - 执行 `gemini_gen.py --image <input.png> "<filled prompt>"`
   - 将输出 JPG 复制到与输入 PNG 同目录，命名为 `*_enhanced.jpg`

### 核心原则

- **几何锁定**：prompt 首行必须写 "Keep ALL geometry EXACTLY unchanged"
- **材质来源**：所有材质描述从 render_config.json `prompt_vars` 读取，不要凭空编造
- **视角一致**：不同视角使用不同模板，确保爆炸图保留间距、正交图无透视
