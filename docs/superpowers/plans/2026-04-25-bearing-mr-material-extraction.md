# 微型轴承 MR-series material 字段型号提取 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 GIS-EE-004-11（MR105ZZ 微型轴承）路由至 sw_toolbox 后提前 miss 的问题，使 resolve_report 覆盖率从 46/48 提升至 47/48。

**Architecture:** 三处独立改动：① YAML size_patterns 新增 MR-series 正则；② 同义词表新增 `微型→miniature`；③ sw_toolbox_adapter 三个 callsite 对 bearing 品类增加 material 字段作为 name_cn 失败时的二次提取来源。每项改动均先写失败测试再实现。

**Tech Stack:** Python 3.11, pytest, YAML, regex

---

## 文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `parts_library.default.yaml` | Modify | bearing size_patterns 新增 model_mr |
| `config/toolbox_cn_synonyms.yaml` | Modify | bearings 区块新增 微型→miniature |
| `adapters/parts/sw_toolbox_adapter.py` | Modify | 3 处 callsite 加 bearing material fallback |
| `tests/test_sw_toolbox_catalog.py` | Modify | 新增 MR-series 提取测试 |
| `tests/test_toolbox_cn_synonyms.py` | Modify | 新增微型同义词测试 |
| `tests/test_sw_toolbox_adapter.py` | Modify | 新增 bearing material fallback 集成测试 |

---

## Task 0：预飞行检查（不写代码）

**验证假设，防止计划漂移。**

- [ ] **Step 1：确认 bearing size_patterns 当前行号**

```bash
grep -n "model_mr\|bearing:" parts_library.default.yaml
```

预期：看到 `bearing:` 和 `model: '\b(\d{4,5})\b'`，无 `model_mr`。

- [ ] **Step 2：确认同义词文件无 `微型`**

```bash
grep -n "微型" config/toolbox_cn_synonyms.yaml
```

预期：无输出。

- [ ] **Step 3：确认 adapter 3 处 callsite 行号**

```bash
grep -n "extract_size_from_name" adapters/parts/sw_toolbox_adapter.py
```

预期：看到约第 185、316、402 行（`name_cn` 作为第一个参数）。

- [ ] **Step 4：确认现有 bearing 测试 fixture 结构**

```bash
grep -n "def default_patterns\|bearing" tests/test_sw_toolbox_catalog.py | head -20
```

预期：`default_patterns` fixture 的 bearing 只有 `"model": r"\b(\d{4,5})\b"`。

---

## Task 1：model_mr 正则 + 单元测试

**文件：**
- Modify: `tests/test_sw_toolbox_catalog.py`（在 `TestExtractSize` 类末尾新增 2 个测试）
- Modify: `parts_library.default.yaml`（bearing size_patterns 新增 model_mr）

- [ ] **Step 1：写失败测试**

在 `tests/test_sw_toolbox_catalog.py` 的 `TestExtractSize` 类末尾（`test_fastener_gbt_spec_no_prefix_no_length` 之后）追加：

```python
    def test_bearing_mr105zz_from_material_text(self, default_patterns):
        """MR-series 微型轴承型号在 material 字段中，需用 model_mr 模式提取。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        patterns_with_mr = {
            **default_patterns["bearing"],
            "model_mr": r"\b(MR\d{3}[A-Za-z0-9]*)\b",
        }
        result = extract_size_from_name(
            "MR105ZZ（Φ10×Φ5×4mm）", patterns_with_mr
        )
        assert result == {"model_mr": "MR105ZZ"}

    def test_bearing_mr84zz_variant(self, default_patterns):
        """MR84ZZ 等不同尺寸变体均可匹配。"""
        from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

        patterns_with_mr = {
            **default_patterns["bearing"],
            "model_mr": r"\b(MR\d{3}[A-Za-z0-9]*)\b",
        }
        result = extract_size_from_name("MR84ZZ bearing", patterns_with_mr)
        assert result == {"model_mr": "MR84ZZ"}
```

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/test_sw_toolbox_catalog.py::TestExtractSize::test_bearing_mr105zz_from_material_text tests/test_sw_toolbox_catalog.py::TestExtractSize::test_bearing_mr84zz_variant -v
```

预期：FAIL — `result is None`（因为 `model_mr` 不在 YAML 里，测试自己构造了 patterns，所以实际上这两个测试应该 PASS 而不需要改 YAML！测试是自包含的，不依赖 YAML。）

> **说明**：`extract_size_from_name` 的正则由参数传入，上面两个测试直接构造含 `model_mr` 的 patterns dict，不读 YAML——因此这两个测试不需要先改 YAML 就能通过。运行后应 PASS。若失败说明函数本身有 bug，需先排查。

- [ ] **Step 3：确认测试通过后，更新 YAML 使生产路径也有此模式**

在 `parts_library.default.yaml` 找到（约第 75 行）：

```yaml
    bearing:
      model: '\b(\d{4,5})\b'
```

改为：

```yaml
    bearing:
      model: '\b(\d{4,5})\b'
      model_mr: '\b(MR\d{3}[A-Za-z0-9]*)\b'
```

- [ ] **Step 4：再次运行测试确认仍通过**

```bash
uv run pytest tests/test_sw_toolbox_catalog.py::TestExtractSize -v
```

预期：全部 PASS（包括原有的 `test_bearing_6205` 等）。

- [ ] **Step 5：提交**

```bash
git add parts_library.default.yaml tests/test_sw_toolbox_catalog.py
git commit -m "feat(bearing): size_patterns 新增 MR-series model_mr 正则 + 测试"
```

---

## Task 2：微型同义词 + 单元测试

**文件：**
- Modify: `tests/test_toolbox_cn_synonyms.py`（`TestLoadCnSynonyms` 类新增测试）
- Modify: `config/toolbox_cn_synonyms.yaml`（bearings 区块）

- [ ] **Step 1：写失败测试**

在 `tests/test_toolbox_cn_synonyms.py` 的 `TestLoadCnSynonyms` 类末尾追加：

```python
    def test_bearing_miniature_synonym_exists(self):
        """微型 → miniature 同义词须存在，确保微型轴承 token 扩展正确。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms

        load_cn_synonyms.cache_clear()
        synonyms = load_cn_synonyms()
        assert "微型" in synonyms, "缺少 '微型' 同义词条目"
        assert "miniature" in synonyms["微型"]
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py::TestLoadCnSynonyms::test_bearing_miniature_synonym_exists -v
```

预期：FAIL — `AssertionError: 缺少 '微型' 同义词条目`。

- [ ] **Step 3：在 YAML 中新增同义词**

在 `config/toolbox_cn_synonyms.yaml` 找到 `bearings:` 区块（约第 28 行）：

```yaml
bearings:
  轴承: [bearing, bearings]
  深沟球: [deep, groove, ball]
  圆锥滚子: [tapered, roller]
  圆柱滚子: [cylindrical, roller]
  推力: [thrust]
  滚针: [needle]
```

改为（在末尾追加 `微型` 一行）：

```yaml
bearings:
  轴承: [bearing, bearings]
  深沟球: [deep, groove, ball]
  圆锥滚子: [tapered, roller]
  圆柱滚子: [cylindrical, roller]
  推力: [thrust]
  滚针: [needle]
  微型: [miniature]
```

- [ ] **Step 4：运行确认通过**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py -v
```

预期：全部 PASS。

- [ ] **Step 5：提交**

```bash
git add config/toolbox_cn_synonyms.yaml tests/test_toolbox_cn_synonyms.py
git commit -m "feat(synonyms): bearings 区块新增 微型→miniature 同义词 + 测试"
```

---

## Task 3：adapter bearing material fallback + 集成测试

**文件：**
- Modify: `adapters/parts/sw_toolbox_adapter.py`（3 处 callsite）
- Modify: `tests/test_sw_toolbox_adapter.py`（新增 class `TestBearingMaterialFallback`）

### Step 1：写失败测试

在 `tests/test_sw_toolbox_adapter.py` 末尾追加新类：

- [ ] **写测试**

```python
class TestBearingMaterialFallback:
    """bearing 品类：name_cn 无法提取型号时，应 fallback 到 material 字段。"""

    def _make_adapter_with_mock_index(self, monkeypatch, tmp_path, fake_part):
        """共用 monkeypatch 设置：mock detect/index/cache，让 resolve 走到 token 匹配阶段。"""
        from adapters.solidworks import sw_toolbox_catalog, sw_detect

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, toolbox_dir=str(tmp_path)),
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "get_toolbox_index_path",
            lambda cfg: tmp_path / "idx.json",
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "load_toolbox_index",
            lambda *a, **kw: {},
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "build_query_tokens_weighted",
            lambda *a, **kw: [("miniature", 1.0), ("bearing", 1.0)],
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "match_toolbox_part",
            lambda *a, **kw: (fake_part, 0.5),
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "get_toolbox_cache_root",
            lambda cfg: tmp_path / "cache",
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "_validate_sldprt_path",
            lambda *a, **kw: True,
        )

    def test_bearing_material_fallback_allows_resolve(self, monkeypatch, tmp_path):
        """name_cn '微型轴承' 无法提取 bearing model 时，adapter 应 fallback 查 material，
        从 'MR105ZZ（Φ10×Φ5×4mm）' 提取 model_mr='MR105ZZ'，不提前 miss。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks.sw_toolbox_catalog import SwToolboxPart
        from parts_resolver import PartQuery

        fake_part = SwToolboxPart(
            standard="GB",
            subcategory="bearing",
            sldprt_path=str(tmp_path / "mini.sldprt"),
            filename="miniature radial ball bearings gb.sldprt",
            tokens=["miniature", "radial", "ball", "bearings", "gb", "bearing"],
        )

        # 预建 STEP 缓存文件（触发 cache hit 路径）
        step_dir = tmp_path / "cache" / "GB" / "bearing"
        step_dir.mkdir(parents=True)
        step_file = step_dir / "miniature radial ball bearings gb.step"
        step_file.touch()

        self._make_adapter_with_mock_index(monkeypatch, tmp_path, fake_part)

        config = {
            "size_patterns": {
                "bearing": {
                    "model": r"\b(\d{4,5})\b",
                    "model_mr": r"\b(MR\d{3}[A-Za-z0-9]*)\b",
                }
            },
            "min_score": 0.30,
        }
        adapter = SwToolboxAdapter(config=config)

        query = PartQuery(
            part_no="GIS-EE-004-11",
            name_cn="微型轴承",
            material="MR105ZZ（Φ10×Φ5×4mm）",
            category="bearing",
            make_buy="外购",
        )
        spec = {
            "standard": ["GB", "ISO", "DIN"],
            "subcategories": ["bearing", "bearings"],
            "part_category": "bearing",
        }

        result = adapter.resolve(query, spec)

        assert result.status == "hit", f"期望 hit，实际 miss 原因：{result.warnings}"
        assert result.adapter == "sw_toolbox"

    def test_bearing_fastener_not_affected_by_material_fallback(self, monkeypatch, tmp_path):
        """fastener 品类不触发 material fallback；name_cn 提取失败应直接 miss。"""
        from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
        from adapters.solidworks import sw_toolbox_catalog, sw_detect
        from parts_resolver import PartQuery

        sw_detect._reset_cache()
        monkeypatch.setattr(
            sw_detect, "detect_solidworks",
            lambda: sw_detect.SwInfo(installed=True, toolbox_dir=str(tmp_path)),
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "get_toolbox_index_path",
            lambda cfg: tmp_path / "idx.json",
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "load_toolbox_index",
            lambda *a, **kw: {},
        )

        config = {
            "size_patterns": {
                "fastener": {
                    "size": r"[Mm](\d+(?:\.\d+)?)",
                    "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
                }
            },
            "min_score": 0.30,
        }
        adapter = SwToolboxAdapter(config=config)

        # name_cn 无 M-size，material 有（但不应被查）
        query = PartQuery(
            part_no="X-001",
            name_cn="非标螺钉",
            material="M6×20 不锈钢",
            category="fastener",
            make_buy="外购",
        )
        spec = {
            "standard": ["GB"],
            "subcategories": ["screws"],
            "part_category": "fastener",
        }

        result = adapter.resolve(query, spec)
        assert result.status == "miss"
        assert "size extraction failed" in (result.warnings or [""])[0]
```

- [ ] **Step 2：运行确认失败**

```bash
uv run pytest tests/test_sw_toolbox_adapter.py::TestBearingMaterialFallback -v
```

预期：`test_bearing_material_fallback_allows_resolve` FAIL（adapter 还未改，直接 miss）；`test_bearing_fastener_not_affected_by_material_fallback` PASS（fastener 行为未变）。

### Step 3：修改 adapter — resolve() 方法（约第 183-190 行）

- [ ] **修改 resolve() callsite**

将 `adapters/parts/sw_toolbox_adapter.py` 第 183-190 行：

```python
        # 3. 抽尺寸（决策 #9）
        size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None:
            return self._miss("size extraction failed or out of scope")
```

改为：

```python
        # 3. 抽尺寸（决策 #9）
        size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None and part_category == "bearing":
            # bearing 型号常见于 material 字段（如 MR105ZZ），name_cn 失败时二次查询
            size_dict = sw_toolbox_catalog.extract_size_from_name(
                getattr(query, "material", "") or "",
                size_patterns,
            )
        if size_dict is None:
            return self._miss("size extraction failed or out of scope")
```

### Step 4：修改 adapter — find_sldprt() 方法（约第 314-321 行）

- [ ] **修改 find_sldprt() callsite**

将：

```python
        # 抽尺寸（决策 #9：失败 → None）
        size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None:
            return None
```

改为：

```python
        # 抽尺寸（决策 #9：失败 → None）
        size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None and part_category == "bearing":
            size_dict = sw_toolbox_catalog.extract_size_from_name(
                getattr(query, "material", "") or "",
                size_patterns,
            )
        if size_dict is None:
            return None
```

### Step 5：修改 adapter — probe_dims() 方法（约第 399-407 行）

- [ ] **修改 probe_dims() callsite**

将：

```python
        size_patterns = self.config.get("size_patterns", {}).get(
            spec.get("part_category", "fastener"), {}
        )
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None:
            return None
```

改为：

```python
        size_patterns = self.config.get("size_patterns", {}).get(
            spec.get("part_category", "fastener"), {}
        )
        _probe_part_category = spec.get("part_category", "fastener")
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None and _probe_part_category == "bearing":
            size_dict = sw_toolbox_catalog.extract_size_from_name(
                getattr(query, "material", "") or "",
                size_patterns,
            )
        if size_dict is None:
            return None
```

- [ ] **Step 6：运行测试确认通过**

```bash
uv run pytest tests/test_sw_toolbox_adapter.py::TestBearingMaterialFallback -v
```

预期：两个测试均 PASS。

- [ ] **Step 7：运行完整 adapter 测试套件确认无回归**

```bash
uv run pytest tests/test_sw_toolbox_adapter.py -v
```

预期：全部 PASS（原有测试不受影响，因为它们 monkeypatch 了 `extract_size_from_name`）。

- [ ] **Step 8：提交**

```bash
git add adapters/parts/sw_toolbox_adapter.py tests/test_sw_toolbox_adapter.py
git commit -m "feat(adapter): bearing 品类新增 material 字段 fallback 尺寸提取 + 测试"
```

---

## Task 4：全套测试 + resolve_report 验证

- [ ] **Step 1：运行全量测试套件**

```bash
uv run pytest tests/ -x -q
```

预期：全部 PASS，无新增 FAIL。

- [ ] **Step 2：验证 resolve_report 覆盖率提升**

```bash
uv run python -c "
from parts_resolver import PartsResolver
from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
from adapters.parts.step_pool_adapter import StepPoolAdapter
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter
import yaml, pathlib

bom = yaml.safe_load(pathlib.Path('tests/fixtures/real_doc_boms/end_effector.yaml').read_text(encoding='utf-8'))
lib = yaml.safe_load(pathlib.Path('parts_library.default.yaml').read_text(encoding='utf-8'))

sw_cfg = lib.get('sw_toolbox', {})
resolver = PartsResolver(
    project_root='.',
    registry={},
    adapters=[
        SwToolboxAdapter(config=sw_cfg),
        StepPoolAdapter(project_root='.', config={'root': 'std_parts/'}),
        JinjaPrimitiveAdapter(),
    ],
)

parts = bom['assembly']['parts']
hits = {'sw_toolbox': 0, 'step_pool': 0, 'jinja_primitive': 0, 'miss': 0}
for row in parts:
    from parts_resolver import PartQuery
    from bom_parser import classify_part
    q = PartQuery(
        part_no=row.get('part_no',''),
        name_cn=row.get('name',''),
        material=row.get('material',''),
        category=classify_part(row),
        make_buy=row.get('make_buy',''),
    )
    r = resolver.resolve(q)
    hits[r.adapter if r.status == 'hit' else 'miss'] += 1
    if r.adapter == 'sw_toolbox' and r.status == 'hit':
        print(f'  sw_toolbox HIT: {row[\"part_no\"]} {row[\"name\"]}')

total = sum(hits.values())
print(f'\\n总计: {total} 件')
for k, v in hits.items():
    print(f'  {k}: {v}')
print(f'覆盖率: {total - hits[\"miss\"]}/{total}')
"
```

预期输出包含：
```
sw_toolbox HIT: GIS-EE-004-11 微型轴承
...
sw_toolbox: 3
覆盖率: 47/48
```

- [ ] **Step 3：如果 Step 2 命令报错（路径/import 问题），改用 sw-inspect 工具**

```bash
uv run python -m cad_spec_gen sw-inspect --resolve-report --bom tests/fixtures/real_doc_boms/end_effector.yaml
```

观察 sw_toolbox hits 是否从 2 变为 3。

- [ ] **Step 4：提交最终验证记录**

```bash
git add -A
git commit -m "chore: 验证 resolve_report 47/48，MR105ZZ sw_toolbox 命中"
```

---

## 自检：Spec 覆盖

| Spec 要求 | 对应 Task |
|---|---|
| bearing size_patterns 新增 model_mr | Task 1 |
| 微型→miniature 同义词 | Task 2 |
| resolve() material fallback（bearing 专属） | Task 3 Step 3 |
| find_sldprt() material fallback | Task 3 Step 4 |
| probe_dims() material fallback | Task 3 Step 5 |
| fastener 不触发 fallback 测试 | Task 3 测试 |
| 全套测试通过 | Task 4 Step 1 |
| resolve_report 47/48 验证 | Task 4 Step 2 |
