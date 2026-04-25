# jinja_primitive._GENERATORS 补全实现计划
## elastic / locating / transmission 三类零件几何生成器

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全 `jinja_primitive` 的三类缺失几何生成器，同时修复 BOM 分类器关键词缺失和 `_dims_to_envelope` 的 gear-width 丢失 bug，使 `elastic`/`transmission` yaml 路由规则真正可达。

**Architecture:** 分两组修改。第一组：在 `bom_parser.py`（根目录和包内各一份，两处同步）新增 `elastic`/`transmission` 分类关键词，令 `classify_part()` 输出与 yaml `match.category` 对齐。第二组：在 `jinja_primitive_adapter.py` 新增 `_gen_locating`/`_gen_elastic`/`_gen_transmission` 三个生成器函数并注册到 `_GENERATORS`，同时修复 `_dims_to_envelope` 忽略 `"w"` 键的 bug；同步在 `cad_spec_defaults.py` 补三个 category fallback dims。

**Tech Stack:** Python 3.11+, CadQuery（几何代码生成为字符串，不执行），pytest / uv run pytest

---

## 文件地图

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| 新建 | `tests/test_bom_classifier_new_categories.py` | BOM 分类器测试 |
| 新建 | `tests/test_jinja_generators_new.py` | 生成器端到端测试 |
| 修改 | `bom_parser.py` | 根目录副本（CLI + 测试用） |
| 修改 | `src/cad_spec_gen/data/python_tools/bom_parser.py` | 包内副本（pip 安装路径） |
| 修改 | `adapters/parts/jinja_primitive_adapter.py` | 新增 3 个生成器函数 + _dims_to_envelope 修复 |
| 修改 | `src/cad_spec_gen/data/python_tools/cad_spec_defaults.py` | 新增 3 条 fallback dims |

> ⚠️ **重要：** 两份 `bom_parser.py`（根目录 vs 包内）内容相同，每次修改必须两处同步，否则 CLI 和 pip 安装后行为不一致。

---

## Task 1: 写失败的 BOM 分类器测试（RED）

**Files:**
- Create: `tests/test_bom_classifier_new_categories.py`

- [ ] **Step 1: 创建测试文件**

```python
# tests/test_bom_classifier_new_categories.py
"""BOM 分类器新增 elastic / transmission 类别规则测试。

import 说明：pytest 根据 pyproject.toml testpaths=["tests"] 运行，conftest.py
将 src/ 加入 sys.path，pytest rootdir（项目根）也在 sys.path，
所以 `from bom_parser import ...` 直接引用根目录的 bom_parser.py。
"""
from __future__ import annotations

from bom_parser import classify_part


def test_rubber_spring_elastic() -> None:
    assert classify_part("橡胶弹簧") == "elastic"


def test_leaf_spring_elastic() -> None:
    assert classify_part("板弹簧 120×30×3mm") == "elastic"


def test_gear_transmission() -> None:
    assert classify_part("齿轮 m=1 z=20") == "transmission"


def test_sprocket_transmission() -> None:
    assert classify_part("链轮 GB") == "transmission"


def test_pulley_transmission() -> None:
    assert classify_part("皮带轮 Φ60") == "transmission"


def test_timing_belt_stays_cable() -> None:
    """同步带 GT2 不被 transmission 误捕（cable 规则含"同步带"/"皮带"）。"""
    assert classify_part("同步带 GT2") == "cable"


def test_spring_washer_stays_spring() -> None:
    """弹性垫圈不被 elastic 误捕（spring 规则在前且含"弹性垫圈"）。"""
    assert classify_part("弹性垫圈 M6") == "spring"


def test_bare_coupler_stays_connector() -> None:
    """裸联轴器归 connector（first-match 且 connector 规则含"联轴器"）。"""
    assert classify_part("联轴器 L070") == "connector"


def test_elastic_coupling_stays_connector() -> None:
    """弹性联轴器也归 connector（connector 规则含"联轴器"和"L050"，排在 elastic 前）。"""
    assert classify_part("弹性联轴器 L050") == "connector"
```

- [ ] **Step 2: 运行测试，确认 RED**

```bash
uv run pytest tests/test_bom_classifier_new_categories.py -v
```

期望输出：`test_rubber_spring_elastic FAILED`、`test_gear_transmission FAILED`（等 5 个新类别用例失败）；`test_timing_belt_stays_cable PASSED`、`test_spring_washer_stays_spring PASSED`、`test_bare_coupler_stays_connector PASSED`、`test_elastic_coupling_stays_connector PASSED`（边界保持用例应已通过）。

---

## Task 2: 实现 elastic 分类规则（两份文件同步）

**Files:**
- Modify: `bom_parser.py`（根目录）
- Modify: `src/cad_spec_gen/data/python_tools/bom_parser.py`

- [ ] **Step 1: 在根目录 `bom_parser.py` 的 `_PART_CATEGORY_RULES` 中插入 elastic 规则**

找到这一行（约第 39 行）：
```python
    ("tank",      ["储液罐", "储罐", "tank", "容器"]),
```
在其**之后**、`("cable", ...)` 之前插入：
```python
    ("elastic",      ["橡胶弹簧", "板弹簧", "弹性卡圈",
                      "弹性垫片", "rubber spring", "leaf spring",
                      "elastic coupling", "snap ring"]),
```

- [ ] **Step 2: 对包内副本做完全相同的修改**

```
src/cad_spec_gen/data/python_tools/bom_parser.py
```
插入位置和内容与 Step 1 完全相同。

- [ ] **Step 3: 运行 elastic 相关测试，确认变绿**

```bash
uv run pytest tests/test_bom_classifier_new_categories.py -v -k "elastic"
```

期望：`test_rubber_spring_elastic PASSED`、`test_leaf_spring_elastic PASSED`、`test_spring_washer_stays_spring PASSED`（3 个与 elastic 相关的用例全绿）。

---

## Task 3: 实现 transmission 分类规则 + 全量 classifier 测试绿 + 提交

**Files:**
- Modify: `bom_parser.py`（根目录）
- Modify: `src/cad_spec_gen/data/python_tools/bom_parser.py`

- [ ] **Step 1: 在根目录 `bom_parser.py` 的 elastic 规则之后插入 transmission 规则**

```python
    ("transmission", ["齿轮", "链轮", "皮带轮", "蜗杆", "蜗轮",
                      "齿条", "锥齿轮", "斜齿轮",
                      "gear", "sprocket", "pulley", "worm"]),
```

插入后 `_PART_CATEGORY_RULES` 的 tank→cable 区段应如下：
```python
    ("tank",      ["储液罐", "储罐", "tank", "容器"]),
    ("elastic",      ["橡胶弹簧", "板弹簧", "弹性卡圈",
                      "弹性垫片", "rubber spring", "leaf spring",
                      "elastic coupling", "snap ring"]),
    ("transmission", ["齿轮", "链轮", "皮带轮", "蜗杆", "蜗轮",
                      "齿条", "锥齿轮", "斜齿轮",
                      "gear", "sprocket", "pulley", "worm"]),
    ("cable",     ["线缆", "cable", "FFC", ...]),
```

- [ ] **Step 2: 对包内副本做完全相同的修改**

```
src/cad_spec_gen/data/python_tools/bom_parser.py
```

- [ ] **Step 3: 运行全量 classifier 测试，确认全绿**

```bash
uv run pytest tests/test_bom_classifier_new_categories.py -v
```

期望：**9/9 PASSED**。

- [ ] **Step 4: 提交**

```bash
git add bom_parser.py src/cad_spec_gen/data/python_tools/bom_parser.py \
        tests/test_bom_classifier_new_categories.py
git commit -m "feat(bom): 新增 elastic/transmission 零件分类规则"
```

---

## Task 4: 写失败的生成器测试（RED）

**Files:**
- Create: `tests/test_jinja_generators_new.py`

- [ ] **Step 1: 创建测试文件**

```python
# tests/test_jinja_generators_new.py
"""jinja_primitive 新增 locating/elastic/transmission 生成器端到端测试。

PartQuery 是 parts_resolver.py 里的 @dataclass，字段：
  part_no, name_cn, material, category, make_buy,
  spec_envelope=None, spec_envelope_granularity="part_envelope", project_root=""
"""
from __future__ import annotations

import pytest
from parts_resolver import PartQuery
from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter


def _q(category: str, name: str = "test", material: str = "") -> PartQuery:
    """快捷构造一个最小化 PartQuery。"""
    return PartQuery(
        part_no="TEST-001",
        name_cn=name,
        material=material,
        category=category,
        make_buy="外购",
    )


@pytest.fixture(scope="module")
def adapter() -> JinjaPrimitiveAdapter:
    return JinjaPrimitiveAdapter()


# ── can_resolve ──────────────────────────────────────────────────────────────

def test_can_resolve_locating(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("locating")) is True


def test_can_resolve_elastic(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("elastic")) is True


def test_can_resolve_transmission(adapter: JinjaPrimitiveAdapter) -> None:
    assert adapter.can_resolve(_q("transmission")) is True


# ── resolve → hit ────────────────────────────────────────────────────────────

def test_resolve_locating_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("locating"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


def test_resolve_elastic_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("elastic"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


def test_resolve_transmission_hit(adapter: JinjaPrimitiveAdapter) -> None:
    result = adapter.resolve(_q("transmission"), {})
    assert result.status == "hit"
    assert result.kind == "codegen"
    assert "cq.Workplane" in result.body_code


# ── probe_dims 返回有效 (w, d, h) tuple ──────────────────────────────────────

def test_probe_dims_locating(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("locating"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


def test_probe_dims_elastic(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("elastic"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


def test_probe_dims_transmission(adapter: JinjaPrimitiveAdapter) -> None:
    dims = adapter.probe_dims(_q("transmission"), {})
    assert dims is not None
    assert len(dims) == 3
    assert all(v > 0 for v in dims)


# ── transmission envelope 正确反映齿轮厚度 w ─────────────────────────────────

def test_transmission_envelope_uses_w(adapter: JinjaPrimitiveAdapter) -> None:
    """默认 dims {"od":30,"w":8,"id":6} → probe_dims 应返回 (30, 30, 8)。
    
    修复前 _dims_to_envelope 不检查 "w"，返回 (30, 30, 5)。
    """
    dims = adapter.probe_dims(_q("transmission"), {})
    assert dims == (30, 30, 8)


# ── locating: dims 从 material text 提取 ─────────────────────────────────────

def test_locating_dims_from_material_text(adapter: JinjaPrimitiveAdapter) -> None:
    """material='Φ5×16mm' 经 _parse_dims_from_text 提取为 d=5, l=16。
    
    _gen_locating 接收 d=5 → circle(2.5)，验证字符串包含正确半径。
    """
    result = adapter.resolve(_q("locating", name="定位销", material="Φ5×16mm"), {})
    assert result.status == "hit"
    assert "circle(2.5)" in result.body_code
```

- [ ] **Step 2: 运行测试，确认 RED**

```bash
uv run pytest tests/test_jinja_generators_new.py -v
```

期望：全部 13 个测试均 `FAILED`（`can_resolve` 返回 False，因为 "locating"/"elastic"/"transmission" 还不在 `_GENERATORS`）。

---

## Task 5: 补 STD_PART_DIMENSIONS 默认 dims + 实现 `_gen_locating`

**Files:**
- Modify: `src/cad_spec_gen/data/python_tools/cad_spec_defaults.py`
- Modify: `adapters/parts/jinja_primitive_adapter.py`

- [ ] **Step 1: 在 `cad_spec_defaults.py` 的 STD_PART_DIMENSIONS 末尾（`_seal` 之后）新增三条**

找到这三行（约第 194–197 行）：
```python
    "_sensor":      {"d": 15, "l": 12},
    "_pump":        {"w": 30, "h": 25, "l": 40},
    "_connector":   {"d": 10, "l": 25},
    "_seal":        {"od": 80, "id": 75, "section_d": 2.4},
    "_tank":        {"d": 38, "l": 280},
}
```
在 `"_tank"` 行之后、闭括号 `}` 之前插入：
```python
    "_locating":     {"d": 3,  "l": 10},
    "_elastic":      {"d": 20, "l": 30},
    "_transmission": {"od": 30, "w": 8, "id": 6},
```

- [ ] **Step 2: 在 `jinja_primitive_adapter.py` 的 `_gen_generic` 函数之前，新增 `_gen_locating` 函数**

插入位置：`_gen_generic` 定义之前（约第 160 行）：
```python
def _gen_locating(dims: dict) -> str:
    d = dims.get("d", 3)
    l = dims.get("l", 10)
    chamfer = max(d * 0.1, 0.3)
    return f"""    # Simplified locating pin: cylinder with chamfered tip
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    body = body.faces(">Z").edges().chamfer({chamfer:.3f})
    return body"""
```

- [ ] **Step 3: 在 `_GENERATORS` 字典中注册 "locating"**

找到：
```python
_GENERATORS = {
    "motor":     _gen_motor,
    ...
    "other":     _gen_generic,
}
```
在 `"other"` 行之前插入：
```python
    "locating":     _gen_locating,
```

- [ ] **Step 4: 运行 locating 相关测试，确认变绿**

```bash
uv run pytest tests/test_jinja_generators_new.py -v -k "locating"
```

期望：`test_can_resolve_locating PASSED`、`test_resolve_locating_hit PASSED`、`test_probe_dims_locating PASSED`、`test_locating_dims_from_material_text PASSED`（4 个 locating 用例全绿）。

---

## Task 6: 实现 `_gen_elastic`

**Files:**
- Modify: `adapters/parts/jinja_primitive_adapter.py`

- [ ] **Step 1: 在 `_gen_locating` 之后插入 `_gen_elastic` 函数**

```python
def _gen_elastic(dims: dict) -> str:
    if "d" in dims and "l" in dims:
        d = dims["d"]
        l = dims["l"]
        return f"""    # Simplified elastic part: solid cylinder (rubber spring/damper)
    body = cq.Workplane("XY").circle({d/2}).extrude({l})
    return body"""
    w = dims.get("w", 20)
    h = dims.get("h", 5)
    l = dims.get("l", 120)
    return f"""    # Simplified elastic part: rectangular block (leaf spring)
    body = cq.Workplane("XY").box({w}, {l}, {h}, centered=(True, True, False))
    return body"""
```

- [ ] **Step 2: 在 `_GENERATORS` 中注册 "elastic"（紧跟 "locating" 之后）**

```python
    "locating":     _gen_locating,
    "elastic":      _gen_elastic,
```

- [ ] **Step 3: 运行 elastic 相关测试，确认变绿**

```bash
uv run pytest tests/test_jinja_generators_new.py -v -k "elastic"
```

期望：`test_can_resolve_elastic PASSED`、`test_resolve_elastic_hit PASSED`、`test_probe_dims_elastic PASSED`（3 个 elastic 用例全绿）。

---

## Task 7: 实现 `_gen_transmission` + 修复 `_dims_to_envelope` + 全量验证 + 提交

**Files:**
- Modify: `adapters/parts/jinja_primitive_adapter.py`

- [ ] **Step 1: 在 `_gen_elastic` 之后插入 `_gen_transmission` 函数**

```python
def _gen_transmission(dims: dict) -> str:
    od = dims.get("od", 30)
    w = dims.get("w", 8)
    id_ = dims.get("id", 6)
    return f"""    # Simplified gear: solid disc with shaft hole
    body = (cq.Workplane("XY")
            .circle({od/2}).circle({id_/2}).extrude({w}))
    return body"""
```

- [ ] **Step 2: 在 `_GENERATORS` 中注册 "transmission"**

```python
    "locating":      _gen_locating,
    "elastic":       _gen_elastic,
    "transmission":  _gen_transmission,
```

- [ ] **Step 3: 修复 `_dims_to_envelope` 的 "w" 丢失 bug**

找到 `_dims_to_envelope` 方法中的 `"od" in dims` 分支（约第 311 行）：
```python
        if "od" in dims:
            h = dims.get("h", dims.get("l", dims.get("t", 5)))
            return (dims["od"], dims["od"], h)
```
改为：
```python
        if "od" in dims:
            h = dims.get("h", dims.get("l", dims.get("w", dims.get("t", 5))))
            return (dims["od"], dims["od"], h)
```

> 说明：`"w"` 作为齿轮/轴承"宽度/厚度"的 fallback 插在 `"t"` 之前。

- [ ] **Step 4: 运行全量生成器测试，确认全绿**

```bash
uv run pytest tests/test_jinja_generators_new.py -v
```

期望：**13/13 PASSED**（含 `test_transmission_envelope_uses_w` 返回 `(30, 30, 8)`）。

- [ ] **Step 5: 全量回归**

```bash
uv run pytest --tb=short -q
```

期望：**≥ 1217 passed，0 failed**（新增测试在此数量之上）。

- [ ] **Step 6: 提交**

```bash
git add adapters/parts/jinja_primitive_adapter.py \
        src/cad_spec_gen/data/python_tools/cad_spec_defaults.py \
        tests/test_jinja_generators_new.py
git commit -m "feat(jinja): 新增 locating/elastic/transmission 生成器 + _dims_to_envelope w 修复"
```

---

## 验收检查清单

完成后对照验证：

- [ ] `classify_part("齿轮")` == `"transmission"`
- [ ] `classify_part("橡胶弹簧")` == `"elastic"`
- [ ] `classify_part("弹性垫圈 M6")` == `"spring"`（不被 elastic 误捕）
- [ ] `classify_part("同步带 GT2")` == `"cable"`（不被 transmission 误捕）
- [ ] `JinjaPrimitiveAdapter().can_resolve(PartQuery(..., category="locating", ...))` == `True`
- [ ] transmission `probe_dims` 返回 `(30, 30, 8)` 而非 `(30, 30, 5)`
- [ ] `uv run pytest` ≥ 1217 passed，0 failed
