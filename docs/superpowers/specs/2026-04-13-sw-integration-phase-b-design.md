# Phase SW-B — SolidWorks Toolbox COM Adapter 设计规格

> 版本: v1.0 — 2026-04-13
> 状态: 待实施
> 前置: Phase SW-A 已完成（`sw_detect.py` / `sw_material_bridge.py` 已合入 main）
> 参考: `docs/design/solidworks-integration-plan.md` §4.4、§5、§8、§11

---

## 1. 目标与范围

### 1.1 目标

将 SolidWorks Toolbox 中的 1818 个标准件（GB/ISO/DIN）接入 `cad-spec-gen` 的 `PartsResolver` 体系，通过 COM 自动化按需把 sldprt 转换为 STEP 文件，作为现有 `bd_warehouse` / `step_pool` 之外的**可选增强 adapter**。

**量化目标**：
- 管道对标准件的覆盖率从 ~9%（仅 step_pool + bd_warehouse）提升到 ~40%+（加入 GB/ISO/DIN 主要品类）
- 无 SW 时输出与现状**字节等同**（不可退化）
- COM 自动化对用户**不可见**（`swApp.Visible = False`）

### 1.2 非目标

- 不做 SolidWorks 的参数化写入（只读，不改原始 sldprt）
- 不在 git 仓库中包含任何 SW 资产（版权合规，见 `solidworks-integration-plan.md` §2）
- 不解决 SW Toolbox 之外的 sldprt 转换（Phase SW-B 只覆盖 Toolbox 目录）
- 不做 PDM Vault 集成

---

## 2. 关键设计决策

本设计通过 brainstorming 锁定 8 个决策，列于此作为实施时的权威参考：

| # | 决策点 | 选择 |
|---|--------|------|
| 1 | COM 启动策略 | **A+B 混合** — 默认按需启动（`resolve()` 触发），并提供 `sw-warmup` 批量预热命令 |
| 2 | Toolbox 索引生成时机 | **首次 `resolve()` 透明扫描** —— 结果缓存到 `~/.cad-spec-gen/sw_toolbox_index.json` |
| 3 | BOM → sldprt 匹配算法 | **YAML 粗分类 + adapter token overlap 精定位** —— `min_score` 默认 0.30 |
| 4 | BOM 尺寸规格提取 | **正则抽 + 缺省默认值** —— 正则规则放 `parts_library.default.yaml` `size_patterns` 段可覆盖 |
| 5 | SW Toolbox 在 resolver 链中的优先级 | **GB 标准件高优先级**（厂商 STEP 之后）；**ISO/DIN 作为 bd_warehouse 专项之后的兜底** |
| 6 | COM 错误处理策略 | **宽松降级 + 连续 3 次失败熔断** —— 单零件超时硬编码 30s |
| 7 | 测试分层策略 | **三层分离** —— 单元（mock COM）+ fake fixture 扫描 + 端到端（mocked + `@requires_solidworks`） |
| 8 | `sw-warmup` 命令接口 | **B+C 组合** —— `--standard` / `--bom` / `--all` / `--dry-run` / `--overwrite` |

---

## 3. 架构总览

### 3.1 数据流

```
BOM row (part_no / name_cn / material)
    │
    ▼
PartsResolver.resolve()  ── 按 parts_library YAML mappings first-hit-wins
    │
    ├──► 厂商 STEP (Maxon/LEMO/ATI) — 最具体
    ├──► SolidWorksToolboxAdapter (GB 标准件) — 国标精准几何
    ├──► bd_warehouse 专用轴承/紧固件 (class 专项)
    ├──► SolidWorksToolboxAdapter (ISO/DIN 兜底)
    ├──► bd_warehouse 通用 fastener/bearing
    └──► jinja_primitive (永远命中的兜底)
```

### 3.2 `SolidWorksToolboxAdapter.resolve()` 内部流程

```
1. Toolbox 索引加载
   └─ 首次 → sw_toolbox_catalog.build_toolbox_index() 扫描
   └─ 后续 → sw_toolbox_catalog.load_toolbox_index() 读 JSON 缓存
      └─ mtime 比较，目录更新时自动重建

2. YAML spec 限定候选子目录
   └─ spec.standard = "GB" / [ISO, DIN]
   └─ spec.subcategories = ["bolts and studs", "nuts", ...]

3. 从 BOM name_cn 正则抽尺寸
   └─ fastener → {size: "M6", length: 20}
   └─ bearing  → {model: "6205"}
   └─ 抽不到字段缺省（不阻断）

4. 候选 sldprt 做 token overlap 打分
   └─ query_tokens = tokenize(name_cn + material + size 字段)
   └─ part_tokens  = sldprt 文件名 + 子目录预提取的 tokens
   └─ score = |query_tokens ∩ part_tokens| / |query_tokens|

5. 置信度 ≥ min_score (0.30) 才继续；否则返回 miss

6. 构造目标 STEP 路径
   └─ ~/.cad-spec-gen/step_cache/sw_toolbox/<standard>/<sub>/<name>.step

7. 缓存命中 → 直接返回 ResolveResult(kind="step_import")
   └─ probe_bbox() 计算真实尺寸

8. 缓存未命中 → COM 转换
   └─ sw_com_session.convert_sldprt_to_step()
   └─ OpenDoc6 → (SetConfiguration) → SaveAs3(STEP AP214) → CloseDoc
   └─ 成功 → 返回 step_import；失败 → 熔断器记录 + 返回 miss

9. 任何异常 → warning 记录 + 返回 miss（让 resolver 降级）
```

---

## 4. 组件分解

### 4.1 新增文件

| 路径 | 职责 | 规模 |
|------|------|------|
| `adapters/solidworks/sw_toolbox_catalog.py` | 扫描 Toolbox 目录树 + 生成/读取索引 JSON + token 提取 + 尺寸正则匹配 | ~250 行 |
| `adapters/solidworks/sw_com_session.py` | COM 会话单例 + OpenDoc/SaveAs 封装 + 熔断器 + 30s 超时 watchdog + 空闲超时自动释放 | ~200 行 |
| `adapters/parts/sw_toolbox_adapter.py` | `SolidWorksToolboxAdapter` 实现 `PartsAdapter` 接口 | ~300 行 |
| `tests/fixtures/fake_toolbox/` | 伪造 Toolbox 目录结构（GB/bolts/、ISO/bolts/ 等 + 空 sldprt） | ~10 文件 |
| `tests/fixtures/demo_bom.csv` | 端到端验收 BOM（3 个典型零件） | ~5 行 |
| `tests/test_sw_toolbox_catalog.py` | catalog 单元测试（scan + match + 正则） | ~200 行 |
| `tests/test_sw_toolbox_adapter.py` | adapter 单元测试（mock win32com） | ~250 行 |
| `tests/test_sw_toolbox_integration.py` | 端到端集成测试（mocked COM + `@requires_solidworks`） | ~150 行 |

### 4.2 改动文件

| 路径 | 改动 | 规模 |
|------|------|------|
| `parts_resolver.py` | `default_resolver()` 注册 SW Toolbox adapter（有 SW 时） | +10 行 |
| `parts_library.default.yaml` | 增加 `solidworks_toolbox` 配置段 + GB 高优先级规则 + ISO/DIN 兜底规则 + `size_patterns` 段 | +60 行 |
| `cad_pipeline.py` | 新增 `cmd_sw_warmup()` + `sw-warmup` 子命令解析 + env-check Toolbox 索引报告 | +120 行 |
| `pyproject.toml` | 新增 `[project.optional-dependencies] solidworks = ["pywin32>=306"]` + `requires_solidworks` marker | +5 行 |

---

## 5. 接口契约

### 5.1 `sw_toolbox_catalog.py`

```python
@dataclass
class ToolboxPart:
    standard: str           # "GB" / "ISO" / "DIN"
    subcategory: str        # "bolts and studs" / "nuts" / "bearing"
    sldprt_path: str        # 绝对路径
    filename: str           # "hex bolt.sldprt"
    tokens: list[str]       # ["hex", "bolt", "螺栓"] 从文件名+子目录提取

def build_toolbox_index(toolbox_dir: Path) -> dict:
    """扫描 Toolbox 目录 → 返回索引 dict。耗时操作，通常只跑一次。"""

def load_toolbox_index(cache_path: Path, toolbox_dir: Path) -> dict:
    """读缓存；缓存不存在或过期（mtime 比较）则重建。"""

def match_toolbox_part(
    index: dict,
    query_tokens: list[str],
    standards: list[str],
    subcategories: list[str],
    min_score: float = 0.30,
) -> Optional[tuple[ToolboxPart, float]]:
    """Token overlap 打分，返回置信度最高的 part + 分数；低于阈值返回 None。"""

def extract_size_from_name(name_cn: str, patterns: dict) -> dict:
    """从 BOM name_cn 正则抽 {size: 'M6', length: 20}，失败键缺省。"""

def tokenize(text: str) -> list[str]:
    """拆分：大小写边界、下划线、空格、中英文边界 → 小写 token 列表。"""
```

### 5.2 `sw_com_session.py`

```python
class SwComSession:
    """延迟单例：首次 convert 调用时启动 SW；
    空闲超时（5 分钟）自动释放。
    内置熔断：连续 3 次 COM 异常则标记 _unhealthy=True，后续 raise。"""

    def convert_sldprt_to_step(
        self,
        sldprt_path: str,
        step_out: str,
        configuration: Optional[str] = None,
    ) -> bool:
        """单零件转换。超时 30s。失败 return False 并记 warning。"""

    def is_healthy(self) -> bool: ...
    def shutdown(self) -> None: ...

_SESSION_SINGLETON: Optional[SwComSession] = None
def get_session() -> SwComSession: ...
def reset_session() -> None: ...   # 测试用
```

### 5.3 `sw_toolbox_adapter.py`

```python
class SolidWorksToolboxAdapter(PartsAdapter):
    name = "solidworks_toolbox"

    def __init__(self, project_root: str = "", config: Optional[dict] = None):
        """config 来自 parts_library.yaml 的 solidworks_toolbox 段：
        - enabled: "auto" | True | False
        - standards: [GB, ISO, DIN]
        - cache: ~/.cad-spec-gen/step_cache/sw_toolbox/
        - size_patterns: {fastener: ..., bearing: ...}
        - min_score: 0.30
        """

    def is_available(self) -> bool:
        """sw_detect.installed + version_year ≥ 2024 + pywin32_available
        + toolbox_dir 存在 + 非熔断状态"""

    def can_resolve(self, query) -> bool:
        """总是 True（具体匹配由 resolve 决定）"""

    def resolve(self, query, spec) -> ResolveResult:
        """主编排流程（见 §3.2）"""

    def probe_dims(self, query, spec) -> Optional[tuple]:
        """缓存命中时读 STEP bbox；缓存未命中时返回 None（避免为了测尺寸而触发 COM 启动）"""

    def _find_sldprt(self, query, spec) -> Optional[tuple[ToolboxPart, float]]:
        """供 sw-warmup --bom 复用：只做匹配，不触发 COM 转换。"""
```

---

## 6. YAML 配置结构

在 `parts_library.default.yaml` 顶层新增 `solidworks_toolbox` 配置段和 `mappings` 规则。

```yaml
# ─── SolidWorks Toolbox 配置（可选；需 SW ≥ 2024 + pywin32）───
solidworks_toolbox:
  enabled: auto                   # "auto" = 检测到 SW 则启用；"true"/"false" 强制
  standards: [GB, ISO, DIN]       # 允许导出的标准
  cache: ~/.cad-spec-gen/step_cache/sw_toolbox/
  min_score: 0.30                 # token overlap 最低置信度阈值

  # 尺寸正则：按 category 分组，adapter 内按 category 选择
  size_patterns:
    fastener:
      size:   '[Mm](\d+(?:\.\d+)?)'        # 匹配 M6 / M6.5
      length: '[×xX](\d+(?:\.\d+)?)'        # 匹配 ×20 / x20
    bearing:
      model:  '\b(\d{4,5})\b'               # 匹配 6205 / 30205

mappings:
  # [现有] 厂商 STEP - Maxon/LEMO/ATI（保持原位）

  # ──────────────────────────────────────────────
  # ★ 新增：SW Toolbox GB 规则（高优先级）
  # ──────────────────────────────────────────────

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

  # ──────────────────────────────────────────────
  # [现有] bd_warehouse 专用轴承/紧固件 class 专项（保持原位）
  # ──────────────────────────────────────────────

  # ──────────────────────────────────────────────
  # ★ 新增：SW Toolbox ISO/DIN 兜底（bd_warehouse 专项之后）
  # ──────────────────────────────────────────────

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

  # ──────────────────────────────────────────────
  # [现有] bd_warehouse 通用 fastener/bearing 兜底（保持原位）
  # [现有] jinja_primitive 最终兜底（保持原位）
```

**关键设计**：
- `subcategories` 是候选白名单 —— adapter 只在这些子目录里搜，大幅缩小 token overlap 的搜索空间
- `part_category` 用于查 `size_patterns`，因紧固件和轴承的尺寸正则不同
- YAML `keyword_contains` 做一级判断（是不是 GB 零件），adapter token overlap 做二级判断（具体是哪一个）

---

## 7. `sw-warmup` 命令接口

```bash
# 默认预热 GB 标准件（~330 个，最实用）
cad_pipeline.py sw-warmup

# 指定标准
cad_pipeline.py sw-warmup --standard GB,ISO
cad_pipeline.py sw-warmup --standard ISO

# 按项目 BOM 精准预热
cad_pipeline.py sw-warmup --bom subsystem/claw/bom.csv

# 全量（1818 个零件，需显式 --all 避免误触发）
cad_pipeline.py sw-warmup --all

# 其他选项
cad_pipeline.py sw-warmup --standard GB --dry-run       # 只列出，不转换
cad_pipeline.py sw-warmup --standard GB --overwrite     # 强制重新转换
```

### 7.1 核心流程

```python
def cmd_sw_warmup(args):
    # 1) 检查 SW + pywin32 → 不可用直接 exit 1 + 清晰提示
    # 2) 加载/构建 Toolbox 索引
    # 3) 根据 args 筛选目标零件列表：
    #    - --all:       index 中所有零件
    #    - --standard:  按 standard 过滤
    #    - --bom:       读 BOM → 对每行调用
    #                   SolidWorksToolboxAdapter._find_sldprt() 找候选 sldprt
    #    - 默认:        等价于 --standard GB
    # 4) 过滤已缓存的（除非 --overwrite）
    # 5) 交互式进度显示：
    #      [12/330] GB/bolts/hex_bolt_m6.step  ✓  (1.2s)
    #      [13/330] GB/bolts/socket_cap_m6.step  ✗ (timeout)
    # 6) 错误追加记入 ~/.cad-spec-gen/sw_warmup_errors.log（带时间戳）
    # 7) 断点续跑：已成功写入的 STEP 下次跑自动跳过
    # 8) 结束后打印汇总：
    #      目标 330 / 成功 328 / 失败 2 / 耗时 18m
```

### 7.2 `--bom` 模式的复用约定

`cmd_sw_warmup` 不应复写匹配算法。读 BOM → 为每行构造 `PartQuery` → 直接调用 `SolidWorksToolboxAdapter._find_sldprt()`（把匹配逻辑从 `resolve()` 里抽成独立方法）→ 拿到 sldprt 列表 → 批量送 COM。

---

## 8. 错误处理与降级矩阵

| 场景 | 行为 | 影响 |
|------|------|------|
| 非 Windows 平台 | `sw_detect.installed=False` → `is_available()=False` → adapter 不注册 | 管道与现状字节等同 |
| SW 未安装 | 同上 | 同上 |
| SW 版本 < 2024 | `is_available()=False` + env-check warning | 同上 |
| pywin32 未安装 | `sw_detect.pywin32_available=False` → `is_available()=False` + env-check 提示 | 同上 |
| Toolbox 目录不存在 | `sw_detect.toolbox_dir=None` → `is_available()=False` | 同上 |
| Toolbox 索引扫描失败（权限） | warning + adapter 返回 miss | 该类零件走 jinja_primitive |
| BOM `name_cn` 无法提取尺寸 | 尺寸字段缺省 → 使用 sldprt 默认 configuration | 几何可能非精确尺寸，记 warning |
| Token overlap 置信度 < 0.30 | adapter 返回 miss | 降级到下一条 YAML 规则 |
| COM session 启动失败 | 熔断触发 → 后续所有 resolve 直接 miss + 一次性 error log | 本次运行全走降级链 |
| 单零件 COM 导出失败（corrupt / timeout / SaveAs err） | warning + 失败计数 +1 + 返回 miss | 单零件降级，其他继续 |
| 连续 3 个零件 COM 失败 | 熔断触发（同上） | 避免 cascading 等待 30s × N |
| 磁盘满 | 捕获 IOError + warning + miss | 单零件降级 |
| COM session 空闲 5 分钟 | 自动 shutdown 释放 SW 进程 | 下次 resolve 冷启动 |

### 8.1 核心不变量

1. **绝不阻断管道** —— 任何 SW 相关异常都 return miss 让 resolver 降级
2. **无 SW 字节等同** —— `is_available()=False` 时 adapter 完全不参与 resolve
3. **熔断后等同降级** —— 有 SW 但熔断触发时，管道退化到"好像没装 SW"的状态

---

## 9. 测试策略（三层分离）

### 9.1 Layer 1 — 单元测试（无 SW，CI Linux/Windows 都能跑）

**`tests/test_sw_toolbox_catalog.py`**:
- `test_build_toolbox_index_with_fake_dir()` — 用 `fixtures/fake_toolbox/`
- `test_load_toolbox_index_uses_cache_when_fresh()`
- `test_load_toolbox_index_rebuilds_on_stale_mtime()`
- `test_match_toolbox_part_token_overlap_scoring()`
- `test_match_toolbox_part_min_score_rejects()`
- `test_extract_size_fastener_m6x20()`
- `test_extract_size_bearing_6205()`
- `test_extract_size_missing_fields_tolerated()`
- `test_tokenize_handles_cjk_and_ascii()`

**`tests/test_sw_toolbox_adapter.py`**:
- `test_is_available_non_windows_returns_false()`
- `test_is_available_without_sw_returns_false()`
- `test_resolve_cache_hit_no_com_call()` — mock COM 验证不被调用
- `test_resolve_cache_miss_triggers_com()` — mock COM 验证被调用
- `test_resolve_com_failure_returns_miss()`
- `test_resolve_circuit_breaker_after_3_failures()`
- `test_resolve_low_score_returns_miss()`
- `test_probe_dims_cache_hit_reads_bbox()`
- `test_probe_dims_cache_miss_returns_none()` — 不触发 COM

### 9.2 Layer 2 — fake fixture 扫描测试

```
tests/fixtures/fake_toolbox/
├── GB/
│   ├── bolts and studs/
│   │   ├── hex bolt.sldprt           (空文件 0 字节)
│   │   └── stud.sldprt
│   ├── nuts/
│   │   └── hex nut.sldprt
│   └── bearing/
│       └── deep groove ball bearing.sldprt
├── ISO/
│   └── bolts/
│       └── hex bolt.sldprt
└── DIN/
    └── bolts/
        └── hex bolt.sldprt
```

验证索引包含 5 个 part、token 正确、standard/subcategory 字段完整。

### 9.3 Layer 3 — 端到端集成测试

**`tests/test_sw_toolbox_integration.py`**:

```python
# 默认执行：mock COM，返回预制的 STEP 文件
def test_e2e_bom_to_resolver_with_mocked_com():
    """加载 demo_bom.csv → PartsResolver → 验证命中 solidworks_toolbox adapter
    → 验证生成的 std_*.py 包含 step_import 调用"""

# 仅本地跑：真实 COM
@pytest.mark.requires_solidworks
def test_e2e_real_com_single_gb_bolt():
    """真实 COM 转换一个 GB/bolts/hex bolt.sldprt → STEP → 验证文件大小合理"""
```

**`tests/fixtures/demo_bom.csv`**:
```csv
part_no,name_cn,material,make_buy,category
GIS-DEMO-001,M6×20 内六角螺钉 GB/T 70.1,钢,标准,fastener
GIS-DEMO-002,深沟球轴承 GB/T 276 6205,SUS304,标准,bearing
GIS-DEMO-003,M4×10 GB/T 70.1 内六角螺钉,钢,标准,fastener
```

### 9.4 CI 策略

- Layer 1 + Layer 2 + Layer 3 mocked 版本在 CI 跑
- Layer 3 `@requires_solidworks` 用 `pytest -m requires_solidworks` 本地触发
- 在 `pyproject.toml` 注册新 marker `requires_solidworks: 需要真实 SolidWorks 安装`

---

## 10. 实施步骤拆分

为 `writing-plans` 阶段提供已分解的任务清单：

| # | 步骤 | 依赖 | 可并行 |
|---|------|------|--------|
| SW-B1 | `sw_toolbox_catalog.py` — 扫描 + 索引 + token 提取 + 尺寸正则 + catalog 单元测试 + `fake_toolbox` fixture | 无 | — |
| SW-B2 | `sw_com_session.py` — COM 单例 + 超时 + 熔断（纯 mock 测试，不依赖 real SW） | 无 | 与 B1 并行 |
| SW-B3 | `sw_toolbox_adapter.py` — `SolidWorksToolboxAdapter.is_available()` + `can_resolve()` + mock 单元测试 | B1, B2 | — |
| SW-B4 | `sw_toolbox_adapter.py` — `resolve()` + `probe_dims()` + 缓存命中/未命中路径 + 更完整的 mock 测试 | B3 | — |
| SW-B5 | `parts_resolver.py` 注册 + `parts_library.default.yaml` 规则（GB 高优先级 + ISO/DIN 兜底 + `size_patterns`） | B4 | — |
| SW-B6 | `cad_pipeline.py` 新增 `sw-warmup` 子命令（`--standard` / `--bom` / `--all` / `--dry-run` / `--overwrite`） | B5 | — |
| SW-B7 | `demo_bom.csv` + `test_sw_toolbox_integration.py` 端到端 mocked 测试 | B5 | 与 B6 并行 |
| SW-B8 | `@requires_solidworks` 真实 COM 测试 + 开发机验收：`demo_bom.csv` 跑通 → STEP 正确生成 → 能进 build phase | B6, B7 | — |
| SW-B9 | `pyproject.toml` 新增 `solidworks` optional-dependencies + `env-check` 增强（Toolbox 索引状态报告） + coverage report 显示 `solidworks_toolbox` 命中数 | B8 | — |

**每步验收标准**：每步都有对应的 pytest 命令，所有测试绿才能进下一步。

---

## 11. 合规性与安全

- **版权合规** — 所有 SW 资产（sldprt / 生成的 STEP）仅留存在用户本机 `~/.cad-spec-gen/`，**绝不入 git**
- **EULA 合规** — COM 自动化属于 SolidWorks EULA 明确允许的 "automation through API"
- **用户体验** — `swApp.Visible = False` + `swApp.UserControl = False`，避免意外弹出 SW GUI
- **可审计性** — 所有 COM 调用记入 `~/.cad-spec-gen/sw_warmup_errors.log`（失败）和管道 stdout（成功）

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| SW 2024+ COM 接口在小版本间变化 | OpenDoc6/SaveAs3 调用失败 | 所有 COM 调用包 try/except + 熔断 |
| Toolbox 零件命名约定不稳定（子目录名大小写、语种） | token 匹配失准 | `tokenize()` 做 lower + CJK 处理 + 子目录也贡献 token |
| BOM 格式多样（`M6×20` / `M6*20` / `M6-20`） | 尺寸抽取失败 | 正则放 yaml 可覆盖 + 失败降级到默认 configuration |
| 大 sldprt（Toolbox Pattern）COM 导出 >30s | 熔断误触发 | 30s 超时为 watchdog 粒度；若实测需要可提升到 60s（yaml 可覆盖是未来工作） |
| 并发管道进程同时转换同一个 sldprt | 文件锁冲突 | 写 STEP 到 `*.step.tmp` 后 atomic rename；命中旧的完整文件则跳过 |
| pywin32 安装失败 | Toolbox 不可用 | optional-dependencies 明确标记 + env-check 提示 `pip install pywin32` |

---

## 13. 开放问题（留给 Phase SW-C）

1. **COM 超时的 yaml 可配置化** — 当前硬编码 30s，后续按需做成配置
2. **真实 COM 长时间稳定性** — Phase SW-B8 验收时实测一批零件，决定是否需要 session restart 周期（如每 100 个零件重启一次）
3. **Configuration 自动选择** — 目前假设 sldprt 的默认 configuration 匹配 BOM 尺寸；若否，需要 COM 枚举 configurations 并按尺寸选择（更复杂）
4. **coverage report 格式** — SW Toolbox 命中如何呈现（"来源：SW Toolbox GB/bolts/hex_bolt_m6.sldprt"）

---

## 14. 参考

- 前置设计: `docs/design/solidworks-integration-plan.md` §4.4、§5、§8、§11
- Phase SW-A 交付: commits `460e0a1`（sw_detect）→ `99d067e`（联动缓存清除）
- `PartsAdapter` 接口: `adapters/parts/base.py`
- 现有 adapter 参考实现: `adapters/parts/step_pool_adapter.py`（最接近的参考）
