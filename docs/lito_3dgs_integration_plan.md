# LiTo / 3DGS 集成方案（终版）

> 基于 LiTo (ICLR 2026)、3DGS 生态、nvdiffrast 系列深度调研
> 审查原则：数据流一致性、数据来源单一、只改管线工具/模板/skill
> 日期：2026-04-07

---

## 0. 核心结论

1. **LiTo 无可用代码**，只能借鉴思想（外观分层、几何/外观解耦）
2. **6 视角是 3DGS 生态硬瓶颈**，优化类方法需 50+ 视角
3. **我们控制渲染器**（Blender Cycles），正向 bake PBR pass 比 ML 反推更准更快
4. **最高 ROI 改动**：消除 `prompt_data_builder.py` 中的重复数据源

---

## 1. 当前数据流审查

### 材质外观数据的实际流向

```
CAD_SPEC.md §2.3 surface_ra + §7 表面颜色
    ↓ 手动                           ↓ gen_parts.py → material_type="al"
render_config.json                   params.py / p*.py
  materials.*.preset="black_anodized"     material_type (用于 DXF 技术要求)
    ↓                                     ↓
    ├→ render_config.py:MATERIAL_PRESETS  prompt_data_builder.py
    │    (color, metallic, roughness)      generate_material_descriptions()
    │    ↓                                 ↓
    │  render_3d.py (Blender PBR)         [A] end_effector: 硬编码 mat_map (40+ 行)
    │                                     [B] 非 EE: derive_from_rc() → _PRESET_APPEARANCE
    │                                           ↓
    ↓                                     enhance_prompt.py → AI prompt
  Blender 渲染 V1-V6 PNG             → gemini_gen.py / comfyui_enhancer.py
```

### 发现的 3 个数据一致性问题

**问题 A：材质外观有 3 个独立数据源**

| 数据源 | 文件 | 内容 | 谁消费 |
|--------|------|------|-------|
| `MATERIAL_PRESETS` | render_config.py:30 | PBR 参数 (color/metallic/roughness) | Blender 渲染 |
| `mat_map` | prompt_data_builder.py:532 | 英文外观描述 (end_effector 专用) | AI prompt |
| `_PRESET_APPEARANCE` | prompt_data_builder.py:845 | 英文外观描述 (通用 fallback) | AI prompt |

这三个数据源**各自独立维护**，改一个不会自动更新另外两个。
例如 `MATERIAL_PRESETS["black_anodized"]` 的 roughness 改了，
但 `_PRESET_APPEARANCE["black_anodized"]` 的文字描述不会自动更新。

**问题 B：`mat_map` 是 end_effector 子系统专用，不通用**

`generate_material_descriptions()` 中的 `mat_map` 包含
"flange_body"、"peek_ring"、"motor" 等 end_effector 专用键名。
对 lifting_platform 等其他子系统走 fallback 路径 `derive_from_rc()`。

**问题 C：`resolve_preset()` 被提议但无调用方**

上一版方案在 `cad_spec_defaults.py` 中新增 `resolve_preset()`，
但没有定义谁在什么时机调用它。render_config.json 是手写的，
codegen 管线中没有生成 render_config.json 的步骤。

---

## 2. 修复方案

### 原则

- **数据源归一**：材质外观描述只在 `MATERIAL_PRESETS` 中定义一次
- **只改共享工具**：render_config.py、prompt_data_builder.py、
  enhance_prompt.py、cad_spec_defaults.py（全在项目根目录）
- **不改产物**：不改 render_config.json、render_3d.py、p*.py、params.py
- **通用性**：改动对所有子系统自动生效

### 2a. 数据源归一：MATERIAL_PRESETS 增加 appearance 字段

**修改文件**：`render_config.py`（共享工具，项目根目录）

当前每个 preset 只有 PBR 参数。增加 `appearance` 文本描述：

```python
MATERIAL_PRESETS = {
    "black_anodized": {
        "color": (0.05, 0.05, 0.05, 1.0),
        "metallic": 0.85,
        "roughness": 0.30,
        "appearance": "hard anodized aluminum, matte dark charcoal, "
                      "micro-porous surface, soft elongated highlights "
                      "at grazing angle, faint silver edge sheen",
    },
    "brushed_aluminum": {
        "color": (0.82, 0.82, 0.84, 1.0),
        "metallic": 1.0,
        "roughness": 0.18,
        "anisotropic": 0.6,
        "appearance": "brushed 6061 aluminum, fine parallel grain marks, "
                      "silver-gray, bright anisotropic streaks perpendicular "
                      "to brush direction, strong white edge reflection",
    },
    # ... 其他 15 个 preset 同理
}
```

**LiTo 借鉴点**：描述文本按 SH 分层思路组织（base → specular → fresnel），
但不引入 SH 系数——用人类可读文本，因为消费者是 AI prompt 而非 3DGS decoder。

**数据来源**：从同一 preset 的 PBR 参数物理推导：
- metallic=0.85 + roughness=0.30 → "soft elongated highlights"
- metallic=1.0 + roughness=0.18 → "bright anisotropic streaks"
- 不引入任何外部数据源。

### 2b. 消除重复数据源：prompt_data_builder.py 读 MATERIAL_PRESETS

**修改文件**：`prompt_data_builder.py`（共享工具，项目根目录）

将 `derive_material_descriptions_from_rc()` 中的 `_PRESET_APPEARANCE`
**删除**，改为从 `MATERIAL_PRESETS` 读取：

```python
def derive_material_descriptions_from_rc(rc):
    """从 render_config.json 的 preset 推导材质描述。

    数据源归一：从 render_config.py:MATERIAL_PRESETS 的 appearance 字段读取，
    不再维护独立的 _PRESET_APPEARANCE 映射。
    """
    from render_config import MATERIAL_PRESETS

    materials = rc.get("materials", {})
    result = []
    for mat_id, mat_cfg in materials.items():
        label = mat_cfg.get("label", mat_id)
        preset_name = mat_cfg.get("preset", "")
        preset = MATERIAL_PRESETS.get(preset_name, {})
        appearance = preset.get("appearance", preset_name.replace("_", " "))
        if label and appearance:
            result.append({"visual_cue": label, "material_desc": appearance})
    return result
```

**效果**：`_PRESET_APPEARANCE` 不再存在，材质描述只有 `MATERIAL_PRESETS` 一个源头。
修改 `MATERIAL_PRESETS` 中的 appearance 字段，Blender 渲染用的 PBR 参数
和 AI prompt 用的文字描述**同步更新**。

### 2c. material_type → preset 自动映射（运行时 fallback）

**修改文件**：`cad_spec_defaults.py`（共享工具）+ `prompt_data_builder.py`（共享工具）

在 `cad_spec_defaults.py` 中新增映射：

```python
MATERIAL_TYPE_TO_DEFAULT_PRESET = {
    "al":     "brushed_aluminum",
    "steel":  "dark_steel",
    "peek":   "peek_amber",
    "nylon":  "white_nylon",
    "rubber": "black_rubber",
}

def default_preset_for_material_type(material_type: str) -> str:
    """material_type → 默认 render preset 名称。"""
    return MATERIAL_TYPE_TO_DEFAULT_PRESET.get(material_type, "brushed_aluminum")
```

在 `prompt_data_builder.py` 的 **通用路径**中作为 fallback 消费：

```python
def auto_enrich_material_data(rc, cad_dir=None):
    """当 render_config.json 缺少材质描述时，从 params.py 的 material_type 自动补充。"""
    if rc.get("prompt_vars", {}).get("material_descriptions"):
        return  # 已有描述，不覆盖

    # 尝试从 params.py 读 material_type 信息
    # ... (已有逻辑读 params.py)

    from cad_spec_defaults import default_preset_for_material_type
    from render_config import MATERIAL_PRESETS
    # 用 material_type → preset → appearance 自动生成
```

**数据流修复后**：

```
CAD_SPEC.md §2.3 material_type
  ↓ gen_parts.py (codegen)
params.py: material_type = "al"
  ↓ prompt_data_builder.py (运行时)
cad_spec_defaults.py: default_preset_for_material_type("al") → "brushed_aluminum"
  ↓
render_config.py: MATERIAL_PRESETS["brushed_aluminum"]["appearance"]
  ↓
enhance_prompt.py → AI prompt material_descriptions
```

**数据源唯一**：从 CAD_SPEC.md → material_type → preset → appearance，
每一步都有唯一的权威来源，无并行数据源。

### 2d. 视角感知材质 prompt

**修改文件**：`enhance_prompt.py`（共享工具）

当前 `_build_consistency_rules()` 对所有视角生成相同的一致性约束。
增强为根据相机仰角选择最相关的外观描述：

```python
def _build_view_material_emphasis(rc, view_key):
    """根据当前视角方位，为材质描述补充视角相关的外观重点。

    低仰角 → 强调 fresnel/edge sheen
    中仰角 → 强调 specular highlights
    俯视   → 强调 base color + environment reflection
    """
    cam = rc.get("camera", {}).get(view_key, {})
    elev = abs(cam.get("elevation_deg", 30))

    if elev < 20:
        return "At this grazing angle, emphasize edge sheen and Fresnel reflections."
    elif elev > 60:
        return "From this steep overhead angle, emphasize base diffuse color and ambient occlusion shadows."
    return ""
```

消费的数据全部来自 render_config.json 的 camera 配置（已有字段），
不引入新数据源。

### 2e. Blender 多 pass 输出（工具层预留）

**修改文件**：`render_config.py`（共享工具）

新增 Blender compositor 设置函数，但**不修改任何 render_3d.py 产物**。
Per-subsystem 脚本在更新时自行决定是否调用：

```python
def setup_render_passes(scene, output_dir, view_name, config):
    """为 Blender 场景启用多 pass 输出。

    读取 config["render_passes"]（可选字段），设置 Cycles compositor。
    若 config 中无 render_passes 字段，则跳过（向后兼容）。

    Per-subsystem render_3d.py 可在渲染前调用此函数。
    现有 render_3d.py 不调用 = 不输出 pass = 行为不变。
    新子系统的 render_3d.py 可选择调用。
    """
    passes_cfg = config.get("render_passes", {})
    if not passes_cfg.get("enabled", False):
        return  # 默认不启用，向后兼容
    # ... compositor node setup
```

**修改文件**：`templates/render_config.schema.json`（共享模板）

新增可选字段定义：

```json
"render_passes": {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean", "default": false},
        "passes": {
            "type": "array",
            "items": {"type": "string", "enum": ["depth","normal","diffuse_color","glossy_color"]}
        }
    }
}
```

**不修改任何产物**。现有 render_3d.py 不调用新函数 = 行为完全不变。

---

## 3. 修改清单（全为共享工具/模板）

| # | 文件 | 类型 | 改动 | 对应 |
|---|------|------|------|------|
| 1 | `render_config.py` | 共享工具 | MATERIAL_PRESETS 增加 `appearance` 字段 | 2a |
| 2 | `prompt_data_builder.py` | 共享工具 | 删除 `_PRESET_APPEARANCE`，改读 MATERIAL_PRESETS | 2b |
| 3 | `cad_spec_defaults.py` | 共享工具 | 新增 `default_preset_for_material_type()` | 2c |
| 4 | `prompt_data_builder.py` | 共享工具 | `auto_enrich_material_data` 增加 fallback 调用 | 2c |
| 5 | `enhance_prompt.py` | 共享工具 | 新增 `_build_view_material_emphasis()` | 2d |
| 6 | `render_config.py` | 共享工具 | 新增 `setup_render_passes()` 函数 | 2e |
| 7 | `templates/render_config.schema.json` | 共享模板 | 新增 `render_passes` 可选字段 | 2e |

**不修改的文件**（产物 / 中间产物）：
- `cad/<sub>/render_3d.py` — 不改
- `cad/<sub>/render_config.json` — 不改
- `cad/<sub>/params.py` — 不改
- `cad/<sub>/p*.py` — 不改

---

## 4. 数据流验证（修复后）

```
CAD_SPEC.md
  ├─ §2.3 material_type → gen_parts.py → params.py (已有)
  ├─ §7 surface_color   → render_config.json (手写，已有)
  ↓
render_config.json materials.*.preset  ← 手写，唯一的 per-subsystem 配置点
  ↓
render_config.py:MATERIAL_PRESETS      ← 唯一的外观权威源
  ├─ PBR params (color, metallic, roughness) → Blender 渲染
  ├─ appearance (文字描述)                    → prompt_data_builder.py
  │                                              ↓
  │                                   enhance_prompt.py
  │                                     + _build_view_material_emphasis()
  │                                              ↓
  │                                   {material_descriptions} in prompt
  │                                              ↓
  │                                   gemini_gen.py / comfyui_enhancer.py
  ↓
Phase 4 渲染 → V1-V6 PNG
Phase 5 增强 → Enhanced JPG (材质一致)

(fallback 路径：render_config.json 无 preset 时)
params.py: material_type
  ↓ cad_spec_defaults.py:default_preset_for_material_type()
  ↓ MATERIAL_PRESETS[resolved_preset]["appearance"]
  ↓ prompt material_descriptions (自动补充)
```

**验证要点**：
- 外观描述只有 `MATERIAL_PRESETS["..."]["appearance"]` 一个源头 ✓
- PBR 参数和外观描述在同一个 dict 中，同步维护 ✓
- 不改任何 `cad/<sub>/` 下的文件 ✓
- material_type → preset 映射通过运行时 fallback，不需要新的 codegen 步骤 ✓
- `render_passes` 是可选字段，默认 disabled，向后兼容 ✓

---

## 5. 不采纳的方案

| 方案 | 不采纳原因 |
|------|-----------|
| appearance_hints 分 4 层 (base/specular/fresnel/env) | 过度设计。消费者是 AI prompt（自然语言），分 4 个 key 不如一段完整描述 |
| 在 render_3d.py 中加 depth pass 代码 | render_3d.py 是 per-subsystem 产物，不应直接改 |
| render_config.json 中加 SH 系数 | 无上游数据源，且 render_config.json 是产物 |
| 新增 gen_render_config.py codegen 步骤 | 引入复杂度不匹配收益，手写 render_config.json + 运行时 fallback 更实用 |
| 完整集成 LiTo / 3DGS fitting | 代码未开源、6 视角不足、我们控制渲染器无需反推 |

---

## 6. 长期架构预留（注释级，不写实现代码）

以下仅在共享工具文件中以注释形式预留接口，不增加实际功能代码：

- `cad_pipeline.py`：Phase 4.5 3DGS fitting 注释占位
- `render_config.py`：`setup_render_passes()` 已实现但默认 disabled
- `templates/render_config.schema.json`：`enhance_mode` 字段预留

```json
"enhance_mode": {
    "type": "string",
    "enum": ["gemini", "comfyui"],
    "default": "gemini",
    "description": "Phase 5 backend. Future: '3dgs_rerender' when 3DGS fitting available"
}
```

**落地条件**：LiTo 开源 / gsplat 支持 6 视角 / nvdiffrecmc 验证可用。

---

## 7. 实施顺序

| 步骤 | 内容 | 文件 | 依赖 |
|------|------|------|------|
| **S1** | MATERIAL_PRESETS 增加 appearance | `render_config.py` | 无 |
| **S2** | 删 _PRESET_APPEARANCE，改读 MATERIAL_PRESETS | `prompt_data_builder.py` | S1 |
| **S3** | default_preset_for_material_type | `cad_spec_defaults.py` | 无 |
| **S4** | auto_enrich 增加 preset fallback | `prompt_data_builder.py` | S1, S3 |
| **S5** | 视角感知材质 emphasis | `enhance_prompt.py` | 无 |
| **S6** | setup_render_passes + schema | `render_config.py` + templates | 无 |

S1-S5 可立即实施，零外部依赖，对所有子系统自动生效。
S6 预留能力，默认 disabled，不影响现有行为。

---

## 附录：调研工具链接

| 工具 | 关联点 | URL |
|------|-------|-----|
| LiTo | SH 分层外观思想 | https://arxiv.org/abs/2603.11047 |
| gsplat | 底层 3DGS 光栅化 (pip) | https://github.com/nerfstudio-project/gsplat |
| nvdiffrecmc | 已知网格 + 图片 → PBR (lock_pos) | https://github.com/NVlabs/nvdiffrecmc |
| GaMeS | 网格约束 3DGS | https://github.com/waczjoan/gaussian-mesh-splatting |
| Mesh2Splat | GLB → 3DGS 即时转换 (C++, Windows) | https://github.com/electronicarts/mesh2splat |
| DN-Splatter | depth 监督 3DGS (nerfstudio 插件) | https://github.com/maturk/dn-splatter |
| GeoSplatting | 网格初始化 + PBR 分解 | https://github.com/PKU-VCL-Geometry/GeoSplatting |
| TexGaussian | 网格 → AI 生成 PBR 纹理 | https://github.com/ymxbj/TexGaussian |
