# SW-B9 PR-a 实施计划 — GB 紧固件中英文同义词表

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `sw_toolbox_catalog.match_toolbox_part` 能把 "GB/T 70.1 M6×20 内六角圆柱头螺钉" 匹配到 SW Toolbox 的英文 sldprt（如 `socket head cap screw_gb.sldprt`），解决 SW-B9 前置阻塞（token 健康检查 #13）。

**Architecture:** 在 `build_query_tokens_weighted` 内新增**子串匹配式**中英同义词扩展层：tokenize 保持原逻辑不变，扩展在组装加权 token 时调用 `expand_cn_synonyms` 注入对等英文 token（同权重）。同义词表走 YAML 外置（复用 `PyYAML` 既有依赖），首次调用懒加载 + lru_cache。

**Tech Stack:** Python 3.11+，PyYAML（parts_library extra 已存在），pytest，`adapters/solidworks/sw_toolbox_catalog.py`。

**关联 Spec：** `docs/superpowers/specs/2026-04-14-sw-b9-real-run-acceptance-design.md` §3（PR-a）+ §13。

---

## File Structure

- Create: `config/toolbox_cn_synonyms.yaml`（~30 条映射，数据配置）
- Create: `tests/test_toolbox_cn_synonyms.py`（单元测试）
- Modify: `adapters/solidworks/sw_toolbox_catalog.py`（新增 `load_cn_synonyms`、`expand_cn_synonyms`；在 `build_query_tokens_weighted` 内调用扩展）

---

### Task 1: 建立同义词表数据文件

**Files:**
- Create: `config/toolbox_cn_synonyms.yaml`

- [ ] **Step 1: 新建 YAML 文件**

路径：`config/toolbox_cn_synonyms.yaml`

```yaml
# 中英文同义词表 — SW Toolbox 紧固件/轴承匹配
# 格式: cn_morpheme (子串) -> [英文 token 列表]
# 匹配方式: 对 tokenize 产出的每个 CJK token，用 str.contains 子串匹配
# 注入权重: 与触发它的原 token 权重相同
#
# 维护规范: 仅新增常见通用标准件词根，避免商标/厂商专用词
# 新增记录需同步 tests/test_toolbox_cn_synonyms.py

fasteners:
  螺钉: [screw]
  螺栓: [bolt, screw]
  螺母: [nut]
  垫圈: [washer]
  平垫圈: [plain, washer]
  弹簧垫圈: [spring, washer, lock]
  内六角: [hex, socket]
  六角: [hex]
  圆柱头: [cap, head, cylinder]
  盘头: [pan, head]
  沉头: [flat, countersunk, head]
  十字: [phillips, cross]
  一字: [slotted]
  自攻: [tapping, self]
  无头: [set]
  紧定: [set]

bearings:
  轴承: [bearing]
  深沟球: [deep, groove, ball]
  圆锥滚子: [tapered, roller]
  圆柱滚子: [cylindrical, roller]
  推力: [thrust]
  滚针: [needle]

pins_keys:
  销: [pin]
  圆柱销: [dowel, pin, cylindrical]
  弹簧销: [spring, pin]
  开口销: [cotter, pin, split]
  平键: [flat, key]
  半圆键: [woodruff, key]

misc:
  碟形: [belleville, disc]
```

- [ ] **Step 2: 验证 YAML 可解析**

```bash
python -c "import yaml; data = yaml.safe_load(open('config/toolbox_cn_synonyms.yaml', encoding='utf-8')); print(list(data.keys())); print(sum(len(v) for v in data.values()), 'entries')"
```

Expected: `['fasteners', 'bearings', 'pins_keys', 'misc']` 和总条数 ≥ 25

- [ ] **Step 3: 提交**

```bash
git add config/toolbox_cn_synonyms.yaml
git commit -m "feat(sw-b): 新增中英文同义词表 config/toolbox_cn_synonyms.yaml"
```

---

### Task 2: `load_cn_synonyms` 加载函数（TDD）

**Files:**
- Modify: `adapters/solidworks/sw_toolbox_catalog.py`（新增函数，追加到文件末尾相关位置）
- Test: `tests/test_toolbox_cn_synonyms.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_toolbox_cn_synonyms.py`：

```python
"""sw_toolbox_catalog 中英文同义词扩展测试（spec §13 / 决策 #34）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestLoadCnSynonyms:
    def test_load_returns_flattened_dict(self):
        """load_cn_synonyms 把分组 YAML 打平为 {cn_key: [en_tokens]}。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms

        synonyms = load_cn_synonyms()
        assert isinstance(synonyms, dict)
        assert "螺钉" in synonyms
        assert synonyms["螺钉"] == ["screw"]
        assert "深沟球" in synonyms
        assert synonyms["深沟球"] == ["deep", "groove", "ball"]

    def test_load_is_cached(self):
        """连续调用返回同一 dict 实例（lru_cache 验证）。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms

        a = load_cn_synonyms()
        b = load_cn_synonyms()
        assert a is b

    def test_load_respects_custom_path(self, tmp_path):
        """支持从参数指定 yaml 路径（测试隔离用）。"""
        from adapters.solidworks.sw_toolbox_catalog import load_cn_synonyms

        custom = tmp_path / "custom.yaml"
        custom.write_text("group1:\n  测试: [test]\n", encoding="utf-8")
        # 注意: 带参数版本不过 lru_cache
        result = load_cn_synonyms(path=custom)
        assert result == {"测试": ["test"]}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py::TestLoadCnSynonyms -v
```

Expected: 3 个 FAIL，`ImportError: cannot import name 'load_cn_synonyms'`

- [ ] **Step 3: 实现最小代码**

在 `adapters/solidworks/sw_toolbox_catalog.py` 文件顶部 `from functools import lru_cache` 导入（若尚未），然后在文件靠近 `tokenize` 函数**之前**（约 line 112 附近）插入：

```python
from functools import lru_cache

DEFAULT_CN_SYNONYMS_PATH = Path(__file__).parent.parent.parent / "config" / "toolbox_cn_synonyms.yaml"


def _load_cn_synonyms_from_path(path: Path) -> dict[str, list[str]]:
    """读取 YAML 并打平分组结构为 {cn_key: [en_tokens]}。"""
    import yaml

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    flat: dict[str, list[str]] = {}
    for group_name, entries in raw.items():
        if not isinstance(entries, dict):
            continue
        for cn_key, en_tokens in entries.items():
            if not isinstance(en_tokens, list):
                continue
            flat[cn_key] = [str(t).lower() for t in en_tokens]
    return flat


@lru_cache(maxsize=1)
def _load_cn_synonyms_cached() -> dict[str, list[str]]:
    return _load_cn_synonyms_from_path(DEFAULT_CN_SYNONYMS_PATH)


def load_cn_synonyms(path: Optional[Path] = None) -> dict[str, list[str]]:
    """加载中英文同义词表。

    无参数调用走 lru_cache（生产路径）；带 path 参数绕开缓存（测试隔离用）。

    Returns:
        {cn_morpheme: [en_token, ...]} 扁平 dict
    """
    if path is None:
        return _load_cn_synonyms_cached()
    return _load_cn_synonyms_from_path(path)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py::TestLoadCnSynonyms -v
```

Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_toolbox_cn_synonyms.py
git commit -m "feat(sw-b): load_cn_synonyms — YAML 同义词表加载 + lru_cache"
```

---

### Task 3: `expand_cn_synonyms` 扩展函数（TDD）

**Files:**
- Modify: `adapters/solidworks/sw_toolbox_catalog.py`
- Test: `tests/test_toolbox_cn_synonyms.py`（追加 test class）

- [ ] **Step 1: 写失败测试**

在 `tests/test_toolbox_cn_synonyms.py` 末尾追加：

```python
class TestExpandCnSynonyms:
    def test_cjk_token_substring_match_injects_en_tokens(self):
        """含 '内六角' 的 CJK token 应注入 [hex, socket]。"""
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        synonyms = {"内六角": ["hex", "socket"], "螺钉": ["screw"]}
        input_tokens = [("内六角圆柱头螺钉", 1.0)]  # 单个长 CJK token
        result = expand_cn_synonyms(input_tokens, synonyms)

        result_map = dict(result)
        assert "内六角圆柱头螺钉" in result_map  # 原 token 保留
        assert result_map["hex"] == 1.0          # 注入同权重
        assert result_map["socket"] == 1.0
        assert result_map["screw"] == 1.0

    def test_ascii_tokens_passthrough(self):
        """非 CJK token 不受影响。"""
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        input_tokens = [("m6", 1.0), ("hex", 1.5)]
        result = expand_cn_synonyms(input_tokens, {"螺钉": ["screw"]})
        assert dict(result) == {"m6": 1.0, "hex": 1.5}

    def test_duplicate_en_keeps_max_weight(self):
        """多源注入同一 en token 时取最大权重。"""
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        # '螺钉' -> [screw], '螺栓' -> [bolt, screw], 两个 CJK token 都含 '螺'
        synonyms = {"螺钉": ["screw"], "螺栓": ["bolt", "screw"]}
        input_tokens = [("螺钉", 1.0), ("螺栓", 2.0)]
        result = dict(expand_cn_synonyms(input_tokens, synonyms))

        assert result["screw"] == 2.0  # 取 max
        assert result["bolt"] == 2.0

    def test_empty_synonyms_noop(self):
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        input_tokens = [("螺钉", 1.0)]
        assert list(expand_cn_synonyms(input_tokens, {})) == input_tokens

    def test_empty_input_returns_empty(self):
        from adapters.solidworks.sw_toolbox_catalog import expand_cn_synonyms

        assert expand_cn_synonyms([], {"螺钉": ["screw"]}) == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py::TestExpandCnSynonyms -v
```

Expected: 5 FAIL，`ImportError: cannot import name 'expand_cn_synonyms'`

- [ ] **Step 3: 实现**

在 `adapters/solidworks/sw_toolbox_catalog.py` 紧接 `load_cn_synonyms` 后追加：

```python
def expand_cn_synonyms(
    tokens_weighted: list[tuple[str, float]],
    synonyms: dict[str, list[str]],
) -> list[tuple[str, float]]:
    """对每个 CJK token 做子串同义词匹配，注入对等英文 token（同权重）。

    规则：
    - 只对含 CJK 字符的 token 做子串扫描（ASCII token 原样透传）
    - 同一英文 token 被多源注入时取最大权重（与 build_query_tokens_weighted 一致）
    - 原 CJK token 保留（不删除），扩展只做添加

    Args:
        tokens_weighted: tokenize + 加权后的 [(token, weight), ...]
        synonyms: load_cn_synonyms 返回的 {cn_morpheme: [en_tokens]}

    Returns:
        扩展后的 [(token, weight), ...]
    """
    if not tokens_weighted or not synonyms:
        return list(tokens_weighted)

    collected: dict[str, float] = {}
    for tok, w in tokens_weighted:
        if tok not in collected or collected[tok] < w:
            collected[tok] = w

    for tok, w in tokens_weighted:
        # 仅对 CJK token 做子串扫描（包含 \u4e00-\u9fff 字符即判定）
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in tok)
        if not has_cjk:
            continue
        for cn_key, en_tokens in synonyms.items():
            if cn_key in tok:
                for en in en_tokens:
                    if en not in collected or collected[en] < w:
                        collected[en] = w

    return list(collected.items())
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py::TestExpandCnSynonyms -v
```

Expected: 5 PASS

- [ ] **Step 5: 提交**

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_toolbox_cn_synonyms.py
git commit -m "feat(sw-b): expand_cn_synonyms — 子串匹配式同义词扩展"
```

---

### Task 4: 把扩展注入到 `build_query_tokens_weighted`（TDD）

**Files:**
- Modify: `adapters/solidworks/sw_toolbox_catalog.py`（函数 `build_query_tokens_weighted`，约 line 556-590）
- Test: `tests/test_toolbox_cn_synonyms.py`

- [ ] **Step 1: 写端到端失败测试**

在 `tests/test_toolbox_cn_synonyms.py` 末尾追加：

```python
class TestEndToEndMatchWithSynonyms:
    """端到端：BOM name_cn 中文 → Toolbox 英文零件命中。"""

    def test_gb_70_1_m6_20_hits_socket_head_cap_screw(self):
        """GB/T 70.1 M6×20 内六角圆柱头螺钉 匹配 'socket head cap screw' sldprt。"""
        from adapters.solidworks.sw_toolbox_catalog import (
            SwToolboxPart,
            build_query_tokens_weighted,
            match_toolbox_part,
        )

        # 伪造含一条 GB 内六角圆柱头螺钉 M6 的索引
        fake_index = {
            "standards": {
                "GB": {
                    "bolts and studs": [
                        SwToolboxPart(
                            standard="GB",
                            subcategory="bolts and studs",
                            sldprt_path="/fake/GB/socket head cap screw_gb.sldprt",
                            filename="socket head cap screw_gb.sldprt",
                            tokens=["socket", "head", "cap", "screw", "m6", "gb"],
                        ),
                    ]
                }
            }
        }

        class Query:
            part_no = "GIS-DEMO-001"
            name_cn = "GB/T 70.1 M6×20 内六角圆柱头螺钉"
            material = "钢"

        weights = {"part_no": 2.0, "name_cn": 1.0, "material": 0.5, "size": 1.5}
        q_tokens = build_query_tokens_weighted(Query(), {"size": "M6"}, weights)

        # 验证扩展确实注入了 'socket' 和 'screw'
        q_map = dict(q_tokens)
        assert "socket" in q_map
        assert "screw" in q_map
        assert "hex" in q_map

        # 端到端匹配
        result = match_toolbox_part(
            fake_index,
            q_tokens,
            standards=["GB"],
            subcategories=["bolts and studs"],
            min_score=0.30,
        )
        assert result is not None
        part, score = result
        assert part.filename == "socket head cap screw_gb.sldprt"
        assert score >= 0.30
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py::TestEndToEndMatchWithSynonyms -v
```

Expected: FAIL（`'socket' not in q_map`，因 build_query_tokens_weighted 尚未接入扩展）

- [ ] **Step 3: 修改 `build_query_tokens_weighted`**

定位 `adapters/solidworks/sw_toolbox_catalog.py` 内 `build_query_tokens_weighted` 函数的 `return` 行（约 line 590）：

```python
    return [(t, w) for t, w in collected.items()]
```

改为：

```python
    base = [(t, w) for t, w in collected.items()]
    synonyms = load_cn_synonyms()
    return expand_cn_synonyms(base, synonyms)
```

- [ ] **Step 4: 运行端到端测试**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py::TestEndToEndMatchWithSynonyms -v
```

Expected: PASS

- [ ] **Step 5: 跑全量同义词测试**

```bash
uv run pytest tests/test_toolbox_cn_synonyms.py -v
```

Expected: 全部 9 个 test PASS

- [ ] **Step 6: 提交**

```bash
git add adapters/solidworks/sw_toolbox_catalog.py tests/test_toolbox_cn_synonyms.py
git commit -m "feat(sw-b): build_query_tokens_weighted 注入中英文同义词扩展"
```

---

### Task 5: 回归既有 toolbox 测试

**Files:**
- 只跑测试，不改代码

- [ ] **Step 1: 全量跑 sw_toolbox 相关测试**

```bash
uv run pytest tests/test_sw_toolbox_catalog.py tests/test_sw_toolbox_adapter.py tests/test_sw_toolbox_adapter_registration.py tests/test_sw_toolbox_integration.py -v
```

Expected: 全部 PASS（同义词扩展仅**新增** token，不删不改，既有行为不变）

- [ ] **Step 2: 若有失败，定位根因**

失败多半因为：
- 原测试 assert q_tokens 的**精确长度**（扩展后变长）→ 改 assert 为 `>= N` 或 set 包含式断言
- 原测试 assert `hit_weight` 精确数值（扩展后命中更多）→ 改 assert 为 `>= 原值`

**禁止**通过禁用扩展或跳过测试绕过失败；改测试 assert 到正确的口径。

- [ ] **Step 3: 跑全项目 pytest 抽查**

```bash
uv run pytest -x --timeout=60 -q
```

Expected: 全绿。若超时或非 toolbox 测试失败，说明扩展影响面超预期，返回 Task 4 Step 3 审视。

- [ ] **Step 4: 提交（若回归需要改测试 assert）**

```bash
git add tests/
git commit -m "test(sw-b): toolbox 回归测试适配同义词扩展后的 token 集合"
```

若 Step 1 一次通过则跳过本步。

---

### Task 6: 创建 PR

- [ ] **Step 1: Push 分支**

```bash
git push -u origin <current-branch>
```

- [ ] **Step 2: 开 PR**

```bash
gh pr create --title "feat(sw-b): GB 紧固件中英文同义词表 (SW-B9 PR-a)" --body "$(cat <<'EOF'
## Summary
- 新增 `config/toolbox_cn_synonyms.yaml` — ~30 条 GB/T 常见紧固件/轴承词根中英映射
- `sw_toolbox_catalog`：新增 `load_cn_synonyms` + `expand_cn_synonyms`；`build_query_tokens_weighted` 注入扩展
- 端到端测试：`GB/T 70.1 M6×20 内六角圆柱头螺钉` 现可命中 SW Toolbox `socket head cap screw_gb.sldprt`

## 背景
SW-B9 真跑验收前置阻塞（详见 `docs/superpowers/specs/2026-04-14-sw-b9-real-run-acceptance-design.md` §13）。既有 tokenize 把 CJK 字符整体保留为单一 token，导致 BOM 中文名与 Toolbox 英文 sldprt 永不命中（demo_bom.csv 历史覆盖率 0%）。本 PR 不改 tokenize，仅在加权阶段做子串同义词扩展。

## 影响面
- 既有 `sw_toolbox_*` 测试全通（Task 5 回归）
- Toolbox 匹配 token 集合会**变大**，同分数下命中率上升；不改匹配算法本身

## Test plan
- [x] `tests/test_toolbox_cn_synonyms.py` — 9 个单测
- [x] 全量 toolbox 回归绿
- [x] 本机 `uv run pytest -x` 通过
- [ ] 合入 main 后由 PR-b（SW-B9 真跑验收）消费

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: 等待 CI + review**

PR 合入 main 后，PR-b 的 Stage 0.5 token 健康检查才能过。

---

## Self-Review 检查清单

- [x] Spec §3 PR-a 范围覆盖（Task 1-4）
- [x] Spec §13 中英文同义词需求覆盖（Task 1 YAML + Task 3/4 代码）
- [x] Spec §9 PR-a 测试策略覆盖（Task 2/3/4 TDD + Task 5 回归）
- [x] 无 TBD / TODO 占位
- [x] 所有代码步骤含完整代码块
- [x] 所有命令含期望输出
- [x] TDD 顺序严格：先失败测试 → 再实现 → 再验证通过 → 再 commit
