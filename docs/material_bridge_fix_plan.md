# 3D 渲染材质桥接修复方案

> 问题：Gemini 增强后各视角几何不一致（法兰大小、弹簧有无、刷子位置变化）
> 根因：不是 Gemini prompt 问题，是 Blender 渲染的输入 PNG 质量不足
> 日期：2026-04-07

---

## 1. 根因链

```
_sync_bom_to_render_config() 只处理 assembly 级零件 (is_assembly=True)
    ↓ 只有 6 个总成 (GIS-EE-001~006) 被映射到 components
    ↓ 11 个自制零件 + 26 个标准件没有 component→material 桥接
    ↓ render_3d.py assign_materials() 的 bom_id 匹配只命中 6 个
    ↓ 其余 30 个零件 → Priority 3: default gray (0.6, 0.6, 0.62)
    ↓ Blender PNG 中大部分零件是相同的灰色
    ↓ Gemini 无法区分零件 → 每张图独立"想象"细节
    ↓ 多视角几何不一致
```

## 2. 数据流分析

### 当前流向

```
CAD_SPEC.md §5 BOM
    ↓ parse_bom_tree()
    ↓ _sync_bom_to_render_config()  ← 只处理 assembly (6个)
    ↓ render_config.json components (8个，含手写的2个)
    ↓ render_config.json materials (21个预设)
    ↓ render_3d.py resolve_bom_materials() → assign_materials()
    ↓ GLB 中 36 个对象，只有 8 个有正确材质
    ↓ 28 个 → default gray
```

### 需要修复的流向

```
CAD_SPEC.md §5 BOM (全部零件)
    ↓ parse_bom_tree()
    ↓ _sync_bom_to_render_config()  ← 处理 ALL 零件（assembly + leaf）
    ↓ render_config.json components (36个，全覆盖)
    ↓ render_config.json materials (自动从 BOM material 推导 preset)
    ↓ render_3d.py → 36 个对象全部有正确 PBR 材质
    ↓ Blender PNG 中每个零件有正确颜色（深灰法兰、琥珀PEEK、银储罐…）
    ↓ Gemini 只需增强纹理，无需"想象"结构
```

## 3. 修复方案

### 3a. _sync_bom_to_render_config 扩展为全零件映射

**修改文件**：`cad_pipeline.py`（共享工具）

**当前**：line 430 `assemblies = [p for p in parts if p["is_assembly"]]`
只取 assembly 级。

**修改**：处理所有零件（assembly + 自制 leaf + 标准件），每个都生成
component + material 条目。

```python
# 改为处理所有零件
all_bom_parts = [p for p in parts if p["part_no"]]

for part in all_bom_parts:
    pno = part["part_no"]
    name_cn = part["name_cn"]
    
    # 从 BOM material 字段推导 preset
    mat_text = part.get("material", "")
    preset = _infer_preset(mat_text)  # 复用已有的 _MAT_PRESET 映射
    
    # component key: 从 part_no 派生（strip prefix, lowercase）
    comp_key = _part_no_to_comp_key(pno)
    
    # 只在不存在时创建（不覆盖手写条目）
    if comp_key not in components:
        components[comp_key] = {
            "name_cn": name_cn,
            "bom_id": pno,
            "material": comp_key,
        }
    if comp_key not in materials:
        materials[comp_key] = {
            "preset": preset,
            "label": name_cn,
        }
```

### 3b. assembly.py 对象名 → bom_id 匹配修复

**现状**：assembly.py 的 `assy.add(p, name="EE-001-01")`，
render_3d.py 的 bom_id 匹配用 `if bid in name_lower`。

**问题**：`resolve_bom_materials()` 做了 normalize（strip prefix + lowercase），
所以 bom_id `GIS-EE-001-01` → `ee-001-01`，Blender 对象名 `EE-001-01` →
`ee-001-01`。匹配应该能工作。

**验证点**：确认 normalize 逻辑一致。如果 assembly.py 用的是
`EE-001-01`（已 strip GIS-前缀），而 resolve 输入是 `GIS-EE-001-01`，
normalize 后都是 `ee-001-01` → 匹配成功。

### 3c. 标准件材质推导

**标准件**没有 BOM material 字段（只有型号），需要从零件名推导：
- 电机/减速器 → `brushed_aluminum`
- 弹簧 → `stainless_304`
- 轴承 → `stainless_304`
- O型圈/密封件 → `black_rubber`
- 传感器 → `dark_steel`
- 齿轮泵 → `brushed_aluminum`

**修改文件**：`cad_pipeline.py` — 在 `_MAT_PRESET` 映射中增加标准件关键词：

```python
_MAT_PRESET = {
    # 自制件材料
    "铝": "brushed_aluminum", "Al": "brushed_aluminum",
    "7075": "black_anodized", "6063": "brushed_aluminum",
    "钢": "stainless_304", "SUS": "stainless_304",
    "PEEK": "peek_amber",
    "橡胶": "black_rubber", "硅橡胶": "black_rubber", "NBR": "black_rubber",
    "塑料": "white_nylon", "尼龙": "white_nylon",
    "铜": "copper",
    # 标准件名称关键词
    "电机": "dark_steel", "减速": "brushed_aluminum",
    "弹簧": "stainless_304", "轴承": "stainless_304",
    "O型圈": "black_rubber", "密封": "black_rubber",
    "传感器": "dark_steel", "探头": "dark_steel",
    "齿轮泵": "brushed_aluminum", "联轴": "stainless_304",
}
```

对标准件，用 name_cn（零件名）而非 material（型号）来匹配。

## 4. 不修改的文件

- `cad/<sub>/render_config.json` — 产物，由 `_sync_bom_to_render_config` 自动更新
- `cad/<sub>/assembly.py` — 产物
- `cad/<sub>/render_3d.py` — per-subsystem 部署副本，不改
- `render_config.py:resolve_bom_materials()` — 已正确，无需改

## 5. 数据一致性验证

修改后的数据流：

```
CAD_SPEC.md §5 BOM         ← 唯一数据源
    ↓ parse_bom_tree()       (codegen/gen_build.py, 共享工具)
    ↓
_sync_bom_to_render_config() (cad_pipeline.py, 共享工具)
    ├→ 自制件: material 字段 → _MAT_PRESET → preset
    ├→ 标准件: name_cn 字段 → _MAT_PRESET → preset
    ├→ 总成:   子零件 material → preset
    ↓
render_config.json components + materials  (产物, 自动生成)
    ↓
render_3d.py resolve_bom_materials()       (共享工具部署副本)
    ↓ bom_id→material→PBR params
    ↓
assign_materials()                          (render_3d.py)
    ↓ 所有 36 个对象有正确颜色
    ↓
Blender PNG (视觉信息丰富)
    ↓
Gemini AI (只需增强纹理, 不需想象结构)
    ↓
Enhanced JPG (几何保持一致)
```

## 6. 审查结论

- 数据源唯一性：✅ 全部来自 CAD_SPEC.md §5 BOM
- 只改工具文件：✅ 只改 cad_pipeline.py
- 数据流一致性：✅ leaf 零件 bom_id 是完整编号，longest-prefix match 优先级正确
- 通用性：✅ _MAT_PRESET 用中文关键词，对任何子系统有效
- 向后兼容：✅ 不覆盖已有手写 components/materials 条目

## 7. 实施步骤

| # | 操作 | 文件 |
|---|------|------|
| 1 | `_sync_bom_to_render_config` 扩展为全零件 | `cad_pipeline.py` |
| 2 | `_MAT_PRESET` 增加标准件关键词 | `cad_pipeline.py` |
| 3 | 标准件用 name_cn 匹配（而非 material 字段） | `cad_pipeline.py` |
| 4 | 重跑 codegen → render_config.json 自动更新 | 无需手改产物 |
| 5 | 重跑 render → 验证材质分配 | 验证 |
| 6 | 重跑 enhance → 验证多视角一致性 | 验证 |
