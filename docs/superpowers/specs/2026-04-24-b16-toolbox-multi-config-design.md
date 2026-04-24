# B-16 — Toolbox 多规格件 ShowConfiguration2 设计规格

**版本**：v0.1  
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
| 匹配失败处理 | exit 5（新 exit code）→ 调用方回退 bd_warehouse；不抛异常 |
| 用户通知 | console `logger.warning` 每件一行 + `sw_report.html` Config 匹配列 |

---

## 3. 数据流

```
BOM 行
  "名称": "内六角螺栓"
  "材质/型号": "GB/T 70.1 M6×20"
        │
        ▼
parts_resolver.py → PartQuery(name_cn="内六角螺栓", material="GB/T 70.1 M6×20")
        │
        ▼
sw_toolbox_adapter.py
  ├─ extract_full_spec(material) → standard="GB/T 70.1", size="M6×20"
  └─ _build_candidate_config(standard, size, resolver_cfg) → "GB_T70.1-M6x20"
        │
        ▼
SwToolboxPart(sldprt_path=..., target_config="GB_T70.1-M6x20")  ← 新增字段
        │
        ▼
sw_convert_worker.py  subprocess argv[3] = "GB_T70.1-M6x20"（可选）
  ├─ OpenDoc6(sldprt_path)
  ├─ GetConfigurationNames() → ["GB_T70.1-M6x10", "GB_T70.1-M6x20", ...]
  ├─ _resolve_config(candidate, available)
  │   ├─ 精确匹配（大小写不敏感）→ ShowConfiguration2(matched) ✓
  │   ├─ 模糊匹配（去 -_/ 空格）→ ShowConfiguration2(matched) ✓
  │   └─ 无匹配 → stderr 输出可用列表 → sys.exit(5)
  ├─ SaveAs3(step_out_path)
  └─ CloseDoc(model.GetPathName())
        │
        ▼
sw_toolbox_adapter.py
  ├─ exit 0 → STEP 路径 ✓
  ├─ exit 5 → logger.warning → return None → bd_warehouse 回退
  └─ exit 其他 → 已有 WorkerError 逻辑不变
```

---

## 4. yaml 配置结构

追加到 `parts_library.default.yaml`（同步到 `parts_library.yaml`）：

```yaml
solidworks_toolbox:
  # 已有字段不动
  size_patterns:
    fastener:
      size: '[Mm](\d+(?:\.\d+)?)'

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

### 4.1 候选名生成逻辑

```python
# sw_toolbox_adapter.py 新增
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

## 5. Worker 协议变更

### 5.1 subprocess 调用

```python
# sw_toolbox_adapter.py — _run_worker() 扩展
cmd = [sys.executable, worker_path, sldprt_path, step_out_path]
if target_config:
    cmd.append(target_config)
result = subprocess.run(cmd, capture_output=True, text=True)
```

### 5.2 Worker 内 config 切换

```python
# sw_convert_worker.py — OpenDoc6 之后，SaveAs3 之前
target_config = sys.argv[3] if len(sys.argv) > 3 else None

if target_config:
    config_mgr = model.ConfigurationManager
    available = list(config_mgr.GetConfigurationNames())
    matched = _resolve_config(target_config, available)
    if matched is None:
        print(f"[B-16] config 未匹配: {target_config!r}", file=sys.stderr)
        print(f"[B-16] 可用列表: {available}", file=sys.stderr)
        sys.exit(5)
    model.ShowConfiguration2(matched)
```

### 5.3 `_resolve_config()` 实现

```python
def _resolve_config(candidate: str, available: list[str]) -> str | None:
    # 精确匹配（大小写不敏感）
    lower_map = {n.lower(): n for n in available}
    if candidate.lower() in lower_map:
        return lower_map[candidate.lower()]
    # 模糊匹配（去连字符/下划线/空格）
    def _norm(s: str) -> str:
        return re.sub(r'[-_\s]', '', s).lower()
    norm_map = {_norm(n): n for n in available}
    return norm_map.get(_norm(candidate))
```

### 5.4 调用方 exit 5 处理

```python
# sw_toolbox_adapter.py — find_sldprt() 内
rc = _run_worker(sldprt_path, step_out_path, target_config)
if rc == 5:
    logger.warning("Toolbox config 未匹配 %s → 回退 bd_warehouse", target_config)
    routing_entry.config_match = "fallback"   # RoutingEntry 由调用方传入
    return None   # 上层 resolver 已有 None → bd_warehouse 回退路径
if rc != 0:
    raise WorkerError(rc)
# 成功
routing_entry.config_match = "matched" if target_config else "n/a"
```

### 5.5 exit code 约定（更新 worker 文件头注释）

| exit | 含义 |
|---|---|
| 0 | 成功，STEP 已写出 |
| 1 | COM/SW 错误 |
| 2 | 文件不存在 |
| **5** | config 未找到（新增；调用方应回退，非硬错误） |

---

## 6. 通知与报告

### 6.1 Console 警告

每个未匹配件：
```
WARNING  sw_toolbox: Toolbox config 未匹配 'GB_T70.1-M99x99' → 回退 bd_warehouse
```

### 6.2 sw_report.html 新增列

延用 A3 `ResolveReport` 机制，`resolve_report()` 中 `RoutingEntry` 新增字段：

```python
@dataclass
class RoutingEntry:
    ...
    config_match: str  # "matched", "fallback", "n/a"
```

HTML routing 区块新增 "Config" 列，显示匹配状态。

---

## 7. 改动文件清单

| 文件 | 改动 |
|---|---|
| `parts_library.default.yaml` | 新增 `solidworks_toolbox.config_name_resolver` 段 |
| `parts_library.yaml` | 同步新增（`dev_sync.py` 镜像） |
| `adapters/solidworks/sw_toolbox_adapter.py` | `extract_full_spec` + `_build_candidate_config` + `SwToolboxPart.target_config` + `find_sldprt` 填充 + `_run_worker` argv 扩展 + exit 5 处理 |
| `adapters/solidworks/sw_convert_worker.py` | argv[3] 读取 + `_resolve_config` + `ShowConfiguration2` 调用 + exit 5 + 文件头 exit code 注释 |
| `adapters/reporting/sw_report.py` | `RoutingEntry.config_match` + HTML 列渲染 |
| `tests/test_sw_toolbox_adapter.py` | `extract_full_spec` 单测 + `_build_candidate_config` 单测 + exit 5 回退测试 |
| `tests/test_sw_convert_worker.py` | `_patch_com` 扩展 `ConfigurationManager` mock + 3 个 config 切换测试 |

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

### 8.3 Adapter 集成测试

- `find_sldprt()` + mocked worker exit 5 → 返回 `None`（触发 bd_warehouse 路径）
- `find_sldprt()` material 解析失败 → `target_config=None` → 不传 argv[3]，worker 跳过切换

### 8.4 手工验收

SW 2024 开启：
```bash
python cad_pipeline.py full --bom "D:\Work\cad-tests\04-末端执行机构设计.md"
```
检查 `sw_report.html` → Config 列至少一件显示"matched"。
