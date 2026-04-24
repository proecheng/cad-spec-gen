# B-16 — Toolbox 多规格件 ShowConfiguration2 设计规格

**版本**：v0.2（代码路径审查后修正）  
**日期**：2026-04-24  
**分支**：feat/b16-toolbox-multi-config

---

## 1. 背景与问题

SW Toolbox 的标准件（螺栓、螺母、轴承等）每个 `.sldprt` 文件承载同规格系列的全部尺寸——例如一个 `GB_T70-1.SLDPRT` 内含 M3×8 到 M24×200 共数十个 configuration。`sw_convert_worker.py` 当前不做 configuration 切换，始终导出默认 config（通常是最小规格，如 M3×10），导致 BOM 中写 M6×20 时 STEP 模型尺寸错 3-5 倍且无任何提示。

### 1.1 现象

```
BOM 行: 内六角螺栓 GB/T 70.1 M6×20
STEP 输出: 实际几何 = M3×10（默认 config）
视觉效果: 螺栓尺寸错 3-5 倍，无视觉提示
```

### 1.2 SW COM 机制

- `IModelDoc2.ConfigurationManager.GetConfigurationNames()` — 枚举文件内全部 configuration 名称
- `IModelDoc2.ShowConfiguration2(name)` — 切换活动 configuration，返回 `True/False`
- 必须在 `OpenDoc6` 之后、`SaveAs3` 之前调用

---

## 2. 设计决策

| 问题 | 决策 |
|---|---|
| Config 名解析方式 | 混合：yaml 标准化 → candidate；worker 用 `GetConfigurationNames()` 验证/回退 |
| 覆盖范围 | 全部三类（螺栓/螺钉 + 轴承/销 + 螺母/垫圈），螺母/垫圈 best-effort 回退 |
| 匹配失败处理 | worker exit 5（新 exit code）→ `SwComSession` 不计入熔断器；调用方回退 bd_warehouse |
| 用户通知 | console `logger.warning` 每件一行 + `sw_report.html` Config 列（`ResolveReportRow.config_match`） |

---

## 3. 数据流（含真实调用链）

```
BOM 行
  "名称": "内六角螺栓"
  "材质/型号": "GB/T 70.1 M6×20"
        │
        ▼
parts_resolver.py → PartQuery(name_cn="内六角螺栓", material="GB/T 70.1 M6×20")
        │
        ▼
adapters/parts/sw_toolbox_adapter.py  SwToolboxAdapter.resolve()
  ├─ 已有：索引匹配 → SwToolboxPart(standard, subcategory, sldprt_path, filename, tokens)
  ├─ 新增：_build_candidate_config(query.material, resolver_cfg) → "GB_T70.1-M6x20"
  ├─ 新增：part.target_config = "GB_T70.1-M6x20"   （SwToolboxPart 新字段）
  └─ 新增：缓存路径含 config 后缀
       step_abs = cache_root / standard / subcategory / "GB_T70-1_GB_T70.1-M6x20.step"
        │
        ▼ 缓存未命中
adapters/solidworks/sw_com_session.py  SwComSession.convert_sldprt_to_step()
  ├─ 新增参数：target_config: str | None = None
  ├─ 返回类型：int（0=成功, 5=config未找到, 其他=真错误）
  └─ 内部 _do_convert(sldprt_path, step_out, target_config)
       └─ cmd = [python, -m, adapters.solidworks.sw_convert_worker,
                 sldprt_path, tmp_path, target_config]  ← argv[3] 可选
        │
        ▼
adapters/solidworks/sw_convert_worker.py  _convert()
  ├─ target_config = argv[2] if len(argv) > 2 else None  （argv 从 _convert 的参数传入）
  ├─ OpenDoc6(sldprt_path)
  ├─ GetConfigurationNames() → ["GB_T70.1-M6x10", "GB_T70.1-M6x20", ...]
  ├─ _resolve_config(target_config, available)
  │   ├─ 精确匹配（大小写不敏感）→ ShowConfiguration2(matched) ✓ → SaveAs3
  │   ├─ 模糊匹配（去 -_/ 空格后比较）→ ShowConfiguration2(matched) ✓ → SaveAs3
  │   └─ 无匹配 → stderr 输出可用列表 → sys.exit(5)
  └─ CloseDoc / ExitApp（已有）
        │
        ▼
sw_com_session._do_convert() 接收 returncode
  ├─ rc == 0 → validate + atomic rename → return 0
  ├─ rc == 5 → cleanup tmp → return 5（不计入熔断器）
  └─ rc 其他 → cleanup tmp → 计入熔断器 → return rc
        │
        ▼
sw_toolbox_adapter.resolve()
  ├─ rc == 0 → 返回 ResolveResult(status="hit", ...)
  ├─ rc == 5 → logger.warning → 更新 ResolveReportRow.config_match="fallback" → return _miss()
  └─ rc 其他 → return _miss("COM convert failed")（已有逻辑）
```

---

## 4. yaml 配置结构

追加到 `parts_library.default.yaml` `solidworks_toolbox:` 段末（同步到 `parts_library.yaml`）：

```yaml
  # 新增段 ─────────────────────────────────────
  config_name_resolver:
    standard_transforms:          # 顺序执行，标准编号标准化
      - {from: "GB/T ", to: "GB_T"}
      - {from: "GB／T ", to: "GB_T"}   # 全角斜杠兼容
      - {from: "ISO ", to: "ISO_"}
      - {from: " ", to: ""}            # 去除残余空格
    size_transforms:              # 尺寸字符串标准化
      - {from: "×", to: "x"}
      - {from: "×", to: "x"}          # 全角乘号
      - {from: " ", to: ""}
    separator: "-"                # 标准编号 + separator + 尺寸
```

### 4.1 BOM material 字段解析

```python
# adapters/parts/sw_toolbox_adapter.py 新增
import re

_SPEC_RE = re.compile(
    r'^(?P<standard>(?:GB[/／]T|ISO|DIN|JIS)\s*[\d.]+(?:\s+Part\s+\d+)?)'
    r'\s+(?P<size>.+)$'
)

def extract_full_spec(material: str) -> tuple[str, str] | None:
    """从 material 字段解析 (standard, size)，失败返回 None。"""
    m = _SPEC_RE.match(material.strip())
    return (m.group("standard"), m.group("size")) if m else None

def _build_candidate_config(material: str, resolver_cfg: dict) -> str | None:
    result = extract_full_spec(material)
    if result is None:
        return None
    standard, size = result
    for rule in resolver_cfg["standard_transforms"]:
        standard = standard.replace(rule["from"], rule["to"])
    for rule in resolver_cfg["size_transforms"]:
        size = size.replace(rule["from"], rule["to"])
    return f"{standard}{resolver_cfg['separator']}{size}"
    # 示例: "GB/T 70.1 M6×20" → "GB_T70.1-M6x20"
```

---

## 5. 各层具体改动

### 5.1 `sw_toolbox_catalog.py` — `SwToolboxPart` 新增字段

```python
@dataclass
class SwToolboxPart:
    standard: str
    subcategory: str
    sldprt_path: str
    filename: str
    tokens: list[str] = field(default_factory=list)
    target_config: str | None = None   # ← 新增（有默认值，向后兼容）
```

### 5.2 `adapters/parts/sw_toolbox_adapter.py` — `resolve()` 扩展

```python
# resolve() 中，步骤 7（构造缓存路径）之前插入：
resolver_cfg = self.config.get("config_name_resolver", {})
target_config = None
material = getattr(query, "material", "") or ""
if resolver_cfg and material:
    target_config = _build_candidate_config(material, resolver_cfg)
part.target_config = target_config

# 步骤 7：缓存路径含 config 后缀（config 可能含特殊字符，先 sanitize）
safe_config = re.sub(r'[^\w.\-]', '_', target_config) if target_config else ""
stem = Path(part.filename).stem
cache_stem = f"{stem}_{safe_config}" if safe_config else stem
step_abs = cache_root / part.standard / part.subcategory / (cache_stem + ".step")

# 步骤 9：COM 转换（原 bool 改为 int）
rc = session.convert_sldprt_to_step(part.sldprt_path, str(step_abs), target_config)
if rc == 5:
    log.warning("Toolbox config 未匹配 %s → 回退 bd_warehouse", target_config)
    return self._miss("config not found, fallback to bd_warehouse")
if rc != 0:
    return self._miss("COM convert failed")
```

### 5.3 `adapters/solidworks/sw_com_session.py` — 返回类型改为 int

```python
def convert_sldprt_to_step(
    self, sldprt_path, step_out, target_config: str | None = None
) -> int:
    """返回值: 0=成功, 5=config未找到（不计熔断）, 其他=真错误（计熔断）。"""
    ...
    rc = self._do_convert(sldprt_path, step_out, target_config)
    if rc == 0:
        self._consecutive_failures = 0
    elif rc != 5:           # exit 5 不触发熔断器
        self._consecutive_failures += 1
        if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            self._unhealthy = True
    return rc

def _do_convert(self, sldprt_path: str, step_out: str,
                target_config: str | None = None) -> int:
    ...
    cmd = [sys.executable, "-m", _WORKER_MODULE, sldprt_path, tmp_path]
    if target_config:
        cmd.append(target_config)
    ...
    # 返回 proc.returncode（不再转 bool）
    if proc.returncode == 5:
        self._cleanup_tmp(tmp_path)
        return 5
    if proc.returncode != 0:
        ...
        self._cleanup_tmp(tmp_path)
        return proc.returncode
    # validate + rename
    ...
    return 0
```

> **熔断器兼容性**：现有调用 `ok = session.convert_sldprt_to_step(...)` 在 `resolve()` 里只有这一处，B-16 修改后统一改为接收 int，向后兼容代价为 `sw_warmup` 中若有调用也需同步更新（见 §7 文件清单）。

### 5.4 `adapters/solidworks/sw_convert_worker.py` — argv[3] + `_resolve_config`

```python
# _convert() 签名不变，但 main() 传入 argv 后内部解析
def _convert(sldprt_path: str, tmp_out_path: str,
             target_config: str | None = None) -> int:
    ...
    # OpenDoc6 之后，SaveAs3 之前：
    if target_config:
        config_mgr = model.ConfigurationManager
        available = list(config_mgr.GetConfigurationNames())
        matched = _resolve_config(target_config, available)
        if matched is None:
            print(f"[B-16] config 未匹配: {target_config!r}", file=sys.stderr)
            print(f"[B-16] 可用列表: {available}", file=sys.stderr)
            return 5
        model.ShowConfiguration2(matched)
    ...

def _resolve_config(candidate: str, available: list[str]) -> str | None:
    lower_map = {n.lower(): n for n in available}
    if candidate.lower() in lower_map:
        return lower_map[candidate.lower()]
    def _norm(s: str) -> str:
        return re.sub(r'[-_\s]', '', s).lower()
    norm_map = {_norm(n): n for n in available}
    return norm_map.get(_norm(candidate))

def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3):   # ← 原 != 2，改为允许可选 argv[2]
        print("usage: ... <sldprt_path> <tmp_out_path> [config_name]", file=sys.stderr)
        return 64
    target_config = argv[2] if len(argv) == 3 else None
    return _convert(argv[0], argv[1], target_config)
```

**退出码契约（更新文件头注释）**：

| exit | 含义 |
|---|---|
| 0 | 成功 |
| 2 | OpenDoc6 失败 |
| 3 | SaveAs3 失败 |
| 4 | 未预期异常 |
| **5** | config 未找到（新增；调用方应回退，不计熔断） |
| 64 | 参数错误 |

---

## 6. 通知与报告

### 6.1 Console 警告

```python
log.warning("Toolbox config 未匹配 %s → 回退 bd_warehouse", target_config)
```

### 6.2 `ResolveReportRow.config_match`（`parts_resolver.py`）

`ResolveReportRow` 新增字段（有默认值，向后兼容）：

```python
@dataclass
class ResolveReportRow:
    bom_id: str
    name_cn: str
    matched_adapter: str
    attempted_adapters: list[str]
    status: str
    config_match: str = "n/a"   # ← 新增："matched" | "fallback" | "n/a"
```

`sw_toolbox_adapter.resolve()` 在返回 `ResolveResult` 前更新 `config_match`（通过 `ResolveResult.metadata` 携带，由 `parts_resolver.resolve_report()` 写入 row）：

```python
# ResolveResult.metadata 新增 key
metadata={"dims": dims, "match_score": score,
          "configuration": target_config or "<default>",
          "config_match": "matched" if target_config else "n/a"},
```

`sw_preflight/report.py`（而非 `adapters/reporting/`）的 HTML 模板追加 Config 列。

---

## 7. 改动文件清单

| 文件 | 改动 |
|---|---|
| `parts_library.default.yaml` | 新增 `solidworks_toolbox.config_name_resolver` 段 |
| `parts_library.yaml` | 同步（`dev_sync.py` 镜像） |
| `adapters/solidworks/sw_toolbox_catalog.py` | `SwToolboxPart` 新增 `target_config: str \| None = None` |
| `adapters/parts/sw_toolbox_adapter.py` | `extract_full_spec` + `_build_candidate_config` + `resolve()` 填充 `target_config` + 缓存路径含 config 后缀 + 接收 int rc + exit 5 处理 |
| `adapters/solidworks/sw_com_session.py` | `convert_sldprt_to_step()` 新增 `target_config` 参数 + 返回 int + exit 5 不计熔断；`_do_convert()` 传 argv[3] |
| `adapters/solidworks/sw_convert_worker.py` | `_convert()` 新增 `target_config` 参数 + `_resolve_config()` + `ShowConfiguration2` 调用 + exit 5；`main()` 支持 argv[2] + 文件头 exit code 注释更新 |
| `parts_resolver.py` | `ResolveReportRow.config_match: str = "n/a"` 新增字段；`to_dict()` 序列化同步 |
| `sw_preflight/report.py` | HTML 模板追加 Config 列（读 `config_match`） |
| `tests/test_sw_toolbox_adapter.py` | `extract_full_spec` 单测 + `_build_candidate_config` 单测 + exit 5 回退测试（mock `session.convert_sldprt_to_step` 返回 5） |
| `tests/test_sw_convert_worker.py` | `_patch_com` 扩展 `ConfigurationManager` mock + 3 个 config 切换测试 |
| `tests/test_sw_com_session.py` | exit 5 不计熔断测试 + `target_config` argv 传递测试 |

---

## 8. 测试验收标准

### 8.1 单元测试（无 COM）

**`extract_full_spec` + `_build_candidate_config`**：

| 输入 | 期望输出 |
|---|---|
| `"GB/T 70.1 M6×20"` | `"GB_T70.1-M6x20"` |
| `"GB/T 6170 M6"` | `"GB_T6170-M6"` |
| `"GB／T 70.1 M6×20"` | `"GB_T70.1-M6x20"`（全角斜杠） |
| `"6206"` | `None`（无标准前缀） |
| `""` | `None` |

**`_resolve_config`**：

| candidate | available | 期望 |
|---|---|---|
| `"GB_T70.1-M6x20"` | `["GB_T70.1-M6x10", "GB_T70.1-M6x20"]` | `"GB_T70.1-M6x20"` |
| `"GB-T70.1-M6x20"` | `["GB_T70.1-M6x20"]` | `"GB_T70.1-M6x20"`（模糊） |
| `"gb_t70.1-m6x20"` | `["GB_T70.1-M6x20"]` | `"GB_T70.1-M6x20"`（大小写） |
| `"GB_T70.1-M99x99"` | `["GB_T70.1-M6x20"]` | `None` |

### 8.2 Worker 测试（`_patch_com` 扩展）

```python
fake_config_mgr = mock.MagicMock()
fake_config_mgr.GetConfigurationNames.return_value = ["GB_T70.1-M6x10", "GB_T70.1-M6x20"]
fake_model.ConfigurationManager = fake_config_mgr
```

1. 精确匹配 → `ShowConfiguration2("GB_T70.1-M6x20")` 被调用，exit 0
2. 模糊匹配 → `ShowConfiguration2` 被调用，exit 0
3. 无匹配 → stderr 含可用列表，exit 5

### 8.3 `SwComSession` 测试

1. `convert_sldprt_to_step()` 调用 `_do_convert()` 时 cmd 含 `target_config`（验证 argv 正确）
2. worker exit 5 → `convert_sldprt_to_step()` 返回 5 且熔断计数不增加
3. worker exit 3 → 返回 3 且熔断计数 +1

### 8.4 Adapter 集成测试

- `resolve()` + mocked `session.convert_sldprt_to_step` 返回 5 → `_miss()` 被调用（不抛异常）
- `resolve()` 当 `material` 解析失败 → `target_config=None` → 缓存路径无 config 后缀（向后兼容）

### 8.5 手工验收

SW 2024 开启：
```bash
python cad_pipeline.py full --bom "D:\Work\cad-tests\04-末端执行机构设计.md"
```
检查 `sw_report.html` → Config 列至少一件显示"matched"，对应 STEP 文件几何尺寸符合 BOM 规格。
