# Track A — 视觉保真度快胜三件套 设计规格

> 版本: v0.4.1 — 2026-04-20（A1-0 spike 已跑，结论写入 §3.2.1；见附录 E）
> 状态: 已审查修订，A1-0 完成，可落地实施
> 触发: 2026-04-20 session `D:\Work\cad-tests\04-末端执行机构设计.md` 端到端测试发现"装 SW 与不装没区别"——渲染图中几何是 envelope primitive、材质是纯色 BSDF，SW 的 530 张纹理 + 1844 个 Toolbox 件全闲置
> 前置: Phase SW-A / SW-B 基础（`SwInfo` / `SwMaterial` / `parts_resolver` / `SwToolboxAdapter` 已合入 main @ `f91508a`）
> 关联: **Track B**（`2026-04-20-track-b-sw-toolbox-activation-design.md`）打通 SW sldprt→STEP 路径；Track A 独立可交付，不阻塞 Track B。
>
> **目标**：在不触碰 SW Add-in 激活路径的前提下，通过 3 处精准改动（贴图桥 + 自制件几何升级 + routing 核查）消除"几何占位 + 材质纯色"两个最刺眼的保真度瓶颈，让图在 1 周内肉眼可见"像"。

---

## 1. 目标与范围

### 1.1 目标

Track A 解决**现有 CAD 管线交付图的视觉保真度短板**。范围锁在三个彼此正交、可并行推进的子项：

| 子项 | 瓶颈 | 产出 |
|---|---|---|
| **A1** | Blender `create_pbr_material` 只设标量，无任何 `ShaderNodeTexImage` —— SW 目录下 530 张 PBR 贴图完全闲置 | 纹理贴图桥（preset → JPG 路径 → Blender Image Texture 节点） |
| **A2** | `gen_parts.py` 产出的 11 个自制件 `ee_*.py` 全是 envelope box/cylinder + 9 行 `TODO` —— 弹簧限力机构=圆柱、法兰=占位 | 零件名 + §2.1 尺寸表 + §6.4 envelope 驱动的半参数几何模板（法兰/壳体/支架/弹簧机构四类） |
| **A3** | 本次跑出 25 个 `std_*.py` 全带 `"Simplified representation for visualization only"` —— parts_library.yaml 的 bd_warehouse/step_pool 路由应命中的件也都落到 `jinja_primitive` fallback | Routing 可观测性（resolve_report）+ bd_warehouse adapter 实际可用性审计 + 必要的回归用例 |

### 1.2 覆盖率与量化指标

**"像"的量化基准**：同一 BOM 在 Track A 前后跑 `cad_pipeline.py full`，对比 4 张视角 PNG：

| 指标 | 前基线（2026-04-20 session） | Track A 目标 | 校准依据 |
|---|---|---|---|
| BOM 行真实几何命中率 | 0 / 54 | ≥ 20 / 54 （37%）| 11 自制件里 4 类模板诚实覆盖 ≈ 5 件（见 §4.2 修订覆盖表），+ 25 标准件里若 A3 修通 bd_warehouse 可再贡献 ~15 件 |
| Blender material 含贴图节点的比例 | 0 / N materials | ≥ 8 / 10 常用 preset 至少带 1 张 base color 贴图 | 与 §9 Task A1-4 范围对齐 |
| 11 件自制件中被模板覆盖产出 ≥ 30 face 的 | 0 | **至少 3 件**（法兰/壳体/支架；剩余退 envelope 不回退） | 机械领域 C1 审查：4 类模板实际覆盖 ≈ 5 件，留 2 件 buffer |
| `_std.py` 文件头含 `Simplified representation` 的比例 | 25 / 25 | ≤ 15 / 25（紧固件/轴承走 bd_warehouse）| A3 审计若揭示 bd_warehouse 根本 import 错则目标作废 |
| `blender_texture_count.json` （A1 子进程写入 artifacts/）| 不存在 | ≥ 1 且数值 > 0 | 避免 500KB 体积作为唯一验收的 silent-fail（见 §8.2 硬验收）|

**硬验收**（Track A 交付时）：
1. 上表所有指标在 `end_effector` 子系统 full pipeline 回归中达标
2. `artifacts/{run_id}/blender_texture_count.json` 写入且 `total_loaded > 0`
3. `resolve_report.json` 里 `adapter_hits.bd_warehouse.count ≥ 1`（条件性：A3 审计发现 bd_warehouse import 链坏则改为 `adapter_hits.bd_warehouse.unavailable_reason != ""` 至少能诊断出原因）
4. 3 张视角 PNG 像素方差对比（patch stddev > 阈值）而非单纯文件大小

### 1.3 非目标（严格范围）

- **不动 SW Add-in 激活路径**——那是 Track B 的领地，Track A 假设 `SwToolboxAdapter.is_available()=False`，所有 SW 路径走降级。
- **不改 parts_library.yaml 的 mapping 规则**——A3 只做 adapter **可用性** 审计和 **routing 观测**，不重写 yaml 决策树；如审计证实 bd_warehouse import 链本身坏了，修它但不动 yaml。
- **不做 AI 后端修复**——今天观察到的 Gemini 代理 503 属外部问题，不在 Track A 范围。`engineering` 后端的 PIL 三参数调色维持不变。
- **不解决几何的设计级精确性**——A2 只让图"像某个法兰"而非"精确到 §2.1 全部尺寸"，尺寸完整性留给 Track C。
- **不引入新的第三方 AI/PBR 库**——所有 A1 贴图加载用 Blender 内置 `bpy.data.images.load` + 现有 PIL 路径。

### 1.4 三子项依赖关系

```
A1 (纹理桥)  ─────────────┐
A2 (几何升级) ─────────────┼──► 联合跑 end_effector full pipeline 回归（§5 验收）
A3 (routing 审计) ────────┘
```

A1/A2/A3 技术上**完全独立**，可并行；合并顺序不强求。单独合入 A1 已经能让"纯色 → 有纹理"见效，单独合入 A2 已经让"box → 带孔带倒角的法兰"见效。

---

## 2. 关键设计决策

| # | 决策点 | 选择 |
|---|---|---|
| A-1 | 纹理来源目录 | 复用 `SwInfo.textures_dir`（= `install_dir/data/Images/textures`），不新增路径。SW 未装时 preset 降级回纯色 BSDF（当前行为）|
| A-2 | preset → 纹理文件的映射落点 | 加在 `render_config.py:36` 的 `MATERIAL_PRESETS` 模块级 dict 内（每个 preset 顶层加 4 个可选字段，见 §3.1）；现有 `resolve_material(entry)`（render_config.py:288）的 `dict(preset)` 合并逻辑自动将新字段传递到 `params`，**不动 `resolve_material` 自身**。不单开 texture_library.yaml —— 避免再引入一个配置层增加零配置负担 |
| A-3 | Blender 侧的贴图 node 构造 | 扩展 `render_3d.create_pbr_material(name, params)` —— 在现有 `ShaderNodeBsdfPrincipled` 基础上插入 `ShaderNodeTexImage` + `ShaderNodeNormalMap` + `ShaderNodeTexCoord`。**不分裂为新函数**，保持单一入口。**UV 坐标走 `TexCoord.Generated` 输出**（与现有 section-view 贴图代码 `render_3d.py:415` 一致），不依赖 GLB 里 SolidWorks 导出器是否写了 UV layer —— 减少假设面 |
| A-4 | 纹理缺失容错 | `bpy.data.images.load(filepath, check_existing=True)` 失败 → 记 warning 降级纯色，**不 raise**。材质层 silent-fail 会让整张图变纯色，和现在同级，不能让管线挂掉 |
| A-5 | 自制件几何模板的组织方式 | `codegen/part_templates/`（新目录）放 4 个模板 python 文件：`flange.py` / `housing.py` / `bracket.py` / `spring_mechanism.py`。`gen_parts.py` 按零件名关键词 + `category` 字段选模板 |
| A-6 | 模板参数来源 | 读 `CAD_SPEC.md §2.1 参数表` + `§6.4 envelope` —— 已有数据，不要求用户再填任何字段。缺数据时回退到现在的 envelope primitive（不倒退）|
| A-7 | A3 routing 观测的落点 | 在 `parts_resolver.py` 增加 `resolve_report(bom) → ResolveReport` —— 产生 `artifacts/{run_id}/resolve_report.json` 记录每行 BOM 最终命中的 adapter、失败原因、候选 adapter 列表。`gen_std_parts.py` 已写 `sw_report.html` 可复用此数据 |
| A-8 | A3 的修复策略 | **只修 adapter 本身的 import/依赖错误**，不改 yaml 决策。若 `BdWarehouseAdapter.is_available()=False` 仅因为 `import bd_warehouse` 失败 → 在 env-check 加装依赖引导，不把 yaml rule 移动 |
| A-9 | SwMaterial schema 扩展 | `adapters/solidworks/sw_material_bridge.py::SwMaterial` dataclass 新增 `texture_files: dict[str, Path]` 字段（keys: `base_color / roughness / normal / metallic`），`parse_sldmat` 解析 `<shader><TextureFileName>` 回填。**默认空 dict**，老代码 path 不受影响 |
| A-10 | 多 subsystem 共享纹理缓存 | 不缓存 —— Blender `bpy.data.images.load(check_existing=True)` 已按文件路径去重；重复装配里同一张 JPG 只加载一次 |
| A-11 | 向后兼容保证 | 所有 preset 字典字段 + SwMaterial 字段 + resolve_report 均为**新增**；未扩展的老 preset（缺 4 个纹理字段）走原纯色 BSDF 分支，与 v2.11 行为等同 |
| A-12 | 用户自定义纹理覆盖入口 | `render_config.json` 加 `material_overrides: {preset_name: {base_color_texture: ..., ...}}` 字段；`resolve_material(entry)` 合并顺序 **= MATERIAL_PRESETS → sldmat auto-bridge → JSON material_overrides**（用户 JSON 优先级最高）。零配置时 JSON 可全缺省；需覆盖时不用改 Python 代码 — 遵循北极星"傻瓜式操作" |
| A-13 | 自制件模板的 `principal_axis` | **不**在模板文件里硬写死；改由 `_apply_template_decision` 读 `CAD_SPEC.md §6.3 serial_chain[*].axis` 翻译到局部坐标系；`make_*()` 工厂函数签名返回 `tuple[cq.Workplane, dict]`（solid + metadata 含 `local_principal_axis`）供 `_orientation_spec()` 按装配姿态重映射 |
| A-14 | `PartsLibraryAdapter.is_available()` 契约扩展 | 现契约 `-> bool` → 改为 `-> tuple[bool, Optional[str]]`（加 reason）；所有 4 个 adapter 同步；新加 `base.py` 提供默认实现 `return True, None` 避免破坏未改动的自定义 adapter |
| A-15 | `SwInfo.textures_dir` 字段契约冻结 | Track A 使用的该字段 schema（str 绝对路径，SW 未装时为 ""）**声明在两 track 生命周期内不变**；Track B 不得重构此字段结构，Track A 同理不得在 Track B 修改 `sw_detect` 时被牵连 |

---

## 3. A1 — Blender 贴图桥（纹理挂载）

### 3.1 接入点与字段变更

**当前** `render_config.py:40` preset 示例：
```python
"brushed_aluminum": {
    "color": (0.82, 0.82, 0.84, 1.0),
    "metallic": 1.0,
    "roughness": 0.18,
    "anisotropic": 0.6,
    "appearance": "brushed 6061 aluminum...",
}
```

**Track A1 后**，preset dict **新增 4 个可选字段**（`Optional[str]`，相对 `SwInfo.textures_dir` 的文件名或绝对路径）：

```python
"brushed_aluminum": {
    "color": (0.82, 0.82, 0.84, 1.0),
    "metallic": 1.0,
    "roughness": 0.18,
    "anisotropic": 0.6,
    "appearance": "brushed 6061 aluminum...",
    # ── Track A1 新增 ──
    "base_color_texture": "metal/brushed aluminum.jpg",
    "normal_texture": "metal/brushed aluminum_normal.jpg",
    "roughness_texture": None,      # 缺省时走标量 roughness
    "metallic_texture": None,
}
```

**路径解析规则**（`render_3d.py` 内新增两个函数，分离返回类型避免同义矛盾）：

```python
def _resolve_texture_path(rel_or_abs: str) -> Optional[Path]:
    """返回磁盘文件路径；无法解析或文件不存在返回 None。不做约定探测。"""

def _detect_normal_convention(normal_filename: str) -> Literal['dx', 'gl']:
    """按文件名后缀/元数据推测 DirectX 或 OpenGL 约定；默认 dx（SW 导出习惯）。"""
```

**`_resolve_texture_path` 查找顺序**：
1. 绝对路径 → 存在即返回
2. 相对路径 + `CAD_SPEC_GEN_TEXTURE_DIR` 环境变量 set → 拼接并检查存在
3. 相对路径 + Blender 子进程启动时 `os.environ["SW_TEXTURES_DIR"]`（由 `cmd_render` 从 `SwInfo.textures_dir` 注入）
4. 以上全 miss → warning（per-material）+ 降级纯色；同时由 `render_3d.py` 结束时汇总写 `blender_texture_count.json`（见 §3.3）

**Rationale for (3)**：Blender `-b -P script.py` 是独立子进程，拿不到 Python 端的 `detect_solidworks()` 结果；通过环境变量注入是最小侵入。

### 3.2 `create_pbr_material` 契约变更

**签名保持不变**（关键 — 调用方 `assign_materials()` 不改）：
```python
def create_pbr_material(name: str, params: dict) -> bpy.types.Material
```

**内部行为变更**：

**关键技术选项**（3D 设计师视角 CRITICAL 审查后修订）：

默认策略 = `UV + BOX projection 双路径自适应`：A1-0 spike 先检测 GLB mesh 是否含 UV layer，有 UV 走 tangent-space normal map（优先级最高）；无 UV 走 BOX projection + `ShaderNodeBump` 替代 tangent-space normal（退化）。

| 新字段 | 新建 Blender 节点 | 节点连接（有 UV 路径） | 颜色空间 | 无 UV 降级 |
|---|---|---|---|---|
| `base_color_texture` | `TexCoord` + `Mapping` + `TexImage` | `TexCoord.UV → Mapping(Scale) → TexImage.Vector → BSDF.Base Color` | **显式 sRGB**（`colorspace="sRGB"`）| 同路径改 `TexCoord.Generated`，`TexImage.projection="BOX"`，`projection_blend=0.2` |
| `normal_texture` | `TexImage` + `NormalMap` | `TexCoord.UV → Mapping → TexImage → NormalMap(space='TANGENT') → BSDF.Normal`；若 SW 导出是 DirectX 约定需在 TexImage 和 NormalMap 间插 `SeparateColor → InvertG → CombineColor` 翻转 Y 通道 | `Non-Color` | **降级用 `ShaderNodeBump` + 灰度 height**，跳过 NormalMap（tangent-space normal 无 UV 无 Tangent 视觉比纯色还糟） |
| `roughness_texture` | `TexImage` | `TexCoord.UV → Mapping → TexImage → BSDF.Roughness` | `Non-Color` | 同路径改 Generated + BOX |
| `metallic_texture` | `TexImage` | `TexCoord.UV → Mapping → TexImage → BSDF.Metallic` | `Non-Color` | 同路径改 Generated + BOX |

**`ShaderNodeMapping` 必加**（3D CRITICAL 审查）：`TexCoord → Mapping(Scale=bbox_mm/10) → TexImage.Vector`。Scale 按零件 bbox 最长边 mm 除以"每 10mm 纹理重复一次"的物理周期（默认 1.0，`material_overrides` 可 per-preset 覆盖）。不加 Mapping 则 Φ90 法兰和 Φ200×80mm 壳体共用一张纹理产生密度不均。

**`projection="BOX"` + `projection_blend=0.2`**（无 UV 降级时必加）：Generated 坐标走 BOX projection 是无 UV 情况下对圆柱/倒角件的工业级可用方案。不加 BOX 则圆柱面侧面被压成线，产生强拉伸条纹。

**SW normal map 约定**：SolidWorks PhotoView/Visualize 默认导出 DirectX 约定（−Y 向上）。Blender `NormalMap` 节点按 OpenGL（+Y 向上）解读，会让凹凸反向。按 §3.1 新定义的 `_detect_normal_convention(filename)` 独立函数返回 `Literal['dx','gl']`，create_pbr_material 在构建 normal 分支节点时查询该函数结果 → 按需插 `SeparateColor → InvertG → CombineColor` 翻转 Y 通道。**`_resolve_texture_path` 本身只返回 `Optional[Path]`，不带元信息**（避免同函数双返回类型矛盾）。

### 3.2.1 Blender 版本矩阵 + A1-0 Spike 结论

本 Track A1 支持 **Blender 4.2 LTS**（`pipeline_config.json blender_path` 当前指向 `D:/Blender/blender.exe` 即 4.2）。Principled BSDF v2 影响 `Specular / Sheen` socket 名，但本 Track 只用 `Base Color / Metallic / Roughness / Normal` 四个 socket，**不受影响**。`bpy.data.images.load(filepath, check_existing=True)` 在 3.x+ 均可用。

**A1-0 Spike 结论（2026-04-20 本机实测，`D:\Work\cad-tests\GISBOT\cad\output\EE-000_assembly.glb`）**：

| 指标 | 数值 |
|---|---|
| 总 mesh 数 | 40（1 个为 Blender 默认 Cube 占位）|
| 技术上有 UV layer | 39 / 40 (97.5%) |
| UV **非退化**（span ≥ 1e-3，unique_points ≥ 10）| **1 / 40 (2.5%)** — 仅 Blender 默认 Cube |
| UV **退化塌缩**（所有 loop UV = `(0.5, 0.5)`）| **38 / 40 (95%)** |
| tangent 可算 | 39 / 40（但在退化 UV 上算出的 tangent 无意义）|

**根因**：CadQuery `exporters.export(obj, path, type=STEP)` 不写 UV；STEP (BREP) 格式本身无 UV；`consolidate_glb.py` / Blender glTF importer 对无 UV 的 mesh 分配默认 `(0.5, 0.5)` fallback，让 39/40 mesh 的 UV 全塌缩到一个点。

**决策**：**默认走 Generated + BOX projection + Bump（无 UV 降级路径升级为主路径）**。UV + TANGENT 路径作 **future / v0.5 扩展**（需在 `consolidate_glb.py` 或新增 `codegen/uv_unwrap.py` 里插 Smart UV Project 步骤，本 Track A 范围不做）。

**对 §3.2 节点连接表的影响**：原表"有 UV 路径"列作为 **future 参考**保留，但 §9 Task A1-1 / A1-2 实施时**只实现"无 UV 降级"列**（Generated + BOX + Bump）。代码结构仍预留 `if mesh_has_valid_uv: uv_path else: generated_path` 分支，目前 `mesh_has_valid_uv` 恒返 False。

**未提供的字段** → 走**现有**标量输入路径（`bsdf.inputs["Base Color"].default_value = params["color"]`）。

### 3.3 SW 纹理路径注入

**前置改动（必做）**：现有 `cad_pipeline._run_subprocess(cmd, label, dry_run=False, timeout=600, warn_exit_codes=None)` 签名（`cad_pipeline.py:198`）**无 `env` 参数**，内部 `subprocess.run` 也不传 env。注入方案需先给 `_run_subprocess` 加可选 `env: dict | None = None` 参数并透传到 `subprocess.run`，老调用点全部兼容（env=None 时 subprocess.run 默认继承父进程 env）。

**然后**在 `cmd_render()` 启动 blender subprocess 前构造 env：

```python
from adapters.solidworks.sw_detect import detect_solidworks
_sw = detect_solidworks()
env = os.environ.copy()
if _sw.installed and _sw.textures_dir and os.path.isdir(_sw.textures_dir):
    env["SW_TEXTURES_DIR"] = _sw.textures_dir
# _run_subprocess(cmd, "render standard views", timeout=1200, env=env)  ← 新参数
```

**SW 未装** → `SW_TEXTURES_DIR` 不注入，`_resolve_texture_path` 走 fallback → 材质降级纯色（当前行为，无回归）。

**UNC 路径容错**（SW 操作员审查）：`SwInfo.textures_dir` 可被用户在 SW Tools → Options → Hole Wizard/Toolbox 指向 UNC `\\server\share\Toolbox`。Blender 子进程对 UNC 可能因 Kerberos double-hop 静默 load 失败。`_resolve_texture_path` 内对以 `\\` 开头的路径先 `os.path.isfile` 预检，失败时 warning 明确写 "UNC 权限或网络不可达"，而非静默 return None。

**纹理加载计数**（防 silent-fail + bug #10 Blender crash 同族守护）：

Blender 子进程启动时注入 `BLENDER_TEXTURE_COUNT_FILE` 环境变量告知落点；落点由 **`cad_paths.get_run_artifact_path(run_id, "blender_texture_count.json")` helper** 统一生成（**禁止**字符串拼接 `./artifacts/{run_id}/` 相对路径——防重犯 bug #1 `cmd_init` 硬编码路径陷阱）。

`render_3d.py` 在渲染结束时写 JSON：
```json
{
  "schema_version": 1,
  "total_loaded": 17,
  "total_miss": 2,
  "base_dir": "C:/...",
  "first_miss_example": "metal/xxx.jpg"
}
```
`cmd_render` 在 subprocess 结束后的判定表（关键 — 防 bug #10 Blender silent exit 0 重犯）：

| subprocess exit | JSON 存在 | JSON schema_version | 判定 |
|---|---|---|---|
| 0 | ✅ | == 1 | 读 JSON；`total_loaded == 0 and total_miss > 0` → 打印全局告警；否则 OK |
| 0 | ❌（Blender Python 脚本未跑到结尾）| — | **视为 Blender 崩溃**：ERROR 打印 `[ERROR] Blender crashed silently — exit 0 but texture_count.json missing`；pipeline return 1 |
| 0 | ✅ | ≠ 1 | **视为 schema drift**：ERROR + return 1（cross-version incompatibility）|
| ≠ 0 | — | — | 按常规 subprocess 失败处理 |

**日志文案统一 ASCII**（防 bug #3 GBK 编码崩重犯）：告警消息不用中文冒号 `：` 不用 emoji，用英文前缀：
- `[WARN] texture_dir mismatch: SW_TEXTURES_DIR=... total_loaded=0/N`
- `[ERROR] Blender crashed silently — exit 0 but texture_count.json missing`

中文长句可在 artifacts/ 下 log 文件内保留（文件是 UTF-8），stdout 只走 ASCII。

### 3.4 sldmat 纹理文件回填（A1 深耕分支，可选）

`sw_material_bridge.parse_sldmat()` 当前只解析物理属性和 shader_path；v2.8.x 实际漏了 `<shader><TextureFileName>` 标签的解析。Track A1 内扩展：

```python
@dataclass
class SwMaterial:
    name: str
    classification: str
    density: Optional[float]
    # ... 既有字段 ...
    shader_path: Optional[str]                 # 既有：类型是 str 不是 Path（见 sw_material_bridge.py:65）
    texture_files: dict[str, str] = field(default_factory=dict)  # ★ A1 新增；value 类型与 shader_path 保持一致用 str
```

**为什么不用 `Path`**：`sw_material_bridge.py:65` 现有 `shader_path: Optional[str]`，若 `texture_files` value 用 `Path` 会与兄弟字段类型不一致，给序列化/JSON dump 路径埋坑。约定消费方（render_3d 加载贴图前）如需 `Path`，在消费侧一行 `Path(path_str)` 转换。

解析逻辑：遍历 `<shaders>/<shader>` 节点，按标签名收集 `<TextureFileName>`、`<BumpTextureFileName>`、`<RoughnessTextureFileName>` 等，落到 dict 的 `base_color / normal / roughness / metallic` 四个标准化 key。

**提供给 `render_config`**：新增 `render_config.resolve_material_from_sldmat(material_name) → dict`，把 SwMaterial 的 `texture_files` 映射到 A1 新增的 4 个 preset 字段，供渲染时自动填。

**若此分支工作量超预算**，Track A1 可只交付 §3.1/3.2/3.3（手工在 `render_config.py` 维护 preset→JPG 的映射表），sldmat 解析留到后续版本——不阻塞主路径。

---

## 4. A2 — 自制件几何升级（零件名 + 尺寸 → 半参数模板）

### 4.1 现状

`codegen/gen_parts.py:235 generate_part_files()` 实际路径：

```
parse_bom_tree(spec_path)  → parts list
  ├── 过滤 is_assembly=True / 非"自制"
  └── 对每个自制件 p：
        ├── _guess_geometry(p["name_cn"], p["material"], envelope=envelope)
        │     → geom dict {type, envelope_w, envelope_d, envelope_h, ...}
        ├── cad_spec_gen.parts_routing.route(name_cn, GeomInfo, templates)
        │     → RouteDecision{outcome, template}
        │     ★ 当前 "dormant integration; emission unchanged"（gen_parts.py:294 注释）
        │     ★ 只打印 [routing preview]，不影响 emission
        └── Jinja template "part_module.py.j2".render(geom_type=..., **geom_vars)
              → ee_*.py 文件（**所有路径都走同一个 Jinja 模板，按 geom_type 内部 if/elif 分支选造型**）
```

**关键事实**：gen_parts 不存在 `resolve_part` / `emit_fallback` 函数；所有路由最终都经过 `templates/part_module.py.j2` 的 geom_type 分支。升级路径是**激活已存在但 dormant 的 `parts_routing.route()` 决策**，让它真正选模板而不只是打印预览。

实测 11 件自制件里 10 件都走 `type=fallback`（见 2026-04-20 session `[routing preview] ... -> FALLBACK (fallback)`），造型是 envelope box/cylinder。

### 4.2 目标：4 类基础模板 + 4 类预留目录（总 8 类覆盖 11 件）

**机械设计师审查校准**：末端执行机构 11 件自制件的实际归类：

| 零件 | BOM id | 模板归属 | Track A2 处理 |
|---|---|---|---|
| 法兰本体（含十字悬臂） | 001-01 | `flange` + **十字悬臂** | **基础 flange 模板覆盖圆盘+孔**，悬臂部分先退 envelope bbox；future `cross_arm_flange` 预留 |
| ISO 9409 适配板 | 001-08 | `flange`（现已 HIT_BUILTIN `iso_9409_flange`）| 不动 |
| PEEK 绝缘段 | 001-02 | `sleeve`（套筒）| **future 预留目录** `codegen/part_templates/sleeve.py`；本期 fallback |
| 涂抹模块壳体 | 002-01 | `housing` | **基础 housing 覆盖** |
| 清洁模块壳体（含卷轴腔+清洁窗口） | 004-01 | `housing` + 非矩形内腔 | housing 基础覆盖外壳，内腔退 bbox；future `compound_housing` |
| 清洁窗口翻盖 | 004-12 | `hinged_lid` | **future 预留目录** `hinged_lid.py`；本期 fallback |
| UHF 安装支架 | 005-02 | `bracket` | **基础 bracket 覆盖** |
| 壳体（含散热鳍片） | 006-01 | `finned_housing`（鳍片需 fin_count/fin_pitch 参数）| **future 预留目录** `finned_housing.py`；本期 fallback |
| 安装支架（抱箍+L 型） | 006-03 | `clamp_l_bracket`（抱箍+L 复合）| **future 预留目录** `clamp_l_bracket.py`；本期 fallback |
| 弹簧限力机构总成 | 003-03 | `spring_mechanism` + 限位销 + 悬臂 | **基础 spring 覆盖弹簧本体**，限位销/悬臂退 bbox |
| 柔性关节（万向节） | 003-04 | `universal_joint` | **future 预留目录** `universal_joint.py`；本期 fallback |

**Track A2 实际交付**：
- **本期实现** 4 类基础模板：`flange` / `housing` / `bracket` / `spring_mechanism` — **实际 100% 覆盖 5 件 + 部分覆盖 1 件 ≈ 5.5/11 = 50%**
- **本期预留**（目录+空 `.py` 占位+`__init__.py`）5 类 future 模板：`sleeve` / `compound_housing` / `cross_arm_flange` / `hinged_lid` / `finned_housing` / `clamp_l_bracket` / `universal_joint` — 不影响 Track A2 交付但让后续 Track C 可快速填充
- 未覆盖的 5.5 件**诚实退回 envelope fallback**，在 resolve_report 里明确标注 `fallback_reason: "no semi-parametric template for category=X"`

| 类别关键词 | 现状 | Track A2 新模板产出 |
|---|---|---|
| `法兰 / flange` | `iso_9409_flange` 仅一种型号 | `flange.py::make_flange(od, id, t, bolt_count, bolt_pcd, bolt_dia) → (cq.Workplane, {"local_principal_axis": "z"})` — 圆盘 + 螺栓孔阵列 + 倒角 |
| `壳体 / housing` | box primitive | `housing.py::make_housing(w, d, h, wall, fillet, mount_holes=[]) → (cq.Workplane, {"local_principal_axis": "z"})` — 薄壁中空盒 + 圆角 + 可选安装孔 |
| `支架 / bracket` | box primitive | `bracket.py::make_l_bracket(w, d, h, t, hole_pattern) → (cq.Workplane, {"local_principal_axis": "z"})` — L 型折弯 + 孔位 |
| `弹簧 / 限力 / 弹性机构` | cylinder primitive | `spring_mechanism.py::make_spring_cylinder(d_outer, d_inner, l_free, pitch, simplified=True) → (cq.Workplane, {"local_principal_axis": "z"})` — **简化弹簧（N 个倾斜圆环堆叠，face ≤ 500）**；不用真螺旋扫掠以免 Cycles BVH 爆炸 |

### 4.3 数据来源（**无需用户新增任何字段**）

#### 4.3.1 Precursor Task A2-0 — 修 §2.1 `dim_tolerances` 混池 bug

**机械设计师 CRITICAL 审查发现**：现有 `auto_annotate` 抽取器把子系统级 §2.1 参数表**不按零件归属过滤**直接塞给每件 ee_*.py（实测 `ee_001_01.py:93` 与 `ee_003_03.py:90` 的 `dim_tolerances` 逐字相同，12 条混合了法兰/悬臂/弹簧销）。

若 A2 在此基础上按"`FLANGE_OD` 前缀推断归属"直接用，会把 001-02 PEEK 绝缘段（套筒件）错误喂 `FLANGE_BOLT_PCD=70`，`make_flange()` 拿到荒诞尺寸。

**A2-0（A2 实施前必做 precursor）**：
1. `cad_spec_gen/parts_routing.py` 或 `codegen/gen_parts.py::_parse_annotation_meta` 增加 `part_no_prefix_filter(dim_name, part_no) → bool` 助函数
2. `dim_tolerances` 按 `part_no` 属归过滤：FLANGE_* 只给 part_no 里 name_cn 含"法兰"的件；SPRING_* / ARM_* 只给 003-03；HOUSING_* 只给 002-01/004-01/006-01；通用 bolt / pin 按零件类别投射
3. 旧的"全量混池"行为加 `CAD_SPEC_GEN_DIM_FILTER=off` 环境变量回退开关（防止本次修改破坏既有 CI 快照）
4. 同步修 `auto_annotate` 单测，断言每件零件的 dim_tolerances 只含属于自己的条目

这一步不做，A2 的数据源就是脏的，模板出的 flange od 会错成别的件的尺寸。

#### 4.3.2 参数源优先级

| 模板参数 | 源字段（按优先级） | Fallback |
|---|---|---|
| 主要尺寸 (od/id/h/...) | **(1) A2-0 过滤后**的 `§2.1 dim_tolerances`（例如 `FLANGE_OD=90`）；**(2) §6.4 envelope bbox + §6.3 serial_chain.axis 消歧** | 全缺 → 退 envelope primitive |
| 螺栓孔数/PCD | `§2.1` 含 `BOLT_PCD` / `BOLT_COUNT` 时取值 | 按法兰 OD 推导（OD ≤ 40: 4 孔, 40-80: 6 孔, ≥80: 8 孔）|
| 圆角/倒角 | §2.1 含 `{TYPE}_FILLET` 命名约定（若存在）| 按类别约定常数：**法兰 R3 / 壳体 R1 / 支架 R2**（机械设计师审查：7075-T6 法兰锐角 1mm 太小，实际 R3-R5 合理） |

#### 4.3.3 envelope 方向歧义消解规则（机械设计师审查）

envelope 是 `length × width × height` 的 bbox，不含方向。`make_flange(od, t)` 若只有 envelope，要知道 od 和 t 哪个是哪个：

1. **优先**从 `§6.3 serial_chain` 里读本件的 `axis: +X/+Y/+Z`，沿 axis 的 envelope 维度 = t（厚度），垂直平面取最大维度 = od
2. serial_chain 无此件定义时 → 读 `§6.4` 里是否有 `principal_axis` hint
3. 以上都无 → **退回 envelope primitive，不强行 fallback 成法兰**（避免"弹簧限力总成 envelope=40×40×20 被当成 Φ40×20 法兰"这种荒诞结果）

**缺数据行为**：任一必填参数缺失（或方向无法消歧）→ 降级到现在的 envelope primitive 并 warning，**不 raise**。保证 Track A2 永远不比现状差，也不引入"错模板 + 乱尺寸"。

### 4.4 `gen_parts.py` 路由激活（机械审查：模板返回元信息）

**修订**：`make_*()` 工厂函数签名 = **`-> tuple[cq.Workplane, dict]`**（不只是 Workplane），dict 内含 `local_principal_axis` / `mount_holes_pattern` / `fallback_reason` 等元信息，供 `_orientation_spec()` 按 §6.3 装配姿态 **重映射**到全局坐标系；不再由模板写死 `principal_axis='z'`。

### 4.4 `gen_parts.py` 路由激活（不重写函数，激活已 dormant 的决策）

**当前** `generate_part_files()` 核心循环（gen_parts.py:275-363，简化）：
```python
for p in parts:
    envelope = envelopes.get(p["part_no"])
    geom = _guess_geometry(p["name_cn"], p["material"], envelope=envelope)
    if _PARTS_ROUTING_AVAILABLE:
        _decision = route(p["name_cn"] or "", _geom, _templates)
        print(f"  [routing preview] {p['name_cn']} -> {_decision.outcome} ({...})")
        # ★ _decision 不喂给后续 emission —— dormant
    ...
    geom_vars = {f"geom_{k}": v for k, v in geom.items()}
    content = template.render(**geom_vars)   # part_module.py.j2 按 geom["type"] 分支
```

**Track A2 后**：把 `_decision` 接入 `geom` —— 命中模板时覆盖 `geom["type"]` + 填参：
```python
for p in parts:
    envelope = envelopes.get(p["part_no"])
    geom = _guess_geometry(p["name_cn"], p["material"], envelope=envelope)
    if _PARTS_ROUTING_AVAILABLE:
        _decision = route(p["name_cn"] or "", _geom, _templates)
        print(f"  [routing preview] ...")
        # ★ Track A2：decision 不再 dormant，喂回 geom
        if _decision.template is not None:
            geom = _apply_template_decision(geom, _decision, p, spec_path)   # ★ 新增 helper
    # 下游 part_module.py.j2 按扩充的 geom["type"] 命中 flange / housing / bracket / spring_mechanism 分支
```

**`_apply_template_decision(geom, decision, part_row, spec_path)`** 新增在 `gen_parts.py`，负责：
- 把 `decision.template.name`（例如 `"flange"`）填回 `geom["type"]`
- 读 `CAD_SPEC.md §2.1` 的参数表抽出零件专属尺寸（FLANGE_OD / HOUSING_WALL 等），回填 `geom["template_params"]` 字典
- 缺参时保留 `geom["type"]="fallback"` 降级（保持现状，不倒退）

**`part_module.py.j2` 扩展**：新增 4 个 `{% elif geom_type == "flange" %}` / `{% elif geom_type == "housing" %}` ... 分支，调 `codegen/part_templates/*.py` 的 `make_flange(**params)` / `make_housing(**params)` 等工厂函数生成 cq.Workplane 表达式。老 fallback 分支保留兜底。

**`codegen/part_templates/` 存在性抉择**：四个半参数工厂函数放 `codegen/part_templates/flange.py` 等普通 Python 模块，不用 Jinja（它们是 Python 代码生成器，而非静态模板）。这与 `codegen/` 目录既有 `gen_*.py` 工具脚本风格对齐；不复用 `templates/` 目录（该目录是 Jinja .j2 文件）。

### 4.5 与 `orientation_check` 的兼容

gen_parts 的 TODO markers 里包含 `principal_axis` / `min_ratio`；Track A2 新模板必须在生成代码时一并填充这些字段（按模板自身的建模方向写死，例如法兰 `principal_axis='z'`）——否则 `orientation_check` 阶段会反复告警。

---

## 5. A3 — parts_library routing 可观测性 + adapter 修复

### 5.1 当前黑盒现象

今天跑出 25 个 `std_*.py` 文件头全带 `"Simplified representation for visualization only"`，这是 `jinja_primitive_adapter` 产出的标识。但 parts_library.yaml 对 bearing/fastener 等类别明确路由到 `bd_warehouse` / `sw_toolbox`。实际命中哪条规则、为何失败，**现有日志不透明**。

### 5.2 resolve_report 结构

**归属**：`PartsResolver` 类的**实例方法**（`parts_resolver.py:115`），与 `coverage_report()`（:251）**并列**。调用方式同既有模式：

```python
from parts_resolver import default_resolver
resolver = default_resolver(project_root=...)
report = resolver.resolve_report(bom_rows)   # ★ 新方法
```

不新增模块级函数；不改 `resolve(query: PartQuery) -> ResolveResult` 的任何契约。产出 JSON：

```json
{
  "schema_version": 1,
  "run_id": "20260420-145807",
  "total_rows": 54,
  "adapter_hits": {
    "sw_toolbox":    {"count": 0,  "unavailable_reason": "toolbox path unhealthy: swbrowser.sldedb missing"},
    "bd_warehouse":  {"count": 0,  "unavailable_reason": "import bd_warehouse failed: ModuleNotFoundError"},
    "step_pool":     {"count": 4,  "unavailable_reason": null},
    "partcad":       {"count": 0,  "unavailable_reason": "partcad.enabled=false in parts_library.yaml"},
    "jinja_primitive": {"count": 50, "unavailable_reason": null}
  },
  "rows": [
    {
      "bom_id": "GIS-EE-001-03",
      "name_cn": "O型圈",
      "matched_rule_idx": 4,
      "matched_adapter": "jinja_primitive",
      "attempted_adapters": ["sw_toolbox(unavailable)", "step_pool(miss)", "bd_warehouse(unavailable)", "jinja_primitive"],
      "status": "fallback"
    }
    // ...
  ]
}
```

**`schema_version` 字段**：供消费方（`sw_report.html` / `sw-inspect`）读 JSON 前校验；未知版本降级显示原始字段，不崩溃。

**大 BOM 体积分档**（边界审查 C4.1）：2000+ 行 BOM 按下表分档生成，避免 JSON >10MB 把 sw_report.html 加载卡死：

| BOM 行数 | rows[] 字段内容 |
|---|---|
| ≤ 200 | 每行完整含 attempted_adapters 详列 |
| 200 - 1000 | 每行含 matched_adapter + status；attempted_adapters **仅失败行保留详列** |
| > 1000 | 按 adapter 聚合计数（只写 `adapter_hits`），`rows` 仅列 `status != "hit"` 的前 100 行做抽样诊断；其余以 `"truncated": true, "sampled": 100, "total": N` 顶层字段说明 |

**`rows[].status` 值域枚举**（边界审查维度 1 W）：`Literal["hit", "fallback", "miss"]` — `hit` = 匹配到非 fallback adapter；`fallback` = 最终落到 `jinja_primitive`；`miss` = resolve_report 生成时无 adapter 可用（极端情况）。`sw_report.html` 按此枚举上色。

**`unavailable_reason` 字符串来源契约**：
- 来自 `adapter.is_available() -> tuple[bool, Optional[str]]` 的 reason 字段（见 §5.4.1），不在 resolver 侧硬编码
- Track B 打通 sw_toolbox 路径后，`SwToolboxAdapter` 的 reason 会自动切换（例如 `"toolbox path unhealthy: swbrowser.sldedb missing"` → `null`），Track A resolve_report 代码不用改

### 5.3 落点

- `parts_resolver.py`：`PartsResolver` 类加 `resolve_report(bom_rows) → ResolveReport` 实例方法（与 `coverage_report()` 并列；内部复用 `resolve(query)` 逐行调用 + 采集 attempted_adapters）
- `gen_std_parts.py`（gen_std_parts.py:38 已 `from parts_resolver import PartQuery, default_resolver`）每次跑完调 `resolver.resolve_report(bom)` 写到 `artifacts/{run_id}/resolve_report.json`
- `sw_report.html` 模板扩展加 "Routing attempts" 区块，读同一 JSON 展示
- `cad_pipeline.py sw-inspect` 增 `--resolve-report` 标志直接展示

### 5.4 Adapter 可用性审计 + `is_available()` 契约升级（**不动 yaml**）

**系统分析师 CRITICAL 审查**：现有 `PartsLibraryAdapter.is_available() -> bool`（`adapters/parts/base.py:31`）只返 bool 无 reason，`resolve_report` 的 `unavailable_reason` 字段无真实来源。Track A3 同步做契约升级：

#### 5.4.1 契约变更

```python
# adapters/parts/base.py（现状 → Track A3）
class PartsLibraryAdapter:
    def is_available(self) -> tuple[bool, Optional[str]]:          # ★ 从 -> bool 扩展
        """Return (available, reason_if_unavailable).
        Default impl: (True, None). Subclass overrides."""
        return True, None
```

4 个 concrete adapter 同步更新：
- `BdWarehouseAdapter.is_available()` → 失败时 `(False, "import bd_warehouse failed: ModuleNotFoundError")` 等具体原因
- `StepPoolAdapter.is_available()` → 失败时 `(False, "no STEP files under std_parts/ or shared cache")`
- `PartCADAdapter.is_available()` → 失败时 `(False, "partcad.enabled=false in yaml")`
- `SwToolboxAdapter.is_available()` → **Track B 范围**（B-2 解耦 Add-in 硬门；reason 字段 Track B 填）

**向后兼容**：所有现有调用方（resolver 里 `if adapter.is_available(): ...`）改成 `ok, _ = adapter.is_available(); if ok: ...`；3 个 call sites 在 `parts_resolver.py` 里，小范围改动。

#### 5.4.2 Adapter 审计范围

按当前 routing 逻辑审：

| Adapter | 当前 `is_available()` 条件 | 预期 Track A3 后 reason | 预期审计结论 |
|---|---|---|---|
| `BdWarehouseAdapter` | `import bd_warehouse` 不抛 | `"import bd_warehouse failed: <exc_name>"` | 若审计发现 import 链坏（`build123d` 版本不兼容）→ 修依赖声明 + env-check 引导 |
| `StepPoolAdapter` | 至少一个 `std_parts/<vendor>/*.step` 能找到 | `None`（预期可用）| 今天命中 4 件，路径正常 |
| `PartCADAdapter` | yaml `partcad.enabled=true` | `"partcad.enabled=false in parts_library.yaml"` | 默认 `false`，**不改** |
| `SwToolboxAdapter` | Track B 领地 | Track B 填 | Track A 不动 |

**结果**：Track A3 **预期修 bd_warehouse 依赖 1 点 + base.py 契约 1 点 + 3 个 adapter 同步**。若 bd_warehouse import 可用但仍不命中任何 BOM 行（当前 routing 规则下 BOM 关键词匹配不上），则写入 `resolve_report.log` 并由 maintainer 决定是否改 yaml mapping —— yaml 决策仍不在 Track A3 范围。

#### 5.4.3 `resolve_report` vs `coverage_report` 职责切割（架构师审查）

| 报告 | 语义 | 时机 | 落点 |
|---|---|---|---|
| `coverage_report()` (既有) | **静态** yaml 规则覆盖率分析（不跑真实 resolve），适合 "检查 yaml 配置的规则是否覆盖典型 BOM 形态" | 手工 call 或 demo_bom 单测 | 返回多行字符串 |
| `resolve_report(bom)` (新增) | **动态** 跑完真实 resolve 后的 per-row 命中轨迹（含 attempted_adapters + unavailable_reason）| 每次 `gen_std_parts` 执行 | 返回 dataclass → 序列化 `artifacts/{run_id}/resolve_report.json` |

两者不重叠、不合并；`coverage_report` 做"配置审查"，`resolve_report` 做"运行诊断"。未来若两边消费需求增加，各自独立演进不交叉。

---

## 6. 数据流与调用关系

### 6.1 Track A1 数据流

```
SW install detect → SwInfo.textures_dir
                              │
                              ▼
cad_pipeline.cmd_render  ── env["SW_TEXTURES_DIR"] ── blender subprocess
                                                            │
                                                            ▼
render_3d.create_pbr_material(name, params)
    ├─ params["base_color_texture"] ── _resolve_texture_path() ── bpy.data.images.load()
    ├─ params["normal_texture"]    ── ..
    ├─ params["roughness_texture"] ── ..
    └─ params["metallic_texture"]  ── ..
                              │
                              ▼
              ShaderNodeBsdfPrincipled + ShaderNodeTexImage 节点图
```

### 6.2 Track A2 数据流

```
CAD_SPEC.md §2.1 参数表 + §6.4 envelope + BOM
        │
        ▼
gen_parts.generate_part_files() 对每行自制件 p：
        ├── _guess_geometry(p["name_cn"], p["material"], envelope=envelope)
        │     → geom = {"type": "fallback", "envelope_w", ...}       （既有）
        │
        ├── cad_spec_gen.parts_routing.route(name_cn, GeomInfo, templates)
        │     → RouteDecision{outcome, template}                      （既有但 dormant）
        │
        ├── _apply_template_decision(geom, decision, p, spec_path)   ★ Track A2 新增
        │     ├── decision.template 命中 flange/housing/bracket/spring_mechanism
        │     ├── 从 CAD_SPEC.md §2.1 抽 FLANGE_OD / HOUSING_WALL 等 →
        │     │   geom["template_params"]
        │     └── 或参数缺失 → geom["type"]="fallback" 降级
        │
        └── part_module.py.j2 .render(**geom_vars)
              ├── {% if geom_type=='flange' %}     make_flange(**p)   ★ 新分支
              ├── {% elif geom_type=='housing' %}  make_housing(**p)  ★ 新分支
              ├── {% elif geom_type=='bracket' %}  make_bracket(**p)  ★ 新分支
              ├── {% elif geom_type=='spring_mechanism' %} ...        ★ 新分支
              └── {% else %}                       envelope primitive (既有 fallback)
```

### 6.3 Track A3 数据流

```
BOM rows
   │
   ▼
default_resolver(project_root)  → PartsResolver 实例（既有）
   │
   ▼
resolver.resolve_report(bom)    ★ 新增实例方法（与 coverage_report() 并列）
   │
   ├─ 内部对每行 BOM 调 self.resolve(query) + 采集 attempted_adapters
   │    （每个 adapter 的 is_available() 失败原因通过 adapter.unavailable_reason 收集）
   │
   ▼
ResolveReport dataclass
   │
   ├── gen_std_parts.py 写 artifacts/{run_id}/resolve_report.json
   ├── sw_report.html 扩展读此 JSON
   └── cad_pipeline.py sw-inspect --resolve-report 展示
```

---

## 7. 向后兼容性

| 变更 | 现有行为 | Track A 行为 | 破坏性? |
|---|---|---|---|
| `MATERIAL_PRESETS` 每个 preset 新 4 字段 | 缺省 | 仍缺省 → 纯色 BSDF；`resolve_material(entry)` 的 copy 会自动透传给 `create_pbr_material` | 否 |
| `create_pbr_material(name, params)` 签名 | 现状 | 不变（内部按 params 的新 key 有无分支） | 否 |
| `SwMaterial.texture_files` 新字段 | 不存在 | 默认 `{}`，value 类型 `str`（与兄弟字段 `shader_path: Optional[str]` 对齐）| 否 |
| `parse_sldmat` 返回值 | `list[SwMaterial]` | 仍是 `list[SwMaterial]`，每个多一个 `{}` 字段 | 否 |
| `_run_subprocess` 签名 | `(cmd, label, dry_run, timeout, warn_exit_codes)` | 追加 `env: dict\|None = None` 可选参数；老调用点不改 | 否 |
| `cmd_render` 子进程 env 注入 | 继承父进程 | 父进程 env + `SW_TEXTURES_DIR`（如果 SW 装了）| 否 |
| `gen_parts.py` 输出文件 | `ee_*.py` 含 TODO | 法兰/壳体/支架/弹簧 4 类内部用模板工厂生成实体；其余仍 envelope fallback | 否（文件名、模块符号未变） |
| `part_module.py.j2` | 仅 fallback 分支 | 加 4 个 `{% elif %}` 分支；老 fallback 保留 | 否 |
| `PartsResolver.resolve_report()` | 不存在 | 新增实例方法（与 `coverage_report()` 并列） | 否 |
| `PartsLibraryAdapter.is_available()` 签名 | `-> bool` | `-> tuple[bool, Optional[str]]` | **是**（小幅，但 4 adapter + 3 call sites 需同步改） |
| `artifacts/{run_id}/resolve_report.json` | 不存在 | 新增（带 `schema_version: 1`）| 否 |
| `artifacts/{run_id}/blender_texture_count.json` | 不存在 | 新增 | 否 |
| `make_*()` 模板工厂函数返回值 | 不存在 | `tuple[cq.Workplane, dict]`（元信息含 local_principal_axis 等）| 新增，无既有 API |
| `render_config.json material_overrides` | 不支持 | 新增顶层字段；缺省时无行为差异 | 否 |
| `_parse_annotation_meta` 的 dim_tolerances 抽取 | 不按零件过滤（bug）| 按零件 part_no 过滤；`CAD_SPEC_GEN_DIM_FILTER=off` 回退 | **是**（正面 bug 修复，但会改变既有 CI 快照，需同步更新快照）|

**零破坏性**：所有老调用不需要改一行；即便 Track A 全卸载，v2.11 行为 1:1 恢复。

---

## 8. 测试与验收

### 8.1 单元测试（RED → GREEN）

**marker 策略**（CI Linux matrix 兼容 — 一致性审查 C4.4）：凡 import `bpy` / `winreg` / `pywin32 COM` 者必须标 `@pytest.mark.requires_windows`（conftest 已实现 skipif 机制，记忆 `feedback_ci_windows_only_skipif`）；纯 Python 数据解析不需 marker。

| 模块 | 测试 | marker |
|---|---|---|
| `test_render_3d_texture_bridge.py` | (a) preset 带 `base_color_texture` 时节点图有 `ShaderNodeTexImage` 且连到 BSDF.Base Color；(b) 字段缺省时退回纯色路径；(c) 路径不存在时 warning + 纯色 fallback；(d) **conftest 层 mock 扫描**（防 bug #4 + skill dev W6）：`grep -rn "is_available" tests/conftest.py tests/**/*.py` → 所有 mock 返回值同步改 `tuple[bool, Optional[str]]` | `@pytest.mark.requires_windows`（import bpy） |
| `test_sw_material_bridge_textures.py` | (a) sample sldmat 解析出 `texture_files` dict；(b) 缺 TextureFileName 标签时 dict 为空；(c) 字段向后兼容（v2.11 老 `SwMaterial` 无 `texture_files` 的构造仍 ok）| 纯 Python（XML parse）|
| `test_gen_parts_templates.py` | (a) 法兰关键词匹配到 `flange.py` 模板；(b) §2.1 缺 `FLANGE_OD` 时回退 envelope；(c) 生成代码含 `principal_axis` 正确填充；(d) **全件降级守护**（W2）：11 件 mock 全缺 §2.1 参数时，`log.error("template coverage regression")` 被调用且 `template_decision_report.json` 产出 | 纯 Python（CadQuery import 仅 script-level）|
| `test_parts_resolver_report.py` | (a) 54 行 BOM 产生 54 行 report；(b) adapter unavailable 时 reason 非空；(c) attempted_adapters 列表完整；(d) **大 BOM 分档**（X4）：2500 行 BOM 触发 `truncated: true`，sampled=100；(e) rows[].status 枚举完整（hit/fallback/miss）| 纯 Python（resolver + yaml）|
| `test_render_3d_blender_crash_fallback.py` | **新增**（防 bug #10 重犯）：(a) mock Blender exit 0 但不写 texture_count.json → `cmd_render` 返回 1 + 打印 `[ERROR] Blender crashed silently`；(b) mock schema_version=0 → ERROR | 纯 Python（mock subprocess 结果）|
| `test_render_3d_existing_presets_no_regression.py` | **新增**（架构师 INFO）：对 8 个既有 preset 不填 texture 字段时，`create_pbr_material` 产出的节点图拓扑与 v2.11 byte-level 等价 | `@pytest.mark.requires_windows`（import bpy） |

### 8.2 集成测试（硬验收 — 审查强化）

**必须通过**：`end_effector` 子系统跑 `cad_pipeline.py full --subsystem end_effector --design-doc docs/design/04-*.md`：

1. **纹理实际加载**：`artifacts/{run_id}/blender_texture_count.json` 存在且 `total_loaded > 0`（替代原"PNG >500KB"的弱验收）
2. **模板覆盖硬下限**：至少 3 件自制件的生成代码 `geom_type ∈ {flange, housing, bracket, spring_mechanism}`（通过 ast 扫描 ee_*.py 的 template render context 验证）；低于即整体 exit 2
3. **resolve_report 诊断能力**：`resolve_report.json` 中 `bd_warehouse` 若 count=0，`unavailable_reason` **必须非空**（至少能诊断出失败原因，而非空字符串）
4. **像素方差下限**：任一 patch 区域 stddev > 阈值（避免纯色块通过大小验收）
5. **dim_tolerances 过滤验证**：`ee_001_01.py` 的 `dim_tolerances` 不含 `SPRING_PIN_BORE` / `ARM_L_2` 等非法兰条目（A2-0 precursor 的硬回归 gate）
6. **clash detection pre/post 对比表**（机械设计师审查）：A2 合入后若 GATE-3.5 新增 clash，**不自动 block**，由 designer 判定真伪（原 envelope 擦边掩盖的真实间隙问题暴露属预期）；但必须产出 `artifacts/{run_id}/clash_diff.json` 记录 delta
7. **DXF 产物回归**（annotate 阶段，审查 C3.6）：A2-0 修 `_parse_annotation_meta` 之后，`ee_001_01_sheet.dxf` 的标注条目数应**减少**（只剩法兰专属尺寸），数量下限由 `tests/snapshots/ee_001_01_sheet_stdout.txt` 存档；超出合理范围（比如原 12 条骤降至 0）→ return 1
8. **所有 artifacts JSON 带 schema_version**（防 cross-version bug）：`blender_texture_count.json` / `resolve_report.json` / `clash_diff.json` 三份顶层均含 `schema_version: 1`；消费方读前校验，schema 不匹配视为 miss

### 8.3 视觉回归（人工）

三张代表性 diff（pre-Track-A / post-Track-A）存档到 `docs/images/track-a-visual-regression/`：
- V1 front iso（主展示）
- V2 rear oblique（背面）
- V4 exploded（爆炸图）

---

## 9. 任务拆分（供 writing-plans 细化）

| Task 编号 | 子项 | 内容 | 预估 |
|---|---|---|---|
| A1-0 | A1 | ✅ **已完成（2026-04-20）**：Spike 结论 = Generated + BOX + Bump 作默认（UV 路径 future）；详见 §3.2.1 + 附录 E | 0.25d |
| A1-0b | A1 | `_run_subprocess` 加可选 `env` 参数；老调用点回归测试 | 0.25d |
| A2-0 | A2 | **Precursor**（A2 实施前必做）：`_parse_annotation_meta` 按零件 `part_no` 过滤 dim_tolerances；`CAD_SPEC_GEN_DIM_FILTER=off` 回退；硬测 `ee_001_01.py` dim_tolerances 不含 SPRING_PIN_BORE | 0.75d |
| A3-0 | A3 | `PartsLibraryAdapter.is_available() -> tuple[bool, Optional[str]]` 契约升级 + 4 adapter 同步 + 3 call sites 改 | 0.5d |
| A1-1 | A1 | `render_3d._resolve_texture_path()` + 环境变量读取 + 单测 | 0.5d |
| A1-2 | A1 | 扩展 `create_pbr_material` 新字段处理 4 种贴图节点 + 单测 | 1d |
| A1-3 | A1 | `cmd_render` 注入 `SW_TEXTURES_DIR` env + 单测 | 0.25d |
| A1-4 | A1 | `render_config.py` 内 8-10 个常用 preset 回填纹理字段 | 0.5d |
| A1-5 | A1 | `SwMaterial.texture_files` 扩展 + `parse_sldmat` 解析 + 单测 | 1d |
| A2-1 | A2 | `codegen/part_templates/flange.py` + 单测 | 0.5d |
| A2-2 | A2 | `housing.py` + `bracket.py` + `spring_mechanism.py` + 单测 | 1.5d |
| A2-3 | A2 | `gen_parts.match_semi_parametric_template()` 路由 + 单测 | 0.5d |
| A2-4 | A2 | 集成：`ee_001_01.py`（法兰）走模板；人工目测验收 | 0.5d |
| A3-1 | A3 | `parts_resolver.resolve_report()` + 单测 | 0.5d |
| A3-2 | A3 | `gen_std_parts.py` 调用 + `artifacts/` 写入 | 0.25d |
| A3-3 | A3 | `bd_warehouse` import 链审计 + 依赖修复（若需要） | 0.5d |
| A3-4 | A3 | `sw_report.html` 扩展 Routing 区块 + `sw-inspect --resolve-report` | 0.5d |
| **合计** | | | **~10d**（1.5 人 workweek，含 precursor A2-0 / A3-0 + spike） |

---

## 10. 与 Track B 的边界

| 议题 | 归属 |
|---|---|
| `find_toolbox_addin_guid` 扫描全量 AddIns | **Track B** |
| `SwToolboxAdapter.is_available()` 解耦 Add-in 硬门 | **Track B** |
| sldprt → STEP 真件转换流水线 | **Track B** |
| SW 纹理 `install_dir/data/Images/textures` 直接读 | **Track A1**（不依赖 Add-in 状态，只需 SW 装了）|
| sldmat 解析 `texture_files` 字段 | **Track A1**（`parse_sldmat` 已是静态 XML 解析，与 COM 无关）|
| `SwMaterial.texture_files` → `render_config` preset 字段 | **Track A1** |
| `resolve_report` 观测 | **Track A3** |
| bd_warehouse import 链修复 | **Track A3** |

**关键原子性**：Track A 成功与否**完全不依赖 Track B**。Track B 交付后，Track A 自动受益（sw_toolbox 命中数跳高），但无需回改 A1/A2/A3 代码。

---

## §11 失败诊断 + 用户引导（非专业用户审查）

### 11.1 Maintainer vs 用户的责任划分

2026-04-20 第四轮审查（非专业用户视角）发现 A1-0 spike / B1-0 smoke test / 环境变量设置 / preset 贴图表维护**普通用户做不了**。Track A 生命周期内这些必须由 maintainer 在**发版前完成**，用户端零感知：

| 责任 | 执行方 | 时机 |
|---|---|---|
| A1-0 GLB UV layer spike | **Maintainer** | v2.12 发版前；决策写死到 `MATERIAL_PRESETS` 默认路径 |
| A1-4 preset 贴图映射回填（至少 10 张常用 preset）| **Maintainer** | v2.12 发版硬 gate — 回填不达 10 张不能发版 |
| 环境变量 `CAD_SPEC_GEN_TEXTURE_DIR` / `SW_TEXTURES_DIR` | **自动 detect** | `cmd_render` 启动时自动探测 SW 装机目录（见 §3.3 注入逻辑），用户无需手设 |
| `render_config.json material_overrides` | 用户（可选）| 仅高级用户需要覆盖默认贴图时 |

### 11.2 失败消息人话化映射

**原则**：对普通用户的错误消息必须一句中文+一句行动指引；技术细节（CLSID / 注册表 key / subprocess exit code）**只写 artifacts/ 下 log 文件**，stdout/对话里只出人话。

| 技术 reason | 人话消息 | 建议动作 |
|---|---|---|
| `"texture_dir mismatch: SW_TEXTURES_DIR=... total_loaded=0/N"` | `未找到 SOLIDWORKS 纹理文件，图将以纯色显示。` | `检查 SOLIDWORKS 是否完整安装了"材质库"组件；或联系 IT 核对纹理目录权限` |
| `"import bd_warehouse failed: ModuleNotFoundError"` | `标准件模型库未就绪，部分标准件将以占位几何显示。` | `管理员重装插件：pip install bd_warehouse` |
| `"Blender crashed silently — exit 0 but texture_count.json missing"` | `渲染引擎意外退出，本次渲染未完成。` | `请重试；多次失败联系技术支持并附 artifacts/{run_id}/ 目录` |
| `"template coverage regression: X/Y degraded"` | `{N} 件自制零件未能自动建模，将以方块占位。` | `通常是设计文档 §2.1 尺寸表未完整；补全 FLANGE_OD / HOUSING_WALL 等条目后重跑` |

这些文案不写到代码里，写到 `docs/user_troubleshooting.md`（新建），发版时一并更新。

### 11.3 Maintainer 发版 checklist（quality gate）

v2.12 发 Track A 时在 release note 明示以下 7 项全过 ✅：

- [ ] A1-0 spike 结论文档化（选定 UV / Generated 默认）
- [ ] A1-4 ≥ 10 个 preset 带 base_color_texture（金属 ≥ 3、塑料 ≥ 3、橡胶/陶瓷 ≥ 2、PEEK/复合材料 ≥ 2）
- [ ] A2-0 Precursor 合入 + CI 快照更新
- [ ] `blender_texture_count.json` + `resolve_report.json` + `clash_diff.json` 三份 JSON 顶层 `schema_version: 1` 核对一致
- [ ] `end_effector` 回归：`blender_texture_count.json.total_loaded > 0` ✅
- [ ] `end_effector` 回归：至少 3 件自制件 geom_type ∈ 4 类 ✅
- [ ] `docs/user_troubleshooting.md` 覆盖 §11.2 所有失败消息 ✅

### 11.4 Track A 对"北极星"的诚实评估

- **零配置**（✅ 基本达成）：纹理自动 detect；`material_overrides` 可留给高级用户
- **装即用**（⚠️ Pro+ 达成；Standard 部分达成）：Track A 的贴图桥不依赖 Add-in 启用；但标准件几何仍需 bd_warehouse 或 sw_toolbox 其一可用（Track B 领地）
- **结果准确**（⚠️ 部分）：3 件自制件像，8 件仍 envelope 占位；用户端产出报告必须把"已建模/占位"**分区展示**（render_3d 产物按 `geom_type` 打 metadata），而非混着出让用户以为工具做烂了
- **傻瓜式**（✅）：所有用户接触面限于 markdown 设计文档 + 产物 JPG/DXF；技术细节全埋管线内

---

## 附录 A：涉及文件清单

**修改**（向后兼容）：
- `src/cad_spec_gen/render_3d.py` — create_pbr_material + 纹理路径解析
- `render_config.py` — preset 字段扩展 + 8-10 个 preset 回填
- `cad_pipeline.py` — cmd_render 的 env 注入
- `codegen/gen_parts.py` — 半参数模板路由
- `parts_resolver.py` — resolve_report 函数
- `adapters/solidworks/sw_material_bridge.py` — SwMaterial + parse_sldmat
- `codegen/gen_std_parts.py` — resolve_report 调用
- `adapters/parts/bd_warehouse_adapter.py` — 依赖引导（若审计需要）
- `sw_report.html` 模板 — Routing 区块

**新增**：
- `codegen/part_templates/flange.py`
- `codegen/part_templates/housing.py`
- `codegen/part_templates/bracket.py`
- `codegen/part_templates/spring_mechanism.py`
- `tests/test_render_3d_texture_bridge.py`
- `tests/test_sw_material_bridge_textures.py`
- `tests/test_gen_parts_templates.py`
- `tests/test_parts_resolver_report.py`
- `docs/images/track-a-visual-regression/*`（人工样本）

---

## 附录 B：v0.1 → v0.2 修订日志（审查闭环）

| # | 审查严重性 | 问题 | 修订位置 |
|---|---|---|---|
| R1 | CRITICAL | §4.4 原引用 `resolve_part()`/`emit_fallback()` 函数不存在 | §4.1/4.4 重写按真实 `generate_part_files()` + `parts_routing.route()` + `part_module.py.j2` 架构；改为"激活已 dormant 的 decision"，而非引入新函数 |
| R2 | CRITICAL | §5.2 原说 `parts_resolver.resolve()` 是模块级函数；实际是 `PartsResolver` 类实例方法 | §5.2/5.3/§6.3 改为 `PartsResolver.resolve_report()` 实例方法（与 `coverage_report()` 并列） |
| R3 | WARNING | §3.3 `_run_subprocess` 无 `env` 参数 | §3.3 明确加前置改动；§7 兼容性表新增一行；§9 新增 task A1-0b |
| R4 | WARNING | §3.2 `TexCoord.UV` 与既有 `render_3d.py:415` 的 `Generated` 不一致 | §2 决策 A-3 + §3.2 节点连接表改 `Generated`；§9 新增 spike task A1-0 |
| R5 | WARNING | §3.4 `shader_path` 类型实际是 `Optional[str]` 非 `Path`；`texture_files` value 混用 `Path` 类型不一致 | §3.4 统一用 `str`；加 rationale 段 |
| R6 | INFO | §2 决策 A-2 未明确 `MATERIAL_PRESETS` → `resolve_material` → `create_pbr_material` 的传递路径 | §2 决策 A-2 精炼表述 |

---

## 附录 C：v0.2 → v0.3 修订日志（5 角色专家审查闭环）

审查角色：系统架构师 / SW 操作员 / 3D 设计师 / 机械设计师 / 系统分析师。

### C.1 CRITICAL 修正（实施前必改）

| # | 来源角色 | 问题 | 修订位置 |
|---|---|---|---|
| C1 | 机械设计师 | 4 类模板宣称覆盖 ≥40/54，实际 11 件自制件里只能套 5 件（45%）| §1.2 覆盖率表校准；§4.2 改 4 类基础 + 5 类 future 预留（total 8 类）；实测覆盖 ≈ 20/54 作为新基线 |
| C2 | 机械设计师 | §2.1 `dim_tolerances` 抽取器不按零件过滤；两件共享同一 dict —— Track A2 建在沙子上 | §4.3.1 新增 Precursor Task **A2-0**（A2 前必做）；§7 兼容性表加一行；§8.2 硬验收第 5 项 |
| C3 | 3D 设计师 | `TexCoord.Generated` 对圆柱件侧面压成线产生重度拉伸 | §3.2 节点连接表重写：有 UV 路径默认走 `UV + Mapping(Scale) + TANGENT normal`；无 UV 路径必须加 `projection='BOX'` + `projection_blend=0.2`；§3.2.1 Blender 4.2 LTS 版本矩阵 |
| C4 | 3D 设计师 | 切线空间 normal map 无 UV + 无 Tangent 则彻底失效，视觉比纯色还糟 | §3.2 无 UV 降级路径改为 `ShaderNodeBump` 替代 `ShaderNodeNormalMap`（跳过 tangent-space）；§3.2 附 SW DirectX 约定 Y 通道翻转处理 |
| C5 | 系统架构师 | 纹理字段加在 Python `MATERIAL_PRESETS` dict，用户无法通过 JSON 覆盖 —— 违反北极星"零配置 + 傻瓜式" | §2 决策表加 A-12：`render_config.json material_overrides` 覆盖层（MATERIAL_PRESETS → sldmat auto → JSON overrides 三级优先）|
| C6 | 系统架构师 | §10 边界未锁 `SwInfo.textures_dir` schema 冻结声明 | §2 决策表加 A-15：Track A 生命周期内两 track 都不得改 SwInfo.textures_dir 结构 |
| C7 | 系统分析师 | `resolve_report.unavailable_reason` 生产链断：adapter `is_available() -> bool` 无 reason 字段 | §5.4.1 契约升级 → `tuple[bool, Optional[str]]`；4 adapter + 3 call sites 同步；Task A3-0 precursor |

### C.2 WARNING 修正（跨多角色验证的高频点）

| # | 来源 | 问题 | 修订位置 |
|---|---|---|---|
| W1 | 系统分析师 | 验收"PNG >500KB"过松，无法检测纹理加载 silent-fail | §1.2 指标表 + §8.2 第 1 项硬验收：`blender_texture_count.json.total_loaded > 0` |
| W2 | 系统分析师 | `_resolve_texture_path` 只 per-material warn，SW_TEXTURES_DIR 坏时无全局告警 | §3.3 新增子进程写入 + cmd_render 后读聚合告警 |
| W3 | 3D 设计师 | base_color 未显式 sRGB / 未加 `ShaderNodeMapping.Scale` 物理尺度 / SW 导出 normal 是 DirectX 约定 | §3.2 节点表三列补齐 |
| W4 | 机械设计师 | envelope bbox 不含方向，`make_flange(od, t)` 缺消歧规则 | §4.3.3 消歧规则：§6.3 serial_chain.axis > §6.4 hint > 退 primitive 不强 fallback |
| W5 | 机械设计师 | 模板 `principal_axis='z'` 硬写死，与装配姿态冲突 | §2 决策 A-13：模板返回 `tuple[Workplane, dict]`，axis 由 `_apply_template_decision` 按 §6.3 重映射 |
| W6 | 机械设计师 | A2 合入后可能新增 clash false positive | §8.2 第 6 项：clash pre/post diff 不 block，产物 `clash_diff.json` |
| W7 | SW 操作员 | UNC `\\server\share` 路径 Blender 子进程 Kerberos double-hop 静默失败 | §3.3 新增 UNC 预检 + warning |
| W8 | 架构师 | resolve_report 与 coverage_report 职责切割未说明 | §5.4.3 新增对比表（静态 yaml 覆盖率 vs 动态运行诊断）|
| W9 | 架构师 | resolve_report JSON 无 schema_version | §5.2 JSON 顶层加 `schema_version: 1` |
| W10 | 机械设计师 | 圆角常数 1mm 对 7075-T6 法兰偏小 | §4.3.2 按类别区分：法兰 R3 / 壳体 R1 / 支架 R2 |
| W11 | 3D 设计师 | spring_mechanism 真螺旋 sweep 会让 Cycles BVH 爆炸 | §4.2 表格：`simplified=True` 用 N 个倾斜圆环堆叠，face ≤ 500 |

### C.3 INFO / 暂不处理

- 机械 I1 (bd_warehouse ISO vs GB/T)：标准归档差异留 Track C
- 3D I1 (视图标准集 V3/V4 双前缀)：属 render_config.json schema 治理，不在 Track A 范围
- 系统分析 I1-I5：纹理表维护约定、filesystem 缓存、edition 矩阵、pipeline_config 兜底、UNC 性能 —— 全部记入 `docs/project_debt.md`（Track C 候选）

**最高优先级 3 条** —— v0.3 必修且已落地：C2 (A2-0 precursor) / C3 (BOX projection) / C7 (is_available 契约)。

---

## 附录 D：v0.3 → v0.4 修订日志（第四轮审查闭环）

审查角色：**非专业用户**（小白装备设计师）+ **skill 开发者**（刚修过 7 个 silent-fail bug 的 maintainer）+ **一致性+边界综合**（硬查双文档交叉）。

### D.1 CRITICAL 修正（实施前必改）

| # | 来源 | 问题 | 修订位置 |
|---|---|---|---|
| D1 | skill 开发者 | bug #10 重犯：Blender crash 不写 `texture_count.json`，pipeline 父进程读不到 fallback 未定义 | §3.3 加 subprocess 结束后 4 行判定表（exit × JSON 存在 × schema_version × 判定）|
| D2 | skill 开发者 | bug #1 重犯风险：artifacts/{run_id}/ 新 JSON 路径无 cad_paths helper 声明 | §3.3 明确 `cad_paths.get_run_artifact_path(run_id, name)` helper 引用，禁止字符串拼接 |
| D3 | skill 开发者 | bug #3 重犯风险：日志含中文冒号/emoji 在 GBK 控制台崩 | §3.3 增 "日志文案统一 ASCII" 段：stdout 纯 ASCII，中文走 artifacts/ log 文件 |
| D4 | 一致性 C2.1 | `_resolve_texture_path` 同一 spec 内两处返回类型矛盾（`Optional[Path]` vs 带 convention 元组）| §3.1 拆两个函数：`_resolve_texture_path -> Optional[Path]` + `_detect_normal_convention -> Literal['dx','gl']` |
| D5 | 一致性 C3.6 | A2-0 改 `_parse_annotation_meta` 影响 annotate 阶段 DXF 产物，§8.2 无硬验收 | §8.2 硬验收加第 7 项（DXF 标注条目数快照回归）+ 第 8 项（三 JSON 一律 schema_version=1）|
| D6 | 一致性 C4.1 | resolve_report.json 大 BOM 体积无上限 | §5.2 加三档分级策略（≤200 全量 / 200-1000 失败详列 / >1000 聚合）+ `rows[].status` 值域完整枚举 |
| D7 | 非专业用户 U1 | Standard 版用户"装即用"承诺破产 | §11.4 北极星诚实评估 + §11.3 发版 checklist；指引 release note 改为 "Pro+ 装即用；Standard 用 bd_warehouse 无需 SW" |
| D8 | 非专业用户 U3 | A1-0 spike 是普通用户做不了的步骤 | §11.1 责任划分表明确 maintainer 发版前完成；用户零感知 |

### D.2 WARNING 修正

| # | 来源 | 问题 | 修订位置 |
|---|---|---|---|
| W1 | 一致性 W6 | A §8.1 4 个新测试未标 marker | §8.1 每行补 marker 列；新增 2 个防同族 bug 的测试（blender crash fallback + existing preset regression）|
| W2 | skill 开发者 W1 | env dict 中文 username 路径 subprocess 默静默失败 | 沿用 §3.3 "日志文案统一 ASCII" 策略；env 值非 str 时 raise |
| W3 | skill 开发者 W2 | `_apply_template_decision` 全件降级无告警 | §8.1 test_gen_parts_templates.py case (d)：全件降级触发 log.error + artifacts JSON |
| W4 | 非专业用户 U2 | 错误消息不人话 | 新增 §11.2 人话化映射表 + `docs/user_troubleshooting.md` |
| W5 | 非专业用户 W5 | "3 件像 + 8 件砖头" 混着出 | §11.4 "已建模/占位分区展示" — 产物按 `geom_type` 打 metadata |
| W6 | 非专业用户 W6 | preset 贴图覆盖硬发版 gate | §11.3 发版 checklist 第 2 条硬 gate：≥ 10 preset 回填不达标不能发 |
| W7 | 一致性 C3.5 | §1.3 不动 enhance vs 附录 C 说 sharpness 1.3→1.0 正文未落地 | 附录 D 记 "暂不改 enhance，A1 合入后按 v2.13 观察效果决策" |

### D.3 INFO / 仍然暂不处理

- 一致性 C4.7 中文用户名/路径：记入 `docs/project_debt.md`
- 一致性 C4.2 UNC 路径性能：Track A 已在 §3.3 加预检，足够
- 机械 I2 圆角常数：已在 v0.3 §4.3.2 修（法兰 R3 / 壳体 R1 / 支架 R2）

**最优先 3 条 v0.4 必修且已落地**：D1（Blender crash fallback 判定表）/ D4（`_resolve_texture_path` 类型拆分）/ D8（maintainer vs 用户责任划分）。本轮关闭 8 条 CRITICAL，Track A 无 blocker 进入 writing-plans 阶段。

---

## 附录 E：A1-0 Spike 实施记录（2026-04-20）

**Spike 脚本**：`D:\Work\cad-tests\GISBOT\a1_0_uv_spike.py`
**输入 GLB**：`D:\Work\cad-tests\GISBOT\cad\output\EE-000_assembly.glb`（2026-04-20 session 产出，40 mesh，含 11 自制件 + 25 std 件）
**JSON 报告**：`D:\Work\cad-tests\GISBOT\a1_0_uv_spike_report.json`

### E.1 实测数据

- **技术上有 UV layer**：39 / 40 mesh（仅 1 个空 mesh 无 UV）
- **UV 非退化（真实展开）**：仅 1 个（Blender 默认 Cube，非工程数据）
- **UV 退化（`(0.5, 0.5)` 塌缩）**：38 / 40（95%）
- **tangent 技术可算**：39 / 40，但基于退化 UV 的 tangent 无物理意义
- **所有自制件 + 所有 `std_*` 件**：UV 均退化

### E.2 根因

CadQuery `exporters.export(type=STEP)` 产生 BREP 格式，不含 UV；`consolidate_glb.py` / Blender glTF importer 对无 UV 的 mesh 兜底分配 `(0.5, 0.5)`。这不是 CadQuery 或 Blender 的 bug——是 CAD 工作流缺少"tessellation 时 UV 展开"一步。

### E.3 决策

| 原 v0.4 预期 | A1-0 Spike 实测 | 新决策 |
|---|---|---|
| 有 UV 走 TANGENT 为默认（高精度）| 95% UV 退化 | Generated + BOX + Bump 为**主路径** |
| 无 UV 降级走 Generated+BOX | 主路径不变 | 作为唯一实现路径（A1-1/A1-2 范围内）|
| 两条路径都要实现 | 退化 UV 走 TANGENT 会导致"整个零件一个像素颜色" | TANGENT 路径 **延后到 v0.5**，等 UV 展开流水线接入 |

### E.4 对 v0.4 内容的精修（v0.4.1）

1. §3.2.1 补 A1-0 结论段（已改）
2. §9 Task A1-0 标 ✅ 完成（已改）
3. §3.2 节点连接表"有 UV 路径"列标 *future*，A1-1/A1-2 只实现 Generated+BOX 列（本 appendix 已说明，表文本不动，留作 v0.5 参考）
4. 不影响 §1.2 覆盖率目标（原"3 件自制件 ≥ 30 face"关于几何不关于贴图）

### E.5 后续影响 Track B 吗？

不。Track B 的 sldprt → STEP 转换仍不产生 UV（SW 导出 STEP 与 CadQuery 一样是 BREP）。Track B 合入后 sw_toolbox 件进 GLB 时**也会是退化 UV**，同样走 Generated + BOX 路径。A1-0 决策对 A/B 双 Track 一致。

### E.6 v0.5 候选任务（记入 `docs/project_debt.md`）

- 在 `consolidate_glb.py` 合并 GLB 前或 Blender 渲染 `render_3d.py` 里对 `mesh_has_valid_uv=False` 的 mesh 调用 `bpy.ops.uv.smart_project(angle_limit=66, island_margin=0.02)` 做自动展开；然后 A1 的"UV 路径"代码正式启用
- 评估对渲染时长的影响（Smart UV Project 对 4000 face 的法兰约 +0.1s；40 mesh 累计 +4s 可接受）
