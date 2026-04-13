# Phase SW-B — SolidWorks Toolbox COM Adapter 设计规格

> 版本: v2.0 — 2026-04-13（五角色联审修订版）
> 状态: 待实施
> 前置: Phase SW-A 已完成（`sw_detect.py` / `sw_material_bridge.py` 已合入 main）
> 参考: `docs/design/solidworks-integration-plan.md` §4.4、§5、§8、§11

---

## 1. 目标与范围

### 1.1 目标

将 SolidWorks Toolbox 中的 1818 个标准件（GB/ISO/DIN）接入 `cad-spec-gen` 的 `PartsResolver` 体系，通过 COM 自动化按需把 sldprt 转换为 STEP 文件，作为现有 `bd_warehouse` / `step_pool` 之外的**可选增强 adapter**。

### 1.2 覆盖率量化指标（可度量）

**覆盖率定义**：对给定 BOM 文件，
```
coverage = (命中非 jinja_primitive adapter 的 BOM 行数) / (总 BOM 行数)
```

**验收基准**：通过 §9.4 扩充的 `demo_bom.csv`（≥ 15 行，涵盖 GB 紧固件 / GB 轴承 / ISO 紧固件 / 非标件）做 regression：
- Phase SW-A 完工时基线（无 SW Toolbox）：实施 SW-B1 前先跑一次记录
- Phase SW-B 交付时目标：新增至少 8 行从 jinja_primitive 迁移到 `solidworks_toolbox`
- 量化交付报告在 coverage_report 里显示 adapter 分布

**无 SW 时**：输出与 Phase SW-A 完工时**字节等同**（不可退化）。

### 1.3 非目标（严格范围）

- **只支持公制 M 螺纹** — Phase SW-B 不处理 UNC/UNF（英制）、Tr（梯形）、G/Rp（管螺纹）、NPT 等。这些 BOM 行直接 miss 降级
- **不做 configuration 自动选择** — 所有 sldprt 导出使用**其保存时激活的 configuration**（通常是默认号）。size 字段从 BOM 抽取仅用于 token 打分 + 覆盖率报告 + warning，**不**调 SetConfiguration
- **STEP 不继承 SW appearance/decal** — Toolbox 零件走渲染链时，材质推断仅靠 BOM `material` 字段 + 管道既有 PBR preset 体系（与非 SW 用户体验一致）。Phase SW-A 的 sldmat 桥接**不作用于 Toolbox 零件**
- **轴承后缀丢失是已知限制** — `6205-2RS` / `6205-ZZ-C3` / `6205/P6` 仍会命中同一个 `deep groove ball bearing.sldprt`；密封/精度/游隙后缀不在 Toolbox 几何中体现
- 不做 SolidWorks 的参数化写入（只读）
- 不在 git 仓库中包含任何 SW 资产
- 不解决 SW Toolbox 之外的 sldprt 转换
- 不做 PDM Vault 集成

---

## 2. 关键设计决策

| # | 决策点 | 选择 |
|---|--------|------|
| 1 | COM 启动策略 | **A+B 混合** — 默认按需启动，另提供 `sw-warmup` 批量预热 |
| 2 | Toolbox 索引生成时机 | **首次 `resolve()` 透明扫描** + `sw_toolbox_index.json` 缓存 |
| 3 | BOM → sldprt 匹配算法 | **YAML 粗分类 + adapter token overlap 精定位**，`min_score` 默认 0.30 |
| 4 | BOM 尺寸规格提取 | **正则抽取 + 缺省键** — 正则规则放 yaml `size_patterns` 可覆盖 |
| 5 | SW Toolbox 在 resolver 链中的优先级 | **GB 高优先级**（厂商 STEP 之后）；ISO/DIN 作为 bd_warehouse 专项之后的兜底 |
| 6 | COM 错误处理策略 | **宽松降级 + 连续 3 次失败熔断** — 熔断计数在**单进程生命周期**内累计；`reset_session()` 可清零 |
| 7 | 测试分层策略 | **三层分离** — 单元（mock COM）+ fake fixture 扫描 + 端到端（mocked + `@requires_solidworks`） |
| 8 | `sw-warmup` 命令接口 | `--standard` / `--bom` / `--all` / `--dry-run` / `--overwrite` |
| **9** | **尺寸抽取失败的处理** | **返回 miss 降级**（NOT 用默认 configuration）—— 避免几何与 BOM 规格不符导致装配验证误报 |
| **10** | **COM 冷启动 vs 单零件超时** | **分开计时**：首次 `get_session()` 冷启动超时 90s；启动后单零件转换超时 30s |
| **11** | **SW 进程内存管理** | **session 周期重启** — 每转换 N=50 个零件强制 shutdown 后重开，避免长批量时 OOM |
| **12** | **Token 权重** | `part_no` 在 query_tokens 中权重 2.0，`name_cn` 权重 1.0，`material` 权重 0.5 — 标准号是最高权重信号 |
| **13** | **Toolbox Add-In 启用检查** | `sw_detect` 新增 `toolbox_addin_enabled` 字段；`is_available()` 强制检查此字段；未启用时 env-check 给出明确指引 |

---

## 3. 架构总览

### 3.1 数据流（resolver 链）

```
BOM row (part_no / name_cn / material)
    │
    ▼
PartsResolver.resolve()  ── 按 parts_library YAML mappings first-hit-wins
    │
    ├──► 厂商 STEP (Maxon/LEMO/ATI)
    ├──► SolidWorksToolboxAdapter (GB 标准件)
    ├──► bd_warehouse 专用轴承/紧固件 (class 专项)
    ├──► SolidWorksToolboxAdapter (ISO/DIN 兜底)
    ├──► bd_warehouse 通用 fastener/bearing
    └──► jinja_primitive (永远命中的兜底)
```

### 3.2 `SolidWorksToolboxAdapter.resolve()` 内部流程

```
1. Toolbox 索引加载
   ├─ 索引缓存文件不存在 → sw_toolbox_catalog.build_toolbox_index() 扫描
   ├─ 缓存 schema_version 不匹配当前 SCHEMA_VERSION → 重建
   ├─ 缓存 mtime 早于 toolbox_dir mtime → 重建
   └─ 否则读缓存 JSON

2. YAML spec 限定候选子目录白名单
   ├─ spec.standard = "GB" 或 [ISO, DIN]
   └─ spec.subcategories = ["bolts and studs", "nuts", ...]

3. 从 BOM name_cn 正则抽尺寸（仅用于打分/报告，不调 SetConfiguration）
   ├─ fastener → {size: "M6", length: 20}
   ├─ bearing  → {model: "6205"}
   ├─ 抽到非 M 开头螺纹（如 UNC、Tr、G）→ 返回 miss（范围外）
   └─ 抽不到任何 size 字段 → 返回 miss（决策 #9）

4. 构造加权 query_tokens（决策 #12）
   ├─ part_no  tokens × 权重 2.0
   ├─ name_cn  tokens × 权重 1.0
   ├─ material tokens × 权重 0.5
   └─ 抽到的 size/length 作为额外 tokens × 权重 1.5

5. 候选 sldprt 做加权 token overlap 打分
   ├─ score = Σ(命中 token 的权重) / Σ(query token 总权重)
   └─ 取最高分 sldprt

6. 置信度 ≥ min_score (0.30) 才继续；否则返回 miss

7. 构造目标 STEP 路径
   └─ ~/.cad-spec-gen/step_cache/sw_toolbox/<standard>/<sub>/<name>.step

8. 缓存命中 → 返回 ResolveResult(kind="step_import")
   └─ probe_bbox() 从 STEP 计算真实尺寸

9. 缓存未命中 → COM 转换
   ├─ sw_com_session.convert_sldprt_to_step()
   │   ├─ 首次调用 → session 冷启动（超时 90s，决策 #10）
   │   ├─ 单零件转换超时 30s（决策 #10）
   │   ├─ 每转换 50 个后 shutdown+restart（决策 #11）
   │   └─ 显式传 units=mm + AP214
   └─ 失败 → 失败计数 +1（达 3 次触发熔断）→ 返回 miss

10. 任何异常 → warning + 返回 miss（绝不 raise）
```

---

## 4. 组件分解

### 4.1 新增文件

| 路径 | 职责 | 规模 |
|------|------|------|
| `adapters/solidworks/sw_toolbox_catalog.py` | 扫描 Toolbox 目录树（仅 `*.sldprt`）+ 生成/读取索引 JSON + 索引 schema_version 校验 + token 提取 + 尺寸正则匹配 + 加权 token overlap 评分 | ~300 行 |
| `adapters/solidworks/sw_com_session.py` | COM 会话管理：冷启动超时 90s + 单零件 30s + 熔断器（连续 3 次失败）+ 空闲超时 5 分钟自动释放 + 每 50 次转换周期重启 + Toolbox Add-In 激活 | ~250 行 |
| `adapters/parts/sw_toolbox_adapter.py` | `SolidWorksToolboxAdapter` 实现 `PartsAdapter`；熔断状态委托给 `SwComSession` | ~300 行 |
| `tests/fixtures/fake_toolbox/` | 伪造 Toolbox 目录（GB/ISO/DIN + 混入 `.xls`/`.slddrw` 验证过滤） | ~15 文件 |
| `tests/fixtures/demo_bom.csv` | 端到端验收 BOM（≥ 15 行，覆盖率 regression baseline） | ~15 行 |
| `tests/test_sw_toolbox_catalog.py` | catalog 单元测试（scan + match + 正则 + schema_version） | ~250 行 |
| `tests/test_sw_toolbox_adapter.py` | adapter 单元测试（mock win32com） | ~300 行 |
| `tests/test_sw_toolbox_integration.py` | 端到端 + 覆盖率 regression | ~200 行 |

### 4.2 改动文件

| 路径 | 改动 | 规模 |
|------|------|------|
| `adapters/solidworks/sw_detect.py` | 新增 `toolbox_addin_enabled` 字段 + 检测逻辑（从 `HKCU\Software\SolidWorks\AddInsStartup` 注册表读） | +30 行 |
| `parts_resolver.py` | `default_resolver()` 注册 SW Toolbox adapter | +10 行 |
| `parts_library.default.yaml` | 增加 `solidworks_toolbox` 配置段 + 规则 + `size_patterns` + `token_weights` + COM 超时/周期重启参数 | +80 行 |
| `cad_pipeline.py` | `cmd_sw_warmup()` + `sw-warmup` 子命令 + env-check 的 Toolbox 索引 & Add-In 状态报告 + coverage report 增强 | +150 行 |
| `pyproject.toml` | `[project.optional-dependencies] solidworks = ["pywin32>=306"]` + `requires_solidworks` marker 声明 | +5 行 |

---

## 5. 接口契约

### 5.1 `sw_toolbox_catalog.py`

```python
SCHEMA_VERSION = 1   # 每次索引结构变更必须 bump；旧缓存自动重建

@dataclass
class ToolboxPart:
    standard: str           # "GB" / "ISO" / "DIN"
    subcategory: str        # "bolts and studs" / "nuts" / ...
    sldprt_path: str        # 绝对路径
    filename: str           # "hex bolt.sldprt"
    tokens: list[str]       # 拆分 + 小写 + 去除通用词（如 "and"/"for"）后的 token 列表

# 扫描时过滤规则：
#   仅接受后缀 ".sldprt"，显式排除 ".xls"、".slddrw"、".sldlfp"、".xml"

def build_toolbox_index(toolbox_dir: Path) -> dict:
    """扫描 → 返回:
    {
      "schema_version": 1,
      "scan_time": "2026-04-13T...",
      "standards": {"GB": {"bolts and studs": [ToolboxPart, ...], ...}, ...}
    }
    """

def load_toolbox_index(cache_path: Path, toolbox_dir: Path) -> dict:
    """读缓存；以下情况重建：
    1. 缓存文件不存在
    2. cache["schema_version"] != SCHEMA_VERSION
    3. cache mtime < toolbox_dir mtime
    """

def match_toolbox_part(
    index: dict,
    query_tokens_weighted: list[tuple[str, float]],   # [(token, weight), ...]
    standards: list[str],
    subcategories: list[str],
    min_score: float = 0.30,
) -> Optional[tuple[ToolboxPart, float]]:
    """加权 token overlap。返回 (part, normalized_score) 或 None（低于 min_score）。"""

def extract_size_from_name(name_cn: str, patterns: dict) -> Optional[dict]:
    """正则抽尺寸。
    返回:
      - 成功抽到任何字段: {size: "M6", length: 20}（缺失字段不在 dict 中）
      - 检测到非 M 公制螺纹（如 UNC/Tr/G）: None （明确范围外）
      - 什么都没抽到: None  （与"范围外"并列）
    调用方看到 None 就走 miss（决策 #9、§1.3）。
    """

def build_query_tokens_weighted(
    query: "PartQuery",
    size_dict: dict,
    weights: dict,   # {"part_no": 2.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}
) -> list[tuple[str, float]]:
    """构造加权 query tokens。"""

def tokenize(text: str, stop_words: set = STOP_WORDS) -> list[str]:
    """拆分：大小写边界、下划线、空格、连字符、中英文边界 → 小写 token。
    STOP_WORDS = {"and", "for", "with", "the", "of", "type"}  # 避免子目录 "bolts and studs" 把 "and" 污染打分
    """
```

### 5.2 `sw_com_session.py`

```python
COLD_START_TIMEOUT_SEC = 90          # 决策 #10
SINGLE_CONVERT_TIMEOUT_SEC = 30      # 决策 #10
IDLE_SHUTDOWN_SEC = 300              # 空闲超时
RESTART_EVERY_N_CONVERTS = 50        # 决策 #11
CIRCUIT_BREAKER_THRESHOLD = 3        # 决策 #6

class SwComSession:
    """COM session 唯一 source of truth。熔断状态、session 生命周期、
    Toolbox Add-In 激活都归此类。

    冷启动与单零件转换分开计时（决策 #10）：
      - 首次 get_session() 中的 Dispatch("SldWorks.Application") + Add-In 激活：90s
      - 后续每次 convert_sldprt_to_step(): 30s

    每转换 RESTART_EVERY_N_CONVERTS 个零件强制 shutdown + restart（决策 #11），
    规避 SW 进程内存泄漏。
    """

    def __init__(self) -> None:
        self._app = None                    # win32com Dispatch object
        self._convert_count = 0
        self._consecutive_failures = 0      # 熔断计数
        self._unhealthy = False
        self._last_used_ts = 0.0

    def start(self) -> None:
        """冷启动：
        1. win32com.client.Dispatch("SldWorks.Application")（超时 90s）
        2. swApp.Visible = False, UserControl = False
        3. 激活 Toolbox Add-In: swApp.LoadAddIn("SOLIDWORKS Toolbox")
           - 若 sw_detect.toolbox_addin_enabled=False，提前 raise 带指引的异常
        4. 任何步骤失败 → self._unhealthy = True，抛异常
        """

    def convert_sldprt_to_step(
        self,
        sldprt_path: str,
        step_out: str,
    ) -> bool:
        """转换单个 sldprt 为 STEP（AP214，mm 单位）。
        签名不含 configuration 参数（Phase SW-B 不调 SetConfiguration，决策 §1.3）。

        超时 30s，失败返回 False + warning。
        连续 3 次失败触发熔断（self._unhealthy=True）。
        每 50 个成功转换后触发 session restart。

        STEP 导出具体 COM 调用：
            swApp.OpenDoc6(sldprt_path,
                           swDocPART=1,
                           swOpenDocOptions_Silent=1,
                           configuration="",
                           errors, warnings)
            model.Extension.SaveAs3(
                step_out,
                version=0,     # 0 = current
                options=swSaveAsOptions_Silent,
                exportData=...  # AP214 + mm
                errors, warnings
            )
            swApp.CloseDoc(title)
        """

    def is_healthy(self) -> bool:
        """熔断状态查询 —— adapter.is_available() 委托此方法（决策 §5.3）。"""

    def shutdown(self) -> None: ...
    def _maybe_restart(self) -> None:
        """如 self._convert_count >= RESTART_EVERY_N_CONVERTS，shutdown + start。"""

_SESSION_SINGLETON: Optional[SwComSession] = None
def get_session() -> SwComSession: ...
def reset_session() -> None:
    """测试用 + 外部主动清熔断。清空 singleton + convert_count + failures。"""
```

### 5.3 `sw_toolbox_adapter.py`

```python
class SolidWorksToolboxAdapter(PartsAdapter):
    name = "solidworks_toolbox"

    def __init__(self, project_root: str = "", config: Optional[dict] = None):
        """config 来自 parts_library.yaml 的 solidworks_toolbox 段。"""

    def is_available(self) -> bool:
        """全部命中才 True：
        1. sw_detect.installed
        2. sw_detect.version_year >= 2024
        3. sw_detect.pywin32_available
        4. sw_detect.toolbox_dir 存在
        5. sw_detect.toolbox_addin_enabled  （决策 #13）
        6. sw_com_session.get_session().is_healthy()  （熔断委托）
        """

    def can_resolve(self, query) -> bool:
        """总是 True（具体匹配由 resolve 决定）"""

    def resolve(self, query, spec) -> ResolveResult:
        """主编排流程（见 §3.2）"""

    def probe_dims(self, query, spec) -> Optional[tuple]:
        """
        缓存命中：读 STEP bbox 返回 (w, d, h)
        缓存未命中：返回 None（不触发 COM 启动）

        ⚠️ 已知限制（§1.3）：首次运行项目且未 sw-warmup 时，Phase 1
        envelope backfill 在 Toolbox 零件上退化。用户可跑 sw-warmup 预热
        再跑管道获得完整 envelope。
        """

    def _find_sldprt(self, query, spec) -> Optional[tuple[ToolboxPart, float]]:
        """匹配逻辑独立方法，供 sw-warmup --bom 复用，不触发 COM。"""
```

### 5.4 `sw_detect.py` 增量（决策 #13）

```python
@dataclass
class SwInfo:
    # ... 既有字段 ...
    toolbox_addin_enabled: bool = False   # ★ 新增

def _check_toolbox_addin_enabled(winreg, version_year: int) -> bool:
    """检查 Toolbox Add-In 启用状态。
    路径: HKCU\\Software\\SolidWorks\\AddInsStartup\\{GUID}
           其中 GUID 为 Toolbox CLSID。
    值为 1 表示启用。
    任何失败（未启用、路径缺失、权限）返回 False。
    """
```

`env-check` 输出增强：
```
SolidWorks 2024: ✅ 已检测到
  材质库: 3 个 sldmat 文件
  Toolbox: C:\SOLIDWORKS Data\browser\
  Toolbox Add-In: ⚠️  未启用，请在 SW 菜单 Tools → Add-Ins 里勾选
                    "SOLIDWORKS Toolbox Library"，然后重启 SW 生效
  COM: ✅
  pywin32: ✅
  Toolbox 索引: 1818 个零件（上次扫描: 2026-04-13）
```

---

## 6. YAML 配置结构

```yaml
solidworks_toolbox:
  enabled: auto
  standards: [GB, ISO, DIN]
  cache: ~/.cad-spec-gen/step_cache/sw_toolbox/
  min_score: 0.30

  # 加权 token overlap（决策 #12）
  token_weights:
    part_no:  2.0       # 标准号最高权重
    name_cn:  1.0
    material: 0.5
    size:     1.5       # 从 name_cn 抽出的 M6/6205 等

  # 尺寸正则（仅公制 M 螺纹和基本轴承，决策 §1.3）
  size_patterns:
    fastener:
      size:   '[Mm](\d+(?:\.\d+)?)'
      length: '[×xX*\-\s](\d+(?:\.\d+)?)'
      # 显式排除标记：如抽到 UNC/UNF/Tr/G 前缀则返回 None
      exclude_patterns: ['UN[CFEF]', '\bTr\d', '\bG\d/', '\bNPT']
    bearing:
      model:  '\b(\d{4,5})\b'

  # COM 超时/重启（决策 #10、#11，可覆盖）
  com:
    cold_start_timeout_sec: 90
    single_convert_timeout_sec: 30
    restart_every_n_converts: 50
    idle_shutdown_sec: 300

mappings:
  # [现有] 厂商 STEP
  # ...

  # ★ SW Toolbox GB 高优先级
  - match:
      category: fastener
      keyword_contains: ["GB/T", "国标", "GB "]
    adapter: solidworks_toolbox
    spec:
      standard: GB
      subcategories: ["bolts and studs", "nuts", "screws",
                      "washers and rings", "pins", "rivets"]
      part_category: fastener

  - match:
      category: bearing
      keyword_contains: ["GB/T", "国标", "深沟球", "圆柱滚子", "推力"]
    adapter: solidworks_toolbox
    spec:
      standard: GB
      subcategories: ["bearing"]
      part_category: bearing

  # [现有] bd_warehouse 专项

  # ★ SW Toolbox ISO/DIN 兜底
  - match:
      category: fastener
    adapter: solidworks_toolbox
    spec:
      standard: [ISO, DIN]
      subcategories: ["bolts", "nuts", "screws", "washers"]
      part_category: fastener

  - match:
      category: bearing
    adapter: solidworks_toolbox
    spec:
      standard: [ISO, DIN]
      subcategories: ["bearings"]
      part_category: bearing

  # [现有] bd_warehouse 通用兜底 + jinja_primitive
```

---

## 7. `sw-warmup` 命令接口

```bash
cad_pipeline.py sw-warmup                          # 默认 --standard GB
cad_pipeline.py sw-warmup --standard GB,ISO
cad_pipeline.py sw-warmup --bom subsystem/claw/bom.csv
cad_pipeline.py sw-warmup --all                    # 需显式 --all，1818 个
cad_pipeline.py sw-warmup --standard GB --dry-run
cad_pipeline.py sw-warmup --standard GB --overwrite
```

**BOM schema 约定**（sw-warmup 读取 BOM 时必需字段）：
- 必需列：`part_no`, `name_cn`, `material`, `category`（与 `PartQuery` 字段对齐）
- 可选列：`make_buy`
- 大小写不敏感的列名匹配；`部件号/名称/材料/类别` 等中文列名也接受（通过 header 别名表）

**核心流程**：
```python
def cmd_sw_warmup(args):
    # 1) 检查前置: sw_detect.installed + version_year≥2024
    #              + pywin32_available + toolbox_addin_enabled
    #    任一失败 → exit 1 + 清晰指引（区分是 SW 未装/Add-In 未启用/pywin32 缺失）
    # 2) 加载/构建 Toolbox 索引
    # 3) 筛选目标零件
    #    --all:       index 全部
    #    --standard:  按 standard 过滤
    #    --bom:       复用 SolidWorksToolboxAdapter._find_sldprt() 匹配每行
    # 4) 过滤已缓存（除非 --overwrite）
    # 5) 进度显示:
    #    [12/330] GB/bolts/hex_bolt_m6.step  ✓  (1.2s)
    #    [13/330] GB/bolts/socket_cap_m6.step  ✗ (timeout)
    #    [50/330] ♻ session 周期重启...
    # 6) 失败累入 ~/.cad-spec-gen/sw_warmup_errors.log（带时间戳）
    # 7) 断点续跑：已缓存跳过
    # 8) 汇总: 目标 330 / 成功 328 / 失败 2 / 耗时 18m
```

---

## 8. 错误处理与降级矩阵

| 场景 | 行为 | 影响 |
|------|------|------|
| 非 Windows | `is_available()=False` → adapter 不注册 | 字节等同 |
| SW 未安装 | 同上 | 同上 |
| SW 版本 < 2024 | `is_available()=False` + env-check warning | 同上 |
| pywin32 未安装 | 同上，env-check 提示 `pip install pywin32` | 同上 |
| Toolbox 目录不存在 | 同上 | 同上 |
| **Toolbox Add-In 未启用**（决策 #13） | `is_available()=False` + env-check 给出勾选指引 | 同上 |
| Toolbox 索引扫描失败（权限） | warning + adapter 返回 miss | 走 jinja_primitive |
| **BOM 尺寸抽取失败**（决策 #9） | 返回 miss（绝不使用默认 configuration） | 降级，避免产错几何 |
| **BOM 抽到非 M 螺纹**（UNC/Tr/G/NPT，§1.3） | 返回 miss + warning "超出 Phase SW-B 范围" | 降级 |
| Token overlap < 0.30 | 返回 miss | 降级 |
| **COM 冷启动超时 90s**（决策 #10） | session._unhealthy=True | 全部 SW Toolbox 资源走降级 |
| 单零件 COM 导出失败（corrupt/timeout/err） | warning + 失败计数 +1 + miss | 单零件降级 |
| 连续 3 个零件 COM 失败 | 熔断（决策 #6） | 本进程后续全降级 |
| **每 50 个周期重启**（决策 #11） | session 自动 shutdown+start，不计熔断 | 透明继续 |
| **session 重启失败** | 视为冷启动失败 → 熔断 | 降级 |
| 磁盘满 | IOError → warning + miss | 单零件降级 |
| COM session 空闲 5 分钟 | 自动 shutdown 释放 | 下次 resolve 冷启动 |
| **STEP 导出单位错误（非 mm）** | SaveAs3 显式传 `units=mm`；SW doc property 异常时仍强制 mm | 几何单位正确 |
| `probe_dims()` 首跑缓存未命中 | 返回 None → Phase 1 envelope backfill 退化（§1.3 已知限制） | 建议用户 sw-warmup 预热 |

**核心不变量**：
1. 任何 SW 异常绝不阻断管道
2. 无 SW / Add-In 未启用 → 字节等同
3. 熔断后 → 等同降级
4. 尺寸抽不出 → miss（不产错几何）

---

## 9. 测试策略（三层分离）

### 9.1 Layer 1 — 单元测试（CI 全平台）

**`tests/test_sw_toolbox_catalog.py`**:
- `test_build_toolbox_index_filters_non_sldprt()` — fixture 混入 `.xls`/`.slddrw`/`.sldlfp`，验证仅收 `.sldprt`
- `test_build_toolbox_index_schema_version()` — 输出 dict 含 `schema_version`
- `test_load_toolbox_index_rebuilds_on_schema_bump()` — 伪造旧 schema_version 缓存验证重建
- `test_load_toolbox_index_uses_cache_when_fresh()`
- `test_load_toolbox_index_rebuilds_on_stale_mtime()`
- `test_tokenize_drops_stop_words()` — "bolts and studs" 不产生 "and"
- `test_tokenize_handles_cjk_and_ascii()`
- `test_extract_size_fastener_m6x20()` — "M6×20"、"M6 20"、"M6-20" 三种分隔符
- `test_extract_size_fastener_decimal()` — "M6.5×20"
- `test_extract_size_unc_returns_none()` — "1/4-20 UNC" 返回 None（范围外）
- `test_extract_size_trapezoidal_returns_none()` — "Tr16×2" 返回 None
- `test_extract_size_pipe_thread_returns_none()` — "G1/2"" 返回 None
- `test_extract_size_bearing_6205()`
- `test_extract_size_bearing_with_suffix()` — "6205-2RS" 只抽 6205（后缀丢失，§1.3 已知）
- `test_match_weighted_token_overlap_scoring()`
- `test_match_part_no_higher_weight()` — 验证 part_no tokens 权重生效
- `test_match_min_score_rejects()`

**`tests/test_sw_toolbox_adapter.py`**:
- `test_is_available_non_windows_returns_false()`
- `test_is_available_without_sw_returns_false()`
- `test_is_available_addin_disabled_returns_false()` — 决策 #13
- `test_is_available_unhealthy_session_returns_false()` — 熔断委托
- `test_resolve_cache_hit_no_com_call()`
- `test_resolve_cache_miss_triggers_com()`
- `test_resolve_com_failure_returns_miss()`
- `test_resolve_circuit_breaker_after_3_failures()`
- `test_resolve_low_score_returns_miss()`
- `test_resolve_size_extract_fail_returns_miss()` — 决策 #9
- `test_resolve_unc_thread_returns_miss()` — §1.3 范围外
- `test_probe_dims_cache_hit_reads_bbox()`
- `test_probe_dims_cache_miss_returns_none()`

**`tests/test_sw_com_session.py`**:
- `test_cold_start_timeout()` — 决策 #10
- `test_single_convert_timeout()` — 决策 #10
- `test_restart_every_n_converts()` — 决策 #11
- `test_circuit_breaker_flip_at_3()` — 决策 #6
- `test_reset_session_clears_breaker()`
- `test_is_healthy_reflects_breaker()`

### 9.2 Layer 2 — fake fixture 扫描

```
tests/fixtures/fake_toolbox/
├── GB/
│   ├── bolts and studs/
│   │   ├── hex bolt.sldprt       (空文件)
│   │   ├── stud.sldprt
│   │   └── sizes.xls             ★ 应被过滤
│   ├── nuts/
│   │   └── hex nut.sldprt
│   ├── bearing/
│   │   └── deep groove ball bearing.sldprt
│   └── drawings/
│       └── sample.slddrw          ★ 应被过滤
├── ISO/
│   ├── bolts/
│   │   └── hex bolt.sldprt
│   └── bearings/
│       └── deep groove ball bearing.sldprt
└── DIN/
    └── bolts/
        └── hex bolt.sldprt
```

### 9.3 Layer 3 — 端到端 + 覆盖率 regression

**`tests/test_sw_toolbox_integration.py`**:
```python
def test_e2e_bom_to_resolver_with_mocked_com():
    """加载 demo_bom.csv → PartsResolver → 验证覆盖率 >= baseline + 8 行"""

def test_coverage_regression_baseline():
    """固定 demo_bom.csv → 不带 SW 跑一遍记 baseline → 带 SW mock 跑一遍
    → 验证 solidworks_toolbox 命中 >= 8，jinja_primitive 命中减少 >= 8"""

@pytest.mark.requires_solidworks
def test_e2e_real_com_single_gb_bolt():
    """真实 COM 单零件转换 → STEP 存在 + 文件大小合理 + 单位为 mm"""

@pytest.mark.requires_solidworks
def test_e2e_real_com_session_restart():
    """真实 COM 连跑 51 个零件验证 session 自动 restart 不影响功能"""
```

### 9.4 `demo_bom.csv`（扩到 ≥ 15 行作为覆盖率 regression baseline）

```csv
part_no,name_cn,material,make_buy,category
GIS-DEMO-001,GB/T 70.1 M6×20 内六角圆柱头螺钉,钢,标准,fastener
GIS-DEMO-002,GB/T 276 深沟球轴承 6205,GCr15,标准,bearing
GIS-DEMO-003,GB/T 70.1 M4×10 内六角圆柱头螺钉,钢,标准,fastener
GIS-DEMO-004,GB/T 6170 M6 六角螺母,钢,标准,fastener
GIS-DEMO-005,GB/T 97.1 6 平垫圈,钢,标准,fastener
GIS-DEMO-006,GB/T 5782 M8×25 六角头螺栓,钢,标准,fastener
GIS-DEMO-007,GB/T 276 深沟球轴承 6204,GCr15,标准,bearing
GIS-DEMO-008,GB/T 297 圆锥滚子轴承 30205,GCr15,标准,bearing
GIS-DEMO-009,ISO 4762 M5×16 hex socket cap screw,steel,standard,fastener
GIS-DEMO-010,ISO 4032 M5 hex nut,steel,standard,fastener
GIS-DEMO-011,DIN 912 M3×8 cap screw,steel,standard,fastener
GIS-DEMO-012,1/4-20 UNC hex bolt,steel,standard,fastener
GIS-DEMO-013,Tr16×2 梯形螺纹丝杠,40Cr,外购,fastener
GIS-DEMO-014,非标异形件定制壳体,7075-T6,自制,housing
GIS-DEMO-015,Maxon ECX SPEED 22L 减速电机,-,外购,motor
```

**覆盖率 regression 预期**：
- 行 01-08 → `solidworks_toolbox` (GB 标准件) — 8 行
- 行 09-11 → `solidworks_toolbox` (ISO/DIN) — 3 行
- 行 12-13 → miss 降级到 `jinja_primitive`（§1.3 范围外）— 2 行
- 行 14 → `jinja_primitive`（非标） — 1 行
- 行 15 → `step_pool` (Maxon vendor synthesizer) — 1 行

SW Toolbox 命中率（满足决策 #1.2 "迁移 ≥ 8 行"）：**11/15 = 73%**

---

## 10. 实施步骤拆分

| # | 步骤 | 依赖 | 可并行 |
|---|------|------|--------|
| **SW-B0** | **Spike — 开发机实测 Toolbox COM 行为**：验证 `OpenDoc6` 是否弹 configuration 对话框；验证 `UserControl=False` 下的稳定性；验证 `LoadAddIn("SOLIDWORKS Toolbox")` 调用形式；产出 ≤ 200 行的 spike 报告放 `docs/spikes/` | 无 | — |
| SW-B1 | `sw_detect.py` 增量：`toolbox_addin_enabled` 检测（注册表）+ 单元测试 | B0 | — |
| SW-B2 | `sw_toolbox_catalog.py` — 扫描 + schema_version + token + 加权匹配 + 尺寸正则 + catalog 单元测试 + `fake_toolbox` fixture | 无 | 与 B1 并行 |
| SW-B3 | `sw_com_session.py` — 冷启动/单转/周期重启/熔断 + 纯 mock 单元测试 | B0 | 与 B2 并行 |
| SW-B4 | `sw_toolbox_adapter.py` — `is_available()` + `can_resolve()` + mock 单元测试（含 Add-In / 熔断委托分支） | B1, B2, B3 | — |
| SW-B5 | `sw_toolbox_adapter.py` — `resolve()` + `probe_dims()` + `_find_sldprt()` + 缓存命中/未命中 + 更完整 mock 测试 | B4 | — |
| SW-B6 | `parts_resolver.py` 注册 + `parts_library.default.yaml` 规则（GB 高优先级 + ISO/DIN 兜底 + `token_weights` + `size_patterns` + `com`） | B5 | — |
| SW-B7 | `cad_pipeline.py` 新增 `sw-warmup` 子命令（`--standard`/`--bom`/`--all`/`--dry-run`/`--overwrite`）+ env-check 增强 | B6 | — |
| SW-B8 | `demo_bom.csv` 扩到 ≥ 15 行 + `test_sw_toolbox_integration.py` 端到端 mocked 测试 + 覆盖率 regression 测试 | B6 | 与 B7 并行 |
| SW-B9 | `@requires_solidworks` 真实 COM 测试 + 开发机验收：demo_bom.csv 覆盖率满足 ≥ 73% + session 周期重启实测 | B7, B8 | — |
| SW-B10 | `pyproject.toml` 新增 `solidworks` optional-deps + `requires_solidworks` marker + coverage report 格式化输出 `solidworks_toolbox` 命中 + 文档更新 | B9 | — |

**每步验收标准**：每步对应 pytest 命令，所有测试绿才能进下一步。

---

## 11. 合规性与安全

- **版权合规** — SW 资产只留本机 `~/.cad-spec-gen/`，绝不入 git
- **EULA 合规** — COM 自动化属 SW EULA 允许范围
- **用户体验** — `Visible=False` + `UserControl=False`，避免弹窗
- **可审计性** — 错误记入 `~/.cad-spec-gen/sw_warmup_errors.log`，成功路径记 stdout

---

## 12. 风险与缓解（已大幅压缩；原开放问题已内化进设计）

| 风险 | 影响 | 缓解 |
|------|------|------|
| SW 2024+ COM 接口小版本变化 | OpenDoc6/SaveAs3 失败 | 所有 COM 调用 try/except + 熔断 + SW-B0 spike 实测 |
| Toolbox 零件命名不稳定（大小写、语种、空格） | token 匹配失准 | `tokenize()` lower + CJK 处理 + stop_words + 子目录贡献 token |
| BOM 格式多样（`M6×20`/`M6*20`/`M6-20`/`M6 20`） | 尺寸抽取失败 | 分隔符正则覆盖 `[×xX*\-\s]` |
| sldprt configuration 弹框挂起 COM | OpenDoc6 超时 | SW-B0 spike 验证；必要时 `OpenDoc6(LoadLightweight=True)` |
| 并发管道进程冲突 | 文件锁 | 写 `*.step.tmp` 后 atomic rename |
| pywin32 安装失败 | Toolbox 不可用 | optional-deps + env-check 指引 |

---

## 13. 留给 Phase SW-C 的开放问题

1. **Configuration 自动选择** — 若 Phase SW-B 实战发现默认 configuration 尺寸严重偏离 BOM（覆盖率明显低于 73%），Phase SW-C 考虑加 configuration 枚举 + 匹配
2. **COM 超时实战调参** — Phase SW-B 验收时若发现 30s 不够，yaml 已支持覆盖；Phase SW-C 可根据数据调整默认
3. **coverage report 显示 SW Toolbox 来源** — 当前覆盖率只显示 adapter 名字，Phase SW-C 加 "来源：SW Toolbox GB/bolts/hex_bolt_m6.sldprt"
4. **STEP tessellation 粒度优化** — 小零件（M3）渲染时三角面可能过细，属渲染链优化

---

## 14. 参考

- 前置设计: `docs/design/solidworks-integration-plan.md` §4.4、§5、§8、§11
- Phase SW-A 交付: commits `460e0a1`（sw_detect）→ `99d067e`（联动缓存清除）
- `PartsAdapter` 接口: `adapters/parts/base.py`
- 参考实现: `adapters/parts/step_pool_adapter.py`

---

## 附录 A — 五角色联审修订记录（v1 → v2）

本节记录 v1 → v2 修订的完整映射表，便于后续审计。

| # | 修订项 | 触发角色 | 严重度 | 落位章节 |
|---|--------|---------|--------|---------|
| 1 | Toolbox Add-In 启用检查 | SolidWorks 操作员 | blocker | §2 #13, §5.4, §8 |
| 2 | Toolbox configuration 弹框 spike | SolidWorks 操作员 | blocker | §10 SW-B0 |
| 3 | SW 进程内存 + 冷启动超时 | SolidWorks 操作员 | blocker | §2 #10 #11, §5.2, §8 |
| 4 | 默认 configuration fallback 改 miss | 机械设计师 | high | §2 #9, §1.3, §8 |
| 5 | probe_dims 冷路径退化显式标注 | 系统架构师 | high | §1.3, §5.3, §8 |
| 6 | part_no 加入 query_tokens + 加权 | 机械设计师 | high | §2 #12, §3.2, §5.1, §6 |
| 7 | 索引 schema_version | 系统架构师 | medium | §5.1, §9.1 |
| 8 | SetConfiguration 策略明确 | 系统架构师 | medium | §1.3, §3.2 |
| 9 | 覆盖率可度量 + demo_bom 扩充 | 系统分析师 | medium | §1.2, §9.3, §9.4 |
| 10 | 螺纹类型严格限定公制 M | 机械设计师 | medium | §1.3, §6, §9.1 |
| 11 | 轴承后缀丢失声明已知限制 | 机械设计师 | low | §1.3 |
| 12 | STEP 不继承 SW appearance 声明 | 3D 设计师 | low | §1.3 |
| 13 | STEP Units 显式 mm | SolidWorks 操作员 / 3D 设计师 | low | §5.2 convert 流程 |
| 14 | 熔断器状态归属明确 | 系统架构师 | low | §5.2 docstring, §5.3 |
| 15 | Toolbox 目录过滤非 sldprt | SolidWorks 操作员 | low | §5.1, §9.2 fixture |
