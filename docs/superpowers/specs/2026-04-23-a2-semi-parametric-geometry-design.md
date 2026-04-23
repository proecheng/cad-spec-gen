# A2 自制件半参数几何升级 — 设计文档

**日期**：2026-04-23
**状态**：已确认，待实施
**关联 spec**：`docs/superpowers/specs/2026-04-20-track-a-visual-fidelity-quick-wins-design.md` §4、§6.2、§9

---

## 1. 问题背景

`gen_parts.py` 生成的 11 个自制件 `ee_*.py` 全部使用 envelope box/cylinder，几何视觉上无法区分法兰、壳体、支架、弹簧机构。

两个根因：
1. **`dim_tolerances` 混池 bug**：`_parse_annotation_meta` 把子系统级所有公差全量返回给每件零件，`ee_001_01.py` 和 `ee_003_03.py` 的 `dim_tolerances` 逐字相同（法兰/悬臂/弹簧销混合）。若直接在此基础上按前缀推断尺寸，会喂给法兰件荒诞的弹簧销尺寸。
2. **无模板路由**：`gen_parts.py` 里的 `_decision`（routing 结果）只打印，不影响几何生成。

---

## 2. 设计决策

### 2.1 A2-0 过滤策略：语义前缀映射（方案 A）

**决策**：在 Python 代码里维护前缀→类别关键词映射表，过滤时对每条 tolerance 名称做前缀 match。

**放弃方案 B（CAD_SPEC.md 手动标注 part_no）**：不同用户的 dim_tolerances 数量不可预期，手动标注负担随项目规模线性增长，与"零配置/傻瓜式"原则相悖。

**映射表**（集中维护于 `gen_parts.py`）：

```python
_TOL_PREFIX_CATEGORY: dict[str, str] = {
    "FLANGE":   "法兰",
    "HOUSING":  "壳体",
    "SPRING":   "弹簧",
    "ARM":      "悬臂",
    "BRACKET":  "支架",
    "SLEEVE":   "套筒",
    "CLAMP":    "夹",
}
```

过滤规则：
- 名称命中某前缀 → 仅保留给 `name_cn` 含对应关键词的零件
- 名称未命中任何前缀 → 视为通用条目，保留给所有零件

逃生口：`CAD_SPEC_GEN_DIM_FILTER=off` 环境变量完全跳过过滤，保持原有行为。

### 2.2 模板几何层次：L2（精细）

**决策**：全部 8 类模板均生成 L2 几何（≥20 面），而非 L1 简化几何。

**L1**（圆盘 + 孔）视觉上刚好"像"该类零件但细节不足；**L2** 加入凸台、圆角、加强筋、线圈端面等特征，在 Track C（精确几何）实现前提供足够辨识度。sleeve/plate/arm/cover 4 类新增模板面数要求放宽到 ≥20（几何相对简单）。

### 2.3 参数缺失策略：主填/次默（方案 Y）

**决策**：主尺寸（决定几何形态的参数）缺任意一个 → 降级到 envelope primitive + warning，不 raise。次级参数（圆角、凸台等修饰特征）缺失 → 使用固定默认值，不降级。

**放弃方案 X（比例估算）**：估算链长时误差叠加，产出"奇怪的法兰"，调试困难。方案 Y 失败边界清晰。

### 2.4 模板路由架构：独立函数（方案 β）

**决策**：新增 `match_semi_parametric_template(name_cn)` 纯函数，与现有 `route()` 解耦。

**放弃方案 α（复用 `route()` 输出）**：`route()` 为 SW toolbox（Track B）设计，其模板命名和我们的 4 类工厂函数未必对齐；且 Track B 尚未实施，依赖它会造成阻抗失配。

两套"路由"职责明确：
- `route()` → SW toolbox 选 `.j2` 模板文件（Track B 用途）
- `match_semi_parametric_template()` → 几何代码生成选工厂函数（Track A 用途）

### 2.5 用户级命名覆盖：`template_mapping.json`

**决策**：在项目根目录（CAD_SPEC.md 旁边）支持可选的 `template_mapping.json`，用户可声明自己的命名习惯，无需改代码。

**动机**：不同用户对同一类零件命名差异很大（"连接盘"/"固定盘"/"法兰" 均指 flange）。内置关键词表只能覆盖常见命名，`template_mapping.json` 提供零配置扩展出口。

```json
{
  "连接盘":  "flange",
  "固定盘":  "flange",
  "外壳":    "housing",
  "机箱":    "housing",
  "限力器":  "spring_mechanism",
  "缓冲件":  "spring_mechanism",
  "轴套":    "sleeve",
  "衬套":    "sleeve",
  "底板":    "plate",
  "安装板":  "plate",
  "端盖":    "cover",
  "盖板":    "cover",
  "连杆":    "arm",
  "摇臂":    "arm"
}
```

查找顺序：`template_mapping.json`（用户覆盖，精确匹配） → 内置 `_TEMPLATE_KEYWORDS`（包含匹配） → `None`（fallback）。文件不存在时静默跳过，行为与原来一致。

---

## 3. 整体数据流

```
CAD_SPEC.md §2.1 dim_tolerances
    │
    ▼
_parse_annotation_meta(spec_path, part_name_cn)   ← A2-0 修复
    │  _TOL_PREFIX_CATEGORY 前缀映射
    │  未命中前缀 → 通用，保留
    │  CAD_SPEC_GEN_DIM_FILTER=off → 跳过过滤
    ▼
part_meta["dim_tolerances"]（已净化）
                                    ┐
§6.4 envelope bbox ─────────────────┤
§6.3 serial_chain.axis ─────────────┤
                                    ▼
match_semi_parametric_template(name_cn, mapping_path)   ← A2-3 新增
    │  1. template_mapping.json 精确匹配（用户覆盖）
    │  2. 内置 _TEMPLATE_KEYWORDS 包含匹配（法兰/壳体/套筒/板/盖/悬臂…）
    │  无匹配 → None → 保持 envelope primitive
    ▼
_apply_template_decision(geom, tpl_type, part_meta, envelope)   ← A2-3 新增
    │  主尺寸缺失 → 返回原 geom + warning
    │  次级参数缺失 → 固定默认值
    ▼
codegen/part_templates/{flange,housing,bracket,spring_mechanism,sleeve,plate,arm,cover}.py
    │  make_flange / make_housing / make_bracket / make_spring_mechanism
    │  make_sleeve / make_plate / make_arm / make_cover
    │  返回 CadQuery 表达式字符串（或 None 表示主尺寸缺失）
    ▼
part_module.py.j2 {% elif geom_type == "flange" %} 等 8 个新增分支
    ▼
ee_001_01.py（L2 几何，≥30 face）
ee_001_02.py（sleeve L2，≥20 face）  ← 新覆盖
```

---

## 4. 各模板规格

### 4.1 参数来源优先级（全部模板统一）

1. A2-0 过滤后的 `dim_tolerances`（最权威）
2. `§6.4 envelope bbox`（推算缺失主尺寸的兜底）
3. 固定默认值（次级参数）
4. 必填主尺寸在 dim_tolerances 和 envelope 双双缺失 → 工厂函数返回 `None` → 调用方退回 envelope primitive + warning

> 注：envelope bbox 来自 `parse_envelopes(spec_path)`，通常总能解析到。"主尺寸缺失"主要发生在 envelope 解析失败或该 part_no 无 envelope 条目的边缘情况。

### 4.2 `make_flange`

| 参数 | 类型 | 来源 |
|---|---|---|
| `od` | 必填 | `FLANGE_OD` 或 envelope max(w,d) |
| `id` | 必填 | `FLANGE_ID` 或 envelope min(w,d)×0.3 |
| `thickness` | 必填 | `FLANGE_H` 或 envelope h |
| `bolt_pcd` | 必填 | `FLANGE_BOLT_PCD` 或 od×0.75 |
| `bolt_count` | 次级 | `FLANGE_BOLT_N` 或默认 6 |
| `boss_h` | 次级 | `FLANGE_BOSS_H` 或默认 0（无凸台） |
| `fillet_r` | 次级 | 默认 1mm |

L2 几何特征：圆盘 + 中心孔 + 螺栓孔环 + 可选凸台 + 边缘倒角。

### 4.3 `make_housing`

| 参数 | 类型 | 来源 |
|---|---|---|
| `width` | 必填 | `HOUSING_W` 或 envelope w |
| `depth` | 必填 | `HOUSING_D` 或 envelope d |
| `height` | 必填 | `HOUSING_H` 或 envelope h |
| `wall_t` | 必填 | `HOUSING_WALL_T` 或 min(w,d)×0.12 |
| `boss_h` | 次级 | 默认 5mm |
| `fillet_r` | 次级 | 默认 2mm |
| `n_mount` | 次级 | 默认 4（安装柱数） |

L2 几何特征：矩形壳体 + 壁厚抽壳 + 安装柱 + 圆角。

### 4.4 `make_bracket`

| 参数 | 类型 | 来源 |
|---|---|---|
| `width` | 必填 | `BRACKET_W` 或 envelope w |
| `height` | 必填 | `BRACKET_H` 或 envelope h |
| `thickness` | 必填 | `BRACKET_T` 或 envelope d |
| `rib_t` | 次级 | 默认 3mm |
| `fillet_r` | 次级 | 默认 1mm |
| `n_hole` | 次级 | 默认 2（安装孔数） |

L2 几何特征：L 形板 + 加强筋 + 安装孔。

### 4.5 `make_spring_mechanism`

| 参数 | 类型 | 来源 |
|---|---|---|
| `od` | 必填 | `SPRING_OD` 或 envelope max(w,d) |
| `id` | 必填 | `SPRING_ID` 或 od×0.6 |
| `free_length` | 必填 | `SPRING_L` 或 envelope h |
| `wire_d` | 次级 | `SPRING_WIRE_D` 或 od×0.1 |
| `coil_n` | 次级 | `SPRING_COIL_N` 或默认 8（有效圈数）|

L2 几何特征：螺旋弹簧线圈 + 端部平磨面（active coil + dead coil）。

### 4.6 `make_sleeve`

| 参数 | 类型 | 来源 |
|---|---|---|
| `od` | 必填 | `SLEEVE_OD` 或 envelope max(w,d) |
| `id` | 必填 | `SLEEVE_ID` 或 od×0.5 |
| `length` | 必填 | `SLEEVE_L` 或 envelope h |
| `chamfer` | 次级 | 默认 0.5mm（两端倒角） |

L2 几何特征：同轴圆柱抠孔（中心孔）+ 两端倒角。覆盖：套筒/轴套/绝缘段/衬套。

### 4.7 `make_plate`

| 参数 | 类型 | 来源 |
|---|---|---|
| `width` | 必填 | `PLATE_W` 或 envelope w |
| `depth` | 必填 | `PLATE_D` 或 envelope d |
| `thickness` | 必填 | `PLATE_T` 或 envelope h |
| `n_hole` | 次级 | `PLATE_HOLE_N` 或默认 4（角孔） |
| `hole_d` | 次级 | 默认 5mm |
| `fillet_r` | 次级 | 默认 2mm |

L2 几何特征：矩形板 + 四角安装孔 + 圆角。覆盖：底板/安装板/盖板/固定板。

### 4.8 `make_arm`

| 参数 | 类型 | 来源 |
|---|---|---|
| `length` | 必填 | `ARM_L` 或 envelope max(w,d,h) |
| `width` | 必填 | `ARM_W` 或 envelope 次大轴 |
| `thickness` | 必填 | `ARM_T` 或 envelope min 轴 |
| `end_hole_d` | 次级 | `ARM_END_HOLE_D` 或默认 8mm（端部连接孔） |
| `fillet_r` | 次级 | 默认 2mm |

L2 几何特征：细长梁 + 两端连接孔 + 圆角。覆盖：悬臂/连杆/摇臂/延伸臂。

### 4.9 `make_cover`

| 参数 | 类型 | 来源 |
|---|---|---|
| `od` | 必填 | `COVER_OD` 或 envelope max(w,d)（圆形盖） |
| `thickness` | 必填 | `COVER_T` 或 envelope h |
| `id` | 次级 | `COVER_ID` 或默认 0（实心，无中心孔） |
| `n_hole` | 次级 | 默认 4（紧固孔数） |
| `fillet_r` | 次级 | 默认 1mm |

L2 几何特征：圆盘/矩形盖板 + 可选中心孔 + 紧固孔环 + 倒角。覆盖：端盖/密封盖/盖板/压板。

---

## 5. 新增文件与修改范围

**新增**：
- `codegen/part_templates/__init__.py`
- `codegen/part_templates/flange.py`（`make_flange`）
- `codegen/part_templates/housing.py`（`make_housing`）
- `codegen/part_templates/bracket.py`（`make_bracket`）
- `codegen/part_templates/spring_mechanism.py`（`make_spring_mechanism`）
- `codegen/part_templates/sleeve.py`（`make_sleeve`）
- `codegen/part_templates/plate.py`（`make_plate`）
- `codegen/part_templates/arm.py`（`make_arm`）
- `codegen/part_templates/cover.py`（`make_cover`）
- `template_mapping.json`（项目根目录，可选，用户命名覆盖）
- `codegen/template_mapping_loader.py`（加载 + 合并内置关键词）

**修改**：
- `codegen/gen_parts.py`：`_parse_annotation_meta`（A2-0 过滤）+ `match_semi_parametric_template` + `_apply_template_decision` + `generate_part_files` 集成调用
- `templates/part_module.py.j2`：新增 8 个 `{% elif geom_type %}` 分支
- `tests/test_gen_parts.py`（或同级）：A2-0 回归 + 各 task 单测

**不修改**：
- routing 系统（`parts_resolver.py`、`route()`）
- `cad_spec_extractors.py`（不改数据源格式）
- 现有 `ee_*.py`（除 A2-4 的 `ee_001_01.py` 和 A2-6 验收件重新生成）

---

## 6. 验收标准

1. **A2-0 回归**：`ee_001_01.py` 的 `dim_tolerances` 不含 `SPRING_PIN_BORE`、`ARM_L_2` 等非法兰条目
2. **DXF 快照**：`ee_001_01_sheet.dxf` 标注条目数比 A2-0 前减少，且 > 0
3. **面数达标（原 4 类）**：重新生成的 `ee_001_01.py` face 数 ≥ 30
4. **面数达标（新 4 类）**：sleeve/plate/arm/cover 各自验收件 face 数 ≥ 20
5. **mapping.json 路由**：在项目根放 `template_mapping.json`（含 `"连接盘": "flange"`），gen_parts 对含"连接盘"的件正确路由到 flange 模板
6. **降级保底**：无模板匹配的件维持 envelope primitive，`resolve_report.json` 含 `fallback_reason`
7. **全量回归**：990+ 现有测试继续通过
8. **`CAD_SPEC_GEN_DIM_FILTER=off`**：设置后 dim_tolerances 恢复全量返回，行为与 A2-0 前一致

---

## 7. 任务拆分（参考 Track A spec §9）

| Task | 描述 | 估算 |
|---|---|---|
| A2-0 | `_TOL_PREFIX_CATEGORY` 映射表 + `_parse_annotation_meta` 过滤逻辑 + 环境变量开关 + 单测 + DXF 快照更新 | 0.75d |
| A2-1 | `codegen/part_templates/flange.py::make_flange` + 单测（正常路径 + 主尺寸缺失路径） | 0.5d |
| A2-2 | `housing.py` / `bracket.py` / `spring_mechanism.py` + 各自单测 | 1.5d |
| A2-3 | `match_semi_parametric_template`（含 mapping.json 加载）+ `_apply_template_decision` + `generate_part_files` 集成 + `part_module.py.j2` 8 个分支 + 单测 | 0.75d |
| A2-4 | 集成验收：`ee_001_01.py` 重新生成，face ≥ 30；mapping.json 路由测试；人工目测 + 全量回归 | 0.5d |
| A2-5 | `template_mapping_loader.py` + `template_mapping.json` 示例文件 + 单测（精确匹配覆盖内置/文件不存在静默跳过） | 0.5d |
| A2-6 | `sleeve.py` / `plate.py` / `arm.py` / `cover.py` + 各自单测 + `part_module.py.j2` 对应分支 | 1.5d |
| A2-7 | 集成验收（新 4 类）：`ee_001_02.py`（sleeve）重新生成，face ≥ 20；全量回归 | 0.5d |
| **合计** | | **~6.5d** |

---

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 前缀映射表遗漏用户自定义前缀 | `template_mapping.json` 用户覆盖 + `CAD_SPEC_GEN_DIM_FILTER=off` 逃生口 |
| 弹簧线圈 CadQuery 实现复杂（螺旋扫掠） | A2-2 优先实现简化版（圆柱 + 端面标记），L2 螺旋版留 TODO |
| A2-0 改 `_parse_annotation_meta` 影响 DXF 产物快照 | 同步更新快照文件作为 A2-0 验收的一部分 |
| 主尺寸全靠 envelope 推算时精度不足 | warning 明确提示，resolve_report 记录 fallback_reason |
| `template_mapping.json` 中错误键值导致错误路由 | 加载时 validate 值只能是已知模板名（8 个），否则 warn + 忽略该条 |
| arm 模板主轴方向歧义（length 对应 w/d/h 哪轴） | 取 envelope max 轴；`match_semi_parametric_template` 同时回传 axis 信息供 `_apply_template_decision` 消歧 |
| 新 4 类模板扩展后覆盖率仍达不到用户预期 | 在 resolve_report 中明确列出 fallback 件及其 fallback_reason，让用户知道哪些件需要手工 Track C 填充 |
