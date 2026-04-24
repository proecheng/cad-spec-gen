# B-16 — Toolbox 多规格件 ShowConfiguration2 设计规格

**版本**：v0.3（方法路径 / 边界 / 通用性 / 硬编码二轮审查后修正）  
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

### 1.3 已知限制

- `_SPEC_RE` 正则仅覆盖 `GB/T`、`ISO`、`DIN`、`JIS` 格式；`GB 93`（弹垫、无 `/T`）等老标准无法解析 → `target_config=None` → 使用默认 config，不报错。
- `sw-warmup` 批量预热使用默认 config 路径；B-16 的 config-specific STEP 路径在预热时不被写入，首次 `resolve()` 必走 live COM。此为第一版已知限制，未来可单独迭代 config-aware warmup。

---

## 2. 设计决策

| 问题 | 决策 |
|---|---|
| Config 名解析方式 | 混合：yaml 标准化 → candidate；worker 用 `GetConfigurationNames()` 验证/回退 |
| 覆盖范围 | 全部三类（螺栓/螺钉 + 轴承/销 + 螺母/垫圈），螺母/垫圈 best-effort 回退 |
| 匹配失败处理 | worker exit 5 → `SwComSession` 通过 `_set_diag("config_not_found")` 传递信号（不改公共 API 返回类型）；不计入熔断器；调用方检 stage 字符串回退 bd_warehouse |
| 用户通知 | console `logger.warning` 每件一行 + `sw_report.html` Config 匹配明细区块（新增行级表格） |

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
  ├─ 新增：part.target_config = "GB_T70.1-M6x20"  （SwToolboxPart 新字段）
  └─ 新增：缓存路径含 config 后缀
       step_abs = cache_root / "GB" / "bolts and studs" / "GB_T70-1_GB_T70.1-M6x20.step"
        │
        ▼ 缓存未命中
adapters/solidworks/sw_com_session.py  SwComSession.convert_sldprt_to_step()
  ├─ 新增参数：target_config: str | None = None
  ├─ 返回类型：bool（不变，向后兼容）
  ├─ 内部 _do_convert() 返回 int（私有，不影响公共 API）
  │   └─ cmd = [python, -m, adapters.solidworks.sw_convert_worker,
  │             sldprt_path, tmp_path, target_config]  ← argv[3] 可选
  └─ exit 5 → _set_diag("config_not_found", 5, ...) → return False（不计熔断）
        │
        ▼
adapters/solidworks/sw_convert_worker.py  _convert()
  ├─ target_config = argv[2] if len(argv) > 2 else None
  ├─ OpenDoc6(sldprt_path)
  ├─ GetConfigurationNames() → ["GB_T70.1-M6x10", "GB_T70.1-M6x20", ...]
  ├─ _resolve_config(target_config, available)
  │   ├─ 精确匹配（大小写不敏感）→ ShowConfiguration2(matched) ✓ → SaveAs3
  │   ├─ 模糊匹配（去 -_/ 空格后比较）→ ShowConfiguration2(matched) ✓ → SaveAs3
  │   └─ 无匹配 → stderr 输出可用列表 → return 5
  └─ CloseDoc / ExitApp（已有）
        │
        ▼
sw_toolbox_adapter.resolve()
  ├─ ok == True → 返回 ResolveResult(status="hit", metadata={"config_match":"matched",...})
  ├─ ok == False + stage=="config_not_found" → logger.warning → _miss() with config_match="fallback"
  └─ ok == False + 其他 → _miss("COM convert failed")（已有逻辑）
        │
        ▼
parts_resolver.resolve_report()  （line 450）
  └─ ResolveReportRow(..., config_match=result.metadata.get("config_match","n/a"))
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

> DIN/JIS 无专用 standard_transform，但最末的 `{from: " ", to: ""}` 规则会把空格去掉，模糊匹配兜底。

### 4.1 BOM material 字段解析

```python
# adapters/parts/sw_toolbox_adapter.py 新增（模块级）
import re

_SPEC_RE = re.compile(
    r'^(?P<standard>(?:GB[/／]T|ISO|DIN|JIS)\s*[\d.]+(?:\s+Part\s+\d+)?)'
    r'\s+(?P<size>.+)$'
)
# 已知不覆盖：GB 93（弹垫无 /T）、ANSI 等 → target_config=None → 使用默认 config

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

### 5.1 `adapters/solidworks/sw_toolbox_catalog.py` — `SwToolboxPart` 新增字段

```python
@dataclass
class SwToolboxPart:
    standard: str
    subcategory: str
    sldprt_path: str
    filename: str
    tokens: list[str] = field(default_factory=list)
    target_config: str | None = None   # ← 新增（默认 None，向后兼容 JSON 反序列化 **p）
```

JSON 缓存反序列化使用 `SwToolboxPart(**p)`（`sw_toolbox_catalog.py:630`），旧缓存文件无此字段时 `None` 默认值自动填充，无需缓存 invalidation。

### 5.2 `adapters/parts/sw_toolbox_adapter.py` — `resolve()` 扩展

```python
# resolve() 步骤 6（路径校验）之后，步骤 7（构造缓存路径）之前插入：
resolver_cfg = self.config.get("config_name_resolver", {})
material = getattr(query, "material", "") or ""
target_config = _build_candidate_config(material, resolver_cfg) if resolver_cfg else None
part.target_config = target_config

# 步骤 7：缓存路径含 config 后缀（无 target_config 时行为不变）
safe_config = re.sub(r'[^\w.\-]', '_', target_config) if target_config else ""
cache_stem = f"{Path(part.filename).stem}_{safe_config}" if safe_config else Path(part.filename).stem
step_abs = cache_root / part.standard / part.subcategory / (cache_stem + ".step")

# 步骤 8：缓存命中检查（不变，路径已含 config 后缀）
if step_abs.exists():
    ...  # 已有逻辑

# 步骤 9：COM 转换
ok = session.convert_sldprt_to_step(part.sldprt_path, str(step_abs), target_config)
if not ok:
    stage = (session.last_convert_diagnostics or {}).get("stage", "")
    if stage == "config_not_found":
        log.warning("Toolbox config 未匹配 %s → 回退 bd_warehouse", target_config)
        return ResolveResult(
            status="miss", kind="miss", adapter=self.name,
            metadata={"config_match": "fallback"},
            warnings=[f"config not found: {target_config}"],
        )
    return self._miss("COM convert failed")

# 成功：metadata 含 config_match
dims = self._probe_step_bbox(step_abs)
return ResolveResult(
    status="hit", kind="step_import", adapter=self.name,
    step_path=str(step_abs), real_dims=dims,
    source_tag=f"sw_toolbox:{part.standard}/{part.subcategory}/{part.filename}",
    metadata={
        "dims": dims,
        "match_score": score,
        "configuration": target_config or "<default>",
        "config_match": "matched" if target_config else "n/a",
    },
)
```

### 5.3 `adapters/solidworks/sw_com_session.py` — 保持 `-> bool`，内部 `_do_convert` 改为 `-> int`

**公共 API 不变**，保留 `convert_sldprt_to_step() -> bool`，内部通过 `_set_diag` 传递 exit 5 信号。

```python
# 新增模块级常量（避免硬编码字符串散落各处）
_STAGE_CONFIG_NOT_FOUND = "config_not_found"

def convert_sldprt_to_step(
    self, sldprt_path, step_out, target_config: str | None = None
) -> bool:
    """保持 -> bool 兼容现有调用（sw_warmup.py:326/385 无需修改）。
    exit 5 (config_not_found) 通过 last_convert_diagnostics["stage"] 传递给调用方。
    """
    sldprt_path = str(os.fspath(sldprt_path))
    step_out = str(os.fspath(step_out))

    with self._lock:
        self._last_convert_diagnostics = None
        if self._unhealthy:
            self._set_diag("circuit_breaker_open", None, "")
            return False

        try:
            rc = self._do_convert(sldprt_path, step_out, target_config)  # int
        except Exception as e:
            self._set_diag("unexpected_exception", None, f"{type(e).__name__}: {e}"[:500])
            rc = 4

        if rc == 0:
            self._consecutive_failures = 0
            return True
        if rc == 5:
            # config_not_found 不是 COM 错误，不计入熔断器
            # _do_convert 已调用 _set_diag("config_not_found", 5, ...)
            return False
        # 真错误：计入熔断器
        self._consecutive_failures += 1
        if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            self._unhealthy = True
        return False

def _do_convert(self, sldprt_path: str, step_out: str,
                target_config: str | None = None) -> int:
    """返回 int exit code（私有 API；0=成功, 5=config未找到, 其他=错误）。"""
    tmp_path = str(Path(step_out).with_suffix(".tmp.step"))
    Path(step_out).parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", _WORKER_MODULE, sldprt_path, tmp_path]
    if target_config:
        cmd.append(target_config)

    try:
        proc = subprocess.run(
            cmd, timeout=SINGLE_CONVERT_TIMEOUT_SEC,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", cwd=str(_PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        self._set_diag("timeout", None, "")
        self._cleanup_tmp(tmp_path)
        return 1  # 非 5，计熔断

    stderr = (proc.stderr or "")[:500]
    if proc.returncode == 5:
        self._set_diag(_STAGE_CONFIG_NOT_FOUND, 5, stderr)
        self._cleanup_tmp(tmp_path)
        return 5

    if proc.returncode != 0:
        self._set_diag("subprocess_error", proc.returncode, stderr)
        self._cleanup_tmp(tmp_path)
        return proc.returncode

    if not self._validate_step_file(tmp_path):
        self._set_diag("validation_failure", proc.returncode, stderr)
        self._cleanup_tmp(tmp_path)
        return 3  # 非 5，计熔断

    self._set_diag("success", 0, stderr)
    os.replace(tmp_path, step_out)
    return 0
```

> **向后兼容**：`sw_warmup.py:326` 的 `ok = session.convert_sldprt_to_step(...)` 和 line 385 的 `success = session.convert_sldprt_to_step(...)` 无需修改——`-> bool` 保持不变，`tools/sw_warmup.py` 不在本次改动范围内。

### 5.4 `adapters/solidworks/sw_convert_worker.py` — argv[2] + `_resolve_config`

```python
# 模块级新增（OpenDoc6 成功后，SaveAs3 前调用）
import re as _re  # 文件已有 sys，此处补 re

def _resolve_config(candidate: str, available: list[str]) -> str | None:
    """两步匹配：精确（大小写不敏感）→ 模糊（去 -_/ 空格）。"""
    lower_map = {n.lower(): n for n in available}
    if candidate.lower() in lower_map:
        return lower_map[candidate.lower()]

    def _norm(s: str) -> str:
        return _re.sub(r'[-_\s]', '', s).lower()

    norm_map = {_norm(n): n for n in available}
    return norm_map.get(_norm(candidate))


# _convert() 新增 target_config 参数
def _convert(sldprt_path: str, tmp_out_path: str,
             target_config: str | None = None) -> int:
    ...
    # OpenDoc6 成功后，SaveAs3 之前插入：
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

# main() 支持可选 argv[2]
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3):   # 原 != 2
        print(
            "usage: python -m adapters.solidworks.sw_convert_worker "
            "<sldprt_path> <tmp_out_path> [config_name]",
            file=sys.stderr,
        )
        return 64
    target_config = argv[2] if len(argv) == 3 else None
    return _convert(argv[0], argv[1], target_config)
```

**文件头 exit code 注释更新**：

| exit | 含义 |
|---|---|
| 0 | 成功 |
| 2 | OpenDoc6 失败 |
| 3 | SaveAs3 失败 |
| 4 | 未预期异常 |
| **5** | config 未找到（新增；调用方 stage="config_not_found"，不计熔断） |
| 64 | 参数错误 |

### 5.5 `parts_resolver.py` — `ResolveReportRow.config_match` + 序列化

```python
@dataclass
class ResolveReportRow:
    bom_id: str
    name_cn: str
    matched_adapter: str
    attempted_adapters: list[str]
    status: str
    config_match: str = "n/a"   # ← 新增；"matched" | "fallback" | "n/a"
```

`to_dict()` 的 rows 列表补上 `config_match`：
```python
"rows": [
    {
        "bom_id": r.bom_id,
        "name_cn": r.name_cn,
        "matched_adapter": r.matched_adapter,
        "attempted_adapters": r.attempted_adapters,
        "status": r.status,
        "config_match": r.config_match,   # ← 新增
    }
    for r in self.rows
],
```

`resolve_report()` line 450 构造行时补上 `config_match`：
```python
report.rows.append(ResolveReportRow(
    bom_id=part_no,
    name_cn=name_cn,
    matched_adapter=matched,
    attempted_adapters=row_trace,
    status=status,
    config_match=(result.metadata or {}).get("config_match", "n/a"),   # ← 新增
))
```

---

## 6. 通知与报告

### 6.1 Console 警告

```python
log.warning("Toolbox config 未匹配 %s → 回退 bd_warehouse", target_config)
```

### 6.2 `sw_preflight/templates/sw_report.html.j2` — 新增行级表格

现有模板在 `{% if resolve_report %}` 区块内只渲染 `adapter_hits` 摘要，不渲染 rows。
B-16 在该区块内追加：

```jinja2
{% if resolve_report and resolve_report.rows %}
<div class="section">
  <div class="section-head">Config 匹配明细 ({{ resolve_report.rows|length }} 行)</div>
  <table style="width:100%;border-collapse:collapse;font-size:.9em;">
    <tr style="text-align:left;background:#f4f4f4;">
      <th style="padding:.3em .6em;">零件名</th>
      <th>Adapter</th>
      <th>Config 匹配</th>
      <th>状态</th>
    </tr>
    {% for row in resolve_report.rows %}
    <tr style="border-top:1px solid #eee;">
      <td style="padding:.3em .6em;">{{ row.name_cn }}</td>
      <td>{{ row.matched_adapter }}</td>
      <td class="{{ 'ok' if row.config_match=='matched' else 'warn' if row.config_match=='fallback' else '' }}">
        {{ row.config_match }}</td>
      <td>{{ row.status }}</td>
    </tr>
    {% endfor %}
  </table>
</div>
{% endif %}
```

`sw_preflight/report.py` 的 `emit_report()` 无需修改——已通过 `resolve_report.to_dict()` 将 rows 传给模板。

---

## 7. 改动文件清单

| 文件 | 改动 |
|---|---|
| `parts_library.default.yaml` | 新增 `solidworks_toolbox.config_name_resolver` 段 |
| `parts_library.yaml` | 同步（`dev_sync.py` 镜像） |
| `adapters/solidworks/sw_toolbox_catalog.py` | `SwToolboxPart` 新增 `target_config: str \| None = None` |
| `adapters/parts/sw_toolbox_adapter.py` | 模块级 `_SPEC_RE`/`extract_full_spec`/`_build_candidate_config`；`resolve()` 填充 `target_config`、config-aware 缓存路径、exit 5 stage 检查 |
| `adapters/solidworks/sw_com_session.py` | `convert_sldprt_to_step()` 新增 `target_config` 参数（保持 `-> bool`）；`_do_convert()` 改为 `-> int` + argv[3] + exit 5 → `_set_diag("config_not_found")`；新增模块常量 `_STAGE_CONFIG_NOT_FOUND` |
| `adapters/solidworks/sw_convert_worker.py` | `_resolve_config()`；`_convert()` 新增 `target_config` 参数 + `ShowConfiguration2` 调用 + exit 5；`main()` 支持 argv[2]；文件头 exit code 注释更新 |
| `parts_resolver.py` | `ResolveReportRow.config_match: str = "n/a"`；`to_dict()` 补 `config_match`；`resolve_report()` line 450 补 `config_match` kwarg |
| `sw_preflight/templates/sw_report.html.j2` | 在 `resolve_report` 区块内追加 Config 匹配明细表格 |
| `tests/test_sw_toolbox_adapter.py` | `extract_full_spec`/`_build_candidate_config` 单测；exit 5 stage 检查路径测试（mock `session.convert_sldprt_to_step` 返回 False + 设 diagnostics） |
| `tests/test_sw_convert_worker.py` | `_patch_com` 扩展 `ConfigurationManager` mock + 3 个 config 切换测试 |
| `tests/test_sw_com_session.py` | exit 5 不计熔断测试；`target_config` 追加到 cmd 测试；`_do_convert` 返回 5 → stage="config_not_found" 测试 |

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

1. `_convert("...", "...", "GB_T70.1-M6x20")` → `ShowConfiguration2("GB_T70.1-M6x20")` 被调用，exit 0
2. `_convert("...", "...", "GB-T70.1-M6x20")` → 模糊匹配后 `ShowConfiguration2` 被调用，exit 0
3. `_convert("...", "...", "GB_T70.1-M99x99")` → stderr 含可用列表，exit 5

### 8.3 `SwComSession` 测试

```python
# 1. exit 5 不计熔断
session = SwComSession()
with mock.patch.object(session, "_do_convert", return_value=5):
    ok = session.convert_sldprt_to_step("a.sldprt", "a.step", "GB_T70.1-M6x20")
assert ok is False
assert session._consecutive_failures == 0
assert session.last_convert_diagnostics["stage"] == "config_not_found"

# 2. exit 5 三次不开熔断
for _ in range(3):
    with mock.patch.object(session, "_do_convert", return_value=5):
        session.convert_sldprt_to_step("a.sldprt", "a.step", "GB_T70.1-M6x20")
assert session.is_healthy() is True

# 3. target_config 追加到 cmd
with mock.patch("subprocess.run") as mock_run:
    mock_run.return_value.returncode = 0
    mock_run.return_value.stderr = ""
    with mock.patch.object(session, "_validate_step_file", return_value=True):
        session.convert_sldprt_to_step("a.sldprt", "a.step", "GB_T70.1-M6x20")
cmd = mock_run.call_args[0][0]
assert cmd[-1] == "GB_T70.1-M6x20"
```

### 8.4 Adapter 集成测试

```python
# exit 5 stage → _miss() 而非异常
adapter = SwToolboxAdapter(config={...})
with mock.patch.object(session, "convert_sldprt_to_step", return_value=False):
    with mock.patch.object(session, "last_convert_diagnostics",
                           new_callable=mock.PropertyMock,
                           return_value={"stage": "config_not_found"}):
        result = adapter.resolve(query, spec)
assert result.status == "miss"
assert "config not found" in result.warnings[0]
```

### 8.5 手工验收

SW 2024 开启：
```bash
python cad_pipeline.py full --bom "D:\Work\cad-tests\04-末端执行机构设计.md"
```
检查 `sw_report.html` → Config 匹配明细区块至少一件显示"matched"，对应 STEP 几何尺寸符合 BOM 规格。
