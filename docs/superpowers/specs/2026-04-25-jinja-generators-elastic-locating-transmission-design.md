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

---

## 改动范围

### 文件一：`src/cad_spec_gen/data/python_tools/bom_parser.py`

在 `_PART_CATEGORY_RULES` 的 `("spring", ...)` 之后、`("cable", ...)` 之前插入两条规则：

```python
("elastic",      ["橡胶弹簧", "板弹簧", "弹性联轴器", "弹性卡圈",
                  "弹性垫片", "rubber spring", "leaf spring",
                  "elastic coupling", "snap ring"]),
("transmission", ["齿轮", "链轮", "皮带轮", "蜗杆", "蜗轮",
                  "齿条", "锥齿轮", "斜齿轮",
                  "gear", "sprocket", "pulley", "worm"]),
```

**关键词边界保证（first-match 语义）：**
- `elastic` 不含"弹簧"/"碟"/"弹性垫圈"→ 不与 `spring` 重叠
- `elastic` 用"弹性联轴器"而非裸"联轴器"→ 不与 `connector` 重叠
- `transmission` 用"皮带轮"而非裸"皮带"→ 不与 `cable`（含"同步带"/"GT2"/"皮带"）重叠

### 文件二：`adapters/parts/jinja_primitive_adapter.py`

新增三个生成器函数，并注册到 `_GENERATORS`。

#### `_gen_locating(dims)` — 圆柱销 + 倒角头

几何：主体圆柱 + 顶面倒角（chamfer ≈ d × 0.1，最小 0.3 mm）。

```
   ┌──┐  ← 倒角引导头
   │  │
   │  │  ← 主体圆柱
   └──┘
```

默认尺寸：d=3 mm, l=10 mm（常见 GB/T 119 圆柱销）。

#### `_gen_elastic(dims)` — 弹性件（橡胶/板弹簧）

几何：
- 有 `d` + `l` → 实心圆柱（橡胶弹簧、弹性减振柱）
- 有 `w`/`h` → 矩形截面（板弹簧）

默认尺寸：d=20 mm, l=30 mm（橡胶减振柱典型尺寸）。

#### `_gen_transmission(dims)` — 齿轮近似（非渐开线）

几何：外环（齿廓近似，od → root_d=od×0.85 的环形 extrude）union 内盘（root_d → id 的圆盘）。
视觉上有齿轮"厚度感"，装配全景可读，非精确轮廓。

```
   ╔══════╗  ← 齿顶圆 od
   ║ ╔══╗ ║
   ║ ║  ║ ║  ← 齿根圆 root_d ≈ od × 0.85
   ║ ╚══╝ ║
   ╚══════╝
        ↑ 轴孔 id
```

默认尺寸：od=30 mm, w=8 mm, id=6 mm。

**_GENERATORS 注册：**
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

验证 BOM 分类器新规则的正确性和边界不重叠：

| 输入 | 期望输出 | 验证目标 |
|------|---------|---------|
| `"橡胶弹簧"` | `"elastic"` | 新规则命中 |
| `"弹性联轴器 L050"` | `"elastic"` | 不被 connector 先捕 |
| `"齿轮 m=1 z=20"` | `"transmission"` | 新规则命中 |
| `"链轮 GB"` | `"transmission"` | 新规则命中 |
| `"同步带 GT2"` | `"cable"` | 不被 transmission 误捕 |
| `"弹性垫圈 M6"` | `"spring"` | 不被 elastic 误捕 |
| `"联轴器 L070"` | `"connector"` | 裸联轴器不触发 elastic |

### `tests/test_jinja_generators_new.py`

验证三个生成器端到端可用：

- `can_resolve()` 对 locating/elastic/transmission 均返回 `True`
- `resolve()` 返回 `status="hit"`, `kind="codegen"`
- `body_code` 包含 `cq.Workplane` 关键字
- `probe_dims()` 返回非 `None` 的 `(w, d, h)` tuple
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
2. 实现 bom_parser.py 新规则 → classifier 测试转绿
3. 实现三个 `_gen_*` 函数 + `_GENERATORS` 注册 → generator 测试转绿
4. 补 STD_PART_DIMENSIONS 默认 dims
5. 全量回归验证 ≥ 1217 passed
