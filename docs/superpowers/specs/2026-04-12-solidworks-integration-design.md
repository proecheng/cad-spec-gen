# SolidWorks 可选集成设计规格

> 历史文档提示（2026-04-28）：当前执行依据已合并到 `docs/PARTS_LIBRARY.md`。
> 本文保留为 SW-A/SW-B 早期设计记录；若本文与 `docs/PARTS_LIBRARY.md`
> 冲突，以 `docs/PARTS_LIBRARY.md` 为准。当前命名：adapter key 为
> `sw_toolbox`，配置段为 `solidworks_toolbox`，类名为 `SwToolboxAdapter`。

> 日期: 2026-04-12
> 状态: 已审核（rev3 — 命名一致性 + 通用性 + 易用性）

## 1. 概述

将用户本机已安装的 SolidWorks 资产作为**可选增强层**接入 cad-spec-gen 管道：

- **有 SW** → 管道自动提取材质物理属性 + 渲染路由 + Toolbox 标准件几何
- **无 SW** → 管道行为与当前版本**字节等同**，env-check 中以正向表述提示可选安装
- **不帮助用户安装 SW**

### 1.1 非目标

- 不做 SW 参数化建模（只读不写）
- 不做 PDM Vault / 云端集成
- 不做 SW Assembly 约束解析
- 不在 git 仓库中存储任何 SW 资产
- 不扩展 `MATERIAL_PRESETS` 的 key 集合

### 1.2 分期交付

| 分期 | 内容 | 外部依赖 |
|------|------|---------|
| **SW-A** | 检测 + 材质桥接 + 函数化改造 + env-check 增强 | 无（stdlib only） |
| **SW-B** | Toolbox Configuration 索引 + COM adapter + 缓存 + 预热命令 | pywin32（可选） |
| **SW-C** | p2m 解析升级 + 文档 + polish | 无 |

---

## 2. 版权合规

代码仓库只包含 Python 调用代码，不包含任何 Dassault 版权内容。

| 行为 | 合规 | 依据 |
|------|------|------|
| `Dispatch("SldWorks.Application")` COM 调用 | ✅ | ProgID 是公开标识符，等同于 `"Excel.Application"` |
| 读用户本机 sldmat XML | ✅ | 等同于 IDE 读已安装 SDK 配置 |
| COM 导出用户 sldprt → STEP | ✅ | 等同于用户 GUI 操作 File → Save As |
| 产物写入 `~/.cad-spec-gen/` | ✅ | 用户本地缓存，不入 git |
| 仓库中存放 sldprt/sldmat/贴图/interop DLL | ❌ 禁止 | 不做 |
| 硬编码 SW 材质数据到源码 | ❌ 禁止 | 不做 |
| 测试 fixture | ✅ | 脚本生成的最小化 XML，不含 SW 原始数据 |

---

## 3. 系统架构

### 3.1 组件与目录结构

```
adapters/
├── parts/
│   ├── base.py                        # 现有
│   ├── step_pool_adapter.py           # 现有
│   ├── bd_warehouse_adapter.py        # 现有
│   ├── jinja_primitive_adapter.py     # 现有
│   ├── partcad_adapter.py             # 现有
│   ├── vendor_synthesizer.py          # 现有
│   └── sw_toolbox_adapter.py          # ★ 新增 (SW-B)
│
└── solidworks/                        # ★ 新增 (SW-A)
    ├── __init__.py
    ├── sw_detect.py                   # 安装检测
    ├── sw_material_bridge.py          # 材质桥接
    └── sw_toolbox_catalog.py          # Toolbox 目录索引 (SW-B)

~/.cad-spec-gen/                       # 用户本地缓存（不入 git）
├── step_cache/
│   └── sw_toolbox/                    # ★ 新增 (SW-B)
│       ├── GB/screws/socket_head_cap_M6x20.step
│       ├── GB/screws/socket_head_cap_M6x20.step.meta
│       └── ...
├── sw_toolbox_index.json              # ★ 新增 (SW-B)
└── sw_materials_cache.json            # ★ 新增 (SW-A)
```

### 3.2 依赖关系

```
sw_detect.py (零依赖: stdlib winreg + os)
    │
    ├── sw_material_bridge.py (依赖 sw_detect, xml.etree)
    │       │
    │       ├── cad_spec_defaults.get_material_type_keywords()  运行时合并（路由）
    │       └── cad_pipeline.get_material_preset_keywords()                  运行时合并（preset 路由）
    │
    └── sw_toolbox_adapter.py (依赖 sw_detect; pywin32 可选)
            │
            ├── sw_toolbox_catalog.py  索引构建 (依赖 pywin32)
            └── StepPoolAdapter        缓存的 STEP 复用其 BBox 逻辑
```

> **注**：当前代码中 `MATERIAL_PROPS` 字典虽有定义（11 种材质的 density/ra_default/color），但全项目无直接消费者（无 `MATERIAL_PROPS[key]` 调用）。SW-A 阶段不做 `MATERIAL_PROPS` 扩展——仅扩展关键词路由和 preset 路由。`MATERIAL_PROPS` 的 SW 扩展留到有实际消费场景时再做。

### 3.3 数据流（SW-A 交付后）

```
SW sldmat (UTF-16 XML)
    │
    ▼  parse
SwMaterialBundle
    ├─ type_keywords ──merge──→ get_material_type_keywords()
    │                              ↓
    │                     classify_material_type() [Phase 1/2]
    │                              ↓
    │                     ┌── 直接路径（英文 BOM）──→ get_material_preset_keywords() ──→ preset
    │                     └── 间接路径（中文 BOM）──→ material_type
    │                                                    ↓
    │                                          default_preset_for_material_type()
    │                                                    ↓
    │                                                  preset
    │
    └─ preset_keywords ─merge──→ get_material_preset_keywords()
                                    ↓
                           _sync_bom_to_render_config() [Phase 3]
                                    ↓
                           render_config.json
                             (preset key ∈ 现有 MATERIAL_PRESETS 15 种)
```

> **两条 preset 映射路径**：
> - **直接路径**：BOM 材质文本含英文关键词（如 `"1023 Carbon Steel"`）→ `get_material_preset_keywords()` 子串匹配 `"Carbon Steel"` → preset `"dark_steel"`
> - **间接路径**：BOM 材质文本含中文（如 `"7075-T6铝合金"`）→ `classify_material_type()` 匹配关键词 → material_type `"al"` → `default_preset_for_material_type("al")` → preset `"brushed_aluminum"`
>
> SW 扩展对中文 BOM 的主要价值在 `type_keywords`（让 `classify_material_type` 识别更多英文材质名），对英文 BOM 的价值在 `preset_keywords`（直接匹配）。

### 3.4 数据流（SW-B 交付后，叠加）

```
BOM part["name_cn"] + part["material"]
    │
    ▼  classify_part() → category
    ▼  SwToolboxAdapter.resolve(query, spec)
    │
    ├─ sw_toolbox_index.json 匹配 sldprt + Configuration
    ├─ STEP 缓存命中? → 返回 step_import
    └─ 缓存未命中 → SwComSession 导出 → 写缓存 → 返回 step_import
```

---

## 4. 详细设计

### 4.1 `sw_detect.py` — 安装检测

**数据结构**：

```python
@dataclass
class SwInfo:
    installed: bool
    version: Optional[str]          # "2024"
    version_year: Optional[int]     # 2024
    install_dir: Optional[Path]     # 从注册表动态获取
    sldmat_paths: list[Path]        # install_dir/lang/*/sldmaterials/*.sldmat（所有语言）
    textures_dir: Optional[Path]    # install_dir / data / Images / textures
    p2m_dir: Optional[Path]         # install_dir / data / graphics / Materials
    toolbox_dir: Optional[Path]     # 从注册表 Toolbox Data Location 动态获取
    com_available: bool
    pywin32_available: bool
```

**检测策略**（所有路径从注册表动态获取，不硬编码任何文件系统路径）：

1. 非 Windows → 立即返回 `SwInfo(installed=False, ...)`
2. **安装目录**：注册表双路查询，year 从 2030 降序到 2020，取最新命中：
   - `HKLM\SOFTWARE\SolidWorks\SolidWorks <year>\Setup\SolidWorks Folder`
   - `HKLM\SOFTWARE\SolidWorks\SOLIDWORKS <year>\Setup\SolidWorks Folder`
   - 两个 key 都不存在 → `installed=False`（不做文件系统猜测扫描）
3. **Toolbox 目录**：从同版本注册表读取：
   - `HKLM\SOFTWARE\SolidWorks\SolidWorks <year>\General\Toolbox Data Location`
   - 拼接 `\browser\` 子目录，验证该目录存在
   - 不存在 → `toolbox_dir=None`（路径 B 不可用，不阻断路径 A）
4. **资产路径**：全部从 `install_dir` 派生：
   - sldmat: `install_dir / lang / * / sldmaterials / *.sldmat`（glob 所有语言子目录，去重合并）
   - textures: `install_dir / data / Images / textures`
   - p2m: `install_dir / data / graphics / Materials`
   - 子目录不存在 → 对应列表/路径为空/None
5. **COM**：检查 `HKCR\SldWorks.Application\CLSID` 存在性
6. **pywin32**：`try: import win32com.client`

**版本语义**：

| version_year | 路径 A（材质） | 路径 B（Toolbox） |
|-------------|--------------|------------------|
| ≥ 2020 | ✅ | ❌ |
| ≥ 2024 | ✅ | ✅（需 pywin32） |
| < 2020 或 None | ❌ | ❌ |

**缓存**：进程级单例 `_cached_info`。`detect_solidworks()` 只执行一次。暴露 `_reset_cache()` 供测试。

### 4.2 `sw_material_bridge.py` — 材质桥接

**解析输入**：sldmat UTF-16 XML（基于实测结构）：

```xml
<classification name="Steel">
  <material name="1023 Carbon Steel Sheet (SS)" matid="82">
    <physicalproperties>
      <DENS value="7858.000032" />
      <KX value="52.000000" />
      ...
    </physicalproperties>
    <shaders>
      <pwshader2 path="\metal\steel\matte steel.p2m" name="matte steel" />
    </shaders>
  </material>
</classification>
```

**中间数据结构**：

```python
@dataclass
class SwMaterial:
    name: str               # "1023 Carbon Steel Sheet (SS)"
    classification: str     # "Steel"
    density_kg_m3: float    # 7858.0
    elastic_modulus: Optional[float]
    yield_strength: Optional[float]
    thermal_conductivity: Optional[float]
    shader_path: Optional[str]  # "\metal\steel\matte steel.p2m"
```

**两组输出**（SW-A 阶段仅做路由扩展，不做物理属性注入）：

```python
@dataclass
class SwMaterialBundle:
    type_keywords: dict[str, list[str]]
    # {"steel": ["Carbon Steel", "Stainless", ...], "al": ["Aluminum", ...]}
    # → 合并进 MATERIAL_TYPE_KEYWORDS
    # 让 classify_material_type() 识别 SW 英文材质名

    preset_keywords: dict[str, str]
    # {"Carbon Steel": "dark_steel", "Stainless Steel": "stainless_304", ...}
    # → 合并进 _MAT_PRESET
    # 值域 ⊂ MATERIAL_PRESETS.keys()
    # 主要服务于英文 BOM 场景
```

> **为什么没有 `props_by_name`**：当前代码中 `MATERIAL_PROPS` 虽然定义了 11 种材质的 density/ra_default，但全项目无 `MATERIAL_PROPS[key]` 直接消费者。`gen_parts.py` 的实际路径是 `classify_material_type()` → `SURFACE_RA[material_type]`，不读 `MATERIAL_PROPS`。因此 SW-A 只扩展路由（`type_keywords` + `preset_keywords`），物理属性注入留到有实际消费场景时再做。

**等价映射表**（~20 条，硬编码）：

```python
EQUIVALENCE_MAP = {
    "AISI 304": "SUS304", "304 Stainless Steel": "SUS304",
    "316L Stainless Steel": "SUS316L",
    "7075 Alloy": "7075-T6", "6061 Alloy": "6061-T6",
    ...
}
```

等价映射中的 SW 材质不创建新条目，只贡献关键词路由（让 `classify_material_type()` 和 `get_material_preset_keywords()` 能识别这些英文名）。

**classification → preset 映射**（SW-A 阶段）：

```python
SW_CLASSIFICATION_TO_PRESET = {
    "Steel": "dark_steel",
    "Iron": "dark_steel",
    "Aluminum Alloys": "brushed_aluminum",
    "Copper Alloys": "copper",
    "Titanium Alloys": "stainless_304",
    "Plastics": "white_nylon",
    "Rubber": "black_rubber",
    "Other Non-metals": "white_nylon",
}
```

SW-C 阶段升级：解析 p2m key-value 格式（`"col1" R G B`、`"roughness" float`）辅助更精准的 preset 选择。

**关键函数**：

```python
def load_sw_material_bundle() -> Optional[SwMaterialBundle]:
    """一键加载。SW 未安装或路径 A 版本不足时返回 None。
    内部使用模块级 _cached_bundle 缓存结果，多次调用只解析一次 sldmat。
    get_material_type_keywords() 和 get_material_preset_keywords() 都调用此函数，
    但不会触发重复 I/O。"""

def parse_sldmat(path: Path) -> list[SwMaterial]:
    """解析单个 sldmat 文件。内部使用，被 load_sw_material_bundle 调用。"""

def reset_all_sw_caches():
    """测试用统一入口：重置 bundle 缓存 + 所有下游合并缓存。"""
    # 重置 sw_material_bridge 内部 _cached_bundle
    # 重置 cad_spec_defaults._merged_keywords
    # 重置 cad_pipeline._preset_keywords_merged
```

### 4.3 现有模块函数化改造

**改造范围**：仅改造两个路由表（`MATERIAL_TYPE_KEYWORDS` 和 `_MAT_PRESET`）。`MATERIAL_PROPS` 和 `MATERIAL_PRESETS` 不改动。

**`cad_spec_defaults.py`**：

```python
# 静态字典保持不动
MATERIAL_PROPS = { "7075-T6": {...}, ... }           # 11 种，不改动
MATERIAL_TYPE_KEYWORDS = { "al": [...], ... }        # 5 个分类，作为基础层

# 新增延迟加载函数
_merged_keywords: Optional[dict] = None

def get_material_type_keywords() -> dict:
    """基础 + SW 扩展的关键词路由表。首次调用时合并，缓存结果。"""
    global _merged_keywords
    if _merged_keywords is not None:
        return _merged_keywords
    # 深拷贝基础层（list 值需要独立副本）
    _merged_keywords = {k: list(v) for k, v in MATERIAL_TYPE_KEYWORDS.items()}
    if sys.platform == "win32":
        try:
            from adapters.solidworks.sw_material_bridge import load_sw_material_bundle
            bundle = load_sw_material_bundle()
            if bundle:
                for mtype, kws in bundle.type_keywords.items():
                    if mtype in _merged_keywords:
                        # extend，不重复
                        existing = set(kw.lower() for kw in _merged_keywords[mtype])
                        for kw in kws:
                            if kw.lower() not in existing:
                                _merged_keywords[mtype].append(kw)
                    else:
                        _merged_keywords[mtype] = list(kws)
        except ImportError:
            pass
    return _merged_keywords

def _reset_material_cache():
    """测试用：重置本模块缓存。由统一入口 reset_all_sw_caches() 调用。"""
    global _merged_keywords
    _merged_keywords = None
```

`classify_material_type()` 内部改为调用 `get_material_type_keywords()` 替代直接引用 `MATERIAL_TYPE_KEYWORDS`。

**`cad_pipeline.py`**：

```python
_MAT_PRESET = {
    "铝": "brushed_aluminum", "Al": "brushed_aluminum",
    "钢": "stainless_304", "SUS": "stainless_304",
    "PEEK": "peek_amber",
    "橡胶": "black_rubber", "硅橡胶": "black_rubber",
    "塑料": "white_nylon", "尼龙": "white_nylon",
    "铜": "copper",
}

_preset_keywords_merged: Optional[dict] = None

def get_material_preset_keywords() -> dict:
    """基础 + SW 扩展的 preset 关键词路由。首次调用时合并，缓存结果。"""
    global _preset_keywords_merged
    if _preset_keywords_merged is not None:
        return _preset_keywords_merged
    _preset_keywords_merged = dict(_MAT_PRESET)
    if sys.platform == "win32":
        try:
            from adapters.solidworks.sw_material_bridge import load_sw_material_bundle
            bundle = load_sw_material_bundle()
            if bundle:
                for k, v in bundle.preset_keywords.items():
                    if k not in _preset_keywords_merged:
                        _preset_keywords_merged[k] = v
        except ImportError:
            pass
    return _preset_keywords_merged
```

**不改动的模块**：
- `render_config.py`：`MATERIAL_PRESETS` 保持静态字典
- `prompt_data_builder.py`：直接读 `MATERIAL_PRESETS`，不受影响
- `codegen/gen_parts.py`：调用 `classify_material_type()` + `SURFACE_RA`，不直接读 `MATERIAL_PROPS`

**消费方改动清单**：

| 文件 | 改动 |
|------|------|
| `cad_spec_defaults.py` | `classify_material_type()` 内部改用 `get_material_type_keywords()` |
| `cad_pipeline.py` | `_MAT_PRESET` 直接引用 → `get_material_preset_keywords()` 调用（~4 处） |
| `cad_spec_reviewer.py` | 若直接引用 `classify_material_type`，无需改动（函数内部已改） |
| 其他文件 | 不变 |

### 4.4 env-check 增强

在 `check_env.py` 的 `detect_environment()` 末尾新增 `enhancements` 字段：

```python
enhancements = {}
try:
    from adapters.solidworks.sw_detect import detect_solidworks
    sw = detect_solidworks()
    enhancements["solidworks"] = {
        "ok": sw.installed and (sw.version_year or 0) >= 2020,
        "version": sw.version,
        "path_a": (sw.version_year or 0) >= 2020,
        "path_b": (sw.version_year or 0) >= 2024 and sw.com_available,
        "pywin32": sw.pywin32_available,
        "materials": len(sw.sldmat_paths),
    }
except ImportError:
    enhancements["solidworks"] = {"ok": False}
result["enhancements"] = enhancements
```

**人类可读输出**（有 SW）：

```
  增强源（可选，不影响能力等级）
  ────────────────────────────────────────
  SolidWorks    [OK]    2024 — 材质 ✓ / Toolbox ✓ (pywin32 未安装)
  ────────────────────────────────────────
```

**人类可读输出**（无 SW）：

```
  增强源（可选，不影响能力等级）
  ────────────────────────────────────────
  SolidWorks    [  ]    未检测到安装
                        已有 SolidWorks 许可？安装后可自动集成材质库和标准件。
  ────────────────────────────────────────
```

**约束**：不改 level 计算、不改退出码约定、`try/except ImportError` 守住 "No dependencies" 约束。

### 4.5 `sw_toolbox_catalog.py` — Toolbox 目录索引（SW-B）

首次运行用 COM 枚举每个 sldprt 的 Configuration 列表，生成索引：

```json
{
  "sw_version": "2024",
  "toolbox_root": "<从注册表 Toolbox Data Location 动态获取>",
  "scan_time": "2026-04-12T15:00:00",
  "entries": [
    {
      "standard": "GB",
      "category": "screws",
      "subcategory": "socket head screws",
      "file": "hexagon socket head cap screws gb.sldprt",
      "rel_path": "browser/GB/screws/socket head screws/hexagon socket head cap screws gb.sldprt",
      "configurations": ["M3-8", "M3-10", "...", "M24-100"],
      "gb_standard": "GB/T 70.1",
      "keywords_en": ["hexagon socket head cap screw", "hex socket"]
    }
  ]
}
```

- 缓存于 `~/.cad-spec-gen/sw_toolbox_index.json`
- `rel_path` 相对于 `toolbox_root`，运行时拼接为绝对路径（不存储硬编码绝对路径）
- SW 版本变化或 `toolbox_root` 变化时自动重建

### 4.6 `sw_toolbox_adapter.py` — Toolbox Adapter（SW-B）

```python
class SwToolboxAdapter(PartsAdapter):
    name = "sw_toolbox"
```

**`is_available()`**：`sw_detect.version_year >= 2024` AND `pywin32_available` AND `toolbox_dir` 存在。

**`resolve(query, spec)`**：

1. 在 `sw_toolbox_index.json` 中匹配 sldprt + Configuration
2. STEP 缓存命中 → 返回 `ResolveResult(kind="step_import")`
3. 缓存未命中 → `SwComSession` 导出 → 写缓存 + `.meta` → 返回 `step_import`
4. 匹配失败或导出失败 → 返回 `ResolveResult.miss()`

**`probe_dims(query, spec)`**：缓存命中 → 读 STEP BBox；未命中 → 返回 None（不为 probe 启动 COM）。

**两级匹配算法**（SW-B 阶段仅英文匹配，中文对照推迟到 SW-C 作为可配置映射文件）：

| 优先级 | 方法 | 示例 |
|--------|------|------|
| 1 | GB/ISO/DIN 标准号精确匹配 | BOM 含 `"GB/T 70.1"` → 索引中 `gb_standard == "GB/T 70.1"` |
| 2 | 分类 + 英文关键词子串匹配 | `category=fastener` + `"socket head cap"` ∈ `keywords_en` |

> SW-C 阶段可增加 `keywords_cn` 字段。中文关键词来源为**可配置的外部映射文件**（如 `catalogs/sw_toolbox_cn.yaml`），不硬编码在代码中。该文件为社区可贡献的翻译资源。

**Configuration 匹配**：从 BOM 文本提取 M-尺寸-长度（如 `"M6×20"` → 匹配 `"M6-20"`）。匹配失败时返回 None → miss → 降级。不用默认 Configuration。

**`SwComSession` 上下文管理器**：

- `__enter__`：启动 SW（`Visible=False`, `UserControl=False`）
- 批量转换复用同一 session
- 单零件超时 30 秒
- `__exit__`：关闭文档 + `ExitApp()`
- `atexit` 注册 cleanup

**Adapter 优先级**：

```
StepPoolAdapter → BdWarehouseAdapter → SwToolboxAdapter → PartCADAdapter → JinjaPrimitiveAdapter
```

**预热命令**：

```bash
python cad_pipeline.py sw-warmup --standard GB
python cad_pipeline.py sw-warmup --standard GB --category screws
python cad_pipeline.py sw-warmup --dry-run
```

**首次运行体验**：
- 逐件进度输出：`[sw_toolbox] 导出 GB/screws/socket_head_cap_M6x20 (3/15)...`
- `--no-sw-toolbox` CLI flag 跳过 COM 转换

---

## 5. 数据一致性保证

### 5.1 跨环境一致性

**核心规则**：`render_config.json` 中引用的 preset key 必须属于 `MATERIAL_PRESETS` 的静态 15 种 key。SW 路由扩展只扩展触发条件（关键词），不扩展目标值（preset key）。

| 环境 | `get_material_type_keywords()` | `get_material_preset_keywords()` | `MATERIAL_PRESETS` |
|------|-------------------------------|---------------------|--------------------|
| Windows + SW | 基础 5 类 + SW 英文关键词 | 基础 7 + SW 英文关键词 | 静态 15（不变） |
| Windows 无 SW | 基础 5 类 | 基础 7 | 静态 15 |
| Linux / macOS | 基础 5 类 | 基础 7 | 静态 15 |

**结果**：`render_config.json` 产出的 preset key 值域始终 ⊂ `MATERIAL_PRESETS` 静态 15 种，在所有环境下可解析。SW 扩展只拓宽了关键词匹配范围，不影响输出值域。

### 5.2 等价映射一致性

`EQUIVALENCE_MAP` 中的 SW 材质（如 `"304 Stainless Steel"` ≈ `"SUS304"`）只贡献关键词路由，不创建新的材质条目，避免同一材质出现两个名称。

### 5.3 Toolbox 缓存版本一致性

每个 STEP 旁的 `.meta` 文件记录：

```json
{
  "sw_version": "2024",
  "source_sldprt": "...",
  "configuration": "M6-20",
  "exported_at": "2026-04-12T15:30:00",
  "bbox_mm": [10.0, 10.0, 20.0]
}
```

`sw_detect` 检测到版本变化时 env-check 提示 `sw-warmup --rebuild`。

### 5.4 无 SW 字节等同保证

延迟加载函数模式保证：
- 无 SW 环境下 `get_material_type_keywords()` 返回值 == 原 `MATERIAL_TYPE_KEYWORDS`
- 无 SW 环境下 `get_material_preset_keywords()` 返回值 == 原 `_MAT_PRESET`
- `MATERIAL_PROPS` 和 `MATERIAL_PRESETS` 完全不改动
- 管道输出字节等同

---

## 6. 降级策略

所有 SW 相关失败都是 **warning 级别，永不阻断管道**。

| 场景 | 路径 A | 路径 B | 行为 |
|------|--------|--------|------|
| 非 Windows | 短路 | 短路 | 字节等同 |
| Windows 无 SW | 短路 | 短路 | env-check 正向提示 |
| SW < 2020 | 不启用 | 不启用 | env-check 提示版本过低 |
| SW 2020~2023 | ✅ | 不启用 | env-check 显示"材质 ✓ / Toolbox ✗ (需 ≥2024)" |
| SW ≥ 2024 无 pywin32 | ✅ | 不启用 | env-check 提示 `pip install pywin32` |
| SW ≥ 2024 有 pywin32 | ✅ | ✅ | 全功能 |
| sldmat 单条解析失败 | 跳过该条目，warning | — | 其他材质正常 |
| COM 启动失败 | — | `is_available()=False` | 静默降级 |
| COM 单零件导出失败 | — | 返回 miss，warning | 降级到下一 adapter |
| COM 超时 30 秒 | — | kill，miss | 降级 |
| 许可证被占用 | — | COM 失败，warning 说明疑似许可证 | 降级 |
| 缓存磁盘满 | — | IOError 捕获，miss | 降级 |
| SW 版本升级后缓存陈旧 | — | env-check 提示 `sw-warmup --rebuild` | 不自动删除 |

---

## 7. 测试策略

### 7.1 测试矩阵

| 测试 | CI (Linux) | CI (Win, no SW) | 开发机 (Win+SW) |
|------|-----------|----------------|-----------------|
| `sw_detect` mock 场景 | ✅ | ✅ | ✅ |
| `sw_material_bridge` 生成 fixture | ✅ | ✅ | ✅ |
| `sw_material_bridge` 真实 sldmat | skip | skip | ✅ |
| `get_material_type_keywords()` 无 SW 等同 | ✅ | ✅ | ✅ |
| `get_material_preset_keywords()` 无 SW 等同 | ✅ | ✅ | ✅ |
| `sw_toolbox_catalog` mock 目录 | ✅ | ✅ | ✅ |
| `sw_toolbox_adapter` mock COM | ✅ | ✅ | ✅ |
| Configuration 匹配纯单元 | ✅ | ✅ | ✅ |
| COM 实际转换 | skip | skip | ✅ (`@requires_solidworks`) |
| 端到端无退化 | ✅ | ✅ | ✅ |
| env-check `enhancements` 字段 | ✅ | ✅ | ✅ |

### 7.2 Fixture 策略

测试用 sldmat 由 Python 脚本**生成**（构造 `ElementTree` + UTF-16 编码写出），不手写 XML，不含 SW 原始数据。

```python
# tests/fixtures/generate_sldmat_fixture.py
def generate_minimal_sldmat(out_path: Path):
    """构造最小化 sldmat 用于测试。"""
    root = ET.Element("{http://www.solidworks.com/sldmaterials}materials")
    cls = ET.SubElement(root, "classification", name="Steel")
    mat = ET.SubElement(cls, "material", name="Test Steel 1000", matid="1")
    props = ET.SubElement(mat, "physicalproperties")
    ET.SubElement(props, "DENS", value="7850.0")
    ET.SubElement(props, "KX", value="50.0")
    tree = ET.ElementTree(root)
    with open(out_path, "wb") as f:
        f.write(b'\xff\xfe')  # UTF-16 LE BOM
        tree.write(f, encoding="utf-16-le", xml_declaration=False)
```

---

## 8. 关键设计决策记录

| # | 决策 | 选项 | 理由 |
|---|------|------|------|
| Q1 | Toolbox 粒度 | 完整 Configuration 匹配 | 尺寸不对的几何不如简化圆柱 |
| Q2 | 材质注入机制 | 函数化 `get_*()` | 显式控制流，无隐式副作用 |
| Q3 | 跨环境一致性 | preset key 不扩展 | render_config.json 在所有环境可解析 |
| Q4 | 交付节奏 | 先 SW-A 再 SW-B | 纯脚本先验证架构 |
| Q5 | p2m 解析深度 | SW-A 用 classification，SW-C 升级 | 先粗后精 |
| Q6 | MATERIAL_PROPS 范围 | 路由全量，MATERIAL_PROPS 不改动 | 当前代码无直接消费者 |
| Q7 | 版本下限 | 路径 A ≥2020，路径 B ≥2024 | 材质 XML 格式稳定，COM API 变化大 |
| — | 架构组织 | 方案 1：独立子系统 | 删目录即可回退 |
| — | 路径发现 | 全部从注册表动态获取，不硬编码 | 用户 SW 安装路径不可预测 |
