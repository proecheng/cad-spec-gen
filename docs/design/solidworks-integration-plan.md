# SolidWorks 集成实现方案

> 版本: v0.1 draft — 2026-04-12
> 状态: 待评审

## 1. 目标

将用户本机已安装的 SolidWorks（≥2024）资产无缝接入 cad-spec-gen 管道，作为**可选增强层**：

- **有 SW** → 管道自动从 SW 安装目录提取材质属性 + 渲染外观 + Toolbox 标准件几何，覆盖率和渲染真实度显著提升
- **无 SW** → 管道行为与现在完全一致（零退化），仅在 `env-check` 和 codegen 覆盖率报告中提示"安装 SolidWorks 可获得更好效果"
- **不帮助用户安装 SW** — Skill 只做检测 + 提取，不涉及任何安装动作

### 1.1 非目标

- 不做 SolidWorks 的参数化建模（我们只读，不写）
- 不做 PDM Vault 集成（仅读本地安装目录）
- 不做 SW Assembly 约束解析（超出当前管道范围）
- 不在 git 仓库中存储任何 SW 资产（版权合规）

---

## 2. 版权合规分析

| 动作 | 合规性 | 理由 |
|------|--------|------|
| 运行时读用户本机 sldmat XML | ✅ | 等同于 IDE 读已安装 SDK 的配置文件 |
| 运行时 copy 贴图到渲染工作目录 | ✅ | 用户对自己许可软件的正常使用，产物不离开本机 |
| COM 自动化导出 sldprt → STEP | ✅ | SolidWorks EULA 允许 API 自动化；产物留在用户本地 |
| 将提取产物写入 `~/.cad-spec-gen/` | ✅ | 用户本地缓存，不入 git、不上传 |
| 在 git 仓库中捆绑 sldmat/sldprt/贴图 | ❌ 禁止 | 再分发 Dassault 资产违反 EULA |
| 在 skill 代码中硬编码 SW 材质数据 | ❌ 禁止 | 相当于静态再分发 |

**结论**：所有运行时提取 + 本地缓存的操作均合规。Skill 代码仓库中不包含任何 SW 资产。

---

## 3. 系统架构

### 3.1 整体数据流

```
                          ┌─────────────────────────────┐
                          │   SolidWorks 2024+ (本机)     │
                          │  D:\SOLIDWORKS Corp\...      │
                          └──────────┬──────────────────┘
                                     │
                     sw_detect.py 检测版本 + 资产路径
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
              路径 A (纯脚本)    路径 A (纯脚本)    路径 B (COM)
              材质 XML 解析     贴图/外观预设      Toolbox → STEP
                    │                │                │
                    ▼                ▼                ▼
            sw_material_bridge   渲染贴图缓存    step_cache/sw_toolbox/
                    │                │                │
          ┌────────┴───┐            │                │
          ▼            ▼            ▼                ▼
    MATERIAL_PROPS  MATERIAL_    Blender        StepPoolAdapter
    (Phase 1-3)     PRESETS      textures       (现有, 无改动)
                   (Phase 4-5)   (Phase 4)
```

### 3.2 组件清单

| 组件 | 路径 | 职责 | 新增/改动 |
|------|------|------|-----------|
| `sw_detect.py` | `adapters/solidworks/sw_detect.py` | SW 安装检测 + 版本校验 + 资产路径发现 | **新增** |
| `sw_material_bridge.py` | `adapters/solidworks/sw_material_bridge.py` | sldmat XML → MATERIAL_PROPS + MATERIAL_PRESETS 映射 | **新增** |
| `sw_texture_resolver.py` | `adapters/solidworks/sw_texture_resolver.py` | p2m 解析 + 贴图路径重写 + 贴图缓存 | **新增** |
| `sw_toolbox_adapter.py` | `adapters/parts/sw_toolbox_adapter.py` | Toolbox sldprt → STEP 转换 adapter（COM 路径） | **新增** |
| `sw_toolbox_catalog.py` | `adapters/solidworks/sw_toolbox_catalog.py` | 扫描 Toolbox 目录 → 生成标准件目录索引 | **新增** |
| `parts_resolver.py` | `parts_resolver.py` | `default_resolver()` 注册 SW adapter | **改动** (3 行) |
| `cad_spec_defaults.py` | `cad_spec_defaults.py` | `MATERIAL_PROPS` 运行时扩展入口 | **改动** (~10 行) |
| `render_config.py` | `render_config.py` | `MATERIAL_PRESETS` 运行时扩展入口 | **改动** (~10 行) |
| `cad_pipeline.py` | `cad_pipeline.py` | `env-check` 子命令增加 SW 检测报告 | **改动** (~15 行) |
| `parts_library.default.yaml` | `parts_library.default.yaml` | 增加 `solidworks_toolbox` adapter 配置段 + GB/ISO/DIN 匹配规则 | **改动** (~30 行) |

### 3.3 依赖关系

```
sw_detect (零依赖, stdlib only: winreg + os)
    │
    ├── sw_material_bridge (依赖 sw_detect, xml.etree)
    │       │
    │       ├── cad_spec_defaults.MATERIAL_PROPS  (运行时注入)
    │       └── render_config.MATERIAL_PRESETS     (运行时注入)
    │
    ├── sw_texture_resolver (依赖 sw_detect, shutil)
    │       │
    │       └── Blender render_3d.py  (贴图路径)
    │
    └── sw_toolbox_adapter (依赖 sw_detect; pywin32 可选)
            │
            └── StepPoolAdapter (现有, 读缓存的 STEP)
```

---

## 4. 详细设计

### 4.1 `sw_detect.py` — SolidWorks 安装检测

**职责**：检测 SW 安装状态、版本、资产目录路径。**零外部依赖**。

```python
@dataclass
class SolidWorksInfo:
    """SolidWorks 安装信息快照。"""
    installed: bool
    version: Optional[str]          # "2024" / "2025" / None
    version_year: Optional[int]     # 2024 / 2025 / None
    install_dir: Optional[Path]     # D:\SOLIDWORKS Corp\SOLIDWORKS
    sldmat_paths: list[Path]        # [*.sldmat]
    textures_dir: Optional[Path]    # .../data/Images/textures/
    p2m_dir: Optional[Path]         # .../data/graphics/Materials/
    toolbox_dir: Optional[Path]     # C:\SOLIDWORKS Data\browser\
    com_available: bool             # SldWorks.Application CLSID 已注册
    pywin32_available: bool         # win32com.client 可导入
```

**检测策略**（优先级从高到低）：

1. **注册表** — `HKLM\SOFTWARE\SolidWorks\SOLIDWORKS <year>\SolidWorks Folder`
   - 遍历 year ∈ [2030, 2029, ..., 2024]，取最新的 ≥ 2024
2. **已知安装路径扫描** — 扫描 `C:\Program Files\SOLIDWORKS Corp\`、`D:\SOLIDWORKS Corp\` 等常见路径
3. **SLDWORKS.exe 搜索** — `shutil.which("SLDWORKS")` 或 `PATH` 中查找
4. **COM 注册表** — `HKCR\SldWorks.Application\CLSID` 存在性检查
5. **pywin32** — 尝试 `import win32com.client`

**版本校验**：
- 仅接受 version_year ≥ 2024
- 低于 2024 的版本：`installed=True` 但标记 `version_too_old=True`，不启用路径 B（COM 接口变化大），路径 A 可酌情启用

**缓存**：全局单例 `_cached_info: Optional[SolidWorksInfo]`，进程生命周期内只检测一次。

**平台守卫**：非 Windows 平台直接返回 `SolidWorksInfo(installed=False, ...)`。

### 4.2 `sw_material_bridge.py` — 材质桥接

**职责**：解析 sldmat XML → 生成与现有 `MATERIAL_PROPS` / `MATERIAL_PRESETS` 兼容的字典。

**sldmat XML 结构解析**（基于实际文件分析）：

```xml
<mstns:materials encoding="utf-16">
  <classification name="Steel">
    <material name="1023 Carbon Steel Sheet (SS)" matid="82">
      <physicalproperties>
        <EX value="204999998381.83875" />    <!-- 弹性模量 Pa -->
        <NUXY value="0.290000" />             <!-- 泊松比 -->
        <DENS value="7858.000032" />          <!-- 密度 kg/m³ -->
        <KX value="52.000000" />              <!-- 热导率 W/(m·K) -->
        <SIGXT value="425000003.203703" />     <!-- 抗拉强度 Pa -->
        <SIGYLD value="282685049.019888" />    <!-- 屈服强度 Pa -->
      </physicalproperties>
      <shaders>
        <pwshader2 path="\metal\steel\matte steel.p2m" name="matte steel" />
      </shaders>
    </material>
  </classification>
</mstns:materials>
```

**映射规则**：

```
SW sldmat → MATERIAL_PROPS:
  DENS (kg/m³) → density (g/cm³)  # ÷ 1000
  classification → material_type   # Steel→steel, Aluminum→al, Plastic→plastic...
  color         → 从关联 p2m 提取  # 或从 classification 推导默认色

SW sldmat + p2m → MATERIAL_PRESETS:
  p2m 中的 diffuse color → color (RGBA)
  p2m 中的 specular/roughness → metallic, roughness
  classification + name → appearance 文本描述
```

**关键函数**：

```python
def parse_sldmat(path: Path) -> list[SwMaterial]:
    """解析一个 sldmat 文件，返回材质列表。"""

def sw_to_material_props(sw_mat: SwMaterial) -> tuple[str, dict]:
    """SwMaterial → (material_key, MATERIAL_PROPS 格式 dict)"""

def sw_to_material_preset(sw_mat: SwMaterial, p2m_dir: Path) -> tuple[str, dict]:
    """SwMaterial + p2m 外观 → (preset_key, MATERIAL_PRESETS 格式 dict)"""

def load_sw_materials() -> tuple[dict, dict]:
    """一键加载：返回 (扩展后的 MATERIAL_PROPS, 扩展后的 MATERIAL_PRESETS)。
    内部调用 sw_detect → 解析所有 sldmat → 合并。
    SW 未安装时返回空字典。
    """
```

**合并语义**：
- 现有手工定义的 `MATERIAL_PROPS` / `MATERIAL_PRESETS` **优先级最高**（不被覆盖）
- SW 提取的材质作为**补充**，仅填充现有字典中不存在的 key
- 命名约定：SW 材质 key 加 `sw_` 前缀避免冲突，如 `sw_1023_carbon_steel`
- 但对于已知的等价映射（如 SW `"304 Stainless Steel"` ≈ 现有 `"SUS304"`），**不重复注册**

### 4.3 `sw_texture_resolver.py` — 贴图/外观解析

**职责**：解析 p2m 文件 → 提取颜色/PBR 参数 + 贴图路径 → 缓存到本地。

**p2m 文件结构**（XML 格式，参考 `color.p2m`）：

```xml
<!-- p2m 为 SolidWorks Photoview 360 材质预设 -->
<appearance>
  <diffuse r="0.75" g="0.75" b="0.77" />
  <specular r="0.9" g="0.9" b="0.9" />
  <roughness value="0.15" />
  <texture file="textures/metal/brushed_steel.png" />
</appearance>
```

**工作流**：

1. `sw_material_bridge` 解析 sldmat 时遇到 `<pwshader2 path="\metal\steel\matte steel.p2m">`
2. 调用 `sw_texture_resolver.resolve_p2m(p2m_dir / "metal/steel/matte steel.p2m")`
3. 返回 `P2mInfo(diffuse=(r,g,b), specular=(r,g,b), roughness=0.15, texture_paths=[...])`
4. 将 PBR 参数合入 `MATERIAL_PRESETS`
5. 贴图文件 **不拷贝入 git**，仅在 Blender 渲染时按需 symlink/copy 到临时工作目录

**降级策略**：p2m 格式半开放且版本间有变化。解析失败时静默回退到 classification 默认色（不影响管道）。

### 4.4 `sw_toolbox_adapter.py` — Toolbox 标准件 Adapter

**职责**：将 SW Toolbox 的 sldprt 通过 COM 自动化转换为 STEP，对接现有 `StepPoolAdapter`。

**设计决策**：

- **不直接实现 `PartsAdapter` 接口** — 而是作为 `StepPoolAdapter` 的"STEP 供应器"（类似 `vendor_synthesizer`）
- 原因：Toolbox 转换的产物就是 STEP 文件，让 `StepPoolAdapter` 统一管理缓存和路径解析，避免两套缓存机制
- 这意味着 `sw_toolbox_adapter` 注册在 `vendor_synthesizer.SYNTHESIZERS` 中，而非作为独立 adapter

**修正方案**：新增一个独立的 `SolidWorksToolboxAdapter`，因为：
- Toolbox 有 1818 个零件，不可能都预注册在 `SYNTHESIZERS` 中
- 需要按 GB/ISO/DIN 标准 + BOM 名称**动态匹配**
- COM 调用开销大，需要特殊的批量策略

```python
class SolidWorksToolboxAdapter(PartsAdapter):
    """从 SolidWorks Toolbox 提取标准件几何。

    工作流：
    1. is_available() → sw_detect 确认 SW ≥ 2024 + pywin32
    2. resolve() → 匹配 BOM 名称到 Toolbox 目录
    3. 检查 step_cache 是否已有缓存
    4. 缓存命中 → 返回 step_import（与 StepPoolAdapter 行为一致）
    5. 缓存未命中 → COM 打开 sldprt → SaveAs STEP → 写入缓存 → 返回 step_import
    """
    name = "solidworks_toolbox"
```

**Toolbox 目录索引**：

```
~/.cad-spec-gen/sw_toolbox_index.json   ← 首次运行时扫描生成
{
  "version": "2024",
  "scan_time": "2026-04-12T10:00:00",
  "standards": {
    "GB": {
      "bolts and studs": [
        {"file": "gb_hex_bolt_m6.sldprt", "path": "C:/SOLIDWORKS Data/browser/GB/bolts and studs/...", "keywords": ["六角螺栓", "hex bolt", "GB/T 5782"]},
        ...
      ],
      "nuts": [...],
      ...
    },
    "ISO": {...},
    "DIN": {...}
  }
}
```

**匹配算法**：

1. BOM `name_cn` + `material` → `classify_part()` 得到 category（bearing / fastener / ...）
2. Category → 筛选 Toolbox 对应子目录（如 fastener → bolts, nuts, screws, washers）
3. 在子目录的 keywords 中做模糊匹配（TF-IDF 或简单 token overlap）
4. 选置信度最高的 sldprt → 转 STEP

**COM 自动化流程**：

```python
def _convert_sldprt_to_step(sldprt_path: str, step_out: str) -> bool:
    """COM 自动化: sldprt → STEP AP214。

    需要 pywin32。SolidWorks 实例在首次调用时启动，
    批量转换期间保持 session 以避免反复启动开销。
    """
    import win32com.client
    swApp = win32com.client.Dispatch("SldWorks.Application")
    swApp.Visible = False
    # OpenDoc6 → SaveAs3(STEP AP214) → CloseDoc
```

**批量转换策略**：

- **延迟转换**：不在安装时一次性转换所有 1818 个零件
- **按需转换 + 缓存**：第一次 resolve 某个 Toolbox 零件时才触发 COM 转换
- **预热命令**（可选）：`cad_pipeline.py sw-warmup --standard GB` 批量预转换 GB 330 个零件
- 缓存路径：`~/.cad-spec-gen/step_cache/sw_toolbox/GB/bolts/gb_hex_bolt_m6.step`

### 4.5 现有模块改动

#### 4.5.1 `parts_resolver.py` — `default_resolver()` 注册

```python
def default_resolver(...):
    # ... 现有 adapter 注册 ...

    # Phase SW — SolidWorks Toolbox (可选, 需 SW ≥ 2024 + pywin32)
    try:
        from adapters.parts.sw_toolbox_adapter import SolidWorksToolboxAdapter
        sw_adapter = SolidWorksToolboxAdapter(
            config=registry.get("solidworks_toolbox", {}),
        )
        if sw_adapter.is_available():
            resolver.register_adapter(sw_adapter)
    except ImportError:
        pass

    return resolver
```

**影响**：仅增加 ~8 行，`is_available()` 返回 False 时完全无副作用。

#### 4.5.2 `cad_spec_defaults.py` — 材质扩展入口

```python
# 在模块底部增加运行时扩展点
def _extend_material_props_from_sw():
    """运行时从 SolidWorks 加载额外材质属性（如果可用）。"""
    try:
        from adapters.solidworks.sw_material_bridge import load_sw_materials
        sw_props, _ = load_sw_materials()
        for key, val in sw_props.items():
            if key not in MATERIAL_PROPS:  # 不覆盖手工定义
                MATERIAL_PROPS[key] = val
    except ImportError:
        pass

# 模块加载时自动扩展
_extend_material_props_from_sw()
```

**影响**：~10 行。`ImportError` 时静默跳过。

#### 4.5.3 `render_config.py` — 材质预设扩展

```python
def _extend_presets_from_sw():
    """运行时从 SolidWorks 外观预设加载额外 PBR 材质。"""
    try:
        from adapters.solidworks.sw_material_bridge import load_sw_materials
        _, sw_presets = load_sw_materials()
        for key, val in sw_presets.items():
            if key not in MATERIAL_PRESETS:
                MATERIAL_PRESETS[key] = val
    except ImportError:
        pass

_extend_presets_from_sw()
```

**影响**：~10 行，模式与 `cad_spec_defaults.py` 对称。

#### 4.5.4 `cad_pipeline.py` — env-check 增强

```python
def _check_solidworks():
    """检查 SolidWorks 安装状态（信息性，非阻断）。"""
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        info = detect_solidworks()
        if info.installed and info.version_year >= 2024:
            print(f"  SolidWorks {info.version}: ✅ 已检测到")
            print(f"    材质库: {len(info.sldmat_paths)} 个 sldmat 文件")
            print(f"    Toolbox: {info.toolbox_dir or '未发现'}")
            print(f"    COM: {'✅' if info.com_available else '❌'}")
            print(f"    pywin32: {'✅' if info.pywin32_available else '❌ (Toolbox 转换不可用)'}")
        elif info.installed:
            print(f"  SolidWorks {info.version}: ⚠️ 版本低于 2024，部分功能不可用")
        else:
            print("  SolidWorks: 未安装（安装 SolidWorks 2024+ 可获得更丰富的材质库和标准件几何）")
    except ImportError:
        print("  SolidWorks: 检测模块不可用")
```

#### 4.5.5 `parts_library.default.yaml` — Toolbox 规则

```yaml
# ─── SolidWorks Toolbox (可选, 需本机安装 SW ≥ 2024) ───
solidworks_toolbox:
  enabled: auto            # "auto" = 检测到 SW 则启用; "true"/"false" 强制
  standards: [GB, ISO, DIN]  # 仅导入这些标准的 Toolbox 零件
  cache: ~/.cad-spec-gen/step_cache/sw_toolbox/

mappings:
  # SW Toolbox 规则（优先级低于 step_pool 和 bd_warehouse）
  - match:
      category: fastener
      keyword_contains: ["GB/T", "国标", "hex bolt", "六角"]
    adapter: solidworks_toolbox
    spec:
      standard: GB
      subcategory: [bolts and studs, nuts, screws, washers and rings]

  - match:
      category: bearing
      keyword_contains: ["GB/T", "深沟球", "滚针", "推力"]
    adapter: solidworks_toolbox
    spec:
      standard: GB
      subcategory: [bearing]

  # ISO/DIN 兜底
  - match:
      category: fastener
    adapter: solidworks_toolbox
    spec:
      standard: [ISO, DIN]
      subcategory: [bolts, nuts, screws, washers]

  - match:
      category: bearing
    adapter: solidworks_toolbox
    spec:
      standard: [ISO, DIN]
      subcategory: [bearings]
```

---

## 5. 管道数据流一致性保证

### 5.1 设计原则

**透明性**：SW 集成不改变管道的输入/输出接口。每个阶段的输入输出格式不变：

| 阶段 | 输入 | 输出 | SW 影响 |
|------|------|------|---------|
| Phase 1 (spec) | 设计文档 | CAD_SPEC.md | MATERIAL_PROPS 更丰富 → §2 公差/材质表更精确 |
| Phase 2 (codegen) | CAD_SPEC.md | `std_*.py` + `params.py` | 更多零件从 `step_import` 解析（覆盖率 ↑） |
| Phase 3 (build) | Python 代码 | STEP/DXF/GLB | 标准件用 SW 真实几何（精度 ↑） |
| Phase 4 (render) | GLB + config | PNG | MATERIAL_PRESETS 更丰富 → PBR 更真实 |
| Phase 5 (enhance) | PNG | 增强 JPG | appearance 描述更精确 → AI prompt 更准确 |

**关键不变量**：

1. `make_std_*() -> cq.Workplane` 签名不变 — 不管几何来自 SW Toolbox 还是 jinja_primitive
2. `MATERIAL_PRESETS[key]` 的 schema 不变 — 必须包含 `color`, `metallic`, `roughness`, `appearance`
3. `MATERIAL_PROPS[key]` 的 schema 不变 — 必须包含 `density`, `color`, `ra_default`, `material_type`
4. `ResolveResult` 的 kind 枚举不变 — SW Toolbox 产出的是 `step_import`，与 `StepPoolAdapter` 一致
5. 无 SW 时 → 输出与当前版本**字节等同**

### 5.2 Adapter 优先级链

```
StepPoolAdapter          ← 用户显式放置的 STEP（最高优先级）
  ↓ miss
BdWarehouseAdapter       ← 参数化硬件库（bd_warehouse）
  ↓ miss
SolidWorksToolboxAdapter ← SW Toolbox COM 导出（新增，中等优先级）
  ↓ miss / SW 未安装
PartCADAdapter           ← 包管理器（opt-in）
  ↓ miss / 未启用
JinjaPrimitiveAdapter    ← 简化几何兜底（永远命中）
```

SW Toolbox 位于 bd_warehouse **之后**，因为：
- bd_warehouse 是跨平台的参数化几何（轴承尺寸精确）
- SW Toolbox 需要 Windows + SW 安装，通用性低
- 用户不应因为装了 SW 就丢失 bd_warehouse 的跨平台一致性

但 SW Toolbox 在 jinja_primitive **之前**：
- 真实几何 > 简化几何
- 对于 bd_warehouse 不覆盖的零件（如 pin、rivet、seal），SW Toolbox 是显著升级

### 5.3 材质合并时序

```python
# 加载顺序（先加载的优先级高，不会被覆盖）

# Step 1: 手工定义（cad_spec_defaults.py 静态表）
MATERIAL_PROPS = { "7075-T6": {...}, "SUS304": {...}, ... }  # 11 种

# Step 2: SW 扩展（模块加载时自动执行）
_extend_material_props_from_sw()
# → 新增 sw_1023_carbon_steel, sw_201_stainless, ... （百余种，仅填充不存在的 key）

# Step 3: 项目 override（parts_library.yaml 中的 material_overrides 段，未来可选）
```

**命名冲突处理**：

| 场景 | 策略 |
|------|------|
| SW "304 Stainless Steel" vs 现有 "SUS304" | 建立等价映射表，SW 侧跳过已知等价材质 |
| SW "Plain Carbon Steel" vs 无对应 | 注册为 `sw_plain_carbon_steel` |
| SW 材质无 classification 名称 | 跳过，记入 warning log |

---

## 6. 降级策略 & 错误处理

| 场景 | 行为 |
|------|------|
| 非 Windows 平台 | `sw_detect` 立即返回 `installed=False`；全部 SW 代码短路 |
| SW 未安装 | 同上，`env-check` 输出提示信息 |
| SW 版本 < 2024 | 路径 A（材质读取）正常工作；路径 B（COM）禁用并提示 |
| pywin32 未安装 | 路径 A 正常；路径 B 禁用，`env-check` 提示 `pip install pywin32` |
| COM 启动失败 | `SolidWorksToolboxAdapter.is_available()` 返回 False，静默降级 |
| COM 转换单个零件失败 | 记 warning，该零件降级到下一个 adapter |
| sldmat XML 解析错误 | 记 warning，跳过该材质条目，不影响其他 |
| p2m 解析失败 | 回退到 classification 默认色 |
| Toolbox 目录不存在 | `sw_detect.toolbox_dir = None`，路径 B 跳过 |
| STEP 缓存磁盘满 | `synthesize_to_cache` 捕获 IOError，该零件降级 |

**核心原则**：所有 SW 相关失败都是 **warning 级别**，永远不阻断管道。

---

## 7. 目录结构

```
adapters/
├── parts/
│   ├── base.py                      # 现有
│   ├── step_pool_adapter.py         # 现有
│   ├── bd_warehouse_adapter.py      # 现有
│   ├── jinja_primitive_adapter.py   # 现有
│   ├── partcad_adapter.py           # 现有
│   ├── vendor_synthesizer.py        # 现有
│   └── sw_toolbox_adapter.py        # ★ 新增: Toolbox COM 适配器
│
└── solidworks/                      # ★ 新增: SW 专用模块
    ├── __init__.py
    ├── sw_detect.py                 # 安装检测
    ├── sw_material_bridge.py        # 材质桥接
    ├── sw_texture_resolver.py       # 贴图/外观解析
    └── sw_toolbox_catalog.py        # Toolbox 目录索引

~/.cad-spec-gen/                     # 用户本地缓存（不入 git）
├── step_cache/
│   ├── maxon/                       # 现有 vendor 缓存
│   └── sw_toolbox/                  # ★ 新增: Toolbox STEP 缓存
│       ├── GB/
│       │   ├── bolts/
│       │   ├── nuts/
│       │   ├── screws/
│       │   └── ...
│       ├── ISO/
│       └── DIN/
├── sw_toolbox_index.json            # ★ 新增: Toolbox 目录索引缓存
└── sw_materials_cache.json          # ★ 新增: 解析后的材质缓存
```

---

## 8. 实施分期

### Phase SW-A：检测 + 材质桥接（路径 A，纯脚本）

**预估工作量**：中等
**外部依赖**：无（stdlib only）

| 步骤 | 内容 | 验收标准 |
|------|------|---------|
| SW-A1 | `sw_detect.py` — 安装检测 | 在有/无 SW 的机器上正确报告状态 |
| SW-A2 | `sw_material_bridge.py` — sldmat 解析 | 正确解析 3 个 sldmat 文件的所有材质条目 |
| SW-A3 | `sw_texture_resolver.py` — p2m 解析 | 正确提取 diffuse color + roughness |
| SW-A4 | `cad_spec_defaults.py` 扩展 | `MATERIAL_PROPS` 运行时包含 SW 材质 |
| SW-A5 | `render_config.py` 扩展 | `MATERIAL_PRESETS` 运行时包含 SW 外观 |
| SW-A6 | `cad_pipeline.py env-check` | 报告 SW 安装状态 |
| SW-A7 | 单元测试 | sw_detect / sw_material_bridge / sw_texture_resolver 全覆盖 |

**交付物**：`MATERIAL_PROPS` 从 11 种扩展到 100+ 种（取决于 SW 安装的材质库），`MATERIAL_PRESETS` 同步增长。

### Phase SW-B：Toolbox Adapter（路径 B，COM 自动化）

**预估工作量**：较大
**外部依赖**：`pywin32`（可选依赖，不装也能跑管道）

| 步骤 | 内容 | 验收标准 |
|------|------|---------|
| SW-B1 | `sw_toolbox_catalog.py` — 目录扫描 | 生成 1818 个零件的索引 JSON |
| SW-B2 | `sw_toolbox_adapter.py` — Adapter 实现 | `is_available()` / `resolve()` / `probe_dims()` 通过 |
| SW-B3 | COM 自动化封装 | 单个 sldprt → STEP 转换成功 |
| SW-B4 | 缓存机制 | 二次 resolve 命中缓存，不触发 COM |
| SW-B5 | `parts_resolver.py` 注册 | `default_resolver()` 包含 SW adapter |
| SW-B6 | `parts_library.default.yaml` 规则 | GB/ISO/DIN 匹配规则覆盖主要品类 |
| SW-B7 | `cad_pipeline.py sw-warmup` | 批量预转换命令 |
| SW-B8 | 集成测试 | 端到端：BOM → resolve → STEP → build |
| SW-B9 | 覆盖率报告 | `solidworks_toolbox` 出现在报告中 |

**交付物**：管道覆盖率从 ~9%（仅 step_pool + bd_warehouse）提升到 ~40%+（加入 SW Toolbox GB/ISO/DIN 标准件）。

### Phase SW-C：polish + 文档

| 步骤 | 内容 |
|------|------|
| SW-C1 | `docs/SOLIDWORKS_INTEGRATION.md` 用户文档 |
| SW-C2 | coverage report 中增加 SW 提升统计 |
| SW-C3 | `env-check` 输出美化 |
| SW-C4 | pyproject.toml 增加 `[project.optional-dependencies] solidworks = ["pywin32>=306"]` |

---

## 9. 测试策略

### 9.1 无 SW 环境的 CI 兼容

CI 服务器通常不装 SolidWorks。测试策略：

- **`sw_detect` 测试**：mock `winreg` / `os.path.exists` → 测试各种安装场景
- **`sw_material_bridge` 测试**：在 `tests/fixtures/` 放一个最小化的 sldmat 样本（手写，不从 SW 复制 → 无版权）
- **`sw_toolbox_adapter` 测试**：mock COM 接口 → 测试 resolve 流程；实际 COM 转换标记 `@pytest.mark.requires_solidworks`
- **集成测试**：无 SW 时验证"字节等同"（输出与现版本完全一致）

### 9.2 测试矩阵

| 场景 | CI (Linux) | CI (Windows, no SW) | 开发机 (Win + SW) |
|------|-----------|-------------------|------------------|
| sw_detect 返回正确状态 | ✅ (installed=False) | ✅ (installed=False) | ✅ (installed=True) |
| 材质桥接（mock sldmat） | ✅ | ✅ | ✅ |
| 材质桥接（真实 sldmat） | skip | skip | ✅ |
| Toolbox adapter (mock) | ✅ | ✅ | ✅ |
| Toolbox adapter (COM) | skip | skip | ✅ |
| 管道无退化 | ✅ | ✅ | ✅ |

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| SW 版本间 sldmat 格式变化 | 解析失败 | 版本检测 + 宽松解析 + 降级策略 |
| p2m 格式闭源，变化不可预测 | PBR 参数不准 | p2m 解析为尽力模式，失败回退默认值 |
| COM 自动化启动 SW GUI（用户可见） | 用户体验差 | `swApp.Visible = False` + `swApp.UserControl = False` |
| 1818 个零件全量转换耗时长 | 首次运行慢 | 按需转换 + 缓存 + 可选预热命令 |
| pywin32 安装困难 | 路径 B 不可用 | 明确标为可选依赖，提供清晰提示 |
| Toolbox 零件名 → BOM 名匹配不准 | 选错零件 | 置信度阈值 + 降级到 jinja_primitive |
| SW 2024 版本号检测不准确（不确定注册表 key 的具体格式） | 漏检或误检 | 多路检测（注册表 + 文件系统 + COM），实施时实测验证 |

---

## 11. 开放问题

1. **SW 版本下限**：方案中暂定 ≥ 2024，但 sldmat XML 格式可能从更早版本就稳定。实施 Phase SW-A 时需要实际测试确定最低兼容版本。
2. **Toolbox 匹配精度**：BOM 中的"M6×20 内六角螺钉"如何精确匹配到 `GB/screws/socket head cap screw m6.sldprt`？需要在 Phase SW-B1 建索引时设计好 keyword 提取规则。
3. **SW 材质 ↔ 现有材质的等价映射表**：如 `"304 Stainless Steel"` ≈ `"SUS304"`。需要手工维护一个小型映射表（~20 条）。
4. **并发安全**：多个管道进程同时调用 COM 转换同一个 sldprt 时的文件锁问题 → 需要 file lock 或 atomic write。
