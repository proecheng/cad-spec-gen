# A3 — parts_library routing 可观测性 + adapter 审计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 parts_library 路由系统新增运行时可观测性——`is_available()` 返回带原因的 tuple、`resolve()` 检查可用性、`resolve_report()` 输出 per-row 命中轨迹 JSON、`sw_report.html` 展示路由诊断区块。

**Architecture:** 三层改动——(1) `is_available()` 契约从 `-> bool` 升级为 `-> tuple[bool, Optional[str]]`，4 个 concrete adapter 实现，`SwToolboxAdapter` 签名跟上但 reason 留 Track B 填；(2) `PartsResolver.resolve()` 新增可选 `_trace` 列表收集 per-row 尝试记录，`resolve_report()` 利用它生成 `ResolveReport` dataclass 序列化到 `artifacts/{run_id}/resolve_report.json`；(3) `sw_report.html.j2` 新增 "Routing attempts" 区块，`emit_report()` 可选接收 `resolve_report` 参数。

**Tech Stack:** Python 3.11 stdlib (dataclasses/json/os) / pytest / Jinja2 / 现有 `adapters/parts/` + `parts_resolver.py` + `sw_preflight/report.py` 架构

> **范围外（已知）**：spec §5.2 C4.1 大 BOM 体积分档（≤200/200-1000/>1000 行三档截断逻辑）本 plan 不实现——当前项目 BOM ≤54 行，JSON 体积远未触发 10MB 上限；留技术债登记 #TD-A3-1。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `adapters/parts/base.py` | 修改 | `is_available()` 抽象方法签名 `→ tuple[bool, Optional[str]]` |
| `adapters/parts/bd_warehouse_adapter.py` | 修改 | 返回 `(False, "catalog not found: {path}")` 或 `(False, "import bd_warehouse failed: {exc}")` |
| `adapters/parts/step_pool_adapter.py` | 修改 | 返回 `(True, None)`（文件系统查找，始终可用） |
| `adapters/parts/partcad_adapter.py` | 修改 | 返回 `(False, "partcad.enabled=false in yaml")` + 修 3 处自调用 |
| `adapters/parts/jinja_primitive_adapter.py` | 修改 | 返回 `(True, None)` |
| `adapters/parts/sw_toolbox_adapter.py` | 修改 | 签名升级，reason 全返 `None`（Track B 填） |
| `parts_resolver.py` | 修改 | `available_adapter_names()` 适配新签名；`resolve()` 新增 `_trace` 参数；新增 `ResolveReport` / `AdapterHit` / `ResolveReportRow` dataclass；新增 `resolve_report(bom_rows)` |
| `codegen/gen_std_parts.py` | 修改 | `main()` 里调 `resolver.resolve_report()` 并写 `resolve_report.json` |
| `sw_preflight/report.py` | 修改 | `emit_report()` 新增可选 `resolve_report` 参数，传入 Jinja 上下文 |
| `sw_preflight/templates/sw_report.html.j2` | 修改 | 新增 "Routing attempts" 折叠区块 |
| `cad_pipeline.py` | 修改 | `sw-inspect` 子命令加 `--resolve-report` 标志 |
| `tests/test_parts_adapters.py` | 修改 | `is_available()` 断言改为解包 tuple |
| `tests/test_sw_toolbox_adapter.py` | 修改 | `is_available()` 断言改为解包 tuple |
| `tests/test_resolve_report.py` | 新增 | `resolve_report()` 单元测试 |

---

### Task 0: 创建分支

- [ ] **Step 1: 创建 feat 分支**

```bash
git checkout -b feat/a3-routing-audit
```

- [ ] **Step 2: 确认在正确目录**

```bash
git branch --show-current
```

Expected: `feat/a3-routing-audit`

---

### Task 1: RED — `is_available()` 新契约单元测试

**Files:**
- Test: `tests/test_parts_adapters.py`（在现有文件末尾追加 `class TestIsAvailableTupleContract`）

**Rationale:** 先写失败测试锁住新签名，后续 Task 2-7 逐步让测试变绿。

- [ ] **Step 1: 在 `tests/test_parts_adapters.py` 末尾追加以下类**

```python
# ─── is_available() tuple contract ────────────────────────────────────────


class TestIsAvailableTupleContract:
    """每个 concrete adapter 的 is_available() 必须返回 (bool, Optional[str])。"""

    def test_jinja_returns_tuple(self):
        ok, reason = JinjaPrimitiveAdapter().is_available()
        assert ok is True
        assert reason is None

    def test_step_pool_returns_tuple(self):
        ok, reason = StepPoolAdapter().is_available()
        assert ok is True
        assert reason is None

    def test_partcad_disabled_returns_false_with_reason(self):
        a = PartCADAdapter(config={})
        ok, reason = a.is_available()
        assert ok is False
        assert reason is not None
        assert "partcad" in reason.lower() or "enabled" in reason.lower()

    def test_partcad_enabled_returns_true(self):
        a = PartCADAdapter(config={"enabled": True})
        ok, reason = a.is_available()
        assert ok is True
        assert reason is None

    def test_bd_warehouse_missing_catalog_returns_false_with_reason(self, tmp_path):
        a = BdWarehouseAdapter(catalog_path=str(tmp_path / "nonexistent.yaml"))
        ok, reason = a.is_available()
        assert ok is False
        assert reason is not None
        assert "catalog" in reason.lower() or "bd_warehouse" in reason.lower()
```

- [ ] **Step 2: 确认 imports 包含需要的类（文件顶部已有 BdWarehouseAdapter, StepPoolAdapter, PartCADAdapter, JinjaPrimitiveAdapter）**

```bash
head -20 tests/test_parts_adapters.py
```

如果缺少某个 import，在文件顶部添加对应行。

- [ ] **Step 3: 运行测试确认 FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_adapters.py::TestIsAvailableTupleContract -v
```

Expected: 5 tests FAIL（`cannot unpack non-sequence bool`）

---

### Task 2: 更新 `adapters/parts/base.py` 抽象方法签名

**Files:**
- Modify: `adapters/parts/base.py`

- [ ] **Step 1: 修改抽象方法签名和 docstring**

将 `base.py:31-37` 的 `is_available` 方法替换为：

```python
    @abstractmethod
    def is_available(self) -> tuple[bool, Optional[str]]:
        """Return (available, reason_if_unavailable).

        available: True if this adapter can be used right now.
        reason_if_unavailable: human-readable string when available=False, else None.

        Should NOT import optional dependencies — use lightweight checks like
        catalog file existence or environment flags. The actual heavy import
        happens lazily inside resolve() / probe_dims().
        """
```

- [ ] **Step 2: 验证 mypy 通过（base 自身无实现，抽象方法只改签名）**

```bash
.venv/Scripts/python.exe -m mypy adapters/parts/base.py --ignore-missing-imports
```

Expected: no errors

---

### Task 3: 更新 `BdWarehouseAdapter.is_available()`

**Files:**
- Modify: `adapters/parts/bd_warehouse_adapter.py:75-77`

- [ ] **Step 1: 替换 is_available 实现**

将 `bd_warehouse_adapter.py:75-77` 替换为：

```python
    def is_available(self) -> tuple[bool, Optional[str]]:
        if not os.path.isfile(self.catalog_path):
            return False, f"catalog not found: {self.catalog_path}"
        if not self._try_load_catalog():
            return False, f"catalog parse error: {self.catalog_path}"
        try:
            import bd_warehouse  # noqa: F401
        except ImportError as exc:
            return False, f"import bd_warehouse failed: {exc}"
        return True, None
```

- [ ] **Step 2: 运行已有 BdWarehouseAdapter 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_adapters.py -k "BdWarehouse" -v
```

Expected: 所有原有测试 PASS（原 `assert a.is_available()` 断言会 FAIL —— Task 8 再修）

---

### Task 4: 更新 `StepPoolAdapter.is_available()`

**Files:**
- Modify: `adapters/parts/step_pool_adapter.py:75-77`

- [ ] **Step 1: 替换 is_available 实现**

将 `step_pool_adapter.py:75-77` 替换为：

```python
    def is_available(self) -> tuple[bool, Optional[str]]:
        """Always available — it's just filesystem lookups."""
        return True, None
```

---

### Task 5: 更新 `PartCADAdapter.is_available()` + 修 3 处自调用

**Files:**
- Modify: `adapters/parts/partcad_adapter.py:98-104, 107, 112, 157`

- [ ] **Step 1: 替换 is_available 实现**

将 `partcad_adapter.py:98-104` 替换为：

```python
    def is_available(self) -> tuple[bool, Optional[str]]:
        """Return (True, None) only if explicitly enabled in the registry.

        Does not import partcad — that would pull in a big dep chain to check.
        """
        if not self.config.get("enabled"):
            return False, "partcad.enabled=false in yaml"
        return True, None
```

- [ ] **Step 2: 修 `can_resolve()` 自调用（line 107）**

将 `can_resolve` 方法改为：

```python
    def can_resolve(self, query) -> bool:
        ok, _ = self.is_available()
        return ok
```

- [ ] **Step 3: 修 `resolve()` 自调用（line 112）**

将 `resolve` 方法开头的 `if not self.is_available():` 改为：

```python
        ok, _ = self.is_available()
        if not ok:
            return ResolveResult.miss()
```

- [ ] **Step 4: 修 `probe_dims()` 自调用（line 157）**

找到 `probe_dims` 里的 `if not self.is_available():` 并改为：

```python
        ok, _ = self.is_available()
        if not ok:
            return None
```

- [ ] **Step 5: 运行 PartCAD 相关测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_adapters.py -k "PartCAD" -v
```

Expected: 原有测试部分 PASS，`assert adapter.is_available()` 断言会 FAIL（Task 8 修）

---

### Task 6: 更新 `JinjaPrimitiveAdapter.is_available()`

**Files:**
- Modify: `adapters/parts/jinja_primitive_adapter.py:255-256`

- [ ] **Step 1: 替换 is_available 实现**

将 `jinja_primitive_adapter.py:255-256` 替换为：

```python
    def is_available(self) -> tuple[bool, Optional[str]]:
        return True, None
```

---

### Task 7: 更新 `SwToolboxAdapter.is_available()` 签名（reason 留 Track B）

**Files:**
- Modify: `adapters/parts/sw_toolbox_adapter.py:54-approx_100`

- [ ] **Step 1: 修改 is_available 方法签名并在每个 return False 前加 reason=None**

找到 `sw_toolbox_adapter.py` 中 `is_available` 方法（约 line 54），将其返回类型改为 `tuple[bool, Optional[str]]`，并将所有 `return False` 改为 `return False, None`，`return True` 改为 `return True, None`（保持 6 项检查逻辑不变）：

```python
    def is_available(self) -> tuple[bool, Optional[str]]:
        """v4 §5.3: 6 项检查全通过。reason 字段 Track B 填充。

        检查顺序（短路优先）：
        1. 非 Windows 平台 → False
        2. SolidWorks 未安装 → False
        3. 版本低于 2024 → False
        4. pywin32 不可用 → False
        5. Toolbox 目录为空 → False
        6. Toolbox Add-In 未启用 → False（v4 决策 #13）
        7. SwComSession 熔断 → False（v4 决策 #22）
        """
        if sys.platform != "win32":
            return False, None  # Track B 填 reason

        try:
            from adapters.solidworks.sw_detect import detect_solidworks
            from adapters.solidworks.sw_com_session import get_session
        except ImportError:
            return False, None

        info = detect_solidworks()
        # ... 保留原有所有判断逻辑，将每个 return False → return False, None
        # ... 将最终 return True → return True, None
```

> **注意**：逐行读取原 `is_available` 方法体，把所有裸 `return False` 替换成 `return False, None`，裸 `return True` 替换成 `return True, None`。不要改判断条件本身。

- [ ] **Step 2: 更新 `tests/test_sw_toolbox_adapter.py` 中所有 `is_available()` 断言**

每处 `assert a.is_available() is False` 改为：

```python
ok, _ = a.is_available()
assert ok is False
```

每处 `assert a.is_available() is True` 改为：

```python
ok, _ = a.is_available()
assert ok is True
```

- [ ] **Step 3: 运行 sw_toolbox 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sw_toolbox_adapter.py -v
```

Expected: 全部 PASS

---

### Task 8: 修复 `parts_resolver.py` 的调用点 + `test_parts_adapters.py` 中的旧断言

**Files:**
- Modify: `parts_resolver.py:150`
- Modify: `tests/test_parts_adapters.py`（`TestIsAvailableTupleContract` 以外的旧断言）

- [ ] **Step 1: 修 `available_adapter_names()`（parts_resolver.py:150）**

将 `parts_resolver.py:149-150` 替换为：

```python
    def available_adapter_names(self) -> list[str]:
        return [a.name for a, (ok, _) in
                ((a, a.is_available()) for a in self.adapters) if ok]
```

- [ ] **Step 2: 修 `test_parts_adapters.py` 中其余旧的 `is_available()` 断言**

在文件中搜索所有 `assert a.is_available()` 和 `assert not adapter.is_available()` 并改为：

```python
# assert a.is_available()  旧写法
ok, _ = a.is_available()
assert ok

# assert not adapter.is_available()  旧写法
ok, _ = adapter.is_available()
assert not ok
```

- [ ] **Step 3: 运行全量 adapter 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_adapters.py tests/test_sw_toolbox_adapter.py -v
```

Expected: 全部 PASS（含 Task 1 写的 `TestIsAvailableTupleContract` 5 条）

---

### Task 9: 添加 `ResolveReport` dataclass + `resolve_report()` + 修改 `resolve()` 加 trace

**Files:**
- Modify: `parts_resolver.py`

**Rationale:** `resolve()` 新增可选 `_trace: list[str] | None = None` 参数，内部记录每个 adapter 的尝试结果（`unavailable` / `miss` / `hit`）。`resolve_report()` 逐行调用 `resolve(_trace=row_trace)` 收集完整轨迹。

- [ ] **Step 1: 在 `parts_resolver.py` 顶部 import 区新增 dataclass import（若未有）**

确认文件顶部有：

```python
from dataclasses import dataclass, field
```

如无则在 `from __future__ import annotations` 之后添加。

- [ ] **Step 2: 在 `class PartsResolver` 定义前（约 line 112 附近）添加三个 dataclass**

```python
@dataclass
class AdapterHit:
    count: int
    unavailable_reason: Optional[str]


@dataclass
class ResolveReportRow:
    bom_id: str
    name_cn: str
    matched_adapter: str
    attempted_adapters: list[str]
    status: str  # "hit" | "fallback" | "miss"


@dataclass
class ResolveReport:
    schema_version: int = 1
    run_id: str = ""
    total_rows: int = 0
    adapter_hits: dict[str, AdapterHit] = field(default_factory=dict)
    rows: list[ResolveReportRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        """序列化为可 json.dump 的 dict（dataclass 嵌套不能直接 json.dumps）。"""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "total_rows": self.total_rows,
            "adapter_hits": {
                name: {"count": h.count, "unavailable_reason": h.unavailable_reason}
                for name, h in self.adapter_hits.items()
            },
            "rows": [
                {
                    "bom_id": r.bom_id,
                    "name_cn": r.name_cn,
                    "matched_adapter": r.matched_adapter,
                    "attempted_adapters": r.attempted_adapters,
                    "status": r.status,
                }
                for r in self.rows
            ],
        }
```

- [ ] **Step 3: 修改 `resolve()` 方法签名，添加 `_trace` 参数**

将 `resolve` 方法签名改为：

```python
    def resolve(self, query: PartQuery, _trace: list[str] | None = None) -> ResolveResult:
```

在方法体内，每次 adapter 处理时追加到 `_trace`（若非 None）：

在 `adapter = self._find_adapter(adapter_name)` 之后：

```python
            if adapter is None:
                self.log(f"  [resolver] rule matches {query.part_no} but "
                         f"adapter '{adapter_name}' not registered")
                if _trace is not None:
                    _trace.append(f"{adapter_name}(not_registered)")
                continue
            # ★ A3: check is_available() before calling resolve()
            _ok, _reason = adapter.is_available()
            if not _ok:
                self.log(f"  [resolver] adapter '{adapter_name}' unavailable"
                         + (f": {_reason}" if _reason else ""))
                if _trace is not None:
                    _trace.append(f"{adapter_name}(unavailable)")
                continue
```

在 `result = adapter.resolve(query, spec)` 成功返回后（`if result.status == "hit":` 块内）：

```python
                if _trace is not None:
                    _trace.append(f"{adapter_name}(hit)")
```

在 `continue` / fall-through（miss 情况）：

```python
            # result.status != "hit" — miss
            if _trace is not None:
                _trace.append(f"{adapter_name}(miss)")
```

在 Terminal fallback（`fallback = self._find_adapter("jinja_primitive")` 段）：

```python
        if fallback is not None:
            result = fallback.resolve(query, spec={})
            if result.status == "hit":
                result.status = "fallback"
                result.category = PartCategory.CUSTOM
                self._decision_log.append(
                    (query.part_no, "jinja_primitive", result.source_tag))
                if _trace is not None:
                    _trace.append("jinja_primitive(fallback)")
                return result
```

- [ ] **Step 4: 在 `PartsResolver` 类里添加 `resolve_report()` 实例方法（在 `coverage_report()` 之后）**

```python
    def resolve_report(
        self,
        bom_rows: list[dict],
        run_id: str = "",
    ) -> "ResolveReport":
        """动态跑完真实 resolve 后输出 per-row 命中轨迹。

        Args:
            bom_rows: 每行是含 part_no / name_cn 字段的 dict（parse_bom_tree 产出格式）。
            run_id:   可选 run 标识，写入 JSON 的 run_id 字段。
        """
        # 预先收集每个 adapter 的可用性（避免 per-row 重复调用）
        adapter_availability: dict[str, tuple[bool, str | None]] = {
            a.name: a.is_available() for a in self.adapters
        }

        report = ResolveReport(run_id=run_id, total_rows=len(bom_rows))

        # 初始化 adapter_hits（所有已注册 adapter）
        for name, (ok, reason) in adapter_availability.items():
            report.adapter_hits[name] = AdapterHit(
                count=0,
                unavailable_reason=None if ok else reason,
            )

        for row in bom_rows:
            part_no = row.get("part_no", "")
            name_cn = row.get("name_cn", "")

            query = PartQuery(  # PartQuery 在同文件定义，直接使用
                part_no=part_no,
                name_cn=name_cn,
                material=row.get("material", ""),
                category=row.get("category", ""),
                make_buy=row.get("make_buy", ""),
            )

            row_trace: list[str] = []
            result = self.resolve(query, _trace=row_trace)

            # 更新 adapter_hits 计数
            matched = result.adapter if result.status != "miss" else "jinja_primitive"
            if matched in report.adapter_hits:
                report.adapter_hits[matched].count += 1
            else:
                report.adapter_hits[matched] = AdapterHit(count=1, unavailable_reason=None)

            status: str
            if result.status == "hit":
                status = "hit"
            elif result.status == "fallback":
                status = "fallback"
            else:
                status = "miss"

            report.rows.append(ResolveReportRow(
                bom_id=part_no,
                name_cn=name_cn,
                matched_adapter=matched,
                attempted_adapters=row_trace,
                status=status,
            ))

        return report
```

- [ ] **Step 5: 运行现有 resolver 测试确认无回归**

```bash
.venv/Scripts/python.exe -m pytest tests/test_parts_library_integration.py tests/test_parts_adapters.py -v -m "not requires_solidworks"
```

Expected: 原有 PASS 不变（Task 1 的新 5 条已绿）

---

### Task 10: `gen_std_parts.py` — 调用 `resolve_report()` 并写 JSON

**Files:**
- Modify: `codegen/gen_std_parts.py`

**Rationale:** 在 `generate_std_part_files()` 执行后、`coverage_report()` 打印之后，调用 `resolver.resolve_report(parts)` 并将结果写到 `artifacts/{run_id}/resolve_report.json`。

- [ ] **Step 1: 在 `generate_std_part_files()` 函数里，`return generated, skipped` 之前，暴露 resolver 给调用方**

检查 `generate_std_part_files()` 的签名和返回值（当前返回 `(list, list)`）。改为也返回 resolver：

```python
def generate_std_part_files(
    spec_path: str,
    output_dir: str,
    mode: str = "scaffold",
) -> tuple[list, list, "PartsResolver"]:
    ...
    # 末尾原先是 return generated, skipped
    return generated, skipped, resolver
```

- [ ] **Step 2: 在 `main()` 里更新对 `generate_std_part_files()` 的调用**

将 `main()` 中 `generated, skipped = generate_std_part_files(...)` 改为：

```python
    generated, skipped, resolver = generate_std_part_files(spec_path, output_dir, mode=args.mode)
```

- [ ] **Step 3: 在 `main()` 里 `coverage_report()` 打印块之后，写 `resolve_report.json`**

在 `report = resolver.coverage_report()` 块之后，`emit_report` 调用之前，添加：

```python
    # ─── A3: resolve_report.json ───
    try:
        import json as _json
        from datetime import datetime as _dt
        _parts = parse_bom_tree(spec_path)
        _rr = resolver.resolve_report(_parts, run_id=run_id)
        _rr_path = _Path(f"./artifacts/{run_id}/resolve_report.json")
        _rr_path.parent.mkdir(parents=True, exist_ok=True)
        _rr_path.write_text(
            _json.dumps(_rr.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[gen_std_parts] Routing report → {_rr_path}")
    except Exception as _rr_exc:
        print(f"[gen_std_parts] resolve_report 生成跳过（{type(_rr_exc).__name__}: {_rr_exc}）")
    # ─── /A3 ───
```

> **注意**：`run_id` 已在 main() 顶部由 Task 30 代码定义（`run_id = datetime.now().strftime('%Y%m%d-%H%M%S')`）。若该变量不在作用域，从 `from datetime import datetime` + 同样格式创建。

- [ ] **Step 4: 确认改动不破坏 gen_std_parts 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -k "gen_std" -v
```

Expected: PASS

---

### Task 11: 新增 `tests/test_resolve_report.py`

**Files:**
- Create: `tests/test_resolve_report.py`

- [ ] **Step 1: 新建测试文件**

```python
"""tests/test_resolve_report.py — PartsResolver.resolve_report() 单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from parts_resolver import (
    PartsResolver,
    PartQuery,
    ResolveReport,
    ResolveReportRow,
    AdapterHit,
    load_registry,
)
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
from adapters.parts.partcad_adapter import PartCADAdapter


def _make_resolver(extra_adapters=None) -> PartsResolver:
    resolver = PartsResolver(registry={"mappings": []})
    resolver.register_adapter(JinjaPrimitiveAdapter())
    for a in (extra_adapters or []):
        resolver.register_adapter(a)
    return resolver


def _make_bom_rows(n: int = 3) -> list[dict]:
    return [
        {"part_no": f"P-00{i}", "name_cn": f"零件{i}", "material": "", "category": "bracket", "make_buy": "外购"}
        for i in range(1, n + 1)
    ]


class TestResolveReportBasic:
    def test_returns_resolve_report_instance(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(2)
        report = resolver.resolve_report(rows)
        assert isinstance(report, ResolveReport)

    def test_total_rows_matches_input(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(5)
        report = resolver.resolve_report(rows)
        assert report.total_rows == 5

    def test_rows_length_matches_input(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(3)
        report = resolver.resolve_report(rows)
        assert len(report.rows) == 3

    def test_all_fallback_to_jinja_when_no_rules(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(4)
        report = resolver.resolve_report(rows)
        for row in report.rows:
            assert row.status == "fallback"
            assert row.matched_adapter == "jinja_primitive"

    def test_run_id_preserved(self):
        resolver = _make_resolver()
        report = resolver.resolve_report([], run_id="test-run-42")
        assert report.run_id == "test-run-42"


class TestResolveReportAdapterHits:
    def test_jinja_primitive_hit_counted(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(3)
        report = resolver.resolve_report(rows)
        assert report.adapter_hits["jinja_primitive"].count == 3

    def test_unavailable_adapter_has_reason(self):
        resolver = _make_resolver(extra_adapters=[PartCADAdapter(config={})])
        rows = _make_bom_rows(2)
        report = resolver.resolve_report(rows)
        hit = report.adapter_hits.get("partcad")
        assert hit is not None
        assert hit.unavailable_reason is not None
        assert "enabled" in hit.unavailable_reason.lower()

    def test_available_adapter_has_no_reason(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(1)
        report = resolver.resolve_report(rows)
        assert report.adapter_hits["jinja_primitive"].unavailable_reason is None


class TestResolveReportSerialization:
    def test_to_dict_schema_version(self):
        resolver = _make_resolver()
        d = resolver.resolve_report([]).to_dict()
        assert d["schema_version"] == 1

    def test_to_dict_is_json_serializable(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(2)
        d = resolver.resolve_report(rows).to_dict()
        serialized = json.dumps(d)
        loaded = json.loads(serialized)
        assert loaded["total_rows"] == 2

    def test_rows_have_required_fields(self):
        resolver = _make_resolver()
        rows = _make_bom_rows(1)
        report = resolver.resolve_report(rows)
        r = report.rows[0]
        assert hasattr(r, "bom_id")
        assert hasattr(r, "name_cn")
        assert hasattr(r, "matched_adapter")
        assert hasattr(r, "attempted_adapters")
        assert hasattr(r, "status")
        assert r.status in ("hit", "fallback", "miss")
```

- [ ] **Step 2: 运行测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_resolve_report.py -v
```

Expected: 全部 PASS

- [ ] **Step 3: 提交 Task 1-11 的所有改动**

```bash
git add adapters/parts/base.py adapters/parts/bd_warehouse_adapter.py \
    adapters/parts/step_pool_adapter.py adapters/parts/partcad_adapter.py \
    adapters/parts/jinja_primitive_adapter.py adapters/parts/sw_toolbox_adapter.py \
    parts_resolver.py codegen/gen_std_parts.py \
    tests/test_parts_adapters.py tests/test_sw_toolbox_adapter.py \
    tests/test_resolve_report.py
git commit -m "feat(parts_resolver): A3 is_available() tuple 契约 + resolve_report() 运行时 JSON"
```

---

### Task 12: 扩展 `sw_report.html.j2` + `emit_report()` 传参

**Files:**
- Modify: `sw_preflight/report.py:31`
- Modify: `sw_preflight/templates/sw_report.html.j2`

- [ ] **Step 1: 修改 `emit_report()` 签名，新增可选 `resolve_report` 参数**

将 `sw_preflight/report.py:31-32` 改为：

```python
def emit_report(bom_rows: list[dict], dry_run: BomDryRunResult,
                preflight: PreflightResult, output_dir: Path,
                resolve_report=None) -> Path:
    """生成 sw_report.html + sw_report_data.json，返回 HTML 路径"""
```

- [ ] **Step 2: 在 `emit_report()` 里把 resolve_report 传入 Jinja 上下文**

找到 `tpl.render(...)` 调用（约 line 78），在 kwargs 里添加 `resolve_report=resolve_report.to_dict() if resolve_report is not None else None`：

```python
    html_content = tpl.render(
        ...existing_args...,
        resolve_report=resolve_report.to_dict() if resolve_report is not None else None,
    )
```

- [ ] **Step 3: 在 `sw_preflight/templates/sw_report.html.j2` 末尾（`</body>` 之前）添加 Routing 区块**

读取文件确认末尾结构，然后在 `</body>` 之前插入：

```html
{% if resolve_report %}
<section>
  <details>
    <summary><strong>Routing attempts</strong>（零件库路由诊断）</summary>
    <table>
      <tr><th>Adapter</th><th>命中数</th><th>不可用原因</th></tr>
      {% for name, hit in resolve_report.adapter_hits.items() %}
      <tr>
        <td>{{ name }}</td>
        <td>{{ hit.count }}</td>
        <td>{{ hit.unavailable_reason or '—' }}</td>
      </tr>
      {% endfor %}
    </table>
    <p>总行数: {{ resolve_report.total_rows }} | Run ID: {{ resolve_report.run_id }}</p>
  </details>
</section>
{% endif %}
```

- [ ] **Step 4: 在 `gen_std_parts.py::main()` 里把 `_rr` 传给 `emit_report()`**

找到 `_report_path = emit_report(_bom, _dry, preflight_result, _Path(...))` 这行，改为：

```python
        _report_path = emit_report(_bom, _dry, preflight_result, _Path(f'./artifacts/{run_id}'),
                                    resolve_report=_rr if '_rr' in dir() else None)
```

> **注意**：`_rr` 定义在外层 try 块，可能不在作用域。改用 `locals().get('_rr')` 更安全：

```python
        _resolve_report_obj = _rr if '_rr' in vars() else None
        _report_path = emit_report(_bom, _dry, preflight_result, _Path(f'./artifacts/{run_id}'),
                                    resolve_report=_resolve_report_obj)
```

- [ ] **Step 5: 运行 sw_preflight 相关测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -k "sw_preflight or report" -v -m "not requires_solidworks"
```

Expected: PASS（`resolve_report=None` 时 HTML 无新区块——向后兼容）

- [ ] **Step 6: 提交**

```bash
git add sw_preflight/report.py sw_preflight/templates/sw_report.html.j2 codegen/gen_std_parts.py
git commit -m "feat(sw_report): A3 routing 诊断区块注入 sw_report.html"
```

---

### Task 13: `sw-inspect --resolve-report` CLI 标志

**Files:**
- Modify: `cad_pipeline.py`（约 line 2987 的 `p_sw_inspect` argparser）
- Modify: `tools/sw_inspect.py`（`run_sw_inspect()` 函数）

- [ ] **Step 1: 在 `cad_pipeline.py` 里给 `p_sw_inspect` 加 `--resolve-report` 参数**

找到 `p_sw_inspect = sub.add_parser(...)` 之后的参数定义区（约 line 2991-3001），添加：

```python
    p_sw_inspect.add_argument(
        "--resolve-report",
        metavar="PATH",
        default=None,
        help="展示指定 resolve_report.json 的路由诊断摘要",
    )
```

- [ ] **Step 2: 在 `tools/sw_inspect.py::run_sw_inspect()` 里处理 `--resolve-report`**

在 `run_sw_inspect(args)` 函数开头，添加处理逻辑：

```python
def run_sw_inspect(args: argparse.Namespace) -> int:
    if getattr(args, "resolve_report", None):
        return _cmd_show_resolve_report(args.resolve_report)
    # ... 原有逻辑不变 ...
```

在同文件里添加 `_cmd_show_resolve_report()` 函数：

```python
def _cmd_show_resolve_report(path: str) -> int:
    """打印 resolve_report.json 的路由摘要。"""
    import json
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        print(f"[sw-inspect] resolve_report.json 不存在: {path}", file=sys.stderr)
        return 1

    data = json.loads(p.read_text(encoding="utf-8"))
    schema = data.get("schema_version", "?")
    if schema != 1:
        print(f"[sw-inspect] 未知 schema_version={schema}，仅展示原始字段")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"Routing report — run_id: {data.get('run_id', '?')} | "
          f"total_rows: {data.get('total_rows', '?')}")
    print()
    hits = data.get("adapter_hits", {})
    width = max((len(n) for n in hits), default=10)
    for name, hit in hits.items():
        reason = hit.get("unavailable_reason") or ""
        suffix = f"  ← {reason}" if reason else ""
        print(f"  {name:<{width}}  {hit['count']:>4} 命中{suffix}")
    return 0
```

- [ ] **Step 3: 冒烟测试（需要一个已存在的 resolve_report.json）**

```bash
echo '{"schema_version":1,"run_id":"test","total_rows":3,"adapter_hits":{"jinja_primitive":{"count":3,"unavailable_reason":null}},"rows":[]}' > /tmp/test_rr.json
.venv/Scripts/python.exe cad_pipeline.py sw-inspect --resolve-report /tmp/test_rr.json
```

Expected: 打印摘要行和 adapter 命中计数

- [ ] **Step 4: 提交**

```bash
git add cad_pipeline.py tools/sw_inspect.py
git commit -m "feat(sw_inspect): A3 --resolve-report 路由诊断 CLI 标志"
```

---

### CHECKPOINT — 全量测试 + PR

- [ ] **Step 1: 全量非 blender 非 SW 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -m "not blender and not requires_solidworks" -v 2>&1 | tail -20
```

Expected: 原有 PASS 保持；新增 `test_resolve_report.py` 全部 PASS；`TestIsAvailableTupleContract` 5 条 PASS

- [ ] **Step 2: ruff 检查**

```bash
.venv/Scripts/python.exe -m ruff check adapters/parts/ parts_resolver.py codegen/gen_std_parts.py sw_preflight/report.py tools/sw_inspect.py cad_pipeline.py
```

Expected: no errors

- [ ] **Step 3: push + 开 PR**

```bash
git push -u origin feat/a3-routing-audit
gh pr create --title "feat(parts_resolver): A3 routing 可观测性 + is_available() tuple 契约" \
  --body "$(cat <<'EOF'
## Summary
- `is_available()` 从 `-> bool` 升级为 `-> tuple[bool, Optional[str]]`，4 个 concrete adapter 实现具体原因
- `PartsResolver.resolve()` 新增可选 `_trace` 参数，记录 per-row adapter 尝试轨迹
- `resolve_report(bom_rows)` 新实例方法输出 `ResolveReport` → `artifacts/{run_id}/resolve_report.json`
- `sw_report.html` 新增 "Routing attempts" 折叠诊断区块
- `sw-inspect --resolve-report <path>` CLI 快速查看路由诊断
- `SwToolboxAdapter` 签名同步升级，reason 留 Track B 填充

## Test plan
- [ ] `tests/test_resolve_report.py` 14 条全绿
- [ ] `tests/test_parts_adapters.py::TestIsAvailableTupleContract` 5 条全绿
- [ ] `tests/test_sw_toolbox_adapter.py` 全部 PASS
- [ ] 全量非 SW 测试无回归

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
