# jinja_primitive._GENERATORS 补全设计
## elastic / locating / transmission 三类零件几何生成器

**日期：** 2026-04-25
**状态：** 已批准，待实现
**范围：** 技术债 #1（Session 8 登记）

---

## 背景与问题

`adapters/parts/jinja_primitive_adapter.py` 的 `_GENERATORS` 字典是兜底 fallback 层，
对所有 `_SKIP_CATEGORIES` 以外的 category 均应能生成简化几何。但目前三类缺失：

| category | BOM 分类器 | yaml 规则 | _GENERATORS | 实际结果 |
|----------|-----------|---------|-------------|---------|
| `locating` | ✅ 有 | ✅ → sw_toolbox | ❌ 缺 | sw_toolbox miss 时完全 miss |
| `elastic` | ❌ 无 | ✅ → jinja_primitive | ❌ 缺 | yaml 规则永远触发不了 |
| `transmission` | ❌ 无 | ✅ → jinja_primitive | ❌ 缺 | yaml 规则永远触发不了 |

根因：BOM 分类器（`_PART_CATEGORY_RULES`）和 yaml 路由规则使用了不一致的分类词汇，
导致 `elastic`/`transmission` 两条 yaml 规则是死代码。

---

## 设计决策

### 分类词汇统一原则

`classify_part()` 的输出 token 必须与 yaml `match.category` 对齐，否则路由规则无效。

### 不动 "spring" 类别

"spring" 已有 `_gen_spring`，测试绿，行为正确。`elastic` 覆盖的是 **spring 未捕获** 的弹性件，
两者关键词不重叠。

### "弹性联轴器" 归属 connector，不归 elastic

`connector` 规则包含"联轴器"和"L050"，在规则列表中排在 `elastic` 之前（first-match 语义）。
"弹性联轴器 L050" 正确返回 `"connector"`，这是预期行为。
`elastic` 关键词不含"联轴器"相关词，避免死代码测试用例。

---

## 改动范围

### 文件一（×2 同步）：`bom_parser.py` — 两处都要改

> **注意：** 根目录 `bom_parser.py` 与 `src/cad_spec_gen/data/python_tools/bom_parser.py`
> 内容完全相同（diff 为空），**两个文件必须同步修改**，否则 pip 安装路径和 CLI 路径行为不一致。

在 `_PART_CATEGORY_RULES` 的 `("tank", ...)` 之后、`("cable", ...)` 之前插入两条规则：

```python
("elastic",      ["橡胶弹簧", "板弹簧", "弹性卡圈",
                  "弹性垫片", "rubber spring", "leaf spring",
                  "elastic coupling", "snap ring"]),
("transmission", ["齿轮", "链轮", "皮带轮", "蜗杆", "蜗轮",
                  "齿条", "锥齿轮", "斜齿轮",
                  "gear", "sprocket", "pulley", "worm"]),
```

**关键词边界保证（first-match 语义）：**

| elastic/transmission 关键词 | 潜在重叠规则 | 为什么安全 |
|-----------------------------|------------|-----------|
| `elastic` 不含"弹簧"/"碟" | `spring` | 不重叠 |
| `elastic` 不含"联轴器"/"L050" | `connector`（排在前面） | 弹性联轴器归 connector，正确 |
| `transmission` 用"皮带轮" 非裸"皮带" | `cable`（含"同步带"/"皮带"） | 皮带轮 ≠ 皮带 |
| `transmission` 用"蜗杆"/"蜗轮" | 无已有规则 | 安全 |

### 文件二：`adapters/parts/jinja_primitive_adapter.py`

#### 新增 `_gen_locating(dims)` — 圆柱销 + 倒角头

几何：主体圆柱 + 顶面倒角（chamfer ≈ d × 0.1，最小 0.3 mm）。

```
   ┌──┐  ← 倒角引导头
   │  │
   │  │  ← 主体圆柱
   └──┘
```

默认尺寸：d=3 mm, l=10 mm（GB/T 119 圆柱销典型）。

#### 新增 `_gen_elastic(dims)` — 弹性件（橡胶/板弹簧）

几何：
- 有 `d` + `l` → 实心圆柱（橡胶减振柱）
- 有 `w`/`h`/`l` → 矩形截面（板弹簧）

默认尺寸：d=20 mm, l=30 mm。

#### 新增 `_gen_transmission(dims)` — 齿轮近似

几何：**实心圆盘 + 轴孔** = `circle(od/2).circle(id_/2).extrude(w)`。

视觉上是标准齿轮截面（实心盘带中心孔），装配全景可读。
不做外齿近似轮廓（union 分解在数学上等价于单一环，无附加视觉价值）。

```
   ╔══════╗  ← 齿顶圆 od
   ║      ║
   ║  ○   ║  ← 轴孔 id
   ║      ║
   ╚══════╝
```

默认尺寸：od=30 mm, w=8 mm, id=6 mm。

#### 修复 `_dims_to_envelope()` — 补 "w" fallback

**现有 bug：** `{"od": 30, "w": 8, "id": 6}` 进入 `"od" in dims` 分支时，
`h = dims.get("h", dims.get("l", dims.get("t", 5)))` 不检查 "w"，返回 `(30, 30, 5)`。
齿轮厚度 `w=8` 被静默丢弃。

**修复：** 在 fallback 链加入 `dims.get("w", 5)`：
```python
if "od" in dims:
    h = dims.get("h", dims.get("l", dims.get("w", dims.get("t", 5))))
    return (dims["od"], dims["od"], h)
```

#### _GENERATORS 注册

```python
_GENERATORS = {
    ...（已有）...
    "locating":     _gen_locating,
    "elastic":      _gen_elastic,
    "transmission": _gen_transmission,
}
```

### 文件三：`src/cad_spec_gen/data/python_tools/cad_spec_defaults.py`

在 `STD_PART_DIMENSIONS` 的 category fallback 区段新增：

```python
"_locating":     {"d": 3,  "l": 10},
"_elastic":      {"d": 20, "l": 30},
"_transmission": {"od": 30, "w": 8, "id": 6},
```

---

## 测试策略（TDD：先 RED 后 GREEN）

### `tests/test_bom_classifier_new_categories.py`

| 输入 | 期望输出 | 验证目标 |
|------|---------|---------|
| `"橡胶弹簧"` | `"elastic"` | 新规则命中 |
| `"板弹簧 120×30×3mm"` | `"elastic"` | 新规则命中 |
| `"齿轮 m=1 z=20"` | `"transmission"` | 新规则命中 |
| `"链轮 GB"` | `"transmission"` | 新规则命中 |
| `"皮带轮 Φ60"` | `"transmission"` | 皮带轮归 transmission |
| `"同步带 GT2"` | `"cable"` | 不被 transmission 误捕 |
| `"弹性垫圈 M6"` | `"spring"` | 不被 elastic 误捕 |
| `"联轴器 L070"` | `"connector"` | 裸联轴器归 connector |
| `"弹性联轴器 L050"` | `"connector"` | 弹性联轴器也归 connector（first-match） |

### `tests/test_jinja_generators_new.py`

- `can_resolve()` 对 locating/elastic/transmission 均返回 `True`
- `resolve()` 返回 `status="hit"`, `kind="codegen"`
- `body_code` 包含 `cq.Workplane` 关键字
- `probe_dims()` 返回非 `None` 的 `(w, d, h)` tuple
- transmission `probe_dims` 正确返回 `(30, 30, 8)` 而非 `(30, 30, 5)`（验证 `_dims_to_envelope` 修复）
- 从 material text 提取尺寸：`"Φ5×16mm"` → locating 使用 `d=5, l=16`

### 回归验收

```
uv run pytest tests/test_bom_classifier_new_categories.py   # 全绿
uv run pytest tests/test_jinja_generators_new.py            # 全绿
uv run pytest                                               # ≥ 1217 passed，0 新失败
```

---

## 不改动的文件

- `parts_library.default.yaml` — elastic/transmission/locating 的 yaml 规则已就绪
- `parts_resolver.py` — `_MATCH_CATEGORY_TO_PART` 已有三类映射
- `sw_preflight/types.py` — `PartCategory` 枚举已有三类
- 所有已有测试

---

## 实现顺序（供 writing-plans 参考）

1. 写失败测试（test_bom_classifier_new_categories.py + test_jinja_generators_new.py）
2. 实现 bom_parser.py 新规则（两处同步）→ classifier 测试转绿
3. 实现三个 `_gen_*` 函数 + `_dims_to_envelope` 修复 + `_GENERATORS` 注册 → generator 测试转绿
4. 补 STD_PART_DIMENSIONS 默认 dims
5. 全量回归验证 ≥ 1217 passed
