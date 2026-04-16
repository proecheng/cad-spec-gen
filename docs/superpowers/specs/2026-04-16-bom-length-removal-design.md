# 设计文档：从 size_patterns.fastener 删除 length 字段

**日期**: 2026-04-16  
**状态**: 已批准  
**范围**: BOM length regex fix（P1 defer）

---

## 背景

`parts_library.default.yaml` 的 `size_patterns.fastener` 包含两个字段：

```yaml
fastener:
  size: '[Mm](\d+(?:\.\d+)?)'
  length: '[×xX*\-\s](\d+(?:\.\d+)?)'
  exclude_patterns: [...]
```

`extract_size_from_name` 使用这两个正则从 BOM 的 `name_cn` 提取尺寸，结果注入 `build_query_tokens_weighted`，以 `weights["size"]`（默认 1.5）权重参与 Toolbox 文件名匹配打分。

---

## 根本原因分析

### Bug：规范号污染 length

输入：`GB/T 70.1 M6×20 内六角圆柱头螺钉`

`length` 正则 `[×xX*\-\s](\d+(?:\.\d+)?)` 的分隔符类包含 `\s`（空白）。  
`re.search` 找第一个匹配：`\s` 匹配 `GB/T 70.1` 中 "70" 前的空格 → **length = "70.1"**，而非期望的 "20"。

### 更深层的问题：length 对匹配无益

打分公式：
```
score = Σ命中权重 / Σquery总权重
```

Toolbox sldprt 文件名是**型号级模板**，如：
```
hex lobular socket head cap screws-4.8 gb.sldprt
```

文件名中从不包含具体长度（20mm、25mm 等），因为 Toolbox 零件是参数化模板，规格在插入时配置。因此：

- 正确的 `length="20"` → token "20" 加入分母，命中 0，纯粹降低分数
- 错误的 `length="70.1"` → tokens ["70","1"] 加入分母；"70" 还与 name_cn 中已有的 "70" 发生权重提升（1.0 → 1.5），双重损害

### 国标规范验证（GB/T 1237）

GB/T 标准紧固件命名格式：`名称 标准号 公称直径×[螺距×]公称长度`

- 粗牙：`M6×20`（直径 × 公称长度）
- 细牙：`M36×3×160`（直径 × 螺距 × 公称长度）
- **`×` 是唯一合法的尺寸分隔符，空格不作为分隔符**

此外，用户确认：`M6×20` 中的 `20` 为**螺纹部分公称长度**，不是螺钉总长（总长信息包含在标准号中）。这进一步说明 `length` 数值对 Toolbox 文件名匹配没有贡献。

---

## 方案选择

| 方案 | 说明 | 取舍 |
|---|---|---|
| **A — 仅修正则（移除 `\s`）** | `[×xX*\-\s]` → `[×xX*\-]` | 减少 bug 危害，但 length token 仍注入，仍是噪声 |
| **B — 删除 length 字段（选定）** | 从 `size_patterns.fastener` 整行删除 `length:` | 语义正确；消除所有长度 token 噪声；与国标命名无关性一致 |

**选定方案 B**。

---

## 变更范围

### 配置文件（2 处，内容相同）

- `parts_library.default.yaml`（根目录）：删除第 74 行 `length:` 行
- `src/cad_spec_gen/data/parts_library.default.yaml`：同上

```yaml
# 变更前
size_patterns:
  fastener:
    size: '[Mm](\d+(?:\.\d+)?)'
    length: '[×xX*\-\s](\d+(?:\.\d+)?)'   # ← 删除此行
    exclude_patterns: [...]

# 变更后
size_patterns:
  fastener:
    size: '[Mm](\d+(?:\.\d+)?)'
    exclude_patterns: [...]
```

### 测试文件

**`tests/test_sw_toolbox_catalog.py`**

| 位置 | 变更 |
|---|---|
| `TestExtractSizeFromName.default_patterns` fixture（第 89 行） | 删除 `"length"` 键 |
| 3 条断言（103、109、115 行） | `{"size": "M6", "length": "20"}` → `{"size": "M6"}` |
| 第 121 行 | `{"size": "M6.5", "length": "20"}` → `{"size": "M6.5"}` |
| 新增回归测试（TDD RED 步骤） | 见下方 |

新增测试（置于 `TestExtractSizeFromName` 类末尾）：

```python
def test_fastener_gbt_spec_no_prefix_no_length(self, default_patterns):
    """回归：GB/T 规范号中的 '70.1' 不应被误抽为 length（P1 defer bug）。
    方案 B 后 length 不在 patterns 里，size_dict 中无 length 键。"""
    from adapters.solidworks.sw_toolbox_catalog import extract_size_from_name

    result = extract_size_from_name(
        "GB/T 70.1 M6×20 内六角圆柱头螺钉", default_patterns["fastener"]
    )
    assert result == {"size": "M6"}  # 无 length 键
```

**`tests/test_sw_toolbox_adapter.py`**

| 位置 | 变更 |
|---|---|
| `_default_config()` 辅助函数（第 332 行） | `size_patterns.fastener` 删除 `"length"` 键 |

### 不变动的内容

| 文件/位置 | 原因 |
|---|---|
| `sw_toolbox_catalog.py` | 函数配置驱动，config 无 `length` 则不提取，无需代码改动 |
| `build_query_tokens_weighted` | 遍历 `size_dict.values()` 是通用逻辑，不依赖 `length` 键名 |
| `test_extra_non_str_key_does_not_crash`（第 260 行） | 用自己的 patterns 字典测试类型守卫，与生产 config 无关，保持原样 |
| `build_query_tokens_weighted` 两条 hardcoded size_dict 测试（664、684 行） | 测试函数弹性，与生产 config 无关，保持原样 |
| `test_init_accepts_safe_patterns`（第 170 行） | 测试 adapter 接受自定义 config 键，保持原样 |

---

## TDD 节奏

```
Task 1 — RED（写新测试，验证现有代码失败）
  - 新增 test_fastener_gbt_spec_no_prefix_no_length
  - 运行 pytest：预期失败（当前返回 {"size": "M6", "length": "70.1"}）

Task 2 — GREEN（改 YAML，让新测试通过）
  - 两个 parts_library.default.yaml 删除 length 行
  - 运行 pytest：新测试绿；原 4 条断言变红

Task 3 — REFACTOR（修正原有测试断言）
  - 更新 4 条 TestExtractSizeFromName 断言（3 条 M6、1 条 M6.5）
  - 更新 _default_config() 的 size_patterns.fastener
  - 运行 pytest：全绿
```

---

## 验收标准

1. `uv run pytest tests/test_sw_toolbox_catalog.py tests/test_sw_toolbox_adapter.py -v` 全绿
2. `test_fastener_gbt_spec_no_prefix_no_length` 存在且通过
3. `uv run pytest` 完整套件全绿（无退化）
4. `uv run ruff check . && uv run ruff format --check .` 无告警
5. `extract_size_from_name("GB/T 70.1 M6×20 内六角圆柱头螺钉", patterns)` 返回 `{"size": "M6"}`，无 `length` 键
