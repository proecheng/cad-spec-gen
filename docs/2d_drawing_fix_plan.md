# 2D 工程图管线修复方案

> 来源：机械专业教授审图意见（`manreview/图纸问题(1).docx`）
> 零件：SLP-100 上固定板
> 日期：2026-04-07
> 状态：**v2.3.0 已实施** (Phase A-G 全部完成)

---

## 1. 问题清单与根因定位

教授对照 3D 模型与 2D 工程图，提出 7 个问题。逐项追溯到管线根因层级：

| # | 教授意见 | 状态 | 根因层级 | 根因文件 |
|---|---------|------|---------|---------|
| 1 | 三视图没放图框 | **已修复** | draw_three_view.py:save() | — |
| 2 | 3D 有 5 孔，2D 有 12 孔，位置对不上 | **未修复** | CAD_SPEC.md 缺零件特征定义 → gen_parts.py 无法生成孔 → 3D 光板 | cad_spec_extractors.py, gen_parts.py, part_module.py.j2 |
| 3 | 只标形状尺寸，缺位置尺寸 | **未修复** | auto_annotate() Phase 1 缺孔心定位逻辑 | cq_to_dxf.py |
| 4 | 技术要求应在图纸下方空白处 | **未修复** | add_technical_notes() 默认 pos=(27,275) 硬编码在左上角 | drawing.py, draw_three_view.py |
| 5 | 俯视图缺 A-A 剖切线 | **未修复** | 管线无剖视图支持，模板只生成 auto_three_view() | cq_to_dxf.py, part_module.py.j2 |
| 6 | 左视图剖面线不对，孔处不应打剖面线 | **未修复** | add_section_hatch_with_holes() 存在但未被自动管线调用 | cq_to_dxf.py |
| 7 | 尺寸线应水平，不应对角斜线 | **未修复** | allocate_dim_angles() 使用 45°/135° 散射角 | drawing.py |

---

## 2. 数据消费者追溯

`make_p100()` 是唯一几何源，所有下游均直接消费：

```
make_p100()
  ├─ assembly.py:92   → .translate(0,0,272) → assy
  │    └─ export_assembly() → SLP-000_assembly.step / .glb
  │         ├─ render_3d.py      → V1-V4 等轴/正交 PNG
  │         ├─ render_exploded.py → V5 爆炸图 PNG
  │         └─ render_section.py  → V6 剖切渲染 PNG (Blender Boolean)
  │
  ├─ build_all.py:41  → cq.exporters.export → SLP-100.step (单件)
  │
  └─ draw_p100_sheet() → auto_three_view + auto_annotate → .dxf → .png
```

**结论**：几何改动自动传播到 STEP/GLB/DXF/Blender 全部输出，3D 多视角一致性天然保持。

---

## 3. 修改方案（按管线层级）

### Layer 0: cad-spec 提取层（影响 #2）

**目标**：让 CAD_SPEC.md 自动生成 §X 零件特征清单。

| 文件 | 修改内容 |
|------|---------|
| `cad_spec_extractors.py` | 新增 `extract_part_features(lines, bom_parts)` — 交叉引用 §2(公差 Φ值)、§3(紧固件)、§4(连接矩阵"穿入上板 φ10H7")、§8(装配序列)，合并出每个零件的特征清单 |
| cad-spec skill 模板 | 新增 §X 零件特征清单的 Markdown 渲染逻辑 |

**产出格式**（自动生成在 CAD_SPEC.md 中）：

```markdown
## X. 零件特征清单

### SLP-100 上固定板
| 特征类型 | 尺寸 | 数量 | 位置(X,Y) | 公差 | 来源 |
|---------|------|------|----------|------|------|
| 通孔 | Φ24 | 2 | (-60,+30),(+60,-30) | +0.1/0 | §2.1 丝杠孔, §4 LS1/LS2 |
| 通孔 | Φ10H7 | 2 | (+60,+30),(-60,-30) | +0.015/0 | §2.1 导向轴孔, §4 GS1/GS2 |
| 螺纹孔 | M5 | 4 | KFL001 安装位 | — | §3 M5×20, §8 step7 |
```

### Layer 1: codegen 生成层（影响 #2, #5, #6）

| 文件 | 修改内容 |
|------|---------|
| `codegen/gen_parts.py` | 新增 `_parse_features(spec_path, part_name)` — 从 §X 提取特征列表；新增 `needs_section_view` 判断（零件含通孔/沉台/内腔 → True） |
| `templates/part_module.py.j2` | 新增 `{% for feat in features %}` 特征生成块（CadQuery `.hole()` / `.cboreHole()`）；新增 `{% if needs_section_view %}` 剖面叠加调用 |

**模板特征生成块示意**：

```jinja2
{% for feat in features %}
{% if feat.type == "through_hole" %}
    # {{ feat.source }} — {{ feat.count }}×Φ{{ feat.diameter }}
    body = body.faces(">Z").workplane().pushPoints({{ feat.positions }}).hole({{ feat.diameter }})
{% elif feat.type == "counterbore" %}
    body = body.faces(">Z").workplane().pushPoints({{ feat.positions }}).cboreHole({{ feat.diameter }}, {{ feat.cbore_d }}, {{ feat.cbore_depth }})
{% elif feat.type == "threaded_hole" %}
    # 螺纹孔简化为通孔 — {{ feat.source }}
    body = body.faces(">Z").workplane().pushPoints({{ feat.positions }}).hole({{ feat.tap_drill_d }})
{% endif %}
{% endfor %}
```

**模板剖面叠加调用示意**：

```jinja2
{% if needs_section_view %}
    from cq_to_dxf import auto_section_overlay
    auto_section_overlay(solid, sheet,
        cut_plane="YZ", label="A",
        hatch_on="left", indicator_on="top")
{% endif %}
```

### Layer 2: 2D 工具层（影响 #3, #4, #5, #6, #7）

#### 2a. drawing.py 修改

| 函数 | 修改 | 影响 |
|------|------|------|
| `allocate_dim_angles()` | 新增 `prefer_orthogonal=True` 参数，默认优先 0°/180°/90°/270° | #7 所有零件孔标注改为水平/垂直优先 |
| `add_technical_notes()` | 移除默认 `pos` 参数，强制调用方传入 | #4 配合 draw_three_view.py 动态计算 |
| **新增** `add_section_cut_indicator()` | 在视图上画 A-A 剖切位置指示线（GB/T 4458.6：两端粗短线 + 中间点划线 + 字母标注 + 观看方向箭头） | #5 |

#### 2b. cq_to_dxf.py 修改

| 函数 | 修改 | 影响 |
|------|------|------|
| `auto_annotate()` Phase 1 | 增加位置尺寸逻辑：孔心到基准边的水平/垂直距离。限数（每视图 ≤4 组）+ 对称去重 + AnnotationPlacer 防碰撞 | #3 |
| **新增** `auto_section_overlay()` | 叠加模式（不替换左视图）：(1) CadQuery `.section()` 提取剖切面轮廓 (2) 分离外边界与内孔边界 (3) 调用已有 `add_section_hatch_with_holes()` (4) 在 top 视图画剖切指示线 (5) 在 left 视图上方加 "A-A" 标注 | #5, #6 |

**为什么用叠加而非替换**：
- 左视图的 HLR 投影轮廓不动 → `calc_three_view_layout` 不受影响
- `auto_annotate` 的坐标体系不受干扰
- 对不需要剖视图的零件完全无影响

#### 2c. draw_three_view.py 修改

| 位置 | 修改 | 影响 |
|------|------|------|
| `save()` 方法 | 技术要求位置动态计算：layout 计算后取最低视图底边与标题栏顶边之间的空隙；空隙 ≥30mm 放下方，否则回退左上角 | #4 |

---

## 4. 一致性验证矩阵

| 下游消费者 | 改动传播路径 | 一致性 | 风险等级 |
|-----------|-------------|-------|---------|
| 单件 STEP | `make_p100()` → export | ✅ 孔自动出现 | 无 |
| 总装 STEP/GLB | `make_p100()` → assembly → export | ✅ 总装自动含孔 | 无 |
| V1-V4 Blender 渲染 | GLB → render_3d.py | ✅ 孔在所有视角可见 | 低：labels anchor 可能微调 |
| V5 爆炸图 | GLB → render_exploded.py | ✅ 零件含孔 | 无 |
| V6 剖切渲染 | GLB → render_section.py (Boolean) | ✅ 切面暴露孔截面 | 无 |
| 2D DXF 三视图 | `make_p100()` → auto_three_view (HLR) | ✅ 孔自动投影 | 无 |
| 2D DXF 剖面线 | auto_section_overlay 叠加 | ✅ 同一 solid 切面 | 新增功能 |
| 2D DXF 标注 | auto_annotate → 直径 + 位置尺寸 | ✅ 同一 solid 检测圆 | 防碰撞限数 |
| AI 增强 (Phase 5) | PNG → JPG (geometry locked) | ✅ 不改几何 | 无 |
| draw_top_plate.py (旧) | 不在管线中 | ⚠️ 残留 | 应标记废弃 |

---

## 5. 实施顺序

Layer 2 不依赖上游数据变化，可以立即生效且对所有零件通用，因此优先实施。

| 阶段 | 内容 | 修改文件 | 解决问题 | 状态 |
|------|------|---------|---------|------|
| **Phase A** | drawing.py 工具函数修复 | drawing.py | #4, #7 | ✅ 完成 |
| **Phase B** | cq_to_dxf.py 标注引擎增强 | cq_to_dxf.py | #3 | ✅ 完成 |
| **Phase C** | 剖面叠加管线 | drawing.py + cq_to_dxf.py | #5, #6 | ✅ 完成 |
| **Phase D** | draw_three_view.py 动态布局 | draw_three_view.py | #4 | ✅ 完成 |
| **Phase E** | cad-spec 特征提取 | cad_spec_extractors.py | #2 | ✅ 完成 |
| **Phase F** | codegen 模板增强 | gen_parts.py + part_module.py.j2 | #2 | ✅ 完成 |
| **Phase G** | 清理遗留 | draw_top_plate.py 标记废弃 | 维护性 | ✅ 完成 |

---

## 6. 设计约束

- **不修改中间产物**（p100.py, params.py 等）—— 只改管线工具和模板，重新生成即可
- **单源几何**：所有 2D/3D 输出均从 `make_<part>()` 单一函数派生
- **叠加不替换**：剖面线叠加到已有视图，不改动布局计算链
- **动态不硬编码**：技术要求位置由布局结果计算，不写死坐标
- **限数防碰撞**：位置尺寸每视图 ≤4 组，使用 AnnotationPlacer 管理偏移
