# 设计文档：微型轴承 MR-series material 字段型号提取

**日期**：2026-04-25  
**作者**：brainstorming session  
**目标**：resolve_report 覆盖率 46/48 → 47/48（GIS-EE-004-11 MR105ZZ 命中 sw_toolbox）

---

## 问题陈述

GIS-EE-004-11（微型轴承，MR105ZZ）当前路由至 sw_toolbox 通用 bearing 规则，
但在尺寸提取阶段提前失败（miss: "size extraction failed or out of scope"）：

- `name_cn = "微型轴承"`：无 4-5 位数字，bearing pattern `\b(\d{4,5})\b` 无匹配 → `None`
- `material = "MR105ZZ（Φ10×Φ5×4mm）"`：未被检查
- 早期返回：`if size_dict is None: return _miss(...)`

Toolbox 索引已有 GB/bearing 条目 15 件（含 "miniature radial ball bearings gb.sldprt"），
STEP 缓存 `miniature radial ball bearings gb.step` 已存在，修复后可直接缓存命中，无需 COM 触发。

---

## 根因链（3 层）

| 层 | 问题 | 影响 |
|---|---|---|
| adapter callsite | `extract_size_from_name` 只传 `name_cn`，不检查 `material` | MR 型号不可见 |
| size_patterns | 仅 `\b(\d{4,5})\b`，不匹配 MR-series | 即使用 material 也无法提取 |
| 同义词 | 无 `微型 → miniature` 映射 | miniature bearing 与 deep groove 分数持平，匹配不确定 |

---

## 设计（方案 A）

### 改动 1：`adapters/parts/sw_toolbox_adapter.py`（3 处 callsite）

在 `resolve()`、`find_sldprt()`、`probe_dims()` 三个方法中，将：

```python
size_dict = sw_toolbox_catalog.extract_size_from_name(
    getattr(query, "name_cn", ""),
    size_patterns,
)
if size_dict is None:
    return self._miss("size extraction failed or out of scope")
```

改为：

```python
size_dict = sw_toolbox_catalog.extract_size_from_name(
    getattr(query, "name_cn", ""),
    size_patterns,
)
if size_dict is None and getattr(query, "material", ""):
    size_dict = sw_toolbox_catalog.extract_size_from_name(
        query.material,
        size_patterns,
    )
if size_dict is None:
    return self._miss("size extraction failed or out of scope")
```

语义：name_cn 提取失败时，尝试 material 字段作为第二来源；两者均失败才 miss。
`find_sldprt()` 和 `probe_dims()` 中 `return self._miss(...)` 替换为 `return None`（原语义）。

### 改动 2：`parts_library.default.yaml`

`size_patterns.bearing` 新增 MR-series 模式：

```yaml
bearing:
  model: '\b(\d{4,5})\b'
  model_mr: '\b(MR\d{3}[A-Za-z0-9]*)\b'
```

`model_mr` 匹配 MR105ZZ、MR84ZZ、MR52ZZ 等微型轴承型号。
提取成功后以 weight=1.5 注入 query tokens，虽然 Toolbox 部件 tokens 不含具体型号，
但阻止了 `size_dict is None` 早退，让 token 匹配得以进行。

### 改动 3：`config/toolbox_cn_synonyms.yaml`

`bearings` 区块新增：

```yaml
微型: [miniature]
```

效果：name_cn "微型轴承" 经同义词展开后包含 token "miniature"（weight=1.0），
使 "miniature radial ball bearings gb.sldprt" 获得额外 1.0 分，
与 "deep groove ball bearings gb.sldprt" 分差：0.50 vs 0.29（均除以总权重）。

---

## 预期 token 匹配分析

查询：GIS-EE-004-11，name_cn="微型轴承"，material="MR105ZZ（Φ10×Φ5×4mm）"

| token | 来源 | weight |
|---|---|---|
| 微型轴承 | name_cn | 1.0 |
| bearing | 同义词（轴承） | 1.0 |
| bearings | 同义词（轴承） | 1.0 |
| miniature | 同义词（微型，新增） | 1.0 |
| mr105zz | size_dict（model_mr） | 1.5 |
| mr105zz | material | 0.5（被 1.5 覆盖，dedup） |
| 10, 5, 4mm | material | 0.5 各 |

候选部件分数（total_weight ≈ 7.0）：
- miniature radial ball bearings：miniature(1.0) + bearing(1.0) + bearings(1.0) = 3.0 → **0.43**
- deep groove ball bearings：bearing(1.0) + bearings(1.0) = 2.0 → **0.29**（< min_score 0.30）

结论：唯一过阈值的候选为 miniature bearing，命中 STEP 缓存 → **sw_toolbox hit**。

---

## 不影响的场景

- **标准 bearing**（如"GB/T 276 6205深沟球轴承"）：name_cn 含 4-5 位数字 → 第一次提取成功，不触发 material fallback
- **fastener**：size_patterns 含 exclude_patterns，逻辑不变
- **seal/locating**：size_patterns 为空 → 直接返回 `{}`，不进入任何提取逻辑

---

## 测试计划

1. **单元测试**（`tests/test_sw_toolbox_catalog.py`）：新增 `extract_size_from_name("MR105ZZ（Φ10×Φ5×4mm）", bearing_patterns)` → `{"model_mr": "MR105ZZ"}`
2. **同义词测试**（`tests/test_toolbox_cn_synonyms.py`）：新增 `微型 → miniature` 验证
3. **adapter 集成测试**（`tests/test_sw_toolbox_adapter.py`）：新增 bearing + material-fallback 场景，验证 `size_dict is not None`

---

## 变更文件清单

| 文件 | 改动 |
|---|---|
| `adapters/parts/sw_toolbox_adapter.py` | 3 处 callsite 加 material fallback |
| `parts_library.default.yaml` | bearing size_patterns 新增 model_mr |
| `config/toolbox_cn_synonyms.yaml` | bearings 新增 微型→miniature |
| `tests/test_sw_toolbox_catalog.py` | MR-series 提取单元测试 |
| `tests/test_toolbox_cn_synonyms.py` | 微型同义词测试 |
| `tests/test_sw_toolbox_adapter.py` | material fallback 集成测试 |
