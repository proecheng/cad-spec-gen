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
   - 读取对应子系统的 `render_config.json` 获取材质描述（`prompt_vars.material_descriptions`）
   - 使用统一 prompt 模板 `templates/prompt_enhance_unified.txt`
     - 按 `render_config.json` 的 `camera.V*.type` 字段自动切换视角特定内容
     - `prompt_data_builder.py` 从 `params.py` 自动生成材质/装配/约束数据
   - 用 render_config.json 中的变量填充模板占位符
   - 执行 `python gemini_gen.py --image <input.png> --model <model_id> "<filled prompt>"`（gemini_gen.py 路径通过 `cad_paths.get_gemini_script()` 或环境变量 `GEMINI_GEN_PATH` 定位）
   - 捕获 gemini_gen.py 的 stdout，提取 `保存:` 后的路径
   - 将输出文件重命名为 `V*_视图名_YYYYMMDD_HHMM_enhanced.ext`（与源 PNG 同目录），时间戳防止覆盖历史版本

### 核心原则

- **几何锁定**：prompt 首行必须写 "Keep ALL geometry EXACTLY unchanged"
- **材质来源**：所有材质描述从 render_config.json `prompt_vars` 读取，不要凭空编造
- **视角一致**：不同视角使用不同模板，确保爆炸图保留间距、正交图无透视

### 标准件增强

prompt 模板包含 `{standard_parts_description}` 占位符，由 `render_config.json` 的 `standard_parts` 数组填充：

```json
"standard_parts": [
  {"visual_cue": "Small cylinder (Φ22×68mm) under flange", "real_part": "Maxon ECX motor, silver housing..."},
  {"visual_cue": "Annular rings at bearing locations", "real_part": "MR105ZZ ball bearing, chrome steel..."}
]
```

Gemini 收到简化几何的位置描述 + 真实零件外观描述，将简化形状增强为逼真外观。如 `standard_parts` 为空，占位符替换为空字符串，不影响现有流程。

### 模型选择

`pipeline_config.json` 的 `enhance` 段配置 Gemini 模型：

```json
"enhance": {
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
