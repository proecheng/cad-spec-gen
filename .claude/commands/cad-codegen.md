# /cad-codegen — 从 CAD_SPEC.md 生成 CadQuery 脚手架代码

用户输入: $ARGUMENTS

## 指令

从 CAD_SPEC.md 的结构化数据，通过 Jinja2 模板自动生成 CadQuery Python 脚本。

### 前置条件

- 目标子系统目录下已有 `CAD_SPEC.md`（由 `/cad-spec` 生成）
- 已安装 Jinja2（`pip install Jinja2`）

### 路由规则

1. **无参数** → 显示用法：
   ```
   用法: /cad-codegen <subsystem> [--force]

   示例:
     /cad-codegen end_effector            # scaffold 模式（不覆盖已有文件）
     /cad-codegen end_effector --force    # 强制覆盖全部生成文件
     /cad-codegen 充电对接机构             # 支持中文别名
   ```

2. **`<子系统名>`** → 执行代码生成：
   ```bash
   python cad_pipeline.py codegen --subsystem <subsystem>
   ```

3. **`<子系统名> --force`** → 强制覆盖模式：
   ```bash
   python cad_pipeline.py codegen --subsystem <subsystem> --force
   ```

### 生成后自动检查（门控2）

`gen_parts.py` 生成脚手架后立即扫描所有新文件中的 `TODO:` 标记：

- **有未填 TODO** → 打印 WARNING 列表（文件名 + 行号 + 内容），以 **exit code 2** 退出
- **全部填写完毕** → 打印 `All coordinate system blocks filled. Ready for build.`

每个生成的 `<part>.py` 文件头包含强制坐标系声明块，**必须**填写后才能进入 Phase 3：

```python
# ┌─ COORDINATE SYSTEM (MUST fill before coding geometry) ──────────────────┐
# Local origin : <填写：如 bottom-left corner of mounting face>
# Principal axis: <填写：如 extrude along +Z (axial), body height = PARAM_H>
# Assembly orient: <填写：如 rotate X+90deg → axis becomes +Y (radial)>
# Design doc ref : <填写：如 §4.1.2 L176 — "储罐轴线与悬臂共线（径向）">
# └──────────────────────────────────────────────────────────────────────────┘
```

> 四道门控：门控1（DESIGN_REVIEW CRITICAL）→ 门控2（TODO扫描）→ 门控3（orientation_check.py）→ 门控3.5（assembly_validator.py 装配校验，v2.7.0+）

代码生成分 5 步，使用 `codegen/` 目录下的生成器 + `templates/` 下的 Jinja2 模板：

| 步骤 | 生成器 | 模板 | 输入(CAD_SPEC) | 输出 |
|------|--------|------|----------------|------|
| 1 | `gen_params.py` | `params.py.j2` | §1 全局参数表 + §6.2 装配层叠 | `params.py` — 尺寸常量 + 派生装配参数 |
| 2 | `gen_build.py` | `build_all.py.j2` | §5 BOM树 | `build_all.py` — STD STEP + DXF 构建表 |
| 3 | `gen_parts.py` | `part_module.py.j2` | §5 BOM(自制叶零件) + §2 公差/表面 + §标题 | `ee_NNN_NN.py` — 零件近似几何（含自动标注） |
| 4 | `gen_assembly.py` | `assembly.py.j2` | §4连接 + §5BOM + §6姿态 | `assembly.py` — 装配结构（含径向定位+方向变换） |
| 5 | `gen_std_parts.py` | — | §5 BOM(外购件) | `std_ee_NNN_NN.py` — 标准件简化几何 |

**命名规则**：零件编号通过 `strip_part_prefix()` 通用前缀剥离（不绑定 "GIS-"），如 `GIS-EE-001-01` → `ee_001_01.py` / `make_ee_001_01()`；外购件 `std_ee_001_03.py` / `make_std_ee_001_03()`

**自动标注**（v2.2.0+）：`gen_parts.py` 现在还解析 CAD_SPEC.md 的 §2 公差/表面数据和标题行，传入模板。生成的 `draw_*_sheet()` 函数自动调用 `auto_annotate(solid, sheet, annotation_meta={...})`，在 HLR 投影后添加 GB/T 合规标注：
- **几何驱动**（无需 §2 数据）：外形尺寸、圆直径、中心线
- **Spec 驱动**（从 §2 注入）：公差文本、形位公差框、个别面粗糙度
- **材质分类**：`classify_material_type(material)` 自动推断 material_type（al/steel/peek/nylon/rubber），驱动技术要求和默认 Ra 选取
- **项目名参数化**：`ThreeViewSheet` 接收 `project_name`/`subsystem_name`（从 spec 标题解析），标题栏不再硬编码

**近似几何**（v2.2.1+）：`gen_parts.py` 的 `_guess_geometry()` 按两级策略推断自制件近似几何：
1. **BOM 尺寸解析**：从 §5 材质列提取显式尺寸（如 `6063铝合金 140×100×55mm` → box, `Φ38×280mm` → cylinder）
2. **关键词推断**：按零件名匹配通用几何类型（壳体/筒→cylinder, 法兰+悬臂→disc_arms, 环/绝缘段→ring, L型支架→l_bracket, 默认→box）

模板 `part_module.py.j2` 按 `geom_type` 分发生成 CadQuery 代码（cylinder/ring/disc_arms/l_bracket/box），不再全部生成 placeholder box。

**装配定位**（v2.2.1+）：`gen_assembly.py` 从 §6.2 `偏移(Z/R/θ)` 列按 GIS-XX-NNN 料号匹配各总成的定位参数（`θ=NNN°` 角度、`R=NNNmm` 半径、`Z=±NNNmm` 轴向偏移），以数值字面量写入 `assembly.py` 模板（如 `_tx = 65.0 * math.cos(_rad)`），不依赖 params.py 中的参数名。无 θ=/R= 数据的总成（如法兰总成）自动跳过径向变换。

**逐零件偏移定位**（v2.2.3+）：`gen_assembly.py` 现在为每个零件生成独立的 `translate()` 调用（Z 轴偏移来自 §6.2 每行的偏移数据），置于 `_station_transform()` 之前。两层定位架构：
1. **零件级偏移**（translate）：零件在总成局部坐标系内的轴向偏移（如 `p.translate((0, 0, -27.0))`）
2. **工位级径向变换**（_station_transform）：总成整体的径向旋转 + 径向平移
无偏移数据的零件保持原点对齐。

**方向变换**：`gen_assembly.py` 读取 §6.2 的 `轴线方向` 列，按零件名匹配子句（如 "壳体轴沿-Z，储罐轴∥XY"），对需要旋转的零件生成 `rotate()` 代码。优先级：盘面∥XY / 环∥XY → 无旋转 > 沿-Z / 垂直 → 无旋转 > ∥XY / 水平 → 绕X轴转90°。

**装配定位增强**（v2.5.0+）：Phase 2 codegen 现在消费 CAD_SPEC.md 中三个新章节的数据：
- **§6.3 零件级定位**（via `_parse_part_positions()` in `gen_assembly.py`）：对已有定位数据的零件，直接使用 mode/confidence 驱动坐标放置，替代原有启发式堆叠逻辑
- **§6.4 零件包络尺寸**（via 更新后的尺寸查找逻辑）：为无显式 BOM 尺寸的零件提供来自多源采集的精确包络尺寸
- **§9.1 装配排除**（via `_parse_excluded_assemblies()` in `gen_assembly.py`）：自动跳过标记为非本地的总成，避免生成无效引用

**§6.4 包络尺寸消费**（v2.7.0+）：
- `gen_parts.py`：读取 §6.4 包络尺寸作为 **Priority 0** 几何源（优先于 BOM 材质列解析和关键词推断），确保自制件近似几何尺寸与多源采集结果一致
- `gen_std_parts.py`：读取 §6.4 包络尺寸为外购件提供精确尺寸（优先于 `cad_spec_defaults.py` 的分类 fallback）

**§9.2 约束消费**（v2.7.0+）：`gen_assembly.py` 的 `parse_constraints()` 读取 §9.2 约束声明表：
- **contact 约束**：两零件面接触 → 自动对齐接触面（消除间隙）
- **stack_on 约束**：堆叠关系 → 锚点相对定位（B 的底面对齐 A 的顶面）
- **exclude_stack**：排除约束 → 跳过非本地总成的约束消费
- **配合代号**：fit 字段（如 H7/m6）写入生成代码注释，供工程师参考

**GATE-3.5 装配校验**（v2.7.0+）：`assembly_validator.py` 在 Phase 3 BUILD 后自动执行，包含 5 项公式驱动的几何检查：

| 检查 | 公式 | 阈值 |
|------|------|------|
| F1 重叠 | AABB 重叠体积 > 0 | 允许微小重叠（公差范围内） |
| F2 断连 | AABB 间距 > 3×RSS(tolerances) + 0.3mm | 零件间不应有过大间隙 |
| F3 紧凑度 | Z 跨度 ≤ Σ(零件高度) × packing_factor(2.0) | 装配体不应过于松散 |
| F4 尺寸比 | 0.5 ≤ 实际尺寸/预期尺寸 ≤ 2.0 | 零件尺寸应与 SPEC 一致 |
| F5 排除合规 | 非本地总成不应出现在装配体中 | 与 §9.1 排除清单交叉验证 |

输出 `ASSEMBLY_REPORT.json`（PASS/WARN/FAIL per check）。FAIL 项阻止后续 Phase 4 RENDER。

**装配定位修复**（v2.7.1）：`gen_assembly.py:_resolve_child_offsets()` 4项bug fix：
- Fix A: 子零件有显式§6.2定位时，父总成不再被误判为orphan（修正堆叠方向）
- Fix B: `z_is_top` 共享Z值的零件组改为从顶部向下顺序堆叠（消除完全重叠）
- Fix C: auto-stack 公式改为 `offset_z = cursor`（匹配 `centered=(T,T,False)` 几何原点）
- Fix D: 向上堆叠种子改为 `max(bottom_z + envelope_h)`（从最高零件顶面开始）

**Parts Library 系统**（v2.8.0+）：外购件不再硬编码到 `_gen_*` 简化几何，而是通过 `parts_resolver.PartsResolver` 路由到三个适配器之一：
- **`StepPoolAdapter`**：从项目本地 `std_parts/` 目录加载真实的 vendor STEP 文件（Maxon / LEMO / ATI 等）
- **`BdWarehouseAdapter`**：参数化 ISO 硬件（深沟球轴承、紧固件、螺纹），通过 `bd_warehouse` lazy import
- **`PartCADAdapter`**：opt-in 包管理器(`partcad`),跨项目共享参数化零件
- **`JinjaPrimitiveAdapter`**：终极 fallback，复用原有 `_gen_*` 简化几何（v2.8.0 之前的行为）

路由由项目根的 `parts_library.yaml` 注册表驱动。无 yaml 时系统是 no-op，输出与 v2.7.x 字节级一致。CI 的 regression job (`CAD_PARTS_LIBRARY_DISABLE=1`) 强制保证这一点。

**§6.4 P7 包络回填**（v2.8.0+）：Phase 1 的 `cad_spec_gen.py` 在 P5/P6 后新增 P7 backfill 循环，对每个外购件调 `resolver.probe_dims()` 把库探测到的尺寸写入 §6.4，标签 `P7:STEP` / `P7:BW` / `P7:PC`。优先级：
- P1..P4（作者提供）：**永不**被 P7 覆盖
- P5..P6（自动推断）：被 P7 覆盖（标记 `P7:STEP(override_P5)` 等）
- 缺失：填入 P7 值

**Registry inheritance `extends: default`**（v2.8.1+）：项目本地 `parts_library.yaml` 加 `extends: default` 即可继承 skill 自带的 `parts_library.default.yaml`：
- 项目 `mappings` **prepend** 到 default mappings（项目规则优先 first-hit-wins，default 作为兜底）
- 项目顶层 keys（`step_pool` / `bd_warehouse` / `partcad`）shallow override default
- 解决了"项目 yaml 完全替换 default 的 sparse-yaml trap"

**Resolver coverage report**（v2.8.1+）：`gen_std_parts.py` 末尾打印按适配器分组的覆盖率表：
```
[gen_std_parts] resolver coverage:
  step_pool          8  GIS-EE-001-05, GIS-EE-001-06 ... (and 6 more)
  jinja_primitive   26  GIS-EE-001-03, GIS-EE-001-04 ... (and 24 more)
  ─────────────────────────────────────────────────────────
  Total: 34 parts | Library hits: 8 (23.5%) | Fallback: 26 (76.5%)
  Hint: 26 parts use simplified geometry. Add a STEP file under
  std_parts/, write a parts_library.yaml rule, or set
  `extends: default` to inherit category-driven routing.
```
hint footer 仅在有 jinja fallback 时显示。详见 `docs/PARTS_LIBRARY.md`。

**F1+F3 disc_arms 模板重写**（v2.8.2+）：法兰类 (`disc_arms` 几何) 的 arm + platform 现在贯通整个 disc 厚度（不再是顶部 8mm 薄片），cross 结构从任何角度都可见——包括底面 iso 视角。叠加 chamfer/fillet polish 让 mounting platform 看起来像 CNC 件。多了一个 2mm `_arm_overlap` 修复 OCCT tangent boolean bug：
- Before: `make_ee_001_01().val()` 返回 5 个 disjoint Solids（arm box 与 disc cylinder 相切但无体积重叠）
- After: 1 fused Solid，bbox 不变，volume 200 → 309 cm³

**GLB consolidator 后处理**（v2.8.2+）：`codegen/consolidate_glb.py` 在 `cad_pipeline.py build` 跑完后自动执行,合并 CadQuery 的 per-face mesh 拆分（一个 face 一个 mesh node）回到 per-part meshes。GISBOT end_effector：321 components → 39。`EE-001-01` 父节点 bbox 从 degenerate `6×0×8 mm` 修正为 `171×171×25 mm`。Gracefully no-ops 当 trimesh 未安装。

**SPEC 部署**（v2.2.1+）：`cad_pipeline.py spec` 成功后自动将 `output/<subsystem>/CAD_SPEC.md` + `DESIGN_REVIEW.*` 拷贝到 `cad/<subsystem>/`，确保 codegen 读取的始终是最新版 SPEC。

**增强质量门控**（v2.2.1+）：`cad_pipeline.py enhance` 在发送 PNG 到 Gemini 前检查文件大小和灰度方差，跳过空白/近空白渲染图并报 WARNING。阈值可通过 `render_config.json` 的 `enhance_quality_gate` 覆盖。

### 标准件自动生成（步骤 5）

`gen_std_parts.py` 从 BOM 中提取所有 `外购` 零件，按名称/型号自动分类后生成简化 CadQuery 几何：

| 分类 | 简化几何 | 示例型号 |
|------|---------|---------|
| motor | 圆柱 + 轴 | Maxon ECX SPEED 22L |
| reducer | 圆柱（较粗） | Maxon GP22C |
| spring | 环形碟片 | DIN 2093 A6 |
| bearing | 内外环 | MR105ZZ, 688ZZ |
| sensor | 圆柱/方盒 | ATI Nano17, I300-UHF |
| pump | 方盒 + 管口 | 齿轮泵 |
| connector | 小圆柱 | LEMO FGG.0B |
| seal | 圆环体 | FKM O型圈 |
| tank | 圆柱 | 不锈钢储罐 |

- 跳过 `fastener`（太小）和 `cable`（柔性体）
- **线缆/线束限长**（v2.2.3+）：外购件中线缆长度超出装配包络时自动截短至可视化尺寸（如 FFC 500mm → 30mm），防止装配体被拉伸变形
- **尺寸三级查找**: `cad_spec_defaults.py` → `lookup_std_part_dims()`:
  1. 型号匹配（如 `GP22C` → d=22, l=35）
  2. 正则提取 BOM 材质字段中的 `Φd×l` / `w×h×l` 模式（如 `Φ25×110mm` → d=25, l=110）
  3. 分类 fallback（如 `_tank` → d=38, l=280）
- 输出命名: `std_ee_001_05.py`（`std_` 前缀 + 料号后缀）
- scaffold 模式下不覆盖已有文件

### scaffold vs force 模式

- **scaffold**：仅生成不存在的文件，已有工程师手动修改的文件不会被覆盖
- **force**（`gen_params.py` 默认）：全部重新生成覆盖，适用于首次生成或 CAD_SPEC 大幅变更后的完全重置

### 生成后汇总

执行完毕后向用户报告：
- 每个生成器的执行结果（成功/跳过/失败）
- 生成或更新的文件列表
- 下一步建议：`/mechdesign <子系统>` 手动完善几何细节，或 `python cad_pipeline.py build` 直接构建

### 与其他命令的关系

```
/cad-spec → CAD_SPEC.md    (Phase 1: 规范化)
/cad-codegen → *.py 脚手架  (Phase 2: 代码生成)  ← 你在这里
/mechdesign → 手动完善几何   (手动阶段)
cad_pipeline.py build       (Phase 3: 构建)
cad_pipeline.py render      (Phase 4: 渲染)
cad_pipeline.py full        (一键全流程)
```
