# cable intentional-skip 状态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `cable`（线缆/拖链）等无法参数化建模的类别新增 `skip` 状态，使 resolve_report 将其显示为"有意跳过"而非"未命中"，覆盖率从 52/54 提升到 54/54（含 2 项 intentional-skip 注记）。

**Architecture:** 在 `ResolveResult.status` 中新增第四种状态 `"skip"`，由 `jinja_primitive` 在遇到 `_SKIP_CATEGORIES`（fastener/cable）时返回；`resolve()` 的兜底路径传递此状态；`resolve_report()` 将 skip 单独计入 `(skip)` 桶；`gen_std_parts` / `cad_spec_gen` 已有的 `miss` 分支扩展到同时覆盖 `skip`。

**Tech Stack:** Python 3.11+, pytest, ruff；无新依赖。

---

## 文件变更矩阵

| 文件 | 操作 | 职责 |
|---|---|---|
| `parts_resolver.py` | Modify | 扩展 ResolveKind/status Literal；新增 skip() 工厂；resolve() 传递 skip；resolve_report() 计 skip |
| `adapters/parts/jinja_primitive_adapter.py` | Modify | _SKIP_CATEGORIES → 返回 skip 而非 miss |
| `codegen/gen_std_parts.py` | Modify | skip 状态 continue（不生成代码） |
| `cad_spec_gen.py` | Modify | skip 状态 continue |
| `sw_preflight/templates/sw_report.html.j2` | Modify | skip 状态显示灰色样式 |
| `tests/test_parts_adapters.py` | Modify | fastener skip 断言更新 |
| `tests/test_resolve_report.py` | Modify | 更新 status 枚举断言 + 新增 skip 测试类 |

---

## Task 1：扩展 ResolveResult — 新增 skip 状态和工厂方法

**Files:**
- Modify: `parts_resolver.py:71` (ResolveKind)
- Modify: `parts_resolver.py:86` (ResolveResult.status)
- Modify: `parts_resolver.py:103-108` (ResolveResult.miss 下方)
- Modify: `parts_resolver.py:250-267` (resolve() 终端 fallback)

- [ ] **Step 1：写失败测试（skip 工厂方法）**

在 `tests/test_resolve_report.py` 文件末尾追加：

```python
class TestResolveResultSkip:
    def test_skip_factory_status(self):
        from parts_resolver import ResolveResult
        r = ResolveResult.skip(reason="cable not modeled")
        assert r.status == "skip"

    def test_skip_factory_kind_is_miss(self):
        from parts_resolver import ResolveResult
        r = ResolveResult.skip()
        assert r.kind == "miss"

    def test_skip_reason_in_source_tag(self):
        from parts_resolver import ResolveResult
        r = ResolveResult.skip(reason="fastener category")
        assert "fastener" in r.source_tag
```

- [ ] **Step 2：运行测试确认失败**

```
uv run pytest tests/test_resolve_report.py::TestResolveResultSkip -v
```

期望：FAIL — `AttributeError: type object 'ResolveResult' has no attribute 'skip'`

- [ ] **Step 3：实现 skip 状态扩展**

在 `parts_resolver.py` 中：

1. 第 71 行 ResolveKind 改为：
```python
ResolveKind = Literal["codegen", "step_import", "python_import", "miss", "skip"]
```

2. 第 86 行 ResolveResult.status 改为：
```python
status: Literal["hit", "miss", "fallback", "skip"]
```

3. 在 `ResolveResult.miss()` classmethod **之后**添加：
```python
    @classmethod
    def skip(cls, reason: str = "") -> "ResolveResult":
        return cls(
            status="skip",
            kind="miss",
            adapter="",
            category=PartCategory.CUSTOM,
            source_tag=reason,
        )
```

4. 在 `resolve()` 的终端 fallback 块（大约 250-267 行）找到：
```python
        fallback = self._find_adapter("jinja_primitive")
        if fallback is not None:
            result = fallback.resolve(query, spec={})
            if result.status == "hit":
                result.status = "fallback"
                # Task 7：兜底 fallback 统一 CUSTOM（规则视角无 match/spec 线索）
                result.category = PartCategory.CUSTOM
                self._decision_log.append(
                    (query.part_no, "jinja_primitive", result.source_tag))
                if _trace is not None:
                    _trace.append("jinja_primitive(fallback)")
                return result

        return ResolveResult.miss()
```

改为：
```python
        fallback = self._find_adapter("jinja_primitive")
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
            if result.status == "skip":
                if _trace is not None:
                    _trace.append("jinja_primitive(skip)")
                return result

        return ResolveResult.miss()
```

- [ ] **Step 4：运行测试确认通过**

```
uv run pytest tests/test_resolve_report.py::TestResolveResultSkip -v
```

期望：3 PASSED

- [ ] **Step 5：提交**

```bash
git add parts_resolver.py tests/test_resolve_report.py
git commit -m "feat(resolver): 新增 ResolveResult.skip() 状态 + resolve() 传递路径"
```

---

## Task 2：jinja_primitive — _SKIP_CATEGORIES 返回 skip 而非 miss

**Files:**
- Modify: `adapters/parts/jinja_primitive_adapter.py:263-270`

- [ ] **Step 1：写失败测试**

在 `tests/test_parts_adapters.py` 中找到 `test_resolve_skip_fastener` 测试，修改断言为：

```python
    def test_resolve_skip_fastener(self):
        """Fasteners 在 _SKIP_CATEGORIES → skip（不是 miss）。"""
        a = JinjaPrimitiveAdapter()
        q = PartQuery(
            part_no="X-001",
            name_cn="M3×10 内六角",
            material="不锈钢",
            category="fastener",
            make_buy="外购",
        )
        result = a.resolve(q, spec={})
        assert result.status == "skip"
```

同时在该文件的 `TestJinjaPrimitiveAdapter` 类中追加 cable 测试：

```python
    def test_resolve_skip_cable(self):
        """Cable 在 _SKIP_CATEGORIES → skip。"""
        a = JinjaPrimitiveAdapter()
        q = PartQuery(
            part_no="GIS-EE-001-11",
            name_cn="Igus拖链段",
            material="E2 micro 内径6mm",
            category="cable",
            make_buy="外购",
        )
        result = a.resolve(q, spec={})
        assert result.status == "skip"
        assert result.kind == "miss"
        assert "cable" in result.source_tag
```

- [ ] **Step 2：运行确认失败**

```
uv run pytest tests/test_parts_adapters.py::TestJinjaPrimitiveAdapter::test_resolve_skip_fastener tests/test_parts_adapters.py::TestJinjaPrimitiveAdapter::test_resolve_skip_cable -v
```

期望：FAIL — `AssertionError: assert 'miss' == 'skip'`

- [ ] **Step 3：实现改写**

在 `adapters/parts/jinja_primitive_adapter.py` 中找到 `resolve()` 方法的 skip 分支（大约 268-269 行）：

```python
        if query.category in _SKIP_CATEGORIES:
            return ResolveResult.miss()
```

改为：

```python
        if query.category in _SKIP_CATEGORIES:
            return ResolveResult.skip(
                reason=f"{query.category} category: no geometry generated"
            )
```

- [ ] **Step 4：运行测试确认通过**

```
uv run pytest tests/test_parts_adapters.py::TestJinjaPrimitiveAdapter::test_resolve_skip_fastener tests/test_parts_adapters.py::TestJinjaPrimitiveAdapter::test_resolve_skip_cable -v
```

期望：2 PASSED

- [ ] **Step 5：确认全套测试不回归**

```
uv run pytest tests/test_parts_adapters.py -v --tb=short
```

期望：所有测试通过

- [ ] **Step 6：提交**

```bash
git add adapters/parts/jinja_primitive_adapter.py tests/test_parts_adapters.py
git commit -m "feat(jinja_primitive): _SKIP_CATEGORIES 返回 skip 替代 miss"
```

---

## Task 3：resolve_report — skip 计入单独桶

**Files:**
- Modify: `parts_resolver.py:130` (ResolveReportRow.status 注释)
- Modify: `parts_resolver.py:434-460` (resolve_report 状态逻辑)

- [ ] **Step 1：写失败测试**

在 `tests/test_resolve_report.py` 末尾追加（在 `TestResolveResultSkip` 之后）：

```python
class TestResolveReportSkip:
    """cable/fastener 等 intentional-skip 件在 resolve_report 中正确体现。"""

    def _make_cable_rows(self) -> list[dict]:
        return [
            {
                "part_no": "GIS-EE-001-11",
                "name_cn": "Igus拖链段",
                "material": "E2 micro 内径6mm",
                "category": "cable",
                "make_buy": "外购",
            },
            {
                "part_no": "GIS-EE-003-09",
                "name_cn": "Gore柔性同轴",
                "material": "MicroTCA系列×500mm",
                "category": "cable",
                "make_buy": "外购",
            },
        ]

    def test_cable_rows_show_skip_status(self):
        resolver = _make_resolver()
        report = resolver.resolve_report(self._make_cable_rows())
        for row in report.rows:
            assert row.status == "skip", f"{row.bom_id} should be skip, got {row.status}"

    def test_cable_rows_matched_adapter_is_skip_bucket(self):
        resolver = _make_resolver()
        report = resolver.resolve_report(self._make_cable_rows())
        for row in report.rows:
            assert row.matched_adapter == "(skip)"

    def test_skip_bucket_counted_separately_from_none(self):
        resolver = _make_resolver()
        report = resolver.resolve_report(self._make_cable_rows())
        assert "(skip)" in report.adapter_hits
        assert report.adapter_hits["(skip)"].count == 2
        # (none) 桶不应出现（没有真正的 miss）
        none_count = report.adapter_hits.get("(none)", AdapterHit(count=0, unavailable_reason=None)).count
        assert none_count == 0

    def test_skip_status_in_to_dict(self):
        resolver = _make_resolver()
        report = resolver.resolve_report(self._make_cable_rows())
        d = report.to_dict()
        statuses = [r["status"] for r in d["rows"]]
        assert statuses == ["skip", "skip"]

    def test_attempted_adapters_has_skip_trace(self):
        resolver = _make_resolver()
        report = resolver.resolve_report(self._make_cable_rows())
        for row in report.rows:
            assert any("skip" in t for t in row.attempted_adapters)
```

- [ ] **Step 2：运行确认失败**

```
uv run pytest tests/test_resolve_report.py::TestResolveReportSkip -v
```

期望：FAIL

- [ ] **Step 3：更新 resolve_report() 逻辑**

在 `parts_resolver.py` 中，找到 `resolve_report()` 的状态判断块（大约 434-460 行）：

```python
            if result.status == "miss":
                matched = "(none)"
            elif result.status == "fallback":
                matched = "jinja_primitive"
            else:
                matched = result.adapter
            if matched in report.adapter_hits:
                report.adapter_hits[matched].count += 1
            else:
                report.adapter_hits[matched] = AdapterHit(count=1, unavailable_reason=None)

            if result.status == "hit":
                status = "hit"
            elif result.status == "fallback":
                status = "fallback"
            else:
                status = "miss"
```

改为：

```python
            if result.status == "miss":
                matched = "(none)"
            elif result.status == "skip":
                matched = "(skip)"
            elif result.status == "fallback":
                matched = "jinja_primitive"
            else:
                matched = result.adapter
            if matched in report.adapter_hits:
                report.adapter_hits[matched].count += 1
            else:
                report.adapter_hits[matched] = AdapterHit(count=1, unavailable_reason=None)

            if result.status == "hit":
                status = "hit"
            elif result.status == "fallback":
                status = "fallback"
            elif result.status == "skip":
                status = "skip"
            else:
                status = "miss"
```

同时更新 `ResolveReportRow` 数据类的注释（第 130 行）：
```python
    status: str  # "hit" | "fallback" | "miss" | "skip"
```

- [ ] **Step 4：运行测试确认通过**

```
uv run pytest tests/test_resolve_report.py::TestResolveReportSkip -v
```

期望：5 PASSED

- [ ] **Step 5：更新 status 枚举断言**

在 `tests/test_resolve_report.py` 中找到 `test_rows_have_required_fields` 测试的这行：

```python
        assert r.status in ("hit", "fallback", "miss")
```

改为：

```python
        assert r.status in ("hit", "fallback", "miss", "skip")
```

- [ ] **Step 6：运行全套 resolve_report 测试**

```
uv run pytest tests/test_resolve_report.py -v
```

期望：所有测试通过

- [ ] **Step 7：提交**

```bash
git add parts_resolver.py tests/test_resolve_report.py
git commit -m "feat(resolve_report): skip 状态计入 (skip) 桶，不污染 miss 统计"
```

---

## Task 4：gen_std_parts + cad_spec_gen — skip 等同 miss

**Files:**
- Modify: `codegen/gen_std_parts.py:294`
- Modify: `cad_spec_gen.py:901`

- [ ] **Step 1：写失败测试**

在 `tests/test_parts_library_integration.py` 中，找到测试 fastener 被跳过的测试（大约 579 行附近），添加 cable 版本：

```python
    def test_cable_skipped_in_gen_std_parts(self, tmp_path):
        """cable category skip 状态不产生 gen_std_parts 输出函数。"""
        from codegen.gen_std_parts import gen_std_parts
        bom = [
            {
                "part_no": "C-001",
                "name_cn": "测试拖链",
                "material": "",
                "category": "cable",
                "make_buy": "外购",
                "qty": 1,
            }
        ]
        out_dir = tmp_path / "std_parts"
        out_dir.mkdir()
        result_files = gen_std_parts(bom, project_root=str(tmp_path), out_dir=str(out_dir))
        assert not any("C_001" in f for f in result_files), \
            "cable 件不应出现在 gen_std_parts 输出中"
```

- [ ] **Step 2：运行确认（应该已经通过，但须验证）**

```
uv run pytest tests/test_parts_library_integration.py::test_cable_skipped_in_gen_std_parts -v
```

若 FAIL 则执行 Step 3，若 PASS 则直接跳到 Step 4。

- [ ] **Step 3：更新 skip 处理（如需要）**

在 `codegen/gen_std_parts.py` 第 294 行附近找到：

```python
        if result.status == "miss" or result.kind == "miss":
```

改为：

```python
        if result.status in {"miss", "skip"} or result.kind == "miss":
```

在 `cad_spec_gen.py` 第 901 行附近找到：

```python
                if result.status == "miss" or result.kind == "miss":
```

改为：

```python
                if result.status in {"miss", "skip"} or result.kind == "miss":
```

- [ ] **Step 4：运行全套测试确认无回归**

```
uv run pytest tests/ -x -q --tb=short 2>&1 | tail -20
```

期望：全部 PASS

- [ ] **Step 5：提交**

```bash
git add codegen/gen_std_parts.py cad_spec_gen.py tests/test_parts_library_integration.py
git commit -m "fix(codegen): skip 状态不产生 gen 输出（等同 miss）"
```

---

## Task 5：HTML 报告 — skip 行加样式

**Files:**
- Modify: `sw_preflight/templates/sw_report.html.j2`

- [ ] **Step 1：在 CSS 区块加 .skip class**

在 `sw_preflight/templates/sw_report.html.j2` 找到 `.ok`, `.warn`, `.err` CSS 定义所在位置（大约第 5-15 行），在其后追加：

```css
.skip{color:#888}
```

- [ ] **Step 2：更新路由表格的状态单元格**

找到：

```html
        <td>{{ row.status }}</td>
```

改为：

```html
        <td class="{{ 'ok' if row.status in ('hit','fallback') else 'skip' if row.status=='skip' else 'err' }}">{{ row.status }}</td>
```

- [ ] **Step 3：视觉验证（可选）**

若本地有 HTML 报告，用浏览器打开验证 skip 行是灰色，miss 行仍是红色。

- [ ] **Step 4：提交**

```bash
git add sw_preflight/templates/sw_report.html.j2
git commit -m "style(report): skip 状态行显示灰色，区别于 miss 红色"
```

---

## Task 6：端到端验证 + 最终全套测试

**Files:**
- Read: `artifacts/20260425-101749/resolve_report.json`（旧报告对比用）

- [ ] **Step 1：运行全套测试**

```
uv run pytest tests/ -q --tb=short 2>&1 | tail -10
```

期望：所有测试 PASSED（≥ 1210），0 FAILED

- [ ] **Step 2：生成新 resolve_report 验证覆盖率**

```bash
python -c "
from bom_parser import parse_bom
from parts_resolver import default_resolver
import json, datetime

bom = parse_bom('tests/fixtures/real_doc_boms/end_effector.yaml')
resolver = default_resolver(project_root='.')
report = resolver.resolve_report(bom)
run_id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
out = f'artifacts/{run_id}'
import os; os.makedirs(out, exist_ok=True)
with open(f'{out}/resolve_report.json', 'w', encoding='utf-8') as f:
    json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
hits = sum(h.count for k, h in report.adapter_hits.items() if k not in ('(none)', '(skip)'))
skips = report.adapter_hits.get('(skip)', type('', (), {'count': 0})()).count
misses = report.adapter_hits.get('(none)', type('', (), {'count': 0})()).count
print(f'命中: {hits}/{report.total_rows}  skip: {skips}  miss: {misses}')
print(f'有效覆盖: {hits+skips}/{report.total_rows} (含 {skips} intentional-skip)')
"
```

期望输出：
```
命中: 52/54  skip: 2  miss: 0
有效覆盖: 54/54 (含 2 intentional-skip)
```

- [ ] **Step 3：确认两个 cable 件状态为 skip**

```bash
python -c "
from bom_parser import parse_bom
from parts_resolver import default_resolver

bom = parse_bom('tests/fixtures/real_doc_boms/end_effector.yaml')
resolver = default_resolver(project_root='.')
report = resolver.resolve_report(bom)
targets = ['GIS-EE-001-11', 'GIS-EE-003-09']
for row in report.rows:
    if row.bom_id in targets:
        print(f'{row.bom_id}: status={row.status}, matched={row.matched_adapter}, trace={row.attempted_adapters}')
"
```

期望：
```
GIS-EE-001-11: status=skip, matched=(skip), trace=['jinja_primitive(skip)']
GIS-EE-003-09: status=skip, matched=(skip), trace=['jinja_primitive(skip)']
```

- [ ] **Step 4：提交**

```bash
git add artifacts/
git commit -m "chore: 更新 resolve_report — cable 件 status=skip，覆盖 54/54"
```

---

## 自审清单

| 检查项 | 状态 |
|---|---|
| `ResolveKind` Literal 已包含 `"skip"` | ☐ |
| `ResolveResult.status` Literal 已包含 `"skip"` | ☐ |
| `ResolveResult.skip()` 工厂方法存在 | ☐ |
| `resolve()` fallback 传递 skip | ☐ |
| `jinja_primitive._SKIP_CATEGORIES` 路径返回 skip | ☐ |
| `resolve_report()` skip → `(skip)` 桶 | ☐ |
| `gen_std_parts` 和 `cad_spec_gen` skip → continue | ☐ |
| HTML skip 行灰色 CSS | ☐ |
| 旧的 `assert status == "miss"` (fastener) 已更新为 `skip` | ☐ |
| `test_rows_have_required_fields` 已包含 `"skip"` | ☐ |
| 全套测试 ≥ 1210 PASSED | ☐ |
| resolve_report 端到端：miss=0, skip=2 | ☐ |
