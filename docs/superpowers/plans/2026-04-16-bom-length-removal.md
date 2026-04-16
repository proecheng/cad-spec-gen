# BOM length 字段删除 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 `size_patterns.fastener` 删除 `length` 字段，消除 GB/T 规范号（如 `70.1`）被误抽为长度 token 的 bug，同时移除对 Toolbox 文件名匹配无贡献的噪声。

**Architecture:** 纯配置驱动变更。`extract_size_from_name` 遍历 `patterns` dict，config 里删除 `length` 键则函数不再提取该字段，无需修改任何 Python 源码。测试文件需同步更新：新增回归测试 + 修正旧断言。

**Tech Stack:** Python 3.11+, pytest, uv, YAML

**Spec:** `docs/superpowers/specs/2026-04-16-bom-length-removal-design.md`

---

## 文件清单

| 操作 | 文件 | 变更摘要 |
|---|---|---|
| Modify | `tests/test_sw_toolbox_catalog.py` | 新增回归测试；删 fixture `length` 键；更新 4 条断言 |
| Modify | `parts_library.default.yaml` | 删除第 74 行 `length:` |
| Modify | `src/cad_spec_gen/data/parts_library.default.yaml` | 同上（两文件内容相同） |
| Modify | `tests/test_sw_toolbox_adapter.py` | `_default_config()` 删除 `length` 键 |

---

## Task 1：写新回归测试（RED）

**Files:**
- Modify: `tests/test_sw_toolbox_catalog.py:166`（在 `test_bearing_suffix_preserved_only_base` 之后、`class TestValidateSizePatterns` 之前插入）

- [ ] **Step 1: 在 `test_sw_toolbox_catalog.py` 第 166 行之后插入新测试方法**

  精确插入位置：`TestExtractSizeFromName` 类末尾，`test_bearing_suffix_preserved_only_base` 方法结束后（line 166），紧接空行。

  在第 167 行（`class TestValidateSizePatterns:` 前的空行）之前插入：

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

- [ ] **Step 2: 运行新测试，确认失败（RED）**

  ```bash
  uv run pytest tests/test_sw_toolbox_catalog.py::TestExtractSizeFromName::test_fastener_gbt_spec_no_prefix_no_length -v
  ```

  预期输出（节选）：
  ```
  FAILED tests/test_sw_toolbox_catalog.py::TestExtractSizeFromName::test_fastener_gbt_spec_no_prefix_no_length
  AssertionError: assert {'length': '70.1', 'size': 'M6'} == {'size': 'M6'}
  ```

  若看到上述失败（返回 `length: '70.1'`），RED 确认 ✓。若测试意外通过，停止并检查 `default_patterns` fixture 是否已被提前修改。

---

## Task 2：更新 fixture + YAML（GREEN）

**Files:**
- Modify: `tests/test_sw_toolbox_catalog.py:89`（fixture 删 `length` 键）
- Modify: `parts_library.default.yaml:74`（删 `length:` 行）
- Modify: `src/cad_spec_gen/data/parts_library.default.yaml:74`（同上）

- [ ] **Step 1: 更新 `default_patterns` fixture，删除 `"length"` 键**

  在 `tests/test_sw_toolbox_catalog.py` 的 `TestExtractSizeFromName.default_patterns` fixture（约 84-95 行）：

  ```python
  # 变更前
  @pytest.fixture
  def default_patterns(self):
      return {
          "fastener": {
              "size": r"[Mm](\d+(?:\.\d+)?)",
              "length": r"[×xX*\-\s](\d+(?:\.\d+)?)",
              "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
          },
          "bearing": {
              "model": r"\b(\d{4,5})\b",
          },
      }

  # 变更后
  @pytest.fixture
  def default_patterns(self):
      return {
          "fastener": {
              "size": r"[Mm](\d+(?:\.\d+)?)",
              "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
          },
          "bearing": {
              "model": r"\b(\d{4,5})\b",
          },
      }
  ```

- [ ] **Step 2: 删除 `parts_library.default.yaml` 的 `length:` 行**

  文件：`parts_library.default.yaml`，约第 70-78 行：

  ```yaml
  # 变更前
  size_patterns:
    fastener:
      size: '[Mm](\d+(?:\.\d+)?)'
      length: '[×xX*\-\s](\d+(?:\.\d+)?)'
      exclude_patterns: ['UN[CFEF]', '\bTr\d', '\bG\d/', '\bNPT']
    bearing:
      model: '\b(\d{4,5})\b'

  # 变更后
  size_patterns:
    fastener:
      size: '[Mm](\d+(?:\.\d+)?)'
      exclude_patterns: ['UN[CFEF]', '\bTr\d', '\bG\d/', '\bNPT']
    bearing:
      model: '\b(\d{4,5})\b'
  ```

- [ ] **Step 3: 对 `src/cad_spec_gen/data/parts_library.default.yaml` 做同样变更**

  该文件与根目录版本内容完全相同，同样删除 `length:` 行（约第 74 行）。变更内容与 Step 2 一致。

- [ ] **Step 4: 运行新测试，确认通过（GREEN）**

  ```bash
  uv run pytest tests/test_sw_toolbox_catalog.py::TestExtractSizeFromName::test_fastener_gbt_spec_no_prefix_no_length -v
  ```

  预期：
  ```
  PASSED
  ```

- [ ] **Step 5: 运行 `TestExtractSizeFromName` 整个类，确认旧断言变红**

  ```bash
  uv run pytest tests/test_sw_toolbox_catalog.py::TestExtractSizeFromName -v
  ```

  预期：新测试 PASSED；以下 4 条测试 FAILED（断言仍含 `length`，尚未更新）：
  - `test_fastener_m6x20_multiplication_sign`
  - `test_fastener_m6x20_ascii_x`
  - `test_fastener_m6_hyphen_20`
  - `test_fastener_decimal_thread`

  若 4 条全部失败，Task 3 前提已就绪 ✓。

---

## Task 3：修正旧断言 + adapter config（REFACTOR）

**Files:**
- Modify: `tests/test_sw_toolbox_catalog.py:103,109,115,121`
- Modify: `tests/test_sw_toolbox_adapter.py:332`

- [ ] **Step 1: 更新 `TestExtractSizeFromName` 4 条断言**

  **第 103 行**（`test_fastener_m6x20_multiplication_sign`）：
  ```python
  # 变更前
  assert result == {"size": "M6", "length": "20"}
  # 变更后
  assert result == {"size": "M6"}
  ```

  **第 109 行**（`test_fastener_m6x20_ascii_x`）：
  ```python
  # 变更前
  assert result == {"size": "M6", "length": "20"}
  # 变更后
  assert result == {"size": "M6"}
  ```

  **第 115 行**（`test_fastener_m6_hyphen_20`）：
  ```python
  # 变更前
  assert result == {"size": "M6", "length": "20"}
  # 变更后
  assert result == {"size": "M6"}
  ```

  **第 121 行**（`test_fastener_decimal_thread`）：
  ```python
  # 变更前
  assert result == {"size": "M6.5", "length": "20"}
  # 变更后
  assert result == {"size": "M6.5"}
  ```

- [ ] **Step 2: 更新 `tests/test_sw_toolbox_adapter.py` 的 `_default_config()`**

  `_default_config()` 函数（约第 320-337 行），`size_patterns.fastener` 段删除 `"length"` 键：

  ```python
  # 变更前
  "size_patterns": {
      "fastener": {
          "size": r"[Mm](\d+(?:\.\d+)?)",
          "length": r"[×xX*\-\s](\d+(?:\.\d+)?)",
          "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
      },
      "bearing": {"model": r"\b(\d{4,5})\b"},
  },

  # 变更后
  "size_patterns": {
      "fastener": {
          "size": r"[Mm](\d+(?:\.\d+)?)",
          "exclude_patterns": [r"UN[CFEF]", r"\bTr\d", r"\bG\d/", r"\bNPT"],
      },
      "bearing": {"model": r"\b(\d{4,5})\b"},
  },
  ```

- [ ] **Step 3: 运行 catalog + adapter 两个测试文件，确认全绿**

  ```bash
  uv run pytest tests/test_sw_toolbox_catalog.py tests/test_sw_toolbox_adapter.py -v
  ```

  预期：所有测试 PASSED，无 FAILED 或 ERROR。

- [ ] **Step 4: 运行完整测试套件，确认无退化**

  ```bash
  uv run pytest -x
  ```

  预期：全绿（`requires_solidworks` 标记的真机测试自动跳过，不影响结果）。

- [ ] **Step 5: ruff 检查**

  ```bash
  uv run ruff check . && uv run ruff format --check .
  ```

  预期：无输出（零告警）。

- [ ] **Step 6: 提交**

  ```bash
  git add tests/test_sw_toolbox_catalog.py \
          parts_library.default.yaml \
          src/cad_spec_gen/data/parts_library.default.yaml \
          tests/test_sw_toolbox_adapter.py
  git commit -m "fix(sw-c): 删除 size_patterns.fastener.length 字段，消除规范号污染 token 的 bug

  length token 对 Toolbox 文件名匹配无贡献（文件名为型号级模板），
  且 \\s 分隔符导致 GB/T 70.1 被误抽为长度。方案 B：直接删除字段。

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
  ```

---

## 验收清单

- [ ] `uv run pytest tests/test_sw_toolbox_catalog.py::TestExtractSizeFromName::test_fastener_gbt_spec_no_prefix_no_length` PASSED
- [ ] `uv run pytest tests/test_sw_toolbox_catalog.py tests/test_sw_toolbox_adapter.py` 全绿
- [ ] `uv run pytest -x` 完整套件无退化
- [ ] `uv run ruff check .` 无告警
- [ ] 两个 `parts_library.default.yaml` 均已删除 `length:` 行
